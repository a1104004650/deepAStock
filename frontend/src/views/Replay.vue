<template>
  <MainLayout>
    <div class="page">
      <!-- 顶栏：标题 + 刷新 + 历史日期 + 触发生成 -->
      <PageHeader eyebrow="RESEARCH / DAILY REVIEW" title="每日复盘" subtitle="收盘快照 · 梯队结构 · 板块强弱 · 次日观察">
        <template #badge><el-tag v-if="rpt?.date" size="small" type="info">{{ rpt.date }}</el-tag></template>
        <template #actions>
          <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
          <el-select v-if="historyDates.length" v-model="viewDate" size="small" style="width:150px" placeholder="历史日期" @change="(d) => viewReport(d)">
            <el-option v-for="d in historyDates" :key="d" :label="d" :value="d" />
          </el-select>
          <el-button size="small" :loading="triggering" @click="trigger" :type="status === 'pending' ? 'danger' : 'warning'">生成今日收盘复盘</el-button>
          <el-button v-if="rpt?.report_md" size="small" @click="mdDialog = true">查看原文</el-button>
        </template>
      </PageHeader>

      <el-alert
        v-if="status === 'pending'"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
         :title="report?.message || '今日复盘尚未生成，交易日 18:00 自动生成；手动生成也须在 17:00 后'"
      />

      <el-alert
        v-if="status === 'gated'"
        type="error"
        :closable="false"
        show-icon
        class="mt8"
        :title="report?.message || '当前时间受限，无法生成该日期复盘'"
      />

      <el-alert
        v-if="rpt && (status === 'ready' || status === 'pending')"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
          :title="`报告日 ${rpt.date} · 公开行情归档；仅有 source=eastmoney 的板块行可按 f62 净流入解读，其他旧存档口径不明；历史日期不以实时行情重建`"
      />
      <el-alert
        v-if="rpt && !arr(rpt.sector_flow).length"
        type="info"
        :closable="false"
        show-icon
        class="mt8"
        title="板块资金流数据在休息时段可能为空"
      />

       <nav v-if="rpt" class="review-nav" aria-label="复盘工作区"><a href="#replay-verdict">市场结论</a><a href="#replay-ladder">连板梯队</a><a href="#replay-pool">次日观察</a><a href="#replay-sector">板块证据</a><a href="#replay-trades">我的交易</a></nav>

      <template v-if="rpt">
        <section id="replay-verdict" class="verdict-hero">
          <div class="hero-top"><span>收盘研究 / DAILY BRIEF</span><span>ARCHIVE NO. {{ rpt.date?.replaceAll('-', '') }}</span></div>
          <div class="hero-main">
            <div class="hero-copy">
              <div class="hero-date">{{ rpt.date }} <span>报告日 · 收盘存档</span></div>
              <h2>{{ ladderTone.label }}<span>，先看梯队再看宽度。</span></h2>
              <p>最高 {{ maxBoard || '暂无' }} 板 · 连板 {{ ladderStats.multiCount }} 家。上涨占比 {{ sentimentScore == null ? '暂无' : sentimentScore + '%' }}，仅为上涨家数占涨跌家数比例，不代表盈利概率。</p>
               <div class="hero-source">数据口径：公开源市场宽度 / 已标来源的板块净额 · 旧记录来源不明时不推断 · 非机构交易证明</div>
            </div>
            <div class="hero-meter"><span>市场宽度 / ADVANCERS</span><strong :class="sentimentScore != null && sentimentScore >= 50 ? 'up' : 'down'">{{ sentimentScore == null ? '-' : sentimentScore + '%' }}</strong><small>上涨 {{ rpt.market_summary?.distribution?.up_count ?? '-' }} / 下跌 {{ rpt.market_summary?.distribution?.down_count ?? '-' }}</small></div>
          </div>
          <div class="hero-tape">
            <div><span>涨停</span><b class="up">{{ rpt.market_summary?.limit_up_count ?? rpt.market_summary?.distribution?.limit_up ?? '-' }}</b><small>家</small></div>
            <div><span>跌停</span><b class="down">{{ rpt.market_summary?.distribution?.limit_down ?? '-' }}</b><small>家</small></div>
            <div><span>最高连板</span><b>{{ maxBoard || '-' }}</b><small>板</small></div>
            <div><span>连板占比</span><b>{{ profitEffect == null ? '-' : profitEffect + '%' }}</b><small>连板 / 涨停</small></div>
          </div>
        </section>

        <!-- 连板梯队主工作区：复盘先看高度、宽度和风险，不先看指数 -->
         <section id="replay-ladder" class="ladder-command mt8">
          <div class="ladder-command-head">
            <div>
              <div class="section-kicker">LIMIT-UP STRUCTURE / CORE SIGNAL</div>
              <div class="ladder-command-title">连板梯队</div>
              <div class="ladder-command-sub">先看最高板能否承载情绪，再看中位梯队是否扩散；数据不足时不强行给出晋级结论。</div>
            </div>
            <el-tag :type="ladderTone.type" effect="dark" size="large">{{ ladderTone.label }}</el-tag>
          </div>
          <div class="ladder-stat-grid">
            <div class="ladder-stat hot"><span>最高高度</span><strong>{{ maxBoard || '-' }}<small>板</small></strong><em>{{ ladderStats.maxName || '暂无高度板' }}</em></div>
            <div class="ladder-stat"><span>连板家数</span><strong>{{ ladderStats.multiCount }}</strong><em>2板及以上</em></div>
            <div class="ladder-stat"><span>首板家数</span><strong>{{ ladderStats.firstCount }}</strong><em>情绪扩散宽度</em></div>
            <div class="ladder-stat risk"><span>跌停家数</span><strong>{{ rpt.market_summary?.distribution?.limit_down ?? '-' }}</strong><em>负反馈观察</em></div>
          </div>
          <div v-if="ladderStats.leaders.length" class="ladder-leader-strip">
            <span class="strip-label">高度板观察</span>
            <button v-for="s in ladderStats.leaders" :key="s.symbol" type="button" class="leader-chip" @click="goStock(s.symbol, s.name)">
              <b>{{ s.name || s.symbol }}</b><span>{{ s.consecutive_days || maxBoard }}板</span>
            </button>
          </div>
          <el-empty v-else description="暂无连板数据，可能尚未收盘或数据源受限" :image-size="45" />
        </section>

        <section id="replay-pool" class="pool-panel">
          <div class="editorial-head"><div><span class="eyebrow">02 / NEXT SESSION</span><h3>次日观察池 <small>{{ arr(rpt.stock_pool).length }} 只</small></h3><p>基于报告日形态的观察清单，不构成交易建议。</p></div><span class="section-aside">关注封单、竞价与量能确认</span></div>
          <div class="table-scroll">
          <el-table :data="arr(rpt.stock_pool)" size="small" @row-click="(row) => goStock(row.symbol, row.name)">
            <el-table-column prop="symbol" label="代码" width="95" />
            <el-table-column prop="name" label="名称" width="90" />
            <el-table-column label="涨幅" width="75" align="right"><template #default="{ row }"><span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : (row.change_pct >= 0 ? '+' : '') + row.change_pct + '%' }}</span></template></el-table-column>
            <el-table-column label="价格" width="70" align="right"><template #default="{ row }">{{ row.price || '-' }}</template></el-table-column>
            <el-table-column label="表现" min-width="150"><template #default="{ row }"><div>{{ row.performance || row.reason || '-' }}</div><div v-if="row.pattern_tags?.length" class="mt4"><el-tag v-for="t in row.pattern_tags" :key="t" size="small" type="danger" effect="plain" class="mr8">{{ t }}</el-tag></div></template></el-table-column>
            <el-table-column label="观察要点" min-width="170"><template #default="{ row }">{{ row.suggestion || '关注' }}</template></el-table-column>
            <el-table-column label="日K量价形态" min-width="160"><template #default="{ row }"><el-tag size="small" :type="mainForceTag(row.main_force)" effect="plain">{{ row.main_force || '证据不足' }}</el-tag><div class="fs11 replay-force-reason">{{ row.main_force_reason || row.t_bias || '证据不足' }}</div></template></el-table-column>
          </el-table>
          </div>
          <el-empty v-if="!arr(rpt.stock_pool).length" description="暂无观察标的" :image-size="50" />
        </section>

        <section id="replay-sector" class="sector-panel">
          <div class="editorial-head"><div><span class="eyebrow">03 / SECTOR EVIDENCE</span><h3>板块证据 <small>资金与涨跌表现</small></h3><p>净流入为东方财富 f62 数据源分类估算，不代表机构真实交易。</p></div><el-button size="small" :loading="sectorTrendLoading" @click="loadSectorTrend">加载7日累计</el-button></div>
           <div class="table-scroll">
           <el-table :data="verifiedSectors" size="small" :default-sort="{ prop: 'net_inflow', order: 'descending' }">
            <el-table-column prop="sector_name" label="板块" min-width="110" fixed><template #default="{ row }"><div>{{ row.sector_name || row.name }}</div><div class="fs11 muted">{{ row.kind }}</div></template></el-table-column>
             <el-table-column prop="net_inflow" label="净流入 f62" align="right" width="120" sortable><template #default="{ row }"><span v-if="row.source === 'eastmoney' && row.net_inflow != null" class="mono" :class="row.net_inflow >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_inflow) }}</span><span v-else title="旧报告未记录资金数据来源，无法验证口径">不可核验</span></template></el-table-column>
            <el-table-column label="涨幅" align="right" width="80"><template #default="{ row }"><span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : (row.change_pct >= 0 ? '+' : '') + row.change_pct + '%' }}</span></template></el-table-column>
            <el-table-column prop="limit_up_count" label="今涨停" align="right" width="80" />
            <el-table-column prop="limit_down_count" label="今跌停" align="right" width="80" />
            <el-table-column v-if="sectorTrendDates.length" label="7日涨停" align="right" width="85"><template #default="{ row }">{{ row._trend?.sum_up ?? '-' }}</template></el-table-column>
            <el-table-column v-if="sectorTrendDates.length" label="7日跌停" align="right" width="85"><template #default="{ row }">{{ row._trend?.sum_down ?? '-' }}</template></el-table-column>
            <el-table-column label="领涨" min-width="95"><template #default="{ row }"><el-link v-if="row.leader_symbol" type="primary" :underline="false" @click="goStock(row.leader_symbol, row.leader)">{{ row.leader || '-' }}</el-link><span v-else>-</span></template></el-table-column>
            <el-table-column label="人气票" min-width="95"><template #default="{ row }"><el-link v-if="row.hot_pick?.symbol" type="primary" :underline="false" @click="goStock(row.hot_pick.symbol, row.hot_pick.name)">{{ row.hot_pick.name }}</el-link><span v-else>-</span></template></el-table-column>
          </el-table>
          </div>
           <el-empty v-if="!verifiedSectors.length" description="该报告没有可核验来源的板块净额快照" :image-size="50" />
        </section>

        <section id="replay-trades" class="card trade-panel">
          <div class="editorial-head"><div><span class="eyebrow">04 / PERSONAL LEDGER</span><h3>我的交易复盘 <small>{{ viewDay || '今日' }} 实盘交易</small></h3><p v-if="myPnl">当前持仓（非复盘日）{{ myPnl.position_count ?? 0 }} · 当前浮动盈亏 <span class="mono" :class="(myPnl.total_return || 0) >= 0 ? 'up' : 'down'">{{ fmtAmount(myPnl.total_return) }}</span></p></div><div class="trade-actions"><el-button size="small" :loading="myTradesLoading" @click="loadMyTrades">刷新</el-button><el-button size="small" @click="router.push('/trade')">去导入</el-button></div></div>
          <div class="table-scroll"><el-table v-if="myTradesOfDay.length" :data="myTradesOfDay" size="small" @row-click="(row) => goStock(row.symbol, row.name)">
            <el-table-column prop="trade_date" label="日期" width="110" /><el-table-column prop="symbol" label="代码" width="110" /><el-table-column prop="name" label="名称" min-width="110" />
            <el-table-column label="方向" width="80"><template #default="{ row }"><el-tag size="small" :type="row.action === 'buy' ? 'danger' : 'success'">{{ row.action === 'buy' ? '买入' : '卖出' }}</el-tag></template></el-table-column>
            <el-table-column prop="quantity" label="数量" align="right" /><el-table-column prop="price" label="价格" align="right" /><el-table-column label="金额" align="right"><template #default="{ row }">{{ fmtAmount(row.amount) }}</template></el-table-column><el-table-column prop="fee" label="费用" align="right" />
          </el-table></div>
          <el-empty v-if="!myTradesOfDay.length" :description="myTrades.length ? '当日无实盘交易，可切换上方历史日期查看' : '尚未导入实盘交易，点击「去导入」录入交割单'" :image-size="50" />
        </section>

        <details class="archive-details" @toggle="onArchiveToggle">
          <summary><span>更多数据与研究附录</span><small>近五日 · 图表 · 梯队明细 · 龙虎榜 · 投资日历 · AI 复盘</small></summary>
          <div v-if="archiveOpen">
        <section v-if="recentLadderDays.length" class="recent-ladder-card mt8">
          <div class="section-headline">
            <div><div class="section-kicker">5-DAY EMOTION TRACK</div><div class="fs14 bold">近五日短线情绪</div></div>
            <span class="fs11" style="color:#7d8390">晋级率看接力，断板率看风险，板块看扩散</span>
          </div>
          <div class="recent-days">
            <div v-for="day in recentLadderDays" :key="day.date" class="recent-day" :class="{ today: day.date === rpt?.date }">
              <div class="recent-date">{{ day.date?.slice(5) }}</div>
              <div class="recent-height"><b>{{ day.max_board || '-' }}</b><span>最高板</span></div>
              <div class="recent-line"><span>涨停</span><strong class="up">{{ day.limit_up ?? '-' }}</strong><span>连板</span><strong>{{ day.multi_board ?? '-' }}</strong></div>
              <div class="recent-line"><span>晋级</span><strong :class="day.promotion_rate >= 30 ? 'up' : 'down'">{{ day.promotion_rate ?? 0 }}%</strong><span>断板</span><strong class="down">{{ day.broken ?? 0 }}</strong></div>
              <div v-if="day.top_sectors?.length" class="recent-sector">{{ day.top_sectors[0].name }}</div>
            </div>
          </div>
        </section>

        <!-- 涨停跌停趋势（近一周） -->
        <div v-if="trendData.length" class="card mt8">
           <div class="fs14 bold">涨跌停与市场宽度 <span class="fs12" style="color:#7d8390">（已存档报告 · 截至所选日期）</span></div>
          <div ref="trendEl" style="width:100%;height:220px" class="mt8"></div>
        </div>

        <!-- 指数概况 + 上证K线 -->
        <div class="split-grid mt8">
          <div class="card">
            <div class="fs14 bold">大盘概况</div>
            <el-table :data="arr(rpt.market_summary?.indices) || []" size="small" class="mt8">
              <el-table-column prop="name" label="指数" />
              <el-table-column prop="price" label="点位" align="right" />
              <el-table-column label="涨跌幅" align="right">
                <template #default="{ row }">
                  <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct }}%</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="fs12 mt8" style="color:#7d8390">
               涨停 {{ rpt.market_summary?.distribution?.limit_up ?? '-' }} / 跌停 {{ rpt.market_summary?.distribution?.limit_down ?? '-' }}
            </div>
            <div class="fs12 mt8" v-if="arr(rpt.market_summary?.news).length">
              <span class="bold">要闻：</span>{{ rpt.market_summary.news[0].title }}
            </div>
          </div>

          <!-- 市场概况统计 -->
          <div class="card">
            <div class="fs14 bold">市场概况</div>
            <div class="mt8">
              <div class="flex gap" style="flex-wrap:wrap;align-items:center;margin-bottom:10px">
                <span class="fs12 up">上涨 {{ rpt.market_summary?.distribution?.up_count ?? '-' }}家</span>
                <span class="fs12 down">下跌 {{ rpt.market_summary?.distribution?.down_count ?? '-' }}家</span>
                <span class="fs12" style="color:#909399">平盘 {{ rpt.market_summary?.distribution?.flat_count ?? '-' }}家</span>
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                <div class="stat-item">
                  <div class="stat-value" style="font-size:20px;color:#f56c6c">{{ rpt.market_summary?.distribution?.limit_up ?? '0' }}</div>
                  <div class="stat-label">涨停</div>
                </div>
                <div class="stat-item">
                  <div class="stat-value" style="font-size:20px;color:#67c23a">{{ rpt.market_summary?.distribution?.limit_down ?? '0' }}</div>
                  <div class="stat-label">跌停</div>
                </div>
                <div class="stat-item">
                  <div class="stat-value mono" style="font-size:16px">{{ fmtMoney(rpt.market_summary?.distribution?.amount) }}</div>
                  <div class="stat-label">总成交额</div>
                </div>
                <div class="stat-item">
                  <div class="stat-value" style="font-size:16px">{{ sentimentScore }}</div>
                   <div class="stat-label">上涨占比 %</div>
                </div>
              </div>
              <div class="fs12 mt8" style="color:#7d8390">
                涨跌比 {{ (rpt.market_summary?.distribution?.up_count ?? 0) + (rpt.market_summary?.distribution?.down_count ?? 0) > 0 ? ((rpt.market_summary?.distribution?.up_count ?? 0) / ((rpt.market_summary?.distribution?.up_count ?? 0) + (rpt.market_summary?.distribution?.down_count ?? 0)) * 100).toFixed(1) : '-' }}% 上涨
              </div>
            </div>
            <div class="fs12 mt8" v-if="arr(rpt.market_summary?.news).length">
              <span class="bold">要闻：</span>{{ rpt.market_summary.news[0].title }}
            </div>
          </div>
        </div>

        <!-- 涨跌分布 + 板块资金流 TOP图表 -->
        <el-row :gutter="10" class="mt8">
          <el-col :xs="24" :sm="12">
            <div class="card">
              <div class="fs14 bold">涨跌分布</div>
              <div ref="distEl" style="height:200px" class="mt8"></div>
               <div class="fs12 mt4" style="color:#7d8390">上涨 / 下跌 / 平盘 · 报告日市场宽度</div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="card">
               <div class="fs14 bold">板块净流入 TOP10 <span class="fs12" style="color:#7d8390">（东方财富 f62 分类估算）</span></div>
               <div v-if="arr(rpt.sector_flow).some(s => s.source === 'eastmoney' && s.net_inflow != null)" ref="sectorEl" style="height:200px" class="mt8"></div>
               <el-empty v-else description="净流入来源无法核验（旧存档可能只有成交额）" :image-size="40" />
            </div>
          </el-col>
        </el-row>

        <!-- 涨停梯队 连板高度图 + 梯队 -->
         <div class="card mt8">
          <div class="fs14 bold">涨停梯队 <span class="fs12" style="color:#7d8390">（连板高度柱状图）</span></div>
          <div ref="ladderEl" style="height:200px" class="mt8"></div>
        </div>

         <div class="card mt8">
          <div class="fs14 bold">涨停梯队明细</div>
          <div class="ladder-scroller mt8">
            <div v-for="(stocks, board) in sortedLadder" :key="board" class="ladder-group">
              <div class="ladder-header">
                <el-tag size="small" :type="Number(board) >= 3 ? 'danger' : Number(board) >= 2 ? 'warning' : 'info'">
                  连板{{ board }}· {{ arr(stocks).length }}只
                </el-tag>
                <span v-if="Number(board) === maxBoard" class="fs11" style="color:#a87822;margin-left:4px">最高板</span>
              </div>
              <div class="ladder-stocks">
                <el-link v-for="s in arr(stocks)" :key="s.symbol" type="primary" :underline="false"
                  @click="goStock(s.symbol, s.name)" style="margin-right:10px">
                  {{ s.name }}
                  <span class="mono" :class="(s.change_pct||0) >= 0 ? 'up' : 'down'">{{ s.change_pct == null ? '' : (s.change_pct >= 0 ? '+' : '') + s.change_pct + '%' }}</span>
                </el-link>
              </div>
            </div>
            <el-empty v-if="!Object.keys(sortedLadder || {}).length" description="当日无涨停梯队（数据源受限）" :image-size="40" />
          </div>
        </div>

        <!-- 龙虎榜 + 席位游资聚合 -->
        <div class="card mt8">
          <div class="fs14 bold">龙虎榜 · 游资席位</div>
          <div v-if="seats.length" class="mt8">
            <div v-for="(group, tag) in seatGroups" :key="tag" class="seat-group">
              <div class="seat-group-header">
                <el-tag size="small" :type="tag === '机构专用' ? 'danger' : tag === '北向资金' ? 'success' : 'warning'" effect="plain">{{ tag || '营业部' }}</el-tag>
                <span class="fs11" style="color:#7d8390;margin-left:6px">{{ group.length }}笔</span>
                <span class="fs11 mono" :class="groupNet(group) >= 0 ? 'up' : 'down'" style="margin-left:6px">净 {{ fmtBig(groupNet(group)) }}</span>
              </div>
              <div v-for="s in group" :key="s.seat + s.symbol" class="seat-row">
                <el-link type="primary" :underline="false" @click="goStock(s.symbol, s.stock_name)" style="font-size:12px">{{ s.stock_name }}</el-link>
                <span class="fs11 mono" :class="(s.net||0) >= 0 ? 'up' : 'down'">{{ fmtBig(s.net) }}</span>
                <span class="fs11" style="color:#7d8390;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ s.seat_name }}</span>
              </div>
            </div>
          </div>
          <el-empty v-if="!seats.length" description="当日龙虎榜席位数据为空（收盘后才发布）" :image-size="50" />
          <el-divider v-if="arr(rpt.limit_analysis?.dragon_tiger).length && seats.length" content-position="left">上榜个股明细</el-divider>
          <el-table v-if="arr(rpt.limit_analysis?.dragon_tiger).length" :data="arr(rpt.limit_analysis?.dragon_tiger).slice(0, 10)" size="small"
            @row-click="(row) => goStock(row.symbol, row.name)">
            <el-table-column prop="name" label="名称" width="74" />
            <el-table-column prop="symbol" label="代码" width="88" />
            <el-table-column label="净买额" align="right" width="86">
              <template #default="{ row }">
                <span class="mono" :class="(row.net_amount||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="涨幅" width="62" align="right">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + row.change_pct + '%') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="140">
              <template #default="{ row }">{{ (row.reason || '').slice(0, 20) }}</template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 投资日历（未来45天 解禁 / 分红除权） -->
        <div class="card mt8">
          <div class="flex between" style="align-items:center">
             <span class="fs14 bold">当前投资日历 <span class="fs12" style="color:#7d8390">（未来45天，非复盘日历史事件）</span></span>
            <el-button size="small" :loading="calLoading" @click="loadCalendar">刷新</el-button>
          </div>
          <div class="split-grid mt8">
            <div class="cal-scroll">
              <div class="fs12 bold" style="color:#f56c6c;margin:2px 0">🛡 限售解禁 <span class="fs11" style="color:#7d8390">（{{ arr(calendar.unlocks).length }}笔，TOP解禁市值）</span></div>
              <div v-for="(u, i) in topUnlocks" :key="'u' + i" class="cal-row">
                <span class="cal-date">{{ (u.date || '').slice(5) }}</span>
                <el-link v-if="u.symbol" class="cal-name" type="danger" :underline="false" @click="goStock(u.symbol, u.name)">{{ u.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ u.name }}</span>
                <span class="cal-val mono fs12" style="color:#f56c6c">{{ u.market_cap_yi }}亿</span>
                <span class="cal-sub">{{ u.type }}</span>
              </div>
              <el-empty v-if="!topUnlocks.length" description="未来45天无解禁" :image-size="30" />
            </div>
            <div class="cal-scroll">
              <div class="fs12 bold" style="color:#67c23a;margin:2px 0">💰 分红除权 <span class="fs11" style="color:#7d8390">（{{ arr(calendar.dividends).length }}笔）</span></div>
              <div v-for="(d, i) in topDividends" :key="'d' + i" class="cal-row">
                <span class="cal-date">{{ (d.date || '').slice(5) }}</span>
                <el-link v-if="d.symbol" class="cal-name" type="success" :underline="false" @click="goStock(d.symbol, d.name)">{{ d.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ d.name }}</span>
                <span class="cal-val mono fs12" style="color:#67c23a">{{ (d.record_date || '').slice(5) }}除权</span>
                <span class="cal-sub">{{ d.plan }}</span>
              </div>
              <el-empty v-if="!topDividends.length" description="未来45天无分红除权" :image-size="30" />
            </div>
          </div>
        </div>

        <!-- Agent 复盘 -->
         <div v-if="Object.keys(rpt.agent_reviews || {}).length" class="card mt8">
           <div class="fs14 bold">AI 复盘（{{ Object.keys(rpt.agent_reviews || {}).length }} 个 Agent）</div>
          <el-row :gutter="10" class="mt8">
            <el-col v-for="(rv, at) in rpt.agent_reviews" :key="at" :xs="24" :sm="8">
               <div class="card">
                <el-tag size="small" :type="tagType(at)">{{ at }}</el-tag>
                <div class="fs12 mt8" style="line-height:1.9;white-space:pre-wrap">{{ rv.summary || rv.raw_output || '(' + JSON.stringify(rv).slice(0, 400) + ')' }}</div>
              </div>
            </el-col>
          </el-row>
        </div>
          </div>
        </details>
      </template>

      <el-empty v-else :description="(status === 'empty' && report?.message) || '暂无复盘报告，点击「生成复盘」手动触发（默认交易日 18:00 自动生成）'" />
      <section v-if="!rpt" class="card trade-panel">
        <div class="editorial-head"><div><span class="eyebrow">PERSONAL LEDGER</span><h3>我的交易复盘</h3><p>暂无市场报告时仍可查看已导入交易。</p></div><div class="trade-actions"><el-button size="small" :loading="myTradesLoading" @click="loadMyTrades">刷新</el-button><el-button size="small" @click="router.push('/trade')">去导入</el-button></div></div>
        <div class="table-scroll"><el-table v-if="myTradesOfDay.length" :data="myTradesOfDay" size="small" @row-click="(row) => goStock(row.symbol, row.name)"><el-table-column prop="trade_date" label="日期" width="110" /><el-table-column prop="symbol" label="代码" width="110" /><el-table-column prop="name" label="名称" min-width="110" /><el-table-column prop="action" label="方向" width="80" /><el-table-column prop="quantity" label="数量" align="right" /><el-table-column prop="price" label="价格" align="right" /><el-table-column label="金额" align="right"><template #default="{ row }">{{ fmtAmount(row.amount) }}</template></el-table-column><el-table-column prop="fee" label="费用" align="right" /></el-table></div>
        <el-empty v-if="!myTradesOfDay.length" description="该日无实盘交易，可从交易页导入交割单" :image-size="50" />
      </section>

      <el-dialog v-model="mdDialog" title="复盘报告原文" width="700">
        <pre class="md">{{ report?.report_md }}</pre>
      </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import { replayApi, marketApi, tradeApi } from '../api'
