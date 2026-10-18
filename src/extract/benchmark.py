#modulo de telemetria y benchmarking para ingesta distribuida (criterio f3-06)
#garantias: esquema determinista, calculo de rendimiento en tiempo real y persistencia atomica
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Optional


def detectar_entorno_nodo() -> str:
    """Detectar automaticamente si el nodo corre en Google Colab o entorno local."""
    if Path("/content").is_dir():
        return "Google Colab Pro (Google Cloud)"
    return "PC Local (Fibra Residencial)"


class ColectorTelemetria:
    """Colector de metricas operativas y rendimiento por worker para benchmarking."""

    def __init__(
        self,
        worker_id: int = 0,
        total_workers: int = 1,
        node_environment: Optional[str] = None,
        total_assigned_appids: int = 0,
        ruta_bronce: Optional[Path] = None,
        fecha: Optional[str] = None,
        sync_tar_dir: Optional[Path] = None,
    ) -> None:
        self.worker_id = worker_id
        self.total_workers = total_workers
        self.node_environment = node_environment or detectar_entorno_nodo()
        self.total_assigned_appids = total_assigned_appids
        self.ruta_bronce = Path(ruta_bronce) if ruta_bronce is not None else None
        self.fecha = fecha
        self.sync_tar_dir = Path(sync_tar_dir) if sync_tar_dir is not None else None

        self.start_time = datetime.now(timezone.utc)
        self.processed_appids = 0
        self.successful_fetches = 0
        self.unavailable_or_dlc = 0
        self.rate_limit_hits_429 = 0
        self.network_retry_count = 0
        self.total_requests = 0

    def registrar_exito(self, appid: int) -> None:
        """Registrar extraccion exitosa de un appid."""
        self.processed_appids += 1
        self.successful_fetches += 1

    def registrar_no_disponible(self, appid: int) -> None:
        """Registrar appid no disponible o dlc deslistado en tienda."""
        self.processed_appids += 1
        self.unavailable_or_dlc += 1

    def registrar_429(self) -> None:
        """Registrar evento de rate limit 429."""
        self.rate_limit_hits_429 += 1

    def registrar_reintento(self) -> None:
        """Registrar reintento por falla de red o servidor."""
        self.network_retry_count += 1

    def registrar_peticion(self) -> None:
        """Registrar solicitud http saliente."""
        self.total_requests += 1

    def sincronizar_contadores_cliente(self, client: Any) -> None:
        """Sincronizar metricas acumuladas en el cliente http si estan expuestas."""
        if hasattr(client, "rate_limit_hits_429"):
            self.rate_limit_hits_429 = getattr(client, "rate_limit_hits_429")
        if hasattr(client, "network_retry_count"):
            self.network_retry_count = getattr(client, "network_retry_count")
        if hasattr(client, "total_requests"):
            self.total_requests = getattr(client, "total_requests")

    def _calcular_bytes_bronce(self) -> int:
        """Calcular peso total en bytes sin comprimir de la particion de bronce."""
        if self.ruta_bronce is None or not self.ruta_bronce.is_dir():
            return 0
        total_bytes = 0
        try:
            for raiz, _, archivos in os.walk(self.ruta_bronce):
                for arch in archivos:
                    #omitir archivos temporales y benchmarks anteriores en calculo de payload
                    if arch.endswith(".tmp") or "benchmark" in arch:
                        continue
                    p = Path(raiz) / arch
                    if p.is_file():
                        total_bytes += p.stat().st_size
        except Exception:
            pass
        return total_bytes

    def _calcular_bytes_tar(self) -> int:
        """Calcular peso comprimido del archivo tar.gz en sync_tar_dir si existe."""
        if self.sync_tar_dir is None:
            return 0
        tar_path = self.sync_tar_dir / f"bronce_worker_{self.worker_id}.tar.gz"
        if tar_path.is_file():
            return tar_path.stat().st_size
        return 0

    def finalizar(self, exit_reason: str = "completed") -> dict[str, Any]:
        """Calcular metricas finales, persistir en disco y retornar estructura determinista."""
        end_time = datetime.now(timezone.utc)
        duration_seconds = max(0.001, (end_time - self.start_time).total_seconds())

        apps_per_minute = round(self.processed_appids / (duration_seconds / 60.0), 2)
        reqs_per_second = round(self.total_requests / duration_seconds, 2)

        payload_bytes = self._calcular_bytes_bronce()
        tar_bytes = self._calcular_bytes_tar()
        compression_ratio = round(payload_bytes / tar_bytes, 2) if tar_bytes > 0 else 1.0

        reporte = {
            "worker_id": self.worker_id,
            "total_workers": self.total_workers,
            "node_environment": self.node_environment,
            "start_time_utc": self.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time_utc": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_duration_seconds": round(duration_seconds, 1),
            "total_assigned_appids": self.total_assigned_appids,
            "processed_appids": self.processed_appids,
            "successful_fetches": self.successful_fetches,
            "unavailable_or_dlc": self.unavailable_or_dlc,
            "rate_limit_hits_429": self.rate_limit_hits_429,
            "network_retry_count": self.network_retry_count,
            "throughput_apps_per_minute": apps_per_minute,
            "throughput_reqs_per_second": reqs_per_second,
            "total_payload_bytes_uncompressed": payload_bytes,
            "total_tar_bytes_compressed": tar_bytes,
            "compression_ratio": compression_ratio,
            "exit_reason": exit_reason,
        }

        #persistir en data/bronce/steam/<fecha>/benchmarks/benchmark_worker_{id}.json
        if self.ruta_bronce is not None:
            dir_benchmarks = self.ruta_bronce / "benchmarks"
            dir_benchmarks.mkdir(parents=True, exist_ok=True)
            ruta_destino = dir_benchmarks / f"benchmark_worker_{self.worker_id}.json"
            ruta_tmp = ruta_destino.with_suffix(".tmp")
            try:
                with open(ruta_tmp, "w", encoding="utf-8") as f:
                    json.dump(reporte, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                os.replace(ruta_tmp, ruta_destino)
            except Exception:
                if ruta_tmp.exists():
                    ruta_tmp.unlink(missing_ok=True)

        return reporte
