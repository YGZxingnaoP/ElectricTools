// 新增元件的画布符号：电容/电感/变压器/二极管/稳压管/三极管/运放/受控源/开关/三相源
// 统一约定：pts = 引脚屏幕坐标（p0 是首端）。所有尺寸按屏幕像素 / scale。

function axis(pts) {
  const [a, b] = pts;
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { a, b, ux: dx / len, uy: dy / len, nx: -dy / len, ny: dx / len, len,
           mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
}
const P = (x, y, ux, uy, nx, ny) => ({ x: x + ux * 0 + nx * 0, y: y });

/** 沿轴取点：t 沿轴（相对中点，像素），s 沿法线 */
function pt(mx, my, ux, uy, nx, ny, t, s) {
  return { x: mx + ux * t + nx * s, y: my + uy * t + ny * s };
}

function line(ctx, p, q) { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke(); }

function drawCapacitor(ctx, pts, scale) {
  const g = axis(pts);
  const gap = 7 / scale, plate = 22 / scale;
  const p1 = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -gap, 0);
  const p2 = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, gap, 0);
  line(ctx, pt(p1.x, p1.y, g.ux, g.uy, g.nx, g.ny, 0, -plate), pt(p1.x, p1.y, g.ux, g.uy, g.nx, g.ny, 0, plate));
  line(ctx, pt(p2.x, p2.y, g.ux, g.uy, g.nx, g.ny, 0, -plate), pt(p2.x, p2.y, g.ux, g.uy, g.nx, g.ny, 0, plate));
  // 引线补到引脚
  line(ctx, g.a, p1); line(ctx, p2, g.b);
}

function drawInductor(ctx, pts, scale) {
  const g = axis(pts);
  const n = 4, r = 8 / scale, span = 44 / scale;
  line(ctx, g.a, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -span / 2, 0));
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const t0 = -span / 2 + (span / n) * i;
    const c = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, t0 + span / (2 * n), 0);
    ctx.save();
    ctx.translate(c.x, c.y);
    ctx.rotate(Math.atan2(g.uy, g.ux));
    ctx.arc(0, 0, r, Math.PI, 0, false);
    ctx.restore();
    ctx.stroke();
    ctx.beginPath();
  }
  line(ctx, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, span / 2, 0), g.b);
}

function drawDiode(ctx, pts, scale, zener) {
  const g = axis(pts);
  const h = 11 / scale, w = 14 / scale;
  const tip = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, 0, 0);
  const back = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -w, 0);
  const barA = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, 0, -h);
  const barB = pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, 0, h);
  ctx.beginPath();
  ctx.moveTo(back.x, back.y);
  ctx.lineTo(pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -w, -h).x, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -w, -h).y);
  ctx.lineTo(pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -w, h).x, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -w, h).y);
  ctx.closePath();
  ctx.fill();
  line(ctx, barA, barB);
  if (zener) {                       // 稳压管：两端折角
    line(ctx, barA, pt(barA.x, barA.y, g.ux, g.uy, g.nx, g.ny, -5 / scale, -5 / scale));
    line(ctx, barB, pt(barB.x, barB.y, g.ux, g.uy, g.nx, g.ny, 5 / scale, 5 / scale));
  }
  line(ctx, g.a, back); line(ctx, tip, g.b);
}

