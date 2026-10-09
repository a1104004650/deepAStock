<template>
  <MainLayout>
    <div class="page event-page">
      <PageHeader
        eyebrow="HISTORICAL CONDITION / EVENT STUDY"
        title="条件归因实验台"
        subtitle="按历史条件动态分组，观察事件后的收益分布、胜率与相对基准表现"
      >
        <template #badge><span class="engine-badge">{{ capabilities?.engine_version || 'ENGINE CHECK' }}</span></template>
        <template #actions>
          <span class="run-scope mono">{{ selectedHorizons.length }} HORIZONS · {{ form.universe.max_symbols }} SYMBOLS MAX</span>
          <el-button type="primary" :loading="running" :disabled="initializing" @click="runStudy">运行事件研究</el-button>
        </template>
      </PageHeader>

      <section class="availability-strip" :class="availabilityTone" aria-label="字段可用性" aria-live="polite">
        <div class="availability-title"><span class="pulse"></span><strong>STRICT FIELD GATE</strong></div>
        <div class="field-state"><i :class="capabilities?.fields?.ohlcv?.available ? 'ok' : 'bad'"></i>OHLCV <b>{{ capabilities?.fields?.ohlcv?.available ? '可用' : '不可用' }}</b></div>
        <div class="field-state"><i :class="capabilities?.fields?.turnover_rate?.available ? 'ok' : 'bad'"></i>历史换手率 <b>{{ turnoverCoverage }}</b></div>
        <div class="field-state"><i class="warn"></i>精确涨停价 <b>不可用 · 阈值近似</b></div>
        <p>{{ capabilities?.fields?.exact_limit_price?.reason || '正在读取本地字段能力，缺失字段不会以零值代替。' }}</p>
      </section>

      <div v-if="loadError" class="notice error" role="alert"><span>{{ loadError }}</span><el-button link @click="loadMeta">重新读取</el-button></div>

      <section class="workbench">
        <aside class="preset-rail" aria-label="研究预设">
          <header><span>RESEARCH TEMPLATES</span><h2>研究预设</h2><p>载入后仍可逐项修改</p></header>
          <button
            v-for="preset in presets"
            :key="preset.key"
            type="button"
            class="preset-card"
            :class="{ active: activePreset === preset.key }"
            @click="applyPreset(preset)"
          >
            <span class="preset-code mono">{{ preset.key }}</span>
            <strong>{{ preset.name }}</strong>
            <small>{{ preset.description }}</small>
          </button>
          <div v-if="!presets.length" class="preset-empty">{{ initializing ? '读取预设中…' : '没有可用预设' }}</div>
          <div class="saved-divider">
            <span>SAVED STUDIES</span>
            <el-button link type="primary" size="small" :loading="saving" @click="saveDefinition">{{ activeDefinitionId ? '更新当前' : '保存当前' }}</el-button>
          </div>
          <div v-for="item in definitions" :key="item.id" class="preset-card saved-card" :class="{ active: activeDefinitionId === item.id }">
            <button type="button" class="saved-load" @click="applyDefinition(item)">
              <span class="preset-code mono">ID {{ item.id }} · {{ item.updated_at?.slice(0, 10) || '-' }}</span>
              <strong>{{ item.name }}</strong>
              <small>{{ item.description || '已保存条件方案' }}</small>
            </button>
            <el-button class="saved-delete" link type="danger" size="small" aria-label="删除已保存方案" @click.stop="removeDefinition(item)"><el-icon><Delete /></el-icon></el-button>
          </div>
          <div v-if="!definitions.length" class="preset-empty">尚未保存条件方案</div>
        </aside>

        <div class="builder-panel">
          <header class="section-head">
            <div><span>01 / RULE DEFINITION</span><h2>事件条件</h2></div>
            <div class="logic-switch">
              <label>条件关系</label>
              <el-radio-group v-model="form.rule.logic" size="small">
                <el-radio-button value="all">全部满足 AND</el-radio-button>
                <el-radio-button value="any">任一满足 OR</el-radio-button>
              </el-radio-group>
            </div>
          </header>
          <div class="rule-name-row">
            <label for="rule-name">研究名称</label>
            <el-input id="rule-name" v-model="form.rule.name" maxlength="100" show-word-limit placeholder="为本次条件组命名" />
          </div>

          <div class="condition-stack">
            <article v-for="(condition, index) in form.rule.conditions" :key="condition._id" class="condition-row">
              <div class="condition-index mono">{{ String(index + 1).padStart(2, '0') }}</div>
              <div class="condition-body">
                <div class="condition-main">
                  <div class="field condition-type">
                    <label :for="`condition-${condition._id}`">条件类型</label>
                    <el-select :id="`condition-${condition._id}`" v-model="condition.type" @change="resetCondition(condition)">
                      <el-option-group v-for="group in conditionGroups" :key="group.label" :label="group.label">
                        <el-option v-for="option in group.types" :key="option.value" :label="option.label" :value="option.value" :disabled="option.requiresTurnover && !turnoverAvailable" />
                      </el-option-group>
                    </el-select>
                  </div>
                  <template v-if="rangeCondition(condition.type)">
                    <div class="field compact"><label>最小值{{ unitFor(condition.type) }}</label><el-input-number v-model="condition.min" :controls="false" /></div>
                    <span class="range-mark">—</span>
                    <div class="field compact"><label>最大值{{ unitFor(condition.type) }}</label><el-input-number v-model="condition.max" :controls="false" /></div>
                  </template>
                  <template v-else-if="condition.type === 'close_vs_ma5'">
                    <div class="field direction-field"><label>收盘相对 MA5</label><el-select v-model="condition.direction"><el-option label="位于 MA5 上方" value="above" /><el-option label="位于 MA5 下方" value="below" /></el-select></div>
                  </template>
                  <button type="button" class="delete-condition" :disabled="form.rule.conditions.length === 1" :aria-label="`删除条件 ${index + 1}`" @click="removeCondition(index)">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="condition.type === 'post_limit_pullback'" class="pullback-fields">
                  <div class="field compact"><label>前序连板最小</label><el-input-number v-model="condition.streak_min" :min="1" :controls="false" /></div>
                  <div class="field compact"><label>前序连板最大</label><el-input-number v-model="condition.streak_max" :min="1" :controls="false" /></div>
                  <div class="field compact"><label>调整日最小</label><el-input-number v-model="condition.days_min" :min="1" :controls="false" /></div>
                  <div class="field compact"><label>调整日最大</label><el-input-number v-model="condition.days_max" :min="1" :controls="false" /></div>
                  <div class="field compact"><label>最大回撤 %</label><el-input-number v-model="condition.max_drawdown_pct" :min="0" :max="100" :controls="false" /></div>
                  <el-checkbox v-model="condition.shrinking_volume">严格逐日缩量</el-checkbox>
                  <el-checkbox v-model="condition.require_pullback">收盘低于连板日</el-checkbox>
                </div>
                <div v-else-if="showExtras(condition.type)" class="pullback-fields">
                  <div v-if="hasLookback(condition.type)" class="field compact"><label>回看交易日</label><el-input-number v-model="condition.lookback" :min="2" :max="250" :controls="false" /></div>
                  <div v-if="condition.type === 'direction_streak'" class="field compact">
                    <label>方向</label>
                    <el-select v-model="condition.direction"><el-option label="连续上涨" value="up" /><el-option label="连续下跌" value="down" /></el-select>
                  </div>
                  <div v-if="condition.type === 'breakout_distance'" class="field compact">
                    <label>参照价</label>
                    <el-select v-model="condition.reference"><el-option label="前N日最高价" value="high" /><el-option label="前N日收盘价" value="close" /></el-select>
                  </div>
                  <template v-if="condition.type === 'ma_cross'">
                    <div class="field compact"><label>短均线</label><el-input-number v-model="condition.short" :min="2" :max="60" :controls="false" /></div>
                    <div class="field compact"><label>长均线</label><el-input-number v-model="condition.long" :min="3" :max="250" :controls="false" /></div>
                    <div class="field compact">
                      <label>交叉类型</label>
                      <el-select v-model="condition.direction"><el-option label="金叉（短上穿长）" value="golden" /><el-option label="死叉（短下穿长）" value="dead" /></el-select>
                    </div>
                  </template>
                  <template v-if="condition.type === 'volume_trend'">
                    <div class="field compact"><label>近期天数</label><el-input-number v-model="condition.recent" :min="1" :max="30" :controls="false" /></div>
                    <div class="field compact"><label>基期天数</label><el-input-number v-model="condition.baseline" :min="3" :max="250" :controls="false" /></div>
                  </template>
                  <div v-if="condition.type === 'volume_contraction_streak'" class="field compact"><label>逐日缩量上限(倍)</label><el-input-number v-model="condition.ratio_max" :min="0.1" :max="1" :step="0.05" :controls="false" /></div>
                  <div v-if="condition.type === 'limit_break'" class="field compact"><label>回落幅度 (bp)</label><el-input-number v-model="condition.close_gap_bp" :min="1" :max="500" :controls="false" /></div>
                </div>
                <p class="condition-note">{{ conditionDescription(condition.type) }}</p>
              </div>
            </article>
          </div>
          <button type="button" class="add-condition" :disabled="form.rule.conditions.length >= 20" @click="addCondition"><el-icon><Plus /></el-icon>添加条件</button>
        </div>
      </section>

      <section class="config-panel">
        <header class="section-head"><div><span>02 / STUDY DESIGN</span><h2>研究设计</h2></div><p>所有期限均按交易日计算</p></header>
        <div class="config-grid">
          <div class="config-cell date-cell"><label>事件窗口</label><el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" :disabled-date="disableDate" /></div>
          <div class="config-cell"><label>收益起点</label><el-select v-model="form.return_basis"><el-option label="事件日收盘" value="event_close" /><el-option label="下一交易日开盘" value="next_open" /></el-select></div>
          <div class="config-cell"><label>市场基准</label><el-select v-model="form.benchmark"><el-option v-for="item in benchmarks" :key="item.value" :label="item.label" :value="item.value" /></el-select></div>
          <div class="config-cell"><label>事件重叠策略</label><el-select v-model="form.occurrence_policy"><el-option label="仅状态首次进入" value="entry" /><el-option label="每个满足日" value="state" /><el-option label="冷却期去重" value="cooldown" /></el-select></div>
          <div class="config-cell" :class="{ muted: form.occurrence_policy !== 'cooldown' }"><label>冷却交易日</label><el-input-number v-model="form.cooldown_sessions" :min="0" :max="240" :disabled="form.occurrence_policy !== 'cooldown'" /></div>
          <div class="config-cell"><label>最大扫描标的</label><el-input-number v-model="form.universe.max_symbols" :min="1" :max="2000" :step="50" /></div>
          <div class="config-cell symbol-cell"><label>指定标的 <small>留空扫描缓存池</small></label><el-input v-model="symbolInput" clearable placeholder="SH600000, SZ000001" /></div>
          <fieldset class="config-cell horizon-cell"><legend>前瞻期限</legend><el-checkbox-group v-model="selectedHorizons"><el-checkbox v-for="h in horizonOptions" :key="h" :value="h">{{ h }}日</el-checkbox></el-checkbox-group></fieldset>
        </div>
        <div class="config-foot">
          <span>缓存范围 <b class="mono">{{ capabilities?.first_date || '-' }} → {{ capabilities?.last_date || '-' }}</b></span>
          <span>缓存标的 <b class="mono">{{ capabilities?.daily_symbols ?? '-' }}</b></span>
          <el-button type="primary" :loading="running" @click="runStudy">运行事件研究</el-button>
        </div>
      </section>

      <section class="config-panel">
        <header class="section-head"><div><span>03 / UNIVERSE FILTER</span><h2>股票池过滤</h2></div><p>在扫描本地缓存前先剔除不合格样本</p></header>
        <div class="universe-grid">
          <fieldset class="universe-cell toggle-cell">
            <legend>池子剔除</legend>
            <el-checkbox v-model="form.universe.equity_only">仅A股个股（剔除指数/债券等）</el-checkbox>
            <el-checkbox v-model="form.universe.exclude_current_st">剔除当前ST（按现有名称，非历史时点）</el-checkbox>
          </fieldset>
          <fieldset class="universe-cell board-cell">
            <legend>剔除板块</legend>
            <el-checkbox-group v-model="form.universe.exclude_boards">
              <el-checkbox v-for="board in boardOptions" :key="board.value" :value="board.value">{{ board.label }}</el-checkbox>
            </el-checkbox-group>
            <p class="cell-note">常见用法：勾选「科创板」「北交所」「ST风险板块外的未知代码」实现去科创、去北交</p>
          </fieldset>
          <fieldset class="universe-cell range-cell">
            <legend>样本质量</legend>
            <div class="field compact"><label>最少观察K线（去新股代理）</label><el-input-number v-model="form.universe.min_observed_bars" :min="0" :max="1000" :step="10" :controls="false" /></div>
            <div class="field compact"><label>最低价 (元)</label><el-input-number v-model="form.universe.min_price" :min="0" :controls="false" placeholder="不限" /></div>
            <div class="field compact"><label>最高价 (元)</label><el-input-number v-model="form.universe.max_price" :min="0" :controls="false" placeholder="不限" /></div>
          </fieldset>
        </div>
        <div class="config-foot">
          <span>过滤发生在事件判定之前，剔除原因会汇总到结果的 <b>excluded_event_bars</b></span>
          <span>缓存标的 <b class="mono">{{ capabilities?.daily_symbols ?? '-' }}</b></span>
          <el-button type="primary" :loading="running" @click="runStudy">运行事件研究</el-button>
        </div>
      </section>

      <div v-if="runError" class="notice error" role="alert"><span>{{ runError }}</span><el-button link @click="runStudy">重试</el-button></div>
      <section v-if="running && !report" class="loading-panel" aria-live="polite"><el-skeleton :rows="8" animated /></section>

      <template v-if="report">
        <section class="result-header">
          <div><span>04 / OBSERVATION</span><h2>{{ report.rule?.name || '事件研究结果' }}</h2><p>{{ resultScope }}</p></div>
          <div class="result-counters">
            <div><small>事件</small><strong class="mono">{{ report.summary?.events ?? 0 }}</strong></div>
            <div><small>标的</small><strong class="mono">{{ report.summary?.unique_symbols ?? 0 }}</strong></div>
            <div><small>事件日</small><strong class="mono">{{ report.summary?.unique_dates ?? 0 }}</strong></div>
            <div><small>已扫描</small><strong class="mono">{{ report.universe?.symbols_scanned ?? 0 }}</strong></div>
          </div>
        </section>

        <div v-if="resultWarnings.length" class="warning-stack" role="status"><b>结果约束</b><span v-for="warning in resultWarnings" :key="warning">{{ warning }}</span></div>

        <section v-if="statistics.length" class="horizon-cards" aria-label="各前瞻期限统计">
          <article v-for="stat in statistics" :key="stat.horizon" class="horizon-card">
            <header><span class="mono">T+{{ stat.horizon }}</span><small>{{ stat.samples }} 样本 · {{ formatPct(stat.coverage_pct) }} 覆盖</small></header>
            <div class="primary-stat"><small>平均收益（事件等权）</small><strong class="mono" :class="tone(stat.mean_pct)">{{ formatPct(stat.mean_pct, true) }}</strong></div>
            <div class="stat-pairs">
              <div><small>中位数</small><b class="mono" :class="tone(stat.median_pct)">{{ formatPct(stat.median_pct, true) }}</b></div>
              <div><small>胜率</small><b class="mono">{{ formatPct(stat.win_rate_pct) }}</b></div>
              <div><small>超额均值</small><b class="mono" :class="tone(stat.benchmark_excess_mean_pct)">{{ formatPct(stat.benchmark_excess_mean_pct, true) }}</b></div>
              <div><small>标准差</small><b class="mono">{{ formatPct(stat.std_pct) }}</b></div>
            </div>
            <div class="dual-line" title="同一天多个事件先取日均值，再对日期取均值，避免单日扎堆放大权重">
              <span>事件日等权均值</span>
              <b class="mono" :class="tone(stat.date_weighted?.mean_pct)">{{ formatPct(stat.date_weighted?.mean_pct, true) }}</b>
              <em class="mono">t={{ formatT(stat.t_stat) }} / {{ formatT(stat.date_weighted?.t_stat) }}</em>
            </div>
            <div class="ci-line"><span>95% CI（事件）</span><b class="mono">{{ formatPct(stat.ci95_low_pct, true) }} — {{ formatPct(stat.ci95_high_pct, true) }}</b></div>
            <div class="ci-line"><span>95% CI（按事件日聚类）</span><b class="mono">{{ formatPct(stat.cluster_ci95_low_pct, true) }} — {{ formatPct(stat.cluster_ci95_high_pct, true) }}</b></div>
            <div class="ci-line" v-if="stat.stability"><span>年度稳定性</span><b class="mono">{{ stat.stability.years_used }}/{{ stat.stability.years_covered }} 年有效 · 正收益年 {{ formatPct(stat.stability.positive_years_pct) }}</b></div>
          </article>
        </section>

        <section v-if="hasChartData" class="chart-grid">
          <article class="result-panel"><PanelTitle title="期限收益与置信区间" subtitle="事件等权 / 事件日等权 / 中位数 / 相对基准超额；误差线为事件均值 95% bootstrap CI" /><div ref="returnChartEl" class="result-chart" role="img" aria-label="各期限平均收益、中位数、基准超额和置信区间图"></div></article>
          <article class="result-panel"><PanelTitle title="收益分布与胜率" subtitle="箱体为 P25–P75，须线为最小–最大；折线为胜率" /><div ref="distributionChartEl" class="result-chart" role="img" aria-label="各期限收益分布箱线图和胜率图"></div></article>
        </section>

        <section class="events-panel">
          <PanelTitle title="事件样本" :subtitle="`展示接口返回的 ${events.length} 条事件；展开查看条件诊断与相对基准收益`"><span class="table-stamp mono">FORWARD RETURN / %</span></PanelTitle>
          <div class="table-scroll">
            <el-table :data="events" row-key="eventKey" size="small" empty-text="当前条件与区间没有匹配事件">
              <el-table-column type="expand" width="42">
                <template #default="{ row }">
                  <div class="event-detail">
                    <div><h3>条件诊断</h3><dl><div v-for="(diagnostic, i) in row.diagnostics || []" :key="i"><dt>{{ conditionLabel(diagnostic.type) }}</dt><dd class="mono">{{ diagnosticText(diagnostic) }}</dd></div></dl></div>
                    <div><h3>相对基准收益</h3><dl><div v-for="h in report.scope?.horizons || []" :key="h"><dt>T+{{ h }}</dt><dd class="mono" :class="tone(row.relative?.[String(h)])">{{ formatPct(row.relative?.[String(h)], true) }}</dd></div></dl></div>
                    <div><h3>事件快照</h3><dl><div><dt>事件收盘</dt><dd class="mono">{{ formatNumber(row.event_close, 4) }}</dd></div><div><dt>收益起点价</dt><dd class="mono">{{ formatNumber(row.entry_price, 4) }}</dd></div><div><dt>连板计数</dt><dd class="mono">{{ row.limit_streak ?? '-' }}</dd></div><div><dt>换手率</dt><dd class="mono">{{ formatPct(row.turnover) }}</dd></div></dl></div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="标的" min-width="150"><template #default="{ row }"><div class="stock-id"><b>{{ row.name || row.symbol }}</b><span class="mono">{{ row.symbol }}</span></div></template></el-table-column>
              <el-table-column prop="event_date" label="事件日" width="112" />
              <el-table-column label="当日涨跌" align="right" width="92"><template #default="{ row }"><span class="mono" :class="tone(row.change_pct)">{{ formatPct(row.change_pct, true) }}</span></template></el-table-column>
              <el-table-column v-for="h in report.scope?.horizons || []" :key="h" :label="`T+${h}`" align="right" min-width="86"><template #default="{ row }"><strong class="mono" :class="tone(row.forward?.[String(h)])">{{ formatPct(row.forward?.[String(h)], true) }}</strong></template></el-table-column>
            </el-table>
          </div>
        </section>

        <section class="methodology-panel">
          <div class="method-mark">M</div>
          <div class="method-lead"><span>METHODOLOGY / COVERAGE</span><h2>口径与覆盖边界</h2><p>这是条件事件研究，不是交易盈亏归因。每个事件以所选收益起点为基准，按后续交易日收盘计算前瞻收益。</p></div>
          <div class="method-facts">
            <div><b>事件抽样</b><p>{{ occurrenceText }}</p></div>
            <div><b>股票池</b><p>{{ universeText }}</p></div>
            <div><b>涨停识别</b><p>{{ report.data_quality?.limit_method || '涨停识别说明不可用' }}</p></div>
            <div><b>右端删失</b><p>{{ censoredText }}</p></div>
          </div>
          <div class="coverage-bar"><span>区间起点有覆盖的标的</span><div><i :style="{ width: `${startCoverage}%` }"></i></div><strong class="mono">{{ report.universe?.symbols_covering_start ?? 0 }} / {{ report.universe?.symbols_with_rows ?? 0 }} · {{ startCoverage }}%</strong></div>
        </section>
      </template>

      <section v-else-if="!running" class="empty-result">
        <div class="empty-axis"><i></i><b></b><span></span></div>
        <div><span>AWAITING OBSERVATION</span><h2>定义条件，然后运行历史观察</h2><p>结果区只展示后端真实返回的数据，不预置示例收益。建议先使用预设确认数据覆盖，再组合条件。</p></div>
      </section>
    </div>
  </MainLayout>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MainLayout from '../layout/MainLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import { eventStudyApi } from '../api'

