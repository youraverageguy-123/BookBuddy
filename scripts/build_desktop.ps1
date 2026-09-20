param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Artifacts = Join-Path $Root "artifacts"
$BackendDist = Join-Path $Artifacts "backend-dist"
$BackendWork = Join-Path $Artifacts "backend-build"
if (-not (Get-Command cargo -ErrorAction SilentlyContinue) -and -not $SkipInstaller) { throw "Rust/Cargo is required. Install Rust with rustup before building the Windows installer." }
$PnpmCommand = (Get-Command pnpm -ErrorAction SilentlyContinue).Source
if (-not $PnpmCommand) {
    $BundledPnpm = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
    if (Test-Path -LiteralPath $BundledPnpm) { $PnpmCommand = $BundledPnpm }
}
if (-not $PnpmCommand) { throw "pnpm is required. Install pnpm or add it to PATH before building the desktop installer." }
& $Python (Join-Path $Root "scripts\check_version.py")
if ($LASTEXITCODE -ne 0) { throw "BookBuddy version metadata is inconsistent." }
& $Python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Installing PyInstaller failed with exit code $LASTEXITCODE." }
& $Python -m PyInstaller --noconfirm --clean `
    --distpath $BackendDist `
    --workpath $BackendWork `
    (Join-Path $Root "packaging\bookbuddy-backend.spec")
if ($LASTEXITCODE -ne 0) { throw "Building the backend sidecar failed with exit code $LASTEXITCODE." }
$BuiltSidecar = Join-Path $BackendDist "bookbuddy-backend.exe"
$ArchiveViewer = Join-Path $Root "venv\Scripts\pyi-archive_viewer.exe"
$ArchiveListing = & $ArchiveViewer $BuiltSidecar -l 2>&1
if ($LASTEXITCODE -ne 0) { throw "Inspecting the backend sidecar failed with exit code $LASTEXITCODE." }
if (-not ($ArchiveListing -match 'config[\\/]+version\.json')) {
    throw "The backend sidecar is missing canonical version metadata (config/version.json)."
}
$Target = Join-Path $Root "frontend\src-tauri\binaries\bookbuddy-backend-x86_64-pc-windows-msvc.exe"
New-Item -ItemType Directory -Force (Split-Path -Parent $Target) | Out-Null
Copy-Item -Force $BuiltSidecar $Target
Push-Location (Join-Path $Root "frontend")
try {
    & $PnpmCommand install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw "Installing frontend dependencies failed with exit code $LASTEXITCODE." }
    if (-not $SkipInstaller) {
        & $PnpmCommand tauri build
        if ($LASTEXITCODE -ne 0) { throw "Building the desktop installer failed with exit code $LASTEXITCODE." }

        $Version = (Get-Content (Join-Path $Root "config\version.json") -Raw | ConvertFrom-Json).version
        $ReleaseExe = Join-Path $Root "frontend\src-tauri\target\release\bookbuddy.exe"
        $Installer = Join-Path $Root "frontend\src-tauri\target\release\bundle\nsis\BookBuddy_${Version}_x64-setup.exe"
        if (-not (Test-Path $ReleaseExe) -or -not (Test-Path $Installer)) {
            throw "The desktop executable or NSIS installer is missing after packaging."
        }

        $ReleaseRoot = Join-Path $Artifacts "releases"
        New-Item -ItemType Directory -Force $ReleaseRoot | Out-Null
        $PortableStage = Join-Path $ReleaseRoot ("portable-" + [guid]::NewGuid().ToString("N"))
        $PortableFolder = Join-Path $PortableStage "BookBuddy"
        New-Item -ItemType Directory -Force $PortableFolder | Out-Null
        try {
            Copy-Item -LiteralPath $ReleaseExe -Destination (Join-Path $PortableFolder "BookBuddy.exe")
            Copy-Item -LiteralPath $Installer -Destination (Join-Path $PortableFolder (Split-Path $Installer -Leaf))
            $PortableZip = Join-Path $ReleaseRoot "BookBuddy_${Version}_portable.zip"
            Compress-Archive -LiteralPath $PortableFolder -DestinationPath $PortableZip -Force

            $Downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"
            Copy-Item -LiteralPath $Installer -Destination (Join-Path $Root (Split-Path $Installer -Leaf)) -Force
            Copy-Item -LiteralPath $Installer -Destination (Join-Path $Downloads (Split-Path $Installer -Leaf)) -Force
            Copy-Item -LiteralPath $ReleaseExe -Destination (Join-Path $Downloads "BookBuddy.exe") -Force
            Copy-Item -LiteralPath $PortableZip -Destination (Join-Path $Downloads (Split-Path $PortableZip -Leaf)) -Force
        } finally {
            $ResolvedReleaseRoot = [IO.Path]::GetFullPath($ReleaseRoot).TrimEnd('\') + '\'
            $ResolvedStage = [IO.Path]::GetFullPath($PortableStage)
            if (-not $ResolvedStage.StartsWith($ResolvedReleaseRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Portable staging directory escaped the release artifact root."
            }
            if (Test-Path -LiteralPath $PortableStage) {
                Remove-Item -LiteralPath $PortableStage -Recurse -Force
            }
        }
    }
} finally { Pop-Location }
