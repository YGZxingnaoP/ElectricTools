// 节点探针面板：电压、分步推导（选参考点 → 支路电流 → KCL → 求解）、方法说明
import { fmtNum } from '../core/numfmt.js';

export function renderProbe(el, detail) {
  if (!el) return;
  if (!detail) {
    el.innerHTML = '<p class="muted">用「节点探针」工具点击导线 / 节点，或直接点击节点圆点，查看电压、电流与计算方法。</p>';
    return;
  }
  if (detail.error) {
    el.innerHTML = `<div class="diag error">${esc(detail.error)}</div>`;
    return;
  }

  const nameTag = detail.label ? `（${esc(detail.label)}）` : '';
  const steps = (detail.steps || []).map(renderStep).join('');

  el.innerHTML = `
    <div class="head">节点 <span class="node-id">${esc(detail.node)}</span>${nameTag}${detail.is_ground ? '（参考地）' : ''}</div>
    ${detail.is_ground
      ? '<p class="muted">参考地：电位定义为 0 V。</p>'
      : `<div><span class="bigval">${fmtNum(detail.voltage)} V</span></div>`}
    ${steps
      ? `<div class="sect"><div class="lab">计算步骤</div>${steps}</div>`
      : renderFallback(detail)}
    ${detail.method ? `
      <div class="sect"><div class="lab">方法说明</div>
        <div class="method">${esc(detail.method)}</div>
      </div>` : ''}
  `;
  renderTex(el);
}

// 老版本后端没有 steps 时的兜底显示
function renderFallback(detail) {
  const rows = (detail.branches || []).map((b) => `
    <tr>
      <td>${esc(b.component)}</td>
      <td class="${b.leaving ? 'dir-out' : 'dir-in'}">${b.leaving ? '离开节点 ↘' : '流入节点 ↗'}</td>
      <td class="val">${fmtNum(b.current)} A</td>
    </tr>`).join('');
  return `
    ${rows ? `<div class="sect"><div class="lab">相关支路电流（参考方向 p0→p1）</div>
      <table><tr><th>支路</th><th>参考方向</th><th>电流</th></tr>${rows}</table></div>` : ''}
    ${detail.kcl_latex ? `<div class="sect"><div class="lab">KCL 方程</div>
      <span class="tex" data-tex="${esc(detail.kcl_latex)}"></span></div>` : ''}
  `;
}

// 一步 = 标题 + 说明 + 公式（或表格）
function renderStep(s) {
  const rows = (s.table || []).map((r) => `
    <tr>
      <td class="val">${esc(r.sym)}</td>
      <td>${esc(r.dir)}</td>
      <td class="${r.leaving ? 'dir-out' : 'dir-in'}">${r.leaving ? '离开' : '流入'}</td>
      <td class="tex" data-tex="${esc(r.expr)}"></td>
      <td class="val">${r.value === null || r.value === undefined ? '—' : fmtNum(r.value)}</td>
    </tr>`).join('');
  return `
    <div class="step">
      <div class="step-t">${esc(s.title)}</div>
      <div class="step-x">${esc(s.text || '')}</div>
      ${s.latex ? `<div class="step-eq"><span class="tex" data-tex="${esc(s.latex)}"></span></div>` : ''}
      ${rows ? `<table class="step-tab"><tr><th>电流</th><th>参考方向</th><th>相对本节点</th><th>表达式</th><th>数值(A)</th></tr>${rows}</table>` : ''}
    </div>`;
}

function renderTex(scope) {
  if (typeof window === 'undefined' || !window.katex) return;
  scope.querySelectorAll('.tex').forEach((elm) => {
    const tex = elm.getAttribute('data-tex');
    if (!tex) return;
    try {
      window.katex.render(tex, elm, { throwOnError: false, displayMode: false });
    } catch {
      elm.textContent = tex;
    }
  });
}

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
