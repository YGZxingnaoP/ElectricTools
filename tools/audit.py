"""全量对抗性审查：把【没测过的东西】全跑一遍，暴露 bug。

覆盖：
A. 前后端元件表一致性（引脚名/单位/默认值）—— 不一致 = 接线直接错
B. 从未测过的器件：稳压管、开关、三极管(直流/交流)、三相电源、变压器原边电流、同相运放、桥式整流
C. 未知量识别：三极管/运放没有 value 字段，会不会被当成「未知量」误触发反解？
D. 端口等效算法用在电容/电感上会怎样？
E. 暂态：正弦源、开关、初值
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_audit.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app import devices as D
from solver.app.engine import AC, DC, TRAN, analyse
from solver.app.models import Component, Pin, Schematic, SolveRequest
from solver.app.solve import build_branches

BUGS = []


def bug(msg):
    BUGS.append(msg)
    p("  ★BUG  " + msg)


def ok(msg):
    p("  ok    " + msg)


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


def run(spec, params, **kw):
    sch, nom = mk(spec, params)
    return analyse(nodes_of(nom), build_branches(sch, nom), **kw)


p("=" * 70)
p("A. 前后端元件表一致性（前端 geometry.js vs 后端 devices.py）")
p("=" * 70)
gj = open(os.path.join(ROOT, "frontend", "src", "core", "geometry.js"), encoding="utf-8").read()
blocks = re.findall(r"(\w+):\s*\{([^}]*)\}", gj, re.S)
front = {}
for name, body in blocks:
    if "pins:" not in body:
        continue
    m = re.search(r"pins:\s*\[(.*?)\]\s*$", body, re.S)
    pins = re.findall(r"name:\s*'([^']+)'", body)
    unit = re.search(r"unit:\s*'([^']*)'", body)
    prefix = re.search(r"prefix:\s*'([^']*)'", body)
    front[name] = {"pins": pins, "unit": unit.group(1) if unit else None,
                   "prefix": prefix.group(1) if prefix else None}
for t, f in front.items():
    if t not in D.DEVICES:
        bug(f"前端有元件 {t}，后端 devices.py 没有")
        continue
    b = D.DEVICES[t]
    if sorted(f["pins"]) != sorted(n for n, _x, _y in b.pins):
        bug(f"{t} 引脚不一致：前端 {f['pins']} vs 后端 {[n for n, _x, _y in b.pins]}")
    elif f["unit"] not in (None, b.unit):
        bug(f"{t} 单位不一致：前端 {f['unit']} vs 后端 {b.unit}")
    else:
        ok(f"{t}: 引脚 {f['pins']} / 单位 {f['unit']} 一致")
for t in D.DEVICES:
    if t not in front and t != "ground":
        bug(f"后端有元件 {t}，前端画不出来")
p(f"  前端 {len(front)} 种，后端 {len(D.DEVICES)} 种")

p("")
p("=" * 70)
p("B. 从未测过的器件")
p("=" * 70)
p("[B1] 三相电源 vsource3（元件库里能拖出来，后端有没有实现？）")
try:
    r = run([("U1", "vsource3", {"p0": "1", "p1": "2", "p2": "3", "p3": "0"})],
            {"U1": {"value": 220, "kind": "ac"}}, domain=AC, freq=50)
    ok("vsource3 能解：" + str({k: round(abs(v), 2) for k, v in r["V"].items()}))
except Exception as exc:
    bug(f"vsource3 直接报错：{type(exc).__name__}: {exc}")

p("[B2] 稳压管（反向击穿）")
try:
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
             ("DZ1", "zener", {"p0": "2", "p1": "0"})],
            {"V1": {"value": 12}, "R1": {"value": 1000}, "DZ1": {"vz": 5.1, "rd": 0}},
            domain=DC)
    v = r["V"].get("2")
    (ok if v is not None and abs(v - 5.1) < 0.1 else bug)(
        f"稳压管：V(2)={v}（理论 5.1V）")
except Exception as exc:
    bug(f"稳压管报错：{type(exc).__name__}: {exc}")

p("[B3] 开关（闭合/断开）")
for closed, want in ((True, 0.0), (False, 10.0)):
    try:
        r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                 ("S1", "switch", {"p0": "2", "p1": "3"}), ("R2", "resistor", {"p0": "3", "p1": "0"})],
                {"V1": {"value": 10}, "R1": {"value": 1000}, "S1": {"closed": closed},
                 "R2": {"value": 1000}}, domain=DC)
        v = r["V"].get("3")
        (ok if v is not None and abs(v - want) < 0.5 else bug)(
            f"开关{'闭合' if closed else '断开'}：V(3)={v}（理论 {want}）")
    except Exception as exc:
        bug(f"开关{'闭合' if closed else '断开'}报错：{type(exc).__name__}: {exc}")

p("[B4] 三极管直流工作点（Vcc=12V, Rb=600k, Rc=3k, β=100）")
try:
    r = run([("Vcc", "vsource", {"p0": "1", "p1": "0"}), ("Rb", "resistor", {"p0": "1", "p1": "b"}),
             ("Rc", "resistor", {"p0": "1", "p1": "c"}), ("Q1", "bjt", {"b": "b", "c": "c", "e": "0"})],
            {"Vcc": {"value": 12}, "Rb": {"value": 600e3}, "Rc": {"value": 3e3},
             "Q1": {"beta": 100, "vbe": 0.7}}, domain=DC)
    ib = (r["V"]["b"] ) / 600e3
    ic = r["I"].get("Rc")
    p(f"          V(b)={r['V'].get('b')}, V(c)={r['V'].get('c')}, I(Rc)={ic}")
    (ok if ic is not None and abs(ic - 1.883e-3) < 1e-4 else bug)(
        f"三极管 Q 点：Ic={ic}（理论 1.883mA, Ib=18.83µA）")
except Exception as exc:
    bug(f"三极管报错：{type(exc).__name__}: {exc}")

p("[B5] 理想运放 同相放大（1+Rf/R1 = 11）")
try:
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("A1", "opamp", {"inp": "1", "inn": "2", "out": "3"}),
             ("Rf", "resistor", {"p0": "3", "p1": "2"}), ("R1", "resistor", {"p0": "2", "p1": "0"})],
            {"V1": {"value": 1}, "Rf": {"value": 10000}, "R1": {"value": 1000}}, domain=DC)
    v = r["V"].get("3")
    (ok if v is not None and abs(v - 11) < 0.05 else bug)(f"同相放大：V(out)={v}（理论 11V）")
except Exception as exc:
    bug(f"同相运放报错：{type(exc).__name__}: {exc}")

p("[B6] 变压器原边电流（n=2，副边 1kΩ，原边 10V → i1=2.5mA 方向）")
try:
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}),
             ("T1", "transformer", {"p0": "1", "p1": "0", "p2": "2", "p3": "0"}),
             ("R2", "resistor", {"p0": "2", "p1": "0"})],
            {"V1": {"value": 10, "kind": "ac"}, "T1": {"ratio": 2}, "R2": {"value": 1000}},
            domain=AC, freq=50)
    i1, i2 = r["I"].get("T1"), r["I"].get("R2")
    p(f"          I(T1)={i1}, I(R2)={i2}")
    (ok if i2 and abs(abs(i2) - 5e-3) < 1e-4 else bug)(f"副边电流 {abs(i2) if i2 else None}（理论 5mA）")
except Exception as exc:
    bug(f"变压器报错：{type(exc).__name__}: {exc}")

p("[B7] 桥式整流（4 个二极管，交流源）")
try:
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("D1", "diode", {"p0": "1", "p1": "2"}),
             ("D2", "diode", {"p0": "0", "p1": "2"}), ("D3", "diode", {"p0": "3", "p1": "1"}),
             ("D4", "diode", {"p0": "3", "p1": "0"}), ("R1", "resistor", {"p0": "2", "p1": "3"})],
            {"V1": {"value": 10, "kind": "ac"}, "R1": {"value": 1000}, "D1": {"vth": 0.7},
             "D2": {"vth": 0.7}, "D3": {"vth": 0.7}, "D4": {"vth": 0.7}}, domain=AC, freq=50)
    ok("桥式整流（交流域）跑了：" + str({k: round(abs(v), 3) for k, v in r["V"].items()}))
except Exception as exc:
    bug(f"桥式整流（交流域）报错：{type(exc).__name__}: {exc}")

p("")
p("=" * 70)
p("C. 未知量识别：三极管/运放没有 value 字段，会不会被误当「未知量」？")
p("=" * 70)
try:
    sch, nom = mk([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                   ("D1", "diode", {"p0": "2", "p1": "0"})],
                  {"V1": {"value": 5}, "R1": {"value": 1000}, "D1": {"vth": 0.7}})
    brs = build_branches(sch, nom)
    novalue = [(b.id, b.type, b.prm.get("value")) for b in brs]
    p("          支路 (id, type, value): " + str(novalue))
    fake_unknown = [b.id for b in brs if b.prm.get("value") is None]
    if "D1" in fake_unknown:
        bug(f"二极管/三极管/运放没有 value 字段 → 被当成未知量（{fake_unknown}）→ 会误触发端口等效/反解")
    else:
        ok("没有把无 value 的器件当未知量")
except Exception as exc:
    bug(f"未知量识别检查报错：{type(exc).__name__}: {exc}")

p("")
p("=" * 70)
p("D. 端口等效算法用在电容/电感上")
p("=" * 70)
from solver.app.algorithms import port_equivalent
from solver.app.topology import NodeRegistry, derive_topology

for typ, val in (("capacitor", 1e-6), ("inductor", 1e-3)):
    try:
        sch, nom = mk([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
                       ("X1", typ, {"p0": "2", "p1": "0"})],
                      {"V1": {"value": 10}, "R1": {"value": 1000}})
        topo = derive_topology(sch, NodeRegistry())
        pe = port_equivalent(sch, topo, ["X1"], SolveRequest(session_id="a", schematic=sch))
        v = (pe.get("solutions") or [{}])[0].get("values", {}).get("X1")
        p(f"          {typ} 端口等效 → {v}")
        if v and abs(v["value"] - val) > 1e-9 * max(1, val):
            if v["value"] > 0:
                bug(f"{typ} 未知时端口等效给出「等效电阻 {v['value']}」，当成该元件的值填回去（量纲/物理都不对）")
            else:
                bug(f"{typ} 端口等效给负数/0：{v}")
        elif v:
            ok(f"{typ} 端口等效算出的 Rth={v['value']}，恰好当成元件值（理论上不对：电容/电感的'值'不是电阻）")
        else:
            ok(f"{typ} 没有瞎填值")
    except Exception as exc:
        bug(f"{typ} 端口等效报错：{type(exc).__name__}: {exc}")

p("")
p("=" * 70)
p("E. 暂态：正弦源 / 初值 / 开关中途翻转")
p("=" * 70)
try:
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
             ("L1", "inductor", {"p0": "2", "p1": "0"})],
            {"V1": {"value": 10, "kind": "ac", "freq": 50}, "R1": {"value": 100}, "L1": {"value": 0.1}},
            domain=TRAN, tstop=0.06, nsteps=121)
    w = r["waveform"]
    ok(f"正弦源暂态跑了：I(L1) 末值={w['I:L1'][-1]:.5f}A，峰值={max(w['I:L1']):.5f}A")
except Exception as exc:
    bug(f"正弦源暂态报错：{type(exc).__name__}: {exc}")

try:
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
             ("C1", "capacitor", {"p0": "2", "p1": "0"}), ("R2", "resistor", {"p0": "2", "p1": "0"})],
            {"V1": {"value": 10, "kind": "step"}, "R1": {"value": 1000}, "C1": {"value": 1e-6},
             "R2": {"value": 1000}}, domain=TRAN, tstop=0.01, nsteps=51, v0={"C1": 5.0})
    w = r["waveform"]
    p(f"          带初值 v_C(0)=5V：t=0 时 U(C1)={w['U:C1'][0]:.4f}（应为 5），末值={w['U:C1'][-1]:.4f}")
    if abs(w["U:C1"][0] - 5.0) > 1e-6:
        bug("暂态初值没生效（t=0 的 U(C1) ≠ 5V）")
    else:
        ok("暂态初值生效")
except Exception as exc:
    bug(f"暂态初值报错：{type(exc).__name__}: {exc}")

p("")
p("=" * 70)
p(f"审查结束：发现 {len(BUGS)} 个问题")
p("=" * 70)
for i, b in enumerate(BUGS, 1):
    p(f"  {i}. {b}")
