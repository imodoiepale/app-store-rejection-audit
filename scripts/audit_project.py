#!/usr/bin/env python3
"""
App Store Rejection Audit — static analysis for common Apple App Review
rejection triggers.

Scans a project directory (native iOS, React Native, Flutter, or Capacitor/
webview-wrapped) for patterns that map to the most-cited App Store Review
Guideline categories: 2.1 (App Completeness), 2.3.10 (other marketplaces),
3.1.1/3.1.2 (IAP & Subscriptions, the seven paywall elements), 4.2 (Minimum
Functionality), 4.8 (Sign in with Apple), 5.1.1 (Privacy / permissions /
account deletion), 5.1.2(i) (third-party AI consent, Nov 2025), plus the
submission-time ITMS hard blocks (required-reason APIs vs
PrivacyInfo.xcprivacy, SDK manifests, export compliance, version keys, CI
Xcode pin).

Every check carries two fields:
  status    PASS / WARN / FAIL          — did the scan find the pattern
  severity  HARD BLOCK / LIKELY REJECTION / RISK FLAG
            — what it costs if it is real. HARD BLOCK means App Store Connect
            refuses the upload or review fails on a fact verifiable from the
            code. LIKELY REJECTION matches a documented rejection cause.
            RISK FLAG needs a human: quality, prominence, judgment calls.

This is a heuristic static scan, not a guarantee of App Review approval.
Several major rejection categories (crash testing on a real device, App
Store Connect metadata/screenshots, the App Privacy questionnaire, visual
judgment calls) cannot be checked from source code at all — see the
"Can't be automated" section printed at the end of every report.

Usage:
    python3 audit_project.py /path/to/project
    python3 audit_project.py /path/to/project --json
    python3 audit_project.py /path/to/project --json --output report.json
    python3 audit_project.py /path/to/project --report APP_STORE_APPROVAL.md
    python3 audit_project.py /path/to/project --check-urls   # HEAD-requests
                                                             # support/privacy
                                                             # /terms URLs
"""

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {
    ".git", "node_modules", "Pods", "build", "DerivedData", ".dart_tool",
    "Carthage", ".build", "dist", "out", "__pycache__", ".gradle",
    "xcuserdata", ".idea", ".vscode", "coverage", ".next", ".expo", ".venv",
    "venv", "graphify-out", "build-screenshots", "app_store_audit_scaffolds",
}

# Directories that are NOT shipped in the binary. Hits inside them do not
# reach a reviewer, so the user-facing checks (cross-platform mentions,
# placeholder text, paywall wording) skip them. The AI-endpoint scan does
# the opposite: it deliberately looks inside backend trees, because in a
# hybrid app the vendor call almost always lives server-side.
NON_SHIPPED_DIR_HINTS = (
    "/docs/", "/test/", "/tests/", "/__tests__/", "/scripts/", "/loadtest/",
    "/android/", "/admin/", "/e2e/", "/fixtures/", "/fastlane/", "/.github/",
)
# Build output that Capacitor / Cordova copy INTO the native trees on
# `cap sync`. It is the same code as src/, minified, so scanning it doubles
# every finding and adds vendor-bundle noise ("not yet implemented" inside a
# polyfill). Skipped entirely, like node_modules.
COPIED_WEB_BUILD_HINTS = (
    "/ios/App/App/public/", "/android/app/src/main/assets/public/",
    "/platforms/ios/www/", "/platforms/android/", "/www/assets/",
)
# Not user-facing text, whatever the extension says.
NON_COPY_FILE_RE = re.compile(
    r"^(?:package(?:-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|tsconfig[\w.]*\.json|"
    r"[\w.-]*\.config\.(?:[cm]?[jt]s|json)|capacitor\.config\.\w+|manifest\.json|"
    r"components\.json|\.eslintrc[\w.]*|vercel\.json|app\.json|eas\.json)$", re.I)
MINIFIED_LINE_LEN = 2000
BACKEND_DIR_HINTS = (
    "/supabase/functions/", "/functions/", "/api/", "/server/", "/backend/",
    "/edge/", "/lambda/", "/workers/", "/netlify/", "/cloud/",
)

SOURCE_EXTENSIONS = {
    ".swift", ".m", ".mm", ".h", ".js", ".jsx", ".ts", ".tsx", ".dart",
    ".html", ".htm", ".json", ".xml", ".storyboard", ".xib", ".kt", ".java",
}

MAX_FILE_BYTES = 2_000_000  # skip anything unusually large (bundled assets etc.)

HIGH_SEVERITY_PLACEHOLDERS = {
    "lorem ipsum": re.compile(r"lorem\s+ipsum", re.I),
    "coming soon": re.compile(r"coming\s+soon", re.I),
    "under construction": re.compile(r"under\s+construction", re.I),
    "not yet implemented": re.compile(r"not\s+(?:yet\s+)?implemented", re.I),
    "dummy/test data marker": re.compile(
        r"\bdummy\s+data\b|\btest\s+data\s*[-\u2013\u2014]\s*remove\b", re.I
    ),
}
LOW_SEVERITY_MARKERS = re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b")

PERMISSION_CHECKS = [
    ("Camera", re.compile(
        r"AVCaptureDevice|expo-camera|react-native-camera|CameraX|"
        r"cordova-plugin-camera", re.I),
        ["NSCameraUsageDescription"]),
    ("Location", re.compile(
        r"CLLocationManager|requestWhenInUseAuthorization|"
        r"requestAlwaysAuthorization|expo-location|react-native-geolocation|"
        r"@react-native-community/geolocation|Geolocator\(", re.I),
        ["NSLocationWhenInUseUsageDescription",
         "NSLocationAlwaysAndWhenInUseUsageDescription"]),
    ("Microphone", re.compile(
        r"AVAudioSession|requestRecordPermission|expo-av|"
        r"react-native-audio-recorder|SpeechRecognizer", re.I),
        ["NSMicrophoneUsageDescription"]),
    ("Photo Library", re.compile(
        r"PHPhotoLibrary|expo-image-picker|react-native-image-picker|"
        r"image_picker:|photo_manager:", re.I),
        ["NSPhotoLibraryUsageDescription"]),
    ("Contacts", re.compile(
        r"CNContactStore|expo-contacts|react-native-contacts|"
        r"contacts_service:", re.I),
        ["NSContactsUsageDescription"]),
    ("Apple Music / Media Library", re.compile(
        r"MPMediaLibrary|MPMediaPickerController", re.I),
        ["NSAppleMusicUsageDescription"]),
    ("Health", re.compile(r"HKHealthStore|health_kit", re.I),
        ["NSHealthShareUsageDescription", "NSHealthUpdateUsageDescription"]),
    ("Bluetooth", re.compile(
        r"CBCentralManager|CBPeripheralManager|flutter_blue|"
        r"react-native-ble", re.I),
        ["NSBluetoothAlwaysUsageDescription",
         "NSBluetoothPeripheralUsageDescription"]),
    ("Calendar", re.compile(
        r"EKEventStore|expo-calendar|react-native-calendar-events|"
        r"device_calendar:", re.I),
        ["NSCalendarsUsageDescription"]),
    ("Face ID", re.compile(
        r"LAContext|LocalAuthentication|local_auth:|"
        r"expo-local-authentication", re.I),
        ["NSFaceIDUsageDescription"]),
]

SOCIAL_LOGIN_RE = re.compile(
    r"GoogleSignIn|GIDSignIn|FBSDKLoginKit|LoginButton|GoogleAuthProvider|"
    r"signInWithGoogle|react-native-fbsdk|FacebookLogin|TwitterKit|"
    r"signInWithFacebook", re.I)
APPLE_SIGNIN_RE = re.compile(
    r"ASAuthorizationAppleIDProvider|AuthenticationServices|"
    r"SignInWithAppleButton|expo-apple-authentication|"
    r"sign[_\s-]?in[_\s-]?with[_\s-]?apple|apple_sign_in|AppleAuthProvider",
    re.I)

SIGNUP_RE = re.compile(
    r"\bsign\s?up\b|createAccount|createUserWithEmail|registerUser|"
    r"/auth/signup|/api/register", re.I)
DELETE_ACCOUNT_RE = re.compile(
    r"delete[_\s]?account|deleteUser|deauthorize|remove[_\s]?account|"
    r"/account/delete|/user/delete|closeAccount", re.I)

WEBVIEW_RE = re.compile(
    r"WKWebView|UIWebView|react-native-webview|flutter_webview|"
    r"InAppWebView", re.I)
NATIVE_UI_HINT_RE = re.compile(
    r"UIViewController|StatelessWidget|StatefulWidget|SwiftUI|"
    r"extends React\.Component|export default function", re.I)

IAP_RE = re.compile(
    r"StoreKit|SKProduct|SKPaymentQueue|react-native-iap|in_app_purchase:|"
    r"Purchases\.configure|RevenueCat|Adapty|Qonversion", re.I)
POLICY_RE = re.compile(r"privacy\s*policy", re.I)
EULA_RE = re.compile(
    r"terms\s*of\s*use|\beula\b|terms\s*and\s*conditions|terms\s*of\s*service",
    re.I)
URL_HINT_RE = re.compile(r"https?://", re.I)

# ---- 5.1.2(i) third-party AI consent (added to the guidelines Nov 13, 2025) ----
# Endpoints and SDK imports. The list is wider than the Swift-only upstream
# scans because hybrid apps talk to voice, transcription and GPU-hosting
# vendors that are just as much "third-party AI" as an LLM.
AI_ENDPOINT_RE = re.compile(
    r"api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|"
    r"aiplatform\.googleapis\.com|openai\.azure\.com|bedrock-runtime|"
    r"api\.x\.ai|api\.mistral\.ai|api\.cohere\.(?:ai|com)|api\.together\.xyz|"
    r"api\.groq\.com|api\.perplexity\.ai|openrouter\.ai|api\.deepseek\.com|"
    r"api\.elevenlabs\.io|api\.fish\.audio|api\.deepgram\.com|"
    r"api\.assemblyai\.com|api\.replicate\.com|api\.runpod\.ai|"
    r"[a-z0-9-]+\.api\.runpod\.ai|api-inference\.huggingface\.co|"
    r"api\.stability\.ai|api\.play\.ht|api\.cartesia\.ai|api\.speechmatics\.com|"
    r"api\.voyageai\.com|api\.jina\.ai|api\.pinecone\.io",
    re.I)
