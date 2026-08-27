"""Pruebas del almacén puro de alias de usuarios."""

import tempfile
import unittest
from pathlib import Path

import alias


class PruebasAlias(unittest.TestCase):

    def test_clave_iguala_espacios_y_mayusculas(self):
        self.assertEqual(alias.clave(" Juan "), alias.clave("juan"))

    def test_poner_guarda_un_alias(self):
        self.assertEqual(alias.poner({}, "Juan", "Juancho"), {"juan": "Juancho"})

    def test_poner_vacio_quita_el_alias(self):
        self.assertEqual(alias.poner({"juan": "Juancho"}, "Juan", "  "), {})

    def test_poner_recorta_a_cincuenta_caracteres(self):
        resultado = alias.poner({}, "Juan", "a" * 51)
        self.assertEqual(resultado["juan"], "a" * 50)

    def test_poner_no_modifica_el_mapa_recibido(self):
        mapa = {"ana": "Anita"}
        alias.poner(mapa, "Juan", "Juancho")
        self.assertEqual(mapa, {"ana": "Anita"})

    def test_quitar_no_modifica_el_mapa_recibido(self):
        mapa = {"ana": "Anita"}
        self.assertEqual(alias.quitar(mapa, "Ana"), {})
        self.assertEqual(mapa, {"ana": "Anita"})

    def test_cargar_inexistente_devuelve_vacio(self):
        with tempfile.TemporaryDirectory() as directorio:
            self.assertEqual(alias.cargar(Path(directorio) / "alias.json"), {})

    def test_cargar_corrupto_devuelve_vacio(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "alias.json"
            ruta.write_text("{", encoding="utf-8")
            self.assertEqual(alias.cargar(ruta), {})

    def test_guardar_y_cargar_conservan_tildes_y_enes(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "alias.json"
            alias.guardar(ruta, {"nino": "Niño Ágil"})
            self.assertEqual(alias.cargar(ruta), {"nino": "Niño Ágil"})

    def test_aplicar_con_y_sin_alias(self):
        self.assertEqual(alias.aplicar("Juan", {"juan": "Juancho"}), "Juancho")
        self.assertEqual(alias.aplicar("Ana", {"juan": "Juancho"}), "Ana")

    def test_aplicar_con_mapa_o_autor_vacio(self):
        self.assertEqual(alias.aplicar("Ana", {}), "Ana")
        self.assertEqual(alias.aplicar("", {"ana": "Anita"}), "")


if __name__ == "__main__":
    unittest.main()
