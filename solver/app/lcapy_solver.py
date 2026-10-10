"""符号求解：lcapy 适配器。

- 用符号值（V_1、R_1…）构建网表，得到分压/分流等符号式与 LaTeX；
- 通过 subs 代入实际数值得到数值，供与 MNA 交叉校验；
- 未知量（未填数值 / 用户填了占位符号）不代入，公式中保留该符号；
- ground：参考节点（真实地 0，或自动选的参考节点），在网表里映射为 lcapy 的 0。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from . import explain

PREFIX = {"resistor": "R", "vsource": "V", "isource": "I"}
_SYM_BAD = re.compile(r"[^0-9A-Za-z_]")

# --- 惰性导入：import lcapy 约 3.7 s，是启动瓶颈；改成首次用到时才导入（服务可秒起） ---
_Circuit = None


def _circuit_cls():
    global _Circuit
    if _Circuit is None:
        from lcapy import Circuit
        _Circuit = Circuit
    return _Circuit


def warmup() -> None:
    """预热：后台线程调用，把 lcapy 的导入代价提前付掉。"""
    _circuit_cls()


# --- 符号结果缓存：同一网表+同一组数值重复求解直接命中（编辑时高频重复） ---
_CACHE: Dict[Any, Dict[str, Any]] = {}
_CACHE_MAX = 128


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


def _flatten(e: Any):
    """通分合并（cancel）：把嵌套分数压成一层，公式对新手更可读。

    例：\\frac{-V_1 + \\frac{a}{b}}{R_1}  →  \\frac{...}{R_1(...)}（单个分式）
    失败则返回 None，调用方退回原始表达式。
    """
    try:
        import sympy as sp

        raw = e.expr
        if isinstance(raw, dict):           # lcapy 按「域」给字典：DC 是 't'，AC 是频率
            raw = raw.get("t")
            if raw is None:
                vals = list(e.expr.values())
                raw = vals[0] if vals else 0
        return sp.cancel(sp.together(raw))
    except Exception:
        return None


def _expr_text(e: Any) -> str:
    flat = _flatten(e)
    return str(flat) if flat is not None else str(e)


def _expr_latex(e: Any) -> str:
    flat = _flatten(e)
    if flat is None:
        return e.latex()
    try:
        import sympy as sp

        return sp.latex(flat)
    except Exception:
        return e.latex()


def _sub_latex(e: Any, subs: Dict[str, Any]) -> Any:
    """把已知元件数值代入后的 LaTeX —— 让学生看到「代入后长什么样」。

    ⚠ 两个坑：
    ① 不能拿 sp.Symbol('R1') 去匹配 lcapy 表达式里的符号：lcapy 的符号带 positive/real
       等假设，**不是同一个 sympy 对象**，subs() 会静默不匹配 —— 表现就是「代入已知数值」
       那一行原封不动、看着像根本没代入。必须用表达式自己的 free_symbols 建映射。
    ② 不能拿 lcapy 的 e.subs() 之后再通分：lcapy 的「域字典」会被塞进 Mul，sympy 会告警。
    """
    if not subs:
        return None
    flat = _flatten(e)
    if flat is None:
        return None
    try:
        import sympy as sp

        m = {s: sp.nsimplify(subs[str(s)]) for s in flat.free_symbols if str(s) in subs}
        if not m:
            return None
        return sp.latex(flat.subs(m))
    except Exception:
        return None


def build_netlist(branches: List[dict], ground: str = "0"):
    # ★ 含 R/V/I 以外的新器件（C/L/受控源/变压器/交流源）→ 走扩展网表构建器
    extra = {"capacitor", "inductor", "vcvs", "vccs", "ccvs", "cccs", "transformer", "switch"}
    has_ac = any((b.get("params") or {}).get("kind") in ("ac", "sin", "sine", "step")
                 or b.get("kind") in ("ac", "sin", "sine", "step") for b in branches)
    if has_ac or any(b.get("type") in extra for b in branches):
        from .branches_ext import enrich
        from .netlist_all import build as _build_all

        nl, name_of, subs, sym_meta, skipped = _build_all(enrich(branches), ground)
        return nl, name_of, subs, sym_meta
    return _build_netlist_basic(branches, ground)


def _build_netlist_basic(branches: List[dict], ground: str = "0"):
    lines: List[str] = []
    name_of: Dict[str, str] = {}
    subs: Dict[str, Any] = {}
    sym_meta: Dict[str, Dict[str, str]] = {}
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
        sym_meta[sym] = {"component": br.get("component"), "type": t}

        lines.append(f"{name} {_lc_node(br['node_p'], ground)} {_lc_node(br['node_n'], ground)} {sym}")
    return "\n".join(lines), name_of, subs, sym_meta


def solve_symbolic(nodes: Dict[str, dict], branches: List[dict], ground: str = "0") -> Dict[str, Any]:
    netlist, name_of, subs, sym_meta = build_netlist(branches, ground)
    if not netlist.strip():
        return {"netlist": "", "nodes": {}, "branches": {}, "ok": False, "error": "无可求解元件"}

    # 缓存键必须同时包含「数值」：网表文本只含符号名，改阻值不会改文本
    key = (netlist, ground, tuple(sorted(nodes.keys())),
           tuple(sorted((k, v) for k, v in subs.items())),
           tuple(sorted((k, v.get("type")) for k, v in sym_meta.items())))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit

    try:
        cct = _circuit_cls()(netlist)
    except Exception as exc:  # pragma: no cover
        return {"netlist": netlist, "nodes": {}, "branches": {}, "ok": False, "error": str(exc)}

    node_out: Dict[str, dict] = {}
    for nid in nodes:
        if nid == ground:
            continue
        try:
            e = cct[nid].V
            node_out[nid] = {
                "expr": _expr_text(e),
                "latex": _expr_latex(e),
                "latex_sub": _sub_latex(e, subs),
                "value": _safe_float(e, subs),
                "decomp": explain.decompose(e, subs, sym_meta),
            }
        except Exception as exc:  # pragma: no cover
            node_out[nid] = {"expr": None, "latex": None, "latex_sub": None, "value": None, "error": str(exc)}

    branch_out: Dict[str, dict] = {}
    for comp, name in name_of.items():
        try:
            e = cct[name].I
            branch_out[comp] = {
                "expr": _expr_text(e),
                "latex": _expr_latex(e),
                "latex_sub": _sub_latex(e, subs),
                "value": _safe_float(e, subs),
                "decomp": explain.decompose(e, subs, sym_meta),
            }
        except Exception as exc:  # pragma: no cover
            branch_out[comp] = {"expr": None, "latex": None, "value": None, "error": str(exc)}

    out = {"netlist": netlist, "nodes": node_out, "branches": branch_out, "ok": True, "error": None}
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()                # 简单限容：满则清空（缓存只是加速，丢了也正确）
    _CACHE[key] = out
    return out
