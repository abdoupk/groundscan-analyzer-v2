"""CLI surface: 5 commands, no compare (fast)."""

import re
from pathlib import Path

import pytest

from groundscan.cli import _build_parser, main
from groundscan.cli.analyze import default_single_out, default_site_out, resolve_out


def test_help_lists_five_commands_no_compare(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for cmd in ["analyze", "analyze-site", "quality-check", "diagnose", "validate"]:
        assert cmd in out
    assert "compare" not in out


def test_unknown_command_rejected():
    with pytest.raises(SystemExit) as e:
        main(["compare", "a", "b"])
    assert e.value.code == 2


def test_site_recursive_on_by_default_with_opt_out():
    parser = _build_parser()
    assert parser.parse_args(["analyze-site", "x"]).recursive is True
    assert parser.parse_args(["analyze-site", "x", "--recursive"]).recursive is True
    assert parser.parse_args(["analyze-site", "x", "--no-recursive"]).recursive is False


def test_out_defaults_to_none_for_default_resolution():
    parser = _build_parser()
    assert parser.parse_args(["analyze", "f.csv"]).out is None
    assert parser.parse_args(["analyze-site", "d"]).out is None


def test_default_single_out_uses_file_stem():
    assert default_single_out("scans/SiteA/grid_N.csv") == Path("results/grid_N")


def test_default_site_out_single_dir_uses_dir_name(tmp_path):
    site = tmp_path / "SiteA"
    site.mkdir()
    assert default_site_out([str(site)]) == Path("results/SiteA")


def test_default_site_out_files_sharing_parent_use_parent_name(tmp_path):
    site = tmp_path / "SiteA"
    site.mkdir()
    assert default_site_out([str(site / "a.csv"), str(site / "b.csv")]) == Path("results/SiteA")


def test_default_site_out_mixed_inputs_falls_back_to_site(tmp_path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    assert default_site_out([str(a), str(b)]) == Path("results/site")


def test_resolve_out_explicit_wins_even_when_default_exists(tmp_path):
    default = tmp_path / "run"
    default.mkdir()
    (default / "old.txt").write_text("x")
    assert resolve_out(str(tmp_path / "mine"), default) == tmp_path / "mine"


def test_resolve_out_reuses_missing_or_empty_default(tmp_path):
    assert resolve_out(None, tmp_path / "fresh") == tmp_path / "fresh"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert resolve_out(None, empty) == empty


def test_resolve_out_timestamps_nonempty_default(tmp_path):
    default = tmp_path / "SiteA"
    default.mkdir()
    (default / "site_report.html").write_text("x")
    got = resolve_out(None, default)
    assert got.parent == tmp_path
    assert re.fullmatch(r"SiteA_\d{8}-\d{6}", got.name)
