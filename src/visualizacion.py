"""Visualización: balance neto de cada estación en el período consultado."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # genera archivos sin abrir ventanas (sirve en cualquier equipo)
import matplotlib.pyplot as plt  # noqa: E402

from src.pipeline import ResultadoReporte  # noqa: E402


def graficar_balance(resultado: ResultadoReporte, ruta) -> Path:
    """Dibuja barras horizontales del balance neto (llegadas - salidas) por estación.

    Las barras hacia la derecha (azul) son estaciones que recibieron más
    bicicletas de las que salieron; hacia la izquierda (rojo), las que perdieron.
    Recordatorio: no es el stock disponible.
    """
    balance = resultado.balance
    if balance.empty:
        raise ValueError("No hay datos para graficar: el reporte está vacío.")

    figura, eje = plt.subplots(figsize=(7, 0.45 * len(balance) + 1.8))
    colores = ["steelblue" if valor >= 0 else "firebrick" for valor in balance["balance_neto"]]
    eje.barh(balance["estacion"], balance["balance_neto"], color=colores)
    eje.axvline(0, color="black", linewidth=0.8)
    eje.invert_yaxis()  # la estación 001 arriba
    eje.set_xlabel("Balance neto (llegadas - salidas)")
    eje.set_ylabel("Estación")
    eje.set_title(f"Balance neto por estación\n{resultado.periodo.etiqueta()}", fontsize=10)
    figura.tight_layout()

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(ruta, dpi=120)
    plt.close(figura)
    return ruta
