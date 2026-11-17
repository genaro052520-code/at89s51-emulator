"""Subsistema de memoria Harvard del microcontrolador Atmel/Microchip AT89S51.

Implementa:
  - Memoria de Programa (Flash ROM): 4096 bytes (0x0000 - 0x0FFF) con cargadores
    para archivos Intel HEX (.hex) y binarios crudos (.bin).
  - Memoria de Datos Interna (RAM): 128 bytes (0x00 - 0x7F) con soporte para los
    4 bancos de registros R0-R7, área direccionable por bit (0x20 - 0x2F) y pila.
  - Registros de Funciones Especiales (SFRs, 0x80 - 0xFF) con sincronización
    automática de los puertos P0, P1, P2 y P3 contra la capa ADM.
"""

from __future__ import annotations

from pathlib import Path
from src.ports.adm import ADM


class Memory8051:
    """Gestiona los espacios de direcciones de programa, datos internos y SFRs."""

    ROM_SIZE: int = 4096  # 4 KB (0x0000 - 0x0FFF)
    RAM_SIZE: int = 128   # 128 B (0x00 - 0x7F)

    # Direcciones de Registros de Funciones Especiales (SFRs)
    SFR_P0: int = 0x80
    SFR_SP: int = 0x81
    SFR_DPL: int = 0x82
    SFR_DPH: int = 0x83
    SFR_PCON: int = 0x87
    SFR_TCON: int = 0x88
    SFR_TMOD: int = 0x89
    SFR_TL0: int = 0x8A
    SFR_TL1: int = 0x8B
    SFR_TH0: int = 0x8C
    SFR_TH1: int = 0x8D
    SFR_P1: int = 0x90
    SFR_SCON: int = 0x98
    SFR_SBUF: int = 0x99
    SFR_P2: int = 0xA0
    SFR_IE: int = 0xA8
    SFR_P3: int = 0xB0
    SFR_IP: int = 0xB8
    SFR_PSW: int = 0xD0
    SFR_ACC: int = 0xE0
    SFR_B: int = 0xF0

    # Mapa de SFRs correspondientes a los 4 puertos bidireccionales de 8 bits
    PORT_SFR_TO_INDEX: dict[int, int] = {
        SFR_P0: 0,
        SFR_P1: 1,
        SFR_P2: 2,
        SFR_P3: 3,
    }

    # Valores por defecto tras un reset por hardware del AT89S51
    DEFAULT_SFR_VALUES: dict[int, int] = {
        SFR_P0: 0xFF,
        SFR_SP: 0x07,
        SFR_DPL: 0x00,
        SFR_DPH: 0x00,
        SFR_PCON: 0x00,
        SFR_TCON: 0x00,
        SFR_TMOD: 0x00,
        SFR_TL0: 0x00,
        SFR_TL1: 0x00,
        SFR_TH0: 0x00,
        SFR_TH1: 0x00,
        SFR_P1: 0xFF,
        SFR_SCON: 0x00,
        SFR_SBUF: 0x00,
        SFR_P2: 0xFF,
        SFR_IE: 0x00,
        SFR_P3: 0xFF,
        SFR_IP: 0x00,
        SFR_PSW: 0x00,
        SFR_ACC: 0x00,
        SFR_B: 0x00,
    }

    def __init__(self, adm: ADM) -> None:
        """Inicializa las memorias Harvard y enlaza la capa de puertos ADM.

        Args:
            adm: Instancia activa de ADM para sincronizar P0-P3.
        """
        self.adm: ADM = adm
        self.rom: bytearray = bytearray(self.ROM_SIZE)
        self.ram: bytearray = bytearray(self.RAM_SIZE)
        self.sfr: dict[int, int] = {}
        self.reset_data_memory()

    def reset_data_memory(self) -> None:
        """Limpia la RAM interna y restaura los SFRs y puertos a su estado de reset."""
        self.ram[:] = bytes(self.RAM_SIZE)
        self.sfr = dict(self.DEFAULT_SFR_VALUES)
        self.adm.reset()

    def clear_rom(self) -> None:
        """Borra la memoria Flash ROM interna (rellena con 0xFF como Flash virgen)."""
        self.rom[:] = b"\xFF" * self.ROM_SIZE

    # ------------------------------------------------------------------
    # Memoria de Programa (ROM / Flash 4 KB) y Cargadores de Firmware
    # ------------------------------------------------------------------

    def read_rom(self, address: int) -> int:
        """Lee un byte de la memoria de programa (0x0000 - 0x0FFF)."""
        addr = address & 0xFFFF
        if addr >= self.ROM_SIZE:
            raise IndexError(
                f"Dirección de ROM fuera de rango: 0x{addr:04X} (máximo 0x{self.ROM_SIZE - 1:04X})."
            )
        return self.rom[addr]

    def load_binary(self, file_path: Path | str, base_address: int = 0x0000) -> int:
        """Carga un archivo binario crudo (.bin) en la memoria ROM.

        Args:
            file_path: Ruta al archivo .bin.
            base_address: Dirección inicial de carga en ROM (por defecto 0x0000).

        Returns:
            int: Cantidad de bytes cargados en ROM.
        """
        path = Path(file_path)
        data = path.read_bytes()
        if base_address < 0 or base_address + len(data) > self.ROM_SIZE:
            raise ValueError(
                f"El binario ({len(data)} bytes en 0x{base_address:04X}) excede los 4 KB de ROM."
            )

        self.clear_rom()
        self.rom[base_address : base_address + len(data)] = data
        return len(data)

    def load_hex(self, file_path: Path | str) -> int:
        """Parsea y carga un archivo en formato Intel HEX (.hex) en la ROM de 4 KB.

        Soporta registros de datos (00), fin de archivo (01), dirección extendida
        de segmento (02) y dirección lineal extendida (04), validando el checksum
        de dos complementos de cada línea.

        Args:
            file_path: Ruta al archivo .hex.

        Returns:
            int: Total de bytes de código escritos en la memoria de programa.
        """
        path = Path(file_path)
        lines = path.read_text(encoding="utf-8").splitlines()

        self.clear_rom()
        extended_base = 0
        bytes_loaded = 0
        eof_found = False

        for line_num, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise ValueError(f"Línea {line_num}: formato Intel HEX inválido (falta ':').")

            hex_content = line[1:]
            if len(hex_content) < 10 or len(hex_content) % 2 != 0:
                raise ValueError(f"Línea {line_num}: longitud de registro Intel HEX inválida.")

            try:
                record_bytes = bytes.fromhex(hex_content)
            except ValueError as exc:
                raise ValueError(f"Línea {line_num}: caracteres hexadecimales inválidos.") from exc

            # Verificación de checksum Intel HEX: suma de todos los bytes mod 256 == 0
            if (sum(record_bytes) & 0xFF) != 0:
                raise ValueError(f"Línea {line_num}: error de checksum en archivo Intel HEX.")

            byte_count = record_bytes[0]
            offset = (record_bytes[1] << 8) | record_bytes[2]
            record_type = record_bytes[3]
            payload = record_bytes[4:-1]

            if len(payload) != byte_count:
                raise ValueError(
                    f"Línea {line_num}: el conteo de bytes ({byte_count}) no coincide con los datos."
                )

            if record_type == 0x00:  # Registro de datos
                for idx, value in enumerate(payload):
                    target_addr = extended_base + offset + idx
                    if target_addr >= self.ROM_SIZE:
                        raise ValueError(
                            f"Línea {line_num}: dirección 0x{target_addr:04X} excede la ROM de 4 KB."
                        )
                    self.rom[target_addr] = value
                    bytes_loaded += 1
            elif record_type == 0x01:  # Fin de archivo (EOF)
                eof_found = True
                break
            elif record_type == 0x02:  # Dirección de segmento extendida
                if byte_count != 2:
                    raise ValueError(f"Línea {line_num}: registro tipo 02 requiere 2 bytes.")
                extended_base = ((payload[0] << 8) | payload[1]) << 4
            elif record_type == 0x04:  # Dirección lineal extendida
                if byte_count != 2:
                    raise ValueError(f"Línea {line_num}: registro tipo 04 requiere 2 bytes.")
                extended_base = ((payload[0] << 8) | payload[1]) << 16
            elif record_type in (0x03, 0x05):  # Registros de dirección de inicio (CS:IP / EIP)
                continue
            else:
                raise ValueError(
                    f"Línea {line_num}: tipo de registro Intel HEX no soportado (0x{record_type:02X})."
                )

        if not eof_found:
            raise ValueError("El archivo Intel HEX no contiene registro de fin de archivo (:00000001FF).")

        return bytes_loaded

    # ------------------------------------------------------------------
    # Bancos de Registros (R0 - R7) y Paridad de ACC
    # ------------------------------------------------------------------

    def get_active_register_bank(self) -> int:
        """Retorna el banco activo (0 a 3) según los bits RS1 (PSW.4) y RS0 (PSW.3)."""
        psw = self.sfr[self.SFR_PSW]
        return (psw >> 3) & 0x03

    def read_register(self, reg_index: int) -> int:
        """Lee un registro Rn (R0-R7) del banco actualmente seleccionado en PSW."""
        if not (0 <= reg_index <= 7):
            raise ValueError(f"Índice de registro inválido: R{reg_index}.")
        bank_offset = self.get_active_register_bank() * 8
        return self.ram[bank_offset + reg_index]

    def write_register(self, reg_index: int, value: int) -> None:
        """Escribe un byte en el registro Rn (R0-R7) del banco activo."""
        if not (0 <= reg_index <= 7):
            raise ValueError(f"Índice de registro inválido: R{reg_index}.")
        bank_offset = self.get_active_register_bank() * 8
        self.ram[bank_offset + reg_index] = value & 0xFF

    def _update_accumulator_parity(self) -> None:
        """Actualiza PSW.0 (P): 1 si ACC tiene número impar de bits en 1, 0 si es par."""
        acc = self.sfr[self.SFR_ACC]
        parity = bin(acc).count("1") & 0x01
        if parity:
            self.sfr[self.SFR_PSW] |= 0x01
        else:
            self.sfr[self.SFR_PSW] &= ~0x01

    # ------------------------------------------------------------------
    # Direccionamiento Directo (RAM 0x00-0x7F y SFRs 0x80-0xFF)
    # ------------------------------------------------------------------

    def read_direct(self, address: int, read_latch: bool = False) -> int:
        """Lee un byte mediante direccionamiento directo (0x00-0x7F RAM, 0x80-0xFF SFR).

        Args:
            address: Dirección directa de 8 bits.
            read_latch: Si es True y la dirección corresponde a P0-P3, retorna el valor
                del latch interno en lugar del estado eléctrico físico de los pines
                (comportamiento hardware para instrucciones Read-Modify-Write).
        """
        addr = address & 0xFF
        if addr < self.RAM_SIZE:
            return self.ram[addr]

        if addr in self.PORT_SFR_TO_INDEX:
            port_idx = self.PORT_SFR_TO_INDEX[addr]
            valor = (
                self.adm.leer_latch_puerto(port_idx)
                if read_latch
                else self.adm.leer_byte_puerto(port_idx)
            )
            self.sfr[addr] = valor
            return valor

        return self.sfr.get(addr, 0x00)

    def write_direct(self, address: int, value: int) -> None:
        """Escribe un byte mediante direccionamiento directo (0x00-0x7F RAM, 0x80-0xFF SFR)."""
        addr = address & 0xFF
        val = value & 0xFF

        if addr < self.RAM_SIZE:
            self.ram[addr] = val
            return

        self.sfr[addr] = val

        if addr in self.PORT_SFR_TO_INDEX:
            port_idx = self.PORT_SFR_TO_INDEX[addr]
            self.adm.escribir_byte_puerto(port_idx, val)
        elif addr == self.SFR_ACC:
            self._update_accumulator_parity()

    # ------------------------------------------------------------------
    # Direccionamiento Indirecto (@R0, @R1) y Pila (Stack)
    # ------------------------------------------------------------------

    def read_indirect(self, address: int) -> int:
        """Lee de la RAM interna mediante direccionamiento indirecto (@Ri o POP)."""
        addr = address & 0x7F
        return self.ram[addr]

    def write_indirect(self, address: int, value: int) -> None:
        """Escribe en la RAM interna mediante direccionamiento indirecto (@Ri o PUSH)."""
        addr = address & 0x7F
        self.ram[addr] = value & 0xFF

    def push_byte(self, value: int) -> None:
        """Incrementa SP y almacena un byte en la pila interna."""
        sp = (self.sfr[self.SFR_SP] + 1) & 0xFF
        self.sfr[self.SFR_SP] = sp
        self.write_indirect(sp, value & 0xFF)

    def pop_byte(self) -> int:
        """Extrae un byte desde la cima de la pila y decrementa SP."""
        sp = self.sfr[self.SFR_SP]
        val = self.read_indirect(sp)
        self.sfr[self.SFR_SP] = (sp - 1) & 0xFF
        return val

    # ------------------------------------------------------------------
    # Direccionamiento Bit a Bit (RAM 0x00-0x7F y SFRs 0x80-0xFF)
    # ------------------------------------------------------------------

    def _resolve_bit_location(self, bit_address: int) -> tuple[int, int]:
        """Convierte una dirección de bit (0x00-0xFF) en (dirección_byte, número_bit 0-7)."""
        b_addr = bit_address & 0xFF
        bit_pos = b_addr & 0x07
        if b_addr < 0x80:
            # Bits 0x00-0x7F corresponden a los bytes 0x20-0x2F de la RAM interna
            byte_addr = 0x20 + (b_addr >> 3)
        else:
            # Bits 0x80-0xFF corresponden a SFRs cuyas direcciones son múltiplos de 8
            byte_addr = b_addr & 0xF8
        return byte_addr, bit_pos

    def read_bit(self, bit_address: int, read_latch: bool = False) -> int:
        """Lee el valor lógico (0 o 1) de un bit direccionable en RAM o SFR."""
        byte_addr, bit_pos = self._resolve_bit_location(bit_address)
        byte_val = self.read_direct(byte_addr, read_latch=read_latch)
        return (byte_val >> bit_pos) & 0x01

    def write_bit(self, bit_address: int, value: int) -> None:
        """Escribe un valor lógico (0 o 1) en un bit direccionable de RAM o SFR."""
        byte_addr, bit_pos = self._resolve_bit_location(bit_address)
        # En puertos I/O, modificar un bit preserva los latches de los otros 7 bits
        current = self.read_direct(byte_addr, read_latch=True)
        if value & 0x01:
            updated = current | (1 << bit_pos)
        else:
            updated = current & ~(1 << bit_pos)
        self.write_direct(byte_addr, updated)