# App Inventor: Bluetooth → Firebase

Hace falta: un Android con Bluetooth, el HC-05 encendido y **emparejado** en Ajustes → Bluetooth (PIN `1234` o `0000`), y una cuenta en <https://appinventor.mit.edu>.

## Componentes
| Componente | Propiedades |
|---|---|
| `ListPicker1` (texto "Conectar") | — |
| `Label1` (estado) | Text: "Sin conexión" |
| `Label2` (última línea / último envío) | — |
| `BluetoothClient1` | **DelimiterByte = 10**, Secure = true |
| `Clock1` | TimerInterval = 500, TimerEnabled = **false** |
| `Web1` | Url = `https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json` |

## Bloques

**1. Elegir el HC-05**
- `ListPicker1.BeforePicking` → `set ListPicker1.Elements to BluetoothClient1.AddressesAndNames`
- `ListPicker1.AfterPicking` →
  - `if BluetoothClient1.Connect(address = ListPicker1.Selection)`
    - then: `set Clock1.TimerEnabled to true`, `set Label1.Text to "Conectado"`
    - else: `set Label1.Text to "No se pudo conectar"`

**2. Leer una línea**
- `Clock1.Timer` →
  - `if BluetoothClient1.BytesAvailableToReceive > 0`
    - then: `call procesar(line = BluetoothClient1.ReceiveText(numberOfBytes = -1))`

**3. Procedimiento `procesar(line)`**
1. `initialize local campos to split(text = trim(line), at = ",")` (trim quita el `\r`).
2. `if` **todas** estas son verdaderas (bloque `and`):
   - `length of list campos = 7`
   - `select list item(campos, 1) = "DATA"`
   - `is number?(select list item(campos, 2))` … hasta el ítem 7
3. then: `call Web1.PostText(text = …)` con este texto, armado con el bloque `join`:

```
{"volt":<ítem2>,"ma":<ítem3>,"luz":<ítem4>,"tds":<ítem5>,"hum":<ítem6>,"tdht":<ítem7>,"ts":{".sv":"timestamp"}}
```

Las comillas dentro del texto se escriben tal cual en el bloque de texto.
Si la línea no cumple (por ejemplo, llegó cortada), **se descarta** sin enviar nada.

**4. Respuesta**
- `Web1.GotText` → `set Label2.Text to "Enviado: " + responseContent`
- Si da error 400/403, revisa la URL y que las reglas de Firebase estén publicadas.
- Si Firebase rechaza el formato, añade a `Web1.RequestHeaders` la lista `[["Content-Type","application/json"]]`.

## Notas
- Android 12 o superior pide el permiso **Dispositivos cercanos**; acéptalo.
- Para probar: AI2 Companion (Conectar → AI Companion). Para dejarla funcionando sin la computadora: **Build → Android App (.apk)** e instala el archivo.
- Mantén la app abierta y la pantalla encendida mientras mide; si Android la suspende, se detiene el envío.
- Prueba primero Firebase con el `curl` del README, antes de depurar la app.
