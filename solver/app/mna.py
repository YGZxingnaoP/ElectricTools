"""数值求解：改进节点分析（MNA），纯 numpy。实时主求解器。

符号约定：
- 支路电流参考方向 = 第一引脚(p) → 第二引脚(n)（被动符号约定）。
- 电压源 V(n+) - V(n-) = value；其支路电流参考方向 p→n。
- 电流源 I(n+ n-)：向节点 p 注入 +I（lcapy 语义，实测 I1 1 0 1 → V(1)=+1）。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

SUPPORTED = {"resistor", "vsource", "isource"}


class MnaError(Exception):
    pass


def solve_dc(
    nodes: Dict[str, dict], branches: List[dict], ground: str = "0"
) -> Tuple[Dict[str, float], Dict[str, float]]:
    node_ids = [n for n in nodes.keys() if n != ground]
    idx = {n: i for i, n in enumerate(node_ids)}
    m = len(node_ids)

    vsrc_row: Dict[int, int] = {}
    k = 0
    for i, br in enumerate(branches):
        if br["type"] == "vsource":
            vsrc_row[i] = m + k
            k += 1
    size = m + k
    if size == 0:
        raise MnaError("空电路：没有可求解的节点或源。")

    A = np.zeros((size, size), dtype=float)
    b = np.zeros(size, dtype=float)

    def gi(nid: str) -> int:
        return -1 if nid == ground else idx[nid]

    for i, br in enumerate(branches):
        t = br["type"]
        val = br.get("value")
        if t not in SUPPORTED:
            raise MnaError(f"暂不支持的元件类型：{t}")
        p, n = gi(br["node_p"]), gi(br["node_n"])

        if t == "resistor":
            if not val:
                raise MnaError(f"电阻 {br['component']} 阻值为零或缺失。")
            g = 1.0 / float(val)
            if p >= 0:
                A[p, p] += g
            if n >= 0:
                A[n, n] += g
            if p >= 0 and n >= 0:
                A[p, n] -= g
                A[n, p] -= g
        elif t == "isource":
            if val is None:
                raise MnaError(f"电流源 {br['component']} 数值缺失。")
            if p >= 0:
                b[p] += float(val)
            if n >= 0:
                b[n] -= float(val)
        elif t == "vsource":
            if val is None:
                raise MnaError(f"电压源 {br['component']} 数值缺失。")
            r = vsrc_row[i]
            if p >= 0:
                A[p, r] += 1.0
                A[r, p] += 1.0
            if n >= 0:
                A[n, r] -= 1.0
                A[r, n] -= 1.0
            b[r] = float(val)

    try:
        x = np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise MnaError("电路方程奇异：可能浮空、缺少到地的通路，或电源短路。") from exc

    v: Dict[str, float] = {ground: 0.0}
    for nid, i in idx.items():
        v[nid] = float(x[i])

    cur: Dict[str, float] = {}
    for i, br in enumerate(branches):
        t = br["type"]
        if t == "resistor":
            cur[br["component"]] = (v[br["node_p"]] - v[br["node_n"]]) / float(br["value"])
        elif t == "vsource":
            cur[br["component"]] = float(x[vsrc_row[i]])
        elif t == "isource":
            cur[br["component"]] = -float(br["value"])
    return v, cur
