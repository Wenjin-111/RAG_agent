<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchQaHistory,
  fetchQaHistoryDetail,
  fetchAdminGroups,
  type QaHistoryItem,
  type QaHistoryDetail,
  type AdminGroupItem,
} from '@/api/admin'
import { fetchAdminUsers } from '@/api/admin-user'
import { extractApiError } from '@/api/http'
import HoverTextPreview from '@/components/HoverTextPreview.vue'

// ── Filters ──
const groupFilter = ref<number | null>(null)
const userFilter = ref<number | null>(null)
const groups = ref<AdminGroupItem[]>([])
const users = ref<Array<{ id: number; displayName: string }>>([])

// ── Data ──
const items = ref<QaHistoryItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

// ── Stats ──
const statTotal = ref(0)
const statRefused = ref(0)
const refusedRate = ref(0)

// ── Detail ──
const detailVisible = ref(false)
const detail = ref<QaHistoryDetail | null>(null)
const detailLoading = ref(false)

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadList() {
  loading.value = true
  try {
    const result = await fetchQaHistory({
      userId: userFilter.value,
      groupId: groupFilter.value,
      page: page.value,
      limit: pageSize.value,
    })
    items.value = result.items
    total.value = result.total
  } catch (err) {
    console.error('Load QA history failed:', extractApiError(err, ''))
    items.value = []
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  page.value = 1
  loadList()
}

function onPageChange(p: number) {
  page.value = p
  loadList()
}

async function openDetail(item: QaHistoryItem) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await fetchQaHistoryDetail(item.sessionId)
  } catch (err) {
    ElMessage.error(extractApiError(err, '加载详情失败'))
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  await loadList()
  try {
    const [g, u] = await Promise.all([fetchAdminGroups(), fetchAdminUsers()])
    groups.value = g
    users.value = (u ?? []).map((x) => ({ id: x.userId, displayName: x.displayName }))
    // 拒答率统计：从本页数据粗算（完整统计在阶段 3 做）
    statTotal.value = total.value
    statRefused.value = items.value.filter((i) => !i.answerPreview).length
    refusedRate.value = statTotal.value > 0 ? Math.round((statRefused.value / statTotal.value) * 100) : 0
  } catch (err) {
    console.error('Load filters failed:', extractApiError(err, ''))
  }
})
</script>

