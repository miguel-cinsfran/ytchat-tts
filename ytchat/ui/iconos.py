"""Iconos vectoriales del reproductor, dibujados con wxPython.

Se generan en memoria (sin recursos externos) y se ponen en botones con
`SetBitmap`. Los botones conservan su nombre accesible y tooltip, así que el
lector de pantalla sigue diciendo la acción, no «botón» a secas.
"""

from __future__ import annotations

import wx


def _play(gc, s):
    p = s * 0.24
    path = gc.CreatePath()
    path.MoveToPoint(p, p * 0.85)
    path.AddLineToPoint(p, s - p * 0.85)
    path.AddLineToPoint(s - p * 0.7, s / 2)
    path.CloseSubpath()
    gc.FillPath(path)


def _pause(gc, s):
    w, gap = s * 0.16, s * 0.14
    y0, y1 = s * 0.24, s * 0.76
    gc.DrawRectangle(s / 2 - gap / 2 - w, y0, w, y1 - y0)
    gc.DrawRectangle(s / 2 + gap / 2, y0, w, y1 - y0)


def _stop(gc, s):
    a = s * 0.28
    gc.DrawRectangle(a, a, s - 2 * a, s - 2 * a)


def _tri_izq(gc, s, x0, x1):
    path = gc.CreatePath()
    path.MoveToPoint(x1, s * 0.26)
    path.AddLineToPoint(x0, s / 2)
    path.AddLineToPoint(x1, s * 0.74)
    path.CloseSubpath()
    gc.FillPath(path)


def _tri_der(gc, s, x0, x1):
    path = gc.CreatePath()
    path.MoveToPoint(x0, s * 0.26)
    path.AddLineToPoint(x1, s / 2)
    path.AddLineToPoint(x0, s * 0.74)
    path.CloseSubpath()
    gc.FillPath(path)


def _retro(gc, s):
    _tri_izq(gc, s, s * 0.20, s * 0.50)
    _tri_izq(gc, s, s * 0.50, s * 0.80)


def _avanz(gc, s):
    _tri_der(gc, s, s * 0.20, s * 0.50)
    _tri_der(gc, s, s * 0.50, s * 0.80)


def _altavoz(gc, s):
    mw, mh = s * 0.15, s * 0.26
    mx, my = s * 0.16, s / 2 - mh / 2
    gc.DrawRectangle(mx, my, mw, mh)
    cr = mx + mw + s * 0.20
    path = gc.CreatePath()
    path.MoveToPoint(mx + mw, my)
    path.AddLineToPoint(cr, s * 0.20)
    path.AddLineToPoint(cr, s * 0.80)
    path.AddLineToPoint(mx + mw, my + mh)
    path.CloseSubpath()
    gc.FillPath(path)
    return cr


def _mute(gc, s):
    cr = _altavoz(gc, s)
    x0 = cr + s * 0.10
    gc.StrokeLine(x0, s * 0.36, x0 + s * 0.22, s * 0.64)
    gc.StrokeLine(x0, s * 0.64, x0 + s * 0.22, s * 0.36)


def _sound(gc, s):
    cr = _altavoz(gc, s)
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    for r in (s * 0.13, s * 0.24):
        path = gc.CreatePath()
        path.AddArc(cr - s * 0.02, s / 2, r, -0.7, 0.7, True)
        gc.StrokePath(path)


def _fullscreen(gc, s):
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    p, L = s * 0.22, s * 0.22
    for (cx, cy, dx, dy) in ((p, p, 1, 1), (s - p, p, -1, 1),
                             (p, s - p, 1, -1), (s - p, s - p, -1, -1)):
        gc.StrokeLine(cx, cy, cx + dx * L, cy)
        gc.StrokeLine(cx, cy, cx, cy + dy * L)


_DIBUJOS = {
    "play": _play, "pause": _pause, "stop": _stop, "retro": _retro,
    "avanz": _avanz, "mute": _mute, "sound": _sound, "fullscreen": _fullscreen,
}


def icono(nombre, color: wx.Colour, fondo: wx.Colour, lado: int = 18) -> wx.Bitmap:
    """Devuelve un wx.Bitmap del icono `nombre` dibujado en `color` sobre `fondo`."""
    bmp = wx.Bitmap(lado, lado, 24)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(fondo))
    dc.Clear()
    gc = wx.GraphicsContext.Create(dc)
    gc.SetBrush(wx.Brush(color))
    gc.SetPen(wx.Pen(color, max(2, round(lado * 0.11))))
    dibujo = _DIBUJOS.get(nombre)
    if dibujo:
        dibujo(gc, lado)
    dc.SelectObject(wx.NullBitmap)
    return bmp
