#modelo cuantitativo de estimacion comercial boxleiter adaptado a cohortes temporales de steam
from dataclasses import dataclass
from typing import Optional

#factor de retencion neta de desarrollador tras el corte del 30% de valve y ~12% de impuestos/devoluciones
FACTOR_NETO_DESARROLLADOR = 0.58


@dataclass(frozen=True)
class EstimacionVentasBoxleiter:
    """Contenedor inmutable de metricas comerciales estimadas bajo metodologia Boxleiter."""

    total_reviews: int
    est_copies_min: int
    est_copies_mid: int
    est_copies_max: int
    est_gross_revenue_usd: float
    est_net_revenue_usd: float
    multiplicador_usado: float
    metodo: str


def calcular_metricas_boxleiter(
    total_reviews: int,
    price_usd: float,
    release_year: Optional[int] = None,
    is_free: bool = False,
) -> EstimacionVentasBoxleiter:
    """Calcular intervalos de copias vendidas y recaudacion bruta/neta en USD.

    Entradas:
    - total_reviews: conteo consolidado de resenas positivas y negativas.
    - price_usd: precio base de lanzamiento en dolares estadounidenses.
    - release_year: anio de lanzamiento para calibrar la cohorte temporal.
    - is_free: bandera que indica si el titulo es de acceso gratuito.

    Retorna:
    - Instancia de EstimacionVentasBoxleiter con los valores calculados.
    """
    reviews_validas = max(int(total_reviews), 0)

    #calibracion de multiplicadores segun saturacion de cohorte temporal
    if release_year is not None and release_year < 2020:
        mult_min = 35.0
        mult_mid = 50.0
        mult_max = 75.0
    elif release_year is not None and 2020 <= release_year <= 2023:
        mult_min = 25.0
        mult_mid = 35.0
        mult_max = 55.0
    else:
        #mercado moderno hiper-saturado (2024 en adelante o no especificado)
        mult_min = 20.0
        mult_mid = 30.0
        mult_max = 45.0

    copies_min = int(round(reviews_validas * mult_min))
    copies_mid = int(round(reviews_validas * mult_mid))
    copies_max = int(round(reviews_validas * mult_max))

    #en juegos gratuitos o sin precio, la recaudacion financiera es cero
    if is_free or price_usd <= 0.0 or reviews_validas == 0:
        gross_rev = 0.0
        net_rev = 0.0
    else:
        gross_rev = round(copies_mid * float(price_usd), 2)
        net_rev = round(gross_rev * FACTOR_NETO_DESARROLLADOR, 2)

    return EstimacionVentasBoxleiter(
        total_reviews=reviews_validas,
        est_copies_min=copies_min,
        est_copies_mid=copies_mid,
        est_copies_max=copies_max,
        est_gross_revenue_usd=gross_rev,
        est_net_revenue_usd=net_rev,
        multiplicador_usado=mult_mid,
        metodo="boxleiter_v2_calibrado",
    )
