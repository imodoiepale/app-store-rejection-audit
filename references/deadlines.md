# Dated requirements

**Verified September 2026.** Re-verify against <https://developer.apple.com/news/upcoming-requirements/> before relying on this after **Q1 2027**. Everything here has a date attached because it has flipped, or is scheduled to flip, from "recommended" to "enforced".

Read this file first when auditing. A missed SDK minimum is a hard block that makes every other finding irrelevant, and it is the one finding that goes from PASS to FAIL with no change to the repo.

## Already enforced

| Since | Requirement | How it fails |
|---|---|---|
| 2026-04-28 | Apps must be built with the **iOS 26 SDK (Xcode 26 or later)** | ITMS-90725 at upload |
| 2025-05-01 | **Privacy manifests and signatures** for SDKs on Apple's list | ITMS-91061 at upload |
| 2024-05-01 | **Required-reason API** declarations in `PrivacyInfo.xcprivacy` | ITMS-91053 / 91055 at upload |
| 2025-11-13 | **5.1.2(i)** explicit consent before sharing personal data with third-party AI | Review rejection |
| 2025-11-13 | **4.1(c)** copycat branding, **4.7** mini-app rules clarified | Review rejection |
| 2025-05-01 | **3.1.1(a) / 3.1.3(a)** post-*Epic* external-link rules by storefront (US differs) | Review rejection |
| 2025 | **5-tier age rating** (4+/9+/13+/16+/18+); existing apps re-answered | Metadata block |
| 2026-09 | Apps with social feeds or UGC: **13+ minimum** | Metadata block |
| 2022-06-30 | **Account deletion** in-app for apps with account creation (5.1.1(v)) | Review rejection |
| 2020-04-30 | **Sign in with Apple** when other third-party logins are offered (4.8) | Review rejection |

## How to check the SDK minimum locally

```bash
xcodebuild -version          # Xcode 26.x or newer
xcodebuild -showsdks         # iphoneos26.x present
```

In CI, check the runner image, not your machine. `xcode: latest` (Codemagic), `macos-latest` (GitHub Actions) and `osx-xcode-edge` (Bitrise) float with the provider's image and are the most common cause of "it uploads from my laptop but not from CI". `audit_project.py` flags them as `ci_xcode_pin`; pin an explicit version and bump it on purpose.

The **deployment target** (`IPHONEOS_DEPLOYMENT_TARGET`) is a separate setting and does not need to move; only the SDK the binary is built against does.

## Staleness rule for this repository

If today is past the re-verify date above, say so to the user before quoting any dated fact, and fetch the upcoming-requirements page. Guideline numbers move too: the November 2025 update renumbered nothing but added subsections, and the 3.1.x family has been renumbered twice since 2023. Quote the rule text, not only the number.
