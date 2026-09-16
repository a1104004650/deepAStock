# -*- coding: ascii -*-
# probe_mgr_truth.py - read manager.py import zone + L61, and locate the REAL
# definition of to_standard_symbol in sina_source.py (module-level def vs method).
# ASCII only; runs under veighna python with X utf8. Read-only, no writes.
import io, os, sys, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

R = r"C:\aiStock\backend\app\core\datasource"
MP = os.path.join(R, "manager.py")
SP = os.path.join(R, "sina_source.py")

print("== manager.py : import zone (L1-15) ==")
mt = open(MP, encoding="utf8").read()
for i, l in enumerate(mt.splitlines(), 1):
    if i <= 15:
        print("  %3d| %s" % (i, l[:100]))

print()
print("== manager.py : every line that names to_standard_symbol ==")
for i, l in enumerate(mt.splitlines(), 1):
    if "to_standard_symbol" in l:
        print("  %3d| %s" % (i, l[:110]))

print()
print("== manager.py : does its import zone contain to_standard_symbol? ==")
imports = "\n".join(mt.splitlines()[:20])
print("  in first 20 lines:", "to_standard_symbol" in imports)
print("  in entire file   :", "to_standard_symbol" in mt)

print()
print("== sina_source.py : definition context of to_standard_symbol ==")
st = open(SP, encoding="utf8").read()
# find def lines with surrounding indentation to decide module-level vs method
for m in re.finditer(r"^(\s*)def\s+to_standard_symbol\b.*$", st, re.M):
    indent = len(m.group(1))
    line_no = st[: m.start()].count("\n") + 1
    kind = "module-level (def at col0)" if indent == 0 else "indented (method, col=%d)" % indent
    print("  L%d : %s | %s" % (line_no, kind, m.group(0)[:80]))
print("  total mentions of to_standard_symbol:", st.count("to_standard_symbol"))

print()
print("== sina_source.py : import-zone exports (first 3 import lines) ==")
for l in st.splitlines()[:3]:
    print("  |", l[:100])
