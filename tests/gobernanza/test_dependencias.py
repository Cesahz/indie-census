#suite de contrato de dependencias y configuracion de entorno
#verifica separacion entre produccion y desarrollo, sincronia con pyproject.toml y cobertura en ci
import ast
import re
import sys
from pathlib import Path

import yaml

#raiz del repositorio: dos niveles arriba de este archivo (tests/gobernanza/)
REPO_ROOT = Path(__file__).resolve().parents[2]

#mapeo de nombres de modulo importados en python hacia nombres de paquete en pypi
IMPORT_A_PAQUETE = {
    "yaml": "pyyaml",
    "pyarrow": "pyarrow",
    "pydantic": "pydantic",
    "requests": "requests",
    "pandas": "pandas",
    "pytest": "pytest",
}

#imports opcionales protegidos por bloques try/except ImportError
IMPORTS_OPCIONALES = {"dotenv"}

#herramientas exclusivas de desarrollo que no deben contaminar requirements.txt de produccion
HERRAMIENTAS_DEV = {"pytest", "pytest-cov", "ruff"}

PATRON_PIN_EXACTO = re.compile(r"^([a-zA-Z0-9_\-]+)==([0-9]+\.[0-9]+\.[0-9]+)$")
PATRON_RANGO_TOML = re.compile(r'^"([a-zA-Z0-9_\-]+)>=([0-9]+\.[0-9]+\.[0-9]+)"$')


def _leer_pines_requirements(ruta: Path) -> dict[str, str]:
    """Extraer diccionario {paquete: version} de un archivo requirements con fijado exacto."""
    assert ruta.is_file(), f"Archivo de dependencias ausente: {ruta.name}"
    pines: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or limpia.startswith("-r "):
            continue
        match = PATRON_PIN_EXACTO.match(limpia)
        assert match, (
            f"Dependencia sin fijado exacto (==) en {ruta.name}: {limpia!r}"
        )
        nombre, version = match.groups()
        pines[nombre.lower()] = version
    return pines


