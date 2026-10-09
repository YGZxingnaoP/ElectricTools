# ElectricTools 架构方案 v2.1

> 版本：2.1（在 v2 基础上纳入 Q1–Q8 决策）
> 状态：**设计定稿阶段，暂不实施代码**
> 运行时基线：根目录内嵌 `env\python.exe`（Python 3.11.9）+ 系统 Node.js v24.17.0
> 关联文档：[`ambiguities.md`](./ambiguities.md)、[`drawing-model.md`](./drawing-model.md)

---

## 0. 版本变更

### v1 → v2
| 项 | v1 | v2 | 原因 |
|---|---|---|---|
| 数值校验 | PySpice 交叉校验 | **移除 PySpice**，改「独立 MNA 数值预言机 + 物理不变量残差」 | NgSpice 共享库非 pip 可装；内嵌 Python 无 pip/site |
| 符号引擎 | "Leapy" | 统一 **lcapy** | PyPI `leapy` 与电路无关 |
| AI 模型 | `deepseek-reasoner` | **`deepseek-flash` / `deepseek-v4-pro`** | 旧名已不在官方列表 |
| 端口等效 | PySpice DC sweep | lcapy 解析式 + MNA 数值扫描 | 去 PySpice |

### v2 → v2.1（本次，纳入 Q1–Q8）
| # | 决策 | 落地 |
|---|---|---|
| Q1 | env 用其自带 `get-pip.py` 构建，**必须用 env 内的解释器** | §2.3 |
| Q2 | **引入构建工具**（Vite） | §3.1 |
| Q3 | **求解是程序行为**；AI 仅在用户提问时触发并调用工具 | §4.0、§6.1 |
| Q4 | 交互像 **Scratch**：元件面板拖放 + 参数输入 | §3.2、drawing-model §6 |
| Q5 | 本质是**用户实时绘制工程图** | 独立文档 [`drawing-model.md`](./drawing-model.md) |
| Q6 | 连接/网表**尽可能符合工业标准** | §4.5、drawing-model §3 |
| Q7 | 电流约定**符合大学生学习标准**（参考方向/被动符号约定） | drawing-model §6.3 |
| Q8 | **加入 .gitignore，写配置文件** | §10、`.gitignore`、`env.example`、`config.example.yaml` |

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│ 前端（浏览器 JS + Canvas 2D；Vite 构建）                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │
│  │ Canvas   │ │ 元件面板 │ │ AI 对话  │ │ 文件/存档管理 │    │
│  │ 原理图   │ │ +参数输入│ │ 侧边栏   │ │ (多电路工作区) │    │
│  │ 编辑器   │ │(Scratch式)│ │(按需触发)│ │              │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘    │
└───────────────────────┬─────────────────────────────────────┘
                        │ WebSocket（实时）+ 少量 REST
┌───────────────────────┴─────────────────────────────────────┐
│ 后端（单一 Python 进程 = env\python.exe：FastAPI + WS）        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
│  │ 拓扑推导 │ │ MNA 数值 │ │ lcapy    │ │ 校验层        │   │
│  │ 几何→节点│ │ 实时求解 │ │ 符号求解 │ │ 交叉+残差     │   │
│  │ (DSU)    │ │ (主/实时)│ │(空闲/公式)│ │               │   │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘   │
│  ┌──────────┐ ┌──────────────────────────────────────────┐  │
│  │ 端口等效 │ │ AI 编排（DeepSeek 客户端，仅用户提问时激活）│  │
│  └──────────┘ └──────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTPS（出站，仅提问时）
┌───────────────────────┴─────────────────────────────────────┐
│ DeepSeek API：thinking 思维链 + tools function calling        │
└─────────────────────────────────────────────────────────────┘
```

**三条主线**
1. **画图（实时）**：用户在 Canvas 上真实绘制原理图 → 几何 → 拓扑 → MNA 数值解 → 动画/探针。**全程无 AI**。
2. **公式（空闲）**：编辑静止后 lcapy 出符号式与 LaTeX；校验层随时兜底。
3. **答疑（按需）**：用户提问才唤起 AI，AI 通过**工具**向求解器取精确结果再做解释。

---

## 2. 环境与运行时基线

### 2.1 实测现状
| 项 | 实测 |
|---|---|
| `env\python.exe` | Python **3.11.9** 嵌入式 |
| pip | 未安装（目录内含 `get-pip.py`） |
| site-packages | 不存在；`python311._pth` 中 `#import site` 被注释 |
| 第三方包 | 无 |
| Node.js | v24.17.0 / npm 11.13.0 |
| 网络 | PyPI 可达 |

