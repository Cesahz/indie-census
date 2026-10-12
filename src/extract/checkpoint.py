#modulo para gestion persistente de checkpoints e idempotencia
#permite reanudar extracciones interrumpidas y asegurar ejecucion determinista
from collections.abc import Iterable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Optional

from src.version import PIPELINE_VERSION

#directorio base del proyecto y rutas por defecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUTA_DATA_DEFAULT = PROJECT_ROOT / "data"
RUTA_CHECKPOINT_DEFAULT = RUTA_DATA_DEFAULT / "checkpoint.json"

class CheckpointError(Exception):
    """Clase base para errores relacionados con el gestor de checkpoint."""

class CheckpointCorruptoError(CheckpointError):
    """Error emitido cuando el archivo de checkpoint esta corrupto o malformado."""

class GestorCheckpoint:
    """Administrador de estado para garantizar idempotencia y tolerancia a fallos."""

    def __init__(
        self,
        ruta_archivo: Optional[Path] = None,
        version_pipeline: Optional[str] = None
    ) -> None:
        """Inicializar el gestor de checkpoint cargando el archivo si existe o preparando nuevo estado."""
        #asignar ruta del archivo de persistencia
        self.ruta_archivo = Path(ruta_archivo) if ruta_archivo is not None else RUTA_CHECKPOINT_DEFAULT
        #asignar version del pipeline
        self.version_pipeline = version_pipeline or PIPELINE_VERSION
        #mapa interno de conjuntos de appids completados por recurso
        self._completados: dict[str, set[int]] = {}

        #cargar estado existente en disco si el archivo ya fue creado
        if self.ruta_archivo.exists():
            self.cargar()

    def cargar(self) -> None:
        """Cargar y validar la estructura del checkpoint almacenado en disco."""
        #leer contenido en formato json asegurando decodificacion utf-8
        try:
            with open(self.ruta_archivo, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise CheckpointCorruptoError(
                f"Archivo de checkpoint corrupto o JSON invalido en '{self.ruta_archivo}': {e}"
            ) from e

        #validar que el nodo raiz sea un diccionario
        if not isinstance(data, dict):
            raise CheckpointCorruptoError(
                f"Estructura de checkpoint corrupta en '{self.ruta_archivo}': el nodo raiz debe ser un objeto JSON."
            )

        #validar que el nodo de completados sea un diccionario
        completados_raw = data.get("completados")
        if completados_raw is None or not isinstance(completados_raw, dict):
            raise CheckpointCorruptoError(
                f"Estructura de checkpoint corrupta en '{self.ruta_archivo}': clave 'completados' ausente o invalida."
            )

        #poblar conjuntos internos por recurso
        self._completados = {}
        for recurso, ids in completados_raw.items():
            if not isinstance(ids, list):
                raise CheckpointCorruptoError(
                    f"Estructura de checkpoint corrupta para recurso '{recurso}': se esperaba una lista de ids."
                )
            self._completados[recurso] = {int(x) for x in ids}

    def esta_completado(self, recurso: str, appid: int) -> bool:
        """Consultar si un appid determinado ya fue registrado como completado para un recurso."""
        #verificar pertenencia en el conjunto del recurso
        return int(appid) in self._completados.get(recurso, set())

    def marcar_completado(self, recurso: str, appid: int, persistir: bool = True) -> None:
        """Registrar un appid como completado y persistir atomicamente en disco."""
        #inicializar conjunto del recurso si no existe
        if recurso not in self._completados:
            self._completados[recurso] = set()
        #agregar appid al conjunto
        self._completados[recurso].add(int(appid))

        #guardar en disco si se solicita persistencia inmediata
        if persistir:
            self.guardar()

    def marcar_lote_completado(
        self,
        recurso: str,
        appids: Iterable[int],
        persistir: bool = True
    ) -> None:
        """Registrar una coleccion de appids como completados y persistir una sola vez."""
        #inicializar conjunto del recurso si no existe
        if recurso not in self._completados:
            self._completados[recurso] = set()
        #agregar coleccion de appids
        self._completados[recurso].update(int(x) for x in appids)

        #guardar en disco si se solicita persistencia inmediata
        if persistir:
            self.guardar()

    def obtener_completados(self, recurso: str) -> set[int]:
        """Obtener una copia del conjunto de appids completados para un recurso especifico."""
        #retornar copia defensiva del conjunto
        return set(self._completados.get(recurso, set()))

    def obtener_pendientes(self, recurso: str, appids: Iterable[int]) -> list[int]:
        """Filtrar una coleccion de appids retornando en orden los que aun no fueron completados."""
        #obtener conjunto completado para el recurso
        completados = self._completados.get(recurso, set())
        #filtrar preservando el orden original de iteracion
        return [int(appid) for appid in appids if int(appid) not in completados]

    def guardar(self) -> None:
        """Persistir atomicamente el estado completo en disco empleando un archivo temporal."""
        #asegurar que la carpeta contenedora exista
        self.ruta_archivo.parent.mkdir(parents=True, exist_ok=True)

        #generar marca temporal utc en formato iso 8601
        ahora_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        #estructurar documento json con listas ordenadas para reproducibilidad
        documento = {
            "version": self.version_pipeline,
            "actualizado_en": ahora_utc,
            "completados": {
                rec: sorted(list(ids))
                for rec, ids in sorted(self._completados.items())
            }
        }

        #escritura atomica mediante archivo temporal adyacente
        ruta_tmp = self.ruta_archivo.with_suffix(".tmp")
        try:
            with open(ruta_tmp, "w", encoding="utf-8") as f:
                json.dump(documento, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(ruta_tmp, self.ruta_archivo)
        except Exception:
            #limpiar archivo temporal residual en caso de fallo
            if ruta_tmp.exists():
                ruta_tmp.unlink(missing_ok=True)
            raise

    def limpiar(self) -> None:
        """Reiniciar el estado interno y persistir el vaciado en el archivo de disco."""
        #vaciar mapa interno de completados y guardar
        self._completados = {}
        self.guardar()

    def resumen(self) -> dict[str, int]:
        """Retornar un resumen con el conteo de elementos completados por recurso activo."""
        #construir diccionario resumen omitiendo recursos vacios
        return {rec: len(ids) for rec, ids in self._completados.items() if len(ids) > 0}
