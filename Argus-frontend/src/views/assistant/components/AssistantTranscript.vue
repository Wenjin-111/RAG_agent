<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { AssistantCitationItem, AssistantToolMode } from '@/types/assistant'
import AssistantMessage, { type UiAssistantMessage } from './AssistantMessage.vue'
const props = defineProps<{
  messages: UiAssistantMessage[]
  sessionId: number | null
  sessionTitle: string
  mode: AssistantToolMode
  groupName: string
  loadingHistory: boolean
  hasMoreOlder: boolean
  loadingOlder: boolean
  summaryText: string
  summaryUpdatedAt: string | null
  summaryLoading: boolean
}>()

const emit = defineEmits<{
  'update:mode': [mode: AssistantToolMode]
  'inspect-citation': [citation: AssistantCitationItem]
  retry: []
  'load-older': []
  'refresh-summary': []
}>()

function formatSummaryTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const scrollRef = ref<HTMLElement | null>(null)
const isAtBottom = ref(true)

function scrollToBottom(smooth = true) {
  const el = scrollRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function onScroll() {
  const el = scrollRef.value
  if (!el) return
  const threshold = 80
  isAtBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
}

watch(
  () => props.messages.length,
  async () => {
    await nextTick()
    if (isAtBottom.value) scrollToBottom(true)
  },
)

watch(
  () => props.sessionId,
  async () => {
    await nextTick()
    scrollToBottom(false)
    isAtBottom.value = true
  },
)

// Stream deltas: when last assistant message content length changes
watch(
  () => props.messages[props.messages.length - 1]?.content.length ?? 0,
  async () => {
    await nextTick()
    if (isAtBottom.value) scrollToBottom(false)
  },
)
</script>

<template>
  <div class="atx">
    <!-- Sticky header -->
    <header class="atx__head">
      <div class="atx__head-left">
        <span class="atx__eyebrow">Active Thread</span>
        <h2 class="atx__title" :title="sessionTitle">
          <span class="atx__title-pulse" />
          {{ sessionTitle || '未命名会话' }}
        </h2>
      </div>

    </header>

    <!-- Scroll area -->
    <div ref="scrollRef" class="atx__scroll" @scroll="onScroll">
      <!-- Loading history skeleton -->
      <div v-if="loadingHistory" class="atx__loading">
        <div class="atx__loading-ring" />
        <span>加载历史消息…</span>
      </div>

      <template v-else>
        <!-- Load older messages -->
        <div v-if="hasMoreOlder" class="atx__load-older">
          <button
            class="atx__load-older-btn"
            type="button"
            :disabled="loadingOlder"
            @click="emit('load-older')"
          >
            <span v-if="loadingOlder" class="atx__loading-ring atx__loading-ring--sm" />
            {{ loadingOlder ? '加载中…' : '加载更早消息' }}
          </button>
        </div>

        <!-- Memory summary card -->
        <div v-if="messages.length > 0" class="atx__memory-card">
          <div class="atx__memory-head">
            <span class="atx__memory-title">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20V22H6.5A2.5 2.5 0 0 1 4 19.5V4.5A2.5 2.5 0 0 1 6.5 2Z" />
              </svg>
              AI 记住了什么
            </span>
            <span class="atx__memory-meta">
              <span v-if="summaryUpdatedAt" class="atx__memory-time">
                更新于 {{ formatSummaryTime(summaryUpdatedAt) }}
              </span>
              <button
                class="atx__memory-refresh"
                type="button"
                :disabled="summaryLoading"
                @click="emit('refresh-summary')"
              >
                <svg :class="{ 'is-spinning': summaryLoading }" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                {{ summaryLoading ? '生成中…' : '刷新摘要' }}
              </button>
            </span>
          </div>
          <p v-if="summaryText" class="atx__memory-text">{{ summaryText }}</p>
          <p v-else class="atx__memory-text atx__memory-text--empty">
            暂无记忆摘要——对话超过 20 条后会自动生成，也可以点击"刷新摘要"立即生成。
          </p>
        </div>

        <div class="atx__thread">
          <AssistantMessage
            v-for="m in messages"
            :key="m.localId"
            :message="m"
            @inspect-citation="(c) => emit('inspect-citation', c)"
            @retry="emit('retry')"
          />
        </div>
      </template>
    </div>

    <!-- Scroll-to-bottom fab -->
    <button
      v-show="!isAtBottom"
      class="atx__scroll-btn"
      type="button"
      @click="scrollToBottom(true)"
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="5" x2="12" y2="19" />
        <polyline points="19 12 12 19 5 12" />
      </svg>
      <span>最新</span>
    </button>
  </div>
</template>

<style scoped>
.atx {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #fff;
  position: relative;
}

.atx > * {
  position: relative;
  z-index: 1;
}

/* Head */
.atx__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px 14px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 5;
  flex-shrink: 0;
}

