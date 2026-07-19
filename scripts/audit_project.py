#!/usr/bin/env python3
"""
App Store Rejection Audit — static analysis for common Apple App Review
rejection triggers.

Scans a project directory (native iOS, React Native, Flutter, or Capacitor/
webview-wrapped) for patterns that map to the most-cited App Store Review
Guideline categories: 2.1 (App Completeness), 3.1.1/3.1.2 (IAP &
Subscriptions), 4.2 (Minimum Functionality), 4.8 (Sign in with Apple), and
5.1.1 (Privacy / permissions / account deletion).

This is a heuristic static scan, not a guarantee of App Review approval.
Several major rejection categories (crash testing on a real device, App
Store Connect metadata/screenshots, the App Privacy questionnaire, visual
judgment calls) cannot be checked from source code at all — see the
"Can't be automated" section printed at the end of every report.

Usage:
    python3 audit_project.py /path/to/project
    python3 audit_project.py /path/to/project --json
    python3 audit_project.py /path/to/project --json --output report.json
"""

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {
    ".git", "node_modules", "Pods", "build", "DerivedData", ".dart_tool",
    "Carthage", ".build", "dist", "out", "__pycache__", ".gradle",
    "xcuserdata", ".idea", ".vscode",
}

SOURCE_EXTENSIONS = {
    ".swift", ".m", ".mm", ".h", ".js", ".jsx", ".ts", ".tsx", ".dart",
    ".html", ".htm", ".json", ".xml", ".storyboard", ".xib", ".kt", ".java",
}

MAX_FILE_BYTES = 2_000_000  # skip anything unusually large (bundled assets etc.)

HIGH_SEVERITY_PLACEHOLDERS = {
    "lorem ipsum": re.compile(r"lorem\s+ipsum", re.I),
    "coming soon": re.compile(r"coming\s+soon", re.I),
    "under construction": re.compile(r"under\s+construction", re.I),
    "not yet implemented": re.compile(r"not\s+(?:yet\s+)?implemented", re.I),
    "dummy/test data marker": re.compile(
        r"\bdummy\s+data\b|\btest\s+data\s*[-\u2013\u2014]\s*remove\b", re.I
    ),
}
LOW_SEVERITY_MARKERS = re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b")

PERMISSION_CHECKS = [
    ("Camera", re.compile(
        r"AVCaptureDevice|expo-camera|react-native-camera|CameraX|"
        r"cordova-plugin-camera", re.I),
        ["NSCameraUsageDescription"]),
    ("Location", re.compile(
        r"CLLocationManager|requestWhenInUseAuthorization|"
        r"requestAlwaysAuthorization|expo-location|react-native-geolocation|"
        r"@react-native-community/geolocation|Geolocator\(", re.I),
        ["NSLocationWhenInUseUsageDescription",
         "NSLocationAlwaysAndWhenInUseUsageDescription"]),
    ("Microphone", re.compile(
        r"AVAudioSession|requestRecordPermission|expo-av|"
        r"react-native-audio-recorder|SpeechRecognizer", re.I),
        ["NSMicrophoneUsageDescription"]),
    ("Photo Library", re.compile(
        r"PHPhotoLibrary|expo-image-picker|react-native-image-picker|"
        r"image_picker:|photo_manager:", re.I),
        ["NSPhotoLibraryUsageDescription"]),
    ("Contacts", re.compile(
        r"CNContactStore|expo-contacts|react-native-contacts|"
        r"contacts_service:", re.I),
        ["NSContactsUsageDescription"]),
    ("Apple Music / Media Library", re.compile(
        r"MPMediaLibrary|MPMediaPickerController", re.I),
        ["NSAppleMusicUsageDescription"]),
    ("Health", re.compile(r"HKHealthStore|health_kit", re.I),
        ["NSHealthShareUsageDescription", "NSHealthUpdateUsageDescription"]),
    ("Bluetooth", re.compile(
        r"CBCentralManager|CBPeripheralManager|flutter_blue|"
        r"react-native-ble", re.I),
        ["NSBluetoothAlwaysUsageDescription",
         "NSBluetoothPeripheralUsageDescription"]),
    ("Calendar", re.compile(
        r"EKEventStore|expo-calendar|react-native-calendar-events|"
        r"device_calendar:", re.I),
        ["NSCalendarsUsageDescription"]),
    ("Face ID", re.compile(
        r"LAContext|LocalAuthentication|local_auth:|"
        r"expo-local-authentication", re.I),
        ["NSFaceIDUsageDescription"]),
]

