"""
API-Aufruf-Wiederholungsmechanismus
Zum Behandeln der Wiederholungslogik bei LLM- und anderen externen API-Aufrufen
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('mirofish.retry')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Wiederholungsdekorator mit exponentiellem Rueckzug

    Args:
        max_retries: Maximale Anzahl von Wiederholungsversuchen
        initial_delay: Anfangsverzoegerung (Sekunden)
        max_delay: Maximale Verzoegerung (Sekunden)
        backoff_factor: Rueckzugsfaktor
        jitter: Ob zufaelliges Rauschen hinzugefuegt werden soll
        exceptions: Ausnahmetypen, die wiederholt werden sollen
        on_retry: Rueckruffunktion bei Wiederholung (exception, retry_count)

    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(f"Funktion {func.__name__} nach {max_retries} Wiederholungsversuchen immer noch fehlgeschlagen: {str(e)}")
                        raise

                    # Verzoegerung berechnen
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())

                    logger.warning(
                        f"Funktion {func.__name__} Versuch {attempt + 1} fehlgeschlagen: {str(e)}, "
                        f"Wiederholung in {current_delay:.1f} Sekunden..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    time.sleep(current_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Asynchrone Version des Wiederholungsdekorators
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(f"Asynchrone Funktion {func.__name__} nach {max_retries} Wiederholungsversuchen immer noch fehlgeschlagen: {str(e)}")
                        raise

                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())

                    logger.warning(
                        f"Asynchrone Funktion {func.__name__} Versuch {attempt + 1} fehlgeschlagen: {str(e)}, "
                        f"Wiederholung in {current_delay:.1f} Sekunden..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


class RetryableAPIClient:
    """
    API-Client-Kapselung mit Wiederholungsversuchen
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        Funktionsaufruf ausfuehren und bei Fehler wiederholen

        Args:
            func: Aufzurufende Funktion
            *args: Funktionsargumente
            exceptions: Ausnahmetypen, die wiederholt werden sollen
            **kwargs: Funktions-Schluesselwortargumente

        Returns:
            Funktionsrueckgabewert
        """
        last_exception = None
        delay = self.initial_delay

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except exceptions as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(f"API-Aufruf nach {self.max_retries} Wiederholungsversuchen immer noch fehlgeschlagen: {str(e)}")
                    raise

                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())

                logger.warning(
                    f"API-Aufruf Versuch {attempt + 1} fehlgeschlagen: {str(e)}, "
                    f"Wiederholung in {current_delay:.1f} Sekunden..."
                )

                time.sleep(current_delay)
                delay *= self.backoff_factor

        raise last_exception

    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """
        Stapelverarbeitung mit individuellen Wiederholungsversuchen bei Fehlern

        Args:
            items: Liste der zu verarbeitenden Elemente
            process_func: Verarbeitungsfunktion, empfaengt ein einzelnes Element als Argument
            exceptions: Ausnahmetypen, die wiederholt werden sollen
            continue_on_failure: Ob nach Einzelelementfehler mit anderen Elementen fortgefahren werden soll

        Returns:
            (Liste erfolgreicher Ergebnisse, Liste fehlgeschlagener Elemente)
        """
        results = []
        failures = []

        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Verarbeitung von Element {idx + 1} fehlgeschlagen: {str(e)}")
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })

                if not continue_on_failure:
                    raise

        return results, failures
