// Canvas 渲染（含摄像机变换：缩放/平移、悬停高亮、自适应网格）
import { pinPositions, GRID, noteBox, COMPONENTS } from './geometry.js';
import { drawExtra } from './symbols.js';
import { fmtNum, fmtEng } from './numfmt.js';

const COL = {
  grid: '#232a37',
  gridMajor: '#2e3849',
  wire: '#7fd1b9',
  wireHover: '#a9f0dd',
  wireSel: '#ffd166',
  comp: '#dfe7f5',
  compHover: '#ffffff',
  compSel: '#ffd166',
  junction: '#7fd1b9',
  nodeLabel: '#9fd0ff',
  current: '#ff9f43',
  muted: '#8b97ad'
};

/**
 * @param scene {{ state, view:{w,h,dpr}, cam:{x,y,scale}, results, anim, overlay, hover }}
 */
export function draw(ctx, scene) {
  const { state, view, cam, results, anim, overlay, hover } = scene;

  ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
  ctx.clearRect(0, 0, view.w, view.h);

  ctx.save();
  ctx.translate(cam.x, cam.y);
  ctx.scale(cam.scale, cam.scale);

  drawGrid(ctx, view, cam);

  // 导线（统一颜色：不再按节点着色，图上不显示任何节点信息）
  for (const wire of state.wires) {
    const sel = state.selection?.kind === 'wire' && state.selection.id === wire.id;
    const hov = hover?.kind === 'wire' && hover.id === wire.id;
    ctx.strokeStyle = sel ? COL.wireSel : hov ? COL.wireHover : COL.wire;
    ctx.lineWidth = (sel || hov ? 3.5 : 2.5) / cam.scale;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    wire.vertices.forEach((v, i) => (i ? ctx.lineTo(v.x, v.y) : ctx.moveTo(v.x, v.y)));
    ctx.stroke();
  }

  // 导线拐点：**不是电气节点**，平时不画。
  // 只在「画导线」时用空心圈提示「这里可以接」。
  if (state.tool === 'wire') {
    ctx.strokeStyle = '#6fb6e8';
    ctx.lineWidth = 1.2 / cam.scale;
    for (const wire of state.wires) {
      for (let i = 1; i < wire.vertices.length - 1; i++) {
        const v = wire.vertices[i];
        ctx.beginPath();
        ctx.arc(v.x, v.y, 3.2 / cam.scale, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  // junction（真正的多路交点）
  for (const j of state.junctions) {
    const sel = state.selection?.kind === 'junction' && state.selection.id === j.id;
    ctx.fillStyle = sel ? COL.wireSel : COL.junction;
    ctx.beginPath();
    ctx.arc(j.x, j.y, 4 / cam.scale, 0, Math.PI * 2);   // 屏幕上恒定大小
    ctx.fill();
  }

  // 元件
  for (const c of state.components) {
    const sel = state.selection?.kind === 'component' && state.selection.id === c.id;
    const hov = hover?.kind === 'component' && hover.id === c.id;
    drawComponent(ctx, c, sel, hov, cam.scale);
  }

  // 「已知量」标注（画在图上的条件）
  for (const n of state.notes || []) {
    const sel = state.selection?.kind === 'note' && state.selection.id === n.id;
    drawNote(ctx, state, n, sel, cam.scale);
  }

  // 结果叠加
  if (results && results.ok) drawResults(ctx, state, results, anim, cam.scale, scene.ui);

  // 草稿（正在画的导线）与吸附高亮
  drawOverlay(ctx, overlay, cam.scale);

  ctx.restore();
}

// 「已知量」标注：一个带引线的标签，锚在节点/支路上
function drawNote(ctx, state, note, sel, scale) {
  const b = noteBox(state, note, scale);
  if (!b) return;
  const txt = b.text;                       // 与 noteBox 用同一份文字，宽度才对得上

  // 引线 + 锚点
  ctx.strokeStyle = '#f0c674';
  ctx.lineWidth = 1.2 / scale;
  ctx.beginPath();
  ctx.moveTo(b.pos.x, b.pos.y);
  ctx.lineTo(b.x + 6 / scale, b.y + b.h);
  ctx.stroke();
  ctx.fillStyle = '#f0c674';
  ctx.beginPath();
  ctx.arc(b.pos.x, b.pos.y, 3.2, 0, Math.PI * 2);
  ctx.fill();

  // 标签底 + 边框
  ctx.fillStyle = sel ? 'rgba(240,198,116,.30)' : 'rgba(240,198,116,.14)';
  roundRect(ctx, b.x, b.y, b.w, b.h, 4 / scale);
  ctx.fill();
  ctx.strokeStyle = '#f0c674';
  ctx.lineWidth = (sel ? 2 : 1) / scale;
  roundRect(ctx, b.x, b.y, b.w, b.h, 4 / scale);
  ctx.stroke();

  ctx.fillStyle = '#f7dfa8';
  ctx.font = `${11 / scale}px "Segoe UI", "Microsoft YaHei"`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(txt, b.x + b.w / 2, b.y + b.h / 2);
}

function drawGrid(ctx, view, cam) {  const s = cam.scale;
  const left = -cam.x / s, top = -cam.y / s;
  const right = (view.w - cam.x) / s, bottom = (view.h - cam.y) / s;

  let minor = GRID;
  while (minor * s < 8) minor *= 5;
  const major = minor * 5;

  ctx.lineWidth = 1 / s;
  const line = (x1, y1, x2, y2, color) => {
    ctx.strokeStyle = color;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  };
  const startX = Math.floor(left / minor) * minor;
  for (let x = startX; x <= right; x += minor) {
    line(x, top, x, bottom, Math.abs(x % major) < 1e-6 ? COL.gridMajor : COL.grid);
  }
  const startY = Math.floor(top / minor) * minor;
  for (let y = startY; y <= bottom; y += minor) {
    line(left, y, right, y, Math.abs(y % major) < 1e-6 ? COL.gridMajor : COL.grid);
  }
}

function drawComponent(ctx, c, sel, hov, scale) {
  const pts = pinPositions(c);
  const base = sel ? COL.compSel : hov ? COL.compHover : COL.comp;
  ctx.strokeStyle = base;
  ctx.fillStyle = base;
  ctx.lineWidth = (sel || hov ? 3 : 2.5) / scale;
  ctx.lineCap = 'round';

  if (c.type === 'resistor') drawResistor(ctx, pts, scale);
  else if (c.type === 'vsource') drawSource(ctx, pts, c, false, scale);
  else if (c.type === 'isource') drawSource(ctx, pts, c, true, scale);
  else if (c.type === 'ground') drawGround(ctx, pts, scale);
  else drawExtra(ctx, c, pts, scale);      // 电容/电感/受控源/变压器/二极管/三极管/运放/开关/三相

  // 引脚端点（屏幕上恒定大小，不随缩放变粗变细）
  ctx.fillStyle = '#6f7c90';
  for (const p of pts) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3 / scale, 0, Math.PI * 2);
    ctx.fill();
  }
  // 标签：各元件可自定义偏移（大符号默认位置会压在图形上）
  const def = COMPONENTS[c.type] || {};
  const lo = def.labelOffset || [22, -22];
  label(ctx, c, c.x + lo[0], c.y + lo[1], scale);
}

function drawResistor(ctx, pts, scale) {
  const [a, b] = pts;
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const nx = -uy, ny = ux;
  const halfW = Math.min(24, len * 0.38);
  const halfH = 9;
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;

  // 引线
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(mx - ux * halfW, my - uy * halfW);
  ctx.moveTo(b.x, b.y);
  ctx.lineTo(mx + ux * halfW, my + uy * halfW);
  ctx.stroke();

  // 长方形（GB/T / IEC 标准电阻符号）
  const c0 = { x: mx - ux * halfW + nx * halfH, y: my - uy * halfW + ny * halfH };
  const c1 = { x: mx + ux * halfW + nx * halfH, y: my + uy * halfW + ny * halfH };
  const c2 = { x: mx + ux * halfW - nx * halfH, y: my + uy * halfW - ny * halfH };
  const c3 = { x: mx - ux * halfW - nx * halfH, y: my - uy * halfW - ny * halfH };
  ctx.beginPath();
  ctx.moveTo(c0.x, c0.y);
  ctx.lineTo(c1.x, c1.y);
  ctx.lineTo(c2.x, c2.y);
  ctx.lineTo(c3.x, c3.y);
  ctx.closePath();
  ctx.stroke();
}

function drawSource(ctx, pts, c, isCurrent, scale) {
  const [a, b] = pts;
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const r = 14;
  // 轴向单位向量：a(p0)=正端，b(p1)=负端（支持任意旋转）
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const nx = -uy, ny = ux;               // 垂直于轴向

  // 引线：端子 → 圆环边缘
  ctx.beginPath();
  ctx.moveTo(a.x, a.y); ctx.lineTo(mid.x - ux * r, mid.y - uy * r);
  ctx.moveTo(b.x, b.y); ctx.lineTo(mid.x + ux * r, mid.y + uy * r);
  ctx.stroke();
  ctx.beginPath(); ctx.arc(mid.x, mid.y, r, 0, Math.PI * 2); ctx.stroke();

  ctx.lineWidth = 2 / scale;
  if (!isCurrent) {
    // 标准直流电压源符号：圆内两条平行短杠（恢复原样式）
    const barHalf = 5, gap = 4;
    for (const s of [-1, 1]) {
      const cx = mid.x + ux * gap * s, cy = mid.y + uy * gap * s;
      ctx.beginPath();
      ctx.moveTo(cx + nx * barHalf, cy + ny * barHalf);
      ctx.lineTo(cx - nx * barHalf, cy - ny * barHalf);
      ctx.stroke();
    }
    // 正/负极标注画在圆外（p0 正极 +，p1 负极 −），靠近各自端子
    const rr = r + 7;   // 沿轴向到圆心的距离（在圆环外、端子内）
    const po = 9;       // 垂直偏移，避免压住引线
    const gs = 5;       // 符号半长
    drawPlusGlyph(ctx, mid.x - ux * rr + nx * po, mid.y - uy * rr + ny * po, gs);
    drawMinusGlyph(ctx, mid.x + ux * rr + nx * po, mid.y + uy * rr + ny * po, gs);
  } else {
    // 独立电流源：圆内箭头表示参考方向（由 p1 指向 p0）
    const s = 7;
    const tipX = mid.x - ux * s, tipY = mid.y - uy * s;
    const tailX = mid.x + ux * s, tailY = mid.y + uy * s;
    ctx.beginPath();
    ctx.moveTo(tailX, tailY); ctx.lineTo(tipX, tipY);
    ctx.stroke();
    const hl = 4, hw = 4;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX + ux * hl + nx * hw, tipY + uy * hl + ny * hw);
    ctx.lineTo(tipX + ux * hl - nx * hw, tipY + uy * hl - ny * hw);
    ctx.closePath();
    ctx.stroke();
  }
}

// 正号（十字），以 (x,y) 为中心、半长为 s
function drawPlusGlyph(ctx, x, y, s) {
  ctx.beginPath();
  ctx.moveTo(x - s, y); ctx.lineTo(x + s, y);
  ctx.moveTo(x, y - s); ctx.lineTo(x, y + s);
  ctx.stroke();
}

// 负号（一横），以 (x,y) 为中心、半长为 s
function drawMinusGlyph(ctx, x, y, s) {
  ctx.beginPath();
  ctx.moveTo(x - s, y); ctx.lineTo(x + s, y);
  ctx.stroke();
}

function drawGround(ctx, pts, scale) {
  const p = pts[0];
  ctx.beginPath();
  ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y + 12);
  ctx.moveTo(p.x - 11, p.y + 12); ctx.lineTo(p.x + 11, p.y + 12);
  ctx.moveTo(p.x - 7, p.y + 17); ctx.lineTo(p.x + 7, p.y + 17);
  ctx.moveTo(p.x - 3, p.y + 22); ctx.lineTo(p.x + 3, p.y + 22);
  ctx.stroke();
}

