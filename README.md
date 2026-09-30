
## Windows CMD 编码修正版

如果旧版 `one_click_deploy_github.bat` 打开后出现乱码，请使用：

```text
DEPLOY_GITHUB_FIXED.bat
```

v0.3 中该脚本使用纯 ASCII + CRLF，兼容 Windows CMD，并会自动检查 Git、GitHub CLI 和 GitHub 登录状态。


# A 股实时盘面监控器

目标：每天自动抓取 A 股盘面数据，生成结构化 JSON + Markdown 报告，供 ChatGPT 在午盘和 14:40 结合你的最新持仓分析。

## 自动时间（北京时间）

- 午盘：GitHub Actions 约 11:25 启动，程序等待到 11:31 后抓取
- 尾盘：GitHub Actions 约 14:30 启动，程序等待到 14:36 后抓取
- GitHub Actions 定时任务可能排队，所以提前启动并在程序内等待

## 数据内容

- 上证指数、深证成指、创业板指、科创 50
- 全 A 上涨/下跌/平盘家数
- 当前全 A 累计成交额
- 与上一交易日同一时段快照比较的放量/缩量
- 涨停/跌停数量（接口可用时）
- 行业/概念板块涨跌与主力资金流
- 大盘资金流（接口可用时）
- 持仓主题匹配、强弱评分、条件化操作参考

## 数据源

默认通过 AKShare 调度公开行情接口：
1. 东方财富优先
2. 腾讯/新浪作为实时 A 股行情备用
3. 所有关键接口均做异常降级，单个接口失败不会让整个报告报废

> 免费公开行情源存在限流、字段变化或临时不可用的可能。程序会在 `meta.errors` 和 `meta.source_status` 中明确记录，禁止把缺失数据当成 0。

## 1. 填写持仓

编辑 `config/portfolio.json`：

```json
[
  {
    "name": "你的基金名称",
    "fund_code": "012345",
    "amount": 5000,
    "cost_return_pct": -3.2,
    "themes": ["半导体", "电子元件"],
    "proxy_codes": [],
    "notes": ""
  }
]
```

字段说明：

- `name`：基金/持仓名称
- `fund_code`：基金代码，可留空
- `amount`：当前金额
- `cost_return_pct`：当前持仓收益率；不填可设为 null
- `themes`：最重要。用于和行业/概念板块匹配
- `proxy_codes`：可选，预留给 ETF/指数代理
- `notes`：备注

## 2. 本地测试

Windows 双击：

- `one_click_test.bat`

或 PowerShell：

```powershell
./one_click_test.ps1
```

手动命令：

```bash
python -m pip install -r requirements.txt
python scripts/run_snapshot.py --session noon --skip-wait
python scripts/run_snapshot.py --session close --skip-wait
```

## 3. 上传 GitHub


### Windows 一键部署（推荐）

解压后直接双击：

```text
one_click_deploy_github.bat
```

脚本会尽量自动完成：

1. 检查/安装 GitHub CLI
2. 第一次授权 GitHub
3. 初始化 Git
4. 新建 Public 仓库
5. 上传全部文件
6. 输出最终仓库地址

如果目录已经绑定现有 GitHub 仓库，则会直接推送到 `origin`。


把整个目录上传到一个 GitHub 仓库。

推荐：**Public 公共仓库**。这样 ChatGPT 可直接读取 `data/latest_noon.json` 与 `data/latest_close.json`。

如果必须使用 Private 私有仓库，则后续需要给 ChatGPT 连接 GitHub，才能稳定读取。

Actions 会自动运行：

- `.github/workflows/noon.yml`
- `.github/workflows/close.yml`

仓库 Settings → Actions → General 中确保 Workflow permissions 至少允许：

- Read and write permissions

## 4. ChatGPT 读取地址

公共仓库上传后，两个关键地址为：

```text
https://raw.githubusercontent.com/你的用户名/你的仓库名/main/data/latest_noon.json
https://raw.githubusercontent.com/你的用户名/你的仓库名/main/data/latest_close.json
```

把仓库地址发给 ChatGPT，后续定时任务就可以固定读取最新 JSON。

## 5. 历史与放缩量逻辑

每次运行同时保存：

```text
data/history/YYYY-MM-DD_noon.json
data/history/YYYY-MM-DD_close.json
```

第二个交易日起，会自动读取上一份同 session 快照：

- 今日 11:31 vs 上一交易日 11:31
- 今日 14:36 vs 上一交易日 14:36

以全 A 累计成交额比较：

- >= +5%：放量
- <= -5%：缩量
- 其余：量能接近

第一天没有历史基准时显示“暂无同周期基准”，不会伪造结论。

## 6. 风控

`config/settings.json` 默认：

```json
{
  "risk": {
    "stop_loss_pct": -15
  }
}
```

程序只输出条件化参考，不替代最终决策；若 `cost_return_pct` 已触及预设线，会优先标记风险。

## 目录

```text
a-share-market-monitor/
├─ .github/workflows/
├─ config/
│  ├─ portfolio.json
│  └─ settings.json
├─ data/
│  └─ history/
├─ reports/
├─ scripts/
├─ src/a_share_monitor/
├─ tests/
├─ one_click_test.bat
├─ one_click_test.ps1
├─ requirements.txt
└─ README.md
```
