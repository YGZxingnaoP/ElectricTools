// 纯逻辑测试：元件创建、吸附、命中检测、拓扑序列化（不依赖 DOM）
// 运行： node tools/logic_test.mjs
import { EditorState } from '../frontend/src/core/model.js';
import { pinPositions, snapPoint, hitComponent, hitWire, endpointOnWireInterior, orthoPath, connectionPoints } from '../frontend/src/core/geometry.js';
import { protectMath, restoreMath } from '../frontend/src/ui/mdMath.js';

let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) { pass++; console.log('  ok  -', msg); } else { fail++; console.log('  FAIL-', msg); } };

console.log('[1] 创建元件');
const s = new EditorState();
const r1 = s.addComponent('resistor', 100, 100);
ok(r1 && r1.id === 'R1', `电阻 id=${r1 && r1.id}`);
ok(Math.abs(r1.value - 1000) < 1e-9, `默认阻值 ${r1.value}`);
const v1 = s.addComponent('vsource', 300, 100);
ok(v1.id === 'V1', `电压源 id=${v1.id}`);
const g = s.addComponent('ground', 100, 300);
ok(g.id === 'GND1', `接地 id=${g.id}`);
ok(s.components.length === 3, `元件数 ${s.components.length}`);

console.log('[2] 引脚几何');
const rp = pinPositions(r1);
ok(rp.length === 2, '电阻 2 引脚');
ok(Math.abs(rp[0].x - 70) < 1e-9 && Math.abs(rp[1].x - 130) < 1e-9, `引脚 ${JSON.stringify(rp)}`);
const vp = pinPositions(v1);
ok(Math.abs(vp[0].y - 70) < 1e-9 && Math.abs(vp[1].y - 130) < 1e-9, '电压源引脚纵向');

console.log('[3] 旋转');
r1.rotation = 90;
const rp90 = pinPositions(r1);
ok(Math.abs(rp90[0].x - 100) < 1e-9 && Math.abs(rp90[0].y - 70) < 1e-9, `旋转90后引脚 ${JSON.stringify(rp90)}`);
r1.rotation = 0;

console.log('[4] 吸附');
const snapToPin = snapPoint(s, { x: 71, y: 101 });
ok(snapToPin.target.kind === 'pin', `近端子吸附 -> ${snapToPin.target.kind}`);
ok(Math.abs(snapToPin.point.x - 70) < 1e-9, '吸到端子坐标');
const snapGrid = snapPoint(s, { x: 403, y: 207 });
ok(snapGrid.target.kind === 'grid' && snapGrid.point.x === 400 && snapGrid.point.y === 210, `网格吸附 ${JSON.stringify(snapGrid.point)}`);

console.log('[5] 命中检测');
ok(hitComponent(s, { x: 100, y: 100 })?.id === 'R1', '命中电阻');
ok(hitComponent(s, { x: 250, y: 250 }) === null, '空白处不命中');

console.log('[6] 导线与 T 接');
const w = s.addWire([{ x: 130, y: 100 }, { x: 200, y: 100 }]);
ok(w && w.id === 'w1', `导线 id=${w && w.id}`);
ok(hitWire(s, { x: 165, y: 102 })?.id === 'w1', '命中导线');
ok(endpointOnWireInterior(s, { x: 165, y: 100 }, null) === true, '端点落在导线内部(T接)');
ok(endpointOnWireInterior(s, { x: 230, y: 100 }, null) === false, '端点不在导线上');

console.log('[7] 撤销 / 重做');
const n0 = s.components.length;
s.addComponent('resistor', 500, 500);
ok(s.components.length === n0 + 1, '新增后 +1');
s.undo();
ok(s.components.length === n0, '撤销后恢复');
s.redo();
ok(s.components.length === n0 + 1, '重做后 +1');

console.log('[8] 序列化');
const nl = s.toNetlist(pinPositions);
ok(Array.isArray(nl.components) && nl.components[0].pins.length === 2, '网表含引脚坐标');
ok(nl.components[0].pins[0].x === 70, '引脚坐标已解析为绝对值');

console.log('[9] 正交（90°）路由');
const p1 = orthoPath({ x: 0, y: 0 }, { x: 100, y: 40 });
ok(p1.length === 3, `斜向 -> 需折点，段数=${p1.length}`);
ok(p1[1].x === 100 && p1[1].y === 0, `先水平再垂直 折点=${JSON.stringify(p1[1])}`);
const p2 = orthoPath({ x: 0, y: 0 }, { x: 20, y: 90 });
ok(p2[1].x === 0 && p2[1].y === 90, `先垂直再水平 折点=${JSON.stringify(p2[1])}`);
const p3 = orthoPath({ x: 0, y: 0 }, { x: 0, y: 50 });
ok(p3.length === 2, '同轴 -> 无需折点');
const seg = (a, b) => Math.abs(a.x - b.x) < 1e-6 || Math.abs(a.y - b.y) < 1e-6;
ok(seg(p1[0], p1[1]) && seg(p1[1], p1[2]), '两段均为水平/垂直');

console.log('[10] 拐点也是节点');
const s2 = new EditorState();
s2.addWire([{ x: 0, y: 0 }, { x: 0, y: 100 }, { x: 100, y: 100 }]);
const cps = connectionPoints(s2);
const corner = cps.find((p) => p.x === 0 && p.y === 100);
ok(!!corner, '拐点已被登记为连接点');
ok(corner.kind === 'wire-corner', `拐点类型=${corner && corner.kind}`);
const snapCorner = snapPoint(s2, { x: 4, y: 103 });
ok(snapCorner.target.kind === 'wire-corner', `可吸附到拐点 -> ${snapCorner.target.kind}`);

console.log('[11] Markdown 公式保护');
const fakeRender = (tex, disp) => `[KATEX:${disp ? 'B' : 'I'}:${tex.trim()}]`;
{
  const r = protectMath('电压为 $V_{n1}=\\frac{R_2 V_1}{R_1+R_2}$ 伏', fakeRender);
  ok(r.stash.length === 1, `行内公式被提取，数量=${r.stash.length}`);
  ok(r.stash[0].startsWith('[KATEX:I'), `行内公式标记=${r.stash[0]}`);
  ok(r.text.includes('@@MATH0@@') && !r.text.includes('V_{n1}'), '原文已替换为占位符');
  const restored = restoreMath('结果：@@MATH0@@ 伏', r.stash);
  ok(restored.includes('[KATEX:I:') && restored.includes('\\frac'), '占位符已还原为渲染结果');
}
{
  const r = protectMath('$$\\sum I_k = 0$$', fakeRender);
  ok(r.stash.length === 1 && r.stash[0].startsWith('[KATEX:B'), '块级公式使用 displayMode');
}
{
  const r = protectMath('```\n$not_a_formula$\n```\n和 `$x$` 行内代码', fakeRender);
  ok(r.stash.length === 0, `代码块/行内代码中的 $ 不被当作公式（数量=${r.stash.length}）`);
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败`);
process.exit(fail ? 1 : 0);
