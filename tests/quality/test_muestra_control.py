#suite de contrato para el manifiesto de la muestra de control (criterio f1-01)
#estado esperado al commitear: todos los tests en rojo (manifiesto vacio)
#estado al cerrar f1-01: todos los tests en verde con manifiesto poblado
#sin acceso a red, sin reloj real
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pytest
import yaml
from pydantic import BaseModel, field_validator, model_validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
RUTA_MANIFIESTO = REPO_ROOT / "config" / "muestra_control.yaml"
RUTA_CHANGELOG = REPO_ROOT / "changelog.md"

GRUPOS_VALIDOS = {"godot", "general"}
NIVELES_EVIDENCIA_GODOT = {1, 2}
FECHA_MIN = date(2024, 1, 1)
FECHA_MAX = date(2026, 12, 31)
TOTAL_JUEGOS = 100
POR_GRUPO = 50


# ---------------------------------------------------------------------------
# esquemas pydantic para el manifiesto poblado
# ---------------------------------------------------------------------------

class EntradaManifiesto(BaseModel):
    """contrato de una entrada individual del manifiesto de la muestra."""

    appid: int
    grupo: str
    titulo: str
    release_date: str
    evidencia_nivel: Optional[int] = None
    fuente_evidencia: Optional[str] = None
    criterio_inclusion: str
    semilla_sorteo: Optional[int] = None

    @field_validator("grupo")
    @classmethod
    def grupo_valido(cls, v: str) -> str:
        #solo se admiten los dos grupos del diseno
        if v not in GRUPOS_VALIDOS:
            raise ValueError(f"grupo invalido: {v!r} — solo se admiten {sorted(GRUPOS_VALIDOS)}")
        return v

    @field_validator("release_date")
    @classmethod
    def fecha_en_ventana(cls, v: str) -> str:
        #formato iso 8601 y dentro de la ventana 2024-2026
        try:
            d = date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"release_date no es una fecha iso valida: {v!r}") from exc
        if not (FECHA_MIN <= d <= FECHA_MAX):
            raise ValueError(
                f"release_date {v!r} fuera de la ventana permitida "
                f"({FECHA_MIN} – {FECHA_MAX})"
            )
        return v

    @field_validator("evidencia_nivel")
    @classmethod
    def nivel_evidencia_valido(cls, v: Optional[int]) -> Optional[int]:
        #si se proporciona, debe ser un nivel reconocido
        if v is not None and v not in {1, 2, 3, 4}:
            raise ValueError(f"evidencia_nivel invalido: {v} — valores admitidos: 1, 2, 3, 4")
        return v

    @model_validator(mode="after")
    def reglas_por_grupo(self) -> "EntradaManifiesto":
        """aplicar reglas cruzadas segun el grupo de la entrada."""
        if self.grupo == "godot":
            #grupo godot: evidencia de nivel 1 o 2 obligatoria
            if self.evidencia_nivel not in NIVELES_EVIDENCIA_GODOT:
                raise ValueError(
                    f"appid {self.appid}: grupo godot requiere evidencia_nivel 1 o 2, "
                    f"se obtuvo {self.evidencia_nivel!r}"
                )
            if not self.fuente_evidencia:
                raise ValueError(
                    f"appid {self.appid}: grupo godot requiere fuente_evidencia no nula"
                )
        elif self.grupo == "general":
            #grupo general: no debe tener evidencia de motor de godot
            if self.evidencia_nivel is not None:
                raise ValueError(
                    f"appid {self.appid}: grupo general no debe tener evidencia_nivel, "
                    f"se obtuvo {self.evidencia_nivel!r}"
                )
        return self


class ManifiestoSchema(BaseModel):
    """contrato del manifiesto completo config/muestra_control.yaml."""

    juegos: list[EntradaManifiesto]
    sha256_manifiesto: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cargar_contenido_yaml() -> Any:
    """cargar muestra_control.yaml y devolver contenido crudo."""
    assert RUTA_MANIFIESTO.is_file(), "config/muestra_control.yaml no existe"
    with RUTA_MANIFIESTO.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _calcular_sha256_manifiesto() -> str:
    """calcular sha256 del contenido binario de muestra_control.yaml."""
    contenido = RUTA_MANIFIESTO.read_bytes()
    return hashlib.sha256(contenido).hexdigest()


