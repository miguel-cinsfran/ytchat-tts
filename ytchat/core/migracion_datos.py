"""Muda los datos de usuario de la raíz a la subcarpeta de datos.

Módulo puro, sin wx y sin logging propio: recibe todas las rutas por
parámetro y nunca arma una por su cuenta. No lanza nunca: cada fallo se
anota en el resultado y se sigue con el elemento siguiente.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ResultadoMigracion:
    """Lo que hizo un llamado a migrar, en nombres de archivo."""

    movidos: list[str] = field(default_factory=list)
    copiados: list[str] = field(default_factory=list)
    conflictos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


def _trasladar(vieja: Path, nueva: Path, datos: Path,
               resultado: ResultadoMigracion) -> None:
    """Aplica las reglas a un solo elemento, sin lanzar."""
    try:
        if vieja == nueva:
            return
        if not vieja.exists() and not vieja.is_symlink():
            return
        if nueva.exists() or nueva.is_symlink():
            resultado.conflictos.append(nueva.name)
            return
        try:
            datos.mkdir(parents=True, exist_ok=True)
            nueva.parent.mkdir(parents=True, exist_ok=True)
            os.replace(vieja, nueva)
            resultado.movidos.append(nueva.name)
        except OSError:
            try:
                if vieja.is_dir() and not vieja.is_file():
                    shutil.copytree(vieja, nueva)
                else:
                    shutil.copy2(vieja, nueva)
                resultado.copiados.append(nueva.name)
            except Exception as exc_copia:
                resultado.errores.append(f"{nueva.name}: {exc_copia}")
    except Exception as exc:
        resultado.errores.append(f"{nueva.name}: {exc}")


def _rotados_de(vieja: Path, datos: Path) -> list[tuple[Path, Path]]:
    """Rotados que acompañan a un archivo, como pares vieja y nueva."""
    hallados: list[tuple[Path, Path]] = []
    try:
        padre = vieja.parent
        if not padre.is_dir():
            return hallados
        prefijo = vieja.name + "."
        for hijo in sorted(padre.iterdir()):
            if hijo == vieja or not hijo.is_file():
                continue
            if not hijo.name.startswith(prefijo):
                continue
            resto = hijo.name[len(prefijo):]
            if resto.isdigit():
                hallados.append((hijo, datos / hijo.name))
    except OSError:
        pass
    return hallados


def migrar(instalacion: Path, datos: Path, rutas: list[Path],
           sounds_ini: Path) -> ResultadoMigracion:
    """Mueve cada ruta desde la raíz hasta la carpeta de datos.

    Para cada archivo también se migran sus rotados, que llevan el mismo
    nombre con punto y dígitos al final. Si el destino ya existe no se
    toca nada y se anota el conflicto. Si el movimiento falla se intenta
    la copia y la vieja se deja donde está. La plantilla de sonidos de la
    raíz solo se copia, nunca se mueve.
    """
    resultado = ResultadoMigracion()
    instalacion = Path(instalacion)
    datos = Path(datos)
    for ruta in rutas:
        try:
            nueva = Path(ruta)
            try:
                vieja = instalacion / nueva.relative_to(datos)
            except ValueError as exc:
                resultado.errores.append(f"{nueva.name}: {exc}")
                continue
            _trasladar(vieja, nueva, datos, resultado)
            for vieja_rot, nueva_rot in _rotados_de(vieja, datos):
                _trasladar(vieja_rot, nueva_rot, datos, resultado)
        except Exception as exc:
            try:
                resultado.errores.append(f"{Path(ruta).name}: {exc}")
            except Exception:
                pass
    try:
        destino_sonidos = Path(sounds_ini)
        vieja_sonidos = instalacion / destino_sonidos.name
        if vieja_sonidos == destino_sonidos:
            return resultado
        if destino_sonidos.exists() or destino_sonidos.is_symlink():
            return resultado
        if vieja_sonidos.is_file():
            try:
                datos.mkdir(parents=True, exist_ok=True)
                destino_sonidos.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(vieja_sonidos, destino_sonidos)
                resultado.copiados.append(destino_sonidos.name)
            except Exception as exc:
                resultado.errores.append(f"{destino_sonidos.name}: {exc}")
    except Exception as exc:
        try:
            resultado.errores.append(f"{Path(sounds_ini).name}: {exc}")
        except Exception:
            pass
    return resultado
