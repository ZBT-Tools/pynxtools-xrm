# eLabFTW metadata mapping

The mapping is based on field names and types, not on the example values in
`test_metadata.json`. Every field in the tables is optional unless it is
already required by `NXtomoproc`. Missing optional fields are omitted.

The official application definition remains `NXtomoproc`. The packaged local
extension `NXxrm_tomoproc.nxdl.xml` documents the additional optional fields
and is referenced through `NXentry/definition_local`.

## Standard NeXus base-class fields

| eLabFTW field | NeXus path | Base class | Unit handling |
|---|---|---|---|
| `elabid` | `/entry/entry_identifier` | `NXentry` | n/a |
| `Project` | `/entry/experiment_identifier` | `NXentry` | n/a |
| `Research question` | `/entry/experiment_description` | `NXentry` | n/a |
| `Measurement start` | `/entry/start_time` | `NXentry` | ISO 8601 date-time |
| `Measurement end` | `/entry/end_time` | `NXentry` | ISO 8601 date-time |
| `Tube / tomography time` | `/entry/collection_time` | `NXentry` | source unit required |
| `fullname`, `userid`, `team_name`, `orcid` | `/entry/user/*` | `NXuser` | n/a |
| `Experimenter` | `/entry/experimenter/*` | `NXuser` | n/a |
| `Owner` | `/entry/owner/*` | `NXuser` | n/a |
| `Sample name` | `/entry/sample/name` | `NXsample` | n/a |
| `Type` | `/entry/sample/description` | `NXsample` | n/a |
| `Sample temperature` | `/entry/sample/temperature` | `NXsample` | `°C` is normalized to `degC` |
| `Stage X/Y/Z` | `/entry/sample/stage_x/y/z/value` | `NXpositioner` | source length unit required |
| `Sample preparation` | `/entry/sample/preparation/data` | `NXnote` | n/a |
| `Acquisition notes` | `/entry/notes/data` | `NXnote` | n/a |
| eLabFTW export metadata | `/entry/elabftw/*` | `NXnote` | date-time where applicable |
| `Tube power` | `/entry/instrument/source/power` | `NXsource` | source power unit required |
| `Tube voltage` | `/entry/instrument/source/voltage` | `NXsource` | source voltage unit required |
| `Source position` | `/entry/instrument/source/distance` | `NXsource` | source length unit required |
| `Detector position` | `/entry/instrument/detector/distance` | `NXdetector` | source length unit required |
| `Exposure time per image` | `/entry/instrument/detector/count_time` | `NXdetector` | source time unit required |
| reconstruction fields | `/entry/reconstruction/*` | `NXprocess`, `NXparameters` | field-specific |

## Optional local application fields

Acquisition fields without a more specific standard base-class field are
stored once below `/entry/acquisition` (`NXcollection`). They include
`Objective`, `Filter`, `Binning`, `Measurement mode`, `ROI / scan region`,
`Output format`, projection counts, acquisition pixel size, raw data volume,
measurement quality, sample holder, sample preparation time, HART use, storage
and release flags, repeat/external-request fields, downstream analysis, and
tags.

Reconstruction-specific status and correction settings are stored below
`/entry/reconstruction/parameters`: reconstruction status, ring-artifact
correction, beam-hardening correction, and reconstruction data volume.

File-system provenance is stored below `/entry/data_provenance`
(`NXcollection`). Windows paths describe the acquisition workstation and are
not interpreted as paths inside a NOMAD Oasis.

## No duplicated datasets

- Source power, source voltage, source/detector position, and exposure time are
  only written to their corresponding instrument base classes, not repeated in
  reconstruction parameters.
- If the available metadata only supplies one shared instrument/source name,
  `/entry/instrument/source/name` is a hard link to `/entry/instrument/name`.
- `/entry/data_provenance/raw_data_path` is a hard link to
  `/entry/reconstruction/parameters/raw_file`.
- Equal raw, reconstruction, analysis, or results paths are represented by
  HDF5 hard links. If their values differ in a future record, separate datasets
  are created.
- `/entry/elabftw/identifier_elabftw` is a hard link to
  `/entry/entry_identifier`.
- `NXnote/author` is a hard link to `/entry/user/name`.

## Unit audit

All physically dimensional numeric fields in the supplied field schema have a
unit: stage and component positions, tube power and voltage, temperature,
pixel/voxel size, acquisition and preparation times, exposure time, data
volumes, and beam-hardening correction.

The following fields intentionally have no unit because they are counts or
dimensionless values: `Binning`, `Objective` magnification, `Images per
projection`, `Number of projections`, and `Number of individual measurements`.
For `Objective`, the example schema encodes magnification as text such as
`20x`; a future numeric field should use `units="1"`.

There are no missing physical units in the current schema, but there are three
metadata-quality gaps which units cannot solve:

1. Stage, source, and detector positions do not define their coordinate-system
   origin or sign convention.
2. Local date-times do not include a UTC offset or named time zone.
3. `GB` does not state whether decimal gigabytes or binary gibibytes are meant.

The converter preserves these source facts and does not invent the missing
semantics.
