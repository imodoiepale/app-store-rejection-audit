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
