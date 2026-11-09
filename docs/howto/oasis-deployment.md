# Deploy on NOMAD 2.0.0 Oasis

This guide addresses a Linux Oasis with separate application and processing
workers. Adapt service names and paths to your installation. All examples use
`/opt/nomad/xrm-definitions` as a chosen container/service path, not a NOMAD
default. Keep app, worker, plugin, pynxtools and definition versions consistent.

## Files to change

| File or setting | Required change | Purpose |
|---|---|---|
| Distribution dependency file / image build (`pyproject.toml`, requirements or Dockerfile) | Install the reviewed pynxtools-xrm version in app and worker environments; retain the distribution's NOMAD pin | Registers parser, schema, app and example entry points |
| `Dockerfile.xrm` (container example below) | Install the wheel and run `pynx-xrm definitions` | Provides the custom XML and complete base definitions inside the image |
| `docker-compose.override.yml` or the actual Compose file | Use the same prepared image for every Python app/worker service; set `NEXUS_DEF_PATH` | Makes definitions visible to all processes |
| Alternatively `/etc/nomad/xrm.env` and systemd drop-ins | Set the absolute overlay path and load the environment file in each service | Persists the variable outside interactive shells |
| Existing `nomad.yaml` plugin configuration, only if filtering plugins | Permit this plugin's entry points and the installed pynxtools NeXus parser | Avoids installed-but-disabled plugins |
| Upload `*.archive.yaml` / JSON | Assign image paths and genuine missing metadata | Configures a measurement, not the server |

No change to installed third-party NXDL files is needed. The plugin's
`src/pynxtools_xrm/definitions.py` implements overlay preparation; normally you
run its CLI rather than editing that source file.

## Install into the actual processing environment

Installing on the host, in a different virtual environment or only in the web
container does not update a worker. For an existing development checkout:

```bash
# Run using the intended virtual environment's python.
python -m pip install -e /path/to/pynxtools-xrm
pynx-xrm definitions --output /opt/nomad/xrm-definitions
```

For deployment use a reviewed wheel or pinned revision, with a reproducible
image/dependency lock. If the distribution has an explicit plugin allow-list,
merge the following installed entry points into that existing configuration:

```text
pynxtools_xrm.nomad.parsers:xrm_raw_parser
pynxtools_xrm.nomad.schema_packages:xrm_data_converter
pynxtools_xrm.nomad.apps:xrm_app
pynxtools_xrm.nomad.example_uploads:xrm_example_upload
```

The first two are needed for binary and YAML conversion. The search app and
example upload are optional. The generated `.nxs` also needs the distribution's
active pynxtools NeXus parser. Do not replace an existing allow-list with only
these four entries. The plugin's search app targets legacy parser field paths;
successful conversion does not establish search-app compatibility with v2 paths.

