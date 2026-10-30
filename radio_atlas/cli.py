"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .app import RadioAtlasApp
from .geo import GeoAssetError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radio-atlas",
        description="Explore and play live radio from around the world.",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="render the globe with ASCII characters instead of braille",
    )
    parser.add_argument(
        "--mpv",
        metavar="PATH",
        default=None,
        help="path to the mpv binary (default: found in PATH)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        app = RadioAtlasApp(ascii_globe=args.ascii, mpv_path=args.mpv)
    except GeoAssetError as error:
        print(f"radio-atlas: {error}", file=sys.stderr)
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
