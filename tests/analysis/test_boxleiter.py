#suite de pruebas unitarias para el modelo comercial boxleiter (criterio f3-03)
#verifica calibracion por cohortes temporales, derivacion neta y contratos de consistencia
#pyrefly: ignore [missing-import]
import pyarrow as pa
import pytest

from src.analysis.boxleiter import (
    EstimacionVentasBoxleiter,
    calcular_metricas_boxleiter,
)
from src.quality.contratos import ContratoCalidadError, validar_metricas_comerciales_oro


def test_calcular_metricas_boxleiter_cohortes_temporales() -> None:
    #1. cohorte previa a 2020 (mercado clasico menos saturado)
    res_antiguo = calcular_metricas_boxleiter(
        total_reviews=100, price_usd=10.0, release_year=2018
    )
    assert isinstance(res_antiguo, EstimacionVentasBoxleiter)
    assert res_antiguo.est_copies_min == 3500  #100 * 35
    assert res_antiguo.est_copies_mid == 5000  #100 * 50
    assert res_antiguo.est_copies_max == 7500  #100 * 75
    assert res_antiguo.est_gross_revenue_usd == 50000.0
    assert res_antiguo.est_net_revenue_usd == 29000.0  #50000 * 0.58

    #2. cohorte 2020-2023 (era pandemica y transicion)
    res_medio = calcular_metricas_boxleiter(
        total_reviews=100, price_usd=10.0, release_year=2022
    )
    assert res_medio.est_copies_min == 2500  #100 * 25
    assert res_medio.est_copies_mid == 3500  #100 * 35
    assert res_medio.est_copies_max == 5500  #100 * 55

    #3. cohorte 2024-2026+ (mercado moderno hiper-saturado)
    res_moderno = calcular_metricas_boxleiter(
        total_reviews=100, price_usd=10.0, release_year=2025
    )
    assert res_moderno.est_copies_min == 2000  #100 * 20
    assert res_moderno.est_copies_mid == 3000  #100 * 30
    assert res_moderno.est_copies_max == 4500  #100 * 45
    assert res_moderno.est_gross_revenue_usd == 30000.0
    assert res_moderno.est_net_revenue_usd == 17400.0  #30000 * 0.58


def test_calcular_metricas_boxleiter_juego_gratuito() -> None:
    #en juegos gratuitos las copias se estiman pero la recaudacion es estrictamente 0.0
    res_free = calcular_metricas_boxleiter(
        total_reviews=200, price_usd=15.0, release_year=2024, is_free=True
    )
    assert res_free.est_copies_mid == 6000  #200 * 30
    assert res_free.est_gross_revenue_usd == 0.0
    assert res_free.est_net_revenue_usd == 0.0


def test_calcular_metricas_boxleiter_cero_resenas() -> None:
    #sin resenas el estimado de ventas y recaudacion es nulo
    res_cero = calcular_metricas_boxleiter(
        total_reviews=0, price_usd=20.0, release_year=2025
    )
    assert res_cero.est_copies_min == 0
    assert res_cero.est_copies_mid == 0
    assert res_cero.est_copies_max == 0
    assert res_cero.est_gross_revenue_usd == 0.0
    assert res_cero.est_net_revenue_usd == 0.0


def test_contrato_metricas_oro_valida_consistencia_correcta() -> None:
    #tabla valida no debe lanzar error en el contrato de calidad
    tabla_valida = pa.Table.from_pydict({
        "game_id": [1],
        "is_free": [False],
        "est_copies_min": [200],
        "est_copies_mid": [300],
        "est_copies_max": [450],
        "est_gross_revenue_usd": [3000.0],
        "est_net_revenue_usd": [1740.0],
    })
    #no debe lanzar excepcion
    validar_metricas_comerciales_oro(tabla_valida)


def test_contrato_metricas_oro_bloquea_rango_invertido() -> None:
    #est_copies_min superior a est_copies_mid debe ser bloqueado
    tabla_invalida = pa.Table.from_pydict({
        "game_id": [1],
        "is_free": [False],
        "est_copies_min": [500],
        "est_copies_mid": [300],  #inversion ilogica
        "est_copies_max": [450],
        "est_gross_revenue_usd": [3000.0],
        "est_net_revenue_usd": [1740.0],
    })
    with pytest.raises(ContratoCalidadError) as exc_info:
        validar_metricas_comerciales_oro(tabla_invalida)
    assert "monotonia" in str(exc_info.value).lower()


def test_contrato_metricas_oro_bloquea_ingreso_neto_mayor_a_bruto() -> None:
    #el ingreso neto nunca puede ser mayor al ingreso bruto
    tabla_invalida = pa.Table.from_pydict({
        "game_id": [1],
        "is_free": [False],
        "est_copies_min": [200],
        "est_copies_mid": [300],
        "est_copies_max": [450],
        "est_gross_revenue_usd": [1000.0],
        "est_net_revenue_usd": [1500.0],  #neto > bruto ilogico
    })
    with pytest.raises(ContratoCalidadError) as exc_info:
        validar_metricas_comerciales_oro(tabla_invalida)
    assert "ingreso neto" in str(exc_info.value).lower()
