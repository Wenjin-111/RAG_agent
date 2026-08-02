import DOMPurify from 'dompurify'

export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'br', 'hr',
      'ul', 'ol', 'li',
      'blockquote', 'pre', 'code',
      'table', 'thead', 'tbody', 'tr', 'th', 'td',
      'strong', 'em', 'del', 's',
      'a', 'img',
      'sup', 'sub', 'kbd',
      'input',
      // KaTeX 公式结构（span 为公式容器，style 承载上下标定位）
      'span',
      // KaTeX MathML 输出
      'math', 'semantics', 'mrow', 'mi', 'mn', 'mo', 'mtext', 'mspace',
      'mfrac', 'msqrt', 'mroot', 'msub', 'msup', 'msubsup',
      'munder', 'mover', 'munderover', 'annotation',
      // KaTeX SVG（根号等符号绘制）
      'svg', 'path',
    ],
    ALLOWED_ATTR: [
      'href', 'target', 'rel', 'title',
      'src', 'alt', 'width', 'height',
      'type', 'checked', 'disabled',
      'class',
      // KaTeX：上下标定位/字号全部依赖内联 style，缺失则公式塌陷为平排文本
      'style',
      // KaTeX MathML / SVG 属性
      'xmlns', 'encoding', 'mathvariant',
      'd', 'viewBox', 'preserveAspectRatio',
    ],
  })
}
