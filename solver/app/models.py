"""数据模型（Pydantic v2）。

几何与拓扑的分工：
- 前端是**几何**的权威：元件位置 + 各引脚绝对坐标、导线折线顶点。
- 后端是**拓扑**的权威：由几何推导电气节点与稳定 NodeID。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    type: str  # resistor / capacitor / inductor / vsource / isource / vcvs / ... / ground
    value: Optional[float] = None
    symbol: Optional[str] = None  # 未知量占位（如 "R"、"Ux"）：设置后按未知量处理，只给符号式
    unit: Optional[str] = None
    pins: List[Pin] = Field(default_factory=list)
    # ★ 多参数元件（C/L/交流源/受控源/变压器/半导体…）的参数放这里：
    #   kind(dc|ac|step)、freq、phase、gain、control、ratio、vth、rd、vz、beta、vbe、type…
    params: Dict[str, Any] = Field(default_factory=dict)
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


class Condition(BaseModel):
    """图上标注的「已知量」：由前端的**位置成员键**定位（几何→拓扑由后端解析）。

    key  ：u:<元件ID>/<引脚名> 或 w:<导线ID> 或 j:<节点圆点ID>  → 表示"这个节点的电压"
            c:<元件ID>                                        → 表示"这条支路的电流"
    kind ：node_voltage（节点电压，单位 V） | branch_current（支路电流，单位 A）
    value：该量等于多少
    """
    key: str
    kind: str = "node_voltage"
    value: Any = None


class Schematic(BaseModel):
    components: List[Component] = Field(default_factory=list)
    wires: List[Wire] = Field(default_factory=list)
    junctions: List[Junction] = Field(default_factory=list)
    # 画在图上、随存档保存的已知量标注；求解时自动当作条件使用
    conditions: List[Condition] = Field(default_factory=list)


# ---------- 请求 ----------

class SolveRequest(BaseModel):
    session_id: str = "default"
    schematic: Schematic
    mode: str = "numeric"  # numeric | symbolic | both
    analysis: str = "dc"   # 兼容旧字段：dc | ac | tran
    domain: Optional[str] = None   # dc | ac | tran（优先于 analysis）
    freq: Optional[float] = None   # 交流频率 Hz
    tstop: Optional[float] = None  # 暂态终止时间 s
    nsteps: Optional[int] = None   # 暂态步数


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

class Phasor(BaseModel):
    """相量（正弦稳态）：re/im 为复数分量，rms 有效值，phase 相角(度)。"""
    re: float = 0.0
    im: float = 0.0
    rms: Optional[float] = None
    phase: Optional[float] = None
    peak: Optional[float] = None


class NodeResult(BaseModel):
    id: str
    members: List[str] = Field(default_factory=list)
    voltage: Optional[float] = None        # 数值（V，对地）；交流时=有效值
    phasor: Optional[Phasor] = None        # 交流相量
    voltage_expr: Optional[str] = None     # 符号式（字符串）
    voltage_latex: Optional[str] = None
    voltage_latex_sub: Optional[str] = None   # 代入已知数值后的式子（只剩未知量）
    voltage_decomp: Optional[dict] = None     # 公式拆解（项 / 分子分母因子 / 依据）
    is_reference: bool = False                # 是不是被选作参考电位的节点（它的 0 V 是定义）


class BranchResult(BaseModel):
    component: str
    type: str
    node_p: str
    node_n: str
    current: Optional[float] = None        # 数值（A，参考方向 p->n）；交流时=有效值
    phasor: Optional[Phasor] = None        # 交流相量
    current_expr: Optional[str] = None
    current_latex: Optional[str] = None
    current_latex_sub: Optional[str] = None   # 代入已知数值后的式子
    current_decomp: Optional[dict] = None     # 公式拆解
    voltage: Optional[float] = None
    power: Optional[dict] = None              # 交流：{p,q,s,pf}；直流：{p}


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
    domain: Optional[str] = None            # dc | ac | tran
    freq: Optional[float] = None            # 交流频率
    waveform: Optional[dict] = None         # 暂态波形 {"t": [...], "V:n1": [...], "I:R1": [...], "U:C1": [...]}
    constraints: Optional[dict] = None      # 反解/填空结果
    # 图上标注了「已知量」且电路存在未知量时，自动反解出的结果（见 constraints.py）
    constraint_result: Optional[Dict[str, Any]] = None
