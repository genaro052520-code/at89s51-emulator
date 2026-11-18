"""Módulo de Protoboard y Cableado Virtual estilo Tinkercad para el AT89S51.

Provee la representación física de una placa de pruebas (breadboard) con buses
de alimentación (+ / -), bloques centrales de perforaciones (filas a-e y f-j por
30 columnas) y cables virtuales suaves (`smooth=True`) que enlazan los pines del
encapsulado DIP-40 del AT89S51 con los terminales de cada componente electrónico.

Regla arquitectónica: Este módulo NO importa nada de `src/core/` ni `src/storage/`.
Toda lectura o escritura de estado eléctrico se realiza exclusivamente mediante
`ADM` (`src/ports/adm.py`).
"""

from __future__ import annotations

import tkinter as tk
from typing import Any
import uuid

from src.gui.components.base import ComponenteElectronico
from src.ports.adm import ADM


FILAS_BLOQUE_SUPERIOR: tuple[str, ...] = ("a", "b", "c", "d", "e")
FILAS_BLOQUE_INFERIOR: tuple[str, ...] = ("f", "g", "h", "i", "j")
TODAS_FILAS_NODO: tuple[str, ...] = FILAS_BLOQUE_SUPERIOR + FILAS_BLOQUE_INFERIOR


def normalizar_destino_adm(destino: int | str) -> tuple[str, int | None, str]:
    """Normaliza un identificador de pin/canal del 8051 hacia su índice en `ADM`."""
    if isinstance(destino, int) and not isinstance(destino, bool):
        if 0 <= destino < ADM.TOTAL_PINES_DIGITALES:
            puerto = destino // 8
            bit = destino % 8
            return f"P{puerto}.{bit}", destino, "digital"
        if ADM.TOTAL_PINES_DIGITALES <= destino < ADM.TOTAL_CANALES:
            an_idx = destino - ADM.TOTAL_PINES_DIGITALES
            return f"AN{an_idx}", destino, "analog"
        raise ValueError(
            f"Índice de canal ADM fuera de rango: {destino}. "
            f"Use 0-31 (P0.0-P3.7) o 32-39 (AN0-AN7)."
        )

    if isinstance(destino, str):
        limpio = destino.strip().upper()
        if "(" in limpio:
            limpio = limpio.split("(", 1)[0].strip()
        if "/" in limpio:
            limpio = limpio.split("/", 1)[0].strip()

        if limpio in ("VCC", "+5V", "5V", "+"):
            return "VCC", None, "vcc"
        if limpio in ("GND", "0V", "-"):
            return "GND", None, "gnd"

        if limpio.startswith("P") and "." in limpio:
            partes = limpio[1:].split(".")
            if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                puerto = int(partes[0])
                bit = int(partes[1])
                if 0 <= puerto <= 3 and 0 <= bit <= 7:
                    canal = puerto * 8 + bit
                    return f"P{puerto}.{bit}", canal, "digital"

        if limpio.startswith(("AN", "AI")) and limpio[2:].isdigit():
            an_idx = int(limpio[2:])
            if 0 <= an_idx < ADM.CANALES_ANALOGICOS_AUX:
                canal = ADM.TOTAL_PINES_DIGITALES + an_idx
                return f"AN{an_idx}", canal, "analog"

    raise ValueError(
        f"Identificador de pin/canal inválido: '{destino}'. "
        "Formatos válidos: 'P0.0'-'P3.7', 'AN0'-'AN7', 'VCC', 'GND' o entero 0-39."
    )


def formatear_canal_adm(canal: int | None, tipo_senal: str = "digital") -> str:
    """Convierte un índice de `ADM` en su etiqueta legible (`P1.0`, `AN0`, `VCC`, `GND`)."""
    if canal is None:
        return "VCC" if tipo_senal == "vcc" else "GND"
    etiqueta, _, _ = normalizar_destino_adm(canal)
    return etiqueta


