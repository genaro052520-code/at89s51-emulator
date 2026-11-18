# Simulador de Microcontrolador Atmel/Microchip AT89S51 (MCS-51)

Emulador de arquitectura Harvard en Python 3 para el microcontrolador **Atmel/Microchip AT89S51 (familia 8051)** con ejecución desacoplada multi-proceso mediante memoria compartida `mmap` (**ADM**), depurador interactivo por consola (CLI) y un **laboratorio electrónico virtual estilo Tinkercad** en Tkinter con encapsulado DIP-40, protoboard interactiva, cableado dinámico y 10 componentes electrónicos.

---

## Características Principales

* **Arquitectura Harvard MCS-51:**
  * Memoria de programa (**ROM**) independiente direccionable desde `0x0000` hasta `0xFFFF` (4 KB internos del AT89S51 / expansión hasta 64 KB).
  * Memoria de datos interna (**RAM**) de 128 bytes (`0x00`–`0x7F`) con 4 bancos de registros (`R0`–`R7`), área direccionable por bits (`0x20`–`0x2F`) y pila (`SP`).
  * Registros de Funciones Especiales (**SFR**) mapeados en `0x80`–`0xFF`: `ACC`, `B`, `PSW`, `SP`, `DPL`, `DPH`, `P0`, `P1`, `P2`, `P3`, `TMOD`, `TCON`, `TH0`, `TL0`, `TH1`, `TL1`, `IE`, `IP`.
* **Periféricos Internos del 8051:**
  * Temporizadores/Contadores de 16 bits (`Timer 0` y `Timer 1`) en modos 0, 1 y 2.
  * Sistema de interrupciones vectorizadas (`INT0`, `TF0`, `INT1`, `TF1`) con prioridades configurables.
  * Actualización automática de banderas de estado en `PSW` (`CY`, `AC`, `F0`, `RS1`, `RS0`, `OV`, `P`).
* **Desacoplamiento Estricto por Memoria Compartida (`ADM` + `mmap`):**
  * El núcleo de emulación (`src/core/`) y la interfaz gráfica (`src/gui/`) se ejecutan como **procesos independientes** sincronizados a través de `.state/ports_state.bin`.
  * La interfaz gráfica nunca importa módulos de `src/core/` ni `src/storage/`.
* **Laboratorio Virtual Estilo Tinkercad (`src/gui/`):**
  * Encapsulado físico **AT89S51 (DIP-40)** con los 40 pines interactivos, botón hardware `RESET (PIN 9)` y monitor hexadecimal/binario de `P0`–`P3`.
  * **Protoboard** con buses de alimentación (`+5V` / `GND`), matriz de perforaciones (`a–e` y `f–j` × `30` columnas) con iluminación de nodos activos a `5V`, **cables virtuales curvados** (`smooth=True`), **Inspector de Propiedades en tiempo real** y **10 componentes electrónicos interactivos**.

---

## Arquitectura y Estructura del Proyecto

```text
+-----------------------------------+       +--------------------------------------+
|       PROCESO CLI / NÚCLEO        |       |       PROCESO GUI (TINKERCAD)        |
|                                   |       |                                      |
|  src/core/cpu.py    (CPU8051)     |       |  src/gui/app.py (AT89S51EmulatorGUI) |
|  src/core/memory.py (Memory8051)  |       |  src/gui/protoboard.py               |
|  src/storage/       (Intel HEX)   |       |  src/gui/components/ (10 clases)     |
+-----------------+-----------------+       +------------------+-------------------+
                  |                                            |
                  |  Lectura/Escritura de Puertos (P0-P3, AN)  |
                  +------------------>  ADM  <-----------------+
                                 (src/ports/adm.py)
                              mmap: .state/ports_state.bin
```

