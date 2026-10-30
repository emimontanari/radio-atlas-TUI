"""Command line entry point."""

from __future__ import annotations

import pytest

from radio_atlas import __version__, cli
from radio_atlas.geo import GeoAssetError


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.ascii is False
    assert args.mpv is None


def test_parser_accepts_ascii_and_custom_mpv():
    args = cli.build_parser().parse_args(["--ascii", "--mpv", "/opt/mpv"])
    assert args.ascii is True
    assert args.mpv == "/opt/mpv"


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_main_builds_and_runs_the_app(monkeypatch):
    created = []

    class FakeApp:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def run(self):
            created.append("ran")

    monkeypatch.setattr(cli, "RadioAtlasApp", FakeApp)
    assert cli.main(["--ascii", "--mpv", "/opt/mpv"]) == 0
    assert created == [{"ascii_globe": True, "mpv_path": "/opt/mpv"}, "ran"]


def test_main_reports_missing_assets(monkeypatch, capsys):
    class BrokenApp:
        def __init__(self, **kwargs):
            raise GeoAssetError("worldmask.bin is missing")

    monkeypatch.setattr(cli, "RadioAtlasApp", BrokenApp)
    assert cli.main([]) == 1
    captured = capsys.readouterr()
    assert "radio-atlas: worldmask.bin is missing" in captured.err
    assert captured.out == ""
