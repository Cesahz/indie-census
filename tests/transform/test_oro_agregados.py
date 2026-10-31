#suite de pruebas para la construccion de tablas analiticas agregadas en capa oro
from datetime import date
from pathlib import Path
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq

from src.transform.oro import (
    ESQUEMA_DIM_DATE,
    ESQUEMA_DIM_GAME_ORO,
    ESQUEMA_DIM_GENRE_BRIDGE,
    ESQUEMA_FACT_GAME_PERFORMANCE,
)
from src.transform.oro_agregados import (
    ESQUEMA_GOLD_ENGINE_MONTHLY,
    ESQUEMA_GOLD_PRICING_GENRE,
    ESQUEMA_GOLD_SATURATION_MONTHLY,
    construir_tablas_oro_agregadas,
    persistir_tablas_oro_agregadas_parquet,
    persistir_tablas_oro_agregadas_sqlite,
)


def _crear_star_schema_sintetico() -> dict[str, pa.Table]:
    """Construir en memoria un star schema representativo para pruebas analiticas hermeticas."""
    juegos = [
        #game_id, title, release_date, engine, is_indie, is_free, price_usd, reviews, revenue, genre
        (1, "Game Godot Indie Paid", "2024-02-15", "godot", True, False, 10.0, 100, 580.0, "Action"),
        (2, "Game Godot Indie Free", "2024-02-20", "godot", True, True, 0.0, 50, 0.0, "Action"),
        (3, "Game Unity Indie Paid", "2024-02-25", "unity", True, False, 20.0, 200, 2320.0, "Action"),
        (4, "Game Unreal Corp Paid", "2024-02-28", "unreal", False, False, 60.0, 500, 17400.0, "Action"),
        (5, "Game Godot RPG Paid", "2024-03-10", "godot", True, False, 15.0, 80, 696.0, "RPG"),
        (6, "Game Unity RPG Paid", "2024-03-15", "unity", True, False, 25.0, 120, 1740.0, "RPG"),
    ]

    filas_dim_game = []
    filas_bridge = []
    filas_fact = []
    fechas_unicas = set()

    for gid, title, rdate, engine, is_indie, is_free, price, revs, rev_net, genre in juegos:
        filas_dim_game.append({
            "game_id": gid,
            "title": title,
            "release_date": rdate,
            "group": "general",
            "engine": engine,
            "engine_evidence_level": 1,
            "indie_score": 0.85 if is_indie else 0.20,
            "is_indie": is_indie,
            "ai_disclosure_level": "unknown",
            "primary_developer": "Dev",
            "primary_publisher": "Pub",
            "is_free": is_free,
        })
        filas_bridge.append({"game_id": gid, "genre": genre})
        date_key = int(rdate.replace("-", ""))
        fechas_unicas.add(rdate)
        filas_fact.append({
            "game_id": gid,
            "release_date_key": date_key,
            "price_usd": price,
            "is_free": is_free,
            "total_positive": int(revs * 0.8),
            "total_negative": int(revs * 0.2),
            "total_reviews": revs,
            "approval_rate": 0.8,
            "est_copies_min": revs * 20,
            "est_copies_mid": revs * 30,
            "est_copies_max": revs * 45,
            "est_gross_revenue_usd": price * revs * 30,
            "est_net_revenue_usd": rev_net,
            "language_count": 1,
        })

    filas_date = []
    for f in sorted(fechas_unicas):
        d = date.fromisoformat(f)
        filas_date.append({
            "date_key": int(f.replace("-", "")),
            "full_date": f,
            "year": d.year,
            "quarter": (d.month - 1) // 3 + 1,
            "month": d.month,
            "month_name": "Month",
            "day": d.day,
            "day_of_week": "Day",
            "is_weekend": False,
        })

    return {
        "dim_game": pa.Table.from_pylist(filas_dim_game, schema=ESQUEMA_DIM_GAME_ORO),
        "dim_date": pa.Table.from_pylist(filas_date, schema=ESQUEMA_DIM_DATE),
        "dim_genre_bridge": pa.Table.from_pylist(filas_bridge, schema=ESQUEMA_DIM_GENRE_BRIDGE),
        "fact_game_performance": pa.Table.from_pylist(filas_fact, schema=ESQUEMA_FACT_GAME_PERFORMANCE),
    }


