#!/usr/bin/env python3
"""
Static asset / branding audit for iOS App Store submissions.

Inspects app icons, launch screens, and design tokens for the technical
compliance issues Apple's automated pipeline and reviewers catch — the
deterministic subset that can be checked from files without rendering the
running app or making a subjective "does this look good" judgment.

Checks:
  - App icon 1024x1024 master present, exactly square, correct dimensions
  - App icon has NO alpha channel (a top cause of automated rejection)
  - App icon PNG is not manually rounded (heuristic: transparent corners on
    an otherwise-opaque image suggests a hand-applied corner radius)
  - Asset catalog AppIcon.appiconset Contents.json references a
    1024 ios-marketing icon and the referenced files exist
  - Launch screen storyboard/asset present (blank/placeholder launch is a
    2.1 completeness smell)
  - Placeholder-looking icon assets (all-one-color, near-empty)

Uses Pillow if available for pixel-level checks; degrades gracefully to
dimension/structure checks parsed from PNG headers if not.

This is a technical-compliance check, not a design-quality opinion. It will
not tell you whether your branding is *good* — only whether the asset files
will survive App Store Connect's automated validation and a reviewer's eye
for obvious placeholder art.
"""

import json
import struct
from pathlib import Path

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

EXCLUDE_DIRS = {
    ".git", "node_modules", "Pods", "build", "DerivedData", ".dart_tool",
    "Carthage", ".build", "dist", "out", "__pycache__", ".gradle",
    "xcuserdata",
}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and not any(p in EXCLUDE_DIRS for p in path.parts):
            yield path


