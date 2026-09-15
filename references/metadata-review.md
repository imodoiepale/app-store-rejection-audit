# Metadata, review notes, and what to do after a rejection

Read this for 2.1 / 2.3 / 4.3 findings, and whenever the user has already been rejected and needs to respond. Adapted from [artbyjazi/app-store-approval](https://github.com/artbyjazi/app-store-approval) (MIT).

## What reviewers check that no script can

| Item | Guideline | What "pass" looks like |
|---|---|---|
| Screenshots match the shipped build | 2.3 | Same UI, same features, no mockup frames claiming features that do not exist |
| Description matches the binary | 2.3 | No promised feature that is absent or gated behind an unreachable flow |
| Demo account works | 2.1 | Credentials in App Review notes, account not expired, not rate-limited, works on a cold install |
| Age rating questionnaire | — | Answered under the 5-tier system; social feeds force 13+ from September 2026 |
| App Privacy labels match data flows | 5.1.1 | Every collected type declared, matching `PrivacyInfo.xcprivacy` and the consent screen |
| Support URL is live with a contact route | 1.5 | Reachable page, real contact method |
| Privacy policy URL is live | 5.1.1(i) | Reachable, and also linked in-app |
| No references to other platforms | 2.3.10 | No "Android", "Google Play", "web version" in metadata or UI |
| Icon and name do not use another developer's brand | 4.1(c) | Original branding |
| The app does something a website cannot | 4.2 | Native capability the reviewer can trigger |

## App Review notes — the template that prevents 2.1

```
DEMO ACCOUNT
  Email:    reviewer@example.com
  Password: ********
  The account is permanent, has sample data, no 2FA, no rate limits.
  A second account (reviewer2@example.com / ********) is provided because
  the app supports in-app account deletion and you may wish to test it.

HOW TO REACH THE MAIN FEATURES
  1. Sign in with the demo account, or tap "Continue as guest" to see the
     sample content without an account.
  2. Home → Morning ritual → Play. Audio streams; the timer runs.
  3. The paywall is under Settings → Upgrade, and appears after the third
     generated ritual. Purchases use Apple In-App Purchase (RevenueCat
     entitlement "premium").

THIRD-PARTY DATA SHARING
  Survey answers, first name and journal text are processed by <Vendor,
  legal entity> (<product>) to generate guidance. Voice samples are
  processed by <Vendor> to build a personal voice. The consent screen
  appears after the survey on first launch and blocks every AI feature
  until accepted. Privacy policy: <url>

PERMISSIONS
  Microphone: requested only when the user taps Record on the voice-setup
  screen or the journal dictation button. Notifications: requested only from
  the Notifications settings screen, never at launch.

HARDWARE / ACCOUNTS REQUIRED
  None. Background audio mode is declared so a ritual keeps playing when the
  screen locks.

WHY THIS APP IS NOT A DUPLICATE (only if 4.3 has been raised before)
  <one paragraph naming the unique functionality>
```

Reviewers read these. Most "Information Needed" replies are answered before they happen by a good notes field.

## 4.3 spam — what actually helps

A 4.3 rejection says the app "shares a similar binary, metadata and/or concept as apps submitted by other developers". Appeals that succeed name specific, demonstrable functionality the comparison apps lack, in the first sentence, with a path to reach it. Appeals that fail argue about branding, describe the target audience, or say the app is "unique". Cosmetic reskins of a shared engine keep getting rejected regardless of the argument.

## The rejection response path

1. **Read the guideline number** in Resolution Center. Look it up: `references/rejection-db.md` in this repo maps it to the rule, the detection and the fix; the `appstore-rejections-mcp` server (see `rejection-lookup.md`) has 554 real cases with what cleared them.
2. **Decide whether a new build is needed.** Metadata findings (2.3, 3.1.2 metadata, 1.5) are fixed in App Store Connect and resubmitted without a build. Binary findings need a build. "Information Needed" needs only a reply.
3. **Reply in Resolution Center** (below), then resubmit. Replies are read by the same reviewer; be specific and short.
4. **Appeal** through the App Review Board only when you believe the guideline was misapplied, not when you disagree with it. Appeals take longer than fixing.
5. **Phone call** — the Resolution Center offers one for some rejections; take it for 4.3 and 4.2, where a human explanation of the native functionality moves things.

### Writing the Resolution Center reply

- First sentence: which guideline, what you changed. "Guideline 3.1.2 — the paywall now shows a Restore Purchases button and links to the Privacy Policy and Terms of Use directly beneath the purchase button (build 42)."
- Then the path to verify it, as numbered steps from a cold launch.
- Attach a screenshot or a short recording of the changed screen.
- If the reviewer could not find something that exists, do not argue; say where it is and offer the recording. "Not seen" is a common outcome under reviewer inconsistency and a calm reply clears it.
- Never promise a fix in a "future update". The build under review is the one being judged.

### When the user pastes a rejection notice

1. Extract every guideline number and the quoted reason.
2. Map each to a check in `audit_project.py`; run the audit to see whether the code confirms it.
3. For each, give: what the reviewer saw, why the guideline applies, the exact change, whether a new build is needed, and the reply text.
4. Look for the second-order failure: a demo account that was deleted by the reviewer, a consent screen gated on a "seen" flag, a Restore button in Settings rather than the paywall. Rejections come in pairs.

Verified September 2026.
