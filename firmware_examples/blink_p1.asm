; ==============================================================================
; blink_p1.asm - Alternancia de patrones LED en Puerto 1 (0x55 <-> 0xAA)
; Microcontrolador: Atmel/Microchip AT89S51 (MCS-51)
; ==============================================================================
        ORG 0000H

LOOP:
        MOV P1, #55H        ; 0x0000: 75 90 55 -> Enciende LEDs pares (0101 0101b)
        MOV R0, #04H        ; 0x0003: 78 04    -> Carga contador de retardo corto
DELAY1:
        DJNZ R0, DELAY1     ; 0x0005: D8 FE    -> Decrementa R0 hasta 0 (salto -2)

        MOV P1, #0AAH       ; 0x0007: 75 90 AA -> Enciende LEDs impares (1010 1010b)
        MOV R0, #04H        ; 0x000A: 78 04    -> Carga contador de retardo corto
DELAY2:
        DJNZ R0, DELAY2     ; 0x000C: D8 FE    -> Decrementa R0 hasta 0 (salto -2)

        SJMP LOOP           ; 0x000E: 80 F0    -> Repite ciclo en 0x0000 (offset -16)
        END
