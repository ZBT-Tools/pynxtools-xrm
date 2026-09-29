"""Command-line interface for local and NOMAD-worker conversions."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.streaming_writer import convert_tomoproc
from pynxtools_xrm.tiff_stack import discover_tiff_stack


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pynx-xrm")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="inspect TIFF headers only")
    inspect.add_argument("tiff_directory", type=Path)
    convert = subparsers.add_parser("convert", help="stream TIFFs into NXtomoproc")
    convert.add_argument("--metadata", required=True, type=Path)
    convert.add_argument("--tiffs", required=True, type=Path)
    convert.add_argument("--output", required=True, type=Path)
    convert.add_argument("--gzip-level", type=int, default=4)
    convert.add_argument("--chunk-mib", type=float, default=1.0)
    convert.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "inspect":
        manifest = discover_tiff_stack(args.tiff_directory)
        print(
            json.dumps(
                {
                    "number_of_slices": len(manifest.paths),
                    "tiff_shape_z_x": manifest.image_shape,
                    "nxtomoproc_shape_x_y_z": manifest.volume_shape,
                    "dtype": str(manifest.dtype),
                    "first": manifest.paths[0].name,
                    "last": manifest.paths[-1].name,
                },
                indent=2,
            )
        )
        return 0

    last_percent = -1

    def show_progress(current: int, total: int, _path: Path) -> None:
        nonlocal last_percent
        percent = current * 100 // total
        if percent >= last_percent + 5 or current == total:
            logging.info("TIFF streaming: %d/%d (%d%%)", current, total, percent)
            last_percent = percent

    report = convert_tomoproc(
        args.metadata,
        args.tiffs,
        args.output,
        compression=CompressionConfig(
            level=args.gzip_level,
            target_chunk_bytes=max(1, round(args.chunk_mib * 1024 * 1024)),
        ),
        overwrite=args.overwrite,
        progress=show_progress,
    )
    print(
        json.dumps(
            {**report.__dict__, "output_path": str(report.output_path)}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
