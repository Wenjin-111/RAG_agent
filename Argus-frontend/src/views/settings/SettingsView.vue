<script setup lang="ts">
import { reactive, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { extractApiError } from '@/api/http'
import http, { type ApiResponse } from '@/api/http'

const router = useRouter()
const authStore = useAuthStore()

const mustChange = computed(() => authStore.currentUser?.mustChangePassword ?? false)
const isAdmin = computed(() => authStore.isAdmin)

// ── Password section ──
const passwordExpanded = ref(mustChange.value)

// ── Model config section ──
const modelExpanded = ref(false)

interface ModelConfigItem {
  id: number
  model_type: string
  display_name: string
  base_url: string
  api_key: string
  model_name: string
  is_active: boolean
  created_at: string | null
}

const chatModels = ref<ModelConfigItem[]>([])
const embModels = ref<ModelConfigItem[]>([])
const mineruModels = ref<ModelConfigItem[]>([])
const modelsLoading = ref(false)

// ── Add model form ──
type ModelType = 'chat' | 'embedding' | 'mineru'
const showAddForm = ref<ModelType | null>(null)
const addForm = reactive({ displayName: '', baseUrl: '', apiKey: '', modelName: '' })
const addLoading = ref(false)
const addError = ref('')
const testResult = ref<{ ok: boolean; message: string } | null>(null)

async function loadModels() {
  modelsLoading.value = true
  try {
    const [chat, emb, mineru] = await Promise.all([
      http.get<ApiResponse<ModelConfigItem[]>>('/admin/model-configs', { params: { modelType: 'chat' } }),
      http.get<ApiResponse<ModelConfigItem[]>>('/admin/model-configs', { params: { modelType: 'embedding' } }),
      http.get<ApiResponse<ModelConfigItem[]>>('/admin/model-configs', { params: { modelType: 'mineru' } }),
    ])
    chatModels.value = chat.data.data ?? []
    embModels.value = emb.data.data ?? []
    mineruModels.value = mineru.data.data ?? []
  } catch { /* ignore */ }
  finally { modelsLoading.value = false }
}

function openAddForm(type: ModelType) {
  showAddForm.value = type
  addForm.displayName = type === 'mineru' ? 'MinerU 文档解析' : ''
  addForm.baseUrl = type === 'mineru' ? 'https://mineru.net' : ''
  addForm.apiKey = ''
  addForm.modelName = type === 'mineru' ? 'vlm' : ''
  addError.value = ''
  testResult.value = null
}

function cancelAdd() {
  showAddForm.value = null
  testResult.value = null
}

async function testConnection() {
  testResult.value = null
  try {
    const { data } = await http.post<ApiResponse<{ ok: boolean; message: string; status: number }>>('/admin/model-configs/test', {
      baseUrl: addForm.baseUrl,
      apiKey: addForm.apiKey,
      modelName: addForm.modelName,
      modelType: showAddForm.value,
    })
    testResult.value = {
      ok: data.data?.ok ?? false,
      message: data.data?.message ?? '未知结果',
    }
  } catch (err) {
    testResult.value = { ok: false, message: extractApiError(err, '测试失败') }
  }
}

async function saveModel() {
  if (!addForm.displayName.trim() || !addForm.apiKey.trim() || !addForm.modelName.trim()) {
    addError.value = '请填写所有字段'
    return
  }
  if (showAddForm.value !== 'mineru' && !addForm.baseUrl.trim()) {
    addError.value = '请填写 API URL'
    return
  }
  addLoading.value = true
  addError.value = ''
  try {
    await http.post('/admin/model-configs', {
      modelType: showAddForm.value,
      displayName: addForm.displayName,
      baseUrl: addForm.baseUrl,
      apiKey: addForm.apiKey,
      modelName: addForm.modelName,
    })
    showAddForm.value = null
    await loadModels()
  } catch (err) {
    addError.value = extractApiError(err, '保存失败')
  } finally {
    addLoading.value = false
  }
}

async function activateModel(modelId: number) {
  try {
    await http.patch(`/admin/model-configs/${modelId}/activate`)
    await loadModels()
  } catch (err) {
    console.error('Activate failed:', extractApiError(err, ''))
  }
}

async function deleteModel(modelId: number) {
  try {
    await http.delete(`/admin/model-configs/${modelId}`)
    await loadModels()
  } catch (err) {
    console.error('Delete failed:', extractApiError(err, ''))
  }
}

// ── Password form ──
const pwForm = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const pwLoading = ref(false)
const pwError = ref('')
const pwSuccess = ref('')

async function handleChangePassword() {
  pwError.value = ''; pwSuccess.value = ''
  if (!pwForm.currentPassword.trim() || !pwForm.newPassword.trim() || !pwForm.confirmPassword.trim()) { pwError.value = '请填写所有密码字段'; return }
  if (pwForm.newPassword.length < 6) { pwError.value = '新密码长度至少 6 个字符'; return }
  if (pwForm.newPassword !== pwForm.confirmPassword) { pwError.value = '两次输入的新密码不一致'; return }
  if (pwForm.currentPassword === pwForm.newPassword) { pwError.value = '新密码不能与当前密码相同'; return }
  pwLoading.value = true
  try {
    await authStore.changePassword({ currentPassword: pwForm.currentPassword, newPassword: pwForm.newPassword })
    pwForm.currentPassword = ''; pwForm.newPassword = ''; pwForm.confirmPassword = ''
    pwSuccess.value = '密码修改成功'
    if (mustChange.value) setTimeout(() => router.push(authStore.homePath), 1200)
  } catch (err) { pwError.value = extractApiError(err, '修改密码失败') }
  finally { pwLoading.value = false }
}

onMounted(() => { if (isAdmin.value) loadModels() })
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <h1>系统设置</h1>
      <p>管理您的账号安全与偏好</p>
    </div>

    <!-- 强制修改密码提示 -->
    <div v-if="mustChange" class="must-change-banner">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/><path d="M12 8V12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="12" cy="16" r="0.5" fill="currentColor" stroke="none"/></svg>
      <span>出于安全考虑，您需要先修改密码后才能继续使用系统</span>
    </div>

    <!-- ── 账号安全与密码管理 ── -->
    <div class="settings-section">
      <button class="section-trigger" :class="{ expanded: passwordExpanded }" @click="passwordExpanded = !passwordExpanded">
        <span class="section-trigger__icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg></span>
        <span class="section-trigger__text"><span class="section-trigger__title">账号安全与密码管理</span><span class="section-trigger__desc">修改登录密码，保护账号安全</span></span>
        <svg class="section-trigger__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      <div v-if="passwordExpanded" class="section-body">
        <form class="pw-form" @submit.prevent="handleChangePassword">
          <div class="input-group"><label>当前密码</label><input v-model="pwForm.currentPassword" type="password" placeholder="输入当前密码" autocomplete="current-password" /></div>
          <div class="input-group"><label>新密码</label><input v-model="pwForm.newPassword" type="password" placeholder="输入新密码（至少 6 位）" autocomplete="new-password" /></div>
          <div class="input-group"><label>确认新密码</label><input v-model="pwForm.confirmPassword" type="password" placeholder="再次输入新密码" autocomplete="new-password" /></div>
          <p v-if="pwError" class="form-error">{{ pwError }}</p>
          <p v-if="pwSuccess" class="form-success">{{ pwSuccess }}</p>
          <button type="submit" class="btn-submit" :disabled="pwLoading">{{ pwLoading ? '保存中...' : '保存修改' }}</button>
        </form>
      </div>
    </div>

    <!-- ── 添加模型（仅管理员） ── -->
    <div v-if="isAdmin" class="settings-section" style="margin-top: 16px;">
      <button class="section-trigger" :class="{ expanded: modelExpanded }" @click="modelExpanded = !modelExpanded; if (modelExpanded && chatModels.length === 0) loadModels()">
        <span class="section-trigger__icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 2a10 10 0 0 1 7 17H5a10 10 0 0 1 7-17z"/><circle cx="12" cy="12" r="3"/></svg></span>
        <span class="section-trigger__text"><span class="section-trigger__title">添加模型</span><span class="section-trigger__desc">管理聊天大模型、嵌入大模型和 MinerU 文档解析的配置</span></span>
        <svg class="section-trigger__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      <div v-if="modelExpanded" class="section-body">
        <!-- Chat models -->
        <div class="model-block">
          <div class="model-block__head">
            <h3 class="model-block__title">聊天大模型</h3>
            <button class="btn-add" @click="openAddForm('chat')">+ 添加</button>
          </div>
          <div v-if="modelsLoading" class="model-list-empty">加载中...</div>
          <div v-else-if="chatModels.length === 0" class="model-list-empty">暂无配置</div>
          <div v-else class="model-list">
            <div v-for="m in chatModels" :key="m.id" class="model-card" :class="{ active: m.isActive }" @click="activateModel(m.id)">
              <div class="model-card__main">
                <span class="model-card__name">{{ m.displayName }}</span>
                <span class="model-card__model">{{ m.modelName }}</span>
                <span v-if="m.isActive" class="model-card__badge">使用中</span>
              </div>
              <button class="model-card__del" title="删除" @click.stop="deleteModel(m.id)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg></button>
            </div>
          </div>
        </div>

        <!-- Embedding models -->
        <div class="model-block">
          <div class="model-block__head">
            <h3 class="model-block__title">嵌入大模型</h3>
            <button class="btn-add" @click="openAddForm('embedding')">+ 添加</button>
          </div>
          <div v-if="modelsLoading" class="model-list-empty">加载中...</div>
          <div v-else-if="embModels.length === 0" class="model-list-empty">暂无配置</div>
          <div v-else class="model-list">
            <div v-for="m in embModels" :key="m.id" class="model-card" :class="{ active: m.isActive }" @click="activateModel(m.id)">
              <div class="model-card__main">
                <span class="model-card__name">{{ m.displayName }}</span>
                <span class="model-card__model">{{ m.modelName }}</span>
                <span v-if="m.isActive" class="model-card__badge">使用中</span>
              </div>
              <button class="model-card__del" title="删除" @click.stop="deleteModel(m.id)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg></button>
            </div>
          </div>
        </div>

        <!-- MinerU parser config -->
        <div class="model-block">
          <div class="model-block__head">
            <h3 class="model-block__title">MinerU 文档解析</h3>
            <button class="btn-add" @click="openAddForm('mineru')">+ 添加</button>
          </div>
          <p class="model-block__hint">配置后上传的 PDF / Word / PPT / Excel / 图片统一由 MinerU 云端解析</p>
          <div v-if="modelsLoading" class="model-list-empty">加载中...</div>
          <div v-else-if="mineruModels.length === 0" class="model-list-empty">未配置，文档解析将不可用（或使用 .env 的 MINERU_TOKEN）</div>
          <div v-else class="model-list">
            <div v-for="m in mineruModels" :key="m.id" class="model-card" :class="{ active: m.isActive }" @click="activateModel(m.id)">
              <div class="model-card__main">
                <span class="model-card__name">{{ m.displayName }}</span>
                <span class="model-card__model">{{ m.modelName }}</span>
                <span v-if="m.isActive" class="model-card__badge">使用中</span>
              </div>
              <button class="model-card__del" title="删除" @click.stop="deleteModel(m.id)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg></button>
            </div>
          </div>
        </div>

        <!-- Add form modal -->
        <div v-if="showAddForm" class="add-overlay" @click.self="cancelAdd">
          <div class="add-modal">
            <h4>{{ showAddForm === 'chat' ? '添加聊天大模型' : showAddForm === 'embedding' ? '添加嵌入大模型' : '添加 MinerU 文档解析' }}</h4>
            <div class="input-group"><label>显示名称</label><input v-model="addForm.displayName" placeholder="例如：MinerU 文档解析" /></div>
            <div v-if="showAddForm !== 'mineru'" class="input-group"><label>API URL</label><input v-model="addForm.baseUrl" placeholder="https://api.deepseek.com/v1" /></div>
            <div class="input-group"><label>{{ showAddForm === 'mineru' ? 'Token' : 'API Key' }}</label><input v-model="addForm.apiKey" type="password" :placeholder="showAddForm === 'mineru' ? 'sk-...（mineru.net 免费创建）' : 'sk-...'" /></div>
            <div class="input-group"><label>Model Name</label><input v-model="addForm.modelName" :placeholder="showAddForm === 'mineru' ? 'vlm / pipeline' : 'deepseek-chat'" /></div>
            <p v-if="showAddForm === 'mineru'" class="model-block__hint">模型说明：vlm（精度高，复杂版式/扫描件/公式）、pipeline（零幻觉，内容逐字准确）</p>
            <p v-if="addError" class="form-error">{{ addError }}</p>
            <div v-if="testResult" class="test-msg" :class="{ ok: testResult.ok, fail: !testResult.ok }">{{ testResult.message }}</div>
            <div class="add-modal__btns">
              <button class="btn-test" :disabled="addLoading" @click="testConnection">测试连接</button>
              <button class="btn-save" :disabled="addLoading" @click="saveModel">{{ addLoading ? '保存中...' : '保存' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-header h1 { font-size: 24px; font-weight: 800; color: var(--text-primary); margin-bottom: 4px; }
.page-header p { font-size: 14px; color: var(--text-secondary); margin: 0; }

.must-change-banner { display: flex; align-items: center; gap: 10px; padding: 14px 18px; background: linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.03)); border: 1px solid rgba(245,158,11,0.2); border-radius: var(--radius-sm); color: #b45309; font-size: 14px; font-weight: 500; margin-bottom: 24px; }
.must-change-banner svg { flex-shrink: 0; color: #f59e0b; }

.settings-section { max-width: 620px; }
.section-trigger { display: flex; align-items: center; gap: 14px; width: 100%; padding: 18px 20px; background: var(--surface-white); border: 1px solid var(--border-default); border-radius: var(--radius-md); cursor: pointer; font-family: inherit; text-align: left; transition: all .2s ease; box-shadow: 0 1px 3px rgba(0,0,0,.03); }
.section-trigger:hover { border-color: var(--brand-primary); box-shadow: 0 4px 12px rgba(74,144,217,.08); }
.section-trigger.expanded { border-radius: var(--radius-md) var(--radius-md) 0 0; border-bottom-color: transparent; }
.section-trigger__icon { display: flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 10px; background: rgba(74,144,217,.08); color: var(--brand-primary); flex-shrink: 0; }
.section-trigger__text { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.section-trigger__title { font-size: .95rem; font-weight: 700; color: var(--text-primary); }
.section-trigger__desc { font-size: .78rem; color: var(--text-muted); }
.section-trigger__chevron { color: var(--text-muted); flex-shrink: 0; transition: transform .25s ease; }
.section-trigger.expanded .section-trigger__chevron { transform: rotate(180deg); }
.section-body { background: var(--surface-white); border: 1px solid var(--border-default); border-top: none; border-radius: 0 0 var(--radius-md) var(--radius-md); padding: 0 20px 24px; animation: section-in .25s ease; }
@keyframes section-in { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }

.pw-form { display: flex; flex-direction: column; gap: 16px; }
.input-group { display: flex; flex-direction: column; gap: 5px; }
.input-group label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.input-group input { padding: 10px 13px; border: 1.5px solid var(--border-default); border-radius: var(--radius-sm); font-size: 14px; font-family: inherit; color: var(--text-primary); background: var(--surface-white); transition: border-color .2s ease, box-shadow .2s ease; outline: none; }
.input-group input::placeholder { color: #94a3b8; }
.input-group input:focus { border-color: var(--brand-primary); box-shadow: 0 0 0 3px rgba(74,144,217,.1); }
.form-error { font-size: 13px; color: var(--el-color-danger); margin: 0; }
.form-success { font-size: 13px; color: var(--el-color-success); margin: 0; }
.btn-submit { padding: 11px 24px; border-radius: var(--radius-sm); background: linear-gradient(135deg, var(--brand-primary), var(--brand-primary-dark)); color: #fff; font-size: 14px; font-weight: 600; border: none; cursor: pointer; transition: all .2s ease; box-shadow: 0 4px 14px rgba(74,144,217,.25); margin-top: 4px; }
.btn-submit:hover:not(:disabled) { box-shadow: 0 6px 20px rgba(74,144,217,.35); transform: translateY(-1px); }
.btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }

/* Model blocks */
.model-block { margin-top: 20px; }
.model-block__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.model-block__title { font-size: .88rem; font-weight: 700; color: var(--text-primary); margin: 0; }
.btn-add { padding: 6px 14px; font-size: .78rem; font-weight: 600; color: var(--brand-primary); background: rgba(74,144,217,.06); border: 1px solid rgba(74,144,217,.15); border-radius: var(--radius-sm); cursor: pointer; font-family: inherit; transition: all .15s ease; }
.btn-add:hover { background: rgba(74,144,217,.12); }
.model-list-empty { text-align: center; padding: 24px; font-size: .82rem; color: var(--text-muted); }
.model-block__hint { margin: 0 0 10px; font-size: .75rem; color: var(--text-muted); line-height: 1.5; }
.model-list { display: flex; flex-direction: column; gap: 8px; }
.model-card { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); cursor: pointer; transition: all .15s ease; }
.model-card:hover { border-color: var(--brand-primary); background: rgba(74,144,217,.03); }
.model-card.active { border-color: var(--brand-primary); background: rgba(74,144,217,.06); }
.model-card__main { display: flex; align-items: center; gap: 10px; min-width: 0; }
.model-card__name { font-size: .85rem; font-weight: 600; color: var(--text-primary); }
.model-card__model { font-size: .75rem; color: var(--text-muted); font-family: monospace; }
.model-card__badge { font-size: .68rem; font-weight: 700; color: #fff; background: linear-gradient(135deg, var(--brand-primary), var(--brand-accent)); padding: 2px 10px; border-radius: 100px; }
.model-card__del { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; border-radius: 6px; opacity: 0; transition: all .15s ease; }
.model-card:hover .model-card__del { opacity: 1; }
.model-card__del:hover { background: rgba(239,68,68,.1); color: #dc2626; }

/* Add form overlay */
.add-overlay { position: fixed; inset: 0; background: rgba(15,23,42,.45); backdrop-filter: blur(4px); z-index: 300; display: flex; align-items: center; justify-content: center; }
.add-modal { width: min(480px, 90vw); background: #fff; border-radius: 14px; padding: 24px; box-shadow: 0 20px 60px rgba(0,0,0,.15); display: flex; flex-direction: column; gap: 14px; }
.add-modal h4 { margin: 0; font-size: 1rem; font-weight: 700; color: var(--text-primary); }
.add-modal__btns { display: flex; justify-content: space-between; margin-top: 4px; }
.btn-test { padding: 10px 20px; font-size: .85rem; font-weight: 600; color: var(--text-secondary); background: var(--surface-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-sm); cursor: pointer; font-family: inherit; transition: all .15s ease; }
.btn-test:hover { border-color: var(--brand-primary); color: var(--brand-primary); }
.btn-save { padding: 10px 28px; font-size: .85rem; font-weight: 600; color: #fff; background: linear-gradient(135deg, var(--brand-primary), var(--brand-primary-dark)); border: none; border-radius: var(--radius-sm); cursor: pointer; font-family: inherit; box-shadow: 0 4px 14px rgba(74,144,217,.25); transition: all .2s ease; }
.btn-save:hover:not(:disabled) { box-shadow: 0 6px 20px rgba(74,144,217,.35); transform: translateY(-1px); }
.btn-save:disabled { opacity: .6; cursor: not-allowed; }
.test-msg { font-size: .8rem; padding: 8px 12px; border-radius: 6px; }
.test-msg.ok { background: rgba(16,185,129,.08); color: #059669; }
.test-msg.fail { background: rgba(239,68,68,.08); color: #dc2626; }
</style>