def test_construir_tablas_oro_agregadas_estructura_y_esquemas() -> None:
    """Verificar que la funcion genere las tres tablas maestras agregadas con esquemas conformes."""
    star = _crear_star_schema_sintetico()
    tablas = construir_tablas_oro_agregadas(
        tablas_estrella=star,
        fecha_inicio=date(2024, 1, 1),
        fecha_corte=date(2024, 12, 31),
        version_pipeline="0.4.0",
    )

    assert set(tablas.keys()) == {
        "gold_engine_adoption_monthly",
        "gold_pricing_by_genre",
        "gold_market_saturation_monthly",
    }
    assert tablas["gold_engine_adoption_monthly"].schema.equals(ESQUEMA_GOLD_ENGINE_MONTHLY)
    assert tablas["gold_pricing_by_genre"].schema.equals(ESQUEMA_GOLD_PRICING_GENRE)
    assert tablas["gold_market_saturation_monthly"].schema.equals(ESQUEMA_GOLD_SATURATION_MONTHLY)


def test_agregacion_motores_suma_100_share() -> None:
    """Verificar que monthly_share_pct sume 100% por segmento y mes."""
    star = _crear_star_schema_sintetico()
    tablas = construir_tablas_oro_agregadas(
        tablas_estrella=star,
        fecha_inicio=date(2024, 1, 1),
        fecha_corte=date(2024, 12, 31),
    )
    engine_table = tablas["gold_engine_adoption_monthly"]
    filas = engine_table.to_pylist()

    #en 2024-02 hay 3 indies: 2 godot (66.67%) y 1 unity (33.33%)
    indies_feb = [f for f in filas if f["year_month"] == "2024-02" and f["is_indie"] is True]
    assert len(indies_feb) == 2
    total_share = sum(f["monthly_share_pct"] for f in indies_feb)
    assert round(total_share, 1) == 100.0


def test_estadisticos_precios_con_gratuitos() -> None:
    """Verificar que los percentiles de precio se calculen sobre juegos de pago y se compute free_games_rate."""
    star = _crear_star_schema_sintetico()
    tablas = construir_tablas_oro_agregadas(
        tablas_estrella=star,
        fecha_inicio=date(2024, 1, 1),
        fecha_corte=date(2024, 12, 31),
    )
    pricing_table = tablas["gold_pricing_by_genre"]
    filas = pricing_table.to_pylist()

    #en genero Action e indie: hay 3 juegos (2 de pago: 10 y 20 USD, y 1 gratis)
    action_indie = next(f for f in filas if f["genre"] == "Action" and f["is_indie"] is True)
    assert action_indie["games_count"] == 3
    assert round(action_indie["free_games_rate"], 2) == 0.33
    #mediana de 10 y 20 USD es 15.0 USD
    assert action_indie["price_median_usd"] == 15.0


def test_determinismo_con_reloj_inyectado() -> None:
    """Verificar que dos ejecuciones con la misma fecha_corte produzcan tablas Arrow bit-identicas."""
    star = _crear_star_schema_sintetico()
    t1 = construir_tablas_oro_agregadas(star, fecha_corte=date(2024, 3, 31))
    t2 = construir_tablas_oro_agregadas(star, fecha_corte=date(2024, 3, 31))

    for k in t1:
        assert t1[k].equals(t2[k])


def test_indice_saturacion_relativa() -> None:
    """Verificar calculo del indice de saturacion en gold_market_saturation_monthly."""
    star = _crear_star_schema_sintetico()
    tablas = construir_tablas_oro_agregadas(star, fecha_corte=date(2024, 3, 31))
    sat_table = tablas["gold_market_saturation_monthly"]
    filas = sat_table.to_pylist()

    #en 2024-02 hay 3 indies en Action con 100, 50, 200 reviews (total 350 reviews)
    action_feb = next(f for f in filas if f["year_month"] == "2024-02" and f["genre"] == "Action")
    assert action_feb["indie_releases_count"] == 3
    assert action_feb["total_reviews_captured"] == 350
    assert action_feb["saturation_index"] > 0.0


def test_persistir_tablas_oro_agregadas_parquet_y_sqlite(tmp_path: Path) -> None:
    """Verificar persistencia atomica en Parquet y en Data Mart SQLite."""
    star = _crear_star_schema_sintetico()
    tablas = construir_tablas_oro_agregadas(star, fecha_corte=date(2024, 3, 31))

    dir_parquet = tmp_path / "mart_agregado"
    rutas = persistir_tablas_oro_agregadas_parquet(tablas, ruta_oro=dir_parquet)
    assert len(rutas) == 3
    for nom, ruta in rutas.items():
        assert ruta.exists()
        leida = pq.read_table(ruta)
        assert leida.equals(tablas[nom])

    ruta_db = tmp_path / "indie_census_mart.db"
    persistir_tablas_oro_agregadas_sqlite(tablas, ruta_db=ruta_db)
    assert ruta_db.exists()

    con = sqlite3.connect(ruta_db)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    nombres_tablas = {r[0] for r in cur.fetchall()}
    con.close()
    assert "gold_engine_adoption_monthly" in nombres_tablas
    assert "gold_pricing_by_genre" in nombres_tablas
    assert "gold_market_saturation_monthly" in nombres_tablas
