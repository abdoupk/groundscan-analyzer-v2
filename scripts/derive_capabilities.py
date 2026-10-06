"""Derive the capability census at `docs/capabilities.md` from the legacy tree.

Row existence is DERIVED, never maintained: a legacy module either exists or it
does not, so re-running this against `docs/legacy/` reproduces the row set and
the count cannot drift. A verdict is the maintained half, and lives in the
artefact's verdict columns.

The derivation reads AST only. It never reads a docstring, a comment, or any
other prose in the archaeology - a legacy docstring asserting a false claim is
the third instance this project has recorded of legacy prose contradicting its
own code, so prose is not evidence here by policy.

Usage:
    python scripts/derive_capabilities.py table     print the row table (markdown)
    python scripts/derive_capabilities.py report    print counts, breakdown, findings
    python scripts/derive_capabilities.py json      print the rows as JSON

Read-only against `docs/legacy/`. It parses files; it never imports them.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

LEGACY_ROOT = Path(__file__).resolve().parent.parent / "docs" / "legacy"
ARTEFACT = Path(__file__).resolve().parent.parent / "docs" / "capabilities.md"

#: A path component that removes a module from the denominator. `tests/` asserts
#: about capabilities and does not have them; `results/` holds only `.gitkeep`.
EXCLUDED_COMPONENTS = frozenset({"tests", "results"})

#: Decorator or base names that make a module-level class a record type.
RECORD_MARKERS = frozenset(
    {
        "dataclass",
        "NamedTuple",
        "namedtuple",
        "TypedDict",
        "Protocol",
        "Enum",
        "IntEnum",
        "StrEnum",
    }
)

#: The row-kind token for a capability that emits no declared record.
NO_OUTPUT = "no-output"

#: The row-kind token for a declared record.
OUTPUT = "declared-record"

#: The roles a `no-output` row can carry. Derived, not assigned. A `no-output`
#: row is a location, not a capability, so every one carries a token.
CALLABLE_SURFACE = "callable-surface"
PRIVATE_ONLY = "private-only"
CONSTANTS_ONLY = "constants-only"

#: Internal marker for the excluded set. A facade takes no row: it declares no
#: definition of its own and re-exports from a module in the tree.
FACADE = "facade"


@dataclass(frozen=True, slots=True)
class Row:
    """One capability row of the census.

    `name` is the record class for a `declared-record` row and the module path for a
    `no-output` row, because that is the identity a search would use. `role`
    is the derived classification of a `no-output` row and is empty otherwise:
    it is populated exactly when `kind` is `no-output`.
    """

    name: str
    kind: str
    module: str
    subtree: str
    role: str = ""


@dataclass(slots=True)
class Census:
    """The derived census, plus the material #90 asks a derivation to report."""

    denominator: tuple[str, ...] = ()
    rows: tuple[Row, ...] = ()
    package_markers: tuple[str, ...] = ()
    facades: dict[str, list[str]] = field(default_factory=dict)
    callable_surface: tuple[str, ...] = ()
    private_only: tuple[str, ...] = ()
    constants_only: tuple[str, ...] = ()
    collisions: dict[str, list[str]] = field(default_factory=dict)


def denominator(root: Path = LEGACY_ROOT) -> tuple[Path, ...]:
    """Every `.py` under `root` outside an excluded component, in path order."""
    return tuple(
        sorted(
            path
            for path in root.rglob("*.py")
            if not EXCLUDED_COMPONENTS & set(path.relative_to(root).parts)
        )
    )


def subtree_of(relative: str) -> str:
    """The subtree bucket a module is counted under.

    Two components for a package, so `groundscan/validation/calibration` and
    `groundscan/validation` are one bucket rather than two, and a top-level
    module such as `groundscan/models.py` buckets as `groundscan` itself.
    """
    parts = relative.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def _public(name: str) -> bool:
    return not name.startswith("_")


def _marker_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        names.add(ast.unparse(decorator).split("(", 1)[0].split(".")[-1])
    for base in node.bases:
        names.add(ast.unparse(base).split(".")[-1])
    return names


def _is_record(node: ast.ClassDef) -> bool:
    return _public(node.name) and bool(_marker_names(node) & RECORD_MARKERS)


def _defs(tree: ast.Module, *, public_only: bool) -> list[str]:
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and (not public_only or _public(node.name))
    ]


