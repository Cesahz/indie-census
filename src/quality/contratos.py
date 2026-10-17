#modulo de contratos bloqueantes de calidad para la capa plata
#regla: cada contrato lanza ContratoCalidadError tipada; ninguna violacion se tolera en silencio
from datetime import date
from typing import Any, Callable

# pyrefly: ignore [missing-import]
import pyarrow as pa

#parametros canonicos de la muestra de control
CARDINALIDAD_MUESTRA = 100
FECHA_MINIMA = date(2024, 1, 1)
FECHA_MAXIMA = date(2026, 12, 31)
GRUPOS_VALIDOS = {"godot", "general"}
NIVELES_EVIDENCIA_GODOT = {1, 2}
MOTORES_VALIDOS = {"godot", "unity", "unreal", "gamemaker", "custom", "other", "unknown"}
NIVELES_DIVULGACION_IA = {"declared", "tagged", "self_reported", "unknown"}

#campos que nunca pueden contener nulos (precio y evidencia son condicionales)
OBLIGATORIOS_DIM_GAME = (
    "game_id", "title", "release_date", "is_free", "genres", "language_count", "developers",
    "publishers", "group", "engine", "indie_score", "is_indie", "ai_disclosure_level",
    "source", "extracted_at", "pipeline_version",
)
OBLIGATORIOS_GAME_REVIEW_SUMMARY = (
    "game_id", "total_positive", "total_negative", "total_reviews", "extracted_at", "pipeline_version",
)

#maximo de identificadores listados en un mensaje de error
_MAX_IDS_MENSAJE = 10


class ContratoCalidadError(Exception):
    """Error bloqueante: la capa plata viola un contrato de calidad de datos."""

    def __init__(self, contrato: str, detalle: str) -> None:
        self.contrato = contrato
        self.detalle = detalle
        super().__init__(f"Contrato '{contrato}' violado: {detalle}")


def _resumir_ids(ids: list[Any]) -> str:
    """Formatear una lista acotada de identificadores para mensajes de error."""
    ordenados = sorted(ids)
    texto = ", ".join(str(i) for i in ordenados[:_MAX_IDS_MENSAJE])
    if len(ordenados) > _MAX_IDS_MENSAJE:
        texto += f" (+{len(ordenados) - _MAX_IDS_MENSAJE} mas)"
    return texto


