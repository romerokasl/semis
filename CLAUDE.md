# Sunny.EMC – contexto del proyecto (handoff para Claude Code)

Usuario: estudiante de Ingeniería en Computación en El Salvador (hispanohablante; responder en español, tono directo y práctico). Zona horaria UTC-6 (sin horario de verano). Laptop Windows (HP), PowerShell. En PowerShell `curl` es un alias de `Invoke-WebRequest`; usar `Invoke-RestMethod`/`Invoke-WebRequest` o Python.

## Objetivo actual
Entrenar un modelo de IA para **mantenimiento predictivo** del panel solar con los datos que ya se guardan en Firebase. Todo el flujo de captura ya funciona de punta a punta.

## Arquitectura (todo funcionando)
```
Sensores → Arduino Nano (PCB propia) → módulo Bluetooth LE → Chrome en un Android (relay.html, Web Bluetooth)
        → Firebase Realtime Database (/lecturas) → dashboard HTML en Vercel (modo Firebase, sondeo cada 2 s)
```
- Repo: https://github.com/romerokasl/semis (el usuario sube los archivos y despliega en Vercel él mismo; Vercel: Framework Preset "Other", sin build).
- Dashboard: https://semis-zeta.vercel.app/ — abrir con `?modo=firebase` para modo en vivo; sin parámetro arranca en simulación.
- Relay: https://semis-zeta.vercel.app/relay.html (hay que abrirlo en **Chrome de Android o de escritorio**; no funciona en iPhone/Safari).

### Archivos del repo (raíz)
| Archivo | Qué es |
|---|---|
| `index.html` | Dashboard "Sunny.EMC" del usuario (Tailwind CDN, lucide, ApexCharts). Se le añadió solo un modo "Firebase (Celular)". **No tocar diseño ni funcionamiento más de lo necesario.** |
| `relay.html` | Página que lee el módulo BLE (Web Bluetooth), junta las líneas y hace POST a Firebase. |
| `logo.svg` | Logo del usuario, sin cambios. |
| `database.rules.json` | Reglas de Firebase (se pegan en la consola; Vercel no las usa). |
| `README.md` | Documentación de uso y prueba. |
| (`APP_INVENTOR.md`) | Obsoleto: App Inventor se descartó (el módulo es BLE y la app daba errores de permisos). |

## Circuito y hardware
- **Arduino Nano** (ATmega328P) en una **PCB propia**; alimentado por USB/powerbank. Para subir código por USB, mejor con el Nano fuera de la PCB, porque el módulo Bluetooth comparte D0/D1 con el USB. En el IDE: placa "Arduino Nano", procesador **ATmega328P (no "Old Bootloader")**, puerto COM4 (FTDI FT232; el driver CDM hubo que instalarlo con `pnputil`).
- Pines (en el sketch se escriben como números, no `D3`):
  - **A0**: fototransistor (luz, ADC crudo 0–1023).
  - **A1**: voltaje del panel solar (el panel alimenta una carga de **40 Ω**).
  - **D5**: DS18B20 (OneWire).
  - **D3**: DHT11.
  - **D0/D1** (RX/TX hardware): módulo Bluetooth.
  - SPI para microSD (D11 MOSI, D12 MISO, D13 SCK, D4 CS): cableado pero **no usado**.
- **Módulo Bluetooth**: una placa tipo "ZS-040" de 6 pines (STATE, RXD, TXD, GND, VCC, EN) soldada a la PCB. Resultó ser **Bluetooth LE** (no clásico/SPP), se anuncia como `05:26:4D:42:C7:C9` (la MAC `00:24:09:00:7C:AC` apareció antes en otro teléfono; ignorarla). Baudios del UART: **9600**. No hace falta emparejarlo con Android; el emparejamiento clásico falla y hay que evitarlo (olvidar el dispositivo en Ajustes).
- La corriente **no se mide**: el sketch calcula `mA = volt / 40 Ω × 1000` (confirmado: 3.925 V → 98.12 mA). Por eso `ma` y `volt` están perfectamente correlacionados; para el modelo son una sola variable.
- La luz es un **fototransistor sin calibrar**; el dashboard la convierte a irradiancia con `luz / 1023 × 1200` W/m² (aproximación, no una medida real).

### Sketch del Nano (`baston_sensor_csv.ino`, ya cargado)
Cada **2 s** imprime por serial (9600) una línea terminada en `\r\n`:
```
DATA,volt,mA,luz,tempDS18B20,humedad,tempDHT11
DATA,4.300,108.50,912,25.94,69.0,25.8
```
Si un sensor falla, su valor es `-999.0` (centinela). El BLE parte la línea en trozos de ~20 bytes; el relay los junta hasta el salto de línea.

## Relay BLE (`relay.html`)
- `navigator.bluetooth.requestDevice({acceptAllDevices:true, optionalServices:[...]})`, elige la característica con notificaciones (prefiere `0000ffe1-…`, servicio `0000ffe0-…`, típico de HM-10), acumula texto, corta por `\n`, valida `DATA` + 7 campos numéricos, y hace `POST` al endpoint de Firebase con `ts` = `{".sv":"timestamp"}`.
- Auto-reconexión (6 intentos), registro en pantalla, casilla "Enviar a Firebase", Wake Lock de pantalla.
- Debe quedar **abierta en Chrome con la pantalla encendida** mientras mide. Un teléfono (el de un amigo) no lograba conectar bien; el que funciona es otro Android.
- Si el escaneo no ve nada en la laptop: el Bluetooth de Windows del usuario ha fallado varias veces tras reinicios (el adaptador desaparece). No es un problema del proyecto.

