"""Partial source metadata, strict precedence and field-level provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pynxtools_xrm.elabftw import FIELDS, populated
from pynxtools_xrm.errors import MetadataConflict, MissingRequiredMetadata
from pynxtools_xrm.geometry import berlin_timestamp

LENGTH_TO_UM = {
    "nm": 0.001,
    "um": 1.0,
    "µm": 1.0,
    "μm": 1.0,
    "mm": 1000.0,
    "cm": 10000.0,
    "m": 1000000.0,
}


def positive_length(value, unit):
    if unit not in LENGTH_TO_UM:
        raise ValueError(f"A supported explicit length unit is required: {unit!r}")
    result = float(value) * LENGTH_TO_UM[unit]
    if not np.isfinite(result) or result <= 0:
        raise ValueError("Length must be finite and greater than zero")
    return result


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


@dataclass
class ResolvedMetadata:
    values: dict = field(default_factory=dict)
    origins: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    sources: dict = field(default_factory=dict)

    def add(self, values, source, *, supplement=False):
        for key, value in values.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if key in self.values:
                equal = json.dumps(
                    self.values[key], default=json_value, sort_keys=True
                ) == json.dumps(value, default=json_value, sort_keys=True)
                if not equal:
                    if supplement:
                        raise MetadataConflict(
                            f"Explicit {key} cannot override {self.origins[key]}"
                        )
                    self.conflicts.append(
                        {
                            "field": key,
                            "selected_source": self.origins[key],
                            "other_source": source,
                            "other_value": value,
                        }
                    )
                continue
            self.values[key], self.origins[key] = value, source

    def require(self, target, keys):
        missing = [
            k
            for k in keys
            if k not in self.values
            or self.values[k] is None
            or (isinstance(self.values[k], str) and not self.values[k].strip())
        ]
        if missing:
            raise MissingRequiredMetadata(target, missing)


def read_elabftw_metadata(path):
    """Return partial values without fabricating reconstruction metadata."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    fields = raw.get("metadata_decoded", {}).get("extra_fields", {})
    if not isinstance(fields, dict):
        raise ValueError("metadata_decoded.extra_fields must be an object")
    result = {}
    conversions = {
        "exposure_s": {"s": 1.0, "second": 1.0, "ms": 0.001},
        "source_voltage_kv": {"kV": 1.0, "V": 0.001},
        "source_power_w": {"W": 1.0, "mW": 0.001},
        "source_x_mm": {k: v / 1000 for k, v in LENGTH_TO_UM.items()},
        "detector_x_mm": {k: v / 1000 for k, v in LENGTH_TO_UM.items()},
    }
    mapping = {key: label for label, (key, _, _) in FIELDS.items()}
    for key, field_name in mapping.items():
        item = fields.get(field_name, {})
        value = item.get("value") if isinstance(item, dict) else item
        if not populated(value):
            continue
        unit = item.get("unit") if isinstance(item, dict) else None
        if key in conversions:
            if unit not in conversions[key]:
                raise ValueError(
                    f"Missing or unsupported unit for {field_name}: {unit}"
                )
            value = float(value) * conversions[key][unit]
        elif key in {
            "binning",
            "images_per_projection",
            "number_of_projections",
            "number_of_measurements",
        }:
            number = float(value)
            if not np.isfinite(number) or not number.is_integer() or number <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
            value = int(number)
        elif key in {
            "hart_used",
            "released_for_analysis",
            "repeat_measurement_required",
        }:
            if isinstance(value, str) and value in {"Yes", "No"}:
                value = value == "Yes"
        if key in {"reconstruction_date", "start_time", "end_time"}:
            value = berlin_timestamp(value)
        result[key] = value
        if unit is not None and key not in conversions:
            result[key + "_unit"] = {"h": "hour", "min": "minute", "°C": "degC"}.get(
                unit, unit
            )
    instrument = result.get("instrument_name")
    if isinstance(instrument, int) or (
        isinstance(instrument, str) and instrument.isdigit()
    ):
        result["instrument_identifier"] = instrument
        del result["instrument_name"]
        matches = [
            link
            for link in raw.get("items_links", [])
            if str(link.get("entityid")) == str(instrument) and link.get("title")
        ]
        if len(matches) == 1:
            result["instrument_name"] = matches[0]["title"]
    for key, label in (
        ("pixel_size_um", "Reconstructed voxel size"),
        ("object_pixel_size_um", "Acquisition pixel size"),
    ):
        item = fields.get(label, {})
        if item.get("value") not in (None, ""):
            result[key] = positive_length(item["value"], item.get("unit"))
    for axis in "xyz":
        item = fields.get("Stage " + axis.upper(), {})
        if item.get("value") not in (None, ""):
            unit = item.get("unit")
            if unit not in LENGTH_TO_UM:
                raise ValueError(f"Stage {axis} requires an explicit length unit")
            result[f"stage_{axis}_um"] = float(item["value"]) * LENGTH_TO_UM[unit]
    for dest, src in {
        "title": "title",
        "author": "fullname",
        "author_affiliation": "team_name",
        "entry_identifier": "elabid",
        "elabftw_url": "sharelink",
        "author_orcid": "orcid",
        "author_id": "userid",
        "tags": "tags",
    }.items():
        if raw.get(src):
            result[dest] = raw[src]
    config = raw.get("xrm_configuration", {})
    if not isinstance(config, dict) or set(config) - {
        "theta",
        "image_orientation",
        "volume_origin_um",
        "image_key",
    }:
        raise ValueError("Invalid explicit xrm_configuration in JSON")
    result.update(config)
    return result, raw


