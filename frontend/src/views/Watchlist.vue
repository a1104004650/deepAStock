<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px">
        <h2 style="font-size:18px">自选股</h2>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新行情</el-button>
      </div>

      <el-row :gutter="10">
        <!-- 左侧：分组 + 自选股列表 -->
        <el-col :xs="24" :sm="8" :md="5">
          <div class="card sidebar-card">
            <div class="flex between" style="align-items:center;margin-bottom:8px">
              <span class="fs14 bold">自选分组</span>
              <el-button size="small" type="primary" link @click="openAddGroup">
                <el-icon><Plus /></el-icon>新建
              </el-button>
            </div>
            <el-scrollbar max-height="140">
              <div class="group-item" :class="{ active: showRecent }" @click="showRecentViewed">
                <span>🕐 最近查看</span>
                <span class="fs12" style="color:#909399">{{ recentList.length }}</span>
              </div>
              <div v-for="g in groups" :key="g.id" class="group-item" :class="{ active: !showRecent && currentGroupId === g.id }" @click="selectGroup(g.id)">
                <span>{{ g.icon || '📁' }} {{ g.name }}</span>
                <span class="fs12" style="color:#909399;margin-right:4px">{{ g.items.length }}</span>
                <el-icon v-if="g.name !== '默认分组'" class="group-del" @click.stop="deleteGroup(g)"
                  style="color:#909399;cursor:pointer;font-size:12px">
                  <Close />
                </el-icon>
              </div>
            </el-scrollbar>
            <el-empty v-if="!groups.length && !recentList.length" description="暂无分组" :image-size="50" />

            <el-divider style="margin:10px 0" />
            <div class="flex between" style="align-items:center;margin-bottom:8px">
              <span class="fs14 bold">{{ showRecent ? '最近查看' : (currentGroup.name || '自选股') }}</span>
              <div class="flex gap" style="align-items:center">
                <template v-if="!showRecent">
                  <el-button v-if="!batchMode" size="small" link @click="openSearch"><el-icon><Plus /></el-icon>添加</el-button>
                  <el-button v-if="!batchMode" size="small" type="danger" link @click="batchMode = true">批量删除</el-button>
                  <template v-else>
                    <el-button size="small" link @click="batchMode = false">取消</el-button>
                    <el-button size="small" type="danger" plain :disabled="!selectedForDelete.length" @click="batchRemove">
                      删除选中{{ selectedForDelete.length ? `(${selectedForDelete.length})` : '' }}
                    </el-button>
                  </template>
                </template>
              </div>
            </div>
            <el-scrollbar max-height="400">
              <div
                v-for="row in displayItems"
                :key="row.symbol"
                class="wl-item"
                :class="{ active: symbolStore.selectedSymbol === row.symbol }"
                @click="batchMode ? toggleDelete(row) : selectItem(row)"
              >
                <div class="wl-line">
                  <span class="flex gap" style="align-items:center">
                    <el-checkbox v-if="batchMode && !showRecent" :model-value="selectedForDelete.includes(row.id)" @change="toggleDelete(row)" @click.stop size="small" />
                    <span class="bold" :class="{ 'fs13': showRecent }">{{ row.name }}</span>
                  </span>
                  <span class="mono fs14" :class="pctCls(row)">{{ fmt(row.price) }}</span>
                </div>
                <div class="wl-line fs12" style="color:#909399">
                  <span>{{ row.symbol }}</span>
                  <span class="flex gap" style="align-items:center">
                    <span class="mono" :class="pctCls(row)">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + Number(row.change_pct).toFixed(2) + '%') }}</span>
                    <span v-if="!batchMode && !showRecent && row.id" class="wl-del" @click.stop="removeOne(row)">✕</span>
                  </span>
                </div>
              </div>
            </el-scrollbar>
            <el-empty v-if="!displayItems.length" description="暂无自选股" :image-size="50" />
          </div>
        </el-col>

        <!-- 右侧：K线 + 详情 tabs -->
        <el-col :xs="24" :sm="16" :md="19">
          <div class="card" v-if="symbolStore.selectedSymbol">
            <div class="detail-wrap">
            <div class="flex gap" style="align-items:center;flex-wrap:wrap">
              <span class="fs16 bold">{{ symbolStore.selectedRealtime.name || symbolStore.selectedSymbol }}</span>
              <span class="fs12" style="color:#909399">{{ symbolStore.selectedSymbol }}</span>
              <span v-if="symbolStore.selectedRealtime.price" class="fs18 bold mono" :class="pctCls(symbolStore.selectedRealtime)">
                {{ fmt(symbolStore.selectedRealtime.price) }}
                <span class="fs12">{{ symbolStore.selectedRealtime.change_pct >= 0 ? '+' : '' }}{{ symbolStore.selectedRealtime.change }} / {{ symbolStore.selectedRealtime.change_pct >= 0 ? '+' : '' }}{{ symbolStore.selectedRealtime.change_pct }}%</span>
              </span>
              <div style="flex:1"></div>
              <el-radio-group v-model="period" size="small">
                <el-radio-button value="mf">分时</el-radio-button>
                <el-radio-button value="m5">5分</el-radio-button>
                <el-radio-button value="m15">15分</el-radio-button>
                <el-radio-button value="m30">30分</el-radio-button>
                <el-radio-button value="m60">60分</el-radio-button>
                <el-radio-button value="day">日K</el-radio-button>
              </el-radio-group>
            </div>

            <!-- 技术标签 -->
            <div v-if="techTags.length" class="mt8 flex gap" style="flex-wrap:wrap">
              <el-tag v-for="t in techTags" :key="t" size="small" :type="t.type">{{ t.label }}</el-tag>
            </div>

            <!-- 行情数据条 -->
            <div class="flex gap fs12 mt4" style="color:#909399;flex-wrap:wrap">
              <span>今开 {{ fmt(symbolStore.selectedRealtime.open) }}</span>
              <span>最高 {{ fmt(symbolStore.selectedRealtime.high) }}</span>
              <span>最低 {{ fmt(symbolStore.selectedRealtime.low) }}</span>
              <span>成交量 {{ fmtVol(symbolStore.selectedRealtime.volume) }}</span>
              <span>成交额 {{ fmtBig(symbolStore.selectedRealtime.amount) }}</span>
            </div>

            <!-- K线 + 右侧常驻盘口面板 -->
            <div class="main-split">
              <div class="main-left">
            <!-- K线图 -->
            <div style="height:460px">
              <div v-if="period !== 'mf'" style="position:relative;height:100%">
                <HQChartKline :data="kline" height="460px"
                  :fx="period === 'day' ? czsc.fx_list || [] : []"
                  :bi="period === 'day' ? czsc.bi_list || [] : []"
                  :zs="period === 'day' ? czsc.zs_list || [] : []"
                  :signals="period === 'day' ? czsc.signals || [] : []"
                  :stage-points="period === 'day' ? (czsc.stage_points || []) : []" />
                <el-empty v-if="!kline.length" description="暂无该周期K线" :image-size="70" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center" />
              </div>
              <div v-else style="position:relative;height:100%">
                <LineChart v-if="intraday.length" :data="intraday" height="430px" :volume="true"
                  :pre-close="symbolStore.selectedRealtime.prev_close"
                  :signals="intradayFilteredSignals" :show-vwap="!!intradaySignals.length"
                  :show-t="intradayShowT" />
                <el-empty v-else description="暂无分时数据" :image-size="70" style="position:absolute;inset:0" />
                <!-- 分时图工具栏 -->
                <div v-if="intraday.length" class="intraday-toolbar">
                  <el-checkbox v-model="intradayShowSignals" size="small">主力信号</el-checkbox>
                  <el-checkbox v-model="intradayShowT" size="small">做T信号</el-checkbox>
                </div>
                <!-- 主力意图标签 -->
                <div v-if="intradayShowSignals && intradaySummary?.intent" class="intent-bar">
                  <span class="intent-label" :class="'intent-' + (intradaySummary.intent.primary === '真拉升' ? 'rally' : intradaySummary.intent.primary === '诱多' ? 'trap' : intradaySummary.intent.primary === '诱空' ? 'bear' : intradaySummary.intent.primary === '吸筹' ? 'accumulate' : intradaySummary.intent.primary === '洗盘' ? 'shakeout' : 'wait')">
                    {{ intradaySummary.intent.primary }}
                  </span>
                  <span v-if="intradaySummary.intent.confidence > 0" class="fs11" style="color:#606266">{{ intradaySummary.intent.confidence }}%</span>
                  <template v-for="(v, k) in intradaySummary.intent.all_scores" :key="k">
                    <span v-if="v > 10" class="fs11" style="color:#606266">{{ k }}{{ Math.round(v) }}%</span>
                  </template>
                </div>
              </div>
            </div>

            <!-- 个股详情（原多tab整合为一） -->
            <el-tabs v-model="detailTab" class="mt8" type="border-card">
              <el-tab-pane label="个股详情" name="detail" lazy>
                <div v-if="czsc.current_state" class="mb8">
                  <el-tag size="small" :type="czsc.current_state.trend === 'up' ? 'danger' : czsc.current_state.trend === 'down' ? 'success' : 'info'">
                    趋势: {{ czsc.current_state.trend === 'up' ? '多头' : czsc.current_state.trend === 'down' ? '空头' : '震荡' }}
                  </el-tag>
                  <el-tag v-if="czsc.current_state.last_bi_direction" size="small" type="info" class="ml4">
                    最后笔: {{ czsc.current_state.last_bi_direction === 'up' ? '向上' : '向下' }}
                  </el-tag>
                  <span v-if="czsc.engine" class="fs12 ml8" style="color:#909399">引擎: {{ czsc.engine }}</span>
                </div>
                <!-- 养家心法情绪阶段 -->
                <div v-if="czsc.current_state?.yangjia_stage?.stage && czsc.current_state.yangjia_stage.stage !== 'unknown'" class="mb8">
                  <el-divider content-position="left">养家心法情绪阶段</el-divider>
                  <el-tag size="small" :type="yangjiaTag(czsc.current_state.yangjia_stage.stage)">
                    {{ czsc.current_state.yangjia_stage.stage }}
                  </el-tag>
                  <div class="fs12 mt4" style="color:#606266">{{ czsc.current_state.yangjia_stage.description }}</div>
                  <div v-if="czsc.current_state.yangjia_stage.position_pct != null" class="fs11 mt4" style="color:#909399">
                    20日位置: {{ czsc.current_state.yangjia_stage.position_pct }}% ·
                    量比: {{ czsc.current_state.yangjia_stage.vol_ratio }} ·
                    20日涨幅: {{ czsc.current_state.yangjia_stage.chg_20d }}%
                  </div>
                </div>
                <!-- AI分析 -->
                <el-divider content-position="left">AI分析</el-divider>
                <div v-if="isStreaming">
                  <div class="stream-box">{{ streamText }}<span class="stream-cursor"></span></div>
                  <div class="fs11 mt4" style="color:#909399">AI 正在生成分析…</div>
                </div>
                <div v-else-if="brain.agents?.length">
                  <div class="flex gap fs12 mb8" style="flex-wrap:wrap;align-items:center">
                    <span class="flex gap" style="align-items:center">
                      <span>综合建议：</span>
                      <el-tag size="small" :type="overallRatingTag">{{ overallRatingText }}</el-tag>
                    </span>
                    <span class="flex gap" style="flex-wrap:wrap;align-items:center">
                      <el-tooltip v-for="a in agentList" :key="a.agent_type"
                        :content="a.agent_type === 'research' ? '投研智能体 · 点击重新分析' : a.agent_type === 'short_term' ? '短线交易智能体 · 点击重新分析' : '波段操作智能体 · 点击重新分析'"
                        placement="top">
                        <el-button size="small" :loading="brainLoading === a.agent_type" @click="runBrainOne(a.agent_type)"
                          :type="a.agent_type === 'research' ? 'danger' : a.agent_type === 'short_term' ? 'warning' : 'info'"
                          plain>
                          <el-icon style="margin-right:3px"><Refresh /></el-icon>
                          {{ a.agent_type === 'research' ? '投研' : a.agent_type === 'short_term' ? '短线' : '波段' }}
                        </el-button>
                      </el-tooltip>
                    </span>
                  </div>
                  <el-row :gutter="10">
                    <el-col :xs="24" :sm="8" v-for="a in brain.agents" :key="a.agent_type">
                      <div class="brain-card">
                        <div class="flex between" style="align-items:center">
                          <span class="fs13 bold">{{ agentLabel(a.agent_type) }}</span>
                          <el-tag size="small" :type="scoreTag(a)">{{ scoreLabel(a) }}</el-tag>
                        </div>
                        <div class="fs12 mt8 brain-text">{{ a.summary || '暂无结论' }}</div>
                      </div>
                    </el-col>
                  </el-row>
                </div>
                <div v-else>
                  <div class="flex gap mb8" style="align-items:center;flex-wrap:wrap">
                    <span class="fs12" style="color:#909399">选择智能体单独分析：</span>
                    <el-button v-for="a in agentList" :key="a.agent_type" size="small" plain
                      :type="a.agent_type === 'research' ? 'danger' : a.agent_type === 'short_term' ? 'warning' : 'info'"
                      :loading="brainLoading === a.agent_type" @click="runBrainOne(a.agent_type)">
                      {{ a.name || agentLabel(a.agent_type) }}
                    </el-button>
                  </div>
                  <div class="fs11" style="color:#909399">每次只运行所选智能体（避免多智能体并行超时），当日结果自动缓存，可点击重跑</div>
                </div>
                <!-- 布林带 -->
                <div v-if="czsc.current_state?.boll?.mid" class="mb8">
                  <el-divider content-position="left">布林带</el-divider>
                  <div class="fs12">
                    <span>上轨: <b class="down">{{ czsc.current_state.boll.upper }}</b></span>
                    <span class="ml8">中轨: <b>{{ czsc.current_state.boll.mid }}</b></span>
                    <span class="ml8">下轨: <b class="up">{{ czsc.current_state.boll.lower }}</b></span>
                    <span class="ml8">带宽: {{ czsc.current_state.boll.width }}%</span>
                    <el-tag size="small" :type="czsc.current_state.boll.position.includes('上轨') ? 'danger' : czsc.current_state.boll.position.includes('下轨') ? 'success' : 'info'" class="ml4">
                      {{ czsc.current_state.boll.position }}
                    </el-tag>
                  </div>
                </div>
                <!-- RSI -->
                <div v-if="czsc.current_state?.rsi?.rsi6 != null" class="mb8">
                  <el-divider content-position="left">RSI (6/12/24)</el-divider>
                  <div class="fs12">
                    <span>RSI6: <b :class="(czsc.current_state.rsi.rsi6||0) >= 70 ? 'down' : (czsc.current_state.rsi.rsi6||0) <= 30 ? 'up' : ''">{{ czsc.current_state.rsi.rsi6 }}</b></span>
                    <span class="ml8">RSI12: <b :class="(czsc.current_state.rsi.rsi12||0) >= 70 ? 'down' : (czsc.current_state.rsi.rsi12||0) <= 30 ? 'up' : ''">{{ czsc.current_state.rsi.rsi12 }}</b></span>
                    <span class="ml8">RSI24: <b :class="(czsc.current_state.rsi.rsi24||0) >= 70 ? 'down' : (czsc.current_state.rsi.rsi24||0) <= 30 ? 'up' : ''">{{ czsc.current_state.rsi.rsi24 }}</b></span>
                    <el-tag size="small" :type="(czsc.current_state.rsi.superposition||'').includes('超') ? 'danger' : 'info'" class="ml4">{{ czsc.current_state.rsi.superposition }}</el-tag>
                    <el-tag v-if="czsc.current_state.rsi.cross && czsc.current_state.rsi.cross !== '—'" size="small" :type="(czsc.current_state.rsi.cross||'').includes('金叉') ? 'danger' : 'success'" class="ml4">{{ czsc.current_state.rsi.cross }}</el-tag>
                  </div>
                </div>
                <!-- 板块 -->
                <div v-if="sectorDetail.industry || (sectorDetail.concepts||[]).length" class="mb8">
                  <el-divider content-position="left">板块</el-divider>
                  <el-tag size="small" type="warning" style="margin:2px">行业: {{ sectorDetail.industry }}</el-tag>
                  <el-tag v-for="c in (sectorDetail.concepts||[])" :key="c" size="small" type="info" style="margin:2px">{{ c }}</el-tag>
                </div>
                <!-- 主力控盘度 -->
                <div v-if="czsc.current_state?.control?.score != null" class="mb8">
                  <el-divider content-position="left">主力控盘度</el-divider>
                  <div class="flex gap" style="align-items:center;flex-wrap:wrap">
                    <el-progress type="dashboard" :percentage="Math.round(czsc.current_state.control.score)" :width="70" :stroke-width="8"
                      :color="czsc.current_state.control.score >= 60 ? '#ef232a' : czsc.current_state.control.score >= 40 ? '#f59e0b' : '#909399'">
                      <template #default="{ percentage }"><span class="fs11">{{ percentage }}</span></template>
                    </el-progress>
                    <div>
                      <el-tag size="small" :type="czsc.current_state.control.score >= 60 ? 'danger' : czsc.current_state.control.score >= 40 ? 'warning' : 'info'">
                        {{ czsc.current_state.control.level }}
                      </el-tag>
                      <div class="fs12 mt4" style="color:#606266">{{ czsc.current_state.control.description }}</div>
                      <div class="fs11 mt4" style="color:#909399">日均振幅 {{ czsc.current_state.control.amp }}% · 涨跌量比 {{ czsc.current_state.control.vol_ratio }}</div>
                    </div>
                  </div>
                </div>
                <!-- 量价口诀信号 -->
                <div v-if="(czsc.mnemonic_tags || []).length" class="mb8">
                  <el-divider content-position="left">量价口诀信号</el-divider>
                  <div class="flex gap" style="flex-wrap:wrap">
                    <el-tooltip v-for="(t, i) in czsc.mnemonic_tags" :key="i" :content="t.desc" placement="top">
                      <el-tag size="small" :type="(t.type || 'info').replace('danger', 'danger').replace('success', 'success')" :style="{ cursor: 'pointer' }">
                        {{ t.label }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                  <div class="fs11 mt4" style="color:#909399;line-height:1.6">来源：量价操作口诀（网上搜集，仅作辅助判断，非确定性信号）</div>
                </div>
                <!-- 三买三卖信号 -->
                <div v-if="threeSignals.length" class="mb8">
                  <el-divider content-position="left">三买三卖信号</el-divider>
                  <el-tag v-for="(sg, i) in threeSignals" :key="i" size="small"
                    :type="sg.type === 'buy' ? 'success' : 'danger'" style="margin:2px">
                    {{ sg.signal_type }} {{ sg.time }} <span class="fs11">{{ sg.reason }}</span>
                  </el-tag>
                </div>
                <!-- 分型 -->
                <div v-if="czsc.fx_list?.length" class="mb8">
                  <el-divider content-position="left">分型 (最近10)</el-divider>
                  <el-tag v-for="fx in czsc.fx_list.slice(-10)" :key="fx.dt" size="small"
                    :type="fx.mark === 'g' ? 'danger' : 'success'" style="margin:2px">
                    {{ fx.dt }} {{ fx.type }} {{ fx.price }}
                  </el-tag>
                </div>
                <el-empty v-if="!czsc.fx_list?.length && !czsc.signals?.length" description="切换到日K查看缠论信号" :image-size="40" />
                <el-divider content-position="left">消息面</el-divider>
                <div v-if="stockNews.length" style="max-height:260px;overflow:auto">
                  <div v-for="(n, i) in stockNews" :key="i" class="fs12 mb6" style="line-height:1.5">
                    <el-tag size="small" :type="n.sentiment === 'positive' ? 'danger' : n.sentiment === 'negative' ? 'success' : 'info'" style="flex-shrink:0">
                      {{ n.sentiment === 'positive' ? '利好' : n.sentiment === 'negative' ? '利空' : '中性' }}
                    </el-tag>
                    <a v-if="n.url" :href="n.url" target="_blank" rel="noopener" class="ml4">{{ n.title }}</a>
                    <span v-else class="ml4">{{ n.title }}</span>
                  </div>
                </div>
                <el-empty v-else description="暂无相关新闻" :image-size="40" />
                <el-divider content-position="left">资金流</el-divider>
                <div v-if="flowSummary || moneyFlow.length" class="fs12">
                  <div class="flex gap mb8" style="flex-wrap:wrap;align-items:center">
                    <span>1日主力: <b :class="(flowSummary.net_1d||0) >= 0 ? 'up' : 'down'">{{ fmtBig(flowSummary.net_1d * 1e8) }}</b></span>
                    <span>5日主力: <b :class="(flowSummary.net_5d||0) >= 0 ? 'up' : 'down'">{{ fmtBig(flowSummary.net_5d * 1e8) }}</b></span>
                    <span>20日主力: <b :class="(flowSummary.net_20d||0) >= 0 ? 'up' : 'down'">{{ fmtBig(flowSummary.net_20d * 1e8) }}</b></span>
                    <el-tag v-if="flowSummary.trend" size="small" type="info">
                      {{ flowSummary.trend === 'inflow' ? '持续流入' : flowSummary.trend === 'outflow' ? '持续流出' : '方向反复' }}
                    </el-tag>
                    <span v-if="flowSummary.latest_date" class="fs11" style="color:#c0c4cc">截至 {{ flowSummary.latest_date }}</span>
                  </div>
                  <div class="mb8">
                    <div class="fs11 mb4" style="color:#909399">近20个交易日主力当日净流入（单位：万元）</div>
                    <LineChart v-if="moneyFlow.length"
                      :data="moneyFlow.map(m => ({ name: String(m.date).slice(5), value: Math.round((Number(m.netamount) || 0) / 1e4) }))"
                      height="160px" :area="false" :colors="['#ef232a']" />
                  </div>
                  <div v-if="moneyFlow.length" style="max-height:200px;overflow:auto">
                    <el-table :data="moneyFlow.slice(0, 10)" size="small" :show-header="true">
                      <el-table-column prop="date" label="日期" width="90" />
                      <el-table-column label="当日主力净流入" align="right">
                        <template #default="{ row }">
                          <span :class="(row.netamount||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.netamount) }}</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="5日/20日累计(亿)" align="right" width="150">
                        <template #default="{ row }">
                          <span class="fs11"><b :class="(row.net_5d||0) >= 0 ? 'up' : 'down'">{{ row.net_5d }}</b> / <b :class="(row.net_20d||0) >= 0 ? 'up' : 'down'">{{ row.net_20d }}</b></span>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
                <el-empty v-else description="暂无资金流数据" :image-size="40" />
                <el-divider content-position="left">技术形态</el-divider>
                <div v-if="forms.length" class="fs12">
                  <el-tag v-for="(f, i) in forms" :key="i" size="small" :type="f.type === 'bullish' ? 'danger' : f.type === 'bearish' ? 'success' : 'info'" style="margin:2px">
                    {{ f.name }}: {{ f.description || f.signal }}
                  </el-tag>
                </div>
                <el-empty v-else description="暂无技术形态" :image-size="40" />
                <el-divider content-position="left">财务（业绩）</el-divider>
                <div v-if="finOverview?.available" class="fs12">
                  <div class="flex gap mb8" style="flex-wrap:wrap">
                    <el-tag size="small" :type="finOverview.market_cap_class === '大盘' ? 'danger' : finOverview.market_cap_class === '中盘' ? 'warning' : 'info'">
                      {{ finOverview.market_cap_class }}
                    </el-tag>
                    <span>总市值: <b>{{ fmtBig(finOverview.total_mv * 1e8) }}</b></span>
                    <span>流通: {{ fmtBig(finOverview.float_mv * 1e8) }}</span>
                    <span>市盈率(PE): <b>{{ finOverview.pe }}</b></span>
                    <span>市净率(PB): <b>{{ finOverview.pb }}</b></span>
                    <span>换手率: {{ finOverview.turnover }}%</span>
                    <span>振幅: {{ finOverview.amplitude }}%</span>
                  </div>
                  <div class="fs11" style="color:#909399">数据来源：{{ finOverview.quote_source }}</div>
                </div>
                <div v-if="financial.length" style="max-height:240px;overflow:auto" class="mt8">
                  <el-table :data="financial" size="small">
                    <el-table-column prop="report_date" label="报告期" width="100" />
                    <el-table-column label="营收" align="right" width="90"><template #default="{ row }">{{ fmtBig(row.revenue) }}</template></el-table-column>
                    <el-table-column label="营收同比" align="right" width="80"><template #default="{ row }"><span :class="pctClsObj(row.revenue_yoy)">{{ row.revenue_yoy == null ? '-' : row.revenue_yoy + '%' }}</span></template></el-table-column>
                    <el-table-column label="净利润" align="right" width="90"><template #default="{ row }">{{ fmtBig(row.net_profit) }}</template></el-table-column>
                    <el-table-column label="净利同比" align="right" width="80"><template #default="{ row }"><span :class="pctClsObj(row.net_profit_yoy)">{{ row.net_profit_yoy == null ? '-' : row.net_profit_yoy + '%' }}</span></template></el-table-column>
                    <el-table-column label="毛利率" align="right" width="70"><template #default="{ row }">{{ row.gross_margin == null ? '-' : row.gross_margin + '%' }}</template></el-table-column>
                    <el-table-column label="ROE(W)" align="right" width="76"><template #default="{ row }">{{ row.roe == null ? '-' : row.roe + '%' }}</template></el-table-column>
                    <el-table-column label="EPS" align="right" width="64"><template #default="{ row }">{{ row.eps ?? '-' }}</template></el-table-column>
                    <el-table-column label="每股净资产" align="right" width="86"><template #default="{ row }">{{ row.bps ?? '-' }}</template></el-table-column>
                    <el-table-column label="每股经营现金流" align="right" width="104"><template #default="{ row }">{{ row.ocf_per_share ?? '-' }}</template></el-table-column>
                    <el-table-column label="分红方案" min-width="100"><template #default="{ row }">{{ row.assign || '-' }}</template></el-table-column>
                  </el-table>
                </div>
                <el-empty v-else-if="!finOverview?.available" description="暂无财务数据" :image-size="40" />
                <div v-if="(industryRanking?.available || industryChain?.industry || (industryChain?.concepts||[]).length)">
                  <el-divider content-position="left">行业对比 / 排名</el-divider>
                  <div v-if="industryRanking?.available" class="fs12">
                    <div class="mb8">行业：<b>{{ industryRanking.industry }}</b>（同行业 {{ industryRanking.peers_count }} 家 · 东方财富季度财报）</div>
                    <div class="flex gap mb8" style="flex-wrap:wrap">
                      <el-tag size="small" type="warning">净利增速排名 {{ industryRanking.target?.rank_by_growth ?? '-' }}/{{ industryRanking.target?.total_by_growth ?? '-' }}</el-tag>
                      <el-tag size="small" type="danger">ROE排名 {{ industryRanking.target?.rank_by_roe ?? '-' }}/{{ industryRanking.target?.total_by_roe ?? '-' }}</el-tag>
                      <el-tag size="small" type="info">行业净利增速中位数 {{ industryRanking.median_growth == null ? '-' : industryRanking.median_growth + '%' }}</el-tag>
                      <el-tag size="small" type="info">行业ROE中位数 {{ industryRanking.median_roe == null ? '-' : industryRanking.median_roe + '%' }}</el-tag>
                    </div>
                    <div class="fs11 mb4" style="color:#909399">同行净利增速 TOP5（点击跳转）</div>
                    <el-table :data="(industryRanking.top_growth || []).slice(0, 5)" size="small" @row-click="(r) => goRowStock(r.code)">
                      <el-table-column prop="name" label="名称" width="100" />
                      <el-table-column prop="code" label="代码" width="84" />
                      <el-table-column label="净利同比" align="right"><template #default="{ row }"><span :class="pctClsObj(row.net_profit_yoy)">{{ row.net_profit_yoy }}%</span></template></el-table-column>
                      <el-table-column label="ROE" align="right" width="70"><template #default="{ row }">{{ row.roe }}%</template></el-table-column>
                    </el-table>
                  </div>
                  <div v-else class="fs12" style="color:#909399">行业对比暂不可用（网络受限）</div>
                  <el-divider content-position="left">产业链</el-divider>
                  <div v-if="industryChain?.industry" class="fs12 mb8">
                    <div class="mb4"><b>{{ industryChain.industry.name }}</b>（{{ industryChain.industry.code }}）</div>
                    <div class="flex gap" style="flex-wrap:wrap;align-items:center">
                      <el-tag size="small" :type="(industryChain.industry.change_pct||0) >= 0 ? 'danger' : 'success'">
                        {{ industryChain.industry.change_pct == null ? '-' : ((industryChain.industry.change_pct >= 0 ? '+' : '') + industryChain.industry.change_pct + '%') }}
                      </el-tag>
                      <span>主力净流入 <b :class="pctClsObj(industryChain.industry.net_inflow)">{{ industryChain.industry.net_inflow ?? '-' }}亿</b></span>
                      <span>净占比 {{ industryChain.industry.net_ratio ?? '-' }}%</span>
                      <span>成交 {{ industryChain.industry.amount ?? '-' }}亿</span>
                      <el-link v-if="industryChain.industry.leader_symbol" type="primary" :underline="false" style="font-size:12px" @click="goStockByCode(industryChain.industry.leader_symbol)">领涨 {{ industryChain.industry.leader }}</el-link>
                    </div>
                    <div v-if="(industryChain.peers || []).length" class="mt8">
                      <div class="fs11 mb4" style="color:#909399">板块市值 TOP10（市值龙头/龙二/龙三，点击跳转）</div>
                      <el-table :data="industryChain.peers.slice(0, 8)" size="small" @row-click="(r) => goStockByCode(r.symbol)">
                        <el-table-column prop="name" label="名称" width="90" />
                        <el-table-column prop="symbol" label="代码" width="78" />
                        <el-table-column label="角色" width="66"><template #default="{ row }"><el-tag :type="row.role === '市值龙头' ? 'danger' : row.role === '龙二' ? 'warning' : 'info'" size="small">{{ row.role || '-' }}</el-tag></template></el-table-column>
                        <el-table-column label="市值(亿)" align="right" width="70"><template #default="{ row }">{{ row.mkt_cap }}</template></el-table-column>
                        <el-table-column label="涨幅%" align="right" width="66"><template #default="{ row }"><span :class="pctClsObj(row.change_pct)">{{ row.change_pct == null ? '-' : (row.change_pct >= 0 ? '+' : '') + row.change_pct + '%' }}</span></template></el-table-column>
                        <el-table-column label="主力净(亿)" align="right" width="80"><template #default="{ row }"><span :class="pctClsObj(row.net_inflow)">{{ row.net_inflow ?? '-' }}</span></template></el-table-column>
                      </el-table>
                    </div>
                  </div>
                  <div v-if="(industryChain?.concepts || []).length" class="fs12 mt8">
                    <div class="fs11 mb4" style="color:#909399">所属概念板块</div>
                    <div class="concept-grid">
                      <div v-for="c in industryChain.concepts.slice(0, 10)" :key="c.code" class="concept-item">
                        <span class="fs12 bold">{{ c.name }}</span>
                        <div class="fs12 mt4">
                          <el-tag size="small" :type="(c.change_pct||0) >= 0 ? 'danger' : 'success'">{{ c.change_pct == null ? '-' : (c.change_pct >= 0 ? '+' : '') + c.change_pct + '%' }}</el-tag>
                          <span class="ml4">主力 <b :class="pctClsObj(c.net_inflow)">{{ c.net_inflow ?? '-' }}亿</b></span>
                          <el-link v-if="c.leader_symbol" type="primary" :underline="false" style="font-size:12px;margin-left:4px" @click="goStockByCode(c.leader_symbol)">{{ c.leader }}</el-link>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </el-tab-pane>
            </el-tabs>
              </div>

              <!-- 右侧常驻盘口面板 -->
              <div class="side-panel">
                <div class="quote-block">
                  <div class="quote-title">五档挂单 <span class="fs11" style="color:#909399">单位:手</span></div>
                  <div class="order-grid">
                    <div v-for="i in 5" :key="i" class="order-row" :class="{ 'row-hl': (askBook[i-1] && askBook[i-1].__hl) || (bidBook[i-1] && bidBook[i-1].__hl) }">
                      <span class="fs11" style="color:#909399">卖{{ i }}</span>
                      <span v-if="askBook[i-1]" class="mono down fs11">{{ fmt(askBook[i-1].price) }}</span>
                      <span v-else class="mono fs11" style="color:#c0c4cc">-</span>
                      <span class="mono fs11" style="text-align:right">{{ askBook[i-1] ? askBook[i-1].volume : '-' }}</span>
                      <span class="fs11" style="color:#dcdfe6;text-align:center">│</span>
                      <span class="mono fs11" style="text-align:right">{{ bidBook[i-1] ? bidBook[i-1].volume : '-' }}</span>
                      <span v-if="bidBook[i-1]" class="mono up fs11">{{ fmt(bidBook[i-1].price) }}</span>
                      <span v-else class="mono fs11" style="color:#c0c4cc">-</span>
                      <span class="fs11" style="color:#909399;text-align:right">买{{ i }}</span>
                    </div>
                  </div>
                  <div v-if="!bidBook.some(b => b) && !askBook.some(a => a)" class="fs12 mt8" style="color:#909399">暂无五档挂单（非交易时段或免费源不可用）</div>
                </div>

                <div class="quote-block">
                  <div class="quote-title">逐笔成交 <span class="fs11" style="color:#909399">滚动递增</span></div>
                  <div ref="ticksScroller" class="ticks-list">
                    <div v-for="t in ticksIncremental" :key="tickKey(t)" class="ticks-row" :class="{ 'row-hl': t.__hl }">
                      <span class="mono">{{ t.time }}</span>
                      <span class="mono" :class="priceCls(Number(t.price))">{{ fmt(t.price) }}</span>
                      <span class="mono" :class="pctClsObj(t.change)">{{ t.change == null ? '-' : ((t.change >= 0 ? '+' : '') + t.change) }}</span>
                      <span class="mono" style="text-align:right">{{ t.volume }}</span>
                      <el-tag size="small" :type="sideTag(t.side)">{{ sideText(t.side) }}</el-tag>
                    </div>
                  </div>
                  <el-empty v-if="!ticksIncremental.length" description="暂无成交明细（非交易时段）" :image-size="40" />
                </div>
              </div>
            </div>

            <div v-if="symbolStore.selectedSymbol" class="mt8 flex gap">
              <el-popconfirm title="确认移除？" @confirm="removeSelected">
                <template #reference>
                  <el-button size="small" type="danger" plain>移除自选</el-button>
                </template>
              </el-popconfirm>
            </div>
              </div>
          </div>
          <div v-else class="card" style="text-align:center;padding:60px 0;color:#909399">
            选择左侧股票查看详情
          </div>
        </el-col>
      </el-row>

      <!-- 添加股票 -->
      <el-dialog v-model="searchDialog" title="添加自选股" width="480">
        <el-input v-model="searchKw" placeholder="输入股票名称或代码" @keyup.enter="doSearch">
          <template #append><el-button @click="doSearch">搜索</el-button></template>
        </el-input>
        <el-table v-if="searchResults.length" :data="searchResults" size="small" class="mt16" @row-click="addStock">
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="symbol" label="代码" width="120" />
          <el-table-column label="" width="80">
            <template #default><el-button size="small" type="primary" link>添加</el-button></template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="searched" description="未找到匹配股票" :image-size="60" />
      </el-dialog>

      <!-- 新建分组 -->
      <el-dialog v-model="addGroupDialog" title="新建分组" width="360">
        <el-input v-model="newGroupName" placeholder="请输入分组名称" @keyup.enter="confirmAddGroup" />
        <template #footer>
          <el-button @click="addGroupDialog = false">取消</el-button>
          <el-button type="primary" @click="confirmAddGroup" :disabled="!newGroupName.trim()">确定</el-button>
        </template>
      </el-dialog>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Close } from '@element-plus/icons-vue'
