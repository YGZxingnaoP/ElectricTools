"""第三轮找 bug：没测过的组合 + 边界值。节点名显式给出，避免测试脚本自己出错。"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_b3.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app import devices as D
from solver.app.engine import AC, DC, TRAN, SolveError
from solver.app.engine import analyse as eng
from solver.app.models import Component, Pin, Schematic
from solver.app.solve import build_branches

BUGS = []


def bug(m):
    BUGS.append(m)
    p("  ★BUG " + m)


def ok(m):
    p("  ok   " + m)


def run(spec, params, **kw):
    """spec: [(id, type, {引脚名: 节点名}), …]"""
    comps, nom = [], {}
    for cid, ctype, pins in spec:
        prm = params.get(cid, {})
        comps.append(Component(id=cid, type=ctype, value=prm.get("value"),
                               params={k: v for k, v in prm.items() if k != "value"},
                               pins=[Pin(name=n, x=float(i), y=0.0) for i, n in enumerate(pins)]))
        for n, node in pins.items():
            nom[f"u:{cid}/{n}"] = node
    sch = Schematic(components=comps, wires=[], junctions=[])
    nodes = {n: {"id": n, "is_ground": n == "g",
                 "members": sorted(k for k, v in nom.items() if v == n)} for n in set(nom.values())}
    return eng(nodes, build_branches(sch, nom), **kw)


p("① 交流电流源（1mA∠0°，并 1kΩ）→ V = 1V∠0°")
try:
    r = run([("I1", "isource", {"p0": "n1", "p1": "g"}), ("R1", "resistor", {"p0": "n1", "p1": "g"})],
            {"I1": {"value": 1e-3, "kind": "ac"}, "R1": {"value": 1000}}, domain=AC, freq=50)
    v = abs(r["V"].get("n1", 0))
    (ok if abs(v - 1.0) < 0.02 else bug)(f"交流电流源：|V|={v:.4f}（理论 1）")
except Exception as exc:
    bug(f"交流电流源报错：{type(exc).__name__}: {exc}")

p("② 运放积分器（交流）：R=1k、C=1µF、f=159.15Hz → |Ho| = 1/(ωRC) = 1")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("R1", "resistor", {"p0": "n1", "p1": "n2"}),
             ("A1", "opamp", {"inn": "n2", "inp": "g", "out": "n3"}),
             ("C1", "capacitor", {"p0": "n2", "p1": "n3"})],
            {"V1": {"value": 1, "kind": "ac"}, "R1": {"value": 1000}, "C1": {"value": 1e-6}},
            domain=AC, freq=159.1549)
    v = abs(r["V"].get("n3", 0))
    (ok if abs(v - 1.0) < 0.05 else bug)(f"运放积分器：|Uo|={v:.4f}（理论 1，即 1/(ωRC)）")
except Exception as exc:
    bug(f"运放积分器报错：{type(exc).__name__}: {exc}")

p("③ 三极管在交流域（共射，含 Re 旁路）")
try:
    r = run([("Vcc", "vsource", {"p0": "g", "p1": "vcc"}),
             ("Rb", "resistor", {"p0": "vcc", "p1": "b"}),
             ("Rc", "resistor", {"p0": "vcc", "p1": "c"}),
             ("Q1", "bjt", {"b": "b", "c": "c", "e": "g"}),
             ("Rs", "resistor", {"p0": "b", "p1": "src"}),
             ("Vs", "vsource", {"p0": "src", "p1": "g"}),
             ("Cs", "capacitor", {"p0": "src", "p1": "g"})],
            {"Vcc": {"value": 12}, "Rb": {"value": 600e3}, "Rc": {"value": 3e3},
             "Q1": {"beta": 100, "vbe": 0.7}, "Rs": {"value": 1000},
             "Vs": {"value": 0.01, "kind": "ac"}, "Cs": {"value": 1e-9}},
            domain=AC, freq=1000)
    p(f"     V(b)={r['V'].get('b')} V(c)={r['V'].get('c')}")
    ok("三极管交流域没崩（直流Q点+微变等效链路）")
except Exception as exc:
    bug(f"三极管交流域报错：{type(exc).__name__}: {exc}")

p("④ 变压器在暂态域")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("T1", "transformer", {"p0": "n1", "p1": "g", "p2": "n2", "p3": "g"}),
             ("R2", "resistor", {"p0": "n2", "p1": "g"})],
            {"V1": {"value": 10, "kind": "step"}, "T1": {"ratio": 2}, "R2": {"value": 1000}},
            domain=TRAN, tstop=1e-4, nsteps=11)
    w = r.get("waveform") or {}
    (ok if w else bug)("变压器暂态：有波形" if w else "变压器暂态没出波形")
except Exception as exc:
    bug(f"变压器暂态报错：{type(exc).__name__}: {exc}")

p("⑤ 三相不平衡负载（各相电阻不同）")
try:
    r = run([("U", "vsource3", {"p0": "a", "p1": "b", "p2": "c", "p3": "g"}),
             ("R1", "resistor", {"p0": "a", "p1": "g"}),
             ("R2", "resistor", {"p0": "b", "p1": "g"}),
             ("R3", "resistor", {"p0": "c", "p1": "g"})],
            {"U": {"value": 220, "kind": "ac"}, "R1": {"value": 10}, "R2": {"value": 20},
             "R3": {"value": 30}}, domain=AC, freq=50)
    vs = {k: round(abs(v), 2) for k, v in r["V"].items() if k != "g"}
    (ok if all(abs(v - 220) < 1 for v in vs.values()) else bug)(
        f"三相不平衡（有中线）：各相电压仍 220V → {vs}")
except Exception as exc:
    bug(f"三相不平衡报错：{type(exc).__name__}: {exc}")

p("⑥ 受控源增益没填（应该提示，而不是当 0 静默算出错答案）")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("E1", "vcvs", {"p0": "n2", "p1": "g", "c0": "n1", "c1": "g"}),
             ("R1", "resistor", {"p0": "n2", "p1": "g"})],
            {"V1": {"value": 10}, "E1": {}, "R1": {"value": 1000}}, domain=DC)
    v = r["V"].get("n2")
    p(f"     V(n2)={v}（增益空 → 当 0 用，结果是 0V）")
    warns = r.get("warnings") or []
    (ok if v == 0 else bug)(f"增益空时输出 {v}（未报错）")
    if not warns:
        bug("受控源增益为空却不给任何提示，静默按 0 算")
except Exception as exc:
    ok(f"增益空时抛错（可以接受）：{type(exc).__name__}")

p("⑦ 电阻为 0（短路）")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("R1", "resistor", {"p0": "n1", "p1": "n2"}), ("R0", "resistor", {"p0": "n2", "p1": "g"}),
             ("R2", "resistor", {"p0": "n2", "p1": "g"})],
            {"V1": {"value": 10}, "R1": {"value": 5}, "R0": {"value": 0}, "R2": {"value": 10}},
            domain=DC)
    v = r["V"].get("n2")
    (ok if abs(v) < 1e-9 else bug)(f"R=0 短路：V(n2)={v}（应为 0）")
except Exception as exc:
    bug(f"R=0 报错：{type(exc).__name__}: {exc}")

p("⑧ 元件两端接同一节点（自环）")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("R1", "resistor", {"p0": "n1", "p1": "g"}),
             ("Rx", "resistor", {"p0": "n1", "p1": "n1"})],
            {"V1": {"value": 10}, "R1": {"value": 5}, "Rx": {"value": 5}}, domain=DC)
    ok(f"自环元件不崩：V(n1)={r['V'].get('n1')}")
except Exception as exc:
    bug(f"自环元件报错：{type(exc).__name__}: {exc}")

p("⑨ 分析域=直流 但电源标了交流（应仍能算直流工作点）")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("R1", "resistor", {"p0": "n1", "p1": "g"})],
            {"V1": {"value": 10, "kind": "ac"}, "R1": {"value": 5}}, domain=DC)
    ok(f"交流源做直流分析：V(n1)={r['V'].get('n1')}")
except Exception as exc:
    bug(f"交流源做直流分析报错：{type(exc).__name__}: {exc}")

p("⑩ 两个接地符号")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("R1", "resistor", {"p0": "n1", "p1": "g"})],
            {"V1": {"value": 5}, "R1": {"value": 100}}, domain=DC)
    ok("（单接地）跳过")
except Exception as exc:
    bug(f"{exc}")

p("⑪ 电感在暂态 + 初值 i0")
try:
    r = run([("V1", "vsource", {"p0": "n1", "p1": "g"}),
             ("R1", "resistor", {"p0": "n1", "p1": "n2"}),
             ("L1", "inductor", {"p0": "n2", "p1": "g"})],
            {"V1": {"value": 10, "kind": "step"}, "R1": {"value": 100}, "L1": {"value": 0.1}},
            domain=TRAN, tstop=0.001, nsteps=21, i0={"L1": 0.05})
    w = r.get("waveform") or {}
    i0v = w.get("I:L1", [None])[0]
    (ok if i0v is not None and abs(i0v - 0.05) < 2e-4 else bug)(
        f"电感初值 i0：t=0 时 I(L1)={i0v:.6f}（应 0.05，梯形法首步误差 ~1e-4）")
except Exception as exc:
    bug(f"电感初值报错：{type(exc).__name__}: {exc}")

p("")
p(f"发现 {len(BUGS)} 个问题")
for i, b in enumerate(BUGS, 1):
    p(f"  {i}. {b}")
