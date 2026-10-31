#modulo de medicion de rendimiento y benchmark comparativo de transformacion
#compara ejecucion monohilo vs streaming adaptativo sobre muestra acotada
import gc
import json
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.transform.plata import (
    PerfilHardware,
    construir_tablas_plata,
    detectar_perfil_hardware,
    indexar_rutas_bronce,
)
from src.version import PIPELINE_VERSION


def _generar_reporte_markdown(datos: dict[str, Any]) -> str:
    """Construir representacion tabular en markdown del benchmark comparativo."""
    ph = datos["perfil_hardware"]
    antes = datos["antes_ansioso_monohilo"]
    despues = datos["despues_streaming_adaptativo"]
    mejora = datos["mejora_relativa"]

    return f"""# Benchmark Comparativo de Transformacion (Bronce -> Plata)

- **Fecha de Medicion:** {datos['fecha_medicion']}
- **Version del Pipeline:** `{datos['version_pipeline']}`
- **Tamano de Muestra:** {datos['tamano_muestra_juegos']} juegos

## Perfil de Hardware Detectado
- **Hilos Logicos:** {ph['hilos_logicos_detectados']}
- **Categoria:** `{ph['categoria_hardware']}`
- **Workers Asignados:** {ph['workers_asignados']}
- **Tamano de Lote (Batch):** {ph['batch_size']}

## Comparativa de Rendimiento

| Metrica | Antes (Ansioso Mono-hilo) | Despues (Streaming Adaptativo) | Factor de Mejora |
| :--- | :---: | :---: | :---: |
| Duracion de Pared | {antes['duracion_segundos']:.2f} s | {despues['duracion_segundos']:.2f} s | **{mejora['speedup_velocidad_x']:.2f}x** mas rapido |
| Throughput | {antes['juegos_por_segundo']:.1f} juegos/s | {despues['juegos_por_segundo']:.1f} juegos/s | +{((despues['juegos_por_segundo'] / max(0.1, antes['juegos_por_segundo'])) - 1.0) * 100:.1f}% |
| Pico de Memoria RAM | {antes['pico_ram_mb']:.2f} MB | {despues['pico_ram_mb']:.2f} MB | **{mejora['reduccion_ram_porcentaje']:.1f}%** ahorro |
| Equivalencia Matematica | Referencia | Identica (`table.equals()`) | {'Verificado' if mejora['equivalencia_exacta_filas'] else 'Fallo'} |
"""


def ejecutar_benchmark_transformacion(
    ruta_base: Path,
    limite_juegos: int = 1000,
    hilos_override: Optional[int] = None,
    ruta_salida_md: Optional[Path] = None,
    ruta_salida_json: Optional[Path] = None,
) -> dict[str, Any]:
    """Medir tiempo y pico de ram antes vs. despues sobre muestra acotada."""
    if limite_juegos < 1:
        raise ValueError("El limite de juegos debe ser al menos 1.")

    rutas_det = indexar_rutas_bronce(ruta_base, "appdetails")
    rutas_res = indexar_rutas_bronce(ruta_base, "appreviews_resumen")
    appids_comunes = sorted(set(rutas_det.keys()) & set(rutas_res.keys()))
    appids_muestra = appids_comunes[:limite_juegos]

    n = len(appids_muestra)
    perfil_adaptativo = detectar_perfil_hardware(hilos_override=hilos_override)
    perfil_secuencial = PerfilHardware(
        hilos_logicos_detectados=1,
        categoria_hardware="gama_baja_secuencial",
        workers_asignados=1,
        usar_multiproceso=False,
        batch_size=max(1, n),
    )

    #fase antes: ejecucion mono-hilo
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    dim_antes, res_antes = construir_tablas_plata(
        ruta_base=ruta_base,
        modo="masivo",
        appids_objetivo=appids_muestra,
        perfil_hardware=perfil_secuencial,
    )
    t1 = time.perf_counter()
    _, peak_antes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    duracion_antes = max(0.0001, t1 - t0)
    ram_antes_mb = round(peak_antes / (1024 * 1024), 2)
    fps_antes = round(n / duracion_antes, 1) if duracion_antes > 0 else 0.0

    #fase despues: ejecucion streaming adaptativo
    gc.collect()
    tracemalloc.start()
    t2 = time.perf_counter()
    dim_despues, res_despues = construir_tablas_plata(
        ruta_base=ruta_base,
        modo="masivo",
        appids_objetivo=appids_muestra,
        perfil_hardware=perfil_adaptativo,
    )
    t3 = time.perf_counter()
    _, peak_despues = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    duracion_despues = max(0.0001, t3 - t2)
    ram_despues_mb = round(peak_despues / (1024 * 1024), 2)
    fps_despues = round(n / duracion_despues, 1) if duracion_despues > 0 else 0.0

    #calculo de metricas comparativas
    speedup = round(duracion_antes / duracion_despues, 2) if duracion_despues > 0 else 1.0
    reduccion_ram = (
        round(max(0.0, (ram_antes_mb - ram_despues_mb) / ram_antes_mb * 100), 2)
        if ram_antes_mb > 0
        else 0.0
    )
    equivalencia = bool(dim_antes.equals(dim_despues) and res_antes.equals(res_despues))

    resultado = {
        "fecha_medicion": datetime.now(timezone.utc).isoformat(),
        "version_pipeline": PIPELINE_VERSION,
        "tamano_muestra_juegos": n,
        "perfil_hardware": {
            "hilos_logicos_detectados": perfil_adaptativo.hilos_logicos_detectados,
            "categoria_hardware": perfil_adaptativo.categoria_hardware,
            "workers_asignados": perfil_adaptativo.workers_asignados,
            "batch_size": perfil_adaptativo.batch_size,
        },
        "antes_ansioso_monohilo": {
            "duracion_segundos": round(duracion_antes, 3),
            "juegos_por_segundo": fps_antes,
            "pico_ram_mb": ram_antes_mb,
        },
        "despues_streaming_adaptativo": {
            "duracion_segundos": round(duracion_despues, 3),
            "juegos_por_segundo": fps_despues,
            "pico_ram_mb": ram_despues_mb,
        },
        "mejora_relativa": {
            "speedup_velocidad_x": speedup,
            "reduccion_ram_porcentaje": reduccion_ram,
            "equivalencia_exacta_filas": equivalencia,
        },
    }

    if ruta_salida_json is not None:
        salida_json = Path(ruta_salida_json)
        salida_json.parent.mkdir(parents=True, exist_ok=True)
        salida_json.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")

    if ruta_salida_md is not None:
        salida_md = Path(ruta_salida_md)
        salida_md.parent.mkdir(parents=True, exist_ok=True)
        salida_md.write_text(_generar_reporte_markdown(resultado), encoding="utf-8")

    return resultado
