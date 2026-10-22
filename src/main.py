"""Punto de entrada de la aplicación (se ejecuta desde la raíz del proyecto).

Ejemplos:
    python -m src.main --entrada data/viajes.csv --desde 2026-09-15 --hasta 2026-09-16
    python -m src.main --entrada data/viajes.json --desde "2026-09-15 07:00:00" --hasta "2026-09-15 10:00:00"
"""

import argparse
import sys

from src.dominio import ErrorDatos, Periodo
from src.fuentes import crear_fuente
from src.pipeline import AplicacionEcobici, guardar_balance, guardar_rechazos


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reporte operativo de movimientos de Ecobici (TP2 - POD)."
    )
    parser.add_argument("--entrada", required=True, help="archivo de viajes (.csv o .json)")
    parser.add_argument("--desde", required=True,
                        help="inicio del período, incluido (AAAA-MM-DD o AAAA-MM-DD HH:MM:SS)")
    parser.add_argument("--hasta", required=True,
                        help="fin del período, excluido (AAAA-MM-DD o AAAA-MM-DD HH:MM:SS)")
    parser.add_argument("--salida", default="outputs", help="carpeta de salida (por defecto: outputs)")
    return parser


def main(argv=None) -> int:
    """Devuelve 0 si todo salió bien y 1 si hubo un error esperado (con mensaje claro)."""
    argumentos = construir_parser().parse_args(argv)
    try:
        periodo = Periodo.desde_texto(argumentos.desde, argumentos.hasta)
        resultado = AplicacionEcobici(crear_fuente(argumentos.entrada)).ejecutar(periodo)
        ruta_balance = guardar_balance(resultado.balance, periodo, argumentos.salida)
        ruta_rechazos = guardar_rechazos(resultado.rechazados, argumentos.salida)
    except (ErrorDatos, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    a = resultado.auditoria
    print(f"Período: {periodo.etiqueta()}")
    print(
        f"Entrada: {a['entrada']} registros | válidos: {a['validos']} | rechazados: {a['rechazados']} | "
        f"viajes en el período: {a['en_periodo']}"
    )
    if resultado.balance.empty:
        print("No hay viajes en el período indicado: el reporte está vacío.")
    else:
        print(resultado.balance.to_string(index=False))
    print(f"Reporte guardado en: {ruta_balance}")
    print(f"Rechazos guardados en: {ruta_rechazos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