def _extraer_listas_pyproject(ruta: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Extraer dependencias de produccion y de desarrollo declaradas en pyproject.toml."""
    assert ruta.is_file(), "Archivo pyproject.toml ausente en la raiz del repositorio"
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    prod: dict[str, str] = {}
    dev: dict[str, str] = {}
    estado: str | None = None

    for linea in lineas:
        limpia = linea.strip()
        if limpia.startswith("dependencies = ["):
            estado = "prod"
            continue
        if limpia.startswith("dev = ["):
            estado = "dev"
            continue
        if estado in {"prod", "dev"}:
            if limpia == "]":
                estado = None
                continue
            item = limpia.rstrip(",")
            match = PATRON_RANGO_TOML.match(item)
            assert match, f"Entrada invalida en pyproject.toml ({estado}): {limpia!r}"
            paquete, version_min = match.groups()
            if estado == "prod":
                prod[paquete.lower()] = version_min
            else:
                dev[paquete.lower()] = version_min

    return prod, dev


def _extraer_imports_terceros(directorio: Path) -> set[str]:
    """Escanear arbol ast de un directorio y devolver modulos externos a la libreria estandar."""
    modulos: set[str] = set()
    stdlib = set(sys.stdlib_module_names) | {"src", "tests"}
    for archivo in directorio.rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8-sig"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    modulos.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulos.add(nodo.module.split(".")[0])
    return modulos - stdlib - IMPORTS_OPCIONALES


def test_separacion_produccion_y_desarrollo_en_requirements() -> None:
    """Verificar que requirements.txt solo contiene produccion y requirements-dev.txt las de prueba."""
    req_prod = _leer_pines_requirements(REPO_ROOT / "requirements.txt")
    req_dev = _leer_pines_requirements(REPO_ROOT / "requirements-dev.txt")

    #ninguna herramienta de desarrollo debe estar mezclada en requirements.txt
    contaminacion = set(req_prod.keys()) & HERRAMIENTAS_DEV
    assert not contaminacion, (
        f"Herramientas de desarrollo mezcladas en requirements.txt: {sorted(contaminacion)}"
    )

    #requirements-dev.txt debe incluir la directiva -r requirements.txt y todas las herramientas dev
    lineas_dev = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    assert any(linea.strip() == "-r requirements.txt" for linea in lineas_dev), (
        "requirements-dev.txt debe heredar de requirements.txt mediante '-r requirements.txt'"
    )
    faltantes_dev = HERRAMIENTAS_DEV - set(req_dev.keys())
    assert not faltantes_dev, (
        f"Herramientas de desarrollo ausentes en requirements-dev.txt: {sorted(faltantes_dev)}"
    )


def test_sincronia_pyproject_con_requirements() -> None:
    """Verificar que pyproject.toml declara exactamente los mismos paquetes que requirements."""
    req_prod = _leer_pines_requirements(REPO_ROOT / "requirements.txt")
    req_dev = _leer_pines_requirements(REPO_ROOT / "requirements-dev.txt")
    toml_prod, toml_dev = _extraer_listas_pyproject(REPO_ROOT / "pyproject.toml")

    assert set(toml_prod.keys()) == set(req_prod.keys()), (
        f"Desincronizacion entre pyproject.toml [project.dependencies] ({sorted(toml_prod)}) "
        f"y requirements.txt ({sorted(req_prod)})"
    )
    assert set(toml_dev.keys()) == set(req_dev.keys()), (
        f"Desincronizacion entre pyproject.toml [project.optional-dependencies.dev] ({sorted(toml_dev)}) "
        f"y requirements-dev.txt ({sorted(req_dev)})"
    )

    #verificar que las versiones minimas de pyproject.toml coinciden con las fijadas
    for pkg, ver_fijada in req_prod.items():
        assert toml_prod[pkg] == ver_fijada, (
            f"Version en pyproject.toml para {pkg} ({toml_prod[pkg]}) difiere de requirements.txt ({ver_fijada})"
        )
    for pkg, ver_fijada in req_dev.items():
        assert toml_dev[pkg] == ver_fijada, (
            f"Version en pyproject.toml para {pkg} ({toml_dev[pkg]}) difiere de requirements-dev.txt ({ver_fijada})"
        )


def test_imports_codigo_declarados_en_dependencias() -> None:
    """Verificar que todo paquete externo importado en src/ y tests/ esta declarado."""
    req_prod = _leer_pines_requirements(REPO_ROOT / "requirements.txt")
    req_dev = _leer_pines_requirements(REPO_ROOT / "requirements-dev.txt")

    imports_src = _extraer_imports_terceros(REPO_ROOT / "src")
    for mod in sorted(imports_src):
        paquete = IMPORT_A_PAQUETE.get(mod, mod).lower()
        assert paquete in req_prod, (
            f"Modulo {mod!r} (paquete {paquete!r}) importado en src/ pero no declarado en requirements.txt"
        )

    imports_tests = _extraer_imports_terceros(REPO_ROOT / "tests")
    universo_dev = set(req_prod.keys()) | set(req_dev.keys())
    for mod in sorted(imports_tests):
        paquete = IMPORT_A_PAQUETE.get(mod, mod).lower()
        assert paquete in universo_dev, (
            f"Modulo {mod!r} (paquete {paquete!r}) importado en tests/ pero no declarado en requirements"
        )


def test_ci_instala_requirements_dev_y_exige_umbral_cobertura_real() -> None:
    """Verificar que el flujo de ci instala requirements-dev.txt y exige cobertura real (>0)."""
    ruta_ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ruta_ci.is_file(), "Flujo de ci .github/workflows/ci.yml ausente"
    texto_ci = ruta_ci.read_text(encoding="utf-8")

    #debe instalar requirements-dev.txt
    assert "requirements-dev.txt" in texto_ci, (
        "ci.yml debe instalar requirements-dev.txt para contar con pytest y ruff"
    )

    #el umbral de cobertura no puede ser 0
    match_cov = re.search(r"--cov-fail-under=(\d+)", texto_ci)
    assert match_cov, "ci.yml debe definir --cov-fail-under=<umbral>"
    umbral = int(match_cov.group(1))
    assert umbral >= 85, (
        f"El umbral de cobertura en ci.yml debe ser real (>=85), se encontro: {umbral}"
    )

    #validar que el yaml de ci es sintacticamente valido
    datos_ci = yaml.safe_load(texto_ci)
    assert isinstance(datos_ci, dict), "ci.yml no es un documento yaml valido"


def test_registros_adr_publicos_existen_y_cumplen_estructura() -> None:
    """Verificar que el directorio publico adr/ contiene decisiones numeradas con estructura formal."""
    dir_adr = REPO_ROOT / "adr"
    assert dir_adr.is_dir(), "Directorio publico adr/ ausente en la raiz del repositorio"
    assert (dir_adr / "README.md").is_file(), "Indice adr/README.md ausente"

    archivos_adr = sorted(dir_adr.glob("[0-9][0-9][0-9][0-9]-*.md"))
    assert len(archivos_adr) >= 5, (
        f"Se esperaban al menos 5 registros ADR publicos en adr/, se encontraron: {len(archivos_adr)}"
    )

    secciones_obligatorias = [
        "## Contexto y Problema",
        "## Alternativas Consideradas",
        "## Decisión",
        "## Consecuencias y Costos Aceptados",
    ]
    for idx, ruta_adr in enumerate(archivos_adr, start=1):
        prefijo_esperado = f"{idx:04d}-"
        assert ruta_adr.name.startswith(prefijo_esperado), (
            f"Numeracion secuencial rota en adr/: se esperaba prefijo {prefijo_esperado}, "
            f"se encontro {ruta_adr.name}"
        )
        contenido = ruta_adr.read_text(encoding="utf-8")
        for seccion in secciones_obligatorias:
            assert seccion in contenido, (
                f"El registro {ruta_adr.name} no contiene la seccion obligatoria {seccion!r}"
            )
