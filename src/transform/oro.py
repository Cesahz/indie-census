#modulo de transformacion de capa plata a capa oro analitica (star schema y data mart)
#regla: esquemas arrow explicitos, salida dimensional normalizada y persistencia atomica
import os
import shutil
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

# pyrefly: ignore [missing-import]
import pyarrow as pa
# pyrefly: ignore [missing-import]
import pyarrow.parquet as pq

from src.transform.plata import ARCHIVO_DIM_GAME, ARCHIVO_GAME_REVIEW_SUMMARY

#nombres de los meses y dias en ingles independientes de locale
_NOMBRES_MESES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_NOMBRES_DIAS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]

#esquemas arrow explicitos para la capa oro

ESQUEMA_DIM_GAME_ORO = pa.schema([
    pa.field("game_id", pa.int64(), nullable=False),
    pa.field("title", pa.string()),
    pa.field("release_date", pa.string()),
    pa.field("group", pa.string()),
    pa.field("engine_evidence_level", pa.int8()),
    pa.field("primary_developer", pa.string()),
    pa.field("primary_publisher", pa.string()),
    pa.field("is_free", pa.bool_()),
])

ESQUEMA_DIM_DATE = pa.schema([
    pa.field("date_key", pa.int32(), nullable=False),
    pa.field("full_date", pa.string()),
    pa.field("year", pa.int32()),
    pa.field("quarter", pa.int32()),
    pa.field("month", pa.int32()),
    pa.field("month_name", pa.string()),
    pa.field("day", pa.int32()),
    pa.field("day_of_week", pa.string()),
    pa.field("is_weekend", pa.bool_()),
])

ESQUEMA_DIM_GENRE_BRIDGE = pa.schema([
    pa.field("game_id", pa.int64(), nullable=False),
    pa.field("genre", pa.string(), nullable=False),
])

ESQUEMA_FACT_GAME_PERFORMANCE = pa.schema([
    pa.field("game_id", pa.int64(), nullable=False),
    pa.field("release_date_key", pa.int32(), nullable=False),
    pa.field("price_usd", pa.float64()),
    pa.field("is_free", pa.bool_()),
    pa.field("total_positive", pa.int64()),
    pa.field("total_negative", pa.int64()),
    pa.field("total_reviews", pa.int64()),
    pa.field("approval_rate", pa.float64()),
    pa.field("est_copies_min", pa.int64()),
    pa.field("est_copies_mid", pa.int64()),
    pa.field("est_copies_max", pa.int64()),
    pa.field("est_gross_revenue_usd", pa.float64()),
    pa.field("language_count", pa.int32()),
])


def _calcular_date_key(fecha_iso: str) -> int:
    """Convertir fecha iso AAAA-MM-DD a entero AAAAMMDD."""
    return int(fecha_iso.replace("-", ""))


def _generar_fila_fecha(fecha_iso: str) -> dict[str, Any]:
    """Generar atributos del calendario para una fecha iso dada."""
    d = date.fromisoformat(fecha_iso)
    return {
        "date_key": _calcular_date_key(fecha_iso),
        "full_date": fecha_iso,
        "year": d.year,
        "quarter": (d.month - 1) // 3 + 1,
        "month": d.month,
        "month_name": _NOMBRES_MESES[d.month - 1],
        "day": d.day,
        "day_of_week": _NOMBRES_DIAS[d.weekday()],
        "is_weekend": d.weekday() >= 5,
    }


