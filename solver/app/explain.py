"""公式拆解（新手友好）：把式子拆成若干「项」，每项再拆成分子 / 分母的「因子连乘」，
给出每个因子的值与单位、乘积结果，以及这么算的依据。

例：V_{n2} = \\frac{R_{2} V_{1}}{R_{1} + R_{2}} - \\frac{R_{1} V_{3}}{R_{1} + R_{2}}

    第 1 项  分子 R2 × V1  = 4 Ω × 8 V = 32 V·Ω
             分母 R1 + R2  = 4 Ω + 4 Ω = 8 Ω
             结果 32 V·Ω ÷ 8 Ω = 4 V
    依据：同一电流流过 R1、R2（串联），压降按阻值成正比分配 → 串联分压；
          两项相加 = 叠加定理（每个电源单独作用一项）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import sympy as sp

UNIT = {"resistor": "Ω", "vsource": "V", "isource": "A"}
CN = {"resistor": "电阻", "vsource": "电压源", "isource": "电流源"}
SRC = ("vsource", "isource")


# ---------- 小工具 ----------

def _flat(e: Any):
    """与 lcapy_solver._flatten 同一套通分逻辑。

    lcapy 按「域」给字典（DC 是 't'，AC 是频率），还可能是空字典 / 嵌套；
    空字典直接送进 sp.together 会让 sympy 报「非表达式参数」告警，这里一并兜住。
    """
    try:
        raw = e.expr
        for _ in range(3):
            if not isinstance(raw, dict):
                break
            vals = list(raw.values())
            raw = raw.get("t", vals[0] if vals else 0)
        return sp.cancel(sp.together(raw))
    except Exception:
        return None


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "?"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.4g}"


def _unit_text(units: Dict[str, int]) -> str:
    if not units:
        return ""
    # 欧姆定律化简：V/Ω = A、A·Ω = V、V/A = Ω
    if units == {"V": 1, "Ω": -1}:
        return "A"
    if units == {"A": 1, "Ω": 1}:
        return "V"
    if units == {"V": 1, "A": -1}:
        return "Ω"
    up = [f"{u}^{n}" if n != 1 else u for u, n in sorted(units.items()) if n > 0]
    dn = [f"{u}^{abs(n)}" if n != -1 else u for u, n in sorted(units.items()) if n < 0]
    return ("·".join(up) if up else "1") + ("/" + "·".join(dn) if dn else "")


def _mul_units(units: Dict[str, int], unit: str, power: int = 1) -> Dict[str, int]:
    if not unit:
        return units
    units[unit] = units.get(unit, 0) + power
    if units[unit] == 0:
        del units[unit]
    return units


def _merge(a: Dict[str, int], b: Dict[str, int], sign: int = 1) -> Dict[str, int]:
    for k, n in (b or {}).items():
        _mul_units(a, k, sign * n)
    return a


def _sym_meta_of(name: str, sym_meta: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    return sym_meta.get(name) or {}


def _sym_unit(name: str, sym_meta: Dict[str, Dict[str, str]]) -> str:
    return UNIT.get(_sym_meta_of(name, sym_meta).get("type") or "", "")


def _sym_desc(name: str, subs: Dict[str, Any], sym_meta: Dict[str, Dict[str, str]]) -> str:
    typ = _sym_meta_of(name, sym_meta).get("type") or ""
    unit = UNIT.get(typ, "")
    val = subs.get(name)
    if val is None:
        return f"{name}（{CN.get(typ, '未知量')}，未给数值）"
    return f"{name}（{CN.get(typ, '量')} {_fmt(float(val))} {unit}）".replace(" ）", "）")


class _Val:
    """一个子式的求值结果。"""

    __slots__ = ("value", "units", "text", "factors")

    def __init__(self, value: Optional[float], units: Dict[str, int], text: str,
                 factors: Optional[List[dict]] = None):
        self.value = value          # 数值（含未知量则 None）
        self.units = units or {}    # {单位: 次幂}
        self.text = text            # 代入数值后的展开文字，如 "4 Ω × 8 V"
        self.factors = factors or []  # 仅乘法层：逐因子明细


def _eval(e: Any, subs: Dict[str, Any], sym_meta: Dict[str, Dict[str, str]]) -> _Val:
    """递归求值：加法 / 乘法 / 幂 / 符号 / 数字。"""
    # 数字
    if e.is_Number:
        v = float(e)
        return _Val(v, {}, _fmt(v))
    # 符号
    if e.is_Symbol:
        name = str(e)
        unit = _sym_unit(name, sym_meta)
        raw = subs.get(name)
        units: Dict[str, int] = {}
        _mul_units(units, unit)
        if raw is None:
            return _Val(None, units, name)
        text = f"{_fmt(float(raw))} {unit}".strip()
        return _Val(float(raw), units, text)
    # 加法：如 R1 + R2（同类量相加 → 单位取一项，不能相加！）
    if isinstance(e, sp.Add):
        vals, texts, units = [], [], None
        for t in e.args:
            coeff, rest = t.as_coeff_Mul()
            sub = _eval(rest, subs, sym_meta)
            if sub.value is None:
                return _Val(None, sub.units, sp.latex(e))
            vals.append(float(coeff) * sub.value)
            if units is None:
                units = dict(sub.units)          # 单位是「各项共同的」，不是相加
            c = float(coeff)
            texts.append(sub.text if abs(c - 1) < 1e-12 else f"{_fmt(c)}×{sub.text}")
        return _Val(sum(vals), units or {}, " + ".join(texts))
    # 乘法：逐因子给明细
    if isinstance(e, sp.Mul):
        val, units, texts, factors = 1.0, {}, [], []
        ok = True
        for f in e.args:
            sub = _eval(f, subs, sym_meta)
            if sub.value is None:
                ok = False
            else:
                val *= sub.value
            _merge(units, sub.units)
            texts.append(sub.text)
            name = str(f) if f.is_Symbol else None
            factors.append({
                "latex": sp.latex(f),
                "value": sub.text,
                "desc": _sym_desc(name, subs, sym_meta) if name else "",
            })
        return _Val(val if ok else None, units, " × ".join(texts), factors)
    # 幂：R^2 之类
    base, exp = e.as_base_exp()
    sub = _eval(base, subs, sym_meta)
    n = int(exp) if exp.is_Integer else None
    if n is None or sub.value is None:
        return _Val(None, sub.units, sp.latex(e))
    units = dict(sub.units)
    for k in list(units):
        units[k] *= n
        if units[k] == 0:
            del units[k]
    return _Val(sub.value ** n, units, f"({sub.text})^{n}", sub.factors)
    # 兜底：尝试数值化，否则按未知处理（上一行不会执行到这里）


def _sum_side(e: Any) -> Optional[sp.Expr]:
    return e if isinstance(e, sp.Add) else None


def _basis(flat: Any, sym_meta: Dict[str, Dict[str, str]], n_terms: int) -> List[str]:
    """依据：能识别的套路点名，识别不了给通用说法。"""
    out: List[str] = []
    try:
        num, den = sp.fraction(flat)
        num = sp.expand(num)
        srcs = [s for s in flat.free_symbols if _sym_meta_of(str(s), sym_meta).get("type") in SRC]
        res_num = [s for s in num.free_symbols if _sym_unit(str(s), sym_meta) == "Ω"]
        if n_terms > 1 and len(srcs) >= 2:
            out.append(f"叠加定理：式子合并后是 {n_terms} 项，每项对应一个独立电源单独作用的结果"
                       "（算某个电源时，其余电压源短路、电流源开路），最后把各项相加。")
        if isinstance(den, sp.Add):
            args = list(den.args)
            plain_syms = all(a.is_Symbol and _sym_unit(str(a), sym_meta) == "Ω" for a in args)
            prods = all(isinstance(a, sp.Mul) for a in args)
            if plain_syms and len(args) == 2:
                out.append(f"分母 {sp.latex(den)} 就是同一电流流过的两个串联电阻之和 —— "
                           "串联时电流一样大，压降按阻值成正比分配（串联分压）。")
            elif plain_syms and len(args) >= 3:
                out.append("分母是同一电流流过的几个串联电阻之和 —— 串联分压。")
            elif prods and len(args) >= 2:
                out.append("分母是「电阻两两相乘再相加」的形式（如 R1R2 + R1R5 + R2R5）："
                           "这是节点方程组的系数行列式，可以理解成「每两个电阻并联一次」的结果之和。")
        # 只有「分母 = 两个电阻相加」且「分子是这两个电阻相乘」时，才叫并联等效
        if isinstance(den, sp.Add) and len(den.args) == 2 and all(a.is_Symbol for a in den.args) \
                and isinstance(num, sp.Mul) and set(num.free_symbols) == set(den.free_symbols):
            out.append("分子是两个电阻相乘、分母是它们相加 —— 这就是并联等效 R1R2/(R1+R2) 的来历。")
    except Exception:
        pass
    out.append("通用依据：对节点列 KCL（离开该节点的电流代数和 = 0），每条电流用欧姆定律 U = R·I 展开，"
               "联立解出节点电位；再回代求出各支路电流。")
    return out


def decompose(e: Any, subs: Dict[str, Any], sym_meta: Dict[str, Dict[str, str]]) -> Optional[dict]:
    """入口：表达式 → {den(共同分母), terms:[...], basis:[...]}"""
    flat = _flat(e)
    if flat is None:
        return None
    try:
        num, den = sp.fraction(flat)
        terms = sp.Add.make_args(sp.expand(num))
    except Exception:
        return None
    if len(terms) > 8:
        return {"den": None, "terms": [], "basis": _basis(flat, sym_meta, len(terms)), "too_many": True}

    den_is_one = str(den) == "1"
    den_val = _Val(1.0, {}, "1") if den_is_one else _eval(den, subs, sym_meta)

    out_terms: List[dict] = []
    for t in terms:
        coeff, rest = t.as_coeff_Mul()
        num_val = _eval(rest, subs, sym_meta)
        val = None
        if num_val.value is not None and den_val.value not in (None, 0):
            val = float(coeff) * num_val.value / den_val.value
        units = _merge({}, num_val.units)
        if not den_is_one:
            _merge(units, den_val.units, sign=-1)
        out_terms.append({
            "latex": sp.latex(t),
            "coeff": _fmt(float(coeff)),
            "num": {
                "latex": sp.latex(rest),
                "factors": num_val.factors,
                "text": num_val.text,
                "value": _fmt(num_val.value),
                "unit": _unit_text(num_val.units),
            },
            "result": {"value": _fmt(val), "unit": _unit_text(units)},
        })

    return {
        "den": None if den_is_one else {
            "latex": sp.latex(den),
            "text": den_val.text,
            "value": _fmt(den_val.value),
            "unit": _unit_text(den_val.units),
        },
        "terms": out_terms,
        "basis": _basis(flat, sym_meta, len(out_terms)),
        "too_many": False,
    }
