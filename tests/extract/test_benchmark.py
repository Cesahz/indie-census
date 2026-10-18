#suite de pruebas para telemetria de benchmarks y graceful shutdown (criterio f3-06)
#garantias: esquema estricto, calculo de ratios, captura de senales e integridad transaccional
import json
from pathlib import Path
from unittest.mock import MagicMock

from src.extract.benchmark import ColectorTelemetria, detectar_entorno_nodo
from src.extract.client import SteamAppNotFoundError, SteamClient
from src.extract.pipeline import ejecutar_ingesta_masiva


def _crear_payload_appdetails(appid: int) -> dict:
    return {
        str(appid): {
            "success": True,
            "data": {
                "steam_appid": appid,
                "name": f"Juego {appid}",
                "is_free": False,
                "release_date": {"date": "Jan 1, 2025"},
            },
        }
    }


def _crear_payload_reviews(appid: int) -> dict:
    return {
        "success": 1,
        "query_summary": {"total_reviews": 10},
    }


def test_colector_telemetria_esquema_y_metricas(tmp_path: Path) -> None:
    #colector debe calcular duraciones, throughput, ratios y volcar json determinista
    fecha = "2026-10-18"
    ruta_bronce = tmp_path / "bronce" / "steam" / fecha
    ruta_bronce.mkdir(parents=True, exist_ok=True)
    #crear archivo simulado de payload
    archivo_dummy = ruta_bronce / "test.json"
    archivo_dummy.write_text("{\"steam\": true}", encoding="utf-8")

    colector = ColectorTelemetria(
        worker_id=0,
        total_workers=2,
        node_environment="PC Local (Fibra Residencial)",
        total_assigned_appids=100,
        ruta_bronce=ruta_bronce,
        fecha=fecha,
    )

    #simular eventos
    colector.registrar_exito(appid=1)
    colector.registrar_exito(appid=2)
    colector.registrar_no_disponible(appid=3)
    colector.registrar_429()
    colector.registrar_reintento()

    reporte = colector.finalizar(exit_reason="completed")

    assert reporte["worker_id"] == 0
    assert reporte["total_workers"] == 2
    assert reporte["node_environment"] == "PC Local (Fibra Residencial)"
    assert "start_time_utc" in reporte
    assert "end_time_utc" in reporte
    assert reporte["total_assigned_appids"] == 100
    assert reporte["processed_appids"] == 3
    assert reporte["successful_fetches"] == 2
    assert reporte["unavailable_or_dlc"] == 1
    assert reporte["rate_limit_hits_429"] == 1
    assert reporte["network_retry_count"] == 1
    assert reporte["exit_reason"] == "completed"
    assert reporte["total_payload_bytes_uncompressed"] > 0
    assert isinstance(reporte["throughput_apps_per_minute"], float)
    assert isinstance(reporte["compression_ratio"], float)

    #verificar persistencia en disco
    ruta_benchmark = ruta_bronce / "benchmarks" / "benchmark_worker_0.json"
    assert ruta_benchmark.is_file()
    guardado = json.loads(ruta_benchmark.read_text(encoding="utf-8"))
    assert guardado["exit_reason"] == "completed"


def test_detectar_entorno_nodo() -> None:
    #debe identificar entorno por defecto como pc local si no esta en colab
    entorno = detectar_entorno_nodo()
    assert isinstance(entorno, str)
    assert len(entorno) > 0


def test_steam_client_contadores_telemetria() -> None:
    #cliente debe exponer contadores de 429, reintentos y solicitudes
    mock_session = MagicMock()
    #primera llamada 429, segunda 200
    resp_429 = MagicMock(status_code=429, headers={})
    resp_200 = MagicMock(status_code=200)
    resp_200.json.return_value = {"2400010": {"success": True, "data": {}}}

    mock_session.get.side_effect = [resp_429, resp_200]

    cliente = SteamClient(
        session=mock_session,
        sleep_fn=lambda _: None,
        max_retries=2,
    )

    datos = cliente.get_app_details(2400010)
    assert "2400010" in datos
    assert cliente.rate_limit_hits_429 == 1
    assert cliente.network_retry_count == 1
    assert cliente.total_requests == 2


