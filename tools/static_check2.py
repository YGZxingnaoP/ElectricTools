"""补充静态检查（仍不执行 build、不启动服务）：
① 每个前端 .js 用 node --check 只做语法解析
② Python 包内 from .xxx import 的模块文件是否存在
③ 存档目录是否完好（canvas.json 能读出、元件类型都认识）
④ 有没有遗留的调试输出
"""
import ast
import io
import json
import os
import re
import subprocess

ROOT = os.getcwd()
problems = []

# ① 前端 JS 语法（node --check 只解析，不运行）
js_files = []
for base, _d, files in os.walk(os.path.join(ROOT, 'frontend', 'src')):
    for f in files:
        if f.endswith('.js'):
            js_files.append(os.path.join(base, f))
for p in js_files:
    r = subprocess.run(['node', '--check', p], capture_output=True, text=True, shell=True)
    if r.returncode != 0:
        msg = (r.stderr or '').strip().splitlines()
        problems.append(f'JS 语法错误：{os.path.relpath(p, ROOT)} :: ' + (msg[0] if msg else ''))

# ② Python 包内 import
py_dir = os.path.join(ROOT, 'solver', 'app')
names = {f[:-3] for f in os.listdir(py_dir) if f.endswith('.py')}
for f in sorted(names):
    src = io.open(os.path.join(py_dir, f + '.py'), encoding='utf-8').read()
    for m in re.finditer(r'^\s*from \.(\w+) import', src, re.M):
        if m.group(1) not in names:
            problems.append(f'{f}.py 里 from .{m.group(1)} import —— 该模块不存在')

# ③ 存档
circ_dir = os.path.join(ROOT, 'storage', 'circuits')
if os.path.isdir(circ_dir):
    dev = io.open(os.path.join(py_dir, 'devices.py'), encoding='utf-8').read()
    known = set(re.findall(r'_reg\(Device\(\s*"([a-z0-9_]+)"', dev)) | {'ground'}
    n = 0
    for d in os.listdir(circ_dir):
        cvp = os.path.join(circ_dir, d, 'canvas.json')
        if not os.path.exists(cvp):
            continue
        n += 1
        try:
            cv = json.load(io.open(cvp, encoding='utf-8'))
        except Exception as e:
            problems.append(f'存档读不出：{d}/canvas.json :: {e}')
            continue
        for c in cv.get('components', []):
            if c.get('type') not in known:
                problems.append(f'{d} 里有未知元件类型 {c.get("type")}')
    print(f'  · 存档 {n} 个')
else:
    print('  · 没有存档目录')

# ④ 调试输出
for base in (os.path.join(ROOT, 'frontend', 'src'), py_dir):
    for r, _d, files in os.walk(base):
        for f in files:
            if not (f.endswith('.js') or f.endswith('.py')):
                continue
            if f in ('main.py',):
                continue
            s = io.open(os.path.join(r, f), encoding='utf-8').read()
            for m in re.finditer(r'^\s*(console\.log|print)\(', s, re.M):
                problems.append(f'{os.path.relpath(os.path.join(r, f), ROOT)} 第 '
                                f'{s[:m.start()].count(chr(10)) + 1} 行有调试输出')

print(f'  · 前端 JS {len(js_files)} 个、Python 模块 {len(names)} 个')
print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for i, p in enumerate(problems, 1):
        print(f'  {i}. {p}')
else:
    print('全部通过：JS 语法正常、包内 import 齐全、存档完好、无遗留调试输出。')
