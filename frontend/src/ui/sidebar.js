// 侧栏：元件属性、数值结果、符号公式（KaTeX）、校验状态
import { fmtNum } from '../core/numfmt.js';

export function renderInspector(el, state, handlers) {
  if (!el) return;

  // ① 选中的是图上的「已知量」标注 → 编辑它
  const note = state.getSelectedNote ? state.getSelectedNote() : null;
  if (note) {
    const tg = (handlers.noteTargets && handlers.noteTargets()) || { nodes: [], components: [] };
    const isI = note.kind === 'branch_current';
    const list = isI ? tg.components : tg.nodes;
    const opts = list.length
      ? list.map((t) => `<option value="${esc(t.value)}"${t.value === note.anchor ? ' selected' : ''}>${esc(t.label)}</option>`).join('')
      : '<option value="">（先求解一次，才能列出可标注的节点/元件）</option>';
    el.innerHTML = `
      <label>标注什么</label>
      <select id="note-kind">
        <option value="node_voltage"${isI ? '' : ' selected'}>节点电压 (V)</option>
        <option value="branch_current"${isI ? ' selected' : ''}>支路电流 (A)</option>
      </select>
      <label>对象</label>
      <select id="note-target">${opts}</select>
      <label>数值</label>
      <input id="note-value" type="text" spellcheck="false" value="${esc(note.value ?? '')}" placeholder="如 2、2000mV" />
      <button id="note-del" class="mini-btn" style="width:100%">删除这个标注</button>
      <p class="muted">它是画在图上的<b>已知量</b>：求解时自动拿它反解未知量。类型和对象都可以随时改，不用重新画。</p>
    `;
    el.querySelector('#note-kind').addEventListener('change', (e) => handlers.onNoteKind(note.id, e.target.value));
    el.querySelector('#note-target').addEventListener('change', (e) => handlers.onNoteTarget(note.id, e.target.value));
    el.querySelector('#note-value').addEventListener('change', (e) => handlers.onNoteValue(note.id, e.target.value));
    el.querySelector('#note-del').addEventListener('click', () => handlers.onNoteDelete(note.id));
    return;
  }

  const c = state.getSelectedComponent();
  if (!c) {
    el.innerHTML = '<p class="muted">未选中元件（点击画布上的元件）</p>';
    return;
  }
  const isSource = c.type === 'vsource' || c.type === 'isource';
  const unit = c.unit || (c.type === 'resistor' ? 'Ω' : '');
  const unknown = !!c.symbol;
  const unkList = state.components.filter((x) => x.value == null && x.type !== 'ground').map((x) => x.id);
  const p = c.params || {};
  const inp = (key, label, val, step = 'any') =>
    `<label>${label}</label><input class="insp-param" data-key="${key}" type="number" step="${step}" value="${val ?? ''}" />`;
  const sel = (key, label, val, opts) =>
    `<label>${label}</label><select class="insp-param" data-key="${key}">` +
    opts.map(([v, t]) => `<option value="${v}"${String(val) === String(v) ? ' selected' : ''}>${t}</option>`).join('') +
    `</select>`;
  let extra = '';
  if (isSource) {
    extra += sel('kind', '类型', p.kind || 'dc',
                 [['dc', '直流'], ['ac', '正弦交流（有效值）'], ['step', '阶跃（暂态用）']]);
    if ((p.kind || 'dc') === 'ac') {
      extra += inp('freq', '频率 f (Hz)', p.freq ?? 50);
      extra += inp('phase', '初相角 (°)', p.phase ?? 0);
    }
  } else if (c.type === 'vcvs' || c.type === 'vccs' || c.type === 'ccvs' || c.type === 'cccs') {
    extra += inp('gain', c.type === 'vccs' ? '转移电导 gm (S)' : c.type === 'ccvs' ? '转移电阻 r (Ω)'
                    : c.type === 'cccs' ? '电流放大 β' : '电压放大 μ', p.gain ?? 1);
    if (c.type === 'ccvs' || c.type === 'cccs') {
      const others = state.components.filter((x) => x.id !== c.id && x.type === 'vsource').map((x) => x.id);
      extra += sel('control', '控制支路（哪个电压源的电流）', p.control || (others[0] || ''),
                   [['', '（自动）'], ...others.map((o) => [o, o])]);
    }
  } else if (c.type === 'transformer') {
    extra += inp('ratio', '变比 n = N1/N2', p.ratio ?? 2);
  } else if (c.type === 'bjt') {
    extra += inp('beta', '电流放大 β', p.beta ?? 100);
    extra += inp('vbe', '导通 Vbe (V)', p.vbe ?? 0.7);
  } else if (c.type === 'diode') {
    extra += inp('vth', '导通压降 (V)', p.vth ?? 0.7);
    extra += inp('rd', '导通内阻 (Ω)', p.rd ?? 0);
  } else if (c.type === 'zener') {
    extra += inp('vz', '击穿电压 Vz (V)', p.vz ?? 5.1);
    extra += inp('rd', '导通内阻 (Ω)', p.rd ?? 0);
  } else if (c.type === 'switch') {
    extra += sel('closed', '状态', p.closed === false ? 'false' : 'true',
                 [['true', '闭合（短路）'], ['false', '断开（开路）']]);
    extra += inp('t_switch', '换路时刻 t (s，留空=一直不变)', p.t_switch ?? '');
    extra += '<p class="muted" style="font-size:12px">填了换路时刻 → 暂态分析会在该时刻翻转开关'
           + '（电容电压/电感电流不跃变）。可设多个开关、不同时刻。</p>';
  }
  el.innerHTML = `
    <label>位号 / 编号（可自定义）</label>
    <input id="insp-id" type="text" value="${esc(c.id)}" spellcheck="false" />
    <label>数值 (${unit || '—'})${unknown ? '（未知量，已停用）' : ''}</label>
    <input id="insp-value" type="number" step="any" value="${c.value ?? ''}" ${unknown ? 'disabled' : ''} />
    ${extra}
    <label>符号 / 未知量占位（如 R、Ux、U_oc）</label>
    <input id="insp-symbol" type="text" value="${esc(c.symbol || '')}" spellcheck="false"
           placeholder="留空 = 已知数值；填写后按未知量处理" />
    <label>旋转</label>
    <select id="insp-rot">
      ${[0, 90, 180, 270].map((r) => `<option value="${r}" ${c.rotation === r ? 'selected' : ''}>${r}°</option>`).join('')}
    </select>
    ${unknown ? '<p class="muted">当前按未知量处理：仅给出含该符号的公式，不给数值。</p>' : ''}
    ${isSource ? '<p class="muted">参考方向：p0(正端) → p1</p>' : ''}
  `;
  el.querySelectorAll('.insp-param').forEach((node) => {
    node.addEventListener('change', (e) => {
      const key = e.target.dataset.key;
      let v = e.target.value;
      if (e.target.type === 'number') v = parseFloat(v);
      else if (v === 'true') v = true;
      else if (v === 'false') v = false;
      handlers.onParam(c.id, key, v);
      if (key === 'kind') renderInspector(el, state, handlers);   // 切交流后要露出频率/相角
    });
  });
  el.querySelector('#insp-id').addEventListener('change', (e) => {
    handlers.onRename(c.id, e.target.value);
    e.target.value = state.getSelectedComponent()?.id ?? c.id;
  });
  el.querySelector('#insp-value').addEventListener('change', (e) => {
    handlers.onValue(c.id, parseFloat(e.target.value));
  });
  el.querySelector('#insp-symbol').addEventListener('change', (e) => {
    handlers.onSymbol(c.id, e.target.value);
  });
  el.querySelector('#insp-rot').addEventListener('change', (e) => {
    handlers.onRotate(c.id, parseInt(e.target.value, 10));
  });
}

