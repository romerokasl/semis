# Sunny.EMC: clasificación de mantenimiento con XGBoost

**Prueba de concepto con fallas simuladas.** No se ha validado con fallas reales en el panel propio.
Clasifica la condición de una ventana de 30 s. No predice cuándo habrá una falla.

## Cómo correrlo (PowerShell, desde la raíz del repo)

```powershell
py -3.13 -m pip install -r ml/requirements.txt
```

```powershell
py -3.13 ml/descargar.py
```

```powershell
py -3.13 ml/entrenar.py
```

```powershell
py -3.13 ml/predecir.py
```

`ml/data/` (descargas y tabla de entrenamiento) no se sube al repo.

## En el dashboard

El modelo corre **dentro del navegador**, sin servidor. Solo se usa en modo Firebase; en los demás modos
la tarjeta sigue como antes (API en `localhost:5000` o, si no responde, **reglas fijas, que no son XGBoost**).

| Archivo (raíz del repo) | Qué hace |
|---|---|
| `modelo.js` | Calcula las variables de la ventana y recorre los árboles |
| `modelo_web.json` | Modelo exportado. `entrenar.py` lo regenera |
| `index.html` | Guarda las últimas 15 lecturas crudas y muestra el resultado |

- Necesita 15 lecturas seguidas (unos 30 s).
- Pérdida óptica y resistencia en serie se muestran juntas como "Requiere inspección".
- No diagnostica sin lecturas en vivo, con un sensor fallido, con el voltaje al tope (4.99 V o más)
  o fuera del rango entrenado.
- "Confianza" es la probabilidad que da el modelo, no la probabilidad real de acertar.
- Paridad con Python: `py -3.13 ml/probar_web.py` (necesita Node).

## Clases

| # | Clase | Origen de la falla simulada | Acción |
|---|---|---|---|
| 0 | `normal` | Lecturas propias | Ninguna |
| 1 | `perdida_optica` | Medellín (suciedad) y TECNALIA (módulo amarillento) | Limpiar; si sigue, inspeccionar |
| 2 | `sombra_parcial` | Medellín (sombra) | Quitar la obstrucción |
| 3 | `resistencia_serie` | TECNALIA (módulo con corrosión y resistencias de 200 y 400 mΩ) | Revisar celdas y conexiones |

Las categorías se derivan de la revisión (SOTA) del proyecto. La revisión no define una lista cerrada.
Temperatura y humedad son variables de entrada, no clases. Delaminación y PID no se incluyen.

## ETL (`etl.py`)

1. **Filtrado:** de 8977 lecturas se quitan 2 pruebas manuales y 646 con voltaje menor a 3.5 V o mayor
   a 4.99 V. Quedan 8329, en 448 ventanas de 15 lecturas. El filtro es una decisión de diseño:
   no demuestra que lo excluido sea una falla.
2. **Normalización:** las curvas I-V se expresan como `V/Voc` e `I/Isc` respecto a la curva limpia del
   mismo panel, corrigiendo irradiancia (corriente) y temperatura (voltaje, -0.35 %/K supuesto).
3. **Adaptación:** se escalan a un panel de referencia
   ([AZ-Delivery 5 V](https://cdn.shopify.com/s/files/1/1509/1638/files/mini-SolarPanel_1.pdf):
   6 V, 240 mA), variando Voc entre 5.5 y 7.0 V e Isc entre 150 y 250 mA. No es el panel propio.
4. **Cruce con la carga:** se calcula cuánta luz explica cada voltaje observado y se cruza la curva con
   falla con `I = V/40`. A la lectura real se le aplica el cambio relativo, y luego tope y pasos del ADC.
5. **Inyección:** cada ventana normal genera una copia por falla. Solo cambia el voltaje.

Efectos de TECNALIA calculados desde los CSV: Isc del módulo amarillento ≈ 0.92 del esperado;
resistencia extra del módulo corroído ≈ 0.055 en unidades de `Voc/Isc`.

## Resultados (`resultados/`)

### A) Bloques de 5 min y paneles de Medellín no vistos

| Métrica | XGBoost | Solo voltaje medio |
|---|---|---|
| Exactitud (4 clases) | 77.3 % | 72.9 % |
| F1 macro | 0.770 | 0.723 |
| Falsas alarmas | 17.0 % | 21.9 % |

| Clase | Recall de XGBoost |
|---|---|
| normal | 83 % |
| perdida_optica | 50 % |
| sombra_parcial | 100 % |
| resistencia_serie | 76 % |

Uniendo pérdida óptica y resistencia en "requiere inspección" (mismas predicciones, 3 clases):
91.7 % de exactitud. La unión se decidió después de ver que esas dos se confunden.

Los efectos de TECNALIA **no** se separan por pliegue: son pocos valores medidos y aparecen (con
severidad aleatoria) en entrenamiento y prueba. Por eso A es optimista para las clases 1 y 3.

### B) Un día completo fuera: el modelo no generaliza

| Día de prueba | Ventanas | Exactitud XGBoost | Falsas alarmas | Fallas detectadas |
|---|---|---|---|---|
| 11/11 | 15 | 49 % | 100 % | 100 % |
| 18/11 | 63 | 51 % | 83 % | 91 % |
| 20/11 | 370 | 58 % | 3 % | 52 % |

Sin el día de prueba, el modelo de solo voltaje tiene mayor exactitud que XGBoost en los tres casos.
Al dejar fuera el 20/11 se pierde la mayoría de los datos de entrenamiento.

**Por qué:** la mediana del voltaje normal va de 3.91 V (11/11) a 4.25 V (20/11), cerca de 8 %.
La pérdida óptica y la resistencia simuladas bajan 1 a 5 % en la mediana. La sombra baja cerca de 79 %.
El `luz` actual no alcanza para compensar la diferencia entre días.

## Limitaciones para el reporte

- Todas las fallas son simuladas a partir de otros paneles (30 a 315 W).
- La sombra simulada es severa (68 a 88 % menos voltaje), así que su 100 % es una separación fácil.
  No cubre sombras leves.
- Medellín: una sesión de 4 h. Su suciedad tiene un efecto pequeño o nulo en varios paneles.
  La decoloración no se usa porque compara paneles distintos.
- Los `.mat` procesados de Medellín tienen al menos un archivo mal rotulado (`Panel1_Dirt` trae
  valores de sombra); se usan los crudos.
- El archivo descargado de TECNALIA trae 5 módulos, sin curvas I-V, con la columna de humedad vacía
  y sin el JASolar1 de referencia. Como referencia se usó JASolar3, que según el póster también se usó
  con resistencias añadidas. Esos efectos son estimaciones gruesas.
- Se supone que la falla no afecta al fototransistor ni a las temperaturas, y que está presente en
  toda la ventana.
- Con el ADC al tope (5 V) no se puede clasificar.

## Qué haría falta para mejorarlo

1. Medir varios días normales con distinta luz.
2. Una referencia de luz que no se sature y que responda de forma consistente.
3. Provocar sombra y suciedad en el panel propio, y una resistencia en serie, para probar con datos reales.

## Fuentes

- Restrepo-Cuestas et al., *Experimental data for Mismatching Faults of Photovoltaic Modules*, v2,
  [doi:10.17632/xjs42j8dtf.2](https://data.mendeley.com/datasets/xjs42j8dtf/2), CC BY 4.0.
- TECNALIA y Universidad de Liubliana, *A photovoltaic performance dataset for the benchmarking of failure
  detection and diagnosis algorithms*, [doi:10.5281/zenodo.18306410](https://zenodo.org/records/18306410),
  CC BY 4.0. [Póster](https://zenodo.org/records/18326501).
