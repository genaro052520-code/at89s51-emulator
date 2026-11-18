"""Sensores y dispositivos de entrada interactivos para el banco virtual del AT89S51.

Implementa 5 clases independientes que capturan interacción del usuario sobre
`tk.Canvas` e inyectan niveles digitales o voltajes analógicos exclusivamente a
través de `ADM` (`src/ports/adm.py`), sin importar ningún módulo de `core` ni
`storage`:
1. `PulsadorComponente`: Botón táctil momentáneo de 4 patas para protoboard.
2. `InterruptorDipComponente`: Interruptor deslizante de 2 posiciones (ON/OFF).
3. `PotenciometroComponente`: Perilla giratoria y deslizador continuo (0% - 100%).
4. `SensorTemperaturaComponente`: Sensor térmico tipo LM35/DHT (0°C - 100°C).
5. `SensorUltrasonicoComponente`: Sensor de distancia tipo HC-SR04 (2 cm - 400 cm).
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


class PulsadorComponente(ComponenteElectronico):
    """Botón pulsador táctil de 4 patas para protoboard."""

    def __init__(
        self,
        nombre: str = "Pulsador",
        pin: int = 26,
        x: float = 0.0,
        y: float = 0.0,
        activo_bajo: bool = True,
    ) -> None:
        voltaje_reposo = ADM.VOLTAJE_ALTO if activo_bajo else ADM.VOLTAJE_BAJO
        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"OUT": pin},
            propiedades={
                "pin": pin,
                "presionado": False,
                "activo_bajo": bool(activo_bajo),
                "voltaje": voltaje_reposo,
                "interactuando": False,
            },
        )
        self._adm_ref: ADM | None = None
        self._tag_interactivo: str = f"{self.tag_grupo}_btn"
        self._id_boton: int | None = None
        self._id_aro: int | None = None
        self._id_etiqueta: int | None = None

    def presionar(self, adm: ADM | None = None) -> None:
        adm_activo = adm if adm is not None else self._adm_ref
        pin = self.pines_conectados["OUT"]
        activo_bajo = bool(self.propiedades.get("activo_bajo", True))
        voltaje_activo = ADM.VOLTAJE_BAJO if activo_bajo else ADM.VOLTAJE_ALTO

        self.propiedades["presionado"] = True
        self.propiedades["voltaje"] = voltaje_activo

        if adm_activo is not None:
            adm_activo.inyectar_estimulo_externo(pin, voltaje_activo)

        self._refrescar_apariencia()

    def soltar(self, adm: ADM | None = None) -> None:
        adm_activo = adm if adm is not None else self._adm_ref
        pin = self.pines_conectados["OUT"]
        activo_bajo = bool(self.propiedades.get("activo_bajo", True))

        self.propiedades["presionado"] = False
        self.propiedades["voltaje"] = ADM.VOLTAJE_ALTO if activo_bajo else ADM.VOLTAJE_BAJO

        if adm_activo is not None:
            adm_activo.liberar_estimulo_externo(pin)

        self._refrescar_apariencia()

    def _al_presionar_raton(self, _event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = True
        self.presionar()
        return "break"

    def _al_soltar_raton(self, _event: tk.Event[tk.Misc]) -> str:
        self.soltar()
        self.propiedades["interactuando"] = False
        return "break"

    def _refrescar_apariencia(self) -> None:
        if self.canvas is None:
            return
        presionado = bool(self.propiedades.get("presionado", False))
        if self._id_boton is not None:
            self.canvas.itemconfig(
                self._id_boton,
                fill="#EF4444" if presionado else "#1E293B",
                outline="#FCA5A5" if presionado else "#94A3B8",
            )
        if self._id_aro is not None:
            self.canvas.itemconfig(
                self._id_aro,
                outline="#F87171" if presionado else "#475569",
            )
        if self._id_etiqueta is not None:
            pin = self.pines_conectados["OUT"]
            estado = "PRESS" if presionado else "IDLE"
            self.canvas.itemconfig(
                self._id_etiqueta,
                text=f"{self.nombre} [{_formatear_pin_8051(pin)}] {estado}",
            )

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo
        t_btn = self._tag_interactivo

        patas = [
            (cx - 26, cy - 16, cx - 18, cy - 10),
            (cx + 18, cy - 16, cx + 26, cy - 10),
            (cx - 26, cy + 10, cx - 18, cy + 16),
            (cx + 18, cy + 10, cx + 26, cy + 16),
        ]
        for x1, y1, x2, y2 in patas:
            self.items_canvas.append(
                canvas.create_rectangle(
                    x1, y1, x2, y2, fill="#CBD5E1", outline="#475569", width=1, tags=(tag,)
                )
            )

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 19, cy - 19, cx + 19, cy + 19,
                fill="#64748B", outline="#CBD5E1", width=1.5, tags=(tag, t_btn),
            )
        )

        for rx, ry in ((cx - 14, cy - 14), (cx + 14, cy - 14), (cx - 14, cy + 14), (cx + 14, cy + 14)):
            self.items_canvas.append(
                canvas.create_oval(
                    rx - 2, ry - 2, rx + 2, ry + 2,
                    fill="#1E293B", outline="", tags=(tag, t_btn),
                )
            )

        self._id_aro = canvas.create_oval(
            cx - 12, cy - 12, cx + 12, cy + 12,
            fill="#0F172A", outline="#475569", width=1.5, tags=(tag, t_btn),
        )
        self.items_canvas.append(self._id_aro)

        self._id_boton = canvas.create_oval(
            cx - 9, cy - 9, cx + 9, cy + 9,
            fill="#1E293B", outline="#94A3B8", width=1.5, tags=(tag, t_btn),
        )
        self.items_canvas.append(self._id_boton)

        pin = self.pines_conectados["OUT"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 31,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}] IDLE",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

        canvas.tag_bind(t_btn, "<ButtonPress-1>", self._al_presionar_raton)
        canvas.tag_bind(t_btn, "<ButtonRelease-1>", self._al_soltar_raton)
        self._refrescar_apariencia()

    def actualizar_desde_adm(self, adm: ADM) -> None:
        self._adm_ref = adm
        pin = self.pines_conectados["OUT"]
        self.propiedades["voltaje"] = adm.leerPuertoAnalogico(pin)
        self._refrescar_apariencia()

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.x, self.y
        return {
            "P1": (cx - 26.0, cy - 13.0),
            "P2": (cx + 26.0, cy - 13.0),
            "P3": (cx - 26.0, cy + 13.0),
            "OUT": (cx + 26.0, cy + 13.0),
        }


class InterruptorDipComponente(ComponenteElectronico):
    """Interruptor deslizante de 2 posiciones (ON / OFF) con enclavamiento en ADM."""

    def __init__(
        self,
        nombre: str = "Switch DIP",
        pin: int = 27,
        x: float = 0.0,
        y: float = 0.0,
        estado_on: bool = False,
        activo_bajo: bool = True,
    ) -> None:
        voltaje_ini = (
            (ADM.VOLTAJE_BAJO if activo_bajo else ADM.VOLTAJE_ALTO)
            if estado_on
            else (ADM.VOLTAJE_ALTO if activo_bajo else ADM.VOLTAJE_BAJO)
        )
        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados={"OUT": pin},
            propiedades={
                "pin": pin,
                "estado_on": bool(estado_on),
                "activo_bajo": bool(activo_bajo),
                "voltaje": voltaje_ini,
                "interactuando": False,
            },
        )
        self._adm_ref: ADM | None = None
        self._sincronizado_inicial: bool = False
        self._tag_interactivo: str = f"{self.tag_grupo}_sw"
        self._id_palanca: int | None = None
        self._id_ranura: int | None = None
        self._id_etiqueta: int | None = None

    def establecer_estado(self, estado_on: bool, adm: ADM | None = None) -> None:
        adm_activo = adm if adm is not None else self._adm_ref
        pin = self.pines_conectados["OUT"]
        activo_bajo = bool(self.propiedades.get("activo_bajo", True))
        self.propiedades["estado_on"] = bool(estado_on)

        if self.propiedades["estado_on"]:
            voltaje = ADM.VOLTAJE_BAJO if activo_bajo else ADM.VOLTAJE_ALTO
            self.propiedades["voltaje"] = voltaje
            if adm_activo is not None:
                adm_activo.inyectar_estimulo_externo(pin, voltaje)
        else:
            self.propiedades["voltaje"] = ADM.VOLTAJE_ALTO if activo_bajo else ADM.VOLTAJE_BAJO
            if adm_activo is not None:
                adm_activo.liberar_estimulo_externo(pin)

        self._refrescar_apariencia()

    def alternar(self, adm: ADM | None = None) -> bool:
        nuevo_estado = not bool(self.propiedades.get("estado_on", False))
        self.establecer_estado(nuevo_estado, adm=adm)
        return nuevo_estado

    def _al_clic_raton(self, _event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = True
        self.alternar()
        self.propiedades["interactuando"] = False
        return "break"

    def _refrescar_apariencia(self) -> None:
        if self.canvas is None:
            return
        cx, cy = self.x, self.y
        estado_on = bool(self.propiedades.get("estado_on", False))

        if self._id_ranura is not None:
            self.canvas.itemconfig(
                self._id_ranura,
                fill="#065F46" if estado_on else "#0F172A",
            )
        if self._id_palanca is not None:
            if estado_on:
                self.canvas.coords(self._id_palanca, cx + 2, cy - 8, cx + 22, cy + 8)
                self.canvas.itemconfig(self._id_palanca, fill="#00E676")
            else:
                self.canvas.coords(self._id_palanca, cx - 22, cy - 8, cx - 2, cy + 8)
                self.canvas.itemconfig(self._id_palanca, fill="#F8FAFC")

        if self._id_etiqueta is not None:
            pin = self.pines_conectados["OUT"]
            estado_txt = "ON" if estado_on else "OFF"
            self.canvas.itemconfig(
                self._id_etiqueta,
                text=f"{self.nombre} [{_formatear_pin_8051(pin)}] {estado_txt}",
            )

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo
        t_sw = self._tag_interactivo

        for offset_x, color_pad in ((-16, "#3B82F6"), (0, "#F59E0B"), (16, "#EF4444")):
            self.items_canvas.append(
                canvas.create_line(
                    cx + offset_x, cy + 16, cx + offset_x, cy + 26,
                    fill="#CBD5E1", width=2, tags=(tag,),
                )
            )
            self.items_canvas.append(
                canvas.create_oval(
                    cx + offset_x - 3.5, cy + 22, cx + offset_x + 3.5, cy + 29,
                    fill=color_pad, outline="#0F172A", width=1, tags=(tag,),
                )
            )

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 32, cy - 16, cx + 32, cy + 16,
                fill="#B91C1C", outline="#FCA5A5", width=1.5, tags=(tag, t_sw),
            )
        )

        self.items_canvas.append(
            canvas.create_text(
                cx - 24, cy - 22, text="OFF", fill="#94A3B8", font=("Consolas", 7, "bold"), tags=(tag,)
            )
        )
        self.items_canvas.append(
            canvas.create_text(
                cx + 24, cy - 22, text="ON", fill="#00E676", font=("Consolas", 7, "bold"), tags=(tag,)
            )
        )

        self._id_ranura = canvas.create_rectangle(
            cx - 24, cy - 10, cx + 24, cy + 10,
            fill="#0F172A", outline="#7F1D1D", width=1, tags=(tag, t_sw),
        )
        self.items_canvas.append(self._id_ranura)

        self._id_palanca = canvas.create_rectangle(
            cx - 22, cy - 8, cx - 2, cy + 8,
            fill="#F8FAFC", outline="#0F172A", width=1.5, tags=(tag, t_sw),
        )
        self.items_canvas.append(self._id_palanca)

        pin = self.pines_conectados["OUT"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 40,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}] OFF",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

        canvas.tag_bind(t_sw, "<ButtonPress-1>", self._al_clic_raton)
        self._refrescar_apariencia()

    def actualizar_desde_adm(self, adm: ADM) -> None:
        self._adm_ref = adm
        if not self._sincronizado_inicial:
            self._sincronizado_inicial = True
            self.establecer_estado(bool(self.propiedades.get("estado_on", False)), adm=adm)
            return

        pin = self.pines_conectados["OUT"]
        self.propiedades["voltaje"] = adm.leerPuertoAnalogico(pin)
        self._refrescar_apariencia()

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.x, self.y
        return {
            "GND": (cx - 16.0, cy + 25.5),
            "OUT": (cx, cy + 25.5),
            "VCC": (cx + 16.0, cy + 25.5),
        }


class PotenciometroComponente(ComponenteElectronico):
    """Potenciómetro interactivo (0% a 100%) con salida analógica (0.0V - 5.0V) y digital."""

    def __init__(
        self,
        nombre: str = "Potenciómetro",
        canal: int = 32,
        pin: int | None = 12,
        x: float = 0.0,
        y: float = 0.0,
        porcentaje: float = 50.0,
    ) -> None:
        pct = max(0.0, min(100.0, float(porcentaje)))
        voltaje_ini = round((pct / 100.0) * ADM.VOLTAJE_MAX, 3)

        pines: dict[str, int] = {"ANALOG": canal}
        if pin is not None and pin != canal:
            pines["OUT"] = pin

        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados=pines,
            propiedades={
                "canal": canal,
                "pin": pin,
                "porcentaje": pct,
                "voltaje": voltaje_ini,
                "nivel_digital": 1 if voltaje_ini > ADM.UMBRAL_LOGICO else 0,
                "interactuando": False,
            },
        )
        self._adm_ref: ADM | None = None
        self._sincronizado_inicial: bool = False
        self._tag_interactivo: str = f"{self.tag_grupo}_pot"
        self._id_arco_activo: int | None = None
        self._id_aguja: int | None = None
        self._id_barra_fill: int | None = None
        self._id_texto_valor: int | None = None
        self._id_etiqueta: int | None = None

    def establecer_porcentaje(self, porcentaje: float, adm: ADM | None = None) -> float:
        adm_activo = adm if adm is not None else self._adm_ref
        pct = max(0.0, min(100.0, float(porcentaje)))
        voltaje = round((pct / 100.0) * ADM.VOLTAJE_MAX, 3)
        nivel_alto = voltaje > ADM.UMBRAL_LOGICO

        self.propiedades["porcentaje"] = round(pct, 1)
        self.propiedades["voltaje"] = voltaje
        self.propiedades["nivel_digital"] = 1 if nivel_alto else 0

        if adm_activo is not None:
            canal = self.pines_conectados["ANALOG"]
            adm_activo.configurarPuerto(canal, ADM.MODO_ESCRITURA)
            adm_activo.escribirPuertoAnalogico(canal, voltaje)

            pin_digital = self.propiedades.get("pin")
            if (
                isinstance(pin_digital, int)
                and pin_digital != canal
                and 0 <= pin_digital < ADM.TOTAL_PINES_DIGITALES
            ):
                voltaje_digital = ADM.VOLTAJE_ALTO if nivel_alto else ADM.VOLTAJE_BAJO
                adm_activo.inyectar_estimulo_externo(pin_digital, voltaje_digital)

        self._refrescar_apariencia()
        return voltaje

    def _actualizar_desde_coordenada_x(self, mouse_x: float) -> None:
        x_min = self.x - 32.0
        x_max = self.x + 32.0
        pct = ((mouse_x - x_min) / (x_max - x_min)) * 100.0
        self.establecer_porcentaje(pct)

    def _al_clic_o_arrastre(self, event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = True
        self._actualizar_desde_coordenada_x(float(event.x))
        return "break"

    def _al_soltar_raton(self, _event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = False
        return "break"

    def _refrescar_apariencia(self) -> None:
        if self.canvas is None:
            return
        cx, cy = self.x, self.y
        pct = float(self.propiedades.get("porcentaje", 50.0))
        voltaje = float(self.propiedades.get("voltaje", 2.5))

        extent_deg = -(pct / 100.0) * 270.0
        angulo_rad = math.radians(225.0 + extent_deg)

        if self._id_arco_activo is not None:
            self.canvas.itemconfig(self._id_arco_activo, extent=extent_deg)

        if self._id_aguja is not None:
            nx = cx + 17.0 * math.cos(angulo_rad)
            ny = (cy - 8.0) - 17.0 * math.sin(angulo_rad)
            self.canvas.coords(self._id_aguja, cx, cy - 8.0, nx, ny)

        if self._id_barra_fill is not None:
            x_fill = (cx - 30.0) + (pct / 100.0) * 60.0
            self.canvas.coords(self._id_barra_fill, cx - 30.0, cy + 24.0, x_fill, cy + 30.0)

        if self._id_texto_valor is not None:
            self.canvas.itemconfig(
                self._id_texto_valor,
                text=f"{voltaje:.2f}V ({int(round(pct))}%)",
            )

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo
        t_pot = self._tag_interactivo

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 38, cy - 36, cx + 38, cy + 38,
                fill="#1E293B", outline="#64748B", width=1.5, tags=(tag, t_pot),
            )
        )

        for offset_x, color_pad in ((-18, "#3B82F6"), (0, "#F59E0B"), (18, "#EF4444")):
            self.items_canvas.append(
                canvas.create_line(
                    cx + offset_x, cy + 38, cx + offset_x, cy + 48,
                    fill="#CBD5E1", width=2, tags=(tag,),
                )
            )
            self.items_canvas.append(
                canvas.create_oval(
                    cx + offset_x - 3.5, cy + 44, cx + offset_x + 3.5, cy + 51,
                    fill=color_pad, outline="#0F172A", width=1, tags=(tag,),
                )
            )

        ky = cy - 8.0
        self.items_canvas.append(
            canvas.create_arc(
                cx - 26, ky - 26, cx + 26, ky + 26,
                start=225, extent=-270, style=tk.ARC, outline="#334155", width=4, tags=(tag, t_pot),
            )
        )

        self._id_arco_activo = canvas.create_arc(
            cx - 26, ky - 26, cx + 26, ky + 26,
            start=225, extent=-135, style=tk.ARC, outline="#38BDF8", width=4, tags=(tag, t_pot),
        )
        self.items_canvas.append(self._id_arco_activo)

        self.items_canvas.append(
            canvas.create_oval(
                cx - 19, ky - 19, cx + 19, ky + 19,
                fill="#0F172A", outline="#94A3B8", width=1.5, tags=(tag, t_pot),
            )
        )

        self._id_aguja = canvas.create_line(
            cx, ky, cx, ky - 17, fill="#F8FAFC", width=2.5, capstyle=tk.ROUND, tags=(tag, t_pot)
        )
        self.items_canvas.append(self._id_aguja)

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 30, cy + 24, cx + 30, cy + 30,
                fill="#0F172A", outline="#475569", width=1, tags=(tag, t_pot),
            )
        )
        self._id_barra_fill = canvas.create_rectangle(
            cx - 30, cy + 24, cx, cy + 30,
            fill="#00E676", outline="", tags=(tag, t_pot),
        )
        self.items_canvas.append(self._id_barra_fill)

        self._id_texto_valor = canvas.create_text(
            cx,
            cy - 44,
            text="2.50V (50%)",
            fill="#38BDF8",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_texto_valor)

        canal = self.pines_conectados["ANALOG"]
        pin_dig = self.propiedades.get("pin")
        destino_txt = _formatear_pin_8051(canal)
        if isinstance(pin_dig, int) and pin_dig != canal:
            destino_txt += f"/{_formatear_pin_8051(pin_dig)}"

        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 61,
            text=f"{self.nombre} [{destino_txt}]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

        canvas.tag_bind(t_pot, "<ButtonPress-1>", self._al_clic_o_arrastre)
        canvas.tag_bind(t_pot, "<B1-Motion>", self._al_clic_o_arrastre)
        canvas.tag_bind(t_pot, "<ButtonRelease-1>", self._al_soltar_raton)
        self._refrescar_apariencia()

    def actualizar_desde_adm(self, adm: ADM) -> None:
        self._adm_ref = adm
        if not self._sincronizado_inicial:
            self._sincronizado_inicial = True
            self.establecer_porcentaje(float(self.propiedades.get("porcentaje", 50.0)), adm=adm)

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.x, self.y
        puntos: dict[str, tuple[float, float]] = {
            "GND": (cx - 18.0, cy + 47.5),
            "ANALOG": (cx, cy + 47.5),
            "VCC": (cx + 18.0, cy + 47.5),
        }
        if "OUT" in self.pines_conectados:
            puntos["OUT"] = (cx, cy + 47.5)
        return puntos


class SensorTemperaturaComponente(ComponenteElectronico):
    """Sensor de temperatura virtual tipo LM35/DHT con control deslizante (0°C a 100°C)."""

    TEMP_MIN_C: float = 0.0
    TEMP_MAX_C: float = 100.0

    def __init__(
        self,
        nombre: str = "Sensor Temp",
        pin: int = 13,
        canal: int | None = 33,
        x: float = 0.0,
        y: float = 0.0,
        temperatura_c: float = 25.0,
        umbral_c: float = 30.0,
    ) -> None:
        temp = max(self.TEMP_MIN_C, min(self.TEMP_MAX_C, float(temperatura_c)))
        voltaje_ini = round((temp / self.TEMP_MAX_C) * ADM.VOLTAJE_MAX, 3)
        alerta_ini = temp > float(umbral_c)

        pines: dict[str, int] = {"OUT": pin}
        if canal is not None and canal != pin:
            pines["ANALOG"] = canal

        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados=pines,
            propiedades={
                "pin": pin,
                "canal": canal,
                "temperatura_c": round(temp, 1),
                "umbral_c": float(umbral_c),
                "voltaje": voltaje_ini,
                "alerta_activa": alerta_ini,
                "interactuando": False,
            },
        )
        self._adm_ref: ADM | None = None
        self._sincronizado_inicial: bool = False
        self._tag_interactivo: str = f"{self.tag_grupo}_temp"
        self._id_mercurio: int | None = None
        self._id_bulbo: int | None = None
        self._id_led_alerta: int | None = None
        self._id_texto_temp: int | None = None
        self._id_etiqueta: int | None = None

    def establecer_temperatura(self, temperatura_c: float, adm: ADM | None = None) -> float:
        adm_activo = adm if adm is not None else self._adm_ref
        temp = max(self.TEMP_MIN_C, min(self.TEMP_MAX_C, float(temperatura_c)))
        umbral = float(self.propiedades.get("umbral_c", 30.0))
        voltaje = round((temp / self.TEMP_MAX_C) * ADM.VOLTAJE_MAX, 3)
        alerta = temp > umbral

        self.propiedades["temperatura_c"] = round(temp, 1)
        self.propiedades["voltaje"] = voltaje
        self.propiedades["alerta_activa"] = alerta

        if adm_activo is not None:
            canal = self.propiedades.get("canal")
            if isinstance(canal, int) and 0 <= canal < ADM.TOTAL_CANALES:
                adm_activo.configurarPuerto(canal, ADM.MODO_ESCRITURA)
                adm_activo.escribirPuertoAnalogico(canal, voltaje)

            pin = self.pines_conectados["OUT"]
            if 0 <= pin < ADM.TOTAL_PINES_DIGITALES and pin != canal:
                volt_digital = ADM.VOLTAJE_ALTO if alerta else ADM.VOLTAJE_BAJO
                adm_activo.inyectar_estimulo_externo(pin, volt_digital)

        self._refrescar_apariencia()
        return voltaje

    def _actualizar_desde_coordenada_y(self, mouse_y: float) -> None:
        y_top = self.y - 26.0
        y_bot = self.y + 18.0
        fraccion = (y_bot - mouse_y) / (y_bot - y_top)
        self.establecer_temperatura(fraccion * self.TEMP_MAX_C)

    def _al_clic_o_arrastre(self, event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = True
        self._actualizar_desde_coordenada_y(float(event.y))
        return "break"

    def _al_soltar_raton(self, _event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = False
        return "break"

    def _refrescar_apariencia(self) -> None:
        if self.canvas is None:
            return
        cx, cy = self.x, self.y
        temp = float(self.propiedades.get("temperatura_c", 25.0))
        voltaje = float(self.propiedades.get("voltaje", 1.25))
        alerta = bool(self.propiedades.get("alerta_activa", False))

        color_termico = "#EF4444" if alerta else ("#38BDF8" if temp < 15.0 else "#10B981")

        y_bot = cy + 18.0
        altura_max = 44.0
        y_nivel = y_bot - (temp / self.TEMP_MAX_C) * altura_max

        if self._id_mercurio is not None:
            self.canvas.coords(self._id_mercurio, cx - 19.0, y_nivel, cx - 11.0, y_bot)
            self.canvas.itemconfig(self._id_mercurio, fill=color_termico)

        if self._id_bulbo is not None:
            self.canvas.itemconfig(self._id_bulbo, fill=color_termico)

        if self._id_led_alerta is not None:
            self.canvas.itemconfig(
                self._id_led_alerta,
                fill="#FF1744" if alerta else "#334155",
            )

        if self._id_texto_temp is not None:
            self.canvas.itemconfig(
                self._id_texto_temp,
                text=f"{temp:.1f}°C\n{voltaje:.2f}V",
                fill="#FCA5A5" if alerta else "#F8FAFC",
            )

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo
        t_temp = self._tag_interactivo

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 34, cy - 36, cx + 34, cy + 36,
                fill="#0F172A", outline="#38BDF8", width=1.5, tags=(tag, t_temp),
            )
        )

        for offset_x, color_pad in ((-16, "#EF4444"), (0, "#F59E0B"), (16, "#3B82F6")):
            self.items_canvas.append(
                canvas.create_line(
                    cx + offset_x, cy + 36, cx + offset_x, cy + 46,
                    fill="#CBD5E1", width=2, tags=(tag,),
                )
            )
            self.items_canvas.append(
                canvas.create_oval(
                    cx + offset_x - 3.5, cy + 42, cx + offset_x + 3.5, cy + 49,
                    fill=color_pad, outline="#0F172A", width=1, tags=(tag,),
                )
            )

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 21, cy - 28, cx - 9, cy + 20,
                fill="#1E293B", outline="#94A3B8", width=1, tags=(tag, t_temp),
            )
        )

        self._id_mercurio = canvas.create_rectangle(
            cx - 19, cy + 6, cx - 11, cy + 18,
            fill="#10B981", outline="", tags=(tag, t_temp),
        )
        self.items_canvas.append(self._id_mercurio)

        self._id_bulbo = canvas.create_oval(
            cx - 23, cy + 14, cx - 7, cy + 30,
            fill="#10B981", outline="#94A3B8", width=1, tags=(tag, t_temp),
        )
        self.items_canvas.append(self._id_bulbo)

        umbral = float(self.propiedades.get("umbral_c", 30.0))
        y_umbral = (cy + 18.0) - (umbral / self.TEMP_MAX_C) * 44.0
        self.items_canvas.append(
            canvas.create_line(
                cx - 25, y_umbral, cx - 5, y_umbral,
                fill="#F59E0B", width=1.5, dash=(2, 1), tags=(tag, t_temp),
            )
        )

        self._id_led_alerta = canvas.create_oval(
            cx + 18, cy - 28, cx + 26, cy - 20,
            fill="#334155", outline="#64748B", width=1, tags=(tag,),
        )
        self.items_canvas.append(self._id_led_alerta)

        self._id_texto_temp = canvas.create_text(
            cx + 12,
            cy + 4,
            text="25.0°C\n1.25V",
            fill="#F8FAFC",
            font=("Consolas", 8, "bold"),
            tags=(tag, t_temp),
        )
        self.items_canvas.append(self._id_texto_temp)

        pin = self.pines_conectados["OUT"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 59,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)} >{int(umbral)}°C]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

        canvas.tag_bind(t_temp, "<ButtonPress-1>", self._al_clic_o_arrastre)
        canvas.tag_bind(t_temp, "<B1-Motion>", self._al_clic_o_arrastre)
        canvas.tag_bind(t_temp, "<ButtonRelease-1>", self._al_soltar_raton)
        self._refrescar_apariencia()

    def actualizar_desde_adm(self, adm: ADM) -> None:
        self._adm_ref = adm
        if not self._sincronizado_inicial:
            self._sincronizado_inicial = True
            self.establecer_temperatura(float(self.propiedades.get("temperatura_c", 25.0)), adm=adm)

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.x, self.y
        puntos: dict[str, tuple[float, float]] = {
            "VCC": (cx - 16.0, cy + 45.5),
            "OUT": (cx, cy + 45.5),
            "GND": (cx + 16.0, cy + 45.5),
        }
        if "ANALOG" in self.pines_conectados:
            puntos["ANALOG"] = (cx, cy + 45.5)
        return puntos


class SensorUltrasonicoComponente(ComponenteElectronico):
    """Sensor ultrasónico de distancia tipo HC-SR04 (2 cm a 400 cm)."""

    DIST_MIN_CM: float = 2.0
    DIST_MAX_CM: float = 400.0

    def __init__(
        self,
        nombre: str = "HC-SR04",
        pin: int = 14,
        canal: int | None = 34,
        x: float = 0.0,
        y: float = 0.0,
        distancia_cm: float = 50.0,
        umbral_obstaculo_cm: float = 20.0,
    ) -> None:
        dist = max(self.DIST_MIN_CM, min(self.DIST_MAX_CM, float(distancia_cm)))
        obstaculo_ini = dist < float(umbral_obstaculo_cm)

        pines: dict[str, int] = {"ECHO": pin}
        if canal is not None and canal != pin:
            pines["ANALOG"] = canal

        super().__init__(
            nombre=nombre,
            x=x,
            y=y,
            pines_conectados=pines,
            propiedades={
                "pin": pin,
                "canal": canal,
                "distancia_cm": round(dist, 1),
                "umbral_obstaculo_cm": float(umbral_obstaculo_cm),
                "obstaculo_detectado": obstaculo_ini,
                "voltaje": ADM.VOLTAJE_ALTO if obstaculo_ini else ADM.VOLTAJE_BAJO,
                "interactuando": False,
            },
        )
        self._adm_ref: ADM | None = None
        self._sincronizado_inicial: bool = False
        self._tag_interactivo: str = f"{self.tag_grupo}_us"
        self._id_cursor_dist: int | None = None
        self._id_barra_dist: int | None = None
        self._id_led_obstaculo: int | None = None
        self._id_texto_dist: int | None = None
        self._id_etiqueta: int | None = None

    def establecer_distancia(self, distancia_cm: float, adm: ADM | None = None) -> bool:
        adm_activo = adm if adm is not None else self._adm_ref
        dist = max(self.DIST_MIN_CM, min(self.DIST_MAX_CM, float(distancia_cm)))
        umbral = float(self.propiedades.get("umbral_obstaculo_cm", 20.0))
        obstaculo = dist < umbral
        voltaje_digital = ADM.VOLTAJE_ALTO if obstaculo else ADM.VOLTAJE_BAJO

        self.propiedades["distancia_cm"] = round(dist, 1)
        self.propiedades["obstaculo_detectado"] = obstaculo
        self.propiedades["voltaje"] = voltaje_digital

        if adm_activo is not None:
            pin = self.pines_conectados["ECHO"]
            if 0 <= pin < ADM.TOTAL_PINES_DIGITALES:
                adm_activo.inyectar_estimulo_externo(pin, voltaje_digital)

            canal = self.propiedades.get("canal")
            if isinstance(canal, int) and 0 <= canal < ADM.TOTAL_CANALES and canal != pin:
                frac = (dist - self.DIST_MIN_CM) / (self.DIST_MAX_CM - self.DIST_MIN_CM)
                volt_analog = round(frac * ADM.VOLTAJE_MAX, 3)
                adm_activo.configurarPuerto(canal, ADM.MODO_ESCRITURA)
                adm_activo.escribirPuertoAnalogico(canal, volt_analog)

        self._refrescar_apariencia()
        return obstaculo

    def _actualizar_desde_coordenada_x(self, mouse_x: float) -> None:
        x_min = self.x - 40.0
        x_max = self.x + 40.0
        frac = max(0.0, min(1.0, (mouse_x - x_min) / (x_max - x_min)))
        dist = self.DIST_MIN_CM + frac * (self.DIST_MAX_CM - self.DIST_MIN_CM)
        self.establecer_distancia(dist)

    def _al_clic_o_arrastre(self, event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = True
        self._actualizar_desde_coordenada_x(float(event.x))
        return "break"

    def _al_soltar_raton(self, _event: tk.Event[tk.Misc]) -> str:
        self.propiedades["interactuando"] = False
        return "break"

    def _refrescar_apariencia(self) -> None:
        if self.canvas is None:
            return
        cx, cy = self.x, self.y
        dist = float(self.propiedades.get("distancia_cm", 50.0))
        obstaculo = bool(self.propiedades.get("obstaculo_detectado", False))

        frac = (dist - self.DIST_MIN_CM) / (self.DIST_MAX_CM - self.DIST_MIN_CM)
        x_pos = (cx - 40.0) + frac * 80.0
        color_estado = "#FF1744" if obstaculo else "#38BDF8"

        if self._id_barra_dist is not None:
            self.canvas.coords(self._id_barra_dist, cx - 40.0, cy + 20.0, x_pos, cy + 26.0)
            self.canvas.itemconfig(self._id_barra_dist, fill=color_estado)

        if self._id_cursor_dist is not None:
            self.canvas.coords(
                self._id_cursor_dist, x_pos - 4.0, cy + 17.0, x_pos + 4.0, cy + 29.0
            )
            self.canvas.itemconfig(
                self._id_cursor_dist,
                fill="#FCA5A5" if obstaculo else "#F8FAFC",
            )

        if self._id_led_obstaculo is not None:
            self.canvas.itemconfig(
                self._id_led_obstaculo,
                fill="#FF1744" if obstaculo else "#1E293B",
            )

        if self._id_texto_dist is not None:
            aviso = " [OBSTÁCULO]" if obstaculo else ""
            self.canvas.itemconfig(
                self._id_texto_dist,
                text=f"{dist:.1f} cm{aviso}",
                fill="#FCA5A5" if obstaculo else "#F8FAFC",
            )

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        cx, cy = self.x, self.y
        tag = self.tag_grupo
        t_us = self._tag_interactivo

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 48, cy - 26, cx + 48, cy + 34,
                fill="#1D4ED8", outline="#93C5FD", width=1.5, tags=(tag, t_us),
            )
        )

        pines_info = [
            (-24, "#EF4444"),
            (-8, "#94A3B8"),
            (8, "#F59E0B"),
            (24, "#3B82F6"),
        ]
        for offset_x, color_pad in pines_info:
            self.items_canvas.append(
                canvas.create_line(
                    cx + offset_x, cy + 34, cx + offset_x, cy + 44,
                    fill="#CBD5E1", width=2, tags=(tag,),
                )
            )
            self.items_canvas.append(
                canvas.create_oval(
                    cx + offset_x - 3, cy + 40, cx + offset_x + 3, cy + 46,
                    fill=color_pad, outline="#0F172A", width=1, tags=(tag,),
                )
            )

        for tx, letra in ((cx - 24, "T"), (cx + 24, "R")):
            self.items_canvas.append(
                canvas.create_oval(
                    tx - 16, cy - 20, tx + 16, cy + 12,
                    fill="#CBD5E1", outline="#475569", width=2, tags=(tag, t_us),
                )
            )
            self.items_canvas.append(
                canvas.create_oval(
                    tx - 11, cy - 15, tx + 11, cy + 7,
                    fill="#334155", outline="#64748B", width=1, tags=(tag, t_us),
                )
            )
            self.items_canvas.append(
                canvas.create_text(
                    tx, cy - 4, text=letra, fill="#E2E8F0", font=("Consolas", 8, "bold"), tags=(tag, t_us)
                )
            )

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 5, cy - 16, cx + 5, cy - 4,
                fill="#94A3B8", outline="#1E293B", width=1, tags=(tag,),
            )
        )
        self._id_led_obstaculo = canvas.create_oval(
            cx - 4, cy + 2, cx + 4, cy + 10,
            fill="#1E293B", outline="#93C5FD", width=1, tags=(tag,),
        )
        self.items_canvas.append(self._id_led_obstaculo)

        self.items_canvas.append(
            canvas.create_rectangle(
                cx - 40, cy + 20, cx + 40, cy + 26,
                fill="#0F172A", outline="#60A5FA", width=1, tags=(tag, t_us),
            )
        )
        self._id_barra_dist = canvas.create_rectangle(
            cx - 40, cy + 20, cx - 25, cy + 26,
            fill="#38BDF8", outline="", tags=(tag, t_us),
        )
        self.items_canvas.append(self._id_barra_dist)

        self._id_cursor_dist = canvas.create_rectangle(
            cx - 29, cy + 17, cx - 21, cy + 29,
            fill="#F8FAFC", outline="#0F172A", width=1, tags=(tag, t_us),
        )
        self.items_canvas.append(self._id_cursor_dist)

        self._id_texto_dist = canvas.create_text(
            cx,
            cy - 36,
            text="50.0 cm",
            fill="#F8FAFC",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_texto_dist)

        pin = self.pines_conectados["ECHO"]
        self._id_etiqueta = canvas.create_text(
            cx,
            cy + 57,
            text=f"{self.nombre} [{_formatear_pin_8051(pin)}]",
            fill="#E2E8F0",
            font=("Consolas", 8, "bold"),
            tags=(tag,),
        )
        self.items_canvas.append(self._id_etiqueta)

        canvas.tag_bind(t_us, "<ButtonPress-1>", self._al_clic_o_arrastre)
        canvas.tag_bind(t_us, "<B1-Motion>", self._al_clic_o_arrastre)
        canvas.tag_bind(t_us, "<ButtonRelease-1>", self._al_soltar_raton)
        self._refrescar_apariencia()

    def actualizar_desde_adm(self, adm: ADM) -> None:
        self._adm_ref = adm
        if not self._sincronizado_inicial:
            self._sincronizado_inicial = True
            self.establecer_distancia(float(self.propiedades.get("distancia_cm", 50.0)), adm=adm)

    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.x, self.y
        puntos: dict[str, tuple[float, float]] = {
            "VCC": (cx - 24.0, cy + 43.0),
            "TRIG": (cx - 8.0, cy + 43.0),
            "ECHO": (cx + 8.0, cy + 43.0),
            "GND": (cx + 24.0, cy + 43.0),
        }
        if "ANALOG" in self.pines_conectados:
            puntos["ANALOG"] = (cx + 8.0, cy + 43.0)
        return puntos
