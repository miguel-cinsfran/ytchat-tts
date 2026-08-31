import unittest
import logging

import apagado


class PruebasApagado(unittest.TestCase):
    def test_cierre_limpio_se_registra_con_nivel_informativo(self):
        self.assertEqual(apagado.nivel_registro_cierre(()), logging.INFO)

    def test_cierre_con_hilo_vivo_se_registra_con_nivel_de_advertencia(self):
        self.assertEqual(apagado.nivel_registro_cierre(("ReproductorStop",)),
                         logging.WARNING)

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
        self.assertFalse(apagado.hay_que_seguir_esperando((), 0, 3.0))

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

    def test_sigue_esperando_con_hilos_vivos_y_no_con_lista_vacia(self):
        self.assertTrue(apagado.hay_que_seguir_esperando(("Comentarios", "Descarga-123"), 0.5, 8.0))
        self.assertFalse(apagado.hay_que_seguir_esperando((), 0.5, 8.0))
        self.assertFalse(apagado.hay_que_seguir_esperando(("Chat",), 8.0, 8.0))

    def test_tope_de_espera_vale_ocho_segundos(self):
        self.assertEqual(apagado.TOPE_ESPERA_CIERRE, 8.0)

    def test_registra_hilos_repetidos_sin_deduplicar(self):
        self.assertEqual(
            apagado.componer_resultado_cierre(
                ("ReproductorCacheVideo", "ReproductorCacheVideo"), 8.0
            ),
            "CIERRE por tope=8.0s hilos vivos=ReproductorCacheVideo, ReproductorCacheVideo",
        )


if __name__ == "__main__":
    unittest.main()
