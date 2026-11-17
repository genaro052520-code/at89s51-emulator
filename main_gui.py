#!/usr/bin/env python3
"""Lanzador principal de la interfaz gráfica (GUI DIP-40) para el AT89S51.

Acoplado exclusivamente a la capa intermedia ADM (src/ports/adm.py) sin importar
ningún módulo del núcleo CPU o de memoria interna.
"""
from pathlib import Path
import sys

# Garantiza que el directorio raíz esté en sys.path al ejecutar directamente
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.gui.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
