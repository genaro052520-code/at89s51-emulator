"""Pruebas técnicas/unitarias de ALU, Pila (Stack) y clase ADM."""
from pathlib import Path
import pytest

from src.core.cpu import CPU8051
from src.ports.adm import ADM
from src.storage.memory import Memory8051


@pytest.fixture
def cpu_entorno(tmp_path: Path) -> CPU8051:
    """Crea una instancia aislada de CPU8051 respaldada por un archivo mmap temporal."""
    adm = ADM(state_file=tmp_path / "unit_ports.bin")
    memoria = Memory8051(adm=adm)
    cpu = CPU8051(memory=memoria)
    cpu.reset()
    yield cpu
    adm.close()


@pytest.fixture
def adm_aislado(tmp_path: Path) -> ADM:
    """Crea una instancia limpia de ADM para probar sus métodos de E/S."""
    adm = ADM(state_file=tmp_path / "adm_unit.bin")
    adm.reset()
    yield adm
    adm.close()


# ----------------------------------------------------------------------
# 1. Pruebas unitarias de ALU (ADD, SUBB, CY, AC, OV, P)
# ----------------------------------------------------------------------


def test_alu_add_acarreo_y_acarreo_auxiliar(cpu_entorno: CPU8051) -> None:
    """Verifica ADD A, #data con activación simultánea de CY, AC y paridad."""
    programa = bytes([0x74, 0xFF, 0x24, 0x02])
    cpu_entorno.memory.rom[0 : len(programa)] = programa

    cpu_entorno.run(max_instructions=2)

    assert cpu_entorno.acc == 0x01
    assert cpu_entorno.carry == 1
    assert cpu_entorno.aux_carry == 1
    assert cpu_entorno.overflow == 0
    assert cpu_entorno.parity == 1


def test_alu_add_desbordamiento_con_signo_ov(cpu_entorno: CPU8051) -> None:
    """Verifica desbordamiento aritmético OV=1 al sumar dos positivos (+127 + 1 = -128)."""
    programa = bytes([0x74, 0x7F, 0x24, 0x01])
    cpu_entorno.memory.rom[0 : len(programa)] = programa

    cpu_entorno.run(max_instructions=2)

    assert cpu_entorno.acc == 0x80
    assert cpu_entorno.carry == 0
    assert cpu_entorno.aux_carry == 1
    assert cpu_entorno.overflow == 1


def test_alu_subb_con_prestamo_y_overflow(cpu_entorno: CPU8051) -> None:
    """Verifica SUBB A, #data con préstamo (CY=1) y desbordamiento con signo (OV=1)."""
    programa = bytes([
        0xC3,              # CLR C
        0x74, 0x10,        # MOV A, #0x10
        0x94, 0x20,        # SUBB A, #0x20 -> ACC=0xF0, CY=1
        0xC3,              # CLR C
        0x74, 0x80,        # MOV A, #0x80
        0x94, 0x01,        # SUBB A, #0x01 -> ACC=0x7F, CY=0, OV=1
    ])
    cpu_entorno.memory.rom[0 : len(programa)] = programa

    cpu_entorno.run(max_instructions=3)
    assert cpu_entorno.acc == 0xF0
    assert cpu_entorno.carry == 1
    assert cpu_entorno.overflow == 0

    cpu_entorno.run(max_instructions=3)
    assert cpu_entorno.acc == 0x7F
    assert cpu_entorno.carry == 0
    assert cpu_entorno.overflow == 1


# ----------------------------------------------------------------------
# 2. Pruebas unitarias de Pila (PUSH / POP)
# ----------------------------------------------------------------------


def test_pila_push_y_pop_lifo(cpu_entorno: CPU8051) -> None:
    """Verifica el incremento/decremento de SP (base 0x07) y orden LIFO en PUSH/POP."""
    assert cpu_entorno.sp == 0x07

    programa = bytes([
        0x78, 0xAA,
        0x79, 0x55,
        0xC0, 0x00,
        0xC0, 0x01,
        0xD0, 0x02,
        0xD0, 0x03,
    ])
    cpu_entorno.memory.rom[0 : len(programa)] = programa

    cpu_entorno.run(max_instructions=4)
    assert cpu_entorno.sp == 0x09
    assert cpu_entorno.memory.ram[0x08] == 0xAA
    assert cpu_entorno.memory.ram[0x09] == 0x55

    cpu_entorno.run(max_instructions=2)
    assert cpu_entorno.sp == 0x07
    assert cpu_entorno.memory.read_register(2) == 0x55
    assert cpu_entorno.memory.read_register(3) == 0xAA


# ----------------------------------------------------------------------
# 3. Pruebas unitarias de todos los métodos de la clase ADM
# ----------------------------------------------------------------------


def test_adm_configurar_leer_y_escribir_digital(adm_aislado: ADM) -> None:
    """Verifica configurarPuerto, escribirPuertoDigital y leerPuertoDigital."""
    pin_p1_0 = 8  # P1.0 corresponde al índice 8

    assert adm_aislado.sentidos[pin_p1_0] == 0
    assert adm_aislado.leerPuertoDigital(pin_p1_0) == 1

    with pytest.raises(ValueError):
        adm_aislado.escribirPuertoDigital(pin_p1_0, 0)

    adm_aislado.configurarPuerto(pin_p1_0, 1)
    assert adm_aislado.sentidos[pin_p1_0] == 1

    adm_aislado.escribirPuertoDigital(pin_p1_0, 0)
    assert adm_aislado.puertos[pin_p1_0] == pytest.approx(0.0)
    assert adm_aislado.leerPuertoDigital(pin_p1_0) == 0

    adm_aislado.escribirPuertoDigital(pin_p1_0, 1)
    assert adm_aislado.puertos[pin_p1_0] == pytest.approx(5.0)
    assert adm_aislado.leerPuertoDigital(pin_p1_0) == 1


def test_adm_leer_y_escribir_analogico(adm_aislado: ADM) -> None:
    """Verifica escribirPuertoAnalogico y leerPuertoAnalogico con validación [0.0V, 5.0V]."""
    canal_aux = 32

    adm_aislado.configurarPuerto(canal_aux, 1)
    adm_aislado.escribirPuertoAnalogico(canal_aux, 3.35)
    assert adm_aislado.leerPuertoAnalogico(canal_aux) == pytest.approx(3.35)

    with pytest.raises(ValueError):
        adm_aislado.escribirPuertoAnalogico(canal_aux, 5.2)

    with pytest.raises(ValueError):
        adm_aislado.escribirPuertoAnalogico(canal_aux, -0.1)


def test_adm_bytes_puerto_quasi_bidireccional(adm_aislado: ADM) -> None:
    """Verifica leer_byte_puerto y escribir_byte_puerto respetando la lógica 8051."""
    adm_aislado.escribir_byte_puerto(1, 0xA5)
    assert adm_aislado.leer_byte_puerto(1) == 0xA5

    assert adm_aislado.sentidos[8] == 0
    assert adm_aislado.puertos[8] == pytest.approx(5.0)

    assert adm_aislado.sentidos[9] == 1
    assert adm_aislado.puertos[9] == pytest.approx(0.0)
