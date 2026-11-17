"""Pruebas de sistema extremo a extremo (E2E) cargando firmware Intel HEX real."""
from pathlib import Path

from src.core.cpu import CPU8051
from src.ports.adm import ADM
from src.storage.memory import Memory8051

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware_examples"


def test_sistema_e2e_button_to_led_hex(tmp_path: Path) -> None:
    """Carga button_to_led.hex, simula pulsación en P3.2 desde ADM y valida LED P1.0."""
    hex_path = FIRMWARE_DIR / "button_to_led.hex"
    assert hex_path.exists(), f"No se encontró el firmware de prueba: {hex_path}"

    archivo_ipc = tmp_path / "e2e_ports.bin"
    pin_p1_0 = 8   # LED de salida (P1.0)
    pin_p3_2 = 26  # Botón de entrada (P3.2 / INT0)

    with ADM(state_file=archivo_ipc) as adm_core, ADM(state_file=archivo_ipc) as adm_gui:
        memoria = Memory8051(adm=adm_core)
        cpu = CPU8051(memory=memoria)
        cpu.reset()

        bytes_cargados = memoria.load_hex(hex_path)
        assert bytes_cargados == 16

        # 1. Estado inicial sin presionar botón (P3.2 = 1 por pull-up)
        cpu.run(max_instructions=10)
        assert adm_gui.leerPuertoDigital(pin_p3_2) == 1
        assert adm_gui.leerPuertoDigital(pin_p1_0) == 0

        # 2. Simular usuario presionando pulsador conectado a P3.2 en la GUI (0V)
        adm_gui.inyectar_estimulo_externo(pin_p3_2, 0)
        cpu.run(max_instructions=10)
        assert adm_gui.leerPuertoDigital(pin_p1_0) == 1

        # 3. Simular usuario soltando el pulsador (regresa a pull-up 5V)
        adm_gui.liberar_estimulo_externo(pin_p3_2)
        cpu.run(max_instructions=10)
        assert adm_gui.leerPuertoDigital(pin_p1_0) == 0
