# NMTPL TIOM localhost 8765 autostart — independent of the office LAN.
# Does NOT modify: Windows network profile/firewall, port 8000, WB or Despatch sync.
# No administrator permission is required for this current-user task.
param([string]$ProjectRoot="E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1")
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$root=(Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$py=Join-Path $root ".venv\Scripts\python.exe"
$pyw=Join-Path $root ".venv\Scripts\pythonw.exe"
foreach($file in @($py,$pyw,(Join-Path $root "app\main.py"))) {
    if(-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Expected existing TIOM PC file missing: $file"
    }
}
$task="NMTPL TIOM Local 8765 - At Logon"
$dstDir=Join-Path $root "data\local_server"
$runner=Join-Path $dstDir "pc_tiom_local_8765_runner.py"
New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root ("backups\tiom_local_autostart_"+$stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
if(Test-Path -LiteralPath $runner) {
    Copy-Item -LiteralPath $runner -Destination (Join-Path $backup "pc_tiom_local_8765_runner.py") -Force
}

# Download a dedicated silent runner, not an entire copy of TIOM code.
$source="https://raw.githubusercontent.com/bikashnyk87-stack/nmtpl/main/scripts/pc_tiom_local_8765_runner.py"
$temp=Join-Path $env:TEMP ("tiom_local_8765_"+$stamp+".py")
try {
    Invoke-WebRequest -UseBasicParsing -Uri $source -OutFile $temp
    & $py -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8-sig').read())" $temp
    if($LASTEXITCODE -ne 0) {throw "Autostart runner syntax validation failed; existing TIOM unchanged."}
    Copy-Item -LiteralPath $temp -Destination $runner -Force
} finally {
    Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
}

# Register only our own uniquely named task. Do not edit the old 8000
# scheduler, existing WB task, Despatch mirror task or database state.
$id=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute $pyw -Argument ('"'+$runner+'"') -WorkingDirectory $root
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $id
$principal=New-ScheduledTaskPrincipal -UserId $id -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Silently start localhost TIOM at 127.0.0.1:8765 on Windows sign-in; no office LAN exposure." -Force | Out-Null

Write-Host "Local TIOM autostart task installed: $task"
Write-Host "Startup executable: $pyw (no popup)"
Write-Host "URL: http://127.0.0.1:8765/tiom"
Write-Host "Log: $root\logs\local_server\uvicorn_8765.log"
Write-Host "Existing port 8000 and WB/Despatch sync tasks were not changed."
Write-Host "Office LAN access is NOT enabled; Wi-Fi may remain Public."

$existing=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if($existing.Count -gt 0) {
    Write-Host "Port 8765 is already running. Autostart will take effect on the next Windows sign-in."
    Write-Host "To activate the background task now: stop only the manual 8765 Uvicorn window using Ctrl+C, then run:"
    Write-Host ('Start-ScheduledTask -TaskName "'+$task+'"')
} else {
    Start-ScheduledTask -TaskName $task
    Write-Host "Background 8765 startup requested."
    Start-Sleep -Seconds 4
    $listen=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
    if($listen.Count -eq 0) {
        Write-Warning "The task was installed but the server did not start. See the local_server log; do not change sync tasks."
    }
}
Get-ScheduledTask -TaskName $task | Select-Object TaskName,State | Format-Table | Out-Host
Get-ScheduledTaskInfo -TaskName $task | Select-Object LastRunTime,LastTaskResult | Format-List | Out-Host
