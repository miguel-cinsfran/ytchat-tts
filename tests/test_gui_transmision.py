"""Pruebas del diálogo de Transmisión sin conectar con OBS."""

import unittest
from unittest import mock

import gui_transmision
import obs_cliente
import obs_disposicion

try:
    import wx
    _HAY_WX = True
except Exception:
    _HAY_WX = False


class GestorFalso:

    def __init__(self, fallo=False):
        self.fallo = fallo
        self.escalable = True
        self.llamadas = []
        self.fuentes_enviadas = []
        self.instantaneas = []
        self.snap = obs_disposicion.SnapshotPanel(
            conectado=True, escena="Principal", ancho=460, alto=620,
            lienzo_ancho=1600, lienzo_alto=900, izquierda=32, arriba=18,
            visible=True, bloqueada=False)
        self.snap_nuevo = self.snap
        self.transformacion_inicial = {"positionX": 32, "positionY": 18, "alignment": 5}
        self.tiene_panel = True
        self.transmitiendo = False
        self.grabando = False
        self.grabacion_en_pausa = False
        self.escena_resultante = "Principal"

    def conectar(self):
        if self.fallo:
            raise obs_cliente.ObsError("OBS no está disponible")
        self.llamadas.append(("conectar",))

    def cerrar(self): self.llamadas.append(("cerrar",))
    @property
    def conectado(self): return True
    def escenas(self): return ("Principal", "Juego")
    def escena_al_aire(self): return self.escena_resultante
    def poner_escena_al_aire(self, escena):
        self.llamadas.append(("poner_escena_al_aire", escena))
        return self.escena_resultante
    def fuentes(self, escena):
        return {"Principal": tuple(fuente for fuente in ("Cámara", "Chat YTChat", "Juego")
                                    if fuente != "Chat YTChat" or self.tiene_panel),
                "Juego": ("Captura",)}.get(escena, ())
    def asegurar_fuente(self, *args):
        self.llamadas.append(("asegurar_fuente",) + args)
        self.tiene_panel = True
    def _llamar(self, nombre, args, kwargs):
        self.llamadas.append((nombre,) + args)
        self.fuentes_enviadas.append((nombre, kwargs.get("fuente")))
        self.snap = self.snap_nuevo

    def colocar(self, *args, **kwargs): self._llamar("colocar", args, kwargs)
    def posicionar(self, *args, **kwargs): self._llamar("posicionar", args, kwargs)
    def transformacion(self, *args, **kwargs): return self.transformacion_inicial
    def mover(self, *args, **kwargs): self._llamar("mover", args, kwargs)
    def redimensionar(self, *args, **kwargs): self._llamar("redimensionar", args, kwargs)
    def escalar(self, *args, **kwargs):
        self._llamar("escalar", args, kwargs)
        return self.escalable
    def mostrar(self, *args, **kwargs): self._llamar("mostrar", args, kwargs)
    def fijar(self, *args, **kwargs): self._llamar("fijar", args, kwargs)
    def al_frente(self, *args, **kwargs): self._llamar("al_frente", args, kwargs)
    def instantanea(self, *args, **kwargs):
        self.instantaneas.append((args, kwargs.get("fuente")))
        return self.snap
    def captura_de_escena(self, *args): self.llamadas.append(("captura_de_escena",) + args)
    def estado_transmision(self):
        return {"outputActive": self.transmitiendo, "outputDuration": 61,
                "outputSkippedFrames": 0, "outputTotalFrames": 100}
    def estado_grabacion(self):
        return {"outputActive": self.grabando, "outputPaused": self.grabacion_en_pausa,
                "outputTimecode": "00:01:02.000"}
    def alternar_transmision(self):
        self.transmitiendo = not self.transmitiendo
        self.llamadas.append(("alternar_transmision",))
        return self.transmitiendo
    def alternar_grabacion(self):
        self.grabando = not self.grabando
        self.llamadas.append(("alternar_grabacion",))
        return self.grabando
    def alternar_pausa_grabacion(self):
        self.grabacion_en_pausa = not self.grabacion_en_pausa
        self.llamadas.append(("alternar_pausa_grabacion",))
        return self.grabacion_en_pausa


class HiloInmediato:

    def __init__(self, target, **kwargs): self.target = target
    def start(self): self.target()