```text
at89s51-emulator/
├── main.py                         # Punto de entrada del núcleo CPU y depurador CLI
├── main_gui.py                     # Punto de entrada del laboratorio virtual (GUI Tkinter)
├── README.md                       # Documentación técnica del proyecto
├── examples/                       # Programas de prueba en código máquina Intel HEX (.hex)
│   ├── blink_p1.hex                # Parpadeo de LEDs en el Puerto 1
│   ├── binary_counter.hex          # Contador binario de 8 bits en P1
│   └── button_to_led.hex           # Lectura de pulsador en P3.2 y salida en P1.0
├── src/
│   ├── core/                       # Núcleo de emulación del microcontrolador AT89S51
│   │   ├── cpu.py                  # Ciclo fetch-decode-execute, ALU, Timers e Interrupciones
│   │   └── memory.py               # Memoria Harvard (ROM, RAM interna y SFRs)
│   ├── storage/                    # Persistencia y carga de firmware
│   │   └── hex_loader.py           # Parser y validador de checksum para archivos Intel HEX
│   ├── ports/                      # Capa intermedia de comunicación IPC
│   │   └── adm.py                  # Administrador de Dispositivos y Memoria (mmap 40 canales)
│   └── gui/                        # Interfaz gráfica estilo Tinkercad (desacoplada)
│       ├── app.py                  # Ventana principal de 3 zonas e Inspector de Propiedades
│       ├── protoboard.py           # Clases Protoboard y CableVirtual (enrutamiento dinámico)
│       └── components/             # Biblioteca de 10 componentes electrónicos virtuales
│           ├── __init__.py         # Exportación y catálogos de actuadores y sensores
│           ├── base.py             # Clase abstracta ComponenteElectronico
│           ├── actuadores.py       # LED, Motor DC, Servomotor, Buzzer y Display 7-Seg
│           └── sensores.py         # Pulsador, Switch DIP, Potenciómetro, Temp y HC-SR04
└── tests/                          # Suite de pruebas automatizadas con pytest
    └── test_components_gui.py      # Pruebas de integración ADM, 10 componentes y AST GUI
```

---

## Mapa de Canales y Señales en `ADM`

`ADM` (`src/ports/adm.py`) administra **40 canales** sincronizados en memoria compartida con umbral lógico TTL de **`2.5 V`** (`0.0 V` = nivel bajo `0`, `5.0 V` = nivel alto `1`):

| Rango de Canales | Puerto / Bus | Pines Físicos DIP-40 | Descripción |
| :--- | :--- | :--- | :--- |
| `0` – `7` | `P0.0` – `P0.7` | Pines `39` – `32` | Puerto 0 bidireccional / bus multiplexado `AD0–AD7` |
| `8` – `15` | `P1.0` – `P1.7` | Pines `1` – `8` | Puerto 1 de E/S de propósito general con pull-up interno |
| `16` – `23` | `P2.0` – `P2.7` | Pines `21` – `28` | Puerto 2 de E/S / byte alto de direcciones `A8–A15` |
| `24` – `31` | `P3.0` – `P3.7` | Pines `10` – `17` | Puerto 3 de E/S y funciones especiales (`RXD`, `TXD`, `INT0`, `INT1`, `T0`, `T1`, `WR`, `RD`) |
| `32` – `39` | `AN0` – `AN7` | Bus Analógico Auxiliar | Canales continuos (`0.0 V` a `5.0 V`) para sensores analógicos y potenciómetros |

---

## Componentes Electrónicos del Laboratorio Virtual (`src/gui/components/`)

### Actuadores de Salida (5)
1. **`LedComponente`**: Diodo emisor de luz (`rojo`, `verde`, `azul`, `amarillo`, `naranja`, `blanco`) con resistencia limitadora y halo luminoso cuando el pin supera `2.5 V`.
2. **`MotorDCComponente`**: Motor de corriente continua con animación continua de rotación del rotor (`girando`/`activo` y `angulo`).
3. **`ServomotorComponente`**: Servomotor posicional (`0°` a `180°`) con interpolación suave del brazo actuador.
4. **`BuzzerComponente`**: Zumbador piezoeléctrico activo con ondas acústicas animadas al recibir nivel lógico alto.
5. **`Display7SegmentosComponente`**: Display de 7 segmentos conectado a un puerto completo de 8 bits o nibble (`digito`, `valor_byte`, `segmentos` `a–g` y `dp`).

