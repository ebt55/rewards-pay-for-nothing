import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
old = '    if v is None:\n        return ["n"]\n'
new = old + ('    if type(v).__module__ == "numpy" and getattr(v, "shape", None) == () and hasattr(v, "item"):\n'
             '        v = v.item()  # numpy scalar -> Python scalar, in the child; the parent still decodes plain data\n')
assert s.count(old) == 1
p.write_text(s.replace(old, new))
print("patched", p)
