"""频率响应扫描：在 f0~f1（对数）上逐点做正弦稳态分析，给出幅频/相频。

用来画 Bode 图、找谐振点（幅值峰/谷）、看滤波特性。
"""
from __future__ import annotations

import cmath
import math
from typing import Any, Dict, List

from .engine import AC, SolveError
from .engine import analyse as engine_analyse
from .solve import build_branches


def logspace(f0: float, f1: float, n: int) -> List[float]:
    f0, f1 = max(f0, 1e-6), max(f1, f0 * 1.0001)
    a, b = math.log10(f0), math.log10(f1)
    return [10 ** (a + (b - a) * i / (n - 1)) for i in range(n)]


def sweep(sch, topo, f0: float = 10.0, f1: float = 1e5, points: int = 61,
          kind: str = "reactive") -> Dict[str, Any]:
    """kind: reactive=只扫电容/电感上的量；all=所有节点电压+支路电流；node=只扫节点电压"""
    branches = build_branches(sch, topo.node_of_member)
    freqs = logspace(f0, f1, max(5, min(points, 401)))
    series: Dict[str, Dict[str, List[float]]] = {}
    ok_freq: List[float] = []
    for f in freqs:
        try:
            res = engine_analyse(topo.nodes, branches, domain=AC, freq=f)
        except SolveError:
            continue
        ok_freq.append(f)
        V, I = res["V"], res["I"]
        picks: Dict[str, Any] = {}
        if kind in ("all", "node"):
            for nid, v in V.items():
                if nid == "0":
                    continue
                picks[f"V({nid})"] = v
        if kind in ("all", "reactive"):
            for b in branches:
                if b.type in ("capacitor", "inductor"):
                    picks[f"I({b.id})"] = I.get(b.id, 0)
        for k, v in picks.items():
            c = complex(v)
            d = series.setdefault(k, {"mag": [], "phase": []})
            d["mag"].append(abs(c))
            d["phase"].append(math.degrees(cmath.phase(c)))
    # 只保留"有变化"的量（全平的曲线没意义）
    keep = {k: v for k, v in series.items()
            if v["mag"] and (max(v["mag"]) - min(v["mag"])) > 1e-12 * max(1.0, max(v["mag"]))}
    return {"freqs": ok_freq, "series": keep or series}
