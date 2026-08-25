import unittest

import apagado


class PruebasApagado(unittest.TestCase):
    def test_filtra_y_ordena_los_hilos_de_captura(self):
        self.assertEqual(
            apagado.hilos_captura_vivos({"Otro", "TikTok", "Chat", "LiveChatId"}),
            ("Chat", "LiveChatId", "TikTok"),
        )

    def test_no_confunde_un_hilo_ajeno_con_captura(self):
        self.assertEqual(apagado.hilos_captura_vivos({"TTSWorker"}), ())

    def test_sigue_esperando_mientras_quede_captura_y_haya_tiempo(self):
        self.assertTrue(apagado.hay_que_seguir_esperando({"Chat"}, 2.9, 3.0))

    def test_deja_de_esperar_sin_capturas(self):
        self.assertFalse(apagado.hay_que_seguir_esperando({"TTSWorker"}, 0, 3.0))

    def test_deja_de_esperar_al_vencer_el_tope(self):
        self.assertFalse(apagado.hay_que_seguir_esperando({"Chat"}, 3.0, 3.0))

    def test_registra_cierre_limpio(self):
        self.assertEqual(apagado.componer_resultado_cierre(set(), 3.0),
                         "CIERRE captura limpia")

    def test_registra_hilos_que_quedaron_vivos_al_vencer(self):
        self.assertEqual(
            apagado.componer_resultado_cierre({"TikTok", "Chat"}, 3.0),
            "CIERRE por tope=3.0s hilos vivos=Chat, TikTok",
        )


if __name__ == "__main__":
    unittest.main()
