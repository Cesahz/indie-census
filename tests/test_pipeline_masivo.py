#suite de pruebas para orquestacion masiva de pipeline y soporte cli (criterio f3-04)
#garantias: hermeticidad total, soporte modo masivo sin manifiesto, generacion de capas oro
from pathlib import Path
from unittest.mock import MagicMock
#pyrefly: ignore [missing-import]
import pyarrow.parquet as pq

from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce
from src.extract.client import SteamClient
from src.pipeline import _construir_parser, ejecutar_pipeline, main
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
                "genres": [{"id": "1", "description": "Action"}, {"id": "23", "description": "Indie"}],
                "supported_languages": "English, Spanish",
                "developers": ["Estudio Indie"],
                "publishers": ["Estudio Indie"],
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


def test_construir_tablas_plata_modo_masivo_descarta_juegos_sin_fecha(tmp_path: Path) -> None:
    #en modo masivo se descartan productos sin fecha de lanzamiento valida en steam
    fecha = "2026-10-17"

    #701 con fecha valida
    env_701 = crear_envoltorio_bronce(
        fuente="steam.appdetails", url_solicitada="http://test/701", parametros={}, estado_http=200,
        payload=_crear_payload_appdetails(701, "Indie Con Fecha"),
    )
    guardar_en_bronce("appdetails", fecha, 701, env_701, ruta_base=tmp_path)
    guardar_en_bronce("appreviews_resumen", fecha, 701, crear_envoltorio_bronce(
        fuente="steam.appreviews_resumen", url_solicitada="http://test/rev/701", parametros={}, estado_http=200,
        payload=_crear_payload_reviews(701),
    ), ruta_base=tmp_path)

    #702 con fecha no parseable (coming soon)
    payload_sin_fecha = _crear_payload_appdetails(702, "Indie Sin Fecha")
    payload_sin_fecha["702"]["data"]["release_date"] = {"date": "Coming soon"}
    env_702 = crear_envoltorio_bronce(
        fuente="steam.appdetails", url_solicitada="http://test/702", parametros={}, estado_http=200,
        payload=payload_sin_fecha,
    )
    guardar_en_bronce("appdetails", fecha, 702, env_702, ruta_base=tmp_path)
    guardar_en_bronce("appreviews_resumen", fecha, 702, crear_envoltorio_bronce(
        fuente="steam.appreviews_resumen", url_solicitada="http://test/rev/702", parametros={}, estado_http=200,
        payload=_crear_payload_reviews(702),
    ), ruta_base=tmp_path)

    dim_game, resumen = construir_tablas_plata(
        ruta_base=tmp_path,
        fecha=fecha,
        modo="masivo",
    )

    assert dim_game.num_rows == 1
    assert resumen.num_rows == 1
    assert dim_game.to_pydict()["game_id"] == [701]
    assert resumen.to_pydict()["game_id"] == [701]


def test_construir_tablas_plata_modo_masivo_descarta_juegos_de_pago_sin_precio(tmp_path: Path) -> None:
    #en modo masivo se descartan productos de pago que no tienen precio disponible (deslistados/bundle-only)
    fecha = "2026-10-17"

    #701 con precio valido
    env_701 = crear_envoltorio_bronce(
        fuente="steam.appdetails", url_solicitada="http://test/701", parametros={}, estado_http=200,
        payload=_crear_payload_appdetails(701, "Indie Con Precio", price_cents=1999),
    )
    guardar_en_bronce("appdetails", fecha, 701, env_701, ruta_base=tmp_path)
    guardar_en_bronce("appreviews_resumen", fecha, 701, crear_envoltorio_bronce(
        fuente="steam.appreviews_resumen", url_solicitada="http://test/rev/701", parametros={}, estado_http=200,
        payload=_crear_payload_reviews(701),
    ), ruta_base=tmp_path)

    #702 de pago pero deslistado / sin precio
    payload_sin_precio = _crear_payload_appdetails(702, "Indie Sin Precio")
    payload_sin_precio["702"]["data"]["price_overview"] = None
    env_702 = crear_envoltorio_bronce(
        fuente="steam.appdetails", url_solicitada="http://test/702", parametros={}, estado_http=200,
        payload=payload_sin_precio,
    )
    guardar_en_bronce("appdetails", fecha, 702, env_702, ruta_base=tmp_path)
    guardar_en_bronce("appreviews_resumen", fecha, 702, crear_envoltorio_bronce(
        fuente="steam.appreviews_resumen", url_solicitada="http://test/rev/702", parametros={}, estado_http=200,
        payload=_crear_payload_reviews(702),
    ), ruta_base=tmp_path)

    dim_game, resumen = construir_tablas_plata(
        ruta_base=tmp_path,
        fecha=fecha,
        modo="masivo",
    )

    assert dim_game.num_rows == 1
    assert resumen.num_rows == 1
    assert dim_game.to_pydict()["game_id"] == [701]
    assert resumen.to_pydict()["game_id"] == [701]


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


