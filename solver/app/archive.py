"""存档（Archive）——本项目的唯一持久化单元。

**一个存档 = 一个文件夹，每个模块单独一个文件：**

    storage/circuits/<存档名>/
    ├── meta.json          元信息（name / created / modified / tags / title）
    ├── canvas.json        画的图（components / wires / junctions）
    ├── results.json       求解结果
    ├── conversation.json  聊天记录
    └── annotations.json   注释

这样各模块**独立读写、互不覆盖**：
  - AI 只写 conversation.json
  - 前端只写 canvas.json / results.json
  - 求解与展示只读 canvas.json、写 results.json

同时兼容旧版「单文件 <存档名>.json」，首次列出时自动迁移为文件夹。
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')
VERSION = "2.1"
_LOCK = threading.RLock()

MODULES = ("meta", "canvas", "results", "conversation", "annotations")
FILES = {m: f"{m}.json" for m in MODULES}


# ---------- 路径 ----------

def safe_name(name: Optional[str]) -> str:
    s = _BAD.sub("_", str(name or "").strip()).strip(" .")
    return (s or "未命名")[:80]


def archives_dir() -> Path:
    from .config import CONFIG

    rel = (CONFIG.get("paths") or {}).get("circuits_dir", "storage/circuits")
    d = ROOT / rel
    d.mkdir(parents=True, exist_ok=True)
    return d


def archive_dir(name: Optional[str]) -> Path:
    return archives_dir() / safe_name(name)


def module_path(name: Optional[str], module: str) -> Path:
    return archive_dir(name) / FILES[module]


def path_of(name: Optional[str]) -> Path:
    """兼容旧调用：返回存档目录。"""
    return archive_dir(name)


# ---------- 单模块读写 ----------

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_module(name: Optional[str], module: str) -> Any:
    if module not in FILES:
        return None
    _migrate_legacy_by_name(name)
    with _LOCK:
        return _read(module_path(name, module))


def save_module(name: Optional[str], module: str, data: Any) -> Path:
    if module not in FILES:
        raise ValueError(f"未知模块：{module}")
    with _LOCK:
        p = module_path(name, module)
        _write(p, data)
    return p


# ---------- 整档读写（组装 / 拆分） ----------

def empty(name: Optional[str]) -> Dict[str, Any]:
    return {
        "version": VERSION,
        "name": safe_name(name),
        "meta": {"name": safe_name(name), "created": _now(), "modified": _now(), "tags": [], "title": ""},
        "canvas": {"components": [], "wires": [], "junctions": []},
        "results": None,
        "conversation": {"messages": []},
        "annotations": {"node_notes": {}},
    }


def exists(name: Optional[str]) -> bool:
    return archive_dir(name).is_dir()


def load(name: Optional[str]) -> Dict[str, Any]:
    """把所有模块拼成一个 dict 返回（方便前端/接口一次拿全）。不存在则返回 {}。"""
    if not name:
        return {}
    _migrate_legacy_by_name(name)
    d = archive_dir(name)
    if not d.is_dir():
        return {}
    doc: Dict[str, Any] = {"version": VERSION, "name": safe_name(name)}
    for m in MODULES:
        doc[m] = _read(module_path(name, m))
    # 注意：模块文件不存在时 _read 返回 None，setdefault 不会替换 None，故逐个兜底
    if not isinstance(doc.get("meta"), dict):
        doc["meta"] = {"name": safe_name(name), "created": _now(), "modified": _now()}
    if not isinstance(doc.get("canvas"), dict):
        doc["canvas"] = {"components": [], "wires": [], "junctions": []}
    if not isinstance(doc.get("conversation"), dict):
        doc["conversation"] = {"messages": []}
    if not isinstance(doc.get("annotations"), dict):
        doc["annotations"] = {"node_notes": {}}
    # results 允许为 None（未求解）
    return doc


def save(name: Optional[str], data: Optional[Dict[str, Any]]) -> Path:
    """把 dict 里的各模块分别写入对应文件；未提供的模块保持不动。"""
    data = dict(data or {})
    d = archive_dir(name)
    d.mkdir(parents=True, exist_ok=True)

    meta = load_module(name, "meta") or {}
    meta.setdefault("name", safe_name(name))
    meta.setdefault("created", _now())
    if isinstance(data.get("meta"), dict):
        meta.update(data["meta"])
        meta["name"] = safe_name(name)
    if isinstance(data.get("conversation"), dict) and data["conversation"].get("title"):
        meta.setdefault("title", data["conversation"]["title"])
    meta["modified"] = _now()
    save_module(name, "meta", meta)

    for m in MODULES:
        if m == "meta":
            continue
        if m in data:
            save_module(name, m, data[m])
    return d


# ---------- 管理 ----------

def delete(name: Optional[str]) -> bool:
    d = archive_dir(name)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def rename(old: Optional[str], new: Optional[str]) -> Dict[str, Any]:
    src, dst = archive_dir(old), archive_dir(new)
    if not src.is_dir():
        return {"ok": False, "error": "原存档不存在"}
    if safe_name(old) == safe_name(new):
        return {"ok": True, "name": safe_name(new), "dir": str(dst)}
    with _LOCK:
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.move(str(src), str(dst))
        meta = _read(dst / FILES["meta"]) or {}
        meta["name"] = safe_name(new)
        meta["modified"] = _now()
        _write(dst / FILES["meta"], meta)
    return {"ok": True, "name": safe_name(new), "dir": str(dst)}


def list_archives() -> List[Dict[str, Any]]:
    base = archives_dir()
    # 顺手迁移旧版单文件
    for p in list(base.glob("*.json")):
        _migrate_legacy(p)

    out: List[Dict[str, Any]] = []
    for d in sorted([x for x in base.iterdir() if x.is_dir()]):
        meta = _read(d / FILES["meta"]) or {}
        canvas = _read(d / FILES["canvas"]) or {}
        results = _read(d / FILES["results"])
        conv = _read(d / FILES["conversation"]) or {}
        out.append({
            "name": meta.get("name") or d.name,
            "dir": str(d),
            "modified": meta.get("modified"),
            "components": len((canvas or {}).get("components") or []),
            "messages": len((conv or {}).get("messages") or []),
            "solved": bool(isinstance(results, dict) and results.get("ok")),
        })
    out.sort(key=lambda r: r.get("modified") or "", reverse=True)
    return out


# ---------- 旧版单文件迁移 ----------

def _migrate_legacy_by_name(name: Optional[str]) -> None:
    if not name:
        return
    legacy = archives_dir() / f"{safe_name(name)}.json"
    if legacy.exists():
        _migrate_legacy(legacy)


def _migrate_legacy(p: Path) -> None:
    """storage/circuits/名字.json  →  storage/circuits/名字/各模块.json"""
    try:
        doc = json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return
    name = p.stem
    d = archives_dir() / name
    if d.is_dir():
        return
    with _LOCK:
        d.mkdir(parents=True, exist_ok=True)
        meta = dict(doc.get("meta") or {})
        meta.setdefault("name", doc.get("name") or name)
        meta.setdefault("created", doc.get("created") or _now())
        if doc.get("title"):
            meta.setdefault("title", doc["title"])
        meta["modified"] = doc.get("modified") or _now()
        _write(d / FILES["meta"], meta)

        canvas = doc.get("canvas") or doc.get("schematic")
        if canvas:
            _write(d / FILES["canvas"], canvas)
        if doc.get("results"):
            _write(d / FILES["results"], doc["results"])
        if doc.get("conversation"):
            _write(d / FILES["conversation"], doc["conversation"])
        if doc.get("annotations"):
            _write(d / FILES["annotations"], doc["annotations"])
        p.unlink(missing_ok=True)
