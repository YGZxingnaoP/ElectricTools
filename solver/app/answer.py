"""一键求解：按一个按钮，把能算成数值的都算成数值。

不需要用户提供任何额外输入。

    ① 图上元件都填了数值        → 全部节点电压 / 支路电流 直接给数值。
    ② 有元件没填数值（未知）    → 除给出能定出的量外，再给出**该元件端口的戴维南等效**：
                                  V_oc 开路电压、I_sc 短路电流、R_th 等效电阻 —— 全是数值。
                                  未知"阻值"唯一有确定数值含义的场合，就是题目要求
                                  「该元件获得最大功率」——此时它的阻值 = R_th。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .analysis import STORE, analyze
from .equivalence import port_thevenin
from .models import SolveRequest
from .topology import derive_topology

UNIT = {"resistor": "Ω", "vsource": "V", "isource": "A"}


def compute_answer(session_id: str, schematic=None) -> Dict[str, Any]:
    if schematic is not None:
        STORE.set_schematic(session_id, schematic)
    sch = STORE.get_schematic(session_id)
    if sch is None:
        return {"error": "当前会话没有电路。"}

    res = analyze(SolveRequest(session_id=session_id, schematic=sch, mode="both"), True)
    if not res.ok:
        return {"error": "电路无法求解。", "diagnostics": [d.model_dump() for d in res.diagnostics]}

    topo = derive_topology(sch, STORE.registry(session_id))
    member_to_node: Dict[str, str] = {}
    for nid, nd in res.nodes.items():
        for m in (nd.members or []):
            member_to_node[m] = nid

    from . import devices as _DEV
    unknowns = [c for c in sch.components
                if c.value is None and _DEV.takes_value(c.type)]
    # 图上标注（已知量）已经把某个未知元件解出数来了 → 直接给出它的值
    solved: Dict[str, float] = {}
    cr = res.constraint_result or {}
    for sol in (cr.get("solutions") or []):
        if sol.get("feasible"):
            solved = {cid: info["value"] for cid, info in (sol.get("values") or {}).items()
                      if info.get("feasible")}
            break

    answers: List[Dict[str, Any]] = []
    for c in unknowns:
        na = member_to_node.get(f"u:{c.id}/p0")
        nb = member_to_node.get(f"u:{c.id}/p1")
        item: Dict[str, Any] = {
            "id": c.id, "type": c.type, "unit": UNIT.get(c.type, ""),
            "symbol": c.symbol, "voc": None, "isc": None, "rth": None,
            "value": solved.get(c.id),
        }
        if na and nb and na != nb:
            try:
                th = port_thevenin(topo.nodes, topo.branches, na, nb, exclude=[c.id])
                item.update({"voc": th["voc"], "isc": th["isc"], "rth": th["rth"]})
            except Exception as exc:                       # pragma: no cover
                item["error"] = str(exc)
        # 它自己的电流/电压表达式里还含不含它自己 —— 用来判断"有没有元件把它钉住"
        br = next((b for b in res.branches if b.component == c.id), None)
        item["current_expr"] = br.current_expr if br else None
        if item["value"] is not None:
            item["reason"] = (
                f"{c.id} = {item['value']} {item['unit']} —— 由图上的「已知量」标注解出"
                f"（标注给出了别的条件，把它锁死了）。"
            )
        else:
            item["reason"] = (
                f"{c.id} 的数值无法由这张图本身求出：把 {c.id} 当作未知量，方程数比未知数少 1 个 —— "
                f"对任意 {c.id} > 0 电路都自洽（图上标注 1、2、4、10 Ω 全都能解出来）。"
                f"要让 {c.id} 解成一个数，题目必须再给一个已知量（例如「{c.id} 两端电压 = ×× V」"
                f"「通过 {c.id} 的电流 = ×× A」，用左侧「标注电压 / 标注电流」画到图上即可），"
                f"或者题目问的是「{c.id} 取何值获得最大功率」——那就是上面的端口等效电阻。"
            )
        answers.append(item)

    return {
        "ok": True,
        "all_known": not unknowns,
        "nodes": [{"id": nid, "voltage": res.nodes[nid].voltage} for nid in res.node_order],
        "branches": [{"component": b.component, "current": b.current, "type": b.type} for b in res.branches],
        "unknowns": answers,
    }
