<template>
  <MainLayout>
    <div class="page">
      <PageHeader eyebrow="MARKET TERMINAL / A-SHARE" title="大盘看板" :subtitle="`${todayStr} · 行情 30 秒轮询 · 非交易时段展示最近可用快照`">
        <template #badge><el-tag size="small" type="info">盘中监测</el-tag></template>
        <template #actions>
          <el-button size="small" type="primary" :loading="loading" @click="load">刷新行情</el-button>
          <el-button size="small" type="warning" :loading="mktLoading" @click="analyzeMarket">AI 大盘分析</el-button>
        </template>
      </PageHeader>

      <section class="terminal-deck" aria-label="盘中作战台">
        <div class="market-pulse">
          <div class="deck-eyebrow">MARKET PULSE <span>{{ dataStaleness.label }}</span></div>
          <div class="pulse-stage" :title="emotion.basis">{{ emotion.label }}</div>
          <div class="pulse-note">{{ breadthState.label }} · 数据覆盖 {{ regime?.confidence == null ? '-' : Math.round(regime.confidence * 100) + '%' }}</div>
          <div class="pulse-counts">
            <div><span>上涨</span><strong class="up">{{ breadthState.upText }}</strong></div>
            <div><span>下跌</span><strong class="down">{{ breadthState.downText }}</strong></div>
            <div><span>涨停 / 跌停</span><strong>{{ distribution.total ? `${distribution.limit_up ?? '-'} / ${distribution.limit_down ?? '-'}` : '- / -' }}</strong></div>
          </div>
          <div v-if="distribution.total" class="breadth-meter" role="img" :aria-label="`上涨 ${breadthState.upText}，下跌 ${breadthState.downText}`">
            <span :style="{ width: marketUpShare + '%' }"></span>
          </div>
          <div class="pulse-footer"><span>成交 {{ distribution.total ? fmtMoney(distribution.amount) : '-' }}</span><el-link type="primary" :underline="false" @click="$router.push('/regime')">周期口径 →</el-link></div>
          <div class="pulse-source">宽度: 腾讯全市场快照 · 周期: 四分项规则 · 并非预测概率</div>
        </div>
        <div class="desk-index">
          <div class="desk-panel-head"><span>主要指数</span><span>点位 / 涨跌幅</span></div>
          <div v-for="mc in mainIdxDefs" :key="mc.code" class="desk-index-row">
            <div><b>{{ mc.name }}</b><small class="mono">{{ mc.code }}</small></div>
            <strong class="mono" :class="ixCls(mc.code)">{{ fmtPrice(ixOf(mc.code)?.price) }}</strong>
            <span class="mono" :class="ixCls(mc.code)">{{ candidatePct(ixOf(mc.code)?.change_pct) }}</span>
          </div>
          <div class="desk-inline-meta">连板高度 <b>{{ maxBoard || '-' }}</b> · 连板率 <b>{{ marketStats.consecutive_rate ?? '-' }}%</b></div>
          <div class="desk-inline-meta">指数涨跌不能替代全市场宽度判断</div>
        </div>
        <div class="desk-sector">
          <div class="desk-panel-head"><span>资金分支</span><span>东方财富 f62 · 数据源分类</span></div>
          <button v-for="s in focusSectors" :key="s.symbol || s.sector_name" type="button" class="sector-lead" :disabled="!s.leader_symbol" @click="goStock(s.leader_symbol, s.leader)">
            <span><b>{{ s.sector_name }}</b><small>{{ s.leader || '无领涨股代码' }}</small></span>
            <span class="mono" :class="Number(s.change_pct) >= 0 ? 'up' : 'down'">{{ candidatePct(s.change_pct) }}</span>
            <span class="mono" :class="Number(s.net_inflow) >= 0 ? 'up' : 'down'">{{ s.net_inflow == null ? '-' : `${signed(s.net_inflow)}亿` }}</span>
          </button>
          <div v-if="!focusSectors.length" class="desk-empty">板块净额接口暂不可用，不能推断主线。</div>
          <div class="desk-inline-meta">仅展示行业流入榜样本；点击领涨股进入研究</div>
        </div>
      </section>

      <section class="opportunity-board" aria-label="盘中异动观察">
        <div class="board-head"><div><div class="deck-eyebrow">OPPORTUNITY TAPE / OBSERVATIONS</div><h2>盘中异动观察</h2><p>榜单观察，不自动生成买入指令。筛选板块只识别已知领涨股。</p></div><span class="board-count mono">{{ candItems.length }} <small>/ {{ candPool.length }} 只</small></span></div>
        <div class="board-controls">
          <el-radio-group v-model="candSource" size="small" aria-label="榜单类型"><el-radio-button value="hot">人气</el-radio-button><el-radio-button value="rise">急拉</el-radio-button><el-radio-button value="fall">急跌</el-radio-button></el-radio-group>
          <el-checkbox v-model="candNoST" size="small">排除 ST</el-checkbox><el-checkbox v-model="candNoMonitored" size="small">排除监控</el-checkbox><el-checkbox v-model="candUpOnly" size="small">仅收红</el-checkbox>
          <el-select v-model="candSector" size="small" clearable placeholder="仅板块领涨股" class="board-sector"><el-option v-for="s in sectorOptions" :key="s.value" :value="s.value" :label="s.label" /></el-select>
        </div>
        <div class="board-table-wrap"><table class="board-table"><thead><tr><th>序 / 标的</th><th>现价</th><th>涨跌</th><th>涨速 / 热度</th><th>量比 / 换手</th><th>入选依据</th></tr></thead><tbody>
          <tr v-for="c in candItems" :key="c.symbol" tabindex="0" role="link" :aria-label="`查看 ${c.name} 个股详情`" @click="goStock(c.symbol, c.name)" @keydown.enter="goStock(c.symbol, c.name)" @keydown.space.prevent="goStock(c.symbol, c.name)">
            <td><b class="mono board-rank">{{ String(c.rank).padStart(2, '0') }}</b><span class="board-stock"><strong>{{ c.name }}</strong><small class="mono">{{ c.symbol }}</small></span></td><td class="mono">{{ c.price ?? '-' }}</td><td class="mono" :class="Number(c.change_pct) >= 0 ? 'up' : 'down'">{{ candidatePct(c.change_pct) }}</td><td class="mono">{{ candSource === 'hot' ? `热度 ${c.heat ?? '-'}` : `涨速 ${c.speed ?? '-'}%/分` }}</td><td class="mono">{{ c.lb ?? '-' }} / {{ c.hsl == null ? '-' : `${c.hsl}%` }}</td><td class="board-reason">{{ c.why }}</td>
          </tr>
        </tbody></table><div v-if="!candItems.length" class="desk-empty">{{ candEmptyText }}；可调整筛选或稍后刷新数据。</div></div>
        <div class="board-foot">榜单源: 人气或分钟涨速，板块只用于额外标注 · <el-link type="primary" :underline="false" @click="goReplay">看盘后复盘 →</el-link></div>
      </section>

      <!-- 三大指数整行展示：每个面板独立周期（分时/日K/60/30/15/5分），分时与K线均带成交量 -->
      <nav class="desk-nav" aria-label="看盘工作区">
        <button type="button" @click="scrollToDesk('market-indices')">指数走势</button><button type="button" @click="scrollToDesk('market-breadth', 'sentiment')">市场宽度</button><button type="button" @click="scrollToDesk('market-movers', 'hot')">盘中异动</button><button type="button" @click="scrollToDesk('market-sectors', 'sectors')">板块强弱</button>
      </nav>
      <el-row id="market-indices" :gutter="10">
        <el-col v-for="mc in mainIdxDefs" :key="mc.code" :xs="24" :sm="8">
          <div class="card ix-panel">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <div>
                <span class="fs13 bold">{{ mc.name }}</span>
                <span class="fs12 ml4" style="color:#909399">{{ mc.code }}</span>
              </div>
              <el-select :model-value="indexPeriods[mc.code] || 'mf'" size="small" style="width:82px"
                @change="(v) => changeIndexPeriod(mc.code, v)">
                <el-option v-for="p in indexPeriodDefs" :key="p.val" :value="p.val" :label="p.label" />
              </el-select>
            </div>
            <div class="mt4">
              <div class="mono fs18 bold" :class="ixCls(mc.code)">
                {{ fmtPrice(ixOf(mc.code)?.price) }}
                <span class="fs13">({{ candidatePct(ixOf(mc.code)?.change_pct) }})</span>
              </div>
              <div class="fs12" style="color:#909399">成交 {{ fmtMoney(ixOf(mc.code)?.amount) }}</div>
            </div>
            <div class="chart-box mt4">
              <template v-if="(indexPeriods[mc.code] || 'mf') !== 'mf'">
                <KlineChart v-if="indexKlines[keyOf(mc.code)]?.length" :data="indexKlines[keyOf(mc.code)]" height="220px" />
                <div v-else class="fs12" style="color:#909399;text-align:center;height:220px;line-height:220px">K线加载中…</div>
              </template>
              <template v-else>
                <LineChart v-if="indexIntradays[mc.code]?.length" :data="indexIntradays[mc.code]" height="200px" :volume="true" />
                <div v-else class="fs12" style="color:#909399;text-align:center;height:200px;line-height:200px">分时加载中…</div>
              </template>
            </div>
          </div>
        </el-col>
      </el-row>

      <div class="ai-comment" v-if="indexComment">规则观察（仅指数涨跌）：{{ indexComment }}</div>

      <!-- 市场状态：左侧涨跌区间分布 + 右侧沪深两市大盘资金流向 -->
      <el-collapse id="market-breadth" v-model="openSections" class="funnel-collapse mt8">
      <el-collapse-item name="sentiment" title="市场宽度 · 涨跌分布与周期状态">
      <el-row :gutter="10">
        <el-col :xs="24" :sm="12">
          <div class="card" style="height:100%">
            <div class="flex gap" style="align-items:center;flex-wrap:wrap;margin-bottom:6px">
              <span class="fs14 bold">市场状态</span>
              <el-tag :type="emotion.tagType" size="small">{{ emotion.label }}</el-tag>
              <span class="fs12 up">上涨 {{ distribution.up_count ?? '-' }}</span>
              <span class="fs12 down">下跌 {{ distribution.down_count ?? '-' }}</span>
              <span class="fs12 flat">平盘 {{ distribution.flat_count ?? '-' }}</span>
              <el-divider direction="vertical" />
              <span class="fs12" style="color:#f56c6c">涨停 <b>{{ distribution.limit_up ?? '0' }}</b></span>
              <span class="fs12" style="color:#67c23a">跌停 <b>{{ distribution.limit_down ?? '0' }}</b></span>
              <span class="fs12" style="color:#909399">连板高度 <b>{{ maxBoard }}</b></span>
              <el-divider direction="vertical" />
              <span class="fs12" style="color:#606266">A股成交 <b class="mono">{{ fmtMoney(distribution.amount) }}</b></span>
            </div>
            <div v-if="regimeStageStrip.length" class="regime-mini mt4" title="近10日周期阶段评分（regime）">
              <span class="fs11" style="color:#909399;margin-right:6px">阶段</span>
              <el-tag
                v-for="(r, i) in regimeStageStrip" :key="i"
                size="small" effect="plain"
                :type="r.score >= 65 ? 'danger' : r.score <= 25 ? 'info' : 'warning'"
                :title="`${r.date} · ${r.label} · ${r.score}`"
                style="margin-right:4px"
              >{{ r.label }} {{ r.score }}</el-tag>
              <el-link type="primary" :underline="false" class="fs11" @click="$router.push('/regime')">详情</el-link>
            </div>
            <div class="flex gap mt8" style="flex-wrap:wrap">
              <div class="stat-item">
                <div class="stat-value" :class="marketStats.consecutive_rate > 30 ? 'danger' : ''">{{ marketStats.consecutive_rate ?? '-' }}%</div>
                  <div class="stat-label">连板率</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ marketStats.consecutive_count ?? '-' }}家</div>
                <div class="stat-label">连板股</div>
              </div>
              <div class="stat-item">
                 <div class="stat-value" :class="marketStats.limit_ratio > 3 ? 'profit' : marketStats.limit_ratio != null && marketStats.limit_ratio < 1 ? 'danger' : ''">{{ marketStats.limit_ratio ?? (distribution.total && distribution.limit_up > 0 && distribution.limit_down === 0 ? '∞' : '-') }}</div>
                <div class="stat-label" title="涨停家数 ÷ 跌停家数">涨跌停比</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ marketStats.up_ratio ?? '-' }}%</div>
                <div class="stat-label" title="上涨家数 ÷ 全市场统计家数">上涨占比</div>
              </div>
            </div>
            <!-- 涨跌区间分布柱状图 -->
            <div class="mt4">
              <div class="fs12 mb8" style="color:#909399">涨跌区间分布（家数）</div>
              <div class="dist-bars" v-if="distBuckets.length">
                <div v-for="(b, i) in distBuckets" :key="i" class="dist-col" :title="b.label + '：' + b.count + ' 家'">
                  <span class="dist-num mono" :class="b.cls">{{ b.count }}</span>
                  <div class="dist-bar" :style="{ height: b.h + 'px', background: b.color }" />
                  <span class="dist-label">{{ b.label }}</span>
                </div>
              </div>
              <div v-else class="fs12" style="color:#c0c4cc">暂无分布数据</div>
            </div>
            <div class="ai-comment" v-if="stateComment">💡 {{ stateComment }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="card" style="height:100%">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">沪深两市大盘资金流向 <span class="fs12" style="color:#909399">{{ marketFlow.date }}</span></span>
              <el-radio-group v-model="flowViewMode" size="small">
                <el-radio-button value="daily">日级</el-radio-button>
                <el-radio-button value="intraday">分时</el-radio-button>
              </el-radio-group>
            </div>
            <div v-if="flowViewMode === 'intraday'" class="chart-box mt4">
              <div ref="flowIntradayChartEl" class="flow-intraday-chart"></div>
              <div v-if="!mfChartData.length" class="fs12" style="color:#909399;text-align:center;height:235px;line-height:235px">分时资金流向加载中…</div>
            </div>
            <div v-else class="chart-box mt4">
              <div v-if="mfDailyChartData.length" class="flow-daily-chart">
                <div v-for="(item, i) in mfDailyChartData" :key="i" class="flow-daily-row">
                  <span class="fs11" style="color:#606266;width:36px;flex-shrink:0">{{ item.date }}</span>
                  <div class="flow-daily-bar-wrap">
                    <div class="flow-daily-bar" :style="{ width: item.barPct + '%', background: item.main_net >= 0 ? '#ef232a' : '#14b143' }"></div>
                  </div>
                  <span class="mono fs11" :class="item.main_net >= 0 ? 'up' : 'down'" style="width:60px;text-align:right;flex-shrink:0">{{ signed(item.main_net) }}亿</span>
                </div>
              </div>
              <div v-else class="fs12" style="color:#909399;text-align:center;height:235px;line-height:235px">日级资金流向加载中…</div>
            </div>
            <div class="ai-comment" v-if="flowComment">💡 {{ flowComment }}</div>
          </div>
        </el-col>
      </el-row>
      </el-collapse-item>
      <el-collapse-item id="market-movers" name="hot" title="盘中异动 · 人气与涨速">

      <!-- 实时股价异动：快速拉升 / 快速下挫（与人气股票TOP10同风格） -->
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">实时股价异动 <span class="fs12" style="color:#909399">（涨速榜 · 最近数分钟急拉 / 急跌）</span></span>
              <span class="fs12" style="color:#909399">点击进入个股详情</span>
            </div>
            <div class="movers-grid mt8">
              <div class="movers-col">
                <div class="movers-title" style="color:#ef232a">🚀 快速拉升 <span class="fs11" style="color:#909399">TOP{{ movers.rise.length }}</span></div>
                <div v-for="(r, i) in movers.rise" :key="r.symbol" class="hot-card" @click="goStock(r.symbol, r.name)">
                  <div class="flex between" style="align-items:center;gap:4px">
                    <span class="fs13 bold">{{ i + 1 }}. {{ r.name }}</span>
                    <el-tag size="small" type="danger">涨速 +{{ r.speed }}%/分</el-tag>
                  </div>
                  <div class="mono fs15" style="color:#303133">
                    {{ r.price }}
                    <span class="fs12" :class="Number(r.change_pct) >= 0 ? 'up' : 'down'">{{ Number(r.change_pct) >= 0 ? '+' : '' }}{{ r.change_pct }}%</span>
                  </div>
                  <div class="fs11" style="color:#909399">量比 <b>{{ r.lb }}</b> · 换手 {{ r.hsl }}% · 成交 {{ fmtMoney(r.turnover * 1e4) }}</div>
                </div>
                <el-empty v-if="!movers.rise.length" description="暂无急拉标的" :image-size="40" />
              </div>
              <div class="movers-col">
                <div class="movers-title" style="color:#14b143">⚡ 快速下挫 <span class="fs11" style="color:#909399">TOP{{ movers.fall.length }}</span></div>
                <div v-for="(r, i) in movers.fall" :key="r.symbol" class="hot-card" @click="goStock(r.symbol, r.name)">
                  <div class="flex between" style="align-items:center;gap:4px">
                    <span class="fs13 bold">{{ i + 1 }}. {{ r.name }}</span>
                    <el-tag size="small" type="success">跌速 {{ r.speed }}%/分</el-tag>
                  </div>
                  <div class="mono fs15" style="color:#303133">
                    {{ r.price }}
                    <span class="fs12" :class="Number(r.change_pct) >= 0 ? 'up' : 'down'">{{ Number(r.change_pct) >= 0 ? '+' : '' }}{{ r.change_pct }}%</span>
                  </div>
                  <div class="fs11" style="color:#909399">量比 <b>{{ r.lb }}</b> · 换手 {{ r.hsl }}% · 成交 {{ fmtMoney(r.turnover * 1e4) }}</div>
                </div>
                <el-empty v-if="!movers.fall.length" description="暂无急跌标的" :image-size="40" />
              </div>
            </div>
            <div class="ai-comment" v-if="moversComment">💡 {{ moversComment }}</div>
          </div>
        </el-col>
      </el-row>
      </el-collapse-item>
      </el-collapse>

      <!-- 板块监控：自选板块ETF + 概念/行业实时行情 -->
      <el-collapse v-model="openSections" class="funnel-collapse mt8">
      <el-collapse-item id="market-sectors" name="sectors" title="板块强弱 · 领涨观察">
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">板块监控</span>
              <div class="flex gap" style="align-items:center">
                <el-radio-group v-model="sectorTabMode" size="small">
                  <el-radio-button value="monitor">实时行情</el-radio-button>
                  <el-radio-button value="rotation">板块轮动</el-radio-button>
                </el-radio-group>
                <span v-if="sectorTabMode === 'monitor'" class="fs12" style="color:#909399">点击板块查看分时</span>
                <el-button size="small" :loading="sectorLoading" @click="sectorTabMode === 'monitor' ? loadSectorMonitor() : loadSectorSpeed()">刷新</el-button>
              </div>
            </div>
            <template v-if="sectorTabMode === 'monitor'">
              <el-radio-group v-model="sectorKind" size="small" class="mt8">
                <el-radio-button value="all">全部</el-radio-button>
                <el-radio-button value="行业">行业</el-radio-button>
                <el-radio-button value="概念">概念</el-radio-button>
              </el-radio-group>
            </template>
            <!-- 板块轮动视图 -->
            <template v-if="sectorTabMode === 'rotation'">
              <div v-if="sectorSpeedList.length" class="mt8">
                 <div class="fs12 mb8" style="color:#909399">新浪 FLJK 板块涨幅排序 · 成交额不是净流入</div>
                <div v-for="(s, i) in sectorSpeedList" :key="s.sector_name" class="speed-row">
                  <span class="speed-rank mono" :class="i < 3 ? 'speed-top' : ''">{{ i + 1 }}</span>
                  <span class="speed-name">{{ s.sector_name }}</span>
                  <div class="speed-bar-wrap">
                    <div class="speed-bar" :style="{ width: s.barPct + '%', background: s.change_pct >= 0 ? '#ef232a' : '#14b143' }"></div>
                  </div>
                  <span class="mono fs12 speed-pct" :class="s.change_pct >= 0 ? 'up' : 'down'">{{ s.change_pct >= 0 ? '+' : '' }}{{ (s.change_pct || 0).toFixed(2) }}%</span>
                   <span class="fs11 speed-flow" style="color:var(--c-text-2)">{{ s.turnover == null ? '-' : `成交 ${fmtMoney(s.turnover)}` }}</span>
                  <span v-if="s.leader" class="fs11 speed-leader">
                    <el-link v-if="s.leader_symbol" type="primary" :underline="false" style="font-size:11px" @click="goStock(s.leader_symbol, s.leader)">{{ s.leader }}</el-link>
                    <span v-else style="color:#909399">{{ s.leader }}</span>
                  </span>
                  <span v-if="s.count" class="fs11" style="color:#c0c4cc;width:30px;text-align:right">{{ s.count }}只</span>
                </div>
              </div>
              <el-empty v-else class="mt8" description="暂无板块轮动数据" :image-size="40" />
            </template>
            <!-- 实时行情视图 -->
            <template v-if="sectorTabMode === 'monitor'">
              <div class="sector-grid mt8">
                <div v-for="s in filteredSectors" :key="s.symbol"
                  class="sector-card" :class="{ active: selectedSector?.symbol === s.symbol }"
                  @click="selectSector(s)">
                  <div class="fs12 bold">
                    <span v-if="s.kind && !s.is_etf" class="kind-badge" :class="'kind-' + (s.kind === '行业' ? 'industry' : 'concept')">{{ s.kind }}</span>
                    {{ s.sector }}
                  </div>
                  <div class="mono fs13" :class="Number(s.change_pct) >= 0 ? 'up' : 'down'">
                    {{ Number(s.change_pct) >= 0 ? '+' : '' }}{{ (s.change_pct || 0).toFixed(2) }}%
                  </div>
                  <div class="fs11" style="color:#909399">{{ fmtMoney(s.amount) }}</div>
                  <div v-if="s.is_etf === false" class="fs11" style="color:#c0c4cc">
                    领涨 <b style="color:#606266">{{ s.leader_name || '-' }}</b>
                  </div>
                </div>
                <el-empty v-if="!sectorList.length" description="暂无数据" :image-size="40" />
              </div>
              <div class="ai-comment" v-if="sectorComment">💡 板块点评：{{ sectorComment }}</div>
              <!-- 选中板块详情：ETF 有分时图，概念/行业展示实时行情+领涨股 -->
              <div v-if="selectedSector" class="mt8" style="border-top:1px solid #f0f0f0;padding-top:8px">
                <div class="flex gap" style="align-items:center;flex-wrap:wrap">
                  <span class="fs13 bold">{{ selectedSector.name }}</span>
                  <span class="mono fs13" :class="Number(selectedSector.change_pct) >= 0 ? 'up' : 'down'">
                    {{ selectedSector.price || '-' }} ({{ Number(selectedSector.change_pct) >= 0 ? '+' : '' }}{{ (selectedSector.change_pct || 0).toFixed(2) }}%)
                  </span>
                  <span class="fs12" style="color:#909399">{{ fmtMoney(selectedSector.amount) }}</span>
                </div>
                <template v-if="selectedSector.is_etf === false">
                  <div class="fs12 mt4" style="line-height:1.8">
                    成分股 <b>{{ selectedSector.count || '-' }}</b> · 领涨股
                    <el-link v-if="selectedSector.leader_symbol" type="primary" :underline="false" style="font-size:12px"
                      @click="goStock(selectedSector.leader_symbol, selectedSector.leader_name)">
                      {{ selectedSector.leader_name }}
                    </el-link>
                    <span v-else>{{ selectedSector.leader_name || '-' }}</span>
                    <span class="fs11" style="color:#c0c4cc">（概念板块暂无 ETF 分时，展示板块实时行情）</span>
                  </div>
                </template>
                <template v-else>
                  <LineChart v-if="sectorIntraday.length" :data="sectorIntraday" height="180px" :pre-close="sectorPreClose" class="mt4" />
                  <div v-else class="fs12" style="color:#909399;text-align:center;height:60px;line-height:60px">分时数据加载中…</div>
                </template>
              </div>
            </template>
          </div>
        </el-col>
      </el-row>

      </el-collapse-item>
      <el-collapse-item name="fundflow" title="💰 资金流向">
      <el-row :gutter="10" class="mt8">
        <el-col :xs="24" :sm="12">
          <div class="card col-card flow-card">
            <div class="fs14 bold">行业资金流 <span class="fs12" style="color:#909399">（东方财富板块主力净流入，单位亿元）</span></div>
            <div class="split-grid mt8">
              <div>
                <div class="fs12 bold" style="color:#f56c6c">流入 TOP5</div>
                <div v-for="(r, i) in flowRank.industries.in" :key="'ii' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12" :class="r.net_inflow >= 0 ? 'up' : 'down'">{{ signed(r.net_inflow) }}亿</span>
                  <span class="mono fs12" :class="r.change_pct >= 0 ? 'up' : 'down'">{{ signed(r.change_pct) }}%</span>
                </div>
                <el-empty v-if="!flowRank.industries.in.length" description="暂无" :image-size="34" />
              </div>
              <div>
                <div class="fs12 bold" style="color:#67c23a">流出 TOP5</div>
                <div v-for="(r, i) in flowRank.industries.out" :key="'io' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12" :class="r.net_inflow >= 0 ? 'up' : 'down'">{{ signed(r.net_inflow) }}亿</span>
                  <span class="mono fs12" :class="r.change_pct >= 0 ? 'up' : 'down'">{{ signed(r.change_pct) }}%</span>
                </div>
                <el-empty v-if="!flowRank.industries.out.length" description="暂无" :image-size="34" />
              </div>
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="card col-card flow-card">
            <div class="fs14 bold">概念资金流 <span class="fs12" style="color:#909399">（东方财富板块主力净流入，单位亿元）</span></div>
            <div class="split-grid mt8">
              <div>
                <div class="fs12 bold" style="color:#f56c6c">流入 TOP5</div>
                <div v-for="(r, i) in flowRank.concepts.in" :key="'ci' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12" :class="r.net_inflow >= 0 ? 'up' : 'down'">{{ signed(r.net_inflow) }}亿</span>
                  <span class="mono fs12" :class="r.change_pct >= 0 ? 'up' : 'down'">{{ signed(r.change_pct) }}%</span>
                </div>
                <el-empty v-if="!flowRank.concepts.in.length" description="暂无" :image-size="34" />
              </div>
              <div>
                <div class="fs12 bold" style="color:#67c23a">流出 TOP5</div>
                <div v-for="(r, i) in flowRank.concepts.out" :key="'co' + i" class="flow-row">
                  <span class="fs12">{{ i + 1 }}.{{ r.name }}
                    <el-link v-if="r.leader_symbol" type="primary" :underline="false" style="font-size:11px;margin-left:2px"
                      @click.stop="goStock(r.leader_symbol, r.leader)">领涨 {{ r.leader }}</el-link>
                    <i v-else class="fs11" style="color:#b0b3b8;font-style:normal">领涨 {{ r.leader }}</i>
                  </span>
                  <span class="mono fs12" :class="r.net_inflow >= 0 ? 'up' : 'down'">{{ signed(r.net_inflow) }}亿</span>
                  <span class="mono fs12" :class="r.change_pct >= 0 ? 'up' : 'down'">{{ signed(r.change_pct) }}%</span>
                </div>
                <el-empty v-if="!flowRank.concepts.out.length" description="暂无" :image-size="34" />
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      </el-collapse-item>
      <el-collapse-item name="calendar" title="📅 投资日历 · 监管异动">
      <el-row :gutter="10" class="mt8">
        <el-col :xs="24" :sm="12">
          <div class="card col-card">
            <div class="flex between" style="align-items:center">
              <span class="fs14 bold">投资日历 <span class="fs12" style="color:#909399">（未来45天 解禁 / 分红除权）</span></span>
              <el-button size="small" :loading="calLoading" @click="loadCalendar">刷新</el-button>
            </div>
            <div class="cal-scroll mt8">
              <div class="fs12 bold" style="color:#f56c6c;margin:2px 0">🛡 限售解禁 <span class="fs11" style="color:#909399">（{{ calendar.unlocks.length }}笔，按解禁市值排序）</span></div>
              <div v-for="(u, i) in topUnlocks" :key="'u' + i" class="cal-row">
                <span class="cal-date">{{ (u.date || '').slice(5) }}</span>
                <el-link v-if="u.symbol" class="cal-name" type="danger" :underline="false" @click="goStock(u.symbol, u.name)">{{ u.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ u.name }}</span>
                <span class="cal-val mono fs12" style="color:#f56c6c">{{ u.market_cap_yi }}亿</span>
                <span class="cal-sub">{{ u.type }}</span>
              </div>
              <el-empty v-if="!calendar.unlocks.length" description="未来45天无解禁" :image-size="30" />
              <div class="fs12 bold" style="color:#67c23a;margin:6px 0 2px">💰 分红除权 <span class="fs11" style="color:#909399">（{{ calendar.dividends.length }}笔）</span></div>
              <div v-for="(d, i) in topDividends" :key="'d' + i" class="cal-row">
                <span class="cal-date">{{ (d.date || '').slice(5) }}</span>
                <el-link v-if="d.symbol" class="cal-name" type="success" :underline="false" @click="goStock(d.symbol, d.name)">{{ d.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ d.name }}</span>
                <span class="cal-val mono fs12" style="color:#67c23a">{{ (d.record_date || '').slice(5) }}除权</span>
                <span class="cal-sub">{{ d.plan }}</span>
              </div>
              <el-empty v-if="!calendar.dividends.length" description="未来45天无分红除权" :image-size="30" />
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="card col-card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">监管异动 <span class="fs12" style="color:#909399">（重点监控 / 严重异常波动）</span></span>
              <el-button size="small" :loading="regLoading" @click="loadRegulatory">刷新</el-button>
            </div>
            <div class="cal-scroll mt8">
              <div class="fs12 bold" style="color:#ef232a;margin:2px 0">⚠ 重点监控 <span class="fs11" style="color:#909399">（{{ monitor.length }}只 在监控窗口内）</span></div>
              <div v-for="(m, i) in monitor" :key="'m' + i" class="cal-row">
                <span class="cal-date">剩{{ m.days_left }}天</span>
                <el-link v-if="m.symbol" class="cal-name" type="danger" :underline="false" @click="goStock(m.symbol, m.name)">{{ m.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ m.name }}</span>
                <span class="cal-val mono fs12" style="color:#909399">{{ m.code }}</span>
                <span class="cal-sub">{{ m.market }}</span>
              </div>
              <el-empty v-if="!monitor.length" description="当前无重点监控标的" :image-size="30" />
              <div class="fs12 bold" style="color:#ef232a;margin:6px 0 2px">🔥 严重异常波动 <span class="fs11" style="color:#909399">（{{ anomalyDateTxt }} {{ anomalyItems.length }}条）</span></div>
              <div v-for="(a, i) in anomalyItems" :key="'a' + i" class="cal-row">
                <el-link v-if="a.symbol" class="cal-name" type="danger" :underline="false" @click="goStock(a.symbol, a.name)">{{ a.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ a.name }}</span>
                <span class="cal-val mono fs12" :class="a.change_pct >= 0 ? 'up' : 'down'">{{ a.change_pct >= 0 ? '+' : '' }}{{ a.change_pct }}%</span>
                <span class="cal-sub">偏离{{ a.deviation }}% · {{ a.rule }}</span>
              </div>
              <el-empty v-if="!anomalyItems.length" description="当前无异常波动标的" :image-size="30" />
            </div>
          </div>
        </el-col>
      </el-row>

      </el-collapse-item>
      <el-collapse-item name="news" title="📰 消息 · ETF 资金流">
      <el-row :gutter="10" class="mt8">
        <el-col :xs="24" :sm="12">
          <div class="card col-card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">消息滚动 <span class="fs12" style="color:#909399">（平台新闻 + RSSHub 订阅推送）</span></span>
              <el-radio-group v-model="newsFilter" size="small">
                <el-radio-button value="">全部</el-radio-button>
                <el-radio-button value="1">重要</el-radio-button>
                <el-radio-button value="2">普通</el-radio-button>
                <el-radio-button value="3">一般</el-radio-button>
              </el-radio-group>
            </div>
            <el-scrollbar class="news-scroll">
              <div v-for="(n, i) in filteredNews" :key="i" class="news-item">
                <el-tag size="small" :type="impTag(n.importance)" style="flex-shrink:0">{{ impText(n.importance) }}</el-tag>
                <el-tag size="small" :type="n.src === 'RSS' ? 'success' : 'info'" effect="plain" style="flex-shrink:0">{{ n.category }}</el-tag>
                <a v-if="n.url" :href="n.url" target="_blank" rel="noopener" class="fs12 news-title">{{ n.title }}</a>
                <span v-else class="fs12 news-title">{{ n.title }}</span>
                <span class="fs12 news-time">{{ formatNewsTime(n.time) }}</span>
              </div>
              <el-empty v-if="!filteredNews.length" description="暂无消息" :image-size="50" />
            </el-scrollbar>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="card col-card">
            <div class="flex between" style="align-items:center">
               <span class="fs14 bold">ETF 资金流 <span class="fs12 mono" style="color:#909399">（现有榜单样本重排 · 截至 {{ etfFlowDate }}）</span></span>
              <el-radio-group v-model="etfDim" size="small">
                <el-radio-button value="net_1d">今日</el-radio-button>
                <el-radio-button value="net_5d">5日</el-radio-button>
                <el-radio-button value="net_20d">20日</el-radio-button>
              </el-radio-group>
            </div>
            <div class="split-grid mt8">
              <div>
                <div class="fs12 bold" style="color:#f56c6c">净流入 TOP5</div>
                <div v-for="(r, i) in etfIn" :key="'ei' + i" class="flow-row">
                  <span class="fs12">{{ r.name }}</span>
                  <span class="mono fs12" :class="r[etfDim] >= 0 ? 'up' : 'down'">{{ signed(r[etfDim]) }}亿</span>
                </div>
                <el-empty v-if="!etfIn.length" description="暂无" :image-size="34" />
              </div>
              <div>
                <div class="fs12 bold" style="color:#67c23a">净流出 TOP5</div>
                <div v-for="(r, i) in etfOut" :key="'eo' + i" class="flow-row">
                  <span class="fs12">{{ r.name }}</span>
                  <span class="mono fs12" :class="r[etfDim] >= 0 ? 'up' : 'down'">{{ signed(r[etfDim]) }}亿</span>
                </div>
                <el-empty v-if="!etfOut.length" description="暂无" :image-size="34" />
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      </el-collapse-item>
      </el-collapse>

      <!-- AI 大盘分析（内联显示，非弹框） -->
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card" v-if="mktSummary">
            <div class="flex between" style="align-items:center;margin-bottom:8px">
              <span class="fs14 bold">AI 大盘分析</span>
              <span class="fs12" style="color:#909399">{{ mktDate }}</span>
            </div>
            <div class="mkt-text">{{ mktSummary }}</div>
          </div>
        </el-col>
      </el-row>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import LineChart from '../components/LineChart.vue'
import KlineChart from '../components/KlineChart.vue'
import * as echarts from 'echarts'
import { marketApi, agentApi, rssApi } from '../api'
import { useSymbolStore } from '../stores/symbol'
import { formatNewsTime as _formatNewsTime, toEpochMs } from '../utils/time'
import { fmtPrice, fmtMoney } from '../utils/format'

const router = useRouter()
const symbolStore = useSymbolStore()
function goStock(symbol, name) {
  if (!symbol) return
  symbolStore.select(symbol, { name: name || symbol })
  router.push({ path: '/watchlist', query: { symbol, name: name || '' } })
}

const loading = ref(false)
const mktLoading = ref(false)
const mktSummary = ref('')
const mktDate = ref('')
const openSections = ref(loadPanelsState())
const indices = ref([])
const news = ref([])
const newsFilter = ref('')
const rssNews = ref([])
const marketFlow = ref({ date: '', intraday: [], daily: [] })
const mergedNews = computed(() => {
  const plat = (news.value || []).map((n) => ({
    title: stripHtml(n.title), url: n.url, importance: Number(n.importance) || 3,
    category: n.category || '财经', time: n.time || '', src: '平台'
  }))
  const rss = (rssNews.value || []).map((r) => ({
    title: stripHtml(r.title), url: r.link, importance: Number(r.importance) || 3,
    category: '订阅·' + (r.source_name || r.platform || 'RSS'), time: r.pub_time || '', src: 'RSS'
  }))
  return [...rss, ...plat]
})
const filteredNews = computed(() => {
  const cutoff = Date.now() - 3 * 24 * 3600 * 1000
  let recent = mergedNews.value.filter((n) => {
    const t = toEpochMs(n.time) ? toEpochMs(n.time) : 0
    return !t || t >= cutoff
  })
  if (newsFilter.value !== '') {
    const f = Number(newsFilter.value)
    recent = recent.filter((n) => Number(n.importance) === f)
  }
  return recent.slice().sort((a, b) => (toEpochMs(b.time) || 0) - (toEpochMs(a.time) || 0))
})
const mfSeries = [
  { name: '主力', key: 'main_net', color: '#ef232a', area: false },
  { name: '超大单', key: 'super_net', color: '#e6a23c', area: false },
  { name: '大单', key: 'large_net', color: '#f56c6c', area: false },
  { name: '中单', key: 'mid_net', color: '#67c23a', area: false },
  { name: '小单', key: 'small_net', color: '#909399', area: false }
]
const flowViewMode = ref('intraday')
const mfChartData = computed(() => {
  return Array.isArray(marketFlow.value.intraday) ? marketFlow.value.intraday : []
})
const mfDailyChartData = computed(() => {
  const daily = Array.isArray(marketFlow.value.daily) ? marketFlow.value.daily : []
  if (!daily.length) return []
  const maxAbs = Math.max(1, ...daily.map(d => Math.abs(d.main_net || 0)))
  return daily.map(d => ({
    date: (d.date || '').slice(5) || d.date || '',
    main_net: d.main_net || 0,
    barPct: Math.min(100, Math.round(Math.abs(d.main_net || 0) / maxAbs * 100))
  }))
})
const flowIntradayChartEl = ref(null)
let flowIntradayChart = null

function renderFlowIntradayChart() {
  if (!flowIntradayChartEl.value || !mfChartData.value.length) return
  if (flowIntradayChart) { flowIntradayChart.dispose(); flowIntradayChart = null }
  flowIntradayChart = echarts.init(flowIntradayChartEl.value)
  const data = mfChartData.value
  const times = data.map(d => d.time)
  const mainNet = data.map(d => d.main_net ?? null)
  const superLarge = data.map(d => (d.super_net || 0) + (d.large_net || 0))
  const mainColor = '#ef232a'
  flowIntradayChart.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      valueFormatter: v => v == null ? '-' : (v >= 0 ? '+' : '') + (v / 1e8).toFixed(2) + '亿'
    },
    legend: { top: 0, right: 10, textStyle: { fontSize: 11 } },
    grid: { left: 56, right: 16, top: 28, bottom: 24 },
    xAxis: { type: 'category', data: times, boundaryGap: false, axisLabel: { fontSize: 10 } },
    yAxis: {
      scale: true,
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { fontSize: 10, formatter: v => Math.abs(v) >= 1e8 ? (v / 1e8).toFixed(1) + '亿' : v }
    },
    series: [
      {
        name: '主力净流入',
        type: 'line',
        data: mainNet,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.8, color: mainColor },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(239,35,42,0.35)' },
            { offset: 1, color: 'rgba(239,35,42,0.03)' }
          ])
        }
      },
      {
        name: '超大单+大单',
        type: 'line',
        data: superLarge,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.4, color: '#e6a23c', type: 'dashed' }
      }
    ]
  })
}
watch(mfChartData, () => {
  if (flowViewMode.value === 'intraday') renderFlowIntradayChart()
})
watch(flowViewMode, (v) => {
  if (v === 'intraday') {
    nextTick(renderFlowIntradayChart)
  }
})
function stripHtml(s) {
  if (!s) return ''
  if (!/<[a-zA-Z]/.test(s)) return s
  const div = document.createElement('div')
  div.innerHTML = s
  return (div.textContent || div.innerText || '').replace(/\s+/g, ' ').trim()
}
function formatNewsTime(ts) {
  return _formatNewsTime(ts)
}
const ladder = ref({})
const distribution = ref({})
const marketStats = ref({})
const flowRank = ref({ industries: { in: [], out: [] }, concepts: { in: [], out: [] } })
const focusSectors = computed(() => (flowRank.value.industries?.in || []).slice(0, 5).map(s => ({ ...s, sector_name: s.name, symbol: s.code })))
const marketUpShare = computed(() => {
  const up = Number(distribution.value.up_count || 0)
  const down = Number(distribution.value.down_count || 0)
  return up + down ? Math.round(up / (up + down) * 100) : 0
})
const etfFlow = ref({ in_top: [], out_top: [], all: [] })
const etfDim = ref('net_1d')

