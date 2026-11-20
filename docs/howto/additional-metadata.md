# Supply TIFF stack metadata

TIFF jobs use explicitly assigned eLabFTW JSON and optional supplements.
ZEISS binary exports use the [embedded metadata mapping](../metadata-mapping.md).

## Provide an eLabFTW-style JSON export

The resolver reads exact, case-sensitive labels in
`metadata_decoded.extra_fields`. This small synthetic JSON shows the five-field
case, with orientation supplied as explicit configuration:

```json
{
  "metadata_decoded": {
    "extra_fields": {
      "Source type": {"value": "Fixed Tube X-ray"},
      "Source name": {"value": "Synthetic example tube"},
      "Software version": {"value": "1.0-example"},
      "Reconstruction date": {"value": "2026-08-26T12:00:00+02:00"}
    }
  },
  "xrm_configuration": {
    "image_orientation": {
      "row_axis": "z",
      "column_axis": "x",
      "row_sign": 1,
      "column_sign": 1
    }
  }
}
```

Assign the JSON to the TIFF job with `metadata_file`. This fragment illustrates
the format. The full list of required values depends on the selected target.

| JSON label / location | Resolver key | Expected value |
|---|---|---|
| `Source type` | `source_type` | Source category supported by active NeXus definitions |
| `Source name` | `source_name` | Actual radiation source designation |
| `Reconstruction software` | `reconstruction_program` | Program used to reconstruct |
| `Software version` | `reconstruction_version` | That program's version, as text |
| `Reconstruction date` | `reconstruction_date` | Full date/time, preferably explicit UTC offset |
| `Sample name` | `sample_name` | Measurement's sample identity |
| `Raw data path` | `raw_file` | Actual source acquisition reference |
| `Reconstructed voxel size` | `pixel_size_um` | Positive number plus explicit supported unit |
| `Stage X`, `Stage Y`, `Stage Z` | `stage_x_um`, `stage_y_um`, `stage_z_um` | Number plus explicit length unit |
| Top-level `xrm_configuration.image_orientation` | `image_orientation` | Axis mapping with integer signs |

For example `"Reconstructed voxel size": {"value": 500, "unit": "nm"}` converts
to `pixel_size_um=0.5`. Supported length units include `nm`, `um`, `µm`, `μm`,
`mm`, `cm`, `m`. Not every field uses that same conversion: see
`metadata.read_elabftw_metadata` and the mapping reference for field-specific units.

`xrm_configuration` accepts only `theta`, `image_orientation`, `volume_origin_um`
and `image_key`. Do not place `source_name` or reconstruction keys there. Use the
extra-field labels above or YAML `metadata_supplements` instead. Lab-book free
text and differently named labels are not automatically interpreted. There is no
live eLabFTW API lookup; upload the correct export and referenced metadata.

## CLI supplements JSON

The CLI `--supplements` file is a plain object of resolver keys, **not** an
eLabFTW export and not a NOMAD `data:` envelope. For the same synthetic case,
save `missing-values.json`:

```json
{
  "source_type": "Fixed Tube X-ray",
  "source_name": "Synthetic example tube",
  "reconstruction_version": "1.0-example",
  "reconstruction_date": "2026-08-26T12:00:00+02:00",
  "image_orientation": {
    "row_axis": "z", "column_axis": "x", "row_sign": 1, "column_sign": 1
  }
}
```

```bash
pynx-xrm convert --tiffs scan/layers --metadata scan/measurement.json --supplements missing-values.json --output reconstruction.nxs
```

CLI paths are ordinary paths relative to the shell's current directory (unless
absolute). They do not use NOMAD's upload-root convention. The CLI does not scan
for NOMAD archive YAML or automatically discover sidecars: pass `--metadata`
explicitly as needed.

## Complete synthetic TIFF example

For a runnable miniature stack, use the bundled example's `metadata.json` and
`xrm.archive.yaml`. In that example the metadata include sample, source,
reconstruction program/version/date, raw reference, voxel size, stage coordinates
and `xrm_configuration` for theta, origin and orientation. Its input is in
`layers/` and output is `xrm_example.nxs`. See the
[example README](../reference/example-upload.md) for the exact files.

For a projection TIFF job with three frames, actual measurement configuration
would have the structure below; the angles and positions are **synthetic**:

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
  tiff_directory: projections
  target_definition: NXtomo
  output: _nexus/projections.nxs
  export: true
  metadata_supplements:
    sample_name: "Synthetic projection example"
    theta: [0.0, 45.0, 90.0]
    stage_x_um: 0.0
    stage_y_um: 0.0
    stage_z_um: 0.0
    image_key: [0, 0, 0]
```

Only use measured angles and confirmed coordinates for real data. `image_key`
must have one valid integer per frame. Additional NXDL-required content is
checked against the definitions installed in your environment.

## Dates, orientation and precedence

Use quoted timestamps such as `"2026-08-26T12:00:00+02:00"`. Full timestamps are
required; a calendar date alone is insufficient for reconstruction time. Naive
local timestamps are interpreted in Europe/Berlin; ambiguous or nonexistent DST
times are rejected. The acquisition date, layer timestamp, conversion time and
reconstruction time have different meanings.

For reconstructed volumes, `row_axis: z` and `column_axis: x` are required by the
current model; `row_sign` and `column_sign` must each be integer `1` or `-1`.
Confirm these from the reconstruction/export convention or calibration. They
are not arbitrary switches to suppress errors. A TIFF volume also needs
`volume_origin_um: [x, y, z]`, the first voxel position in the model's sample
frame.

An explicit supplement fills an absent TIFF metadata value. A conflicting
supplement raises an error.
