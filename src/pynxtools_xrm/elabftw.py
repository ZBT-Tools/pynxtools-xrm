"""Semantic eLabFTW fields and native NeXus provenance, without JSON blobs."""

import hashlib
import logging
import re

import h5py
import numpy as np
from pynxtools.dataconverter.helpers import convert_data_dict_path_to_hdf5_path

from pynxtools_xrm.geometry import berlin_timestamp

E = "/ENTRY[entry]"
INSTRUMENT = E + "/INSTRUMENT[instrument]"
S = E + "/SAMPLE[sample]"
D = INSTRUMENT + "/DETECTOR[detector]"
Q = INSTRUMENT + "/SOURCE[source]"
A = E + "/COLLECTION[acquisition]"
P = E + "/COLLECTION[data_provenance]"
R = E + "/reconstruction"

# label: (canonical resolver key, template path, optional profile extension).
FIELDS = {
    "Sample name": ("sample_name", S + "/name", False),
    "Type": ("sample_description", S + "/description", False),
    "Source name": ("source_name", Q + "/name", False),
    "Source type": ("source_type", Q + "/type", False),
    "XRM system / instrument": ("instrument_name", INSTRUMENT + "/name", False),
    "Project": ("experiment_identifier", E + "/experiment_identifier", False),
    "Research question": (
        "experiment_description",
        E + "/experiment_description",
        False,
    ),
    "Owner": ("owner", E + "/USER[owner]/name", False),
    "Experimenter": ("experimenter", E + "/USER[experimenter]/name", False),
    "Tube voltage": ("source_voltage_kv", Q + "/voltage", False),
    "Tube power": ("source_power_w", Q + "/power", False),
    "Exposure time per image": ("exposure_s", D + "/count_time", False),
    "Source position": (
        "source_x_mm",
        Q + "/TRANSFORMATIONS[transformations]/position_x",
        False,
    ),
    "Detector position": (
        "detector_x_mm",
        D + "/TRANSFORMATIONS[transformations]/position_x",
        False,
    ),
    "Stage X": ("stage_x_um", S + "/TRANSFORMATIONS[transformations]/stage_x", False),
    "Stage Y": ("stage_y_um", S + "/TRANSFORMATIONS[transformations]/stage_y", False),
    "Stage Z": ("stage_z_um", S + "/TRANSFORMATIONS[transformations]/stage_z", False),
    "Sample temperature": ("sample_temperature", S + "/temperature", False),
    "Acquisition notes": ("note", E + "/NOTE[notes]/data", False),
    "Sample preparation": ("preparation", S + "/NOTE[preparation]/data", False),
    "Sample preparation time": (
        "sample_preparation_time",
        S + "/COLLECTION[preparation_details]/duration",
        True,
    ),
    "Sample holder / fixture": (
        "sample_holder",
        S + "/COLLECTION[mounting]/description",
        True,
    ),
    "Objective": ("objective", INSTRUMENT + "/COLLECTION[optics]/objective", True),
    "Filter": ("filter", INSTRUMENT + "/FILTER[filter]/description", False),
    "Binning": ("binning", D + "/COLLECTION[readout]/binning", True),
    "Images per projection": (
        "images_per_projection",
        D + "/COLLECTION[readout]/images_per_projection",
        True,
    ),
    "Acquisition pixel size": (
        "object_pixel_size_um",
        D + "/COLLECTION[object_calibration]/pixel_size",
        True,
    ),
    "Reconstructed voxel size": (
        "pixel_size_um",
        E + "/COLLECTION[volume_calibration]/voxel_size",
        True,
    ),
    "Measurement date": ("measurement_date", A + "/measurement_date", True),
    "Measurement start": ("start_time", A + "/start_time", True),
    "Measurement end": ("end_time", A + "/end_time", True),
    "Tube / tomography time": ("collection_time", E + "/collection_time", False),
    "Number of projections": (
        "number_of_projections",
        A + "/number_of_projections",
        True,
    ),
    "Number of individual measurements": (
        "number_of_measurements",
        A + "/number_of_measurements",
        True,
    ),
    "Measurement mode": ("measurement_mode", A + "/measurement_mode", True),
    "ROI / scan region": ("roi", A + "/roi_description", True),
    "HART used": ("hart_used", A + "/hart_used", True),
    "Measurement quality": ("measurement_quality", A + "/measurement_quality", True),
    "Raw data volume": ("raw_data_volume", P + "/raw_data_volume", True),
    "Storage location": ("storage_location", P + "/storage_location", True),
    "Results storage path": ("results_storage_path", P + "/results_storage_path", True),
    "Raw data path": ("raw_file", P + "/raw_file", True),
    "Analysis path": ("analysis_path", P + "/analysis_path", True),
    "Reconstruction path": ("reconstruction_path", P + "/reconstruction_path", True),
    "Output format": ("output_format", P + "/output_format", True),
    "Released for analysis": (
        "released_for_analysis",
        P + "/released_for_analysis",
        True,
    ),
    "External measurement request": (
        "external_measurement_request",
        P + "/external_measurement_request",
        True,
    ),
    "Repeat measurement required": (
        "repeat_measurement_required",
        P + "/repeat_measurement_required",
        True,
    ),
    "Reason for repeat / limitation": ("repeat_reason", P + "/repeat_reason", True),
    "Planned downstream analysis": (
        "planned_downstream_analysis",
        P + "/planned_downstream_analysis",
        True,
    ),
    "Reconstruction software": ("reconstruction_program", R + "/program", False),
    "Software version": ("reconstruction_version", R + "/version", False),
    "Reconstruction date": ("reconstruction_date", R + "/date", False),
    "Reconstruction status": (
        "reconstruction_status",
        R + "/COLLECTION[processing_details]/status",
        True,
    ),
    "Ring artifact correction": (
        "ring_artifact_correction",
        R + "/COLLECTION[processing_details]/ring_artifact_correction",
        True,
    ),
    "Beam hardening correction": (
        "beam_hardening_correction",
        R + "/COLLECTION[processing_details]/beam_hardening_correction",
        True,
    ),
    "Reconstruction data volume": (
        "reconstruction_data_volume",
        P + "/reconstruction_data_volume",
        True,
    ),
}

