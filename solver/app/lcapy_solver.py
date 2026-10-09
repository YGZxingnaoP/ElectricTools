"""符号求解：lcapy 适配器（见 docs/architecture.md §4.2）。

- 用符号值（V_1、R_1…）构建网表，得到分压/分流等符号式与 LaTeX；
- 通过 subs 代入实际数值得到数值，供与 MNA 交叉校验。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from lcapy import Circuit

PREFIX = {"resistor": "R", "vsource": "V", "isource": "I"}


def _extract_float(e: Any) -> float:
    """从 lcapy 表达式抽取数值（DC 电路落在 't' 域常数）。"""
    try:
        d = e.expr
    except Exception:
        return float(e)
    if isinstance(d, dict):
        if "t" in d:
            return float(d["t"])
        vals = [v for v in d.values()]
        return float(vals[0]) if vals else 0.0
    return float(d)


def build_netlist(branches: List[dict]) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    lines: List[str] = []
    name_of: Dict[str, str] = {}
    subs: Dict[str, Any] = {}
    counters: Dict[str, int] = {}
    for br in branches:
        t = br["type"]
        if t not in PREFIX:
            continue
        pre = PREFIX[t]
        counters[pre] = counters.get(pre, 0) + 1
        idx = counters[pre]
        name = f"{pre}{idx}"
        sym = f"{pre}_{idx}"
        name_of[br["component"]] = name
        subs[sym] = br.get("value")
        lines.append(f"{name} {br['node_p']} {br['node_n']} {sym}")
    return "\n".join(lines), name_of, subs


def solve_symbolic(nodes: Dict[str, dict], branches: List[dict]) -> Dict[str, Any]:
    netlist, name_of, subs = build_netlist(branches)
    if not netlist.strip():
        return {"netlist": "", "nodes": {}, "branches": {}, "ok": False, "error": "无可求解元件"}

    try:
        cct = Circuit(netlist)
    except Exception as exc:  # pragma: no cover
        return {"netlist": netlist, "nodes": {}, "branches": {}, "ok": False, "error": str(exc)}

    node_out: Dict[str, dict] = {}
    for nid in nodes:
        if nid == "0":
            continue
        try:
            e = cct[nid].V
            node_out[nid] = {
                "expr": str(e),
                "latex": e.latex(),
                "value": _extract_float(e.subs(subs)),
            }
        except Exception as exc:  # pragma: no cover
            node_out[nid] = {"expr": None, "latex": None, "value": None, "error": str(exc)}

    branch_out: Dict[str, dict] = {}
    for comp, name in name_of.items():
        try:
            e = cct[name].I
            branch_out[comp] = {
                "expr": str(e),
                "latex": e.latex(),
                "value": _extract_float(e.subs(subs)),
            }
        except Exception as exc:  # pragma: no cover
            branch_out[comp] = {"expr": None, "latex": None, "value": None, "error": str(exc)}

    return {"netlist": netlist, "nodes": node_out, "branches": branch_out, "ok": True, "error": None}
