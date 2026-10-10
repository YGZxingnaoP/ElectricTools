"""上下文构造：系统提示词 + 电路状态块 + @节点注入。"""
from __future__ import annotations

from typing import Any, List, Optional

SYSTEM_PROMPT = (
    "你是一名电路分析助教，面向大学《电路分析》课程的本科生。\n"
    "工作规则：\n"
    "1. 你必须调用提供的工具获取电路的精确数据（节点电压、支路电流、KCL 方程、"
    "戴维南/诺顿等效），不得凭空猜测数值。\n"
    "2. 电流采用『参考方向』（关联参考方向 / 被动符号约定）：支路参考方向为 p0→p1；"
    "数值为负表示实际方向与参考方向相反。讲解时请沿用此记号。\n"
    "3. 回答请使用 **Markdown** 排版（标题、列表、表格、代码块），数学式子用 LaTeX 且"
    "包在美元符号中：行内用 $...$，独立成行用 $$...$$（例如 $V_{n1}=\\frac{R_2 V_1}{R_1+R_2}$）。\n"
    "4. 解释应简明、分步骤。\n"
    "5. 若电路无法求解（缺少参考地、元件缺值等），如实说明并给出修改建议。\n"
    "6. 不要编造工具未返回的数据。"
)


def build_context_block(res: Optional[Any], mentions: Optional[List[str]]) -> str:
    if res is None:
        return "[当前电路状态]\n（尚无电路或尚未求解）"

    lines: List[str] = ["[当前电路状态]"]
    lines.append("网表：")
    lines.append(res.netlist or "(空)")
    lines.append("节点电压（对地）：")
    for nid in res.node_order:
        n = res.nodes[nid]
        lines.append(f"  {nid}: {n.voltage}")
    lines.append("支路电流（参考方向 p0→p1）：")
    for b in res.branches:
        lines.append(f"  {b.component}({b.type}): {b.current} A  [{b.node_p}->{b.node_n}]")

    if res.diagnostics:
        lines.append("诊断：")
        for d in res.diagnostics:
            lines.append(f"  [{d.level}] {d.message}")

    if mentions:
        lines.append("[用户 @ 的节点]")
        for m in mentions:
            n = res.nodes.get(m)
            if n is None:
                lines.append(f"  {m}: 不存在")
            else:
                lines.append(f"  {m}: V={n.voltage} V" + (f"，符号式 {n.voltage_expr}" if n.voltage_expr else ""))
    return "\n".join(lines)
