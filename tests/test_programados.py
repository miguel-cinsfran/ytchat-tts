import unittest

import programados


class TestValidarMensaje(unittest.TestCase):
    def test_acepta_mensaje_valido(self):
        self.assertEqual(programados.validar_mensaje("Sígueme", 10, 15), ("", ""))

    def test_rechaza_texto_vacio(self):
        self.assertEqual(programados.validar_mensaje("  ", 10, 10)[0],
                         "El mensaje no puede estar vacío.")

    def test_rechaza_texto_largo(self):
        error, _ = programados.validar_mensaje("x" * 201, 10, 10)
        self.assertEqual(error, "El mensaje tiene 201 caracteres y el máximo son 200.")

    def test_rechaza_minimo_bajo(self):
        error, _ = programados.validar_mensaje("Hola", 4, 10)
        self.assertEqual(error, "El intervalo mínimo son 5 minutos.")

    def test_rechaza_maximo_menor(self):
        error, _ = programados.validar_mensaje("Hola", 10, 9)
        self.assertEqual(error, "El intervalo máximo no puede ser menor que el mínimo.")

    def test_avisa_url_sin_rechazar(self):
        error, aviso = programados.validar_mensaje("Visita https://ejemplo.com", 10, 10)
        self.assertEqual(error, "")
        self.assertEqual(aviso, "YouTube suele bloquear los enlaces en el chat en vivo. "
                         "Conviene poner el nombre de usuario en vez de la dirección completa.")


class TestCalcularProximo(unittest.TestCase):
    def test_intervalo_fijo_no_llama_al_azar(self):
        llamadas = []
        aleatorio = lambda a, b: llamadas.append((a, b)) or 0
        self.assertEqual(programados.calcular_proximo(10, 10, 1000, aleatorio), 1600)
        self.assertEqual(llamadas, [])

    def test_intervalo_aleatorio_inyectado(self):
        self.assertEqual(programados.calcular_proximo(10, 15, 1000,
                                                       lambda a, b: 720), 1720)


class TestElegirEnvio(unittest.TestCase):
    def setUp(self):
        self.mensajes = [
            {"texto": "nuevo", "activo": True, "proximo": 90},
            {"texto": "viejo", "activo": True, "proximo": 80},
        ]

    def test_ignora_inactivos(self):
        self.mensajes[1]["activo"] = False
        self.assertIs(self._elegir(100), self.mensajes[0])

    def test_elige_el_vencido_mas_antiguo(self):
        self.assertIs(self._elegir(100), self.mensajes[1])

    def test_reserva_un_minuto_entre_envios(self):
        self.assertIsNone(self._elegir(100, ultimo_envio=50))

    def test_no_devuelve_si_no_hay_vencidos(self):
        self.assertIsNone(self._elegir(70))

    def _elegir(self, ahora, ultimo_envio=None):
        return programados.elegir_envio(self.mensajes, ahora, ultimo_envio)


class TestDescribirProximo(unittest.TestCase):
    def test_sin_mensajes_activos(self):
        self.assertEqual(programados.describir_proximo([], 0), "")

    def test_menos_de_un_minuto(self):
        mensajes = [{"activo": True, "proximo": 30}]
        self.assertEqual(programados.describir_proximo(mensajes, 0),
                         "Próximo mensaje programado en menos de un minuto")

    def test_singular(self):
        mensajes = [{"activo": True, "proximo": 60}]
        self.assertEqual(programados.describir_proximo(mensajes, 0),
                         "Próximo mensaje programado en 1 minuto")

    def test_elige_el_mas_cercano_y_redondea(self):
        mensajes = [{"activo": True, "proximo": 301},
                    {"activo": True, "proximo": 500}]
        self.assertEqual(programados.describir_proximo(mensajes, 0),
                         "Próximo mensaje programado en 6 minutos")


if __name__ == "__main__":
    unittest.main()
