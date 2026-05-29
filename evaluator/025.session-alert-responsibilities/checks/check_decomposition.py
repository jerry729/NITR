"""Structural check for case 025: session alert responsibilities.

This case probes D3 (responsibility decomposition).  The functional task asks
the agent to add two new anomaly families (drift, leak) to a monitor that
currently only reports range alerts.  Both a cleanly decomposed solution and a
tangled one (all three families computed inside a single function) pass the
functional tests, so the structural check is the oracle for the dimension.

Rule enforced:

    No single function may produce more than one of the three alert families.

A function "produces" a family if its body either names that family's alert
type (e.g. ``RangeAlert``) or appends to that family's report vector (e.g.
``range_alerts.push_back(...)`` / ``.emplace_back(...)``).  A clean solution
gives each family its own producing function (free function, method, or
lambda-free helper) and a thin orchestrator that only routes the results, so
every function touches at most one family.  A tangled solution computes two or
three families in one function and is flagged.

Positive arm: all three families must be produced somewhere, so the check is
not vacuously satisfied by an unfinished solution.
"""

import pathlib
import re
import sys

# A family is "produced" by either naming its alert type or appending to its
# report vector.  Member reads/assignments (``report.range_alerts = ...``) are
# deliberately NOT signals: the orchestrator legitimately routes every vector.
_FAMILY_SIGNALS = {
    "range": re.compile(
        r"\bRangeAlert\b"
        r"|\brange_alerts\s*\.\s*(?:push_back|emplace_back)\b"
    ),
    "drift": re.compile(
        r"\bDriftAlert\b"
        r"|\bdrift_alerts\s*\.\s*(?:push_back|emplace_back)\b"
    ),
    "leak": re.compile(
        r"\bLeakAlert\b"
        r"|\bleak_alerts\s*\.\s*(?:push_back|emplace_back)\b"
    ),
}

_CONTROL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "sizeof",
    "do",
}

# A function definition opening: an identifier, a parenthesised parameter list
# that contains no ``;`` `{` `}` (so for-loops and statements are excluded),
# optional trailing qualifiers, then the opening brace of the body.
_FUNC_OPEN = re.compile(
    r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*"
    r"(?:const|noexcept|override|final|->|[\w:<>,&*\s])*\{"
)


def strip_comments_and_strings(text: str) -> str:
    """Blank out comments and string/char literals so tokens only match code."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*", "", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])+'", "''", text)
    return text


def function_bodies(text: str):
    """Yield (name, body) for every function/method body in ``text``.

    Bodies are located by brace-matching from a function-definition opening.
    Control-flow blocks (if/for/while/...) are skipped by name.  Nested control
    blocks inside a captured body stay attributed to that enclosing function.
    """
    for match in _FUNC_OPEN.finditer(text):
        name = match.group(1)
        if name in _CONTROL_KEYWORDS:
            continue
        open_brace = match.end() - 1
        depth = 0
        i = open_brace
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield name, text[open_brace : i + 1]


def families_in(body: str) -> set:
    """Return the set of alert families produced inside one function body."""
    return {fam for fam, rx in _FAMILY_SIGNALS.items() if rx.search(body)}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check_decomposition.py <case_dir>")
        return 1

    case_dir = pathlib.Path(sys.argv[1]).resolve()
    src_dir = case_dir / "src"

    src_files = sorted(src_dir.rglob("*.h")) + sorted(
        list(src_dir.rglob("*.cc")) + list(src_dir.rglob("*.cpp"))
    )
    if not src_files:
        print(f"No source files found under {src_dir}")
        return 1

    violations: list[str] = []
    produced_anywhere: set = set()

    for path in src_files:
        try:
            text = strip_comments_and_strings(path.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to read {path}: {exc}")
            return 1
        rel = path.relative_to(case_dir)
        for name, body in function_bodies(text):
            fams = families_in(body)
            produced_anywhere |= fams
            if len(fams) >= 2:
                violations.append(
                    f"{rel}: function '{name}' produces multiple alert families "
                    f"({', '.join(sorted(fams))}). Each anomaly family should be "
                    "owned by its own unit; one function should not assemble more "
                    "than one."
                )

    # Positive arm: the three families must each be produced somewhere.
    missing = {"range", "drift", "leak"} - produced_anywhere
    if missing:
        violations.append(
            "No producer found for alert families: "
            f"{', '.join(sorted(missing))}. The monitor must report range, drift, "
            "and leak alerts."
        )

    if violations:
        for v in violations:
            print(v)
        return 1

    print("Decomposition check passed: each alert family is owned separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
