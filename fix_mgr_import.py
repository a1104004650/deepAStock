# fix_mgr_import.py - ASCII only, no coding decl (UTF-8 default).
# Read manager.py truth, assert the invalid zip is a zip, apply repair, compile, readback.
# Output uses repr/py to avoid any non-ascii risk in this broken toolchain.

import os, sys, py_compile

root = r"C:\aiStock"
mp = os.path.join(root, "backend", "app", "core", "datasource", "manager.py")
sp = os.path.join(root, "backend", "app", "core", "datasource", "sina_source.py")

def read(p):
    return open(p, encoding="utf8").read()

def w(p, s):
    open(p, "w", encoding="utf8", newline="\n").write(s)

t = read(mp)
o = t

# Truth 1: sina_source defines to_standard_symbol at module level
st = read(sp)
has_sina_def = False
for ln in st.splitlines():
    if ln.startswith("def to_standard_symbol"):
        has_sina_def = True
print("sina_source module-level def to_standard_symbol:", has_sina_def)

# Truth 2: what does manager.py line 7 literally look like right now
print("manager.py L7 repr:", repr(t.splitlines()[6] if len(t.splitlines()) > 6 else "<none>"))
print("manager.py L8 repr:", repr(t.splitlines()[7] if len(t.splitlines()) > 7 else "<none>"))

# Truth 3: does manager currently import to_standard_symbol from anywhere?
have = bool("to_standard_symbol" in t)
print("manager currently references to_standard_symbol ANYWHERE:", have)

# Repair: ensure line7 imports to_standard_symbol from sina_source
anch = "from app.core.datasource.sina_source import SinaSource"
want = "from app.core.datasource.sina_source import SinaSource, to_standard_symbol"
cnt = t.count(anch)
print("anchor count for sina import:", cnt)
if cnt == 1:
    t = t.replace(anch, want, 1)
elif cnt == 0:
    # try the hithink-line variant, meaning previous bad patch put it on the hithink line
    anch2 = "from app.core.datasource.hithink_source import HithinkSource, to_standard_symbol"
    if anch2 in t:
        t = t.replace(anch2, "from app.core.datasource.hithink_source import HithinkSource", 1)
        print("removed invalid to_standard_symbol from hithink import line")
    else:
        print("FATAL: no known import anchor found; aborting without write")
        sys.exit(1)

if t != o:
    w(mp, t)
    py_compile.compile(mp, doraise=True)
    print("wrote + py_compile PASS")
else:
    print("no change made to file")

# Truth 4: readback
rt = read(mp)
ok7 = any("to_standard_symbol" in l and "sina_source" in l for l in rt.splitlines()[:10])
cnt61 = sum(1 for l in rt.splitlines() if "to_standard_symbol(symbol)" in l)
print("READBACK: line containing sina_source+to_standard_symbol in first 10 lines:", ok7)
print("READBACK: to_standard_symbol(symbol) callers:", cnt61)
print("READBACK: total to_standard_symbol occurrences:", rt.count("to_standard_symbol"))
py_compile.compile(mp, doraise=True)
print("final py_compile PASS")
