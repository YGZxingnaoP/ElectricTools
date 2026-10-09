// 节点探针面板：电压、相关支路电流、KCL 方程、计算方法
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

  const rows = (detail.branches || []).map((b) => `
    <tr>
      <td>${esc(b.component)}</td>
      <td class="${b.leaving ? 'dir-out' : 'dir-in'}">${b.leaving ? '离开节点 ↘' : '流入节点 ↗'}</td>
      <td class="val">${fmtNum(b.current)} A</td>
    </tr>`).join('');

  const nameTag = detail.label ? `（${esc(detail.label)}）` : '';
  el.innerHTML = `
    <div class="head">节点 <span class="node-id">${esc(detail.node)}</span>${nameTag}${detail.is_ground ? '（参考地）' : ''}</div>
    ${detail.is_ground
      ? '<p class="muted">参考地：电位定义为 0 V。</p>'
      : `<div><span class="bigval">${fmtNum(detail.voltage)} V</span></div>`}
    ${detail.voltage_latex ? `
      <div class="sect"><div class="lab">符号式</div>
        <span class="tex" data-tex="${esc('V_{' + detail.node + '} = ' + detail.voltage_latex)}"></span>
      </div>` : ''}
    ${rows ? `
      <div class="sect"><div class="lab">相关支路电流（参考方向 p0→p1）</div>
        <table><tr><th>支路</th><th>参考方向</th><th>电流</th></tr>${rows}</table>
      </div>` : ''}
    ${detail.kcl_latex ? `
      <div class="sect"><div class="lab">KCL 方程</div>
        <span class="tex" data-tex="${esc(detail.kcl_latex)}"></span>
      </div>` : ''}
    ${detail.method_latex ? `
      <div class="sect"><div class="lab">计算方法</div>
        <span class="tex" data-tex="${esc(detail.method_latex)}"></span>
        <div class="method">${esc(detail.method || '')}</div>
      </div>` : ''}
  `;
  renderTex(el);
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
