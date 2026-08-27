"""Banco de QA: maneja la aplicación desde dentro y comprueba lo que dice.

Segunda versión. La primera manejaba la aplicación desde fuera con teclas
sintéticas y no servía: para poder teclear había que robarle el primer plano a
Windows, el truco para lograrlo era un ALT sintético, y ALT abre la barra de
menú, así que los aceleradores dejaban de llegar. La herramienta rompía lo que
estaba midiendo, y llegó a dar por roto un Ctrl+S que funciona perfectamente.

Lo que se hace ahora, que es lo que hace la gente que prueba aplicaciones de
escritorio en serio:

- **Manejar desde dentro**, con `wx.UIActionSimulator`, que es la herramienta
  que wxWidgets trae para conducir sus propias pruebas. Sin peleas de foco.
- **Esperar hechos, no relojes.** Ni un `sleep` a ciegas: se espera a que
  aparezca una ventana, a que el foco caiga en un control, o a que la
  aplicación diga algo. Es como sincroniza el banco de pruebas del propio NVDA.
- **Grabar la voz en vez de decirla**, para que correr las pruebas no le
  secuestre el lector de pantalla al dueño.

Lo que sí prueba: que los controles tengan nombre y se alcancen con Tab, que
los atajos hagan lo que dicen, y que la aplicación intente decir lo que
corresponde cuando corresponde.

Lo que NO prueba, y no hay que declararlo probado: que NVDA lo lea, cómo suena,
la línea braille, y si la ventana se ve bien.

Uso:

    .venv\\Scripts\\python.exe qa/conducir.py
    .venv\\Scripts\\python.exe qa/conducir.py --escenario descargas
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "qa"))

from sonda import VAR_DESTINO, VAR_ORDENES, VAR_RESULTADOS  # noqa: E402

TIEMPO_ORDEN = 20.0

# La consola de Windows va en cp1252 y el chat lleva emojis. Sin esto, imprimir
# un super chat revienta la corrida entera con UnicodeEncodeError, y el fallo
# parece de la aplicacion cuando es del banco.
for _flujo in (sys.stdout, sys.stderr):
    try:    _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


class Resultado:
    def __init__(self):
        self.fallos: list[str] = []
        self.notas: list[str] = []

    def fallo(self, texto: str) -> None:
        self.fallos.append(texto)
        print(f"    FALLO  {texto}")

    def nota(self, texto: str) -> None:
        self.notas.append(texto)
        print(f"    . {texto}")

    @property
    def ok(self) -> bool:
        return not self.fallos


class VentanaNoActiva(RuntimeError):
    """No se pudo dejar la ventana al frente, así que no se tecleó nada.

    Pasa cuando el dueño está usando la máquina, que es lo normal mientras el
    banco corre. No es un defecto de la aplicación y no se cuenta como tal.
    """


class OrdenRechazada(RuntimeError):
    """La sonda recibió la orden y dijo que no. No es un fallo de la aplicación."""


class Aplicacion:
    """La aplicación corriendo, con el canal de órdenes abierto."""

    def __init__(self, carpeta: Path):
        carpeta.mkdir(parents=True, exist_ok=True)
        self.anuncios_ruta = carpeta / "qa-anuncios.jsonl"
        self.ordenes_ruta = carpeta / "qa-ordenes.jsonl"
        self.resultados_ruta = carpeta / "qa-resultados.jsonl"
        self.salida_ruta = carpeta / "qa-salida-app.txt"
        for r in (self.anuncios_ruta, self.ordenes_ruta, self.resultados_ruta,
                  self.salida_ruta):
            if r.exists():
                r.unlink()
        self._siguiente_id = 1
        self.proceso = None

    # ── ciclo de vida ────────────────────────────────────────────────────────

    def arrancar(self) -> None:
        entorno = dict(os.environ)
        entorno[VAR_DESTINO] = str(self.anuncios_ruta)
        entorno[VAR_ORDENES] = str(self.ordenes_ruta)
        entorno[VAR_RESULTADOS] = str(self.resultados_ruta)
        codigo = (
            "import sys; sys.path.insert(0, r'%s'); "
            "import sonda as qa_sonda; qa_sonda.arrancar_aplicacion(r'%s')"
            % (RAIZ / "qa", RAIZ / "main.py")
        )
        # La salida de la aplicacion NO se tira: wx escribe ahi sus avisos de
        # widgets mal construidos, y hoy no los lee nadie.
        self._salida = open(self.salida_ruta, "w", encoding="utf-8",
                            errors="replace")
        self.proceso = subprocess.Popen(
            [sys.executable, "-c", codigo], cwd=str(RAIZ), env=entorno,
            stdout=self._salida, stderr=subprocess.STDOUT)

    def esperar_lista(self, segundos: float = 60.0) -> bool:
        """Espera a que la ventana principal exista, preguntándoselo a ella."""
        limite = time.time() + segundos
        while time.time() < limite:
            # Si el proceso ya murió no hay nada que esperar. Pasa cuando otra
            # instancia sigue abierta: `main.py` avisa y se cierra, y sin esto
            # el banco agotaba el minuto entero sin saber por qué.
            if self.proceso is not None and self.proceso.poll() is not None:
                return False
            try:
                r = self.pedir("ping", tiempo=3.0, tolerar=True)
                if r.get("ok") and r.get("datos", {}).get("listo"):
                    return True
            except TimeoutError:
                pass
        return False

    def murio_sola(self) -> bool:
        """¿Se cerró la aplicación por su cuenta? Normalmente, el guardián de
        instancia única: ya había otra ventana abierta."""
        return self.proceso is not None and self.proceso.poll() is not None

    def cerrar(self) -> None:
        try:
            self.pedir("salir", tiempo=5.0)
        except Exception:
            pass
        if self.proceso is not None:
            try:
                self.proceso.terminate()
                self.proceso.wait(timeout=10)
            except Exception:
                try:    self.proceso.kill()
                except Exception: pass
        try:    self._salida.close()
        except Exception: pass
        # `main.py` solo deja abrir una instancia: si la anterior sigue viva,
        # la siguiente muere mostrando un aviso y el banco se queda esperando
        # un `ping` que no va a llegar nunca.
        self.proceso = None

    # ── canal de órdenes ─────────────────────────────────────────────────────

    def pedir(self, op: str, tiempo: float = TIEMPO_ORDEN,
              tolerar: bool = False, **extra) -> dict:
        """Manda una orden y espera la respuesta.

        Una orden rechazada revienta, y eso es a propósito. Antes devolvía el
        sobre con `ok` en falso y el escenario seguía como si nada: el
        21/08/2026 el escenario del reproductor dio nueve fallos de
        accesibilidad que en realidad eran nueve órdenes que la sonda nunca
        pudo ejecutar. Un banco que confunde «no lo encontré» con «está mal
        hecho» miente en la dirección más cara.

        `tolerar=True` para los casos en que el rechazo es la respuesta.
        """
        id_orden = self._siguiente_id
        self._siguiente_id += 1
        orden = {"id": id_orden, "op": op}
        orden.update(extra)
        with open(self.ordenes_ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(orden, ensure_ascii=False) + "\n")
            f.flush()

        limite = time.time() + tiempo
        while time.time() < limite:
            for linea in self._lineas(self.resultados_ruta):
                if linea.get("id") == id_orden:
                    if not linea.get("ok") and not tolerar:
                        raise OrdenRechazada(
                            f"{op}({extra}): {linea.get('error')}")
                    return linea
            time.sleep(0.05)
        raise TimeoutError(f"la orden {op!r} no contestó en {tiempo} s")

    @staticmethod
    def _lineas(ruta: Path) -> list[dict]:
        if not ruta.exists():
            return []
        salida = []
        crudo = ruta.read_text(encoding="utf-8", errors="replace")
        for linea in crudo.splitlines():
            linea = linea.strip()
            if linea:
                try:
                    salida.append(json.loads(linea))
                except ValueError:
                    pass
        return salida

    # ── consultas ────────────────────────────────────────────────────────────

    @property
    def anuncios(self) -> list[dict]:
        return self._lineas(self.anuncios_ruta)

    def dijo(self, fragmento: str, desde: int = 0) -> bool:
        f = fragmento.lower()
        return any(f in a["texto"].lower() for a in self.anuncios[desde:])

    def esperar_dicho(self, fragmento: str, segundos: float = 15.0,
                      desde: int = 0) -> bool:
        """Espera a que la aplicación intente decir algo. Así sincroniza NVDA."""
        limite = time.time() + segundos
        while time.time() < limite:
            if self.dijo(fragmento, desde):
                return True
            time.sleep(0.1)
        return False

    def ventanas(self) -> list[dict]:
        return self.pedir("ventanas").get("datos", {}).get("ventanas", [])

    def esperar_ventana(self, titulo: str, segundos: float = 15.0):
        """Espera un diálogo.

        Se pregunta desde dentro, así que los modales también se ven. Eso es lo
        que la versión anterior no conseguía: `Desktop().windows()` de pywinauto
        no devolvía los diálogos modales, y por eso parecía que no se abrían.
        """
        objetivo = titulo.lower()
        limite = time.time() + segundos
        while time.time() < limite:
            for v in self.ventanas():
                if objetivo in (v.get("titulo") or "").lower() and v.get("visible"):
                    return v
            time.sleep(0.2)
        return None

    def arbol(self, ventana: str | None = None) -> list[dict]:
        datos = self.pedir("arbol", ventana=ventana).get("datos", {})
        return datos.get("controles", [])

    def foco(self) -> dict | None:
        return self.pedir("quien_tiene_foco").get("datos", {}).get("control")

    def al_frente(self, segundos: float = 5.0) -> bool:
        """Trae la ventana al frente y espera a que Windows lo confirme.

        `wx.UIActionSimulator` escribe en la ventana que el sistema tenga al
        frente, no en la que uno cree. Pedir `frente` y teclear en la línea
        siguiente funcionaba o no según lo ocupada que estuviera la máquina: el
        21/08/2026 eso hizo que el banco diera por mudo el volumen del
        reproductor, que anuncia perfectamente.
        """
        limite = time.time() + segundos
        while time.time() < limite:
            if self.pedir("frente").get("datos", {}).get("activa"):
                return True
            time.sleep(0.2)
        return False

    def hilos(self) -> list[str]:
        """Los hilos vivos de la aplicación, por nombre."""
        return self.pedir("hilos").get("datos", {}).get("vivos", [])

    def llamar(self, metodo: str, *args, **kwargs) -> dict:
        """Llama a un método público del frame, como hace `main.py`."""
        return self.pedir("llamar", metodo=metodo, args=list(args),
                          kwargs=kwargs)

    def simular_sesion_youtube(self, titulo: str = "Directo de prueba",
                               espectadores: int = 42) -> None:
        """Monta una sesión de YouTube sin tocar la red.

        Usa la misma API pública que `main.py` invoca desde el hilo de captura.
        No es hacer trampa: es probar la interfaz sin depender de que haya un
        directo vivo y de que la red se porte bien.
        """
        self.llamar("set_conectado", True)
        self.llamar("set_tipo_video", "live", "ArKbAx1K-2U")
        self.llamar("set_titulo_stream", titulo)
        self.llamar("set_espectadores", espectadores)
        self.llamar("set_live_chat_id", "prueba-qa")

    def restaurar_desconectado(self) -> None:
        """Deshace una sesion simulada y deja la aplicacion desconectada.

        Lo necesita cualquier escenario que simule una sesion y no sea el
        ultimo de la corrida. Medido el 26/08/2026: `redactar` simulaba una
        sesion y no la deshacia, asi que `chat`, que corre despues y mide
        justamente el PASO de desconectado a conectado, encontraba la
        aplicacion ya conectada y fallaba diciendo que conectar no anunciaba
        nada. El defecto no estaba donde saltaba.
        """
        self.llamar("set_live_chat_id", "")
        self.llamar("set_titulo_stream", "")
        self.llamar("set_espectadores", 0)
        self.llamar("set_conectado", False)

    def simular_sesion_tiktok(self, usuario: str = "rolon_100") -> None:
        self.llamar("set_conectado", True)
        self.llamar("configurar_tiktok", usuario, "")

    def mensaje(self, autor: str, texto: str, hora: str = "12:00",
                tipo: str = "text", monto: str = "") -> None:
        self.llamar("agregar_mensaje_chat", autor, texto, hora, tipo, monto, "")

    def menus(self) -> list[dict]:
        return self.pedir("menus").get("datos", {}).get("menus", [])

    def abrir_por_menu(self, etiqueta: str) -> dict:
        """Dispara un ítem de menú por su texto, sin usar el teclado."""
        return self.pedir("menu_click", etiqueta=etiqueta, tiempo=10.0)

    def teclas(self, *pasos) -> dict:
        """teclas(("s", ["ctrl"])) para Ctrl+S, o teclas("tab").

        Se asegura de que la ventana esté al frente antes y después. El
        simulador de wx escribe en la ventana que tenga el sistema al frente,
        no en la que uno cree: si el dueño se pasó al navegador en medio de la
        corrida, las teclas van a parar allá y el banco lo reporta como que la
        aplicación se quedó muda. Prefiere no medir a medir mal.
        """
        if not self.al_frente():
            raise VentanaNoActiva("la ventana no está al frente")
        secuencia = []
        for p in pasos:
            secuencia.append(list(p) if isinstance(p, (list, tuple)) else [p])
        r = self.pedir("teclas", secuencia=secuencia)
        if not self.pedir("frente").get("datos", {}).get("activa"):
            raise VentanaNoActiva("la ventana perdió el frente mientras se "
                                  "tecleaba, no se puede juzgar lo que pasó")
        return r


# ── Comprobaciones ───────────────────────────────────────────────────────────

CLASES_INTERACTIVAS = {
    "Button", "BitmapButton", "TextCtrl", "Choice", "ComboBox", "ListBox",
    "ListCtrl", "CheckBox", "RadioButton", "RadioBox", "Slider",
    "DirPickerCtrl", "FilePickerCtrl", "SpinCtrl", "Notebook",
}

# wx le pone a cada control un nombre por defecto según su clase. Que exista no
# quiere decir que alguien lo haya nombrado, así que estos no cuentan.
NOMBRES_POR_DEFECTO = {
    "", "button", "text", "textctrl", "choice", "listctrl", "listbox",
    "checkbox", "panel", "staticbox", "dirpicker", "filepicker", "combobox",
    "radiobutton", "radiobox", "slider", "spinctrl", "notebook", "control",
}


def parece_clave_cruda(texto: str) -> bool:
    """¿Esto es lenguaje humano o una clave del `config.ini` que se escapó?

    Distinción pagada el 21/08/2026: una mutación cambió la etiqueta de un
    botón de atajos por su clave de configuración, `descargas_abrir`, y ni la
    suite ni este banco dijeron nada. El control tenía nombre, y el banco solo
    comprobaba que lo tuviera. Un lector de pantalla lee «descargas guion bajo
    abrir», que no es un nombre: es un identificador de programador.
    """
    t = (texto or "").strip()
    # Los botones de atajo se llaman «accion: Ctrl+S», asi que la parte que
    # tiene que ser legible es la de antes de los dos puntos.
    if ":" in t:
        t = t.split(":", 1)[0].strip()
    if not t or " " in t:
        return False
    return "_" in t and t == t.lower() and t.replace("_", "").isalnum()


def revisar_nombres(controles: list[dict], res: Resultado, donde: str) -> None:
    """Un control interactivo sin nombre ni etiqueta es mudo para el lector."""
    mudos = []
    crudos = []
    interactivos = 0
    for c in controles:
        if c.get("clase") not in CLASES_INTERACTIVAS or not c.get("visible"):
            continue
        interactivos += 1
        nombre = (c.get("nombre") or "").strip()
        etiqueta = (c.get("etiqueta") or "").strip()
        if nombre.lower() in NOMBRES_POR_DEFECTO and not etiqueta:
            mudos.append(c)
        # Solo se juzga el texto que de verdad se anuncia. El `name=` interno
        # de wx puede ser un identificador (`Atajo_silenciar_sonidos`) sin que
        # eso llegue al lector, y darlo por defecto llena el informe de ruido.
        elif parece_clave_cruda(etiqueta or nombre):
            crudos.append((c, etiqueta or nombre))
    for c in mudos:
        res.fallo(f"{donde}: un {c['clase']} no tiene nombre ni etiqueta")
    for c, texto in crudos:
        res.fallo(f"{donde}: un {c['clase']} se llama «{texto}», que parece "
                  "una clave de configuración y no una frase")
    if not mudos and not crudos:
        res.nota(f"{donde}: {interactivos} controles interactivos, "
                 "todos con nombre o etiqueta")


def recorrer_tab(app: Aplicacion, res: Resultado, donde: str,
                 vueltas: int = 20) -> list[str]:
    """Pulsa Tab y anota dónde cae el foco, preguntándoselo a wx."""
    visto: list[str] = []
    for _ in range(vueltas):
        ctrl = app.foco()
        if ctrl:
            nombre = (ctrl.get("nombre") or "").strip()
            etiqueta = (ctrl.get("etiqueta") or "").strip().replace("&", "")
            legible = etiqueta or nombre
            if nombre.lower() in NOMBRES_POR_DEFECTO and not etiqueta:
                legible = "(SIN NOMBRE)"
            etiq = f"{ctrl['clase']}: {legible}"
            if etiq not in visto:
                visto.append(etiq)
        app.teclas("tab")
    for v in visto:
        if "(SIN NOMBRE)" in v:
            res.fallo(f"{donde}: el foco cae en algo sin nombre, {v}")
    if not visto:
        res.fallo(f"{donde}: Tab no movió el foco a ningún sitio legible")
    return visto


def _con_tope(funcion, segundos: float, por_defecto):
    """Corre algo en un hilo aparte y se rinde si tarda de más.

    Hace falta porque una llamada de UI Automation a un proceso que no responde
    no tiene tope propio y no se puede interrumpir. El hilo queda colgado, pero
    es demonio y no impide salir: peor es que se cuelgue la corrida entera.
    """
    import threading
    resultado = [por_defecto]

    def _correr():
        try:
            resultado[0] = funcion()
        except Exception:
            pass

    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()
    hilo.join(segundos)
    return resultado[0]


def roles_segun_windows(titulo: str, tope: float = 20.0) -> dict[str, int]:
    """Qué roles expone esta ventana al servicio de accesibilidad de Windows.

    Es la única comprobación que necesita mirar desde fuera, y por eso usa
    pywinauto: desde dentro wx siempre dirá `CheckBox`, aunque Windows la esté
    exponiendo como botón. La diferencia es justo lo que discute `AGENTS.md`.
    """
    try:
        from pywinauto import Desktop
    except ImportError:
        return {}
    return _con_tope(lambda: _roles_sin_tope(titulo, Desktop), tope, {})


def _ventana_por_titulo(Desktop, objetivo):
    """La ventana cuyo titulo contiene `objetivo`, este donde este.

    Se mira primero entre las ventanas de raiz. Si no aparece ahi, se busca
    DENTRO de la ventana de la aplicacion, y esa segunda vuelta es la que hace
    falta de verdad: medido el 26/08/2026, el dialogo de Preferencias NO cuelga
    de la raiz sino de la ventana principal, porque un `wx.Dialog` modal tiene
    dueno y Windows lo expone como descendiente suyo.

    Ese detalle dejo muda la comprobacion de owner-drawn durante un dia entero:
    devolvia vacio y el banco lo anotaba como «no se pudo leer el arbol», que
    parece un problema del entorno y no una comprobacion que no se hace.

    La segunda vuelta se limita a la ventana de la aplicacion a proposito.
    Recorrer los descendientes de CADA ventana del escritorio tardo 72,4
    segundos contra 0,8, porque UI Automation pregunta a cada proceso ajeno y
    espera a su bucle de mensajes. Dentro de la propia aplicacion son 0,2.
    """
    for w in _candidatas_uia(Desktop):
        try:
            if (w.element_info.control_type in ("Window", "Pane")
                    and objetivo in (w.element_info.name or "").lower()):
                return w
        except Exception:
            continue
    return None


def _candidatas_uia(Desktop):
    """Las ventanas donde puede estar algo nuestro, primero las mas probables.

    Se recorren las ventanas de raiz, que son diez y se enumeran en menos de un
    segundo, y solo despues los descendientes de la ventana de la aplicacion,
    que son otros 0,2 segundos.

    Lo que NO se hace, y es el motivo de que esto exista, es pedirle a UI
    Automation `top_level_only=False`. Eso recorre los descendientes de CADA
    ventana del escritorio: pregunta a Chrome, a Steam, a Telegram, y espera al
    bucle de mensajes de cada uno. Medido el 25/08/2026 en 72,4 segundos contra
    0,8, y el 26/08/2026 comiendo casi entera la corrida de `dialogos_ayuda`,
    que bajo de 72 segundos a 12 al quitarlo.

    El tope por reloj no protegia de esto: una sola pasada tarda mas que el
    tope entero y no se puede interrumpir desde fuera.
    """
    raices = list(Desktop(backend="uia").windows(top_level_only=True))
    for w in raices:
        yield w
    for w in raices:
        try:
            if not (w.element_info.name or "").lower().startswith("ytchat"):
                continue
        except Exception:
            continue
        for d in w.descendants():
            yield d


def _roles_sin_tope(titulo, Desktop) -> dict[str, int]:
    cuenta: dict[str, int] = {}
    _ULTIMOS_NOMBRES.clear()
    try:
        w = _ventana_por_titulo(Desktop, titulo.lower())
        if w is None:
            return cuenta
        for d in w.descendants():
            try:
                rol = d.element_info.control_type
                nombre = (d.element_info.name or "").strip()
            except Exception:
                continue
            cuenta[rol] = cuenta.get(rol, 0) + 1
            _ULTIMOS_NOMBRES.setdefault(rol, []).append(nombre)
    except Exception:
        pass
    return cuenta


# Se guardan los nombres del ultimo vistazo para poder decir QUE control es el
# que no cuadra, en vez de solo cuantos faltan. Un recuento sin nombre obliga a
# adivinar, y adivinar es como se producen los hallazgos falsos.
_ULTIMOS_NOMBRES: dict[str, list[str]] = {}


def nombres_segun_windows(rol: str) -> list[str]:
    return list(_ULTIMOS_NOMBRES.get(rol, []))


def auditar_dialogo(app: Aplicacion, res: Resultado, etiqueta_menu: str,
                    titulo: str, vueltas_tab: int = 16,
                    esperados: tuple[str, ...] = (),
                    esperados_en_tab: tuple[str, ...] = ()) -> bool:
    """Abre un diálogo desde el menú, lo audita entero y lo cierra."""
    app.pedir("frente")
    try:
        app.abrir_por_menu(etiqueta_menu)
    except Exception as exc:
        res.fallo(f"{titulo}: no se pudo disparar «{etiqueta_menu}», {exc}")
        return False

    dlg = app.esperar_ventana(titulo, segundos=15)
    if dlg is None:
        res.fallo(f"{titulo}: el menú no abrió ninguna ventana con ese título")
        return False
    res.nota(f"{titulo}: abre desde «{etiqueta_menu}», clase {dlg['clase']}")

    controles = app.arbol(titulo)
    revisar_nombres(controles, res, titulo)

    if esperados:
        # Se quita la marca de mnemonico: una etiqueta como "Aplicar &tamano"
        # no contiene "aplicar tamano", y eso daba fallos que no existian.
        juntos = " ".join(
            ((c.get("nombre") or "") + " " + (c.get("etiqueta") or ""))
            for c in controles).replace("&", "").lower()
        for e in esperados:
            if e.lower() not in juntos:
                res.fallo(f"{titulo}: no aparece nada llamado «{e}»")

    orden = recorrer_tab(app, res, titulo, vueltas=vueltas_tab)
    res.nota(f"{titulo}, orden de Tab, {len(orden)} paradas: "
             + " > ".join(orden[:12]))

    # `esperados` busca el texto en TODO el dialogo, asi que un rotulo o el
    # cuadro de estado pueden hacerlo pasar aunque el control no exista. Lo que
    # se pide aca tiene que estar en una parada de Tab, que es lo unico que
    # demuestra que hay un control alcanzable y con nombre.
    if esperados_en_tab:
        paradas = " ".join(orden).replace("&", "").lower()
        for e in esperados_en_tab:
            if e.lower() not in paradas:
                res.fallo(f"{titulo}: «{e}» no aparece en el orden de Tab")

    app.pedir("cerrar_ventana", ventana=titulo)
    if app.esperar_ventana(titulo, segundos=4) is not None:
        res.fallo(f"{titulo}: el diálogo no cerró")
    return True


def abrir_y_auditar(app: Aplicacion, res: Resultado, etiqueta_menu: str,
                    vueltas_tab: int = 14):
    """Dispara un ítem de menú y audita la ventana que aparezca, sea cual sea.

    No se le pide el título por adelantado a propósito: si el diálogo se
    llamara distinto de lo que uno cree, un escenario con el título escrito a
    mano diría «no abrió» y sería mentira. Ya pasó una vez hoy.
    """
    app.pedir("frente")
    antes = {v["titulo"] for v in app.ventanas()}
    try:
        app.abrir_por_menu(etiqueta_menu)
    except Exception as exc:
        res.fallo(f"«{etiqueta_menu}»: no se pudo disparar, {exc}")
        return None

    limite = time.time() + 12
    titulo = None
    while time.time() < limite:
        nuevas = {v["titulo"] for v in app.ventanas()} - antes
        if nuevas:
            titulo = sorted(nuevas)[0]
            break
        time.sleep(0.2)
    if titulo is None:
        res.nota(f"«{etiqueta_menu}»: no abre ventana, "
                 "puede ser una acción directa")
        return None

    res.nota(f"«{etiqueta_menu}» abre «{titulo}»")
    controles = app.arbol(titulo)
    revisar_nombres(controles, res, titulo)
    orden = recorrer_tab(app, res, titulo, vueltas=vueltas_tab)
    res.nota(f"{titulo}, Tab: " + " > ".join(orden[:10]))
    app.pedir("cerrar_ventana", ventana=titulo)
    if app.esperar_ventana(titulo, segundos=4) is not None:
        res.fallo(f"{titulo}: no cerró")
    return titulo


def lista_del_chat(controles):
    """La lista donde aterrizan los mensajes. Primero por nombre, si no la
    primera lista con contenido que aparezca."""
    for c in controles:
        if c["clase"] in ("ListBox", "ListCtrl") and "items" in c:
            nombre = ((c.get("nombre") or "") + (c.get("etiqueta") or "")).lower()
            if "chat" in nombre:
                return c
    for c in controles:
        if c["clase"] == "ListBox" and "items" in c:
            return c
    return None



# ── Escenarios ───────────────────────────────────────────────────────────────

def escenario_arranque_frio(app: Aplicacion, args, res: Resultado):
    """¿Responde la ventana mientras libVLC se precalienta?

    Monta una aplicación aparte y la sondea desde el instante del lanzamiento.
    Esperar primero a que la ventana conteste no sirve: en una máquina con el
    caché de plugins caliente el precalentamiento ya terminó para entonces, y
    la medición llega tarde a lo único que quería medir.

    En el registro que mandó el amigo del dueño, del 19 al 21/08/2026, el hilo
    `ReproductorWarmup` tardó 56, 92 y 128 segundos, y los tres bloqueos más
    largos de la interfaz, de 10, 40 y 53 segundos, terminaron en el mismo
    segundo en que ese hilo terminaba. `reproductor.py:381` da por hecho que
    crear la instancia cuesta uno o dos segundos.

    Acá el disco está caliente, así que el número va a salir mucho más chico.
    Lo que se mira no es el número: es si mientras ese hilo vive la ventana
    deja o no de contestar. Si deja, el mecanismo está confirmado y en la
    máquina del amigo solo escala.
    """
    aparte = Aplicacion(app.anuncios_ruta.parent / "arranque")
    t0 = time.time()
    aparte.arrancar()
    try:
        primera = None
        muestras = []          # (t, latencia, contesto, hilos)
        vio_warmup = False
        while time.time() - t0 < 150:
            antes = time.time()
            try:
                r = aparte.pedir("ping", tiempo=2.0, tolerar=True)
                contesto = bool(r.get("ok"))
            except TimeoutError:
                contesto = False
            latencia = time.time() - antes
            vivos = []
            if contesto:
                if primera is None:
                    primera = antes - t0
                try:
                    vivos = aparte.hilos()
                except Exception:
                    vivos = []
            muestras.append((antes - t0, latencia, contesto, vivos))

            if "ReproductorWarmup" in vivos:
                vio_warmup = True
            elif vio_warmup and contesto:
                break          # el precalentamiento terminó
            elif (primera is not None and not vio_warmup
                  and antes - t0 > primera + 5):
                break          # nunca lo vimos: el caché estaba caliente
            if aparte.murio_sola():
                break
            time.sleep(0.1)

        if aparte.murio_sola() and primera is None:
            res.nota("arranque: la aplicación se cerró sola, casi seguro porque "
                     "ya había otra instancia abierta; este escenario necesita "
                     "la máquina para él solo")
            return
        if primera is None:
            res.fallo("arranque: la ventana no contestó ni una vez en 150 s")
            return

        res.nota("arranque: la ventana contesta por primera vez a los %.1f s"
                 % primera)

        # Solo cuentan las muestras posteriores a la primera respuesta: antes de
        # eso «no contesta» quiere decir «todavía no existe», que no es lo mismo
        # que estar congelada.
        utiles = [m for m in muestras if m[0] >= primera]
        peor_t, peor = max(((m[0], m[1]) for m in utiles), key=lambda x: x[1])
        durante = [m for m in utiles if "ReproductorWarmup" in m[3]]

        if not vio_warmup:
            res.nota("arranque: el precalentamiento de libVLC ya había terminado "
                     "antes de la primera respuesta; con el caché de plugins "
                     "caliente no se lo puede juzgar desde acá")
        else:
            ventana = durante[-1][0] - durante[0][0] if len(durante) > 1 else 0.0
            peor_dentro = max((m[1] for m in durante), default=0.0)
            res.nota("arranque: ReproductorWarmup vivo durante %.1f s, y la peor "
                     "respuesta mientras tanto fue de %.1f s"
                     % (ventana, peor_dentro))
            if peor_dentro > 2.0:
                res.fallo("arranque: la ventana estuvo %.1f s sin responder "
                          "mientras libVLC se precalentaba" % peor_dentro)

        res.nota("arranque: %d sondeos, peor respuesta %.1f s a los %.1f s"
                 % (len(utiles), peor, peor_t))
        if peor > 2.0 and not vio_warmup:
            res.fallo("arranque: la ventana estuvo %.1f s sin responder" % peor)
    finally:
        aparte.cerrar()


# Cuánto puede tardar una acción del reproductor antes de que se note. Medio
# segundo no lo percibe nadie; a partir de uno la ventana ya "va dura", y por
# encima de dos, sin ver la pantalla, no se sabe si la tecla entró.
BLOQUEO_SOSPECHOSO = 1.0
BLOQUEO_INACEPTABLE = 2.0
# Y cuánto puede tardar en hablar. Un anuncio que llega tarde es peor que uno
# que no llega: para entonces la persona ya pulsó otra cosa.
VOZ_LENTA = 1.5


def medir_accion(app: Aplicacion, hacer, espera: float = 3.0):
    """Hace algo y mide las dos cosas que producen «torpeza».

    La primera es cuánto tarda la ventana en volver a atender a nadie. Como la
    sonda despacha con `wx.CallAfter`, un `ping` que vuelve es la prueba de que
    el hilo de interfaz está libre otra vez; lo que tarde en volver es tiempo
    en el que la aplicación no responde a una tecla.

    La segunda es cuánto tarda en decir algo. Devuelve
    `(bloqueo, latencia_de_voz, lo_que_dijo)`, con la latencia en `None` si no
    llegó a hablar.
    """
    # Esperar a que la aplicación se calle ANTES de actuar. Si no, el primer
    # anuncio que llegue se le atribuye a la acción, y con una carga en vuelo
    # eso mide la red y no el control. El 21/08/2026 esto produjo tres fallos
    # contra un directo real que en la corrida siguiente no aparecieron.
    quieto = time.time() + 8
    ultimo = len(app.anuncios)
    calma = time.time() + 0.6
    while time.time() < quieto and time.time() < calma:
        if len(app.anuncios) != ultimo:
            ultimo = len(app.anuncios)
            calma = time.time() + 0.6
        time.sleep(0.05)

    antes = len(app.anuncios)
    t0 = time.time()
    hacer()
    app.pedir("ping", tiempo=120)
    bloqueo = time.time() - t0

    latencia = None
    limite = time.time() + espera
    while time.time() < limite:
        if any(a["canal"] == "voz" for a in app.anuncios[antes:]):
            latencia = time.time() - t0
            break
        time.sleep(0.05)
    dichos = [a["texto"] for a in app.anuncios[antes:] if a["canal"] == "voz"]
    return bloqueo, latencia, dichos


def juzgar_accion(res: Resultado, donde: str, que: str, medida) -> bool:
    """Convierte una medida en veredicto. Devuelve si habló."""
    bloqueo, latencia, dichos = medida
    if not dichos:
        res.fallo(f"{donde}: {que} no dice nada")
        hablo = False
    else:
        hablo = True
        detalle = dichos[0][:58]
        if latencia is not None and latencia > VOZ_LENTA:
            res.fallo(f"{donde}: {que} tarda {latencia:.1f} s en decir "
                      f"«{detalle}»")
        else:
            res.nota(f"{donde}: {que} dice «{detalle}»"
                     + (f", a los {latencia:.2f} s" if latencia else ""))

    if bloqueo > BLOQUEO_INACEPTABLE:
        res.fallo(f"{donde}: {que} deja la ventana {bloqueo:.1f} s sin responder")
    elif bloqueo > BLOQUEO_SOSPECHOSO:
        res.nota(f"{donde}: ojo, {que} tarda {bloqueo:.1f} s en devolver la "
                 f"ventana")
    return hablo


# Los seis botones de transporte, por la etiqueta con la que se los encuentra.
BOTONES_REPRODUCTOR = (
    ("Reproducir", "el botón de reproducir"),
    ("Retroceder 1 min", "el botón de retroceder"),
    ("Avanzar 1 min", "el botón de avanzar"),
    ("Detener", "el botón de detener"),
    ("Silenciar audio", "el botón de silenciar"),
    ("Pantalla completa", "el botón de pantalla completa"),
)

# Y los atajos, que son el camino que de verdad usa quien no ve la pantalla:
# `AGENTS.md` cuenta que los botones vienen ocultos justamente porque se maneja
# por teclado. Son los de `config.ATAJOS_DEFAULTS`, área Ctrl.
ATAJOS_REPRODUCTOR = (
    (("p", ["ctrl"]), "Ctrl+P, reproducir o pausa"),
    (("left", ["ctrl"]), "Ctrl+Izquierda, retroceder"),
    (("right", ["ctrl"]), "Ctrl+Derecha, avanzar"),
    (("m", ["ctrl"]), "Ctrl+M, silenciar"),
    (("up", ["ctrl"]), "Ctrl+Arriba, subir volumen"),
    (("down", ["ctrl"]), "Ctrl+Abajo, bajar volumen"),
    (("d", ["ctrl"]), "Ctrl+D, detener"),
)


def bateria_reproductor(app: Aplicacion, res: Resultado, donde: str) -> None:
    """Maltrata el reproductor entero y mide cada golpe.

    Se usa dos veces: sin nada cargado, que es como arranca la aplicación, y
    contra un directo de verdad desde `escenario_directo_youtube`. Las dos
    situaciones tienen que hablar; la segunda además tiene que ser rápida.
    """
    # ── los seis botones ────────────────────────────────────────────────────
    for etiqueta, quien in BOTONES_REPRODUCTOR:
        medida = medir_accion(app, lambda e=etiqueta: app.pedir("pulsar", nombre=e))
        juzgar_accion(res, donde, quien, medida)

        # Pantalla completa abre una ventana nueva que se queda con el foco y
        # con el teclado. Hay que volver, o todo lo que se mida después se mide
        # sobre la ventana equivocada.
        if etiqueta == "Pantalla completa":
            ctrl = app.foco() or {}
            nombre = (ctrl.get("nombre") or ctrl.get("etiqueta") or "").strip()
            if not nombre:
                res.fallo(f"{donde}: en pantalla completa el foco queda en un "
                          f"control sin nombre ({ctrl.get('clase')})")
            else:
                res.nota(f"{donde}: en pantalla completa el foco va a «{nombre}»")
            medida = medir_accion(
                app, lambda e=etiqueta: app.pedir("pulsar", nombre=e))
            juzgar_accion(res, donde, "salir de pantalla completa", medida)
            ctrl = app.foco() or {}
            nombre = (ctrl.get("nombre") or ctrl.get("etiqueta") or "").strip()
            if not nombre:
                res.fallo(f"{donde}: al salir de pantalla completa el foco "
                          f"queda en el aire ({ctrl.get('clase')})")
            else:
                res.nota(f"{donde}: al salir, el foco vuelve a «{nombre}»")

    # ── dos pulsaciones seguidas, que es lo que hace cualquiera cuando la
    #    primera no contestó ─────────────────────────────────────────────────
    antes = len(app.anuncios)
    app.pedir("pulsar", nombre="Reproducir")
    medida = medir_accion(app, lambda: app.pedir("pulsar", nombre="Reproducir"))
    if not medida[2]:
        res.fallo(f"{donde}: pulsar reproducir dos veces seguidas deja la "
                  f"segunda muda")
    else:
        res.nota(f"{donde}: la segunda pulsación de reproducir también habla")
    del antes

    # ── los siete atajos ────────────────────────────────────────────────────
    # Antes de juzgar los atajos hay que saber si el menú que los sostiene está
    # encendido. `gui.py:1769` apaga el menú Reproductor entero mientras no hay
    # conexión (`mb.EnableTop`), y un menú apagado se lleva por delante a sus
    # siete aceleradores aunque cada ítem se declare habilitado. Sin esto, el
    # banco daba siete atajos por rotos cuando lo que pasaba es que estaban
    # apagados a propósito.
    menu_vivo = None
    for m in app.menus():
        if m["camino"].strip().lower() == "reproductor":
            menu_vivo = bool(m.get("habilitado"))
            break
    if menu_vivo is False:
        res.nota(f"{donde}: el menú Reproductor está apagado, así que sus siete "
                 f"atajos no pueden funcionar")
        # Y ahí está lo que sí es un defecto: los botones de la ventana siguen
        # encendidos y respondiendo. Dos caminos para lo mismo, uno vivo y otro
        # muerto, sin que nada se lo diga a quien no ve la pantalla.
        encendidos = [c.get("etiqueta") or c.get("nombre")
                      for c in app.arbol()
                      if c.get("clase") in ("Button", "BitmapButton")
                      and c.get("habilitado") and c.get("en_pantalla")
                      and (c.get("etiqueta") or "") in
                      [e for e, _ in BOTONES_REPRODUCTOR]]
        if encendidos:
            res.fallo(f"{donde}: con el menú Reproductor apagado, sus atajos no "
                      f"hacen nada pero estos botones siguen encendidos y "
                      f"funcionando: " + ", ".join(encendidos))

    # Los aceleradores solo llegan si el foco está DENTRO de un control, no en
    # el frame. Se ancla a propósito para que el resultado no dependa de dónde
    # lo haya dejado la comprobación anterior.
    for candidato in ("Volumen del reproductor", "URL", "Chat en vivo"):
        try:
            app.pedir("foco", nombre=candidato)
            break
        except OrdenRechazada:
            continue

    for combo, quien in ATAJOS_REPRODUCTOR:
        try:
            medida = medir_accion(app, lambda c=combo: app.teclas(c))
        except VentanaNoActiva as exc:
            res.nota(f"{donde}: no se pudo probar {quien}, {exc}")
            continue
        if menu_vivo is False:
            if medida[2]:
                res.nota(f"{donde}: {quien} habla aun con el menú apagado")
            continue
        juzgar_accion(res, donde, quien, medida)

    # ── los dos deslizadores, con las flechas ───────────────────────────────
    for nombre_ctrl, teclas, quien in (
            ("Posición de reproducción", ("right", "left"), "la posición"),
            ("Volumen del reproductor", ("up", "down"), "el volumen")):
        try:
            app.pedir("foco", nombre=nombre_ctrl)
        except OrdenRechazada as exc:
            res.fallo(f"{donde}: no se llega a {quien}, {exc}")
            continue
        for tecla in teclas:
            try:
                medida = medir_accion(app, lambda t=tecla: app.teclas(t))
            except VentanaNoActiva as exc:
                res.nota(f"{donde}: no se pudo probar {quien}, {exc}")
                break
            juzgar_accion(res, donde, f"{quien} con la flecha {tecla}", medida)


def escenario_reproductor(app: Aplicacion, args, res: Resultado):
    """El reproductor sin nada cargado, que es como arranca la aplicación.

    Nunca lo probó nadie: `reproductor.py` son 1.059 líneas con cinco pruebas,
    y las cinco son del parser de atajos. El recorrido de Tab lo pasaba de largo
    porque los seis botones vienen ocultos de fábrica.

    Va primero de todos los escenarios y no es capricho: en cuanto `chat` o
    `tiktok` simulan una sesión, el estado «sin nada cargado» no vuelve sin
    reiniciar, y el botón de reproducir pasa la comprobación por el motivo
    equivocado.

    La regla que se comprueba no admite matices: un control que se activa y no
    dice nada es indistinguible, para quien no ve la pantalla, de una
    aplicación colgada. Y uno que tarda dos segundos en contestar, también.
    """
    if not app.al_frente():
        res.nota("reproductor: Windows no puso la ventana al frente")

    # Sin python-vlc el panel no se construye: en su lugar va un aviso de una
    # línea. Juzgar los botones ahí daría seis fallos de accesibilidad que en
    # realidad son una dependencia que falta.
    todo = " ".join(((c.get("etiqueta") or "") + " " + (c.get("nombre") or ""))
                    for c in app.arbol())
    if "AvisoReproductor" in todo or "no disponible" in todo.lower():
        res.nota("reproductor: no hay panel; falta VLC o yt-dlp en este "
                 "entorno, así que no se juzga nada. Correlo con el intérprete "
                 "del proyecto, .venv/Scripts/python.exe")
        return

    # Los botones vienen ocultos («minimalista»), y ocultos wx los saca del
    # recorrido de Tab. Hay que mostrarlos para poder probarlos como los prueba
    # una persona. Se anota cómo estaban para dejarlo igual al terminar.
    # Se pregunta por la etiqueta del propio interruptor, que dice «Ocultar…»
    # cuando están visibles y «Mostrar…» cuando no. Mirar `en_pantalla` de los
    # botones no sirve: `IsShownOnScreen` da falso también cuando la ventana
    # está tapada o minimizada, y entonces el banco creía que estaban ocultos,
    # los ocultaba, y encima le dejaba la preferencia cambiada al dueño.
    estaban_visibles = any(
        (c.get("etiqueta") or "").lower().startswith("ocultar botones")
        for c in app.arbol())
    if not estaban_visibles:
        medida = medir_accion(
            app, lambda: app.pedir("pulsar", nombre="AlternarBotonesReproductor"))
        juzgar_accion(res, "reproductor", "mostrar los botones", medida)

    faltan = []
    visibles = " ".join(((c.get("etiqueta") or "") + " " + (c.get("nombre") or ""))
                        for c in app.arbol()).lower()
    for etiqueta, quien in BOTONES_REPRODUCTOR:
        if etiqueta.lower() not in visibles:
            faltan.append(quien)
    if faltan:
        res.fallo("reproductor: no aparecen " + ", ".join(faltan))
        return

    bateria_reproductor(app, res, "reproductor")

    orden = recorrer_tab(app, res, "reproductor", vueltas=12)
    res.nota("reproductor, orden de Tab, %d paradas: %s"
             % (len(orden), " > ".join(orden)))

    # Dejarlo como estaba: el banco no puede cambiarle la ventana al dueño. La
    # visibilidad de los botones se guarda en `config.ini`, así que sin esto
    # cada corrida le deja la aplicación distinta de como la encontró.
    if not estaban_visibles:
        app.pedir("pulsar", nombre="AlternarBotonesReproductor")


def escenario_principal(app: Aplicacion, args, res: Resultado):
    """La ventana con la que se encuentra alguien al abrir la aplicación."""
    app.pedir("frente")
    revisar_nombres(app.arbol(), res, "ventana principal")
    # Tab desde el frame no recorre nada: hay que empezar dentro, en un
    # control de verdad. En los diálogos no hace falta porque wx ya le da el
    # foco al primero al abrirlos.
    try:
        app.pedir("foco", nombre="URL")
    except Exception as exc:
        res.fallo(f"ventana principal: no pude enfocar el campo de URL, {exc}")
    orden = recorrer_tab(app, res, "ventana principal", vueltas=12)
    res.nota(f"orden de Tab, {len(orden)} paradas: " + " > ".join(orden))

    n = len(app.anuncios)
    app.teclas(("f2",))
    if app.esperar_dicho("desconectado", segundos=8, desde=n):
        res.nota("F2 anuncia el estado")
    else:
        res.fallo("F2 no anunció nada en 8 segundos")


def escenario_descargas(app: Aplicacion, args, res: Resultado):
    """El gestor de descargas, que entró al repositorio sin que nadie lo abra."""
    app.pedir("frente")
    # El foco tiene que estar DENTRO de un control, no en el frame, o el
    # acelerador no llega. Sin esto el escenario pasaba o fallaba segun que
    # otro escenario se hubiera corrido antes, que es la peor clase de prueba.
    try:    app.pedir("foco", nombre="URL")
    except Exception: pass
    app.teclas(("s", ["ctrl"]))
    dlg = app.esperar_ventana("Gestor de descargas", segundos=12)
    if dlg is None:
        res.fallo("Ctrl+S no abrió el gestor de descargas")
        return
    res.nota(f"Ctrl+S abre «{dlg['titulo']}», clase {dlg['clase']}")

    controles = app.arbol("Gestor de descargas")
    revisar_nombres(controles, res, "descargas")

    juntos = " ".join(
        ((c.get("nombre") or "") + " " + (c.get("etiqueta") or ""))
        for c in controles).lower()
    for esperado in ("formato", "bitrate", "carpeta", "cola", "cerrar"):
        if esperado not in juntos:
            res.fallo(f"descargas: no aparece nada llamado «{esperado}»")

    orden = recorrer_tab(app, res, "descargas", vueltas=14)
    res.nota(f"descargas, orden de Tab, {len(orden)} paradas: "
             + " > ".join(orden))

    app.pedir("cerrar_ventana", ventana="Gestor de descargas")
    if app.esperar_ventana("Gestor de descargas", segundos=3) is None:
        res.nota("descargas: el diálogo cierra")
    else:
        res.fallo("descargas: el diálogo no cerró")


def escenario_diagnostico(app: Aplicacion, args, res: Resultado):
    """¿El diagnóstico se está anunciando por voz? No debería.

    Es la regresión que reportó el dueño: cada 30 segundos el lector le lee el
    censo de hilos, y cuando salta el vigilante de bloqueo, una traza entera.
    El censo va cada `INTERVALO_CENSO_HILOS_S`, que son 30, así que hay que
    escuchar más que eso o la prueba no puede fallar.
    """
    res.nota("escuchando 35 segundos, más que el intervalo del censo")
    fin = time.time() + 35
    while time.time() < fin:
        time.sleep(1.0)

    marcas = ("HILOS vivos", "HILO inicia", "HILO termina",
              "INTERFAZ bloqueada", "ENTORNO")
    fugas = [a for a in app.anuncios
             if a["canal"] in ("voz", "braille")
             and any(m in a["texto"] for m in marcas)]
    if fugas:
        res.fallo(f"el diagnóstico se anuncia por voz: {len(fugas)} veces")
        for a in fugas[:3]:
            res.fallo(f"  se dijo: {a['texto'][:70]}")
    else:
        res.nota("el diagnóstico no se anuncia por voz")




def escenario_menus(app: Aplicacion, args, res: Resultado):
    """Todos los ítems de menú: que tengan texto, atajo anunciable y estado."""
    items = app.menus()
    if not items:
        res.fallo("no se pudo leer la barra de menú")
        return
    hojas = [i for i in items if not i.get("submenu")]
    res.nota(f"{len(items)} entradas de menú, {len(hojas)} accionables")

    sin_texto = [i for i in items if not i["etiqueta"].strip()]
    for i in sin_texto:
        res.fallo(f"menú: una entrada sin texto en «{i['camino']}»")

    # Un ítem que promete atajo y otro que hace lo mismo sin prometerlo es una
    # inconsistencia que el usuario paga aprendiendo dos veces.
    con_atajo = [i for i in hojas if i["acelerador"]]
    res.nota(f"{len(con_atajo)} ítems anuncian atajo en su etiqueta")

    repetidos: dict[str, list[str]] = {}
    for i in con_atajo:
        repetidos.setdefault(i["acelerador"].lower(), []).append(i["camino"])
    for atajo, donde in repetidos.items():
        if len(donde) > 1:
            res.fallo(f"menú: el atajo {atajo} está en {len(donde)} sitios: "
                      + ", ".join(donde))

    apagados = [i["camino"] for i in hojas if not i["habilitado"]]
    res.nota(f"sin conexión hay {len(apagados)} ítems deshabilitados")
    if apagados:
        res.nota("  " + ", ".join(apagados[:8]))


def escenario_preferencias(app: Aplicacion, args, res: Resultado):
    """Preferencias, donde `AGENTS.md` y el código no dicen lo mismo.

    El contrato afirma que el diálogo va sin paleta, porque colorear una
    casilla en Windows la convierte en botón owner-drawn y NVDA la lee como
    botón y sin estado. El código colorea nueve casillas y un radio. Acá se
    mira qué rol expone Windows de verdad, que es lo que zanja la discusión.
    """
    app.pedir("frente")
    try:
        app.abrir_por_menu("Preferencias")
    except Exception as exc:
        res.fallo(f"preferencias: no se pudo abrir, {exc}")
        return
    dlg = app.esperar_ventana("Preferencias", segundos=15)
    if dlg is None:
        res.fallo("preferencias: no abrió")
        return
    res.nota(f"preferencias: abre, clase {dlg['clase']}")

    controles = app.arbol("Preferencias")
    revisar_nombres(controles, res, "preferencias")

    # Solo lo que está en pantalla: el resto vive en pestañas no seleccionadas
    # y Windows no lo expone, así que compararlo daría una diferencia falsa.
    casillas_wx = [c for c in controles
                   if c["clase"] == "CheckBox" and c.get("en_pantalla")]
    radios_wx = [c for c in controles
                 if c["clase"] in ("RadioButton", "RadioBox")
                 and c.get("en_pantalla")]
    res.nota(f"preferencias, pestaña visible: wx dice {len(casillas_wx)} "
             f"casillas y {len(radios_wx)} radios")

    roles = roles_segun_windows("Preferencias")
    if not roles:
        res.nota("preferencias: no se pudo leer el árbol de Windows, se salta "
                 "la comprobación de owner-drawn")
    else:
        vistos_casilla = roles.get("CheckBox", 0)
        vistos_radio = roles.get("RadioButton", 0)
        res.nota(f"preferencias: Windows expone {vistos_casilla} CheckBox y "
                 f"{vistos_radio} RadioButton")
        if casillas_wx and vistos_casilla < len(casillas_wx):
            res.fallo(
                "preferencias: wx creó %d casillas y Windows solo expone %d "
                "como CheckBox. Las que faltan se anuncian con otro rol, que "
                "es lo que avisa AGENTS.md sobre el color."
                % (len(casillas_wx), vistos_casilla))

    orden = recorrer_tab(app, res, "preferencias", vueltas=20)
    res.nota(f"preferencias, orden de Tab, {len(orden)} paradas: "
             + " > ".join(orden[:10]))

    # Y ahora el resto de las pestanas, una por una. Auditar solo la visible
    # dejaba fuera la pagina de atajos entera, que son veinte botones.
    try:
        respuesta = app.pedir("pestanas", ventana="Preferencias")
    except Exception as exc:
        res.nota(f"preferencias: no se pudieron listar las pestañas, {exc}")
        respuesta = {}
    if not respuesta.get("ok"):
        if respuesta:
            res.nota("preferencias: no se pudieron listar las pestañas, "
                     + str(respuesta.get("error", "sin motivo")))
        info = None
    else:
        info = respuesta.get("datos", {})
    if info:
        paginas = info.get("paginas", [])
        res.nota(f"preferencias: {len(paginas)} pestañas: "
                 + ", ".join(paginas))
        for i, nombre in enumerate(paginas):
            app.pedir("pestanas", ventana="Preferencias", indice=i)
            visibles = [c for c in app.arbol("Preferencias")
                        if c.get("en_pantalla")]
            revisar_nombres(visibles, res, f"preferencias/{nombre}")
            casillas = [c for c in visibles if c["clase"] == "CheckBox"]
            # Ojo con la diferencia, que ya produjo una alarma falsa el
            # 21/08/2026: `wx.RadioBox` es un CONTENEDOR, un solo control para
            # wx, y Windows expone sus opciones como varios RadioButton
            # sueltos. Compararlos juntos da siempre un desajuste inventado.
            radios = [c for c in visibles if c["clase"] == "RadioButton"]
            cajas_radio = [c for c in visibles if c["clase"] == "RadioBox"]
            # Sincronizar con un hecho, no con un reloj. Windows redibuja la
            # pestana nueva cuando le parece, y un `sleep` fijo daba dos
            # recuentos distintos en dos corridas seguidas: el 21/08/2026 eso
            # produjo una alarma que no era tal. Se espera a que el arbol de
            # accesibilidad muestre algo de ESTA pagina antes de contar nada.
            testigo = ""
            for c in visibles:
                texto = (c.get("etiqueta") or c.get("nombre") or "")
                texto = texto.replace("&", "").strip()
                if len(texto) > 6:
                    testigo = texto.lower()
                    break
            roles = {}
            limite_pag = time.time() + 10
            while time.time() < limite_pag:
                roles = roles_segun_windows("Preferencias")
                if not testigo:
                    break
                todos = [n.replace("&", "").strip().lower()
                         for lista in _ULTIMOS_NOMBRES.values() for n in lista]
                if any(testigo in n or n in testigo for n in todos if n):
                    break
                time.sleep(0.4)
            else:
                res.nota(f"preferencias/{nombre}: Windows no llegó a mostrar "
                         f"«{testigo[:40]}», no se juzgan los roles")
                roles = {}

            if roles and casillas and roles.get("CheckBox", 0) < len(casillas):
                res.fallo(
                    "preferencias/%s: wx creó %d casillas y Windows solo "
                    "expone %d como CheckBox"
                    % (nombre, len(casillas), roles.get("CheckBox", 0)))
            if roles and cajas_radio:
                sueltos = roles.get("RadioButton", 0) - len(radios)
                if sueltos <= 0:
                    # Nota y no fallo, a propósito. Esta misma cuenta dio la
                    # alarma del 21/08/2026 y el dueño la desmintió probándolo
                    # con NVDA: se lee bien. La medición depende de cuándo
                    # Windows termine de redibujar la pestaña, así que da
                    # números distintos en corridas seguidas. Mientras no se
                    # sepa medirla estable, no puede acusar a nadie.
                    res.nota(
                        "preferencias/%s: %d agrupación(es) de radios y Windows "
                        "no expone ninguna opción como RadioButton; la medida "
                        "es inestable y ya se desmintió con NVDA, así que no "
                        "cuenta como fallo" % (nombre, len(cajas_radio)))
                else:
                    res.nota(
                        "preferencias/%s: %d agrupación(es) de radios, y "
                        "Windows expone %d opciones como RadioButton pese al "
                        "color" % (nombre, len(cajas_radio), sueltos))
            if roles and radios and roles.get("RadioButton", 0) < len(radios):
                vistos = {n.replace("&", "").strip().lower()
                          for n in nombres_segun_windows("RadioButton")}
                ausentes = [
                    (c.get("etiqueta") or c.get("nombre") or "?").replace("&", "")
                    for c in radios
                    if (c.get("etiqueta") or c.get("nombre") or ""
                        ).replace("&", "").strip().lower() not in vistos]
                res.fallo(
                    "preferencias/%s: wx creó %d radios y Windows solo expone "
                    "%d como RadioButton. No aparece: %s"
                    % (nombre, len(radios), roles.get("RadioButton", 0),
                       ", ".join(ausentes) or "no se pudo emparejar por nombre"))
                for rol_otro in ("Button", "Group", "Custom", "Pane", "Text"):
                    for n in nombres_segun_windows(rol_otro):
                        if n and any(n.replace("&", "").strip().lower()
                                     == a.strip().lower() for a in ausentes):
                            res.nota("  Windows lo expone como %s" % rol_otro)

    app.pedir("cerrar_ventana", ventana="Preferencias")


def escenario_historial(app: Aplicacion, args, res: Resultado):
    """El historial de directos vistos."""
    auditar_dialogo(app, res, "Historial de directos", "Historial de directos",
                    vueltas_tab=12)


def escenario_transmision(app: Aplicacion, args, res: Resultado):
    """El diálogo que coloca el panel de chat dentro de una escena de OBS.

    Vale con OBS abierto y sin OBS. Sin él, el diálogo tiene que abrirse
    IGUAL, decir en su cuadro de estado por qué no puede hacer nada, y que sus
    controles se sigan anunciando: uno que se rinde y no abre deja a quien no
    ve sin saber qué pasó. Con OBS abierto se audita además con todos los
    controles habilitados, que es cuando el orden de Tab es completo.

    La fase 3 del smoke NO llega hasta acá: solo audita la pantalla
    desconectada. Esta es la única auditoría automática de esta superficie.
    """
    auditar_dialogo(
        app, res, "Transmisión", "Transmisión", vueltas_tab=20,
        esperados=("Estado de la transmisión", "Actualizar estado", "Escena",
                   "Fuente",
                   "Posición del panel", "Ancho del panel", "Alto del panel",
                   "Aplicar tamaño", "Mostrar el panel", "Fijar el panel",
                   "Poner al frente", "Ajuste fino", "captura", "lienzo",
                   "Restablecer",
                   "Cerrar"),
        esperados_en_tab=("Fuente", "Escena", "Posición del panel"))


def escenario_ayuda(app: Aplicacion, args, res: Resultado):
    """El menú Ayuda, que abre ventanas de texto largo."""
    items = [i for i in app.menus()
             if not i.get("submenu") and i["camino"].startswith("Ayuda")]
    if not items:
        res.fallo("ayuda: el menú no tiene entradas accionables")
        return
    res.nota(f"ayuda: {len(items)} entradas: "
             + ", ".join(i["etiqueta"] for i in items))
    for i in items:
        if not i["habilitado"]:
            res.fallo(f"ayuda: «{i['etiqueta']}» está deshabilitado sin motivo")




def escenario_chat(app: Aplicacion, args, res: Resultado):
    """Una sesión de YouTube con mensajes, sin tocar la red.

    Se monta con la misma API pública que usa `main.py` desde el hilo de
    captura. Así se prueba la parte conectada de la interfaz sin depender de
    que haya un directo vivo ni de que la red se porte bien.
    """
    app.pedir("frente")

    # Este escenario mide el PASO de desconectado a conectado, asi que si llega
    # con la aplicacion ya conectada no falla por un defecto suyo: falla porque
    # otro escenario dejo puesta una sesion simulada. Se dice asi, con el
    # nombre del culpable a la vista, porque el 26/08/2026 el mismo fallo se
    # leyo como «conectar no anuncia nada» y se busco durante un rato en el
    # sitio equivocado.
    conectado_ya = any(
        i["habilitado"] for i in app.menus()
        if not i.get("submenu")
        and "desconectar" in (i.get("camino") or "").lower())
    if conectado_ya:
        res.fallo("chat: llegue con la aplicacion YA conectada. No es un "
                  "defecto de la aplicacion: algun escenario anterior simulo "
                  "una sesion y no llamo a `restaurar_desconectado`")
        return

    apagados_antes = len([i for i in app.menus()
                          if not i.get("submenu") and not i["habilitado"]])

    n = len(app.anuncios)
    app.simular_sesion_youtube(titulo="Directo de prueba QA", espectadores=137)
    if app.esperar_dicho("conectado", segundos=10, desde=n):
        res.nota("chat: conectar se anuncia")
    else:
        res.fallo("chat: conectar no anunció nada")

    apagados = [i["camino"] for i in app.menus()
                if not i.get("submenu") and not i["habilitado"]]
    res.nota(f"al conectar, los ítems apagados bajan de {apagados_antes} "
             f"a {len(apagados)}")
    if len(apagados) >= apagados_antes:
        res.fallo("chat: conectar no habilitó ningún ítem de menú")
    if apagados:
        res.nota("  siguen apagados: " + ", ".join(apagados))

    muestras = [
        ("Ana", "hola que tal el directo", "text", ""),
        ("Beto", "gracias por todo", "superchat", "5,00 US$"),
        ("Cora", "me hice miembro", "member", ""),
        ("Dani", "un sticker", "sticker", "2,00 US$"),
    ]
    for autor, texto, tipo, monto in muestras:
        app.mensaje(autor, texto, tipo=tipo, monto=monto)

    # El chat se vuelca agrupado, así que se espera a que aparezca en la lista
    # en vez de dar por hecho que ya está.
    limite = time.time() + 12
    lista = None
    while time.time() < limite:
        lista = lista_del_chat(app.arbol())
        if lista and len(lista.get("items", [])) >= len(muestras):
            break
        time.sleep(0.3)

    if not lista:
        res.fallo("chat: no encontré la lista del chat")
        return
    items = lista.get("items", [])
    res.nota(f"chat: la lista tiene {len(items)} entradas tras enviar "
             f"{len(muestras)}")
    if len(items) < len(muestras):
        res.fallo(f"chat: se enviaron {len(muestras)} mensajes y llegaron "
                  f"{len(items)}")
    texto_junto = " ".join(str(i) for i in items).lower()
    for autor, _, _, _ in muestras:
        if autor.lower() not in texto_junto:
            res.fallo(f"chat: «{autor}» no aparece en la lista")
    for entrada in items[:4]:
        res.nota("  lee: " + str(entrada)[:70])

    # El monto del super chat tiene que verse: es el motivo de la función.
    if "5,00" not in texto_junto and "5.00" not in texto_junto:
        res.fallo("chat: el monto del super chat no aparece en la lista")

    orden = recorrer_tab(app, res, "principal conectada", vueltas=16)
    res.nota(f"conectado, Tab da {len(orden)} paradas: "
             + " > ".join(orden[:10]))


def escenario_tiktok(app: Aplicacion, args, res: Resultado):
    """La ruta de TikTok, que es distinta y comparte la misma lista."""
    app.pedir("frente")
    n = len(app.anuncios)
    app.simular_sesion_tiktok(usuario="rolon_100")
    if not app.esperar_dicho("conectado", segundos=10, desde=n):
        res.nota("tiktok: no anunció «conectado», puede usar otra frase")

    for autor, texto, tipo in (("Eva", "hola desde tiktok", "text"),
                               ("Fito", "entra al directo", "entrada")):
        app.mensaje(autor, texto, tipo=tipo)

    limite = time.time() + 12
    lista = None
    while time.time() < limite:
        lista = lista_del_chat(app.arbol())
        if lista and lista.get("items"):
            break
        time.sleep(0.3)
    if not lista or not lista.get("items"):
        res.fallo("tiktok: no llegó ningún mensaje a la lista")
        return
    res.nota(f"tiktok: {len(lista.get('items'))} entradas en la lista")

    # «Descargar este vídeo» va apagado en TikTok, por diseño.
    item = [i for i in app.menus() if "Descargar este" in i["camino"]]
    if item and item[0]["habilitado"]:
        res.fallo("tiktok: «Descargar este vídeo» quedó habilitado, y el "
                  "diseño dice que en TikTok va apagado")
    elif item:
        res.nota("tiktok: «Descargar este vídeo» correctamente apagado")


def escenario_comentarios(app: Aplicacion, args, res: Resultado):
    """El panel de comentarios, que hasta el 26/08/2026 no entraba en el banco.

    Va sin red a propósito: traer comentarios de verdad necesita clave de API y
    sesión iniciada, y eso ya lo cubren las pruebas de `youtube_api`. Lo que
    solo se puede comprobar con la aplicación viva es otra cosa: que los
    controles tengan nombre, que Tab los alcance, y que la lista diga algo
    cuando se pulsa sobre nada.
    """
    app.pedir("frente")

    respuesta = app.pedir("pestanas")
    if not respuesta.get("ok"):
        res.fallo("comentarios: no se pudieron listar las pestañas, "
                  + str(respuesta.get("error", "sin motivo")))
        return
    paginas = respuesta.get("datos", {}).get("paginas", [])
    if "Comentarios" not in paginas:
        res.fallo("comentarios: no hay ninguna pestaña «Comentarios»; hay "
                  + ", ".join(paginas))
        return
    pagina = paginas.index("Comentarios")
    app.pedir("pestanas", indice=pagina)

    visibles = _panel_comentarios(app)
    revisar_nombres(visibles, res, "comentarios")

    lista = _lista_de_comentarios(visibles)
    if lista is None:
        res.fallo("comentarios: no encontré la lista del panel")
        return
    res.nota("comentarios: la lista arranca con %d entradas"
             % len(lista.get("items", [])))

    # «Cargar más» sin ninguna página cargada tiene que estar apagado: si
    # figura encendido, invita a pulsar algo que no puede hacer nada.
    botones = {(c.get("etiqueta") or "").replace("&", ""): c
               for c in visibles if c["clase"] == "Button"}
    mas = botones.get("Cargar más")
    if mas is None:
        res.fallo("comentarios: no está el botón «Cargar más»")
    elif mas["habilitado"]:
        res.fallo("comentarios: «Cargar más» está habilitado sin ninguna "
                  "página cargada")
    else:
        res.nota("comentarios: «Cargar más» correctamente apagado al empezar")

    # Este otro depende de que haya sesión iniciada, que no está en manos del
    # banco. Se anota lo que se encontró, sin juzgarlo.
    comentar = botones.get("Comentar en el vídeo")
    if comentar is None:
        res.fallo("comentarios: no está el botón «Comentar en el vídeo»")
    else:
        res.nota("comentarios: «Comentar en el vídeo» "
                 + ("habilitado, hay sesión" if comentar["habilitado"]
                    else "apagado, no hay sesión iniciada"))

    # Tab hay que empezarlo DENTRO de la pagina: desde el marco no recorre
    # nada, igual que en la ventana principal.
    app.pedir("foco", nombre="Lista de comentarios")
    orden = recorrer_tab(app, res, "comentarios", vueltas=12)
    res.nota("comentarios, orden de Tab, %d paradas: %s"
             % (len(orden), " > ".join(orden[:10])))

    # Enter sobre la lista vacía tiene que decir algo. Callarse es lo peor que
    # puede hacer: quien no ve la pantalla no sabe si la tecla llegó.
    app.pedir("foco", nombre="Lista de comentarios")
    n = len(app.anuncios)
    app.teclas("return")
    if app.esperar_dicho("sin comentario", segundos=5, desde=n):
        res.nota("comentarios: Enter sin selección avisa en vez de callarse")
    else:
        res.fallo("comentarios: Enter sobre la lista vacía no anunció nada")

    # El aviso de TikTok es la única entrada que el panel muestra sin red, y
    # existe para que la pestaña vacía no parezca una avería. Esto deja la
    # aplicación en sesión de TikTok, así que el escenario va justo antes de
    # `tiktok` en la corrida completa.
    app.simular_sesion_tiktok()
    app.pedir("pestanas", indice=pagina)
    items = []
    limite = time.time() + 8
    while time.time() < limite:
        actual = _lista_de_comentarios(subarbol(app.arbol(), "PanelComentarios"))
        items = actual.get("items", []) if actual else []
        if items:
            break
        time.sleep(0.3)
    if any("tiktok" in i.lower() for i in items):
        res.nota("comentarios: en TikTok la lista explica por qué está vacía")
    else:
        res.fallo("comentarios: en TikTok la lista no explica por qué está "
                  "vacía; dice %r" % (items,))


def subarbol(controles: list[dict], nombre: str) -> list[dict]:
    """Los controles que cuelgan del panel con ese nombre, el panel incluido.

    Hace falta porque en el marco principal NINGUNA de las dos banderas de
    visibilidad acota una pagina del cuaderno, medido el 26/08/2026: wx deja
    `IsShown` en True para las paginas que no estan al frente, asi que
    `visible` las incluye a todas, y `IsShownOnScreen` da False para todo lo
    que cuelga por debajo del nivel 3, asi que `en_pantalla` no deja ni la
    pagina que si esta seleccionada. En un dialogo aparte, como Preferencias,
    `en_pantalla` si funciona, y por eso el escenario de preferencias lo usa.

    Lo que si es fiable es el nivel, que `_arbol` pone en cada control.
    """
    inicio = None
    for i, c in enumerate(controles):
        if (c.get("nombre") or "") == nombre:
            inicio = i
            break
    if inicio is None:
        return []
    base = controles[inicio]["nivel"]
    for j in range(inicio + 1, len(controles)):
        if controles[j]["nivel"] <= base:
            return controles[inicio:j]
    return controles[inicio:]


def _lista_de_comentarios(controles: list[dict]) -> dict | None:
    for c in controles:
        if (c["clase"] == "ListBox"
                and "comentario" in (c.get("nombre") or "").lower()):
            return c
    return None


def _panel_comentarios(app: Aplicacion, segundos: float = 8.0) -> list[dict]:
    """Espera a que el panel este construido y devuelve solo sus controles."""
    limite = time.time() + segundos
    rama: list[dict] = []
    while time.time() < limite:
        rama = subarbol(app.arbol(), "PanelComentarios")
        if _lista_de_comentarios(rama) is not None:
            return rama
        time.sleep(0.3)
    return rama


def dialogo_nativo(titulo: str, segundos: float = 8.0):
    """Busca un cuadro de diálogo NATIVO de Windows, de los de `wx.MessageBox`.

    Estos no son ventanas de wx: no salen en `wx.GetTopLevelWindows()`, así
    que desde dentro son invisibles. Es el único caso donde hay que mirar
    desde fuera para saber siquiera que existen.
    """
    try:
        from pywinauto import Desktop
    except ImportError:
        return None
    objetivo = titulo.lower()
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            for w in _candidatas_uia(Desktop):
                try:
                    if objetivo in (w.element_info.name or "").lower():
                        return w
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.3)
    return None


def escenario_dialogos_ayuda(app: Aplicacion, args, res: Resultado):
    """Las tres entradas del menú Ayuda, que son de tres tipos distintos.

    Y esa es la lección: dar por hecho que un ítem de menú «abre una ventana»
    es lo que hizo que la primera versión de este escenario dijera que ninguno
    de los tres abría nada. Uno abre el navegador, otro solo anuncia, y el
    tercero abre un cuadro nativo que wx no lista.
    """
    # 1. Marcar incidencia: no abre nada, anuncia. Se comprueba el anuncio.
    app.pedir("frente")
    n = len(app.anuncios)
    try:
        app.abrir_por_menu("Marcar incidencia")
    except Exception as exc:
        res.fallo(f"Marcar incidencia: no se pudo disparar, {exc}")
    else:
        if app.esperar_dicho("incidencia", segundos=8, desde=n):
            res.nota("«Marcar incidencia» anuncia que se guardó")
        else:
            res.fallo("«Marcar incidencia» no anunció nada, y es su única "
                      "señal: no abre ventana ni hace ruido")

    # 2. Acerca de: cuadro nativo, invisible para wx.
    app.pedir("frente")
    try:
        app.abrir_por_menu("Acerca de")
    except Exception as exc:
        res.fallo(f"Acerca de: no se pudo disparar, {exc}")
        return
    dlg = dialogo_nativo("Acerca de", segundos=8)
    if dlg is None:
        res.fallo("«Acerca de» no abrió ningún cuadro que Windows exponga")
    else:
        textos, botones = [], []
        try:
            for d in dlg.descendants():
                try:
                    rol = d.element_info.control_type
                    nombre = (d.element_info.name or "").strip()
                except Exception:
                    continue
                if rol == "Text" and nombre:
                    textos.append(nombre)
                elif rol == "Button" and nombre:
                    botones.append(nombre)
        except Exception:
            pass
        res.nota(f"«Acerca de» abre un cuadro nativo con {len(textos)} textos "
                 f"y botones: {', '.join(botones) or 'ninguno'}")
        _version_coherente(textos, res)
        for x in textos[:3]:
            res.nota("  dice: " + x[:70])
        if not textos:
            res.fallo("«Acerca de»: el cuadro no expone ningún texto, así que "
                      "un lector de pantalla no tiene qué leer")
        try:
            dlg.type_keys("{ESC}")
        except Exception:
            try:    dlg.close()
            except Exception: pass
        time.sleep(0.8)

    # 3. La guía de la API abre el NAVEGADOR. No se dispara salvo que se pida.
    if getattr(args, "con_navegador", False):
        app.pedir("frente")
        app.abrir_por_menu("Guía de configuración de la API")
        res.nota("«Guía de configuración de la API» abrió el navegador")
    else:
        res.nota("«Guía de configuración de la API» abre el navegador con "
                 "`webbrowser.open`; se salta para no llenar de pestañas la "
                 "máquina de quien corre las pruebas. Usá --con-navegador.")



def _version_coherente(textos: list, res: Resultado) -> None:
    """La version que la aplicacion MUESTRA contra la que documenta el CHANGELOG.

    Nadie vigilaba esto: comprobado el 26/08/2026, ninguna prueba mira
    `APP_VERSION`, asi que se podia publicar una version con el numero mal y el
    unico sintoma seria que el «Acerca de» dijera una cosa y las novedades
    otra. Quien lo sufre es el que descarga el ZIP y no sabe que tiene.
    """
    import re
    mostrada = ""
    for x in textos:
        m = re.search(r"v(\d+\.\d+\.\d+)", x)
        if m:
            mostrada = m.group(1)
            break
    if not mostrada:
        res.fallo("«Acerca de» no muestra ningun numero de version")
        return

    try:
        texto = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    except Exception as exc:
        res.nota(f"no se pudo leer CHANGELOG.md: {exc}")
        return
    m = re.search(r"^##\s*(\d+\.\d+\.\d+)", texto, re.MULTILINE)
    documentada = m.group(1) if m else ""
    if not documentada:
        res.fallo("CHANGELOG.md no tiene ninguna entrada de version")
    elif documentada != mostrada:
        res.fallo("la aplicacion dice v%s y la entrada mas nueva del CHANGELOG "
                  "es %s" % (mostrada, documentada))
    else:
        res.nota(f"version coherente: la aplicacion y el CHANGELOG dicen {mostrada}")


def escenario_avisos_wx(app: Aplicacion, args, res: Resultado):
    """Lo que wx escribe por la salida de error y nadie lee nunca.

    wxWidgets avisa por ahí de widgets mal construidos, de jerarquías que no
    corresponden y de llamadas que fallan. En uso normal esa salida se pierde,
    porque la aplicación se lanza sin consola. Acá se captura y se mira.

    No todo aviso es un defecto, pero un aviso que se repite en cada arranque
    y que nadie ha leído nunca merece por lo menos una mirada.
    """
    # Se recorre un poco de interfaz para que salgan los avisos de construir
    # paneles, no solo los del arranque.
    app.pedir("frente")
    app.simular_sesion_youtube()
    app.mensaje("Ana", "hola")
    time.sleep(2.0)

    if not app.salida_ruta.exists():
        res.fallo("no se capturó la salida de la aplicación")
        return
    crudo = app.salida_ruta.read_text(encoding="utf-8", errors="replace")
    lineas = [l.strip() for l in crudo.splitlines() if l.strip()]

    marcas = ("should be created as child", "failed with error", "Assert",
              "wxWidgets", "Warning:", "Error:")
    avisos = [l for l in lineas if any(m in l for m in marcas)]

    # Se agrupan, porque el mismo aviso sale muchas veces y en bruto tapa todo.
    resumen = {}
    for a in avisos:
        clave = a[:110]
        resumen[clave] = resumen.get(clave, 0) + 1

    if not resumen:
        res.nota("wx no escribió ningún aviso")
        return
    res.nota(f"wx escribió {len(avisos)} avisos, {len(resumen)} distintos")
    for texto, veces in sorted(resumen.items(), key=lambda x: -x[1])[:6]:
        res.fallo(f"aviso de wx x{veces}: {texto}")



# Enlaces que dio el dueno el 21/08/2026 para poder probar contra la red.
# Un directo caduca: si el escenario dice que no hay nadie emitiendo, lo
# primero que hay que mirar es si el enlace sigue vivo, no el codigo.
# Directo de TN, que emite siempre y tiene el chat lleno. Lo eligio el
# dueno el 26/08/2026 como el sitio donde probar: es publico, va rapido
# y a nadie le llama la atencion un mensaje suelto.
DIRECTO_YOUTUBE = "https://www.youtube.com/watch?v=cb12KmMMDJA"
DIRECTO_TIKTOK = "https://www.tiktok.com/@rolon_100/live"


def conectar_de_verdad(app: Aplicacion, res: Resultado, url: str,
                       donde: str, espera: float = 60.0):
    """Pega una URL, pulsa Conectar, y espera a que la aplicacion diga algo.

    Es el unico escenario que toca la red, y por eso es el unico que puede
    fallar por motivos ajenos al codigo. Cuando falle, antes de tocar nada hay
    que comprobar a mano que el directo siga emitiendo.
    """
    app.al_frente()
    # Por el nombre COMPLETO del campo. Pedir foco por «URL» a secas caia en la
    # etiqueta «URL/ID:», que tambien contiene esa palabra y va antes en el
    # arbol, y entonces la URL no se escribia nunca. El escenario no lo decia
    # porque las ordenes rechazadas se ignoraban; con `pedir` estricto salta.
    app.pedir("foco", nombre="URL del directo o vídeo")
    app.pedir("texto", valor=url)
    n = len(app.anuncios)

    boton = None
    for c in app.arbol():
        if c["clase"] == "Button" and "conectar" in (
                (c.get("etiqueta") or "") + (c.get("nombre") or "")).lower():
            boton = c
            break
    if boton is None:
        res.fallo(f"{donde}: no encuentro el botón Conectar")
        return False
    app.pedir("pulsar", nombre=boton.get("nombre") or boton.get("etiqueta"))

    # Se sincroniza con lo que la aplicación dice, no con un reloj: si tarda
    # veinte segundos porque yt-dlp está lento, esperar cinco daría un fallo
    # falso, y esperar sesenta a ciegas gastaría un minuto siempre.
    limite = time.time() + espera
    while time.time() < limite:
        dichos = " ".join(a.get("texto", "") for a in app.anuncios[n:]).lower()
        if "conectado" in dichos or "error" in dichos or "no se pudo" in dichos:
            break
        time.sleep(0.5)

    dichos = [a.get("texto", "") for a in app.anuncios[n:]]
    if not dichos:
        res.fallo(f"{donde}: pulsé Conectar y la aplicación no dijo nada en "
                  f"{espera:.0f} s. Un usuario ciego no sabría si pasó algo")
        return False
    for d in dichos[:6]:
        res.nota(f"  {donde} dice: {d[:90]}")
    junto = " ".join(dichos).lower()
    if "error" in junto or "no se pudo" in junto:
        res.fallo(f"{donde}: la conexión falló. Comprobá a mano que el directo "
                  "siga emitiendo antes de culpar al código")
        return False
    return True


def escenario_directo_youtube(app: Aplicacion, args, res: Resultado):
    """Un directo de YouTube de verdad, con la red de por medio."""
    url = getattr(args, "url_youtube", None) or DIRECTO_YOUTUBE
    res.nota(f"youtube en vivo: {url}")
    if not conectar_de_verdad(app, res, url, "youtube en vivo"):
        return

    # El título y los espectadores los rellena el hilo de captura, no la GUI:
    # que aparezcan prueba que el cableado entero funciona.
    limite = time.time() + 45
    titulo = ""
    while time.time() < limite:
        for c in app.arbol():
            texto = (c.get("etiqueta") or "").strip()
            if c["clase"] == "StaticText" and len(texto) > 12:
                titulo = texto
        if titulo:
            break
        time.sleep(1.0)
    if titulo:
        res.nota(f"youtube en vivo: la ventana muestra «{titulo[:70]}»")
    else:
        res.fallo("youtube en vivo: conectó pero no apareció ningún texto "
                  "largo en la ventana, o sea ni título ni estado")

    lista = None
    limite = time.time() + 90
    while time.time() < limite:
        lista = lista_del_chat(app.arbol())
        if lista and lista.get("items"):
            break
        time.sleep(2.0)
    if lista and lista.get("items"):
        items = lista["items"]
        res.nota(f"youtube en vivo: llegaron {len(items)} mensajes reales")
        for i in items[:3]:
            res.nota("  lee: " + str(i)[:80])
    else:
        res.nota("youtube en vivo: conectó pero no llegó ningún mensaje en "
                 "90 s. Puede ser un chat tranquilo, no es defecto por sí solo")

    # Y ahora lo que ningún escenario había hecho nunca: el reproductor con
    # vídeo de verdad cargado. Hasta el 21/08/2026 la batería solo se había
    # corrido sin nada cargado, que es el caso fácil: con medio real entran en
    # juego la red, el buffer y lo que tarda VLC en responder, y ahí es donde
    # viviría la torpeza de la que se queja quien la usa.
    #
    # Se espera a que termine de cargar antes de medir: juzgar la latencia
    # mientras yt-dlp todavía resuelve la URL mide la red, no la aplicación.
    if app.esperar_dicho("reproduciendo", segundos=60):
        res.nota("youtube en vivo: el reproductor arrancó")
    else:
        res.nota("youtube en vivo: no se oyó «Reproduciendo» en 60 s; se mide "
                 "igual, pero puede que no haya llegado a cargar")
    time.sleep(3.0)

    visibles = " ".join(((c.get("etiqueta") or "") + " " + (c.get("nombre") or ""))
                        for c in app.arbol()).lower()
    if "retroceder 1 min" not in visibles:
        app.pedir("pulsar", nombre="AlternarBotonesReproductor")
    bateria_reproductor(app, res, "youtube en vivo")

    app.llamar("set_conectado", False)


def escenario_directo_tiktok(app: Aplicacion, args, res: Resultado):
    """Un directo de TikTok de verdad. Ruta distinta y más frágil."""
    url = getattr(args, "url_tiktok", None) or DIRECTO_TIKTOK
    res.nota(f"tiktok en vivo: {url}")
    if not conectar_de_verdad(app, res, url, "tiktok en vivo", espera=75.0):
        return
    lista = None
    limite = time.time() + 60
    while time.time() < limite:
        lista = lista_del_chat(app.arbol())
        if lista and lista.get("items"):
            break
        time.sleep(2.0)
    if lista and lista.get("items"):
        res.nota(f"tiktok en vivo: llegaron {len(lista['items'])} eventos")
    else:
        res.nota("tiktok en vivo: conectó pero no llegó nada en 60 s")
    app.llamar("set_conectado", False)


def _hilos_de_captura(app: Aplicacion) -> list:
    """Los hilos de captura de chat vivos, por nombre."""
    vivos = app.hilos()
    return [h for h in vivos if h in ("Chat", "TikTok")]


def escenario_dos_conexiones(app: Aplicacion, args, res: Resultado):
    """Conectar dos veces sin desconectar no deja el hilo viejo girando.

    El 21/08/2026 los registros de un usuario real mostraron diez hilos `Chat`
    arrancados y nueve terminados: al conectar a otro vídeo, el anterior se
    quedaba pidiendo el chat para siempre porque nadie ponía su evento de
    parada. Esto lo comprueba con la aplicación de verdad, que es donde se vio.

    El camino por el que pasa de verdad, leído en `gui.py:872` el 21/08/2026:
    el botón alterna, así que estando conectado no se puede conectar otra vez.
    Pero un error de red hace `set_conectado(False)` y rehabilita el botón
    MIENTRAS el hilo de captura sigue vivo reintentando, y ahí una pulsación
    abre la segunda sesión. Por eso el escenario llama a `set_conectado(False)`
    en medio: es exactamente lo que la aplicación se hace a sí misma cuando
    pytchat pierde la conexión, y lo que le pasó al usuario a las 12:23 y a las
    12:30.

    Vale con conectar dos veces al MISMO directo: la conexión no compara el
    vídeo, abre una sesión nueva igual.
    """
    url = getattr(args, "url_youtube", None) or DIRECTO_YOUTUBE
    res.nota(f"dos conexiones: {url}")

    if not conectar_de_verdad(app, res, url, "dos conexiones (primera)"):
        return
    # Esperar a que el hilo de captura exista de verdad antes de medir: si se
    # mide antes de que arranque, el conteo da cero y el escenario pasa sin
    # haber probado nada.
    limite = time.time() + 30
    while time.time() < limite and not _hilos_de_captura(app):
        time.sleep(0.5)
    primeros = _hilos_de_captura(app)
    if not primeros:
        res.fallo("dos conexiones: la primera no llegó a arrancar ningún hilo "
                  "de captura en 30 s; sin eso no se puede medir nada")
        return
    res.nota(f"dos conexiones: tras la primera hay {len(primeros)} "
             f"({', '.join(primeros)})")

    # Lo que hace la aplicación sola al perder la conexión: apaga la interfaz
    # y deja el hilo reintentando. No mata nada.
    app.llamar("set_conectado", False)
    time.sleep(1.0)
    if not conectar_de_verdad(app, res, url, "dos conexiones (segunda)"):
        return
    # El hilo viejo puede tardar en morir: está dentro de una lectura de red y
    # no ve la parada hasta que vuelve. Se le da margen y se toma el mínimo,
    # porque un solape de un segundo es correcto y quedarse pegado no lo es.
    limite = time.time() + 45
    minimo = 99
    while time.time() < limite:
        minimo = min(minimo, len(_hilos_de_captura(app)))
        if minimo <= 1:
            break
        time.sleep(1.0)

    if minimo <= 1:
        res.nota(f"dos conexiones: el hilo de la primera murió, quedó {minimo}")
    else:
        vivos = _hilos_de_captura(app)
        res.fallo(f"dos conexiones: quedaron {minimo} hilos de captura vivos "
                  f"tras 45 s ({', '.join(vivos)}); el de la sesión vieja no "
                  f"se paró y va a seguir pidiendo el chat hasta que se cierre "
                  f"la aplicación")
    app.llamar("set_conectado", False)


def escenario_overlay(app: Aplicacion, args, res: Resultado):
    """El panel de chat para transmitir: interruptor, servicio y estado.

    La fase 3 de `smoke_test.py` no lo cubre: solo mira Button, Edit, ComboBox,
    List, CheckBox y RadioButton, así que un ítem de menú le pasa invisible.
    Y las pruebas unitarias no arrancan la aplicación entera, que es donde se
    ve si el interruptor está cableado de verdad.

    Comprueba lo único que el dueño no puede mirar: que cuando dice que está
    activo, esté sirviendo la página de verdad.
    """
    import urllib.request

    etiqueta = "Panel de chat para transmitir"
    puerto = 8730
    url = f"http://127.0.0.1:{puerto}/chat"

    def responde(tiempo=4.0):
        try:
            with urllib.request.urlopen(url, timeout=tiempo) as r:
                return r.status == 200 and len(r.read()) > 0
        except Exception:
            return False

    items = [m for m in app.menus()
             if etiqueta in (m.get("etiqueta") or "") and not m.get("submenu")]
    if not items:
        res.fallo(f"no existe el ítem de menú «{etiqueta}»")
        return
    if not items[0].get("marcable"):
        res.fallo("el ítem del panel no es una casilla marcable")
    res.nota(f"ítem encontrado: {items[0].get('etiqueta')!r}")

    encendido_al_entrar = responde(2.0)
    if encendido_al_entrar:
        res.nota("el panel ya venía encendido; se apaga para probar el ciclo")
        app.abrir_por_menu(etiqueta)
        app.esperar_dicho("panel de chat apagado", 8)

    # Encender
    antes = len(app.anuncios)
    app.abrir_por_menu(etiqueta)
    if not app.esperar_dicho("panel de chat activo en el puerto", 10, desde=antes):
        dichos = [a["texto"][:60] for a in app.anuncios[antes:]]
        res.fallo(f"al encender no anunció el puerto; dijo: {dichos}")
    if not responde():
        res.fallo(f"anunció el panel activo pero {url} no responde")
    else:
        res.nota(f"{url} responde")

    # F2 tiene que distinguir que nadie lo está mostrando
    antes = len(app.anuncios)
    app.abrir_por_menu("Anunciar estado")
    app.esperar_dicho("panel", 8, desde=antes)
    dicho = " ".join(a["texto"].lower() for a in app.anuncios[antes:])
    if "panel de chat activo" not in dicho:
        res.fallo("F2 no menciona el panel estando encendido")
    elif "nadie lo est" not in dicho:
        res.fallo("F2 no distingue que nadie está mostrando el panel")
    else:
        res.nota("F2 dice que nadie lo está mostrando")

    # Apagar
    antes = len(app.anuncios)
    app.abrir_por_menu(etiqueta)
    if not app.esperar_dicho("panel de chat apagado", 10, desde=antes):
        res.fallo("al apagar no lo anunció")
    if responde(3.0):
        res.fallo("apagado, el puerto sigue respondiendo")
    else:
        res.nota("apagado, el puerto deja de responder")

    if encendido_al_entrar:
        app.abrir_por_menu(etiqueta)   # se deja como estaba


def escenario_programados(app: Aplicacion, args, res: Resultado):
    """La pestaña de mensajes automáticos, control por control.

    Interesa sobre todo por los dos `wx.SpinCtrl`: son controles COMPUESTOS
    (una caja de texto más dos flechas), y en Windows el `name=` de wx no
    siempre llega al servicio de accesibilidad. Un intervalo que el lector
    anuncia como «cuadro de edición» a secas, sin decir si es el mínimo o el
    máximo, deja al usuario adivinando cuál de los dos está tocando.
    """
    etiqueta_pag = "Mensajes automáticos"
    app.pedir("frente")
    try:
        app.abrir_por_menu("Preferencias")
    except Exception as exc:
        res.fallo(f"programados: no se pudo abrir Preferencias, {exc}")
        return
    if app.esperar_ventana("Preferencias", segundos=15) is None:
        res.fallo("programados: Preferencias no abrió")
        return

    try:
        paginas = app.pedir("pestanas", ventana="Preferencias").get(
            "datos", {}).get("paginas", [])
        if etiqueta_pag not in paginas:
            res.fallo(f"programados: no existe la pestaña «{etiqueta_pag}»; "
                      f"hay {paginas}")
            return
        res.nota(f"pestaña encontrada, es la {paginas.index(etiqueta_pag) + 1} "
                 f"de {len(paginas)}")
        app.pedir("pestanas", ventana="Preferencias",
                  indice=paginas.index(etiqueta_pag))
        time.sleep(0.4)

        controles = app.arbol("Preferencias")
        visibles = [c for c in controles if c.get("en_pantalla")]
        revisar_nombres(visibles, res, "programados")

        # El texto de introducción es donde se explican los límites de la API.
        # Si desaparece, el usuario no tiene dónde enterarse.
        textos = " ".join((c.get("etiqueta") or "") + " " + (c.get("nombre") or "")
                          for c in controles)
        for clave, que in (("5 minutos", "el intervalo mínimo"),
                           ("200 caracteres", "el límite de caracteres"),
                           ("enlaces", "el aviso sobre los enlaces")):
            if clave not in textos:
                res.fallo(f"programados: la introducción no menciona {que}")
        if all(k in textos for k in ("5 minutos", "200 caracteres", "enlaces")):
            res.nota("la introducción explica intervalo, longitud y enlaces")

        # Los controles que tienen que estar, por su name= de wx.
        esperados = ("ActivarProgramados", "ListaProgramados", "TextoProgramado",
                     "MinutosMin", "MinutosMax", "MensajeActivo",
                     "AgregarProgramado", "GuardarProgramado", "QuitarProgramado")
        nombres = {(c.get("nombre") or "") for c in controles}
        faltan = [n for n in esperados if n not in nombres]
        if faltan:
            res.fallo(f"programados: no aparecen en el árbol: {faltan}")
        else:
            res.nota(f"los {len(esperados)} controles de la pestaña están")
    finally:
        app.pedir("cerrar_ventana", ventana="Preferencias")


def escenario_conectar(app: Aplicacion, args, res: Resultado):
    """El boton Conectar, que en una corrida rutinaria no se pulsaba nunca.

    Lo pulsaban solo los tres escenarios de directo vivo, que estan fuera de
    `todos`, asi que sus dos caminos de error no los habia visto nadie. Este no
    toca la red: se queda en los dos casos que fallan antes de salir a buscar
    nada.
    """
    app.pedir("frente")

    # 1. Sin URL. Sale un cuadro nativo, no un anuncio: NVDA lo lee al recibir
    # el foco, pero si el cuadro no expone texto no hay nada que leer.
    app.llamar("set_url", "")
    try:
        app.pedir("pulsar", nombre="Conectar", tiempo=6.0)
    except Exception:
        pass                      # el cuadro es modal y se come la respuesta
    dlg = dialogo_nativo("Falta URL", segundos=8)
    if dlg is None:
        res.fallo("conectar: con la URL vacia no aparecio ningun aviso")
    else:
        textos = _textos_de(dlg)
        res.nota("conectar sin URL abre «Falta URL» con %d textos" % len(textos))
        for x in textos[:2]:
            res.nota("  dice: " + x[:70])
        if not textos:
            res.fallo("conectar: el aviso de URL vacia no expone ningun texto, "
                      "asi que un lector de pantalla no tiene que leer")
        _cerrar_nativo(dlg)

    # 2. URL que no es de YouTube ni de TikTok.
    app.llamar("set_url", "esto no es una direccion")
    n = len(app.anuncios)
    try:
        app.pedir("pulsar", nombre="Conectar", tiempo=6.0)
    except Exception:
        pass
    dlg = dialogo_nativo("URL", segundos=6) or dialogo_nativo("no vál", segundos=2)
    if dlg is not None:
        res.nota("conectar con una URL invalida abre un aviso nativo")
        _cerrar_nativo(dlg)
    elif app.dijo("no es válido", desde=n) or app.dijo("no válido", desde=n):
        res.nota("conectar con una URL invalida se anuncia con voz")
    else:
        res.fallo("conectar: una URL invalida no produjo ni aviso ni anuncio")

    app.llamar("set_url", "")


def _textos_de(dlg) -> list:
    """Los textos que Windows expone de un cuadro nativo."""
    salida = []
    try:
        for d in dlg.descendants():
            try:
                if d.element_info.control_type == "Text":
                    nombre = (d.element_info.name or "").strip()
                    if nombre:
                        salida.append(nombre)
            except Exception:
                continue
    except Exception:
        pass
    return salida


def _cerrar_nativo(dlg) -> None:
    try:
        dlg.type_keys("{ESC}")
    except Exception:
        try:    dlg.close()
        except Exception: pass
    time.sleep(0.8)


def escenario_menu_chat(app: Aplicacion, args, res: Resultado):
    """El menu contextual de la lista del chat, donde vive casi toda la accion.

    Entre siete y nueve entradas segun haya sesion: copiar, copiar todo,
    releer, abrir enlace, silenciar de dos formas, rehabilitar, y con sesion
    expulsar y banear. Nunca se habia abierto en el banco.

    Se abre con la tecla Aplicaciones, que es como llega quien no usa raton.
    """
    app.pedir("frente")
    app.simular_sesion_youtube(titulo="Prueba del menu contextual")
    app.mensaje("Ana", "hola, mira esto https://example.com/algo")

    limite = time.time() + 12
    lista = None
    while time.time() < limite:
        lista = lista_del_chat(app.arbol())
        if lista and lista.get("items"):
            break
        time.sleep(0.3)
    if not lista or not lista.get("items"):
        res.fallo("menu del chat: no llego ningun mensaje a la lista")
        return

    app.pedir("foco", nombre="Chat en vivo")
    app.teclas("down")
    time.sleep(0.5)

    # El menu emergente es una ventana nativa: wx no la expone, hay que
    # mirarla desde fuera igual que los cuadros de `wx.MessageBox`.
    try:
        app.teclas("menu")
    except Exception as exc:
        res.nota("menu del chat: la tecla Aplicaciones no se pudo simular, %s" % exc)
        res.fallo("menu del chat: SIN PROBAR, no se pudo abrir")
        return

    entradas = _entradas_de_menu(segundos=8)
    if not entradas:
        res.fallo("menu del chat: la tecla Aplicaciones no abrio ningun menu "
                  "que Windows exponga")
        _escape()
        return

    res.nota("menu del chat: %d entradas" % len(entradas))
    for e in entradas[:9]:
        res.nota("  " + e[:70])

    juntas = " ".join(entradas).lower()
    for esperada in ("copiar", "releer", "enlace", "silenciar"):
        if esperada not in juntas:
            res.fallo("menu del chat: no aparece ninguna entrada de «%s»"
                      % esperada)
    sin_nombre = [e for e in entradas if not e.strip()]
    if sin_nombre:
        res.fallo("menu del chat: %d entradas sin texto, mudas para el lector"
                  % len(sin_nombre))
    _escape()


def _entradas_de_menu(segundos: float = 8.0) -> list:
    """Los textos de un menu emergente nativo, mirando desde fuera."""
    try:
        from pywinauto import Desktop
    except ImportError:
        return []
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            for w in _candidatas_uia(Desktop):
                try:
                    if w.element_info.control_type != "Menu":
                        continue
                    textos = []
                    for d in w.descendants():
                        try:
                            if d.element_info.control_type == "MenuItem":
                                textos.append((d.element_info.name or "").strip())
                        except Exception:
                            continue
                    if textos:
                        return textos
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.3)
    return []


def _escape() -> None:
    try:
        from pywinauto import keyboard
        keyboard.send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.5)


def escenario_captura_atajo(app: Aplicacion, args, res: Resultado):
    """La pestana Atajos, ahora que la captura ya no abre ninguna ventana.

    Hasta el 26/08/2026 esto pulsaba un boton y esperaba un dialogo «Capturar
    atajo». Ese dialogo se borro: ahora el propio boton entra en modo captura.
    El escenario viejo daba un fallo que parecia de la aplicacion y era del
    banco, y estuvo dos dias en el informe.

    LO QUE ESTE ESCENARIO NO CUBRE, y conviene saberlo: no comprueba que teclas
    de verdad lleguen al boton, porque el simulador de wx escribe en la ventana
    que Windows tenga al frente y el banco trae al frente la ventana PRINCIPAL,
    no el dialogo modal de Preferencias. Esa parte, o sea que Escape cancele,
    que Tab salga y que Alt+Enter se capture en vez de desactivar, la cubren
    las pruebas de `tests/test_atajos_captura.py`, una por rama.
    """
    app.pedir("frente")
    try:
        app.abrir_por_menu("Preferencias")
    except Exception as exc:
        res.fallo("atajos: no se pudo abrir Preferencias, %s" % exc)
        return
    if app.esperar_ventana("Preferencias", segundos=15) is None:
        res.fallo("atajos: Preferencias no abrio")
        return

    try:
        respuesta = app.pedir("pestanas", ventana="Preferencias")
        paginas = respuesta.get("datos", {}).get("paginas", [])
        indice = next(i for i, n in enumerate(paginas) if "tajo" in n)
        app.pedir("pestanas", ventana="Preferencias", indice=indice)
        time.sleep(0.8)
    except Exception as exc:
        res.fallo("atajos: no se pudo llegar a la pestana, %s" % exc)
        app.pedir("cerrar_ventana", ventana="Preferencias")
        return

    def boton_de(nombre):
        for c in app.arbol("Preferencias"):
            if (c.get("nombre") or "") == nombre:
                return c
        return None

    # Cada boton dice su atajo en la etiqueta, y eso NO es decoracion: es lo
    # unico que lee un lector de pantalla al recorrer la pestana.
    conectar = boton_de("Atajo_conectar")
    if conectar is None:
        res.fallo("atajos: no encuentro el boton de la accion Conectar")
        app.pedir("cerrar_ventana", ventana="Preferencias")
        return
    etiqueta_inicial = (conectar.get("etiqueta") or "").replace("&", "")
    if ":" not in etiqueta_inicial:
        res.fallo("atajos: el boton se llama «%s» y no dice que atajo tiene"
                  % etiqueta_inicial)
    else:
        res.nota("atajos, el boton dice: " + etiqueta_inicial)

    # Entrar en modo captura tiene que anunciarse Y cambiar la etiqueta. Si
    # solo se anunciara, quien vuelve sobre el control mas tarde no tendria
    # forma de saber que esta esperando una combinacion.
    n = len(app.anuncios)
    # El foco PRIMERO, y no es un adorno: el modo captura se sale al perder el
    # foco, asi que si se entra con un evento sintetico sin foco, el boton
    # nunca lo pierde y la comprobacion de mas abajo da un fallo que parece de
    # la aplicacion. Pasó el 26/08/2026 al escribir este escenario.
    app.pedir("foco", ventana="Preferencias", nombre="Atajo_conectar")
    app.pedir("pulsar", nombre="Atajo_conectar")
    time.sleep(0.5)
    if app.esperar_dicho("combinación", segundos=6, desde=n):
        res.nota("atajos: entrar en captura se anuncia")
    else:
        res.fallo("atajos: pulsar el boton no anuncio nada, asi que nadie sabe "
                  "que la aplicacion esta esperando una combinacion")
    ahora = boton_de("Atajo_conectar")
    texto = (ahora.get("etiqueta") or "").replace("&", "") if ahora else ""
    if "combinación" not in texto.lower():
        res.fallo("atajos: en modo captura el boton sigue diciendo «%s», asi "
                  "que su estado no se puede leer" % texto)
    else:
        res.nota("atajos, en captura el boton dice: " + texto)

    # Se sale del modo por el mismo camino que usaria alguien que se arrepiente
    # sin teclado disponible: mover el foco a otro control.
    app.pedir("foco", ventana="Preferencias", nombre="RestablecerAtajos")
    time.sleep(0.5)
    vuelto = boton_de("Atajo_conectar")
    texto = (vuelto.get("etiqueta") or "").replace("&", "") if vuelto else ""
    if texto != etiqueta_inicial:
        res.fallo("atajos: al perder el foco el boton quedo en «%s» y antes "
                  "decia «%s»" % (texto, etiqueta_inicial))
    else:
        res.nota("atajos: perder el foco devuelve la etiqueta a como estaba")

    restablecer = boton_de("RestablecerAtajos")
    if restablecer is None:
        res.fallo("atajos: no hay boton para restablecer los valores de fabrica")
    elif not restablecer.get("habilitado"):
        res.fallo("atajos: el boton de restablecer esta deshabilitado, asi que "
                  "sale del orden de Tab")
    else:
        n = len(app.anuncios)
        app.pedir("pulsar", nombre="RestablecerAtajos")
        if app.esperar_dicho("restablecid", segundos=6, desde=n):
            res.nota("atajos: restablecer se anuncia")
        else:
            res.fallo("atajos: restablecer no anuncio nada")

    revisar_nombres(subarbol(app.arbol("Preferencias"), "PagAtajos"),
                    res, "atajos")
    app.pedir("cerrar_ventana", ventana="Preferencias")


def escenario_redactar(app: Aplicacion, args, res: Resultado):
    """El cuadro de escritura del chat.

    Lo que se comprueba es el contrato que lo hace usable sin ver: que el
    cuadro y el boton esten SIEMPRE, que el boton diga por que no se puede
    usar, y que activarlo sin poder lo anuncie en vez de callarse.
    """
    app.pedir("frente")

    def controles():
        rama = subarbol(app.arbol(), "PanelRedactar")
        cuadro = next((c for c in rama if c["clase"] == "TextCtrl"), None)
        boton = next((c for c in rama if c["clase"] == "Button"), None)
        return cuadro, boton

    cuadro, boton = controles()
    if cuadro is None or boton is None:
        res.fallo("redactar: no encuentro el cuadro o el boton en el arbol")
        return

    # Sin conectar tienen que seguir estando, y habilitados: deshabilitarlos
    # los sacaria del orden de Tab y el motivo quedaria fuera de alcance.
    for ctrl, comovse in ((cuadro, "el cuadro"), (boton, "el boton")):
        if not ctrl.get("habilitado"):
            res.fallo("redactar: %s esta deshabilitado sin conectar, asi que "
                      "sale del orden de Tab y su motivo no se puede leer"
                      % comovse)
    etiqueta = (boton.get("etiqueta") or "").replace("&", "")
    if "(" not in etiqueta:
        res.fallo("redactar: sin conectar, el boton se llama «%s» y no dice "
                  "por que no se puede usar" % etiqueta)
    else:
        res.nota("redactar, sin conectar el boton se llama: " + etiqueta)

    n = len(app.anuncios)
    app.pedir("pulsar", nombre="Enviar mensaje al chat")
    if app.esperar_dicho("conéctate", segundos=6, desde=n):
        res.nota("redactar: activarlo sin conectar lo anuncia en vez de callarse")
    else:
        res.fallo("redactar: activarlo sin conectar no anuncio nada")

    # Conectado, el motivo desaparece.
    app.simular_sesion_youtube(titulo="Prueba del cuadro")
    time.sleep(1.2)
    _, boton = controles()
    etiqueta = (boton.get("etiqueta") or "").replace("&", "")
    if "(" in etiqueta:
        res.fallo("redactar: conectado, el boton sigue diciendo un motivo: «%s»"
                  % etiqueta)
    else:
        res.nota("redactar, conectado el boton vuelve a llamarse: " + etiqueta)

    # Con el cuadro vacio no se manda nada y se avisa.
    n = len(app.anuncios)
    app.pedir("pulsar", nombre="Enviar mensaje al chat")
    if app.esperar_dicho("escribe un mensaje", segundos=6, desde=n):
        res.nota("redactar: con el cuadro vacio avisa en vez de mandar nada")
    else:
        res.fallo("redactar: con el cuadro vacio no avisa")

    orden = recorrer_tab(app, res, "redactar", vueltas=10)
    res.nota("redactar, orden de Tab: " + " > ".join(orden[:5]))
    esperado = ["Chat en vivo", "Mensaje para el chat", "Enviar"]
    juntos = " > ".join(orden)
    if not all(x in juntos for x in esperado):
        res.fallo("redactar: el orden de Tab no pasa por lista, cuadro y "
                  "boton; da %s" % juntos)

    # Se deja como se encontro: este escenario necesita el estado SIN conectar
    # para su primera mitad, y el de mas adelante mide el paso de uno al otro.
    app.restaurar_desconectado()
    time.sleep(0.5)


def escenario_enviar_live(app: Aplicacion, args, res: Resultado):
    """Manda un mensaje de verdad al chat de un directo, punta a punta.

    Es el unico que prueba la ruta de ESCRITURA de la API: credenciales, token,
    `liveChatId` y la llamada. Todo lo demas del cuadro se comprueba sin red en
    `redactar`, pero eso no toca la API ni una vez.

    Necesita tres cosas que no dependen del codigo: un directo emitiendo, sesion
    OAuth iniciada y que el directo tenga el chat abierto. Cuando falle, eso es
    lo primero que hay que descartar. Por eso vive fuera de `todos`.

    Manda la palabra «test» y nada mas, en el directo que el dueno eligio para
    esto. No se manda nada que parezca dirigido a nadie.
    """
    url = getattr(args, "url_youtube", None) or DIRECTO_YOUTUBE
    res.nota(f"enviar al chat: {url}")
    if not conectar_de_verdad(app, res, url, "enviar al chat", espera=75.0):
        return

    # El motivo dentro del nombre del boton es el que dice si se puede escribir.
    # Si sigue ahi conectado, no hay sesion o el directo no tiene chat, y eso no
    # es un fallo del cuadro: se dice y se para, en vez de mandar a ciegas.
    boton = None
    limite = time.time() + 30
    while time.time() < limite:
        rama = subarbol(app.arbol(), "PanelRedactar")
        boton = next((c for c in rama if c["clase"] == "Button"), None)
        if boton and "(" not in (boton.get("etiqueta") or ""):
            break
        time.sleep(1.0)
    if boton is None:
        res.fallo("enviar al chat: no encuentro el boton de enviar")
        return
    etiqueta = (boton.get("etiqueta") or "").replace("&", "")
    if "(" in etiqueta:
        res.nota("enviar al chat: NO se manda nada, el boton dice «%s». "
                 "Falta sesion o el directo no tiene chat abierto." % etiqueta)
        return

    app.pedir("foco", nombre="Mensaje para el chat")
    app.pedir("texto", valor="test")
    n = len(app.anuncios)
    app.pedir("pulsar", nombre="Enviar mensaje al chat")

    # Se espera a lo que DICE, no a un reloj: la llamada va en un hilo aparte y
    # tarda lo que tarde la red.
    dicho = ""
    limite = time.time() + 45
    while time.time() < limite:
        dicho = " ".join(a.get("texto", "") for a in app.anuncios[n:]).lower()
        if "enviado" in dicho or "error" in dicho or "no se pudo" in dicho:
            break
        time.sleep(0.5)

    for d in [a.get("texto", "") for a in app.anuncios[n:]][:6]:
        res.nota("  enviar al chat dice: " + d[:90])
    if "enviado" in dicho:
        res.nota("enviar al chat: el mensaje salio y se anuncio")
    elif not dicho:
        res.fallo("enviar al chat: pulse enviar y la aplicacion no dijo nada "
                  "en 45 s. Sin voz, quien no ve no sabe si salio")
    else:
        res.fallo("enviar al chat: no confirmo el envio, dijo: " + dicho[:120])

    # Despues de enviar, el cuadro queda vacio y con el foco: si no, hay que
    # volver a buscarlo con Tab para escribir el siguiente.
    rama = subarbol(app.arbol(), "PanelRedactar")
    cuadro = next((c for c in rama if c["clase"] == "TextCtrl"), None)
    if cuadro is None:
        res.fallo("enviar al chat: el cuadro desaparecio despues de enviar")
    else:
        if (cuadro.get("valor") or "").strip():
            res.fallo("enviar al chat: el cuadro conserva el texto ya enviado, "
                      "asi que el siguiente mensaje saldria repetido")
        else:
            res.nota("enviar al chat: el cuadro queda vacio")


def escenario_cierre(app: Aplicacion, args, res: Resultado):
    """Cerrar la ventana con una sesion abierta.

    Cierra la instancia PRINCIPAL, no una aparte, y por eso va el ultimo de la
    corrida completa. No se puede levantar una segunda: `main.py` tiene guarda
    de instancia unica, avisa y se cierra sola. Costo una corrida descubrirlo.

    Lo que esto NO prueba, y conviene decirlo en vez de dar por cubierto lo que
    no lo esta: aca la sesion esta simulada y NO hay hilos de captura de verdad
    girando, que es justamente el caso que se sospecha del cierre con Alt+F4.
    Ese sigue SIN PROBAR y necesita un directo real.
    """
    app.pedir("frente")
    app.simular_sesion_youtube(titulo="Prueba de cierre")
    app.mensaje("Ana", "hola")
    time.sleep(1.5)
    hilos = app.hilos()
    res.nota("cierre: antes de cerrar hay %d hilos: %s"
             % (len(hilos), ", ".join(sorted(hilos)[:8])))

    arranque = time.time()
    try:
        app.pedir("cerrar_ventana", tiempo=6.0)
    except Exception:
        pass
    limite = time.time() + 20
    murio = False
    while time.time() < limite:
        if app.murio_sola():
            murio = True
            break
        time.sleep(0.5)
    tardanza = time.time() - arranque

    if not murio:
        res.fallo("cierre: la aplicacion no cerro en 20 s con una sesion "
                  "abierta")
        return
    res.nota("cierre: la aplicacion cerro sola en %.1f s" % tardanza)
    # `apagado.TOPE_ESPERA_CIERRE` son 3 segundos. Con margen para que arranque
    # el proceso de cierre, mas de 10 significa que algo se quedo esperando.
    if tardanza > 10:
        res.fallo("cierre: tardo %.1f s, y el tope de espera de las capturas "
                  "es de %.0f s" % (tardanza, 3.0))
    if app.dijo("cerrando"):
        res.nota("cierre: se anuncia antes de cerrar")
    else:
        res.nota("cierre: SIN COMPROBAR que se anuncie; no aparece «cerrando» "
                 "entre lo grabado")


# Cada modulo de interfaz con el escenario que lo recorre. Los `gui*.py` NO se
# listan aca: se descubren del disco en `superficies_sin_escenario`, y esa es
# toda la gracia. Una lista escrita a mano solo caza lo que alguien se acordo
# de anotar, y el 25/08/2026 eso ya dejo dos escenarios registrados fuera de la
# corrida completa sin que nadie avisara. Descubriendo, un `gui_algo.py` nuevo
# sin escenario detiene la corrida y queda nombrado.
#
# La idea es de `miguel-cinsfran/tesis-orquestacion`, donde el barrido de
# accesibilidad descubre las pantallas del sistema de archivos por el mismo
# motivo.
#
# `reproductor.py` e `iconos.py` van a mano porque dibujan interfaz y no se
# llaman `gui*`: sin ellos el descubrimiento miraria para otro lado.
SUPERFICIES = {
    "gui.py": "principal",
    "gui_comentarios.py": "comentarios",
    "gui_descargas.py": "descargas",
    "gui_historial.py": "historial",
    "gui_transmision.py": "transmision",
    "gui_preferencias.py": "preferencias",
    "gui_redactar.py": "redactar",
    "reproductor.py": "reproductor",
    "iconos.py": "reproductor",
}

EXTRAS_DE_INTERFAZ = ("reproductor.py", "iconos.py")


def superficies_sin_escenario() -> list[str]:
    """Modulos de interfaz que existen en el disco y no tiene quien los mire."""
    modulos = {p.name for p in RAIZ.glob("gui*.py")}
    modulos.update(n for n in EXTRAS_DE_INTERFAZ if (RAIZ / n).exists())
    huerfanos = []
    for nombre in sorted(modulos):
        escenario = SUPERFICIES.get(nombre)
        if escenario is None or escenario not in ESCENARIOS:
            huerfanos.append(nombre)
    return huerfanos


# Escenarios que a proposito NO entran en `todos`, con su motivo. Los tres
# necesitan un directo de verdad emitiendo ahora mismo: en una corrida rutinaria
# fallarian por la red o porque el directo termino, no por la aplicacion.
FUERA_DE_TODOS = frozenset({
    "directo_youtube",   # pide un directo de YouTube vivo
    "directo_tiktok",    # pide un directo de TikTok vivo
    "dos_conexiones",    # conecta dos veces a un directo vivo
    "enviar_live",       # escribe de verdad en un chat: pide directo y sesion
})

ESCENARIOS = {
    "menus": escenario_menus,
    "principal": escenario_principal,
    "descargas": escenario_descargas,
    "preferencias": escenario_preferencias,
    "historial": escenario_historial,
    "transmision": escenario_transmision,
    "ayuda": escenario_ayuda,
    "dialogos_ayuda": escenario_dialogos_ayuda,
    "chat": escenario_chat,
    "comentarios": escenario_comentarios,
    "conectar": escenario_conectar,
    "menu_chat": escenario_menu_chat,
    "captura_atajo": escenario_captura_atajo,
    "redactar": escenario_redactar,
    "cierre": escenario_cierre,
    "tiktok": escenario_tiktok,
    "avisos_wx": escenario_avisos_wx,
    "diagnostico": escenario_diagnostico,
    "reproductor": escenario_reproductor,
    "arranque_frio": escenario_arranque_frio,
    "directo_youtube": escenario_directo_youtube,
    "dos_conexiones": escenario_dos_conexiones,
    "directo_tiktok": escenario_directo_tiktok,
    "overlay": escenario_overlay,
    "programados": escenario_programados,
    "enviar_live": escenario_enviar_live,
}


_ESCENARIO_EN_CURSO = "ninguno todavía"


def _armar_tope_global(minutos: float, app) -> None:
    """Mata la corrida entera si se cuelga, diciendo en qué escenario fue.

    Cada espera del banco tiene su propio tope, pero la corrida no tenía
    ninguno. El 25/08/2026 se colgó con el diálogo de Preferencias abierto y se
    quedó así hasta que alguien lo mató a mano, con la máquina del dueño
    secuestrada. Un banco que puede no terminar no se puede dejar corriendo.

    Sale con `os._exit` a propósito: si el hilo principal está bloqueado dentro
    de una llamada nativa, una excepción no lo despierta.
    """
    def _matar():
        print()
        print(f"TOPE: la corrida pasó de {minutos:g} minutos y se corta.")
        print(f"Se colgó en el escenario: {_ESCENARIO_EN_CURSO}")
        print("La aplicación se cierra igual. Esto es un fallo del banco o del")
        print("escenario, no necesariamente de la aplicación.")
        try:
            app.cerrar()
        except Exception:
            pass
        sys.stdout.flush()
        os._exit(2)

    temporizador = threading.Timer(minutos * 60, _matar)
    temporizador.daemon = True
    temporizador.start()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--escenario", action="append", default=None,
                   choices=sorted(ESCENARIOS) + ["todos"])
    p.add_argument("--url-youtube", dest="url_youtube",
                   default=None, help="directo de YouTube a usar")
    p.add_argument("--url-tiktok", dest="url_tiktok",
                   default=None, help="directo de TikTok a usar")
    p.add_argument("--con-navegador", action="store_true",
                   dest="con_navegador",
                   help="permite abrir el navegador de verdad")
    p.add_argument("--carpeta", default=None,
                   help="dónde dejar las grabaciones")
    p.add_argument("--tope-minutos", dest="tope_minutos", type=float,
                   default=20.0,
                   help="corta la corrida entera si se cuelga (0 lo desactiva)")
    args = p.parse_args()

    pedidos = args.escenario or ["todos"]
    if "todos" in pedidos:
        # `reproductor` va primero y no es capricho: comprueba qué dice la
        # aplicación con NADA cargado, y en cuanto `chat` o `tiktok` simulan una
        # sesión ese estado ya no vuelve sin reiniciar. Corrido después, el
        # botón de reproducir pasa la comprobación por el motivo equivocado.
        pedidos = ["arranque_frio", "reproductor",
                   "menus", "principal", "descargas", "preferencias",
                   "programados", "historial", "transmision", "ayuda", "dialogos_ayuda",
                   # `redactar` va antes que `chat` y no es capricho: la
                   # mitad de lo que comprueba es como se comporta SIN
                   # conectar, y en cuanto `chat` simula una sesion ese estado
                   # no vuelve. Corrido despues, pasaba por el motivo
                   # equivocado. Mismo motivo que `reproductor`.
                   "conectar", "captura_atajo", "redactar",
                   "overlay", "chat", "menu_chat",
                   "comentarios", "tiktok", "avisos_wx", "diagnostico", "cierre"]
        # Un escenario registrado que no este ni aca ni entre los excluidos no
        # se corre NUNCA con `todos`, y no lo dice nadie. Paso el 25/08/2026:
        # se agregaron `overlay` y `programados` al registro y quedaron fuera de
        # la corrida completa sin una linea de aviso. La lista va a mano porque
        # el ORDEN importa, asi que la unica defensa es comprobar que no falte.
        olvidados = sorted(set(ESCENARIOS) - set(pedidos) - FUERA_DE_TODOS)
        if olvidados:
            p.error("estos escenarios estan registrados pero no se corren con "
                    "`todos` ni figuran en FUERA_DE_TODOS: %s. Agregalos a la "
                    "lista, en el lugar que corresponda por orden, o a "
                    "FUERA_DE_TODOS con su motivo." % ", ".join(olvidados))

        # Y el otro lado del mismo agujero: un modulo de interfaz que nacio y
        # no tiene quien lo recorra. La guarda de arriba solo mira lo que ya
        # esta registrado, asi que no habria dicho nada de `gui_comentarios.py`,
        # que existia desde el principio y nunca entro en el banco.
        huerfanos = superficies_sin_escenario()
        if huerfanos:
            p.error("estos modulos de interfaz no tienen escenario que los "
                    "recorra: %s. Escribi uno y anotalo en SUPERFICIES."
                    % ", ".join(huerfanos))

    # Por defecto, dentro de `qa/salida/`, que está en el `.gitignore`: las
    # grabaciones llevan la salida cruda de la aplicación y no se suben. Fuera de
    # versiones. En la raíz ensuciaba el repositorio con tres archivos sueltos
    # después de cada corrida.
    carpeta = Path(args.carpeta) if args.carpeta else (RAIZ / "qa" / "salida")
    carpeta.mkdir(parents=True, exist_ok=True)
    app = Aplicacion(carpeta)
    res = Resultado()
    if args.tope_minutos > 0:
        _armar_tope_global(args.tope_minutos, app)

    # El arranque en frío monta su propia aplicación, y `main.py` no admite dos
    # a la vez. Va antes de levantar la compartida, y no dentro del bucle.
    if "arranque_frio" in pedidos:
        pedidos = [n for n in pedidos if n != "arranque_frio"]
        print()
        print("--- escenario: arranque_frio ---")
        try:
            escenario_arranque_frio(app, args, res)
        except Exception as exc:
            res.fallo(f"arranque_frio: el escenario reventó, {exc!r}")

    print("Arrancando la aplicación con la sonda puesta. No va a hablar.")
    app.arrancar()
    try:
        if not app.esperar_lista(segundos=60):
            print("La aplicación no contestó al ping en 60 segundos.")
            return 1
        print("Lista y contestando órdenes.")
        # Prueba de que la sonda está puesta, no de que yo lo crea.
        if not app.dijo("grabador instalado"):
            print("AVISO: la sonda no dejó constancia. Podría estar hablando.")

        for nombre in pedidos:
            global _ESCENARIO_EN_CURSO
            _ESCENARIO_EN_CURSO = nombre
            print()
            print(f"--- escenario: {nombre} ---")
            try:
                ESCENARIOS[nombre](app, args, res)
            except Exception as exc:
                res.fallo(f"{nombre}: el escenario reventó, {exc!r}")
    finally:
        app.cerrar()

    print()
    print("=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  {len(res.notas)} comprobaciones, {len(res.fallos)} fallos.")
    print(f"  Anuncios grabados: {len(app.anuncios)}, "
          f"en {app.anuncios_ruta.name}")
    print("  Esto no prueba que NVDA lo lea, ni cómo suena, ni la braille.")

    # Los fallos, aparte y en un archivo. Una corrida completa son veinte
    # minutos y mas de cien lineas: buscar los fallos volviendo atras en la
    # terminal es incomodo con lector de pantalla, y con el buffer lleno
    # directamente se pierden.
    informe = carpeta / "qa-informe.txt"
    try:
        lineas = ["Banco de QA de YTChat TTS",
                  "escenarios: " + ", ".join(pedidos),
                  "%d comprobaciones, %d fallos"
                  % (len(res.notas), len(res.fallos)), ""]
        if res.fallos:
            lineas.append("FALLOS")
            lineas += ["%2d. %s" % (i, x)
                       for i, x in enumerate(res.fallos, 1)]
        else:
            lineas.append("Sin fallos.")
        lineas += ["", "NOTAS"]
        lineas += ["    " + x for x in res.notas]
        informe.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        print(f"  Informe con los fallos en {informe}")
    except Exception as exc:
        print(f"  AVISO: no se pudo escribir el informe: {exc}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
