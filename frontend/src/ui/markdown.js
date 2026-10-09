// Markdown 渲染：marked + marked-highlight + highlight.js（参考 D:\YOder 的做法）
// 增强：支持 KaTeX 数学公式 $$...$$ 与 $...$，并在代码块上加复制按钮。
import { marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import bash from 'highlight.js/lib/languages/bash';
import json from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import c from 'highlight.js/lib/languages/c';
import cpp from 'highlight.js/lib/languages/cpp';
import latex from 'highlight.js/lib/languages/latex';
import xml from 'highlight.js/lib/languages/xml';
import markdownLang from 'highlight.js/lib/languages/markdown';
import plaintext from 'highlight.js/lib/languages/plaintext';
import 'highlight.js/styles/github-dark.css';
import { protectMath, restoreMath } from './mdMath.js';

// 只注册常用语言，避免把全部语言打进包里
hljs.registerLanguage('python', python);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('json', json);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('c', c);
hljs.registerLanguage('cpp', cpp);
hljs.registerLanguage('latex', latex);
hljs.registerLanguage('tex', latex);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('markdown', markdownLang);
hljs.registerLanguage('plaintext', plaintext);
hljs.registerLanguage('text', plaintext);

let inited = false;

function init() {
  if (inited) return;
  marked.use(markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      try {
        if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
        return hljs.highlightAuto(code).value;
      } catch {
        return code;
      }
    }
  }));
  marked.setOptions({ breaks: true, gfm: true });
  inited = true;
}

/** 移除脚本/事件属性等危险内容（AI 输出经 markdown 渲染后可能带链接） */
export function sanitizeHtml(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html || '';
  tpl.content
    .querySelectorAll('script,style,iframe,object,embed,link,meta,form,svg')
    .forEach((n) => n.remove());
  tpl.content.querySelectorAll('*').forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const val = (attr.value || '').trim().toLowerCase();
      if (name.startsWith('on') || ((name === 'href' || name === 'src') && val.startsWith('javascript:'))) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return tpl.innerHTML;
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function katexHtml(tex, display) {
  const k = typeof window !== 'undefined' ? window.katex : null;
  if (!k) return `<code>${esc(tex)}</code>`;
  try {
    return k.renderToString(String(tex).trim(), { throwOnError: false, displayMode: !!display });
  } catch {
    return `<code>${esc(tex)}</code>`;
  }
}

/** 文本 → HTML（markdown + 公式 + 代码高亮） */
export function renderMarkdown(text) {
  init();
  const { text: prepared, stash } = protectMath(text, katexHtml);
  let html = marked.parse(prepared);
  html = sanitizeHtml(html);              // 先净化（此时只有占位符，安全）
  html = restoreMath(html, stash);        // 再插入 KaTeX（保留其内部结构）
  return html;
}

/** 给容器内每个代码块加“复制”按钮（参考 YOder） */
export function addCopyButtons(container) {
  container.querySelectorAll('pre').forEach((pre) => {
    if (pre.querySelector('.md-copy')) return;
    const btn = document.createElement('button');
    btn.className = 'md-copy';
    btn.textContent = '复制';
    btn.onclick = () => {
      const code = pre.querySelector('code')?.textContent || '';
      try { navigator.clipboard.writeText(code); } catch { /* ignore */ }
      btn.textContent = '已复制';
      setTimeout(() => { btn.textContent = '复制'; }, 1500);
    };
    pre.appendChild(btn);
  });
}

/** 便捷：直接渲染到元素 */
export function setMarkdown(el, text) {
  if (!el) return;
  el.innerHTML = renderMarkdown(text);
  addCopyButtons(el);
}
