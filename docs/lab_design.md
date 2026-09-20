# 实验室 - AI驱动模块设计

## 整体架构

实验室 = 独立沙箱，与主系统隔离。AI调用、数据、交易、配置全部隔离。

```
实验室 (Lab)
  AI炒股比赛 (Competition)     - 多AI实时对决, 群聊+排行榜
  AI投研团队 (ResearchTeam)    - 多角色协作分析, 工作流+报告
  共享基础设施
    AI沙箱 (独立token配置, 隔离调用)
    模拟交易引擎 (复用现有, 独立账户体系)
    群聊/消息系统
    数据获取 (只读)
```

---

## 模块一: AI炒股比赛

### 核心概念

- **比赛 (Competition)**: 一场AI对决，有时间范围、股票池、参赛者
- **参赛者 (Participant)**: 一个AI选手，绑定独立LLM配置
- **模拟账户**: 每个参赛者独立账户，初始资金、持仓、交易记录
- **群聊 (ChatRoom)**: 比赛期间AI们可以发言、观察、互动
- **排行榜 (Leaderboard)**: 实时收益排名

### 流程

1. 用户创建比赛 → 设置股票池(可不限)、初始资金、比赛时间
2. 添加参赛者 → 每个参赛者配置不同AI(可相同模型不同提示词,或不同模型)
3. 交易日自动执行 → 每个AI独立决策买卖
4. AI群聊 → 盘中AI可以发言(分析、预测、互动)
5. 收盘结算 → 更新排行榜, AI自我复盘
6. 比赛结束 → 最终排名, 获胜者

### 关键规则

- 仅交易日、交易时段(9:30-11:30, 13:00-15:00)可交易
- T+1规则, ST禁买
- 同一比赛内不同AI的选股池自动分散(防扎堆)
- 每个AI有独立的风控规则(止损止盈)

### 数据表

```
lab_competitions        比赛表
  id, name, description, status(筹备/进行中/已结束),
  stock_pool(JSON: ["600519","000858"] or null=不限),
  initial_capital, start_date, end_date,
  created_at, updated_at

lab_participants        参赛者表
  id, competition_id(FK), name, avatar,
  provider, api_base, api_key, model_name,
  system_prompt(自定义AI人设),
  account_capital, account_return,
  status(活跃/已淘汰),
  created_at

lab_positions           持仓表
  id, participant_id(FK), symbol, name,
  quantity, avg_cost, current_price, unrealized_pnl

lab_trades              交易表
  id, participant_id(FK), symbol, name,
  action(buy/sell), quantity, price, amount, fee,
  reason(AI给出的理由), confidence,
  timestamp

lab_chat_messages       群聊消息表
  id, competition_id(FK), participant_id(FK nullable, null=系统消息),
  content, message_type(text/analysis/alert/system),
  created_at

lab_leaderboard         排行榜快照表
  id, competition_id(FK), snapshot_date,
  participant_id(FK), total_return, win_rate,
  max_drawdown, total_trades, rank
```

### AI群聊机制

- 每个交易时段(开盘/午盘/尾盘), AI自动发言:
  - 今日市场观察
  - 自己的交易决策和理由
  - 对其他AI的评论(可选)
- 用户可以看到所有AI的对话
- AI发言时可引用实时数据

### 排行榜

实时计算:
- 总收益率 = (当前总资产 - 初始资金) / 初始资金
- 胜率, 最大回撤, 交易次数
- 综合评分 = 收益率*0.5 + 胜率*0.2 - 最大回撤*0.3

---

## 模块二: AI投研团队

### 核心概念

- **研究任务 (ResearchTask)**: 用户输入股票代码, 发起一次研究
- **分析师 (Analyst)**: AI角色, 每个有独立人设和分析视角
- **工作流 (Workflow)**: 分析师按流程协作 → 独立研究 → 交叉讨论 → 综合报告
- **研究报告 (Report)**: 最终产出, 多视角综合分析

### 分析师角色

