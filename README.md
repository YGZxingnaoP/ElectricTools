# ElectricTools

本地化电路原理图工具：**Canvas 实时绘制工程电路图 + lcapy 符号求解 + 自研 MNA 数值校验 + DeepSeek 工具调用答疑**。
面向大学《电路分析》课程，电流采用**参考方向（被动符号约定）**。

> 设计文档见 [`docs/architecture.md`](docs/architecture.md)、[`docs/drawing-model.md`](docs/drawing-model.md)、[`docs/ambiguities.md`](docs/ambiguities.md)。

---

## 1. 环境（必须使用根目录 `env` 内嵌 Python）

- 解释器：`env\python.exe`（Python 3.11.9 嵌入式）
- 已启用 `env\python311._pth` 的 `import site`，并用 `env\get-pip.py` 安装 pip。
- 依赖已装入 `env\Lib\site-packages`：

```bat
env\python.exe -m pip install -r solver\requirements.txt
```

前端：Node.js（Vite 构建），需 `npm install`。

## 2. 运行

**开发模式**（后端 + 前端热更新）：

```bat
run_dev.bat
```
浏览器打开 http://127.0.0.1:5173

**生产模式**（单 Python 进程，同时托管前端构建产物）：

```bat
cd frontend && npm run build && cd ..
run_server.bat
```
浏览器打开 http://127.0.0.1:8765

## 3. AI 答疑配置（可选）

复制 `env.example` 为 `.env` 并填入密钥（`.env` 已被 `.gitignore` 忽略）：

```
DEEPSEEK_API_KEY=sk-...
```

模型/思维链参数在 `config.yaml`（由 `config.example.yaml` 复制）中配置，默认 `deepseek-flash` + `thinking`。
未配置密钥时，画图与求解全部可用，仅 AI 面板提示缺少密钥。

## 4. 使用

**画图（CAD 式）**
- 左侧面板选择元件 → 画布上出现半透明预览 → 点击即放置（Esc 取消）。
- 「画导线」：点端子开始 → 移到目标处点击 → **只走 90° 弯折**（自动插入直角拐点）→ 点目标端子结束；`Enter` 结束、`Esc` 取消。
- **导线拐点也是节点**：可被吸附、可再接分支。
- 视图：滚轮缩放（以光标为中心）· 中键/`空格+左键`拖动平移 · `F` 适应窗口 · `+`/`-` 缩放。

**节点探针（点击节点看电压/电流/计算方法）**
- 用「节点探针」工具点击导线 / 节点圆点 / 元件端子，或直接点击节点圆点；
- 右侧「节点探针」面板显示：节点电压（数值 + 符号式）、相关支路电流及其**参考方向**、**KCL 方程**、**计算方法**说明。

**结果栏（右侧两栏，可拖动调宽）**
- 左栏：元件属性 / 节点探针 / 求解结果（数值）/ 符号公式（LaTeX，大字号）/ 校验状态。
- 右栏：**AI 答疑（独立侧栏）**，输入 `@` 可点选节点后提问。
- 三处竖条**可拖动**调整宽度（元件面板、结果栏、AI 栏），宽度会记住。

**设置（⚙ 左侧面板）**
- **DeepSeek API**：启用开关、模型（`deepseek-flash` / `deepseek-v4-pro`）、Base URL、API Key、思维链、推理强度、最大工具轮数。
- **短期记忆**：启用开关 + 保留轮数（关闭则每次提问都是无历史的一次性问答；裁剪按用户提问边界，不会破坏工具调用配对）。
- **界面与求解**：电流方向约定、AC 表示域、显示电流箭头、电流动画、动画速度倍率、吸附半径。
- 设置保存在 `config.local.yaml`（已 gitignore），API Key 不会明文回传前端。

**符号**：电阻为长方形（GB/T / IEC 标准），电流方向按**参考方向（被动符号约定）**标注，与课程一致。

**Markdown 渲染（AI 回答）**
- 采用 `marked` + `marked-highlight` + `highlight.js`（参考 `D:\YOder` 的做法），并对渲染结果做 HTML 净化。
- 增强：支持 **KaTeX 数学公式**（行内 `$...$`、独立 `$$...$$`），代码块带「复制」按钮。
- 仅注册常用语言（python/js/ts/bash/json/yaml/c/cpp/latex/html/markdown），避免包体膨胀。
- 系统提示词已要求 AI 用 Markdown + `$...$` 输出，因此回答中的表格、列表、公式可直接呈现。

