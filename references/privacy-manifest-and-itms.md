# Privacy manifests and the ITMS upload blockers

These are not review findings. They are **App Store Connect refusing the upload**, so nothing reaches a human and there is no Resolution Center thread to argue in. Every one is deterministic and every one is checkable from the repo, which is why the audit marks them HARD BLOCK.

Adapted from [artbyjazi/app-store-approval](https://github.com/artbyjazi/app-store-approval) (MIT).

| Error | Meaning | Where the fix lives |
|---|---|---|
| ITMS-91053 | A required-reason API is used with no `NSPrivacyAccessedAPITypes` entry | `PrivacyInfo.xcprivacy` in the app target |
| ITMS-91055 | Same, but the reason code given is not on the approved list for that category | `PrivacyInfo.xcprivacy` |
| ITMS-91056 | Manifest present but malformed | `PrivacyInfo.xcprivacy` |
| ITMS-91061 | A third-party SDK on Apple's list ships without its own manifest or signature | The SDK version you depend on |
| ITMS-90683 | A permission is requested with no purpose string | `Info.plist` |
| ITMS-90022 | Missing 1024×1024 marketing icon, or an icon with alpha | Asset catalog |
| ITMS-90725 | Built against an SDK older than the current minimum | CI Xcode version (see `deadlines.md`) |

## PrivacyInfo.xcprivacy — structure

```xml
<plist version="1.0"><dict>
  <key>NSPrivacyTracking</key><false/>
  <key>NSPrivacyTrackingDomains</key><array/>
  <key>NSPrivacyCollectedDataTypes</key>
  <array>
    <dict>
      <key>NSPrivacyCollectedDataType</key><string>NSPrivacyCollectedDataTypeEmailAddress</string>
      <key>NSPrivacyCollectedDataTypeLinked</key><true/>
      <key>NSPrivacyCollectedDataTypeTracking</key><false/>
      <key>NSPrivacyCollectedDataTypePurposes</key>
      <array><string>NSPrivacyCollectedDataTypePurposeAppFunctionality</string></array>
    </dict>
  </array>
  <key>NSPrivacyAccessedAPITypes</key>
  <array>
    <dict>
      <key>NSPrivacyAccessedAPIType</key><string>NSPrivacyAccessedAPICategoryUserDefaults</string>
      <key>NSPrivacyAccessedAPITypeReasons</key><array><string>CA92.1</string></array>
    </dict>
  </array>
</dict></plist>
```

The file must be a member of the app target (Build Phases → Copy Bundle Resources). A manifest sitting in the folder but not in the target is the same as no manifest.

## Required-reason API categories and approved codes

| Category | Typical API | Approved codes (pick the one that is true) |
|---|---|---|
| `…CategoryUserDefaults` | `UserDefaults`, `@AppStorage`, Capacitor Preferences | **CA92.1** app's own defaults · 1C8F.1 app group · C56D.1 SDK wrapper · AC6B.1 iCloud KVS |
| `…CategoryFileTimestamp` | `.creationDate`, `.modificationDate`, `stat`, `fstat`, `getattrlist` | **C617.1** timestamps of the app's own files · 3B52.1 files the user chose · 0A2A.1 SDK wrapper · DDA9.1 display to user |
| `…CategorySystemBootTime` | `systemUptime`, `mach_absolute_time`, `KERN_BOOTTIME` | **35F9.1** elapsed time inside the app · 8FFB.1 calculate absolute timestamps for events · 3D61.1 SDK wrapper |
| `…CategoryDiskSpace` | `volumeAvailableCapacity`, `statfs`, `NSFileSystemFreeSize` | **85F4.1** display to user · **E174.1** check space before writing · 7D9E.1 SDK wrapper · B728.1 health research app |
| `…CategoryActiveKeyboards` | `activeInputModes` | 3EC4.1 custom keyboard app · 54BD.1 SDK wrapper |

`audit_project.py` scans only the **app's own** Swift/Objective-C sources for these; SDKs and Capacitor/RN plugins carry their own manifests. `autofix.py` adds the bold default code for a missing category and leaves a note; change the code if a different reason is the true one.

## Third-party SDK manifests (ITMS-91061)

Apple publishes a list of commonly used SDKs that must ship a privacy manifest and a signature. The copy in `scripts/data/apple-sdk-manifest-list.txt` has 86 entries and is matched against `Podfile.lock`, `Package.resolved`, `package.json` and `pubspec.yaml`. Notable for hybrid apps: **Capacitor, Cordova, Flutter, hermes** (React Native's engine), **FirebaseCore/Messaging/Auth, GoogleSignIn, FBSDKCoreKit, OneSignal**, and most Flutter plugins (`shared_preferences_ios`, `path_provider`, `url_launcher`…).

An SDK on the list is fine when the version you depend on bundles `PrivacyInfo.xcprivacy`. The audit reports WARN, not FAIL, because SPM checkouts and CocoaPods installs are usually not committed and it cannot see inside them. Confirm by opening the SDK's changelog for "privacy manifest" or by looking in `DerivedData/…/SourcePackages/checkouts/<sdk>/`.

Source: <https://developer.apple.com/support/third-party-SDK-requirements/>

## Purpose strings (ITMS-90683 and 5.1.1)

Two failures. The upload block: the key is missing and the app requests the permission — App Store Connect rejects, and on-device the app crashes on the request. The review finding: the key exists but says "This app needs camera access". Purpose strings name the feature: "DepthMe records your voice so it can read your daily guidance back to you in your own voice." If audio also goes to a transcription vendor, say so in the same string; the consent-screen rule in `third-party-ai-consent.md` applies here too.

## Icon and launch screen (ITMS-90022)

A 1024×1024 PNG with **no alpha channel**, in the asset catalog, plus a launch storyboard. `audit_assets.py` checks this with Pillow when installed. `autofix.py` can flatten the alpha onto white; if your icon needs another background, re-export from the source instead.

## Export compliance

`ITSAppUsesNonExemptEncryption` in `Info.plist` answers the question TestFlight otherwise asks on every build ("Missing Compliance"). `false` is correct for an app that only uses HTTPS/TLS and OS-provided crypto. `true` means you ship your own encryption and must file the export documentation. `autofix.py` sets `false` when the key is absent and tells you why that might be wrong.

Verified September 2026. Reason codes: <https://developer.apple.com/documentation/bundleresources/privacy_manifest_files/describing_use_of_required_reason_api>
