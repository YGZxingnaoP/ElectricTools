// 引用识别：把 AI 回复 / 公式里出现的「节点名、元件名、电压数值」变成可悬停锚点。
//
// 两条通道（必须分开，原因见下）：
//   ① 正文：DOM text node 遍历 + <span class="ai-ref" data-kind data-ref>
//   ② LaTeX：渲染前用 \htmlClass 包住（KaTeX 会把 n_2 拆成 <span>n</span><span>2</span>，
//      事后再扫 DOM 是扫不到 "n2" 这段连续文本的）
//
// 只识别「当前电路里真实存在」的名字 —— 这是防误伤的第一道闸。

const REF_CLASS_PREFIX = 'ai-ref--';

let REFS = {
  comps: new Set(),
  nodes: new Set(),
  labels: {},          // 自定义节点名 { n1: '中间节点' }
  volts: new Map(),    // 数值 → Set(节点id)，用于「只提到 5 V」时反查
};

/** 主程序在结果/元件/自定义节点名变化时调用，保持识别表与当前电路一致 */
export function setRefs({ comps = [], nodes = [], labels = {}, results = null } = {}) {
  REFS.comps = new Set(comps.filter(Boolean));
  REFS.nodes = new Set(nodes.filter((n) => n && n !== '0'));
  REFS.labels = labels || {};
  const volts = new Map();
  const ns = (results && results.nodes) || {};
  for (const nid of REFS.nodes) {
    const v = ns[nid] && ns[nid].voltage;
    if (typeof v !== 'number' || !Number.isFinite(v)) continue;
    const key = siKey(v);
    if (!volts.has(key)) volts.set(key, new Set());
    volts.get(key).add(nid);
  }
  REFS.volts = volts;
}

// ── 数值 → 归一化 key（容差 3 位有效数字，和显示用的 fmtEng 对齐）───────
function siKey(v) {
  const s = Math.abs(v) === 0 ? 0 : Number(Number(v).toPrecision(3));
  return String(s);
}

// 把 "5 mV" / "1.5kV" / "220 V" 这类文本解析成数值
const SI = { p: 1e-12, n: 1e-9, 'µ': 1e-6, u: 1e-6, m: 1e-3, '': 1, k: 1e3, K: 1e3, M: 1e6, G: 1e9 };
const VOLT_RE = /(\d+(?:\.\d+)?)\s*(p|n|µ|u|m|k|K|M|G)?\s*V\b/g;

/** 从数值 token 找到唯一对应的节点（多义返回 null，宁可不高亮） */
function nodeByVoltage(text) {
  VOLT_RE.lastIndex = 0;
  let m;
  while ((m = VOLT_RE.exec(text))) {
    const key = siKey(parseFloat(m[1]) * (SI[m[2] || ''] ?? 1));
    const hit = REFS.volts.get(key);
    if (hit && hit.size === 1) return [...hit][0];
  }
  return null;
}

// ── 令牌表：只用"当前存在"的名字构正则，天然不会命中不存在的元件 ────────
function tokenTable() {
  const names = [];
  for (const id of REFS.comps) names.push([id, { kind: 'comp', id }]);
  for (const id of REFS.nodes) names.push([id, { kind: 'node', id }]);
  for (const [nid, label] of Object.entries(REFS.labels || {})) {
    const t = String(label || '').trim();
    if (t.length >= 2) names.push([t, { kind: 'node', id: nid }]);   // 单字母名太吵，不要
  }
  names.sort((a, b) => b[0].length - a[0].length);                    // 长名优先
  return names;
}

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function textRe(table) {
  if (!table.length) return null;
  const alt = table.map(([t]) => esc(t)).join('|');
  // 不用 lookbehind（兼容性），用捕获组保住前一个字符
  return new RegExp(`(^|[^A-Za-z0-9_])(${alt})(?![A-Za-z0-9_])`, 'g');
}

