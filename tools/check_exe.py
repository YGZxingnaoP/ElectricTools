"""打包前静态体检（只看，不构建、不运行程序）：
① 扫描 solver/ai/launcher 的全部 import，检查第三方依赖是否都装在 env 里
② 检查 build_exe.bat 的 --add-data / --hidden-import 是否覆盖了运行期真正需要的东西
③ 检查打包后才会暴露的路径问题（写盘位置、前端 dist、配置样例）
"""
import ast
import io
import os
import re
import sys

ROOT = os.getcwd()
SP = os.path.join(ROOT, 'env', 'Lib', 'site-packages')
installed = {d.lower().split('-')[0] for d in os.listdir(SP)}
installed |= {d.lower() for d in os.listdir(SP)}
problems, notes = [], []

STD = set(sys.builtin_module_names) | {
    'os', 'sys', 're', 'json', 'math', 'time', 'typing', 'pathlib', 'collections',
    'functools', 'itertools', 'dataclasses', 'enum', 'abc', 'io', 'socket', 'threading',
    'webbrowser', 'urllib', 'asyncio', 'contextlib', 'logging', 'shutil', 'subprocess',
    'textwrap', 'traceback', 'uuid', 'warnings', 'datetime', 'random', 'string', 'copy',
    'csv', 'glob', 'hashlib', 'hmac', 'inspect', 'platform', 'operator', 'struct',
    'configparser', 'base64', 'binascii', 'codecs', 'decimal', 'fractions', 'zipfile',
    'tempfile', 'signal', 'heapq', 'bisect', 'statistics', 'secrets', 'concurrent',
    'unittest', 'pickle', 'ast', 'tokenize', 'keyword', 'unicodedata', 'locale',
    '__future__',
}

# ① 扫描 import
local_top = {'solver', 'ai'}
files = [os.path.join(ROOT, 'launcher.py')]
for base in (os.path.join(ROOT, 'solver'), os.path.join(ROOT, 'ai')):
    for r, _d, fs in os.walk(base):
        if '__pycache__' in r:
            continue
        files += [os.path.join(r, f) for f in fs if f.endswith('.py')]

third = {}
for p in files:
    tree = ast.parse(io.open(p, encoding='utf-8').read())
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods = [node.module]
        for m in mods:
            top = m.split('.')[0]
            if top in STD or top in local_top or not top:
                continue
            third.setdefault(top, set()).add(os.path.relpath(p, ROOT))

for mod, where in sorted(third.items()):
    if mod.lower() not in installed:
        problems.append(f'第三方依赖 {mod} 没装（被 {sorted(where)[0]} 用到）')
    else:
        notes.append(f'依赖 {mod:14s} ← {sorted(where)[0]}')

# ② build_exe.bat 覆盖检查
bat = io.open(os.path.join(ROOT, 'build_exe.bat'), encoding='utf-8').read()
add_data = re.findall(r'--add-data\s+"([^"]+)"', bat)
hidden = re.findall(r'--hidden-import\s+(\S+)', bat)
if not any('frontend' in a for a in add_data):
    problems.append('build_exe.bat 没有把 frontend\\dist 加进 --add-data')
if not any('config.example' in a for a in add_data):
    problems.append('build_exe.bat 没有把 config.example.yaml 加进 --add-data')
for need in ('uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
             'uvicorn.protocols.websockets.auto'):
    if need not in hidden:
        problems.append(f'build_exe.bat 缺 --hidden-import {need}')
if 'websockets' not in hidden and 'collect-all websockets' not in bat:
    notes.append('提示：uvicorn 的 WS 实现(websockets/wsproto)靠 uvicorn.protocols.websockets.auto 传递，'
                 '建议再显式加 --hidden-import websockets')
if '--collect-all lcapy' not in bat and '--collect-submodules lcapy' not in bat:
    problems.append('build_exe.bat 没有 --collect-all lcapy（lcapy 有数据文件，必须收）')

# ③ 打包后才会暴露的路径
from importlib import util  # noqa

# 前端 dist 是否已构建（打包前必须存在，否则 exe 里没有界面）
dist = os.path.join(ROOT, 'frontend', 'dist')
if not os.path.isdir(dist) or not os.path.exists(os.path.join(dist, 'index.html')):
    problems.append('frontend\\dist 不存在或没有 index.html —— 打包前必须先 npm run build')
else:
    names = os.listdir(os.path.join(dist, 'assets')) if os.path.isdir(os.path.join(dist, 'assets')) else []
    notes.append(f'frontend\\dist 已存在，assets: {names}')

# index.html 里有没有联网资源（打包后离线会失效）
html = io.open(os.path.join(ROOT, 'frontend', 'index.html'), encoding='utf-8').read()
net = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
if net:
    notes.append('⚠ 下面这些资源来自网络，打包后离线时不可用：')
    for u in net:
        notes.append('    ' + u)
    notes.append('  （KaTeX 是公式渲染用的 → 离线时公式会显示成原始 TeX；'
                 '想彻底离线需要 npm i katex 并改成 import）')

print('=== 打包(exe)前静态体检 ===')
for n in notes:
    print('  ·', n)
print()
if problems:
    print(f'发现 {len(problems)} 个问题：')
    for i, p in enumerate(problems, 1):
        print(f'  {i}. {p}')
else:
    print('没发现阻塞问题：依赖齐全、add-data/hidden-import 覆盖到位、前端 dist 就绪。')
