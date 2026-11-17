"""src/core/cpu.py - Unidad Central de Procesamiento del AT89S51."""

from src.ports.adm import ADM
from src.storage.ram import InternalRAM
from src.storage.rom import ProgramROM
from src.storage.sfr import SpecialFunctionRegisters


class CPU8051:
    """Controlador principal del ciclo de instrucción Harvard del 8051."""

    def __init__(
        self,
        rom: ProgramROM,
        ram: InternalRAM,
        sfr: SpecialFunctionRegisters,
        adm: ADM,
    ) -> None:
        self.rom = rom
        self.ram = ram
        self.sfr = sfr
        self.adm = adm
        self.pc: int = 0x0000

    def reset(self) -> None:
        """Reinicia PC a 0x0000 y sincroniza el estado inicial con ADM."""
        pass

    def step(self) -> int:
        """Ejecuta una instrucción completa y retorna los ciclos máquina consumidos."""
        pass