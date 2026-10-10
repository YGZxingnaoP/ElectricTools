// 元件几何库、坐标变换、吸附与命中检测

export const GRID = 10;
export const SNAP = 14;

// 元件定义：引脚为局部坐标（含符号朝向：p0=正端/首端，p1=负端/末端）
// ★ 与后端 solver/app/devices.py 一一对应：引脚名、单位、默认值都保持一致。
export const COMPONENTS = {
  resistor: {
    label: '电阻', prefix: 'R', unit: 'Ω', defValue: 1000, group: 'dc',
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  vsource: {
    label: '电压源', prefix: 'V', unit: 'V', defValue: 5, group: 'dc',
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 }]
  },
  isource: {
    label: '电流源', prefix: 'I', unit: 'A', defValue: 0.01, group: 'dc',
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 }]
  },
  ground: {
    label: '接地', prefix: 'GND', unit: 'V', defValue: null, group: 'dc',
    pins: [{ name: 'p0', dx: 0, dy: 0 }]
  },
  // ---- 动态元件（交流 / 暂态）----
  capacitor: {
    label: '电容', labelOffset: [22, -26], prefix: 'C', unit: 'F', defValue: 1e-6, group: 'dyn',
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  inductor: {
    label: '电感', labelOffset: [24, -26], prefix: 'L', unit: 'H', defValue: 1e-3, group: 'dyn',
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  switch: {
    label: '开关', labelOffset: [22, -26], prefix: 'S', unit: '-', defValue: null, group: 'dyn',
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  vsource3: {
    label: '三相电源', labelOffset: [30, -68], prefix: 'U', unit: 'V', defValue: 220, group: 'dyn',
    pins: [{ name: 'p0', dx: 0, dy: -60 }, { name: 'p1', dx: 0, dy: -20 },
           { name: 'p2', dx: 0, dy: 20 }, { name: 'p3', dx: 0, dy: 60 }]
  },
  // ---- 受控源 ----
  vcvs: {
    label: '压控电压源', labelOffset: [24, -28], prefix: 'E', unit: '×', defValue: 1, group: 'ac',
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 },
           { name: 'c0', dx: -40, dy: -16 }, { name: 'c1', dx: -40, dy: 16 }]
  },
  vccs: {
    label: '压控电流源', labelOffset: [24, -28], prefix: 'G', unit: 'S', defValue: 0.001, group: 'ac',
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 },
           { name: 'c0', dx: -40, dy: -16 }, { name: 'c1', dx: -40, dy: 16 }]
  },
  ccvs: {
    label: '流控电压源', labelOffset: [24, -28], prefix: 'H', unit: 'Ω', defValue: 1, group: 'ac',
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 }]
  },
  cccs: {
    label: '流控电流源', labelOffset: [24, -28], prefix: 'F', unit: '×', defValue: 1, group: 'ac',
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 }]
  },
  transformer: {
    label: '理想变压器', labelOffset: [-18, -48], prefix: 'T', unit: '×', defValue: 2, group: 'ac',
    pins: [{ name: 'p0', dx: -40, dy: -30 }, { name: 'p1', dx: -40, dy: 30 },
           { name: 'p2', dx: 40, dy: -30 }, { name: 'p3', dx: 40, dy: 30 }]
  },
  // ---- 半导体 / 运放 ----
  diode: {
    label: '二极管', labelOffset: [22, -26], prefix: 'D', unit: 'V', defValue: 0.7, group: 'semi',
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  zener: {
    label: '稳压管', labelOffset: [22, -26], prefix: 'DZ', unit: 'V', defValue: 5.1, group: 'semi',
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  bjt: {
    label: '三极管', labelOffset: [32, -38], prefix: 'Q', unit: '×', defValue: null, group: 'semi',
    pins: [{ name: 'b', dx: -30, dy: 0 }, { name: 'c', dx: 30, dy: -30 }, { name: 'e', dx: 30, dy: 30 }]
  },
  opamp: {
    label: '集成运放', labelOffset: [-48, -36], prefix: 'A', unit: '×', defValue: null, group: 'semi',
    pins: [{ name: 'inp', dx: -40, dy: -14 }, { name: 'inn', dx: -40, dy: 14 }, { name: 'out', dx: 40, dy: 0 }]
  }
};

export function pinPositions(comp) {
  const def = COMPONENTS[comp.type];
  const rot = (((comp.rotation || 0) % 360) * Math.PI) / 180;
  const cos = Math.cos(rot);
  const sin = Math.sin(rot);
  return def.pins.map((p) => {
    let x = p.dx;
    const y = p.dy;
    if (comp.mirror) x = -x;
    return { name: p.name, x: comp.x + (x * cos - y * sin), y: comp.y + (x * sin + y * cos) };
  });
}

export function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

// 「已知量」标注的锚点位置（由位置成员键解析）
export function notePosition(state, note) {
  const a = String(note?.anchor || '');
  if (a.startsWith('u:')) {
    const [cid, pin] = a.slice(2).split('/');
    const c = state.components.find((x) => x.id === cid);
    if (c) {
      const p = pinPositions(c).find((q) => q.name === pin);
      if (p) return { x: p.x, y: p.y };
    }
  } else if (a.startsWith('j:')) {
    const j = state.junctions.find((x) => x.id === a.slice(2));
    if (j) return { x: j.x, y: j.y };
  } else if (a.startsWith('w:')) {
    const w = state.wires.find((x) => x.id === a.slice(2));
    if (w && w.vertices.length) {
      const i = Math.max(0, Math.floor((w.vertices.length - 1) / 2));
      const p = w.vertices[i];
      const q = w.vertices[i + 1] || p;
      return { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
    }
  } else if (a.startsWith('c:')) {
    const c = state.components.find((x) => x.id === a.slice(2));
    if (c) return { x: c.x, y: c.y };
  }
  return null;
}

// 标注要显示的文字（画布与宽高计算共用同一份，避免两边不一致）
export function noteText(note) {
  const v = (note.value === null || note.value === undefined || note.value === '') ? '?' : note.value;
  return note.kind === 'branch_current' ? `I = ${v} A` : `V = ${v} V`;
}

// 标注标签的矩形（画布坐标）——用于命中检测与绘制。
// scale：框按屏幕像素固定大小，所以画布尺寸要除以 scale（和其它文字一样不随缩放变大小）
export function noteBox(state, note, scale = 1) {
  const p = notePosition(state, note);
  if (!p) return null;
  const text = noteText(note);
  const w = Math.max(46, text.length * 7.5 + 12) / scale;
  const h = 20 / scale;
  return { x: p.x + 8 / scale, y: p.y - 30 / scale, w, h, pos: p, text };
}

export function hitNote(state, p, scale = 1) {
  const notes = state.notes || [];
  for (let i = notes.length - 1; i >= 0; i--) {
    const b = noteBox(state, notes[i], scale);
    if (b && p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) return notes[i];
  }
  return null;
}

export function snapToGrid(v, g = GRID) {
  return Math.round(v / g) * g;
}

// 收集所有可吸附的"连接点"（含导线拐点：拐点也是节点）
export function connectionPoints(state) {
  const pts = [];
  for (const c of state.components) for (const p of pinPositions(c)) pts.push({ x: p.x, y: p.y, kind: 'pin', comp: c.id, pin: p.name });
  for (const w of state.wires) {
    const n = w.vertices.length;
    w.vertices.forEach((v, i) => {
      const isEnd = i === 0 || i === n - 1;
      pts.push({ x: v.x, y: v.y, kind: isEnd ? 'wire' : 'wire-corner', wire: w.id, end: i });
    });
  }
  for (const j of state.junctions) pts.push({ x: j.x, y: j.y, kind: 'junction', junction: j.id });
  return pts;
}

// 正交路由：只允许 90° 弯折。返回折点（无折点则 null）
export function orthoCorner(from, to) {
  if (Math.abs(from.x - to.x) < 1e-6 || Math.abs(from.y - to.y) < 1e-6) return null;
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  // 主轴先走：水平距离大则先水平再垂直，反之先垂直
  return dx >= dy ? { x: to.x, y: from.y } : { x: from.x, y: to.y };
}

// 正交路径（含起点、折点、终点）
export function orthoPath(from, to) {
  const c = orthoCorner(from, to);
  return c ? [from, c, to] : [from, to];
}

function projectOnSegment(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const l2 = dx * dx + dy * dy;
  if (l2 === 0) return { x: a.x, y: a.y, t: 0 };
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2;
  t = Math.max(0, Math.min(1, t));
  return { x: a.x + t * dx, y: a.y + t * dy, t };
}

// 吸附：优先连接点 → 导线内部(T接) → 网格
// opts.noWire = true 时**不吸附到导线上**（用于「按住 Shift 穿过不连」）
export function snapPoint(state, p, radius = SNAP, opts = {}) {
  const noWire = !!opts.noWire;
  let best = null, bestD = radius;
  for (const cp of connectionPoints(state)) {
    if (noWire && (cp.kind === 'wire' || cp.kind === 'wire-corner')) continue;
    const d = dist(p, cp);
    if (d < bestD) { bestD = d; best = { point: { x: cp.x, y: cp.y }, target: cp }; }
  }
  if (best) return best;

  if (!noWire) {
    for (const w of state.wires) {
      for (let i = 0; i < w.vertices.length - 1; i++) {
        const proj = projectOnSegment(p, w.vertices[i], w.vertices[i + 1]);
        const d = dist(p, proj);
        if (d < bestD && proj.t > 0.001 && proj.t < 0.999) {
          bestD = d;
          best = { point: { x: proj.x, y: proj.y }, target: { kind: 'wire-mid', wire: w.id } };
        }
      }
    }
    if (best) return best;
  }

  return { point: { x: snapToGrid(p.x), y: snapToGrid(p.y) }, target: { kind: 'grid' } };
}

// 把点从最近的导线上推开（保证电气上不与它相接）——「Shift 穿过不连」用
export function detachFromWires(state, p, keepAway = 5) {
  let best = null, bestD = Infinity;
  for (const w of state.wires) {
    for (let i = 0; i < w.vertices.length - 1; i++) {
      const a = w.vertices[i], b = w.vertices[i + 1];
      const proj = projectOnSegment(p, a, b);
      const d = dist(p, proj);
      if (d < bestD) { bestD = d; best = { proj, a, b }; }
    }
  }
  if (!best || bestD >= keepAway) return p;
  const dx = best.b.x - best.a.x, dy = best.b.y - best.a.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const side = Math.sign((p.x - best.proj.x) * nx + (p.y - best.proj.y) * ny) || 1;
  return { x: best.proj.x + nx * keepAway * side, y: best.proj.y + ny * keepAway * side };
}

// 离某点最近的元件（用于把「电压标注」转成「电流标注」时换对象）
export function nearestComponent(state, p) {
  let best = null, bestD = Infinity;
  for (const c of state.components) {
    const pts = pinPositions(c);
    const cx = pts.reduce((s, q) => s + q.x, 0) / pts.length;
    const cy = pts.reduce((s, q) => s + q.y, 0) / pts.length;
    const d = dist(p, { x: cx, y: cy });
    if (d < bestD) { bestD = d; best = c; }
  }
  return best;
}

export function hitComponent(state, p) {  for (let i = state.components.length - 1; i >= 0; i--) {
    const c = state.components[i];
    const pts = pinPositions(c);
    const xs = pts.map((q) => q.x), ys = pts.map((q) => q.y);
    const minX = Math.min(...xs) - 14, maxX = Math.max(...xs) + 14;
    const minY = Math.min(...ys) - 14, maxY = Math.max(...ys) + 14;
    if (p.x >= minX && p.x <= maxX && p.y >= minY && p.y <= maxY) return c;
  }
  return null;
}

export function hitWire(state, p, tol = 8) {
  for (let i = state.wires.length - 1; i >= 0; i--) {
    const w = state.wires[i];
    for (let s = 0; s < w.vertices.length - 1; s++) {
      const proj = projectOnSegment(p, w.vertices[s], w.vertices[s + 1]);
      if (dist(p, proj) <= tol) return w;
    }
  }
  return null;
}

export function hitJunction(state, p, tol = 8) {
  for (let i = state.junctions.length - 1; i >= 0; i--) {
    if (dist(p, state.junctions[i]) <= tol) return state.junctions[i];
  }
  return null;
}

// 端点是否落在某导线"内部"（用于自动生成 junction）
// 容差必须 ≥ 后端 topology.py 的 ON_WIRE_TOL(=2.0)：后端在 2.0 以内就判定"接上"，
// 前端若用更小的容差，就会出现「电气上连了、画面上却没有三通点」的静默连接。
export function endpointOnWireInterior(state, point, excludeWireId) {
  for (const w of state.wires) {
    if (w.id === excludeWireId) continue;
    for (let s = 0; s < w.vertices.length - 1; s++) {
      const proj = projectOnSegment(point, w.vertices[s], w.vertices[s + 1]);
      if (dist(point, proj) < 2.5 && proj.t > 0.001 && proj.t < 0.999) return true;
    }
  }
  return false;
}