const PanelTitle = defineComponent({
  props: { title: String, subtitle: String },
  setup(props, { slots }) {
    return () => h('header', { class: 'panel-title' }, [h('div', null, [h('h2', null, props.title), h('p', null, props.subtitle)]), slots.default?.()])
  },
})

const conditionGroups = [
  { label: '涨停与连板', types: [
    { value: 'limit_up_streak', label: '连续涨停天数' },
    { value: 'post_limit_pullback', label: '连板后缩量调整' },
    { value: 'turnover_limit_up', label: '换手涨停', requiresTurnover: true },
    { value: 'first_limit_in_window', label: '窗口内首次涨停' },
    { value: 'days_since_limit', label: '距上次涨停天数' },
    { value: 'limit_break', label: '炸板（触板回落）' },
  ] },
  { label: '量价形态', types: [
    { value: 'change_pct', label: '当日涨跌幅' },
    { value: 'volume_ratio', label: '成交量比（前N日均量）' },
    { value: 'amplitude', label: '当日振幅' },
    { value: 'close_location', label: '收盘位置（日内%）' },
    { value: 'upper_shadow_pct', label: '上影线（%前收）' },
    { value: 'lower_shadow_pct', label: '下影线（%前收）' },
    { value: 'gap_pct', label: '跳空缺口（%前收）' },
    { value: 'intraday_return_pct', label: '日内涨幅（收对开）' },
    { value: 'volume_trend', label: '近期/基期均量比' },
    { value: 'volume_contraction_streak', label: '连续缩量天数' },
  ] },
  { label: '趋势与位置', types: [
    { value: 'close_vs_ma5', label: '收盘价相对 MA5' },
    { value: 'ma_distance', label: '收盘距均线（%）' },
    { value: 'ma_cross', label: '均线金叉/死叉' },
    { value: 'return_n', label: 'N日区间涨跌幅' },
    { value: 'direction_streak', label: '连续涨/跌方向天数' },
    { value: 'breakout_distance', label: '突破前高距离（%）' },
    { value: 'range_position', label: 'N日区间位置（%）' },
    { value: 'drawdown_from_high', label: '距N日高点回撤' },
    { value: 'rebound_from_low', label: '距N日低点反弹' },
  ] },
  { label: '波动率', types: [
    { value: 'realized_volatility', label: '年化已实现波动率' },
    { value: 'atr_pct', label: 'ATR 波动（%收盘）' },
  ] },
]
const conditionTypes = conditionGroups.flatMap((group) => group.types)
const descriptions = {
  limit_up_streak: '事件日连续达到代码板块涨停阈值的交易日数。',
  post_limit_pullback: '从前序连板日向后寻找指定长度调整段，并核验缩量、回撤和收盘关系。',
  turnover_limit_up: '事件日同时满足涨停近似与历史换手率区间；字段缺失时严格拒绝运行。',
  first_limit_in_window: '事件日达到涨停阈值，且此前回看窗口内没有涨停阈值事件。',
  days_since_limit: '距离上一次涨停阈值事件的交易日数；从未涨停则不计入。',
  limit_break: '最高价触及涨停阈值价但收盘回落超过指定幅度，属于日K近似而非逐笔开板记录。',
  change_pct: '事件日相邻收盘涨跌幅区间。',
  volume_ratio: '事件日成交量相对回看窗口平均成交量的倍数。',
  amplitude: '事件日最高价与最低价相对前收盘的振幅区间。',
  close_location: '(收盘-最低)/(最高-最低)×100，100 表示收在日内最高。',
  upper_shadow_pct: '上影线长度相对前收盘的百分比。',
  lower_shadow_pct: '下影线长度相对前收盘的百分比。',
  gap_pct: '开盘相对前收盘的跳空百分比。',
  intraday_return_pct: '收盘相对开盘的日内涨幅。',
  volume_trend: '近近期天数均量 / 基期天数均量，两者窗口不重叠。',
  volume_contraction_streak: '事件日向前连续逐日缩量的天数（每日量不高于前日的指定倍数）。',
  close_vs_ma5: '事件日收盘价位于 5 日移动平均线上方或下方。',
  ma_distance: '收盘价相对回看窗口均线的偏离百分比。',
  ma_cross: '短均线相对长均线在事件日发生金叉或死叉（均需窗口满样本）。',
  return_n: '事件日收盘相对回看窗口起点收盘的涨跌幅。',
  direction_streak: '事件日向前连续收涨或收跌的交易日数。',
  breakout_distance: '事件日收盘相对窗口内最高价/收盘价的距离，正值表示突破。',
  range_position: '收盘在窗口最高-最低区间中的位置百分比。',
  drawdown_from_high: '收盘相对窗口内最高收盘的回撤百分比。',
  rebound_from_low: '收盘相对窗口内最低收盘的反弹百分比。',
  realized_volatility: '回看窗口日收益标准差年化（×√252），需满样本。',
  atr_pct: '窗口内真实波幅均值相对当日收盘的百分比。',
}
const defaults = {
  limit_up_streak: { min: 1, max: 3 },
  post_limit_pullback: { streak_min: 1, streak_max: 3, days_min: 2, days_max: 5, shrinking_volume: true, require_pullback: true, max_drawdown_pct: 20 },
  turnover_limit_up: { min: 8, max: 35 },
  first_limit_in_window: { lookback: 20 },
  days_since_limit: { min: 1, max: 10 },
  limit_break: { close_gap_bp: 50 },
  change_pct: { min: 0, max: 10 },
  volume_ratio: { lookback: 20, min: 1.5, max: 10 },
  amplitude: { min: 0, max: 10 },
  close_location: { min: 70, max: 100 },
  upper_shadow_pct: { min: 3, max: 30 },
  lower_shadow_pct: { min: 1, max: 30 },
  gap_pct: { min: 2, max: 10 },
  intraday_return_pct: { min: 3, max: 20 },
  volume_trend: { recent: 3, baseline: 20, min: 1.2, max: 5 },
  volume_contraction_streak: { min: 3, max: 20, ratio_max: 1 },
  close_vs_ma5: { direction: 'above' },
  ma_distance: { lookback: 20, min: -3, max: 3 },
  ma_cross: { short: 5, long: 20, direction: 'golden' },
  return_n: { lookback: 20, min: 10, max: 100 },
  direction_streak: { direction: 'up', min: 3, max: 20 },
  breakout_distance: { lookback: 20, reference: 'high', min: 0, max: 20 },
  range_position: { lookback: 60, min: 80, max: 120 },
  drawdown_from_high: { lookback: 60, min: 20, max: 90 },
  rebound_from_low: { lookback: 60, min: 10, max: 80 },
  realized_volatility: { lookback: 20, min: 20, max: 120 },
  atr_pct: { lookback: 20, min: 2, max: 15 },
}
const RANGE_TYPES = ['limit_up_streak', 'turnover_limit_up', 'change_pct', 'volume_ratio', 'amplitude',
  'close_location', 'upper_shadow_pct', 'lower_shadow_pct', 'gap_pct', 'intraday_return_pct',
  'volume_trend', 'volume_contraction_streak', 'ma_distance', 'return_n', 'direction_streak',
  'breakout_distance', 'range_position', 'drawdown_from_high', 'rebound_from_low',
  'realized_volatility', 'atr_pct', 'days_since_limit']