def construir_tablas_oro(
    tabla_dim_plata: pa.Table,
    tabla_reviews_plata: pa.Table,
) -> dict[str, pa.Table]:
    """Construir tablas del star schema en memoria a partir de los datos de plata.

    Genera dim_game, dim_date, dim_genre_bridge y fact_game_performance.
    """
    dict_dim = tabla_dim_plata.to_pydict()
    dict_rev = tabla_reviews_plata.to_pydict()

    #indexar resenas por game_id para cruce rapido O(1)
    rev_por_id: dict[int, dict[str, int]] = {}
    for i in range(len(dict_rev["game_id"])):
        gid = dict_rev["game_id"][i]
        rev_por_id[gid] = {
            "total_positive": dict_rev["total_positive"][i] or 0,
            "total_negative": dict_rev["total_negative"][i] or 0,
            "total_reviews": dict_rev["total_reviews"][i] or 0,
        }

    #listas de acumulacion para dimensiones y hechos
    filas_dim_game: list[dict[str, Any]] = []
    filas_bridge: list[dict[str, Any]] = []
    filas_fact: list[dict[str, Any]] = []
    fechas_unicas: set[str] = set()

    for i in range(len(dict_dim["game_id"])):
        gid = dict_dim["game_id"][i]
        title = dict_dim["title"][i]
        release_date = dict_dim["release_date"][i]
        is_free = bool(dict_dim["is_free"][i])
        price_cents = dict_dim["price_launch_usd_cents"][i]
        genres = dict_dim["genres"][i] or []
        lang_count = dict_dim["language_count"][i] or 0
        devs = dict_dim["developers"][i] or []
        pubs = dict_dim["publishers"][i] or []
        group = dict_dim["group"][i]
        evidence = dict_dim["engine_evidence_level"][i]

        primary_dev = devs[0] if len(devs) > 0 else None
        primary_pub = pubs[0] if len(pubs) > 0 else None

        #1. dimension juego
        filas_dim_game.append({
            "game_id": gid,
            "title": title,
            "release_date": release_date,
            "group": group,
            "engine_evidence_level": evidence,
            "primary_developer": primary_dev,
            "primary_publisher": primary_pub,
            "is_free": is_free,
        })

        #2. registrar fecha para dimension calendario
        if release_date:
            fechas_unicas.add(release_date)
            date_key = _calcular_date_key(release_date)
        else:
            date_key = 19700101

        #3. tabla puente de generos desanidada
        for g in genres:
            filas_bridge.append({"game_id": gid, "genre": str(g)})

        #4. metricas financieras y de resenas
        rev = rev_por_id.get(gid, {"total_positive": 0, "total_negative": 0, "total_reviews": 0})
        pos = rev["total_positive"]
        neg = rev["total_negative"]
        tot = rev["total_reviews"]

        price_usd = 0.0 if (is_free or price_cents is None) else round(price_cents / 100.0, 2)
        approval = round(pos / tot, 4) if tot > 0 else 0.0

        copies_min = tot * 30
        copies_mid = tot * 40
        copies_max = tot * 60
        gross_rev = round(copies_mid * price_usd, 2)

        filas_fact.append({
            "game_id": gid,
            "release_date_key": date_key,
            "price_usd": price_usd,
            "is_free": is_free,
            "total_positive": pos,
            "total_negative": neg,
            "total_reviews": tot,
            "approval_rate": approval,
            "est_copies_min": copies_min,
            "est_copies_mid": copies_mid,
            "est_copies_max": copies_max,
            "est_gross_revenue_usd": gross_rev,
            "language_count": lang_count,
        })

    #5. dimension fecha a partir de las fechas unicas observadas
    filas_dim_date = [_generar_fila_fecha(f) for f in sorted(fechas_unicas)]

    #convertir a tablas pyarrow con esquemas estrictos
    tabla_dim_game = pa.Table.from_pylist(filas_dim_game, schema=ESQUEMA_DIM_GAME_ORO)
    tabla_dim_date = pa.Table.from_pylist(filas_dim_date, schema=ESQUEMA_DIM_DATE)
    tabla_bridge = pa.Table.from_pylist(filas_bridge, schema=ESQUEMA_DIM_GENRE_BRIDGE)
    tabla_fact = pa.Table.from_pylist(filas_fact, schema=ESQUEMA_FACT_GAME_PERFORMANCE)

    return {
        "dim_game": tabla_dim_game,
        "dim_date": tabla_dim_date,
        "dim_genre_bridge": tabla_bridge,
        "fact_game_performance": tabla_fact,
    }


def persistir_mart_parquet(mart: dict[str, pa.Table], ruta_mart: Path) -> None:
    """Guardar las tablas del star schema en archivos parquet de forma atomica."""
    ruta_mart.mkdir(parents=True, exist_ok=True)
    ruta_tmp = ruta_mart / ".tmp_mart"
    if ruta_tmp.exists():
        shutil.rmtree(ruta_tmp)
    ruta_tmp.mkdir(parents=True)

    try:
        for nombre, tabla in mart.items():
            pq.write_table(tabla, ruta_tmp / f"{nombre}.parquet", compression="snappy")

        #mover archivos de temporal al destino definitivo de forma atomica
        for nombre in mart.keys():
            destino = ruta_mart / f"{nombre}.parquet"
            origen = ruta_tmp / f"{nombre}.parquet"
            os.replace(origen, destino)
    finally:
        if ruta_tmp.exists():
            shutil.rmtree(ruta_tmp, ignore_errors=True)


