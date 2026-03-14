# Recapture all HTML snapshots in both DE and EN languages
# Usage: .\scripts\recapture-snapshots.ps1

$ErrorActionPreference = "Stop"

$snapshotsDir = Join-Path $PSScriptRoot "..\unittests\testdata\html_snapshots"
$envFile = Join-Path $PSScriptRoot "..\.env"

# Read current SAP_LANGUAGE from .env
$originalLanguage = "DE"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match 'SAP_LANGUAGE=(\w+)') {
        $originalLanguage = $Matches[1]
    }
}

Write-Host "Current SAP_LANGUAGE: $originalLanguage" -ForegroundColor Cyan

# Delete all existing snapshots (except README.md)
Write-Host "`nDeleting existing snapshots..." -ForegroundColor Yellow
Get-ChildItem -Path $snapshotsDir -Filter "*.html" | Remove-Item -Force
Write-Host "Deleted all *.html files in $snapshotsDir"

# Function to update SAP_LANGUAGE in .env
function Set-SapLanguage {
    param([string]$lang)

    $content = Get-Content $envFile -Raw
    $content = $content -replace 'SAP_LANGUAGE=\w+', "SAP_LANGUAGE=$lang"
    Set-Content $envFile -Value $content -NoNewline
    Write-Host "Set SAP_LANGUAGE=$lang in .env" -ForegroundColor Green
}

# Function to run integration tests
function Invoke-IntegrationTests {
    param([string]$lang)

    Write-Host "`n=== Capturing $lang snapshots ===" -ForegroundColor Cyan
    Set-SapLanguage $lang

    # Run all integration tests to capture snapshots
    python -m pytest unittests/ -k integration -v --tb=short

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: Some tests failed for $lang" -ForegroundColor Yellow
    }
}

try {
    # Capture German snapshots
    Invoke-IntegrationTests "DE"

    # Capture English snapshots
    Invoke-IntegrationTests "EN"

    Write-Host "`n=== Snapshot capture complete ===" -ForegroundColor Green

    # List captured snapshots
    Write-Host "`nCaptured snapshots:"
    Get-ChildItem -Path $snapshotsDir -Filter "*.html" | ForEach-Object {
        Write-Host "  - $($_.Name)"
    }
}
finally {
    # Restore original language
    Set-SapLanguage $originalLanguage
    Write-Host "`nRestored SAP_LANGUAGE=$originalLanguage" -ForegroundColor Cyan
}
