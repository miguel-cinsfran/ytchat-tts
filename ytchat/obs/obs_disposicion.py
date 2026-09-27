"""Geometría de la disposición del panel en OBS."""

from __future__ import annotations

from dataclasses import dataclass


ANCLAJES: dict[str, int] = {
    "superior-izquierda": 5, "superior-centro": 4, "superior-derecha": 6,
    "centro-izquierda": 1, "centro": 0, "centro-derecha": 2,
    "inferior-izquierda": 9, "inferior-centro": 8, "inferior-derecha": 10,
}


def coordenadas(anclaje, lienzo_ancho, lienzo_alto, margen_pct=2.0):
    if anclaje not in ANCLAJES:
        raise ValueError(f"Anclaje desconocido: {anclaje}")
    margen_x = lienzo_ancho * margen_pct / 100
    margen_y = lienzo_alto * margen_pct / 100
    mascara = ANCLAJES[anclaje]
    x = (margen_x if mascara & 1 else
         lienzo_ancho - margen_x if mascara & 2 else lienzo_ancho / 2)
    y = (margen_y if mascara & 4 else
         lienzo_alto - margen_y if mascara & 8 else lienzo_alto / 2)
    return x, y, mascara


def rectangulo(x, y, ancho, alto, alineacion):
    izquierda = (x if alineacion & 1 else
                 x - ancho if alineacion & 2 else x - ancho / 2)
    arriba = (y if alineacion & 4 else
              y - alto if alineacion & 8 else y - alto / 2)
    return izquierda, arriba, ancho, alto


def escala_para(ancho_deseado, alto_deseado, ancho_fuente, alto_fuente):
    if ancho_fuente <= 0 or alto_fuente <= 0:
        return None
    return ancho_deseado / ancho_fuente, alto_deseado / alto_fuente


def _interseccion(a, b):
    izquierda = max(a[0], b[0])
    arriba = max(a[1], b[1])
    derecha = min(a[0] + a[2], b[0] + b[2])
    abajo = min(a[1] + a[3], b[1] + b[3])
    return max(0.0, derecha - izquierda) * max(0.0, abajo - arriba)


def _area(rect):
    return max(0.0, rect[2]) * max(0.0, rect[3])


def solape(rect_a, rect_b) -> float:
    area_b = _area(rect_b)
    return 0.0 if not area_b else _interseccion(rect_a, rect_b) / area_b * 100


def fuera_del_lienzo(rect, lienzo_ancho, lienzo_alto) -> float:
    area = _area(rect)
    if not area:
        return 0.0
    return (area - _interseccion(rect, (0, 0, lienzo_ancho, lienzo_alto))) / area * 100


def anclaje_de(rect, lienzo_ancho, lienzo_alto, margen_pct=2.0,
               tolerancia_pct=0.5) -> str:
    tolerancia_x = lienzo_ancho * tolerancia_pct / 100
    tolerancia_y = lienzo_alto * tolerancia_pct / 100
    for nombre in ANCLAJES:
        x, y, alineacion = coordenadas(nombre, lienzo_ancho, lienzo_alto, margen_pct)
        esperado = rectangulo(x, y, rect[2], rect[3], alineacion)
        if (abs(rect[0] - esperado[0]) <= tolerancia_x and
                abs(rect[1] - esperado[1]) <= tolerancia_y):
            return nombre
    return ""


@dataclass(frozen=True)
class SnapshotPanel:
    conectado: bool = False
    escena: str = ""
    al_aire: bool = True
    izquierda: float = 0.0
    arriba: float = 0.0
    ancho: int = 0
    alto: int = 0
    lienzo_ancho: int = 0
    lienzo_alto: int = 0
    visible: bool = True
    bloqueada: bool = False
    tapada_por: str = ""
    solapes: tuple = ()
    fuera: float = 0.0
    mensajes_visibles: int = 0
    tamano_letra: int = 0


COMPONENTES = ("conexion", "escena", "posicion", "tamano", "capa",
               "solape", "visible", "bloqueada", "fuera", "aspecto",
               "transparencia")

ACTIVOS_DEFECTO = frozenset({"conexion", "escena", "posicion", "tamano",
                             "capa", "solape", "visible", "bloqueada",
                             "fuera"})


def _porcentaje(valor) -> int:
    return int(round(valor))


