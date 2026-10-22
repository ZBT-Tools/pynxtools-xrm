"""Local inspection and the same conversion service used in NOMAD workers."""

import argparse
import json
from pathlib import Path

from pynxtools_xrm.definitions import prepare_definitions
from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.streaming_writer import convert
from pynxtools_xrm.tiff_stack import TiffSource, discover_tiff_stack
from pynxtools_xrm.zeiss import ZeissSource, read_recipe


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pynx-xrm")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("input", type=Path)
    setup = commands.add_parser("definitions")
    setup.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("convert")
    inputs = command.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path)
    inputs.add_argument("--tiffs", type=Path)
    command.add_argument("--metadata", type=Path)
    command.add_argument("--recipe", action="append", type=Path, default=[])
    command.add_argument(
        "--supplements", type=Path, help="JSON object: explicit missing values only"
    )
    command.add_argument("--target", choices=["NXtomo", "NXtomoproc", "NXxrm_image"])
    command.add_argument("--output", required=True, type=Path)
    command.add_argument("--gzip-level", type=int, default=4)
    command.add_argument("--chunk-mib", type=float, default=1.0)
    command.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "definitions":
        print(prepare_definitions(args.output))
        return 0
    if args.command == "inspect":
        if args.input.suffix.casefold() == ".rcp":
            print(json.dumps(read_recipe(args.input), indent=2))
            return 0
        source = (
            TiffSource(discover_tiff_stack(args.input))
            if args.input.is_dir()
            else ZeissSource(args.input)
        )
        print(
            json.dumps(
                {
                    "frames": source.frame_count,
                    "image_shape": source.image_shape,
                    "dtype": str(source.dtype),
                    "auxiliary": [b.name for b in source.auxiliary],
                },
                indent=2,
            )
        )
        return 0
    report = convert(
        args.input or args.tiffs,
        args.output,
        target_definition=args.target,
        metadata_file=args.metadata,
        recipe_paths=args.recipe,
        supplements=json.loads(args.supplements.read_text())
        if args.supplements
        else None,
        compression=CompressionConfig(
            level=args.gzip_level,
            target_chunk_bytes=max(1, round(args.chunk_mib * 1024**2)),
        ),
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {**report.__dict__, "output_path": str(report.output_path)}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