import { useSymbolStore } from '../stores/symbol'
import * as echarts from 'echarts'
import { fmtMoney, fmtLarge as fmtBig, fmtAmt as fmtAmount } from '../utils/format'

const router = useRouter()
const symbolStore = useSymbolStore()
const loading = ref(false)
const triggering = ref(false)
const report = ref(null)
const viewDate = ref('')
const historyDates = ref([])
const mdDialog = ref(false)
const archiveOpen = ref(false)
function onArchiveToggle(event) {
  archiveOpen.value = event.target.open
  if (archiveOpen.value) nextTick(renderCharts)
}
const calendar = ref({ date: '', unlocks: [], dividends: [] })
const calLoading = ref(false)
const seats = ref([])
const trendData = ref([])
const trendEl = ref(null)
let trendChart = null
const arr = (v) => (Array.isArray(v) ? v : [])
const recentLadderDays = computed(() => trendData.value.filter(d => d.date <= (rpt.value?.date || '')).slice(-5))

const distEl = ref(null)
const sectorEl = ref(null)
const ladderEl = ref(null)
let distChart = null
let sectorChart = null
let ladderChart = null

const rpt = computed(() => {
  const r = report.value
  if (!r) return null
  if (r.status === 'ready' || r.status === 'pending') return r.data || null
  return null
})
const rptv = computed(() => report.value)
const status = computed(() => report.value?.status || '')

