"""
Zep-Entitaetslese- und Filterdienst
Knoten aus dem Zep-Graph lesen und Knoten filtern, die vordefinierten Entitaetstypen entsprechen
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# Fuer generischen Rueckgabetyp
T = TypeVar('T')


@dataclass
class EntityNode:
    """Entitaetsknoten-Datenstruktur"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Zugehoerige Kanteninformationen
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Zugehoerige andere Knoteninformationen
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """Entitaetstyp abrufen (Standard-Entity-Label ausschliessen)"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Gefilterte Entitaetssammlung"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Zep-Entitaetslese- und Filterdienst

    Hauptfunktionen:
    1. Alle Knoten aus dem Zep-Graph lesen
    2. Knoten filtern, die vordefinierten Entitaetstypen entsprechen (Knoten mit Labels ausser nur Entity)
    3. Zugehoerige Kanten- und verknuepfte Knoteninformationen fuer jede Entitaet abrufen
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY ist nicht konfiguriert")
        
        self.client = Zep(api_key=self.api_key)
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        Zep-API-Aufruf mit Wiederholungsmechanismus

        Args:
            func: Auszufuehrende Funktion (parameterlose Lambda oder Callable)
            operation_name: Operationsname fuer Protokollierung
            max_retries: Maximale Anzahl der Wiederholungen (Standard 3, d.h. maximal 3 Versuche)
            initial_delay: Anfangsverzoegerung in Sekunden

        Returns:
            API-Aufrufergebnis
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} 第 {attempt + 1} 次尝试失败: {str(e)[:100]}, "
                        f"{delay:.1f}秒后重试..."
                    )
                    time.sleep(delay)
                    delay *= 2  # 指数退避
                else:
                    logger.error(f"Zep {operation_name} 在 {max_retries} 次尝试后仍失败: {str(e)}")
        
        raise last_exception
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Alle Knoten des Graphen abrufen (paginiert)

        Args:
            graph_id: Graph-ID

        Returns:
            Knotenliste
        """
        logger.info(f"Alle Knoten des Graphen {graph_id} werden abgerufen...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"Insgesamt {len(nodes_data)} Knoten abgerufen")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Alle Kanten des Graphen abrufen (paginiert)

        Args:
            graph_id: Graph-ID

        Returns:
            Kantenliste
        """
        logger.info(f"Alle Kanten des Graphen {graph_id} werden abgerufen...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"Insgesamt {len(edges_data)} Kanten abgerufen")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        Alle zugehoerigen Kanten eines bestimmten Knotens abrufen (mit Wiederholungsmechanismus)

        Args:
            node_uuid: Knoten-UUID

        Returns:
            Kantenliste
        """
        try:
            # Zep-API mit Wiederholungsmechanismus aufrufen
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"获取节点边(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"Abrufen der Kanten von Knoten {node_uuid} fehlgeschlagen: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Knoten filtern, die vordefinierten Entitaetstypen entsprechen

        Filterlogik:
        - Wenn Knoten-Labels nur "Entity" enthalten, entspricht die Entitaet nicht unserem vordefinierten Typ, ueberspringen
        - Wenn Knoten-Labels Labels ausser "Entity" und "Node" enthalten, entspricht dies dem vordefinierten Typ, beibehalten

        Args:
            graph_id: Graph-ID
            defined_entity_types: Liste vordefinierter Entitaetstypen (optional, wenn angegeben nur diese Typen beibehalten)
            enrich_with_edges: Ob zugehoerige Kanteninformationen fuer jede Entitaet abgerufen werden sollen

        Returns:
            FilteredEntities: Gefilterte Entitaetssammlung
        """
        logger.info(f"Entitaeten des Graphen {graph_id} werden gefiltert...")
        
        # Alle Knoten abrufen
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # Alle Kanten abrufen (fuer spaetere Verknuepfungssuche)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # Knoten-UUID-zu-Knotendaten-Zuordnung erstellen
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # Passende Entitaeten filtern
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # Filterlogik: Labels muessen Labels ausser "Entity" und "Node" enthalten
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                # Nur Standard-Labels, ueberspringen
                continue
            
            # Falls vordefinierte Typen angegeben, Uebereinstimmung pruefen
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # Entitaetsknotenobjekt erstellen
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # Zugehoerige Kanten und Knoten abrufen
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # Grundinformationen verknuepfter Knoten abrufen
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"Filterung abgeschlossen: Gesamt-Knoten {total_count}, passend {len(filtered_entities)}, "
                   f"Entitaetstypen: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Einzelne Entitaet mit vollstaendigem Kontext abrufen (Kanten und verknuepfte Knoten, mit Wiederholungsmechanismus)

        Args:
            graph_id: Graph-ID
            entity_uuid: Entitaets-UUID

        Returns:
            EntityNode oder None
        """
        try:
            # Knoten mit Wiederholungsmechanismus abrufen
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"获取节点详情(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # Kanten des Knotens abrufen
            edges = self.get_node_edges(entity_uuid)
            
            # Alle Knoten abrufen用于关联查找
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # Zugehoerige Kanten und Knoten verarbeiten
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # Verknuepfte Knoteninformationen abrufen
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"获取实体 {entity_uuid} 失败: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        获取指定类型的所有实体
        
        Args:
            graph_id: 图谱ID
            entity_type: 实体类型（如 "Student", "PublicFigure" 等）
            enrich_with_edges: 是否获取相关边信息
            
        Returns:
            实体列表
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities


