"""Zep-Graph-Paginierungswerkzeug.

Die Knoten-/Kanten-Listenschnittstellen von Zep verwenden UUID-Cursor-Paginierung.
Dieses Modul kapselt die automatische Seitenumblatterlogik (mit Einzelseiten-Wiederholungsversuchen)
und gibt der aufrufenden Seite transparent die vollstaendige Liste zurueck.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from zep_cloud import InternalServerError
from zep_cloud.client import Zep

from .logger import get_logger

logger = get_logger('mirofish.zep_paging')

_DEFAULT_PAGE_SIZE = 100
_MAX_NODES = 2000
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 2.0  # Sekunden, verdoppelt sich bei jedem Wiederholungsversuch


def _fetch_page_with_retry(
    api_call: Callable[..., list[Any]],
    *args: Any,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay: float = _DEFAULT_RETRY_DELAY,
    page_description: str = "page",
    **kwargs: Any,
) -> list[Any]:
    """Einzelseitenanfrage, bei Fehler exponentieller Rueckzug mit Wiederholungsversuch. Nur transiente Netzwerk-/IO-Fehler werden wiederholt."""
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    last_exception: Exception | None = None
    delay = retry_delay

    for attempt in range(max_retries):
        try:
            return api_call(*args, **kwargs)
        except (ConnectionError, TimeoutError, OSError, InternalServerError) as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"Zep {page_description} Versuch {attempt + 1} fehlgeschlagen: {str(e)[:100]}, Wiederholung in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= 2
            else:
                logger.error(f"Zep {page_description} nach {max_retries} Versuchen fehlgeschlagen: {str(e)}")

    assert last_exception is not None
    raise last_exception


def fetch_all_nodes(
    client: Zep,
    graph_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_NODES,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay: float = _DEFAULT_RETRY_DELAY,
) -> list[Any]:
    """Graphknoten seitenweise abrufen, maximal max_items Eintraege (Standard 2000). Jede Seitenanfrage hat eingebaute Wiederholungsversuche."""
    all_nodes: list[Any] = []
    cursor: str | None = None
    page_num = 0

    while True:
        kwargs: dict[str, Any] = {"limit": page_size}
        if cursor is not None:
            kwargs["uuid_cursor"] = cursor

        page_num += 1
        batch = _fetch_page_with_retry(
            client.graph.node.get_by_graph_id,
            graph_id,
            max_retries=max_retries,
            retry_delay=retry_delay,
            page_description=f"Knoten abrufen Seite {page_num} (graph={graph_id})",
            **kwargs,
        )
        if not batch:
            break

        all_nodes.extend(batch)
        if len(all_nodes) >= max_items:
            all_nodes = all_nodes[:max_items]
            logger.warning(f"Knotenanzahl hat Limit erreicht ({max_items}), Paginierung fuer Graph {graph_id} wird gestoppt")
            break
        if len(batch) < page_size:
            break

        cursor = getattr(batch[-1], "uuid_", None) or getattr(batch[-1], "uuid", None)
        if cursor is None:
            logger.warning(f"Knoten hat kein uuid-Feld, Paginierung wird bei {len(all_nodes)} Knoten gestoppt")
            break

    return all_nodes


def fetch_all_edges(
    client: Zep,
    graph_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay: float = _DEFAULT_RETRY_DELAY,
) -> list[Any]:
    """Alle Graphkanten seitenweise abrufen, vollstaendige Liste zurueckgeben. Jede Seitenanfrage hat eingebaute Wiederholungsversuche."""
    all_edges: list[Any] = []
    cursor: str | None = None
    page_num = 0

    while True:
        kwargs: dict[str, Any] = {"limit": page_size}
        if cursor is not None:
            kwargs["uuid_cursor"] = cursor

        page_num += 1
        batch = _fetch_page_with_retry(
            client.graph.edge.get_by_graph_id,
            graph_id,
            max_retries=max_retries,
            retry_delay=retry_delay,
            page_description=f"Kanten abrufen Seite {page_num} (graph={graph_id})",
            **kwargs,
        )
        if not batch:
            break

        all_edges.extend(batch)
        if len(batch) < page_size:
            break

        cursor = getattr(batch[-1], "uuid_", None) or getattr(batch[-1], "uuid", None)
        if cursor is None:
            logger.warning(f"Kante hat kein uuid-Feld, Paginierung wird bei {len(all_edges)} Kanten gestoppt")
            break

    return all_edges
