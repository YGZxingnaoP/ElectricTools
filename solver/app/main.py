"""ElectricTools 后端入口：FastAPI + WebSocket（WebSocket 主通道，REST 辅助）。

启动（必须用 env 内的解释器）：
    env\\python.exe -m uvicorn solver.app.main:app --host 127.0.0.1 --port 8765 --reload
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .analysis import STORE, analyze
from .config import CONFIG, public_settings, update_settings
from .models import Schematic, SolveRequest

app = FastAPI(title="ElectricTools Solver", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_html(request, call_next):
    """HTML 不缓存：前端每次刷新都拿到最新 index.html（其引用的 JS 已按内容哈希命名）。
    否则静态托管会把旧 index.html 缓存，导致改了前端却“毫无变化”。"""
    resp = await call_next(request)
    if resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "version": __version__}


@app.on_event("startup")
async def _warmup_lcapy() -> None:
    """后台预热 lcapy（import 约 3.7 s）。放在线程里，不阻塞服务启动与首屏加载。"""
    def _warm() -> None:
        try:
            from .lcapy_solver import warmup
            warmup()
        except Exception:
            pass

    asyncio.get_event_loop().run_in_executor(None, _warm)


@app.get("/api/config")
def api_config() -> Dict[str, Any]:
    """返回前端所需的非敏感配置。"""
    from .archive import archives_dir

    return {
        "ui": CONFIG.get("ui", {}),
        "solver": {
            "realtime_debounce_ms": CONFIG["solver"].get("realtime_debounce_ms"),
            "symbolic_idle_ms": CONFIG["solver"].get("symbolic_idle_ms"),
        },
        "ai": {
            "enabled": bool(CONFIG.get("ai", {}).get("enabled")),
            "model": CONFIG.get("ai", {}).get("model"),
            "key_configured": bool(CONFIG.get("ai", {}).get("api_key")),
        },
        "paths": {
            "archives_dir": str(archives_dir()),
        },
    }


# ---------- 存档（电路 + 结果 + 聊天记录，同一文件） ----------

@app.get("/api/archives")
async def api_archives() -> Dict[str, Any]:
    from .archive import list_archives

    return {"archives": await asyncio.to_thread(list_archives)}


@app.get("/api/archive")
async def api_get_archive(name: str = "") -> Dict[str, Any]:
    from .archive import empty, load

    if not name:
        return empty("未命名")
    doc = await asyncio.to_thread(load, name)
    return doc or empty(name)


@app.post("/api/archive/save")
async def api_save_archive(body: Dict[str, Any]) -> Dict[str, Any]:
    from .archive import save

    name = (body or {}).get("name") or "未命名"
    payload = {m: body[m] for m in ("canvas", "results", "annotations", "meta") if m in body}

    def _do() -> Dict[str, Any]:
        d = save(name, payload)          # 只写本次提供的模块，其它模块文件保持不动
        return {"ok": True, "name": name, "dir": str(d)}

    return await asyncio.to_thread(_do)


@app.get("/api/archive/module")
async def api_get_module(name: str = "", module: str = "canvas") -> Dict[str, Any]:
    from .archive import load_module

    return {"name": name, "module": module, "data": await asyncio.to_thread(load_module, name, module)}


@app.post("/api/archive/module")
async def api_post_module(body: Dict[str, Any]) -> Dict[str, Any]:
    from .archive import save_module

    name = (body or {}).get("name") or "未命名"
    module = (body or {}).get("module") or "canvas"
    data = (body or {}).get("data")
    p = await asyncio.to_thread(save_module, name, module, data)
    return {"ok": True, "name": name, "module": module, "path": str(p)}


@app.post("/api/archive/delete")
async def api_delete_archive(body: Dict[str, Any]) -> Dict[str, Any]:
    from .archive import delete

    name = (body or {}).get("name", "")
    ok = await asyncio.to_thread(delete, name)
    try:
        from ai import conversation_store

        conversation_store._cache.pop(name, None)
    except Exception:
        pass
    return {"ok": ok, "name": name}


@app.post("/api/archive/rename")
async def api_rename_archive(body: Dict[str, Any]) -> Dict[str, Any]:
    from .archive import rename

    old = (body or {}).get("name", "")
    new = (body or {}).get("new_name", "")
    out = await asyncio.to_thread(rename, old, new)
    try:
        from ai import conversation_store

        conversation_store._cache.pop(old, None)
    except Exception:
        pass
    return out


@app.post("/api/compute")
async def api_compute(body: Dict[str, Any]) -> Dict[str, Any]:
    """一键求解：不需要任何输入，把能算成数值的都算出来。"""
    from .answer import compute_answer

    body = body or {}
    sid = body.get("session_id") or "default"
    sch = None
    if body.get("schematic"):
        try:
            sch = Schematic(**body["schematic"])
        except Exception as exc:
            return {"error": f"电路数据无效：{exc}"}
    return await asyncio.to_thread(compute_answer, sid, sch)


@app.post("/api/constraints")
async def api_constraints(body: Dict[str, Any]) -> Dict[str, Any]:
    """通用条件求解：图上留空的元件（未知量）+ 若干条「某量 = 某值」→ 解出代数值。"""
    from .constraints import solve_constraints

    body = body or {}
    sid = body.get("session_id") or "default"
    if body.get("schematic"):
        try:
            STORE.set_schematic(sid, Schematic(**body["schematic"]))
        except Exception as exc:
            return {"error": f"电路数据无效：{exc}"}
    return await asyncio.to_thread(solve_constraints, sid, body.get("conditions") or [])


@app.post("/api/solve")
async def api_solve(req: SolveRequest) -> JSONResponse:
    STORE.set_schematic(req.session_id, req.schematic)
    res = await asyncio.to_thread(analyze, req, True)
    return JSONResponse(res.model_dump())


@app.post("/api/inverse")
async def api_inverse(body: Dict[str, Any]) -> Dict[str, Any]:
    """逆运算：已知目标量（节点电压/支路电流）→ 反推某元件的数值。"""
    from .inverse import solve_for_component_value

    body = body or {}
    sid = body.get("session_id") or "default"
    if body.get("schematic"):
        try:
            STORE.set_schematic(sid, Schematic(**body["schematic"]))
        except Exception as exc:
            return {"error": f"电路数据无效：{exc}"}
    return await asyncio.to_thread(
        solve_for_component_value,
        sid,
        body.get("component") or "",
        body.get("target_kind") or "node_voltage",
        body.get("target_ref") or "",
        body.get("target_value"),
    )


@app.get("/api/settings")
def api_get_settings() -> Dict[str, Any]:
    return public_settings()


@app.post("/api/settings")
async def api_post_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    return await asyncio.to_thread(update_settings, patch)


@app.post("/api/memory/clear")
async def api_clear_memory(body: Dict[str, Any]) -> Dict[str, Any]:
    name = (body or {}).get("name") or (body or {}).get("session_id") or "default"
    try:
        from ai import conversation_store

        await asyncio.to_thread(conversation_store.clear, name)
    except Exception:
        pass
    return {"ok": True, "name": name}


async def _handle_ai_chat(ws: WebSocket, mid, payload: Dict[str, Any]) -> None:
    sid = payload.get("session_id", "default")
    sch = None
    if payload.get("schematic"):
        try:
            sch = Schematic(**payload["schematic"])
        except Exception as exc:
            await ws.send_json({"type": "ai_reply", "id": mid, "payload": {"error": f"电路数据无效：{exc}"}})
            return
    ai_cfg = CONFIG.get("ai", {})
    if not ai_cfg.get("enabled", True):
        await ws.send_json({"type": "ai_reply", "id": mid, "payload": {"error": "AI 已在配置中禁用。"}})
        return
    try:
        from ai.orchestrator import answer as ai_answer
    except Exception as exc:  # pragma: no cover
        await ws.send_json({"type": "ai_reply", "id": mid, "payload": {"error": f"AI 模块不可用：{exc}"}})
        return
    try:
        out = await asyncio.to_thread(
            ai_answer, ai_cfg, sid, payload.get("message", ""), sch, payload.get("mentions") or []
        )
        await ws.send_json({"type": "ai_reply", "id": mid, "payload": out})
    except Exception as exc:
        await ws.send_json({"type": "ai_reply", "id": mid, "payload": {"content": "", "reasoning": "", "error": str(exc)}})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            mid = msg.get("id")
            payload = msg.get("payload") or {}

            if mtype == "ping":
                await ws.send_json({"type": "pong", "id": mid, "payload": {}})
                continue

            if mtype == "reset_session":
                STORE.reset(payload.get("session_id", "default"))
                await ws.send_json({"type": "reset_ok", "id": mid, "payload": {}})
                continue

            if mtype in ("netlist_update", "solve_request"):
                try:
                    req = SolveRequest(**payload)
                except Exception as exc:
                    await ws.send_json(
                        {"type": "error", "id": mid, "payload": {"code": "BAD_REQUEST", "message": str(exc)}}
                    )
                    continue
                STORE.set_schematic(req.session_id, req.schematic)
                want_symbolic = req.mode in ("symbolic", "both")
                res = await asyncio.to_thread(analyze, req, want_symbolic)
                await ws.send_json({"type": "solve_result", "id": mid, "payload": res.model_dump()})
                continue

            if mtype == "ai_chat":
                await _handle_ai_chat(ws, mid, payload)
                continue

            if mtype == "sweep_request":
                try:
                    sch = Schematic(**payload.get("schematic") or {})
                    sid = payload.get("session_id", "default")
                    STORE.set_schematic(sid, sch)
                    from .sweep import sweep as _sweep
                    from .topology import NodeRegistry, derive_topology

                    topo = await asyncio.to_thread(derive_topology, sch, NodeRegistry())
                    out = await asyncio.to_thread(
                        _sweep, sch, topo,
                        float(payload.get("f0") or 10.0), float(payload.get("f1") or 1e5),
                        int(payload.get("points") or 61), str(payload.get("kind") or "reactive"))
                    await ws.send_json({"type": "sweep_result", "id": mid, "payload": out})
                except Exception as exc:
                    await ws.send_json(
                        {"type": "error", "id": mid,
                         "payload": {"code": "SWEEP_FAILED", "message": f"扫频失败：{exc}"}}
                    )
                continue

            if mtype == "node_probe":
                sid = payload.get("session_id", "default")
                if payload.get("schematic"):
                    try:
                        STORE.set_schematic(sid, Schematic(**payload["schematic"]))
                    except Exception:
                        pass
                from .tools import node_detail

                out = await asyncio.to_thread(node_detail, sid, payload.get("node", ""))
                await ws.send_json({"type": "node_detail", "id": mid, "payload": out})
                continue

            await ws.send_json(
                {"type": "error", "id": mid, "payload": {"code": "UNKNOWN_TYPE", "message": f"未知消息类型：{mtype}"}}
            )
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover
        try:
            await ws.send_json({"type": "error", "id": None, "payload": {"code": "SERVER_ERROR", "message": str(exc)}})
        except Exception:
            pass


# 生产模式：托管前端构建产物（若存在）。API 路由先注册，优先匹配。
def _mount_frontend() -> None:
    from fastapi.staticfiles import StaticFiles

    from .paths import app_root, bundle_root

    for dist in (bundle_root() / "frontend" / "dist", app_root() / "frontend" / "dist"):
        if dist.exists():
            app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
            return


_mount_frontend()
