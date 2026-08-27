# TradingAgents-AShare：A股智能投研多智能体系统

本项目是基于多智能体协作的 A 股深度分析系统，模拟顶级投研机构的决策闭环，通过 14 名专业 Agent 的多空辩论与风控博弈，为投资者提供结构化的交易建议。

<div align="center">
  <img src="assets/web/analysis.png" width="100%" alt="智能分析"/>
  <p><em>14 名智能体实时协作，左侧对话驱动，右侧可视化全流程</em></p>
</div>

## 版本更新

README 仅保留近期更新摘要；完整版本历史见 [CHANGELOG.md](CHANGELOG.md)。后续更新请按版本号倒序追加。

### v0.5.1 - 2026-08-27

- **实时行情**：日线、5 分钟和 1 分钟 K 线统一通过 MiniQMT 实时刷新；日线实时合并当日开高低收、成交量和成交额，分析链路同步使用当日数据。
- **时间展示**：1 分钟和 5 分钟 K 线的坐标轴、悬浮信息与状态时间统一为 `YYYY/MM/DD HH:mm`。
- **行情完整性**：分钟历史数据会补齐当日午后缺失区间；5 分钟最后一根 K 线以 `14:55` 表示 `14:55-15:00` 收盘区间。
- **交互优化**：指数快捷栏仅展示固定预设，切换指数时不再额外插入或重复显示“上证指数”按钮；导航栏支持固定与非固定切换。

## 功能特性

### 辩论对战可视化

点击 Agent 卡片即可打开辩论 Drawer，实时观看多空对抗与风控三方辩论。垂直时间线按 Round 分组，Token 级流式呈现每位 Agent 的发言，裁决卡片独立高亮展示。

<div align="center">
  <img src="assets/web/debate_drawer.png" width="80%" alt="辩论对战可视化"/>
</div>

### 意图驱动的自然语言交互

直接输入"调研茅台短线"即可自动识别标的、解析投资周期，支持短线与中线双周期分析，无需填写表单。

### 自选股与定时分析

数据库持久化自选列表，支持批量加入股票、自定义周期与触发时间，并可在前端批量更新、删除或手动测试定时任务。定时分析会自动复用持仓上下文，连续失败自动停用，无需人工干预。

<div align="center">
  <img src="assets/web/timer_analysis.png" width="80%" alt="定时分析"/>
</div>

### 持仓追踪与跟踪看板

支持导入持仓数据，自动记录持仓、成本价与仓位占比，并可一键将持仓标的补齐到定时分析列表。控制台会展示跟踪看板摘要，完整看板页支持查看实时价格、当日区间、持仓盈亏与上一交易日报告区间，方便盘中快速跟踪。

### 结构化研报管理

分析结果结构化存储，支持按标的、日期检索历史研报，决策卡片一目了然地展示方向、置信度、目标价与止损价。

<div align="center">
  <table style="width: 100%">
    <tr>
      <td width="50%"><img src="assets/web/reports.png" alt="历史报告"/><br><em>研报历史</em></td>
      <td width="50%"><img src="assets/web/detail.png" alt="研报详情"/><br><em>深度详情</em></td>
    </tr>
  </table>
</div>

### 多模型厂商支持

OpenAI、Anthropic、Google Gemini、DeepSeek、Moonshot、智谱、硅基流动等，用户可在前端自由切换模型厂商与具体模型；保存配置后会自动执行模型 warmup，也可以在设置页手动发送“你好”查看模型原始返回，便于排查接入问题。

<div align="center">
  <img src="assets/web/settings.png" width="80%" alt="定时分析"/>
</div>

## 核心架构

TradingAgents 模拟真实交易机构的部门协作，将复杂任务拆解为专业的智能体角色：

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

*图中仅展示核心节点，完整流程包含 14 名智能体。

### 分析师团队
基本面、情绪、新闻、技术、宏观、主力资金 6 大维度同步作业，对市场数据进行深度提取与初步评估。

<p align="center">
  <img src="assets/analyst.png" width="90%">
</p>

### 研究员团队
多头与空头研究员针对分析师结论开展 Claim 驱动的结构化辩论（红蓝对抗），研究总监综合裁决形成投资计划。

<p align="center">
  <img src="assets/researcher.png" width="80%">
</p>

### 决策与风控
交易员将研究结论转化为可执行方案，激进/稳健/中性三方风控辩论审查，组合经理最终裁决。

<p align="center">
  <img src="assets/risk.png" width="80%">
</p>

## 快速上手

### 环境准备

根据部署方式准备以下工具：

