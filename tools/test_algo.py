"""端口等效 / 反解数值正确性（原「解法步骤」已删，这里只验数值）。"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_algo.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app.analysis import STORE, analyze
from solver.app.models import Component, Junction, Pin, Schematic, SolveRequest, Wire

OK = [0, 0]


def chk(c, m):
    OK[0 if c else 1] += 1
    p(("  ok   " if c else "  FAIL ") + m)


# ① 电工与电子2.7：R5 留空 → 端口等效反解应为 2 Ω
P = os.path.join(ROOT, "storage", "circuits", "电工与电子2.7")
cv = json.load(open(os.path.join(P, "canvas.json"), encoding="utf-8"))
PINS = {"resistor": [("p0", -30, 0), ("p1", 30, 0)], "vsource": [("p0", 0, -30), ("p1", 0, 30)],
        "isource": [("p0", 0, -30), ("p1", 0, 30)], "ground": [("p0", 0, 0)]}
comps = []
for c in cv["components"]:
    rr = math.radians(c.get("rotation") or 0)
    cs, sn = math.cos(rr), math.sin(rr)
    comps.append(Component(id=c["id"], type=c["type"], value=c.get("value"), symbol=c.get("symbol"),
                           rotation=c.get("rotation") or 0, x=c["x"], y=c["y"],
                           pins=[Pin(name=n, x=c["x"] + dx * cs - dy * sn, y=c["y"] + dx * sn + dy * cs)
                                 for n, dx, dy in PINS[c["type"]]]))
sch = Schematic(components=comps, wires=[Wire(**w) for w in cv["wires"]],
                junctions=[Junction(**j) for j in cv["junctions"]], conditions=[])
STORE.set_schematic("r5x", sch)
r = analyze(SolveRequest(session_id="r5x", schematic=sch, mode="both"), True)
cr = r.constraint_result or {}
vals = (cr.get("solutions") or [{}])[0].get("values", {})
chk(abs((vals.get("R5", {}).get("value") or 0) - 2.0) < 1e-9,
    f"无条件下反解 R5 = {vals.get('R5', {}).get('value')} Ω（应 2）")
chk(r.ok, "代入反解值后重算 ok")
chk(all(nd.voltage is not None for nd in r.nodes.values()), "所有节点电压都解出来了（无 None）")
chk(abs(r.branches[0].current) > 0 if r.branches else False, "支路电流有值")

# ② 给了条件也用同一个引擎（R5=3Ω 时应该 V(n4)=? 由引擎自洽）
sch2 = sch.model_copy(deep=True)
r2 = analyze(SolveRequest(session_id="r5x", schematic=sch2, mode="numeric"), False)
chk(r2.ok, "同一电路纯数值求解 ok")

# ③ 端口等效：电容未知 → 不应瞎填一个电阻值
from solver.app.models import Pin as P2


def mk(spec, params):
    cs, nom = [], {}
    for cid, ctype, pins in spec:
        prm = params.get(cid, {})
        cs.append(Component(id=cid, type=ctype, value=prm.get("value"),
                            params={k: v for k, v in prm.items() if k != "value"},
                            pins=[Pin(name=n, x=x, y=y) for n, x, y in pins]))
    return Schematic(components=cs, wires=[], junctions=[])


sch3 = mk([("V1", "vsource", [("p0", 0, 0), ("p1", 0, 200)]),
           ("R1", "resistor", [("p0", 0, 0), ("p1", 0, -100)]),
           ("C1", "capacitor", [("p0", 0, -100), ("p1", 0, 200)])],
          {"V1": {"value": 10}, "R1": {"value": 1000}})
STORE.set_schematic("capx", sch3)
r3 = analyze(SolveRequest(session_id="capx", schematic=sch3, mode="numeric"), False)
cvals = (r3.constraint_result or {}).get("solutions") or []
got = (cvals[0].get("values", {}) if cvals else {}).get("C1")
chk(got is None or got.get("unit") == "F", f"电容未知时没被当成电阻反解（得到 {got}）")

p("")
p(f"通过 {OK[0]}，失败 {OK[1]}")