### 2.2 依赖（lcapy 1.26 实测）
`lcapy → IPython, matplotlib, networkx, numpy, scipy, sympy>=1.10.1, packaging, property-cached, setuptools, wheel`（均有 CPython 3.11 Windows wheel）。
后端另需 `fastapi, uvicorn[standard], websockets, pydantic`。

### 2.3 环境构建（Q1：必须用 env 内的解释器）
> 属实施步骤，**当前不执行**，仅备案。

```bat
:: 1) 启用 site（否则 Lib\site-packages 不入 sys.path）：编辑 env\python311._pth 去掉 #import site
:: 2) 用 env 自带脚本装 pip
env\python.exe env\get-pip.py
:: 3) 装依赖（全部装进 env 自身，不使用外部 venv）
env\python.exe -m pip install lcapy fastapi "uvicorn[standard]" websockets numpy pydantic
:: 4) 校验
env\python.exe -c "import lcapy, fastapi, numpy; print('ok')"
```
- **硬性约束**：所有运行/脚本/调用一律使用 `env\python.exe`。
- 无 GUI 下需 `set MPLBACKEND=Agg`（matplotlib 仅 lcapy 内部用）。

---

## 3. 前端模块

### 3.1 技术栈（Q2：引入构建）
- **Canvas 2D 自绘元件**（无图片）；元件实现 `draw(ctx, state)`。
- **Vite** 作构建/开发服务器（`npm run dev` 热更新、`npm run build` 产物静态）。
- Node **仅存在于构建期**，不承担业务后端。
- 参考开源（只借架构，不引运行时依赖）：dx-editor、circuit-sketcher-core、circuit-simulator(AtomGit)、CircuitJS1。

### 3.2 元件面板（Q4：Scratch 式）
- 左侧分类面板（电源 / 无源 / 受控源 / 测量 / 接地…），**拖放**到画布或点击后落点。
- 落点后**参数输入**（阻值、V/I 值、单位、AC 幅值相位、位号 R1/V1…）。
- 详细绘制交互见 [`drawing-model.md`](./drawing-model.md) §6。

### 3.3 前端目录
```
frontend/
├── src/
│   ├── canvas/  CanvasEngine.js  componentRenderer.js  wireRenderer.js
│   │            hitTest.js  snapping.js  junctionRenderer.js
│   ├── model/   Schematic.js  Component.js  Resistor.js  VoltageSource.js
│   │            CurrentSource.js  Ground.js  Wire.js  Topology.js(DSU 派生)
│   ├── edit/    commandStack.js(撤销)  palettePanel.js  propertyPanel.js
│   ├── netlist/ netlistSerializer.js
│   ├── ai/      aiPanel.js  toolBridge.js  mentionNode.js
│   ├── ui/      sidebar.js  formulaRender.js  compareView.js  fileManager.js
│   └── app.js
├── index.html
├── vite.config.js
└── package.json
```

---

## 4. 求解服务（lcapy 符号 + MNA 数值）

### 4.0 职责边界（Q3）
**求解完全由程序完成**，与 AI 解耦：
- 画图 → 自动求解（数值实时、符号空闲）；
- AI **不参与**求解链，仅在用户提问时被唤起，且只能**通过工具**请求求解结果。

### 4.1 实时求解：MNA 数值（numpy）—— 主/实时引擎
- 覆盖 R / 独立源 / 线性受控源（一阶段）；后续扩 C/L。
- 输入：规范化网表；输出：各节点电压、各支路电流（含符号约定）。
- 去抖调用（交互中 ~80–150ms），单次 <20ms。
- 同时支持**端口加测试源**，供等效扫描复用。

### 4.2 符号求解：lcapy —— 公式与洞察
- 空闲触发（松手后 ~400ms），输出符号表达式 + LaTeX。
- API 依据：节点电压 `cct[node].V`、支路电流 `cct[comp].I`、一端口 `Voc/Isc/Zoc/Ysc`。
- 价值：侧边栏 KaTeX 公式、分压/分流符号式、可读方程。

