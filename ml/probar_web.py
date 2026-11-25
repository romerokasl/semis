"""Comprueba que modelo.js (navegador) de lo mismo que Python. Necesita Node."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import etl

JS = """
const M = require(process.argv[1]), modelo = require(process.argv[2]);
const e = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify({
  x: e.ventanas.map(w => M.caracteristicas(w)),
  p: e.filas.map(f => M.probabilidades(modelo, f))
}));
"""


def main():
    modelo = xgb.XGBClassifier()
    modelo.load_model(AQUI / "resultados" / "modelo_xgb.json")
    tabla = pd.read_csv(etl.DATA / "dataset_entrenamiento.csv")
    cols = json.loads((AQUI.parent / "modelo_web.json").read_text())["variables"]
    df, _ = etl.filtrar_normales(etl.cargar_lecturas())
    ventanas = etl.ventanas(df)
    entrada = {"ventanas": [w[["volt", "luz", "tds", "tdht", "hum"]].to_dict("records") for w in ventanas],
               "filas": tabla[cols].to_dict("records")}
    r = subprocess.run(["node", "-e", JS, str(AQUI.parent / "modelo.js"), str(AQUI.parent / "modelo_web.json")],
                       input=json.dumps(entrada), capture_output=True, text=True, check=True)
    js = json.loads(r.stdout)

    x_py = pd.DataFrame([etl.caracteristicas(w) for w in ventanas])[cols].to_numpy()
    dif_x = np.abs(pd.DataFrame(js["x"])[cols].to_numpy() - x_py).max()
    p_py = modelo.predict_proba(tabla[cols])
    p_js = np.array(js["p"])
    dif_p = np.abs(p_js - p_py).max()
    iguales = (p_js.argmax(1) == p_py.argmax(1)).mean()
    print(f"Variables: {len(ventanas)} ventanas, diferencia max {dif_x:.2e}")
    print(f"Modelo: {len(tabla)} filas, diferencia max de probabilidad {dif_p:.2e}, misma clase {iguales:.2%}")
    if dif_x > 1e-9 or dif_p > 1e-5 or iguales < 1:
        raise SystemExit("FALLA: el navegador no coincide con Python")
    print("OK: el navegador coincide con Python")


if __name__ == "__main__":
    main()
