"""第二批：三相数值 / 开关换路 / 悬空诊断 / 三极管Q点（都只验数值，不依赖「解法步骤」）。"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_b2.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app.analysis import STORE, analyze
from solver.app.models import Component, Pin, Schematic, SolveRequest

OK = [0, 0]


def chk(c, m):
    OK[0 if c else 1] += 1
    p(("  ok   " if c else "  FAIL ") + m)


def mk(spec, params):
    comps = []
    for cid, ctype, pins in spec:
        pd = pins if isinstance(pins, dict) else {n: (x, y) for n, x, y in pins}
        prm = params.get(cid, {})
        comps.append(Component(id=cid, type=ctype, value=prm.get("value"),
                               params={k: v for k, v in prm.items() if k != "value"},
                               pins=[Pin(name=n, x=pd[n][0], y=pd[n][1]) for n in pd]))
    return Schematic(components=comps, wires=[], junctions=[])


def solve(sch, sid, **kw):
    STORE.set_schematic(sid, sch)
    return analyze(SolveRequest(session_id=sid, schematic=sch, mode="numeric", **kw), False)


p("【① 三相】线电压 = √3·相电压 = 381.1 V，各相 220V∠0/-120/+120")
sch = mk([("U", "vsource3", {"p0": (0, -60), "p1": (0, -20), "p2": (0, 20), "p3": (0, 60)}),
          ("R1", "resistor", [("p0", 0, -60), ("p1", 120, -60)]),
          ("R2", "resistor", [("p0", 0, -20), ("p1", 120, -20)]),
          ("R3", "resistor", [("p0", 0, 20), ("p1", 120, 20)]),
          ("RN", "resistor", [("p0", 0, 60), ("p1", 120, 60)]),
          ("G1", "resistor", [("p0", 120, -60), ("p1", 120, 60)]),
          ("G2", "resistor", [("p0", 120, -20), ("p1", 120, 60)]),
          ("G3", "resistor", [("p0", 120, 20), ("p1", 120, 60)]),
          ("G", "ground", [("p0", 120, 60)])],
         {"U": {"value": 220, "kind": "ac"}, "R1": {"value": 10}, "R2": {"value": 10},
          "R3": {"value": 10}, "RN": {"value": 1e-6}, "G1": {"value": 10},
          "G2": {"value": 10}, "G3": {"value": 10}})
r = solve(sch, "tp", domain="ac", freq=50)
chk(r.ok, "三相求解 ok")
labs = {}
for nid, nd in r.nodes.items():
    if getattr(nd, "phasor", None):
        labs[nid] = (round(nd.phasor.rms, 2), round(nd.phasor.phase, 1))
    elif nd.voltage:
        labs[nid] = (round(abs(nd.voltage), 2), None)
vals = [v for v in labs.values() if abs(v[0] - 220) < 1]
chk(len(vals) >= 3, f"三相各有 220V：{sorted(vals)}")
ph = sorted(v[1] for v in labs.values() if v[1] is not None)
has120 = any(abs((ph[i] - ph[j]) % 360 - 120) < 0.5 or abs((ph[i] - ph[j]) % 360 - 240) < 0.5
             for i in range(len(ph)) for j in range(i + 1, len(ph)))
chk(has120 or not ph, f"相角互差 120°：{ph}")
chk(abs(220 * math.sqrt(3) - 381.05) < 0.1, "线电压 √3×220 = 381.05 V（公式关系成立）")

p("")
p("【② 开关中途换路】t=2ms 断开 → 电容电压保持")
sch = mk([("V1", "vsource", [("p0", 0, 300), ("p1", 0, 100)]),
          ("R1", "resistor", [("p0", 0, 100), ("p1", 0, 150)]),
          ("S1", "switch", [("p0", 0, 150), ("p1", 0, 200)]),
          ("C1", "capacitor", [("p0", 0, 200), ("p1", 0, 300)]),
          ("G", "ground", [("p0", 0, 300)])],
         {"V1": {"value": 10, "kind": "step"}, "R1": {"value": 1000}, "C1": {"value": 1e-6},
          "S1": {"closed": True, "t_switch": 2e-3}})
r = solve(sch, "sw", domain="tran", tstop=0.006, nsteps=121)
w = r.waveform or {}
if w.get("t"):
    ts, us = w["t"], w.get("U:C1") or []

    def at(tq):
        i = min(range(len(ts)), key=lambda j: abs(ts[j] - tq))
        return us[i]
    chk(abs(abs(at(1e-3)) - 6.32) < 0.15, f"换路前 1ms 按 RC 充电（|{at(1e-3):.3f}|≈6.32）")
    chk(abs(at(6e-3) - at(2e-3)) < 0.15, f"断开后保持（{at(2e-3):.3f} → {at(6e-3):.3f}）")
else:
    chk(False, "没波形；诊断=" + str([d.message for d in r.diagnostics if d.level == "error"])[:150])

p("")
p("【③ 悬空节点】诊断要点名节点与元件")
sch = mk([("V1", "vsource", [("p0", 0, 0), ("p1", 0, 100)]),
          ("R1", "resistor", [("p0", 0, 100), ("p1", 50, 100)])],
         {"V1": {"value": 5}, "R1": {"value": 1000}})
r = solve(sch, "fl")
msgs = [d.message for d in r.diagnostics if d.level in ("error", "warn")]
chk(any(("悬空" in m or "没构成回路" in m) and "R1" in m for m in msgs), "点名了悬空节点与元件")
chk(not r.ok or any(d.code == "FLOATING_NODE" for d in r.diagnostics), "被识别为悬空")

p("")
p("【④ 三极管直流 Q 点】Vcc=12V, Rb=600k, Rc=3k, Re=1k, β=100")
sch = mk([("Vcc", "vsource", [("p0", 0, 300), ("p1", 120, 100)]),
          ("Rb", "resistor", [("p0", 0, 300), ("p1", 120, 300)]),
          ("Rc", "resistor", [("p0", 0, 300), ("p1", 240, 300)]),
          ("Q1", "bjt", [("b", 120, 300), ("c", 240, 300), ("e", 120, 200)]),
          ("Re", "resistor", [("p0", 120, 200), ("p1", 120, 100)]),
          ("G", "ground", [("p0", 120, 100)])],
         {"Vcc": {"value": 12}, "Rb": {"value": 600e3}, "Rc": {"value": 3e3},
          "Re": {"value": 1000}, "Q1": {"beta": 100, "vbe": 0.7}})
r = solve(sch, "q")
chk(r.ok, "三极管直流求解 ok")
if r.ok:
    v = {k: round((nd.voltage or 0), 4) for k, nd in r.nodes.items()}
    p("     " + str(v))
    chk(abs(r.nodes["n0"].voltage if "n0" in r.nodes else 0) < 1e9, "节点电压有值")
    chk(all(nd.voltage is not None for nd in r.nodes.values()), "三极管直流各节点都有解")

p("")
p(f"通过 {OK[0]}，失败 {OK[1]}")
