"""Pruebas de las fuentes de datos (CSV y JSON)."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.dominio import ErrorDatos
from src.fuentes import FuenteCSV, FuenteDatos, FuenteJSON, crear_fuente

DATOS = Path(__file__).resolve().parents[1] / "data"


class PruebasFuentes(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.temporal.name)

    def tearDown(self):
        self.temporal.cleanup()

    def test_la_clase_base_es_abstracta(self):
        with self.assertRaises(TypeError):
            FuenteDatos("x.csv")

    def test_ambas_fuentes_cumplen_el_contrato_comun(self):
        for fuente in (FuenteCSV(DATOS / "viajes.csv"), FuenteJSON(DATOS / "viajes.json")):
            with self.subTest(fuente=type(fuente).__name__):
                self.assertIsInstance(fuente, FuenteDatos)
                tabla = fuente.cargar()
                self.assertIsInstance(tabla, pd.DataFrame)
                self.assertEqual(len(tabla), 413)
                self.assertIn("estacion_origen", tabla.columns)

    def test_csv_y_json_coinciden_en_los_campos_con_valor(self):
        csv = FuenteCSV(DATOS / "viajes.csv").cargar()
        js = FuenteJSON(DATOS / "viajes.json").cargar()
        for columna in ("viaje_id", "inicio", "estacion_origen"):
            with self.subTest(columna=columna):
                pares = pd.DataFrame({"csv": csv[columna], "json": js[columna]}).dropna()
                pares = pares[pares["csv"] != ""]
                self.assertTrue((pares["csv"] == pares["json"]).all())

    def test_el_csv_conserva_los_ceros_iniciales(self):
        tabla = FuenteCSV(DATOS / "viajes.csv").cargar()
        self.assertTrue(tabla["estacion_origen"].iloc[0].startswith("0"))

    def test_archivo_inexistente(self):
        for clase in (FuenteCSV, FuenteJSON):
            with self.subTest(clase=clase.__name__):
                with self.assertRaisesRegex(FileNotFoundError, "No existe"):
                    clase(self.carpeta / "no_existe").cargar()

    def test_json_mal_formado(self):
        ruta = self.carpeta / "roto.json"
        ruta.write_text("[{'a': 1,", encoding="utf-8")
        with self.assertRaisesRegex(ErrorDatos, "JSON mal formado"):
            FuenteJSON(ruta).cargar()

    def test_json_con_estructura_distinta_al_contrato(self):
        ruta = self.carpeta / "anidado.json"
        ruta.write_text(json.dumps({"viajes": [{"a": 1}]}), encoding="utf-8")
        with self.assertRaisesRegex(ErrorDatos, "lista de objetos"):
            FuenteJSON(ruta).cargar()

    def test_csv_vacio(self):
        ruta = self.carpeta / "vacio.csv"
        ruta.write_text("", encoding="utf-8")
        with self.assertRaises(ErrorDatos):
            FuenteCSV(ruta).cargar()

    def test_crear_fuente_segun_extension(self):
        self.assertIsInstance(crear_fuente("a.csv"), FuenteCSV)
        self.assertIsInstance(crear_fuente("a.JSON"), FuenteJSON)
        with self.assertRaisesRegex(ErrorDatos, "Formato no soportado"):
            crear_fuente("a.xlsx")


if __name__ == "__main__":
    unittest.main()
