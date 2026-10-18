#modulo de transformacion determinista de bronce a capa plata
#regla: esquemas arrow explicitos, salida ordenada por game_id, persistencia atomica en parquet
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from src.classify.ai import clasificar_divulgacion_ia
from src.classify.engine import clasificar_motor
from src.classify.indie import calcular_indie_score
from src.version import PIPELINE_VERSION

#rutas canonicas por defecto del repositorio
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUTA_DATA_DEFAULT = PROJECT_ROOT / "data"
RUTA_MANIFIESTO_DEFAULT = PROJECT_ROOT / "config" / "muestra_control.yaml"

#nombres de archivo de la capa plata
ARCHIVO_DIM_GAME = "dim_game.parquet"
ARCHIVO_GAME_REVIEW_SUMMARY = "game_review_summary.parquet"

#esquema explicito de la dimension de juegos
ESQUEMA_DIM_GAME = pa.schema([
    pa.field("game_id", pa.int64(), nullable=False),
    pa.field("title", pa.string()),
    pa.field("release_date", pa.string()),
    pa.field("is_free", pa.bool_()),
    pa.field("price_launch_usd_cents", pa.int64()),
    pa.field("genres", pa.list_(pa.string())),
    pa.field("language_count", pa.int32()),
    pa.field("developers", pa.list_(pa.string())),
    pa.field("publishers", pa.list_(pa.string())),
    pa.field("group", pa.string()),
    pa.field("engine", pa.string()),
    pa.field("engine_evidence_level", pa.int8()),
    pa.field("indie_score", pa.float64()),
    pa.field("is_indie", pa.bool_()),
    pa.field("ai_disclosure_level", pa.string()),
    pa.field("source", pa.string()),
    pa.field("extracted_at", pa.string()),
    pa.field("pipeline_version", pa.string()),
])

#esquema explicito del resumen cuantitativo de resenas
ESQUEMA_GAME_REVIEW_SUMMARY = pa.schema([
    pa.field("game_id", pa.int64(), nullable=False),
    pa.field("total_positive", pa.int64()),
    pa.field("total_negative", pa.int64()),
    pa.field("total_reviews", pa.int64()),
    pa.field("extracted_at", pa.string()),
    pa.field("pipeline_version", pa.string()),
])

#mapa de meses en ingles independiente del locale del sistema
_MESES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RE_DIA_MES = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})$")
_RE_MES_DIA = re.compile(r"^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$")
_RE_ETIQUETA_HTML = re.compile(r"<[^>]+>")


def _construir_fecha_iso(anio: str, mes: int, dia: str) -> Optional[str]:
    """Validar componentes de calendario y retornar fecha iso o None si es imposible."""
    try:
        return date(int(anio), mes, int(dia)).isoformat()
    except ValueError:
        return None


def parsear_fecha_steam(texto: Optional[str]) -> Optional[str]:
    """Normalizar una fecha de lanzamiento de Steam a formato iso AAAA-MM-DD.
    Formatos admitidos: '29 May, 2024', 'May 29, 2024', '29 May 2024', nombres completos,
    abreviatura 'Sept' e iso 'AAAA-MM-DD'.
    Salida:
    - cadena iso o None si el texto es vacio, ambiguo ('Coming soon') o invalido.
    """
    if not texto:
        return None
    limpio = texto.strip()

    coincidencia = _RE_ISO.match(limpio)
    if coincidencia:
        anio, mes, dia = coincidencia.groups()
        return _construir_fecha_iso(anio, int(mes), dia)

    coincidencia = _RE_DIA_MES.match(limpio)
    if coincidencia:
        dia, nombre_mes, anio = coincidencia.groups()
    else:
        coincidencia = _RE_MES_DIA.match(limpio)
        if not coincidencia:
            return None
        nombre_mes, dia, anio = coincidencia.groups()

    mes = _MESES.get(nombre_mes.lower())
    if mes is None:
        return None
    return _construir_fecha_iso(anio, mes, dia)


