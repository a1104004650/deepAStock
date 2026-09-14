# agent.md — deepAStock 深度A股交易 开发与运行说明

> 本文件用于让 AI 助手（agent）快速理解项目现状、环境约束与后续任务。
> 版本日志与发布说明见 `CHANGELOG.md` / `README.md`。

## 项目目标
构建个人深度 A 股 AI 交易平台（PC/H5），闭环：**看盘 → 选股 → 交易 → 复盘 → 进化**。
项目名 **deepAStock（深度A股交易）**，版本 **1.1.5**。
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
- 定时任务：APScheduler（Asia/Shanghai，周一~五）**10:25/13:30/14:50 交易窗口盘中决策、15:10 收盘决策**（当日已有成交的账户自动跳过）、**18:00 复盘**、20:00 进化；另有 **30s 一次 RSSHub 轮询**（单源限频按订阅间隔，微博/公众号/股吧等推送信息落库供「消息滚动」）。调度信息经 `/api/v1/system/status` 的 `jobs` 字段暴露。settings 快照启动时从 DB 刷新（`refresh_settings`），PUT 时异步写回。

## 部署
- **Docker 多服务**：根 `Dockerfile`（叠加 node 构建前端 + python 依赖 + nginx，supervisord 同容器跑 uvicorn+nginx）+ `nginx.conf`（`/api`→`127.0.0.1:8000`）+ `docker-compose.yml`（默认 SQLite 卷 `backend_data`，可选 `postgres` profile；**rsshub** 本地部署镜像 diygod/rsshub，宿主机 11200 映射，应用内部走 `http://rsshub:1200`，弱依赖不阻塞主业务）。端口（宿主机）：18080 前端 / 18000 接口 / 11200 rsshub / 15432 postgres。
- **本地开发**：双击 `start.bat`（chcp 65001，调用 `backend/scripts/dev_up.py`：后端 8000、前端 5173 起自动顺延端口，Ctrl+C 一并停止）或手动两脚本。

