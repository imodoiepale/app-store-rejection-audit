# Privacy, Permissions & Data Disclosure

Covers Guideline 5.1.1 and the newer supply-chain/AI disclosure requirements layered on top of it in 2025–2026.

## Permission usage strings

Every system permission prompt (camera, location, microphone, contacts, photo library, calendar, Bluetooth, Face ID, health data, media library) needs a **specific, accurate** usage-description string in `Info.plist` — not a generic placeholder like "This app needs access to your camera." Explain *why*, in terms the end user understands (e.g. "Used to photograph receipts for expense tracking").

- Only request a permission at the moment the feature actually needs it — requesting everything up front at first launch, "just in case," is a common flag.
- If a permission is requested but the corresponding `Info.plist` key is missing or empty, the app crashes on that permission request on iOS — this is both a guideline violation and a guaranteed 2.1 crash rejection.
- Guideline 5.1.1(iv) specifically prohibits manipulating, tricking, or forcing consent — including apps that alter behavior based on a user's App Tracking Transparency response by gating unrelated permissions on it.

## App Privacy details ("Nutrition Label")

Every submission and update requires a privacy questionnaire in App Store Connect covering:
- What data types are collected (14 categories: contact info, health & fitness, financial info, location, browsing history, user content, identifiers, usage data, diagnostics, and others)
- Whether each data type is linked to the user's identity
- Whether each data type is used for cross-app/cross-site tracking
- What purpose the data serves (app functionality, analytics, product personalization, your own marketing, third-party advertising, other)

This must account for **third-party SDKs**, not just your own code — analytics, crash reporting, ad networks, and attribution SDKs all count toward your disclosure. It's self-declared and not directly audited at submission time, but false or incomplete disclosures are grounds for rejection or later removal if discovered, and Apple has been increasing enforcement here.

**Practical process before submission:**
1. Audit every third-party SDK in the project for what it collects by default and what it collects if you've enabled optional features.
2. Cross-reference against your actual App Store Connect questionnaire answers — these drift out of sync easily as SDKs get added over time without anyone updating the label.
3. Make sure your written Privacy Policy (linked in-app and in metadata) doesn't contradict what the questionnaire discloses.

## Third-party SDK privacy manifests

Apple now requires signatures and privacy manifests for many common third-party SDKs as part of software supply-chain integrity. If a bundled SDK (analytics, ads, attribution) doesn't have a current privacy manifest, or is found tracking without disclosure, **your app** is the one that gets rejected — even though you didn't write that code. Audit your dependency list before every submission, not just the first one; an SDK that passed six months ago can fail on a routine update if its manifest lapses or Apple's enforcement tightens.

## AI data-sharing disclosure

If the app sends user data to an external AI service (OpenAI, Anthropic, Google Gemini, or any other third-party model API), display a clear consent screen that **names the specific provider** and explains what data is shared before that data leaves the device. This is a newer requirement and apps built before it existed are getting caught on their first update submission after it took effect — worth checking even for apps that passed review previously.

## Privacy Policy link

A working Privacy Policy URL is required in App Store Connect metadata, and the policy must also be reachable from inside the app itself (not just the store listing) if the app collects any personal data. This is checked independently of the subscription-specific EULA/policy link requirement in `payments-and-subscriptions.md` — an app with no IAP still needs this if it collects user data at all.
