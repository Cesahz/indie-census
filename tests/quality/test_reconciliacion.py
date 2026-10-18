#suite de pruebas para reconciliacion cero-huecos y auditoria pre-plata (contrato 10)
#garantias: verificacion exhaustiva contra manifest_master, barrido residual y validacion sha-256
import hashlib
import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

from src.extract.bronce import crear_envoltorio_bronce, guardar_en_bronce
from src.extract.checkpoint import GestorCheckpoint
from src.extract.client import SteamAppNotFoundError, SteamClient
from src.quality.reconciliacion import (
    auditar_completitud_manifiesto,
    descomprimir_snapshot_worker,
    ejecutar_barrido_residual,
    reconciliar_ingesta_distribuida,
    verificar_integridad_criptografica,
)


def _crear_payload_appdetails(appid: int) -> dict:
    return {
        str(appid): {
            "success": True,
            "data": {
                "steam_appid": appid,
                "name": f"Juego {appid}",
                "is_free": False,
                "release_date": {"date": "Jan 1, 2025"},
            },
        }
    }


def _crear_payload_reviews(appid: int) -> dict:
    return {
        "success": 1,
        "query_summary": {"total_reviews": 10},
    }


def _crear_manifiesto_maestro(ruta_archivo: Path, appids: list[int], fecha: str = "2026-10-18") -> None:
    ruta_archivo.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "descripcion": "Manifiesto maestro inmutable",
        "total_appids": len(appids),
        "appids": appids,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    doc = {
        "meta": {
            "fuente": "steam.catalog.manifest_master",
            "sha256_payload": sha,
            "sha256": sha,
            "extraido_en": f"{fecha}T00:00:00Z",
            "version_pipeline": "0.3.0",
        },
        "payload": payload,
    }
    with open(ruta_archivo, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)


def test_descomprimir_snapshot_worker(tmp_path: Path) -> None:
    #descomprimir snapshot debe restaurar la estructura de carpetas sin danar archivos existentes
    dir_origen = tmp_path / "origen" / "bronce" / "steam" / "2026-10-18" / "appdetails"
    dir_origen.mkdir(parents=True, exist_ok=True)
    archivo_origen = dir_origen / "101.json"
    archivo_origen.write_text('{"steam": 101}', encoding="utf-8")

    ruta_tar = tmp_path / "bronce_worker_1.tar.gz"
    with tarfile.open(ruta_tar, "w:gz") as tar:
        tar.add(tmp_path / "origen" / "bronce", arcname="bronce")

    dir_destino = tmp_path / "destino"
    res = descomprimir_snapshot_worker(ruta_tar=ruta_tar, ruta_base_destino=dir_destino)

    assert res["archivos_extraidos"] >= 1
    archivo_restaurado = dir_destino / "bronce" / "steam" / "2026-10-18" / "appdetails" / "101.json"
    assert archivo_restaurado.is_file()
    assert json.loads(archivo_restaurado.read_text(encoding="utf-8")) == {"steam": 101}


def test_auditar_completitud_manifiesto_100_por_ciento(tmp_path: Path) -> None:
    #si todos los appids estan en disco o marcados como no disponible, completitud es 100%
    fecha = "2026-10-18"
    appids = [101, 102, 103]
    ruta_man = tmp_path / "bronce" / "steam" / fecha / "applist" / "manifest_master.json"
    _crear_manifiesto_maestro(ruta_man, appids, fecha=fecha)

    #guardar 101 y 102 en bronce
    for aid in [101, 102]:
        env_det = crear_envoltorio_bronce("steam.appdetails", f"http://test/{aid}", {}, 200, _crear_payload_appdetails(aid))
        guardar_en_bronce("appdetails", fecha, aid, env_det, ruta_base=tmp_path)
        env_rev = crear_envoltorio_bronce("steam.appreviews_resumen", f"http://test/r/{aid}", {}, 200, _crear_payload_reviews(aid))
        guardar_en_bronce("appreviews_resumen", fecha, aid, env_rev, ruta_base=tmp_path)

    #marcar 103 en checkpoint como no disponible
    cp = GestorCheckpoint(ruta_archivo=tmp_path / "checkpoint.json")
    cp.marcar_completado("no_disponible", 103)

    auditoria = auditar_completitud_manifiesto(
        ruta_manifiesto=ruta_man,
        ruta_base=tmp_path,
        fecha=fecha,
        checkpoints=[cp],
    )

    assert auditoria["total_manifiesto"] == 3
    assert auditoria["completados_exito"] == 2
    assert auditoria["no_disponibles"] == 1
    assert auditoria["huecos_pendientes"] == 0
    assert auditoria["tasa_completitud"] == 1.0


def test_auditar_completitud_manifiesto_detecta_huecos(tmp_path: Path) -> None:
    #cuando faltan appids, la auditoria los identifica con precision
    fecha = "2026-10-18"
    appids = [201, 202, 203]
    ruta_man = tmp_path / "bronce" / "steam" / fecha / "applist" / "manifest_master.json"
    _crear_manifiesto_maestro(ruta_man, appids, fecha=fecha)

    #solo 201 esta presente completo
    env_det = crear_envoltorio_bronce("steam.appdetails", "http://test/201", {}, 200, _crear_payload_appdetails(201))
    guardar_en_bronce("appdetails", fecha, 201, env_det, ruta_base=tmp_path)
    env_rev = crear_envoltorio_bronce("steam.appreviews_resumen", "http://test/r/201", {}, 200, _crear_payload_reviews(201))
    guardar_en_bronce("appreviews_resumen", fecha, 201, env_rev, ruta_base=tmp_path)

    auditoria = auditar_completitud_manifiesto(
        ruta_manifiesto=ruta_man,
        ruta_base=tmp_path,
        fecha=fecha,
    )

    assert auditoria["total_manifiesto"] == 3
    assert auditoria["completados_exito"] == 1
    assert auditoria["huecos_pendientes"] == 2
    assert sorted(auditoria["appids_pendientes"]) == [202, 203]


