# AGENTS.md

Python 3.13 CLI package managed with `uv` (src layout, `uv_build` backend). Intended purpose per `pyproject.toml`: an "OKM-focused ground scan analyzer with field-operational quality gating" — `pyproject.toml` declares only the decided runtime set and the entry point dispatches subcommands on stdlib `argparse`; scientific behaviour is still ahead.

## Setup

```bash
uv sync                 # creates .venv (Python pinned by .python-version: 3.13)
```

Plain `uv run` auto-syncs; `--frozen` is used in this repo's commands to avoid re-resolving. Never `pip install` into `.venv`.

The shell is PowerShell without Unix utils (`head`, `grep`, bare `python3`, and Unix-style `gh` pipes/quoting all fail); prefer the dedicated file tools and `uv run python`.

The Windows console is cp1256, not UTF-8: never print non-ASCII from inline scripts (unit symbols, arrows); assert or compare values in-process, or write files with the file tools. To list `CONTEXT.md` headwords, write them to a temp file with the file tools and `Read` that file; never print glossary slices inline.

## Commands

| Task | Command |
| --- | --- |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Typecheck | `uv run mypy` (config already sets `files = ["src", "tests"]` — no args needed) |
| Test | `uv run pytest` |
| Single test | `uv run pytest tests/test_smoke.py::test_main_is_reexported --no-cov` |
| Debug ordering | add `-p no:randomly` |
| Mutation | `uv run pytest --gremlins --no-cov` |
| Dependency audit | `uv run deptry .` |
| Dead code | `uv run vulture src` |
| CVE scan | `uv run pip-audit -r audit-requirements.txt --disable-pip` |
| Regenerate audit lockfile | `uv export --no-emit-project --frozen -o audit-requirements.txt` |
| Run the CLI | `uv run groundscan-analyzer` |

Run gates in this order: `ruff format` → `ruff check` → `mypy` → `pytest`.

Bumping a registry version also means bumping its `Document` literal and regenerating `tests/data/*.json` via `document.dumps`; only a full `pytest` proves it, never a focused file.

There is still no CI. There **is** a `.pre-commit-config.yaml`, which runs the cheap gates on every commit: `ruff format` → `ruff check` → `vulture src` → `mypy` → `pytest` → `scripts/check_map.py` → `deptry .`. Two more are wired up but off the commit path, on the `manual` stage, because they cost minutes or need the network:

```bash
uv run pre-commit run --hook-stage manual --all-files
```

- **`deptry` is a blocking gate on the commit path.** The #19 verdicts have reached `pyproject.toml`, so a declared-but-unimported package is now a defect. The admitted-but-not-yet-imported set is scoped in `[tool.deptry.per_rule_ignores]`; any other DEP002 fails the commit.
- **`scripts/check_map.py` calls the network.** Its subject is the relationship between this repository and the tracker, not a file's contents, which is why it is a hook rather than a test.

## Pytest addopts are hostile to focused runs

`[tool.pytest.ini_options].addopts` hard-codes `-n=auto` (xdist), `--cov-branch`, `--cov-fail-under=95`, `--strict-markers`, `--strict-config`, `filterwarnings = ["error"]`, `timeout = 120`, `xfail_strict = true`. Additionally `pytest-randomly` reshuffles test order on every run.

- A focused run will **fail the 95% coverage gate** as soon as any module lacks coverage. Pass `--no-cov` for anything narrower than the full suite.
- Test order changes every run. Never depend on ordering or on module-level mutable state shared between tests. Use `-p no:randomly` to reproduce an ordering bug.
- `--strict-markers` with no `markers = [...]` list in `pyproject.toml`: any custom marker you add must be registered there first.
- Warnings are errors — new deprecation/third-party warnings break the suite.

## Ruff is pinned to one version

`required-version = "==0.16.9"` — any other ruff aborts with a version error. Do not substitute a globally installed ruff or a different `uvx ruff`.

