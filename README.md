# App Store Rejection Audit

![guidelines verified](https://img.shields.io/badge/guidelines%20verified-September%202026-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-iOS%20%7C%20hybrid-lightgrey)

A pre-submission audit for the Apple App Store Review Guidelines that account for the large majority of first-submission rejections — crashes/placeholder content (2.1), metadata and other-platform mentions (2.3), in-app purchases, subscriptions and the seven paywall elements (3.1.1/3.1.2), minimum functionality for webview/PWA-style apps (4.2), spam/templated apps (4.3), Sign in with Apple (4.8), privacy/permissions/account deletion (5.1.1), **third-party AI consent (5.1.2(i), November 2025)** — and the **upload-time ITMS blockers** (required-reason APIs, SDK manifests, export compliance, SDK minimum) that stop a build before any reviewer sees it.

Built for the apps other tools skip: React Native, Flutter and Capacitor projects where the AI vendor call lives in an edge function, the strings ship to three platforms from one table, and the iOS tree is mostly generated.

It ships four things:

1. **A source static-analysis script** (`scripts/audit_project.py`) that scans a project — native iOS, React Native, Flutter, or Capacitor — for the issues detectable from source, gives every finding a **severity** (`HARD BLOCK` / `LIKELY REJECTION` / `RISK FLAG`) beside its status, and with `--report` writes an `APP_STORE_APPROVAL.md` with Evidence / Why / Fix / Source per finding, the App Store Connect artifacts it cannot see, and the manual checklist. It looks in backend trees for AI vendors, skips build output copied into `ios/` and `android/`, and only counts copy a user can read.
2. **An asset/branding auditor** (`scripts/audit_assets.py`) that checks the *technical* compliance of your icons and launch screen: 1024×1024 dimensions, alpha-channel presence (a top automated-rejection cause), hand-applied rounded corners, placeholder-looking flat icons, and asset-catalog integrity. Uses Pillow for pixel checks if installed; degrades gracefully without it.
3. **An autofixer** (`scripts/autofix.py`) with two tiers: **safe** mechanical fixes applied by default (permission strings, icon alpha flattening, standard EULA metadata line, export-compliance key, missing `PrivacyInfo.xcprivacy` required-reason entries, a TODO above a floating CI Xcode pin), and **aggressive** scaffolds behind `--aggressive` (Sign in with Apple, account deletion, an AI consent gate that gates on the consent value alone, a Restore Purchases control) that are always clearly-marked TODO stubs — never silent edits to working auth/purchase code. `--dry-run` previews everything without writing.
4. **A [Claude Skill](https://docs.claude.com)** (`SKILL.md` + `references/`) that packages the knowledge — including everything the scripts *can't* check, like real-device crash testing, App Store Connect metadata, and the App Privacy questionnaire — and knows when to reach for the [`appstore-rejections-mcp`](https://github.com/robertojoseph/appstore-rejections-mcp) case database once a rejection notice exists.

Knowledge on 5.1.2(i), the ITMS errors, the paywall elements, the severity model and the report format is adapted from [artbyjazi/app-store-approval](https://github.com/artbyjazi/app-store-approval) (MIT), whose bash scans target native Xcode projects; this project carries the same rules into Python and hybrid stacks, with an autofixer and a backtest suite neither upstream has.

**This is risk reduction, not a guarantee — and the project is deliberately honest about that.** Apple's review is a human judgment call against changing guidelines plus subjective criteria. A clean report doesn't mean your app will be approved, autofix deliberately leaves some things failing rather than fake them, and the test suite backtests *the tool*, not Apple. No static tool can promise a first-pass approval, and this one doesn't pretend to.

## Using the scripts standalone

Core scanning needs only Python 3.8+. Pixel-level icon checks and icon alpha-flattening additionally use [Pillow](https://pypi.org/project/Pillow/) (`pip install Pillow`) — everything degrades gracefully without it and tells you what it skipped.

```bash
# source audit
python3 scripts/audit_project.py /path/to/your/project
python3 scripts/audit_project.py /path/to/your/project --report APP_STORE_APPROVAL.md
python3 scripts/audit_project.py /path/to/your/project --json --output report.json
python3 scripts/audit_project.py /path/to/your/project --check-urls   # HEAD-requests support/privacy/terms URLs

# asset / branding audit
python3 scripts/audit_assets.py /path/to/your/project

# autofix — preview, then apply
python3 scripts/autofix.py /path/to/your/project --dry-run
python3 scripts/autofix.py /path/to/your/project
python3 scripts/autofix.py /path/to/your/project --aggressive   # + scaffolds

# backtest the tool's own reliability
python3 tests/run_tests.py
```

`audit_project.py`'s exit code is `1` if any check fails, `0` otherwise — usable as a pre-submission CI gate. Non-blocking is recommended given the heuristic nature of the checks; treat a non-zero exit as "review before you submit," not "build failed."

### What "backtesting" means here

`tests/run_tests.py` builds synthetic known-bad and known-good fixture projects and asserts that: the auditor flags the bad ones on every check it claims to cover, passes the good one with no false positives, and — after running the safe autofixer on a fixable project — the project re-audits clean on the mechanically-fixable checks while the non-autofixable ones (in-app subscription links, Sign in with Apple, account deletion) are *honestly left failing rather than faked*. **This validates the tool, not App Store approval.** A green suite means the tooling behaves as specified; it makes no claim about whether Apple will approve any given submission.

## Using it as a Claude Skill

Drop this folder into `~/.claude/skills/` (Claude Code) or upload it as a skill in claude.ai / Claude Cowork. Once installed, Claude will consult it automatically when you're working on an iOS submission, mention App Store rejection, App Review, demo credentials, IAP/subscriptions, or similar — no need to invoke it by name.

## What it checks

| Area | Guideline | Check id | Severity | Reference doc |
|---|---|---|---|---|
| Placeholder content in shipped screens | 2.1 | `placeholder_content` | LIKELY REJECTION | `app-completeness-and-design.md` |
| Other platforms / payment processors named on iOS | 2.3.10 / 3.1.3 | `cross_platform_mentions` | RISK FLAG | `app-completeness-and-design.md` |
| Webview/PWA wrapper risk | 4.2 | `webview_ratio` | RISK FLAG | `app-completeness-and-design.md` |
| Templated/duplicate apps, copycat branding | 4.3, 4.1(c) | — | — | `app-completeness-and-design.md` |
| Sign in with Apple | 4.8 | `sign_in_with_apple` | LIKELY REJECTION | `accounts-and-sign-in.md` |
| Account deletion | 5.1.1(v) | `account_deletion` | HARD BLOCK | `accounts-and-sign-in.md` |
| Permission purpose strings | 5.1.1 / ITMS-90683 | `permission_usage_strings` | HARD BLOCK | `privacy-and-permissions.md` |
| Third-party AI consent (client + backend scan, vendor naming, hasSeen trap) | 5.1.2(i) | `ai_consent_gate` | LIKELY REJECTION | `third-party-ai-consent.md` |
| Required-reason APIs vs `PrivacyInfo.xcprivacy` | ITMS-91053 | `required_reason_apis` | HARD BLOCK | `privacy-manifest-and-itms.md` |
| SDKs on Apple's manifest list | ITMS-91061 | `sdk_manifests` | RISK FLAG | `privacy-manifest-and-itms.md` |
| In-app Privacy Policy + Terms links on the paywall | 3.1.2 | `iap_inapp_policy_eula_links` | LIKELY REJECTION | `payments-and-subscriptions.md` |
| Terms link in App Store metadata | 3.1.2 | `iap_metadata_eula_link` | LIKELY REJECTION | `payments-and-subscriptions.md` |
| Seven paywall elements (Restore, duration, auto-renew…) | 3.1.2 | `paywall_elements` | LIKELY REJECTION | `payments-and-subscriptions.md` |
| Literal price strings on native | 3.1.2 | `hardcoded_prices` | LIKELY REJECTION | `payments-and-subscriptions.md` |
| Floating CI Xcode pin vs the SDK minimum | ITMS-90725 | `ci_xcode_pin` | RISK FLAG | `deadlines.md` |
| Version keys, export compliance | Upload | `version_keys`, `export_compliance` | RISK FLAG | `privacy-manifest-and-itms.md` |
| One App Store id across Rate/Share and CI | 2.1 | `app_store_id_consistency` | RISK FLAG | `submission-artifacts.md` |
| Support / privacy / terms URLs live (`--check-urls`) | 1.5, 5.1.1(i) | `support_privacy_urls` | LIKELY REJECTION | `submission-artifacts.md` |
| HealthKit transparency | 2.5.1 / 5.1.3 | `healthkit_transparency` | LIKELY REJECTION | `privacy-and-permissions.md` |
| Icon, launch screen, asset catalog | ITMS-90022 | `audit_assets.py` | HARD BLOCK | `assets-and-branding.md` |
| Demo credentials, review notes, App Privacy labels, age rating, agreements | process | — | — | `submission-artifacts.md`, `metadata-review.md` |
| Working a rejection notice, real cases | — | — | — | `metadata-review.md`, `rejection-lookup.md` |

Full checklist with all 28 items lives in `SKILL.md`.

## Why this exists

Apple's own [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) are the source of truth and change over time — this project is a practical, opinionated summary of the guidelines that most often trip up first-time and indie submissions, built from Apple's published guidelines plus patterns reported across developer forums and rejection-reason writeups. It is **not official**, **not affiliated with Apple**, and won't always be perfectly current — guideline numbers and requirements do shift. Always cross-check anything load-bearing against the current official guidelines before you rely on it.

## Limitations

- The script is regex/heuristic-based static analysis, not a real Xcode/App Store Connect integration. It will miss things and occasionally flag non-issues (e.g. a `WKWebView` used for a legitimate in-app browser, not the whole app).
- It doesn't test on-device, doesn't touch App Store Connect, and can't judge visual/design compliance.
- Coverage for native Android-only files, watchOS, or macOS Catalyst specifics is out of scope — this is iOS/iPadOS-focused.

## Contributing

Issues and PRs welcome — especially additional permission-API patterns, additional social-login SDK patterns, and corrections to guideline numbers/requirements as Apple updates them. See `CONTRIBUTING.md`.

## License

MIT — see `LICENSE`.
