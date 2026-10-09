"""核心冒烟测试（无需 pytest 也可运行）：
    env\\python.exe solver\\tests\\test_core.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from solver.app.analysis import analyze
from solver.app.models import Component, Pin, Point, Schematic, SolveRequest, Wire


def _divider() -> Schematic:
    comps = [
        Component(id="V1", type="vsource", value=5.0, pins=[Pin(name="p0", x=100, y=100), Pin(name="p1", x=100, y=160)]),
        Component(id="R1", type="resistor", value=1000.0, pins=[Pin(name="p0", x=200, y=100), Pin(name="p1", x=300, y=100)]),
        Component(id="R2", type="resistor", value=1000.0, pins=[Pin(name="p0", x=300, y=100), Pin(name="p1", x=300, y=160)]),
        Component(id="GND1", type="ground", pins=[Pin(name="p0", x=100, y=160)]),
    ]
    wires = [
        Wire(id="w1", vertices=[Point(x=100, y=100), Point(x=200, y=100)]),
        Wire(id="w2", vertices=[Point(x=300, y=160), Point(x=100, y=160)]),
    ]
    return Schematic(components=comps, wires=wires, junctions=[])


def test_divider():
    res = analyze(SolveRequest(session_id="t1", schematic=_divider(), mode="both"), True)
    assert res.ok, res.diagnostics
    volts = {n: round(res.nodes[n].voltage, 6) for n in res.node_order}
    assert sorted(volts.values()) == [0.0, 2.5, 5.0], volts
    # 中间节点（2.5V）应有分压符号式
    mid = [n for n in res.node_order if abs(res.nodes[n].voltage - 2.5) < 1e-9][0]
    assert res.nodes[mid].voltage_latex, res.nodes[mid]
    assert "R" in (res.nodes[mid].voltage_latex or ""), res.nodes[mid].voltage_latex
    assert res.validation is not None and res.validation.ok, res.validation
    r1 = [b for b in res.branches if b.component == "R1"][0]
    assert abs(r1.current - 0.0025) < 1e-9, r1.current
    print("[OK] test_divider:", volts)
    print("     netlist:", " | ".join((res.netlist or "").splitlines()))
    print("     分压符号式 latex:", res.nodes[mid].voltage_latex)


def test_isource():
    comps = [
        Component(id="I1", type="isource", value=1.0, pins=[Pin(name="p0", x=100, y=100), Pin(name="p1", x=100, y=160)]),
        Component(id="R1", type="resistor", value=1.0, pins=[Pin(name="p0", x=200, y=100), Pin(name="p1", x=200, y=160)]),
        Component(id="GND1", type="ground", pins=[Pin(name="p0", x=100, y=160)]),
    ]
    wires = [
        Wire(id="w1", vertices=[Point(x=100, y=100), Point(x=200, y=100)]),
        Wire(id="w2", vertices=[Point(x=100, y=160), Point(x=200, y=160)]),
    ]
    sch = Schematic(components=comps, wires=wires, junctions=[])
    res = analyze(SolveRequest(session_id="t2", schematic=sch, mode="both"), True)
    assert res.ok, res.diagnostics
    n1 = [n for n in res.node_order if n != "0"][0]
    assert abs(res.nodes[n1].voltage - 1.0) < 1e-9, res.nodes[n1].voltage
    print("[OK] test_isource: V =", res.nodes[n1].voltage, "| validation:", res.validation.ok)


def test_node_stability():
    r1 = analyze(SolveRequest(session_id="stab", schematic=_divider(), mode="numeric"), False)
    ids1 = sorted(r1.node_order)

    sch2 = _divider()
    dx, dy = 37.0, 120.0
    for c in sch2.components:
        for p in c.pins:
            p.x += dx
            p.y += dy
    for w in sch2.wires:
        for v in w.vertices:
            v.x += dx
            v.y += dy
    r2 = analyze(SolveRequest(session_id="stab", schematic=sch2, mode="numeric"), False)
    ids2 = sorted(r2.node_order)
    assert ids1 == ids2, (ids1, ids2)
    for nid in ids1:
        assert abs(r1.nodes[nid].voltage - r2.nodes[nid].voltage) < 1e-9
    print("[OK] test_node_stability: 平移后节点集合保持", ids2)


def test_no_ground():
    sch = _divider()
    sch.components = [c for c in sch.components if c.type != "ground"]
    res = analyze(SolveRequest(session_id="nog", schematic=sch, mode="numeric"), False)
    # 未接地：现在会自动选择参考节点继续求解（电流可求，节点电压为相对值）
    assert res.ok, res.diagnostics
    assert any(d.code == "NO_GROUND" for d in res.diagnostics), res.diagnostics
    r1 = [b for b in res.branches if b.component == "R1"][0]
    assert abs(abs(r1.current) - 0.0025) < 1e-9, r1.current
    print("[OK] test_no_ground: 未接地→自动参考，电流正确 R1 =", r1.current)


def test_unknown_symbol():
    """未知量占位：元件不填数值（或填符号）时，仍给符号式；
    与未知量无关的量照常给出数值（不再整片变空）。"""
    sch = _divider()
    for c in sch.components:
        if c.id == "R2":
            c.value = None
            c.symbol = "Rx"
    res = analyze(SolveRequest(session_id="unk", schematic=sch, mode="both"), True)
    assert res.ok, res.diagnostics
    assert any(d.code == "UNKNOWN_VALUE" for d in res.diagnostics), res.diagnostics
    nums = {n: res.nodes[n].voltage for n in res.node_order}
    assert 5.0 in [round(v, 6) for v in nums.values() if v is not None], nums
    exprs = [res.nodes[n].voltage_expr or "" for n in res.node_order if n != "0"]
    assert any("Rx" in e for e in exprs), exprs
    assert any(res.nodes[n].voltage is None for n in res.node_order if n != "0"), nums
    r2 = [b for b in res.branches if b.component == "R2"][0]
    assert r2.current is None and r2.current_latex, r2
    print("[OK] test_unknown_symbol: nums =", nums, "| exprs =", exprs)


if __name__ == "__main__":
    test_divider()
    test_isource()
    test_node_stability()
    test_no_ground()
    test_unknown_symbol()
    print("\nALL PASSED")
