# Assets & Branding (Technical Compliance)

Covers the deterministic, file-level asset checks that Apple's automated pipeline and reviewers catch — primarily under Guideline 2.3 (Accurate Metadata) and the submission validation step, with placeholder/blank assets also touching 2.1 (App Completeness).

This is about whether the asset *files* are valid, not whether the design is *good*. Design quality is a subjective judgment this tooling deliberately doesn't make.

## App icon — hard technical rules

The master App Store icon is **1024×1024 pixels**, and getting it wrong causes rejection at validation time before a human even looks:

- **No alpha channel / transparency.** This is one of the most common automated icon rejections. Even a fully-opaque image *saved with* an alpha channel is rejected. Flatten onto a solid background and re-export without alpha. (The `autofix.py` safe tier does exactly this — composites onto white and re-saves as RGB.)
- **Exactly square, exactly 1024×1024** for the marketing asset. Non-square or wrong-dimension icons are rejected.
- **No manually-added rounded corners.** iOS applies its own superellipse corner mask automatically. If you round the corners yourself (leaving transparent corner pixels), the system mask stacks on top and produces a cropped/uneven look — and the transparency itself trips the alpha rule.
- **No drop shadows, gloss, or other pre-applied effects.** iOS handles presentation; bake nothing in.
- **Flat PNG, no layers.** Unlike Android's adaptive icons, iOS uses a single flat image. Keep key brand elements centered and inside a safe zone so nothing important sits at the very edge where the corner mask clips.
- **No trademarks, pricing, or "free" badges** in the icon.

Modern Xcode (15+) auto-generates all the smaller sizes from the single 1024 master, so for new projects you usually only supply the one asset. Older asset catalogs list every size explicitly in `Contents.json` — if a referenced filename is missing, or the `ios-marketing` 1024 entry is absent, App Store Connect throws "A 1024×1024 pixel app icon must be added to the asset catalog."

## Launch screen

A missing or blank/default launch screen reads as an incomplete app (2.1) and undercuts the "app-like" impression that matters for 4.2. Provide a real `LaunchScreen.storyboard` (or the SwiftUI equivalent) rather than shipping the default black/white screen.

## Screenshots (App Store Connect — not checkable from the repo)

Not something the asset script can inspect, but part of the same branding-compliance surface, so worth stating here:
- Screenshots must be current and show the app actually in use.
- They must be appropriate for **all audiences regardless of the app's age rating** — a 17+ app still needs 4+-safe screenshots.
- They must reflect features that actually ship — no "vision" mockups of unbuilt functionality (that's a 2.3 misleading-metadata rejection).

## What the tooling checks vs. what it can't

`scripts/audit_assets.py` checks: icon dimensions, alpha channel, transparent-corner heuristic, flat-placeholder heuristic, `Contents.json` integrity and referenced-file existence, launch-screen presence.

It cannot check: whether the design is attractive or on-brand, whether screenshots are honest and current (those live in App Store Connect), color/contrast accessibility, or how the icon reads at a glance on a real home screen. Those remain human judgment.