.atx__head-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.atx__eyebrow {
  font-family: 'Poppins', sans-serif;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--brand-primary);
}

.atx__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-family: 'Poppins', 'Noto Sans SC', sans-serif;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
}

.atx__title-pulse {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--brand-accent);
  box-shadow: 0 0 10px rgba(92, 201, 193, 0.6);
  flex-shrink: 0;
  animation: atx-pulse 2.2s ease-in-out infinite;
}

@keyframes atx-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.88); }
}

.atx__head-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* Scroll area with grid paper background (matches Qa) */
.atx__scroll {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-default) transparent;
  background-image:
    linear-gradient(rgba(74, 144, 217, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(74, 144, 217, 0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  background-position: 0 0;
}

.atx__scroll::-webkit-scrollbar {
  width: 6px;
}

.atx__scroll::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: 3px;
}

.atx__scroll::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

.atx__thread {
  max-width: 900px;
  margin: 0 auto;
  padding: 8px 0 24px;
}

/* Loading */
.atx__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 80px 20px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.atx__loading-ring {
  width: 18px;
  height: 18px;
  border: 2px solid var(--surface-muted);
  border-top-color: var(--brand-primary);
  border-radius: 50%;
  animation: atx-spin 0.7s linear infinite;
}

@keyframes atx-spin {
  to { transform: rotate(360deg); }
}

/* Load older */
.atx__load-older {
  display: flex;
  justify-content: center;
  padding: 14px 0 4px;
}

.atx__load-older-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 18px;
  border: 1px solid var(--border-default);
  border-radius: 100px;
  background: #fff;
  font-family: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.atx__load-older-btn:hover:not(:disabled) {
  border-color: var(--brand-primary);
  color: var(--brand-primary);
}

.atx__load-older-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.atx__loading-ring--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

/* Memory summary card */
.atx__memory-card {
  margin: 12px 24px 4px;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(74, 144, 217, 0.05), rgba(92, 201, 193, 0.05));
  border: 1px solid rgba(74, 144, 217, 0.18);
  border-radius: 10px;
}

.atx__memory-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.atx__memory-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: 'Poppins', 'Noto Sans SC', sans-serif;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--brand-primary);
}

.atx__memory-meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.atx__memory-time {
  font-size: 0.66rem;
  color: var(--text-muted);
}

.atx__memory-refresh {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border: 1px solid rgba(74, 144, 217, 0.25);
  border-radius: 100px;
  background: #fff;
  font-family: inherit;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--brand-primary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.atx__memory-refresh:hover:not(:disabled) {
  background: rgba(74, 144, 217, 0.06);
}

.atx__memory-refresh:disabled {
  opacity: 0.6;
  cursor: default;
}

.atx__memory-refresh svg.is-spinning {
  animation: atx-spin 0.9s linear infinite;
}

.atx__memory-text {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.atx__memory-text--empty {
  color: var(--text-muted);
  font-size: 0.78rem;
}

/* Scroll-to-bottom */
.atx__scroll-btn {
  position: absolute;
  right: 24px;
  bottom: 16px;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  font-family: inherit;
  font-size: 0.76rem;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-primary-dark));
  border: none;
  border-radius: 100px;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(74, 144, 217, 0.3);
  animation: fade-in 0.2s ease-out;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.atx__scroll-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(74, 144, 217, 0.4);
}
</style>
