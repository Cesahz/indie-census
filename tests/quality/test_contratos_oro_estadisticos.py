#suite de pruebas para contratos estadisticos de calidad en capa oro
import pyarrow as pa
import pytest

from src.quality.contratos_oro import (
    ContratoContinuidadTemporalError,
    ContratoRangoHistoricoError,
    validar_continuidad_temporal_oro,
    validar_rango_historico_3sigma,
)


def _crear_tabla_mensual(meses_con_conteos: list[tuple[str, int]]) -> pa.Table:
    """Helper para crear tabla Arrow con esquema de engine_monthly."""
    filas = []
    for ym, conteo in meses_con_conteos:
        filas.append({
            "year_month": ym,
            "is_indie": True,
            "engine": "godot",
            "releases_count": conteo,
            "monthly_share_pct": 100.0,
            "median_reviews": 10.0,
            "total_net_revenue_usd": 1000.0,
            "pipeline_version": "0.3.6",
        })
    schema = pa.schema([
        pa.field("year_month", pa.string()),
        pa.field("is_indie", pa.bool_()),
        pa.field("engine", pa.string()),
        pa.field("releases_count", pa.int64()),
        pa.field("monthly_share_pct", pa.float64()),
        pa.field("median_reviews", pa.float64()),
        pa.field("total_net_revenue_usd", pa.float64()),
        pa.field("pipeline_version", pa.string()),
    ])
    return pa.Table.from_pylist(filas, schema=schema)


def test_validar_continuidad_temporal_exitoso() -> None:
    """Verificar que una serie sin meses faltantes entre 2024-01 y 2026-10 sea validada."""
    meses = []
    for anio in (2024, 2025):
        for mes in range(1, 13):
            meses.append((f"{anio}-{mes:02d}", 50))
    for mes in range(1, 11):
        meses.append((f"2026-{mes:02d}", 50))

    tabla = _crear_tabla_mensual(meses)
    #no debe levantar excepcion
    validar_continuidad_temporal_oro(tabla, mes_inicio="2024-01", mes_corte="2026-10")


def test_validar_continuidad_temporal_falla_si_falta_mes() -> None:
    """Verificar que la ausencia de un mes calendario levante ContratoContinuidadTemporalError."""
    meses = [
        ("2024-01", 10),
        ("2024-02", 15),
        #falta 2024-03
        ("2024-04", 20),
    ]
    tabla = _crear_tabla_mensual(meses)
    with pytest.raises(ContratoContinuidadTemporalError, match="Mes vacio o ausente"):
        validar_continuidad_temporal_oro(tabla, mes_inicio="2024-01", mes_corte="2024-04")


def test_validar_rango_historico_3sigma_exitoso() -> None:
    """Verificar que conteos estables dentro de la banda 3-sigma pasen la validacion."""
    meses = []
    for anio in (2024, 2025):
        for mes in range(1, 13):
            meses.append((f"{anio}-{mes:02d}", 1000 + (mes % 5) * 10))

    tabla = _crear_tabla_mensual(meses)
    validar_rango_historico_3sigma(tabla, ventana_meses=12, umbral_sigma=3.0)


def test_validar_rango_historico_3sigma_falla_ante_caida_espuria() -> None:
    """Verificar que una caida anomala a 2 lanzamientos tras 12 meses estables levante ContratoRangoHistoricoError."""
    meses = []
    #12 meses estables con 1000 lanzamientos
    for mes in range(1, 13):
        meses.append((f"2024-{mes:02d}", 1000))
    #mes 13 con anomalia de truncamiento (2 lanzamientos)
    meses.append(("2025-01", 2))

    tabla = _crear_tabla_mensual(meses)
    with pytest.raises(ContratoRangoHistoricoError, match="viola la banda 3-sigma"):
        validar_rango_historico_3sigma(tabla, ventana_meses=12, umbral_sigma=3.0)
