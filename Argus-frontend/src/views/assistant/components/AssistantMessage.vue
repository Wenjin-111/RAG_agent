<script setup lang="ts">
import { computed } from 'vue'
import { markdownToHtml } from '@/utils/markdown'
import type {
  AssistantCitationItem,
  AssistantConfirmation,
  AssistantMessageRole,
  AssistantToolCall,
  AssistantToolMode,
} from '@/types/assistant'
import AssistantCitationBar from './AssistantCitationBar.vue'
import ToolCallCard from './ToolCallCard.vue'

export interface UiAssistantMessage {
  localId: string
  messageId: number | null
  role: AssistantMessageRole
  content: string
  toolMode: AssistantToolMode | null
  groupId: number | null
  createdAt: string
  streaming?: boolean
  failed?: boolean
  failureMessage?: string | null
  citations?: AssistantCitationItem[]
  /** 本轮流式中产生的工具调用（实时卡片） */
  toolCalls?: AssistantToolCall[]
  /** 等待用户确认的写操作（human-in-the-loop） */
  confirmation?: AssistantConfirmation | null
}

const props = defineProps<{
  message: UiAssistantMessage
}>()

const emit = defineEmits<{
  'inspect-citation': [citation: AssistantCitationItem]
  retry: []
  'confirm-action': [value: string]
  'cancel-action': [value: string]
}>()

const rendered = computed(() => {
  if (props.message.role === 'USER' || props.message.role === 'TOOL') return ''
  return markdownToHtml(props.message.content || '')
})

/** 历史 TOOL 消息：content 存 JSON（tool_name/args/result/status） */
const historicalToolCall = computed<AssistantToolCall | null>(() => {
  if (props.message.role !== 'TOOL') return null
  try {
    const parsed = JSON.parse(props.message.content || '{}') as {
      tool_name?: string
      args?: string
      result?: string
      status?: string
    }
    if (!parsed.tool_name) return null
    return {
      id: `hist-${props.message.localId}`,
      name: parsed.tool_name,
      args: parsed.args ?? '',
      result: parsed.result ?? '',
      status: parsed.status === 'failed' ? 'failed' : 'success',
    }
  } catch {
    return null
  }
})

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return map[c] ?? c
  })
}

function formatTime(iso: string): string {
  if (!iso) {
    const d = new Date()
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  const d = new Date(iso)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}
</script>

<template>
  <article class="amsg" :class="`amsg--${message.role.toLowerCase()}`">
    <!-- Avatar -->
    <div class="amsg__avatar">
      <template v-if="message.role === 'USER'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </template>
      <template v-else-if="message.role === 'ASSISTANT'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      </template>
      <template v-else>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
      </template>
    </div>

    <!-- Body -->
    <div class="amsg__body">
      <header class="amsg__head">
        <span class="amsg__role">
          {{ message.role === 'USER' ? 'You' : message.role === 'ASSISTANT' ? 'Argus' : 'Tool' }}
        </span>
        <span v-if="message.toolMode" class="amsg__mode-tag" :class="`amsg__mode-tag--${message.toolMode.toLowerCase()}`">
          {{ message.toolMode === 'CHAT' ? 'chat' : message.toolMode === 'ADMIN' ? 'admin' : 'kb_search' }}
        </span>
        <span class="amsg__time">{{ formatTime(message.createdAt) }}</span>
      </header>

      <!-- USER -->
      <div v-if="message.role === 'USER'" class="amsg__user-text">
        {{ message.content }}
      </div>

      <!-- TOOL: 工具调用卡片（历史消息） -->
      <div v-else-if="message.role === 'TOOL'" class="amsg__tool-calls">
        <ToolCallCard v-if="historicalToolCall" :call="historicalToolCall" :default-collapsed="true" />
      </div>

      <!-- ASSISTANT: 实时工具调用卡片 + 流式回答 -->
      <template v-else>
        <div v-if="message.toolCalls && message.toolCalls.length > 0" class="amsg__tool-calls">
          <ToolCallCard
            v-for="tc in message.toolCalls"
            :key="tc.id"
            :call="tc"
          />
        </div>

        <!-- 写操作确认卡片（human-in-the-loop） -->
        <div v-if="message.confirmation" class="amsg__confirm">
          <div class="amsg__confirm-head">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>需要确认的写操作</span>
          </div>
          <p class="amsg__confirm-target">目标：{{ message.confirmation.target }}</p>
          <p class="amsg__confirm-impact">影响：{{ message.confirmation.impact }}</p>
          <div class="amsg__confirm-btns">
            <button class="amsg__confirm-btn amsg__confirm-btn--ok" type="button" @click="emit('confirm-action', 'confirm')">
              {{ message.confirmation.confirmLabel ?? '确认执行' }}
            </button>
            <button class="amsg__confirm-btn amsg__confirm-btn--cancel" type="button" @click="emit('cancel-action', 'cancel')">
              {{ message.confirmation.cancelLabel ?? '取消' }}
            </button>
          </div>
        </div>
        <div v-if="message.streaming && !message.content" class="amsg__thinking">
          <span class="amsg__thinking-dot" />
          <span class="amsg__thinking-dot" />
          <span class="amsg__thinking-dot" />
          <span class="amsg__thinking-label">Agent 正在思考…</span>
        </div>

        <div v-else-if="!message.failed" class="amsg__md" :class="{ 'is-streaming': message.streaming }">
          <div class="amsg__md-content" v-html="rendered" />
          <span v-if="message.streaming" class="amsg__cursor" />
        </div>

        <AssistantCitationBar
          v-if="!message.streaming && message.citations && message.citations.length > 0"
          :citations="message.citations"
          @inspect="(c) => emit('inspect-citation', c)"
        />

        <!-- ASSISTANT failed -->
        <div v-if="message.failed" class="amsg__fail">
          <div class="amsg__fail-head">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>生成失败</span>
          </div>
          <p class="amsg__fail-text">
            {{ message.failureMessage || '请求过程中出现异常，请重试或换一种提问方式。' }}
          </p>
          <button class="amsg__fail-retry" type="button" @click="emit('retry')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            <span>重试</span>
          </button>
        </div>
      </template>
    </div>
  </article>
</template>

<style scoped>
.amsg {
  display: flex;
  gap: 16px;
  padding: 22px 32px 22px 28px;
  animation: amsg-in 0.35s cubic-bezier(0.16, 1, 0.3, 1);
  color: var(--text-primary);
}

@keyframes amsg-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.amsg--user {
  background: transparent;
}

.amsg--assistant {
  background: linear-gradient(180deg, rgba(250, 250, 247, 0.6), rgba(250, 250, 247, 0.3));
  border-top: 1px solid rgba(15, 23, 42, 0.05);
  border-bottom: 1px solid rgba(15, 23, 42, 0.05);
}

.amsg--tool {
  padding: 6px 32px 6px 28px;
  background: transparent;
  opacity: 0.85;
}

/* Avatar */
.amsg__avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.amsg__avatar svg {
  width: 16px;
  height: 16px;
}

.amsg--user .amsg__avatar {
  background: linear-gradient(135deg, #1e293b, #0f172a);
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.2);
}

.amsg--assistant .amsg__avatar {
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-accent));
  box-shadow: 0 2px 8px rgba(74, 144, 217, 0.25);
}