SOCIAL_LOGIN_RE = re.compile(
    r"GoogleSignIn|GIDSignIn|FBSDKLoginKit|LoginButton|GoogleAuthProvider|"
    r"signInWithGoogle|react-native-fbsdk|FacebookLogin|TwitterKit|"
    r"signInWithFacebook", re.I)
APPLE_SIGNIN_RE = re.compile(
    r"ASAuthorizationAppleIDProvider|AuthenticationServices|"
    r"SignInWithAppleButton|expo-apple-authentication|"
    r"sign[_\s-]?in[_\s-]?with[_\s-]?apple|apple_sign_in|AppleAuthProvider",
    re.I)

SIGNUP_RE = re.compile(
    r"\bsign\s?up\b|createAccount|createUserWithEmail|registerUser|"
    r"/auth/signup|/api/register", re.I)
DELETE_ACCOUNT_RE = re.compile(
    r"delete[_\s]?account|deleteUser|deauthorize|remove[_\s]?account|"
    r"/account/delete|/user/delete|closeAccount", re.I)

WEBVIEW_RE = re.compile(
    r"WKWebView|UIWebView|react-native-webview|flutter_webview|"
    r"InAppWebView", re.I)
NATIVE_UI_HINT_RE = re.compile(
    r"UIViewController|StatelessWidget|StatefulWidget|SwiftUI|"
    r"extends React\.Component|export default function", re.I)

IAP_RE = re.compile(
    r"StoreKit|SKProduct|SKPaymentQueue|react-native-iap|in_app_purchase:|"
    r"Purchases\.configure|RevenueCat|Adapty|Qonversion", re.I)
POLICY_RE = re.compile(r"privacy\s*policy", re.I)
EULA_RE = re.compile(
    r"terms\s*of\s*use|\beula\b|terms\s*and\s*conditions|terms\s*of\s*service",
    re.I)
URL_HINT_RE = re.compile(r"https?://", re.I)


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def load_text(path: Path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return None


def gather_source_files(root: Path):
    files = []
    for path in iter_files(root):
        if path.suffix.lower() in SOURCE_EXTENSIONS:
            text = load_text(path)
            if text is not None:
                files.append((path, text))
    return files


def find_info_plists(root: Path):
    return [p for p in iter_files(root) if p.name == "Info.plist"]


def load_plist_keys(path: Path):
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str)}
    except Exception:
        return {}


def check_placeholders(files):
    findings = []
    todo_count = 0
    for path, text in files:
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pattern in HIGH_SEVERITY_PLACEHOLDERS.items():
                if pattern.search(line):
                    findings.append({
                        "file": str(path),
                        "line": lineno,
                        "marker": label,
                        "snippet": line.strip()[:120],
                    })
            if LOW_SEVERITY_MARKERS.search(line):
                todo_count += 1
    return findings, todo_count


def check_permissions(files, plist_keys):
    missing = []
    for name, api_pattern, required_keys in PERMISSION_CHECKS:
        used = any(api_pattern.search(text) for _, text in files)
        if not used:
            continue
        has_nonempty = False
        for keys in plist_keys.values():
            for rk in required_keys:
                val = keys.get(rk)
                if isinstance(val, str) and val.strip():
                    has_nonempty = True
        if not has_nonempty:
            missing.append({"permission": name, "required_keys": required_keys})
    return missing


def check_sign_in_with_apple(files):
    has_social = any(SOCIAL_LOGIN_RE.search(text) for _, text in files)
    has_apple = any(APPLE_SIGNIN_RE.search(text) for _, text in files)
    return has_social, has_apple


def check_account_deletion(files):
    has_signup = any(SIGNUP_RE.search(text) for _, text in files)
    has_delete = any(DELETE_ACCOUNT_RE.search(text) for _, text in files)
    return has_signup, has_delete