def contar_idiomas(texto: Optional[str]) -> int:
    """Contar idiomas declarados en el campo html supported_languages de Steam.
    Se descarta la nota al pie posterior a '<br>' y las marcas de audio '*'.
    """
    if not texto:
        return 0
    principal = re.split(r"<br\s*/?>", texto, maxsplit=1, flags=re.IGNORECASE)[0]
    principal = _RE_ETIQUETA_HTML.sub("", principal).replace("*", "")
    return len([idioma for idioma in principal.split(",") if idioma.strip()])


def _lista_cadenas(valor: Any) -> list[str]:
    """Normalizar una lista de cadenas tolerando ausencia o nulos."""
    if not isinstance(valor, list):
        return []
    return [str(v) for v in valor if v is not None]


def parsear_appdetails(envoltorio: dict[str, Any], appid: int) -> dict[str, Any]:
    """Extraer los campos tecnicos de dim_game desde un envoltorio de bronce appdetails.
    Excepciones:
    - ValueError: si el payload no contiene el appid o la respuesta de Steam fue fallida.
    """
    payload = envoltorio.get("payload", {})
    nodo = payload.get(str(appid)) if isinstance(payload, dict) else None
    if not isinstance(nodo, dict) or not nodo.get("success") or not isinstance(nodo.get("data"), dict):
        raise ValueError(f"Respuesta appdetails fallida o ausente para appid {appid}")
    data = nodo["data"]
    meta = envoltorio.get("meta", {})

    es_gratis = bool(data.get("is_free", False))
    precio: Optional[int] = None
    overview = data.get("price_overview")
    #el precio de lanzamiento es el inicial sin descuento y solo se acepta en usd
    if not es_gratis and isinstance(overview, dict) and overview.get("currency") == "USD":
        inicial = overview.get("initial")
        if inicial is not None:
            precio = int(inicial)

    generos = data.get("genres")
    descripciones = [g.get("description") for g in generos if isinstance(g, dict)] if isinstance(generos, list) else []
    desc_html = (
        data.get("detailed_description")
        or data.get("about_the_game")
        or data.get("short_description")
        or ""
    )
    desc_texto = _RE_ETIQUETA_HTML.sub(" ", str(desc_html)).strip()
    descriptors_dict = data.get("content_descriptors") or {}
    descriptors_notes = descriptors_dict.get("notes")
    descriptors_list = [str(descriptors_notes)] if descriptors_notes else []

    return {
        "game_id": int(appid),
        "title": data.get("name"),
        "release_date": parsear_fecha_steam((data.get("release_date") or {}).get("date")),
        "is_free": es_gratis,
        "price_launch_usd_cents": precio,
        "genres": _lista_cadenas(descripciones),
        "language_count": contar_idiomas(data.get("supported_languages")),
        "developers": _lista_cadenas(data.get("developers")),
        "publishers": _lista_cadenas(data.get("publishers")),
        "source": meta.get("fuente"),
        "extracted_at": meta.get("extraido_en"),
        "_desc_texto": desc_texto,
        "_descriptors_steam": descriptors_list,
    }


def parsear_appreviews(envoltorio: dict[str, Any], appid: int) -> dict[str, Any]:
    """Extraer los conteos de game_review_summary desde un envoltorio de bronce appreviews.
    Un juego sin resenas se representa con conteos en cero.
    Excepciones:
    - ValueError: si la respuesta de Steam no fue exitosa.
    """
    payload = envoltorio.get("payload", {})
    if not isinstance(payload, dict) or payload.get("success") != 1:
        raise ValueError(f"Respuesta appreviews fallida para appid {appid}")
    resumen = payload.get("query_summary") or {}
    positivas = int(resumen.get("total_positive", 0))
    negativas = int(resumen.get("total_negative", 0))
    #se conserva el total declarado por steam para que el contrato aritmetico lo audite
    total = int(resumen.get("total_reviews", positivas + negativas))
    return {
        "game_id": int(appid),
        "total_positive": positivas,
        "total_negative": negativas,
        "total_reviews": total,
        "extracted_at": envoltorio.get("meta", {}).get("extraido_en"),
    }


