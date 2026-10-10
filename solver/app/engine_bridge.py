"""把新引擎接进主流程：域判定、多域结果 schema、旧 DC 交叉校验。

设计原则（不改坏老功能）：
- 一切求解都走新引擎（DC/AC/TRAN 一套）。
- 纯直流 R/V/I 电路额外用旧 MNA 复算一次，两者不一致就报诊断（老路径是回归保险）。
"""
from __future__ import annotations

import cmath
import math
from typing import Any, Dict, List, Optional, Tuple

from . import devices as DEV
from .engine import AC, DC, TRAN, SolveError, analyse as engine_analyse
from .models import Diagnostic          # ★ fill_result 里要用，必须模块级导入
from .solve import Br, build_branches


def domain_of(req) -> Tuple[str, float, float, int]:
    """从请求里取域参数。默认直流；有 C/L/交流源/三相 时可按 domain 指定。"""
    d = str(getattr(req, "domain", None) or DC).lower()
    if d in ("ac", "交流", "phasor", "sin"):
        d = AC
    elif d in ("tran", "transient", "暂态", "time"):
        d = TRAN
    else:
        d = DC
    freq = float(getattr(req, "freq", None) or 50.0)
    tstop = float(getattr(req, "tstop", None) or 0.0)
    nsteps = int(getattr(req, "nsteps", None) or 201)
    return d, freq, tstop, nsteps


def needs_dynamic(sch) -> bool:
    """电路里有没有需要交流/暂态的器件（用来给用户提示该切域）。"""
    for c in sch.components:
        if c.type in ("capacitor", "inductor"):
            return True
        # ★ 三相电源(vsource3) 也带 kind，漏了它会把三相交流强行降级成直流分析
        if c.type in ("vsource", "isource", "vsource3") and \
                str((c.params or {}).get("kind") or "dc") != "dc":
            return True
    return False


def use_new_engine(sch, req) -> bool:
    """什么时候走新引擎：
    ① 指定了 ac / tran 域；
    ② 电路里出现 R/V/I/地 以外的器件（电容/电感/受控源/变压器/运放/二极管/三极管/开关/三相）。
    纯直流 R/V/I 电路继续走老路径（最保险）。
    """
    d, _f, _t, _n = domain_of(req)
    if d in (AC, TRAN):
        return True
    simple = {"resistor", "vsource", "isource", "ground"}
    return any(c.type not in simple for c in sch.components)


def _phasor(c) -> Dict[str, float]:
    from .models import Diagnostic, Phasor

    z = complex(c)
    r = abs(z)
    return Phasor(re=z.real, im=z.imag, rms=r, peak=r * math.sqrt(2),
                  phase=math.degrees(cmath.phase(z)))


def _solve_multi_switch(topo, branches, segs, freq, tstop, nsteps):
    """多个开关在不同时刻翻转：逐段求解并在每段交界处用储能元件终值当下一段初值。"""
    state = {cid: (True if st else False) for cid, _t, st in segs}
    times = [0.0] + [t for _c, t, _s in segs if 0 < t < tstop] + [tstop]
    wave = {"t": []}
    v0: dict = {}
    i0: dict = {}
    for k in range(len(times) - 1):
        t_a, t_b = times[k], times[k + 1]
        if t_b <= t_a:
            continue
        mod = []
        for b in branches:
            if b.id in state:
                prm = dict(b.prm)
                prm["closed"] = state[b.id]
                mod.append(Br(id=b.id, type=b.type, n=dict(b.n), prm=prm))
            else:
                mod.append(b)
        nseg = max(3, int(round(nsteps * (t_b - t_a) / max(tstop, 1e-9))))
        e = engine_analyse(topo.nodes, mod, domain=TRAN, freq=freq,
                           tstop=max(t_b - t_a, 1e-12), nsteps=nseg,
                           v0={k2: complex(v).real for k2, v in v0.items()},
                           i0={k2: complex(v).real for k2, v in i0.items()})
        skip = 1 if k else 0
        for key, arr in (e.get("waveform") or {}).items():
            if key == "t":
                wave["t"] += [t_a + x for x in list(arr)[skip:]]
            else:
                wave[key] = wave.get(key, []) + list(arr)[skip:]
        if k < len(times) - 2:                 # 该翻哪个开关
            for cid, t, _st in segs:
                if abs(t - t_b) < 1e-12:
                    state[cid] = not state[cid]
        v0 = {b.id: complex(e["V"].get(b.node("p0"), 0)) - complex(e["V"].get(b.node("p1"), 0))
              for b in branches if b.type == "capacitor"}
        i0 = {b.id: e["I"].get(b.id, 0) for b in branches if b.type == "inductor"}
    out = dict(e)
    out["waveform"] = wave
    return out


