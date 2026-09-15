#!/usr/bin/env python3
"""
Autofixer for App Store Rejection Audit findings.

Two tiers, by design:

  SAFE (applied by default, or shown with --dry-run):
    - Add missing Info.plist permission usage-description strings with a
      clear, editable default value (you should still reword them).
    - Append Apple's standard EULA line to a metadata description file if an
      IAP/subscription was detected and no Terms-of-Use link exists.
    - Flatten an app icon's alpha channel by compositing onto a solid
      background (requires Pillow), fixing the #1 automated icon rejection.
    - Add a 1024 ios-marketing entry stub to an appiconset Contents.json if
      one is missing (points at an expected filename you then supply).
    - Add ITSAppUsesNonExemptEncryption = false to Info.plist when absent
      (the standard HTTPS-only exemption; the note tells you when that is
      the wrong answer).
    - Add a PrivacyInfo.xcprivacy required-reason entry (with the most
      common approved code) for each category the audit found in your own
      native code but not in the manifest — ITMS-91053 is an upload block.
    - Annotate a floating `xcode: latest` CI pin with a TODO comment. It
      never rewrites the pin itself: which Xcode meets the current minimum
      is a fact about today, not about the repo.

  AGGRESSIVE (only with --aggressive, and always emitted as a reviewable
  patch/scaffold, NEVER a silent edit to working auth/purchase code):
    - Scaffold a Sign in with Apple button + entitlement notes.
    - Scaffold an in-app "Delete Account" flow stub.
    - Scaffold a third-party AI consent screen (Swift + React/Capacitor)
      that gates on the consent value ALONE — no "seen" flag.
    - Scaffold a Restore Purchases control for the paywall.
  These require real integration work (Apple Developer config, entitlements,
  server-side token handling). The tool writes clearly-marked TODO scaffolds
  and prints exactly what you must complete by hand. It does not pretend the
  feature is done.

Nothing here can guarantee App Store approval — see the audit's
"cannot_be_automated" list. This reduces the mechanical failure surface;
the human judgment calls remain yours.

Usage:
    python3 autofix.py /path/to/project                 # apply safe fixes
    python3 autofix.py /path/to/project --dry-run        # show, don't write
    python3 autofix.py /path/to/project --aggressive     # + AI/scaffold tier
    python3 autofix.py /path/to/project --json
"""

import argparse
import json
import plistlib
import re
from pathlib import Path

STANDARD_EULA = "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/"

PERMISSION_DEFAULTS = {
    "NSCameraUsageDescription":
        "This app uses the camera so you can capture photos within the app. "
        "[EDIT: describe your specific feature]",
    "NSLocationWhenInUseUsageDescription":
        "This app uses your location to provide location-based features. "
        "[EDIT: describe your specific feature]",
    "NSLocationAlwaysAndWhenInUseUsageDescription":
        "This app uses your location to provide features even in the "
        "background. [EDIT: describe your specific feature]",
    "NSMicrophoneUsageDescription":
        "This app uses the microphone to record audio within the app. "
        "[EDIT: describe your specific feature]",
    "NSPhotoLibraryUsageDescription":
        "This app accesses your photo library so you can select images. "
        "[EDIT: describe your specific feature]",
    "NSContactsUsageDescription":
        "This app accesses your contacts to help you connect with people. "
        "[EDIT: describe your specific feature]",
    "NSAppleMusicUsageDescription":
        "This app accesses your media library. [EDIT: describe your feature]",
    "NSHealthShareUsageDescription":
        "This app reads health data to show you insights. [EDIT: describe]",
    "NSHealthUpdateUsageDescription":
        "This app saves health data on your behalf. [EDIT: describe]",
    "NSBluetoothAlwaysUsageDescription":
        "This app uses Bluetooth to connect to nearby devices. [EDIT]",
    "NSBluetoothPeripheralUsageDescription":
        "This app uses Bluetooth to connect to nearby devices. [EDIT]",
    "NSCalendarsUsageDescription":
        "This app accesses your calendar to manage events. [EDIT: describe]",
    "NSFaceIDUsageDescription":
        "This app uses Face ID to secure your account. [EDIT: describe]",
}