// 「代数参考值」：只给代数式（含符号），不给数值 —— 数值去「一键求解」按一下拿。
// 求解结果（仅数字）。opts: { nodeLabels, onRenameNode }
export function renderResults(el, results, opts = {}) {
  if (!el) return;
  const labels = opts.nodeLabels || {};
  if (!results || !results.ok) {
    el.innerHTML = '<p class="muted">尚未得到有效解</p>' + renderDiagnostics(results);
    return;
  }
  const rows = [];
  for (const nid of results.node_order) {
    if (nid === '0') continue;
    const n = results.nodes[nid];
    const label = labels[nid];
    const ph = n.phasor ? `<span class="muted"> ∠${fmtNum(n.phasor.phase)}°</span>` : '';
    const unit = n.phasor ? ' V(有效值)' : ' V';
    rows.push(
      `<tr>` +
      `<td class="node-id">${esc(nid)}</td>` +
      `<td><button class="link-btn" data-node="${esc(nid)}" title="点击命名该节点">${label ? esc(label) : '＋命名'}</button></td>` +
      `<td class="val">${fmtNum(n.voltage)}${esc(unit)}${ph}` +
      `${n.is_reference ? '<span class="muted" title="未接地时自动选的参考节点，它的 0 V 是定义"> 参考</span>' : ''}</td></tr>`
    );
  }
  const brows = results.branches.map((b) => {
    const neg = b.current !== null && b.current !== undefined && b.current < 0;
    const ph = b.phasor ? `<span class="muted"> ∠${fmtNum(b.phasor.phase)}°</span>` : '';
    const unit = b.phasor ? ' A(有效值)' : ' A';
    const pw = b.power && b.power.p !== undefined && b.phasor
      ? `<span class="muted">  P=${fmtNum(b.power.p)}W Q=${fmtNum(b.power.q)}var</span>` : '';
    return `<tr><td>${esc(b.component)}</td>` +
      `<td class="val">${fmtNum(b.current)}${esc(unit)}${ph}${pw}` +
      `${neg ? '<span class="muted"> ←实际 p1→p0</span>' : ''}</td></tr>`;
  });
  el.innerHTML = `
    ${renderDiagnostics(results)}
    ${renderSolvedUnknowns(results)}
    ${renderWiring(results)}
    <table>
      <tr><th>节点</th><th>名称</th><th>电压 (V)</th></tr>
      ${rows.join('')}
    </table>
    <table style="margin-top:10px">
      <tr><th>支路</th><th>电流 (A, 以 p0→p1 为正)</th></tr>
      ${brows.join('')}
    </table>
    <p class="muted" style="font-size:12px;line-height:1.5">
      符号约定：支路电流参考方向一律 <b>p0 → p1</b>；<b>画布上的箭头画的是实际方向</b>（负电流会整根反过来）。
      电压源 <b>p0 端是 ＋</b>（V(p0)−V(p1)=数值）；电流源符号里的<b>箭头指向 p0</b>，
      即电流从 p1 穿到 p0 出来、注入 p0 所在节点，所以它的支路电流 = −数值。
    </p>
  `;
  el.querySelectorAll('.link-btn[data-node]').forEach((b) => {
    b.addEventListener('click', () => opts.onRenameNode && opts.onRenameNode(b.dataset.node));
  });
  renderTex(el);      // 反解的分步推导里有公式
}

