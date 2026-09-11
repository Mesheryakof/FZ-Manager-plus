from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('FZ-Manager')
except PackageNotFoundError:
    # Package is not installed (e.g. running from a source checkout without `poetry install`).
    __version__ = '0.0.0.dev0'

