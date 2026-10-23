import Foundation
import AppKit
import AVFoundation

// Stay registered with AppKit while the Python UI is running. In particular,
// TCC must be able to present camera approval for the responsible app.
let application=NSApplication.shared
application.setActivationPolicy(.accessory)
let resources=Bundle.main.resourceURL!
let process=Process()
process.executableURL=resources.appendingPathComponent("Runtime/bin/python")
process.arguments=[resources.appendingPathComponent("Source/main.py").path]
process.currentDirectoryURL=resources
var environment=ProcessInfo.processInfo.environment
environment["PYTHONUNBUFFERED"]="1"
environment["PYTHONDONTWRITEBYTECODE"]="1"
environment["AIRCONTROL_APP"]=Bundle.main.bundleURL.path
environment["PATH"]="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
environment["SSL_CERT_FILE"]="/etc/ssl/cert.pem"
process.environment=environment
let logs=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/AirControl/Logs")
try? FileManager.default.createDirectory(at:logs,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
let log=logs.appendingPathComponent("app.log")
if !FileManager.default.fileExists(atPath:log.path){FileManager.default.createFile(atPath:log.path,contents:nil,attributes:[.posixPermissions:0o600])}
if let handle=try? FileHandle(forWritingTo:log){_ = try? handle.seekToEnd();process.standardOutput=handle;process.standardError=handle}
process.terminationHandler={ child in
    DispatchQueue.main.async { exit(child.terminationStatus) }
}
func launchInterface(){
do{try process.run()}catch{
    let alert=NSAlert();alert.messageText="AirControl не удалось запустить"
    alert.informativeText=error.localizedDescription;alert.runModal();exit(1)
}
}
// Capture is a core app feature. Request from the long-lived native app,
// rather than an OpenCV worker which may exit before the alert is answered.
if AVCaptureDevice.authorizationStatus(for:.video) == .notDetermined {
    AVCaptureDevice.requestAccess(for:.video){ _ in }
}
// Settings remain accessible even if the permission alert is left unanswered.
launchInterface()
application.run()
