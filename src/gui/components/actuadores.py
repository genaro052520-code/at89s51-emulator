"""Actuadores electrónicos virtuales animados para el banco de trabajo del AT89S51.

Implementa 5 dispositivos de salida independientes que leen niveles digitales o
voltajes analógicos exclusivamente desde `ADM` (`src/ports/adm.py`):
1. `LedComponente`: Diodo emisor de luz con resistencia limitadora y halo.
2. `MotorDCComponente`: Motor de corriente continua con rotor giratorio animado.
3. `ServomotorComponente`: Servomotor con brazo indicador de 0° a 180°.
4. `BuzzerComponente`: Bocina piezoeléctrica con ondas sonoras animadas.
5. `Display7SegmentosComponente`: Display de 7 segmentos + punto decimal (puerto/nibble).
"""

from __future__ import annotations

import math
import tkinter as tk

from src.gui.components.base import ComponenteElectronico
from src.ports.adm import ADM


def _formatear_pin_8051(pin: int) -> str:
    """Convierte un índice de canal ADM (0-39) en su etiqueta física del AT89S51."""
    if 0 <= pin < 32:
        puerto = pin // 8
        bit = pin % 8
        return f"P{puerto}.{bit}"
    if 32 <= pin < 40:
        return f"AI{pin - 32}"
    return f"CH{pin}"


