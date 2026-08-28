import Cocoa
import CoreText

enum Settings {
    static let projectRoot = "/Users/mxpf/Code/photo-system-automation"
    static let cliPath = "\(projectRoot)/bin/photo-system"
}

func preferredFont(size: CGFloat, weight: NSFont.Weight = .regular) -> NSFont {
    let names = [
        "ABCDiatypeTrial-Regular",
        "ABCDiatypeTrial-Medium",
        "ABCDiatypeTrial-Bold",
        "ABCDiatypeTrial-Heavy",
        "Diatype",
        "ABC Diatype",
        "ABCDiatype",
        "Diatype-Regular",
        "Diatype Variable",
    ]
    for name in names {
        if let font = NSFont(name: name, size: size) {
            return font
        }
    }
    return NSFont.systemFont(ofSize: size, weight: weight)
}

func styled(_ title: String, size: CGFloat = 14, weight: NSFont.Weight = .regular) -> NSAttributedString {
    return NSAttributedString(
        string: title,
        attributes: [
            .font: preferredFont(size: size, weight: weight),
            .foregroundColor: NSColor.labelColor,
        ]
    )
}

@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!

    func applicationDidFinishLaunching(_ notification: Notification) {
        registerBundledFonts()
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "📷 Photos"
            button.font = preferredFont(size: 13, weight: .semibold)
            button.toolTip = "Photo System Automation"
        }
        rebuildMenu()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            self.alert(
                title: "Photo System is running",
                text: "Look for “📷 Photos” in the menu bar. Use it to audit now, check status, open the latest report, or change the background audit interval.",
                ok: true
            )
        }
    }

    private func registerBundledFonts() {
        guard let fontsURL = Bundle.main.resourceURL?.appendingPathComponent("Fonts") else {
            return
        }
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: fontsURL,
            includingPropertiesForKeys: nil
        ) else {
            return
        }

        for url in files where ["otf", "ttf"].contains(url.pathExtension.lowercased()) {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }

    private func rebuildMenu() {
        let menu = NSMenu()

        let title = NSMenuItem()
        title.attributedTitle = styled("Photo System", size: 15, weight: .semibold)
        title.isEnabled = false
        menu.addItem(title)
        menu.addItem(.separator())

        menu.addItem(item("Audit now…", action: #selector(auditNow)))
        menu.addItem(item("Status…", action: #selector(showStatus)))
        menu.addItem(item("Open latest report", action: #selector(openLatestReport)))
        menu.addItem(.separator())

        let interval = NSMenuItem(title: "Set interval", action: nil, keyEquivalent: "")
        interval.attributedTitle = styled("Set interval", size: 14, weight: .medium)
        let submenu = NSMenu()
        for value in ["90m", "hourly", "6h", "12h", "daily", "weekly"] {
            let i = NSMenuItem(title: value, action: #selector(setInterval(_:)), keyEquivalent: "")
            i.representedObject = value
            i.target = self
            i.attributedTitle = styled(value)
            submenu.addItem(i)
        }
        interval.submenu = submenu
        menu.addItem(interval)

        menu.addItem(item("Stop background audit", action: #selector(stopAutomation)))
        menu.addItem(.separator())
        menu.addItem(item("Open project folder", action: #selector(openProject)))
        menu.addItem(item("Quit", action: #selector(quit)))

        statusItem.menu = menu
    }

    private func item(_ title: String, action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        item.attributedTitle = styled(title)
        return item
    }

    private func run(_ args: [String], title: String, notifyOnDone: Bool = false) {
        let taskTitle = title
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: Settings.cliPath)
            process.arguments = args
            process.currentDirectoryURL = URL(fileURLWithPath: Settings.projectRoot)

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe

            do {
                try process.run()
                process.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                DispatchQueue.main.async {
                    if notifyOnDone {
                        self.notify(title: taskTitle, message: process.terminationStatus == 0 ? "Done." : "Needs attention.")
                    }
                    self.alert(title: taskTitle, text: output, ok: process.terminationStatus == 0)
                }
            } catch {
                DispatchQueue.main.async {
                    self.alert(title: taskTitle, text: "\(error)", ok: false)
                }
            }
        }
    }

    private func alert(title: String, text: String, ok: Bool) {
        let alert = NSAlert()
        alert.messageText = title
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        alert.informativeText = String(trimmed.prefix(3500))
        alert.alertStyle = ok ? .informational : .warning
        alert.addButton(withTitle: "OK")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    private func notify(title: String, message: String) {
        let script = "display notification \"\(message)\" with title \"\(title)\""
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]
        try? process.run()
    }

    @objc private func auditNow() {
        run(["audit", "--audit", "both", "--notify"], title: "Photo audit", notifyOnDone: true)
    }

    @objc private func showStatus() {
        run(["status"], title: "Photo system status")
    }

    @objc private func openLatestReport() {
        run(["latest-report", "--open"], title: "Latest photo report")
    }

    @objc private func setInterval(_ sender: NSMenuItem) {
        guard let value = sender.representedObject as? String else { return }
        run(["install", "--interval", value], title: "Set photo audit interval")
    }

    @objc private func stopAutomation() {
        run(["uninstall"], title: "Stop photo audit automation")
    }

    @objc private func openProject() {
        NSWorkspace.shared.open(URL(fileURLWithPath: Settings.projectRoot))
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}
