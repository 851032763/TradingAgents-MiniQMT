# TradingAgents-MiniQMT：A 股智能投研多智能体系统

本项目是在 TradingAgents-AShare 基础上扩展的 A 股深度分析系统，以本机 MiniQMT 作为优先行情与证券数据源。系统模拟专业投研机构的决策闭环，通过 14 名 Agent 的多空辩论与风控博弈生成结构化交易建议，并提供实时行情、自选与定时分析、持仓跟踪、历史研报和 Kronos 时序预测。

<div align="center">
  <img src="assets/web/analysis.png" width="100%" alt="智能分析"/>
  <p><em>14 名智能体实时协作，左侧对话驱动，右侧可视化全流程</em></p>
</div>

## 版本更新

README 仅保留近期更新摘要；完整版本历史见 [CHANGELOG.md](CHANGELOG.md)。后续更新请按版本号倒序追加。

### v0.5.4 - 2026-09-12

- **Kronos 预测记录**：每次预测会在主数据库中保存独立快照，包括输入 K 线、预测结果、请求参数、实际加载模型、运行设备、耗时和行情来源，支持分页、按标的/状态筛选以及单条或批量删除。
- **预测复盘与导出**：新增预测记录页面，可查看冻结快照、历史与预测曲线、完整参数，并导出 JSON/CSV；支持使用相同参数和当前最新行情重新预测，旧快照不会被覆盖。
- **服务调用收口**：前端通过主 API 的 `/v1/kronos/predictions` 系列接口发起和管理预测，主 API 负责读取 MiniQMT K 线、调用 `kronos_service` 并持久化结果。
- **MiniQMT 标的校验**：自选股、股票搜索、定时分析和证券名称解析优先使用 MiniQMT 证券范围，避免 AkShare 名称表滞后导致新股或特定标的无法加入。
- **中文名称容错**：MiniQMT 仍是证券代码有效性的首选依据；当 xtquant 返回空名称、代码形式名称或编码乱码时，仅将其用于标的校验，展示名称自动由 AkShare 名称表补齐，覆盖自选、历史报告、定时分析和组合概览。

### v0.5.3 - 2026-09-05

- **Kronos 预测工作台**：导航栏新增“kronos预测”功能模板，支持对股票 OHLCVA 序列进行时序预测并在图表中对比历史收盘价与预测路径。
- **Kronos 配置**：支持日线、小时、分钟频率，以及历史窗口、预测长度、Temperature、Top-p、采样次数和 Kronos-small/base 模型切换。
- **独立预测服务**：新增 `kronos_service` 微服务，提供模型健康检查、模型信息、模型切换和预测接口；前端开发服务器通过 `/kronos-api` 代理访问。
- **服务可观测性**：预测页面展示 Kronos 服务状态、运行设备、当前模型和推理耗时，并支持保存浏览器中的预测配置。

### v0.5.2 - 2026-08-27

- **分析报告数据质量**：新闻数据源限流、请求失败或无数据时统一降级为“数据不可用”，不再向报告暴露错误码、异常堆栈或供应商技术信息。
- **新闻时间窗口**：新闻采集窗口与分析报告标签保持一致；短线分析使用近 14 天，包含中线分析时使用近 90 天。
- **财务数据一致性**：基本面、资产负债表、现金流量表和利润表按同一数据源成组获取；数据源不完整时整体切换，避免不同供应商或不同口径混用。
- **缺失值展示**：财务数据中的 `NaN`、`Inf`、空值统一显示为“暂无数据”，分析模型不得将缺失值按 0 计算。
- **降级链路**：MiniQMT、AkShare、今日投资和 yfinance 的财务输出统一清洗，缓存抓取正确传递分析周期参数。

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

自选输入同时支持 `002201`、`002201.SZ` 和中文证券名称。代码归属与有效性优先由本机 MiniQMT 证券范围确认；MiniQMT 不可用时才使用兼容数据源降级。证券中文名属于展示元数据，如果 xtquant 返回乱码或缺失名称，系统会从 AkShare 名称表补齐，不影响 MiniQMT 行情继续作为分析数据源。

<div align="center">
  <img src="assets/web/timer_analysis.png" width="80%" alt="定时分析"/>
</div>

### 持仓追踪与跟踪看板

