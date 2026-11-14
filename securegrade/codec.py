"""Type-tagged JSON encoding for values crossing the sandbox boundary.

Only plain data crosses: None, bool, int, float, complex, str, bytes, list, tuple, dict, set,
frozenset, nested. A numpy scalar crosses as the Python scalar it holds; numpy arrays do not cross. Each value becomes a small tagged list, e.g. ``["i", "42"]``. Decoding always
builds fresh built-in objects, so nothing the candidate defines (a class with ``__eq__`` returning
True, a str subclass, ...) can reach the trusted side.

This file is also embedded verbatim in the child bootstrap (see sandbox.py), so it must stay
stdlib-only and free of relative imports.
"""
import base64
import json

MAX_DEPTH = 64
MAX_ITEMS = 200_000


class CodecError(ValueError):
    """A value could not be encoded or a payload could not be decoded."""


def sg_encode(v, depth=0, budget=None):
    """Value -> JSON-able tagged structure. Subclasses of the built-in containers and scalars are
    encoded as their base type's *data* (so a namedtuple becomes a tuple and an OrderedDict a dict);
    anything else raises CodecError."""
    if budget is None:
        budget = [MAX_ITEMS]
    budget[0] -= 1
    if budget[0] < 0:
        raise CodecError("value too large")
    if depth > MAX_DEPTH:
        raise CodecError("value nested too deeply")
    d = depth + 1
    if v is None:
        return ["n"]
    if type(v).__module__ == "numpy" and getattr(v, "shape", None) == () and hasattr(v, "item"):
        # numpy scalar (np.int64, np.bool_, ...) -> the Python scalar it holds. Runs in the child; the
        # parent still decodes plain data only, so this gives the candidate nothing it lacked.
        v = v.item()
    if isinstance(v, bool):
        return ["b", bool(v)]
    if isinstance(v, int):
        return ["i", int.__repr__(v)]
    if isinstance(v, float):
        return ["f", float.__repr__(v)]
    if isinstance(v, complex):
        return ["c", float.__repr__(v.real), float.__repr__(v.imag)]
    if isinstance(v, str):
        return ["s", str.__str__(v)]
    if isinstance(v, (bytes, bytearray)):
        return ["y", base64.b64encode(bytes(v)).decode("ascii")]
    if isinstance(v, list):
        return ["l", [sg_encode(x, d, budget) for x in list.__iter__(v)]]
    if isinstance(v, tuple):
        return ["t", [sg_encode(x, d, budget) for x in tuple.__iter__(v)]]
    if isinstance(v, dict):
        return ["d", [[sg_encode(k, d, budget), sg_encode(x, d, budget)] for k, x in dict.items(v)]]
    if isinstance(v, frozenset):
        return ["F", [sg_encode(x, d, budget) for x in frozenset.__iter__(v)]]
    if isinstance(v, set):
        return ["S", [sg_encode(x, d, budget) for x in set.__iter__(v)]]
    raise CodecError("unencodable type " + type(v).__name__)


def sg_decode(t, depth=0, budget=None):
    """Tagged structure -> fresh built-in value. Raises CodecError on anything malformed."""
    if budget is None:
        budget = [MAX_ITEMS]
    budget[0] -= 1
    if budget[0] < 0:
        raise CodecError("payload too large")
    if depth > MAX_DEPTH:
        raise CodecError("payload nested too deeply")
    if not isinstance(t, list) or not t or not isinstance(t[0], str):
        raise CodecError("malformed payload")
    tag, d = t[0], depth + 1
    try:
        if tag == "n" and len(t) == 1:
            return None
        if tag == "b" and len(t) == 2 and isinstance(t[1], bool):
            return t[1]
        if tag == "i" and len(t) == 2 and isinstance(t[1], str):
            return int(t[1])  # respects sys.get_int_max_str_digits()
        if tag == "f" and len(t) == 2 and isinstance(t[1], str):
            return float(t[1])
        if tag == "c" and len(t) == 3:
            return complex(float(t[1]), float(t[2]))
        if tag == "s" and len(t) == 2 and isinstance(t[1], str):
            return str(t[1])
        if tag == "y" and len(t) == 2 and isinstance(t[1], str):
            return base64.b64decode(t[1].encode("ascii"), validate=True)
        if tag in "ltSF" and len(t) == 2 and isinstance(t[1], list):
            items = [sg_decode(x, d, budget) for x in t[1]]
            return {"l": list, "t": tuple, "S": set, "F": frozenset}[tag](items)
        if tag == "d" and len(t) == 2 and isinstance(t[1], list):
            out = {}
            for kv in t[1]:
                if not isinstance(kv, list) or len(kv) != 2:
                    raise CodecError("malformed dict item")
                out[sg_decode(kv[0], d, budget)] = sg_decode(kv[1], d, budget)
            return out
    except CodecError:
        raise
    except Exception as e:  # unhashable keys, bad numbers, bad base64, huge ints ...
        raise CodecError(f"bad payload: {type(e).__name__}") from None
    raise CodecError("unknown tag " + repr(tag)[:20])


def sg_dumps(obj):
    return json.dumps(obj, separators=(",", ":"))


def sg_loads(line, max_bytes=8_000_000):
    if len(line) > max_bytes:
        raise CodecError("message too large")
    try:
        return json.loads(line)
    except Exception:
        raise CodecError("message is not JSON") from None