function latexRe(table) {
  if (!table.length) return null;
  // LaTeX 里可能是 R1 或 R_1 两种写法
  const alt = table.map(([t]) => esc(t).replace(/([A-Za-z])(\d)/g, '$1_?$2')).join('|');
  return new RegExp(`(^|[^A-Za-z0-9_{])((?:${alt}))(?![A-Za-z0-9_}])`, 'g');
}

// ── 通道 ①：正文 ────────────────────────────────────────────────
const SKIP_SEL = 'pre, code, .katex, .think, .ai-ref, [class*="ai-ref--"]';

/** 遍历 root 下的 text node，把引用包成可悬停 span。返回包裹数量。 */
export function wrapTextNodes(root) {
  if (!root) return 0;
  const table = tokenTable();
  const re = textRe(table);
  if (!re) return 0;
  const map = new Map(table);

  // 先收集，避免边遍历边改 DOM
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      const p = node.parentElement;
      if (!p || p.closest(SKIP_SEL)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const targets = [];
  while (walker.nextNode()) targets.push(walker.currentNode);

  let n = 0;
  for (const node of targets) {
    const text = node.nodeValue;
    re.lastIndex = 0;
    if (!re.test(text)) continue;
    re.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0;
    let m;
    while ((m = re.exec(text))) {
      const hit = map.get(m[2]);
      let ref = hit;
      if (!ref) {
        const vid = nodeByVoltage(m[2]);
        if (vid) ref = { kind: 'node', id: vid };
      }
      if (!ref) continue;
      const start = m.index + m[1].length;
      if (start > last) frag.appendChild(document.createTextNode(text.slice(last, start)));
      const sp = document.createElement('span');
      sp.className = 'ai-ref';
      sp.dataset.kind = ref.kind;
      sp.dataset.ref = ref.id;
      sp.textContent = m[2];
      frag.appendChild(sp);
      last = start + m[2].length;
      n++;
    }
    if (!last) continue;
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    node.parentNode.replaceChild(frag, node);
  }
  return n;
}

// ── 通道 ②：LaTeX ───────────────────────────────────────────────
/** 渲染前把 LaTeX 里的引用包成 \htmlClass（配合 katexOpts 的 trust 白名单） */
export function wrapLatex(tex) {
  const s = String(tex ?? '');
  const table = tokenTable();
  const re = latexRe(table);
  if (!re) return s;
  const map = new Map(table);
  return s.replace(re, (all, pre, hit) => {
    const ref = map.get(hit) || map.get(hit.replace('_', ''));
    if (!ref) return all;
    const cls = `${REF_CLASS_PREFIX}${ref.kind}--${ref.id}`;
    return `${pre}\\htmlClass{${cls}}{${hit}}`;
  });
}

// ── KaTeX 渲染选项：只放行 \htmlClass / \htmlId，其余 trust 命令一律拒绝 ──
export function katexOpts(display) {
  return {
    throwOnError: false,
    displayMode: !!display,
    trust: (ctx) => ctx.command === '\\htmlClass' || ctx.command === '\\htmlId',
  };
}

// ── 从元素反解出引用（正文 span 与 KaTeX 的 \htmlClass 两种形态都认）────
export function refFromEl(el) {
  if (!el || !el.classList) return null;
  for (const c of el.classList) {
    if (c.startsWith(REF_CLASS_PREFIX)) {
      const parts = c.slice(REF_CLASS_PREFIX.length).split('--');
      if (parts.length === 2) return { kind: parts[0], id: parts[1] };
    }
  }
  if (el.classList.contains('ai-ref') && el.dataset && el.dataset.ref) {
    return { kind: el.dataset.kind || 'node', id: el.dataset.ref };
  }
  return null;
}

/** 事件委托用：从任意事件目标往上找最近的引用元素 */
export function refElFrom(target) {
  try {
    return target && target.closest ? target.closest(`.ai-ref, [class*="${REF_CLASS_PREFIX}"]`) : null;
  } catch {
    return null;
  }
}
