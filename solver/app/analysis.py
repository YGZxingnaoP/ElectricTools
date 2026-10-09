"""编排器：一次求解的完整流水线（几何→拓扑→数值→符号→校验）。"""
from __future__ import annotations

import re
from typing import Dict, List

from .config import CONFIG
from .lcapy_solver import solve_symbolic
from .mna import MnaError, solve_dc
from .models import (
    BranchResult,
    Diagnostic,
    NodeResult,
    Schematic,
    SolveRequest,
    SolveResult,
)
from .topology import NodeRegistry, derive_topology
from .validation import cross_check

_PREFIX = {"resistor": "R", "vsource": "V", "isource": "I"}


class SessionStore:
    def __init__(self) -> None:
        self._reg: Dict[str, NodeRegistry] = {}
        self._sch: Dict[str, Schematic] = {}

    def registry(self, sid: str) -> NodeRegistry:
        if sid not in self._reg:
            self._reg[sid] = NodeRegistry()
        return self._reg[sid]

    def set_schematic(self, sid: str, sch: Schematic) -> None:
        self._sch[sid] = sch

    def get_schematic(self, sid: str) -> Schematic | None:
        return self._sch.get(sid)

    def reset(self, sid: str) -> None:
        self._reg.pop(sid, None)
        self._sch.pop(sid, None)


STORE = SessionStore()


def _sort_key(nid: str):
    if nid == "0":
        return (0, 0, "")
    if nid.startswith("n") and nid[1:].isdigit():
        return (1, int(nid[1:]), "")
    return (2, 0, nid)


def _net_name(raw: object, fallback: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_]", "_", str(raw or "").strip()).strip("_")
    if not s:
        return fallback
    return ("X" + s) if s[0].isdigit() else s


def _spice_netlist(branches: List[dict]) -> str:
    """给 AI / 界面展示用的网表：**元件名用真实位号**，与工具、画布保持一致。"""
    lines: List[str] = []
    counters: Dict[str, int] = {}
    for br in branches:
        t = br["type"]
        if t not in _PREFIX:
            continue
        pre = _PREFIX[t]
        counters[pre] = counters.get(pre, 0) + 1
        name = _net_name(br.get("component"), f"{pre}{counters[pre]}")
        val = br.get("value")
        if val is None:
            valtxt = (br.get("symbol") or "?").strip() or "?"
        else:
            valtxt = f"{val:g}" if isinstance(val, (int, float)) else str(val)
        lines.append(f"{name} {br['node_p']} {br['node_n']} {valtxt}")
    return "\n".join(lines)


