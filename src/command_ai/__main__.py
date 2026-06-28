"""Allow ``python -m command_ai``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