def test_verificar_integridad_criptografica_sha256(tmp_path: Path) -> None:
    #valida hashes sha256 de los envoltorios json en bronce
    fecha = "2026-10-18"
    env_ok = crear_envoltorio_bronce("steam.appdetails", "http://test/301", {}, 200, _crear_payload_appdetails(301))
    guardar_en_bronce("appdetails", fecha, 301, env_ok, ruta_base=tmp_path)

    ruta_bronce = tmp_path / "bronce"
    res_ok = verificar_integridad_criptografica(ruta_bronce)
    assert res_ok["total_verificados"] >= 1
    assert res_ok["integros"] >= 1
    assert res_ok["corruptos"] == 0

    #alterar manualmente el payload para forzar discrepancia
    archivo = tmp_path / "bronce" / "steam" / "appdetails" / f"fecha={fecha}" / "appid=301.json"
    contenido = json.loads(archivo.read_text(encoding="utf-8"))
    contenido["payload"]["301"]["data"]["name"] = "Nombre Alterado Maliciosamente"
    archivo.write_text(json.dumps(contenido), encoding="utf-8")

    res_corrupto = verificar_integridad_criptografica(ruta_bronce)
    assert res_corrupto["corruptos"] == 1
    assert len(res_corrupto["archivos_corruptos"]) == 1


def test_ejecutar_barrido_residual(tmp_path: Path) -> None:
    #el barrido residual procesa appids pendientes hasta dejarlos en 0
    fecha = "2026-10-18"
    appids_pendientes = [401, 402]

    mock_client = MagicMock(spec=SteamClient)
    #401 exitoso, 402 arroja SteamAppNotFoundError
    def mock_get_details(aid: int) -> dict:
        if aid == 402:
            raise SteamAppNotFoundError(f"Appid {aid} no existe")
        return _crear_payload_appdetails(aid)

    mock_client.get_app_details.side_effect = mock_get_details
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"

    cp = GestorCheckpoint(ruta_archivo=tmp_path / "checkpoint_barrido.json")

    res = ejecutar_barrido_residual(
        appids_pendientes=appids_pendientes,
        client=mock_client,
        fecha=fecha,
        ruta_base=tmp_path,
        checkpoint=cp,
    )

    assert res["resueltos_exito"] == 1
    assert res["no_disponibles"] == 1
    assert res["pendientes_finales"] == 0
    assert cp.esta_completado("no_disponible", 402)
    assert (tmp_path / "bronce" / "steam" / "appdetails" / f"fecha={fecha}" / "appid=401.json").is_file()


def test_reconciliar_ingesta_distribuida_flujo_completo(tmp_path: Path) -> None:
    #flujo e2e: unificar tar, auditar manifiesto, barrer residuales y verificar criptografia
    fecha = "2026-10-18"
    appids = [501, 502, 503]
    ruta_man = tmp_path / "bronce" / "steam" / fecha / "applist" / "manifest_master.json"
    _crear_manifiesto_maestro(ruta_man, appids, fecha=fecha)

    #501 ya existe en local
    env_501 = crear_envoltorio_bronce("steam.appdetails", "http://test/501", {}, 200, _crear_payload_appdetails(501))
    guardar_en_bronce("appdetails", fecha, 501, env_501, ruta_base=tmp_path)
    env_rev_501 = crear_envoltorio_bronce("steam.appreviews_resumen", "http://test/r/501", {}, 200, _crear_payload_reviews(501))
    guardar_en_bronce("appreviews_resumen", fecha, 501, env_rev_501, ruta_base=tmp_path)

    #502 viene empaquetado en snapshot tar de worker 1
    dir_worker1 = tmp_path / "w1" / "bronce" / "steam" / fecha
    dir_worker1.mkdir(parents=True, exist_ok=True)
    guardar_en_bronce("appdetails", fecha, 502, crear_envoltorio_bronce("steam.appdetails", "http://test/502", {}, 200, _crear_payload_appdetails(502)), ruta_base=tmp_path / "w1")
    guardar_en_bronce("appreviews_resumen", fecha, 502, crear_envoltorio_bronce("steam.appreviews_resumen", "http://test/r/502", {}, 200, _crear_payload_reviews(502)), ruta_base=tmp_path / "w1")

    ruta_tar = tmp_path / "bronce_worker_1.tar.gz"
    with tarfile.open(ruta_tar, "w:gz") as tar:
        tar.add(tmp_path / "w1" / "bronce", arcname="bronce")

    #503 esta ausente pero el sweep pass lo resuelve
    mock_client = MagicMock(spec=SteamClient)
    mock_client.get_app_details.side_effect = lambda aid: _crear_payload_appdetails(aid)
    mock_client.get_app_reviews_summary.side_effect = lambda aid: _crear_payload_reviews(aid)
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"

    resultado = reconciliar_ingesta_distribuida(
        ruta_manifiesto=ruta_man,
        fecha=fecha,
        ruta_base=tmp_path,
        rutas_snapshots=[ruta_tar],
        client=mock_client,
        permitir_barrido=True,
    )

    assert resultado["estado"] == "aprobado"
    assert resultado["huecos_pendientes"] == 0
    assert resultado["tasa_completitud"] == 1.0
    assert resultado["archivos_corruptos"] == 0

    #verificar persistencia de reporte en auditorias/
    ruta_auditoria = tmp_path / "bronce" / "steam" / fecha / "auditorias" / "reconciliacion_cero_huecos.json"
    assert ruta_auditoria.is_file()
