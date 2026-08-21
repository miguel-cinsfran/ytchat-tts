"""Sonda de QA: se mete dentro de la aplicación para grabarla y manejarla.

No es parte de la aplicación y la aplicación no la conoce. Se instala desde
fuera, antes de arrancar `main.py`, y hace dos cosas.

**Graba lo que la aplicación diría, sin decirlo.** Sustituye el objeto por el
que `gui.anunciar` habla con el lector de pantalla. El dueño es ciego y corre
estas pruebas él mismo: una prueba que hable le secuestra el lector mientras
trabaja.

**Recibe órdenes y las ejecuta dentro del proceso.** Esto es lo que corrige el
error de la primera versión, que manejaba la aplicación desde fuera con teclas
sintéticas. Para poder teclear había que robarle el primer plano a Windows, y
el truco para conseguirlo era mandar un ALT sintético, que activa la barra de
menú y hace que los aceleradores dejen de llegar. O sea que la herramienta
rompía justo lo que estaba midiendo.

Desde dentro no hace falta nada de eso: `wx.UIActionSimulator` es la
herramienta que wxWidgets trae para manejar sus propias pruebas, y
`wx.GetTopLevelWindows()` dice qué diálogos hay abiertos sin tener que
adivinarlo desde el árbol de UI Automation.

El canal de órdenes son dos archivos de líneas JSON, uno de entrada y otro de
salida. Es más fácil de depurar que un socket y sobrevive a que un lado muera.
"""

from __future__ import annotations

import json
import os
import threading
import time

VAR_DESTINO = "YTCHAT_QA_ANUNCIOS"
VAR_ORDENES = "YTCHAT_QA_ORDENES"
VAR_RESULTADOS = "YTCHAT_QA_RESULTADOS"