function label(ctx, c, x, y, scale) {
  ctx.fillStyle = '#aab6cc';
  ctx.font = `${12 / scale}px "Segoe UI", "Microsoft YaHei"`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(`${c.id}${paramText(c)}`, x, y);
}

/** 元件标签上的文字：数值 + 该元件特有的参数（交流源相位、受控源增益、变压器变比、三极管 β…） */
export function paramText(c) {
  const p = c.params || {};
  if (c.type === 'opamp') return '';
  if (c.type === 'bjt') return ` β=${p.beta ?? 100}`;
  if (c.type === 'transformer') return ` n=${p.ratio ?? 2}`;
  if (c.type === 'vcvs') return ` μ=${p.gain ?? 1}`;
  if (c.type === 'vccs') return ` gm=${p.gain ?? 0.001}`;
  if (c.type === 'ccvs') return ` r=${p.gain ?? 1}`;
  if (c.type === 'cccs') return ` β=${p.gain ?? 1}`;
  const v = c.value !== null && c.value !== undefined ? c.value : '';
  if (p.kind === 'ac') return ` ${v === '' ? '' : v}∠${p.phase ?? 0}°`;
  if (p.kind === 'step') return ` ${v}（阶跃）`;
  return c.symbol ? ` ${c.symbol}` : (v === '' ? '' : ` ${fmtEng(v, c.unit || '')}`);
}

