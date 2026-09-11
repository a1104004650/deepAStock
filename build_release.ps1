# deepAStock release package builder
# Usage: powershell -ExecutionPolicy Bypass -File build_release.ps1
# Output: release/deepAStock-v1.0.0.zip (deploy with: docker compose up -d --build)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Version = "1.1.2"
$PkgName = "deepAStock-v$Version"
$ReleaseDir = Join-Path $Root "release"
$PkgDir = Join-Path $ReleaseDir $PkgName
$ZipPath = Join-Path $ReleaseDir "$PkgName.zip"

Write-Host "==> [1/3] building frontend (npm run build)"
Push-Location (Join-Path $Root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
Pop-Location

Write-Host "==> [2/3] assembling package -> $PkgDir"
if (Test-Path $PkgDir) { Remove-Item -Recurse -Force $PkgDir }
New-Item -ItemType Directory -Path $PkgDir -Force | Out-Null

# backend (exclude runtime data / caches / venv)
$backend = Join-Path $Root "backend"
$backendDest = Join-Path $PkgDir "backend"
robocopy $backend $backendDest /E /XD "__pycache__" "data" ".venv" "venv" ".pytest_cache" /XF "*.pyc" /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -gt 7) { throw "backend copy failed (robocopy exit $LASTEXITCODE)" }

# frontend (built assets only, no node_modules)
$fe = Join-Path $Root "frontend"
New-Item -ItemType Directory -Path (Join-Path $PkgDir "frontend") -Force | Out-Null
Copy-Item (Join-Path $fe "dist") (Join-Path $PkgDir "frontend\dist") -Recurse
Copy-Item (Join-Path $fe "index.html") (Join-Path $PkgDir "frontend\index.html")
Copy-Item (Join-Path $fe "package.json") (Join-Path $PkgDir "frontend\package.json")
New-Item -ItemType Directory -Path (Join-Path $PkgDir "frontend\public") -Force | Out-Null
Copy-Item (Join-Path $fe "public\favicon.svg") (Join-Path $PkgDir "frontend\public\favicon.svg")

# docker deployment kit + docs
foreach ($f in @("Dockerfile", "docker-compose.yml", "nginx.conf", "supervisord.conf", ".dockerignore", "README.md", "CHANGELOG.md", "start.bat")) {
    Copy-Item (Join-Path $Root $f) (Join-Path $PkgDir $f)
}

Write-Host "==> [3/3] zipping -> $ZipPath"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $PkgDir "*") -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Package ready: $ZipPath"
Write-Host ""
Write-Host "HOW TO DEPLOY (no Python/Node/DB needed):"
Write-Host "  1. unzip  $PkgName.zip"
Write-Host "  2. cd $PkgName && docker compose up -d --build"
Write-Host "  3. open http://localhost:18080  (API docs: http://localhost:18000/docs)"
Write-Host "  4. RSSHub subscribe page: http://localhost:11200  (managed in 界面「设置 → RSSHub 订阅」)"
Write-Host ""
Write-Host "Database: default SQLite (volume backend_data, survives rebuild)."
Write-Host "To use your own PostgreSQL: edit docker-compose.yml, uncomment"
Write-Host "DATABASE_URL/USE_POSTGRES, then: docker compose --profile postgres up -d --build"

# cleanup temp dir (optional)
$reply = Read-Host "Press Enter to clean temp dir and exit [y/N]"
if ($reply -match '^y') { if (Test-Path $PkgDir) { Remove-Item -Recurse -Force $PkgDir } }