For NOMAD's `plugins.entry_points.include` setting, the entries to merge into
an existing `nomad.yaml` list have this form (retain all existing required
entries, especially the distribution's NeXus parser):

```yaml
plugins:
  entry_points:
    include:
      # Keep the existing entries here as well.
      - pynxtools_xrm.nomad.parsers:xrm_raw_parser
      - pynxtools_xrm.nomad.schema_packages:xrm_data_converter
      - pynxtools_xrm.nomad.apps:xrm_app
      - pynxtools_xrm.nomad.example_uploads:xrm_example_upload
```

Also check that no `exclude` rule disables these entries. If you already enable
all installed plugins, no include-list change is required. `NEXUS_DEF_PATH` is
a process environment variable, not a new top-level key to add to `nomad.yaml`.

## Docker: build definitions into the image

From the plugin repository, build a wheel in a build environment:

```bash
python -m pip install build
python -m build --wheel
```

Save this example as `Dockerfile.xrm` in that repository. Choose the exact base
image already used by your Oasis. The same resulting image must serve all app
and worker roles that import this plugin. Use an appropriate non-root runtime
user if your base image defines one; the shown root user is for installation.

```dockerfile
ARG NOMAD_BASE_IMAGE
FROM ${NOMAD_BASE_IMAGE}
USER root
COPY dist/*.whl /tmp/xrm-wheels/
RUN python -m pip install --no-cache-dir /tmp/xrm-wheels/*.whl
RUN pynx-xrm definitions --output /opt/nomad/xrm-definitions
ENV NEXUS_DEF_PATH=/opt/nomad/xrm-definitions
# Restore your base image's runtime USER here, if applicable.
```

The base image must resolve the declared pynxtools dependency without breaking
its NOMAD distribution. Check the build and `python -m pip check`; do not bypass
dependency conflicts. Use a fresh destination if that path already contains an
unrecognized definitions tree.

Build with the base-image tag used by your installation:

```bash
docker build --build-arg NOMAD_BASE_IMAGE=YOUR_EXISTING_PINNED_NOMAD_IMAGE -f Dockerfile.xrm -t nomad-oasis-xrm:local .
```

In the directory containing the Oasis Compose files, add or merge
`docker-compose.override.yml`. **Replace `app` and `worker` with actual service
names from `docker compose config --services`**; add equivalent settings for
every additional worker. Existing commands, volumes and settings remain needed.

```yaml
services:
  app:
    image: nomad-oasis-xrm:local
    environment:
      NEXUS_DEF_PATH: /opt/nomad/xrm-definitions
  worker:
    image: nomad-oasis-xrm:local
    environment:
      NEXUS_DEF_PATH: /opt/nomad/xrm-definitions
```

Inspect the merged configuration, then recreate the affected services using
your actual names. A restart alone does not apply a changed Compose environment.

```bash
docker compose config
docker compose up -d --force-recreate app worker
```

Alternatively prepare definitions using the same package versions in a host
directory and mount the **whole tree** read-only into every relevant service:

```yaml
volumes:
  - ./xrm-definitions:/opt/nomad/xrm-definitions:ro
environment:
  NEXUS_DEF_PATH: /opt/nomad/xrm-definitions
```

This fragment belongs inside each service. The host directory must already
contain the prepared tree. A mount over an image's definition directory hides
that image content, so do not accidentally mount an empty directory over it.

## Native Linux services: systemd alternative

Prepare definitions with the same virtual environment used by the services.
Ensure service users can traverse and read the full tree. Create
`/etc/nomad/xrm.env` with:

```ini
NEXUS_DEF_PATH=/opt/nomad/xrm-definitions
```

For each actual unit, use `systemctl edit UNIT_NAME` to add a drop-in such as
`/etc/systemd/system/UNIT_NAME.service.d/override.conf`:

```ini
[Service]
EnvironmentFile=/etc/nomad/xrm.env
```

Replace `UNIT_NAME` with the application and each worker unit. Run
`systemctl daemon-reload` and restart those units during an appropriate service
window. An interactive shell `export` is not inherited by existing systemd
services. Use the equivalent persistent environment mechanism if using another
process manager.

## Verify inside each app and worker environment

For Docker, prefix these commands with `docker compose exec SERVICE_NAME` and
use the actual Python interpreter used by that service:

```bash
python -m pip check
python -c 'import os, sys; from importlib.metadata import version; print(sys.executable); print(version("pynxtools-xrm")); print(version("pynxtools")); print(os.environ.get("NEXUS_DEF_PATH"))'
python -c 'from pynxtools.nexus.utils import get_nxdl_root_and_path; print(get_nxdl_root_and_path("NXxrm_image")[1]); print(get_nxdl_root_and_path("NXtomoproc")[1]); print(get_nxdl_root_and_path("NXtomo")[1])'
python -c 'from importlib.metadata import entry_points; print([e.name for e in entry_points(group="nomad.plugin") if e.value.startswith("pynxtools_xrm.")])'
```

Expect `NXxrm_image` to resolve to
`/opt/nomad/xrm-definitions/applications/NXxrm_image.nxdl.xml`, and the standard
applications to the same tree. Entry-point enumeration proves installation,
not that an allow-list enabled them. Check the deployment's plugin information
and worker logs as well. A new `exec` process confirms the container environment;
the running workers must also have been recreated/restarted with it.

Process the bundled synthetic example, then a representative TXRM/TXM/XRM upload.
Check the binary entries **and** their generated NeXus entries. Reprocess an
existing affected upload after fixing the server setup.

## Definition files and upgrades

| Location | Meaning |
|---|---|
| `site-packages/pynxtools/definitions/applications/` | Standard installed application definitions |
| `site-packages/pynxtools_xrm/definitions/applications/NXxrm_image.nxdl.xml` | Plugin source of the custom single-image definition |
| `$NEXUS_DEF_PATH/applications/NXxrm_image.nxdl.xml` | Active copied custom definition |
| `$NEXUS_DEF_PATH/xrm-overlay.json` | Base revision and custom-definition checksum recorded during preparation |

Find the installed plugin XML without guessing the Python version:

```bash
python -c 'from pathlib import Path; import pynxtools_xrm; print(Path(pynxtools_xrm.__file__).parent / "definitions/applications/NXxrm_image.nxdl.xml")'
```

`NEXUS_DEF_PATH` points to the root containing `applications`, `base_classes`
and related definition files. It is **not** the XML filename or the plugin's
private `applications` directory. pynxtools captures the path during import.

The overlay command copies the installed pynxtools definitions and adds
**only `NXxrm_image`**. It refuses an existing destination without its marker,
and refuses reusing a marked tree with a different base revision. After an
upgrade, create a fresh versioned directory, point all processes to it, restart
them and repeat the lookup and conversion checks. Prepare the overlay before
switching `NEXUS_DEF_PATH`; stale environment settings can affect imports.

The optional packaged XML is named **`NXxrm_tomoproc`**, extending `NXtomoproc`.
It is not copied by this command and is not an accepted YAML/CLI target. TXM
conversion uses `NXtomoproc`; copying or renaming the optional XML alone does
not enable another target. Additional optional domain metadata are emitted by
the mapping code. Supporting a new target requires coordinated reader, mapping,
writer, schema and validation changes and tests.

## Upstream guidance

Use the [NOMAD documentation](https://docs.nomad-lab.eu/) for the distribution's
installation, plugin and administration procedures. This guide documents the
extra requirements of the ZBT plugin, not a replacement Oasis deployment.