def _switch_segments(sch) -> list:
    """带 t_switch 参数的开关 → 暂态分两段（换路前后）求解。"""
    out = []
    for c in sch.components:
        if c.type != "switch":
            continue
        prm = getattr(c, "params", None) or {}
        t = prm.get("t_switch")
        if t is None:
            continue
        try:
            out.append((c.id, float(t), bool(prm.get("closed", True))))
        except Exception:
            continue
    return sorted(out, key=lambda x: x[1])


def _solve_with_switching(topo, branches, segs, freq, tstop, nsteps):
    """分两段求解并在拼接处衔接：电容电压取上段终值，电感电流取上段终值。

    只用换路时刻的「储能元件终值」当后一段初值 —— 这正是三要素法里
    「电容电压/电感电流不跃变」的体现。
    """
    from .engine import TRAN, analyse as _eng

    sw_id, t_sw, state0 = segs[0]
    # 多开关：按时间顺序逐段衔接（每段只翻一个开关）
    if len(segs) > 1:
        return _solve_multi_switch(topo, branches, segs, freq, tstop, nsteps)
    n1 = max(3, int(round(nsteps * min(1.0, t_sw / max(tstop, 1e-9)))))
    n2 = max(3, nsteps - n1 + 1)
    seg1 = []
    for b in branches:
        if b.id == sw_id:
            prm = dict(b.prm)
            prm["closed"] = state0
            seg1.append(Br(id=b.id, type=b.type, n=dict(b.n), prm=prm))
        else:
            seg1.append(b)
    e1 = _eng(topo.nodes, seg1, domain=TRAN, freq=freq, tstop=t_sw, nsteps=n1)
    v0 = {b.id: e1["V"].get(b.node("p0"), 0) - e1["V"].get(b.node("p1"), 0)
          for b in branches if b.type == "capacitor"}
    i0 = {b.id: e1["I"].get(b.id, 0) for b in branches if b.type == "inductor"}
    seg2 = []
    for b in branches:
        if b.id == sw_id:
            prm = dict(b.prm)
            prm["closed"] = not state0
            seg2.append(Br(id=b.id, type=b.type, n=dict(b.n), prm=prm))
        else:
            seg2.append(b)
    e2 = _eng(topo.nodes, seg2, domain=TRAN, freq=freq,
              tstop=max(tstop - t_sw, 1e-12), nsteps=n2,
              v0={k: complex(v).real for k, v in v0.items()},
              i0={k: complex(v).real for k, v in i0.items()})
    # 拼接波形：后段时间轴平移
    wave = {"t": list(e1["waveform"]["t"])}
    for k, arr in (e1.get("waveform") or {}).items():
        if k != "t":
            wave[k] = list(arr)
    for k, arr in (e2.get("waveform") or {}).items():
        if k == "t":
            wave["t"] += [t_sw + x for x in list(arr)[1:]]
        else:
            wave[k] = wave.get(k, []) + list(arr)[1:]
    out = dict(e2)
    out["waveform"] = wave
    return out


