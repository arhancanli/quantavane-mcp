"""python -m quantavane_mcp: run the server over stdio (or a subcommand; see --help)."""
import sys

from .server import main

sys.exit(main())
