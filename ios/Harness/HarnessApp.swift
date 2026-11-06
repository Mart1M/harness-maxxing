import SwiftUI

@main
struct HarnessApp: App {
    @StateObject private var server = ServerConfig()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(server)
        }
    }
}

/// The setup screen until a server address is saved, then the Harness web app.
struct RootView: View {
    @EnvironmentObject private var server: ServerConfig

    var body: some View {
        if let url = server.url {
            WebScreen(url: url)
                .id(url)
        } else {
            SetupView()
        }
    }
}
