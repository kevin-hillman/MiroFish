"""
OASIS-Agent-Profil-Generator
Entitaeten aus dem Zep-Graph in das fuer die OASIS-Simulationsplattform erforderliche Agent-Profil-Format umwandeln

Optimierungsverbesserungen:
1. Zep-Abruffunktion aufrufen, um Knoteninformationen zu bereichern
2. Optimierte Prompts fuer sehr detaillierte Persona-Generierung
3. Unterscheidung zwischen individuellen Entitaeten und abstrakten Gruppenentitaeten
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS-Agent-Profil-Datenstruktur"""
    # Allgemeine Felder
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Optionale Felder - Reddit-Stil
    karma: int = 1000
    
    # Optionale Felder - Twitter-Stil
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Zusaetzliche Persona-Informationen
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Quellentitaets-Informationen
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """In Reddit-Plattform-Format umwandeln"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS-Bibliothek erfordert Feldname username (ohne Unterstrich)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # Zusaetzliche Persona-Informationen hinzufuegen (falls vorhanden)
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """In Twitter-Plattform-Format umwandeln"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS-Bibliothek erfordert Feldname username (ohne Unterstrich)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Zusaetzliche Persona-Informationen hinzufuegen
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """In vollstaendiges Woerterbuch-Format umwandeln"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS-Profil-Generator

    Entitaeten aus dem Zep-Graph in die fuer OASIS-Simulation erforderlichen Agent-Profile umwandeln

    Optimierte Funktionen:
    1. Zep-Graph-Abruffunktion fuer reichhaltigeren Kontext aufrufen
    2. Sehr detaillierte Persona generieren (einschliesslich Basisinformationen, Berufserfahrung, Persoenlichkeitsmerkmale, Social-Media-Verhalten etc.)
    3. Unterscheidung zwischen individuellen Entitaeten und abstrakten Gruppenentitaeten
    """
    
    # MBTI-Typenliste
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Liste haeufiger Laender
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Individuelle Entitaetstypen (benoetigen konkrete Persona-Generierung)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Gruppen-/Institutionsentitaetstypen (benoetigen repraesentative Gruppen-Persona)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY ist nicht konfiguriert")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Zep-Client fuer den Abruf reichhaltigen Kontexts
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Zep-Client-Initialisierung fehlgeschlagen: {e}")
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        OASIS-Agent-Profil aus Zep-Entitaet generieren

        Args:
            entity: Zep-Entitaetsknoten
            user_id: Benutzer-ID (fuer OASIS)
            use_llm: Ob LLM fuer detaillierte Persona-Generierung verwendet werden soll

        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Basisinformationen
        name = entity.name
        user_name = self._generate_username(name)
        
        # Kontextinformationen erstellen
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Detaillierte Persona mit LLM generieren
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # Basis-Persona regelbasiert generieren
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Benutzernamen generieren"""
        # Sonderzeichen entfernen, in Kleinbuchstaben umwandeln
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Zufaelliges Suffix hinzufuegen, um Duplikate zu vermeiden
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Zep-Graph-Hybridsuche verwenden, um reichhaltige entitaetsbezogene Informationen abzurufen

        Zep hat keine eingebaute Hybridsuche-Schnittstelle, Kanten- und Knotensuche muessen separat durchgefuehrt und dann zusammengefuehrt werden.
        Parallele Anfragen fuer hoehere Effizienz verwenden.

        Args:
            entity: Entitaetsknotenobjekt

        Returns:
            Woerterbuch mit facts, node_summaries, context
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # graph_id muss vorhanden sein, um Suche durchzufuehren
        if not self.graph_id:
            logger.debug(f"Zep-Abruf uebersprungen: graph_id nicht gesetzt")
            return results
        
        comprehensive_query = f"关于{entity_name}的所有信息、活动、事件、关系和背景"
        
        def search_edges():
            """Kanten suchen (Fakten/Beziehungen) - mit Wiederholungsmechanismus"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep边搜索第 {attempt + 1} 次失败: {str(e)[:80]}, 重试中...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep边搜索在 {max_retries} 次尝试后仍失败: {e}")
            return None
        
        def search_nodes():
            """Knoten suchen (Entitaetszusammenfassungen) - mit Wiederholungsmechanismus"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep节点搜索第 {attempt + 1} 次失败: {str(e)[:80]}, 重试中...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep节点搜索在 {max_retries} 次尝试后仍失败: {e}")
            return None
        
        try:
            # Kanten- und Knotensuche parallel ausfuehren
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # Ergebnisse abrufen
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # Kantensuchergebnisse verarbeiten
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # Knotensuchergebnisse verarbeiten
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"相关实体: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # Umfassenden Kontext erstellen
            context_parts = []
            if results["facts"]:
                context_parts.append("事实信息:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("相关实体:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Zep-Hybridabruf abgeschlossen: {entity_name}, {len(results['facts'])} Fakten abgerufen, {len(results['node_summaries'])} zugehoerige Knoten")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Zep-Abruf Zeitueberschreitung ({entity_name})")
        except Exception as e:
            logger.warning(f"Zep-Abruf fehlgeschlagen ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Vollstaendige Kontextinformationen fuer eine Entitaet erstellen

        Beinhaltet:
        1. Kanteninformationen der Entitaet selbst (Fakten)
        2. Detailinformationen verknuepfter Knoten
        3. Durch Zep-Hybridsuche abgerufene reichhaltige Informationen
        """
        context_parts = []
        
        # 1. Entitaetsattribut-Informationen hinzufuegen
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### 实体属性\n" + "\n".join(attrs))
        
        # 2. Zugehoerige Kanteninformationen hinzufuegen (Fakten/Beziehungen)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # Keine Mengenbegrenzung
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (相关实体)")
                    else:
                        relationships.append(f"- (相关实体) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### 相关事实和关系\n" + "\n".join(relationships))
        
        # 3. Detailinformationen verknuepfter Knoten hinzufuegen
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # Keine Mengenbegrenzung
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # Standard-Labels herausfiltern
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### 关联实体信息\n" + "\n".join(related_info))
        
        # 4. Zep-Hybridsuche fuer reichhaltigere Informationen verwenden
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # Deduplizierung: Bereits vorhandene Fakten ausschliessen
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Zep检索到的事实信息\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Zep检索到的相关节点\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Pruefen, ob es sich um eine individuelle Entitaet handelt"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """Pruefen, ob es sich um eine Gruppen-/Institutionsentitaet handelt"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Sehr detaillierte Persona mit LLM generieren

        Unterscheidung nach Entitaetstyp:
        - Individuelle Entitaet: Konkrete Personenbeschreibung generieren
        - Gruppen-/Institutionsentitaet: Repraesentative Kontobeschreibung generieren
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Mehrfache Generierungsversuche, bis Erfolg oder maximale Wiederholungsanzahl erreicht
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Temperatur bei jedem Wiederholungsversuch senken
                    # max_tokens nicht setzen, LLM frei arbeiten lassen
                )
                
                content = response.choices[0].message.content
                
                # Pruefen, ob abgeschnitten (finish_reason ist nicht 'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM-Ausgabe abgeschnitten (attempt {attempt+1}), Reparatur wird versucht...")
                    content = self._fix_truncated_json(content)
                
                # JSON-Parsing versuchen
                try:
                    result = json.loads(content)
                    
                    # Erforderliche Felder validieren
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name}是一个{entity_type}。"
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON-Parsing fehlgeschlagen (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # JSON-Reparatur versuchen
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM-Aufruf fehlgeschlagen (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponentielles Backoff
        
        logger.warning(f"LLM-Persona-Generierung fehlgeschlagen ({max_attempts} Versuche): {last_error}, regelbasierte Generierung wird verwendet")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Abgeschnittenes JSON reparieren (Ausgabe durch max_tokens-Limit abgeschnitten)"""
        import re
        
        # Falls JSON abgeschnitten, versuchen es zu schliessen
        content = content.strip()
        
        # 计算未闭合的括号
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # 检查是否有未闭合的字符串
        # Einfache Pruefung: Wenn nach dem letzten Anfuehrungszeichen kein Komma oder schliessende Klammer, String moeglicherweise abgeschnitten
        if content and content[-1] not in '",}]':
            # Versuchen, String zu schliessen
            content += '"'
        
        # 闭合括号
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Beschaedigtes JSON reparieren versuchen"""
        import re
        
        # 1. Zuerst abgeschnittenen Fall reparieren versuchen
        content = self._fix_truncated_json(content)
        
        # 2. JSON-Teil extrahieren versuchen
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Zeilenumbruch-Probleme in Strings behandeln
            # Alle String-Werte finden und Zeilenumbrueche darin ersetzen
            def fix_string_newlines(match):
                s = match.group(0)
                # Tatsaechliche Zeilenumbrueche in Strings durch Leerzeichen ersetzen
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Ueberfluessige Leerzeichen ersetzen
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # JSON-String-Werte zuordnen
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Parsing versuchen
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. Falls immer noch fehlgeschlagen, aggressivere Reparatur versuchen
                try:
                    # Alle Steuerzeichen entfernen
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Alle aufeinanderfolgenden Leerzeichen ersetzen
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Versuchen, Teilinformationen aus dem Inhalt zu extrahieren
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # Moeglicherweise abgeschnitten
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name}是一个{entity_type}。")
        
        # Falls bedeutungsvoller Inhalt extrahiert wurde, als repariert markieren
        if bio_match or persona_match:
            logger.info(f"Teilinformationen aus beschaedigtem JSON extrahiert")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Vollstaendig fehlgeschlagen, Basisstruktur zurueckgeben
        logger.warning(f"JSON-Reparatur fehlgeschlagen, Basisstruktur wird zurueckgegeben")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name}是一个{entity_type}。"
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """System-Prompt abrufen"""
        base_prompt = "你是社交媒体用户画像生成专家。生成详细、真实的人设用于舆论模拟,最大程度还原已有现实情况。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。使用中文。"
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Detaillierten Persona-Prompt fuer individuelle Entitaet erstellen"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
        return f"""为实体生成详细的社交媒体用户人设,最大程度还原已有现实情况。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（年龄、职业、教育背景、所在地）
   - 人物背景（重要经历、与事件的关联、社会关系）
   - 性格特征（MBTI类型、核心性格、情绪表达方式）
   - 社交媒体行为（发帖频率、内容偏好、互动风格、语言特点）
   - 立场观点（对话题的态度、可能被激怒/感动的内容）
   - 独特特征（口头禅、特殊经历、个人爱好）
   - 个人记忆（人设的重要部分，要介绍这个个体与事件的关联，以及这个个体在事件中的已有动作与反应）
3. age: 年龄数字（必须是整数）
4. gender: 性别，必须是英文: "male" 或 "female"
5. mbti: MBTI类型（如INTJ、ENFP等）
6. country: 国家（使用中文，如"中国"）
7. profession: 职业
8. interested_topics: 感兴趣话题数组

重要:
- 所有字段值必须是字符串或数字，不要使用换行符
- persona必须是一段连贯的文字描述
- 使用中文（除了gender字段必须用英文male/female）
- 内容要与实体信息保持一致
- age必须是有效的整数，gender必须是"male"或"female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Detaillierten Persona-Prompt fuer Gruppen-/Institutionsentitaet erstellen"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
        return f"""为机构/群体实体生成详细的社交媒体账号设定,最大程度还原已有现实情况。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 官方账号简介，200字，专业得体
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（正式名称、机构性质、成立背景、主要职能）
   - 账号定位（账号类型、目标受众、核心功能）
   - 发言风格（语言特点、常用表达、禁忌话题）
   - 发布内容特点（内容类型、发布频率、活跃时间段）
   - 立场态度（对核心话题的官方立场、面对争议的处理方式）
   - 特殊说明（代表的群体画像、运营习惯）
   - 机构记忆（机构人设的重要部分，要介绍这个机构与事件的关联，以及这个机构在事件中的已有动作与反应）