def analyze(req: SolveRequest, do_symbolic: bool = True) -> SolveResult:
    sch: Schematic = req.schematic
    reg = STORE.registry(req.session_id)
    topo = derive_topology(sch, reg)

    diagnostics: List[Diagnostic] = list(topo.diagnostics)
    node_order = sorted(topo.nodes.keys(), key=_sort_key)

    result = SolveResult(ok=False, node_order=node_order, diagnostics=diagnostics)
    # 注意：SolveResult 会复制一份 diagnostics，后续 append 必须写到 result.diagnostics 上，
    # 否则新加的诊断（EMPTY / NO_GROUND / UNKNOWN_VALUE / SOLVE_FAILED …）不会出现在返回结果里。
    diagnostics = result.diagnostics

    for nid in node_order:
        info = topo.nodes[nid]
        result.nodes[nid] = NodeResult(
            id=nid,
            members=info.get("members", []),
            voltage=0.0 if nid == "0" else None,
        )

    if not topo.branches:
        diagnostics.append(
            Diagnostic(level="warn", code="EMPTY", message="还没有可求解的元件。")
        )
        return result

    # 参考节点：优先真实接地（节点 0）；若未接地则自动选一个参考节点，
    # 这样电流仍可求解，节点电压为「相对该参考节点」的值。
    has_ground = any(info.get("is_ground") for info in topo.nodes.values())
    ref_node = "0"
    if not has_ground:
        if not topo.nodes:
            return result
        # 选「连接最多」的节点作为参考；同分时取位号最小者（确定性，且通常是公共回流端）
        ref_node = sorted(
            topo.nodes.keys(),
            key=lambda n: (-len(topo.nodes[n].get("members", [])), n),
        )[0]
        diagnostics.append(
            Diagnostic(
                level="warn",
                code="NO_GROUND",
                message=(
                    f"电路未接参考地（ground）：已自动选取连接最多的节点 {ref_node} 作为参考"
                    f"（它的电位记作 0 V，其余节点电压都是相对它的值）。"
                    "电流与接地无关、仍然正确；若需要绝对电位，请放置一个接地符号。"
                ),
            )
        )

    # 未知量（未填数值，或填了占位符号）：跳过数值求解，仅给出符号式
    unknowns = [b for b in topo.branches if b.get("value") is None]
    if unknowns:
        diagnostics.append(
            Diagnostic(
                level="warn",
                code="UNKNOWN_VALUE",
                message=(
                    "以下元件未填数值、按【未知量】处理（结果用符号表示）："
                    + "、".join(f"{b['component']}({b.get('symbol') or '未知'})" for b in unknowns)
                    + "。若题目要求具体数值，请补上该元件的数值，或输入题目给出的其它条件。"
                ),
            )
        )

    # ① 数值 MNA（实时主求解器）
    v_mna: Dict[str, float] = {}
    if unknowns:
        # 含未知量：不做数值 MNA，但仍会做符号求解；
        # 与未知量无关的节点/支路，下面会从符号解里取出数值直接显示。
        result.branches = [
            BranchResult(
                component=b["component"], type=b["type"],
                node_p=b["node_p"], node_n=b["node_n"], current=None, voltage=None,
            )
            for b in topo.branches
        ]
        if ref_node in result.nodes:
            result.nodes[ref_node].voltage = 0.0
    else:
        try:
            v_mna, i_mna = solve_dc(topo.nodes, topo.branches, ground=ref_node)
        except MnaError as exc:
            diagnostics.append(Diagnostic(level="error", code="SOLVE_FAILED", message=str(exc)))
            return result

        for nid, val in v_mna.items():
            if nid in result.nodes:
                result.nodes[nid].voltage = val

        result.branches = [
            BranchResult(
                component=br["component"],
                type=br["type"],
                node_p=br["node_p"],
                node_n=br["node_n"],
                current=i_mna.get(br["component"]),
                voltage=v_mna.get(br["node_p"], 0.0) - v_mna.get(br["node_n"], 0.0),
            )
            for br in topo.branches
        ]
    result.ok = True
    result.netlist = _spice_netlist(topo.branches)

    # ② 符号求解 + ③ 校验（可关闭以加速实时路径）
    if do_symbolic and req.mode in ("symbolic", "both"):
        sym = solve_symbolic(topo.nodes, topo.branches, ground=ref_node)
        if sym.get("ok"):
            for nid, nd in sym["nodes"].items():
                if nid in result.nodes:
                    result.nodes[nid].voltage_expr = nd.get("expr")
                    result.nodes[nid].voltage_latex = nd.get("latex")
                    # 即使存在未知量，只要该节点电压与未知量无关（纯数字），也照样给出数值
                    if result.nodes[nid].voltage is None and nd.get("value") is not None:
                        result.nodes[nid].voltage = nd["value"]
            for br in result.branches:
                bd = sym["branches"].get(br.component)
                if bd:
                    br.current_expr = bd.get("expr")
                    br.current_latex = bd.get("latex")
                    if br.current is None and bd.get("value") is not None:
                        br.current = bd["value"]
            if not unknowns:
                lcapy_values = {
                    nid: nd["value"] for nid, nd in sym["nodes"].items() if nd.get("value") is not None
                }
                tol = CONFIG["solver"]["crosscheck_rel_tol"]
                result.validation = cross_check(v_mna, lcapy_values, tol)
                if not result.validation.ok:
                    diagnostics.append(
                        Diagnostic(
                            level="warn",
                            code="VALIDATION_MISMATCH",
                            message="MNA 与 lcapy 结果不一致，已标注，请检查电路。",
                        )
                    )
        else:
            diagnostics.append(
                Diagnostic(
                    level="warn",
                    code="SYMBOLIC_FAILED",
                    message=f"符号求解失败：{sym.get('error')}",
                )
            )

    return result
