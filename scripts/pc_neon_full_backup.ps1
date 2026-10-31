# NMTPL full Neon PostgreSQL backup. Runs ONLY on the office Windows PC.
# Windows PowerShell 5.1 compatible. No secrets in repository, logs or argv.
# First run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\pc_neon_full_backup.ps1 -InstallDaily
param([switch]$InstallDaily)

$ErrorActionPreference = "Stop"
$taskName = "NMTPL Neon Full Backup Daily"
$backupDir = Join-Path $env:USERPROFILE "Documents\NMTPL_Backups\Neon_Full"
$secretDir = Join-Path $env:APPDATA "NMTPL"
$secretFile = Join-Path $secretDir "neon_pg_uri.dpapi"
$scriptFile = $MyInvocation.MyCommand.Path

function Find-PgTool([string]$name) {
    $cmd = Get-Command "$name.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $root = "C:\Program Files\PostgreSQL"
    if (Test-Path $root) {
        $all = @(Get-ChildItem $root -Directory | Sort-Object Name -Descending)
        foreach ($dir in $all) {
            $file = Join-Path $dir.FullName "bin\$name.exe"
            if (Test-Path $file) { return $file }
        }
    }
    throw "$name.exe is missing. Install the PostgreSQL client command-line tools on the office PC."
}

function Read-Saved-NeonUri {
    if (-not (Test-Path $secretFile)) {
        New-Item -ItemType Directory -Path $secretDir -Force | Out-Null
        Write-Host "Enter the Neon DIRECT connection URL (not the -pooler URL). It is encrypted for your Windows account and never printed."
        $secure = Read-Host "Neon Direct URL" -AsSecureString
        if ($secure.Length -eq 0) { throw "Neon URL was not entered." }
        ($secure | ConvertFrom-SecureString) | Set-Content -Path $secretFile -Encoding ASCII
    }
    $encrypted = (Get-Content $secretFile -Raw).Trim()
    $secure = ConvertTo-SecureString $encrypted
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$dump = Find-PgTool "pg_dump"
$restore = Find-PgTool "pg_restore"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

$connection = Read-Saved-NeonUri
try {
    $uri = [Uri]$connection
    if ($uri.Scheme -notin @("postgres", "postgresql") -or
        -not $uri.Host.EndsWith(".neon.tech", [StringComparison]::OrdinalIgnoreCase) -or
        $uri.Host.Contains("-pooler") -or
        -not $uri.UserInfo.Contains(":")) {
        throw "Safety stop: the connection must be a Neon Direct PostgreSQL URL with user and password."
    }
    $parts = $uri.UserInfo.Split(":", 2)
    $pguser = [Uri]::UnescapeDataString($parts[0])
    $pgpass = [Uri]::UnescapeDataString($parts[1])
    $dbname = [Uri]::UnescapeDataString($uri.AbsolutePath.Trim("/"))
    if (-not $dbname) { throw "Database name is missing." }
    $port = if ($uri.IsDefaultPort) { 5432 } else { $uri.Port }
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $file = Join-Path $backupDir "TIOM_Neon_$stamp.dump"
    $env:PGPASSWORD = $pgpass
    $env:PGSSLMODE = "require"
    $env:PGCONNECT_TIMEOUT = "30"
    try {
        & $dump -h $uri.Host -p $port -U $pguser -d $dbname -Fc --no-owner --no-acl --file $file
        if ($LASTEXITCODE -ne 0) { throw "pg_dump exited with $LASTEXITCODE" }
        if ((Get-Item $file).Length -lt 100000) { throw "Backup file is suspiciously small." }
        $toc = & $restore --list $file
        if ($LASTEXITCODE -ne 0 -or -not $toc) { throw "pg_restore archive validation failed." }
        $digest = (Get-FileHash -Path $file -Algorithm SHA256).Hash
        $manifest = [pscustomobject]@{
            verifiedAt = (Get-Date).ToString("o")
            file = $file
            sizeBytes = (Get-Item $file).Length
            sha256 = $digest
            archiveTableOfContentsValidated = $true
            source = "Neon Direct"
        }
        $manifest | ConvertTo-Json | Set-Content -Path "$file.json" -Encoding UTF8
        Write-Host "BACKUP VERIFIED: $file"
        Write-Host "SHA-256: $digest"
    }
    catch {
        if (Test-Path $file) { Remove-Item $file -Force }
        throw
    }
    finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        Remove-Item Env:\PGSSLMODE -ErrorAction SilentlyContinue
        Remove-Item Env:\PGCONNECT_TIMEOUT -ErrorAction SilentlyContinue
    }
} finally {
    $connection = $null
    $pgpass = $null
}
if ($InstallDaily) {
    if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
        throw "The verified dump exists, but Task Scheduler is unavailable."
    }
    $cmd = (Get-Command powershell.exe).Source
    $args = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $scriptFile + '"'
    $action = New-ScheduledTaskAction -Execute $cmd -Argument $args
    $trigger = New-ScheduledTaskTrigger -Daily -At 6:30AM
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "SCHEDULE INSTALLED: $taskName (daily 06:30, starts when available; Windows user must be signed in)."
}