<template>
  <div class="admin-qa">
    <div class="page-header">
      <h1>问答历史</h1>
      <p>全平台问答记录浏览、审计与拒答分析</p>
    </div>

    <!-- Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-card__label">问答总次数</div>
        <div class="stat-card__value">{{ statTotal }}</div>
      </div>
      <div class="stat-card stat-card--refused">
        <div class="stat-card__label">本页拒答</div>
        <div class="stat-card__value">{{ statRefused }}</div>
      </div>
      <div class="stat-card stat-card--rate">
        <div class="stat-card__label">本页拒答率</div>
        <div class="stat-card__value">{{ refusedRate }}%</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <el-select
        v-model="groupFilter"
        style="width: 200px"
        clearable
        placeholder="全部群组"
        @change="applyFilter"
      >
        <el-option v-for="g in groups" :key="g.groupId" :label="g.groupName" :value="g.groupId" />
      </el-select>
      <el-select
        v-model="userFilter"
        style="width: 200px"
        clearable
        filterable
        placeholder="全部用户"
        @change="applyFilter"
      >
        <el-option v-for="u in users" :key="u.id" :label="u.displayName" :value="u.id" />
      </el-select>
    </div>

    <!-- Table -->
    <div class="table-card">
      <el-table :data="items" v-loading="loading" style="width: 100%">
        <el-table-column prop="question" label="问题" min-width="220">
          <template #default="{ row }">
            <HoverTextPreview :text="row.question" class="q-question" />
          </template>
        </el-table-column>
        <el-table-column label="回答" min-width="220">
          <template #default="{ row }">
            <HoverTextPreview v-if="row.answerPreview" :text="row.answerPreview" class="q-answer" />
            <span v-else class="q-refused">未回答（拒答）</span>
          </template>
        </el-table-column>
        <el-table-column prop="userName" label="用户" width="110" show-overflow-tooltip />
        <el-table-column prop="groupName" label="群组" width="150" show-overflow-tooltip />
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="onPageChange"
        />
      </div>
    </div>

    <!-- Detail dialog -->
    <el-dialog v-model="detailVisible" width="780px" top="5vh" :title="detail?.title ?? '问答详情'">
      <div v-loading="detailLoading" class="qa-detail">
        <template v-if="detail">
          <div class="qa-detail__meta">
            <span>{{ detail.userName }}</span> · <span>{{ detail.groupName }}</span> ·
            <span>{{ formatTime(detail.createdAt) }}</span>
          </div>

          <div
            v-for="m in detail.messages"
            :key="m.messageId"
            class="qa-msg"
            :class="m.role === 'USER' ? 'qa-msg--user' : 'qa-msg--assistant'"
          >
            <div class="qa-msg__role">{{ m.role === 'USER' ? '用户' : 'Argus' }}</div>
            <div class="qa-msg__content">
              <p v-if="m.content" class="qa-msg__text">{{ m.content }}</p>
              <div v-if="m.role === 'ASSISTANT' && !m.content" class="qa-msg__refused">
                <span class="qa-msg__refused-code">{{ m.reasonCode }}</span>
                {{ m.reasonMessage }}
              </div>
              <details v-if="m.thinking" class="qa-msg__thinking">
                <summary>思考过程</summary>
                <pre>{{ m.thinking }}</pre>
              </details>
              <div v-if="m.citations && m.citations.length > 0" class="qa-msg__citations">
                <div class="qa-msg__citations-title">引用来源（{{ m.citations.length }}）</div>
                <div v-for="(c, i) in m.citations" :key="i" class="qa-citation">
                  <span class="qa-citation__file">{{ c.fileName }}</span>
                  <span v-if="c.chunkIndex != null" class="qa-citation__idx">片段 #{{ c.chunkIndex }}</span>
                  <span class="qa-citation__score">{{ Math.round((c.score ?? 0) * 100) }}%</span>
                  <p v-if="c.snippet" class="qa-citation__snippet">{{ c.snippet }}</p>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-qa {
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 18px;
  max-width: 640px;
}

.stat-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px 18px;
}

.stat-card__label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.stat-card__value {
  font-family: 'Poppins', 'JetBrains Mono', monospace;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-card--refused .stat-card__value { color: #f59e0b; }
.stat-card--rate .stat-card__value { color: #ef4444; }

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}

.table-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 14px;
}

.q-question {
  font-weight: 500;
}

.q-answer {
  color: var(--text-secondary);
  font-size: 0.88rem;
}

.q-refused {
  color: #dc2626;
  font-size: 0.82rem;
  font-weight: 500;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.qa-detail__meta {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-bottom: 14px;
}

.qa-msg {
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
}

.qa-msg--user {
  background: var(--surface-subtle);
}

.qa-msg__role {
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.qa-msg__text {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.qa-msg__refused {
  font-size: 0.85rem;
  color: #dc2626;
}

.qa-msg__refused-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  margin-right: 8px;
}

.qa-msg__thinking {
  margin-top: 8px;
}

.qa-msg__thinking summary {
  cursor: pointer;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.qa-msg__thinking pre {
  margin: 6px 0 0;
  padding: 10px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  font-size: 0.75rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.qa-msg__citations {
  margin-top: 10px;
  border-top: 1px dashed var(--border-default);
  padding-top: 8px;
}

.qa-msg__citations-title {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.qa-citation {
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(74, 144, 217, 0.04);
  margin-bottom: 6px;
}

.qa-citation__file {
  font-size: 0.8rem;
  font-weight: 600;
}

.qa-citation__idx {
  margin-left: 8px;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.qa-citation__score {
  margin-left: 8px;
  font-size: 0.7rem;
  color: var(--brand-primary);
}

.qa-citation__snippet {
  margin: 4px 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
