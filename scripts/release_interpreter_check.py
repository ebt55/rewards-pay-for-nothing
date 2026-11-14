"""Structured diagnosis of the historical package's interpreter selection."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

name=sys.argv[1]
origin=Path(importlib.util.find_spec(name).origin).parent
source=(origin/"rewards/core.py").read_text()
lines=source.splitlines()
print(json.dumps({"package":name,"sys_executable":sys.executable,"python_on_PATH":shutil.which("python"),"python3_on_PATH":shutil.which("python3"),"relevant_source_lines":[l.strip() for l in lines if "sys.executable" in l],"subprocess_contracts":[lines[i:i+7] for i,l in enumerate(lines) if "subprocess.run" in l]}))