## 模块与关键文件
| 模块 | 路径 | 说明 |
|---|---|---|
| 智能体 | `app/core/agent/` | `base.py`(AgentContext/AgentResult/BaseAgent)、`llm_client.py`(OpenAI兼容)、3默认(registry)、`executor.py`。默认模型配置文件在 `registry.py`；**统一单智能体运行**（默认 research，个股分析只跑一次）。LLM 失败自动降级本地启发式，不会让接口 500 |
| 缠论 | `app/core/czsc_engine/analyzer.py` | 内置简化缠论（分型/笔/中枢） |
| 模拟交易 | `app/core/simulation/engine.py` | 账户/买卖/风控/绩效；无 API Key 时用本地启发式基于**真实行情**决策；候选池=复盘池+持仓池+跟踪池+观察池（观察池按 `account.id % len(items)` 轮转差异化）；**禁止买入 ST/\*ST**（`_is_st_name` 正则候选池+`_exec` 终审双保险）；不满足买点则如实空仓 |
| 复盘 | `app/core/replay/engine.py` | 数据采集+AI 解读+次日选股池+Markdown |
| 实盘导入 | `app/core/trade_import/parser.py` | JSON/交割单 CSV·Excel 批量导入（自动识别列：同花顺/东方财富/投资账本表头别名、UTF-8/GBK 编码、xlsx/xls/标题行；分红/配号/非交易行跳过；佣金+印花税+过户费合计）→持仓重算+盈亏 |
| 行情服务 | `app/core/market/quote_service.py` `kline_service.py` `stock_service.py` `watchlist_service.py` | 指数/板块/涨停/龙虎榜/个股详情 |
| 设置 | `app/core/settings/service.py` `api/v1/settings.py` `models/system.py` | DB 持久化覆盖 env 默认值（`Setting` 表 + `EFFECTIVE` 内存快照）；数据源主+备用1/2/3 顺序回退；数据库连接测试；`snapshot()` 只显示与默认值不同的覆盖项 |
| RSSHub 订阅 | `app/core/rsshub/parser.py` `app/core/rsshub/service.py` `api/v1/rss.py` `models/rss.py` 前端 `views/RssNews.vue` | 本地 RSSHub 自建实例；订阅源 CRUD（微博/公众号/股吧/自定义，**path(route) 或 url 二选一**）、RSS/Atom/JSON Feed 解析（`fetch_feed`；**页面地址 HTML 会显式报错而非静默 0 条**）、限频轮询去重落库（`rss_sources`/`rss_items` 表）；ST 标题过滤；`_upsert_items` 按 source+guid 去重；`_prune` 按天数/每源上限清理。导航「订阅」为**独立整页**（`RssNews.vue` 包裹 `MainLayout`，保留顶部导航栏；桌面双栏网格：消息流 + 订阅源状态表），页内直接维护 **RSSHub 配置**（启用开关/实例地址/保存，等同步「设置 → RSSHub 订阅」）；轮询后**重要消息全局通知为多条同叠**（`stores/news.js` 的 `toasts` 数组，每条独立 15s 自动消失；`MainLayout.pollImportantNews` 合并平台新闻`importance=1` + `pollRssIncrement` 只推 RSS `importance ≤ 2`，按标题本地去重）；「设置 → RSSHub 订阅」可编辑实例地址（本机开发 `http://127.0.0.1:11200`，容器内 `http://rsshub:1200`）；已预置 4 个**实测可直连解析**的案例源（雪球热帖/钛媒体/IT之家/爱范儿） |
| API | `app/api/v1/` 11 个路由模块 | market/watchlist/stock/replay/agent/simulation/trade/system/settings/rss/backtest |
| 策略回测 | `app/api/v1/backtest.py` `models/strategy.py` 前端 `views/Backtest.vue` | 策略 DB 化管理（`strategy_configs` 表，增删改/停用/复制/测试）；`run(bars, params)` 自定义策略代码（内置 `sma/ema`）；单只 `list` / 自选组合 `dict {symbol: K线}` 双模式（组合信号必带 `symbol`，`weight` 参数控注资占比）；`_simulate` / `_simulate_portfolio` 浮点份额连续持仓，信号当日开盘价成交 |

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
17. **`from app.api.v1 import settings` 遮蔽 `app.config.settings`** → main.py 中必须 `from app.api.v1 import settings as settings_api`，否则 `settings.APP_NAME` 触发 AttributeError 启动崩溃。
18. **SQLite 存储的 DateTime 字段为 naive（无 tzinfo）** → `datetime.now(tz_aware)` 与 naive 相减报 TypeError；所有对比 DB 时间的代码必须 `.replace(tzinfo=None)` 使用 naive datetime。
19. **ST 名称检测正则 `\bST\b` 在中文 CJK 场景失效**：Python `\b` 将 CJK 视为 word char，`ST慧球`（T后直接跟"慧"）无法触发边界 → 改用 `(?<![A-Za-z0-9])(?:S[*★]?ST|\*?ST)(?![A-Za-z0-9])` 显式排除前后 ASCII 字母数字，同步应用于 `engine._ST_NAME_RE` 与 `parser._ST_RE`。
20. **`snapshot()["overridden"]` 原返回所有 DB 键** → 用户恢复默认值后 overridden 列表仍残留该项 → 改为 `EFFECTIVE[k] != DEFAULTS.get(k, "")` 比较。
21. **直接把微博网页地址（如 `https://weibo.com/u/1xxxx`）当订阅 URL**：解析器拿到 HTML 页面后返回 0 条（`ok:0`），看起来“配置了但没反应”→ 微博等平台必须用 RSSHub **路径** `/weibo/user/{uid}`（`url` 留空，base 从设置取）；解析器现已对 `text/html` 内容显式报错（`err:地址返回的是 HTML 网页…`）。**rsshub_base 默认 `http://127.0.0.1:1200` 只对容器内有效**：本机开发必须在「设置 → RSSHub 订阅」把实例地址改成宿主机映射 `http://127.0.0.1:11200`，且先 `docker compose up -d rsshub`，否则路径型订阅报连接错误。
22. **宿主机访问不到/连不上 rsshub（11200 拒绝）但容器看着在跑**：查 compose 里 rsshub `LISTEN_INADDR_ANY`，若为 `0` 则 RSSHub 只监听容器内 `127.0.0.1:1200`（`docker exec … cat /proc/net/tcp` 见 `0100007F:04B0` 即中招），宿主机端口转发必超时 → 必须为 `true` 并 `docker compose up -d rsshub` 重建；用 `docker port deepastock-rsshub` 确认绑定。
23. **微博个人博主/热搜路由 503**：**v1.1.4 起微博用户订阅（`/weibo/user/{uid}`）不再走 RSSHub**，由后端 `parser._fetch_weibo_user` **直连 m.weibo.cn**（Cookie 取自「设置 → RSSHub 订阅」/「订阅消息 → RSSHub 配置」里保存的 `weibo_cookies`，不写 docker/环境变量）。若报 `微博接口返回 4xx`/`未找到内容 Tab` = Cookie 失效，重新登录 m.weibo.cn 复制新 Cookie 即可；其他微博路由（热搜 `/weibo/search/hot` 等）仍走 RSSHub，需其实例可用。
24. **回测整手股数导致 0 交易**：按 100 股整手建仓时，茅台等一手市值超本金的标的一直买不起、回测 0 笔 → `buy/sell` 一律用**浮点份额连续持仓**（`shares = spend / fill`），不做整手取整。
25. **SQLAlchemy `.scalars()` 返回标量**：`select(StrategyConfig.key).scalars()` 得到的是字符串而非行对象；要行对象必须 `select(StrategyConfig)`。
26. **回测策略双模式入参**：单只 `bars`=K线 list；自选组合 `bars`=**`{symbol: [K线...]}` dict**。组合信号必须带 `symbol`，`fraction`=可用资金占比；`/strategies/test` 会先按 list 调、抛 `TypeError/AttributeError` 再按 dict 重试（纯组合代码也能测）。内置模板已 `isinstance(bars, dict)` 双模式兼容；升级旧内置模板仅当其 code 仍精确等于历史模板时（用户改过的不覆盖）。
27. **全局消息 toast 用「多条同叠」而非单条队列**：同一事件周期多条消息要**同时弹出、互不覆盖**、各自 15s 自动消失（Element Plus 单 `ElMessage` 会顶掉/单条排队）→ `stores/news.js` 维护 `toasts` 数组（每条独立 `setTimeout` 15s 移除），`MainLayout.pollRssIncrement` 仅推送 `importance` ≤ 2（1=重要 / 2=普通），`importance=3`（其他/低价值）不弹窗。平台新闻仍只推 `importance===1`。