def _cargar_manifiesto_validado() -> ManifiestoSchema:
    """cargar y validar el manifiesto completo con pydantic."""
    contenido = _cargar_contenido_yaml()
    assert contenido is not None, (
        "muestra_control.yaml esta vacio — poblar el manifiesto antes de ejecutar estos tests"
    )
    try:
        return ManifiestoSchema(**contenido)
    except ValidationError as exc:
        pytest.fail(f"muestra_control.yaml no pasa el esquema de contrato:\n{exc}")


def _extraer_sha256_desde_changelog() -> Optional[str]:
    """buscar la huella sha256 del manifiesto registrada en changelog.md."""
    if not RUTA_CHANGELOG.is_file():
        return None
    texto = RUTA_CHANGELOG.read_text(encoding="utf-8")
    #formato esperado en changelog: sha256-muestra-control: <hexdigest>
    patron = re.compile(r"sha256-muestra-control:\s*([a-f0-9]{64})", re.IGNORECASE)
    match = patron.search(texto)
    return match.group(1).lower() if match else None


# ---------------------------------------------------------------------------
# f1-01a: existencia y estructura basica del manifiesto
# ---------------------------------------------------------------------------

def test_f1_01_manifiesto_existe() -> None:
    #config/muestra_control.yaml debe existir
    assert RUTA_MANIFIESTO.is_file(), "config/muestra_control.yaml no existe"


def test_f1_01_manifiesto_no_vacio() -> None:
    #el manifiesto debe tener contenido (no puede estar vacio en fase 1)
    contenido = _cargar_contenido_yaml()
    assert contenido is not None, (
        "muestra_control.yaml esta vacio — debe contener el manifiesto de 100 juegos"
    )


def test_f1_01_manifiesto_es_mapping() -> None:
    #el contenido raiz debe ser un mapping (dict), no una lista ni un escalar
    contenido = _cargar_contenido_yaml()
    assert isinstance(contenido, dict), (
        f"muestra_control.yaml debe ser un mapping en la raiz, se obtuvo: {type(contenido).__name__}"
    )


def test_f1_01_manifiesto_tiene_campo_juegos() -> None:
    #el campo 'juegos' debe estar presente y ser una lista
    contenido = _cargar_contenido_yaml() or {}
    assert "juegos" in contenido, "campo 'juegos' ausente en muestra_control.yaml"
    assert isinstance(contenido["juegos"], list), (
        f"campo 'juegos' debe ser una lista, se obtuvo: {type(contenido['juegos']).__name__}"
    )


def test_f1_01_manifiesto_tiene_campo_sha256() -> None:
    #el campo 'sha256_manifiesto' debe estar presente
    contenido = _cargar_contenido_yaml() or {}
    assert "sha256_manifiesto" in contenido, (
        "campo 'sha256_manifiesto' ausente en muestra_control.yaml"
    )


# ---------------------------------------------------------------------------
# f1-01b: cardinalidad y balance del manifiesto
# ---------------------------------------------------------------------------

def test_f1_01_total_100_juegos() -> None:
    #el manifiesto debe tener exactamente 100 entradas
    manifiesto = _cargar_manifiesto_validado()
    assert len(manifiesto.juegos) == TOTAL_JUEGOS, (
        f"se esperaban {TOTAL_JUEGOS} juegos, se encontraron {len(manifiesto.juegos)}"
    )


def test_f1_01_exactamente_50_godot() -> None:
    #deben existir exactamente 50 juegos del grupo godot
    manifiesto = _cargar_manifiesto_validado()
    godot = [j for j in manifiesto.juegos if j.grupo == "godot"]
    assert len(godot) == POR_GRUPO, (
        f"se esperaban {POR_GRUPO} juegos godot, se encontraron {len(godot)}"
    )


