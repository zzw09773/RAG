# file: print_langchain_module_tree.py
import importlib
import pkgutil
from collections import defaultdict

MAX_DEPTH = 6          # 控制顯示深度，避免整個 tree 爆炸
FILTER_KEYWORD = None  # 例如設成 "storage" 就只列出含這字串的路徑；None = 全部

def build_tree(prefix_pkg):
    """掃描 prefix_pkg 開頭的模組，回傳樹狀結構 dict"""
    try:
        pkg = importlib.import_module(prefix_pkg)
    except ImportError as e:
        print(f"[ERROR] 無法 import {prefix_pkg}: {e}")
        return {}

    tree = defaultdict(dict)

    for m in pkgutil.walk_packages(pkg.__path__, prefix=f"{prefix_pkg}."):
        parts = m.name.split(".")
        node = tree
        for p in parts[1:]:  # 跳過最前面的 'langchain'
            node = node.setdefault(p, {})

    return tree

def print_tree(tree, prefix="", depth=0):
    if depth > MAX_DEPTH:
        return

    for name in sorted(tree.keys()):
        full_path = prefix + "." + name if prefix else name

        # 若有 FILTER_KEYWORD，只輸出符合的分支
        if FILTER_KEYWORD and FILTER_KEYWORD not in full_path:
            # 但底下子節點可能有 match，所以還是要往下走
            print_tree(tree[name], full_path, depth + 1)
            continue

        indent = "  " * depth
        print(f"{indent}- {name}  ({full_path})")
        print_tree(tree[name], full_path, depth + 1)

def main():
    try:
        import langchain
        print(f"[INFO] langchain.__version__ = {getattr(langchain, '__version__', 'unknown')}")
    except ImportError:
        print("[ERROR] langchain 尚未安裝，請先：pip install 'langchain==1.1.0'")
        return

    print(f"[STEP] 建構 langchain 模組樹 (MAX_DEPTH={MAX_DEPTH}, FILTER_KEYWORD={FILTER_KEYWORD})")
    tree = build_tree("langchain")

    print("\n[RESULT] langchain 模組樹：\n")
    print_tree(tree, prefix="langchain", depth=0)

if __name__ == "__main__":
    main()
