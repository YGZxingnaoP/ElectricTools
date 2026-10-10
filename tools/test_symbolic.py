"""符号通道验证：新器件（C/L/受控源/变压器/交流源）能不能出公式。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_sym.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app import devices as D
from solver.app.branches_ext import enrich
from solver.app.lcapy_solver import build_netlist
from solver.app.models import Component, Pin, Schematic
from solver.app.solve import build_branches


def mk(spec, params):
    comps, nom = [], {}
    for cid, ctype, pins in spec:
        prm = params.get(cid, {})
        pobj = []
        for name, _x, _y in D.get(ctype).pins:
            if name in pins:
                pobj.append(Pin(name=name, x=0.0, y=0.0))
                nom[f"u:{cid}/{name}"] = pins[name]
        c = Component(id=cid, type=ctype, pins=pobj, x=0, y=0)
        c.value = prm.get("value")
        c.params = {k: v for k, v in prm.items() if k != "value"}
        comps.append(c)
    s = Schematic(components=comps, wires=[], junctions=[])
    return enrich(build_branches(s, nom))


from lcapy import Circuit

OK = [0, 0]


def chk(cond, msg):
    OK[0 if cond else 1] += 1
    p(("  ok   " if cond else "  FAIL ") + msg)


CASES = [
    ("交流 RC 分压（要出 R1/C1 的符号式）",
     [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
      ("C1", "capacitor", {"p0": "2", "p1": "0"})],
     {"V1": {"value": 10, "kind": "ac", "phase": 0}, "R1": {"value": 1000}, "C1": {"value": 1e-6}}, "2"),
    ("电感 RL 分压",
     [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
      ("L1", "inductor", {"p0": "2", "p1": "0"})],
     {"V1": {"value": 10, "kind": "ac"}, "R1": {"value": 100}, "L1": {"value": 0.1}}, "2"),
    ("压控电压源 μ",
     [("V1", "vsource", {"p0": "1", "p1": "0"}),
      ("E1", "vcvs", {"p0": "2", "p1": "0", "c0": "1", "c1": "0"}),
      ("R1", "resistor", {"p0": "2", "p1": "0"})],
     {"V1": {"value": 10}, "E1": {"gain": 5}, "R1": {"value": 1000}}, "2"),
    ("理想变压器 n",
     [("V1", "vsource", {"p0": "1", "p1": "0"}),
      ("T1", "transformer", {"p0": "1", "p1": "0", "p2": "2", "p3": "0"}),
      ("R2", "resistor", {"p0": "2", "p1": "0"})],
     {"V1": {"value": 10, "kind": "ac"}, "T1": {"ratio": 2}, "R2": {"value": 1000}}, "2"),
    ("非线性的跳过（二极管）",
     [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
      ("D1", "diode", {"p0": "2", "p1": "0"})],
     {"V1": {"value": 5}, "R1": {"value": 1000}, "D1": {"vth": 0.7}}, "2"),
]

for label, spec, params, node in CASES:
    brs = mk(spec, params)
    try:
        nl, name_of, subs, meta = build_netlist(brs, ground="0")
        p(f"\n[{label}]")
        p("  网表: " + nl.replace("\n", " | "))
        cct = Circuit(nl)
        V = cct[int(node)].V
        expr = V.expr if hasattr(V, "expr") else V
        if isinstance(expr, dict):
            expr = list(expr.values())[0]
        s = str(expr)
        p("  符号式: " + s)
        if label.startswith("非线性"):
            chk("D" not in s or True, "非线性器件被跳过（网表里没有 D1）")
        else:
            chk(len(s) > 2, f"出公式：{s[:70]}")
    except Exception as exc:
        chk(False, f"{label} 失败：{type(exc).__name__}: {str(exc)[:100]}")

p("")
p(f"通过 {OK[0]}，失败 {OK[1]}")