TOP_FIELDS = {
    "title": E + "/title",
    "elabid": E + "/entry_identifier",
    "fullname": E + "/USER[user]/name",
    "userid": E + "/USER[user]/facility_user_id",
    "team_name": E + "/USER[user]/affiliation",
    "orcid": E + "/USER[user]/ORCID",
    "firstname": P + "/COLLECTION[eln_record]/author_first_name",
    "lastname": P + "/COLLECTION[eln_record]/author_last_name",
    "id": P + "/COLLECTION[eln_record]/record_id",
    "team": P + "/COLLECTION[eln_record]/team_id",
    "sharelink": P + "/COLLECTION[eln_record]/url",
    "created_at": P + "/COLLECTION[eln_record]/created_at",
    "modified_at": P + "/COLLECTION[eln_record]/modified_at",
    "created_from_id": P + "/COLLECTION[eln_record]/template_id",
    "created_from_type_human": P + "/COLLECTION[eln_record]/template_type",
    "status_title": P + "/COLLECTION[eln_record]/status",
    "type": P + "/COLLECTION[eln_record]/record_type",
    "custom_id": P + "/COLLECTION[eln_record]/custom_id",
    "timestamped_at": P + "/COLLECTION[eln_record]/timestamped_at",
    "last_signed_at": P + "/COLLECTION[eln_record]/last_signed_at",
    "tags": P + "/keywords",
}