def test_f1_01_exactamente_50_general() -> None:
    #deben existir exactamente 50 juegos del grupo general
    manifiesto = _cargar_manifiesto_validado()
    general = [j for j in manifiesto.juegos if j.grupo == "general"]
    assert len(general) == POR_GRUPO, (
        f"se esperaban {POR_GRUPO} juegos general, se encontraron {len(general)}"
    )


def test_f1_01_appids_unicos() -> None:
    #no puede haber dos entradas con el mismo appid
    manifiesto = _cargar_manifiesto_validado()
    appids = [j.appid for j in manifiesto.juegos]
    duplicados = {a for a in appids if appids.count(a) > 1}
    assert not duplicados, f"appids duplicados en el manifiesto: {sorted(duplicados)}"


# ---------------------------------------------------------------------------
# f1-01c: contratos de ventana de lanzamiento
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grupo", ["godot", "general"])
def test_f1_01_ventana_lanzamiento_por_grupo(grupo: str) -> None:
    #toda release_date debe estar dentro de 2024-01-01 a 2026-12-31
    manifiesto = _cargar_manifiesto_validado()
    fuera = [
        (j.appid, j.release_date)
        for j in manifiesto.juegos
        if j.grupo == grupo and not (FECHA_MIN <= date.fromisoformat(j.release_date) <= FECHA_MAX)
    ]
    assert not fuera, (
        f"juegos del grupo {grupo!r} con release_date fuera de ventana: {fuera}"
    )


# ---------------------------------------------------------------------------
# f1-01d: contratos de evidencia por grupo
# ---------------------------------------------------------------------------

def test_f1_01_godot_evidencia_nivel_1_o_2() -> None:
    #todos los juegos godot deben tener evidencia_nivel 1 o 2
    manifiesto = _cargar_manifiesto_validado()
    sin_evidencia = [
        j.appid for j in manifiesto.juegos
        if j.grupo == "godot" and j.evidencia_nivel not in NIVELES_EVIDENCIA_GODOT
    ]
    assert not sin_evidencia, (
        f"juegos godot sin evidencia de nivel 1 o 2: {sin_evidencia}"
    )


def test_f1_01_godot_fuente_evidencia_no_nula() -> None:
    #todos los juegos godot deben tener fuente_evidencia declarada
    manifiesto = _cargar_manifiesto_validado()
    sin_fuente = [
        j.appid for j in manifiesto.juegos
        if j.grupo == "godot" and not j.fuente_evidencia
    ]
    assert not sin_fuente, (
        f"juegos godot sin fuente_evidencia declarada: {sin_fuente}"
    )


def test_f1_01_general_sin_evidencia_nivel() -> None:
    #los juegos del grupo general no deben tener evidencia_nivel de motor godot
    manifiesto = _cargar_manifiesto_validado()
    con_nivel = [
        j.appid for j in manifiesto.juegos
        if j.grupo == "general" and j.evidencia_nivel is not None
    ]
    assert not con_nivel, (
        f"juegos del grupo general con evidencia_nivel declarada (no permitido): {con_nivel}"
    )


# ---------------------------------------------------------------------------
# f1-01e: campos obligatorios presentes en todas las entradas
# ---------------------------------------------------------------------------

CAMPOS_OBLIGATORIOS = ["appid", "grupo", "titulo", "release_date", "criterio_inclusion"]


@pytest.mark.parametrize("campo", CAMPOS_OBLIGATORIOS)
def test_f1_01_campo_obligatorio_presente(campo: str) -> None:
    #ningun juego puede tener el campo obligatorio ausente o nulo
    manifiesto = _cargar_manifiesto_validado()
    faltantes = [
        j.appid for j in manifiesto.juegos
        if not getattr(j, campo, None)
    ]
    assert not faltantes, (
        f"campo obligatorio {campo!r} ausente o vacio en appids: {faltantes}"
    )


# ---------------------------------------------------------------------------
# f1-01f: validacion completa del esquema con pydantic (caso de bloqueo)
# ---------------------------------------------------------------------------

def test_f1_01_esquema_pydantic_valida_manifiesto_completo() -> None:
    #el manifiesto completo debe pasar la validacion pydantic sin errores
    _cargar_manifiesto_validado()  #lanza pytest.fail si hay error de validacion


