# App Store Rejection Audit

A pre-submission audit for the Apple App Store Review Guidelines that account for the large majority of first-submission rejections — crashes/placeholder content (2.1), metadata (2.3), in-app purchases and subscriptions (3.1.1/3.1.2), minimum functionality for webview/PWA-style apps (4.2), spam/templated apps (4.3), Sign in with Apple (4.8), and privacy/permissions/account deletion (5.1.1).

It ships two things:

1. **A static-analysis script** (`scripts/audit_project.py`) that scans a project — native iOS, React Native, Flutter, or webview-wrapped — for the subset of these issues that are actually detectable from source: missing permission usage strings, placeholder UI text, Sign in with Apple gaps, missing account-deletion code paths, webview-heaviness, and missing Privacy Policy/EULA links alongside IAP code.
2. **A [Claude Skill](https://docs.claude.com)** (`SKILL.md` + `references/`) that packages the same knowledge — including everything the script *can't* check, like real-device crash testing, App Store Connect metadata, and the App Privacy questionnaire — so Claude can walk through a submission with you and know when to run the script versus when to just talk it through.

This is risk reduction, not a guarantee. Apple's review is a human judgment call. A clean report doesn't mean your app will be approved, and a flag doesn't always mean something is actually wrong — read the linked reference doc before treating any result as gospel.

## Using the script standalone

No dependencies beyond Python 3.8+.

```bash
python3 scripts/audit_project.py /path/to/your/project
```

Machine-readable output for CI:

```bash
python3 scripts/audit_project.py /path/to/your/project --json --output report.json
```

Exit code is `1` if any check fails, `0` otherwise — usable as a pre-submission CI gate (non-blocking is recommended given the heuristic nature of the checks; treat a non-zero exit as "review before you submit," not "build failed").

## Using it as a Claude Skill

Drop this folder into `~/.claude/skills/` (Claude Code) or upload it as a skill in claude.ai / Claude Cowork. Once installed, Claude will consult it automatically when you're working on an iOS submission, mention App Store rejection, App Review, demo credentials, IAP/subscriptions, or similar — no need to invoke it by name.

## What it checks

| Area | Guideline | Script | Reference doc |
|---|---|---|---|
| Crashes, placeholder content, broken links | 2.1 | Partial | `references/app-completeness-and-design.md` |
| Screenshots, description, age rating | 2.3 | No | `references/app-completeness-and-design.md` |
| Webview/PWA wrapper risk | 4.2 | Partial (heuristic) | `references/app-completeness-and-design.md` |
| Templated/duplicate apps | 4.3 | No | `references/app-completeness-and-design.md` |
| Demo credentials, reviewer access | 5.1.1 / process | No | `references/accounts-and-sign-in.md` |
| Sign in with Apple | 4.8 | Yes | `references/accounts-and-sign-in.md` |
| Account deletion | 5.1.1(v) | Partial | `references/accounts-and-sign-in.md` |
| In-app purchase | 3.1.1 | Partial | `references/payments-and-subscriptions.md` |
| Auto-renewable subscriptions | 3.1.2 | Partial | `references/payments-and-subscriptions.md` |
| Permission usage strings | 5.1.1 | Yes | `references/privacy-and-permissions.md` |
| App Privacy questionnaire, SDK manifests, AI disclosure | 5.1.1 | No | `references/privacy-and-permissions.md` |

Full checklist with all 20 items lives in `SKILL.md`.

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
