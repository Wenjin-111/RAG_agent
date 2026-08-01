<script setup lang="ts">
import { ref } from 'vue'

defineOptions({ inheritAttrs: true })

const props = defineProps<{
  text: string
}>()

const show = ref(false)
const pos = ref({ top: 0, left: 0, width: 400 })
let hideTimer: ReturnType<typeof setTimeout> | null = null

function onEnter(e: MouseEvent) {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const width = Math.max(320, Math.min(420, window.innerWidth - rect.left - 16))
  pos.value = {
    top: rect.bottom + 6,
    left: rect.left,
    width,
  }
  show.value = true
}

function onLeave() {
  hideTimer = setTimeout(() => {
    show.value = false
  }, 150)
}

function onPopEnter() {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

function onPopLeave() {
  show.value = false
}
</script>

<template>
  <span class="hvp" @mouseenter="onEnter" @mouseleave="onLeave">{{ props.text }}</span>
  <Teleport to="body">
    <div
      v-if="show"
      class="hvp-pop"
      :style="{ top: `${pos.top}px`, left: `${pos.left}px`, width: `${pos.width}px` }"
      @mouseenter="onPopEnter"
      @mouseleave="onPopLeave"
    >
      <div class="hvp-pop__inner">{{ props.text }}</div>
    </div>
  </Teleport>
</template>

<style scoped>
.hvp {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: default;
}

.hvp-pop {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
  padding: 10px 14px;
  font-size: 0.82rem;
  line-height: 1.7;
  color: var(--text-primary);
}

.hvp-pop__inner {
  max-height: 320px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
