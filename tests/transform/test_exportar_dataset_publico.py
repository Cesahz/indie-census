#suite de pruebas para exportador de dataset publico
#cubre f4-04: exportacion dual (parquet + csv) y manifiesto checksums sha-256
#sin acceso a red, sin reloj real, escrituras aisladas en tmp_path
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.transform.exportar_dataset_publico import (
    ChecksumInvalidoError,
    exportar_dataset_publico,
    verificar_manifiesto_checksums,
)

TABLAS_SINTETICAS = [
    ("plata", "plata_steam_catalogo_limpio"),
    ("plata", "plata_steam_metricas_limpias"),
    ("oro", "gold_engine_adoption_monthly"),
    ("oro", "gold_pricing_by_genre"),
    ("oro", "gold_market_saturation_monthly"),
]


@pytest.fixture
def entorno_datos_sinteticos(tmp_path: Path) -> tuple[Path, Path, Path]:
    #crear directorios temporales de plata, oro y destino
    ruta_plata = tmp_path / "plata"
    ruta_oro = tmp_path / "oro" / "mart"
    ruta_destino = tmp_path / "publico"
    ruta_plata.mkdir(parents=True)
    ruta_oro.mkdir(parents=True)
    ruta_destino.mkdir(parents=True)

    #tabla sintetica plata catalogo
    esquema_catalogo = pa.schema([
        ("appid", pa.int64()),
        ("nombre", pa.string()),
        ("es_indie", pa.bool_()),
    ])
    tabla_catalogo = pa.Table.from_arrays([
        pa.array([10, 20, 30], type=pa.int64()),
        pa.array(["Juego A", "Juego B", "Juego C"], type=pa.string()),
        pa.array([True, True, False], type=pa.bool_()),
    ], schema=esquema_catalogo)
    pq.write_table(tabla_catalogo, ruta_plata / "plata_steam_catalogo_limpio.parquet")

    #tabla sintetica plata metricas
    esquema_metricas = pa.schema([
        ("appid", pa.int64()),
        ("precio_centavos_usd", pa.int64()),
        ("copias_estimadas", pa.int64()),
    ])
    tabla_metricas = pa.Table.from_arrays([
        pa.array([10, 20, 30], type=pa.int64()),
        pa.array([1999, 999, 4999], type=pa.int64()),
        pa.array([1500, 300, 10000], type=pa.int64()),
    ], schema=esquema_metricas)
    pq.write_table(tabla_metricas, ruta_plata / "plata_steam_metricas_limpias.parquet")

    #tabla sintetica oro adopcion motores
    esquema_motores = pa.schema([
        ("anio_mes", pa.string()),
        ("motor", pa.string()),
        ("total_lanzamientos", pa.int64()),
    ])
    tabla_motores = pa.Table.from_arrays([
        pa.array(["2025-01", "2025-01"], type=pa.string()),
        pa.array(["Godot", "Unity"], type=pa.string()),
        pa.array([45, 120], type=pa.int64()),
    ], schema=esquema_motores)
    pq.write_table(tabla_motores, ruta_oro / "gold_engine_adoption_monthly.parquet")

    #tabla sintetica oro pricing
    esquema_pricing = pa.schema([
        ("genero", pa.string()),
        ("total_juegos", pa.int64()),
        ("precio_promedio_usd", pa.float64()),
    ])
    tabla_pricing = pa.Table.from_arrays([
        pa.array(["Action", "RPG"], type=pa.string()),
        pa.array([50, 25], type=pa.int64()),
        pa.array([14.99, 24.99], type=pa.float64()),
    ], schema=esquema_pricing)
    pq.write_table(tabla_pricing, ruta_oro / "gold_pricing_by_genre.parquet")

    #tabla sintetica oro saturacion
    esquema_sat = pa.schema([
        ("anio_mes", pa.string()),
        ("total_lanzamientos", pa.int64()),
        ("porcentaje_indie", pa.float64()),
    ])
    tabla_sat = pa.Table.from_arrays([
        pa.array(["2025-01"], type=pa.string()),
        pa.array([165], type=pa.int64()),
        pa.array([88.5], type=pa.float64()),
    ], schema=esquema_sat)
    pq.write_table(tabla_sat, ruta_oro / "gold_market_saturation_monthly.parquet")

    return ruta_plata, ruta_oro, ruta_destino