def apply_permission_strings(missing_permissions, plist_paths, dry_run):
    """missing_permissions: list of {'permission':..,'required_keys':[...]}.
    Adds the first required key for each to every Info.plist that lacks it."""
    actions = []
    if not plist_paths:
        return actions
    # Prefer the main app Info.plist (shortest path depth is a decent proxy;
    # test/extension plists live deeper). Fall back to all.
    target = min(plist_paths, key=lambda p: len(Path(p).parts))
    try:
        with open(target, "rb") as f:
            data = plistlib.load(f)
    except Exception as e:
        return [{"action": "add_permission_strings", "status": "error",
                 "detail": f"could not read {target}: {e}"}]
    changed = False
    for mp in missing_permissions:
        key = mp["required_keys"][0]
        if key not in data or not str(data.get(key, "")).strip():
            default = PERMISSION_DEFAULTS.get(
                key, f"This app requires access for {mp['permission']}. [EDIT]")
            actions.append({
                "action": "add_permission_string",
                "file": target,
                "key": key,
                "value": default,
                "tier": "safe",
                "status": "planned" if dry_run else "applied",
            })
            if not dry_run:
                data[key] = default
                changed = True
    if changed and not dry_run:
        with open(target, "wb") as f:
            plistlib.dump(data, f)
    return actions


def append_eula_to_metadata(root: Path, iap_detected, has_eula_link, dry_run):
    actions = []
    if not iap_detected or has_eula_link:
        return actions
    # Look for a metadata description file (fastlane deliver layout or a
    # plain description.txt); otherwise create one so the line isn't lost.
    candidates = list(root.rglob("description.txt")) + \
        list(root.rglob("metadata/**/description.txt"))
    candidates = [c for c in candidates if ".git" not in c.parts]
    target = candidates[0] if candidates else (root / "AppStore_description.txt")
    line = f"\n\nTerms of Use (EULA): {STANDARD_EULA}\n"
    actions.append({
        "action": "append_standard_eula",
        "file": str(target),
        "appended": line.strip(),
        "tier": "safe",
        "status": "planned" if dry_run else "applied",
        "note": "Standard Apple EULA appended to App Store description "
                "metadata. Also ensure a Terms-of-Use link is reachable from "
                "your in-app subscription screen — metadata alone isn't "
                "enough for 3.1.2.",
    })
    if not dry_run:
        existing = target.read_text() if target.exists() else ""
        target.write_text(existing + line)
    return actions


def flatten_icon_alpha(icon_findings, dry_run):
    actions = []
    try:
        from PIL import Image
    except ImportError:
        for f in icon_findings:
            if any("alpha channel" in i for i in f["issues"]):
                actions.append({
                    "action": "flatten_icon_alpha",
                    "file": f.get("master_icon"),
                    "tier": "safe",
                    "status": "skipped",
                    "detail": "Pillow not installed; cannot flatten. "
                              "pip install Pillow",
                })
        return actions
    from PIL import Image
    for f in icon_findings:
        master = f.get("master_icon")
        if not master:
            continue
        if not any("alpha channel" in i for i in f["issues"]):
            continue
        actions.append({
            "action": "flatten_icon_alpha",
            "file": master,
            "tier": "safe",
            "status": "planned" if dry_run else "applied",
            "note": "Composited onto a solid white background and re-saved "
                    "without alpha. If your icon needs a different background "
                    "color, edit the source and re-export.",
        })
        if not dry_run:
            try:
                im = Image.open(master).convert("RGBA")
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                flat = Image.alpha_composite(bg, im).convert("RGB")
                flat.save(master, "PNG")
            except Exception as e:
                actions[-1]["status"] = "error"
                actions[-1]["detail"] = str(e)
    return actions