def exportar_a_sqlite(mart: dict[str, pa.Table], ruta_sqlite: Path) -> None:
    """Exportar el data mart a una base de datos SQLite monousuario con esquema relacional."""
    ruta_sqlite.parent.mkdir(parents=True, exist_ok=True)
    ruta_tmp = ruta_sqlite.with_suffix(".tmp.db")
    if ruta_tmp.exists():
        ruta_tmp.unlink()

    conexion = sqlite3.connect(ruta_tmp)
    cursor = conexion.cursor()

    try:
        #crear esquema ddl relacional con claves primarias y foraneas
        cursor.executescript("""
            CREATE TABLE dim_date (
                date_key INTEGER PRIMARY KEY,
                full_date TEXT,
                year INTEGER,
                quarter INTEGER,
                month INTEGER,
                month_name TEXT,
                day INTEGER,
                day_of_week TEXT,
                is_weekend INTEGER
            );

            CREATE TABLE dim_game (
                game_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                release_date TEXT,
                "group" TEXT,
                engine_evidence_level INTEGER,
                primary_developer TEXT,
                primary_publisher TEXT,
                is_free INTEGER
            );

            CREATE TABLE dim_genre_bridge (
                game_id INTEGER,
                genre TEXT,
                PRIMARY KEY (game_id, genre),
                FOREIGN KEY (game_id) REFERENCES dim_game (game_id)
            );

            CREATE TABLE fact_game_performance (
                game_id INTEGER PRIMARY KEY,
                release_date_key INTEGER,
                price_usd REAL,
                is_free INTEGER,
                total_positive INTEGER,
                total_negative INTEGER,
                total_reviews INTEGER,
                approval_rate REAL,
                est_copies_min INTEGER,
                est_copies_mid INTEGER,
                est_copies_max INTEGER,
                est_gross_revenue_usd REAL,
                language_count INTEGER,
                FOREIGN KEY (game_id) REFERENCES dim_game (game_id),
                FOREIGN KEY (release_date_key) REFERENCES dim_date (date_key)
            );
        """)

        #insercion masiva por tabla a partir de los datos en memoria
        #1. dim_date
        d_date = mart["dim_date"].to_pylist()
        cursor.executemany(
            """INSERT INTO dim_date VALUES (
                :date_key, :full_date, :year, :quarter, :month,
                :month_name, :day, :day_of_week, :is_weekend
            )""",
            d_date,
        )

        #2. dim_game
        d_game = mart["dim_game"].to_pylist()
        cursor.executemany(
            """INSERT INTO dim_game VALUES (
                :game_id, :title, :release_date, :group,
                :engine_evidence_level, :primary_developer,
                :primary_publisher, :is_free
            )""",
            d_game,
        )

        #3. dim_genre_bridge
        d_bridge = mart["dim_genre_bridge"].to_pylist()
        cursor.executemany(
            """INSERT INTO dim_genre_bridge VALUES (:game_id, :genre)""",
            d_bridge,
        )

        #4. fact_game_performance
        d_fact = mart["fact_game_performance"].to_pylist()
        cursor.executemany(
            """INSERT INTO fact_game_performance VALUES (
                :game_id, :release_date_key, :price_usd, :is_free,
                :total_positive, :total_negative, :total_reviews,
                :approval_rate, :est_copies_min, :est_copies_mid,
                :est_copies_max, :est_gross_revenue_usd, :language_count
            )""",
            d_fact,
        )

        conexion.commit()
    finally:
        conexion.close()

    #reemplazo atomico del archivo sqlite
    os.replace(ruta_tmp, ruta_sqlite)


def ejecutar_transformacion_oro(
    ruta_plata: Path,
    ruta_oro: Path,
    generar_sqlite: bool = True,
) -> dict[str, int]:
    """Cargar tablas de plata, construir el star schema y persistir en parquet y opcionalmente sqlite.

    Retorna diccionario con el conteo de filas persistidas por tabla.
    """
    archivo_dim = ruta_plata / ARCHIVO_DIM_GAME
    archivo_rev = ruta_plata / ARCHIVO_GAME_REVIEW_SUMMARY

    if not archivo_dim.is_file() and (ruta_plata / "steam" / ARCHIVO_DIM_GAME).is_file():
        archivo_dim = ruta_plata / "steam" / ARCHIVO_DIM_GAME
        archivo_rev = ruta_plata / "steam" / ARCHIVO_GAME_REVIEW_SUMMARY

    if not archivo_dim.is_file():
        raise FileNotFoundError(f"archivo no encontrado en capa plata: {archivo_dim}")
    if not archivo_rev.is_file():
        raise FileNotFoundError(f"archivo no encontrado en capa plata: {archivo_rev}")

    tabla_dim_plata = pq.read_table(archivo_dim)
    tabla_reviews_plata = pq.read_table(archivo_rev)

    mart = construir_tablas_oro(tabla_dim_plata, tabla_reviews_plata)

    #persistir en data/oro/mart/*.parquet
    persistir_mart_parquet(mart, ruta_oro / "mart")

    #opcionalmente persistir en data/oro/indie_census_mart.db
    if generar_sqlite:
        exportar_a_sqlite(mart, ruta_oro / "indie_census_mart.db")

    return {nombre: len(tabla) for nombre, tabla in mart.items()}