def read_png_dimensions(path: Path):
    """Parse width/height/colortype from a PNG header without Pillow.

    Returns (width, height, color_type) or None. color_type 6 = RGBA,
    2 = RGB, 4 = grayscale+alpha, 0 = grayscale, 3 = palette.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(26)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        if header[12:16] != b"IHDR":
            return None
        width, height = struct.unpack(">II", header[16:24])
        color_type = header[25]
        return width, height, color_type
    except (OSError, struct.error):
        return None


def has_alpha_channel(path: Path):
    """Return True if the PNG declares an alpha channel.

    With Pillow we check the mode precisely; without it we fall back to the
    PNG color_type byte (6 = RGBA, 4 = grayscale+alpha).
    """
    if HAVE_PIL:
        try:
            with Image.open(path) as im:
                if im.mode in ("RGBA", "LA", "PA"):
                    return True
                if "transparency" in im.info:
                    return True
                return False
        except Exception:
            pass
    dims = read_png_dimensions(path)
    if dims:
        return dims[2] in (4, 6)
    return None


def corners_transparent(path: Path):
    """Heuristic for a hand-applied corner radius: the four corner pixels
    are fully transparent while the center is opaque. Only meaningful when
    Pillow is available and the image actually has alpha."""
    if not HAVE_PIL:
        return None
    try:
        with Image.open(path) as im:
            if im.mode not in ("RGBA", "LA", "PA"):
                return False
            im = im.convert("RGBA")
            w, h = im.size
            if w < 4 or h < 4:
                return False
            corners = [
                im.getpixel((0, 0)),
                im.getpixel((w - 1, 0)),
                im.getpixel((0, h - 1)),
                im.getpixel((w - 1, h - 1)),
            ]
            center = im.getpixel((w // 2, h // 2))
            corners_clear = all(px[3] < 16 for px in corners)
            center_opaque = center[3] > 240
            return corners_clear and center_opaque
    except Exception:
        return None


def looks_like_placeholder_icon(path: Path):
    """Heuristic: an icon that is a single flat color (or nearly so) across
    the whole image is very likely a placeholder, not real branding."""
    if not HAVE_PIL:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB").resize((16, 16))
            colors = im.getcolors(maxcolors=256) or []
            if not colors:
                return None
            dominant = max(colors, key=lambda c: c[0])
            total = sum(c[0] for c in colors)
            # >97% of pixels one color -> almost certainly a placeholder fill
            return (dominant[0] / total) > 0.97
    except Exception:
        return None


def find_appicon_sets(root: Path):
    return [p for p in root.rglob("*.appiconset")
            if p.is_dir() and not any(x in EXCLUDE_DIRS for x in p.parts)]


def audit_appicon_set(iconset: Path):
    findings = {"path": str(iconset), "issues": [], "master_icon": None}
    contents = iconset / "Contents.json"
    referenced = []
    if contents.exists():
        try:
            data = json.loads(contents.read_text())
            for entry in data.get("images", []):
                fn = entry.get("filename")
                if fn:
                    referenced.append((entry.get("size"), entry.get("idiom"),
                                       entry.get("scale"), fn))
        except (OSError, json.JSONDecodeError):
            findings["issues"].append(
                "Contents.json present but unreadable/invalid JSON")
    else:
        findings["issues"].append("No Contents.json in appiconset")

    has_marketing = any(
        idiom == "ios-marketing" or (size and size.startswith("1024"))
        for size, idiom, scale, fn in referenced)
    if referenced and not has_marketing:
        findings["issues"].append(
            "No 1024x1024 ios-marketing icon referenced in Contents.json "
            "(App Store Connect requires it)")

    for size, idiom, scale, fn in referenced:
        if not (iconset / fn).exists():
            findings["issues"].append(f"Referenced icon file missing: {fn}")

    # Find the largest actual PNG in the set to treat as the master
    pngs = list(iconset.glob("*.png"))
    master = None
    master_dims = (0, 0)
    for p in pngs:
        dims = read_png_dimensions(p)
        if dims and dims[0] * dims[1] > master_dims[0] * master_dims[1]:
            master, master_dims = p, (dims[0], dims[1])
    if master:
        findings["master_icon"] = str(master)
        w, h = master_dims
        if (w, h) != (1024, 1024):
            findings["issues"].append(
                f"Largest icon {master.name} is {w}x{h}, expected 1024x1024 "
                "master")
        if w != h:
            findings["issues"].append(
                f"Master icon {master.name} is not square ({w}x{h})")
        alpha = has_alpha_channel(master)
        if alpha:
            findings["issues"].append(
                f"Master icon {master.name} has an alpha channel — iOS App "
                "Store rejects transparent icons; flatten onto a solid "
                "background")
        rounded = corners_transparent(master)
        if rounded:
            findings["issues"].append(
                f"Master icon {master.name} appears to have hand-applied "
                "rounded corners (transparent corners) — iOS masks corners "
                "automatically; submit a full square")
        placeholder = looks_like_placeholder_icon(master)
        if placeholder:
            findings["issues"].append(
                f"Master icon {master.name} looks like a flat placeholder "
                "(single dominant color) — verify this is real branding")
    return findings


def find_launch_screens(root: Path):
    hits = []
    for path in iter_files(root):
        name = path.name.lower()
        if name in ("launchscreen.storyboard", "launch_screen.xib") or \
           "launchscreen" in name.replace(" ", ""):
            hits.append(str(path))
    return hits


def audit_assets(root: Path):
    root = Path(root).resolve()
    iconsets = find_appicon_sets(root)
    icon_findings = [audit_appicon_set(s) for s in iconsets]
    launch = find_launch_screens(root)

    checks = []

    if not iconsets:
        checks.append({
            "id": "app_icon_present",
            "guideline": "2.3 / submission",
            "status": "WARN",
            "summary": "No *.appiconset found — expected for a native iOS "
                       "target. If this is React Native/Flutter, the icon "
                       "set is usually under ios/<App>/Images.xcassets.",
        })
    else:
        all_issues = [i for f in icon_findings for i in f["issues"]]
        checks.append({
            "id": "app_icon_compliance",
            "guideline": "2.3 / submission",
            "status": "FAIL" if all_issues else "PASS",
            "summary": (f"{len(all_issues)} icon issue(s) found across "
                        f"{len(iconsets)} icon set(s)"
                        if all_issues else
                        f"{len(iconsets)} app icon set(s) look technically "
                        "compliant"),
            "detail": icon_findings,
        })

    checks.append({
        "id": "launch_screen_present",
        "guideline": "2.1",
        "status": "PASS" if launch else "WARN",
        "summary": (f"{len(launch)} launch screen file(s) found"
                    if launch else
                    "No launch screen storyboard/xib found — a blank or "
                    "default launch experience reads as incomplete (2.1)"),
        "detail": launch,
    })

    if not HAVE_PIL:
        checks.append({
            "id": "pixel_checks_available",
            "guideline": "n/a",
            "status": "WARN",
            "summary": "Pillow not installed — alpha-channel, rounded-corner "
                       "and placeholder pixel checks were skipped. Install "
                       "with: pip install Pillow — for full asset auditing.",
        })

    return {"asset_checks": checks, "icon_findings": icon_findings}


if __name__ == "__main__":
    import sys
    report = audit_assets(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(json.dumps(report, indent=2))
