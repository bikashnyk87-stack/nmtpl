# Enable office-only NMTPL TIOM LAN server at 8765 without touching WB/Despatch sync.
# Run Windows PowerShell as Administrator for the inbound Private-only firewall.
param([string]$ProjectRoot="E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1")
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$project=(Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$pythonw=Join-Path $project ".venv\Scripts\pythonw.exe"
$python=Join-Path $project ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf) -or -not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $project "app\main.py"))) {
    throw "Existing TIOM PC project/venv not found. No changes made."
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$administrator=New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $administrator.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Open PowerShell with Run as administrator; inbound Private-LAN firewall permission is required."
}
$privateIps=@(
    Get-NetConnectionProfile | Where-Object {$_.NetworkCategory -in @("Private","DomainAuthenticated")} | ForEach-Object {
        $iface=$_.InterfaceIndex
        Get-NetIPAddress -InterfaceIndex $iface -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
            $_.IPAddress -notmatch "^(127|169\.254)\." -and $_.IPAddress -notmatch "^0\."
        }
    }
)
if ($privateIps.Count -eq 0) {
    Get-NetConnectionProfile | Format-Table InterfaceAlias,NetworkCategory,IPv4Connectivity | Out-Host
    throw "No trusted Private/Domain office IPv4 network found. Public and guest Wi-Fi are not supported."
}

$dest=Join-Path $project "data\lan_server"
$runner=Join-Path $dest "pc_tiom_lan_runner.py"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $project ("backups\tiom_lan_setup_"+$stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
if(Test-Path -LiteralPath $runner) {Copy-Item -LiteralPath $runner -Destination (Join-Path $backup "pc_tiom_lan_runner.py") -Force}
Write-Host "Project: $project"
Write-Host "Backup : $backup"
Write-Host "No existing WB or Despatch sync tasks or data will be changed."

$url="https://raw.githubusercontent.com/bikashnyk87-stack/nmtpl/main/scripts/pc_tiom_lan_runner.py"
$temp=Join-Path $env:TEMP ("nmtpl_lan_runner_"+$stamp+".py")
try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temp
    & $python -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8-sig').read())" $temp
    if($LASTEXITCODE -ne 0) {throw "LAN startup Python syntax test failed."}
    Copy-Item -LiteralPath $temp -Destination $runner -Force
} finally {
    Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
}
$ruleName="NMTPL-TIOM-Private-LAN-8765"
$existing=Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if($existing) {$existing | Remove-NetFirewallRule}
$firewallParams=@{
    Name=$ruleName
    DisplayName="NMTPL TIOM - Office LAN 8765"
    Description="TIOM only on trusted Private local subnets"
    Direction="Inbound"
    Protocol="TCP"
    LocalPort=8765
    Program=$pythonw
    Profile="Private,Domain"
    RemoteAddress="LocalSubnet"
    Action="Allow"
    Enabled="True"
}
New-NetFirewallRule @firewallParams | Out-Null

$taskName="NMTPL TIOM LAN Server - At Logon"
$action=New-ScheduledTaskAction -Execute $pythonw -Argument ('"'+$runner+'"') -WorkingDirectory $project
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$principal=New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Silent TIOM LAN 8765 server on Windows sign-in; sync tasks remain untouched" -Force | Out-Null

Write-Host ""
Write-Host "OFFICE LAN ACCESS CONFIGURED"
@($privateIps | Select-Object -ExpandProperty IPAddress -Unique) | ForEach-Object {Write-Host ("Office browser URL: http://"+$_+":8765/tiom")}
Write-Host "Local browser URL: http://127.0.0.1:8765/tiom"
Write-Host "Firewall: Private/Domain LocalSubnet only (never Public), pythonw.exe, TCP 8765"
Write-Host "Startup task: $taskName"
Write-Host "Server log: $project\logs\lan_server\uvicorn_8765.log"
$listening=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if($listening.Count -gt 0) {
    Write-Warning "Port 8765 already has a running TIOM server. Do not run a duplicate."
    Write-Host "Stop the existing manual Uvicorn in its PowerShell window (Ctrl+C), then run:"
    Write-Host "Start-ScheduledTask -TaskName '$taskName'"
} else {
    Start-ScheduledTask -TaskName $taskName
    Write-Host "Background LAN server task started."
}
Write-Host "Check: Get-ScheduledTaskInfo -TaskName '$taskName'"
Write-Host "The host PC must be powered on and signed in to Windows."
Write-Warning "Office LAN HTTP is not encrypted. Use trusted local devices only; configure HTTPS for untrusted networks."