def test_cli_main_modo_masivo_exitoso(tmp_path: Path) -> None:
    #main() en modo masivo debe imprimir reporte y retornar 0
    apps_catalogo = [{"appid": 901, "name": "Juego 901"}]
    mock_client = MagicMock(spec=SteamClient)
    mock_client.iterar_catalogo_completo.return_value = iter(apps_catalogo)
    mock_client.get_app_details.side_effect = lambda aid: _crear_payload_appdetails(aid, f"Juego {aid}")
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"

    codigo = main(
        [
            "--ruta-base", str(tmp_path),
            "--modo", "masivo",
            "--descubrir",
            "--max-juegos", "1",
            "--generar-oro",
        ],
        client=mock_client,
    )
    assert codigo == 0


def test_cli_parser_argumentos_sharding() -> None:
    #el parser cli debe aceptar opciones de manifiesto maestro y particionamiento distribuido
    parser = _construir_parser()
    args = parser.parse_args([
        "--congelar-manifiesto",
        "--min-appid", "2500000",
        "--manifiesto-maestro", "ruta/manifest.json",
        "--worker-id", "1",
        "--total-workers", "2",
        "--sync-tar-dir", "drive/sync",
        "--sync-interval", "100",
    ])
    assert args.congelar_manifiesto is True
    assert args.min_appid == 2500000
    assert args.manifiesto_maestro == Path("ruta/manifest.json")
    assert args.worker_id == 1
    assert args.total_workers == 2
    assert args.sync_tar_dir == Path("drive/sync")
    assert args.sync_interval == 100


def test_ejecutar_pipeline_congelar_manifiesto(tmp_path: Path) -> None:
    #congelar manifiesto via pipeline debe generar manifest_master y retornar sin procesar plata
    apps = [
        {"appid": 2400010, "name": "Modern 1"},
        {"appid": 2400020, "name": "Modern 2"},
    ]
    mock_client = MagicMock(spec=SteamClient)
    mock_client.iterar_catalogo_completo.return_value = iter(apps)

    res = ejecutar_pipeline(
        ruta_base=tmp_path,
        client=mock_client,
        fecha="2026-10-18",
        congelar_manifiesto=True,
        min_appid=2400000,
    )

    assert res["estado"] == "ok"
    assert "manifest_master.json" in res["manifiesto_maestro"]
    assert res["extraccion"] is None
    assert Path(res["manifiesto_maestro"]).is_file()


def test_ejecutar_pipeline_manifiesto_maestro_sharding(tmp_path: Path) -> None:
    #ejecutar pipeline con manifiesto maestro asigna unicamente el shard modular al worker
    apps = [
        {"appid": 2400010, "name": "Modern 1"},
        {"appid": 2400020, "name": "Modern 2"},
        {"appid": 2400030, "name": "Modern 3"},
        {"appid": 2400040, "name": "Modern 4"},
    ]
    mock_client = MagicMock(spec=SteamClient)
    mock_client.iterar_catalogo_completo.return_value = iter(apps)
    mock_client.get_app_details.side_effect = lambda aid: _crear_payload_appdetails(aid, f"Modern {aid}")
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"

    res_man = ejecutar_pipeline(
        ruta_base=tmp_path,
        client=mock_client,
        fecha="2026-10-18",
        congelar_manifiesto=True,
        min_appid=2400000,
    )
    ruta_manifest = Path(res_man["manifiesto_maestro"])

    #worker 1 de 2: debe procesar indices impares [2400020, 2400040] (2 juegos)
    res_worker = ejecutar_pipeline(
        ruta_base=tmp_path,
        client=mock_client,
        fecha="2026-10-18",
        modo="masivo",
        manifiesto_maestro=ruta_manifest,
        worker_id=1,
        total_workers=2,
    )

    assert res_worker["estado"] == "ok"
    assert res_worker["extraccion"]["total_solicitados"] == 2
    assert res_worker["extraccion"]["procesados_exito"] == 2

