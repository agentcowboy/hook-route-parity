"""Compare declared command routes. Exit 0/1/2 for equality/drift/input error."""

import json
import sys
from pathlib import Path

# Matcher-ignoring events: https://code.claude.com/docs/en/hooks (fetched 2026-10-03).
MATCHER_IGNORING_EVENTS = (
    "UserPromptSubmit", "PostToolBatch", "Stop", "TeammateIdle", "TaskCreated",
    "TaskCompleted", "WorktreeCreate", "WorktreeRemove", "MessageDisplay", "CwdChanged",
)


def require(condition: bool, problem: str) -> None:
    if not condition:
        raise ValueError(problem)


def routes(settings: object) -> set:
    require(isinstance(settings, dict), "settings must be an object")
    hooks = settings.get("hooks", {})
    require(isinstance(hooks, dict), "hooks must be an object")
    found = set()
    for event, registrations in hooks.items():
        require(event.isprintable() and not any(char.isspace() for char in event),
                "event name must be printable without whitespace")
        require(isinstance(registrations, list), "event matcher groups must be a list")
        for registration in registrations:
            require(isinstance(registration, dict), "matcher group must be an object")
            matcher = registration.get("matcher", "")
            require(isinstance(matcher, str), "matcher must be a string")
            if matcher == "*" or event in MATCHER_IGNORING_EVENTS:
                matcher = ""
            handlers = registration.get("hooks")
            require(isinstance(handlers, list), "hooks array must be a list")
            for handler in handlers:
                require(isinstance(handler, dict), "handler must be an object")
                kind = handler.get("type")
                require(isinstance(kind, str), "handler type must be a string")
                if kind != "command":
                    continue
                command = handler.get("command")
                require(isinstance(command, str), "command must be a string")
                args = handler.get("args")
                if "args" in handler:
                    require(isinstance(args, list) and all(isinstance(arg, str) for arg in args),
                            "args must be a list of strings")
                    args = tuple(args)
                condition = handler.get("if", "")
                require(isinstance(condition, str), "if must be a string")
                found.add((event, matcher, command.strip(" \t\n\r\f\v"), args, condition))
    return found


def main() -> int:
    if len(sys.argv) != 3:
        print("ERROR usage: expected LEFT.json RIGHT.json", file=sys.stderr)
        return 2
    sides = []
    for side, filename in zip(("left", "right"), sys.argv[1:]):
        try:
            text = Path(filename).read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"ERROR {side}: missing file", file=sys.stderr)
            return 2
        except (OSError, UnicodeError):
            # All read failures use fixed diagnostics, never paths or raw exceptions.
            print(f"ERROR {side}: cannot read UTF-8 JSON file", file=sys.stderr)
            return 2
        try:
            settings = json.loads(text)
        except json.JSONDecodeError as error:
            print(f"ERROR {side}: invalid JSON line={error.lineno} column={error.colno}",
                  file=sys.stderr)
            return 2
        except (ValueError, RecursionError):
            print(f"ERROR {side}: invalid JSON", file=sys.stderr)
            return 2
        try:
            sides.append(routes(settings))
        except ValueError as error:
            # Only fixed structural diagnostics raised by require reach this boundary.
            print(f"ERROR {side}: {error}", file=sys.stderr)
            return 2
    left, right = sides
    if left == right:
        print(f"PASS command-routes left={len(left)} right={len(right)}")
        return 0
    left_only, right_only = left - right, right - left
    events = sorted({route[0] for route in left_only | right_only})
    for event in events:
        left_count = sum(route[0] == event for route in left_only)
        right_count = sum(route[0] == event for route in right_only)
        print(f"DRIFT {event} left-only={left_count} right-only={right_count}")
    print(f"DRIFT command-routes events={len(events)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
