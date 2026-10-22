# pynxtools-xrm

Sequential ZEISS TXRM, TXM, XRM and numbered TIFF conversion for NeXus and NOMAD.
TXRM produces NXtomo projections, TXM produces NXtomoproc volumes, and XRM uses
the local NXxrm_image application based on NXimage/NXdata. Each image file has
its own output. RCP is associated recipe metadata and creates no separate entry.

Install with `uv pip install -e .`. The supported pynxtools series is 0.15.x.
Prepare the shared definitions overlay and set NEXUS_DEF_PATH **before** starting
Python, the NOMAD app and its workers:

```powershell
pynx-xrm definitions --output run/xrm-definitions
$env:NEXUS_DEF_PATH = (Resolve-Path run/xrm-definitions).Path
```

```shell
pynx-xrm inspect acquisition.txrm
pynx-xrm inspect recipe.rcp
pynx-xrm convert --input acquisition.txrm --recipe recipe.rcp --output acquisition.nxs
pynx-xrm convert --tiffs layers --target NXtomoproc --metadata metadata.json --output volume.nxs
```

Use `--supplements missing-values.json` for explicit missing values. Existing
image, recipe or eLabFTW values cannot be overwritten. Missing required metadata
raise an error before output creation. Acquisition timestamps are localized to
Europe/Berlin; incomplete dates and ambiguous daylight-saving times are errors.

In NOMAD, upload the image files and associated metadata together. The binary
parser selects the target automatically. TIFF stacks continue to use
XRMDataConverter archive.yaml with target_definition NXtomo or NXtomoproc.
After adding/changing sidecars, reprocess the upload to rerun dependent files.

The core pynxtools Writer writes metadata; a small HDF5 adapter streams one
image at a time. Standard `pynx convert --reader xrm` rejects the call with
guidance because it has no frame-iterator writer contract.

See [architecture](docs/architecture.md), [metadata mapping](docs/metadata-mapping.md)
and [installation](docs/tutorial/installation.md).
