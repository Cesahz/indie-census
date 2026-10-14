#suite de pruebas unitarias para gestor de checkpoint e idempotencia
#garantias: idempotencia, recuperacion ante cortes, deteccion de corrupcion, escritura atomica
import json
from pathlib import Path
import pytest

from src.extract.checkpoint import (
    CheckpointCorruptoError,
    CheckpointError,
    GestorCheckpoint,
)

def test_inicializacion_vacia_crea_directorio_y_estado_valido(tmp_path: Path) -> None:
    """Verificar que un gestor nuevo inicializa un estado vacio y crea directorios si faltan."""
    ruta = tmp_path / "subcarpeta" / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)

    #el archivo no se crea hasta el primer guardado
    assert not ruta.exists()
    assert not gestor.esta_completado("appdetails", 1809540)
    assert gestor.obtener_completados("appdetails") == set()
    assert gestor.resumen() == {}

    #guardado explicito inicial
    gestor.guardar()
    assert ruta.exists()

    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "version" in data
    assert "actualizado_en" in data
    assert data["completados"] == {}

def test_marcar_completado_y_recuperar_en_nueva_instancia(tmp_path: Path) -> None:
    """Verificar que marcar un elemento lo persiste y se recarga fielmente en otra instancia."""
    ruta = tmp_path / "checkpoint.json"
    gestor1 = GestorCheckpoint(ruta_archivo=ruta)

    gestor1.marcar_completado("appdetails", 1809540)
    assert gestor1.esta_completado("appdetails", 1809540)
    assert gestor1.resumen() == {"appdetails": 1}

    #segunda instancia sobre el mismo archivo en disco
    gestor2 = GestorCheckpoint(ruta_archivo=ruta)
    assert gestor2.esta_completado("appdetails", 1809540)
    assert gestor2.obtener_completados("appdetails") == {1809540}
    assert gestor2.resumen() == {"appdetails": 1}

def test_idempotencia_marcar_duplicados_deja_mismo_estado(tmp_path: Path) -> None:
    """Verificar que marcar repetidamente el mismo appid produce un estado identico sin duplicados."""
    ruta = tmp_path / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)

    #marcar el mismo id varias veces
    gestor.marcar_completado("appdetails", 252490)
    gestor.marcar_completado("appdetails", 252490)
    gestor.marcar_completado("appdetails", 252490)

    with open(ruta, "r", encoding="utf-8") as f:
        data1 = json.load(f)

    assert data1["completados"]["appdetails"] == [252490]

    #guardar nuevamente de forma idempotente
    gestor.guardar()
    with open(ruta, "r", encoding="utf-8") as f:
        data2 = json.load(f)

    assert data1["completados"] == data2["completados"]

def test_obtener_pendientes_preserva_orden_y_excluye_completados(tmp_path: Path) -> None:
    """Verificar que el filtrado de pendientes preserva el orden y omite los ya completados."""
    ruta = tmp_path / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)

    muestra = [100, 200, 300, 400, 500]
    gestor.marcar_completado("appdetails", 200)
    gestor.marcar_completado("appdetails", 400)

    pendientes = gestor.obtener_pendientes("appdetails", muestra)
    assert pendientes == [100, 300, 500]

def test_simulacion_interrupcion_y_reanudacion_idempotente(tmp_path: Path) -> None:
    """Simular una interrupcion a mitad de lote y reanudacion posterior solo con pendientes."""
    ruta = tmp_path / "checkpoint.json"
    lote_original = [10, 20, 30, 40, 50]

    #primera sesion: procesa solo 10 y 20 antes de interrumpirse
    sesion1 = GestorCheckpoint(ruta_archivo=ruta)
    for appid in [10, 20]:
        sesion1.marcar_completado("appdetails", appid)

    #segunda sesion: reanuda leyendo el archivo persistido
    sesion2 = GestorCheckpoint(ruta_archivo=ruta)
    pendientes = sesion2.obtener_pendientes("appdetails", lote_original)
    assert pendientes == [30, 40, 50]

    #procesar lo que faltaba
    for appid in pendientes:
        sesion2.marcar_completado("appdetails", appid)

    #tercera sesion de verificacion: 0 pendientes
    sesion3 = GestorCheckpoint(ruta_archivo=ruta)
    assert sesion3.obtener_pendientes("appdetails", lote_original) == []
    assert sesion3.obtener_completados("appdetails") == {10, 20, 30, 40, 50}

def test_deteccion_checkpoint_corrupto_json_invalido(tmp_path: Path) -> None:
    """Verificar que un archivo json truncado o corrupto levanta excepcion tipada."""
    ruta = tmp_path / "checkpoint.json"
    ruta.write_text('{"version": "0.1.0", "completados": {', encoding="utf-8")

    with pytest.raises(CheckpointCorruptoError) as exc_info:
        GestorCheckpoint(ruta_archivo=ruta)
    assert issubclass(CheckpointCorruptoError, CheckpointError)
    assert "corrupto" in str(exc_info.value).lower() or "invalido" in str(exc_info.value).lower()

