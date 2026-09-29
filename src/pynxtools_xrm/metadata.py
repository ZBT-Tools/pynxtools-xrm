"""Translate the eLabFTW JSON export into NXtomoproc metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class XRMMetadata:
    title: str
    sample_name: str
    source_type: str
    source_name: str
    reconstruction_program: str
    reconstruction_version: str
    reconstruction_date: str
    raw_file: str
    voxel_size_um: float
    parameters: dict[str, Any]
    assumptions: tuple[str, ...]


def _value(fields: dict[str, Any], name: str, default: Any = None) -> Any:
    item = fields.get(name, default)
    return item.get("value", default) if isinstance(item, dict) else item


def _choose_raw_file(metadata_path: Path, sample_name: str) -> str | None:
    candidates = []
    for path in metadata_path.parent.rglob("*.txrm"):
        lowered = path.name.casefold()
        penalty = sum(token in lowered for token in ("drift", "scout", "reference"))
        sample_match = sample_name.casefold().replace("_", "") in lowered.replace(
            "_", ""
        )
        candidates.append(
            (penalty, not sample_match, -path.stat().st_size, path.as_posix(), path)
        )
    if not candidates:
        return None
    selected = min(candidates)[-1]
    return selected.relative_to(metadata_path.parent).as_posix()


def read_elabftw_metadata(path: str | Path) -> XRMMetadata:
    """Read the supplied eLabFTW JSON and apply documented fallbacks."""

    path = Path(path)
    with path.open("r", encoding="utf-8") as stream:
        source = json.load(stream)
    fields = source.get("metadata_decoded", {}).get("extra_fields", {})
    if not isinstance(fields, dict):
        raise ValueError("metadata_decoded.extra_fields must be a JSON object")

    assumptions: list[str] = []
    sample_name = str(_value(fields, "Sample name") or source.get("title") or "sample")
    voxel_size = _value(fields, "Reconstructed voxel size")
    if voxel_size in (None, ""):
        voxel_size = _value(fields, "Acquisition pixel size")
        assumptions.append(
            "Reconstructed voxel size was empty; Acquisition pixel size was used "
            "isotropically for X, Y and Z."
        )
    if voxel_size in (None, ""):
        raise ValueError(
            "Neither Reconstructed voxel size nor Acquisition pixel size is present."
        )

    version = _value(fields, "Software version")
    if version in (None, ""):
        version = "unknown"
        assumptions.append(
            "Reconstruction software version was unavailable; 'unknown' was used."
        )

    reconstruction_date = _value(fields, "Measurement date")
    if reconstruction_date in (None, ""):
        reconstruction_date = source.get("modified_at") or source.get("created_at")
        assumptions.append(
            "Reconstruction date was unavailable; the eLabFTW record timestamp was used."
        )
    elif "T" not in str(reconstruction_date):
        reconstruction_date = f"{reconstruction_date}T00:00:00+00:00"
        assumptions.append(
            "Only the measurement date was available; midnight UTC was used as the "
            "required reconstruction date-time."
        )

    raw_file = _value(fields, "Raw data path")
    if raw_file in (None, ""):
        raw_file = _choose_raw_file(path, sample_name)
        if raw_file:
            assumptions.append(
                "Raw data path was empty; the largest matching non-scout TXRM file "
                "was selected."
            )
        else:
            raw_file = "unknown"
            assumptions.append("Raw data path was unavailable; 'unknown' was used.")

    instrument = _value(fields, "XRM system / instrument")
    source_name = (
        f"XRM system / instrument {instrument}" if instrument else "XRM instrument"
    )
    if not instrument:
        assumptions.append(
            "Instrument identifier was unavailable; 'XRM instrument' was used."
        )

    mapped_parameters = {
        key: _value(fields, key)
        for key in (
            "Objective",
            "Filter",
            "Binning",
            "Tube power",
            "Tube voltage",
            "Source position",
            "Detector position",
            "Exposure time per image",
            "Images per projection",
            "Number of projections",
            "Acquisition notes",
        )
        if _value(fields, key) not in (None, "")
    }
    return XRMMetadata(
        title=str(
            source.get("title") or f"Tomographic reconstruction of {sample_name}"
        ),
        sample_name=sample_name,
        source_type="laboratory X-ray tube",
        source_name=source_name,
        reconstruction_program=str(
            _value(fields, "Reconstruction software") or "unknown"
        ),
        reconstruction_version=str(version),
        reconstruction_date=str(reconstruction_date),
        raw_file=str(raw_file),
        voxel_size_um=float(voxel_size),
        parameters=mapped_parameters,
        assumptions=tuple(assumptions),
    )
