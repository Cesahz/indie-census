#modulo de transformacion determinista de bronce a capa plata
#regla: esquemas arrow explicitos, salida ordenada por game_id, persistencia atomica en parquet
import json
import os
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from src.classify.ai import clasificar_divulgacion_ia
from src.classify.engine import clasificar_motor
from src.classify.indie import calcular_indie_score
from src.classify.taxonomy import cargar_taxonomia
from src.quality.contratos import FECHA_MAXIMA_CATALOGO, FECHA_MINIMA_CATALOGO
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

@dataclass(frozen=True)
class PerfilHardware:
    """Configuracion de ejecucion adaptada a la capacidad del procesador."""

    hilos_logicos_detectados: int
    categoria_hardware: str
    workers_asignados: int
    usar_multiproceso: bool
    batch_size: int


def detectar_perfil_hardware(
    hilos_override: Optional[int] = None,
    max_workers_techo: int = 12,
) -> PerfilHardware:
    """Calcular perfil optimo de workers y tamano de lote segun los hilos del procesador."""
    if max_workers_techo < 1:
        raise ValueError("El techo maximo de workers debe ser al menos 1.")

    hilos = hilos_override if hilos_override is not None else (os.cpu_count() or 1)
    if hilos < 1:
        hilos = 1

    #gama baja: mono-hilo o dual-core sin sobrecosto de multiproceso
    if hilos <= 2:
        return PerfilHardware(
            hilos_logicos_detectados=hilos,
            categoria_hardware="gama_baja_secuencial",
            workers_asignados=1,
            usar_multiproceso=False,
            batch_size=1500,
        )

    #gama media: 3 a 6 hilos logicos
    if hilos <= 6:
        workers = min(max(2, hilos - 1), max_workers_techo)
        return PerfilHardware(
            hilos_logicos_detectados=hilos,
            categoria_hardware="gama_media_moderada",
            workers_asignados=workers,
            usar_multiproceso=True,
            batch_size=3000,
        )

    #gama alta: 7 o mas hilos logicos (ej. ryzen 5 8600g con 12 hilos)
    workers_alta = min(max(1, hilos - 2), max_workers_techo)
    return PerfilHardware(
        hilos_logicos_detectados=hilos,
        categoria_hardware="multiproceso_alto_rendimiento",
        workers_asignados=workers_alta,
        usar_multiproceso=True,
        batch_size=5000,
    )


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
    categorias = data.get("categories")
    cat_descripciones = [c.get("description") for c in categorias if isinstance(c, dict)] if isinstance(categorias, list) else []
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
        "_categories": _lista_cadenas(cat_descripciones),
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


def indexar_rutas_bronce(
    ruta_base: Path,
    recurso: str,
    fecha: Optional[str] = None,
) -> dict[int, Path]:
    """Indexar unicamente las rutas Path del archivo mas reciente por appid sin cargar json en ram.
    Si no se especifica fecha, las particiones posteriores prevalecen ordenadas cronologicamente.
    """
    directorio = Path(ruta_base) / "bronce" / "steam" / recurso
    if not directorio.is_dir():
        return {}
    if fecha is not None:
        particiones = [directorio / f"fecha={fecha}"]
    else:
        particiones = sorted(p for p in directorio.glob("fecha=*") if p.is_dir())

    indice: dict[int, Path] = {}
    for particion in particiones:
        if not particion.is_dir():
            continue
        for archivo in sorted(particion.glob("appid=*.json")):
            try:
                appid = int(archivo.stem.split("=", 1)[1])
                indice[appid] = archivo
            except (ValueError, IndexError):
                continue
    return indice


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


_TAX_CACHE_LOCAL: Optional[Any] = None


def _obtener_taxonomia_local() -> Any:
    """Obtener o inicializar en cache la taxonomia en el proceso actual."""
    global _TAX_CACHE_LOCAL
    if _TAX_CACHE_LOCAL is None:
        _TAX_CACHE_LOCAL = cargar_taxonomia()
    return _TAX_CACHE_LOCAL


