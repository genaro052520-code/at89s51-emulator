"""Paquete de componentes electrónicos virtuales estilo Tinkercad para el AT89S51."""

from src.gui.components.actuadores import (
    BuzzerComponente,
    Display7SegmentosComponente,
    LedComponente,
    MotorDCComponente,
    ServomotorComponente,
)
from src.gui.components.base import ComponenteElectronico
from src.gui.components.sensores import (
    InterruptorDipComponente,
    PotenciometroComponente,
    PulsadorComponente,
    SensorTemperaturaComponente,
    SensorUltrasonicoComponente,
)

CATALOGO_ACTUADORES: dict[str, type[ComponenteElectronico]] = {
    "LED con Resistencia": LedComponente,
    "Motor DC": MotorDCComponente,
    "Servomotor (0°-180°)": ServomotorComponente,
    "Buzzer Piezoeléctrico": BuzzerComponente,
    "Display 7 Segmentos": Display7SegmentosComponente,
}

CATALOGO_SENSORES: dict[str, type[ComponenteElectronico]] = {
    "Pulsador Táctil": PulsadorComponente,
    "Interruptor DIP": InterruptorDipComponente,
    "Potenciómetro (0-5V)": PotenciometroComponente,
    "Sensor Temperatura (LM35/DHT)": SensorTemperaturaComponente,
    "Sensor Ultrasónico (HC-SR04)": SensorUltrasonicoComponente,
}

CATALOGO_COMPONENTES: dict[str, type[ComponenteElectronico]] = {
    **CATALOGO_ACTUADORES,
    **CATALOGO_SENSORES,
}

__all__ = [
    "ComponenteElectronico",
    "LedComponente",
    "MotorDCComponente",
    "ServomotorComponente",
    "BuzzerComponente",
    "Display7SegmentosComponente",
    "PulsadorComponente",
    "InterruptorDipComponente",
    "PotenciometroComponente",
    "SensorTemperaturaComponente",
    "SensorUltrasonicoComponente",
    "CATALOGO_ACTUADORES",
    "CATALOGO_SENSORES",
    "CATALOGO_COMPONENTES",
]
