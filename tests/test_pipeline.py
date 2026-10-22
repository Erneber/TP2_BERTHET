"""Pruebas del flujo: validación, selección de período, balance, exportación y aplicación."""

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

from src.dominio import ErrorDatos, Periodo
from src.fuentes import FuenteCSV, FuenteJSON
from src.main import main
from src.pipeline import (
    AplicacionEcobici,
    generar_balance,
    guardar_balance,
    guardar_rechazos,
    nombre_balance,
    registrar_movimientos,
    seleccionar_periodo,
    validar_esquema,
    validar_recorridos,
    verificar_balance,
)

DATOS = Path(__file__).resolve().parents[1] / "data"


def viaje(identificador="V00001", inicio="2026-09-15 08:00:00", fin="2026-09-15 08:30:00",
          origen="001", destino="002"):
    return {"viaje_id": identificador, "inicio": inicio, "fin": fin,
            "estacion_origen": origen, "estacion_destino": destino}


def tabla(*viajes):
    return pd.DataFrame(list(viajes))


def validos_de(*viajes):
    validos, _ = validar_recorridos(tabla(*viajes))
    return validos


class PruebasValidacion(unittest.TestCase):
    def setUp(self):
        self.tabla = FuenteCSV(DATOS / "viajes.csv").cargar()

    def test_caso_normal_separa_validos_y_rechazados(self):
        validos, rechazados = validar_recorridos(self.tabla)
        self.assertEqual((len(validos), len(rechazados)), (400, 13))
        self.assertEqual(len(self.tabla), len(validos) + len(rechazados))  # nada se pierde en silencio

    def test_cada_rechazo_tiene_su_motivo(self):
        _, rechazados = validar_recorridos(self.tabla)
        motivo = dict(zip(rechazados["viaje_id"], rechazados["motivo"]))
        self.assertIn("identificador de viaje inválido", motivo["VX0001"])
        self.assertIn("duplicado", motivo["V00010"])
        self.assertIn("inicio", motivo["V00402"])
        self.assertIn("fin", motivo["V00403"])
        self.assertIn("fin no posterior", motivo["V00404"])
        self.assertIn("fin no posterior", motivo["V00405"])
        self.assertIn("origen faltante", motivo["V00406"])
        self.assertIn("destino faltante", motivo["V00407"])
        self.assertIn("origen con formato inválido", motivo["V00408"])
        self.assertIn("destino con formato inválido", motivo["V00409"])

    def test_el_duplicado_conserva_la_primera_aparicion(self):
        validos, _ = validar_recorridos(self.tabla)
        self.assertEqual(int((validos["viaje_id"] == "V00010").sum()), 1)

    def test_un_viaje_de_origen_igual_a_destino_es_valido(self):
        self.assertEqual(len(validos_de(viaje(origen="003", destino="003"))), 1)

    def test_no_modifica_la_tabla_original(self):
        antes = self.tabla.copy(deep=True)
        validar_recorridos(self.tabla)
        pd.testing.assert_frame_equal(self.tabla, antes)

    def test_los_validos_tienen_fechas_y_conservan_el_cero_inicial(self):
        validos, _ = validar_recorridos(self.tabla)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(validos["inicio"]))
        self.assertTrue((validos["fin"] > validos["inicio"]).all())
        self.assertTrue(validos["estacion_origen"].str.fullmatch(r"[0-9]{3}").all())

    def test_espacios_y_vacios(self):
        validos, rechazados = validar_recorridos(tabla(viaje(origen=" 001 "), viaje("V00002", destino="   ")))
        self.assertEqual(list(validos["estacion_origen"]), ["001"])  # el espacio sobrante se recorta
        self.assertIn("destino faltante", rechazados["motivo"].iloc[0])

    def test_entradas_que_detienen_el_flujo(self):
        with self.assertRaisesRegex(ErrorDatos, "Faltan columnas: fin"):
            validar_recorridos(self.tabla.drop(columns="fin"))
        with self.assertRaisesRegex(ErrorDatos, "vacía"):
            validar_esquema(self.tabla.iloc[0:0])
        with self.assertRaisesRegex(ErrorDatos, "Ningún viaje es válido"):
            validar_recorridos(tabla(viaje(origen=None)))

    def test_csv_y_json_equivalentes_dan_la_misma_validacion(self):
        v_csv, r_csv = validar_recorridos(FuenteCSV(DATOS / "viajes.csv").cargar())
        v_json, r_json = validar_recorridos(FuenteJSON(DATOS / "viajes.json").cargar())
        pd.testing.assert_frame_equal(v_csv, v_json)
        self.assertEqual(list(r_csv["motivo"]), list(r_json["motivo"]))


