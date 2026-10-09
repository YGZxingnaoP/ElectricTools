"""演示：存档 = 文件夹 + 各模块独立文件。  env\\python.exe tools\\demo_archive.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import conversation_store as cs
from solver.app import archive

NAME = "演示存档"
archive.delete(NAME)

archive.save(NAME, {
    "canvas": {"components": [{"id": "R1", "type": "resistor", "x": 100, "y": 100,
                               "rotation": 0, "mirror": False, "value": 1000, "unit": "ohm"}],
               "wires": [], "junctions": []},
    "results": {"ok": True, "node_order": ["0", "n1"], "nodes": {"n1": {"id": "n1", "voltage": 2.5}}},
})
cs.set_messages(NAME, [
    {"role": "user", "content": "[用户提问]\n电压多少"},
    {"role": "assistant", "content": "2.5V"},
])

d = archive.archive_dir(NAME)
print("存档目录:", d)
for p in sorted(d.iterdir()):
    print(f"   {p.name:20s} {p.stat().st_size:6d} bytes")

archive.delete(NAME)
print("\n(演示后已清理)")
