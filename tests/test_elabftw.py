"""Check semantic storage, source precedence and unmapped-field reporting."""

import json

import h5py
import numpy as np
import pytest

from pynxtools_xrm.metadata import read_elabftw_metadata
from pynxtools_xrm.streaming_writer import convert


@pytest.mark.parametrize("target", ["NXtomoproc", "NXtomo"])
def test_semantic_elabftw_storage(tmp_path, xrm_inputs, target):
    metadata, tiffs, _ = xrm_inputs
    raw = json.loads(metadata.read_text())
    raw.update(
        items_links=[{"entityid": 109, "title": "Xradia 620 XRM"}],
        body_html="<p>Measurement documentation</p>",
        canread='{"teams":[2]}',
        access_key="must-not-copy",
    )
    raw["metadata_decoded"]["extra_fields"].update(
        {
            "Objective": {"value": "20x"},
            "Filter": {"value": "Air"},
            "Binning": {"value": "2", "type": "number"},
            "Research question": {"value": ["Prüfung", "Method development"]},
            "Unverified field": {"value": "retain as native text", "options": ["a"]},
            "Empty field": {"value": ""},
        }
    )
    if target == "NXtomo":
        raw["xrm_configuration"].update(theta=[0, 1, 2], image_key=[0, 0, 0])
    metadata.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "semantic.nxs"
    convert(tiffs, output, metadata_file=metadata, target_definition=target)
    with h5py.File(output) as h:
        entry = h["entry"]
        assert "elabftw" not in entry
        assert entry["metadata_provenance"].attrs["NX_class"] == "NXcollection"
        assert entry["instrument/name"].asstr()[()] == "Xradia 620 XRM"
        assert entry["instrument/identifiers/elabftw_item_id"][()] == 109
        assert entry["instrument/filter/description"].asstr()[()] == "Air"
        assert entry["instrument/optics/objective"].asstr()[()] == "20x"
        assert entry["instrument/detector/readout/binning"][()] == 2
        np.testing.assert_array_equal(
            entry["experiment_description"].asstr()[:],
            ["Prüfung", "Method development"],
        )
        assert entry["acquisition/measurement_date"].asstr()[()] == "2026-08-26"
        assert (
            entry["experiment_documentation/data"][()]
            == b"<p>Measurement documentation</p>"
        )
        table = entry["metadata_provenance/elabftw_mapping"]
        statuses = dict(
            zip(table["source_path"].asstr()[:], table["status"].asstr()[:])
        )
        assert (
            statuses["metadata_decoded/extra_fields/Unverified field"] == "not_assigned"
        )
        assert statuses["metadata_decoded/extra_fields/Empty field"] == "empty"
        assert statuses["access_key"] == "not_assigned"
        assert len(entry["unmapped_metadata"]) == 1
        assert entry["metadata_provenance/origins/sample_name"].asstr()[()] == str(
            metadata
        )
        assert (
            "reconstruction" in entry
            if target == "NXtomoproc"
            else "reconstruction" not in entry
        )


def test_instrument_identifier_is_not_a_name(xrm_inputs):
    values, _ = read_elabftw_metadata(xrm_inputs[0])
    assert values["instrument_identifier"] == 109
    assert "instrument_name" not in values


def test_raw_calibration_is_not_reconstruction_calibration(tmp_path, xrm_inputs):
    metadata, tiffs, _ = xrm_inputs
    raw = json.loads(metadata.read_text())
    raw["metadata_decoded"]["extra_fields"].pop("Reconstructed voxel size")
    raw["xrm_configuration"].update(theta=[0, 1, 2], image_key=[0, 0, 0])
    metadata.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "raw-calibration.nxs"
    convert(tiffs, output, metadata_file=metadata, target_definition="NXtomo")
    with h5py.File(output) as h:
        assert "declared_reconstructed_voxel_size" not in h["entry/data_provenance"]
        assert h["entry/instrument/detector/object_calibration/pixel_size"][()] == 0.5
