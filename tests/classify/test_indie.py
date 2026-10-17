#suite de pruebas para calculo de indie_score y clasificacion de independencia
#evalua reglas multidimensionales y penalizaciones por major publishers
import pytest

from src.classify.indie import ResultadoIndie, calcular_indie_score
from src.classify.taxonomy import cargar_taxonomia


@pytest.fixture(scope="module")
def taxonomia():
    """Cargar la taxonomia para reutilizar en las pruebas del clasificador indie."""
    return cargar_taxonomia()


def test_juego_indie_arquetipico(taxonomia) -> None:
    """Verificar que un juego desarrollado y publicado por la misma persona obtiene score alto."""
    res = calcular_indie_score(
        tags=["Indie", "Pixel Graphics", "Metroidvania"],
        generos=["Action", "Indie"],
        developers=["Solo Dev"],
        publishers=["Solo Dev"],
        price_usd=14.99,
        language_count=2,
        titulos_del_publisher=1,
        taxonomia=taxonomia,
    )
    assert isinstance(res, ResultadoIndie)
    assert res.indie_score >= 0.85
    assert res.is_indie is True
    assert res.es_major_publisher is False
    assert res.desglose["tag_indie"] > 0.0
    assert res.desglose["auto_publicado_o_pequeno"] > 0.0


def test_juego_major_publisher_bloqueante(taxonomia) -> None:
    """Verificar que un juego publicado por Electronic Arts es penalizado severamente."""
    res = calcular_indie_score(
        tags=["Indie", "Simulation"],
        generos=["Simulation"],
        developers=["Small Studio"],
        publishers=["Electronic Arts"],
        price_usd=19.99,
        language_count=5,
        titulos_del_publisher=200,
        taxonomia=taxonomia,
    )
    assert res.es_major_publisher is True
    assert res.is_indie is False
    #sin_major_publisher debe ser 0.0
    assert res.desglose["sin_major_publisher"] == 0.0
    assert res.indie_score < 0.6


def test_juego_aaa_completo(taxonomia) -> None:
    """Verificar que un juego AAA con precio alto y muchos idiomas obtiene score minimo."""
    res = calcular_indie_score(
        tags=["Action", "Open World", "Multiplayer"],
        generos=["Action"],
        developers=["Ubisoft Montreal"],
        publishers=["Ubisoft"],
        price_usd=69.99,
        language_count=14,
        titulos_del_publisher=150,
        taxonomia=taxonomia,
    )
    assert res.is_indie is False
    assert res.es_major_publisher is True
    assert res.indie_score < 0.25


def test_juego_gratuito_indie(taxonomia) -> None:
    """Verificar que un juego gratuito autogestionado obtiene puntos de precio bajo."""
    res = calcular_indie_score(
        tags=["Indie", "Visual Novel"],
        generos=["Adventure"],
        developers=["Indie Creator"],
        publishers=["Indie Creator"],
        price_usd=0.0,
        language_count=1,
        titulos_del_publisher=1,
        taxonomia=taxonomia,
    )
    assert res.desglose["precio_bajo"] > 0.0
    assert res.indie_score >= 0.8
    assert res.is_indie is True


def test_datos_nulos_o_vacios(taxonomia) -> None:
    """Verificar que entradas vacias no lanzan excepciones y retornan valores validos."""
    res = calcular_indie_score(taxonomia=taxonomia)
    assert 0.0 <= res.indie_score <= 1.0
    assert isinstance(res.is_indie, bool)
    assert res.es_major_publisher is False
