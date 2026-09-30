
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "A股盘面监控器 - GitHub 一键部署"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 GitHub CLI，尝试通过 winget 安装..."
    winget install --id GitHub.cli -e --source winget
    Write-Host "安装完成。请关闭当前 PowerShell 后重新运行本脚本。"
    exit
}

try {
    gh auth status | Out-Null
} catch {
    gh auth login --web
}

if (-not (Test-Path ".git")) {
    git init
}

git add .
git commit -m "init: a-share market monitor" 2>$null

$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0 -and $origin) {
    git branch -M main
    git push -u origin main
} else {
    $repoName = Read-Host "请输入新仓库名称（直接回车使用 a-share-market-monitor）"
    if ([string]::IsNullOrWhiteSpace($repoName)) {
        $repoName = "a-share-market-monitor"
    }
    gh repo create $repoName --public --source . --remote origin --push
}

Write-Host ""
Write-Host "部署成功，仓库地址："
gh repo view --json url -q .url
Write-Host ""
Write-Host "把这个仓库地址发给 ChatGPT。"
