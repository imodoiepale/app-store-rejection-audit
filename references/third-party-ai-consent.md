# Third-party AI consent — Guideline 5.1.2(i)

Added to the App Review Guidelines on **November 13, 2025**. For any app that sends user data to an AI vendor this is the single highest-value check in this project, because it is new enough that apps which passed review in 2025 fail on their next update, and because the fix is UI work nobody budgets for.

Adapted from [artbyjazi/app-store-approval](https://github.com/artbyjazi/app-store-approval) (MIT), extended for hybrid apps where the vendor call lives server-side.

## The rule, verbatim

> "You must clearly disclose where personal data will be shared with third parties, including with third-party AI, and obtain explicit permission before doing so."

## The rejection text you will actually receive

> "The app appears to share the user's personal data with a third-party AI service but the app does not clearly explain what data is sent, identify who the data is sent to, and ask the user's permission before sharing the data."

Read that as a three-item checklist. Reviewers do.

## All four requirements must be met

1. **Disclose WHAT data is sent.** "The text of your journal entry and your survey answers", not "some data" or "your inputs".
2. **Name WHO receives it, by legal entity and product.** "OpenAI, L.L.C. (GPT-4o)", "ElevenLabs, Inc.", "Deepgram, Inc.". A generic "our AI partner" or "AI services" fails. Every vendor, not just the LLM: voice cloning, transcription, embeddings and GPU-hosted inference are all third-party AI.
3. **Obtain permission BEFORE the first transmission.** The consent control sits in front of the first network call, not in a Settings screen the user may never open, and not in a Terms checkbox on the sign-up form.
4. **The privacy policy identifies all of it** and confirms that the third party protects the data equivalently.

## The consistency triangle

Three artefacts must describe the same data flow: the consent screen, the App Privacy nutrition labels in App Store Connect, and the hosted privacy policy. Reviewers compare them. If the consent screen says "your voice recording", the labels must declare Audio Data, and the policy must name the voice vendor. A vendor named in the policy but absent from the consent screen is the most common mismatch.

## The documented repeat-rejection trap

Developers have logged eight or more rejection cycles on this one guideline with a consent screen that existed. The root cause in the best-documented case was the condition:

```swift
// WRONG — the reviewer never saw the screen
if !hasSeenConsent && !hasConsented { showConsent() }
```

A `hasSeenConsent`-style flag, or anything that is reset differently per launch or per install, meant the screen did not appear on the review device. The reviewer reported "the app does not ask permission", and no amount of screenshots in the reply changed that.

The fix that cleared it gates the AI features on the consent value **alone**:

```swift
// RIGHT — no "seen" flag anywhere in the condition
if !hasConsented {
    ConsentView()      // blocks all AI features until accepted
} else {
    RootView()
}
```

`audit_project.py` flags a line where `consent` shares a condition with `hasSeen*`, `didShow*`, `firstLaunch*`, `hasShown*` or `onboardingComplete*`.

Persist consent **per account**, not only per device. A reviewer installs fresh and signs in with the demo account; if consent lives only in local storage they see the screen (good), but if the demo account was consented on another device and consent lives only server-side, they never see it (bad). Store it on the profile row and mirror it locally.

## Hybrid apps: where the scanner has to look

In a React Native, Flutter or Capacitor app the vendor call is almost never in the app bundle. It is in a Supabase edge function, a Cloud Function, a Next.js API route or a Lambda, and the client calls that. Scanning only the iOS target reports "no third-party AI detected" and is wrong.

The scanner therefore:

- searches **client and backend** trees (`supabase/functions`, `functions/`, `api/`, `server/`, `backend/`, `edge/`, `lambda/`, `workers/`) for vendor endpoints and SDK imports;
- then looks for a consent control **only in shipped, user-visible text**: i18n files and string literals in UI files, never comments, log lines or import paths;
- and reports which detected vendors are never named anywhere the user can read.

That last list is the fix list. Apple's list of vendors is not closed; the scanner's endpoint list includes OpenAI, Anthropic, Google, Azure OpenAI, Bedrock, Mistral, Groq, Cohere, Together, Perplexity, OpenRouter, DeepSeek, xAI, ElevenLabs, Fish Audio, Deepgram, AssemblyAI, Replicate, RunPod, Hugging Face, Stability, Play.ht and Cartesia. Add yours in `AI_ENDPOINT_RE`.

## What the consent screen looks like when it passes

- Its own step, before the survey or the first generated content, not a modal on top of the feature that is about to fire.
- Plain sentence per vendor: *what* → *who* → *why*. One sentence each.
- A link to the privacy policy on the same screen.
- Two buttons. "I agree" and a real "Not now" that leaves the user in a part of the app that works without AI (guest content, static content). A "Not now" that dead-ends is a 5.1.1(iv) manipulation finding.
- The microphone purpose string in `Info.plist` matches: if dictation goes to a transcription vendor, the purpose string says the audio is transcribed, not only "records your voice".

## App Review notes that pre-empt the challenge

```
THIRD-PARTY DATA SHARING
  Survey answers, your name and journal text are processed by OpenAI, L.L.C.
  (GPT-4o) to generate guidance. Voice samples are processed by ElevenLabs,
  Inc. and Fish Audio to build a personal voice. Dictation audio is
  transcribed by Deepgram, Inc. The consent screen appears after the survey
  on first launch and blocks every AI feature until accepted.
  Privacy policy: https://…/privacy-policy (section "Third-party services")
```

Sources: <https://developer.apple.com/news/?id=ey6d8onl>, <https://developer.apple.com/forums/thread/815109>, <https://developer.apple.com/forums/thread/820209>. Verified September 2026; re-verify the guideline number at <https://developer.apple.com/app-store/review/guidelines/#5.1.2>.