const kline = ref([])
const sectorTrendRows = ref([])
const sectorTrendDates = ref([])
const sectorTrendLoading = ref(false)
const SECTOR_SNAP = 'replay_sector_snap_'

const topUnlocks = computed(() => [...(calendar.value.unlocks || [])]
  .sort((a, b) => b.market_cap_yi - a.market_cap_yi).slice(0, 6))
const topDividends = computed(() => [...(calendar.value.dividends || [])]
  .sort((a, b) => (a.date || '').localeCompare(b.date || '')).slice(0, 6))

const mergedSectors = computed(() => {
  const flow = arr(rpt.value?.sector_flow).slice(0, 15)
  const trendMap = {}
  for (const r of sectorTrendRows.value) {
    trendMap[r.sector] = r
  }
  return flow.map(f => ({
    ...f,
    _trend: trendMap[f.sector_name] || null
  }))
})

async function loadCalendar() {
  calLoading.value = true
  try { calendar.value = (await marketApi.investCalendar()) || { date: '', unlocks: [], dividends: [] } } catch { /* 保留旧数据 */ }
  calLoading.value = false
}

async function loadSeats() {
  const d = rpt.value?.date
  if (!d) { seats.value = []; return }
  try {
    const rows = (await marketApi.dragonTigerSeats(d)) || []
    seats.value = rows.sort((a, b) => Math.abs(b.net || 0) - Math.abs(a.net || 0)).slice(0, 30)
  } catch { seats.value = [] }
}

