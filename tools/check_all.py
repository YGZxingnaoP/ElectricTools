"""全面体检：专门挑我怀疑有 bug 的地方，打印真实输出。"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = open(os.path.join(ROOT, "tools", "_chk.txt"), "w", encoding="utf-8")


def p(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")


from solver.app import devices as D
from solver.app.algo_all import series_parallel_steps, three_element_steps
from solver.app.analysis import STORE, analyze
from solver.app.engine import AC, DC, TRAN, SolveError
from solver.app.engine import analyse as eng
from solver.app.models import Component, Pin, Schematic, SolveRequest
from solver.app.solve import Br, build_branches

BUGS = []


def bug(m):
    BUGS.append(m)
    p("  ★BUG " + m)


def ok(m):
    p("  ok   " + m)


def mk(spec, params):
    comps, nom = [], {}
    for cid, ctype, pins in spec:
        pd = pins if isinstance(pins, dict) else {n: (x, y) for n, x, y in pins}
        prm = params.get(cid, {})
        comps.append(Component(id=cid, type=ctype, value=prm.get("value"),
                               params={k: v for k, v in prm.items() if k != "value"},
                               pins=[Pin(name=n, x=pd[n][0], y=pd[n][1]) for n in pd]))
        for n in pd:
            nom[f"u:{cid}/{n}"] = f"n{abs(hash((pd[n][0], pd[n][1]))) % 97}"
    return Schematic(components=comps, wires=[], junctions=[]), nom


def nodes_of(nom):
    return {n: {"id": n, "is_ground": False, "members": sorted(k for k, v in nom.items() if v == n)}
            for n in set(nom.values())}


def brs(sch, nom):
    return build_branches(sch, nom)


def steps(sch, sid="x", **kw):
    STORE.set_schematic(sid, sch)
    r = analyze(SolveRequest(session_id=sid, schematic=sch, mode="numeric", **kw), False)
    return r, (r.constraint_result or {}).get("steps") or []


p("=" * 72)
p("检查 1：节点电压法的 KCL 方程写对了没（必须有另一个节点的电压）")
sch, nom = mk([("V1", "vsource", {"p0": (0, 0), "p1": (0, 100)}),
               ("R1", "resistor", {"p0": (0, 100), "p1": (50, 100)}),
               ("R2", "resistor", {"p0": (50, 100), "p1": (50, 0)})],
              {"V1": {"value": 10}, "R1": {"value": 5}, "R2": {"value": 5}})
r, st = steps(sch, "s1")
for s in st:
    t = (s.get("title") or "") + " " + (s.get("text") or "")
    if "KCL" in t:
        p("   实际: " + t)
        if "-" not in t and "−" not in t:
            bug(f"KCL 方程没减另一个节点电压（应为 (V2-V1)/R）：{t[:80]}")
        else:
            ok("KCL 含另一个节点电压")

p("")
p("检查 2：三个独立源时叠加定理")
sch, nom = mk([("V1", "vsource", {"p0": (0, 0), "p1": (0, 50)}),
               ("I1", "isource", {"p0": (0, 50), "p1": (0, 0)}),
               ("R1", "resistor", {"p0": (0, 50), "p1": (50, 50)})],
              {"V1": {"value": 10}, "I1": {"value": 2}, "R1": {"value": 5}})
r, st = steps(sch, "s2")
sup = [s for s in st if "只留" in (s.get("title") or "")]
p(f"   叠加分段数 = {len(sup)}（应有 2）")
if len(sup) != 2:
    bug("叠加定理分段数不对")
else:
    ok("叠加定理按独立源个数分段")

p("")
p("检查 3：三要素法里【电感】的稳态值（电感在直流稳态=短路，不能当成断开）")
sch, nom = mk([("V1", "vsource", {"p0": (0, 0), "p1": (0, 300)}),
               ("R1", "resistor", {"p0": (0, 300), "p1": (0, 200)}),
               ("L1", "inductor", {"p0": (0, 200), "p1": (0, 0)})],
              {"V1": {"value": 10}, "R1": {"value": 100}, "L1": {"value": 0.1}})
br = brs(sch, nom)
st = three_element_steps(nodes_of(nom), br, None) if False else None
# 直接调（req 用不到）
import types
try:
    st = three_element_steps(nodes_of(nom), br, types.SimpleNamespace(domain="tran"))
except Exception as exc:
    st = []
    p("   异常: " + repr(exc))
for s in st:
    if "L1" in (s.get("text") or ""):
        p("   实际: " + s["text"][:120])
        if "0 V" not in s["text"] and "0 A" not in s["text"]:
            bug("电感稳态值算错（直流稳态电感=短路，电流应是 U/R=0.1A，两端电压 0）")
        else:
            ok("电感稳态值正确")

p("")
p("检查 4：交流支路电流取的是有效值还是相量（两表法要用相量）")
sch, nom = mk([("V1", "vsource", {"p0": (0, 0), "p1": (0, 50)}),
               ("R1", "resistor", {"p0": (0, 50), "p1": (50, 50)}),
               ("R2", "resistor", {"p0": (50, 50), "p1": (50, 0)})],
              {"V1": {"value": 10, "kind": "ac", "phase": 45}, "R1": {"value": 5}, "R2": {"value": 5}})
STORE.set_schematic("s4", sch)
r = analyze(SolveRequest(session_id="s4", schematic=sch, mode="numeric", domain="ac", freq=50), False)
b0 = r.branches[0] if r.branches else None
p(f"   支路 {b0.component}: current={b0.current} phasor={b0.phasor}")
if b0 and getattr(b0, "phasor", None):
    if abs(b0.current - b0.phasor.rms) < 1e-9:
        bug("AC 支路 current 只存了有效值（幅值），丢掉相位 → 两表法/叠加若用 current 会错")
    else:
        ok("AC 支路电流带相位信息")

p("")
p("检查 5：takes_value 遇到未知器件类型")
from solver.app import devices
try:
    devices.takes_value("不存在的器件")
    ok("takes_value 不炸")
except Exception as exc:
    bug(f"takes_value 对未知类型抛 {type(exc).__name__} → 缓存里有脏数据时会崩")

p("")
p("检查 6：符号网表遇到没有节点信息的支路")
from solver.app.netlist_all import build as nl_build
try:
    nl, *_ = nl_build([{"component": "R9", "type": "resistor", "value": 10}], "0")
    p("   实际网表: " + repr(nl))
    if "None" in nl:
        bug(f"缺节点信息时网表写进了 None：{nl!r}")
    else:
        ok("缺节点时被跳过")
except Exception as exc:
    bug(f"缺节点时抛 {type(exc).__name__}: {exc}")

p("")
p("检查 7：悬空检查对「自己接自己」的支路")
from solver.app.engine import check_floating
b1 = Br(id="R1", type="resistor", n={"p0": "n1", "p1": "n1"}, prm={"value": 1.0})
b2 = Br(id="R2", type="resistor", n={"p0": "n2", "p1": "n2"}, prm={"value": 1.0})
msg = check_floating({"n1": {}, "n2": {}}, [b1, b2], None)
p("   实际: " + repr(msg))
if not msg:
    bug("p0==p1 的自环支路被当成两个连接 → 悬空检查失效")

p("")
p("检查 8：电流源方向（叠加定理里置零要开路，电压源置零要短路）")
sch, nom = mk([("V1", "vsource", {"p0": (0, 0), "p1": (0, 50)}),
               ("I1", "isource", {"p0": (0, 50), "p1": (0, 0)}),
               ("R1", "resistor", {"p0": (0, 50), "p1": (50, 50)}),
               ("R2", "resistor", {"p0": (50, 50), "p1": (50, 0)})],
              {"V1": {"value": 10}, "I1": {"value": 1}, "R1": {"value": 5}, "R2": {"value": 5}})
r, st = steps(sch, "s8")
tot = [s for s in st if "相加" in (s.get("title") or "")]
if r.ok and tot:
    p("   实际: " + tot[0]["text"][:100])
    V = {k: round(abs(complex(v.voltage or v.phasor.re if getattr(v, 'phasor', None) else v.voltage or 0)), 4)
         for k, v in r.nodes.items()}
    p("   真解: " + str(V))

p("")
p("检查 9：变压器 n=1")
sch, nom = mk([("V1", "vsource", {"p0": (0, 0), "p1": (0, 50)}),
               ("T1", "transformer", {"p0": (0, 0), "p1": (0, 50), "p2": (60, 0), "p3": (60, 50)}),
               ("R2", "resistor", {"p0": (60, 50), "p1": (60, 0)})],
              {"V1": {"value": 10, "kind": "ac"}, "T1": {"ratio": 1}, "R2": {"value": 100}})
sch.components[0].pins[0].x = 0.0
try:
    from solver.app.topology import NodeRegistry, derive_topology

    topo = derive_topology(sch, NodeRegistry())
    # 手工把端子接起来（测试用）
    topo.node_of_member["u:V1/p1"] = topo.node_of_member["u:T1/p1"]
    topo.node_of_member["u:R2/p0"] = topo.node_of_member["u:T1/p2"]
    topo.node_of_member["u:R2/p1"] = topo.node_of_member["u:T1/p3"]
    e = eng(topo.nodes, brs(sch, topo.node_of_member), domain=AC, freq=50)
    vr = {k: round(abs(v), 4) for k, v in e["V"].items()}
    p("   实际 V: " + str(vr))
except Exception as exc:
    p("   异常: " + f"{type(exc).__name__}: {exc}")

p("")
p("检查 10：电流源单独供电 + 悬空节点（旧路径报错信息）")
sch, nom = mk([("I1", "isource", {"p0": (0, 0), "p1": (50, 0)}),
               ("R1", "resistor", {"p0": (50, 0), "p1": (50, 100)})],
              {"I1": {"value": 2}, "R1": {"value": 10}})
r, st = steps(sch, "s10")
errs = [d.message for d in r.diagnostics if d.level == "error"]
p("   诊断: " + str(errs)[:150])
p("   ok=" + str(r.ok))
if r.ok:
    v = {k: (round(v.voltage, 4) if v.voltage is not None else None) for k, v in r.nodes.items()}
    p("   V: " + str(v))

p("")
p("=" * 72)
p(f"发现 {len(BUGS)} 个问题")
for i, b in enumerate(BUGS, 1):
    p(f"  {i}. {b}")