def _procesar_elemento(
    item: dict[str, Any],
    ruta_detalles: Optional[Path],
    ruta_resenas: Optional[Path],
    modo: str,
    tax_config: Any,
) -> Optional[dict[str, Any]]:
    """Procesar un juego individual desde sus rutas de bronce."""
    if ruta_detalles is None or ruta_resenas is None:
        return None

    appid = int(item["appid"])
    try:
        raw_detalles = json.loads(ruta_detalles.read_text(encoding="utf-8"))
        fila_dim = parsear_appdetails(raw_detalles, appid)
        raw_resenas = json.loads(ruta_resenas.read_text(encoding="utf-8"))
        fila_resena = parsear_appreviews(raw_resenas, appid)
    except (ValueError, OSError, json.JSONDecodeError):
        return None

    #enriquecimiento con el manifiesto curado como respaldo de titulo y fecha
    fila_dim["title"] = fila_dim["title"] or item.get("titulo")
    fila_dim["release_date"] = fila_dim["release_date"] or parsear_fecha_steam(
        str(item["release_date"]) if item.get("release_date") is not None else None
    )
    fila_dim["group"] = item.get("grupo")

    #en modo masivo se descartan productos sin fecha valida, fuera de catalogo, sin titulo o sin precio
    if modo == "masivo":
        if not fila_dim.get("release_date") or not fila_dim.get("title"):
            return None
        try:
            f_obj = date.fromisoformat(str(fila_dim["release_date"]))
            if not (FECHA_MINIMA_CATALOGO <= f_obj <= FECHA_MAXIMA_CATALOGO):
                return None
        except (ValueError, TypeError):
            return None
        if not fila_dim.get("is_free") and fila_dim.get("price_launch_usd_cents") is None:
            return None

    desc_texto = fila_dim.pop("_desc_texto", "")
    descriptors = fila_dim.pop("_descriptors_steam", [])
    categories = fila_dim.pop("_categories", [])

    etiquetas_tienda = categories + [g for g in fila_dim["genres"] if g not in categories]

    res_motor = clasificar_motor(
        descripcion=desc_texto,
        tags=etiquetas_tienda,
        taxonomia=tax_config,
    )

    precio_usd = (
        0.0 if fila_dim["is_free"]
        else (fila_dim["price_launch_usd_cents"] / 100.0 if fila_dim["price_launch_usd_cents"] is not None else None)
    )

    res_ia = clasificar_divulgacion_ia(
        descriptors_steam=descriptors,
        tags=etiquetas_tienda,
        descripcion_o_notas=desc_texto,
        taxonomia=tax_config,
    )

    es_grupo_godot = item.get("grupo") == "godot"
    if es_grupo_godot:
        fila_dim["engine"] = "godot"
        nivel = item.get("evidencia_nivel")
        fila_dim["engine_evidence_level"] = int(nivel) if nivel is not None else (res_motor.evidence_level or 1)
    else:
        fila_dim["engine"] = res_motor.engine
        fila_dim["engine_evidence_level"] = res_motor.evidence_level

    fila_dim["ai_disclosure_level"] = res_ia.disclosure_level.value

    #extraer lista de publishers para conteo global
    publishers_limpios = [
        p.strip().lower() for p in fila_dim.get("publishers", []) if p and p.strip()
    ]

    return {
        "item": item,
        "fila_dim": fila_dim,
        "fila_resena": fila_resena,
        "etiquetas_tienda": etiquetas_tienda,
        "precio_usd": precio_usd,
        "publishers_limpios": publishers_limpios,
    }


