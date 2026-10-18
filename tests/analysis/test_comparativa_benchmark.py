#suite de pruebas para generacion de comparativa de benchmarking de nodos
#garantias: calculo preciso de aceleracion, agregacion de metricas y formato markdown
import json
from pathlib import Path

from src.analysis.comparativa_benchmark import (
    generar_comparativa_benchmarks,
    generar_reporte_markdown_comparativa,
)


def _crear_benchmark_mock(worker_id: int, env: str, duration: float, apps: int, exito: int, hits_429: int) -> dict:
    return {
        "worker_id": worker_id,
        "total_workers": 2,
        "node_environment": env,
        "start_time_utc": "2026-10-18T14:00:00Z",
        "end_time_utc": "2026-10-18T16:00:00Z",
        "total_duration_seconds": duration,
        "total_assigned_appids": 50000,
        "processed_appids": apps,
        "successful_fetches": exito,
        "unavailable_or_dlc": apps - exito,
        "rate_limit_hits_429": hits_429,
        "network_retry_count": hits_429 + 2,
        "throughput_apps_per_minute": round(apps / (duration / 60.0), 2),
        "throughput_reqs_per_second": round((apps * 2) / duration, 2),
        "total_payload_bytes_uncompressed": apps * 15000,
        "total_tar_bytes_compressed": apps * 2000,
        "compression_ratio": 7.5,
        "exit_reason": "completed",
    }


def test_generar_comparativa_benchmarks(tmp_path: Path) -> None:
    #debe cruzar ambos workers y calcular totales consolidados y ratios relativos
    bm0 = _crear_benchmark_mock(0, "PC Local (Fibra Residencial)", duration=7200.0, apps=20000, exito=19500, hits_429=5)
    bm1 = _crear_benchmark_mock(1, "Google Colab Pro (Google Cloud)", duration=3600.0, apps=20000, exito=19800, hits_429=1)

    ruta_bm0 = tmp_path / "benchmark_worker_0.json"
    ruta_bm1 = tmp_path / "benchmark_worker_1.json"
    ruta_bm0.write_text(json.dumps(bm0), encoding="utf-8")
    ruta_bm1.write_text(json.dumps(bm1), encoding="utf-8")

    res = generar_comparativa_benchmarks(rutas_benchmarks=[ruta_bm0, ruta_bm1])

    assert res["total_workers_analizados"] == 2
    assert res["total_appids_procesados"] == 40000
    assert res["total_exitosos"] == 39300
    assert res["aceleracion_relativa"] > 1.5
    assert len(res["nodos"]) == 2


def test_generar_reporte_markdown_comparativa(tmp_path: Path) -> None:
    #debe producir un reporte en markdown listo para documentacion o publicacion
    bm0 = _crear_benchmark_mock(0, "PC Local (Fibra Residencial)", duration=7200.0, apps=20000, exito=19500, hits_429=5)
    bm1 = _crear_benchmark_mock(1, "Google Colab Pro (Google Cloud)", duration=3600.0, apps=20000, exito=19800, hits_429=1)

    ruta_bm0 = tmp_path / "benchmark_worker_0.json"
    ruta_bm1 = tmp_path / "benchmark_worker_1.json"
    ruta_bm0.write_text(json.dumps(bm0), encoding="utf-8")
    ruta_bm1.write_text(json.dumps(bm1), encoding="utf-8")

    comparativa = generar_comparativa_benchmarks(rutas_benchmarks=[ruta_bm0, ruta_bm1])
    md = generar_reporte_markdown_comparativa(comparativa)

    assert "# Comparativa de Rendimiento de Nodos" in md
    assert "PC Local (Fibra Residencial)" in md
    assert "Google Colab Pro (Google Cloud)" in md
    assert "Aceleración Relativa" in md
