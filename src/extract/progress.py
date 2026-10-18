#modulo de renderizado de barra de progreso visual en consola para ingesta masiva
#soporta calculo dinamico de eta, actualizacion en linea con \r y tolerancia a codificaciones cp1252/ascii
import sys
import time
from typing import Optional, TextIO


def formatear_tiempo_estimado(segundos: float) -> str:
    """Formatear una duracion en segundos a representacion legible (ej. 45s, 2m 15s, 1h 05m)."""
    seg = max(0, int(segundos))
    if seg == 0:
        return "0s"
    if seg < 60:
        return f"{seg}s"
    if seg < 3600:
        minutos = seg // 60
        restante = seg % 60
        return f"{minutos}m {restante:02d}s"
    horas = seg // 3600
    minutos = (seg % 3600) // 60
    return f"{horas}h {minutos:02d}m"


class BarraProgreso:
    """Barra de progreso visual en consola con bloques y metadatos de rendimiento."""

    def __init__(
        self,
        total: int,
        ancho: int = 25,
        stream: Optional[TextIO] = None,
        habilitado: bool = True,
    ) -> None:
        self.total = max(1, total)
        self.ancho = ancho
        self.stream = stream or sys.stdout
        self.habilitado = habilitado
        self.tiempo_inicio = time.time()
        self._ultimo_render = 0.0
        self._char_lleno = "\u2588"
        self._char_vacio = "\u2591"

    def actualizar(
        self,
        actual: int,
        appid: Optional[int] = None,
        exitosos: int = 0,
        fallidos: int = 0,
        forzar: bool = False,
    ) -> None:
        """Actualizar y renderizar el estado actual de la barra en una unica linea."""
        if not self.habilitado:
            return

        ahora = time.time()
        #limitar frecuencia de renderizado a maximo 10 fps excepto en eventos forzados o finalizacion
        if not forzar and actual < self.total and (ahora - self._ultimo_render) < 0.1:
            return

        self._ultimo_render = ahora
        fraccion = min(1.0, max(0.0, actual / self.total))
        pct = fraccion * 100.0

        bloques = int(fraccion * self.ancho)
        vacios = self.ancho - bloques

        #calculo de eta basado en items procesados y tiempo transcurrido
        transcurrido = ahora - self.tiempo_inicio
        if actual > 0 and transcurrido > 0:
            tasa = actual / transcurrido
            restantes = max(0, self.total - actual)
            eta_texto = formatear_tiempo_estimado(restantes / tasa)
        else:
            eta_texto = "--"

        appid_str = str(appid) if appid is not None else "-"

        linea = self._construir_linea(
            bloques=bloques,
            vacios=vacios,
            pct=pct,
            actual=actual,
            exitosos=exitosos,
            fallidos=fallidos,
            appid_str=appid_str,
            eta_texto=eta_texto,
            char_lleno=self._char_lleno,
            char_vacio=self._char_vacio,
        )

        try:
            self.stream.write(linea)
            self.stream.flush()
        except UnicodeEncodeError:
            #conmutar a caracteres ascii compatibles con consolas heredadas
            self._char_lleno = "="
            self._char_vacio = "-"
            linea_ascii = self._construir_linea(
                bloques=bloques,
                vacios=vacios,
                pct=pct,
                actual=actual,
                exitosos=exitosos,
                fallidos=fallidos,
                appid_str=appid_str,
                eta_texto=eta_texto,
                char_lleno=self._char_lleno,
                char_vacio=self._char_vacio,
            )
            self.stream.write(linea_ascii)
            self.stream.flush()

    def _construir_linea(
        self,
        bloques: int,
        vacios: int,
        pct: float,
        actual: int,
        exitosos: int,
        fallidos: int,
        appid_str: str,
        eta_texto: str,
        char_lleno: str,
        char_vacio: str,
    ) -> str:
        barra = (char_lleno * bloques) + (char_vacio * vacios)
        return (
            f"\r[{barra}] {pct:5.1f}% ({actual}/{self.total}) | "
            f"Exito: {exitosos} | Fallo: {fallidos} | "
            f"AppID: {appid_str} | ETA: {eta_texto}  "
        )

    def cerrar(self) -> None:
        """Finalizar la emision de la barra con un salto de linea para preservar la salida."""
        if not self.habilitado:
            return
        try:
            self.stream.write("\n")
            self.stream.flush()
        except Exception:
            pass