## Firebase
- Proyecto: `semis-f1ac4`. **Realtime Database** (us-central1): `https://semis-f1ac4-default-rtdb.firebaseio.com`
- Config web del proyecto (la dio el usuario; son **identificadores públicos de cliente**, no secretos):
```js
const firebaseConfig = {
  apiKey: "AIzaSyDrdUztu3HCpdj1rFZGW8v8Sg195m8GCqs",
  authDomain: "semis-f1ac4.firebaseapp.com",
  databaseURL: "https://semis-f1ac4-default-rtdb.firebaseio.com",
  projectId: "semis-f1ac4",
  storageBucket: "semis-f1ac4.firebasestorage.app",
  messagingSenderId: "1095735291021",
  appId: "1:1095735291021:web:fce2e2a50f4bde940486c4",
  measurementId: "G-FSDVYZ135F"
};
```
- **No hay credenciales de administrador** (ni service account ni tokens): no se tienen y no se necesitan para leer. Si hiciera falta escribir/borrar con privilegios, el usuario debe hacerlo desde la consola de Firebase o dar una cuenta de servicio él mismo.
- **Reglas** (`database.rules.json`): lectura pública en `lecturas`; solo se puede **agregar** (`!data.exists() && newData.exists()`) con los 7 campos numéricos válidos; no se puede modificar ni borrar. Cualquiera con la URL puede leer y agregar (sirve para demo; no es autenticación). Para borrar datos hay que usar la consola de Firebase.

### Esquema de datos
Ruta `/lecturas/<pushKey>` (las llaves push son cronológicas):
```json
{ "volt": 3.925, "ma": 98.12, "luz": 859, "tds": 27.31, "hum": 73, "tdht": 29, "ts": 1794436996173 }
```
`volt` V · `ma` mA · `luz` ADC 0–1023 · `tds` °C del DS18B20 · `hum` % del DHT11 · `tdht` °C del DHT11 · `ts` milisegundos Unix (hora del servidor). Valores `<= -900` significan sensor fallido.

### Cómo bajar los datos (sin autenticación)
- Todo: `GET https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json`
- Solo llaves (para contar): `...lecturas.json?shallow=true`
- Paginar si crece mucho: `?orderBy="$key"&limitToFirst=5000` y luego `&startAt="<última llave>"`
- Python rápido:
```python
import requests, pandas as pd
d = requests.get("https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json", timeout=120).json()
df = pd.DataFrame.from_dict(d, orient="index").sort_values("ts")
df["t"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert("America/El_Salvador")
```
- A 22/nov había **8 977 registros** (~5 h de datos a 1 lectura/2 s). Pesa unos pocos MB; seguirá creciendo mientras el circuito mida.

## Consideraciones para el modelo (mantenimiento predictivo)
- **No hay etiquetas de falla** ni historial de degradación: son horas/días de operación normal de un panel pequeño. Un modelo supervisado de "falla" no es viable todavía. Opciones realistas: detección de **anomalías** (autoencoder, isolation forest) sobre ventanas de series de tiempo, y/o un **modelo de comportamiento esperado** (p. ej. voltaje/potencia esperados a partir de luz y temperatura) cuyo residuo creciente indique degradación o suciedad. Habrá que definir con el usuario qué es "falla" (¿sombra, suciedad, sensor desconectado, caída de voltaje?) y si pueden provocarlas a propósito para tener etiquetas.
- **Calidad de datos a revisar antes de entrenar:**
  - Registros de **pruebas manuales** con valores inventados al inicio (por ejemplo `volt 4.3, ma 108, luz 900, tds 25.9, hum 69, tdht 25.8`, repetidos); filtrarlos.
  - Centinelas `-999` y huecos cuando el relay estuvo apagado o sin conexión (`ts` con saltos mayores a 2 s).
  - `ma` es derivada de `volt` (redundante); `luz` es cruda y no lineal; DHT11 es poco preciso (±2 °C, ±5 %).
  - Hay variación diurna fuerte (luz natural): conviene incluir hora del día como característica o normalizar por luz.
- Mantener separado el código de ML (carpeta aparte, p. ej. `ml/`) para no tocar el dashboard.

## Reglas de trabajo con este usuario
- No cambiar el diseño ni el comportamiento del dashboard (`index.html`) salvo lo estrictamente necesario; el usuario ya tenía su diseño.
- El usuario sube archivos al repo y despliega en Vercel **él mismo**; avisar qué archivos hay que subir.
- No borrar ni modificar datos de Firebase sin preguntar; las reglas lo impiden desde el cliente de todos modos.
- Probar antes de afirmar que algo funciona; si algo no se puede verificar (hardware, Bluetooth real), decirlo claramente.
- Instrucciones paso a paso, concretas y cortas; explicar dónde se hace cada cosa (computadora, teléfono, consola de Firebase).
