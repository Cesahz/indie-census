#suite de contrato para la transformacion determinista de bronce a capa plata
#sin acceso a red: bronce sintetico construido en tmp_path con fixtures locales
import json
from pathlib import Path
from typing import Any, Optional

# pyrefly: ignore [missing-import]
import pyarrow as pa
# pyrefly: ignore [missing-import]
import pyarrow.parquet as pq
# pyrefly: ignore [missing-import]
import pytest
import yaml

from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce
from src.transform import plata
from src.transform.plata import (
    ESQUEMA_DIM_GAME,
    ESQUEMA_GAME_REVIEW_SUMMARY,
    construir_tablas_plata,
    contar_idiomas,
    ejecutar_transformacion_plata,
    leer_particion_bronce,
    parsear_appdetails,
    parsear_appreviews,
    parsear_fecha_steam,
    persistir_plata,
)
from src.version import PIPELINE_VERSION

RUTA_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "steam"
EXTRAIDO_EN = "2026-10-01T12:00:00Z"
FECHA = "2026-10-01"


#utilidades de construccion de bronce sintetico

def _cargar_fixture(nombre: str) -> dict[str, Any]:
    """Leer un fixture json de steam desde el directorio de pruebas."""
    return json.loads((RUTA_FIXTURES / nombre).read_text(encoding="utf-8"))


def _envoltorio(fuente: str, payload: dict[str, Any], extraido_en: str = EXTRAIDO_EN) -> dict[str, Any]:
    """Construir envoltorio de bronce con marca temporal fija."""
    return crear_envoltorio_bronce(
        fuente=fuente,
        url_solicitada="https://example.invalid",
        parametros={},
        estado_http=200,
        payload=payload,
        extraido_en=extraido_en,
    )


def _payload_details(
    appid: int,
    nombre: str = "Juego",
    es_gratis: bool = False,
    precio: Optional[int] = 1999,
    fecha: str = "29 May, 2024",
    generos: Optional[list[str]] = None,
    desarrolladores: Optional[list[str]] = None,
    idiomas: Optional[str] = "English, French",
) -> dict[str, Any]:
    """Construir payload sintetico de appdetails con la forma real de steam."""
    data: dict[str, Any] = {
        "type": "game",
        "name": nombre,
        "steam_appid": appid,
        "is_free": es_gratis,
        "release_date": {"coming_soon": False, "date": fecha},
        "developers": desarrolladores if desarrolladores is not None else ["Dev"],
        "publishers": ["Pub"],
    }
    if precio is not None:
        data["price_overview"] = {"currency": "USD", "initial": precio, "final": precio}
    if generos is not None:
        data["genres"] = [{"id": str(i), "description": g} for i, g in enumerate(generos)]
    if idiomas is not None:
        data["supported_languages"] = idiomas
    return {str(appid): {"success": True, "data": data}}


def _payload_reviews(positivas: int = 10, negativas: int = 2) -> dict[str, Any]:
    """Construir payload sintetico de appreviews con query_summary."""
    return {
        "success": 1,
        "query_summary": {
            "num_reviews": 0,
            "total_positive": positivas,
            "total_negative": negativas,
            "total_reviews": positivas + negativas,
        },
    }


def _escribir_manifiesto(ruta: Path, juegos: list[dict[str, Any]]) -> Path:
    """Persistir un manifiesto reducido de muestra de control."""
    ruta.write_text(yaml.safe_dump({"juegos": juegos}), encoding="utf-8")
    return ruta


def _poblar_bronce(base: Path, appid: int, details: dict, reviews: Optional[dict], fecha: str = FECHA) -> None:
    """Guardar appdetails y appreviews de un juego en la capa bronce."""
    guardar_en_bronce("appdetails", fecha, appid, _envoltorio("steam.appdetails", details), ruta_base=base)
    if reviews is not None:
        guardar_en_bronce(
            "appreviews_resumen", fecha, appid,
            _envoltorio("steam.appreviews_resumen", reviews), ruta_base=base,
        )


