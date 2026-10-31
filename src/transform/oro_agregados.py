#modulo de construccion de tablas maestras agregadas en capa oro
#calcula agregaciones deterministas para adopcion de motores, pricing y saturacion
import math
import os
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from src.quality.contratos_oro import validar_continuidad_temporal_oro, validar_rango_historico_3sigma
from src.version import PIPELINE_VERSION

#rutas canonicas por defecto del repositorio
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUTA_DATA_DEFAULT = PROJECT_ROOT / "data"

#esquemas arrow explicitos para tablas agregadas en capa oro
ESQUEMA_GOLD_ENGINE_MONTHLY = pa.schema([
    pa.field("year_month", pa.string(), nullable=False),
    pa.field("is_indie", pa.bool_(), nullable=False),
    pa.field("engine", pa.string(), nullable=False),
    pa.field("releases_count", pa.int64(), nullable=False),
    pa.field("monthly_share_pct", pa.float64(), nullable=False),
    pa.field("median_reviews", pa.float64(), nullable=False),
    pa.field("total_net_revenue_usd", pa.float64(), nullable=False),
    pa.field("pipeline_version", pa.string(), nullable=False),
])

ESQUEMA_GOLD_PRICING_GENRE = pa.schema([
    pa.field("genre", pa.string(), nullable=False),
    pa.field("is_indie", pa.bool_(), nullable=False),
    pa.field("games_count", pa.int64(), nullable=False),
    pa.field("free_games_rate", pa.float64(), nullable=False),
    pa.field("price_p25_usd", pa.float64(), nullable=False),
    pa.field("price_median_usd", pa.float64(), nullable=False),
    pa.field("price_p75_usd", pa.float64(), nullable=False),
    pa.field("median_net_revenue_usd", pa.float64(), nullable=False),
    pa.field("pipeline_version", pa.string(), nullable=False),
])

ESQUEMA_GOLD_SATURATION_MONTHLY = pa.schema([
    pa.field("year_month", pa.string(), nullable=False),
    pa.field("genre", pa.string(), nullable=False),
    pa.field("indie_releases_count", pa.int64(), nullable=False),
    pa.field("total_reviews_captured", pa.int64(), nullable=False),
    pa.field("median_reviews_per_release", pa.float64(), nullable=False),
    pa.field("saturation_index", pa.float64(), nullable=False),
    pa.field("pipeline_version", pa.string(), nullable=False),
])


def _mediana(valores: list[float]) -> float:
    """Calcular la mediana de una lista de flotantes de forma determinista."""
    if not valores:
        return 0.0
    s = sorted(valores)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return round(float(s[mid]), 2)
    return round((float(s[mid - 1]) + float(s[mid])) / 2.0, 2)


