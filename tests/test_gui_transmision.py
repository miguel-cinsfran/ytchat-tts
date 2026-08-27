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
        self.llamadas = []
        self.snap = obs_disposicion.SnapshotPanel(
            conectado=True, escena="Principal", ancho=460, alto=620,
            lienzo_ancho=1600, lienzo_alto=900, izquierda=32, arriba=18,
            visible=True, bloqueada=False)
        self.snap_nuevo = self.snap
        self.transformacion_inicial = {"positionX": 32, "positionY": 18, "alignment": 5}

    def conectar(self):
        if self.fallo:
            raise obs_cliente.ObsError("OBS no está disponible")
        self.llamadas.append(("conectar",))

    def cerrar(self): self.llamadas.append(("cerrar",))
    @property
    def conectado(self): return True
    def escenas(self): return ("Principal", "Juego")
    def escena_al_aire(self): return "Principal"
    def asegurar_fuente(self, *args): pass
    def colocar(self, *args): self.llamadas.append(("colocar",) + args); self.snap = self.snap_nuevo
    def posicionar(self, *args): self.llamadas.append(("posicionar",) + args)
    def transformacion(self, *args): return self.transformacion_inicial
    def mover(self, *args): self.llamadas.append(("mover",) + args); self.snap = self.snap_nuevo
    def redimensionar(self, *args): self.llamadas.append(("redimensionar",) + args); self.snap = self.snap_nuevo
    def mostrar(self, *args): self.llamadas.append(("mostrar",) + args); self.snap = self.snap_nuevo
    def fijar(self, *args): self.llamadas.append(("fijar",) + args); self.snap = self.snap_nuevo
    def al_frente(self, *args): self.llamadas.append(("al_frente",) + args); self.snap = self.snap_nuevo
    def instantanea(self, *args): return self.snap
    def captura_de_escena(self, *args): self.llamadas.append(("captura_de_escena",) + args)


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
        self.parches = [
            mock.patch.object(gui_transmision.threading, "Thread", HiloInmediato),
            mock.patch.object(gui_transmision.wx, "CallAfter", lambda funcion, *args: funcion(*args)),
            mock.patch.object(gui_transmision, "anunciar", self.anuncios.append),
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

    def test_aplicar_tamano_usa_los_dos_numeros(self):
        self.dialogo.sp_ancho.SetValue(800)
        self.dialogo.sp_alto.SetValue(500)
        self.dialogo._tamano(Evento())
        self.assertIn(("redimensionar", "Principal", 800, 500), self.gestor.llamadas)

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

    def test_restablecer_devuelve_los_cuatro_valores_iniciales(self):
        self.dialogo._restaurar(Evento())
        self.assertEqual(self.gestor.llamadas[-4:], [
            ("posicionar", "Principal", 32, 18, 5),
            ("redimensionar", "Principal", 460, 620),
            ("mostrar", "Principal", True),
            ("fijar", "Principal", False),
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


if __name__ == "__main__":
    unittest.main()