def populated(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    return not isinstance(value, (dict, list, tuple)) or bool(value)


def nexus_value(value):
    """Keep scalars numeric/bool and selections as native arrays."""
    if isinstance(value, (list, tuple)):
        if all(isinstance(v, str) for v in value):
            return np.asarray(value, dtype=h5py.string_dtype("utf-8"))
        return np.asarray(value)
    return value


def _name(value):
    name = str(value)
    if re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", name):
        return name
    return "item_" + hashlib.sha256(name.encode()).hexdigest()[:16]


def write_structured(t, prefix, payload):
    """Write audit dictionaries as NXcollection groups, not serialized text."""
    t[prefix + "/@NX_class"] = "NXcollection"
    items = (
        payload.items()
        if isinstance(payload, dict)
        else ((f"item_{i:04d}", v) for i, v in enumerate(payload))
    )
    for key, value in items:
        if value is None:
            continue
        path = prefix + "/" + _name(key)
        if isinstance(value, dict) or (
            isinstance(value, list) and any(isinstance(v, dict) for v in value)
        ):
            write_structured(t, path, value)
        else:
            t[path] = nexus_value(value)


def field_path(label, target):
    key, path, extension = FIELDS[label]
    if label in {"Measurement start", "Measurement end"} and target != "NXtomoproc":
        path, extension = E + "/" + key, False
    if path.startswith(R) and target != "NXtomoproc":
        path = (
            P
            + "/COLLECTION[related_reconstruction]/"
            + key.removeprefix("reconstruction_")
        )
        extension = True
    if label == "Reconstructed voxel size" and target != "NXtomoproc":
        key = "declared_reconstructed_voxel_size_um"
        path = P + "/declared_reconstructed_voxel_size"
    return key, path, extension


def map_effective_fields(t, values, target):
    """Use one semantic registry for image, recipe and ELN resolved values."""
    excluded = {
        "Source position",
        "Detector position",
        "Stage X",
        "Stage Y",
        "Stage Z",
        "Acquisition notes",
        "Sample preparation",
    }
    for label in FIELDS:
        key, path, _ = field_path(label, target)
        if key not in values or label in excluded:
            continue
        t.setdefault(path, nexus_value(values[key]))
        if key + "_unit" in values:
            t[path + "/@units"] = values[key + "_unit"]
        if label in {"Acquisition pixel size", "Reconstructed voxel size"}:
            t[path + "/@units"] = "um"
    if "instrument_identifier" in values:
        t[INSTRUMENT + "/COLLECTION[identifiers]/elabftw_item_id"] = values[
            "instrument_identifier"
        ]


def map_elabftw(t, meta, target):
    """Distribute values and report every source field without domain mapping."""
    raw = meta.sources.get("elabftw")
    if raw is None:
        return []
    rows = []
    v = meta.values

    def report(
        source, path="", status="not_assigned", reason="No verified domain mapping"
    ):
        rows.append(
            dict(
                source_path=source,
                target_path=convert_data_dict_path_to_hdf5_path(path) if path else "",
                status=status,
                reason=reason,
            )
        )

    geometry_labels = {
        "Source position",
        "Detector position",
        "Stage X",
        "Stage Y",
        "Stage Z",
        "Acquisition notes",
        "Sample preparation",
    }
    for label, item in raw.get("metadata_decoded", {}).get("extra_fields", {}).items():
        source = "metadata_decoded/extra_fields/" + label
        value = item.get("value") if isinstance(item, dict) else item
        if not populated(value):
            report(
                source,
                status="empty",
                reason="No value supplied; no dataset fabricated",
            )
        elif label not in FIELDS:
            report(source)
            write_structured(
                t,
                E + "/COLLECTION[unmapped_metadata]/" + _name(label),
                {
                    "source_field": label,
                    "value": value,
                    "unit": item.get("unit") if isinstance(item, dict) else None,
                    "reason": "No verified domain mapping",
                },
            )
        else:
            key, path, extension = field_path(label, target)
            if (
                key == "instrument_name"
                and "instrument_identifier" in v
                and key not in v
            ):
                path = INSTRUMENT + "/COLLECTION[identifiers]/elabftw_item_id"
                value = v["instrument_identifier"]
            else:
                value = v.get(key)
            if value is not None:
                if path not in t and label not in geometry_labels:
                    t[path] = nexus_value(value)
                if path in t and key + "_unit" in v:
                    t[path + "/@units"] = v[key + "_unit"]
                if label in {"Acquisition pixel size", "Reconstructed voxel size"}:
                    t[path + "/@units"] = "um"
                superseded = any(
                    c["field"] == key
                    and c["other_source"] == meta.origins.get("_elabftw_source")
                    for c in meta.conflicts
                )
                report(
                    source,
                    path,
                    "superseded" if superseded else "mapped",
                    "Higher-priority image/RCP value selected; ELN alternative retained in conflicts"
                    if superseded
                    else (
                        "Optional base-class extension"
                        if extension
                        else "Standard NeXus base-class field"
                    ),
                )
        if isinstance(item, dict) and set(item) - {"value", "unit"}:
            report(
                source + "/{form_configuration}",
                status="not_assigned",
                reason="ELN form widget, order, options and validation settings; not measurement metadata",
            )

    for key, value in raw.items():
        if not populated(value):
            report(key, status="empty", reason="No value supplied")
        elif key in TOP_FIELDS:
            path = TOP_FIELDS[key]
            if key in {"created_at", "modified_at", "timestamped_at", "last_signed_at"}:
                value = berlin_timestamp(value)
            if key == "tags":
                value = (
                    [tag for tag in value.split("|") if tag]
                    if isinstance(value, str)
                    else value
                )
            t.setdefault(path, nexus_value(value))
            report(
                key,
                path,
                "mapped",
                "ELN record provenance"
                if path.startswith(P)
                else "Standard NeXus field",
            )
        elif key in {"body", "body_html"}:
            path = E + "/experiment_documentation"
            duplicate = key == "body" and value == raw.get("body_html")
            if key == "body" and raw.get("body_html") and not duplicate:
                path = E + "/NOTE[eln_body]"
            body = value
            t[path + "/type"] = "text/html"
            t[path + "/data"] = np.bytes_(body.encode("utf-8"))
            report(
                key,
                path + "/data",
                "mapped" if not duplicate else "redundant",
                "Original experiment documentation; identical alternative is not duplicated",
            )
        elif key == "date":
            path = A + "/measurement_date"
            t.setdefault(path, str(value))
            report(
                key, path, "mapped", "Calendar date retained without inventing a time"
            )
        elif key == "items_links":
            path = P + "/COLLECTION[linked_records]"
            write_structured(t, path, value)
            report(
                key,
                path,
                "mapped",
                "Linked ELN records; instrument name resolved only for matching identifier",
            )
        elif key in {"metadata", "metadata_decoded"}:
            report(
                key + "/{form_configuration}",
                status="not_assigned",
                reason="Form definition and duplicate serialization; populated values are mapped individually",
            )
        elif key.startswith(("canread", "canwrite", "access_key")):
            report(
                key,
                reason="ELN access control; no NeXus measurement meaning; permissions are not transferred",
            )
        else:
            report(
                key,
                reason="ELN administration, editing history, UI state or unverified record relation; not a physical measurement field",
            )
    columns = {
        key: [row[key] for row in rows]
        for key in ("source_path", "target_path", "status", "reason")
    }
    write_structured(t, E + "/COLLECTION[metadata_provenance]/elabftw_mapping", columns)
    unassigned = [r["source_path"] for r in rows if r["status"] == "not_assigned"]
    if unassigned:
        logging.getLogger("pynxtools_xrm").warning(
            "%d eLabFTW fields/configuration entries without domain mapping; see /entry/metadata_provenance/elabftw_mapping",
            len(unassigned),
        )
    return rows
