---
name: app-store-rejection-audit
description: Audit an iOS or cross-platform (React Native/Flutter/PWA-wrapped) app for the most common Apple App Store rejection reasons before submitting to App Review. Use this whenever the user is preparing an App Store submission, mentions App Store rejection, App Review, TestFlight, demo/reviewer credentials, Apple in-app purchases or auto-renewable subscriptions, Sign in with Apple, account deletion requirements, App Store Connect metadata or screenshots, or asks things like "why was my app rejected," "how do I avoid App Store rejection," or "is my app ready to submit." Also trigger proactively for React Native, Flutter, Capacitor, or PWA-wrapped apps heading to iOS, since Guideline 4.2 (minimum functionality / webview wrappers) disproportionately hits those stacks.
---

# App Store Rejection Audit

A pre-submission audit skill covering the Apple App Store Review Guideline categories that account for the large majority of first-submission rejections: 2.1 (App Completeness), 2.3 (Accurate Metadata), 3.1.1 (In-App Purchase), 3.1.2 (Subscriptions), 4.2 (Minimum Functionality), 4.3 (Spam), 4.8 (Sign in with Apple), and 5.1.1 (Privacy / Account Sign-In).

This is risk reduction, not a guarantee. Apple's review is ultimately a human judgment call — a clean audit lowers the odds of a rejection, it doesn't eliminate them. Never tell the user their app "will pass."

## How to use this skill

1. **If a project directory is available** (via bash/computer tools), run the automated scan first:
   ```
   python3 scripts/audit_project.py /path/to/project
   ```
   This gives a PASS/WARN/FAIL report across the checks that can actually be verified by reading source code and config files.

2. **Walk through the manual items** the script cannot check — these live in App Store Connect or require a real device, not the codebase. Use the "Can't be automated" list at the bottom of the script's report, cross-referenced against the checklist below.

3. **For anything flagged**, open the matching reference file before advising the user — it has the exact rejection language reviewers send, the specific fix, and edge cases people commonly get stuck on.

| Flag / topic | Reference file |
|---|---|
| Crashes, placeholder content, broken links, hardware compatibility | `references/app-completeness-and-design.md` |
| Webview-heavy / PWA-wrapped app risk, "looks like a website" | `references/app-completeness-and-design.md` |
| Repackaged/templated app, too similar to existing apps | `references/app-completeness-and-design.md` |
| Screenshots, description, age rating, icon mismatches | `references/app-completeness-and-design.md` |
| Demo/reviewer login credentials, 2FA blocking review | `references/accounts-and-sign-in.md` |
| Sign in with Apple required or not | `references/accounts-and-sign-in.md` |
| Account deletion missing | `references/accounts-and-sign-in.md` |
| Digital goods sold outside Apple IAP, external payment links | `references/payments-and-subscriptions.md` |
| Auto-renewable subscription missing price/length/EULA/privacy link | `references/payments-and-subscriptions.md` |
| Free trial displayed more prominently than billed price | `references/payments-and-subscriptions.md` |
| Missing/vague permission usage strings (camera, location, mic...) | `references/privacy-and-permissions.md` |
| Privacy Nutrition Label / App Privacy questionnaire accuracy | `references/privacy-and-permissions.md` |
| Third-party SDK privacy manifests, AI data-sharing disclosure | `references/privacy-and-permissions.md` |

## Master pre-submission checklist

| # | Check | Guideline | Automatable? |
|---|---|---|---|
| 1 | No placeholder text, "coming soon," empty states, dead links | 2.1 | Partial (script scans for common markers) |
| 2 | App tested on a real device, not just simulator — no crash on launch | 2.1 | No |
| 3 | Tested against the current + at least one older iOS version and device size | 2.1, 2.4.1 | No |
| 4 | Screenshots are current, show the app in use, and are rated for all audiences regardless of the app's actual age rating | 2.3 | No |
| 5 | App description and age rating accurately reflect the app's content | 2.3 | No |
| 6 | App isn't a near-duplicate of an existing template/app with only cosmetic differences | 4.3 | No (judgment call) |
| 7 | App offers native functionality beyond "a website in a wrapper" — relevant if built on RN/Flutter/webview/PWA | 4.2 | Partial (heuristic ratio check) |
| 8 | Working demo account credentials provided in App Store Connect Review Notes, tested the morning of submission; no SMS/authenticator 2FA the reviewer can't complete | 5.1.1 / review process | Partial (script flags login flows; you must test credentials manually) |
| 9 | If a demo account can be deleted by the reviewer, the app handles that gracefully (recreate-on-delete or a protected review account) | account deletion + review process | No |
| 10 | Digital content/subscriptions use Apple In-App Purchase, not external payment links | 3.1.1 | Partial (script flags IAP/payment SDK usage) |
| 11 | Auto-renewable subscriptions display title, length, price, and functional links to Privacy Policy + Terms of Use (EULA), both in-app and in App Store Connect metadata | 3.1.2 | Partial (script checks for policy/EULA link presence) |
| 12 | Free trial / intro price is not shown more prominently than the actual billed price | 3.1.2 | No (visual judgment call) |
| 13 | If any third-party social login (Google, Facebook, etc.) is offered, Sign in with Apple is also offered | 4.8 | Yes (script checks SDK references) |
| 14 | If the app supports account creation, it supports in-app account deletion (not just "email us") | 5.1.1(v) | Partial (script flags signup without deletion markers) |
| 15 | Every permission request (camera, location, mic, contacts, etc.) has a specific, accurate Info.plist usage-description string, and only fires when the feature is used | 5.1.1 | Yes (script maps API usage to Info.plist keys) |
| 16 | App Privacy ("Nutrition Label") questionnaire in App Store Connect accurately reflects all data collected, including by third-party SDKs | 5.1.1 | No (lives in App Store Connect, not the codebase) |
| 17 | Third-party SDKs (analytics, ads, attribution) have current privacy manifests and signatures | 5.1.1 / SDK integrity | No (check each SDK vendor's docs) |
| 18 | If the app sends user data to an external AI service (OpenAI, Anthropic, Gemini, etc.), there's a clear consent screen naming the provider | 5.1.1 / newer AI disclosure requirement | No (judgment call, verify screen exists) |
| 19 | Privacy Policy link works and is reachable both in-app and in App Store Connect metadata | 5.1.1 | Partial (script checks for a policy link/string) |
| 20 | `App Review Information → Notes` briefs the reviewer on anything non-obvious: required hardware, complex flows, demo account behavior | review process | No |

## Notes for Claude

- The script is heuristic. A FAIL means "go look at this," not "this is definitely broken" — verify before telling the user something is wrong. A clean PASS across the board doesn't mean the app is ready; items 2–6, 8–9, 12, 16–18, 20 above can't be checked from source code at all.
- Framework matters for the webview-ratio and permission-mapping checks — the script handles native Swift/Obj-C, React Native, and Flutter patterns, but always sanity-check its output against what you can see of the actual project rather than trusting it blindly.
- If the user hasn't got a project directory accessible (e.g. they're just asking conceptually, or their code lives outside this environment), skip the script and just walk the checklist with them conversationally, pointing to the relevant reference file per topic.