const LOOKBACK_TYPES = ['volume_ratio', 'first_limit_in_window', 'ma_distance', 'return_n',
  'breakout_distance', 'range_position', 'drawdown_from_high', 'rebound_from_low',
  'realized_volatility', 'atr_pct']
const boardOptions = [
  { label: '沪主板', value: 'main_sh' }, { label: '深主板', value: 'main_sz' },
  { label: '创业板', value: 'chinext' }, { label: '科创板', value: 'star' },
  { label: '北交所', value: 'beijing' }, { label: '未知代码', value: 'unknown' },
]
const benchmarks = [
  { label: '沪深300 · SH000300', value: 'SH000300' },
  { label: '上证指数 · SH000001', value: 'SH000001' },
  { label: '中证500 · SH000905', value: 'SH000905' },
  { label: '创业板指 · SZ399006', value: 'SZ399006' },
]
const horizonOptions = [1, 3, 5, 7, 10, 20, 30, 60, 120]
let conditionId = 0
const makeCondition = (type = 'limit_up_streak') => ({ _id: ++conditionId, type, ...defaults[type] })

const capabilities = ref(null)
const presets = ref([])
const definitions = ref([])
const activeDefinitionId = ref(null)
const saving = ref(false)
const initializing = ref(true)
const loadError = ref('')
const running = ref(false)
const runError = ref('')
const report = ref(null)
const activePreset = ref('')
const symbolInput = ref('')
const selectedHorizons = ref([1, 3, 7, 30])
const dateRange = ref([])
const returnChartEl = ref(null)
const distributionChartEl = ref(null)
let returnChart = null
let distributionChart = null

