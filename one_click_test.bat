@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 安装依赖...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/3] 运行单元测试...
python tests\test_analytics.py
if errorlevel 1 goto :error

echo [3/3] 抓取当前盘面作为测试...
python scripts\run_snapshot.py --session noon --skip-wait
if errorlevel 1 goto :error

echo.
echo 完成。查看 data\latest_noon.json 和 reports\latest_noon.md
pause
exit /b 0

:error
echo.
echo 执行失败，请把上面的报错截图发给 ChatGPT。
pause
exit /b 1
