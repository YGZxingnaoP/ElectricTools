"""数据模型（Pydantic v2）。

几何与拓扑的分工（见 docs/drawing-model.md）：
- 前端是**几何**的权威：元件位置 + 各引脚绝对坐标、导线折线顶点。
- 后端是**拓扑**的权威：由几何推导电气节点与稳定 NodeID。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------- 几何（前端上传） ----------

class Point(BaseModel):
    x: float
    y: float


class Pin(BaseModel):
    name: str
    x: float
    y: float


class Component(BaseModel):
    id: str
    type: str  # resistor / vsource / isource / ground / ...
    value: Optional[float] = None
    unit: Optional[str] = None
    pins: List[Pin] = Field(default_factory=list)
    # 便于回显（非拓扑必需）
    label: Optional[str] = None
    rotation: Optional[float] = 0.0
    mirror: Optional[bool] = False


class Wire(BaseModel):
    id: str
    vertices: List[Point] = Field(default_factory=list)


class Junction(BaseModel):
    id: str
    x: float
    y: float


class Schematic(BaseModel):
    components: List[Component] = Field(default_factory=list)
    wires: List[Wire] = Field(default_factory=list)
    junctions: List[Junction] = Field(default_factory=list)


# ---------- 请求 ----------

class SolveRequest(BaseModel):
    session_id: str = "default"
    schematic: Schematic
    mode: str = "numeric"  # numeric | symbolic | both
    analysis: str = "dc"  # dc | ac | tran（当前仅 dc）


class NodeRefRequest(BaseModel):
    session_id: str = "default"
    schematic: Schematic
    node: str


class TheveninRequest(BaseModel):
    session_id: str = "default"
    schematic: Schematic
    node_a: str
    node_b: str


# ---------- 结果 ----------

class NodeResult(BaseModel):
    id: str
    members: List[str] = Field(default_factory=list)
    voltage: Optional[float] = None        # 数值（V，对地）
    voltage_expr: Optional[str] = None     # 符号式（字符串）
    voltage_latex: Optional[str] = None


class BranchResult(BaseModel):
    component: str
    type: str
    node_p: str
    node_n: str
    current: Optional[float] = None        # 数值（A，参考方向 p->n）
    current_expr: Optional[str] = None
    current_latex: Optional[str] = None
    voltage: Optional[float] = None


class Diagnostic(BaseModel):
    level: str  # info | warn | error
    code: str
    message: str


class ValidationResult(BaseModel):
    ok: bool
    max_abs_diff: Optional[float] = None   # |V_lcapy - V_mna| 最大绝对差
    max_rel_diff: Optional[float] = None
    tol: Optional[float] = None
    details: Dict[str, float] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class SolveResult(BaseModel):
    ok: bool
    node_order: List[str] = Field(default_factory=list)
    nodes: Dict[str, NodeResult] = Field(default_factory=dict)
    branches: List[BranchResult] = Field(default_factory=list)
    diagnostics: List[Diagnostic] = Field(default_factory=list)
    validation: Optional[ValidationResult] = None
    netlist: Optional[str] = None