const sectorList = ref([])
const sectorLoading = ref(false)
const selectedSector = ref(null)
const sectorIntraday = ref([])
const sectorPreClose = ref(0)
const sectorKind = ref('all')
const sectorTabMode = ref('monitor')
const sectorSpeedRaw = ref([])
const filteredSectors = computed(() => {
  let list = sectorList.value || []
  if (sectorKind.value !== 'all') {
    list = list.filter(s => s.kind === sectorKind.value || s.is_etf === true)
  }
  // ETF 排前面，其余按涨幅降序
  const etfs = list.filter(s => s.is_etf === true).sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0))
  const boards = list.filter(s => s.is_etf !== true).sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0))
  return [...etfs, ...boards]
})
const sectorSpeedList = computed(() => {
  const rows = sectorSpeedRaw.value || []
  if (!rows.length) return []
  const maxAbs = Math.max(1, ...rows.map(r => Math.abs(r.change_pct || 0)))
  return rows.map(r => ({
    ...r,
    barPct: Math.min(100, Math.round(Math.abs(r.change_pct || 0) / maxAbs * 100))
  }))
})
const hotStocks = ref([])

const calendar = ref({ date: '', unlocks: [], dividends: [] })
const calLoading = ref(false)
const monitor = ref([])
const anomaly = ref({ date: '', items: [], count: [] })
const regLoading = ref(false)
const topUnlocks = computed(() => [...(calendar.value.unlocks || [])]
  .sort((a, b) => b.market_cap_yi - a.market_cap_yi).slice(0, 6))
