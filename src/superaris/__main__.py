"""Run the same installed interface with this Python interpreter."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(prog="superaris"))
