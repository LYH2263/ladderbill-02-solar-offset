<script setup>
import { onMounted, ref, watch } from 'vue'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const accounts = ref([])
const accountId = ref(null)
const period = ref(currentMonth())
const gross = ref(null)
const peak = ref(false)
const result = ref(null)
const error = ref('')
const saving = ref(false)

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

onMounted(async () => {
  accounts.value = (await getJSON('/api/accounts')).items
  if (accounts.value.length) {
    accountId.value = accounts.value[0].id
    await seedGrossFromReading()
  }
})

async function seedGrossFromReading() {
  // Pre-fill gross usage from the account's latest reading when available.
  const detail = await getJSON(`/api/accounts/${accountId.value}`)
  const r = detail.readings[0]
  if (r) {
    gross.value = r.kwh
    peak.value = !!r.peak
  }
}

watch(accountId, seedGrossFromReading)

// Selecting the account + billing period automatically brings out its active offset.
let timer = null
watch([accountId, period, gross, peak], () => {
  clearTimeout(timer)
  timer = setTimeout(preview, 300)
}, { immediate: false })

async function preview() {
  error.value = ''
  const g = gross.value
  if (!accountId.value || !period.value || g === null || g === '' || !Number.isFinite(+g) || +g < 0) {
    result.value = null
    return
  }
  try {
    result.value = await postJSON('/api/solar-offset/preview', {
      account_id: +accountId.value,
      period: period.value,
      gross_kwh: +gross.value,
      peak: peak.value,
    })
  } catch (e) {
    error.value = e.message
  }
}

async function persist() {
  error.value = ''
  saving.value = true
  try {
    result.value = await postJSON('/api/bill', {
      account_id: +accountId.value,
      kwh: +gross.value,
      peak: peak.value,
      persist: true,
      period: period.value,
    })
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page work">
    <h1>测算工作台</h1>
    <div class="panel form-row">
      <label>户号
        <select v-model="accountId">
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}（{{ a.meter_no }}）</option>
        </select>
      </label>
      <label>账期 <input type="month" v-model="period" /></label>
      <label>毛电量(kWh) <input type="number" v-model.number="gross" min="0" step="1" /></label>
      <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
      <button :disabled="!result || saving" @click="persist">计算并入库</button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="result" class="panel">
      <p class="offset-chip" v-if="result.has_active_offset">
        已带出 {{ period }} 有效抵扣 <strong>v{{ result.offset_version }}</strong>
        · 抵扣 {{ result.offset_kwh }} kWh
      </p>
      <p class="offset-chip muted" v-else>{{ period }} 暂无抵扣记录，按 0 抵扣测算（不落库）</p>

      <div class="gn-grid">
        <div class="tile">
          <span class="tile-label">毛电量</span>
          <strong>{{ result.gross_kwh }}</strong><small>kWh</small>
        </div>
        <div class="tile minus">
          <span class="tile-label">光伏抵扣</span>
          <strong>−{{ result.offset_kwh }}</strong><small>kWh</small>
        </div>
        <div class="tile net">
          <span class="tile-label">净电量</span>
          <strong>{{ result.net_kwh }}</strong><small>kWh</small>
        </div>
      </div>

      <p class="total-line">
        计费顺序：先抵扣（净电量下限 0）→ 阶梯分段 → 尖峰系数
        <strong>×{{ result.peak_factor }}</strong>
        ；合计
        <strong class="hero-num" style="font-size:1.6rem">¥{{ result.total }}</strong>
        <span v-if="result.run_id" class="muted">记录#{{ result.run_id }}</span>
      </p>

      <SegmentTable :rows="result.segments" />
    </div>
  </div>
</template>

<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
.form-row label { display: flex; flex-direction: column; font-size: 0.85rem; gap: 0.25rem; }
input[type=number] { width: 7rem; }
select { background: #0d1612; border: 1px solid var(--muted); color: var(--text); padding: 0.35rem 0.5rem; border-radius: 6px; }
.err { color: #ff8080; }
.offset-chip { font-size: 0.9rem; }
.gn-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin: 0.75rem 0; }
.tile { background: var(--bg); border-radius: 10px; padding: 0.8rem 1rem; display: flex; align-items: baseline; gap: 0.4rem; }
.tile strong { font-size: 1.9rem; color: var(--text); }
.tile small { color: var(--muted); }
.tile-label { display: block; font-size: 0.78rem; color: var(--muted); margin-right: 0.5rem; }
.tile.minus strong { color: #f0b35a; }
.tile.net strong { color: var(--accent); }
.total-line { font-size: 0.92rem; }
</style>
