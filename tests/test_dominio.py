"""Pruebas de las reglas del dominio: regex, calendario, Periodo y BalanceEstacion."""

import unittest
from datetime import datetime

from src.dominio import (
    BalanceEstacion,
    ErrorDatos,
    Periodo,
    es_estacion_valida,
    es_viaje_valido,
    parsear_fecha,
)


class PruebasRegex(unittest.TestCase):
    def comprobar(self, funcion, validos, invalidos):
        for texto in validos:
            with self.subTest(valido=texto):
                self.assertTrue(funcion(texto))
        for texto in invalidos:
            with self.subTest(invalido=texto):
                self.assertFalse(funcion(texto))

    def test_identificador_de_viaje(self):
        self.comprobar(es_viaje_valido, ["V00001", "V99999"],
                       ["V0001", "V000011", "v00001", "X00001", " V00001", "V0000A", "", None, 5])

    def test_codigo_de_estacion(self):
        self.comprobar(es_estacion_valida, ["001", "012", "999"],
                       ["12", "0012", "A01", "1 2", "", None, 1])

    def test_no_acepta_digitos_de_otros_alfabetos(self):
        self.assertFalse(es_estacion_valida("00\u0663"))  # dígito arábigo-índico


class PruebasFechas(unittest.TestCase):
    def test_fecha_valida(self):
        self.assertEqual(parsear_fecha("2026-09-14 08:30:15"), datetime(2026, 9, 14, 8, 30, 15))

    def test_la_regex_comprueba_la_forma_y_strptime_el_calendario(self):
        # Cumplen la forma AAAA-MM-DD HH:MM:SS pero no existen en el calendario.
        for texto in ["2026-02-30 08:00:00", "2026-09-31 08:00:00", "2026-13-01 08:00:00",
                      "2026-09-14 25:00:00", "2026-09-14 08:61:00"]:
            with self.subTest(texto=texto):
                self.assertIsNone(parsear_fecha(texto))

    def test_bisiesto(self):
        self.assertIsNotNone(parsear_fecha("2028-02-29 00:00:00"))
        self.assertIsNone(parsear_fecha("2026-02-29 00:00:00"))

    def test_formas_incorrectas(self):
        for texto in ["2026/09/14 08:00:00", "2026-9-14 8:00:00", "2026-09-14", "", None, 20260914]:
            with self.subTest(texto=texto):
                self.assertIsNone(parsear_fecha(texto))


class PruebasPeriodo(unittest.TestCase):
    def test_incluye_el_inicio_y_excluye_el_fin(self):
        periodo = Periodo.desde_texto("2026-09-15", "2026-09-16")
        self.assertTrue(periodo.contiene(datetime(2026, 9, 15, 0, 0, 0)))
        self.assertTrue(periodo.contiene(datetime(2026, 9, 15, 23, 59, 59)))
        self.assertFalse(periodo.contiene(datetime(2026, 9, 16, 0, 0, 0)))
        self.assertFalse(periodo.contiene(datetime(2026, 9, 14, 23, 59, 59)))

    def test_acepta_fecha_sola_u_hora_completa(self):
        self.assertEqual(Periodo.desde_texto("2026-09-15", "2026-09-16 07:00:00").hasta,
                         datetime(2026, 9, 16, 7, 0, 0))

    def test_entradas_invalidas(self):
        casos = [("2026-09-16", "2026-09-15"), ("2026-09-15", "2026-09-15"),
                 ("2026-02-30", "2026-03-01"), ("ayer", "hoy"), ("2026-09-15", "")]
        for desde, hasta in casos:
            with self.subTest(desde=desde, hasta=hasta):
                with self.assertRaises(ErrorDatos):
                    Periodo.desde_texto(desde, hasta)

    def test_es_inmutable(self):
        periodo = Periodo.desde_texto("2026-09-15", "2026-09-16")
        with self.assertRaises(Exception):  # FrozenInstanceError
            periodo.desde = datetime(2000, 1, 1)


class PruebasBalanceEstacion(unittest.TestCase):
    def test_conteos_y_balance(self):
        estacion = BalanceEstacion("001")
        for _ in range(2):
            estacion.registrar_salida()
        for _ in range(5):
            estacion.registrar_llegada()
        self.assertEqual((estacion.salidas, estacion.llegadas, estacion.balance), (2, 5, 3))
        self.assertEqual(estacion.a_diccionario()["balance_neto"], 3)

    def test_estacion_nueva_arranca_en_cero(self):
        self.assertEqual(BalanceEstacion("002").balance, 0)

    def test_estado_encapsulado(self):
        estacion = BalanceEstacion("001")
        for atributo in ("salidas", "llegadas", "balance"):
            with self.subTest(atributo=atributo):
                with self.assertRaises(AttributeError):
                    setattr(estacion, atributo, 10)

    def test_codigo_invalido(self):
        with self.assertRaises(ErrorDatos):
            BalanceEstacion("1")


if __name__ == "__main__":
    unittest.main()
