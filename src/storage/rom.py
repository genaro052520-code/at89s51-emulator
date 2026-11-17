"""src/storage/rom.py - Memoria de programa Flash ROM (4 KB) del AT89S51."""

from pathlib import Path


class ProgramROM:
    """Almacenamiento no volátil de 4096 bytes (0x0000 - 0x0FFF)."""

    SIZE_BYTES: int = 4096

    def __init__(self) -> None:
        self._memory = bytearray(self.SIZE_BYTES)

    def load_hex(self, hex_path: Path | str) -> None:
        """Carga un archivo en formato Intel HEX en la memoria de programa."""
        pass

    def read_byte(self, address: int) -> int:
        """Retorna el byte ubicado en la dirección de 16 bits indicada."""
        pass