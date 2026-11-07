import SwiftUI
import UIKit
import WebKit

/// Loading state shared between the web view and the SwiftUI overlay.
final class WebModel: ObservableObject {
    @Published var progress: Double = 0
    @Published var error: String?
    weak var webView: WKWebView?

    func reload() {
        error = nil
        if webView?.url == nil, let start = startURL { webView?.load(URLRequest(url: start)) } else { webView?.reload() }
    }

    var startURL: URL?
}

/// Full-screen web app (under the status bar and the home indicator: the page handles the safe areas itself,
/// Harness sets viewport-fit=cover) with an error screen when the server cannot be reached.
struct WebScreen: View {
    let url: URL
    @EnvironmentObject private var server: ServerConfig
    @StateObject private var model = WebModel()
    @ObservedObject private var push = PushCenter.shared

    var body: some View {
        ZStack(alignment: .top) {
            Color(uiColor: .systemBackground).ignoresSafeArea()
            HarnessWebView(url: url, model: model)
                .ignoresSafeArea()
            if model.progress > 0 && model.progress < 1 {
                ProgressView(value: model.progress)
                    .progressViewStyle(.linear)
                    .tint(.accentColor)
                    .allowsHitTesting(false)
            }
            if let message = model.error {
                ErrorScreen(host: url.host ?? url.absoluteString, message: message,
                            retry: { model.reload() }, change: { server.forget() })
            }
        }
        .onAppear {
            push.start()
            openPending()
        }
        .onChange(of: push.pendingPath) { _ in openPending() }
    }

    /// A tap on a notification: open the page it carries inside the server.
    private func openPending() {
        guard let path = push.pendingPath, let target = URL(string: path, relativeTo: url)?.absoluteURL,
              target.host?.lowercased() == url.host?.lowercased() else { return }
        push.pendingPath = nil
        model.webView?.load(URLRequest(url: target))
    }
}

struct ErrorScreen: View {
    let host: String
    let message: String
    let retry: () -> Void
    let change: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 36))
                .foregroundStyle(.secondary)
            Text("Cannot reach \(host)")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Try again", action: retry)
                .buttonStyle(.borderedProminent)
            Button("Change server", role: .destructive, action: change)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .systemBackground))
    }
}

struct HarnessWebView: UIViewRepresentable {
    let url: URL
    let model: WebModel

    func makeCoordinator() -> Coordinator { Coordinator(url: url, model: model) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()                   // the session cookie survives launches
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        config.applicationNameForUserAgent = "HarnessiOS/1.0"  // the server can tell the app from Safari
        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = context.coordinator
        web.uiDelegate = context.coordinator
        web.allowsBackForwardNavigationGestures = true
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.isOpaque = false
        web.backgroundColor = .systemBackground
        web.scrollView.backgroundColor = .systemBackground
        #if DEBUG
        if #available(iOS 16.4, *) { web.isInspectable = true }
        #endif
        context.coordinator.observe(web)
        model.webView = web
        PushCenter.shared.webView = web
        model.startURL = url
        web.load(URLRequest(url: url))
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
        let origin: URL
        let model: WebModel
        private var progressObservation: NSKeyValueObservation?
        private var downloads: [ObjectIdentifier: URL] = [:]

        init(url: URL, model: WebModel) {
            origin = url
            self.model = model
        }

        func observe(_ web: WKWebView) {
            progressObservation = web.observe(\.estimatedProgress, options: [.new]) { [weak self] web, _ in
                DispatchQueue.main.async { self?.model.progress = web.isLoading ? web.estimatedProgress : 1 }
            }
        }

        private func sameHost(_ url: URL?) -> Bool {
            url?.host?.lowercased() == origin.host?.lowercased()
        }

        // MARK: navigation

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { return decisionHandler(.cancel) }
            if action.shouldPerformDownload { return decisionHandler(.download) }
            let scheme = url.scheme?.lowercased() ?? ""
            if ["about", "blob", "data"].contains(scheme) { return decisionHandler(.allow) }
            if scheme != "http" && scheme != "https" {                         // mailto:, tel:, ...
                if action.navigationType == .linkActivated { UIApplication.shared.open(url) }
                return decisionHandler(.cancel)
            }
            if action.targetFrame?.isMainFrame != false, !sameHost(url), action.navigationType == .linkActivated {
                UIApplication.shared.open(url)                                  // another site: Safari
                return decisionHandler(.cancel)
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                     decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            if !response.canShowMIMEType { return decisionHandler(.download) }
            if let http = response.response as? HTTPURLResponse,
               let disposition = http.value(forHTTPHeaderField: "Content-Disposition"),
               disposition.lowercased().hasPrefix("attachment") {
                return decisionHandler(.download)
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            model.error = nil
            model.progress = 1
            PushCenter.shared.publish()
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            fail(error)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            fail(error)
        }

        private func fail(_ error: Error) {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled { return }
            model.error = ns.localizedDescription
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            webView.reload()                                                   // iOS reclaimed the page's memory
        }

        // MARK: window.open / target=_blank, JavaScript dialogs, camera and microphone

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            guard let url = action.request.url else { return nil }
            if sameHost(url) { webView.load(action.request) } else { UIApplication.shared.open(url) }
            return nil
        }

        func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                     decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(origin.host.lowercased() == self.origin.host?.lowercased() ? .grant : .deny)
        }

        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            present(message: message, ok: "OK", cancel: nil) { _ in completionHandler() }
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            present(message: message, ok: "OK", cancel: "Cancel") { completionHandler($0 != nil) }
        }

        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
            present(message: prompt, ok: "OK", cancel: "Cancel", field: defaultText ?? "") { completionHandler($0) }
        }

        /// Calls `done` with the text of the field ("" without one) on OK, nil on Cancel.
        private func present(message: String, ok: String, cancel: String?, field: String? = nil,
                             done: @escaping (String?) -> Void) {
            guard let top = Self.topViewController() else { return done(cancel == nil ? "" : nil) }
            let alert = UIAlertController(title: origin.host, message: message, preferredStyle: .alert)
            if let field { alert.addTextField { $0.text = field } }
            if let cancel { alert.addAction(UIAlertAction(title: cancel, style: .cancel) { _ in done(nil) }) }
            alert.addAction(UIAlertAction(title: ok, style: .default) { _ in done(alert.textFields?.first?.text ?? "") })
            top.present(alert, animated: true)
        }

        static func topViewController() -> UIViewController? {
            let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive }
            var top = scene?.windows.first { $0.isKeyWindow }?.rootViewController
            while let next = top?.presentedViewController { top = next }
            return top
        }

        // MARK: downloads -> share sheet (Save to Files, AirDrop...)

        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }

        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            download.delegate = self
        }

        func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                      suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
            let name = URL(fileURLWithPath: suggestedFilename).lastPathComponent
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
            do {
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            } catch {
                return completionHandler(nil)
            }
            let destination = dir.appendingPathComponent(name.isEmpty ? "download" : name)
            downloads[ObjectIdentifier(download)] = destination
            completionHandler(destination)
        }

        func downloadDidFinish(_ download: WKDownload) {
            guard let file = downloads.removeValue(forKey: ObjectIdentifier(download)),
                  let top = Self.topViewController() else { return }
            let sheet = UIActivityViewController(activityItems: [file], applicationActivities: nil)
            sheet.popoverPresentationController?.sourceView = top.view
            sheet.popoverPresentationController?.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.maxY - 1, width: 1, height: 1)
            top.present(sheet, animated: true)
        }

        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
            downloads.removeValue(forKey: ObjectIdentifier(download))
        }
    }
}
