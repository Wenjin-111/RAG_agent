import http, { type ApiResponse } from './http'

// ─────────────────────────────────────────────
// 管理控制台 — 全局文档管理
// ─────────────────────────────────────────────

export interface AdminDocumentItem {
  documentId: number
  fileName: string
  fileExt: string
  fileSize: number
  status: string
  groupId: number
  groupName: string
  uploaderUserId: number
  uploaderDisplayName: string
  uploaderUserCode: string
  failureReason: string | null
  uploadedAt: string | null
  processedAt: string | null
}

export interface AdminDocumentsPage {
  items: AdminDocumentItem[]
  total: number
  page: number
  limit: number
}

export interface AdminDocumentStats {
  total: number
  ready: number
  processing: number
  pending: number
  failed: number
  storageBytes: number
}

/**
 * 全局文档分页列表（管理员）
 *
 * GET /api/admin/documents?status=&groupId=&fileName=&page=&limit=
 */
export async function fetchAdminDocuments(params: {
  status?: string
  groupId?: number | null
  fileName?: string
  page: number
  limit: number
}): Promise<AdminDocumentsPage> {
  const { data } = await http.get<ApiResponse<AdminDocumentsPage>>('/admin/documents', { params })
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载文档失败')
  return data.data
}

/**
 * 全局文档统计（管理员）
 *
 * GET /api/admin/documents/stats
 */
export async function fetchAdminDocumentStats(): Promise<AdminDocumentStats> {
  const { data } = await http.get<ApiResponse<AdminDocumentStats>>('/admin/documents/stats')
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载统计失败')
  return data.data
}

/**
 * 管理员重试失败文档
 *
 * POST /api/admin/documents/{documentId}/retry
 */
export async function adminRetryDocument(documentId: number): Promise<void> {
  const { data } = await http.post<ApiResponse<null>>(`/admin/documents/${documentId}/retry`)
  if (!data.success) throw new Error(data.message ?? '重试失败')
}

/**
 * 管理员删除文档
 *
 * DELETE /api/admin/documents/{documentId}
 */
export async function adminDeleteDocument(documentId: number): Promise<void> {
  const { data } = await http.delete<ApiResponse<null>>(`/admin/documents/${documentId}`)
  if (!data.success) throw new Error(data.message ?? '删除失败')
}

// ─────────────────────────────────────────────
// 管理控制台 — 全量群组
// ─────────────────────────────────────────────

export interface AdminGroupItem {
  groupId: number
  groupCode: string
  groupName: string
  description: string
  ownerUserId: number
  status: string
  memberCount: number
  createdAt: string | null
}

/**
 * 全量群组列表（管理员）
 *
 * GET /api/admin/groups
 */
export async function fetchAdminGroups(): Promise<AdminGroupItem[]> {
  const { data } = await http.get<ApiResponse<AdminGroupItem[]>>('/admin/groups')
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载群组失败')
  return data.data
}

export interface AdminGroupMember {
  id: number
  userId: number
  username: string
  displayName: string
  email: string
  role: string
  joinedAt: string | null
}

export interface AdminGroupDetail {
  groupId: number
  groupCode: string
  groupName: string
  description: string
  ownerUserId: number
  status: string
  documentCount: number
  storageBytes: number
  memberCount: number
  members: AdminGroupMember[]
  createdAt: string | null
}

/**
 * 群组详情（管理员）：基本信息 + 成员 + 文档统计
 *
 * GET /api/admin/groups/{groupId}
 */
export async function fetchAdminGroupDetail(groupId: number): Promise<AdminGroupDetail> {
  const { data } = await http.get<ApiResponse<AdminGroupDetail>>(`/admin/groups/${groupId}`)
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载群组详情失败')
  return data.data
}

/**
 * 停用群组（管理员）
 *
 * POST /api/admin/groups/{groupId}/ban
 */
export async function adminBanGroup(groupId: number): Promise<void> {
  const { data } = await http.post<ApiResponse<null>>(`/admin/groups/${groupId}/ban`)
  if (!data.success) throw new Error(data.message ?? '停用失败')
}

/**
 * 恢复群组（管理员）
 *
 * POST /api/admin/groups/{groupId}/unban
 */
export async function adminUnbanGroup(groupId: number): Promise<void> {
  const { data } = await http.post<ApiResponse<null>>(`/admin/groups/${groupId}/unban`)
  if (!data.success) throw new Error(data.message ?? '恢复失败')
}

/**
 * 移除群组成员（管理员）
 *
 * DELETE /api/admin/groups/{groupId}/members/{userId}
 */
export async function adminRemoveGroupMember(groupId: number, userId: number): Promise<void> {
  const { data } = await http.delete<ApiResponse<null>>(`/admin/groups/${groupId}/members/${userId}`)
  if (!data.success) throw new Error(data.message ?? '移除成员失败')
}

/**
 * 解散群组（管理员）：软删群组与全部文档，清理索引
 *
 * DELETE /api/admin/groups/{groupId}
 */
