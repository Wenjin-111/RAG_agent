<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchSystemHealth, type SystemHealth } from '@/api/admin'
import { extractApiError } from '@/api/http'

const health = ref<SystemHealth | null>(null)
const loading = ref(false)
const lastChecked = ref('')

function formatTime(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

async function check() {
  loading.value = true
  try {
    health.value = await fetchSystemHealth()
    lastChecked.value = formatTime(new Date())
  } catch (err) {
    console.error('Health check failed:', extractApiError(err, ''))
  } finally {
    loading.value = false
  }
}

onMounted(check)
</script>

<template>
  <div class="health-page">
    <div class="page-header">
      <h1>系统健康</h1>
      <p>基础设施连通性与任务队列状态</p>
    </div>

    <div class="toolbar">
      <el-button type="primary" :loading="loading" @click="check">重新检测</el-button>
      <span v-if="lastChecked" class="toolbar__hint">上次检测：{{ lastChecked }}</span>
    </div>

    <div v-loading="loading">
      <template v-if="health">
        <!-- Infrastructure status -->
        <div class="status-grid">
          <div
            v-for="(item, key) in {
              postgresql: { label: 'PostgreSQL', comp: health.postgresql },
              elasticsearch: { label: 'Elasticsearch', comp: health.elasticsearch },
              minio: { label: 'MinIO', comp: health.minio },
              embedding: { label: 'Embedding API', comp: health.embedding },
            }"
            :key="key"
            class="status-card"
            :class="item.comp.ok ? 'status-card--ok' : 'status-card--bad'"
          >
            <div class="status-card__head">
              <span class="status-dot" :class="item.comp.ok ? 'status-dot--ok' : 'status-dot--bad'" />
              <span class="status-card__name">{{ item.label }}</span>
              <span class="status-card__state">{{ item.comp.ok ? '正常' : '异常' }}</span>
            </div>
            <p class="status-card__msg">{{ item.comp.message }}</p>
          </div>
        </div>

        <!-- Ingestion queue -->
        <div class="section-card">
          <h3 class="section-card__title">文档处理队列</h3>
          <div class="queue-stats">
            <div class="queue-stat">
              <span class="queue-stat__value">{{ health.ingestion.pendingJobs }}</span>
              <span class="queue-stat__label">待处理</span>
            </div>
            <div class="queue-stat">
              <span class="queue-stat__value">{{ health.ingestion.runningJobs }}</span>
              <span class="queue-stat__label">处理中</span>
            </div>
            <div class="queue-stat">
              <span
                class="queue-stat__value"
                :class="health.ingestion.workerRunning ? 'queue-stat__value--ok' : 'queue-stat__value--bad'"
              >{{ health.ingestion.workerRunning ? '运行中' : '已停止' }}</span>
              <span class="queue-stat__label">Worker</span>
            </div>
          </div>

          <h4 class="sub-title">最近失败任务</h4>
          <el-table
            v-if="health.ingestion.recentFailures.length > 0"
            :data="health.ingestion.recentFailures"
            size="small"
            style="width: 100%"
          >
            <el-table-column prop="jobId" label="任务 ID" width="90" />
            <el-table-column prop="documentId" label="文档 ID" width="90" />
            <el-table-column prop="error" label="错误信息" min-width="300" show-overflow-tooltip />
            <el-table-column prop="createdAt" label="时间" width="160" />
          </el-table>
          <p v-else class="empty-tip">暂无失败任务</p>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.health-page {
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

.toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}

.toolbar__hint {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-bottom: 18px;
}

.status-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 14px 16px;
}

.status-card--bad {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.02);
}

.status-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot--ok {
  background: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.5);
}

.status-dot--bad {
  background: #ef4444;
  box-shadow: 0 0 6px rgba(239, 68, 68, 0.5);
}

.status-card__name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.status-card__state {
  margin-left: auto;
  font-size: 0.72rem;
  font-weight: 600;
}

.status-card--ok .status-card__state { color: #059669; }
.status-card--bad .status-card__state { color: #dc2626; }

.status-card__msg {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-muted);
  word-break: break-all;
}

.section-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px 18px;
}

.section-card__title {
  margin: 0 0 14px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.queue-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}

.queue-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.queue-stat__value {
  font-family: 'Poppins', 'JetBrains Mono', monospace;
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text-primary);
}

.queue-stat__value--ok { color: #10b981; font-size: 1rem; }
.queue-stat__value--bad { color: #ef4444; font-size: 1rem; }

.queue-stat__label {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.sub-title {
  margin: 0 0 10px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-tip {
  padding: 14px 0;
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}
</style>