const seatGroups = computed(() => {
  const groups = {}
  for (const s of seats.value) {
    const tag = s.tag || '营业部'
    if (!groups[tag]) groups[tag] = []
    groups[tag].push(s)
  }
  // 按组内总净额绝对值排序
  const sorted = Object.entries(groups).sort((a, b) => {
    const aNet = a[1].reduce((s, x) => s + Math.abs(x.net || 0), 0)
    const bNet = b[1].reduce((s, x) => s + Math.abs(x.net || 0), 0)
    return bNet - aNet
  })
  return Object.fromEntries(sorted)
})

function groupNet(group) {
  return group.reduce((s, x) => s + (x.net || 0), 0)
}

async function loadTrend() {
  try {
    trendData.value = (await replayApi.trend(7)) || []
    nextTick(renderTrend)
  } catch { trendData.value = [] }
}

const sortedLadder = computed(() => {
  const raw = rpt.value?.limit_analysis?.ladder
  if (!raw || typeof raw !== 'object') return {}
  const entries = raw.ladder && typeof raw.ladder === 'object' ? raw.ladder : (Array.isArray(raw) ? {} : raw)
  if (!entries || typeof entries !== 'object') return {}
  const sorted = Object.entries(entries).sort((a, b) => Number(b[0]) - Number(a[0]))
  return Object.fromEntries(sorted)
})
const maxBoard = computed(() => {
  const keys = Object.keys(sortedLadder.value)
  const nums = keys.map(k => parseInt(k, 10)).filter(n => !isNaN(n))
  return nums.length ? Math.max(...nums) : 0
})
const verifiedSectors = computed(() => mergedSectors.value.filter(s => s.source === 'eastmoney' && s.net_inflow != null))
const ladderStats = computed(() => {
  const entries = Object.entries(sortedLadder.value)
  const stocks = entries.flatMap(([, rows]) => Array.isArray(rows) ? rows : [])
  const firstCount = Number((sortedLadder.value['1'] || []).length)
  const multiCount = stocks.filter((s) => Number(s.consecutive_days || s.board || 1) >= 2).length
  const leaders = (sortedLadder.value[String(maxBoard.value)] || []).slice(0, 6)
  return {
    firstCount,
    multiCount,
    maxName: leaders[0]?.name || leaders[0]?.symbol || '',
    leaders,
  }
})
const ladderTone = computed(() => {
  const down = Number(rpt.value?.market_summary?.distribution?.limit_down || 0)
  if (!maxBoard.value) return { label: '等待数据', type: 'info' }
  if (maxBoard.value >= 5 && down <= 8) return { label: '高位强势', type: 'danger' }
  if (maxBoard.value >= 3 && down <= 15) return { label: '结构分化', type: 'warning' }
  return { label: '弱势观察', type: 'info' }
})

