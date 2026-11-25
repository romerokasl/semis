"""Descarga los datos a ml/data/ : lecturas de Firebase, Medellin y TECNALIA.

Uso:  py -3.13 ml/descargar.py            (no repite los datasets ya bajados)
      py -3.13 ml/descargar.py --firebase (solo actualiza las lecturas)

Usa curl y el tar de Windows (curl.exe y System32\\tar.exe, que si abre .rar).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent / "data" / "raw"
FIREBASE = "https://semis-f1ac4-default-rtdb.firebaseio.com/lecturas.json"
TECNALIA = "https://zenodo.org/records/18306410/files/TECNALIA.rar?download=1"
TECNALIA_MD5 = "15daed06b32f5debc9f3d81f0afe31d4"
MENDELEY = "https://data.mendeley.com/public-api/datasets/xjs42j8dtf"
# carpetas "RawData/.../ElectricalData" (los .mat procesados traen al menos uno mal rotulado)
CARPETAS = {"a2852d14": "SP090P", "7251ac94": "M5_30112"}


def curl(url, destino, accept=None):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".part")
    cmd = [shutil.which("curl") or "curl", "-sSLf", "-m", "600", "-o", str(temporal), url]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    subprocess.run(cmd, check=True)
    os.replace(temporal, destino)


def firebase():
    destino = RAW / "firebase" / "lecturas.json"
    curl(FIREBASE, destino)
    print("Firebase:", len(json.loads(destino.read_text())), "lecturas")


def tecnalia():
    rar = RAW / "tecnalia" / "TECNALIA.rar"
    if not rar.exists():
        curl(TECNALIA, rar)
    if hashlib.md5(rar.read_bytes()).hexdigest() != TECNALIA_MD5:
        raise SystemExit("TECNALIA.rar no coincide con el MD5 publicado")
    if not (rar.parent / "TECNALIA").exists():
        tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
        subprocess.run([str(tar) if tar.exists() else "bsdtar", "-xf", rar.name], cwd=rar.parent, check=True)
    print("TECNALIA: ok")


def medellin():
    meta = RAW / "medellin" / "meta.json"
    curl(MENDELEY, meta, accept="application/json")  # las URLs de descarga caducan
    n = 0
    for f in json.loads(meta.read_text(encoding="utf-8"))["files"]:
        carpeta = CARPETAS.get(f["folder_id"][:8])
        nombre = os.path.basename(f["filename"])
        if not carpeta or not nombre.endswith(".mat"):
            continue
        destino = RAW / "medellin" / "raw" / carpeta / nombre
        esperado = f["content_details"]["sha256_hash"]
        if not destino.exists() or hashlib.sha256(destino.read_bytes()).hexdigest() != esperado:
            curl(f["content_details"]["download_url"], destino)
        if hashlib.sha256(destino.read_bytes()).hexdigest() != esperado:
            raise SystemExit(f"{nombre}: SHA-256 no coincide")
        n += 1
    if n != 18:
        raise SystemExit(f"Se esperaban 18 curvas de Medellin y hay {n}")
    print("Medellin: 18 curvas ok")


if __name__ == "__main__":
    firebase()
    if "--firebase" not in sys.argv:
        tecnalia()
        medellin()
