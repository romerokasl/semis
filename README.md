# Sunny.EMC – dashboard

Arduino Nano (HC-05) → celular Android (App Inventor) → Firebase Realtime Database → dashboard (Vercel).

## Archivos del repo (raíz)
- `index.html` – dashboard. Se añadió el modo **Firebase (Celular)** al menú de conexión.
- `logo.svg` – logo (sin cambios).
- `database.rules.json` – reglas de Firebase (se pegan en la consola; Vercel no las usa).
- `APP_INVENTOR.md` – guía de la app del celular.
- `README.md` – este archivo.

## Usar el modo Firebase
- El dashboard inicia en este modo por defecto.
- Para abrir la Simulación Demo: `https://TU-SITIO.vercel.app/?modo=sim` o desde el menú de conexión.

Al conectar, solo muestra lecturas **nuevas** (la última que ya estaba guardada se toma como punto de partida, para no pasar datos viejos como si fueran en vivo). Consulta Firebase cada 2 s.

Conversión al formato del dashboard (igual que el modo WebSerial):
| Firebase | Dashboard |
|---|---|
| `volt` (V) | voltaje |
| `ma` (mA) | corriente en A (`ma / 1000`) |
| `luz` (0–1023) | irradiancia = `luz / 1023 × 1200` W/m² |
| `tds` (DS18B20) | temperatura; si es −999 usa `tdht`, y si no hay, 25 °C |
| `hum` | humedad; si es −999 usa 50 % |

Al abrir en modo Firebase las tarjetas están en 0 hasta que llega una lectura **nueva**.

Se descartan las lecturas sin `volt` o `ma` válidos.

## 1. Reglas de Firebase
Consola → Realtime Database → **Reglas** → pegar `database.rules.json` → **Publicar**.
Solo permiten **agregar** lecturas con el formato correcto; nadie puede borrar ni modificar lo guardado. Cualquiera con la URL puede leer y agregar lecturas (sirve para la demo; no es autenticación).

## 2. Probar sin el celular
Con el dashboard abierto en modo Firebase, desde una terminal:

PowerShell (Windows):

```powershell
$body = '{"volt":4.3,"ma":108,"luz":900,"tds":25.9,"hum":69,"tdht":25.8,"ts":{".sv":"timestamp"}}'
Invoke-RestMethod -Method Post -Uri "https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json" -Body $body -ContentType "application/json"
```

bash / Mac / Linux:

```bash
curl -X POST \
  -d '{"volt":4.3,"ma":108,"luz":900,"tds":25.9,"hum":69,"tdht":25.8,"ts":{".sv":"timestamp"}}' \
  'https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json'
```

(En PowerShell `curl` es un alias de otro comando; por eso se usa `Invoke-RestMethod`.)

Responde con un `name` (`-N...`) y en ≤ 2 s se mueven las tarjetas y gráficas.
Si responde `Permission denied`, revisa que publicaste las reglas y que el JSON trae los 7 campos numéricos.

## 3. Vercel
Importar el repo, **Framework Preset: Other**, sin Build Command ni Output Directory.

## Línea que manda el Nano
`DATA,volt,ma,luz,tds,hum,tdht` — una por lectura, cada 2 s, a 9600 baudios.
