<template>
  <MainLayout>
    <div class="page">
      <!-- 椤舵爮锛氭爣棰?+ 鍒锋柊 + 鍘嗗彶鏃ユ湡 + 瑙﹀彂鐢熸垚 -->
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">姣忔棩澶嶇洏 <span class="fs12" style="color:#7d8390">路 A鑲℃父璧勬绾富棰?/span></h2>
        <el-button size="small" type="primary" :loading="loading" @click="load">鍒锋柊</el-button>
        <el-select v-if="historyDates.length" v-model="viewDate" size="small" style="width:170px;margin-left:8px"
          placeholder="鍘嗗彶澶嶇洏鏃ユ湡" @change="(d) => viewReport(d)">
          <el-option v-for="d in historyDates" :key="d" :label="d" :value="d" />
        </el-select>
        <el-tag v-if="rpt?.date" size="small" type="info" style="margin-left:8px">鏌ョ湅 {{ rpt.date }}</el-tag>
        <el-select v-model="triggerDate" size="small" style="width:150px;margin-left:8px">
          <el-option v-for="i in 30" :key="i" :label="dateStr(i) + (i === 0 ? '锛堜粖鏃ワ級' : '')" :value="dateStr(i)" />
        </el-select>
        <el-button size="small" :loading="triggering" @click="trigger"
          :type="status === 'pending' ? 'danger' : 'warning'">
          鐢熸垚澶嶇洏
        </el-button>
        <el-tag v-if="status === 'pending'" size="small" type="warning">浠婃棩灏氭湭鐢熸垚锛屼氦鏄撴棩 18:00 鑷姩澶嶇洏</el-tag>
        <el-tag v-if="status === 'empty'" size="small" type="info">鏆傛棤澶嶇洏璁板綍</el-tag>
        <div style="flex:1"></div>
        <el-button v-if="rpt?.report_md" size="small" @click="mdDialog = true">鏌ョ湅澶嶇洏鍘熸枃 (Markdown)</el-button>
      </div>

      <el-alert
        v-if="status === 'pending'"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
        :title="report?.message || '浠婃棩澶嶇洏灏氭湭鐢熸垚锛屼氦鏄撴棩 18:00 灏嗚嚜鍔ㄧ敓鎴愶紝涔熷彲鐐瑰嚮銆岀敓鎴愬鐩樸€嶇珛鍗崇敓鎴?"
      />

      <el-alert
        v-if="status === 'gated'"
        type="error"
        :closable="false"
        show-icon
        class="mt8"
        :title="report?.message || '褰撳墠鏃堕棿鍙楅檺锛屾棤娉曠敓鎴愯鏃ユ湡澶嶇洏'"
      />

      <el-alert
        v-if="rpt && (status === 'ready' || status === 'pending')"
        type="warning"
        :closable="false"
        show-icon
        class="mt8"
        title="甯傚満鏁版嵁浠ヤ笢鏂硅储瀵屽綋鏃ユ敹鐩樹负鍑嗭紱鍚屼竴浜ゆ槗鏃ュ娆＄敓鎴愬彧淇濈暀鏈€鏂颁竴浠藉鐩?
      />
      <el-alert
        v-if="rpt && rpt.sector_flow?.length === undefined"
        type="info"
        :closable="false"
        show-icon
        class="mt8"
        title="鏉垮潡璧勯噾娴佹暟鎹湪浼戞伅鏃舵鍙兘涓虹┖"
      />

      <template v-if="rpt">
        <!-- 鎯呯华 KPI 鏉?-->
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">娑ㄥ仠瀹舵暟</div>
            <div class="kpi-val up">{{ rpt.limit_up_count ?? '-' }}<span class="kpi-unit">瀹?/span></div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">璺屽仠瀹舵暟</div>
            <div class="kpi-val down">{{ rpt.limit_down_count ?? '-' }}<span class="kpi-unit">瀹?/span></div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">涓婃定瀹舵暟</div>
            <div class="kpi-val up">{{ rpt.market_summary?.distribution?.up_count ?? '-' }}<span class="kpi-unit">瀹?/span></div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">涓嬭穼瀹舵暟</div>
            <div class="kpi-val down">{{ rpt.market_summary?.distribution?.down_count ?? '-' }}<span class="kpi-unit">瀹?/span></div>
          </div>
          <div class="kpi-card accent">
            <div class="kpi-label">鏈€楂樿繛鏉?/div>
            <div class="kpi-val" style="color:#f7b32b">{{ maxBoard || '-' }}<span class="kpi-unit">鏉?/span></div>
          </div>
          <div class="kpi-card accent">
            <div class="kpi-label">鎯呯华娓╁害</div>
            <div class="kpi-val" style="color:#f7b32b">{{ sentimentScore }}<span class="kpi-unit">/100</span></div>
          </div>
        </div>

        <!-- 澶х洏姒傚喌锛堝幓鎺変笂璇佹寚鏁癒绾匡細澶嶇洏涓嶇湅K绾垮舰鎬侊級 -->
        <div class="card mt8">
          <div class="fs14 bold">澶х洏姒傚喌</div>
          <el-table :data="arr(rpt.market_summary?.indices) || []" size="small" class="mt8">
            <el-table-column prop="name" label="鎸囨暟" />
            <el-table-column prop="price" label="鐐逛綅" align="right" />
            <el-table-column label="娑ㄨ穼骞? align="right">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct }}%</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="fs12 mt8" style="color:#7d8390">
            娑ㄥ仠 {{ arr(rpt.market_summary?.distribution) && (rpt.market_summary?.distribution) ? (rpt.market_summary?.distribution.up_count ?? '-') : '-' }} / 璺屽仠 {{ arr(rpt.market_summary?.distribution) && (rpt.market_summary?.distribution) ? (rpt.market_summary?.distribution.down_count ?? '-') : '-' }}
          </div>
          <div class="fs12 mt8" v-if="arr(rpt.market_summary?.news).length">
            <span class="bold">瑕侀椈锛?/span>{{ rpt.market_summary.news[0].title }}
          </div>
        </div>

        <!-- 娑ㄨ穼鍒嗗竷 + 鏉垮潡璧勯噾娴?TOP鍥捐〃 -->
        <el-row :gutter="10" class="mt8">
          <el-col :xs="24" :sm="12">
            <div class="card">
              <div class="fs14 bold">娑ㄨ穼鍒嗗竷</div>
              <div ref="distEl" style="height:200px" class="mt8"></div>
              <div class="fs12 mt4" style="color:#7d8390">涓婃定 vs 涓嬭穼 vs 骞崇洏锛堝惈娑ㄥ仠/璺屽仠鏍囪锛?/div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="card">
              <div class="fs14 bold">鏉垮潡璧勯噾娴?TOP10 <span class="fs12" style="color:#7d8390">锛堜富鍔涘噣娴佸叆锛?/span></div>
              <div ref="sectorEl" style="height:200px" class="mt8"></div>
            </div>
          </el-col>
        </el-row>

        <!-- 娑ㄥ仠姊槦 杩炴澘楂樺害鍥?+ 姊槦 -->
        <div class="card mt8">
          <div class="fs14 bold">娑ㄥ仠姊槦 <span class="fs12" style="color:#7d8390">锛堣繛鏉块珮搴︽煴鐘跺浘锛?/span></div>
          <div ref="ladderEl" style="height:200px" class="mt8"></div>
        </div>

        <div class="card mt8">
          <div class="fs14 bold">娑ㄥ仠姊槦鏄庣粏</div>
          <div class="ladder-scroller mt8">
            <div v-for="(stocks, board) in sortedLadder" :key="board" class="ladder-group">
              <div class="ladder-header">
                <el-tag size="small" :type="Number(board) >= 3 ? 'danger' : Number(board) >= 2 ? 'warning' : 'info'">
                  杩炴澘{{ board }}路 {{ arr(stocks).length }}鍙?                </el-tag>
                <span v-if="Number(board) === maxBoard" class="fs11" style="color:#f7b32b;margin-left:4px">馃敟鏈€楂樻澘</span>
              </div>
              <div class="ladder-stocks">
                <el-link v-for="s in arr(stocks)" :key="s.symbol" type="primary" :underline="false"
                  @click="goStock(s.symbol, s.name)" style="margin-right:10px">
                  {{ s.name }}
                  <span class="mono" :class="(s.change_pct||0) >= 0 ? 'up' : 'down'">{{ s.change_pct == null ? '' : (s.change_pct >= 0 ? '+' : '') + s.change_pct + '%' }}</span>
                </el-link>
              </div>
            </div>
            <el-empty v-if="!Object.keys(sortedLadder).length" description="褰撴棩鏃犳定鍋滄闃燂紙鏁版嵁婧愬彈闄愶級" :image-size="40" />
          </div>
        </div>

        <!-- 鏉垮潡璧勯噾娴?鏄庣粏琛?-->
        <div class="card mt8">
          <div class="fs14 bold">鏉垮潡璧勯噾娴佹槑缁?<span class="fs12" style="color:#7d8390">锛堜富鍔涘噣娴佸叆鎺掑簭锛?/span></div>
          <el-table :data="arr(rpt.sector_flow).slice(0, 12)" size="small" class="mt8">
            <el-table-column prop="sector_name" label="鏉垮潡" min-width="110">
              <template #default="{ row }">{{ row.sector_name || row.name }}</template>
            </el-table-column>
            <el-table-column label="涓诲姏鍑€" align="right" width="90">
              <template #default="{ row }">
                <span class="mono" :class="(row.net_inflow||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_inflow) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="鍑€鍗犳瘮" align="right" width="70">
              <template #default="{ row }">{{ row.net_ratio == null ? '-' : row.net_ratio + '%' }}</template>
            </el-table-column>
            <el-table-column label="娑ㄥ箙" align="right" width="70">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + row.change_pct + '%') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="娑ㄥ仠" align="right" width="64">
              <template #default="{ row }">
                <span class="mono up">{{ row.limit_up_count ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="璺屽仠" align="right" width="64">
              <template #default="{ row }">
                <span class="mono down">{{ row.limit_down_count ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="棰嗘定" min-width="90">
              <template #default="{ row }">
                <el-link v-if="row.leader_symbol" type="primary" :underline="false" @click="goStock(row.leader_symbol, row.leader)">
                  {{ row.leader || '-' }}
                </el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="甯傚€奸緳澶? min-width="130">
              <template #default="{ row }">
                <span v-for="(m, i) in (row.mkt_cap_top || [])" :key="i" class="fs12 mr8">
                  {{ ['榫欎竴', '榫欎簩', '榫欎笁'][i] }}:
                  <el-link v-if="m.symbol" type="primary" :underline="false" @click="goStock(m.symbol, m.name)">{{ m.name }}</el-link>
                </span>
                <span v-if="!(row.mkt_cap_top || []).length">-</span>
              </template>
            </el-table-column>
            <el-table-column label="浜烘皵绁? width="70">
              <template #default="{ row }">
                <el-link v-if="row.hot_pick?.symbol" type="primary" :underline="false" @click="goStock(row.hot_pick.symbol, row.hot_pick.name)">{{ row.hot_pick.name }}</el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!arr(rpt.sector_flow).length" description="褰撴棩涓滄柟璐㈠瘜鏉垮潡璧勯噾鏁版嵁涓虹┖锛堜紤甯傛垨缃戠粶鍙楅檺锛? :image-size="50" />
        </div>

        <!-- 榫欒檸姒?+ 甯綅娓歌祫 -->
        <div class="card mt8">
          <div class="fs14 bold">榫欒檸姒滐紙{{ arr(rpt.limit_analysis?.dragon_tiger).length }}锛?/div>
          <el-table :data="arr(rpt.limit_analysis?.dragon_tiger).slice(0, 10)" size="small" class="mt8"
            @row-click="(row) => goStock(row.symbol, row.name)">
            <el-table-column prop="name" label="鍚嶇О" width="74" />
            <el-table-column prop="symbol" label="浠ｇ爜" width="88" />
            <el-table-column label="鍑€涔伴" align="right" width="86">
              <template #default="{ row }">
                <span class="mono" :class="(row.net_amount||0) >= 0 ? 'up' : 'down'">{{ fmtBig(row.net_amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="娑ㄥ箙" width="62" align="right">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">{{ row.change_pct == null ? '-' : ((row.change_pct >= 0 ? '+' : '') + row.change_pct + '%') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="鍘熷洜" min-width="140">
              <template #default="{ row }">{{ (row.reason || '').slice(0, 20) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!arr(rpt.limit_analysis?.dragon_tiger).length" description="褰撴棩榫欒檸姒滄暟鎹负绌猴紙鏀剁洏鍚庢墠鍙戝竷锛? :image-size="50" />
          <div v-if="seats.length" class="mt8" style="border-top:1px dashed #f0f0f0;padding-top:6px">
            <div class="fs12 bold" style="color:#e6a23c">甯綅娓歌祫锛坽{ seats.length }}鏉★紝鎸夊噣鍊硷級</div>
            <div v-for="s in seats" :key="s.seat + s.symbol" class="seat-row">
              <el-tag v-if="s.tag" size="small" type="warning" effect="plain">{{ s.tag }}</el-tag>
              <el-tag v-else size="small" type="info" effect="plain">钀ヤ笟閮?/el-tag>
              <el-link type="primary" :underline="false" @click="goStock(s.symbol, s.stock_name)">{{ s.stock_name }}</el-link>
              <span class="mono fs12" :class="(s.net||0) >= 0 ? 'up' : 'down'">{{ fmtBig(s.net) }}</span>
              <span class="fs11" style="color:#7d8390;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ s.seat_name }}</span>
            </div>
          </div>
        </div>

        <!-- 娆℃棩閫夎偂姹?-->
        <div class="card mt8">
          <div class="fs14 bold">娆℃棩閫夎偂姹狅紙{{ arr(rpt.stock_pool).length }}锛?/div>
          <el-table :data="arr(rpt.stock_pool)" size="small" class="mt8" @row-click="(row) => goStock(row.symbol, row.name)">
            <el-table-column prop="symbol" label="浠ｇ爜" width="95" />
            <el-table-column prop="name" label="鍚嶇О" width="90" />
            <el-table-column label="娑ㄥ箙" width="75" align="right">
              <template #default="{ row }">
                <span class="mono" :class="(row.change_pct||0) >= 0 ? 'up' : 'down'">
                  {{ (row.change_pct||0) >= 0 ? '+' : '' }}{{ row.change_pct || '-' }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="浠锋牸" width="70" align="right">
              <template #default="{ row }">{{ row.price || '-' }}</template>
            </el-table-column>
            <el-table-column label="琛ㄧ幇" min-width="100">
              <template #default="{ row }">{{ row.performance || row.reason || '-' }}</template>
            </el-table-column>
            <el-table-column label="寤鸿" min-width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="(row.suggestion||'').includes('鍏虫敞') ? 'warning' : 'info'">
                  {{ row.suggestion || '鍏虫敞' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!arr(rpt.stock_pool).length" description="鏆傛棤閫夎偂姹? :image-size="50" />
        </div>

        <!-- 鎶曡祫鏃ュ巻锛堟湭鏉?5澶?瑙ｇ / 鍒嗙孩闄ゆ潈锛?-->
        <div class="card mt8">
          <div class="flex between" style="align-items:center">
            <span class="fs14 bold">鎶曡祫鏃ュ巻 <span class="fs12" style="color:#7d8390">锛堟湭鏉?5澶?瑙ｇ / 鍒嗙孩闄ゆ潈锛?/span></span>
            <el-button size="small" :loading="calLoading" @click="loadCalendar">鍒锋柊</el-button>
          </div>
          <div class="split-grid mt8">
            <div class="cal-scroll">
              <div class="fs12 bold" style="color:#f56c6c;margin:2px 0">馃洝 闄愬敭瑙ｇ <span class="fs11" style="color:#7d8390">锛坽{ arr(calendar.unlocks).length }}绗旓紝TOP瑙ｇ甯傚€硷級</span></div>
              <div v-for="(u, i) in topUnlocks" :key="'u' + i" class="cal-row">
                <span class="cal-date">{{ (u.date || '').slice(5) }}</span>
                <el-link v-if="u.symbol" class="cal-name" type="danger" :underline="false" @click="goStock(u.symbol, u.name)">{{ u.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ u.name }}</span>
                <span class="cal-val mono fs12" style="color:#f56c6c">{{ u.market_cap_yi }}浜?/span>
                <span class="cal-sub">{{ u.type }}</span>
              </div>
              <el-empty v-if="!topUnlocks.length" description="鏈潵45澶╂棤瑙ｇ" :image-size="30" />
            </div>
            <div class="cal-scroll">
              <div class="fs12 bold" style="color:#67c23a;margin:2px 0">馃挵 鍒嗙孩闄ゆ潈 <span class="fs11" style="color:#7d8390">锛坽{ arr(calendar.dividends).length }}绗旓級</span></div>
              <div v-for="(d, i) in topDividends" :key="'d' + i" class="cal-row">
                <span class="cal-date">{{ (d.date || '').slice(5) }}</span>
                <el-link v-if="d.symbol" class="cal-name" type="success" :underline="false" @click="goStock(d.symbol, d.name)">{{ d.name }}</el-link>
                <span v-else class="fs12 cal-name">{{ d.name }}</span>
                <span class="cal-val mono fs12" style="color:#67c23a">{{ (d.record_date || '').slice(5) }}闄ゆ潈</span>
                <span class="cal-sub">{{ d.plan }}</span>
              </div>
              <el-empty v-if="!topDividends.length" description="鏈潵45澶╂棤鍒嗙孩闄ゆ潈" :image-size="30" />
            </div>
          </div>
        </div>

        <!-- Agent 澶嶇洏 -->
        <div v-if="arr(rpt.agent_reviews).length" class="card mt8">
          <div class="fs14 bold">AI 澶嶇洏锛坽{ arr(rpt.agent_reviews).length }} 涓?Agent锛?/div>
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

      <el-empty v-else :description="(status === 'empty' && report?.message) || '鏆傛棤澶嶇洏鎶ュ憡锛岀偣鍑汇€岀敓鎴愬鐩樸€嶆墜鍔ㄨЕ鍙戯紙榛樿浜ゆ槗鏃?18:00 鑷姩鐢熸垚锛?" />

      <el-dialog v-model="mdDialog" title="澶嶇洏鎶ュ憡鍘熸枃" width="700">
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
import { replayApi, marketApi } from '../api'
import * as echarts from 'echarts'

const router = useRouter()
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

const topUnlocks = computed(() => [...(calendar.value.unlocks || [])]
  .sort((a, b) => b.market_cap_yi - a.market_cap_yi).slice(0, 6))
const topDividends = computed(() => [...(calendar.value.dividends || [])]
  .sort((a, b) => (a.date || '').localeCompare(b.date || '')).slice(0, 6))

async function loadCalendar() {
  calLoading.value = true
  try { calendar.value = (await marketApi.investCalendar()) || { date: '', unlocks: [], dividends: [] } } catch { /* 淇濈暀鏃ф暟鎹?*/ }
  calLoading.value = false
}

async function loadSeats() {
  const d = rpt.value?.date
  if (!d) { seats.value = []; return }
  try {
    const rows = (await marketApi.dragonTigerSeats(d)) || []
    seats.value = rows.sort((a, b) => Math.abs(b.net || 0) - Math.abs(a.net || 0)).slice(0, 10)
  } catch { seats.value = [] }
}

const sortedLadder = computed(() => {
  const raw = rpt.value?.limit_analysis?.ladder || {}
  const entries = raw && typeof raw === 'object' && !Array.isArray(raw) && raw.ladder && typeof raw.ladder === 'object'
    ? raw.ladder
    : raw
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
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '浜?
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '涓?
  return n.toFixed(0)
}

function goStock(symbol, name) {
  if (!symbol) return
  try {
    const list = JSON.parse(localStorage.getItem('recent_viewed') || '[]')
    const filtered = list.filter(r => r.symbol !== symbol)
    filtered.unshift({ symbol, name: name || symbol, ts: Date.now() })
    localStorage.setItem('recent_viewed', JSON.stringify(filtered.slice(0, 30)))
  } catch {}
  router.push({ path: '/watchlist', query: { symbol } })
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

async function load() {
  loading.value = true
  try {
    const r = await replayApi.latest()
    report.value = r
    const d = rpt.value?.date || r?.date
    if (d) viewDate.value = d
    await loadSeats()
    await loadHistory()
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
      report.value = { status: 'empty', date: d, message: '璇ユ棩鏈熸殏鏃犲鐩樿褰曪紝鍙敤搴曢儴銆岀敓鎴愬鐩樸€嶄负璇ユ棩鏈熺敓鎴? }
      viewDate.value = d
    }
  } catch {
    report.value = { status: 'gated', date: d, message: '鍔犺浇澶辫触锛岃妫€鏌ュ悗绔湇鍔? }
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
        { value: up, name: '涓婃定 ' + up, itemStyle: { color: '#ef232a' } },
        { value: down, name: '涓嬭穼 ' + down, itemStyle: { color: '#14b143' } },
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
    xAxis: { type: 'value', axisLabel: { color: '#7d8390', fontSize: 10, formatter: (v) => v.toFixed(1) + '浜? }, splitLine: { lineStyle: { color: '#2c3240' } } },
    yAxis: { type: 'category', data: names, axisLabel: { color: '#c8ccd4', fontSize: 10 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: vals, barWidth: '55%',
      itemStyle: { color: (p) => (vals[p.dataIndex] >= 0 ? '#ef232a' : '#14b143'), borderRadius: 2 },
      label: { show: true, position: 'right', color: '#c8ccd4', fontSize: 10, formatter: (p) => p.value.toFixed(1) + '浜? },
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
    xAxis: { type: 'category', data: boards.map((b) => b + '鏉?), axisLabel: { color: '#c8ccd4', fontSize: 11 }, axisLine: { lineStyle: { color: '#2c3240' } } },
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
}

watch(rpt, () => { if (rpt.value) { nextTick(renderCharts) } }, { deep: false })

onMounted(() => {
  triggerDate.value = dateStr(0)
  load()
  loadCalendar()
  window.addEventListener('resize', resizeCharts)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  distChart && distChart.dispose()
  sectorChart && sectorChart.dispose()
  ladderChart && ladderChart.dispose()
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

/* 娣辫壊琛ㄦ牸寰皟 */
:deep(.el-table) { background: transparent; color: #d8dce6; }
:deep(.el-table tr), :deep(.el-table th.el-table__cell) { background: transparent; }
:deep(.el-table th.el-table__cell) { color: #8b93a1; }
:deep(.el-table--border, .el-table--group) { border-color: #2a2f3a; }
:deep(.el-table td.el-table__cell), :deep(.el-table th.el-table__cell.is-leaf) { border-bottom: 1px solid #2a2f3a; }
:deep(.el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell) { background: #232936; }
:deep(.el-link) { color: #ef6c6d; }

/* H5 绉诲姩绔€傞厤 */
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
