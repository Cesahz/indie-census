#modulo de clasificacion determinista de motores de juego
#evalua niveles de evidencia 1 a 4 con resolucion de conflictos
import re
from typing import Optional

from pydantic import BaseModel

from src.classify.taxonomy import ConfiguracionTaxonomia, cargar_taxonomia


class ResultadoMotor(BaseModel):
    """Resultado estructurado de la clasificacion de motor."""

    engine: str
    evidence_level: Optional[int] = None
    detalles: str


def clasificar_motor(
    descripcion: Optional[str] = None,
    tags: Optional[list[str]] = None,
    creditos: Optional[str] = None,
    firma_tecnica: Optional[str] = None,
    taxonomia: Optional[ConfiguracionTaxonomia] = None,
) -> ResultadoMotor:
    """Clasificar el motor de un juego evaluando niveles de evidencia 1 a 4."""
    tax = taxonomia or cargar_taxonomia()

    texto_nivel_1 = ""
    if descripcion:
        texto_nivel_1 += f" {descripcion}"
    if creditos:
        texto_nivel_1 += f" {creditos}"

    tags_normalizados = [t.strip().lower() for t in (tags or []) if t]

    #1. evaluar nivel 1: declaracion formal o explicita en descripcion o creditos
    coincidencias_nivel_1: list[tuple[str, str]] = []
    if texto_nivel_1:
        for cod_motor, motor in tax.motores.items():
            for patron in motor.patrones_regex_nivel_1:
                match = re.search(patron, texto_nivel_1)
                if match:
                    coincidencias_nivel_1.append((cod_motor, match.group(0)))
                    break

    if coincidencias_nivel_1:
        #resolucion determinista en caso de multiples coincidencias
        coincidencias_nivel_1.sort(key=lambda x: x[0])
        ganador, fragmento = coincidencias_nivel_1[0]
        detalles = f"Nivel 1: declaracion formal detectada ('{fragmento}') para {ganador}"
        if len(coincidencias_nivel_1) > 1:
            otros = [c[0] for c in coincidencias_nivel_1[1:]]
            detalles += f"; conflicto resuelto frente a {otros}"
        return ResultadoMotor(engine=ganador, evidence_level=1, detalles=detalles)

    #2. evaluar nivel 2: tags de tienda o de usuario
    coincidencias_nivel_2: list[str] = []
    if tags_normalizados:
        for cod_motor, motor in tax.motores.items():
            for tag_motor in motor.tags_nivel_2:
                if tag_motor.lower() in tags_normalizados:
                    coincidencias_nivel_2.append(cod_motor)
                    break

    if coincidencias_nivel_2:
        coincidencias_nivel_2.sort()
        ganador = coincidencias_nivel_2[0]
        detalles = f"Nivel 2: tag de tienda detectado para {ganador}"
        if len(coincidencias_nivel_2) > 1:
            otros = coincidencias_nivel_2[1:]
            detalles += f"; conflicto resuelto: detectados multiples tags {otros}"
        return ResultadoMotor(engine=ganador, evidence_level=2, detalles=detalles)

    #3. evaluar nivel 3: firma tecnica comprobada
    if firma_tecnica:
        firma_lower = firma_tecnica.lower()
        for cod_motor, motor in tax.motores.items():
            if any(alias.lower() in firma_lower for alias in motor.aliases) or cod_motor in firma_lower:
                return ResultadoMotor(
                    engine=cod_motor,
                    evidence_level=3,
                    detalles=f"Nivel 3: firma tecnica verificada '{firma_tecnica}' para {cod_motor}",
                )

    #4. evaluar nivel 4: inferencia por regex en descripcion
    coincidencias_nivel_4: list[tuple[str, str]] = []
    if descripcion:
        for cod_motor, motor in tax.motores.items():
            for patron in motor.patrones_regex_nivel_4:
                match = re.search(patron, descripcion)
                if match:
                    coincidencias_nivel_4.append((cod_motor, match.group(0)))
                    break

    if coincidencias_nivel_4:
        coincidencias_nivel_4.sort(key=lambda x: x[0])
        ganador, fragmento = coincidencias_nivel_4[0]
        detalles = f"Nivel 4: mencion regex detectada ('{fragmento}') para {ganador}"
        if len(coincidencias_nivel_4) > 1:
            otros = [c[0] for c in coincidencias_nivel_4[1:]]
            detalles += f"; conflicto resuelto frente a {otros}"
        return ResultadoMotor(engine=ganador, evidence_level=4, detalles=detalles)

    #sin coincidencia
    return ResultadoMotor(
        engine="unknown",
        evidence_level=None,
        detalles="Sin senales comprobables de motor",
    )