def test_deteccion_checkpoint_corrupto_estructura_no_dict(tmp_path: Path) -> None:
    """Verificar que un json que no sea un objeto o sin clave completados levanta error."""
    ruta = tmp_path / "checkpoint.json"
    ruta.write_text('["elemento1", "elemento2"]', encoding="utf-8")

    with pytest.raises(CheckpointCorruptoError):
        GestorCheckpoint(ruta_archivo=ruta)

def test_deteccion_checkpoint_corrupto_nodo_completados_invalido(tmp_path: Path) -> None:
    """Verificar que un checkpoint cuyo nodo completados no sea un diccionario levanta error."""
    ruta = tmp_path / "checkpoint.json"
    ruta.write_text('{"version": "0.1.0", "completados": "invalido"}', encoding="utf-8")

    with pytest.raises(CheckpointCorruptoError):
        GestorCheckpoint(ruta_archivo=ruta)

def test_escritura_atomica_sin_temporales_residuales(tmp_path: Path) -> None:
    """Verificar que el guardado atomico no deja archivos temporales residuales en disco."""
    ruta = tmp_path / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)

    gestor.marcar_completado("appdetails", 1809540)
    gestor.guardar()

    #revisar que no existan archivos .tmp
    temporales = list(tmp_path.glob("*.tmp"))
    assert len(temporales) == 0

    #verificar integridad del archivo final
    assert ruta.exists()
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["completados"]["appdetails"] == [1809540]

def test_independencia_entre_recursos_distintos(tmp_path: Path) -> None:
    """Verificar que recursos distintos (appdetails vs appreviews_resumen) no interfieren entre si."""
    ruta = tmp_path / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)

    gestor.marcar_completado("appdetails", 1809540)
    gestor.marcar_completado("appreviews_resumen", 252490)

    assert gestor.esta_completado("appdetails", 1809540)
    assert not gestor.esta_completado("appdetails", 252490)

    assert gestor.esta_completado("appreviews_resumen", 252490)
    assert not gestor.esta_completado("appreviews_resumen", 1809540)

    assert gestor.resumen() == {"appdetails": 1, "appreviews_resumen": 1}

def test_marcar_lote_completado_y_limpiar(tmp_path: Path) -> None:
    """Verificar que marcar en lote y limpiar el estado operan correctamente y persisten."""
    ruta = tmp_path / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)

    #marcar lote
    gestor.marcar_lote_completado("appdetails", [10, 20, 30])
    assert gestor.obtener_completados("appdetails") == {10, 20, 30}

    #limpiar estado
    gestor.limpiar()
    assert gestor.obtener_completados("appdetails") == set()
    assert gestor.resumen() == {}

    #verificar recarga limpia desde disco
    recargado = GestorCheckpoint(ruta_archivo=ruta)
    assert recargado.obtener_completados("appdetails") == set()

def test_deteccion_checkpoint_corrupto_nodo_recurso_no_lista(tmp_path: Path) -> None:
    """Verificar que si el valor de un recurso en completados no es una lista, levanta error."""
    ruta = tmp_path / "checkpoint.json"
    ruta.write_text('{"version": "0.1.0", "completados": {"appdetails": "no_es_lista"}}', encoding="utf-8")

    with pytest.raises(CheckpointCorruptoError):
        GestorCheckpoint(ruta_archivo=ruta)

def test_guardar_falla_limpia_archivo_temporal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verificar que ante un fallo de disco en el reemplazo, el archivo temporal se elimina."""
    ruta = tmp_path / "checkpoint.json"
    gestor = GestorCheckpoint(ruta_archivo=ruta)
    gestor.marcar_completado("appdetails", 100, persistir=False)

    def mock_replace_falla(origen: Path, destino: Path) -> None:
        raise OSError("Fallo simulado de disco")

    monkeypatch.setattr("os.replace", mock_replace_falla)

    with pytest.raises(OSError, match="Fallo simulado de disco"):
        gestor.guardar()

    #verificar que no quedo el archivo temporal colgado
    ruta_tmp = ruta.with_suffix(".tmp")
    assert not ruta_tmp.exists()

def test_inicializacion_ruta_por_defecto() -> None:
    """Verificar que la inicializacion sin argumentos adopta la ruta canonica por defecto."""
    gestor = GestorCheckpoint()
    from src.extract.checkpoint import RUTA_CHECKPOINT_DEFAULT
    assert gestor.ruta_archivo == RUTA_CHECKPOINT_DEFAULT
