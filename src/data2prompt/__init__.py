"""data2prompt — convert data-heavy local workspaces into LLM-ready context."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("data2prompt")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0.dev0"