function drawBjt(ctx, pts, scale) {
  const b = pts.find((p) => p.name === 'b') || pts[0];
  const c = pts.find((p) => p.name === 'c') || pts[1];
  const e = pts.find((p) => p.name === 'e') || pts[2];
  const R = 22 / scale;
  const cx = (b.x + c.x + e.x) / 3, cy = (b.y + c.y + e.y) / 3;
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
  const barX = cx - 6 / scale;
  line(ctx, { x: barX, y: cy - 12 / scale }, { x: barX, y: cy + 12 / scale });
  line(ctx, b, { x: barX, y: cy });
  const cIn = { x: barX, y: cy - 9 / scale };
  const eIn = { x: barX, y: cy + 9 / scale };
  line(ctx, c, cIn); line(ctx, e, eIn);
  // 发射极箭头
  const dx = eIn.x - e.x, dy = eIn.y - e.y, L = Math.hypot(dx, dy) || 1;
  const ux = dx / L, uy = dy / L;
  const tip = { x: eIn.x - ux * 2, y: eIn.y - uy * 2 };
  ctx.beginPath();
  ctx.moveTo(eIn.x - ux * 10, eIn.y - uy * 10);
  ctx.lineTo(eIn.x - ux * 10 + uy * 5, eIn.y - uy * 10 - ux * 5);
  ctx.lineTo(eIn.x - ux * 10 - uy * 5, eIn.y - uy * 10 + ux * 5);
  ctx.closePath(); ctx.fill();
}

function drawOpamp(ctx, pts, scale) {
  const inp = pts.find((p) => p.name === 'inp') || pts[0];
  const inn = pts.find((p) => p.name === 'inn') || pts[1];
  const out = pts.find((p) => p.name === 'out') || pts[2];
  const w = 34 / scale, h = 26 / scale;
  const x0 = inp.x - 2, cy = (inp.y + inn.y) / 2;
  ctx.beginPath();
  ctx.moveTo(x0, cy - h);
  ctx.lineTo(x0, cy + h);
  ctx.lineTo(x0 + w, cy);
  ctx.closePath();
  ctx.stroke();
  line(ctx, inp, { x: x0, y: inp.y }); line(ctx, inn, { x: x0, y: inn.y }); line(ctx, out, { x: x0 + w, y: cy });
  ctx.save(); ctx.fillStyle = ctx.strokeStyle;
  ctx.font = `${13 / scale}px "Segoe UI"`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('+', x0 + 7 / scale, inp.y);
  ctx.fillText('−', x0 + 7 / scale, inn.y);
  ctx.restore();
}

function drawControlled(ctx, pts, scale, label) {
  const [a, b] = pts.filter((p) => p.name === 'p0' || p.name === 'p1');
  const g = axis([a, b]);
  const r = 13 / scale;
  ctx.beginPath();
  ctx.moveTo(g.mx, g.my - r); ctx.lineTo(g.mx + r, g.my);
  ctx.lineTo(g.mx, g.my + r); ctx.lineTo(g.mx - r, g.my);
  ctx.closePath(); ctx.stroke();
  line(ctx, g.a, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -r / g.len * g.len, 0));
  // 控制端子（有 c0/c1 时画虚线连接）
  const c0 = pts.find((p) => p.name === 'c0'), c1 = pts.find((p) => p.name === 'c1');
  if (c0 && c1) {
    ctx.save(); ctx.setLineDash([4 / scale, 3 / scale]);
    line(ctx, { x: g.mx, y: g.my - (c0.y > g.my ? -r : r) }, { x: g.mx, y: g.my - r });
    line(ctx, c0, { x: g.mx - 18 / scale, y: c0.y });
    line(ctx, c1, { x: g.mx - 18 / scale, y: c1.y });
    ctx.restore();
  }
  ctx.save();
  ctx.fillStyle = ctx.strokeStyle;
  ctx.font = `bold ${12 / scale}px "Segoe UI"`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(label, g.mx + 1 / scale, g.my + 1 / scale);
  ctx.restore();
}

