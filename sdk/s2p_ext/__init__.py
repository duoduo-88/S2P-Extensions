"""S2P-Extensions SDK: talk to S2P-XInput-Lite over its Extensions pipe.

Only the standard library is used.  Protocol: S2P-XInput-Lite
``docs/extensions-ipc.md`` (protocol v1).
"""

from .client import (
    BUTTON_NAMES,
    DEFAULT_PIPE,
    HEARTBEAT_SECONDS,
    PROTOCOL_VERSION,
    AutoConnection,
    ExtensionClient,
    S2PError,
)

__all__ = [
    "BUTTON_NAMES",
    "DEFAULT_PIPE",
    "HEARTBEAT_SECONDS",
    "PROTOCOL_VERSION",
    "AutoConnection",
    "ExtensionClient",
    "S2PError",
]