def add_marketing_icon_stub(icon_findings, dry_run):
    actions = []
    for f in icon_findings:
        if not any("ios-marketing" in i for i in f["issues"]):
            continue
        iconset = Path(f["path"])
        contents = iconset / "Contents.json"
        if not contents.exists():
            continue
        try:
            data = json.loads(contents.read_text())
        except Exception:
            continue
        data.setdefault("images", []).append({
            "filename": "AppIcon-1024.png",
            "idiom": "ios-marketing",
            "scale": "1x",
            "size": "1024x1024",
        })
        actions.append({
            "action": "add_marketing_icon_entry",
            "file": str(contents),
            "tier": "safe",
            "status": "planned" if dry_run else "applied",
            "note": "Added a 1024x1024 ios-marketing entry pointing at "
                    "AppIcon-1024.png. You must place that 1024x1024 PNG "
                    "(no alpha) into the appiconset.",
        })
        if not dry_run:
            contents.write_text(json.dumps(data, indent=2))
    return actions


def add_export_compliance(export_check, plist_paths, dry_run):
    """ITSAppUsesNonExemptEncryption = false. Setting it is what Apple's own
    'Missing Compliance' dialog asks you for; `false` is right for an app
    that only uses HTTPS/TLS. The note says when it is wrong."""
    actions = []
    if not export_check or export_check["status"] == "PASS" or not plist_paths:
        return actions
    target = min(plist_paths, key=lambda p: len(Path(p).parts))
    actions.append({
        "action": "add_export_compliance_key",
        "file": target,
        "key": "ITSAppUsesNonExemptEncryption",
        "value": False,
        "tier": "safe",
        "status": "planned" if dry_run else "applied",
        "note": "false asserts the app uses only exempt encryption (standard "
                "HTTPS/TLS, OS-provided crypto). If you ship your own "
                "encryption, proprietary algorithms, or a VPN, set this to "
                "true and file the export documentation instead.",
    })
    if not dry_run:
        try:
            with open(target, "rb") as f:
                data = plistlib.load(f)
            data["ITSAppUsesNonExemptEncryption"] = False
            with open(target, "wb") as f:
                plistlib.dump(data, f)
        except Exception as e:  # noqa: BLE001
            actions[-1]["status"] = "error"
            actions[-1]["detail"] = str(e)
    return actions


# The most common approved reason per category. CA92.1 = "app's own
# UserDefaults", C617.1 = "timestamps of the app's own files", 35F9.1 =
# "elapsed time inside the app", E174.1 = "check space before writing",
# 3EC4.1 = "custom keyboard app". Every other code needs a reason the
# developer must be able to defend, so we never guess past the default.
DEFAULT_REASON_CODE = {
    "NSPrivacyAccessedAPICategoryUserDefaults": "CA92.1",
    "NSPrivacyAccessedAPICategoryFileTimestamp": "C617.1",
    "NSPrivacyAccessedAPICategorySystemBootTime": "35F9.1",
    "NSPrivacyAccessedAPICategoryDiskSpace": "E174.1",
    "NSPrivacyAccessedAPICategoryActiveKeyboards": "3EC4.1",
}


