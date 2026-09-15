# Payments & Subscriptions

Covers Guideline 3.1.1 (In-App Purchase) and 3.1.2 (Subscriptions) — one of the three most-cited rejection categories alongside crashes and metadata.

## 3.1.1 — In-App Purchase

- Any digital content or service consumed **within the app** — subscriptions, unlocking features, virtual goods, digital media — must go through Apple's In-App Purchase system. External payment links, "buy on our website," or hidden paywalls that bypass IAP for digital goods get rejected.
- Physical goods and services consumed outside the app (e.g. a waste-management invoice, a taxi ride, a hotel booking) are **not** subject to IAP — those can use external payment flows like M-Pesa STK push, card processors, etc. The distinction is whether what's being purchased is consumed inside the app or in the real world.
- If you have IAP products configured, they must be complete, priced, visible to the reviewer, and functional at review time. A common rejection is Apple simply being unable to locate the IAP screen — if you've hidden purchase UI behind a flow the reviewer can't reach, either surface it or remove references to it from the metadata.
- Use Apple's **Sandbox environment** to test the entire purchase flow end-to-end before submitting, including receipt validation. A frequent bug: production servers choke on sandbox-signed receipts. Validate against production first, and only fall back to the sandbox endpoint if that validation fails with a "sandbox receipt used in production" error.

## 3.1.2 — Subscriptions

Auto-renewable subscriptions are only appropriate for services providing **dynamic, ongoing value** over time — not a one-time unlock dressed up as a subscription. If your "subscription" is really just a permanent feature unlock, Apple may reject it as an inappropriate use of the subscription mechanism and ask you to switch to a non-consumable IAP instead.

**Required disclosures — both in the app binary itself and in App Store Connect metadata:**
- Title of the subscription (can match the IAP product name)
- Length of the subscription
- Price, and price-per-unit if relevant
- A functional link to your Privacy Policy
- A functional link to your Terms of Use (EULA)

If you don't have a custom EULA, you can simply reference Apple's standard EULA — add a line to your App Store Description:
`Terms of Use: https://www.apple.com/legal/internet-services/itunes/dev/stdeula/`

If you do have a custom EULA, set it under **App Store Connect → App Information → Custom App Store Licensing Agreement** rather than only linking it in-app.

**Common rejection: "links present but review still says missing."** This is usually a placement issue, not an absence issue — the links need to be reachable from the purchase/subscription screen itself, not just buried in a general Settings menu. Put them directly on or immediately next to the paywall.

**Free trial / pricing display:** the actual billed amount must be at least as visually prominent as any free trial or intro-price messaging. A subscription button that says "Start free trial 🔓" in bold with the real recurring price in small, low-contrast text below it is a common rejection — the fix is usually as simple as making the price line the same size/weight, e.g. "7-day free trial, then KES X,XXX/month" with the price given equal visual weight.

**Upgrades/downgrades** between subscription tiers should be seamless — users shouldn't be able to accidentally end up subscribed to two variations of the same thing at once.

## The seven required paywall elements

Reviewers walk the purchase flow end to end. All seven must be visible on the paywall itself, not in a Settings screen the reviewer may never open:

1. **Subscription title.**
2. **Length / duration** of the subscription period.
3. **The full renewal price, as the most prominent price element**, localized — plus a per-unit price if helpful. A large "$4.99/mo" next to a small "billed $59.99/year" is a rejection.
4. **What the user gets** for each period.
5. **A functional Privacy Policy link.**
6. **A functional Terms of Use (EULA) link.**
7. **A Restore Purchases control.** Required even when entitlements sync automatically — the reviewer looks for the button. `audit_project.py` reports it under `paywall_elements`; the aggressive autofix tier writes a scaffold.

Minimum subscription length is **7 days**, and the subscription must be available across all of the user's devices. Thin utility subscriptions attract a "does this provide ongoing value?" challenge under 3.1.2; prepare reviewer notes that answer it directly.

### Prices come from the store, never from a string

```swift
// WRONG — wrong currency, wrong tax, wrong number in most storefronts
Text("$9.99 / month")

// RIGHT
Text(product.displayPrice)
Text(product.subscription?.subscriptionPeriod.formatted() ?? "")
```

RevenueCat: `package.product.priceString`. Play Billing: `formattedPrice`. A hardcoded price is both a 3.1.2 finding and a real bug: the App Store shows the localized price on the purchase sheet, so the paywall and the sheet disagree. Keeping constants as a **web-only** fallback is fine; rendering them on native is not. `audit_project.py` flags literal price strings in UI and i18n files as `hardcoded_prices`.

### Family Sharing

If a subscription is Family Sharing-enabled in App Store Connect, the paywall may say so; it must not claim sharing that is not enabled.

## 3.1.1(a) / 3.1.3 — the regional split since May 1, 2025

After *Epic v. Apple* the rules differ by storefront:

- **United States storefront:** apps may include buttons and links to external purchase options for digital goods, without Apple's entitlement, provided the link is not deceptive and the in-app IAP path remains. Steering language ("cheaper on our website") is allowed *there*.
- **European Union:** the alternative-terms entitlement and the Core Technology Fee regime apply; external links need the entitlement and disclosure sheet.
- **Everywhere else:** the pre-2025 rule holds — no external purchase links or steering for digital goods (3.1.1), no mention of pricing elsewhere (3.1.3).

The practical consequence for a global app: **gate the wording by storefront**, or do not show it at all. A single binary that shows "buy on the web for less" in Kenya, Thailand or the UK is rejected under 3.1.3 even though the same string is legal in the US. `audit_project.py` flags "on the web", "web version", "Stripe", "PayPal", "Google Play" and "Android" in shipped text as `cross_platform_mentions`; on iOS the user should see App Store wording only.

### 3.1.3 categories that may use non-IAP payment

Reader apps (3.1.3(a)), multiplatform services where the purchase was made elsewhere (3.1.3(b)), enterprise services (3.1.3(c)), person-to-person services (3.1.3(d)), physical goods and services (3.1.3(e)), and free stand-alone companions to paid web tools (3.1.3(f)). A meditation or wellness subscription is none of these; it is a digital service consumed in-app and must use IAP on iOS, even when the same account can also subscribe on the web via Stripe. What the app may do is **honour** a web subscription (3.1.3(b)); what it may not do is **sell** or **steer** to one.

### Reviewer notes that pre-empt 3.1.2 challenges

State the subscription's ongoing value in one sentence ("new personalised guidance generated every day"), where the paywall is, that Restore Purchases is on it, and that the same entitlement is honoured across web and mobile.