// 接线自检：每个节点上到底挂了哪些元件 —— 串还是并，用人话写出来
// 暂态波形（后端的 waveform：{t:[…], "U:C1":[…], "I:L1":[…], "V:n1":[…]…}）
function renderWaveform(results) {
  const w = results && results.waveform;
  if (!w || !w.t || w.t.length < 2) return '';
  const t = w.t;
  // 优先画「动态元件」（电容/电感）自己的电压和电流 —— 暂态题就看它们
  const reactive = new Set((results.branches || [])
    .filter((b) => b.type === 'capacitor' || b.type === 'inductor')
    .map((b) => b.component));
  let keys = Object.keys(w).filter((k) => k !== 't' && reactive.has(String(k).split(':')[1]));
  if (!keys.length) keys = Object.keys(w).filter((k) => k.startsWith('U:'));
  if (!keys.length) keys = Object.keys(w).filter((k) => k.startsWith('I:'));
  if (!keys.length) keys = Object.keys(w).filter((k) => k !== 't');
  keys = keys.slice(0, 4);
  if (!keys.length) return '';
  const W = 330, H = 160, L = 34, B = 22;
  const all = keys.flatMap((k) => w[k] || []);
  let lo = Math.min(...all), hi = Math.max(...all);
  if (!(hi > lo)) { hi = lo + 1; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const X = (i) => L + (W - L - 8) * (i / (t.length - 1));
  const Y = (v) => (H - B) - (H - B - 10) * ((v - lo) / (hi - lo));
  const COLORS = ['#4f9cf9', '#f9a04f', '#7ee787', '#f97e9e'];
  const paths = keys.map((k, i) => {
    const d = (w[k] || []).map((v, j) => `${j ? 'L' : 'M'}${X(j).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
    return `<path d="${d}" fill="none" stroke="${COLORS[i % 4]}" stroke-width="1.6" />`;
  }).join('');
  const legend = keys.map((k, i) => `<span style="color:${COLORS[i % 4]}">${esc(k)}</span>`).join('　');
  return `<div class="wave-box">
    <div class="lab">暂态波形（横轴 t，共 ${t.length} 点）</div>
    <svg viewBox="0 0 ${W} ${H}" class="wave-svg" preserveAspectRatio="none">
      <line x1="${L}" y1="10" x2="${L}" y2="${H - B}" stroke="#3a4453" />
      <line x1="${L}" y1="${H - B}" x2="${W - 8}" y2="${H - B}" stroke="#3a4453" />
      <text x="2" y="16" fill="#8894a8" font-size="10">${esc(fmtNum(hi))}</text>
      <text x="2" y="${H - B}" fill="#8894a8" font-size="10">${esc(fmtNum(lo))}</text>
      <text x="${W - 66}" y="${H - B + 13}" fill="#8894a8" font-size="10">t = ${esc(fmtNum(t[t.length - 1]))} s</text>
      ${paths}
    </svg>
    <div class="muted" style="font-size:11px">${legend}</div>
  </div>`;
}

function renderWiring(results) {
  if (!results || !results.ok) return '';
  const lines = [];
  for (const nid of results.node_order) {
    const info = results.nodes[nid];
    const comps = [];
    for (const m of (info.members || [])) {
      const mm = /^u:([^/]+)\//.exec(m);
      if (mm && !/^GND/i.test(mm[1]) && !comps.includes(mm[1])) comps.push(mm[1]);
    }
    if (comps.length < 2) continue;
    const list = comps.join('、');
    const tail = comps.length > 2
      ? ` —— 这 ${comps.length} 个元件的端子都接在同一点上，它们是<b>并接</b>的`
      : ' —— 只有这两个元件接在这里，它们是<b>串接</b>的';
    const ground = nid === '0' ? '（参考地）' : '';
    lines.push(`<div class="wire-node"><b>节点 ${esc(nid)}</b>${ground}：${esc(list)}${tail}</div>`);
  }
  if (!lines.length) return '';
  return `<details class="wiring"><summary>接线自检 —— 谁和谁接在一起（串/并联）</summary>${lines.join('')}</details>`;
}

// 公式拆解：每一部分乘起来是什么 · 这么算的依据
function renderDecomp(d) {
  if (!d) return '';
  const basis = (d.basis || []).map((b) => `<div class="basis">依据：${esc(b)}</div>`).join('');
  if (d.too_many || !(d.terms || []).length) {
    return basis ? `<details class="decomp"><summary>依据</summary>${basis}</details>` : '';
  }
  const den = d.den;
  const denLine = den
    ? `<div class="d-line">共同分母 <span class="tex" data-tex="${esc(den.latex)}"></span> = ${esc(den.text)} = <b>${esc(den.value)} ${esc(den.unit)}</b></div>`
    : '';
  const terms = d.terms.map((t, i) => {
    const n = t.num || {};
    const notes = (n.factors || []).filter((f) => f.desc)
      .map((f) => `<div class="d-note">· <span class="tex" data-tex="${esc(f.latex)}"></span> 是 ${esc(f.desc)}</div>`).join('');
    const tail = den ? ` ÷ ${esc(den.value)} ${esc(den.unit)} =` : ' =';
    return `<div class="d-term">
      <div class="d-head">第 ${i + 1} 项 <span class="tex" data-tex="${esc(t.latex)}"></span></div>
      <div class="d-line">分子 <span class="tex" data-tex="${esc(n.latex)}"></span> = ${esc(n.text)} = <b>${esc(n.value)} ${esc(n.unit)}</b></div>
      <div class="d-line">结果 ${esc(n.value)} ${esc(n.unit)}${tail} <b>${esc(t.result.value)} ${esc(t.result.unit)}</b></div>
      ${notes}
    </div>`;
  }).join('');
  return `<details class="decomp">
    <summary>拆解：每一部分乘起来是什么 · 依据</summary>
    ${denLine}${terms}${basis}
  </details>`;
}

// 符号公式（单独区块，字号更大）：每行 ① 含符号的式子 ② 代入已知数值后的式子 ③ 可展开的拆解
export function renderFormulas(el, results) {
  if (!el) return;
  if (!results || !results.ok) {
    el.innerHTML = '<p class="muted">—</p>';
    return;
  }
  const row = (tag, sym, sub, decomp) => {
    const extra = (sub && sub !== sym)
      ? `<div class="frow fsub"><span class="tag">代入已知数值</span><span class="tex" data-tex="${esc(sub)}"></span></div>`
      : '';
    return `<div class="frow"><span class="tag">${esc(tag)}</span><span class="tex" data-tex="${esc(sym)}"></span></div>`
      + extra + renderDecomp(decomp);
  };
  const rows = [];
  for (const nid of results.node_order) {
    if (nid === '0') continue;
    const n = results.nodes[nid];
    if (!n.voltage_latex) continue;
    rows.push(row(`V(${nid}) =`, n.voltage_latex, n.voltage_latex_sub, n.voltage_decomp));
  }
  for (const b of results.branches) {
    if (!b.current_latex) continue;
    rows.push(row(`I(${b.component}) =`, b.current_latex, b.current_latex_sub, b.current_decomp));
  }
  el.innerHTML = (hasKatex() ? ''
    : '<p class="muted" style="font-size:12px;line-height:1.5">公式以纯文本显示'
      + '（KaTeX 没加载出来：检查 /lib/katex/katex.min.js 是否存在，硬刷新 Ctrl+Shift+R）。</p>')
    + (rows.length ? rows.join('') : '<p class="muted">（无符号式）</p>');
  renderTex(el);
}

export function renderValidation(el, results) {
  if (!el) return;
  if (!results) { el.innerHTML = '<p class="muted">—</p>'; return; }
  if (!results.validation) {
    el.innerHTML = '<p class="muted">数值解（未做符号校验）</p>';
    return;
  }
  const v = results.validation;
  const badge = v.ok ? '<span class="badge ok">通过 ✓</span>' : '<span class="badge bad">不一致</span>';
  el.innerHTML = `
    <p>${badge} <span class="muted">MNA(数值) vs lcapy(符号)</span></p>
    <table>
      <tr><td>最大绝对差</td><td class="val">${fmtNum(v.max_abs_diff, 4)} V</td></tr>
      <tr><td>最大相对差</td><td class="val">${fmtNum(v.max_rel_diff, 4)}</td></tr>
      <tr><td>阈值</td><td class="val">${v.tol}</td></tr>
    </table>
    ${(v.notes || []).map((n) => `<div class="diag warn">${esc(n)}</div>`).join('')}
  `;
}

// 图上「已知量」自动解出的未知量 + 反解/算法推导
function renderSolvedUnknowns(results) {
  const cr = results && results.constraint_result;
  if (!cr) return '';
  if (cr.error && !(cr.solutions || []).length) return `<div class="diag warn">${esc(cr.error)}</div>`;
  const sol = (cr.solutions || [])[0];
  if (!sol) return '';
  const items = Object.entries(sol.values || {}).map(([cid, info]) =>
    `<div class="inv-ok">✓ ${esc(cid)} = <b>${fmtNum(info.value)} ${esc(info.unit)}</b>${info.feasible ? '' : ` <span class="inv-warn">（${esc(info.note || '不可行')}）</span>`}</div>`
  ).join('');
  const conds = (cr.conditions || []).map((c) => `${esc(c.label)} = ${esc(c.value)}`).join('，');
  // 一步一步推：找出待求量 → 写条件式 → 列方程 → 解出
  const steps = (cr.steps || []).map((s) => `
    <div class="step">
      <div class="step-t">${esc(s.title)}</div>
      ${s.text ? `<div class="step-x">${esc(s.text)}</div>` : ''}
      ${s.latex ? `<div class="step-eq"><span class="tex" data-tex="${esc(s.latex)}"></span></div>` : ''}
      ${(s.table || []).map((r) => `<div class="step-eq"><span class="tex" data-tex="${esc(`${r.label} = ${r.expr}`)}"></span>
        <span class="muted">— 题目给 ${esc(r.value)}</span></div>`).join('')}
    </div>`).join('');
  const method = cr.method ? `（${cr.method}）` : '';
  const label = cr.method ? `${cr.method}算出` : '由图上的「已知量」解出';
  return `<div class="solved-box">
    <div class="lab">${esc(label)}</div>
    ${conds ? `<div class="muted" style="font-size:12px">条件：${conds}</div>` : ''}
    ${items}
    ${steps ? `<details class="inv-steps"><summary>一步一步推（${(cr.steps || []).length} 步）</summary>${steps}</details>` : ''}
  </div>`;
}

function renderDiagnostics(results) {
  if (!results || !results.diagnostics) return '';
  return results.diagnostics
    .map((d) => `<div class="diag ${d.level}">${esc(d.message)}</div>`)
    .join('');
}

// LaTeX → 可读纯文本。公式绝不能因为「KaTeX 没加载出来（断网/CDN 被墙）」就消失，
// 所以 KaTeX 不可用时降级成纯文本显示。
export function texToPlain(tex) {
  let s = String(tex ?? '');
  s = s.replace(/_\{([^{}]*)\}/g, '_$1').replace(/\^\{([^{}]*)\}/g, '^$1');       // R_{2} → R_2
  s = s.replace(/\\text\{([^{}]*)\}/g, '$1').replace(/\\mathrm\{([^{}]*)\}/g, '$1');
  for (let i = 0; i < 8 && s.includes('\\frac'); i++) {                            // 分数转 (a)/(b)
    s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (m, a, b) => `(${a})/(${b})`);
  }
  s = s.replace(/\\left|\\right/g, '')
    .replace(/\\cdot|\\times/g, '×')
    .replace(/\\div/g, '÷')
    .replace(/\\Omega/g, 'Ω')
    .replace(/\\mu/g, 'µ')
    .replace(/\\[,;!]/g, ' ');
  return s.replace(/\\[a-zA-Z]+/g, '').replace(/[{}\\]/g, '').replace(/\s+/g, ' ').trim();
}

function renderTex(scope) {
  const katex = (typeof window !== 'undefined' && window.katex) || null;
  scope.querySelectorAll('.tex').forEach((elm) => {
    const tex = elm.getAttribute('data-tex');
    if (!tex) { elm.textContent = '—'; return; }
    if (katex) {
      try {
        katex.render(tex, elm, { throwOnError: false, displayMode: false });
        return;
      } catch { /* 落到纯文本 */ }
    }
    elm.classList.add('tex-plain');
    elm.textContent = texToPlain(tex);
  });
}

export function hasKatex() {
  return typeof window !== 'undefined' && !!window.katex;
}

export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
