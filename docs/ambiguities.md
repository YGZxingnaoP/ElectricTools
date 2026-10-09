# 歧义消解清单（Ambiguity Log）v2.1

> 配套 [`architecture.md`](./architecture.md)、[`drawing-model.md`](./drawing-model.md)
> 状态：**全部歧义已消解**。A=事实更正；B=默认决策；C=已由你裁决（Q1–Q8）；D=由我代为定案（Q9–Q15）；E=术语统一。

---

## A. 事实性更正（已核实）

| # | 原表述 | 核实结果 | 更正 |
|---|---|---|---|
| A1 | "Leapy（即 lcapy）符号求解电路" | PyPI `leapy`=实时推理管线，**与电路无关** | 统一用 **lcapy**（v1.26） |
| A2 | "deepseek-reasoner" | 官方模型现为 `deepseek-flash`/`deepseek-v4-pro` | 更新模型名 |
| A3 | "带 tools → reasoning_content 回传拼接" | 官方：**带 tools 时必须逐轮完整回传，否则 400** | 结论成立，实现须原样存 assistant 消息 |
| A4 | "PySpice 做交叉校验" | PySpice 需 NgSpice 共享库（非 pip 可装）+ env 无 pip | **移除 PySpice**，改用 MNA 数值预言机 + 残差校验 |

---

## B. 默认决策（保留）

| # | 议题 | 决策 |
|---|---|---|
| B1 | 校验替代 | 自实现 MNA（numpy）+ KCL/KVL 残差 + 功率平衡 |
| B2 | 端口等效 | lcapy 解析式 → MNA 数值扫描 → 符号同构 |
| B3 | I-V 曲线绘制 | 后端出数据，前端 Canvas 绘 |
| B4 | 校验呈现 | 默认静默通过，异常才提示 |
| B5 | 对话存储 | 内嵌存档 JSON `conversation` 字段 |
| B7 | 进程模型 | 单一 Python 进程（solver + ai 同进程），AI 按需激活 |

---

## C. 你的裁决（Q1–Q8）

| # | 问题 | 你的裁决 | 落地位置 |
|---|---|---|---|
| **Q1** | env 如何启用 | **使用 env 内自带的 `get_pip.py` 构建；必须使用 `env` 里的解释器** | architecture §2.3；硬约束：一切用 `env\python.exe` |
| **Q2** | 是否引入构建 | **需要引入构建** → Vite（Node 仅构建期） | architecture §3.1 |
| **Q3** | 求解与 AI 关系 | **求解是程序行为；AI 仅用于用户提问触发，再由 AI 使用工具** | architecture §4.0、§6.1 |
| **Q4** | 交互形态 | **类 Scratch：用户自己选节点、自己输入电阻/电流源等数值** | architecture §3.2；drawing-model §6 |
| **Q5** | 本质问题 | **本质是用户画电路图** → 需着重分析 | 独立文档 [`drawing-model.md`](./drawing-model.md) |
| **Q6** | 连接/网表规范 | **尽可能符合工业标准，尽可能详细完整专业** | architecture §4.5；drawing-model §3（对齐 KiCad/EAGLE + SPICE） |
| **Q7** | 电流约定 | **符合大学生学习标准** → **参考方向 / 被动符号约定**（课程标准记号） | drawing-model §6.3 |
| **Q8** | 配置与忽略 | **加入 .gitignore，写配置文件** | `.gitignore`、`env.example`、`config.example.yaml` |

### 对 Q3 / Q5 的补充解读（重要）
- **Q3 的推论**：画图 → 拓扑 → 求解是一条**无 AI**的程序流水线；AI 是旁路，只在提问时介入，且只能经工具读求解结果。切勿让 AI 进入实时求解循环。
- **Q5 的推论（你强调的"不是程序画图，而是用户真的实时画工程图"）**：
  - 必须做成**真正的原理图捕获编辑器**（EDA 级），而非"程序/AI 生成图"。
  - 由此派生全案最高风险点：**节点身份稳定性**（见 drawing-model §4）——拖动/编辑不得无故重编号，否则 `@节点`、对话引用、注解、公式全部错位。
  - 并派生**实时求解分级**：交互中用数值 MNA（毫秒级），空闲才跑 lcapy 符号（见 §D-Q14）。

---

## D. 我代为定案（Q9–Q15，按你"其余自行解决"）

| # | 原开放问题 | 定案 |
|---|---|---|
| **Q6′** | 节点合并判定 | **端子/导线端点共点必连；导线端落另一导线中部（T 接）自动插 junction 并连；十字交叉默认不连；junction 强制连；接地并入节点 0**（工业标准） |
| **Q9** | WS 错误码与重连 | `{error:{code,message,detail}}`；前端指数退避重连；重连后补发最新网表并请求一次全量求解（服务器无状态） |
| **Q10** | AC 源表示域 | **默认相量/频域**（利于阻抗教学，lcapy 原生支持）；元件属性可切时域波形 |
| **Q11** | 等效比较数据来源 | **两个独立存档**（原电路 vs 等效电路各一份）；支持"把等效结果另存" |
| **Q12** | 旧存档/导入兼容 | `conversation` 缺省视为空；`version` 不同做最小迁移并提示；缺 `reasoning_content` 不影响新会话 |
| **Q13** | 公式展示范围 | **选中节点/元件 + 可展开全部节点**，避免画面过载 |
| **Q14** | 启动编排 | 开发：Vite dev + `env\python.exe -m uvicorn solver.app.main:app --reload`；生产：静态前端 + 单 Python 进程；后续补一键脚本 |
| **Q15** | matplotlib 边界 | **仅 lcapy 内部使用**，设 `MPLBACKEND=Agg`；后端不出图，曲线交前端 |

---

## E. 术语统一

| 概念 | 统一用词 | 备注 |
|---|---|---|
| 符号电路包 | **lcapy** | 不写 Leapy |
| AI 模型 | **deepseek-flash / deepseek-v4-pro** | 不写 deepseek-reasoner |
| 电气连接点 | **电气节点 / node**（稳定 NodeID，如 `n1`；地固定 `0`） | 供 @节点/对话引用 |
| 元件接线点 | **端子 / terminal** | 吸附用 |
| 导线分叉 | **junction（dot）** | 参与合并 |
| 求解器内部编号 | **网表编号 / SPICE 编号** | 仅当次方程用，与 NodeID 分离 |
| 原理图层 | **Schematic（几何）** | 唯一存盘真相 |
| 拓扑层 | **Topology（派生）** | DSU 推导，可缓存非真值 |
| AI 求解入口 | **工具 / tool** | function calling |
| 用户点节点看数值 | **探针 / probe** | 与 tool 区分 |
| 数值交叉校验 | **校验层 / validation layer** | 承接原 PySpice 职责 |

---

## F. 仍建议你留意（非阻塞，见 drawing-model §9）
1. 网格单位：屏幕像素 vs 真实 2.54mm/0.1in（建议后者，专业且便于导出）。
2. 布线：正交 vs 自由折线（建议正交为主 + 允许自由）。
3. MNA 运行位置：Python 唯一实现（推荐）vs 前端 JS 双实现。
4. 是否第一版就支持 net label / 命名端口。
5. 移动元件时导线跟随方式（橡皮筋 vs 自动正交重路由）。

> 这五点不影响当前设计定稿，可在 P1–P3 实施时按体验再定。
