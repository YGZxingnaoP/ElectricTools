"""符号求解：lcapy 适配器（见 docs/architecture.md §4.2）。

- 用符号值（V_1、R_1…）构建网表，得到分压/分流等符号式与 LaTeX；
- 通过 subs 代入实际数值得到数值，供与 MNA 交叉校验；
- 未知量（未填数值 / 用户填了占位符号）不代入，公式中保留该符号；
- ground：参考节点（真实地 0，或自动选的参考节点），在网表里映射为 lcapy 的 0。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from lcapy import Circuit

PREFIX = {"resistor": "R", "vsource": "V", "isource": "I"}
_SYM_BAD = re.compile(r"[^0-9A-Za-z_]")


def _symbol_name(raw: Any) -> str:
    """把用户填的占位文字清洗成合法的符号名（如 "R?"→"R_"，"1x"→"X1x"）。"""
    s = _SYM_BAD.sub("_", str(raw or "").strip()).strip("_") or "X"
    if s[0].isdigit():
        s = "X" + s
    return s


def _lc_node(nid: str, ground: str) -> str:
    return "0" if nid == ground else nid


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


def _safe_float(e: Any, subs: Dict[str, Any]):
    """代入已知数值取数；若仍含未知量则返回 None。"""
    try:
        return _extract_float(e.subs(subs))
    except Exception:
        return None


def build_netlist(branches: List[dict], ground: str = "0") -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    lines: List[str] = []
    name_of: Dict[str, str] = {}
    subs: Dict[str, Any] = {}
    counters: Dict[str, int] = {}
    used: set = set()
    for br in branches:
        t = br["type"]
        if t not in PREFIX:
            continue
        pre = PREFIX[t]
        counters[pre] = counters.get(pre, 0) + 1
        idx = counters[pre]
        # 元件名必须保留类型首字母（lcapy 依据首字母判断元件类型：R/L/C/V/I…）
        name = f"{pre}{idx}"
        name_of[br["component"]] = name

        val = br.get("value")
        sym_raw = br.get("symbol")
        if sym_raw:
            # 用户显式填的占位符号：不代入数值；允许两个元件同名（表示同一个未知量）
            sym = _symbol_name(sym_raw)
        else:
            # 否则用**真实位号**作为参数符号，公式里就直接显示 R1 / V3 / R_load
            sym = _symbol_name(br.get("component")) or f"{pre}_{idx}"
            n = 2
            while sym in used:            # 位号清洗后可能撞名，加后缀保证唯一
                sym = f"{_symbol_name(br.get('component'))}_{n}"
                n += 1
        used.add(sym)
        if val is not None:
            subs[sym] = val

        lines.append(f"{name} {_lc_node(br['node_p'], ground)} {_lc_node(br['node_n'], ground)} {sym}")
    return "\n".join(lines), name_of, subs


def solve_symbolic(nodes: Dict[str, dict], branches: List[dict], ground: str = "0") -> Dict[str, Any]:
    netlist, name_of, subs = build_netlist(branches, ground)
    if not netlist.strip():
        return {"netlist": "", "nodes": {}, "branches": {}, "ok": False, "error": "无可求解元件"}

    try:
        cct = Circuit(netlist)
    except Exception as exc:  # pragma: no cover
        return {"netlist": netlist, "nodes": {}, "branches": {}, "ok": False, "error": str(exc)}

    node_out: Dict[str, dict] = {}
    for nid in nodes:
        if nid == ground:
            continue
        try:
            e = cct[nid].V
            node_out[nid] = {
                "expr": str(e),
                "latex": e.latex(),
                "value": _safe_float(e, subs),
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
                "value": _safe_float(e, subs),
            }
        except Exception as exc:  # pragma: no cover
            branch_out[comp] = {"expr": None, "latex": None, "value": None, "error": str(exc)}

    return {"netlist": netlist, "nodes": node_out, "branches": branch_out, "ok": True, "error": None}
