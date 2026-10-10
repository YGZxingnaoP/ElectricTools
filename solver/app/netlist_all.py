"""符号网表构建（lcapy）—— 支持器件从 R/V/I 扩展到全部线性器件。

lcapy 靠元件名的首字母判断类型：
  R 电阻  C 电容  L 电感  V 电压源  I 电流源  E 压控电压源  G 压控电流源
  H 流控电压源  F 流控电流源  TF 理想变压器
非线性器件（二极管/稳压管/三极管/运放/三相）不在此通道，交给数值引擎。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

_SYM_BAD = re.compile(r"[^0-9A-Za-z_]")

# 首字母 → 参数写法。value=数值符号；extra=额外参数（相位等）
NETLIST = {
    "resistor": "R", "capacitor": "C", "inductor": "L",
    "vsource": "V", "isource": "I",
    "vcvs": "E", "vccs": "G", "ccvs": "H", "cccs": "F",
    "transformer": "TF", "switch": "V",
}
# 这些交给数值引擎，不走符号通道
UNSUPPORTED = {"diode", "zener", "bjt", "opamp", "vsource3"}


def symbol_name(raw: Any) -> str:
    s = _SYM_BAD.sub("_", str(raw or "").strip()).strip("_") or "X"
    return ("X" + s) if s[0].isdigit() else s


def build(branches: List[dict], ground: str = "0"):
    """返回 (netlist, name_of, subs, sym_meta, skipped)"""
    lines: List[str] = []
    name_of: Dict[str, str] = {}
    subs: Dict[str, Any] = {}
    sym_meta: Dict[str, Dict[str, str]] = {}
    skipped: List[str] = []
    counters: Dict[str, int] = {}
    used: set = set()

    def lc(nid):
        return "0" if nid == ground else str(nid)

    # 第一趟：分配元件名（流控源/变压器要用到别的支路名）
    plan = []
    for br in branches:
        t = br.get("type")
        if t in UNSUPPORTED:
            skipped.append(br.get("component"))
            continue
        if t not in NETLIST:
            skipped.append(br.get("component"))
            continue
        pre = NETLIST[t]
        counters[pre] = counters.get(pre, 0) + 1
        name = f"{pre}{counters[pre]}"
        name_of[br["component"]] = name
        sym = symbol_name(br.get("symbol") or br.get("component")) or f"{pre}{counters[pre]}"
        while sym in used:
            sym = f"{sym}_2"
        used.add(sym)
        val = br.get("value")
        if val is not None:
            subs[sym] = val
        sym_meta[sym] = {"component": br.get("component"), "type": t}
        plan.append((br, t, name, sym))

    # 第二趟：写网表行
    for br, t, name, sym in plan:
        a, b = lc(br.get("node_p")), lc(br.get("node_n"))
        if a in (None, "None") or b in (None, "None"):
            skipped.append(br.get("component"))       # 缺节点信息 → 不能写进网表（否则出现 "None"）
            continue
        if t in ("resistor", "capacitor", "inductor"):
            lines.append(f"{name} {a} {b} {sym}")
        elif t == "switch":
            # 闭合 = 0V 电压源（短路）；断开 = 该支路不写（开路）
            if br.get("closed", True) is False:
                skipped.append(br.get("component"))
                continue
            lines.append(f"{name} {a} {b} 0")
        elif t in ("vsource", "isource"):
            kind = str(br.get("kind") or "dc").lower()
            if kind in ("ac", "sin", "sine"):
                ph = br.get("phase")
                phs = float(ph) if ph is not None else 0.0
                lines.append(f"{name} {a} {b} ac {sym} {phs}")
            elif kind == "step":
                lines.append(f"{name} {a} {b} step {sym}")
            else:
                lines.append(f"{name} {a} {b} {sym}")
        elif t in ("vcvs", "vccs"):
            c0, c1 = lc(br.get("c0_node")), lc(br.get("c1_node"))
            lines.append(f"{name} {a} {b} {c0} {c1} {sym}")
        elif t in ("ccvs", "cccs"):
            ctrl = br.get("control")
            cname = name_of.get(ctrl) if ctrl else None
            if not cname:                      # 没指定控制支路 → 取第一个电压源
                for x in plan:
                    if x[1] == "vsource":
                        cname = x[2]
                        break
            if not cname:
                skipped.append(br.get("component"))
                continue
            lines.append(f"{name} {a} {b} {cname} {sym}")
        elif t == "transformer":
            c = lc(br.get("n2_node")) if br.get("n2_node") else None
            d = lc(br.get("n3_node")) if br.get("n3_node") else None
            if c is None or d is None:
                skipped.append(br.get("component"))
                continue
            lines.append(f"{name} {a} {b} {c} {d} {sym}")
    return "\n".join(lines), name_of, subs, sym_meta, skipped
