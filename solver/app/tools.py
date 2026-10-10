"""AI 工具的后端实现。

工具与前端手动求解**共用同一批求解函数**，保证一致性。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .analysis import STORE, analyze
from .equivalence import port_norton, port_thevenin
from .models import SolveRequest, SolveResult
from .topology import derive_topology

_cache: Dict[str, tuple] = {}


def _lsym(name: str) -> str:
    """R1 → R_{1}（LaTeX 下标），贴近课本写法。"""
    m = re.match(r"^([A-Za-z_]+)(\d+)$", str(name or ""))
    return f"{m.group(1)}_{{{m.group(2)}}}" if m else str(name or "")


def _vc(nid: str) -> str:
    """节点电压符号：n1 → V_{n1}；参考节点 → 0。"""
    return "0" if nid == "0" else f"V_{{{nid}}}"


def _isym(component: str) -> str:
    """支路电流符号：I_{R1}。"""
    return f"I_{{{component}}}"


def _branch_current_latex(t: str, component: str, node_p: str, node_n: str) -> str:
    """该支路电流用「节点电压」表示的式子——只保留一层分数，新手一眼能看懂。"""
    sym = _isym(component)
    if t == "resistor":
        return f"{sym}=\\frac{{{_vc(node_p)}-{_vc(node_n)}}}{{{_lsym(component)}}}"
    if t == "isource":
        return f"{sym}=\\text{{电流源，题目已给定}}"
    return f"{sym}=\\text{{待求（由节点方程定出）}}"


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
    """KCL：**先用支路电流符号写一行方程**，再单独给出每条电流的表达式（新手友好，不再嵌套成一大串）。"""
    res = _solve(session_id, "both")
    if res is None:
        return {"error": "当前会话没有电路。"}
    terms: List[str] = []
    detail: List[Dict[str, Any]] = []
    for b in res.branches:
        if b.node_p != node and b.node_n != node:
            continue
        leaving = b.node_p == node                  # 参考方向 p0→p1：从本节点出发即"离开"
        sym = _isym(b.component)
        terms.append(("+ " if leaving else "- ") + sym)
        detail.append({
            "component": b.component,
            "sym": sym,
            "leaving": leaving,
            "current": b.current,
            "expr_latex": _branch_current_latex(b.type, b.component, b.node_p, b.node_n),
            "full_latex": b.current_latex,
        })
    if not terms:
        return {"error": f"节点 {node} 没有支路。"}
    expr = " ".join(terms).lstrip("+ ").strip()
    return {
        "node": node,
        "kcl_latex": expr + " = 0",
        "branch_currents": detail,
        "description": "离开节点的电流代数和为零（KCL）。先按支路电流符号写出方程，再把各电流表达式代入求解。",
    }


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


def solve_unknowns_with_conditions(session_id: str, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """通用条件求解：图上留空的元件（未知量）+ 若干条「某量 = 某值」→ 解出代数值。

    例：conditions=[{"kind":"node_voltage","ref":"n2","value":2}] 表示「V_n2 = 2 V」。
    未知量个数、条件条数都不限。
    """
    from .constraints import solve_constraints

    return solve_constraints(session_id, conditions or [])


def solve_component_for_target(
    session_id: str, component: str, target_kind: str, target_ref: str, target_value: Any
) -> Dict[str, Any]:
    """逆运算：已知目标量（节点电压/支路电流）→ 反推某元件的数值。

    例：component=R5, target_kind=node_voltage, target_ref=n2, target_value=2
        → 求使 V_n2 = 2V 的 R5。
    """
    from .inverse import solve_for_component_value

    return solve_for_component_value(session_id, component, target_kind, target_ref, target_value)


def node_detail(session_id: str, node: str) -> Dict[str, Any]:
    """节点探针：电压、相关支路电流、KCL 方程与计算方法（供前端点击节点时展示）。"""
    res = _solve(session_id, "both")
    if res is None:
        return {"error": "当前会话没有电路。"}
    if node not in res.nodes:
        return {"error": f"节点 {node} 不存在。", "available": res.node_order}

    n = res.nodes[node]
    ref = "0" if "0" in res.nodes else next((k for k, v in res.nodes.items() if v.voltage == 0.0), "0")
    branch_rows: List[Dict[str, Any]] = []
    terms: List[str] = []
    for b in res.branches:
        if b.node_p != node and b.node_n != node:
            continue
        leaving = b.node_p == node          # 参考方向 p0→p1，从 node 出发即为"离开"
        sym = _isym(b.component)
        terms.append(("+ " if leaving else "- ") + sym)
        branch_rows.append({
            "component": b.component,
            "type": b.type,
            "sym": sym,
            "expr": _branch_current_latex(b.type, b.component, b.node_p, b.node_n),
            "current": b.current,
            "current_latex": b.current_latex,
            "node_p": b.node_p,
            "node_n": b.node_n,
            "leaving": leaving,
        })

    kcl = (" ".join(terms).lstrip("+ ").strip() + " = 0") if terms else ""

    # 分步讲解（新手友好）：选参考点 → 支路电流起名 → 一行 KCL → 代入求解
    steps: List[Dict[str, Any]] = [
        {
            "title": "① 选参考点（地）",
            "text": "把接地点（或自动选定的参考节点）的电位记作 0 V，其余节点电压都是相对它的值。",
            "latex": f"V_{{{ref}}}=0",
        },
        {
            "title": "② 给每条支路电流起名字，并用节点电压表示",
            "text": "电阻用欧姆定律：电流 =（两端电位差）÷ 电阻。先把每条电流写成一个符号，下一步写方程就简单了。",
            "table": [
                {
                    "sym": r["sym"],
                    "expr": r["expr"],
                    "dir": f"{r['node_p']}→{r['node_n']}",
                    "leaving": r["leaving"],
                    "value": r["current"],
                }
                for r in branch_rows
            ],
        },
        {
            "title": "③ 对这个节点列 KCL",
            "text": "规定「离开节点的电流记正号」，把②里的电流符号相加，令它等于 0。这一步故意不展开，保持一行，才看得清结构。",
            "latex": kcl,
        },
        {
            "title": "④ 把②代入③，联立解出该节点电压",
            "text": "代入后得到关于节点电压的方程（若含未知量则保留符号），解出即可。",
            "latex": (f"V_{{{node}}}={n.voltage_latex}" if n.voltage_latex else f"V_{{{node}}}=\\text{{—（无符号式）}}"),
            "value": n.voltage,
        },
    ]

    return {
        "node": node,
        "is_ground": node == "0",
        "voltage": n.voltage,
        "voltage_expr": n.voltage_expr,
        "voltage_latex": n.voltage_latex,
        "branches": branch_rows,
        "kcl_latex": kcl,
        "steps": steps,
        "method": (
            "节点电压法（KCL）：以该节点电位为未知量，对节点列写 KCL —— "
            "离开节点的各支路电流代数和为 0；每条支路电流再由元件的 VCR（欧姆定律）"
            "表示为节点电压之差的函数，联立方程组即可解出该节点电压。"
        ),
        "method_latex": r"\sum_k I_k = 0 \quad\Rightarrow\quad \sum_k \frac{V_{node}-V_{k}}{R_k} + \sum I_{src} = 0",
    }
