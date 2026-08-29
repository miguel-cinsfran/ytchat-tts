"""Pruebas del reproductor de sonidos sin usar el backend real."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sound_player


class PruebasSoundPlayer(unittest.TestCase):
    def setUp(self):
        parches = (
            mock.patch.object(sound_player, "_eventos", {}),
            mock.patch.object(sound_player, "_volumen", 0.7),
            mock.patch.object(sound_player, "_activo", True),
            mock.patch.object(sound_player, "_silenciado_usuario", False),
            mock.patch.object(sound_player, "_backend_winmm", False),
            mock.patch.object(sound_player, "_init_backend"),
            mock.patch.object(sound_player, "_iniciar_sweeper"),
            mock.patch.object(sound_player, "_sweeper_thread", None),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_cargar_desactivado_silencia(self):
        sound_player.cargar({"activar": False})

        self.assertTrue(sound_player.esta_silenciado())

    def test_cargar_activo_con_eventos_no_silencia(self):
        sound_player.cargar({"activar": True, "eventos": {"mensaje": Path("mensaje.wav")}})

        self.assertFalse(sound_player.esta_silenciado())

    def test_cargar_recorta_el_volumen(self):
        sound_player.cargar({"volumen": 5})
        self.assertEqual(sound_player._volumen, 1.0)

        sound_player.cargar({"volumen": -3})
        self.assertEqual(sound_player._volumen, 0.0)

    def test_cargar_descarta_eventos_vacios(self):
        ruta = Path("mensaje.wav")
        sound_player.cargar({"eventos": {"mensaje": ruta, "vacio": "", "nulo": None}})

        self.assertEqual(sound_player._eventos, {"mensaje": ruta})

    def test_silenciar_todo_impide_llegar_al_backend(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directorio:
            ruta = Path(directorio) / "mensaje.wav"
            ruta.touch()
            sound_player.cargar({"eventos": {"mensaje": ruta}})
            sound_player.silenciar_todo(True)
            with mock.patch.object(sound_player, "_reproducir_winmm") as winmm, \
                    mock.patch.object(sound_player, "_reproducir_fallback") as fallback:
                sound_player.reproducir("mensaje")

        winmm.assert_not_called()
        fallback.assert_not_called()

    def test_reproducir_evento_desconocido_no_llama_al_backend(self):
        with mock.patch.object(sound_player, "_reproducir_winmm") as winmm, \
                mock.patch.object(sound_player, "_reproducir_fallback") as fallback:
            sound_player.reproducir("inexistente")

        winmm.assert_not_called()
        fallback.assert_not_called()

    def test_reproducir_archivo_ausente_no_llama_al_backend(self):
        sound_player.cargar({"eventos": {"mensaje": Path("no-existe.wav")}})
        with mock.patch.object(sound_player, "_reproducir_winmm") as winmm, \
                mock.patch.object(sound_player, "_reproducir_fallback") as fallback:
            sound_player.reproducir("mensaje")

        winmm.assert_not_called()
        fallback.assert_not_called()

    def test_reproducir_archivo_existente_llama_al_backend(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directorio:
            ruta = Path(directorio) / "mensaje.wav"
            ruta.touch()
            sound_player.cargar({"eventos": {"mensaje": ruta}})
            with mock.patch.object(sound_player, "_reproducir_fallback") as fallback:
                sound_player.reproducir("mensaje")

        fallback.assert_called_once_with(ruta)

    def test_cerrar_sin_haber_cargado_no_lanza(self):
        sound_player.cerrar()


if __name__ == "__main__":
    unittest.main()