def test_f1_01_pydantic_bloquea_godot_sin_evidencia() -> None:
    #un juego godot sin evidencia_nivel debe ser rechazado por el esquema
    datos_invalidos = {
        "appid": 999999,
        "grupo": "godot",
        "titulo": "juego de prueba",
        "release_date": "2024-06-01",
        "evidencia_nivel": None,  #invalido para godot
        "fuente_evidencia": None,
        "criterio_inclusion": "criterio de prueba",
    }
    with pytest.raises(ValidationError):
        EntradaManifiesto(**datos_invalidos)


def test_f1_01_pydantic_bloquea_fecha_fuera_de_ventana() -> None:
    #una release_date fuera de 2024-2026 debe ser rechazada
    datos_invalidos = {
        "appid": 999998,
        "grupo": "general",
        "titulo": "juego antiguo",
        "release_date": "2023-12-31",  #fuera de ventana
        "criterio_inclusion": "criterio de prueba",
    }
    with pytest.raises(ValidationError):
        EntradaManifiesto(**datos_invalidos)


def test_f1_01_pydantic_bloquea_grupo_invalido() -> None:
    #un grupo distinto de godot/general debe ser rechazado
    datos_invalidos = {
        "appid": 999997,
        "grupo": "unity",  #invalido
        "titulo": "juego unity",
        "release_date": "2024-06-01",
        "criterio_inclusion": "criterio de prueba",
    }
    with pytest.raises(ValidationError):
        EntradaManifiesto(**datos_invalidos)


def test_f1_01_pydantic_bloquea_general_con_evidencia_nivel() -> None:
    #un juego general con evidencia_nivel declarado debe ser rechazado
    datos_invalidos = {
        "appid": 999996,
        "grupo": "general",
        "titulo": "juego sin godot",
        "release_date": "2024-06-01",
        "evidencia_nivel": 1,  #no permitido para general
        "criterio_inclusion": "criterio de prueba",
    }
    with pytest.raises(ValidationError):
        EntradaManifiesto(**datos_invalidos)


# ---------------------------------------------------------------------------
# f1-01g: integridad sha256 del manifiesto
# ---------------------------------------------------------------------------

def test_f1_01_sha256_campo_en_yaml_coincide_con_archivo() -> None:
    """el sha256_manifiesto dentro del yaml debe coincidir con el sha256 del archivo.

    nota: el campo sha256_manifiesto registra el hash del archivo tal como queda
    tras ser escrito — esto crea una circularidad que se rompe calculando el hash
    del archivo en disco y comparandolo con el valor declarado en el campo.
    en la practica, el valor se calcula sobre el archivo ya finalizado y luego
    se inserta en el campo, por lo que el hash del archivo en disco con el campo
    ya presente es el valor canónico.
    """
    manifiesto = _cargar_manifiesto_validado()
    sha_calculado = _calcular_sha256_manifiesto()
    assert manifiesto.sha256_manifiesto.lower() == sha_calculado, (
        f"sha256_manifiesto en el yaml ({manifiesto.sha256_manifiesto!r}) "
        f"no coincide con el sha256 del archivo en disco ({sha_calculado!r})"
    )


def test_f1_01_sha256_registrado_en_changelog() -> None:
    #el changelog debe contener una linea con la huella sha256 del manifiesto
    sha_changelog = _extraer_sha256_desde_changelog()
    assert sha_changelog is not None, (
        "no se encontro 'sha256-muestra-control: <hexdigest>' en changelog.md — "
        "registrar la huella al cerrar f1-01"
    )


def test_f1_01_sha256_changelog_coincide_con_archivo() -> None:
    #el sha256 en changelog debe coincidir con el sha256 del archivo en disco
    sha_changelog = _extraer_sha256_desde_changelog()
    assert sha_changelog is not None, (
        "sha256-muestra-control no encontrado en changelog.md"
    )
    sha_calculado = _calcular_sha256_manifiesto()
    assert sha_changelog == sha_calculado, (
        f"sha256 en changelog ({sha_changelog!r}) no coincide "
        f"con el sha256 del archivo en disco ({sha_calculado!r})"
    )