def add_required_reason_entries(rra_check, plist_paths, dry_run):
    """ITMS-91053. Adds the missing NSPrivacyAccessedAPITypes entries to the
    existing PrivacyInfo.xcprivacy, or creates one next to the main
    Info.plist when the project has none."""
    actions = []
    if not rra_check or rra_check["status"] != "FAIL":
        return actions
    detail = rra_check.get("detail") or {}
    missing = detail.get("missing") or []
    if not missing:
        return actions
    manifests = detail.get("manifests_found") or []
    if manifests:
        target = Path(min(manifests, key=lambda p: len(Path(p).parts)))
    elif plist_paths:
        main_plist = Path(min(plist_paths, key=lambda p: len(Path(p).parts)))
        target = main_plist.parent / "PrivacyInfo.xcprivacy"
    else:
        return actions
    try:
        if target.exists():
            with open(target, "rb") as f:
                data = plistlib.load(f)
        else:
            data = {"NSPrivacyTracking": False, "NSPrivacyTrackingDomains": [],
                    "NSPrivacyCollectedDataTypes": [],
                    "NSPrivacyAccessedAPITypes": []}
    except Exception as e:  # noqa: BLE001
        return [{"action": "add_required_reason_entries", "status": "error",
                 "tier": "safe", "file": str(target),
                 "detail": f"could not read manifest: {e}"}]
    entries = data.setdefault("NSPrivacyAccessedAPITypes", [])
    for m in missing:
        cat = m["category"]
        code = DEFAULT_REASON_CODE.get(cat, (m.get("approved_reasons") or ["?"])[0])
        actions.append({
            "action": "add_required_reason_entry",
            "file": str(target),
            "key": cat,
            "value": code,
            "tier": "safe",
            "status": "planned" if dry_run else "applied",
            "note": f"Reason {code} is the most common approved code for this "
                    "category. Confirm it describes YOUR use; the approved "
                    f"list is {', '.join(m.get('approved_reasons') or [])}. "
                    "A new manifest must also be added to the app target in "
                    "Xcode (Build Phases → Copy Bundle Resources).",
        })
        if not dry_run:
            entries.append({"NSPrivacyAccessedAPIType": cat,
                            "NSPrivacyAccessedAPITypeReasons": [code]})
    if actions and not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            plistlib.dump(data, f)
    return actions


def annotate_ci_xcode_pin(ci_check, dry_run):
    """Puts a TODO line above a floating Xcode pin. Deliberately does not
    choose a version: the right one is 'whatever meets Apple's minimum
    today', which this tool cannot know when it runs next year."""
    actions = []
    if not ci_check or ci_check["status"] == "PASS":
        return actions
    marker = "# TODO(app-store-audit): pin an explicit Xcode version"
    for hit in ci_check.get("detail") or []:
        f = Path(hit["file"])
        try:
            lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            continue
        idx = hit["line"] - 1
        if idx < 0 or idx >= len(lines) or any(marker in l for l in lines):
            continue
        indent = re.match(r"\s*", lines[idx]).group(0)
        actions.append({
            "action": "annotate_floating_xcode_pin",
            "file": str(f),
            "tier": "safe",
            "status": "planned" if dry_run else "applied",
            "note": "Added a TODO above the floating pin. Replace 'latest' "
                    "with the Xcode version that meets the current SDK "
                    "minimum (https://developer.apple.com/news/upcoming-requirements/).",
        })
        if not dry_run:
            lines.insert(idx, f"{indent}{marker} — Apple's SDK minimum moves "
                              f"every April; 'latest' drifts with the CI image\n")
            f.write_text("".join(lines), encoding="utf-8")
    return actions


# ---- Aggressive tier: scaffolds only, never silent edits ----

AI_CONSENT_SWIFT_SCAFFOLD = '''\
// AUTO-GENERATED SCAFFOLD — third-party AI consent (Guideline 5.1.2(i))
// This is NOT complete. To finish:
//   1. Fill in WHAT is sent and WHO receives it, by legal entity:
//      "the text of your journal entry" → "OpenAI, L.L.C. (GPT-4o)", not
//      "some data" → "our AI partner".
//   2. Show this view BEFORE the first network call to any AI vendor. Gate
//      on `hasConsented` ALONE. Do not add a hasSeen / didShow / firstLaunch
//      flag to the condition — that is the documented repeat-rejection
//      trap: the flag differs on the reviewer's device and the screen
//      never appears.
//   3. Make the privacy policy and the App Privacy labels say the same
//      thing (reviewers compare all three).
import SwiftUI

struct AIConsentGate<Content: View>: View {
    @AppStorage("ai_consent_granted") private var hasConsented = false
    let content: () -> Content
    var body: some View {
        if hasConsented {
            content()
        } else {
            AIConsentView { hasConsented = true }
        }
    }
}

struct AIConsentView: View {
    let onAccept: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Before we begin").font(.title2.bold())
            Text("To generate your guidance, DepthMe sends [EDIT: what data — "
                 + "e.g. your survey answers and journal text] to "
                 + "[EDIT: vendor legal name and product, e.g. OpenAI, L.L.C. "
                 + "(GPT-4o)]. It is used only to produce your content and is "
                 + "not used to train public models.")
            Link("Privacy Policy", destination: URL(string: "[EDIT: https://…/privacy]")!)
            Button("I agree", action: onAccept).buttonStyle(.borderedProminent)
            Button("Not now") { /* TODO: keep the user in a non-AI part of the app */ }
        }
        .padding()
    }
}
'''

