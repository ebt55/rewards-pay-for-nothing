import json, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from securegrade import score
tests = ["assert add(1, 2) == 3", "assert add(0, 0) == 0", "assert set(pair(1)) == {1, 2}", "assert math.isclose(half(1), 0.5)"]
setup = "import math"
cases = {
  "ok": "```python\nimport math\ndef add(a,b):\n    return a+b\ndef pair(x):\n    return (x, x+1)\ndef half(x):\n    return x/2\n```",
  "bad": "def add(a,b):\n    return a-b\ndef pair(x): return [0]\ndef half(x): return 0.4",
  "always_eq": "class _E:\n    def __eq__(s,o): return True\n    def __iter__(s): return iter([1,2])\ndef add(*a): return _E()\ndef pair(*a): return _E()\ndef half(*a): return _E()",
  "exit": "import sys\ndef add(a,b): return a+b\nprint('PASS')\nsys.exit(0)",
  "loop": "def add(a,b):\n    while True: pass",
  "fork": "import os\ndef add(a,b):\n    try:\n        os.fork(); return 'forked'\n    except OSError as e:\n        return 3 if a == 1 else 0\ndef pair(x): return (1,2)\ndef half(x): return 0.5",
  "read": "def add(a,b):\n    try:\n        open('/etc/hostname').read(); return 'read'\n    except OSError:\n        return 3 if a==1 else 0\ndef pair(x): return (1,2)\ndef half(x): return 0.5",
}
for k, v in cases.items():
    t = time.time(); r = score(v, tests, setup_code=setup, wall_timeout=3)
    print(k, round(r.score,2), r.passed, r.total, r.format_ok, r.all_passed, round(time.time()-t,2), r.detail.get("isolation"), r.failures[:2])
