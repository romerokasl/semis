"""ETL: lleva los efectos de falla medidos en otros paneles al montaje propio.

1. Lecturas propias -> filtrado y ventanas "normales".
2. Medellin: curvas I-V normalizadas (V/Voc, I/Isc). TECNALIA: efectos relativos.
3. Las curvas se escalan al panel de referencia (con Voc/Isc aleatorios) y se
   cruzan con la carga de 40 ohm.
4. Cada ventana normal genera una copia con cada falla. Solo cambia el voltaje.

LAS FALLAS SON SIMULADAS. Ninguna se midio en el panel propio.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from sklearn.isotonic import IsotonicRegression

DATA = Path(__file__).resolve().parent / "data"
RAW = DATA / "raw"

CLASES = ["normal", "perdida_optica", "sombra_parcial", "resistencia_serie"]
R_CARGA = 40.0
VOC_REF = (5.5, 7.0)     # V  (referencia AZ-Delivery 6.0 V; rango supuesto)
ISC_REF = (0.15, 0.25)   # A  (referencia AZ-Delivery 0.24 A; rango supuesto)
V_MIN, V_MAX = 3.5, 4.99  # fuera de esto no se usa como "normal" (4.99+ = ADC al tope)
VENTANA = 15             # lecturas por ventana (30 s)
TEMP_VOC = -0.0035       # 1/K, coeficiente tipico de Voc en silicio (supuesto)
PANELES = ["PanelA", "PanelB", "PanelC", "Panel1", "Panel2", "Panel3"]


# ---------------------------------------------------------------- lecturas propias
def cargar_lecturas():
    d = json.loads((RAW / "firebase" / "lecturas.json").read_text())
    df = pd.DataFrame.from_dict(d, orient="index").sort_values("ts").reset_index(drop=True)
    df["t"] = pd.to_datetime(df.ts, unit="ms", utc=True).dt.tz_convert("America/El_Salvador")
    return df


def filtrar_normales(df):
    """Quita pruebas manuales, sensores fallidos y voltajes anomalos o saturados."""
    manual = (df[["volt", "ma", "luz", "tds", "hum", "tdht"]]
              == [4.3, 108, 900, 25.9, 69, 25.8]).all(axis=1)
    fallido = (df[["volt", "luz", "tds", "hum", "tdht"]] <= -900).any(axis=1)
    rango = df.volt.between(V_MIN, V_MAX)
    resumen = {"total": len(df), "pruebas_manuales": int(manual.sum()),
               "sensor_fallido": int(fallido.sum()),
               "voltaje_fuera_de_rango": int((~rango & ~manual & ~fallido).sum())}
    ok = df[~manual & ~fallido & rango].copy()
    resumen["usadas"] = len(ok)
    return ok, resumen


def ventanas(df):
    """Ventanas sin traslape de VENTANA lecturas contiguas (huecos <= 10 s)."""
    corte = df.ts.diff() > 10_000
    out = []
    for _, tramo in df.groupby(corte.cumsum()):
        for i in range(0, len(tramo) - VENTANA + 1, VENTANA):
            out.append(tramo.iloc[i:i + VENTANA])
    return out


def caracteristicas(w):
    """Variables de una ventana. 'ma' no se usa: es volt/40."""
    v, luz = w.volt.to_numpy(float), w.luz.to_numpy(float)
    x = np.arange(len(v))
    return {
        "volt_media": v.mean(), "volt_std": v.std(), "volt_min": v.min(), "volt_max": v.max(),
        "volt_pendiente": np.polyfit(x, v, 1)[0], "volt_salto_max": np.abs(np.diff(v)).max(),
        "luz_media": luz.mean(), "luz_std": luz.std(), "luz_pendiente": np.polyfit(x, luz, 1)[0],
        "volt_por_luz": v.mean() / luz.mean(),
        "temp_ds18b20": w.tds.mean(), "temp_dht11": w.tdht.mean(), "humedad": w.hum.mean(),
    }


# ---------------------------------------------------------------- Medellin
def leer_curva(ruta):
    """Curva cruda del osciloscopio -> mediana por tramos de voltaje, monotona."""
    d = loadmat(ruta, squeeze_me=True)
    V, I = d["Vpanel"].astype(float), d["Ipanel"].astype(float)
    bordes = np.linspace(V.min(), V.max(), 201)
    g = pd.DataFrame({"k": np.digitize(V, bordes), "V": V, "I": I}).groupby("k").agg(
        V=("V", "median"), I=("I", "median"), n=("I", "size"))
    g = g[g.n > 50].sort_values("V")
    v = g.V.to_numpy()
    i = IsotonicRegression(increasing=False).fit_transform(v, g.I.to_numpy())
    voc = float(np.polyval(np.polyfit(g.I.tail(10), g.V.tail(10), 1), 0))
    isc = float(np.median(i[v < v.min() + 2]))
    temp = float(d["T"])
    return {"v": v, "i": i, "voc": max(voc, v.max()), "isc": isc,
            "irr": float(d["IRR"]), "temp": temp}


def curvas_medellin():
    """Por panel: curva limpia, sucia y sombreada, en unidades de la limpia."""
    out = {}
    for panel in PANELES:
        carpeta = "SP090P" if panel[-1].isdigit() else "M5_30112"
        c = {cond: leer_curva(RAW / "medellin" / "raw" / carpeta / f"{panel}_{cond}.mat")
             for cond in ("Clean", "Dirt", "Shadow")}
        limpia = c["Clean"]
        pu = {}
        for cond, f in c.items():
            # se corrige irradiancia en corriente y temperatura en voltaje
            v = f["v"] * (1 - TEMP_VOC * (f["temp"] - limpia["temp"])) / limpia["voc"]
            i = f["i"] / (limpia["isc"] * f["irr"] / limpia["irr"])
            voc = f["voc"] * (1 - TEMP_VOC * (f["temp"] - limpia["temp"])) / limpia["voc"]
            pu[cond] = (np.r_[0.0, v, voc], np.r_[i[0], i, 0.0])
        out[panel] = pu
    return out


# ---------------------------------------------------------------- TECNALIA
def efectos_tecnalia():
    """Perdida de Isc (amarillamiento, Ningbo) y de factor de forma (corrosion, Trina).

    Se compara cada modulo con su ficha y se corrige con JASolar3, el unico JASolar
    publicado (al que tambien le pusieron resistencias en algun periodo).
    No es un control sano ideal: tomar como estimacion gruesa.
    """
    base = RAW / "tecnalia" / "TECNALIA"
    ficha = {"JaSolar3": (9.98, 40.53, 9.50, 33.16),
             "NingboSolar": (5.48, 44.0, 4.96, 35.2),
             "TrinaSolar": (5.40, 44.5, 4.95, 37.5)}
    rel = {}
    for nombre, (isc0, voc0, imp0, vmp0) in ficha.items():
        df = pd.read_csv(base / f"data_{nombre}" / f"data_{nombre}.csv", sep=";",
                         encoding="utf-8", encoding_errors="replace")
        col = lambda prefijo: df[next(c for c in df.columns if c.startswith(prefijo))]
        isc, ff, g, tm = df["Isc(A)"], df["FF"], col("Front GPOA"), col("Temp. Mod")
        m = (g.between(700, 1100) & isc.notna() & tm.between(5, 75) & ff.between(30, 90)
             & (isc > 0.5) & (isc / g * 1000 < 13))
        rel[nombre] = ((isc[m] / g[m] * 1000).median() / isc0,
                       ff[m].median() / 100 / (imp0 * vmp0 / (isc0 * voc0)))
    ref_i, ref_ff = rel["JaSolar3"]
    ki_amarillo = rel["NingboSolar"][0] / ref_i
    rs_corrosion = 1 - rel["TrinaSolar"][1] / ref_ff   # FF ~ FF0 (1 - Rs en p.u.)
    # cajas de resistencia del poster: 200 y 400 mOhm sobre Voc/Isc = 40.53/9.98 ohm
    z_ja = 40.53 / 9.98
    return {"ki_amarillamiento": float(ki_amarillo), "rs_pu_corrosion": float(rs_corrosion),
            "rs_pu_cajas": [0.2 / z_ja, 0.4 / z_ja]}


# ---------------------------------------------------------------- adaptacion al montaje
def _cruce(curva, isc, voc):
    """Voltaje donde la curva escalada corta a la carga I = V/40."""
    v_pu, i_pu = curva
    lo, hi = 0.0, voc * float(v_pu.max())
    for _ in range(40):
        m = (lo + hi) / 2
        if isc * np.interp(m / voc, v_pu, i_pu, right=0.0) > m / R_CARGA:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def _voc_con_luz(voc, g):
    return voc * (1 + 0.067 * np.log(np.clip(g, 0.02, None)))


def _luz_equivalente(v_obs, sana, voc_ref, isc_ref):
    """Fraccion de luz g con la que el panel sano daria v_obs sobre 40 ohm."""
    lo, hi = 0.01, 4.0
    for _ in range(40):
        g = (lo + hi) / 2
        if _cruce(sana, g * isc_ref, _voc_con_luz(voc_ref, g)) < v_obs:
            lo = g
        else:
            hi = g
    return (lo + hi) / 2


def adc(v):
    """Imita al Nano: tope de 5 V, 10 bits y 3 decimales."""
    paso = 5.0 / 1023
    return np.round(np.round(np.clip(v, 0, 5.0) / paso) * paso, 3)


def curva_con_falla(clase, curvas, panel, tec, rng):
    sana = curvas[panel]["Clean"]
    v, i = sana
    if clase == "sombra_parcial":
        return curvas[panel]["Shadow"], "medellin_sombra"
    if clase == "perdida_optica":
        if rng.random() < 0.5:
            return curvas[panel]["Dirt"], "medellin_suciedad"
        ki = tec["ki_amarillamiento"] + rng.uniform(-0.02, 0.02)
        return (v, i * ki), "tecnalia_amarillamiento"
    if clase == "resistencia_serie":
        valores = [tec["rs_pu_corrosion"], *tec["rs_pu_cajas"]]
        rs = rng.uniform(min(valores), max(valores))
        v2 = np.clip(v - rs * i, 0, None)          # misma corriente, menos voltaje
        return (np.maximum.accumulate(v2), i), "tecnalia_resistencia"
    raise ValueError(clase)


def inyectar(w, clase, curvas, panel, tec, rng):
    """Copia de la ventana con el voltaje que habria con la falla."""
    sana = curvas[panel]["Clean"]
    falla, origen = curva_con_falla(clase, curvas, panel, tec, rng)
    voc_ref, isc_ref = rng.uniform(*VOC_REF), rng.uniform(*ISC_REF)
    cache = {}
    for v_obs in np.unique(w.volt):
        g = _luz_equivalente(v_obs, sana, voc_ref, isc_ref)
        voc_g = _voc_con_luz(voc_ref, g)
        # solo se traslada el cambio relativo, para conservar el voltaje y ruido propios
        razon = _cruce(falla, g * isc_ref, voc_g) / _cruce(sana, g * isc_ref, voc_g)
        cache[v_obs] = v_obs * razon
    copia = w.copy()
    copia["volt"] = adc(np.array([cache[v] for v in w.volt]))
    return copia, origen


def construir(paneles, lista_ventanas, indices, curvas, tec, semilla, copias=1):
    """Tabla balanceada: cada ventana aparece como normal y con cada falla."""
    rng = np.random.default_rng(semilla)
    filas = []
    for idx in indices:
        w = lista_ventanas[idx]
        for _ in range(copias):
            for etiqueta, clase in enumerate(CLASES):
                panel = paneles[rng.integers(len(paneles))]
                if clase == "normal":
                    muestra, origen, panel = w, "propio", ""
                else:
                    muestra, origen = inyectar(w, clase, curvas, panel, tec, rng)
                filas.append({**caracteristicas(muestra), "y": etiqueta, "clase": clase,
                              "ventana": idx, "origen": origen, "panel_fuente": panel,
                              "inicio": w.t.iloc[0].isoformat()})
    return pd.DataFrame(filas)
