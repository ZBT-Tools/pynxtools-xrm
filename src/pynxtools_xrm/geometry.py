"""Explicit Berlin timestamps and the global / co-rotating ZEISS stage frames."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

BERLIN = ZoneInfo("Europe/Berlin")
# Columns are native sample basis vectors in the global beam-X frame at theta=0.
SAMPLE_ZERO = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
# Columns are global basis vectors in the NeXus McStas beam-Z / Y-up frame.
GLOBAL_IN_NEXUS = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])


def berlin_timestamp(value):
    """Preserve instants; reject missing times, DST gaps and ambiguous local times."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A complete timestamp including time is required")
    text = value.strip()
    if ":" not in text:
        raise ValueError(f"Timestamp lacks a time: {text}")
    if "/" in text:
        parsed = datetime.strptime(text, "%m/%d/%Y %H:%M:%S.%f")
    else:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(BERLIN).isoformat()
    candidates = []
    for fold in (0, 1):
        candidate = parsed.replace(tzinfo=BERLIN, fold=fold)
        back = candidate.astimezone(timezone.utc).astimezone(BERLIN)
        if back.replace(tzinfo=None) == parsed:
            candidates.append(candidate)
    if not candidates:
        raise ValueError(f"Nonexistent Berlin local time: {text}")
    if len({v.utcoffset() for v in candidates}) > 1:
        raise ValueError(f"Ambiguous Berlin local time; provide UTC offset: {text}")
    return candidates[0].isoformat()


def stage_orientation(theta_degrees):
    theta = np.deg2rad(np.asarray(theta_degrees, dtype=float))
    rotation = np.zeros(theta.shape + (3, 3))
    rotation[..., 0, 0] = rotation[..., 2, 2] = np.cos(theta)
    rotation[..., 0, 2] = np.sin(theta)
    rotation[..., 2, 0] = -np.sin(theta)
    rotation[..., 1, 1] = 1
    return SAMPLE_ZERO @ rotation


def global_stage_position(x, y, z, theta):
    x, y, z, theta = np.broadcast_arrays(x, y, z, theta)
    return np.einsum(
        "...ij,...j->...i", stage_orientation(theta), np.stack((x, y, z), axis=-1)
    )
