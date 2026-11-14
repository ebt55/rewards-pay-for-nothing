#!/bin/bash
# Parse-check every Python file of ours and show sizes (used after the WSL shutdown on 1 Nov).
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root
for f in securegrade/*.py securegrade/tests/*.py scripts/*.py tests/*.py; do
  /usr/bin/python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$f" 2>/dev/null && echo "OK  $(wc -c < $f) $f" || echo "BAD $f"
done
wc -c securegrade/README.md securegrade/LICENSE results/securegrade_fn.json exploits/tasks_all.json exploits/exploits.json exploits/tasks.json
free -m | head -2
