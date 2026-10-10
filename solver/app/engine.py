"""求解入口：按「域」组织求解流程，含非线性迭代、三极管两段式（Q点→微变等效）、暂态步进。"""
from __future__ import annotations

import cmath
import math
from typing import Any, Dict, List, Optional

from . import devices as D
from .solve import AC, DC, TRAN, Br, SolveError, Solver, build_branches

__all__ = ["analyse", "SolveError", "AC", "DC", "TRAN", "build_branches"]


def _pick_ground(nodes: Dict[str, dict], branches: List[Br]) -> str:
    gnd = [nid for nid, info in nodes.items() if info.get("is_ground")]
    if gnd:
        return gnd[0]
    # 未接地：选连接最多的节点当参考（与旧行为一致）
    if not nodes:
        raise SolveError("空电路")
    return sorted(nodes.keys(), key=lambda n: (-len(nodes[n].get("members", [])), n))[0]


def _iterate_linear(nodes, branches, domain, freq, ground, h=0.0, prev=None,
                    max_iter=40) -> Dict[str, Any]:
    """非线性（二极管/稳压管/开关）分段线性迭代：状态 → 解 → 判据 → 再解。"""
    specials = [b for b in branches if b.type in ("diode", "zener", "switch")]
    st: Dict[str, Dict[str, Any]] = {}
    for b in specials:
        if b.type == "switch":
            st[b.id] = {"closed": bool(b.prm.get("closed", True))}
        else:
            st[b.id] = {"on": False, "mode": "forward"}
    solver = Solver(nodes, branches, ground)
    last = None
    for _ in range(max_iter):
        solver.state = {k: dict(v) for k, v in st.items()}
        res = solver.solve_once(domain, freq, h, prev)
        V, I = res["V"], res["I"]
        changed = False
        for b in specials:
            if b.type != "switch":
                continue
        for b in specials:
            if b.type != "diode" and b.type != "zener":
                continue
            if b.id in solver.extra and not st[b.id].get("on"):
                pass
            vp = V.get(b.node("p0"), 0)
            vn = V.get(b.node("p1"), 0)
            v = vp - vn
            vth = float(b.prm.get("vth", 0.7) or 0.7)
            on = st[b.id].get("on", False)
            if b.type == "diode":
                if not on and _gt(v, vth):
                    st[b.id] = {"on": True}
                    changed = True
                elif on:
                    i = I.get(b.id, 0)
                    if not _gt(i, 0.0):
                        st[b.id] = {"on": False}
                        changed = True
            else:                       # 稳压管：正向导通 / 反向击穿 / 截止
                vz = float(b.prm.get("vz", 5.1) or 5.1)
                if not on and _gt(v, vth):
                    st[b.id] = {"on": True, "mode": "forward"}
                    changed = True
                elif not on and _lt(v, -vz - 1e-9):
                    st[b.id] = {"on": True, "mode": "breakdown"}
                    changed = True
                elif on:
                    i = I.get(b.id, 0)
                    if not _gt(i, 0.0):
                        st[b.id] = {"on": False}
                        changed = True
        last = res
        if not changed:
            return {"V": V, "I": I, "states": {k: dict(v) for k, v in st.items()}, "x": res["x"]}
    return {"V": last["V"], "I": last["I"], "states": st, "x": last["x"] if last else None}


def _gt(a, b, tol=1e-9):
    return float(getattr(a, "real", a)) - float(b) > tol


def _lt(a, b, tol=1e-9):
    return float(getattr(a, "real", a)) - float(b) < -tol


def _powers(V, I, branches, domain):
    P: Dict[str, Any] = {}
    for b in branches:
        v = V.get(b.node("p0"), 0) - V.get(b.node("p1"), 0)
        i = I.get(b.id, 0)
        if domain == AC:
            # 复功率 S = V·I*（吸收为正）
            S = complex(v) * complex(i).conjugate()
            P[b.id] = {"p": S.real, "q": S.imag, "s": abs(S), "pf": (S.real / abs(S)) if abs(S) > 0 else 0.0}
        else:
            P[b.id] = float(getattr(v, "real", v) * getattr(i, "real", i))
    return P


