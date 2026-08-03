<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AssistantToolCall } from '@/types/assistant'

const props = defineProps<{
  call: AssistantToolCall
  /** 历史消息默认收起 */
  defaultCollapsed?: boolean
}>()

const expanded = ref(!props.defaultCollapsed)

// 写操作（停用/恢复/删除）用琥珀色警示
const WRITE_TOOLS = new Set(['ban_group', 'unban_group', 'delete_document'])

const isWrite = computed(() => WRITE_TOOLS.has(props.call.name))

const toolLabel = computed(() => {
  const map: Record<string, string> = {
    list_groups: '列出全部群组',
    get_group_stats: '查看群组统计',
    list_group_members: '查看群组成员',
    list_documents: '列出文档',
    search_knowledge: '搜索知识库',
    ban_group: '停用群组',
    unban_group: '恢复群组',
    delete_document: '删除文档',
    knowledge_base_search: '知识库检索',
  }
  return map[props.call.name] ?? props.call.name
})

function formatArgs(args: string): string {
  if (!args) return ''
  try {
    const obj = JSON.parse(args)
    return JSON.stringify(obj, null, 1).slice(0, 300)
  } catch {
    return args.slice(0, 300)
  }
}

function formatResult(result: string | undefined): string {
  if (!result) return ''
  try {
    const obj = JSON.parse(result)
    const msg = obj.message ?? ''
    if (msg) return String(msg).slice(0, 500)
    return JSON.stringify(obj, null, 1).slice(0, 500)
  } catch {
    return result.slice(0, 500)
  }
}
</script>

<template>
  <div
    class="tcc"
    :class="{
      'tcc--write': isWrite,
      'tcc--failed': call.status === 'failed',
    }"
  >
    <button class="tcc__head" type="button" @click="expanded = !expanded">
      <span class="tcc__icon">
        <template v-if="call.status === 'pending'">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
          </svg>
        </template>
        <template v-else-if="call.status === 'failed'">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </template>
        <template v-else>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </template>
      </span>
      <span class="tcc__name">{{ toolLabel }}</span>
      <span v-if="call.status === 'pending'" class="tcc__pending">执行中…</span>
      <span v-else-if="call.status === 'failed'" class="tcc__badge tcc__badge--fail">失败</span>
      <span v-else-if="isWrite" class="tcc__badge tcc__badge--write">写操作</span>
      <svg class="tcc__chevron" :class="{ open: expanded }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <div v-if="expanded" class="tcc__body">
      <div v-if="call.args" class="tcc__block">
        <span class="tcc__block-label">参数</span>
        <pre class="tcc__code">{{ formatArgs(call.args) }}</pre>
      </div>
      <div v-if="call.status !== 'pending'" class="tcc__block">
        <span class="tcc__block-label" :class="{ 'tcc__block-label--fail': call.status === 'failed' }">
          {{ call.status === 'failed' ? '结果（失败）' : '结果' }}
        </span>
        <pre class="tcc__code" :class="{ 'tcc__code--fail': call.status === 'failed' }">
          {{ formatResult(call.result) || '(空)' }}
        </pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tcc {
  margin: 4px 0;
  border: 1px solid var(--border-default);
  border-radius: 9px;
  overflow: hidden;
  background: #fff;
}

.tcc--write {
  border-color: rgba(245, 158, 11, 0.35);
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.05), #fff 60%);
}

.tcc--failed {
  border-color: rgba(239, 68, 68, 0.4);
}

.tcc__head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  color: var(--text-primary);
}

.tcc__head:hover {
  background: rgba(15, 23, 42, 0.03);
}

.tcc__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  flex-shrink: 0;
}

.tcc--write .tcc__icon {
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.tcc--failed .tcc__icon {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.tcc__name {
  font-size: 0.82rem;
  font-weight: 600;
  flex: 1;
  min-width: 0;
}

.tcc__pending {
  font-size: 0.7rem;
  color: #3b82f6;
  animation: tcc-pulse 1.4s ease-in-out infinite;
}

@keyframes tcc-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.tcc__badge {
  font-size: 0.66rem;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 100px;
}

.tcc__badge--fail {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.1);
}

.tcc__badge--write {
  color: #d97706;
  background: rgba(245, 158, 11, 0.12);
}

.tcc__chevron {
  color: var(--text-muted);
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.tcc__chevron.open {
  transform: rotate(180deg);
}

.tcc__body {
  padding: 0 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tcc__block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tcc__block-label {
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.tcc__block-label--fail {
  color: #dc2626;
}

.tcc__code {
  margin: 0;
  padding: 8px 10px;
  background: #f8fafc;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.tcc__code--fail {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.04);
}
</style>
