#suite de contrato para la transformacion de capa plata a capa oro (star schema y data mart)
#sin acceso a red: plata sintetica construida en tmp_path con esquemas arrow estrictos
import sqlite3
from pathlib import Path

# pyrefly: ignore [missing-import]
import pyarrow as pa
# pyrefly: ignore [missing-import]
import pyarrow.parquet as pq
# pyrefly: ignore [missing-import]
import pytest

from src.transform.oro import (
    ESQUEMA_DIM_DATE,
    ESQUEMA_DIM_GAME_ORO,
    ESQUEMA_DIM_GENRE_BRIDGE,
    ESQUEMA_FACT_GAME_PERFORMANCE,
    construir_tablas_oro,
    ejecutar_transformacion_oro,
    exportar_a_sqlite,
    persistir_mart_parquet,
)
from src.transform.plata import ESQUEMA_DIM_GAME, ESQUEMA_GAME_REVIEW_SUMMARY


def _crear_tablas_plata_sinteticas() -> tuple[pa.Table, pa.Table]:
    """Generar tablas de plata sinteticas con casos tipicos y borde."""
    datos_dim = {
        "game_id": [101, 102, 103],
        "title": ["Juego Alpha", "Juego Beta Gratis", "Juego Gamma"],
        "release_date": ["2024-05-29", "2024-05-29", "2025-01-15"],
        "is_free": [False, True, False],
        "price_launch_usd_cents": [1999, None, 999],
        "genres": [["Action", "Indie"], ["Free to Play"], []],
        "language_count": [5, 2, 1],
        "developers": [["Dev Uno", "Dev Dos"], ["Dev Gratis"], []],
        "publishers": [["Pub Uno"], [], []],
        "group": ["godot", "general", "godot"],
        "engine": ["godot", "unity", "godot"],
        "engine_evidence_level": [1, None, 2],
        "indie_score": [0.85, 0.70, 0.90],
        "is_indie": [True, True, True],
        "ai_disclosure_level": ["unknown", "unknown", "tagged"],
        "source": ["steam", "steam", "steam"],
        "extracted_at": ["2026-10-01T12:00:00Z"] * 3,
        "pipeline_version": ["0.1.0"] * 3,
    }
    datos_reviews = {
        "game_id": [101, 102, 103],
        "total_positive": [90, 10, 0],
        "total_negative": [10, 0, 0],
        "total_reviews": [100, 10, 0],
        "extracted_at": ["2026-10-01T12:00:00Z"] * 3,
        "pipeline_version": ["0.1.0"] * 3,
    }
    tabla_dim = pa.Table.from_pydict(datos_dim, schema=ESQUEMA_DIM_GAME)
    tabla_reviews = pa.Table.from_pydict(datos_reviews, schema=ESQUEMA_GAME_REVIEW_SUMMARY)
    return tabla_dim, tabla_reviews


def test_esquemas_arrow_oro_definidos() -> None:
    #los esquemas deben contener todos los campos declarados en el contrato
    campos_fact = set(ESQUEMA_FACT_GAME_PERFORMANCE.names)
    assert "game_id" in campos_fact
    assert "release_date_key" in campos_fact
    assert "price_usd" in campos_fact
    assert "approval_rate" in campos_fact
    assert "est_copies_mid" in campos_fact
    assert "est_gross_revenue_usd" in campos_fact

    campos_dim_game = set(ESQUEMA_DIM_GAME_ORO.names)
    assert "game_id" in campos_dim_game
    assert "primary_developer" in campos_dim_game
    assert "primary_publisher" in campos_dim_game
    assert "engine" in campos_dim_game
    assert "indie_score" in campos_dim_game
    assert "is_indie" in campos_dim_game
    assert "ai_disclosure_level" in campos_dim_game

    campos_bridge = set(ESQUEMA_DIM_GENRE_BRIDGE.names)
    assert campos_bridge == {"game_id", "genre"}

    campos_date = set(ESQUEMA_DIM_DATE.names)
    assert "date_key" in campos_date
    assert "is_weekend" in campos_date


def test_construir_tablas_oro_metricas_y_relaciones() -> None:
    #transformacion en memoria: calculo exacto de metricas y aplanamiento de genero
    tabla_dim, tabla_reviews = _crear_tablas_plata_sinteticas()
    mart = construir_tablas_oro(tabla_dim, tabla_reviews)

    assert set(mart.keys()) == {
        "fact_game_performance",
        "dim_game",
        "dim_date",
        "dim_genre_bridge",
    }

    fact = mart["fact_game_performance"].to_pydict()
    #verificar juego 101: 1999 centavos = 19.99 usd, 90/100 = 0.9 approval
    idx_101 = fact["game_id"].index(101)
    assert fact["price_usd"][idx_101] == 19.99
    assert fact["is_free"][idx_101] is False
    assert fact["total_reviews"][idx_101] == 100
    assert fact["approval_rate"][idx_101] == 0.9
    assert fact["est_copies_min"][idx_101] == 3000
    assert fact["est_copies_mid"][idx_101] == 4000
    assert fact["est_copies_max"][idx_101] == 6000
    assert round(fact["est_gross_revenue_usd"][idx_101], 2) == round(4000 * 19.99, 2)
    assert fact["release_date_key"][idx_101] == 20240529

    #verificar juego 102 (gratuito)
    idx_102 = fact["game_id"].index(102)
    assert fact["price_usd"][idx_102] == 0.0
    assert fact["is_free"][idx_102] is True
    assert fact["est_gross_revenue_usd"][idx_102] == 0.0

    #verificar juego 103 (cero resenas)
    idx_103 = fact["game_id"].index(103)
    assert fact["total_reviews"][idx_103] == 0
    assert fact["approval_rate"][idx_103] == 0.0
    assert fact["est_copies_mid"][idx_103] == 0

    #verificar dimension fecha (2 fechas unicas: 2024-05-29 y 2025-01-15)
    dim_date = mart["dim_date"].to_pydict()
    assert set(dim_date["date_key"]) == {20240529, 20250115}
    idx_date = dim_date["date_key"].index(20240529)
    assert dim_date["year"][idx_date] == 2024
    assert dim_date["month"][idx_date] == 5
    assert dim_date["month_name"][idx_date] == "May"
    assert dim_date["day_of_week"][idx_date] == "Wednesday"
    assert dim_date["is_weekend"][idx_date] is False

    #verificar tabla puente generos (juego 101 tiene Action e Indie; juego 102 tiene Free to Play)
    bridge = mart["dim_genre_bridge"].to_pydict()
    pares = list(zip(bridge["game_id"], bridge["genre"]))
    assert (101, "Action") in pares
    assert (101, "Indie") in pares
    assert (102, "Free to Play") in pares
    assert all(gid != 103 for gid, _ in pares)