.amsg--tool .amsg__avatar {
  background: var(--surface-muted);
  color: var(--text-muted);
}

/* Body */
.amsg__body {
  flex: 1;
  min-width: 0;
}

.amsg__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.amsg__role {
  font-family: 'Poppins', sans-serif;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}

.amsg__mode-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 1px 7px;
  border-radius: 4px;
  text-transform: uppercase;
}

.amsg__mode-tag--chat {
  color: var(--brand-primary);
  background: rgba(74, 144, 217, 0.1);
}

.amsg__mode-tag--kb_search {
  color: var(--brand-accent-dark);
  background: rgba(92, 201, 193, 0.12);
}

.amsg__mode-tag--admin {
  color: #d97706;
  background: rgba(245, 158, 11, 0.12);
}

.amsg__time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-left: auto;
}

/* USER content */
.amsg__user-text {
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* TOOL */
.amsg__tool {
  margin: 2px 0;
  background: var(--surface-subtle);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
}

.amsg__tool summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  list-style: none;
}

.amsg__tool summary::-webkit-details-marker {
  display: none;
}

.amsg__tool summary svg {
  color: var(--text-muted);
}

.amsg__tool-body {
  margin: 0;
  padding: 10px 14px;
  background: #0f172a;
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem;
  line-height: 1.55;
  overflow-x: auto;
  max-height: 240px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Confirmation (human-in-the-loop) */
.amsg__confirm {
  margin: 8px 0;
  padding: 14px 16px;
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.08), rgba(245, 158, 11, 0.03));
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 10px;
}

.amsg__confirm-head {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  font-family: 'Poppins', 'Noto Sans SC', sans-serif;
  font-size: 0.84rem;
  font-weight: 700;
  color: #b45309;
}

.amsg__confirm-target,
.amsg__confirm-impact {
  margin: 3px 0;
  font-size: 0.84rem;
  line-height: 1.55;
  color: var(--text-secondary);
  word-break: break-word;
}

