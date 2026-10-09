"""端口级等效引擎（docs/architecture.md §5）：Thévenin / Norton / I-V 扫描。

用 MNA 数值实现（替代已移除的 PySpice 扫描）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .mna import MnaError, solve_dc

PROBE = "__probe__"


def _pick_ground(nodes: Dict[str, dict], ground: Optional[str] = None) -> str:
    """参考节点：给定则用；否则优先真实地(0)，再否则取连接最多的节点（与主求解器一致）。"""
    if ground and ground in nodes:
        return ground
    if "0" in nodes and nodes["0"].get("is_ground"):
        return "0"
    if not nodes:
        return ground or "0"
    return sorted(nodes.keys(), key=lambda n: (-len(nodes[n].get("members", [])), n))[0]


def _filter(branches: List[dict], exclude: Optional[List[str]]) -> List[dict]:
    """剔除指定元件（例如要测"负载"端口时把负载本身移走）。"""
    if not exclude:
        return list(branches)
    drop = {str(x) for x in exclude}
    return [b for b in branches if b.get("component") not in drop]


def _with_probe(branches: List[dict], a: str, b: str, value: float) -> List[dict]:
    return list(branches) + [
        {"component": PROBE, "type": "vsource", "node_p": a, "node_n": b, "value": float(value)}
    ]


def port_thevenin(
    nodes: Dict[str, dict], branches: List[dict], a: str, b: str,
    ground: Optional[str] = None, exclude: Optional[List[str]] = None,
) -> Dict[str, Optional[float]]:
    """返回 {voc, isc, rth}。参考方向：端口 a→b。可 exclude 掉某些元件（如被求的负载）。"""
    if a == b:
        raise MnaError("端口两端为同一节点。")
    if a not in nodes or b not in nodes:
        raise MnaError("端口节点不存在。")

    brs = _filter(branches, exclude)
    g = _pick_ground(nodes, ground)

    v_open, _ = solve_dc(nodes, brs, ground=g)
    voc = v_open[a] - v_open[b]

    v_short, i_short = solve_dc(nodes, _with_probe(brs, a, b, 0.0), ground=g)
    isc = i_short[PROBE]

    rth: Optional[float]
    if abs(isc) > 1e-15:
        rth = voc / isc
    else:
        rth = None
    return {"voc": voc, "isc": isc, "rth": rth}


def port_norton(
    nodes: Dict[str, dict], branches: List[dict], a: str, b: str,
    ground: Optional[str] = None, exclude: Optional[List[str]] = None,
) -> Dict[str, Optional[float]]:
    th = port_thevenin(nodes, branches, a, b, ground=ground, exclude=exclude)
    return {"in": th["isc"], "rn": th["rth"]}


def port_iv_curve(
    nodes: Dict[str, dict], branches: List[dict], a: str, b: str,
    vmax: float = 10.0, steps: int = 101,
    ground: Optional[str] = None, exclude: Optional[List[str]] = None,
) -> List[Dict[str, float]]:
    """在端口加扫描电压源，返回 I-V 曲线。电流参考方向 a→b。"""
    brs = _filter(branches, exclude)
    g = _pick_ground(nodes, ground)
    pts: List[Dict[str, float]] = []
    n = max(2, int(steps))
    for i in range(n):
        vtest = -vmax + (2 * vmax) * i / (n - 1)
        try:
            _, cur = solve_dc(nodes, _with_probe(brs, a, b, vtest), ground=g)
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
