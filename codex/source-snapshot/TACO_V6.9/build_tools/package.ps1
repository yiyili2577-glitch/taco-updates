$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = (Get-Content (Join-Path $Root "desktop_app\VERSION") -Raw).Trim()
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
$Python = if ($PythonCommand) { $PythonCommand.Source } else {
  "C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Python runtime not found" }

Push-Location $Root
try {
  & $Python -m compileall -q desktop_app tests
  if ($LASTEXITCODE -ne 0) { throw "Compile failed" }
  & $Python -m unittest discover -s tests -v
  if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

  $Out = Join-Path $Root "artifacts"
  New-Item -ItemType Directory -Force -Path $Out | Out-Null
  $Zip = Join-Path $Out "TACO_V$Version`_Complete.zip"
  if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip }

  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $Archive = [System.IO.Compression.ZipFile]::Open($Zip, [System.IO.Compression.ZipArchiveMode]::Create)
  try {
    $Files = Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
      $Relative = $_.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
      $Relative -notmatch '(^|/)artifacts/' -and
      $Relative -notmatch '(^|/)__pycache__/' -and
      $_.Extension -notin @('.pyc', '.pyo', '.pem', '.key', '.db', '.sqlite', '.sqlite3') -and
      $_.Name -notmatch '(?i)(private.?key|licenses\.db)'
    }
    foreach ($File in $Files) {
      $EntryName = $File.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
      [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $Archive, $File.FullName, $EntryName, [System.IO.Compression.CompressionLevel]::Optimal
      ) | Out-Null
    }
  } finally {
    $Archive.Dispose()
  }

  $Forbidden = [System.IO.Compression.ZipFile]::OpenRead($Zip)
  try {
    $Bad = @($Forbidden.Entries | Where-Object {
      $_.FullName -match '(^|/)__pycache__/' -or
      $_.FullName -match '(?i)(private.?key|licenses\.db)' -or
      [System.IO.Path]::GetExtension($_.FullName) -in @('.pyc', '.pyo', '.pem', '.key', '.db', '.sqlite', '.sqlite3')
    })
    if ($Bad.Count -gt 0) { throw "Forbidden file in ZIP: $($Bad[0].FullName)" }
  } finally {
    $Forbidden.Dispose()
  }

  $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash.ToLowerInvariant()
  Set-Content -Encoding utf8 (Join-Path $Out "PACKAGE_SHA256_V6.9.txt") "$Hash  TACO_V$Version`_Complete.zip"
  Write-Host "ZIP=$Zip"
  Write-Host "SHA256=$Hash"
} finally {
  Pop-Location
}