class CableVirtual:
    """Cable puente virtual (jumper wire) estilo Tinkercad entre el 8051 y un componente."""

    PALETA_SENALES: tuple[str, ...] = (
        "#10B981",
        "#F59E0B",
        "#F97316",
        "#06B6D4",
        "#A855F7",
        "#EC4899",
    )

    COLOR_VCC: str = "#EF4444"
    COLOR_GND: str = "#1E3A8A"
    COLOR_RESALTADO_ALTO: str = "#00E676"

    def __init__(
        self,
        origen_etiqueta: str,
        destino_componente: ComponenteElectronico,
        destino_terminal: str,
        punto_origen: tuple[float, float],
        punto_destino: tuple[float, float],
        canal_adm: int | None = None,
        tipo_senal: str = "digital",
        color_base: str | None = None,
        nodo_protoboard: tuple[str, int] | None = None,
    ) -> None:
        self.id_cable: str = f"wire_{uuid.uuid4().hex[:8]}"
        self.origen_etiqueta: str = origen_etiqueta
        self.destino_componente: ComponenteElectronico = destino_componente
        self.destino_terminal: str = destino_terminal
        self.punto_origen: tuple[float, float] = (float(punto_origen[0]), float(punto_origen[1]))
        self.punto_destino: tuple[float, float] = (float(punto_destino[0]), float(punto_destino[1]))
        self.canal_adm: int | None = canal_adm
        self.tipo_senal: str = tipo_senal
        self.nodo_protoboard: tuple[str, int] | None = nodo_protoboard

        if color_base is not None:
            self.color_base: str = color_base
        elif tipo_senal == "vcc":
            self.color_base = self.COLOR_VCC
        elif tipo_senal == "gnd":
            self.color_base = self.COLOR_GND
        else:
            idx_color = (canal_adm or 0) % len(self.PALETA_SENALES)
            self.color_base = self.PALETA_SENALES[idx_color]

        self.estado_alto: bool = tipo_senal == "vcc"
        self.voltaje: float = ADM.VOLTAJE_ALTO if tipo_senal == "vcc" else ADM.VOLTAJE_BAJO

        self.canvas: tk.Canvas | None = None
        self.tag_grupo: str = f"tag_{self.id_cable}"
        self._id_halo: int | None = None
        self._id_linea: int | None = None
        self._id_punta_origen: int | None = None
        self._id_punta_destino: int | None = None

    def calcular_puntos_curva(self) -> list[float]:
        """Genera puntos de control para dibujar una curva suave tipo puente Tinkercad."""
        x1, y1 = self.punto_origen
        x2, y2 = self.punto_destino

        dx = x2 - x1
        dy = y2 - y1
        distancia = (dx * dx + dy * dy) ** 0.5
        curvatura = min(55.0, max(18.0, distancia * 0.22))

        salida_x = x1 + (24.0 if dx >= 0 else -24.0)
        salida_y = y1

        ctrl_mid_x = (x1 + x2) / 2.0
        ctrl_mid_y = min(y1, y2) - curvatura if abs(dy) < 90.0 else (y1 + y2) / 2.0 - curvatura * 0.4

        llegada_x = x2
        llegada_y = y2 - 18.0 if y2 >= y1 else y2 + 18.0

        return [
            x1, y1,
            salida_x, salida_y,
            ctrl_mid_x, ctrl_mid_y,
            llegada_x, llegada_y,
            x2, y2,
        ]

    def dibujar(self, canvas: tk.Canvas) -> None:
        """Renderiza el cable virtual con halo de actividad y conectores en sus extremos."""
        self.eliminar()
        self.canvas = canvas
        tag = self.tag_grupo
        coords = self.calcular_puntos_curva()

        self._id_halo = canvas.create_line(
            *coords,
            smooth=True,
            splinesteps=24,
            width=6.5,
            fill="",
            capstyle=tk.ROUND,
            tags=(tag, "cable_virtual"),
        )

        self._id_linea = canvas.create_line(
            *coords,
            smooth=True,
            splinesteps=24,
            width=3.0,
            fill=self.color_base,
            capstyle=tk.ROUND,
            tags=(tag, "cable_virtual"),
        )

        ox, oy = self.punto_origen
        self._id_punta_origen = canvas.create_oval(
            ox - 4.5, oy - 4.5, ox + 4.5, oy + 4.5,
            fill=self.color_base,
            outline="#F8FAFC",
            width=1.2,
            tags=(tag, "cable_virtual"),
        )

        dx, dy = self.punto_destino
        self._id_punta_destino = canvas.create_oval(
            dx - 4.5, dy - 4.5, dx + 4.5, dy + 4.5,
            fill=self.color_base,
            outline="#F8FAFC",
            width=1.2,
            tags=(tag, "cable_virtual"),
        )

        self._aplicar_estilo_estado()

    def actualizar_extremos(
        self,
        punto_origen: tuple[float, float] | None = None,
        punto_destino: tuple[float, float] | None = None,
    ) -> None:
        """Recalcula la geometría de la curva si el chip o el componente cambiaron de posición."""
        if punto_origen is not None:
            self.punto_origen = (float(punto_origen[0]), float(punto_origen[1]))
        if punto_destino is not None:
            self.punto_destino = (float(punto_destino[0]), float(punto_destino[1]))

        if self.canvas is None or self._id_linea is None:
            return

        coords = self.calcular_puntos_curva()
        self.canvas.coords(self._id_linea, *coords)
        if self._id_halo is not None:
            self.canvas.coords(self._id_halo, *coords)

        ox, oy = self.punto_origen
        if self._id_punta_origen is not None:
            self.canvas.coords(self._id_punta_origen, ox - 4.5, oy - 4.5, ox + 4.5, oy + 4.5)

        dx, dy = self.punto_destino
        if self._id_punta_destino is not None:
            self.canvas.coords(self._id_punta_destino, dx - 4.5, dy - 4.5, dx + 4.5, dy + 4.5)

    def _aplicar_estilo_estado(self) -> None:
        """Ilumina el cable cuando transporta nivel lógico alto (5V)."""
        if self.canvas is None or self._id_linea is None:
            return

        if self.tipo_senal == "vcc":
            self.canvas.itemconfig(self._id_linea, fill=self.COLOR_VCC, width=3.2)
            if self._id_halo is not None:
                self.canvas.itemconfig(self._id_halo, fill="#7F1D1D")
            return

        if self.tipo_senal == "gnd":
            self.canvas.itemconfig(self._id_linea, fill="#3B82F6", width=2.8)
            if self._id_halo is not None:
                self.canvas.itemconfig(self._id_halo, fill="")
            return

        if self.estado_alto:
            color_activo = "#38BDF8" if self.tipo_senal == "analog" else self.COLOR_RESALTADO_ALTO
            self.canvas.itemconfig(self._id_linea, fill=color_activo, width=3.6)
            if self._id_halo is not None:
                self.canvas.itemconfig(self._id_halo, fill="#064E3B")
            if self._id_punta_origen is not None:
                self.canvas.itemconfig(self._id_punta_origen, fill=color_activo)
            if self._id_punta_destino is not None:
                self.canvas.itemconfig(self._id_punta_destino, fill=color_activo)
        else:
            self.canvas.itemconfig(self._id_linea, fill=self.color_base, width=2.6)
            if self._id_halo is not None:
                self.canvas.itemconfig(self._id_halo, fill="")
            if self._id_punta_origen is not None:
                self.canvas.itemconfig(self._id_punta_origen, fill=self.color_base)
            if self._id_punta_destino is not None:
                self.canvas.itemconfig(self._id_punta_destino, fill=self.color_base)

    def actualizar_desde_adm(self, adm: ADM) -> bool:
        """Consulta el voltaje del canal en `ADM`, actualiza el resaltado y retorna si está en alto."""
        if self.tipo_senal == "vcc":
            self.voltaje = ADM.VOLTAJE_ALTO
            self.estado_alto = True
        elif self.tipo_senal == "gnd" or self.canal_adm is None:
            self.voltaje = ADM.VOLTAJE_BAJO
            self.estado_alto = False
        else:
            self.voltaje = adm.leerPuertoAnalogico(self.canal_adm)
            self.estado_alto = self.voltaje >= ADM.UMBRAL_LOGICO

        self._aplicar_estilo_estado()
        return self.estado_alto

    def eliminar(self) -> None:
        """Elimina todos los elementos gráficos del cable en el canvas."""
        if self.canvas is not None:
            self.canvas.delete(self.tag_grupo)
        self._id_halo = None
        self._id_linea = None
        self._id_punta_origen = None
        self._id_punta_destino = None


