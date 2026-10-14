#suite de pruebas para persistencia inmutable en capa bronce (criterio f1-03)
#verifica envoltorio de metadatos, particionado estricto y rechazo de sobrescritura
import json
from pathlib import Path

#pyrefly: ignore [missing-import]
import pytest

from src.extract.bronce import (
    BronzeImmutabilityError,
    crear_envoltorio_bronce,
    guardar_en_bronce,
)


# ---------------------------------------------------------------------------
# pruebas del envoltorio de metadatos
# ---------------------------------------------------------------------------

def test_crear_envoltorio_bronce_estructura_valida() -> None:
    #verificar campos obligatorios del envoltorio
    payload_muestra = {"1809540": {"success": True, "data": {"name": "Nine Sols"}}}
    envoltorio = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="https://store.steampowered.com/api/appdetails?appids=1809540",
        parametros={"region": "US", "idioma": "english"},
        estado_http=200,
        payload=payload_muestra,
        extraido_en="2026-10-06T12:00:00Z",
        version_pipeline="0.1.0",
    )

    assert "meta" in envoltorio
    assert "payload" in envoltorio
    assert envoltorio["payload"] == payload_muestra

    meta = envoltorio["meta"]
    assert meta["fuente"] == "steam.appdetails"
    assert "appids=1809540" in meta["url_solicitada"]
    assert meta["parametros"] == {"region": "US", "idioma": "english"}
    assert meta["estado_http"] == 200
    assert meta["extraido_en"] == "2026-10-06T12:00:00Z"
    assert meta["version_pipeline"] == "0.1.0"
    assert isinstance(meta["sha256_payload"], str)
    assert len(meta["sha256_payload"]) == 64


def test_crear_envoltorio_calcula_sha256_determinista() -> None:
    #el hash del payload debe ser identico para payloads equivalentes
    payload = {"clave": "valor", "numero": 123}
    env1 = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="http://url1",
        parametros={},
        estado_http=200,
        payload=payload,
    )
    env2 = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="http://url2",
        parametros={},
        estado_http=200,
        payload=payload,
    )
    assert env1["meta"]["sha256_payload"] == env2["meta"]["sha256_payload"]


# ---------------------------------------------------------------------------
# pruebas de almacenamiento y particionado
# ---------------------------------------------------------------------------

def test_guardar_en_bronce_crea_particion_correcta(tmp_path: Path) -> None:
    #verificar ruta data/bronce/steam/<recurso>/fecha=AAAA-MM-DD/appid=<id>.json
    payload = {"data": "prueba"}
    envoltorio = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="http://url",
        parametros={},
        estado_http=200,
        payload=payload,
    )

    ruta_archivo = guardar_en_bronce(
        recurso="appdetails",
        fecha="2026-10-06",
        appid=1809540,
        envoltorio=envoltorio,
        ruta_base=tmp_path,
    )

    esperada = (
        tmp_path
        / "bronce"
        / "steam"
        / "appdetails"
        / "fecha=2026-10-06"
        / "appid=1809540.json"
    )
    assert ruta_archivo == esperada
    assert ruta_archivo.is_file()

    contenido_disco = json.loads(ruta_archivo.read_text(encoding="utf-8"))
    assert contenido_disco == envoltorio


def test_guardar_en_bronce_rechaza_sobrescritura(tmp_path: Path) -> None:
    #inmutabilidad estricta: un archivo existente no puede ser sobrescrito
    envoltorio = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="http://url",
        parametros={},
        estado_http=200,
        payload={"intento": 1},
    )

    #primer guardado exitoso
    guardar_en_bronce(
        recurso="appdetails",
        fecha="2026-10-06",
        appid=1809540,
        envoltorio=envoltorio,
        ruta_base=tmp_path,
    )

    #segundo guardado debe ser rechazado
    envoltorio_nuevo = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="http://url",
        parametros={},
        estado_http=200,
        payload={"intento": 2},
    )

    with pytest.raises(BronzeImmutabilityError) as exc_info:
        guardar_en_bronce(
            recurso="appdetails",
            fecha="2026-10-06",
            appid=1809540,
            envoltorio=envoltorio_nuevo,
            ruta_base=tmp_path,
        )

    assert "sobrescritura rechazada" in str(exc_info.value).lower()
    assert "appid=1809540.json" in str(exc_info.value)


def test_guardar_en_bronce_recurso_invalido_bloquea(tmp_path: Path) -> None:
    #solo se admiten los recursos fijados en la arquitectura
    envoltorio = crear_envoltorio_bronce(
        fuente="steam.otro",
        url_solicitada="http://url",
        parametros={},
        estado_http=200,
        payload={},
    )
    with pytest.raises(ValueError) as exc_info:
        guardar_en_bronce(
            recurso="recurso_no_reconocido",
            fecha="2026-10-06",
            appid=1809540,
            envoltorio=envoltorio,
            ruta_base=tmp_path,
        )
    assert "recurso no admitido" in str(exc_info.value).lower()


def test_guardar_en_bronce_limpia_archivo_temporal_ante_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    #si ocurre un fallo durante el renombrado atomico, se elimina el temporal .tmp
    envoltorio = crear_envoltorio_bronce(
        fuente="steam.appdetails",
        url_solicitada="http://url",
        parametros={},
        estado_http=200,
        payload={"clave": "prueba"},
    )

    def fake_replace(src: Path, dst: Path) -> None:
        raise OSError("error de disco simulado")

    monkeypatch.setattr("os.replace", fake_replace)

    with pytest.raises(OSError):
        guardar_en_bronce(
            recurso="appdetails",
            fecha="2026-10-06",
            appid=1809540,
            envoltorio=envoltorio,
            ruta_base=tmp_path,
        )

    directorio = tmp_path / "bronce" / "steam" / "appdetails" / "fecha=2026-10-06"
    assert not (directorio / "appid=1809540.tmp").exists()
    assert not (directorio / "appid=1809540.json").exists()