import MainLayout from '../layout/MainLayout.vue'
import HQChartKline from '../components/HQChartKline.vue'
import LineChart from '../components/LineChart.vue'
import { watchlistApi, stockApi, marketApi, agentApi } from '../api'
import { useSymbolStore } from '../stores/symbol'

const route = useRoute()
const groups = ref([])
const currentGroupId = ref(null)
const loading = ref(false)
const searchKw = ref('')
const searchResults = ref([])
const searched = ref(false)
const searchDialog = ref(false)
const addGroupDialog = ref(false)
const newGroupName = ref('')
const symbolStore = useSymbolStore()
const VALID_PERIODS = ['mf', 'm5', 'm15', 'm30', 'm60', 'day']
const period = ref('day')
const kline = ref([])
const intraday = ref([])
const intradaySignals = ref([])
const intradaySummary = ref(null)
const intradayShowSignals = ref(false)
const intradayShowT = ref(false)
const intradayFilteredSignals = computed(() => {
  if (!intradaySignals.value.length) return []
  return intradaySignals.value.filter(s => {
    const isT = s.type === 't_buy' || s.type === 't_sell'
    if (isT) return intradayShowT.value
    return intradayShowSignals.value
  })
})
const czsc = ref({})
const stockNews = ref([])
const forms = ref([])
const financial = ref([])
const finOverview = ref(null)
const moneyFlow = ref([])
const flowSummary = ref(null)
const sectorDetail = ref({})
const industryRanking = ref(null)
const industryChain = ref(null)
const brain = ref({})
const brainLoading = ref(false)
const streamText = ref('')
const isStreaming = ref(false)
const agentList = ref([])
const detailTab = ref('detail')
const bidBook = ref([])
const askBook = ref([])
const ticksIncremental = ref([])
const ticksScroller = ref(null)
const showRecent = ref(false)
const recentList = ref([])
const recentPriceMap = ref({})
const recentLoading = ref(false)
const batchMode = ref(false)
const selectedForDelete = ref([])