def test_exportar_dataset_publico_genera_archivos_dual_y_checksums(
    entorno_datos_sinteticos: tuple[Path, Path, Path]
) -> None:
    #verificar exportacion dual parquet + csv y creacion de checksums
    ruta_plata, ruta_oro, ruta_destino = entorno_datos_sinteticos

    reporte = exportar_dataset_publico(
        ruta_plata=ruta_plata,
        ruta_oro=ruta_oro,
        ruta_destino=ruta_destino,
        version="v0.4.0",
        tablas=TABLAS_SINTETICAS,
    )

    assert reporte["version"] == "v0.4.0"
    assert reporte["total_tablas"] == 5

    dir_parquet = ruta_destino / "v0.4.0" / "parquet"
    dir_csv = ruta_destino / "v0.4.0" / "csv"
    archivo_checksums = ruta_destino / "v0.4.0" / "checksums.sha256"

    assert dir_parquet.is_dir()
    assert dir_csv.is_dir()
    assert archivo_checksums.is_file()

    for _, tabla in TABLAS_SINTETICAS:
        assert (dir_parquet / f"{tabla}.parquet").is_file()
        assert (dir_csv / f"{tabla}.csv").is_file()


def test_verificar_manifiesto_checksums_exito(
    entorno_datos_sinteticos: tuple[Path, Path, Path]
) -> None:
    #verificar que el validador aprueba un manifiesto integro
    ruta_plata, ruta_oro, ruta_destino = entorno_datos_sinteticos

    reporte = exportar_dataset_publico(
        ruta_plata=ruta_plata,
        ruta_oro=ruta_oro,
        ruta_destino=ruta_destino,
        version="v0.4.0",
        tablas=TABLAS_SINTETICAS,
    )
    manifiesto = Path(reporte["manifiesto_checksums"])

    valido = verificar_manifiesto_checksums(manifiesto)
    assert valido is True


def test_verificar_manifiesto_checksums_detecta_corrupcion(
    entorno_datos_sinteticos: tuple[Path, Path, Path]
) -> None:
    #verificar que se levanta error ante alteracion de contenido
    ruta_plata, ruta_oro, ruta_destino = entorno_datos_sinteticos

    reporte = exportar_dataset_publico(
        ruta_plata=ruta_plata,
        ruta_oro=ruta_oro,
        ruta_destino=ruta_destino,
        version="v0.4.0",
        tablas=TABLAS_SINTETICAS,
    )
    manifiesto = Path(reporte["manifiesto_checksums"])

    #corromper uno de los archivos csv alterando su contenido
    archivo_csv = ruta_destino / "v0.4.0" / "csv" / "gold_pricing_by_genre.csv"
    with open(archivo_csv, "a", encoding="utf-8") as f:
        f.write("\ncorrupcion_de_datos,999,999.99")

    with pytest.raises(ChecksumInvalidoError) as exc_info:
        verificar_manifiesto_checksums(manifiesto)

    assert "gold_pricing_by_genre.csv" in str(exc_info.value)


def test_exportar_dataset_publico_preserva_filas_y_esquema(
    entorno_datos_sinteticos: tuple[Path, Path, Path]
) -> None:
    #verificar que el conteo de filas se mantiene identico
    ruta_plata, ruta_oro, ruta_destino = entorno_datos_sinteticos

    exportar_dataset_publico(
        ruta_plata=ruta_plata,
        ruta_oro=ruta_oro,
        ruta_destino=ruta_destino,
        version="v0.4.0",
        tablas=TABLAS_SINTETICAS,
    )

    archivo_parquet_exportado = ruta_destino / "v0.4.0" / "parquet" / "gold_engine_adoption_monthly.parquet"
    tabla = pq.read_table(archivo_parquet_exportado)
    assert len(tabla) == 2
    assert "motor" in tabla.column_names
