"""Interfaz de línea de comandos (CLI) y depurador interactivo para el núcleo AT89S51.

Ejecuta el microcontrolador 8051 estrictamente en modo consola sin dependencias
gráficas, sincronizando el estado de los puertos P0-P3 con procesos externos
exclusivamente a través de la capa ADM (memoria compartida mmap).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Sequence

from src.core.cpu import CPU8051
from src.ports.adm import ADM
from src.storage.memory import Memory8051


# Nombres simbólicos de SFRs para enriquecer el desensamblado en consola
SFR_NAMES: dict[int, str] = {
    0x80: "P0",
    0x81: "SP",
    0x82: "DPL",
    0x83: "DPH",
    0x87: "PCON",
    0x88: "TCON",
    0x89: "TMOD",
    0x8A: "TL0",
    0x8B: "TL1",
    0x8C: "TH0",
    0x8D: "TH1",
    0x90: "P1",
    0x98: "SCON",
    0x99: "SBUF",
    0xA0: "P2",
    0xA8: "IE",
    0xB0: "P3",
    0xB8: "IP",
    0xD0: "PSW",
    0xE0: "ACC",
    0xF0: "B",
}


def _format_direct_addr(addr: int) -> str:
    """Formatea una dirección directa (0x00-0xFF) incluyendo su alias SFR si existe."""
    nombre = SFR_NAMES.get(addr)
    if nombre is not None:
        return f"{nombre}(0x{addr:02X})"
    return f"0x{addr:02X}"


def _format_bit_addr(bit_addr: int) -> str:
    """Formatea una dirección de bit (0x00-0xFF) mostrando puerto/SFR y bit."""
    bit_pos = bit_addr & 0x07
    if bit_addr >= 0x80:
        sfr_base = bit_addr & 0xF8
        sfr_name = SFR_NAMES.get(sfr_base)
        if sfr_name is not None:
            return f"{sfr_name}.{bit_pos}(0x{bit_addr:02X})"
    return f"0x{bit_addr:02X}"


def _signed_byte(val: int) -> int:
    """Convierte un byte sin signo en desplazamiento relativo con signo (-128..+127)."""
    return val - 0x100 if val >= 0x80 else val


def disassemble_at(rom: bytearray, pc: int) -> tuple[str, list[int]]:
    """Decodifica el mnemónico 8051 y los bytes crudos ubicados en `pc`.

    Args:
        rom: Arreglo de memoria de programa (4 KB).
        pc: Dirección actual del contador de programa.

    Returns:
        tuple[str, list[int]]: (Mnemónico formateado, lista de bytes de la instrucción).
    """
    rom_len = len(rom)

    def rb(offset: int) -> int:
        addr = (pc + offset) & 0xFFFF
        return rom[addr] if addr < rom_len else 0xFF

    op = rb(0)
    b1 = rb(1)
    b2 = rb(2)

    def rel_target(instr_len: int, rel_val: int) -> int:
        return (pc + instr_len + _signed_byte(rel_val)) & 0xFFFF

    # Saltos y llamadas absolutas de 11 bits (AJMP / ACALL)
    if (op & 0x1F) == 0x01:
        target = ((pc + 2) & 0xF800) | ((op & 0xE0) << 3) | b1
        return f"AJMP 0x{target:04X}", [op, b1]
    if (op & 0x1F) == 0x11:
        target = ((pc + 2) & 0xF800) | ((op & 0xE0) << 3) | b1
        return f"ACALL 0x{target:04X}", [op, b1]

    # Tabla de decodificación completa del repertorio MCS-51
    if op == 0x00:
        return "NOP", [op]
    if op == 0x02:
        return f"LJMP 0x{(b1 << 8) | b2:04X}", [op, b1, b2]
    if op == 0x12:
        return f"LCALL 0x{(b1 << 8) | b2:04X}", [op, b1, b2]
    if op == 0x22:
        return "RET", [op]
    if op == 0x32:
        return "RETI", [op]
    if op == 0x03:
        return "RR A", [op]
    if op == 0x13:
        return "RRC A", [op]
    if op == 0x23:
        return "RL A", [op]
    if op == 0x33:
        return "RLC A", [op]

    # INC / DEC
    if op == 0x04:
        return "INC A", [op]
    if op == 0x05:
        return f"INC {_format_direct_addr(b1)}", [op, b1]
    if op in (0x06, 0x07):
        return f"INC @R{op & 1}", [op]
    if 0x08 <= op <= 0x0F:
        return f"INC R{op & 7}", [op]
    if op == 0xA3:
        return "INC DPTR", [op]

    if op == 0x14:
        return "DEC A", [op]
    if op == 0x15:
        return f"DEC {_format_direct_addr(b1)}", [op, b1]
    if op in (0x16, 0x17):
        return f"DEC @R{op & 1}", [op]
    if 0x18 <= op <= 0x1F:
        return f"DEC R{op & 7}", [op]

    # Saltos condicionales y relativos
    if op == 0x10:
        return f"JBC {_format_bit_addr(b1)}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if op == 0x20:
        return f"JB {_format_bit_addr(b1)}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if op == 0x30:
        return f"JNB {_format_bit_addr(b1)}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if op == 0x40:
        return f"JC 0x{rel_target(2, b1):04X}", [op, b1]
    if op == 0x50:
        return f"JNC 0x{rel_target(2, b1):04X}", [op, b1]
    if op == 0x60:
        return f"JZ 0x{rel_target(2, b1):04X}", [op, b1]
    if op == 0x70:
        return f"JNZ 0x{rel_target(2, b1):04X}", [op, b1]
    if op == 0x80:
        return f"SJMP 0x{rel_target(2, b1):04X}", [op, b1]
    if op == 0x73:
        return "JMP @A+DPTR", [op]

    # ADD / ADDC / SUBB
    for base, mnemonic in ((0x20, "ADD"), (0x30, "ADDC"), (0x90, "SUBB")):
        if op == base + 0x04:
            return f"{mnemonic} A, #0x{b1:02X}", [op, b1]
        if op == base + 0x05:
            return f"{mnemonic} A, {_format_direct_addr(b1)}", [op, b1]
        if op in (base + 0x06, base + 0x07):
            return f"{mnemonic} A, @R{op & 1}", [op]
        if (base + 0x08) <= op <= (base + 0x0F):
            return f"{mnemonic} A, R{op & 7}", [op]

    # ORL / ANL / XRL
    for base, mnemonic in ((0x40, "ORL"), (0x50, "ANL"), (0x60, "XRL")):
        if op == base + 0x02:
            return f"{mnemonic} {_format_direct_addr(b1)}, A", [op, b1]
        if op == base + 0x03:
            return f"{mnemonic} {_format_direct_addr(b1)}, #0x{b2:02X}", [op, b1, b2]
        if op == base + 0x04:
            return f"{mnemonic} A, #0x{b1:02X}", [op, b1]
        if op == base + 0x05:
            return f"{mnemonic} A, {_format_direct_addr(b1)}", [op, b1]
        if op in (base + 0x06, base + 0x07):
            return f"{mnemonic} A, @R{op & 1}", [op]
        if (base + 0x08) <= op <= (base + 0x0F):
            return f"{mnemonic} A, R{op & 7}", [op]

    # Operaciones booleanas sobre Carry y bits
    if op == 0x72:
        return f"ORL C, {_format_bit_addr(b1)}", [op, b1]
    if op == 0xA0:
        return f"ORL C, /{_format_bit_addr(b1)}", [op, b1]
    if op == 0x82:
        return f"ANL C, {_format_bit_addr(b1)}", [op, b1]
    if op == 0xB0:
        return f"ANL C, /{_format_bit_addr(b1)}", [op, b1]
    if op == 0x92:
        return f"MOV {_format_bit_addr(b1)}, C", [op, b1]
    if op == 0xA2:
        return f"MOV C, {_format_bit_addr(b1)}", [op, b1]
    if op == 0xB2:
        return f"CPL {_format_bit_addr(b1)}", [op, b1]
    if op == 0xB3:
        return "CPL C", [op]
    if op == 0xC2:
        return f"CLR {_format_bit_addr(b1)}", [op, b1]
    if op == 0xC3:
        return "CLR C", [op]
    if op == 0xD2:
        return f"SETB {_format_bit_addr(b1)}", [op, b1]
    if op == 0xD3:
        return "SETB C", [op]

    # Transferencia de datos MOV / MOVC / PUSH / POP / XCH
    if op == 0x74:
        return f"MOV A, #0x{b1:02X}", [op, b1]
    if op == 0x75:
        return f"MOV {_format_direct_addr(b1)}, #0x{b2:02X}", [op, b1, b2]
    if op in (0x76, 0x77):
        return f"MOV @R{op & 1}, #0x{b1:02X}", [op, b1]
    if 0x78 <= op <= 0x7F:
        return f"MOV R{op & 7}, #0x{b1:02X}", [op, b1]

    if op == 0x83:
        return "MOVC A, @A+PC", [op]
    if op == 0x93:
        return "MOVC A, @A+DPTR", [op]
    if op == 0x84:
        return "DIV AB", [op]
    if op == 0xA4:
        return "MUL AB", [op]
    if op == 0x85:
        return f"MOV {_format_direct_addr(b2)}, {_format_direct_addr(b1)}", [op, b1, b2]
    if op in (0x86, 0x87):
        return f"MOV {_format_direct_addr(b1)}, @R{op & 1}", [op, b1]
    if 0x88 <= op <= 0x8F:
        return f"MOV {_format_direct_addr(b1)}, R{op & 7}", [op, b1]
    if op == 0x90:
        return f"MOV DPTR, #0x{(b1 << 8) | b2:04X}", [op, b1, b2]
    if op in (0xA6, 0xA7):
        return f"MOV @R{op & 1}, {_format_direct_addr(b1)}", [op, b1]
    if 0xA8 <= op <= 0xAF:
        return f"MOV R{op & 7}, {_format_direct_addr(b1)}", [op, b1]

    if op == 0xC0:
        return f"PUSH {_format_direct_addr(b1)}", [op, b1]
    if op == 0xD0:
        return f"POP {_format_direct_addr(b1)}", [op, b1]
    if op == 0xC4:
        return "SWAP A", [op]
    if op == 0xC5:
        return f"XCH A, {_format_direct_addr(b1)}", [op, b1]
    if op in (0xC6, 0xC7):
        return f"XCH A, @R{op & 1}", [op]
    if 0xC8 <= op <= 0xCF:
        return f"XCH A, R{op & 7}", [op]

    if op == 0xE4:
        return "CLR A", [op]
    if op == 0xE5:
        return f"MOV A, {_format_direct_addr(b1)}", [op, b1]
    if op in (0xE6, 0xE7):
        return f"MOV A, @R{op & 1}", [op]
    if 0xE8 <= op <= 0xEF:
        return f"MOV A, R{op & 7}", [op]

    if op == 0xF4:
        return "CPL A", [op]
    if op == 0xF5:
        return f"MOV {_format_direct_addr(b1)}, A", [op, b1]
    if op in (0xF6, 0xF7):
        return f"MOV @R{op & 1}, A", [op]
    if 0xF8 <= op <= 0xFF:
        return f"MOV R{op & 7}, A", [op]

    # CJNE / DJNZ
    if op == 0xB4:
        return f"CJNE A, #0x{b1:02X}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if op == 0xB5:
        return f"CJNE A, {_format_direct_addr(b1)}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if op in (0xB6, 0xB7):
        return f"CJNE @R{op & 1}, #0x{b1:02X}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if 0xB8 <= op <= 0xBF:
        return f"CJNE R{op & 7}, #0x{b1:02X}, 0x{rel_target(3, b2):04X}", [op, b1, b2]

    if op == 0xD5:
        return f"DJNZ {_format_direct_addr(b1)}, 0x{rel_target(3, b2):04X}", [op, b1, b2]
    if 0xD8 <= op <= 0xDF:
        return f"DJNZ R{op & 7}, 0x{rel_target(2, b1):04X}", [op, b1]

    return f"DB 0x{op:02X}", [op]


class InteractiveDebugger8051:
    """Consola de depuración de bajo nivel para el núcleo AT89S51."""

    def __init__(self, cpu: CPU8051, cycle_delay: float = 0.0) -> None:
        self.cpu: CPU8051 = cpu
        self.cycle_delay: float = max(0.0, cycle_delay)
        self.breakpoints: set[int] = set()

    @staticmethod
    def _parse_int(token: str) -> int:
        """Convierte cadenas hexadecimales ('0x1A', '1A', '1Ah') o decimales a entero."""
        limpio = token.strip().lower()
        if limpio.endswith("h"):
            limpio = "0x" + limpio[:-1]
        if limpio.startswith("0x"):
            return int(limpio, 16)
        # Por defecto en depuración 8051 se interpretan direcciones en hexadecimal
        return int(limpio, 16)

    def format_registers(self) -> str:
        """Formatea el estado completo de registros internos, banderas PSW y banco R0-R7."""
        c = self.cpu
        psw = c.psw
        f0 = 1 if (psw & CPU8051.PSW_F0) else 0
        rs1 = 1 if (psw & CPU8051.PSW_RS1) else 0
        rs0 = 1 if (psw & CPU8051.PSW_RS0) else 0
        bank = c.memory.get_active_register_bank()

        regs_r = " ".join(
            f"R{i}:0x{c.memory.read_register(i):02X}" for i in range(8)
        )
        banderas = (
            f"[CY={c.carry} AC={c.aux_carry} F0={f0} "
            f"RS1={rs1} RS0={rs0}(B{bank}) OV={c.overflow} P={c.parity}]"
        )
        linea_1 = (
            f"  PC=0x{c.pc:04X} | A=0x{c.acc:02X} | B=0x{c.b_reg:02X} | "
            f"SP=0x{c.sp:02X} | DPTR=0x{c.dptr:04X} | Ciclos={c.total_cycles}"
        )
        linea_2 = f"  PSW=0x{psw:02X} {banderas}"
        linea_3 = f"  Banco {bank}: {regs_r}"
        return f"{linea_1}\n{linea_2}\n{linea_3}"

    def execute_single_step(self, verbose: bool = True) -> int:
        """Ejecuta una instrucción, aplica retardo por ciclos e imprime telemetría."""
        pc_antes = self.cpu.pc
        mnemonico, raw_bytes = disassemble_at(self.cpu.memory.rom, pc_antes)
        bytes_str = " ".join(f"{b:02X}" for b in raw_bytes)

        ciclos = self.cpu.step()

        if self.cycle_delay > 0.0:
            time.sleep(self.cycle_delay * ciclos)

        if verbose:
            print(
                f"[0x{pc_antes:04X}] {bytes_str:<9} -> {mnemonico:<24} "
                f"(+{ciclos} ciclo{'s' if ciclos > 1 else ''})"
            )
            print(self.format_registers())

        return ciclos

    def run_continuous(self, stop_on_breakpoints: bool = True) -> None:
        """Ejecuta instrucciones continuamente hasta encontrar un breakpoint o Ctrl+C."""
        print("Ejecutando núcleo AT89S51... Presione Ctrl+C para detener.")
        try:
            while True:
                if stop_on_breakpoints and self.cpu.pc in self.breakpoints:
                    print(f"\n[BREAKPOINT] Ejecución detenida en PC=0x{self.cpu.pc:04X}")
                    print(self.format_registers())
                    break

                ciclos = self.cpu.step()
                if self.cycle_delay > 0.0:
                    time.sleep(self.cycle_delay * ciclos)

        except KeyboardInterrupt:
            print(f"\n[PAUSA] Interrupción por teclado (Ctrl+C) en PC=0x{self.cpu.pc:04X}")
            print(self.format_registers())
        except NotImplementedError as exc:
            print(f"\n[ERROR ISA] {exc}")
            print(self.format_registers())

    def cmd_break(self, args: list[str]) -> None:
        """Agrega o elimina un breakpoint en una dirección de programa."""
        if not args:
            if not self.breakpoints:
                print("No hay breakpoints activos. Uso: break <addr_hex>")
            else:
                lista = ", ".join(f"0x{addr:04X}" for addr in sorted(self.breakpoints))
                print(f"Breakpoints activos: {lista}")
            return

        try:
            addr = self._parse_int(args[0])
        except ValueError:
            print(f"Dirección hexadecimal inválida: '{args[0]}'.")
            return

        if not (0x0000 <= addr < Memory8051.ROM_SIZE):
            print(f"Dirección fuera de rango ROM (0x0000 - 0x{Memory8051.ROM_SIZE - 1:04X}).")
            return

        if addr in self.breakpoints:
            self.breakpoints.remove(addr)
            print(f"Breakpoint eliminado en 0x{addr:04X}.")
        else:
            self.breakpoints.add(addr)
            print(f"Breakpoint agregado en 0x{addr:04X}.")

    def cmd_ports(self) -> None:
        """Lee y muestra el estado binario y hexadecimal actual de P0-P3 desde ADM."""
        print("Estado actual de puertos en ADM (Pines físicos / Latch):")
        for idx in range(4):
            val_pin = self.cpu.adm.leer_byte_puerto(idx)
            val_latch = self.cpu.adm.leer_latch_puerto(idx)
            print(
                f"  P{idx}: Pin=0x{val_pin:02X} (0b{val_pin:08b}) | "
                f"Latch=0x{val_latch:02X} (0b{val_latch:08b})"
            )

    def cmd_stack(self) -> None:
        """Muestra el contenido actual de la pila desde 0x08 hasta SP."""
        sp = self.cpu.sp
        print(f"Puntero de Pila actual: SP=0x{sp:02X}")
        if sp < 0x08:
            print("  (Pila vacía: SP se encuentra en su posición inicial 0x07 o inferior)")
            return

        limite = min(sp, Memory8051.RAM_SIZE - 1)
        for addr in range(0x08, limite + 1):
            val = self.cpu.memory.ram[addr]
            marcador = " <-- SP (cima)" if addr == sp else ""
            print(f"  [0x{addr:02X}] = 0x{val:02X} (0b{val:08b}){marcador}")

    def cmd_ram(self, args: list[str]) -> None:
        """Inspecciona un rango de la memoria RAM interna (0x00 - 0x7F)."""
        if len(args) != 2:
            print("Uso: ram <inicio_hex> <fin_hex>  (ej. ram 0x00 0x2F)")
            return

        try:
            inicio = self._parse_int(args[0])
            fin = self._parse_int(args[1])
        except ValueError:
            print("Las direcciones de inicio y fin deben ser valores hexadecimales válidos.")
            return

        if not (0x00 <= inicio <= fin < Memory8051.RAM_SIZE):
            print(
                f"Rango inválido. Se requiere 0x00 <= inicio <= fin <= 0x{Memory8051.RAM_SIZE - 1:02X}."
            )
            return

        print(f"Volcado RAM Interna [0x{inicio:02X} .. 0x{fin:02X}]:")
        for base in range(inicio, fin + 1, 16):
            fila = self.cpu.memory.ram[base : min(base + 16, fin + 1)]
            hex_cols = " ".join(f"{b:02X}" for b in fila)
            ascii_cols = "".join(chr(b) if 32 <= b <= 126 else "." for b in fila)
            print(f"  0x{base:02X}: {hex_cols:<47} |{ascii_cols}|")

    def cmd_reset(self) -> None:
        """Reinicia el microcontrolador y sincroniza ADM."""
        self.cpu.reset()
        print("Microcontrolador AT89S51 reiniciado (PC=0x0000, SP=0x07, Puertos=0xFF).")
        print(self.format_registers())

    @staticmethod
    def print_help() -> None:
        """Imprime el resumen de comandos de consola disponibles."""
        print(
            "Comandos disponibles:\n"
            "  step | s               Ejecuta 1 instrucción y muestra registros/banderas\n"
            "  run  | r               Ejecuta continuamente hasta breakpoint o Ctrl+C\n"
            "  break | b <addr_hex>   Agrega o elimina un breakpoint (ej. b 0x000A)\n"
            "  ports | p              Muestra el estado de P0, P1, P2 y P3 desde ADM\n"
            "  stack                  Muestra la pila desde 0x08 hasta SP\n"
            "  ram <inicio> <fin>     Inspecciona un rango de RAM interna (ej. ram 00 1F)\n"
            "  reset                  Reinicia la CPU y actualiza la capa ADM\n"
            "  help | h               Muestra esta ayuda\n"
            "  quit | q               Cierra la sesión y libera memoria compartida"
        )

    def repl(self) -> None:
        """Bucle principal de lectura-evaluación-impresión (REPL) del depurador."""
        print("=== Depurador Interactivo AT89S51 (Modo Consola) ===")
        print("Escriba 'help' para ver los comandos disponibles.")
        print(self.format_registers())

        while True:
            try:
                raw_cmd = input(f"\n(8051 @ 0x{self.cpu.pc:04X})> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nSaliendo del depurador...")
                break

            if not raw_cmd:
                continue

            parts = raw_cmd.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("step", "s"):
                try:
                    self.execute_single_step(verbose=True)
                except NotImplementedError as exc:
                    print(f"[ERROR ISA] {exc}")
            elif cmd in ("run", "r"):
                self.run_continuous(stop_on_breakpoints=True)
            elif cmd in ("break", "b"):
                self.cmd_break(args)
            elif cmd in ("ports", "p"):
                self.cmd_ports()
            elif cmd == "stack":
                self.cmd_stack()
            elif cmd == "ram":
                self.cmd_ram(args)
            elif cmd == "reset":
                self.cmd_reset()
            elif cmd in ("help", "h", "?"):
                self.print_help()
            elif cmd in ("quit", "q", "exit"):
                print("Finalizando emulación y liberando recursos ADM...")
                break
            else:
                print(f"Comando desconocido: '{cmd}'. Escriba 'help' para listar opciones.")


def build_parser() -> argparse.ArgumentParser:
    """Construye el analizador de argumentos CLI para el núcleo AT89S51."""
    parser = argparse.ArgumentParser(
        prog="at89s51-cli",
        description="Núcleo de emulación del microcontrolador Atmel/Microchip AT89S51 (CLI).",
    )

    prog_group = parser.add_mutually_exclusive_group(required=False)
    prog_group.add_argument(
        "--hex",
        type=Path,
        metavar="RUTA_HEX",
        help="Ruta al archivo de programa en formato Intel HEX (.hex).",
    )
    prog_group.add_argument(
        "--bin",
        type=Path,
        metavar="RUTA_BIN",
        help="Ruta al archivo binario crudo (.bin) para cargar en ROM.",
    )

    parser.add_argument(
        "--base-addr",
        type=lambda x: int(x, 0),
        default=0x0000,
        metavar="ADDR",
        help="Dirección inicial de carga en ROM para archivos --bin (por defecto: 0x0000).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        metavar="SEGUNDOS",
        help="Retardo en segundos por ciclo máquina para observar cambios en ADM en tiempo real.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(".state/ports_state.bin"),
        metavar="ARCHIVO_MMAP",
        help="Ruta al archivo compartido mmap de ADM (por defecto: .state/ports_state.bin).",
    )

    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument(
        "--run",
        action="store_true",
        help="Inicia directamente en modo ejecución continua hasta Ctrl+C.",
    )
    mode_group.add_argument(
        "--debug",
        action="store_true",
        help="Inicia en modo depuración interactiva paso a paso (por defecto).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada principal del proceso CLI del núcleo 8051."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.delay < 0:
        parser.error("El parámetro --delay debe ser mayor o igual a 0.0 segundos.")

    with ADM(state_file=args.state_file) as adm:
        memoria = Memory8051(adm=adm)
        cpu = CPU8051(memory=memoria)
        cpu.reset()

        try:
            if args.hex is not None:
                cargados = memoria.load_hex(args.hex)
                print(f"[ROM] Cargados {cargados} bytes desde Intel HEX: {args.hex}")
            elif args.bin is not None:
                cargados = memoria.load_binary(args.bin, base_address=args.base_addr)
                print(
                    f"[ROM] Cargados {cargados} bytes desde binario: {args.bin} "
                    f"(base 0x{args.base_addr:04X})"
                )
            else:
                print("[ROM] Sin archivo cargado. Memoria de programa inicializada en 0x00 (NOP).")
        except (OSError, ValueError) as exc:
            print(f"[ERROR DE CARGA] No se pudo cargar el programa en ROM: {exc}", file=sys.stderr)
            return 1

        depurador = InteractiveDebugger8051(cpu=cpu, cycle_delay=args.delay)

        if args.run:
            depurador.run_continuous(stop_on_breakpoints=False)
        else:
            depurador.repl()

    return 0


if __name__ == "__main__":
    sys.exit(main())