const RECENT_KEY = 'recent_viewed'
const GROUP_STATE_KEY = 'watchlist_tab_state'
const MAX_RECENT = 30
const agentLabels = { research: '投研', short_term: '短线', swing: '波段' }

function agentLabel(t) { return agentLabels[t] || t }
function scoreOf(a) { return a?.score ?? null }
function scoreLabel(a) { const s = scoreOf(a); return s == null ? '暂无' : Number(s).toFixed(1) }
function scoreTag(a) { const s = scoreOf(a); return s == null ? 'info' : s >= 7 ? 'danger' : s >= 4 ? 'warning' : 'success' }
function yangjiaTag(stage) {
  const map = { '吸筹': 'warning', '洗盘': 'info', '拉升': 'danger', '出货': 'success' }
  return map[stage] || 'info'
}
const threeSignals = computed(() => (czsc.value.signals || []).filter(s => s.signal_type?.includes('买') || s.signal_type?.includes('卖')))

const overallRatingText = computed(() => {
  const scores = (brain.value.agents || []).map(a => scoreOf(a)).filter(s => s != null)
  if (!scores.length) return '待评估'
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length
  return avg >= 7 ? '偏多' : avg >= 4 ? '中性' : '偏空'
})
const overallRatingTag = computed(() => {
  const scores = (brain.value.agents || []).map(a => scoreOf(a)).filter(s => s != null)
  if (!scores.length) return 'info'
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length
  return avg >= 7 ? 'danger' : avg >= 4 ? 'warning' : 'success'
})

