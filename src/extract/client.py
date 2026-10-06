#cliente http resiliente para la api de steamworks (criterio f1-05)
#soporta backoff exponencial, respeto de Retry-After e inyeccion de pausas
import time
from typing import Any, Callable, Optional

import requests


class SteamClientError(Exception):
    """error base para fallas del cliente steam."""


class SteamAppNotFoundError(SteamClientError):
    """appid no encontrado o respuesta con success false."""


class SteamRateLimitError(SteamClientError):
    """tasa de peticiones excedida tras agotar reintentos (429)."""


class SteamServerError(SteamClientError):
    """error interno del servidor de steam (5xx)."""


class SteamNetworkError(SteamClientError):
    """error de conexion a nivel de red."""


class SteamClient:
    """cliente http para consultar metadatos y resenas de steam."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        base_url_store: str = "https://store.steampowered.com/api",
        country_code: str = "US",
        language: str = "english",
    ) -> None:
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.sleep_fn = sleep_fn
        self.base_url_store = base_url_store.rstrip("/")
        self.country_code = country_code
        self.language = language

    def _ejecutar_solicitud(self, url: str) -> dict[str, Any]:
        """ejecutar peticion get con manejo de reintentos y 429."""
        intento = 0
        while True:
            try:
                respuesta = self.session.get(url, timeout=30)
            except requests.exceptions.RequestException as exc:
                raise SteamNetworkError(f"fallo de red al conectar con steam: {exc}") from exc

            if respuesta.status_code == 200:
                try:
                    return respuesta.json()
                except Exception as exc:
                    raise SteamServerError(f"respuesta json no valida de steam: {exc}") from exc

            if respuesta.status_code == 429:
                if intento >= self.max_retries:
                    raise SteamRateLimitError(
                        "tasa de peticiones excedida: limite 429 alcanzado tras reintentos"
                    )

                cabecera_retry = respuesta.headers.get("Retry-After")
                if cabecera_retry:
                    try:
                        pausa = float(cabecera_retry)
                    except ValueError:
                        pausa = self.backoff_factor * (2**intento)
                else:
                    pausa = self.backoff_factor * (2**intento)

                self.sleep_fn(pausa)
                intento += 1
                continue

            if respuesta.status_code >= 500:
                raise SteamServerError(
                    f"error de servidor de steam: codigo {respuesta.status_code}"
                )

            raise SteamClientError(
                f"error http inesperado de steam: codigo {respuesta.status_code}"
            )

    def get_app_details(self, appid: int) -> dict[str, Any]:
        """obtener detalle crudo de aplicacion desde steam store api."""
        url = (
            f"{self.base_url_store}/appdetails"
            f"?appids={appid}&cc={self.country_code}&l={self.language}"
        )
        datos = self._ejecutar_solicitud(url)
        appid_str = str(appid)
        if appid_str not in datos or not datos[appid_str].get("success", False):
            raise SteamAppNotFoundError(f"appid {appid} no encontrado o success es false")
        return datos

    def get_app_reviews_summary(self, appid: int) -> dict[str, Any]:
        """obtener resumen de resenas de aplicacion desde steam store api."""
        url = (
            f"https://store.steampowered.com/appreviews/{appid}"
            f"?json=1&language={self.language}&purchase_type=all&num_per_page=0"
        )
        return self._ejecutar_solicitud(url)
