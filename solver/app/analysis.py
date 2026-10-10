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


def _resolve_and_resolve(req: SolveRequest, cr: dict, do_symbolic: bool):
    """把反解出的可行值当成已知值，重算一次 → 整张图都变成数字。"""
    vals: Dict[str, float] = {}
    for sol in cr.get("solutions", []):
        if sol.get("feasible"):
            vals = {cid: info["value"] for cid, info in sol["values"].items() if info.get("feasible")}
            break
    if not vals:
        return None
    sch3 = req.schematic.model_copy(deep=True)
    sch3.conditions = []
    for c in sch3.components:
        if c.id in vals:
            c.value = vals[c.id]
            c.symbol = None
    inner = analyze(SolveRequest(session_id=req.session_id, schematic=sch3, mode=req.mode,
                                 domain=req.domain, freq=req.freq, tstop=req.tstop,
                                 nsteps=req.nsteps), do_symbolic)
    inner.constraint_result = cr
    return inner


def analyze(req: SolveRequest, do_symbolic: bool = True) -> SolveResult:
    """对外入口。

    历史上这里会再挂一堆「解法步骤」（节点电压法/叠加/三要素…），
    但前端已改成用「学习文档」卡片讲方法 —— 步骤文字既费时间又没人看，故不再生成。
    端口等效反解仍然保留自己的 steps（那是反解过程本身）。
    """
    return _analyze_impl(req, do_symbolic)


def _analyze_impl(req: SolveRequest, do_symbolic: bool = True) -> SolveResult:
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

    # ★ 悬空节点先提示（不拦路：端口等效会故意摘元件，那时端口节点只剩一个元件）
    try:
        from .engine import check_floating
        from .solve import build_branches as _bb

        _g = next((n for n, info in topo.nodes.items() if info.get("is_ground")), None)
        _msg = check_floating(topo.nodes, _bb(sch, topo.node_of_member), _g)
        if _msg:
            diagnostics.append(Diagnostic(
                level="warn", code="FLOATING_NODE",
                message=_msg + "。若求解失败，多半就是这里没接好。"))
    except Exception:
        pass

    # ★★ 新引擎通道：含 C/L/受控源/变压器/运放/二极管/三极管，或指定了 ac/tran 域时启用。
    # 纯直流 R/V/I 电路仍走老路径（零回归风险）；老路径另有交叉校验。
    try:
        from . import engine_bridge

        if engine_bridge.use_new_engine(sch, req):
            return engine_bridge.fill_result(result, sch, topo, req)
    except Exception as exc:  # pragma: no cover
        diagnostics.append(
            Diagnostic(level="warn", code="ENGINE_FAILED",
                       message=f"统一求解引擎出错，已回退旧路径：{type(exc).__name__}: {exc}")
        )

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
        if ref_node in result.nodes:
            result.nodes[ref_node].is_reference = True      # 它的 0 V 是「定义」，不是算出来的
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
    from . import devices as _DEV

    # 只有「真的用数值 value」的器件才算未知量；二极管/三极管/运放/开关没有 value，不算
    unknowns = [b for b in topo.branches
                if b.get("value") is None and _DEV.takes_value(b.get("type", ""))]
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
            _fl = next((d.message for d in diagnostics if d.code == "FLOATING_NODE"), "")
            diagnostics.append(Diagnostic(
                level="error", code="SOLVE_FAILED",
                message=(_fl if _fl else str(exc))))
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
                    result.nodes[nid].voltage_latex_sub = nd.get("latex_sub")
                    result.nodes[nid].voltage_decomp = nd.get("decomp")
                    # 即使存在未知量，只要该节点电压与未知量无关（纯数字），也照样给出数值
                    if result.nodes[nid].voltage is None and nd.get("value") is not None:
                        result.nodes[nid].voltage = nd["value"]
            for br in result.branches:
                bd = sym["branches"].get(br.component)
                if bd:
                    br.current_expr = bd.get("expr")
                    br.current_latex = bd.get("latex")
                    br.current_latex_sub = bd.get("latex_sub")
                    br.current_decomp = bd.get("decomp")
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

    # ④ 图上标注的「已知量」→ 自动反解未知量（"画完就有答案"）
    conds_in = getattr(req.schematic, "conditions", None)
    if unknowns:
        from .constraints import resolve_annotations, solve_constraints

        member_of = {nid: nd.members for nid, nd in result.nodes.items()}
        conds, errs = resolve_annotations(member_of, conds_in or [])
        if conds:
            cr = solve_constraints(req.session_id, conds, req.schematic)
            if errs:
                cr["warnings"] = errs
            result.constraint_result = cr
        elif errs:
            # 标注解析不出来的话以前是**悄悄丢掉**的，这里必须说出来，否则用户只看到"没反应"
            result.constraint_result = {
                "error": "图上的「已知量」标注没能用上：" + "；".join(errs)
                         + "（把标注拖到节点圆点、导线或元件端子上再填数值）",
            }
        else:
            # ★ 没有任何条件：用**端口等效（戴维南）算法**直接把未知元件推出来 ——
            #   断开 → 求 Voc → 求 Isc → Rth = Voc/Isc。不需要用户再补任何东西。
            try:
                from .algorithms import port_equivalent

                pe = port_equivalent(sch, topo, [b["component"] for b in unknowns],
                                     SolveRequest(session_id=req.session_id, schematic=sch,
                                                  mode=req.mode, domain=req.domain, freq=req.freq))
                if pe:
                    result.constraint_result = pe
                    inner = _resolve_and_resolve(req, pe, do_symbolic)
                    if inner is not None:
                        inner.constraint_result = pe
                        return inner
            except Exception as exc:  # pragma: no cover
                diagnostics.append(
                    Diagnostic(level="warn", code="ALGO_FAILED",
                               message=f"端口等效算法没能算出结果：{type(exc).__name__}: {exc}")
                )
        if conds:
            # 解出可行值后，直接把它当成已知值重算一次 → 整张图都变成数字
            vals: Dict[str, float] = {}
            for sol in cr.get("solutions", []):
                if sol.get("feasible"):
                    vals = {cid: info["value"] for cid, info in sol["values"].items() if info.get("feasible")}
                    break
            if vals:
                inner = _resolve_and_resolve(req, cr, do_symbolic)
                if inner is not None:
                    return inner

    return result
