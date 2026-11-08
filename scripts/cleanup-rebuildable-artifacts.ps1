$ErrorActionPreference = "Stop"
$workspace = [System.IO.Path]::GetFullPath("D:\Agent")
$targets = @(
    "D:\Agent\output",
    "D:\Agent\sites\ai-clip-studio\dist",
    "D:\Agent\sites\ai-clip-studio\.next",
    "D:\Agent\sites\ai-clip-studio\.wrangler",
    "D:\Agent\sites\ai-clip-studio\.vinext",
    "D:\Agent\remotion-engine\debug.log",
    "D:\Agent\vie-agentic-skills\.git\objects\pack\tmp_pack_rivMCu",
    "D:\Agent\context-optimizer\output\cleaned.log",
    "D:\Agent\context-optimizer\samples\ffmpeg.log"
)

$validated = @()
foreach ($target in $targets) {
    $full = [System.IO.Path]::GetFullPath($target)
    if (-not $full.StartsWith($workspace + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe cleanup target: $full"
    }
    if (Test-Path -LiteralPath $full) { $validated += $full }
}

$bytes = 0
foreach ($item in $validated) {
    $entry = Get-Item -LiteralPath $item
    if ($entry.PSIsContainer) {
        $bytes += (Get-ChildItem -LiteralPath $item -File -Recurse -Force | Measure-Object Length -Sum).Sum
    } else {
        $bytes += $entry.Length
    }
}

Write-Output ("Deleting {0} rebuildable targets ({1:N1} MB)" -f $validated.Count, ($bytes / 1MB))
foreach ($item in $validated) {
    Remove-Item -LiteralPath $item -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $workspace "output") -Force | Out-Null
Write-Output "Rebuildable artifacts removed."
