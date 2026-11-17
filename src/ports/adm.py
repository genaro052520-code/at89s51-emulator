"""Módulo de Administración de Puertos (ADM) para el emulador Atmel/Microchip AT89S51.

Provee una capa intermedia desacoplada entre el núcleo de emulación (CLI) y la
interfaz gráfica (GUI) mediante memoria compartida (mmap) y bloqueos de archivo
multiplataforma para evitar condiciones de carrera entre procesos independientes.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
import mmap
import os
from pathlib import Path
import struct
import threading
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class ADM:
    """Administrador de Puertos e IPC en tiempo real del microcontrolador AT89S51.

    Modela los 32 pines digitales agrupados en cuatro puertos de 8 bits:
      - P0: pines 0 a 7
      - P1: pines 8 a 15
      - P2: pines 16 a 23
      - P3: pines 24 a 31
    Además incorpora 8 canales analógicos auxiliares (índices 32 a 39) para
    periféricos externos conectados al entorno de simulación.

    Attributes:
        puertos (list[float]): Voltajes actuales (0.0 V a 5.0 V) de los 40 canales.
        sentidos (list[int]): Dirección de cada canal (0 = lectura/entrada,
            1 = escritura/salida).
    """

    # Constantes eléctricas y lógicas TTL (5V)
    MODO_LECTURA: int = 0
    MODO_ESCRITURA: int = 1

    VOLTAJE_MIN: float = 0.0
    VOLTAJE_MAX: float = 5.0
    VOLTAJE_BAJO: float = 0.0
    VOLTAJE_ALTO: float = 5.0
    UMBRAL_LOGICO: float = 2.5

    # Distribución de pines y canales
    NUM_PUERTOS_DIGITALES: int = 4
    PINES_POR_PUERTO: int = 8
    TOTAL_PINES_DIGITALES: int = 32
    CANALES_ANALOGICOS_AUX: int = 8
    TOTAL_CANALES: int = TOTAL_PINES_DIGITALES + CANALES_ANALOGICOS_AUX  # 40 canales

    # Formato binario en memoria compartida (.state/ports_state.bin)
    # Cabecera: Magic (8B) + Secuencia uint64 (8B) + Total canales uint16 (2B) + Padding (6B) = 24B
    # Cuerpo: 40 floats (puertos) + 40 uint8 (sentidos) + 32 uint8 (latches) + 40 floats (estímulos)
    _MAGIC: bytes = b"8051ADM\x01"
    _HEADER_STRUCT: struct.Struct = struct.Struct("<8sQH6x")
    _PAYLOAD_STRUCT: struct.Struct = struct.Struct(
        f"<{TOTAL_CANALES}d{TOTAL_CANALES}B{TOTAL_PINES_DIGITALES}B{TOTAL_CANALES}d"
    )
    _MMAP_SIZE: int = 1024  # Bloque alineado de 1 KB

    def __init__(self, state_file: Path | str = ".state/ports_state.bin") -> None:
        """Inicializa o se acopla al bloque de memoria compartida de puertos.

        Si el archivo de estado ya existe y posee una cabecera válida (por ejemplo,
        iniciado previamente por el proceso CLI), el proceso actual se conecta sin
        sobrescribir el estado en curso.

        Args:
            state_file: Ruta al archivo binario respaldado por mmap.
        """
        self._state_path: Path = Path(state_file)
        self._lock_path: Path = self._state_path.with_suffix(".lock")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        self._thread_lock: threading.RLock = threading.RLock()
        self._secuencia: int = 0

        # Atributos públicos exigidos por el diseño orientado a objetos
        self.puertos: list[float] = [self.VOLTAJE_ALTO] * self.TOTAL_PINES_DIGITALES + [
            self.VOLTAJE_BAJO
        ] * self.CANALES_ANALOGICOS_AUX
        self.sentidos: list[int] = [self.MODO_LECTURA] * self.TOTAL_CANALES

        # Estado interno de latches del 8051 (P0-P3) y estímulos externos de periféricos
        self._latches: list[int] = [1] * self.TOTAL_PINES_DIGITALES
        self._estimulos_externos: list[float] = [float("nan")] * self.TOTAL_CANALES

        self._fd: int | None = None
        self._lock_fd: int | None = None
        self._mmap: mmap.mmap | None = None

        self._abrir_memoria_compartida()

    def _abrir_memoria_compartida(self) -> None:
        """Abre los descriptores de archivo y mapea el bloque IPC en memoria."""
        self._lock_fd = os.open(
            str(self._lock_path),
            os.O_CREAT | os.O_RDWR,
            0o666,
        )
        self._fd = os.open(
            str(self._state_path),
            os.O_CREAT | os.O_RDWR,
            0o666,
        )

        with self._bloqueo_exclusivo():
            tamano_actual = os.fstat(self._fd).st_size
            if tamano_actual < self._MMAP_SIZE:
                os.ftruncate(self._fd, self._MMAP_SIZE)

            self._mmap = mmap.mmap(self._fd, self._MMAP_SIZE, access=mmap.ACCESS_WRITE)

            # Verificar si ya existe un estado válido creado por otro proceso
            self._mmap.seek(0)
            magic, seq, total = self._HEADER_STRUCT.unpack(
                self._mmap.read(self._HEADER_STRUCT.size)
            )
            if magic == self._MAGIC and total == self.TOTAL_CANALES and seq > 0:
                self._cargar_desde_mmap_sin_bloqueo()
            else:
                self._volcar_a_mmap_sin_bloqueo()

    @contextmanager
    def _bloqueo_exclusivo(self) -> Iterator[None]:
        """Context manager que garantiza exclusión mutua intra e inter-proceso."""
        if self._lock_fd is None:
            raise RuntimeError("El administrador ADM ya fue cerrado.")

        with self._thread_lock:
            if os.name == "nt":
                os.lseek(self._lock_fd, 0, os.SEEK_SET)
                msvcrt.locking(self._lock_fd, msvcrt.LK_LOCK, 1)
            else:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    os.lseek(self._lock_fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._lock_fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)

    def _cargar_desde_mmap_sin_bloqueo(self) -> None:
        """Lee el contenido binario desde mmap y actualiza los atributos en RAM."""
        if self._mmap is None:
            raise RuntimeError("La región mmap no está inicializada.")

        self._mmap.seek(0)
        magic, seq, total = self._HEADER_STRUCT.unpack(
            self._mmap.read(self._HEADER_STRUCT.size)
        )
        if magic != self._MAGIC or total != self.TOTAL_CANALES:
            raise ValueError("Cabecera corrupta o incompatible en ports_state.bin.")

        datos = self._PAYLOAD_STRUCT.unpack(
            self._mmap.read(self._PAYLOAD_STRUCT.size)
        )
        n = self.TOTAL_CANALES
        d = self.TOTAL_PINES_DIGITALES

        self._secuencia = seq
        self.puertos = list(datos[0:n])
        self.sentidos = list(datos[n : 2 * n])
        self._latches = list(datos[2 * n : 2 * n + d])
        self._estimulos_externos = list(datos[2 * n + d : 3 * n + d])

    def _volcar_a_mmap_sin_bloqueo(self) -> None:
        """Serializa el estado actual hacia mmap e incrementa el contador de secuencia."""
        if self._mmap is None:
            raise RuntimeError("La región mmap no está inicializada.")

        self._secuencia += 1
        cabecera = self._HEADER_STRUCT.pack(
            self._MAGIC,
            self._secuencia,
            self.TOTAL_CANALES,
        )
        cuerpo = self._PAYLOAD_STRUCT.pack(
            *self.puertos,
            *self.sentidos,
            *self._latches,
            *self._estimulos_externos,
        )

        self._mmap.seek(0)
        self._mmap.write(cabecera)
        self._mmap.write(cuerpo)
        self._mmap.flush()

    def sincronizar(self) -> None:
        """Fuerza la lectura del estado más reciente desde la memoria compartida."""
        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()

    def _validar_canal(self, puerto: int, solo_digital: bool = False) -> None:
        """Valida que el índice del pin o canal se encuentre dentro del rango permitido."""
        limite = self.TOTAL_PINES_DIGITALES if solo_digital else self.TOTAL_CANALES
        if not isinstance(puerto, int) or isinstance(puerto, bool) or not (0 <= puerto < limite):
            tipo = "pin digital (0-31)" if solo_digital else f"canal (0-{self.TOTAL_CANALES - 1})"
            raise ValueError(f"Índice de puerto inválido: {puerto}. Se esperaba un {tipo}.")

    def _validar_num_puerto_8bit(self, num_puerto: int) -> None:
        """Valida que el identificador de puerto de 8 bits sea P0 (0), P1 (1), P2 (2) o P3 (3)."""
        if (
            not isinstance(num_puerto, int)
            or isinstance(num_puerto, bool)
            or not (0 <= num_puerto < self.NUM_PUERTOS_DIGITALES)
        ):
            raise ValueError(
                f"Número de puerto 8051 inválido: {num_puerto}. Valores válidos: 0 (P0) a 3 (P3)."
            )

    def _resolver_voltaje_pin_digital(self, pin: int) -> float:
        """Calcula el voltaje físico resultante en un pin digital del 8051.

        Si el latch está en 0 (salida activa), el transistor interno fuerza 0.0 V.
        Si el latch está en 1 (modo entrada/pull-up), prevalece el estímulo externo
        si existe; de lo contrario, la resistencia pull-up mantiene 5.0 V.
        """
        if self._latches[pin] == 0 and self.sentidos[pin] == self.MODO_ESCRITURA:
            return self.VOLTAJE_BAJO

        estimulo = self._estimulos_externos[pin]
        if not math.isnan(estimulo):
            return estimulo

        return self.puertos[pin]

    # ------------------------------------------------------------------
    # Métodos principales de diseño orientado a objetos
    # ------------------------------------------------------------------

    def configurarPuerto(self, puerto: int, sentido: int) -> None:
        """Configura la dirección operativa de un pin o canal.

        Args:
            puerto: Índice del pin digital (0-31) o canal analógico auxiliar (32-39).
            sentido: 0 para lectura/entrada, 1 para escritura/salida.

        Raises:
            ValueError: Si el puerto o el sentido están fuera de rango.
        """
        self._validar_canal(puerto, solo_digital=False)
        if sentido not in (self.MODO_LECTURA, self.MODO_ESCRITURA):
            raise ValueError(
                f"Sentido inválido: {sentido}. Use 0 (lectura/entrada) o 1 (escritura/salida)."
            )

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            self.sentidos[puerto] = sentido
            if puerto < self.TOTAL_PINES_DIGITALES and sentido == self.MODO_LECTURA:
                self._latches[puerto] = 1
                self.puertos[puerto] = self._resolver_voltaje_pin_digital(puerto)
            self._volcar_a_mmap_sin_bloqueo()

    def leerPuertoDigital(self, puerto: int) -> int:
        """Lee el nivel lógico (0 o 1) de uno de los 32 pines digitales del 8051.

        Args:
            puerto: Índice del pin digital (0-31).

        Returns:
            int: 1 si el voltaje del pin es >= 2.5 V, 0 en caso contrario.
        """
        self._validar_canal(puerto, solo_digital=True)

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            voltaje = self.puertos[puerto]
            return 1 if voltaje >= self.UMBRAL_LOGICO else 0

    def escribirPuertoDigital(self, puerto: int, valor: int) -> None:
        """Escribe un nivel lógico (0 o 1) en un pin digital configurado como salida.

        Si valor == 1 asigna estado alto (5.0 V); si valor == 0 asigna 0.0 V,
        validando previamente que el sentido del pin esté configurado en escritura (1).

        Args:
            puerto: Índice del pin digital (0-31).
            valor: Nivel lógico binario (0 o 1).

        Raises:
            ValueError: Si el pin es inválido, valor no es 0/1 o el sentido no es escritura.
        """
        self._validar_canal(puerto, solo_digital=True)
        if valor not in (0, 1) or isinstance(valor, bool):
            raise ValueError(f"Valor digital inválido: {valor}. Debe ser 0 o 1.")

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            if self.sentidos[puerto] != self.MODO_ESCRITURA:
                raise ValueError(
                    f"Operación denegada en pin {puerto}: el sentido actual es lectura (0). "
                    "Configure el pin en escritura (1) antes de escribir."
                )

            self._latches[puerto] = valor
            self.puertos[puerto] = self.VOLTAJE_ALTO if valor == 1 else self.VOLTAJE_BAJO
            self._volcar_a_mmap_sin_bloqueo()

    def leerPuertoAnalogico(self, puerto: int) -> float:
        """Lee el voltaje continuo (en voltios) de un pin o canal analógico auxiliar.

        Args:
            puerto: Índice del pin (0-31) o canal analógico auxiliar (32-39).

        Returns:
            float: Voltaje actual en el rango [0.0, 5.0].
        """
        self._validar_canal(puerto, solo_digital=False)

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            return round(float(self.puertos[puerto]), 4)

    def escribirPuertoAnalogico(self, puerto: int, valor: float) -> None:
        """Escribe un voltaje analógico continuo en el rango de 0.0 V a 5.0 V.

        Args:
            puerto: Índice del pin (0-31) o canal analógico auxiliar (32-39).
            valor: Voltaje en voltios dentro del intervalo [0.0, 5.0].

        Raises:
            ValueError: Si el voltaje excede [0.0, 5.0] o el canal no es de escritura.
        """
        self._validar_canal(puerto, solo_digital=False)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or math.isnan(valor):
            raise ValueError(f"Valor analógico inválido: {valor}.")

        voltaje = float(valor)
        if not (self.VOLTAJE_MIN <= voltaje <= self.VOLTAJE_MAX):
            raise ValueError(
                f"Voltaje fuera de rango: {voltaje} V. El rango permitido es 0.0 V a 5.0 V."
            )

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            if self.sentidos[puerto] != self.MODO_ESCRITURA:
                raise ValueError(
                    f"Operación denegada en canal {puerto}: el sentido actual es lectura (0). "
                    "Configure el canal en escritura (1) antes de escribir."
                )

            self.puertos[puerto] = voltaje
            if puerto < self.TOTAL_PINES_DIGITALES:
                self._latches[puerto] = 1 if voltaje >= self.UMBRAL_LOGICO else 0
            self._volcar_a_mmap_sin_bloqueo()

    # ------------------------------------------------------------------
    # Métodos auxiliares de puertos de 8 bits (Arquitectura 8051)
    # ------------------------------------------------------------------

    def leer_byte_puerto(self, num_puerto: int) -> int:
        """Lee el estado físico completo (8 bits) de un puerto del 8051 (P0-P3).

        Args:
            num_puerto: Número de puerto (0 = P0, 1 = P1, 2 = P2, 3 = P3).

        Returns:
            int: Byte sin signo (0x00 a 0xFF) correspondiente al estado de los 8 pines.
        """
        self._validar_num_puerto_8bit(num_puerto)
        pin_base = num_puerto * self.PINES_POR_PUERTO

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            resultado = 0
            for bit in range(self.PINES_POR_PUERTO):
                voltaje = self.puertos[pin_base + bit]
                if voltaje >= self.UMBRAL_LOGICO:
                    resultado |= 1 << bit
            return resultado

    def escribir_byte_puerto(self, num_puerto: int, byte_val: int) -> None:
        """Escribe un byte completo en un puerto del 8051 respetando su lógica quasi-bidireccional.

        Comportamiento hardware 8051 por cada bit:
          - Bit = 1: Escribe 1 en el latch, desactiva el transistor pull-down y
            configura el pin como entrada (sentido = 0) con pull-up a 5.0 V (salvo que
            un periférico externo lo fuerce a nivel bajo).
          - Bit = 0: Escribe 0 en el latch, activa el transistor pull-down y
            configura el pin como salida activa (sentido = 1) a 0.0 V.

        Args:
            num_puerto: Número de puerto (0 = P0, 1 = P1, 2 = P2, 3 = P3).
            byte_val: Valor de 8 bits (0x00 a 0xFF).
        """
        self._validar_num_puerto_8bit(num_puerto)
        if (
            not isinstance(byte_val, int)
            or isinstance(byte_val, bool)
            or not (0x00 <= byte_val <= 0xFF)
        ):
            raise ValueError(f"Valor de byte inválido: {byte_val}. Debe estar entre 0x00 y 0xFF.")

        pin_base = num_puerto * self.PINES_POR_PUERTO

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            for bit in range(self.PINES_POR_PUERTO):
                pin = pin_base + bit
                nivel = (byte_val >> bit) & 0x01
                self._latches[pin] = nivel

                if nivel == 1:
                    # En arquitectura 8051 escribir 1 habilita el pin como entrada quasi-bidireccional
                    self.sentidos[pin] = self.MODO_LECTURA
                    estimulo = self._estimulos_externos[pin]
                    self.puertos[pin] = (
                        estimulo if not math.isnan(estimulo) else self.VOLTAJE_ALTO
                    )
                else:
                    # Escribir 0 fuerza salida activa en estado bajo (0.0 V)
                    self.sentidos[pin] = self.MODO_ESCRITURA
                    self.puertos[pin] = self.VOLTAJE_BAJO

            self._volcar_a_mmap_sin_bloqueo()

    def leer_latch_puerto(self, num_puerto: int) -> int:
        """Retorna el valor almacenado en el registro latch interno de P0-P3.

        Útil para instrucciones de lectura-modificación-escritura del 8051
        (como ANL, ORL, XRL o CPL sobre SFRs de puerto).
        """
        self._validar_num_puerto_8bit(num_puerto)
        pin_base = num_puerto * self.PINES_POR_PUERTO

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            latch_byte = 0
            for bit in range(self.PINES_POR_PUERTO):
                if self._latches[pin_base + bit]:
                    latch_byte |= 1 << bit
            return latch_byte

    # ------------------------------------------------------------------
    # Interacción de periféricos externos (GUI DIP-40) y diagnóstico
    # ------------------------------------------------------------------

    def inyectar_estimulo_externo(self, puerto: int, valor: float | int) -> None:
        """Permite a la GUI o periféricos aplicar una señal externa sobre un canal de entrada.

        Args:
            puerto: Índice del pin (0-31) o canal analógico auxiliar (32-39).
            valor: Nivel lógico (0/1) o voltaje continuo (0.0 V a 5.0 V).
        """
        self._validar_canal(puerto, solo_digital=False)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or math.isnan(valor):
            raise ValueError(f"Estímulo externo inválido: {valor}.")

        voltaje = (
            self.VOLTAJE_ALTO
            if valor == 1
            else (self.VOLTAJE_BAJO if valor == 0 else float(valor))
        )
        if not (self.VOLTAJE_MIN <= voltaje <= self.VOLTAJE_MAX):
            raise ValueError(f"Voltaje externo fuera de rango [0.0, 5.0]: {voltaje} V.")

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            self._estimulos_externos[puerto] = voltaje
            # Solo altera el voltaje físico si el pin está en modo entrada (sentido == 0)
            if self.sentidos[puerto] == self.MODO_LECTURA:
                self.puertos[puerto] = voltaje
            self._volcar_a_mmap_sin_bloqueo()

    def liberar_estimulo_externo(self, puerto: int) -> None:
        """Desconecta el estímulo externo de un pin, restaurando su estado pull-up."""
        self._validar_canal(puerto, solo_digital=False)

        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            self._estimulos_externos[puerto] = float("nan")
            if puerto < self.TOTAL_PINES_DIGITALES and self.sentidos[puerto] == self.MODO_LECTURA:
                self.puertos[puerto] = self.VOLTAJE_ALTO
            elif self.sentidos[puerto] == self.MODO_LECTURA:
                self.puertos[puerto] = self.VOLTAJE_BAJO
            self._volcar_a_mmap_sin_bloqueo()

    def reset(self) -> None:
        """Restaura todos los pines y canales al estado inicial tras reset por hardware."""
        with self._bloqueo_exclusivo():
            self.puertos = [self.VOLTAJE_ALTO] * self.TOTAL_PINES_DIGITALES + [
                self.VOLTAJE_BAJO
            ] * self.CANALES_ANALOGICOS_AUX
            self.sentidos = [self.MODO_LECTURA] * self.TOTAL_CANALES
            self._latches = [1] * self.TOTAL_PINES_DIGITALES
            self._estimulos_externos = [float("nan")] * self.TOTAL_CANALES
            self._volcar_a_mmap_sin_bloqueo()

    def exportar_snapshot_json(self) -> str:
        """Serializa una instantánea legible del estado de puertos en formato JSON."""
        with self._bloqueo_exclusivo():
            self._cargar_desde_mmap_sin_bloqueo()
            snapshot = {
                "secuencia": self._secuencia,
                "puertos_byte": {
                    f"P{p}": f"0x{self.leer_byte_puerto(p):02X}"
                    for p in range(self.NUM_PUERTOS_DIGITALES)
                },
                "puertos_voltaje": self.puertos,
                "sentidos": self.sentidos,
            }
            return json.dumps(snapshot, indent=2)

    def close(self) -> None:
        """Libera de forma segura la proyección mmap y los descriptores de archivo."""
        with self._thread_lock:
            if self._mmap is not None:
                self._mmap.flush()
                self._mmap.close()
                self._mmap = None
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None

    def __enter__(self) -> ADM:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass