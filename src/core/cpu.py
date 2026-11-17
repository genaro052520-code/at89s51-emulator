"""Núcleo de ejecución (CPU y ALU) del microcontrolador Atmel/Microchip AT89S51.

Implementa el ciclo Fetch-Decode-Execute, el contador de programa (PC de 16 bits),
las banderas de estado de la ALU en PSW (CY, AC, OV, P) y el repertorio de
instrucciones (ISA 8051) con conteo exacto de ciclos máquina (1, 2 o 4 ciclos).
"""

from __future__ import annotations

from src.ports.adm import ADM
from src.storage.memory import Memory8051


class CPU8051:
    """Unidad Central de Procesamiento (CPU) y ALU de 8 bits del AT89S51."""

    # Máscaras de bits del registro PSW (0xD0)
    PSW_CY: int = 0x80   # Bit 7: Carry
    PSW_AC: int = 0x40   # Bit 6: Auxiliary Carry
    PSW_F0: int = 0x20   # Bit 5: Flag 0 de usuario
    PSW_RS1: int = 0x10  # Bit 4: Selector de banco de registros 1
    PSW_RS0: int = 0x08  # Bit 3: Selector de banco de registros 0
    PSW_OV: int = 0x04   # Bit 2: Overflow aritmético con signo
    PSW_P: int = 0x01    # Bit 0: Paridad del acumulador ACC

    def __init__(self, memory: Memory8051 | None = None, adm: ADM | None = None) -> None:
        """Inicializa la CPU conectada a la memoria Harvard y la capa ADM.

        Args:
            memory: Instancia opcional de Memory8051. Si no se provee, se crea una.
            adm: Instancia opcional de ADM si no se pasa `memory`.
        """
        if memory is not None:
            self.memory: Memory8051 = memory
            self.adm: ADM = memory.adm
        else:
            self.adm = adm if adm is not None else ADM()
            self.memory = Memory8051(self.adm)

        self.pc: int = 0x0000
        self.total_cycles: int = 0
        self.last_opcode: int = 0x00

    # ------------------------------------------------------------------
    # Propiedades auxiliares de registros y banderas PSW
    # ------------------------------------------------------------------

    @property
    def acc(self) -> int:
        return self.memory.sfr[Memory8051.SFR_ACC]

    @acc.setter
    def acc(self, value: int) -> None:
        self.memory.write_direct(Memory8051.SFR_ACC, value & 0xFF)

    @property
    def b_reg(self) -> int:
        return self.memory.sfr[Memory8051.SFR_B]

    @b_reg.setter
    def b_reg(self, value: int) -> None:
        self.memory.sfr[Memory8051.SFR_B] = value & 0xFF

    @property
    def psw(self) -> int:
        return self.memory.sfr[Memory8051.SFR_PSW]

    @psw.setter
    def psw(self, value: int) -> None:
        self.memory.sfr[Memory8051.SFR_PSW] = value & 0xFF
        self.memory._update_accumulator_parity()

    @property
    def sp(self) -> int:
        return self.memory.sfr[Memory8051.SFR_SP]

    @sp.setter
    def sp(self, value: int) -> None:
        self.memory.sfr[Memory8051.SFR_SP] = value & 0xFF

    @property
    def dptr(self) -> int:
        return (self.memory.sfr[Memory8051.SFR_DPH] << 8) | self.memory.sfr[Memory8051.SFR_DPL]

    @dptr.setter
    def dptr(self, value: int) -> None:
        val16 = value & 0xFFFF
        self.memory.sfr[Memory8051.SFR_DPH] = (val16 >> 8) & 0xFF
        self.memory.sfr[Memory8051.SFR_DPL] = val16 & 0xFF

    @property
    def carry(self) -> int:
        return 1 if (self.psw & self.PSW_CY) else 0

    @carry.setter
    def carry(self, bit: int) -> None:
        if bit & 0x01:
            self.memory.sfr[Memory8051.SFR_PSW] |= self.PSW_CY
        else:
            self.memory.sfr[Memory8051.SFR_PSW] &= ~self.PSW_CY

    @property
    def aux_carry(self) -> int:
        return 1 if (self.psw & self.PSW_AC) else 0

    @aux_carry.setter
    def aux_carry(self, bit: int) -> None:
        if bit & 0x01:
            self.memory.sfr[Memory8051.SFR_PSW] |= self.PSW_AC
        else:
            self.memory.sfr[Memory8051.SFR_PSW] &= ~self.PSW_AC

    @property
    def overflow(self) -> int:
        return 1 if (self.psw & self.PSW_OV) else 0

    @overflow.setter
    def overflow(self, bit: int) -> None:
        if bit & 0x01:
            self.memory.sfr[Memory8051.SFR_PSW] |= self.PSW_OV
        else:
            self.memory.sfr[Memory8051.SFR_PSW] &= ~self.PSW_OV

    @property
    def parity(self) -> int:
        return 1 if (self.psw & self.PSW_P) else 0

    # ------------------------------------------------------------------
    # Control de Reset y Ciclo Fetch-Decode-Execute
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reinicia PC a 0x0000, SP a 0x07, SFRs y puertos a sus valores por defecto."""
        self.pc = 0x0000
        self.total_cycles = 0
        self.last_opcode = 0x00
        self.memory.reset_data_memory()

    def _fetch_byte(self) -> int:
        """Obtiene el siguiente byte desde ROM apuntado por PC e incrementa PC."""
        byte = self.memory.read_rom(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return byte

    @staticmethod
    def _signed_offset(byte_val: int) -> int:
        """Convierte un desplazamiento relativo de 8 bits en complemento a dos (-128..+127)."""
        return byte_val - 0x100 if byte_val >= 0x80 else byte_val

    def _jump_relative(self, rel_byte: int) -> None:
        """Aplica un salto relativo respecto al PC actual (después de fetch)."""
        offset = self._signed_offset(rel_byte)
        self.pc = (self.pc + offset) & 0xFFFF

    # ------------------------------------------------------------------
    # Operaciones Primitivas de la ALU (Actualización de CY, AC, OV, P)
    # ------------------------------------------------------------------

    def _alu_add(self, operand: int, with_carry: bool = False) -> None:
        """Ejecuta ADD o ADDC sobre ACC actualizando CY, AC, OV y P."""
        a = self.acc
        op = operand & 0xFF
        c_in = self.carry if with_carry else 0

        total = a + op + c_in
        result = total & 0xFF

        self.carry = 1 if total > 0xFF else 0
        self.aux_carry = 1 if ((a & 0x0F) + (op & 0x0F) + c_in) > 0x0F else 0
        self.overflow = 1 if ((a ^ result) & (op ^ result) & 0x80) != 0 else 0
        self.acc = result

    def _alu_subb(self, operand: int) -> None:
        """Ejecuta SUBB A, operand (A - operand - CY) actualizando CY, AC, OV y P."""
        a = self.acc
        op = operand & 0xFF
        borrow_in = self.carry

        diff = a - op - borrow_in
        result = diff & 0xFF

        self.carry = 1 if diff < 0 else 0
        self.aux_carry = 1 if ((a & 0x0F) - (op & 0x0F) - borrow_in) < 0 else 0
        self.overflow = 1 if ((a ^ op) & (a ^ result) & 0x80) != 0 else 0
        self.acc = result

    # ------------------------------------------------------------------
    # Ejecución de Instrucciones (ISA 8051)
    # ------------------------------------------------------------------

    def step(self) -> int:
        """Ejecuta un ciclo completo Fetch-Decode-Execute de una instrucción 8051.

        Returns:
            int: Cantidad de ciclos máquina consumidos por la instrucción (1, 2 o 4).
        """
        opcode = self._fetch_byte()
        self.last_opcode = opcode
        cycles = self._decode_and_execute(opcode)
        self.total_cycles += cycles
        return cycles

    def run(self, max_instructions: int = 1000) -> int:
        """Ejecuta hasta `max_instructions` instrucciones consecutivas.

        Returns:
            int: Ciclos máquina totales acumulados durante la ráfaga.
        """
        cycles_spent = 0
        for _ in range(max_instructions):
            cycles_spent += self.step()
        return cycles_spent

    def _decode_and_execute(self, opcode: int) -> int:
        """Decodifica el opcode de 8 bits, ejecuta la operación y devuelve ciclos máquina."""
        # --- NOP ---
        if opcode == 0x00:
            return 1

        # --- Saltos y Llamadas Absolutas de 11 bits: AJMP (xxx00001) y ACALL (xxx10001) ---
        if (opcode & 0x1F) == 0x01:
            low8 = self._fetch_byte()
            target = (self.pc & 0xF800) | ((opcode & 0xE0) << 3) | low8
            self.pc = target
            return 2

        if (opcode & 0x1F) == 0x11:
            low8 = self._fetch_byte()
            target = (self.pc & 0xF800) | ((opcode & 0xE0) << 3) | low8
            self.memory.push_byte(self.pc & 0xFF)
            self.memory.push_byte((self.pc >> 8) & 0xFF)
            self.pc = target
            return 2

        # --- Saltos Largos y Subrutinas (16 bits) ---
        if opcode == 0x02:  # LJMP addr16
            hi = self._fetch_byte()
            lo = self._fetch_byte()
            self.pc = (hi << 8) | lo
            return 2

        if opcode == 0x12:  # LCALL addr16
            hi = self._fetch_byte()
            lo = self._fetch_byte()
            self.memory.push_byte(self.pc & 0xFF)
            self.memory.push_byte((self.pc >> 8) & 0xFF)
            self.pc = (hi << 8) | lo
            return 2

        if opcode in (0x22, 0x32):  # RET / RETI
            hi = self.memory.pop_byte()
            lo = self.memory.pop_byte()
            self.pc = (hi << 8) | lo
            return 2

        if opcode == 0x73:  # JMP @A+DPTR
            self.pc = (self.acc + self.dptr) & 0xFFFF
            return 2

        # --- Saltos Relativos y Condicionales ---
        if opcode == 0x80:  # SJMP rel
            rel = self._fetch_byte()
            self._jump_relative(rel)
            return 2

        if opcode == 0x40:  # JC rel
            rel = self._fetch_byte()
            if self.carry == 1:
                self._jump_relative(rel)
            return 2

        if opcode == 0x50:  # JNC rel
            rel = self._fetch_byte()
            if self.carry == 0:
                self._jump_relative(rel)
            return 2

        if opcode == 0x60:  # JZ rel
            rel = self._fetch_byte()
            if self.acc == 0:
                self._jump_relative(rel)
            return 2

        if opcode == 0x70:  # JNZ rel
            rel = self._fetch_byte()
            if self.acc != 0:
                self._jump_relative(rel)
            return 2

        # --- Manipulación y Saltos Condicionales por Bit ---
        if opcode == 0x10:  # JBC bit, rel
            bit_addr = self._fetch_byte()
            rel = self._fetch_byte()
            if self.memory.read_bit(bit_addr, read_latch=True) == 1:
                self.memory.write_bit(bit_addr, 0)
                self._jump_relative(rel)
            return 2

        if opcode == 0x20:  # JB bit, rel
            bit_addr = self._fetch_byte()
            rel = self._fetch_byte()
            if self.memory.read_bit(bit_addr, read_latch=False) == 1:
                self._jump_relative(rel)
            return 2

        if opcode == 0x30:  # JNB bit, rel
            bit_addr = self._fetch_byte()
            rel = self._fetch_byte()
            if self.memory.read_bit(bit_addr, read_latch=False) == 0:
                self._jump_relative(rel)
            return 2

        if opcode == 0xC3:  # CLR C
            self.carry = 0
            return 1

        if opcode == 0xC2:  # CLR bit
            bit_addr = self._fetch_byte()
            self.memory.write_bit(bit_addr, 0)
            return 1

        if opcode == 0xD3:  # SETB C
            self.carry = 1
            return 1

        if opcode == 0xD2:  # SETB bit
            bit_addr = self._fetch_byte()
            self.memory.write_bit(bit_addr, 1)
            return 1

        if opcode == 0xB3:  # CPL C
            self.carry ^= 1
            return 1

        if opcode == 0xB2:  # CPL bit
            bit_addr = self._fetch_byte()
            current = self.memory.read_bit(bit_addr, read_latch=True)
            self.memory.write_bit(bit_addr, current ^ 1)
            return 1

        if opcode == 0xA2:  # MOV C, bit
            bit_addr = self._fetch_byte()
            self.carry = self.memory.read_bit(bit_addr, read_latch=False)
            return 1

        if opcode == 0x92:  # MOV bit, C
            bit_addr = self._fetch_byte()
            self.memory.write_bit(bit_addr, self.carry)
            return 2

        # --- Rotaciones y Operaciones sobre Acumulador ---
        if opcode == 0x03:  # RR A
            a = self.acc
            self.acc = ((a >> 1) | ((a & 0x01) << 7)) & 0xFF
            return 1

        if opcode == 0x13:  # RRC A
            a = self.acc
            old_c = self.carry
            self.carry = a & 0x01
            self.acc = ((a >> 1) | (old_c << 7)) & 0xFF
            return 1

        if opcode == 0x23:  # RL A
            a = self.acc
            self.acc = (((a << 1) & 0xFF) | ((a >> 7) & 0x01)) & 0xFF
            return 1

        if opcode == 0x33:  # RLC A
            a = self.acc
            old_c = self.carry
            self.carry = (a >> 7) & 0x01
            self.acc = (((a << 1) & 0xFF) | old_c) & 0xFF
            return 1

        if opcode == 0xC4:  # SWAP A
            a = self.acc
            self.acc = ((a & 0x0F) << 4) | ((a >> 4) & 0x0F)
            return 1

        if opcode == 0xE4:  # CLR A
            self.acc = 0x00
            return 1

        if opcode == 0xF4:  # CPL A
            self.acc = (~self.acc) & 0xFF
            return 1

        # --- Incrementos y Decrementos (INC / DEC) ---
        if opcode == 0x04:  # INC A
            self.acc = (self.acc + 1) & 0xFF
            return 1

        if opcode == 0x05:  # INC direct
            addr = self._fetch_byte()
            val = (self.memory.read_direct(addr, read_latch=True) + 1) & 0xFF
            self.memory.write_direct(addr, val)
            return 1

        if opcode in (0x06, 0x07):  # INC @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            val = (self.memory.read_indirect(ptr) + 1) & 0xFF
            self.memory.write_indirect(ptr, val)
            return 1

        if 0x08 <= opcode <= 0x0F:  # INC Rn
            reg = opcode & 0x07
            self.memory.write_register(reg, (self.memory.read_register(reg) + 1) & 0xFF)
            return 1

        if opcode == 0xA3:  # INC DPTR
            self.dptr = (self.dptr + 1) & 0xFFFF
            return 2

        if opcode == 0x14:  # DEC A
            self.acc = (self.acc - 1) & 0xFF
            return 1

        if opcode == 0x15:  # DEC direct
            addr = self._fetch_byte()
            val = (self.memory.read_direct(addr, read_latch=True) - 1) & 0xFF
            self.memory.write_direct(addr, val)
            return 1

        if opcode in (0x16, 0x17):  # DEC @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            val = (self.memory.read_indirect(ptr) - 1) & 0xFF
            self.memory.write_indirect(ptr, val)
            return 1

        if 0x18 <= opcode <= 0x1F:  # DEC Rn
            reg = opcode & 0x07
            self.memory.write_register(reg, (self.memory.read_register(reg) - 1) & 0xFF)
            return 1

        # --- Aritméticas: ADD, ADDC, SUBB, MUL AB, DIV AB ---
        if opcode == 0x24:  # ADD A, #data
            self._alu_add(self._fetch_byte(), with_carry=False)
            return 1
        if opcode == 0x25:  # ADD A, direct
            self._alu_add(self.memory.read_direct(self._fetch_byte()), with_carry=False)
            return 1
        if opcode in (0x26, 0x27):  # ADD A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self._alu_add(self.memory.read_indirect(ptr), with_carry=False)
            return 1
        if 0x28 <= opcode <= 0x2F:  # ADD A, Rn
            self._alu_add(self.memory.read_register(opcode & 0x07), with_carry=False)
            return 1

        if opcode == 0x34:  # ADDC A, #data
            self._alu_add(self._fetch_byte(), with_carry=True)
            return 1
        if opcode == 0x35:  # ADDC A, direct
            self._alu_add(self.memory.read_direct(self._fetch_byte()), with_carry=True)
            return 1
        if opcode in (0x36, 0x37):  # ADDC A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self._alu_add(self.memory.read_indirect(ptr), with_carry=True)
            return 1
        if 0x38 <= opcode <= 0x3F:  # ADDC A, Rn
            self._alu_add(self.memory.read_register(opcode & 0x07), with_carry=True)
            return 1

        if opcode == 0x94:  # SUBB A, #data
            self._alu_subb(self._fetch_byte())
            return 1
        if opcode == 0x95:  # SUBB A, direct
            self._alu_subb(self.memory.read_direct(self._fetch_byte()))
            return 1
        if opcode in (0x96, 0x97):  # SUBB A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self._alu_subb(self.memory.read_indirect(ptr))
            return 1
        if 0x98 <= opcode <= 0x9F:  # SUBB A, Rn
            self._alu_subb(self.memory.read_register(opcode & 0x07))
            return 1

        if opcode == 0xA4:  # MUL AB (4 ciclos máquina)
            product = self.acc * self.b_reg
            self.carry = 0
            self.overflow = 1 if product > 0xFF else 0
            self.acc = product & 0xFF
            self.b_reg = (product >> 8) & 0xFF
            return 4

        if opcode == 0x84:  # DIV AB (4 ciclos máquina)
            divisor = self.b_reg
            self.carry = 0
            if divisor == 0:
                self.overflow = 1
            else:
                dividend = self.acc
                self.overflow = 0
                self.acc = dividend // divisor
                self.b_reg = dividend % divisor
            return 4

        # --- Lógicas: ORL, ANL, XRL ---
        if opcode == 0x42:  # ORL direct, A
            addr = self._fetch_byte()
            val = self.memory.read_direct(addr, read_latch=True) | self.acc
            self.memory.write_direct(addr, val)
            return 1
        if opcode == 0x43:  # ORL direct, #data
            addr = self._fetch_byte()
            imm = self._fetch_byte()
            val = self.memory.read_direct(addr, read_latch=True) | imm
            self.memory.write_direct(addr, val)
            return 2
        if opcode == 0x44:  # ORL A, #data
            self.acc |= self._fetch_byte()
            return 1
        if opcode == 0x45:  # ORL A, direct
            self.acc |= self.memory.read_direct(self._fetch_byte())
            return 1
        if opcode in (0x46, 0x47):  # ORL A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self.acc |= self.memory.read_indirect(ptr)
            return 1
        if 0x48 <= opcode <= 0x4F:  # ORL A, Rn
            self.acc |= self.memory.read_register(opcode & 0x07)
            return 1
        if opcode == 0x72:  # ORL C, bit
            self.carry |= self.memory.read_bit(self._fetch_byte())
            return 2
        if opcode == 0xA0:  # ORL C, /bit
            self.carry |= self.memory.read_bit(self._fetch_byte()) ^ 1
            return 2

        if opcode == 0x52:  # ANL direct, A
            addr = self._fetch_byte()
            val = self.memory.read_direct(addr, read_latch=True) & self.acc
            self.memory.write_direct(addr, val)
            return 1
        if opcode == 0x53:  # ANL direct, #data
            addr = self._fetch_byte()
            imm = self._fetch_byte()
            val = self.memory.read_direct(addr, read_latch=True) & imm
            self.memory.write_direct(addr, val)
            return 2
        if opcode == 0x54:  # ANL A, #data
            self.acc &= self._fetch_byte()
            return 1
        if opcode == 0x55:  # ANL A, direct
            self.acc &= self.memory.read_direct(self._fetch_byte())
            return 1
        if opcode in (0x56, 0x57):  # ANL A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self.acc &= self.memory.read_indirect(ptr)
            return 1
        if 0x58 <= opcode <= 0x5F:  # ANL A, Rn
            self.acc &= self.memory.read_register(opcode & 0x07)
            return 1
        if opcode == 0x82:  # ANL C, bit
            self.carry &= self.memory.read_bit(self._fetch_byte())
            return 2
        if opcode == 0xB0:  # ANL C, /bit
            self.carry &= self.memory.read_bit(self._fetch_byte()) ^ 1
            return 2

        if opcode == 0x62:  # XRL direct, A
            addr = self._fetch_byte()
            val = self.memory.read_direct(addr, read_latch=True) ^ self.acc
            self.memory.write_direct(addr, val)
            return 1
        if opcode == 0x63:  # XRL direct, #data
            addr = self._fetch_byte()
            imm = self._fetch_byte()
            val = self.memory.read_direct(addr, read_latch=True) ^ imm
            self.memory.write_direct(addr, val)
            return 2
        if opcode == 0x64:  # XRL A, #data
            self.acc ^= self._fetch_byte()
            return 1
        if opcode == 0x65:  # XRL A, direct
            self.acc ^= self.memory.read_direct(self._fetch_byte())
            return 1
        if opcode in (0x66, 0x67):  # XRL A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self.acc ^= self.memory.read_indirect(ptr)
            return 1
        if 0x68 <= opcode <= 0x6F:  # XRL A, Rn
            self.acc ^= self.memory.read_register(opcode & 0x07)
            return 1

        # --- Transferencia de Datos: MOV, MOVC, PUSH, POP, XCH ---
        if opcode == 0x74:  # MOV A, #data
            self.acc = self._fetch_byte()
            return 1
        if opcode == 0x75:  # MOV direct, #data
            addr = self._fetch_byte()
            imm = self._fetch_byte()
            self.memory.write_direct(addr, imm)
            return 2
        if opcode in (0x76, 0x77):  # MOV @Ri, #data
            ptr = self.memory.read_register(opcode & 0x01)
            self.memory.write_indirect(ptr, self._fetch_byte())
            return 1
        if 0x78 <= opcode <= 0x7F:  # MOV Rn, #data
            self.memory.write_register(opcode & 0x07, self._fetch_byte())
            return 1

        if opcode == 0x85:  # MOV direct_dst, direct_src (codificado: opcode, src, dst)
            src = self._fetch_byte()
            dst = self._fetch_byte()
            self.memory.write_direct(dst, self.memory.read_direct(src))
            return 2
        if opcode in (0x86, 0x87):  # MOV direct, @Ri
            dst = self._fetch_byte()
            ptr = self.memory.read_register(opcode & 0x01)
            self.memory.write_direct(dst, self.memory.read_indirect(ptr))
            return 2
        if 0x88 <= opcode <= 0x8F:  # MOV direct, Rn
            dst = self._fetch_byte()
            self.memory.write_direct(dst, self.memory.read_register(opcode & 0x07))
            return 2

        if opcode == 0x90:  # MOV DPTR, #data16
            hi = self._fetch_byte()
            lo = self._fetch_byte()
            self.dptr = (hi << 8) | lo
            return 2

        if opcode in (0xA6, 0xA7):  # MOV @Ri, direct
            src = self._fetch_byte()
            ptr = self.memory.read_register(opcode & 0x01)
            self.memory.write_indirect(ptr, self.memory.read_direct(src))
            return 2
        if 0xA8 <= opcode <= 0xAF:  # MOV Rn, direct
            src = self._fetch_byte()
            self.memory.write_register(opcode & 0x07, self.memory.read_direct(src))
            return 2

        if opcode == 0xE5:  # MOV A, direct
            self.acc = self.memory.read_direct(self._fetch_byte())
            return 1
        if opcode in (0xE6, 0xE7):  # MOV A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            self.acc = self.memory.read_indirect(ptr)
            return 1
        if 0xE8 <= opcode <= 0xEF:  # MOV A, Rn
            self.acc = self.memory.read_register(opcode & 0x07)
            return 1

        if opcode == 0xF5:  # MOV direct, A
            self.memory.write_direct(self._fetch_byte(), self.acc)
            return 1
        if opcode in (0xF6, 0xF7):  # MOV @Ri, A
            ptr = self.memory.read_register(opcode & 0x01)
            self.memory.write_indirect(ptr, self.acc)
            return 1
        if 0xF8 <= opcode <= 0xFF:  # MOV Rn, A
            self.memory.write_register(opcode & 0x07, self.acc)
            return 1

        if opcode == 0x93:  # MOVC A, @A+DPTR
            addr = (self.acc + self.dptr) & 0xFFFF
            self.acc = self.memory.read_rom(addr)
            return 2

        if opcode == 0x83:  # MOVC A, @A+PC
            addr = (self.acc + self.pc) & 0xFFFF
            self.acc = self.memory.read_rom(addr)
            return 2

        if opcode == 0xC0:  # PUSH direct
            src = self._fetch_byte()
            self.memory.push_byte(self.memory.read_direct(src))
            return 2

        if opcode == 0xD0:  # POP direct
            dst = self._fetch_byte()
            self.memory.write_direct(dst, self.memory.pop_byte())
            return 2

        if opcode == 0xC5:  # XCH A, direct
            addr = self._fetch_byte()
            temp = self.acc
            self.acc = self.memory.read_direct(addr)
            self.memory.write_direct(addr, temp)
            return 1

        if opcode in (0xC6, 0xC7):  # XCH A, @Ri
            ptr = self.memory.read_register(opcode & 0x01)
            temp = self.acc
            self.acc = self.memory.read_indirect(ptr)
            self.memory.write_indirect(ptr, temp)
            return 1

        if 0xC8 <= opcode <= 0xCF:  # XCH A, Rn
            reg = opcode & 0x07
            temp = self.acc
            self.acc = self.memory.read_register(reg)
            self.memory.write_register(reg, temp)
            return 1

        # --- Comparación y Salto (CJNE) ---
        if opcode == 0xB4:  # CJNE A, #data, rel
            imm = self._fetch_byte()
            rel = self._fetch_byte()
            self.carry = 1 if self.acc < imm else 0
            if self.acc != imm:
                self._jump_relative(rel)
            return 2

        if opcode == 0xB5:  # CJNE A, direct, rel
            op2 = self.memory.read_direct(self._fetch_byte())
            rel = self._fetch_byte()
            self.carry = 1 if self.acc < op2 else 0
            if self.acc != op2:
                self._jump_relative(rel)
            return 2

        if opcode in (0xB6, 0xB7):  # CJNE @Ri, #data, rel
            ptr = self.memory.read_register(opcode & 0x01)
            op1 = self.memory.read_indirect(ptr)
            imm = self._fetch_byte()
            rel = self._fetch_byte()
            self.carry = 1 if op1 < imm else 0
            if op1 != imm:
                self._jump_relative(rel)
            return 2

        if 0xB8 <= opcode <= 0xBF:  # CJNE Rn, #data, rel
            op1 = self.memory.read_register(opcode & 0x07)
            imm = self._fetch_byte()
            rel = self._fetch_byte()
            self.carry = 1 if op1 < imm else 0
            if op1 != imm:
                self._jump_relative(rel)
            return 2

        # --- Decremento y Salto si no es Cero (DJNZ) ---
        if opcode == 0xD5:  # DJNZ direct, rel
            addr = self._fetch_byte()
            rel = self._fetch_byte()
            val = (self.memory.read_direct(addr, read_latch=True) - 1) & 0xFF
            self.memory.write_direct(addr, val)
            if val != 0:
                self._jump_relative(rel)
            return 2

        if 0xD8 <= opcode <= 0xDF:  # DJNZ Rn, rel
            reg = opcode & 0x07
            rel = self._fetch_byte()
            val = (self.memory.read_register(reg) - 1) & 0xFF
            self.memory.write_register(reg, val)
            if val != 0:
                self._jump_relative(rel)
            return 2

        raise NotImplementedError(
            f"Opcode 0x{opcode:02X} no implementado en PC=0x{(self.pc - 1) & 0xFFFF:04X}."
        )