class Evento:
    def Skip(self): pass


class EventoTecla:
    def __init__(self, codigo, ctrl=False, shift=False):
        self.codigo = codigo
        self.ctrl = ctrl
        self.shift = shift
        self.se_omitio = False

    def GetKeyCode(self): return self.codigo
    def ControlDown(self): return self.ctrl
    def ShiftDown(self): return self.shift
    def Skip(self): self.se_omitio = True


@unittest.skipUnless(_HAY_WX, "wxPython no está instalado")
class TestTransmisionDialog(unittest.TestCase):

    def setUp(self):
        self.app = wx.App() if not wx.App.Get() else wx.App.Get()
        self.anuncios = []
        self.categorias = []
        def anunciar(texto, categoria=""):
            self.anuncios.append(texto)
            self.categorias.append(categoria)
        self.parches = [
            mock.patch.object(gui_transmision.threading, "Thread", HiloInmediato),
            mock.patch.object(gui_transmision.wx, "CallAfter", lambda funcion, *args: funcion(*args)),
            mock.patch.object(gui_transmision, "anunciar", anunciar),
            mock.patch.object(gui_transmision.sound_player, "reproducir"),
        ]
        for parche in self.parches: parche.start()
        self.gestor = GestorFalso()
        self.dialogo = gui_transmision.TransmisionDialog(None, self.gestor)
        self.anuncios.clear()

    def tearDown(self):
        self.dialogo.Destroy()
        for parche in reversed(self.parches): parche.stop()

    def test_fallo_al_abrir_desactiva_controles_y_muestra_error(self):
        self.dialogo.Destroy()
        gestor = GestorFalso(fallo=True)
        self.dialogo = gui_transmision.TransmisionDialog(None, gestor)
        self.assertIn("OBS no está disponible", self.dialogo.txt_estado.GetValue())
        self.assertFalse(self.dialogo.cho_escena.IsEnabled())
        self.assertFalse(self.dialogo.btn_tamano.IsEnabled())

    def test_cambiar_posicion_usa_clave_de_anclaje(self):
        self.dialogo.cho_posicion.SetSelection(8)
        self.dialogo._colocar(Evento())
        self.assertIn(("colocar", "Principal", "inferior-derecha"), self.gestor.llamadas)

    def test_carga_las_fuentes_y_prefiere_el_panel_de_chat(self):
        self.assertEqual(self.dialogo.cho_fuente.GetStrings(), ["Cámara", "Chat YTChat", "Juego"])
        self.assertEqual(self.dialogo.cho_fuente.GetStringSelection(), "Chat YTChat")

    def test_apertura_anuncia_el_estado_sin_preparar_nada(self):
        gestor = GestorFalso()
        encender = mock.Mock()
        with mock.patch.object(gui_transmision.overlay_servidor, "esta_encendido",
                               return_value=False), \
             mock.patch.object(gui_transmision.overlay_servidor, "puerto_actual",
                               return_value=None), \
             mock.patch.object(gui_transmision.overlay_servidor, "encender", encender):
            dialogo = gui_transmision.TransmisionDialog(None, gestor)
        self.addCleanup(dialogo.Destroy)
        self.assertIn("Falta preparar el panel. El panel de chat está apagado.", self.anuncios)
        self.assertIn("Al aire: Principal", self.anuncios)
        encender.assert_not_called()

    def test_preparar_panel_enciende_y_crea_solo_lo_necesario(self):
        for encendido, tiene_panel in ((False, False), (True, False),
                                       (False, True), (True, True)):
            with self.subTest(encendido=encendido, tiene_panel=tiene_panel):
                self.gestor.tiene_panel = tiene_panel
                self.gestor.llamadas.clear()
                encender = mock.Mock()
                with mock.patch.object(gui_transmision.overlay_servidor, "esta_encendido",
                                       return_value=encendido), \
                     mock.patch.object(gui_transmision.overlay_servidor, "puerto_actual",
                                       return_value=8730), \
                     mock.patch.object(gui_transmision.overlay_servidor, "encender", encender):
                    self.dialogo._preparar(Evento())
                self.assertEqual(encender.call_count, int(not encendido))
                llamadas = [llamada for llamada in self.gestor.llamadas
                            if llamada[0] == "asegurar_fuente"]
                self.assertEqual(len(llamadas), int(not tiene_panel))
                if llamadas:
                    self.assertEqual(llamadas[0], ("asegurar_fuente", "Principal",
                                                    "http://127.0.0.1:8730/chat", 460, 620))

    def test_preparar_panel_anuncia_si_el_puerto_esta_ocupado(self):
        with mock.patch.object(gui_transmision.overlay_servidor, "esta_encendido",
                               return_value=False), \
             mock.patch.object(gui_transmision.overlay_servidor, "puerto_actual",
                               return_value=8765), \
             mock.patch.object(gui_transmision.overlay_servidor, "encender",
                               side_effect=gui_transmision.overlay_servidor.OverlayPuertoOcupadoError):
            self.dialogo._preparar(Evento())
        self.assertEqual(self.anuncios[-1],
                         "No se pudo encender el panel, el puerto 8765 está ocupado")

    def test_cambiar_escena_rehace_las_fuentes(self):
        self.dialogo.cho_escena.SetStringSelection("Juego")
        self.dialogo._cambiar_escena(Evento())
        self.assertEqual(self.dialogo.cho_fuente.GetStrings(), ["Captura"])
        self.assertEqual(self.dialogo.cho_fuente.GetStringSelection(), "Captura")
        self.assertNotIn(("poner_escena_al_aire", "Juego"), self.gestor.llamadas)

    def test_poner_al_aire_usa_la_escena_elegida_y_anuncia_la_devuelta(self):
        self.dialogo.cho_escena.SetStringSelection("Juego")
        self.gestor.escena_resultante = "Principal"
        self.dialogo._poner_al_aire(Evento())
        self.assertIn(("poner_escena_al_aire", "Juego"), self.gestor.llamadas)
        self.assertEqual(self.anuncios[-1], "Al aire: Principal")

    def test_boton_poner_al_aire_sigue_a_escena_en_las_acciones(self):
        indice = self.dialogo._acciones.index(self.dialogo.cho_escena)
        self.assertIs(self.dialogo._acciones[indice + 1], self.dialogo.btn_poner_al_aire)
        self.assertEqual(self.dialogo.btn_poner_al_aire.GetName(), "Poner al aire")

    def test_leer_y_ajuste_fino_piden_la_instantanea_de_la_fuente_elegida(self):
        self.dialogo.cho_fuente.SetSelection(0)
        self.gestor.instantaneas.clear()

        self.dialogo._cambiar_fuente(Evento())
        self.assertEqual(self.gestor.instantaneas[-1], (("Principal",), "Cámara"))

        self.dialogo._ajuste_en_curso = True
        self.dialogo._mover_ajuste(10, 0)
        self.assertEqual(self.gestor.instantaneas[-1], (("Principal",), "Cámara"))

    def test_aplicar_tamano_usa_los_dos_numeros(self):
        self.dialogo.sp_ancho.SetValue(800)
        self.dialogo.sp_alto.SetValue(500)
        self.dialogo._tamano(Evento())
        self.assertIn(("redimensionar", "Principal", 800, 500), self.gestor.llamadas)

    def test_acciones_operan_sobre_la_fuente_elegida(self):
        self.dialogo.cho_fuente.SetStringSelection("Cámara")
        self.dialogo.cho_posicion.SetSelection(0)
        self.dialogo._colocar(Evento())
        self.dialogo._mostrar(Evento())
        self.dialogo._fijar(Evento())
        self.dialogo._frente(Evento())
        self.assertEqual(self.gestor.fuentes_enviadas[-4:], [
            ("colocar", "Cámara"), ("mostrar", "Cámara"),
            ("fijar", "Cámara"), ("al_frente", "Cámara"),
        ])

    def test_aplicar_tamano_redimensiona_el_panel_y_escala_otra_fuente(self):
        self.dialogo._tamano(Evento())
        self.dialogo.cho_fuente.SetStringSelection("Cámara")
        self.dialogo._tamano(Evento())
        self.assertIn(("redimensionar", "Principal", 460, 620), self.gestor.llamadas)
        self.assertIn(("escalar", "Principal", 460, 620), self.gestor.llamadas)
        self.assertIn(("redimensionar", None), self.gestor.fuentes_enviadas)
        self.assertIn(("escalar", "Cámara"), self.gestor.fuentes_enviadas)

    def test_tamano_sin_imagen_no_anuncia_exito(self):
        self.dialogo.cho_fuente.SetStringSelection("Cámara")
        self.gestor.escalable = False
        self.dialogo._tamano(Evento())
        self.assertEqual(self.anuncios[-1], "Cámara todavía no informa su tamaño.")
        self.assertNotIn("Cámara. 460 por 620", self.anuncios)

    def test_mostrar_usa_el_valor_de_la_casilla(self):
        self.dialogo.chk_mostrar.SetValue(False)
        self.dialogo._mostrar(Evento())
        self.assertIn(("mostrar", "Principal", False), self.gestor.llamadas)

    def test_fijar_usa_el_valor_de_la_casilla(self):
        self.dialogo.chk_fijar.SetValue(True)
        self.dialogo._fijar(Evento())
        self.assertIn(("fijar", "Principal", True), self.gestor.llamadas)

    def test_poner_al_frente_llama_al_gestor(self):
        self.dialogo._frente(Evento())
        self.assertIn(("al_frente", "Principal"), self.gestor.llamadas)

    def test_restablecer_devuelve_los_valores_de_las_dos_fuentes_tocadas(self):
        self.dialogo._tamano(Evento())
        self.dialogo.cho_fuente.SetStringSelection("Cámara")
        self.dialogo._tamano(Evento())
        self.dialogo._restaurar(Evento())
        self.assertEqual(self.gestor.llamadas[-8:-4], [
            ("posicionar", "Principal", 32, 18, 5),
            ("redimensionar", "Principal", 460, 620),
            ("mostrar", "Principal", True),
            ("fijar", "Principal", False),
        ])
        self.assertEqual(self.gestor.llamadas[-4:], [
            ("posicionar", "Principal", 32, 18, 5),
            ("escalar", "Principal", 460, 620),
            ("mostrar", "Principal", True),
            ("fijar", "Principal", False),
        ])
        self.assertEqual(self.gestor.fuentes_enviadas[-8:], [
            ("posicionar", "Chat YTChat"), ("redimensionar", None),
            ("mostrar", "Chat YTChat"), ("fijar", "Chat YTChat"),
            ("posicionar", "Cámara"), ("escalar", "Cámara"),
            ("mostrar", "Cámara"), ("fijar", "Cámara"),
        ])

    def test_anuncia_la_instantanea_nueva_despues_del_cambio(self):
        self.gestor.snap_nuevo = obs_disposicion.SnapshotPanel(
            conectado=True, escena="Principal", ancho=800, alto=500,
            lienzo_ancho=1600, lienzo_alto=900, izquierda=32, arriba=18,
            visible=False, bloqueada=True)
        self.dialogo._frente(Evento())
        self.assertIn("800 por 500", self.anuncios[-1])
        self.assertIn("Oculto", self.anuncios[-1])

    def test_ajuste_fino_entra_y_anuncia_la_posicion(self):
        self.dialogo._iniciar_ajuste(Evento())
        self.assertTrue(self.dialogo._ajuste_en_curso)
        self.assertEqual(self.dialogo.btn_ajuste.GetLabel(), "Ajustando, flechas para mover")
        self.assertIn("Ajuste fino.", self.anuncios[-2])
        self.assertEqual(self.anuncios[-1], "Superior izquierda; Libre.")

    def test_flecha_del_ajuste_mueve_y_anuncia_el_conjunto_corto(self):
        self.dialogo._iniciar_ajuste(Evento())
        self.anuncios.clear()
        self.dialogo._tecla_ajuste(EventoTecla(wx.WXK_RIGHT))
        self.assertIn(("mover", "Principal", 10, 0), self.gestor.llamadas)
        self.assertEqual(self.anuncios[-1], "Superior izquierda; Libre.")

    def test_flecha_se_descarta_si_hay_movimiento_en_vuelo(self):
        self.dialogo._iniciar_ajuste(Evento())
        self.dialogo._movimiento_en_vuelo = True
        self.dialogo._tecla_ajuste(EventoTecla(wx.WXK_RIGHT))
        self.assertNotIn(("mover", "Principal", 10, 0), self.gestor.llamadas)

    def test_escape_restaura_la_colocacion(self):
        self.dialogo._iniciar_ajuste(Evento())
        self.dialogo._tecla_ajuste(EventoTecla(wx.WXK_ESCAPE))
        self.assertIn(("posicionar", "Principal", 32, 18, 5), self.gestor.llamadas)
        self.assertIn("Ajuste deshecho", self.anuncios)

    def test_tab_confirma_y_deja_navegar(self):
        self.dialogo._iniciar_ajuste(Evento())
        evento = EventoTecla(wx.WXK_TAB)
        self.dialogo._tecla_ajuste(evento)
        self.assertFalse(self.dialogo._ajuste_en_curso)
        self.assertTrue(evento.se_omitio)
        self.assertIn("Ajuste confirmado", self.anuncios)

    def test_perder_el_foco_confirma_el_ajuste(self):
        self.dialogo._iniciar_ajuste(Evento())
        self.dialogo._ajuste_perdio_foco(Evento())
        self.assertFalse(self.dialogo._ajuste_en_curso)
        self.assertIn("Ajuste confirmado", self.anuncios)

    def test_cerrar_no_anuncia_ni_depende_del_error_de_obs(self):
        self.gestor.cerrar = mock.Mock(side_effect=obs_cliente.ObsError("sin red"))
        self.dialogo.EndModal = mock.Mock()
        self.dialogo._cerrar(Evento())
        self.gestor.cerrar.assert_called_once_with()
        self.dialogo.EndModal.assert_called_once_with(wx.ID_CANCEL)
        self.assertNotIn("Consultando OBS", self.anuncios)

    def test_consulta_rapida_no_anuncia_la_espera(self):
        temporizador = mock.Mock()
        self.dialogo._temporizador_consulta = temporizador
        self.dialogo._actualizar(Evento())
        temporizador.StartOnce.assert_called_once_with(400)
        temporizador.Stop.assert_called_once_with()
        self.assertNotIn("Consultando OBS", self.anuncios)

    def test_consulta_lenta_anuncia_la_espera(self):
        self.dialogo._operacion_en_vuelo = True
        self.dialogo._anunciar_consulta(Evento())
        self.assertIn("Consultando OBS", self.anuncios)

    def test_cerrar_detiene_el_aviso_pendiente(self):
        temporizador = mock.Mock()
        self.dialogo._temporizador_consulta = temporizador
        self.dialogo.EndModal = mock.Mock()
        self.dialogo._cerrar(Evento())
        temporizador.Stop.assert_called_once_with()

    def test_ajuste_fino_declara_su_categoria(self):
        self.dialogo._anunciar_ajuste(self.gestor.snap)
        self.assertEqual(self.categorias[-1], "ajuste")

    def test_botones_de_transmision_y_grabacion_llaman_al_gestor_y_anuncian(self):
        self.dialogo._transmitir(Evento())
        self.dialogo._grabar(Evento())
        self.dialogo._pausar_grabacion(Evento())
        self.assertEqual(self.gestor.llamadas[-3:], [
            ("alternar_transmision",), ("alternar_grabacion",),
            ("alternar_pausa_grabacion",)])
        self.assertEqual(self.anuncios[-3:], ["Transmisión iniciada", "Grabación iniciada",
                                               "Grabación en pausa"])

    def test_actualizar_estado_cambia_etiquetas_nombres_y_pausa(self):
        self.gestor.transmitiendo = True
        self.gestor.grabando = True
        self.dialogo._actualizar(Evento())
        self.assertEqual(self.dialogo.btn_transmitir.GetLabel(), "&Detener la transmision")
        self.assertEqual(self.dialogo.btn_transmitir.GetName(), "Detener la transmision")
        self.assertEqual(self.dialogo.btn_grabar.GetLabel(), "&Detener la grabacion")
        self.assertEqual(self.dialogo.btn_grabar.GetName(), "Detener la grabacion")
        self.assertTrue(self.dialogo.btn_pausar_grabacion.IsEnabled())
        self.assertIn("Transmitiendo desde hace 1 min", self.anuncios)
        self.assertIn("Grabando, 00:01:02", self.anuncios)

    def test_pausa_esta_deshabilitada_si_no_se_esta_grabando(self):
        self.assertFalse(self.dialogo.btn_pausar_grabacion.IsEnabled())


if __name__ == "__main__":
    unittest.main()
