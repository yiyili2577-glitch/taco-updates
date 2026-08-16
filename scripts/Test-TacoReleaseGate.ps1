[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Package,
    [Parameter(Mandatory)] [string] $Version,
    [Parameter(Mandatory)] [string] $RcTag,
    [Parameter(Mandatory)] [string] $WorkDir,
    [Parameter(Mandatory)] [string] $ReportPath,
    [Parameter(Mandatory)] [string] $ChecksumPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) { throw $Message }
}

function Write-Utf8Text {
    param([string] $Path, [string] $Value)
    $parent = Split-Path -Parent $Path
    if ($parent) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false))
}

function Reset-Directory {
    param([string] $Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    [IO.Directory]::CreateDirectory($Path) | Out-Null
}

function Get-FileManifest {
    param([string] $Root)
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $result = [ordered]@{}
    Get-ChildItem -LiteralPath $rootPath -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($rootPath.Length).TrimStart('\').Replace('\', '/')
            $result[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    return $result
}

function Assert-ManifestsEqual {
    param($Expected, $Actual, [string] $Message)
    Assert-True ($Expected.Count -eq $Actual.Count) "$Message (file count differs)"
    foreach ($path in $Expected.Keys) {
        Assert-True $Actual.Contains($path) "$Message (missing $path)"
        Assert-True ($Expected[$path] -eq $Actual[$path]) "$Message (hash differs: $path)"
    }
}

function Get-HistoryActions {
    param([string] $HistoryDir)
    $path = Join-Path $HistoryDir 'update_history.json'
    Assert-True (Test-Path -LiteralPath $path) "Updater history was not created: $path"
    return @((Get-Content -LiteralPath $path -Raw | ConvertFrom-Json) | ForEach-Object action)
}

function Invoke-TacoUpdater {
    param(
        [string] $Updater,
        [string] $UpdatePackage,
        [string] $InstallDir,
        [string] $BackupDir,
        [string] $HistoryDir,
        [string] $Sha256,
        [switch] $CloseErrorDialog
    )
    [IO.Directory]::CreateDirectory($BackupDir) | Out-Null
    [IO.Directory]::CreateDirectory($HistoryDir) | Out-Null
    $arguments = @(
        '--package', ('"' + $UpdatePackage + '"'),
        '--install-dir', ('"' + $InstallDir + '"'),
        '--backup-dir', ('"' + $BackupDir + '"'),
        '--history-dir', ('"' + $HistoryDir + '"'),
        '--sha256', $Sha256
    )
    $process = Start-Process -FilePath $Updater -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(120)
    while (-not $process.HasExited -and (Get-Date) -lt $deadline) {
        if ($CloseErrorDialog) {
            $historyPath = Join-Path $HistoryDir 'update_history.json'
            if (Test-Path -LiteralPath $historyPath) {
                try {
                    $actions = @((Get-Content -LiteralPath $historyPath -Raw | ConvertFrom-Json) | ForEach-Object action)
                    if ($actions -contains 'fatal') {
                        $process.Refresh()
                        if ($process.MainWindowHandle -ne 0) { [void] $process.CloseMainWindow() }
                    }
                } catch { }
            }
        }
        if (-not $process.HasExited) { Start-Sleep -Milliseconds 250 }
    }
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        throw 'Updater did not exit within 120 seconds'
    }
    return $process.ExitCode
}

function Initialize-OldAppFixture {
    param([string] $InstallDir)
    Reset-Directory $InstallDir
    [IO.File]::WriteAllBytes((Join-Path $InstallDir 'TACO.exe'), [byte[]](0x4d, 0x5a, 0x90, 0x00))
    Write-Utf8Text (Join-Path $InstallDir 'BUILD_VERSION.txt') "6.9.0`n"
    Write-Utf8Text (Join-Path $InstallDir 'OLD_ONLY_SENTINEL.txt') "must be removed on success and restored on failure`n"
    [IO.Directory]::CreateDirectory((Join-Path $InstallDir 'legacy')) | Out-Null
    Write-Utf8Text (Join-Path $InstallDir 'legacy\settings.json') "{`"fixture`":true}`n"
}

function Test-RcPackage {
    param([string] $ZipPath, [string] $ExpectedVersion)
    Add-Type -AssemblyName System.IO.Compression
    $bannedNames = @(
        'license_private_key.pem', 'update_private_key.pem', 'licenses.db',
        '.env', 'id_rsa', 'id_ed25519'
    )
    $bannedExtensions = @('.pfx', '.p12', '.key')
    $textExtensions = @('.pem', '.txt', '.json', '.env', '.ini', '.cfg', '.yaml', '.yml', '.toml', '.py', '.ps1', '.xml')
    $privateKeyMarkers = @('-----BEGIN PRIVATE KEY-----', '-----BEGIN OPENSSH PRIVATE KEY-----', '-----BEGIN RSA PRIVATE KEY-----')
    $required = @('TACO.exe', 'BUILD_VERSION.txt', 'TACOUpdater/TACOUpdater.exe')
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    [int64] $totalBytes = 0
    $exeCount = 0
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $archive.Entries) {
            $raw = $entry.FullName.Replace('\', '/')
            $parts = $raw.Split('/', [StringSplitOptions]::RemoveEmptyEntries)
            Assert-True (-not $raw.StartsWith('/') -and $raw -notmatch '^[A-Za-z]:/' -and $parts -notcontains '..') "Unsafe ZIP path: $raw"
            if ($entry.Name -eq '') { continue }
            [void] $seen.Add($raw)
            $name = $entry.Name.ToLowerInvariant()
            $extension = [IO.Path]::GetExtension($name).ToLowerInvariant()
            Assert-True ($bannedNames -notcontains $name -and $bannedExtensions -notcontains $extension) "Forbidden secret/key material in RC: $raw"
            Assert-True ($raw -notmatch '(^|/)(secret|secrets)(/|$)') "Forbidden secret directory in RC: $raw"
            $totalBytes += $entry.Length
            Assert-True ($totalBytes -le 2GB) 'RC uncompressed size exceeds 2 GiB safety limit'
            if ($extension -eq '.exe') { $exeCount++ }

            # Reading every entry to EOF makes the ZIP implementation verify decompression/CRC.
            $stream = $entry.Open()
            try {
                $memory = if ($entry.Length -le 8MB -and $textExtensions -contains $extension) { [IO.MemoryStream]::new() } else { $null }
                try {
                    $buffer = [byte[]]::new(1MB)
                    while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                        if ($memory) { $memory.Write($buffer, 0, $read) }
                    }
                    if ($memory) {
                        $text = [Text.Encoding]::UTF8.GetString($memory.ToArray())
                        foreach ($marker in $privateKeyMarkers) {
                            Assert-True (-not $text.Contains($marker, [StringComparison]::Ordinal)) "Private-key PEM marker found in RC: $raw"
                        }
                    }
                } finally {
                    if ($memory) { $memory.Dispose() }
                }
            } finally {
                $stream.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
    }
    foreach ($path in $required) { Assert-True $seen.Contains($path) "RC package is missing required path: $path" }
    Assert-True ($exeCount -gt 0) 'RC package contains no Windows executable'

    return [ordered]@{
        zip_crc = 'PASS'
        path_traversal_check = 'PASS'
        secret_material_check = 'PASS'
        windows_executable_check = 'PASS'
        required_layout_check = 'PASS'
        executable_count = $exeCount
        uncompressed_bytes = $totalBytes
    }
}

function Test-SchemaMigration {
    param([string] $TacoExe, [string] $Root, [string] $ExpectedVersion)
    Reset-Directory $Root
    $dataDir = Join-Path $Root 'Data'
    [IO.Directory]::CreateDirectory($dataDir) | Out-Null
    $fixtures = [ordered]@{
        'product_master.json' = "[]`n"
        'suppliers.json' = "[{`"supplier_id`":`"GATE-SUPPLIER`",`"name`":`"Release Gate`"}]`n"
        'warehouse_inventory.json' = "[{`"sku`":`"GATE-SKU`",`"quantity`":7}]`n"
        'finance_data.json' = "{`"gate_sentinel`":611}`n"
    }
    foreach ($item in $fixtures.GetEnumerator()) { Write-Utf8Text (Join-Path $dataDir $item.Key) $item.Value }
    Write-Utf8Text (Join-Path $dataDir 'schema_version.json') "{`n  `"schema_version`": 3,`n  `"app_version`": `"6.9.0`",`n  `"updated_at`": `"2026-01-01T00:00:00`"`n}`n"
    $before = Get-FileManifest $dataDir
    [void] $before.Remove('schema_version.json')

    $environment = @{
        TACO_RUNTIME_ROOT = $Root
        QT_QPA_PLATFORM = 'offscreen'
    }
    $process = Start-Process -FilePath $TacoExe -WorkingDirectory (Split-Path $TacoExe) -Environment $environment -PassThru -WindowStyle Hidden
    $schemaPath = Join-Path $dataDir 'schema_version.json'
    $deadline = (Get-Date).AddSeconds(90)
    $migrated = $false
    try {
        while ((Get-Date) -lt $deadline) {
            if (Test-Path -LiteralPath $schemaPath) {
                try {
                    $schema = Get-Content -LiteralPath $schemaPath -Raw | ConvertFrom-Json
                    if ([int] $schema.schema_version -eq 5) { $migrated = $true; break }
                } catch { }
            }
            if ($process.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
    Assert-True $migrated 'TACO.exe did not migrate schema 3 to 5 within 90 seconds'
    $schema = Get-Content -LiteralPath $schemaPath -Raw | ConvertFrom-Json
    Assert-True ([int] $schema.schema_version -eq 5) 'Final schema version is not 5'
    Assert-True ([string] $schema.app_version -eq $ExpectedVersion) 'Migration app_version does not match the RC version'

    $after = Get-FileManifest $dataDir
    [void] $after.Remove('schema_version.json')
    [void] $after.Remove('integration.db')
    Assert-ManifestsEqual $before $after 'Schema migration modified legacy business JSON'
    $backup = @(Get-ChildItem -LiteralPath (Join-Path $Root 'Backups') -Filter 'SCHEMA_PRE_3_TO_5_*.zip' -File)
    Assert-True ($backup.Count -ge 1) 'Schema migration did not create a pre-migration backup'

    $database = Join-Path $dataDir 'integration.db'
    Assert-True (Test-Path -LiteralPath $database) 'Schema 5 integration.db was not created'
    $python = @'
import json, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
required = {
    'barcode_bindings', 'container_bindings', 'location_inventory',
    'mapping_profiles', 'master_data_items', 'product_location_rules',
    'product_master_v2', 'scan_events', 'scan_session_items',
    'scan_sessions', 'sync_queue', 'warehouse_locations'
}
missing = sorted(required - tables)
print(json.dumps({'integrity': integrity, 'missing': missing}, separators=(',', ':')))
if integrity != 'ok' or missing:
    raise SystemExit(1)
'@
    $dbResult = $python | python - $database
    Assert-True ($LASTEXITCODE -eq 0) "integration.db validation failed: $dbResult"

    return [ordered]@{
        schema_3_to_5 = 'PASS'
        migration_data_integrity = 'PASS'
        migration_backup = 'PASS'
        integration_db_integrity = 'PASS'
    }
}

function Test-SuccessfulReplacement {
    param([string] $Updater, [string] $ZipPath, [string] $Extracted, [string] $Root, [string] $ExpectedVersion, [string] $PackageHash)
    Reset-Directory $Root
    $install = Join-Path $Root 'OLD_APP'
    $backup = Join-Path $Root 'backups'
    $history = Join-Path $Root 'history'
    Initialize-OldAppFixture $install
    $exitCode = Invoke-TacoUpdater $Updater $ZipPath $install $backup $history $PackageHash
    Assert-True ($exitCode -eq 0) "Successful updater test returned exit code $exitCode"
    Assert-True ((Get-Content -LiteralPath (Join-Path $install 'BUILD_VERSION.txt') -Raw).Trim() -eq $ExpectedVersion) 'Updater did not install the expected BUILD_VERSION'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $install 'OLD_ONLY_SENTINEL.txt'))) 'Successful replacement left an old-only file behind'
    Assert-ManifestsEqual (Get-FileManifest $Extracted) (Get-FileManifest $install) 'Installed files differ from the validated RC payload'
    $actions = Get-HistoryActions $history
    Assert-True ($actions -contains 'apply_started' -and $actions -contains 'apply_success') 'Successful updater history is incomplete'
    Assert-True (@(Get-ChildItem -LiteralPath $backup -Filter 'APP_UPDATE_PRE_*.zip' -File).Count -ge 1) 'Successful updater did not create a pre-update backup'
    return [ordered]@{
        successful_updater_replacement = 'PASS'
        successful_updater_exit_code = 'PASS'
        successful_updater_history = 'PASS'
        successful_updater_backup = 'PASS'
    }
}

function Test-ForcedFailureRollback {
    param([string] $Updater, [string] $Extracted, [string] $Root)
    Reset-Directory $Root
    $install = Join-Path $Root 'OLD_APP'
    $backup = Join-Path $Root 'backups'
    $history = Join-Path $Root 'history'
    $badStage = Join-Path $Root 'bad-package'
    $badZip = Join-Path $Root 'TACO_Update_FORCED_FAILURE.zip'
    Initialize-OldAppFixture $install
    $expected = Get-FileManifest $install

    [IO.Directory]::CreateDirectory($badStage) | Out-Null
    Copy-Item -Path (Join-Path $Extracted '*') -Destination $badStage -Recurse -Force
    $badExe = Join-Path $badStage 'TACO.exe'
    Assert-True (Test-Path -LiteralPath $badExe) 'Cannot build forced-failure package: source TACO.exe is missing'
    Remove-Item -LiteralPath $badExe -Force
    Compress-Archive -Path (Join-Path $badStage '*') -DestinationPath $badZip -CompressionLevel Optimal
    $badHash = (Get-FileHash -LiteralPath $badZip -Algorithm SHA256).Hash

    $exitCode = Invoke-TacoUpdater $Updater $badZip $install $backup $history $badHash -CloseErrorDialog
    Assert-True ($exitCode -ne 0) 'Forced-failure updater test unexpectedly returned exit code 0'
    $actions = Get-HistoryActions $history
    foreach ($action in @('apply_started', 'apply_failed', 'rollback_success', 'fatal')) {
        Assert-True ($actions -contains $action) "Forced-failure updater history is missing $action"
    }
    Assert-ManifestsEqual $expected (Get-FileManifest $install) 'Rollback did not restore the old app byte-for-byte'
    Assert-True (@(Get-ChildItem -LiteralPath $backup -Filter 'APP_UPDATE_PRE_*.zip' -File).Count -ge 1) 'Forced-failure updater did not create a pre-update backup'
    return [ordered]@{
        forced_failure_rollback = 'PASS'
        rollback_exit_code = 'PASS'
        rollback_history = 'PASS'
        rollback_byte_for_byte = 'PASS'
    }
}

Assert-True ($Version -match '^\d+\.\d+\.\d+$') 'Invalid version'
Assert-True ($RcTag -eq "rc-$Version") 'rc_tag must be exactly rc-<version>'
$packagePath = (Resolve-Path -LiteralPath $Package).Path
$workPath = [IO.Path]::GetFullPath($WorkDir)
Reset-Directory $workPath
$extractPath = Join-Path $workPath 'payload'
[IO.Directory]::CreateDirectory($extractPath) | Out-Null

$results = [ordered]@{}
$packageResults = Test-RcPackage $packagePath $Version
$packageResults.GetEnumerator() | ForEach-Object { $results[$_.Key] = $_.Value }
Expand-Archive -LiteralPath $packagePath -DestinationPath $extractPath
Assert-True ((Get-Content -LiteralPath (Join-Path $extractPath 'BUILD_VERSION.txt') -Raw).Trim() -eq $Version) 'RC BUILD_VERSION does not match workflow input'
$results['build_version_check'] = 'PASS'

$packageHash = (Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
$tacoExe = Join-Path $extractPath 'TACO.exe'
$updater = Join-Path $extractPath 'TACOUpdater\TACOUpdater.exe'
$migrationResults = Test-SchemaMigration $tacoExe (Join-Path $workPath 'migration') $Version
$migrationResults.GetEnumerator() | ForEach-Object { $results[$_.Key] = $_.Value }
$successResults = Test-SuccessfulReplacement $updater $packagePath $extractPath (Join-Path $workPath 'success') $Version $packageHash
$successResults.GetEnumerator() | ForEach-Object { $results[$_.Key] = $_.Value }
$rollbackResults = Test-ForcedFailureRollback $updater $extractPath (Join-Path $workPath 'rollback')
$rollbackResults.GetEnumerator() | ForEach-Object { $results[$_.Key] = $_.Value }

$reportLines = [Collections.Generic.List[string]]::new()
$reportLines.Add('TACO Automated Release Gate')
$reportLines.Add("version=$Version")
$reportLines.Add("rc_tag=$RcTag")
$reportLines.Add("validated_at_utc=$([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))")
$reportLines.Add("workflow_run_id=$env:GITHUB_RUN_ID")
$reportLines.Add("workflow_run_attempt=$env:GITHUB_RUN_ATTEMPT")
$reportLines.Add("package=$([IO.Path]::GetFileName($packagePath))")
$reportLines.Add("sha256=$packageHash")
foreach ($item in $results.GetEnumerator()) { $reportLines.Add("$($item.Key)=$($item.Value)") }
$reportLines.Add('result=PASS')
Write-Utf8Text $ReportPath (($reportLines -join "`n") + "`n")
Write-Utf8Text $ChecksumPath "$packageHash  $([IO.Path]::GetFileName($packagePath))`n"

Write-Host 'All TACO automated release gates PASS.'
Get-Content -LiteralPath $ReportPath
