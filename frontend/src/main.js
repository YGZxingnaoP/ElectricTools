// 应用入口与交互控制器（CAD 式：缩放 / 平移 / 悬停反馈）
import { EditorState } from './core/model.js';
import { draw } from './core/renderer.js';
import {
  COMPONENTS, pinPositions, snapPoint, hitComponent, hitWire, hitJunction, hitNote,
  endpointOnWireInterior, dist, orthoPath, SNAP, detachFromWires, notePosition, nearestComponent
} from './core/geometry.js';
import { SolverClient } from './net/client.js';
import { renderInspector, renderResults, renderFormulas, renderValidation } from './ui/sidebar.js';
import { renderPhasor, renderCurves } from './ui/panels.js';
import { DOCS, renderLearn } from './ui/learn.js';
import { setupAiPanel } from './ui/aiPanel.js';
import { renderProbe } from './ui/probePanel.js';
import { setupSettings } from './ui/settings.js';
import { fmtNum } from './core/numfmt.js';

// 当前存档名（持久化在 localStorage）
// 一个存档 = 画的图 + 求解结果 + 聊天记录，全部在同一个文件里
let ARCHIVE = localStorage.getItem('et.archive') || '';

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const hint = document.getElementById('hint');
const debugEl = document.getElementById('debug');
const connStatus = document.getElementById('conn-status');
const inspEl = document.getElementById('inspector');
const probeEl = document.getElementById('probe');
const resultsEl = document.getElementById('results');
const phasorEl = document.getElementById('phasor');
const curvesEl = document.getElementById('curves');
let lastSweep = null;
let lastResults = null;
const solveOutEl = document.getElementById('solve-out');
const formulasEl = document.getElementById('formulas');
const validationEl = document.getElementById('validation');

// ---------- 侧栏区块折叠（点标题收起/展开） ----------
function setupCollapse() {
  document.querySelectorAll('#sidebar .panel-head').forEach((h) => {
    const body = h.parentElement.querySelector('.panel-body');
    if (!body) return;
    h.addEventListener('click', () => h.parentElement.classList.toggle('collapsed'));
  });
}
setupCollapse();

// ---------- 全局错误上报（便于定位问题） ----------
const errlog = document.getElementById('errlog');
function showError(msg) {
  if (!errlog) return;
  errlog.style.display = 'block';
  const line = document.createElement('div');
  line.textContent = '⚠ ' + msg;
  errlog.appendChild(line);
  console.error(msg);
}
window.addEventListener('error', (e) => showError(`${e.message} @ ${e.filename}:${e.lineno}`));
window.addEventListener('unhandledrejection', (e) => showError('Promise: ' + (e.reason?.message || e.reason)));

const state = new EditorState();
const client = new SolverClient(wsUrl());

const aiPanel = setupAiPanel({
  logEl: document.getElementById('ai-log'),
  textEl: document.getElementById('ai-text'),
  sendEl: document.getElementById('ai-send'),
  client, state, sessionId: () => ARCHIVE, pinPositions
});

// ---------- 视图摄像机 ----------
const view = { w: 0, h: 0, dpr: 1 };
const cam = { x: 0, y: 0, scale: 1 };

let results = null;
let anim = 0;
let draft = null;        // 正在绘制的导线 {vertices:[worldPts]}
let drag = null;         // 元件拖拽
let panning = null;      // 平移中 {sx, sy, camx, camy}
let spaceDown = false;
let shiftDown = false;   // 画导线时按住 Shift = 穿过不连（不吸附到其它导线）
let mouseScreen = { x: 0, y: 0 };
let mouseWorld = { x: 0, y: 0 };
let hover = null;        // {kind,id}
let hoverSnap = null;
let uiCfg = {};          // 来自 /api/config 与设置弹窗的界面配置
let nodeLabels = {};     // 自定义节点名称（持久化在存档 annotations.node_notes）
let lastProbe = null;    // 最近一次探针详情（用于重命名后即时刷新）

