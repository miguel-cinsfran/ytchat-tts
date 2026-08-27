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
    def fuentes(self, escena):
        return {"Principal": ("Cámara", "Chat YTChat", "Juego"),
                "Juego": ("Captura",)}.get(escena, ())
    def asegurar_fuente(self, *args): pass
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
    def instantanea(self, *args, **kwargs): return self.snap
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

    def test_carga_las_fuentes_y_prefiere_el_panel_de_chat(self):
        self.assertEqual(self.dialogo.cho_fuente.GetStrings(), ["Cámara", "Chat YTChat", "Juego"])
        self.assertEqual(self.dialogo.cho_fuente.GetStringSelection(), "Chat YTChat")

    def test_cambiar_escena_rehace_las_fuentes(self):
        self.dialogo.cho_escena.SetStringSelection("Juego")
        self.dialogo._cambiar_escena(Evento())
        self.assertEqual(self.dialogo.cho_fuente.GetStrings(), ["Captura"])
        self.assertEqual(self.dialogo.cho_fuente.GetStringSelection(), "Captura")

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
        self.assertEqual(self.anuncios[-1], "Chat YTChat. Superior izquierda; Libre.")

    def test_flecha_del_ajuste_mueve_y_anuncia_el_conjunto_corto(self):
        self.dialogo._iniciar_ajuste(Evento())
        self.anuncios.clear()
        self.dialogo._tecla_ajuste(EventoTecla(wx.WXK_RIGHT))
        self.assertIn(("mover", "Principal", 10, 0), self.gestor.llamadas)
        self.assertEqual(self.anuncios[-1], "Chat YTChat. Superior izquierda; Libre.")

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


if __name__ == "__main__":
    unittest.main()
