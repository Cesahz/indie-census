#modulo de reconciliacion cero-huecos, unificacion de workers y auditoria pre-plata (contrato 10)
#garantias: verificacion integral contra manifest_master, barrido residual y validacion sha-256
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tarfile
from typing import Any, Optional

from src.extract.checkpoint import GestorCheckpoint
from src.extract.client import SteamAppNotFoundError, SteamClient
from src.extract.pipeline import cargar_manifest_master, extraer_juego
from src.quality.contratos import ContratoCalidadError


class ReconciliacionError(ContratoCalidadError):
    """Error bloqueante emitido cuando se detectan huecos o corrupcion en la fusion de ingesta."""

    def __init__(self, detalle: str) -> None:
        super().__init__(contrato="c10_reconciliacion_cero_huecos", detalle=detalle)


def descomprimir_snapshot_worker(
    ruta_tar: Path,
    ruta_base_destino: Path,
) -> dict[str, Any]:
    """Descomprimir atómicamente un archivo snapshot tar.gz sobre la estructura base sin corromper datos."""
    ruta_tar = Path(ruta_tar)
    ruta_base_destino = Path(ruta_base_destino)
    ruta_base_destino.mkdir(parents=True, exist_ok=True)

    if not ruta_tar.is_file():
        raise FileNotFoundError(f"Snapshot tar no encontrado en: {ruta_tar}")

    archivos_extraidos = 0
    with tarfile.open(ruta_tar, "r:gz") as tar:
        try:
            tar.extractall(path=ruta_base_destino, filter="data")
        except TypeError:
            tar.extractall(path=ruta_base_destino)
        archivos_extraidos = len([m for m in tar.getmembers() if m.isfile()])

    return {
        "snapshot": str(ruta_tar),
        "destino": str(ruta_base_destino),
        "archivos_extraidos": archivos_extraidos,
    }


def _encontrar_archivo_recurso(
    ruta_base: Path,
    recurso: str,
    fecha: str,
    appid: int,
) -> Optional[Path]:
    """Localizar archivo de recurso tanto en formato hive (recurso/fecha=X/appid=Y.json) como plano."""
    posibles_rutas = [
        ruta_base / "bronce" / "steam" / recurso / f"fecha={fecha}" / f"appid={appid}.json",
        ruta_base / "bronce" / "steam" / recurso / f"fecha={fecha}" / f"{appid}.json",
        ruta_base / "bronce" / "steam" / fecha / recurso / f"appid={appid}.json",
        ruta_base / "bronce" / "steam" / fecha / recurso / f"{appid}.json",
    ]
    for p in posibles_rutas:
        if p.is_file():
            return p
    return None


def auditar_completitud_manifiesto(
    ruta_manifiesto: Path,
    ruta_bronce_fecha: Optional[Path] = None,
    ruta_base: Optional[Path] = None,
    fecha: Optional[str] = None,
    checkpoints: Optional[list[GestorCheckpoint]] = None,
) -> dict[str, Any]:
    """Auditar completitud exhaustiva de todos los appids del manifiesto maestro en capa bronce."""
    ruta_man = Path(ruta_manifiesto)
    appids_maestros = cargar_manifest_master(ruta_man)
    total_manifiesto = len(appids_maestros)

    #resolver ruta base
    if ruta_base is not None:
        base = Path(ruta_base)
    elif ruta_bronce_fecha is not None:
        base = Path(ruta_bronce_fecha).parents[2]
    else:
        base = ruta_man.parents[4]

    #resolver fecha
    if fecha is None:
        if ruta_bronce_fecha is not None:
            fecha = ruta_bronce_fecha.name
            if fecha.startswith("fecha="):
                fecha = fecha.split("=", 1)[1]
        else:
            #intentar extraer de la ruta del manifiesto
            for part in ruta_man.parts:
                if len(part) == 10 and part.count("-") == 2:
                    fecha = part
                    break
            if fecha is None:
                fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    checkpoints_activos = checkpoints or []
    no_disponibles_set: set[int] = set()
    for cp in checkpoints_activos:
        no_disponibles_set.update(cp.obtener_completados("no_disponible"))

    completados_exito: list[int] = []
    no_disponibles: list[int] = []
    appids_pendientes: list[int] = []

    for aid in appids_maestros:
        if aid in no_disponibles_set:
            no_disponibles.append(aid)
            continue

        arch_det = _encontrar_archivo_recurso(base, "appdetails", fecha, aid)
        arch_rev = _encontrar_archivo_recurso(base, "appreviews_resumen", fecha, aid)

        if arch_det is not None and arch_rev is not None:
            try:
                if arch_det.stat().st_size > 0 and arch_rev.stat().st_size > 0:
                    completados_exito.append(aid)
                else:
                    appids_pendientes.append(aid)
            except Exception:
                appids_pendientes.append(aid)
        else:
            appids_pendientes.append(aid)

    huecos = len(appids_pendientes)
    total_cubierto = len(completados_exito) + len(no_disponibles)
    tasa = round(total_cubierto / total_manifiesto, 4) if total_manifiesto > 0 else 1.0

    return {
        "ruta_manifiesto": str(ruta_man),
        "total_manifiesto": total_manifiesto,
        "completados_exito": len(completados_exito),
        "no_disponibles": len(no_disponibles),
        "huecos_pendientes": huecos,
        "tasa_completitud": tasa,
        "appids_pendientes": appids_pendientes,
    }


