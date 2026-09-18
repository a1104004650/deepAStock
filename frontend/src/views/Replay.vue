<template>
  <MainLayout>
    <div class="page">
      <!-- 顶栏：标题 + 刷新 + 历史日期 + 触发生成 -->
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">每日复盘 <span class="fs12" style="color:#7d8390">· A股游资橙红主题</span></h2>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
        <el-select v-if="historyDates.length" v-model="viewDate" size="small" style="width:170px;margin-left:8px"
          placeholder="历史复盘日期" @change="(d) => viewReport(d)">
          <el-option v-for="d in historyDates" :key="d" :label="d" :value="d" />
        </el-select>
        <el-tag v-if="rpt?.date" size="small" type="info" style="margin-left:8px">查看 {{ rpt.date }}</el-tag>
        <el-select v-model="triggerDate" size="small" style="width:150px;margin-left:8px">
          <el-option v-for="i in 30" :key="i" :label="dateStr(i) + (i === 0 ? '（今日）' : '')" :value="dateStr(i)" />
        </el-select>
        <el-button size="small" :loading="triggering" @click="trigger"
          :type="status === 'pending' ? 'danger' : 'warning'">
          生成复盘
        </el-button>
        <el-tag v-if="status === 'pending'" size="small" type="warning">今日尚未生成，交易日 18:00 自动复盘</el-tag>
        <el-tag v-if="status === 'empty'" size="small" type="info">暂无复盘记录</el-tag>
        <div style="flex:1"></div>
        <el-button v-if="rpt?.report_md" size="small" @click="mdDialog = true">查看复盘原文 (Markdown)</el-button>
      </div>

      <el-alert
        v-if="status === 'pending'"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
        :title="report?.message || '今日复盘尚未生成，交易日 18:00 将自动生成，也可点击「生成复盘」立即生成'"
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
        title="市场数据以东方财富当日收盘为准；同一交易日多次生成只保留最新一份复盘"
      />
      <el-alert
        v-if="rpt && rpt.sector_flow?.length === undefined"
        type="info"
        :closable="false"
        show-icon
        class="mt8"
        title="板块资金流数据在休息时段可能为空"
      />

      <!-- 我的交易复盘（实盘导入，按复盘日对齐；无市场报告也可查看） -->
      <div class="card mt8">
        <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
          <span class="fs14 bold">我的交易复盘 <span class="fs12" style="color:#7d8390">（{{ viewDay || '今日' }} 实盘交易）</span></span>
          <div class="flex gap" style="align-items:center">
            <span v-if="myPnl" class="fs12" style="color:#7d8390">
              持仓 {{ myPnl.position_count ?? 0 }} · 浮动盈亏
              <span class="mono" :class="(myPnl.total_return || 0) >= 0 ? 'up' : 'down'">{{ fmtAmount(myPnl.total_return) }}</span>
            </span>
            <el-button size="small" :loading="myTradesLoading" @click="loadMyTrades">刷新</el-button>
            <el-button size="small" @click="router.push('/trade')">去导入</el-button>
          </div>
        </div>
        <el-table v-if="myTradesOfDay.length" :data="myTradesOfDay" size="small" class="mt8"
          @row-click="(row) => goStock(row.symbol, row.name)">
          <el-table-column prop="trade_date" label="日期" width="110" />
          <el-table-column prop="symbol" label="代码" width="110" />
          <el-table-column prop="name" label="名称" min-width="110" />
          <el-table-column label="方向" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.action === 'buy' ? 'danger' : 'success'">{{ row.action === 'buy' ? '买入' : '卖出' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" align="right" />
          <el-table-column prop="price" label="价格" align="right" />
          <el-table-column label="金额" align="right">
            <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="fee" label="费用" align="right" />
        </el-table>
        <el-empty v-else :description="myTrades.length ? '当日无实盘交易，可切换上方历史日期查看' : '尚未导入实盘交易，点击「去导入」录入交割单'"
          :image-size="50" />
      </div>

      <template v-if="rpt">
        <!-- 情绪 KPI 条 -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">涨停家数</div>
            <div class="kpi-val up">{{ rpt.limit_up_count ?? '-' }}<span class="kpi-unit">家</span></div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">跌停家数</div>
            <div class="kpi-val down">{{ rpt.limit_down_count ?? '-' }}<span class="kpi-unit">家</span></div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">上涨家数</div>
            <div class="kpi-val up">{{ rpt.market_summary?.distribution?.up_count ?? '-' }}<span class="kpi-unit">家</span></div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">下跌家数</div>
            <div class="kpi-val down">{{ rpt.market_summary?.distribution?.down_count ?? '-' }}<span class="kpi-unit">家</span></div>
          </div>
          <div class="kpi-card accent">
            <div class="kpi-label">最高连板</div>
            <div class="kpi-val" style="color:#f7b32b">{{ maxBoard || '-' }}<span class="kpi-unit">板</span></div>
          </div>
          <div class="kpi-card accent">
            <div class="kpi-label">情绪温度</div>
            <div class="kpi-val" style="color:#f7b32b">{{ sentimentScore }}<span class="kpi-unit">/100</span></div>
          </div>
        </div>

        <!-- 涨停跌停趋势（近一周） -->
        <div v-if="trendData.length" class="card mt8">
          <div class="fs14 bold">涨停/跌停趋势 <span class="fs12" style="color:#7d8390">（近一周）</span></div>
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
              涨停 {{ arr(rpt.market_summary?.distribution) && (rpt.market_summary?.distribution) ? (rpt.market_summary?.distribution.up_count ?? '-') : '-' }} / 跌停 {{ arr(rpt.market_summary?.distribution) && (rpt.market_summary?.distribution) ? (rpt.market_summary?.distribution.down_count ?? '-') : '-' }}
            </div>
            <div class="fs12 mt8" v-if="arr(rpt.market_summary?.news).length">
              <span class="bold">要闻：</span>{{ rpt.market_summary.news[0].title }}
            </div>
          </div>

          <!-- 大盘概况（复盘不看上证指数K线形态，已移除K线栏位） -->
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
              涨停 {{ arr(rpt.market_summary?.distribution) && (rpt.market_summary?.distribution) ? (rpt.market_summary?.distribution.up_count ?? '-') : '-' }} / 跌停 {{ arr(rpt.market_summary?.distribution) && (rpt.market_summary?.distribution) ? (rpt.market_summary?.distribution.down_count ?? '-') : '-' }}
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
              <div class="fs12 mt4" style="color:#7d8390">上涨 vs 下跌 vs 平盘（含涨停/跌停标记）</div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="card">
              <div class="fs14 bold">板块资金流 TOP10 <span class="fs12" style="color:#7d8390">（主力净流入）</span></div>
              <div ref="sectorEl" style="height:200px" class="mt8"></div>
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
                <span v-if="Number(board) === maxBoard" class="fs11" style="color:#f7b32b;margin-left:4px">🔥最高板</span>
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

        <!-- 板块资金流 明细表 -->
        <div class="card mt8">
          <div class="fs14 bold">板块资金流明细 <span class="fs12" style="color:#7d8390">（主力净流入排序）</span></div>
          <el-table :data="arr(rpt.sector_flow).slice(0, 12)" size="small" class="mt8">
            <el-table-column prop="sector_name" label="板块" min-width="110">
              <template #default="{ row }">{{ row.sector_name || row.name }}</template>
            </el-table-column>
            <el-table-column label="主力净" align="right" width="90">
              <template #default="{ row }">
                <span class="mono" :class="(row.net_inflow||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_inflow) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="净占比" align="right" width="70">
              <template #default="{ row }">{{ row.net_ratio == null ? '-' : row.net_ratio + '%' }}</template>
            </el-table-column>
            <el-table-column label="涨幅" align="right" width="70">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + row.change_pct + '%') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="涨停" align="right" width="64">
              <template #default="{ row }">
                <span class="mono up">{{ row.limit_up_count ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="跌停" align="right" width="64">
              <template #default="{ row }">
                <span class="mono down">{{ row.limit_down_count ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="领涨" min-width="90">
              <template #default="{ row }">
                <el-link v-if="row.leader_symbol" type="primary" :underline="false" @click="goStock(row.leader_symbol, row.leader)">
                  {{ row.leader || '-' }}
                </el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="市值龙头" min-width="130">
              <template #default="{ row }">
                <span v-for="(m, i) in (row.mkt_cap_top || [])" :key="i" class="fs12 mr8">
                  {{ ['龙一', '龙二', '龙三'][i] }}:
                  <el-link v-if="m.symbol" type="primary" :underline="false" @click="goStock(m.symbol, m.name)">{{ m.name }}</el-link>
                </span>
                <span v-if="!(row.mkt_cap_top || []).length">-</span>
              </template>
            </el-table-column>
            <el-table-column label="人气票" width="70">
              <template #default="{ row }">
                <el-link v-if="row.hot_pick?.symbol" type="primary" :underline="false" @click="goStock(row.hot_pick.symbol, row.hot_pick.name)">{{ row.hot_pick.name }}</el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!arr(rpt.sector_flow).length" description="当日东方财富板块资金数据为空（休市或网络受限）" :image-size="50" />
        </div>

        <!-- 板块涨停/跌停排行（近7交易日，真实数据本地累计） -->
        <div class="card mt8">
          <div class="flex between" style="align-items:center">
            <span class="fs14 bold">板块涨停/跌停排行（近7交易日）</span>
            <el-button size="small" :loading="sectorTrendLoading" @click="loadSectorTrend">拉取7日板块涨停/跌停</el-button>
          </div>
          <div class="fs12 mt8" style="color:#7d8390">
            共 {{ sectorTrendDates.length }} 个交易日：每日 涨停家数/跌停家数 由当日真实报告写入 localStorage 累计，休市日显示 -（无伪造）
          </div>
          <el-table v-if="sectorTrendRows.length" :data="sectorTrendRows" size="small" class="mt8">
            <el-table-column prop="sector" label="板块" min-width="110" fixed />
            <el-table-column v-for="d in sectorTrendDates" :key="'d' + d" :label="d.slice(5)" align="right" min-width="92">
              <template #default="{ row }">
                <span v-if="row.days[d]" class="mono">
                  <span class="up">{{ row.days[d].up ?? '-' }}</span>
                  <span class="down">/{{ row.days[d].down ?? '-' }}</span>
                </span>
                <span v-else class="mono" style="color:#7d8390">-</span>
              </template>
            </el-table-column>
            <el-table-column label="7日合计涨停" align="right" width="104" fixed="right">
              <template #default="{ row }">
                <span class="mono up">{{ row.sum_up ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="7日合计跌停" align="right" width="104" fixed="right">
              <template #default="{ row }">
                <span class="mono down">{{ row.sum_down ?? '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!sectorTrendRows.length" description="近7日板块涨停/跌停数据为空（休市或交易日报告未积累）" :image-size="50" />
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

        <!-- 次日选股池 -->
        <div class="card mt8">
          <div class="fs14 bold">次日选股池（{{ arr(rpt.stock_pool).length }}）</div>
          <el-table :data="arr(rpt.stock_pool)" size="small" class="mt8" @row-click="(row) => goStock(row.symbol, row.name)">
            <el-table-column prop="symbol" label="代码" width="95" />
            <el-table-column prop="name" label="名称" width="90" />
            <el-table-column label="涨幅" width="75" align="right">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">
                  {{ (row.change_pct||0) >= 0 ? '+' : '' }}{{ row.change_pct || '-' }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="价格" width="70" align="right">
              <template #default="{ row }">{{ row.price || '-' }}</template>
            </el-table-column>
            <el-table-column label="表现" min-width="100">
              <template #default="{ row }">
                <div>{{ row.performance || row.reason || '-' }}</div>
                <div v-if="row.pattern_tags && row.pattern_tags.length" style="margin-top:2px">
                  <el-tag v-for="t in row.pattern_tags" :key="t" size="small" type="danger" effect="plain" style="margin-right:3px;font-size:10px">{{ t }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="建议" min-width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="(row.suggestion||'').includes('风险') ? 'danger' : (row.suggestion||'').includes('关注') ? 'warning' : 'info'">
                  {{ row.suggestion || '关注' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!arr(rpt.stock_pool).length" description="暂无选股池" :image-size="50" />
        </div>

        <!-- 投资日历（未来45天 解禁 / 分红除权） -->
        <div class="card mt8">
          <div class="flex between" style="align-items:center">
            <span class="fs14 bold">投资日历 <span class="fs12" style="color:#7d8390">（未来45天 解禁 / 分红除权）</span></span>
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
        <div v-if="arr(rpt.agent_reviews).length" class="card mt8">
          <div class="fs14 bold">AI 复盘（{{ arr(rpt.agent_reviews).length }} 个 Agent）</div>
          <el-row :gutter="10" class="mt8">
            <el-col v-for="(rv, at) in rpt.agent_reviews" :key="at" :xs="24" :sm="8">
              <div class="card" style="background:#1d2229">
                <el-tag size="small" :type="tagType(at)">{{ at }}</el-tag>
                <div class="fs12 mt8" style="line-height:1.9;white-space:pre-wrap">{{ rv.summary || rv.raw_output || '(' + JSON.stringify(rv).slice(0, 400) + ')' }}</div>
              </div>
            </el-col>
          </el-row>
        </div>
      </template>

      <el-empty v-else :description="(status === 'empty' && report?.message) || '暂无复盘报告，点击「生成复盘」手动触发（默认交易日 18:00 自动生成）'" />

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
import HQChartKline from '../components/HQChartKline.vue'
import { replayApi, marketApi, tradeApi } from '../api'
import { useSymbolStore } from '../stores/symbol'
import * as echarts from 'echarts'

const router = useRouter()
const symbolStore = useSymbolStore()
const loading = ref(false)
const triggering = ref(false)
const report = ref(null)
const triggerDate = ref('')
const viewDate = ref('')
const historyDates = ref([])
const mdDialog = ref(false)
const calendar = ref({ date: '', unlocks: [], dividends: [] })
const calLoading = ref(false)
const seats = ref([])
const trendData = ref([])
const trendEl = ref(null)
let trendChart = null
const arr = (v) => (Array.isArray(v) ? v : [])

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
  return keys.length ? Math.max(...keys.map(Number)) : 0
})

const sentimentScore = computed(() => {
  const m = rpt.value?.market_summary
  const up = Number(m?.distribution?.up_count || 0)
  const down = Number(m?.distribution?.down_count || 0)
  const lc = Number(rpt.value?.limit_up_count || 0)
  const base = up + down
  if (!base) return 50
  return Math.round(30 + (up / base) * 40 + Math.min(lc, 30) * 1)
})

function tagType(at) {
  return at === 'research' ? 'primary' : at === 'short_term' ? 'danger' : 'success'
}
function arr1(v) { return Array.isArray(v) ? v : [] }
function fmtBig(v) {
  if (v == null) return '-'
  const n = Number(v)
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}

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

const viewDay = computed(() => viewDate.value || rpt.value?.date || '')
const myTradesOfDay = computed(() =>
  myTrades.value.filter((t) => (t.trade_date || t.date || '').slice(0, 10) === viewDay.value))

function fmtAmount(v) {
  return v == null ? '-' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

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
    })).filter((x) => x.dt).slice(-130)
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
    const dates = [...new Set((Array.isArray(rows) ? rows : []).map((r) => r.date || '').filter(Boolean))].slice(-7)
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
    const resp = await replayApi.trigger({ date: triggerDate.value || undefined })
    await loadHistory()
    if (resp?.status === 'success' && resp?.date) await viewReport(resp.date)
    else await load()
  } finally {
    triggering.value = false
  }
}

function renderCharts() {
  if (!rpt.value) return
  renderDist()
  renderSector()
  renderLadder()
  renderTrend()
}

function renderTrend() {
  if (!trendEl.value || !trendData.value.length) return
  if (!trendChart) trendChart = echarts.init(trendEl.value)
  const dates = trendData.value.map(d => d.date.slice(5))
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
      { name: '涨停数', type: 'bar', barWidth: 16, yAxisIndex: 0, data: trendData.value.map(d => d.limit_up), itemStyle: { color: '#ef232a', borderRadius: [3, 3, 0, 0] } },
      { name: '跌停数', type: 'bar', barWidth: 16, yAxisIndex: 0, data: trendData.value.map(d => d.limit_down), itemStyle: { color: '#14b143', borderRadius: [3, 3, 0, 0] } },
      { name: '连板率', type: 'line', yAxisIndex: 1, data: trendData.value.map(d => d.consecutive_rate), smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#f7b32b', width: 2 }, itemStyle: { color: '#f7b32b' } },
      { name: '断板率', type: 'line', yAxisIndex: 1, data: trendData.value.map(d => d.broken_rate), smooth: true, symbol: 'diamond', symbolSize: 6, lineStyle: { color: '#409eff', width: 2, type: 'dashed' }, itemStyle: { color: '#409eff' } },
    ]
  }, true)
}

function renderDist() {
  if (!distEl.value) return
  const m = rpt.value?.market_summary?.distribution || {}
  const up = Number(m.up_count || 0)
  const down = Number(m.down_count || 0)
  if (!distChart) distChart = echarts.init(distEl.value)
  const total = up + down || 1
  distChart.setOption({
    backgroundColor: 'transparent',
    series: [{
      type: 'pie', radius: ['52%', '78%'], center: ['38%', '55%'],
      label: { color: '#c8ccd4', fontSize: 11 },
      data: [
        { value: up, name: '上涨 ' + up, itemStyle: { color: '#ef232a' } },
        { value: down, name: '下跌 ' + down, itemStyle: { color: '#14b143' } },
      ],
      labelLine: { lineStyle: { color: '#4d5461' } },
    }],
    legend: { orient: 'vertical', right: 8, top: 'center', textStyle: { color: '#c8ccd4', fontSize: 12 } },
    tooltip: { trigger: 'item' },
  }, true)
}

function renderSector() {
  if (!sectorEl.value) return
  const rows = [...arr1(rpt.value?.sector_flow)].sort((a, b) => Math.abs(b.net_inflow || 0) - Math.abs(a.net_inflow || 0)).slice(0, 10)
  if (!rows.length) return
  if (!sectorChart) sectorChart = echarts.init(sectorEl.value)
  const names = rows.map((r) => r.sector_name || r.name || '').reverse()
  const vals = rows.map((r) => (r.net_inflow || 0) / 1e8).reverse()
  sectorChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: '#7d8390', fontSize: 10, formatter: (v) => v.toFixed(1) + '亿' }, splitLine: { lineStyle: { color: '#2c3240' } } },
    yAxis: { type: 'category', data: names, axisLabel: { color: '#c8ccd4', fontSize: 10 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: vals, barWidth: '55%',
      itemStyle: { color: (p) => (vals[p.dataIndex] >= 0 ? '#ef232a' : '#14b143'), borderRadius: 2 },
      label: { show: true, position: 'right', color: '#c8ccd4', fontSize: 10, formatter: (p) => p.value.toFixed(1) + '亿' },
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
  triggerDate.value = dateStr(0)
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
.page { }
.kpi-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: 10px; }
.kpi-card {
  background: #171a21; border: 1px solid #2a2f3a; border-radius: 6px; padding: 10px 12px;
  text-align: center;
}
.kpi-card.accent { background: linear-gradient(135deg, #2a1c10, #3a2813); border-color: #f7b32b55; }
.kpi-label { font-size: 12px; color: #8b93a1; }
.kpi-val { font-size: 22px; font-weight: 700; line-height: 1.4; font-family: Consolas, 'Microsoft YaHei', monospace; }
.kpi-unit { font-size: 11px; color: #8b93a1; font-weight: 400; margin-left: 2px; }
.up { color: #ef232a; }
.down { color: #14b143; }
.mono { font-family: Consolas, monospace; }
.card {
  background: #1c2028; border: 1px solid #2a2f3a; border-radius: 8px;
  padding: 12px; color: #d8dce6;
}
.mt8 { margin-top: 8px; }
.mt4 { margin-top: 4px; }
.mr8 { margin-right: 8px; }
.fs12 { font-size: 12px; }
.fs14 { font-size: 14px; }
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
:deep(.el-table) { background: transparent; color: #d8dce6; }
:deep(.el-table tr), :deep(.el-table th.el-table__cell) { background: transparent; }
:deep(.el-table th.el-table__cell) { color: #8b93a1; }
:deep(.el-table--border, .el-table--group) { border-color: #2a2f3a; }
:deep(.el-table td.el-table__cell), :deep(.el-table th.el-table__cell.is-leaf) { border-bottom: 1px solid #2a2f3a; }
:deep(.el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell) { background: #232936; }
:deep(.el-link) { color: #ef6c6d; }

/* H5 移动端适配 */
@media (max-width: 820px) {
  .page { padding: 8px; }
  .card { padding: 10px; }
  .split-grid { grid-template-columns: 1fr; }
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 480px) {
  .card { padding: 8px; }
  .kpi-val { font-size: 18px; }
  .kpi-grid { grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .seat-row { flex-wrap: wrap; }
}
</style>
