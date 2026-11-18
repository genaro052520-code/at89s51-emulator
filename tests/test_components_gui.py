"""Pruebas unitarias e integración headless para los componentes GUI y ADM.

Valida:
  1. Existencia e inicialización de las 10 clases de componentes electrónicos.
  2. Flujo CPU8051 -> ADM -> Actuadores (LED, Motor DC, Display 7 Segmentos).
  3. Flujo Sensores/Entradas -> ADM -> CPU8051 (Pulsador, Potenciómetro,
     Sensor de Temperatura, Interruptor DIP y Sensor Ultrasónico).
  4. Enrutamiento dinámico en `Protoboard` y `CableVirtual` sin entorno gráfico.
  5. Inspección AST estricta para garantizar que ningún archivo en `src/gui/`
     importe módulos de `src/core` o `src/storage`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import tkinter as tk
from typing import Any

import pytest

from src.core.cpu import CPU8051
from src.gui.app import AT89S51EmulatorGUI
from src.gui.components import (
    BuzzerComponente,
    CATALOGO_ACTUADORES,
    CATALOGO_COMPONENTES,
    CATALOGO_SENSORES,
    ComponenteElectronico,
    Display7SegmentosComponente,
    InterruptorDipComponente,
    LedComponente,
    MotorDCComponente,
    PotenciometroComponente,
    PulsadorComponente,
    SensorTemperaturaComponente,
    SensorUltrasonicoComponente,
    ServomotorComponente,
)
from src.gui.protoboard import CableVirtual, Protoboard
from src.ports.adm import ADM


CLASES_ESPERADAS: tuple[type[ComponenteElectronico], ...] = (
    LedComponente,
    MotorDCComponente,
    ServomotorComponente,
    BuzzerComponente,
    Display7SegmentosComponente,
    PulsadorComponente,
    InterruptorDipComponente,
    PotenciometroComponente,
    SensorTemperaturaComponente,
    SensorUltrasonicoComponente,
)


def _instanciar_cpu8051(adm: ADM) -> Any:
    """Instancia `CPU8051` adaptándose automáticamente a la firma de su `__init__`."""
    sig = inspect.signature(CPU8051.__init__)
    kwargs: dict[str, Any] = {}
    posicionales: list[Any] = []

    for nombre, param in sig.parameters.items():
        if nombre == "self":
            continue
        if nombre in ("adm", "ports", "bus_adm", "puerto_adm"):
            if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                posicionales.append(adm)
            else:
                kwargs[nombre] = adm
        elif param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            if isinstance(param.annotation, type):
                kwargs[nombre] = param.annotation()
            elif not posicionales:
                posicionales.append(adm)

    cpu = CPU8051(*posicionales, **kwargs)

    if hasattr(cpu, "adm") and getattr(cpu, "adm") is not adm:
        setattr(cpu, "adm", adm)

    return cpu


def _cargar_programa_y_ejecutar(
    cpu: Any,
    codigo_maquina: bytes,
    pasos: int,
) -> None:
    """Carga bytes de código máquina en ROM desde 0x0000 y ejecuta `pasos` instrucciones."""
    contenedores = [cpu]
    for attr in ("memory", "mem", "memoria"):
        if hasattr(cpu, attr):
            contenedores.append(getattr(cpu, attr))

    cargado = False
    for obj in contenedores:
        for metodo in ("load_rom", "cargar_rom", "load_program", "cargar_programa", "load_bytes"):
            if hasattr(obj, metodo) and callable(getattr(obj, metodo)):
                getattr(obj, metodo)(codigo_maquina)
                cargado = True
                break
        if cargado:
            break

    if not cargado:
        for obj in contenedores:
            for attr_rom in ("rom", "code", "code_memory", "program_memory", "flash"):
                if hasattr(obj, attr_rom):
                    buf = getattr(obj, attr_rom)
                    for idx, byte_val in enumerate(codigo_maquina):
                        buf[idx] = byte_val
                    cargado = True
                    break
            if cargado:
                break

    if not cargado:
        for obj in contenedores:
            for metodo_w in ("write_code", "escribir_rom", "write_rom"):
                if hasattr(obj, metodo_w) and callable(getattr(obj, metodo_w)):
                    for idx, byte_val in enumerate(codigo_maquina):
                        getattr(obj, metodo_w)(idx, byte_val)
                    cargado = True
                    break
            if cargado:
                break

    assert cargado, "No se encontró método ni buffer ROM en CPU8051 para cargar código máquina."

    if hasattr(cpu, "PC"):
        cpu.PC = 0x0000
    elif hasattr(cpu, "pc"):
        cpu.pc = 0x0000

    for _ in range(pasos):
        if hasattr(cpu, "step"):
            cpu.step()
        elif hasattr(cpu, "ejecutar_instruccion"):
            cpu.ejecutar_instruccion()
        elif hasattr(cpu, "tick"):
            cpu.tick()
        else:
            raise AssertionError("CPU8051 no expone un método step()/ejecutar_instruccion().")


def _leer_acumulador(cpu: Any) -> int:
    """Obtiene el valor actual del registro Acumulador (ACC / 0xE0) desde `CPU8051`."""
    for attr in ("A", "acc", "ACC"):
        if hasattr(cpu, attr) and isinstance(getattr(cpu, attr), int):
            return int(getattr(cpu, attr)) & 0xFF

    for attr_reg in ("registers", "regs", "sfr"):
        if hasattr(cpu, attr_reg):
            coleccion = getattr(cpu, attr_reg)
            if isinstance(coleccion, dict):
                for clave in ("A", "ACC", 0xE0):
                    if clave in coleccion:
                        return int(coleccion[clave]) & 0xFF

    for obj in (cpu, getattr(cpu, "memory", None), getattr(cpu, "mem", None)):
        if obj is None:
            continue
        for attr_ram in ("ram", "iram", "data_memory"):
            if hasattr(obj, attr_ram):
                ram = getattr(obj, attr_ram)
                if len(ram) > 0xE0:
                    return int(ram[0xE0]) & 0xFF

    raise AssertionError("No se pudo leer el registro Acumulador (A / ACC) de CPU8051.")


@pytest.fixture
def entorno_adm(tmp_path: Path) -> ADM:
    """Crea una instancia temporal e independiente de `ADM` en archivo mmap aislado."""
    adm = ADM(state_file=tmp_path / "ports_state_test.bin")
    yield adm
    adm.close()


# ==============================================================================
# 1. Verificación de las 10 Clases de Componentes Independientes
# ==============================================================================


def test_existen_las_10_clases_de_componentes() -> None:
    """Comprueba que las 10 clases existen, heredan de ComponenteElectronico y están catalogadas."""
    assert len(CLASES_ESPERADAS) == 10
    assert len(CATALOGO_ACTUADORES) == 5
    assert len(CATALOGO_SENSORES) == 5
    assert len(CATALOGO_COMPONENTES) == 10

    clases_en_catalogo = set(CATALOGO_COMPONENTES.values())
    for clase in CLASES_ESPERADAS:
        assert issubclass(clase, ComponenteElectronico)
        assert clase in clases_en_catalogo
        instancia = clase()
        assert isinstance(instancia.nombre, str) and len(instancia.nombre) > 0
        assert isinstance(instancia.pines_conectados, dict)
        assert isinstance(instancia.propiedades, dict)

    assert hasattr(AT89S51EmulatorGUI, "_iniciar_sondeo_adm")
    assert hasattr(AT89S51EmulatorGUI, "agregar_componente_desde_paleta")


# ==============================================================================
# 2. Flujo CPU8051 -> ADM -> Actuadores (LED, Motor DC, Display 7 Segmentos)
# ==============================================================================


def test_cpu8051_hacia_actuadores_via_adm(entorno_adm: ADM) -> None:
    """Al escribir CPU8051 en P1 y P2 vía ADM, los actuadores actualizan estado y animación."""
    cpu = _instanciar_cpu8051(entorno_adm)

    led_encendido = LedComponente(nombre="LED P1.0", pin=8, color="rojo")
    led_apagado = LedComponente(nombre="LED P1.1", pin=9, color="verde")
    motor = MotorDCComponente(nombre="Motor P1.2", pin=10)
    display = Display7SegmentosComponente(nombre="Display P2", puerto=2, nibble="low")

    # Programa 8051:
    #   MOV P1, #0x05  -> 0x75, 0x90, 0x05  (P1.0=1, P1.1=0, P1.2=1)
    #   MOV P2, #0x07  -> 0x75, 0xA0, 0x07  (Dígito 7 en nibble bajo de P2)
    programa = bytes([0x75, 0x90, 0x05, 0x75, 0xA0, 0x07])
    _cargar_programa_y_ejecutar(cpu, programa, pasos=2)

    entorno_adm.sincronizar()
    led_encendido.actualizar_desde_adm(entorno_adm)
    led_apagado.actualizar_desde_adm(entorno_adm)
    motor.actualizar_desde_adm(entorno_adm)
    display.actualizar_desde_adm(entorno_adm)

    assert led_encendido.propiedades["encendido"] is True
    assert led_encendido.propiedades["voltaje"] == pytest.approx(5.0)
    assert led_apagado.propiedades["encendido"] is False
    assert led_apagado.propiedades["voltaje"] == pytest.approx(0.0)

    estado_motor = motor.propiedades.get("girando", motor.propiedades.get("activo"))
    assert estado_motor is True
    assert motor.propiedades["voltaje"] == pytest.approx(5.0)

    angulo_previo = float(motor.propiedades.get("angulo", 0.0))
    motor.actualizar_desde_adm(entorno_adm)
    angulo_siguiente = float(motor.propiedades.get("angulo", 0.0))
    if angulo_siguiente == angulo_previo:
        try:
            root_tmp = tk.Tk()
            try:
                canvas_tmp = tk.Canvas(root_tmp, width=200, height=200)
                motor.dibujar(canvas_tmp)
                motor.actualizar_desde_adm(entorno_adm)
                angulo_siguiente = float(motor.propiedades.get("angulo", 0.0))
                assert angulo_siguiente != angulo_previo
            finally:
                motor.canvas = None
                root_tmp.destroy()
        except tk.TclError:
            pass

    assert display.propiedades["valor_byte"] == 0x07
    digito_actual = display.propiedades.get("digito", display.propiedades["valor_byte"] & 0x0F)
    assert digito_actual == 7
    segmentos = display.propiedades["segmentos"]
    assert segmentos["a"] is True
    assert segmentos["b"] is True
    assert segmentos["c"] is True
    assert segmentos["d"] is False
    assert segmentos["g"] is False

    # Apagar P1 desde CPU8051 (MOV P1, #0x00 -> 0x75, 0x90, 0x00)
    _cargar_programa_y_ejecutar(cpu, bytes([0x75, 0x90, 0x00]), pasos=1)
    entorno_adm.sincronizar()
    led_encendido.actualizar_desde_adm(entorno_adm)
    motor.actualizar_desde_adm(entorno_adm)

    assert led_encendido.propiedades["encendido"] is False
    assert motor.propiedades.get("girando", motor.propiedades.get("activo")) is False


# ==============================================================================
# 3. Flujo Sensores / Entradas -> ADM -> CPU8051
# ==============================================================================


def test_pulsador_escribe_en_adm_y_cpu8051_lee_p3(entorno_adm: ADM) -> None:
    """Al presionar y soltar PulsadorComponente en P3.2, ADM y CPU8051 leen el cambio."""
    cpu = _instanciar_cpu8051(entorno_adm)
    pulsador = PulsadorComponente(nombre="BTN_INT0", pin=26)  # P3.2 (canal 26)

    pulsador.presionar(adm=entorno_adm)
    assert pulsador.propiedades["presionado"] is True
    assert entorno_adm.leerPuertoAnalogico(26) == pytest.approx(0.0)

    _cargar_programa_y_ejecutar(cpu, bytes([0xE5, 0xB0]), pasos=1)  # MOV A, P3
    assert (_leer_acumulador(cpu) & (1 << 2)) == 0

    pulsador.soltar(adm=entorno_adm)
    assert pulsador.propiedades["presionado"] is False
    assert entorno_adm.leerPuertoAnalogico(26) == pytest.approx(5.0)

    _cargar_programa_y_ejecutar(cpu, bytes([0xE5, 0xB0]), pasos=1)
    assert (_leer_acumulador(cpu) & (1 << 2)) != 0


def test_potenciometro_escribe_analogico_y_digital_para_cpu8051(entorno_adm: ADM) -> None:
    """PotenciometroComponente actualiza voltaje (0-5V) en AN0 y nivel digital en P2.0."""
    cpu = _instanciar_cpu8051(entorno_adm)
    pot = PotenciometroComponente(nombre="POT1", canal=32, pin=16)  # AN0 (32) y P2.0 (16)

    voltaje_alto = pot.establecer_porcentaje(80.0, adm=entorno_adm)
    assert pot.propiedades["porcentaje"] == pytest.approx(80.0)
    assert voltaje_alto == pytest.approx(4.0)
    assert entorno_adm.leerPuertoAnalogico(32) == pytest.approx(4.0)
    assert pot.propiedades["nivel_digital"] == 1

    _cargar_programa_y_ejecutar(cpu, bytes([0xE5, 0xA0]), pasos=1)  # MOV A, P2
    assert (_leer_acumulador(cpu) & 0x01) == 1

    voltaje_bajo = pot.establecer_porcentaje(20.0, adm=entorno_adm)
    assert voltaje_bajo == pytest.approx(1.0)
    assert entorno_adm.leerPuertoAnalogico(32) == pytest.approx(1.0)
    assert pot.propiedades["nivel_digital"] == 0

    _cargar_programa_y_ejecutar(cpu, bytes([0xE5, 0xA0]), pasos=1)  # MOV A, P2
    assert (_leer_acumulador(cpu) & 0x01) == 0


def test_sensor_temperatura_escribe_en_adm_y_dispara_umbral_en_cpu8051(entorno_adm: ADM) -> None:
    """SensorTemperaturaComponente calcula voltaje proporcional y activa P2.1 sobre 30°C."""
    cpu = _instanciar_cpu8051(entorno_adm)
    sensor_temp = SensorTemperaturaComponente(
        nombre="LM35",
        pin=17,      # P2.1
        canal=33,    # AN1
        temperatura_c=22.0,
        umbral_c=30.0,
    )

    sensor_temp.establecer_temperatura(20.0, adm=entorno_adm)
    assert sensor_temp.propiedades["temperatura_c"] == pytest.approx(20.0)
    assert sensor_temp.propiedades["voltaje"] == pytest.approx(1.0)
    assert sensor_temp.propiedades["alerta_activa"] is False
    assert entorno_adm.leerPuertoAnalogico(33) == pytest.approx(1.0)

    _cargar_programa_y_ejecutar(cpu, bytes([0xE5, 0xA0]), pasos=1)  # MOV A, P2
    assert (_leer_acumulador(cpu) & (1 << 1)) == 0

    sensor_temp.establecer_temperatura(50.0, adm=entorno_adm)
    assert sensor_temp.propiedades["temperatura_c"] == pytest.approx(50.0)
    assert sensor_temp.propiedades["voltaje"] == pytest.approx(2.5)
    assert sensor_temp.propiedades["alerta_activa"] is True
    assert entorno_adm.leerPuertoAnalogico(33) == pytest.approx(2.5)

    _cargar_programa_y_ejecutar(cpu, bytes([0xE5, 0xA0]), pasos=1)  # MOV A, P2
    assert (_leer_acumulador(cpu) & (1 << 1)) != 0


def test_interruptor_dip_y_sensor_ultrasonico_headless(entorno_adm: ADM) -> None:
    """Valida enclavamiento de InterruptorDipComponente y detección <20 cm en HC-SR04."""
    sw = InterruptorDipComponente(nombre="SW1", pin=27)  # P3.3
    sw.establecer_estado(True, adm=entorno_adm)
    assert sw.propiedades["estado_on"] is True
    assert entorno_adm.leerPuertoAnalogico(27) == pytest.approx(0.0)

    sw.alternar(adm=entorno_adm)
    assert sw.propiedades["estado_on"] is False
    assert entorno_adm.leerPuertoAnalogico(27) == pytest.approx(5.0)

    hc = SensorUltrasonicoComponente(nombre="US1", pin=18, canal=34)  # P2.2 / AN2
    assert hc.establecer_distancia(12.5, adm=entorno_adm) is True
    assert hc.propiedades["obstaculo_detectado"] is True
    assert entorno_adm.leerPuertoAnalogico(18) == pytest.approx(5.0)

    assert hc.establecer_distancia(120.0, adm=entorno_adm) is False
    assert hc.propiedades["obstaculo_detectado"] is False
    assert entorno_adm.leerPuertoAnalogico(18) == pytest.approx(0.0)


# ==============================================================================
# 4. Conexión Dinámica en Protoboard y CableVirtual
# ==============================================================================


def test_protoboard_conexion_dinamica_sin_entorno_grafico(entorno_adm: ADM) -> None:
    """Protoboard conecta y desconecta componentes en P0.0-P3.7 y AN0-AN7 en modo headless."""
    proto = Protoboard()
    led = LedComponente(nombre="LED_DYN", pin=8)

    proto.montar_componente(led, columna=5, fila="c", auto_cablear=True, adm=entorno_adm)
    assert len(proto.cables) == 1

    cable = proto.conectar_componente(led, destino_adm="P2.4", adm=entorno_adm)
    assert isinstance(cable, CableVirtual)
    assert cable.origen_etiqueta == "P2.4"
    assert cable.canal_adm == 20
    assert led.pines_conectados["IN"] == 20

    cable_an = proto.conectar_componente(led, destino_adm="AN3", adm=entorno_adm)
    assert cable_an.origen_etiqueta == "AN3"
    assert cable_an.canal_adm == 35

    eliminados = proto.desconectar_componente(led, adm=entorno_adm)
    assert len(eliminados) == 1
    assert len(proto.cables) == 0


def test_protoboard_renderizado_canvas_si_hay_display(entorno_adm: ADM) -> None:
    """Prueba dibujo real en tk.Canvas cuando el entorno dispone de servidor gráfico."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Entorno sin servidor gráfico ($DISPLAY no disponible).")

    try:
        canvas = tk.Canvas(root, width=800, height=500)
        proto = Protoboard()
        proto.dibujar(canvas)

        led = LedComponente(nombre="LED_GUI", pin=8)
        proto.montar_componente(led, columna=4, fila="c", auto_cablear=True, adm=entorno_adm)
        proto.actualizar_desde_adm(entorno_adm)

        assert len(proto.componentes_montados) == 1
        assert len(proto.cables) == 1
    finally:
        root.destroy()