const topDividends = computed(() => [...(calendar.value.dividends || [])]
  .sort((a, b) => (a.date || '').localeCompare(b.date || '')).slice(0, 6))
const anomalyItems = computed(() => (anomaly.value.items || []).slice(0, 8))
const anomalyDateTxt = computed(() => {
  const dt = anomaly.value.date || ''
  return dt ? `${dt.slice(0, 4)}-${dt.slice(4, 6)}-${dt.slice(6)}` : ''
})

async function loadCalendar() {
  calLoading.value = true
  try { calendar.value = (await marketApi.investCalendar()) || { date: '', unlocks: [], dividends: [] } } catch { /* 保留旧数据 */ }
  calLoading.value = false
}

async function loadRegulatory() {
  regLoading.value = true
  try {
    const d = (await marketApi.regulatory()) || { monitor: [], anomaly: { date: '', items: [], count: [] } }
    monitor.value = d.monitor || []
    anomaly.value = d.anomaly || { date: '', items: [], count: [] }
  } catch { /* 保留旧数据 */ }
  regLoading.value = false
}

function hotColor(heat) {
  const n = Number(heat || 0)
  return n >= 80 ? '#ef232a' : n >= 60 ? '#f56c6c' : '#e6a23c'
}

async function loadHotStocks() {
  try {
    hotStocks.value = (await marketApi.hotStocks()) || []
    hotLoadedAt.value = Date.now()
  } catch { /* 保留旧数据 */ }
}

