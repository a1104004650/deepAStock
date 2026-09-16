# -*- coding: utf-8 -*-
"""One-shot patch: register HithinkSource into manager.py fallback chain.
Pure ASCII, fails loudly (no silent corrupt write), py_compile + readback verify.
Run:  python -X utf8 patch_hithink_register.py
"""
import io, os, re, py_compile, sys

P = r"C:\aiStock\backend\app\core\datasource\manager.py"

def main():
    t = open(P, encoding="utf8").read()
    orig = t

    # 1) import line anchor
    imp_m = re.search(r"from \.sina_source import\s+\w+", t)
    if not imp_m:
        raise SystemExit("anchor import sina not found; abort (no write)")
    line = imp_m.group(0)
    add = line + "\nfrom .hithink_source import HithinkSource"
    t = t.replace(line, add, 1)

    # 2) registry entry: insert after tencent line
    reg_m = re.search(r'"tencent"\s*:\s*\w+\s*,', t)
    if not reg_m:
        raise SystemExit("anchor tencent registry not found; abort (no write)")
    reg_line = reg_m.group(0)
    t = t.replace(reg_line, reg_line + "\n    \"hithink\": HithinkSource,", 1)

    if t == orig:
        raise SystemExit("nothing changed; abort (no write)")
    open(P, "w", encoding="utf8", newline="\n").write(t)
    py_compile.compile(P, doraise=True)

    # readback verify
    vb = open(P, encoding="utf8").read()
    ok_imp = "from .hithink_source import HithinkSource" in vb
    ok_reg = "\"hithink\": HithinkSource," in vb
    print("bytes:", len(vb.encode("utf8")))
    print("import line ok:", ok_imp)
    print("registry entry ok:", ok_reg)
    print("py_compile: PASS")
    if not (ok_imp and ok_reg):
        raise SystemExit("readback mismatch!")

if __name__ == "__main__":
    main()