class LedComponente(ComponenteElectronico):
    """LED virtual en serie con resistencia limitadora y halo luminoso configurable."""

    PALETA_COLORES: dict[str, tuple[str, str, str, str]] = {
        "rojo": ("#FF1744", "#FF8A80", "#5C0A1B", "#3B1219"),
        "verde": ("#00E676", "#B9F6CA", "#064E3B", "#0F2E22"),
        "azul": ("#2979FF", "#82B1FF", "#0C2D6B", "#102142"),
        "amarillo": ("#FFEA00", "#FFFF8D", "#574B00", "#36300A"),
        "naranja": ("#FF9100", "#FFD180", "#5C3000", "#382008"),
        "blanco": ("#F8FAFC", "#FFFFFF", "#475569", "#334155"),
    }

    def __init__(
        self,
        nombre: str = "LED",
        pin: int = 8,
        x: float = 0.0,
        y: float = 0.0,
        color: str = "rojo",
        activo_alto: bool = True,
        resistencia_ohms: int = 220,
    ) -> None:
        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"IN": pin},
            propiedades={
                "pin": pin,
                "color": color.lower(),
                "activo_alto": activo_alto,
                "resistencia_ohms": resistencia_ohms,
                "encendido": False,
                "voltaje": 0.0,
            },
        )
        self._id_halo: int | None = None
        self._id_lente: int | None = None
        self._id_reflejo: int | None = None
        self._id_etiqueta: int | None = None

    def _obtener_paleta(self) -> tuple[str, str, str, str]:
        color_key = str(self.propiedades.get("color", "rojo")).lower()
        return self.PALETA_COLORES.get(color_key, self.PALETA_COLORES["rojo"])

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo
        _, _, _, fill_off = self._obtener_paleta()

        self.items_canvas.append(
            canvas.create_line(cx - 58, cy, cx - 42, cy, fill="#94A3B8", width=2, tags=(tag,))
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx - 63, cy - 5, cx - 53, cy + 5,
                fill="#F59E0B", outline="#1E293B", width=1.5, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 42, cy - 7, cx - 10, cy + 7,
                fill="#E7C697", outline="#78350F", width=1.5, tags=(tag,),
            )
        )
        bandas = [(-36, "#DC2626"), (-30, "#DC2626"), (-24, "#78350F"), (-16, "#EAB308")]
        for offset_x, color_banda in bandas:
            self.items_canvas.append(
                canvas.create_rectangle(
                    cx + offset_x, cy - 6.5, cx + offset_x + 3, cy + 6.5,
                    fill=color_banda, outline="", tags=(tag,),
                )
            )
        self.items_canvas.append(
            canvas.create_line(cx - 10, cy, cx + 6, cy, fill="#94A3B8", width=2, tags=(tag,))
        )
        self._id_halo = canvas.create_oval(
            cx + 2, cy - 22, cx + 46, cy + 22,
            fill="", outline="", width=2, tags=(tag,),
        )
        self.items_canvas.append(self._id_halo)
        self._id_lente = canvas.create_oval(
            cx + 10, cy - 14, cx + 38, cy + 14,
            fill=fill_off, outline="#64748B", width=2, tags=(tag,),
        )
        self.items_canvas.append(self._id_lente)
        self._id_reflejo = canvas.create_arc(
            cx + 14, cy - 10, cx + 32, cy + 8,
            start=45, extent=90, style=tk.ARC, outline="#CBD5E1", width=1.5, tags=(tag,),
        )
        self.items_canvas.append(self._id_reflejo)
        self.items_canvas.append(
            canvas.create_line(cx + 38, cy, cx + 56, cy, fill="#94A3B8", width=2, tags=(tag,))
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx + 51, cy - 5, cx + 61, cy + 5,
                fill="#3B82F6", outline="#1E293B", width=1.5, tags=(tag,),
            )
        )
        pin = self.pines_conectados["IN"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 26,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

    def actualizar_desde_adm(self, adm: ADM) -> None:
        pin = self.pines_conectados["IN"]
        voltaje = adm.leerPuertoAnalogico(pin)
        nivel_digital = adm.leerPuertoDigital(pin) if pin < ADM.TOTAL_PINES_DIGITALES else (
            1 if voltaje > ADM.UMBRAL_LOGICO else 0
        )

        activo_alto = bool(self.propiedades.get("activo_alto", True))
        alto = (voltaje > ADM.UMBRAL_LOGICO) or (nivel_digital == 1)
        encendido = alto if activo_alto else (not alto)

        self.propiedades["voltaje"] = voltaje
        self.propiedades["encendido"] = encendido

        if self.canvas is None or self._id_lente is None or self._id_halo is None:
            return

        fill_on, outline_on, halo_on, fill_off = self._obtener_paleta()
        if encendido:
            self.canvas.itemconfig(self._id_halo, fill=halo_on, outline=outline_on)
            self.canvas.itemconfig(self._id_lente, fill=fill_on, outline="#FFFFFF")
            if self._id_reflejo is not None:
                self.canvas.itemconfig(self._id_reflejo, outline="#FFFFFF")
        else:
            self.canvas.itemconfig(self._id_halo, fill="", outline="")
            self.canvas.itemconfig(self._id_lente, fill=fill_off, outline="#64748B")
            if self._id_reflejo is not None:
                self.canvas.itemconfig(self._id_reflejo, outline="#94A3B8")

        if self._id_etiqueta is not None:
            estado_txt = "ON" if encendido else "OFF"
            self.canvas.itemconfig(
                self._id_etiqueta,
                text=f"{self.nombre} [{_formatear_pin_8051(pin)}] {estado_txt}",
            )

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        return {
            "IN": (self.x - 58.0, self.y),
            "GND": (self.x + 56.0, self.y),
        }


class MotorDCComponente(ComponenteElectronico):
    """Motor de corriente continua virtual que gira sus aspas mientras su pin está activo."""

    def __init__(
        self,
        nombre: str = "Motor DC",
        pin: int = 9,
        x: float = 0.0,
        y: float = 0.0,
        paso_angulo: float = 22.0,
    ) -> None:
        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"IN": pin},
            propiedades={
                "pin": pin,
                "activo": False,
                "angulo": 0.0,
                "paso_angulo": float(paso_angulo),
                "voltaje": 0.0,
            },
        )
        self._ids_aspas: list[int] = []
        self._id_arco_giro: int | None = None
        self._id_led_estado: int | None = None
        self._id_etiqueta: int | None = None

    def _coordenadas_aspa(self, cx: float, cy: float, angulo_grados: float) -> list[float]:
        rad = math.radians(angulo_grados)
        perp = rad + math.pi / 2.0
        r_in, r_out = 6.0, 23.0
        ancho = 3.2

        p1x = cx + r_in * math.cos(rad) - ancho * math.cos(perp)
        p1y = cy + r_in * math.sin(rad) - ancho * math.sin(perp)
        p2x = cx + r_out * math.cos(rad) - (ancho * 0.7) * math.cos(perp)
        p2y = cy + r_out * math.sin(rad) - (ancho * 0.7) * math.sin(perp)
        p3x = cx + r_out * math.cos(rad) + (ancho * 0.7) * math.cos(perp)
        p3y = cy + r_out * math.sin(rad) + (ancho * 0.7) * math.sin(perp)
        p4x = cx + r_in * math.cos(rad) + ancho * math.cos(perp)
        p4y = cy + r_in * math.sin(rad) + ancho * math.sin(perp)
        return [p1x, p1y, p2x, p2y, p3x, p3y, p4x, p4y]

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self._ids_aspas.clear()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 42, cy - 12, cx + 42, cy + 12,
                fill="#475569", outline="#1E293B", width=1.5, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx - 47, cy - 5, cx - 37, cy + 5,
                fill="#EF4444", outline="#0F172A", width=1.5, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx + 37, cy - 5, cx + 47, cy + 5,
                fill="#3B82F6", outline="#0F172A", width=1.5, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx - 32, cy - 32, cx + 32, cy + 32,
                fill="#334155", outline="#94A3B8", width=2, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx - 26, cy - 26, cx + 26, cy + 26,
                fill="#1E293B", outline="#475569", width=1, tags=(tag,),
            )
        )
        self._id_arco_giro = canvas.create_arc(
            cx - 23, cy - 23, cx + 23, cy + 23,
            start=20, extent=130, style=tk.ARC, outline="", width=2, tags=(tag,),
        )
        self.items_canvas.append(self._id_arco_giro)

        angulo_base = float(self.propiedades.get("angulo", 0.0))
        for idx in range(3):
            coords = self._coordenadas_aspa(cx, cy, angulo_base + idx * 120.0)
            aspa_id = canvas.create_polygon(
                coords, fill="#38BDF8", outline="#0284C7", width=1, tags=(tag,)
            )
            self._ids_aspas.append(aspa_id)
            self.items_canvas.append(aspa_id)

        self.items_canvas.append(
            canvas.create_oval(
                cx - 7, cy - 7, cx + 7, cy + 7,
                fill="#CBD5E1", outline="#0F172A", width=1.5, tags=(tag,),
            )
        )
        self._id_led_estado = canvas.create_oval(
            cx - 3, cy - 29, cx + 3, cy - 23,
            fill="#475569", outline="", tags=(tag,),
        )
        self.items_canvas.append(self._id_led_estado)

        pin = self.pines_conectados["IN"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 44,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}] STOP",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

    def actualizar_desde_adm(self, adm: ADM) -> None:
        pin = self.pines_conectados["IN"]
        voltaje = adm.leerPuertoAnalogico(pin)
        nivel = adm.leerPuertoDigital(pin) if pin < ADM.TOTAL_PINES_DIGITALES else (
            1 if voltaje > ADM.UMBRAL_LOGICO else 0
        )

        activo = (voltaje > ADM.UMBRAL_LOGICO) or (nivel == 1)
        self.propiedades["voltaje"] = voltaje
        self.propiedades["activo"] = activo

        if self.canvas is None:
            return

        if activo:
            factor_vel = max(0.5, voltaje / ADM.VOLTAJE_MAX)
            paso = float(self.propiedades.get("paso_angulo", 22.0)) * factor_vel
            nuevo_angulo = (float(self.propiedades.get("angulo", 0.0)) + paso) % 360.0
            self.propiedades["angulo"] = nuevo_angulo

            bbox = self.canvas.bbox(self.tag_grupo)
            cx_actual, cy_actual = self.x, self.y
            if bbox is not None:
                cx_actual = (bbox[0] + bbox[2]) / 2.0
                cy_actual = self.y

            for idx, aspa_id in enumerate(self._ids_aspas):
                coords = self._coordenadas_aspa(cx_actual, cy_actual, nuevo_angulo + idx * 120.0)
                self.canvas.coords(aspa_id, *coords)

            if self._id_arco_giro is not None:
                self.canvas.itemconfig(
                    self._id_arco_giro,
                    outline="#7DD3FC",
                    start=(nuevo_angulo * 1.5) % 360.0,
                )
            if self._id_led_estado is not None:
                self.canvas.itemconfig(self._id_led_estado, fill="#00E676")
            if self._id_etiqueta is not None:
                self.canvas.itemconfig(
                    self._id_etiqueta,
                    text=f"{self.nombre} [{_formatear_pin_8051(pin)}] RUN",
                )
        else:
            if self._id_arco_giro is not None:
                self.canvas.itemconfig(self._id_arco_giro, outline="")
            if self._id_led_estado is not None:
                self.canvas.itemconfig(self._id_led_estado, fill="#475569")
            if self._id_etiqueta is not None:
                self.canvas.itemconfig(
                    self._id_etiqueta,
                    text=f"{self.nombre} [{_formatear_pin_8051(pin)}] STOP",
                )

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        return {
            "IN": (self.x - 42.0, self.y),
            "GND": (self.x + 42.0, self.y),
        }