def verificar_integridad_criptografica(ruta_bronce_o_base: Path) -> dict[str, Any]:
    """Validar hashes SHA-256 de todos los payloads json almacenados en una particion de bronce."""
    ruta_dir = Path(ruta_bronce_o_base)
    total_verificados = 0
    integros = 0
    corruptos = 0
    archivos_corruptos: list[str] = []

    if not ruta_dir.is_dir():
        return {
            "total_verificados": 0,
            "integros": 0,
            "corruptos": 0,
            "archivos_corruptos": [],
        }

    for raiz, _, archivos in os.walk(ruta_dir):
        for arch in archivos:
            if not arch.endswith(".json") or arch.endswith(".tmp"):
                continue
            #omitir reportes de auditorias, checkpoints y benchmarks de la validacion de payloads raw
            if "auditorias" in raiz or "benchmarks" in raiz or "applist" in raiz or "checkpoint" in arch:
                continue

            ruta_archivo = Path(raiz) / arch
            total_verificados += 1
            try:
                with open(ruta_archivo, "r", encoding="utf-8") as f:
                    doc = json.load(f)

                meta = doc.get("meta", {})
                payload = doc.get("payload")
                hash_esperado = meta.get("sha256") or meta.get("sha256_payload")

                if not hash_esperado or payload is None:
                    integros += 1
                    continue

                raw_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
                hash_calculado = hashlib.sha256(raw_bytes).hexdigest()

                if hash_calculado == hash_esperado:
                    integros += 1
                else:
                    corruptos += 1
                    archivos_corruptos.append(str(ruta_archivo))
            except Exception:
                corruptos += 1
                archivos_corruptos.append(str(ruta_archivo))

    return {
        "total_verificados": total_verificados,
        "integros": integros,
        "corruptos": corruptos,
        "archivos_corruptos": archivos_corruptos,
    }


def ejecutar_barrido_residual(
    appids_pendientes: list[int],
    client: SteamClient,
    fecha: str,
    ruta_base: Path,
    checkpoint: GestorCheckpoint,
) -> dict[str, Any]:
    """Ejecutar pasada de barrido final sobre la lista de appids residuales hasta extinguir huecos."""
    resueltos_exito = 0
    no_disponibles = 0
    fallidos = 0
    pendientes_finales: list[int] = []

    for aid in appids_pendientes:
        try:
            extraer_juego(
                client=client,
                checkpoint=checkpoint,
                appid=aid,
                fecha=fecha,
                ruta_base=ruta_base,
            )
            resueltos_exito += 1
        except SteamAppNotFoundError:
            checkpoint.marcar_completado("no_disponible", aid)
            no_disponibles += 1
        except Exception:
            fallidos += 1
            pendientes_finales.append(aid)

    checkpoint.guardar()
    return {
        "resueltos_exito": resueltos_exito,
        "no_disponibles": no_disponibles,
        "fallidos": fallidos,
        "pendientes_finales": len(pendientes_finales),
        "appids_no_resueltos": pendientes_finales,
    }