async function loadPriceMovers() {
  try {
    movers.value = (await marketApi.priceMovers()) || { rise: [], fall: [] }
    moversLoadedAt.value = Date.now()
  } catch { /* 保留旧数据 */ }
}

async function loadSectorMonitor() {
  sectorLoading.value = true
  try {
    sectorList.value = (await marketApi.sectorMonitor()) || []
  } catch { sectorList.value = [] }
  sectorLoading.value = false
}

async function loadSectorSpeed() {
  sectorLoading.value = true
  try {
    sectorSpeedRaw.value = (await marketApi.sectorSpeed()) || []
  } catch { sectorSpeedRaw.value = [] }
  sectorLoading.value = false
}

async function selectSector(s) {
  selectedSector.value = s
  sectorIntraday.value = []
  sectorPreClose.value = 0
  if (s.is_etf === false) return
  try {
    const data = (await marketApi.sectorMonitorIntraday(s.symbol)) || []
    sectorIntraday.value = data
    if (data.length) sectorPreClose.value = data[0].price || 0
  } catch { sectorIntraday.value = [] }
}

const indexPeriodDefs = [
  { val: 'mf', label: '分时' },
  { val: 'day', label: '日K' },
  { val: 'm60', label: '60分' },
  { val: 'm30', label: '30分' },
  { val: 'm15', label: '15分' },
  { val: 'm5', label: '5分' }
]
const indexPeriods = reactive({})
const indexIntradays = reactive({})
const indexKlines = reactive({})
const keyOf = (code) => `${code}:${indexPeriods[code] || 'mf'}`