class Protoboard:
    """Placa de pruebas (Protoboard) interactiva estilo Tinkercad para el AT89S51."""

    COLOR_CUERPO: str = "#E2E8F0"
    COLOR_BORDE: str = "#94A3B8"
    COLOR_CANAL_DIP: str = "#CBD5E1"
    COLOR_BUS_VCC: str = "#EF4444"
    COLOR_BUS_GND: str = "#2563EB"
    COLOR_NODO_REPOSO: str = "#1E293B"
    COLOR_NODO_BORDE: str = "#64748B"
    COLOR_NODO_ALTO: str = "#00E676"
    COLOR_NODO_ALTO_BORDE: str = "#86EFAC"

    def __init__(
        self,
        x: float = 520.0,
        y: float = 40.0,
        columnas: int = 30,
        espaciado: float = 17.0,
        puntos_pines_8051: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.x: float = float(x)
        self.y: float = float(y)
        self.columnas: int = int(columnas)
        self.espaciado: float = float(espaciado)

        self.canvas: tk.Canvas | None = None
        self.tag_grupo: str = f"protoboard_{uuid.uuid4().hex[:8]}"

        self._coordenadas_nodos: dict[tuple[str, int], tuple[float, float]] = {}
        self._ids_nodos_canvas: dict[tuple[str, int], int] = {}
        self._nodos_iluminados: set[tuple[str, int]] = set()

        self.puntos_pines_8051: dict[str, tuple[float, float]] = (
            dict(puntos_pines_8051)
            if puntos_pines_8051 is not None
            else self._generar_puntos_pines_dip40_por_defecto()
        )

        self.componentes_montados: dict[str, dict[str, Any]] = {}
        self.cables: dict[str, CableVirtual] = {}

    def _generar_puntos_pines_dip40_por_defecto(self) -> dict[str, tuple[float, float]]:
        puntos: dict[str, tuple[float, float]] = {}
        base_x_izq = max(40.0, self.x - 280.0)
        base_x_der = max(180.0, self.x - 130.0)
        y_ini = self.y + 30.0
        paso = 14.0

        for bit in range(8):
            puntos[f"P1.{bit}"] = (base_x_izq, y_ini + bit * paso)

        for bit in range(8):
            puntos[f"P3.{bit}"] = (base_x_izq, y_ini + (9 + bit) * paso)

        puntos["GND"] = (base_x_izq, y_ini + 19 * paso)
        puntos["VCC"] = (base_x_der, y_ini)

        for bit in range(8):
            puntos[f"P0.{bit}"] = (base_x_der, y_ini + (1 + bit) * paso)

        for idx, bit in enumerate(range(7, -1, -1)):
            puntos[f"P2.{bit}"] = (base_x_der, y_ini + (12 + idx) * paso)

        for an_idx in range(8):
            puntos[f"AN{an_idx}"] = (base_x_der, y_ini + (20 + an_idx) * paso)

        return puntos

    def registrar_punto_pin_8051(self, etiqueta_pin: str, x: float, y: float) -> None:
        etiqueta, _, _ = normalizar_destino_adm(etiqueta_pin)
        self.puntos_pines_8051[etiqueta] = (float(x), float(y))
        for cable in self.cables.values():
            if cable.origen_etiqueta == etiqueta:
                cable.actualizar_extremos(punto_origen=(x, y))

    def obtener_coordenada_nodo(self, fila: str, columna: int) -> tuple[float, float]:
        clave = (fila.lower(), int(columna))
        if clave not in self._coordenadas_nodos:
            raise KeyError(
                f"Nodo de protoboard inexistente: fila='{fila}', columna={columna}. "
                f"Use filas a-j y columnas 1-{self.columnas}."
            )
        return self._coordenadas_nodos[clave]

    def dibujar(self, canvas: tk.Canvas) -> None:
        self.eliminar()
        self.canvas = canvas
        self._coordenadas_nodos.clear()
        self._ids_nodos_canvas.clear()

        tag = self.tag_grupo
        margen_x = 34.0
        margen_y = 22.0
        ancho_matriz = (self.columnas - 1) * self.espaciado
        ancho_total = ancho_matriz + margen_x * 2.0

        y_bus_sup_vcc = self.y + margen_y
        y_bus_sup_gnd = y_bus_sup_vcc + self.espaciado
        y_bloque_sup_ini = y_bus_sup_gnd + self.espaciado * 1.45
        y_canal_dip = y_bloque_sup_ini + 4 * self.espaciado + self.espaciado * 0.85
        y_bloque_inf_ini = y_canal_dip + self.espaciado * 1.15
        y_bus_inf_vcc = y_bloque_inf_ini + 4 * self.espaciado + self.espaciado * 1.45
        y_bus_inf_gnd = y_bus_inf_vcc + self.espaciado
        alto_total = (y_bus_inf_gnd - self.y) + margen_y

        x_col_1 = self.x + margen_x

        canvas.create_rectangle(
            self.x,
            self.y,
            self.x + ancho_total,
            self.y + alto_total,
            fill=self.COLOR_CUERPO,
            outline=self.COLOR_BORDE,
            width=2,
            tags=(tag,),
        )

        canvas.create_rectangle(
            self.x + 8.0,
            y_canal_dip - 6.0,
            self.x + ancho_total - 8.0,
            y_canal_dip + 6.0,
            fill=self.COLOR_CANAL_DIP,
            outline="#94A3B8",
            width=1,
            tags=(tag,),
        )

        self._dibujar_buses_alimentacion(
            canvas, x_col_1, ancho_matriz, y_bus_sup_vcc, y_bus_sup_gnd, prefijo="sup"
        )
        self._dibujar_buses_alimentacion(
            canvas, x_col_1, ancho_matriz, y_bus_inf_vcc, y_bus_inf_gnd, prefijo="inf"
        )

        for idx_fila, nombre_fila in enumerate(FILAS_BLOQUE_SUPERIOR):
            fy = y_bloque_sup_ini + idx_fila * self.espaciado
            self._dibujar_fila_perforaciones(canvas, x_col_1, fy, nombre_fila)

        for idx_fila, nombre_fila in enumerate(FILAS_BLOQUE_INFERIOR):
            fy = y_bloque_inf_ini + idx_fila * self.espaciado
            self._dibujar_fila_perforaciones(canvas, x_col_1, fy, nombre_fila)

        y_num_sup = y_bloque_sup_ini - 12.0
        y_num_inf = y_bloque_inf_ini + 4 * self.espaciado + 12.0
        for col in range(1, self.columnas + 1):
            if col == 1 or col % 5 == 0:
                cx = x_col_1 + (col - 1) * self.espaciado
                canvas.create_text(
                    cx, y_num_sup, text=str(col), fill="#475569",
                    font=("Consolas", 7, "bold"), tags=(tag,),
                )
                canvas.create_text(
                    cx, y_num_inf, text=str(col), fill="#475569",
                    font=("Consolas", 7, "bold"), tags=(tag,),
                )

        for info in self.componentes_montados.values():
            comp: ComponenteElectronico = info["componente"]
            comp.dibujar(canvas)
            info["coordenadas_terminales"] = comp.obtener_puntos_conexion()

        for cable in self.cables.values():
            cable.dibujar(canvas)

    def _dibujar_buses_alimentacion(
        self,
        canvas: tk.Canvas,
        x_inicio: float,
        ancho_matriz: float,
        y_vcc: float,
        y_gnd: float,
        prefijo: str,
    ) -> None:
        tag = self.tag_grupo

        canvas.create_line(
            x_inicio, y_vcc - 6.5, x_inicio + ancho_matriz, y_vcc - 6.5,
            fill=self.COLOR_BUS_VCC, width=1.6, tags=(tag,),
        )
        canvas.create_line(
            x_inicio, y_gnd + 6.5, x_inicio + ancho_matriz, y_gnd + 6.5,
            fill=self.COLOR_BUS_GND, width=1.6, tags=(tag,),
        )

        for sx in (x_inicio - 16.0, x_inicio + ancho_matriz + 16.0):
            canvas.create_text(
                sx, y_vcc, text="+", fill=self.COLOR_BUS_VCC,
                font=("Consolas", 10, "bold"), tags=(tag,),
            )
            canvas.create_text(
                sx, y_gnd, text="-", fill=self.COLOR_BUS_GND,
                font=("Consolas", 10, "bold"), tags=(tag,),
            )

        radio = 3.2
        hole_idx = 0
        for col in range(self.columnas):
            if col % 6 == 5:
                continue
            hole_idx += 1
            hx = x_inicio + col * self.espaciado

            id_vcc = canvas.create_oval(
                hx - radio, y_vcc - radio, hx + radio, y_vcc + radio,
                fill="#991B1B", outline=self.COLOR_BUS_VCC, width=1.1, tags=(tag,),
            )
            self._coordenadas_nodos[(f"vcc_{prefijo}", hole_idx)] = (hx, y_vcc)
            self._ids_nodos_canvas[(f"vcc_{prefijo}", hole_idx)] = id_vcc

            id_gnd = canvas.create_oval(
                hx - radio, y_gnd - radio, hx + radio, y_gnd + radio,
                fill="#1E3A8A", outline=self.COLOR_BUS_GND, width=1.1, tags=(tag,),
            )
            self._coordenadas_nodos[(f"gnd_{prefijo}", hole_idx)] = (hx, y_gnd)
            self._ids_nodos_canvas[(f"gnd_{prefijo}", hole_idx)] = id_gnd

    def _dibujar_fila_perforaciones(
        self,
        canvas: tk.Canvas,
        x_inicio: float,
        y_fila: float,
        nombre_fila: str,
    ) -> None:
        tag = self.tag_grupo
        ancho_matriz = (self.columnas - 1) * self.espaciado

        canvas.create_text(
            x_inicio - 16.0, y_fila, text=nombre_fila, fill="#334155",
            font=("Consolas", 8, "bold"), tags=(tag,),
        )
        canvas.create_text(
            x_inicio + ancho_matriz + 16.0, y_fila, text=nombre_fila, fill="#334155",
            font=("Consolas", 8, "bold"), tags=(tag,),
        )

        radio = 3.4
        for col in range(1, self.columnas + 1):
            hx = x_inicio + (col - 1) * self.espaciado
            hole_id = canvas.create_oval(
                hx - radio,
                y_fila - radio,
                hx + radio,
                y_fila + radio,
                fill=self.COLOR_NODO_REPOSO,
                outline=self.COLOR_NODO_BORDE,
                width=1.0,
                tags=(tag, f"hole_{nombre_fila}_{col}"),
            )
            self._coordenadas_nodos[(nombre_fila, col)] = (hx, y_fila)
            self._ids_nodos_canvas[(nombre_fila, col)] = hole_id

    def eliminar(self) -> None:
        if self.canvas is not None:
            self.canvas.delete(self.tag_grupo)

    def _buscar_columna_libre(self) -> int:
        columnas_ocupadas = {
            int(info["columna"]) for info in self.componentes_montados.values()
        }
        for candidata in range(3, self.columnas - 2, 5):
            if candidata not in columnas_ocupadas:
                return candidata
        for candidata in range(1, self.columnas + 1):
            if candidata not in columnas_ocupadas:
                return candidata
        return 1

    def montar_componente(
        self,
        componente: ComponenteElectronico,
        columna: int | None = None,
        fila: str = "c",
        auto_cablear: bool = True,
        adm: ADM | None = None,
    ) -> dict[str, Any]:
        col_elegida = columna if columna is not None else self._buscar_columna_libre()
        fila_norm = fila.lower()

        if (fila_norm, col_elegida) in self._coordenadas_nodos:
            nx, ny = self._coordenadas_nodos[(fila_norm, col_elegida)]
            componente.establecer_posicion(nx, ny)

        if self.canvas is not None:
            componente.dibujar(self.canvas)

        coordenadas_term = componente.obtener_puntos_conexion()
        registro: dict[str, Any] = {
            "componente": componente,
            "fila": fila_norm,
            "columna": col_elegida,
            "coordenadas_terminales": coordenadas_term,
        }
        self.componentes_montados[componente.tag_grupo] = registro

        if auto_cablear:
            for terminal, destino in list(componente.pines_conectados.items()):
                if terminal == "PUERTO":
                    destino_pin = int(destino) * 8
                    self.conectar_componente(
                        componente=componente,
                        destino_adm=destino_pin,
                        terminal=terminal,
                        fila_nodo=fila_norm,
                        columna_nodo=col_elegida,
                        adm=adm,
                    )
                else:
                    self.conectar_componente(
                        componente=componente,
                        destino_adm=destino,
                        terminal=terminal,
                        fila_nodo=fila_norm,
                        columna_nodo=col_elegida,
                        adm=adm,
                    )

        return registro

    def desmontar_componente(
        self,
        componente: ComponenteElectronico | str,
        adm: ADM | None = None,
    ) -> bool:
        comp_id = componente.tag_grupo if isinstance(componente, ComponenteElectronico) else componente
        registro = self.componentes_montados.pop(comp_id, None)
        if registro is None:
            return False

        comp_obj: ComponenteElectronico = registro["componente"]
        self.desconectar_componente(comp_obj, adm=adm)
        comp_obj.eliminar()
        return True

    @staticmethod
    def _inferir_terminal_componente(
        componente: ComponenteElectronico,
        tipo_senal: str,
    ) -> str:
        if tipo_senal == "vcc" and "VCC" in componente.pines_conectados:
            return "VCC"
        if tipo_senal == "gnd" and "GND" in componente.pines_conectados:
            return "GND"

        if tipo_senal == "analog":
            for candidato in ("ANALOG", "SIG", "OUT", "IN", "ECHO"):
                if candidato in componente.pines_conectados:
                    return candidato

        for candidato in ("IN", "OUT", "SIG", "ECHO", "ANALOG", "PUERTO"):
            if candidato in componente.pines_conectados:
                return candidato

        terminales_geom = list(componente.obtener_puntos_conexion().keys())
        if terminales_geom:
            return terminales_geom[0]
        return "IN"

    def conectar_componente(
        self,
        componente: ComponenteElectronico,
        destino_adm: int | str,
        terminal: str | None = None,
        fila_nodo: str | None = None,
        columna_nodo: int | None = None,
        color_cable: str | None = None,
        adm: ADM | None = None,
    ) -> CableVirtual:
        etiqueta_pin, canal_adm, tipo_senal = normalizar_destino_adm(destino_adm)
        term_elegido = (
            terminal
            if terminal is not None
            else self._inferir_terminal_componente(componente, tipo_senal)
        )

        self.desconectar_componente(componente, terminal=term_elegido, adm=adm)

        if canal_adm is not None:
            if term_elegido == "PUERTO":
                puerto_8bit = canal_adm // 8 if canal_adm < 32 else 0
                componente.pines_conectados["PUERTO"] = puerto_8bit
                componente.propiedades["puerto"] = puerto_8bit
            else:
                componente.pines_conectados[term_elegido] = canal_adm
                if tipo_senal == "analog" and "canal" in componente.propiedades:
                    componente.propiedades["canal"] = canal_adm
                else:
                    componente.propiedades["pin"] = canal_adm

            if hasattr(componente, "_sincronizado_inicial"):
                setattr(componente, "_sincronizado_inicial", False)

            if self.canvas is not None:
                componente.dibujar(self.canvas)

        if componente.tag_grupo not in self.componentes_montados:
            self.componentes_montados[componente.tag_grupo] = {
                "componente": componente,
                "fila": (fila_nodo or "c").lower(),
                "columna": columna_nodo or self._buscar_columna_libre(),
                "coordenadas_terminales": componente.obtener_puntos_conexion(),
            }
        else:
            self.componentes_montados[componente.tag_grupo][
                "coordenadas_terminales"
            ] = componente.obtener_puntos_conexion()

        reg_comp = self.componentes_montados[componente.tag_grupo]
        coords_term = reg_comp["coordenadas_terminales"]

        nodo_asignado: tuple[str, int] | None = None
        if fila_nodo is not None and columna_nodo is not None:
            clave_nodo = (fila_nodo.lower(), int(columna_nodo))
            if clave_nodo in self._coordenadas_nodos:
                nodo_asignado = clave_nodo
        else:
            clave_defecto = (str(reg_comp["fila"]), int(reg_comp["columna"]))
            if clave_defecto in self._coordenadas_nodos:
                nodo_asignado = clave_defecto

        if term_elegido in coords_term:
            punto_destino = coords_term[term_elegido]
        elif nodo_asignado is not None:
            punto_destino = self._coordenadas_nodos[nodo_asignado]
        else:
            punto_destino = (componente.x, componente.y)

        punto_origen = self.puntos_pines_8051.get(
            etiqueta_pin,
            (self.x - 120.0, self.y + 40.0),
        )

        cable = CableVirtual(
            origen_etiqueta=etiqueta_pin,
            destino_componente=componente,
            destino_terminal=term_elegido,
            punto_origen=punto_origen,
            punto_destino=punto_destino,
            canal_adm=canal_adm,
            tipo_senal=tipo_senal,
            color_base=color_cable,
            nodo_protoboard=nodo_asignado,
        )

        if self.canvas is not None:
            cable.dibujar(self.canvas)

        if adm is not None:
            cable.actualizar_desde_adm(adm)
            componente.actualizar_desde_adm(adm)

        self.cables[cable.id_cable] = cable
        return cable

    def desconectar_componente(
        self,
        componente: ComponenteElectronico,
        terminal: str | None = None,
        destino_adm: int | str | None = None,
        adm: ADM | None = None,
    ) -> list[CableVirtual]:
        etiqueta_filtro: str | None = None
        if destino_adm is not None:
            etiqueta_filtro, _, _ = normalizar_destino_adm(destino_adm)

        eliminados: list[CableVirtual] = []
        for cid, cable in list(self.cables.items()):
            if cable.destino_componente is not componente:
                continue
            if terminal is not None and cable.destino_terminal != terminal:
                continue
            if etiqueta_filtro is not None and cable.origen_etiqueta != etiqueta_filtro:
                continue

            if adm is not None and cable.canal_adm is not None:
                try:
                    adm.liberar_estimulo_externo(cable.canal_adm)
                except ValueError:
                    pass

            cable.eliminar()
            del self.cables[cid]
            eliminados.append(cable)

        return eliminados

    def _actualizar_iluminacion_nodos(self, nodos_activos: set[tuple[str, int]]) -> None:
        if self.canvas is None:
            return

        todos_agujeros_altos: set[tuple[str, int]] = set()
        for fila, col in nodos_activos:
            if fila in FILAS_BLOQUE_SUPERIOR:
                for f_strip in FILAS_BLOQUE_SUPERIOR:
                    todos_agujeros_altos.add((f_strip, col))
            elif fila in FILAS_BLOQUE_INFERIOR:
                for f_strip in FILAS_BLOQUE_INFERIOR:
                    todos_agujeros_altos.add((f_strip, col))
            else:
                todos_agujeros_altos.add((fila, col))

        for clave in self._nodos_iluminados - todos_agujeros_altos:
            hole_id = self._ids_nodos_canvas.get(clave)
            if hole_id is not None:
                self.canvas.itemconfig(
                    hole_id,
                    fill=self.COLOR_NODO_REPOSO,
                    outline=self.COLOR_NODO_BORDE,
                )

        for clave in todos_agujeros_altos:
            hole_id = self._ids_nodos_canvas.get(clave)
            if hole_id is not None:
                self.canvas.itemconfig(
                    hole_id,
                    fill=self.COLOR_NODO_ALTO,
                    outline=self.COLOR_NODO_ALTO_BORDE,
                )

        self._nodos_iluminados = todos_agujeros_altos

    def actualizar_desde_adm(self, adm: ADM) -> None:
        nodos_con_5v: set[tuple[str, int]] = set()

        for info in self.componentes_montados.values():
            comp: ComponenteElectronico = info["componente"]
            info["coordenadas_terminales"] = comp.obtener_puntos_conexion()

        for cable in self.cables.values():
            comp = cable.destino_componente
            reg = self.componentes_montados.get(comp.tag_grupo)
            if reg is not None:
                coords_term = reg["coordenadas_terminales"]
                if cable.destino_terminal in coords_term:
                    cable.actualizar_extremos(punto_destino=coords_term[cable.destino_terminal])

            en_alto = cable.actualizar_desde_adm(adm)
            if en_alto and cable.nodo_protoboard is not None:
                nodos_con_5v.add(cable.nodo_protoboard)

        self._actualizar_iluminacion_nodos(nodos_con_5v)

        for info in self.componentes_montados.values():
            comp = info["componente"]
            comp.actualizar_desde_adm(adm)
