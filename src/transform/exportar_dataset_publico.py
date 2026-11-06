#modulo de exportacion dual y manifiesto de checksums para dataset publico
#cubre f4-04: exportacion en formatos parquet y csv con verificacion criptografica
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

import pyarrow as pa
import pyarrow.csv as pc
import pyarrow.parquet as pq


class ChecksumInvalidoError(Exception):
    """Excepcion levantada cuando un archivo exportado no coincide con su hash SHA-256."""


TABLAS_PUBLICAS_POR_DEFECTO = [
    ("plata", "dim_game"),
    ("plata", "game_review_summary"),
    ("oro", "fact_game_performance"),
    ("oro", "gold_engine_adoption_monthly"),
    ("oro", "gold_pricing_by_genre"),
    ("oro", "gold_market_saturation_monthly"),
]

ALIAS_TABLAS: dict[str, list[str]] = {
    "dim_game": ["dim_game", "plata_steam_catalogo_limpio"],
    "game_review_summary": ["game_review_summary", "plata_steam_metricas_limpias"],
    "plata_steam_catalogo_limpio": ["plata_steam_catalogo_limpio", "dim_game"],
    "plata_steam_metricas_limpias": ["plata_steam_metricas_limpias", "game_review_summary"],
}


def calcular_sha256_archivo(ruta: Path) -> str:
    #calcular hash sha256 de un archivo en bloques
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def preparar_tabla_para_csv(tabla: pa.Table) -> pa.Table:
    #convertir columnas anidadas de lista a string json para exportacion csv
    nuevas_columnas = []
    for nombre in tabla.column_names:
        col = tabla[nombre]
        if pa.types.is_list(col.type):
            valores_serializados = [
                json.dumps(x.as_py(), ensure_ascii=False) if x.as_py() is not None else ""
                for x in col
            ]
            nuevas_columnas.append(pa.array(valores_serializados, type=pa.string()))
        else:
            nuevas_columnas.append(col)
    return pa.Table.from_arrays(nuevas_columnas, names=tabla.column_names)


def _localizar_archivo_origen(directorio_base: Path, nombre_tabla: str) -> Path:
    #buscar archivo parquet en directorio base, subdirectorios steam o mart considerando alias
    nombres_a_buscar = ALIAS_TABLAS.get(nombre_tabla, [nombre_tabla])
    subdirectorios = [directorio_base, directorio_base / "mart", directorio_base / "steam"]

    for sub in subdirectorios:
        for nombre in nombres_a_buscar:
            ruta = sub / f"{nombre}.parquet"
            if ruta.is_file():
                return ruta

    raise FileNotFoundError(
        f"No se encontro el archivo parquet para la tabla '{nombre_tabla}' (alias probados: {nombres_a_buscar}) en {directorio_base}."
    )


def exportar_dataset_publico(
    ruta_plata: Path,
    ruta_oro: Path,
    ruta_destino: Path,
    version: str = "v0.4.0",
    tablas: Optional[list[tuple[str, str]]] = None,
) -> dict[str, Any]:
    """Exporta las tablas maestras de las capas Plata y Oro a Parquet y CSV con manifiesto SHA-256."""
    dir_version = ruta_destino / version
    dir_parquet = dir_version / "parquet"
    dir_csv = dir_version / "csv"

    dir_parquet.mkdir(parents=True, exist_ok=True)
    dir_csv.mkdir(parents=True, exist_ok=True)

    tablas_a_procesar = tablas or TABLAS_PUBLICAS_POR_DEFECTO
    archivos_generados: list[dict[str, Any]] = []
    lineas_manifiesto: list[str] = []

    for capa, nombre_tabla in tablas_a_procesar:
        directorio_fuente = ruta_plata if capa == "plata" else ruta_oro
        ruta_fuente = _localizar_archivo_origen(directorio_fuente, nombre_tabla)

        #cargar tabla original
        tabla = pq.read_table(ruta_fuente)
        filas = len(tabla)

        #exportar parquet de forma atomica
        ruta_dest_parquet = dir_parquet / f"{nombre_tabla}.parquet"
        ruta_tmp_parquet = dir_parquet / f"{nombre_tabla}.parquet.tmp"
        pq.write_table(tabla, ruta_tmp_parquet)
        os.replace(ruta_tmp_parquet, ruta_dest_parquet)
        hash_parquet = calcular_sha256_archivo(ruta_dest_parquet)
        bytes_parquet = ruta_dest_parquet.stat().st_size

        archivos_generados.append({
            "tabla": nombre_tabla,
            "capa": capa,
            "formato": "parquet",
            "ruta": str(ruta_dest_parquet),
            "sha256": hash_parquet,
            "filas": filas,
            "bytes": bytes_parquet,
        })
        lineas_manifiesto.append(f"{hash_parquet}  parquet/{nombre_tabla}.parquet")

        #exportar csv de forma atomica
        tabla_csv = preparar_tabla_para_csv(tabla)
        ruta_dest_csv = dir_csv / f"{nombre_tabla}.csv"
        ruta_tmp_csv = dir_csv / f"{nombre_tabla}.csv.tmp"
        pc.write_csv(tabla_csv, ruta_tmp_csv)
        os.replace(ruta_tmp_csv, ruta_dest_csv)
        hash_csv = calcular_sha256_archivo(ruta_dest_csv)
        bytes_csv = ruta_dest_csv.stat().st_size

        archivos_generados.append({
            "tabla": nombre_tabla,
            "capa": capa,
            "formato": "csv",
            "ruta": str(ruta_dest_csv),
            "sha256": hash_csv,
            "filas": filas,
            "bytes": bytes_csv,
        })
        lineas_manifiesto.append(f"{hash_csv}  csv/{nombre_tabla}.csv")

    #escribir manifiesto checksums.sha256 de forma atomica
    ruta_manifiesto = dir_version / "checksums.sha256"
    ruta_tmp_manifiesto = dir_version / "checksums.sha256.tmp"
    with open(ruta_tmp_manifiesto, "w", encoding="utf-8") as f:
        for linea in lineas_manifiesto:
            f.write(linea + "\n")
    os.replace(ruta_tmp_manifiesto, ruta_manifiesto)

    return {
        "version": version,
        "directorio_salida": str(dir_version),
        "total_tablas": len(tablas_a_procesar),
        "archivos_generados": archivos_generados,
        "manifiesto_checksums": str(ruta_manifiesto),
    }


def verificar_manifiesto_checksums(ruta_manifiesto: Path) -> bool:
    """Verifica que cada archivo listado en el manifiesto coincida exactamente con su hash SHA-256."""
    if not ruta_manifiesto.is_file():
        raise FileNotFoundError(f"No existe el archivo de manifiesto en: {ruta_manifiesto}")

    directorio_base = ruta_manifiesto.parent

    with open(ruta_manifiesto, "r", encoding="utf-8") as f:
        lineas = [linea.strip() for linea in f if linea.strip()]

    for linea in lineas:
        partes = linea.split(maxsplit=1)
        if len(partes) != 2:
            raise ChecksumInvalidoError(f"Formato de linea de manifiesto no reconocido: '{linea}'")

        hash_esperado, rel_path = partes
        ruta_archivo = directorio_base / rel_path

        if not ruta_archivo.is_file():
            raise ChecksumInvalidoError(f"El archivo referenciado no existe: '{rel_path}'")

        hash_calculado = calcular_sha256_archivo(ruta_archivo)
        if hash_calculado != hash_esperado:
            raise ChecksumInvalidoError(
                f"Discrepancia en checksum para '{rel_path}': esperado {hash_esperado}, calculado {hash_calculado}"
            )

    return True
