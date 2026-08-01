<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  fetchPlatformInsights,
  type PlatformInsights,
  type TrendPoint,
} from '@/api/admin'
import { extractApiError } from '@/api/http'

const insights = ref<PlatformInsights | null>(null)
const loading = ref(false)
const errorMsg = ref('')

const EVIDENCE_META: Record<string, { label: string; color: string }> = {
  SUFFICIENT: { label: '证据充分', color: '#10b981' },
  PARTIAL: { label: '部分证据', color: '#3b82f6' },
  WEAK: { label: '证据较弱', color: '#f59e0b' },
  NONE: { label: '无证据', color: '#ef4444' },
  UNKNOWN: { label: '未知', color: '#94a3b8' },
}

const W = 860
const H = 180

function trendPoints(trend: TrendPoint[], key: 'count' | 'users'): string {
  if (trend.length === 0) return ''
  const max = Math.max(...trend.map((t) => t[key] ?? 0), 1)
  const step = W / Math.max(trend.length - 1, 1)
  return trend
    .map((t, i) => `${(i * step).toFixed(1)},${(H - ((t[key] ?? 0) / max) * H).toFixed(1)}`)
    .join(' ')
}

function areaPath(points: string): string {
  if (!points) return ''
  const first = points.split(' ')[0]
  const last = points.split(' ').at(-1)
  return `M0,${H} L${points} L${last?.split(',')[0]},${H} Z`
}

const uploadPoints = computed(() => trendPoints(insights.value?.uploadTrend ?? [], 'count'))
const activePoints = computed(() => trendPoints(insights.value?.activeTrend ?? [], 'users'))

function trendLabels(trend: TrendPoint[]): { x: number; label: string }[] {
  if (trend.length === 0) return []
  const step = W / Math.max(trend.length - 1, 1)
  const labels: { x: number; label: string }[] = []
  const stride = Math.max(1, Math.floor(trend.length / 8))
  for (let i = 0; i < trend.length; i += stride) {
    const d = trend[i]!.date.slice(5)
    labels.push({ x: i * step, label: d })
  }
  return labels
}

const uploadLabels = computed(() => trendLabels(insights.value?.uploadTrend ?? []))
const activeLabels = computed(() => trendLabels(insights.value?.activeTrend ?? []))

