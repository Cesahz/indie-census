#suite de pruebas para sharding modular, congelamiento de manifiesto y snapshots tar
#garantias: particionamiento sin huecos ni solapamientos, checkpoints aislados, empaquetado atomico
import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.extract.checkpoint import GestorCheckpoint
from src.extract.pipeline import (
    cargar_manifest_master,
    congelar_manifiesto_maestro,
    ejecutar_ingesta_masiva,
    particionar_appids_por_modulo,
    sincronizar_snapshot_tar,
)


def test_particionar_appids_por_modulo_dos_workers() -> None:
    """Particionar 10 appids entre 2 workers garantiza particiones disjuntas y completas."""
    appids = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

    worker_0 = particionar_appids_por_modulo(appids, worker_id=0, total_workers=2)
    worker_1 = particionar_appids_por_modulo(appids, worker_id=1, total_workers=2)

    assert worker_0 == [100, 300, 500, 700, 900]
    assert worker_1 == [200, 400, 600, 800, 1000]

    #garantizar cero solapamiento
    assert set(worker_0).intersection(set(worker_1)) == set()

    #garantizar cero huecos (union exacta)
    assert set(worker_0).union(set(worker_1)) == set(appids)


def test_particionar_appids_tres_workers() -> None:
    """Particionar lista entre 3 workers asigna congruencia modulo 3."""
    appids = [1, 2, 3, 4, 5, 6, 7, 8, 9]

    w0 = particionar_appids_por_modulo(appids, worker_id=0, total_workers=3)
    w1 = particionar_appids_por_modulo(appids, worker_id=1, total_workers=3)
    w2 = particionar_appids_por_modulo(appids, worker_id=2, total_workers=3)

    assert w0 == [1, 4, 7]
    assert w1 == [2, 5, 8]
    assert w2 == [3, 6, 9]
    assert set(w0 + w1 + w2) == set(appids)


def test_particionar_appids_validaciones_error() -> None:
    """Verificar que argumentos invalidos de worker_id y total_workers levantan ValueError."""
    appids = [10, 20, 30]

    with pytest.raises(ValueError, match="total_workers debe ser >= 1"):
        particionar_appids_por_modulo(appids, worker_id=0, total_workers=0)

    with pytest.raises(ValueError, match="worker_id debe estar en"):
        particionar_appids_por_modulo(appids, worker_id=2, total_workers=2)

    with pytest.raises(ValueError, match="worker_id debe estar en"):
        particionar_appids_por_modulo(appids, worker_id=-1, total_workers=2)


def test_congelar_manifiesto_maestro(tmp_path: Path) -> None:
    """Congelar manifiesto maestro filtra por umbral min_appid, ordena y calcula sha256."""
    mock_client = MagicMock()
    mock_client.iterar_catalogo_completo.return_value = iter([
        {"appid": 10, "name": "Classic 1"},
        {"appid": 500000, "name": "Old Game"},
        {"appid": 2600050, "name": "Modern 2"},
        {"appid": 2600010, "name": "Modern 1"},
        {"appid": 2600050, "name": "Modern 2 Duplicado"},
    ])

    ruta_manifiesto = congelar_manifiesto_maestro(
        client=mock_client,
        min_appid=2600000,
        fecha="2026-10-18",
        ruta_base=tmp_path,
    )

    assert ruta_manifiesto.is_file()

    #verificar contenido y formato del envoltorio de bronce
    with open(ruta_manifiesto, "r", encoding="utf-8") as f:
        datos = json.load(f)

    assert "meta" in datos
    assert "sha256" in datos["meta"]
    assert datos["meta"]["recurso"] == "applist"

    payload = datos["payload"]
    assert payload["total_appids"] == 2
    #debe estar estrictamente ordenado y deduplicado
    assert payload["appids"] == [2600010, 2600050]
    assert payload["min_appid"] == 2600010
    assert payload["max_appid"] == 2600050


def test_cargar_manifest_master(tmp_path: Path) -> None:
    """Cargar manifiesto maestro extrae la lista entera de appids."""
    archivo_manifest = tmp_path / "manifest_master.json"
    contenido = {
        "meta": {"sha256": "fakehash", "recurso": "applist"},
        "payload": {
            "total_appids": 3,
            "appids": [2600001, 2600002, 2600003],
        },
    }
    archivo_manifest.write_text(json.dumps(contenido), encoding="utf-8")

    appids = cargar_manifest_master(archivo_manifest)
    assert appids == [2600001, 2600002, 2600003]


def test_checkpoint_aislado_por_worker(tmp_path: Path) -> None:
    """Ejecucion con sharding crea checkpoint aislado nombrado por worker."""
    mock_client = MagicMock()
    mock_client.base_url_store = "https://store.steampowered.com/api"
    mock_client.country_code = "US"
    mock_client.language = "english"
    mock_client.get_app_details.return_value = {"2600001": {"success": True, "data": {"name": "Test"}}}
    mock_client.get_app_reviews_summary.return_value = {"success": 1, "query_summary": {"total_reviews": 10}}

    resultado = ejecutar_ingesta_masiva(
        appids=[2600001],
        client=mock_client,
        fecha="2026-10-18",
        ruta_base=tmp_path,
        mostrar_progreso=False,
        worker_id=1,
        total_workers=2,
    )

    assert resultado["procesados_exito"] == 1
    checkpoint_worker = tmp_path / "checkpoint_worker_1_of_2.json"
    assert checkpoint_worker.is_file()

    cp = GestorCheckpoint(ruta_archivo=checkpoint_worker)
    assert cp.esta_completado("appdetails", 2600001)
    assert cp.esta_completado("appreviews_resumen", 2600001)


def test_sincronizar_snapshot_tar(tmp_path: Path) -> None:
    """Empaquetar directorio bronce en tar.gz atomico en sync_tar_dir."""
    ruta_bronce = tmp_path / "bronce"
    ruta_appdetails = ruta_bronce / "steam" / "2026-10-18" / "appdetails"
    ruta_appdetails.mkdir(parents=True, exist_ok=True)
    (ruta_appdetails / "2600001.json").write_text('{"test": 1}', encoding="utf-8")

    sync_dir = tmp_path / "drive_sync"
    archivo_tar = sincronizar_snapshot_tar(
        ruta_bronce=ruta_bronce,
        sync_tar_dir=sync_dir,
        worker_id=1,
    )

    assert archivo_tar.is_file()
    assert archivo_tar.name == "bronce_worker_1.tar.gz"

    #verificar contenido del archivo tar
    with tarfile.open(archivo_tar, "r:gz") as tar:
        nombres = tar.getnames()
        assert any("2600001.json" in n for n in nombres)
