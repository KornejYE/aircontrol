import Foundation
import AppKit

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
do{try process.run();process.waitUntilExit();exit(process.terminationStatus)}catch{
    _ = NSApplication.shared
    let alert=NSAlert();alert.messageText="AirControl не удалось запустить"
    alert.informativeText=error.localizedDescription;alert.runModal();exit(1)
}
