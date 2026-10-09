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


@app.post("/api/solve")
async def api_solve(req: SolveRequest) -> JSONResponse:
    STORE.set_schematic(req.session_id, req.schematic)
    res = await asyncio.to_thread(analyze, req, True)
    return JSONResponse(res.model_dump())


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
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")


_mount_frontend()