const techTags = computed(() => {
  const tags = []
  const s = symbolStore.selectedRealtime
  if (!s || !s.price) return tags
  const pct = Number(s.change_pct || 0)
  const last = kline.value[kline.value.length - 1]
  const prev = kline.value[kline.value.length - 2]
  const todayCls = { open: last?.open, close: last?.close, high: last?.high, low: last?.low, volume: last?.volume }
  const prevVol = prev ? Number(prev.volume || 0) : 0
  if (pct >= 5) tags.push({ label: '强势', type: 'danger' })
  else if (pct >= 2) tags.push({ label: '偏强', type: 'warning' })
  else if (pct <= -5) tags.push({ label: '弱势', type: 'success' })
  else if (pct <= -2) tags.push({ label: '偏弱', type: 'info' })
  if (czsc.value?.current_state?.trend === 'up') tags.push({ label: '多头排列', type: 'danger' })
  else if (czsc.value?.current_state?.trend === 'down') tags.push({ label: '空头排列', type: 'success' })

  // 竞价抢筹：低开/平开后放量快速翻红拉升（开盘跳空高开+较前日放量）
  if (todayCls.open && prev && todayCls.open > prev.close * 1.03 && prevVol > 0 && Number(todayCls.volume || 0) > prevVol * 1.3) {
    tags.push({ label: '竞价抢筹', type: 'danger' })
  }
  // 猛烈打压：放量深跌（跌超5%且量能放大1.5倍）
  if (pct <= -5 && prevVol > 0 && Number(todayCls.volume || 0) > prevVol * 1.5) {
    tags.push({ label: '猛烈打压', type: 'success' })
  }
  // 吸筹/诱多/诱空/洗盘 依赖日K + 养家情绪阶段
  const stage = czsc.value?.current_state?.yangjia_stage?.stage
  const subtype = czsc.value?.current_state?.yangjia_stage?.subtype
  if (stage === '吸筹') tags.push({ label: '低位吸筹', type: 'warning' })
  else if (stage === '洗盘') tags.push({ label: '拉升洗盘', type: 'info' })
  else if (stage === '拉升') tags.push(subtype === '主升加速' ? { label: '主升浪', type: 'danger' } : { label: '放量拉升', type: 'danger' })
  else if (stage === '出货') tags.push({ label: '高位出货', type: 'success' })
  // 诱多：高开冲高回落长上影
  if (todayCls.open && todayCls.close && todayCls.high && prev &&
      todayCls.open > prev.close * 1.02 && (todayCls.high - todayCls.close) > (todayCls.close - todayCls.open) && todayCls.close < todayCls.open) {
    tags.push({ label: '冲高回落', type: 'success' })
  }
  // 诱空：低开探底回升长下影放量
  if (todayCls.open && todayCls.close && todayCls.low && prev &&
      todayCls.open < prev.close * 0.98 && (todayCls.close - todayCls.low) > (todayCls.open - todayCls.close) && todayCls.close > todayCls.open && prevVol > 0 && Number(todayCls.volume || 0) > prevVol * 1.3) {
    tags.push({ label: '探底回升', type: 'danger' })
  }
  return tags
})

