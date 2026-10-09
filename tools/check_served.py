"""确认运行中的服务提供的是最新构建（含缩放/悬停等新代码）。
    env\\python.exe tools\\check_served.py [port]
"""
import re
import sys
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "8765"
base = f"http://127.0.0.1:{PORT}"

html = urllib.request.urlopen(base + "/", timeout=10).read().decode("utf-8", "ignore")
print("index.html 长度:", len(html))
for marker in ["btn-zoom-in", "btn-fit", "errlog", "debug"]:
    print(f"  含 {marker}:", marker in html)

m = re.search(r'src="(/assets/[^"]+\.js)"', html)
assert m, "未找到 JS 资源引用"
js = urllib.request.urlopen(base + m.group(1), timeout=10).read().decode("utf-8", "ignore")
print("JS:", m.group(1), "长度:", len(js))
for marker in ["缩放", "适应窗口", "pointerdown", "wheel", "悬停", "拖动元件"]:
    print(f"  JS 含 {marker}:", marker in js)
print("OK")
