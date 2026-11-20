# Architecture and operation

Developed at ZBT by Jonas Fortmann. For operational steps use the
[deployment guide](howto/oasis-deployment.md), [upload guide](howto/nomad-upload.md)
and [output reference](reference/outputs.md).

All conversion entry points call `streaming_writer.convert`. `ZeissSource`
opens the OLE directory and reads the image headers and embedded metadata. It
yields pixels one frame at a time. Three direct mappings select the NeXus
groups, required fields, axes and storage order. The TIFF reader is an adapter
for numbered stacks and eLabFTW metadata. It prepares a pynxtools template and
uses the same pixel writer.

The writer uses a fixed-size gzip dataset, a per-output lock, a temporary file
and atomic replacement after validation. TXRM and TXM use the standard NXDL
validator. XRM uses NeXus base classes and checks the shape and signal link.
The pixel checksum is recorded during streaming.

| Input | Dataset order | Source metadata |
|---|---|---|
| TXRM | projection, column, row | Embedded sample name, measured angles, and established image roles |
| TXM | column, layer, row | Embedded reconstruction metadata and local volume axes |
| XRM | row, column | Embedded metadata and optional image calibration |
| TIFF stack | target-specific | Explicitly assigned TIFF metadata |

Auxiliary OLE images retain their type and original stream paths. The remaining
OLE streams are preserved as bytes in an `NXcollection`. Acquisition and slice
timestamps retain their recorded timezone-free representation. See the
[metadata mapping](metadata-mapping.md) for the details.

## NOMAD deployment

Install the package into the app and worker environments. The standard
pynxtools definitions suffice for new exports. An overlay with `NXxrm_image`
is available when an installation still reads existing files using that
application definition.

The binary MatchingParser checks extension, compound-file signature and ZEISS
image headers without converting. The image mainfile owns conversion; an optional
archive.yaml points at it with input_file and requests that owner to reprocess.
Generated files use `_nexus/<relative path>/<original name including extension>.nxs`.
Their processing is requested through NOMAD's process_updated_raw_file interface.
Reused outputs do not trigger another generated-file processing request.

A binary job can select an output path and compression in a matching YAML.
Each binary input provides its own metadata. Only the separate TIFF adapter
takes explicitly assigned metadata.

```yaml
data:
  m_def: pynxtools_xrm.nomad.schema_packages.schema.XRMDataConverter
  tiff_directory: layers
  metadata_file: metadata.json
  target_definition: NXtomoproc
  output: result.nxs
  metadata_supplements:
    theta: 0
    stage_x_um: 0
    stage_y_um: 0
    stage_z_um: 0
    volume_origin_um: [-0.75, -0.5, -0.5]
    image_orientation: {row_axis: z, column_axis: x, row_sign: 1, column_sign: 1}
```

The geometry values above are a synthetic example, not defaults for measurements.
Reconstruction program/version/date and source name/type must be supplied by
genuine metadata.

## Definition scope

TXRM validates against `NXtomo`, TXM against `NXtomoproc`. Single-image XRM
uses `NXentry`, `NXdata` and instrument base classes. On the legacy NOMAD
parser, these generic entries can be parsed but do not match the XRM app's
current application-definition filter.
