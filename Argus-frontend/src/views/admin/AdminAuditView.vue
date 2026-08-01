<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchAuditLogs, type AuditLogItem } from '@/api/admin'
import { extractApiError } from '@/api/http'

const ACTION_LABELS: Record<string, string> = {
  DOCUMENT_DELETE: '删除文档',
  DOCUMENT_RETRY: '重试文档',
  GROUP_BAN: '停用群组',
  GROUP_UNBAN: '恢复群组',
  GROUP_DISSOLVE: '解散群组',
  GROUP_MEMBER_REMOVE: '移除成员',
  USER_CREATE: '创建用户',
  USER_STATUS_CHANGE: '用户状态变更',
  USER_PASSWORD_RESET: '重置密码',
  MODEL_CONFIG_ADD: '新增模型配置',
  MODEL_CONFIG_ACTIVATE: '激活模型配置',
  MODEL_CONFIG_DELETE: '删除模型配置',
}

const actionOptions = Object.entries(ACTION_LABELS).map(([value, label]) => ({ value, label }))

const items = ref<AuditLogItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const actionFilter = ref('')

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function detailText(item: AuditLogItem): string {
  const d = item.detail ?? {}
  const parts: string[] = []
  if (d.groupName) parts.push(`群组:${d.groupName}`)
  if (d.status) parts.push(`状态:${d.status}`)
  if (d.modelName) parts.push(`模型:${d.modelName}`)
  if (d.username) parts.push(`用户:${d.username}`)
  if (d.documentCount != null) parts.push(`文档数:${d.documentCount}`)
  return parts.join(' · ')
}

async function load() {
  loading.value = true
  try {
    const result = await fetchAuditLogs({
      action: actionFilter.value || undefined,
      userId: null,
      page: page.value,
      limit: pageSize.value,
    })
    items.value = result.items
    total.value = result.total
  } catch (err) {
    console.error('Load audit logs failed:', extractApiError(err, ''))
    items.value = []
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  page.value = 1
  load()
}

function onPageChange(p: number) {
  page.value = p
  load()
}

onMounted(load)
</script>

<template>
  <div class="audit-page">
    <div class="page-header">
      <h1>审计日志</h1>
      <p>敏感操作留痕：文档删除、群组操作、用户与模型配置变更</p>
    </div>

    <div class="filter-bar">
      <el-select
        v-model="actionFilter"
        style="width: 200px"
        clearable
        placeholder="全部操作"
        @change="applyFilter"
      >
        <el-option v-for="opt in actionOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <div class="table-card">
      <el-table :data="items" v-loading="loading" style="width: 100%">
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <span class="action-tag">{{ ACTION_LABELS[row.action] ?? row.action }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="操作者" width="120" />
        <el-table-column label="对象" width="150">
          <template #default="{ row }">
            <span v-if="row.targetId" class="target-id">#{{ row.targetId }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ detailText(row) || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
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
.audit-page {
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

.filter-bar {
  margin-bottom: 14px;
}

.table-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 14px;
}

.action-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 100px;
  font-size: 0.72rem;
  font-weight: 600;
  background: rgba(74, 144, 217, 0.1);
  color: #2563eb;
}

.target-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}
</style>
