"""Flujo de procesamiento del reporte de movimientos.

leer -> inspeccionar y validar -> seleccionar período -> registrar movimientos
-> generar balance -> verificar -> comunicar

Criterio de diseño: la lógica de transformación está en funciones que reciben
datos y devuelven resultados, sin leer ni escribir archivos. Los efectos
(guardar archivos, mostrar por pantalla) se concentran en los bordes del flujo.
"""

import pandas as pd

from src.dominio import (
    ErrorDatos,
    es_estacion_valida,
    es_viaje_valido,
    parsear_fecha,
)

COLUMNAS_VIAJE = ("viaje_id", "inicio", "fin", "estacion_origen", "estacion_destino")


# ---------------------------------------------------------------------------
# Validación y limpieza
# ---------------------------------------------------------------------------
def validar_esquema(tabla: pd.DataFrame) -> None:
    """Detiene el flujo si la tabla no sirve para el análisis.

    Política de errores: una tabla vacía o con columnas ausentes es un problema
    de toda la entrada, por eso se lanza una excepción y no se apartan filas.
    """
    if tabla.empty:
        raise ErrorDatos("La tabla de entrada está vacía.")
    faltan = set(COLUMNAS_VIAJE) - set(tabla.columns)
    if faltan:
        raise ErrorDatos("Faltan columnas: " + ", ".join(sorted(faltan)))


def _texto_o_none(valor):
    """Normaliza un valor a texto sin espacios; faltantes (None, NaN o vacío) pasan a None."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    return str(valor).strip() or None


def validar_recorridos(tabla: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa los viajes válidos de los rechazados.

    Devuelve `(validos, rechazados)`. Los rechazados conservan la fila original y
    una columna `motivo` con todas las reglas incumplidas. La tabla de entrada no
    se modifica. En `validos`, `inicio` y `fin` ya son fechas (datetime64).
    """
    validar_esquema(tabla)
    trabajo = tabla.loc[:, list(COLUMNAS_VIAJE)].copy()
    for columna in COLUMNAS_VIAJE:
        trabajo[columna] = trabajo[columna].map(_texto_o_none)

    inicio = pd.to_datetime(trabajo["inicio"].map(parsear_fecha))  # NaT si es inválida o falta
    fin = pd.to_datetime(trabajo["fin"].map(parsear_fecha))
    id_invalido = ~trabajo["viaje_id"].map(es_viaje_valido).astype(bool)
    origen_falta = trabajo["estacion_origen"].isna()
    destino_falta = trabajo["estacion_destino"].isna()

    # Una columna booleana por regla: True significa "la regla se viola".
    controles = pd.DataFrame(index=trabajo.index)
    controles["identificador de viaje inválido"] = id_invalido
    controles["identificador de viaje duplicado"] = (
        trabajo["viaje_id"].duplicated(keep="first") & ~id_invalido
    )
    controles["inicio faltante o inválido"] = inicio.isna()
    controles["fin faltante o inválido"] = fin.isna()
    controles["fin no posterior al inicio"] = fin <= inicio  # con NaT da False
    controles["estación de origen faltante"] = origen_falta
    controles["estación de origen con formato inválido"] = (
        ~origen_falta & ~trabajo["estacion_origen"].map(es_estacion_valida).astype(bool)
    )
    controles["estación de destino faltante"] = destino_falta
    controles["estación de destino con formato inválido"] = (
        ~destino_falta & ~trabajo["estacion_destino"].map(es_estacion_valida).astype(bool)
    )

    invalidos = controles.any(axis=1).to_numpy()
    columnas = list(controles.columns)
    motivos = [
        "; ".join(nombre for nombre, falla in zip(columnas, fila) if falla)
        for fila in controles.to_numpy()[invalidos]
    ]

    rechazados = tabla.loc[invalidos].copy()
    rechazados["motivo"] = motivos

    trabajo["inicio"] = inicio
    trabajo["fin"] = fin
    validos = trabajo.loc[~invalidos].reset_index(drop=True)

    if validos.empty:
        raise ErrorDatos("Ningún viaje es válido: revise el archivo de entrada.")
    return validos, rechazados
