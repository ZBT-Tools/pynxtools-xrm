"""Translate the eLabFTW JSON export into NXtomoproc metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UserMetadata:
    """Metadata for one NXuser group."""

    group_name: str
    name: str
    role: str | None = None
    affiliation: str | None = None
    facility_user_id: str | None = None
    orcid: str | None = None


@dataclass(frozen=True)
class MetadataValue:
    """A scalar NeXus value and its optional physical unit."""

    value: Any
    unit: str | None = None


@dataclass(frozen=True)
class XRMMetadata:
    title: str
    entry_identifier: str | None
    experiment_identifier: str | None
    experiment_description: str | None
    start_time: str | None
    end_time: str | None
    collection_time: MetadataValue | None
    sample_name: str
    sample_description: str | None
    sample_temperature: MetadataValue | None
    sample_positioners: dict[str, MetadataValue]
    instrument_name: str
    source_type: str
    source_name: str
    source_distance: float | None
    source_distance_unit: str | None
    source_power: float | None
    source_power_unit: str | None
    source_voltage: float | None
    source_voltage_unit: str | None
    detector_distance: float | None
    detector_distance_unit: str | None
    detector_count_time: float | None
    detector_count_time_unit: str | None
    users: tuple[UserMetadata, ...]
    reconstruction_program: str
    reconstruction_version: str
    reconstruction_date: str
    raw_file: str
    voxel_size_um: float
    acquisition: dict[str, MetadataValue]
    reconstruction_parameters: dict[str, MetadataValue]
    provenance: dict[str, MetadataValue]
    acquisition_note: str | None
    sample_preparation: str | None
    elabftw_created_at: str | None
    elabftw_file_name: str
    assumptions: tuple[str, ...]


def _value(fields: dict[str, Any], name: str, default: Any = None) -> Any:
    item = fields.get(name, default)
    return item.get("value", default) if isinstance(item, dict) else item


def _unit(fields: dict[str, Any], name: str) -> str | None:
    item = fields.get(name)
    if not isinstance(item, dict):
        return None
    unit = item.get("unit")
    if unit in (None, ""):
        return None
    return {
        "µm": "um",
        "μm": "um",
        "°C": "degC",
        "h": "hour",
        "min": "minute",
        "s": "second",
    }.get(str(unit), str(unit))


def _optional_float(fields: dict[str, Any], name: str) -> float | None:
    value = _value(fields, name)
    return None if value in (None, "") else float(value)


def _optional_text(fields: dict[str, Any], name: str) -> str | None:
    value = _value(fields, name)
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def _metadata_value(
    fields: dict[str, Any], name: str, *, numeric: bool = False
) -> MetadataValue | None:
    value = _value(fields, name)
    if value in (None, "", []):
        return None
    if numeric:
        value = float(value)
    elif isinstance(value, list):
        value = "; ".join(str(item) for item in value)
    return MetadataValue(value=value, unit=_unit(fields, name))


def _collect_fields(
    fields: dict[str, Any], mapping: dict[str, tuple[str, bool]]
) -> dict[str, MetadataValue]:
    result: dict[str, MetadataValue] = {}
    for nexus_name, (source_name, numeric) in mapping.items():
        value = _metadata_value(fields, source_name, numeric=numeric)
        if value is not None:
            result[nexus_name] = value
    return result


def _iso_datetime(
    value: Any,
    field_name: str,
    assumptions: list[str],
) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).replace(" ", "T")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
        assumptions.append(
            f"{field_name} had no timezone; UTC was used to produce a valid "
            "NX_DATE_TIME value."
        )
    return parsed.isoformat()


def _read_users(
    source: dict[str, Any], fields: dict[str, Any]
) -> tuple[UserMetadata, ...]:
    users: list[UserMetadata] = []
    author = source.get("fullname")
    if author:
        users.append(
            UserMetadata(
                group_name="user",
                name=str(author),
                role="eLabFTW record author",
                affiliation=(
                    str(source["team_name"]) if source.get("team_name") else None
                ),
                facility_user_id=(
                    str(source["userid"]) if source.get("userid") is not None else None
                ),
                orcid=str(source["orcid"]) if source.get("orcid") else None,
            )
        )

    experimenter = _value(fields, "Experimenter")
    if experimenter and str(experimenter) != str(author):
        users.append(
            UserMetadata(
                group_name="experimenter",
                name=str(experimenter),
                role="experimenter",
            )
        )
    owner = _value(fields, "Owner")
    if owner and str(owner) not in {str(author), str(experimenter)}:
        users.append(
            UserMetadata(
                group_name="owner",
                name=str(owner),
                role="data owner",
            )
        )
    return tuple(users)


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

    reconstruction_date_source = _value(fields, "Measurement date")
    if reconstruction_date_source in (None, ""):
        reconstruction_date_source = source.get("modified_at") or source.get(
            "created_at"
        )
        assumptions.append(
            "Reconstruction date was unavailable; the eLabFTW record timestamp was used."
        )
    if reconstruction_date_source in (None, ""):
        reconstruction_date_source = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        assumptions.append(
            "No reconstruction or eLabFTW timestamp was available; the metadata "
            "file modification time was used."
        )
    reconstruction_date = _iso_datetime(
        reconstruction_date_source, "Measurement date", assumptions
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
    instrument_name = (
        f"XRM system / instrument {instrument}" if instrument else "XRM instrument"
    )
    if not instrument:
        assumptions.append(
            "Instrument identifier was unavailable; 'XRM instrument' was used."
        )

    acquisition = _collect_fields(
        fields,
        {
            "objective": ("Objective", False),
            "filter": ("Filter", False),
            "binning": ("Binning", False),
            "measurement_mode": ("Measurement mode", False),
            "roi": ("ROI / scan region", False),
            "output_format": ("Output format", False),
            "images_per_projection": ("Images per projection", True),
            "number_of_projections": ("Number of projections", True),
            "number_of_measurements": (
                "Number of individual measurements",
                True,
            ),
            "acquisition_pixel_size": ("Acquisition pixel size", True),
            "raw_data_volume": ("Raw data volume", True),
            "measurement_quality": ("Measurement quality", False),
            "sample_holder": ("Sample holder / fixture", False),
            "sample_preparation_time": ("Sample preparation time", True),
            "hart_used": ("HART used", False),
            "storage_location": ("Storage location", False),
            "released_for_analysis": ("Released for analysis", False),
            "external_measurement_request": (
                "External measurement request",
                False,
            ),
            "repeat_measurement_required": (
                "Repeat measurement required",
                False,
            ),
            "repeat_reason": ("Reason for repeat / limitation", False),
            "planned_downstream_analysis": (
                "Planned downstream analysis",
                False,
            ),
        },
    )
    if source.get("tags"):
        acquisition["tags"] = MetadataValue(str(source["tags"]))

    reconstruction_parameters = _collect_fields(
        fields,
        {
            "reconstruction_status": ("Reconstruction status", False),
            "ring_artifact_correction": ("Ring artifact correction", False),
            "beam_hardening_correction": ("Beam hardening correction", True),
            "reconstruction_data_volume": ("Reconstruction data volume", True),
        },
    )
    provenance = _collect_fields(
        fields,
        {
            "raw_data_path": ("Raw data path", False),
            "reconstruction_path": ("Reconstruction path", False),
            "analysis_path": ("Analysis path", False),
            "results_storage_path": ("Results storage path", False),
        },
    )
    for name, value in {
        "elabftw_url": source.get("sharelink"),
        "elabftw_record_id": source.get("id"),
        "elabftw_status": source.get("status_title"),
        "elabftw_modified_at": _iso_datetime(
            source.get("modified_at"), "eLabFTW modified_at", assumptions
        ),
        "elabftw_template_id": source.get("created_from_id"),
        "elabftw_template_type": source.get("created_from_type_human"),
        "elabftw_timestamped_at": _iso_datetime(
            source.get("timestamped_at"), "eLabFTW timestamped_at", assumptions
        ),
    }.items():
        if value not in (None, ""):
            provenance[name] = MetadataValue(value)

    sample_positioners = _collect_fields(
        fields,
        {
            "stage_x": ("Stage X", True),
            "stage_y": ("Stage Y", True),
            "stage_z": ("Stage Z", True),
        },
    )
    assumptions.append(
        "Detector layout was inferred as 'area' from the TIFF image acquisition."
    )
    if _value(fields, "Source position") not in (None, "") or _value(
        fields, "Detector position"
    ) not in (None, ""):
        assumptions.append(
            "Source and detector positions were interpreted as signed distances "
            "from the sample center."
        )
    return XRMMetadata(
        title=str(
            source.get("title") or f"Tomographic reconstruction of {sample_name}"
        ),
        entry_identifier=(str(source["elabid"]) if source.get("elabid") else None),
        experiment_identifier=_optional_text(fields, "Project"),
        experiment_description=_optional_text(fields, "Research question"),
        start_time=_iso_datetime(
            _value(fields, "Measurement start"), "Measurement start", assumptions
        ),
        end_time=_iso_datetime(
            _value(fields, "Measurement end"), "Measurement end", assumptions
        ),
        collection_time=_metadata_value(fields, "Tube / tomography time", numeric=True),
        sample_name=sample_name,
        sample_description=(
            str(_value(fields, "Type")) if _value(fields, "Type") else None
        ),
        sample_temperature=_metadata_value(fields, "Sample temperature", numeric=True),
        sample_positioners=sample_positioners,
        instrument_name=instrument_name,
        source_type="Fixed Tube X-ray",
        source_name=instrument_name,
        source_distance=_optional_float(fields, "Source position"),
        source_distance_unit=_unit(fields, "Source position"),
        source_power=_optional_float(fields, "Tube power"),
        source_power_unit=_unit(fields, "Tube power"),
        source_voltage=_optional_float(fields, "Tube voltage"),
        source_voltage_unit=_unit(fields, "Tube voltage"),
        detector_distance=_optional_float(fields, "Detector position"),
        detector_distance_unit=_unit(fields, "Detector position"),
        detector_count_time=_optional_float(fields, "Exposure time per image"),
        detector_count_time_unit=_unit(fields, "Exposure time per image"),
        users=_read_users(source, fields),
        reconstruction_program=str(
            _value(fields, "Reconstruction software") or "unknown"
        ),
        reconstruction_version=str(version),
        reconstruction_date=str(reconstruction_date),
        raw_file=str(raw_file),
        voxel_size_um=float(voxel_size),
        acquisition=acquisition,
        reconstruction_parameters=reconstruction_parameters,
        provenance=provenance,
        acquisition_note=_optional_text(fields, "Acquisition notes"),
        sample_preparation=_optional_text(fields, "Sample preparation"),
        elabftw_created_at=_iso_datetime(
            source.get("created_at"), "eLabFTW created_at", assumptions
        ),
        elabftw_file_name=path.name,
        assumptions=tuple(assumptions),
    )
