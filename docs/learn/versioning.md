# Versions and reproducibility

The distribution version comes from setuptools-scm and Git history at build
time. Query installed versions in the actual worker environment:

```bash
python -c 'from importlib.metadata import version; print("pynxtools-xrm", version("pynxtools-xrm")); print("pynxtools", version("pynxtools")); print("nomad-lab", version("nomad-lab"))'
```

The NOMAD query requires NOMAD to be installed; standalone conversion does not.
Record the Git revision for editable installations as well as the reported
version. Do not infer the deployed worker revision from a local checkout.

The converter records its package name, version and actual conversion time in
`/entry/conversion` (`NXprocess`). The reconstruction software/version/date in
`/entry/reconstruction` describe the experimental processing and are independent
of the converter's version/time. A TXM file's `exeVersion` is retained as source
metadata rather than silently substituted for either quantity.

The overlay marker `xrm-overlay.json` records the base-definition revision and
`NXxrm_image` checksum. Keep it with the deployment configuration. Rebuild a fresh
overlay when upgrading the base definitions and switch app/workers together.
See [deployment](../howto/oasis-deployment.md#definition-files-and-upgrades).

For reproducibility retain original files, RCP, uploaded JSON, configuration,
package/image revision, definitions and generated NeXus. Output reuse considers
source file stamps, metadata and implementation fingerprint; see
[outputs](../reference/outputs.md). It does not establish that a source file was
unchanged if external software modified bytes while preserving size and mtime.
