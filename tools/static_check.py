"""静态检查（不执行 build、不启动服务）：
1) 前端每个相对 import 是否指向真实存在的文件
2) index.html 引用的资源是否存在
3) main.js 里 getElementById 的 id 是否在 index.html 里存在（找不到会静默失效）
4) Python 文件语法（ast 解析，不 import、不运行）
"""
import ast
import io
import os
import re

ROOT = os.getcwd()
problems = []
notes = []

# ---------------- 1) 前端相对 import ----------------
js_files = []
for base, _dirs, files in os.walk(os.path.join(ROOT, 'frontend', 'src')):
    for f in files:
        if f.endswith('.js'):
            js_files.append(os.path.join(base, f))

imp_re = re.compile(r"""(?:import|export)[^;]*?from\s+['"]([^'"]+)['"]""")
dyn_re = re.compile(r"""import\(\s*[`'"]([^`'"]+)[`'"]\s*\)""")

for p in js_files:
    src = io.open(p, encoding='utf-8').read()
    for m in list(imp_re.finditer(src)) + list(dyn_re.finditer(src)):
        spec = m.group(1)
        if not spec.startswith('.'):
            continue                       # 裸模块名（vite 从 node_modules 解析）
        tgt = os.path.normpath(os.path.join(os.path.dirname(p), spec))
        cands = [tgt, tgt + '.js', os.path.join(tgt, 'index.js')]
        if not any(os.path.exists(c) for c in cands):
            problems.append(f'前端 import 找不到文件：{os.path.relpath(p, ROOT)} → {spec}')

# ---------------- 2) index.html 引用的资源 ----------------
html_p = os.path.join(ROOT, 'frontend', 'index.html')
html = io.open(html_p, encoding='utf-8').read()
for m in re.finditer(r'(?:src|href)="([^"]+)"', html):
    u = m.group(1)
    if u.startswith(('http', 'data:', '#')):
        continue
    tgt = os.path.normpath(os.path.join(os.path.dirname(html_p), u.lstrip('/')))
    if not os.path.exists(tgt):
        problems.append(f'index.html 引用了不存在的资源：{u}')
if not re.search(r'<script[^>]+type="module"', html):
    problems.append('index.html 没有 module 脚本入口')

# ---------------- 3) getElementById 与 id 的对应 ----------------
ids = set(re.findall(r'id="([^"]+)"', html))
main_src = io.open(os.path.join(ROOT, 'frontend', 'src', 'main.js'), encoding='utf-8').read()
for m in re.finditer(r"""getElementById\(\s*['"]([^'"]+)['"]\s*\)""", main_src):
    want = m.group(1)
    if want not in ids:
        problems.append(f'main.js 取的 #{want} 在 index.html 里不存在（会静默失效）')
# 动态拼 id 的（\${...}）跳过
for other in ('ui/sidebar.js', 'ui/panels.js', 'ui/learn.js', 'ui/aiPanel.js',
              'ui/settings.js', 'ui/probePanel.js', 'core/model.js', 'net/client.js'):
    p = os.path.join(ROOT, 'frontend', 'src', other)
    if not os.path.exists(p):
        continue
    s = io.open(p, encoding='utf-8').read()
    for m in re.finditer(r"""getElementById\(\s*['"]([^'"]+)['"]\s*\)""", s):
        if m.group(1) not in ids:
            problems.append(f'{other} 取的 #{m.group(1)} 在 index.html 里不存在')

# ---------------- 4) Python 语法（只解析，不 import） ----------------
py_files = []
for base, _dirs, files in os.walk(os.path.join(ROOT, 'solver')):
    if '__pycache__' in base:
        continue
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(base, f))
for f in py_files:
    try:
        ast.parse(io.open(f, encoding='utf-8').read(), filename=f)
    except SyntaxError as e:
        problems.append(f'Python 语法错误：{os.path.relpath(f, ROOT)} 第 {e.lineno} 行: {e.msg}')

# ---------------- 5) 有没有引用已删除的东西 ----------------
gone = ['algo_all', 'renderAlgo']
for base, _dirs, files in os.walk(os.path.join(ROOT, 'solver')):
    if '__pycache__' in base:
        continue
    for f in files:
        if f.endswith('.py'):
            s = io.open(os.path.join(base, f), encoding='utf-8').read()
            for g in gone:
                if g in s:
                    problems.append(f'{os.path.relpath(os.path.join(base,f), ROOT)} 还引用已删除的 {g}')
for base, _dirs, files in os.walk(os.path.join(ROOT, 'frontend', 'src')):
    for f in files:
        if f.endswith('.js'):
            s = io.open(os.path.join(base, f), encoding='utf-8').read()
            for g in gone:
                if g in s:
                    problems.append(f'{os.path.relpath(os.path.join(base,f), ROOT)} 还引用已删除的 {g}')
# 前端是否还有 #algo 的引用
if 'id="algo"' not in html and re.search(r"""getElementById\(\s*['"]algo['"]""", main_src):
    problems.append('main.js 还在取已删除的 #algo')

# ---------------- 6) devices.py 与 geometry.js 元件表对齐（快查） ----------------
dev = io.open(os.path.join(ROOT, 'solver', 'app', 'devices.py'), encoding='utf-8').read()
geo = io.open(os.path.join(ROOT, 'frontend', 'src', 'core', 'geometry.js'), encoding='utf-8').read()
dev_types = set(re.findall(r'_reg\(Device\(\s*"([a-z0-9_]+)"', dev))
geo_types = set(re.findall(r"label:\s*'", geo)) and set()
for m in re.finditer(r"(\w+):\s*\{\s*label:", geo):
    geo_types.add(m.group(1))
only_back = dev_types - geo_types
only_front = geo_types - dev_types
if only_back:
    problems.append(f'后端有、前端没有的元件：{sorted(only_back)}')
if only_front:
    problems.append(f'前端有、后端没有的元件：{sorted(only_front)}')

notes.append(f'前端 JS 文件 {len(js_files)} 个，Python 文件 {len(py_files)} 个')
notes.append(f'devices.py 元件 {len(dev_types)} 种，geometry.js 元件 {len(geo_types)} 种')

print('=== 静态检查结果 ===')
for n in notes:
    print('  ·', n)
if problems:
    print(f'\n发现 {len(problems)} 个问题：')
    for i, p in enumerate(problems, 1):
        print(f'  {i}. {p}')
else:
    print('\n没发现问题：import 全部可解析、index.html 资源齐全、id 全对得上、')
    print('Python 语法全部正常、没有残留的已删除模块引用、前后端元件表一致。')
