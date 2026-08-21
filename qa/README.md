# Banco de pruebas de accesibilidad

Maneja la aplicación como si fuera una persona y anota qué le diría a un lector
de pantalla, sin decirlo en voz alta.

No sustituye a `python -m unittest discover -s tests`, que prueba la lógica, ni
a `smoke_test.py`, que comprueba que todo importa y que ningún control se quede
sin nombre. Esto es otra cosa: abre ventanas, pulsa teclas, escribe en campos y
mira qué pasa.

## Cómo se usa

    python qa/conducir.py                          # todos los escenarios
    python qa/conducir.py --escenario descargas    # solo uno
    python qa/conducir.py --escenario directo_youtube --url-youtube URL

Arranca la aplicación de verdad, así que hace falta Windows con wxPython. La
ventana aparece y se mueve sola durante la corrida.

Las grabaciones quedan en `qa/salida/`, que está en el `.gitignore`: llevan la
salida cruda de la aplicación, con el identificador del vídeo que se estuvo
viendo.

## Cómo funciona

Son dos piezas.

`sonda.py` se instala **dentro** del proceso de la aplicación, antes de que
arranque. Sustituye el objeto por el que `gui.anunciar` habla con el lector, así
que la aplicación recorre su código de verdad pero en vez de hablar escribe una
línea por anuncio. Además atiende órdenes por archivos de líneas JSON y las
ejecuta en el hilo de interfaz.

`conducir.py` es quien manda las órdenes y juzga lo que vuelve. Cada escenario
es una función que abre algo, lo recorre con Tab, y comprueba una cosa concreta.

Los escenarios que terminan en `directo_` son los únicos que tocan la red. No
entran en la corrida completa: gastan minutos y dependen de que haya alguien
emitiendo en ese momento.

## Tres trampas que costaron una tarde

Están escritas acá porque las tres hicieron que el banco diera por roto algo que
funcionaba, y las tres son fáciles de volver a pisar.

**Un ALT sintético para traer la ventana al frente abre la barra de menú**, y a
partir de ahí los aceleradores dejan de llegar. El banco declaró roto un Ctrl+S
que funcionaba: la herramienta rompía lo que estaba midiendo.

**`Desktop().windows()` de pywinauto no devuelve los diálogos modales.** Desde
fuera parece que el diálogo no se abrió. Desde dentro, `wx.GetTopLevelWindows()`
sí los ve.

**Comparar el árbol de wx entero contra lo que expone Windows da una diferencia
enorme y falsa** cuando hay pestañas: una que no está seleccionada esconde a sus
hijos y el servicio de accesibilidad no los expone. Hay que mirar solo lo que
está en pantalla, con `IsShownOnScreen`.

Y la regla que sale de las tres: cuando el instrumento y el código no coinciden,
mirar primero el instrumento.

## Lo que esto no prueba

No prueba que NVDA lo lea, ni cómo suena, ni la línea braille. Que un control
tenga nombre no quiere decir que se anuncie bien. Eso lo comprueba una persona
con el lector puesto, y no hay forma de automatizarlo desde acá.
