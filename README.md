# deepAStock 深度A股交易

深度 A 股 AI 交易平台（PC/H5）。围绕「看盘 → 选股 → 交易 → 复盘 → 进化」闭环，内置 3 个默认 AI 智能体（投研 / 短线 / 波段），支持模拟交易（AI 禁买 ST）、实盘导入、缠论分析、每日自动复盘、RSSHub 订阅消息（微博/公众号/股吧实时推送）与系统设置。

> 发布说明 & 版本日志见 [CHANGELOG.md](CHANGELOG.md) · 需求来源 `提示词.txt` 与 `量化交易系统开发需求讨论.markdown`

## 部署方式（推荐：Docker，无需安装 Python/Node）
> 对使用者而言这是唯一需要的方式：解压 → `docker compose up -d --build` → 打开浏览器，即可用。
> 数据库默认 SQLite（零配置）；如有自己的 PostgreSQL，改两个环境变量即可切换（见下）。

### 1. 获取release包
```bash
# 开发者：自己打 release 包
powershell -ExecutionPolicy Bypass -File build_release.ps1
# 产出：release/deepAStock-v1.1.2.zip（含完整项目 + Docker 全家桶 + 文档）
```

### 2. 部署（使用者）
```bash
unzip deepAStock-v1.1.2.zip
cd deepAStock-v1.1.2
docker compose up -d --build     # 首次构建约需数分钟，之后秒级
# 打开浏览器 http://localhost:18080   （接口文档 http://localhost:18000/docs）
docker compose logs -f app       # 看日志
docker compose down              # 停止
docker compose up -d             # 再次启动（增量秒级）
```

> **访问不了/端口没暴露？先自检（配置本身已含 `18080`/`18000`/`11200` 端口映射）：**
> 1. `docker compose ps`：STATUS 必须是 `Up (healthy)`，PORTS 要显示 `0.0.0.0:18080->80/tcp` 等——若只有 `build/pull` 没有 `up`，容器没起来当然没端口；
> 2. `docker port deepastock-app`：确认端口确实绑定在宿主机；
> 3. 访问地址用**运行 Docker 的那台机器 IP**：`http://<宿主IP>:18080`（WSL2 / 云主机 / 远程服务器不能只在本机浏览器打 `localhost`），并确认防火墙放行了这三口；
> 4. 启动失败看原因：`docker compose logs app`。
>
> **改了代码/换了新版压缩包，但页面还是旧的？** 原因是没用 `--build` 重建镜像：
> ```
> docker compose up -d --build app       # 强制重新构建并用新镜像重启
> docker compose build --no-cache app    # 如果还不放心，全量无缓存重建
> ```
> 完成后浏览器 `Ctrl+F5` 强刷；不要只执行 `docker compose up`（它永远复用旧镜像）。

### 端口
| 端口 | 用途 |
|---|---|
| `18080` | 前端页面（Nginx 托管 `frontend/dist`，`/api` 反代到同容器 8000） |
| `18000` | 后端接口（uvicorn，可直接访问 /docs） |
| `11200` | 本地 RSSHub 实例（微博/公众号/股吧等订阅源，仅供本项目） |

### 数据库选择
- **SQLite（默认）**：数据保存在 Docker 卷 `backend_data`，重建容器不丢失，开箱即用。
- **PostgreSQL（可选，适合自己有 psql 的用户）**：
  ```bash
  # 1) 编辑 docker-compose.yml：取消 app 服务中 DATABASE_URL/USE_POSTGRES 两行注释
  #    (自行修改 用户名/密码/库名)
  # 2) 启动（连带 postgres 服务）
  docker compose --profile postgres up -d --build
  ```

### 环境变量（docker-compose.yml 可改）
| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | sqlite...quant.db | 数据库地址；PostgreSQL 用 `postgresql+asyncpg://用户:密码@host:5432/库名` |
| `USE_POSTGRES` | false | 切换 PostgreSQL 时置 true |
| `SECRET_KEY` | 自动生成并持久化到 `data/.secret_key` | 固定密钥勿留默认，可用环境变量显式覆盖 |
| `DEBUG` | false | 生产安全默认关闭 |
| `TZ` | Asia/Shanghai | 时区 |
| `APP_VERSION` | 1.1.2 | 显示版本 |
| `PRIMARY_SOURCE/BACKUP_SOURCE` | sina+tencent | 行情数据源 |
| `RSSHUB_BASE` | http://rsshub:1200 | 本地 RSSHub 实例地址（容器内）；本机直接跑后端需在「设置 → RSSHub 订阅」填宿主机映射 `http://127.0.0.1:11200` |
| `RSSHUB_ENABLED` | true | RSSHub 轮询总开关 |

## 本机开发（开发者）
> 上文的 Docker 是给使用者的发布形态。开发者在本机迭代时用下面的方式（进程式，热重载）。

