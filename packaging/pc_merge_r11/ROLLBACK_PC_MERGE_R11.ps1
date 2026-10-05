param([string]$ProjectRoot="")
$ErrorActionPreference='Stop'
if(-not $ProjectRoot){$ProjectRoot=Read-Host 'Enter full path of NMTPL_Server_v0_1 folder'}
$ProjectRoot=(Resolve-Path -LiteralPath $ProjectRoot).Path
$root=Join-Path $ProjectRoot 'backups'
$latest=Get-ChildItem -LiteralPath $root -Directory -Filter 'PC_MERGE_R11_*' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
if(-not $latest){throw 'No PC_MERGE_R11 backup found.'}
if(Get-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue){
  Stop-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue
}
Get-ChildItem -LiteralPath $latest.FullName -File -Recurse | ForEach-Object {
  $rel=$_.FullName.Substring($latest.FullName.Length).TrimStart('\','/')
  $dst=Join-Path $ProjectRoot $rel
  New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
  Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
}
Write-Host ('Restored backup: '+$latest.FullName) -ForegroundColor Green
