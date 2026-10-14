#suite de pruebas unitarias para el orquestador de extraccion de la muestra de control
#garantias: integracion de componentes, idempotencia, resiliencia ante errores, hermeticidad
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import yaml

from src.extract.checkpoint import GestorCheckpoint
from src.extract.client import SteamAppNotFoundError, SteamClient
from src.extract.pipeline import ejecutar_extraccion_muestra, extraer_juego

@pytest.fixture
def mock_steam_client() -> SteamClient:
    """Crear un cliente steam con session mockeada que retorna respuestas canonicas."""
    session = MagicMock()

    def mock_get(url: str, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        if "appdetails" in url:
            #extraer appid de url
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            appid = params.get("appids", ["0"])[0]

            if appid == "999999":
                mock_resp.json.return_value = {appid: {"success": False}}
            else:
                mock_resp.json.return_value = {
                    appid: {
                        "success": True,
                        "data": {
                            "name": f"Juego {appid}",
                            "steam_appid": int(appid),
                            "is_free": False,
                        },
                    }
                }
        elif "appreviews" in url:
            mock_resp.json.return_value = {
                "success": 1,
                "query_summary": {
                    "num_reviews": 100,
                    "review_score": 8,
                    "total_positive": 80,
                    "total_negative": 20,
                    "total_reviews": 100,
                },
            }
        else:
            mock_resp.status_code = 404
            mock_resp.json.return_value = {}

        return mock_resp

    session.get.side_effect = mock_get
    return SteamClient(session=session, sleep_fn=lambda _: None)

def test_extraer_juego_exitoso_guarda_bronce_y_marca_checkpoint(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar que un juego pendiente se extrae, se guarda en bronce y se marca en checkpoint."""
    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"
    checkpoint = GestorCheckpoint(ruta_archivo=ruta_checkpoint)

    resultado = extraer_juego(
        client=mock_steam_client,
        checkpoint=checkpoint,
        appid=1809540,
        fecha="2026-10-12",
        ruta_base=ruta_base,
    )

    #ambos recursos debieron ser procesados con exito
    assert resultado == {"appdetails": True, "appreviews_resumen": True}
    assert checkpoint.esta_completado("appdetails", 1809540)
    assert checkpoint.esta_completado("appreviews_resumen", 1809540)

    #verificar persistencia fisica en bronce
    archivo_details = (
        ruta_base / "bronce" / "steam" / "appdetails" / "fecha=2026-10-12" / "appid=1809540.json"
    )
    archivo_reviews = (
        ruta_base / "bronce" / "steam" / "appreviews_resumen" / "fecha=2026-10-12" / "appid=1809540.json"
    )

    assert archivo_details.exists()
    assert archivo_reviews.exists()

    #verificar estructura del envoltorio de bronce
    with open(archivo_details, "r", encoding="utf-8") as f:
        datos = json.load(f)
    assert datos["meta"]["fuente"] == "steam.appdetails"
    assert datos["payload"]["1809540"]["success"] is True

def test_extraer_juego_omite_llamadas_si_ya_esta_en_checkpoint(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar que no se llama a la api si el juego ya figura como completado."""
    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"
    checkpoint = GestorCheckpoint(ruta_archivo=ruta_checkpoint)

    #marcar como completado previamente
    checkpoint.marcar_completado("appdetails", 1809540)
    checkpoint.marcar_completado("appreviews_resumen", 1809540)

    resultado = extraer_juego(
        client=mock_steam_client,
        checkpoint=checkpoint,
        appid=1809540,
        fecha="2026-10-12",
        ruta_base=ruta_base,
    )

    #ningun recurso debio requerir extraccion
    assert resultado == {"appdetails": False, "appreviews_resumen": False}
    #verificar que la sesion no realizo ninguna llamada get
    mock_steam_client.session.get.assert_not_called()

def test_extraer_juego_maneja_error_sin_marcar_checkpoint(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar que si ocurre un error (appid no encontrado), no se marca el checkpoint."""
    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"
    checkpoint = GestorCheckpoint(ruta_archivo=ruta_checkpoint)

    with pytest.raises(SteamAppNotFoundError):
        extraer_juego(
            client=mock_steam_client,
            checkpoint=checkpoint,
            appid=999999,
            fecha="2026-10-12",
            ruta_base=ruta_base,
        )

    #no debe quedar registrado en checkpoint
    assert not checkpoint.esta_completado("appdetails", 999999)

def test_ejecutar_extraccion_muestra_completa(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar orquestacion completa sobre un archivo de manifiesto sintesis."""
    manifiesto_path = tmp_path / "manifiesto.yaml"
    manifiesto_data = {
        "juegos": [
            {"appid": 100, "grupo": "godot"},
            {"appid": 200, "grupo": "general"},
        ]
    }
    with open(manifiesto_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifiesto_data, f)

    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"

    resumen = ejecutar_extraccion_muestra(
        ruta_manifiesto=manifiesto_path,
        ruta_base=ruta_base,
        ruta_checkpoint=ruta_checkpoint,
        client=mock_steam_client,
        fecha="2026-10-12",
    )

    assert resumen["total_juegos"] == 2
    assert resumen["procesados_exito"] == 2
    assert resumen["fallidos"] == 0
    assert len(resumen["errores"]) == 0

def test_ejecutar_extraccion_muestra_idempotente_segunda_pasada(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar que ejecutar dos veces consecutivas la extraccion no repite llamadas."""
    manifiesto_path = tmp_path / "manifiesto.yaml"
    manifiesto_data = {
        "juegos": [
            {"appid": 100, "grupo": "godot"},
            {"appid": 200, "grupo": "general"},
        ]
    }
    with open(manifiesto_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifiesto_data, f)

    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"

    #primera pasada
    ejecutar_extraccion_muestra(
        ruta_manifiesto=manifiesto_path,
        ruta_base=ruta_base,
        ruta_checkpoint=ruta_checkpoint,
        client=mock_steam_client,
        fecha="2026-10-12",
    )

    llamadas_iniciales = mock_steam_client.session.get.call_count
    assert llamadas_iniciales == 4  #2 juegos x 2 recursos

    #segunda pasada sobre la misma configuracion
    resumen2 = ejecutar_extraccion_muestra(
        ruta_manifiesto=manifiesto_path,
        ruta_base=ruta_base,
        ruta_checkpoint=ruta_checkpoint,
        client=mock_steam_client,
        fecha="2026-10-12",
    )

    #no debieron realizarse llamadas adicionales
    assert mock_steam_client.session.get.call_count == llamadas_iniciales
    assert resumen2["total_juegos"] == 2
    assert resumen2["procesados_exito"] == 2

def test_ejecutar_extraccion_con_fallo_individual_continua_con_el_resto(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar que un fallo en un juego no detiene la ingesta del resto."""
    manifiesto_path = tmp_path / "manifiesto.yaml"
    manifiesto_data = {
        "juegos": [
            {"appid": 999999, "grupo": "godot"},  #falla simulada
            {"appid": 300, "grupo": "general"},
        ]
    }
    with open(manifiesto_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifiesto_data, f)

    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"

    resumen = ejecutar_extraccion_muestra(
        ruta_manifiesto=manifiesto_path,
        ruta_base=ruta_base,
        ruta_checkpoint=ruta_checkpoint,
        client=mock_steam_client,
        fecha="2026-10-12",
    )

    assert resumen["total_juegos"] == 2
    assert resumen["procesados_exito"] == 1
    assert resumen["fallidos"] == 1
    assert len(resumen["errores"]) == 1
    assert resumen["errores"][0]["appid"] == 999999

def test_ejecutar_extraccion_resuelve_defaults(
    tmp_path: Path, mock_steam_client: SteamClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verificar que la orquestacion resuelve parametros por defecto sin errores."""
    manifiesto_path = tmp_path / "manifiesto.yaml"
    manifiesto_data = {
        "juegos": [
            {"appid": 100, "grupo": "godot"},
        ]
    }
    with open(manifiesto_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifiesto_data, f)

    #mockear instanciacion por defecto de SteamClient para no tocar red
    monkeypatch.setattr("src.extract.pipeline.SteamClient", lambda: mock_steam_client)

    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"

    #no pasar fecha ni client ni checkpoint para ejercitar ramas por defecto
    resumen = ejecutar_extraccion_muestra(
        ruta_manifiesto=manifiesto_path,
        ruta_base=ruta_base,
        ruta_checkpoint=ruta_checkpoint,
    )

    assert resumen["total_juegos"] == 1
    assert resumen["procesados_exito"] == 1

def test_extraer_juego_fecha_por_defecto_resuelve_hoy(
    tmp_path: Path, mock_steam_client: SteamClient
) -> None:
    """Verificar que extraer_juego adopta la fecha UTC actual si no se provee."""
    ruta_base = tmp_path
    ruta_checkpoint = tmp_path / "checkpoint.json"
    checkpoint = GestorCheckpoint(ruta_archivo=ruta_checkpoint)

    resultado = extraer_juego(
        client=mock_steam_client,
        checkpoint=checkpoint,
        appid=1809540,
        ruta_base=ruta_base,
    )

    assert resultado == {"appdetails": True, "appreviews_resumen": True}
