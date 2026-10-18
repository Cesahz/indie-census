#modulo orquestador de extraccion de la muestra de control
#coordina cliente http resiliente, persistencia inmutable en bronce y gestor de checkpoint
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import yaml

from src.extract.bronce import BronzeImmutabilityError, crear_envoltorio_bronce, guardar_en_bronce
from src.extract.checkpoint import GestorCheckpoint
from src.extract.client import SteamClient
from src.extract.progress import BarraProgreso

#rutas canonicas por defecto del repositorio
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUTA_MANIFIESTO_DEFAULT = PROJECT_ROOT / "config" / "muestra_control.yaml"
RUTA_DATA_DEFAULT = PROJECT_ROOT / "data"
RUTA_BRONCE_DEFAULT = RUTA_DATA_DEFAULT / "bronce"
RUTA_CHECKPOINT_DEFAULT = RUTA_DATA_DEFAULT / "checkpoint.json"

def extraer_juego(
    client: SteamClient,
    checkpoint: GestorCheckpoint,
    appid: int,
    fecha: Optional[str] = None,
    ruta_base: Optional[Path] = None,
) -> dict[str, bool]:
    """Extraer appdetails y appreviews_resumen para un appid individual si estan pendientes.
    Entradas:
    - client: instancia configurada de SteamClient.
    - checkpoint: instancia de GestorCheckpoint para auditar completados.
    - appid: identificador numerico unico del juego en Steam.
    - fecha: particion de fecha en formato AAAA-MM-DD (opcional).
    - ruta_base: directorio base de datos (opcional, por defecto data/).
    Salida:
    - diccionario indicando si cada recurso requirio extraccion efectiva.
    """
    #asignar fecha utc actual si no se especifica particion
    if fecha is None:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    resultado = {"appdetails": False, "appreviews_resumen": False}

    #1. procesar metadatos de appdetails si no esta completado
    if not checkpoint.esta_completado("appdetails", appid):
        url_details = (
            f"{client.base_url_store}/appdetails"
            f"?appids={appid}&cc={client.country_code}&l={client.language}"
        )
        payload_details = client.get_app_details(appid)
        envoltorio_details = crear_envoltorio_bronce(
            fuente="steam.appdetails",
            url_solicitada=url_details,
            parametros={"region": client.country_code, "idioma": client.language},
            estado_http=200,
            payload=payload_details,
        )
        guardar_en_bronce(
            recurso="appdetails",
            fecha=fecha,
            appid=appid,
            envoltorio=envoltorio_details,
            ruta_base=ruta_base,
        )
        checkpoint.marcar_completado("appdetails", appid)
        resultado["appdetails"] = True

    #2. procesar resumen cuantitativo de resenas si no esta completado
    if not checkpoint.esta_completado("appreviews_resumen", appid):
        url_reviews = (
            f"https://store.steampowered.com/appreviews/{appid}"
            f"?json=1&language={client.language}&purchase_type=all&num_per_page=0"
        )
        payload_reviews = client.get_app_reviews_summary(appid)
        envoltorio_reviews = crear_envoltorio_bronce(
            fuente="steam.appreviews_resumen",
            url_solicitada=url_reviews,
            parametros={"language": client.language, "purchase_type": "all", "num_per_page": 0},
            estado_http=200,
            payload=payload_reviews,
        )
        guardar_en_bronce(
            recurso="appreviews_resumen",
            fecha=fecha,
            appid=appid,
            envoltorio=envoltorio_reviews,
            ruta_base=ruta_base,
        )
        checkpoint.marcar_completado("appreviews_resumen", appid)
        resultado["appreviews_resumen"] = True

    return resultado

