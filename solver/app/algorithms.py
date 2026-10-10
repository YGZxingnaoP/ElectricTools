"""手算算法引擎：按人算的顺序把未知元件推出来，每步给式子+数值。

第一个算法：**端口等效（戴维南/诺顿）** —— 求一个未知二端元件的值，不需要额外条件：
    ① 把它从端口断开
    ② 求端口开路电压 Voc（对剩下的电路做节点电压法）
    ③ 把端口短路，求短路电流 Isc
    ④ 等效电阻 Rth = Voc / Isc → 该元件的取值
    ⑤ 回代：整张图变成数字
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import devices as DEV
from .engine import AC, DC, TRAN
from .engine import analyse as engine_analyse
from .solve import Br, build_branches

RESISTIVE = {"resistor"}


def _solve(nodes: Dict[str, dict], branches: List[Br], domain: str, freq: float) -> Dict[str, Any]:
    return engine_analyse(nodes, branches, domain=domain, freq=freq)


def port_equivalent(sch, topo, unknowns: List[str], req) -> Dict[str, Any]:
    """对每个未知元件做端口等效。返回可被前端直接渲染的 {solutions, steps}。"""
    from .engine_bridge import domain_of

    domain, freq, _t, _n = domain_of(req)
    if domain == TRAN:
        domain = DC
    branches = build_branches(sch, topo.node_of_member)
    by_id = {b.id: b for b in branches}
    nodes = topo.nodes
    values: Dict[str, Dict[str, Any]] = {}
    steps: List[Dict[str, Any]] = []
    details: List[Dict[str, Any]] = []

    for cid in unknowns:
        b = by_id.get(cid)
        if b is None:
            continue
        spec = DEV.get(b.type)
        if b.type not in ("resistor", "capacitor", "inductor"):
            # 端口等效只对**无源二端元件**有意义；未知源要靠条件才能定出，不能瞎填
            steps.append({"title": f"{cid} 是{spec.cn}，不能用端口等效",
                          "text": "未知电源/受控源需要有已知条件（某点电压或某条电流）才能定出，"
                                  "请在图上标注一条「已知量」，或在「条件求解」里给一条。"})
            continue
        a, bb = b.node("p0"), b.node("p1")
        # ① 断开该元件
        rest = [x for x in branches if x.id != cid]
        # ② 端口开路电压
        try:
            voc_res = _solve(nodes, rest, domain, freq)
        except Exception as exc:
            steps.append({"title": f"① 断开 {cid}", "text": f"断开后电路无法求解：{exc}"})
            continue
        va = voc_res["V"].get(a, 0)
        vb = voc_res["V"].get(bb, 0)
        voc = va - vb
        # ③ 端口短路电流：在端口上加一条 0V 电压源，测它的电流
        short = Br(id="__port__", type="vsource", n={"p0": a, "p1": bb}, prm={"value": 0.0})
        try:
            sc_res = _solve(nodes, rest + [short], domain, freq)
            isc = sc_res["I"].get("__port__", 0)
        except Exception as exc:
            isc = None
        # ④ 等效电阻
        rth = None
        if isc not in (None, 0):
            rth = voc / isc
        if rth is None:
            continue
        rth_f = abs(complex(rth))
        voc_f = abs(complex(voc))
        isc_f = abs(complex(isc))
        unit = spec.unit
        values[cid] = {"value": rth_f, "unit": unit, "type": b.type, "feasible": rth_f > 0,
                       "note": "" if rth_f > 0 else "等效电阻必须为正"}
        details.append({"id": cid, "a": a, "b": bb, "voc": voc_f, "isc": isc_f, "rth": rth_f,
                        "unit": unit, "type": b.type})

    if not details:
        return {}

    d0 = details[0]
    comp = next((c for c in sch.components if c.id == d0["id"]), None)
    steps = [
        {"title": f"① 把 {d0['id']} 从端口断开",
         "text": f"端口 = {d0['a']} 与 {d0['b']} 两端。断开后先不管它，只看剩下的电路。"},
        {"title": "② 求端口开路电压 Voc",
         "text": "对剩下的电路列节点电压法（KCL），解出两个端点的电位差。",
         "latex": f"V_{{oc}} = {_num(d0['voc'])}\\ \\text{{V}}"},
        {"title": "③ 求端口短路电流 Isc",
         "text": "把两个端点短接，求流过短接线的电流（端口上的 0V 支路电流）。",
         "latex": f"I_{{sc}} = {_num(d0['isc'])}\\ \\text{{A}}"},
        {"title": "④ 等效电阻 Rth = Voc / Isc",
         "text": "这就是从端口看进去的等效电阻；待求元件取这个值时获得最大功率、也即本题答案。",
         "latex": f"R_{{th}} = \\frac{{V_{{oc}}}}{{I_{{sc}}}} = \\frac{{{_num(d0['voc'])}}}"
                  f"{{{_num(d0['isc'])}}} = {_num(d0['rth'])}\\ \\text{{{d0['unit']}}}"},
        {"title": "⑤ 回代：整张图变成数字",
         "text": f"把 {d0['id']} = {_num(d0['rth'])} {d0['unit']} 填回电路，所有节点电压、"
                 "支路电流都随之定出（见下方表格）。"},
    ]
    return {
        "ok": True,
        "method": "端口等效（戴维南）",
        "unknowns": [{"id": d["id"], "type": d["type"]} for d in details],
        "solutions": [{"feasible": True, "values": values}],
        "steps": steps,
        "port": details,
    }


def _num(x: float) -> str:
    v = float(x)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4g}"
