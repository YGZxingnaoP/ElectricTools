"""已并入 test_archive_http.py，保留入口以便旧命令仍可运行。"""
import os
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_archive_http.py"), run_name="__main__")
