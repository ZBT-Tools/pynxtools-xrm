"""Small target mappings; metadata uses pynxtools' standard template paths."""

import json
from datetime import datetime
from importlib.metadata import version

import numpy as np

from pynxtools_xrm.elabftw import (
    map_effective_fields,
    map_elabftw,
    nexus_value,
    write_structured,
)
from pynxtools_xrm.errors import MissingRequiredMetadata
from pynxtools_xrm.geometry import BERLIN, GLOBAL_IN_NEXUS, global_stage_position
from pynxtools_xrm.metadata import json_value

E = "/ENTRY[entry]"
INSTRUMENT = E + "/INSTRUMENT[instrument]"
S = E + "/SAMPLE[sample]"
D = INSTRUMENT + "/DETECTOR[detector]"
Q = INSTRUMENT + "/SOURCE[source]"


def frame_array(value, count, field):
    a = np.asarray(value, dtype=float)
    if (
        count == 1
        and a.ndim == 1
        and a.size > 1
        and np.allclose(a, a[0], rtol=0, atol=1e-6)
    ):
        a = a[:1]
    if a.size == 1:
        a = np.full(count, a.item())
    if a.shape != (count,) or not np.all(np.isfinite(a)):
        raise ValueError(f"Invalid {field}: expected {count} finite values")
    return a


def add_note(t, name, payload):
    prefix = E + f"/NOTE[{name}]"
    t[prefix + "/type"] = "application/json"
    t[prefix + "/data"] = np.bytes_(
        json.dumps(
            payload, ensure_ascii=True, default=json_value, allow_nan=False
        ).encode("utf-8")
    )


def _transform(t, prefix, name, value, kind, vector, depends, unit):  # noqa: PLR0917
    path = prefix + "/" + name
    t[path] = value
    for key, v in {
        "transformation_type": kind,
        "vector": np.asarray(vector, dtype=float),
        "depends_on": depends,
        "units": unit,
        "offset": np.zeros(3),
        "offset_units": "m",
    }.items():
        t[path + "/@" + key] = v


def geometry_template(t, v, source, target):
    count = source.frame_count if target == "NXtomo" else 1
    theta = frame_array(v["theta"], source.frame_count, "theta")
    if target != "NXtomo":
        if not np.allclose(theta, theta[0], rtol=0, atol=1e-6):
            raise ValueError("A reconstructed volume requires one orientation")
        theta = theta[:1]
    native = [frame_array(v[f"stage_{a}_um"], count, f"stage_{a}_um") for a in "xyz"]
    frame = E + "/COORDINATE_SYSTEM[global_frame]"
    t[frame + "/@NX_class"] = "NXcoordinate_system"
    t[frame + "/type"] = "cartesian"
    t[frame + "/origin"] = "Stage zero; global X source-to-detector, Y down"
    t[frame + "/depends_on"] = "."
    for i, a in enumerate("xyz"):
        t[frame + "/" + a] = GLOBAL_IN_NEXUS[:, i]
        t[frame + "/" + a + "/@units"] = "m"
    p = S + "/TRANSFORMATIONS[transformations]"
    _transform(
        t, p, "sample_zero", 90.0, "rotation", [0, 1, 0], "/entry/global_frame", "deg"
    )
    _transform(
        t,
        p,
        "theta",
        theta,
        "rotation",
        [0, 1, 0],
        "/entry/sample/transformations/sample_zero",
        "deg",
    )
    dep = "/entry/sample/transformations/theta"
    for i, a in enumerate("xyz"):
        _transform(
            t, p, "stage_" + a, native[i], "translation", np.eye(3)[i], dep, "um"
        )
        dep = "/entry/sample/transformations/stage_" + a
    t[S + "/depends_on"] = dep
    frame = E + "/COORDINATE_SYSTEM[sample_frame]"
    t[frame + "/@NX_class"] = "NXcoordinate_system"
    t[frame + "/type"] = "cartesian"
    t[frame + "/origin"] = "Native stage translations in co-rotating sample basis"
    t[frame + "/depends_on"] = dep
    for i, a in enumerate("xyz"):
        t[frame + "/" + a] = np.eye(3)[:, i]
        t[frame + "/" + a + "/@units"] = "m"
    if target == "NXtomo":
        global_positions = global_stage_position(*native, theta)
        for i, a in enumerate("xyz"):
            t[S + f"/{a}_translation"] = global_positions[:, i]
            t[S + f"/{a}_translation/@units"] = "um"
    for key, group in (("source_x_mm", Q), ("detector_x_mm", D)):
        if key in v:
            values = frame_array(v[key], count, key)
            if (key == "source_x_mm" and np.any(values >= 0)) or (
                key == "detector_x_mm" and np.any(values <= 0)
            ):
                raise ValueError(
                    f"{key} conflicts with confirmed global beam-X geometry"
                )
            p = group + "/TRANSFORMATIONS[transformations]"
            _transform(
                t,
                p,
                "position_x",
                values,
                "translation",
                [1, 0, 0],
                "/entry/global_frame",
                "mm",
            )
            t[group + "/depends_on"] = (
                "/entry/instrument/"
                + ("source" if group == Q else "detector")
                + "/transformations/position_x"
            )