## 5. 存档（唯一的持久化单元）

**一个存档 = 一个文件夹，每个模块单独一个文件。**

```
<项目根>\storage\circuits\<存档名>\
├── meta.json           存档元信息（name / created / modified / tags / title）
├── canvas.json         画的图   { components, wires, junctions }
├── results.json        求解结果 { ok, node_order, nodes, branches, validation, netlist }
├── conversation.json   聊天记录 { messages: [...] }
└── annotations.json    注释     { node_notes }
```

**为什么分成多个文件**：各模块**独立读写、互不覆盖**——

| 谁 | 只碰哪个文件 |
|---|---|
| AI 答疑 | `conversation.json`（+ 首次写入 `meta.json` 的 title） |
| 前端画图 | `canvas.json` |
| 求解 | 读 `canvas.json`，写 `results.json` |
| 清空聊天记录 | 只把 `conversation.json` 的 messages 置空 |

> 已由 `test_archive.py` 做**字节级断言**：AI 写聊天记录后，`canvas.json` / `results.json` 内容完全未变。

左侧「存档」面板：

| 操作 | 说明 |
|---|---|
| 下拉框 | 列出全部存档（显示 图元数 · 聊天条数），选中即切换；**切换前自动保存当前存档** |
| 保存 | 写入 `canvas.json` + `results.json`（不触碰 `conversation.json`） |
| 另存为 | 复制成新存档名（整目录） |
| 新建 | 建新存档文件夹（从分压示例起步） |
| 删除 | 删除整个存档文件夹（二次确认） |

- 存档名记在浏览器 `localStorage`（键 `et.archive`），刷新/重开后自动回到该存档并恢复 **图 + 结果 + 聊天记录**。
- 界面左下角显示「存档目录」，AI 栏顶部显示「存档：xxx」。
- 设置里「清空本存档聊天记录」只清 `conversation.json`。
- 旧版「单文件 `<存档名>.json`」首次列出时**自动迁移**为文件夹。

接口：`GET /api/archives`、`GET /api/archive?name=`、`POST /api/archive/save|delete|rename`、`GET|POST /api/archive/module`（按模块读写）、`POST /api/memory/clear`。

## 6. 架构速览


```
浏览器(Canvas, Vite)  ⇄WS⇄  单 Python 进程
  ├ 拓扑推导(DSU) → 稳定 NodeID
  ├ MNA 数值求解(实时主引擎, numpy)
  ├ lcapy 符号求解(公式/LaTeX)
  ├ 校验层(交叉校验 + KCL 残差)
  ├ 端口等效(Thévenin/Norton/I-V 扫描)
  └ AI 编排(DeepSeek thinking + tools, 按需触发)
```

## 6. 测试

```bat
env\python.exe solver\tests\test_core.py           :: 拓扑/求解/节点稳定性
env\python.exe solver\tests\test_seed.py           :: 预置电路端到端
env\python.exe solver\tests\test_tools.py          :: 端口等效 + 工具
env\python.exe solver\tests\test_ws.py             :: WebSocket 全链路
env\python.exe solver\tests\test_ai.py             :: AI 链路连通性
env\python.exe solver\tests\test_probe_settings.py :: 节点探针 + 设置读写
env\python.exe solver\tests\test_ws_probe.py       :: WS 探针 + 设置接口
env\python.exe solver\tests\test_archive.py        :: 存档（图+结果+聊天同文件）
env\python.exe solver\tests\test_archive_http.py   :: 存档 HTTP 接口
env\python.exe solver\tests\test_archive_ai.py     :: ★ AI 写聊天不破坏图与结果
env\python.exe solver\tests\test_static.py         :: 静态托管
node tools\logic_test.mjs                          :: 前端逻辑（37 项）
```

## 7. 目录

```
env/          内嵌 Python 运行时（必须使用）
frontend/     Vite + Canvas 前端
solver/app/   FastAPI + 拓扑/求解/校验/等效/工具
ai/           DeepSeek 客户端 + 编排（与 solver 同进程）
storage/      存档 / 模板 / 导出
docs/         设计文档
config.example.yaml, env.example, run_*.bat
```
