"""逆运算求解：已知**目标量**（节点电压 / 支路电流），反推**某元件**的数值。

分四步（与界面展示的步骤一一对应）：
    ① 把待求元件当成未知量 x（复用「未知量占位」机制，不改动原电路）
    ② 符号求解，得到目标量的表达式 f(x)
    ③ 令 f(x) = 题目给出的目标值 —— 得到一个一次方程
    ④ 解出 x，并按物理意义筛掉不可行解（电阻必须为正）

为什么一定解得出来：
    电路是线性的 ⇒
      · 反推「电压源/电流源数值」时，f 是 x 的**线性函数** α+βx；
      · 反推「电阻值」时，f 是 R 的**分式线性函数** (a+bR)/(c+dR)。
    两者都只归结为一次方程，故解唯一（除非 β=0，即目标量与 x 无关）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import sympy as sp

from .analysis import STORE, analyze
from .models import SolveRequest

UNIT = {"resistor": "Ω", "vsource": "V", "isource": "A"}
_SI = {"k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12}
_NUM = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-zA-ZµΩ]*)$")


def _lsym(name: str) -> str:
    """R1 → R_{1}；R_load → R_{load}。"""
    m = re.match(r"^([A-Za-z_]+)(\d+)$", str(name or ""))
    return f"{m.group(1)}_{{{m.group(2)}}}" if m else str(name or "")


def _vc(nid: str) -> str:
    return "0" if nid == "0" else f"V_{{{nid}}}"


def parse_value(raw: Any) -> Optional[float]:
    """把 '2'、'2k'、'2 kΩ'、'2000mV'、'2.5A' 解析成 SI 数值。"""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw or "").strip().replace(" ", "")
    if not s:
        return None
    m = _NUM.match(s)
    if not m:
        try:
            return float(s)
        except ValueError:
            return None
    num = float(m.group(1))
    suf = m.group(2)
    if suf:
        head = suf[0]
        if head in _SI:
            num *= _SI[head]
    return num


def _fresh_symbol(sch) -> str:
    """挑一个没被占用的符号名（避免和位号/已有符号冲突）。"""
    used = {str(c.id) for c in sch.components} | {str(c.symbol) for c in sch.components if c.symbol}
    for cand in ("x", "y", "z", "w", "u", "v"):
        if cand not in used:
            return cand
    return "xx"


def solve_for_component_value(
    session_id: str,
    component: str,
    target_kind: str,
    target_ref: str,
    target_value: Any,
) -> Dict[str, Any]:
    """主入口。target_kind: node_voltage | branch_current。"""
    sch = STORE.get_schematic(session_id)
    if sch is None:
        return {"error": "当前会话没有电路。"}

    comp = next((c for c in sch.components if c.id == component), None)
    if comp is None:
        return {"error": f"元件 {component} 不存在。", "available": [c.id for c in sch.components]}
    if comp.type not in UNIT:
        return {"error": f"只能反推 电阻/电压源/电流源 的数值（当前是 {comp.type}）。"}
    unit = UNIT[comp.type]

    value = parse_value(target_value)
    if value is None:
        return {"error": f"目标值无法识别：{target_value!r}（可写 2、2k、2000mV 等）"}

    # 电路里若还有别的未知量，一个条件解不出两个未知量
    others = [c.id for c in sch.components if c.value is None and c.type != "ground" and c.id != component]
    if others:
        return {"error": "电路里还有其它未知量（" + "、".join(others) + "），请先补全它们的数值，再反推。"}
    if target_kind == "branch_current" and target_ref == component:
        return {"error": "目标支路不能就是待求元件本身。"}

    # ① 复制一份电路，把待求元件标记为未知量 x（原电路不动）
    sch2 = sch.model_copy(deep=True)
    tgt_comp = next(c for c in sch2.components if c.id == component)
    xname = _fresh_symbol(sch2)
    tgt_comp.value = None
    tgt_comp.symbol = xname

    # ② 符号求解（与主求解器同一套代码，节点编号沿用本会话，保持一致）
    res = analyze(SolveRequest(session_id=session_id, schematic=sch2, mode="both"), True)
    if not res.ok:
        return {"error": "电路当前无法求解。", "diagnostics": [d.model_dump() for d in res.diagnostics]}

    if target_kind == "branch_current":
        br = next((b for b in res.branches if b.component == target_ref), None)
        if br is None:
            return {"error": f"元件 {target_ref} 不存在。", "available": [b.component for b in res.branches]}
        expr, expr_latex = br.current_expr, br.current_latex
        tgt_sym = f"I_{{{target_ref}}}"
        tgt_desc = f"{target_ref} 的电流（参考方向 {br.node_p}→{br.node_n}）"
    else:
        if target_ref not in res.nodes:
            return {"error": f"节点 {target_ref} 不存在。", "available": res.node_order}
        nd = res.nodes[target_ref]
        expr, expr_latex = nd.voltage_expr, nd.voltage_latex
        tgt_sym = f"V_{{{target_ref}}}"
        tgt_desc = f"{target_ref} 的节点电压（相对参考点）"

    if not expr:
        if target_kind == "node_voltage" and (res.nodes[target_ref].voltage == 0.0):
            return {"error": f"{target_ref} 是参考节点（电位恒为 0 V），不能作为反推目标，请换一个节点。"}
        return {"error": "符号求解没有给出表达式，无法反推（该量可能是纯数值，或电路不可解）。"}

    xs = sp.Symbol(xname)
    try:
        f_sym = sp.sympify(expr)                    # 含「已知量符号」的表达式
    except Exception as exc:  # pragma: no cover
        return {"error": f"表达式解析失败：{exc}", "expr": expr}

    # 目标量与未知量无关 → 无法反推
    if not f_sym.has(xs):
        return {
            "error": f"{tgt_desc}与 {component} 无关：{component} 取任何值，{tgt_sym} 都不变，因此无法反推。",
            "expr_latex": expr_latex,
        }

    # ★ 关键：把已知元件代入（否则方程里还留着 V_1、R_1 这些符号，解不出数）
    subs_map = {
        sp.Symbol(c.id): sp.nsimplify(c.value)
        for c in sch.components
        if c.id != component and c.type != "ground" and c.value is not None
    }
    f = f_sym.subs(subs_map)

    extra = f.free_symbols - {xs}
    if extra:
        return {
            "error": "表达式里仍含未知符号：" + "、".join(sorted(str(s) for s in extra))
                     + "。请先补全这些元件的数值再反推。",
            "expr_latex": expr_latex,
        }

    # ③ 令 f(x) = 目标值（用有理数精确求解，避免浮点误差）
    try:
        rhs = sp.nsimplify(value)
    except Exception:
        rhs = sp.Float(value)
    try:
        raw_sols = sp.solve(sp.Eq(f, rhs), xs)
    except Exception as exc:  # pragma: no cover
        return {"error": f"解方程失败：{exc}", "expr_latex": expr_latex}

    if not raw_sols:
        return {
            "error": f"无解：{component} 取任何（物理可行的）值都无法让 {tgt_sym} = {value:g} {unit_target(target_kind)}。",
            "expr_latex": expr_latex,
        }

    # ④ 过滤：丢掉复数解、非实数解；电阻还要求 > 0
    solutions: List[Dict[str, Any]] = []
    for s in raw_sols:
        try:
            if getattr(s, "is_real", None) is False:
                continue
            if sp.im(sp.nsimplify(s)) != 0:
                continue
            sv = float(sp.re(s))
        except Exception:
            continue
        feasible, note = True, ""
        if comp.type == "resistor":
            if sv <= 0:
                feasible, note = False, "电阻必须大于 0，该解不可用"
            elif sv == 0:
                feasible, note = False, "电阻为 0 相当于短路"
        elif abs(sv) < 1e-15:
            note = "数值为 0（该电源不起作用）"
        solutions.append({"value": sv, "unit": unit, "feasible": feasible, "note": note})

    if not solutions:
        return {
            "error": "解不是实数或不符合物理意义，无法给出可用结果（常见原因：目标值超出该电路可达范围）。",
            "expr_latex": expr_latex,
        }

    solutions.sort(key=lambda s: (not s["feasible"], abs(s["value"])))
    ok_sols = [s for s in solutions if s["feasible"]]

    # ④ 去分母后的一次方程（写出来，新手才好照着做）
    try:
        num, _den = sp.fraction(sp.together(f - rhs))
        linear_latex = f"{sp.latex(sp.expand(num))}=0"
    except Exception:  # pragma: no cover
        linear_latex = None

    # 推导步骤（5 步，与节点探针同一套「分步」风格）
    steps: List[Dict[str, Any]] = [
        {
            "title": "① 把待求元件设为未知量",
            "text": f"令 {component} = {xname}（与「未知量占位」同一机制，不改变原电路）。",
            "latex": f"{_lsym(component)}={xname}",
        },
        {
            "title": "② 符号求解，写出目标量的表达式",
            "text": f"对含未知量 {xname} 的电路做符号求解，得到 {tgt_desc} 的表达式（此时已知量还是符号）。",
            "latex": f"{tgt_sym}={sp.latex(f_sym)}",
        },
        {
            "title": "③ 代入已知数值",
            "text": "把题目给的已知量（电源值、电阻值）代进去，式子里就只剩未知量 x 了。",
            "latex": f"{tgt_sym}={sp.latex(f)}",
        },
        {
            "title": "④ 令目标量等于题目要求的值",
            "text": "把③的式子等于目标值；两边同乘分母，就化成一个一次方程。",
            "latex": f"{sp.latex(f)}={sp.latex(rhs)}",
            "latex2": linear_latex,
            "text2": "两边同乘分母并整理后的一次方程：" if linear_latex else "",
        },
        {
            "title": "⑤ 解一次方程，取物理可行解",
            "text": "解出未知量。电阻必须为正；电源允许为负（表示实际极性与参考方向相反）。",
            "latex": ",\\quad ".join(
                f"{xname}={s['value']:g}\\ \\text{{{s['unit']}}}" for s in ok_sols
            ) or f"{xname}=\\text{{—（无可行解）}}",
        },
    ]

    return {
        "ok": True,
        "component": component,
        "component_type": comp.type,
        "symbol": xname,
        "target": {"kind": target_kind, "ref": target_ref, "value": value,
                   "unit": unit_target(target_kind), "desc": tgt_desc},
        "expr": str(f),
        "expr_latex": sp.latex(f),
        "expr_symbolic_latex": sp.latex(f_sym),
        "target_latex": f"{tgt_sym}={value:g}",
        "solutions": solutions,
        "values": [s["value"] for s in ok_sols],
        "steps": steps,
    }


def unit_target(kind: str) -> str:
    return "A" if kind == "branch_current" else "V"
