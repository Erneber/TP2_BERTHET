"""Dominio del reporte de movimientos: error propio, validación de campos y clases.

Contiene las reglas sobre la *forma* de los datos (expresiones regulares), la
comprobación del calendario, el período de consulta y el balance de una estación.
"""

import re
from dataclasses import dataclass
from datetime import datetime

# Expresiones regulares. Se usa [0-9] y no \d porque \d acepta dígitos de otros alfabetos.
PATRON_VIAJE = re.compile(r"V[0-9]{5}")
PATRON_ESTACION = re.compile(r"[0-9]{3}")
PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")
PATRON_SOLO_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


class ErrorDatos(ValueError):
    """La entrada no cumple el contrato de la aplicación."""


def _coincide(patron: re.Pattern, valor) -> bool:
    """fullmatch exige que el texto completo cumpla el patrón (search lo buscaría adentro)."""
    return isinstance(valor, str) and patron.fullmatch(valor) is not None


def es_viaje_valido(valor) -> bool:
    """Forma del identificador de viaje: V + 5 dígitos. No comprueba que sea único."""
    return _coincide(PATRON_VIAJE, valor)


def es_estacion_valida(valor) -> bool:
    """Forma del código de estación: 3 dígitos (se conserva el cero inicial)."""
    return _coincide(PATRON_ESTACION, valor)


def parsear_fecha(valor) -> datetime:
    """Convierte 'AAAA-MM-DD HH:MM:SS' en datetime, o devuelve None si no es válida
    (por eso el resultado puede ser un datetime o None).

    Hace dos controles distintos: la regex verifica la *forma* y `strptime`
    verifica el *calendario*. Por ejemplo, '2026-02-30 08:00:00' cumple la forma
    pero no existe, y '2026-09-14 25:00:00' tampoco es una hora posible.
    """
    if not _coincide(PATRON_FECHA, valor):
        return None
    try:
        return datetime.strptime(valor, FORMATO_FECHA)
    except ValueError:
        return None


def _interpretar_instante(texto: str, nombre: str) -> datetime:
    """Acepta 'AAAA-MM-DD' (medianoche) o 'AAAA-MM-DD HH:MM:SS'."""
    if _coincide(PATRON_SOLO_FECHA, texto):
        texto = f"{texto} 00:00:00"
    instante = parsear_fecha(texto)
    if instante is None:
        raise ErrorDatos(
            f"'{nombre}' inválido: {texto!r}. Use AAAA-MM-DD o AAAA-MM-DD HH:MM:SS "
            "con una fecha que exista."
        )
    return instante


@dataclass(frozen=True)
class Periodo:
    """Franja temporal de consulta: incluye `desde` y excluye `hasta` ([desde, hasta))."""

    desde: datetime
    hasta: datetime

    def __post_init__(self):
        if not isinstance(self.desde, datetime) or not isinstance(self.hasta, datetime):
            raise ErrorDatos("El período debe estar definido por dos fechas y horas.")
        if self.desde >= self.hasta:
            raise ErrorDatos("El inicio del período debe ser anterior a su fin.")

    @classmethod
    def desde_texto(cls, desde: str, hasta: str) -> "Periodo":
        """Constructor alternativo a partir de los textos recibidos por la línea de comandos."""
        return cls(_interpretar_instante(desde, "desde"), _interpretar_instante(hasta, "hasta"))

    def contiene(self, instante: datetime) -> bool:
        return self.desde <= instante < self.hasta

    def etiqueta(self) -> str:
        return f"{self.desde:{FORMATO_FECHA}} a {self.hasta:{FORMATO_FECHA}}"


class BalanceEstacion:
    """Conteo de salidas y llegadas de una estación.

    Encapsula su estado: los contadores solo cambian mediante `registrar_salida()`
    y `registrar_llegada()`, de modo que no se pueden dejar en un estado incoherente.

    Aclaración: el balance neto (llegadas - salidas) NO es el stock de bicicletas,
    porque no incluye inventario inicial ni reposiciones.
    """

    def __init__(self, codigo: str):
        if not es_estacion_valida(codigo):
            raise ErrorDatos(f"Código de estación inválido: {codigo!r} (se esperan 3 dígitos).")
        self._codigo = codigo
        self._salidas = 0
        self._llegadas = 0

    @property
    def codigo(self) -> str:
        return self._codigo

    @property
    def salidas(self) -> int:
        return self._salidas

    @property
    def llegadas(self) -> int:
        return self._llegadas

    @property
    def balance(self) -> int:
        """Llegadas menos salidas (se consulta sin paréntesis)."""
        return self._llegadas - self._salidas

    def registrar_salida(self) -> None:
        self._salidas += 1

    def registrar_llegada(self) -> None:
        self._llegadas += 1

    def a_diccionario(self) -> dict:
        return {
            "estacion": self._codigo,
            "salidas": self._salidas,
            "llegadas": self._llegadas,
            "balance_neto": self.balance,
        }

    def __repr__(self) -> str:
        return (f"BalanceEstacion({self._codigo!r}, salidas={self._salidas}, "
                f"llegadas={self._llegadas})")
