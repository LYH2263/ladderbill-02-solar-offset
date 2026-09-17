<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getJSON, postJSON } from '../api'

const props = defineProps({ accountId: { type: [Number, String], required: true } })

const items = ref([])
const error = ref('')
const saving = ref(false)
const form = ref({ period: currentMonth(), offset_kwh: null, source_note: '', entered_by: '' })

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function fmt(iso) {
  return iso ? iso.slice(0, 16).replace('T', ' ') : ''
}

async function load() {
  if (!props.accountId) return
  items.value = (await getJSON(`/api/accounts/${props.accountId}/solar-offsets`)).items
}
onMounted(load)
watch(() => props.accountId, load)

const activeForPeriod = computed(
  () => items.value.find((r) => r.period === form.value.period && r.is_active === 1) || null,
)

const periods = computed(() => {
  const map = new Map()
  for (const r of items.value) {
    if (!map.has(r.period)) map.set(r.period, [])
    map.get(r.period).push(r)
  }
  return [...map.entries()]
    .map(([period, rows]) => ({ period, rows }))
    .sort((a, b) => b.period.localeCompare(a.period))
})

const valid = computed(
  () => !!form.value.period && Number.isFinite(+form.value.offset_kwh) && +form.value.offset_kwh >= 0,
)

async function submit() {
  error.value = ''
  saving.value = true
  const base = activeForPeriod.value
  const payload = {
    offset_kwh: +form.value.offset_kwh,
    source_note: form.value.source_note || null,
    entered_by: form.value.entered_by || null,
  }
  try {
    if (base) {
      await postJSON(
        `/api/accounts/${props.accountId}/solar-offsets/${form.value.period}/correct`,
        { base_version: base.version, ...payload },
      )
    } else {
      await postJSON(`/api/accounts/${props.accountId}/solar-offsets`, {
        period: form.value.period,
        ...payload,
      })
    }
    form.value.offset_kwh = null
    form.value.source_note = ''
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function voidActive() {
  const base = activeForPeriod.value
  if (!base) return
  if (!window.confirm(`作废 ${form.value.period} 的有效抵扣 v${base.version}？旧版仍保留只读。`)) return
  error.value = ''
  try {
    await postJSON(
      `/api/accounts/${props.accountId}/solar-offsets/${form.value.period}/void`,
      { base_version: base.version },
    )
    await load()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <div class="panel solar">
    <h3>光伏抵扣录入</h3>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="form-row">
      <label>账期
        <input type="month" v-model="form.period" />
      </label>
      <label>录入电量(kWh)
        <input type="number" v-model.number="form.offset_kwh" min="0" step="1" />
      </label>
      <label>来源备注
        <input type="text" v-model="form.source_note" placeholder="如：屋顶光伏逆变器" />
      </label>
      <label>录入者
        <input type="text" v-model="form.entered_by" placeholder="姓名" />
      </label>
      <button :disabled="!valid || saving" @click="submit">
        {{ activeForPeriod ? `更正为 v${activeForPeriod.version + 1}` : '录入抵扣' }}
      </button>
      <button v-if="activeForPeriod" class="ghost" @click="voidActive">作废当前</button>
    </div>

    <p v-if="activeForPeriod" class="hint">
      该账期已有有效记录 <strong>v{{ activeForPeriod.version }}</strong>
      （{{ activeForPeriod.offset_kwh }} kWh，{{ activeForPeriod.entered_by || '未署名' }}）。
      再次提交将基于显式版本号 v{{ activeForPeriod.version }} 生成新版本，旧版保留只读。
    </p>
    <p v-else class="muted">该账期暂无有效抵扣，提交即新建 v1。</p>

    <h4>账期列表</h4>
    <div v-for="g in periods" :key="g.period" class="period-block">
      <div class="period-head">
        <a href="#" @click.prevent="form.period = g.period">{{ g.period }}</a>
        <span
          class="badge"
          :class="{ on: g.rows.some((r) => r.is_active === 1) }"
        >{{ g.rows.some((r) => r.is_active === 1) ? '有效' : '已作废' }}</span>
      </div>
      <table>
        <thead>
          <tr><th>版本</th><th>状态</th><th>抵扣电量</th><th>来源备注</th><th>录入者</th><th>录入时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in g.rows" :key="r.id" :class="{ dead: r.is_active !== 1 }">
            <td>v{{ r.version }}</td>
            <td>{{ r.is_active === 1 ? '有效' : '只读旧版' }}</td>
            <td>{{ r.offset_kwh }}</td>
            <td class="muted">{{ r.source_note }}</td>
            <td>{{ r.entered_by }}</td>
            <td class="muted">{{ fmt(r.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!periods.length" class="muted">尚无抵扣记录。</p>
  </div>
</template>

<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 0.9rem; align-items: end; }
.form-row label { display: flex; flex-direction: column; font-size: 0.85rem; gap: 0.25rem; }
input[type=number] { width: 8rem; }
input[type=text] { width: 11rem; }
.ghost { background: transparent; color: var(--muted); border: 1px solid var(--muted); }
.hint { font-size: 0.88rem; color: var(--accent); }
.err { color: #ff8080; }
h4 { margin: 1.1rem 0 0.5rem; }
.period-block { margin-bottom: 0.8rem; }
.period-head { display: flex; gap: 0.6rem; align-items: center; margin-bottom: 0.2rem; }
.badge { font-size: 0.72rem; padding: 0.05rem 0.45rem; border-radius: 999px; background: var(--bg); color: var(--muted); }
.badge.on { background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
tr.dead td { color: var(--muted); }
</style>