支持通过截图识别导入持仓，也支持在页面中逐条新增或更新。截图识别采用按股票代码增量合并：已存在的股票更新持仓信息，本次未识别到的原有股票继续保留，不会清空整个看板；相同股票代码只保留一条记录。看板支持勾选多条记录后批量删除，并可一键将持仓标的补齐到定时分析列表。

手动新增时，股票代码、持仓数和成本价为必填项；输入完整股票代码后自动查询股票名称和最新价格，股票名称、最新价格和市值不可手工修改。市值按“持仓数 × 当前实时价格”计算，不按成本价估算。控制台会展示跟踪看板摘要，完整看板页支持查看实时价格、当日区间、持仓盈亏与上一交易日报告区间，方便盘中快速跟踪。

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

### Kronos 预测工作台

导航栏中的“Kronos 预测”页面用于运行 Kronos 金融时序模型。输入股票代码后，可以选择日线、小时或分钟数据，调整历史窗口与预测长度，并配置 Temperature、Top-p、采样次数和 Kronos-small/base 模型。主 API 从 MiniQMT 获取 OHLCVA 序列、生成未来交易日期，再调用独立推理服务完成预测。

每次运行都会生成一条归属于当前用户的不可变预测快照。导航栏中的“预测记录”支持：

- 按股票代码和运行状态筛选、分页查看；
- 查看历史输入与预测路径、行情区间、模型和采样参数；
- 查看请求、行情和执行环境的完整参数快照；
- 导出包含历史及预测数据的 JSON 或 CSV；
- 使用原参数和当前行情重新预测；
- 删除单条记录或批量删除选中记录。

重新预测会创建新记录，不会修改原快照。预测记录保存在主应用数据库中，因此生产部署时必须持久化数据库文件或数据卷。

Kronos 由独立的 `kronos_service` 提供推理能力，默认监听 `8101` 端口。服务启动后可通过以下接口检查和调用：

| 操作 | 接口 |
|------|------|
| 健康检查 | `GET /health` |
| 模型信息 | `GET /models/info` |
| 切换模型 | `POST /models/switch` |
| 发起预测 | `POST /predict` |

主 API 默认通过 `KRONOS_SERVICE_URL=http://127.0.0.1:8101` 访问该服务。前端日常预测走主 API 的鉴权接口，不需要浏览器直接访问 `8101`；Vite 仍保留 `/kronos-api/*` 开发代理用于服务状态等兼容调用。

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
# 克隆本仓库
git clone https://github.com/851032763/TradingAgents-MiniQMT.git
cd TradingAgents-MiniQMT

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

#### Docker 启用 Kronos 预测

Kronos 服务使用独立镜像和端口，可在项目根目录执行：

```bash
docker compose -f kronos_service/docker-compose.yml up -d --build
```

服务启动后监听宿主机 `8101` 端口。Kronos 预测由主 API 调用，不需要将 `8101` 暴露给公网浏览器。主 API 在宿主机运行时使用默认的 `KRONOS_SERVICE_URL=http://127.0.0.1:8101`；主 API 在 Docker Desktop 容器中运行时，应配置 `KRONOS_SERVICE_URL=http://host.docker.internal:8101`。如果两个服务加入同一 Docker 网络，可改用 Kronos 的服务名，例如 `http://kronos:8101`。GPU 主机可改用 `kronos_service/docker-compose.gpu.yml`。

### 源码安装

```bash
git clone https://github.com/851032763/TradingAgents-MiniQMT.git
cd TradingAgents-MiniQMT

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

#### 本地启动全部服务

使用 Kronos 预测功能时，需要同时运行前端、主 API、定时任务调度器和 Kronos 服务。建议使用 Python 3.11 创建项目虚拟环境；Kronos 服务默认使用 CPU，也可在具备 CUDA 环境时按需配置 GPU。

首次运行时，先安装 Kronos 服务依赖：

```powershell
cd kronos_service
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

```powershell
# 终端 1：主 API
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# 终端 2：定时任务调度器
.\.venv\Scripts\python.exe -m scheduler.main

# 终端 3：Kronos 预测服务
.\kronos_service\.venv\Scripts\python.exe .\kronos_service\main.py

# 终端 4：前端开发服务器
cd frontend
npm run dev
```

