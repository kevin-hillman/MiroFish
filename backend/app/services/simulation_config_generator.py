"""
Intelligenter Simulationskonfigurations-Generator
Verwendet LLM zur automatischen Generierung detaillierter Simulationsparameter basierend auf Simulationsanforderungen, Dokumentinhalten und Graph-Informationen
Vollstaendige Automatisierung, keine manuelle Parametereinstellung erforderlich

Schrittweise Generierungsstrategie zur Vermeidung von Fehlern durch zu langen Inhalt auf einmal:
1. Zeitkonfiguration generieren
2. Ereigniskonfiguration generieren
3. Agent-Konfiguration batchweise generieren
4. Plattformkonfiguration generieren
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.simulation_config')

# Chinesische Tagesablauf-Zeitkonfiguration (Pekinger Zeit)
CHINA_TIMEZONE_CONFIG = {
    # Tiefnachtzeit (fast keine Aktivitaet)
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Morgenzeit (allmaehliches Aufwachen)
    "morning_hours": [6, 7, 8],
    # Arbeitszeit
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Abend-Spitzenzeit (am aktivsten)
    "peak_hours": [19, 20, 21, 22],
    # Nachtzeit (sinkende Aktivitaet)
    "night_hours": [23],
    # Aktivitaetskoeffizienten
    "activity_multipliers": {
        "dead": 0.05,      # Frueher Morgen fast niemand
        "morning": 0.4,    # Morgens allmaehlich aktiver
        "work": 0.7,       # Arbeitszeit mittel
        "peak": 1.5,       # Abend-Spitzenzeit
        "night": 0.5       # Nachtabnahme
    }
}


@dataclass
class AgentActivityConfig:
    """Aktivitaetskonfiguration eines einzelnen Agents"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    
    # Aktivitaetskonfiguration (0.0-1.0)
    activity_level: float = 0.5  # Gesamtaktivitaet
    
    # Posting-Haeufigkeit (erwartete Beitraege pro Stunde)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0
    
    # Aktive Zeitraeume (24-Stunden-Format, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))
    
    # Reaktionsgeschwindigkeit (Verzoegerung bei Trendthemen, Einheit: Simulationsminuten)
    response_delay_min: int = 5
    response_delay_max: int = 60
    
    # Stimmungstendenz (-1.0 bis 1.0, negativ bis positiv)
    sentiment_bias: float = 0.0
    
    # Standpunkt (Einstellung zu bestimmten Themen)
    stance: str = "neutral"  # supportive, opposing, neutral, observer
    
    # Einflussgewichtung (bestimmt die Wahrscheinlichkeit, dass Beitraege von anderen Agents gesehen werden)
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """Zeitsimulationskonfiguration (basierend auf chinesischen Tagesablauf-Gewohnheiten)"""
    # Gesamte Simulationsdauer (Simulationsstunden)
    total_simulation_hours: int = 72  # Standard 72 Stunden Simulation (3 Tage)
    
    # Zeit pro Runde (Simulationsminuten) - Standard 60 Minuten (1 Stunde), beschleunigter Zeitablauf
    minutes_per_round: int = 60
    
    # Bereich der pro Stunde aktivierten Agents
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20
    
    # Spitzenzeit (Abends 19-22 Uhr, aktivste Zeit in China)
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5
    
    # Nebenzeit (0-5 Uhr morgens, fast keine Aktivitaet)
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Fruehmorgens extrem niedrige Aktivitaet
    
    # Morgenzeit
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4
    
    # Arbeitszeit
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """Ereigniskonfiguration"""
    # Anfangsereignisse (Ausloeser-Ereignisse bei Simulationsstart)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)
    
    # Geplante Ereignisse (zu bestimmten Zeiten ausgeloeste Ereignisse)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)
    
    # Trendthema-Schluesselwoerter
    hot_topics: List[str] = field(default_factory=list)
    
    # Richtung der Meinungsfuehrung
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Plattformspezifische Konfiguration"""
    platform: str  # twitter or reddit
    
    # Empfehlungsalgorithmus-Gewichtung
    recency_weight: float = 0.4  # Zeitliche Aktualitaet
    popularity_weight: float = 0.3  # Popularitaet
    relevance_weight: float = 0.3  # Relevanz
    
    # Virale Verbreitungsschwelle (Interaktionsanzahl ab der Verbreitung ausgeloest wird)
    viral_threshold: int = 10
    
    # Staerke des Echokammer-Effekts (Grad der Konzentration aehnlicher Meinungen)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Vollstaendige Simulationsparameter-Konfiguration"""
    # Basisinformationen
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    
    # Zeitkonfiguration
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)
    
    # Agent-Konfigurationsliste
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)
    
    # Ereigniskonfiguration
    event_config: EventConfig = field(default_factory=EventConfig)
    
    # Plattformkonfiguration
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # LLM-Konfiguration
    llm_model: str = ""
    llm_base_url: str = ""
    
    # Generierungsmetadaten
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM-Begruendung
    
    def to_dict(self) -> Dict[str, Any]:
        """In Woerterbuch umwandeln"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """In JSON-String umwandeln"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Intelligenter Simulationskonfigurations-Generator

    Verwendet LLM zur Analyse von Simulationsanforderungen, Dokumentinhalten und Graph-Entitaetsinformationen,
    um automatisch optimale Simulationsparameter zu generieren

    Schrittweise Generierungsstrategie:
    1. Zeit- und Ereigniskonfiguration generieren (leichtgewichtig)
    2. Agent-Konfiguration batchweise generieren (je 10-20 pro Batch)
    3. Plattformkonfiguration generieren
    """
    
    # Maximale Kontextzeichenanzahl
    MAX_CONTEXT_LENGTH = 50000
    # Anzahl der Agents pro Batch
    AGENTS_PER_BATCH = 15
    
    # Kontextabschneide-Laenge pro Schritt (Zeichenanzahl)
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Zeitkonfiguration
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Ereigniskonfiguration
    ENTITY_SUMMARY_LENGTH = 300          # Entitaetszusammenfassung
    AGENT_SUMMARY_LENGTH = 300           # Entitaetszusammenfassung in Agent-Konfiguration
    ENTITIES_PER_TYPE_DISPLAY = 20       # Angezeigte Entitaeten pro Typ
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
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
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Vollstaendige Simulationskonfiguration intelligent generieren (schrittweise)

        Args:
            simulation_id: Simulations-ID
            project_id: Projekt-ID
            graph_id: Graph-ID
            simulation_requirement: Beschreibung der Simulationsanforderung
            document_text: Originaldokumentinhalt
            entities: Gefilterte Entitaetsliste
            enable_twitter: Ob Twitter aktiviert werden soll
            enable_reddit: Ob Reddit aktiviert werden soll
            progress_callback: Fortschritts-Callback-Funktion(current_step, total_steps, message)

        Returns:
            SimulationParameters: Vollstaendige Simulationsparameter
        """
        logger.info(f"Intelligente Simulationskonfigurationsgenerierung gestartet: simulation_id={simulation_id}, Entitaeten={len(entities)}")
        
        # Gesamtanzahl der Schritte berechnen
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Zeitkonfiguration + Ereigniskonfiguration + N Agent-Batches + Plattformkonfiguration
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. Basis-Kontextinformationen erstellen
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== Schritt 1: Zeitkonfiguration generieren ==========
        report_progress(1, "Zeitkonfiguration wird generiert...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"Zeitkonfiguration: {time_config_result.get('reasoning', 'Erfolg')}")
        
        # ========== Schritt 2: Ereigniskonfiguration generieren ==========
        report_progress(2, "Ereigniskonfiguration und Trendthemen werden generiert...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"Ereigniskonfiguration: {event_config_result.get('reasoning', 'Erfolg')}")
        
        # ========== Schritt 3-N: Agent-Konfiguration batchweise generieren ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                f"Agent-Konfiguration wird generiert ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)
        
        reasoning_parts.append(f"Agent-Konfiguration: {len(all_agent_configs)} erfolgreich generiert")
        
        # ========== Veroeffentlicher-Agent fuer initiale Beitraege zuweisen ==========
        logger.info("Geeignete Veroeffentlicher-Agents fuer initiale Beitraege werden zugewiesen...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"Initiale Beitragszuweisung: {assigned_count} Beitraege haben zugewiesene Veroeffentlicher")
        
        # ========== Letzter Schritt: Plattformkonfiguration generieren ==========
        report_progress(total_steps, "Plattformkonfiguration wird generiert...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # Endgueltige Parameter erstellen
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"Simulationskonfigurationsgenerierung abgeschlossen: {len(params.agent_configs)} Agent-Konfigurationen")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """LLM-Kontext erstellen, auf maximale Laenge abschneiden"""
        
        # Entitaetszusammenfassung
        entity_summary = self._summarize_entities(entities)
        
        # Kontext erstellen
        context_parts = [
            f"## 模拟需求\n{simulation_requirement}",
            f"\n## 实体信息 ({len(entities)}个)\n{entity_summary}",
        ]
        
        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # 500 Zeichen Puffer lassen
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(Dokument abgeschnitten)"
            context_parts.append(f"\n## 原始文档内容\n{doc_text}")
        
        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Entitaetszusammenfassung generieren"""
        lines = []
        
        # Nach Typ gruppieren
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)}个)")
            # Konfigurierte Anzeigeanzahl und Zusammenfassungslaenge verwenden
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... 还有 {len(type_entities) - display_count} 个")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """LLM-Aufruf mit Wiederholung, einschliesslich JSON-Reparaturlogik"""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Temperatur bei jedem Wiederholungsversuch senken
                    # max_tokens nicht setzen, LLM frei arbeiten lassen
                )
                
                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason
                
                # Pruefen, ob abgeschnitten wurde
                if finish_reason == 'length':
                    logger.warning(f"LLM-Ausgabe abgeschnitten (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # JSON-Parsing versuchen
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON-Parsing fehlgeschlagen (attempt {attempt+1}): {str(e)[:80]}")
                    
                    # JSON-Reparatur versuchen
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"LLM-Aufruf fehlgeschlagen (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLM-Aufruf fehlgeschlagen")
    
    def _fix_truncated_json(self, content: str) -> str:
        """Abgeschnittenes JSON reparieren"""
        content = content.strip()
        
        # Nicht geschlossene Klammern zaehlen
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Pruefen, ob nicht geschlossene Strings vorhanden
        if content and content[-1] not in '",}]':
            content += '"'
        
        # Klammern schliessen
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Konfigurations-JSON-Reparatur versuchen"""
        import re
        
        # Abgeschnittenen Fall reparieren
        content = self._fix_truncated_json(content)
        
        # JSON-Teil extrahieren
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # Zeilenumbrueche in Strings entfernen
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # Alle Steuerzeichen entfernen versuchen
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Zeitkonfiguration generieren"""
        # Konfigurierte Kontextabschneide-Laenge verwenden
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # Maximalen Erlaubniswert berechnen (90% der Agent-Anzahl)
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""基于以下模拟需求，生成时间模拟配置。

{context_truncated}

## 任务
请生成时间配置JSON。

### 基本原则（仅供参考，需根据具体事件和参与群体灵活调整）：
- 用户群体为中国人，需符合北京时间作息习惯
- 凌晨0-5点几乎无人活动（活跃度系数0.05）
- 早上6-8点逐渐活跃（活跃度系数0.4）
- 工作时间9-18点中等活跃（活跃度系数0.7）
- 晚间19-22点是高峰期（活跃度系数1.5）
- 23点后活跃度下降（活跃度系数0.5）
- 一般规律：凌晨低活跃、早间渐增、工作时段中等、晚间高峰
- **重要**：以下示例值仅供参考，你需要根据事件性质、参与群体特点来调整具体时段
  - 例如：学生群体高峰可能是21-23点；媒体全天活跃；官方机构只在工作时间
  - 例如：突发热点可能导致深夜也有讨论，off_peak_hours 可适当缩短

### 返回JSON格式（不要markdown）

示例：
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "针对该事件的时间配置说明"
}}

字段说明：
- total_simulation_hours (int): 模拟总时长，24-168小时，突发事件短、持续话题长
- minutes_per_round (int): 每轮时长，30-120分钟，建议60分钟
- agents_per_hour_min (int): 每小时最少激活Agent数（取值范围: 1-{max_agents_allowed}）
- agents_per_hour_max (int): 每小时最多激活Agent数（取值范围: 1-{max_agents_allowed}）
- peak_hours (int数组): 高峰时段，根据事件参与群体调整
- off_peak_hours (int数组): 低谷时段，通常深夜凌晨
- morning_hours (int数组): 早间时段
- work_hours (int数组): 工作时段
- reasoning (string): 简要说明为什么这样配置"""

        system_prompt = "你是社交媒体模拟专家。返回纯JSON格式，时间配置需符合中国人作息习惯。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Zeitkonfigurations-LLM-Generierung fehlgeschlagen: {e}, Standard-Konfiguration wird verwendet")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Standard-Zeitkonfiguration abrufen (chinesischer Tagesablauf)"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 每轮1小时，加快时间流速
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Standard-Konfiguration basierend auf chinesischem Tagesablauf (1 Stunde pro Runde)"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Zeitkonfigurationsergebnis parsen und validieren, dass agents_per_hour die Gesamt-Agent-Anzahl nicht ueberschreitet"""
        # Originalwerte abrufen
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # Validieren und korrigieren: Sicherstellen, dass Gesamt-Agent-Anzahl nicht ueberschritten wird
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) 超过总Agent数 ({num_entities})，已修正")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) 超过总Agent数 ({num_entities})，已修正")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # Sicherstellen, dass min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max，已修正为 {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # 默认每轮1小时
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # 凌晨几乎无人
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Ereigniskonfiguration generieren"""
        
        # Liste verfuegbarer Entitaetstypen abrufen, als LLM-Referenz
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))
        
        # Repraesentative Entitaetsnamen fuer jeden Typ auflisten
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # Konfigurierte Kontextabschneide-Laenge verwenden
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""基于以下模拟需求，生成事件配置。

模拟需求: {simulation_requirement}

{context_truncated}

## 可用实体类型及示例
{type_info}

## 任务
请生成事件配置JSON：
- 提取热点话题关键词
- 描述舆论发展方向
- 设计初始帖子内容，**每个帖子必须指定 poster_type（发布者类型）**

**重要**: poster_type 必须从上面的"可用实体类型"中选择，这样初始帖子才能分配给合适的 Agent 发布。
例如：官方声明应由 Official/University 类型发布，新闻由 MediaOutlet 发布，学生观点由 Student 发布。

返回JSON格式（不要markdown）：
{{
    "hot_topics": ["关键词1", "关键词2", ...],
    "narrative_direction": "<舆论发展方向描述>",
    "initial_posts": [
        {{"content": "帖子内容", "poster_type": "实体类型（必须从可用类型中选择）"}},
        ...
    ],
    "reasoning": "<简要说明>"
}}"""

        system_prompt = "你是舆论分析专家。返回纯JSON格式。注意 poster_type 必须精确匹配可用实体类型。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Ereigniskonfigurations-LLM-Generierung fehlgeschlagen: {e}, Standard-Konfiguration wird verwendet")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Standard-Konfiguration verwendet"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Ereigniskonfigurationsergebnis parsen"""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Geeignete Veroeffentlicher-Agents fuer initiale Beitraege zuweisen

        Basierend auf dem poster_type jedes Beitrags den am besten passenden agent_id zuordnen
        """
        if not event_config.initial_posts:
            return event_config
        
        # Agent-Index nach Entitaetstyp erstellen
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # Typ-Zuordnungstabelle (verschiedene LLM-Ausgabeformate verarbeiten)
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # Bereits verwendete Agent-Indizes pro Typ aufzeichnen, um Wiederverwendung zu vermeiden
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # Versuchen, passenden Agent zu finden
            matched_agent_id = None
            
            # 1. Direkte Uebereinstimmung
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Alias-Uebereinstimmung
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. Falls immer noch nicht gefunden, Agent mit hoechstem Einfluss verwenden
            if matched_agent_id is None:
                logger.warning(f"Kein passender Agent fuer Typ '{poster_type}' gefunden, Agent mit hoechstem Einfluss wird verwendet")
                if agent_configs:
                    # Nach Einfluss sortieren, den mit hoechstem Einfluss waehlen
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"初始帖子分配: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Agent-Konfiguration batchweise generieren"""
        
        # Entitaetsinformationen erstellen (konfigurierte Zusammenfassungslaenge verwenden)
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""基于以下信息，为每个实体生成社交媒体活动配置。

