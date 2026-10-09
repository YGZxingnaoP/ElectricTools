"""端口级等效引擎（docs/architecture.md §5）：Thévenin / Norton / I-V 扫描。

用 MNA 数值实现（替代已移除的 PySpice 扫描）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .mna import MnaError, solve_dc

PROBE = "__probe__"


def _with_probe(branches: List[dict], a: str, b: str, value: float) -> List[dict]:
    return list(branches) + [
        {"component": PROBE, "type": "vsource", "node_p": a, "node_n": b, "value": float(value)}
    ]


def port_thevenin(nodes: Dict[str, dict], branches: List[dict], a: str, b: str) -> Dict[str, Optional[float]]:
    """返回 {voc, isc, rth}。参考方向：端口 a→b。"""
    if a == b:
        raise MnaError("端口两端为同一节点。")
    if a not in nodes or b not in nodes:
        raise MnaError("端口节点不存在。")

    v_open, _ = solve_dc(nodes, branches)
    voc = v_open[a] - v_open[b]

    v_short, i_short = solve_dc(nodes, _with_probe(branches, a, b, 0.0))
    isc = i_short[PROBE]

    rth: Optional[float]
    if abs(isc) > 1e-15:
        rth = voc / isc
    else:
        rth = None
    return {"voc": voc, "isc": isc, "rth": rth}


def port_norton(nodes: Dict[str, dict], branches: List[dict], a: str, b: str) -> Dict[str, Optional[float]]:
    th = port_thevenin(nodes, branches, a, b)
    return {"in": th["isc"], "rn": th["rth"]}


def port_iv_curve(
    nodes: Dict[str, dict], branches: List[dict], a: str, b: str,
    vmax: float = 10.0, steps: int = 101,
) -> List[Dict[str, float]]:
    """在端口加扫描电压源，返回 I-V 曲线。电流参考方向 a→b。"""
    pts: List[Dict[str, float]] = []
    n = max(2, int(steps))
    for i in range(n):
        vtest = -vmax + (2 * vmax) * i / (n - 1)
        try:
            _, cur = solve_dc(nodes, _with_probe(branches, a, b, vtest))
            pts.append({"v": vtest, "i": cur[PROBE]})
        except MnaError:
            continue
    return pts


def compare_iv(curve_a: List[Dict[str, float]], curve_b: List[Dict[str, float]], tol: float = 0.01) -> Dict:
    """比较两条 I-V 曲线（同 v 网格）的最大偏差。"""
    map_b = {round(p["v"], 6): p["i"] for p in curve_b}
    max_abs = 0.0
    max_rel = 0.0
    for p in curve_a:
        ib = map_b.get(round(p["v"], 6))
        if ib is None:
            continue
        d = abs(p["i"] - ib)
        max_abs = max(max_abs, d)
        denom = max(abs(p["i"]), abs(ib), 1e-12)
        max_rel = max(max_rel, d / denom)
    return {"equivalent": max_rel <= tol, "max_abs": max_abs, "max_rel": max_rel, "tol": tol}
