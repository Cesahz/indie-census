#script cli para exportacion reproducible del dataset publico
#ejecuta la exportacion dual (parquet + csv) y verifica checksums sha-256
import argparse
import sys
from pathlib import Path

#anadir raiz al path si se ejecuta como script independiente
raiz_proyecto = Path(__file__).resolve().parent.parent
if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))

from src.transform.exportar_dataset_publico import (  # noqa: E402
    exportar_dataset_publico,
    verificar_manifiesto_checksums,
)


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta el dataset publico de Indie Census en formatos Parquet y CSV con manifiesto SHA-256."
    )
    parser.add_argument(
        "--ruta-plata",
        type=Path,
        default=raiz_proyecto / "data" / "plata",
        help="Ruta al directorio de la Capa Plata (contiene plata_steam_*.parquet).",
    )
    parser.add_argument(
        "--ruta-oro",
        type=Path,
        default=raiz_proyecto / "data" / "oro" / "mart",
        help="Ruta al directorio de la Capa Oro (contiene gold_*.parquet).",
    )
    parser.add_argument(
        "--ruta-destino",
        type=Path,
        default=raiz_proyecto / "data" / "publico",
        help="Directorio de destino para la exportacion publica.",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="v0.4.0",
        help="Etiqueta de version de la distribucion (ej. v0.4.0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parsear_argumentos()
    print(f"Iniciando exportacion publica de Indie Census ({args.version})...")
    print(f"  Fuente Plata: {args.ruta_plata}")
    print(f"  Fuente Oro:   {args.ruta_oro}")
    print(f"  Destino:      {args.ruta_destino / args.version}")

    try:
        reporte = exportar_dataset_publico(
            ruta_plata=args.ruta_plata,
            ruta_oro=args.ruta_oro,
            ruta_destino=args.ruta_destino,
            version=args.version,
        )
    except Exception as e:
        print(f"ERROR durante la exportacion: {e}", file=sys.stderr)
        return 1

    print(f"\nExito: {reporte['total_tablas']} tablas exportadas en Parquet y CSV.")
    for item in reporte["archivos_generados"]:
        tamano_kb = item["bytes"] / 1024
        print(f"  [{item['formato'].upper()}] {item['tabla']} -> {item['filas']} filas ({tamano_kb:.1f} KB)")

    print(f"\nVerificando integridad criptografica en {reporte['manifiesto_checksums']}...")
    try:
        verificar_manifiesto_checksums(Path(reporte["manifiesto_checksums"]))
        print("Verificacion exitosa: todos los hashes SHA-256 coinciden con el contenido en disco.")
    except Exception as e:
        print(f"ERROR de verificacion de integridad: {e}", file=sys.stderr)
        return 1

    print("\nDataset publico listo para distribucion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
