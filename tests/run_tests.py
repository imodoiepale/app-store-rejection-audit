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


def main():
    for t in [test_bad_fixture_is_flagged, test_good_fixture_passes,
              test_autofix_then_reaudit_clean, test_dry_run_writes_nothing,
              test_aggressive_only_scaffolds]:
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