def check_webview_ratio(files):
    ui_like = [
        (p, t) for p, t in files
        if p.suffix.lower() in {".swift", ".m", ".mm", ".dart", ".tsx", ".jsx"}
    ]
    if not ui_like:
        return None
    webview_files = sum(1 for _, t in ui_like if WEBVIEW_RE.search(t))
    native_hint_files = sum(1 for _, t in ui_like if NATIVE_UI_HINT_RE.search(t))
    total = len(ui_like)
    ratio = webview_files / total if total else 0
    return {
        "webview_files": webview_files,
        "native_hint_files": native_hint_files,
        "total_ui_files": total,
        "ratio": round(ratio, 2),
    }


def check_iap_and_policy(files):
    has_iap = any(IAP_RE.search(text) for _, text in files)
    has_policy_link = any(
        POLICY_RE.search(text) and URL_HINT_RE.search(text) for _, text in files
    )
    has_eula_link = any(
        EULA_RE.search(text) and URL_HINT_RE.search(text) for _, text in files
    )
    has_policy_mention = any(POLICY_RE.search(text) for _, text in files)
    return {
        "has_iap": has_iap,
        "has_policy_link": has_policy_link,
        "has_eula_link": has_eula_link,
        "has_policy_mention_anywhere": has_policy_mention,
    }


def build_report(root: Path):
    files = gather_source_files(root)
    plists = find_info_plists(root)
    plist_keys = {str(p): load_plist_keys(p) for p in plists}

    placeholder_findings, todo_count = check_placeholders(files)
    missing_permissions = check_permissions(files, plist_keys)
    has_social, has_apple = check_sign_in_with_apple(files)
    has_signup, has_delete = check_account_deletion(files)
    webview_info = check_webview_ratio(files)
    iap_info = check_iap_and_policy(files)

    checks = []

    checks.append({
        "id": "placeholder_content",
        "guideline": "2.1",
        "status": "FAIL" if placeholder_findings else "PASS",
        "summary": (
            f"{len(placeholder_findings)} high-severity placeholder marker(s) found"
            if placeholder_findings else "No obvious placeholder content found"
        ),
        "detail": placeholder_findings[:20],
        "note": (f"{todo_count} TODO/FIXME/XXX marker(s) also found — advisory "
                 "only, verify none are reachable as shipped UI text."
                 if todo_count else None),
    })

    checks.append({
        "id": "info_plist_found",
        "guideline": "5.1.1",
        "status": "PASS" if plists else "WARN",
        "summary": (f"{len(plists)} Info.plist file(s) found"
                    if plists else "No Info.plist found in project tree — "
                    "expected for a native iOS target"),
    })

    checks.append({
        "id": "permission_usage_strings",
        "guideline": "5.1.1",
        "status": "FAIL" if missing_permissions else "PASS",
        "summary": (
            f"{len(missing_permissions)} permission(s) used in code without a "
            "matching non-empty Info.plist usage-description string"
            if missing_permissions else
            "All detected permission APIs have a matching Info.plist usage string"
        ),
        "detail": missing_permissions,
    })

    if has_social:
        checks.append({
            "id": "sign_in_with_apple",
            "guideline": "4.8",
            "status": "PASS" if has_apple else "FAIL",
            "summary": (
                "Third-party social login detected and Sign in with Apple "
                "also detected" if has_apple else
                "Third-party social login (Google/Facebook/etc.) detected "
                "WITHOUT Sign in with Apple — required by Guideline 4.8"
            ),
        })
    else:
        checks.append({
            "id": "sign_in_with_apple",
            "guideline": "4.8",
            "status": "PASS",
            "summary": "No third-party social login detected — Sign in with "
                       "Apple not required",
        })

    if has_signup:
        checks.append({
            "id": "account_deletion",
            "guideline": "5.1.1(v)",
            "status": "PASS" if has_delete else "FAIL",
            "summary": (
                "Account creation and account deletion markers both found"
                if has_delete else
                "Account creation markers found but no account deletion "
                "markers detected — required if the app supports sign-up"
            ),
        })
    else:
        checks.append({
            "id": "account_deletion",
            "guideline": "5.1.1(v)",
            "status": "PASS",
            "summary": "No account-creation markers detected — account "
                       "deletion requirement likely not applicable",
        })

    if webview_info:
        ratio = webview_info["ratio"]
        status = "WARN" if ratio > 0.3 else "PASS"
        checks.append({
            "id": "webview_ratio",
            "guideline": "4.2",
            "status": status,
            "summary": (
                f"{webview_info['webview_files']}/{webview_info['total_ui_files']} "
                f"UI-ish source files reference a webview component "
                f"(ratio {ratio}). "
                + ("This is advisory, not a guarantee of a 4.2 rejection — "
                   "review references/app-completeness-and-design.md."
                   if status == "WARN" else "")
            ),
            "detail": webview_info,
        })

    if iap_info["has_iap"]:
        status = "PASS" if (iap_info["has_policy_link"] and iap_info["has_eula_link"]) else "FAIL"
        checks.append({
            "id": "iap_policy_eula_links",
            "guideline": "3.1.2",
            "status": status,
            "summary": (
                "IAP/subscription SDK detected; Privacy Policy and Terms of "
                "Use links with a URL both found in source"
                if status == "PASS" else
                "IAP/subscription SDK detected but a Privacy Policy and/or "
                "Terms of Use (EULA) link with an actual URL was not found "
                "in source — required in-app for auto-renewable subscriptions"
            ),
            "detail": iap_info,
        })
    else:
        checks.append({
            "id": "iap_policy_eula_links",
            "guideline": "3.1.2",
            "status": "PASS",
            "summary": "No IAP/subscription SDK detected",
        })

    if not iap_info["has_iap"]:
        checks.append({
            "id": "privacy_policy_present",
            "guideline": "5.1.1",
            "status": "PASS" if iap_info["has_policy_mention_anywhere"] else "WARN",
            "summary": (
                "Privacy Policy mentioned somewhere in source"
                if iap_info["has_policy_mention_anywhere"] else
                "No mention of a Privacy Policy found anywhere in source — "
                "verify one exists and is linked in-app and in App Store "
                "Connect metadata if the app collects any personal data"
            ),
        })

    return {
        "project": str(root),
        "files_scanned": len(files),
        "info_plists_found": [str(p) for p in plists],
        "checks": checks,
        "cannot_be_automated": [
            "Crash-free launch and navigation on a real device (multiple "
            "iOS versions / device sizes)",
            "App Store Connect screenshots, description, and age rating "
            "accuracy",
            "Whether the app is a near-duplicate of existing templated apps "
            "(Guideline 4.3 spam)",
            "Demo/reviewer account credentials actually working today, and "
            "not gated behind SMS/authenticator 2FA",
            "Whether a subscription provides genuine 'dynamic, ongoing "
            "value' vs. a one-time unlock (Guideline 3.1.2)",
            "Whether the billed subscription price is visually as prominent "
            "as free-trial messaging",
            "App Privacy ('Nutrition Label') questionnaire accuracy in App "
            "Store Connect, including third-party SDK data collection",
            "Third-party SDK privacy manifest currency",
            "AI data-sharing consent screen, if the app calls an external "
            "LLM API",
            "App Review Notes briefing the reviewer on non-obvious flows",
        ],
    }


