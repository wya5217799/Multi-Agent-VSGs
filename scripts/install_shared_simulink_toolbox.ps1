param(
  [string]$SharedRoot = 'C:\Users\27443\.shared-skills\simulink-toolbox',
  [string]$CodexPath  = 'C:\Users\27443\.codex\skills\simulink-toolbox',
  [string]$ClaudePath = 'C:\Users\27443\.claude\skills\simulink-toolbox',
  [string]$BackupRoot = 'C:\Users\27443\.shared-skills\backups',
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve absolute paths
$SharedRoot = [System.IO.Path]::GetFullPath($SharedRoot)
$CodexPath  = [System.IO.Path]::GetFullPath($CodexPath)
$ClaudePath = [System.IO.Path]::GetFullPath($ClaudePath)
$BackupRoot = [System.IO.Path]::GetFullPath($BackupRoot)

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = Join-Path $BackupRoot $timestamp

if ($DryRun) {
    Write-Host "DRY-RUN mode — no filesystem changes will be made."
    Write-Host "SHARED:  $SharedRoot"
    Write-Host "CODEX:   $CodexPath"
    Write-Host "CLAUDE:  $ClaudePath"
    Write-Host "BACKUP:  $BackupDir"
    exit 0
}

# Step 1: Create backup directory
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
Write-Host "BACKUP: $BackupDir"

# Step 2: Populate SharedRoot if it doesn't exist yet
if (-not (Test-Path $SharedRoot)) {
    $source = $null
    if (Test-Path $CodexPath) {
        $source = $CodexPath
        Write-Host "Seeding shared root from Codex copy: $source"
    } elseif (Test-Path $ClaudePath) {
        $source = $ClaudePath
        Write-Host "Seeding shared root from Claude copy: $source"
    } else {
        throw "Neither Codex nor Claude skill directories exist. Cannot seed shared root."
    }

    # Create parent of SharedRoot first
    $sharedParent = Split-Path $SharedRoot -Parent
    New-Item -ItemType Directory -Path $sharedParent -Force | Out-Null

    Copy-Item -Path $source -Destination $SharedRoot -Recurse -Force
    Write-Host "SHARED: $SharedRoot (seeded)"
} else {
    Write-Host "SHARED: $SharedRoot (already exists)"
}

# Step 3: Back up existing install directories before touching them
foreach ($installPath in @($CodexPath, $ClaudePath)) {
    if (Test-Path $installPath) {
        $backupTarget = Join-Path $BackupDir (Split-Path $installPath -Leaf)
        # If it's a junction, just record the target; if real dir, copy it
        $item = Get-Item -LiteralPath $installPath
        if ($item.LinkType -eq 'Junction') {
            $junctionTarget = $item.Target
            Set-Content -Path "$backupTarget.junction-target.txt" -Value $junctionTarget
            Write-Host "Backed up junction target for $(Split-Path $installPath -Leaf): $junctionTarget"
        } else {
            Copy-Item -Path $installPath -Destination $backupTarget -Recurse -Force
            Write-Host "Backed up real directory: $installPath -> $backupTarget"
        }
    }
}

# Step 4: Remove current install directories (after backup)
foreach ($installPath in @($CodexPath, $ClaudePath)) {
    if (Test-Path $installPath) {
        $item = Get-Item -LiteralPath $installPath
        if ($item.LinkType -eq 'Junction') {
            # Remove junction (cmd /c rmdir works cleanly for junctions without deleting target)
            cmd /c "rmdir `"$installPath`"" 2>&1 | Out-Null
        } else {
            Remove-Item -Path $installPath -Recurse -Force
        }
        Write-Host "Removed: $installPath"
    }
}

# Step 5: Create junctions
cmd /c "mklink /J `"$CodexPath`" `"$SharedRoot`"" 2>&1
cmd /c "mklink /J `"$ClaudePath`" `"$SharedRoot`"" 2>&1

# Step 6: Verify both paths resolve to the same canonical target
$codexItem  = Get-Item -LiteralPath $CodexPath  -ErrorAction Stop
$claudeItem = Get-Item -LiteralPath $ClaudePath -ErrorAction Stop

$codexResolved  = $codexItem.Target
$claudeResolved = $claudeItem.Target

if (-not $codexResolved -or -not $claudeResolved) {
    throw 'Expected both install paths to be junctions.'
}

$codexCanon  = [System.IO.Path]::GetFullPath($codexResolved[0])
$claudeCanon = [System.IO.Path]::GetFullPath($claudeResolved[0])

if ($codexCanon.ToLower() -ne $claudeCanon.ToLower()) {
    throw "Junction targets differ! Codex -> $codexCanon | Claude -> $claudeCanon"
}

Write-Host "CODEX:  ok ($codexCanon)"
Write-Host "CLAUDE: ok ($claudeCanon)"
Write-Host ""
Write-Host "Migration complete. Both install paths are junctions to the shared root."
