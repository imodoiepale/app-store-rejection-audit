---
name: app-store-rejection-audit
description: Audit an iOS or cross-platform (React Native / Flutter / Capacitor / PWA-wrapped) app for Apple App Store rejection risks before submission, and work a rejection notice after one. Use this whenever the user mentions App Store submission, App Review, TestFlight, a rejection or Resolution Center message, ITMS upload errors, privacy manifests or PrivacyInfo.xcprivacy, demo/reviewer credentials, Apple in-app purchases or auto-renewable subscriptions, paywall compliance, Sign in with Apple, account deletion, third-party AI consent, App Store Connect metadata or screenshots, or asks "why was my app rejected", "is my app ready to submit", "will this pass review". Trigger proactively for React Native, Flutter, Capacitor or PWA-wrapped apps heading to iOS: the webview (4.2) and hybrid-app AI-consent (5.1.2(i)) findings hit those stacks hardest.
---

# App Store Rejection Audit

A pre-submission audit covering the guideline categories behind most first-submission rejections — 2.1 completeness, 2.3 metadata, 3.1.1/3.1.2 purchases and the seven paywall elements, 4.2 minimum functionality, 4.3 spam, 4.8 Sign in with Apple, 5.1.1 privacy and account deletion, 5.1.2(i) third-party AI consent — plus the submission-time ITMS hard blocks that stop an upload before any reviewer sees it.

This is risk reduction, not a guarantee. Apple's review is a human judgment call against changing guidelines. A clean audit lowers the odds of a rejection; it does not eliminate them. Never tell the user their app "will pass".

## Severity model

Every finding carries exactly one level. Getting the level right matters more than finding more items: a wall of maybes is useless to someone shipping tomorrow.

| Level | Meaning |
|---|---|
| **HARD BLOCK** | Deterministic. App Store Connect refuses the upload, or review fails on a fact verifiable from the code (missing purpose string, undeclared required-reason API, account creation without deletion). |
| **LIKELY REJECTION** | Matches a documented rejection cause. A reviewer following the guideline as written would reject it. |
| **RISK FLAG** | Needs a human or App Store Connect: purpose-string quality, ongoing value, minimum functionality, metadata accuracy, prominence. |

When unsure between two levels, choose the lower and say what would settle it. Reviewer inconsistency is real: identical builds pass and then fail. These are risk scores.

## Workflow

### 1. Read `references/deadlines.md` first

It is short and it gates everything else. If today is past its re-verify date, say so before quoting any dated fact and fetch <https://developer.apple.com/news/upcoming-requirements/>. A build against a stale SDK is a hard block that makes every other finding irrelevant.

### 2. Run the scans

```bash
python3 scripts/audit_project.py /path/to/project --report APP_STORE_APPROVAL.md
python3 scripts/audit_assets.py  /path/to/project
```

`audit_project.py` prints a PASS/WARN/FAIL table with a severity per check and, with `--report`, writes the findings grouped by severity with Evidence / Why / Fix / Source, the App Store Connect artifacts it cannot see, and the manual checklist. Add `--check-urls` to HEAD-request the support/privacy/terms URLs it finds (network; off by default). `--json` for machine output; exit code 1 when any check FAILs.

For hybrid apps it scans the backend tree too (`supabase/functions`, `functions/`, `api/`, `server/`…), because the AI vendor call is never in the app bundle. It skips build output copied into `ios/` and `android/`, hidden directories, lock files and minified bundles.

`audit_assets.py` checks the icon (1024×1024, no alpha, no hand-rounded corners), the asset catalog and the launch screen. Pillow enables pixel checks; without it the script says what it skipped.

### 3. Read only the references the scans point at