function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws`;
}

// 世界 ↔ 屏幕
function toWorld(p) { return { x: (p.x - cam.x) / cam.scale, y: (p.y - cam.y) / cam.scale }; }
function toScreen(p) { return { x: p.x * cam.scale + cam.x, y: p.y * cam.scale + cam.y }; }
function clientToScreen(e) {
  const r = canvas.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

// ---------- 画布尺寸 ----------
function resize() {
  const dpr = window.devicePixelRatio || 1;
  const r = canvas.getBoundingClientRect();
  view.w = r.width; view.h = r.height; view.dpr = dpr;
  canvas.width = Math.max(1, Math.round(r.width * dpr));
  canvas.height = Math.max(1, Math.round(r.height * dpr));
}
window.addEventListener('resize', resize);

// ---------- 渲染循环 ----------
function loop() {
  // 电流流动动画的全局相位（0.006 为基准；current_flow_speed 为倍率）
  const mul = Number(uiCfg.current_flow_speed ?? 1) || 1;
  anim = (anim + 0.006 * mul) % 1;
  const ghost = state.pendingType && !panning ? ghostComponent() : null;
  draw(ctx, {
    state, view, cam, results, anim, hover,
    ui: { ...uiCfg },
    nodeLabels,
    overlay: { draft, preview: wirePreview(), hoverSnap, ghost, noConnect: state.tool === 'wire' && shiftDown }
  });
  debugEl.textContent = `缩放 ${(cam.scale * 100).toFixed(0)}%  |  光标 (${mouseWorld.x.toFixed(0)}, ${mouseWorld.y.toFixed(0)})  |  元件 ${state.components.length}  导线 ${state.wires.length}`;
  requestAnimationFrame(loop);
}

function ghostComponent() {
  const def = COMPONENTS[state.pendingType];
  if (!def) return null;
  const s = snapPoint(state, mouseWorld);
  return { id: def.prefix, type: state.pendingType, x: s.point.x, y: s.point.y, rotation: 0, mirror: false, value: def.defValue, unit: def.unit };
}

// ---------- 求解（去抖：数值快、符号慢） ----------
let numericTimer = null, symbolicTimer = null;

/** 分析域设置：直流 / 正弦交流（相量） / 暂态 */
function domainCfg() {
  const num = (id, d) => {
    const el = document.getElementById(id);
    const v = el ? parseFloat(el.value) : NaN;
    return Number.isFinite(v) ? v : d;
  };
  const sel = document.getElementById('domain-sel');
  return {
    domain: sel ? sel.value : 'dc',
    freq: num('freq-in', 50),
    tstop: num('tstop-in', 0.005),
    nsteps: Math.max(11, Math.round(num('nsteps-in', 201))),
  };
}

function scheduleSolve() {
  clearTimeout(numericTimer);
  clearTimeout(symbolicTimer);
  numericTimer = setTimeout(() => sendSolve('numeric'), 70);
  symbolicTimer = setTimeout(() => sendSolve('both'), 420);
  scheduleArchiveSave();         // 图变化时也存一次
  updateHint();
}
function sendSolve(mode) {
  if (!client.ready || !ARCHIVE) return;
  client.solve(ARCHIVE, state.toNetlist(pinPositions), mode, domainCfg());
}

client.onSweep = (payload) => {
  lastSweep = payload;
  renderCurves(curvesEl, lastResults, lastSweep);
};
client.onStatus = (s) => {  connStatus.textContent = s === 'on' ? '已连接求解服务' : '断开，重连中…';
  connStatus.className = 'conn-status ' + (s === 'on' ? 'on' : 'off');
  if (s === 'on') scheduleSolve();
  else aiPanel.abort('⚠️ 与求解服务的连接已断开（后端可能未运行或正在重启），本次提问已中断，请重试。');
};
client.onResult = (payload) => {
  results = payload;
  refreshSidebar();
  aiPanel.setNodes(payload.node_order || []);
  scheduleArchiveSave();          // 结果随存档一起保存
};
client.onError = (p) => showError('求解服务：' + JSON.stringify(p));
client.onNodeDetail = (p) => showProbe(attachNodeLabel(p));

// ---------- 一键求解：按一下出数值（不需要任何输入） ----------
let lastCompute = null;

async function runCompute() {
  if (solveOutEl) solveOutEl.innerHTML = '<p class="muted">计算中…</p>';
  let data;
  try {
    const r = await fetch('/api/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: ARCHIVE, schematic: state.toNetlist(pinPositions) })
    });
    data = await r.json();
  } catch (e) {
    data = { error: '请求失败：' + e.message };
  }
  lastCompute = data;
  renderComputeOut();
}

function renderComputeOut() {
  const out = solveOutEl;
  if (!out) return;
  const d = lastCompute;
  if (!d) { out.innerHTML = ''; return; }
  if (d.error) { out.innerHTML = `<p class="inv-err">✗ ${escAttr(d.error)}</p>`; return; }

  const rows = [];
  for (const n of (d.nodes || [])) {
    if (n.id === '0') continue;
    rows.push(`<tr><td>V(${escAttr(n.id)})</td><td class="val">${n.voltage == null ? '—' : fmtNum(n.voltage) + ' V'}</td></tr>`);
  }
  for (const b of (d.branches || [])) {
    rows.push(`<tr><td>I(${escAttr(b.component)})</td><td class="val">${b.current == null ? '—' : fmtNum(b.current) + ' A'}</td></tr>`);
  }

  // 未知量：已经由「图上已知量」反解出来的，这里**不再重复**（代数参考值面板顶部已显示一次）
  const unk = (d.unknowns || []).map((u) => {
    if (u.value !== null && u.value !== undefined) return '';
    if (u.rth == null) return `<div class="inv-warn">${escAttr(u.id)}：还没有数值（缺条件）。</div>`;
    return `<div class="inv-warn">${escAttr(u.id)} 还没有数值（缺条件）—— 从它两端看进去的等效电阻 = <b>${fmtNum(u.rth)} Ω</b>
        <span class="muted">（开路电压 ${fmtNum(u.voc)} V · 短路电流 ${fmtNum(u.isc)} A）</span></div>
      ${u.reason ? `<div class="muted" style="font-size:12px;line-height:1.5;margin-top:2px">${escAttr(u.reason)}</div>` : ''}`;
  }).join('');

  out.innerHTML = `
    ${unk}
    <table style="margin-top:8px">${rows.join('')}</table>`;
}

// ---------- 条件求解（通用）：图上留空的未知量 + 条件 → 代数值 ----------
let condRows = [{ kind: 'node_voltage', ref: '', value: '' }];
let lastConstraints = null;

function condTargets(kind) {
  if (!results || !results.ok) return [];
  if (kind === 'branch_current') {
    return results.branches.map((b) => ({
      id: b.component,
      label: `${b.component}（${b.node_p}→${b.node_n}）`
    }));
  }
  return results.node_order
    .filter((n) => n !== '0')
    .map((n) => ({ id: n, label: nodeLabels[n] ? `${n}｜${nodeLabels[n]}` : n }));
}

// 条件行的增删改（就地更新，不重绘整个属性面板）
function renderCondRows() {
  const box = document.getElementById('cond-list');
  if (!box) return;
  box.innerHTML = '';
  condRows.forEach((row, i) => {
    const opts = condTargets(row.kind);
    if (!row.ref && opts.length) row.ref = opts[0].id;
    const div = document.createElement('div');
    div.className = 'cond-row';
    div.innerHTML = `
      <select class="cond-kind">
        <option value="node_voltage"${row.kind === 'node_voltage' ? ' selected' : ''}>节点电压</option>
        <option value="branch_current"${row.kind === 'branch_current' ? ' selected' : ''}>支路电流</option>
      </select>
      <select class="cond-ref">${opts.map((o) => `<option value="${escAttr(o.id)}"${o.id === row.ref ? ' selected' : ''}>${escAttr(o.label)}</option>`).join('')}</select>
      <span class="cond-eq">=</span>
      <input class="cond-val" type="text" spellcheck="false" value="${escAttr(row.value)}" placeholder="如 2" />
      <button class="cond-del" title="删除这条">×</button>`;
    const kindSel = div.querySelector('.cond-kind');
    const refSel = div.querySelector('.cond-ref');
    const valInp = div.querySelector('.cond-val');
    kindSel.addEventListener('change', () => {
      row.kind = kindSel.value;
      const list = condTargets(row.kind);
      row.ref = list.length ? list[0].id : '';
      refSel.innerHTML = list.map((o) => `<option value="${escAttr(o.id)}">${escAttr(o.label)}</option>`).join('');
    });
    refSel.addEventListener('change', () => { row.ref = refSel.value; });
    valInp.addEventListener('input', () => { row.value = valInp.value; });
    div.querySelector('.cond-del').addEventListener('click', () => {
      condRows.splice(i, 1);
      if (!condRows.length) condRows.push({ kind: 'node_voltage', ref: '', value: '' });
      renderCondRows();
    });
    box.appendChild(div);
  });
}

function addCondition() {
  condRows.push({ kind: 'node_voltage', ref: '', value: '' });
  renderCondRows();
}

async function runConstraints() {
  const out = document.getElementById('cond-out');
  const conds = condRows
    .filter((r) => r.ref && String(r.value ?? '').trim() !== '')
    .map((r) => ({ kind: r.kind, ref: r.ref, value: r.value }));
  if (!conds.length) {
    if (out) out.innerHTML = '<p class="muted">请至少填一条完整条件（选一个量 + 填它的值）</p>';
    return;
  }
  if (out) out.innerHTML = '<p class="muted">求解中…</p>';
  let data;
  try {
    const r = await fetch('/api/constraints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: ARCHIVE,
        schematic: state.toNetlist(pinPositions),
        conditions: conds
      })
    });
    data = await r.json();
  } catch (e) {
    data = { error: '请求失败：' + e.message };
  }
  lastConstraints = data;
  renderCondOut();
}

function renderCondOut() {
  const out = document.getElementById('cond-out');
  if (!out) return;
  const d = lastConstraints;
  if (!d) { out.innerHTML = ''; return; }
  if (d.error) { out.innerHTML = `<p class="inv-err">✗ ${escAttr(d.error)}</p>`; return; }

  const sol = (d.solutions || [])[0];
  if (!sol) { out.innerHTML = '<p class="inv-err">✗ 没有解</p>'; return; }
  const items = Object.entries(sol.values || {}).map(([cid, info]) => `
    <div class="inv-ok">✓ ${escAttr(cid)} = <b>${fmtNum(info.value)} ${escAttr(info.unit)}</b>${info.feasible ? '' : ` <span class="inv-warn">（${escAttr(info.note || '物理上不可行')}）</span>`}</div>`).join('');
  const steps = (d.steps || []).map((s) => `
    <div class="step">
      <div class="step-t">${escAttr(s.title)}</div>
      <div class="step-x">${escAttr(s.text || '')}</div>
      ${s.latex ? `<div class="step-eq"><span class="tex" data-tex="${escAttr(s.latex)}"></span></div>` : ''}
      ${(s.table || []).map((r) => `<div class="step-eq"><span class="tex" data-tex="${escAttr(r.label + '=' + r.expr)}"></span></div>`).join('')}
    </div>`).join('');

  out.innerHTML = `
    <div class="inv-res">
      ${items}
      ${sol.feasible ? '<button id="cond-apply" class="mini-btn" style="width:100%">把这些值填回图上</button>' : ''}
      <details class="inv-steps"><summary>推导过程（${(d.steps || []).length} 步）</summary>${steps}</details>
    </div>`;
  renderTexIn(out);

  const btn = out.querySelector('#cond-apply');
  if (btn) {
    btn.addEventListener('click', () => {
      for (const [cid, info] of Object.entries(sol.values || {})) {
        if (info.feasible) state.setValue(cid, info.value);
      }
      lastConstraints = null;
      scheduleSolve();
      refreshSidebar();
    });
  }
}

function renderTexIn(scope) {
  if (!window.katex) return;  scope.querySelectorAll('.tex').forEach((elm) => {
    const tex = elm.getAttribute('data-tex');
    if (!tex) return;
    try {
      window.katex.render(tex, elm, { throwOnError: false, displayMode: false });
    } catch {
      elm.textContent = tex;
    }
  });
}

// ---------- 侧栏 ----------
function refreshSidebar() {
  renderInspector(inspEl, state, {
    onValue: (id, val) => { state.setValue(id, val); scheduleSolve(); },
    onSymbol: (id, sym) => { state.setSymbol(id, sym); scheduleSolve(); },
    onParam: (id, key, val) => { state.setParam(id, key, val); scheduleSolve(); },
    inverseTargets: condTargets,
    onAddCondition: addCondition,
    onSolveConstraints: runConstraints,
    onCompute: runCompute,
    onNoteValue: (id, v) => {
      const num = parseFloat(String(v).replace(/[^\d.eE+-]/g, ''));
      state.updateNote(id, { value: isFinite(num) ? num : null });
      scheduleSolve();
    },
    onNoteKind: (id, kind) => {
      const note = state.getSelectedNote();
      if (!note) return;
      const patch = { kind };
      // 换类型时自动换「对象」：电压↔电流 互转，不用重新画
      if (kind === 'branch_current' && !String(note.anchor).startsWith('c:')) {
        const c = nearestComponent(state, notePosition(state, note) || { x: 0, y: 0 });
        if (c) patch.anchor = `c:${c.id}`;
      } else if (kind === 'node_voltage' && String(note.anchor).startsWith('c:')) {
        patch.anchor = `u:${String(note.anchor).slice(2)}/p0`;
      }
      state.updateNote(id, patch);
      refreshSidebar();
      scheduleSolve();
    },
    onNoteTarget: (id, anchor) => { state.updateNote(id, { anchor }); refreshSidebar(); scheduleSolve(); },
    onNoteDelete: (id) => { state.removeNote(id); refreshSidebar(); scheduleSolve(); },
    // 标注可选的「对象」清单：节点（电压）/ 元件（电流）
    noteTargets: () => {
      const components = state.components
        .filter((c) => c.type !== 'ground')
        .map((c) => ({ value: `c:${c.id}`, label: `${c.id}（${(COMPONENTS[c.type] || {}).label || c.type}）的电流` }));
      const nodes = [];
      if (results && results.ok) {
        for (const nid of results.node_order) {
          if (nid === '0') continue;
          const m = (results.nodes[nid].members || [])[0];
          if (m) nodes.push({ value: m, label: `${nid} 节点的电压${nodeLabels[nid] ? `（${nodeLabels[nid]}）` : ''}` });
        }
      }
      return { nodes, components };
    },
    onRename: (id, name) => {
      if (!state.renameComponent(id, name)) {
        hint.textContent = '位号无效或与其它元件重名，已还原';
        setTimeout(updateHint, 1500);
      }
      scheduleSolve();
    },
    onRotate: (id, rot) => {
      const c = state.components.find((x) => x.id === id);
      if (c) { c.rotation = rot; scheduleSolve(); }
    }
  });
  renderComputeOut();
  lastResults = results;
  renderResults(resultsEl, results, { nodeLabels, onRenameNode: renameNode });
  renderFormulas(formulasEl, results);
  renderValidation(validationEl, results);
  // 右栏新增的三个折叠栏（相量图 / 曲线 / 解法步骤）
  renderPhasor(phasorEl, results);
  renderCurves(curvesEl, results, lastSweep);
  renderTexIn(phasorEl);
  renderCondRows();          // 条件反解的行（目标列表要依赖 solver 结果）
}

function updateHint() {
  if (state.pendingType) {
    const def = COMPONENTS[state.pendingType];
    hint.textContent = `放置 ${def.label}：移动到画布点击放置（Esc 取消）`;
    return;
  }
  const msgs = {
    select: '左键拖动元件 · 滚轮缩放 · 中键/空格+拖动平移 · R 旋转 · Del 删除',
    wire: '点击端子开始 → 点击空白加拐点 → 点击目标端子结束 · Enter 结束 · Esc 取消 · '
        + '端点落到导线上会形成三通（会连接）；按住 Shift 则穿过不连',
    note: '标注电压：点节点（导线 / 节点圆点 / 元件端子）→ 填电压值；点已有的标注可改类型和对象',
    noteI: '标注电流：点元件 → 填电流值；点已有的标注可改类型和对象'
  };
  hint.textContent = (msgs[state.tool] || '') + (state.tool === 'wire' && shiftDown ? '　【Shift：穿过不连】' : '');
}

// ---------- 指针交互 ----------
canvas.addEventListener('pointerdown', (e) => {
  canvas.setPointerCapture(e.pointerId);
  const sp = clientToScreen(e);
  const wp = toWorld(sp);
  mouseScreen = sp; mouseWorld = wp;

  // 平移：中键 或 空格+左键
  if (e.button === 1 || (e.button === 0 && spaceDown)) {
    panning = { sx: sp.x, sy: sp.y, camx: cam.x, camy: cam.y };
    canvas.style.cursor = 'grabbing';
    e.preventDefault();
    return;
  }
  if (e.button !== 0) return;   // 其余按键忽略

  // 1) 放置元件
  if (state.pendingType) {
    const s = snapPoint(state, wp);
    state.addComponent(state.pendingType, s.point.x, s.point.y, state.pendingParams || null);
    state.pendingType = null;
    state.pendingParams = null;
    setActivePalette(null);
    updateHint();
    scheduleSolve();
    return;
  }

  // 2) 画导线（只允许 90° 弯折）
  if (state.tool === 'wire') {
    const s = wireSnap(wp);
    if (!draft) draft = { vertices: [s.point] };
    else {
      appendOrtho(draft.vertices, s.point);
      if (isConnTarget(s.target)) finishWire();
    }
    return;
  }

  // 2.5) 节点探针
  if (state.tool === 'probe') {
    probeAt(wp);
    return;
  }

  // 2.6) 放置「已知量」标注：标注电压 V 点在节点上；标注电流 A 点在元件上
  if (state.tool === 'note' || state.tool === 'noteI') {
    placeNote(wp, state.tool === 'noteI' ? 'branch_current' : 'node_voltage');
    return;
  }

  // 3) 选择 / 拖拽（标注在最上层，先判它）
  const note = hitNote(state, wp, cam.scale);
  if (note) {
    state.selection = { kind: 'note', id: note.id };
    refreshSidebar();
    return;
  }
  const comp = hitComponent(state, wp);
  if (comp) {
    state.selection = { kind: 'component', id: comp.id };
    drag = startDrag(comp, wp);
    refreshSidebar();
    return;
  }
  const wire = hitWire(state, wp);
  if (wire) { state.selection = { kind: 'wire', id: wire.id }; refreshSidebar(); return; }
  const j = hitJunction(state, wp);
  if (j) {
    state.selection = { kind: 'junction', id: j.id };
    probeAt(wp);               // 点击节点圆点也显示电压/电流/计算方法
    refreshSidebar();
    return;
  }
  state.selection = null;
  refreshSidebar();
});

canvas.addEventListener('pointermove', (e) => {
  const sp = clientToScreen(e);
  const wp = toWorld(sp);
  mouseScreen = sp; mouseWorld = wp;

  if (panning) {
    cam.x = panning.camx + (sp.x - panning.sx);
    cam.y = panning.camy + (sp.y - panning.sy);
    return;
  }
  if (drag) { moveDrag(wp); return; }

  // 悬停反馈
  hover = null;
  const comp = hitComponent(state, wp);
  if (comp) hover = { kind: 'component', id: comp.id };
  else {
    const wire = hitWire(state, wp);
    if (wire) hover = { kind: 'wire', id: wire.id };
  }

  // 吸附预览
  if (state.tool === 'wire') hoverSnap = wireSnap(wp);
  else if (state.pendingType) hoverSnap = snapPoint(state, wp);
  else hoverSnap = null;

  // 光标样式
  if (spaceDown) canvas.style.cursor = 'grab';
  else if (state.pendingType || state.tool === 'wire') canvas.style.cursor = 'crosshair';
  else if (drag) canvas.style.cursor = 'grabbing';
  else if (comp) canvas.style.cursor = 'move';
  else if (hover) canvas.style.cursor = 'pointer';
  else canvas.style.cursor = 'default';
});

function endPointer() {
  if (panning) { panning = null; canvas.style.cursor = spaceDown ? 'grab' : 'default'; }
  if (drag) { drag = null; scheduleSolve(); }
}
canvas.addEventListener('pointerup', endPointer);
canvas.addEventListener('pointercancel', endPointer);
canvas.addEventListener('pointerleave', () => { hover = null; hoverSnap = null; });

// 滚轮缩放（以光标为中心）
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const sp = clientToScreen(e);
  const before = toWorld(sp);
  const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  cam.scale = Math.min(6, Math.max(0.15, cam.scale * factor));
  cam.x = sp.x - before.x * cam.scale;
  cam.y = sp.y - before.y * cam.scale;
}, { passive: false });

function isConnTarget(t) { return t && ['pin', 'wire', 'wire-corner', 'wire-mid', 'junction'].includes(t.kind); }

// 正交（90°）追加：把 target 以直角方式接到折线末尾
function appendOrtho(verts, target) {
  const last = verts[verts.length - 1];
  const path = orthoPath(last, target);
  for (let i = 1; i < path.length; i++) {
    const prev = verts[verts.length - 1];
    if (Math.abs(prev.x - path[i].x) > 0.5 || Math.abs(prev.y - path[i].y) > 0.5) {
      verts.push({ x: path[i].x, y: path[i].y });
    }
  }
}

// 画导线时的吸附：按住 Shift 则不吸附到其它导线上，并把它推开 → 电气上不连（穿过去）
function wireSnap(wp) {
  const s = snapPoint(state, wp, SNAP, shiftDown ? { noWire: true } : {});
  if (shiftDown && s.target.kind === 'grid') {
    const p = detachFromWires(state, s.point, 5);
    if (p !== s.point) s.point = p;
  }
  return s;
}

// 实时预览（正交）
function wirePreview() {
  if (!draft) return null;
  const s = wireSnap(mouseWorld);
  const pts = draft.vertices.map((v) => ({ x: v.x, y: v.y }));
  const last = pts[pts.length - 1];
  for (const p of orthoPath(last, s.point).slice(1)) {
    const prev = pts[pts.length - 1];
    if (Math.abs(prev.x - p.x) > 0.5 || Math.abs(prev.y - p.y) > 0.5) pts.push({ x: p.x, y: p.y });
  }
  return pts;
}

function finishWire() {
  if (!draft) return;
  const verts = dedupe(draft.vertices);
  const created = state.addWire(verts);
  if (created) {
    for (const v of [verts[0], verts[verts.length - 1]]) {
      if (endpointOnWireInterior(state, v, created.id)) state.addJunction(v.x, v.y);
    }
    scheduleSolve();
  }
  draft = null;
  hoverSnap = null;
}

function dedupe(verts) {
  const out = [];
  for (const v of verts) {
    const last = out[out.length - 1];
    if (!last || dist(last, v) > 0.5) out.push({ x: v.x, y: v.y });
  }
  return out;
}

function startDrag(comp, wp) {
  const attach = [];
  const pins = pinPositions(comp);
  for (const w of state.wires) {
    if (!w.vertices.length) continue;
    const ends = [
      { idx: 0, v: w.vertices[0] },
      { idx: w.vertices.length - 1, v: w.vertices[w.vertices.length - 1] }
    ];
    for (const e of ends) {
      const pin = pins.find((q) => dist(q, e.v) < 1.5);
      if (pin) attach.push({ wire: w, idx: e.idx, pin: pin.name });
    }
  }
  return { comp, start: { x: wp.x, y: wp.y }, orig: { x: comp.x, y: comp.y }, attach, moved: false };
}

function moveDrag(wp) {
  if (!drag) return;
  const dx = wp.x - drag.start.x;
  const dy = wp.y - drag.start.y;
  if (!drag.moved && Math.hypot(dx, dy) * cam.scale < 2) return;
  if (!drag.moved) { state.pushHistory(); drag.moved = true; }
  drag.comp.x = drag.orig.x + dx;
  drag.comp.y = drag.orig.y + dy;
  const pins = pinPositions(drag.comp);
  for (const a of drag.attach) {
    const pin = pins.find((q) => q.name === a.pin);
    if (pin && a.wire.vertices[a.idx]) {
      a.wire.vertices[a.idx].x = pin.x;
      a.wire.vertices[a.idx].y = pin.y;
    }
  }
  state.emit();
}

// ---------- 节点探针 ----------
// 给探针详情附上自定义节点名
function attachNodeLabel(detail) {
  if (detail && detail.node) detail.label = nodeLabels[detail.node] || null;
  return detail;
}

function showProbe(detail) {
  lastProbe = detail;
  renderProbe(probeEl, detail);
}

// 命名 / 清除节点自定义名称（持久化在存档 annotations）
async function renameNode(nid) {
  if (!nid || nid === '0') return;
  const v = await askText({ title: `节点 ${nid} 的名称`, value: nodeLabels[nid] || '', okText: '保存' });
  if (v === null) return;
  const name = v.trim();
  if (name) nodeLabels[nid] = name;
  else delete nodeLabels[nid];
  refreshSidebar();
  if (lastProbe && lastProbe.node === nid) showProbe(attachNodeLabel(lastProbe));
  scheduleArchiveSave();
}

function memberToNodeMap() {
  const map = new Map();
  if (!results || !results.ok) return map;
  for (const [nid, info] of Object.entries(results.nodes)) {
    for (const m of (info.members || [])) map.set(m, nid);
  }
  return map;
}

function nodeKeyAt(wp) {
  const pr = 12 / cam.scale;
  for (const c of state.components) {
    for (const p of pinPositions(c)) {
      if (dist(wp, p) <= pr) return `u:${c.id}/${p.name}`;
    }
  }
  const j = hitJunction(state, wp, 12 / cam.scale + 4);
  if (j) return `j:${j.id}`;
  const w = hitWire(state, wp, 10 / cam.scale + 2);
  if (w) return `w:${w.id}`;
  return null;
}

function probeAt(wp) {
  const key = nodeKeyAt(wp);
  if (!key) {
    showProbe({ error: '此处没有节点：请点击导线、节点圆点或元件端子。' });
    return;
  }
  const nid = memberToNodeMap().get(key);
  if (!nid) {
    showProbe({ error: '该位置尚未对应到已求解的节点（电路可能还没解出来）。' });
    return;
  }
  const local = results && results.nodes ? results.nodes[nid] : null;
  showProbe(attachNodeLabel({
    node: nid,
    is_ground: nid === '0',
    voltage: local ? local.voltage : null,
    voltage_latex: local ? local.voltage_latex : null,
    branches: [],
    method: '（正在获取 KCL 与计算方法…）'
  }));
  client.probe(ARCHIVE, nid, state.toNetlist(pinPositions));
}

// 「已知量」标注：wantKind = node_voltage（点节点填电压）| branch_current（点元件填电流）
async function placeNote(wp, wantKind = 'node_voltage') {
  let anchor = null;
  let title = '';
  if (wantKind === 'branch_current') {
    const comp = hitComponent(state, wp) || nearestComponent(state, wp);
    if (!comp) {
      hint.textContent = '画布上还没有元件：请先放一个元件，再点它标注电流';
      setTimeout(updateHint, 2500);
      return;
    }
    anchor = `c:${comp.id}`;
    title = `已知：通过 ${comp.id} 的电流 = ? (A)`;
  } else {
    const key = nodeKeyAt(wp);
    if (!key) {
      hint.textContent = '请点在节点上（导线 / 节点圆点 / 元件端子）';
      setTimeout(updateHint, 2500);
      return;
    }
    anchor = key;
    title = '已知：这个节点的电压 = ? (V)';
  }
  const v = await askText({ title, value: '', okText: '放到图上' });
  if (v === null) return;
  const num = parseFloat(String(v).replace(/[^\d.eE+-]/g, ''));
  state.addNote(anchor, wantKind, isFinite(num) ? num : null);
  refreshSidebar();
  scheduleSolve();
  hint.textContent = isFinite(num) ? '标注已画到图上，求解会自动拿它反解未知量' : '标注已放置，请在右侧填数值';
  setTimeout(updateHint, 2500);
}

// ---------- 侧栏拖动调整宽度 ----------
const WIDTH_VARS = { palette: '--w-palette', sidebar: '--w-sidebar', 'ai-sidebar': '--w-ai-sidebar' };
function applySavedWidths() {
  try {
    const saved = JSON.parse(localStorage.getItem('et.widths') || '{}');
    for (const [panel, varName] of Object.entries(WIDTH_VARS)) {
      if (saved[panel]) document.documentElement.style.setProperty(varName, saved[panel] + 'px');
    }
  } catch { /* ignore */ }
}
function setupResizers() {
  document.querySelectorAll('.resizer').forEach((rz) => {
    rz.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const panel = rz.dataset.panel;
      const dir = rz.dataset.dir;
      const el = document.getElementById(panel);
      if (!el) return;
      const startX = e.clientX;
      const startW = el.getBoundingClientRect().width;
      const min = panel === 'palette' ? 150 : 220;
      rz.classList.add('active');
      try { rz.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        const w = Math.max(min, Math.min(760, dir === 'right' ? startW + dx : startW - dx));
        document.documentElement.style.setProperty(WIDTH_VARS[panel], w + 'px');
        resize();
      };
      const onUp = () => {
        rz.classList.remove('active');
        rz.removeEventListener('pointermove', onMove);
        rz.removeEventListener('pointerup', onUp);
        try {
          const saved = JSON.parse(localStorage.getItem('et.widths') || '{}');
          saved[panel] = Math.round(el.getBoundingClientRect().width);
          localStorage.setItem('et.widths', JSON.stringify(saved));
        } catch { /* ignore */ }
        resize();
      };
      rz.addEventListener('pointermove', onMove);
      rz.addEventListener('pointerup', onUp);
    });
  });
}

// ---------- 设置与界面配置 ----------
function applyUiConfig(ui) { if (ui) uiCfg = { ...uiCfg, ...ui }; }
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    const c = await r.json();
    applyUiConfig(c.ui);
    const p = c.paths && c.paths.archives_dir;
    const el = document.getElementById('rec-path');
    if (el && p) { el.textContent = '存档目录：' + p; el.title = p; }
  } catch { /* ignore */ }
}
function setupSettingsUI() {
  setupSettings({
    button: document.getElementById('btn-settings'),
    modal: document.getElementById('settings-modal'),
    bodyEl: document.getElementById('settings-body'),
    closeBtn: document.getElementById('settings-close'),
    saveBtn: document.getElementById('settings-save'),
    clearMemBtn: document.getElementById('settings-clear-memory'),
    msgEl: document.getElementById('settings-msg'),
    sessionId: () => ARCHIVE,
    onSaved: (s) => { applyUiConfig(s.ui); scheduleSolve(); }
  });
}

// ---------- 键盘 ----------
window.addEventListener('keydown', (e) => {
  const tag = (e.target.tagName || '').toUpperCase();
  const typing = tag === 'INPUT' || tag === 'TEXTAREA';
  if (!typing && e.code === 'Space') { spaceDown = true; if (!drag) canvas.style.cursor = 'grab'; }
  if (e.key === 'Shift') shiftDown = true;
  if (typing) return;

  if (e.key === 'Delete' || e.key === 'Backspace') { state.deleteSelected(); scheduleSolve(); e.preventDefault(); }
  else if (e.key === 'r' || e.key === 'R') { state.rotateSelected(); scheduleSolve(); }
  else if (e.key === 'Escape') { draft = null; state.pendingType = null; setActivePalette(null); updateHint(); }
  else if (e.key === 'Enter' && draft) { appendOrtho(draft.vertices, mouseWorld); finishWire(); }
  else if (e.ctrlKey && (e.key === 'z' || e.key === 'Z')) { state.undo(); scheduleSolve(); e.preventDefault(); }
  else if (e.ctrlKey && (e.key === 'y' || e.key === 'Y')) { state.redo(); scheduleSolve(); e.preventDefault(); }
  else if (e.key === '+' || e.key === '=') { zoomAt(1.15); }
  else if (e.key === '-' || e.key === '_') { zoomAt(1 / 1.15); }
  else if (e.key === '0' || e.key === 'f' || e.key === 'F') { fitView(); }
});
window.addEventListener('keyup', (e) => {
  if (e.code === 'Space') { spaceDown = false; if (!panning) canvas.style.cursor = 'default'; }
  if (e.key === 'Shift') { shiftDown = false; updateHint(); }
});

function zoomAt(factor) {
  const cx = view.w / 2, cy = view.h / 2;
  const before = toWorld({ x: cx, y: cy });
  cam.scale = Math.min(6, Math.max(0.15, cam.scale * factor));
  cam.x = cx - before.x * cam.scale;
  cam.y = cy - before.y * cam.scale;
}

function fitView() {
  const pts = [];
  for (const c of state.components) pts.push(...pinPositions(c));
  for (const w of state.wires) pts.push(...w.vertices);
  if (!pts.length) { cam.x = view.w / 2; cam.y = view.h / 2; cam.scale = 1; return; }
  const minX = Math.min(...pts.map((p) => p.x)) - 60;
  const maxX = Math.max(...pts.map((p) => p.x)) + 60;
  const minY = Math.min(...pts.map((p) => p.y)) - 60;
  const maxY = Math.max(...pts.map((p) => p.y)) + 60;
  const sx = view.w / (maxX - minX);
  const sy = view.h / (maxY - minY);
  cam.scale = Math.min(3, Math.max(0.2, Math.min(sx, sy)));
  cam.x = view.w / 2 - ((minX + maxX) / 2) * cam.scale;
  cam.y = view.h / 2 - ((minY + maxY) / 2) * cam.scale;
}

// ---------- 面板按钮 ----------
document.querySelectorAll('.palette-item').forEach((btn) => {
  btn.addEventListener('click', () => {
    state.pendingType = btn.dataset.type;
    try {
      state.pendingParams = btn.dataset.params ? JSON.parse(btn.dataset.params) : null;
    } catch { state.pendingParams = null; }
    state.tool = 'select';
    draft = null;
    setActiveTool('select');
    setActivePalette(btn.dataset.type);
    updateHint();
  });
});
// 分析域切换 / 频率·时间改动 → 立刻重算
['domain-sel', 'freq-in', 'tstop-in', 'nsteps-in'].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', () => scheduleSolve());
});
// 「给条件反解」面板的按钮（容器在 index.html 的「代数参考值」里）
const condAddBtn = document.getElementById('cond-add');
const condRunBtn = document.getElementById('cond-run');
if (condAddBtn) condAddBtn.addEventListener('click', () => addCondition());
if (condRunBtn) condRunBtn.addEventListener('click', () => runConstraints());

// 学习文档卡片
const learnModal = document.getElementById('learn-modal');
const learnBody = document.getElementById('learn-body');
let learnActive = (DOCS[0] && DOCS[0].id) || '';
function openLearn() {
  if (!learnModal) return;
  learnModal.style.display = 'flex';
  renderLearn(learnBody, learnActive);
  renderTexIn(learnBody);
}
if (learnModal) {
  const btn = document.getElementById('btn-learn');
  if (btn) btn.addEventListener('click', openLearn);
  const cl = document.getElementById('learn-close');
  if (cl) cl.addEventListener('click', () => { learnModal.style.display = 'none'; });
  learnModal.addEventListener('click', (ev) => {
    if (ev.target === learnModal) learnModal.style.display = 'none';
    const nav = ev.target.closest && ev.target.closest('[data-learn]');
    if (nav) {
      learnActive = nav.dataset.learn;
      renderLearn(learnBody, learnActive);
      renderTexIn(learnBody);
    }
  });
}

// 扫频按钮：10 Hz ~ 100 kHz 做频率响应
const sweepBtn = document.getElementById('sweep-btn');
if (sweepBtn) {
  sweepBtn.addEventListener('click', () => {
    if (!client.ready) return;
    sweepBtn.textContent = '扫频中…';
    client.sweep(ARCHIVE, state.toNetlist(pinPositions), 10, 1e5, 61, 'reactive');
    setTimeout(() => { sweepBtn.textContent = '扫频（10 Hz ~ 100 kHz）'; }, 1500);
  });
}
document.querySelectorAll('.tool-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    state.tool = btn.dataset.tool;
    state.pendingType = null;
    draft = null;
    setActiveTool(btn.dataset.tool);
    setActivePalette(null);
    updateHint();
  });
});
function setActiveTool(tool) {
  document.querySelectorAll('.tool-btn').forEach((b) => b.classList.toggle('active', b.dataset.tool === tool));
}
function setActivePalette(type) {
  document.querySelectorAll('.palette-item').forEach((b) => b.classList.toggle('active', b.dataset.type === type));
}

// 防御式绑定：任一元素缺失也不至于中断整个初始化
const onBtn = (id, fn) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('click', fn);
  else console.warn('[ElectricTools] 缺少按钮元素：', id);
};

onBtn('btn-undo', () => { state.undo(); scheduleSolve(); });
onBtn('solve-btn', () => runCompute());        // 一键求解（常驻按钮）onBtn('btn-redo', () => { state.redo(); scheduleSolve(); });
onBtn('btn-rotate', () => { state.rotateSelected(); scheduleSolve(); });
onBtn('btn-delete', () => { state.deleteSelected(); scheduleSolve(); });
onBtn('btn-clear', () => { state.clear(); scheduleSolve(); });
onBtn('btn-fit', () => fitView());
onBtn('btn-zoom-in', () => zoomAt(1.2));
onBtn('btn-zoom-out', () => zoomAt(1 / 1.2));
onBtn('btn-archive-save', () => saveArchiveWithName());
onBtn('btn-archive-saveas', () => saveArchiveAs());
onBtn('btn-archive-new', () => newArchive());
onBtn('btn-archive-delete', () => deleteArchive());
const archiveSel = document.getElementById('archive-select');
if (archiveSel) {
  archiveSel.addEventListener('change', (e) => { if (e.target.value) openArchive(e.target.value); });
}
onBtn('btn-ai-toggle', () => {
  const app = document.getElementById('app');
  app.classList.toggle('hide-ai');
  setTimeout(resize, 60);
});

// ---------- 存档（图 + 结果 + 聊天记录，同一个文件） ----------
let archiveTimer = null;

// 通用输入/确认弹窗：优先用页面内弹窗，避免依赖浏览器原生 prompt/confirm
// （原生对话框在某些浏览器/被“阻止更多对话框”后会被静默拦截，表现为“点了没反应”）
function askText(opts = {}) {
  const { title = '输入', value = '', okText = '确定', confirmOnly = false } = opts;
  const mask = document.getElementById('prompt-modal');
  const input = document.getElementById('prompt-input');
  const msg = document.getElementById('prompt-msg');
  const okBtn = document.getElementById('prompt-ok');
  const cancelBtn = document.getElementById('prompt-cancel');
  const closeBtn = document.getElementById('prompt-close');
  const titleEl = document.getElementById('prompt-title');
  if (!mask || !input || !okBtn) {
    // 兜底：弹窗标记缺失时退回原生对话框
    return Promise.resolve(confirmOnly ? (window.confirm(title) ? '' : null) : window.prompt(title, value));
  }

  if (titleEl) titleEl.textContent = title;
  okBtn.textContent = okText;
  input.value = value || '';
  input.style.display = confirmOnly ? 'none' : '';
  if (msg) msg.textContent = '';
  mask.style.display = 'flex';
  if (!confirmOnly) setTimeout(() => { input.focus(); input.select(); }, 0);

  return new Promise((resolve) => {
    let done = false;
    const finish = (val) => {
      if (done) return;
      done = true;
      mask.style.display = 'none';
      okBtn.removeEventListener('click', onOk);
      if (cancelBtn) cancelBtn.removeEventListener('click', onCancel);
      if (closeBtn) closeBtn.removeEventListener('click', onCancel);
      input.removeEventListener('keydown', onKey);
      mask.removeEventListener('mousedown', onMask);
      resolve(val);
    };
    const onOk = () => finish(confirmOnly ? '' : input.value);
    const onCancel = () => finish(null);
    const onKey = (e) => {
      if (e.key === 'Enter') { e.preventDefault(); onOk(); }
      else if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
    };
    const onMask = (e) => { if (e.target === mask) onCancel(); };
    okBtn.addEventListener('click', onOk);
    if (cancelBtn) cancelBtn.addEventListener('click', onCancel);
    if (closeBtn) closeBtn.addEventListener('click', onCancel);
    input.addEventListener('keydown', onKey);
    mask.addEventListener('mousedown', onMask);
  });
}

// 确认对话框（返回 true/false）
function askConfirm(message, okText = '确定') {
  return askText({ title: message, value: '', okText, confirmOnly: true }).then((v) => v !== null);
}

async function fetchArchives() {
  try {
    const r = await fetch('/api/archives');
    return (await r.json()).archives || [];
  } catch { return []; }
}
async function fetchArchive(name) {
  try {
    const r = await fetch('/api/archive?name=' + encodeURIComponent(name));
    return await r.json();
  } catch { return {}; }
}
async function saveArchive(name) {
  const target = name || ARCHIVE;
  if (!target) return null;
  try {
    const r = await fetch('/api/archive/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: target, canvas: state.serialize(), results, annotations: { node_notes: nodeLabels } })
    });
    const d = await r.json();
    updateArchivePath(d.dir || d.path);
    return d;
  } catch (e) { showError('保存存档失败：' + e.message); return null; }
}
// 保存：先让用户确认/输入文件名（默认当前名），可改名保存
async function saveArchiveWithName() {
  const input = await askText({ title: '保存文件名（可直接修改）', value: ARCHIVE || '未命名', okText: '保存' });
  if (input === null) return;                 // 用户取消
  const name = input.trim();
  if (!name) {
    hint.textContent = '文件名不能为空';
    setTimeout(updateHint, 1500);
    return;
  }

  if (name !== ARCHIVE) {
    // 目标名已被其它存档占用？先确认覆盖
    const list = await fetchArchives();
    if (list.some((a) => a.name === name) && !(await askConfirm(`已存在存档「${name}」，用当前内容覆盖它？`, '覆盖'))) return;

    // 重命名既有存档，保留聊天记录等其它模块；否则直接以新名保存
    let finalName = name;
    if (ARCHIVE) {
      try {
        const r = await fetch('/api/archive/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: ARCHIVE, new_name: name })
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const d = await r.json();
        if (d && d.name) finalName = d.name;    // 采用后端规范化后的名字
      } catch (e) { showError('重命名存档失败：' + e.message); }
    }
    ARCHIVE = finalName;
    localStorage.setItem('et.archive', ARCHIVE);
    updateArchiveLabel();
  }

  await saveArchive();
  await refreshArchiveSelect(ARCHIVE);
  hint.textContent = `已保存「${ARCHIVE}」`;
  setTimeout(updateHint, 1500);
}

function scheduleArchiveSave() {
  clearTimeout(archiveTimer);
  archiveTimer = setTimeout(() => saveArchive(), 1200);
}
function escAttr(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
async function refreshArchiveSelect(selected) {
  const sel = document.getElementById('archive-select');
  if (!sel) return;
  const list = await fetchArchives();
  const cur = selected || ARCHIVE;
  sel.innerHTML = list.length
    ? list.map((a) => `<option value="${escAttr(a.name)}" title="图 ${a.components} · 聊天 ${a.messages}" ${a.name === cur ? 'selected' : ''}>${escAttr(a.name)}</option>`).join('')
    : '<option value="">无存档</option>';
}
function updateArchiveLabel() {
  const el = document.getElementById('ai-session');
  if (el) el.textContent = '存档：' + (ARCHIVE || '未命名');
}
function updateArchivePath(p) {
  const el = document.getElementById('rec-path');
  if (el && p) { el.textContent = '存档目录：' + p; el.title = p; }
}

async function openArchive(name) {
  if (!name) return;
  // 切换到别的存档前，先把当前存档保存好（避免丢内容）
  if (ARCHIVE && ARCHIVE !== name && (state.components.length || state.wires.length)) {
    await saveArchive(ARCHIVE);
  }
  ARCHIVE = name;
  localStorage.setItem('et.archive', name);

  const doc = await fetchArchive(name);
  const canvas = doc.canvas || {};
  if ((canvas.components || []).length) {
    state.load(canvas);
  } else {
    state.clear();
    seedDivider();
  }
  results = doc.results || null;                 // 恢复「结果」
  nodeLabels = (doc.annotations && doc.annotations.node_notes) || {};   // 恢复「自定义节点名」
  refreshSidebar();
  aiPanel.setNodes(results && results.node_order ? results.node_order : []);
  aiPanel.restore((doc.conversation && doc.conversation.messages) || []);   // 恢复「聊天记录」
  showProbe(null);
  updateArchiveLabel();
  await refreshArchiveSelect(name);
  fitView();
  scheduleSolve();
  hint.textContent = `已打开存档「${name}」`;
  setTimeout(updateHint, 1500);
}

async function newArchive() {
  const n = await askText({ title: '新建存档名', value: '未命名-' + new Date().toISOString().slice(5, 10), okText: '新建' });
  if (n === null || !n.trim()) return;
  if (ARCHIVE) await saveArchive(ARCHIVE);
  ARCHIVE = n.trim();
  localStorage.setItem('et.archive', ARCHIVE);
  state.clear();
  results = null;
  nodeLabels = {};
  aiPanel.clear();
  showProbe(null);
  seedDivider();
  refreshSidebar();
  updateArchiveLabel();
  await saveArchive();
  await refreshArchiveSelect(ARCHIVE);
  fitView();
  scheduleSolve();
}

async function saveArchiveAs() {
  const n = await askText({ title: '另存为（存档名）', value: (ARCHIVE || '未命名') + '-副本', okText: '另存为' });
  if (n === null || !n.trim()) return;
  ARCHIVE = n.trim();
  localStorage.setItem('et.archive', ARCHIVE);
  await saveArchive();
  updateArchiveLabel();
  await refreshArchiveSelect(ARCHIVE);
  hint.textContent = `已另存为「${ARCHIVE}」`;
  setTimeout(updateHint, 1500);
}

async function deleteArchive() {
  if (!ARCHIVE) return;
  if (!(await askConfirm(`删除存档「${ARCHIVE}」？该操作不可恢复。`, '删除'))) return;
  try {
    await fetch('/api/archive/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: ARCHIVE })
    });
  } catch { /* ignore */ }
  localStorage.removeItem('et.archive');
  ARCHIVE = '';
  await boot();
}

// ---------- 启动 ----------
state.onChange(() => refreshSidebar());
applySavedWidths();
setupResizers();
setupSettingsUI();
resize();
client.connect();
updateHint();
refreshSidebar();
showProbe(null);
loop();
boot();

async function boot() {
  await loadConfig();
  const list = await fetchArchives();
  let name = ARCHIVE;
  if (!name || !list.some((a) => a.name === name)) {
    name = list.length ? list[0].name : '';
  }
  if (!name) {
    ARCHIVE = '未命名';
    localStorage.setItem('et.archive', ARCHIVE);
    state.clear();
    nodeLabels = {};
    seedDivider();
    updateArchiveLabel();
    await saveArchive();
    await refreshArchiveSelect(ARCHIVE);
    fitView();
    scheduleSolve();
    return;
  }
  await openArchive(name);
}

// 预置分压电路（首次体验）
function seedDivider() {
  state.addComponent('vsource', 200, 300);   // p0=(200,270)+  p1=(200,330)-
  state.addComponent('resistor', 350, 270);  // p0=(320,270)   p1=(380,270)
  state.addComponent('resistor', 350, 400);  // p0=(320,400)   p1=(380,400)
  state.addComponent('ground', 200, 400);
  state.addWire([{ x: 200, y: 270 }, { x: 320, y: 270 }]);
  state.addWire([{ x: 380, y: 270 }, { x: 430, y: 270 }, { x: 430, y: 400 }, { x: 380, y: 400 }]);
  state.addWire([{ x: 320, y: 400 }, { x: 200, y: 400 }]);
  state.addWire([{ x: 200, y: 400 }, { x: 200, y: 330 }]);
  state.selection = null;
  fitView();
}