def resolve_metadata(
    source,
    *,
    recipe_match=None,
    metadata_file=None,
    supplements=None,
    target="NXtomoproc",
):
    meta = ResolvedMetadata()
    image_values = dict(source.values)
    if source.kind in {".txrm", ".xrm"} and "pixel_size_um" in image_values:
        image_values["object_pixel_size_um"] = image_values["pixel_size_um"]
    if source.kind == ".txrm":
        image_values["number_of_projections"] = source.frame_count
    meta.add(image_values, str(source.path))
    if recipe_match:
        recipe, point_name, point = recipe_match
        meta.sources["recipe"] = recipe
        meta.add(
            {"sample_name": point.get("SampleName")},
            f"{recipe['path']}:{point_name}/SampleName",
        )
        if target == "NXtomoproc":
            meta.add(
                {"raw_file": point.get("AcqFileName")},
                f"{recipe['path']}:{point_name}/AcquisitionSettings/AcqFileName",
            )
    if metadata_file:
        values, raw = read_elabftw_metadata(metadata_file)
        if target != "NXtomoproc" and "pixel_size_um" in values:
            values["declared_reconstructed_voxel_size_um"] = values.pop("pixel_size_um")
        meta.sources["elabftw"] = raw
        meta.origins["_elabftw_source"] = str(metadata_file)
        meta.add(values, str(metadata_file))
    meta.add(supplements or {}, "explicit configuration", supplement=True)
    meta.values.setdefault("title", source.path.name)
    meta.origins.setdefault("title", "generated source filename label")
    if (
        target != "NXtomoproc"
        and "pixel_size_um" not in source.values
        and "object_pixel_size_um" in meta.values
    ):
        meta.values.setdefault("pixel_size_um", meta.values["object_pixel_size_um"])
        meta.origins.setdefault("pixel_size_um", meta.origins["object_pixel_size_um"])
    if "pixel_size_um" in meta.values:
        a = np.asarray(meta.values["pixel_size_um"])
        if a.size != 1 or not np.isfinite(a.item()) or a.item() <= 0:
            raise ValueError("Voxel/pixel size must be finite and greater than zero")
        meta.values["pixel_size_um"] = float(a.item())
    for key in ("reconstruction_date", "start_time", "end_time"):
        if key in meta.values:
            meta.values[key] = berlin_timestamp(meta.values[key])
    return meta