def ejecutar_extraccion_muestra(
    ruta_manifiesto: Optional[Path] = None,
    ruta_base: Optional[Path] = None,
    ruta_checkpoint: Optional[Path] = None,
    client: Optional[SteamClient] = None,
    checkpoint: Optional[GestorCheckpoint] = None,
    fecha: Optional[str] = None,
) -> dict[str, Any]:
    """Orquestar la extraccion secuencial e idempotente de la muestra de control.
    Entradas:
    - ruta_manifiesto: ruta al archivo muestra_control.yaml.
    - ruta_base: ruta base para data (opcional, por defecto data/).
    - ruta_checkpoint: ruta al archivo json del checkpoint.
    - client: cliente steam inyectado (o nuevo por defecto).
    - checkpoint: gestor de checkpoint inyectado (o nuevo por defecto).
    - fecha: marca de particion de fecha (opcional).
    Salida:
    - diccionario con metricas del lote: total, exitosos, fallidos y detalle de errores.
    """
    #resolver rutas canonicas predeterminadas si no se inyectan
    ruta_man = Path(ruta_manifiesto) if ruta_manifiesto is not None else RUTA_MANIFIESTO_DEFAULT
    ruta_chk = Path(ruta_checkpoint) if ruta_checkpoint is not None else RUTA_CHECKPOINT_DEFAULT

    #inicializar dependencias si no fueron provistas
    if client is None:
        client = SteamClient()
    if checkpoint is None:
        checkpoint = GestorCheckpoint(ruta_archivo=ruta_chk)
    if fecha is None:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    #leer el manifiesto con los appids de control
    with open(ruta_man, "r", encoding="utf-8") as f:
        manifiesto = yaml.safe_load(f)

    juegos = manifiesto.get("juegos", []) if isinstance(manifiesto, dict) else []
    total_juegos = len(juegos)
    procesados_exito = 0
    fallidos = 0
    errores: list[dict[str, Any]] = []

    #iterar por cada juego de la muestra
    for item in juegos:
        appid = int(item["appid"])
        try:
            extraer_juego(
                client=client,
                checkpoint=checkpoint,
                appid=appid,
                fecha=fecha,
                ruta_base=ruta_base,
            )
            procesados_exito += 1
        except Exception as exc:
            fallidos += 1
            errores.append({"appid": appid, "error": str(exc)})

    return {
        "total_juegos": total_juegos,
        "procesados_exito": procesados_exito,
        "fallidos": fallidos,
        "errores": errores,
    }


def _guardar_lote_catalogo(
    apps: list[dict[str, Any]],
    lote_idx: int,
    fecha: str,
    ruta_base: Optional[Path],
) -> None:
    #guardar lote de apps descubiertas en capa bronce
    payload = {"response": {"apps": apps, "total_apps": len(apps)}}
    envoltorio = crear_envoltorio_bronce(
        fuente="steam.applist",
        url_solicitada="https://api.steampowered.com/IStoreService/GetAppList/v1/",
        parametros={"lote_idx": lote_idx, "total_en_lote": len(apps)},
        estado_http=200,
        payload=payload,
    )
    try:
        guardar_en_bronce(
            recurso="applist",
            fecha=fecha,
            appid=lote_idx,
            envoltorio=envoltorio,
            ruta_base=ruta_base,
        )
    except BronzeImmutabilityError:
        pass


def descubrir_catalogo_steam(
    client: SteamClient,
    max_juegos: Optional[int] = None,
    batch_size: int = 50000,
    fecha: Optional[str] = None,
    ruta_base: Optional[Path] = None,
) -> list[int]:
    """Descubrir catalogo en Steam, persistir lotes crudos en capa Bronce y retornar appids."""
    if fecha is None:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    appids: list[int] = []
    lote_apps: list[dict[str, Any]] = []
    lote_idx = 0

    for app in client.iterar_catalogo_completo(max_total=max_juegos, batch_size=batch_size):
        appid = int(app["appid"])
        appids.append(appid)
        lote_apps.append(app)

        if len(lote_apps) >= batch_size:
            _guardar_lote_catalogo(lote_apps, lote_idx, fecha, ruta_base)
            lote_idx += 1
            lote_apps = []

    if lote_apps or lote_idx == 0:
        _guardar_lote_catalogo(lote_apps, lote_idx, fecha, ruta_base)

    return appids


