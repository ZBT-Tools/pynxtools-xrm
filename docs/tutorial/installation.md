# Install pynxtools-xrm

This tutorial installs the converter into an isolated Python environment and
checks its NeXus definitions. For NOMAD 2.0.0 Oasis deployment, continue with the
[server guide](../howto/oasis-deployment.md); a local installation does not install
the plugin into a remote worker.

## Requirements

- Python >=3.10; the examples use Python 3.12.
- `pynxtools>=0.15.2,<0.16`, installed by the package dependency resolver.
- Disk space for the input and compressed output, including a temporary new
  output alongside an existing result during replacement.
- For NOMAD: the plugin and the configured pynxtools NeXus parser in the app and
  worker environments. The package declares a NOMAD extra, but its dependency
  lower bound is not a compatibility guarantee for all NOMAD releases.

## Install from the repository

Use the ZBT developer's repository. Pin a reviewed tag or commit for deployment;
do not assume the moving default branch is a stable release.

```bash
git clone https://github.com/jonasdfortmann/pynxtools-xrm.git
cd pynxtools-xrm
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. If NOMAD is
not already provided by your development environment, install the optional extra
with `python -m pip install -e '.[nomad]'`. An existing Oasis should retain its
distribution's pinned NOMAD version; build and test the plugin into that image.

## Prepare NeXus definitions

The plugin ships `NXxrm_image`, but pynxtools does not automatically discover the
plugin's private XML directory. Prepare a separate **complete** definitions tree:

```bash
pynx-xrm definitions --output "$PWD/run/xrm-definitions"
export NEXUS_DEF_PATH="$PWD/run/xrm-definitions"
```

PowerShell equivalent:

```powershell
pynx-xrm definitions --output run/xrm-definitions
$env:NEXUS_DEF_PATH = (Resolve-Path run/xrm-definitions).Path
```

The output includes base classes, standard applications and the local
`applications/NXxrm_image.nxdl.xml`. Set the variable before imports. Restart
already running Python sessions after changing it. See the
[definition lifecycle](../howto/oasis-deployment.md#definition-files-and-upgrades)
for upgrades and the inactive `NXxrm_tomoproc` extension.

## Verify the environment

```bash
python -c 'from importlib.metadata import version; print(version("pynxtools-xrm")); print(version("pynxtools"))'
python -c 'from pynxtools.nexus.utils import get_nxdl_root_and_path; print(get_nxdl_root_and_path("NXxrm_image")[1]); print(get_nxdl_root_and_path("NXtomoproc")[1])'
pynx-xrm --help
```

Both XML lookups should resolve into the chosen overlay. This validates lookup,
not a complete measurement. Next use genuine data or the bundled synthetic
example, following [the upload guide](../howto/nomad-upload.md).