AI_SDK_RE = re.compile(
    r"from\s+['\"](?:openai|@anthropic-ai/sdk|@google/generative-ai|"
    r"@deepgram/sdk|elevenlabs|@elevenlabs/[\w-]+|replicate|@mistralai/[\w-]+|"
    r"groq-sdk|cohere-ai|together-ai|@huggingface/inference|assemblyai)['\"]|"
    r"require\(['\"](?:openai|@anthropic-ai/sdk|@deepgram/sdk|elevenlabs)['\"]\)|"
    r"import\s+(?:OpenAI|OpenAIKit|Anthropic|SwiftAnthropic|GoogleGenerativeAI|"
    r"LangChain|ElevenLabs|Deepgram)\b|"
    r"npm:(?:openai|@anthropic-ai/sdk|@deepgram/sdk|elevenlabs)|"
    r"AnthropicClient|OpenAIClient|GenerativeModel\(|ChatGPTAPI|"
    r"new\s+OpenAI\(|createClient\(\s*Deno\.env\.get\(['\"]DEEPGRAM",
    re.I)
# Vendor names as a reviewer would expect to see them in a consent screen.
# 5.1.2(i) wants the legal entity, so "our AI partner" does not count.
AI_VENDOR_NAME_RE = re.compile(
    r"(?<![/@\w.\-_])(?:"
    r"\bOpenAI\b|\bAnthropic\b|\bClaude\b|\bGemini\b|\bGoogle AI\b|\bVertex\b|"
    r"\bElevenLabs\b|\bEleven Labs\b|\bDeepgram\b|\bFish Audio\b|\bMistral\b|"
    r"\bGroq\b|\bCohere\b|\bReplicate\b|\bRunPod\b|\bHugging ?Face\b|"
    r"\bAzure OpenAI\b|\bBedrock\b|\bPerplexity\b|\bDeepSeek\b|\bxAI\b|"
    r"\bTogether AI\b|\bAssemblyAI\b|\bStability AI\b|\bPlay\.ht\b|\bCartesia\b"
    r")(?![/\w.\-_])",
    re.I)
CONSENT_WORD_RE = re.compile(
    r"\bconsent|\bagree\b|\bpermission\b|\bopt[\s-]?in\b|\ballow\b|\baccept\b",
    re.I)
# The repeat-rejection trap: a consent gate that is ALSO conditioned on a
# "seen this screen" flag. On the reviewer's device the flag state differs
# and the screen never appears — developers have logged 8+ cycles on this.
SEEN_FLAG_RE = re.compile(
    r"has[_]?seen\w*|did[_]?show\w*|first[_]?launch\w*|has[_]?shown\w*|"
    r"seen[_]?consent|consent[_]?shown|shown[_]?consent|onboarding[_]?complete\w*",
    re.I)

# ---- ITMS-91053 required-reason APIs vs PrivacyInfo.xcprivacy ----
# Category -> (usage regex over native sources, approved reason codes)
REQUIRED_REASON_APIS = [
    ("NSPrivacyAccessedAPICategoryUserDefaults", re.compile(
        r"\bUserDefaults\b|\bNSUserDefaults\b|@AppStorage\b", re.I),
        ["CA92.1", "1C8F.1", "C56D.1", "AC6B.1"]),
    ("NSPrivacyAccessedAPICategoryFileTimestamp", re.compile(
        r"\.creationDate\b|\.modificationDate\b|fileModificationDate|"
        r"contentModificationDateKey|creationDateKey|\bfstat\(|\blstat\(|"
        r"\bstat\(|getattrlist\(|fgetattrlist\(|\bfstatat\(", re.I),
        ["C617.1", "3B52.1", "0A2A.1", "DDA9.1"]),
    ("NSPrivacyAccessedAPICategorySystemBootTime", re.compile(
        r"\bsystemUptime\b|mach_absolute_time\(|KERN_BOOTTIME", re.I),
        ["35F9.1", "8FFB.1", "3D61.1"]),
    ("NSPrivacyAccessedAPICategoryDiskSpace", re.compile(
        r"volumeAvailableCapacity|NSFileSystemFreeSize|NSFileSystemSize|"
        r"\bstatfs\(|\bstatvfs\(|\bfstatfs\(|\bfstatvfs\(|"
        r"volumeTotalCapacity", re.I),
        ["85F4.1", "E174.1", "7D9E.1", "B728.1"]),
    ("NSPrivacyAccessedAPICategoryActiveKeyboards", re.compile(
        r"activeInputModes", re.I),
        ["3EC4.1", "54BD.1"]),
]
NATIVE_EXTENSIONS = {".swift", ".m", ".mm", ".h"}

# ---- 3.1.2 the seven paywall elements ----
PAYWALL_FILE_RE = re.compile(
    r"paywall|premium|upgrade|subscri|purchase|checkout|pricing|plans?\b|"
    r"membership|pro[_-]?screen|billing", re.I)
PAYWALL_ELEMENTS = {
    "restore_purchases": re.compile(r"restore", re.I),
    "terms_link": re.compile(
        r"terms\s*of\s*(?:use|service)|\beula\b|terms\s*(?:&|and)\s*conditions|"
        r"terms[_-]?(?:of[_-]?)?(?:service|use)|['\"]terms['\"]", re.I),
    "privacy_link": re.compile(r"privacy[\s_-]*policy|privacy[_-]?link", re.I),
    "duration": re.compile(
        r"\b(?:per|/|every|a)\s*(?:month|year|week)\b|monthly|yearly|annual|"
        r"weekly|\bmonth\b|\byear\b", re.I),
    "auto_renew_disclosure": re.compile(
        r"auto[\s-]?renew|renews?\s+automatically|cancel\s+(?:any\s?time|at\s+least)|"
        r"unless\s+cancel", re.I),
}
# A literal price inside UI or i18n text. Prices must come from StoreKit /
# RevenueCat / Play Billing at runtime — a hardcoded "$9.99" is the wrong
# currency and the wrong tax in most storefronts, and reviewers compare it
# against the sheet the App Store shows at purchase time.
HARDCODED_PRICE_RE = re.compile(
    r"(?<![\w{])(?:[$€£¥]|USD|EUR|GBP|KES)\s?\d{1,4}(?:[.,]\d{2})\b"
    r"(?:\s*/\s*(?:mo|month|yr|year|wk|week))?", re.I)
COMMENT_LINE_RE = re.compile(r"^\s*(?://|#|\*|/\*|<!--|\{/\*)")

# ---- 2.3.10 / 3.1.3 other-platform mentions visible on iOS ----
CROSS_PLATFORM_RE = re.compile(
    r"(?<![/@\-_.\w])(?:\bAndroid\b|Google\s*Play|Play\s*Store|\bStripe\b|\bPayPal\b|"
    r"\bon\s+the\s+web\b|\bweb\s+version\b|\bour\s+website\b\s+(?:for|to)\s+"
    r"(?:cheaper|less|a\s+discount)|\bWindows\s+Phone\b|\bHuawei\b|\bAppGallery\b)",
    re.I)
NATIVE_GUARD_RE = re.compile(
    r"isNative\(|isNativePlatform\(|Capacitor\.getPlatform|Platform\.OS|"
    r"defaultTargetPlatform|Platform\.isIOS|Platform\.isAndroid|"
    r"process\.platform|isIOS\b|isAndroid\b|\bnative\.[a-z_]+|"
    r"#if\s+os\(|TARGET_OS_", re.I)
UI_TEXT_EXTENSIONS = {".swift", ".m", ".mm", ".dart", ".tsx", ".jsx", ".ts",
                      ".js", ".json", ".html", ".htm", ".xml", ".strings",
                      ".storyboard", ".xib", ".kt"}

# ---- CI Xcode pin (dated requirement: iOS 26 SDK / Xcode 26 since 2026-04-28) ----
CI_FLOATING_XCODE_RE = re.compile(
    r"^\s*xcode:\s*(?:latest|edge)\s*$|xcode_version:\s*['\"]?(?:latest|edge)|"
    r"xcode-version:\s*['\"]?latest|"
    r"stack:\s*osx-xcode-edge|"
    r"macos-latest\b", re.I | re.M)
CI_FILE_GLOBS = ("codemagic.yaml", "codemagic.yml", "bitrise.yml",
                 ".github/workflows/*.yml", ".github/workflows/*.yaml",
                 "fastlane/Fastfile", ".gitlab-ci.yml", "appcircle.yml",
                 ".circleci/config.yml")

# ---- App Store id consistency ----
APP_STORE_ID_URL_RE = re.compile(
    r"apps\.apple\.com/[^\s'\"]*?/id(\d{9,10})|itms-apps://[^\s'\"]*?id(\d{9,10})|"
    r"itunes\.apple\.com/[^\s'\"]*?/id(\d{9,10})", re.I)
APP_STORE_ID_CONFIG_RE = re.compile(
    r"(?:APP_STORE_APP_ID|APP_STORE_ID|APPLE_APP_ID|app_store_id|apple_id|"
    r"appStoreId|appleId|ITC_APP_ID)\s*[:=]\s*['\"]?(\d{9,10})", re.I)

SUPPORT_URL_RE = re.compile(
    r"https?://[^\s'\"`)<>\]]*(?:support|help|contact|privacy|terms|legal|eula)"
    r"[^\s'\"`)<>\]]*", re.I)