class PruebasPeriodoYMovimientos(unittest.TestCase):
    def test_limites_del_periodo(self):
        viajes = validos_de(
            viaje("V00001", inicio="2026-09-15 00:00:00", fin="2026-09-15 00:20:00"),  # == desde: entra
            viaje("V00002", inicio="2026-09-15 23:59:59", fin="2026-09-16 00:20:00"),  # último segundo: entra
            viaje("V00003", inicio="2026-09-16 00:00:00", fin="2026-09-16 00:20:00"),  # == hasta: no entra
            viaje("V00004", inicio="2026-09-14 23:59:59", fin="2026-09-15 00:20:00"),  # antes: no entra
        )
        seleccion = seleccionar_periodo(viajes, Periodo.desde_texto("2026-09-15", "2026-09-16"))
        self.assertEqual(list(seleccion["viaje_id"]), ["V00001", "V00002"])

    def test_un_viaje_que_termina_fuera_del_periodo_cuenta_ambos_extremos(self):
        viajes = validos_de(viaje(inicio="2026-09-15 23:50:00", fin="2026-09-16 00:20:00",
                                  origen="001", destino="002"))
        balance = registrar_movimientos(seleccionar_periodo(viajes, Periodo.desde_texto("2026-09-15", "2026-09-16")))
        self.assertEqual((balance["001"].salidas, balance["002"].llegadas), (1, 1))

    def test_periodo_sin_viajes_da_reporte_vacio_explicito(self):
        viajes = validos_de(viaje())
        vacio = seleccionar_periodo(viajes, Periodo.desde_texto("2030-01-01", "2030-01-02"))
        self.assertTrue(vacio.empty)
        balance = generar_balance(registrar_movimientos(vacio))
        self.assertTrue(balance.empty)
        self.assertEqual(list(balance.columns), ["estacion", "salidas", "llegadas", "balance_neto"])
        verificar_balance(balance, vacio)  # el reporte vacío también es coherente

    def test_seleccionar_no_modifica_los_viajes(self):
        viajes = validos_de(viaje(), viaje("V00002", inicio="2026-09-20 08:00:00", fin="2026-09-20 09:00:00"))
        antes = viajes.copy(deep=True)
        seleccionar_periodo(viajes, Periodo.desde_texto("2026-09-15", "2026-09-16"))
        pd.testing.assert_frame_equal(viajes, antes)

    def test_un_viaje_de_A_a_B_suma_una_salida_en_A_y_una_llegada_en_B(self):
        balances = registrar_movimientos(validos_de(viaje(origen="001", destino="002")))
        self.assertEqual((balances["001"].salidas, balances["001"].llegadas), (1, 0))
        self.assertEqual((balances["002"].salidas, balances["002"].llegadas), (0, 1))
        self.assertEqual((balances["001"].balance, balances["002"].balance), (-1, 1))

    def test_viaje_circular_suma_salida_y_llegada_en_la_misma_estacion(self):
        balances = registrar_movimientos(validos_de(viaje(origen="005", destino="005")))
        self.assertEqual((balances["005"].salidas, balances["005"].llegadas, balances["005"].balance), (1, 1, 0))

    def test_balance_con_valores_conocidos(self):
        viajes = validos_de(
            viaje("V00001", origen="001", destino="002"),
            viaje("V00002", origen="001", destino="003"),
            viaje("V00003", origen="002", destino="001"),
        )
        reporte = generar_balance(registrar_movimientos(viajes)).set_index("estacion")
        self.assertEqual(reporte.loc["001"].tolist(), [2, 1, -1])
        self.assertEqual(reporte.loc["002"].tolist(), [1, 1, 0])
        self.assertEqual(reporte.loc["003"].tolist(), [0, 1, 1])
        verificar_balance(reporte.reset_index(), viajes)

    def test_la_suma_de_balances_es_cero_en_todo_el_conjunto(self):
        validos, _ = validar_recorridos(FuenteCSV(DATOS / "viajes.csv").cargar())
        balance = generar_balance(registrar_movimientos(validos))
        self.assertEqual(int(balance["balance_neto"].sum()), 0)
        self.assertEqual(int(balance["salidas"].sum()), len(validos))

    def test_verificar_detecta_balances_corruptos(self):
        viajes = validos_de(viaje(), viaje("V00002", origen="002", destino="003"))
        balance = generar_balance(registrar_movimientos(viajes))

        mas_llegadas = balance.copy()
        mas_llegadas.loc[0, "llegadas"] += 1
        with self.assertRaisesRegex(ErrorDatos, "llegadas"):
            verificar_balance(mas_llegadas, viajes)

        mas_salidas = balance.copy()
        mas_salidas.loc[0, "salidas"] += 1
        with self.assertRaisesRegex(ErrorDatos, "salidas"):
            verificar_balance(mas_salidas, viajes)

        neto_mal = balance.copy()
        neto_mal.loc[0, "balance_neto"] += 1
        with self.assertRaises(ErrorDatos):
            verificar_balance(neto_mal, viajes)