def test_integridad_referencial_oro() -> None:
    #toda clave foranea de fact y bridge debe existir en las dimensiones
    tabla_dim, tabla_reviews = _crear_tablas_plata_sinteticas()
    mart = construir_tablas_oro(tabla_dim, tabla_reviews)

    ids_juegos = set(mart["dim_game"]["game_id"].to_pylist())
    ids_fact = set(mart["fact_game_performance"]["game_id"].to_pylist())
    ids_bridge = set(mart["dim_genre_bridge"]["game_id"].to_pylist())

    assert ids_fact == ids_juegos
    assert ids_bridge.issubset(ids_juegos)

    fechas_keys = set(mart["dim_date"]["date_key"].to_pylist())
    fechas_fact = set(mart["fact_game_performance"]["release_date_key"].to_pylist())
    assert fechas_fact.issubset(fechas_keys)


def test_persistir_mart_parquet_atomico(tmp_path: Path) -> None:
    #la persistencia debe escribir todos los archivos parquet de forma atomica
    tabla_dim, tabla_reviews = _crear_tablas_plata_sinteticas()
    mart = construir_tablas_oro(tabla_dim, tabla_reviews)

    ruta_mart = tmp_path / "oro" / "mart"
    persistir_mart_parquet(mart, ruta_mart)

    for nombre in [
        "fact_game_performance.parquet",
        "dim_game.parquet",
        "dim_date.parquet",
        "dim_genre_bridge.parquet",
    ]:
        archivo = ruta_mart / nombre
        assert archivo.is_file(), f"archivo ausente en mart: {nombre}"
        #verificar que es legible como parquet valido
        tabla_leida = pq.read_table(archivo)
        assert len(tabla_leida) > 0


def test_exportar_a_sqlite(tmp_path: Path) -> None:
    #la exportacion a sqlite debe generar base valida consultable por sql
    tabla_dim, tabla_reviews = _crear_tablas_plata_sinteticas()
    mart = construir_tablas_oro(tabla_dim, tabla_reviews)

    ruta_sqlite = tmp_path / "oro" / "indie_census_mart.db"
    exportar_a_sqlite(mart, ruta_sqlite)

    assert ruta_sqlite.is_file()

    conexion = sqlite3.connect(ruta_sqlite)
    cursor = conexion.cursor()

    #verificar tablas creadas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tablas = {fila[0] for fila in cursor.fetchall()}
    assert {
        "fact_game_performance",
        "dim_game",
        "dim_date",
        "dim_genre_bridge",
    }.issubset(tablas)

    #verificar consulta relacional con join entre hecho y dimensiones
    cursor.execute("""
        SELECT f.game_id, d.title, dt.year, f.price_usd, f.est_copies_mid, d.engine, d.indie_score, d.is_indie
        FROM fact_game_performance f
        JOIN dim_game d ON f.game_id = d.game_id
        JOIN dim_date dt ON f.release_date_key = dt.date_key
        WHERE f.game_id = 101;
    """)
    fila = cursor.fetchone()
    assert fila is not None
    assert fila[0] == 101
    assert fila[1] == "Juego Alpha"
    assert fila[2] == 2024
    assert fila[3] == 19.99
    assert fila[4] == 4000
    assert fila[5] == "godot"
    assert fila[6] == 0.85
    assert fila[7] == 1
    conexion.close()


def test_ejecutar_transformacion_oro_completa(tmp_path: Path) -> None:
    #flujo de punta a punta: lee plata desde disco y escribe mart y sqlite
    ruta_plata = tmp_path / "plata"
    ruta_plata.mkdir(parents=True)
    tabla_dim, tabla_reviews = _crear_tablas_plata_sinteticas()
    pq.write_table(tabla_dim, ruta_plata / "dim_game.parquet")
    pq.write_table(tabla_reviews, ruta_plata / "game_review_summary.parquet")

    ruta_oro = tmp_path / "oro"
    conteo = ejecutar_transformacion_oro(ruta_plata, ruta_oro, generar_sqlite=True)

    assert conteo["fact_game_performance"] == 3
    assert conteo["dim_game"] == 3
    assert conteo["dim_date"] == 2
    assert conteo["dim_genre_bridge"] == 3

    assert (ruta_oro / "mart" / "fact_game_performance.parquet").is_file()
    assert (ruta_oro / "indie_census_mart.db").is_file()


def test_ejecutar_transformacion_oro_error_si_falta_plata(tmp_path: Path) -> None:
    #debe levantar FileNotFoundError si no existen las tablas de plata
    ruta_vacia = tmp_path / "plata_inexistente"
    ruta_vacia.mkdir()
    with pytest.raises(FileNotFoundError):
        ejecutar_transformacion_oro(ruta_vacia, tmp_path / "oro")