def render_markdown(report):
    lines = []
    lines.append(f"# App Store Rejection Audit — {report['project']}")
    lines.append("")
    lines.append(f"Files scanned: {report['files_scanned']}")
    lines.append(f"Info.plist found: {len(report['info_plists_found'])}")
    lines.append("")
    lines.append("| Status | Guideline | Check | Summary |")
    lines.append("|---|---|---|---|")
    for c in report["checks"]:
        icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[c["status"]]
        lines.append(f"| {icon} | {c['guideline']} | {c['id']} | {c['summary']} |")
    lines.append("")
    for c in report["checks"]:
        if c.get("detail"):
            lines.append(f"### {c['id']} — detail")
            lines.append("```")
            lines.append(json.dumps(c["detail"], indent=2)[:3000])
            lines.append("```")
        if c.get("note"):
            lines.append(f"> {c['note']}")
    lines.append("")
    lines.append("## Can't be automated — check these manually")
    for item in report["cannot_be_automated"]:
        lines.append(f"- {item}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_path", help="Path to the project root")
    parser.add_argument("--json", action="store_true",
                         help="Output machine-readable JSON instead of Markdown")
    parser.add_argument("--output", help="Write report to this file instead of stdout")
    args = parser.parse_args()

    root = Path(args.project_path).resolve()
    if not root.exists():
        print(f"Error: path not found: {root}", file=sys.stderr)
        sys.exit(1)

    report = build_report(root)
    output = json.dumps(report, indent=2) if args.json else render_markdown(report)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)

    fail_count = sum(1 for c in report["checks"] if c["status"] == "FAIL")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
