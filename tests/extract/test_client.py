#suite de pruebas unitarias y contratos para el cliente http de steam (criterio f1-05)
#hermetico: sin llamadas a red, con pausas inyectadas sin esperas reales
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from src.extract.client import (
    SteamAppNotFoundError,
    SteamClient,
    SteamClientError,
    SteamNetworkError,
    SteamRateLimitError,
    SteamServerError,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "steam"


def _cargar_fixture(nombre_archivo: str) -> dict[str, Any]:
    """Cargar fixture grabada desde el directorio de pruebas."""
    ruta = FIXTURES_DIR / nombre_archivo
    with ruta.open(encoding="utf-8") as f:
        return json.load(f)


class DummyResponse:
    """Doble de prueba para simular requests.Response de forma hermetica."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self.text = json.dumps(json_data) if json_data is not None else ""

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        raise ValueError("sin contenido json")


# ---------------------------------------------------------------------------
# pruebas de casos exitosos
# ---------------------------------------------------------------------------

def test_get_app_details_exitoso() -> None:
    #obtener detalle de juego existente con respuesta 200 valida
    fixture = _cargar_fixture("appdetails_success_1809540.json")
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = DummyResponse(status_code=200, json_data=fixture)

    cliente = SteamClient(session=mock_session)
    resultado = cliente.get_app_details(1809540)

    assert resultado == fixture
    mock_session.get.assert_called_once()
    llamada_url = mock_session.get.call_args[0][0]
    assert "1809540" in llamada_url
    assert "cc=US" in llamada_url
    assert "l=english" in llamada_url


def test_get_app_reviews_summary_exitoso() -> None:
    #obtener resumen de resenas existente con respuesta 200 valida
    fixture = _cargar_fixture("appreviews_success_1809540.json")
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = DummyResponse(status_code=200, json_data=fixture)

    cliente = SteamClient(session=mock_session)
    resultado = cliente.get_app_reviews_summary(1809540)

    assert resultado == fixture
    mock_session.get.assert_called_once()
    llamada_url = mock_session.get.call_args[0][0]
    assert "1809540" in llamada_url
    assert "json=1" in llamada_url


# ---------------------------------------------------------------------------
# pruebas de error de negocio y exito falso
# ---------------------------------------------------------------------------

def test_get_app_details_exito_falso_lanza_error_tipado() -> None:
    #cuando steam responde 200 pero success es false, se lanza SteamAppNotFoundError
    fixture = _cargar_fixture("appdetails_failed_9999999.json")
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = DummyResponse(status_code=200, json_data=fixture)

    cliente = SteamClient(session=mock_session)
    with pytest.raises(SteamAppNotFoundError) as exc_info:
        cliente.get_app_details(9999999)

    assert "9999999" in str(exc_info.value)
    assert issubclass(SteamAppNotFoundError, SteamClientError)


# ---------------------------------------------------------------------------
# pruebas de manejo de 429 y backoff exponencial (f1-05)
# ---------------------------------------------------------------------------

def test_manejo_429_respeta_cabecera_retry_after() -> None:
    #ante 429 con cabecera Retry-After, duerme el tiempo indicado y reintenta
    fixture = _cargar_fixture("appdetails_success_1809540.json")
    resp_429 = DummyResponse(status_code=429, headers={"Retry-After": "4"})
    resp_200 = DummyResponse(status_code=200, json_data=fixture)

    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.side_effect = [resp_429, resp_200]

    pausas: list[float] = []
    cliente = SteamClient(
        session=mock_session,
        sleep_fn=lambda s: pausas.append(s),
    )

    resultado = cliente.get_app_details(1809540)

    assert resultado == fixture
    assert mock_session.get.call_count == 2
    assert pausas == [4.0]


def test_manejo_429_backoff_exponencial_sin_cabecera() -> None:
    #ante 429 sin Retry-After, aplica crecimiento exponencial de espera
    fixture = _cargar_fixture("appdetails_success_1809540.json")
    resp_429_1 = DummyResponse(status_code=429)
    resp_429_2 = DummyResponse(status_code=429)
    resp_200 = DummyResponse(status_code=200, json_data=fixture)

    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.side_effect = [resp_429_1, resp_429_2, resp_200]

    pausas: list[float] = []
    cliente = SteamClient(
        session=mock_session,
        backoff_factor=1.5,
        sleep_fn=lambda s: pausas.append(s),
    )

    resultado = cliente.get_app_details(1809540)

    assert resultado == fixture
    assert mock_session.get.call_count == 3
    #intento 0: 1.5 * (2 ** 0) = 1.5; intento 1: 1.5 * (2 ** 1) = 3.0
    assert pausas == [1.5, 3.0]


def test_manejo_429_tope_reintentos_lanza_error_tipado() -> None:
    #al agotar max_retries por 429 consecutivo, lanza SteamRateLimitError
    resp_429 = DummyResponse(status_code=429)

    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = resp_429

    pausas: list[float] = []
    cliente = SteamClient(
        session=mock_session,
        max_retries=2,
        sleep_fn=lambda s: pausas.append(s),
    )

    with pytest.raises(SteamRateLimitError) as exc_info:
        cliente.get_app_details(1809540)

    assert "tasa de peticiones excedida" in str(exc_info.value).lower()
    #primer intento + 2 reintentos = 3 llamadas en total
    assert mock_session.get.call_count == 3
    assert len(pausas) == 2


# ---------------------------------------------------------------------------
# pruebas de errores de servidor y red
# ---------------------------------------------------------------------------

def test_error_servidor_500_lanza_error_tipado() -> None:
    #un error 500 debe provocar SteamServerError inmediato
    resp_500 = DummyResponse(status_code=500)
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = resp_500

    cliente = SteamClient(session=mock_session)
    with pytest.raises(SteamServerError) as exc_info:
        cliente.get_app_details(1809540)

    assert "500" in str(exc_info.value)
    assert issubclass(SteamServerError, SteamClientError)


def test_error_conexion_lanza_error_tipado() -> None:
    #una falla de socket o dns de requests debe envolverse en SteamNetworkError
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.side_effect = requests.exceptions.ConnectionError("fallo de red simulado")

    cliente = SteamClient(session=mock_session)
    with pytest.raises(SteamNetworkError) as exc_info:
        cliente.get_app_details(1809540)

    assert "fallo de red" in str(exc_info.value).lower()
    assert issubclass(SteamNetworkError, SteamClientError)


def test_configuracion_parametros_fijos_region_e_idioma() -> None:
    #garantizar que los parametros cc y l se inyecten de forma fija segun criterio f1-02
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = DummyResponse(
        status_code=200, json_data={"1": {"success": True, "data": {}}}
    )

    cliente = SteamClient(session=mock_session, country_code="AR", language="spanish")
    cliente.get_app_details(1)

    url_llamada = mock_session.get.call_args[0][0]
    assert "cc=AR" in url_llamada
    assert "l=spanish" in url_llamada


def test_respuesta_json_invalido_lanza_error_servidor() -> None:
    #si steam devuelve 200 pero cuerpo corrupto, debe lanzar SteamServerError
    mock_session = MagicMock(spec=requests.Session)
    resp_corrupta = DummyResponse(status_code=200, json_data=None)
    mock_session.get.return_value = resp_corrupta

    cliente = SteamClient(session=mock_session)
    with pytest.raises(SteamServerError) as exc_info:
        cliente.get_app_details(1809540)

    assert "json no valida" in str(exc_info.value).lower()


def test_codigo_http_inesperado_lanza_error_cliente() -> None:
    #codigos como 403 o 400 deben lanzar SteamClientError generico
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = DummyResponse(status_code=403)

    cliente = SteamClient(session=mock_session)
    with pytest.raises(SteamClientError) as exc_info:
        cliente.get_app_details(1809540)

    assert "403" in str(exc_info.value)


def test_appid_ausente_en_diccionario_lanza_error_no_encontrado() -> None:
    #si la respuesta json 200 no contiene la clave del appid, lanza SteamAppNotFoundError
    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.return_value = DummyResponse(status_code=200, json_data={})

    cliente = SteamClient(session=mock_session)
    with pytest.raises(SteamAppNotFoundError) as exc_info:
        cliente.get_app_details(1809540)

    assert "1809540" in str(exc_info.value)


def test_retry_after_no_numerico_usa_backoff_exponencial() -> None:
    #si la cabecera Retry-After contiene texto invalido, se calcula backoff exponencial
    fixture = _cargar_fixture("appdetails_success_1809540.json")
    resp_429 = DummyResponse(status_code=429, headers={"Retry-After": "invalido"})
    resp_200 = DummyResponse(status_code=200, json_data=fixture)

    mock_session = MagicMock(spec=requests.Session)
    mock_session.get.side_effect = [resp_429, resp_200]

    pausas: list[float] = []
    cliente = SteamClient(
        session=mock_session,
        backoff_factor=2.0,
        sleep_fn=lambda s: pausas.append(s),
    )

    resultado = cliente.get_app_details(1809540)

    assert resultado == fixture
    #2.0 * (2 ** 0) = 2.0
    assert pausas == [2.0]

