# App Completeness, Metadata & Minimum Functionality

Covers Guidelines 2.1 (App Completeness), 2.3 (Accurate Metadata), 4.2 (Minimum Functionality), and 4.3 (Spam). Publicly reported rejection-reason breakdowns put crashes/completeness and spam/duplicate concerns among the single largest rejection categories — well over half of first-submission rejections trace back to something in this file.

## 2.1 — App Completeness

Apple will not review, or will reject, a binary that:
- Crashes on launch or during the review flow
- Contains placeholder text, "lorem ipsum," "coming soon," empty websites, or obviously temporary content
- Has broken links (support URL, marketing URL, in-app links)
- Includes in-app purchases that are incomplete, not visible to the reviewer, or non-functional

**Fixes:**
- Run a TestFlight external beta for several business days before the production submission and actually walk every screen, not just the happy path.
- Test on more than one device size — the smaller/older devices (e.g. iPhone SE) and the newest ones both surface different layout and crash bugs.
- If the app looks empty before a user creates any data, seed onboarding with sample data so the reviewer sees the app in a normal, populated state rather than a blank shell.
- Symbolicate and fix any crash reports from your own beta testing before submitting — don't rely on "it worked on my device."

## 2.3 — Accurate Metadata

- Screenshots must be current, must show the app actually being used, and must be appropriate for all audiences **regardless of the app's real age rating** — a 17+ app still needs 4+-safe screenshots.
- App icon in the binary and the marketing icon in App Store Connect must match.
- The description must be substantial and about the app itself — not just brand/company copy with no mention of what the app does.
- Age rating must match the actual content.

### 2.3.1 — Hidden features and claims that are not true

Metadata and UI copy must describe what the binary does. Two shapes of failure: a feature switch that unlocks behaviour the reviewer cannot see (hidden features), and a claim the code cannot back — "zero-knowledge encryption", "military-grade security", "clinically proven" — with no implementation behind it. Reviewers grep for these in screenshots and onboarding; when challenged, "we plan to" is not an answer. Say what is true: "stored under row-level security, deletable any time, never used to train public models."

### 2.3.10 — Other marketplaces and platforms

No "Android", "Google Play", "available on the web", "Windows" in the description, screenshots or UI shown on iOS. A settings string that says "manage your subscription in Google Play" is enough. Hybrid apps ship one string table for three platforms, so this is where they get caught; gate the string with `isNative()` / `Platform.OS` or give the native build its own override key. `audit_project.py` reports these as `cross_platform_mentions` and notes whether the file also carries a platform guard.

### 2.5.1 — HealthKit transparency

If the app reads or writes HealthKit data: purpose strings for share and update, a privacy-policy section naming the data types, no use for advertising, no storage in iCloud. Mindfulness minutes written to HealthKit are the common wellness-app case.

## 4.1(c) — Copycats (November 2025)

An app whose name, icon or presentation could be mistaken for another developer's is rejected regardless of function. Keyword fields that contain competitor brand names are metadata spam under the same clause.

## 4.7 — Mini apps and mini games (clarified November 2025)

Apps that host other apps (HTML5 games, chatbots, plug-ins, mini programs) must use the in-process web technology, must not extend native APIs to that content, must apply the same guidelines to the hosted content and must offer IAP for any digital purchases inside it. A "skills" or "plug-in" marketplace inside a wellness app is 4.7 territory.

## 4.2 — Minimum Functionality

This is the one that hits webview wrappers, PWA-style apps, and thin React Native/Flutter shells the hardest — it's a frequent rejection point for exactly the kind of full-stack/web-first apps that get ported to iOS as an afterthought.

Apple's underlying test isn't "does this have native code," it's "would a user have a real reason to install this instead of just visiting the website in Safari." Rejection language typically says the app "does not sufficiently differ from a mobile web browsing experience."

**What actually helps (from developer reports of successful appeals/fixes):**
- Native navigation patterns — tab bars, native menus, gestures — instead of a single full-screen webview.
- Push notifications with deep linking.
- Offline support / local caching of content.
- Platform features a website can't replicate: camera capture flows, on-device storage, widgets, share extensions, Face ID-gated content, background refresh.
- A splash screen and native onboarding, not an instant webview load.

**What doesn't reliably help**, based on rejection appeals that failed even after changes:
- Cosmetic native chrome wrapped around what is still fundamentally a content webview.
- "Users can already bookmark/share this in Safari" is not a counter-argument Apple accepts — the app has to be meaningfully better than that.

**If native functionality genuinely isn't the goal:** consider shipping as a PWA (Add to Home Screen via Safari) instead of fighting 4.2 repeatedly. You lose IAP, App Store discovery, and some background processing, but you skip App Review entirely. This is a legitimate architectural choice for content/dashboard-style apps, not just a fallback.

## 4.3 — Spam

Triggered when an app "shares a similar binary, metadata, and/or concept as apps submitted... by other developers, with only minor differences" — i.e., templated apps (common in prayer, weather, calculator, and simple utility categories) or an unusually large number of near-identical apps from one account.

**Fixes:** custom UI (not a stock template), original branding, and at least one feature that's genuinely specific to this app rather than swappable content in a shared shell. If you're shipping several apps off one internal template/engine for different clients, invest in visually and functionally differentiating each one before submission — Apple compares across the whole App Store, not just your account.