def test_ejecutar_ingesta_masiva_genera_benchmark(tmp_path: Path) -> None:
    #ejecutar ingesta masiva debe generar benchmark_worker_X.json con exit_reason completed
    appids = [3001, 3002]
    mock_client = MagicMock(spec=SteamClient)
    mock_client.get_app_details.side_effect = lambda aid: _crear_payload_appdetails(aid)
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"
    mock_client.rate_limit_hits_429 = 0
    mock_client.network_retry_count = 0
    mock_client.total_requests = 4

    fecha = "2026-10-18"
    resultado = ejecutar_ingesta_masiva(
        appids=appids,
        client=mock_client,
        fecha=fecha,
        ruta_base=tmp_path,
        worker_id=0,
        total_workers=2,
        mostrar_progreso=False,
    )

    assert resultado["procesados_exito"] == 2
    ruta_bm = tmp_path / "bronce" / "steam" / fecha / "benchmarks" / "benchmark_worker_0.json"
    assert ruta_bm.is_file()
    datos_bm = json.loads(ruta_bm.read_text(encoding="utf-8"))
    assert datos_bm["exit_reason"] == "completed"
    assert datos_bm["successful_fetches"] == 2
    assert datos_bm["processed_appids"] == 2


def test_ejecutar_ingesta_masiva_unavailable_or_dlc(tmp_path: Path) -> None:
    #cuando un appid arroja SteamAppNotFoundError debe registrarse como unavailable_or_dlc
    appids = [4001]
    mock_client = MagicMock(spec=SteamClient)
    mock_client.get_app_details.side_effect = SteamAppNotFoundError("Appid 4001 not found")
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"
    mock_client.rate_limit_hits_429 = 0
    mock_client.network_retry_count = 0
    mock_client.total_requests = 1

    fecha = "2026-10-18"
    resultado = ejecutar_ingesta_masiva(
        appids=appids,
        client=mock_client,
        fecha=fecha,
        ruta_base=tmp_path,
        worker_id=1,
        total_workers=2,
        mostrar_progreso=False,
    )

    assert resultado["procesados_exito"] == 0
    assert resultado["unavailable_or_dlc"] == 1
    ruta_bm = tmp_path / "bronce" / "steam" / fecha / "benchmarks" / "benchmark_worker_1.json"
    assert ruta_bm.is_file()
    datos_bm = json.loads(ruta_bm.read_text(encoding="utf-8"))
    assert datos_bm["unavailable_or_dlc"] == 1
    assert datos_bm["successful_fetches"] == 0


def test_ejecutar_ingesta_masiva_graceful_shutdown_keyboard_interrupt(tmp_path: Path) -> None:
    #captura de KeyboardInterrupt debe guardar checkpoint, tar si aplica y volcar benchmark sigint_interrupted
    appids = [5001, 5002, 5003]
    mock_client = MagicMock(spec=SteamClient)
    #el primer juego tiene exito, el segundo interrumpe con KeyboardInterrupt
    def side_effect_details(aid: int) -> dict:
        if aid == 5002:
            raise KeyboardInterrupt("Interrupcion manual")
        return _crear_payload_appdetails(aid)

    mock_client.get_app_details.side_effect = side_effect_details
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"
    mock_client.rate_limit_hits_429 = 0
    mock_client.network_retry_count = 0
    mock_client.total_requests = 3

    fecha = "2026-10-18"
    sync_dir = tmp_path / "sync_drive"

    resultado = ejecutar_ingesta_masiva(
        appids=appids,
        client=mock_client,
        fecha=fecha,
        ruta_base=tmp_path,
        worker_id=0,
        total_workers=2,
        sync_tar_dir=sync_dir,
        mostrar_progreso=False,
    )

    assert resultado["exit_reason"] == "sigint_interrupted"
    assert resultado["procesados_exito"] == 1

    #verificar persistencia de tar en sync_dir
    tar_final = sync_dir / "bronce_worker_0.tar.gz"
    assert tar_final.is_file()

    #verificar persistencia de benchmark con sigint_interrupted
    ruta_bm = tmp_path / "bronce" / "steam" / fecha / "benchmarks" / "benchmark_worker_0.json"
    assert ruta_bm.is_file()
    datos_bm = json.loads(ruta_bm.read_text(encoding="utf-8"))
    assert datos_bm["exit_reason"] == "sigint_interrupted"
    assert datos_bm["successful_fetches"] == 1
    assert datos_bm["total_tar_bytes_compressed"] > 0