function loadRecent() {
  try { recentList.value = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { recentList.value = [] }
}

function addToRecent(symbol, name) {
  let list = recentList.value.filter(r => r.symbol !== symbol)
  list.unshift({ symbol, name: name || symbol, ts: Date.now() })
  if (list.length > MAX_RECENT) list = list.slice(0, MAX_RECENT)
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  recentList.value = list
}

const currentGroup = computed(() => groups.value.find(g => g.id === currentGroupId.value) || { items: [] })
const displayItems = computed(() => {
  if (showRecent.value) {
    return recentList.value.map(r => ({ ...r, price: recentPriceMap.value[r.symbol]?.price, change_pct: recentPriceMap.value[r.symbol]?.change_pct }))
  }
  return currentGroup.value.items || []
})

function fmt(v) { return v == null || v === '' ? '-' : Number(v).toFixed(2) }
function fmtVol(v) { if (v == null) return '-'; const n = Number(v); return n >= 1e8 ? (n / 1e8).toFixed(2) + '亿手' : n >= 1e4 ? (n / 1e4).toFixed(2) + '万手' : n.toFixed(0) }
function fmtBig(v) { if (v == null) return '-'; const n = Number(v); return n >= 1e8 ? (n / 1e8).toFixed(2) + '亿' : n >= 1e4 ? (n / 1e4).toFixed(2) + '万' : n.toFixed(0) }
function pctCls(row) { return (row.change_pct || 0) >= 0 ? 'up' : 'down' }
function pctClsObj(v) { return Number(v || 0) >= 0 ? 'up' : 'down' }
function priceCls(p) {
  const prev = symbolStore.selectedRealtime?.prev_close
  if (prev == null) return 'flat'
  return Number(p) > prev ? 'up' : Number(p) < prev ? 'down' : 'flat'
}
function sideText(s) { return s === 'B' ? '买' : s === 'S' ? '卖' : '中性' }
function sideTag(s) { return s === 'B' ? 'danger' : s === 'S' ? 'success' : 'info' }
function tickKey(t) {
  return t.time + '|' + t.price + '|' + t.side
}

function applyOrderBookIncremental(p) {
  const bid = p?.order_book?.bid || []
  const ask = p?.order_book?.ask || []
  const applyBook = (book, rows) => {
    const changed = []
    for (let i = 0; i < 5; i++) {
      const raw = rows[i]
      if (raw) {
        const prev = book[i]
        if (!prev || Number(prev.price) !== Number(raw.price)) {
          book[i] = { level: i + 1, price: raw.price, volume: raw.volume, __hl: true }
          changed.push(book[i])
        } else if (Number(prev.volume) !== Number(raw.volume)) {
          prev.volume = raw.volume
        }
      } else {
        book[i] = null
      }
    }
    return changed
  }
  const changed = [...applyBook(bidBook.value, bid), ...applyBook(askBook.value, ask)]
  if (changed.length) setTimeout(() => changed.forEach(x => { x.__hl = false }), 1000)
}

function applyTicksIncremental(p) {
  const fresh = p?.ticks || []
  if (!fresh.length) return
  const rows = ticksIncremental.value
  const had = rows.length > 0
  const scroller = ticksScroller.value
  const prevH = had && scroller ? scroller.scrollHeight : null
  const seen = new Set(rows.map(tickKey))
  const added = []
  for (const t of fresh) {
    const k = tickKey(t)
    if (!seen.has(k)) {
      seen.add(k)
      const obj = Object.assign({}, t, had ? { __hl: true } : {})
      rows.push(obj)
      added.push(obj)
    }
  }
  if (!added.length) return
  if (had && prevH != null) scrollTicksToSeam(prevH)
  if (had) setTimeout(() => added.forEach(x => { x.__hl = false }), 1000)
}

function scrollTicksToSeam(prevH) {
  requestAnimationFrame(() => {
    const el = ticksScroller.value
    if (!el || prevH == null) return
    const clientH = el.clientHeight
    const atBottom = el.scrollTop + clientH >= prevH - 1
    el.scrollTop = Math.max(0, atBottom ? el.scrollHeight - clientH : prevH - clientH)
  })
}

async function loadQuotePanel() {
  const sym = symbolStore.selectedSymbol
  if (!sym) return
  try {
    const p = await stockApi.quotePanel(sym)
    applyOrderBookIncremental(p)
    applyTicksIncremental(p)
  } catch { /* 保留已有增量数据 */ }
}
function goStockByCode(code) {
  if (!code) return
  const sym = String(code).toUpperCase().replace(/^\D+/, '')
  const full = sym.length === 6 ? fullSymbol(sym) : code
  loadWithSymbol(full)
}
function fullSymbol(sym) {
  if (sym.startsWith('6') || sym.startsWith('900')) return 'SH' + sym
  if (sym.startsWith('0') || sym.startsWith('3') || sym.startsWith('200')) return 'SZ' + sym
  return 'BJ' + sym
}
function goRowStock(code) { goStockByCode(code) }

async function loadRecentPrices() {
  const syms = (recentList.value || []).map(r => r.symbol)
  if (!recentList.value.length) return
  if (recentLoading.value) return
  recentLoading.value = true
  try {
    const r = await marketApi.realtime({ symbols: syms.join(',') })
    const arr = Array.isArray(r) ? r : (r?.data || [])
    const map = {}
    arr.forEach(x => {
      if (x?.symbol) map[x.symbol] = x
    })
    recentPriceMap.value = map
  } catch { recentPriceMap.value = {} } finally { recentLoading.value = false }
}

function showRecentViewed() {
  showRecent.value = true
  symbolStore.clear()
  batchMode.value = false
  selectedForDelete.value = []
  loadRecentPrices()
}

function selectGroup(id) {
  showRecent.value = false
  currentGroupId.value = id
  symbolStore.clear()
  const first = (groups.value.find(g => g.id === id)?.items || [])[0]
  if (first) selectItem(first)
}

function selectItem(row) {
  batchMode.value = false
  selectedForDelete.value = []
  symbolStore.select(row.symbol, { name: row.name, price: row.price, change_pct: row.change_pct, change: row.change, ...row })
  addToRecent(row.symbol, row.name)
  detailTab.value = 'detail'
  loadKline()
  loadStockDetail()
}

async function loadStockDetail() {
  const sym = symbolStore.selectedSymbol
  if (!sym) return
  const [basic, czscData, formData, finData, finOv, flowData, fsData, nzData, secData, rankData, chainData] = await Promise.allSettled([
    stockApi.basic(sym), stockApi.czsc(sym), stockApi.forms(sym),
    stockApi.financial(sym), stockApi.financialOverview(sym), stockApi.moneyFlow(sym), stockApi.moneyFlowSummary(sym),
    stockApi.news(sym), stockApi.sector(sym),
    stockApi.industryRanking(sym), stockApi.industryChain(sym),
  ])
  if (basic.status === 'fulfilled' && basic.value) {
    symbolStore.updateRealtime({ ...basic.value.realtime, name: basic.value.name || symbolStore.selectedRealtime.name })
  }
  if (czscData.status === 'fulfilled') czsc.value = czscData.value || {}
  if (formData.status === 'fulfilled') forms.value = formData.value || []
  if (finData.status === 'fulfilled') financial.value = finData.value || []
  if (finOv.status === 'fulfilled') finOverview.value = finOv.value || null
  if (flowData.status === 'fulfilled') moneyFlow.value = flowData.value || []
  if (fsData.status === 'fulfilled') flowSummary.value = fsData.value || null
  if (nzData.status === 'fulfilled') stockNews.value = nzData.value || []
  if (secData.status === 'fulfilled') sectorDetail.value = secData.value || {}
  if (rankData.status === 'fulfilled') industryRanking.value = rankData.value || null
  if (chainData.status === 'fulfilled') industryChain.value = chainData.value || null
}

let _klineLoading = false
let _klineSeq = 0
async function loadKline() {
  const sym = symbolStore.selectedSymbol
  if (!sym || _klineLoading) return
  _klineLoading = true
  const seq = ++_klineSeq
  // 先清空旧数据，避免切换个股时旧图表残留
  intraday.value = []
  intradaySignals.value = []
  intradaySummary.value = null
  kline.value = []
  try {
    if (period.value === 'mf') {
      let preClose = symbolStore.selectedRealtime?.prev_close || 0
      if (!preClose) {
        try {
          const b = await stockApi.basic(sym)
          if (b?.realtime?.prev_close) {
            preClose = b.realtime.prev_close
            symbolStore.updateRealtime(b.realtime)
          }
        } catch {}
      }
      const r = await marketApi.intradayAnalysis({ symbol: sym, pre_close: preClose })
      if (seq !== _klineSeq) return
      intraday.value = r.bars || []
      intradaySignals.value = [...(r.signals || []), ...(r.t_signals || [])]
      intradaySummary.value = r.summary || null
      return
    }
    const r = await stockApi.kline(sym, { period: period.value })
    if (seq !== _klineSeq) return
    const newData = r.data || []
    const old = kline.value
    if (old.length > 0 && newData.length > 0 && Math.abs(old.length - newData.length) <= 3) {
      const minLen = Math.min(old.length, newData.length)
      for (let i = 0; i < minLen; i++) {
        if (old[i].dt === newData[i].dt) {
          old[i].open = newData[i].open
          old[i].high = newData[i].high
          old[i].low = newData[i].low
          old[i].close = newData[i].close
          old[i].volume = newData[i].volume
        }
      }
      if (newData.length > old.length) {
        for (let i = old.length; i < newData.length; i++) old.push(newData[i])
      }
    } else {
      kline.value = newData
    }
  } catch (e) { console.warn('loadKline error:', e) } finally { _klineLoading = false }
}

async function loadBrain() {
  const sym = symbolStore.selectedSymbol
  if (!sym) return
  try { brain.value = (await agentApi.brainstormGet(sym)) || {} } catch { brain.value = {} }
}

async function runBrainOne(at) {
  const sym = symbolStore.selectedSymbol
  if (!at || !sym || isStreaming.value) return
  brainLoading.value = at
  isStreaming.value = true
  streamText.value = ''
  const prev = brain.value.agents || []
  try {
    const resp = await agentApi.brainstormOneStream(sym, at)
    if (!resp.body) throw new Error('no stream body')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const ev = JSON.parse(line.slice(6))
          if (ev.type === 'delta') {
            streamText.value += ev.text
          } else if (ev.type === 'done') {
            if (symbolStore.selectedSymbol === sym) {
              brain.value = { symbol: sym, agents: [...prev.filter(a => a.agent_type !== at), ev.result] }
            }
          } else if (ev.type === 'error') {
            try { ElMessage.warning(`分析失败：${ev.message}`) } catch {}
          }
        } catch {}
      }
    }
  } catch (e) {
    try { ElMessage.warning(`智能体分析失败，请稍后重试 (${agentLabel(at)})`) } catch {}
  } finally {
    isStreaming.value = false
    brainLoading.value = false
  }
}