def check_floating(nodes: Dict[str, dict], branches: List[Br], ground: Optional[str] = None) -> str:
    """悬空节点：只挂一个元件的节点通常解不出。返回描述（空串=没有）。

    注意：不能直接报错 —— 端口等效算法会**故意**摘掉一个元件，那时端口节点
    就只剩一个元件。所以这里只产出描述，等真解不出来时再拿它当解释。
    """
    deg: Dict[str, int] = {}
    who: Dict[str, List[str]] = {}
    for b in branches:
        ns = set(x for x in (b.n or {}).values() if x)
        for n in ns:                     # ★ 用 set：两端接同一节点（自环）只算一次连接
            deg[n] = deg.get(n, 0) + 1
            who.setdefault(n, []).append(b.id)
    bad = sorted(n for n, d in deg.items() if d < 2 and n != ground and n in nodes)
    if bad:
        det = "；".join(f"节点 {n} 只接了 {'、'.join(sorted(set(who.get(n, []))))}" for n in bad[:4])
        return f"有节点悬空（没构成回路）：{det}"
    return ""


def analyse(nodes: Dict[str, dict], branches: List[Br], domain: str = DC,
            freq: float = 50.0, tstop: float = 0.0, nsteps: int = 201,
            v0: Optional[Dict[str, float]] = None, i0: Optional[Dict[str, float]] = None,
            ground: Optional[str] = None) -> Dict[str, Any]:
    """统一求解入口。返回 {V, I, P, domain, freq, warnings, waveform, states}"""
    if not nodes:
        raise SolveError("空电路")
    ground = ground or _pick_ground(nodes, branches)
    warnings: List[str] = []

    # 治本：悬空节点先记下来；真解不出来时用它当解释，别让用户看"方程奇异"
    floating = check_floating(nodes, branches, ground)
    if ground is None:
        raise SolveError("电路里没有任何接地/参考点，也找不到可自动选作参考的节点。加一个接地符号即可。")

    # 参数没填的受控源/变压器：不能静默按 0 算（结果会莫名奇妙）
    for _b in branches:
        if _b.type in ("vcvs", "vccs", "ccvs", "cccs") and _b.prm.get("gain") is None \
                and _b.prm.get("value") is None:
            warnings.append(f"{_b.id}（受控源）的增益没填，已按 0 计算 —— 请填上增益。")
        if _b.type == "transformer" and _b.prm.get("ratio") is None \
                and _b.prm.get("value") is None:
            warnings.append(f"{_b.id}（理想变压器）的变比没填，已按 1 计算 —— 请填上变比。")
        if _b.type == "resistor" and _b.prm.get("value") == 0:
            warnings.append(f"{_b.id} 阻值为 0，按短路（理想导线）处理。")

    # 三极管：直流 Q 点 → 交流微变等效
    bjts = [b for b in branches if b.type == "bjt"]

    try:
        return _analyse_inner(nodes, branches, domain, freq, tstop, nsteps, v0, i0,
                              ground, warnings, bjts)
    except SolveError as exc:
        if floating and ("奇异" in str(exc) or "singular" in str(exc).lower()):
            raise SolveError(f"{floating}。请检查这些元件另一端是否接到了别的节点或接地。") from exc
        raise