双击 `start.bat`，或手动执行：

```bash
# 后端（端口 8000）
cd backend
python -m scripts.init_db        # 首次：初始化数据库（SQLite: backend/data/quant.db）
python scripts/run_server.py start

# 前端（端口 5173，已配置 /api 代理到 8000）
python scripts/run_frontend.py start
```

打开浏览器访问 **http://127.0.0.1:5173**，接口文档 http://127.0.0.1:8000/docs

进程管理：
```bash
python scripts/run_server.py    status|start|stop
python scripts/run_frontend.py  status|start|stop
```

## 页面导航
| 页面 | 路由 | 功能 |
|---|---|---|
| 大盘看板 | `/` | 四大指数（含日K线）、**涨跌区间分布图**、板块资金流/涨速、消息滚动、自选股分时 |
| 自选股 | `/watchlist` | 分组管理、**批量/单条删除**、实时行情与最近查看价格、个股详情（资金流/财务/产业链/行业对比） |
| 每日复盘 | `/replay` | 市场概况、涨停梯队、**真实龙虎榜**、**板块主力净流入/流出**、AI 复盘、次日选股池、复盘原文（交易日 18:00 自动生成） |
| 模拟交易 | `/simulation` | 多账户，AI 每日决策买卖（**禁买 ST/\*ST**），持仓/追踪/观察/复盘四池 Tab 切换，收益曲线 + 绩效统计（收益率/胜率/最大回撤） |
| 实盘导入 | `/trade` | 手动录入 / JSON / **券商交割单 CSV·Excel 批量导入**（同花顺、东方财富、投资账本等自动识别列，UTF-8/GBK 均可，分红配号自动跳过），持仓与盈亏汇总 |
| 智能体中心 | `/agents` | 3 个默认智能体 + 自定义，配置 API/模型/提示词，大盘分析 |
| 订阅消息 | `/rss` | 导航「订阅」为**独立整页**（保留顶部导航栏），页内消息流（来源/重要度/搜索/ST过滤）+ **RSSHub 配置**（启用开关/实例地址/保存）+ 订阅源状态表；立即轮询、30s 自动刷新；轮询后重要消息全局推送 |
| 系统设置 | `/settings` | 数据源（主+备用1/2/3顺序回退）、数据库配置/测试、RSSHub开关+订阅地址+间隔+订阅源管理 |

## 核心接口（节选）
| 接口 | 说明 |
|---|---|
| `/api/v1/replay/latest` | 复盘状态与数据（`pending`=未生成 / `ready`=就绪 / `empty`） |
| `/api/v1/market/distribution` | 涨跌区间分布（11 档） |
| `/api/v1/market/sectors/flow-top` | 行业/概念主力净流入流出 Top |
| `/api/v1/market/dragon-tiger` | 龙虎榜 |
| `/api/v1/stocks/{symbol}/industry-chain` | 产业链（行业板块 + 成分市值 TOP + 概念） |
| `/api/v1/stocks/{symbol}/industry-ranking` | 行业对比（中位数/排名/Top榜单） |
| `/api/v1/stocks/search` | 股票搜索（本地 A 股名称库优先） |
| `/api/v1/watchlist/items/batch-delete` | 自选批量删除 |
| `/api/v1/settings` | 系统设置（GET/PUT，含数据库测试） |
| `/api/v1/rss/sources` | RSS 订阅源 CRUD |
| `/api/v1/rss/items` | RSS 消息列表（支持 search/filter） |
| `/api/v1/rss/poll` | 手动触发轮询 |
| `/api/v1/rss/test` | 测试订阅地址是否可用 |

## 智能体配置
在「智能体中心」填入 OpenAI 兼容 API：
- API 地址：如 `https://api.deepseek.com/v1`
- API Key：`sk-...`
- 模型：如 `deepseek-chat`

> 未配置时智能体自动降级为内置启发式分析（个股/大盘/复盘），接口不会 500；模拟交易按本地规则决策（均线多头/放量买入，止损/止盈/破位卖出）。

## 定时任务
| 时间（Asia/Shanghai，交易日） | 任务 |
|---|---|
| 每 30 秒 | RSSHub 轮询（按单源 interval_sec 限频，去重后落库） |
| 09:25 / 10:30 / 13:30 / 14:50 | 盘中 AI 决策（模拟账户） |
| 15:10 | 收盘决策（当日已有成交的账户自动跳过） |
| 18:00 | 每日复盘（数据采集 + 智能体解读 + 次日选股池） |
| 20:00 | AI 模拟交易 + 提示词自我迭代 |

