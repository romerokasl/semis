"""Entrena XGBoost y lo evalua. Uso:  py -3.13 ml/entrenar.py

Evaluaciones (siempre sobre fallas SIMULADAS):
  A) cruzada: bloques de tiempo y paneles de Medellin que el modelo no vio.
  B) dejar una sesion (dia) completa fuera.
Se compara contra un modelo que solo ve el voltaje medio.
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, classification_report,
                             confusion_matrix, f1_score)

import etl
import exportar_web

SALIDA = AQUI / "resultados"
BLOQUE_S = 300          # bloques de 5 min: ventanas vecinas caen juntas
# cada pliegue deja fuera un panel de 30 W y uno de 90 W
PLIEGUES_PANEL = [["PanelA", "Panel1"], ["PanelB", "Panel2"], ["PanelC", "Panel3"]]
NO_VARIABLES = ["y", "clase", "ventana", "origen", "panel_fuente", "inicio"]


def modelo():
    return xgb.XGBClassifier(objective="multi:softprob", n_estimators=200, max_depth=3,
                             learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                             min_child_weight=3, reg_lambda=2.0, random_state=42, n_jobs=4)


def metricas(y, p):
    alerta_real, alerta = y > 0, p > 0
    return {"n": int(len(y)),
            "exactitud": float(accuracy_score(y, p)),
            "f1_macro": float(f1_score(y, p, average="macro")),
            "falsas_alarmas": float(alerta[~alerta_real].mean()),
            "fallas_detectadas": float(alerta[alerta_real].mean())}


def evaluar(nombre, partes):
    """partes: lista de (entrenamiento, prueba). Junta las predicciones."""
    todo = []
    for tr, te in partes:
        cols = [c for c in tr.columns if c not in NO_VARIABLES]
        completo = modelo().fit(tr[cols], tr.y)
        base = modelo().fit(tr[["volt_media"]], tr.y)
        todo.append(te.assign(pred=completo.predict(te[cols]),
                              pred_base=base.predict(te[["volt_media"]])))
    r = pd.concat(todo)
    res = {"modelo": metricas(r.y.to_numpy(), r.pred.to_numpy()),
           "solo_voltaje": metricas(r.y.to_numpy(), r.pred_base.to_numpy())}
    print(f"\n== {nombre} ==")
    for k, m in res.items():
        print(f"{k:13s} " + "  ".join(f"{a}={b:.3f}" if a != "n" else f"n={b}" for a, b in m.items()))
    return r, res


def main():
    SALIDA.mkdir(exist_ok=True)
    df, resumen = etl.filtrar_normales(etl.cargar_lecturas())
    V = etl.ventanas(df)
    curvas, tec = etl.curvas_medellin(), etl.efectos_tecnalia()
    print("Filtrado:", resumen)
    print("Ventanas normales:", len(V))
    print("TECNALIA:", tec)

    inicio = pd.Series([w.ts.iloc[0] for w in V])
    bloque = (inicio // (BLOQUE_S * 1000)).astype(int)
    fecha = pd.Series([w.t.iloc[0].strftime("%d/%m") for w in V])

    # A) bloques de tiempo + paneles fuente no vistos
    rng = np.random.default_rng(7)
    bloques = rng.permutation(bloque.unique())
    pliegue = bloque.map({b: i % 3 for i, b in enumerate(bloques)})
    partes = []
    for k, fuera in enumerate(PLIEGUES_PANEL):
        dentro = [p for p in etl.PANELES if p not in fuera]
        tr = etl.construir(dentro, V, np.where(pliegue != k)[0], curvas, tec, 100 + k, copias=3)
        te = etl.construir(fuera, V, np.where(pliegue == k)[0], curvas, tec, 200 + k, copias=3)
        partes.append((tr, te))
    r, res_a = evaluar("A) bloques de tiempo y paneles no vistos", partes)

    nombres = ["normal", "pérdida óptica", "sombra parcial", "resist. serie"]
    print(classification_report(r.y, r.pred, target_names=nombres, digits=3))
    cm = confusion_matrix(r.y, r.pred)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    ConfusionMatrixDisplay(cm / cm.sum(1, keepdims=True), display_labels=nombres).plot(
        ax=ax, cmap="Blues", values_format=".2f", xticks_rotation=25, colorbar=False)
    ax.set_title("XGBoost, fallas SIMULADAS\n(tiempo y paneles fuente no vistos)")
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Clase simulada")
    plt.tight_layout()
    plt.savefig(SALIDA / "matriz_confusion.png", dpi=150)

    # mismas predicciones, uniendo optica + serie en "requiere inspeccion" (0, 2, 1)
    unir = {0: 0, 1: 1, 2: 2, 3: 1}
    y3, p3 = r.y.map(unir), r.pred.map(unir)
    unidas = {"clases": ["normal", "requiere_inspeccion", "sombra_parcial"],
              "exactitud": float(accuracy_score(y3, p3)),
              "f1_macro": float(f1_score(y3, p3, average="macro")),
              "recall": confusion_matrix(y3, p3, normalize="true").diagonal().tolist()}
    print("Uniendo optica + serie:", unidas)

    recall_origen = r.assign(alerta=r.pred > 0, ok=r.pred == r.y).groupby("origen")[["ok", "alerta"]].mean()
    print("\nPor origen (ok = clase correcta, alerta = marcado como cualquier falla):")
    print(recall_origen.round(3).to_string())

    # B) dejar un dia fuera
    todo = etl.construir(etl.PANELES, V, range(len(V)), curvas, tec, 300, copias=3)
    por_dia = {}
    for dia in fecha.unique():
        idx = set(np.where(fecha == dia)[0])
        te = todo[todo.ventana.isin(idx)]
        _, por_dia[dia] = evaluar(f"B) dia {dia} fuera ({len(idx)} ventanas)",
                                  [(todo[~todo.ventana.isin(idx)], te)])

    # modelo final con todo
    cols = [c for c in todo.columns if c not in NO_VARIABLES]
    final = modelo().fit(todo[cols], todo.y)
    final.save_model(SALIDA / "modelo_xgb.json")
    imp = pd.Series(final.feature_importances_, index=cols).sort_values(ascending=False)
    print("\nImportancia de variables:\n" + imp.round(3).to_string())

    etl.DATA.mkdir(exist_ok=True)
    todo.to_csv(etl.DATA / "dataset_entrenamiento.csv", index=False)
    (SALIDA / "metricas.json").write_text(json.dumps({
        "aviso": "Fallas simuladas. No es validacion con fallas reales del panel propio.",
        "clases": etl.CLASES, "variables": cols, "filtrado": resumen,
        "ventanas_normales": len(V), "efectos_tecnalia": tec,
        "A_tiempo_y_paneles_no_vistos": res_a,
        "A_matriz_confusion": cm.tolist(),
        "A_clases_unidas": unidas,
        "rango_volt_media": [float(todo.volt_media.min()), float(todo.volt_media.max())],
        "A_por_origen": recall_origen.to_dict(orient="index"),
        "B_dia_fuera": por_dia,
        "importancia": {k: float(v) for k, v in imp.items()},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nGuardado en", SALIDA)
    exportar_web.exportar()


if __name__ == "__main__":
    main()
