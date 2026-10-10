"""扫频验证：RC 低通，转折频率 159Hz；谐振电路应出现峰值。"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_sw.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app import devices as D
from solver.app.models import Component, Pin, Schematic
from solver.app.solve import build_branches
from solver.app.sweep import sweep



def sch_of(spec, params):
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
    return s, nom


def nodes_of(nom):
    return {n: {"id": n, "is_ground": n == "0",
                "members": sorted(k for k, v in nom.items() if v == n)} for n in set(nom.values())}


OK = [0, 0]


def chk(cond, msg):
    OK[0 if cond else 1] += 1
    p(("  ok   " if cond else "  FAIL ") + msg)


p("【RC 低通】V(2)/V1 的幅频：转折频率 f_c = 1/(2πRC) = 159.15 Hz")
sch, nom = sch_of([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                   ("C1", "capacitor", {"p0": "2", "p1": "0"})],
                  {"V1": {"value": 1, "kind": "ac"}, "R1": {"value": 1000}, "C1": {"value": 1e-6}})
topo = type("T", (), {"nodes": nodes_of(nom), "node_of_member": nom})()
out = sweep(sch, topo, 10, 100000, 61, "node")
f, s = out["freqs"], out["series"]["V(2)"]
p("  频点数：" + str(len(f)))
for want in (10.0, 159.15, 1591.5, 15915.0):
    i = min(range(len(f)), key=lambda j: abs(f[j] - want))
    p(f"    f={f[i]:9.2f} Hz  |V(2)|={s['mag'][i]:.5f}  相角={s['phase'][i]:.2f}°")
i0 = min(range(len(f)), key=lambda j: abs(f[j] - 10))
i1 = min(range(len(f)), key=lambda j: abs(f[j] - 159.15))
i2 = min(range(len(f)), key=lambda j: abs(f[j] - 1591.5))
chk(abs(s["mag"][i0] - 1.0) < 0.01, f"10Hz 增益≈1（实得 {s['mag'][i0]:.4f}）")
chk(abs(s["mag"][i1] - 0.7071) < 0.02, f"转折点 159Hz 增益≈0.707（实得 {s['mag'][i1]:.4f}）")
chk(abs(s["phase"][i1] + 45) < 2, f"转折点相角≈-45°（实得 {s['phase'][i1]:.2f}°）")
chk(s["mag"][i2] < s["mag"][i1] < s["mag"][i0], "幅值随频率单调下降（低通特性）")
chk(abs(s["phase"][i2] + 90) < 3, f"高频相角 → -90°（实得 {s['phase'][i2]:.2f}°）")

p("")
p("【RLC 串联：找谐振峰】L=1mH C=1µF → f0 = 5033 Hz")
sch2, nom2 = sch_of([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                     ("L1", "inductor", {"p0": "2", "p1": "3"}), ("C1", "capacitor", {"p0": "3", "p1": "0"})],
                    {"V1": {"value": 1, "kind": "ac"}, "R1": {"value": 10},
                     "L1": {"value": 1e-3}, "C1": {"value": 1e-6}})
topo2 = type("T", (), {"nodes": nodes_of(nom2), "node_of_member": nom2})()
out2 = sweep(sch2, topo2, 100, 50000, 121, "reactive")
f2 = out2["freqs"]
key = "I(C1)" if "I(C1)" in out2["series"] else list(out2["series"])[0]
mag = out2["series"][key]["mag"]
imax = max(range(len(mag)), key=lambda j: mag[j])
p(f"  电流峰所在频率 = {f2[imax]:.1f} Hz（理论 f0 = 5032.9 Hz），峰值 {mag[imax]:.5f} A")
chk(abs(f2[imax] - 5032.9) / 5032.9 < 0.03, f"谐振点定位正确（误差 {abs(f2[imax]-5032.9)/5032.9*100:.1f}%）")
chk(abs(mag[imax] - 0.1) < 5e-3, f"谐振电流 ≈ U/R = 0.1A（实得 {mag[imax]:.4f}）")

p("")
p(f"通过 {OK[0]}，失败 {OK[1]}")