模拟需求: {simulation_requirement}

## 实体列表
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## 任务
为每个实体生成活动配置，注意：
- **时间符合中国人作息**：凌晨0-5点几乎不活动，晚间19-22点最活跃
- **官方机构**（University/GovernmentAgency）：活跃度低(0.1-0.3)，工作时间(9-17)活动，响应慢(60-240分钟)，影响力高(2.5-3.0)
- **媒体**（MediaOutlet）：活跃度中(0.4-0.6)，全天活动(8-23)，响应快(5-30分钟)，影响力高(2.0-2.5)
- **个人**（Student/Person/Alumni）：活跃度高(0.6-0.9)，主要晚间活动(18-23)，响应快(1-15分钟)，影响力低(0.8-1.2)
- **公众人物/专家**：活跃度中(0.4-0.6)，影响力中高(1.5-2.0)

返回JSON格式（不要markdown）：
{{
    "agent_configs": [
        {{
            "agent_id": <必须与输入一致>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <发帖频率>,
            "comments_per_hour": <评论频率>,
            "active_hours": [<活跃小时列表，考虑中国人作息>],
            "response_delay_min": <最小响应延迟分钟>,
            "response_delay_max": <最大响应延迟分钟>,
            "sentiment_bias": <-1.0到1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <影响力权重>
        }},
        ...
    ]
}}"""

        system_prompt = "你是社交媒体行为分析专家。返回纯JSON，配置需符合中国人作息习惯。"
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Agent-Konfigurations-Batch-LLM-Generierung fehlgeschlagen: {e}, regelbasierte Generierung wird verwendet")
            llm_configs = {}
        
        # AgentActivityConfig-Objekte erstellen
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # Falls LLM nicht generiert hat, regelbasiert generieren
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Einzelne Agent-Konfiguration regelbasiert generieren (chinesischer Tagesablauf)"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # Offizielle Institutionen: Arbeitszeit-Aktivitaet, niedrige Frequenz, hoher Einfluss
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Medien: Ganztagsaktivitaet, mittlere Frequenz, hoher Einfluss
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Experten/Professoren: Arbeits- und Abendaktivitaet, mittlere Frequenz
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Studenten: Hauptsaechlich abends, hohe Frequenz
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Vormittag + Abend
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: Hauptsaechlich abends
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Mittagspause + Abend
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # Normalverbraucher: Abend-Spitzenzeit
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Tagsueher + Abend
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