def reconciliar_ingesta_distribuida(
    ruta_manifiesto: Path,
    fecha: str,
    ruta_base: Path,
    rutas_snapshots: Optional[list[Path]] = None,
    client: Optional[SteamClient] = None,
    permitir_barrido: bool = True,
) -> dict[str, Any]:
    """Orquestar la unificacion, auditoria cero-huecos, barrido y validacion sha-256 pre-plata."""
    base = Path(ruta_base)
    ruta_man = Path(ruta_manifiesto)
    ruta_bronce = base / "bronce"

    #1. descomprimir snapshots de workers remotos si fueron provistos
    snapshots_procesados: list[dict[str, Any]] = []
    if rutas_snapshots:
        for r_tar in rutas_snapshots:
            if Path(r_tar).is_file():
                res_tar = descomprimir_snapshot_worker(r_tar, base)
                snapshots_procesados.append(res_tar)

    #2. cargar checkpoints existentes
    checkpoints: list[GestorCheckpoint] = []
    for f in base.glob("checkpoint*.json"):
        try:
            checkpoints.append(GestorCheckpoint(ruta_archivo=f))
        except Exception:
            pass

    #3. primera pasada de auditoria de completitud
    auditoria_inicial = auditar_completitud_manifiesto(
        ruta_manifiesto=ruta_man,
        ruta_base=base,
        fecha=fecha,
        checkpoints=checkpoints,
    )

    #4. si existen huecos y se habilita el barrido, procesar lista residual
    resultado_barrido: Optional[dict[str, Any]] = None
    if auditoria_inicial["huecos_pendientes"] > 0 and permitir_barrido and client is not None:
        cp_barrido = GestorCheckpoint(ruta_archivo=base / "checkpoint_barrido.json")
        resultado_barrido = ejecutar_barrido_residual(
            appids_pendientes=auditoria_inicial["appids_pendientes"],
            client=client,
            fecha=fecha,
            ruta_base=base,
            checkpoint=cp_barrido,
        )
        checkpoints.append(cp_barrido)

    #5. auditoria final de completitud
    auditoria_final = auditar_completitud_manifiesto(
        ruta_manifiesto=ruta_man,
        ruta_base=base,
        fecha=fecha,
        checkpoints=checkpoints,
    )

    #6. verificacion criptografica sha-256 de los archivos unificados
    auditoria_crypto = verificar_integridad_criptografica(ruta_bronce)

    aprobado = (
        auditoria_final["huecos_pendientes"] == 0
        and auditoria_crypto["corruptos"] == 0
    )

    estado = "aprobado" if aprobado else "bloqueado"

    reporte = {
        "estado": estado,
        "fecha_particion": fecha,
        "auditado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_manifiesto": auditoria_final["total_manifiesto"],
        "completados_exito": auditoria_final["completados_exito"],
        "no_disponibles": auditoria_final["no_disponibles"],
        "huecos_pendientes": auditoria_final["huecos_pendientes"],
        "tasa_completitud": auditoria_final["tasa_completitud"],
        "archivos_verificados": auditoria_crypto["total_verificados"],
        "archivos_integros": auditoria_crypto["integros"],
        "archivos_corruptos": auditoria_crypto["corruptos"],
        "snapshots_unificados": len(snapshots_procesados),
        "barrido_residual_ejecutado": resultado_barrido is not None,
    }

    #persistir reporte en data/bronce/steam/<fecha>/auditorias/reconciliacion_cero_huecos.json
    dir_auditorias = base / "bronce" / "steam" / fecha / "auditorias"
    dir_auditorias.mkdir(parents=True, exist_ok=True)
    ruta_rep = dir_auditorias / "reconciliacion_cero_huecos.json"
    ruta_tmp = ruta_rep.with_suffix(".tmp")
    try:
        with open(ruta_tmp, "w", encoding="utf-8") as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(ruta_tmp, ruta_rep)
    except Exception:
        if ruta_tmp.exists():
            ruta_tmp.unlink(missing_ok=True)

    if not aprobado:
        raise ReconciliacionError(
            f"Fallo en Contrato 10 de Reconciliacion: {auditoria_final['huecos_pendientes']} huecos pendientes, "
            f"{auditoria_crypto['corruptos']} archivos corruptos."
        )

    return reporte