## 当前完成度（v1.1.4 发布状态）
- 后端全部核心功能 + API 全链路可用：行情/自选(批量删除)/个股(资金流/财务/产业链/行业对比)/复盘(真实龙虎榜+板块资金流)/模拟/导入/智能体/系统/设置/RSS订阅。
- 前端 8 页面完成（大盘/自选/复盘/模拟/实盘导入/智能体/订阅消息/设置），`npm run build` 成功；复盘 pending/ready/empty 状态、涨跌区间分布、批量删除、消息滚动（平台新闻+RSS合并）、订阅消息独立页等均已联调。
- Docker 多服务部署方案确定（compose config 校验通过，含 rsshub 本地镜像）。
- v1.1.0：RSSHub 订阅系统（本地实例+订阅源管理+轮询去重+ST过滤+独立「订阅消息」页+内置 4 个可直连案例源）、系统设置页（数据源链+数据库+RSSHub）、大盘看板四板块等高、模拟四池Tab切换、AI禁买ST/观察池差异化。
- v1.1.1：导航「订阅」为完整整页（保留顶部导航栏、含 RSS 配置与订阅源状态）；设置页 RSSHub 实例地址可编辑；订阅弹窗支持 RSSHub 路径/URL 二选一；RSS 解析对 HTML 网页地址显式报错；微博订阅源修正为 RSSHub 路径；订阅页嵌入配置行可保存；后台轮询后重要 RSS 消息全局定向推送；`run_server.py` stop GBK 解码修复。版本号 1.1.1（compose / build_release / 文档）已同步。
- v1.1.2：实盘导入**直接解析券商交割单**（同花顺/东方财富/投资账本等 CSV/Excel，UTF-8/GBK 自动识别，表头别名映射，分红/配号/非交易行自动跳过，佣金+印花税+过户费合计入费用；endpoint `/trade/import/file`，旧 `/trade/import/csv` 保留兼容）。版本号 1.1.2 已同步。
- v1.1.3：修复 compose 中 rsshub `LISTEN_INADDR_ANY=0` 导致**只监听容器内 127.0.0.1、宿主机始终打不开**的问题（改为 `true`）；微博博主/热搜路由需 RSSHub 配 `WEIBO_COOKIES`（已注释位），README/设置页/订阅页给出获取与配置指引；README 补部署排障与强制重建说明。版本号 1.1.3 已同步。
- v1.1.4：**一键本地启动**（`start.bat` → `backend/scripts/dev_up.py`，后端 8000/前端 5173 起自动顺延空闲端口，Ctrl+C 一并停止）；**微博 Cookie 移到应用内配置**（设置页/订阅页新增「微博 Cookie」，`weibo_cookies` 存 DB；`/weibo/user/{uid}` 由后端直连 m.weibo.cn 拉取，不再依赖 RSSHub WEIBO_COOKIES/docker），vite 代理目标读 `BACKEND_PORT` 跟随启动端口。版本号 1.1.4 已同步。
- v1.1.5：**AI 流式输出**（`/brainstorm/{symbol}/{agent_type}/stream` SSE + 自选股页流式渲染）；**策略回测**（导航「回测」，内置均线金叉死叉；策略 DB 化管理 + `run(bars, params)` 自定义代码 + 「测试代码」；浮点份额连续持仓修复高价股 0 交易；**自选组合回测** `symbols` 入参 / `_simulate_portfolio` / `list`+`dict` 双模式模板 + 「组合建仓比例」weight 参数 + 「从自选股导入」；模拟账户 AI 分散化（候选池轮转 + 风格评分）；前端状态管理重构为 Pinia。版本号 1.1.5 已同步。