def _calcular_percentiles(valores: list[float]) -> tuple[float, float, float]:
    """Calcular percentiles P25, P50 (mediana) y P75 con interpolacion determinista."""
    if not valores:
        return 0.0, 0.0, 0.0
    s = sorted(valores)
    n = len(s)
    if n == 1:
        v = round(float(s[0]), 2)
        return v, v, v

    def _pos(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(s[int(k)])
        return float(s[int(f)]) * (c - k) + float(s[int(c)]) * (k - f)

    return round(_pos(0.25), 2), round(_pos(0.50), 2), round(_pos(0.75), 2)


def construir_tablas_oro_agregadas(
    tablas_estrella: dict[str, pa.Table],
    fecha_inicio: date = date(2024, 1, 1),
    fecha_corte: date = date(2026, 10, 1),
    version_pipeline: Optional[str] = None,
) -> dict[str, pa.Table]:
    """Construir en memoria las tres tablas maestras agregadas a partir del star schema."""
    version = version_pipeline if version_pipeline is not None else PIPELINE_VERSION

    dict_dim = tablas_estrella["dim_game"].to_pydict()
    dict_fact = tablas_estrella["fact_game_performance"].to_pydict()
    dict_bridge = tablas_estrella["dim_genre_bridge"].to_pydict()

    #indexar metricas de performance por game_id
    fact_por_id: dict[int, dict[str, Any]] = {}
    total_filas_fact = len(dict_fact["game_id"])
    for i in range(total_filas_fact):
        gid = dict_fact["game_id"][i]
        fact_por_id[gid] = {
            "price_usd": float(dict_fact["price_usd"][i] or 0.0),
            "is_free": bool(dict_fact["is_free"][i]),
            "total_reviews": int(dict_fact["total_reviews"][i] or 0),
            "est_net_revenue_usd": float(dict_fact["est_net_revenue_usd"][i] or 0.0),
        }

    #indexar generos por game_id
    generos_por_id: dict[int, list[str]] = defaultdict(list)
    total_filas_bridge = len(dict_bridge["game_id"])
    for i in range(total_filas_bridge):
        gid = dict_bridge["game_id"][i]
        gen = dict_bridge["genre"][i]
        if gen and str(gen).strip():
            generos_por_id[gid].append(str(gen).strip())

    #filtrar juegos en ventana [fecha_inicio, fecha_corte]
    juegos_filtrados: list[dict[str, Any]] = []
    total_juegos = len(dict_dim["game_id"])
    for i in range(total_juegos):
        gid = dict_dim["game_id"][i]
        rdate = dict_dim["release_date"][i]
        if not rdate:
            continue
        try:
            d = date.fromisoformat(str(rdate))
        except (ValueError, TypeError):
            continue

        if not (fecha_inicio <= d <= fecha_corte):
            continue

        ym = f"{d.year:04d}-{d.month:02d}"
        engine = str(dict_dim["engine"][i] or "unknown").strip().lower()
        is_indie = bool(dict_dim["is_indie"][i])
        fact = fact_por_id.get(gid, {
            "price_usd": 0.0,
            "is_free": False,
            "total_reviews": 0,
            "est_net_revenue_usd": 0.0,
        })

        juegos_filtrados.append({
            "game_id": gid,
            "year_month": ym,
            "engine": engine,
            "is_indie": is_indie,
            "price_usd": fact["price_usd"],
            "is_free": fact["is_free"],
            "total_reviews": fact["total_reviews"],
            "est_net_revenue_usd": fact["est_net_revenue_usd"],
            "generos": generos_por_id.get(gid, ["Sin Genero"]),
        })

    #1. tabla gold_engine_adoption_monthly
    agrup_motor: dict[tuple[str, bool, str], list[dict[str, Any]]] = defaultdict(list)
    totales_segmento_mes: dict[tuple[str, bool], int] = defaultdict(int)

    for j in juegos_filtrados:
        clave_motor = (j["year_month"], j["is_indie"], j["engine"])
        agrup_motor[clave_motor].append(j)
        totales_segmento_mes[(j["year_month"], j["is_indie"])] += 1

    filas_motor = []
    for (ym, is_indie, engine), grupo in sorted(agrup_motor.items()):
        total_segmento = totales_segmento_mes[(ym, is_indie)]
        conteo = len(grupo)
        share_pct = round((conteo / total_segmento) * 100.0, 2) if total_segmento > 0 else 0.0
        reviews = [float(x["total_reviews"]) for x in grupo]
        revenues = [float(x["est_net_revenue_usd"]) for x in grupo]

        filas_motor.append({
            "year_month": ym,
            "is_indie": is_indie,
            "engine": engine,
            "releases_count": conteo,
            "monthly_share_pct": share_pct,
            "median_reviews": _mediana(reviews),
            "total_net_revenue_usd": round(sum(revenues), 2),
            "pipeline_version": version,
        })

    #2. tabla gold_pricing_by_genre
    agrup_precio: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for j in juegos_filtrados:
        for gen in j["generos"]:
            agrup_precio[(gen, j["is_indie"])].append(j)

    filas_precio = []
    for (gen, is_indie), grupo in sorted(agrup_precio.items()):
        conteo_total = len(grupo)
        gratuitos = [x for x in grupo if x["is_free"] or x["price_usd"] == 0.0]
        pagos = [x["price_usd"] for x in grupo if not x["is_free"] and x["price_usd"] > 0.0]
        tasa_gratis = round(len(gratuitos) / conteo_total, 4) if conteo_total > 0 else 0.0
        p25, p50, p75 = _calcular_percentiles(pagos)
        revs_net = [float(x["est_net_revenue_usd"]) for x in grupo]

        filas_precio.append({
            "genre": gen,
            "is_indie": is_indie,
            "games_count": conteo_total,
            "free_games_rate": tasa_gratis,
            "price_p25_usd": p25,
            "price_median_usd": p50,
            "price_p75_usd": p75,
            "median_net_revenue_usd": _mediana(revs_net),
            "pipeline_version": version,
        })

    #3. tabla gold_market_saturation_monthly
    agrup_sat: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    totales_indie_mes: dict[str, int] = defaultdict(int)
    totales_reviews_mes: dict[str, int] = defaultdict(int)

    for j in juegos_filtrados:
        if not j["is_indie"]:
            continue
        ym = j["year_month"]
        for gen in j["generos"]:
            agrup_sat[(ym, gen)].append(j)
            totales_indie_mes[ym] += 1
            totales_reviews_mes[ym] += j["total_reviews"]

    filas_sat = []
    for (ym, gen), grupo in sorted(agrup_sat.items()):
        conteo_indie = len(grupo)
        reviews_capturadas = sum(x["total_reviews"] for x in grupo)
        mediana_rev = _mediana([float(x["total_reviews"]) for x in grupo])

        tot_indie_mes = totales_indie_mes[ym]
        tot_rev_mes = totales_reviews_mes[ym]

        oferta_rel = (conteo_indie / tot_indie_mes) if tot_indie_mes > 0 else 1.0
        demanda_rel = (reviews_capturadas / tot_rev_mes) if tot_rev_mes > 0 else 1.0
        sat_index = round(oferta_rel / demanda_rel, 4) if demanda_rel > 0 else 1.0

        filas_sat.append({
            "year_month": ym,
            "genre": gen,
            "indie_releases_count": conteo_indie,
            "total_reviews_captured": reviews_capturadas,
            "median_reviews_per_release": mediana_rev,
            "saturation_index": sat_index,
            "pipeline_version": version,
        })

    return {
        "gold_engine_adoption_monthly": pa.Table.from_pylist(filas_motor, schema=ESQUEMA_GOLD_ENGINE_MONTHLY),
        "gold_pricing_by_genre": pa.Table.from_pylist(filas_precio, schema=ESQUEMA_GOLD_PRICING_GENRE),
        "gold_market_saturation_monthly": pa.Table.from_pylist(filas_sat, schema=ESQUEMA_GOLD_SATURATION_MONTHLY),
    }


def persistir_tablas_oro_agregadas_parquet(
    tablas_agregadas: dict[str, pa.Table],
    ruta_oro: Optional[Path] = None,
) -> dict[str, Path]:
    """Guardar las tablas agregadas en parquet de forma atomica en data/oro/mart/."""
    base = Path(ruta_oro) if ruta_oro is not None else RUTA_DATA_DEFAULT / "oro" / "mart"
    base.mkdir(parents=True, exist_ok=True)

    destinos = {}
    temporales = []
    try:
        for nombre, tabla in tablas_agregadas.items():
            destino = base / f"{nombre}.parquet"
            temporal = base / f"{nombre}.tmp"
            pq.write_table(tabla, temporal, compression="snappy")
            temporales.append((temporal, destino))
            destinos[nombre] = destino

        for temporal, destino in temporales:
            os.replace(temporal, destino)
    except Exception:
        for temporal, _ in temporales:
            if temporal.exists():
                temporal.unlink()
        raise

    return destinos


def persistir_tablas_oro_agregadas_sqlite(
    tablas_agregadas: dict[str, pa.Table],
    ruta_db: Path,
) -> None:
    """Registrar las tablas agregadas en la base de datos sqlite del data mart."""
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta_db)
    try:
        cur = con.cursor()
        for nombre, tabla in tablas_agregadas.items():
            filas = tabla.to_pylist()
            if not filas:
                continue

            columnas = list(filas[0].keys())
            cols_def = ", ".join(f'"{c}" TEXT' for c in columnas)
            cur.execute(f'DROP TABLE IF EXISTS "{nombre}";')
            cur.execute(f'CREATE TABLE "{nombre}" ({cols_def});')

            placeholders = ", ".join("?" for _ in columnas)
            valores = [tuple(f[c] for c in columnas) for f in filas]
            cur.executemany(f'INSERT INTO "{nombre}" VALUES ({placeholders});', valores)

        con.commit()
    finally:
        con.close()


