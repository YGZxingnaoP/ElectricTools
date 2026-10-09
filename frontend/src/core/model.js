// 编辑状态 + 快照式撤销/重做（docs/drawing-model.md §6）
import { COMPONENTS } from './geometry.js';

export class EditorState {
  constructor() {
    this.components = [];
    this.wires = [];
    this.junctions = [];
    this.selection = null;      // { kind:'component'|'wire'|'junction', id }
    this.tool = 'select';       // select | wire
    this.pendingType = null;    // 待放置元件类型
    this.undoStack = [];
    this.redoStack = [];
    this.listeners = [];
  }

  onChange(fn) { this.listeners.push(fn); }
  emit() { for (const fn of this.listeners) fn(this); }

  snapshot() {
    return JSON.stringify({
      components: this.components,
      wires: this.wires,
      junctions: this.junctions
    });
  }

  pushHistory() {
    this.undoStack.push(this.snapshot());
    if (this.undoStack.length > 200) this.undoStack.shift();
    this.redoStack.length = 0;
  }

  _restore(snap) {
    const d = JSON.parse(snap);
    this.components = d.components;
    this.wires = d.wires;
    this.junctions = d.junctions;
    this.selection = null;
    this.emit();
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(this.snapshot());
    this._restore(this.undoStack.pop());
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(this.snapshot());
    this._restore(this.redoStack.pop());
  }

  nextId(prefix) {
    const used = new Set([
      ...this.components.map((c) => c.id),
      ...this.wires.map((w) => w.id),
      ...this.junctions.map((j) => j.id)
    ]);
    // 按前缀独立计数（修正：原先用全局共享计数器导致 V1→V2、GND1→GND3、w1→w4）
    if (!this._seq) this._seq = {};
    let n = this._seq[prefix] || 0;
    let id;
    do { n += 1; id = `${prefix}${n}`; } while (used.has(id));
    this._seq[prefix] = n;
    return id;
  }

  addComponent(type, x, y) {
    const def = COMPONENTS[type];
    this.pushHistory();
    const comp = {
      id: this.nextId(def.prefix),
      type,
      x, y,
      rotation: 0,
      mirror: false,
      value: def.defValue,
      unit: def.unit
    };
    this.components.push(comp);
    this.selection = { kind: 'component', id: comp.id };
    this.emit();
    return comp;
  }

  addWire(vertices) {
    if (vertices.length < 2) return null;
    this.pushHistory();
    const w = { id: this.nextId('w'), vertices: vertices.map((v) => ({ x: v.x, y: v.y })) };
    this.wires.push(w);
    this.emit();
    return w;
  }

  addJunction(x, y) {
    const j = { id: this.nextId('j'), x, y };
    this.junctions.push(j);
    this.emit();
    return j;
  }

  getSelectedComponent() {
    if (this.selection?.kind === 'component') {
      return this.components.find((c) => c.id === this.selection.id) || null;
    }
    return null;
  }

  setValue(id, value) {
    const c = this.components.find((x) => x.id === id);
    if (!c) return;
    this.pushHistory();
    c.value = value;
    this.emit();
  }

  // 自定义位号 / 编号（唯一性校验）。返回 true 表示成功。
  renameComponent(oldId, newId) {
    const id = String(newId ?? '').trim();
    if (!id || id === oldId) return false;
    if (this.components.some((c) => c.id === id)) return false;   // 与其他元件重复
    const c = this.components.find((x) => x.id === oldId);
    if (!c) return false;
    this.pushHistory();
    c.id = id;
    if (this.selection?.kind === 'component' && this.selection.id === oldId) {
      this.selection = { kind: 'component', id };
    }
    this.emit();
    return true;
  }

  rotateSelected() {
    const c = this.getSelectedComponent();
    if (!c) return;
    this.pushHistory();
    c.rotation = ((c.rotation || 0) + 90) % 360;
    this.emit();
  }

  deleteSelected() {
    if (!this.selection) return;
    const { kind, id } = this.selection;
    this.pushHistory();
    if (kind === 'component') this.components = this.components.filter((c) => c.id !== id);
    else if (kind === 'wire') this.wires = this.wires.filter((w) => w.id !== id);
    else if (kind === 'junction') this.junctions = this.junctions.filter((j) => j.id !== id);
    this.selection = null;
    this.emit();
  }

  clear() {
    this.pushHistory();
    this.components = [];
    this.wires = [];
    this.junctions = [];
    this.selection = null;
    this.emit();
  }

  // 序列化给后端（几何，含引脚绝对坐标）
  toNetlist(pinPositions) {    return {
      components: this.components.map((c) => ({
        id: c.id,
        type: c.type,
        value: c.value,
        unit: c.unit,
        rotation: c.rotation,
        mirror: c.mirror,
        pins: pinPositions(c).map((p) => ({ name: p.name, x: p.x, y: p.y }))
      })),
      wires: this.wires.map((w) => ({
        id: w.id,
        vertices: w.vertices.map((v) => ({ x: v.x, y: v.y }))
      })),
      junctions: this.junctions.map((j) => ({ id: j.id, x: j.x, y: j.y }))
    };
  }

  // 可编辑状态的完整快照（用于 localStorage / 会话记录，含 x,y，可直接 load 回来）
  serialize() {
    return {
      components: JSON.parse(JSON.stringify(this.components)),
      wires: JSON.parse(JSON.stringify(this.wires)),
      junctions: JSON.parse(JSON.stringify(this.junctions))
    };
  }

  load(obj) {
    this.components = obj.components || [];
    this.wires = obj.wires || [];
    this.junctions = obj.junctions || [];
    this.selection = null;
    this.emit();
  }
}