const mainIdxDefs = [
  { code: 'SH000001', name: '上证指数' },
  { code: 'SZ399006', name: '创业板指' },
  { code: 'SH000688', name: '科创50' }
]

function ixOf(code) {
  return indices.value.find((ix) => ix.code === code)
}
function ixCls(code) {
  const pct = ixOf(code)?.change_pct ?? 0
  return Number(pct) >= 0 ? 'up' : 'down'
}
function signed(v) {
  const n = Number(v) || 0
  return (n > 0 ? '+' : n < 0 ? '-' : '') + Math.abs(n).toFixed(2)
}
const etfRows = computed(() => [...new Map([...(etfFlow.value.in_top || []), ...(etfFlow.value.out_top || [])]
  .map(r => [r.symbol || r.code || r.name, r])).values()])
const etfIn = computed(() => etfRows.value.filter(r => Number(r[etfDim.value]) > 0)
  .sort((a, b) => Number(b[etfDim.value]) - Number(a[etfDim.value])).slice(0, 5))
const etfOut = computed(() => etfRows.value.filter(r => Number(r[etfDim.value]) < 0)
  .sort((a, b) => Number(a[etfDim.value]) - Number(b[etfDim.value])).slice(0, 5))
const etfFlowDate = computed(() => (etfFlow.value.in_top || []).find((r) => r.flow_date)?.flow_date || '')
const maxBoard = computed(() => {
  const keys = Object.keys(ladder.value.ladder || {})
  const nums = keys.map(k => parseInt(k, 10)).filter(n => !isNaN(n))
  return nums.length ? Math.max(...nums) : 0
})

const sectorOptions = computed(() => (sectorList.value || [])
  .filter((s) => s && s.sector)
  .map((s) => ({ value: s.sector, label: s.sector })))

function candidatePct(v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
}

function sectorNameFor(symbol) {
  const sym = String(symbol || '').toUpperCase()
  const hit = (sectorList.value || []).find((s) => {
    const ls = String(s.leader_symbol || '').toUpperCase()
    return ls && ls === sym
  })
  return hit ? hit.sector : ''
}

const HOME_FILTERS_KEY = 'home_filters'
const HOME_PANELS_KEY = 'home_panels'

function isTradingHours() {
  const now = new Date()
  const h = now.getHours(), m = now.getMinutes()
  const t = h * 60 + m
  return (t >= 570 && t <= 900)
}