def _procesar_lote_trabajador(
    lote_datos: list[tuple[dict[str, Any], Optional[Path], Optional[Path]]],
    modo: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Procesar un fragmento de juegos en un proceso trabajador sin saturar memoria."""
    tax = _obtener_taxonomia_local()
    resultados: list[dict[str, Any]] = []
    conteo_local: Counter[str] = Counter()

    for item, ruta_det, ruta_res in lote_datos:
        res = _procesar_elemento(item, ruta_det, ruta_res, modo=modo, tax_config=tax)
        if res is not None:
            resultados.append(res)
            for pub in res["publishers_limpios"]:
                conteo_local[pub] += 1

    return resultados, conteo_local


def construir_tablas_plata(
    ruta_base: Optional[Path] = None,
    ruta_manifiesto: Optional[Path] = None,
    fecha: Optional[str] = None,
    version_pipeline: Optional[str] = None,
    modo: str = "control",
    appids_objetivo: Optional[list[int]] = None,
    perfil_hardware: Optional[PerfilHardware] = None,
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
    perfil = perfil_hardware or detectar_perfil_hardware()

    rutas_detalles = indexar_rutas_bronce(base, "appdetails", fecha)
    rutas_resenas = indexar_rutas_bronce(base, "appreviews_resumen", fecha)

    #determinar universo de items segun modo
    if modo == "masivo":
        if appids_objetivo is not None:
            candidatos = [int(a) for a in appids_objetivo if a in rutas_detalles and a in rutas_resenas]
        else:
            candidatos = [aid for aid in sorted(rutas_detalles.keys()) if aid in rutas_resenas]
        items = [{"appid": aid, "grupo": "general"} for aid in candidatos]
    else:
        items = _cargar_manifiesto(ruta_man)

    if not items:
        return (
            pa.Table.from_pylist([], schema=ESQUEMA_DIM_GAME),
            pa.Table.from_pylist([], schema=ESQUEMA_GAME_REVIEW_SUMMARY),
        )

    #construir lotes de items emparejados con sus rutas de bronce
    tamano_lote = max(1, perfil.batch_size)
    lotes: list[list[tuple[dict[str, Any], Optional[Path], Optional[Path]]]] = []
    for i in range(0, len(items), tamano_lote):
        chunk = items[i : i + tamano_lote]
        lote_chunk = [
            (it, rutas_detalles.get(int(it["appid"])), rutas_resenas.get(int(it["appid"])))
            for it in chunk
        ]
        lotes.append(lote_chunk)

    #ejecucion adaptativa: paralela con ProcessPoolExecutor o secuencial
    if perfil.usar_multiproceso and len(lotes) > 1:
        with ProcessPoolExecutor(max_workers=perfil.workers_asignados) as executor:
            resultados_lotes = list(
                executor.map(_procesar_lote_trabajador, lotes, [modo] * len(lotes))
            )
    else:
        resultados_lotes = [_procesar_lote_trabajador(lote, modo) for lote in lotes]

    #consolidar conteo global de publishers y elementos procesados
    conteo_publishers: Counter[str] = Counter()
    todos_los_elementos: list[dict[str, Any]] = []
    for elementos_lote, conteo_local in resultados_lotes:
        conteo_publishers.update(conteo_local)
        todos_los_elementos.extend(elementos_lote)

    tax_config = _obtener_taxonomia_local()
    filas_dim: list[dict[str, Any]] = []
    filas_resenas: list[dict[str, Any]] = []

    for elem in todos_los_elementos:
        fila_dim = elem["fila_dim"]
        fila_resena = elem["fila_resena"]

        #determinar tamano del catalogo del publisher segun conteo consolidado
        titulos_pub = None
        if fila_dim["publishers"]:
            conteos_pub = [
                conteo_publishers.get(p.strip().lower(), 1)
                for p in fila_dim["publishers"]
                if p and p.strip()
            ]
            if conteos_pub:
                titulos_pub = max(conteos_pub)

        res_indie = calcular_indie_score(
            tags=elem["etiquetas_tienda"],
            generos=fila_dim["genres"],
            developers=fila_dim["developers"],
            publishers=fila_dim["publishers"],
            price_usd=elem["precio_usd"],
            language_count=fila_dim["language_count"],
            titulos_del_publisher=titulos_pub,
            taxonomia=tax_config,
        )

        fila_dim["indie_score"] = res_indie.indie_score
        fila_dim["is_indie"] = res_indie.is_indie
        fila_dim["pipeline_version"] = version
        fila_resena["pipeline_version"] = version

        filas_dim.append(fila_dim)
        filas_resenas.append(fila_resena)

    filas_dim.sort(key=lambda f: f["game_id"])
    filas_resenas.sort(key=lambda f: f["game_id"])

    #construccion de tablas arrow mediante record batches compactos
    batches_dim: list[pa.RecordBatch] = []
    batches_resenas: list[pa.RecordBatch] = []
    for i in range(0, len(filas_dim), tamano_lote):
        chunk_dim = filas_dim[i : i + tamano_lote]
        chunk_res = filas_resenas[i : i + tamano_lote]
        batches_dim.append(pa.RecordBatch.from_pylist(chunk_dim, schema=ESQUEMA_DIM_GAME))
        batches_resenas.append(pa.RecordBatch.from_pylist(chunk_res, schema=ESQUEMA_GAME_REVIEW_SUMMARY))

    dim_game = (
        pa.Table.from_batches(batches_dim, schema=ESQUEMA_DIM_GAME)
        if batches_dim
        else pa.Table.from_pylist([], schema=ESQUEMA_DIM_GAME)
    )
    resumen = (
        pa.Table.from_batches(batches_resenas, schema=ESQUEMA_GAME_REVIEW_SUMMARY)
        if batches_resenas
        else pa.Table.from_pylist([], schema=ESQUEMA_GAME_REVIEW_SUMMARY)
    )

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
    perfil_hardware: Optional[PerfilHardware] = None,
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
        perfil_hardware=perfil_hardware,
    )
    if validador is not None:
        validador(dim_game, resumen)
    rutas = persistir_plata(dim_game, resumen, ruta_base=ruta_base)
    return {
        **rutas,
        "filas_dim_game": dim_game.num_rows,
        "filas_game_review_summary": resumen.num_rows,
    }
