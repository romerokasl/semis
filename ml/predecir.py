"""Clasifica las lecturas mas recientes de Firebase (solo lee).

Uso:  py -3.13 ml/predecir.py            (ultimas 10 ventanas)
      py -3.13 ml/predecir.py 40
"""
import json
import sys
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import pandas as pd
import xgboost as xgb

import etl

URL = "https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json"


def main(n=10):
    meta = json.loads((AQUI / "resultados" / "metricas.json").read_text(encoding="utf-8"))
    modelo = xgb.XGBClassifier()
    modelo.load_model(AQUI / "resultados" / "modelo_xgb.json")
    consulta = f'?orderBy=%22%24key%22&limitToLast={(n + 2) * etl.VENTANA}'
    with urllib.request.urlopen(URL + consulta, timeout=60) as r:
        datos = json.load(r)
    df = pd.DataFrame.from_dict(datos, orient="index").sort_values("ts").reset_index(drop=True)
    df["t"] = pd.to_datetime(df.ts, unit="ms", utc=True).dt.tz_convert("America/El_Salvador")
    ventanas = etl.ventanas(df)[-n:]
    if not ventanas:
        raise SystemExit("No hay suficientes lecturas contiguas para una ventana.")
    print("Modelo entrenado con fallas SIMULADAS: tomar como orientacion, no como diagnostico.\n")
    minimo, maximo = meta["rango_volt_media"]
    for w in ventanas:
        x = etl.caracteristicas(w)
        hora = f"{w.t.iloc[0]:%d/%m %H:%M:%S}  {x['volt_media']:.2f} V"
        if (w[["volt", "luz", "tds", "hum", "tdht"]] <= -900).any().any():
            print(hora, " sensor fallido: sin clasificar")
        elif w.volt.max() >= etl.V_MAX:
            print(hora, " ADC al tope (5 V): sin clasificar")
        elif not minimo <= x["volt_media"] <= maximo:
            print(hora, " voltaje fuera del rango entrenado: revisar conexiones y luz")
        else:
            p = modelo.predict_proba(pd.DataFrame([x])[meta["variables"]])[0]
            k = int(p.argmax())
            print(hora, f" {etl.CLASES[k]:18s} ({p[k]:.0%})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
