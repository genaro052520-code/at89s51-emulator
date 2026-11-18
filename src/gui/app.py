"""Interfaz gráfica independiente (GUI) estilo Tinkercad para el AT89S51.

Distribuye el entorno de simulación en tres zonas desacopladas del núcleo CPU:
1. Izquierda: Encapsulado físico DIP-40 del Atmel/Microchip AT89S51 con sus
   40 pines interactivos, botón hardware RESET (Pin 9) y monitor hexadecimal
   en tiempo real de P0, P1, P2 y P3.
2. Centro: Mesa de trabajo con la Protoboard, el bus de pines del AT89S51,
   los cables virtuales curvados (`CableVirtual`) y el Panel Inspector de
   Propiedades en vivo.
3. Derecha: Paleta con los 10 componentes electrónicos (5 actuadores y 5
   sensores/entradas), selector de pin (P0.0-P3.7) y circuitos de demostración
   prearmados de un clic.

Regla arquitectónica: Este módulo NO importa nada de `src/core/` ni `src/storage/`.
Toda comunicación ocurre exclusivamente mediante `ADM` (`src/ports/adm.py`).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Sequence

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
from src.gui.protoboard import (
    FILAS_BLOQUE_INFERIOR,
    FILAS_BLOQUE_SUPERIOR,
    Protoboard,
    formatear_canal_adm,
    normalizar_destino_adm,
)
from src.ports.adm import ADM


@dataclass(frozen=True)
class PinDIP40:
    """Descriptor físico y eléctrico de cada uno de los 40 pines del AT89S51."""

    numero_dip: int
    etiqueta: str
    adm_canal: int | None
    tipo: str


PINES_IZQUIERDA: list[PinDIP40] = [
    PinDIP40(1, "P1.0", 8, "io"),
    PinDIP40(2, "P1.1", 9, "io"),
    PinDIP40(3, "P1.2", 10, "io"),
    PinDIP40(4, "P1.3", 11, "io"),
    PinDIP40(5, "P1.4", 12, "io"),
    PinDIP40(6, "P1.5", 13, "io"),
    PinDIP40(7, "P1.6", 14, "io"),
    PinDIP40(8, "P1.7", 15, "io"),
    PinDIP40(9, "RST", None, "rst"),
    PinDIP40(10, "P3.0 / RXD", 24, "io"),
    PinDIP40(11, "P3.1 / TXD", 25, "io"),
    PinDIP40(12, "P3.2 / INT0", 26, "io"),
    PinDIP40(13, "P3.3 / INT1", 27, "io"),
    PinDIP40(14, "P3.4 / T0", 28, "io"),
    PinDIP40(15, "P3.5 / T1", 29, "io"),
    PinDIP40(16, "P3.6 / WR", 30, "io"),
    PinDIP40(17, "P3.7 / RD", 31, "io"),
    PinDIP40(18, "XTAL2", None, "xtal"),
    PinDIP40(19, "XTAL1", None, "xtal"),
    PinDIP40(20, "GND", None, "gnd"),
]

PINES_DERECHA_TOP_DOWN: list[PinDIP40] = [
    PinDIP40(40, "VCC (+5V)", None, "vcc"),
    PinDIP40(39, "P0.0 / AD0", 0, "io"),
    PinDIP40(38, "P0.1 / AD1", 1, "io"),
    PinDIP40(37, "P0.2 / AD2", 2, "io"),
    PinDIP40(36, "P0.3 / AD3", 3, "io"),
    PinDIP40(35, "P0.4 / AD4", 4, "io"),
    PinDIP40(34, "P0.5 / AD5", 5, "io"),
    PinDIP40(33, "P0.6 / AD6", 6, "io"),
    PinDIP40(32, "P0.7 / AD7", 7, "io"),
    PinDIP40(31, "EA / VPP", None, "ctrl"),
    PinDIP40(30, "ALE / PROG", None, "ctrl"),
    PinDIP40(29, "PSEN", None, "ctrl"),
    PinDIP40(28, "P2.7 / A15", 23, "io"),
    PinDIP40(27, "P2.6 / A14", 22, "io"),
    PinDIP40(26, "P2.5 / A13", 21, "io"),
    PinDIP40(25, "P2.4 / A12", 20, "io"),
    PinDIP40(24, "P2.3 / A11", 19, "io"),
    PinDIP40(23, "P2.2 / A10", 18, "io"),
    PinDIP40(22, "P2.1 / A9", 17, "io"),
    PinDIP40(21, "P2.0 / A8", 16, "io"),
]


def _construir_opciones_pines_io() -> dict[str, int]:
    """Genera el mapa ordenado de etiquetas `P0.0`..`P3.7` hacia índices ADM `0..31`."""
    opciones: dict[str, int] = {}
    nombres_puertos = [
        (0, "P0", ["AD0", "AD1", "AD2", "AD3", "AD4", "AD5", "AD6", "AD7"]),
        (1, "P1", ["T2", "T2EX", "", "", "", "MOSI", "MISO", "SCK"]),
        (2, "P2", ["A8", "A9", "A10", "A11", "A12", "A13", "A14", "A15"]),
        (3, "P3", ["RXD", "TXD", "INT0", "INT1", "T0", "T1", "WR", "RD"]),
    ]
    for p_idx, p_nombre, alt_funcs in nombres_puertos:
        for bit in range(8):
            adm_idx = p_idx * 8 + bit
            sufijo = f" ({alt_funcs[bit]})" if alt_funcs[bit] else ""
            etiqueta = f"{p_nombre}.{bit}{sufijo}"
            opciones[etiqueta] = adm_idx
    return opciones


class AT89S51EmulatorGUI:
    """Laboratorio virtual Tkinter estilo Tinkercad para el microcontrolador AT89S51."""

    POLL_INTERVAL_MS: int = 50

    BG_APP: str = "#0B1120"
    BG_CARD: str = "#1E293B"
    BG_PANEL_INNER: str = "#0F172A"
    BG_WORKBENCH: str = "#111827"
    CHIP_BODY: str = "#181B20"
    CHIP_BORDER: str = "#475569"
    PIN_METAL: str = "#CBD5E1"
    TEXT_PRIMARY: str = "#F8FAFC"
    TEXT_MUTED: str = "#94A3B8"
    ACCENT_CYAN: str = "#38BDF8"

    COLOR_PIN_ALTO: str = "#00E676"
    COLOR_PIN_BAJO: str = "#334155"
    COLOR_PIN_VCC: str = "#EF4444"
    COLOR_PIN_GND: str = "#3B82F6"
    COLOR_PIN_XTAL: str = "#F59E0B"

    def __init__(self, root: tk.Tk, adm: ADM) -> None:
        self.root: tk.Tk = root
        self.adm: ADM = adm
        self._after_id: str | None = None
        self._reset_activo: bool = False
        self._xtal_toggle: bool = False

        self._pin_indicators: dict[int, int] = {}
        self._pin_meta: dict[int, PinDIP40] = {}
        self._bus_sockets_leds: dict[str, int] = {}

        self.componentes_activos: list[ComponenteElectronico] = []
        self._componente_seleccionado: ComponenteElectronico | None = None
        self._id_marco_seleccion: int | None = None
        self._arrastre_activo: dict[str, Any] = {
            "comp": None,
            "last_x": 0.0,
            "last_y": 0.0,
        }
        self._contador_instancias: dict[str, int] = {}
        self._siguiente_canal_analogico: int = 32

        self._opciones_pines: dict[str, int] = _construir_opciones_pines_io()
        self._etiqueta_por_adm: dict[int, str] = {
            v: k for k, v in self._opciones_pines.items()
        }

        self._pin_paleta_var = tk.StringVar(value="P1.0")
        self._color_led_var = tk.StringVar(value="rojo")
        self._fila_proto_var = tk.StringVar(value="c")
        self._col_proto_var = tk.StringVar(value="Auto")

        self._hover_var = tk.StringVar(
            value="Listo. Seleccione un componente en la paleta derecha o haga clic en un componente de la protoboard."
        )
        self._ipc_status_var = tk.StringVar(value="IPC ADM: Conectado (50 ms)")

        self._port_hex_vars: list[tk.StringVar] = [tk.StringVar(value="0xFF") for _ in range(4)]
        self._port_bin_vars: list[tk.StringVar] = [tk.StringVar(value="1111 1111") for _ in range(4)]
        self._port_dir_vars: list[tk.StringVar] = [tk.StringVar(value="IN:8 OUT:0") for _ in range(4)]

        self._insp_titulo_var = tk.StringVar(value="Ningún componente seleccionado")
        self._insp_tipo_var = tk.StringVar(value="—")
        self._insp_pin_combo_var = tk.StringVar(value="P1.0")
        self._insp_sentido_var = tk.StringVar(value="—")
        self._insp_voltaje_var = tk.StringVar(value="0.00 V")
        self._insp_estado_var = tk.StringVar(value="—")
        self._insp_detalle_1_lbl = tk.StringVar(value="Magnitud:")
        self._insp_detalle_1_val = tk.StringVar(value="—")
        self._insp_detalle_2_lbl = tk.StringVar(value="Parámetro:")
        self._insp_detalle_2_val = tk.StringVar(value="—")

        self._configurar_ventana()
        self._construir_interfaz()
        self._cargar_demo_actuadores_p1()
        self._iniciar_sondeo_adm()

    def _configurar_ventana(self) -> None:
        self.root.title("Laboratorio Virtual AT89S51 — Simulador Estilo Tinkercad (ADM IPC)")
        self.root.configure(bg=self.BG_APP)
        self.root.minsize(1340, 780)
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _construir_interfaz(self) -> None:
        header = tk.Frame(self.root, bg=self.BG_CARD, padx=14, pady=8)
        header.pack(fill=tk.X, padx=10, pady=(10, 6))

        tk.Label(
            header,
            text="ATMEL / MICROCHIP AT89S51 — LABORATORIO ELECTRÓNICO VIRTUAL",
            font=("Consolas", 13, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            textvariable=self._ipc_status_var,
            font=("Consolas", 10, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_CARD,
        ).pack(side=tk.RIGHT)

        contenedor = tk.Frame(self.root, bg=self.BG_APP)
        contenedor.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self._construir_zona_izquierda(contenedor)
        self._construir_zona_centro(contenedor)
        self._construir_zona_derecha(contenedor)

        footer = tk.Frame(self.root, bg=self.BG_CARD, padx=12, pady=5)
        footer.pack(fill=tk.X, padx=10, pady=(2, 8))
        tk.Label(
            footer,
            textvariable=self._hover_var,
            font=("Consolas", 9),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W)

    def _construir_zona_izquierda(self, parent: tk.Frame) -> None:
        panel_izq = tk.Frame(parent, bg=self.BG_CARD, padx=10, pady=10, width=365)
        panel_izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        panel_izq.pack_propagate(False)

        tk.Label(
            panel_izq,
            text="1. MICROCONTROLADOR AT89S51 (DIP-40)",
            font=("Consolas", 10, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(0, 6))

        self.canvas_dip = tk.Canvas(
            panel_izq,
            width=342,
            height=450,
            bg=self.BG_PANEL_INNER,
            highlightthickness=1,
            highlightbackground=self.CHIP_BORDER,
        )
        self.canvas_dip.pack()
        self._dibujar_encapsulado_dip40()

        reset_frame = tk.Frame(panel_izq, bg=self.BG_CARD, pady=6)
        reset_frame.pack(fill=tk.X)

        btn_reset = tk.Button(
            reset_frame,
            text="RESET HARDWARE (PIN 9 RST)",
            font=("Consolas", 10, "bold"),
            bg="#DC2626",
            fg="#FFFFFF",
            activebackground="#991B1B",
            activeforeground="#FFFFFF",
            cursor="hand2",
            pady=5,
        )
        btn_reset.pack(fill=tk.X)
        btn_reset.bind("<ButtonPress-1>", lambda _e: self._iniciar_reset_hardware())
        btn_reset.bind("<ButtonRelease-1>", lambda _e: self._finalizar_reset_hardware())

        tk.Label(
            panel_izq,
            text="MONITOR DE REGISTROS DE PUERTO (ADM)",
            font=("Consolas", 9, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(4, 4))

        grid_ports = tk.Frame(panel_izq, bg=self.BG_CARD)
        grid_ports.pack(fill=tk.BOTH, expand=True)

        titulos_puertos = ["P0 (0x80)", "P1 (0x90)", "P2 (0xA0)", "P3 (0xB0)"]
        for idx, titulo in enumerate(titulos_puertos):
            fila_g = idx // 2
            col_g = idx % 2
            celda = tk.Frame(
                grid_ports,
                bg=self.BG_PANEL_INNER,
                padx=8,
                pady=5,
                highlightthickness=1,
                highlightbackground=self.CHIP_BORDER,
            )
            celda.grid(
                row=fila_g,
                column=col_g,
                sticky="nsew",
                padx=(0 if col_g == 0 else 4, 0),
                pady=(0 if fila_g == 0 else 4, 0),
            )
            grid_ports.columnconfigure(col_g, weight=1)
            grid_ports.rowconfigure(fila_g, weight=1)

            top_p = tk.Frame(celda, bg=self.BG_PANEL_INNER)
            top_p.pack(fill=tk.X)
            tk.Label(
                top_p,
                text=titulo,
                font=("Consolas", 9, "bold"),
                fg=self.ACCENT_CYAN,
                bg=self.BG_PANEL_INNER,
            ).pack(side=tk.LEFT)
            tk.Label(
                top_p,
                textvariable=self._port_hex_vars[idx],
                font=("Consolas", 11, "bold"),
                fg=self.COLOR_PIN_ALTO,
                bg=self.BG_PANEL_INNER,
            ).pack(side=tk.RIGHT)

            tk.Label(
                celda,
                textvariable=self._port_bin_vars[idx],
                font=("Consolas", 9),
                fg=self.TEXT_PRIMARY,
                bg=self.BG_PANEL_INNER,
            ).pack(anchor=tk.W)

            tk.Label(
                celda,
                textvariable=self._port_dir_vars[idx],
                font=("Consolas", 8),
                fg=self.TEXT_MUTED,
                bg=self.BG_PANEL_INNER,
            ).pack(anchor=tk.W)

    def _dibujar_encapsulado_dip40(self) -> None:
        c = self.canvas_dip
        c.delete("all")
        self._pin_indicators.clear()
        self._pin_meta.clear()

        chip_x1, chip_y1 = 116, 16
        chip_x2, chip_y2 = 226, 434
        cx_mid = (chip_x1 + chip_x2) // 2

        c.create_rectangle(
            chip_x1 - 18,
            chip_y1 - 6,
            chip_x2 + 18,
            chip_y2 + 6,
            outline="#1E3A5F",
            dash=(3, 2),
            width=1,
        )

        c.create_rectangle(
            chip_x1,
            chip_y1,
            chip_x2,
            chip_y2,
            fill=self.CHIP_BODY,
            outline=self.CHIP_BORDER,
            width=2,
        )

        c.create_arc(
            cx_mid - 16,
            chip_y1 - 12,
            cx_mid + 16,
            chip_y1 + 12,
            start=180,
            extent=180,
            fill=self.BG_PANEL_INNER,
            outline=self.CHIP_BORDER,
            width=2,
        )

        c.create_oval(
            chip_x1 + 9,
            chip_y1 + 10,
            chip_x1 + 17,
            chip_y1 + 18,
            fill="#334155",
            outline="#64748B",
        )

        c.create_text(cx_mid, 180, text="ATMEL", fill="#CBD5E1", font=("Consolas", 12, "bold"))
        c.create_text(cx_mid, 202, text="AT89S51", fill="#F8FAFC", font=("Consolas", 11, "bold"))
        c.create_text(cx_mid, 222, text="24PU 8051", fill="#94A3B8", font=("Consolas", 8))
        c.create_text(cx_mid, 240, text="4KB ROM", fill="#64748B", font=("Consolas", 7))

        y_inicio = 32.0
        paso_y = 20.4

        for idx in range(20):
            y = y_inicio + idx * paso_y
            self._dibujar_pin_dip(PINES_IZQUIERDA[idx], chip_x1, y, es_izquierda=True)
            self._dibujar_pin_dip(PINES_DERECHA_TOP_DOWN[idx], chip_x2, y, es_izquierda=False)

    def _dibujar_pin_dip(
        self,
        pin: PinDIP40,
        chip_edge_x: int,
        y: float,
        es_izquierda: bool,
    ) -> None:
        c = self.canvas_dip
        largo_pata = 16
        alto_pata = 9
        radio_led = 4.5

        if es_izquierda:
            pata_x1 = chip_edge_x - largo_pata
            pata_x2 = chip_edge_x
            num_x = chip_edge_x + 12
            led_cx = pata_x1 - 9
            label_x = led_cx - 9
            anchor_label = tk.E
        else:
            pata_x1 = chip_edge_x
            pata_x2 = chip_edge_x + largo_pata
            num_x = chip_edge_x - 12
            led_cx = pata_x2 + 9
            label_x = led_cx + 9
            anchor_label = tk.W

        c.create_rectangle(
            pata_x1,
            y - alto_pata / 2,
            pata_x2,
            y + alto_pata / 2,
            fill=self.PIN_METAL,
            outline="#64748B",
            width=1,
        )

        c.create_text(
            num_x,
            y,
            text=str(pin.numero_dip),
            fill="#94A3B8",
            font=("Consolas", 7, "bold"),
        )

        tag_pin = f"dip_pin_{pin.numero_dip}"
        oval_id = c.create_oval(
            led_cx - radio_led,
            y - radio_led,
            led_cx + radio_led,
            y + radio_led,
            fill=self._color_por_defecto_pin(pin),
            outline="#0F172A",
            width=1,
            tags=(tag_pin,),
        )

        color_texto = (
            self.ACCENT_CYAN
            if pin.tipo == "io"
            else ("#FCA5A5" if pin.tipo in ("vcc", "rst") else "#94A3B8")
        )
        text_id = c.create_text(
            label_x,
            y,
            text=pin.etiqueta,
            fill=color_texto,
            font=("Consolas", 8, "bold" if pin.tipo == "io" else "normal"),
            anchor=anchor_label,
            tags=(tag_pin,),
        )

        self._pin_indicators[pin.numero_dip] = oval_id
        self._pin_meta[pin.numero_dip] = pin

        for item_id in (oval_id, text_id):
            c.tag_bind(item_id, "<Enter>", lambda _e, p=pin: self._mostrar_info_pin_dip(p))
            if pin.adm_canal is not None:
                c.tag_bind(
                    item_id,
                    "<Button-1>",
                    lambda _e, ch=pin.adm_canal: self._seleccionar_pin_desde_dip(ch),
                )

    def _color_por_defecto_pin(self, pin: PinDIP40) -> str:
        if pin.tipo == "vcc":
            return self.COLOR_PIN_VCC
        if pin.tipo == "gnd":
            return self.COLOR_PIN_GND
        if pin.tipo == "rst":
            return self.COLOR_PIN_VCC if self._reset_activo else self.COLOR_PIN_BAJO
        if pin.tipo == "xtal":
            return self.COLOR_PIN_XTAL if self._xtal_toggle else "#78350F"
        if pin.tipo == "ctrl":
            return self.COLOR_PIN_ALTO if pin.numero_dip == 31 else self.COLOR_PIN_BAJO
        return self.COLOR_PIN_ALTO

    def _mostrar_info_pin_dip(self, pin: PinDIP40) -> None:
        if pin.adm_canal is None:
            self._hover_var.set(
                f"Pin DIP #{pin.numero_dip:02d} [{pin.etiqueta}] — Pin hardware de alimentación/control."
            )
            return

        voltaje = self.adm.puertos[pin.adm_canal]
        sentido = self.adm.sentidos[pin.adm_canal]
        nivel = 1 if voltaje >= ADM.UMBRAL_LOGICO else 0
        modo_str = "SALIDA (0V activo)" if sentido == ADM.MODO_ESCRITURA else "ENTRADA / Pull-up"
        self._hover_var.set(
            f"Pin DIP #{pin.numero_dip:02d} [{pin.etiqueta}] | ADM #{pin.adm_canal:02d} | "
            f"Nivel: {nivel} ({voltaje:.2f} V) | {modo_str} (Clic para seleccionar en paleta)"
        )

    def _seleccionar_pin_desde_dip(self, canal_adm: int) -> None:
        etiqueta = self._etiqueta_por_adm.get(canal_adm)
        if etiqueta is not None:
            self._pin_paleta_var.set(etiqueta)
            self._hover_var.set(f"Pin destino seleccionado en paleta: {etiqueta}")

    def _construir_zona_centro(self, parent: tk.Frame) -> None:
        panel_centro = tk.Frame(parent, bg=self.BG_APP)
        panel_centro.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        card_proto = tk.Frame(panel_centro, bg=self.BG_CARD, padx=10, pady=8)
        card_proto.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        barra_proto = tk.Frame(card_proto, bg=self.BG_CARD)
        barra_proto.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            barra_proto,
            text="2. MESA DE TRABAJO — PROTOBOARD Y CABLEADO VIRTUAL (TINKERCAD)",
            font=("Consolas", 10, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT)

        tk.Label(
            barra_proto,
            text="Clic: inspeccionar | Arrastrar cuerpo: mover componente",
            font=("Consolas", 8),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
        ).pack(side=tk.RIGHT)

        self.canvas_protoboard = tk.Canvas(
            card_proto,
            width=680,
            height=435,
            bg=self.BG_WORKBENCH,
            highlightthickness=1,
            highlightbackground=self.CHIP_BORDER,
        )
        self.canvas_protoboard.pack(fill=tk.BOTH, expand=True)

        self.protoboard = Protoboard(x=136.0, y=28.0, columnas=30, espaciado=16.5)
        self.protoboard.dibujar(self.canvas_protoboard)
        self._dibujar_bus_pines_8051_en_mesa()

        self.canvas_protoboard.bind("<ButtonPress-1>", self._al_clic_canvas_protoboard)
        self.canvas_protoboard.bind("<B1-Motion>", self._al_arrastrar_canvas_protoboard)
        self.canvas_protoboard.bind("<ButtonRelease-1>", self._al_soltar_canvas_protoboard)

        self._construir_panel_inspector_propiedades(panel_centro)

    def _dibujar_bus_pines_8051_en_mesa(self) -> None:
        c = self.canvas_protoboard
        c.delete("bus_8051")
        self._bus_sockets_leds.clear()

        c.create_rectangle(
            8, 12, 114, 422,
            fill="#1E293B", outline="#475569", width=1.5, tags=("bus_8051",),
        )
        c.create_text(
            61, 22, text="BUS AT89S51", fill=self.ACCENT_CYAN,
            font=("Consolas", 8, "bold"), tags=("bus_8051",),
        )

        grupo_izq: list[tuple[str, int | None, str]] = (
            [(f"P1.{b}", 8 + b, "digital") for b in range(8)]
            + [(f"P3.{b}", 24 + b, "digital") for b in range(8)]
            + [("VCC", None, "vcc"), ("GND", None, "gnd")]
        )
        grupo_der: list[tuple[str, int | None, str]] = (
            [(f"P2.{b}", 16 + b, "digital") for b in range(8)]
            + [(f"P0.{b}", b, "digital") for b in range(8)]
            + [("AN0", 32, "analog"), ("AN1", 33, "analog")]
        )

        y_ini = 38.0
        paso_y = 21.0

        for idx, (etiqueta, canal, tipo) in enumerate(grupo_izq):
            y = y_ini + idx * paso_y
            self._dibujar_zocalo_bus(x_socket=44.0, y=y, etiqueta=etiqueta, canal=canal, tipo=tipo)

        for idx, (etiqueta, canal, tipo) in enumerate(grupo_der):
            y = y_ini + idx * paso_y
            self._dibujar_zocalo_bus(x_socket=98.0, y=y, etiqueta=etiqueta, canal=canal, tipo=tipo)

        for an_idx in range(2, 8):
            self.protoboard.registrar_punto_pin_8051(f"AN{an_idx}", 98.0, y_ini + 17 * paso_y)

    def _dibujar_zocalo_bus(
        self,
        x_socket: float,
        y: float,
        etiqueta: str,
        canal: int | None,
        tipo: str,
    ) -> None:
        c = self.canvas_protoboard
        color_ini = (
            self.COLOR_PIN_VCC
            if tipo == "vcc"
            else (self.COLOR_PIN_GND if tipo == "gnd" else self.COLOR_PIN_ALTO)
        )

        c.create_text(
            x_socket - 8.0,
            y,
            text=etiqueta,
            fill="#E2E8F0",
            font=("Consolas", 7, "bold"),
            anchor=tk.E,
            tags=("bus_8051",),
        )
        socket_id = c.create_rectangle(
            x_socket - 4.0,
            y - 4.0,
            x_socket + 4.0,
            y + 4.0,
            fill=color_ini,
            outline="#F8FAFC",
            width=1,
            tags=("bus_8051",),
        )
        self._bus_sockets_leds[etiqueta] = socket_id
        self.protoboard.registrar_punto_pin_8051(etiqueta, x_socket, y)

    def _construir_panel_inspector_propiedades(self, parent: tk.Frame) -> None:
        card_insp = tk.Frame(parent, bg=self.BG_CARD, padx=12, pady=8)
        card_insp.pack(fill=tk.X)

        barra_top = tk.Frame(card_insp, bg=self.BG_CARD)
        barra_top.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            barra_top,
            text="INSPECTOR DE PROPIEDADES EN TIEMPO REAL:",
            font=("Consolas", 10, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT)

        tk.Label(
            barra_top,
            textvariable=self._insp_titulo_var,
            font=("Consolas", 10, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(
            barra_top,
            text="Eliminar Componente",
            font=("Consolas", 8, "bold"),
            bg="#991B1B",
            fg="#FFFFFF",
            activebackground="#7F1D1D",
            activeforeground="#FFFFFF",
            padx=8,
            pady=1,
            cursor="hand2",
            command=self._eliminar_componente_seleccionado,
        ).pack(side=tk.RIGHT)

        grid_props = tk.Frame(
            card_insp,
            bg=self.BG_PANEL_INNER,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=self.CHIP_BORDER,
        )
        grid_props.pack(fill=tk.X)

        for col_i in range(4):
            grid_props.columnconfigure(col_i, weight=1)

        self._crear_celda_inspector(grid_props, 0, 0, "Clase:", self._insp_tipo_var)

        celda_pin = tk.Frame(grid_props, bg=self.BG_PANEL_INNER)
        celda_pin.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        tk.Label(
            celda_pin, text="Pin 8051:", font=("Consolas", 8), fg=self.TEXT_MUTED, bg=self.BG_PANEL_INNER
        ).pack(side=tk.LEFT)
        self._combo_insp_pin = ttk.Combobox(
            celda_pin,
            textvariable=self._insp_pin_combo_var,
            values=list(self._opciones_pines.keys()),
            state="readonly",
            width=13,
            font=("Consolas", 8),
        )
        self._combo_insp_pin.pack(side=tk.LEFT, padx=(4, 0))
        self._combo_insp_pin.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._reasignar_pin_componente_seleccionado(),
        )

        self._crear_celda_inspector(grid_props, 0, 2, "Sentido E/S:", self._insp_sentido_var)
        self._crear_celda_inspector(
            grid_props, 0, 3, "Voltaje:", self._insp_voltaje_var, color_val=self.COLOR_PIN_ALTO
        )

        self._crear_celda_inspector(
            grid_props, 1, 0, "Estado Lógico:", self._insp_estado_var, color_val=self.ACCENT_CYAN
        )

        celda_d1 = tk.Frame(grid_props, bg=self.BG_PANEL_INNER)
        celda_d1.grid(row=1, column=1, columnspan=2, sticky="w", padx=4, pady=2)
        tk.Label(
            celda_d1,
            textvariable=self._insp_detalle_1_lbl,
            font=("Consolas", 8),
            fg=self.TEXT_MUTED,
            bg=self.BG_PANEL_INNER,
        ).pack(side=tk.LEFT)
        tk.Label(
            celda_d1,
            textvariable=self._insp_detalle_1_val,
            font=("Consolas", 9, "bold"),
            fg="#FBBF24",
            bg=self.BG_PANEL_INNER,
        ).pack(side=tk.LEFT, padx=(4, 0))

        celda_d2 = tk.Frame(grid_props, bg=self.BG_PANEL_INNER)
        celda_d2.grid(row=1, column=3, sticky="w", padx=4, pady=2)
        tk.Label(
            celda_d2,
            textvariable=self._insp_detalle_2_lbl,
            font=("Consolas", 8),
            fg=self.TEXT_MUTED,
            bg=self.BG_PANEL_INNER,
        ).pack(side=tk.LEFT)
        tk.Label(
            celda_d2,
            textvariable=self._insp_detalle_2_val,
            font=("Consolas", 9, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_PANEL_INNER,
        ).pack(side=tk.LEFT, padx=(4, 0))

    def _crear_celda_inspector(
        self,
        parent: tk.Frame,
        row: int,
        col: int,
        etiqueta: str,
        var_valor: tk.StringVar,
        color_val: str = "#F8FAFC",
    ) -> None:
        celda = tk.Frame(parent, bg=self.BG_PANEL_INNER)
        celda.grid(row=row, column=col, sticky="w", padx=4, pady=2)
        tk.Label(
            celda, text=etiqueta, font=("Consolas", 8), fg=self.TEXT_MUTED, bg=self.BG_PANEL_INNER
        ).pack(side=tk.LEFT)
        tk.Label(
            celda,
            textvariable=var_valor,
            font=("Consolas", 9, "bold"),
            fg=color_val,
            bg=self.BG_PANEL_INNER,
        ).pack(side=tk.LEFT, padx=(4, 0))

    def _construir_zona_derecha(self, parent: tk.Frame) -> None:
        panel_der = tk.Frame(parent, bg=self.BG_CARD, padx=10, pady=10, width=305)
        panel_der.pack(side=tk.LEFT, fill=tk.Y)
        panel_der.pack_propagate(False)

        tk.Label(
            panel_der,
            text="3. PALETA DE COMPONENTES",
            font=("Consolas", 10, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(0, 6))

        cfg_box = tk.Frame(
            panel_der,
            bg=self.BG_PANEL_INNER,
            padx=8,
            pady=8,
            highlightthickness=1,
            highlightbackground=self.CHIP_BORDER,
        )
        cfg_box.pack(fill=tk.X, pady=(0, 8))

        fila_pin = tk.Frame(cfg_box, bg=self.BG_PANEL_INNER)
        fila_pin.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            fila_pin,
            text="Pin AT89S51:",
            font=("Consolas", 9, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_PANEL_INNER,
        ).pack(side=tk.LEFT)

        ttk.Combobox(
            fila_pin,
            textvariable=self._pin_paleta_var,
            values=list(self._opciones_pines.keys()),
            state="readonly",
            width=15,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        fila_pos = tk.Frame(cfg_box, bg=self.BG_PANEL_INNER)
        fila_pos.pack(fill=tk.X, pady=(2, 0))

        tk.Label(
            fila_pos, text="Fila:", font=("Consolas", 8), fg=self.TEXT_MUTED, bg=self.BG_PANEL_INNER
        ).pack(side=tk.LEFT)
        ttk.Combobox(
            fila_pos,
            textvariable=self._fila_proto_var,
            values=list(FILAS_BLOQUE_SUPERIOR + FILAS_BLOQUE_INFERIOR),
            state="readonly",
            width=3,
            font=("Consolas", 8),
        ).pack(side=tk.LEFT, padx=(2, 6))

        tk.Label(
            fila_pos, text="Col:", font=("Consolas", 8), fg=self.TEXT_MUTED, bg=self.BG_PANEL_INNER
        ).pack(side=tk.LEFT)
        columnas_opts = ["Auto"] + [str(c) for c in range(1, 31)]
        ttk.Combobox(
            fila_pos,
            textvariable=self._col_proto_var,
            values=columnas_opts,
            state="readonly",
            width=5,
            font=("Consolas", 8),
        ).pack(side=tk.LEFT, padx=(2, 6))

        tk.Label(
            fila_pos, text="LED:", font=("Consolas", 8), fg=self.TEXT_MUTED, bg=self.BG_PANEL_INNER
        ).pack(side=tk.LEFT)
        ttk.Combobox(
            fila_pos,
            textvariable=self._color_led_var,
            values=["rojo", "verde", "azul", "amarillo", "naranja", "blanco"],
            state="readonly",
            width=7,
            font=("Consolas", 8),
        ).pack(side=tk.LEFT, padx=(2, 0))

        tk.Label(
            panel_der,
            text="ACTUADORES DE SALIDA (5)",
            font=("Consolas", 9, "bold"),
            fg="#34D399",
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(2, 3))

        for nombre_comp in CATALOGO_ACTUADORES:
            self._crear_boton_paleta(panel_der, nombre_comp, bg_btn="#1E3A5F")

        tk.Label(
            panel_der,
            text="SENSORES Y ENTRADAS (5)",
            font=("Consolas", 9, "bold"),
            fg="#FBBF24",
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(8, 3))

        for nombre_comp in CATALOGO_SENSORES:
            self._crear_boton_paleta(panel_der, nombre_comp, bg_btn="#3B2F1E")

        tk.Label(
            panel_der,
            text="CIRCUITOS DEMOSTRACIÓN (1 CLIC)",
            font=("Consolas", 9, "bold"),
            fg=self.ACCENT_CYAN,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(10, 4))

        demos = [
            ("Demo 1: Actuadores en P1", self._cargar_demo_actuadores_p1, "#0F766E"),
            ("Demo 2: Botón P3.2 -> LED P1.0", self._cargar_demo_boton_a_led, "#1D4ED8"),
            ("Demo 3: Sensores + Display 7-Seg", self._cargar_demo_sensores_y_display, "#6D28D9"),
        ]
        for texto_demo, callback_demo, color_demo in demos:
            tk.Button(
                panel_der,
                text=texto_demo,
                font=("Consolas", 8, "bold"),
                bg=color_demo,
                fg="#FFFFFF",
                activebackground="#0F172A",
                activeforeground="#FFFFFF",
                anchor=tk.W,
                padx=8,
                pady=4,
                cursor="hand2",
                command=callback_demo,
            ).pack(fill=tk.X, pady=2)

        tk.Button(
            panel_der,
            text="Limpiar Protoboard",
            font=("Consolas", 8, "bold"),
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#475569",
            activeforeground="#FFFFFF",
            pady=4,
            cursor="hand2",
            command=self._limpiar_protoboard,
        ).pack(fill=tk.X, pady=(6, 0))

    def _crear_boton_paleta(self, parent: tk.Frame, nombre_comp: str, bg_btn: str) -> None:
        tk.Button(
            parent,
            text=f"+ {nombre_comp}",
            font=("Consolas", 8, "bold"),
            bg=bg_btn,
            fg="#F8FAFC",
            activebackground="#0284C7",
            activeforeground="#FFFFFF",
            anchor=tk.W,
            padx=8,
            pady=3,
            cursor="hand2",
            command=lambda n=nombre_comp: self.agregar_componente_desde_paleta(n),
        ).pack(fill=tk.X, pady=1.5)

    def _siguiente_nombre_unico(self, prefijo: str) -> str:
        cuenta = self._contador_instancias.get(prefijo, 0) + 1
        self._contador_instancias[prefijo] = cuenta
        return f"{prefijo} #{cuenta}"

    def _asignar_canal_analogico_libre(self) -> int:
        canal = self._siguiente_canal_analogico
        self._siguiente_canal_analogico += 1
        if self._siguiente_canal_analogico >= ADM.TOTAL_CANALES:
            self._siguiente_canal_analogico = ADM.TOTAL_PINES_DIGITALES
        return canal

    def _instanciar_componente_por_tipo(
        self,
        nombre_catalogo: str,
        pin_adm: int,
    ) -> ComponenteElectronico:
        if nombre_catalogo == "LED con Resistencia":
            return LedComponente(
                nombre=self._siguiente_nombre_unico("LED"),
                pin=pin_adm,
                color=self._color_led_var.get(),
            )
        if nombre_catalogo == "Motor DC":
            return MotorDCComponente(
                nombre=self._siguiente_nombre_unico("Motor DC"),
                pin=pin_adm,
            )
        if nombre_catalogo == "Servomotor (0°-180°)":
            return ServomotorComponente(
                nombre=self._siguiente_nombre_unico("Servo"),
                pin=pin_adm,
            )
        if nombre_catalogo == "Buzzer Piezoeléctrico":
            return BuzzerComponente(
                nombre=self._siguiente_nombre_unico("Buzzer"),
                pin=pin_adm,
            )
        if nombre_catalogo == "Display 7 Segmentos":
            puerto_8bit = pin_adm // 8 if 0 <= pin_adm < 32 else 1
            return Display7SegmentosComponente(
                nombre=self._siguiente_nombre_unico("7-Seg"),
                puerto=puerto_8bit,
            )
        if nombre_catalogo == "Pulsador Táctil":
            return PulsadorComponente(
                nombre=self._siguiente_nombre_unico("Pulsador"),
                pin=pin_adm,
            )
        if nombre_catalogo == "Interruptor DIP":
            return InterruptorDipComponente(
                nombre=self._siguiente_nombre_unico("Switch"),
                pin=pin_adm,
            )
        if nombre_catalogo == "Potenciómetro (0-5V)":
            return PotenciometroComponente(
                nombre=self._siguiente_nombre_unico("Pot"),
                canal=self._asignar_canal_analogico_libre(),
                pin=pin_adm,
            )
        if nombre_catalogo == "Sensor Temperatura (LM35/DHT)":
            return SensorTemperaturaComponente(
                nombre=self._siguiente_nombre_unico("Temp"),
                pin=pin_adm,
                canal=self._asignar_canal_analogico_libre(),
            )
        if nombre_catalogo == "Sensor Ultrasónico (HC-SR04)":
            return SensorUltrasonicoComponente(
                nombre=self._siguiente_nombre_unico("HC-SR04"),
                pin=pin_adm,
                canal=self._asignar_canal_analogico_libre(),
            )

        clase_comp = CATALOGO_COMPONENTES[nombre_catalogo]
        return clase_comp(nombre=self._siguiente_nombre_unico(nombre_catalogo))

    def agregar_componente_desde_paleta(self, nombre_catalogo: str) -> ComponenteElectronico:
        etiqueta_pin = self._pin_paleta_var.get()
        pin_adm = self._opciones_pines.get(etiqueta_pin, 8)

        fila = self._fila_proto_var.get()
        col_str = self._col_proto_var.get()
        columna = None if col_str == "Auto" else int(col_str)

        comp = self._instanciar_componente_por_tipo(nombre_catalogo, pin_adm)
        self.protoboard.montar_componente(
            componente=comp,
            columna=columna,
            fila=fila,
            auto_cablear=True,
            adm=self.adm,
        )
        self.componentes_activos.append(comp)
        self._seleccionar_componente(comp)
        self._actualizar_vista_desde_adm()

        self._hover_var.set(
            f"Componente '{comp.nombre}' montado en protoboard y conectado a {etiqueta_pin}."
        )
        return comp

    def _limpiar_protoboard(self) -> None:
        for comp in list(self.componentes_activos):
            self.protoboard.desmontar_componente(comp, adm=self.adm)
        self.componentes_activos.clear()
        self._contador_instancias.clear()
        self._siguiente_canal_analogico = 32
        self._seleccionar_componente(None)
        self.adm.reset()
        self._actualizar_vista_desde_adm()
        self._hover_var.set("Protoboard limpia y registros de puertos restaurados en ADM.")

    def _cargar_demo_actuadores_p1(self) -> None:
        self._limpiar_protoboard()

        specs: list[tuple[ComponenteElectronico, str, int]] = [
            (LedComponente(nombre="LED #1", pin=8, color="rojo"), "c", 4),
            (LedComponente(nombre="LED #2", pin=9, color="verde"), "c", 9),
            (MotorDCComponente(nombre="Motor DC #1", pin=10), "c", 15),
            (ServomotorComponente(nombre="Servo #1", pin=11), "c", 21),
            (BuzzerComponente(nombre="Buzzer #1", pin=12), "c", 27),
        ]
        for comp, fila, col in specs:
            self.protoboard.montar_componente(
                componente=comp, columna=col, fila=fila, auto_cablear=True, adm=self.adm
            )
            self.componentes_activos.append(comp)

        self._seleccionar_componente(self.componentes_activos[0])
        self._actualizar_vista_desde_adm()
        self._hover_var.set(
            "Demo 1 cargada: Actuadores conectados a P1.0..P1.4 (compatible con blink_p1.hex / binary_counter.hex)."
        )

    def _cargar_demo_boton_a_led(self) -> None:
        self._limpiar_protoboard()

        pulsador = PulsadorComponente(nombre="Pulsador #1", pin=26)
        led = LedComponente(nombre="LED #1", pin=8, color="rojo")

        self.protoboard.montar_componente(
            componente=pulsador, columna=8, fila="d", auto_cablear=True, adm=self.adm
        )
        self.protoboard.montar_componente(
            componente=led, columna=18, fila="d", auto_cablear=True, adm=self.adm
        )
        self.componentes_activos.extend([pulsador, led])

        self._seleccionar_componente(pulsador)
        self._actualizar_vista_desde_adm()
        self._hover_var.set(
            "Demo 2 cargada: Pulsador en P3.2 (INT0) y LED en P1.0 (compatible con button_to_led.hex)."
        )

    def _cargar_demo_sensores_y_display(self) -> None:
        self._limpiar_protoboard()

        display = Display7SegmentosComponente(nombre="7-Seg #1", puerto=1, nibble="low")
        pot = PotenciometroComponente(nombre="Pot #1", canal=32, pin=16)
        temp = SensorTemperaturaComponente(nombre="Temp #1", pin=17, canal=33)
        ultra = SensorUltrasonicoComponente(nombre="HC-SR04 #1", pin=18, canal=34)

        specs: list[tuple[ComponenteElectronico, str, int]] = [
            (display, "d", 5),
            (pot, "d", 12),
            (temp, "d", 19),
            (ultra, "d", 26),
        ]
        for comp, fila, col in specs:
            self.protoboard.montar_componente(
                componente=comp, columna=col, fila=fila, auto_cablear=True, adm=self.adm
            )
            self.componentes_activos.append(comp)

        self._seleccionar_componente(pot)
        self._actualizar_vista_desde_adm()
        self._hover_var.set(
            "Demo 3 cargada: Display 7-Seg en P1 y Potenciómetro/Temperatura/Ultrasónico en P2.0..P2.2."
        )

    def _buscar_componente_en_coordenada(
        self, x: float, y: float
    ) -> ComponenteElectronico | None:
        items = self.canvas_protoboard.find_overlapping(x - 3, y - 3, x + 3, y + 3)
        if not items:
            return None

        mapa_tags = {comp.tag_grupo: comp for comp in self.componentes_activos}
        for item_id in reversed(items):
            tags = self.canvas_protoboard.gettags(item_id)
            for tag in tags:
                if tag in mapa_tags:
                    return mapa_tags[tag]
        return None

    def _al_clic_canvas_protoboard(self, event: tk.Event[tk.Misc]) -> None:
        comp = self._buscar_componente_en_coordenada(float(event.x), float(event.y))
        self._seleccionar_componente(comp)
        if comp is not None and not bool(comp.propiedades.get("interactuando", False)):
            self._arrastre_activo["comp"] = comp
            self._arrastre_activo["last_x"] = float(event.x)
            self._arrastre_activo["last_y"] = float(event.y)

    def _al_arrastrar_canvas_protoboard(self, event: tk.Event[tk.Misc]) -> None:
        comp: ComponenteElectronico | None = self._arrastre_activo["comp"]
        if comp is None or bool(comp.propiedades.get("interactuando", False)):
            return

        dx = float(event.x) - float(self._arrastre_activo["last_x"])
        dy = float(event.y) - float(self._arrastre_activo["last_y"])
        self._arrastre_activo["last_x"] = float(event.x)
        self._arrastre_activo["last_y"] = float(event.y)

        comp.mover(dx, dy)
        coords_term = comp.obtener_puntos_conexion()
        for cable in self.protoboard.cables.values():
            if cable.destino_componente is comp and cable.destino_terminal in coords_term:
                cable.actualizar_extremos(punto_destino=coords_term[cable.destino_terminal])

        self._dibujar_marco_seleccion()

    def _al_soltar_canvas_protoboard(self, _event: tk.Event[tk.Misc]) -> None:
        self._arrastre_activo["comp"] = None
        self._dibujar_marco_seleccion()

    def _seleccionar_componente(self, comp: ComponenteElectronico | None) -> None:
        self._componente_seleccionado = comp
        self._dibujar_marco_seleccion()
        self._refrescar_inspector_propiedades()

    def _dibujar_marco_seleccion(self) -> None:
        if self._id_marco_seleccion is not None:
            self.canvas_protoboard.delete(self._id_marco_seleccion)
            self._id_marco_seleccion = None

        comp = self._componente_seleccionado
        if comp is None:
            return

        bbox = comp.obtener_bbox()
        if bbox is not None:
            self._id_marco_seleccion = self.canvas_protoboard.create_rectangle(
                bbox[0] - 5,
                bbox[1] - 5,
                bbox[2] + 5,
                bbox[3] + 5,
                outline=self.ACCENT_CYAN,
                dash=(4, 2),
                width=1.5,
            )

    def _reasignar_pin_componente_seleccionado(self) -> None:
        comp = self._componente_seleccionado
        if comp is None:
            return

        etiqueta_nueva = self._insp_pin_combo_var.get()
        pin_nuevo = self._opciones_pines.get(etiqueta_nueva)
        if pin_nuevo is None:
            return

        if isinstance(comp, Display7SegmentosComponente):
            puerto_8bit = pin_nuevo // 8
            self.protoboard.conectar_componente(
                componente=comp,
                destino_adm=puerto_8bit * 8,
                terminal="PUERTO",
                adm=self.adm,
            )
        elif isinstance(comp, PotenciometroComponente):
            self.protoboard.conectar_componente(
                componente=comp,
                destino_adm=pin_nuevo,
                terminal="OUT",
                adm=self.adm,
            )
        else:
            self.protoboard.conectar_componente(
                componente=comp,
                destino_adm=pin_nuevo,
                adm=self.adm,
            )

        self._actualizar_vista_desde_adm()
        self._hover_var.set(f"'{comp.nombre}' reconectado dinámicamente a {etiqueta_nueva}.")

    def _eliminar_componente_seleccionado(self) -> None:
        comp = self._componente_seleccionado
        if comp is None:
            return

        self.protoboard.desmontar_componente(comp, adm=self.adm)
        if comp in self.componentes_activos:
            self.componentes_activos.remove(comp)

        siguiente = self.componentes_activos[-1] if self.componentes_activos else None
        self._seleccionar_componente(siguiente)
        self._actualizar_vista_desde_adm()

    def _refrescar_inspector_propiedades(self) -> None:
        comp = self._componente_seleccionado
        if comp is None:
            self._insp_titulo_var.set("Ningún componente seleccionado")
            self._insp_tipo_var.set("—")
            self._insp_sentido_var.set("—")
            self._insp_voltaje_var.set("0.00 V")
            self._insp_estado_var.set("—")
            self._insp_detalle_1_lbl.set("Magnitud:")
            self._insp_detalle_1_val.set("—")
            self._insp_detalle_2_lbl.set("Parámetro:")
            self._insp_detalle_2_val.set("—")
            return

        self._insp_titulo_var.set(comp.nombre)
        self._insp_tipo_var.set(type(comp).__name__)

        if isinstance(comp, Display7SegmentosComponente):
            puerto = int(comp.propiedades.get("puerto", 1))
            pin_ref = puerto * 8
        else:
            pin_ref = int(comp.propiedades.get("pin", 8))

        if 0 <= pin_ref < ADM.TOTAL_CANALES:
            etiqueta_combo = self._etiqueta_por_adm.get(pin_ref)
            if etiqueta_combo is not None and self._insp_pin_combo_var.get() != etiqueta_combo:
                self._insp_pin_combo_var.set(etiqueta_combo)

            sentido = self.adm.sentidos[pin_ref]
            self._insp_sentido_var.set(
                "SALIDA (1)" if sentido == ADM.MODO_ESCRITURA else "ENTRADA / Pull-up (0)"
            )
            voltaje = float(comp.propiedades.get("voltaje", self.adm.puertos[pin_ref]))
            self._insp_voltaje_var.set(f"{voltaje:.2f} V")
            nivel = 1 if voltaje >= ADM.UMBRAL_LOGICO else 0
            self._insp_estado_var.set(f"{nivel} ({'ALTO' if nivel == 1 else 'BAJO'})")

        if isinstance(comp, LedComponente):
            enc = bool(comp.propiedades.get("encendido", False))
            self._insp_detalle_1_lbl.set("Estado LED:")
            self._insp_detalle_1_val.set("ENCENDIDO" if enc else "APAGADO")
            self._insp_detalle_2_lbl.set("Color / R:")
            self._insp_detalle_2_val.set(
                f"{str(comp.propiedades.get('color', 'rojo')).upper()} / {comp.propiedades.get('resistencia_ohms', 220)}Ω"
            )
        elif isinstance(comp, MotorDCComponente):
            act = bool(comp.propiedades.get("activo", False))
            ang = float(comp.propiedades.get("angulo", 0.0))
            rpm = int(round((float(comp.propiedades.get("voltaje", 0.0)) / 5.0) * 3000)) if act else 0
            self._insp_detalle_1_lbl.set("Rotor / RPM:")
            self._insp_detalle_1_val.set(f"{'GIRANDO' if act else 'DETENIDO'} ({rpm} RPM)")
            self._insp_detalle_2_lbl.set("Ángulo Eje:")
            self._insp_detalle_2_val.set(f"{int(round(ang))}°")
        elif isinstance(comp, ServomotorComponente):
            ang = float(comp.propiedades.get("angulo", 0.0))
            obj = float(comp.propiedades.get("angulo_objetivo", 0.0))
            self._insp_detalle_1_lbl.set("Ángulo Brazo:")
            self._insp_detalle_1_val.set(f"{ang:.1f}° (Obj: {obj:.0f}°)")
            self._insp_detalle_2_lbl.set("Rango:")
            self._insp_detalle_2_val.set("0° - 180°")
        elif isinstance(comp, BuzzerComponente):
            act = bool(comp.propiedades.get("activo", False))
            freq = int(comp.propiedades.get("frecuencia_hz", 2400))
            self._insp_detalle_1_lbl.set("Emisión Acústica:")
            self._insp_detalle_1_val.set("ACTIVA (ON)" if act else "SILENCIO")
            self._insp_detalle_2_lbl.set("Frecuencia:")
            self._insp_detalle_2_val.set(f"{freq} Hz")
        elif isinstance(comp, Display7SegmentosComponente):
            val_b = int(comp.propiedades.get("valor_byte", 0))
            puerto = int(comp.propiedades.get("puerto", 1))
            segs = comp.propiedades.get("segmentos", {})
            activos = "".join(k for k, v in segs.items() if v) or "ninguno"
            self._insp_estado_var.set(f"P{puerto} = 0x{val_b:02X}")
            self._insp_detalle_1_lbl.set("Segmentos ON:")
            self._insp_detalle_1_val.set(activos)
            self._insp_detalle_2_lbl.set("Modo:")
            self._insp_detalle_2_val.set(f"Nibble {comp.propiedades.get('nibble') or '8-bit'}")
        elif isinstance(comp, PulsadorComponente):
            pres = bool(comp.propiedades.get("presionado", False))
            self._insp_detalle_1_lbl.set("Accionamiento:")
            self._insp_detalle_1_val.set("PRESIONADO (GND)" if pres else "EN REPOSO")
            self._insp_detalle_2_lbl.set("Tipo:")
            self._insp_detalle_2_val.set("Momentáneo 4-pin")
        elif isinstance(comp, InterruptorDipComponente):
            on = bool(comp.propiedades.get("estado_on", False))
            self._insp_detalle_1_lbl.set("Enclavamiento:")
            self._insp_detalle_1_val.set("ON (LOW activo)" if on else "OFF (Pull-up)")
            self._insp_detalle_2_lbl.set("Tipo:")
            self._insp_detalle_2_val.set("DIP 2 posiciones")
        elif isinstance(comp, PotenciometroComponente):
            pct = float(comp.propiedades.get("porcentaje", 50.0))
            canal = int(comp.propiedades.get("canal", 32))
            self._insp_detalle_1_lbl.set("Posición Cursor:")
            self._insp_detalle_1_val.set(f"{pct:.1f}% ({formatear_canal_adm(canal, 'analog')})")
            self._insp_detalle_2_lbl.set("Salida Dig.:")
            self._insp_detalle_2_val.set(f"Nivel {comp.propiedades.get('nivel_digital', 0)}")
        elif isinstance(comp, SensorTemperaturaComponente):
            temp = float(comp.propiedades.get("temperatura_c", 25.0))
            alerta = bool(comp.propiedades.get("alerta_activa", False))
            umbral = float(comp.propiedades.get("umbral_c", 30.0))
            self._insp_detalle_1_lbl.set("Temperatura:")
            self._insp_detalle_1_val.set(f"{temp:.1f} °C {'[ALERTA]' if alerta else ''}")
            self._insp_detalle_2_lbl.set("Umbral:")
            self._insp_detalle_2_val.set(f">{umbral:.0f} °C")
        elif isinstance(comp, SensorUltrasonicoComponente):
            dist = float(comp.propiedades.get("distancia_cm", 50.0))
            obst = bool(comp.propiedades.get("obstaculo_detectado", False))
            self._insp_detalle_1_lbl.set("Distancia:")
            self._insp_detalle_1_val.set(f"{dist:.1f} cm {'[OBSTÁCULO]' if obst else ''}")
            self._insp_detalle_2_lbl.set("Umbral:")
            self._insp_detalle_2_val.set("< 20.0 cm")

    def _iniciar_reset_hardware(self) -> None:
        self._reset_activo = True
        for comp in self.componentes_activos:
            if isinstance(comp, InterruptorDipComponente):
                comp.establecer_estado(False, adm=self.adm)
            elif isinstance(comp, PulsadorComponente):
                comp.soltar(adm=self.adm)
        self.adm.reset()
        self._actualizar_vista_desde_adm()
        self._hover_var.set("RESET hardware ejecutado (Pin 9 RST). Puertos P0-P3 restaurados a 0xFF.")

    def _finalizar_reset_hardware(self) -> None:
        self._reset_activo = False
        self._actualizar_vista_desde_adm()

    def _iniciar_sondeo_adm(self) -> None:
        self._actualizar_vista_desde_adm()
        self._after_id = self.root.after(self.POLL_INTERVAL_MS, self._iniciar_sondeo_adm)

    def _actualizar_vista_desde_adm(self) -> None:
        self.adm.sincronizar()
        self._xtal_toggle = not self._xtal_toggle

        for num_dip, oval_id in self._pin_indicators.items():
            pin = self._pin_meta[num_dip]
            if pin.adm_canal is not None:
                voltaje = self.adm.puertos[pin.adm_canal]
                color = (
                    self.COLOR_PIN_ALTO
                    if voltaje >= ADM.UMBRAL_LOGICO
                    else self.COLOR_PIN_BAJO
                )
            else:
                color = self._color_por_defecto_pin(pin)
            self.canvas_dip.itemconfig(oval_id, fill=color)

        for p_idx in range(4):
            valor_byte = self.adm.leer_byte_puerto(p_idx)
            self._port_hex_vars[p_idx].set(f"0x{valor_byte:02X}")
            bits_hi = f"{(valor_byte >> 4) & 0x0F:04b}"
            bits_lo = f"{valor_byte & 0x0F:04b}"
            self._port_bin_vars[p_idx].set(f"{bits_hi} {bits_lo}")

            base = p_idx * 8
            salidas = sum(
                1 for b in range(8) if self.adm.sentidos[base + b] == ADM.MODO_ESCRITURA
            )
            self._port_dir_vars[p_idx].set(f"IN:{8 - salidas}  OUT:{salidas}")

        for etiqueta, socket_id in self._bus_sockets_leds.items():
            _, canal, tipo = normalizar_destino_adm(etiqueta)
            if canal is not None:
                volt = self.adm.puertos[canal]
                color_sock = (
                    self.COLOR_PIN_ALTO if volt >= ADM.UMBRAL_LOGICO else self.COLOR_PIN_BAJO
                )
                self.canvas_protoboard.itemconfig(socket_id, fill=color_sock)
            elif tipo == "vcc":
                self.canvas_protoboard.itemconfig(socket_id, fill=self.COLOR_PIN_VCC)
            else:
                self.canvas_protoboard.itemconfig(socket_id, fill=self.COLOR_PIN_GND)

        for componente in self.componentes_activos:
            componente.actualizar_desde_adm(self.adm)

        nodos_con_5v: set[tuple[str, int]] = set()
        for cable in self.protoboard.cables.values():
            en_alto = cable.actualizar_desde_adm(self.adm)
            if en_alto and cable.nodo_protoboard is not None:
                nodos_con_5v.add(cable.nodo_protoboard)
        self.protoboard._actualizar_iluminacion_nodos(nodos_con_5v)

        self._dibujar_marco_seleccion()
        self._refrescar_inspector_propiedades()

    def _al_cerrar(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.adm.close()
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="at89s51-gui",
        description="Laboratorio virtual Tkinter estilo Tinkercad para el AT89S51.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(".state/ports_state.bin"),
        metavar="ARCHIVO_MMAP",
        help="Ruta al archivo compartido mmap de ADM (por defecto: .state/ports_state.bin).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    adm = ADM(state_file=args.state_file)
    root = tk.Tk()
    _ = AT89S51EmulatorGUI(root=root, adm=adm)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