def _texto_posicion(snap, largo):
    if not snap.ancho or not snap.alto or not snap.lienzo_ancho or not snap.lienzo_alto:
        return ""
    rect = (snap.izquierda, snap.arriba, snap.ancho, snap.alto)
    nombre = anclaje_de(rect, snap.lienzo_ancho, snap.lienzo_alto)
    if nombre:
        lugares = {
            "superior-izquierda": "esquina superior izquierda",
            "superior-centro": "borde superior, centrado",
            "superior-derecha": "esquina superior derecha",
            "centro-izquierda": "borde izquierdo, centrado",
            "centro": "centro",
            "centro-derecha": "borde derecho, centrado",
            "inferior-izquierda": "esquina inferior izquierda",
            "inferior-centro": "borde inferior, centrado",
            "inferior-derecha": "esquina inferior derecha",
        }
        texto = lugares[nombre]
    else:
        derecha = snap.izquierda + snap.ancho
        abajo = snap.arriba + snap.alto
        if snap.izquierda < 0:
            sale_x = "por la izquierda"
        elif derecha > snap.lienzo_ancho:
            sale_x = "por la derecha"
        else:
            horizontal = [(snap.izquierda, "izquierdo"),
                          (snap.lienzo_ancho - derecha, "derecho")]
            distancia_x, borde_x = min(horizontal)
            sale_x = ""
        if snap.arriba < 0:
            sale_y = "por arriba"
        elif abajo > snap.lienzo_alto:
            sale_y = "por abajo"
        else:
            vertical = [(snap.arriba, "superior"),
                        (snap.lienzo_alto - abajo, "inferior")]
            distancia_y, borde_y = min(vertical)
            sale_y = ""
        salidas = " y ".join(salida for salida in (sale_x, sale_y) if salida)
        distancias = []
        if not sale_x:
            distancias.append(
                f"a {_porcentaje(distancia_x / snap.lienzo_ancho * 100)}% del borde {borde_x}")
        if not sale_y:
            distancias.append(
                f"a {_porcentaje(distancia_y / snap.lienzo_alto * 100)}% del borde {borde_y}")
        texto = (f"se sale del lienzo {salidas}, y " if salidas and distancias
                 else f"se sale del lienzo {salidas}" if salidas
                 else "") + " y ".join(distancias)
    if not largo:
        texto = texto.capitalize()
    return f"Posición: {texto}" if largo else texto


def _render(nombre: str, s: SnapshotPanel, largo: bool) -> str:
    if not s.conectado and nombre != "conexion":
        return ""
    if nombre == "conexion":
        return "OBS: conectado" if largo and s.conectado else ("Sin conexión con OBS" if not s.conectado else "")
    if nombre == "escena":
        if not s.escena:
            return ""
        valor = s.escena + (", no al aire" if not s.al_aire else "")
        return f"Escena: {valor}" if largo else valor
    if nombre == "posicion":
        return _texto_posicion(s, largo)
    if nombre == "tamano":
        if not s.ancho or not s.alto or not s.lienzo_ancho:
            return ""
        porcentaje = _porcentaje(s.ancho / s.lienzo_ancho * 100)
        return (f"Tamaño: {s.ancho} por {s.alto} píxeles, {porcentaje}% del ancho de pantalla"
                if largo else f"{s.ancho} por {s.alto}, {porcentaje}% del ancho")
    if nombre == "capa":
        if not s.tapada_por:
            valor = "no lo tapa nada"
        else:
            valor = f"lo tapa {s.tapada_por}"
        return f"Capa: {valor}" if largo else valor[0].upper() + valor[1:]
    if nombre == "solape":
        if not s.solapes:
            # El modo corto se oye en cada pulsación del ajuste fino.
            return "No se superpone con ninguna otra fuente" if largo else "Libre"
        # El porcentaje de superposición es de la otra fuente; el de recorte, del propio panel.
        partes = [f"al {_porcentaje(porcentaje)}% de {nombre}"
                  for nombre, porcentaje in s.solapes]
        return "Superpone " + " y ".join(partes)
    if nombre == "visible":
        return f"Visible: {'sí' if s.visible else 'no'}" if largo else ("" if s.visible else "Oculto")
    if nombre == "bloqueada":
        return f"Fijado: {'sí' if s.bloqueada else 'no'}" if largo else ("Fijado" if s.bloqueada else "")
    if nombre == "fuera":
        if not s.fuera:
            return ""
        valor = f"queda fuera del lienzo el {_porcentaje(s.fuera)}% del panel"
        return f"Recorte: {valor}" if largo else valor.capitalize()
    if nombre == "aspecto":
        if not s.mensajes_visibles and not s.tamano_letra:
            return ""
        return (f"Aspecto: {s.mensajes_visibles} mensajes visibles, tamaño de letra {s.tamano_letra}"
                if largo else f"{s.mensajes_visibles} mensajes, letra {s.tamano_letra}")
    if nombre == "transparencia":
        return ("El fondo del panel es transparente. Solo se ven las tarjetas de los mensajes, "
                "apiladas contra el borde inferior." if largo else "")
    return ""


def describir(snap: SnapshotPanel, componentes, modo="corto") -> str:
    partes = []
    for nombre in COMPONENTES:
        if nombre in componentes:
            texto = _render(nombre, snap, modo == "largo")
            if texto:
                partes.append(texto)
    if not partes:
        return ""
    return "\n".join(partes) if modo == "largo" else "; ".join(partes) + "."


def describir_fuente(nombre, snap, componentes, modo="corto") -> str:
    texto = describir(snap, componentes, modo)
    if not nombre:
        return texto
    if modo == "largo":
        return f"Fuente: {nombre}" + (f"\n{texto}" if texto else "")
    return f"{nombre}." + (f" {texto}" if texto else "")


def describir_preparacion(obs_responde, panel_encendido, puerto, fuente_en_escena):
    if not obs_responde:
        return ("OBS no responde. En OBS, menú Herramientas, Configuración del "
                "servidor WebSocket, activa el servidor.")
    if panel_encendido and fuente_en_escena:
        return (f"Panel de chat encendido en el puerto {puerto}. "
                "La fuente está en esta escena.")
    partes = []
    if not panel_encendido:
        partes.append("El panel de chat está apagado.")
    if not fuente_en_escena:
        partes.append("La fuente no está en esta escena.")
    return "Falta preparar el panel. " + " ".join(partes)
