# Changelog

## 2.0.0 — 2026-09-15

The first release that covers the November 2025 guideline update and the upload-time ITMS blockers. Knowledge and structure adapted from [artbyjazi/app-store-approval](https://github.com/artbyjazi/app-store-approval) (MIT) and extended for hybrid apps; case lookup delegated to [robertojoseph/appstore-rejections-mcp](https://github.com/robertojoseph/appstore-rejections-mcp).

### Added

- **Severity per check** — `HARD BLOCK` / `LIKELY REJECTION` / `RISK FLAG` alongside the existing `PASS`/`WARN`/`FAIL` status, with counts in the report.
- **`--report PATH`** — writes an `APP_STORE_APPROVAL.md`: findings grouped by severity, each with Evidence / Why / Fix / Source; a SUBMISSION ARTIFACTS table for the App Store Connect side; the manual checklist.
- **`ai_consent_gate`** (5.1.2(i)) — detects third-party AI endpoints and SDKs in the client **and** in backend trees (`supabase/functions`, `functions/`, `api/`, `server/`…), then checks for a vendor named next to a consent control in shipped copy only (i18n files and string literals, never comments, logs or import paths), and flags the `hasSeen`-flag repeat-rejection trap. Vendor list covers LLM, voice, transcription and GPU-hosting providers.
- **`required_reason_apis`** (ITMS-91053) — required-reason API usage in the app's own native code vs `PrivacyInfo.xcprivacy`.
- **`sdk_manifests`** (ITMS-91061) — dependencies matched against Apple's 86-SDK list from `Podfile.lock`, `Package.resolved`, `package.json` and `pubspec.yaml`.
- **`paywall_elements`** and **`hardcoded_prices`** (3.1.2) — Restore, Terms, Privacy, duration and auto-renew wording on paywall-like files; literal price strings in UI and i18n.
- **`cross_platform_mentions`** (2.3.10 / 3.1.3) — "Android", "Google Play", "Stripe", "on the web" in shipped copy, with a note on whether the file carries a platform guard; the same i18n key across N locales is one finding.
- **`ci_xcode_pin`** — floating `xcode: latest` / `macos-latest` / `osx-xcode-edge` in CI config.
- **`version_keys`**, **`export_compliance`**, **`app_store_id_consistency`**, **`healthkit_transparency`**, and **`support_privacy_urls`** with an opt-in `--check-urls`.
- **Autofix, safe tier** — `ITSAppUsesNonExemptEncryption = false`, missing required-reason manifest entries with the most common approved code, a TODO above a floating CI pin.
- **Autofix, aggressive tier** — AI consent gate scaffolds (Swift and React) that gate on the consent value alone; Restore Purchases scaffolds.
- **References** — `third-party-ai-consent.md`, `privacy-manifest-and-itms.md`, `submission-artifacts.md`, `metadata-review.md`, `deadlines.md`, `rejection-lookup.md`; the seven paywall elements and the post-*Epic* regional split in `payments-and-subscriptions.md`; 2.3.1, 2.3.10, 2.5.1, 4.1(c), 4.7 in `app-completeness-and-design.md`.
- **`scripts/data/apple-sdk-manifest-list.txt`**.
- **Tests** — fixtures for a hybrid app with the vendor call in an edge function, the hasSeen trap, a manifest missing a category, a paywall without Restore, a hardcoded price, an ungated "Google Play", two App Store ids; assertions that the safe autofix clears ITMS-91053 and export compliance and honestly leaves the CI pin failing.

### Changed

- The scanner skips build output that Capacitor/Cordova copy into `ios/` and `android/`, hidden directories, lock and config files, and minified bundles. Before this, every finding on a Capacitor repo appeared twice and vendor bundles produced "not yet implemented" placeholders.
- `iap_metadata_eula_link` also accepts the EULA link in `docs/*.md`, `metadata/**`, `appstore/**` and fastlane description files.
- `SKILL.md` restructured around the severity model and a nine-step workflow: deadlines first, progressive reference loading, cross-check every finding, ask what the repo cannot answer, always end with the manual checklist.

## 1.0.0 — 2026-07-19

Initial release: source audit, asset audit, two-tier autofix, backtest suite, skill with five references.
