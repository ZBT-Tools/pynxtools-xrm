# Structure and process a NOMAD upload

Automatic processing needs a configured server, supported image files, complete
metadata and unambiguous associations. Directory layout alone cannot guarantee
that arbitrary manufacturer files satisfy the supported profile. First complete
[Oasis deployment](oasis-deployment.md).

## Binary image upload

Upload the entire tree together, or a ZIP preserving the following structure.
Here `/` is the **upload raw-file root**, not the server filesystem root:

```text
/
└── scan/
    ├── measurement.json
    ├── recipe.rcp
    ├── reconstruction.archive.yaml
    └── tomo-A/
        ├── acquisition.txrm
        ├── reconstruction.txm
        └── FrontScoutImage.xrm
```

The names are illustrative. Keep original vendor basenames and acquisition
directory names when possible: RCP association uses declared filenames and
directory context. Recipe and eLabFTW JSON should describe these measurements.
Each ZEISS image with supported headers is automatically matched by the binary
parser. Without custom options, no YAML is required if the associated sources
already provide every required value. A single-image XRM must contain one frame.

An example `scan/reconstruction.archive.yaml` is:

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
  input_file: scan/tomo-A/reconstruction.txm
  metadata_file: scan/measurement.json
  recipe_file: scan/recipe.rcp
  target_definition: NXtomoproc
  export: true
  metadata_supplements:
    image_orientation:
      row_axis: z
      column_axis: x
      row_sign: 1
      column_sign: 1
```

This example assumes all other required metadata are available in the assigned
sources and that the orientation has been verified. Use the
[full metadata examples](additional-metadata.md) when fields are missing.
`recipe_file` is optional; if set it must still match the image. An explicit
assignment does not bypass the association check.

## Path and configuration rules

1. Every `input_file`, `metadata_file`, `recipe_file`, `tiff_directory` and `output`
   path is relative to the upload root. A nested YAML does not change the base.
2. Use `/` separators and exact filename case for Linux. Server-absolute and
   external paths are not accepted for input; paths must resolve inside the upload.
3. A ZIP containing a top-level `scan/` directory needs `scan/...` paths. A ZIP
   containing only its contents needs paths without that prefix. Inspect NOMAD's
   Files view after extraction before choosing a path.
4. Use one `*.archive.yaml` per binary input. The parser scans the upload for
   matching `data.input_file`; duplicate matching jobs are an error. Filename
   similarity alone does not assign a YAML to a binary.
5. For binary files use `input_file`. A YAML containing only `tiff_directory`
   configures a TIFF job and supplies no metadata to a TXM parser. Do not set both.
6. Choose distinct output paths for different jobs. Retain the default for
   binary images unless an explicit naming convention is needed.

## Automatic sidecar discovery

For each binary source, the parser searches its directory, then ancestors up to
the upload root. At the nearest level containing an eLabFTW-style JSON (a JSON
object containing `metadata_decoded`), it uses that file. Two matching JSONs at
that level are ambiguous: set `metadata_file` explicitly. An unrelated plain
JSON supplement file is not automatically interpreted as eLabFTW metadata.

RCP discovery similarly selects the nearest directory containing `.rcp` files.
The reader then requires an unambiguous association through RecipePoint file
declarations or acquisition-directory context. An unrelated RCP in that scope
can stop conversion; keep acquisitions in separate directories or explicitly
assign the correct recipe. The reader does not merge all recipes or all JSON
files in the upload.

## TIFF stack upload

TIFF images do not independently trigger the XRM volume converter. Upload a job:

```text
/
├── volume.archive.yaml
├── metadata.json
└── layers/
    ├── layer_0001.tif
    ├── layer_0002.tif
    └── layer_0003.tif
```

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
  tiff_directory: layers
  metadata_file: metadata.json
  target_definition: NXtomoproc
  output: _nexus/volume.nxs
  export: true
```

This requires a complete metadata JSON; the bundled synthetic example provides
one. TIFF discovery is not recursive: all slices must be in `layers/`. Each file
must be single-page grayscale, with identical dimensions and datatype. Filenames
must end in a numeric index, with no duplicates or gaps; the starting index need
not be zero. A reconstructed stack additionally needs voxel calibration, volume
origin and verified orientation. Projection TIFFs use `NXtomo`, real measured
angles and one `image_key` per frame. See [metadata](additional-metadata.md).

For TIFF jobs, assign `metadata_file` explicitly. The YAML TIFF path does not
perform the binary parser's automatic JSON/RCP discovery; `recipe_file` is not
passed through that TIFF conversion path.

## Processing and verification

1. Submit images, JSON/RCP and YAML together. Avoid triggering a large conversion
   while associated files are still being uploaded.
2. Inspect the Entries tab. A completed project/upload can still contain failed
   entries. Open each failure's Logs and expand its exception.
3. Expect a successful binary conversion entry and a generated `.nxs` entry
   processed by the configured NeXus parser. An RCP need not have its own entry.
4. Inspect [output paths and datasets](../reference/outputs.md), not just the
   existence of an older `.nxs` file. Failed replacement preserves an older result.
5. After adding/changing JSON, RCP or YAML, **reprocess the entire upload**.
   There is no custom sidecar watcher that automatically reruns dependent images.

For a small first check use NOMAD's installed XRM example upload. Its values are
synthetic. Passing that example verifies the pipeline, not a real measurement's
metadata accuracy. See [troubleshooting](troubleshooting.md) for specific failures.
