#suite de contratos bloqueantes de calidad para la capa plata
#cada contrato tiene al menos un caso valido y un caso de bloqueo comprobado
#sin acceso a red: tablas arrow en memoria y bronce sintetico en tmp_path
from pathlib import Path
from typing import Any, Callable, Optional

import pyarrow as pa
import pytest
import yaml

from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce
from src.quality.contratos import (
    CARDINALIDAD_MUESTRA,
    ContratoCalidadError,
    validar_cardinalidad,
    validar_clasificacion_semantica,
    validar_coherencia_aritmetica,
    validar_coherencia_precio,
    validar_contratos_plata,
    validar_evidencia_motor,
    validar_integridad_referencial,
    validar_no_nulos,
    validar_unicidad,
    validar_ventana_temporal,
)
from src.transform.plata import (
    ESQUEMA_DIM_GAME,
    ESQUEMA_GAME_REVIEW_SUMMARY,
    ejecutar_transformacion_plata,
)

Mutador = Optional[Callable[[list[dict[str, Any]]], None]]


#utilidades de construccion de tablas validas

def _fila_dim(i: int) -> dict[str, Any]:
    """Fila valida de dim_game: pares godot de pago, impares general gratuitos."""
    es_godot = i % 2 == 0
    return {
        "game_id": 1000 + i,
        "title": f"Juego {i}",
        "release_date": f"{2024 + i % 3}-0{1 + i % 9}-1{i % 9}",
        "is_free": not es_godot,
        "price_launch_usd_cents": 1999 if es_godot else None,
        "genres": ["Indie"] if i % 5 else [],
        "language_count": i % 4,
        "developers": ["Dev"],
        "publishers": ["Pub"],
        "group": "godot" if es_godot else "general",
        "engine": "godot" if es_godot else "unity",
        "engine_evidence_level": (1 + (i // 2) % 2) if es_godot else None,
        "indie_score": 0.85 if es_godot else 0.75,
        "is_indie": True,
        "ai_disclosure_level": "unknown",
        "source": "steam.appdetails",
        "extracted_at": "2026-10-01T12:00:00Z",
        "pipeline_version": "0.1.0",
    }


def _fila_resena(i: int) -> dict[str, Any]:
    """Fila valida de game_review_summary con aritmetica coherente."""
    return {
        "game_id": 1000 + i,
        "total_positive": i * 3,
        "total_negative": i,
        "total_reviews": i * 4,
        "extracted_at": "2026-10-01T12:00:00Z",
        "pipeline_version": "0.1.0",
    }


def _tablas(n: int = CARDINALIDAD_MUESTRA, mut_dim: Mutador = None, mut_res: Mutador = None) -> tuple[pa.Table, pa.Table]:
    """Construir tablas plata validas de n juegos aplicando mutaciones opcionales."""
    dim = [_fila_dim(i) for i in range(n)]
    res = [_fila_resena(i) for i in range(n)]
    if mut_dim:
        mut_dim(dim)
    if mut_res:
        mut_res(res)
    return (
        pa.Table.from_pylist(dim, schema=ESQUEMA_DIM_GAME),
        pa.Table.from_pylist(res, schema=ESQUEMA_GAME_REVIEW_SUMMARY),
    )


def _set(indice: int, campo: str, valor: Any) -> Callable[[list[dict[str, Any]]], None]:
    """Mutador que asigna un valor a un campo de una fila."""
    def aplicar(filas: list[dict[str, Any]]) -> None:
        filas[indice][campo] = valor
    return aplicar


#excepcion tipada

def test_contrato_calidad_error_expone_nombre_del_contrato() -> None:
    error = ContratoCalidadError("nulos", "Detalle de prueba")
    assert isinstance(error, Exception)
    assert error.contrato == "nulos"
    assert "nulos" in str(error)
    assert "Detalle de prueba" in str(error)


def test_cardinalidad_muestra_es_cien() -> None:
    assert CARDINALIDAD_MUESTRA == 100


#contrato 1: nulos

def test_nulos_caso_valido() -> None:
    validar_no_nulos(*_tablas())


def test_nulos_caso_valido_acepta_precio_y_evidencia_nulos_en_campos_condicionales() -> None:
    dim, res = _tablas()
    assert dim.column("price_launch_usd_cents").null_count > 0
    assert dim.column("engine_evidence_level").null_count > 0
    validar_no_nulos(dim, res)


@pytest.mark.parametrize("campo", [
    "title", "release_date", "is_free", "genres", "language_count", "developers", "publishers",
    "group", "engine", "indie_score", "is_indie", "ai_disclosure_level", "source", "extracted_at", "pipeline_version",
])
def test_nulos_bloquea_campo_obligatorio_de_dim_game(campo: str) -> None:
    with pytest.raises(ContratoCalidadError, match=campo) as info:
        validar_no_nulos(*_tablas(mut_dim=_set(7, campo, None)))
    assert info.value.contrato == "nulos"


@pytest.mark.parametrize("campo", [
    "total_positive", "total_negative", "total_reviews", "extracted_at", "pipeline_version",
])
def test_nulos_bloquea_campo_obligatorio_de_resenas(campo: str) -> None:
    with pytest.raises(ContratoCalidadError, match=campo):
        validar_no_nulos(*_tablas(mut_res=_set(3, campo, None)))


#contrato 2: duplicidad

def test_unicidad_caso_valido() -> None:
    validar_unicidad(*_tablas())


def test_unicidad_bloquea_duplicado_en_dim_game() -> None:
    with pytest.raises(ContratoCalidadError, match="1000") as info:
        validar_unicidad(*_tablas(mut_dim=_set(1, "game_id", 1000)))
    assert info.value.contrato == "duplicidad"


def test_unicidad_bloquea_duplicado_en_resenas() -> None:
    with pytest.raises(ContratoCalidadError, match="game_review_summary"):
        validar_unicidad(*_tablas(mut_res=_set(1, "game_id", 1000)))


#contrato 3: cardinalidad

def test_cardinalidad_caso_valido() -> None:
    validar_cardinalidad(*_tablas())


def test_cardinalidad_caso_valido_con_esperado_inyectado() -> None:
    validar_cardinalidad(*_tablas(n=3), esperado=3)


@pytest.mark.parametrize("n", [0, 99, 101])
def test_cardinalidad_bloquea_conteo_distinto_de_cien(n: int) -> None:
    with pytest.raises(ContratoCalidadError, match=str(n)) as info:
        validar_cardinalidad(*_tablas(n=n))
    assert info.value.contrato == "cardinalidad"


def test_cardinalidad_bloquea_resenas_incompletas() -> None:
    with pytest.raises(ContratoCalidadError, match="game_review_summary"):
        validar_cardinalidad(*_tablas(mut_res=lambda filas: filas.pop()))


#contrato 4: integridad referencial

def test_integridad_referencial_caso_valido() -> None:
    validar_integridad_referencial(*_tablas())


def test_integridad_referencial_bloquea_resena_huerfana() -> None:
    with pytest.raises(ContratoCalidadError, match="999999") as info:
        validar_integridad_referencial(*_tablas(mut_res=_set(0, "game_id", 999999)))
    assert info.value.contrato == "integridad_referencial"


def test_integridad_referencial_bloquea_juego_sin_resena() -> None:
    with pytest.raises(ContratoCalidadError, match="1099"):
        validar_integridad_referencial(*_tablas(mut_res=lambda filas: filas.pop()))


#contrato 5: ventana temporal

def test_ventana_temporal_caso_valido_incluye_bordes() -> None:
    def bordes(filas: list[dict[str, Any]]) -> None:
        filas[0]["release_date"] = "2024-01-01"
        filas[1]["release_date"] = "2026-12-31"
    validar_ventana_temporal(*_tablas(mut_dim=bordes))


@pytest.mark.parametrize("fecha", ["2023-12-31", "2027-01-01", "29 May, 2024", "2025-02-30"])
def test_ventana_temporal_bloquea_fuera_de_rango_o_formato_invalido(fecha: str) -> None:
    with pytest.raises(ContratoCalidadError, match="1004") as info:
        validar_ventana_temporal(*_tablas(mut_dim=_set(4, "release_date", fecha)))
    assert info.value.contrato == "ventana_temporal"


#contrato 6: coherencia aritmetica

def test_coherencia_aritmetica_caso_valido_incluye_juego_sin_resenas() -> None:
    dim, res = _tablas()
    assert res.column("total_reviews")[0].as_py() == 0
    validar_coherencia_aritmetica(dim, res)


def test_coherencia_aritmetica_bloquea_suma_incoherente() -> None:
    with pytest.raises(ContratoCalidadError, match="1005") as info:
        validar_coherencia_aritmetica(*_tablas(mut_res=_set(5, "total_reviews", 1)))
    assert info.value.contrato == "coherencia_aritmetica"


@pytest.mark.parametrize("campo", ["total_positive", "total_negative"])
def test_coherencia_aritmetica_bloquea_conteos_negativos(campo: str) -> None:
    def negativo(filas: list[dict[str, Any]]) -> None:
        filas[2][campo] = -1
        filas[2]["total_reviews"] = filas[2]["total_positive"] + filas[2]["total_negative"]
    with pytest.raises(ContratoCalidadError, match="1002"):
        validar_coherencia_aritmetica(*_tablas(mut_res=negativo))


def test_coherencia_aritmetica_bloquea_language_count_negativo() -> None:
    with pytest.raises(ContratoCalidadError, match="language_count"):
        validar_coherencia_aritmetica(*_tablas(mut_dim=_set(6, "language_count", -1)))


#contrato 7: coherencia de precio

def test_coherencia_precio_caso_valido_acepta_gratuito_con_cero() -> None:
    validar_coherencia_precio(*_tablas(mut_dim=_set(1, "price_launch_usd_cents", 0)))


def test_coherencia_precio_bloquea_pago_sin_precio() -> None:
    with pytest.raises(ContratoCalidadError, match="1000") as info:
        validar_coherencia_precio(*_tablas(mut_dim=_set(0, "price_launch_usd_cents", None)))
    assert info.value.contrato == "coherencia_precio"


def test_coherencia_precio_bloquea_gratuito_con_precio_positivo() -> None:
    with pytest.raises(ContratoCalidadError, match="1001"):
        validar_coherencia_precio(*_tablas(mut_dim=_set(1, "price_launch_usd_cents", 499)))


def test_coherencia_precio_bloquea_precio_negativo() -> None:
    with pytest.raises(ContratoCalidadError, match="1000"):
        validar_coherencia_precio(*_tablas(mut_dim=_set(0, "price_launch_usd_cents", -100)))


#contrato 8: evidencia de motor

def test_evidencia_motor_caso_valido_niveles_uno_y_dos() -> None:
    dim, res = _tablas()
    niveles = {
        f["engine_evidence_level"] for f in dim.to_pylist() if f["group"] == "godot"
    }
    assert niveles == {1, 2}
    validar_evidencia_motor(dim, res)


@pytest.mark.parametrize("nivel", [None, 0, 3])
def test_evidencia_motor_bloquea_godot_sin_nivel_valido(nivel: Optional[int]) -> None:
    with pytest.raises(ContratoCalidadError, match="1000") as info:
        validar_evidencia_motor(*_tablas(mut_dim=_set(0, "engine_evidence_level", nivel)))
    assert info.value.contrato == "evidencia_motor"


def test_evidencia_motor_bloquea_grupo_desconocido() -> None:
    with pytest.raises(ContratoCalidadError, match="unity"):
        validar_evidencia_motor(*_tablas(mut_dim=_set(1, "group", "unity")))


#contrato 9: clasificacion semantica

def test_clasificacion_semantica_caso_valido() -> None:
    validar_clasificacion_semantica(*_tablas())


def test_clasificacion_semantica_bloquea_motor_invalido() -> None:
    with pytest.raises(ContratoCalidadError, match="motor_inexistente") as info:
        validar_clasificacion_semantica(*_tablas(mut_dim=_set(1, "engine", "motor_inexistente")))
    assert info.value.contrato == "clasificacion_semantica"


def test_clasificacion_semantica_bloquea_indie_score_fuera_de_rango() -> None:
    with pytest.raises(ContratoCalidadError, match="indie_score") as info:
        validar_clasificacion_semantica(*_tablas(mut_dim=_set(2, "indie_score", 1.5)))
    assert info.value.contrato == "clasificacion_semantica"


def test_clasificacion_semantica_bloquea_is_indie_no_booleano() -> None:
    dim, res = _tablas()
    col_invalida = pa.array(["no_bool"] * dim.num_rows, type=pa.string())
    idx = dim.schema.get_field_index("is_indie")
    dim_invalida = dim.set_column(idx, "is_indie", col_invalida)
    with pytest.raises(ContratoCalidadError, match="is_indie") as info:
        validar_clasificacion_semantica(dim_invalida, res)
    assert info.value.contrato == "clasificacion_semantica"


def test_clasificacion_semantica_bloquea_ai_disclosure_invalido() -> None:
    with pytest.raises(ContratoCalidadError, match="ai_disclosure_level") as info:
        validar_clasificacion_semantica(*_tablas(mut_dim=_set(4, "ai_disclosure_level", "inventado")))
    assert info.value.contrato == "clasificacion_semantica"


def test_clasificacion_semantica_bloquea_grupo_godot_con_otro_motor() -> None:
    with pytest.raises(ContratoCalidadError, match="engine != 'godot'") as info:
        #juego 0 es grupo godot pero mutamos su engine a unity
        validar_clasificacion_semantica(*_tablas(mut_dim=_set(0, "engine", "unity")))
    assert info.value.contrato == "clasificacion_semantica"


#ejecucion conjunta

def test_validar_contratos_plata_caso_valido() -> None:
    validar_contratos_plata(*_tablas())


def test_validar_contratos_plata_bloquea_al_primer_contrato_violado() -> None:
    with pytest.raises(ContratoCalidadError) as info:
        validar_contratos_plata(*_tablas(mut_res=_set(5, "total_reviews", 1)))
    assert info.value.contrato == "coherencia_aritmetica"


def test_validar_contratos_plata_cardinalidad_inyectable() -> None:
    validar_contratos_plata(*_tablas(n=4), cardinalidad_esperada=4)
    with pytest.raises(ContratoCalidadError):
        validar_contratos_plata(*_tablas(n=4))


#contencion atomica: un contrato fallido no deja archivos en plata

def _envoltorio(fuente: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Construir envoltorio de bronce con marca temporal fija."""
    return crear_envoltorio_bronce(
        fuente=fuente, url_solicitada="https://example.invalid", parametros={},
        estado_http=200, payload=payload, extraido_en="2026-10-01T12:00:00Z",
    )


def _poblar_bronce(base: Path, fecha: str, total_reviews_juego_2: int) -> Path:
    """Crear bronce de dos juegos y su manifiesto; el segundo con total de resenas configurable."""
    juegos = [
        {"appid": 1, "grupo": "godot", "titulo": "Uno", "release_date": "2025-01-01", "evidencia_nivel": 1},
        {"appid": 2, "grupo": "general", "titulo": "Dos", "release_date": "2025-02-01", "evidencia_nivel": None},
    ]
    for juego in juegos:
        appid = juego["appid"]
        details = {str(appid): {"success": True, "data": {
            "name": juego["titulo"], "is_free": appid == 2,
            "release_date": {"coming_soon": False, "date": juego["release_date"]},
            "price_overview": {"currency": "USD", "initial": 999, "final": 999},
            "genres": [], "developers": ["Dev"], "publishers": ["Pub"],
            "supported_languages": "English",
        }}}
        total = total_reviews_juego_2 if appid == 2 else 5
        reviews = {"success": 1, "query_summary": {
            "total_positive": 4 if appid == 1 else 1,
            "total_negative": 1 if appid == 1 else 1,
            "total_reviews": total,
        }}
        guardar_en_bronce("appdetails", fecha, appid, _envoltorio("steam.appdetails", details), ruta_base=base)
        guardar_en_bronce(
            "appreviews_resumen", fecha, appid,
            _envoltorio("steam.appreviews_resumen", reviews), ruta_base=base,
        )
    manifiesto = base / "muestra.yaml"
    manifiesto.write_text(yaml.safe_dump({"juegos": juegos}), encoding="utf-8")
    return manifiesto


def _validador_dos(dim: pa.Table, res: pa.Table) -> None:
    """Validador completo con cardinalidad ajustada al escenario reducido."""
    validar_contratos_plata(dim, res, cardinalidad_esperada=2)


def test_contencion_caso_valido_persiste_plata(tmp_path: Path) -> None:
    manifiesto = _poblar_bronce(tmp_path, "2026-10-01", total_reviews_juego_2=2)
    resultado = ejecutar_transformacion_plata(
        ruta_base=tmp_path, ruta_manifiesto=manifiesto, fecha="2026-10-01", validador=_validador_dos,
    )
    assert resultado["dim_game"].exists()
    assert resultado["game_review_summary"].exists()


def test_contencion_contrato_fallido_no_crea_archivos_en_plata(tmp_path: Path) -> None:
    manifiesto = _poblar_bronce(tmp_path, "2026-10-01", total_reviews_juego_2=99)
    with pytest.raises(ContratoCalidadError, match="coherencia_aritmetica"):
        ejecutar_transformacion_plata(
            ruta_base=tmp_path, ruta_manifiesto=manifiesto, fecha="2026-10-01", validador=_validador_dos,
        )
    plata = tmp_path / "plata"
    assert not plata.exists() or not [p for p in plata.rglob("*") if p.is_file()]


def test_contencion_contrato_fallido_preserva_plata_valida_previa(tmp_path: Path) -> None:
    manifiesto = _poblar_bronce(tmp_path, "2026-10-01", total_reviews_juego_2=2)
    rutas = ejecutar_transformacion_plata(
        ruta_base=tmp_path, ruta_manifiesto=manifiesto, fecha="2026-10-01", validador=_validador_dos,
    )
    contenido_previo = {
        nombre: rutas[nombre].read_bytes() for nombre in ("dim_game", "game_review_summary")
    }
    _poblar_bronce(tmp_path, "2026-10-02", total_reviews_juego_2=99)
    with pytest.raises(ContratoCalidadError):
        ejecutar_transformacion_plata(
            ruta_base=tmp_path, ruta_manifiesto=manifiesto, fecha="2026-10-02", validador=_validador_dos,
        )
    archivos = sorted(p.name for p in (tmp_path / "plata" / "steam").iterdir())
    assert archivos == ["dim_game.parquet", "game_review_summary.parquet"]
    for nombre, contenido in contenido_previo.items():
        assert rutas[nombre].read_bytes() == contenido


def test_validar_contratos_plata_modo_masivo_admite_fechas_historicas() -> None:
    #en modo masivo la ventana temporal admite el catalogo historico desde 1997
    def fecha_historica(filas: list[dict[str, Any]]) -> None:
        filas[0]["release_date"] = "1999-04-01"
        filas[1]["release_date"] = "2000-11-01"

    dim, res = _tablas(mut_dim=fecha_historica)
    #en modo control debe fallar por violacion de ventana temporal
    with pytest.raises(ContratoCalidadError, match="ventana_temporal"):
        validar_contratos_plata(dim, res, cardinalidad_esperada=dim.num_rows, modo="control")

    #en modo masivo debe ser valido y no levantar excepcion
    validar_contratos_plata(dim, res, cardinalidad_esperada=dim.num_rows, modo="masivo")
