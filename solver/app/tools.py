"""AI 工具的后端实现（docs/architecture.md §6.5）。

工具与前端手动求解**共用同一批求解函数**，保证一致性。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .analysis import STORE, analyze
from .equivalence import port_norton, port_thevenin
from .models import SolveRequest, SolveResult
from .topology import derive_topology

_cache: Dict[str, tuple] = {}


def _solve(session_id: str, mode: str = "both") -> Optional[SolveResult]:
    sch = STORE.get_schematic(session_id)
    if sch is None:
        return None
    key = session_id
    cached = _cache.get(key)
    if cached and cached[0] == mode and cached[1] is sch:
        return cached[2]
    res = analyze(SolveRequest(session_id=session_id, schematic=sch, mode=mode), mode == "both")
    _cache[key] = (mode, sch, res)
    return res


def _topo(session_id: str):
    sch = STORE.get_schematic(session_id)
    if sch is None:
        return None
    return derive_topology(sch, STORE.registry(session_id))


# ---------- 工具 ----------

def get_circuit_netlist(session_id: str) -> Dict[str, Any]:
    res = _solve(session_id, "numeric")
    if res is None:
        return {"error": "当前会话没有电路。"}
    return {
        "netlist": res.netlist,
        "nodes": [{"id": n, "voltage": res.nodes[n].voltage} for n in res.node_order],
        "components": [
            {"id": b.component, "type": b.type, "node_p": b.node_p, "node_n": b.node_n}
            for b in res.branches
        ],
    }


def solve_node_voltage(session_id: str, node: str) -> Dict[str, Any]:
    res = _solve(session_id, "both")
    if res is None:
        return {"error": "当前会话没有电路。"}
    if node not in res.nodes:
        return {"error": f"节点 {node} 不存在。", "available": res.node_order}
    n = res.nodes[node]
    return {"node": node, "voltage": n.voltage, "expr": n.voltage_expr, "latex": n.voltage_latex}


def solve_branch_current(session_id: str, component: str) -> Dict[str, Any]:
    res = _solve(session_id, "both")
    if res is None:
        return {"error": "当前会话没有电路。"}
    for b in res.branches:
        if b.component == component:
            return {
                "component": component,
                "current": b.current,
                "reference_direction": f"{b.node_p} -> {b.node_n} (p0->p1)",
                "expr": b.current_expr,
                "latex": b.current_latex,
            }
    return {"error": f"元件 {component} 不存在。", "available": [b.component for b in res.branches]}


def get_kcl_equations(session_id: str, node: str) -> Dict[str, Any]:
    res = _solve(session_id, "both")
    if res is None:
        return {"error": "当前会话没有电路。"}
    terms: List[str] = []
    for b in res.branches:
        if b.node_p != node and b.node_n != node:
            continue
        sign = "+" if b.node_p == node else "-"
        sym = b.current_latex or f"I_{{{b.component}}}"
        terms.append(f"{sign} \\left({sym}\\right)")
    if not terms:
        return {"error": f"节点 {node} 没有支路。"}
    expr = " ".join(terms).lstrip("+ ").strip()
    return {"node": node, "kcl_latex": expr + " = 0", "description": "离开节点的电流之和为零（KCL）"}


def apply_thevenin(session_id: str, node_a: str, node_b: str, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    topo = _topo(session_id)
    if topo is None:
        return {"error": "当前会话没有电路。"}
    nodes = {nid: info for nid, info in topo.nodes.items()}
    try:
        th = port_thevenin(nodes, topo.branches, node_a, node_b, exclude=exclude)
    except Exception as exc:
        return {"error": str(exc)}
    return {
        "port": f"{node_a}-{node_b}",
        "excluded": list(exclude or []),
        "voc": th["voc"], "isc": th["isc"], "rth": th["rth"],
        "equivalent_netlist": f"Vth {node_a} {node_b} {th['voc']!r}\nRth {node_a} {node_b} {th['rth']!r}",
    }


def apply_norton(session_id: str, node_a: str, node_b: str, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    topo = _topo(session_id)
    if topo is None:
        return {"error": "当前会话没有电路。"}
    nodes = {nid: info for nid, info in topo.nodes.items()}
    try:
        nr = port_norton(nodes, topo.branches, node_a, node_b, exclude=exclude)
    except Exception as exc:
        return {"error": str(exc)}
    return {"port": f"{node_a}-{node_b}", "excluded": list(exclude or []), "in": nr["in"], "rn": nr["rn"]}


def node_detail(session_id: str, node: str) -> Dict[str, Any]:
    """节点探针：电压、相关支路电流、KCL 方程与计算方法（供前端点击节点时展示）。"""
    res = _solve(session_id, "both")
    if res is None:
        return {"error": "当前会话没有电路。"}
    if node not in res.nodes:
        return {"error": f"节点 {node} 不存在。", "available": res.node_order}

    n = res.nodes[node]
    branch_rows: List[Dict[str, Any]] = []
    terms: List[str] = []
    for b in res.branches:
        if b.node_p != node and b.node_n != node:
            continue
        leaving = b.node_p == node          # 参考方向 p0→p1，从 node 出发即为"离开"
        sign = "+" if leaving else "-"
        sym = b.current_latex or f"I_{{{b.component}}}"
        terms.append(f"{sign} \\left({sym}\\right)")
        branch_rows.append({
            "component": b.component,
            "type": b.type,
            "current": b.current,
            "latex": b.current_latex,
            "node_p": b.node_p,
            "node_n": b.node_n,
            "leaving": leaving,
        })

    kcl = (" ".join(terms).lstrip("+ ").strip() + " = 0") if terms else ""
    return {
        "node": node,
        "is_ground": node == "0",
        "voltage": n.voltage,
        "voltage_expr": n.voltage_expr,
        "voltage_latex": n.voltage_latex,
        "branches": branch_rows,
        "kcl_latex": kcl,
        "method": (
            "节点电压法（KCL）：以该节点电位为未知量，对节点列写 KCL —— "
            "离开节点的各支路电流代数和为 0；每条支路电流再由元件的 VCR（欧姆定律）"
            "表示为节点电压之差的函数，联立方程组即可解出该节点电压。"
        ),
        "method_latex": r"\sum_k I_k = 0 \quad\Rightarrow\quad \sum_k \frac{V_{node}-V_{k}}{R_k} + \sum I_{src} = 0",
    }
