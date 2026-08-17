"""lindas-mcp — MCP server for the Swiss Linked Data Service (LINDAS)."""

from ._version import __version__
from .server import main, mcp

__all__ = ["main", "mcp", "__version__"]
