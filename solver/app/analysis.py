"""编排器：一次求解的完整流水线（几何→拓扑→数值→符号→校验）。"""
from __future__ import annotations

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


def _spice_netlist(branches: List[dict]) -> str:
    lines: List[str] = []
    counters: Dict[str, int] = {}
    for br in branches:
        t = br["type"]
        if t not in _PREFIX:
            continue
        pre = _PREFIX[t]
        counters[pre] = counters.get(pre, 0) + 1
        name = f"{pre}{counters[pre]}"
        val = br.get("value")
        valtxt = "" if val is None else (f"{val:g}" if isinstance(val, (int, float)) else str(val))
        lines.append(f"{name} {br['node_p']} {br['node_n']} {valtxt}")
    return "\n".join(lines)


def analyze(req: SolveRequest, do_symbolic: bool = True) -> SolveResult:
    sch: Schematic = req.schematic
    reg = STORE.registry(req.session_id)
    topo = derive_topology(sch, reg)

    diagnostics: List[Diagnostic] = list(topo.diagnostics)
    node_order = sorted(topo.nodes.keys(), key=_sort_key)

    result = SolveResult(ok=False, node_order=node_order, diagnostics=diagnostics)

    for nid in node_order:
        info = topo.nodes[nid]
        result.nodes[nid] = NodeResult(
            id=nid,
            members=info.get("members", []),
            voltage=0.0 if nid == "0" else None,
        )

    has_ground = any(info.get("is_ground") for info in topo.nodes.values())
    if not has_ground:
        return result
    if not topo.branches:
        diagnostics.append(
            Diagnostic(level="warn", code="EMPTY", message="还没有可求解的元件。")
        )
        return result

    # 缺值检查
    missing = [b["component"] for b in topo.branches if b.get("value") is None and b["type"] != "ground"]
    if missing:
        diagnostics.append(
            Diagnostic(
                level="warn",
                code="MISSING_VALUE",
                message="以下元件缺少数值，暂不求值：" + ", ".join(missing),
            )
        )

    # ① 数值 MNA（实时主求解器）
    try:
        v_mna, i_mna = solve_dc(topo.nodes, topo.branches)
    except MnaError as exc:
        diagnostics.append(Diagnostic(level="error", code="SOLVE_FAILED", message=str(exc)))
        return result

    for nid, val in v_mna.items():
        if nid in result.nodes:
            result.nodes[nid].voltage = val

    branch_results: List[BranchResult] = []
    for br in topo.branches:
        comp = br["component"]
        vp = v_mna.get(br["node_p"], 0.0)
        vn = v_mna.get(br["node_n"], 0.0)
        branch_results.append(
            BranchResult(
                component=comp,
                type=br["type"],
                node_p=br["node_p"],
                node_n=br["node_n"],
                current=i_mna.get(comp),
                voltage=vp - vn,
            )
        )
    result.branches = branch_results
    result.ok = True
    result.netlist = _spice_netlist(topo.branches)

    # ② 符号求解 + ③ 校验（可关闭以加速实时路径）
    if do_symbolic and req.mode in ("symbolic", "both"):
        sym = solve_symbolic(topo.nodes, topo.branches)
        if sym.get("ok"):
            for nid, nd in sym["nodes"].items():
                if nid in result.nodes:
                    result.nodes[nid].voltage_expr = nd.get("expr")
                    result.nodes[nid].voltage_latex = nd.get("latex")
            for br in result.branches:
                bd = sym["branches"].get(br.component)
                if bd:
                    br.current_expr = bd.get("expr")
                    br.current_latex = bd.get("latex")
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