const sentimentScore = computed(() => {
  const d = rpt.value?.market_summary?.distribution || {}
  const up = Number(d.up_count || 0)
  const down = Number(d.down_count || 0)
  return up + down ? Math.round(up / (up + down) * 100) : null
})

const profitEffect = computed(() => {
  const totalLimit = Number(rpt.value?.market_summary?.limit_up_count ?? rpt.value?.market_summary?.distribution?.limit_up ?? 0)
  return totalLimit ? Math.round(ladderStats.value.multiCount / totalLimit * 100) : null
})

function tagType(at) {
  return at === 'research' ? 'primary' : at === 'short_term' ? 'danger' : 'success'
}
function mainForceTag(value) {
  return value === '真拉升' ? 'danger' : value === '吸筹' || value === '诱空' ? 'warning' : value === '洗盘' ? 'info' : value === '出货' || value === '诱多' ? 'success' : 'info'
}
function arr1(v) { return Array.isArray(v) ? v : [] }
function goStock(symbol, name) {
  if (!symbol) return
  symbolStore.select(symbol, { name: name || symbol })
  try {
    const list = JSON.parse(localStorage.getItem('recent_viewed') || '[]')
    const filtered = list.filter(r => r.symbol !== symbol)
    filtered.unshift({ symbol, name: name || symbol, ts: Date.now() })
    localStorage.setItem('recent_viewed', JSON.stringify(filtered.slice(0, 30)))
  } catch {}
  router.push({ path: '/watchlist', query: { symbol } })
}

// ---- 我的交易复盘（实盘导入交易，按日对齐当前复盘日期） ----
const myTrades = ref([])
const myTradesLoading = ref(false)
const myPnl = ref(null)

const viewDay = computed(() => rpt.value?.date || viewDate.value || report.value?.date || dateStr(0))
const myTradesOfDay = computed(() =>
  myTrades.value.filter((t) => (t.trade_date || t.date || '').slice(0, 10) === viewDay.value))

async function loadMyTrades() {
  myTradesLoading.value = true
  try {
    const [trades, pnl] = await Promise.all([tradeApi.trades(), tradeApi.pnl().catch(() => null)])
    myTrades.value = trades || []
    myPnl.value = pnl
  } catch { myTrades.value = [] }
  myTradesLoading.value = false
}