## 数据源
- 主：`新浪 + 腾讯`（`backend/app/core/datasource/sina_source.py`，实时行情/K线/分时/指数/搜索，**全真实数据，无 mock**）
- **多源链式降级**：`DataSourceManager` 按「设置→数据源」中的主源 + 备用源 1/2/3 顺序逐源调用（支持 `sina+tencent` 组合写法），当前源失败自动回退下一个；无需重启，运行时生效。
- 东财系（板块资金流/龙虎榜/财务/股东/资金K线）：直连 `push2delay.eastmoney.com` 等，网络不可达时**如实返回空**，前端显示「数据源受限」，不注入假数据
- K线/自选/名称库落库 SQLite，重复请求走缓存

### RSS 订阅源（预置案例，可直接请求）
- **预置 4 个实测可直连解析的公开 RSS（无需 RSSHub）**：雪球每日热帖、钛媒体TMT、IT之家、爱范儿；在「订阅消息」页可一键案例速选新增，均已实测可拉取入库存库。
- 微博 / 公众号 / 股吧 等平台推送走**本地 RSSHub 实例**（docker 中 11200 端口映射），应用内地址 `http://rsshub:1200`；rsshub 未启动时主业务不受影响（弱依赖）。
- **微博用户订阅的正确姿势**：先 `docker compose up -d rsshub`，然后在「设置 → RSSHub 订阅」确认实例地址为本机映射 `http://127.0.0.1:11200`；新建订阅时选平台「微博」并填 RSSHub 路径 `/weibo/user/{uid}`（如 `https://weibo.com/u/1645823934` 的 uid 为 `1645823934`）。**不要把微博网页地址直接填为订阅地址**——解析器会提示「地址返回的是 HTML 网页，而是 RSS」并置为失败状态，不会静默。

## Roadmap（待优化 / 待完成）
- **已完成发布准备**
  - ✅ SECRET_KEY 自动生成并持久化（`data/.secret_key`），可用环境变量覆盖
  - ✅ `DEBUG` 默认 `false`
  - ✅ favicon、前端 `manualChunks` 分包、release 打包脚本 `build_release.ps1`
- **待优化**
  - 前端打包体积：ECharts/element-plus 全量引入导致厂商包 ~1MB，后续按需引入（`echarts/core`、element-plus 按组件）
  - 补充 release 构建产物 smoke 测试脚本（解压→compose→health 自动断言）
- **数据与功能**
  - 若网络放开东财其他接口：恢复板块涨速、个股新闻、股东、情绪等真实数据源
  - 复盘 Markdown 原文渲染（当前为数据化表格）
  - AI 分析结果卡片化展示
  - 个股财务数据图表化（同比/环比趋势）
- **性能与容量**
  - ECharts 按需引入；element-plus 组件按需加载
  - 长期数据可迁移 PostgreSQL（Docker 已支持）；超大数据量考虑 TimescaleDB
- **安全与多用户**
  - 当前为单用户本地部署，无登录鉴权；对外部署需加用户系统 + JWT + 权限隔离
  - SQLite 并发写与多实例部署限制（PostgreSQL 路径已预留）

## 目录结构
```
backend/app
  api/v1          # REST 接口（market/watchlist/stock/replay/agent/simulation/trade/system/settings/rss）
  core/datasource # sina+tencent 直连（全真实） + EastMoney 资金/财务/龙虎榜 + 多源链式降级
  core/market     # 行情/自选/个股服务
  core/agent      # 智能体（LLM + 3 默认 + 执行器）
  core/czsc_engine# 缠论（分型/笔/中枢）
  core/simulation # 模拟交易（ST禁买 + 观察池轮转）
  core/replay     # 每日复盘
  core/trade_import # 实盘导入
  core/rsshub     # RSSHub 订阅（parser解析 + service轮询去重）
  core/settings   # 系统设置快照（DB 覆盖 env 默认值）
  models/rss.py, models/system.py  # rss_sources/rss_items + setting 表
  schemas, tasks, utils
frontend/src
  api, components, layout, views, router, styles
```

## 常见问题
- **行情数据**：实时/K线/分时来自新浪与腾讯直连，个别端点较慢时最多等约 15s；确实不可达的东财系数据如实返回空并提示「数据源受限」。
- **端口占用**：`scripts/run_server.py stop` 按端口强制清理；前端同理。
- **数据库**：数据保存在 `backend/data/quant.db`，删除后执行 `python -m scripts.init_db` 重建（Docker 部署在卷 `backend_data`）。
- **RSSHub 不可用**：本项目 RSSHub 走 Docker 本地镜像（`diygod/rsshub`），不依赖公网；应用启动不依赖 rsshub（弱依赖），rsshub 拉取失败不影响主业务；订阅轮询在 rsshub 启动后自动生效。
- **ST 漏检**：引擎与 RSS 解析器均使用 `(?<![A-Za-z0-9])(?:S[*★]?ST|\*?ST)(?![A-Za-z0-9])` 正则，已兼容中文 CJK 无空格场景（如"ST慧球"）。