"""Capa intermedia de administración de puertos y estado compartido (Clase ADM)."""

from pathlib import Path


class ADM:
    """Administrador de Puertos y Memoria Compartida entre el Núcleo 8051 y la GUI.

    Gestiona un bloque de memoria mapeada (mmap) y respaldos de estado en JSON para
    sincronizar los puertos bidireccionales (P0, P1, P2, P3) y señales de control
    sin acoplamiento directo entre procesos.
    """

    def __init__(self, shm_path: Path | str = "runtime_state/at89s51.shm") -> None:
        self.shm_path = Path(shm_path)

    def initialize_bus(self) -> None:
        """Inicializa la región de memoria compartida con valores de reset del AT89S51."""
        pass

    def write_port_latch(self, port: int, value: int) -> None:
        """Escribe el valor del latch interno desde el núcleo hacia la capa ADM."""
        pass

    def read_port_pins(self, port: int) -> int:
        """Lee el estado eléctrico efectivo de los 8 pines de un puerto (0 a 3)."""
        pass

    def set_external_pin(self, port: int, bit: int, level: int) -> None:
        """Permite a la GUI o periféricos inyectar estímulos externos en un pin."""
        pass

    def close(self) -> None:
        """Libera los descriptores de archivo y recursos mmap."""
        pass