@pytest.fixture
def escenario(tmp_path: Path) -> dict[str, Path]:
    """Escenario minimo: un juego godot de pago, uno general gratuito y uno sin resenas."""
    manifiesto = _escribir_manifiesto(tmp_path / "muestra.yaml", [
        {"appid": 1809540, "grupo": "godot", "titulo": "Nine Sols", "release_date": "2024-05-29",
         "evidencia_nivel": 1},
        {"appid": 200, "grupo": "general", "titulo": "Gratis", "release_date": "2025-01-15",
         "evidencia_nivel": None},
        {"appid": 300, "grupo": "godot", "titulo": "Manifiesto 300", "release_date": "2026-03-10",
         "evidencia_nivel": 2},
    ])
    _poblar_bronce(
        tmp_path, 1809540,
        _cargar_fixture("appdetails_success_1809540.json"),
        _cargar_fixture("appreviews_success_1809540.json"),
    )
    _poblar_bronce(
        tmp_path, 200,
        _payload_details(200, nombre="Gratis", es_gratis=True, precio=None, fecha="Jan 15, 2025",
                         generos=["Action", "Indie"]),
        _payload_details_reviews_vacias(),
    )
    _poblar_bronce(
        tmp_path, 300,
        _payload_details(300, nombre="Sin Fecha", fecha="Coming soon", generos=[], desarrolladores=[],
                         idiomas=None),
        _payload_reviews(0, 0),
    )
    return {"base": tmp_path, "manifiesto": manifiesto}


def _payload_details_reviews_vacias() -> dict[str, Any]:
    """Payload de resenas de un juego sin resenas registradas (query_summary sin totales)."""
    return {"success": 1, "query_summary": {"num_reviews": 0}}


#parseo de fechas de steam

@pytest.mark.parametrize("texto, esperado", [
    ("29 May, 2024", "2024-05-29"),
    ("May 29, 2024", "2024-05-29"),
    ("29 May 2024", "2024-05-29"),
    ("3 Sep, 2025", "2025-09-03"),
    ("3 Sept, 2025", "2025-09-03"),
    ("Sep 3, 2025", "2025-09-03"),
    ("1 January, 2026", "2026-01-01"),
    ("December 31, 2026", "2026-12-31"),
    ("29 may, 2024", "2024-05-29"),
    ("2024-05-29", "2024-05-29"),
    ("  2024-05-29  ", "2024-05-29"),
])
def test_parsear_fecha_steam_formatos_validos(texto: str, esperado: str) -> None:
    assert parsear_fecha_steam(texto) == esperado


@pytest.mark.parametrize("texto", [
    None, "", "Coming soon", "To be announced", "Q2 2025", "31 Feb, 2025", "Mayo 29, 2024", "2024-13-01",
])
def test_parsear_fecha_steam_formatos_invalidos_retornan_none(texto: Optional[str]) -> None:
    assert parsear_fecha_steam(texto) is None


#conteo de idiomas soportados

@pytest.mark.parametrize("texto, esperado", [
    (None, 0),
    ("", 0),
    ("English", 1),
    ("English, French, German", 3),
    ("English<strong>*</strong>, Japanese<strong>*</strong><br><strong>*</strong>languages with full audio support", 2),
])
def test_contar_idiomas(texto: Optional[str], esperado: int) -> None:
    assert contar_idiomas(texto) == esperado


#parseo de appdetails

def test_parsear_appdetails_juego_de_pago_desde_fixture() -> None:
    env = _envoltorio("steam.appdetails", _cargar_fixture("appdetails_success_1809540.json"))
    fila = parsear_appdetails(env, 1809540)
    assert fila["game_id"] == 1809540
    assert fila["title"] == "Nine Sols"
    assert fila["release_date"] == "2024-05-29"
    assert fila["is_free"] is False
    assert fila["price_launch_usd_cents"] == 2999
    assert isinstance(fila["price_launch_usd_cents"], int)
    assert fila["developers"] == ["Red Candle Games"]
    assert fila["publishers"] == ["Red Candle Games"]
    assert fila["genres"] == []
    assert fila["language_count"] == 0
    assert fila["source"] == "steam.appdetails"
    assert fila["extracted_at"] == EXTRAIDO_EN


def test_parsear_appdetails_juego_gratuito_sin_precio() -> None:
    env = _envoltorio("steam.appdetails", _payload_details(5, es_gratis=True, precio=None))
    fila = parsear_appdetails(env, 5)
    assert fila["is_free"] is True
    assert fila["price_launch_usd_cents"] is None


def test_parsear_appdetails_juego_gratuito_con_precio_cero_se_normaliza_a_nulo() -> None:
    env = _envoltorio("steam.appdetails", _payload_details(5, es_gratis=True, precio=0))
    assert parsear_appdetails(env, 5)["price_launch_usd_cents"] is None


def test_parsear_appdetails_moneda_distinta_de_usd_no_se_asume() -> None:
    payload = _payload_details(6, precio=1500)
    payload["6"]["data"]["price_overview"]["currency"] = "EUR"
    env = _envoltorio("steam.appdetails", payload)
    assert parsear_appdetails(env, 6)["price_launch_usd_cents"] is None


