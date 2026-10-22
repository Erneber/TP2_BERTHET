"""Fuentes de datos: una abstracción común y dos implementaciones (CSV y JSON).

La aplicación depende del contrato `FuenteDatos.cargar()` y no del formato del
archivo. Ambas fuentes devuelven la misma representación: un DataFrame con una
fila por registro y **todos los valores como texto**. La conversión de tipos
(fechas, por ejemplo) es responsabilidad de la validación; así no se pierden
los ceros iniciales de los códigos de estación ("001" no pasa a ser 1).
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from src.dominio import ErrorDatos


class FuenteDatos(ABC):
    """Contrato común: toda fuente sabe cargar una tabla desde un archivo."""

    def __init__(self, ruta):
        self._ruta = Path(ruta)

    @property
    def ruta(self) -> Path:
        """Ruta del archivo (solo lectura: no hay setter público)."""
        return self._ruta

    def comprobar_archivo(self) -> None:
        """Falla de forma explícita si el archivo no existe."""
        if not self.ruta.is_file():
            raise FileNotFoundError(f"No existe el archivo: {self.ruta}")

    @abstractmethod
    def cargar(self) -> pd.DataFrame:
        """Devuelve una tabla con una fila por registro."""


class FuenteCSV(FuenteDatos):
    """Lee tablas en CSV (separador coma, UTF-8), sin inferir tipos."""

    def cargar(self) -> pd.DataFrame:
        self.comprobar_archivo()
        try:
            # dtype=str conserva ceros iniciales; keep_default_na=False evita que
            # textos como "NA" se conviertan en faltantes sin avisar.
            return pd.read_csv(self.ruta, encoding="utf-8", dtype=str, keep_default_na=False)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as error:
            raise ErrorDatos(f"CSV ilegible ({self.ruta.name}): {error}") from error


class FuenteJSON(FuenteDatos):
    """Lee tablas en JSON con el contrato: una lista de objetos, uno por registro."""

    def cargar(self) -> pd.DataFrame:
        self.comprobar_archivo()
        try:
            with self.ruta.open(encoding="utf-8") as archivo:
                registros = json.load(archivo)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ErrorDatos(f"JSON mal formado ({self.ruta.name}): {error}") from error
        # Se valida la estructura antes de armar la tabla (fallo temprano).
        if not isinstance(registros, list) or not all(isinstance(r, dict) for r in registros):
            raise ErrorDatos(
                f"{self.ruta.name}: se esperaba una lista de objetos (uno por registro)."
            )
        return pd.DataFrame(registros)


def crear_fuente(ruta) -> FuenteDatos:
    """Elige la fuente concreta según la extensión del archivo."""
    extension = Path(ruta).suffix.lower()
    if extension == ".csv":
        return FuenteCSV(ruta)
    if extension == ".json":
        return FuenteJSON(ruta)
    raise ErrorDatos(f"Formato no soportado: {extension!r} (use .csv o .json).")
