# Independent TIOM Despatch PC installation — never merges or edits WB sync code.
# Run in ordinary Windows PowerShell after downloading from the approved NMTPL GitHub.
param([string]$ProjectRoot="E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1")
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$ProjectRoot=(Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$python=Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {throw "PC virtualenv Python not found: $python"}
$pair=Join-Path $ProjectRoot "config\render_sync_client.json"
if (-not (Test-Path -LiteralPath $pair)) {throw "Existing Render sync pairing is missing. WB sync configuration was not touched."}

$timestamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $ProjectRoot ("backups\despatch_independent_"+$timestamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$tools=Join-Path $ProjectRoot "data\despatch_addon"
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$raw="https://raw.githubusercontent.com/bikashnyk87-stack/nmtpl/main/"
$worker=Join-Path $tools "pc_despatch_mirror_standalone.py"
$pkg=Join-Path $env:TEMP ("despatch_pc_installer_"+$timestamp)
New-Item -ItemType Directory -Path $pkg -Force | Out-Null

# Only files dedicated to Despatch, plus a minimal guarded Main/HTML registration.
$downloads=@(
    "scripts/pc_despatch_mirror_standalone.py",
    "app/routers/tiom_despatch.py",
    "app/services/tiom_despatch_client_layout.py",
    "app/services/tiom_despatch_client_reports.py",
    "app/services/tiom_despatch_mail.py",
    "app/static/tiom_despatch.js",
    "app/static/tiom_despatch.css"
)

function Backup-File([string]$rel) {
    $src=Join-Path $ProjectRoot ($rel -replace "/", "\")
    if(Test-Path -LiteralPath $src -PathType Leaf) {
        $dest=Join-Path $backup ($rel -replace "/", "\")
        New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
        Copy-Item -LiteralPath $src -Destination $dest -Force
    }
}

Write-Host "PC TIOM root : $ProjectRoot"
Write-Host "Backup       : $backup"
Write-Host "Working WB synchronization and its Git customizations will be left unchanged."

try {
    foreach($rel in $downloads) {
        $dest=Join-Path $pkg ($rel -replace "/", "\")
        New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri ($raw+$rel) -OutFile $dest
        if(-not (Test-Path $dest) -or (Get-Item $dest).Length -lt 100) {
            throw "Incomplete Despatch-only file: $rel"
        }
    }
    # Syntax validation before installing any application module.
    $pyFiles=@($downloads | Where-Object {$_ -like "*.py"})
    foreach($rel in $pyFiles) {
        $item=Join-Path $pkg ($rel -replace "/", "\")
        & $python -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8-sig').read())" $item
        if($LASTEXITCODE -ne 0) {throw "Python source syntax check failed: $rel"}
    }
    Write-Host "Official Despatch module files retrieved and syntax checked."

    # FIRST: verify independent historical data mirror with no application
    # source modifications and no change to the WB sync cursor.
    Backup-File "data/despatch_addon/pc_despatch_mirror_standalone.py"
    Copy-Item -LiteralPath (Join-Path $pkg "scripts\pc_despatch_mirror_standalone.py") -Destination $worker -Force
    $env:NMTPL_PC_PROJECT_ROOT=$ProjectRoot
    Push-Location $ProjectRoot
    try {
        Write-Host "Fetching Despatch history from Render into the local database..."
        & $python $worker
        if($LASTEXITCODE -ne 0) {
            throw "Independent Despatch data mirror did not complete. Existing WB sync remains unchanged. Details: data\despatch_addon\mirror_status.json"
        }
    } finally {Pop-Location}

    $main=Join-Path $ProjectRoot "app\main.py"
    $index=Join-Path $ProjectRoot "app\static\index.html"
    if(-not (Test-Path -LiteralPath $main) -or -not (Test-Path -LiteralPath $index)) {
        throw "PC application registration files missing; data mirror is complete but UI not installed."
    }
    Backup-File "app/main.py"
    Backup-File "app/static/index.html"
    foreach($rel in $downloads) {
        if($rel -notlike "app/*") {continue}
        Backup-File $rel
    }

    # PC main.py may be older than Render. Append a minimal router import and
    # registration instead of replacing it with the online version.
    $mainText=[System.IO.File]::ReadAllText($main)
    if($mainText -notmatch "app\.include_router\(sync\.router\)") {
        throw "PC main.py does not have the expected sync router registration. Despatch data is mirrored, but PC UI was not modified."
    }
    if($mainText -notmatch "app\.include_router\(tiom_despatch\.router\)") {
        $needle="app.include_router(sync.router)"
        $patch=@"
$needle
from app.routers import tiom_despatch
from app.services import tiom_despatch_mail
app.include_router(tiom_despatch.router)
"@
        $mainText=$mainText.Replace($needle,$patch)
    }

    $indexText=[System.IO.File]::ReadAllText($index)
    if($indexText -notmatch "tiom_despatch\.css") {
        $indexText=$indexText.Replace("</head>",'<link rel="stylesheet" href="/static/tiom_despatch.css?v=pc-mirror-r1"></head>')
    }
    if($indexText -notmatch "tiom_despatch\.js") {
        $indexText=$indexText.Replace("</body>",'<script src="/static/tiom_despatch.js?v=pc-mirror-r1"></script></body>')
    }
    if($indexText -notmatch "tiom_despatch\.js" -or $mainText -notmatch "app\.include_router\(tiom_despatch\.router\)") {
        throw "Failed to prepare Despatch UI integration; existing PC pages were not touched."
    }

    # Stage Despatch-only source and verify syntax, then write Main/HTML.
    foreach($rel in $downloads) {
        if($rel -notlike "app/*") {continue}
        $from=Join-Path $pkg ($rel -replace "/", "\")
        $to=Join-Path $ProjectRoot ($rel -replace "/", "\")
        New-Item -ItemType Directory -Path (Split-Path -Parent $to) -Force | Out-Null
        Copy-Item -LiteralPath $from -Destination $to -Force
    }
    $tempMain=Join-Path $pkg "pc_main_candidate.py"
    [System.IO.File]::WriteAllText($tempMain,$mainText,[System.Text.UTF8Encoding]::new($false))
    & $python -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8-sig').read())" $tempMain
    if($LASTEXITCODE -ne 0) {throw "PC main module syntax test failed; original main.py remains unchanged."}

    [System.IO.File]::WriteAllText($main,$mainText,[System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($index,$indexText,[System.Text.UTF8Encoding]::new($false))
    Write-Host "PC Despatch API and Five Reports UI registered without changing WB sync files."

    # Scheduled task belongs only to Despatch. The existing every-3-min WB
    # scheduler, state files and token stay untouched.
    $taskName="NMTPL Despatch Mirror - Every 5 Minutes"
    # Use the console-free executable: python.exe produces a visible terminal
    # every five minutes when the task runs in the logged-on user's session.
    # Keep the exact same task interval, current user, pairing and database.
    $pythonw=Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path -LiteralPath $pythonw)) {
        throw "Windows background Python missing: $pythonw. Despatch was mirrored, but no visible-window scheduler was created."
    }
    $command='"'+$pythonw+'" "'+$worker+'"'
    & schtasks.exe /Create /TN $taskName /SC MINUTE /MO 5 /TR $command /F | Out-Host
    if($LASTEXITCODE -ne 0) {
        Write-Warning "Despatch data synced, but silent task creation failed. Existing WB tasks are unchanged."
    } else {
        Write-Host "Automatic Despatch mirror scheduled every 5 minutes without popup windows."
    }
    $status=Join-Path $tools "mirror_status.json"
    Write-Host ""
    Write-Host "Despatch database sync status:"
    Get-Content -LiteralPath $status | Out-Host
    Write-Host "SUCCESS: Despatch mirror installed independently from the WB engine."
    Write-Host "Restart your local TIOM web server to activate the new Despatch Report tab."
    Write-Host "Backup: $backup"
} finally {
    Remove-Item -LiteralPath $pkg -Recurse -Force -ErrorAction SilentlyContinue
}
