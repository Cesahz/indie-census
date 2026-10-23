#modulo de calculo de autenticidad indie y clasificacion de independencia
#evalua reglas multidimensionales y penalizaciones por major publishers
import re
from typing import Optional

from pydantic import BaseModel, Field

from src.classify.taxonomy import ConfiguracionTaxonomia, cargar_taxonomia


class ResultadoIndie(BaseModel):
    """Resultado estructurado de la clasificacion de independencia."""

    indie_score: float = Field(ge=0.0, le=1.0)
    is_indie: bool
    desglose: dict[str, float]
    es_major_publisher: bool


def calcular_indie_score(
    tags: Optional[list[str]] = None,
    generos: Optional[list[str]] = None,
    developers: Optional[list[str]] = None,
    publishers: Optional[list[str]] = None,
    price_usd: Optional[float] = None,
    language_count: Optional[int] = None,
    titulos_del_publisher: Optional[int] = None,
    taxonomia: Optional[ConfiguracionTaxonomia] = None,
) -> ResultadoIndie:
    """Calcular el score de autenticidad indie y determinar si califica como indie."""
    tax = taxonomia or cargar_taxonomia()
    pesos = tax.umbrales.pesos_indie_score

    #1. evaluar etiqueta o genero indie
    tags_norm = [t.strip().lower() for t in (tags or []) if t]
    generos_norm = [g.strip().lower() for g in (generos or []) if g]
    tiene_tag_indie = ("indie" in tags_norm) or ("indie" in generos_norm)
    score_tag = 1.0 if tiene_tag_indie else 0.0

    #2. evaluar ausencia de major publisher conocido o distribuidor masivo
    devs_norm = [d.strip() for d in (developers or []) if d]
    pubs_norm = [p.strip() for p in (publishers or []) if p]

    es_major = False
    pubs_excluidos = tax.umbrales.publishers_excluidos
    for pub in pubs_norm:
        for exc in pubs_excluidos:
            patron = rf"\b{re.escape(exc)}\b"
            if re.search(patron, pub, re.IGNORECASE):
                es_major = True
                break
        if es_major:
            break

    #evaluar distribucion masiva por tamano de catalogo (>25 titulos)
    max_mediano = getattr(tax.umbrales, "max_titulos_publisher_mediano", 25)
    es_distribuidor_masivo = bool(
        titulos_del_publisher is not None and titulos_del_publisher > max_mediano
    )
    es_corporativo_o_masivo = es_major or es_distribuidor_masivo
    score_sin_major = 0.0 if es_corporativo_o_masivo else 1.0

    #3. evaluar autopublicacion o publisher pequeno
    es_autopublicado = False
    if devs_norm and pubs_norm:
        #verificar coincidencia entre desarrollador y publicador
        for dev in devs_norm:
            dev_l = dev.lower()
            if any(dev_l == p.lower() or dev_l in p.lower() or p.lower() in dev_l for p in pubs_norm):
                es_autopublicado = True
                break

    if es_corporativo_o_masivo:
        #si es publisher grande o corporacion no aplica bonificacion indie
        score_pub = 0.0
    elif titulos_del_publisher is not None and titulos_del_publisher <= tax.umbrales.max_titulos_publisher_pequeno:
        score_pub = 1.0
    elif titulos_del_publisher is not None and titulos_del_publisher <= max_mediano:
        #curva suave para publishers independientes medianos entre 5 y 25 titulos
        rango = max_mediano - tax.umbrales.max_titulos_publisher_pequeno
        score_pub = round(max(0.4, 1.0 - ((titulos_del_publisher - tax.umbrales.max_titulos_publisher_pequeno) / rango * 0.6)), 4)
    elif es_autopublicado:
        score_pub = 1.0
    elif not pubs_norm and devs_norm:
        #sin publicador listado, asume autogestion
        score_pub = 1.0
    elif devs_norm or pubs_norm:
        score_pub = 0.0
    else:
        score_pub = 0.5

    #4. evaluar precio de lanzamiento
    if price_usd is None:
        score_precio = 0.5
    elif price_usd <= tax.umbrales.precio_max_indie_usd:
        score_precio = 1.0
    else:
        exceso = price_usd - tax.umbrales.precio_max_indie_usd
        score_precio = max(0.0, 1.0 - (exceso / 30.0))

    #5. evaluar cantidad de idiomas (proxy de presupuesto de localizacion)
    if language_count is None:
        score_idiomas = 0.5
    elif language_count <= tax.umbrales.max_idiomas_indie:
        score_idiomas = 1.0
    else:
        exceso_idiomas = language_count - tax.umbrales.max_idiomas_indie
        score_idiomas = max(0.0, 1.0 - (exceso_idiomas / 15.0))

    desglose = {
        "tag_indie": round(score_tag * pesos.tag_indie, 4),
        "auto_publicado_o_pequeno": round(score_pub * pesos.auto_publicado_o_pequeno, 4),
        "precio_bajo": round(score_precio * pesos.precio_bajo, 4),
        "pocos_idiomas": round(score_idiomas * pesos.pocos_idiomas, 4),
        "sin_major_publisher": round(score_sin_major * pesos.sin_major_publisher, 4),
    }

    total_score = sum(desglose.values())
    total_score_acotado = max(0.0, min(1.0, round(total_score, 4)))

    is_indie = (not es_corporativo_o_masivo) and (total_score_acotado >= tax.umbrales.umbral_corte_is_indie)

    return ResultadoIndie(
        indie_score=total_score_acotado,
        is_indie=is_indie,
        desglose=desglose,
        es_major_publisher=es_corporativo_o_masivo,
    )
