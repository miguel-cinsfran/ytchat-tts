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
    python qa/conducir.py --escenario dos_conexiones

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

`dos_conexiones` también toca la red, aunque no se llame así, y merece un
párrafo porque es el único que mide un defecto en vez de un anuncio.

Comprueba que conectar dos veces sin desconectar no deja el hilo de captura
viejo girando. El camino no es evidente: el botón alterna, así que estando
conectado no se puede conectar otra vez. Lo que lo abre es un error de red, que
llama a `set_conectado(False)` y rehabilita el botón mientras el hilo sigue
vivo reintentando. El escenario provoca eso a propósito llamando a
`set_conectado(False)` en medio.

Mide hilos vivos, no anuncios, así que se prueba mutando el arreglo: quitar el
`set()` de `sesiones.abrir()` tiene que hacerlo decir «quedaron 2 hilos de
captura vivos tras 45 s (Chat, Chat)». Si sigue en verde, el instrumento se
rompió. Ojo con eso: la primera versión leía mal el sobre de la sonda, contaba
cero hilos siempre y habría pasado en verde para siempre.

Los escenarios que terminan en `directo_` son los únicos que tocan la red. No
entran en la corrida completa: gastan minutos y dependen de que haya alguien
emitiendo en ese momento.

## Cuatro trampas que costaron una tarde

Están escritas acá porque hicieron que el banco diera por roto algo que
funcionaba, o peor, por bueno algo que nunca miró. Todas son fáciles de volver
a pisar.

**Un ALT sintético para traer la ventana al frente abre la barra de menú**, y a
partir de ahí los aceleradores dejan de llegar. El banco declaró roto un Ctrl+S
que funcionaba: la herramienta rompía lo que estaba midiendo.

**Con el dueño lejos del equipo, el banco NO puede medir nada del teclado.**
Medido el 27/08/2026 con una ventana wx mínima que se manda una tecla a sí
misma: la ventana estaba activa según wx, el foco estaba en su cuadro de texto,
y las teclas simuladas no llegaron. Este es el veredicto textual del
experimento: «las teclas simuladas NO llegan a la ventana».

Cuando pasa eso, TODA comprobación que use `teclas` falla a la vez: los siete
atajos del reproductor, las flechas de los deslizadores, `F2`, `Ctrl+S`. Una
corrida así dio 23 fallos donde la línea base tenía 2, y ninguno era una
regresión.

La señal para reconocerlo, y es la misma de siempre: **fallan todas las
comprobaciones de una clase y ninguna de otra**. Lo que se dispara llamando a
wx directamente sigue en verde; lo que pasa por el teclado del sistema falla
entero. Antes de creerse una lista de fallos así, correr el experimento de la
ventana mínima.

Consecuencia práctica: el banco completo se corre con alguien delante del
equipo. En sesión remota o con la pantalla bloqueada sirve para los escenarios
que no dependen del teclado, y nada más.

**El recorrido de Tab no auditaba nada, y lo dijo en verde durante meses.**
Mandaba la tecla con `wx.UIActionSimulator`, que la entrega a la ventana con el
foco DEL ESCRITORIO. Corriendo el banco sin traer la aplicación al frente, esa
ventana era otra: el foco no se movía y todos los diálogos daban «1 parada».
Estaba a la vista en cada informe, pero era una nota sin umbral, y una nota que
nadie compara con nada no es una medición.

Ahora `recorrer_tab` usa la orden `navegar` de la sonda, que avanza por la
cadena de foco de wx con `Navigate()`, sin pasar por el sistema. El diálogo de
Transmisión pasó de 1 parada a 16. Lo que se gana es medir el orden real; lo
que NO se cubre es el camino del teclado del sistema operativo hasta la
ventana, y conviene no confundir una cosa con la otra.

Si mañana una comprobación de Tab falla, antes de tocar el diálogo corré otro
que ya sepas bueno. Si también falla, el roto es el instrumento.

**`Desktop().windows()` de pywinauto no devuelve los diálogos modales.** Desde
fuera parece que el diálogo no se abrió. Desde dentro, `wx.GetTopLevelWindows()`
sí los ve.

**Comparar el árbol de wx entero contra lo que expone Windows da una diferencia
enorme y falsa** cuando hay pestañas: una que no está seleccionada esconde a sus
hijos y el servicio de accesibilidad no los expone. Hay que mirar solo lo que
está en pantalla, con `IsShownOnScreen`.

**El smoke test y el banco no se pueden correr pegados.** La fase 3 de
`smoke_test.py` levanta la aplicación con pywinauto, y si queda un proceso vivo
cuando arranca el banco, su ventana se lleva el foco. El 21/08/2026 eso produjo
diecisiete fallos de golpe: los once de teclado, dos aceleradores, y un
escenario reventado con «la ventana no está al frente». Con la mesa limpia, la
misma corrida dio cinco fallos, que son los conocidos.

La firma es inconfundible: **fallan a la vez todas las comprobaciones que
teclean, y ninguna de las que no**. Antes de creerse eso, cerrar los procesos
de Python que estén corriendo la aplicación y repetir.

Y la regla que sale de las cuatro: cuando el instrumento y el código no
coinciden, mirar primero el instrumento.

## Lo que esto no prueba

No prueba que NVDA lo lea, ni cómo suena, ni la línea braille. Que un control
tenga nombre no quiere decir que se anuncie bien. Eso lo comprueba una persona
con el lector puesto, y no hay forma de automatizarlo desde acá.
