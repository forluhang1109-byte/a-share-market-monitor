$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "[1/3] 安装依赖..."
python -m pip install -r requirements.txt
Write-Host "[2/3] 运行单元测试..."
python tests/test_analytics.py
Write-Host "[3/3] 抓取当前盘面作为测试..."
python scripts/run_snapshot.py --session noon --skip-wait
Write-Host "完成。查看 data/latest_noon.json 和 reports/latest_noon.md"