def congelar_manifiesto_maestro(
    client: Optional[SteamClient] = None,
    min_appid: int = 2400000,
    max_juegos: Optional[int] = None,
    fecha: Optional[str] = None,
    ruta_base: Optional[Path] = None,
    ruta_destino: Optional[Path] = None,
) -> Path:
    """Descubrir catalogo en Steam, filtrar por umbral min_appid y congelar manifest_master.json inmutable."""
    cliente_activo = client or SteamClient()
    if fecha is None:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    appids_encontrados: set[int] = set()
    for app in cliente_activo.iterar_catalogo_completo():
        aid = int(app["appid"])
        if aid >= min_appid:
            appids_encontrados.add(aid)
            if max_juegos is not None and len(appids_encontrados) >= max_juegos:
                break

    appids_ordenados = sorted(appids_encontrados)

    payload = {
        "descripcion": "Manifiesto maestro inmutable para ingesta distribuida",
        "criterio_filtro": f"appid >= {min_appid}",
        "total_appids": len(appids_ordenados),
        "min_appid": appids_ordenados[0] if appids_ordenados else None,
        "max_appid": appids_ordenados[-1] if appids_ordenados else None,
        "appids": appids_ordenados,
    }

    envoltorio = crear_envoltorio_bronce(
        fuente="steam.catalog.manifest_master",
        url_solicitada="IStoreService/GetAppList/v1",
        parametros={"min_appid": min_appid, "max_juegos": max_juegos},
        estado_http=200,
        payload=payload,
    )
    envoltorio["meta"]["recurso"] = "applist"
    envoltorio["meta"]["sha256"] = envoltorio["meta"]["sha256_payload"]

    if ruta_destino is None:
        base = ruta_base or RUTA_DATA_DEFAULT
        destino = base / "bronce" / "steam" / fecha / "applist" / "manifest_master.json"
    else:
        destino = ruta_destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    ruta_tmp = destino.with_suffix(".tmp")
    with open(ruta_tmp, "w", encoding="utf-8") as f:
        json.dump(envoltorio, f, indent=2, ensure_ascii=False)
    ruta_tmp.replace(destino)

    return destino


def cargar_manifest_master(ruta_manifiesto: Path) -> list[int]:
    """Cargar lista inmutable de appids desde manifest_master.json."""
    if not ruta_manifiesto.is_file():
        raise FileNotFoundError(f"Manifiesto maestro no encontrado: {ruta_manifiesto}")

    with open(ruta_manifiesto, "r", encoding="utf-8") as f:
        datos = json.load(f)

    if "payload" in datos and isinstance(datos["payload"], dict) and "appids" in datos["payload"]:
        appids = datos["payload"]["appids"]
    elif isinstance(datos, list):
        appids = datos
    elif "appids" in datos:
        appids = datos["appids"]
    else:
        raise ValueError(f"Formato no reconocido en manifiesto maestro: {ruta_manifiesto}")

    return [int(a) for a in appids]


def particionar_appids_por_modulo(
    appids: list[int],
    worker_id: int = 0,
    total_workers: int = 1,
) -> list[int]:
    """Filtrar lista de appids mediante congruencia modular asegurando cero huecos y cero solapamiento."""
    if total_workers < 1:
        raise ValueError(f"total_workers debe ser >= 1, se recibio {total_workers}")
    if not (0 <= worker_id < total_workers):
        raise ValueError(f"worker_id debe estar en [0..{total_workers-1}], se recibio {worker_id}")

    if total_workers == 1:
        return list(appids)

    return [appid for idx, appid in enumerate(appids) if idx % total_workers == worker_id]


