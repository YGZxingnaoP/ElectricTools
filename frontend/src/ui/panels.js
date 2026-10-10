// 右栏新增的三个折叠栏内容：相量图 / 曲线（波形·扫频）/ 解法步骤
import { fmtNum } from '../core/numfmt.js';

const COLORS = ['#4f9cf9', '#f9a04f', '#7ee787', '#f97e9e', '#c58cf9', '#f9d84f'];

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** 相量图：把每个交流相量画成从原点出发的箭头，长度∝有效值 */
export function renderPhasor(el, results) {
  if (!el) return;
  if (!results || results.domain !== 'ac') {
    el.innerHTML = '<p class="muted">只有「正弦交流（相量）」分析才画相量图。</p>';
    return;
  }
  const items = [];
  for (const nid of results.node_order || []) {
    const nd = results.nodes[nid];
    if (nd && nd.phasor && nd.phasor.rms > 1e-12) {
      items.push({ key: `V(${nid})`, rms: nd.phasor.rms, phase: nd.phasor.phase });
    }
  }
  for (const b of results.branches || []) {
    if (b.phasor && b.phasor.rms > 1e-12) {
      items.push({ key: `I(${b.component})`, rms: b.phasor.rms, phase: b.phasor.phase, isI: true });
    }
  }
  if (!items.length) {
    el.innerHTML = '<p class="muted">没有可画的有效值（全是 0）。</p>';
    return;
  }
  const cap = items.slice(0, 6);
  const maxV = Math.max(...cap.filter((x) => !x.isI).map((x) => x.rms), 1e-12);
  const maxI = Math.max(...cap.filter((x) => x.isI).map((x) => x.rms), 1e-12);
  const W = 340, H = 190, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 26;
  const arrows = cap.map((it, i) => {
    // 电压电流量纲不同 → 各自归一化（图例里标明基准）
    const ref = it.isI ? maxI : maxV;
    const len = (it.rms / ref) * R * 0.9;
    const a = (-it.phase * Math.PI) / 180;      // 屏幕 y 轴向下 → 取负
    const x = cx + len * Math.cos(a), y = cy + len * Math.sin(a);
    const col = COLORS[i % COLORS.length];
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${col}" stroke-width="2" />
      <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${col}" />
      <text x="${(x + 5).toFixed(1)}" y="${(y - 4).toFixed(1)}" fill="${col}" font-size="10">${esc(it.key)}</text>`;
  }).join('');
  const legend = cap.map((it, i) =>
    `<div><i style="background:${COLORS[i % COLORS.length]}"></i>${esc(it.key)} = ${fmtNum(it.rms)}` +
    `${it.isI ? ' A' : ' V'} ∠${fmtNum(it.phase)}°</div>`).join('');
  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}">
      <line x1="${cx - R - 8}" y1="${cy}" x2="${cx + R + 8}" y2="${cy}" stroke="#3a4453" />
      <line x1="${cx}" y1="${cy - R - 8}" x2="${cx}" y2="${cy + R + 8}" stroke="#3a4453" />
      <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="#243044" stroke-dasharray="3 3" />
      <text x="${cx + R - 16}" y="${cy - 4}" fill="#6f7c90" font-size="9">0°</text>
      <text x="${cx + 5}" y="${cy - R + 4}" fill="#6f7c90" font-size="9">90°</text>
      ${arrows}
    </svg>
    <div class="legend">${legend}
      <div style="margin-top:3px">电压基准 ${fmtNum(maxV)} V，电流基准 ${fmtNum(maxI)} A（各自归一化画箭头）</div>
    </div>`;
}

/** 曲线栏：暂态波形 / 扫频结果 */
export function renderCurves(el, results, sweep) {
  if (!el) return;
  const parts = [];
  const w = results && results.waveform;
  if (w && w.t && w.t.length > 1) {
    parts.push(waveSvg(w, results));
  }
  if (sweep && sweep.freqs && sweep.freqs.length) {
    parts.push(sweepSvg(sweep));
  }
  el.innerHTML = parts.length ? parts.join('') :
    '<p class="muted">暂态分析出波形；交流分析点下面「扫频」看幅频/相频。</p>';
}

function waveSvg(w, results) {
  const t = w.t;
  const reactive = new Set((results.branches || [])
    .filter((b) => b.type === 'capacitor' || b.type === 'inductor').map((b) => b.component));
  let keys = Object.keys(w).filter((k) => k !== 't' && reactive.has(String(k).split(':')[1]));
  if (!keys.length) keys = Object.keys(w).filter((k) => k.startsWith('U:'));
  if (!keys.length) keys = Object.keys(w).filter((k) => k !== 't');
  keys = keys.slice(0, 4);
  if (!keys.length) return '';
  const all = keys.flatMap((k) => w[k] || []);
  let lo = Math.min(...all), hi = Math.max(...all);
  if (!(hi > lo)) hi = lo + 1;
  const pd = (hi - lo) * 0.08; lo -= pd; hi += pd;
  const W = 330, H = 170, L = 40, B = 22;
  const X = (i) => L + (W - L - 8) * (i / (t.length - 1));
  const Y = (v) => (H - B) - (H - B - 10) * ((v - lo) / (hi - lo));
  const paths = keys.map((k, i) => {
    const d = (w[k] || []).map((v, j) => `${j ? 'L' : 'M'}${X(j).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
    return `<path d="${d}" fill="none" stroke="${COLORS[i % COLORS.length]}" stroke-width="1.6" />`;
  }).join('');
  const legend = keys.map((k, i) => `<div><i style="background:${COLORS[i % COLORS.length]}"></i>${esc(k)}</div>`).join('');
  return `<div class="wave-box">
    <div class="lab">暂态波形（横轴 t，${t.length} 点）</div>
    <svg viewBox="0 0 ${W} ${H}" class="wave-svg" preserveAspectRatio="none">
      <line x1="${L}" y1="10" x2="${L}" y2="${H - B}" stroke="#3a4453" />
      <line x1="${L}" y1="${H - B}" x2="${W - 8}" y2="${H - B}" stroke="#3a4453" />
      <text x="2" y="16" fill="#8894a8" font-size="10">${esc(fmtNum(hi))}</text>
      <text x="2" y="${H - B}" fill="#8894a8" font-size="10">${esc(fmtNum(lo))}</text>
      <text x="${W - 70}" y="${H - B + 13}" fill="#8894a8" font-size="10">t=${esc(fmtNum(t[t.length - 1]))} s</text>
      ${paths}
    </svg>
    <div class="legend">${legend}</div>
  </div>`;
}

function sweepSvg(sw) {
  const f = sw.freqs;
  const series = Object.keys(sw.series || {}).slice(0, 4);
  if (!series.length) return '';
  const W = 330, H = 170, L = 42, B = 24;
  const lf = (x) => Math.log10(Math.max(x, 1e-9));
  const x0 = lf(f[0]), x1 = lf(f[f.length - 1]);
  const X = (i) => L + (W - L - 8) * ((lf(f[i]) - x0) / (x1 - x0 || 1));
  const allMag = series.flatMap((k) => sw.series[k].mag || []);
  let hi = Math.max(...allMag, 1e-12), lo = Math.min(...allMag.filter((v) => v > 0), hi) || 1e-9;
  if (!(hi > lo)) hi = lo * 10;
  const Y = (v) => (H - B) - (H - B - 10) * ((Math.log10(Math.max(v, 1e-12)) - Math.log10(lo)) /
                                            (Math.log10(hi) - Math.log10(lo) || 1));
  const paths = series.map((k, i) => {
    const d = (sw.series[k].mag || []).map((v, j) => `${j ? 'L' : 'M'}${X(j).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
    return `<path d="${d}" fill="none" stroke="${COLORS[i % COLORS.length]}" stroke-width="1.6" />`;
  }).join('');
  const legend = series.map((k, i) => `<div><i style="background:${COLORS[i % COLORS.length]}"></i>${esc(k)}</div>`).join('');
  return `<div class="wave-box">
    <div class="lab">扫频（幅频，横轴对数频率 ${fmtNum(f[0])}~${fmtNum(f[f.length - 1])} Hz）</div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <line x1="${L}" y1="10" x2="${L}" y2="${H - B}" stroke="#3a4453" />
      <line x1="${L}" y1="${H - B}" x2="${W - 8}" y2="${H - B}" stroke="#3a4453" />
      <text x="2" y="16" fill="#8894a8" font-size="10">${esc(fmtNum(hi))}</text>
      <text x="2" y="${H - B}" fill="#8894a8" font-size="10">${esc(fmtNum(lo))}</text>
      ${paths}
    </svg>
    <div class="legend">${legend}</div>
  </div>`;
}
