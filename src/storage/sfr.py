"""src/storage/sfr.py - Registros de Funciones Especiales (0x80 - 0xFF)."""


class SpecialFunctionRegisters:
    """Gestiona A, B, PSW, SP, DPL, DPH y los registros de puerto P0, P1, P2, P3."""

    def __init__(self) -> None:
        self._registers: dict[int, int] = {}

    def reset(self) -> None:
        """Restaura los valores iniciales tras un reset por hardware del AT89S51."""
        pass