async function loadAgentList() {
  try {
    const order = ['research', 'short_term', 'swing']
    const list = await agentApi.list()
    const row = Array.isArray(list) ? list : (list?.data || [])
    agentList.value = order
      .map(t => {
        const c = row.find(x => x.agent_type === t)
        return { agent_type: t, name: c?.name || agentLabels[t] || t }
      })
      .filter(Boolean)
  } catch { agentList.value = [] }
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    groups.value = await watchlistApi.groups()
    loadRecent()
    if (showRecent.value && recentList.value.length) loadRecentPrices()
    loadAgentList()
    if (!currentGroupId.value || !groups.value.some(g => g.id === currentGroupId.value)) {
      currentGroupId.value = groups.value[0]?.id
    }
    if (symbolStore.selectedSymbol) {
      loadBrain()
      loadKline()
      loadStockDetail()
    } else {
      // 自动选中第一个分组的第一个个股
      const firstGroup = groups.value.find(g => g.items?.length)
      const firstItem = firstGroup?.items?.[0]
      if (firstItem) selectItem(firstItem)
    }
  } finally { loading.value = false }
}

async function loadWithSymbol(sym) {
  await load(true)
  if (!sym) return
  const item = groups.value.flatMap(g => g.items || []).find(i => i.symbol === sym)
  if (item) {
    selectItem(item)
    return
  }
  try {
    const basic = await stockApi.basic(sym)
    if (basic) {
      const row = { symbol: sym, name: basic.name || sym, price: basic.realtime?.price, change_pct: basic.realtime?.change_pct }
      symbolStore.select(sym, row)
      addToRecent(sym, row.name)
      loadKline()
      loadStockDetail()
    }
  } catch {}
}