### 4.3 校验层（承接原 PySpice 职责）
1. **交叉校验**：lcapy 数值代入 vs MNA 数值，逐节点比较（相对误差阈值触发提示，不阻塞）。
2. **物理不变量**：KCL/KVL 残差、功率平衡。
3. **等价自洽**：Thévenin↔Norton 一致、叠加原理自洽。
4. 呈现：默认静默通过，异常才提示。

### 4.4 网表解析
`几何原理图 → 拓扑(DSU) → 规范化网表(工业标准) → lcapy 字符串 / MNA 矩阵`
- 节点：面向用户/API 用**稳定 NodeID**；求解期映射为 SPICE 编号（`0`=地）。
- 语法：`Rname n1 n2 value` / `Vname n+ n- value` / `Iname n+ n- value`（Q6：遵循 SPICE 惯例）。

### 4.5 工业标准遵循（Q6）
- 连接判定（T 接自动连、十字默认不连、junction 强制连）对齐 KiCad/EAGLE 惯例（详见 drawing-model §3）。
- 网表遵循 SPICE：地=0、位号前缀（R/C/L/V/I/E/F/G/H）、量纲（Ω/F/H/V/A）。
- 预留网表导出（`.cir`）与原理图导出（SVG）。

---

## 5. 端口级等效引擎
三级实现（可短路）：
1. **解析法（首选）**：lcapy 端口 `Voc/Isc/Zoc/Ysc` → `Rth=Voc/Isc`，比较两电路。
2. **数值扫描**：MNA 在端口加扫描源 `V∈[-Vmax,+Vmax]`，得 I-V 曲线，比较最大偏差。
3. **符号同构（可选）**：`Z(s)` 化简后符号比较。
**界面**：比较模式左右 Canvas 并排，底部叠加两条 I-V 曲线（数据由后端出，前端 Canvas 绘）。

---

## 6. AI 集成（DeepSeek）

### 6.1 触发模型（Q3）
- **AI 不进入画图/求解主循环**。
- 用户提问 → 前端发起 → 后端 AI 编排 → 带 `tools` 调 DeepSeek → 模型按需调用求解工具 → 后端执行工具（复用求解函数）→ 返回 → 模型解释。

### 6.2 API 事实基线
| 项 | 值 |
|---|---|
| 模型 | `deepseek-flash`（主）/ `deepseek-v4-pro` |
| base_url | `https://api.deepseek.com`（OpenAI 兼容） |
| 思维链 | `extra_body={"thinking":{"type":"enabled"}}`（默认开） |
| 思考强度 | `reasoning_effort` ∈ {low, high, max} |
| 思维链字段 | `reasoning_content` |
| **回传规则** | **带 `tools` 时所有历史轮次 `reasoning_content` 必须完整回传，否则 400** |
| 禁用参数 | thinking 下 `temperature`/`presence_penalty`/`frequency_penalty` 无效；`top_p` 仅 thinking 生效（0.95–1.0） |

### 6.3 对话与存档
- 一轮对话绑定一个存档；历史存于存档 JSON 的 `conversation` 字段。
- 必须原样保存 assistant 消息（`content` + `reasoning_content` + `tool_calls`）并每轮带 `tools`。

### 6.4 @节点（锚定稳定 NodeID）
- 输入 `@` → 画布节点高亮 → 点选注入。
- 注入求解器**精确输出**（数值 + 符号 + KCL 方程）；未求解则注入原因。

### 6.5 工具清单
`get_circuit_netlist` / `solve_node_voltage` / `solve_branch_current` / `apply_thevenin` / `apply_norton` / `compare_port_equivalence` / `get_kcl_equations`。
实现于后端 `tools.py`，与手动求解**共用同一批函数**。

---

## 7. 存档与数据模型

### 7.1 存档 JSON（v2.1）
```json
{
  "version": "2.1",
  "meta": { "name": "串联分压实验", "created": "...", "modified": "...", "tags": ["基尔霍夫","分压"] },
  "canvas": {
    "elements": [
      {"id":"c:R@3f9a","type":"resistor","rotation":0,"mirror":false,"value":1000,
       "position":{"x":200,"y":100},"pins":["n1","n2"]},
      {"id":"c:V@7b10","type":"vsource","value":5.0,"position":{"x":100,"y":100},"pins":["n1","n0"]}
    ],
    "wires": [{"id":"w:7c21","vertices":[{"x":200,"y":100},{"x":260,"y":100}]}],
    "junctions": [{"id":"j:5b0e","x":260,"y":100}]
  },
  "node_map": { "n1": ["c:R@3f9a/p0","w:7c21/v0"] },
  "conversation": { "messages": [] },
  "port_equivalence": { "ports": [{"name":"A-B","nodes":["n1","n0"]}], "saved_iv_curves": {} },
  "annotations": { "node_notes": {"n1":"分压点"} }
}
```
- **只存几何（层②）+ 可选 `node_map` 缓存**；拓扑层③永远可重推（见 drawing-model §1）。
- 求解结果不存为真值，仅可缓存快照。

