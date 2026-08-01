<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchAdminGroups,
  fetchAdminGroupDetail,
  adminBanGroup,
  adminUnbanGroup,
  adminRemoveGroupMember,
  adminDissolveGroup,
  type AdminGroupItem,
  type AdminGroupDetail,
} from '@/api/admin'
import { extractApiError } from '@/api/http'

const groups = ref<AdminGroupItem[]>([])
const loading = ref(false)

const detailVisible = ref(false)
const detail = ref<AdminGroupDetail | null>(null)
const detailLoading = ref(false)

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

const statusMeta: Record<string, { label: string; cls: string }> = {
  ACTIVE: { label: '正常', cls: 'g-status--active' },
  DISABLED: { label: '已停用', cls: 'g-status--disabled' },
}

async function loadGroups() {
  loading.value = true
  try {
    groups.value = await fetchAdminGroups()
  } catch (err) {
    console.error('Load groups failed:', extractApiError(err, ''))
  } finally {
    loading.value = false
  }
}

async function openDetail(group: AdminGroupItem) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await fetchAdminGroupDetail(group.groupId)
  } catch (err) {
    ElMessage.error(extractApiError(err, '加载群组详情失败'))
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function handleToggleBan(group: AdminGroupItem) {
  const isDisabled = group.status === 'DISABLED'
  try {
    await ElMessageBox.confirm(
      isDisabled
        ? `确定恢复群组「${group.groupName}」吗？`
        : `确定停用群组「${group.groupName}」吗？停用后成员将无法访问该群组的文档与问答。`,
      isDisabled ? '恢复群组' : '停用群组',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    if (isDisabled) {
      await adminUnbanGroup(group.groupId)
    } else {
      await adminBanGroup(group.groupId)
    }
    ElMessage.success(isDisabled ? '群组已恢复' : '群组已停用')
    await loadGroups()
    if (detail.value?.groupId === group.groupId) {
      detail.value = await fetchAdminGroupDetail(group.groupId)
    }
  } catch (err) {
    ElMessage.error(extractApiError(err, '操作失败'))
  }
}

async function handleRemoveMember(userId: number) {
  if (!detail.value) return
  const member = detail.value.members.find((m) => m.userId === userId)
  try {
    await ElMessageBox.confirm(
      `确定将成员「${member?.displayName ?? userId}」移出群组「${detail.value.groupName}」吗？`,
      '移除成员',
      { confirmButtonText: '确认移除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminRemoveGroupMember(detail.value.groupId, userId)
    ElMessage.success('成员已移除')
    detail.value = await fetchAdminGroupDetail(detail.value.groupId)
  } catch (err) {
    ElMessage.error(extractApiError(err, '移除失败'))
  }
}

async function handleDissolve(group: AdminGroupItem) {
  try {
    await ElMessageBox.confirm(
      `确定解散群组「${group.groupName}」吗？\n群组及其全部文档将被删除（含向量与搜索索引），此操作不可撤销。`,
      '解散群组',
      { confirmButtonText: '确认解散', cancelButtonText: '取消', type: 'error' },
    )
  } catch {
    return
  }
  try {
    await adminDissolveGroup(group.groupId)
    ElMessage.success('群组已解散')
    detailVisible.value = false
    await loadGroups()
  } catch (err) {
    ElMessage.error(extractApiError(err, '解散失败'))
  }
}

onMounted(loadGroups)
</script>

<template>
  <div class="admin-groups">
    <div class="page-header">
      <h1>群组管理</h1>
      <p>全平台群组总览、成员与文档管理、停用与解散</p>
    </div>

    <div class="table-card">
      <el-table :data="groups" v-loading="loading" style="width: 100%">
        <el-table-column prop="groupName" label="群组名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="group-name">
              <span class="group-name__title">{{ row.groupName }}</span>
              <code class="group-name__code">{{ row.groupCode }}</code>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="g-status" :class="statusMeta[row.status]?.cls ?? ''">
              {{ statusMeta[row.status]?.label ?? row.status }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="memberCount" label="成员数" width="90" />
        <el-table-column prop="ownerUserId" label="所有者 ID" width="100" />
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              link
              :type="row.status === 'DISABLED' ? 'success' : 'warning'"
              @click="handleToggleBan(row)"
            >{{ row.status === 'DISABLED' ? '恢复' : '停用' }}</el-button>
            <el-button link type="danger" @click="handleDissolve(row)">解散</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Detail dialog -->
    <el-dialog v-model="detailVisible" width="720px" top="6vh" :title="detail?.groupName ?? '群组详情'">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <div class="detail-stats">
            <div class="detail-stat">
              <div class="detail-stat__label">成员数</div>
              <div class="detail-stat__value">{{ detail.memberCount }}</div>
            </div>
            <div class="detail-stat">
              <div class="detail-stat__label">文档数</div>
              <div class="detail-stat__value">{{ detail.documentCount }}</div>
            </div>
            <div class="detail-stat">
              <div class="detail-stat__label">存储占用</div>
              <div class="detail-stat__value">{{ formatSize(detail.storageBytes) }}</div>
            </div>
            <div class="detail-stat">
              <div class="detail-stat__label">状态</div>
              <div class="detail-stat__value">
                <span class="g-status" :class="statusMeta[detail.status]?.cls ?? ''">
                  {{ statusMeta[detail.status]?.label ?? detail.status }}
                </span>
              </div>
            </div>
          </div>

          <div class="member-section">
            <div class="member-section__head">
              <span>成员列表</span>
              <span class="member-section__hint">所有者不可移除</span>
            </div>
            <el-table :data="detail.members" size="small" style="width: 100%">
              <el-table-column prop="displayName" label="姓名" min-width="120" />
              <el-table-column prop="username" label="用户名" min-width="120" />
              <el-table-column prop="email" label="邮箱" min-width="160" show-overflow-tooltip />
              <el-table-column label="角色" width="90">
                <template #default="{ row }">
                  <span class="role-tag" :class="row.role === 'OWNER' ? 'role-tag--owner' : ''">
                    {{ row.role === 'OWNER' ? '所有者' : '成员' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="加入时间" width="140">
                <template #default="{ row }">{{ formatTime(row.joinedAt) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="90">
                <template #default="{ row }">
                  <el-button
                    v-if="row.role !== 'OWNER'"
                    link
                    type="danger"
                    size="small"
                    @click="handleRemoveMember(row.userId)"
                  >移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-groups {
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

.table-card {
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 14px;
}

.group-name__title {
  font-weight: 500;
}

.group-name__code {
  margin-left: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
  background: var(--surface-muted);
  padding: 1px 6px;
  border-radius: 4px;
}

.g-status {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 100px;
  font-size: 0.72rem;
  font-weight: 600;
}

.g-status--active { background: rgba(16, 185, 129, 0.12); color: #059669; }
.g-status--disabled { background: rgba(239, 68, 68, 0.12); color: #dc2626; }

.detail-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 18px;
}

.detail-stat {
  background: var(--surface-subtle);
  border-radius: 10px;
  padding: 12px 14px;
}

.detail-stat__label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.detail-stat__value {
  font-family: 'Poppins', 'JetBrains Mono', monospace;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary);
}

.member-section__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 10px;
}

.member-section__hint {
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--text-muted);
}

.role-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 100px;
  font-size: 0.7rem;
  background: rgba(100, 116, 139, 0.12);
  color: #64748b;
}

.role-tag--owner {
  background: rgba(245, 158, 11, 0.14);
  color: #d97706;
}
</style>