3. age: 固定填30（机构账号的虚拟年龄）
4. gender: 固定填"other"（机构账号使用other表示非个人）
5. mbti: MBTI类型，用于描述账号风格，如ISTJ代表严谨保守
6. country: 国家（使用中文，如"中国"）
7. profession: 机构职能描述
8. interested_topics: 关注领域数组

重要:
- 所有字段值必须是字符串或数字，不允许null值
- persona必须是一段连贯的文字描述，不要使用换行符
- 使用中文（除了gender字段必须用英文"other"）
- age必须是整数30，gender必须是字符串"other"
- 机构账号发言要符合其身份定位"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Basis-Persona regelbasiert generieren"""
        
        # Verschiedene Persona nach Entitaetstyp generieren
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # Virtuelles Alter der Institution
                "gender": "other",  # Institutionen verwenden other
                "mbti": "ISTJ",  # Institutionsstil: streng konservativ
                "country": "中国",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # Virtuelles Alter der Institution
                "gender": "other",  # Institutionen verwenden other
                "mbti": "ISTJ",  # Institutionsstil: streng konservativ
                "country": "中国",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Standard-Persona
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Graph-ID fuer Zep-Abruf festlegen"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Agent-Profile batchweise aus Entitaeten generieren (unterstuetzt parallele Generierung)

        Args:
            entities: Entitaetsliste
            use_llm: Ob LLM fuer detaillierte Persona-Generierung verwendet werden soll
            progress_callback: Fortschritts-Callback-Funktion (current, total, message)
            graph_id: Graph-ID, fuer Zep-Abruf reichhaltigeren Kontexts
            parallel_count: Parallele Generierungsanzahl, Standard 5
            realtime_output_path: Echtzeit-Schreibdateipfad (falls angegeben, nach jeder Generierung schreiben)
            output_platform: Ausgabeplattform-Format ("reddit" oder "twitter")

        Returns:
            Agent-Profil-Liste
        """
        import concurrent.futures
        from threading import Lock
        
        # graph_id fuer Zep-Abruf festlegen
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # Liste vorbelegen, um Reihenfolge beizubehalten
        completed_count = [0]  # Liste verwenden, um Aenderung in Closure zu ermoeglichen
        lock = Lock()
        
        # Hilfsfunktion zum Echtzeit-Dateischreiben
        def save_profiles_realtime():
            """Bereits generierte Profile in Echtzeit in Datei speichern"""
            if not realtime_output_path:
                return
            
            with lock:
                # Bereits generierte Profile herausfiltern
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit-JSON-Format
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter-CSV-Format
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Echtzeitspeicherung von Profilen fehlgeschlagen: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Arbeitsfunktion zur Generierung eines einzelnen Profils"""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # Generierte Persona in Echtzeit an Konsole und Protokoll ausgeben
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"Persona-Generierung fuer Entitaet {entity.name} fehlgeschlagen: {str(e)}")
                # Ein Basis-Profil erstellen
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"开始并行生成 {total} 个Agent人设（并行数: {parallel_count}）...")
        print(f"\n{'='*60}")
        print(f"Agent-Persona-Generierung wird gestartet - insgesamt {total} Entitaeten, Parallelitaet: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Parallel mit Thread-Pool ausfuehren
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Alle Aufgaben einreichen
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # Ergebnisse sammeln
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # In Echtzeit in Datei schreiben
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"已完成 {current}/{total}: {entity.name}（{entity_type}）"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} 使用备用人设: {error}")
                    else:
                        logger.info(f"[{current}/{total}] 成功生成人设: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"Ausnahme bei der Verarbeitung von Entitaet {entity.name}: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # In Echtzeit in Datei schreiben（即使是备用人设）
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"Persona-Generierung abgeschlossen! Insgesamt {len([p for p in profiles if p])} Agents generiert")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Generierte Persona in Echtzeit an die Konsole ausgeben (vollstaendiger Inhalt, nicht abgeschnitten)"""
        separator = "-" * 70
        
        # Vollstaendigen Ausgabeinhalt erstellen (nicht abgeschnitten)
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else '无'
        
        output_lines = [
            f"\n{separator}",
            f"[Generiert] {entity_name} ({entity_type})",
            f"{separator}",
            f"Benutzername: {profile.user_name}",
            f"",
            f"[Kurzbiografie]",
            f"{profile.bio}",
            f"",
            f"[Detaillierte Persona]",
            f"{profile.persona}",
            f"",
            f"[Grundattribute]",
            f"Alter: {profile.age} | Geschlecht: {profile.gender} | MBTI: {profile.mbti}",
            f"Beruf: {profile.profession} | Land: {profile.country}",
            f"Interessenthemen: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Nur an Konsole ausgeben (Duplikate vermeiden, Logger gibt nicht mehr vollstaendigen Inhalt aus)
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Profile in Datei speichern (korrektes Format je nach Plattform waehlen)

        OASIS-Plattform-Formatanforderungen:
        - Twitter: CSV-Format
        - Reddit: JSON-Format

        Args:
            profiles: Profilliste
            file_path: Dateipfad
            platform: Plattformtyp ("reddit" oder "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        保存Twitter Profile为CSV格式（符合OASIS官方要求）
        
        OASIS Twitter要求的CSV字段：
        - user_id: 用户ID（根据CSV顺序从0开始）
        - name: 用户真实姓名
        - username: 系统中的用户名
        - user_char: 详细人设描述（注入到LLM系统提示中，指导Agent行为）
        - description: 简短的公开简介（显示在用户资料页面）
        
        user_char vs description 区别：
        - user_char: 内部使用，LLM系统提示，决定Agent如何思考和行动
        - description: 外部显示，其他用户可见的简介
        """
        import csv
        
        # Sicherstellen, dass Dateierweiterung .csv ist
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Von OASIS geforderte Kopfzeile schreiben
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # Datenzeilen schreiben
            for idx, profile in enumerate(profiles):
                # user_char: Vollstaendige Persona (bio + persona), fuer LLM-System-Prompt
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Zeilenumbrueche behandeln (in CSV durch Leerzeichen ersetzen)
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: Kurze Beschreibung, fuer externe Anzeige
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: Fortlaufende ID ab 0
                    profile.name,           # name: Echter Name
                    profile.user_name,      # username: Benutzername
                    user_char,              # user_char: Vollstaendige Persona (intern fuer LLM)
                    description             # description: Kurze Beschreibung (extern angezeigt)
                ]
                writer.writerow(row)
        
        logger.info(f"已保存 {len(profiles)} 个Twitter Profile到 {file_path} (OASIS CSV格式)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        gender-Feld auf das von OASIS geforderte englische Format standardisieren

        OASIS erfordert: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        # Chinesische Zuordnung
        gender_map = {
            "男": "male",
            "女": "female",
            "机构": "other",
            "其他": "other",
            # Englisch bereits vorhanden
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        保存Reddit Profile为JSON格式
        
        使用与 to_reddit_format() 一致的格式，确保 OASIS 能正确读取。
        必须包含 user_id 字段，这是 OASIS agent_graph.get_agent() 匹配的关键！
        
        必需字段：
        - user_id: 用户ID（整数，用于匹配 initial_posts 中的 poster_agent_id）
        - username: 用户名
        - name: 显示名称
        - bio: 简介
        - persona: 详细人设
        - age: 年龄（整数）
        - gender: "male", "female", 或 "other"
        - mbti: MBTI类型
        - country: 国家
        """
        data = []
        for idx, profile in enumerate(profiles):
            # 使用与 to_reddit_format() 一致的格式
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Wichtig: user_id muss enthalten sein
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS-Pflichtfelder - Sicherstellen, dass alle Standardwerte haben
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "中国",
            }
            
            # Optionale Felder
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存 {len(profiles)} 个Reddit Profile到 {file_path} (JSON格式，包含user_id字段)")
    
    # Alten Methodennamen als Alias beibehalten fuer Rueckwaertskompatibilitaet
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Veraltet] Bitte verwenden Sie die Methode save_profiles()"""
        logger.warning("save_profiles_to_json ist veraltet, bitte verwenden Sie die Methode save_profiles")
        self.save_profiles(profiles, file_path, platform)

