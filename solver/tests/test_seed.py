"""端到端：用与前端预置分压电路完全一致的几何，验证拓扑与解。
    env\\python.exe solver\\tests\\test_seed.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from solver.app.analysis import analyze
from solver.app.models import Component, Pin, Point, Schematic, SolveRequest, Wire


def build():
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
    res = analyze(SolveRequest(session_id="seed", schematic=build(), mode="both"), True)
    assert res.ok, res.diagnostics
    volt = {n: round(res.nodes[n].voltage, 4) for n in res.node_order}
    print("nodes:", volt)
    assert sorted(volt.values()) == [0.0, 2.5, 5.0], volt
    # 三个电气节点
    assert len(res.node_order) == 3, res.node_order
    # 分压符号式
    mid = [n for n in res.node_order if abs(res.nodes[n].voltage - 2.5) < 1e-9][0]
    print("netlist:", " | ".join((res.netlist or "").splitlines()))
    print("mid latex:", res.nodes[mid].voltage_latex)
    print("validation:", res.validation.ok if res.validation else None)
    assert res.validation and res.validation.ok
    print("SEED OK")


if __name__ == "__main__":
    main()
