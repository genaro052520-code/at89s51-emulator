"""src/storage/ram.py - Memoria de datos interna (128 bytes) del AT89S51."""


class InternalRAM:
    """RAM interna de 128 bytes (0x00 - 0x7F): bancos R0-R7, área de bits y pila."""

    SIZE_BYTES: int = 128

    def __init__(self) -> None:
        self._memory = bytearray(self.SIZE_BYTES)

    def read_byte(self, address: int) -> int:
        """Lee un byte de la RAM interna."""
        pass

    def write_byte(self, address: int, value: int) -> None:
        """Escribe un byte en la RAM interna."""
        pass