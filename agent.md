# agent.md — deepAStock 深度A股交易 开发与运行说明

> 本文件用于让 AI 助手（agent）快速理解项目现状、环境约束与后续任务。
> 版本日志与发布说明见 `CHANGELOG.md` / `README.md`。

## 项目目标
构建个人深度 A 股 AI 交易平台（PC/H5），闭环：**看盘 → 选股 → 交易 → 复盘 → 进化**。
项目名 **deepAStock（深度A股交易）**，版本 **1.0.0**。
需求来源：`提示词.txt`（功能要求）、`量化交易系统开发需求讨论.markdown`（工程文档）。

## 关键环境事实（务必遵守）
- 工作目录：`C:\aiStock`；不是 git 仓库。
- Python：`C:\veighna_studio\python.exe`（3.13.8），Node 20.20.0 / npm 10.8.2，Docker 可用，无 PostgreSQL。
- **数据全部为真实行情**：新浪(Sina)+腾讯(Tencent) 直连为行情主源；东财系（板块资金流/龙虎榜/财务/资金K线）走 `push2delay.eastmoney.com` 等直连，**个别网络不可达时如实返回空**，禁止 mock 兜底。
- **禁止执行可能长时间挂起的命令**：不阻塞式启动服务。用 `backend/scripts/run_server.py start` / `run_frontend.py start`（Popen 后台 + pid 文件）。
- 服务端口被旧进程占用时，`run_server.py stop` 会按端口（8000）+ 进程名(python)兜底清理；前端按 5173 清理。
- PowerShell 5.1：不支持 `&&`；管道/变量会被外层吞（如 `$r`）；终端 GBK，python 打印中文用 `sys.stdout.buffer.write(...encode('utf-8','replace'))`；PowerShell 发中文请求体用 UTF-8 字节。
- urllib 直连 `127.0.0.1` 会被系统代理影响 → 测试脚本务必 `urllib.request.build_opener(urllib.request.ProxyHandler({}))`。
- 前端改动后必须 `npm run build`（发布版产物在 `frontend/dist`），后端改动后必须 `run_server.py stop` + `start` 重启。

## 技术栈与运行方式
- 后端：FastAPI（Python 3.13），入口 `backend/app/main.py`，uvicorn 端口 **8000**，文档 `/docs`。
- DB：SQLite（SQLAlchemy async + aiosqlite）→ `backend/data/quant.db`（`python -m scripts.init_db` 建表/初始化）；配置 `DATABASE_URL`/`USE_POSTGRES` 预留 PostgreSQL 切换（需 asyncpg）。
- 数据源：`backend/app/core/datasource/sina_source.py` **SinaSource**（manager primary/backup 均用它，`config.PRIMARY_SOURCE="sina+tencent"`；**全真实 HTTP 直连，无任何 mock**）：
  - 实时行情 `https://hq.sinajs.cn/list=sh600519,...`（需 `Referer: https://finance.sina.com.cn`，GBK；stock 字段 1开/2昨收/3现价/4高/5低/8量(股)/9额/30日期/31时间，量÷100=手；index 字段 1现价/2昨收）。
  - K线 `https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,N,qfq`（条目=[日期,开,收,高,低,量(手)]，area 键 `qfqday/day/qfqweek/week/qfqmonth/month`；指数量=手）。
  - 分时 `https://ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519`（`"HHMM 价 量(手) 额"`）。
  - 港/美指数 `https://qt.gtimg.cn/q=hkHSI,usIXIC,usDJI`（`~` 分隔，1名/3现价/4昨收）。
  - 搜索本地 A 股名称库（每月刷新约 4600 条，来源腾讯排行版 `proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList`）。
  - **EastMoney（东财）**：
    - 板块资金流/涨速 `api/qt/clist/get`（`fs=m:90+t:2`行业/`t:3`概念，字段 f3/f6/f62/f66/f72/f78/f84/f104/f105/f128/f136/f140/f184/f198）。
    - **板块自身行情直取用 `api/qt/ulist.np/get?secids=90.BKn`**（`fs=b:BK` 只返回成分股；部分板块如白酒 BK1277 不在资金流 clist 前 200，务必用 ulist 直取，见 `_em_board_quote`）。
    - 龙虎榜 `datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_BILLBOARD_DAILYDETAILS`（filter `(TRADE_DATE='YYYY-MM-DD')`；`TOTAL_NET/TOTAL_BUY/TOTAL_SELL/TURNOVERRATE/EXPLANATION`，排序字段需核实否则报错）。
    - 个股资金流/板块资金K线 `api/qt/stock/fflow/(day)kline/get`（`2.push2`/`9.push2` 常 RemoteDisconnected → 优先 `push2delay`/`push2his`）。
    - 财务 `RPT_LICO_FN_CPD`（`YSTZ/SJLTZ/MGJYXJJE/XSMLL/ASSIGNDSCRPT/...`）。
  - K线/自选已落库缓存（purge 过旧 mock 缓存后 MA 正常）。
