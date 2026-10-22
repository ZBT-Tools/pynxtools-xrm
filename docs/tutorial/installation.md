# Installation guide

## What should you know before this tutorial?

To get started, it does not hurt to read the following `pynxtools` tutorial:

- [Guide on getting started with `pynxtools`, NeXus, and NOMAD](https://fairmat-nfdi.github.io/pynxtools/getting-started.html)
- [Installation tutorial for `pynxtools`](https://fairmat-nfdi.github.io/pynxtools/tutorial/installation.html)

## What you will know at the end of this tutorial?

You will know

- how to install `pynxtools-xrm`
- how to install `pynxtools-xrm` together with NOMAD

## Setup

It is recommended to use python 3.12 with a dedicated virtual environment for this package. Learn how to manage [python versions](https://github.com/pyenv/pyenv) and [virtual environments](https://realpython.com/python-virtual-environments-a-primer/).

There are many alternatives to managing virtual environments and package dependencies (requirements). We recommend using [`uv`](https://github.com/astral-sh/uv), an extremely fast Python package and project manager. In this tutorial, you will find parallel descriptions, using either `uv` or a more classical approach using `venv` and `pip`.

Start by creating a virtual environment:

=== "uv"
    `uv` is capable of creating a virtual environment and install the required Python version at the same time.

    ```bash
    uv venv --python 3.12
    ```

=== "venv"

    Note that you will need to install the Python version manually beforehand.

    ```bash
    python -m venv .venv
    ```
That command creates a new virtual environment in a directory called `.venv`.

## Installation

Install the latest stable version of this package from PyPI with

=== "uv"

    ```bash
    uv pip install pynxtools-xrm
    ```

=== "pip"

    ```bash
    pip install pynxtools-xrm
    ```

You can also install the latest _development_ version with

=== "uv"

    ```bash
    uv pip install git+https://github.com/FAIRmat-NFDI/pynxtools-xrm.git
    ```

=== "pip"

    ```bash
    pip install git+https://github.com/FAIRmat-NFDI/pynxtools-xrm.git
    ```

### How to install `pynxtools-xrm` with NOMAD

Install it in the same environment as `nomad-lab`, prepare the definitions overlay,
and set `NEXUS_DEF_PATH` to its absolute path before starting the app and workers.
See [architecture and deployment](../architecture.md) for the commands. Restart
the processes after installing the new parser entry point. All processes must
use the same definitions; the package does not modify installed third-party files.

## Start using `pynxtools-xrm`

That's it! You can now use `pynxtools-xrm`!