function dateStr(backDays) {
  const d = new Date(Date.now() - backDays * 86400000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function loadKline() {
  try {
    const resp = await marketApi.kline('sh000001', { period: 'day' })
    const d = resp?.data || resp || []
    kline.value = (Array.isArray(d) ? d : []).map((x) => ({
      dt: x.dt || x.date,
      open: x.open, close: x.close, low: x.low, high: x.high, volume: x.volume,
    })).filter((x) => x.dt && x.dt.slice(0, 10) <= (rpt.value?.date || dateStr(0))).slice(-130)
  } catch {
    kline.value = []
  }
}

async function loadHistory() {
  try {
    const rows = (await replayApi.history()) || []
    const dates = (Array.isArray(rows) ? rows : []).map((r) => r.date || '').filter(Boolean)
    historyDates.value = [...new Set(dates)]
  } catch {
    historyDates.value = []
  }
}

async function loadSectorTrend() {
  sectorTrendLoading.value = true
  try {
    const rows = (await replayApi.history()) || []
    const dates = [...new Set((Array.isArray(rows) ? rows : []).map((r) => r.date || '').filter(d => d && d <= (rpt.value?.date || '')))].slice(0, 7).reverse()
    sectorTrendDates.value = dates
    const byName = {}
    for (const d of dates) {
      let snap = null
      try { snap = JSON.parse(localStorage.getItem(SECTOR_SNAP + d)) } catch { snap = null }
      if (!snap) {
        const rep = await replayApi.byDate(d)
        const flow = Array.isArray(rep?.sector_flow) ? rep.sector_flow : []
        snap = flow.map((f) => ({ sector: f.sector_name, up: f.limit_up_count, down: f.limit_down_count }))
        try { localStorage.setItem(SECTOR_SNAP + d, JSON.stringify(snap)) } catch { /* 本地存储满则跳过，不影响展示 */ }
      }
      for (const it of (snap || [])) {
        if (!it.sector) continue
        if (!byName[it.sector]) byName[it.sector] = { sector: it.sector, days: {}, sum_up: 0, sum_down: 0 }
        byName[it.sector].days[d] = { up: it.up ?? 0, down: it.down ?? 0 }
      }
    }
    for (const r of Object.values(byName)) {
      r.sum_up = Object.values(r.days).reduce((s, v) => s + (Number(v.up) || 0), 0)
      r.sum_down = Object.values(r.days).reduce((s, v) => s + (Number(v.down) || 0), 0)
    }
    sectorTrendRows.value = Object.values(byName).sort((a, b) => b.sum_up - a.sum_up)
  } catch {
    sectorTrendRows.value = []
    sectorTrendDates.value = []
  } finally {
    sectorTrendLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const r = await replayApi.latest()
    report.value = r
    const d = rpt.value?.date || r?.date
    if (d) viewDate.value = d
    await loadSeats()
    await loadHistory()
    loadSectorTrend()
    loadTrend()
    await loadKline()
    await nextTick()
    renderCharts()
  } catch {
    report.value = null
  } finally {
    loading.value = false
  }
}

async function viewReport(d) {
  if (!d) return
  try {
    const data = await replayApi.byDate(d)
    if (data) {
      report.value = { status: 'ready', date: d, data }
      viewDate.value = d
      await loadSeats()
      loadSectorTrend()
      loadKline()
      await nextTick()
      renderCharts()
    } else {
      report.value = { status: 'empty', date: d, message: '该日期暂无复盘记录，可用底部「生成复盘」为该日期生成' }
      viewDate.value = d
    }
  } catch {
    report.value = { status: 'gated', date: d, message: '加载失败，请检查后端服务' }
    viewDate.value = d
  }
}

async function trigger() {
  triggering.value = true
  try {
    const resp = await replayApi.trigger({ date: dateStr(0) })
    await loadHistory()
    if (resp?.status === 'success' && resp?.date) await viewReport(resp.date)
    else report.value = { ...report.value, status: 'gated', message: resp?.message || '收盘数据尚未就绪' }
  } finally {
    triggering.value = false
  }
}

function renderCharts() {
  if (!rpt.value || !archiveOpen.value) return
  renderDist()
  renderSector()
  renderLadder()
  renderTrend()
}

function renderTrend() {
  if (!trendEl.value || !trendData.value.length || !archiveOpen.value) return
  if (!trendChart) trendChart = echarts.init(trendEl.value)
  const rows = trendData.value.filter(d => d.date <= (rpt.value?.date || ''))
  if (!rows.length) return
  const dates = rows.map(d => d.date.slice(5))
  const sentimentLine = rows.map(d => {
    const up = Number(d.up_count || 0)
    const down = Number(d.down_count || 0)
    return up + down ? Math.round(up / (up + down) * 100) : null
  })
  const profitLine = rows.map(d => {
    const lu = Number(d.limit_up || 0)
    const mb = Number(d.multi_board || 0)
    return lu > 0 ? Math.round(mb / lu * 100) : null
  })
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#1c2028', borderColor: '#2a2f3a', textStyle: { color: '#d8dce6', fontSize: 12 } },
    legend: { top: 0, textStyle: { color: '#8b93a1', fontSize: 11 }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 50, right: 16, top: 36, bottom: 24 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#8b93a1', fontSize: 11 }, axisLine: { lineStyle: { color: '#2a2f3a' } } },
    yAxis: [
      { type: 'value', name: '数量', splitLine: { lineStyle: { color: '#2a2f3a33' } }, axisLabel: { color: '#8b93a1', fontSize: 11 }, axisLine: { show: false } },
      { type: 'value', name: '%', splitLine: { show: false }, axisLabel: { color: '#8b93a1', fontSize: 11 }, axisLine: { show: false } }
    ],
    series: [
       { name: '涨停数', type: 'bar', barWidth: 16, yAxisIndex: 0, data: rows.map(d => d.limit_up), itemStyle: { color: '#ef232a' } },
       { name: '跌停数', type: 'bar', barWidth: 16, yAxisIndex: 0, data: rows.map(d => d.limit_down), itemStyle: { color: '#14b143' } },
       { name: '连板率', type: 'line', yAxisIndex: 1, data: rows.map(d => d.consecutive_rate), lineStyle: { color: '#c47d14' } },
       { name: '断板率', type: 'line', yAxisIndex: 1, data: rows.map(d => d.broken_rate), lineStyle: { color: '#2e6bc6', type: 'dashed' } },
       { name: '上涨占比', type: 'line', yAxisIndex: 1, data: sentimentLine, lineStyle: { color: '#ef232a' } },
       { name: '连板占比', type: 'line', yAxisIndex: 1, data: profitLine, lineStyle: { color: '#8c61ac', type: 'dotted' } },
    ]
  }, true)
}

function renderDist() {
  if (!distEl.value) return
  const m = rpt.value?.market_summary?.distribution || {}
  const up = Number(m.up_count || 0)
  const down = Number(m.down_count || 0)
  const flat = Number(m.flat_count || 0)
  if (!distChart) distChart = echarts.init(distEl.value)
  distChart.setOption({
    backgroundColor: 'transparent',
    series: [{
      type: 'pie', radius: ['52%', '78%'], center: ['38%', '55%'],
       label: { color: '#57606f', fontSize: 11 },
      data: [
        { value: up, name: '上涨 ' + up, itemStyle: { color: '#ef232a' } },
         { value: down, name: '下跌 ' + down, itemStyle: { color: '#14b143' } },
         { value: flat, name: '平盘 ' + flat, itemStyle: { color: '#9aa3af' } },
      ],
      labelLine: { lineStyle: { color: '#4d5461' } },
    }],
     legend: { orient: 'vertical', right: 8, top: 'center', textStyle: { color: '#57606f', fontSize: 12 } },
    tooltip: { trigger: 'item' },
  }, true)
}

function renderSector() {
  if (!sectorEl.value) return
  const rows = [...arr1(rpt.value?.sector_flow)].filter(r => r.source === 'eastmoney' && r.net_inflow != null).sort((a, b) => Math.abs(b.net_inflow) - Math.abs(a.net_inflow)).slice(0, 10)
  if (!rows.length) return
  if (!sectorChart) sectorChart = echarts.init(sectorEl.value)
  const names = rows.map((r) => r.sector_name || r.name || '').reverse()
  const vals = rows.map((r) => r.net_inflow / 1e8).reverse()
  sectorChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: '#7d8390', fontSize: 10, formatter: (v) => v.toFixed(1) + '亿' }, splitLine: { lineStyle: { color: '#2c3240' } } },
     yAxis: { type: 'category', data: names, axisLabel: { color: '#57606f', fontSize: 10 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: vals, barWidth: '55%',
       itemStyle: { color: p => p.value >= 0 ? '#ef232a' : '#14b143', borderRadius: 2 },
       label: { show: true, position: p => p.value >= 0 ? 'right' : 'left', color: '#57606f', fontSize: 10, formatter: (p) => p.value.toFixed(1) + '亿' },
    }],
  }, true)
}

