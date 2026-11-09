# Supply additional metadata

The converter merges image headers, associated recipe metadata, an assigned
eLabFTW JSON export and explicit supplements. Supplements fill missing values;
they must not replace values already supplied by the other sources. Preserve
real measurement values rather than making conversion succeed with placeholders.

## Which values are required?

All targets require a sample name, theta and native stage X/Y/Z coordinates.
The current XRM profile imposes some requirements in addition to NXDL validation.
See the [mapping reference](../metadata-mapping.md) for distinctions.

| Target | Additional metadata required by this converter |
|---|---|
| TXRM / `NXtomo` | Measured angle per projection; integer primary images; generated primary TXRM `image_key=0` |
| TXM / `NXtomoproc` | Source type/name, reconstruction program/version/date, raw acquisition filename, positive cubic voxel size, verified image orientation; measured slice Y coordinates |
| XRM / `NXxrm_image` | Positive object-side pixel size; one image |
| Reconstructed TIFF / `NXtomoproc` | Same reconstruction fields, explicit voxel size, orientation and three-coordinate `volume_origin_um`; no measured TXM slice array available |
| Projection TIFF / `NXtomo` | Actual per-frame theta and integer role array `image_key` (0..3); integer primary images |

The missing-fields exception reports unresolved values, not proof that no source
contains the information. The reader currently decodes only selected TXM/RCP
fields. The mappings can be extended after their meaning is established.

## Option 1: supplement a binary image using archive YAML

Save `scan/reconstruction.archive.yaml` in the same upload as the source. The
following is a **synthetic illustration**; replace source and reconstruction
values with verified records. Add only fields absent from the assigned sources.

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
  input_file: scan/tomo-A/reconstruction.txm
  metadata_file: scan/measurement.json
  target_definition: NXtomoproc
  export: true
  metadata_supplements:
    source_type: "Fixed Tube X-ray"
    source_name: "Synthetic example tube"
    reconstruction_version: "1.0-example"
    reconstruction_date: "2026-08-26T12:00:00+02:00"
    image_orientation:
      row_axis: z
      column_axis: x
      row_sign: 1
      column_sign: 1
```

This matches a common five-field failure, assuming `reconstruction_program`,
sample, geometry, voxel size and raw-file reference already exist. If a program
name is also missing, add `reconstruction_program` with its true value.
The quoted `source_type` is an example of a NeXus source category, not an arbitrary
test string; check the enum in your active NXsource/NXDL definitions.

The `input_file` assignment is essential. Putting supplements in a TIFF-only YAML
does not configure a TXM. `metadata_file` is relative to the upload root, not to
the YAML. Once saved/uploaded, reprocess the full upload.

Do not add `theta: 0` or zero stage coordinates when the image already supplies
them. Different explicit values raise `MetadataConflict`. The same applies to
units: supplement keys ending `_um` are numbers in micrometres, and theta is in
degrees. A mismatching supplement does not “win” over the image.

## Option 2: provide an eLabFTW-style JSON export

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

For that example, assign the JSON to the binary with `metadata_file`, or put it
as the sole eLabFTW-style JSON in the nearest measurement folder. It augments
image/RCP values; it is not a complete metadata record for a bare TIFF stack.

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

## Option 3: CLI supplements JSON

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
pynx-xrm convert --input scan/tomo-A/reconstruction.txm --metadata scan/measurement.json --supplements missing-values.json --output reconstruction.nxs
```

CLI paths are ordinary paths relative to the shell's current directory (unless
absolute). They do not use NOMAD's upload-root convention. The CLI does not scan
for NOMAD archive YAML or automatically discover sidecars: pass `--metadata`
and repeatable `--recipe` explicitly as needed.

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
frame. TXM instead uses measured slice positions and centred local X/Z axes.

Precedence is **image > associated RCP > eLabFTW > explicit supplements**.
Conflicting lower-priority source values are recorded; a conflicting explicit
supplement raises an error. RCP currently contributes sample name and, for
reconstructions, acquisition reference. TXM `exeVersion` is preserved as
`file_software_version`, not assumed to be reconstruction software version.
Layer dates are preserved, not asserted to be reconstruction time. Extending
those mappings requires verification of the manufacturer fields' semantics.
