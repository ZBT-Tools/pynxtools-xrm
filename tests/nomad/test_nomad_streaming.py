"""NOMAD integration tests for streamed NXtomoproc conversion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("nomad")

from nomad.client import parse
from nomad.datamodel import Context, EntryArchive, EntryMetadata

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

    @property
    def upload_id(self):
        return "test-upload"

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
    archive = EntryArchive(
        m_context=context, metadata=EntryMetadata(upload_id="test-upload")
    )
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
    assert not section.assumptions
    assert section.m_to_dict()["nexus_view"].endswith("#/data")


def test_binary_matching_has_no_conversion(monkeypatch):
    from pynxtools_xrm.nomad.parsers import xrm_raw_parser  # noqa: PLC0415

    class Compound:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def exists(self, path):
            return True

    monkeypatch.setattr(
        "pynxtools_xrm.nomad.parsers.parser.olefile.OleFileIO", Compound
    )
    parser = xrm_raw_parser.load()
    magic = bytes.fromhex("d0cf11e0a1b11ae1")
    assert parser.is_mainfile("scan.TXRM", "application/octet-stream", magic, "")
    assert not parser.is_mainfile("scan.doc", "application/octet-stream", magic, "")
    assert not parser.is_mainfile(
        "scan.txrm", "application/octet-stream", b"not OLE", ""
    )


def test_upload_paths_are_scoped_and_outputs_are_distinct(tmp_path):
    from pynxtools_xrm.nomad.jobs import output_relative, safe_raw_path  # noqa: PLC0415

    a, b = tmp_path / "scan.txrm", tmp_path / "scan.txm"
    for path in (a, b):
        path.touch()
    assert output_relative(a, tmp_path) != output_relative(b, tmp_path)
    assert safe_raw_path(tmp_path, "scan.txrm") == a
    with pytest.raises(ValueError, match="escapes"):
        safe_raw_path(tmp_path, "../outside.txrm")
