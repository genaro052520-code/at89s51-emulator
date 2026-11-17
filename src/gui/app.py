"""src/gui/app.py - Proceso gráfico independiente del encapsulado DIP-40."""

import tkinter as tk
from src.ports.adm import ADM


class EmulatorGUIApp:
    """Ventana principal Tkinter acoplada únicamente a la capa ADM."""

    def __init__(self, root: tk.Tk, adm: ADM) -> None:
        self.root = root
        self.adm = adm

    def poll_adm_state(self) -> None:
        """Consulta periódicamente el estado de pines en ADM y actualiza la vista."""
        pass


def main() -> None:
    """Punto de entrada del proceso gráfico (GUI DIP-40)."""
    root = tk.Tk()
    root.title("AT89S51 - Encapsulado DIP-40")
    adm = ADM()
    _ = EmulatorGUIApp(root, adm)
    root.mainloop()


if __name__ == "__main__":
    main()