def test_parsear_appdetails_listas_vacias_y_claves_ausentes() -> None:
    payload = _payload_details(7, generos=None, desarrolladores=[], idiomas=None)
    del payload["7"]["data"]["publishers"]
    fila = parsear_appdetails(_envoltorio("steam.appdetails", payload), 7)
    assert fila["genres"] == []
    assert fila["developers"] == []
    assert fila["publishers"] == []
    assert fila["language_count"] == 0


def test_parsear_appdetails_generos_e_idiomas() -> None:
    payload = _payload_details(8, generos=["Action", "Indie"], idiomas="English, Spanish - Spain, Japanese")
    fila = parsear_appdetails(_envoltorio("steam.appdetails", payload), 8)
    assert fila["genres"] == ["Action", "Indie"]
    assert fila["language_count"] == 3


def test_parsear_appdetails_extrae_categories() -> None:
    #extraer categorias formales de tienda desde el campo categories
    payload = _payload_details(81)
    payload["81"]["data"]["categories"] = [
        {"id": 2, "description": "Single-player"},
        {"id": 1, "description": "Multi-player"},
    ]
    fila = parsear_appdetails(_envoltorio("steam.appdetails", payload), 81)
    assert fila["_categories"] == ["Single-player", "Multi-player"]



def test_parsear_appdetails_fecha_no_parseable_retorna_none() -> None:
    payload = _payload_details(9, fecha="Coming soon")
    assert parsear_appdetails(_envoltorio("steam.appdetails", payload), 9)["release_date"] is None


def test_parsear_appdetails_respuesta_fallida_lanza_error() -> None:
    env = _envoltorio("steam.appdetails", _cargar_fixture("appdetails_failed_9999999.json"))
    with pytest.raises(ValueError, match="9999999"):
        parsear_appdetails(env, 9999999)


def test_parsear_appdetails_appid_ausente_en_payload_lanza_error() -> None:
    env = _envoltorio("steam.appdetails", _payload_details(10))
    with pytest.raises(ValueError):
        parsear_appdetails(env, 11)


#parseo de appreviews

def test_parsear_appreviews_desde_fixture() -> None:
    env = _envoltorio("steam.appreviews_resumen", _cargar_fixture("appreviews_success_1809540.json"))
    fila = parsear_appreviews(env, 1809540)
    assert fila == {
        "game_id": 1809540,
        "total_positive": 14500,
        "total_negative": 650,
        "total_reviews": 15150,
        "extracted_at": EXTRAIDO_EN,
    }


def test_parsear_appreviews_juego_sin_resenas_retorna_ceros() -> None:
    env = _envoltorio("steam.appreviews_resumen", _payload_details_reviews_vacias())
    fila = parsear_appreviews(env, 42)
    assert (fila["total_positive"], fila["total_negative"], fila["total_reviews"]) == (0, 0, 0)


def test_parsear_appreviews_respuesta_fallida_lanza_error() -> None:
    env = _envoltorio("steam.appreviews_resumen", {"success": 2})
    with pytest.raises(ValueError, match="42"):
        parsear_appreviews(env, 42)


#lectura de particiones de bronce

def test_leer_particion_bronce_directorio_inexistente_retorna_vacio(tmp_path: Path) -> None:
    assert leer_particion_bronce(tmp_path, "appdetails") == {}


def test_leer_particion_bronce_filtra_por_fecha(tmp_path: Path) -> None:
    _poblar_bronce(tmp_path, 1, _payload_details(1, nombre="Viejo"), None, fecha="2026-09-01")
    _poblar_bronce(tmp_path, 2, _payload_details(2, nombre="Nuevo"), None, fecha="2026-10-01")
    resultado = leer_particion_bronce(tmp_path, "appdetails", fecha="2026-09-01")
    assert set(resultado) == {1}


def test_leer_particion_bronce_sin_fecha_prioriza_particion_mas_reciente(tmp_path: Path) -> None:
    _poblar_bronce(tmp_path, 1, _payload_details(1, nombre="Viejo"), None, fecha="2026-09-01")
    _poblar_bronce(tmp_path, 1, _payload_details(1, nombre="Nuevo"), None, fecha="2026-10-01")
    resultado = leer_particion_bronce(tmp_path, "appdetails")
    assert resultado[1]["payload"]["1"]["data"]["name"] == "Nuevo"


#construccion de tablas arrow

