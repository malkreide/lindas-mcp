"""lindas-mcp — MCP server for the Swiss Linked Data Service (LINDAS)."""

__version__ = "0.2.0"

from .server import main, mcp

__all__ = ["main", "mcp", "__version__"]
