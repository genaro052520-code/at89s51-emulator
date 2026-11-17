"""src/core/cli.py - Interfaz de línea de comandos para el núcleo 8051."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Configura los argumentos CLI para cargar firmware .hex y controlar ejecución."""
    parser = argparse.ArgumentParser(
        prog="at89s51-core",
        description="Núcleo de emulación del microcontrolador Atmel/Microchip AT89S51.",
    )
    parser.add_argument("--hex", type=str, help="Ruta al archivo Intel HEX de entrada.")
    return parser


def main() -> None:
    """Punto de entrada del proceso de emulación (Núcleo CLI)."""
    parser = build_parser()
    _ = parser.parse_args()


if __name__ == "__main__":
    main()