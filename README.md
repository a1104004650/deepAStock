# deepAStock 深度A股交易

深度 A 股 AI 交易平台（PC/H5）。围绕「看盘 → 选股 → 交易 → 复盘 → 进化」闭环，内置 3 个默认 AI 智能体（投研 / 短线 / 波段），支持模拟交易、实盘导入、缠论分析、每日自动复盘。

> 发布说明 & 版本日志见 [CHANGELOG.md](CHANGELOG.md) · 需求来源 `提示词.txt` 与 `量化交易系统开发需求讨论.markdown`

## 部署方式（推荐：Docker，无需安装 Python/Node）
> 对使用者而言这是唯一需要的方式：解压 → `docker compose up -d --build` → 打开浏览器，即可用。
> 数据库默认 SQLite（零配置）；如有自己的 PostgreSQL，改两个环境变量即可切换（见下）。

### 1. 获取release包
```bash
# 开发者：自己打 release 包
powershell -ExecutionPolicy Bypass -File build_release.ps1
# 产出：release/deepAStock-v1.0.0.zip（含完整项目 + Docker 全家桶 + 文档）
```

### 2. 部署（使用者）
```bash
unzip deepAStock-v1.0.0.zip
cd deepAStock-v1.0.0
docker compose up -d --build     # 首次构建约需数分钟，之后秒级
# 打开浏览器 http://localhost   （接口文档 http://localhost:8000/docs）
docker compose logs -f app       # 看日志
docker compose down              # 停止
docker compose up -d             # 再次启动（增量秒级）
```

### 端口
| 端口 | 用途 |
|---|---|
| `80`  | 前端页面（Nginx 托管 `frontend/dist`，`/api` 反代到同容器 8000） |
| `8000` | 后端接口（uvicorn，可直接访问 /docs） |

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
| `APP_VERSION` | 1.0.0 | 显示版本 |
| `PRIMARY_SOURCE/BACKUP_SOURCE` | sina+tencent | 行情数据源 |

## 本机开发（开发者）

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
| 模拟交易 | `/simulation` | 多账户，AI 每日决策买卖，收益曲线 + 绩效统计（收益率/胜率/最大回撤） |
| 实盘导入 | `/trade` | JSON/CSV 导入真实成交，持仓与盈亏汇总 |
| 智能体中心 | `/agents` | 3 个默认智能体 + 自定义，配置 API/模型/提示词，大盘分析 |

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

## 智能体配置
在「智能体中心」填入 OpenAI 兼容 API：
- API 地址：如 `https://api.deepseek.com/v1`
- API Key：`sk-...`
- 模型：如 `deepseek-chat`

> 未配置时智能体自动降级为内置启发式分析（个股/大盘/复盘），接口不会 500；模拟交易按本地规则决策（均线多头/放量买入，止损/止盈/破位卖出）。

## 定时任务
| 时间（Asia/Shanghai，交易日） | 任务 |
|---|---|
| 09:25 / 10:30 / 13:30 / 14:50 | 盘中 AI 决策（模拟账户） |
| 15:10 | 收盘决策（当日已有成交的账户自动跳过） |
| 18:00 | 每日复盘（数据采集 + 智能体解读 + 次日选股池） |
| 20:00 | AI 模拟交易 + 提示词自我迭代 |

## 数据源
- 主：`新浪 + 腾讯`（`backend/app/core/datasource/sina_source.py`，实时行情/K线/分时/指数/搜索，**全真实数据，无 mock**）
- 东财系（板块资金流/龙虎榜/财务/股东/资金K线）：直连 `push2delay.eastmoney.com` 等，网络不可达时**如实返回空**，前端显示「数据源受限」，不注入假数据
- K线/自选/名称库落库 SQLite，重复请求走缓存

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
  api/v1          # REST 接口（market/watchlist/stock/replay/agent/simulation/trade/system）
  core/datasource # sina+tencent 直连（全真实） + EastMoney 资金/财务/龙虎榜
  core/market     # 行情/自选/个股服务
  core/agent      # 智能体（LLM + 3 默认 + 执行器）
  core/czsc_engine# 缠论（分型/笔/中枢）
  core/simulation # 模拟交易
  core/replay     # 每日复盘
  core/trade_import # 实盘导入
  models, schemas, tasks, utils
frontend/src
  api, components, layout, views, router, styles
```

## 常见问题
- **行情数据**：实时/K线/分时来自新浪与腾讯直连，个别端点较慢时最多等约 15s；确实不可达的东财系数据如实返回空并提示「数据源受限」。
- **端口占用**：`scripts/run_server.py stop` 按端口强制清理；前端同理。
- **数据库**：数据保存在 `backend/data/quant.db`，删除后执行 `python -m scripts.init_db` 重建（Docker 部署在卷 `backend_data`）。