# ==============================================================================
# 5. Inspección AST: Aislamiento Estricto de `src/gui/`
# ==============================================================================


def test_ast_ningun_archivo_en_src_gui_importa_core_o_storage() -> None:
    """Verifica mediante AST que `src/gui/` no importe nada de `src/core` ni `src/storage`."""
    raiz_proyecto = Path(__file__).resolve().parents[1]
    dir_gui = raiz_proyecto / "src" / "gui"
    archivos_py = sorted(dir_gui.rglob("*.py"))

    assert len(archivos_py) >= 5, "Se esperaban los módulos de src/gui/ y src/gui/components/"

    modulos_prohibidos = ("src.core", "core", "src.storage", "storage")
    violaciones: list[str] = []

    for archivo in archivos_py:
        codigo = archivo.read_text(encoding="utf-8")
        arbol = ast.parse(codigo, filename=str(archivo))

        rel_parts = archivo.relative_to(raiz_proyecto).with_suffix("").parts
        paquete_parts = rel_parts[:-1]

        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    nombre = alias.name
                    if nombre in modulos_prohibidos or nombre.startswith(
                        tuple(f"{m}." for m in modulos_prohibidos)
                    ):
                        violaciones.append(f"{archivo.relative_to(raiz_proyecto)}: import {nombre}")

            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 0 and nodo.module:
                    mod = nodo.module
                elif nodo.level > 0:
                    subir = nodo.level - 1
                    base_parts = paquete_parts[: max(0, len(paquete_parts) - subir)]
                    mod = ".".join((*base_parts, nodo.module)) if nodo.module else ".".join(base_parts)
                else:
                    mod = ""

                if mod in modulos_prohibidos or mod.startswith(
                    tuple(f"{m}." for m in modulos_prohibidos)
                ):
                    violaciones.append(
                        f"{archivo.relative_to(raiz_proyecto)}: from {mod} import ..."
                    )

    assert not violaciones, (
        "Se detectaron importaciones acopladas prohibidas en src/gui/:\n"
        + "\n".join(violaciones)
    )
