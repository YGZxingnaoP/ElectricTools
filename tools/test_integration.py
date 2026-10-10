"""集成验证：走完整 analyze() 流程（含旧存档回归 + 交流 + 暂态）。"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_int.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app.analysis import STORE, analyze
from solver.app.models import Component, Pin, Schematic, SolveRequest

OK = [0, 0]


def check(label, cond, extra=""):
    OK[0 if cond else 1] += 1
    p(("  ok   " if cond else "  FAIL ") + label + ("   " + extra if extra else ""))


def sch_of(spec):
    comps = []
    for cid, ctype, pins, val, prm in spec:
        comps.append(Component(id=cid, type=ctype, value=val, params=prm or {},
                               pins=[Pin(name=n, x=x, y=y) for n, x, y in pins]))
    return Schematic(components=comps, wires=[], junctions=[])


p("【旧存档回归（直流，走老路径）】")
base = os.path.join(ROOT, "storage", "circuits")
for name in sorted(os.listdir(base)):
    p_ = os.path.join(base, name, "canvas.json")
    if not os.path.exists(p_):
        continue
    cv = json.load(open(p_, encoding="utf-8"))
    from solver.app.models import Wire, Junction
    comps = []
    for c in cv["components"]:
        comps.append(Component(id=c["id"], type=c["type"], value=c.get("value"),
                               symbol=c.get("symbol"), rotation=c.get("rotation") or 0,
                               x=c["x"], y=c["y"],
                               pins=[Pin(**q) for q in c["pins"]] if c.get("pins") else []))
    # 若存档没存 pins，用旧几何重建（resistor/vsource/isource 三种）
    def pins_for(c):
        P = {"resistor": [("p0", -30, 0), ("p1", 30, 0)],
             "vsource": [("p0", 0, -30), ("p1", 0, 30)],
             "isource": [("p0", 0, -30), ("p1", 0, 30)],
             "ground": [("p0", 0, 0)]}
        r = math.radians(c.get("rotation") or 0)
        cs, sn = math.cos(r), math.sin(r)
        return [Pin(name=n, x=c["x"] + dx * cs - dy * sn, y=c["y"] + dx * sn + dy * cs)
                for n, dx, dy in P[c["type"]]]
    comps = [Component(id=c["id"], type=c["type"], value=c.get("value"), symbol=c.get("symbol"),
                       rotation=c.get("rotation") or 0, x=c["x"], y=c["y"], pins=pins_for(c))
             for c in cv["components"]]
    sch = Schematic(components=comps,
                    wires=[Wire(**w) for w in cv.get("wires", [])],
                    junctions=[Junction(**j) for j in cv.get("junctions", [])],
                    conditions=[{"key": n["anchor"], "kind": n["kind"], "value": n["value"]}
                                for n in (cv.get("notes") or [])])
    res = analyze(SolveRequest(session_id="t" + name, schematic=sch, mode="both"), True)
    got = {n: res.nodes[n].voltage for n in res.node_order}
    check(f"{name}: ok={res.ok} 节点={ {k: (None if v is None else round(v, 3)) for k, v in got.items()} }",
          res.ok, f"domain={res.domain}")

p("\n【交流：RC 分压（走新引擎）】")
sch = sch_of([("V1", "vsource", [("p0", 0, -30), ("p1", 0, 30)], 10, {"kind": "ac", "freq": 50}),
              ("R1", "resistor", [("p0", -30, 0), ("p1", 30, 0)], 1000, {}),
              ("C1", "capacitor", [("p0", -30, 0), ("p1", 30, 0)], 1e-6, {})])
# 接线：V1.p1—R1.p0，R1.p1—C1.p0，V1.p0—C1.p1（用重合点）
for c in sch.components:
    for q in c.pins:
        q.x, q.y = {"V1": {"p1": (0, 0), "p0": (0, 200)}, "R1": {"p0": (0, 0), "p1": (0, -100)},
                    "C1": {"p0": (0, -100), "p1": (0, 200)}}[c.id][q.name]
res = analyze(SolveRequest(session_id="ac1", schematic=sch, mode="both", domain="ac", freq=50), True)
n2 = next((n for n in res.node_order if n != res.nodes.get("0", None)), None)
vals = {n: res.nodes[n].phasor for n in res.node_order if res.nodes[n].phasor}
w = 2 * math.pi * 50
want = 10 / math.sqrt(1 + (w * 1000 * 1e-6) ** 2)
ph = [v for v in vals.values() if abs(v.rms - want) < 0.01]
check(f"域={res.domain} 相量={[(n, round(res.nodes[n].phasor.rms,4) if res.nodes[n].phasor else None) for n in res.node_order]}",
      res.domain == "ac" and bool(ph),
      f"理论有效值 {want:.4f}∠{math.degrees(-math.atan(w*1000*1e-6)):.2f}°")

p("\n【暂态：RC 阶跃（走新引擎，出波形）】")
sch = sch_of([("V1", "vsource", [("p0", 0, -30), ("p1", 0, 30)], 10, {"kind": "step"}),
              ("R1", "resistor", [("p0", -30, 0), ("p1", 30, 0)], 1000, {}),
              ("C1", "capacitor", [("p0", -30, 0), ("p1", 30, 0)], 1e-6, {})])
for c in sch.components:
    for q in c.pins:
        q.x, q.y = {"V1": {"p1": (0, 0), "p0": (0, 200)}, "R1": {"p0": (0, 0), "p1": (0, -100)},
                    "C1": {"p0": (0, -100), "p1": (0, 200)}}[c.id][q.name]
res = analyze(SolveRequest(session_id="tr1", schematic=sch, mode="numeric",
                           domain="tran", tstop=0.005, nsteps=101), True)
wv = res.waveform or {}
uk = "U:C1" if "U:C1" in wv else None
if uk:
    v1 = wv[uk][20]
    check(f"域={res.domain} 波形点数={len(wv['t'])} abs(U(C1))@1ms={abs(v1):.5f}",
          res.domain == "tran" and abs(abs(v1) - 6.32121) / 6.32121 < 0.005, "理论 6.32121")
else:
    check(f"域={res.domain} 波形键={list(wv)[:6]}", False, "没拿到电容电压波形")

p("\n【交流：RLC 串联谐振 + 功率】")
sch = sch_of([("V1", "vsource", [("p0", 0, -30), ("p1", 0, 30)], 1, {"kind": "ac", "freq": 5032.9}),
              ("R1", "resistor", [("p0", -30, 0), ("p1", 30, 0)], 10, {}),
              ("L1", "inductor", [("p0", -30, 0), ("p1", 30, 0)], 1e-3, {}),
              ("C1", "capacitor", [("p0", -30, 0), ("p1", 30, 0)], 1e-6, {})])
coords = {"V1": {"p1": (0, 0), "p0": (0, 300)}, "R1": {"p0": (0, 0), "p1": (0, -100)},
          "L1": {"p0": (0, -100), "p1": (0, -200)}, "C1": {"p0": (0, -200), "p1": (0, 300)}}
for c in sch.components:
    for q in c.pins:
        q.x, q.y = coords[c.id][q.name]
res = analyze(SolveRequest(session_id="rlc", schematic=sch, mode="both", domain="ac", freq=5032.9), True)
br = {b.component: b for b in res.branches}
i_rms = br["R1"].current
pw = br["R1"].power or {}
check(f"谐振电流 I(R1)={i_rms:.5f} A（理论 0.1）R 上 P={pw.get('p'):.4f} W（理论 0.1）",
      i_rms is not None and abs(i_rms - 0.1) < 1e-3 and abs((pw.get("p") or 0) - 0.1) < 1e-3)

p(f"\n通过 {OK[0]}，失败 {OK[1]}")
