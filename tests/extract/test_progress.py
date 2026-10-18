#suite de pruebas unitarias para el renderizador de barra de progreso en consola
#evalua calculo porcentual, formato de eta, tolerancia a codificacion cp1252 y flujo de cierre
import io
import time
from unittest.mock import MagicMock

from src.extract.client import SteamClient
from src.extract.pipeline import ejecutar_ingesta_masiva
from src.extract.progress import BarraProgreso, formatear_tiempo_estimado


def test_formatear_tiempo_estimado() -> None:
    #segundos
    assert formatear_tiempo_estimado(45) == "45s"
    #minutos y segundos
    assert formatear_tiempo_estimado(125) == "2m 05s"
    #horas y minutos
    assert formatear_tiempo_estimado(3720) == "1h 02m"
    #tiempo negativo o cero
    assert formatear_tiempo_estimado(0) == "0s"
    assert formatear_tiempo_estimado(-10) == "0s"


def test_barra_progreso_renderiza_salida_en_stream() -> None:
    #renderiza porcentaje, conteos, appid y eta forzando la escritura
    buffer = io.StringIO()
    barra = BarraProgreso(total=100, ancho=20, stream=buffer, habilitado=True)

    barra.actualizar(actual=50, appid=12345, exitosos=48, fallidos=2, forzar=True)
    contenido = buffer.getvalue()

    assert "50.0%" in contenido
    assert "50/100" in contenido
    assert "Exito: 48" in contenido
    assert "Fallo: 2" in contenido
    assert "AppID: 12345" in contenido


def test_barra_progreso_deshabilitada_no_emite_salida() -> None:
    #si habilitado es False no se escribe nada en el stream
    buffer = io.StringIO()
    barra = BarraProgreso(total=50, ancho=20, stream=buffer, habilitado=False)

    barra.actualizar(actual=25, appid=999, exitosos=25, fallidos=0, forzar=True)
    barra.cerrar()

    assert buffer.getvalue() == ""


def test_barra_progreso_resiliencia_codificacion_ascii() -> None:
    #si el stream falla al codificar caracteres unicode (como en consolas cp1252), conmuta a ascii
    class StreamFallaUnicode(io.StringIO):
        def write(self, s: str) -> int:
            if "\u2588" in s or "\u2591" in s:
                raise UnicodeEncodeError("charmap", s, 0, 1, "character maps to <undefined>")
            return super().write(s)

    stream_mock = StreamFallaUnicode()
    barra = BarraProgreso(total=10, ancho=10, stream=stream_mock, habilitado=True)

    #debe capturar el error y conmutar a caracteres ascii sin lanzar excepcion
    barra.actualizar(actual=5, appid=10, exitosos=5, fallidos=0, forzar=True)
    contenido = stream_mock.getvalue()

    assert "=" in contenido
    assert "50.0%" in contenido


def test_barra_progreso_cerrar_agrega_salto_de_linea() -> None:
    #al cerrar imprime salto de linea final para preservar la linea
    buffer = io.StringIO()
    barra = BarraProgreso(total=10, ancho=10, stream=buffer, habilitado=True)

    barra.actualizar(actual=10, appid=10, exitosos=10, fallidos=0, forzar=True)
    barra.cerrar()

    assert buffer.getvalue().endswith("\n")


def test_ejecutar_ingesta_masiva_integra_barra_progreso(tmp_path) -> None:
    #ejecutar_ingesta_masiva acepta stream y actualiza el progreso en terminal
    buffer = io.StringIO()
    mock_client = MagicMock(spec=SteamClient)
    mock_client.country_code = "US"
    mock_client.language = "english"
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.get_app_details.return_value = {"success": True}
    mock_client.get_app_reviews_summary.return_value = {
        "success": 1,
        "query_summary": {"total_reviews": 10, "total_positive": 9, "total_negative": 1},
    }

    appids = [101, 102]
    resumen = ejecutar_ingesta_masiva(
        appids=appids,
        client=mock_client,
        fecha="2026-10-18",
        ruta_base=tmp_path,
        mostrar_progreso=True,
        stream_progreso=buffer,
    )

    assert resumen["procesados_exito"] == 2
    salida = buffer.getvalue()
    assert "100.0%" in salida
    assert "2/2" in salida
