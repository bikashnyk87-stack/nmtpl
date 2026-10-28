# Reliable staged PC TIOM Gmail configuration UI installer.
# PowerShell downloads the approved three components with retries; Python applies
# them OFFLINE, only after all downloads and syntax prechecks complete.
# Do not update WB sync, Despatch mirror, database, or Gmail OAuth credentials.
param([string]$ProjectRoot="E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1")
$ErrorActionPreference="Stop"
$ProgressPreference="SilentlyContinue"
Set-StrictMode -Version Latest

$root=(Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$python=Join-Path $root ".venv\Scripts\python.exe"
if(-not(Test-Path -LiteralPath $python -PathType Leaf)) {throw "Existing TIOM PC Python missing: $python"}
$stage=Join-Path $env:TEMP ("NMTPL-Gmail-Setup-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$base="https://raw.githubusercontent.com/bikashnyk87-stack/nmtpl/main/"
$files=@(
 "scripts/install_pc_gmail_config_safe.py",
 "app/routers/automation.py",
 "app/routers/tiom_despatch.py",
 "app/static/tiom_despatch.js"
)
try {
 foreach($relative in $files) {
  $target=Join-Path $stage ($relative -replace "/","\")
  New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
  $successful=$false
  for($n=1;$n -le 4;$n++) {
   try {
    Write-Host "Downloading $relative (attempt $n/4)"
    Invoke-WebRequest -UseBasicParsing -Uri ($base+$relative) -OutFile $target -TimeoutSec 180 -ErrorAction Stop
    $length=(Get-Item -LiteralPath $target).Length
    if($length -lt 100 -or $length -gt 256000) {throw "Unexpected downloaded file size: $length"}
    $successful=$true
    break
   } catch {
    Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    if($n -eq 4) {throw ("Download failed after four attempts: "+$relative+". "+$_.Exception.Message)}
    Start-Sleep -Seconds (3*$n)
   }
  }
  if(-not $successful) {throw "Unable to retrieve $relative"}
 }
 # The Python installer is now OFFLINE: it will NOT call the Python URL reader.
 $script=Join-Path $stage "scripts\install_pc_gmail_config_safe.py"
 foreach($relative in @("scripts/install_pc_gmail_config_safe.py","app/routers/automation.py","app/routers/tiom_despatch.py")) {
  $file=Join-Path $stage ($relative -replace "/","\")
  & $python -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8-sig').read())" $file
  if($LASTEXITCODE -ne 0) {throw "Python syntax validation failed: $relative"}
 }
 $js=(Get-Content (Join-Path $stage "app\static\tiom_despatch.js") -Raw)
 if($js -notmatch "tiomDDGmailConnect") {throw "Incorrect/incomplete Gmail UI download. No files changed."}
 Write-Host "All files staged and validated. Applying safe offline installation..."
 & $python $script --project-root $root --source-dir $stage
 if($LASTEXITCODE -ne 0) {throw "PC Gmail UI safe installer failed; check the preceding message. Nothing else was restarted."}
} finally {
 Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host "PC Gmail UI files installed. Verifying local TIOM autostart registration."
$taskName="NMTPL TIOM Local 8765 - At Logon"
$task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if($task) {
 Write-Host "Restarting only the verified TIOM port 8765 task: $taskName"
 if($task.State -eq "Running") {Stop-ScheduledTask -TaskName $taskName}
 Start-Sleep -Seconds 2
 Start-ScheduledTask -TaskName $taskName
 $ready=$false
 for($n=0;$n -lt 30;$n++) {
  try {
   $api=Invoke-RestMethod -Uri "http://127.0.0.1:8765/openapi.json" -TimeoutSec 2 -ErrorAction Stop
   $registered=@($api.paths.PSObject.Properties.Name) -contains "/api/tiom/despatch/gmail-connect-local"
   if($registered) {$ready=$true; break}
  } catch {}
  Start-Sleep -Seconds 2
 }
 if($ready) {
  Write-Host "SUCCESS: Local Gmail connection API registered on port 8765."
 } else {
  Write-Warning "Installer succeeded but 8765 Gmail API is not verified. Check logs\local_server\uvicorn_8765.log or logs\lan_server\uvicorn_8765.log."
 }
} else {
 Write-Warning "The expected 8765 task was not found. Restart your existing TIOM server manually."
}
Write-Host "Open http://127.0.0.1:8765/tiom and press Ctrl+F5."
Write-Host "Production > Despatch Report > Mail & Image Imports > Connect MIS Gmail."
Write-Host "WB and Despatch sync workers and existing OAuth credentials were not changed."
