import SwiftUI
import UIKit
import UserNotifications
import WebKit

/// Push notifications (APNs). The app asks for permission once a server is set, registers with Apple and hands the
/// device token to the Harness page (`window.__wuitbotPush` + a `wuitbot-push` event): the signed-in page registers it
/// on the server, which keeps the cookie. A tap on a notification opens the page it carries (`path`).
final class PushCenter: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = PushCenter()

    /// A path inside the server ("/sessions/abc") to open, set by a tap on a notification.
    @Published var pendingPath: String?
    weak var webView: WKWebView?
    private var token: String?

    #if DEBUG
    private let environment = "sandbox"
    #else
    private let environment = "production"
    #endif

    override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    /// Ask for permission (the first time only) and register; called when the web app is on screen.
    func start() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            switch settings.authorizationStatus {
            case .notDetermined:
                center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
                    if granted { self.register() }
                }
            case .denied:
                break
            default:
                self.register()
            }
        }
    }

    private func register() {
        DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
    }

    func didRegister(deviceToken: Data) {
        token = deviceToken.map { String(format: "%02x", $0) }.joined()
        publish()
    }

    /// Give the token to the page (again after every load: the page is a fresh JavaScript world each time).
    func publish() {
        guard let token, let web = webView else { return }
        let info: [String: String] = ["token": token, "env": environment, "name": UIDevice.current.name]
        guard let data = try? JSONSerialization.data(withJSONObject: info),
              let json = String(data: data, encoding: .utf8) else { return }
        let script = "window.__wuitbotPush = \(json); window.dispatchEvent(new CustomEvent('wuitbot-push', { detail: window.__wuitbotPush }));"
        DispatchQueue.main.async { web.evaluateJavaScript(script, completionHandler: nil) }
    }

    // MARK: UNUserNotificationCenterDelegate

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let path = response.notification.request.content.userInfo["path"] as? String,
           path.hasPrefix("/"), !path.hasPrefix("//") {
            DispatchQueue.main.async { self.pendingPath = path }
        }
        completionHandler()
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions
                     launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        _ = PushCenter.shared                                   // the delegate must be set before the app finishes launching
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        PushCenter.shared.didRegister(deviceToken: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NSLog("Push registration failed: %@", error.localizedDescription)
    }
}
