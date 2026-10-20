"""
Proxmox MCP formatting package for styled output.
"""

from .colors import ProxmoxColors
from .components import ProxmoxComponents
from .formatters import ProxmoxFormatters
from .templates import ProxmoxTemplates
from .theme import ProxmoxTheme

__all__ = [
    "ProxmoxTheme",
    "ProxmoxColors",
    "ProxmoxFormatters",
    "ProxmoxTemplates",
    "ProxmoxComponents",
]
