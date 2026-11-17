"""Pruebas de integración entre el núcleo CPU8051 y la capa compartida ADM."""
from pathlib import Path
import pytest

from src.core.cpu import CPU8051
from src.ports.adm import ADM
from src.storage.memory import Memory8051


@pytest.fixture
def par_procesos_adm(tmp_path: Path) -> tuple[CPU8051, ADM]:
    """Instancia un núcleo CPU y una segunda instancia ADM independiente (simulando GUI)."""
    archivo_ipc = tmp_path / "integration_ports.bin"
    adm_core = ADM(state_file=archivo_ipc)
    memoria = Memory8051(adm=adm_core)
    cpu = CPU8051(memory=memoria)
    cpu.reset()

    adm_gui = ADM(state_file=archivo_ipc)
    yield cpu, adm_gui

    adm_gui.close()
    adm_core.close()


def test_escritura_p1_en_cpu_visible_en_segunda_instancia_adm(
    par_procesos_adm: tuple[CPU8051, ADM],
) -> None:
    """Valida que MOV P1 y SETB/CLR P1.x actualicen mmap para el proceso GUI."""
    cpu, adm_gui = par_procesos_adm

    programa = bytes([
        0x75, 0x90, 0x00,
        0xD2, 0x90,
        0x75, 0x90, 0xFF,
    ])
    cpu.memory.rom[0 : len(programa)] = programa

    cpu.step()  # MOV P1, #0x00
    assert adm_gui.leer_byte_puerto(1) == 0x00

    cpu.step()  # SETB P1.0
    assert adm_gui.leer_byte_puerto(1) == 0x01
    assert adm_gui.leerPuertoDigital(8) == 1

    cpu.step()  # MOV P1, #0xFF
    assert adm_gui.leer_byte_puerto(1) == 0xFF


def test_estimulo_externo_en_p3_leido_por_cpu(
    par_procesos_adm: tuple[CPU8051, ADM],
) -> None:
    """Valida que un estímulo aplicado en ADM desde la GUI sea leído por MOV A, P3."""
    cpu, adm_gui = par_procesos_adm

    programa = bytes([0x75, 0xB0, 0xFF, 0xE5, 0xB0])
    cpu.memory.rom[0 : len(programa)] = programa

    cpu.step()  # MOV P3, #0xFF
    adm_gui.inyectar_estimulo_externo(26, 0)

    cpu.step()  # MOV A, P3
    assert cpu.acc == 0xFB
