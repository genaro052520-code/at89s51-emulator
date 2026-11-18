"""Clase base abstracta para los componentes electrónicos virtuales del banco Tinkercad.

Define el contrato común de renderizado sobre `tk.Canvas`, gestión de coordenadas,
puntos de conexión eléctrica (pads/terminales) y sincronización periódica contra
la instancia de `ADM` (`src/ports/adm.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import tkinter as tk
from typing import Any
import uuid

from src.ports.adm import ADM


class ComponenteElectronico(ABC):
    """Clase base para cualquier componente electrónico virtual sobre un `tk.Canvas`."""

    def __init__(
        self,
        nombre: str,
        x: float = 0.0,
        y: float = 0.0,
        pines_conectados: dict[str, int] | None = None,
        propiedades: dict[str, Any] | None = None,
    ) -> None:
        self.nombre: str = nombre
        self.x: float = float(x)
        self.y: float = float(y)
        self.pines_conectados: dict[str, int] = (
            dict(pines_conectados) if pines_conectados is not None else {}
        )
        self.propiedades: dict[str, Any] = (
            dict(propiedades) if propiedades is not None else {}
        )

        self.canvas: tk.Canvas | None = None
        self.tag_grupo: str = f"comp_{uuid.uuid4().hex[:10]}"
        self.items_canvas: list[int] = []

    @abstractmethod
    def dibujar(self, canvas: tk.Canvas) -> None:
        """Dibuja la geometría completa del componente sobre el `tk.Canvas` indicado."""

    @abstractmethod
    def actualizar_desde_adm(self, adm: ADM) -> None:
        """Consulta el estado eléctrico en `ADM` y actualiza la apariencia o animación."""

    @abstractmethod
    def obtener_puntos_conexion(self) -> dict[str, tuple[float, float]]:
        """Retorna las coordenadas `(x, y)` absolutas de cada terminal del componente."""

    def mover(self, dx: float, dy: float) -> None:
        """Desplaza el componente y todos sus elementos gráficos en `(dx, dy)` píxeles."""
        self.x += float(dx)
        self.y += float(dy)
        if self.canvas is not None:
            self.canvas.move(self.tag_grupo, dx, dy)

    def establecer_posicion(self, nueva_x: float, nueva_y: float) -> None:
        """Posiciona el componente en las coordenadas absolutas `(nueva_x, nueva_y)`."""
        dx = float(nueva_x) - self.x
        dy = float(nueva_y) - self.y
        self.mover(dx, dy)

    def eliminar(self) -> None:
        """Elimina todos los elementos gráficos asociados al componente en el canvas."""
        if self.canvas is not None:
            self.canvas.delete(self.tag_grupo)
        self.items_canvas.clear()

    def obtener_bbox(self) -> tuple[float, float, float, float] | None:
        """Retorna la caja delimitadora `(x1, y1, x2, y2)` actual del componente en canvas."""
        if self.canvas is None:
            return None
        return self.canvas.bbox(self.tag_grupo)