class GrabadorAnuncios:
    """Ocupa el lugar de `accessible_output2` y escribe en vez de hablar.

    Tiene que responder a `speak` y a `braille` porque `gui.anunciar` llama a
    los dos, y cada uno dentro de su propio try. Si alguno faltara, la
    excepción quedaría tapada y la grabación saldría incompleta sin avisar.
    """

    def __init__(self, ruta: str):
        self._ruta = ruta
        self._inicio = time.monotonic()
        self._lock = threading.Lock()

    def _apuntar(self, canal: str, texto: str) -> None:
        registro = {
            "t": round(time.monotonic() - self._inicio, 3),
            "canal": canal,
            "texto": texto,
        }
        with self._lock:
            with open(self._ruta, "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
                f.flush()

    def speak(self, texto, interrupt=False):
        self._apuntar("voz", str(texto))

    def braille(self, texto):
        self._apuntar("braille", str(texto))


# ── Traducción de nombres de tecla a lo que entiende wx ───────────────────────

def _mapa_teclas():
    import wx
    return {
        "tab": wx.WXK_TAB, "enter": wx.WXK_RETURN, "return": wx.WXK_RETURN,
        "esc": wx.WXK_ESCAPE, "escape": wx.WXK_ESCAPE, "space": wx.WXK_SPACE,
        "up": wx.WXK_UP, "down": wx.WXK_DOWN,
        "left": wx.WXK_LEFT, "right": wx.WXK_RIGHT,
        "home": wx.WXK_HOME, "end": wx.WXK_END,
        "delete": wx.WXK_DELETE, "back": wx.WXK_BACK,
        **{f"f{n}": getattr(wx, f"WXK_F{n}") for n in range(1, 13)},
    }


def _modificadores(nombres):
    import wx
    total = wx.MOD_NONE
    for n in nombres or ():
        n = n.lower()
        if n in ("ctrl", "control"):
            total |= wx.MOD_CONTROL
        elif n == "alt":
            total |= wx.MOD_ALT
        elif n == "shift":
            total |= wx.MOD_SHIFT
    return total


def _codigo_tecla(nombre: str) -> int:
    nombre = str(nombre)
    mapa = _mapa_teclas()
    if nombre.lower() in mapa:
        return mapa[nombre.lower()]
    if len(nombre) == 1:
        # Las letras van en mayúscula: UIActionSimulator espera el código de
        # tecla física, no el carácter que saldría.
        return ord(nombre.upper())
    raise ValueError(f"tecla desconocida: {nombre!r}")


# ── Inspección de la interfaz, desde dentro ──────────────────────────────────

def _describir(ventana, profundidad=0):
    """Describe un control de wx como lo vería quien lo usa."""
    import wx

    try:
        nombre = ventana.GetName()
    except Exception:
        nombre = ""
    try:
        etiqueta = ventana.GetLabel()
    except Exception:
        etiqueta = ""
    datos = {
        "clase": ventana.__class__.__name__,
        "nombre": nombre,
        "etiqueta": etiqueta,
        "habilitado": bool(ventana.IsEnabled()),
        "visible": bool(ventana.IsShown()),
        # `IsShown` es la bandera propia del control. Lo que de verdad importa
        # es si está en pantalla, porque una pestaña no seleccionada esconde a
        # sus hijos y el servicio de accesibilidad no los expone. Comparar el
        # árbol de wx entero contra lo que ve Windows sin esto da una
        # diferencia enorme y falsa.
        "en_pantalla": bool(ventana.IsShownOnScreen()),
        "acepta_foco": bool(ventana.AcceptsFocus()),
        "nivel": profundidad,
    }
    if isinstance(ventana, wx.TextCtrl):
        try:    datos["valor"] = ventana.GetValue()
        except Exception: pass
    # El contenido de las listas es lo que de verdad lee el usuario, así que
    # sin esto no se puede comprobar que un mensaje llegó al chat.
    if isinstance(ventana, wx.ListBox):
        try:
            datos["items"] = list(ventana.GetStrings())
            datos["seleccion"] = int(ventana.GetSelection())
        except Exception: pass
    elif isinstance(ventana, wx.ListCtrl):
        try:
            filas = []
            for f in range(ventana.GetItemCount()):
                cols = []
                for c in range(max(1, ventana.GetColumnCount())):
                    try:    cols.append(ventana.GetItemText(f, c))
                    except Exception: break
                filas.append(cols)
            datos["items"] = filas
        except Exception: pass
    return datos


def _arbol(ventana, profundidad=0, tope=8):
    salida = [_describir(ventana, profundidad)]
    if profundidad >= tope:
        return salida
    try:
        hijos = list(ventana.GetChildren())
    except Exception:
        hijos = []
    for h in hijos:
        salida.extend(_arbol(h, profundidad + 1, tope))
    return salida


def _buscar_notebook(ventana):
    """El primer cuaderno de pestanas que cuelgue de esta ventana.

    Se reconoce por lo que sabe hacer y no por su clase: `wx.Notebook`,
    `wx.Listbook` y `wx.Treebook` no comparten antepasado util, y en este
    archivo `wx` solo esta importado dentro de las funciones que lo usan.
    """
    if all(hasattr(ventana, m) for m in
           ("GetPageCount", "GetPageText", "SetSelection", "GetSelection")):
        return ventana
    for hijo in ventana.GetChildren():
        encontrado = _buscar_notebook(hijo)
        if encontrado is not None:
            return encontrado
    return None


def _buscar_control(raiz, nombre: str):
    """Busca por nombre accesible, y si no por etiqueta. None si no está."""
    objetivo = (nombre or "").strip().lower()
    candidatos = []
    for ctrl in _iterar(raiz):
        try:
            n = (ctrl.GetName() or "").strip().lower()
            e = (ctrl.GetLabel() or "").strip().lower().replace("&", "")
        except Exception:
            continue
        if n == objetivo or e == objetivo:
            return ctrl
        if objetivo and (objetivo in n or objetivo in e):
            candidatos.append(ctrl)
    return candidatos[0] if candidatos else None


def _items_de_menu(menu, camino, salida):
    for item in menu.GetMenuItems():
        try:
            if item.IsSeparator():
                continue
            etiqueta = item.GetItemLabelText()
            completa = item.GetItemLabel()
            # El acelerador viaja pegado a la etiqueta tras un tabulador.
            acelerador = completa.split("\t", 1)[1] if "\t" in completa else ""
            datos = {
                "camino": " > ".join(camino + [etiqueta]),
                "etiqueta": etiqueta,
                "acelerador": acelerador,
                "habilitado": bool(item.IsEnabled()),
                "marcable": bool(item.IsCheckable()),
                "id": item.GetId(),
            }
            if item.IsCheckable():
                try:    datos["marcado"] = bool(item.IsChecked())
                except Exception: pass
            sub = item.GetSubMenu()
            if sub is not None:
                datos["submenu"] = True
                salida.append(datos)
                _items_de_menu(sub, camino + [etiqueta], salida)
            else:
                salida.append(datos)
        except Exception:
            continue


def _recorrer_menus(barra):
    salida = []
    if barra is None:
        return salida
    for i in range(barra.GetMenuCount()):
        try:
            titulo = barra.GetMenuLabelText(i)
            salida.append({
                "camino": titulo,
                "etiqueta": titulo,
                "acelerador": "",
                "habilitado": bool(barra.IsEnabledTop(i)),
                "marcable": False,
                "id": None,
                "submenu": True,
            })
            _items_de_menu(barra.GetMenu(i), [titulo], salida)
        except Exception:
            continue
    return salida


def _buscar_item_menu(barra, objetivo: str):
    """Devuelve (id, etiqueta) del ítem cuyo texto coincida. None si no está."""
    for datos in _recorrer_menus(barra):
        # Ojo: los ids que reparte `wx.ID_ANY` son NEGATIVOS. Descartar por
        # `id < 0` para saltarse los menús de nivel superior se lleva puestos
        # todos los ítems de verdad, y el síntoma es "no existe ese menú".
        if datos.get("submenu") or datos.get("id") is None:
            continue
        etiqueta = datos["etiqueta"].strip().lower()
        if etiqueta == objetivo or objetivo in etiqueta:
            return datos["id"], datos["etiqueta"]
    return None


def _iterar(ventana):
    yield ventana
    try:
        hijos = list(ventana.GetChildren())
    except Exception:
        hijos = []
    for h in hijos:
        yield from _iterar(h)


# ── Servidor de órdenes ──────────────────────────────────────────────────────

class Sonda:
    def __init__(self, grabador: GrabadorAnuncios, ordenes: str, resultados: str):
        self.grabador = grabador
        self.ruta_ordenes = ordenes
        self.ruta_resultados = resultados
        self._leidas = 0
        self._lock = threading.Lock()

    def responder(self, id_orden, ok, datos=None, error=None):
        registro = {"id": id_orden, "ok": bool(ok)}
        if datos is not None:
            registro["datos"] = datos
        if error is not None:
            registro["error"] = str(error)
        with self._lock:
            with open(self.ruta_resultados, "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
                f.flush()

    # Todo lo que toca la interfaz corre acá, en el hilo de la interfaz.
    def ejecutar(self, orden):
        import wx
        import gui

        op = orden.get("op")
        id_orden = orden.get("id")
        frame = getattr(gui, "_gui_frame", None)
        try:
            if op == "ping":
                self.responder(id_orden, True, {"listo": frame is not None})

            elif op == "frente":
                # Trae al frente la ventana que de verdad esta arriba, que con
                # un dialogo abierto NO es la principal. Levantar siempre el
                # frame le roba el foco al dialogo, y entonces el recorrido de
                # Tab dentro de Preferencias o del gestor de descargas daba dos
                # paradas en vez de veinte. Medido el 21/08/2026.
                #
                # El foco no se toca: moverlo al frame se lo quita al control
                # que lo tuviera, y sin foco dentro de un control los
                # aceleradores no llegan.
                if frame is None:
                    raise RuntimeError("todavía no hay ventana principal")
                # Ojo: `_ventana_por_titulo` devuelve el frame cuando no se
                # le pasa titulo, asi que preguntarle siempre nunca dejaba
                # elegir el dialogo.
                objetivo = None
                if orden.get("ventana"):
                    objetivo = self._ventana_por_titulo(orden["ventana"], frame)
                if objetivo is None:
                    objetivo = frame
                    for v in wx.GetTopLevelWindows():
                        try:
                            if v is frame or not v.IsShown():
                                continue
                        except Exception:
                            continue
                        objetivo = v
                        if getattr(v, "IsModal", lambda: False)():
                            break
                if objetivo is frame:
                    frame.Iconize(False)
                objetivo.Raise()
                self.responder(id_orden, True, {
                    "activa": bool(objetivo.IsActive()),
                    "ventana": objetivo.GetTitle(),
                })

            elif op == "ventanas":
                abiertas = []
                for v in wx.GetTopLevelWindows():
                    try:
                        abiertas.append({
                            "titulo": v.GetTitle(),
                            "clase": v.__class__.__name__,
                            "visible": bool(v.IsShown()),
                            "modal": bool(getattr(v, "IsModal", lambda: False)()),
                        })
                    except Exception:
                        continue
                self.responder(id_orden, True, {"ventanas": abiertas})

            elif op == "hilos":
                # Los hilos vivos, por nombre. Sirve para atar un congelamiento
                # de la ventana a quien lo esta causando: si `ReproductorWarmup`
                # sigue vivo mientras los `ping` no vuelven, el precalentamiento
                # de libVLC y el bloqueo son el mismo suceso y no dos.
                self.responder(id_orden, True, {
                    "vivos": sorted(h.name for h in threading.enumerate()),
                })

            elif op == "llamar":
                # Llama a un método público del frame. Es lo que usa `main.py`
                # desde el hilo de captura, así que permite montar una sesión
                # entera sin red: conectado, tipo de vídeo, mensajes, todo.
                # Se llama desde el hilo de interfaz, igual que lo hace la
                # aplicación con `wx.CallAfter`.
                if frame is None:
                    raise RuntimeError("todavía no hay ventana principal")
                nombre = orden.get("metodo", "")
                if nombre.startswith("_") or not hasattr(frame, nombre):
                    raise RuntimeError(f"el frame no tiene método {nombre!r}")
                metodo = getattr(frame, nombre)
                if not callable(metodo):
                    raise RuntimeError(f"{nombre!r} no es un método")
                devuelto = metodo(*orden.get("args", []),
                                  **orden.get("kwargs", {}))
                try:
                    json.dumps(devuelto)
                except (TypeError, ValueError):
                    devuelto = repr(devuelto)
                self.responder(id_orden, True, {"devuelto": devuelto})

            elif op == "menus":
                if frame is None:
                    raise RuntimeError("todavía no hay ventana principal")
                self.responder(id_orden, True,
                               {"menus": _recorrer_menus(frame.GetMenuBar())})

            elif op == "menu_click":
                if frame is None:
                    raise RuntimeError("todavía no hay ventana principal")
                objetivo = (orden.get("etiqueta") or "").strip().lower()
                encontrado = _buscar_item_menu(frame.GetMenuBar(), objetivo)
                if encontrado is None:
                    raise RuntimeError(f"no hay ítem de menú {objetivo!r}")
                # Se contesta ANTES de disparar: si el ítem abre un diálogo
                # modal, el control no vuelve hasta que se cierre, y quien
                # espera la respuesta se quedaría colgado creyendo que falló.
                self.responder(id_orden, True, {"etiqueta": encontrado[1]})
                evento = wx.CommandEvent(wx.EVT_MENU.typeId, encontrado[0])
                evento.SetEventObject(frame)
                frame.GetEventHandler().ProcessEvent(evento)

            elif op == "arbol":
                objetivo = self._ventana_por_titulo(orden.get("ventana"), frame)
                if objetivo is None:
                    raise RuntimeError(f"no hay ventana {orden.get('ventana')!r}")
                self.responder(id_orden, True, {"controles": _arbol(objetivo)})

            elif op == "pestanas":
                # Sin esto solo se audita la pestana visible, porque una que no
                # esta seleccionada esconde a sus hijos y el servicio de
                # accesibilidad de Windows no los expone. Cambiar de pagina es
                # la unica forma de mirar el resto con el mismo rasero.
                objetivo = self._ventana_por_titulo(orden.get("ventana"), frame)
                if objetivo is None:
                    raise RuntimeError(f"no hay ventana {orden.get('ventana')!r}")
                libro = _buscar_notebook(objetivo)
                if libro is None:
                    raise RuntimeError("esa ventana no tiene ningun cuaderno "
                                       "de pestanas")
                indice = orden.get("indice")
                if indice is not None:
                    libro.SetSelection(int(indice))
                    wx.SafeYield()
                self.responder(id_orden, True, {
                    "paginas": [libro.GetPageText(i)
                                for i in range(libro.GetPageCount())],
                    "actual": libro.GetSelection(),
                })

            elif op == "foco":
                objetivo = self._ventana_por_titulo(orden.get("ventana"), frame)
                ctrl = _buscar_control(objetivo, orden.get("nombre", ""))
                if ctrl is None:
                    raise RuntimeError(f"no encontré {orden.get('nombre')!r}")
                ctrl.SetFocus()
                self.responder(id_orden, True, {"clase": ctrl.__class__.__name__})

            elif op == "quien_tiene_foco":
                ctrl = wx.Window.FindFocus()
                self.responder(id_orden, True,
                               {"control": _describir(ctrl) if ctrl else None})

            elif op == "teclas":
                sim = wx.UIActionSimulator()
                for paso in orden.get("secuencia", []):
                    tecla = paso[0]
                    mods = paso[1] if len(paso) > 1 else []
                    codigo = _codigo_tecla(tecla)
                    # Char pulsa y suelta, modificadores incluidos. La
                    # documentación de wx avisa de que un modificador sin su
                    # KeyUp queda pegado en Windows, y Char lo evita.
                    sim.Char(codigo, _modificadores(mods))
                    wx.MilliSleep(40)
                self.responder(id_orden, True)

            elif op == "texto":
                ctrl = wx.Window.FindFocus()
                if ctrl is None:
                    raise RuntimeError("no hay nada con el foco")
                if hasattr(ctrl, "SetValue"):
                    ctrl.SetValue(orden.get("valor", ""))
                else:
                    raise RuntimeError(
                        f"{ctrl.__class__.__name__} no acepta texto")
                self.responder(id_orden, True)

            elif op == "pulsar":
                objetivo = self._ventana_por_titulo(orden.get("ventana"), frame)
                ctrl = _buscar_control(objetivo, orden.get("nombre", ""))
                if ctrl is None:
                    raise RuntimeError(f"no encontré {orden.get('nombre')!r}")
                evento = wx.CommandEvent(wx.EVT_BUTTON.typeId, ctrl.GetId())
                evento.SetEventObject(ctrl)
                ctrl.GetEventHandler().ProcessEvent(evento)
                self.responder(id_orden, True)

            elif op == "cerrar_ventana":
                objetivo = self._ventana_por_titulo(orden.get("ventana"), frame)
                if objetivo is None:
                    raise RuntimeError("no está esa ventana")
                objetivo.Close(True)
                self.responder(id_orden, True)

            elif op == "salir":
                self.responder(id_orden, True)
                for v in list(wx.GetTopLevelWindows()):
                    try:    v.Destroy()
                    except Exception: pass

            else:
                raise RuntimeError(f"orden desconocida: {op!r}")
        except Exception as exc:
            self.responder(id_orden, False, error=repr(exc))

    def _ventana_por_titulo(self, titulo, frame):
        import wx
        if not titulo:
            return frame
        objetivo = titulo.strip().lower()
        for v in wx.GetTopLevelWindows():
            try:
                if objetivo in (v.GetTitle() or "").lower():
                    return v
            except Exception:
                continue
        return None

    def vigilar(self):
        """Hilo de fondo: lee órdenes nuevas y las manda al hilo de interfaz."""
        import wx
        while True:
            try:
                if os.path.exists(self.ruta_ordenes):
                    with open(self.ruta_ordenes, encoding="utf-8") as f:
                        lineas = f.read().splitlines()
                    while self._leidas < len(lineas):
                        cruda = lineas[self._leidas].strip()
                        self._leidas += 1
                        if not cruda:
                            continue
                        try:
                            orden = json.loads(cruda)
                        except ValueError:
                            continue
                        wx.CallAfter(self.ejecutar, orden)
            except Exception:
                pass
            time.sleep(0.05)


def instalar() -> str:
    """Silencia la voz, abre el canal de órdenes, y deja constancia de ambos."""
    ruta = os.environ.get(VAR_DESTINO)
    if not ruta:
        raise RuntimeError(
            f"Falta la variable {VAR_DESTINO} con la ruta de la grabación")

    import gui
    grabador = GrabadorAnuncios(ruta)

    # No alcanza con asignar `gui._ao2` acá: `iniciar_gui` llama a `_ao2_init()`
    # por dentro, después, y vuelve a poner el objeto real encima. Costó una
    # corrida entera creer que la sonda estaba puesta cuando no lo estaba, y
    # peor: creer que la aplicación no iba a hablar cuando sí podía.
    if not hasattr(gui, "_ao2_init"):
        raise RuntimeError(
            "gui ya no tiene _ao2_init: la sonda quedó vieja y no puede "
            "garantizar que la aplicación no hable. Revisala antes de seguir.")

    def _init_grabando():
        gui._ao2 = grabador
        grabador._apuntar("sonda", "la aplicación pidió inicializar la voz y "
                                   "se le dio el grabador")

    gui._ao2_init = _init_grabando
    gui._ao2 = grabador
    grabador._apuntar("sonda", "grabador instalado antes de arrancar")

    try:
        gui._snd.silenciar_todo(True)
    except Exception:
        pass

    ordenes = os.environ.get(VAR_ORDENES)
    resultados = os.environ.get(VAR_RESULTADOS)
    if ordenes and resultados:
        sonda = Sonda(grabador, ordenes, resultados)
        hilo = threading.Thread(target=sonda.vigilar, daemon=True,
                                name="QA-Sonda")
        hilo.start()
        grabador._apuntar("sonda", "canal de órdenes abierto")

    return ruta


def arrancar_aplicacion(ruta_main: str) -> None:
    """Instala la sonda y cede el control a `main.py` como si nada."""
    instalar()
    import runpy
    runpy.run_path(ruta_main, run_name="__main__")
