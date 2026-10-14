#suite e2e hermetica del orquestador general del pipeline
#flujo verificado: extraccion -> transformacion_plata -> validacion_contratos
#sin acceso a red: cliente steam falso inyectado y sockets bloqueados
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pyarrow.parquet as pq
import pytest
import yaml

from src.pipeline import RUTA_MANIFIESTO_DEFAULT, ejecutar_pipeline, main
from src.quality.contratos import ContratoCalidadError, validar_contratos_plata

REPO_ROOT = Path(__file__).resolve().parents[1]
FECHA = "2026-10-01"
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@pytest.fixture(autouse=True)
def bloquear_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garantizar hermeticidad: cualquier intento de abrir un socket hace fallar la prueba."""
    def socket_prohibido(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Acceso a red prohibido en pruebas e2e")
    monkeypatch.setattr(socket, "socket", socket_prohibido)
    monkeypatch.setattr(socket, "create_connection", socket_prohibido)


def _juegos_manifiesto(ruta: Path) -> list[dict[str, Any]]:
    """Leer la lista de juegos de un manifiesto yaml."""
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))["juegos"]


class ClienteSteamFalso:
    """Cliente con la misma interfaz publica que SteamClient y respuestas sinteticas."""

    base_url_store = "https://store.example.invalid/api"
    country_code = "us"
    language = "english"

    def __init__(
        self,
        juegos: list[dict[str, Any]],
        appid_incoherente: Optional[int] = None,
        appid_fallido: Optional[int] = None,
        prohibir_llamadas: bool = False,
    ) -> None:
        self.juegos = {int(j["appid"]): j for j in juegos}
        self.appid_incoherente = appid_incoherente
        self.appid_fallido = appid_fallido
        self.prohibir_llamadas = prohibir_llamadas
        self.llamadas: list[tuple[str, int]] = []

    def _registrar(self, recurso: str, appid: int) -> None:
        """Registrar la llamada y simular fallas configuradas."""
        if self.prohibir_llamadas:
            raise AssertionError(f"Llamada no esperada a {recurso} para appid {appid}")
        self.llamadas.append((recurso, appid))
        if appid == self.appid_fallido:
            raise RuntimeError(f"Falla simulada para appid {appid}")

    def get_app_details(self, appid: int) -> dict[str, Any]:
        """Retornar appdetails sintetico coherente con el manifiesto."""
        self._registrar("appdetails", appid)
        juego = self.juegos[appid]
        fecha = date.fromisoformat(str(juego["release_date"]))
        es_gratis = appid % 7 == 0
        data: dict[str, Any] = {
            "type": "game",
            "name": juego["titulo"],
            "steam_appid": appid,
            "is_free": es_gratis,
            "release_date": {"coming_soon": False, "date": f"{fecha.day} {MESES[fecha.month - 1]}, {fecha.year}"},
            "developers": ["Estudio"],
            "publishers": ["Editorial"],
            "genres": [{"id": "23", "description": "Indie"}],
            "supported_languages": "English, Spanish - Spain",
        }
        if not es_gratis:
            data["price_overview"] = {"currency": "USD", "initial": 1499, "final": 1499}
        return {str(appid): {"success": True, "data": data}}

    def get_app_reviews_summary(self, appid: int) -> dict[str, Any]:
        """Retornar resumen de resenas sintetico, opcionalmente incoherente."""
        self._registrar("appreviews_resumen", appid)
        positivas, negativas = appid % 100, appid % 13
        total = positivas + negativas + (1 if appid == self.appid_incoherente else 0)
        return {"success": 1, "query_summary": {
            "total_positive": positivas, "total_negative": negativas, "total_reviews": total,
        }}


@pytest.fixture
def juegos_reales() -> list[dict[str, Any]]:
    """Juegos del manifiesto versionado de la muestra de control."""
    return _juegos_manifiesto(RUTA_MANIFIESTO_DEFAULT)


def _archivos_plata(base: Path) -> list[Path]:
    """Listar archivos presentes bajo plata."""
    plata = base / "plata"
    return [p for p in plata.rglob("*") if p.is_file()] if plata.exists() else []


#flujo completo con la muestra de control real

def test_e2e_muestra_real_produce_plata_valida(tmp_path: Path, juegos_reales: list[dict[str, Any]]) -> None:
    cliente = ClienteSteamFalso(juegos_reales)
    resultado = ejecutar_pipeline(ruta_base=tmp_path, client=cliente, fecha=FECHA)

    assert resultado["estado"] == "ok"
    assert resultado["extraccion"]["total_juegos"] == 100
    assert resultado["extraccion"]["fallidos"] == 0
    assert resultado["plata"]["filas_dim_game"] == 100
    assert resultado["plata"]["filas_game_review_summary"] == 100
    assert len(cliente.llamadas) == 200

    dim = pq.read_table(tmp_path / "plata" / "steam" / "dim_game.parquet")
    resenas = pq.read_table(tmp_path / "plata" / "steam" / "game_review_summary.parquet")
    validar_contratos_plata(dim, resenas)
    grupos = dim.column("group").to_pylist()
    assert grupos.count("godot") == 50
    assert grupos.count("general") == 50


def test_e2e_artefactos_quedan_confinados_en_ruta_base(tmp_path: Path, juegos_reales: list[dict[str, Any]]) -> None:
    ejecutar_pipeline(ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales), fecha=FECHA)
    assert (tmp_path / "checkpoint.json").exists()
    assert len(list((tmp_path / "bronce" / "steam" / "appdetails" / f"fecha={FECHA}").glob("*.json"))) == 100
    assert len(list((tmp_path / "bronce" / "steam" / "appreviews_resumen" / f"fecha={FECHA}").glob("*.json"))) == 100


def test_e2e_segunda_ejecucion_es_idempotente_sin_llamadas(
    tmp_path: Path, juegos_reales: list[dict[str, Any]],
) -> None:
    ejecutar_pipeline(ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales), fecha=FECHA)
    cliente_vigilado = ClienteSteamFalso(juegos_reales, prohibir_llamadas=True)
    resultado = ejecutar_pipeline(ruta_base=tmp_path, client=cliente_vigilado, fecha=FECHA)
    assert resultado["estado"] == "ok"
    assert cliente_vigilado.llamadas == []
    assert resultado["plata"]["filas_dim_game"] == 100


def test_e2e_omitir_extraccion_reprocesa_bronce_existente(
    tmp_path: Path, juegos_reales: list[dict[str, Any]],
) -> None:
    ejecutar_pipeline(ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales), fecha=FECHA)
    resultado = ejecutar_pipeline(
        ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales, prohibir_llamadas=True),
        omitir_extraccion=True,
    )
    assert resultado["extraccion"] is None
    assert resultado["plata"]["filas_dim_game"] == 100


#bloqueos de calidad durante el flujo

def test_e2e_contrato_violado_bloquea_y_no_escribe_plata(
    tmp_path: Path, juegos_reales: list[dict[str, Any]],
) -> None:
    appid = int(juegos_reales[10]["appid"])
    with pytest.raises(ContratoCalidadError, match=str(appid)) as info:
        ejecutar_pipeline(
            ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales, appid_incoherente=appid), fecha=FECHA,
        )
    assert info.value.contrato == "coherencia_aritmetica"
    assert _archivos_plata(tmp_path) == []


def test_e2e_fallo_de_extraccion_bloquea_por_cardinalidad(
    tmp_path: Path, juegos_reales: list[dict[str, Any]],
) -> None:
    appid = int(juegos_reales[0]["appid"])
    with pytest.raises(ContratoCalidadError) as info:
        ejecutar_pipeline(
            ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales, appid_fallido=appid), fecha=FECHA,
        )
    assert info.value.contrato == "cardinalidad"
    assert _archivos_plata(tmp_path) == []


def test_e2e_manifiesto_y_cardinalidad_inyectables(tmp_path: Path, juegos_reales: list[dict[str, Any]]) -> None:
    manifiesto = tmp_path / "muestra.yaml"
    manifiesto.write_text(yaml.safe_dump({"juegos": juegos_reales[:4]}), encoding="utf-8")
    resultado = ejecutar_pipeline(
        ruta_manifiesto=manifiesto, ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales[:4]),
        fecha=FECHA, cardinalidad_esperada=4,
    )
    assert resultado["plata"]["filas_dim_game"] == 4


#punto de entrada cli

def test_main_retorna_cero_y_reporta_resumen(
    tmp_path: Path, juegos_reales: list[dict[str, Any]], capsys: pytest.CaptureFixture[str],
) -> None:
    codigo = main(["--ruta-base", str(tmp_path), "--fecha", FECHA], client=ClienteSteamFalso(juegos_reales))
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "Pipeline completado" in salida
    assert "100" in salida


def test_main_retorna_uno_ante_contrato_violado(
    tmp_path: Path, juegos_reales: list[dict[str, Any]], capsys: pytest.CaptureFixture[str],
) -> None:
    appid = int(juegos_reales[3]["appid"])
    codigo = main(
        ["--ruta-base", str(tmp_path), "--fecha", FECHA],
        client=ClienteSteamFalso(juegos_reales, appid_incoherente=appid),
    )
    error = capsys.readouterr().err
    assert codigo == 1
    assert "Pipeline bloqueado" in error
    assert "coherencia_aritmetica" in error
    assert _archivos_plata(tmp_path) == []


def test_main_omitir_extraccion_por_cli(
    tmp_path: Path, juegos_reales: list[dict[str, Any]],
) -> None:
    ejecutar_pipeline(ruta_base=tmp_path, client=ClienteSteamFalso(juegos_reales), fecha=FECHA)
    codigo = main(
        ["--ruta-base", str(tmp_path), "--omitir-extraccion"],
        client=ClienteSteamFalso(juegos_reales, prohibir_llamadas=True),
    )
    assert codigo == 0


def test_modulo_ejecutable_con_python_m() -> None:
    #el subproceso solo consulta la ayuda y no construye cliente http
    proceso = subprocess.run(
        [sys.executable, "-m", "src.pipeline", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proceso.returncode == 0
    assert "--omitir-extraccion" in proceso.stdout