`select = ["ALL"]` with `preview = true`, line length 100, Google docstring convention. All rules apply, notably:

- `flake8-type-checking` is `strict = true` → typing-only imports go inside `if TYPE_CHECKING:`.
- `flake8-annotations`: `mypy-init-return = true` (`__init__` must be annotated `-> None`), `allow-star-arg-any = false` (no unannotated `*args`).
- Size/complexity caps: `max-args = 5`, `max-branches = 10`, `max-returns = 4`, `max-statements = 40`, `max-complexity = 8`. Split functions rather than suppressing with `# noqa`.
- Assign exception messages to a variable before raising (EM101/TRY003); document exactly the exceptions a function raises itself; suppress only as `ruff: ignore[rule-name]` with a reason.
- `tests/**` ignores `D`, `assert`, `private-member-access`, `magic-value-comparison`, `too-many-arguments` — test files do not need docstrings.
- Share closed vocabularies as `Literal` aliases (e.g. `WithheldReason`); never `Final[Literal[...]]` constants or `NamedTuple` fields named `count`/`index` (tuple methods).

## mypy is stricter than default strict

`disallow_any_explicit = true` is on: writing `Any` anywhere in `src/` is a hard error (verified). Also enabled: `disallow_any_decorated`, `warn_unreachable`, `possibly-undefined`, `unused-awaitable`, `deprecated`, `explicit-override`, `mutable-override`, and `ignore-without-code`. These are relaxed for `tests.*` only — tests may use `Any` in fixtures/decorators.

## Dependency gate

`uv run deptry .` is blocking and currently reports zero findings. `pyproject.toml` declares only the decided runtime set (`numpy`, `pydantic`, `scipy`); the [evaluation](https://github.com/abdoupk/groundscan-analyzer-v2/issues/19) ruled `natsort`, `orjson`, `pint`, `typer`, and `rich` **out**. The admitted-but-not-yet-imported set is scoped in `[tool.deptry.per_rule_ignores]`; importing one narrows the scope, so any other DEP002 is a defect. Do not add a declared-but-unimported dependency to make a future slice convenient; that inverts the gate.

## Files to leave alone

- `audit-requirements.txt` is **autogenerated** by the `uv export` command recorded in its header. Never hand-edit it. (It was stale until [#19](https://github.com/abdoupk/groundscan-analyzer-v2/issues/19): it was missing `vulture` entirely, and the "in sync with `uv.lock`" claim in this file was false. Regenerate rather than patch.)
- `uv.lock` — commit dependency changes, never hand-edit.

## Packaging and layout

- `src/groundscan_analyzer/` with a checked-in `py.typed`; the package ships typed, so keep everything annotated.
- Console script is `groundscan-analyzer = "groundscan_analyzer:main"`. `main` must remain re-exported from `__init__.py` — `tests/test_smoke.py::test_main_is_reexported` asserts `groundscan_analyzer.main is groundscan_analyzer.cli.main`. The real implementation belongs in `cli.py`; `__init__.py` stays a thin re-export.
- CLI output goes through stdlib `argparse` + `print()` (`cli.py`), and `capsys` captures it. Per [#19](https://github.com/abdoupk/groundscan-analyzer-v2/issues/19), `rich` and `typer` are **out** — presentational weight is out of scope. The print ban is lifted for `cli.py` only (see the `cli.py` per-file-ignore in `pyproject.toml`).

## Git hygiene

`.gitignore` covers generated files, tool caches, `.venv`, and `graphify-out/`. If a tool cache shows up as untracked, extend `.gitignore` rather than deleting by hand each time.

## Implementing an engine slice

Read the ticket body, then #127's Implementation Decisions, then the `CONTEXT.md` entries they cite; on conflict the ticket wins. `docs/legacy/` is archaeology: read and cite it, never import it.

## Agent skills

### Issue tracker

Issues live in `abdoupk/groundscan-analyzer-v2` GitHub Issues, accessed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles keep their default names: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