def volume_axes(source, meta):
    v = meta.values
    meta.require("NXtomoproc", ["image_orientation"])
    orientation = v["image_orientation"]
    if orientation not in (
        {"row_axis": "z", "column_axis": "x", "row_sign": 1, "column_sign": 1},
        {"row_axis": "z", "column_axis": "x", "row_sign": -1, "column_sign": 1},
        {"row_axis": "z", "column_axis": "x", "row_sign": 1, "column_sign": -1},
        {"row_axis": "z", "column_axis": "x", "row_sign": -1, "column_sign": -1},
    ):
        raise ValueError(
            "image_orientation must explicitly give row_axis=z, column_axis=x and row_sign/column_sign +/-1"
        )
    h, w = source.image_shape
    shape = (w, source.frame_count, h)
    spacing = v["pixel_size_um"]
    if source.kind == ".txm":
        y = np.asarray(v.get("slice_y_um"), dtype=float)
        if y.shape != (source.frame_count,) or not np.all(np.isfinite(y)):
            raise MissingRequiredMetadata("NXtomoproc", ["slice_y_um"])
        if len(y) > 1 and not np.allclose(
            np.abs(np.diff(y)), spacing, atol=max(spacing * 1e-5, 0.002), rtol=0
        ):
            raise ValueError("Slice spacing conflicts with cubic voxel calibration")
        x = (np.arange(w) - (w - 1) / 2) * spacing * orientation["column_sign"]
        z = (np.arange(h) - (h - 1) / 2) * spacing * orientation["row_sign"]
        y = y - float(v["stage_y_um"])
    else:
        meta.require("NXtomoproc", ["volume_origin_um"])
        origin = np.asarray(v["volume_origin_um"], dtype=float)
        if origin.shape != (3,) or not np.all(np.isfinite(origin)):
            raise ValueError(
                "volume_origin_um must give three finite first-voxel coordinates"
            )
        x = origin[0] + np.arange(w) * spacing * orientation["column_sign"]
        y = origin[1] + np.arange(source.frame_count) * spacing
        z = origin[2] + np.arange(h) * spacing * orientation["row_sign"]
    return shape, (x, y, z)