def _sibling_imports(tree: ast.Module, package: str) -> list[str]:
    """Modules this one imports from inside the tree.

    A relative import, or an absolute one naming the same top-level package.
    Absolute imports of stdlib or of a third-party package are not evidence that
    a module re-exports a sibling capability.
    """
    sources: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.level or node.module.split(".")[0] == package:
            sources.append(node.module)
    return sources


def is_facade(tree: ast.Module, package: str) -> bool:
    """Whether a module is a re-export surface taking no row.

    A module that declares no definition of its own and re-exports from a
    module in the tree. Derived rather than assigned, because assigning it by
    reading is exactly the prose-reading this derivation refuses.
    """
    return not _defs(tree, public_only=False) and bool(_sibling_imports(tree, package))


def resolve_targets(
    facade: str, tree: ast.Module, denominator_set: set[str]
) -> list[str]:
    """Resolve a facade's re-export imports to denominator modules, one hop.

    Every target takes a row already and there are zero chains, so the
    coverage check needs one hop rather than a fixpoint. A fixpoint would be
    machinery for a case the tree does not contain.

    Args:
        facade: the facade's own module path, e.g. `groundscan/core/artifact.py`.
        tree: its parsed AST.
        denominator_set: every denominator module path.

    Returns:
        The sorted target module paths this facade re-exports.
    """
    package = facade.split("/")[0]
    base = facade.rpartition("/")[0] if "/" in facade else ""
    if facade.endswith("__init__.py"):
        base_dir = facade.rpartition("/")[0]
    else:
        base_dir = base
    targets: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            if node.module:
                dotted = f"{base_dir.replace('/', '.')}.{node.module}" if base_dir else node.module
            else:
                dotted = base_dir.replace("/", ".") if base_dir else ""
        elif node.module and node.module.split(".")[0] == package:
            dotted = node.module
        else:
            continue
        if not dotted:
            continue
        rel = dotted.replace(".", "/") + ".py"
        if rel in denominator_set:
            targets.add(rel)
            continue
        init_rel = dotted.replace(".", "/") + "/__init__.py"
        if init_rel in denominator_set:
            targets.add(init_rel)
    return sorted(targets)


def role_of(tree: ast.Module) -> str:
    """The role of a module that emits no declared record and is not a facade.

    Derived rather than assigned. Every `no-output` row carries one token:
    `callable-surface` for the ordinary case, never blank.
    """
    if not _defs(tree, public_only=False):
        return CONSTANTS_ONLY
    return PRIVATE_ONLY if not _defs(tree, public_only=True) else CALLABLE_SURFACE