def ejecutar_transformacion_oro_agregados(
    ruta_oro: Optional[Path] = None,
    fecha_inicio: date = date(2024, 1, 1),
    fecha_corte: Optional[date] = None,
    ruta_db: Optional[Path] = None,
    version_pipeline: Optional[str] = None,
    validar_contratos: bool = True,
    umbral_sigma: float = 3.0,
    hitos_verificados: Optional[set[str]] = None,
    bloquear_solo_caidas: bool = True,
) -> dict[str, Any]:
    """Cargar star schema de oro, construir tablas agregadas, validar contratos y persistir."""
    base_oro = Path(ruta_oro) if ruta_oro is not None else RUTA_DATA_DEFAULT / "oro" / "mart"
    db_path = Path(ruta_db) if ruta_db is not None else RUTA_DATA_DEFAULT / "oro" / "indie_census_mart.db"
    corte = fecha_corte if fecha_corte is not None else date(2026, 10, 1)

    tablas_estrella = {
        "dim_game": pq.read_table(base_oro / "dim_game.parquet"),
        "dim_date": pq.read_table(base_oro / "dim_date.parquet"),
        "dim_genre_bridge": pq.read_table(base_oro / "dim_genre_bridge.parquet"),
        "fact_game_performance": pq.read_table(base_oro / "fact_game_performance.parquet"),
    }

    tablas_agregadas = construir_tablas_oro_agregadas(
        tablas_estrella=tablas_estrella,
        fecha_inicio=fecha_inicio,
        fecha_corte=corte,
        version_pipeline=version_pipeline,
    )

    if validar_contratos:
        engine_monthly = tablas_agregadas["gold_engine_adoption_monthly"]
        mes_ini_str = f"{fecha_inicio.year:04d}-{fecha_inicio.month:02d}"
        mes_corte_str = f"{corte.year:04d}-{corte.month:02d}"
        validar_continuidad_temporal_oro(engine_monthly, mes_inicio=mes_ini_str, mes_corte=mes_corte_str)
        validar_rango_historico_3sigma(
            engine_monthly,
            ventana_meses=12,
            umbral_sigma=umbral_sigma,
            hitos_verificados=hitos_verificados,
            bloquear_solo_caidas=bloquear_solo_caidas,
        )

    rutas_parquet = persistir_tablas_oro_agregadas_parquet(tablas_agregadas, ruta_oro=base_oro)
    persistir_tablas_oro_agregadas_sqlite(tablas_agregadas, ruta_db=db_path)

    return {
        "tablas_agregadas": list(tablas_agregadas.keys()),
        "rutas_parquet": {k: str(v) for k, v in rutas_parquet.items()},
        "ruta_db": str(db_path),
        "filas_engine_monthly": tablas_agregadas["gold_engine_adoption_monthly"].num_rows,
        "filas_pricing_genre": tablas_agregadas["gold_pricing_by_genre"].num_rows,
        "filas_saturation_monthly": tablas_agregadas["gold_market_saturation_monthly"].num_rows,
    }