def sincronizar_snapshot_tar(
    ruta_bronce: Path,
    sync_tar_dir: Path,
    worker_id: int = 0,
) -> Path:
    """Empaquetar atómicamente el directorio local de bronce en un archivo tar.gz en sync_tar_dir."""
    sync_tar_dir.mkdir(parents=True, exist_ok=True)
    nombre_final = f"bronce_worker_{worker_id}.tar.gz"
    ruta_final = sync_tar_dir / nombre_final
    ruta_tmp = sync_tar_dir / f"bronce_worker_{worker_id}.tmp.tar.gz"

    with tarfile.open(ruta_tmp, "w:gz") as tar:
        #empaquetar el directorio si existe
        if ruta_bronce.is_dir():
            tar.add(ruta_bronce, arcname=ruta_bronce.name)

    ruta_tmp.replace(ruta_final)
    return ruta_final


def ejecutar_ingesta_masiva(
    appids: list[int],
    client: Optional[SteamClient] = None,
    checkpoint: Optional[GestorCheckpoint] = None,
    fecha: Optional[str] = None,
    ruta_base: Optional[Path] = None,
    mostrar_progreso: bool = True,
    stream_progreso: Optional[Any] = None,
    worker_id: int = 0,
    total_workers: int = 1,
    sync_tar_dir: Optional[Path] = None,
    sync_interval: int = 250,
) -> dict[str, Any]:
    """Orquestar la ingesta secuencial masiva de appids con checkpoints e idempotencia."""
    cliente_activo = client or SteamClient()
    base_dir = ruta_base or RUTA_DATA_DEFAULT

    if checkpoint is None:
        if total_workers > 1:
            nombre_cp = f"checkpoint_worker_{worker_id}_of_{total_workers}.json"
        else:
            nombre_cp = "checkpoint.json"
        cp_activo = GestorCheckpoint(ruta_archivo=base_dir / nombre_cp)
    else:
        cp_activo = checkpoint

    if fecha is None:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_solicitados = len(appids)
    ya_completados = 0
    procesados_exito = 0
    fallidos = 0
    errores: list[dict[str, Any]] = []
    juegos_desde_sync = 0
    ruta_bronce_local = base_dir / "bronce"

    barra = BarraProgreso(
        total=total_solicitados,
        stream=stream_progreso,
        habilitado=mostrar_progreso,
    )

    try:
        for i, appid in enumerate(appids, start=1):
            #verificar si ambos recursos estan completados
            det_completado = cp_activo.esta_completado("appdetails", appid)
            rev_completado = cp_activo.esta_completado("appreviews_resumen", appid)

            if det_completado and rev_completado:
                ya_completados += 1
                barra.actualizar(
                    actual=i,
                    appid=appid,
                    exitosos=procesados_exito + ya_completados,
                    fallidos=fallidos,
                )
                continue

            try:
                extraer_juego(
                    client=cliente_activo,
                    checkpoint=cp_activo,
                    appid=appid,
                    fecha=fecha,
                    ruta_base=ruta_base,
                )
                procesados_exito += 1
                juegos_desde_sync += 1

                #sincronizar snapshot tar si se alcanza el intervalo
                if sync_tar_dir is not None and juegos_desde_sync >= sync_interval:
                    sincronizar_snapshot_tar(ruta_bronce_local, sync_tar_dir, worker_id=worker_id)
                    juegos_desde_sync = 0
            except Exception as exc:
                fallidos += 1
                errores.append({"appid": appid, "error": str(exc)})

            barra.actualizar(
                actual=i,
                appid=appid,
                exitosos=procesados_exito + ya_completados,
                fallidos=fallidos,
                forzar=(i == total_solicitados),
            )
    finally:
        barra.cerrar()
        #sincronizacion final atómica al concluir o interrumpir
        if sync_tar_dir is not None:
            try:
                sincronizar_snapshot_tar(ruta_bronce_local, sync_tar_dir, worker_id=worker_id)
            except Exception:
                pass

    return {
        "total_solicitados": total_solicitados,
        "total_juegos": total_solicitados,
        "ya_completados": ya_completados,
        "procesados_exito": procesados_exito,
        "fallidos": fallidos,
        "errores": errores,
    }


