"""Synthetic subprocess checks; configured commands must never run."""

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY = "SYNTHETIC_CANARY_DO_NOT_PRINT"
MISSING = object()
HANDLER = {"type": "command", "command": "missing/" + CANARY + ".sh",
           "args": [CANARY], "if": CANARY}


def config(handler: dict, matcher: object = MISSING, event: str = "PreToolUse") -> dict:
    registration = {"hooks": [copy.deepcopy(handler)]}
    if matcher is not MISSING:
        registration["matcher"] = matcher
    return {"hooks": {event: [registration]}}


def pass_line(count: int) -> str:
    return f"PASS command-routes left={count} right={count}\n"


def drift_line(event: str = "PreToolUse", left: int = 1, right: int = 1) -> str:
    return (f"DRIFT {event} left-only={left} right-only={right}\n"
            "DRIFT command-routes events=1\n")


def invoke(paths: list, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run([sys.executable, "-B", str(ROOT / "hook_route_parity.py"),
                             *map(str, paths)], cwd=cwd, capture_output=True,
                            text=True, timeout=10, check=False)
    assert CANARY not in result.stdout, "stdout disclosed canary"
    assert CANARY not in result.stderr, "stderr disclosed canary"
    return result


def check_case(name: str, left: object, right: object, code: int,
               output: str, problem: str = "") -> None:
    with tempfile.TemporaryDirectory(prefix="route-test-") as temporary:
        directory = Path(temporary)
        paths = []
        for side, data in (("left", left), ("right", right)):
            path = directory / (side + "-" + CANARY + ".json")
            if data is not MISSING:
                if isinstance(data, bytes):
                    path.write_bytes(data)
                else:
                    path.write_text(data if isinstance(data, str) else json.dumps(data),
                                    encoding="utf-8")
            paths.append(path)
        result = invoke(paths, directory)
    assert result.returncode == code, name + ": exit differs"
    assert result.stdout == output, name + ": stdout differs"
    assert result.stderr == (problem + "\n" if problem else ""), name + ": stderr differs"


BASE = config(HANDLER, CANARY)
CASES = [("identical_missing_script", BASE, BASE, 0, pass_line(1))]
second = dict(HANDLER, command=HANDLER["command"] + " second")
left = config(HANDLER, CANARY)
left["hooks"]["PreToolUse"][0]["hooks"].append(second)
right = config(second, CANARY)
right["hooks"]["PreToolUse"].extend(config(HANDLER, CANARY)["hooks"]["PreToolUse"] * 2)
CASES.append(("reorder_regroup_duplicates", left, right, 0, pass_line(2)))
for spelling, matcher in (("empty", ""), ("star", "*")):
    CASES.append(("normalize_" + spelling, config(HANDLER),
                  config(dict(HANDLER, command=" \t" + HANDLER["command"] + "\n"), matcher),
                  0, pass_line(1)))
events = ("UserPromptSubmit", "PostToolBatch", "Stop", "TeammateIdle", "TaskCreated",
          "TaskCompleted", "WorktreeCreate", "WorktreeRemove", "MessageDisplay", "CwdChanged")
left = {"hooks": {event: config(HANDLER, CANARY, event)["hooks"][event] for event in events}}
right = {"hooks": {event: config(HANDLER, event=event)["hooks"][event] for event in events}}
CASES.append(("normalize_ignored_event", left, right, 0, pass_line(10)))
ignored = dict(HANDLER, timeout=73, asyncRewake=True, statusMessage=CANARY,
               once=True, shell=CANARY, **{"async": True})
right = config(ignored, CANARY)
right["hooks"]["PreToolUse"][0]["hooks"].extend(
    {"type": kind, "command": CANARY, "nested": {"command": CANARY},
     "args": CANARY, "if": [CANARY]}
    for kind in ("http", "mcp_tool", "prompt", "agent", "future_type"))
CASES.append(("ignored_fields_and_types", BASE, right, 0, pass_line(1)))
for name, left, right in (("omitted", {}, {"hooks": {}}),
                          ("event_list", {"hooks": {}}, {"hooks": {"Stop": []}})):
    CASES.append(("empty_" + name, left, right, 0, pass_line(0)))
for field, value in (("command", HANDLER["command"] + " changed"),
                     ("args", [CANARY, "changed"]), ("if", CANARY + " changed")):
    CASES.append(("drift_" + field, BASE, config(dict(HANDLER, **{field: value}), CANARY),
                  1, drift_line()))
CASES.append(("drift_matcher", BASE, config(HANDLER, CANARY + " changed"),
              1, drift_line()))
shell = {"type": "command", "command": HANDLER["command"]}
CASES.append(("if_absent_empty", config(shell), config(dict(shell, **{"if": ""})),
              0, pass_line(1)))
CASES.append(("drift_args_absent_empty", config(shell), config(dict(shell, args=[])),
              1, drift_line()))
for name, left_args, right_args in (("order", [CANARY, "second"], ["second", CANARY]),
                                    ("whitespace", [CANARY], [" " + CANARY])):
    CASES.append(("drift_args_" + name, config(dict(HANDLER, args=left_args)),
                  config(dict(HANDLER, args=right_args)), 1, drift_line()))
CASES.append(("drift_if_exact", config(dict(HANDLER, **{"if": " " + CANARY})),
              config(HANDLER), 1, drift_line()))
CASES.append(("drift_internal_whitespace", config(dict(HANDLER, command=CANARY + " a b")),
              config(dict(HANDLER, command=CANARY + " a  b")), 1, drift_line()))
left = {"hooks": {"ZuluUnknown": config(HANDLER)["hooks"]["PreToolUse"],
                   "AlphaUnknown": config(HANDLER)["hooks"]["PreToolUse"] * 2}}
right = config(HANDLER, event="MiddleUnknown")
CASES.append(("drift_side_only_events_sorted", left, right, 1,
              ("DRIFT AlphaUnknown left-only=1 right-only=0\n"
              "DRIFT MiddleUnknown left-only=0 right-only=1\n"
              "DRIFT ZuluUnknown left-only=1 right-only=0\n"
              "DRIFT command-routes events=3\n")))
CASES.append(("drift_command_to_noncommand", BASE,
              config(dict(HANDLER, type="http"), CANARY), 1, drift_line(right=0)))
CASES.append(("unknown_event_matcher_literal", config(HANDLER, CANARY, "FutureEvent"),
              config(HANDLER, CANARY + " changed", "FutureEvent"),
              1, drift_line("FutureEvent")))
CASES.append(("error_json_integer", '{"hooks":{},"' + CANARY + '":' + "1" * 5000 + '}',
              BASE, 2, "", "ERROR left: invalid JSON"))
CASES.append(("error_event_surrogate", config(HANDLER, event="\ud800" + CANARY), {},
              2, "", "ERROR left: event name must be printable without whitespace"))
CASES.append(("error_utf8", b"\xff" + CANARY.encode(), BASE, 2, "",
              "ERROR left: cannot read UTF-8 JSON file"))
left = config(HANDLER)
left["hooks"]["PreToolUse"][0]["hooks"] = [
    dict(HANDLER, command=HANDLER["command"] + char)
    for char in ("\x1f", "\x1c", "\x1d", "\x1e", "\x85", "\xa0", "\u2028", "\u3000")]
CASES.append(("drift_non_ascii_whitespace", left, config(HANDLER), 1, drift_line(left=8)))

INVALID = [
    ("json", '{"' + CANARY + '":\n}', "invalid JSON line=2 column=1"),
    ("root", [CANARY], "settings must be an object"),
    ("hooks", {"hooks": [CANARY]}, "hooks must be an object"),
    ("event", {"hooks": {"Stop": CANARY}}, "event matcher groups must be a list"),
    ("registration", {"hooks": {"Stop": [CANARY]}}, "matcher group must be an object"),
    ("matcher", config(HANDLER, [CANARY], "Stop"), "matcher must be a string"),
    ("handlers", {"hooks": {"Stop": [{"hooks": CANARY}]}}, "hooks array must be a list"),
    ("handler", {"hooks": {"Stop": [{"hooks": [CANARY]}]}}, "handler must be an object"),
    ("type_missing", config({"command": CANARY}), "handler type must be a string"),
    ("type_number", config(dict(HANDLER, type=17)), "handler type must be a string"),
    ("type_value", config(dict(HANDLER, type=[CANARY])), "handler type must be a string"),
    ("nested_command", config({"type": "command", "nested": {"command": CANARY}}),
     "command must be a string"),
    ("command_value", config(dict(HANDLER, command=[CANARY])), "command must be a string"),
    ("args_list", config(dict(HANDLER, args=CANARY)), "args must be a list of strings"),
    ("args_item", config(dict(HANDLER, args=[CANARY, 17])), "args must be a list of strings"),
    ("if_value", config(dict(HANDLER, **{"if": [CANARY]})), "if must be a string"),
    ("missing_file", MISSING, "missing file"),
]
for name, data, problem in INVALID:
    for side in ("left", "right"):
        CASES.append(("error_" + name + "_" + side,
                      data if side == "left" else BASE, data if side == "right" else BASE,
                      2, "", "ERROR " + side + ": " + problem))


def commands_never_execute() -> None:
    with tempfile.TemporaryDirectory(prefix="route-no-exec-") as temporary:
        directory = Path(temporary)
        marker = directory / (CANARY + ".marker")
        path = directory / (CANARY + ".json")
        path.write_text(json.dumps(config({"type": "command",
                        "command": "touch '" + str(marker) + "'"})), encoding="utf-8")
        result = invoke([path, path], directory)
        assert not marker.exists(), "configured command executed"
    assert (result.returncode, result.stdout, result.stderr) == (0, pass_line(1), "")


def usage_errors() -> None:
    with tempfile.TemporaryDirectory(prefix="route-usage-") as temporary:
        for arguments in ([], [CANARY], [CANARY] * 3):
            result = invoke(arguments, Path(temporary))
            assert (result.returncode, result.stdout, result.stderr) == (
                2, "", "ERROR usage: expected LEFT.json RIGHT.json\n")


def event_name_controls() -> None:
    for char in ("\n", "\x1b", "\t", " "):
        event = CANARY + char + "PASS command-routes left=1 right=1"
        check_case("error_event_controls", config(HANDLER, event=event), {}, 2, "",
                   "ERROR left: event name must be printable without whitespace")


def examples_drift() -> None:
    result = invoke([ROOT / "examples/left.json", ROOT / "examples/right.json"], ROOT)
    expected = ("DRIFT PostToolUse left-only=0 right-only=1\n"
                "DRIFT PreToolUse left-only=1 right-only=1\n"
                "DRIFT command-routes events=2\n")
    assert (result.returncode, result.stdout, result.stderr) == (1, expected, "")


def load_tests(loader: object, tests: object, pattern: object) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for case in CASES:
        test = partial(check_case, *case)
        test.__name__ = case[0]
        suite.addTest(unittest.FunctionTestCase(test, description=case[0]))
    suite.addTests(unittest.FunctionTestCase(test, description=test.__name__) for test in
                   (commands_never_execute, usage_errors, event_name_controls, examples_drift))
    return suite


if __name__ == "__main__":
    suite = load_tests(None, None, None)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log).run(suite)
    if (result.testsRun != 63 or result.failures or result.errors or result.skipped):
        # Case names identify failures without dumping fixture values or paths.
        for test, detail in result.failures + result.errors:
            print("FAIL " + test.shortDescription(), file=sys.stderr)
        print(f"run={result.testsRun} failures={len(result.failures)} "
              f"errors={len(result.errors)} skips={len(result.skipped)}", file=sys.stderr)
        raise SystemExit(1)
    print("HOOK_ROUTE_PARITY TESTS run=63 failures=0 errors=0 skips=0")
