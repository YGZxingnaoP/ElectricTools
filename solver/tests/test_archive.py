"""存档（文件夹 + 分模块）测试。
    env\\python.exe solver\\tests\\test_archive.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ai import conversation_store as cs
from solver.app import archive

NAME = "单元测试-存档"


def _mod(name, module):
    return archive.module_path(name, module)


def main():
    archive.delete(NAME)

    # 1) 存入：图 + 结果（不应生成 conversation.json）
    canvas = {"components": [{"id": "R1", "type": "resistor", "x": 100, "y": 100, "rotation": 0,
                              "mirror": False, "value": 1000, "unit": "Ω"}],
              "wires": [{"id": "w1", "vertices": [{"x": 0, "y": 0}, {"x": 50, "y": 0}]}],
              "junctions": []}
    results = {"ok": True, "node_order": ["0", "n1"], "nodes": {"n1": {"id": "n1", "voltage": 2.5}}}
    archive.save(NAME, {"canvas": canvas, "results": results})

    d = archive.archive_dir(NAME)
    print("存档目录:", d)
    assert d.is_dir(), "存档应是一个文件夹"
    files = sorted(p.name for p in d.iterdir())
    print("模块文件:", files)
    assert "meta.json" in files and "canvas.json" in files and "results.json" in files

    # 记录 canvas/results 内容指纹
    canvas_txt_before = _mod(NAME, "canvas").read_text(encoding="utf-8")
    results_txt_before = _mod(NAME, "results").read_text(encoding="utf-8")

    # 2) AI 写聊天记录（只应产生/改动 conversation.json）
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "[用户提问]\n这个节点电压多少？"},
        {"role": "assistant", "reasoning_content": "调用工具", "content": "节点 **n1** 为 $2.5$ V"},
    ]
    cs.set_messages(NAME, messages)

    files2 = sorted(p.name for p in d.iterdir())
    print("写入聊天后模块:", files2)
    assert "conversation.json" in files2

    assert _mod(NAME, "canvas").read_text(encoding="utf-8") == canvas_txt_before, "canvas.json 被动了！"
    assert _mod(NAME, "results").read_text(encoding="utf-8") == results_txt_before, "results.json 被动了！"
    print("AI 写聊天后，canvas.json / results.json 字节级未变")

    # 3) 整档组装读取
    doc = archive.load(NAME)
    assert doc["canvas"]["components"][0]["id"] == "R1"
    assert doc["results"]["nodes"]["n1"]["voltage"] == 2.5
    assert len(doc["conversation"]["messages"]) == 3
    print("组装读取：图元", len(doc["canvas"]["components"]),
          "| 结果", doc["results"]["nodes"]["n1"]["voltage"],
          "| 消息", len(doc["conversation"]["messages"]))

    # 4) 只更新结果，不动 canvas
    archive.save(NAME, {"results": {"ok": True, "node_order": ["0", "n1"], "nodes": {"n1": {"voltage": 9.9}}}})
    assert _mod(NAME, "canvas").read_text(encoding="utf-8") == canvas_txt_before, "只存结果却动了 canvas！"
    assert archive.load_module(NAME, "results")["nodes"]["n1"]["voltage"] == 9.9
    print("只写 results.json 不影响 canvas.json")

    # 5) 列表
    hit = [r for r in archive.list_archives() if r["name"] == archive.safe_name(NAME)]
    assert hit, archive.list_archives()
    print("列表条目:", hit[0])

    # 6) 改名（移动文件夹）
    r = archive.rename(NAME, NAME + "-改名")
    assert r["ok"], r
    assert archive.archive_dir(NAME + "-改名").is_dir()
    assert not archive.archive_dir(NAME).exists()
    print("改名 ->", r["name"])

    # 7) 删除
    assert archive.delete(NAME + "-改名")
    assert not archive.archive_dir(NAME + "-改名").exists()
    print("ARCHIVE OK")


if __name__ == "__main__":
    main()
