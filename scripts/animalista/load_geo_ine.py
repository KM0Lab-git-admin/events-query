"""
load_geo_ine.py — Carga el maestro de municipios de España en animalista_db.

Fuente oficial: "Relación de municipios y sus códigos por provincias" del INE,
fichero Excel anual https://www.ine.es/daco/daco42/codmun/diccionarioAA.xlsx
(AA = dos últimos dígitos del año). Columnas: CODAUTO, CPRO, CMUN, DC, NOMBRE.

El xlsx se lee con la librería estándar (zipfile + xml) para no añadir
dependencias al proyecto.

USO
---
    python scripts/animalista/load_geo_ine.py                 # descarga el año en curso
    python scripts/animalista/load_geo_ine.py --year 2025
    python scripts/animalista/load_geo_ine.py --file diccionario26.xlsx
    python scripts/animalista/load_geo_ine.py --dry-run       # solo parsea y resume

CONEXIÓN
--------
    ANIMALISTA_DB_HOST / _PORT / _USER / _PASSWORD / _NAME (default animalista_db).
    Si faltan, usa DB_HOST / DB_PORT / DB_USER / DB_PASSWORD del .env (mismo
    MySQL que events_db) con base de datos animalista_db.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.animalista.db import connect, parse_db_args  # noqa: E402

# Consola Windows en cp1252: no romper al imprimir nombres con acentos
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INE_URL = "https://www.ine.es/daco/daco42/codmun/diccionario{yy}.xlsx"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def ine_display_name(raw: str) -> str:
    """'Coruña, A' -> 'A Coruña'; 'Palmas de Gran Canaria, Las' -> 'Las Palmas de Gran Canaria'.
    Nombres bilingües 'Alacant/Alicante' se conservan tal cual."""
    if "," in raw:
        base, art = raw.rsplit(",", 1)
        return f"{art.strip()} {base.strip()}"
    return raw.strip()


def read_xlsx_rows(data: bytes) -> list[list[str]]:
    """Lee la primera hoja de un xlsx y devuelve filas como listas de strings."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet_name = next(n for n in sorted(z.namelist()) if n.startswith("xl/worksheets/sheet"))
        root = ET.fromstring(z.read(sheet_name))
    rows: list[list[str]] = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells: dict[int, str] = {}
        for c in row.findall("m:c", NS):
            ref = c.get("r", "")
            col = 0
            for ch in ref:
                if ch.isalpha():
                    col = col * 26 + (ord(ch.upper()) - 64)
                else:
                    break
            v = c.find("m:v", NS)
            if v is None:
                t_inline = c.find("m:is/m:t", NS)
                val = t_inline.text if t_inline is not None else ""
            elif c.get("t") == "s":
                val = shared[int(v.text)]
            else:
                val = v.text or ""
            cells[col] = val.strip()
        if cells:
            width = max(cells)
            rows.append([cells.get(i, "") for i in range(1, width + 1)])
    return rows


def parse_municipios(rows: list[list[str]]) -> list[dict]:
    # Localiza la cabecera (CODAUTO, CPRO, CMUN, DC, NOMBRE), suele ir en la fila 2
    header_idx = None
    for i, r in enumerate(rows[:10]):
        up = [c.upper() for c in r]
        if "CPRO" in up and "CMUN" in up and "NOMBRE" in up:
            header_idx = i
            cols = {name: up.index(name) for name in ("CODAUTO", "CPRO", "CMUN", "NOMBRE")}
            break
    if header_idx is None:
        raise SystemExit("No se encontró la cabecera CODAUTO/CPRO/CMUN/NOMBRE en el xlsx")
    out = []
    for r in rows[header_idx + 1:]:
        try:
            codauto = r[cols["CODAUTO"]].zfill(2)
            cpro = r[cols["CPRO"]].zfill(2)
            cmun = r[cols["CMUN"]].zfill(3)
            nombre_raw = r[cols["NOMBRE"]]
        except IndexError:
            continue
        if not (cpro.isdigit() and cmun.isdigit() and nombre_raw):
            continue
        nombre = ine_display_name(nombre_raw)
        out.append({
            "codigo": cpro + cmun,
            "provincia": cpro,
            "ccaa": codauto,
            "nombre": nombre,
            "nombre_norm": normalize(nombre),
            "nombre_ine": nombre_raw,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="xlsx del INE ya descargado")
    ap.add_argument("--year", type=int, default=dt.date.today().year)
    ap.add_argument("--dry-run", action="store_true")
    parse_db_args(ap)
    args = ap.parse_args()

    if args.file:
        data = Path(args.file).read_bytes()
        origen = args.file
    else:
        url = INE_URL.format(yy=str(args.year)[-2:])
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 ViajeroAnimalista-Geo/0.1"},
                      follow_redirects=True, timeout=60)
        r.raise_for_status()
        data, origen = r.content, url

    municipios = parse_municipios(read_xlsx_rows(data))
    por_ccaa: dict[str, int] = {}
    for m in municipios:
        por_ccaa[m["ccaa"]] = por_ccaa.get(m["ccaa"], 0) + 1
    print(f"Origen: {origen}")
    print(f"Municipios parseados: {len(municipios)}")
    print("Por CCAA: " + ", ".join(f"{k}:{v}" for k, v in sorted(por_ccaa.items())))
    ejemplos = [m for m in municipios if m["codigo"] in ("08121", "15030", "35016", "28079")]
    for m in ejemplos:
        print(f"  {m['codigo']} {m['nombre']!r} (INE: {m['nombre_ine']!r}) norm={m['nombre_norm']!r}")

    if args.dry_run:
        print("--dry-run: no se escribe en BD")
        return

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM GEO_PROVINCIAS")
            if cur.fetchone()[0] < 52:
                raise SystemExit("GEO_PROVINCIAS vacía: ejecuta SQL/animalista/seed_geo.sql antes")
            cur.executemany(
                """
                INSERT INTO GEO_MUNICIPIOS (Codigo_INE, Nombre, Nombre_Norm, Nombre_INE, Codigo_Provincia)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    Nombre = VALUES(Nombre), Nombre_Norm = VALUES(Nombre_Norm),
                    Nombre_INE = VALUES(Nombre_INE), Codigo_Provincia = VALUES(Codigo_Provincia)
                """,
                [(m["codigo"], m["nombre"], m["nombre_norm"], m["nombre_ine"], m["provincia"]) for m in municipios],
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM GEO_MUNICIPIOS")
            print(f"GEO_MUNICIPIOS: {cur.fetchone()[0]} filas")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