function renderLadder() {
  if (!ladderEl.value) return
  const l = sortedLadder.value
  const keys = Object.keys(l)
  if (!keys.length) return
  if (!ladderChart) ladderChart = echarts.init(ladderEl.value)
  const boards = keys.map(Number).sort((a, b) => a - b)
  const counts = boards.map((b) => arr1(l[b]).length)
  ladderChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 8, right: 30, top: 10, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: boards.map((b) => b + '板'), axisLabel: { color: '#c8ccd4', fontSize: 11 }, axisLine: { lineStyle: { color: '#2c3240' } } },
    yAxis: { type: 'value', axisLabel: { color: '#7d8390', fontSize: 10 }, splitLine: { lineStyle: { color: '#2c3240' } } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: counts, barWidth: '52%',
      itemStyle: { color: (p) => (boards[p.dataIndex] >= 3 ? '#f7b32b' : boards[p.dataIndex] >= 2 ? '#ef232a' : '#409eff'), borderRadius: 2 },
      label: { show: true, position: 'top', color: '#c8ccd4', fontSize: 11 },
    }],
  }, true)
}

function resizeCharts() {
  distChart && distChart.resize()
  sectorChart && sectorChart.resize()
  ladderChart && ladderChart.resize()
  trendChart && trendChart.resize()
}

watch(rpt, () => { if (rpt.value) { nextTick(renderCharts) } }, { deep: false })

onMounted(() => {
  load()
  loadCalendar()
  loadMyTrades()
  window.addEventListener('resize', resizeCharts)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  distChart && distChart.dispose()
  sectorChart && sectorChart.dispose()
  ladderChart && ladderChart.dispose()
  trendChart && trendChart.dispose()
})
</script>

