// 侧栏：元件属性、数值结果、符号公式（KaTeX）、校验状态
import { fmtNum } from '../core/numfmt.js';

export function renderInspector(el, state, handlers) {
  if (!el) return;
  const c = state.getSelectedComponent();
  if (!c) {
    el.innerHTML = '<p class="muted">未选中元件（点击画布上的元件）</p>';
    return;
  }
  const isSource = c.type === 'vsource' || c.type === 'isource';
  const unit = c.unit || (c.type === 'resistor' ? 'Ω' : '');
  const unknown = !!c.symbol;
  el.innerHTML = `
    <label>位号 / 编号（可自定义）</label>
    <input id="insp-id" type="text" value="${esc(c.id)}" spellcheck="false" />
    <label>数值 (${unit || '—'})${unknown ? '（未知量，已停用）' : ''}</label>
    <input id="insp-value" type="number" step="any" value="${c.value ?? ''}" ${unknown ? 'disabled' : ''} />
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

// 数值结果（仅数字）。opts: { nodeLabels, onRenameNode }
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
    rows.push(
      `<tr>` +
      `<td class="node-id">${esc(nid)}</td>` +
      `<td><button class="link-btn" data-node="${esc(nid)}" title="点击命名该节点">${label ? esc(label) : '＋命名'}</button></td>` +
      `<td class="val">${fmtNum(n.voltage)} V</td></tr>`
    );
  }
  const brows = results.branches.map(
    (b) => `<tr><td>${esc(b.component)}</td><td class="val">${fmtNum(b.current)} A</td></tr>`
  );
  el.innerHTML = `
    <table>
      <tr><th>节点</th><th>名称</th><th>电压 (V)</th></tr>
      ${rows.join('')}
    </table>
    <table style="margin-top:10px">
      <tr><th>支路</th><th>电流 (A, p0→p1)</th></tr>
      ${brows.join('')}
    </table>
    ${renderDiagnostics(results)}
  `;
  el.querySelectorAll('.link-btn[data-node]').forEach((b) => {
    b.addEventListener('click', () => opts.onRenameNode && opts.onRenameNode(b.dataset.node));
  });
}

// 符号公式（单独区块，字号更大）
export function renderFormulas(el, results) {
  if (!el) return;
  if (!results || !results.ok) {
    el.innerHTML = '<p class="muted">—</p>';
    return;
  }
  const rows = [];
  for (const nid of results.node_order) {
    if (nid === '0') continue;
    const n = results.nodes[nid];
    if (!n.voltage_latex) continue;
    rows.push(`<div class="frow"><span class="tag">V(${nid}) =</span><span class="tex" data-tex="${esc(n.voltage_latex)}"></span></div>`);
  }
  for (const b of results.branches) {
    if (!b.current_latex) continue;
    rows.push(`<div class="frow"><span class="tag">I(${b.component}) =</span><span class="tex" data-tex="${esc(b.current_latex)}"></span></div>`);
  }
  el.innerHTML = rows.length ? rows.join('') : '<p class="muted">（无符号式）</p>';
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

function renderDiagnostics(results) {
  if (!results || !results.diagnostics) return '';
  return results.diagnostics
    .map((d) => `<div class="diag ${d.level}">${esc(d.message)}</div>`)
    .join('');
}

function renderTex(scope) {
  if (typeof window === 'undefined' || !window.katex) return;
  scope.querySelectorAll('.tex').forEach((elm) => {
    const tex = elm.getAttribute('data-tex');
    if (!tex) { elm.textContent = '—'; return; }
    try {
      window.katex.render(tex, elm, { throwOnError: false, displayMode: false });
    } catch {
      elm.textContent = tex;
    }
  });
}

export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