### Sensores y Entradas Interactivas (5)
6. **`PulsadorComponente`**: Botón táctil momentáneo de 4 patas; al mantenerlo presionado inyecta estímulo en `ADM` (`inyectar_estimulo_externo`) y al soltarlo lo libera (`liberar_estimulo_externo`).
7. **`InterruptorDipComponente`**: Interruptor deslizante de 2 posiciones (`ON`/`OFF`) con enclavamiento de estado en `ADM`.
8. **`PotenciometroComponente`**: Perilla rotatoria y barra deslizante (`0%` a `100%`) que escribe voltaje continuo (`0.0 V` – `5.0 V`) en `AN0–AN7` y refleja nivel lógico en un pin digital si supera `2.5 V`.
9. **`SensorTemperaturaComponente`**: Sensor térmico tipo LM35/DHT (`0 °C` a `100 °C`) con salida analógica lineal proporcional y disparo digital alto al superar un umbral configurable (`30 °C` por defecto).
10. **`SensorUltrasonicoComponente`**: Sensor de distancia tipo HC-SR04 (`2 cm` a `400 cm`) con deslizador de objetivo y activación de señal digital de obstáculo cuando la distancia es menor a `20 cm`.

---

## Instalación y Requisitos

* **Python:** `3.10` o superior.
* **Tkinter:** Incluido en instalaciones estándar de Python. En distribuciones Debian/Ubuntu/Linux Mint, instalar si no está presente:
  ```bash
  sudo apt update && sudo apt install -y python3-tk
  ```
* **Pytest** (para ejecutar las pruebas unitarias e integración):
  ```bash
  pip install pytest
  ```

---

## Guía de Ejecución

### 1. Ejecución Multi-Proceso (Laboratorio Visual + Núcleo AT89S51)

Abre **dos terminales** en la raíz del proyecto para observar la comunicación IPC en tiempo real:

**Terminal 1 — Iniciar el Laboratorio Virtual (GUI):**
```bash
python main_gui.py
```
*(Opcional: puedes especificar un archivo de estado compartido personalizado con `--state-file ruta/archivo.bin`.)*

**Terminal 2 — Ejecutar un firmware Intel HEX en el núcleo AT89S51:**
```bash
python main.py examples/blink_p1.hex
```

### 2. Controles del Laboratorio Virtual (`main_gui.py`)

* **Agregar componentes:** Selecciona el pin destino (`P0.0`–`P3.7`), fila/columna de la protoboard y haz clic sobre cualquiera de los 10 botones de la paleta derecha.
* **Circuitos de demostración (1 clic):** Carga configuraciones prearmadas (`Actuadores en P1`, `Botón P3.2 -> LED P1.0` o `Sensores + Display 7-Seg`).
* **Inspección y reconexión en vivo:** Haz clic sobre cualquier componente en la protoboard para ver sus propiedades en tiempo real en el **Panel Inspector** o cambiar dinámicamente el pin del AT89S51 al que está conectado.
* **Reset hardware:** Mantén presionado **`RESET HARDWARE (PIN 9 RST)`** en el panel izquierdo para restaurar todos los puertos a `0xFF`.

---

## Pruebas Automatizadas

Ejecuta la suite completa de pruebas desde la raíz del repositorio:

```bash
pytest -v
```

La suite en `tests/test_components_gui.py` verifica:
* La existencia e inicialización de las **10 clases de componentes** en `src/gui/components/`.
* La sincronización bidireccional **`CPU8051` ↔ `ADM` ↔ Componentes** (escritura en `P1`/`P2` hacia actuadores y lectura en `P2`/`P3` desde sensores y pulsadores) en modo headless sin necesidad de servidor gráfico.
* El enrutamiento dinámico de **`Protoboard`** y **`CableVirtual`** sobre pines digitales (`P0.0`–`P3.7`) y canales analógicos (`AN0`–`AN7`).
* Una **auditoría estática mediante AST** que confirma que ningún archivo dentro de `src/gui/` importa módulos de `src/core` ni `src/storage`.