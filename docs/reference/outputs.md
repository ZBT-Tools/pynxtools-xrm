# Output paths and generated data

## NOMAD binary defaults

The automatic binary parser writes one NeXus file per source image. Given a
source path relative to the upload root, the default is:

```text
_nexus/<relative parent directories>/<original filename including extension>.nxs
```

| Source in upload | Default generated file in upload |
|---|---|
| `acquisition.txrm` | `_nexus/acquisition.txrm.nxs` |
| `scan/tomo-A/acquisition.txrm` | `_nexus/scan/tomo-A/acquisition.txrm.nxs` |
| `scan/tomo-A/reconstruction.txm` | `_nexus/scan/tomo-A/reconstruction.txm.nxs` |
| `scan/tomo-A/FrontScoutImage.xrm` | `_nexus/scan/tomo-A/FrontScoutImage.xrm.nxs` |

Keeping `.txrm`, `.txm` or `.xrm` in the output name avoids collisions between
different input types sharing a stem. `_nexus` is a plugin naming convention
inside the upload, not a directory to create under the server's installation.

Override with `data.output: results/reconstruction.nxs` in the **matching binary
YAML**. The path is relative to the upload root and must stay inside it. Use a
separate `.nxs` filename and never target an input. Different jobs must not
share outputs. A subsequent output-name change can leave the previous result
in the upload; it is not automatically renamed or removed.

## TIFF and CLI outputs

TIFF YAML jobs use exactly `data.output`, relative to the upload root; the
fallback when omitted is **`xrm_volume.nxs` at the upload root**, not a path under
`_nexus`. Set an explicit unique output for every TIFF job. The bundled example
uses `xrm_example.nxs`.

The CLI requires `--output`. It resolves relative paths against the working
directory and does not add `_nexus` or the original extension automatically.
Existing output requires `--overwrite` for CLI conversion; NOMAD requests
overwrite through its conversion adapter.

## HDF5 dataset paths

| Application | Primary pixel dataset | Array order |
|---|---|---|
| `NXtomo` | `/entry/instrument/detector/data` (linked as `/entry/data/data`) | projection, column, row |
| `NXtomoproc` | `/entry/data/data` | x, y-layer, z |
| `NXxrm_image` | `/entry/instrument/detector/data` (linked as `/entry/image/image_2d/intensity`) | row, column |

Projection frames and reconstruction slices are transposed during streaming
to the documented target order. XRM retains its row/column image layout.
Physical axes, geometry and metadata accompany the pixels. These internal HDF5
paths are not upload filenames and must not be used as YAML `output` paths.

## NOMAD entries, status and reuse

The binary mainfile owns conversion; the YAML requests processing of that
mainfile. Its `conversion_status: requested` does not prove that conversion has
finished. Successful binary entries report `converted` or `reused`. A TIFF YAML
owns its own conversion. Newly written `.nxs` files are submitted to the
configured pynxtools NeXus parser as separate mainfiles. `nexus_view` links the
converter to the generated archive's data; it is not another raw data file.

Check both conversion and generated NeXus entry status. A generated file can
exist while its NeXus parsing fails. An unchanged validated output can be reused
without requesting generated-file processing again; if only the NeXus parser
configuration changed, explicitly reprocess that generated entry as well.

Writes use gzip compression, an exclusive output lock, a temporary `.part` file
and atomic replacement after validation. Failed conversion preserves an older
valid output, so file existence alone does not prove the latest run succeeded.
Reuse checks source path/size/mtime, effective metadata, recipe, compression,
application NXDL and implementation fingerprint. It does not reread the complete
input pixel content for cache lookup. The pixel checksum is computed while writing.