export async function adminDissolveGroup(groupId: number): Promise<void> {
  const { data } = await http.delete<ApiResponse<null>>(`/admin/groups/${groupId}`)
  if (!data.success) throw new Error(data.message ?? '解散失败')
}

// ─────────────────────────────────────────────
// 管理控制台 — QA 问答历史
// ─────────────────────────────────────────────

export interface QaHistoryItem {
  sessionId: number
  userId: number
  userName: string
  userCode: string
  groupId: number
  groupName: string
  title: string
  question: string
  answerPreview: string
  messageCount: number
  createdAt: string | null
}

export interface QaHistoryPage {
  items: QaHistoryItem[]
  total: number
  page: number
  limit: number
}

export interface QaHistoryMessage {
  messageId: number
  role: 'USER' | 'ASSISTANT'
  content: string
  thinking: string | null
  citations: Array<{ fileName: string; chunkIndex: number | null; score: number; snippet: string | null }>
  reasonCode: string | null
  reasonMessage: string | null
  createdAt: string | null
}

export interface QaHistoryDetail {
  sessionId: number
  userId: number
  userName: string
  userCode: string
  groupId: number
  groupName: string
  title: string
  messages: QaHistoryMessage[]
  createdAt: string | null
}

/**
 * QA 问答历史分页（管理员）
 *
 * GET /api/admin/qa/sessions?userId=&groupId=&page=&limit=
 */
export async function fetchQaHistory(params: {
  userId?: number | null
  groupId?: number | null
  page: number
  limit: number
}): Promise<QaHistoryPage> {
  const { data } = await http.get<ApiResponse<QaHistoryPage>>('/admin/qa/sessions', { params })
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载问答历史失败')
  return data.data
}

/**
 * 问答历史详情（管理员）
 *
 * GET /api/admin/qa/sessions/{sessionId}
 */
export async function fetchQaHistoryDetail(sessionId: number): Promise<QaHistoryDetail> {
  const { data } = await http.get<ApiResponse<QaHistoryDetail>>(`/admin/qa/sessions/${sessionId}`)
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载问答详情失败')
  return data.data
}

// ─────────────────────────────────────────────
// 管理控制台 — 数据洞察 / 系统健康 / 审计日志
// ─────────────────────────────────────────────

export interface TrendPoint {
  date: string
  count?: number
  users?: number
}

export interface FormatStat {
  ext: string
  count: number
}

export interface EvidenceStat {
  level: string
  count: number
}

export interface PlatformInsights {
  uploadTrend: TrendPoint[]
  formats: FormatStat[]
  activeTrend: TrendPoint[]
  evidenceDistribution: EvidenceStat[]
  totalQa: number
  refusedQa: number
}

export interface HealthComponent {
  ok: boolean
  message: string
}

export interface SystemHealth {
  postgresql: HealthComponent
  elasticsearch: HealthComponent
  minio: HealthComponent
  embedding: HealthComponent
  ingestion: {
    pendingJobs: number
    runningJobs: number
    workerRunning: boolean
    recentFailures: Array<{ jobId: number; documentId: number; error: string; createdAt: string | null }>
  }
}

export interface AuditLogItem {
  id: number
  userId: number
  username: string
  action: string
  targetType: string | null
  targetId: string | null
  detail: Record<string, unknown>
  createdAt: string | null
}

export interface AuditLogPage {
  items: AuditLogItem[]
  total: number
  page: number
  limit: number
}

/**
 * 平台数据洞察（管理员）
 *
 * GET /api/admin/metrics/insights
 */
export async function fetchPlatformInsights(): Promise<PlatformInsights> {
  const { data } = await http.get<ApiResponse<PlatformInsights>>('/admin/metrics/insights')
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载数据洞察失败')
  return data.data
}

/**
 * 系统健康检查（管理员）
 *
 * GET /api/admin/health
 */
export async function fetchSystemHealth(): Promise<SystemHealth> {
  const { data } = await http.get<ApiResponse<SystemHealth>>('/admin/health')
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载健康状态失败')
  return data.data
}

/**
 * 审计日志（管理员）
 *
 * GET /api/admin/audit-logs?action=&userId=&page=&limit=
 */
export async function fetchAuditLogs(params: {
  action?: string
  userId?: number | null
  page: number
  limit: number
}): Promise<AuditLogPage> {
  const { data } = await http.get<ApiResponse<AuditLogPage>>('/admin/audit-logs', { params })
  if (!data.success || data.data == null) throw new Error(data.message ?? '加载审计日志失败')
  return data.data
}

/**
 * 管理员创建用户（初始密码 Admin@123456，首次登录需修改）
 *
 * POST /api/admin/users
 */
export async function createAdminUser(payload: {
  username: string
  email: string
  displayName: string
}): Promise<{ userId: number; username: string; email: string; displayName: string }> {
  const { data } = await http.post<ApiResponse<{ userId: number; username: string; email: string; displayName: string }>>(
    '/admin/users',
    payload,
  )
  if (!data.success || data.data == null) throw new Error(data.message ?? '创建用户失败')
  return data.data
}