- 前端：Vue3 + Vite 5 + Element Plus + Pinia + vue-router + ECharts，`frontend/`，dev 端口 **5173**，`vite.config.js` 已把 `/api` 代理到 8000。所有页面级代码做 `npm run build` 已验证编译通过。
- 定时任务：APScheduler（Asia/Shanghai，周一~五）**09:25/10:30/13:30/14:50 盘中决策、15:10 收盘决策**（当日已有成交的账户自动跳过）、**18:00 复盘**、20:00 进化。调度信息经 `/api/v1/system/status` 的 `jobs` 字段暴露。

## 部署
- **Docker 单容器**：根 `Dockerfile`（叠加 node 构建前端 + python 依赖 + nginx，supervisord 同容器跑 uvicorn+nginx）+ `nginx.conf`（`/api`→`127.0.0.1:8000`）+ `docker-compose.yml`（默认 SQLite 卷 `backend_data`，可选 `postgres` profile）。端口（宿主机）：18080 前端 / 18000 接口 / 15432 postgres。
- **本地开发**：`start.bat`（chcp 65001）或手动。

## 模块与关键文件
| 模块 | 路径 | 说明 |
|---|---|---|
| 智能体 | `app/core/agent/` | `base.py`(AgentContext/AgentResult/BaseAgent)、`llm_client.py`(OpenAI兼容)、3默认(registry)、`executor.py`。默认模型配置文件在 `registry.py`；**统一单智能体运行**（默认 research，个股分析只跑一次）。LLM 失败自动降级本地启发式，不会让接口 500 |
| 缠论 | `app/core/czsc_engine/analyzer.py` | 内置简化缠论（分型/笔/中枢） |
| 模拟交易 | `app/core/simulation/engine.py` | 账户/买卖/风控/绩效；无 API Key 时用本地启发式基于**真实行情**决策；候选池=最近复盘选股池，为空时回退到自选股；不满足买点则如实空仓 |
| 复盘 | `app/core/replay/engine.py` | 数据采集+AI 解读+次日选股池+Markdown |
| 实盘导入 | `app/core/trade_import/parser.py` | JSON/CSV→持仓重算+盈亏 |
| 行情服务 | `app/core/market/quote_service.py` `kline_service.py` `stock_service.py` `watchlist_service.py` | 指数/板块/涨停/龙虎榜/个股详情 |
| API | `app/api/v1/` 8 个路由模块 | market/watchlist/stock/replay/agent/simulation/trade/system |