const form = ref({
  benchmark: 'SH000300', return_basis: 'event_close', occurrence_policy: 'entry', cooldown_sessions: 30,
  universe: { mode: 'cached', max_symbols: 500, equity_only: true, exclude_current_st: true,
    exclude_boards: ['star', 'beijing'], min_observed_bars: 120, min_price: null, max_price: null },
  rule: { name: '未命名条件组', logic: 'all', conditions: [makeCondition()] },
})

const turnoverAvailable = computed(() => Boolean(capabilities.value?.fields?.turnover_rate?.available))
const turnoverCoverage = computed(() => capabilities.value ? `${capabilities.value.turnover_symbols || 0} / ${capabilities.value.daily_symbols || 0} 标的` : '检查中')
const availabilityTone = computed(() => capabilities.value?.fields?.ohlcv?.available ? 'available' : 'unavailable')
const statistics = computed(() => report.value?.statistics || [])
const hasChartData = computed(() => statistics.value.some((row) => Number(row.samples) > 0))
const events = computed(() => (report.value?.events || []).map((row, index) => ({ ...row, eventKey: `${row.symbol}-${row.event_date}-${index}` })))
const resultWarnings = computed(() => [...new Set([...(report.value?.summary?.condition_errors || []), ...(report.value?.data_quality?.warnings || [])])])
const resultScope = computed(() => {
  const scope = report.value?.scope
  return scope ? `${scope.start_date} → ${scope.end_date} · ${scope.return_basis === 'next_open' ? '次日开盘起算' : '事件收盘起算'}` : ''
})
const occurrenceText = computed(() => ({ state: '每个满足条件的交易日都作为独立事件。', entry: '仅条件状态由不满足转为满足时记为事件。', cooldown: `事件后 ${report.value?.scope?.cooldown_sessions || 0} 个交易日内不重复采样。` }[report.value?.scope?.occurrence_policy] || '-'))
const censoredText = computed(() => {
  const rows = Object.entries(report.value?.data_quality?.censored_events || {})
  return rows.length ? rows.map(([horizon, count]) => `T+${horizon}: ${count} 条`).join('；') : '无删失统计'
})
const startCoverage = computed(() => {
  const covered = Number(report.value?.universe?.symbols_covering_start || 0)
  const total = Number(report.value?.universe?.symbols_with_rows || 0)
  return total ? Math.round(covered / total * 100) : 0
})
const universeText = computed(() => {
  const filters = report.value?.universe?.filters || {}
  const labels = []
  if (filters.equity_only) labels.push('仅A股个股')
  if (filters.exclude_current_st) labels.push('剔除当前ST')
  if (filters.exclude_boards?.length) labels.push(`剔除板块 ${filters.exclude_boards.join('/')}`)
  if (filters.min_observed_bars) labels.push(`最少观察${filters.min_observed_bars}根K线`)
  if (filters.min_price != null) labels.push(`价≥${filters.min_price}`)
  if (filters.max_price != null) labels.push(`价≤${filters.max_price}`)
  const excluded = Object.entries(report.value?.universe?.excluded_event_bars || {})
  const excludedText = excluded.length ? `；事件条剔除 ${excluded.map(([reason, count]) => `${reason}:${count}`).join('，')}` : ''
  const caveat = report.value?.universe?.survivorship_caveat || ''
  return `${labels.length ? `已应用：${labels.join('；')}${excludedText}。` : ''}${caveat}`
})