AI_CONSENT_REACT_SCAFFOLD = '''\
// AUTO-GENERATED SCAFFOLD — third-party AI consent (Guideline 5.1.2(i))
// React / React Native / Capacitor variant. This is NOT complete. To finish:
//   1. Fill in WHAT is sent and WHO receives it, by legal entity.
//   2. Render <AiConsentGate> around every screen that triggers an AI call,
//      and check `consent` on the server too — the client gate is UX, the
//      server check is the guarantee.
//   3. Gate on the stored consent value ALONE. No hasSeen / didShow /
//      firstLaunch flag in the condition (documented repeat-rejection trap).
//   4. Persist per ACCOUNT, not per device: a reviewer on a fresh install
//      with the demo account must still see it exactly once.
import { useEffect, useState } from 'react';

const KEY = 'ai_consent_granted_at';

export function useAiConsent() {
  const [consent, setConsent] = useState<string | null>(() => {
    try { return localStorage.getItem(KEY); } catch { return null; }
  });
  const grant = () => {
    const now = new Date().toISOString();
    try { localStorage.setItem(KEY, now); } catch { /* storage unavailable */ }
    setConsent(now);
    // TODO: also persist to the user's profile row (ai_consent_at).
  };
  return { consent, grant };
}

export function AiConsentGate({ children }: { children: React.ReactNode }) {
  const { consent, grant } = useAiConsent();
  if (consent) return <>{children}</>;
  return (
    <section>
      <h2>Before we begin</h2>
      <p>
        To generate your guidance, this app sends [EDIT: what data] to
        [EDIT: vendor legal name (product)], and [EDIT: second vendor] for
        [EDIT: purpose]. It is used only to produce your content and is not
        used to train public models. <a href="[EDIT: privacy url]">Privacy Policy</a>
      </p>
      <button onClick={grant}>I agree</button>
      <button>{/* TODO: route to a non-AI part of the app */}Not now</button>
    </section>
  );
}
'''

RESTORE_SWIFT_SCAFFOLD = '''\
// AUTO-GENERATED SCAFFOLD — Restore Purchases on the paywall (Guideline 3.1.2)
// Required even if entitlements auto-sync: the reviewer looks for the control
// on the paywall itself, not in Settings. Place this on the purchase screen.
import StoreKit
import SwiftUI

struct RestorePurchasesButton: View {
    var body: some View {
        Button("Restore Purchases") {
            Task { try? await AppStore.sync() }
        }
    }
}
'''

RESTORE_REACT_SCAFFOLD = '''\
// AUTO-GENERATED SCAFFOLD — Restore Purchases on the paywall (Guideline 3.1.2)
// RevenueCat / react-native-iap variant. Place it ON the paywall screen.
// TODO: replace the restore call with your SDK's:
//   RevenueCat (Capacitor):  Purchases.restorePurchases()
//   RevenueCat (RN):         Purchases.restorePurchases()
//   react-native-iap:        getAvailablePurchases()
export function RestorePurchasesButton({ onRestore }: { onRestore: () => Promise<void> }) {
  return (
    <button type="button" onClick={() => { onRestore().catch(() => {/* surface a toast */}); }}>
      Restore Purchases
    </button>
  );
}
'''

