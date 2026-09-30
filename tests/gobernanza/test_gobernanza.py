#suite de gobernanza — fase 0
#cubre criterios f0-01, f0-02, f0-04, f0-06, f0-07, f0-08
#sin acceso a red, sin reloj real, sin azar sin semilla
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

import pytest
import yaml
from pydantic import BaseModel, ValidationError

#raiz del repositorio: dos niveles arriba de este archivo (tests/gobernanza/)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# f0-01: arbol canonico de directorios
# ---------------------------------------------------------------------------

DIRECTORIOS_CANONICOS = [
    "config",
    "src",
    "src/extract",
    "src/transform",
    "src/classify",
    "src/quality",
    "tests",
    "tests/gobernanza",
    "tests/extract",
    "tests/transform",
    "tests/classify",
    "tests/quality",
    "tests/fixtures",
    "data",
    "data/bronce",
    "data/plata",
    "data/oro",
]

ARCHIVOS_CANONICOS = [
    "changelog.md",
    "readme.md",
    "requirements.txt",
    ".gitignore",
    "config/taxonomy.yaml",
    "config/milestones.yaml",
    "config/muestra_control.yaml",
    "src/version.py",
    "src/__init__.py",
]

GITKEEPS_CANONICOS = [
    "data/bronce/.gitkeep",
    "data/plata/.gitkeep",
    "data/oro/.gitkeep",
]


@pytest.mark.parametrize("relpath", DIRECTORIOS_CANONICOS)
def test_f0_01_directorio_canonico_existe(relpath: str) -> None:
    #verificar que cada directorio del arbol canonico esta presente
    ruta = REPO_ROOT / relpath
    assert ruta.is_dir(), f"directorio canonico ausente: {relpath}"


@pytest.mark.parametrize("relpath", ARCHIVOS_CANONICOS)
def test_f0_01_archivo_canonico_existe(relpath: str) -> None:
    #verificar que cada archivo del arbol canonico esta presente
    ruta = REPO_ROOT / relpath
    assert ruta.is_file(), f"archivo canonico ausente: {relpath}"


@pytest.mark.parametrize("relpath", GITKEEPS_CANONICOS)
def test_f0_01_gitkeep_canonico_existe(relpath: str) -> None:
    #verificar que los marcadores de carpeta de data/ estan presentes
    ruta = REPO_ROOT / relpath
    assert ruta.is_file(), f"marcador .gitkeep ausente: {relpath}"


# ---------------------------------------------------------------------------
# f0-02: efectividad del .gitignore
# ---------------------------------------------------------------------------

