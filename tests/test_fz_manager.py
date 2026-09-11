from importlib.metadata import version

from fz_manager import __version__


def test_version():
    # __version__ is resolved dynamically from installed package metadata, so it always
    # stays in sync with the version declared in pyproject.toml.
    assert __version__ == version("FZ-Manager")