class PruebasAplicacion(unittest.TestCase):
    PERIODO = Periodo.desde_texto("2026-09-15", "2026-09-16")

    def ejecutar(self, archivo, fuente, periodo=None):
        return AplicacionEcobici(fuente(DATOS / archivo)).ejecutar(periodo or self.PERIODO)

    def test_csv_y_json_producen_el_mismo_reporte(self):
        r_csv = self.ejecutar("viajes.csv", FuenteCSV)
        r_json = self.ejecutar("viajes.json", FuenteJSON)
        pd.testing.assert_frame_equal(r_csv.balance, r_json.balance)
        self.assertEqual(r_csv.auditoria, r_json.auditoria)

    def test_auditoria_cierra(self):
        a = self.ejecutar("viajes.csv", FuenteCSV).auditoria
        self.assertEqual(a["entrada"], a["validos"] + a["rechazados"])
        self.assertEqual(a["validos"], a["en_periodo"] + a["fuera_de_periodo"])
        self.assertEqual(a["en_periodo"], 57)

    def test_los_rechazados_no_alteran_los_conteos(self):
        resultado = self.ejecutar("viajes.csv", FuenteCSV)
        # Todos los registros inválidos usan la estación 001: si se contaran, las salidas
        # de 001 serían mayores que las de un reporte armado solo con los viajes válidos.
        validos, _ = validar_recorridos(FuenteCSV(DATOS / "viajes.csv").cargar())
        esperado = generar_balance(registrar_movimientos(seleccionar_periodo(validos, self.PERIODO)))
        pd.testing.assert_frame_equal(resultado.balance, esperado)

    def test_periodos_consecutivos_suman_el_periodo_total(self):
        manana = self.ejecutar("viajes.csv", FuenteCSV, Periodo.desde_texto("2026-09-15", "2026-09-15 12:00:00"))
        tarde = self.ejecutar("viajes.csv", FuenteCSV, Periodo.desde_texto("2026-09-15 12:00:00", "2026-09-16"))
        dia = self.ejecutar("viajes.csv", FuenteCSV)
        suma = pd.concat([manana.balance, tarde.balance]).groupby("estacion").sum()
        pd.testing.assert_frame_equal(suma, dia.balance.set_index("estacion"), check_dtype=False)

    def test_es_deterministica(self):
        a = self.ejecutar("viajes.csv", FuenteCSV).balance
        b = self.ejecutar("viajes.csv", FuenteCSV).balance
        pd.testing.assert_frame_equal(a, b)


