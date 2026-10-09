// 元件几何库、坐标变换、吸附与命中检测（docs/drawing-model.md §2、§3）

export const GRID = 10;
export const SNAP = 14;

// 元件定义：引脚为局部坐标（含符号朝向：p0=正端/首端，p1=负端/末端）
export const COMPONENTS = {
  resistor: {
    label: '电阻', prefix: 'R', unit: 'Ω', defValue: 1000,
    pins: [{ name: 'p0', dx: -30, dy: 0 }, { name: 'p1', dx: 30, dy: 0 }]
  },
  vsource: {
    label: '电压源', prefix: 'V', unit: 'V', defValue: 5,
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 }]
  },
  isource: {
    label: '电流源', prefix: 'I', unit: 'A', defValue: 0.01,
    pins: [{ name: 'p0', dx: 0, dy: -30 }, { name: 'p1', dx: 0, dy: 30 }]
  },
  ground: {
    label: '接地', prefix: 'GND', unit: '', defValue: null,
    pins: [{ name: 'p0', dx: 0, dy: 0 }]
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
export function snapPoint(state, p, radius = SNAP) {
  let best = null, bestD = radius;
  for (const cp of connectionPoints(state)) {
    const d = dist(p, cp);
    if (d < bestD) { bestD = d; best = { point: { x: cp.x, y: cp.y }, target: cp }; }
  }
  if (best) return best;

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

  return { point: { x: snapToGrid(p.x), y: snapToGrid(p.y) }, target: { kind: 'grid' } };
}

export function hitComponent(state, p) {
  for (let i = state.components.length - 1; i >= 0; i--) {
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
export function endpointOnWireInterior(state, point, excludeWireId) {
  for (const w of state.wires) {
    if (w.id === excludeWireId) continue;
    for (let s = 0; s < w.vertices.length - 1; s++) {
      const proj = projectOnSegment(point, w.vertices[s], w.vertices[s + 1]);
      if (dist(point, proj) < 1.0 && proj.t > 0.001 && proj.t < 0.999) return true;
    }
  }
  return false;
}