def build_template(source, meta, target):
    v = meta.values
    required = ["sample_name", "theta", "stage_x_um", "stage_y_um", "stage_z_um"]
    if target == "NXtomoproc":
        required += [
            "source_type",
            "source_name",
            "reconstruction_program",
            "reconstruction_version",
            "reconstruction_date",
            "raw_file",
            "pixel_size_um",
            "image_orientation",
        ]
    elif target == "NXxrm_image":
        required += ["pixel_size_um"]
    elif target == "NXtomo":
        if not np.issubdtype(source.dtype, np.integer):
            raise ValueError(
                "Pinned NXtomo requires integer primary images; no implicit float cast is allowed"
            )
    else:
        raise ValueError(f"Unsupported application definition: {target}")
    meta.require(target, required)
    t = {
        E + "/definition": target,
        E + "/title": str(v["title"]),
        S + "/name": str(v["sample_name"]),
        Q + "/probe": "x-ray",
        D + "/layout": "area",
        D + "/type": "planar area detector",
    }
    for k, path in {
        "source_name": Q + "/name",
        "source_type": Q + "/type",
        "instrument_name": INSTRUMENT + "/name",
        "camera_name": D + "/description",
        "camera_serial": D + "/serial_number",
        "sample_description": S + "/description",
        "entry_identifier": E + "/entry_identifier",
        "experiment_identifier": E + "/experiment_identifier",
        "experiment_description": E + "/experiment_description",
    }.items():
        if k in v:
            t[path] = nexus_value(v[k])
    for k, path, unit in (
        ("source_voltage_kv", Q + "/voltage", "kV"),
        ("source_current_ua", Q + "/current", "uA"),
        ("source_power_w", Q + "/power", "W"),
        ("exposure_s", D + "/count_time", "s"),
    ):
        if k in v:
            t[path], t[path + "/@units"] = v[k], unit
    for k, path in (
        ("sample_temperature", S + "/temperature"),
        ("collection_time", E + "/collection_time"),
    ):
        if k in v:
            meta.require(target, [k + "_unit"])
            t[path], t[path + "/@units"] = float(v[k]), v[k + "_unit"]
    for k in ("start_time", "end_time"):
        if k in v and target != "NXtomoproc":
            t[E + "/" + k] = v[k]
    if "frame_times" in v and target != "NXtomoproc":
        times = v["frame_times"]
        t[E + "/start_time"] = times[0]
        # The last recorded frame timestamp is not necessarily exposure completion.
    for user_key, group in (
        ("author", "user"),
        ("experimenter", "experimenter"),
        ("owner", "owner"),
    ):
        if user_key in v:
            t[E + f"/USER[{group}]/name"] = str(v[user_key])
            t[E + f"/USER[{group}]/name/@target"] = f"/entry/{group}/name"
    for key, field in {
        "author_affiliation": "affiliation",
        "author_orcid": "ORCID",
        "author_id": "facility_user_id",
    }.items():
        if "author" in v and key in v:
            t[E + "/USER[user]/" + field] = str(v[key])
    for key, name in (("note", "notes"), ("preparation", "preparation")):
        if key in v:
            p = (
                S + "/NOTE[preparation]"
                if name == "preparation"
                else E + "/NOTE[notes]"
            )
            text = (
                "; ".join(map(str, v[key])) if isinstance(v[key], list) else str(v[key])
            )
            t[p + "/data"] = np.bytes_(text.encode("utf-8"))
            t[p + "/type"] = "text/plain"
            if "author" in v:
                t[p + "/author"] = {"link": "/entry/user/name"}
    geometry_template(t, v, source, target)
    if target == "NXtomo":
        n, (h, w) = source.frame_count, source.image_shape
        t[S + "/rotation_angle"] = frame_array(v["theta"], n, "theta")
        t[S + "/rotation_angle/@units"] = "deg"
        t[S + "/rotation_angle/@target"] = "/entry/sample/rotation_angle"
        if source.kind == ".tiff":
            meta.require(target, ["image_key"])
            keys = np.asarray(v["image_key"])
            if (
                keys.shape != (n,)
                or not np.issubdtype(keys.dtype, np.integer)
                or not np.all(np.isin(keys, [0, 1, 2, 3]))
            ):
                raise ValueError(
                    "image_key must give one integer role (0..3) per frame"
                )
        else:
            keys = np.zeros(n, dtype=np.int32)
        t[D + "/image_key"] = keys
        t[D + "/image_key/@target"] = "/entry/instrument/detector/image_key"
        for name, link in (
            ("data", "/entry/instrument/detector/data"),
            ("rotation_angle", "/entry/sample/rotation_angle"),
            ("image_key", "/entry/instrument/detector/image_key"),
        ):
            t[E + "/data/" + name] = {"link": link}
        shape, dataset = (n, w, h), "/entry/instrument/detector/data"
        t[E + "/data/@axes"] = np.asarray(["rotation_angle", ".", "."], dtype="S")
        t[E + "/data/@signal"] = "data"
    elif target == "NXtomoproc":
        shape, axes = volume_axes(source, meta)
        for name, axis in zip("xyz", axes, strict=True):
            t[E + "/data/" + name], t[E + "/data/" + name + "/@units"] = axis, "um"
        t[E + "/data/@axes"] = np.asarray(list("xyz"), dtype="S")
        t[E + "/data/@signal"] = "data"
        for key in ("program", "version", "date"):
            t[E + "/reconstruction/" + key] = v["reconstruction_" + key]
        t[E + "/reconstruction/parameters/raw_file"] = str(v["raw_file"])
        dataset = "/entry/data/data"
    else:
        h, w = source.image_shape
        shape, dataset = (h, w), "/entry/instrument/detector/data"
        p = E + "/image/image_2d"
        t[p + "/intensity"] = {"link": dataset}
        t[p + "/@signal"] = "intensity"
        t[p + "/@axes"] = np.asarray(["axis_j", "axis_i"], dtype="S")
        for name, length in (("axis_j", h), ("axis_i", w)):
            t[p + "/" + name] = np.arange(length, dtype=float) * v["pixel_size_um"]
            t[p + "/" + name + "/@units"] = "um"
        t[p + "/@interpretation"] = "image"
    p = E + "/PROCESS[conversion]"
    t[p + "/program"] = "pynxtools-xrm"
    t[p + "/version"] = version("pynxtools-xrm")
    t[p + "/date"] = datetime.now(BERLIN).isoformat()
    # Generic NXparameters/PARAMETER is numeric in the pinned schema. Only
    # the local single-image application declares this string explicitly.
    if target == "NXxrm_image":
        t[p + "/PARAMETERS[parameters]/source_file"] = str(source.path)
    map_effective_fields(t, v, target)
    write_structured(
        t,
        E + "/COLLECTION[metadata_provenance]",
        {
            "source_file": str(source.path),
            "origins": meta.origins,
            "lower_priority_conflicts": meta.conflicts,
            "values": v,
        },
    )
    map_elabftw(t, meta, target)
    if source.raw_metadata:
        add_note(
            t,
            "zeiss_metadata",
            {"path": str(source.path), "streams_base64": source.raw_metadata},
        )
    for name, payload in meta.sources.items():
        if name != "elabftw":
            add_note(t, name, payload)
    return t, shape, dataset
