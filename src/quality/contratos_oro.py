#modulo de contratos estadisticos y control de calidad en capa oro
#valida continuidad temporal estricta y control de bandas 3-sigma
import math
from collections import defaultdict
from typing import Optional

import pyarrow as pa


class ContratoContinuidadTemporalError(Exception):
    """Error bloqueante emitido cuando existen meses vacios entre el inicio y la fecha de corte."""


class ContratoRangoHistoricoError(Exception):
    """Error bloqueante emitido cuando un conteo mensual viola la banda estadistica de 3 desviaciones estandar."""


def _generar_secuencia_meses(mes_inicio: str, mes_corte: str) -> list[str]:
    """Generar lista cronologica de meses en formato AAAA-MM entre mes_inicio y mes_corte inclusive."""
    anio_ini, m_ini = [int(x) for x in mes_inicio.split("-")]
    anio_fin, m_fin = [int(x) for x in mes_corte.split("-")]

    secuencia = []
    actual_anio = anio_ini
    actual_mes = m_ini
    while (actual_anio < anio_fin) or (actual_anio == anio_fin and actual_mes <= m_fin):
        secuencia.append(f"{actual_anio:04d}-{actual_mes:02d}")
        actual_mes += 1
        if actual_mes > 12:
            actual_mes = 1
            actual_anio += 1
    return secuencia


def validar_continuidad_temporal_oro(
    engine_monthly: pa.Table,
    mes_inicio: str = "2024-01",
    mes_corte: str = "2026-10",
) -> None:
    """Verificar que todos los meses calendario en [mes_inicio, mes_corte] existen con conteo > 0."""
    secuencia_esperada = _generar_secuencia_meses(mes_inicio, mes_corte)
    filas = engine_monthly.to_pylist()

    conteos_por_mes: dict[str, int] = defaultdict(int)
    for fila in filas:
        ym = str(fila.get("year_month", ""))
        conteos_por_mes[ym] += int(fila.get("releases_count", 0))

    for mes in secuencia_esperada:
        if mes not in conteos_por_mes or conteos_por_mes[mes] <= 0:
            raise ContratoContinuidadTemporalError(
                f"Mes vacio o ausente en serie temporal: {mes} (conteo={conteos_por_mes.get(mes, 0)})."
            )


def validar_rango_historico_3sigma(
    engine_monthly: pa.Table,
    ventana_meses: int = 12,
    umbral_sigma: float = 3.0,
    hitos_verificados: Optional[set[str]] = None,
    bloquear_solo_caidas: bool = False,
) -> None:
    """Verificar que los conteos mensuales totales no caigan a cero ni violen 3 desviaciones estandar."""
    filas = engine_monthly.to_pylist()
    conteos_por_mes: dict[str, int] = defaultdict(int)
    for fila in filas:
        ym = str(fila.get("year_month", ""))
        conteos_por_mes[ym] += int(fila.get("releases_count", 0))

    verificados = hitos_verificados or set()
    meses_ordenados = sorted(conteos_por_mes.keys())
    for i in range(ventana_meses, len(meses_ordenados)):
        mes_actual = meses_ordenados[i]
        if mes_actual in verificados:
            continue

        conteo_actual = conteos_por_mes[mes_actual]

        if conteo_actual <= 0:
            raise ContratoRangoHistoricoError(
                f"Conteo mensual nulo o negativo en {mes_actual}: {conteo_actual}."
            )

        ventana = [conteos_por_mes[meses_ordenados[j]] for j in range(i - ventana_meses, i)]
        media = sum(ventana) / len(ventana)
        varianza = sum((x - media) ** 2 for x in ventana) / len(ventana)
        sigma = math.sqrt(varianza)

        if bloquear_solo_caidas and conteo_actual >= media:
            continue

        sigma_efectiva = max(sigma, 1.0)
        desviacion = abs(conteo_actual - media) / sigma_efectiva
        if desviacion > umbral_sigma:
            raise ContratoRangoHistoricoError(
                f"Conteo mensual {conteo_actual} en {mes_actual} viola la banda 3-sigma "
                f"(media={media:.1f}, sigma={sigma:.1f}, desviacion={desviacion:.2f}sigma)."
            )