启动后访问 `http://127.0.0.1:5173`，主 API 健康检查为 `http://127.0.0.1:8000/healthz`，Kronos 健康检查为 `http://127.0.0.1:8101/health`。如果没有为 `kronos_service` 单独创建虚拟环境，可将第三条命令中的 Python 路径替换为已安装 Kronos 依赖的 Python 解释器，或直接执行 `powershell -ExecutionPolicy Bypass -File kronos_service\start.ps1 -Cpu`。

四个进程的职责如下：

| 进程 | 默认地址 | 职责 | 是否必需 |
|------|----------|------|----------|
| 前端 Vite | `127.0.0.1:5173` | 本地开发页面及 API 代理 | 开发模式必需 |
| 主 API | `127.0.0.1:8000` | 登录、分析、报告、自选、持仓、MiniQMT 与 Kronos 记录 | 必需 |
| 调度器 | 无 HTTP 端口 | 扫描并执行定时分析任务 | 使用定时分析时必需 |
| Kronos 服务 | `127.0.0.1:8101` | 加载时序模型并执行预测推理 | 使用 Kronos 时必需 |

PowerShell 可使用以下命令逐项确认服务状态：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/healthz -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing
Invoke-RestMethod http://127.0.0.1:8101/health
```

Kronos 服务的依赖位于 [`kronos_service/requirements.txt`](kronos_service/requirements.txt)，本地模型目录为 `kronos_service/kronos-base` 和 `kronos_service/kronos-small`。本地目录不存在时，服务会按模型配置尝试从 Hugging Face 加载，因此首次启动可能需要联网并等待模型下载。生产环境建议预先准备模型文件。可通过 `KRONOS_HOST`、`KRONOS_SERVICE_PORT`、`KRONOS_DEFAULT_MODEL`、`KRONOS_MODEL_ROOT` 和 `KRONOS_LOG_LEVEL` 调整服务。

### 数据源与 MiniQMT

项目支持将本机 MiniQMT 作为优先数据源。配置生效后，以下内容会优先从 MiniQMT 获取：

- 日线 K 线和实时行情；
- 基于 MiniQMT OHLCV 数据计算的技术指标；
- MiniQMT 能提供的公司财务数据；
- 指数 K 线接口（例如 `000001.SH`）；
- 股票代码校验、证券范围和代码搜索。

新闻、资金流、龙虎榜、涨停池等 MiniQMT 未提供的内容，会自动继续使用 AkShare、BaoStock、今日投资、yfinance 等已有数据源。MiniQMT 未安装、客户端未运行、本地没有对应历史数据或接口返回失败时，也会按同样规则自动回退，不会阻塞整个分析流程。

需要特别区分“行情来源”和“展示名称来源”：行情、代码有效性优先由 MiniQMT 决定；中文名称只是展示元数据。部分 xtquant 安装会因编码问题返回包含 `�` 的证券名称，系统会拒绝缓存这类乱码，并使用 AkShare 名称表补齐中文名。这种降级不会把行情切换到 AkShare。

#### MiniQMT 数据同步

前端 MiniQMT 同步页面可查看本地缓存覆盖情况，并按数据类型同步全部市场或指定标的。支持的数据类型包括：

| 类型 | 内容 |
|------|------|
| 行情缓存 | 日线、1 分钟、5 分钟 K 线 |
| 财务报表与指标 | 资产负债表、利润表、现金流量表、每股指标 |
| 股本与股东 | 股本、股东户数、前十大股东、前十大流通股东 |
| 证券基础信息 | 证券与板块基础资料 |
| ETF 专项数据 | ETF 基础资料及相关缓存 |

首次打开同步页面时，服务会在后台只读盘点 MiniQMT 已有缓存，不会自动下载。主动提交同步任务后，状态和覆盖摘要写入 `data/miniqmt_sync_state.json`，服务重启后仍可查看上次结果。xtdata 下载客户端不适合并行调用，因此同步任务串行执行；同一时间只能运行一个盘点或下载任务。

同步接口为 `GET /v1/miniqmt/sync` 和 `POST /v1/miniqmt/sync`。如果未指定 `symbols`，服务会从“沪深A股”“沪深ETF”“北交所”“沪深指数”板块构建同步范围；旧版 MiniQMT 无法读取板块范围时，应在页面或请求中显式指定股票代码。

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
| 创建 Kronos 预测 | `POST /v1/kronos/predictions` |
| 查询 Kronos 记录 | `GET /v1/kronos/predictions`、`GET /v1/kronos/predictions/{run_id}` |
| 删除 Kronos 记录 | `DELETE /v1/kronos/predictions/{run_id}`、`POST /v1/kronos/predictions/batch/delete` |
| MiniQMT 同步状态/启动 | `GET /v1/miniqmt/sync`、`POST /v1/miniqmt/sync` |
| 股票搜索 | `GET /v1/market/stock-search?q=贵州茅台` |
| 持仓导入 | `GET/POST/DELETE /v1/portfolio/imports` |
| 批量删除持仓 | `POST /v1/portfolio/imports/batch/delete` |
| 获取单只股票实时价格 | `GET /v1/market/realtime-quote?symbol=600519.SH` |
| 跟踪看板摘要/明细 | `GET /v1/dashboard/tracking-board` |
| 获取未来 A 股交易日 | `GET /v1/market/trading-dates` |
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

## 常见问题排查

| 现象 | 优先检查 | 处理建议 |
|------|----------|----------|
| 输入股票代码后提示“未识别” | MiniQMT 客户端是否启动，`MINIQMT_XTQUANT_PATH` 是否指向匹配当前 Python 的 xtquant | 重启 MiniQMT 和主 API；在 MiniQMT 同步页确认能够读取证券范围 |
| 自选或历史报告只显示股票代码 | xtquant 的 `InstrumentName` 是否为空或乱码，主 API 是否为最新进程 | 更新并重启主 API；系统会自动通过名称表补齐，首次请求可能需要等待名称缓存加载 |
| `No module named xtquant` 或 DLL 加载失败 | Python ABI 与 MiniQMT 扩展是否匹配 | 推荐 Python 3.11，并确认 `MINIQMT_XTQUANT_PATH` 填写的是包含 `xtquant` 的上级目录 |
| 行情有数据但中文名称缺失 | 行情与名称是两条独立链路 | 检查外网是否能访问 AkShare 名称接口；不会影响 MiniQMT 行情读取 |
| Kronos 页面提示无法连接服务 | `8101` 是否监听，`KRONOS_SERVICE_URL` 是否正确 | 调用 `/health` 检查模型状态；本地分别启动主 API 与 `kronos_service/main.py` |
| Kronos 首次启动很慢 | 模型尚未下载或 CPU 正在加载模型 | 等待健康状态变为 `ready`；生产环境预先放置模型目录，GPU 环境使用对应 Compose 配置 |
| 定时任务没有自动运行 | 调度器是否启动，是否误启多个实例 | 源码部署启动 `python -m scheduler.main`；同一数据库只运行一个调度器 |

更新代码后如果页面行为仍与代码不一致，应先确认端口对应的进程确实已重启。Windows 可用 `Get-NetTCPConnection -State Listen -LocalPort 8000,5173,8101` 查看监听进程；结束旧进程后再从当前工作区启动服务。

## 特别鸣谢

本项目核心架构灵感与部分基础逻辑源自 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)。感谢原作者及团队在多智能体交易领域做出的卓越探索与开源贡献。

本项目基于 [KylinMountain/TradingAgents-AShare](https://github.com/KylinMountain/TradingAgents-AShare)二次开发。感谢原作者及团队在多智能体交易领域做出的卓越探索与开源贡献。

## 许可说明
- 本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache 2.0) 二次开发。
- 本项目基于 [KylinMountain/TradingAgents-AShare](https://github.com/KylinMountain/TradingAgents-AShare)(Apache 2.0) 二次开发。
- 新增模块 (`api/`, `frontend/`) 及对核心逻辑的深度修改采用 `PolyForm Noncommercial 1.0.0` 协议。
- 详情请参阅根目录下的 [LICENSE](./LICENSE) 文件。

## 重要声明
- **仅供学习研究**：本项目仅用于学术研究、技术演示及学习交流目的，不构成任何形式的投资建议。
- **实盘风险**：证券市场有风险，投资需谨慎。基于本系统生成的任何观点、建议或计划，仅代表算法博弈结果，不对实际投资损益负责。
- **数据延迟**：分析所依赖的数据源可能存在延迟或偏差，请以交易所实时公告为准。