# ---- Severity: what the finding costs if it is real ----
SEVERITY = {
    "placeholder_content": "LIKELY REJECTION",
    "info_plist_found": "RISK FLAG",
    "permission_usage_strings": "HARD BLOCK",
    "sign_in_with_apple": "LIKELY REJECTION",
    "account_deletion": "HARD BLOCK",
    "webview_ratio": "RISK FLAG",
    "iap_inapp_policy_eula_links": "LIKELY REJECTION",
    "iap_metadata_eula_link": "LIKELY REJECTION",
    "privacy_policy_present": "RISK FLAG",
    "ai_consent_gate": "LIKELY REJECTION",
    "required_reason_apis": "HARD BLOCK",
    "sdk_manifests": "RISK FLAG",
    "paywall_elements": "LIKELY REJECTION",
    "hardcoded_prices": "LIKELY REJECTION",
    "cross_platform_mentions": "RISK FLAG",
    "ci_xcode_pin": "RISK FLAG",
    "version_keys": "RISK FLAG",
    "export_compliance": "RISK FLAG",
    "app_store_id_consistency": "RISK FLAG",
    "support_privacy_urls": "LIKELY REJECTION",
    "healthkit_transparency": "LIKELY REJECTION",
}
SEVERITY_ORDER = ["HARD BLOCK", "LIKELY REJECTION", "RISK FLAG"]

GUIDELINES_URL = "https://developer.apple.com/app-store/review/guidelines/"
# Per-check "why it matters" / "how to fix" for the report writer. Kept
# short; the references/ files carry the long form.
CHECK_META = {
    "placeholder_content": (
        "Reviewers reject a binary that shows 'coming soon', lorem ipsum or "
        "test markers anywhere they can reach (2.1).",
        "Remove or finish the placeholder screens; if a feature is not ready, "
        "remove its entry point rather than stubbing it.",
        GUIDELINES_URL + "#2.1"),
    "permission_usage_strings": (
        "A permission prompt with no Info.plist purpose string crashes the app "
        "on that request (2.1) and App Store Connect rejects the upload "
        "outright as ITMS-90683.",
        "Add the NS*UsageDescription key with a sentence that names the "
        "feature the permission serves; generic wording is a 5.1.1 finding.",
        "https://developer.apple.com/documentation/bundleresources/information-property-list/protected-resources"),
    "sign_in_with_apple": (
        "Guideline 4.8: an app that offers Google, Facebook or another "
        "third-party login must offer Sign in with Apple (or an equivalent "
        "privacy-preserving login) with equal prominence.",
        "Add Sign in with Apple next to every other social login button and "
        "enable the capability on the App ID.",
        GUIDELINES_URL + "#4.8"),
    "account_deletion": (
        "Guideline 5.1.1(v): an app that lets users create an account must let "
        "them delete it in-app. Reviewers tap the button by hand; sign-out and "
        "'email us' do not count.",
        "Add a Delete Account action that calls a real server-side deletion "
        "and revokes the Sign in with Apple credential.",
        GUIDELINES_URL + "#5.1.1"),
    "webview_ratio": (
        "Guideline 4.2: an app that is 'not particularly useful, unique or "
        "app-like' is rejected — the #1 killer of webview wrappers.",
        "Add genuine native capability: offline content, push with deep links, "
        "widgets, share sheet, Face ID, background refresh.",
        GUIDELINES_URL + "#4.2"),
    "iap_inapp_policy_eula_links": (
        "Guideline 3.1.2: the paywall itself must carry functional Privacy "
        "Policy and Terms of Use links. Links buried in Settings are reported "
        "as missing.",
        "Put both links on or directly beneath the purchase button.",
        GUIDELINES_URL + "#3.1.2"),
    "iap_metadata_eula_link": (
        "The Terms of Use link must ALSO appear in App Store metadata. There is "
        "no dedicated field, so it goes in the Description.",
        "Add 'Terms of Use (EULA): <url>' to the App Store description, or set "
        "a custom EULA under App Information.",
        GUIDELINES_URL + "#3.1.2"),
    "privacy_policy_present": (
        "Guideline 5.1.1(i): a privacy policy must be linked in-app and in the "
        "store listing for any app that collects personal data.",
        "Link the hosted policy from Settings and from the paywall.",
        GUIDELINES_URL + "#5.1.1"),
    "ai_consent_gate": (
        "Guideline 5.1.2(i) (added Nov 13, 2025): 'You must clearly disclose "
        "where personal data will be shared with third parties, including with "
        "third-party AI, and obtain explicit permission before doing so.' The "
        "rejection text reads: 'the app does not clearly explain what data is "
        "sent, identify who the data is sent to, and ask the user's permission "
        "before sharing the data.'",
        "Show a consent screen BEFORE the first transmission that (1) says what "
        "data is sent, (2) names each vendor by legal entity, (3) asks for "
        "explicit permission, and (4) matches the privacy policy and the App "
        "Privacy labels. Gate on the stored consent value alone — never on a "
        "'seen' flag.",
        "https://developer.apple.com/news/?id=ey6d8onl"),
    "required_reason_apis": (
        "ITMS-91053: App Store Connect rejects an upload that uses a "
        "required-reason API without a matching entry in "
        "PrivacyInfo.xcprivacy. Nothing reaches a human reviewer.",
        "Add an NSPrivacyAccessedAPITypes entry for each category with an "
        "approved reason code (UserDefaults CA92.1, file timestamp C617.1, "
        "boot time 35F9.1, disk space E174.1, keyboards 3EC4.1).",
        "https://developer.apple.com/documentation/bundleresources/privacy_manifest_files/describing_use_of_required_reason_api"),
    "sdk_manifests": (
        "ITMS-91061: SDKs on Apple's list must ship their own privacy manifest "
        "and signature, or the upload is rejected.",
        "Update each listed SDK to a version that bundles PrivacyInfo.xcprivacy; "
        "check the vendor's changelog for 'privacy manifest'.",
        "https://developer.apple.com/support/third-party-SDK-requirements/"),
    "paywall_elements": (
        "Guideline 3.1.2: reviewers walk the purchase flow and look for the "
        "subscription title, duration, full renewal price as the most "
        "prominent price, what the user gets, Privacy Policy link, Terms link "
        "and a Restore Purchases control — all on the paywall itself.",
        "Add the missing element to the paywall screen, not to Settings.",
        GUIDELINES_URL + "#3.1.2"),
    "hardcoded_prices": (
        "A literal price string is the wrong currency and wrong tax in most "
        "storefronts, and disagrees with the sheet the App Store shows at "
        "purchase time — reviewers compare them (3.1.2).",
        "Render product.displayPrice / RevenueCat priceString / Play "
        "formattedPrice at runtime; keep constants only as a web fallback.",
        GUIDELINES_URL + "#3.1.2"),
    "cross_platform_mentions": (
        "Guideline 2.3.10: metadata and UI must not reference other mobile "
        "platforms; 3.1.3 forbids steering users to cheaper purchase paths "
        "outside the app.",
        "Gate the string on the native platform (isNative / Platform.OS) or "
        "reword it so iOS users see only App Store wording.",
        GUIDELINES_URL + "#2.3.10"),
    "ci_xcode_pin": (
        "Apple raises the minimum SDK every April (iOS 26 SDK / Xcode 26 since "
        "2026-04-28). A floating 'latest' pin means the linked SDK changes "
        "silently with the CI image; a stale image fails the upload with no "
        "code change.",
        "Pin an explicit Xcode version that meets the current minimum and bump "
        "it deliberately.",
        "https://developer.apple.com/news/upcoming-requirements/"),
    "version_keys": (
        "CFBundleShortVersionString / CFBundleVersion (MARKETING_VERSION / "
        "CURRENT_PROJECT_VERSION) must be present and must increase on every "
        "upload, or App Store Connect refuses the build.",
        "Set MARKETING_VERSION to the release version and let CI bump "
        "CURRENT_PROJECT_VERSION.",
        "https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleshortversionstring"),
    "export_compliance": (
        "Without ITSAppUsesNonExemptEncryption every TestFlight build shows "
        "'Missing Compliance' and blocks external testing until answered by "
        "hand.",
        "Add ITSAppUsesNonExemptEncryption = false to Info.plist if the app "
        "only uses HTTPS/TLS (the standard exemption); otherwise file the "
        "export documentation.",
        "https://developer.apple.com/documentation/security/complying-with-encryption-export-regulations"),
    "app_store_id_consistency": (
        "Two different App Store ids in one project means either the Rate/Share "
        "button opens the wrong listing or CI uploads to the wrong app record "
        "(2.1 broken link).",
        "Keep one constant for the App Store id and reference it everywhere.",
        GUIDELINES_URL + "#2.1"),
    "support_privacy_urls": (
        "A Support URL or Privacy Policy URL that 404s is a metadata rejection "
        "(1.5 / 5.1.1(i)); reviewers open both.",
        "Publish the page before submitting, or point the field at a page "
        "that exists.",
        GUIDELINES_URL + "#1.5"),
    "healthkit_transparency": (
        "Guidelines 2.5.1 / 5.1.3: HealthKit use needs a purpose string, a "
        "privacy-policy disclosure, and the data must never reach advertising "
        "or be stored in iCloud.",
        "Add NSHealthShareUsageDescription / NSHealthUpdateUsageDescription "
        "and disclose the data types in the privacy policy.",
        GUIDELINES_URL + "#5.1.3"),
}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).parts[:-1]
        if any(part.startswith(".") for part in rel):
            continue
        posix = "/" + path.as_posix().strip("/") + "/"
        if any(h in posix for h in COPIED_WEB_BUILD_HINTS):
            continue
        yield path


def looks_minified(text: str) -> bool:
    head = text[:20000]
    return any(len(line) > MINIFIED_LINE_LEN for line in head.splitlines())


def load_text(path: Path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return None


def gather_source_files(root: Path):
    files = []
    for path in iter_files(root):
        if path.suffix.lower() in SOURCE_EXTENSIONS:
            text = load_text(path)
            if text is None:
                continue
            if path.suffix.lower() in {".js", ".css", ".html"} and looks_minified(text):
                continue
            files.append((path, text))
    return files


def find_info_plists(root: Path):
    return [p for p in iter_files(root) if p.name == "Info.plist"]


def load_plist_keys(path: Path):
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str)}
    except Exception:
        return {}