## 常用命令
```bash
cd C:\aiStock\backend
python -m scripts.init_db                     # 重建数据库
python scripts/run_server.py status|start|stop
python scripts/run_frontend.py status|start|stop
npm --prefix C:\aiStock\frontend run build    # 前端编译校验
cd C:\aiStock && docker compose up -d --build # Docker 多服务部署
cd C:\aiStock && docker compose --profile postgres up -d --build  # 启用 PostgreSQL
cd C:\aiStock && docker compose config --quiet  # 验证 compose 配置
```

## Roadmap / 未完成项
- v1.1.4 发布准备已完成：版本号 1.1.4（compose / build_release / README / CHANGELOG），release zip 已打包验证。
- v1.1.5：版本号 1.1.5 已同步（config / compose / build_release / README / CHANGELOG / frontend package.json）；release zip 未重新打包（本次仅源码与开发环境更新）。
- 待优化：前端按需引入 (echarts/core、element-plus 按组件) 减少厂商包体积；release smoke 测试脚本（解压→compose→health 断言）。
- 数据：恢复东财板块涨速/个股新闻/股东/情绪等（网络放开时）；复盘 Markdown 原文渲染；财务图表化。
- 性能容量：SQLite→PostgreSQL（已支持）；TimescaleDB 预留。
- 安全多用户：当前单用户无鉴权，对外部署需登录 + JWT + 权限（`SECRET_KEY/ACCESS_TOKEN_*` 已预留）。