function drawResults(ctx, state, results, anim, scale, ui) {
  // 图上不再画任何节点信息（节点名 / 电压 / 引线 / 着色）—— 节点数据只在右侧面板看。
  // 画布上只保留「支路电流箭头」。
  if (ui && ui.show_current_arrows === false) return;

  for (const br of (results.branches || [])) {
    if (br.current === null || br.current === undefined) continue;
    const comp = state.components.find((c) => c.id === br.component);
    if (!comp) continue;
    const pts = pinPositions(comp);
    if (pts.length < 2) continue;
    drawCurrentArrow(ctx, pts[0], pts[1], br, anim, scale, ui);
  }
}

function drawCurrentArrow(ctx, a, b, br, anim, scale, ui) {
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  // ★ 箭头画的是「实际电流方向」：p0→p1 为正，为负就整根反过来。
  //   以前无论正负都画成 p0→p1，负电流时箭头方向和真实电流相反，
  //   看起来就和电流源符号里的箭头打架（这就是"箭头方向混乱"的来源）。
  const neg = br.current < 0;
  const ux = (neg ? -dx : dx) / len;
  const uy = (neg ? -dy : dy) / len;
  const nx = -uy, ny = ux;
  const off = 24;
  const cx = mid.x + nx * off, cy = mid.y + ny * off;
  const mag = Math.abs(br.current);
  const color = COL.current;

  const size = 10;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2 / scale;
  ctx.beginPath();
  ctx.moveTo(cx - ux * size, cy - uy * size);
  ctx.lineTo(cx + ux * size, cy + uy * size);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(cx + ux * size, cy + uy * size);
  ctx.lineTo(cx + ux * size - ux * 6 + nx * 4, cy + uy * size - uy * 6 + ny * 4);
  ctx.lineTo(cx + ux * size - ux * 6 - nx * 4, cy + uy * size - uy * 6 - ny * 4);
  ctx.closePath();
  ctx.fill();

  // 流动小点：半径小、速度慢，仅随电流大小轻微加速（上限受限，避免大电流时飞快）
  if (!ui || ui.current_animation !== false) {
    const speed = 0.5 + 0.5 * Math.min(1, mag / 0.05);
    const flow = (anim * speed) % 1;
    ctx.beginPath();
    ctx.arc(cx - ux * size + ux * 2 * size * flow, cy - uy * size + uy * 2 * size * flow, 1.5, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.font = `${11 / scale}px "Segoe UI"`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(`I=${fmtEng(mag, 'A')}`, cx + nx * 14, cy + ny * 14);
}

function drawOverlay(ctx, overlay, scale) {
  if (!overlay) return;
  // 吸附点高亮 + 「会不会接上」的明确提示
  const hs = overlay.hoverSnap;
  if (hs && hs.target && hs.target.kind !== 'grid') {
    const onWire = ['wire-mid', 'wire', 'wire-corner'].includes(hs.target.kind);
    const col = onWire ? '#ffb454' : '#4f9cf9';
    ctx.strokeStyle = col;
    ctx.lineWidth = 2 / scale;
    ctx.beginPath();
    ctx.arc(hs.point.x, hs.point.y, 7, 0, Math.PI * 2);
    ctx.stroke();
    if (onWire) {                       // 三通：实心点，强调"这一下会连上"
      ctx.fillStyle = col;
      ctx.beginPath();
      ctx.arc(hs.point.x, hs.point.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
    const label = onWire ? '⚠ 将连接（三通）' : '✓ 连接端子';
    ctx.font = `bold ${12 / scale}px "Segoe UI", "Microsoft YaHei"`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const w = ctx.measureText(label).width + 10 / scale;
    ctx.fillStyle = 'rgba(20,26,38,.9)';
    roundRect(ctx, hs.point.x + 10 / scale, hs.point.y - 26 / scale, w, 17 / scale, 4 / scale);
    ctx.fill();
    ctx.fillStyle = col;
    ctx.fillText(label, hs.point.x + 15 / scale, hs.point.y - 17.5 / scale);
  }
  if (overlay.noConnect) {              // 按住 Shift：明确告诉用户"这里断开"
    const p = hs ? hs.point : null;
    const label = 'Shift：穿过不连';
    ctx.font = `bold ${12 / scale}px "Segoe UI", "Microsoft YaHei"`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const w = ctx.measureText(label).width + 10 / scale;
    const bx = (p ? p.x : 0) + 10 / scale;
    const by = (p ? p.y : 0) + 10 / scale;
    ctx.fillStyle = 'rgba(20,26,38,.9)';
    roundRect(ctx, bx, by, w, 17 / scale, 4 / scale);
    ctx.fill();
    ctx.fillStyle = '#6ee7a8';
    ctx.fillText(label, bx + 5 / scale, by + 9 / scale);
  }
  // 导线草稿 + 正交预览（虚线）
  if (overlay.preview && overlay.preview.length >= 2) {
    ctx.strokeStyle = '#ffd166';
    ctx.lineWidth = 2.5 / scale;
    ctx.setLineDash([6 / scale, 4 / scale]);
    ctx.beginPath();
    overlay.preview.forEach((v, i) => (i ? ctx.lineTo(v.x, v.y) : ctx.moveTo(v.x, v.y)));
    ctx.stroke();
    ctx.setLineDash([]);
    // 已确定的拐点
    if (overlay.draft) {
      for (const v of overlay.draft.vertices) {
        ctx.fillStyle = '#ffd166';
        ctx.beginPath(); ctx.arc(v.x, v.y, 3 / scale, 0, Math.PI * 2); ctx.fill();
      }
    }
  }
  // 放置预览
  if (overlay.ghost) {
    ctx.globalAlpha = 0.45;
    drawComponent(ctx, overlay.ghost, false, true, scale);
    ctx.globalAlpha = 1;
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