def _analyse_inner(nodes, branches, domain, freq, tstop, nsteps, v0, i0,
                   ground, warnings, bjts):
    if domain in (DC, AC):
        # 非线性元件在正弦稳态里没有唯一解（二极管通断取决于瞬时极性）→ 明确报出来
        nonlin = [b.id for b in branches if b.type in ("diode", "zener")]
        if domain == AC and nonlin:
            raise SolveError(
                f"含非线性元件（{', '.join(nonlin)}）不能做正弦稳态分析："
                "二极管的通断取决于每个时刻的极性。请把「分析域」切到**暂态（时域）**再算。"
            )
        res = _iterate_linear(nodes, branches, domain, freq, ground)
        out = {"V": res["V"], "I": res["I"], "domain": domain, "ground": ground,
               "states": res["states"], "warnings": warnings}
        if domain == AC and bjts:
            out["warnings"].append("交流含三极管：已按微变等效（π 模型）处理，需先给出静态工作点参数。")
        out["P"] = _powers(res["V"], res["I"], branches, domain)
        return out

    # ---- 暂态：梯形法时域步进 ----
    if tstop <= 0:
        raise SolveError("暂态分析需要 tstop > 0")
    h = tstop / max(1, nsteps - 1)
    solver = Solver(nodes, branches, ground)
    prev: Dict[str, Any] = {"__t__": 0.0}
    for b in branches:
        if b.type == "capacitor":
            prev[b.id] = {"v": float((v0 or {}).get(b.id, 0.0)), "i": float((i0 or {}).get(b.id, 0.0))}
        elif b.type == "inductor":
            prev[b.id] = {"v": float((v0 or {}).get(b.id, 0.0)), "i": float((i0 or {}).get(b.id, 0.0))}
    # t=0⁺ 快照：h 取到极小，电容/电感就退化成「初值电压源 / 初值电流源」，
    # 直接得到精确的 0⁺ 状态（阶跃源在 t=0 的跳变只影响电流，不影响电容电压）。
    prev["__t__"] = 0.0
    res0 = _iterate_linear(nodes, branches, TRAN, freq, ground, h / 1000.0, prev)
    wave: Dict[str, List[float]] = {"t": [0.0]}
    for nid, val in res0["V"].items():
        wave.setdefault("V:" + nid, []).append(float(getattr(val, "real", val)))
    for bid, val in res0["I"].items():
        wave.setdefault("I:" + bid, []).append(float(getattr(val, "real", val)))
    for b in branches:
        up = res0["V"].get(b.node("p0"), 0)
        un = res0["V"].get(b.node("p1"), 0)
        wave.setdefault("U:" + b.id, []).append(float(getattr(up - un, "real", up - un)))
    first = None
    lastV = None
    lastI: Dict[str, Any] = {}
    for k in range(1, nsteps):
        t = k * h
        # 第一个区间：阶跃/开关的跳变要细分，之后用整步（梯形法二阶精度）
        micro = 50 if k == 1 else 1
        for _m in range(micro):
            prev["__t__"] = t - h + (_m + 1) * h / micro
            res = _iterate_linear(nodes, branches, TRAN, freq, ground, h / micro, prev)
            V, I = res["V"], res["I"]
            for b in branches:
                if b.type in ("capacitor", "inductor"):
                    up = V.get(b.node("p0"), 0)
                    un = V.get(b.node("p1"), 0)
                    cur = I.get(b.id, 0)
                    prev[b.id] = {"v": float(getattr(up - un, "real", up - un)),
                                  "i": float(getattr(cur, "real", cur))}
        wave["t"].append(t)
        for nid, val in V.items():
            wave.setdefault("V:" + nid, []).append(float(getattr(val, "real", val)))
        for bid, val in I.items():
            wave.setdefault("I:" + bid, []).append(float(getattr(val, "real", val)))
        for b in branches:
            up = V.get(b.node("p0"), 0)
            un = V.get(b.node("p1"), 0)
            wave.setdefault("U:" + b.id, []).append(float(getattr(up - un, "real", up - un)))
        lastV = V
        lastI = I
    out = {"V": {k: float(getattr(v, "real", v)) for k, v in lastV.items()}, "I": {},
           "domain": TRAN, "ground": ground, "h": h, "waveform": wave,
           "initial": first, "states": {}, "warnings": warnings}
    out["I"] = {k: float(getattr(v, "real", v)) for k, v in lastI.items()}
    out["P"] = _powers(lastV, lastI, branches, TRAN)
    return out
