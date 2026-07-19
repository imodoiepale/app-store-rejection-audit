# Accounts, Demo Credentials & Sign-In

Covers the reviewer-access parts of Guideline 5.1.1 and Guideline 4.8 (Sign in with Apple). These are disproportionately common first-week rejections because they have nothing to do with app quality — the reviewer simply couldn't get in.

## Demo / reviewer credentials

- If the app has a login, provide working demo credentials in **App Store Connect → App Review Information → Notes**, and turn on whatever backend service the demo account depends on before you submit.
- **Test the credentials yourself the morning you submit.** Expired tokens, redeployed backends, or a database reset between when you wrote the notes and when you submitted are a very common self-inflicted rejection. The rejection message usually reads "we were unable to complete testing," which teams often misread as a bug report rather than an access failure — it's almost always credentials.
- Don't gate the demo account behind SMS or authenticator-app 2FA the reviewer can't complete. Disable 2FA for the specific reviewer account, or provide an alternate verification path.
- If your app has multiple roles (e.g. admin vs regular user), provide credentials for whichever role is needed to see the core features being reviewed — and say so explicitly in the notes.
- If you genuinely cannot provide a demo account for legal/security reasons (e.g. regulated fintech, healthcare), Apple allows a built-in demo mode instead, but it requires **prior approval from Apple** and must show the app's full functionality, not a stripped-down preview.

## The "reviewer deleted my demo account" problem

Since account deletion became mandatory, some reviewers test the deletion flow using the same account provided as demo credentials — which then breaks the login for any subsequent review pass. A workaround developers have converged on:
1. Recreate an account with the same credentials/data if the review account gets deleted.
2. In the deletion code path, special-case the designated review account so it can't be deleted — instead show a message explaining that this specific account is protected, and that they can create + delete a new account to verify the deletion flow.
3. State this explicitly in the App Review Notes, so the behavior isn't mistaken for a bug.

## Sign in with Apple (Guideline 4.8)

If the app offers **any** third-party or social login — Google, Facebook, X/Twitter, etc. — it must also offer Sign in with Apple as an equivalent, similarly prominent option. This applies even if email/password login is also available; the trigger is offering *any* third-party identity provider, not whether login is required at all.

Exceptions exist (e.g. education/enterprise apps using a mandated institutional login, or apps using the user's existing account with a specific third-party service where the service itself is the point of the app) — but don't assume you qualify; check the current guideline text or expect App Review to disagree.

## Account deletion (Guideline 5.1.1(v))

- If the app supports account creation, it must support account deletion **initiated within the app itself** — a visible, functional "Delete Account" control, not a "contact support" workaround.
- This has been required since June 30, 2022 and is still one of the most common 2026 rejections — it's an easy check for a reviewer to run, so it gets checked.
- If your app has no meaningful account-based features, the simplest compliant path is often to not require login at all rather than build out full account lifecycle management.
- Regulated industries (banking, healthcare, gambling, legal cannabis, air travel) have historically pushed back on this requirement citing compliance obligations, with mixed success in App Review responses — if this applies to you, budget time for a back-and-forth with Apple rather than assuming an exemption.
