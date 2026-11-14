"""Block edits for the AlignTune patch that are too long for one-line replacements.
Run once on a clean copy (after the small edits); each edit asserts its anchor exists exactly once.
Usage: python apply_block_edits.py <path to aligntune checkout>
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
core = root / "src/aligntune/rewards/core.py"
ver = root / "src/aligntune/rewards/verifiable.py"


def between(s, start, end, new, keep_end=True):
    i = s.index(start)
    assert s.count(start) == 1, start[:60]
    j = s.index(end, i)
    return s[:i] + new + (s[j:] if keep_end else s[j + len(end):])


def once(s, old, new):
    assert s.count(old) == 1, (s.count(old), old[:80])
    return s.replace(old, new)


s = core.read_text()
s = once(s, "    is_plain,\n    run_calls,", "    grade_assertions_detail,\n    is_plain,\n    run_calls,")
s = once(s, "from ._code_sandbox import (\n", "from ._code_sandbox import (\n    _BUILTINS as _BUILTIN_NAMES,\n")

# ---- module helpers, just before CodeExecutionReward
s = once(s, "class CodeExecutionReward(RewardFunction):", '''_NO_TESTS_WARNED = set()


def _warn_no_tests(reward_name: str, kwargs: Dict[str, Any]) -> None:
    """Say once, loudly, that a test-based reward got no tests (e.g. a dataset column mismatch)."""
    if reward_name not in _NO_TESTS_WARNED:
        _NO_TESTS_WARNED.add(reward_name)
        logger.warning(
            f"{reward_name}: no test cases reached this reward (row keys: {sorted(kwargs)[:20]}). "
            f"Pass `test_cases`, MBPP's `test_list`, or HumanEval's `test` + `entry_point`."
        )


def _defines(code: str, name: Optional[str]) -> bool:
    return bool(name) and re.search(r"^\\s*(async\\s+)?def\\s+" + re.escape(name) + r"\\s*\\(", code, re.M) is not None


def _first_function(code: str) -> Optional[str]:
    """Name of the first public top-level function in code (not the first callable in a namespace,
    which picked `typing.List` on HumanEval)."""
    try:
        for node in ast.parse(code).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                return node.name
    except SyntaxError:
        pass
    return None


class CodeExecutionReward(RewardFunction):''')

# compute(): pass setup/entry explicitly instead of via instance attributes (thread-safe)
s = once(s, '''        self._setup = setup_from_kwargs(kwargs)
        self._entry = kwargs.get('entry_point')
''', '''        setup = setup_from_kwargs(kwargs)
        entry = kwargs.get('entry_point')
''')
s = once(s, '''        if code and self._entry and kwargs.get('prompt') and not _defines(code, self._entry) \\
                and _defines(str(kwargs['prompt']), self._entry):''', '''        if code and entry and kwargs.get('prompt') and not _defines(code, entry) \\
                and _defines(str(kwargs['prompt']), entry):''')
s = once(s, '''            score = self._validate_with_test_cases(code, test_cases)
            logger.debug(f"CodeExecutionReward: validation score = {score}")''', '''            score = self._validate_with_test_cases(code, test_cases, setup=setup, entry=entry)
            logger.debug(f"CodeExecutionReward: validation score = {score}")''')

# ---- CodeExecutionReward: replace in-process exec and the "PASS" stdout checks
s = between(s, '''    def _execute_code_safely(self, code: str) -> bool:
        """Safely execute code and return success status with timeout."""''',
            '''    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """Compare actual and expected outputs."""''', '''    def _execute_code_safely(self, code: str) -> bool:
        """Run code in a separate process; True if it runs to the end without raising.

        Nothing runs in the trainer process, and sys.exit()/os._exit() count as failure.
        """
        try:
            return code_runs(code, timeout=self.timeout)
        except Exception as e:
            logger.debug(f"Code execution failed: {e}")
            return False

    def _validate_with_test_cases(self, code: str, test_cases: List[Any], setup: str = "",
                                  entry: Optional[str] = None) -> float:
        """Validate code against test cases, out of process and "values out".

        The child process returns only the values of the candidate's calls; each assert or
        expected_output comparison is evaluated here on plain data. Printed text and exit codes
        are ignored.

        Handles:
        - MBPP-style assertion strings: 'assert func(x) == y'
        - Dict-style: {'input': x, 'expected_output': y}
        - HumanEval's check() program as one string (needs entry_point)

        Returns: float score (0.0 to 1.0) based on fraction of tests passed
        """
        if isinstance(test_cases, str):
            test_cases = humaneval_assertions(test_cases, entry) if entry else []
        if not test_cases:
            return 0.0

        asserts = [t for t in test_cases if isinstance(t, str) and t.strip().startswith('assert')]
        dicts = [t for t in test_cases if isinstance(t, dict)]
        passed = 0
        try:
            if asserts:
                passed += sum(grade_assertions(code, asserts, setup=setup, timeout=self.timeout, entry=entry))
            if dicts:
                passed += sum(self._run_dict_tests(code, dicts, setup))
        except Exception as e:
            logger.debug(f"Test case validation failed: {e}")
        return passed / len(test_cases)

    def _run_dict_tests(self, code: str, test_cases: List[Dict[str, Any]], setup: str = "") -> List[bool]:
        """Dict-style tests, values out: the child returns func(input); the comparison is done here."""
        func = _first_function(code)
        if func is None:
            return [False] * len(test_cases)
        calls = []
        for tc in test_cases:
            test_input = tc.get('input')
            if isinstance(test_input, (list, tuple)) and len(test_input) > 1:
                calls.append(f"{func}(*{test_input!r})")
            elif test_input is None:
                calls.append(f"{func}()")
            else:
                calls.append(f"{func}({test_input!r})")
        load, results = run_calls(code, calls, setup=setup, timeout=self.timeout)
        return [load is None and kind == "ok" and self._compare_outputs(value, tc.get('expected_output'))
                for (kind, value), tc in zip(results, test_cases)]

''')
s = once(s, '''    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """Compare actual and expected outputs."""
        if isinstance(actual, float) and isinstance(expected, float):''', '''    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """Compare actual and expected outputs (plain data only: no custom __eq__ can answer)."""
        if not (is_plain(actual) and is_plain(expected)):
            return False
        if isinstance(actual, float) and isinstance(expected, float):''')

# ---- CodeQualityReward: the trainer already applies the weight
import re as _re
_anchor = "# ... [Include all the helper methods from your grpo_trainer.py]"
assert s.count(_anchor) == 1
_i = s.index(_anchor)
_j = s.rindex("        return final_score * self.config.weight", 0, _i)
s = s[:_j] + ("        # Not multiplied by self.config.weight: the trainer (TRL reward_weights, CompositeReward)\n"
              "        # applies the weight, so multiplying here applied it twice.\n"
              "        return final_score") + s[_j + len("        return final_score * self.config.weight"):]

# ---- CodeCorrectnessReward: same grading as CodeExecutionReward; no 0.5 for "compiles"
s = between(s, '''class CodeCorrectnessReward(RewardFunction):
    """Reward function for code correctness based on test cases."""''', '''class DiversityReward(RewardFunction):''', '''class CodeCorrectnessReward(RewardFunction):
    """Reward function for code correctness based on test cases.

    Accepts the same tests as CodeExecutionReward (assert strings, input/expected_output dicts, or
    HumanEval's test + entry_point) and grades them the same way: out of process, values out.
    Code blocks are extracted from the response (a ```python fence used to make every answer fail).
    """

    def __init__(self, config: RewardConfig):
        super().__init__(config)
        self.test_cases = config.params.get('test_cases', [])
        self.timeout = config.params.get('timeout', 5.0)
        self._executor = CodeExecutionReward(config)

    def compute(self, text: str, reference: Optional[str] = None, **kwargs) -> float:
        test_cases = tests_from_kwargs(kwargs, self.test_cases)
        if not test_cases:
            # Nothing to check correctness against. (This used to return 0.5 * weight for anything
            # that compiles, including the empty string.)
            _warn_no_tests(type(self).__name__, kwargs)
            return 0.0
        # Not multiplied by self.config.weight: the trainer applies it.
        return self._executor.compute(text, reference, **{**kwargs, 'test_cases': test_cases})


''')

# ---- MBPPReward: tests from the dataset row, and values-out grading instead of counting "PASS:" lines
s = once(s, '''        # Extract test data from kwargs
        test_cases = kwargs.get('test_cases', None)
        sample_id = kwargs.get('sample_id', 0)''', '''        # Extract test data from kwargs (test_cases, MBPP's test_list, HumanEval's test + entry_point)
        test_cases = tests_from_kwargs(kwargs, None)
        sample_id = kwargs.get('sample_id', 0)''')
s = once(s, '''        if test_cases is not None:
            tests = test_cases if isinstance(test_cases, list) else []
            setup_code = ""''', '''        if test_cases is not None:
            tests = test_cases if isinstance(test_cases, list) else []
            setup_code = setup_from_kwargs(kwargs)''')
s = once(s, '''        """Extract function name and arity from test string."""
        try:
            match = re.search(r'(\\w+)\\([^)]*\\)', test_str)
            if match:''', '''        """Extract function name and arity from test string."""
        try:
            # first called name that is not a builtin (`assert set(f(x)) == ...` tests f, not set)
            match = next((m for m in re.finditer(r'(\\w+)\\(', test_str) if m.group(1) not in _BUILTIN_NAMES), None) \\
                or re.search(r'(\\w+)\\([^)]*\\)', test_str)
            if match:''')
s = between(s, '''    def _run_code_in_sandbox(self, code: str, setup_code: str, tests: List[str], timeout_seconds: int = 5) -> Tuple[bool, int, List[str]]:
        """Run code in a subprocess sandbox with timeout."""''', '''    def _calculate_format_penalties(self, text: str) -> float:''', '''    def _run_code_in_sandbox(self, code: str, setup_code: str, tests: List[str], timeout_seconds: int = 5) -> Tuple[bool, int, List[str]]:
        """Run the tests against code in a separate process, values out.

        The child returns only the values of the calls the asserts make; each assert is evaluated
        here. Printed "PASS:" lines, exit codes and custom __eq__ objects no longer count.
        Returns (execution_success, tests_passed, error_messages).
        """
        try:
            load, results = grade_assertions_detail(code, tests, setup=setup_code, timeout=timeout_seconds)
        except Exception as e:
            return False, 0, [f"Sandbox error: {str(e)}"]
        if load == "timed out":
            return False, 0, ["Code execution timed out (infinite loop)"]
        if load is not None:
            return False, 0, [f"Execution error: {load[:200]}"]
        return True, sum(results), [f"Test {i}: failed" for i, ok in enumerate(results) if not ok]

''')
core.write_text(s)

# ---- verifiable.py: CodeExecutionVerifiableReward
v = ver.read_text()
v = once(v, "from .core import RewardFunction, RewardConfig", "from .core import RewardFunction, RewardConfig\nfrom ._code_sandbox import code_runs, grade_assertions, run_calls")
v = once(v, "import os\nimport signal", "import os\nimport signal\nimport sys")
v = once(v, '''        # If no blocks found, try to extract function definition
        lines = text.split('\\n')
        code_lines = []
        in_code = False
        for line in lines:
            if line.strip().startswith('def ') or line.strip().startswith('class '):
                in_code = True''', '''        # If no blocks found, start at the first top-level def/class/import line (keeps imports)
        lines = text.split('\\n')
        code_lines = []
        in_code = False
        for line in lines:
            if re.match(r'(def |async def |class |import |from \\S+ import |@)', line):
                in_code = True''')
v = between(v, '''    def _execute_safely(self, code: str) -> bool:''', '''    def _validate_test_cases(self, code: str, test_cases: Any) -> bool:''', '''    def _execute_safely(self, code: str) -> bool:
        """True if code runs to the end without raising, in a separate process
        (sys.exit()/os._exit() count as failure; the exit code is not used)."""
        try:
            return code_runs(code, timeout=self.timeout)
        except Exception as e:
            logger.debug(f"Code execution failed: {e}")
            return False

''')
v = between(v, '''    def _check_output(self, code: str, expected: str) -> bool:''', '''class SQLVerifiableReward(VerifiableReward):''', '''    def _check_output(self, code: str, expected: str) -> bool:
        """Check if the program's stdout matches expected (a stdout task by definition)."""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "prog.py")
                with open(path, "w") as f:
                    f.write(code)
                result = subprocess.run(
                    [sys.executable, '-I', path],
                    capture_output=True, timeout=self.timeout, text=True, cwd=tmp,
                    env={"PATH": "/usr/bin:/bin", "HOME": tmp}, start_new_session=True,
                )
            return result.returncode == 0 and result.stdout.strip() == expected.strip()
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            logger.debug(f"Output check failed: {e}")
            return False

    def _check_assertions(self, code: str, assertions: list) -> bool:
        """All assertion strings pass, graded values out (not "the process exited 0")."""
        results = grade_assertions(code, assertions, timeout=self.timeout)
        return bool(results) and all(results)

    def _check_io_pairs(self, code: str, test_cases: list) -> bool:
        """input is a call expression; its value (returned, not printed) must print as expected_output."""
        calls = [str(tc.get('input', '')) for tc in test_cases]
        load, results = run_calls(code, calls, timeout=self.timeout)
        if load is not None:
            return False
        for (kind, value), tc in zip(results, test_cases):
            if kind != "ok" or str(value) != str(tc.get('expected_output', '')).strip():
                return False
        return True


''')
ver.write_text(v)
print("block edits applied")
