# Enable trusted office Wi-Fi access to the EXISTING silent TIOM port 8765.
# Do not modify application, WB/Despatch sync tasks, database or old port 8000.
param(
 [string]$ProjectRoot="E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1",
 [string]$InterfaceAlias="Wi-Fi"
)
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$root=(Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$python=Join-Path $root ".venv\Scripts\python.exe"
$pythonw=Join-Path $root ".venv\Scripts\pythonw.exe"
$taskName="NMTPL TIOM Local 8765 - At Logon"
$ruleName="NMTPL-TIOM-Private-LAN-8765"
$runner=Join-Path $root "data\lan_server\pc_tiom_lan_runner.py"
foreach($p in @($python,$pythonw,(Join-Path $root "app\main.py"))) {
 if(-not(Test-Path -LiteralPath $p -PathType Leaf)) {throw "Missing TIOM file: $p"}
}
$id=[Security.Principal.WindowsIdentity]::GetCurrent()
$admin=New-Object Security.Principal.WindowsPrincipal($id)
if(-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
 throw "Open PowerShell using Run as administrator."
}
$task=Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if(@($task.Actions).Count -ne 1) {throw "Unexpected task actions; no change made."}
$oldAction=@($task.Actions)[0]
if($oldAction.Execute -ine $pythonw) {throw "Task action executable differs from expected pythonw.exe; no change."}
if($oldAction.Arguments -notlike "*pc_tiom_local_8765_runner.py*" -and $oldAction.Arguments -notlike "*pc_tiom_lan_runner.py*") {
 throw "Unknown existing TIOM startup task runner; no change."
}

$profile=Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias -ErrorAction Stop
Write-Host "Office network: $($profile.Name) [$($profile.NetworkCategory)] on $InterfaceAlias"
if($profile.NetworkCategory -eq "Public") {
 Write-Warning "Only proceed when physically connected to your trusted OFFICE Wi-Fi (never guest, hotel or public Wi-Fi)."
 $response=Read-Host "To confirm this is trusted OFFICE Wi-Fi and set it Private, type TRUSTED-OFFICE"
 if($response -cne "TRUSTED-OFFICE") {throw "Not a confirmed office network. No LAN exposure."}
 Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private -ErrorAction Stop
 $profile=Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias
}
if($profile.NetworkCategory -notin @("Private","DomainAuthenticated")) {
 throw "Office LAN needs a trusted Private/Domain Windows network."
}
$addresses=@(Get-NetIPAddress -InterfaceIndex $profile.InterfaceIndex -AddressFamily IPv4 -ErrorAction Stop |
 Where-Object {$_.AddressState -eq "Preferred" -and (
 $_.IPAddress -match "^10\." -or $_.IPAddress -match "^192\.168\." -or
 $_.IPAddress -match "^172\.(1[6-9]|2[0-9]|3[01])\."
 )})
if($addresses.Count -ne 1) {throw "Expected one private office IPv4 on Wi-Fi; found $($addresses.Count)."}
$lanIp=$addresses[0].IPAddress
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root ("backups\tiom_office_lan_"+$stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Export-ScheduledTask -TaskName $taskName |
 Set-Content -LiteralPath (Join-Path $backup "previous_8765_task.xml") -Encoding UTF8
New-Item -ItemType Directory -Path (Split-Path -Parent $runner) -Force | Out-Null
if(Test-Path -LiteralPath $runner) {
 Copy-Item -LiteralPath $runner -Destination (Join-Path $backup "previous_lan_runner.py") -Force
}
$temp=Join-Path $env:TEMP ("tiom_8765_lan_"+$stamp+".py")
try {
 Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/bikashnyk87-stack/nmtpl/main/scripts/pc_tiom_lan_runner.py" -OutFile $temp
 & $python -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8-sig').read())" $temp
 if($LASTEXITCODE -ne 0) {throw "LAN runner syntax check failed."}
 Copy-Item -LiteralPath $temp -Destination $runner -Force
} finally {
 Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
}

# One restrictive firewall rule, never Public; only office Wi-Fi subnet.
$prior=Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if($prior) {$prior | Remove-NetFirewallRule}
$fw=@{
 Name=$ruleName
 DisplayName="NMTPL TIOM Office LAN 8765"
 Description="Trusted office Wi-Fi local subnet only"
 Direction="Inbound"; Protocol="TCP"; LocalPort=8765
 LocalAddress=$lanIp; Program=$pythonw; InterfaceAlias=$InterfaceAlias
 Profile="Private,Domain"; RemoteAddress="LocalSubnet"
 Action="Allow"; Enabled="True"
}
New-NetFirewallRule @fw | Out-Null
$updated=$false
try {
 # The running port 8765 is from our known scheduled task. Stop only that task.
 if((Get-ScheduledTask -TaskName $taskName).State -eq "Running") {
  Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop
 }
 $free=$false
 for($i=0;$i -lt 20;$i++) {
  $listeners=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
  if($listeners.Count -eq 0) {$free=$true; break}
  Start-Sleep -Seconds 1
 }
 if(-not $free) {throw "Port 8765 is still occupied. No unknown process will be terminated."}
 $action=New-ScheduledTaskAction -Execute $pythonw -Argument ('"'+$runner+'"') -WorkingDirectory $root
 Set-ScheduledTask -TaskName $taskName -Action $action -ErrorAction Stop | Out-Null
 $updated=$true
 Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
} catch {
 $failure=$_.Exception.Message
 Write-Warning ("Switch failed: "+$failure)
 if($updated) {
  try {
   Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
   Set-ScheduledTask -TaskName $taskName -Action $oldAction -ErrorAction Stop | Out-Null
  } catch {Write-Warning ("Rollback needs attention: "+$_.Exception.Message)}
 }
 try {Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue} catch {}
 throw "LAN migration incomplete. Previous 8765 task restored where possible; backup at $backup."
}
$healthy=$false
for($i=0;$i -lt 30;$i++) {
 try {
  $r=Invoke-WebRequest -Uri ("http://"+$lanIp+":8765/health") -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
  if($r.StatusCode -eq 200) {$healthy=$true;break}
 } catch {}
 Start-Sleep -Seconds 2
}
Write-Host ""
Write-Host "LAN URL: http://$($lanIp):8765/tiom"
Write-Host "Local URL: http://127.0.0.1:8765/tiom"
Write-Host "Startup task: $taskName (silent, at Windows sign-in)"
Write-Host "Firewall: $ruleName; Private/Domain; LocalSubnet; $InterfaceAlias"
Write-Host "Backup: $backup"
Write-Host "WB + Despatch tasks and port 8000: UNCHANGED"
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
 Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table | Out-Host
if($healthy) {Write-Host "LAN_HTTP_HEALTH_200_OK"} else {
 Write-Warning "LAN health not verified yet. Check logs\lan_server\uvicorn_8765.log."
}
Write-Warning "HTTP is unencrypted. Only use trusted office devices; wireless client isolation can block other PCs."
