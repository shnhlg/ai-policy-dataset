$ErrorActionPreference = 'Stop'

Write-Host 'AI Policy Dataset - GitHub bootstrap' -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is not installed. Install Git for Windows or GitHub Desktop first.'
}

git lfs install

if (-not (Test-Path '.git')) {
    git init
}

Write-Host 'Running repository verification...' -ForegroundColor Cyan
python scripts/verify_release.py

Write-Host ''
Write-Host 'Next commands:' -ForegroundColor Green
Write-Host '  git add .'
Write-Host '  git commit -m "Initial AI policy dataset release"'
Write-Host '  git branch -M main'
Write-Host '  git remote add origin https://github.com/<account>/<repo>.git'
Write-Host '  git push -u origin main'

