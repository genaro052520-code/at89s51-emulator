; ==============================================================================
; binary_counter.asm - Contador binario ascendente de 8 bits en Puerto 1 (0x00..0xFF)
; Microcontrolador: Atmel/Microchip AT89S51 (MCS-51)
; ==============================================================================
        ORG 0000H

        MOV P1, #00H        ; 0x0000: 75 90 00 -> Inicializa P1 en 0x00
LOOP:
        INC P1              ; 0x0003: 05 90    -> Incrementa latch de P1 en 1
        MOV R0, #02H        ; 0x0005: 78 02    -> Retardo breve para visualización
DELAY:
        DJNZ R0, DELAY      ; 0x0007: D8 FE    -> Decrementa R0 hasta 0 (salto -2)
        SJMP LOOP           ; 0x0009: 80 F8    -> Salta a LOOP (0x0003, offset -8)
        END
