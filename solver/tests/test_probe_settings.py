"""节点探针 + 设置读写 测试。
    env\\python.exe solver\\tests\\test_probe_settings.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from solver.app import tools as T
from solver.app.analysis import STORE, analyze
from solver.app.config import CONFIG, public_settings, update_settings
from solver.app.models import Component, Pin, Point, Schematic, SolveRequest, Wire


def divider():
    comps = [
        Component(id="V1", type="vsource", value=5.0, pins=[Pin(name="p0", x=200, y=270), Pin(name="p1", x=200, y=330)]),
        Component(id="R1", type="resistor", value=1000.0, pins=[Pin(name="p0", x=320, y=270), Pin(name="p1", x=380, y=270)]),
        Component(id="R2", type="resistor", value=1000.0, pins=[Pin(name="p0", x=320, y=400), Pin(name="p1", x=380, y=400)]),
        Component(id="GND1", type="ground", pins=[Pin(name="p0", x=200, y=400)]),
    ]
    wires = [
        Wire(id="w1", vertices=[Point(x=200, y=270), Point(x=320, y=270)]),
        Wire(id="w2", vertices=[Point(x=380, y=270), Point(x=430, y=270), Point(x=430, y=400), Point(x=380, y=400)]),
        Wire(id="w3", vertices=[Point(x=320, y=400), Point(x=200, y=400)]),
        Wire(id="w4", vertices=[Point(x=200, y=400), Point(x=200, y=330)]),
    ]
    return Schematic(components=comps, wires=wires, junctions=[])


def main():
    STORE.set_schematic("ps", divider())
    res = analyze(SolveRequest(session_id="ps", schematic=divider(), mode="both"), True)
    mid = [n for n in res.node_order if abs(res.nodes[n].voltage - 2.5) < 1e-9][0]

    d = T.node_detail("ps", mid)
    print("节点:", d["node"], "电压:", d["voltage"])
    print("符号式:", d["voltage_latex"])
    print("相关支路:", [(b["component"], round(b["current"], 6), "离开" if b["leaving"] else "流入") for b in d["branches"]])
    print("KCL:", d["kcl_latex"])
    print("方法:", d["method"][:40], "...")
    assert abs(d["voltage"] - 2.5) < 1e-9
    assert len(d["branches"]) == 2, d["branches"]
    assert d["kcl_latex"].endswith("= 0")
    assert d["voltage_latex"]

    # 设置读写（白名单 + 持久化）
    before = public_settings()
    print("默认 memory_enabled:", before["ai"]["memory_enabled"], "max_turns:", before["ai"]["memory_max_turns"])
    after = update_settings({"ai": {"memory_enabled": False, "memory_max_turns": 3, "model": "deepseek-v4-pro"},
                             "ui": {"current_animation": False},
                             "hacker": {"x": 1}})
    assert after["ai"]["memory_enabled"] is False
    assert after["ai"]["memory_max_turns"] == 3
    assert after["ai"]["model"] == "deepseek-v4-pro"
    assert after["ui"]["current_animation"] is False
    assert "hacker" not in after
    print("写入后:", after["ai"]["memory_enabled"], after["ai"]["memory_max_turns"], after["ai"]["model"])
    assert CONFIG["ai"]["memory_enabled"] is False

    # 还原
    update_settings({"ai": {"memory_enabled": True, "memory_max_turns": 10, "model": "deepseek-flash"},
                     "ui": {"current_animation": True}})
    print("PROBE+SETTINGS OK")


if __name__ == "__main__":
    main()