def validar_no_nulos(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 1: ningun campo obligatorio contiene valores nulos."""
    for nombre_tabla, tabla, campos in (
        ("dim_game", dim_game, OBLIGATORIOS_DIM_GAME),
        ("game_review_summary", game_review_summary, OBLIGATORIOS_GAME_REVIEW_SUMMARY),
    ):
        for campo in campos:
            nulos = tabla.column(campo).null_count
            if nulos:
                raise ContratoCalidadError(
                    "nulos", f"{nombre_tabla}.{campo} contiene {nulos} valores nulos"
                )


def validar_unicidad(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 2: game_id es estrictamente unico en ambas tablas."""
    for nombre_tabla, tabla in (("dim_game", dim_game), ("game_review_summary", game_review_summary)):
        vistos: set[int] = set()
        duplicados: set[int] = set()
        for game_id in tabla.column("game_id").to_pylist():
            if game_id in vistos:
                duplicados.add(game_id)
            vistos.add(game_id)
        if duplicados:
            raise ContratoCalidadError(
                "duplicidad", f"{nombre_tabla} contiene game_id duplicados: {_resumir_ids(list(duplicados))}"
            )


def validar_cardinalidad(
    dim_game: pa.Table,
    game_review_summary: pa.Table,
    esperado: int = CARDINALIDAD_MUESTRA,
) -> None:
    """Contrato 3: ambas tablas contienen exactamente los juegos de la muestra de control."""
    for nombre_tabla, tabla in (("dim_game", dim_game), ("game_review_summary", game_review_summary)):
        if tabla.num_rows != esperado:
            raise ContratoCalidadError(
                "cardinalidad", f"{nombre_tabla} contiene {tabla.num_rows} filas, se esperaban {esperado}"
            )


def validar_integridad_referencial(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 4: relacion 1:1 de game_id entre game_review_summary y dim_game."""
    ids_dim = set(dim_game.column("game_id").to_pylist())
    ids_resenas = set(game_review_summary.column("game_id").to_pylist())
    huerfanos = ids_resenas - ids_dim
    if huerfanos:
        raise ContratoCalidadError(
            "integridad_referencial",
            f"game_review_summary referencia game_id inexistentes en dim_game: {_resumir_ids(list(huerfanos))}",
        )
    sin_resena = ids_dim - ids_resenas
    if sin_resena:
        raise ContratoCalidadError(
            "integridad_referencial",
            f"dim_game contiene game_id sin resumen de resenas: {_resumir_ids(list(sin_resena))}",
        )


def validar_ventana_temporal(
    dim_game: pa.Table,
    game_review_summary: pa.Table,
    desde: date = FECHA_MINIMA,
    hasta: date = FECHA_MAXIMA,
) -> None:
    """Contrato 5: release_date es iso AAAA-MM-DD y cae dentro de la ventana de lanzamiento."""
    invalidos: list[int] = []
    for fila in dim_game.select(["game_id", "release_date"]).to_pylist():
        try:
            fecha = date.fromisoformat(fila["release_date"])
            valido = len(fila["release_date"]) == 10 and desde <= fecha <= hasta
        except (TypeError, ValueError):
            valido = False
        if not valido:
            invalidos.append(fila["game_id"])
    if invalidos:
        raise ContratoCalidadError(
            "ventana_temporal",
            f"release_date fuera de {desde.isoformat()}..{hasta.isoformat()} o invalida en game_id: "
            f"{_resumir_ids(invalidos)}",
        )


def validar_coherencia_aritmetica(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 6: total_reviews == total_positive + total_negative y conteos no negativos."""
    incoherentes: list[int] = []
    for fila in game_review_summary.to_pylist():
        positivas, negativas, total = fila["total_positive"], fila["total_negative"], fila["total_reviews"]
        if positivas < 0 or negativas < 0 or total != positivas + negativas:
            incoherentes.append(fila["game_id"])
    if incoherentes:
        raise ContratoCalidadError(
            "coherencia_aritmetica",
            f"total_reviews != total_positive + total_negative o conteo negativo en game_id: "
            f"{_resumir_ids(incoherentes)}",
        )
    idiomas_negativos = [
        f["game_id"] for f in dim_game.select(["game_id", "language_count"]).to_pylist()
        if f["language_count"] < 0
    ]
    if idiomas_negativos:
        raise ContratoCalidadError(
            "coherencia_aritmetica", f"language_count negativo en game_id: {_resumir_ids(idiomas_negativos)}"
        )


def validar_coherencia_precio(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 7: juegos de pago con precio positivo; juegos gratuitos con precio nulo o 0."""
    incoherentes: list[int] = []
    for fila in dim_game.select(["game_id", "is_free", "price_launch_usd_cents"]).to_pylist():
        precio = fila["price_launch_usd_cents"]
        if fila["is_free"]:
            valido = precio is None or precio == 0
        else:
            valido = precio is not None and precio > 0
        if not valido:
            incoherentes.append(fila["game_id"])
    if incoherentes:
        raise ContratoCalidadError(
            "coherencia_precio", f"precio incoherente con is_free en game_id: {_resumir_ids(incoherentes)}"
        )


def validar_evidencia_motor(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 8: grupo valido y juegos godot con engine_evidence_level en {1, 2}."""
    for fila in dim_game.select(["game_id", "group", "engine_evidence_level"]).to_pylist():
        if fila["group"] not in GRUPOS_VALIDOS:
            raise ContratoCalidadError(
                "evidencia_motor", f"Grupo desconocido '{fila['group']}' en game_id {fila['game_id']}"
            )
    sin_evidencia = [
        f["game_id"] for f in dim_game.select(["game_id", "group", "engine_evidence_level"]).to_pylist()
        if f["group"] == "godot" and f["engine_evidence_level"] not in NIVELES_EVIDENCIA_GODOT
    ]
    if sin_evidencia:
        raise ContratoCalidadError(
            "evidencia_motor",
            f"Juegos godot sin engine_evidence_level en {{1, 2}}: {_resumir_ids(sin_evidencia)}",
        )


def validar_clasificacion_semantica(dim_game: pa.Table, game_review_summary: pa.Table) -> None:
    """Contrato 9: validar dominios y consistencia de las columnas semanticas."""
    filas = dim_game.select([
        "game_id", "group", "engine", "engine_evidence_level", "indie_score", "is_indie", "ai_disclosure_level"
    ]).to_pylist()

    motores_invalidos = [(f["game_id"], f["engine"]) for f in filas if f["engine"] not in MOTORES_VALIDOS]
    if motores_invalidos:
        ids = [m[0] for m in motores_invalidos]
        detalles_motores = ", ".join(f"{m[1]} (id {m[0]})" for m in motores_invalidos[:5])
        raise ContratoCalidadError(
            "clasificacion_semantica",
            f"Valor de engine desconocido o invalido [{detalles_motores}] en game_id: {_resumir_ids(ids)}",
        )

    indie_score_invalidos = [
        f["game_id"] for f in filas
        if f["indie_score"] is None or not isinstance(f["indie_score"], (int, float)) or not (0.0 <= f["indie_score"] <= 1.0)
    ]
    if indie_score_invalidos:
        raise ContratoCalidadError(
            "clasificacion_semantica",
            f"Valor de indie_score fuera del rango [0.0, 1.0] o nulo en game_id: {_resumir_ids(indie_score_invalidos)}",
        )

    is_indie_invalidos = [f["game_id"] for f in filas if not isinstance(f["is_indie"], bool)]
    if is_indie_invalidos:
        raise ContratoCalidadError(
            "clasificacion_semantica",
            f"Valor de is_indie no booleano o nulo en game_id: {_resumir_ids(is_indie_invalidos)}",
        )

    ai_invalidos = [f["game_id"] for f in filas if f["ai_disclosure_level"] not in NIVELES_DIVULGACION_IA]
    if ai_invalidos:
        raise ContratoCalidadError(
            "clasificacion_semantica",
            f"Nivel de ai_disclosure_level invalido en game_id: {_resumir_ids(ai_invalidos)}",
        )

    #consistencia: si el grupo es godot, el motor debe ser godot
    godot_inconsistentes = [
        f["game_id"] for f in filas if f["group"] == "godot" and f["engine"] != "godot"
    ]
    if godot_inconsistentes:
        raise ContratoCalidadError(
            "clasificacion_semantica",
            f"Juego con group='godot' pero engine != 'godot' en game_id: {_resumir_ids(godot_inconsistentes)}",
        )


def validar_contratos_plata(
    dim_game: pa.Table,
    game_review_summary: pa.Table,
    cardinalidad_esperada: int = CARDINALIDAD_MUESTRA,
) -> None:
    """Ejecutar la matriz completa de contratos en orden y bloquear ante la primera violacion."""
    contratos: list[Callable[[pa.Table, pa.Table], None]] = [
        validar_no_nulos,
        validar_unicidad,
        lambda d, r: validar_cardinalidad(d, r, esperado=cardinalidad_esperada),
        validar_integridad_referencial,
        validar_ventana_temporal,
        validar_coherencia_aritmetica,
        validar_coherencia_precio,
        validar_evidencia_motor,
        validar_clasificacion_semantica,
    ]
    for contrato in contratos:
        contrato(dim_game, game_review_summary)

