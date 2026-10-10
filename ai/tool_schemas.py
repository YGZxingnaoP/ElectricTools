"""工具定义（OpenAI function-calling 格式，DeepSeek 兼容）。"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_circuit_netlist",
            "description": "获取当前电路的完整网表（节点、元件、连接关系）与节点电压。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_node_voltage",
            "description": "求解指定节点的电压（数值 + 符号式 + LaTeX）。",
            "parameters": {
                "type": "object",
                "properties": {"node": {"type": "string", "description": "节点 ID，如 n1"}},
                "required": ["node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_branch_current",
            "description": "求解指定元件的支路电流（参考方向 p0→p1，数值 + LaTeX）。",
            "parameters": {
                "type": "object",
                "properties": {"component": {"type": "string", "description": "元件 ID，如 R1"}},
                "required": ["component"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kcl_equations",
            "description": "获取指定节点的 KCL 方程（LaTeX）。",
            "parameters": {
                "type": "object",
                "properties": {"node": {"type": "string", "description": "节点 ID"}},
                "required": ["node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_thevenin",
            "description": "对指定端口做戴维南等效，返回开路电压 Voc、短路电流 Isc、等效电阻 Rth。"
                           "若要求「某元件（如负载 R）为何值时获得最大功率」，请用 exclude 把它本身排除后再求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_a": {"type": "string", "description": "端口正端节点 ID"},
                    "node_b": {"type": "string", "description": "端口负端节点 ID"},
                    "exclude": {
                        "type": "array", "items": {"type": "string"},
                        "description": "要从网络中移走的元件 ID 列表（例如被求的负载电阻）",
                    },
                },
                "required": ["node_a", "node_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_norton",
            "description": "对指定端口做诺顿等效，返回短路电流 In 与等效电阻 Rn（同样支持 exclude）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_a": {"type": "string", "description": "端口正端节点 ID"},
                    "node_b": {"type": "string", "description": "端口负端节点 ID"},
                    "exclude": {
                        "type": "array", "items": {"type": "string"},
                        "description": "要从网络中移走的元件 ID 列表",
                    },
                },
                "required": ["node_a", "node_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_unknowns_with_conditions",
            "description": "【通用反解】把图上数值留空的元件当作未知量，用若干条条件（某个量 = 某个数）解出它们的代数值。"
                           "未知量和条件都可以是多条。例如「已知 V_n2 = 2 V，求 R5」→ "
                           "conditions=[{kind:'node_voltage', ref:'n2', value:2}]；"
                           "「V_mid = 2.5V 且 I(R1) = 2.5mA」→ 两条条件一起给。"
                           "会返回每个未知量的数值、是否物理可行，以及分步推导；欠定/无解/多解也会明确说明。",
            "parameters": {
                "type": "object",
                "properties": {
                    "conditions": {
                        "type": "array",
                        "description": "条件列表，每条形如 {kind, ref, value}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["node_voltage", "branch_current"],
                                    "description": "node_voltage=节点电压（ref 填节点 ID）；branch_current=支路电流（ref 填元件 ID）",
                                },
                                "ref": {"type": "string", "description": "节点 ID（如 n2）或元件 ID（如 R1）"},
                                "value": {"type": "number", "description": "该量等于多少（SI 单位：V 或 A）"},
                            },
                            "required": ["kind", "ref", "value"],
                        },
                    },
                },
                "required": ["conditions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_component_for_target",
            "description": "逆运算（反推元件数值）：已知某个目标量应该等于多少，求某个元件（电阻/电压源/电流源）的数值。"
                           "例如『求 R5 使 V_n2 = 2V』→ component=R5, target_kind=node_voltage, target_ref=n2, target_value=2；"
                           "『求 I1 使 R2 的电流为 0.5A』→ target_kind=branch_current, target_ref=R2。"
                           "返回解 + 分步推导（可直接讲给学生）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "component": {"type": "string", "description": "要反推的元件 ID，如 R5"},
                    "target_kind": {
                        "type": "string",
                        "enum": ["node_voltage", "branch_current"],
                        "description": "目标量类型：node_voltage=节点电压，branch_current=支路电流",
                    },
                    "target_ref": {"type": "string", "description": "目标对象：节点电压填节点 ID（如 n2）；支路电流填元件 ID（如 R1）"},
                    "target_value": {"type": "number", "description": "目标值（SI 单位：V 或 A）"},
                },
                "required": ["component", "target_kind", "target_ref", "target_value"],
            },
        },
    },
]
