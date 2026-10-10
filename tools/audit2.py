"""正确版核查：只查关键项，脚本自身不再有解析/期望错误。"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_a2.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app import devices as D
from solver.app.engine import AC, DC, TRAN
from solver.app.engine import analyse as eng_analyse
from solver.app.models import Component, Pin, Schematic, SolveRequest
from solver.app.solve import build_branches
from solver.app.topology import NodeRegistry, derive_topology

BAD = []


def bug(m):
    BAD.append(m)
    p("  X " + m)


def ok(m):
    p("  v " + m)


def blocks(src):
    out = {}
    for m in re.finditer(r"(\w+):\s*\{", src):
        i, depth = m.end() - 1, 0
        for j in range(i, len(src)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    out[m.group(1)] = src[i:j + 1]
                    break
    return out


def mk(spec, params=None):
    comps, nom = [], {}
    for cid, ctype, pins in spec:
        prm = (params or {}).get(cid, {})
        pobj = []
        for name, _x, _y in D.get(ctype).pins:
            if name in pins:
                pobj.append(Pin(name=name, x=0.0, y=0.0))
                nom[f"u:{cid}/{name}"] = pins[name]
        c = Component(id=cid, type=ctype, pins=pobj, x=0, y=0)
        c.value = prm.get("value")
        c.params = {k: v for k, v in prm.items() if k != "value"}
        comps.append(c)
    return Schematic(components=comps, wires=[], junctions=[]), nom


def nd(nom):
    return {n: {"id": n, "is_ground": n == "0",
                "members": sorted(k for k, v in nom.items() if v == n)} for n in set(nom.values())}


def run(spec, params, **kw):
    sch, nom = mk(spec, params)
    return eng_analyse(nd(nom), build_branches(sch, nom), **kw)


p("A. 前后端元件表（引脚/单位/默认值）一致性")
gj = open(os.path.join(ROOT, "frontend", "src", "core", "geometry.js"), encoding="utf-8").read()
front = {}
for name, body in blocks(gj).items():
    if "pins:" not in body:
        continue
    front[name] = {
        "pins": re.findall(r"name:\s*'([^']+)'", body),
        "unit": (re.search(r"unit:\s*'([^']*)'", body) or [None, None])[1],
        "prefix": (re.search(r"prefix:\s*'([^']*)'", body) or [None, None])[1],
        "def": (re.search(r"defValue:\s*([-\w.e+]+)", body) or [None, None])[1],
    }
for t, f in sorted(front.items()):
    b = D.DEVICES.get(t)
    if not b:
        bug(f"前端有 {t}，后端没有")
        continue
    back = [n for n, _x, _y in b.pins]
    if sorted(f["pins"]) != sorted(back):
        bug(f"{t} 引脚不一致 前端{f['pins']} 后端{back}")
    elif f["unit"] not in (None, b.unit):
        bug(f"{t} 单位不一致 前端'{f['unit']}' 后端'{b.unit}'")
    elif (f["prefix"] or "") != b.prefix:
        bug(f"{t} 位号前缀不一致 前端'{f['prefix']}' 后端'{b.prefix}'")
    else:
        ok(f"{t}: 引脚{sorted(back)} 单位'{b.unit}' 前缀{b.prefix}")
for t in D.DEVICES:
    if t not in front:
        bug(f"后端有 {t}，前端画不出来")
p(f"  前端 {len(front)} 种 / 后端 {len(D.DEVICES)} 种")

p("")
p("B. 器件正确性（期望值都手算过）")
# 稳压管：正接（导通 0.7）
r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
         ("DZ", "zener", {"p0": "2", "p1": "0"})],
        {"V1": {"value": 12}, "R1": {"value": 1000}, "DZ": {"vz": 5.1, "rd": 0}}, domain=DC)
v = r["V"].get("2")
(ok if abs(v - 0.7) < 0.1 else bug)(f"稳压管正接导通 V(2)={v:.4g}（理论 0.7）")
# 稳压管：反接（击穿 5.1）
r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
         ("DZ", "zener", {"p0": "0", "p1": "2"})],
        {"V1": {"value": 12}, "R1": {"value": 1000}, "DZ": {"vz": 5.1, "rd": 0}}, domain=DC)
v = r["V"].get("2")
(ok if abs(v - 5.1) < 0.1 else bug)(f"稳压管反接击穿 V(2)={v:.4g}（理论 5.1）")
# 开关
for closed, want, label in ((True, 5.0, "闭合"), (False, 0.0, "断开")):
    r = run([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
             ("S", "switch", {"p0": "2", "p1": "3"}), ("R2", "resistor", {"p0": "3", "p1": "0"})],
            {"V1": {"value": 10}, "R1": {"value": 1000}, "S": {"closed": closed}, "R2": {"value": 1000}},
            domain=DC)
    v = r["V"].get("3")
    (ok if abs(v - want) < 0.5 else bug)(f"开关{label} V(3)={v:.4g}（理论 {want}）")
# 三相
r = run([("U", "vsource3", {"p0": "1", "p1": "2", "p2": "3", "p3": "0"}),
         ("R1", "resistor", {"p0": "1", "p1": "0"}), ("R2", "resistor", {"p0": "2", "p1": "0"}),
         ("R3", "resistor", {"p0": "3", "p1": "0"})],
        {"U": {"value": 220, "kind": "ac"}, "R1": {"value": 10}, "R2": {"value": 10}, "R3": {"value": 10}},
        domain=AC, freq=50)
import math
vs = {k: (abs(v), round(math.degrees(math.atan2(v.imag, v.real)), 1)) for k, v in r["V"].items() if k != "0"}
wantp = {"1": 0.0, "2": -120.0, "3": 120.0}
good = all(abs(vs[k][0] - 220) < 0.5 and abs(vs[k][1] - wantp[k]) < 0.2 for k in ("1", "2", "3"))
(ok if good else bug)(f"三相电源四线：{vs}")

p("")
p("C. 未知量识别（走后端真实逻辑）")
sch, nom = mk([("V1", "vsource", {"p0": "1", "p1": "0"}), ("R1", "resistor", {"p0": "1", "p1": "2"}),
               ("D1", "diode", {"p0": "2", "p1": "0"}), ("Q1", "bjt", {"b": "2", "c": "1", "e": "0"})],
              {"V1": {"value": 5}, "R1": {"value": 1000}, "D1": {"vth": 0.7}})
topo = derive_topology(sch, NodeRegistry())
unk = [b["component"] for b in topo.branches
       if b.get("value") is None and D.takes_value(b.get("type", ""))]
(ok if not unk else bug)(f"未知量判定（应空）→ {unk}")
res = __import__("solver.app.analysis", fromlist=["analyze"]).analyze(
    SolveRequest(session_id="c", schematic=sch), True)
codes = [d.code for d in res.diagnostics]
(ok if "UNKNOWN_VALUE" not in codes and not res.constraint_result else bug)(
    f"含二极管/三极管时不该触发反解：诊断={codes} 反解={bool(res.constraint_result)}")

p("")
p(f"结论：{len(BAD)} 个问题")
for i, b in enumerate(BAD, 1):
    p(f"  {i}. {b}")