def leer_particion_bronce(
    ruta_base: Path,
    recurso: str,
    fecha: Optional[str] = None,
) -> dict[int, dict[str, Any]]:
    """Leer los envoltorios de bronce de un recurso indexados por appid.
    Si no se especifica fecha, la particion mas reciente prevalece por appid.
    """
    directorio = Path(ruta_base) / "bronce" / "steam" / recurso
    if not directorio.is_dir():
        return {}
    if fecha is not None:
        particiones = [directorio / f"fecha={fecha}"]
    else:
        particiones = sorted(p for p in directorio.glob("fecha=*") if p.is_dir())

    envoltorios: dict[int, dict[str, Any]] = {}
    for particion in particiones:
        for archivo in sorted(particion.glob("appid=*.json")):
            appid = int(archivo.stem.split("=", 1)[1])
            envoltorios[appid] = json.loads(archivo.read_text(encoding="utf-8"))
    return envoltorios


def _cargar_manifiesto(ruta_manifiesto: Path) -> list[dict[str, Any]]:
    """Leer la lista de juegos del manifiesto de muestra de control."""
    with open(ruta_manifiesto, "r", encoding="utf-8") as f:
        contenido = yaml.safe_load(f)
    return contenido.get("juegos", []) if isinstance(contenido, dict) else []


def construir_tablas_plata(
    ruta_base: Optional[Path] = None,
    ruta_manifiesto: Optional[Path] = None,
    fecha: Optional[str] = None,
    version_pipeline: Optional[str] = None,
    modo: str = "control",
    appids_objetivo: Optional[list[int]] = None,
) -> tuple[pa.Table, pa.Table]:
    """Construir las tablas arrow dim_game y game_review_summary a partir de bronce.
    En modo 'control', lee la muestra definida en el manifiesto yaml.
    En modo 'masivo', procesa todos los titulos de bronce o los indicados en appids_objetivo.
    Salida:
    - tupla (dim_game, game_review_summary) ordenada por game_id y con esquemas explicitos.
    """
    base = Path(ruta_base) if ruta_base is not None else RUTA_DATA_DEFAULT
    ruta_man = Path(ruta_manifiesto) if ruta_manifiesto is not None else RUTA_MANIFIESTO_DEFAULT
    version = version_pipeline if version_pipeline is not None else PIPELINE_VERSION

    detalles = leer_particion_bronce(base, "appdetails", fecha)
    resenas = leer_particion_bronce(base, "appreviews_resumen", fecha)

    #determinar universo de items segun modo
    if modo == "masivo":
        if appids_objetivo is not None:
            candidatos = [int(a) for a in appids_objetivo if a in detalles and a in resenas]
        else:
            candidatos = [aid for aid in sorted(detalles.keys()) if aid in resenas]
        items = [{"appid": aid, "grupo": "general"} for aid in candidatos]
    else:
        items = _cargar_manifiesto(ruta_man)

    filas_dim: list[dict[str, Any]] = []
    filas_resenas: list[dict[str, Any]] = []
    for item in items:
        appid = int(item["appid"])
        if appid not in detalles or appid not in resenas:
            continue
        try:
            fila_dim = parsear_appdetails(detalles[appid], appid)
            fila_resena = parsear_appreviews(resenas[appid], appid)
        except ValueError:
            continue

        #enriquecimiento con el manifiesto curado como respaldo de titulo y fecha
        fila_dim["title"] = fila_dim["title"] or item.get("titulo")
        fila_dim["release_date"] = fila_dim["release_date"] or parsear_fecha_steam(
            str(item["release_date"]) if item.get("release_date") is not None else None
        )
        fila_dim["group"] = item.get("grupo")

        #en modo masivo se descartan productos sin fecha de lanzamiento valida o sin titulo
        if modo == "masivo" and (not fila_dim.get("release_date") or not fila_dim.get("title")):
            continue

        desc_texto = fila_dim.pop("_desc_texto", "")
        descriptors = fila_dim.pop("_descriptors_steam", [])

        res_motor = clasificar_motor(
            descripcion=desc_texto,
            tags=fila_dim["genres"],
        )

        precio_usd = (
            0.0 if fila_dim["is_free"]
            else (fila_dim["price_launch_usd_cents"] / 100.0 if fila_dim["price_launch_usd_cents"] is not None else None)
        )
        res_indie = calcular_indie_score(
            tags=fila_dim["genres"],
            generos=fila_dim["genres"],
            developers=fila_dim["developers"],
            publishers=fila_dim["publishers"],
            price_usd=precio_usd,
            language_count=fila_dim["language_count"],
        )

        res_ia = clasificar_divulgacion_ia(
            descriptors_steam=descriptors,
            tags=fila_dim["genres"],
            descripcion_o_notas=desc_texto,
        )

        es_grupo_godot = item.get("grupo") == "godot"
        if es_grupo_godot:
            fila_dim["engine"] = "godot"
            nivel = item.get("evidencia_nivel")
            fila_dim["engine_evidence_level"] = int(nivel) if nivel is not None else (res_motor.evidence_level or 1)
        else:
            fila_dim["engine"] = res_motor.engine
            fila_dim["engine_evidence_level"] = res_motor.evidence_level

        fila_dim["indie_score"] = res_indie.indie_score
        fila_dim["is_indie"] = res_indie.is_indie
        fila_dim["ai_disclosure_level"] = res_ia.disclosure_level.value
        fila_dim["pipeline_version"] = version
        fila_resena["pipeline_version"] = version

        filas_dim.append(fila_dim)
        filas_resenas.append(fila_resena)

    filas_dim.sort(key=lambda f: f["game_id"])
    filas_resenas.sort(key=lambda f: f["game_id"])
    dim_game = pa.Table.from_pylist(filas_dim, schema=ESQUEMA_DIM_GAME)
    resumen = pa.Table.from_pylist(filas_resenas, schema=ESQUEMA_GAME_REVIEW_SUMMARY)
    return dim_game, resumen


