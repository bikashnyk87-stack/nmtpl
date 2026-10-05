param([string]$ProjectRoot="")
$ErrorActionPreference='Stop'
$PackageRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot=Join-Path $PackageRoot 'payload'

function Step([string]$m){Write-Host ('[NMTPL] '+$m) -ForegroundColor Cyan}
function FindRoot([string]$candidate){
  $tries=@()
  if($candidate){$tries+=$candidate}
  $tries+=(Get-Location).Path
  $tries+=(Split-Path -Parent $PackageRoot)
  foreach($x in $tries){
    if(-not $x){continue}
    try{$p=(Resolve-Path -LiteralPath $x).Path}catch{continue}
    if((Test-Path (Join-Path $p 'app\main.py')) -and (Test-Path (Join-Path $p 'run_server.bat'))){return $p}
  }
  $x=Read-Host 'Enter full path of NMTPL_Server_v0_1 folder'
  $p=(Resolve-Path -LiteralPath $x).Path
  if(-not (Test-Path (Join-Path $p 'app\main.py'))){throw 'app\main.py not found.'}
  return $p
}
function StopApp([string]$root){
  foreach($task in @('NMTPL Server - Boot Startup','NMTPL WB Gmail - Boot Startup')){
    if(Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue){
      Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    }
  }
  $esc=[regex]::Escape($root)
  Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and $_.CommandLine -match $esc
  } | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}
}
function StartTasks {
  foreach($task in @('NMTPL Server - Boot Startup','NMTPL WB Gmail - Boot Startup')){
    if(Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue){
      Enable-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue | Out-Null
      Start-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    }
  }
}

$ProjectRoot=FindRoot $ProjectRoot
$python=Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if(-not (Test-Path $python)){throw 'Project .venv Python is missing.'}
Step "Project: $ProjectRoot"

$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot=Join-Path $ProjectRoot ("backups\PC_SITE_SOFTWARE_R7_"+$stamp)
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

Step 'Stopping NMTPL'
StopApp $ProjectRoot

Step 'Backing up changed files'
Get-ChildItem -LiteralPath $PayloadRoot -File -Recurse | ForEach-Object {
  $rel=$_.FullName.Substring($PayloadRoot.Length).TrimStart('\','/')
  $dst=Join-Path $ProjectRoot $rel
  if(Test-Path -LiteralPath $dst){
    $bak=Join-Path $BackupRoot $rel
    New-Item -ItemType Directory -Path (Split-Path -Parent $bak) -Force | Out-Null
    Copy-Item -LiteralPath $dst -Destination $bak -Force
  }
}

Step 'Installing consolidated SOCP/KOCP build'
Get-ChildItem -LiteralPath $PayloadRoot -File -Recurse | ForEach-Object {
  $rel=$_.FullName.Substring($PayloadRoot.Length).TrimStart('\','/')
  $dst=Join-Path $ProjectRoot $rel
  New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
  Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
}

Step 'Applying LAN-safe background startup'
$bg=Join-Path $ProjectRoot 'scripts\start_server_background.ps1'
if(Test-Path $bg){
  $x=Get-Content -Raw -LiteralPath $bg
  $x=$x.Replace("'--host', '127.0.0.1'","'--host', '0.0.0.0'")
  $x=$x.Replace("'--forwarded-allow-ips=127.0.0.1'","'--forwarded-allow-ips=*'")
  Set-Content -LiteralPath $bg -Value $x -Encoding UTF8
}
try{
  Get-NetFirewallRule -DisplayName 'NMTPL TIOM TCP 8000' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
  New-NetFirewallRule -DisplayName 'NMTPL TIOM TCP 8000' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Any -RemoteAddress LocalSubnet | Out-Null
}catch{}

Step 'Validating Python'
& $python -m py_compile (Join-Path $ProjectRoot 'app\main.py') (Join-Path $ProjectRoot 'app\models.py') (Join-Path $ProjectRoot 'app\site_models.py') (Join-Path $ProjectRoot 'app\routers\sites.py') (Join-Path $ProjectRoot 'app\routers\site_ops.py') (Join-Path $ProjectRoot 'app\services\site_context.py') (Join-Path $ProjectRoot 'app\services\tiom_location_erp.py')
if($LASTEXITCODE -ne 0){throw 'Python syntax validation failed.'}

Step 'Validating application import'
Push-Location $ProjectRoot
try{
  & $python -c "import app.main; print('NMTPL_IMPORT_OK', app.main.app.version)"
  if($LASTEXITCODE -ne 0){throw 'app.main import validation failed.'}
}finally{Pop-Location}

Step 'Starting NMTPL'
StartTasks
Start-Sleep -Seconds 6
$ok=$false
try{
  Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 6 -UseBasicParsing | Out-Null
  $ok=$true
}catch{}
if(-not $ok){
  Step 'Task did not start server; starting directly'
  Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000') -WorkingDirectory $ProjectRoot -WindowStyle Hidden
  Start-Sleep -Seconds 5
  try{
    Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 6 -UseBasicParsing | Out-Null
    $ok=$true
  }catch{}
}
if(-not $ok){throw 'Server did not pass health check. Run run_server.bat and share the traceback.'}

$lan=Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object {$_.IPAddress -notmatch '^127\.' -and $_.PrefixOrigin -ne 'WellKnown'} |
  Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress
@(
  'NMTPL PC SITE SOFTWARE R1',
  'Health: OK',
  'TIOM generic site removed: /site/TIOM -> /tiom',
  'Site workspace: SOCP + KOCP',
  ('Backup: '+$BackupRoot),
  ($(if($lan){'KOCP LAN: http://'+$lan+':8000/site/KOCP'}else{'LAN IP not detected'}))
) | Set-Content -LiteralPath (Join-Path $ProjectRoot 'PC_SITE_SOFTWARE_R7_RESULT.txt') -Encoding UTF8

Write-Host '[NMTPL] Health: OK' -ForegroundColor Green
if($lan){Write-Host ('[NMTPL] KOCP LAN: http://'+$lan+':8000/site/KOCP') -ForegroundColor Green}
