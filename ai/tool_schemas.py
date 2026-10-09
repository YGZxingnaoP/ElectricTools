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
            "description": "对指定端口做戴维南等效，返回开路电压 Voc、短路电流 Isc、等效电阻 Rth。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_a": {"type": "string", "description": "端口正端节点 ID"},
                    "node_b": {"type": "string", "description": "端口负端节点 ID"},
                },
                "required": ["node_a", "node_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_norton",
            "description": "对指定端口做诺顿等效，返回短路电流 In 与等效电阻 Rn。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_a": {"type": "string", "description": "端口正端节点 ID"},
                    "node_b": {"type": "string", "description": "端口负端节点 ID"},
                },
                "required": ["node_a", "node_b"],
            },
        },
    },
]
