"""Convierte el modelo entrenado a modelo_web.json (raiz del repo), que usa modelo.js."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import etl

DESTINO = AQUI.parent / "modelo_web.json"


def exportar():
    meta = json.loads((AQUI / "resultados" / "metricas.json").read_text(encoding="utf-8"))
    ruta = AQUI / "resultados" / "modelo_xgb.json"
    crudo = json.loads(ruta.read_text())["learner"]["gradient_booster"]["model"]
    arboles = [{"clase": c, "izq": t["left_children"], "der": t["right_children"],
                "var": t["split_indices"], "val": t["split_conditions"]}
               for t, c in zip(crudo["trees"], crudo["tree_info"])]

    # margen base = margen de XGBoost menos la suma de las hojas, en una fila cualquiera
    modelo = xgb.XGBClassifier()
    modelo.load_model(ruta)
    cero = pd.DataFrame(np.zeros((1, len(meta["variables"]))), columns=meta["variables"])
    margen = modelo.predict(cero, output_margin=True)[0].astype(float)
    for t in arboles:
        n = 0
        while t["izq"][n] != -1:
            n = t["izq"][n] if 0.0 < t["val"][n] else t["der"][n]
        margen[t["clase"]] -= t["val"][n]

    DESTINO.write_text(json.dumps({
        "aviso": meta["aviso"], "clases": meta["clases"], "variables": meta["variables"],
        "ventana": etl.VENTANA, "v_tope": etl.V_MAX,
        "rango_volt_media": meta["rango_volt_media"],
        "margen_base": margen.tolist(), "arboles": arboles,
    }, separators=(",", ":")), encoding="utf-8")
    print(f"Modelo para el dashboard: {DESTINO.name} ({DESTINO.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    exportar()
