"""2.7：R5 留空、**不给任何条件** → 端口等效算法直接算出 R5。"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_r5.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app.analysis import STORE, analyze
from solver.app.models import Component, Pin, Schematic, SolveRequest, Wire, Junction

PINS = {"resistor": [("p0", -30, 0), ("p1", 30, 0)],
        "vsource": [("p0", 0, -30), ("p1", 0, 30)],
        "isource": [("p0", 0, -30), ("p1", 0, 30)],
        "ground": [("p0", 0, 0)]}
P = os.path.join(ROOT, "storage", "circuits", "电工与电子2.7")
cv = json.load(open(os.path.join(P, "canvas.json"), encoding="utf-8"))


def build(with_note: bool):
    comps = []
    for c in cv["components"]:
        r = math.radians(c.get("rotation") or 0)
        cs, sn = math.cos(r), math.sin(r)
        comps.append(Component(id=c["id"], type=c["type"], value=c.get("value"), symbol=c.get("symbol"),
                               rotation=c.get("rotation") or 0, x=c["x"], y=c["y"],
                               pins=[Pin(name=n, x=c["x"] + dx * cs - dy * sn, y=c["y"] + dx * sn + dy * cs)
                                     for n, dx, dy in PINS[c["type"]]]))
    notes = [{"key": n["anchor"], "kind": n["kind"], "value": n["value"]} for n in (cv.get("notes") or [])]
    return Schematic(components=comps, wires=[Wire(**w) for w in cv["wires"]],
                     junctions=[Junction(**j) for j in cv["junctions"]],
                     conditions=notes if with_note else [])


for with_note in (False, True):
    label = "带标注 I(R5)=1A" if with_note else "**不给任何条件**"
    sch = build(with_note)
    STORE.set_schematic("r5", sch)
    res = analyze(SolveRequest(session_id="r5", schematic=sch, mode="both"), True)
    cr = res.constraint_result or {}
    p(f"\n===== {label} =====")
    if cr.get("error"):
        p("  反解: X", cr["error"][:120])
    sols = (cr.get("solutions") or [])
    if sols:
        p("  结果:", {k: f"{v['value']}{v['unit']}" for k, v in (sols[0].get("values") or {}).items()},
          " 方法:", cr.get("method", "条件反解"))
    p("  诊断:", [d.code for d in res.diagnostics])
    p("  节点:", {n: (None if res.nodes[n].voltage is None else round(res.nodes[n].voltage, 4))
                  for n in res.node_order})
    p("  支路:", {b.component: (None if b.current is None else round(b.current, 4)) for b in res.branches})
    for st in (cr.get("steps") or []):
        p("    ·", st.get("title"), "|", (st.get("latex") or ""))
