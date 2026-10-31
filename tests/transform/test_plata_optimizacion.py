#suite de pruebas de optimizacion de capa plata
#cubre perfil de hardware adaptativo, indexacion ligera de rutas y equivalencia matematica
from pathlib import Path

import pyarrow as pa
import pytest

from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce
from src.transform.plata import (
    PerfilHardware,
    construir_tablas_plata,
    detectar_perfil_hardware,
    indexar_rutas_bronce,
)


def test_detectar_perfil_hardware_gama_baja() -> None:
    """Verificar configuracion para cpus de 1 o 2 hilos (ej. pentium o celeron)."""
    for hilos in (1, 2):
        perfil = detectar_perfil_hardware(hilos_override=hilos)
        assert isinstance(perfil, PerfilHardware)
        assert perfil.hilos_logicos_detectados == hilos
        assert not perfil.usar_multiproceso
        assert perfil.workers_asignados == 1
        assert perfil.batch_size == 1500
        assert "gama_baja" in perfil.categoria_hardware


def test_detectar_perfil_hardware_gama_media() -> None:
    """Verificar configuracion para cpus de 4 a 6 hilos (gama media)."""
    perfil_4 = detectar_perfil_hardware(hilos_override=4)
    assert perfil_4.usar_multiproceso
    assert perfil_4.workers_asignados == 3
    assert perfil_4.batch_size == 3000

    perfil_6 = detectar_perfil_hardware(hilos_override=6)
    assert perfil_6.usar_multiproceso
    assert perfil_6.workers_asignados == 5
    assert perfil_6.batch_size == 3000


def test_detectar_perfil_hardware_gama_alta_ryzen() -> None:
    """Verificar configuracion para cpus de 8 o mas hilos (ej. ryzen 5 8600g con 12 hilos)."""
    perfil_12 = detectar_perfil_hardware(hilos_override=12)
    assert perfil_12.usar_multiproceso
    assert perfil_12.workers_asignados == 10
    assert perfil_12.batch_size == 5000
    assert "alto_rendimiento" in perfil.categoria_hardware or "gama_alta" in perfil.categoria_hardware if (perfil := perfil_12) else True


def test_detectar_perfil_hardware_respeta_techo_workers() -> None:
    """Verificar que el techo max_workers_techo limita la asignacion en maquinas de muchos hilos."""
    perfil = detectar_perfil_hardware(hilos_override=32, max_workers_techo=8)
    assert perfil.workers_asignados == 8


def test_detectar_perfil_hardware_valida_argumentos() -> None:
    """Verificar que techos invalidos levanten ValueError."""
    with pytest.raises(ValueError, match="El techo maximo de workers"):
        detectar_perfil_hardware(hilos_override=8, max_workers_techo=0)


def test_detectar_perfil_hardware_usa_cpu_count_por_defecto() -> None:
    """Verificar que sin override se detecte el cpu del sistema."""
    perfil = detectar_perfil_hardware()
    assert perfil.hilos_logicos_detectados >= 1
    assert perfil.workers_asignados >= 1


def test_indexar_rutas_bronce_sin_cargar_json(tmp_path: Path) -> None:
    """Verificar que indexar_rutas_bronce devuelva rutas Path sin leer payloads a memoria."""
    dir_bronce = tmp_path / "bronce" / "steam" / "appdetails"
    particion_1 = dir_bronce / "fecha=2026-10-18"
    particion_2 = dir_bronce / "fecha=2026-10-28"
    particion_1.mkdir(parents=True)
    particion_2.mkdir(parents=True)

    #crear archivos para appid 100 en fecha 1 y fecha 2
    f1 = particion_1 / "appid=100.json"
    f2 = particion_2 / "appid=100.json"
    f1.write_text('{"payload": "viejo"}', encoding="utf-8")
    f2.write_text('{"payload": "nuevo"}', encoding="utf-8")

    #crear archivo unico para appid 200 en fecha 1
    f3 = particion_1 / "appid=200.json"
    f3.write_text('{"payload": "unico"}', encoding="utf-8")

    #al no especificar fecha la particion mas reciente (2026-10-28) debe prevalecer para appid 100
    indice = indexar_rutas_bronce(ruta_base=tmp_path, recurso="appdetails")
    assert isinstance(indice, dict)
    assert len(indice) == 2
    assert indice[100] == f2
    assert indice[200] == f3


