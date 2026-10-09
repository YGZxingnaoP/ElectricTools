// Canvas 渲染（含摄像机变换：缩放/平移、悬停高亮、自适应网格）
import { pinPositions, GRID } from './geometry.js';
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

  // 导线
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

  // 导线拐点（拐点即节点，可连接）
  for (const wire of state.wires) {
    for (let i = 1; i < wire.vertices.length - 1; i++) {
      const v = wire.vertices[i];
      ctx.fillStyle = '#6fb6e8';
      ctx.beginPath();
      ctx.arc(v.x, v.y, 2.6, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // junction
  for (const j of state.junctions) {
    const sel = state.selection?.kind === 'junction' && state.selection.id === j.id;
    ctx.fillStyle = sel ? COL.wireSel : COL.junction;
    ctx.beginPath();
    ctx.arc(j.x, j.y, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  // 元件
  for (const c of state.components) {
    const sel = state.selection?.kind === 'component' && state.selection.id === c.id;
    const hov = hover?.kind === 'component' && hover.id === c.id;
    drawComponent(ctx, c, sel, hov, cam.scale);
  }

  // 结果叠加
  if (results && results.ok) drawResults(ctx, state, results, anim, cam.scale, scene.ui, scene.nodeLabels);

  // 草稿（正在画的导线）与吸附高亮
  drawOverlay(ctx, overlay, cam.scale);

  ctx.restore();
}

function drawGrid(ctx, view, cam) {
  const s = cam.scale;
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

  // 引脚端点
  ctx.fillStyle = '#6f7c90';
  for (const p of pts) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3 / Math.min(scale, 1.6), 0, Math.PI * 2);
    ctx.fill();
  }
  label(ctx, c, c.x + 22, c.y - 22, scale);
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
  let val = '';
  if (c.symbol) val = c.symbol;                                  // 未知量占位（如 R、Ux）
  else if (c.value !== null && c.value !== undefined) val = fmtEng(c.value, c.unit || '');
  ctx.fillText(`${c.id} ${val}`.trim(), x, y);
}

function drawResults(ctx, state, results, anim, scale, ui, nodeLabels) {
  const labels = nodeLabels || {};
  const nodePos = nodeAnchors(state, results);
  for (const [nid, info] of Object.entries(results.nodes)) {
    if (nid === '0' || info.voltage === null || info.voltage === undefined) continue;
    const pos = nodePos[nid];
    if (!pos) continue;
    const name = labels[nid] ? `${labels[nid]} (${nid})` : nid;
    const txt = `${name}: ${fmtNum(info.voltage)} V`;
    ctx.font = `bold ${12 / scale}px "Segoe UI", "Microsoft YaHei"`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const wpx = ctx.measureText(txt).width + 12 / scale;
    ctx.fillStyle = 'rgba(20,26,38,.85)';
    roundRect(ctx, pos.x - wpx / 2, pos.y - 10 / scale, wpx, 20 / scale, 5 / scale);
    ctx.fill();
    ctx.fillStyle = COL.nodeLabel;
    ctx.fillText(txt, pos.x, pos.y);
  }

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
  const ux = dx / len, uy = dy / len;
  const nx = -uy, ny = ux;
  const off = 24;
  const cx = mid.x + nx * off, cy = mid.y + ny * off;
  const mag = Math.abs(br.current);
  const color = br.current >= 0 ? COL.current : '#5aa9e6';

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
  ctx.fillText(`I=${fmtEng(br.current, 'A')}`, cx + nx * 14, cy + ny * 14);
}

function drawOverlay(ctx, overlay, scale) {
  if (!overlay) return;
  // 吸附点高亮
  if (overlay.hoverSnap && overlay.hoverSnap.target && overlay.hoverSnap.target.kind !== 'grid') {
    ctx.strokeStyle = '#4f9cf9';
    ctx.lineWidth = 2 / scale;
    ctx.beginPath();
    ctx.arc(overlay.hoverSnap.point.x, overlay.hoverSnap.point.y, 7, 0, Math.PI * 2);
    ctx.stroke();
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

function nodeAnchors(state, results) {
  const map = {};
  const wires = Object.fromEntries(state.wires.map((w) => [w.id, w]));
  const juncs = Object.fromEntries(state.junctions.map((j) => [j.id, j]));
  for (const [nid, info] of Object.entries(results.nodes)) {
    if (nid === '0') continue;
    for (const m of info.members) {
      if (m.startsWith('u:')) {
        const [cid, pname] = m.slice(2).split('/');
        const comp = state.components.find((c) => c.id === cid);
        if (comp) {
          const p = pinPositions(comp).find((q) => q.name === pname);
          if (p) { map[nid] = { x: p.x, y: p.y - 18 }; break; }
        }
      } else if (m.startsWith('j:')) {
        const j = juncs[m.slice(2)];
        if (j) { map[nid] = { x: j.x, y: j.y - 18 }; break; }
      } else if (m.startsWith('w:')) {
        const w = wires[m.slice(2)];
        if (w && w.vertices.length) { map[nid] = { x: w.vertices[0].x, y: w.vertices[0].y - 18 }; break; }
      }
    }
  }
  return map;
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