function loadFilterState() {
  try {
    const raw = localStorage.getItem(HOME_FILTERS_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch { return null }
}

function saveFilterState() {
  try {
    localStorage.setItem(HOME_FILTERS_KEY, JSON.stringify({
      candSource: candSource.value,
      candNoST: candNoST.value,
      candNoMonitored: candNoMonitored.value,
      candUpOnly: candUpOnly.value,
      candSector: candSector.value,
    }))
  } catch {}
}

function getDefaultPanels() {
  if (isTradingHours()) return ['sentiment', 'hot', 'sectors']
  return ['sentiment']
}

function loadPanelsState() {
  try {
    const raw = localStorage.getItem(HOME_PANELS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length) return parsed
    }
  } catch {}
  return getDefaultPanels()
}

function savePanelsState() {
  try {
    localStorage.setItem(HOME_PANELS_KEY, JSON.stringify(openSections.value))
  } catch {}
}
function openSection(name) {
  if (!openSections.value.includes(name)) openSections.value = [...openSections.value, name]
}
function scrollToDesk(id, section) {
  if (section) openSection(section)
  nextTick(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

const savedFilters = loadFilterState()
const candSource = ref(savedFilters?.candSource ?? 'hot')
const candNoST = ref(savedFilters?.candNoST ?? true)
const candNoMonitored = ref(savedFilters?.candNoMonitored ?? true)
const candUpOnly = ref(savedFilters?.candUpOnly ?? false)
const candSector = ref(savedFilters?.candSector ?? '')

const candPool = computed(() => {
  const src = candSource.value
  let rows = []
  if (src === 'hot') rows = hotStocks.value || []
  else if (src === 'rise') rows = (movers.value && movers.value.rise) || []
  else rows = (movers.value && movers.value.fall) || []
  const seen = new Set()
  const pool = []
  for (const r of rows) {
    if (!r || !r.symbol) continue
    const sym = String(r.symbol).toUpperCase()
    if (seen.has(sym)) continue
    seen.add(sym)
    const name = String(r.name || '')
    pool.push({
      symbol: sym,
      name,
      price: r.price,
      change_pct: r.change_pct,
      heat: r.heat ?? null,
      hsl: r.hsl,
      lb: r.lb,
      speed: r.speed ?? null,
      turnover: r.turnover,
      isSt: isStName(name),
      isMonitored: monitoredSymbols.value.has(sym),
      sector: sectorNameFor(sym)
    })
  }
  return pool
})

const candItems = computed(() => {
  let rows = candPool.value.filter((c) => {
    if (candNoST.value && c.isSt) return false
    if (candNoMonitored.value && c.isMonitored) return false
    if (candUpOnly.value && Number(c.change_pct) < 0) return false
    if (candSector.value && c.sector !== candSector.value) return false
    return true
  })
  rows.sort((a, b) => {
    if (candSource.value === 'hot') return (Number(b.heat) || 0) - (Number(a.heat) || 0)
    return (Number(b.speed) || 0) - (Number(a.speed) || 0)
  })
  rows = rows.slice(0, 12).map((c, idx) => {
    const tags = []
    const why = []
    if (candSource.value === 'rise') {
      tags.push('急拉')
      why.push(`涨速+${c.speed}%/分`)
    } else if (candSource.value === 'fall') {
      tags.push('急跌')
      why.push(`涨速${c.speed}%/分`)
    } else {
      tags.push('人气')
      why.push(`热度${c.heat ?? '-'}`)
    }
    if (c.sector) {
      tags.push(c.sector)
      why.push(`${c.sector}板块在监控列表`)
    }
    if (Number(c.hsl) >= 5) {
      tags.push('高换手')
      why.push(`换手${c.hsl}%`)
    }
    if (Number(c.lb) >= 2) {
      tags.push('放量')
      why.push(`量比${c.lb}`)
    }
    if (Number(c.change_pct) >= 9.8) why.push('涨幅逼近/达到涨停')
    if (!why.length) why.push('仅上榜该榜单')
    return { ...c, rank: idx + 1, tags, why: why.join(' · ') }
  })
  return rows
})

const candEmptyText = computed(() => {
  if (!candPool.value.length) {
    return candSource.value === 'hot' ? '人气榜暂无数据' : (candSource.value === 'rise' ? '暂无急拉标的' : '暂无急跌标的')
  }
  if (candNoST.value || candNoMonitored.value || candUpOnly.value || candSector.value) {
    return '过滤后无候选，可放宽筛选'
  }
  return '暂无候选'
})

function goTrade() {
  router.push('/trade')
}
function goReplay() {
  router.push('/replay')
}
function goSimulation() {
  router.push('/simulation')
}

const ratioUpDown = computed(() => {
  const up = distribution.value.limit_up || 0
  const down = distribution.value.limit_down || 0
  if (down === 0) return up > 0 ? '∞' : '-'
  return (up / down).toFixed(1)
})

const DIST_ORDER = ['≤-9%', '-9%~-7%', '-7%~-5%', '-5%~-3%', '-3%~0%', '平盘', '0%~+3%', '+3%~+5%', '+5%~+7%', '+7%~+9%', '≥+9%']
const distBuckets = computed(() => {
  const bk = distribution.value.buckets || {}
  if (!Object.keys(bk).length) return []
  const items = DIST_ORDER.map(label => ({ label, count: Number(bk[label]) || 0 }))
  const max = Math.max(1, ...items.map(b => b.count))
  return items.map(b => ({
    label: b.label, count: b.count,
    cls: b.label === '平盘' ? '' : b.label.includes('-') || b.count === 0 ? 'down' : 'up',
    color: b.label === '平盘' ? '#909399' : b.label.includes('-') ? '#14b143' : '#e6452f',
    h: 8 + Math.round(b.count / max * 160)
  }))
})
const emotion = computed(() => {
  if (!regime.value?.data_available && breadthState.value.level === 'unknown') {
    return { label: '数据不足', tagType: 'info', basis: '周期与有效市场宽度均不可用' }
  }
  const up = distribution.value.up_count || 0
  const down = distribution.value.down_count || 0
  const limUp = distribution.value.limit_up || 0
  const limDown = distribution.value.limit_down || 0
  const breadth = up - down
  const risk = limUp - limDown

  // 周期阶段优先（regime 口径：宽度35/涨停结构30/接力20/轮动15，缺项降置信度）
  const st = regime.value?.stage
  const score = regime.value?.score
  if (st?.label && score != null) {
    const toneMap = {
      climax: 'danger', markup: 'danger', start: 'warning',
      repair: 'success', decline: 'info', ice: 'info', unknown: 'info'
    }
    return {
      label: `${st.label} · ${score}`,
      tagType: toneMap[st.code] || 'success',
      regime: { stage: st, score, confidence: regime.value?.confidence, delta: regime.value?.score_delta },
      basis: regime.value?.methodology || '市场状态=周期阶段(regime)为主，结合当日涨跌宽度与涨跌停结构'
    }
  }

  // 无 regime 时退回宽度启发式（旧口径，明确标注）
  if (breadth > 200 && risk > 0) return { label: '情绪偏强 · 赚钱效应好', tagType: 'danger', basis: '涨跌宽度+涨跌停结构（启发式）' }
  if (breadth > 0 && risk >= 0) return { label: '震荡偏强', tagType: 'warning', basis: '涨跌宽度+涨跌停结构（启发式）' }
  if (breadth < -200 && risk < 0) return { label: '情绪冰点 · 亏钱效应', tagType: 'info', basis: '涨跌宽度+涨跌停结构（启发式）' }
  if (breadth < 0) return { label: '震荡偏弱', tagType: 'info', basis: '涨跌宽度+涨跌停结构（启发式）' }
  return { label: '多空均衡', tagType: 'success', basis: '涨跌宽度+涨跌停结构（启发式）' }
})

const regime = ref(null)
const regimeHistory = ref([])
const regimeTrend = computed(() => {
  const rows = (regimeHistory.value || []).slice(-7)
  if (rows.length < 2) return ''
  const scores = rows.map(r => Number(r.score)).filter(n => Number.isFinite(n))
  if (scores.length < 2) return ''
  const d = scores[scores.length - 1] - scores[0]
  if (d >= 8) return `近${scores.length}日评分 +${d.toFixed(1)}，阶段回升`
  if (d <= -8) return `近${scores.length}日评分 ${d.toFixed(1)}，阶段回落`
  return `近${scores.length}日评分 ${d >= 0 ? '+' : ''}${d.toFixed(1)}，阶段震荡`
})
const regimeStageStrip = computed(() => {
  const rows = (regimeHistory.value || []).slice(-10)
  return rows.map(r => ({ date: (r.trade_date || r.date || '').slice(5), score: r.score, label: r.stage?.label || r.stage_label || '-' }))
})

async function loadRegime() {
  try {
    const [cur, hist] = await Promise.all([
      marketApi.regime().catch(() => null),
      marketApi.regimeHistory(20).catch(() => [])
    ])
    regime.value = cur || null
    regimeHistory.value = Array.isArray(hist) ? hist : []
  } catch { /* 保留旧数据 */ }
}

// ---- 轻量 AI 点评（启发式，无需 LLM Key；随行情自动更新） ----
const stateComment = computed(() => {
  const parts = []
  if (regime.value?.stage?.label && regime.value?.score != null) {
    parts.push(`周期阶段【${regime.value.stage.label}】评分 ${regime.value.score}`)
    if (regime.value.previous_score != null) {
      const d = regime.value.score - regime.value.previous_score
      parts.push(`较前值 ${d >= 0 ? '+' : ''}${d.toFixed(1)}`)
    }
    if (regimeTrend.value) parts.push(regimeTrend.value)
    if (regime.value.confidence != null) parts.push(`分项覆盖 ${Math.round(regime.value.confidence * 100)}%（非预测概率）`)
    parts.push('口径=宽度/涨停结构/接力/轮动四分项加权，缺项降置信度，不伪装中性')
  }
  const up = distribution.value.up_count || 0
  const down = distribution.value.down_count || 0
  const limUp = distribution.value.limit_up || 0
  const limDown = distribution.value.limit_down || 0
  if (up || down) {
    const breadth = up - down
    if (breadth > 300) parts.push(`当日普涨（${up}/${down}）`)
    else if (breadth < -300) parts.push(`当日大面积下跌（${down}家），谨慎追高`)
    else if (breadth > 100) parts.push(`涨多跌少（${up}↑/${down}↓）`)
    else if (breadth < -100) parts.push(`跌多涨少（${up}↑/${down}↓）`)
    else parts.push('涨跌互现')
    if (limUp >= 10 && limDown === 0) parts.push('涨停潮无跌停')
    else if (limDown > limUp) parts.push(`跌停(${limDown})>涨停(${limUp})`)
  }
  return parts.join('；')
})
const flowComment = computed(() => {
  const last = marketFlow.value.intraday?.[marketFlow.value.intraday.length - 1]
  if (!last) return ''
  const main = last.main_net || 0
  const superNet = last.super_net || 0
  const parts = []
  parts.push(`数据源大单分类净额 ${main >= 0 ? '+' : ''}${(main / 1e8).toFixed(1)}亿`)
  parts.push(`超大单分类 ${superNet >= 0 ? '+' : ''}${(superNet / 1e8).toFixed(1)}亿；分类不等于机构身份`)
  return parts.join('；')
})
const indexComment = computed(() => {
  const rows = indices.value || []
  if (!rows.length) return ''
  const up = rows.filter((r) => Number(r.change_pct) >= 0)
  const down = rows.filter((r) => Number(r.change_pct) < 0)
  if (down.length === 0) return '三大指数全线翻红；板块和个股是否同步需另看市场宽度'
  if (up.length === 0) return '三大指数集体下跌；结合涨跌家数观察风险扩散'
  return `指数分化（${up.length}红/${down.length}绿），对照板块强弱观察结构差异`
})
const hotComment = computed(() => {
  const rows = hotStocks.value || []
  if (!rows.length) return ''
  const top = rows[0]
  const up = rows.filter((r) => Number(r.change_pct) >= 0).length
  return `人气龙头 ${top.name}（热度 ${top.heat}，${top.change_pct >= 0 ? '+' : ''}${top.change_pct}%）领衔；TOP10 中 ${up} 只上涨，说明盘面热度${up >= 6 ? '较高，资金接力情绪好' : '一般，谨防高位分歧'}`
})
const movers = ref({ rise: [], fall: [] })
const moversLoadedAt = ref(0)
const hotLoadedAt = ref(0)
const distributionLoadedAt = ref(0)
const lastTickAt = ref(Date.now())
let mainTimer = null

const ST_NAME_RE = /(^|[^A-Za-z0-9])(S*ST|\*ST|退[A-Z0-9]{0,4}|X?D[A-Z]{0,2})/i

function isStName(name) {
  if (!name) return false
  ST_NAME_RE.lastIndex = 0
  if (ST_NAME_RE.test(String(name))) return true
  return /(^|[^A-Z])(\*?ST|S*ST)/.test(String(name).toUpperCase()) || /退/.test(String(name))
}

const monitoredSymbols = computed(() => {
  const out = new Set()
  for (const m of monitor.value || []) {
    if (m?.symbol) out.add(String(m.symbol).toUpperCase())
  }
  return out
})

const breadthState = computed(() => {
  const d = distribution.value || {}
  const up = Number(d.up_count)
  const down = Number(d.down_count)
  const total = Number(d.total)
  const known = Number.isFinite(up) && Number.isFinite(down) && (up > 0 || down > 0 || total > 0)
  if (!known) {
    return { level: 'unknown', label: '涨跌分布未知', tagType: 'info', upText: '-', downText: '-' }
  }
  const upNum = up || 0
  const downNum = down || 0
  if (downNum > upNum * 2) return { level: 'risk', label: '跌多涨少，控制回撤', tagType: 'danger', upText: String(upNum), downText: String(downNum) }
  if (upNum > downNum * 2) return { level: 'good', label: '涨多跌少，做多氛围浓', tagType: 'danger', upText: String(upNum), downText: String(downNum) }
  if (upNum >= downNum) return { level: 'ok', label: '涨跌互现偏强', tagType: 'success', upText: String(upNum), downText: String(downNum) }
  return { level: 'ok', label: '涨跌互现偏弱', tagType: 'warning', upText: String(upNum), downText: String(downNum) }
})

const dataStaleness = computed(() => {
  const stamps = [hotLoadedAt.value, moversLoadedAt.value, distributionLoadedAt.value]
  if (stamps.some(v => !v)) {
    return { label: '行情未就绪', tagType: 'info' }
  }
  const age = Math.max(0, lastTickAt.value - Math.min(...stamps))
  if (age < 90 * 1000) return { label: '接口最近拉取 · 源有缓存', tagType: 'success' }
  if (age < 5 * 60 * 1000) return { label: '接口近5分拉取 · 源有缓存', tagType: 'warning' }
  return { label: '已过期，请刷新', tagType: 'danger' }
})
const moversComment = computed(() => {
  const rise = movers.value?.rise || []
  const fall = movers.value?.fall || []
  if (!rise.length && !fall.length) return ''
  const parts = []
  if (rise.length) parts.push(`急拉标兵：${rise.map((r) => r.name).join('、')}`)
  if (fall.length) parts.push(`急跌警示：${fall.map((r) => r.name).join('、')}`)
  if (rise.length && fall.length) parts.push('多空交战激烈，追涨杀跌需谨慎，优先跟随领涨分支')
  else if (rise.length) parts.push('资金正在抢筹拉升，关注持续性')
  else parts.push('盘面整体走弱，谨防进一步回落')
  return parts.join('；')
})
const sectorComment = computed(() => {
  const rows = sectorList.value || []
  if (!rows.length) return ''
  const upRows = rows.filter((s) => Number(s.change_pct) >= 0)
  const strong = upRows.filter((s) => Number(s.change_pct) >= 2)
  const weak = rows.filter((s) => Number(s.change_pct) <= -2)
  const parts = []
  parts.push(`监控 ${rows.length} 板块，上涨 ${upRows.length} / 下跌 ${rows.length - upRows.length}`)
  if (strong.length) parts.push(`强势分支：${strong.slice(0, 3).map((s) => `${s.sector}(${s.change_pct > 0 ? '+' : ''}${s.change_pct}%)`).join('、')}`)
  if (weak.length) parts.push(`弱势分支：${weak.slice(0, 3).map((s) => `${s.sector}(${s.change_pct}%)`).join('、')}`)
  return parts.join('；')
})
const emComment = computed(() => emotion.value.label + (emotion.value.label.includes('强') ? '，短线方向偏多' : emotion.value.label.includes('弱') ? '，仓位宜轻' : ''))

const impText = (v) => (v === 1 ? '重要' : v === 3 ? '一般' : '普通')
const impTag = (v) => (v === 1 ? 'danger' : v === 3 ? 'info' : 'warning')

const todayStr = new Date().toLocaleDateString('zh-CN')

// ---- 每个看板模块独立接口调用，独立定时刷新 ----
async function loadIndices() {
  try { indices.value = await marketApi.indices() } catch { /* 保留旧数据 */ }
}
async function loadIndexIntraday(code) {
  try {
    const rows = await marketApi.intraday({ symbol: code })
    if (Array.isArray(rows) && (indexPeriods[code] || 'mf') === 'mf') indexIntradays[code] = rows
  } catch {
    indexIntradays[code] = indexIntradays[code] || []
  }
}
async function loadIndexKline(code, period) {
  const key = `${code}:${period}`
  try {
    const r = await marketApi.kline({ symbol: code, period })
    if (indexPeriods[code] === period) indexKlines[key] = r?.data || []
  } catch {
    indexKlines[key] = indexKlines[key] || []
  }
}
function loadPanel(code) {
  if ((indexPeriods[code] || 'mf') === 'mf') loadIndexIntraday(code)
  else loadIndexKline(code, indexPeriods[code])
}
function changeIndexPeriod(code, v) {
  indexPeriods[code] = v
  loadPanel(code)
}
async function loadSectorFlowTop() {
  try { flowRank.value = await marketApi.sectorFlowTop() } catch { /* 保留旧数据 */ }
}
async function loadEtf() {
  try { etfFlow.value = await marketApi.etfFlow() } catch { /* 保留旧数据 */ }
}
async function loadNews() {
  try { news.value = (await marketApi.news(50)) || [] } catch { /* 保留旧数据 */ }
}
async function loadRssNews() {
  try {
    const rows = (await rssApi.items({ limit: 30 })) || []
    rssNews.value = rows.filter((r) => !r.is_st)
  } catch { /* RSS 未启用时保持旧数据 */ }
}
async function loadDistribution() {
  try {
    distribution.value = (await marketApi.distribution()) || {}
    if (distribution.value.total) distributionLoadedAt.value = Date.now()
  } catch { /* 保留旧数据 */ }
}
async function loadLadder() {
  try { ladder.value = (await marketApi.limitUpLadder()) || {} } catch { /* 保留旧数据 */ }
}
async function loadMarketFlow() {
  try { marketFlow.value = (await marketApi.marketFlow()) || { date: '', intraday: [], daily: [] } } catch { /* 保留旧数据 */ }
}
async function loadMarketStats() {
  try { marketStats.value = (await marketApi.marketStats()) || {} } catch { /* 保留旧数据 */ }
}

async function analyzeMarket() {
  mktLoading.value = true
  try {
    const r = await agentApi.analyzeMarket()
    mktSummary.value = r?.summary || r?.raw_output || '（空结果，请检查智能体配置）'
    mktDate.value = new Date().toLocaleString('zh-CN')
  } finally {
    mktLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    await Promise.all([
      loadIndices(),
      ...mainIdxDefs.map((m) => loadPanel(m.code)),
      loadSectorFlowTop(),
      loadEtf(),
      loadNews(),
      loadRssNews(),
      loadDistribution(),
      loadLadder(),
      loadSectorMonitor(),
      loadHotStocks(),
      loadPriceMovers(),
      loadMarketFlow(),
      loadCalendar(),
      loadRegulatory(),
      loadMarketStats(),
      loadRegime()
    ])
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  if (loading.value) return
  lastTickAt.value = Date.now()
  await Promise.all([
    loadIndices(),
    ...mainIdxDefs.map((m) => loadPanel(m.code)),
    loadSectorFlowTop(),
    loadEtf(),
    loadDistribution(),
    loadLadder(),
    loadSectorMonitor(),
    loadHotStocks(),
    loadPriceMovers(),
    loadMarketFlow(),
    loadMarketStats(),
    loadRegime()
  ])
}

watch([candSource, candNoST, candNoMonitored, candUpOnly, candSector], saveFilterState)
watch(sectorTabMode, (mode) => { if (mode === 'rotation' && !sectorSpeedRaw.value.length) loadSectorSpeed() })
watch(openSections, savePanelsState, { deep: true })

onMounted(() => {
  load()
  mainTimer = setInterval(refreshAll, 30000)
})
onUnmounted(() => {
  if (mainTimer) clearInterval(mainTimer)
  if (flowIntradayChart) { flowIntradayChart.dispose(); flowIntradayChart = null }
})
</script>

<style scoped>
.terminal-deck { display:grid; grid-template-columns:minmax(265px,1.05fr) minmax(245px,.9fr) minmax(290px,1fr); gap:10px; margin:8px 0 12px; }
.market-pulse { color:#e8eef7; background:linear-gradient(125deg,#132338,#1b344c); border:1px solid #2c4761; border-radius:8px; padding:18px; min-height:278px; display:flex; flex-direction:column; }
.deck-eyebrow { font:700 10px var(--font-mono); letter-spacing:.15em; color:var(--c-primary); text-transform:uppercase; }
.market-pulse .deck-eyebrow { color:#9fb9ce; display:flex; justify-content:space-between; gap:8px; }
.market-pulse .deck-eyebrow span { font:500 10px var(--font-mono); letter-spacing:0; }
.pulse-stage { font-size:26px; font-weight:750; letter-spacing:-.04em; margin:13px 0 4px; line-height:1.2; }
.pulse-note { color:#c4d4e3; font-size:12px; }
.pulse-counts { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:auto; padding:16px 0 10px; }
.pulse-counts div { display:flex; flex-direction:column; gap:4px; border-right:1px solid #40566d; }
.pulse-counts div:last-child { border:0; }
.pulse-counts span { color:#a9c0d0; font-size:11px; }
.pulse-counts strong { color:#fff; font:700 20px var(--font-mono); }
.pulse-counts strong.up { color:#ff7479; }.pulse-counts strong.down { color:#60d69b; }
.breadth-meter { height:6px; background:var(--c-down); border-radius:4px; overflow:hidden; }
.breadth-meter span { display:block; height:100%; background:var(--c-up); }
.pulse-footer { display:flex; justify-content:space-between; align-items:center; margin-top:11px; font-size:12px; }
.pulse-source { color:#abc0d2; font-size:10px; margin-top:8px; }
.desk-index, .desk-sector { padding:14px; background:#fff; border:1px solid var(--c-border); border-radius:8px; min-width:0; }
.desk-panel-head { display:flex; align-items:baseline; justify-content:space-between; color:var(--c-ink); font-weight:700; font-size:14px; gap:8px; border-bottom:1px solid var(--c-border); padding-bottom:10px; }
.desk-panel-head span:last-child { color:var(--c-text-2); font-size:10px; font-weight:400; }
.desk-index-row { display:grid; grid-template-columns:minmax(92px,1fr) auto 74px; align-items:center; gap:10px; border-bottom:1px solid #eef1f5; min-height:56px; }
.desk-index-row div { display:flex; flex-direction:column; }.desk-index-row b { font-size:13px; }.desk-index-row small,.sector-lead small { font-size:10px; color:var(--c-text-2); }.desk-index-row strong { font-size:17px; }.desk-index-row > span { font-size:12px; text-align:right; }
.desk-inline-meta { font-size:11px; color:var(--c-text-2); padding-top:10px; }.desk-inline-meta b { color:var(--c-ink); }
.sector-lead { display:grid; grid-template-columns:minmax(80px,1fr) 62px 86px; width:100%; align-items:center; gap:8px; min-height:41px; border:0; border-bottom:1px solid #eef1f5; background:transparent; text-align:left; cursor:pointer; padding:4px 0; color:var(--c-ink); }
.sector-lead:hover:not(:disabled) { background:var(--c-bg-soft); }.sector-lead:disabled { cursor:default; }.sector-lead span:first-child { min-width:0; display:flex; flex-direction:column; }.sector-lead b,.sector-lead small { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.sector-lead .mono { font-size:11px; text-align:right; }
.desk-empty { padding:24px 12px; color:var(--c-text-2); font-size:12px; text-align:center; }
.opportunity-board { background:#fff; border:1px solid var(--c-border); border-radius:8px; margin-bottom:12px; overflow:hidden; }
.board-head { display:flex; justify-content:space-between; align-items:end; gap:10px; padding:16px 18px 12px; }.board-head h2 { margin:4px 0; font-size:21px; }.board-head p { color:var(--c-text-2); font-size:12px; }.board-count { color:var(--c-ink); font-size:26px; font-weight:700; }.board-count small { font-size:11px; color:var(--c-text-2); font-weight:400; }
.board-controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; padding:9px 18px; background:var(--c-bg-soft); border-top:1px solid var(--c-border); border-bottom:1px solid var(--c-border); }.board-sector { width:150px; }
.board-table-wrap { overflow-x:auto; }.board-table { width:100%; border-collapse:collapse; min-width:760px; font-size:12px; }.board-table th { text-align:left; color:var(--c-text-2); background:#f7f8fa; font-weight:600; padding:8px 12px; }.board-table td { padding:9px 12px; border-top:1px solid var(--c-border); white-space:nowrap; }.board-table tbody tr { cursor:pointer; }.board-table tbody tr:hover,.board-table tbody tr:focus-visible { background:#edf3fb; outline:2px solid var(--c-focus); }.board-table td:first-child { display:flex; gap:12px; align-items:center; }.board-rank { color:var(--c-text-2); font-size:11px; }.board-stock { display:flex; flex-direction:column; }.board-stock small { color:var(--c-text-2); font-size:10px; }.board-reason { max-width:290px; overflow:hidden; text-overflow:ellipsis; color:var(--c-text-2); }.board-foot { padding:9px 18px; border-top:1px solid var(--c-border); font-size:11px; color:var(--c-text-2); }
@media(max-width:1190px) { .terminal-deck { grid-template-columns:repeat(2,minmax(0,1fr)); }.desk-sector { grid-column:1/-1; } }
@media(max-width:690px) { .terminal-deck { grid-template-columns:1fr; }.desk-sector { grid-column:auto; }.board-head { align-items:start; }.board-head h2 { font-size:18px; }.market-pulse { min-height:250px; } }
.regime-mini {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  padding: 4px 0;
}
.regime-mini .el-tag {
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.overview-bar {
  display: flex;
  align-items: center;
  gap: 0;
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  margin-bottom: 6px;
  flex-wrap: wrap;
  font-size: 12px;
}
.ov-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.ov-name {
  color: var(--c-text-3);
  font-size: 11px;
}
.ov-sep {
  width: 1px;
  height: 14px;
  background: var(--c-border);
  margin: 0 8px;
  flex-shrink: 0;
}
.funnel-collapse {
  border: none;
}
.funnel-collapse :deep(.el-collapse-item__header) {
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  font-size: 13px;
  font-weight: 600;
  height: 34px;
  line-height: 34px;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.funnel-collapse :deep(.el-collapse-item__header:hover) {
  background: var(--c-bg);
}
.funnel-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  margin-bottom: 0;
}
.funnel-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}
.news-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--c-border);
}
.ai-comment {
  margin-top: 6px;
  padding: 5px 8px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--c-text-2);
  background: linear-gradient(90deg, var(--c-bg), #fdf6ec);
  border-left: 3px solid #e6a23c;
  border-radius: var(--radius-sm);
}
.news-title {
  color: var(--c-text-1);
  text-decoration: none;
  flex: 1;
  min-width: 0;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  word-break: break-all;
}
.news-time {
  color: var(--c-text-3);
  flex-shrink: 0;
}
.col-card {
  display: flex;
  flex-direction: column;
}
@media (min-width: 768px) {
  .col-card { min-height: 380px; max-height: 500px; overflow-y: auto; }
  .col-card.flow-card { height: 260px; }
}
.news-scroll {
  flex: 1;
  min-height: 0;
  margin-top: 6px;
}
.ix-panel {
  border-radius: var(--radius-sm);
  height: 100%;
}
.chart-box {
  min-height: 180px;
}
.flow-intraday-chart {
  width: 100%;
  height: 235px;
}
.flow-daily-chart {
  height: 235px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.flow-daily-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.flow-daily-bar-wrap {
  flex: 1;
  height: 10px;
  background: #f0f0f0;
  border-radius: 5px;
  overflow: hidden;
}
.flow-daily-bar {
  height: 100%;
  border-radius: 5px;
  transition: width .3s;
}
.idx-card {
  cursor: pointer;
  border: 2px solid transparent;
}
.idx-card.active {
  border-color: var(--c-primary);
}
.split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.flow-row {
  display: grid;
  grid-template-columns: 1fr 72px 64px;
  gap: 4px;
  padding: 3px 0;
  border-bottom: 1px dashed var(--c-border);
  align-items: center;
}
.mkt-text {
  white-space: pre-wrap;
  line-height: 1.8;
  max-height: 55vh;
  overflow: auto;
}
.sector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
  gap: 6px;
}
.sector-card {
  padding: 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-border);
  cursor: pointer;
  text-align: center;
  transition: all .15s;
}
.sector-card:hover { border-color: var(--c-primary); background: rgba(46,107,198,.04); }
.sector-card.active { border-color: var(--c-primary); background: rgba(46,107,198,.08); font-weight: 600; }
.hot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 6px;
}
.hot-card {
  padding: 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-border);
  cursor: pointer;
  transition: all .15s;
  line-height: 1.6;
}
.hot-card:hover { border-color: var(--c-up); background: rgba(239,35,42,.03); }
.heat-bar {
  height: 3px;
  border-radius: 2px;
  background: var(--c-border);
  margin-top: 4px;
  overflow: hidden;
}
.heat-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, #f7b32b, var(--c-up));
}
.movers-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.movers-col {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
  align-content: start;
}
.movers-title {
  grid-column: 1 / -1;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 0 2px 2px;
  border-left: 3px solid var(--c-up);
  padding-left: 6px;
}
.movers-col:last-child .movers-title { border-left-color: var(--c-down); }
.movers-col .hot-card { min-height: 72px; }
@media (max-width: 1100px) {
  .movers-grid { grid-template-columns: 1fr; }
}
.dist-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 180px;
  overflow-x: auto;
  overflow-y: hidden;
}
.dist-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  min-width: 36px;
  flex: 1 0 36px;
  height: 100%;
  cursor: default;
}
.dist-num { font-size: 10px; line-height: 1; }
.dist-bar { width: 70%; border-radius: 2px 2px 0 0; min-height: 2px; opacity: .85; }
.dist-label { font-size: 10px; color: var(--c-text-2); white-space: nowrap; }
.desk-nav { display:flex; gap:6px; overflow-x:auto; padding:8px 0; white-space:nowrap; }
.desk-nav button { color:var(--c-primary); background:#fff; border:1px solid var(--c-border); padding:7px 12px; border-radius:4px; cursor:pointer; font-size:12px; }
.desk-nav button:hover, .desk-nav button:focus-visible { background:#edf3fb; border-color:var(--c-primary); }
.cal-scroll { flex: 1; min-height: 0; overflow: auto; }
.cal-row { display: flex; align-items: center; gap: 4px; padding: 3px 0; border-bottom: 1px dashed var(--c-border); }
.cal-date { color: var(--c-text-3); font-size: 10px; flex-shrink: 0; width: 38px; }
.cal-name { flex-shrink: 0; }
.cal-val { flex-shrink: 0; }
.cal-sub { flex: 1; min-width: 0; text-align: right; color: var(--c-text-3); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.funnel-top { display: flex; flex-direction: column; }
.funnel-card { margin-top: 6px; }
.cand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 6px;
}
.cand-card { min-height: 72px; }
.reason-row { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
.cand-why {
  color: var(--c-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}
.unk { color: var(--c-text-3); }
.kind-badge { display: inline-block; font-size: 9px; padding: 0 3px; border-radius: 2px; margin-right: 2px; font-weight: 400; line-height: 14px; vertical-align: middle; }
.kind-industry { background: rgba(46,107,198,.08); color: var(--c-primary); }
.kind-concept { background: #fdf6ec; color: #e6a23c; }
.speed-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--c-border);
}
.speed-rank {
  width: 20px;
  text-align: center;
  font-size: 11px;
  color: var(--c-text-3);
  flex-shrink: 0;
}
.speed-rank.speed-top {
  color: #ef232a;
  font-weight: 700;
}
.speed-name {
  width: 90px;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.speed-bar-wrap {
  flex: 1;
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
  min-width: 40px;
}
.speed-bar {
  height: 100%;
  border-radius: 4px;
  transition: width .3s;
}
.speed-pct {
  width: 60px;
  text-align: right;
  flex-shrink: 0;
}
.speed-flow {
  width: 60px;
  text-align: right;
  flex-shrink: 0;
}
.speed-leader {
  width: 70px;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stat-item {
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: 12px;
  padding: 12px 16px;
  text-align: center;
  min-width: 80px;
}
.stat-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--c-text-1);
  line-height: 1.2;
  margin-bottom: 2px;
}
.stat-value.danger { color: var(--c-down); }
.stat-value.profit { color: var(--c-up); }
.stat-label {
  font-size: 11px;
  color: var(--c-text-3);
}
</style>
