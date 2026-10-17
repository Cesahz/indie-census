#suite de pruebas para clasificador determinista de motores de juego
#evalua niveles de evidencia 1 a 4 y resolucion de conflictos
import pytest

from src.classify.engine import ResultadoMotor, clasificar_motor
from src.classify.taxonomy import cargar_taxonomia


@pytest.fixture(scope="module")
def taxonomia():
    """Cargar la taxonomia para reutilizar en las pruebas del clasificador."""
    return cargar_taxonomia()


def test_motor_nivel_1_descripcion_explicita(taxonomia) -> None:
    """Verificar deteccion nivel 1 con 'Made with Godot' en la descripcion."""
    desc = "This is a retro adventure game made with Godot and passion."
    res = clasificar_motor(descripcion=desc, taxonomia=taxonomia)
    assert isinstance(res, ResultadoMotor)
    assert res.engine == "godot"
    assert res.evidence_level == 1
    assert "godot" in res.detalles.lower()


def test_motor_nivel_1_creditos(taxonomia) -> None:
    """Verificar deteccion nivel 1 cuando la declaracion esta en creditos."""
    creditos = "Special thanks to Epic Games. Built with Unreal Engine 5."
    res = clasificar_motor(creditos=creditos, taxonomia=taxonomia)
    assert res.engine == "unreal"
    assert res.evidence_level == 1


def test_motor_nivel_2_tag_tienda(taxonomia) -> None:
    """Verificar deteccion nivel 2 cuando el motor aparece en tags de tienda."""
    tags = ["Indie", "Action", "unity", "Singleplayer"]
    res = clasificar_motor(tags=tags, taxonomia=taxonomia)
    assert res.engine == "unity"
    assert res.evidence_level == 2


def test_motor_nivel_3_firma_tecnica(taxonomia) -> None:
    """Verificar deteccion nivel 3 cuando se proporciona una firma tecnica."""
    res = clasificar_motor(firma_tecnica="godot_binary", taxonomia=taxonomia)
    assert res.engine == "godot"
    assert res.evidence_level == 3


def test_motor_nivel_4_regex_descripcion(taxonomia) -> None:
    """Verificar deteccion nivel 4 por mencion simple en descripcion."""
    desc = "The game was exported using gamemaker tools."
    res = clasificar_motor(descripcion=desc, taxonomia=taxonomia)
    assert res.engine == "gamemaker"
    assert res.evidence_level == 4


def test_jerarquia_evidencia_nivel_1_supera_nivel_2(taxonomia) -> None:
    """Verificar que evidencia nivel 1 (Godot) prevalece sobre tag nivel 2 (Unity)."""
    desc = "Proudly made with Godot."
    tags = ["unity", "2D"]
    res = clasificar_motor(descripcion=desc, tags=tags, taxonomia=taxonomia)
    assert res.engine == "godot"
    assert res.evidence_level == 1


def test_jerarquia_evidencia_nivel_2_supera_nivel_4(taxonomia) -> None:
    """Verificar que un tag nivel 2 prevalece sobre una mencion indirecta nivel 4."""
    tags = ["godot"]
    desc = "Inspired by older games built on unreal engine."
    res = clasificar_motor(descripcion=desc, tags=tags, taxonomia=taxonomia)
    assert res.engine == "godot"
    assert res.evidence_level == 2


def test_sin_senales_devuelve_unknown(taxonomia) -> None:
    """Verificar que un juego sin menciones de motor devuelve unknown y evidencia None."""
    desc = "A simple puzzle game with cats."
    tags = ["Puzzle", "Cute"]
    res = clasificar_motor(descripcion=desc, tags=tags, taxonomia=taxonomia)
    assert res.engine == "unknown"
    assert res.evidence_level is None


def test_resolucion_conflicto_mismo_nivel(taxonomia) -> None:
    """Verificar resolucion determinista si hay dos motores detectados al mismo nivel."""
    tags = ["godot", "unity"]
    res = clasificar_motor(tags=tags, taxonomia=taxonomia)
    #debe retornar un resultado determinista sin lanzar excepcion
    assert res.engine in ["godot", "unity"]
    assert res.evidence_level == 2
    assert "conflicto" in res.detalles.lower() or "detectados" in res.detalles.lower()
