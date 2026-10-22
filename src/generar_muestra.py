"""Genera la muestra de viajes de ejemplo (datos simulados) en CSV y JSON.

Uso (desde la raíz del proyecto):
    python -m src.generar_muestra

La simulación es reproducible: con la misma semilla se obtienen los mismos archivos.
Además de viajes correctos se agregan registros con errores deliberados para poder
comprobar la validación.
"""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEMILLA = 2026
CANTIDAD_VALIDOS = 400
ESTACIONES = [f"{numero:03d}" for numero in range(1, 13)]  # "001" ... "012"
INICIO_SEMANA = datetime(2026, 9, 14)  # lunes
FORMATO = "%Y-%m-%d %H:%M:%S"
COLUMNAS = ("viaje_id", "inicio", "fin", "estacion_origen", "estacion_destino")


def _pesos_por_hora() -> np.ndarray:
    """Más viajes en las horas pico (7-9 y 17-19) y muy pocos de madrugada."""
    pesos = np.ones(24)
    pesos[0:6] = 0.2
    pesos[7:10] = 5
    pesos[17:20] = 5
    return pesos / pesos.sum()


def generar_viajes_validos(rng: np.random.Generator, cantidad: int) -> list[dict]:
    """Viajes coherentes: el fin es posterior al inicio y ambas estaciones existen."""
    dias = rng.integers(0, 7, cantidad)
    horas = rng.choice(24, size=cantidad, p=_pesos_por_hora())
    minutos = rng.integers(0, 60, cantidad)
    segundos = rng.integers(0, 60, cantidad)
    duraciones = rng.integers(5, 56, cantidad)  # minutos
    popularidad = rng.dirichlet(np.full(len(ESTACIONES), 3.0))  # algunas estaciones se usan más
    origenes = rng.choice(ESTACIONES, size=cantidad, p=popularidad)
    destinos = rng.choice(ESTACIONES, size=cantidad, p=popularidad)

    viajes = []
    for d, h, m, s, dur, origen, destino in zip(dias, horas, minutos, segundos, duraciones, origenes, destinos):
        inicio = INICIO_SEMANA + timedelta(days=int(d), hours=int(h), minutes=int(m), seconds=int(s))
        fin = inicio + timedelta(minutes=int(dur), seconds=int(rng.integers(0, 60)))
        viajes.append(
            {
                "inicio": inicio.strftime(FORMATO),
                "fin": fin.strftime(FORMATO),
                "estacion_origen": str(origen),
                "estacion_destino": str(destino),
            }
        )
    viajes.sort(key=lambda v: v["inicio"])
    for numero, viaje in enumerate(viajes, start=1):
        viaje["viaje_id"] = f"V{numero:05d}"
    return [{columna: v[columna] for columna in COLUMNAS} for v in viajes]


def generar_registros_con_errores(validos: list[dict]) -> list[dict]:
    """Registros inválidos, uno por cada regla que la aplicación debe detectar."""
    base = validos[0]

    def registro(identificador, **cambios):
        fila = {**base, "viaje_id": identificador}
        fila.update(cambios)
        return fila

    return [
        registro("VX0001"),                                                   # identificador con mala forma
        {**validos[9]},                                                       # identificador duplicado (V00010)
        registro("V00401", inicio="2026/09/15 08:00:00", fin="2026/09/15 08:30:00"),  # formato de fecha
        registro("V00402", inicio="2026-02-30 08:00:00", fin="2026-03-01 09:00:00"),  # fecha inexistente
        registro("V00403", inicio="2026-09-15 08:00:00", fin="2026-09-31 09:00:00"),  # fin inexistente
        registro("V00404", inicio="2026-09-15 08:00:00", fin="2026-09-15 07:30:00"),  # fin anterior al inicio
        registro("V00405", inicio="2026-09-15 08:00:00", fin="2026-09-15 08:00:00"),  # duración cero
        registro("V00406", estacion_origen=None),                             # origen faltante
        registro("V00407", estacion_destino=""),                              # destino faltante
        registro("V00408", estacion_origen="12"),                             # origen con mala forma
        registro("V00409", estacion_destino="A01"),                           # destino con mala forma
        registro("V00410", fin=None),                                         # fin faltante
        registro("V00411", inicio=None),                                      # inicio faltante
    ]


def generar_tabla(semilla: int = SEMILLA, cantidad: int = CANTIDAD_VALIDOS) -> list[dict]:
    rng = np.random.default_rng(semilla)
    validos = generar_viajes_validos(rng, cantidad)
    return validos + generar_registros_con_errores(validos)


def guardar(tabla: list[dict], carpeta) -> None:
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    with (carpeta / "viajes.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS, lineterminator="\n")
        escritor.writeheader()
        for fila in tabla:
            escritor.writerow({k: ("" if v is None else v) for k, v in fila.items()})
    registros_json = [{k: (None if v == "" else v) for k, v in fila.items()} for fila in tabla]
    with (carpeta / "viajes.json").open("w", encoding="utf-8") as archivo:
        json.dump(registros_json, archivo, indent=2, ensure_ascii=False)
        archivo.write("\n")


if __name__ == "__main__":
    guardar(generar_tabla(), "data")
    print("Archivos generados: data/viajes.csv y data/viajes.json")