def check_placeholders(files):
    findings = []
    todo_count = 0
    for path, text in files:
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pattern in HIGH_SEVERITY_PLACEHOLDERS.items():
                if pattern.search(line):
                    findings.append({
                        "file": str(path),
                        "line": lineno,
                        "marker": label,
                        "snippet": line.strip()[:120],
                    })
            if LOW_SEVERITY_MARKERS.search(line):
                todo_count += 1
    return findings, todo_count


def check_permissions(files, plist_keys):
    missing = []
    for name, api_pattern, required_keys in PERMISSION_CHECKS:
        used = any(api_pattern.search(text) for _, text in files)
        if not used:
            continue
        has_nonempty = False
        for keys in plist_keys.values():
            for rk in required_keys:
                val = keys.get(rk)
                if isinstance(val, str) and val.strip():
                    has_nonempty = True
        if not has_nonempty:
            missing.append({"permission": name, "required_keys": required_keys})
    return missing


def check_sign_in_with_apple(files):
    has_social = any(SOCIAL_LOGIN_RE.search(text) for _, text in files)
    has_apple = any(APPLE_SIGNIN_RE.search(text) for _, text in files)
    return has_social, has_apple


def check_account_deletion(files):
    has_signup = any(SIGNUP_RE.search(text) for _, text in files)
    has_delete = any(DELETE_ACCOUNT_RE.search(text) for _, text in files)
    return has_signup, has_delete


def check_webview_ratio(files):
    ui_like = [
        (p, t) for p, t in files
        if p.suffix.lower() in {".swift", ".m", ".mm", ".dart", ".tsx", ".jsx"}
    ]
    if not ui_like:
        return None
    webview_files = sum(1 for _, t in ui_like if WEBVIEW_RE.search(t))
    native_hint_files = sum(1 for _, t in ui_like if NATIVE_UI_HINT_RE.search(t))
    total = len(ui_like)
    ratio = webview_files / total if total else 0
    return {
        "webview_files": webview_files,
        "native_hint_files": native_hint_files,
        "total_ui_files": total,
        "ratio": round(ratio, 2),
    }


def check_iap_and_policy(files, root):
    has_iap = any(IAP_RE.search(text) for _, text in files)
    has_policy_link = any(
        POLICY_RE.search(text) and URL_HINT_RE.search(text) for _, text in files
    )
    has_eula_link = any(
        EULA_RE.search(text) and URL_HINT_RE.search(text) for _, text in files
    )
    has_policy_mention = any(POLICY_RE.search(text) for _, text in files)

    # Metadata EULA link is a separate requirement, checked in App Store
    # description files (which the source scan deliberately skips).
    has_eula_in_metadata = False
    meta_candidates = (list(root.rglob("description.txt"))
                       + list(root.rglob("AppStore_description.txt"))
                       + list(root.glob("docs/*.md")) + list(root.glob("*.md"))
                       + list(root.glob("metadata/**/*.txt"))
                       + list(root.glob("appstore/**/*.txt"))
                       + list(root.glob("appstore/**/*.md")))
    for meta in meta_candidates:
        if any(part in EXCLUDE_DIRS for part in meta.parts):
            continue
        try:
            t = meta.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if EULA_RE.search(t) and URL_HINT_RE.search(t):
            has_eula_in_metadata = True
            break

    return {
        "has_iap": has_iap,
        "has_policy_link": has_policy_link,
        "has_eula_link": has_eula_link,
        "has_policy_mention_anywhere": has_policy_mention,
        "has_eula_in_metadata": has_eula_in_metadata,
    }


def _posix(path: Path) -> str:
    return "/" + path.as_posix().strip("/") + "/"


def is_shipped_path(path: Path) -> bool:
    p = _posix(path)
    return not any(h in p for h in NON_SHIPPED_DIR_HINTS)


def is_backend_path(path: Path) -> bool:
    p = _posix(path)
    return any(h in p for h in BACKEND_DIR_HINTS)


def _hits(pattern, files, only=None, max_hits=40):
    out = []
    for path, text in files:
        if only is not None and not only(path):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = pattern.search(line)
            if m:
                out.append({"file": str(path), "line": lineno,
                            "match": m.group(0)[:60],
                            "snippet": line.strip()[:140]})
                if len(out) >= max_hits:
                    return out
    return out


def check_ai_consent(files):
    """5.1.2(i). Three questions, answered separately so the report can say
    which one failed:
      1. Does the project send anything to a third-party AI vendor? Look in
         the client AND the backend — in a hybrid app the vendor call lives
         in an edge function, and only the client is in the binary.
      2. Does shipped UI/i18n text name that vendor next to a consent word?
         That is the minimum a reviewer looks for: 'what data', 'who', and
         a control that asks.
      3. Is the consent gate also conditioned on a 'seen' flag? That is the
         documented repeat-rejection trap.
    """
    endpoint_hits = _hits(AI_ENDPOINT_RE, files)
    sdk_hits = _hits(AI_SDK_RE, files)
    vendors_used = set()
    for h in endpoint_hits + sdk_hits:
        m = h["match"].lower()
        for name, keys in (
            ("OpenAI", ("openai",)), ("Anthropic", ("anthropic",)),
            ("Google (Gemini/Vertex)", ("googleapis", "generative")),
            ("ElevenLabs", ("elevenlabs",)), ("Deepgram", ("deepgram",)),
            ("Fish Audio", ("fish.audio",)), ("RunPod", ("runpod",)),
            ("Replicate", ("replicate",)), ("Mistral", ("mistral",)),
            ("Groq", ("groq",)), ("Cohere", ("cohere",)),
            ("Hugging Face", ("huggingface",)), ("AssemblyAI", ("assemblyai",)),
            ("Perplexity", ("perplexity",)), ("DeepSeek", ("deepseek",)),
            ("xAI", ("api.x.ai",)), ("Together AI", ("together",)),
            ("OpenRouter", ("openrouter",)), ("AWS Bedrock", ("bedrock",)),
            ("Stability AI", ("stability",)), ("Play.ht", ("play.ht",)),
            ("Cartesia", ("cartesia",)),
        ):
            if any(k in m for k in keys):
                vendors_used.add(name)
    if not endpoint_hits and not sdk_hits:
        return {"vendors_detected": [], "endpoint_hits": [], "sdk_hits": [],
                "consent_evidence": [], "seen_flag_trap": [],
                "vendors_named_in_ui": []}

    # Consent evidence: a shipped, non-backend UI/i18n file where a consent
    # word and a vendor name appear within a short window of each other.
    consent_evidence = []
    vendors_named = set()
    for path, text in _shipped_ui_files(files):
        visible = _visible_text(path, text)
        # Names first, evidence second: the evidence loop stops at the first
        # hit per file, and a vendor listed after that hit still counts as
        # named (it did not, and reported "Deepgram never named" on a file
        # that named all four).
        for m in AI_VENDOR_NAME_RE.finditer(visible):
            vendors_named.add(m.group(0))
        for m in AI_VENDOR_NAME_RE.finditer(visible):
            lo, hi = max(0, m.start() - 400), m.end() + 400
            if CONSENT_WORD_RE.search(visible[lo:hi]):
                idx = text.find(m.group(0))
                consent_evidence.append({
                    "file": str(path),
                    "line": text.count("\n", 0, idx) + 1 if idx >= 0 else None,
                    "vendor": m.group(0),
                    "snippet": visible[max(0, m.start() - 80):m.end() + 80]
                    .replace("\n", " ").strip()[:200]})
                break  # one piece of evidence per file is enough

    # The trap: consent symbol and a seen/shown/first-launch flag in the same
    # condition or the same line.
    trap = []
    for path, text in files:
        if not is_shipped_path(path) or is_backend_path(path):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "consent" in line.lower() and SEEN_FLAG_RE.search(line) \
                    and re.search(r"\bif\b|&&|\|\||\?|!", line):
                trap.append({"file": str(path), "line": lineno,
                             "snippet": line.strip()[:160]})
    return {
        "vendors_detected": sorted(vendors_used),
        "endpoint_hits": endpoint_hits[:20],
        "sdk_hits": sdk_hits[:20],
        "consent_evidence": consent_evidence[:10],
        "vendors_named_in_ui": sorted(vendors_named),
        "seen_flag_trap": trap[:10],
    }


def find_privacy_manifests(root: Path):
    return [p for p in iter_files(root) if p.name == "PrivacyInfo.xcprivacy"]


def load_manifest_categories(path: Path):
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        return None
    cats = {}
    for entry in data.get("NSPrivacyAccessedAPITypes", []) or []:
        if isinstance(entry, dict):
            cats[entry.get("NSPrivacyAccessedAPIType", "")] = \
                list(entry.get("NSPrivacyAccessedAPITypeReasons", []) or [])
    return cats


def check_required_reason_apis(files, root: Path, plists):
    """ITMS-91053. Only the app's OWN native sources are scanned — third-party
    SDKs carry their own manifest (see check_sdk_manifests). Returns None when
    there is no native iOS tree to judge."""
    if not plists:
        return None
    native = [(p, t) for p, t in files if p.suffix.lower() in NATIVE_EXTENSIONS
              and is_shipped_path(p)]
    manifests = find_privacy_manifests(root)
    declared = {}
    for m in manifests:
        cats = load_manifest_categories(m)
        if cats:
            for k, v in cats.items():
                declared.setdefault(k, set()).update(v)
    used, missing = [], []
    for category, pattern, reasons in REQUIRED_REASON_APIS:
        hits = _hits(pattern, native, max_hits=5)
        if not hits:
            continue
        used.append(category)
        if category not in declared:
            missing.append({"category": category,
                            "approved_reasons": reasons,
                            "evidence": hits[:3]})
    return {
        "manifests_found": [str(m) for m in manifests],
        "categories_used": used,
        "categories_declared": sorted(declared),
        "missing": missing,
    }


