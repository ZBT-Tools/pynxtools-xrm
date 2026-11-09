# Bundled synthetic example

NOMAD's XRM example-upload entry point supplies a tiny reconstructed TIFF job.
Its resources are located at
`src/pynxtools_xrm/nomad/example_uploads/example/` in the checkout:

```text
/
├── README.md
├── xrm.archive.yaml
├── metadata.json
└── layers/
    └── numbered grayscale TIFF slices
```

The YAML references `metadata.json` and `layers` relative to that upload root,
uses `NXtomoproc`, and writes `xrm_example.nxs`. The JSON contains the complete
synthetic source/reconstruction metadata, voxel size and geometry. All values
are artificial and must not be copied into a real measurement.

Load the installed XRM example through NOMAD's example-project/upload feature,
or upload the **contents** of the example directory preserving `layers/`.
An extra enclosing folder changes the upload root paths and requires adjusting
the YAML. Process the YAML and inspect both its result and the generated NeXus
entry. The [configuration reference](configuration.md) explains these fields.

The example validates the reconstruction pipeline; separately test a real
single-image XRM to verify `NXxrm_image` lookup and the installed NeXus parser.