.amsg__confirm-btns {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.amsg__confirm-btn {
  padding: 7px 18px;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.amsg__confirm-btn--ok {
  color: #fff;
  background: linear-gradient(135deg, #f59e0b, #d97706);
  border: none;
  box-shadow: 0 3px 10px rgba(245, 158, 11, 0.3);
}

.amsg__confirm-btn--ok:hover {
  box-shadow: 0 5px 16px rgba(245, 158, 11, 0.4);
  transform: translateY(-1px);
}

.amsg__confirm-btn--cancel {
  color: var(--text-secondary);
  background: #fff;
  border: 1px solid var(--border-default);
}

.amsg__confirm-btn--cancel:hover {
  border-color: var(--text-muted);
  color: var(--text-primary);
}

/* Thinking */
.amsg__thinking {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 100px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.amsg__thinking-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-primary);
  animation: amsg-think 1.3s ease-in-out infinite;
}

.amsg__thinking-dot:nth-child(2) { animation-delay: 0.15s; }
.amsg__thinking-dot:nth-child(3) { animation-delay: 0.3s; }

@keyframes amsg-think {
  0%, 80%, 100% { transform: scale(0.5); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.amsg__thinking-label {
  margin-left: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
}

/* Fail */
.amsg__fail {
  padding: 14px 16px;
  background: rgba(239, 68, 68, 0.04);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: 10px;
}

.amsg__fail-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-family: 'Poppins', sans-serif;
  font-size: 0.85rem;
  font-weight: 700;
  color: #dc2626;
}

.amsg__fail-text {
  margin: 0 0 8px;
  font-size: 0.87rem;
  color: var(--text-secondary);
  line-height: 1.55;
}

.amsg__fail-retry {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  font-family: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  color: #dc2626;
  background: #fff;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 100px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.amsg__fail-retry:hover {
  background: rgba(239, 68, 68, 0.08);
  border-color: #dc2626;
}

/* Markdown */
.amsg__md {
  position: relative;
  font-size: 0.93rem;
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-word;
}

.amsg__md-content {
  display: inline;
}

/* Streaming cursor */
.amsg__cursor {
  display: inline-block;
  width: 2px;
  height: 1.05em;
  margin-left: 1px;
  background: var(--brand-primary);
  vertical-align: middle;
  animation: amsg-cursor 1.1s ease-in-out infinite;
  border-radius: 1px;
  box-shadow: 0 0 6px rgba(74, 144, 217, 0.5);
}

@keyframes amsg-cursor {
  0%, 45% { opacity: 1; }
  55%, 100% { opacity: 0; }
}

.amsg__md :deep(h1),
.amsg__md :deep(h2),
.amsg__md :deep(h3),
.amsg__md :deep(h4) {
  font-family: 'Poppins', 'Noto Sans SC', sans-serif;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
  margin: 16px 0 8px;
}

.amsg__md :deep(h1) { font-size: 1.4rem; }
.amsg__md :deep(h2) { font-size: 1.2rem; }
.amsg__md :deep(h3) { font-size: 1.05rem; }
.amsg__md :deep(h4) { font-size: 0.95rem; }

.amsg__md :deep(p) { margin: 10px 0; }

.amsg__md :deep(ul),
.amsg__md :deep(ol) {
  margin: 10px 0;
  padding-left: 24px;
}

.amsg__md :deep(ul) { list-style: disc; }
.amsg__md :deep(ol) { list-style: decimal; }

.amsg__md :deep(li) { margin: 4px 0; padding-left: 3px; }

.amsg__md :deep(li::marker) {
  color: var(--brand-primary);
}

.amsg__md :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.84em;
  padding: 1px 6px;
  background: rgba(15, 23, 42, 0.06);
  border-radius: 4px;
  color: var(--brand-primary-dark);
}

.amsg__md :deep(pre) {
  margin: 12px 0;
  padding: 14px 16px;
  background: #0f172a;
  border-radius: 10px;
  overflow-x: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem;
  line-height: 1.6;
  color: #e2e8f0;
  border: 1px solid #1e293b;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.15);
}

.amsg__md :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
  font-size: inherit;
}

.amsg__md :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 3px solid var(--brand-primary);
  background: rgba(74, 144, 217, 0.06);
  border-radius: 0 6px 6px 0;
  color: var(--text-secondary);
  font-style: italic;
}

.amsg__md :deep(a) {
  color: var(--brand-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
  text-decoration-thickness: 1px;
  transition: color 0.15s ease;
}

.amsg__md :deep(a:hover) {
  color: var(--brand-primary-dark);
}

.amsg__md :deep(strong) {
  font-weight: 700;
  color: var(--text-primary);
}

.amsg__md :deep(hr) {
  margin: 18px 0;
  border: none;
  border-top: 1px dashed var(--border-default);
}

.amsg__md :deep(table) {
  width: 100%;
  margin: 12px 0;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.amsg__md :deep(th),
.amsg__md :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--border-default);
  text-align: left;
}

.amsg__md :deep(th) {
  background: var(--surface-subtle);
  font-weight: 700;
  color: var(--text-primary);
}

.amsg__md :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 12px 0;
}

@media (max-width: 720px) {
  .amsg {
    padding: 18px 18px 18px 16px;
    gap: 12px;
  }
}
</style>