<style scoped>
.page { max-width: 1440px; margin: 0 auto; padding: 12px 24px 56px; }
.verdict-hero { margin-top: 14px; background: #fff; border: 1px solid #e7e1d9; border-top: 4px solid #c33a37; box-shadow: 0 12px 36px rgba(31,41,55,.055); padding: 22px 28px 0; color: #222b35; }
.hero-top { display: flex; justify-content: space-between; gap: 12px; color: #946a62; font: 600 11px var(--font-mono, monospace); letter-spacing: .12em; }
.hero-main { display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 28px; padding: 24px 0 26px; align-items: center; }
.hero-date { color: #b83232; font: 700 17px var(--font-mono, monospace); }
.hero-date span { font: 500 12px sans-serif; color: #737c87; margin-left: 10px; }
.hero-copy h2 { font-size: clamp(27px, 3vw, 40px); line-height: 1.25; letter-spacing: -.04em; margin: 14px 0 10px; }
.hero-copy h2 span { font-weight: 450; }
.hero-copy p { font-size: 15px; line-height: 1.7; margin: 0; color: #46515f; }
.hero-source { font-size: 12px; color: #6c7582; border-left: 2px solid #c33a37; padding-left: 10px; margin-top: 19px; line-height: 1.6; }
.hero-meter { border-left: 1px solid #eee5df; padding-left: 24px; display: flex; flex-direction: column; gap: 8px; }
.hero-meter span { font-size: 11px; letter-spacing: .08em; color: #647080; }
.hero-meter strong { font: 700 46px var(--font-mono, monospace); line-height: 1; }
.hero-meter small { color: #606b77; font-size: 12px; }
.hero-tape { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid #eae6e1; }
.hero-tape > div { padding: 15px 12px 17px; display: flex; align-items: baseline; gap: 7px; border-right: 1px solid #eae6e1; }
.hero-tape > div:first-child { padding-left: 0; }
.hero-tape > div:last-child { border-right: 0; }
.hero-tape span { font-size: 12px; color: #626d78; margin-right: auto; }
.hero-tape b { font: 700 25px var(--font-mono, monospace); }
.hero-tape small { font-size: 11px; color: #77808b; }
.editorial-head { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.eyebrow { color: #aa3936; font: 700 11px var(--font-mono, monospace); letter-spacing: .13em; }
.editorial-head h3 { font-size: 24px; letter-spacing: -.03em; margin: 6px 0; color: #232d37; }
.editorial-head h3 small { color: #77808b; font-size: 13px; font-weight: 500; letter-spacing: 0; }
.editorial-head p, .section-aside { color: #687481; font-size: 12px; margin: 0; line-height: 1.6; }
.pool-panel, .sector-panel, .trade-panel { background: #fff; border: 1px solid #e2e6ea; padding: 22px 24px; margin-top: 16px; }
.pool-panel { border-top: 3px solid #bc3e3c; }
.sector-panel { border-top: 3px solid #d0a15b; }
.trade-panel { border-top: 3px solid #778394; }
.table-scroll { overflow-x: auto; }
.table-scroll :deep(.el-table) { min-width: 740px; }
.trade-actions { display: flex; white-space: nowrap; }
.muted { color: #75808b; }
.archive-details { margin-top: 18px; border: 1px solid #dfe3e8; background: #f8f9fa; padding: 0 18px 18px; }
.archive-details summary { cursor: pointer; min-height: 58px; display: flex; flex-wrap: wrap; align-items: center; gap: 12px; font-size: 15px; font-weight: 600; color: #33404e; }
.archive-details summary::before { content: '+'; font: 700 24px var(--font-mono, monospace); color: #ac3a38; }
.archive-details[open] summary::before { content: '-'; }
.archive-details summary small { color: #687481; font-size: 12px; font-weight: 400; }
.archive-details summary:focus-visible, .review-nav a:focus-visible, .leader-chip:focus-visible { outline: 2px solid #b32e2b; outline-offset: 2px; }
.up { color: #ef232a; }
.down { color: #14b143; }
.mono { font-family: Consolas, monospace; }
.card { background: var(--c-bg-card); border: 1px solid var(--c-border); border-radius: 6px; padding: 12px; color: var(--c-ink); }
.mt8 { margin-top: 8px; }
.mt4 { margin-top: 4px; }
.mr8 { margin-right: 8px; }
.fs12 { font-size: 12px; }
.fs14 { font-size: 14px; }
.replay-force-reason { color: #8b93a1; line-height: 1.45; margin-top: 3px; white-space: normal; }
.section-kicker { color:#f7b32b; font:600 10px var(--font-mono); letter-spacing:.1em; margin-bottom:3px; }
.ladder-command { background:linear-gradient(110deg,#192535,#26384a); border:1px solid #343d4c; border-radius:4px; padding:24px 28px; color:#d8dce6; }
.ladder-command-head, .section-headline { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.ladder-command-title { color:#fff; font-size:26px; font-weight:750; letter-spacing:-.03em; }
.ladder-command-sub { color:#8993a3; font-size:12px; margin-top:3px; }
.ladder-stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:16px; }
.ladder-stat { background:rgba(255,255,255,.055); border:1px solid rgba(255,255,255,.08); border-radius:6px; padding:10px 12px; }
.ladder-stat span, .ladder-stat em { display:block; color:#8993a3; font-size:11px; font-style:normal; }
.ladder-stat strong { display:block; color:#fff; font:700 25px var(--font-mono); margin:4px 0; }
.ladder-stat strong small { font:normal 11px inherit; margin-left:3px; color:#8993a3; }
.ladder-stat.hot strong { color:#f7b32b; }.ladder-stat.risk strong { color:#14b143; }
.ladder-leader-strip { display:flex; align-items:center; flex-wrap:wrap; gap:7px; margin-top:14px; padding-top:11px; border-top:1px solid rgba(255,255,255,.08); }
.strip-label { color:#8993a3; font-size:11px; margin-right:3px; }
.leader-chip { border:1px solid rgba(247,179,43,.35); background:rgba(247,179,43,.08); color:#f7b32b; border-radius:5px; padding:5px 8px; cursor:pointer; }
.leader-chip:hover { background:rgba(247,179,43,.17); }
.leader-chip span { color:#c8a96a; font:11px var(--font-mono); margin-left:6px; }
.recent-ladder-card { background:#fff; border:1px solid var(--c-border); border-radius:8px; padding:14px; }
.recent-days { display:grid; grid-template-columns:repeat(5,minmax(110px,1fr)); gap:8px; margin-top:10px; overflow-x:auto; }
.recent-day { border:1px solid #e2e6ec; border-radius:6px; padding:9px; background:#fafbfc; }
.recent-day.today { border-color:#f7b32b; box-shadow:inset 0 2px 0 #f7b32b; }
.recent-date { color:#7d8390; font:11px var(--font-mono); margin-bottom:5px; }
.recent-height { display:flex; align-items:baseline; gap:5px; }.recent-height b { color:#202733; font:700 21px var(--font-mono); }.recent-height span { color:#9099a7; font-size:10px; }
.recent-line { display:flex; align-items:center; justify-content:space-between; color:#9099a7; font-size:10px; margin-top:5px; }.recent-line strong { color:#303744; font:600 11px var(--font-mono); }
.recent-sector { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; margin-top:8px; padding-top:6px; border-top:1px solid #e7eaf0; color:#2e6bc6; font-size:11px; }
@media (max-width:820px) { .ladder-command-head { align-items:flex-start; flex-direction:column; }.ladder-stat-grid { grid-template-columns:repeat(2,1fr); }.recent-days { grid-template-columns:repeat(5, minmax(110px,1fr)); overflow-x:auto; padding-bottom:4px; }.recent-day { min-width:110px; } }
.fs11 { font-size: 11px; }
.bold { font-weight: 600; }
.flex { display: flex; }
.between { justify-content: space-between; }
.split-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.md {
  font-family: Consolas, 'Microsoft YaHei', monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  background: #15181f;
  color: #d8dce6;
  padding: 12px;
  border-radius: 6px;
  max-height: 70vh;
  overflow: auto;
}
.ladder-scroller { position: relative; }
.ladder-group { padding: 6px 0; border-bottom: 1px dashed #2a2f3a; }
.ladder-header { display: flex; align-items: center; margin-bottom: 4px; }
.ladder-stocks { display: flex; flex-wrap: wrap; gap: 4px; }
.cal-scroll { max-height: 260px; overflow: auto; }
.cal-row { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px dashed #2a2f3a; }
.cal-date { color: #626a77; font-size: 11px; flex-shrink: 0; width: 42px; }
.cal-name { flex-shrink: 0; }
.cal-val { flex-shrink: 0; }
.cal-sub { flex: 1; min-width: 0; text-align: right; color: #7d8390; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.seat-row { display: flex; align-items: center; gap: 5px; padding: 3px 0; border-bottom: 1px dashed #2a2f3a; font-size: 12px; }
.seat-group { margin-bottom: 8px; padding: 6px 0; border-bottom: 1px solid #2a2f3a33; }
.seat-group:last-child { border-bottom: none; }
.seat-group-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }

/* 深色表格微调 */
:deep(.el-table) { color: var(--c-ink); }
.review-nav { display:flex; gap:4px; overflow-x:auto; padding:10px 0; white-space:nowrap; }
.review-nav a { color:#394754; background:transparent; border-bottom:2px solid transparent; padding:12px 16px; text-decoration:none; font-size:13px; font-weight:600; }
.review-nav a:hover, .review-nav a:focus-visible { border-color:var(--c-primary); background:#edf3fb; }

/* H5 移动端适配 */
@media (max-width: 820px) {
  .page { padding: 8px 12px 36px; }
  .card { padding: 10px; }
  .split-grid { grid-template-columns: 1fr; }
  .hero-main { grid-template-columns: 1fr; gap: 18px; }
  .hero-meter { border-left: 0; border-top: 1px solid #eee5df; padding: 18px 0 0; }
  .hero-tape { grid-template-columns: repeat(2, 1fr); }
  .hero-tape > div:nth-child(2) { border-right: 0; }
  .hero-tape > div:nth-child(-n+2) { border-bottom: 1px solid #eae6e1; }
}
@media (max-width: 480px) {
  .card { padding: 8px; }
  .verdict-hero { padding: 18px 16px 0; }
  .hero-top { flex-wrap: wrap; }
  .hero-tape > div { padding: 12px 6px; flex-wrap: wrap; }
  .hero-tape span { width: 100%; }
  .editorial-head { align-items: flex-start; flex-direction: column; }
  .pool-panel, .sector-panel, .trade-panel { padding: 16px 12px; }
  .section-aside { display: none; }
  .seat-row { flex-wrap: wrap; }
}
</style>