SIWA_SWIFT_SCAFFOLD = '''\
// AUTO-GENERATED SCAFFOLD — Sign in with Apple (Guideline 4.8)
// This is NOT complete. To finish:
//   1. In your Apple Developer account, enable the "Sign In with Apple"
//      capability for this App ID.
//   2. In Xcode: Signing & Capabilities -> + Capability -> Sign In with Apple.
//   3. Handle the ASAuthorizationAppleIDCredential on your server: verify the
//      identity token, create/lookup the user, issue your own session.
//   4. Show this button anywhere you show Google/Facebook/other social login,
//      with equal prominence.
import AuthenticationServices
import SwiftUI

struct AppleSignInButton: View {
    var body: some View {
        SignInWithAppleButton(.signIn) { request in
            request.requestedScopes = [.fullName, .email]
        } onCompletion: { result in
            // TODO: handle result.get() credential; send token to your backend.
        }
        .frame(height: 48)
    }
}
'''

DELETE_ACCOUNT_SCAFFOLD = '''\
// AUTO-GENERATED SCAFFOLD — In-app account deletion (Guideline 5.1.1(v))
// This is NOT complete. To finish:
//   1. Implement deleteAccount() to call your backend's account-deletion
//      endpoint, which must actually delete or irreversibly anonymise the
//      user's data (not just deactivate).
//   2. Surface a clearly labelled "Delete Account" control in Settings.
//   3. Consider protecting your App Review demo account from deletion (see
//      references/accounts-and-sign-in.md) so reviewers don't lock themselves
//      out, while still leaving the flow testable via a fresh account.
func deleteAccount() async throws {
    // TODO: call DELETE /api/account and clear local session on success.
    throw NSError(domain: "NotImplemented", code: -1)
}
'''


def scaffold_aggressive(root: Path, need_siwa, need_delete, dry_run,
                        need_ai_consent=False, need_restore=False):
    actions = []
    scaffold_dir = root / "app_store_audit_scaffolds"

    def emit(action, filename, content, note):
        target = scaffold_dir / filename
        actions.append({
            "action": action, "file": str(target), "tier": "aggressive",
            "status": "planned" if dry_run else "written", "note": note,
        })
        if not dry_run:
            scaffold_dir.mkdir(exist_ok=True)
            target.write_text(content)

    if need_ai_consent:
        emit("scaffold_ai_consent_gate", "AIConsentGate.swift", AI_CONSENT_SWIFT_SCAFFOLD,
             "Scaffold only — fill in what data / which vendor (legal entity); "
             "gate on the consent value alone.")
        emit("scaffold_ai_consent_gate", "AiConsentGate.tsx", AI_CONSENT_REACT_SCAFFOLD,
             "React/Capacitor variant of the same scaffold.")
    if need_restore:
        emit("scaffold_restore_purchases", "RestorePurchasesButton.swift",
             RESTORE_SWIFT_SCAFFOLD, "Scaffold only — place it on the paywall.")
        emit("scaffold_restore_purchases", "RestorePurchasesButton.tsx",
             RESTORE_REACT_SCAFFOLD, "React/RN variant; wire your SDK's restore call.")
    if need_siwa:
        target = scaffold_dir / "AppleSignInButton.swift"
        actions.append({
            "action": "scaffold_sign_in_with_apple",
            "file": str(target),
            "tier": "aggressive",
            "status": "planned" if dry_run else "written",
            "note": "Scaffold only — requires Apple Developer capability + "
                    "backend token verification. Not a working integration.",
        })
        if not dry_run:
            scaffold_dir.mkdir(exist_ok=True)
            target.write_text(SIWA_SWIFT_SCAFFOLD)
    if need_delete:
        target = scaffold_dir / "DeleteAccount.swift"
        actions.append({
            "action": "scaffold_delete_account",
            "file": str(target),
            "tier": "aggressive",
            "status": "planned" if dry_run else "written",
            "note": "Scaffold only — you must implement real server-side "
                    "deletion.",
        })
        if not dry_run:
            scaffold_dir.mkdir(exist_ok=True)
            target.write_text(DELETE_ACCOUNT_SCAFFOLD)
    return actions


