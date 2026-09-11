<template>
  <MainLayout>
    <div class="page">
      <div class="flex gap" style="align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h2 style="font-size:18px">实盘交易导入</h2>
        <el-button size="small" type="primary" :loading="loading" @click="load">刷新</el-button>
        <el-popconfirm title="删除全部交易记录？该操作不可撤销" @confirm="clearAll">
          <template #reference>
            <el-button size="small" type="danger" :loading="clearing">清空全部记录</el-button>
          </template>
        </el-popconfirm>
      </div>

      <el-row :gutter="10">
        <el-col :xs="24" :sm="14">
          <div class="card">
            <div class="fs14 bold">手动录入一条交易</div>
            <el-form inline class="mt8" label-width="0" @submit.prevent>
              <el-form-item>
                <el-select v-model="form.symbol" filterable remote :remote-method="searchStock" placeholder="搜索股票（代码/名称）" style="width:200px" :loading="searching" @change="onSymbol">
                  <el-option v-for="s in searchResults" :key="s.symbol" :label="`${s.name} ${s.symbol}`" :value="s.symbol" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-input v-model="form.name" placeholder="名称（可自动填充）" style="width:130px" />
              </el-form-item>
              <el-form-item>
                <el-radio-group v-model="form.action">
                  <el-radio-button value="buy">买入</el-radio-button>
                  <el-radio-button value="sell">卖出</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item>
                <el-input-number v-model="form.quantity" :min="1" placeholder="数量" style="width:110px" />
              </el-form-item>
              <el-form-item>
                <el-input-number v-model="form.price" :min="0.01" :precision="2" placeholder="价格" style="width:110px" />
              </el-form-item>
              <el-form-item>
                <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" placeholder="日期" style="width:140px" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="adding" @click="addManual">添加</el-button>
              </el-form-item>
            </el-form>
            <div class="fs12" style="color:#909399">支持买卖方向、数量、价格、日期；录入后自动重算持仓与盈亏。</div>
          </div>

          <div class="card mt8">
            <div class="fs14 bold">交割单 / CSV 批量导入</div>
            <div class="fs12 mt8" style="color:#909399">
              直接上传券商导出的交割单（CSV/Excel，支持同花顺 / 东方财富等，UTF-8 或 GBK 编码，自动识别列）
              — 列如：成交日期 / 证券代码 / 证券名称 / 买卖标志 / 成交数量 / 成交价格 / 成交金额 / 手续费 / 印花税 / 过户费；
              也支持本站模板 CSV（symbol,name,action,quantity,price,date,fee）。买卖金额不含费用的行会按 金额÷数量 补算价格。
            </div>
            <div class="flex gap mt8" style="align-items:center">
              <el-button size="small" @click="downloadTemplate">下载 CSV 模板</el-button>
              <input ref="fileInput" type="file" accept=".csv,.xlsx,.xls" class="mt8" @change="importFile" />
            </div>
          </div>

          <div class="card mt8">
            <div class="fs14 bold">JSON 导入（高级/迁移用）</div>
            <div class="fs12 mt8" style="color:#909399">
              格式：{"trades": [{"symbol":"SH600519","name":"贵州茅台","action":"buy","quantity":100,"price":1600,"date":"2026-09-01"}]}
            </div>
            <el-collapse class="mt8">
              <el-collapse-item title="展开 JSON 输入">
                <el-input v-model="jsonText" type="textarea" :rows="6" placeholder='{"trades": [{"symbol":"SH600519","name":"贵州茅台","action":"buy","quantity":100,"price":1600.0,"date":"2026-09-01"}]}' />
                <el-button type="primary" class="mt8" :loading="importing" @click="importJson">导入</el-button>
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-col>

        <el-col :xs="24" :sm="10">
          <div class="card">
            <div class="fs14 bold">盈亏汇总</div>
            <el-descriptions :column="1" border class="mt8" size="small">
              <el-descriptions-item label="持仓数量">{{ pnl.position_count ?? 0 }}</el-descriptions-item>
              <el-descriptions-item label="持仓市值">{{ fmt(pnl.total_market_value) }}</el-descriptions-item>
              <el-descriptions-item label="总成本">{{ fmt(pnl.total_cost) }}</el-descriptions-item>
              <el-descriptions-item label="浮动盈亏">
                <span class="mono" :class="(pnl.total_return||0) >= 0 ? 'up' : 'down'">{{ fmt(pnl.total_return) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="收益率">
                <span :class="(pnl.return_rate||0) >= 0 ? 'up' : 'down'">
                  {{ pnl.return_rate == null ? '-' : (pnl.return_rate * 100).toFixed(2) + '%' }}
                </span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="card mt8">
            <div class="fs14 bold">当前持仓</div>
            <el-table :data="positions" size="small" class="mt8">
              <el-table-column prop="symbol" label="代码" width="100" />
              <el-table-column prop="name" label="名称" width="100" />
              <el-table-column prop="remaining_qty" label="数量" align="right" />
              <el-table-column prop="avg_cost" label="均价" align="right" />
              <el-table-column label="盈亏" align="right">
                <template #default="{ row }">
                  <span class="mono" :class="(row.total_return||0) >= 0 ? 'up' : 'down'">{{ fmt(row.total_return) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-col>
      </el-row>

      <div class="card mt8">
        <div class="flex between" style="align-items:center">
          <span class="fs14 bold">交易记录（{{ trades.length }} 条）</span>
          <div class="flex gap">
            <el-tag v-if="trades.length" size="small" type="info">支持逐条删除，导入错误可纠正</el-tag>
          </div>
        </div>
        <el-table :data="trades.slice(0, 100)" size="small" class="mt8">
          <el-table-column prop="trade_date" label="日期" width="110" />
          <el-table-column prop="symbol" label="代码" width="110" />
          <el-table-column prop="name" label="名称" width="120" />
          <el-table-column label="方向" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.action === 'buy' ? 'danger' : 'success'">{{ row.action === 'buy' ? '买入' : '卖出' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" align="right" />
          <el-table-column prop="price" label="价格" align="right" />
          <el-table-column prop="amount" label="金额" align="right">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-popconfirm title="删除该条记录？" @confirm="deleteOne(row)">
                <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!trades.length" description="暂无交易记录" :image-size="50" />
      </div>
    </div>
  </MainLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import MainLayout from '../layout/MainLayout.vue'
import { tradeApi, stockApi } from '../api'

const jsonText = ref('')
const importing = ref(false)
const adding = ref(false)
const clearing = ref(false)
const loading = ref(false)
const positions = ref([])
const trades = ref([])
const pnl = ref({})
const fileInput = ref(null)
const form = ref({ symbol: '', name: '', action: 'buy', quantity: 100, price: 0, date: new Date().toISOString().slice(0, 10) })
const searchResults = ref([])
const searching = ref(false)

function fmt(v) {
  return v == null ? '-' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function searchStock(kw) {
  if (!kw || kw.trim().length < 2) return
  searching.value = true
  try {
    searchResults.value = await stockApi.search(kw.trim())
  } finally {
    searching.value = false
  }
}

function onSymbol() {
  const found = searchResults.value.find((s) => s.symbol === form.value.symbol)
  if (found) form.value.name = found.name
}

async function addManual() {
  if (!form.value.symbol) return ElMessage.warning('请先选择股票')
  if (!form.value.quantity || !form.value.price) return ElMessage.warning('请输入数量与价格')
  adding.value = true
  try {
    const r = await tradeApi.importJson({
      trades: [{
        symbol: form.value.symbol,
        name: form.value.name || '',
        action: form.value.action,
        quantity: form.value.quantity,
        price: form.value.price,
        date: form.value.date
      }]
    })
    ElMessage.success(`已添加 1 条记录`)
    form.value = { symbol: '', name: '', action: 'buy', quantity: 100, price: 0, date: new Date().toISOString().slice(0, 10) }
    await load()
  } finally {
    adding.value = false
  }
}

function downloadTemplate() {
  const csv = ['symbol,name,action,quantity,price,date,fee',
    'SH600519,贵州茅台,buy,100,1600.00,2026-09-01,5.00',
    'SH000001,上证指数,sell,0,0,2026-09-01,0'].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'trades_template.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

async function importJson() {
  if (!jsonText.value.trim()) return ElMessage.warning('请输入 JSON')
  importing.value = true
  try {
    let body
    try {
      body = JSON.parse(jsonText.value)
    } catch {
      return ElMessage.error('JSON 格式错误')
    }
    const r = await tradeApi.importJson(body.trades ? body : { trades: Array.isArray(body) ? body : [body] })
    ElMessage.success(`导入成功 ${r.imported} 条`)
    jsonText.value = ''
    await load()
  } finally {
    importing.value = false
  }
}

async function importFile(e) {
  const file = e.target.files[0]
  if (!file) return
  if (!/\.(csv|xlsx|xls|csv)$/i.test(file.name)) return ElMessage.warning('请选择 CSV 或 Excel 文件')
  const fd = new FormData()
  fd.append('file', file)
  try {
    const r = await tradeApi.importFile(fd)
    const msg = `导入成功 ${r.imported} 条` + (r.skipped ? `，跳过 ${r.skipped} 条（无代码/非买卖/数量价格异常）` : '')
    ElMessage.success(msg)
    if (r.skipped) ElMessage.warning(`有 ${r.skipped} 行被跳过（如分红/配号/非交易行不导入，仅保留买卖成交）`)
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
  await load()
}

async function deleteOne(row) {
  await tradeApi.deleteTrade(row.id)
  ElMessage.success('已删除')
  await load()
}

async function clearAll() {
  clearing.value = true
  try {
    const r = await tradeApi.deleteAll()
    ElMessage.success(`已清空 ${r.deleted} 条记录`)
    await load()
  } finally {
    clearing.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const [ps, p, ts] = await Promise.all([tradeApi.positions(), tradeApi.pnl(), tradeApi.trades()])
    positions.value = ps || []
    pnl.value = p || {}
    trades.value = ts || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>