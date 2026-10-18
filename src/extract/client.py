#cliente http resiliente para la api de steamworks (criterio f1-05)
#soporta backoff exponencial, respeto de Retry-After e inyeccion de pausas
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import requests


class SteamClientError(Exception):
    """Error base para fallas del cliente steam."""


class SteamAppNotFoundError(SteamClientError):
    """Appid no encontrado o respuesta con success false."""


class SteamRateLimitError(SteamClientError):
    """Tasa de peticiones excedida tras agotar reintentos (429)."""


class SteamServerError(SteamClientError):
    """Error interno del servidor de steam (5xx)."""


class SteamNetworkError(SteamClientError):
    """Error de conexion a nivel de red."""


class SteamClient:
    """Cliente http para consultar metadatos y resenas de steam."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        base_url_store: str = "https://store.steampowered.com/api",
        base_url_api: str = "https://api.steampowered.com",
        country_code: str = "US",
        language: str = "english",
        ruta_env: Optional[Path] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else self._resolver_api_key(ruta_env)
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.sleep_fn = sleep_fn
        self.base_url_store = base_url_store.rstrip("/")
        self.base_url_api = base_url_api.rstrip("/")
        self.country_code = country_code
        self.language = language
        self.rate_limit_hits_429: int = 0
        self.network_retry_count: int = 0
        self.total_requests: int = 0

    @staticmethod
    def _resolver_api_key(ruta_env: Optional[Path] = None) -> Optional[str]:
        """Resolver la clave de steamworks desde entorno o archivo .env."""
        #1. variable de entorno activa en el sistema
        clave_env = os.getenv("STEAM_API_KEY")
        if clave_env:
            return clave_env

        #2. si python-dotenv esta disponible, intentar cargarlo
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=ruta_env)
            clave_cargada = os.getenv("STEAM_API_KEY")
            if clave_cargada:
                return clave_cargada
        except ImportError:
            pass

        #3. lectura directa de archivo .env como fallback
        posibles_rutas = [
            ruta_env,
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]
        for ruta in posibles_rutas:
            if ruta is not None and ruta.is_file():
                try:
                    for linea in ruta.read_text(encoding="utf-8").splitlines():
                        linea = linea.strip()
                        if not linea or linea.startswith("#"):
                            continue
                        if "=" in linea:
                            clave, valor = linea.split("=", 1)
                            clave = clave.strip()
                            valor = valor.strip().strip("'\"")
                            if clave == "STEAM_API_KEY" and valor:
                                return valor
                except Exception:
                    pass
        return None

    def _ejecutar_solicitud(self, url: str) -> dict[str, Any]:
        """Ejecutar peticion get con manejo de reintentos y 429."""
        intento = 0
        while True:
            self.total_requests += 1
            try:
                respuesta = self.session.get(url, timeout=30)
            except requests.exceptions.RequestException as exc:
                self.network_retry_count += 1
                raise SteamNetworkError(f"Fallo de red al conectar con steam: {exc}") from exc

            if respuesta.status_code == 200:
                try:
                    return respuesta.json()
                except Exception as exc:
                    raise SteamServerError(f"Respuesta json no valida de steam: {exc}") from exc

            if respuesta.status_code == 429:
                self.rate_limit_hits_429 += 1
                self.network_retry_count += 1
                if intento >= self.max_retries:
                    raise SteamRateLimitError(
                        "Tasa de peticiones excedida: limite 429 alcanzado tras reintentos"
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
                    f"Error de servidor de steam: codigo {respuesta.status_code}"
                )

            raise SteamClientError(
                f"Error http inesperado de steam: codigo {respuesta.status_code}"
            )

    def get_app_details(self, appid: int) -> dict[str, Any]:
        """Obtener detalle crudo de aplicacion desde steam store api."""
        url = (
            f"{self.base_url_store}/appdetails"
            f"?appids={appid}&cc={self.country_code}&l={self.language}"
        )
        datos = self._ejecutar_solicitud(url)
        appid_str = str(appid)
        if appid_str not in datos or not datos[appid_str].get("success", False):
            raise SteamAppNotFoundError(f"Appid {appid} no encontrado o success es false")
        return datos

    def get_app_reviews_summary(self, appid: int) -> dict[str, Any]:
        """Obtener resumen de resenas de aplicacion desde steam store api."""
        url = (
            f"https://store.steampowered.com/appreviews/{appid}"
            f"?json=1&language={self.language}&purchase_type=all&num_per_page=0"
        )
        return self._ejecutar_solicitud(url)

    def get_app_list_batch(
        self,
        last_appid: int = 0,
        max_results: int = 50000,
        include_games: bool = True,
        include_dlc: bool = False,
        include_software: bool = False,
    ) -> dict[str, Any]:
        """Consultar lote de catalogo mediante el servicio oficial IStoreService."""
        clave = self.api_key
        if not clave:
            raise SteamClientError("Se requiere api_key para consultar IStoreService/GetAppList")

        url = (
            f"{self.base_url_api}/IStoreService/GetAppList/v1/"
            f"?key={clave}&last_appid={last_appid}&max_results={max_results}"
            f"&include_games={'true' if include_games else 'false'}"
            f"&include_dlc={'true' if include_dlc else 'false'}"
            f"&include_software={'true' if include_software else 'false'}"
        )
        return self._ejecutar_solicitud(url)

    def iterar_catalogo_completo(
        self,
        max_total: Optional[int] = None,
        batch_size: int = 50000,
        include_games: bool = True,
        include_dlc: bool = False,
        include_software: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Iterar de forma paginada y perezosa sobre todo el catalogo disponible."""
        last_appid = 0
        entregados = 0
        while True:
            limite_batch = batch_size
            if max_total is not None:
                restantes = max_total - entregados
                if restantes <= 0:
                    break
                if restantes < batch_size:
                    limite_batch = restantes

            datos = self.get_app_list_batch(
                last_appid=last_appid,
                max_results=limite_batch,
                include_games=include_games,
                include_dlc=include_dlc,
                include_software=include_software,
            )

            respuesta = datos.get("response", {})
            apps = respuesta.get("apps", [])
            if not apps:
                break

            for app in apps:
                yield app
                entregados += 1
                if max_total is not None and entregados >= max_total:
                    return

            have_more = respuesta.get("have_more_results", False)
            last_appid = respuesta.get("last_appid", last_appid)
            if not have_more or not last_appid:
                break


