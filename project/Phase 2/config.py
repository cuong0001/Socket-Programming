"""Shared runtime configuration for the phase-2 server."""

import os


class ServerConfig:
    """Hold server defaults and apply supported command-line overrides."""

    def __init__(self) -> None:
        self.host = ""
        self.port = 9000
        self.max_clients = 10
        self.rate_kbps = 0
        self.chunk_size = 4096
        self.socket_timeout = 30.0
        self.storage_dir = os.path.join(os.getcwd(), "storage")
        self.log_file = os.path.join(os.getcwd(), "logs", "server.log")

    @classmethod
    def from_args(cls, args) -> "ServerConfig":
        """Build a configuration from an ``argparse``-style namespace."""
        config = cls()
        config.host = getattr(args, "host", config.host)
        config.port = getattr(args, "port", config.port)
        config.max_clients = getattr(args, "max_clients", config.max_clients)
        config.rate_kbps = getattr(args, "rate_kbps", config.rate_kbps)
        return config
