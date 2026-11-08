param(
    [switch]$ConfirmDelete
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$safeRoots = @(
    (Join-Path $projectRoot "remotion-engine\_draft_cache"),
    (Join-Path $projectRoot "remotion-engine\out"),
    (Join-Path $projectRoot "remotion-engine\node_modules\.cache"),
    (Join-Path $projectRoot "output\studio-voice-cache")
)
$jobRoot = Join-Path $projectRoot "output\studio-jobs"
$mediaExtensions = @(".mp4", ".webm", ".mov", ".avi", ".mkv", ".wav")

$targets = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
foreach ($root in $safeRoots) {
    if (Test-Path -LiteralPath $root) {
        Get-ChildItem -LiteralPath $root -File -Recurse -Force | ForEach-Object { $targets.Add($_) }
    }
}
if (Test-Path -LiteralPath $jobRoot) {
    Get-ChildItem -LiteralPath $jobRoot -File -Recurse -Force |
        Where-Object { $mediaExtensions -contains $_.Extension.ToLowerInvariant() } |
        ForEach-Object { $targets.Add($_) }
}

$uniqueTargets = $targets | Sort-Object FullName -Unique
$totalBytes = ($uniqueTargets | Measure-Object Length -Sum).Sum
if ($null -eq $totalBytes) { $totalBytes = 0 }

Write-Output ("Generated test-media files: {0}" -f $uniqueTargets.Count)
Write-Output ("Recoverable space: {0:N2} GB" -f ($totalBytes / 1GB))

if (-not $ConfirmDelete) {
    Write-Output "Preview only. Re-run with -ConfirmDelete to remove these generated files."
    exit 0
}

foreach ($file in $uniqueTargets) {
    Remove-Item -LiteralPath $file.FullName -Force
}

foreach ($root in $safeRoots) {
    if (Test-Path -LiteralPath $root) {
        Get-ChildItem -LiteralPath $root -Directory -Recurse -Force |
            Sort-Object FullName -Descending |
            Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) } |
            Remove-Item -Force
    }
}
if (Test-Path -LiteralPath $jobRoot) {
    Get-ChildItem -LiteralPath $jobRoot -Directory -Recurse -Force |
        Sort-Object FullName -Descending |
        Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) } |
        Remove-Item -Force
}

Write-Output "Generated test media removed. Source files and test reports were preserved."
