#!/usr/bin/env python3
"""Lanzador principal de consola (CLI) para el emulador Atmel/Microchip AT89S51."""
from pathlib import Path
import sys

# Garantiza que el directorio raíz esté en sys.path al ejecutar directamente
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
