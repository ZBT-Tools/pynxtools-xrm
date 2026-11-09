# Synthetic ZBT XRM conversion example

Developed at ZBT – Zentrum für BrennstoffzellenTechnik GmbH by Jonas Fortmann
([j.formtann@zbt.de](mailto:j.formtann@zbt.de)).

This miniature example demonstrates the reconstructed TIFF path. All values
are synthetic and do not describe a real experiment.

Upload this directory's **contents**, keeping `layers/` intact, so that
`xrm.archive.yaml`, `metadata.json` and `layers/` are at the upload root.
Process `xrm.archive.yaml`: it assigns `metadata.json`, reads the numbered
grayscale slices in `layers/`, writes `xrm_example.nxs` and requests processing
of the generated NeXus entry. All YAML paths are relative to the upload root.

The server needs this plugin, its pynxtools dependency, an enabled NeXus parser
and a prepared definitions overlay exposed to app and workers through
`NEXUS_DEF_PATH` before startup. Use the package's Oasis deployment guide.

Check both the YAML entry and `xrm_example.nxs` entry for success. Changed metadata
require reprocessing the upload. Real TXM/TXRM/XRM images use a binary parser;
configure them with `input_file`, not this example's `tiff_directory`.

Source, documentation and issues:
<https://github.com/jonasdfortmann/pynxtools-xrm>.
