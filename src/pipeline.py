"""Flujo de procesamiento del reporte de movimientos.

leer -> inspeccionar y validar -> seleccionar período -> registrar movimientos
-> generar balance -> verificar -> comunicar

Criterio de diseño: la lógica de transformación está en funciones que reciben
datos y devuelven resultados, sin leer ni escribir archivos. Los efectos
(guardar archivos, mostrar por pantalla) se concentran en los bordes del flujo.
"""

import pandas as pd

from src.dominio import (
    BalanceEstacion,
    ErrorDatos,
    Periodo,
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


# ---------------------------------------------------------------------------
# Selección de período y registro de movimientos
# ---------------------------------------------------------------------------
def seleccionar_periodo(viajes: pd.DataFrame, periodo: Periodo) -> pd.DataFrame:
    """Devuelve los viajes cuyo **inicio** cae en el período [desde, hasta).

    Decisión de la primera versión: el viaje se asigna al período por su hora de
    inicio. Si termina después del fin del período, igualmente se cuentan ambos
    extremos (salida y llegada). Un período sin viajes devuelve una tabla vacía.
    """
    dentro = (viajes["inicio"] >= periodo.desde) & (viajes["inicio"] < periodo.hasta)
    return viajes.loc[dentro].reset_index(drop=True)


def registrar_movimientos(viajes: pd.DataFrame) -> dict[str, BalanceEstacion]:
    """Acumula, por estación, una salida en el origen y una llegada en el destino de cada viaje."""
    balances: dict[str, BalanceEstacion] = {}

    def balance_de(codigo: str) -> BalanceEstacion:
        if codigo not in balances:
            balances[codigo] = BalanceEstacion(codigo)
        return balances[codigo]

    for origen, destino in zip(viajes["estacion_origen"], viajes["estacion_destino"]):
        balance_de(origen).registrar_salida()
        balance_de(destino).registrar_llegada()
    return balances


# ---------------------------------------------------------------------------
# Balance y verificación
# ---------------------------------------------------------------------------
COLUMNAS_BALANCE = ("estacion", "salidas", "llegadas", "balance_neto")


def generar_balance(balances: dict[str, BalanceEstacion]) -> pd.DataFrame:
    """Arma el reporte por estación: salidas, llegadas y balance neto (llegadas - salidas).

    Entradas: diccionario código de estación -> BalanceEstacion.
    Salida: DataFrame ordenado por código de estación; vacío (pero con sus
    columnas) si no hubo movimientos.
    Efectos: ninguno (función pura: no modifica los balances recibidos).
    """
    filas = [balances[codigo].a_diccionario() for codigo in sorted(balances)]
    return pd.DataFrame(filas, columns=list(COLUMNAS_BALANCE))


def verificar_balance(balance: pd.DataFrame, viajes: pd.DataFrame) -> None:
    """Comprueba propiedades que cualquier balance correcto debe cumplir.

    No alcanza con que el programa termine sin errores. Cada viaje aporta una
    salida y una llegada, por lo tanto:
    1. la suma de salidas es igual a la cantidad de viajes seleccionados;
    2. la suma de llegadas es igual a la cantidad de viajes seleccionados;
    3. la suma de los balances netos de todas las estaciones es cero
       (lo que sale de un lugar llega a otro);
    4. el balance de cada estación es llegadas - salidas.

    Errores: ErrorDatos si alguna propiedad no se cumple.
    """
    cantidad = len(viajes)
    if int(balance["salidas"].sum()) != cantidad:
        raise ErrorDatos("Balance inconsistente: las salidas no coinciden con los viajes.")
    if int(balance["llegadas"].sum()) != cantidad:
        raise ErrorDatos("Balance inconsistente: las llegadas no coinciden con los viajes.")
    if int(balance["balance_neto"].sum()) != 0:
        raise ErrorDatos("Balance inconsistente: la suma de los balances netos no es cero.")
    if (balance["balance_neto"] != balance["llegadas"] - balance["salidas"]).any():
        raise ErrorDatos("Balance inconsistente: balance_neto debe ser llegadas - salidas.")