| Flag / topic | Reference |
|---|---|
| Third-party AI: consent screen, vendor naming, the hasSeen trap, hybrid-app detection | `references/third-party-ai-consent.md` |
| ITMS-91053/91055/91061/90683/90022, PrivacyInfo.xcprivacy, reason codes, SDK list, export compliance | `references/privacy-manifest-and-itms.md` |
| Purpose strings, App Privacy labels, SDK manifests | `references/privacy-and-permissions.md` |
| Seven paywall elements, hardcoded prices, Restore, the post-*Epic* regional split, 3.1.3 categories | `references/payments-and-subscriptions.md` |
| Demo credentials, 2FA, reviewer deleting the demo account, Sign in with Apple, account deletion | `references/accounts-and-sign-in.md` |
| Placeholder content, 2.3.1 untrue claims, 2.3.10 other platforms, 4.1(c), 4.2 webviews, 4.3, 4.7 | `references/app-completeness-and-design.md` |
| Icon, launch screen, asset catalog | `references/assets-and-branding.md` |
| Everything in App Store Connect: URLs, EULA in the Description, labels, age rating, agreements | `references/submission-artifacts.md` |
| Review-notes template, Resolution Center reply, appeals, "the user pasted a rejection" | `references/metadata-review.md` |
| Real cases and solutions via the `appstore-rejections-mcp` server | `references/rejection-lookup.md` |
| Dated requirements and the staleness rule | `references/deadlines.md` |

### 4. Cross-check every finding against the code

A FAIL means "go look at this", not "this is definitely broken". Open the file the evidence names. A `WKWebView` used as an in-app browser is not a 4.2 problem; a `$9.99` in a web-only fallback constant is not a 3.1.2 problem if native renders the store price. Drop findings you cannot confirm and say why.

### 5. Autofix the mechanical issues, preview first

```bash
python3 scripts/autofix.py /path/to/project --dry-run
python3 scripts/autofix.py /path/to/project              # safe tier
python3 scripts/autofix.py /path/to/project --aggressive # + scaffolds
```

**Safe tier:** missing purpose strings (with `[EDIT]` defaults), the standard EULA line in metadata, icon alpha flattening, the 1024 marketing-icon entry, `ITSAppUsesNonExemptEncryption = false`, missing `PrivacyInfo.xcprivacy` required-reason entries with the most common approved code, and a TODO above a floating `xcode: latest` pin (never a rewrite: which Xcode meets the minimum is a fact about today).

**Aggressive tier:** scaffolds only, in `app_store_audit_scaffolds/` — Sign in with Apple, Delete Account, an AI consent gate (Swift and React) that gates on the consent value alone, and a Restore Purchases control. Never a silent edit to working auth or purchase code.

### 6. If the user pasted a rejection notice

Extract every guideline number and the quoted reason. Run the audit to see whether the code confirms each one. If the `appstore-rejections-mcp` server is installed, call `search_rejections` with the verbatim text and `get_cases` for the app's category (see `references/rejection-lookup.md`); if not, offer the one-line install. For each finding give: what the reviewer saw, why the guideline applies, the exact change, whether a new build is needed, and the Resolution Center reply text (`references/metadata-review.md`). Look for the second-order failure — a demo account the reviewer deleted, a consent gate on a "seen" flag, a Restore button in Settings — because rejections come in pairs.

### 7. Ask what the repository cannot answer

Before writing the report, ask the questions at the end of `references/submission-artifacts.md`: the demo account and whether it can be deleted, whether the Privacy Policy and Support URLs are live now, whether the EULA link is in the Description, when App Privacy was last answered, the age-rating tier, the Paid Applications agreement, and the CI Xcode version. Record the answers in the SUBMISSION ARTIFACTS table.

### 8. Write the report

`--report` produces it; edit rather than rewrite. Order: HARD BLOCK → LIKELY REJECTION → RISK FLAG → SUBMISSION ARTIFACTS → manual checklist. Keep an empty section with "None found." — an absent heading reads as an oversight. Within a section, quickest fix first.

### 9. Always end with the manual checklist

The checks below marked "No" cannot be automated. Walk them with the user; do not let a green scan stand in for them.

## Honesty guardrails — do not soften these

- **Never say "will pass" or "guaranteed".** Say "this lowers your rejection risk on X, Y, Z".
- **The test suite backtests the tool, not Apple.** `python3 tests/run_tests.py` proves the auditor flags what it claims, passes clean fixtures, and that autofix re-audits clean on mechanical checks. It says nothing about any submission.
- **Autofix deliberately leaves things failing** — in-app paywall links, Sign in with Apple, account deletion, AI consent, the CI pin — rather than fake them. Surface those as real work, not tool defects.
- **Static analysis has hard limits.** Purpose-string quality, ongoing value, minimum functionality, spam, metadata accuracy and prominence need a human.

## Master pre-submission checklist