function openAddGroup() {
  newGroupName.value = ''
  addGroupDialog.value = true
}

async function confirmAddGroup() {
  const name = newGroupName.value.trim()
  if (!name) return
  try {
    await watchlistApi.createGroup({ name })
    addGroupDialog.value = false
    load()
  } catch {}
}

async function deleteGroup(g) {
  if (g.name === '默认分组') return
  try {
    await ElMessageBox.confirm(`确认删除分组「${g.name}」？分组内的自选股将被移除。`, '删除分组', { type: 'warning' })
    await watchlistApi.deleteGroup(g.id)
    ElMessage.success('已删除')
    if (currentGroupId.value === g.id) { showRecent.value = true }
    await load()
  } catch { /* 取消 */ }
}

function openSearch() {
  searchKw.value = ''
  searchResults.value = []
  searched.value = false
  searchDialog.value = true
}

function doSearch() {
  if (!searchKw.value.trim()) return
  searched.value = true
  stockApi.search(searchKw.value.trim())
    .then(r => {
      searchResults.value = r || []
      if (!searchResults.value.length) ElMessage.warning('未找到匹配的股票，请尝试输入股票名称或6位代码（如 SH600519 / 600519 / 贵州茅台）')
    })
    .catch(() => {
      searchResults.value = []
      ElMessage.warning('搜索服务暂不可用，请稍后重试')
    })
}

