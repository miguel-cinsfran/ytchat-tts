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


def roles_segun_windows(titulo: str) -> dict[str, int]:
    """Qué roles expone esta ventana al servicio de accesibilidad de Windows.

    Es la única comprobación que necesita mirar desde fuera, y por eso usa
    pywinauto: desde dentro wx siempre dirá `CheckBox`, aunque Windows la esté
    exponiendo como botón. La diferencia es justo lo que discute `AGENTS.md`.
    """
    try:
        from pywinauto import Desktop
    except ImportError:
        return {}
    cuenta: dict[str, int] = {}
    _ULTIMOS_NOMBRES.clear()
    objetivo = titulo.lower()
    try:
        for w in Desktop(backend="uia").windows(top_level_only=False):
            try:
                if objetivo not in (w.element_info.name or "").lower():
                    continue
            except Exception:
                continue
            for d in w.descendants():
                try:
                    rol = d.element_info.control_type
                    nombre = (d.element_info.name or "").strip()
                except Exception:
                    continue
                cuenta[rol] = cuenta.get(rol, 0) + 1
                _ULTIMOS_NOMBRES.setdefault(rol, []).append(nombre)
            break
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
                    esperados: tuple[str, ...] = ()) -> bool:
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
        juntos = " ".join(
            ((c.get("nombre") or "") + " " + (c.get("etiqueta") or ""))
            for c in controles).lower()
        for e in esperados:
            if e.lower() not in juntos:
                res.fallo(f"{titulo}: no aparece nada llamado «{e}»")

    orden = recorrer_tab(app, res, titulo, vueltas=vueltas_tab)
    res.nota(f"{titulo}, orden de Tab, {len(orden)} paradas: "
             + " > ".join(orden[:12]))

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
            for w in Desktop(backend="uia").windows(top_level_only=False):
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
DIRECTO_YOUTUBE = "https://www.youtube.com/watch?v=ArKbAx1K-2U"
DIRECTO_TIKTOK = "https://www.tiktok.com/@rolon_100/live"


def conectar_de_verdad(app: Aplicacion, res: Resultado, url: str,
                       donde: str, espera: float = 60.0):
    """Pega una URL, pulsa Conectar, y espera a que la aplicacion diga algo.

    Es el unico escenario que toca la red, y por eso es el unico que puede
    fallar por motivos ajenos al codigo. Cuando falle, antes de tocar nada hay
    que comprobar a mano que el directo siga emitiendo.
    """
    app.pedir("frente")
    app.pedir("foco", nombre="URL")
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


ESCENARIOS = {
    "menus": escenario_menus,
    "principal": escenario_principal,
    "descargas": escenario_descargas,
    "preferencias": escenario_preferencias,
    "historial": escenario_historial,
    "ayuda": escenario_ayuda,
    "dialogos_ayuda": escenario_dialogos_ayuda,
    "chat": escenario_chat,
    "tiktok": escenario_tiktok,
    "avisos_wx": escenario_avisos_wx,
    "diagnostico": escenario_diagnostico,
    "reproductor": escenario_reproductor,
    "arranque_frio": escenario_arranque_frio,
    "directo_youtube": escenario_directo_youtube,
    "directo_tiktok": escenario_directo_tiktok,
}


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
    args = p.parse_args()

    pedidos = args.escenario or ["todos"]
    if "todos" in pedidos:
        # `reproductor` va primero y no es capricho: comprueba qué dice la
        # aplicación con NADA cargado, y en cuanto `chat` o `tiktok` simulan una
        # sesión ese estado ya no vuelve sin reiniciar. Corrido después, el
        # botón de reproducir pasa la comprobación por el motivo equivocado.
        pedidos = ["arranque_frio", "reproductor",
                   "menus", "principal", "descargas", "preferencias",
                   "historial", "ayuda", "dialogos_ayuda", "chat",
                   "tiktok", "avisos_wx", "diagnostico"]

    # Por defecto, dentro de `qa/salida/`, que está en el `.gitignore`: las
    # grabaciones llevan la salida cruda de la aplicación y no se suben. Fuera de
    # versiones. En la raíz ensuciaba el repositorio con tres archivos sueltos
    # después de cada corrida.
    carpeta = Path(args.carpeta) if args.carpeta else (RAIZ / "qa" / "salida")
    carpeta.mkdir(parents=True, exist_ok=True)
    app = Aplicacion(carpeta)
    res = Resultado()

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
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
