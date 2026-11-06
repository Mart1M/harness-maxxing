# Harness for iOS

A small native app (SwiftUI + `WKWebView`) that opens your Harness server full screen. It exists so you can install
Harness from **TestFlight** like any app: a PWA cannot be uploaded to App Store Connect, a native app that shows it can.

- First launch: you enter the address of your server (`harness.example.com`), then sign in as usual.
- The session cookie is kept between launches. Links to other sites open in Safari.
- Voice messages (microphone), camera and photo pickers, file downloads (share sheet: Save to Files, AirDrop...) work.
- iOS 16 or later, iPhone and iPad. No third-party dependency.
- **Forget the server**: iOS Settings -> Harness -> turn on "Forget the server", reopen the app. The error screen has a
  "Change server" button as well.
- Not included: native push notifications (the web push of the PWA does not run in a web view), offline mode.

## Run it in the simulator

```bash
cd ios
xcodebuild -project Harness.xcodeproj -scheme Harness -sdk iphonesimulator \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
xcrun simctl boot "iPhone 15 Pro" 2>/dev/null; open -a Simulator
xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/Harness.app
xcrun simctl launch booted com.example.harnessmaxxing
```

Or open `Harness.xcodeproj` in Xcode and press Run. An HTTP address is accepted only on a local network
(`localhost`, `192.168.x.x`, `10.x.x.x`, `.local`); anything else must be HTTPS.

## Put it on your iPhone with TestFlight

You need an Apple Developer Program membership (99 USD/year) and Xcode 15 or later on a Mac.

1. **Bundle identifier.** In Xcode, open the project, select the *Harness* target -> *Signing & Capabilities*.
   Replace `com.example.harnessmaxxing` with an identifier of yours (`com.yourname.harness`) and pick your *Team*.
   Automatic signing creates the certificates and the App ID.
2. **App record.** On [App Store Connect](https://appstoreconnect.apple.com) -> *Apps* -> *+* -> *New App*: iOS, any
   name, the same bundle identifier, any SKU.
3. **Archive.** In Xcode choose *Any iOS Device (arm64)* as destination, then *Product -> Archive*.
4. **Upload.** In the Organizer window select the archive -> *Distribute App* -> *App Store Connect* -> *Upload*.
   Processing takes a few minutes; an email tells you when the build is ready.
5. **Test.** In App Store Connect -> your app -> *TestFlight*: add yourself under *Internal Testing* (people of your
   team, up to 100: no Apple review, the build is available as soon as it is processed). Install the **TestFlight** app
   on your iPhone, accept the invitation, install Harness.
   External testers (a public link, up to 10 000) need a short Beta App Review.

For the next versions raise *Build* (target -> General -> Identity; or `CURRENT_PROJECT_VERSION`) before each archive:
App Store Connect refuses a build number it has already seen.

## Notes

- `ITSAppUsesNonExemptEncryption` is `false` (the app only uses the system's HTTPS), so no export-compliance question.
- The app only grants the camera / microphone to the server address you entered; links to another host are opened in
  Safari, never inside the app.
- A build for the App Store itself (public release) may be refused by Apple as a simple web wrapper (guideline 4.2);
  TestFlight internal testing is not affected.
- The icon is the PWA icon; replace `Harness/Assets.xcassets/AppIcon.appiconset/icon-1024.png` (1024x1024, no
  transparency) with a final one.
