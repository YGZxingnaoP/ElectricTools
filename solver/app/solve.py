"""统一数值求解内核：直流 / 正弦稳态(相量) / 暂态(时域步进)。纯 numpy，无 lcapy 依赖。

符号约定（与原有 mna.py 完全一致，保证旧结果不变）：
- 支路电流参考方向 = 第一引脚(p0) → 第二引脚(p1)（被动符号约定）。
- 电压源：V(p0) − V(p1) = value；支路电流参考方向 p0→p1。
- 电流源：向 p0 所在节点注入 +I（即实际电流从 p1 穿过源流向 p0）。
- 相量：**有效值**相量；瞬时值 = √2·|V|·cos(ωt + φ)。中文教材习惯。

支持器件（见 devices.py）：R C L V I / 受控源 E G F H / 理想变压器 TF /
理想运放(虚短虚断) / 开关 / 二极管·稳压管(分段线性迭代) / 三极管(直流Q点 + 微变等效)。
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import devices as D

DC, AC, TRAN = D.DC, D.AC, D.TRAN


class SolveError(Exception):
    pass


# ---------------------------------------------------------------------------
# 支路记录
# ---------------------------------------------------------------------------
@dataclass
class Br:
    id: str
    type: str
    n: Dict[str, str] = field(default_factory=dict)     # 引脚名 → 节点ID
    prm: Dict[str, Any] = field(default_factory=dict)   # 参数

    def node(self, pin: str) -> Optional[str]:
        return self.n.get(pin)


def build_branches(sch, node_of_member: Dict[str, str]) -> List[Br]:
    """把原理图元件转成支路（支持多引脚器件；节点沿用 topology 的分配）。"""
    out: List[Br] = []
    for c in sch.components:
        if c.type == "ground":
            continue
        n: Dict[str, str] = {}
        for p in c.pins:
            nid = node_of_member.get(f"u:{c.id}/{p.name}")
            if nid:
                n[p.name] = nid
        spec = D.get(c.type)
        prm: Dict[str, Any] = {"value": c.value, "symbol": c.symbol}
        # 参数来源：① 元件对象上的同名字段（旧存档）② params 字典（新）
        for k in spec.params:
            v = getattr(c, k, None)
            if v is not None:
                prm[k] = v
        for k, v in (getattr(c, "params", None) or {}).items():
            if v is not None:
                prm[k] = v
        # 三相电源：一个器件 = 三相对称电压源（U/V/W 各自对中性点 p3）
        if c.type == "vsource3":
            val = c.value
            neu = n.get("p3")
            for pin, ph, tag in (("p0", 0.0, "A"), ("p1", -120.0, "B"), ("p2", 120.0, "C")):
                if pin not in n or neu is None:
                    continue
                out.append(Br(id=f"{c.id}:{tag}", type="vsource",
                              n={"p0": n[pin], "p1": neu},
                              prm={**prm, "kind": "ac", "phase": ph, "value": val}))
            continue
        out.append(Br(id=c.id, type=c.type, n=n, prm=prm))
    return out


# ---------------------------------------------------------------------------
# 源规格
# ---------------------------------------------------------------------------
def source_of(br: Br):
    """独立源规格 → (kind, value, phase, freq)。"""
    kind = str(br.prm.get("kind") or "dc").lower()
    val = br.prm.get("value")
    if val is None:
        raise SolveError(f"源 {br.id} 数值缺失")
    phase = float(br.prm.get("phase") or 0.0)
    freq = float(br.prm.get("freq") or 50.0)
    if kind in ("sin", "sine", "交流", "ac"):
        kind = "ac"
    return kind, float(val), phase, freq


def src_phasor(br: Br) -> complex:
    """交流相量（有效值）。"""
    _, val, ph, _ = source_of(br)
    return val * cmath.exp(1j * math.radians(ph))


def src_time(br: Br, t: float) -> float:
    """时域瞬时值。"""
    kind, val, ph, f = source_of(br)
    if kind == "dc":
        return val
    if kind == "step":
        return val if t >= 0 else 0.0
    return math.sqrt(2.0) * val * math.cos(2 * math.pi * f * t + math.radians(ph))


# ---------------------------------------------------------------------------
# 求解器
# ---------------------------------------------------------------------------
class Solver:
    """一次求解的上下文：组装 A·x=b 并解出各量。

    额外未知（在节点电压之后追加）：
      V/E/H 源、闭合开关、理想变压器(2个)、理想运放输出 —— 这些器件需要支路电流未知量。
    """

    def __init__(self, nodes: Dict[str, dict], branches: List[Br], ground: str = "0"):
        self.nodes = nodes
        self.branches = branches
        self.ground = ground
        self.nidx = {n: i for i, n in enumerate(n for n in nodes if n != ground)}
        self.m = len(self.nidx)
        self.extra: Dict[str, int] = {}        # 支路 key → 行号（可多个 key：'i'、'i1'、'i2'）
        self.state: Dict[str, Any] = {}        # 迭代状态：二极管通断、开关通断
        self.gm_extra: Dict[str, Dict[str, float]] = {}   # 三极管微变等效附加参数

    # ---- 基础工具 ----
    def gi(self, nid: Optional[str]) -> int:
        if nid is None or nid == self.ground:
            return -1
        return self.nidx[nid]

    def _alloc(self, key: str) -> int:
        row = self.m + len(self.extra)
        self.extra[key] = row
        return row

    def _need_row(self, br: Br) -> int:
        if br.id in self.extra:
            return self.extra[br.id]
        return self._alloc(br.id)

    # ---- 组装 ----
    def assemble(self, domain: str, freq: float, h: float = 0.0,
                 prev: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, np.ndarray]:
        prev = prev or {}
        complex_ = domain == AC
        k = self._prealloc(domain)
        size = self.m + k
        dt = complex if complex_ else float
        A = np.zeros((size, size), dtype=dt)
        b = np.zeros(size, dtype=dt)

        for br in self.branches:
            t = br.type
            p, n = self.gi(br.node("p0")), self.gi(br.node("p1"))
            if t == "resistor":
                g = self._val(br)
                # ★ R = 0 是短路，不能当成"电导 0"（那等于开路，结果会离谱）
                if g == 0:
                    self._stamp_g(A, p, n, 1e9)
                else:
                    self._stamp_g(A, p, n, 1.0 / g if g else 0.0)
            elif t in ("capacitor", "inductor"):
                self._stamp_reactive(A, b, br, domain, freq, h, prev, p, n)
            elif t == "vsource":
                self._stamp_source(A, b, br, t, domain, freq, prev, p, n)
            elif t == "isource":
                self._stamp_source(A, b, br, t, domain, freq, prev, p, n)
            elif t in ("vcvs", "vccs", "ccvs", "cccs"):
                self._stamp_controlled(A, b, br, t, p, n)
            elif t == "transformer":
                self._stamp_transformer(A, b, br)
            elif t == "opamp":
                self._stamp_opamp(A, b, br)
            elif t == "switch":
                self._stamp_switch(A, b, br, p, n)
            elif t in ("diode", "zener"):
                self._stamp_diode(A, b, br, t, p, n)
            elif t == "bjt":
                self._stamp_bjt(A, b, br, p, n)
            else:
                raise SolveError(f"不支持的元件类型：{t}")
        return A, b

    def _prealloc(self, domain: str) -> int:
        """先给需要支路电流未知量的器件分配行号（尺寸必须一次定死）。"""
        self.extra = {}
        for br in self.branches:
            t = br.type
            if t in ("vsource", "vcvs", "ccvs"):
                self._alloc(br.id)
            elif t == "inductor" and domain == DC:
                self._alloc(br.id)          # 直流：电感等效为短路（0V 支路，需要支路电流未知量）
            elif t == "switch" and br.prm.get("closed", True):
                self._alloc(br.id)
            elif t == "transformer":
                self._alloc(br.id + ":1")
                self._alloc(br.id + ":2")
            elif t == "opamp":
                self._alloc(br.id)
            elif t in ("diode", "zener"):
                # 用「分段线性」模型：导通时 = 电压源 + 串联电阻（需要行）
                if self.state.get(br.id, {}).get("on"):
                    self._alloc(br.id)
            elif t == "bjt":
                self._alloc(br.id)          # be 结的分段线性电压源
        return len(self.extra)

    # ---- 各类元件 ----
    def _val(self, br: Br, default: float = 0.0) -> float:
        v = br.prm.get("value")
        return float(v) if v not in (None, "") else default

    @staticmethod
    def _stamp_g(A, p, n, g):
        if p >= 0:
            A[p, p] += g
        if n >= 0:
            A[n, n] += g
        if p >= 0 and n >= 0:
            A[p, n] -= g
            A[n, p] -= g

    def _stamp_reactive(self, A, b, br, domain, freq, h, prev, p, n):
        t = br.type
        val = self._val(br)
        if domain == DC:
            if t == "inductor":            # 直流：电感 = 短路
                self._stamp_zero_branch(A, br, p, n)
            return                          # 电容：直流开路（什么都不加）
        if domain == AC:
            Z = (1.0 / (1j * 2 * math.pi * freq * val)) if t == "capacitor" else (1j * 2 * math.pi * freq * val)
            if Z == 0:
                raise SolveError(f"{br.id} 参数为零")
            self._stamp_g(A, p, n, 1.0 / Z)
            return
        # 暂态：梯形法伴随模型（二阶精度，RC/RL 与解析解误差 <0.1%）
        st = prev.get(br.id) or {}
        vprev = float(st.get("v", 0.0)) if isinstance(st, dict) else float(st)
        iprev = float(st.get("i", 0.0)) if isinstance(st, dict) else 0.0
        if t == "capacitor":
            geq = 2.0 * val / h
            ieq = -geq * vprev - iprev
            self._stamp_g(A, p, n, geq)
            if p >= 0:
                b[p] -= ieq
            if n >= 0:
                b[n] += ieq
        else:
            geq = h / (2.0 * val)
            i0 = iprev + geq * vprev
            self._stamp_g(A, p, n, geq)
            if p >= 0:
                b[p] -= i0
            if n >= 0:
                b[n] += i0

    def _stamp_source(self, A, b, br, t, domain, freq, prev, p, n):
        if domain == TRAN:
            val = src_time(br, prev.get("__t__", 0.0))
        elif domain == AC:
            val = src_phasor(br) if str(br.prm.get("kind") or "dc").lower() in ("ac", "sin", "sine") else float(self._val(br))
        else:
            kind, v0, _, _ = source_of(br)
            val = 0.0 if kind == "ac" else (v0 if kind != "step" else v0)
        if t == "isource":
            if p >= 0:
                b[p] += val
            if n >= 0:
                b[n] -= val
            return
        row = self.extra[br.id]
        if p >= 0:
            A[p, row] += 1.0
            A[row, p] += 1.0
        if n >= 0:
            A[n, row] -= 1.0
            A[row, n] -= 1.0
        b[row] = val

    def _stamp_zero_branch(self, A, br, p, n):
        row = self.extra[br.id]
        if p >= 0:
            A[p, row] += 1.0
            A[row, p] += 1.0
        if n >= 0:
            A[n, row] -= 1.0
            A[row, n] -= 1.0

    def _stamp_controlled(self, A, b, br, t, p, n):
        gain = float(br.prm.get("gain") or 0.0)
        # 控制支路：前端给 control（元件位号），默认取第一个独立电压源
        ctrl_id = br.prm.get("control")
        if t in ("ccvs", "cccs") and not ctrl_id:
            for x in self.branches:
                if x.type in ("vsource", "vcvs", "ccvs") and x.id != br.id:
                    ctrl_id = x.id
                    break
        if t in ("vcvs", "vccs"):
            cp, cn = self.gi(br.node("c0")), self.gi(br.node("c1"))
            if t == "vcvs":
                row = self.extra[br.id]
                if p >= 0:
                    A[p, row] += 1.0
                    A[row, p] += 1.0
                if n >= 0:
                    A[n, row] -= 1.0
                    A[row, n] -= 1.0
                if cp >= 0:
                    A[row, cp] -= gain
                if cn >= 0:
                    A[row, cn] += gain
            else:
                # i(p→n) = gain·u(cp−cn)：在 KCL 里表现为受控电流源
                if p >= 0 and cp >= 0:
                    A[p, cp] += gain
                if p >= 0 and cn >= 0:
                    A[p, cn] -= gain
                if n >= 0 and cp >= 0:
                    A[n, cp] -= gain
                if n >= 0 and cn >= 0:
                    A[n, cn] += gain
        else:
            row_c = self.extra.get(ctrl_id)
            if row_c is None:
                raise SolveError(f"{br.id} 的控制支路 {ctrl_id} 不存在（只能受电压源类支路控制）")
            if t == "ccvs":
                row = self.extra[br.id]
                if p >= 0:
                    A[p, row] += 1.0
                    A[row, p] += 1.0
                if n >= 0:
                    A[n, row] -= 1.0
                    A[row, n] -= 1.0
                A[row, row_c] -= gain
            else:
                if p >= 0:
                    A[p, row_c] += gain
                if n >= 0:
                    A[n, row_c] -= gain

    def _stamp_transformer(self, A, b, br):
        n = float(br.prm.get("ratio") or 1.0)
        a, bb = self.gi(br.node("p0")), self.gi(br.node("p1"))
        c, d = self.gi(br.node("p2")), self.gi(br.node("p3"))
        r1, r2 = self.extra[br.id + ":1"], self.extra[br.id + ":2"]
        # V1 = n·V2
        for r, sgn in ((r1, 1.0), (r2, -n)):
            if a >= 0:
                A[r, a] += sgn
            if bb >= 0:
                A[r, bb] -= sgn
            if c >= 0:
                A[r, c] -= sgn * n
            if d >= 0:
                A[r, d] += sgn * n
        # i1 + i2/n = 0
        A[r2, r1] += 1.0
        A[r2, r2] += 1.0 / n
        # 电流注入
        if a >= 0:
            A[a, r1] += 1.0
        if bb >= 0:
            A[bb, r1] -= 1.0
        if c >= 0:
            A[c, r2] += 1.0
        if d >= 0:
            A[d, r2] -= 1.0

    def _stamp_opamp(self, A, b, br):
        """理想运放：虚短 V(inp)=V(inn) + 输出电流未知。"""
        ip, inn, o = self.gi(br.node("inp")), self.gi(br.node("inn")), self.gi(br.node("out"))
        row = self.extra[br.id]
        if ip >= 0:
            A[row, ip] += 1.0
        if inn >= 0:
            A[row, inn] -= 1.0
        if o >= 0:
            A[o, row] += 1.0
            A[row, o] += 0.0

    def _stamp_switch(self, A, b, br, p, n):
        if self.state.get(br.id, {}).get("closed", bool(br.prm.get("closed", True))):
            self._stamp_zero_branch(A, br, p, n)

    def _stamp_diode(self, A, b, br, t, p, n):
        st = self.state.get(br.id)
        if not st or not st.get("on"):
            return
        vth = float(br.prm.get("vth", 0.7 if t == "diode" else 0.7))
        rd = float(br.prm.get("rd", 0.0) or 0.0)
        if t == "zener" and st.get("mode") == "breakdown":
            vth = -float(br.prm.get("vz", 5.1))
        row = self.extra[br.id]
        if p >= 0:
            A[p, row] += 1.0
            A[row, p] += 1.0
        if n >= 0:
            A[n, row] -= 1.0
            A[row, n] -= 1.0
        A[row, row] -= rd
        b[row] = vth

    def _stamp_bjt(self, A, b, br, p, n):
        """三极管：
        直流（Q点）：Vbe≈0.7V + Ic = β·Ib（流控电流源）
        交流（微变等效）：rbe 电阻 + gm·Vbe 压控电流源（π 模型）
        """
        bnode = self.gi(br.node("b"))
        cnode = self.gi(br.node("c"))
        enode = self.gi(br.node("e"))
        beta = float(br.prm.get("beta") or 100.0)
        if self.gm_extra.get(br.id):
            gm = float(self.gm_extra[br.id].get("gm", 0.0))
            rbe = float(self.gm_extra[br.id].get("rbe", 0.0))
            if rbe > 0:
                self._stamp_g(A, bnode, enode, 1.0 / rbe)
            # Ic = gm·Vbe（从 c 流向 e）
            if cnode >= 0 and bnode >= 0:
                A[cnode, bnode] += gm
            if cnode >= 0 and enode >= 0:
                A[cnode, enode] -= gm
            if enode >= 0 and bnode >= 0:
                A[enode, bnode] -= gm
            if enode >= 0 and enode >= 0:
                A[enode, enode] += gm
            return
        vbe = float(br.prm.get("vbe", 0.7) or 0.7)
        row = self.extra[br.id]
        if bnode >= 0:
            A[bnode, row] += 1.0
            A[row, bnode] += 1.0
        if enode >= 0:
            A[enode, row] -= 1.0
            A[row, enode] -= 1.0
        b[row] = vbe
        # Ic = β·Ib（Ib = 该支路电流）
        if cnode >= 0:
            A[cnode, row] += beta
        if enode >= 0:
            A[enode, row] -= beta

    # ---- 求解 ----
    def solve_once(self, domain: str, freq: float, h: float = 0.0,
                   prev: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        A, b = self.assemble(domain, freq, h, prev)
        if A.shape[0] == 0:
            return {"V": {self.ground: 0.0}, "I": {}, "x": None}
        try:
            x = np.linalg.solve(A, b)
        except np.linalg.LinAlgError as exc:
            raise SolveError("电路方程奇异：可能浮空、缺少到地的通路、或理想源冲突。") from exc
        V = {n: (x[i] if not (domain == AC and abs(np.imag(x[i])) < 1e-12 * max(1.0, abs(x[i])))
                 else x[i]) for n, i in self.nidx.items()}
        V = {n: complex(x[i]) if domain == AC else float(x[i]) for n, i in self.nidx.items()}
        V[self.ground] = 0j if domain == AC else 0.0
        I = self._branch_currents(V, x, domain, freq, h, prev)
        return {"V": V, "I": I, "x": x}

    def _branch_currents(self, V, x, domain, freq, h, prev) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for br in self.branches:
            t = br.type
            p, n = br.node("p0"), br.node("p1")
            vp, vn = V.get(p, 0), V.get(n, 0)
            if t == "resistor":
                out[br.id] = (vp - vn) / self._val(br) if self._val(br) else 0.0
            elif t == "capacitor":
                if domain == AC:
                    Z = 1.0 / (1j * 2 * math.pi * freq * self._val(br))
                    out[br.id] = (vp - vn) / Z
                elif domain == TRAN:
                    st = prev.get(br.id) or {}
                    vprev = float(st.get("v", 0.0)) if isinstance(st, dict) else float(st)
                    iprev = float(st.get("i", 0.0)) if isinstance(st, dict) else 0.0
                    geq = 2.0 * self._val(br) / h
                    out[br.id] = geq * (vp - vn) + (-geq * vprev - iprev)
                else:
                    out[br.id] = 0.0
            elif t == "inductor":
                if domain == AC:
                    out[br.id] = (vp - vn) / (1j * 2 * math.pi * freq * self._val(br))
                elif domain == TRAN:
                    st = prev.get(br.id) or {}
                    vprev = float(st.get("v", 0.0)) if isinstance(st, dict) else float(st)
                    iprev = float(st.get("i", 0.0)) if isinstance(st, dict) else 0.0
                    geq = h / (2.0 * self._val(br))
                    out[br.id] = geq * (vp - vn) + (iprev + geq * vprev)
                else:
                    out[br.id] = float(x[self.extra[br.id]])
            elif t in ("vsource", "vcvs", "ccvs"):
                out[br.id] = x[self.extra[br.id]]
            elif t == "isource":
                out[br.id] = -self._src_value(br, domain, freq, prev)
            elif t == "switch":
                out[br.id] = x[self.extra[br.id]] if br.id in self.extra else 0.0
            elif t in ("diode", "zener"):
                st = self.state.get(br.id)
                if st and st.get("on"):
                    row = self.extra[br.id]
                    rd = float(br.prm.get("rd", 0.0) or 0.0)
                    out[br.id] = float(x[row])
                else:
                    out[br.id] = 0.0
            elif t == "bjt":
                if self.gm_extra.get(br.id):
                    gm = float(self.gm_extra[br.id]["gm"])
                    out[br.id] = gm * (V.get(br.node("b"), 0) - V.get(br.node("e"), 0))
                else:
                    out[br.id] = float(x[self.extra[br.id]])
            elif t == "opamp":
                out[br.id] = x[self.extra[br.id]]
            elif t == "transformer":
                out[br.id] = x[self.extra[br.id + ":1"]]
            else:
                out[br.id] = 0.0
        return out

    def _src_value(self, br, domain, freq, prev):
        if domain == AC:
            if str(br.prm.get("kind") or "dc").lower() in ("ac", "sin", "sine"):
                return src_phasor(br)
            return complex(self._val(br))
        if domain == TRAN:
            return src_time(br, (prev or {}).get("__t__", 0.0))
        return float(self._val(br))