function isoDate(date) {
  const y = date.getFullYear(), m = String(date.getMonth() + 1).padStart(2, '0'), d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
function setInitialDates() {
  const end = capabilities.value?.last_date ? new Date(`${capabilities.value.last_date}T00:00:00`) : new Date()
  const start = new Date(end); start.setFullYear(start.getFullYear() - 1)
  const first = capabilities.value?.first_date ? new Date(`${capabilities.value.first_date}T00:00:00`) : null
  dateRange.value = [isoDate(first && first > start ? first : start), isoDate(end)]
}
function disableDate(date) {
  const first = capabilities.value?.first_date ? new Date(`${capabilities.value.first_date}T00:00:00`) : null
  const last = capabilities.value?.last_date ? new Date(`${capabilities.value.last_date}T23:59:59`) : new Date()
  return (first && date < first) || date > last
}
async function loadMeta() {
  initializing.value = true; loadError.value = ''
  try {
    const [caps, presetRows, savedRows] = await Promise.all([eventStudyApi.capabilities(), eventStudyApi.presets(), eventStudyApi.definitions()])
    capabilities.value = caps; presets.value = presetRows || []; definitions.value = savedRows || []; setInitialDates()
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || '事件研究能力读取失败'
  } finally { initializing.value = false }
}
function cleanCondition(source) {
  const { _id, ...condition } = source
  return condition
}
function applyPreset(preset) {
  activePreset.value = preset.key
  activeDefinitionId.value = null
  form.value.rule = { ...preset.rule, conditions: preset.rule.conditions.map((condition) => ({ _id: ++conditionId, ...condition })) }
}
function buildPayload() {
  const symbols = symbolInput.value.split(/[\s,，;；]+/).map((value) => value.trim().toUpperCase()).filter(Boolean)
  const universe = form.value.universe
  return {
    start_date: dateRange.value[0], end_date: dateRange.value[1], horizons: [...selectedHorizons.value].sort((a, b) => a - b),
    benchmark: form.value.benchmark, return_basis: form.value.return_basis, occurrence_policy: form.value.occurrence_policy,
    cooldown_sessions: form.value.cooldown_sessions,
    universe: { mode: 'cached', symbols, max_symbols: universe.max_symbols, equity_only: universe.equity_only,
      exclude_current_st: universe.exclude_current_st, exclude_boards: [...universe.exclude_boards],
      min_observed_bars: universe.min_observed_bars ?? 0, min_price: universe.min_price, max_price: universe.max_price },
    rule: { name: form.value.rule.name.trim(), logic: form.value.rule.logic, conditions: form.value.rule.conditions.map(cleanCondition) },
  }
}
function applyDefinition(item) {
  const config = item.config || {}
  const universe = config.universe || {}
  activePreset.value = ''; activeDefinitionId.value = item.id
  dateRange.value = [config.start_date, config.end_date]
  selectedHorizons.value = [...(config.horizons || [1, 3, 7, 30])]
  symbolInput.value = (universe.symbols || []).join(', ')
  form.value = {
    benchmark: config.benchmark || 'SH000300', return_basis: config.return_basis || 'event_close',
    occurrence_policy: config.occurrence_policy || 'entry', cooldown_sessions: config.cooldown_sessions ?? 30,
    universe: { mode: 'cached', max_symbols: universe.max_symbols || 500,
      equity_only: universe.equity_only ?? true, exclude_current_st: universe.exclude_current_st ?? true,
      exclude_boards: [...(universe.exclude_boards || [])], min_observed_bars: universe.min_observed_bars ?? 120,
      min_price: universe.min_price ?? null, max_price: universe.max_price ?? null },
    rule: { ...config.rule, conditions: (config.rule?.conditions || []).map(condition => ({ _id: ++conditionId, ...condition })) },
  }
}
async function saveDefinition() {
  const invalid = validate(); if (invalid) { ElMessage.warning(invalid); return }
  saving.value = true
  try {
    const data = { name: form.value.rule.name.trim(), description: `前瞻 ${selectedHorizons.value.join('/')} 个交易日`, config: buildPayload() }
    const saved = activeDefinitionId.value ? await eventStudyApi.updateDefinition(activeDefinitionId.value, data) : await eventStudyApi.createDefinition(data)
    activeDefinitionId.value = saved.id
    definitions.value = await eventStudyApi.definitions()
    ElMessage.success('条件组已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '条件组保存失败')
  } finally { saving.value = false }
}
async function removeDefinition(item) {
  try {
    await ElMessageBox.confirm(`删除条件组「${item.name}」？`, '删除条件组', { type: 'warning' })
    await eventStudyApi.deleteDefinition(item.id)
    if (activeDefinitionId.value === item.id) activeDefinitionId.value = null
    definitions.value = definitions.value.filter(row => row.id !== item.id)
  } catch { /* cancelled */ }
}
function resetCondition(condition) {
  const id = condition._id, type = condition.type
  Object.keys(condition).forEach((key) => delete condition[key])
  Object.assign(condition, { _id: id, type, ...defaults[type] }); activePreset.value = ''; activeDefinitionId.value = null
}
function addCondition() { form.value.rule.conditions.push(makeCondition('change_pct')); activePreset.value = ''; activeDefinitionId.value = null }
function removeCondition(index) { if (form.value.rule.conditions.length > 1) form.value.rule.conditions.splice(index, 1); activePreset.value = ''; activeDefinitionId.value = null }
function rangeCondition(type) { return RANGE_TYPES.includes(type) }
function hasLookback(type) { return LOOKBACK_TYPES.includes(type) }
function showExtras(type) {
  return hasLookback(type) || ['ma_cross', 'breakout_distance', 'direction_streak',
    'volume_trend', 'volume_contraction_streak', 'limit_break'].includes(type)
}
function unitFor(type) {
  if (['turnover_limit_up', 'change_pct', 'amplitude', 'close_location', 'upper_shadow_pct',
    'lower_shadow_pct', 'gap_pct', 'intraday_return_pct', 'ma_distance', 'return_n',
    'breakout_distance', 'range_position', 'drawdown_from_high', 'rebound_from_low',
    'realized_volatility', 'atr_pct'].includes(type)) return ' (%)'
  if (type === 'volume_ratio') return ' (倍)'
  if (type === 'volume_trend') return ' (比值)'
  if (type === 'volume_contraction_streak') return ' (天)'
  if (['limit_up_streak', 'days_since_limit'].includes(type)) return ' (天)'
  return ''
}
function conditionDescription(type) { return descriptions[type] || '' }
function conditionLabel(type) { return conditionTypes.find((item) => item.value === type)?.label || type || '-' }
function validate() {
  if (!dateRange.value?.[0] || !dateRange.value?.[1]) return '请选择完整的事件窗口'
  if (!selectedHorizons.value.length) return '至少选择一个前瞻期限'
  if (!form.value.rule.name.trim()) return '请输入研究名称'
  if (form.value.rule.conditions.some((condition) => condition.type === 'turnover_limit_up') && !turnoverAvailable.value) return '历史换手率字段不可用，不能运行换手涨停条件'
  const universe = form.value.universe
  if (universe.min_price != null && universe.max_price != null && Number(universe.min_price) > Number(universe.max_price)) return '股票池最低价不能大于最高价'
  for (const condition of form.value.rule.conditions) {
    if (rangeCondition(condition.type) && Number(condition.min) > Number(condition.max)) return `${conditionLabel(condition.type)}的最小值不能大于最大值`
    if (condition.type === 'post_limit_pullback' && (condition.streak_min > condition.streak_max || condition.days_min > condition.days_max)) return '连板后缩量调整的区间下限不能大于上限'
    if (condition.type === 'ma_cross' && Number(condition.short) >= Number(condition.long)) return '均线金叉/死叉的短均线周期必须小于长均线周期'
    if (condition.type === 'volume_trend' && Number(condition.recent) >= Number(condition.baseline)) return '近期/基期均量比的近期天数必须小于基期天数'
  }
  return ''
}
async function runStudy() {
  const invalid = validate()
  if (invalid) { ElMessage.warning(invalid); return }
  running.value = true; runError.value = ''
  try {
    report.value = await eventStudyApi.run(buildPayload())
    await nextTick(); renderCharts()
  } catch (error) {
    runError.value = error?.response?.data?.detail || error?.message || '事件研究运行失败'
  } finally { running.value = false }
}
function tone(value) { const n = Number(value); return !Number.isFinite(n) || n === 0 ? 'flat' : n > 0 ? 'up' : 'down' }
function formatPct(value, signed = false) { const n = Number(value); return value == null || !Number.isFinite(n) ? '-' : `${signed && n > 0 ? '+' : ''}${n.toFixed(2)}%` }
function formatNumber(value, digits = 2) { const n = Number(value); return value == null || !Number.isFinite(n) ? '-' : n.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '') }
function formatT(value) { const n = Number(value); return value == null || !Number.isFinite(n) ? '-' : n.toFixed(2) }
function diagnosticText(item) {
  if (item.value && typeof item.value === 'object') return Object.entries(item.value).map(([key, value]) => `${key}=${Array.isArray(value) ? `[${value.join(', ')}]` : value}`).join(' · ')
  if (item.value_pct != null) return `${formatPct(item.value_pct, true)} · ${item.direction === 'above' ? '上方' : '下方'}`
  const range = item.min != null || item.max != null ? ` [${item.min ?? '-'}, ${item.max ?? '-'}]` : ''
  return `${item.value ?? '无可用值'}${range}`
}
function baseChart() {
  return { animationDuration: 320, textStyle: { fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif" }, tooltip: { trigger: 'axis', backgroundColor: '#111b2d', borderWidth: 0, textStyle: { color: '#fff', fontSize: 11 } } }
}
function renderCharts() {
  if (!hasChartData.value) { returnChart?.dispose(); distributionChart?.dispose(); returnChart = null; distributionChart = null; return }
  const rows = statistics.value
  if (returnChartEl.value) {
    if (!returnChart) returnChart = echarts.init(returnChartEl.value)
    const errorData = rows.map((row, index) => [index, row.ci95_low_pct, row.ci95_high_pct])
    returnChart.setOption({ ...baseChart(), legend: { top: 8, right: 12, itemWidth: 14, textStyle: { fontSize: 10 } }, grid: { left: 52, right: 24, top: 48, bottom: 36 }, xAxis: { type: 'category', data: rows.map((row) => `T+${row.horizon}`), axisTick: { show: false }, axisLine: { lineStyle: { color: '#cfd5de' } } }, yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#7b8492' }, splitLine: { lineStyle: { color: '#edf0f4' } } }, series: [
      { name: '平均', type: 'line', data: rows.map((row) => row.mean_pct), symbol: 'circle', symbolSize: 7, lineStyle: { width: 2, color: '#ef232a' }, itemStyle: { color: '#ef232a' } },
      { name: '事件日等权', type: 'line', data: rows.map((row) => row.date_weighted?.mean_pct ?? null), symbol: 'triangle', symbolSize: 7, lineStyle: { width: 1.5, type: 'dotted', color: '#d28a16' }, itemStyle: { color: '#d28a16' } },
      { name: '中位数', type: 'line', data: rows.map((row) => row.median_pct), symbol: 'diamond', symbolSize: 7, lineStyle: { width: 1.5, type: 'dashed', color: '#31445f' }, itemStyle: { color: '#31445f' } },
      { name: '基准超额', type: 'bar', data: rows.map((row) => ({ value: row.benchmark_excess_mean_pct, itemStyle: { color: Number(row.benchmark_excess_mean_pct) >= 0 ? 'rgba(239,35,42,.23)' : 'rgba(20,177,67,.25)' } })), barMaxWidth: 24 },
      { name: '95% CI', type: 'custom', data: errorData, tooltip: { show: false }, renderItem(params, api) { const lowValue = Number(api.value(1)), highValue = Number(api.value(2)); if (!Number.isFinite(lowValue) || !Number.isFinite(highValue)) return null; const x = api.coord([api.value(0), 0])[0], low = api.coord([0, lowValue])[1], high = api.coord([0, highValue])[1]; return { type: 'group', children: [{ type: 'line', shape: { x1: x, y1: low, x2: x, y2: high }, style: { stroke: '#ef232a', lineWidth: 1.3 } }, { type: 'line', shape: { x1: x - 5, y1: low, x2: x + 5, y2: low }, style: { stroke: '#ef232a' } }, { type: 'line', shape: { x1: x - 5, y1: high, x2: x + 5, y2: high }, style: { stroke: '#ef232a' } }] } } },
    ] }, true)
  }
  if (distributionChartEl.value) {
    if (!distributionChart) distributionChart = echarts.init(distributionChartEl.value)
    distributionChart.setOption({ ...baseChart(), legend: { top: 8, right: 12, itemWidth: 14, textStyle: { fontSize: 10 } }, grid: { left: 52, right: 52, top: 48, bottom: 36 }, xAxis: { type: 'category', data: rows.map((row) => `T+${row.horizon}`), axisTick: { show: false }, axisLine: { lineStyle: { color: '#cfd5de' } } }, yAxis: [{ type: 'value', axisLabel: { formatter: '{value}%', color: '#7b8492' }, splitLine: { lineStyle: { color: '#edf0f4' } } }, { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%', color: '#7b8492' }, splitLine: { show: false } }], series: [
      { name: '收益分布', type: 'boxplot', data: rows.map((row) => [row.min_pct, row.p25_pct, row.median_pct, row.p75_pct, row.max_pct]), itemStyle: { color: '#f1f5fb', borderColor: '#2e6bc6', borderWidth: 1.5 } },
      { name: '胜率', type: 'line', yAxisIndex: 1, data: rows.map((row) => row.win_rate_pct), symbol: 'circle', symbolSize: 7, lineStyle: { color: '#d28a16', width: 2 }, itemStyle: { color: '#d28a16' } },
    ] }, true)
  }
}
function handleResize() { returnChart?.resize(); distributionChart?.resize() }
onMounted(() => { loadMeta(); window.addEventListener('resize', handleResize) })
onBeforeUnmount(() => { window.removeEventListener('resize', handleResize); returnChart?.dispose(); distributionChart?.dispose() })
</script>

<style scoped>
.event-page { padding-bottom:42px; }.mono { font-family:var(--font-mono); font-variant-numeric:tabular-nums; }.up { color:var(--c-up)!important; }.down { color:var(--c-down)!important; }.flat { color:var(--c-flat)!important; }
.engine-badge { padding:3px 7px; border:1px solid #c8d6e9; background:#edf3fb; color:#315b94; font:600 9px var(--font-mono); letter-spacing:.06em; }.run-scope { color:var(--c-text-3); font-size:9px; }
.availability-strip { display:grid; grid-template-columns:auto auto auto auto minmax(220px,1fr); align-items:center; gap:18px; padding:9px 13px; margin-bottom:10px; border:1px solid #d8dee7; border-left:3px solid #d18a18; background:#fffdf7; font-size:10px; }.availability-title,.field-state { display:flex; align-items:center; gap:6px; white-space:nowrap; }.availability-title strong { color:#775512; font:700 9px var(--font-mono); letter-spacing:.08em; }.pulse,.field-state i { width:7px; height:7px; border-radius:50%; flex:none; }.pulse,.field-state i.warn { background:#d18a18; box-shadow:0 0 0 3px rgba(209,138,24,.12); }.field-state i.ok { background:#2e6bc6; }.field-state i.bad { background:var(--c-down); }.field-state b { color:var(--c-text-2); font-weight:600; }.availability-strip p { color:var(--c-text-3); line-height:1.4; text-align:right; }.availability-strip.unavailable { border-left-color:var(--c-down); }
.notice { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:9px 12px; margin-bottom:10px; font-size:11px; }.notice.error { border:1px solid #edb7b7; background:#fff3f3; color:#8b2f32; }
.workbench { display:grid; grid-template-columns:230px minmax(0,1fr); background:#fff; border:1px solid var(--c-border); box-shadow:var(--shadow-card); }.preset-rail { padding:15px 12px; background:#f5f7fa; border-right:1px solid var(--c-border); }.preset-rail header { padding:0 3px 10px; }.preset-rail header span,.section-head span,.result-header > div > span,.method-lead > span,.empty-result > div:last-child > span { color:var(--c-primary); font:600 9px var(--font-mono); letter-spacing:.1em; }.preset-rail h2,.section-head h2 { font-size:15px; margin-top:4px; }.preset-rail header p,.section-head p { color:var(--c-text-3); font-size:9px; margin-top:3px; }.preset-card { position:relative; width:100%; display:flex; flex-direction:column; align-items:flex-start; gap:5px; padding:10px; margin-top:7px; border:1px solid #dde2e9; border-left:2px solid transparent; border-radius:3px; background:#fff; text-align:left; cursor:pointer; transition:border-color .15s, transform .15s, box-shadow .15s; }.preset-card:hover { transform:translateY(-1px); border-color:#bfc9d6; box-shadow:0 4px 12px rgba(25,39,58,.06); }.preset-card.active { border-color:#b9cceb; border-left-color:var(--c-primary); background:#f5f8fd; }.preset-code { color:#8b96a5; font-size:8px; text-transform:uppercase; }.preset-card strong { color:var(--c-ink); font-size:11px; }.preset-card small { color:var(--c-text-3); font-size:9px; line-height:1.45; }.preset-empty { padding:18px 5px; color:var(--c-text-3); font-size:10px; }.saved-divider { display:flex; align-items:center; justify-content:space-between; margin-top:16px; padding:9px 3px 2px; border-top:1px solid var(--c-border); color:var(--c-primary); font:600 9px var(--font-mono); letter-spacing:.1em; }.saved-card { padding:0; cursor:default; }.saved-load { width:100%; display:flex; flex-direction:column; align-items:flex-start; gap:5px; padding:10px 34px 10px 10px; border:0; background:transparent; text-align:left; cursor:pointer; }.saved-delete { position:absolute; right:4px; top:2px; opacity:0; }.saved-card:hover .saved-delete,.saved-card:focus-within .saved-delete { opacity:1; }
.builder-panel { min-width:0; padding:14px; }.section-head { display:flex; align-items:flex-end; justify-content:space-between; gap:14px; padding-bottom:10px; border-bottom:1px solid var(--c-border); }.logic-switch { display:flex; align-items:center; gap:8px; }.logic-switch label,.field label,.rule-name-row label,.config-cell > label { color:var(--c-text-3); font-size:9px; font-weight:600; }.rule-name-row { display:grid; grid-template-columns:86px 1fr; align-items:center; gap:10px; padding:10px 0; }.rule-name-row :deep(.el-input) { max-width:520px; }
.condition-stack { display:flex; flex-direction:column; gap:7px; }.condition-row { display:grid; grid-template-columns:38px 1fr; border:1px solid #dde2e9; border-radius:4px; background:#fbfcfd; overflow:hidden; }.condition-index { display:grid; place-items:center; color:#8a96a6; font-size:10px; background:#f0f3f7; border-right:1px solid #dde2e9; }.condition-body { min-width:0; padding:9px 10px 8px; }.condition-main { display:flex; align-items:flex-end; gap:8px; }.field { display:flex; flex-direction:column; gap:4px; }.condition-type { width:220px; }.field.compact { width:128px; }.direction-field { width:210px; }.field :deep(.el-input-number),.field :deep(.el-select),.config-cell :deep(.el-select),.config-cell :deep(.el-input-number) { width:100%; }.range-mark { color:#a0a9b5; padding-bottom:9px; }.delete-condition { margin-left:auto; display:grid; place-items:center; width:34px; height:32px; border:1px solid #e0e4ea; border-radius:4px; background:#fff; color:#8b96a5; cursor:pointer; }.delete-condition:hover:not(:disabled) { color:var(--c-down); border-color:#addbbb; }.delete-condition:disabled { opacity:.35; cursor:not-allowed; }.pullback-fields { display:flex; align-items:flex-end; flex-wrap:wrap; gap:8px 12px; padding-top:9px; margin-top:8px; border-top:1px dashed #dce1e8; }.pullback-fields :deep(.el-checkbox) { margin-right:0; height:32px; }.condition-note { color:var(--c-text-3); font-size:9px; line-height:1.4; margin-top:7px; }.add-condition { min-height:36px; width:100%; display:flex; align-items:center; justify-content:center; gap:6px; margin-top:8px; border:1px dashed #b9c5d3; border-radius:4px; background:#f8fafc; color:#45648e; font:600 10px inherit; cursor:pointer; }.add-condition:hover { border-color:var(--c-primary); background:#f2f6fc; }
.config-panel { margin-top:10px; padding:14px; background:#fff; border:1px solid var(--c-border); box-shadow:var(--shadow-card); }.universe-grid { display:grid; grid-template-columns:1fr 1.4fr 1.2fr; border-left:1px solid var(--c-border); border-top:1px solid var(--c-border); margin-top:11px; }.universe-cell { min-width:0; display:flex; flex-direction:column; justify-content:center; gap:7px; padding:9px 11px; border:0; border-right:1px solid var(--c-border); border-bottom:1px solid var(--c-border); margin:0; }.universe-cell legend { color:var(--c-text-3); font-size:9px; font-weight:600; padding:0; }.universe-cell :deep(.el-checkbox) { margin-right:14px; margin-left:0; }.toggle-cell,.board-cell { background:#fbfcfd; }.range-cell { display:grid; grid-template-columns:repeat(3,1fr); align-items:end; }.range-cell .field.compact { width:100%; }.cell-note { color:#b0b7c0; font-size:8px; line-height:1.5; margin:0; }.config-grid { display:grid; grid-template-columns:1.5fr repeat(4,1fr); border-left:1px solid var(--c-border); border-top:1px solid var(--c-border); margin-top:11px; }.config-cell { min-width:0; display:flex; flex-direction:column; justify-content:center; gap:6px; padding:9px; border-right:1px solid var(--c-border); border-bottom:1px solid var(--c-border); }.config-cell.muted { background:#f7f8fa; }.date-cell { grid-column:span 2; }.date-cell :deep(.el-date-editor) { width:100%; }.symbol-cell { grid-column:span 2; }.config-cell label small { color:#b0b7c0; font-weight:400; margin-left:4px; }.horizon-cell { grid-column:span 3; border:0; border-right:1px solid var(--c-border); border-bottom:1px solid var(--c-border); }.horizon-cell legend { color:var(--c-text-3); font-size:9px; font-weight:600; }.horizon-cell :deep(.el-checkbox) { margin-right:14px; }.config-foot { display:flex; align-items:center; gap:18px; padding-top:11px; color:var(--c-text-3); font-size:9px; }.config-foot b { color:var(--c-text-2); }.config-foot .el-button { margin-left:auto; }
.loading-panel { margin-top:10px; padding:20px; background:#fff; border:1px solid var(--c-border); }.result-header { display:flex; justify-content:space-between; align-items:stretch; gap:20px; margin-top:10px; padding:15px 17px; background:var(--c-navy); color:#fff; border-radius:5px 5px 0 0; }.result-header h2 { color:#fff; font-size:18px; margin:4px 0; }.result-header p { color:#8fa0b7; font-size:10px; }.result-counters { display:grid; grid-template-columns:repeat(4,90px); }.result-counters div { display:flex; flex-direction:column; justify-content:center; padding:0 12px; border-left:1px solid rgba(255,255,255,.12); }.result-counters small { color:#8293aa; font-size:9px; }.result-counters strong { color:#fff; font-size:20px; margin-top:3px; }.warning-stack { display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding:8px 13px; border:1px solid #ead7a6; border-top:0; background:#fff9e9; color:#765411; font-size:9px; }.warning-stack span::before { content:'·'; margin-right:6px; }
.horizon-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(205px,1fr)); gap:8px; margin-top:10px; }.horizon-card { min-width:0; padding:11px 12px 9px; background:#fff; border:1px solid var(--c-border); border-top:2px solid #263b59; box-shadow:var(--shadow-card); }.horizon-card header { display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid #edf0f4; }.horizon-card header span { color:#263b59; font-size:12px; font-weight:700; }.horizon-card header small { color:var(--c-text-3); font-size:8px; }.primary-stat { display:flex; align-items:flex-end; justify-content:space-between; padding:9px 0; }.primary-stat small,.stat-pairs small { color:var(--c-text-3); font-size:9px; }.primary-stat strong { font-size:24px; letter-spacing:-.04em; }.stat-pairs { display:grid; grid-template-columns:1fr 1fr; gap:7px; }.stat-pairs div { display:flex; flex-direction:column; gap:2px; }.stat-pairs b { font-size:10px; }.dual-line { display:flex; align-items:center; justify-content:space-between; gap:6px; margin-top:8px; padding:5px 7px; background:#f5f8fc; border:1px solid #e3eaf3; font-size:8px; color:var(--c-text-3); }.dual-line b { font-size:10px; }.dual-line em { font-style:normal; color:#8b96a5; font-size:8px; }.ci-line { display:flex; justify-content:space-between; gap:6px; margin-top:8px; padding-top:7px; border-top:1px solid #edf0f4; color:var(--c-text-3); font-size:8px; }.ci-line b { color:var(--c-text-2); font-weight:500; }
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px; }.result-panel,.events-panel { min-width:0; background:#fff; border:1px solid var(--c-border); box-shadow:var(--shadow-card); }.panel-title { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; padding:11px 13px 8px; border-bottom:1px solid var(--c-border); }.panel-title h2 { font-size:13px; }.panel-title p { color:var(--c-text-3); font-size:9px; margin-top:3px; line-height:1.4; }.result-chart { width:100%; height:300px; }.events-panel { margin-top:10px; }.table-stamp { color:var(--c-text-3); font-size:8px; }.table-scroll { overflow-x:auto; }.events-panel :deep(.el-table) { min-width:750px; }.events-panel :deep(.el-table__cell) { padding:6px 0; }.events-panel :deep(th.el-table__cell) { font-size:9px; }.events-panel :deep(.el-table__expanded-cell) { padding:0!important; background:#f6f8fb; }.stock-id { display:flex; flex-direction:column; gap:2px; }.stock-id b { font-size:10px; }.stock-id span { color:var(--c-text-3); font-size:9px; }.event-detail { display:grid; grid-template-columns:1.4fr 1fr 1fr; gap:0; padding:12px 42px; }.event-detail > div { padding:0 15px; border-left:1px solid var(--c-border); }.event-detail > div:first-child { border-left:0; padding-left:0; }.event-detail h3 { font-size:10px; margin-bottom:7px; }.event-detail dl div { display:flex; justify-content:space-between; gap:12px; padding:4px 0; border-bottom:1px solid #e9edf2; font-size:9px; }.event-detail dt { color:var(--c-text-3); }.event-detail dd { max-width:70%; text-align:right; color:var(--c-text-2); overflow-wrap:anywhere; }
.methodology-panel { display:grid; grid-template-columns:55px 220px 1fr; gap:16px; margin-top:10px; padding:15px; border:1px solid var(--c-border); border-left:3px solid var(--c-primary); background:#f8fafc; }.method-mark { color:#d8dfe8; font:700 46px/1 Georgia,serif; }.method-lead h2 { font-size:14px; margin:4px 0 6px; }.method-lead p,.method-facts p { color:var(--c-text-2); font-size:9px; line-height:1.55; }.method-facts { display:grid; grid-template-columns:repeat(4,1fr); }.method-facts div { padding:2px 12px; border-left:1px solid var(--c-border); }.method-facts b { font-size:9px; }.method-facts p { color:var(--c-text-3); margin-top:5px; }.coverage-bar { grid-column:2/-1; display:grid; grid-template-columns:130px 1fr auto; align-items:center; gap:10px; padding-top:10px; border-top:1px solid var(--c-border); color:var(--c-text-2); font-size:9px; }.coverage-bar > div { height:5px; background:#e2e7ee; }.coverage-bar i { display:block; height:100%; background:var(--c-primary); }.empty-result { min-height:270px; display:flex; align-items:center; justify-content:center; gap:28px; margin-top:10px; background:#fff; border:1px solid var(--c-border); }.empty-axis { position:relative; width:135px; height:100px; border-left:1px solid #cdd4dd; border-bottom:1px solid #cdd4dd; }.empty-axis i,.empty-axis b,.empty-axis span { position:absolute; bottom:0; width:16px; background:#dce3ec; }.empty-axis i { left:20px; height:35px; }.empty-axis b { left:58px; height:75px; }.empty-axis span { left:96px; height:52px; }.empty-axis::after { content:''; position:absolute; left:0; right:0; top:46%; border-top:1px dashed #cbd3dd; }.empty-result h2 { font-size:19px; margin:6px 0; }.empty-result p { max-width:430px; color:var(--c-text-3); font-size:10px; line-height:1.6; }
@media (max-width:1200px) { .config-grid { grid-template-columns:repeat(3,1fr); }.date-cell,.symbol-cell,.horizon-cell { grid-column:span 2; }.result-header { flex-direction:column; }.result-counters { grid-template-columns:repeat(4,1fr); }.methodology-panel { grid-template-columns:45px 190px 1fr; }.method-facts { grid-template-columns:1fr 1fr; row-gap:12px; } }
@media (max-width:900px) { .availability-strip { grid-template-columns:repeat(2,1fr); gap:8px 14px; }.availability-strip p { grid-column:1/-1; text-align:left; }.workbench { grid-template-columns:1fr; }.preset-rail { border-right:0; border-bottom:1px solid var(--c-border); display:grid; grid-template-columns:repeat(3,1fr); gap:7px; }.preset-rail header { grid-column:1/-1; }.preset-card { margin-top:0; }.universe-grid { grid-template-columns:1fr; }.range-cell { grid-template-columns:repeat(3,1fr); }.chart-grid { grid-template-columns:1fr; }.methodology-panel { grid-template-columns:40px 1fr; }.method-facts,.coverage-bar { grid-column:2; }.event-detail { grid-template-columns:1fr 1fr; }.event-detail > div:nth-child(3) { border-left:0; padding-left:0; margin-top:12px; } }
@media (max-width:650px) { .availability-strip { grid-template-columns:1fr; }.availability-strip p { grid-column:auto; }.run-scope { display:none; }.preset-rail { grid-template-columns:1fr; }.builder-panel,.config-panel { padding:11px; }.section-head { align-items:flex-start; flex-direction:column; }.logic-switch { align-items:flex-start; flex-direction:column; width:100%; }.rule-name-row { grid-template-columns:1fr; }.condition-row { grid-template-columns:30px 1fr; }.condition-main { flex-wrap:wrap; }.condition-type,.direction-field { width:calc(100% - 44px); }.field.compact { width:calc(50% - 16px); }.range-mark { display:none; }.delete-condition { order:2; }.config-grid { grid-template-columns:1fr; }.date-cell,.symbol-cell,.horizon-cell { grid-column:auto; }.range-cell { grid-template-columns:1fr; }.config-foot { align-items:flex-start; flex-direction:column; gap:7px; }.config-foot .el-button { width:100%; margin-left:0; }.result-counters { grid-template-columns:repeat(2,1fr); gap:10px 0; }.result-counters div:nth-child(odd) { border-left:0; }.horizon-cards { grid-template-columns:1fr; }.event-detail { grid-template-columns:1fr; padding:12px 40px; }.event-detail > div,.event-detail > div:nth-child(3) { border-left:0; border-top:1px solid var(--c-border); padding:10px 0; margin:0; }.event-detail > div:first-child { border-top:0; padding-top:0; }.methodology-panel { grid-template-columns:1fr; }.method-mark { display:none; }.method-facts,.coverage-bar { grid-column:auto; }.method-facts { grid-template-columns:1fr; }.method-facts div { border-left:0; border-top:1px solid var(--c-border); padding:9px 0; }.coverage-bar { grid-template-columns:1fr; }.empty-result { padding:28px 20px; }.empty-axis { display:none; }.result-chart { height:270px; } }
</style>