async function addStock(row) {
  if (!currentGroupId.value) return
  try {
    const resp = await watchlistApi.addItem({ group_id: currentGroupId.value, symbol: row.symbol, name: row.name })
    if (resp && resp.ok === false) {
      if (resp.error === 'already_exists') ElMessage.warning(`${row.name} 已在自选中`)
      else ElMessage.error(resp.message || resp.error || '添加失败，请稍后重试')
      return
    }
    ElMessage.success(`已添加 ${row.name}`)
    searchDialog.value = false
    await load()
  } catch {
    ElMessage.error('添加失败，请检查网络后重试')
  }
}

function removeOne(row) {
  ElMessageBox.confirm(`确认删除 ${row.name}？`, '删除自选', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    .then(() => watchlistApi.removeItem(row.id).then(() => {
      if (symbolStore.selectedSymbol === row.symbol) symbolStore.clear()
      load()
    }))
    .catch(() => {})
}

function toggleDelete(row) {
  const idx = selectedForDelete.value.indexOf(row.id)
  if (idx >= 0) selectedForDelete.value.splice(idx, 1)
  else selectedForDelete.value.push(row.id)
}

async function batchRemove() {
  const ids = selectedForDelete.value.slice()
  if (!ids.length) return
  ElMessageBox.confirm(`确认删除选中的 ${ids.length} 只自选股？`, '批量删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    .then(async () => {
      try {
        await watchlistApi.batchRemove(ids)
        ElMessage.success(`已删除 ${ids.length} 只`)
        const remain = groups.value.flatMap(g => g.items || []).filter(i => !ids.includes(i.id))
        if (symbolStore.selectedSymbol && !remain.some(i => i.symbol === symbolStore.selectedSymbol)) symbolStore.clear()
        selectedForDelete.value = []
        batchMode.value = false
        await load()
      } catch { ElMessage.error('批量删除失败，请稍后重试') }
    })
    .catch(() => {})
}

function removeSelected() {
  const item = groups.value.flatMap(g => g.items || []).find(i => i.symbol === symbolStore.selectedSymbol)
  if (item?.id) watchlistApi.removeItem(item.id).then(() => { symbolStore.clear(); load() })
}

watch(period, (v) => { if (VALID_PERIODS.includes(v)) loadKline() })

watch(() => symbolStore.selectedSymbol, (sym) => { if (sym) loadQuotePanel() })

function restoreTabState() {
  try {
    const raw = localStorage.getItem(GROUP_STATE_KEY)
    if (raw) {
      const st = JSON.parse(raw)
      if (st.showRecent) showRecent.value = true
      else if (st.groupId) currentGroupId.value = st.groupId
    }
  } catch {}
}
function persistTabState() {
  try {
    const st = showRecent.value
      ? { showRecent: true, groupId: null }
      : { showRecent: false, groupId: currentGroupId.value }
    localStorage.setItem(GROUP_STATE_KEY, JSON.stringify(st))
  } catch {}
}
watch([currentGroupId, showRecent], persistTabState)

let timer = null
let loaded = false
onMounted(() => {
  restoreTabState()
  const qSym = route.query.symbol
  if (qSym) { loadWithSymbol(qSym) } else { load() }
  loaded = true
  timer = setInterval(() => {
    if (symbolStore.selectedSymbol) loadKline()
    if (symbolStore.selectedSymbol) loadQuotePanel()
    if (showRecent.value && recentList.value.length) loadRecentPrices()
  }, 30000)
})
// 路由变化时重新加载（解决导航回自选股不刷新的问题）
watch(() => route.path, (p) => {
  if (p === '/watchlist' && loaded) {
    const qSym = route.query.symbol
    if (qSym) { loadWithSymbol(qSym) }
    else if (!symbolStore.selectedSymbol) { load() }
  }
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.group-item { display: flex; justify-content: space-between; padding: 8px 10px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; }
.group-item:hover { background: #f3f4f6; }
.group-item.active { background: #409eff; color: #fff; box-shadow: 0 2px 6px rgba(64,158,255,.4); }
.group-item.active .fs12, .group-item.active .group-del, .group-item.active .el-icon { color: #fff !important; }
.wl-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; border: 1px solid transparent; }
.wl-item:hover { background: #f3f4f6; }
.wl-item.active { background: #ecf5ff; border-color: #b3d8ff; }
.wl-line { display: flex; justify-content: space-between; align-items: center; }
.brain-card { padding: 12px; border: 1px solid #e5e7eb; border-radius: 6px; height: 100%; }
.brain-text { color: #303133; line-height: 1.7; max-height: 180px; overflow: auto; }
.wl-del { color: #f56c6c; cursor: pointer; padding: 0 2px; font-size: 12px; opacity: 0; transition: opacity .15s; }
.wl-item:hover .wl-del { opacity: 1; }
.flex.gap { display: flex; gap: 8px; }
.concept-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.concept-item { padding: 8px; border: 1px solid #eef0f3; border-radius: 6px; background: #fafbfc; }
.stream-box { background: #1a1a2e; color: #e6e6f0; font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.7; padding: 12px 14px; border-radius: 6px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.stream-cursor { display: inline-block; width: 7px; height: 14px; background: #4ade80; margin-left: 2px; vertical-align: text-bottom; animation: stream-blink 1s step-end infinite; }
@keyframes stream-blink { 50% { opacity: 0; } }
.intent-bar { position: absolute; top: 8px; left: 56px; display: flex; align-items: center; gap: 8px; background: rgba(255,255,255,0.95); border: 1px solid #dcdfe6; border-radius: 6px; padding: 4px 10px; z-index: 10; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.intent-label { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 4px; color: #fff; background: #909399; }
.intent-rally { background: #409eff; }
.intent-trap { background: #f56c6c; }
.intent-bear { background: #67c23a; }
.intent-accumulate { background: #e6a23c; }
.intent-shakeout { background: #909399; }
.intent-wait { background: #c0c4cc; }
.intraday-toolbar { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.quote-block { padding: 10px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fafbfc; height: 100%; }
.quote-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; }
.sidebar-card { background: #fafbfc; }
.detail-wrap { max-width: 1080px; margin: 0 auto; }
.main-split { display: flex; gap: 12px; margin-top: 8px; align-items: flex-start; }
.main-left { flex: 1 1 auto; min-width: 0; }
.side-panel { width: 300px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; max-height: 640px; overflow: hidden auto; }
.order-grid { display: flex; flex-direction: column; gap: 2px; }
.order-row { display: grid; grid-template-columns: 24px 1fr 30px 10px 30px 1fr 24px; align-items: center; gap: 2px; padding: 3px 4px; border-radius: 4px; transition: background-color .3s; }
.order-row span { line-height: 1.2; white-space: nowrap; }
.ticks-list { max-height: 220px; overflow-y: auto; border: 1px solid #eef0f3; border-radius: 4px; }
.ticks-row { display: grid; grid-template-columns: 46px 48px 40px 26px 40px; align-items: center; gap: 2px; padding: 3px 4px; border-radius: 4px; font-size: 11px; transition: background-color .3s; }
.ticks-row .mono { font-size: 11px; }
.ticks-row .el-tag { width: 100%; justify-content: center; padding: 0; font-size: 11px; }
.ticks-row.row-hl, .order-row.row-hl { background: #fff7e6; }
.ticks-row:hover { background: #f7f8fa; }
@media (max-width: 991px) {
  .main-split { flex-direction: column; }
  .side-panel { width: 100%; max-height: none; }
}
</style>
