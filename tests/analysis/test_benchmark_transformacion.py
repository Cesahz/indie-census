#suite de pruebas para el benchmark de transformacion de capa plata
from pathlib import Path

import pytest

from src.analysis.benchmark_transformacion import ejecutar_benchmark_transformacion
from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce


def _poblar_juegos_prueba(base: Path, cantidad: int = 6) -> None:
    """Helper para crear fixtures sinteticos en bronce sin red."""
    fecha = "2026-10-18"
    for i in range(1, cantidad + 1):
        appid = 1000 + i
        details = {
            str(appid): {
                "success": True,
                "data": {
                    "name": f"Game Benchmark {i}",
                    "release_date": {"date": "10 May, 2024"},
                    "is_free": False,
                    "price_overview": {"currency": "USD", "initial": 999},
                    "genres": [{"description": "Indie"}],
                    "supported_languages": "English",
                    "developers": [f"Dev {i}"],
                    "publishers": ["Common Publisher" if i % 2 == 0 else f"Pub {i}"],
                    "detailed_description": f"Made with Godot Engine for test {i}.",
                },
            }
        }
        reviews = {
            "success": 1,
            "query_summary": {
                "total_positive": i * 10,
                "total_negative": i,
                "total_reviews": i * 11,
            },
        }
        env_det = crear_envoltorio_bronce("steam_appdetails", "https://example.invalid", {}, 200, details, "2026-10-18T00:00:00Z")
        env_rev = crear_envoltorio_bronce("steam_appreviews", "https://example.invalid", {}, 200, reviews, "2026-10-18T00:00:00Z")
        guardar_en_bronce("appdetails", fecha, appid, env_det, ruta_base=base)
        guardar_en_bronce("appreviews_resumen", fecha, appid, env_rev, ruta_base=base)


def test_ejecutar_benchmark_valida_limite_invalido(tmp_path: Path) -> None:
    """Verificar que un limite de juegos menor a 1 levante ValueError."""
    with pytest.raises(ValueError, match="El limite de juegos debe ser al menos 1"):
        ejecutar_benchmark_transformacion(ruta_base=tmp_path, limite_juegos=0)


def test_ejecutar_benchmark_comparativo_hermetico(tmp_path: Path) -> None:
    """Verificar generacion de metricas comparativas y reportes json y markdown."""
    _poblar_juegos_prueba(tmp_path, cantidad=6)

    ruta_json = tmp_path / "reporte.json"
    ruta_md = tmp_path / "reporte.md"

    resultado = ejecutar_benchmark_transformacion(
        ruta_base=tmp_path,
        limite_juegos=6,
        hilos_override=4,
        ruta_salida_md=ruta_md,
        ruta_salida_json=ruta_json,
    )

    assert isinstance(resultado, dict)
    assert resultado["tamano_muestra_juegos"] == 6
    assert "perfil_hardware" in resultado
    assert "antes_ansioso_monohilo" in resultado
    assert "despues_streaming_adaptativo" in resultado
    assert "mejora_relativa" in resultado
    assert resultado["mejora_relativa"]["equivalencia_exacta_filas"] is True

    #verificar persistencia de reportes
    assert ruta_json.exists()
    assert ruta_md.exists()
    assert "Benchmark Comparativo de Transformacion" in ruta_md.read_text(encoding="utf-8")