const totalFormats = computed(() => (insights.value?.formats ?? []).reduce((s, f) => s + f.count, 0))
const evidenceTotal = computed(() =>
  (insights.value?.evidenceDistribution ?? []).reduce((s, e) => s + e.count, 0),
)
const refusedRate = computed(() => {
  const total = insights.value?.totalQa ?? 0
  return total > 0 ? Math.round(((insights.value?.refusedQa ?? 0) / total) * 100) : 0
})

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    insights.value = await fetchPlatformInsights()
  } catch (err) {
    errorMsg.value = extractApiError(err, '加载数据洞察失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="insights-page">
    <div class="page-header">
      <h1>数据洞察</h1>
      <p>平台运行全景：文档、活跃度与检索质量</p>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <div v-loading="loading">
      <template v-if="insights">
        <!-- KPI -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-card__label">累计问答</div>
            <div class="kpi-card__value">{{ insights.totalQa }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-card__label">拒答次数</div>
            <div class="kpi-card__value">{{ insights.refusedQa }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-card__label">拒答率</div>
            <div class="kpi-card__value">{{ refusedRate }}%</div>
          </div>
        </div>

        <!-- Charts -->
        <div class="chart-grid">
          <div class="chart-card">
            <h3 class="chart-card__title">文档上传趋势（30 天）</h3>
            <svg viewBox="0 0 860 180" preserveAspectRatio="none" class="chart-svg">
              <path :d="areaPath(uploadPoints)" fill="rgba(59,130,246,0.12)" />
              <polyline
                :points="uploadPoints"
                fill="none" stroke="#3b82f6" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round"
              />
            </svg>
            <div class="chart-labels">
              <span
                v-for="(l, i) in uploadLabels"
                :key="i"
                :style="{ left: (l.x / 860) * 100 + '%' }"
              >{{ l.label }}</span>
            </div>
          </div>

          <div class="chart-card">
            <h3 class="chart-card__title">活跃用户趋势（30 天）</h3>
            <svg viewBox="0 0 860 180" preserveAspectRatio="none" class="chart-svg">
              <path :d="areaPath(activePoints)" fill="rgba(16,185,129,0.12)" />
              <polyline
                :points="activePoints"
                fill="none" stroke="#10b981" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round"
              />
            </svg>
            <div class="chart-labels">
              <span
                v-for="(l, i) in activeLabels"
                :key="i"
                :style="{ left: (l.x / 860) * 100 + '%' }"
              >{{ l.label }}</span>
            </div>
          </div>
        </div>

        <!-- Distributions -->
        <div class="chart-grid">
          <div class="chart-card">
            <h3 class="chart-card__title">文档格式分布</h3>
            <div v-if="totalFormats > 0" class="bar-list">
              <div v-for="f in insights.formats" :key="f.ext" class="bar-row">
                <span class="bar-row__label">{{ f.ext }}</span>
                <div class="bar-row__track">
                  <div
                    class="bar-row__fill"
                    :style="{ width: ((f.count / totalFormats) * 100).toFixed(1) + '%' }"
                  />
                </div>
                <span class="bar-row__count">{{ f.count }}</span>
              </div>
            </div>
            <p v-else class="chart-empty">暂无文档</p>
          </div>

          <div class="chart-card">
            <h3 class="chart-card__title">检索证据质量分布</h3>
            <div v-if="evidenceTotal > 0" class="bar-list">
              <div
                v-for="e in insights.evidenceDistribution"
                :key="e.level"
                class="bar-row"
              >
                <span class="bar-row__label">{{ EVIDENCE_META[e.level]?.label ?? e.level }}</span>
                <div class="bar-row__track">
                  <div
                    class="bar-row__fill"
                    :style="{
                      width: ((e.count / evidenceTotal) * 100).toFixed(1) + '%',
                      background: EVIDENCE_META[e.level]?.color ?? '#94a3b8',
                    }"
                  />
                </div>
                <span class="bar-row__count">{{ e.count }}</span>
              </div>
            </div>
            <p v-else class="chart-empty">暂无问答数据（问答后自动统计）</p>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.insights-page {
  padding: 4px 0 24px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  font-family: 'Poppins', 'Noto Sans SC', sans-serif;
  font-size: 1.45rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.page-header p {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.error-banner {
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
  font-size: 0.85rem;
  margin-bottom: 14px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 18px;
  max-width: 720px;
}

.kpi-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px 18px;
}

.kpi-card__label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.kpi-card__value {
  font-family: 'Poppins', 'JetBrains Mono', monospace;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}

.chart-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px 18px;
}

.chart-card__title {
  margin: 0 0 12px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-svg {
  width: 100%;
  height: 180px;
  display: block;
}

.chart-labels {
  position: relative;
  height: 18px;
  margin-top: 4px;
}

.chart-labels span {
  position: absolute;
  transform: translateX(-50%);
  font-size: 0.66rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.chart-labels span:first-child { transform: translateX(0); }
.chart-labels span:last-child { transform: translateX(-100%); }

.bar-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 6px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bar-row__label {
  width: 74px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-align: right;
}

.bar-row__track {
  flex: 1;
  height: 10px;
  border-radius: 6px;
  background: var(--surface-muted);
  overflow: hidden;
}

.bar-row__fill {
  height: 100%;
  border-radius: 6px;
  background: #3b82f6;
  transition: width 0.4s ease;
}

.bar-row__count {
  width: 40px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.chart-empty {
  padding: 24px 0;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-muted);
}

@media (max-width: 1100px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
