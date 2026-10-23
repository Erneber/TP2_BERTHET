"""Flujo de procesamiento del reporte de movimientos.

leer -> inspeccionar y validar -> seleccionar período -> registrar movimientos
-> generar balance -> verificar -> comunicar

Criterio de diseño: la lógica de transformación está en funciones que reciben
datos y devuelven resultados, sin leer ni escribir archivos. Los efectos
(guardar archivos, mostrar por pantalla) se concentran en los bordes del flujo.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.dominio import (
    BalanceEstacion,
    ErrorDatos,
    Periodo,
    es_estacion_valida,
    es_viaje_valido,
    parsear_fecha,
)
from src.fuentes import FuenteDatos

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
    """Normaliza un valor a texto sin espacios; faltantes (None, NaN o vacío) pasan a None.

    Es una función pura: así el CSV (campo vacío) y el JSON (null) se tratan igual.
    """
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    return str(valor).strip() or None


def validar_recorridos(tabla: pd.DataFrame) -> tuple:
    """Separa los viajes válidos de los rechazados.

    Entradas: tabla con las columnas de COLUMNAS_VIAJE; todos los valores como texto.
    Salida: `(validos, rechazados)`. Los rechazados conservan la fila original y una
    columna `motivo` con todas las reglas incumplidas. En `validos`, `inicio` y `fin`
    ya son fechas (datetime64) y los códigos de estación conservan el cero inicial.
    Efectos: ninguno. Trabaja sobre una copia: la tabla recibida no se modifica.
    Errores: ErrorDatos si la tabla está vacía, faltan columnas o ningún viaje es válido.
    Reglas: forma del identificador y de las estaciones (regex), fechas que existan
    en el calendario, fin posterior al inicio, estaciones presentes y sin duplicados.
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

    Entradas: viajes ya validados (con `inicio` como fecha) y un Periodo.
    Salida: nueva tabla con los viajes seleccionados; vacía si no hay ninguno.
    Efectos: ninguno (no modifica `viajes`).
    Errores: ninguno propio; un Periodo inválido ya fue rechazado al construirse.
    Decisión de la primera versión: el viaje se asigna al período por su hora de
    inicio. Si termina después del fin del período, igualmente se cuentan ambos
    extremos (salida y llegada).
    """
    dentro = (viajes["inicio"] >= periodo.desde) & (viajes["inicio"] < periodo.hasta)
    return viajes.loc[dentro].reset_index(drop=True)


def registrar_movimientos(viajes: pd.DataFrame) -> dict:
    """Acumula, por estación, una salida en el origen y una llegada en el destino de cada viaje.

    Entradas: viajes ya validados y seleccionados.
    Salida: diccionario código de estación -> BalanceEstacion (solo estaciones con movimientos).
    Efectos: ninguno sobre los viajes; los objetos BalanceEstacion se crean dentro de la función.
    Errores: ninguno si los viajes pasaron por `validar_recorridos` (los códigos ya son válidos).
    Un viaje con origen igual a destino suma una salida y una llegada en la misma estación.
    """
    balances = {}

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


def generar_balance(balances: dict) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# Exportación (efectos en el borde del flujo)
# ---------------------------------------------------------------------------
def nombre_balance(periodo: Periodo) -> str:
    """Nombre del archivo del reporte; incluye el período para no pisar reportes de otros."""
    return f"balance_{periodo.desde:%Y%m%dT%H%M%S}_{periodo.hasta:%Y%m%dT%H%M%S}.csv"


def guardar_balance(balance: pd.DataFrame, periodo: Periodo, carpeta) -> Path:
    """Guarda el reporte en CSV y devuelve su ruta.

    Entradas: reporte, período (para nombrar el archivo) y carpeta de destino.
    Salida: ruta del archivo creado.
    Efectos: crea la carpeta si no existe y escribe (o reemplaza) el archivo del período.
    Errores: OSError si no se puede escribir (por ejemplo, permisos).
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre_balance(periodo)
    balance.to_csv(ruta, index=False, encoding="utf-8")
    return ruta


def guardar_rechazos(rechazados: pd.DataFrame, carpeta) -> Path:
    """Guarda los registros rechazados con su motivo en `rechazos.csv` (aunque no haya ninguno).

    Entradas: tabla de rechazados y carpeta de destino.
    Salida: ruta del archivo creado.
    Efectos: crea la carpeta si no existe y escribe el archivo.
    Errores: OSError si no se puede escribir.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "rechazos.csv"
    rechazados.to_csv(ruta, index=False, encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Aplicación (composición con inyección de dependencia)
# ---------------------------------------------------------------------------
@dataclass
class ResultadoReporte:
    """Todo lo que produce una ejecución, incluida la auditoría de la limpieza."""

    periodo: Periodo
    viajes_periodo: pd.DataFrame
    balance: pd.DataFrame
    rechazados: pd.DataFrame
    auditoria: dict


class AplicacionEcobici:
    """Coordina leer -> validar -> seleccionar período -> registrar -> balance -> verificar.

    *Tiene una* fuente de datos (composición) y la recibe por el constructor
    (inyección de dependencia): funciona igual con FuenteCSV o FuenteJSON sin
    duplicar la lógica. No escribe archivos: eso lo decide quien la usa.
    """

    def __init__(self, fuente: FuenteDatos):
        self._fuente = fuente

    def ejecutar(self, periodo: Periodo) -> ResultadoReporte:
        """Ejecuta el flujo completo para un período.

        Entradas: un Periodo (la fuente ya está inyectada).
        Salida: ResultadoReporte con viajes, balance, rechazados y auditoría.
        Efectos: solo lee el archivo de la fuente; no escribe nada.
        Errores: FileNotFoundError o ErrorDatos si la entrada no es utilizable, o si
        el balance no cumple las propiedades de `verificar_balance`.
        """
        entrada = self._fuente.cargar()
        validos, rechazados = validar_recorridos(entrada)
        viajes = seleccionar_periodo(validos, periodo)
        balance = generar_balance(registrar_movimientos(viajes))
        verificar_balance(balance, viajes)
        auditoria = {
            "entrada": len(entrada),
            "validos": len(validos),
            "rechazados": len(rechazados),
            "en_periodo": len(viajes),
            "fuera_de_periodo": len(validos) - len(viajes),
        }
        return ResultadoReporte(periodo, viajes, balance, rechazados, auditoria)
