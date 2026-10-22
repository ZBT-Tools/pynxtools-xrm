"""Thin raw-file orchestrator; generated NeXus uses the existing NOMAD parser."""

from pathlib import Path

import olefile
from nomad.parsing import MatchingParser

from pynxtools_xrm.models import CompressionConfig
from pynxtools_xrm.nomad.jobs import discover_sidecars, find_config, output_relative
from pynxtools_xrm.streaming_writer import convert


class XRMRawParser(MatchingParser):
    def is_mainfile(self, filename, mime, buffer, decoded_buffer, compression=None):
        if not super().is_mainfile(filename, mime, buffer, decoded_buffer, compression):
            return False
        try:
            with olefile.OleFileIO(filename) as ole:
                return all(
                    ole.exists(p)
                    for p in (
                        "ImageInfo/ImageWidth",
                        "ImageInfo/ImageHeight",
                        "ImageInfo/DataType",
                        "ImageData1/Image1",
                    )
                )
        except (OSError, ValueError):
            return False

    def parse(self, mainfile, archive, logger=None, child_archives=None):
        from pynxtools_xrm.nomad.schema_packages.schema import (  # noqa: PLC0415
            XRMDataConverter,
        )

        source = Path(mainfile).resolve()
        root = Path(archive.m_context.raw_path()).resolve()
        config = find_config(source, root)
        metadata, recipes = discover_sidecars(source, root, config)
        output = config.get("output") or output_relative(source, root)
        output_path = (root / output).resolve()
        if not output_path.is_relative_to(root):
            raise ValueError("Output escapes NOMAD upload")
        section = XRMDataConverter(
            input_file=source.relative_to(root).as_posix(), output=output, export=False
        )
        archive.data = section
        report = convert(
            source,
            output_path,
            metadata_file=metadata,
            recipe_paths=recipes,
            supplements=config.get("metadata_supplements"),
            target_definition=config.get("target_definition"),
            compression=CompressionConfig(
                level=int(config.get("gzip_level", 4)),
                target_chunk_bytes=round(
                    float(config.get("target_chunk_mib", 1.0)) * 1024**2
                ),
            ),
            overwrite=True,
        )
        if not report.reused:
            archive.m_context.process_updated_raw_file(output, allow_modify=True)
        section.nexus_view = f"../upload/archive/mainfile/{output}#/data"
        section.conversion_status = "reused" if report.reused else "converted"
