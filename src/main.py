"""Punto de entrada de la aplicación: menú de consola.

Se ejecuta desde la raíz del proyecto:
    python -m src.main

El programa pregunta el archivo de viajes, el período y las opciones de salida.

"""

from pathlib import Path

from src.dominio import ErrorDatos, Periodo
from src.fuentes import crear_fuente
from src.pipeline import AplicacionEcobici, guardar_balance, guardar_rechazos


def pedir_datos(leer=input) -> dict:
    """Pregunta los datos de la consulta y los devuelve en un diccionario.

    Entradas: `leer`, la función que obtiene cada respuesta (por defecto `input`).
    Recibirla como parámetro permite probar el menú sin escribir por teclado.
    Salida: diccionario con entrada, desde, hasta, salida y graficar.
    Efectos: lee de la consola (o de `leer`).
    """
    def preguntar(texto, por_defecto=None):
        sufijo = f" [{por_defecto}]" if por_defecto else ""
        respuesta = leer(f"{texto}{sufijo}: ").strip()
        return respuesta or por_defecto

    return {
        "entrada": preguntar("Archivo de viajes (.csv o .json)", "data/viajes.csv"),
        "desde": preguntar("Desde, incluido (AAAA-MM-DD o AAAA-MM-DD HH:MM:SS)"),
        "hasta": preguntar("Hasta, excluido (AAAA-MM-DD o AAAA-MM-DD HH:MM:SS)"),
        "salida": preguntar("Carpeta de salida", "outputs"),
        "graficar": preguntar("¿Generar el gráfico? (s/n)", "n").lower() == "s",
    }


def ejecutar_reporte(entrada, desde, hasta, salida="outputs", graficar=False):
    """Ejecuta el flujo completo y guarda los resultados.

    Entradas: ruta del archivo, límites del período (texto), carpeta de salida y
    si se quiere el gráfico.
    Salida: `(resultado, rutas)`; `rutas` es un diccionario con los archivos creados.
    Efectos: crea la carpeta de salida y escribe el reporte, los rechazos y,
    opcionalmente, el gráfico.
    Errores: ErrorDatos o FileNotFoundError si la entrada o el período no son válidos.
    """
    if not desde or not hasta:
        raise ErrorDatos("Hay que indicar el inicio y el fin del período.")
    periodo = Periodo.desde_texto(desde, hasta)
    resultado = AplicacionEcobici(crear_fuente(entrada)).ejecutar(periodo)

    rutas = {
        "balance": guardar_balance(resultado.balance, periodo, salida),
        "rechazos": guardar_rechazos(resultado.rechazados, salida),
    }
    if graficar and not resultado.balance.empty:
        # Se importa acá para que matplotlib solo se necesite cuando se pide el gráfico.
        from src.visualizacion import graficar_balance

        rutas["grafico"] = graficar_balance(resultado, Path(salida) / "balance_estaciones.png")
    return resultado, rutas


def mostrar_resultado(resultado, rutas) -> None:
    """Imprime la auditoría y el reporte (efecto: escribe en la consola)."""
    a = resultado.auditoria
    print(f"Período: {resultado.periodo.etiqueta()}")
    print(
        f"Entrada: {a['entrada']} registros | válidos: {a['validos']} | rechazados: {a['rechazados']} | "
        f"viajes en el período: {a['en_periodo']}"
    )
    if resultado.balance.empty:
        print("No hay viajes en el período indicado: el reporte está vacío.")
    else:
        print(resultado.balance.to_string(index=False))
    for nombre, ruta in rutas.items():
        print(f"Guardado ({nombre}): {ruta}")


def main() -> None:
    """Menú de consola: pregunta, ejecuta y muestra; los errores esperados se informan sin traceback."""
    try:
        resultado, rutas = ejecutar_reporte(**pedir_datos())
    except (ErrorDatos, FileNotFoundError) as error:
        print(f"Error: {error}")
        return
    mostrar_resultado(resultado, rutas)


if __name__ == "__main__":
    main()