| # | Check | Guideline | Automatable? |
|---|---|---|---|
| 1 | No placeholder text, "coming soon", empty states, dead links in shipped screens | 2.1 | Partial |
| 2 | Tested on a real device, current and one older iOS, small and large screens; no crash | 2.1, 2.4.1 | No |
| 3 | Screenshots current, show the app in use, 4+-safe regardless of age rating | 2.3 | No |
| 4 | Description, keywords and age rating match the binary; no untrue claims ("zero-knowledge encryption") | 2.3, 2.3.1 | Partial |
| 5 | No "Android", "Google Play", "web version" or cheaper-elsewhere wording visible on iOS | 2.3.10, 3.1.3 | Yes (`cross_platform_mentions`) |
| 6 | Not a near-duplicate of a templated app; original name and icon | 4.3, 4.1(c) | No |
| 7 | Native functionality beyond a wrapped website | 4.2 | Partial |
| 8 | Demo credentials in App Review notes, permanent, seeded, no 2FA, tested the morning of submission | 2.1 / process | No |
| 9 | If the reviewer can delete the demo account, a second account or a protected one exists | 5.1.1(v) + process | No |
| 10 | Digital goods use In-App Purchase; web subscriptions honoured, never sold or steered to, on iOS | 3.1.1, 3.1.3(b) | Partial |
| 11 | Paywall shows title, duration, full renewal price as the most prominent price, what you get, Privacy Policy, Terms of Use, Restore Purchases | 3.1.2 | Yes (`paywall_elements`) |
| 12 | Prices rendered from StoreKit / RevenueCat, no literal price strings on native | 3.1.2 | Yes (`hardcoded_prices`) |
| 13 | Terms of Use link also in the App Store Description | 3.1.2 | Yes (`iap_metadata_eula_link`) |
| 14 | Trial / intro price not more prominent than the billed price | 3.1.2 | No |
| 15 | Sign in with Apple offered wherever another social login is | 4.8 | Yes |
| 16 | In-app account deletion that deletes server-side | 5.1.1(v) | Partial |
| 17 | Every permission has a specific purpose string; requested only when the feature is used | 5.1.1, ITMS-90683 | Yes |
| 18 | Consent screen before the first send to any third-party AI, naming each vendor by legal entity and what is sent; gated on consent alone | 5.1.2(i) | Yes (`ai_consent_gate`) |
| 19 | Consent screen, App Privacy labels and privacy policy describe the same data flow | 5.1.1, 5.1.2(i) | No |
| 20 | `PrivacyInfo.xcprivacy` declares every required-reason API the app's own code uses | ITMS-91053 | Yes (`required_reason_apis`) |
| 21 | Every SDK on Apple's list ships its own manifest and signature | ITMS-91061 | Partial (`sdk_manifests`) |
| 22 | Built with the current minimum SDK; CI Xcode pinned explicitly | ITMS-90725 | Partial (`ci_xcode_pin`) |
| 23 | `ITSAppUsesNonExemptEncryption` set; version and build keys present and increasing | Upload | Yes |
| 24 | One App Store id across Rate/Share buttons and CI | 2.1 | Yes (`app_store_id_consistency`) |
| 25 | Privacy Policy and Support URLs live, with a contact route | 1.5, 5.1.1(i) | Partial (`--check-urls`) |
| 26 | Icon 1024×1024 without alpha; launch screen present | ITMS-90022 | Yes (`audit_assets.py`) |
| 27 | App Review notes brief the reviewer: demo account, path to features and paywall, third-party data sharing, hardware | process | No |
| 28 | Paid Applications agreement signed; IAP products in "Ready to Submit" and attached to the version | process | No |

## Notes for Claude

- The scripts are heuristic. Verify before telling the user something is wrong; a clean PASS across the board does not mean the app is ready — items marked "No" above cannot be checked from source.
- Framework matters. The scanner handles native Swift/Obj-C, React Native, Flutter and Capacitor patterns, and knows to look in backend trees for AI vendors; sanity-check its output against the project you can see.
- If no project directory is accessible, skip the scripts and walk the checklist conversationally, pointing to the reference file per topic.
- Guideline numbers move. Quote the rule text alongside the number, and re-verify the 3.1.x and 5.1.x families against the live guidelines before anything load-bearing.