class PruebasExportacion(unittest.TestCase):
    def test_guarda_el_balance_y_los_rechazos(self):
        periodo = Periodo.desde_texto("2026-09-15", "2026-09-16")
        resultado = AplicacionEcobici(FuenteCSV(DATOS / "viajes.csv")).ejecutar(periodo)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = guardar_balance(resultado.balance, periodo, Path(carpeta) / "sub")
            self.assertEqual(ruta.name, "balance_20260915T000000_20260916T000000.csv")
            leido = pd.read_csv(ruta, dtype={"estacion": str})
            pd.testing.assert_frame_equal(leido, resultado.balance, check_dtype=False)
            self.assertEqual(leido["estacion"].iloc[0], "001")  # el cero inicial sobrevive
            rechazos = pd.read_csv(guardar_rechazos(resultado.rechazados, carpeta), dtype=str)
            self.assertEqual(len(rechazos), 13)

    def test_periodos_distintos_no_se_pisan(self):
        a = nombre_balance(Periodo.desde_texto("2026-09-15", "2026-09-16"))
        b = nombre_balance(Periodo.desde_texto("2026-09-16", "2026-09-17"))
        self.assertNotEqual(a, b)


class PruebasLineaDeComandos(unittest.TestCase):
    def ejecutar_main(self, *argumentos):
        salida, error = StringIO(), StringIO()
        with redirect_stdout(salida), redirect_stderr(error):
            codigo = main(list(argumentos))
        return codigo, salida.getvalue(), error.getvalue()

    def test_ejecucion_correcta_genera_archivos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            codigo, salida, _ = self.ejecutar_main(
                "--entrada", str(DATOS / "viajes.csv"), "--desde", "2026-09-15",
                "--hasta", "2026-09-16", "--salida", carpeta)
            self.assertEqual(codigo, 0)
            self.assertIn("rechazados: 13", salida)
            self.assertIn("viajes en el período: 57", salida)
            self.assertTrue((Path(carpeta) / "rechazos.csv").is_file())
            self.assertEqual(len(list(Path(carpeta).glob("balance_*.csv"))), 1)

    def test_periodo_vacio_informa_en_lugar_de_fallar(self):
        with tempfile.TemporaryDirectory() as carpeta:
            codigo, salida, _ = self.ejecutar_main(
                "--entrada", str(DATOS / "viajes.json"), "--desde", "2030-01-01",
                "--hasta", "2030-01-02", "--salida", carpeta)
            self.assertEqual(codigo, 0)
            self.assertIn("reporte está vacío", salida)

    def test_errores_esperados_devuelven_codigo_1_y_mensaje(self):
        with tempfile.TemporaryDirectory() as carpeta:
            casos = [
                (["--entrada", "no_existe.csv", "--desde", "2026-09-15", "--hasta", "2026-09-16"], "No existe el archivo"),
                (["--entrada", str(DATOS / "viajes.csv"), "--desde", "2026-09-16", "--hasta", "2026-09-15"], "anterior"),
                (["--entrada", str(DATOS / "viajes.csv"), "--desde", "2026-02-30", "--hasta", "2026-03-02"], "inválido"),
                (["--entrada", "datos.xlsx", "--desde", "2026-09-15", "--hasta", "2026-09-16"], "Formato no soportado"),
            ]
            for argumentos, texto in casos:
                with self.subTest(argumentos=argumentos):
                    codigo, _, error = self.ejecutar_main(*argumentos, "--salida", carpeta)
                    self.assertEqual(codigo, 1)
                    self.assertIn(texto, error)


if __name__ == "__main__":
    unittest.main()
