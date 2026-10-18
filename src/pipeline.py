#modulo orquestador integral del pipeline de la muestra de control
#flujo: extraccion a bronce -> transformacion a plata -> contratos bloqueantes de calidad
#uso: python -m src.pipeline [--fecha AAAA-MM-DD] [--ruta-base DIR] [--manifiesto YAML] [--omitir-extraccion]
import argparse
import sys
from pathlib import Path
from typing import Any, Optional

# pyrefly: ignore [missing-import]
import pyarrow as pa

from src.extract.client import SteamClient
from src.extract.pipeline import (
    descubrir_catalogo_steam,
    ejecutar_extraccion_muestra,
    ejecutar_ingesta_masiva,
)
from src.quality.contratos import CARDINALIDAD_MUESTRA, ContratoCalidadError, validar_contratos_plata
from src.transform.oro import ejecutar_transformacion_oro
from src.transform.plata import ejecutar_transformacion_plata
from src.version import PIPELINE_VERSION

#rutas canonicas por defecto del repositorio
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUTA_MANIFIESTO_DEFAULT = PROJECT_ROOT / "config" / "muestra_control.yaml"
RUTA_DATA_DEFAULT = PROJECT_ROOT / "data"


def ejecutar_pipeline(
    ruta_manifiesto: Optional[Path] = None,
    ruta_base: Optional[Path] = None,
    ruta_checkpoint: Optional[Path] = None,
    client: Optional[Any] = None,
    fecha: Optional[str] = None,
    cardinalidad_esperada: int = CARDINALIDAD_MUESTRA,
    omitir_extraccion: bool = False,
    generar_oro: bool = False,
    modo: str = "control",
    max_juegos: Optional[int] = None,
    descubrir: bool = False,
    mostrar_progreso: bool = True,
) -> dict[str, Any]:
    """Ejecutar el pipeline completo de forma reproducible.
    Entradas:
    - ruta_manifiesto: manifiesto de la muestra de control (opcional).
    - ruta_base: directorio de datos donde viven bronce, plata y checkpoint (opcional, por defecto data/).
    - ruta_checkpoint: archivo de checkpoint (opcional, por defecto <ruta_base>/checkpoint.json).
    - client: cliente steam inyectable; si es None la extraccion construye uno real.
    - fecha: particion AAAA-MM-DD; si es None se extrae en la fecha utc actual y plata usa la
      particion mas reciente disponible por juego.
    - cardinalidad_esperada: numero exacto de juegos exigido por el contrato de cardinalidad (modo control).
    - omitir_extraccion: reprocesar unicamente el bronce existente sin contactar a Steam.
    - generar_oro: generar star schema y data mart analitico en capa oro.
    - modo: 'control' para la muestra de prueba o 'masivo' para el catalogo completo.
    - max_juegos: limite de titulos a descubrir o extraer en modo masivo.
    - descubrir: activar descubrimiento por lotes via IStoreService en modo masivo.
    Salida:
    - diccionario con estado, metricas de extraccion y resultado de plata y oro.
    Excepciones:
    - ContratoCalidadError: si plata u oro violan algun contrato bloqueante.
    """
    base = Path(ruta_base) if ruta_base is not None else RUTA_DATA_DEFAULT
    manifiesto = Path(ruta_manifiesto) if ruta_manifiesto is not None else RUTA_MANIFIESTO_DEFAULT
    checkpoint = Path(ruta_checkpoint) if ruta_checkpoint is not None else base / "checkpoint.json"

    #1. extraccion idempotente hacia bronce
    metricas_extraccion: Optional[dict[str, Any]] = None
    if not omitir_extraccion:
        if modo == "masivo":
            appids_descubiertos: list[int] = []
            if descubrir:
                cliente_steam = client or SteamClient()
                appids_descubiertos = descubrir_catalogo_steam(
                    client=cliente_steam,
                    max_juegos=max_juegos,
                    fecha=fecha,
                    ruta_base=base,
                )
            metricas_extraccion = ejecutar_ingesta_masiva(
                appids=appids_descubiertos,
                client=client,
                checkpoint=None,
                fecha=fecha,
                ruta_base=base,
                mostrar_progreso=mostrar_progreso,
            )
        else:
            metricas_extraccion = ejecutar_extraccion_muestra(
                ruta_manifiesto=manifiesto,
                ruta_base=base,
                ruta_checkpoint=checkpoint,
                client=client,
                fecha=fecha,
            )

    #2 y 3. transformacion a plata con contratos evaluados en memoria antes de persistir
    def validador(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
        cardinalidad = dim_game.num_rows if modo == "masivo" else cardinalidad_esperada
        validar_contratos_plata(
            dim_game, game_review_summary, cardinalidad_esperada=cardinalidad, modo=modo
        )

    resultado_plata = ejecutar_transformacion_plata(
        ruta_base=base,
        ruta_manifiesto=manifiesto,
        fecha=fecha,
        validador=validador,
        modo=modo,
    )

    #4. opcional: generacion de data mart analitico en capa oro (parquet y sqlite)
    resultado_oro: Optional[dict[str, int]] = None
    if generar_oro:
        resultado_oro = ejecutar_transformacion_oro(
            ruta_plata=base / "plata",
            ruta_oro=base / "oro",
            generar_sqlite=True,
        )

    return {
        "estado": "ok",
        "pipeline_version": PIPELINE_VERSION,
        "extraccion": metricas_extraccion,
        "plata": resultado_plata,
        "oro": resultado_oro,
    }


def _construir_parser() -> argparse.ArgumentParser:
    """Definir los argumentos de linea de comandos del orquestador."""
    parser = argparse.ArgumentParser(
        prog="python -m src.pipeline",
        description="Ejecuta extraccion, transformacion a plata y contratos de calidad del censo indie.",
    )
    parser.add_argument("--fecha", default=None, help="Particion AAAA-MM-DD (por defecto fecha utc actual).")
    parser.add_argument("--ruta-base", type=Path, default=None, help="Directorio de datos (por defecto data/).")
    parser.add_argument("--manifiesto", type=Path, default=None, help="Ruta al manifiesto yaml de la muestra.")
    parser.add_argument(
        "--omitir-extraccion", action="store_true", help="Reprocesar el bronce existente sin contactar a Steam.",
    )
    parser.add_argument(
        "--generar-oro", action="store_true", help="Generar star schema y data mart analitico en capa oro.",
    )
    parser.add_argument(
        "--modo", choices=["control", "masivo"], default="control",
        help="Modo de ejecucion: control (muestra fija) o masivo (catalogo masivo de Steam).",
    )
    parser.add_argument(
        "--descubrir", action="store_true",
        help="Ejecutar descubrimiento de catalogo mediante Steam Web API en modo masivo.",
    )
    parser.add_argument(
        "--max-juegos", type=int, default=None,
        help="Limite maximo de juegos a descubrir/extraer en modo masivo.",
    )
    parser.add_argument(
        "--sin-progreso", action="store_true",
        help="Desactivar barra de progreso visual en consola.",
    )
    return parser


def main(argv: Optional[list[str]] = None, client: Optional[Any] = None) -> int:
    """Punto de entrada cli: retorna 0 si el pipeline termina y 1 si un contrato lo bloquea."""
    args = _construir_parser().parse_args(argv)
    base = args.ruta_base or RUTA_DATA_DEFAULT
    try:
        resultado = ejecutar_pipeline(
            ruta_manifiesto=args.manifiesto,
            ruta_base=args.ruta_base,
            client=client,
            fecha=args.fecha,
            omitir_extraccion=args.omitir_extraccion,
            generar_oro=args.generar_oro,
            modo=args.modo,
            max_juegos=args.max_juegos,
            descubrir=args.descubrir,
            mostrar_progreso=not args.sin_progreso,
        )
    except ContratoCalidadError as exc:
        print(f"Pipeline bloqueado por contrato de calidad: {exc}", file=sys.stderr)
        return 1

    extraccion = resultado["extraccion"]
    plata = resultado["plata"]
    oro = resultado.get("oro")
    print(f"Pipeline completado (version {resultado['pipeline_version']})")
    if extraccion is None:
        print("Extraccion: omitida")
    else:
        total = extraccion.get("total_juegos", extraccion.get("total_solicitados", 0))
        print(
            f"Extraccion: {extraccion['procesados_exito']}/{total} juegos, "
            f"{extraccion['fallidos']} fallidos"
        )
    print(f"Plata dim_game: {plata['filas_dim_game']} filas -> {plata['dim_game']}")
    print(
        f"Plata game_review_summary: {plata['filas_game_review_summary']} filas -> "
        f"{plata['game_review_summary']}"
    )
    if oro is not None:
        print(f"Oro fact_game_performance: {oro['fact_game_performance']} filas -> {base / 'oro' / 'mart'}")
        print(f"Oro sqlite mart: {base / 'oro' / 'indie_census_mart.db'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
