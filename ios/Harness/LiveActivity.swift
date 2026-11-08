import ActivityKit
import Foundation

/// The data shared by the iOS app and its WidgetKit extension. There is one activity for the Harness server, not one
/// per session: Dynamic Island has little room, while the count still tells the user when several agents are working.
@available(iOS 16.1, *)
struct HarnessActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var runningSessions: Int
        var queuedMessages: Int
        var primaryTitle: String
        var updatedAt: Date
    }

    var serverName: String
}

/// Receives a small, authenticated session summary from the page and keeps the corresponding Live Activity current.
/// The page only reports state while it is open; server-pushed Live Activity updates are deliberately not claimed here.
@MainActor
@available(iOS 16.1, *)
final class LiveActivityCenter {
    static let shared = LiveActivityCenter()

    private var activity: Activity<HarnessActivityAttributes>?

    private init() {}

    func apply(_ payload: Any, serverName: String) {
        guard let body = payload as? [String: Any],
              let running = body["running"] as? Int,
              let queued = body["queued"] as? Int,
              let title = body["title"] as? String else { return }

        let state = HarnessActivityAttributes.ContentState(
            runningSessions: max(0, running),
            queuedMessages: max(0, queued),
            primaryTitle: String(title.prefix(120)),
            updatedAt: Date()
        )

        if state.runningSessions == 0 {
            end()
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }

        if let activity {
            Task { await activity.update(using: state) }
            return
        }

        do {
            activity = try Activity.request(
                attributes: HarnessActivityAttributes(serverName: serverName),
                contentState: state,
                pushType: nil
            )
        } catch {
            NSLog("Could not start Harness Live Activity: %@", error.localizedDescription)
        }
    }

    func end() {
        guard let activity else { return }
        self.activity = nil
        Task { await activity.end(dismissalPolicy: .immediate) }
    }
}
