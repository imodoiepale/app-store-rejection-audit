#!/usr/bin/env python3
"""
Regression / backtest suite for the App Store Rejection Audit tools.

IMPORTANT framing: this backtests *the tool's own reliability*, not App
Store approval. It proves that:
  (a) the auditor FLAGS known-bad fixtures on the checks it claims to cover,
  (b) the auditor PASSES a known-good fixture (no false positives on it),
  (c) the safe autofixer, applied to a fixable fixture, produces a project
      that then RE-AUDITS CLEAN on the mechanically-fixable checks.

It does NOT and cannot assert "this app will be approved by Apple." No
static tool can. Treat a green suite as "the auditor behaves as specified,"
not "your submission is guaranteed."

Run:
    python3 tests/run_tests.py
Exit code 0 = all assertions passed.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_project import build_report          # noqa: E402
from audit_assets import audit_assets           # noqa: E402
from autofix import run_autofix                  # noqa: E402


# ---------- fixture builders ----------

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def build_bad_fixture(root: Path):
    """A project that violates multiple checks: placeholder text, a
    permission API with no plist string, social login w/o Apple, signup
    w/o deletion, IAP w/o policy links."""
    write(root / "ios" / "App" / "Info.plist", (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '</dict></plist>\n'))
    write(root / "src" / "Home.swift", (
        'import AVFoundation\n'
        'let s = "Coming soon: dashboard"\n'
        'AVCaptureDevice.default(for: .video)\n'))
    write(root / "src" / "Auth.swift", (
        'import GoogleSignIn\n'
        'func go() { GIDSignIn.sharedInstance.signIn() }\n'
        'func createAccount() {}\n'))
    write(root / "src" / "Billing.swift", (
        'import StoreKit\n'
        'let p: SKProduct? = nil\n'))


def build_good_fixture(root: Path):
    """A project that should pass the source-level checks."""
    write(root / "ios" / "App" / "Info.plist", (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>NSCameraUsageDescription</key>\n'
        '  <string>Used to scan receipts for your expense log.</string>\n'
        '</dict></plist>\n'))
    write(root / "src" / "Home.swift", (
        'import AVFoundation\n'
        'AVCaptureDevice.default(for: .video)\n'
        'let title = "Your dashboard"\n'))
    write(root / "src" / "Auth.swift", (
        'import GoogleSignIn\n'
        'import AuthenticationServices\n'
        'func go() { GIDSignIn.sharedInstance.signIn() }\n'
        'func apple() { let _ = ASAuthorizationAppleIDProvider() }\n'
        'func createAccount() {}\n'
        'func deleteAccount() { /* DELETE /api/account */ }\n'))
    write(root / "src" / "Billing.swift", (
        'import StoreKit\n'
        'let policy = "https://x.example/privacy Privacy Policy"\n'
        'let eula = "https://x.example/terms Terms of Use"\n'))
    write(root / "fastlane" / "metadata" / "en-US" / "description.txt", (
        "A great expense tracker.\n\n"
        "Terms of Use (EULA): "
        "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/\n"))


def build_fixable_fixture(root: Path):
    """Same as bad, but limited to the mechanically-fixable checks so we can
    assert autofix -> re-audit clean on those. Keeps social-login/deletion
    OUT (those aren't safe-autofixable), so a clean re-audit is achievable
    with safe fixes alone."""
    write(root / "ios" / "App" / "Info.plist", (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '</dict></plist>\n'))
    write(root / "src" / "Home.swift", (
        'import AVFoundation\n'
        'AVCaptureDevice.default(for: .video)\n'))
    write(root / "src" / "Billing.swift", (
        'import StoreKit\n'
        'let p: SKProduct? = nil\n'))
    # No social login, no signup -> those checks pass; leaves only
    # permission string + IAP policy links as failures to be fixed.


def build_ai_consent_bad_fixture(root: Path):
    """Hybrid (Capacitor-style) app: the vendor call lives in a Supabase
    edge function, the client never names the vendor. Must FAIL."""
    write(root / "ios" / "App" / "App" / "Info.plist", (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>ITSAppUsesNonExemptEncryption</key><false/>\n'
        '</dict></plist>\n'))
    write(root / "supabase" / "functions" / "generate" / "index.ts", (
        'const r = await fetch("https://api.openai.com/v1/chat/completions", '
        '{ method: "POST" });\n'))
    write(root / "src" / "screens" / "Onboarding.tsx", (
        'export default function Onboarding() {\n'
        '  // OpenAI is used here but the user is never told\n'
        '  return <p>{"Welcome to your daily practice"}</p>;\n'
        '}\n'))
    # A log line that names the vendor must NOT count as consent evidence
    write(root / "src" / "lib" / "ai.ts", (
        'console.warn("[ai] OpenAI key missing, allow fallback");\n'))


def build_ai_consent_trap_fixture(root: Path):
    """Consent screen exists and names the vendor, but the gate is also
    conditioned on a hasSeen flag. Must WARN (the repeat-rejection trap)."""
    build_ai_consent_bad_fixture(root)
    write(root / "src" / "screens" / "AiConsent.tsx", (
        'export function AiConsent({ hasSeenConsent, hasConsented }) {\n'
        '  if (!hasSeenConsent && !hasConsented) { return <Gate />; }\n'
        '  return <p>{"Your journal text is sent to OpenAI, L.L.C. (GPT-4o). '
        'Tap I agree to give permission."}</p>;\n'
        '}\n'))


def build_ai_consent_good_fixture(root: Path):
    build_ai_consent_bad_fixture(root)
    write(root / "src" / "i18n" / "en" / "consent.json", (
        '{\n'
        '  "title": "Before we begin",\n'
        '  "body": "Your survey answers are sent to OpenAI, L.L.C. (GPT-4o) '
        'to generate guidance. Tap I agree to consent.",\n'
        '  "cta": "I agree"\n'
        '}\n'))
    write(root / "src" / "screens" / "AiConsent.tsx", (
        'export function AiConsent({ hasConsented }) {\n'
        '  if (!hasConsented) { return <Gate />; }\n'
        '  return <Root />;\n'
        '}\n'))


def build_manifest_bad_fixture(root: Path):
    """Native code uses UserDefaults + disk space; manifest declares only
    UserDefaults. Must FAIL on required_reason_apis, and be safe-fixable."""
    write(root / "ios" / "App" / "Info.plist", (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '</dict></plist>\n'))
    write(root / "ios" / "App" / "PrivacyInfo.xcprivacy", (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>NSPrivacyAccessedAPITypes</key><array><dict>\n'
        '    <key>NSPrivacyAccessedAPIType</key>'
        '<string>NSPrivacyAccessedAPICategoryUserDefaults</string>\n'
        '    <key>NSPrivacyAccessedAPITypeReasons</key><array><string>CA92.1</string></array>\n'
        '  </dict></array>\n'
        '</dict></plist>\n'))
    write(root / "ios" / "App" / "Cache.swift", (
        'let d = UserDefaults.standard\n'
        'let free = try? URL(fileURLWithPath: "/").resourceValues('
        'forKeys: [.volumeAvailableCapacityKey])\n'))
    write(root / "codemagic.yaml", (
        'workflows:\n  ios:\n    environment:\n      xcode: latest\n'))


def build_paywall_bad_fixture(root: Path):
    """RevenueCat present; paywall has price + terms + privacy but no
    Restore control, a hardcoded '$9.99', and an ungated 'Google Play'."""
    write(root / "src" / "screens" / "PaywallScreen.tsx", (
        'import Purchases from "@revenuecat/purchases-capacitor";\n'
        'export function PaywallScreen() {\n'
        '  return (<div>\n'
        '    <h1>{"DepthMe Premium — $9.99 / month, auto-renews, cancel anytime"}</h1>\n'
        '    <a href="https://x.example/privacy">{"Privacy Policy"}</a>\n'
        '    <a href="https://x.example/terms">{"Terms of Use"}</a>\n'
        '    <p>{"Manage your subscription in Google Play or the App Store"}</p>\n'
        '  </div>);\n'
        '}\n'))
    write(root / "src" / "lib" / "platform.ts", (
        "export const isAndroid = () => Capacitor.getPlatform() === 'android';\n"))
    write(root / "src" / "screens" / "RateApp.tsx", (
        'const a = "https://apps.apple.com/app/x/id1234567890";\n'
        'const b = "itms-apps://itunes.apple.com/app/id9876543210";\n'))
    write(root / "fastlane" / "metadata" / "en-US" / "description.txt", (
        "Terms of Use (EULA): https://www.apple.com/legal/internet-services/itunes/dev/stdeula/\n"))


# ---------- assertions ----------

def status_of(report, check_id):
    for c in report["checks"]:
        if c["id"] == check_id:
            return c["status"]
    return None


PASSED = []
FAILED = []


def check(name, condition):
    (PASSED if condition else FAILED).append(name)
    mark = "ok  " if condition else "FAIL"
    print(f"  [{mark}] {name}")


def test_bad_fixture_is_flagged():
    print("test: bad fixture is flagged on every claimed check")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_bad_fixture(root)
        r = build_report(root)
        check("placeholder_content FAIL", status_of(r, "placeholder_content") == "FAIL")
        check("permission_usage_strings FAIL",
              status_of(r, "permission_usage_strings") == "FAIL")
        check("sign_in_with_apple FAIL",
              status_of(r, "sign_in_with_apple") == "FAIL")
        check("account_deletion FAIL",
              status_of(r, "account_deletion") == "FAIL")
        check("iap_inapp_policy_eula_links FAIL",
              status_of(r, "iap_inapp_policy_eula_links") == "FAIL")
        check("iap_metadata_eula_link FAIL",
              status_of(r, "iap_metadata_eula_link") == "FAIL")


def test_good_fixture_passes():
    print("test: good fixture passes the source-level checks (no false positives)")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_good_fixture(root)
        r = build_report(root)
        for cid in ["placeholder_content", "permission_usage_strings",
                    "sign_in_with_apple", "account_deletion",
                    "iap_inapp_policy_eula_links", "iap_metadata_eula_link"]:
            check(f"{cid} PASS", status_of(r, cid) == "PASS")


def test_autofix_then_reaudit_clean():
    print("test: safe autofix on fixable fixture -> re-audits clean on "
          "mechanical checks")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_fixable_fixture(root)
        before = build_report(root)
        check("before: permission FAIL",
              status_of(before, "permission_usage_strings") == "FAIL")
        check("before: iap metadata FAIL",
              status_of(before, "iap_metadata_eula_link") == "FAIL")

        assets = audit_assets(root)
        run_autofix(root, before, assets, aggressive=False, dry_run=False)

        after = build_report(root)
        # Safe autofix DOES clear the mechanical checks:
        check("after: permission PASS",
              status_of(after, "permission_usage_strings") == "PASS")
        check("after: iap metadata PASS (EULA appended)",
              status_of(after, "iap_metadata_eula_link") == "PASS")
        # And it HONESTLY leaves the in-app UI requirement failing rather than
        # faking it — this staying FAIL is correct behaviour, not a bug:
        check("after: in-app iap links still FAIL (not faked)",
              status_of(after, "iap_inapp_policy_eula_links") == "FAIL")


def test_dry_run_writes_nothing():
    print("test: --dry-run writes nothing to disk")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_fixable_fixture(root)
        before_files = {str(p): p.stat().st_mtime
                        for p in root.rglob("*") if p.is_file()}
        rep = build_report(root)
        assets = audit_assets(root)
        result = run_autofix(root, rep, assets, aggressive=False, dry_run=True)
        after_files = {str(p): p.stat().st_mtime
                       for p in root.rglob("*") if p.is_file()}
        check("no files added", set(before_files) == set(after_files))
        check("no files modified",
              all(before_files[k] == after_files.get(k) for k in before_files))
        check("actions were still planned", len(result["actions"]) > 0)


def test_aggressive_only_scaffolds():
    print("test: --aggressive emits scaffolds, not silent auth edits")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_bad_fixture(root)
        rep = build_report(root)
        assets = audit_assets(root)
        result = run_autofix(root, rep, assets, aggressive=True, dry_run=False)
        agg = [a for a in result["actions"] if a["tier"] == "aggressive"]
        check("aggressive actions exist", len(agg) > 0)
        check("all aggressive actions are scaffolds",
              all(a["action"].startswith("scaffold_") for a in agg))
        # crucial: the original Auth.swift must be byte-for-byte untouched
        auth = (root / "src" / "Auth.swift").read_text()
        check("original auth code untouched",
              "GIDSignIn.sharedInstance.signIn()" in auth
              and "ASAuthorization" not in auth)


def detail_of(report, check_id):
    for c in report["checks"]:
        if c["id"] == check_id:
            return c.get("detail") or {}
    return {}


def test_ai_consent_gate():
    print("test: 5.1.2(i) — backend vendor call is found; consent must be in "
          "shipped copy; the hasSeen trap is a WARN")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_ai_consent_bad_fixture(root)
        r = build_report(root)
        check("vendor found in supabase/functions (not just the client)",
              "OpenAI" in detail_of(r, "ai_consent_gate").get("vendors_detected", []))
        check("no consent copy -> FAIL", status_of(r, "ai_consent_gate") == "FAIL")
        check("log line naming the vendor is not consent evidence",
              detail_of(r, "ai_consent_gate").get("consent_evidence") == [])
        check("severity is LIKELY REJECTION",
              next(c for c in r["checks"] if c["id"] == "ai_consent_gate")["severity"]
              == "LIKELY REJECTION")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_ai_consent_trap_fixture(root)
        r = build_report(root)
        check("consent + hasSeen flag -> WARN (repeat-rejection trap)",
              status_of(r, "ai_consent_gate") == "WARN")
        check("trap line is reported",
              len(detail_of(r, "ai_consent_gate").get("seen_flag_trap", [])) == 1)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_ai_consent_good_fixture(root)
        r = build_report(root)
        check("vendor named in i18n next to consent, gate on value alone -> PASS",
              status_of(r, "ai_consent_gate") == "PASS")


def test_required_reason_apis_and_safe_autofix():
    print("test: ITMS-91053 — missing manifest category FAILs, safe autofix "
          "adds it, CI floating pin is annotated not rewritten")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_manifest_bad_fixture(root)
        before = build_report(root)
        check("DiskSpace used but undeclared -> FAIL",
              status_of(before, "required_reason_apis") == "FAIL")
        missing = [m["category"] for m in detail_of(before, "required_reason_apis")["missing"]]
        check("exactly the DiskSpace category is missing",
              missing == ["NSPrivacyAccessedAPICategoryDiskSpace"])
        check("xcode: latest -> ci_xcode_pin WARN",
              status_of(before, "ci_xcode_pin") == "WARN")
        check("no ITSAppUsesNonExemptEncryption -> export_compliance WARN",
              status_of(before, "export_compliance") == "WARN")
        check("severity HARD BLOCK on required_reason_apis",
              next(c for c in before["checks"] if c["id"] == "required_reason_apis")["severity"]
              == "HARD BLOCK")

        run_autofix(root, before, audit_assets(root), aggressive=False, dry_run=False)
        after = build_report(root)
        check("after: required_reason_apis PASS",
              status_of(after, "required_reason_apis") == "PASS")
        check("after: export_compliance PASS",
              status_of(after, "export_compliance") == "PASS")
        cm = (root / "codemagic.yaml").read_text()
        check("after: CI pin annotated with a TODO, not rewritten",
              "TODO(app-store-audit)" in cm and "xcode: latest" in cm)
        check("after: ci_xcode_pin still WARN (honestly not faked)",
              status_of(after, "ci_xcode_pin") == "WARN")


def test_paywall_prices_crossplatform_ids():
    print("test: 3.1.2 seven elements, hardcoded price, 2.3.10 mentions, "
          "App Store id consistency, --report writer")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_paywall_bad_fixture(root)
        r = build_report(root)
        check("paywall lacks restore -> FAIL",
              status_of(r, "paywall_elements") == "FAIL")
        check("restore_purchases is the missing element",
              detail_of(r, "paywall_elements").get("elements_missing") == ["restore_purchases"])
        check("$9.99 literal -> hardcoded_prices WARN",
              status_of(r, "hardcoded_prices") == "WARN")
        xp = detail_of(r, "cross_platform_mentions")
        check("'Google Play' in copy is reported",
              any(h["term"] == "Google Play" for h in xp))
        check("'android' enum value in platform.ts is NOT reported",
              not any("platform.ts" in h["file"] for h in xp))
        check("two App Store ids -> FAIL",
              status_of(r, "app_store_id_consistency") == "FAIL")
        check("metadata EULA link found in fastlane description",
              status_of(r, "iap_metadata_eula_link") == "PASS")

        from audit_project import render_report
        md = render_report(r, app_name="Fixture")
        check("report has all three severity sections",
              all(f"## {s}" in md for s in ("HARD BLOCK", "LIKELY REJECTION", "RISK FLAG")))
        check("empty section says 'None found.'", "None found." in md)
        check("report carries Why/Fix/Source for a finding",
              "**Why:**" in md and "**Fix:**" in md and "**Source:**" in md)
        check("report ends with the manual checklist", "## Manual review checklist" in md)

        # Aggressive tier writes the AI-consent and Restore scaffolds
        res = run_autofix(root, r, audit_assets(root), aggressive=True, dry_run=False)
        names = {a["action"] for a in res["actions"] if a["tier"] == "aggressive"}
        check("restore scaffold emitted", "scaffold_restore_purchases" in names)
        paywall_src = (root / "src" / "screens" / "PaywallScreen.tsx").read_text()
        check("paywall source untouched by aggressive tier",
              "Restore" not in paywall_src)


def test_good_fixture_no_new_false_positives():
    print("test: the original good fixture is still clean on the new checks")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build_good_fixture(root)
        r = build_report(root)
        for cid in ["ai_consent_gate", "hardcoded_prices", "cross_platform_mentions",
                    "ci_xcode_pin"]:
            check(f"{cid} PASS", status_of(r, cid) == "PASS")
        check("no HARD BLOCK counted", r["counts"]["HARD BLOCK"] == 0)


def main():
    for t in [test_bad_fixture_is_flagged, test_good_fixture_passes,
              test_autofix_then_reaudit_clean, test_dry_run_writes_nothing,
              test_aggressive_only_scaffolds, test_ai_consent_gate,
              test_required_reason_apis_and_safe_autofix,
              test_paywall_prices_crossplatform_ids,
              test_good_fixture_no_new_false_positives]:
        t()
        print()
    total = len(PASSED) + len(FAILED)
    print(f"{len(PASSED)}/{total} assertions passed.")
    if FAILED:
        print("FAILED:")
        for f in FAILED:
            print(f"  - {f}")
        sys.exit(1)
    print("\nAll assertions passed. NOTE: this verifies the auditor/autofixer "
          "behave as specified — it does NOT guarantee App Store approval.")


if __name__ == "__main__":
    main()