def _git_ls_files(*rutas: str) -> list[str]:
    """ejecutar git ls-files y devolver la lista de rutas rastreadas."""
    resultado = subprocess.run(
        ["git", "ls-files", "--", *rutas],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [linea.strip() for linea in resultado.stdout.splitlines() if linea.strip()]


def _git_check_ignore(ruta_relativa: str) -> bool:
    """devolver true si git trata la ruta como ignorada."""
    resultado = subprocess.run(
        ["git", "check-ignore", "-q", ruta_relativa],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return resultado.returncode == 0


def test_f0_02_docs_no_rastreable() -> None:
    #la carpeta docs/ no debe tener ninguna ruta rastreada por git
    rastreados = _git_ls_files("docs/")
    assert rastreados == [], (
        f"docs/ contiene rutas rastreadas (debe estar completamente ignorada): {rastreados}"
    )


def test_f0_02_docs_ignorada_por_check_ignore() -> None:
    #git check-ignore confirma que docs/ esta ignorada
    assert _git_check_ignore("docs/"), "docs/ no esta declarada como ignorada en .gitignore"


def test_f0_02_data_archivos_no_rastreables() -> None:
    #ningun archivo de datos real debe estar rastreado (solo .gitkeep)
    rastreados = _git_ls_files("data/")
    no_gitkeep = [r for r in rastreados if not r.endswith(".gitkeep")]
    assert no_gitkeep == [], (
        f"data/ contiene archivos rastreados que no son .gitkeep: {no_gitkeep}"
    )


def test_f0_02_gitkeep_si_rastreados() -> None:
    #los marcadores .gitkeep deben estar rastreados por git
    rastreados = _git_ls_files("data/")
    gitkeeps = [r for r in rastreados if r.endswith(".gitkeep")]
    assert len(gitkeeps) >= 3, (
        f"se esperaban al menos 3 .gitkeep rastreados en data/, se encontraron: {gitkeeps}"
    )


@pytest.mark.parametrize("relpath", [
    "data/bronce/.gitkeep",
    "data/plata/.gitkeep",
    "data/oro/.gitkeep",
])
def test_f0_02_gitkeep_individual_rastreado(relpath: str) -> None:
    #verificar que cada .gitkeep canonico aparece en el indice de git
    rastreados = _git_ls_files(relpath)
    assert rastreados != [], f".gitkeep no rastreado: {relpath}"


# ---------------------------------------------------------------------------
# f0-04: regex de conventional commits (normas seccion 3.4)
# ---------------------------------------------------------------------------

PATRON_COMMIT = re.compile(
    r"^(feat|fix|test|chore|refactor|docs)(\([a-z_]+\))?!?: "
    r"[a-z0-9][a-z0-9 _./,\-]{0,70}(?<![ ._/,\-])$"
)

#ejemplos que deben pasar
COMMITS_VALIDOS = [
    "feat: generar pipeline de ingesta cruda",
    "test: agregar validacion de esquema en capa plata",
    "fix(extract): corregir reintento ante 429",
    "chore: fijar versiones en requirements.txt",
    "refactor(quality): separar contratos de nulos y duplicados",
    "feat(transform): normalizar fechas a utc",
    "docs: actualizar readme con guia de reproduccion",
    "chore!: actualizar dependencias incompatibles",
    "feat(extract)!: redisenar cliente http",
    "test: agregar fixture de respuesta 429",
    "fix: corregir escritura atomica en capa plata",
    "chore(quality): agregar umbral de cobertura",
]

#ejemplos que deben fallar
COMMITS_INVALIDOS = [
    "feat: Generar pipeline",
    "test: agregu\u00e9 validaci\u00f3n de esquema",  #tildes — charset no admitido
    "test: anad\u00ed prueba de esquema",             #tilde — charset no admitido
    "fix: corrigiendo reintento.",
    "update: fijar versiones",
    " feat: corregir algo",
    "feat:sin espacio tras dos puntos",
    "feat: ",
    "FEAT: algo",
    "feat: corregir algo.",
    "feat(Modulo): algo",
    "feat: " + "a" * 75,
]


@pytest.mark.parametrize("mensaje", COMMITS_VALIDOS)
def test_f0_04_commit_valido_acepta(mensaje: str) -> None:
    #el patron debe aceptar mensajes bien formados
    assert PATRON_COMMIT.match(mensaje), (
        f"se esperaba aceptar el commit pero fue rechazado: {mensaje!r}"
    )


@pytest.mark.parametrize("mensaje", COMMITS_INVALIDOS)
def test_f0_04_commit_invalido_rechaza(mensaje: str) -> None:
    #el patron debe rechazar mensajes mal formados
    assert not PATRON_COMMIT.match(mensaje), (
        f"se esperaba rechazar el commit pero fue aceptado: {mensaje!r}"
    )


# ---------------------------------------------------------------------------
# f0-06: esquemas pydantic para config/ (contenido vacio permitido)
# ---------------------------------------------------------------------------

class TaxonomySchema(BaseModel):
    """esquema minimo para taxonomy.yaml; todos los campos son opcionales en fase 0."""

    motores: Optional[Any] = None
    generos: Optional[Any] = None
    ai_disclosure: Optional[Any] = None
    umbrales: Optional[Any] = None


class MilestoneEntry(BaseModel):
    """entrada individual de hito; todos los campos opcionales en fase 0."""

    fecha: Optional[str] = None
    tipo: Optional[str] = None
    fuente: Optional[str] = None
    descripcion: Optional[str] = None


class MilestonesSchema(BaseModel):
    """esquema de milestones.yaml; lista de hitos o ninguno en fase 0."""

    hitos: Optional[list[MilestoneEntry]] = None


class MuestraEntrada(BaseModel):
    """entrada individual del manifiesto de muestra."""

    appid: Optional[int] = None
    grupo: Optional[str] = None
    evidencia_nivel: Optional[int] = None
    fuente: Optional[str] = None


class MuestraControlSchema(BaseModel):
    """esquema de muestra_control.yaml; lista de juegos o ninguno en fase 0."""

    juegos: Optional[list[MuestraEntrada]] = None
    sha256_manifiesto: Optional[str] = None


def _cargar_yaml(nombre_archivo: str) -> Any:
    """cargar archivo yaml y devolver su contenido parseado (none si vacio)."""
    ruta = REPO_ROOT / "config" / nombre_archivo
    with ruta.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_f0_06_taxonomy_yaml_existe_y_carga() -> None:
    #el archivo taxonomy.yaml debe existir y ser parseable
    ruta = REPO_ROOT / "config" / "taxonomy.yaml"
    assert ruta.is_file(), "config/taxonomy.yaml no existe"
    contenido = _cargar_yaml("taxonomy.yaml")
    assert contenido is None or isinstance(contenido, dict), (
        f"taxonomy.yaml debe ser un mapping o estar vacio, se obtuvo: {type(contenido)}"
    )


def test_f0_06_taxonomy_yaml_valida_con_pydantic() -> None:
    #taxonomy.yaml debe ser valido contra TaxonomySchema
    contenido = _cargar_yaml("taxonomy.yaml") or {}
    try:
        TaxonomySchema(**contenido)
    except ValidationError as exc:
        pytest.fail(f"taxonomy.yaml no pasa el esquema pydantic: {exc}")


def test_f0_06_milestones_yaml_existe_y_carga() -> None:
    #el archivo milestones.yaml debe existir y ser parseable
    ruta = REPO_ROOT / "config" / "milestones.yaml"
    assert ruta.is_file(), "config/milestones.yaml no existe"
    contenido = _cargar_yaml("milestones.yaml")
    assert contenido is None or isinstance(contenido, dict), (
        f"milestones.yaml debe ser un mapping o estar vacio, se obtuvo: {type(contenido)}"
    )


def test_f0_06_milestones_yaml_valida_con_pydantic() -> None:
    #milestones.yaml debe ser valido contra MilestonesSchema
    contenido = _cargar_yaml("milestones.yaml") or {}
    try:
        MilestonesSchema(**contenido)
    except ValidationError as exc:
        pytest.fail(f"milestones.yaml no pasa el esquema pydantic: {exc}")


def test_f0_06_muestra_control_yaml_existe_y_carga() -> None:
    #el archivo muestra_control.yaml debe existir y ser parseable
    ruta = REPO_ROOT / "config" / "muestra_control.yaml"
    assert ruta.is_file(), "config/muestra_control.yaml no existe"
    contenido = _cargar_yaml("muestra_control.yaml")
    assert contenido is None or isinstance(contenido, dict), (
        f"muestra_control.yaml debe ser un mapping o estar vacio, se obtuvo: {type(contenido)}"
    )


def test_f0_06_muestra_control_yaml_valida_con_pydantic() -> None:
    #muestra_control.yaml debe ser valido contra MuestraControlSchema
    contenido = _cargar_yaml("muestra_control.yaml") or {}
    try:
        MuestraControlSchema(**contenido)
    except ValidationError as exc:
        pytest.fail(f"muestra_control.yaml no pasa el esquema pydantic: {exc}")


def test_f0_06_muestra_control_grupos_validos() -> None:
    #si hay entradas, el campo grupo solo admite 'godot' o 'general'
    contenido = _cargar_yaml("muestra_control.yaml") or {}
    schema = MuestraControlSchema(**contenido)
    if schema.juegos:
        for entrada in schema.juegos:
            if entrada.grupo is not None:
                assert entrada.grupo in {"godot", "general"}, (
                    f"grupo invalido en muestra_control.yaml: {entrada.grupo!r}"
                )


def test_f0_06_muestra_control_cardinalidad() -> None:
    #si la muestra esta poblada, debe tener exactamente 100 entradas con 50/50
    contenido = _cargar_yaml("muestra_control.yaml") or {}
    schema = MuestraControlSchema(**contenido)
    if not schema.juegos:
        pytest.skip("muestra_control.yaml vacio — validacion de cardinalidad diferida a f1")
    assert len(schema.juegos) == 100, (
        f"se esperaban 100 juegos en la muestra, se encontraron {len(schema.juegos)}"
    )
    godot_count = sum(1 for j in schema.juegos if j.grupo == "godot")
    general_count = sum(1 for j in schema.juegos if j.grupo == "general")
    assert godot_count == 50, f"se esperaban 50 del grupo godot, se encontraron {godot_count}"
    assert general_count == 50, f"se esperaban 50 del grupo general, se encontraron {general_count}"


# ---------------------------------------------------------------------------
# f0-07: formato de changelog.md
# ---------------------------------------------------------------------------

SECCIONES_ADMITIDAS = {"agregado", "cambiado", "corregido", "eliminado"}
PATRON_VERSION_RELEASE = re.compile(r"^## \[\d+\.\d+\.\d+\] - \d{4}-\d{2}-\d{2}$")
PATRON_SIN_PUBLICAR = re.compile(r"^## \[sin publicar\]$")
PATRON_SECCION = re.compile(r"^### (.+)$")


def _leer_changelog() -> list[str]:
    """leer changelog.md y devolver lista de lineas sin salto final."""
    ruta = REPO_ROOT / "changelog.md"
    assert ruta.is_file(), "changelog.md no existe"
    return ruta.read_text(encoding="utf-8").splitlines()


def test_f0_07_changelog_existe() -> None:
    #changelog.md debe existir en la raiz del repositorio
    assert (REPO_ROOT / "changelog.md").is_file(), "changelog.md no existe"


def test_f0_07_changelog_tiene_seccion_sin_publicar() -> None:
    #changelog.md debe tener al menos una entrada ## [sin publicar]
    lineas = _leer_changelog()
    tiene_sin_publicar = any(PATRON_SIN_PUBLICAR.match(linea.strip()) for linea in lineas)
    assert tiene_sin_publicar, (
        "changelog.md no contiene la seccion '## [sin publicar]' requerida"
    )


def test_f0_07_changelog_sin_publicar_es_primera_entrada() -> None:
    #la primera entrada de version debe ser ## [sin publicar]
    lineas = _leer_changelog()
    for linea in lineas:
        stripped = linea.strip()
        if stripped.startswith("## ["):
            assert PATRON_SIN_PUBLICAR.match(stripped), (
                f"la primera entrada de version no es '[sin publicar]': {stripped!r}"
            )
            break
    else:
        pytest.fail("changelog.md no contiene ninguna entrada de version")


def test_f0_07_changelog_secciones_validas() -> None:
    #las secciones ### solo pueden ser las admitidas por las normas
    lineas = _leer_changelog()
    for linea in lineas:
        match = PATRON_SECCION.match(linea.strip())
        if match:
            nombre_seccion = match.group(1).strip().lower()
            assert nombre_seccion in SECCIONES_ADMITIDAS, (
                f"seccion de changelog no admitida: {nombre_seccion!r} "
                f"(admitidas: {sorted(SECCIONES_ADMITIDAS)})"
            )


def test_f0_07_changelog_entradas_de_version_con_formato_correcto() -> None:
    #las entradas ## [x.y.z] - AAAA-MM-DD deben seguir el patron semver
    lineas = _leer_changelog()
    for linea in lineas:
        stripped = linea.strip()
        if stripped.startswith("## [") and not PATRON_SIN_PUBLICAR.match(stripped):
            assert PATRON_VERSION_RELEASE.match(stripped), (
                f"entrada de version con formato invalido: {stripped!r}"
            )


def test_f0_07_changelog_no_vacio_bajo_sin_publicar() -> None:
    #la seccion [sin publicar] debe tener al menos un item de lista
    lineas = _leer_changelog()
    en_sin_publicar = False
    tiene_item = False
    for linea in lineas:
        stripped = linea.strip()
        if PATRON_SIN_PUBLICAR.match(stripped):
            en_sin_publicar = True
            continue
        if en_sin_publicar:
            if stripped.startswith("## ["):
                break
            if stripped.startswith("- "):
                tiene_item = True
                break
    assert tiene_item, (
        "la seccion '## [sin publicar]' de changelog.md no tiene ningun item de lista"
    )


# ---------------------------------------------------------------------------
# f0-08: coherencia version.py <-> changelog.md
# ---------------------------------------------------------------------------

def _extraer_version_py() -> str:
    """leer la version definida en src/version.py."""
    ruta = REPO_ROOT / "src" / "version.py"
    assert ruta.is_file(), "src/version.py no existe"
    contenido = ruta.read_text(encoding="utf-8")
    patron = re.compile(r'^PIPELINE_VERSION\s*=\s*["\x27]([^"\x27]+)["\x27]', re.MULTILINE)
    match = patron.search(contenido)
    assert match, "PIPELINE_VERSION no encontrado en src/version.py"
    return match.group(1)


def _extraer_ultima_version_changelog() -> Optional[str]:
    """devolver la ultima version publicada de changelog.md o none si solo hay [sin publicar]."""
    lineas = _leer_changelog()
    for linea in lineas:
        stripped = linea.strip()
        match = PATRON_VERSION_RELEASE.match(stripped)
        if match:
            version_match = re.search(r"\[(\d+\.\d+\.\d+)\]", stripped)
            if version_match:
                return version_match.group(1)
    return None


def test_f0_08_version_py_formato_semver() -> None:
    #PIPELINE_VERSION debe seguir el formato semver x.y.z
    version = _extraer_version_py()
    patron_semver = re.compile(r"^\d+\.\d+\.\d+$")
    assert patron_semver.match(version), (
        f"PIPELINE_VERSION no sigue formato semver: {version!r}"
    )


def test_f0_08_version_py_existe_y_define_constante() -> None:
    #src/version.py debe existir y definir PIPELINE_VERSION
    version = _extraer_version_py()
    assert version, "PIPELINE_VERSION esta vacia en src/version.py"


def test_f0_08_coherencia_version_y_changelog() -> None:
    """verificar coherencia entre version.py y changelog.md.

    reglas:
    - si changelog solo tiene [sin publicar], version.py debe ser 0.0.0
    - si changelog tiene versiones publicadas, la version superior debe coincidir
      con PIPELINE_VERSION
    """
    version_py = _extraer_version_py()
    ultima_version_changelog = _extraer_ultima_version_changelog()

    if ultima_version_changelog is None:
        #estado inicial: solo [sin publicar] en el changelog
        assert version_py == "0.0.0", (
            f"changelog.md solo tiene [sin publicar] pero version.py no es 0.0.0: {version_py!r}"
        )
    else:
        #hay versiones publicadas: deben coincidir
        assert version_py == ultima_version_changelog, (
            f"version.py ({version_py!r}) no coincide con la ultima "
            f"version publicada en changelog.md ({ultima_version_changelog!r})"
        )


def test_f0_08_changelog_tiene_entrada_para_version_actual() -> None:
    """si version.py no es 0.0.0, debe existir una entrada en changelog.md."""
    version_py = _extraer_version_py()
    if version_py == "0.0.0":
        pytest.skip("version 0.0.0 no requiere entrada en changelog (estado inicial)")
    lineas = _leer_changelog()
    patron_version = re.compile(rf"^## \[{re.escape(version_py)}\] - \d{{4}}-\d{{2}}-\d{{2}}$")
    tiene_entrada = any(patron_version.match(linea.strip()) for linea in lineas)
    assert tiene_entrada, (
        f"no se encontro entrada '## [{version_py}] - AAAA-MM-DD' en changelog.md"
    )
