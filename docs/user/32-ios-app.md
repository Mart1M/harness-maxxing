---
section: Using Harness Maxxing
---
# iPhone app: WuitBot (TestFlight)

Harness is a web app you can add to the Home Screen (Share -> Add to Home Screen). If you prefer a real app installed
from **TestFlight**, the repository holds a small iOS app, `ios/`, that opens your server full screen: you enter the
address of your Harness once, sign in, and the session is kept.

It shows the same interface, with the microphone for voice messages, photos, camera and file downloads (Save to Files,
AirDrop). Links to other sites open in Safari. Push notifications work too, even when the app is closed: see
[Notifications on the iPhone](33-notifications).

Building and sending it to TestFlight takes about 20 minutes and an Apple Developer account (99 USD/year); the steps
are in `ios/README.md` in the repository: set your bundle identifier and team in Xcode, create the app on App Store
Connect, *Product -> Archive*, upload, then install it on your iPhone with the TestFlight app.

To use another server later: iOS Settings -> Harness -> **Forget the server**, then reopen the app. (iOS lists the app as WuitBot in Settings.)
