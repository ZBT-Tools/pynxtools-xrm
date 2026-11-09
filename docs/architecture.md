# Architecture and operation

Developed at ZBT by Jonas Fortmann. For operational steps use the
[deployment guide](howto/oasis-deployment.md), [upload guide](howto/nomad-upload.md)
and [output reference](reference/outputs.md).

All conversion entry points call streaming_writer.convert. XRMReader remains a
pynxtools MultiFormatReader; format inspection and metadata mapping are separate
from the pixel phase. ZeissSource reads the OLE directory and small header streams,
then opens one image stream at a time. TiffSource adapts the existing TIFF manifest.
No complete pixel volume is assembled. Header arrays and the OLE directory grow
with frame count, so total metadata memory is not constant.

The standard pynxtools Writer creates metadata using the selected NXDL. Links
to pixels are deferred until the HDF5 adapter has created their targets. Each
frame is written to a fixed-size gzip dataset. Float reference images remain in
separate NXdata groups with their original datatype. All non-image vendor streams
and complete associated recipes are retained as base64 JSON in NXnote datasets.
This preserves metadata stream bytes; it does not preserve the original OLE file
layout or embed a byte-identical copy of the entire image file.

Output creation uses an exclusive per-output lock, a temporary file, NXDL and
shape checks, and atomic replacement. Failed conversions preserve an existing
valid output. Repeated conversion can reuse a validated result when source
path/size/mtime, effective metadata, recipe, compression, application NXDL and
implementation fingerprint match. The source pixel SHA-256 is recorded during
writing; cache lookup uses file stamps rather than rereading gigabytes of pixels.

| Input | Dataset order | Write operation |
|---|---|---|
| TXRM / projection TIFF | frame, column, row | data[i] = frame.T |
| TXM / reconstruction TIFF | x, y-layer, z | data[:, i, :] = frame.T |
| XRM | row, column | data[:, :] = frame |

TXM requires explicit image_orientation (row_axis=z, column_axis=x, signs +/-1).
Its measured Y positions are checked against the single cubic voxel size.
X/Z axes are local centered pixel offsets; the volume is related to the native
sample frame through the stored stage transformations. TIFF volumes additionally
require volume_origin_um, the first voxel coordinate in that frame. Raw TIFFs
require a real theta array and one image_key per frame. No uniform angle series
is generated. XRM pixel axes are local row/column distances with no asserted
orientation in stage coordinates.

The global coordinate system uses X along the beam, source -X and detector +X,
Y down, and right-handed Z. The sample basis is B @ Ry(theta), with
B=[[0,0,1],[0,1,0],[-1,0,0]]. Native translations depend on the rotation chain.
NXcoordinate_system explicitly relates this global frame to the NeXus default.
Detector layout=area and type='planar area detector' record the user-confirmed
geometry. Sensor pitch is never substituted for object-side pixel size.

## NOMAD deployment

Install the package into the app/worker environment to register xrm_raw_parser.
Prepare an overlay with `pynx-xrm definitions --output run/xrm-definitions`.
Set NEXUS_DEF_PATH to its absolute path before starting **every** app/worker
process, and restart after plugin entry-point changes. The overlay is a copy of
the installed definitions plus NXxrm_image; third-party package files are untouched.
Its marker records the base revision and custom application checksum.

The binary MatchingParser checks extension, compound-file signature and ZEISS
image headers without converting. The image mainfile owns conversion; an optional
archive.yaml points at it with input_file and requests that owner to reprocess.
Generated files use `_nexus/<relative path>/<original name including extension>.nxs`.
Their processing is requested through NOMAD's process_updated_raw_file interface.
Reused outputs do not trigger another generated-file processing request.

RCP matching uses explicit RecipePoint file declarations and acquisition directory
context. The nearest unambiguous eLabFTW scope is used. Multiple matching metadata
files or recipes require explicit assignment. Server inputs must remain inside
the upload root; original absolute ZEISS paths are retained only as provenance.
Adding/changing RCP or JSON later requires **reprocessing the upload**. There is no
custom sidecar watcher or hidden background conversion service.

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

The active targets are NXtomo, NXtomoproc and NXxrm_image. The optional packaged
NXxrm_tomoproc extension is not an enabled target and is not copied into the
overlay. See [definition setup](howto/oasis-deployment.md#definition-files-and-upgrades).
