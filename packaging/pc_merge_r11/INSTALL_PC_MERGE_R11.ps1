param([string]$ProjectRoot="")
$ErrorActionPreference='Stop'
$PackageRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseRoot=Join-Path $PackageRoot 'base'
$LatestRoot=Join-Path $PackageRoot 'latest'
$Targets=@(
  'app\main.py',
  'app\routers\site_ops.py',
  'app\routers\sites.py',
  'app\static\simple_field_v1.css',
  'app\static\simple_field_v1.js',
  'app\static\site.html',
  'app\static\site_ops.js'
)

function Step([string]$m){Write-Host ('[NMTPL] '+$m) -ForegroundColor Cyan}
function Find-Root([string]$candidate){
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
  if(-not (Test-Path (Join-Path $p 'app\main.py'))){throw 'app\main.py not found in selected project.'}
  return $p
}
function Hash([string]$p){(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash}
function Ensure-Parent([string]$p){New-Item -ItemType Directory -Path (Split-Path -Parent $p) -Force | Out-Null}
function Stop-Server([string]$root){
  if(Get-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue){
    Stop-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue
  }
  $esc=[regex]::Escape($root)
  Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
    ($_.CommandLine -match $esc) -and ($_.CommandLine -match 'uvicorn|app\.main')
  } | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}
}
function Start-Server([string]$root,[string]$python){
  $task=Get-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue
  if($task){
    Enable-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue | Out-Null
    Start-ScheduledTask -TaskName 'NMTPL Server - Boot Startup' -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 5
  try{
    Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5 -UseBasicParsing | Out-Null
    return $true
  }catch{}
  Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000') -WorkingDirectory $root -WindowStyle Hidden
  Start-Sleep -Seconds 5
  try{
    Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 6 -UseBasicParsing | Out-Null
    return $true
  }catch{return $false}
}
function Write-Report([string[]]$lines){
  $lines | Set-Content -LiteralPath (Join-Path $ProjectRoot 'PC_MERGE_R11_REPORT.txt') -Encoding UTF8
}

$ProjectRoot=Find-Root $ProjectRoot
$python=Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if(-not (Test-Path $python)){throw 'Project .venv Python is missing.'}
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$StageRoot=Join-Path $env:TEMP ("NMTPL_PC_MERGE_R11_"+$stamp)
$BackupRoot=Join-Path $ProjectRoot ("backups\PC_MERGE_R11_"+$stamp)
$ConflictRoot=Join-Path $ProjectRoot ("merge_conflicts\PC_MERGE_R11_"+$stamp)
New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null

$git=(Get-Command git.exe -ErrorAction SilentlyContinue)
$results=New-Object System.Collections.Generic.List[string]
$conflicts=New-Object System.Collections.Generic.List[string]

Step "Project: $ProjectRoot"
Step 'Preflight merge - no PC files are changed during this step'

foreach($rel in $Targets){
  $cur=Join-Path $ProjectRoot $rel
  $base=Join-Path $BaseRoot $rel
  $new=Join-Path $LatestRoot $rel
  $stage=Join-Path $StageRoot $rel
  if(-not (Test-Path $base)){throw "Package base file missing: $rel"}
  if(-not (Test-Path $new)){throw "Package latest file missing: $rel"}
  Ensure-Parent $stage

  if(-not (Test-Path $cur)){
    Copy-Item -LiteralPath $new -Destination $stage -Force
    $results.Add("NEW | $rel")
    continue
  }

  $hc=Hash $cur; $hb=Hash $base; $hn=Hash $new
  if($hc -eq $hn){
    Copy-Item -LiteralPath $cur -Destination $stage -Force
    $results.Add("ALREADY_CURRENT | $rel")
    continue
  }
  if($hc -eq $hb){
    Copy-Item -LiteralPath $new -Destination $stage -Force
    $results.Add("SAFE_UPDATE | $rel")
    continue
  }

  if($git){
    Copy-Item -LiteralPath $cur -Destination $stage -Force
    & $git.Source merge-file -- $stage $base $new
    $code=$LASTEXITCODE
    if($code -eq 0){
      $results.Add("MERGED_LOCAL_CHANGES | $rel")
    }else{
      Remove-Item -LiteralPath $stage -Force -ErrorAction SilentlyContinue
      $conflicts.Add($rel)
      $results.Add("CONFLICT | $rel")
    }
  }else{
    $conflicts.Add($rel)
    $results.Add("LOCAL_CHANGED_GIT_REQUIRED | $rel")
  }
}

if($conflicts.Count -gt 0){
  New-Item -ItemType Directory -Path $ConflictRoot -Force | Out-Null
  foreach($rel in $conflicts){
    $dst=Join-Path $ConflictRoot $rel
    Ensure-Parent $dst
    if(Test-Path (Join-Path $ProjectRoot $rel)){Copy-Item -LiteralPath (Join-Path $ProjectRoot $rel) -Destination ($dst+'.PC_CURRENT') -Force}
    Copy-Item -LiteralPath (Join-Path $BaseRoot $rel) -Destination ($dst+'.R7_BASE') -Force
    Copy-Item -LiteralPath (Join-Path $LatestRoot $rel) -Destination ($dst+'.R11_LATEST') -Force
  }
  $report=@(
    'NMTPL PC MERGE R11 - NOT INSTALLED',
    ('Time: '+(Get-Date)),
    ('Project: '+$ProjectRoot),
    'Reason: One or more PC-local changes could not be merged automatically.',
    'No project source file was overwritten.',
    ('Conflict copies: '+$ConflictRoot),
    '',
    'Preflight results:'
  ) + $results
  Write-Report $report
  Write-Host '[NMTPL] Merge conflict found. NOTHING was installed.' -ForegroundColor Yellow
  Write-Host ('[NMTPL] See: '+(Join-Path $ProjectRoot 'PC_MERGE_R11_REPORT.txt'))
  exit 2
}

Step 'Preflight merge clean'
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
foreach($rel in $Targets){
  $cur=Join-Path $ProjectRoot $rel
  if(Test-Path $cur){
    $bak=Join-Path $BackupRoot $rel
    Ensure-Parent $bak
    Copy-Item -LiteralPath $cur -Destination $bak -Force
  }
}

$installed=$false
try{
  Step 'Stopping PC server'
  Stop-Server $ProjectRoot

  Step 'Installing merged R11 files'
  foreach($rel in $Targets){
    $src=Join-Path $StageRoot $rel
    $dst=Join-Path $ProjectRoot $rel
    Ensure-Parent $dst
    Copy-Item -LiteralPath $src -Destination $dst -Force
  }
  $installed=$true

  Step 'Validating Python files'
  $pyFiles=@(
    (Join-Path $ProjectRoot 'app\main.py'),
    (Join-Path $ProjectRoot 'app\routers\sites.py'),
    (Join-Path $ProjectRoot 'app\routers\site_ops.py')
  )
  & $python -m py_compile @pyFiles
  if($LASTEXITCODE -ne 0){throw 'Python syntax validation failed.'}

  $node=(Get-Command node.exe -ErrorAction SilentlyContinue)
  if($node){
    Step 'Validating merged JavaScript'
    & $node.Source --check (Join-Path $ProjectRoot 'app\static\simple_field_v1.js')
    if($LASTEXITCODE -ne 0){throw 'simple_field_v1.js validation failed.'}
    & $node.Source --check (Join-Path $ProjectRoot 'app\static\site_ops.js')
    if($LASTEXITCODE -ne 0){throw 'site_ops.js validation failed.'}
  }

  Step 'Validating app.main import'
  Push-Location $ProjectRoot
  try{
    & $python -c "import app.main; print('NMTPL_IMPORT_OK', app.main.app.version)"
    if($LASTEXITCODE -ne 0){throw 'app.main import failed.'}
  }finally{Pop-Location}

  Step 'Starting PC server'
  if(-not (Start-Server $ProjectRoot $python)){throw 'Server failed health check after update.'}

  $lan=Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {$_.IPAddress -notmatch '^127\.' -and $_.PrefixOrigin -ne 'WellKnown'} |
    Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress

  $report=@(
    'NMTPL PC MERGE R11 - SUCCESS',
    ('Time: '+(Get-Date)),
    ('Project: '+$ProjectRoot),
    ('Backup: '+$BackupRoot),
    'Source freeze: 99dcf176873a7e740afc4b745b6920db698c9033',
    'Health: OK',
    ($(if($lan){'KOCP: http://'+$lan+':8000/site/KOCP'}else{'KOCP: http://127.0.0.1:8000/site/KOCP'})),
    ($(if($lan){'SOCP: http://'+$lan+':8000/site/SOCP'}else{'SOCP: http://127.0.0.1:8000/site/SOCP'})),
    '',
    'Merge results:'
  ) + $results
  Write-Report $report
  Write-Host '[NMTPL] PC MERGE R11 SUCCESS' -ForegroundColor Green
  Write-Host ('[NMTPL] Backup: '+$BackupRoot)
}catch{
  $err=$_.Exception.Message
  Write-Host ('[NMTPL] Validation/startup failed: '+$err) -ForegroundColor Red
  if($installed){
    Step 'Rolling back automatically'
    Stop-Server $ProjectRoot
    foreach($rel in $Targets){
      $bak=Join-Path $BackupRoot $rel
      $dst=Join-Path $ProjectRoot $rel
      if(Test-Path $bak){
        Ensure-Parent $dst
        Copy-Item -LiteralPath $bak -Destination $dst -Force
      }
    }
    [void](Start-Server $ProjectRoot $python)
  }
  $report=@(
    'NMTPL PC MERGE R11 - FAILED AND ROLLED BACK',
    ('Time: '+(Get-Date)),
    ('Project: '+$ProjectRoot),
    ('Backup: '+$BackupRoot),
    ('Error: '+$err),
    '',
    'Merge results:'
  ) + $results
  Write-Report $report
  throw
}finally{
  Remove-Item -LiteralPath $StageRoot -Recurse -Force -ErrorAction SilentlyContinue
}
