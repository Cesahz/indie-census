#modulo de clasificacion de divulgacion de inteligencia artificial
#regla inviolable: clasificacion exclusivamente basada en declaraciones formales y metadatos
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from src.classify.taxonomy import ConfiguracionTaxonomia, cargar_taxonomia


class NivelDivulgacionIA(str, Enum):
    """Niveles formales de divulgacion de IA en plataformas de distribucion."""

    DECLARED = "declared"
    TAGGED = "tagged"
    SELF_REPORTED = "self_reported"
    UNKNOWN = "unknown"


class ResultadoIA(BaseModel):
    """Resultado estructurado de la clasificacion de uso divulgado de IA."""

    disclosure_level: NivelDivulgacionIA
    detalles: str


def clasificar_divulgacion_ia(
    descriptors_steam: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    descripcion_o_notas: Optional[str] = None,
    taxonomia: Optional[ConfiguracionTaxonomia] = None,
) -> ResultadoIA:
    """Clasificar el nivel formal de declaracion de IA sin realizar inferencias estilisticas o visuales."""
    tax = taxonomia or cargar_taxonomia()

    #1. evaluar declaracion formal en descriptores de steam (nivel declared)
    if descriptors_steam:
        for desc in descriptors_steam:
            if not desc:
                continue
            for patron in tax.ai_disclosure.patrones_descriptor_steam:
                if re.search(patron, desc):
                    return ResultadoIA(
                        disclosure_level=NivelDivulgacionIA.DECLARED,
                        detalles="Declaracion formal en descriptor de contenido de tienda",
                    )

    #2. evaluar tags de tienda (nivel tagged)
    tags_norm = [t.strip().lower() for t in (tags or []) if t]
    tags_ia = [t.strip().lower() for t in tax.ai_disclosure.tags_tienda]
    for tag in tags_norm:
        if tag in tags_ia:
            return ResultadoIA(
                disclosure_level=NivelDivulgacionIA.TAGGED,
                detalles=f"Tag de tienda detectado: '{tag}'",
            )

    #3. evaluar autodivulgacion en texto de descripcion o notas (nivel self_reported)
    if descripcion_o_notas:
        for patron in tax.ai_disclosure.patrones_autodivulgacion:
            match = re.search(patron, descripcion_o_notas)
            if match:
                return ResultadoIA(
                    disclosure_level=NivelDivulgacionIA.SELF_REPORTED,
                    detalles=f"Autodivulgacion en descripcion o notas: '{match.group(0)}'",
                )

    #4. sin declaraciones comprobables (nivel unknown)
    return ResultadoIA(
        disclosure_level=NivelDivulgacionIA.UNKNOWN,
        detalles="Sin senales de declaracion formal de IA",
    )
