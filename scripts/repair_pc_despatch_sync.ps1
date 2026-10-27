#requires -Version 5.1
param(
    [string]$ProjectRoot = "E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1",
    [switch]$SkipSourceUpdate
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "PC TIOM project folder not found: $ProjectRoot"
}
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $ProjectRoot ("backups\despatch_pc_upgrade_" + $timestamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Write-Host "PC TIOM : $ProjectRoot"
Write-Host "Backup  : $backup"
if (-not $SkipSourceUpdate) {
    $gitExe = Get-Command git.exe -ErrorAction SilentlyContinue
    $isRepo = $false
    if ($gitExe) {
        & $gitExe.Source -C $ProjectRoot rev-parse --is-inside-work-tree 2>$null | Out-Null
        $isRepo = $LASTEXITCODE -eq 0
    }
    if ($isRepo) {
        $remote = (& $gitExe.Source -C $ProjectRoot remote get-url origin).Trim()
        if ($remote -notmatch "bikashnyk87-stack/nmtpl") {
            throw "Unexpected Git remote; no code was changed: $remote"
        }
        $branch = (& $gitExe.Source -C $ProjectRoot rev-parse --abbrev-ref HEAD).Trim()
        if ($branch -ne "main") { throw "PC Git branch is $branch, not main. No update was attempted." }
        $dirty = @(& $gitExe.Source -C $ProjectRoot status --porcelain --untracked-files=no)
        if ($dirty.Count -gt 0 -and ($dirty -join "").Trim()) {
            $dirty | Set-Content -Path (Join-Path $backup "git_local_changes.txt")
            throw "Local tracked code differs; saved changed-file list to backup. No overwrite attempted."
        }
        & $gitExe.Source -C $ProjectRoot fetch origin main
        if ($LASTEXITCODE -ne 0) { throw "Git fetch failed" }
        & $gitExe.Source -C $ProjectRoot merge --ff-only origin/main
        if ($LASTEXITCODE -ne 0) { throw "Fast-forward-only code update failed. No forced reset used." }
        Write-Host "Latest TIOM source updated safely from Git main."
    } else {
        # Older PC installations were ZIP copies rather than Git checkouts.
        # Back up source, update only app/ and scripts/; NEVER copy over DB,
        # .env, credentials, device token, images, logs, or sync state.
        $zip = Join-Path $env:TEMP ("nmtpl_pc_despatch_" + $timestamp + ".zip")
        $tmp = Join-Path $env:TEMP ("nmtpl_pc_despatch_" + $timestamp)
        Write-Host "No Git checkout found. Backing up PC application source before ZIP code refresh."
        foreach ($item in @("app", "scripts")) {
            $source = Join-Path $ProjectRoot $item
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination (Join-Path $backup $item) -Recurse -Force
            }
        }
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/bikashnyk87-stack/nmtpl/archive/refs/heads/main.zip" -OutFile $zip
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            $sourceRoot = Join-Path $tmp "nmtpl-main"
            foreach ($item in @("app", "scripts")) {
                $src = Join-Path $sourceRoot $item
                if (-not (Test-Path -LiteralPath $src)) { throw "Source package missing $item" }
                Copy-Item -Path (Join-Path $src "*") -Destination (Join-Path $ProjectRoot $item) -Recurse -Force
            }
            Write-Host "PC application code updated; existing local data/config remain untouched."
        } finally {
            Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
$venv = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venv) {
    $python = $venv
} else {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}
Push-Location $ProjectRoot
try {
    Write-Host "Running non-destructive PC sync + Despatch historical backfill..."
    & $python (Join-Path $ProjectRoot "scripts\pull_render_sync.py")
    if ($LASTEXITCODE -ne 0) {
        throw "PC sync reported an error. Check logs\render_sync\worker.log. No sync watermark was reset."
    }
    Write-Host ""
    Write-Host "Checking local Despatch trip counts and four mirror tables..."
    & $python (Join-Path $ProjectRoot "scripts\check_pc_despatch_sync.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Despatch mirror verification incomplete; review the diagnostics printed above."
    }
    Write-Host ""
    Write-Host "PC Despatch database sync verified. Existing WB records and state were preserved."
    Write-Host "IMPORTANT: restart the local TIOM/Uvicorn server process to load the updated Despatch UI."
} finally {
    Pop-Location
}
