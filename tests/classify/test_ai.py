#suite de pruebas para clasificador de divulgacion de ia
#incluye prueba de contencion etica: prohibido el analisis visual o de estilo
import pytest

from src.classify.ai import (
    NivelDivulgacionIA,
    ResultadoIA,
    clasificar_divulgacion_ia,
)
from src.classify.taxonomy import cargar_taxonomia


@pytest.fixture(scope="module")
def taxonomia():
    """Cargar la taxonomia para reutilizar en las pruebas de clasificacion de IA."""
    return cargar_taxonomia()


def test_ia_nivel_declared_steam_descriptor(taxonomia) -> None:
    """Verificar nivel declared cuando Steam incluye descriptor formal de IA generativa."""
    descriptors = ["This title contains generative AI content created during development."]
    res = clasificar_divulgacion_ia(descriptors_steam=descriptors, taxonomia=taxonomia)
    assert isinstance(res, ResultadoIA)
    assert res.disclosure_level == NivelDivulgacionIA.DECLARED
    assert "declaracion formal" in res.detalles.lower()


def test_ia_nivel_tagged_tienda(taxonomia) -> None:
    """Verificar nivel tagged cuando el juego posee tags relativos a IA."""
    tags = ["Indie", "Generative AI", "Puzzle"]
    res = clasificar_divulgacion_ia(tags=tags, taxonomia=taxonomia)
    assert res.disclosure_level == NivelDivulgacionIA.TAGGED
    assert "tag" in res.detalles.lower()


def test_ia_nivel_self_reported_descripcion(taxonomia) -> None:
    """Verificar nivel self_reported cuando el desarrollador lo menciona en la descripcion."""
    desc = "Background music and extra assets generated with AI tools."
    res = clasificar_divulgacion_ia(descripcion_o_notas=desc, taxonomia=taxonomia)
    assert res.disclosure_level == NivelDivulgacionIA.SELF_REPORTED
    assert "autodivulgacion" in res.detalles.lower()


def test_ia_nivel_unknown_sin_declaraciones(taxonomia) -> None:
    """Verificar nivel unknown cuando no existe ninguna declaracion o tag de IA."""
    desc = "A classic hand-drawn platformer."
    tags = ["Platformer", "2D", "Hand-drawn"]
    res = clasificar_divulgacion_ia(descripcion_o_notas=desc, tags=tags, taxonomia=taxonomia)
    assert res.disclosure_level == NivelDivulgacionIA.UNKNOWN


def test_jerarquia_declared_supera_tagged(taxonomia) -> None:
    """Verificar que declared tiene mayor precedencia que tagged."""
    descriptors = ["Generative AI used for localized voices."]
    tags = ["ai"]
    res = clasificar_divulgacion_ia(
        descriptors_steam=descriptors,
        tags=tags,
        taxonomia=taxonomia,
    )
    assert res.disclosure_level == NivelDivulgacionIA.DECLARED


def test_prueba_de_contencion_etica_rechaza_analisis_visual(taxonomia) -> None:
    """Verificar prueba de contencion: la funcion rechaza parametros de analisis visual o estilo."""
    #la funcion no debe aceptar argumentos de imagenes o heuristica visual
    with pytest.raises(TypeError):
        # pyrefly: ignore
        clasificar_divulgacion_ia(
            imagen_bytes=b"fake_image_bytes",  # type: ignore[call-arg]
            taxonomia=taxonomia,
        )
