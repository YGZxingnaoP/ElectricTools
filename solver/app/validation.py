"""校验层：交叉校验 + 物理不变量残差（承接原 PySpice 职责，见 docs/architecture.md §4.3）。"""
from __future__ import annotations

from typing import Dict, List

from .models import Diagnostic, ValidationResult


def cross_check(
    mna_voltages: Dict[str, float],
    lcapy_values: Dict[str, float],
    tol: float,
) -> ValidationResult:
    details: Dict[str, float] = {}
    max_abs = 0.0
    max_rel = 0.0
    for nid, v in mna_voltages.items():
        if nid == "0":
            continue
        lv = lcapy_values.get(nid)
        if lv is None:
            continue
        d = abs(v - lv)
        details[nid] = d
        max_abs = max(max_abs, d)
        denom = max(abs(lv), 1e-9)
        max_rel = max(max_rel, d / denom)

    ok = (max_rel <= tol) or (max_abs < 1e-9)
    notes: List[str] = []
    if not ok:
        notes.append("数值(MNA) 与 符号(lcapy) 结果存在偏差，请检查电路或元件取值。")
    return ValidationResult(
        ok=ok,
        max_abs_diff=max_abs,
        max_rel_diff=max_rel,
        tol=tol,
        details=details,
        notes=notes,
    )


def kcl_residuals(
    nodes: Dict[str, dict], branches: List[dict], voltages: Dict[str, float]
) -> Dict[str, float]:
    """每个节点 KCL 残差（注入电流之和，应≈0）。"""
    resid: Dict[str, float] = {}
    for nid in nodes:
        if nid == "0":
            continue
        total = 0.0
        for br in branches:
            t = br["type"]
            val = br.get("value")
            p, n = br["node_p"], br["node_n"]
            if t == "resistor" and val:
                i = (voltages.get(p, 0.0) - voltages.get(n, 0.0)) / float(val)  # p->n 离开 p
                if p == nid:
                    total -= i  # 离开节点
                if n == nid:
                    total += i
            elif t == "isource" and val is not None:
                if p == nid:
                    total += float(val)
                if n == nid:
                    total -= float(val)
            elif t == "vsource":
                # 电压源电流未知，跳过（残差仅作辅助）
                pass
        resid[nid] = total
    return resid
