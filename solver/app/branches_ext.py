"""把 topology 支路 / solve.Br 统一成【符号网表构建器】要的形状（带全部端子与参数）。

要求**幂等**：同一个 dict 反复 enrich 结果不变（否则第二次会把 c0/p2/kind 全丢掉）。
"""
from __future__ import annotations

from typing import Any, Dict, List

_EXTRA_NODES = (("c0", "c0_node"), ("c1", "c1_node"), ("p2", "n2_node"), ("p3", "n3_node"))


def enrich(branches: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for br in branches:
        if hasattr(br, "id"):                       # solve.Br
            d: Dict[str, Any] = {"component": br.id, "type": br.type,
                                 "value": br.prm.get("value"), "symbol": br.prm.get("symbol")}
            nodes = dict(getattr(br, "n", None) or {})
            prm = dict(getattr(br, "prm", None) or {})
        else:                                       # topology 的 dict（可能已 enrich 过）
            d = dict(br)
            nodes = dict(br.get("nodes") or {})
            prm = dict(br.get("params") or {})
            if d.get("value") is None and prm.get("value") is not None:
                d["value"] = prm["value"]
            if not d.get("symbol") and prm.get("symbol"):
                d["symbol"] = prm["symbol"]

        if not d.get("node_p"):
            d["node_p"] = nodes.get("p0")
        if not d.get("node_n"):
            d["node_n"] = nodes.get("p1")
        for pin, key in _EXTRA_NODES:
            if nodes.get(pin) and not d.get(key):
                d[key] = nodes[pin]
        for k in ("kind", "phase", "control", "closed"):
            if d.get(k) is None and prm.get(k) is not None:
                d[k] = prm[k]
        if d.get("value") is None:
            for k in ("gain", "ratio"):
                if prm.get(k) is not None:
                    d["value"] = prm[k]
                    break
        out.append(d)
    return out
