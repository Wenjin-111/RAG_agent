import { marked, Renderer } from 'marked'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { sanitizeHtml } from './sanitize'

// 链接统一在新窗口打开
const renderer = new Renderer()
renderer.link = function ({ href, title, text }) {
  const titleAttr = title ? ` title="${title}"` : ''
  return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
}

// ── KaTeX 公式渲染 ─────────────────────────────
// 支持行内 $...$ / \(...\) 与块级 $$...$$ / \[...\]

function renderKatex(text: string, raw: string, display: boolean): string {
  try {
    return katex.renderToString(text, {
      throwOnError: false,
      displayMode: display,
      output: 'html',
    })
  } catch {
    return raw
  }
}

const inlineMath = {
  name: 'inlineMath',
  level: 'inline',
  start(src: string) {
    const candidates = [src.indexOf('$'), src.indexOf('\\(')].filter((i) => i >= 0)
    return candidates.length > 0 ? Math.min(...candidates) : undefined
  },
  tokenizer(src: string) {
    const m = /^\$([^$\n]+?)\$/.exec(src)
    if (m) return { type: 'inlineMath', raw: m[0], text: m[1] }
    const m2 = /^\\\((.+?)\\\)/.exec(src)
    if (m2) return { type: 'inlineMath', raw: m2[0], text: m2[1] }
    return undefined
  },
  renderer(token: { text: string; raw: string }) {
    return renderKatex(token.text, token.raw, false)
  },
}

const blockMath = {
  name: 'blockMath',
  level: 'block',
  start(src: string) {
    const candidates = [src.indexOf('$$'), src.indexOf('\\[')].filter((i) => i >= 0)
    return candidates.length > 0 ? Math.min(...candidates) : undefined
  },
  tokenizer(src: string) {
    const m = /^\$\$([\s\S]+?)\$\$/.exec(src)
    if (m) return { type: 'blockMath', raw: m[0], text: m[1] }
    const m2 = /^\\\[([\s\S]+?)\\\]/.exec(src)
    if (m2) return { type: 'blockMath', raw: m2[0], text: m2[1] }
    return undefined
  },
  renderer(token: { text: string; raw: string }) {
    return renderKatex(token.text, token.raw, true)
  },
}

marked.use({
  extensions: [inlineMath, blockMath],
  renderer,
  gfm: true,
  breaks: true,
})

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return map[c] ?? c
  })
}

/**
 * 统一 Markdown 渲染入口：marked（GFM + LaTeX 公式）→ DOMPurify 消毒。
 */
export function markdownToHtml(text: string): string {
  if (!text || !text.trim()) return ''
  try {
    return sanitizeHtml(marked.parse(text) as string)
  } catch {
    return escapeHtml(text)
  }
}
