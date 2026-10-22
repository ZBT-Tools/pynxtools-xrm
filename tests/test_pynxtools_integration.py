"""Integration tests for the supported pynxtools-xrm streaming contract."""

from __future__ import annotations

import logging

import h5py
from pynxtools.dataconverter.convert import get_reader
from pynxtools.dataconverter.validate_file import validate

from pynxtools_xrm.reader import XRMReader
from pynxtools_xrm.streaming_writer import convert_tomoproc


def test_xrm_reader_entry_point_is_discoverable():
    """The metadata reader remains discoverable through pynxtools entry points."""

    reader = get_reader("xrm")
    assert reader is XRMReader
    assert reader.supported_nxdls == ["NXtomo", "NXtomoproc", "NXxrm_image"]


def test_streaming_output_passes_pynxtools_validation(tmp_path, xrm_inputs, caplog):
    """Validate the dedicated writer output without invoking the core Writer."""

    metadata, tiffs, _ = xrm_inputs
    output = tmp_path / "validated.nxs"
    convert_tomoproc(metadata, tiffs, output)

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        validate(str(output), ignore_undocumented=True)

    assert not any("NOT valid" in record.getMessage() for record in caplog.records)
    with h5py.File(output, "r") as handle:
        assert handle["/entry/definition"].asstr()[()] == "NXtomoproc"
        assert handle["/entry/data/data"].shape == (4, 3, 3)
