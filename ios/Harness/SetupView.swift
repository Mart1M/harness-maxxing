import SwiftUI

/// First launch: the address of your Harness server.
struct SetupView: View {
    @EnvironmentObject private var server: ServerConfig
    @State private var text = ""
    @State private var failed = false
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Spacer()
            Image(systemName: "terminal")
                .font(.system(size: 40, weight: .semibold))
                .foregroundStyle(.tint)
            Text("Harness")
                .font(.largeTitle.bold())
            Text("Enter the address of your Harness server. You sign in on the next screen, with the password you chose at setup.")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 8) {
                TextField("harness.example.com", text: $text)
                    .textContentType(.URL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.go)
                    .focused($focused)
                    .onSubmit(connect)
                    .padding(12)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                if failed {
                    Text("That does not look like a server address. Example: harness.example.com")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            Button(action: connect) {
                Text("Connect").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
            Spacer()
            Spacer()
        }
        .padding(24)
        .frame(maxWidth: 480)
        .frame(maxWidth: .infinity)
        .onAppear { focused = true }
    }

    private func connect() {
        guard let url = ServerConfig.normalize(text) else {
            failed = true
            return
        }
        failed = false
        server.save(url)
    }
}
