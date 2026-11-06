import Foundation

/// Address of the Harness server this app opens (every installation of Harness has its own).
/// Stored in UserDefaults. Settings -> Harness -> "Forget the server" (Settings.bundle) clears it on the next launch.
final class ServerConfig: ObservableObject {
    static let key = "server_url"
    static let resetKey = "reset_server"

    @Published private(set) var url: URL?

    init() {
        let defaults = UserDefaults.standard
        if defaults.bool(forKey: Self.resetKey) {
            defaults.removeObject(forKey: Self.key)
            defaults.set(false, forKey: Self.resetKey)
        }
        url = defaults.string(forKey: Self.key).flatMap(Self.normalize)
    }

    func save(_ url: URL) {
        UserDefaults.standard.set(url.absoluteString, forKey: Self.key)
        self.url = url
    }

    func forget() {
        UserDefaults.standard.removeObject(forKey: Self.key)
        url = nil
    }

    /// "harness.example.com", "https://harness.example.com/x?y" -> https://harness.example.com
    /// http is accepted only for a local network address (the app's transport security allows nothing else).
    static func normalize(_ raw: String) -> URL? {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !text.contains(" ") else { return nil }
        if !text.contains("://") { text = "https://" + text }
        guard var parts = URLComponents(string: text),
              let scheme = parts.scheme?.lowercased(), scheme == "https" || scheme == "http",
              let host = parts.host?.lowercased(), host.contains(".") || host == "localhost"
        else { return nil }
        if scheme == "http" && !isLocal(host) { return nil }
        parts.scheme = scheme
        parts.host = host
        parts.path = ""
        parts.query = nil
        parts.fragment = nil
        parts.user = nil
        parts.password = nil
        return parts.url
    }

    private static func isLocal(_ host: String) -> Bool {
        if host == "localhost" || host.hasSuffix(".local") { return true }
        let octets = host.split(separator: ".").compactMap { Int($0) }
        guard octets.count == 4, octets.allSatisfy({ (0...255).contains($0) }) else { return false }
        return octets[0] == 10 || octets[0] == 127 || (octets[0] == 192 && octets[1] == 168)
            || (octets[0] == 172 && (16...31).contains(octets[1]))
    }
}
