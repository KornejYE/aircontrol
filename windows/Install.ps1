$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {throw 'This installer requires Windows x64.'}
$package=Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $package 'Source\main.py'))) {throw 'Extract the complete package before starting Install.cmd.'}
$target=Join-Path $env:LOCALAPPDATA 'Programs\AirControl'
$data=Join-Path $env:LOCALAPPDATA 'AirControl'
New-Item -ItemType Directory -Force -Path $target,$data | Out-Null
$live=Get-CimInstance Win32_Process | Where-Object {($_.ExecutablePath -like "$target\Runtime\*") -or ($_.CommandLine -like "*$target\Source\main.py*") -or ($_.CommandLine -like "*$target\Start-AirControl.py*")}
if ($live) {throw 'Close AirControl before updating. No other Python programs need to be closed.'}
Add-Type -Namespace AirControl -Name InstallPower -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
[AirControl.InstallPower]::SetThreadExecutionState([uint32]2147483649) | Out-Null
Start-Transcript -Path (Join-Path $data 'install.log') -Append | Out-Null
try {
 if ([IO.Path]::GetFullPath($package) -ne [IO.Path]::GetFullPath($target)) {
  if (Test-Path (Join-Path $target 'Source')) {
   $backup=Join-Path $data ('PreviousVersions\'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
   New-Item -ItemType Directory -Force -Path $backup | Out-Null
   Copy-Item (Join-Path $target 'Source') $backup -Recurse
  }
  foreach ($name in @('Source','BrowserGestures','docs')) {Copy-Item (Join-Path $package $name) $target -Recurse -Force}
  foreach ($name in @('requirements-windows.lock','LICENSE','NOTICE.md','README.md','README.ru.md','PRIVACY.md','UPSTREAM.json','CHANGELOG.md')) {Copy-Item (Join-Path $package $name) $target -Force}
  Copy-Item (Join-Path $PSScriptRoot 'Start-AirControl.py') $target -Force
 }
 $python=Join-Path $target 'Python\python.exe'
 if (-not (Test-Path $python)) {
  $installer=Join-Path $env:TEMP 'aircontrol-python-3.13.12-amd64.exe'
  Write-Host 'Downloading Python from python.org...'
  Invoke-WebRequest 'https://www.python.org/ftp/python/3.13.12/python-3.13.12-amd64.exe' -OutFile $installer -UseBasicParsing
  $signature=Get-AuthenticodeSignature $installer
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {throw 'Python installer signature verification failed.'}
  $args=@('/quiet','InstallAllUsers=0',('TargetDir="'+(Join-Path $target 'Python')+'"'),'PrependPath=0','Include_launcher=0','Include_test=0','Include_doc=0','Include_tcltk=0','AssociateFiles=0','Shortcuts=0','Include_pip=1')
  $result=Start-Process $installer -ArgumentList $args -Wait -PassThru
  if ($result.ExitCode -notin @(0,3010)) {throw ('Python installation failed: '+$result.ExitCode)}
 }
 $runtime=Join-Path $target 'Runtime\Scripts\python.exe'
 if (-not (Test-Path $runtime)) {& $python -m venv (Join-Path $target 'Runtime');if ($LASTEXITCODE) {throw 'Cannot create Python environment.'}}
 & $runtime -m pip install --disable-pip-version-check --only-binary=:all: -r (Join-Path $target 'requirements-windows.lock')
 if ($LASTEXITCODE) {throw 'Dependency installation failed.'}
 $model=Join-Path $target 'Models\gestures\hand_landmarker.task'
 New-Item -ItemType Directory -Force -Path (Split-Path $model -Parent) | Out-Null
 $packagedModel=Join-Path $package 'Models\gestures\hand_landmarker.task'
 if (Test-Path $packagedModel) {Copy-Item $packagedModel $model -Force}
 elseif (-not (Test-Path $model)) {Invoke-WebRequest 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -OutFile $model -UseBasicParsing}
 if ((Get-FileHash $model -Algorithm SHA256).Hash -ne 'FBC2A30080C3C557093B5DDFC334698132EB341044CCEE322CCF8BCF3607CDE1') {throw 'Hand model checksum mismatch.'}
 & $runtime -X utf8 (Join-Path $PSScriptRoot 'Smoke-Test.py') $target
 if ($LASTEXITCODE) {throw 'Application dependency/model check failed.'}
 $shell=New-Object -ComObject WScript.Shell
 $shortcut=$shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'AirControl.lnk'))
 $shortcut.TargetPath=Join-Path $target 'Runtime\Scripts\pythonw.exe'
 $shortcut.Arguments='-X utf8 "'+(Join-Path $target 'Start-AirControl.py')+'"'
 $shortcut.WorkingDirectory=$target
 $shortcut.IconLocation=(Join-Path $target 'Source\assets\aircontrol.ico')+',0'
 $shortcut.Save()
 Write-Host 'AirControl is ready. Open the AirControl shortcut on your Desktop.'
} finally {[AirControl.InstallPower]::SetThreadExecutionState([uint32]2147483648) | Out-Null;Stop-Transcript | Out-Null}