## 已修复的坑（避免重蹈）
1. **`date: Optional[date] = None` 在 Python3.13 类字段上会解析成 NoneType** → 用 `from datetime import date as _date` 别名（见 `schemas/common.py`）。
2. 复盘引擎调用 `MarketService.get_limit_up` 但服务类没有该方法 → 已补上。
3. AgentContext 字段之前是 `dict/list`，个股接口传入 list 导致 422 → 放宽为 `Any`。
4. `analyze/stock` 未传 agent_type 时默认 research；未知 agent_type 在 executor 兜底到 research（不 500）。
5. 旧 python 进程会用旧代码占 8000 → 改完代码必须 `run_server.py stop`（按端口）+ `start`。
6. 5173 曾被外部工具的 Vite 占用 → 启动前先 `run_frontend.py stop` 清理。
7. `quote_service.get_sector_speed` 曾写 `await self.dsm.get_sector_speed()[:limit]` → 先 await 再切片。
8. `market.py` 的 `/market/distribution` 前缀重复 → 改为 `/distribution`。
9. 新浪 A 股指数代码必须**小写**（`sh000001`）否则无数据；恒指用小写 `hkHSI`；指数 K线量=手。
10. `ensure_default_agents` 曾把 `await db.execute(...).scalars()` 写成 coroutine 调用 → 凡 `db.execute` 一律先存 result 再 `.scalars()`。
11. APScheduler job 传 `lambda` 返回 coroutine 即可被 await；jobs 在 lifespan 内 `start_scheduler` 注册。
12. **`fs=b:BKxxxx` 返回的是成分股列表不是板块行情**；板块行情一律用 `ulist.np/get?secids=90.BKxxxx`（`_em_board_quote`）否则白酒等板块取不到。
13. **B股/北交所代码映射**：`900xxx`→SH、`200xxx`→SZ、`4/8/43/83/87/88`→BJ；`to_standard_symbol` 与前端 `fullSymbol`（Watchlist/StockDetail）一致，改一处必须三处同步。
14. **`_EM_CHAIN_CACHE`/`_EM_FLOW_CACHE` 是类级缓存** → 调试接口数据变更需重启进程或清缓存；空结果也会缓存 600s。
15. 复盘状态：`pending` = 交易日且今日尚未生成，`latest_date` 为最近已生成日期；新交易日不得展示昨日陈旧复盘。
16. 排行源 `RPT_BILLBOARD_DAILYDETAILS` 按净额字段排序会报参数错 → 不排序，取回后内存排序。

## 当前完成度（v1.0.0 发布状态）
- 后端全部核心功能 + API 全链路可用：行情/自选(批量删除)/个股(资金流/财务/产业链/行业对比)/复盘(真实龙虎榜+板块资金流)/模拟/导入/智能体/系统。
- 前端 7 页面完成，`npm run build` 成功；复盘 pending/ready/empty 状态、涨跌区间分布、批量删除等均已联调。
- Docker 单容器镜像方案确定（compose config 校验通过，`docker compose build` 验证凭 Docker Desktop 可用）。

## 常用命令
```bash
cd C:\aiStock\backend
python -m scripts.init_db                     # 重建数据库
python scripts/run_server.py status|start|stop
python scripts/run_frontend.py status|start|stop
npm --prefix C:\aiStock\frontend run build    # 前端编译校验
cd C:\aiStock && docker compose up -d --build # Docker 单容器部署
cd C:\aiStock && docker compose --profile postgres up -d --build  # 启用 PostgreSQL
```

## Roadmap / 未完成项
- 发布准备已完成：`SECRET_KEY` 自动生成并持久化（`data/.secret_key`，环境变量 `SECRET_KEY` 可覆盖）、`DEBUG` 默认 `false`、favicon、前端 `manualChunks` 分包、`build_release.ps1` 打包脚本。
- 待优化：前端按需引入 (echarts/core、element-plus 按组件) 减少厂商包体积；release smoke 测试脚本（解压→compose→health 断言）。
- 数据：恢复东财板块涨速/个股新闻/股东/情绪等（网络放开时）；复盘 Markdown 原文渲染；财务图表化。
- 性能容量：SQLite→PostgreSQL（已支持）；TimescaleDB 预留。
- 安全多用户：当前单用户无鉴权，对外部署需登录 + JWT + 权限（`SECRET_KEY/ACCESS_TOKEN_*` 已预留）。