def persistir_plata(
    dim_game: pa.Table,
    game_review_summary: pa.Table,
    ruta_base: Optional[Path] = None,
) -> dict[str, Path]:
    """Persistir ambas tablas en parquet de forma atomica en data/plata/steam/.
    Ambas se escriben primero a temporales; solo si las dos escrituras terminan se reemplazan
    los destinos. Ante cualquier falla se eliminan los temporales.
    """
    base = Path(ruta_base) if ruta_base is not None else RUTA_DATA_DEFAULT
    directorio = base / "plata" / "steam"
    directorio.mkdir(parents=True, exist_ok=True)

    destinos = {
        "dim_game": (dim_game, directorio / ARCHIVO_DIM_GAME),
        "game_review_summary": (game_review_summary, directorio / ARCHIVO_GAME_REVIEW_SUMMARY),
    }
    temporales: list[tuple[Path, Path]] = []
    try:
        for tabla, destino in destinos.values():
            temporal = destino.with_suffix(".tmp")
            temporales.append((temporal, destino))
            pq.write_table(tabla, temporal)
        for temporal, destino in temporales:
            os.replace(temporal, destino)
    except Exception:
        #limpiar cualquier temporal remanente para no dejar artefactos parciales
        for temporal, _ in temporales:
            if temporal.exists():
                temporal.unlink()
        raise

    return {nombre: destino for nombre, (_, destino) in destinos.items()}


def ejecutar_transformacion_plata(
    ruta_base: Optional[Path] = None,
    ruta_manifiesto: Optional[Path] = None,
    fecha: Optional[str] = None,
    version_pipeline: Optional[str] = None,
    validador: Optional[Callable[[pa.Table, pa.Table], None]] = None,
    modo: str = "control",
    appids_objetivo: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Construir, validar opcionalmente y persistir la capa plata.
    El validador se ejecuta en memoria antes de cualquier escritura: si lanza una excepcion,
    no se crea ningun archivo en plata.
    Salida:
    - diccionario con rutas de los parquet y conteo de filas por tabla.
    """
    dim_game, resumen = construir_tablas_plata(
        ruta_base=ruta_base,
        ruta_manifiesto=ruta_manifiesto,
        fecha=fecha,
        version_pipeline=version_pipeline,
        modo=modo,
        appids_objetivo=appids_objetivo,
    )
    if validador is not None:
        validador(dim_game, resumen)
    rutas = persistir_plata(dim_game, resumen, ruta_base=ruta_base)
    return {
        **rutas,
        "filas_dim_game": dim_game.num_rows,
        "filas_game_review_summary": resumen.num_rows,
    }