def fill_result(result, sch, topo, req):
    """用新引擎求解并写进 SolveResult（节点电压/支路电流/相量/功率/波形）。"""
    # 新引擎分支比旧路径早返回，这里必须先把支路表建好（原来只在老路径里建）
    if not result.branches:
        from .models import BranchResult

        for b in topo.branches:
            result.branches.append(BranchResult(
                component=b["component"], type=b["type"],
                node_p=b.get("node_p") or "0", node_n=b.get("node_n") or "0",
            ))
    domain, freq, tstop, nsteps = domain_of(req)
    branches = build_branches(sch, topo.node_of_member)
    if domain == AC and not needs_dynamic(sch):
        domain = DC
    # ★ 开关中途换路：把暂态分成两段（换路前/后），后一段以前一段终值作初值
    segs = _switch_segments(sch) if domain == TRAN else []
    try:
        if segs:
            eng = _solve_with_switching(topo, branches, segs, freq, tstop, nsteps)
        else:
            eng = engine_analyse(topo.nodes, branches, domain=domain, freq=freq,
                                 tstop=tstop, nsteps=nsteps)
    except SolveError as exc:
        result.diagnostics.append(
            Diagnostic(level="error", code="SOLVE_FAILED", message=str(exc))
        )
        result.ok = False
        return result

    result.ok = True
    result.domain = domain
    result.freq = freq if domain == AC else None
    result.waveform = eng.get("waveform")
    V, I, P = eng["V"], eng["I"], eng.get("P", {})
    for nid, nd in result.nodes.items():
        v = V.get(nid)
        if v is None:
            continue
        if domain == AC:
            nd.phasor = _phasor(v)
            nd.voltage = nd.phasor.rms
        else:
            nd.voltage = float(getattr(v, "real", v))
    bm = {b.id: b for b in branches}
    for br in result.branches:
        b = bm.get(br.component)
        cur = I.get(br.component)
        if b is not None:
            up, un = V.get(b.node("p0"), 0), V.get(b.node("p1"), 0)
            br.voltage = float(getattr(up - un, "real", up - un)) if domain != AC else abs(up - un)
        if cur is None:
            continue
        if domain == AC:
            br.phasor = _phasor(cur)
            br.current = br.phasor.rms
        else:
            br.current = float(getattr(cur, "real", cur))
        p = P.get(br.component)
        if p is not None:
            br.power = p if isinstance(p, dict) else {"p": p}
    # 未接地提示（与老路径一致）
    has_ground = any(info.get("is_ground") for info in topo.nodes.values())
    if not has_ground:
        ref = eng.get("ground")
        if ref in result.nodes:
            result.nodes[ref].voltage = 0.0
            result.nodes[ref].is_reference = True
        result.diagnostics.append(
            Diagnostic(
                level="warn", code="NO_GROUND",
                message=f"电路未接参考地（ground）：已自动选取连接最多的节点 {ref} 作为参考"
                        "（它的电位记作 0 V，其余电压都是相对它的值）。",
            )
        )
    if domain == AC:
        result.diagnostics.append(
            Diagnostic(level="info", code="AC",
                       message=f"正弦稳态（相量法）：f = {freq:g} Hz，电压/电流显示为**有效值**与相角。")
        )
    elif domain == TRAN:
        result.diagnostics.append(
            Diagnostic(level="info", code="TRAN",
                       message=f"暂态分析：0 ~ {tstop:g} s，共 {nsteps} 点（梯形法）。")
        )
    return result



def branch_map(branches) -> Dict[str, Any]:
    return {b.id: b for b in branches}


def run_dc_crosscheck(sch, topo) -> Optional[str]:
    """纯直流 R/V/I：用旧 MNA 复算，不一致就返回提示文本。"""
    simple = {"resistor", "vsource", "isource"}
    if any(c.type not in simple for c in sch.components):
        return None
    try:
        from .mna import solve_dc

        ground = next((n for n, i in topo.nodes.items() if i.get("is_ground")), None)
        if not ground:
            cand = sorted(topo.nodes.keys(), key=lambda n: (-len(topo.nodes[n].get("members", [])), n))
            ground = cand[0] if cand else "0"
        v_old, i_old = solve_dc(topo.nodes, topo.branches, ground=ground)
        brs = build_branches(sch, topo.node_of_member)
        res = engine_analyse(topo.nodes, brs, domain=DC)
        bad = []
        for nid, val in v_old.items():
            new = res["V"].get(nid)
            if new is None:
                continue
            if abs(float(getattr(new, "real", new)) - float(val)) > 1e-6 * max(1.0, abs(val)):
                bad.append(nid)
        if bad:
            return f"新旧求解器结果不一致（节点 {', '.join(bad)}），请检查接线。"
    except Exception:
        return None
    return None
