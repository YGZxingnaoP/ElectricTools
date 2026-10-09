"""端口等效 + AI 工具函数测试。
    env\\python.exe solver\\tests\\test_tools.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from solver.app import tools as T
from solver.app.analysis import STORE, analyze
from solver.app.equivalence import port_iv_curve, port_norton, port_thevenin
from solver.app.models import Component, Pin, Point, Schematic, SolveRequest, Wire
from solver.app.topology import derive_topology, NodeRegistry


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
    # 拓扑：找中点节点（2.5V）
    res = analyze(SolveRequest(session_id="eq", schematic=divider(), mode="both"), True)
    mid = [n for n in res.node_order if abs(res.nodes[n].voltage - 2.5) < 1e-9][0]

    topo = derive_topology(divider(), NodeRegistry())
    nodes = {nid: info for nid, info in topo.nodes.items()}
    th = port_thevenin(nodes, topo.branches, mid, "0")
    print("Thevenin:", th)
    assert abs(th["voc"] - 2.5) < 1e-9, th
    assert abs(th["rth"] - 500.0) < 1e-6, th          # R1||R2 = 500
    assert abs(th["isc"] - 0.005) < 1e-12, th          # 5mA

    nr = port_norton(nodes, topo.branches, mid, "0")
    print("Norton:", nr)
    assert abs(nr["in"] - 0.005) < 1e-12

    curve = port_iv_curve(nodes, topo.branches, mid, "0", vmax=2.0, steps=5)
    print("IV curve:", curve)
    assert len(curve) == 5

    # 工具函数
    STORE.set_schematic("tq", divider())
    nl = T.get_circuit_netlist("tq")
    print("netlist:", nl["netlist"])
    v = T.solve_node_voltage("tq", mid)
    print("node voltage:", v["node"], v["voltage"], v["latex"])
    i = T.solve_branch_current("tq", "R1")
    print("branch:", i["component"], i["current"], i["reference_direction"])
    kcl = T.get_kcl_equations("tq", mid)
    print("KCL:", kcl["kcl_latex"])
    thv = T.apply_thevenin("tq", mid, "0")
    print("apply_thevenin:", thv["voc"], thv["rth"])

    assert abs(v["voltage"] - 2.5) < 1e-9
    assert "latex" in v
    assert "= 0" in kcl["kcl_latex"]
    print("TOOLS OK")


if __name__ == "__main__":
    main()
