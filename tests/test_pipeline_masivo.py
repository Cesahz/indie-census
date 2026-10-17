#suite de pruebas para orquestacion masiva de pipeline y soporte cli (criterio f3-04)
#garantias: hermeticidad total, soporte modo masivo sin manifiesto, generacion de capas oro
import json
from pathlib import Path
from unittest.mock import MagicMock
#pyrefly: ignore [missing-import]
import pyarrow.parquet as pq

from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce
from src.extract.client import SteamClient
from src.pipeline import _construir_parser, ejecutar_pipeline
from src.transform.plata import construir_tablas_plata


def _crear_payload_appdetails(appid: int, nombre: str, price_cents: int = 1499) -> dict:
    return {
        str(appid): {
            "success": True,
            "data": {
                "steam_appid": appid,
                "name": nombre,
                "is_free": False,
                "release_date": {"date": "May 10, 2024"},
                "price_overview": {"initial": price_cents, "currency": "USD"},
                "genres": [{"id": "1", "description": "Action"}],
                "supported_languages": "English, Spanish",
                "developers": ["Estudio Indie"],
                "publishers": ["Publisher Indie"],
                "categories": [{"id": 2, "description": "Single-player"}],
                "short_description": "A game made in Godot Engine with great mechanics.",
            },
        }
    }


def _crear_payload_reviews(appid: int) -> dict:
    return {
        "success": 1,
        "query_summary": {
            "num_reviews": 50,
            "review_score": 8,
            "total_positive": 45,
            "total_negative": 5,
            "total_reviews": 50,
        },
    }


def test_cli_parser_argumentos_masivo() -> None:
    #el parser cli debe aceptar --modo masivo, --descubrir y --max-juegos
    parser = _construir_parser()
    args = parser.parse_args(["--modo", "masivo", "--descubrir", "--max-juegos", "500", "--generar-oro"])

    assert args.modo == "masivo"
    assert args.descubrir is True
    assert args.max_juegos == 500
    assert args.generar_oro is True


def test_construir_tablas_plata_modo_masivo(tmp_path: Path) -> None:
    #en modo masivo, se procesan los appids en bronce sin requerir muestra_control.yaml
    appids = [701, 702]
    fecha = "2026-10-17"

    for appid in appids:
        env_det = crear_envoltorio_bronce(
            fuente="steam.appdetails",
            url_solicitada=f"http://test/{appid}",
            parametros={},
            estado_http=200,
            payload=_crear_payload_appdetails(appid, f"Indie {appid}"),
        )
        guardar_en_bronce("appdetails", fecha, appid, env_det, ruta_base=tmp_path)

        env_rev = crear_envoltorio_bronce(
            fuente="steam.appreviews_resumen",
            url_solicitada=f"http://test/rev/{appid}",
            parametros={},
            estado_http=200,
            payload=_crear_payload_reviews(appid),
        )
        guardar_en_bronce("appreviews_resumen", fecha, appid, env_rev, ruta_base=tmp_path)

    dim_game, resumen = construir_tablas_plata(
        ruta_base=tmp_path,
        fecha=fecha,
        modo="masivo",
    )

    assert dim_game.num_rows == 2
    assert resumen.num_rows == 2

    d_dict = dim_game.to_pydict()
    assert d_dict["game_id"] == [701, 702]
    #grupo por defecto en modo masivo es general
    assert d_dict["group"] == ["general", "general"]
    assert d_dict["engine"] == ["godot", "godot"]
    assert d_dict["is_indie"] == [True, True]


def test_ejecutar_pipeline_modo_masivo_con_descubrimiento_e2e(tmp_path: Path) -> None:
    #flujo e2e masivo: descubrimiento -> ingesta bronce -> plata -> oro analitico
    apps_catalogo = [
        {"appid": 801, "name": "Juego 801", "last_modified": 1700000000},
        {"appid": 802, "name": "Juego 802", "last_modified": 1700000001},
    ]

    mock_client = MagicMock(spec=SteamClient)
    mock_client.iterar_catalogo_completo.return_value = iter(apps_catalogo)
    mock_client.get_app_details.side_effect = lambda aid: _crear_payload_appdetails(aid, f"Juego {aid}")
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"

    resultado = ejecutar_pipeline(
        ruta_base=tmp_path,
        client=mock_client,
        fecha="2026-10-17",
        modo="masivo",
        descubrir=True,
        max_juegos=2,
        generar_oro=True,
    )

    assert resultado["estado"] == "ok"
    assert resultado["extraccion"]["procesados_exito"] == 2

    #verificar persistencia en capa plata
    archivo_dim = tmp_path / "plata" / "steam" / "dim_game.parquet"
    assert archivo_dim.is_file()
    t_dim = pq.read_table(archivo_dim)
    assert t_dim.num_rows == 2

    #verificar persistencia en capa oro
    archivo_fact = tmp_path / "oro" / "mart" / "fact_game_performance.parquet"
    assert archivo_fact.is_file()
    t_fact = pq.read_table(archivo_fact)
    assert t_fact.num_rows == 2
    f_dict = t_fact.to_pydict()
    assert "est_net_revenue_usd" in f_dict

    #verificar base sqlite
    archivo_db = tmp_path / "oro" / "indie_census_mart.db"
    assert archivo_db.is_file()