| 方式 | 必需工具 | 说明 |
|------|----------|------|
| Docker 部署 | Docker Engine / Docker Desktop | 推荐方式，镜像内已包含后端与构建后的前端 |
| 源码安装 | Python 3.10+、[uv](https://docs.astral.sh/uv/)、Node.js 18+、npm | 适合本地开发、调试后端或前端 |
| MiniQMT 数据源 | 本机 MiniQMT 客户端、可用的 `xtquant` | 可选；适合需要使用本地 MiniQMT 行情、实时数据和财务数据的场景 |

如果本机尚未安装 `uv`，可先执行：

```bash
pip install uv
```

Windows PowerShell 用户可用下面的命令生成 `TA_APP_SECRET_KEY`：

```powershell
$env:TA_APP_SECRET_KEY = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
```

### Docker 一键部署 (推荐)

**方式一：Docker Compose（推荐）**

```bash
# 克隆仓库（也可以只下载 compose 文件：
#   curl -O https://raw.githubusercontent.com/KylinMountain/TradingAgents-AShare/main/docker-compose.yml）
git clone https://github.com/KylinMountain/TradingAgents-AShare.git
cd TradingAgents-AShare

export TA_APP_SECRET_KEY=$(openssl rand -base64 32)
docker compose up -d
```

镜像默认在同一容器内同时启动 API 服务与定时任务调度器，定时分析开箱即用，无需 Redis 等额外组件。如需分开部署（API/调度器/Redis 各自一个容器），使用 `docker-compose.split.yml`，详见 [guide/deployment.md](guide/deployment.md)。

**方式二：docker run**

```bash
docker pull ghcr.io/kylinmountain/tradingagents-ashare:latest

mkdir -p $(pwd)/data
export TA_APP_SECRET_KEY=$(openssl rand -base64 32)

docker run -d -p 8000:8000 \
  --name tradingagents \
  --restart always \
  -v $(pwd)/data:/app/data \
  -e DATABASE_URL="sqlite:///./data/tradingagents.db" \
  -e TA_APP_SECRET_KEY="${TA_APP_SECRET_KEY}" \
  ghcr.io/kylinmountain/tradingagents-ashare:latest
```

访问 `http://localhost:8000` 即可使用。

> **`TA_APP_SECRET_KEY`**：用于加密用户 LLM API Key 和签发登录 JWT。不设置时使用内置默认密钥（仅适合本地开发）。生产环境务必设置，且不可更改。

> **LLM 配置**：启动后在前端"设置"页面配置模型厂商、API Key 和模型名称即可，无需环境变量预设。

> **邮箱验证码**：未配置 SMTP（`MAIL_HOST` 等）时，验证码会在前端登录页直接显示为 `开发环境验证码：xxxxxx`，本地使用无需配置邮件服务器。如果需要真实邮件投递，参考 `.env.example` 配置 `MAIL_HOST` / `MAIL_USER` / `MAIL_PASS` 等并通过 `-e` 注入容器。

Docker 容器使用 SQLite 时建议挂载 `/app/data`，否则容器删除后历史研报、用户配置和 Token 会丢失。

> 📖 更多部署拓扑（分开部署、旧版镜像升级迁移）与全部环境变量说明，见 [guide/ 配置与部署指南](guide/)。

### 源码安装

```bash
git clone https://github.com/KylinMountain/TradingAgents-AShare.git
cd TradingAgents-AShare

# 后端
uv sync

# 前端
cd frontend
npm install
npm run build
cd ..
```

复制 `.env.example` 到 `.env` 并按需修改，然后：

```bash
# 启动后端
uv run python -m uvicorn api.main:app --port 8000
```

访问 `http://localhost:8000` 即可开始 AI 投研之旅。

如果需要单独调试前端开发服务器：

```bash
cd frontend
echo VITE_API_URL=http://localhost:8000 > .env
npm run dev
```

前端开发服务器默认运行在 `http://localhost:5173`，后端仍保持 `http://localhost:8000`。

### 数据源与 MiniQMT

项目支持将本机 MiniQMT 作为优先数据源。配置生效后，以下内容会优先从 MiniQMT 获取：

- 日线 K 线和实时行情；
- 基于 MiniQMT OHLCV 数据计算的技术指标；
- MiniQMT 能提供的公司财务数据；
- 指数 K 线接口（例如 `000001.SH`）。

新闻、资金流、龙虎榜、涨停池等 MiniQMT 未提供的内容，会自动继续使用 AkShare、BaoStock、今日投资、yfinance 等已有数据源。MiniQMT 未安装、客户端未运行、本地没有对应历史数据或接口返回失败时，也会按同样规则自动回退，不会阻塞整个分析流程。

#### 行情更新与时间

- 日线 K 线请求会将结束日期按包含语义读取；如果 MiniQMT 返回当天实时行情，API 会把最新价格、成交量和成交额合并到当天日线，因此盘中可看到当天实时值。
- 切换到 1 分钟或 5 分钟周期时，前端先加载历史数据：1 分钟默认最近 7 天，5 分钟默认最近 30 天。若请求包含当天且当前已收盘，系统会检查最后一根数据是否覆盖到 15:00；仅有上午数据时，会自动调用 MiniQMT 下载当天缺失区间并重新读取（需要 `MINIQMT_AUTO_DOWNLOAD=1`）。
- 分钟历史加载成功后，前端通过 `/v1/market/kline/stream` 接收实时更新，后端约每 2 秒读取一次 MiniQMT 最新行情；连接异常时约每 5 秒重试。
- 5 分钟 K 线使用区间开始时间标记，最后一根 `14:55` 柱覆盖 `14:55-15:00` 的收盘区间；不会额外生成 `15:00` 的新柱。
- 1 分钟和 5 分钟在图表坐标轴、悬浮信息和实时状态中的展示格式统一为 `YYYY/MM/DD HH:mm`，例如 `2026/08/26 14:30`。

MiniQMT 属于本地客户端数据源，建议使用源码方式部署。先完成 MiniQMT 客户端安装并确认客户端正常运行，再在项目虚拟环境中配置 `xtquant` 路径。Windows PowerShell 示例：

> **Python 版本要求**：MiniQMT 的 `xtquant` 包包含 Python 原生扩展，必须使用与扩展匹配的 Python 版本。当前常见 MiniQMT 安装提供 `cp310`/`cp311` 扩展，推荐使用 Python 3.11；不要使用 Python 3.12 启动 API，否则可能出现 `No module named 'xtquant.IPythonApiClient'` 或 DLL 加载失败。

```powershell
# 项目根目录
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

# 填写 xtquant 所在目录的上级目录，路径以本机 MiniQMT 安装位置为准
$env:MINIQMT_XTQUANT_PATH = "C:\\MiniQMT\\bin.x64"

# 可选：本地没有日线时，允许 MiniQMT 尝试下载历史数据
$env:MINIQMT_AUTO_DOWNLOAD = "1"

.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS 或通过 `.env` 配置时，可使用：

```dotenv
# xtquant 包所在目录的上级目录
MINIQMT_XTQUANT_PATH=/path/to/miniqmt/bin.x64
# 默认 0，仅读取已下载数据；设为 1 才会尝试自动下载日线
MINIQMT_AUTO_DOWNLOAD=0
```

默认数据源优先级为：

```text
cn_miniqmt -> cn_akshare -> cn_baostock -> cn_investoday -> yfinance -> alpha_vantage
```

数据源配置可在 [`.env.example`](.env.example) 中查看。Docker 容器通常无法直接连接宿主机上的 MiniQMT 客户端；如需使用 MiniQMT，请在运行 MiniQMT 的主机上进行源码部署，并确保 API 进程与 MiniQMT 使用可访问的同一用户环境。

## API 集成

系统提供标准 REST API，方便集成到自定义脚本、交易机器人或第三方看板：

| 操作 | 接口 |
|------|------|
| 触发分析 | `POST /v1/analyze` → 返回 `job_id` |
| 状态追踪 | `GET /v1/jobs/{job_id}` |
| 获取结果 | `GET /v1/jobs/{job_id}/result` |
| 历史检索 | `GET /v1/reports` |
| 批量获取最新报告 | `POST /v1/reports/latest-by-symbols` |
| 持仓导入 | `GET/POST/DELETE /v1/portfolio/imports` |
| 跟踪看板摘要/明细 | `GET /v1/dashboard/tracking-board` |
| 批量定时任务操作 | `PATCH /v1/scheduled/batch`、`POST /v1/scheduled/batch/delete`、`POST /v1/scheduled/batch/trigger` |
| 模型 warmup | `POST /v1/config/warmup` |

认证：Web 端登录后在"设置 / API Token"生成密钥，通过 `Authorization: Bearer <TOKEN>` 传入。

本地部署示例：

```bash
curl -X POST 'http://localhost:8000/v1/analyze' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <YOUR_API_TOKEN>' \
  -d '{"symbol": "分析一下600519.SH短期趋势", "trade_date": "2026-03-28"}'
```

线上服务示例：

```bash
curl -X POST 'https://app.510168.xyz/v1/analyze' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <YOUR_API_TOKEN>' \
  -d '{"symbol": "分析一下600519.SH短期趋势", "trade_date": "2026-03-28"}'
```

## 特别鸣谢

本项目核心架构灵感与部分基础逻辑源自 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)。感谢原作者及团队在多智能体交易领域做出的卓越探索与开源贡献。

## 许可说明
- 本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache 2.0) 二次开发。
- 新增模块 (`api/`, `frontend/`) 及对核心逻辑的深度修改采用 `PolyForm Noncommercial 1.0.0` 协议。
- 详情请参阅根目录下的 [LICENSE](./LICENSE) 文件。

## 重要声明
- **仅供学习研究**：本项目仅用于学术研究、技术演示及学习交流目的，不构成任何形式的投资建议。
- **实盘风险**：证券市场有风险，投资需谨慎。基于本系统生成的任何观点、建议或计划，仅代表算法博弈结果，不对实际投资损益负责。
- **数据延迟**：分析所依赖的数据源可能存在延迟或偏差，请以交易所实时公告为准。

<div align="center">
<a href="https://www.star-history.com/#KylinMountain/TradingAgents-AShare&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=KylinMountain/TradingAgents-AShare&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=KylinMountain/TradingAgents-AShare&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=KylinMountain/TradingAgents-AShare&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>
