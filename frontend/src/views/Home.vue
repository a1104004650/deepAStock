<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size: 18px">大盘看板</h2>
        <el-tag size="small" type="info">{{ todayStr }}</el-tag>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
        <el-button size="small" type="warning" :loading="mktLoading" @click="analyzeMarket">AI 大盘分析</el-button>
        <span class="fs12" style="color:#909399">每 15 秒自动刷新行情</span>
      </div>

      <div class="funnel-top">
        <div class="overview-bar">
          <template v-for="mc in mainIdxDefs" :key="mc.code">
            <span class="ov-item">
              <span class="ov-name">{{ mc.name }}</span>
              <span class="mono bold" :class="ixCls(mc.code)">{{ fmtPrice(ixOf(mc.code)?.price) }}</span>
              <span class="mono fs12" :class="ixCls(mc.code)">{{ candidatePct(ixOf(mc.code)?.change_pct) }}</span>
            </span>
            <span class="ov-sep" />
          </template>
          <span class="ov-item">
            <span class="ov-name">情绪</span>
            <el-tag :type="emotion.tagType" size="small">{{ emotion.label }}</el-tag>
          </span>
          <span class="ov-sep" />
          <span class="ov-item">
            <span class="ov-name">涨停</span>
            <span class="mono bold up">{{ distribution.limit_up ?? '0' }}</span>
          </span>
          <span class="ov-item">
            <span class="ov-name">跌停</span>
            <span class="mono bold down">{{ distribution.limit_down ?? '0' }}</span>
          </span>
          <span class="ov-sep" />
          <span class="ov-item">
            <span class="ov-name">成交</span>
            <span class="mono bold">{{ fmtMoney(distribution.amount) }}</span>
          </span>
        </div>

        <div class="card funnel-card">
          <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:6px">
            <div class="flex gap" style="align-items:center;flex-wrap:wrap">
              <span class="fs14 bold">决策漏斗</span>
              <el-tag size="small" :type="breadthState.tagType">{{ breadthState.label }}</el-tag>
              <span class="fs12" :class="breadthState.level === 'unknown' ? 'unk' : breadthState.level === 'risk' ? 'down' : 'up'">
                上涨 {{ breadthState.upText }} / 下跌 {{ breadthState.downText }}
              </span>
              <el-divider direction="vertical" />
              <span class="fs12" style="color:#909399">数据时效</span>
              <el-tag size="small" :type="dataStaleness.tagType">{{ dataStaleness.label }}</el-tag>
            </div>
            <span class="fs11" style="color:#c0c4cc">筛选来自人气/异动/板块公开行情，仅供研究参考，不构成交易指令</span>
          </div>
          <div class="flex gap mt8" style="align-items:center;flex-wrap:wrap">
            <el-radio-group v-model="candSource" size="small">
              <el-radio-button value="hot">人气TOP10</el-radio-button>
              <el-radio-button value="rise">急拉</el-radio-button>
              <el-radio-button value="fall">急跌</el-radio-button>
            </el-radio-group>
            <el-divider direction="vertical" />
            <el-checkbox v-model="candNoST" size="small">排除 ST/退市风险</el-checkbox>
            <el-checkbox v-model="candNoMonitored" size="small">排除重点监控</el-checkbox>
            <el-checkbox v-model="candUpOnly" size="small">仅收红</el-checkbox>
            <el-divider direction="vertical" />
            <el-select v-model="candSector" size="small" clearable placeholder="全部监控板块" style="width:150px">
              <el-option v-for="s in sectorOptions" :key="s.value" :value="s.value" :label="s.label" />
            </el-select>
            <span class="fs12" style="color:#909399">共 {{ candPool.length }} 只 · 命中 {{ candItems.length }} 只</span>
          </div>
          <div v-if="candItems.length" class="cand-grid mt8">
            <div v-for="c in candItems" :key="c.symbol" class="hot-card cand-card" @click="goStock(c.symbol, c.name)">
              <div class="flex between" style="align-items:center;gap:4px">
                <span class="fs13 bold">{{ c.rank }}. {{ c.name }}</span>
                <el-tag size="small" :type="Number(c.change_pct) >= 0 ? 'danger' : 'success'">
                  {{ Number(c.change_pct) >= 0 ? '+' : '' }}{{ c.change_pct }}%
                </el-tag>
              </div>
              <div class="mono fs15" style="color:#303133">{{ c.price }}</div>
              <div class="fs11" style="color:#909399">热度 {{ c.heat }} · 换手 {{ c.hsl }}% · 量比 {{ c.lb }}</div>
              <div class="reason-row"><el-tag v-for="(t, i) in c.tags" :key="i" size="small" effect="plain" type="info">{{ t }}</el-tag></div>
              <div class="fs11 cand-why" :title="c.why">{{ c.why }}</div>
            </div>
          </div>
          <el-empty v-else :description="candEmptyText" :image-size="46" />
          <div class="fs11" style="color:#c0c4cc;margin-top:6px">
            候选入选条件：板块资金流/板块监控命中 + 涨速榜上榜 + 热度达标（三项数据均来自本页行情接口）。
            点击候选进入个股详情研究；模拟交易请到 <el-link type="primary" :underline="false" @click="goSimulation">模拟交易</el-link>，实盘记录到 <el-link type="primary" :underline="false" @click="goTrade">实盘导入</el-link>，历史验证到 <el-link type="primary" :underline="false" @click="goReplay">每日复盘</el-link>。
          </div>
        </div>
      </div>

      <!-- 三大指数整行展示：每个面板独立周期（分时/日K/60/30/15/5分），分时与K线均带成交量 -->
      <el-row :gutter="10">
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

      <div class="ai-comment" v-if="indexComment">💡 指数点评：{{ indexComment }}</div>

      <!-- 市场状态：左侧涨跌区间分布 + 右侧沪深两市大盘资金流向 -->
      <el-collapse v-model="openSections" class="funnel-collapse mt8">
      <el-collapse-item name="sentiment" title="📊 市场情绪 · 涨跌分布">
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
              <span class="fs14 bold">沪深两市大盘资金流向 <span class="fs12" style="color:#909399">{{ marketFlow.date }} · 今日分时</span></span>
            </div>
            <div class="chart-box mt4">
              <LineChart v-if="mfChartData.length" :data="mfChartData" height="235px" :multi="mfSeries" :area="true" />
              <div v-else class="fs12" style="color:#909399;text-align:center;height:235px;line-height:235px">资金流向加载中…</div>
            </div>
            <div class="ai-comment" v-if="flowComment">💡 {{ flowComment }}</div>
          </div>
        </el-col>
      </el-row>
      </el-collapse-item>
      <el-collapse-item name="hot" title="🔥 人气排行 · 实时异动">
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">人气股票 TOP10 <span class="fs12" style="color:#909399">（按当日 换手×量比×涨幅 综合热度估算）</span></span>
              <span class="fs12" style="color:#909399">点击进入个股详情 · {{ todayStr }}</span>
            </div>
            <div class="hot-grid mt8">
              <div v-for="(r, i) in hotStocks" :key="r.symbol" class="hot-card" @click="goStock(r.symbol, r.name)">
                <div class="flex between" style="align-items:center;gap:4px">
                  <span class="fs13 bold">{{ i + 1 }}. {{ r.name }}</span>
                  <el-tag size="small" :type="Number(r.change_pct) >= 0 ? 'danger' : 'success'">
                    {{ Number(r.change_pct) >= 0 ? '+' : '' }}{{ r.change_pct }}%
                  </el-tag>
                </div>
                <div class="mono fs15" style="color:#303133">{{ r.price }}</div>
                <div class="fs11" style="color:#909399">
                  热度 <b :style="{ color: hotColor(r.heat) }">{{ r.heat }}</b>
                  · 换手 {{ r.hsl }}% · 量比 {{ r.lb }} · 成交 {{ fmtMoney(r.turnover * 1e4) }}
                </div>
                <div class="heat-bar"><div class="heat-fill" :style="{ width: Math.min(100, r.heat) + '%' }" /></div>
              </div>
              <el-empty v-if="!hotStocks.length" description="暂无人气排行" :image-size="40" />
            </div>
            <div class="ai-comment" v-if="hotComment">💡 人气点评：{{ hotComment }}</div>
          </div>
        </el-col>
      </el-row>

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
                    <el-tag size="small" type="danger">+{{ r.speed }}%/分</el-tag>
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
                    <el-tag size="small" type="success">{{ r.speed }}%/分</el-tag>
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
      <el-collapse-item name="sectors" title="📈 板块监控">
      <el-row :gutter="10" class="mt8">
        <el-col :span="24">
          <div class="card">
            <div class="flex between" style="align-items:center;flex-wrap:wrap;gap:4px">
              <span class="fs14 bold">板块监控</span>
              <div class="flex gap" style="align-items:center">
                <el-radio-group v-model="sectorKind" size="small">
                  <el-radio-button value="all">全部</el-radio-button>
                  <el-radio-button value="行业">行业</el-radio-button>
                  <el-radio-button value="概念">概念</el-radio-button>
                </el-radio-group>
                <span class="fs12" style="color:#909399">点击板块查看分时</span>
                <el-button size="small" :loading="sectorLoading" @click="loadSectorMonitor">刷新</el-button>
              </div>
            </div>
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
              <span class="fs14 bold">ETF 资金流 <span class="fs12 mono" style="color:#909399">（截至 {{ etfFlowDate }}）</span></span>
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
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'
import LineChart from '../components/LineChart.vue'
import KlineChart from '../components/KlineChart.vue'
import { marketApi, agentApi, rssApi } from '../api'
import { useSymbolStore } from '../stores/symbol'
import { formatNewsTime as _formatNewsTime, toEpochMs } from '../utils/time'

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
const openSections = ref(['sentiment', 'hot', 'sectors', 'fundflow', 'calendar', 'news'])
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
const mfChartData = computed(() => {
  return Array.isArray(marketFlow.value.intraday) ? marketFlow.value.intraday : []
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
const flowRank = ref({ industries: { in: [], out: [] }, concepts: { in: [], out: [] } })
const etfFlow = ref({ in_top: [], out_top: [], all: [] })
const etfDim = ref('net_1d')

const sectorList = ref([])
const sectorLoading = ref(false)
const selectedSector = ref(null)
const sectorIntraday = ref([])
const sectorPreClose = ref(0)
const sectorKind = ref('all')
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
const etfIn = computed(() => etfFlow.value.in_top || [])
const etfOut = computed(() => etfFlow.value.out_top || [])
const etfFlowDate = computed(() => (etfFlow.value.in_top || []).find((r) => r.flow_date)?.flow_date || '')
const maxBoard = computed(() => {
  const keys = Object.keys(ladder.value.ladder || {})
  return keys.length ? Math.max(...keys.map((k) => parseInt(k, 10))) : 0
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

const candSource = ref('hot')
const candNoST = ref(true)
const candNoMonitored = ref(true)
const candUpOnly = ref(false)
const candSector = ref('')

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
  const up = distribution.value.up_count || 0
  const down = distribution.value.down_count || 0
  const limUp = distribution.value.limit_up || 0
  const limDown = distribution.value.limit_down || 0
  const breadth = up - down
  const risk = limUp - limDown
  if (breadth > 200 && risk > 0) return { label: '情绪偏强 · 赚钱效应好', tagType: 'danger' }
  if (breadth > 0 && risk >= 0) return { label: '震荡偏强', tagType: 'warning' }
  if (breadth < -200 && risk < 0) return { label: '情绪冰点 · 亏钱效应', tagType: 'info' }
  if (breadth < 0) return { label: '震荡偏弱', tagType: 'info' }
  return { label: '多空均衡', tagType: 'success' }
})

// ---- 轻量 AI 点评（启发式，无需 LLM Key；随行情自动更新） ----
const stateComment = computed(() => {
  const up = distribution.value.up_count || 0
  const down = distribution.value.down_count || 0
  const limUp = distribution.value.limit_up || 0
  const limDown = distribution.value.limit_down || 0
  if (!up && !down) return ''
  const breadth = up - down
  const parts = []
  if (breadth > 300) parts.push(`普涨格局，上涨 ${up} 家远超下跌 ${down} 家，短线做多气氛浓`)
  else if (breadth < -300) parts.push(`大面积下跌（${down}家），情绪偏冰点，谨慎追高`)
  else if (breadth > 100) parts.push(`涨多跌少（${up}↑/${down}↓），结构偏强`)
  else if (breadth < -100) parts.push(`跌多涨少（${up}↑/${down}↓），注意回撤风险`)
  else parts.push('涨跌互现，多空均衡，宜选强弃弱')
  if (limUp >= 10 && limDown === 0) parts.push('涨停潮无跌停，赚钱效应极佳')
  else if (limDown > limUp) parts.push(`跌停(${limDown})多于涨停(${limUp})，风险偏好下降`)
  return parts.join('；')
})
const flowComment = computed(() => {
  const last = marketFlow.value.intraday?.[marketFlow.value.intraday.length - 1]
  if (!last) return ''
  const main = last.main_net || 0
  const superNet = last.super_net || 0
  const parts = []
  const abs = Math.abs(main)
  if (main < 0 && abs > 1e10) parts.push(`两市主力大幅净流出 ${(abs / 1e8).toFixed(0)}亿，机构减仓迹象明显`)
  else if (main > 0 && abs > 1e10) parts.push(`两市主力净流入 ${(abs / 1e8).toFixed(0)}亿，资金积极进场`)
  else if (main < 0) parts.push(`主力净流出 ${(abs / 1e8).toFixed(1)}亿，观望为主`)
  else parts.push(`主力净流入 ${(abs / 1e8).toFixed(1)}亿，情绪回暖`)
  parts.push(superNet < 0 ? '超大单（机构）在卖出，注意权重股拖累' : '超大单（机构）净买入，权重托底')
  return parts.join('；')
})
const indexComment = computed(() => {
  const rows = indices.value || []
  if (!rows.length) return ''
  const up = rows.filter((r) => Number(r.change_pct) >= 0)
  const down = rows.filter((r) => Number(r.change_pct) < 0)
  if (down.length === 0) return '三大指数全线翻红，权重与题材共振，做多动能充足'
  if (up.length === 0) return '三大指数集体下挫，谨防破位风险，多看少动'
  return `指数分化（${up.length}红/${down.length}绿），结构性行情，优先关注走强分支`
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
let heartbeatTimer = null

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
  const age = Math.max(0, Date.now() - Math.max(hotLoadedAt.value, moversLoadedAt.value, distributionLoadedAt.value, lastTickAt.value))
  if (hotLoadedAt.value === 0 && moversLoadedAt.value === 0 && distributionLoadedAt.value === 0) {
    return { label: '行情未就绪', tagType: 'info' }
  }
  if (age < 90 * 1000) return { label: '实时（1分内）', tagType: 'success' }
  if (age < 5 * 60 * 1000) return { label: '近期（5分内）', tagType: 'warning' }
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

function fmtPrice(v) {
  return v == null ? '-' : Number(v).toFixed(2)
}
function fmtMoney(v) {
  if (v == null) return '-'
  const n = Number(v)
  const abs = Math.abs(n)
  if (abs >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (abs >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}

// ---- 每个看板模块独立接口调用，独立定时刷新 ----
async function loadIndices() {
  try { indices.value = await marketApi.indices() } catch { /* 保留旧数据 */ }
}
async function loadIndexIntraday(code) {
  try {
    const rows = await marketApi.intraday({ symbol: code })
    if (Array.isArray(rows)) indexIntradays[code] = rows
  } catch {
    indexIntradays[code] = indexIntradays[code] || []
  }
}
async function loadIndexKline(code, period) {
  const key = `${code}:${period}`
  try {
    const r = await marketApi.kline({ symbol: code, period })
    indexKlines[key] = r?.data || []
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
    distributionLoadedAt.value = Date.now()
  } catch { /* 保留旧数据 */ }
}
async function loadLadder() {
  try { ladder.value = (await marketApi.limitUpLadder()) || {} } catch { /* 保留旧数据 */ }
}
async function loadMarketFlow() {
  try { marketFlow.value = (await marketApi.marketFlow()) || { date: '', intraday: [], daily: [] } } catch { /* 保留旧数据 */ }
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
      loadRegulatory()
    ])
  } finally {
    loading.value = false
  }
}

let indexTimer = null
let newsTimer = null
let flowTimer = null
let distTimer = null
let sectorTimer = null

onMounted(() => {
  load()
  heartbeatTimer = setInterval(() => { lastTickAt.value = Date.now() }, 15000)
  indexTimer = setInterval(() => { loadIndices(); mainIdxDefs.forEach((m) => loadPanel(m.code)) }, 15000)
  newsTimer = setInterval(() => { loadNews(); loadRssNews() }, 60000)
  flowTimer = setInterval(() => { loadSectorFlowTop(); loadEtf(); loadHotStocks(); loadPriceMovers() }, 60000)
  distTimer = setInterval(() => { loadDistribution(); loadLadder(); loadMarketFlow(); loadCalendar(); loadRegulatory() }, 60000)
  sectorTimer = setInterval(loadSectorMonitor, 15000)
})
onUnmounted(() => {
  if (indexTimer) clearInterval(indexTimer)
  if (newsTimer) clearInterval(newsTimer)
  if (flowTimer) clearInterval(flowTimer)
  if (distTimer) clearInterval(distTimer)
  if (sectorTimer) clearInterval(sectorTimer)
  if (heartbeatTimer) clearInterval(heartbeatTimer)
})
</script>

<style scoped>
.page {
  --c-up: #e6452f;
  --c-down: #14b143;
  --c-flat: #909399;
  --c-accent: #409eff;
  --c-bg: #f8f9fb;
  --c-card: #fff;
  --c-border: #ebeef5;
}
.overview-bar {
  display: flex;
  align-items: center;
  gap: 0;
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  padding: 8px 14px;
  margin-bottom: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}
.ov-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.ov-name {
  color: #909399;
  font-size: 12px;
}
.ov-sep {
  width: 1px;
  height: 16px;
  background: #e4e7ed;
  margin: 0 10px;
  flex-shrink: 0;
}
.funnel-collapse {
  border: none;
}
.funnel-collapse :deep(.el-collapse-item__header) {
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  padding: 0 14px;
  font-size: 14px;
  font-weight: 600;
  height: 40px;
  line-height: 40px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.funnel-collapse :deep(.el-collapse-item__header:hover) {
  background: #f0f2f5;
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
  padding: 5px 0;
  border-bottom: 1px dashed #f0f0f0;
}
.ai-comment {
  margin-top: 8px;
  padding: 6px 8px;
  font-size: 12px;
  line-height: 1.6;
  color: #606266;
  background: linear-gradient(90deg, #f5f7fa, #fdf6ec);
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
}
.news-title {
  color: #303133;
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
  color: #c0c4cc;
  flex-shrink: 0;
}
.col-card {
  display: flex;
  flex-direction: column;
}
/* 四大板块（投资日历/监管异动/消息滚动/ETF资金流）统一等高 */
@media (min-width: 768px) {
  .col-card { height: 440px; }
  /* 行业/概念资金流只放 流入/流出 TOP5，无需 440px */
  .col-card.flow-card { height: 300px; }
}
.news-scroll {
  flex: 1;
  min-height: 0;
  margin-top: 8px;
}
.ix-panel {
  border-radius: 8px;
  height: 100%;
}
.chart-box {
  min-height: 200px;
}
.idx-card {
  cursor: pointer;
  border: 2px solid transparent;
}
.idx-card.active {
  border-color: #409eff;
}
.split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.flow-row {
  display: grid;
  grid-template-columns: 1fr 72px 64px;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px dashed #f5f5f5;
  align-items: center;
}
.mkt-text {
  white-space: pre-wrap;
  line-height: 1.9;
  max-height: 55vh;
  overflow: auto;
}
.sector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}
.sector-card {
  padding: 8px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  cursor: pointer;
  text-align: center;
  transition: all .15s;
}
.sector-card:hover { border-color: #409eff; background: #f0f7ff; }
.sector-card.active { border-color: #409eff; background: #ecf5ff; font-weight: 600; }
.hot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 8px;
}
.hot-card {
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  cursor: pointer;
  transition: all .15s;
  line-height: 1.7;
}
.hot-card:hover { border-color: #ef232a; background: #fff5f5; }
.heat-bar {
  height: 5px;
  border-radius: 3px;
  background: #f0f0f0;
  margin-top: 6px;
  overflow: hidden;
}
.heat-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #f7b32b, #ef232a);
}
.movers-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.movers-col {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  align-content: start;
}
.movers-title {
  grid-column: 1 / -1;
  font-size: 13px;
  font-weight: 700;
  padding: 2px 0 2px 2px;
  border-left: 3px solid #ef232a;
  padding-left: 8px;
}
.movers-col:last-child .movers-title { border-left-color: #14b143; }
.movers-col .hot-card { min-height: 84px; }
@media (max-width: 1100px) {
  .movers-grid { grid-template-columns: 1fr; }
}
.dist-bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 210px;
  overflow: hidden;
}
.dist-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 3px;
  min-width: 40px;
  flex: 1;
  height: 100%;
  cursor: default;
}
.dist-num { font-size: 11px; line-height: 1; }
.dist-bar { width: 70%; border-radius: 2px 2px 0 0; min-height: 2px; opacity: .85; }
.dist-label { font-size: 10px; color: #909399; white-space: nowrap; }
.cal-scroll { flex: 1; min-height: 0; overflow: auto; }
.cal-row { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px dashed #f5f5f5; }
.cal-date { color: #c0c4cc; font-size: 11px; flex-shrink: 0; width: 42px; }
.cal-name { flex-shrink: 0; }
.cal-val { flex-shrink: 0; }
.cal-sub { flex: 1; min-width: 0; text-align: right; color: #909399; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.funnel-top { display: flex; flex-direction: column; }
.funnel-card { margin-top: 8px; }
.cand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 8px;
}
.cand-card { min-height: 84px; }
.reason-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.cand-why {
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 3px;
}
.unk { color: #909399; }
.kind-badge { display: inline-block; font-size: 10px; padding: 0 4px; border-radius: 3px; margin-right: 3px; font-weight: 400; line-height: 16px; vertical-align: middle; }
.kind-industry { background: #ecf5ff; color: #409eff; }
.kind-concept { background: #fdf6ec; color: #e6a23c; }
</style>