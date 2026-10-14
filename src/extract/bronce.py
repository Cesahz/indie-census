#modulo de persistencia inmutable para la capa de bronce
#regla: solo escritura, sobreescritura rechazada, escritura atomica
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.version import PIPELINE_VERSION

#directorio base del proyecto y carpeta data por defecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUTA_DATA_DEFAULT = PROJECT_ROOT / "data"

#recursos permitidos en la particion de steam
RECURSOS_ADMITIDOS = {"appdetails", "appreviews_resumen"}

class BronzeImmutabilityError(FileExistsError):
    """Error bloqueante: intento de sobreescritura sobre archivo existente en bronce."""

def crear_envoltorio_bronce(
    fuente: str,
    url_solicitada: str,
    parametros: dict[str, Any],
    estado_http: int,
    payload: dict[str, Any],
    extraido_en: Optional[str] = None,
    version_pipeline: Optional[str] = None
) -> dict[str, Any]:
    """Construir envoltorio canonico con metadatos tecnicos y hash de auditoria.
    Entradas:
    - fuente: identificador del endpoint (ej. 'steam.appdetails').
    - url_solicitada: url completa con query params enviada al servidor.
    - parametros: diccionario de configuracion de la llamada (region, idioma).
    - estado_http: codigo de respuesta http retornado (ej. 200).
    - payload: respuesta cruda de la api sin modificar.
    - extraido_en: marca de tiempo utc en formato iso 8601 (opcional).
    - version_pipeline: version del codigo extractor (opcional).
    Salida:
    - diccionario con claves 'meta' y 'payload', incluyendo 'sha256_payload'.
    """
    #generar marca temporal utc en formato iso 8601 si no se provee
    if extraido_en is None:
        extraido_en = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    #utilizar version activa del pipeline si no se provee
    if version_pipeline is None:
        version_pipeline = PIPELINE_VERSION
        
    #computar hash sha256 determinista del payload serializado
    payload_serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    sha256_payload = hashlib.sha256(payload_serializado.encode("utf-8")).hexdigest()
    
    #ensamblar envoltorio inmutable
    return {
        "meta": {
            "fuente": fuente,
            "url_solicitada": url_solicitada,
            "parametros": parametros,
            "estado_http": estado_http,
            "extraido_en": extraido_en,
            "version_pipeline": version_pipeline,
            "sha256_payload": sha256_payload,
        },
        "payload": payload,
    }

def guardar_en_bronce(
    recurso: str,
    fecha: str,
    appid: int,
    envoltorio: dict[str,Any],
    ruta_base: Path = None
) -> Path:
    """Persistir envoltorio en disco con particionado estricto y escritura atomica.
    particionado:
    data/bronce/steam/<recurso>/fecha=AAAA-MM-DD/appid=<id>.json
    entradas:
    - recurso: nombre del endpoint ('appdetails' o 'appreviews_resumen').
    - fecha: cadena con fecha en formato 'AAAA-MM-DD'.
    - appid: identificador numerico unico de la aplicacion.
    - envoltorio: diccionario generado por crear_envoltorio_bronce.
    - ruta_base: directorio base (opcional, por defecto data/).
    salida:
    - Path del archivo final persistido en disco.
    excepciones:
    - ValueError: si el recurso no pertenece al conjunto admitido.
    - BronzeImmutabilityError: si el archivo de destino ya existe.

    """
    
    #validar recurso permitido
    if recurso not in RECURSOS_ADMITIDOS:
        raise ValueError(f"Recurso no admitido '{recurso}'. Admitidos: {RECURSOS_ADMITIDOS}")
    
    #resolver directorio base
    base = ruta_base or RUTA_DATA_DEFAULT
    
    #construir ruta canonico segun estandar bronce
    directorio_particion = base / "bronce" / "steam" / recurso / f"fecha={fecha}"
    archivo_destino = directorio_particion / f"appid={appid}.json"
    
    #rechazo estricto de sobreescritura
    if archivo_destino.exists():
        raise BronzeImmutabilityError(
            f"Sobrescritura rechazada en capa bronce: el archivo {archivo_destino.name} "
            f"Ya existe en {directorio_particion}"
        )
    
    #crear directorios si no existen
    directorio_particion.mkdir(parents=True, exist_ok=True)
    
    #escritura atomica con archivo temporal y reemplazo
    archivo_temporal = directorio_particion / f"appid={appid}.tmp"
    try:
        contenido_json = json.dumps(envoltorio, indent=4, ensure_ascii=False)
        archivo_temporal.write_text(contenido_json, encoding="utf-8")
        os.replace(archivo_temporal, archivo_destino)
    except Exception:
        #eliminar archivo temporal si ocurrio cualquier falla imprevista
        if archivo_temporal.exists():
            archivo_temporal.unlink()
        raise

    return archivo_destino
    