def test_indexar_rutas_bronce_con_fecha_especifica(tmp_path: Path) -> None:
    """Verificar filtrado por particion de fecha especifica."""
    dir_bronce = tmp_path / "bronce" / "steam" / "appreviews_resumen"
    p1 = dir_bronce / "fecha=2026-10-18"
    p2 = dir_bronce / "fecha=2026-10-28"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)

    f1 = p1 / "appid=50.json"
    f2 = p2 / "appid=50.json"
    f1.write_text('{}', encoding="utf-8")
    f2.write_text('{}', encoding="utf-8")

    indice = indexar_rutas_bronce(ruta_base=tmp_path, recurso="appreviews_resumen", fecha="2026-10-18")
    assert len(indice) == 1
    assert indice[50] == f1


def _crear_juego_sintetico(
    base: Path,
    appid: int,
    nombre: str,
    publisher: str,
    engine_desc: str,
    positivas: int = 10,
    negativas: int = 2,
    fecha: str = "2026-10-18",
) -> None:
    """Helper para crear fixtures sinteticos en bronce sin red."""
    details = {
        str(appid): {
            "success": True,
            "data": {
                "name": nombre,
                "release_date": {"date": "15 May, 2024"},
                "is_free": False,
                "price_overview": {"currency": "USD", "initial": 1499},
                "genres": [{"description": "Indie"}],
                "supported_languages": "English*",
                "developers": ["Solo Dev"],
                "publishers": [publisher],
                "detailed_description": f"A game made with {engine_desc}.",
            },
        }
    }
    reviews = {
        "success": 1,
        "query_summary": {
            "total_positive": positivas,
            "total_negative": negativas,
            "total_reviews": positivas + negativas,
        },
    }
    env_det = crear_envoltorio_bronce("steam_appdetails", "https://example.invalid", {}, 200, details, "2026-10-18T00:00:00Z")
    env_rev = crear_envoltorio_bronce("steam_appreviews", "https://example.invalid", {}, 200, reviews, "2026-10-18T00:00:00Z")
    guardar_en_bronce("appdetails", fecha, appid, env_det, ruta_base=base)
    guardar_en_bronce("appreviews_resumen", fecha, appid, env_rev, ruta_base=base)


def test_equivalencia_matematica_secuencial_vs_multiproceso(tmp_path: Path) -> None:
    """Verificar que la ejecucion secuencial y la multiproceso produzcan tablas Arrow bit-identicas."""
    #crear 6 juegos con motores y publishers diversos
    juegos = [
        (10, "Godot Quest", "Indie Pub A", "Godot Engine v4.2", 15, 1),
        (20, "Unreal Shooter", "Indie Pub A", "Unreal Engine 5", 50, 5),
        (30, "Unity Platformer", "Indie Pub B", "Made with Unity 2022", 100, 20),
        (40, "Custom Rogue", "Solo Dev", "Custom C++ engine", 8, 2),
        (50, "Pico Adventure", "Solo Dev", "Pico-8 fantasy console", 4, 0),
        (60, "Renpy Novel", "Novel Studio", "Ren'Py Visual Novel", 30, 3),
    ]
    for aid, nom, pub, eng, pos, neg in juegos:
        _crear_juego_sintetico(tmp_path, aid, nom, pub, eng, pos, neg)

    perfil_sec = PerfilHardware(
        hilos_logicos_detectados=1,
        categoria_hardware="gama_baja_secuencial",
        workers_asignados=1,
        usar_multiproceso=False,
        batch_size=2,
    )
    perfil_par = PerfilHardware(
        hilos_logicos_detectados=4,
        categoria_hardware="gama_media_moderada",
        workers_asignados=2,
        usar_multiproceso=True,
        batch_size=2,
    )

    dim_sec, res_sec = construir_tablas_plata(
        ruta_base=tmp_path,
        modo="masivo",
        perfil_hardware=perfil_sec,
    )
    dim_par, res_par = construir_tablas_plata(
        ruta_base=tmp_path,
        modo="masivo",
        perfil_hardware=perfil_par,
    )

    assert isinstance(dim_sec, pa.Table)
    assert isinstance(dim_par, pa.Table)
    assert dim_sec.num_rows == 6
    assert dim_par.num_rows == 6

    #verificar equivalencia matematica estricta
    assert dim_sec.equals(dim_par)
    assert res_sec.equals(res_par)

    #verificar ordenamiento ascendente por game_id
    ids = dim_par.column("game_id").to_pylist()
    assert ids == [10, 20, 30, 40, 50, 60]