def test_construir_tablas_respeta_esquemas_explicitos(escenario: dict[str, Path]) -> None:
    dim, resenas = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    assert dim.schema.equals(ESQUEMA_DIM_GAME)
    assert resenas.schema.equals(ESQUEMA_GAME_REVIEW_SUMMARY)
    assert dim.num_rows == 3
    assert resenas.num_rows == 3


def test_esquema_dim_game_tipos_declarados() -> None:
    assert ESQUEMA_DIM_GAME.field("game_id").type == pa.int64()
    assert ESQUEMA_DIM_GAME.field("is_free").type == pa.bool_()
    assert ESQUEMA_DIM_GAME.field("price_launch_usd_cents").type == pa.int64()
    assert ESQUEMA_DIM_GAME.field("genres").type == pa.list_(pa.string())
    assert ESQUEMA_DIM_GAME.field("language_count").type == pa.int32()
    assert ESQUEMA_DIM_GAME.field("engine").type == pa.string()
    assert ESQUEMA_DIM_GAME.field("engine_evidence_level").type == pa.int8()
    assert ESQUEMA_DIM_GAME.field("indie_score").type == pa.float64()
    assert ESQUEMA_DIM_GAME.field("is_indie").type == pa.bool_()
    assert ESQUEMA_DIM_GAME.field("ai_disclosure_level").type == pa.string()
    assert ESQUEMA_GAME_REVIEW_SUMMARY.names == [
        "game_id", "total_positive", "total_negative", "total_reviews", "extracted_at", "pipeline_version",
    ]


def test_construir_tablas_enriquece_con_manifiesto(escenario: dict[str, Path]) -> None:
    dim, _ = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    filas = {f["game_id"]: f for f in dim.to_pylist()}
    assert filas[1809540]["group"] == "godot"
    assert filas[1809540]["engine"] == "godot"
    assert filas[1809540]["engine_evidence_level"] == 1
    assert 0.0 <= filas[1809540]["indie_score"] <= 1.0
    assert isinstance(filas[1809540]["is_indie"], bool)
    assert filas[1809540]["ai_disclosure_level"] in ("declared", "tagged", "self_reported", "unknown")
    assert filas[200]["group"] == "general"
    assert filas[200]["engine_evidence_level"] is None
    assert filas[300]["engine_evidence_level"] == 2
    assert all(f["pipeline_version"] == PIPELINE_VERSION for f in filas.values())


def test_construir_tablas_casos_borde(escenario: dict[str, Path]) -> None:
    dim, resenas = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    filas = {f["game_id"]: f for f in dim.to_pylist()}
    #juego gratuito sin precio
    assert filas[200]["is_free"] is True
    assert filas[200]["price_launch_usd_cents"] is None
    assert filas[200]["release_date"] == "2025-01-15"
    assert filas[200]["genres"] == ["Action", "Indie"]
    #fecha no parseable en steam recurre al manifiesto curado
    assert filas[300]["release_date"] == "2026-03-10"
    assert filas[300]["genres"] == []
    assert filas[300]["developers"] == []
    #juego sin resenas
    conteos = {f["game_id"]: f for f in resenas.to_pylist()}
    assert conteos[200]["total_reviews"] == 0
    assert conteos[300]["total_reviews"] == 0
    assert conteos[1809540]["total_reviews"] == 15150


def test_construir_tablas_ordenadas_por_game_id_y_deterministas(escenario: dict[str, Path]) -> None:
    dim_a, res_a = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    dim_b, res_b = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    assert dim_a.column("game_id").to_pylist() == [200, 300, 1809540]
    assert dim_a.equals(dim_b)
    assert res_a.equals(res_b)


def test_construir_tablas_omite_juegos_sin_bronce_o_fallidos(tmp_path: Path) -> None:
    manifiesto = _escribir_manifiesto(tmp_path / "m.yaml", [
        {"appid": 1, "grupo": "general", "titulo": "Ok", "release_date": "2025-01-01", "evidencia_nivel": None},
        {"appid": 2, "grupo": "general", "titulo": "Ausente", "release_date": "2025-01-01",
         "evidencia_nivel": None},
        {"appid": 9999999, "grupo": "general", "titulo": "Fallido", "release_date": "2025-01-01",
         "evidencia_nivel": None},
    ])
    _poblar_bronce(tmp_path, 1, _payload_details(1), _payload_reviews())
    _poblar_bronce(
        tmp_path, 9999999, _cargar_fixture("appdetails_failed_9999999.json"), {"success": 2},
    )
    dim, resenas = construir_tablas_plata(tmp_path, manifiesto, fecha=FECHA)
    assert dim.column("game_id").to_pylist() == [1]
    assert resenas.column("game_id").to_pylist() == [1]


