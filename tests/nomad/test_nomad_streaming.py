"""NOMAD integration tests for streamed NXtomoproc conversion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("nomad")

from nomad.client import parse
from nomad.datamodel import Context, EntryArchive

from pynxtools_xrm.nomad.schema_packages.schema import XRMDataConverter
from pynxtools_xrm.streaming_writer import convert_tomoproc


class TemporaryRawContext(Context):
    """Small local context that records generated-file processing requests."""

    def __init__(self, raw_root: Path):
        super().__init__()
        self.raw_root = raw_root
        self.updated: list[tuple[str, bool]] = []

    def raw_path(self) -> str:
        return str(self.raw_root)

    def process_updated_raw_file(self, path, allow_modify=False):
        self.updated.append((path, allow_modify))


def test_generated_nexus_is_parsed_by_nomad(tmp_path, xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    output = tmp_path / "nomad-parse.nxs"
    convert_tomoproc(metadata, tiffs, output)

    archives = parse(
        str(output),
        strict=True,
        parser_name=None,
        server_context=False,
        username=None,
        password=None,
    )

    assert archives
    assert any(archive.data is not None for archive in archives)


def test_xrm_data_converter_normalizer(tmp_path, xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    context = TemporaryRawContext(tmp_path)
    archive = EntryArchive(m_context=context)
    section = XRMDataConverter(
        metadata_file=metadata.name,
        tiff_directory=tiffs.name,
        output="normalized.nxs",
        gzip_level=1,
        target_chunk_mib=0.01,
        export=True,
    )
    archive.data = section

    section.normalize(archive, Mock())

    assert (tmp_path / "normalized.nxs").is_file()
    assert context.updated == [("normalized.nxs", True)]
    assert section.assumptions