def load_sdk_manifest_list():
    data = Path(__file__).resolve().parent / "data" / "apple-sdk-manifest-list.txt"
    if not data.exists():
        return set()
    return {l.strip() for l in data.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


def check_sdk_manifests(root: Path):
    """ITMS-91061. Names dependencies that are on Apple's privacy-manifest
    list and reports whether a manifest is visible in the checkout. SPM
    checkouts and CocoaPods installs are usually NOT committed, so a missing
    manifest here is 'verify', not 'broken'."""
    listed = load_sdk_manifest_list()
    if not listed:
        return None
    lower = {s.lower(): s for s in listed}
    found = {}

    def note(name, source):
        key = name.lower()
        if key in lower:
            found.setdefault(lower[key], set()).add(source)

    for lock in root.rglob("Podfile.lock"):
        if any(part in EXCLUDE_DIRS for part in lock.parts):
            continue
        for line in (load_text(lock) or "").splitlines():
            m = re.match(r"\s+- ([A-Za-z0-9_\-]+)", line)
            if m:
                note(m.group(1), str(lock))
    for resolved in root.rglob("Package.resolved"):
        if any(part in EXCLUDE_DIRS for part in resolved.parts):
            continue
        for m in re.finditer(r'"identity"\s*:\s*"([^"]+)"', load_text(resolved) or ""):
            note(m.group(1), str(resolved))
            note(m.group(1).replace("-swift-pm", ""), str(resolved))
    for pkg in root.rglob("package.json"):
        if any(part in EXCLUDE_DIRS for part in pkg.parts):
            continue
        try:
            deps = json.loads(load_text(pkg) or "{}")
        except json.JSONDecodeError:
            continue
        for dep in list((deps.get("dependencies") or {}).keys()):
            if dep.startswith("@capacitor/"):
                note("Capacitor", str(pkg))
            if dep in ("react-native",):
                note("hermes", str(pkg))
            if dep.startswith("@react-native-firebase/") or dep.startswith("firebase"):
                note("FirebaseCore", str(pkg))
            if dep.startswith("react-native-fbsdk"):
                note("FBSDKCoreKit", str(pkg))
            if dep == "react-native-onesignal":
                note("OneSignal", str(pkg))
    for pubspec in root.rglob("pubspec.yaml"):
        if any(part in EXCLUDE_DIRS for part in pubspec.parts):
            continue
        text = load_text(pubspec) or ""
        note("Flutter", str(pubspec))
        for m in re.finditer(r"^\s{2}([a-z_]+):", text, re.M):
            note(m.group(1), str(pubspec))

    manifests_in_tree = {m.parent.name.lower(): str(m)
                         for m in find_privacy_manifests(root)}
    entries = []
    for name in sorted(found):
        visible = [v for k, v in manifests_in_tree.items() if name.lower() in k]
        entries.append({"sdk": name, "declared_in": sorted(found[name]),
                        "manifest_visible_in_checkout": bool(visible),
                        "manifest_paths": visible[:2]})
    return {"listed_sdks_found": entries}


def _shipped_ui_files(files):
    return [(p, t) for p, t in files
            if p.suffix.lower() in UI_TEXT_EXTENSIONS and is_shipped_path(p)
            and not is_backend_path(p) and not NON_COPY_FILE_RE.match(p.name)]


STRING_LITERAL_RE = re.compile(
    r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')


DEV_ONLY_LINE_RE = re.compile(
    r"console\.\w+\(|logger\.\w+\(|\blog\(|\bwarn\(|\bdebug\(|throw new \w*Error\(|"
    r"\btrack\(|analytics\.\w+\(|Sentry\.|\bassert\(|print\(|NSLog\(|os_log\(")
IMPORT_LINE_RE = re.compile(r"^\s*(?:import\b|from\b|export\s+.*\bfrom\b|"
                            r"const\s+\w+\s*=\s*require\(|@import\b|#import\b)")


def _visible_text(path: Path, text: str) -> str:
    """What a user could read: whole file for i18n/markup, only string
    literals on non-comment lines for code. Keeps code comments that
    mention a vendor from counting as a consent screen."""
    if path.suffix.lower() in {".json", ".strings", ".xml", ".html", ".htm",
                               ".storyboard", ".xib"}:
        return text
    out = []
    for line in text.splitlines():
        if COMMENT_LINE_RE.match(line) or IMPORT_LINE_RE.match(line) \
                or DEV_ONLY_LINE_RE.search(line):
            continue
        for m in STRING_LITERAL_RE.finditer(line):
            lit = next(g for g in m.groups() if g is not None)
            if " " in lit.strip():
                out.append(lit)
    return "\n".join(out)


def check_paywall_elements(files, has_iap):
    """3.1.2 seven elements, checked over paywall-like files only. A store
    price string in i18n counts as a hardcoded price even when the screen
    file is clean, because that is what the user sees."""
    if not has_iap:
        return None
    ui = _shipped_ui_files(files)
    paywall = [(p, t) for p, t in ui if PAYWALL_FILE_RE.search(p.stem)]
    # i18n namespaces named like the paywall count as paywall text too
    corpus = "\n".join(t for _, t in paywall)
    present = {k: bool(v.search(corpus)) for k, v in PAYWALL_ELEMENTS.items()}
    # Restore must be on the paywall file itself, not just any file
    missing = [k for k, ok in present.items() if not ok]
    prices = []
    for p, t in ui:
        if p.suffix.lower() in {".json", ".strings", ".xml"} or PAYWALL_FILE_RE.search(p.stem):
            for lineno, line in enumerate(t.splitlines(), start=1):
                if COMMENT_LINE_RE.match(line):
                    continue
                m = HARDCODED_PRICE_RE.search(line)
                if m and "{{" not in line and "${" not in line[max(0, m.start() - 2):m.start() + 1]:
                    prices.append({"file": str(p), "line": lineno,
                                   "price": m.group(0),
                                   "snippet": line.strip()[:140]})
                    if len(prices) >= 25:
                        break
    return {
        "paywall_files": [str(p) for p, _ in paywall][:15],
        "elements_present": present,
        "elements_missing": missing,
        "hardcoded_prices": prices,
    }


def check_cross_platform_mentions(files):
    """2.3.10 / 3.1.3. For each hit, say whether the same file also carries a
    platform guard. i18n JSON cannot carry a guard, so those hits are
    reported as 'ungated (i18n)' — the guard, if any, lives in the consumer
    and a human has to confirm it."""
    hits = []
    for p, t in _shipped_ui_files(files):
        guarded = bool(NATIVE_GUARD_RE.search(t))
        is_i18n = p.suffix.lower() in {".json", ".strings", ".xml"}
        for lineno, line in enumerate(t.splitlines(), start=1):
            if COMMENT_LINE_RE.match(line):
                continue
            # In code files only quoted copy counts — `android: {` in a
            # config object or an import path is not something a user reads.
            if not is_i18n and (IMPORT_LINE_RE.match(line) or DEV_ONLY_LINE_RE.search(line)):
                continue
            haystack = line if is_i18n else "\n".join(
                lit for lit in (next(g for g in m.groups() if g is not None)
                                for m in STRING_LITERAL_RE.finditer(line))
                if " " in lit.strip())
            m = CROSS_PLATFORM_RE.search(haystack)
            if not m:
                continue
            # 'Stripe' in an import or an SDK call is code, not copy
            if m.group(0).lower() == "stripe" and re.search(
                    r"import|require|stripe\.|Stripe\(|stripe-js|@stripe", line):
                continue
            key = ""
            if is_i18n:
                km = re.match(r'\s*"([^"]+)"\s*:', line)
                key = km.group(1) if km else ""
                # Keys starting with "_" are maintainer notes inside the
                # string table, never rendered — the place a comment about
                # Google Play belongs, not a finding.
                if key.startswith("_"):
                    continue
            hits.append({"file": str(p), "line": lineno, "term": m.group(0),
                         "gated": "unknown (i18n)" if is_i18n else guarded,
                         "key": key, "snippet": line.strip()[:140]})
    # 20 locale files with the same key are one problem, not twenty.
    merged = {}
    for h in hits:
        k = (p_name(h["file"]), h["key"] or h["line"], h["term"].lower())
        if k in merged:
            merged[k]["locales"] += 1
        else:
            merged[k] = dict(h, locales=1)
    return list(merged.values())[:40]


def p_name(path_str: str) -> str:
    return Path(path_str).name


def check_ci_xcode_pin(root: Path):
    findings = []
    for pattern in CI_FILE_GLOBS:
        for f in root.glob(pattern):
            text = load_text(f)
            if not text:
                continue
            for m in CI_FLOATING_XCODE_RE.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                findings.append({"file": str(f), "line": lineno,
                                 "snippet": m.group(0).strip()[:100]})
    return findings


def check_version_keys(root: Path, plist_keys):
    pbx = list(root.rglob("project.pbxproj"))
    pbx = [p for p in pbx if not any(part in EXCLUDE_DIRS for part in p.parts)]
    info = {"pbxproj": [str(p) for p in pbx], "marketing_version": None,
            "current_project_version": None, "plist_short_version": None}
    for p in pbx:
        text = load_text(p) or ""
        m = re.search(r"MARKETING_VERSION = ([^;]+);", text)
        if m:
            info["marketing_version"] = m.group(1).strip()
        m = re.search(r"CURRENT_PROJECT_VERSION = ([^;]+);", text)
        if m:
            info["current_project_version"] = m.group(1).strip()
    for keys in plist_keys.values():
        v = keys.get("CFBundleShortVersionString")
        if isinstance(v, str):
            info["plist_short_version"] = v
    return info


def check_export_compliance(plist_keys):
    for path, keys in plist_keys.items():
        if "ITSAppUsesNonExemptEncryption" in keys:
            return {"declared": True, "value": keys["ITSAppUsesNonExemptEncryption"],
                    "file": path}
    return {"declared": False}


def check_app_store_ids(files, root: Path):
    ids = {}
    for p, t in files:
        for m in APP_STORE_ID_URL_RE.finditer(t):
            sid = next(g for g in m.groups() if g)
            ids.setdefault(sid, set()).add(str(p))
    for pattern in CI_FILE_GLOBS + ("fastlane/Appfile", "**/*.env*", "**/*.yaml",
                                    "**/*.yml"):
        for f in root.glob(pattern):
            if any(part in EXCLUDE_DIRS for part in f.parts) or not f.is_file():
                continue
            text = load_text(f) or ""
            for m in APP_STORE_ID_CONFIG_RE.finditer(text):
                ids.setdefault(m.group(1), set()).add(str(f))
    return {sid: sorted(v)[:5] for sid, v in ids.items()}


def check_healthkit(files, root: Path, plist_keys):
    uses_hk = any(re.search(r"HKHealthStore|health_kit|react-native-health", t)
                  for _, t in files)
    entitled = False
    for e in root.rglob("*.entitlements"):
        if "com.apple.developer.healthkit" in (load_text(e) or ""):
            entitled = True
    if not uses_hk and not entitled:
        return None
    has_strings = any(
        isinstance(k.get("NSHealthShareUsageDescription"), str) or
        isinstance(k.get("NSHealthUpdateUsageDescription"), str)
        for k in plist_keys.values())
    return {"uses_healthkit_api": uses_hk, "entitlement_present": entitled,
            "purpose_strings_present": has_strings}


def collect_metadata_urls(root: Path):
    urls = set()
    candidates = list(root.rglob("description.txt")) + \
        list(root.rglob("support_url.txt")) + list(root.rglob("privacy_url.txt")) + \
        [p for p in root.glob("docs/*.md")] + [p for p in root.glob("*.md")]
    for f in candidates:
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        for m in SUPPORT_URL_RE.finditer(load_text(f) or ""):
            u = m.group(0).rstrip(".,;:)`*_")
            if "example" in u or "apple.com/legal" in u:
                continue
            urls.add(u)
    return sorted(urls)[:20]


def check_urls_live(urls):
    import urllib.request
    import urllib.error
    results = []
    for u in urls:
        try:
            req = urllib.request.Request(u, method="HEAD",
                                         headers={"User-Agent": "app-store-audit/2"})
            with urllib.request.urlopen(req, timeout=8) as r:
                results.append({"url": u, "status": r.status})
        except urllib.error.HTTPError as e:
            if e.code in (403, 405):
                # Some hosts refuse HEAD; a GET that answers is still live.
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "app-store-audit/2"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        results.append({"url": u, "status": r.status})
                        continue
                except Exception as e2:  # noqa: BLE001
                    results.append({"url": u, "status": None, "error": str(e2)[:80]})
                    continue
            results.append({"url": u, "status": e.code})
        except Exception as e:  # noqa: BLE001
            results.append({"url": u, "status": None, "error": str(e)[:80]})
    return results


def build_report(root: Path, check_urls: bool = False):
    root = Path(root).resolve()
    files = gather_source_files(root)
    plists = find_info_plists(root)
    plist_keys = {str(p): load_plist_keys(p) for p in plists}

    placeholder_findings, todo_count = check_placeholders(
        [(p, t) for p, t in files if is_shipped_path(p)])
    missing_permissions = check_permissions(files, plist_keys)
    has_social, has_apple = check_sign_in_with_apple(files)
    has_signup, has_delete = check_account_deletion(files)
    webview_info = check_webview_ratio(files)
    iap_info = check_iap_and_policy(files, root)
    ai_info = check_ai_consent(files)
    rra_info = check_required_reason_apis(files, root, plists)
    sdk_info = check_sdk_manifests(root)
    paywall_info = check_paywall_elements(files, iap_info["has_iap"])
    xplat_hits = check_cross_platform_mentions(files)
    ci_hits = check_ci_xcode_pin(root)
    version_info = check_version_keys(root, plist_keys)
    export_info = check_export_compliance(plist_keys)
    app_ids = check_app_store_ids(files, root)
    hk_info = check_healthkit(files, root, plist_keys)
    metadata_urls = collect_metadata_urls(root)
    url_results = check_urls_live(metadata_urls) if (check_urls and metadata_urls) else None

    checks = []

    checks.append({
        "id": "placeholder_content",
        "guideline": "2.1",
        "status": "FAIL" if placeholder_findings else "PASS",
        "summary": (
            f"{len(placeholder_findings)} high-severity placeholder marker(s) found"
            if placeholder_findings else "No obvious placeholder content found"
        ),
        "detail": placeholder_findings[:20],
        "note": (f"{todo_count} TODO/FIXME/XXX marker(s) also found — advisory "
                 "only, verify none are reachable as shipped UI text."
                 if todo_count else None),
    })

    checks.append({
        "id": "info_plist_found",
        "guideline": "5.1.1",
        "status": "PASS" if plists else "WARN",
        "summary": (f"{len(plists)} Info.plist file(s) found"
                    if plists else "No Info.plist found in project tree — "
                    "expected for a native iOS target"),
    })

    checks.append({
        "id": "permission_usage_strings",
        "guideline": "5.1.1",
        "status": "FAIL" if missing_permissions else "PASS",
        "summary": (
            f"{len(missing_permissions)} permission(s) used in code without a "
            "matching non-empty Info.plist usage-description string"
            if missing_permissions else
            "All detected permission APIs have a matching Info.plist usage string"
        ),
        "detail": missing_permissions,
    })

    if has_social:
        checks.append({
            "id": "sign_in_with_apple",
            "guideline": "4.8",
            "status": "PASS" if has_apple else "FAIL",
            "summary": (
                "Third-party social login detected and Sign in with Apple "
                "also detected" if has_apple else
                "Third-party social login (Google/Facebook/etc.) detected "
                "WITHOUT Sign in with Apple — required by Guideline 4.8"
            ),
        })
    else:
        checks.append({
            "id": "sign_in_with_apple",
            "guideline": "4.8",
            "status": "PASS",
            "summary": "No third-party social login detected — Sign in with "
                       "Apple not required",
        })

    if has_signup:
        checks.append({
            "id": "account_deletion",
            "guideline": "5.1.1(v)",
            "status": "PASS" if has_delete else "FAIL",
            "summary": (
                "Account creation and account deletion markers both found"
                if has_delete else
                "Account creation markers found but no account deletion "
                "markers detected — required if the app supports sign-up"
            ),
        })
    else:
        checks.append({
            "id": "account_deletion",
            "guideline": "5.1.1(v)",
            "status": "PASS",
            "summary": "No account-creation markers detected — account "
                       "deletion requirement likely not applicable",
        })

    if webview_info:
        ratio = webview_info["ratio"]
        status = "WARN" if ratio > 0.3 else "PASS"
        checks.append({
            "id": "webview_ratio",
            "guideline": "4.2",
            "status": status,
            "summary": (
                f"{webview_info['webview_files']}/{webview_info['total_ui_files']} "
                f"UI-ish source files reference a webview component "
                f"(ratio {ratio}). "
                + ("This is advisory, not a guarantee of a 4.2 rejection — "
                   "review references/app-completeness-and-design.md."
                   if status == "WARN" else "")
            ),
            "detail": webview_info,
        })

    if iap_info["has_iap"]:
        # 3.1.2 has TWO distinct requirements that get conflated constantly:
        #   (1) in-app: links reachable from the subscription screen itself
        #       (checked from source). NOT safely autofixable — needs real UI.
        #   (2) metadata: links in the App Store Connect description
        #       (checked from a metadata/description file). Safely autofixable.
        inapp_ok = iap_info["has_policy_link"] and iap_info["has_eula_link"]
        checks.append({
            "id": "iap_inapp_policy_eula_links",
            "guideline": "3.1.2 (in-app)",
            "status": "PASS" if inapp_ok else "FAIL",
            "summary": (
                "IAP/subscription SDK detected; Privacy Policy and Terms of "
                "Use links with a URL both found in app source"
                if inapp_ok else
                "IAP/subscription SDK detected but a Privacy Policy and/or "
                "Terms of Use (EULA) link with an actual URL was not found in "
                "app source — these must be reachable from the in-app "
                "subscription screen. This is app-specific UI work; autofix "
                "will NOT fake it for you."
            ),
            "detail": iap_info,
        })
        meta_ok = iap_info.get("has_eula_in_metadata", False)
        checks.append({
            "id": "iap_metadata_eula_link",
            "guideline": "3.1.2 (metadata)",
            "status": "PASS" if meta_ok else "FAIL",
            "summary": (
                "Terms of Use (EULA) link found in App Store metadata "
                "description" if meta_ok else
                "No Terms of Use (EULA) link found in an App Store metadata "
                "description file — required in App Store Connect metadata. "
                "This one IS safe-autofixable (standard Apple EULA)."
            ),
        })
    else:
        checks.append({
            "id": "iap_inapp_policy_eula_links",
            "guideline": "3.1.2 (in-app)",
            "status": "PASS",
            "summary": "No IAP/subscription SDK detected",
        })

    if not iap_info["has_iap"]:
        checks.append({
            "id": "privacy_policy_present",
            "guideline": "5.1.1",
            "status": "PASS" if iap_info["has_policy_mention_anywhere"] else "WARN",
            "summary": (
                "Privacy Policy mentioned somewhere in source"
                if iap_info["has_policy_mention_anywhere"] else
                "No mention of a Privacy Policy found anywhere in source — "
                "verify one exists and is linked in-app and in App Store "
                "Connect metadata if the app collects any personal data"
            ),
        })

    # ---- 5.1.2(i) third-party AI consent ----
    if not ai_info["vendors_detected"]:
        checks.append({
            "id": "ai_consent_gate", "guideline": "5.1.2(i)", "status": "PASS",
            "summary": "No third-party AI endpoint or SDK detected in client "
                       "or backend code",
        })
    else:
        vendors = ", ".join(ai_info["vendors_detected"])
        if not ai_info["consent_evidence"]:
            status = "FAIL"
            summary = (f"User data reaches {vendors} but no shipped screen names "
                       "a vendor next to a consent control. 5.1.2(i) requires: "
                       "what data, who receives it (legal entity), explicit "
                       "permission BEFORE the first send, and a matching "
                       "privacy policy.")
        elif ai_info["seen_flag_trap"]:
            status = "WARN"
            summary = (f"Consent wording names a vendor, but the gate is also "
                       "conditioned on a 'seen/shown/first-launch' flag — the "
                       "documented repeat-rejection trap. Gate on the consent "
                       "value alone.")
        else:
            status = "PASS"
            named = set(v.lower() for v in ai_info["vendors_named_in_ui"])
            unnamed = [v for v in ai_info["vendors_detected"]
                       if not any(v.split(" ")[0].lower() in n for n in named)]
            if unnamed:
                status = "WARN"
                summary = (f"Consent wording found, but these detected vendors "
                           f"are never named in shipped UI text: "
                           f"{', '.join(unnamed)}. Every recipient must be "
                           "identified.")
            else:
                summary = (f"Consent wording names {vendors}; verify it appears "
                           "before the first transmission and matches the "
                           "privacy policy and App Privacy labels.")
        checks.append({
            "id": "ai_consent_gate", "guideline": "5.1.2(i)", "status": status,
            "summary": summary, "detail": ai_info,
        })

    # ---- ITMS-91053 required-reason APIs ----
    if rra_info is not None:
        if not rra_info["manifests_found"] and rra_info["categories_used"]:
            status = "FAIL"
            summary = ("Required-reason APIs used in native code "
                       f"({', '.join(c.split('Category')[-1] for c in rra_info['categories_used'])}) "
                       "but no PrivacyInfo.xcprivacy exists — App Store Connect "
                       "rejects the upload (ITMS-91053).")
        elif rra_info["missing"]:
            status = "FAIL"
            summary = (f"{len(rra_info['missing'])} required-reason API "
                       "category(ies) used without a PrivacyInfo.xcprivacy "
                       "entry: " + ", ".join(
                           m["category"].split("Category")[-1] for m in rra_info["missing"]))
        elif not rra_info["manifests_found"]:
            status = "WARN"
            summary = ("No PrivacyInfo.xcprivacy in the tree. None of the "
                       "scanned native files use a required-reason API "
                       "directly, but every third-party SDK and Capacitor/"
                       "RN plugin does — ship a manifest anyway.")
        else:
            status = "PASS"
            summary = ("Every required-reason API category used in native code "
                       "is declared in PrivacyInfo.xcprivacy")
        entry = {
            "id": "required_reason_apis", "guideline": "ITMS-91053",
            "status": status, "summary": summary, "detail": rra_info,
        }
        if status == "WARN":
            # Advice, not a verified upload block: nothing in the app's own
            # code needs a reason, so do not count it against HARD BLOCK.
            entry["severity"] = "RISK FLAG"
        checks.append(entry)

    # ---- ITMS-91061 SDK manifests ----
    if sdk_info is not None and sdk_info["listed_sdks_found"]:
        unseen = [e["sdk"] for e in sdk_info["listed_sdks_found"]
                  if not e["manifest_visible_in_checkout"]]
        checks.append({
            "id": "sdk_manifests", "guideline": "ITMS-91061",
            "status": "WARN" if unseen else "PASS",
            "summary": (
                f"{len(sdk_info['listed_sdks_found'])} dependency(ies) on Apple's "
                "privacy-manifest list; no bundled manifest visible in this "
                f"checkout for: {', '.join(unseen)}. Usually fine (SPM/Pods "
                "checkouts are not committed) — confirm each SDK version ships "
                "PrivacyInfo.xcprivacy."
                if unseen else
                "Every listed SDK has a visible privacy manifest"),
            "detail": sdk_info,
        })

    # ---- 3.1.2 paywall elements + hardcoded prices ----
    if paywall_info is not None:
        if not paywall_info["paywall_files"]:
            checks.append({
                "id": "paywall_elements", "guideline": "3.1.2", "status": "WARN",
                "summary": "IAP SDK detected but no file looks like a paywall "
                           "(name matching paywall/premium/upgrade/subscri…). "
                           "Check the seven elements by hand.",
            })
        else:
            missing = paywall_info["elements_missing"]
            checks.append({
                "id": "paywall_elements", "guideline": "3.1.2",
                "status": "FAIL" if missing else "PASS",
                "summary": (
                    "Paywall files lack: " + ", ".join(missing) +
                    ". All seven elements must be on the paywall itself "
                    "(title, duration, full renewal price, what you get, "
                    "Privacy Policy link, Terms link, Restore Purchases)."
                    if missing else
                    "Restore, Terms, Privacy, duration and auto-renew wording "
                    "all found in paywall files — verify prominence by eye"),
                "detail": {k: v for k, v in paywall_info.items()
                           if k != "hardcoded_prices"},
            })
        prices = paywall_info["hardcoded_prices"]
        checks.append({
            "id": "hardcoded_prices", "guideline": "3.1.2",
            "status": "WARN" if prices else "PASS",
            "summary": (
                f"{len(prices)} literal price string(s) in UI/i18n text. "
                "Prices must come from StoreKit / RevenueCat at runtime; a "
                "literal is the wrong currency in most storefronts."
                if prices else "No literal price strings in UI/i18n text"),
            "detail": prices,
        })

    # ---- 2.3.10 / 3.1.3 cross-platform mentions ----
    ungated = [h for h in xplat_hits if h["gated"] is not True]
    checks.append({
        "id": "cross_platform_mentions", "guideline": "2.3.10 / 3.1.3",
        "status": "WARN" if ungated else "PASS",
        "summary": (
            f"{len(xplat_hits)} mention(s) of another platform or payment "
            f"processor in shipped text, {len(ungated)} with no platform "
            "guard in the same file. On iOS the user must not see 'Google "
            "Play', 'Android' or a cheaper web path."
            if ungated else
            ("All other-platform mentions sit in files with a platform guard"
             if xplat_hits else "No other-platform mentions in shipped text")),
        "detail": xplat_hits,
    })

    # ---- CI Xcode pin ----
    checks.append({
        "id": "ci_xcode_pin", "guideline": "SDK minimum",
        "status": "WARN" if ci_hits else "PASS",
        "summary": (
            "CI builds against a floating Xcode ('latest'/'edge'/macos-latest). "
            "Pin the version explicitly; Apple's SDK minimum moves every April."
            if ci_hits else "No floating Xcode pin found in CI config"),
        "detail": ci_hits or None,
    })

    # ---- Version keys / export compliance (native tree only) ----
    if plists:
        vk_missing = [k for k in ("marketing_version", "current_project_version")
                      if not version_info.get(k)] if version_info["pbxproj"] else []
        checks.append({
            "id": "version_keys", "guideline": "Upload",
            "status": "WARN" if vk_missing else "PASS",
            "summary": (
                "project.pbxproj lacks " + ", ".join(vk_missing).upper() +
                " — App Store Connect needs both, and each upload must "
                "increase the build number."
                if vk_missing else
                f"MARKETING_VERSION={version_info.get('marketing_version')} "
                f"CURRENT_PROJECT_VERSION={version_info.get('current_project_version')}"
                " — confirm the marketing version matches the release you are "
                "shipping (CI usually bumps only the build number)"),
            "detail": version_info,
        })
        checks.append({
            "id": "export_compliance", "guideline": "Export compliance",
            "status": "PASS" if export_info["declared"] else "WARN",
            "summary": (
                f"ITSAppUsesNonExemptEncryption = {export_info.get('value')}"
                if export_info["declared"] else
                "ITSAppUsesNonExemptEncryption not in Info.plist — every "
                "TestFlight build will show 'Missing Compliance' until answered "
                "by hand. Safe-autofixable to false when only HTTPS is used."),
            "detail": export_info,
        })

    # ---- App Store id consistency ----
    if len(app_ids) > 1:
        checks.append({
            "id": "app_store_id_consistency", "guideline": "2.1",
            "status": "FAIL",
            "summary": (f"{len(app_ids)} different App Store ids referenced: "
                        + ", ".join(sorted(app_ids)) +
                        ". One of them opens the wrong listing."),
            "detail": app_ids,
        })
    elif app_ids:
        checks.append({
            "id": "app_store_id_consistency", "guideline": "2.1",
            "status": "PASS",
            "summary": f"One App Store id referenced ({next(iter(app_ids))})",
            "detail": app_ids,
        })

    # ---- Support / privacy / terms URLs ----
    if url_results is not None:
        dead = [r for r in url_results if not (r.get("status") and 200 <= r["status"] < 400)]
        checks.append({
            "id": "support_privacy_urls", "guideline": "1.5 / 5.1.1(i)",
            "status": "FAIL" if dead else "PASS",
            "summary": (f"{len(dead)} of {len(url_results)} support/privacy/terms "
                        "URL(s) found in docs/metadata did not answer 2xx/3xx"
                        if dead else
                        f"All {len(url_results)} support/privacy/terms URL(s) answered"),
            "detail": url_results,
        })
    elif metadata_urls:
        checks.append({
            "id": "support_privacy_urls", "guideline": "1.5 / 5.1.1(i)",
            "status": "WARN",
            "summary": (f"{len(metadata_urls)} support/privacy/terms URL(s) found "
                        "in docs/metadata; not checked (run with --check-urls). "
                        "Reviewers open every one."),
            "detail": metadata_urls,
        })

    # ---- HealthKit ----
    if hk_info is not None:
        ok = hk_info["purpose_strings_present"]
        checks.append({
            "id": "healthkit_transparency", "guideline": "2.5.1 / 5.1.3",
            "status": "PASS" if ok else "FAIL",
            "summary": ("HealthKit in use with purpose strings present — "
                        "confirm the privacy policy names the data types"
                        if ok else
                        "HealthKit API or entitlement present without "
                        "NSHealthShare/UpdateUsageDescription"),
            "detail": hk_info,
        })

    for c in checks:
        c.setdefault("severity", SEVERITY.get(c["id"], "RISK FLAG"))

    return {
        "project": str(root),
        "files_scanned": len(files),
        "info_plists_found": [str(p) for p in plists],
        "checks": checks,
        "counts": {
            sev: sum(1 for c in checks
                     if c["severity"] == sev and c["status"] != "PASS")
            for sev in SEVERITY_ORDER
        },
        "cannot_be_automated": [
            "Crash-free launch and navigation on a real device (multiple "
            "iOS versions / device sizes)",
            "App Store Connect screenshots, description, and age rating "
            "accuracy",
            "Whether the app is a near-duplicate of existing templated apps "
            "(Guideline 4.3 spam)",
            "Demo/reviewer account credentials actually working today, and "
            "not gated behind SMS/authenticator 2FA",
            "Whether a subscription provides genuine 'dynamic, ongoing "
            "value' vs. a one-time unlock (Guideline 3.1.2)",
            "Whether the billed subscription price is visually as prominent "
            "as free-trial messaging",
            "App Privacy ('Nutrition Label') questionnaire accuracy in App "
            "Store Connect, including third-party SDK data collection",
            "Third-party SDK privacy manifest currency",
            "AI data-sharing consent screen, if the app calls an external "
            "LLM API",
            "App Review Notes briefing the reviewer on non-obvious flows",
        ],
    }


def render_markdown(report):
    lines = []
    lines.append(f"# App Store Rejection Audit — {report['project']}")
    lines.append("")
    lines.append(f"Files scanned: {report['files_scanned']}")
    lines.append(f"Info.plist found: {len(report['info_plists_found'])}")
    lines.append("")
    counts = report.get("counts", {})
    lines.append("Open findings: " + " · ".join(
        f"{counts.get(s, 0)} {s}" for s in SEVERITY_ORDER))
    lines.append("")
    lines.append("| Status | Severity | Guideline | Check | Summary |")
    lines.append("|---|---|---|---|---|")
    for c in report["checks"]:
        icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[c["status"]]
        lines.append(f"| {icon} | {c.get('severity', '')} | {c['guideline']} | "
                     f"{c['id']} | {c['summary']} |")
    lines.append("")
    for c in report["checks"]:
        if c.get("detail"):
            lines.append(f"### {c['id']} — detail")
            lines.append("```")
            lines.append(json.dumps(c["detail"], indent=2)[:3000])
            lines.append("```")
        if c.get("note"):
            lines.append(f"> {c['note']}")
    lines.append("")
    lines.append("## Can't be automated — check these manually")
    for item in report["cannot_be_automated"]:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _evidence_lines(detail, limit=6, project_root=""):
    """Turn a check's detail blob into a few `file:line` evidence lines,
    repo-relative so the report reads the same on every machine."""
    out = []
    items = []

    def rel(path):
        p = str(path)
        if project_root and p.startswith(project_root):
            p = p[len(project_root):].lstrip("\\/")
        return p.replace("\\", "/")

    def not_admin(it):
        return not re.search(r"/admin[-_/]", rel(it.get("file", "")) if isinstance(it, dict) else "")
    if isinstance(detail, list):
        items = detail
    elif isinstance(detail, dict):
        for key in ("endpoint_hits", "sdk_hits", "seen_flag_trap", "missing",
                    "hardcoded_prices", "listed_sdks_found", "evidence"):
            v = detail.get(key)
            if isinstance(v, list) and v:
                items = v
                break
        if not items and detail and all(isinstance(v, list) for v in detail.values()):
            for k, v in detail.items():
                out.append(f"`{k}` → " + ", ".join(rel(x) for x in v[:3]))
            return out[:limit]
    # Admin/back-office call sites are real but not what a reviewer meets;
    # list user-facing evidence first.
    items = sorted(items, key=lambda it: 0 if not_admin(it) else 1)
    for it in items[:limit]:
        if isinstance(it, dict):
            if it.get("file"):
                loc = f"`{rel(it['file'])}`" + (f":{it['line']}" if it.get("line") else "")
                extra = it.get("snippet") or it.get("match") or it.get("price") or ""
                out.append(f"{loc} — {extra[:110]}" if extra else loc)
            elif it.get("category"):
                ev = it.get("evidence") or []
                first = ev[0] if ev else {}
                out.append(f"`{it['category']}` — approved reasons "
                           f"{', '.join(it.get('approved_reasons', []))}"
                           + (f"; e.g. `{first.get('file')}`:{first.get('line')}" if first else ""))
            elif it.get("sdk"):
                out.append(f"{it['sdk']} — declared in {', '.join(rel(x) for x in it.get('declared_in', []))}")
            elif it.get("url"):
                out.append(f"{it['url']} → {it.get('status') or it.get('error')}")
        else:
            out.append(str(it))
    return out


def render_report(report, app_name=None, verified="September 2026"):
    """The APP_STORE_APPROVAL.md format: findings grouped by severity, each
    with Evidence / Why / Fix / Source, then the App Store Connect artifacts
    the code cannot see, then the manual checklist. Empty sections are kept
    and say 'None found.' — an absent heading reads as an oversight."""
    import datetime
    name = app_name or Path(report["project"]).name
    counts = report.get("counts", {})
    open_checks = [c for c in report["checks"] if c["status"] != "PASS"]
    lines = [
        f"# App Store submission audit — {name}",
        f"Audited {datetime.date.today().isoformat()} · "
        + " · ".join(f"{counts.get(s, 0)} {s}" for s in SEVERITY_ORDER),
        f"Guidelines verified {verified} — re-verify at {GUIDELINES_URL}",
        "",
        "Static scan of the repository. A FAIL means 'go look at this', not "
        "'this is definitely broken'; a clean run does not mean approval — the "
        "manual checklist at the end is not optional.",
        "",
    ]
    n = 0
    for sev in SEVERITY_ORDER:
        lines.append(f"## {sev}")
        group = [c for c in open_checks if c["severity"] == sev]
        # FAIL before WARN; within that, the order the checks were produced
        # in (cheapest fixes first is a judgment the reader makes)
        group.sort(key=lambda c: 0 if c["status"] == "FAIL" else 1)
        if not group:
            lines.append("None found.")
            lines.append("")
            continue
        for c in group:
            n += 1
            why, fix, src = CHECK_META.get(c["id"], ("", "", GUIDELINES_URL))
            lines.append(f"### {n}. {c['guideline']} — {c['id']} ({c['status']})")
            lines.append(f"**Finding:** {c['summary']}")
            ev = _evidence_lines(c.get("detail"), project_root=report["project"])
            if ev:
                lines.append("**Evidence:**")
                lines += [f"- {e}" for e in ev]
            if why:
                lines.append(f"**Why:** {why}")
            if fix:
                lines.append(f"**Fix:** {fix}")
            lines.append(f"**Source:** {src}")
            if c.get("note"):
                lines.append(f"> {c['note']}")
            lines.append("")
    by_id = {c["id"]: c for c in report["checks"]}

    def art(cid, ok_text, missing_text, unknown="Unverified — confirm in App Store Connect"):
        c = by_id.get(cid)
        if not c:
            return unknown
        return ok_text if c["status"] == "PASS" else missing_text

    lines += [
        "## SUBMISSION ARTIFACTS",
        "Things that live in App Store Connect, not in the code.",
        "",
        "| Item | Status |",
        "|---|---|",
        "| Demo credentials in App Review Information (permanent account, seeded, no 2FA; two accounts if in-app deletion exists) | Unverified — confirm before submitting |",
        f"| Terms of Use (EULA) link in the Description | {art('iap_metadata_eula_link', 'Found in a metadata description file', '**MISSING** — add to the Description (3.1.2)')} |",
        f"| Privacy Policy URL live and linked in-app | {art('support_privacy_urls', 'URLs answered', 'Check — see support_privacy_urls', 'Unverified — run with --check-urls')} |",
        "| Support URL reachable with a contact route | Unverified — open it in a private window |",
        f"| Export compliance (`ITSAppUsesNonExemptEncryption`) | {art('export_compliance', 'Declared in Info.plist', '**Not set** — TestFlight will show Missing Compliance')} |",
        "| App Privacy labels match `PrivacyInfo.xcprivacy` and the consent screen | Unverified — compare the three by hand |",
        "| Age rating questionnaire (5-tier: 4+/9+/13+/16+/18+) | Unverified |",
        "| Paid Applications agreement signed, banking and tax complete | Unverified |",
        "| App Review notes: demo account, path to the paywall, third-party data sharing, hardware needs | Unverified — see references/metadata-review.md for the template |",
        "",
        "## Manual review checklist",
    ]
    lines += [f"- [ ] {item}" for item in report["cannot_be_automated"]]
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_path", help="Path to the project root")
    parser.add_argument("--json", action="store_true",
                         help="Output machine-readable JSON instead of Markdown")
    parser.add_argument("--output", help="Write report to this file instead of stdout")
    parser.add_argument("--report", metavar="PATH",
                        help="Also write an APP_STORE_APPROVAL.md-style report "
                             "(findings by severity with Why/Fix/Source, "
                             "submission artifacts, manual checklist)")
    parser.add_argument("--app-name", help="Name used in the --report heading")
    parser.add_argument("--check-urls", action="store_true",
                        help="HEAD-request support/privacy/terms URLs found in "
                             "docs and metadata (needs network; off by default)")
    args = parser.parse_args()

    root = Path(args.project_path).resolve()
    if not root.exists():
        print(f"Error: path not found: {root}", file=sys.stderr)
        sys.exit(1)

    report = build_report(root, check_urls=args.check_urls)
    output = json.dumps(report, indent=2) if args.json else render_markdown(report)

    if args.report:
        Path(args.report).write_text(render_report(report, args.app_name),
                                     encoding="utf-8")
        print(f"Report written to {args.report}")
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    elif not args.report:
        print(output)

    fail_count = sum(1 for c in report["checks"] if c["status"] == "FAIL")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
