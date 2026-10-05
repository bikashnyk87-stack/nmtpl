param([string]$ProjectRoot="")
$ErrorActionPreference='Stop'
if(-not $ProjectRoot){$ProjectRoot=Read-Host 'Enter full path of NMTPL_Server_v0_1 folder'}
$ProjectRoot=(Resolve-Path -LiteralPath $ProjectRoot).Path
$latest=Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'backups') -Directory -Filter 'PC_SITE_SOFTWARE_R7_*' -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending | Select-Object -First 1
if(-not $latest){throw 'No PC_SITE_SOFTWARE_R7 backup found.'}
foreach($t in @('NMTPL Server - Boot Startup','NMTPL WB Gmail - Boot Startup')){
  if(Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue){
    Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
  }
}
Get-ChildItem -LiteralPath $latest.FullName -File -Recurse | ForEach-Object {
  $rel=$_.FullName.Substring($latest.FullName.Length).TrimStart('\','/')
  $dst=Join-Path $ProjectRoot $rel
  New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
  Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
}
Write-Host ('Restored '+$latest.FullName) -ForegroundColor Green
