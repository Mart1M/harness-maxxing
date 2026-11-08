import ActivityKit
import SwiftUI
import WidgetKit

@main
struct HarnessLiveActivities: WidgetBundle {
    var body: some Widget {
        if #available(iOS 16.1, *) {
            HarnessSessionsLiveActivity()
        }
    }
}

@available(iOS 16.1, *)
struct HarnessSessionsLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: HarnessActivityAttributes.self) { context in
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Label("WuitBot", systemImage: "bolt.fill")
                        .font(.headline)
                    Spacer()
                    Text(sessionCount(context.state.runningSessions))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                Text(context.state.primaryTitle)
                    .font(.subheadline)
                    .lineLimit(1)
                if context.state.queuedMessages > 0 {
                    Text(queueCount(context.state.queuedMessages))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
            .activityBackgroundTint(Color.black.opacity(0.85))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "bolt.fill")
                        .foregroundStyle(.yellow)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(sessionCount(context.state.runningSessions))
                        .font(.caption.weight(.semibold))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.state.primaryTitle).lineLimit(1)
                        if context.state.queuedMessages > 0 {
                            Text(queueCount(context.state.queuedMessages))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            } compactLeading: {
                Image(systemName: "bolt.fill").foregroundStyle(.yellow)
            } compactTrailing: {
                Text("\(context.state.runningSessions)")
            } minimal: {
                Image(systemName: "bolt.fill").foregroundStyle(.yellow)
            }
        }
    }

    private func sessionCount(_ count: Int) -> String {
        count == 1 ? "1 session active" : "\(count) sessions actives"
    }

    private func queueCount(_ count: Int) -> String {
        count == 1 ? "1 message en attente" : "\(count) messages en attente"
    }
}
