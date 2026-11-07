---
section: Using Harness Maxxing
---
# Notifications on the iPhone

The iPhone app ([WuitBot](32-ios-app)) can receive real push notifications, even when it is closed: an answer is
ready, a turn failed, a scheduled job ran. They go from your server to Apple (APNs) and from Apple to your phone.
Nothing passes through a third-party service.

## What you are notified about

In **Settings -> Notifications -> iPhone notifications**:

- **Finished answers**: every session, only the sessions that have *Notify* on, or never.
- **Errors**: a turn that failed, and any error event of the notifications feed.
- **Scheduled jobs**: the result of each cron run.

A tap on the notification opens that session in the app. Summaries made by compaction are never notified.

## One-time setup (about 10 minutes)

You need the Apple Developer account you already use for TestFlight.

1. On developer.apple.com -> *Certificates, Identifiers & Profiles* -> *Keys* -> **+**. Name it, tick **Apple Push
   Notifications service (APNs)**, continue, register. **Download the `.p8` file** (Apple lets you do it once) and note
   the **Key ID** shown on the page.
2. Your **Team ID** is under *Membership details*. The **bundle id** is the one of the app (for example
   `com.example.wuitbot`).
3. In Harness, Settings -> Notifications -> *Apple push key*: paste the content of the `.p8` file, the Key ID, the Team
   ID and the bundle id, then **Save**. The key stays on your server and is never shown again.
4. Install a build of the app that has push enabled (a new TestFlight build: the app needs the *Push Notifications*
   capability, which Xcode adds by itself when it signs with your account).
5. Open the app, sign in, **Allow** notifications. The iPhone appears in the list; press **Send a test**.

If the test fails, the error is shown under the device: `BadDeviceToken` means the app and the key do not belong to the
same Apple account or environment, `TopicDisallowed` that the bundle id is wrong.

## Good to know

- A build run from Xcode (debug) is registered as *Development build* and uses Apple's sandbox; TestFlight builds use
  the normal service.
- *Forget this iPhone* stops the notifications for it until the app registers again.
- The browser notifications of this page (same settings tab) are separate and only work while a tab is open.