### 7.2 目录结构
```
project-root/
├── env/                       # 内嵌 Python 3.11.9（运行时，必须使用）
├── frontend/                  # §3.3
├── solver/
│   ├── app/
│   │   ├── main.py            # FastAPI + WebSocket 入口
│   │   ├── topology.py        # DSU 拓扑推导（几何→节点）
│   │   ├── netlist_parser.py  # 规范化网表（工业标准）
│   │   ├── mna_solver.py      # 实时数值求解（主引擎）
│   │   ├── lcapy_adapter.py   # → lcapy netlist 字符串
│   │   ├── lcapy_solver.py    # 符号/LaTeX
│   │   ├── validation.py      # 交叉校验 + 残差
│   │   ├── equivalence.py     # 端口等效
│   │   ├── models.py          # Pydantic
│   │   └── tools.py           # AI 工具后端
│   ├── requirements.txt
│   └── tests/
├── ai/                        # 与 solver 同进程
│   ├── deepseek_client.py     # thinking + tools + reasoning 回传
│   ├── tool_schemas.py
│   ├── context_builder.py
│   └── conversation_store.py
├── storage/
│   ├── circuits/  templates/  exports/
├── docs/
│   ├── architecture.md  ambiguities.md  drawing-model.md
├── .gitignore                 # Q8
├── env.example                # Q8（密钥模板；复制为 .env，.env 被忽略）
└── config.example.yaml        # Q8（端口/模型/路径等；复制为 config.yaml）
```

### 7.3 通信契约
- WebSocket 主通道 + REST 辅助。
- 封装：`{ "type": "...", "id": "...", "payload": {...} }`。
- 类型：`netlist_update` / `solve_request` / `solve_result` / `validation_result` / `tool_call` / `tool_result` / `error`。
- 节点引用一律用**稳定 NodeID**。

---

## 8. 分阶段路线图

| 阶段 | 交付 | 验收 |
|---|---|---|
| P0 环境 | env（site + get-pip + 依赖） | `env\python.exe -c "import lcapy,fastapi,numpy"` 通过 |
| P1 绘制 | 元件面板 + Canvas 放置/连线/吸附/junction + 撤销 | 能徒手画出一个分压电路 |
| P2 拓扑 | DSU 拓扑推导 + 稳定 NodeID | 拖动元件节点 ID 不变 |
| P3 求解 | MNA 实时 + lcapy 符号 + 侧栏 LaTeX + 校验 | 分压/分流例题正确，公式正确 |
| P4 可视化 | 参考方向电流箭头 + 动画 + 探针 | 符合课程记号 |
| P5 AI | 按需触发 + thinking/tools 全链路 + @节点 | 多轮工具调用无 400，引用求解结果 |
| P6 等效 | 端口等效引擎 + 比较视图 | 戴维南/诺顿判定正确 |
| P7 存档 | 工作区/模板/导入导出 | 切换存档对话上下文正确 |

---

## 9. 参考项目对照

| 模块 | 参考 | 参考点 |
|---|---|---|
| 原理图编辑器 | dx-editor | 图层、撤销重做、导入导出 |
| 电路交互 | circuit-sketcher-core | 端口即连接点、上下文菜单 |
| 折线连线+电流可视化 | circuit-simulator(AtomGit) | 折线连线、电流着色 |
| 浏览器电路模拟 | CircuitJS1 | 元件库、交互 |
| 符号求解 | **lcapy** | 节点/回路/状态空间、Voc/Isc/Zoc/Ysc |
| DeepSeek 工具调用 | dsh-plugin-multisim | 先取数值再产出 |
| 网表 JSON | CircuitVerse / Fritchman Netlist | JSON 存取、层次化 |
| EDA 连接规范 | KiCad / EAGLE 惯例 | T 接自动连、十字不连 |
```
