from importlib import metadata

try:
    __version__ = metadata.version("the-thomas-test-suite")
except metadata.PackageNotFoundError:
    __version__ = "unknown"