def test_construir_tablas_version_pipeline_inyectable(escenario: dict[str, Path]) -> None:
    dim, resenas = construir_tablas_plata(
        escenario["base"], escenario["manifiesto"], fecha=FECHA, version_pipeline="9.9.9",
    )
    assert set(dim.column("pipeline_version").to_pylist()) == {"9.9.9"}
    assert set(resenas.column("pipeline_version").to_pylist()) == {"9.9.9"}


#persistencia atomica en parquet

def test_persistir_plata_escribe_parquet_legible(escenario: dict[str, Path]) -> None:
    dim, resenas = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    rutas = persistir_plata(dim, resenas, ruta_base=escenario["base"])
    directorio = escenario["base"] / "plata" / "steam"
    assert rutas["dim_game"] == directorio / "dim_game.parquet"
    assert rutas["game_review_summary"] == directorio / "game_review_summary.parquet"
    assert pq.read_table(rutas["dim_game"]).equals(dim)
    assert pq.read_table(rutas["game_review_summary"]).equals(resenas)
    assert not list(directorio.glob("*.tmp"))


def test_persistir_plata_falla_no_deja_archivos_parciales(
    escenario: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    dim, resenas = construir_tablas_plata(escenario["base"], escenario["manifiesto"], fecha=FECHA)
    escritor_real = pq.write_table
    llamadas = {"n": 0}

    def escritor_fallido(*args: Any, **kwargs: Any) -> None:
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise OSError("Disco lleno simulado")
        escritor_real(*args, **kwargs)

    monkeypatch.setattr(plata.pq, "write_table", escritor_fallido)
    with pytest.raises(OSError, match="Disco lleno"):
        persistir_plata(dim, resenas, ruta_base=escenario["base"])
    directorio = escenario["base"] / "plata" / "steam"
    assert list(directorio.iterdir()) == []


#orquestacion de la transformacion

def test_ejecutar_transformacion_plata_persiste_y_reporta(escenario: dict[str, Path]) -> None:
    resultado = ejecutar_transformacion_plata(
        ruta_base=escenario["base"], ruta_manifiesto=escenario["manifiesto"], fecha=FECHA,
    )
    assert resultado["filas_dim_game"] == 3
    assert resultado["filas_game_review_summary"] == 3
    assert resultado["dim_game"].exists()
    assert resultado["game_review_summary"].exists()


def test_ejecutar_transformacion_plata_invoca_validador_antes_de_persistir(escenario: dict[str, Path]) -> None:
    recibido: dict[str, Any] = {}

    def validador(dim: pa.Table, resenas: pa.Table) -> None:
        recibido["filas"] = (dim.num_rows, resenas.num_rows)
        raise RuntimeError("Validacion rechazada")

    with pytest.raises(RuntimeError, match="Validacion rechazada"):
        ejecutar_transformacion_plata(
            ruta_base=escenario["base"], ruta_manifiesto=escenario["manifiesto"], fecha=FECHA,
            validador=validador,
        )
    assert recibido["filas"] == (3, 3)
    assert not (escenario["base"] / "plata").exists()


def test_construir_tablas_calcula_y_pasa_titulos_del_publisher(tmp_path: Path) -> None:
    #verificar que el conteo consolidado de titulos por publisher se calcula y penaliza catalogos masivos
    fecha = "2026-10-01"
    #crear 28 juegos del mismo publisher 'MegaCorp Distribution' (>25 titulos)
    appids = list(range(901, 929))
    juegos_man = []
    for aid in appids:
        payload = _payload_details(aid, nombre=f"Juego {aid}", precio=999, generos=["Indie"])
        payload[str(aid)]["data"]["publishers"] = ["MegaCorp Distribution"]
        payload[str(aid)]["data"]["developers"] = ["MegaCorp Dev"]
        _poblar_bronce(tmp_path, aid, payload, _payload_reviews(10, 1), fecha=fecha)
        juegos_man.append({"appid": aid, "grupo": "general", "titulo": f"Juego {aid}", "release_date": "2024-05-29"})

    manifiesto = _escribir_manifiesto(tmp_path / "muestra_pubs.yaml", juegos_man)
    dim, _ = construir_tablas_plata(tmp_path, manifiesto, fecha=fecha)
    filas = dim.to_pylist()
    #con 28 titulos excede max_titulos_publisher_mediano (25)
    for fila in filas:
        assert fila["indie_score"] < 0.60
        assert fila["is_indie"] is False