def derive(root: Path = LEGACY_ROOT) -> Census:
    """Derive the census from the tree, by AST, reading no prose."""
    paths = denominator(root)
    trees = {path: ast.parse(path.read_text(encoding="utf-8", errors="replace")) for path in paths}
    relative = {path: path.relative_to(root).as_posix() for path in paths}

    declared: dict[str, str] = {}
    for path in paths:
        for node in trees[path].body:
            if isinstance(node, ast.ClassDef) and _is_record(node):
                declared.setdefault(node.name, relative[path])

    instantiated: dict[str, set[str]] = {}
    for path in paths:
        for node in ast.walk(trees[path]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in declared:
                    instantiated.setdefault(node.func.id, set()).add(relative[path])

    rows: list[Row] = []
    markers: list[str] = []
    facades: dict[str, list[str]] = {}
    callable_surface: list[str] = []
    private_only: list[str] = []
    constants_only: list[str] = []
    for path in paths:
        name = relative[path]
        package = name.split("/")[0]
        emitted = sorted(cls for cls, owner in declared.items() if owner == name)
        if emitted:
            rows.extend(
                Row(name=cls, kind=OUTPUT, module=name, subtree=subtree_of(name)) for cls in emitted
            )
            continue
        if is_facade(trees[path], package):
            facades[name] = resolve_targets(name, trees[path], set(relative.values()))
            continue
        role = role_of(trees[path])
        if role == CONSTANTS_ONLY and path.name == "__init__.py":
            markers.append(name)
            continue
        rows.append(
            Row(name=name, kind=NO_OUTPUT, module=name, subtree=subtree_of(name), role=role)
        )
        if role == CALLABLE_SURFACE:
            callable_surface.append(name)
        elif role == PRIVATE_ONLY:
            private_only.append(name)
        elif role == CONSTANTS_ONLY:
            constants_only.append(name)

    owners: dict[str, list[str]] = {}
    for cls, owner in declared.items():
        owners.setdefault(cls, []).append(owner)

    return Census(
        denominator=tuple(relative[path] for path in paths),
        rows=tuple(sorted(rows, key=lambda row: (row.module, row.name))),
        package_markers=tuple(sorted(markers)),
        facades=facades,
        callable_surface=tuple(sorted(callable_surface)),
        private_only=tuple(sorted(private_only)),
        constants_only=tuple(sorted(constants_only)),
        collisions={cls: sorted(where) for cls, where in owners.items() if len(where) > 1},
    )


def render_table(census: Census) -> str:
    """The row table, exactly as the artefact carries it."""
    lines = [
        "| capability | kind | role | legacy module | concept | implementation | verdict issue |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in census.rows:
        role = f"`{row.role}`" if row.role else ""
        lines.append(
            f"| `{row.name}` | `{row.kind}` | {role} | `{row.module}` |  |  | #1 |"
        )
    return "\n".join(lines)


def report(census: Census) -> dict[str, object]:
    """The numbers #90 requires a derivation to record, as amended by #92."""
    covered = {row.module for row in census.rows}
    uncovered = sorted(set(census.denominator) - covered)
    return {
        "denominator_files": len(census.denominator),
        "rows": len(census.rows),
        "rows_by_kind": dict(sorted(Counter(row.kind for row in census.rows).items())),
        "rows_by_role": dict(
            sorted(Counter(row.role for row in census.rows if row.role).items())
        ),
        "rows_by_subtree": dict(
            sorted(Counter(row.subtree for row in census.rows).items())
        ),
        "modules_covered": len(covered),
        "modules_uncovered": uncovered,
        "excluded_modules": sorted([*census.facades, *census.package_markers]),
        "package_markers": list(census.package_markers),
        "re_export_facades": census.facades,
        "callable_surface_modules": list(census.callable_surface),
        "private_only_modules": list(census.private_only),
        "constants_only_modules": list(census.constants_only),
        "record_name_collisions": census.collisions,
        "callable_name_collisions": _callable_collisions(census),
        "verdicts_located": 0,
        "verdicts_empty": len(census.rows),
    }


def _callable_collisions(census: Census) -> dict[str, list[str]]:
    """Public callable names declared in more than one denominator module.

    Reported because a name collision is a finding the record grain cannot
    exhibit: rows are keyed by record class, and no two modules declare the same
    one. The collisions below are what a callable-grain enumeration *would* have
    had to qualify, and they are recorded rather than left for a reader to find.
    """
    seen: dict[str, set[str]] = {}
    for path in denominator():
        name = path.relative_to(LEGACY_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _public(node.name):
                seen.setdefault(node.name, set()).add(name)
    return {name: sorted(where) for name, where in sorted(seen.items()) if len(where) > 1}


BEGIN_MARKER = "<!-- BEGIN DERIVED TABLE -->"
END_MARKER = "<!-- END DERIVED TABLE -->"


def sync(census: Census, artefact: Path = ARTEFACT) -> int:
    """Replace the generated block in the artefact with the derived table.

    The block is regenerated rather than pasted, so the table and the row set
    cannot drift apart: one command rewrites both or neither.
    """
    text = artefact.read_text(encoding="utf-8")
    if BEGIN_MARKER not in text or END_MARKER not in text:
        message = f"{artefact} has no derived-table markers to sync"
        raise SystemExit(message)
    head, _, rest = text.partition(f"{BEGIN_MARKER}\n")
    _, _, tail = rest.partition(END_MARKER)
    table = render_table(census)
    artefact.write_text(f"{head}{BEGIN_MARKER}\n{table}\n\n{END_MARKER}{tail}", encoding="utf-8")
    return census.rows.__len__()


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("table", "report", "json", "sync"))
    args = parser.parse_args()

    census = derive()
    if args.mode == "table":
        print(render_table(census))
    elif args.mode == "sync":
        print(f"synced {sync(census)} rows into {ARTEFACT.name}")
    elif args.mode == "report":
        print(json.dumps(report(census), indent=2))
    else:
        print(
            json.dumps(
                [
                    {
                        "name": row.name,
                        "kind": row.kind,
                        "shape": row.shape,
                        "module": row.module,
                        "subtree": row.subtree,
                    }
                    for row in census.rows
                ],
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
