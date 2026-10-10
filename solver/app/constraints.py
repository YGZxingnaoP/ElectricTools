"""通用「条件求解」：根据条件，推出未知量的代数值。

这不是绑在某个元件上的"目标值"，而是一个通用反解引擎：

    输入
      ① 电路：元件要么给数值（已知），要么留空（未知，可以有多个）
      ② 条件：任意多条「某个量 = 某个数」
         · 节点电压 = 值   （kind=node_voltage, ref=节点 ID）
         · 支路电流 = 值   （kind=branch_current, ref=元件 ID）
    过程
      1. 把所有未知元件符号化（x0, x1, …）
      2. 做一次符号求解，得到每条条件的量关于未知量的表达式 f_i(x)
      3. 代入已知元件的数值 → f_i 只含未知量
      4. 联立 f_i(x) = 目标值，解方程组
      5. 按物理意义筛选（电阻 > 0），并报告 无解 / 多解 / 欠定 / 超定
    输出
      每个未知量的代数值 + 可核对的分步推导

一般性：
    · 未知量个数、条件条数都不限（1 个未知量 1 条条件只是它的特例）；
    · 条件是"等式约束"，可以是题目里任何一个已知量；
    · 线性电路下，电压/电流对「元件数值」是分式线性函数，所以方程是一次/分式一次，
      用 sympy 精确求解即可，不依赖试凑。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

import sympy as sp

from .analysis import STORE, analyze
from .inverse import _lsym, parse_value
from .models import SolveRequest

UNIT = {"resistor": "Ω", "vsource": "V", "isource": "A"}


def _cond_expr(res, kind: str, ref: str):
    """取条件的量关于未知量的符号表达式（字符串）。"""
    if kind == "branch_current":
        br = next((b for b in res.branches if b.component == ref), None)
        if br is None:
            return None, f"元件 {ref} 不存在。"
        return br.current_expr, None
    nd = res.nodes.get(ref)
    if nd is None:
        return None, f"节点 {ref} 不存在。"
    return nd.voltage_expr, None


def _cond_label(kind: str, ref: str) -> str:
    return (f"I_{{{ref}}}" if kind == "branch_current" else f"V_{{{ref}}}")


def resolve_annotations(member_of: Dict[str, List[str]], annotations) -> tuple:
    """把图上的「已知量」标注（位置成员键）解析成条件列表。

    member_of: {节点ID: [成员键, …]}，由求解器给出，保证与当前节点编号一致。
    返回 (conditions, errors)。
    """
    to_node: Dict[str, str] = {}
    for nid, members in (member_of or {}).items():
        for m in members or []:
            to_node[m] = nid
    conds: List[Dict[str, Any]] = []
    errs: List[str] = []
    for a in annotations or []:
        key = str(getattr(a, "key", None) or (a or {}).get("key") or "")
        kind = str(getattr(a, "kind", None) or (a or {}).get("kind") or "node_voltage")
        val = getattr(a, "value", None) if not isinstance(a, dict) else a.get("value")
        if val is None:
            continue                                   # 还没填数值的标注先跳过
        if kind == "branch_current":
            comp = key.split(":", 1)[1] if key.startswith("c:") else key
            conds.append({"kind": "branch_current", "ref": comp, "value": val})
        else:
            nid = to_node.get(key)
            if nid is None:
                errs.append(f"标注（{key}）没能对应到某个节点")
                continue
            conds.append({"kind": "node_voltage", "ref": nid, "value": val})
    return conds, errs


def solve_constraints(session_id: str, conditions: List[Dict[str, Any]],
                      schematic=None) -> Dict[str, Any]:
    """通用条件求解主入口。conditions: [{kind, ref, value}, …]"""
    sch = schematic if schematic is not None else STORE.get_schematic(session_id)
    if sch is None:
        return {"error": "当前会话没有电路。"}

    conds = [c for c in (conditions or []) if (c or {}).get("ref")]
    from . import devices as _DEV
    unknowns = [c for c in sch.components
                if c.value is None and _DEV.takes_value(c.type)]
    if not unknowns:
        return {"error": "图上没有未知量：所有元件都已有数值。把要反推的元件数值清空（或填一个符号）即可。"}
    if not conds:
        return {
            "error": f"图上待求的量有 {len(unknowns)} 个（" + "、".join(c.id for c in unknowns)
                     + "），但没有给条件。每一条条件（例如「V_n2 = 2 V」）才能定出解，请至少给一条。",
            "unknowns": [c.id for c in unknowns],
        }

    # ① 未知量符号化（用**位号本身**当符号，公式里直接显示 R5，学生看得懂；原电路不动）
    sch2 = sch.model_copy(deep=True)
    sch2.conditions = []                 # ★ 防止递归：内部求解不再处理图上标注
    sym_of: Dict[str, str] = {}          # 元件 ID -> 符号名
    used: set = set()
    for c in unknowns:
        name = re.sub(r"[^0-9A-Za-z_]", "_", str(c.id)).strip("_") or "X"
        if name[0].isdigit():
            name = "X" + name
        while name in used:
            name += "_"
        used.add(name)
        sym_of[c.id] = name
        t = next(x for x in sch2.components if x.id == c.id)
        t.value = None
        t.symbol = name

    res = analyze(SolveRequest(session_id=session_id, schematic=sch2, mode="both"), True)
    if not res.ok:
        return {"error": "电路当前无法求解。", "diagnostics": [d.model_dump() for d in res.diagnostics]}

    # 已知元件数值（含用户自己写的符号？——只代入有数值的）
    subs = {sp.Symbol(c.id): sp.nsimplify(c.value)
            for c in sch.components if c.type != "ground" and c.value is not None}

    xs = [sp.Symbol(n) for n in sym_of.values()]
    eqs: List[Any] = []
    cond_rows: List[Dict[str, Any]] = []
    for cond in conds:
        kind = cond.get("kind") or "node_voltage"
        ref = str(cond.get("ref"))
        val = parse_value(cond.get("value"))
        if val is None:
            return {"error": f"条件值无法识别：{cond.get('value')!r}（可写 2、2k、2000mV 等）"}
        expr, err = _cond_expr(res, kind, ref)
        if err:
            return {"error": err, "available_nodes": res.node_order,
                    "available_branches": [b.component for b in res.branches]}
        if not expr:
            return {"error": f"{_cond_label(kind, ref)} 没有符号表达式（可能是参考点、纯数值或不可解）。"}
        try:
            f = sp.sympify(expr).subs(subs)
        except Exception as exc:
            return {"error": f"表达式解析失败：{exc}"}
        eqs.append(sp.Eq(f, sp.nsimplify(val)))
        cond_rows.append({"kind": kind, "ref": ref, "value": val,
                          "label": _cond_label(kind, ref),
                          "expr_latex": sp.latex(f)})

    # ④ 解方程组
    try:
        raw = sp.solve(eqs, xs, dict=True)
    except Exception as exc:
        return {"error": f"解方程组失败：{exc}", "equations": [sp.latex(e) for e in eqs]}

    if not raw:
        return {
            "error": "无解：这些条件同时满足不了（可能条件互相矛盾，或超出该电路能达到的范围）。",
            "equations": [sp.latex(e) for e in eqs],
        }

    # 解里若还含自由符号 → 欠定
    solutions: List[Dict[str, Any]] = []
    for sol in raw:
        free = set().union(*[s.free_symbols for s in sol.values()]) if sol else set()
        free -= set(xs)
        if free:
            return {
                "error": "欠定：条件不足，未知量还留有关系式 —— "
                         + ", ".join(f"{k}={sp.latex(v)}" for k, v in sol.items()),
                "equations": [sp.latex(e) for e in eqs],
            }
        row: Dict[str, Any] = {}
        feasible = True
        for cid, sname in sym_of.items():
            x = sp.Symbol(sname)
            v = sol.get(x)
            if v is None:
                feasible = False
                continue
            try:
                if sp.im(sp.nsimplify(v)) != 0:
                    feasible = False
                    continue
                fv = float(sp.re(v))
            except Exception:
                feasible = False
                continue
            comp = next(c for c in sch.components if c.id == cid)
            note = ""
            if comp.type == "resistor" and fv <= 0:
                feasible, note = False, "电阻必须大于 0"
            row[cid] = {"value": fv, "unit": UNIT.get(comp.type, ""),
                        "type": comp.type, "feasible": feasible, "note": note}
        solutions.append({"feasible": feasible, "values": row})

    solutions.sort(key=lambda s: not s["feasible"])

    # ⑤ 分步推导（可核对）
    steps: List[Dict[str, Any]] = [
        {
            "title": "① 找出待求的量",
            "text": "图上数值为空的元件就是要反推的未知量。",
            "latex": ",\\quad ".join(_lsym(c.id) for c in unknowns),
        },
        {
            "title": "② 把条件写成关于未知量的式子",
            "text": "对电路做符号求解，再把已知元件的数值代进去，每条条件就变成只含未知量的式子。",
            "table": [{"label": r["label"], "expr": r["expr_latex"],
                       "value": r["value"]} for r in cond_rows],
        },
        {
            "title": "③ 令它们等于题目给的值，得到方程组",
            "text": "未知量 " + str(len(xs)) + " 个，条件 " + str(len(eqs)) + " 条。",
            "latex": " \\quad ".join(sp.latex(e) for e in eqs),
        },
        {
            "title": "④ 解方程组，取物理可行解",
            "text": "解出未知量；电阻取正值，电源允许为负（表示极性与参考方向相反）。",
            "latex": ",\\quad ".join(
                f"{_lsym(cid)}={info['value']:g}\\ \\text{{{info['unit']}}}"
                for cid, info in (solutions[0]["values"].items() if solutions else [])
                if info["feasible"]
            ) or "\\text{—（无可行解）}",
        },
    ]

    return {
        "ok": True,
        "unknowns": [{"id": c.id, "symbol": sym_of[c.id], "type": c.type} for c in unknowns],
        "conditions": cond_rows,
        "equations": [sp.latex(e) for e in eqs],
        "solutions": solutions,
        "steps": steps,
    }
