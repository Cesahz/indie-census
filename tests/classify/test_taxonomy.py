#suite de pruebas para taxonomia semantica
#valida esquemas pydantic, carga de configuracion y coherencia
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.classify.taxonomy import (
    ConfiguracionTaxonomia,
    MotorTaxonomia,
    cargar_taxonomia,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_cargar_taxonomia_archivo_por_defecto() -> None:
    """Verificar que cargar_taxonomia sin argumentos carga config/taxonomy.yaml exitosamente."""
    tax = cargar_taxonomia()
    assert isinstance(tax, ConfiguracionTaxonomia)
    assert "godot" in tax.motores
    assert "unity" in tax.motores
    assert "unreal" in tax.motores
    assert "gamemaker" in tax.motores


def test_cargar_taxonomia_archivo_inexistente(tmp_path: Path) -> None:
    """Verificar que una ruta inexistente lanza FileNotFoundError."""
    ruta_falsa = tmp_path / "no_existe.yaml"
    with pytest.raises(FileNotFoundError):
        cargar_taxonomia(ruta_falsa)


def test_motores_patrones_regex_compilables() -> None:
    """Verificar que todas las expresiones regulares de motores compilan sin error."""
    tax = cargar_taxonomia()
    for nombre_motor, motor in tax.motores.items():
        assert isinstance(motor, MotorTaxonomia)
        assert motor.nombre
        assert len(motor.aliases) > 0
        for patron in motor.patrones_regex_nivel_1:
            compilado = re.compile(patron)
            assert compilado is not None
        for patron in motor.patrones_regex_nivel_4:
            compilado = re.compile(patron)
            assert compilado is not None


def test_ai_disclosure_patrones_compilables() -> None:
    """Verificar que todas las expresiones regulares de divulgacion de IA compilan."""
    tax = cargar_taxonomia()
    for patron in tax.ai_disclosure.patrones_descriptor_steam:
        assert re.compile(patron) is not None
    for patron in tax.ai_disclosure.patrones_autodivulgacion:
        assert re.compile(patron) is not None
    assert len(tax.ai_disclosure.tags_tienda) > 0


def test_umbrales_pesos_suman_uno() -> None:
    """Verificar que la suma de los pesos de indie_score sea exactamente 1.0."""
    tax = cargar_taxonomia()
    pesos = tax.umbrales.pesos_indie_score
    total_pesos = (
        pesos.tag_indie
        + pesos.auto_publicado_o_pequeno
        + pesos.precio_bajo
        + pesos.pocos_idiomas
        + pesos.sin_major_publisher
    )
    assert pytest.approx(total_pesos, abs=1e-5) == 1.0


def test_publishers_excluidos_presentes() -> None:
    """Verificar que la lista de publishers excluidos contenga las empresas clave."""
    tax = cargar_taxonomia()
    pubs = tax.umbrales.publishers_excluidos
    assert len(pubs) >= 15
    pubs_lower = [p.lower() for p in pubs]
    assert "electronic arts" in pubs_lower
    assert "ubisoft" in pubs_lower
    assert "square enix" in pubs_lower
    assert "activision" in pubs_lower
    assert "valve" in pubs_lower


def test_validacion_pydantic_falla_si_estructura_invalida() -> None:
    """Verificar que un diccionario con tipos invalidos lanza ValidationError."""
    datos_invalidos: dict[str, Any] = {
        "motores": "no_es_un_dict",
        "generos": {},
        "ai_disclosure": {},
        "umbrales": {},
    }
    with pytest.raises(ValidationError):
        ConfiguracionTaxonomia(**datos_invalidos)
