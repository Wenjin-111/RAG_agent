<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchAdminDocuments,
  fetchAdminDocumentStats,
  fetchAdminGroups,
  adminRetryDocument,
  adminDeleteDocument,
  type AdminDocumentItem,
  type AdminDocumentStats,
  type AdminGroupItem,
} from '@/api/admin'
import { extractApiError } from '@/api/http'

// ── Filters ──
const statusFilter = ref('ALL')
const groupFilter = ref<number | null>(null)
const searchText = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

// ── Data ──
const documents = ref<AdminDocumentItem[]>([])
const stats = ref<AdminDocumentStats | null>(null)
const groups = ref<AdminGroupItem[]>([])
const loading = ref(false)
const loadingStats = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const statusOptions = [
  { label: '全部状态', value: 'ALL' },
  { label: '已就绪', value: 'READY' },
  { label: '处理中', value: 'PROCESSING' },
  { label: '待处理', value: 'UPLOADED' },
  { label: '失败', value: 'FAILED' },
]

const statusMeta: Record<string, { label: string; cls: string }> = {
  READY: { label: '已就绪', cls: 'doc-status--ready' },
  PROCESSING: { label: '处理中', cls: 'doc-status--processing' },
  UPLOADED: { label: '待处理', cls: 'doc-status--pending' },
  FAILED: { label: '失败', cls: 'doc-status--failed' },
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadStats() {
  loadingStats.value = true
  try {
    stats.value = await fetchAdminDocumentStats()
  } catch (err) {
    console.error('Load stats failed:', extractApiError(err, ''))
  } finally {
    loadingStats.value = false
  }
}

async function loadDocuments() {
  loading.value = true
  try {
    const result = await fetchAdminDocuments({
      status: statusFilter.value === 'ALL' ? undefined : statusFilter.value,
      groupId: groupFilter.value,
      fileName: searchText.value.trim() || undefined,
      page: page.value,
      limit: pageSize.value,
    })
    documents.value = result.items
    total.value = result.total
  } catch (err) {
    console.error('Load documents failed:', extractApiError(err, ''))
    documents.value = []
  } finally {
    loading.value = false
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadDocuments()
  }, 300)
}

function applyFilter() {
  page.value = 1
  loadDocuments()
}

function onPageChange(p: number) {
  page.value = p
  loadDocuments()
}

async function handleRetry(doc: AdminDocumentItem) {
  try {
    await adminRetryDocument(doc.documentId)
    ElMessage.success(`已重新提交「${doc.fileName}」`)
    await Promise.all([loadDocuments(), loadStats()])
  } catch (err) {
    ElMessage.error(extractApiError(err, '重试失败'))
  }
}

async function handleDelete(doc: AdminDocumentItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除文档「${doc.fileName}」（群组：${doc.groupName}）吗？删除后将清理向量和搜索索引，此操作不可撤销。`,
      '删除文档',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminDeleteDocument(doc.documentId)
    ElMessage.success('文档已删除')
    await Promise.all([loadDocuments(), loadStats()])
  } catch (err) {
    ElMessage.error(extractApiError(err, '删除失败'))
  }
}

onMounted(async () => {
  await Promise.all([loadStats(), loadDocuments()])
  try {
    groups.value = await fetchAdminGroups()
  } catch (err) {
    console.error('Load groups failed:', extractApiError(err, ''))
  }
})
</script>

<template>
  <div class="admin-docs">
    <div class="page-header">
      <h1>文档管理</h1>
      <p>全平台文档总览、处理状态与批量运维</p>
    </div>

    <!-- Stats cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-card__label">文档总量</div>
        <div class="stat-card__value">{{ stats?.total ?? '-' }}</div>
      </div>
      <div class="stat-card stat-card--ready">
        <div class="stat-card__label">已就绪</div>
        <div class="stat-card__value">{{ stats?.ready ?? '-' }}</div>
      </div>
      <div class="stat-card stat-card--pending">
        <div class="stat-card__label">待处理/处理中</div>
        <div class="stat-card__value">{{ (stats?.pending ?? 0) + (stats?.processing ?? 0) }}</div>
      </div>
      <div class="stat-card stat-card--failed">
        <div class="stat-card__label">失败</div>
        <div class="stat-card__value">{{ stats?.failed ?? '-' }}</div>
      </div>
      <div class="stat-card stat-card--storage">
        <div class="stat-card__label">存储占用</div>
        <div class="stat-card__value">{{ formatSize(stats?.storageBytes ?? 0) }}</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <el-select v-model="statusFilter" placeholder="全部状态" style="width: 140px" @change="applyFilter">
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-select
        v-model="groupFilter"
        style="width: 200px"
        clearable
        placeholder="全部群组"
        @change="applyFilter"
      >
        <el-option v-for="g in groups" :key="g.groupId" :label="g.groupName" :value="g.groupId" />
      </el-select>
      <el-input
        v-model="searchText"
        placeholder="搜索文件名"
        clearable
        style="width: 220px"
        @input="onSearchInput"
        @clear="applyFilter"
      />
    </div>

    <!-- Table -->
    <div class="table-card">
      <el-table :data="documents" v-loading="loading" style="width: 100%">
        <el-table-column prop="fileName" label="文件名" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="doc-name">
              <span class="doc-name__text">{{ row.fileName }}</span>
              <span v-if="row.status === 'FAILED' && row.failureReason" class="doc-name__reason" :title="row.failureReason">
                {{ row.failureReason.slice(0, 60) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="groupName" label="群组" width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="doc-status" :class="statusMeta[row.status]?.cls ?? ''">
              {{ statusMeta[row.status]?.label ?? row.status }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上传者" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.uploaderDisplayName }}</template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.fileSize) }}</template>
        </el-table-column>
        <el-table-column label="上传时间" width="150">
          <template #default="{ row }">{{ formatTime(row.uploadedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'FAILED'"
              link
              type="primary"
              @click="handleRetry(row)"
            >重试</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
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
  </div>
</template>

<style scoped>
.admin-docs {
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
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 18px;
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

.stat-card--ready .stat-card__value { color: #10b981; }
.stat-card--pending .stat-card__value { color: #f59e0b; }
.stat-card--failed .stat-card__value { color: #ef4444; }
.stat-card--storage .stat-card__value { color: #6366f1; }

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

.doc-name__text {
  font-weight: 500;
}

.doc-name__reason {
  display: block;
  margin-top: 2px;
  font-size: 0.7rem;
  color: #dc2626;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-status {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 100px;
  font-size: 0.72rem;
  font-weight: 600;
}

.doc-status--ready { background: rgba(16, 185, 129, 0.12); color: #059669; }
.doc-status--processing { background: rgba(59, 130, 246, 0.12); color: #2563eb; }
.doc-status--pending { background: rgba(245, 158, 11, 0.12); color: #d97706; }
.doc-status--failed { background: rgba(239, 68, 68, 0.12); color: #dc2626; }

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

@media (max-width: 1100px) {
  .stats-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