function drawTransformer(ctx, pts, scale) {
  const p = (n) => pts.find((q) => q.name === n);
  const a = p('p0'), b = p('p1'), c = p('p2'), d = p('p3');
  if (!a || !c) return;
  const coil = (top, bot, xoff) => {
    const R = 8 / scale, n = 4;
    const y0 = Math.min(top.y, bot.y) + 10, y1 = Math.max(top.y, bot.y) - 10;
    const h = (y1 - y0) / n;
    line(ctx, top, { x: top.x, y: y0 });
    for (let i = 0; i < n; i++) {
      ctx.beginPath();
      ctx.arc(top.x, y0 + h * (i + 0.5), R, -Math.PI / 2, Math.PI / 2, true);
      ctx.stroke();
    }
    line(ctx, { x: top.x, y: y1 }, bot);
  };
  coil(a, b); coil(c, d);
  const cx = (a.x + c.x) / 2;
  line(ctx, { x: cx - 3 / scale, y: Math.min(a.y, d.y) + 6 }, { x: cx - 3 / scale, y: Math.max(b.y, c.y) - 6 });
  line(ctx, { x: cx + 3 / scale, y: Math.min(a.y, d.y) + 6 }, { x: cx + 3 / scale, y: Math.max(b.y, c.y) - 6 });
}

function drawSwitch(ctx, pts, scale) {
  const [a, b] = pts;
  const g = axis(pts);
  const l = 12 / scale;
  line(ctx, g.a, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -l * 0.9, 0));
  line(ctx, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, -l * 0.9, 0),
       pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, l * 0.5, -l * 0.9));
  ctx.beginPath();
  ctx.arc(pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, l * 0.9, 0).x,
          pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, l * 0.9, 0).y, 3 / scale, 0, Math.PI * 2);
  ctx.fill();
  line(ctx, pt(g.mx, g.my, g.ux, g.uy, g.nx, g.ny, l * 0.9, 0), g.b);
}

function drawThreePhase(ctx, pts, scale) {
  const ys = pts.map((p) => p.y);
  const x = pts[0].x;
  const top = Math.min(...ys) - 6 / scale, bot = Math.max(...ys) + 6 / scale;
  const w = 34 / scale;
  ctx.strokeRect(x - w / 2, top, w, bot - top);
  ctx.save();
  ctx.fillStyle = ctx.strokeStyle;
  ctx.font = `bold ${12 / scale}px "Segoe UI"`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('3~', x, (top + bot) / 2);
  ctx.restore();
  pts.forEach((p, i) => {
    line(ctx, { x, y: top + ((bot - top) / 4) * (i + 0.5) }, p);
  });
}

/** 返回 true 表示这个类型由本模块画（renderer 不再画默认符号） */
export function drawExtra(ctx, c, pts, scale) {
  const t = c.type;
  if (t === 'capacitor') { drawCapacitor(ctx, pts, scale); return true; }
  if (t === 'inductor') { drawInductor(ctx, pts, scale); return true; }
  if (t === 'diode') { drawDiode(ctx, pts, scale, false); return true; }
  if (t === 'zener') { drawDiode(ctx, pts, scale, true); return true; }
  if (t === 'bjt') { drawBjt(ctx, pts, scale); return true; }
  if (t === 'opamp') { drawOpamp(ctx, pts, scale); return true; }
  if (t === 'vcvs') { drawControlled(ctx, pts, scale, 'μ'); return true; }
  if (t === 'vccs') { drawControlled(ctx, pts, scale, 'gm'); return true; }
  if (t === 'ccvs') { drawControlled(ctx, pts, scale, 'r'); return true; }
  if (t === 'cccs') { drawControlled(ctx, pts, scale, 'β'); return true; }
  if (t === 'transformer') { drawTransformer(ctx, pts, scale); return true; }
  if (t === 'switch') { drawSwitch(ctx, pts, scale); return true; }
  if (t === 'vsource3') { drawThreePhase(ctx, pts, scale); return true; }
  return false;
}

/** 交流源：在圆圈里画正弦（renderer 里的 drawSource 调用） */
export function drawAcMark(ctx, cx, cy, r, scale) {
  ctx.beginPath();
  const n = 16;
  for (let i = 0; i <= n; i++) {
    const t = -r * 0.8 + (r * 1.6 * i) / n;
    const y = cy - Math.sin((i / n) * Math.PI * 2) * r * 0.55;
    if (i === 0) ctx.moveTo(cx + t, y); else ctx.lineTo(cx + t, y);
  }
  ctx.stroke();
}
