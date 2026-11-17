"""Interfaz gráfica independiente (GUI) del encapsulado DIP-40 para el AT89S51.

Este módulo representa únicamente el plano físico y los periféricos externos
del microcontrolador Atmel/Microchip AT89S51 usando Tkinter. No tiene ninguna
dependencia ni referencia directa a la CPU, ALU o memorias internas; toda la
comunicación se realiza exclusivamente mediante la clase ADM (mmap).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from typing import Sequence

from src.ports.adm import ADM


@dataclass(frozen=True)
class PinDIP40:
    """Descriptor físico y eléctrico de cada uno de los 40 pines del AT89S51."""

    numero_dip: int          # Número de pin físico (1 a 40)
    etiqueta: str            # Nombre según hoja de datos (ej. "P1.0", "P3.2 / INT0", "VCC")
    adm_canal: int | None    # Índice en ADM (0-31 para P0-P3) o None si es alimentación/control
    tipo: str                # "io", "vcc", "gnd", "rst", "xtal", "ctrl"


# Mapa oficial de pines del encapsulado DIP-40 del Atmel/Microchip AT89S51
# Lado izquierdo (1..20 de arriba hacia abajo) y lado derecho (40..21 de arriba hacia abajo)
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
    """Genera el diccionario ordenado de nombres de pines seleccionables para botones."""
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
    """Aplicación gráfica Tkinter del encapsulado DIP-40 y periféricos virtuales."""

    POLL_INTERVAL_MS: int = 50

    # Paleta de colores estilo placa PCB / laboratorio electrónico
    BG_APP: str = "#0F172A"
    BG_CARD: str = "#1E293B"
    BG_PCB: str = "#0B1324"
    CHIP_BODY: str = "#181B20"
    CHIP_BORDER: str = "#475569"
    PIN_METAL: str = "#CBD5E1"
    TEXT_PRIMARY: str = "#F8FAFC"
    TEXT_MUTED: str = "#94A3B8"
    ACCENT_CYAN: str = "#38BDF8"

    COLOR_PIN_ALTO: str = "#00E676"      # Verde brillante (5V / Nivel lógico 1)
    COLOR_PIN_BAJO: str = "#334155"      # Gris oscuro (0V / Nivel lógico 0)
    COLOR_PIN_VCC: str = "#EF4444"       # Rojo alimentación +5V
    COLOR_PIN_GND: str = "#3B82F6"       # Azul referencia 0V GND
    COLOR_PIN_XTAL: str = "#F59E0B"      # Ámbar oscilador

    def __init__(self, root: tk.Tk, adm: ADM) -> None:
        self.root: tk.Tk = root
        self.adm: ADM = adm
        self._after_id: str | None = None
        self._reset_activo: bool = False
        self._xtal_toggle: bool = False

        # Referencias a ítems dibujados en el Canvas DIP-40
        self._pin_indicators: dict[int, int] = {}
        self._pin_meta: dict[int, PinDIP40] = {}
        self._led_p1_ovals: list[int] = []
        self._led_p1_halos: list[int] = []

        # Estado de los 4 módulos de botones/interruptores externos
        self._opciones_pines: dict[str, int] = _construir_opciones_pines_io()
        self._boton_combos: list[ttk.Combobox] = []
        self._boton_pin_actual: list[int] = [26, 27, 16, 17]  # P3.2, P3.3, P2.0, P2.1
        self._boton_dip_vars: list[tk.BooleanVar] = []
        self._boton_estado_labels: list[tk.Label] = []

        # Variables de interfaz
        self._led_activo_alto = tk.BooleanVar(value=True)
        self._hover_var = tk.StringVar(
            value="Pase el cursor sobre cualquier pin del DIP-40 para inspeccionar su estado."
        )
        self._ipc_status_var = tk.StringVar(value="IPC ADM: Conectado (sondeo cada 50 ms)")

        self._port_hex_vars: list[tk.StringVar] = [tk.StringVar(value="0xFF") for _ in range(4)]
        self._port_bin_vars: list[tk.StringVar] = [tk.StringVar(value="1111 1111") for _ in range(4)]
        self._port_dir_vars: list[tk.StringVar] = [tk.StringVar(value="IN (Pull-up)") for _ in range(4)]

        self._configurar_ventana()
        self._construir_interfaz()
        self._iniciar_sondeo_adm()

    def _configurar_ventana(self) -> None:
        """Configura el título, dimensiones mínimas y protocolo de cierre de la ventana."""
        self.root.title("Emulador Atmel/Microchip AT89S51 — Encapsulado DIP-40 y Periféricos")
        self.root.configure(bg=self.BG_APP)
        self.root.minsize(1040, 720)
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _construir_interfaz(self) -> None:
        """Construye el layout principal dividido en Encapsulado DIP-40 y Panel E/S."""
        header = tk.Frame(self.root, bg=self.BG_CARD, padx=16, pady=10)
        header.pack(fill=tk.X, padx=12, pady=(12, 6))

        tk.Label(
            header,
            text="ATMEL / MICROCHIP AT89S51 (MCS-51)",
            font=("Consolas", 14, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            textvariable=self._ipc_status_var,
            font=("Consolas", 10),
            fg=self.ACCENT_CYAN,
            bg=self.BG_CARD,
        ).pack(side=tk.RIGHT)

        main_frame = tk.Frame(self.root, bg=self.BG_APP)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        left_card = tk.Frame(main_frame, bg=self.BG_CARD, padx=12, pady=12)
        left_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 8))

        tk.Label(
            left_card,
            text="ENCAPSULADO FÍSICO DIP-40 (VISTA SUPERIOR)",
            font=("Consolas", 11, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(0, 8))

        self.canvas_dip = tk.Canvas(
            left_card,
            width=480,
            height=610,
            bg=self.BG_PCB,
            highlightthickness=1,
            highlightbackground=self.CHIP_BORDER,
        )
        self.canvas_dip.pack()
        self._dibujar_encapsulado_dip40()

        leyenda = tk.Frame(left_card, bg=self.BG_CARD, pady=6)
        leyenda.pack(fill=tk.X)
        for color, texto in [
            (self.COLOR_PIN_ALTO, "Alto (1 / 5V)"),
            (self.COLOR_PIN_BAJO, "Bajo (0 / 0V)"),
            (self.COLOR_PIN_VCC, "VCC / RST"),
            (self.COLOR_PIN_GND, "GND"),
        ]:
            item = tk.Frame(leyenda, bg=self.BG_CARD)
            item.pack(side=tk.LEFT, padx=(0, 12))
            tk.Canvas(item, width=12, height=12, bg=color, highlightthickness=0).pack(
                side=tk.LEFT, padx=(0, 4)
            )
            tk.Label(
                item, text=texto, font=("Consolas", 9), fg=self.TEXT_MUTED, bg=self.BG_CARD
            ).pack(side=tk.LEFT)

        right_col = tk.Frame(main_frame, bg=self.BG_APP)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._construir_panel_monitor_puertos(right_col)
        self._construir_panel_leds_p1(right_col)
        self._construir_panel_botones_entrada(right_col)
        self._construir_panel_reset_y_control(right_col)

        footer = tk.Frame(self.root, bg=self.BG_CARD, padx=14, pady=6)
        footer.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(
            footer,
            textvariable=self._hover_var,
            font=("Consolas", 10),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # Dibujo del Encapsulado DIP-40 en Canvas
    # ------------------------------------------------------------------

    def _dibujar_encapsulado_dip40(self) -> None:
        """Dibuja el circuito integrado DIP-40 de 40 pines con etiquetas reales."""
        c = self.canvas_dip
        c.delete("all")

        chip_x1, chip_y1 = 165, 24
        chip_x2, chip_y2 = 315, 586
        cx_mid = (chip_x1 + chip_x2) // 2

        c.create_rectangle(
            chip_x1 - 24,
            chip_y1 - 10,
            chip_x2 + 24,
            chip_y2 + 10,
            outline="#1E3A5F",
            dash=(4, 3),
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
            cx_mid - 22,
            chip_y1 - 16,
            cx_mid + 22,
            chip_y1 + 16,
            start=180,
            extent=180,
            fill=self.BG_PCB,
            outline=self.CHIP_BORDER,
            width=2,
        )

        c.create_oval(
            chip_x1 + 12,
            chip_y1 + 14,
            chip_x1 + 22,
            chip_y1 + 24,
            fill="#334155",
            outline="#64748B",
        )

        c.create_text(
            cx_mid,
            235,
            text="ATMEL",
            fill="#CBD5E1",
            font=("Consolas", 15, "bold"),
        )
        c.create_text(
            cx_mid,
            262,
            text="AT89S51",
            fill="#F8FAFC",
            font=("Consolas", 14, "bold"),
        )
        c.create_text(
            cx_mid,
            286,
            text="24PU  8051",
            fill="#94A3B8",
            font=("Consolas", 10),
        )
        c.create_text(
            cx_mid,
            312,
            text="4KB FLASH / 128B RAM",
            fill="#64748B",
            font=("Consolas", 8),
        )

        y_inicio = 46
        paso_y = 27.5

        for idx in range(20):
            y = y_inicio + idx * paso_y
            self._dibujar_pin_individual(
                pin=PINES_IZQUIERDA[idx],
                chip_edge_x=chip_x1,
                y=y,
                es_izquierda=True,
            )
            self._dibujar_pin_individual(
                pin=PINES_DERECHA_TOP_DOWN[idx],
                chip_edge_x=chip_x2,
                y=y,
                es_izquierda=False,
            )

    def _dibujar_pin_individual(
        self,
        pin: PinDIP40,
        chip_edge_x: int,
        y: float,
        es_izquierda: bool,
    ) -> None:
        """Dibuja la pata metálica, número de pin, etiqueta e indicador LED de un pin."""
        c = self.canvas_dip
        largo_pata = 22
        alto_pata = 12
        radio_led = 6

        if es_izquierda:
            pata_x1 = chip_edge_x - largo_pata
            pata_x2 = chip_edge_x
            num_x = chip_edge_x + 16
            led_cx = pata_x1 - 12
            label_x = led_cx - 12
            anchor_label = tk.E
        else:
            pata_x1 = chip_edge_x
            pata_x2 = chip_edge_x + largo_pata
            num_x = chip_edge_x - 16
            led_cx = pata_x2 + 12
            label_x = led_cx + 12
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
            font=("Consolas", 8, "bold"),
        )

        color_inicial = self._color_por_defecto_pin(pin)

        tag_pin = f"pin_{pin.numero_dip}"
        oval_id = c.create_oval(
            led_cx - radio_led,
            y - radio_led,
            led_cx + radio_led,
            y + radio_led,
            fill=color_inicial,
            outline="#0F172A",
            width=1.5,
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
            font=("Consolas", 9, "bold" if pin.tipo == "io" else "normal"),
            anchor=anchor_label,
            tags=(tag_pin,),
        )

        self._pin_indicators[pin.numero_dip] = oval_id
        self._pin_meta[pin.numero_dip] = pin

        for item_id in (oval_id, text_id):
            c.tag_bind(
                item_id,
                "<Enter>",
                lambda _e, p=pin: self._mostrar_info_pin(p),
            )

    def _color_por_defecto_pin(self, pin: PinDIP40) -> str:
        """Retorna el color base para pines no mapeados a E/S digital."""
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

    def _mostrar_info_pin(self, pin: PinDIP40) -> None:
        """Actualiza la barra inferior con el voltaje y dirección del pin seleccionado."""
        if pin.adm_canal is None:
            self._hover_var.set(
                f"Pin DIP #{pin.numero_dip:02d} [{pin.etiqueta}] — Pin de alimentación/control hardware."
            )
            return

        voltaje = self.adm.puertos[pin.adm_canal]
        sentido = self.adm.sentidos[pin.adm_canal]
        nivel = 1 if voltaje >= ADM.UMBRAL_LOGICO else 0
        modo_str = "SALIDA (Drive 0V)" if sentido == ADM.MODO_ESCRITURA else "ENTRADA / Pull-up"
        self._hover_var.set(
            f"Pin DIP #{pin.numero_dip:02d} [{pin.etiqueta}] | Canal ADM #{pin.adm_canal:02d} | "
            f"Estado: {nivel} ({voltaje:.2f} V) | Modo: {modo_str}"
        )

    # ------------------------------------------------------------------
    # Paneles de Periféricos Virtuales y Monitor de Registros
    # ------------------------------------------------------------------

    def _construir_panel_monitor_puertos(self, parent: tk.Frame) -> None:
        """Crea el monitor hexadecimal/binario en tiempo real de P0, P1, P2 y P3."""
        card = tk.Frame(parent, bg=self.BG_CARD, padx=14, pady=10)
        card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            card,
            text="MONITOR DE PUERTOS EN TIEMPO REAL (LECTURA DESDE ADM)",
            font=("Consolas", 11, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(0, 8))

        grid = tk.Frame(card, bg=self.BG_CARD)
        grid.pack(fill=tk.X)

        nombres = [
            "P0 (0x80)",
            "P1 (0x90)",
            "P2 (0xA0)",
            "P3 (0xB0)",
        ]
        for idx, titulo in enumerate(nombres):
            col = tk.Frame(
                grid,
                bg=self.BG_PCB,
                padx=10,
                pady=8,
                highlightthickness=1,
                highlightbackground=self.CHIP_BORDER,
            )
            col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if idx == 0 else 6, 0))

            tk.Label(
                col,
                text=titulo,
                font=("Consolas", 10, "bold"),
                fg=self.ACCENT_CYAN,
                bg=self.BG_PCB,
            ).pack(anchor=tk.W)

            tk.Label(
                col,
                textvariable=self._port_hex_vars[idx],
                font=("Consolas", 16, "bold"),
                fg=self.COLOR_PIN_ALTO,
                bg=self.BG_PCB,
            ).pack(anchor=tk.W, pady=(2, 0))

            tk.Label(
                col,
                textvariable=self._port_bin_vars[idx],
                font=("Consolas", 10),
                fg=self.TEXT_PRIMARY,
                bg=self.BG_PCB,
            ).pack(anchor=tk.W)

            tk.Label(
                col,
                textvariable=self._port_dir_vars[idx],
                font=("Consolas", 8),
                fg=self.TEXT_MUTED,
                bg=self.BG_PCB,
            ).pack(anchor=tk.W, pady=(2, 0))

    def _construir_panel_leds_p1(self, parent: tk.Frame) -> None:
        """Crea el banco visual de 8 LEDs conectados al Puerto 1 (P1.0 - P1.7)."""
        card = tk.Frame(parent, bg=self.BG_CARD, padx=14, pady=10)
        card.pack(fill=tk.X, pady=(0, 8))

        top_row = tk.Frame(card, bg=self.BG_CARD)
        top_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            top_row,
            text="BANCO DE 8 LEDs VIRTUALES — PUERTO 1 (P1.7 .. P1.0)",
            font=("Consolas", 11, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT)

        tk.Checkbutton(
            top_row,
            text="Lógica Positiva (1=ON)",
            variable=self._led_activo_alto,
            font=("Consolas", 9),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
            selectcolor=self.BG_PCB,
            activebackground=self.BG_CARD,
            activeforeground=self.TEXT_PRIMARY,
            command=self._actualizar_vista_desde_adm,
        ).pack(side=tk.RIGHT)

        self.canvas_leds = tk.Canvas(
            card,
            height=92,
            bg=self.BG_PCB,
            highlightthickness=1,
            highlightbackground=self.CHIP_BORDER,
        )
        self.canvas_leds.pack(fill=tk.X)

        self._led_p1_ovals.clear()
        self._led_p1_halos.clear()

        # Dibujar 8 LEDs ordenados de MSB (P1.7 a la izquierda) a LSB (P1.0 a la derecha)
        for pos in range(8):
            bit = 7 - pos
            cx = 42 + pos * 62
            cy = 40

            halo = self.canvas_leds.create_oval(
                cx - 21,
                cy - 21,
                cx + 21,
                cy + 21,
                fill="",
                outline="",
            )
            cuerpo = self.canvas_leds.create_oval(
                cx - 14,
                cy - 14,
                cx + 14,
                cy + 14,
                fill="#2D1518",
                outline="#64748B",
                width=2,
            )
            self.canvas_leds.create_text(
                cx,
                72,
                text=f"P1.{bit}",
                fill=self.TEXT_PRIMARY,
                font=("Consolas", 9, "bold"),
            )
            self._led_p1_halos.append(halo)
            self._led_p1_ovals.append(cuerpo)

    def _construir_panel_botones_entrada(self, parent: tk.Frame) -> None:
        """Crea 4 módulos interactivos de pulsadores e interruptores DIP para entradas."""
        card = tk.Frame(parent, bg=self.BG_CARD, padx=14, pady=10)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        tk.Label(
            card,
            text="ESTÍMULOS EXTERNOS — BOTONES PULSADORES E INTERRUPTORES DIP",
            font=("Consolas", 11, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(0, 4))

        tk.Label(
            card,
            text="Al presionar o activar un interruptor se inyecta 0V (GND) en ADM; al soltar vuelve a Pull-up (5V).",
            font=("Consolas", 9),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
        ).pack(anchor=tk.W, pady=(0, 8))

        lista_etiquetas = list(self._opciones_pines.keys())
        pines_iniciales = [
            "P3.2 (INT0)",
            "P3.3 (INT1)",
            "P2.0 (A8)",
            "P2.1 (A9)",
        ]

        self._boton_combos.clear()
        self._boton_dip_vars.clear()
        self._boton_estado_labels.clear()

        for idx in range(4):
            fila = tk.Frame(
                card,
                bg=self.BG_PCB,
                padx=10,
                pady=7,
                highlightthickness=1,
                highlightbackground=self.CHIP_BORDER,
            )
            fila.pack(fill=tk.X, pady=3)

            tk.Label(
                fila,
                text=f"SW{idx + 1}:",
                font=("Consolas", 10, "bold"),
                fg=self.ACCENT_CYAN,
                bg=self.BG_PCB,
            ).pack(side=tk.LEFT, padx=(0, 8))

            combo = ttk.Combobox(
                fila,
                values=lista_etiquetas,
                state="readonly",
                width=16,
                font=("Consolas", 9),
            )
            combo.set(pines_iniciales[idx])
            combo.pack(side=tk.LEFT, padx=(0, 10))
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, b_idx=idx: self._al_cambiar_pin_boton(b_idx),
            )
            self._boton_combos.append(combo)

            btn_push = tk.Button(
                fila,
                text="PULSAR (GND)",
                font=("Consolas", 9, "bold"),
                bg="#2563EB",
                fg="#FFFFFF",
                activebackground="#1D4ED8",
                activeforeground="#FFFFFF",
                relief=tk.RAISED,
                padx=10,
                pady=2,
                cursor="hand2",
            )
            btn_push.pack(side=tk.LEFT, padx=(0, 10))
            btn_push.bind(
                "<ButtonPress-1>",
                lambda _e, b_idx=idx: self._presionar_pulsador(b_idx),
            )
            btn_push.bind(
                "<ButtonRelease-1>",
                lambda _e, b_idx=idx: self._soltar_pulsador(b_idx),
            )

            dip_var = tk.BooleanVar(value=False)
            self._boton_dip_vars.append(dip_var)
            chk_dip = tk.Checkbutton(
                fila,
                text="Retener LOW",
                variable=dip_var,
                font=("Consolas", 9),
                fg=self.TEXT_PRIMARY,
                bg=self.BG_PCB,
                selectcolor="#0F172A",
                activebackground=self.BG_PCB,
                activeforeground=self.TEXT_PRIMARY,
                command=lambda b_idx=idx: self._al_conmutar_dip(b_idx),
            )
            chk_dip.pack(side=tk.LEFT, padx=(0, 8))

            lbl_estado = tk.Label(
                fila,
                text="5.0V (1)",
                font=("Consolas", 9, "bold"),
                fg=self.COLOR_PIN_ALTO,
                bg=self.BG_PCB,
            )
            lbl_estado.pack(side=tk.RIGHT)
            self._boton_estado_labels.append(lbl_estado)

    def _construir_panel_reset_y_control(self, parent: tk.Frame) -> None:
        """Crea el botón físico de RESET (Pin 9) y controles de placa."""
        card = tk.Frame(parent, bg=self.BG_CARD, padx=14, pady=10)
        card.pack(fill=tk.X)

        btn_reset = tk.Button(
            card,
            text="RESET HARDWARE (PIN 9 RST)",
            font=("Consolas", 11, "bold"),
            bg="#DC2626",
            fg="#FFFFFF",
            activebackground="#991B1B",
            activeforeground="#FFFFFF",
            padx=16,
            pady=8,
            cursor="hand2",
        )
        btn_reset.pack(side=tk.LEFT)
        btn_reset.bind("<ButtonPress-1>", lambda _e: self._iniciar_reset_hardware())
        btn_reset.bind("<ButtonRelease-1>", lambda _e: self._finalizar_reset_hardware())

        tk.Label(
            card,
            text="Restaura puertos P0-P3 a 0xFF (5.0V) y libera estímulos en ADM.",
            font=("Consolas", 9),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
        ).pack(side=tk.LEFT, padx=(14, 0))

    # ------------------------------------------------------------------
    # Manejadores de Interacción de Periféricos Externos
    # ------------------------------------------------------------------

    def _al_cambiar_pin_boton(self, idx: int) -> None:
        """Reasigna un botón externo a un nuevo pin ADM liberando el pin anterior."""
        pin_anterior = self._boton_pin_actual[idx]
        self.adm.liberar_estimulo_externo(pin_anterior)

        etiqueta_nueva = self._boton_combos[idx].get()
        pin_nuevo = self._opciones_pines[etiqueta_nueva]
        self._boton_pin_actual[idx] = pin_nuevo

        if self._boton_dip_vars[idx].get():
            self.adm.inyectar_estimulo_externo(pin_nuevo, 0)
        self._actualizar_vista_desde_adm()

    def _presionar_pulsador(self, idx: int) -> None:
        """Inyecta nivel lógico bajo (0V) en ADM mientras se mantiene presionado el botón."""
        pin_adm = self._boton_pin_actual[idx]
        self.adm.inyectar_estimulo_externo(pin_adm, 0)
        self._actualizar_vista_desde_adm()

    def _soltar_pulsador(self, idx: int) -> None:
        """Libera el estímulo al soltar el botón salvo que el DIP switch esté retenido."""
        pin_adm = self._boton_pin_actual[idx]
        if self._boton_dip_vars[idx].get():
            self.adm.inyectar_estimulo_externo(pin_adm, 0)
        else:
            self.adm.liberar_estimulo_externo(pin_adm)
        self._actualizar_vista_desde_adm()

    def _al_conmutar_dip(self, idx: int) -> None:
        """Fija o libera el nivel bajo (0V) de forma permanente mediante interruptor DIP."""
        pin_adm = self._boton_pin_actual[idx]
        if self._boton_dip_vars[idx].get():
            self.adm.inyectar_estimulo_externo(pin_adm, 0)
        else:
            self.adm.liberar_estimulo_externo(pin_adm)
        self._actualizar_vista_desde_adm()

    def _iniciar_reset_hardware(self) -> None:
        """Activa el pulso alto en Pin 9 (RST) y reinicia el bus ADM."""
        self._reset_activo = True
        for idx, dip_var in enumerate(self._boton_dip_vars):
            dip_var.set(False)
            self.adm.liberar_estimulo_externo(self._boton_pin_actual[idx])
        self.adm.reset()
        self._actualizar_vista_desde_adm()

    def _finalizar_reset_hardware(self) -> None:
        """Desactiva el pulso de RESET al soltar el botón."""
        self._reset_activo = False
        self._actualizar_vista_desde_adm()

    # ------------------------------------------------------------------
    # Bucle de Sondeo Periódico (50 ms) contra ADM
    # ------------------------------------------------------------------

    def _iniciar_sondeo_adm(self) -> None:
        """Arranca el temporizador periódico de 50 ms usando root.after."""
        self._actualizar_vista_desde_adm()
        self._after_id = self.root.after(self.POLL_INTERVAL_MS, self._iniciar_sondeo_adm)

    def _actualizar_vista_desde_adm(self) -> None:
        """Sincroniza desde mmap y refresca pines DIP-40, LEDs P1 y monitor de registros."""
        self.adm.sincronizar()
        self._xtal_toggle = not self._xtal_toggle

        # 1. Actualizar los 40 indicadores del encapsulado DIP-40
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

        # 2. Actualizar monitor hexadecimal y binario de P0, P1, P2 y P3
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
            entradas = 8 - salidas
            self._port_dir_vars[p_idx].set(f"IN:{entradas}  OUT:{salidas}")

        # 3. Actualizar banco de 8 LEDs del Puerto 1 (P1.7 .. P1.0)
        p1_byte = self.adm.leer_byte_puerto(1)
        activo_alto = self._led_activo_alto.get()
        for pos in range(8):
            bit = 7 - pos
            nivel_pin = (p1_byte >> bit) & 0x01
            encendido = (nivel_pin == 1) if activo_alto else (nivel_pin == 0)
            if encendido:
                self.canvas_leds.itemconfig(
                    self._led_p1_ovals[pos], fill="#FF1744", outline="#FF8A80"
                )
                self.canvas_leds.itemconfig(
                    self._led_p1_halos[pos], fill="#4C0519", outline="#FB7185"
                )
            else:
                self.canvas_leds.itemconfig(
                    self._led_p1_ovals[pos], fill="#2D1518", outline="#475569"
                )
                self.canvas_leds.itemconfig(
                    self._led_p1_halos[pos], fill="", outline=""
                )

        # 4. Actualizar etiquetas de estado de los 4 botones externos
        for idx, pin_adm in enumerate(self._boton_pin_actual):
            volt = self.adm.puertos[pin_adm]
            nivel = 1 if volt >= ADM.UMBRAL_LOGICO else 0
            self._boton_estado_labels[idx].configure(
                text=f"{volt:.1f}V ({nivel})",
                fg=self.COLOR_PIN_ALTO if nivel == 1 else "#F87171",
            )

    def _al_cerrar(self) -> None:
        """Detiene el ciclo after y libera de forma limpia los recursos mmap de ADM."""
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.adm.close()
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    """Construye el analizador de argumentos opcionales para el lanzador GUI."""
    parser = argparse.ArgumentParser(
        prog="at89s51-gui",
        description="Interfaz gráfica DIP-40 y periféricos virtuales del AT89S51.",
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
    """Punto de entrada principal del proceso gráfico (GUI)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    adm = ADM(state_file=args.state_file)
    root = tk.Tk()
    _ = AT89S51EmulatorGUI(root=root, adm=adm)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