| 角色 | 人称 | 关注点 | 分析框架 |
|------|------|--------|----------|
| 巴菲特AI | 价值投资大师 | 护城河、估值、长期价值、管理层 | 内在价值法, 安全边际 |
| 芒格AI | 多元思维模型 | 检查清单、逆向思考、心理学陷阱 | 25种误判心理学, 多学科思维 |
| 游资AI | 短线交易高手 | 龙虎榜、资金动向、情绪面、题材 | 情绪周期, 龙头战法 |
| 技术派AI | 技术分析专家 | K线形态、均线系统、MACD/RSI | 趋势理论, 波浪理论 |
| 量化AI | 量化分析 | 因子模型、统计套利、风险评估 | 多因子模型, 蒙特卡洛模拟 |

### 工作流 (4阶段)

```
Stage 1: 独立研究 (Parallel)
  各分析师独立获取数据、分析、产出初步观点

Stage 2: 交叉质询 (Sequential)  
  每个分析师阅读其他人的报告, 提出质疑或补充

Stage 3: 综合讨论 (Group)
  所有分析师的最终观点汇总, 找出共识和分歧

Stage 4: 最终报告 (AI Summarizer)
  综合所有输入, 生成结构化报告:
  - 基本面评分 (0-10)
  - 技术面评分 (0-10)
  - 情绪面评分 (0-10)
  - 综合建议 (强烈推荐/推荐/中性/谨慎/回避)
  - 目标价区间
  - 关键风险
  - 各分析师摘要
```

### 数据表

```
lab_research_tasks      研究任务表
  id, symbol, stock_name, status(研究中/已完成/失败),
  stage(独立研究/交叉质询/综合讨论/最终报告),
  created_at, completed_at

lab_analysts            分析师配置表
  id, name, role(价值/博弈/技术/量化/综合),
  avatar, system_prompt,
  provider, api_base, api_key, model_name,
  is_active, sort_order

lab_analyst_reports     分析师报告表
  id, task_id(FK), analyst_id(FK),
  stage, content(JSON: {view, score, reasoning, concerns}),
  created_at

lab_research_reports    最终研究报告表
  id, task_id(FK),
  fundamental_score, technical_score, sentiment_score,
  overall_score, recommendation, target_price_range,
  risk_factors(JSON), consensus(JSON), divergences(JSON),
  full_report(Markdown), created_at
```

---

## AI沙箱 (隔离层)

### 配置隔离

每个参赛者/分析师有独立的:
- provider (openai/deepseek/qwen/zhipu/claude/gemini/ollama)
- api_base (API地址)
- api_key (API密钥, 加密存储)
- model_name (模型名称)
- system_prompt (系统提示词, 可自定义)

### 调用隔离

- 使用现有 `LLMClient` (支持7个provider)
- 每个AI实例独立创建, 不共享状态
- 失败时使用本地分析fallback

### 交易隔离

- 实验室使用独立的模拟交易引擎
- 不影响主系统的模拟盘
- 独立的账户体系

---

## 复用现有代码

| 现有模块 | 复用方式 |
|----------|----------|
| LLMClient | 直接使用, 支持7个provider |
| SimulationEngine | 复用交易执行逻辑, 独立账户 |
| DataSourceManager | 复用数据获取, 只读模式 |
| 涨停/龙虎榜/资金流 | 复用数据获取 |
| APScheduler | 复用定时任务, 新增比赛调度 |

---

## 前端页面

### 比赛模块
- `/lab/competitions` - 比赛列表
- `/lab/competitions/create` - 创建比赛
- `/lab/competitions/:id` - 比赛详情(排行榜+群聊+持仓)
- `/lab/competitions/:id/chat` - 群聊页面

### 投研模块
- `/lab/research` - 研究任务列表
- `/lab/research/create` - 发起研究
- `/lab/research/:id` - 研究过程(分析师动态+报告)
- `/lab/research/analysts` - 分析师管理

### 配置模块
- `/lab/settings` - 实验室AI配置(全局默认)
