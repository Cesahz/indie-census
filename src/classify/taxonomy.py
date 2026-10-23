#modulo de definicion y carga de taxonomia semantica
#valida esquemas mediante pydantic y provee configuraciones tipadas
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

#ruta raiz del proyecto
REPO_ROOT = Path(__file__).resolve().parents[2]
RUTA_TAXONOMIA_DEFECTO = REPO_ROOT / "config" / "taxonomy.yaml"


class MotorTaxonomia(BaseModel):
    """Definicion de motor y sus reglas de deteccion jerarquicas."""

    nombre: str
    aliases: list[str] = Field(default_factory=list)
    patrones_regex_nivel_1: list[str] = Field(default_factory=list)
    tags_nivel_2: list[str] = Field(default_factory=list)
    patrones_regex_nivel_4: list[str] = Field(default_factory=list)


class AIDisclosureTaxonomia(BaseModel):
    """Patrones y reglas para clasificar divulgacion de inteligencia artificial."""

    patrones_descriptor_steam: list[str] = Field(default_factory=list)
    tags_tienda: list[str] = Field(default_factory=list)
    patrones_autodivulgacion: list[str] = Field(default_factory=list)


class PesosIndieScore(BaseModel):
    """Ponderacion de los componentes del indie score."""

    tag_indie: float = 0.25
    auto_publicado_o_pequeno: float = 0.25
    precio_bajo: float = 0.15
    pocos_idiomas: float = 0.10
    sin_major_publisher: float = 0.25


class UmbralesTaxonomia(BaseModel):
    """Umbrales de corte y listas de exclusion para juegos independientes."""

    precio_max_indie_usd: float = 35.0
    max_idiomas_indie: int = 8
    max_titulos_publisher_pequeno: int = 5
    max_titulos_publisher_mediano: int = 25
    umbral_corte_is_indie: float = 0.6
    pesos_indie_score: PesosIndieScore = Field(default_factory=PesosIndieScore)
    publishers_excluidos: list[str] = Field(default_factory=list)



class ConfiguracionTaxonomia(BaseModel):
    """Contrato raiz de configuracion taxonomica del proyecto."""

    motores: dict[str, MotorTaxonomia]
    generos: dict[str, Any]
    ai_disclosure: AIDisclosureTaxonomia
    umbrales: UmbralesTaxonomia


def cargar_taxonomia(ruta_yaml: Optional[Path] = None) -> ConfiguracionTaxonomia:
    """Cargar y validar la configuracion taxonomica desde un archivo YAML."""
    ruta = ruta_yaml or RUTA_TAXONOMIA_DEFECTO
    if not ruta.is_file():
        raise FileNotFoundError(f"Archivo de taxonomia no encontrado: {ruta}")

    with ruta.open(encoding="utf-8") as f:
        contenido = yaml.safe_load(f) or {}

    #validar estructura con pydantic
    return ConfiguracionTaxonomia(**contenido)