def run_autofix(root: Path, audit_report, asset_report,
                aggressive=False, dry_run=False):
    root = Path(root).resolve()
    actions = []
    checks = {c["id"]: c for c in audit_report.get("checks", [])}

    # Safe: permission strings
    perm = checks.get("permission_usage_strings")
    if perm and perm["status"] == "FAIL":
        actions += apply_permission_strings(perm.get("detail", []),
                                            audit_report.get("info_plists_found", []),
                                            dry_run)

    # Safe: EULA metadata line — only the METADATA requirement is
    # autofixable. The in-app link requirement (iap_inapp_policy_eula_links)
    # is deliberately left for the developer; we never fake in-app UI.
    iap_meta = checks.get("iap_metadata_eula_link")
    if iap_meta and iap_meta["status"] == "FAIL":
        actions += append_eula_to_metadata(root, True, False, dry_run)

    # Safe: icon fixes
    icon_findings = asset_report.get("icon_findings", []) if asset_report else []
    actions += flatten_icon_alpha(icon_findings, dry_run)
    actions += add_marketing_icon_stub(icon_findings, dry_run)

    # Safe: upload-time blockers and TestFlight friction
    plists = audit_report.get("info_plists_found", [])
    actions += add_export_compliance(checks.get("export_compliance"), plists, dry_run)
    actions += add_required_reason_entries(checks.get("required_reason_apis"),
                                           plists, dry_run)
    actions += annotate_ci_xcode_pin(checks.get("ci_xcode_pin"), dry_run)

    # Aggressive: scaffolds
    if aggressive:
        siwa = checks.get("sign_in_with_apple")
        deletion = checks.get("account_deletion")
        ai = checks.get("ai_consent_gate")
        paywall = checks.get("paywall_elements")
        need_siwa = bool(siwa and siwa["status"] == "FAIL")
        need_delete = bool(deletion and deletion["status"] == "FAIL")
        need_ai = bool(ai and ai["status"] != "PASS")
        need_restore = bool(
            paywall and paywall["status"] == "FAIL" and
            "restore_purchases" in ((paywall.get("detail") or {}).get("elements_missing") or []))
        actions += scaffold_aggressive(root, need_siwa, need_delete, dry_run,
                                       need_ai_consent=need_ai,
                                       need_restore=need_restore)

    return {
        "project": str(root),
        "dry_run": dry_run,
        "aggressive": aggressive,
        "actions": actions,
        "reminder": "Autofix reduces mechanical failures only. It cannot "
                    "guarantee App Store approval, and every [EDIT] / TODO "
                    "marker it leaves must be completed and reviewed by you "
                    "before submitting.",
    }


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from audit_project import build_report
    from audit_assets import audit_assets

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    parser.add_argument("--aggressive", action="store_true",
                        help="Also emit Sign in with Apple / account deletion "
                             "scaffolds (never silent edits)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_path).resolve()
    if not root.exists():
        print(f"Error: path not found: {root}")
        sys.exit(1)

    audit_report = build_report(root)
    asset_report = audit_assets(root)
    result = run_autofix(root, audit_report, asset_report,
                         aggressive=args.aggressive, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        mode = "DRY RUN — no files written" if args.dry_run else "APPLIED"
        print(f"# Autofix ({mode})  aggressive={args.aggressive}\n")
        if not result["actions"]:
            print("No auto-fixable issues found.")
        for a in result["actions"]:
            print(f"[{a['tier']}] {a['action']} — {a['status']}")
            print(f"    file: {a.get('file')}")
            if a.get("key"):
                print(f"    key:  {a['key']} = {a['value']!r}")
            if a.get("note"):
                print(f"    note: {a['note']}")
            if a.get("detail"):
                print(f"    detail: {a['detail']}")
            print()
        print(result["reminder"])


if __name__ == "__main__":
    main()
