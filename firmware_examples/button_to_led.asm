; ==============================================================================
; button_to_led.asm - Control de LED en P1.0 desde pulsador externo en P3.2 (INT0)
; Microcontrolador: Atmel/Microchip AT89S51 (MCS-51)
; Lógica:
;   - Pulsador liberado (P3.2 = 1 por pull-up) -> P1.0 = 0 (LED apagado)
;   - Pulsador presionado (P3.2 = 0 a GND)    -> P1.0 = 1 (LED encendido)
; ==============================================================================
        ORG 0000H

        MOV P3, #0FFH       ; 0x0000: 75 B0 FF -> Configura P3 como entrada con pull-up
        CLR P1.0            ; 0x0003: C2 90    -> Estado inicial: LED P1.0 apagado

MAIN_LOOP:
        JB P3.2, APAGAR_LED ; 0x0005: 20 B2 04 -> Si P3.2 == 1, salta a APAGAR_LED (0x000C)
        SETB P1.0           ; 0x0008: D2 90    -> Si P3.2 == 0, enciende LED P1.0 (5V)
        SJMP MAIN_LOOP      ; 0x000A: 80 F9    -> Regresa a MAIN_LOOP (0x0005, offset -7)

APAGAR_LED:
        CLR P1.0            ; 0x000C: C2 90    -> Apaga LED P1.0 (0V)
        SJMP MAIN_LOOP      ; 0x000E: 80 F5    -> Regresa a MAIN_LOOP (0x0005, offset -11)
        END
