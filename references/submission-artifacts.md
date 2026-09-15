# Submission artifacts — everything that lives outside the code

No script can see App Store Connect. This is the list of what a reviewer touches there, ordered by what it costs you when it is wrong, with the questions to ask before submitting. Adapted from [artbyjazi/app-store-approval](https://github.com/artbyjazi/app-store-approval) (MIT).

## Ordered by cost

1. **Demo credentials** — the single most common "Information Needed" reply (2.1). Costs a full review cycle.
2. **Terms of Use link in the Description** — 3.1.2, rejected on the paywall walk-through.
3. **Privacy Policy URL live** — 5.1.1(i); a 404 is a metadata rejection.
4. **Support URL live with a contact route** — 1.5.
5. **App Privacy labels matching the manifest and the consent screen** — 5.1.1; increasingly enforced.
6. **Age rating under the 5-tier system** — wrong answers delay, rarely reject.
7. **Export compliance** — TestFlight friction, not a rejection.
8. **Paid Applications agreement, banking, tax** — the build cannot go to review with IAP until these are signed by the Account Holder.

## App Review Information

### Sign-in required

If any feature needs an account, tick "Sign-in required" and supply a demo account that is:

- **permanent** — not a trial that expires next week, not an account with a 30-day inactivity purge;
- **seeded** — the reviewer should see the app in a normal populated state, not an empty shell;
- **free of 2FA, SMS codes, magic links and CAPTCHAs** — the reviewer cannot receive your texts;
- **not rate-limited** — reviewers regenerate, retry and reopen more than a user would;
- **tested the morning of submission** from a cold install.

If the app supports in-app account deletion (5.1.1(v)) the reviewer **will delete the demo account** to test it, and the second review pass then fails at login. Either seed two accounts and say so in the notes, or protect the review account server-side (refuse deletion for that email and return a clear message) while leaving the flow testable with a fresh sign-up.

### Contact information

A phone number and email that a human answers during the review window. Apple calls when the notes are ambiguous.

### Notes (4,000 characters)

Use the template in `metadata-review.md`. Cover: demo account behaviour, the path to the main features, the path to the paywall, third-party data sharing (name the vendors), hardware or accounts the reviewer will not have, and why the app is not a duplicate if 4.3 has ever been raised.

### Attachments

A screen recording of the purchase flow and of the consent screen saves a cycle when the reviewer cannot reproduce them. Keep it under a minute.

## URLs

| Field | Requirement |
|---|---|
| Support URL | Reachable, and offers a way to contact you (form, email, chat). A marketing page with no contact route fails 1.5. |
| Marketing URL | Optional. If set, must be live. |
| Privacy Policy URL | Reachable, and the policy must also be linked in-app. Must name every third-party recipient of personal data, including AI vendors. |

Run `audit_project.py --check-urls` to HEAD-request the URLs it finds in docs and metadata; it is off by default because the test suite must not need the network.

## Terms of Use / EULA

There is no dedicated field. Put the link in the **Description** — Apple's standard EULA (`https://www.apple.com/legal/internet-services/itunes/dev/stdeula/`) is acceptable if you have no custom terms. A custom EULA also goes under App Information → License Agreement. The same link must be on the paywall in the binary; one without the other is a 3.1.2 finding.

## App Privacy labels

Every data type the app or any SDK collects, whether it is linked to identity, whether it is used for tracking, and its purposes. Must agree with `PrivacyInfo.xcprivacy` and with the consent screen. Audio uploaded to a voice-cloning vendor is **Audio Data**; journal text sent to an LLM is **Other User Content**; a purchase history synced from RevenueCat is **Purchase History**. "Data not collected" with an analytics SDK in the binary is the classic mismatch.

## Age rating

Five tiers since 2025: 4+, 9+, 13+, 16+, 18+. Apps with a social feed or user-generated content are forced to 13+ minimum from September 2026. Wellness apps that discuss anxiety, stress or grief are usually 12+/13+ under "Medical/Treatment Information — infrequent"; answer the questionnaire literally rather than aspirationally.

## Export compliance

Answered by `ITSAppUsesNonExemptEncryption` in `Info.plist` (see `privacy-manifest-and-itms.md`). Without it, every TestFlight build stops at "Missing Compliance" until someone clicks through.

## The rest, one line each

- **Screenshots** match the shipped build, current UI, no frames claiming features that do not exist (2.3). Required sizes change; 6.9" and 6.5" iPhone are the current mandatory set, iPad only if the binary targets iPad.
- **App name and subtitle** contain no other platform names and no pricing claims.
- **Keywords** contain no competitor brand names (4.1(c)).
- **Category** matches the primary function.
- **Copyright** is the legal entity that owns the app, matching the developer account.
- **Version** in App Store Connect equals `MARKETING_VERSION` in the binary.
- **Build number** increases on every upload.
- **Phased release / manual release** chosen deliberately.
- **In-app purchases** are attached to the version being submitted, each with a display name, description and a review screenshot, and are in "Ready to Submit".
- **Subscription group** has a localized display name.
- **Introductory offers** are configured on the products if the paywall advertises a trial.

## Questions to ask the user before writing the report

1. Which demo account will you give the reviewer, and does the app let them delete it?
2. Are the Privacy Policy and Support URLs live right now, in a private window?
3. Is the Terms of Use link in the Description?
4. Have you answered App Privacy since the last SDK was added?
5. Which age-rating tier did you answer, and does the survey or content discuss health topics?
6. Is the Paid Applications agreement signed by the Account Holder?
7. Is the Xcode version on your CI at or above the current minimum?
