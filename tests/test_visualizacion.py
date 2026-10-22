"""Pruebas del gráfico: se genera el archivo y se rechaza un reporte vacío."""

import tempfile
import unittest
from pathlib import Path

from src.dominio import Periodo
from src.fuentes import FuenteCSV
from src.pipeline import AplicacionEcobici
from src.visualizacion import graficar_balance

DATOS = Path(__file__).resolve().parents[1] / "data"


class PruebasVisualizacion(unittest.TestCase):
    def ejecutar(self, desde, hasta):
        return AplicacionEcobici(FuenteCSV(DATOS / "viajes.csv")).ejecutar(Periodo.desde_texto(desde, hasta))

    def test_genera_un_png_no_vacio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = graficar_balance(self.ejecutar("2026-09-15", "2026-09-16"), Path(carpeta) / "sub" / "g.png")
            self.assertTrue(ruta.is_file())
            self.assertGreater(ruta.stat().st_size, 0)

    def test_reporte_vacio_no_se_grafica(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with self.assertRaisesRegex(ValueError, "vacío"):
                graficar_balance(self.ejecutar("2030-01-01", "2030-01-02"), Path(carpeta) / "g.png")


if __name__ == "__main__":
    unittest.main()
