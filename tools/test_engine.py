"""引擎验证（修正期望值版）：每条都用理论值对照。"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_eng.txt"), "w", encoding="utf-8")

from solver.app import devices as D
from solver.app.engine import AC, DC, TRAN, analyse
from solver.app.models import Component, Pin, Schematic
from solver.app.solve import build_branches

OK = [0, 0]


def mk(spec, params=None):
    comps, nom = [], {}
    for cid, ctype, pins in spec:
        prm = (params or {}).get(cid, {})
        dev = D.get(ctype)
        pobj = []
        for name, _dx, _dy in dev.pins:
            if name in pins:
                pobj.append(Pin(name=name, x=0.0, y=0.0))
                nom[f"u:{cid}/{name}"] = pins[name]
        c = Component(id=cid, type=ctype, pins=pobj, x=0, y=0)
        c.value = prm.get("value")
        c.params = {k: v for k, v in prm.items() if k != "value"}
        comps.append(c)
    return Schematic(components=comps, wires=[], junctions=[]), nom


def nodes_of(nom):
    out = {}
    for nid in set(nom.values()):
        out[nid] = {"id": nid, "is_ground": nid == "0",
                    "members": sorted(k for k, v in nom.items() if v == nid)}
    return out


def _fmt(x):
    c = complex(x)
    if abs(c.imag) > 1e-9:
        return f"{abs(c):.5g}∠{math.degrees(math.atan2(c.imag, c.real)):.2f}°"
    return f"{c.real:.6g}"


def run(label, spec, params, domain=DC, expect=None, freq=50.0, key="V", tol=3e-3, **kw):
    sch, nom = mk(spec, params)
    nodes = nodes_of(nom)
    try:
        res = analyse(nodes, build_branches(sch, nom), domain=domain, freq=freq, **kw)
    except Exception as exc:
        OK[1] += 1
        print(f"  FAIL {label:24s} X {type(exc).__name__}: {str(exc)[:70]}")
        return None
    okall, lines = True, []
    for k, want in (expect or {}).items():
        g = res[key].get(k)
        wc = complex(want[0] * math.cos(math.radians(want[1])), want[0] * math.sin(math.radians(want[1]))) \
            if isinstance(want, tuple) else complex(want)
        err = abs(complex(g) - wc) / max(1e-12, abs(wc))
        if err > tol:
            okall = False
        lines.append(f"{k}={_fmt(g)}(理论 {_fmt(wc)})")
    OK[0 if okall else 1] += 1
    print(("  ok   " if okall else "  FAIL ") + f"{label:24s} " + "  ".join(lines))
    return res


print("【直流】")
run("分压 10V→5V", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                 ("R2", "resistor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "R1": {"value": 5}, "R2": {"value": 5}}, DC, {"2": 5.0})
run("电感直流=短路", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                 ("L1", "inductor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "R1": {"value": 5}, "L1": {"value": 0.1}}, DC, {"2": 0.0})
run("电容直流=开路", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                 ("R2", "resistor", {"p0": "2", "p1": "0"}), ("C1", "capacitor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "R1": {"value": 5}, "R2": {"value": 5}, "C1": {"value": 1e-6}}, DC, {"2": 5.0})
run("VCVS μ=5", [("V1", "vsource", {"p0": "1", "p1": "0"}),
                ("E1", "vcvs", {"p0": "2", "p1": "0", "c0": "1", "c1": "0"}),
                ("R1", "resistor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "E1": {"gain": 5}, "R1": {"value": 1000}}, DC, {"2": 50.0})
run("VCCS gm=0.1S", [("V1", "vsource", {"p0": "1", "p1": "0"}),
                    ("G1", "vccs", {"p0": "2", "p1": "0", "c0": "1", "c1": "0"}),
                    ("R1", "resistor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "G1": {"gain": 0.1}, "R1": {"value": 1000}}, DC, {"2": -1000.0})
run("CCCS β=2（i_ctrl=-2A）", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R0", "resistor", {"p0": "1", "p1": "0"}),
                          ("F1", "cccs", {"p0": "2", "p1": "0"}), ("R1", "resistor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "R0": {"value": 5}, "F1": {"gain": 2, "control": "V1"}, "R1": {"value": 1000}},
    DC, {"2": 4000.0})
run("CCVS r=3Ω（i_ctrl=-2A）", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R0", "resistor", {"p0": "1", "p1": "0"}),
                          ("H1", "ccvs", {"p0": "2", "p1": "0"}), ("R1", "resistor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10}, "R0": {"value": 5}, "H1": {"gain": 3, "control": "V1"}, "R1": {"value": 1000}},
    DC, {"2": -6.0})
run("二极管导通 0.7V", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                  ("D1", "diode", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 5}, "R1": {"value": 1000}, "D1": {"vth": 0.7}}, DC, {"2": 0.7})
run("二极管反偏截止", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                 ("D1", "diode", {"p0": "0", "p1": "2"})],
    {"V1": {"value": 5}, "R1": {"value": 1000}, "D1": {"vth": 0.7}}, DC, {"2": 5.0})

print("\n【正弦稳态（有效值相量）】")
w = 2 * math.pi * 50
rc = 1 / math.sqrt(1 + (w * 1000 * 1e-6) ** 2)
run("RC 分压 f=50", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                  ("C1", "capacitor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10, "kind": "ac"}, "R1": {"value": 1000}, "C1": {"value": 1e-6}},
    AC, {"2": (10 * rc, -math.degrees(math.atan(w * 1000 * 1e-6)))}, freq=50.0)
zl = 2 * math.pi * 50 * 0.1
run("RL 分压（L 上电压）f=50", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                        ("L1", "inductor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10, "kind": "ac"}, "R1": {"value": 100}, "L1": {"value": 0.1}},
    AC, {"2": (10 * zl / math.hypot(100, zl), 90 - math.degrees(math.atan2(zl, 100)))}, freq=50.0)
f0 = 1 / (2 * math.pi * math.sqrt(1e-3 * 1e-6))
run("LC 串联谐振 f0（C 上电压=Q·U）", [("V1", "vsource", {"p0": "1", "p1": "0"}),
                             ("R1", "resistor", {"p0": "1", "p1": "2"}),
                             ("L1", "inductor", {"p0": "2", "p1": "3"}),
                             ("C1", "capacitor", {"p0": "3", "p1": "0"})],
    {"V1": {"value": 1, "kind": "ac"}, "R1": {"value": 10}, "L1": {"value": 1e-3}, "C1": {"value": 1e-6}},
    AC, {"3": (0.1 * (1 / (2 * math.pi * f0 * 1e-6)), -90.0)}, freq=f0)
run("变压器 n=2 副边 5V", [("V1", "vsource", {"p0": "1", "p1": "0"}),
                     ("T1", "transformer", {"p0": "1", "p1": "0", "p2": "2", "p3": "0"}),
                     ("R2", "resistor", {"p0": "2", "p1": "0"})],
    {"V1": {"value": 10, "kind": "ac"}, "T1": {"ratio": 2}, "R2": {"value": 1000}},
    AC, {"2": 5.0}, freq=50.0)
run("理想运放反相放大 -10", [("V1", "vsource", {"p0": "1", "p1": "0"}),
                      ("R1", "resistor", {"p0": "1", "p1": "2"}),
                      ("A1", "opamp", {"inp": "0", "inn": "2", "out": "3"}),
                      ("Rf", "resistor", {"p0": "2", "p1": "3"})],
    {"V1": {"value": 1}, "R1": {"value": 1000}, "Rf": {"value": 10000}}, DC, {"3": -10.0})

print("\n【暂态（后向欧拉）】")
r = run("RC 阶跃（对照解析）", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                        ("C1", "capacitor", {"p0": "2", "p1": "0"})],
        {"V1": {"value": 10, "kind": "step"}, "R1": {"value": 1000}, "C1": {"value": 1e-6}},
        TRAN, {}, tstop=0.005, nsteps=101, v0={"C1": 0.0})
if r:
    wv = r["waveform"]
    e1, e2 = 10 * (1 - math.exp(-1)), 10 * (1 - math.exp(-5))
    print(f"        t=1ms  V(C1)={wv['U:C1'][20]:.5f}  解析 {e1:.5f}   偏差 {abs(wv['U:C1'][20]-e1)/e1*100:.2f}%")
    print(f"        t=5ms  V(C1)={wv['U:C1'][100]:.5f} 解析 {e2:.5f}   偏差 {abs(wv['U:C1'][100]-e2)/e2*100:.2f}%")
r = run("RL 阶跃（对照解析）", [("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                        ("L1", "inductor", {"p0": "2", "p1": "0"})],
        {"V1": {"value": 10, "kind": "step"}, "R1": {"value": 0.1}, "L1": {"value": 1e-3}},
        TRAN, {}, tstop=0.05, nsteps=101, i0={"L1": 0.0})
if r:
    wv = r["waveform"]
    e1 = 100 * (1 - math.exp(-1))
    print(f"        t=10ms I(L1)={wv['I:L1'][20]:.5f}  解析 {e1:.5f}   偏差 {abs(wv['I:L1'][20]-e1)/e1*100:.2f}%")

print("\n【三相】")
run("三相星形对称（相电压 220V）", [("U1", "vsource", {"p0": "1", "p1": "0"}),
                         ("U2", "vsource", {"p0": "2", "p1": "0"}),
                         ("U3", "vsource", {"p0": "3", "p1": "0"}),
                         ("R1", "resistor", {"p0": "1", "p1": "0"}),
                         ("R2", "resistor", {"p0": "2", "p1": "0"}),
                         ("R3", "resistor", {"p0": "3", "p1": "0"})],
    {"U1": {"value": 220, "kind": "ac", "phase": 0},
     "U2": {"value": 220, "kind": "ac", "phase": -120},
     "U3": {"value": 220, "kind": "ac", "phase": 120},
     "R1": {"value": 10}, "R2": {"value": 10}, "R3": {"value": 10}},
    AC, {"1": (220.0, 0.0), "2": (220.0, -120.0), "3": (220.0, 120.0)}, freq=50.0)

print(f"\n通过 {OK[0]} 项，失败 {OK[1]} 项")
