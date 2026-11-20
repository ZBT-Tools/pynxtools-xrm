# Structure and process a NOMAD upload

Automatic processing needs a configured server, supported image files, complete
embedded metadata for the selected output. Directory layout alone cannot guarantee
that arbitrary manufacturer files satisfy the supported profile. First complete
[Oasis deployment](oasis-deployment.md).

## Binary image upload

Upload the ZEISS files individually or in their original directory tree.
The binary parser processes each supported file using its embedded metadata.
The file extension selects the output structure. Missing application fields
are listed in the conversion status before a new NeXus output is written.

A matching YAML can choose an output path or compression:

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
  input_file: scan/tomo-A/acquisition.txrm
  output: results/acquisition.nxs
  gzip_level: 4
```

## Path and configuration rules

1. Every `input_file`, `metadata_file`, `tiff_directory` and `output`
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

For TIFF jobs, assign `metadata_file` explicitly.

## Processing and verification

1. Submit the image files. For TIFF stacks include the YAML job and its metadata.
2. Inspect the Entries tab. A completed project/upload can still contain failed
   entries. Open each failure's Logs and expand its exception.
3. Expect a successful binary conversion entry and a generated `.nxs` entry
   processed by the configured NeXus parser. An RCP need not have its own entry.
4. Inspect [output paths and datasets](../reference/outputs.md), not just the
   existence of an older `.nxs` file. Failed replacement preserves an older result.
5. Reprocess the relevant job after changes to its source or configuration.

For a small first check use NOMAD's installed XRM example upload. Its values are
synthetic. Passing that example verifies the pipeline, not a real measurement's
metadata accuracy. See [troubleshooting](troubleshooting.md) for specific failures.
