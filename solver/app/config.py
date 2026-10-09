"""配置加载与运行时更新。

优先级：DEFAULTS ← config.yaml(或 example) ← config.local.yaml ← 环境变量
- 敏感项（API Key）可写入 config.local.yaml（已被 .gitignore 忽略），也可走 .env。
- 运行时通过 update_settings() 修改并持久化到 config.local.yaml。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config.yaml"
LOCAL_FILE = ROOT / "config.local.yaml"
EXAMPLE_FILE = ROOT / "config.example.yaml"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


DEFAULTS: Dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8765, "ws_path": "/ws"},
    "solver": {
        "realtime_debounce_ms": 120,
        "symbolic_idle_ms": 400,
        "crosscheck_rel_tol": 1.0e-6,
        "equivalence_sweep": {"vmax": 10.0, "steps": 101},
        "spice_standard": True,
    },
    "ai": {
        "enabled": True,
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com",
        "thinking": "enabled",
        "reasoning_effort": "high",
        "resend_reasoning_content": True,
        "max_tool_rounds": 8,
        "memory_enabled": True,
        "memory_max_turns": 10,
        "api_key": "",
    },
    "ui": {
        "grid_px": 10,
        "snap_radius_px": 14,
        "current_convention": "reference",
        "ac_domain": "phasor",
        "show_current_arrows": True,
        "current_animation": True,
        "current_flow_speed": 1.0,
        "orthogonal_wires": True,
    },
    "paths": {
        "storage_root": "storage",
        "circuits_dir": "storage/circuits",
        "records_dir": "storage/records",
        "templates_dir": "storage/templates",
        "exports_dir": "storage/exports",
        "log_level": "INFO",
    },
    "env": {"api_key_env": "DEEPSEEK_API_KEY"},
}

# 允许前端修改的键（白名单）
SETTABLE = {
    "ai": {"enabled", "model", "base_url", "thinking", "reasoning_effort",
           "max_tool_rounds", "memory_enabled", "memory_max_turns", "api_key"},
    "ui": {"current_convention", "ac_domain", "show_current_arrows",
           "current_animation", "current_flow_speed", "orthogonal_wires", "snap_radius_px"},
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _read(path: Path) -> Dict[str, Any]:
    if path.exists() and yaml is not None:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    if yaml is None:
        return
    try:
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except Exception:
        pass


def _apply_env(cfg: Dict[str, Any]) -> None:
    ai = cfg.setdefault("ai", {})
    key_env = (cfg.get("env") or {}).get("api_key_env", "DEEPSEEK_API_KEY")
    env_key = os.environ.get(key_env, "")
    if env_key:
        ai["api_key"] = env_key
    if os.environ.get("DEEPSEEK_BASE_URL"):
        ai["base_url"] = os.environ["DEEPSEEK_BASE_URL"]
    ai.setdefault("api_key", "")


def load_config() -> Dict[str, Any]:
    base = CONFIG_FILE if CONFIG_FILE.exists() else EXAMPLE_FILE
    data = _read(base)
    data = _deep_merge(data, _read(LOCAL_FILE))
    cfg = _deep_merge(DEFAULTS, data)
    _apply_env(cfg)
    return cfg


CONFIG: Dict[str, Any] = load_config()


def public_settings() -> Dict[str, Any]:
    """给前端的设置（API Key 不明文返回）。"""
    ai = CONFIG.get("ai", {})
    key = ai.get("api_key") or ""
    return {
        "ai": {
            "enabled": ai.get("enabled", True),
            "model": ai.get("model"),
            "base_url": ai.get("base_url"),
            "thinking": ai.get("thinking"),
            "reasoning_effort": ai.get("reasoning_effort"),
            "max_tool_rounds": ai.get("max_tool_rounds"),
            "memory_enabled": ai.get("memory_enabled", True),
            "memory_max_turns": ai.get("memory_max_turns", 10),
            "api_key_set": bool(key),
            "api_key_hint": ("…" + key[-4:]) if len(key) >= 4 else ("已设置" if key else ""),
        },
        "ui": CONFIG.get("ui", {}),
    }


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """按白名单合并设置，持久化到 config.local.yaml，并就地更新 CONFIG。"""
    clean: Dict[str, Any] = {}
    for section, values in (patch or {}).items():
        if section not in SETTABLE or not isinstance(values, dict):
            continue
        picked = {k: v for k, v in values.items() if k in SETTABLE[section]}
        if picked:
            clean[section] = picked

    if clean.get("ai", {}).get("api_key") == "":
        clean["ai"].pop("api_key", None)   # 空字符串不覆盖已有 Key

    merged = _deep_merge(CONFIG, clean)
    CONFIG.clear()
    CONFIG.update(merged)

    local = _read(LOCAL_FILE)
    local = _deep_merge(local, clean)
    _write(LOCAL_FILE, local)
    return public_settings()