class ServomotorComponente(ComponenteElectronico):
    """Servomotor virtual con brazo indicador angular de 0° a 180°."""

    def __init__(
        self,
        nombre: str = "Servomotor",
        pin: int = 10,
        x: float = 0.0,
        y: float = 0.0,
        canal_analogico: int | None = None,
    ) -> None:
        canal_control = canal_analogico if canal_analogico is not None else pin
        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"SIG": canal_control},
            propiedades={
                "pin": canal_control,
                "angulo": 0.0,
                "angulo_objetivo": 0.0,
                "voltaje": 0.0,
            },
        )
        self._id_brazo: int | None = None
        self._id_texto_angulo: int | None = None
        self._id_etiqueta: int | None = None

    def _coordenadas_brazo(self, eje_x: float, eje_y: float, angulo_grados: float) -> list[float]:
        rad = math.radians(180.0 - angulo_grados)
        perp = rad + math.pi / 2.0
        largo = 30.0
        r_base = 6.0
        r_punta = 3.0

        punta_x = eje_x + largo * math.cos(rad)
        punta_y = eje_y - largo * math.sin(rad)

        return [
            eje_x + r_base * math.cos(perp),
            eje_y - r_base * math.sin(perp),
            punta_x + r_punta * math.cos(perp),
            punta_y - r_punta * math.sin(perp),
            punta_x - r_punta * math.cos(perp),
            punta_y + r_punta * math.sin(perp),
            eje_x - r_base * math.cos(perp),
            eje_y + r_base * math.sin(perp),
        ]

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 46, cy + 4, cx + 46, cy + 12,
                fill="#1D4ED8", outline="#1E3A8A", width=1, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 36, cy - 10, cx + 36, cy + 34,
                fill="#2563EB", outline="#93C5FD", width=1.5, tags=(tag,),
            )
        )
        colores_cables = [(-12, "#3B82F6"), (0, "#EF4444"), (12, "#F59E0B")]
        for offset_x, color_cable in colores_cables:
            self.items_canvas.append(
                canvas.create_line(
                    cx + offset_x, cy + 34, cx + offset_x, cy + 46,
                    fill=color_cable, width=2.5, tags=(tag,),
                )
            )
        self.items_canvas.append(
            canvas.create_oval(
                cx + 7, cy + 42, cx + 17, cy + 52,
                fill="#F59E0B", outline="#0F172A", width=1.5, tags=(tag,),
            )
        )

        eje_x, eje_y = cx - 12, cy - 10
        self.items_canvas.append(
            canvas.create_arc(
                eje_x - 34, eje_y - 34, eje_x + 34, eje_y + 34,
                start=0, extent=180, style=tk.ARC, outline="#64748B", dash=(3, 2), tags=(tag,),
            )
        )

        angulo_ini = float(self.propiedades.get("angulo", 0.0))
        self._id_brazo = canvas.create_polygon(
            self._coordenadas_brazo(eje_x, eje_y, angulo_ini),
            fill="#F8FAFC", outline="#0F172A", width=1.5, tags=(tag,),
        )
        self.items_canvas.append(self._id_brazo)

        self.items_canvas.append(
            canvas.create_oval(
                eje_x - 5, eje_y - 5, eje_x + 5, eje_y + 5,
                fill="#94A3B8", outline="#0F172A", width=1, tags=(tag,),
            )
        )
        self._id_texto_angulo = canvas.create_text(
            cx + 12,
            cy + 16,
            text=f"{int(round(angulo_ini))}°",
            fill="#FFFFFF",
            font=("Consolas", 10, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_texto_angulo)

        pin = self.pines_conectados["SIG"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 62,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

    def actualizar_desde_adm(self, adm: ADM) -> None:
        canal = self.pines_conectados["SIG"]
        voltaje = adm.leerPuertoAnalogico(canal)

        if canal < ADM.TOTAL_PINES_DIGITALES and voltaje in (ADM.VOLTAJE_BAJO, ADM.VOLTAJE_ALTO):
            nivel = adm.leerPuertoDigital(canal)
            angulo_objetivo = 180.0 if nivel == 1 else 0.0
        else:
            volt_acotado = max(ADM.VOLTAJE_MIN, min(ADM.VOLTAJE_MAX, voltaje))
            angulo_objetivo = (volt_acotado / ADM.VOLTAJE_MAX) * 180.0

        self.propiedades["voltaje"] = voltaje
        self.propiedades["angulo_objetivo"] = angulo_objetivo

        angulo_actual = float(self.propiedades.get("angulo", 0.0))
        diferencia = angulo_objetivo - angulo_actual
        if abs(diferencia) <= 36.0:
            angulo_nuevo = angulo_objetivo
        else:
            angulo_nuevo = angulo_actual + math.copysign(36.0, diferencia)

        self.propiedades["angulo"] = angulo_nuevo

        if self.canvas is None:
            return

        eje_x, eje_y = self.x - 12.0, self.y - 10.0
        if self._id_brazo is not None:
            coords = self._coordenadas_brazo(eje_x, eje_y, angulo_nuevo)
            self.canvas.coords(self._id_brazo, *coords)

        if self._id_texto_angulo is not None:
            self.canvas.itemconfig(self._id_texto_angulo, text=f"{int(round(angulo_nuevo))}°")

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        return {
            "GND": (self.x - 12.0, self.y + 46.0),
            "VCC": (self.x, self.y + 46.0),
            "SIG": (self.x + 12.0, self.y + 47.0),
        }


class BuzzerComponente(ComponenteElectronico):
    """Bocina piezoeléctrica que anima ondas acústicas y emite beep opcional al activarse."""

    def __init__(
        self,
        nombre: str = "Buzzer",
        pin: int = 11,
        x: float = 0.0,
        y: float = 0.0,
        frecuencia_hz: int = 2400,
        emitir_sonido: bool = False,
    ) -> None:
        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"IN": pin},
            propiedades={
                "pin": pin,
                "activo": False,
                "frecuencia_hz": int(frecuencia_hz),
                "emitir_sonido": bool(emitir_sonido),
                "fase_onda": 0,
                "voltaje": 0.0,
            },
        )
        self._id_membrana: int | None = None
        self._ids_ondas: list[int] = []
        self._id_etiqueta: int | None = None

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self._ids_ondas.clear()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo

        self.items_canvas.append(
            canvas.create_line(cx - 12, cy + 24, cx - 12, cy + 36, fill="#94A3B8", width=2, tags=(tag,))
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx - 17, cy + 32, cx - 7, cy + 42,
                fill="#F59E0B", outline="#0F172A", width=1.5, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_line(cx + 12, cy + 24, cx + 12, cy + 36, fill="#94A3B8", width=2, tags=(tag,))
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx + 7, cy + 32, cx + 17, cy + 42,
                fill="#3B82F6", outline="#0F172A", width=1.5, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_oval(
                cx - 26, cy - 26, cx + 26, cy + 26,
                fill="#111827", outline="#64748B", width=2, tags=(tag,),
            )
        )
        self.items_canvas.append(
            canvas.create_text(
                cx - 14, cy - 12, text="+", fill="#EF4444", font=("Consolas", 9, "bold"), tags=(tag,)
            )
        )
        self._id_membrana = canvas.create_oval(
            cx - 8, cy - 8, cx + 8, cy + 8,
            fill="#475569", outline="#94A3B8", width=1.5, tags=(tag,),
        )
        self.items_canvas.append(self._id_membrana)

        for radio in (33, 41, 49):
            onda_id = canvas.create_arc(
                cx - radio,
                cy - radio,
                cx + radio,
                cy + radio,
                start=40,
                extent=100,
                style=tk.ARC,
                outline="",
                width=2.2,
                tags=(tag,),
            )
            self._ids_ondas.append(onda_id)
            self.items_canvas.append(onda_id)

        pin = self.pines_conectados["IN"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 54,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

    def actualizar_desde_adm(self, adm: ADM) -> None:
        pin = self.pines_conectados["IN"]
        voltaje = adm.leerPuertoAnalogico(pin)
        nivel = adm.leerPuertoDigital(pin) if pin < ADM.TOTAL_PINES_DIGITALES else (
            1 if voltaje > ADM.UMBRAL_LOGICO else 0
        )

        activo = (voltaje > ADM.UMBRAL_LOGICO) or (nivel == 1)
        estaba_activo = bool(self.propiedades.get("activo", False))
        self.propiedades["voltaje"] = voltaje
        self.propiedades["activo"] = activo

        if self.canvas is None:
            return

        pin_txt = _formatear_pin_8051(pin)
        if activo:
            fase = (int(self.propiedades.get("fase_onda", 0)) + 1) % 3
            self.propiedades["fase_onda"] = fase

            if self._id_membrana is not None:
                self.canvas.itemconfig(self._id_membrana, fill="#F59E0B", outline="#FEF08A")

            colores_fase = ["#FBBF24", "#38BDF8", "#A78BFA"]
            for idx, onda_id in enumerate(self._ids_ondas):
                color = colores_fase[idx] if idx <= fase else "#334155"
                self.canvas.itemconfig(onda_id, outline=color)

            if self._id_etiqueta is not None:
                freq = self.propiedades.get("frecuencia_hz", 2400)
                self.canvas.itemconfig(
                    self._id_etiqueta, text=f"{self.nombre} [{pin_txt}] {freq}Hz"
                )

            if bool(self.propiedades.get("emitir_sonido", False)) and not estaba_activo:
                try:
                    self.canvas.bell()
                except tk.TclError:
                    pass
        else:
            if self._id_membrana is not None:
                self.canvas.itemconfig(self._id_membrana, fill="#475569", outline="#94A3B8")
            for onda_id in self._ids_ondas:
                self.canvas.itemconfig(onda_id, outline="")
            if self._id_etiqueta is not None:
                self.canvas.itemconfig(self._id_etiqueta, text=f"{self.nombre} [{pin_txt}]")

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        return {
            "IN": (self.x - 12.0, self.y + 37.0),
            "GND": (self.x + 12.0, self.y + 37.0),
        }


class Display7SegmentosComponente(ComponenteElectronico):
    """Display virtual de 7 segmentos + punto decimal (dp) conectado a un puerto 8051."""

    TABLA_HEX_7SEG: dict[int, int] = {
        0x0: 0x3F,
        0x1: 0x06,
        0x2: 0x5B,
        0x3: 0x4F,
        0x4: 0x66,
        0x5: 0x6D,
        0x6: 0x7D,
        0x7: 0x07,
        0x8: 0x7F,
        0x9: 0x6F,
        0xA: 0x77,
        0xB: 0x7C,
        0xC: 0x39,
        0xD: 0x5E,
        0xE: 0x79,
        0xF: 0x71,
    }

    ORDEN_SEGMENTOS: tuple[str, ...] = ("a", "b", "c", "d", "e", "f", "g", "dp")

    def __init__(
        self,
        nombre: str = "Display 7-Seg",
        puerto: int = 1,
        x: float = 0.0,
        y: float = 0.0,
        catodo_comun: bool = True,
        nibble: str | None = None,
        color_encendido: str = "#FF1744",
    ) -> None:
        if not (0 <= puerto <= 3):
            raise ValueError(f"Puerto inválido para Display 7-Seg: {puerto}. Use 0..3 (P0..P3).")
        if nibble not in (None, "low", "high"):
            raise ValueError(f"Modo nibble inválido: {nibble}. Use None, 'low' o 'high'.")

        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"PUERTO": puerto},
            propiedades={
                "puerto": puerto,
                "catodo_comun": bool(catodo_comun),
                "nibble": nibble,
                "color_encendido": color_encendido,
                "valor_byte": 0x00,
                "segmentos": {seg: False for seg in self.ORDEN_SEGMENTOS},
            },
        )
        self._ids_segmentos: dict[str, int] = {}
        self._id_etiqueta: int | None = None

    @staticmethod
    def _poligono_horizontal(x1: float, x2: float, y: float, grosor: float = 5.0) -> list[float]:
        h = grosor / 2.0
        return [
            x1, y,
            x1 + h, y - h,
            x2 - h, y - h,
            x2, y,
            x2 - h, y + h,
            x1 + h, y + h,
        ]

    @staticmethod
    def _poligono_vertical(x: float, y1: float, y2: float, grosor: float = 5.0) -> list[float]:
        h = grosor / 2.0
        return [
            x, y1,
            x + h, y1 + h,
            x + h, y2 - h,
            x, y2,
            x - h, y2 - h,
            x - h, y1 + h,
        ]

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self._ids_segmentos.clear()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo

        for idx in range(5):
            px = cx - 24 + idx * 12
            self.items_canvas.append(
                canvas.create_rectangle(
                    px - 2, cy - 56, px + 2, cy - 48,
                    fill="#CBD5E1", outline="#475569", tags=(tag,),
                )
            )
            self.items_canvas.append(
                canvas.create_rectangle(
                    px - 2, cy + 48, px + 2, cy + 56,
                    fill="#CBD5E1", outline="#475569", tags=(tag,),
                )
            )

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 34, cy - 48, cx + 34, cy + 48,
                fill="#0F172A", outline="#64748B", width=2, tags=(tag,),
            )
        )

        off_apagado = "#1E293B"
        geometrias: dict[str, list[float]] = {
            "a": self._poligono_horizontal(cx - 14, cx + 16, cy - 32),
            "g": self._poligono_horizontal(cx - 16, cx + 14, cy),
            "d": self._poligono_horizontal(cx - 18, cx + 12, cy + 32),
            "f": self._poligono_vertical(cx - 16, cy - 30, cy - 2),
            "b": self._poligono_vertical(cx + 16, cy - 30, cy - 2),
            "e": self._poligono_vertical(cx - 18, cy + 2, cy + 30),
            "c": self._poligono_vertical(cx + 14, cy + 2, cy + 30),
        }

        for nombre_seg, coords in geometrias.items():
            seg_id = canvas.create_polygon(
                coords, fill=off_apagado, outline="#0B1120", width=1, tags=(tag,)
            )
            self._ids_segmentos[nombre_seg] = seg_id
            self.items_canvas.append(seg_id)

        dp_id = canvas.create_oval(
            cx + 20, cy + 28, cx + 27, cy + 35,
            fill=off_apagado, outline="#0B1120", width=1, tags=(tag,),
        )
        self._ids_segmentos["dp"] = dp_id
        self.items_canvas.append(dp_id)

        puerto = self.pines_conectados["PUERTO"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 68,
            text=f"{self.nombre} [P{puerto}: 0x00]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

    def actualizar_desde_adm(self, adm: ADM) -> None:
        puerto = self.pines_conectados["PUERTO"]
        byte_val = adm.leer_byte_puerto(puerto)
        self.propiedades["valor_byte"] = byte_val

        nibble = self.propiedades.get("nibble")
        catodo_comun = bool(self.propiedades.get("catodo_comun", True))

        if nibble == "low":
            digito = byte_val & 0x0F
            mascara = self.TABLA_HEX_7SEG[digito]
        elif nibble == "high":
            digito = (byte_val >> 4) & 0x0F
            mascara = self.TABLA_HEX_7SEG[digito]
        else:
            mascara = byte_val if catodo_comun else (~byte_val & 0xFF)

        color_on = str(self.propiedades.get("color_encendido", "#FF1744"))
        color_off = "#1E293B"

        for idx, nombre_seg in enumerate(self.ORDEN_SEGMENTOS):
            encendido = bool((mascara >> idx) & 0x01)
            self.propiedades["segmentos"][nombre_seg] = encendido
            if self.canvas is not None and nombre_seg in self._ids_segmentos:
                self.canvas.itemconfig(
                    self._ids_segmentos[nombre_seg],
                    fill=color_on if encendido else color_off,
                )

        if self.canvas is not None and self._id_etiqueta is not None:
            modo_str = f" ({nibble})" if nibble else ""
            self.canvas.itemconfig(
                self._id_etiqueta,
                text=f"{self.nombre} [P{puerto}{modo_str}: 0x{byte_val:02X}]",
            )

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.x, self.y
        return {
            "g": (cx - 24.0, cy - 56.0),
            "f": (cx - 12.0, cy - 56.0),
            "COM_SUP": (cx, cy - 56.0),
            "a": (cx + 12.0, cy - 56.0),
            "b": (cx + 24.0, cy - 56.0),
            "e": (cx - 24.0, cy + 56.0),
            "d": (cx - 12.0, cy + 56.0),
            "COM_INF": (cx, cy + 56.0),
            "c": (cx + 12.0, cy + 56.0),
            "dp": (cx + 24.0, cy + 56.0),
        }
