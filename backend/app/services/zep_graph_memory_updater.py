"""
Zep-Graph-Speicher-Aktualisierungsdienst
Agent-Aktivitaeten aus der Simulation dynamisch in den Zep-Graph aktualisieren
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent-Aktivitaetsprotokoll"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Aktivitaet in eine an Zep sendbare Textbeschreibung umwandeln

        Verwendet natuerliches Sprachformat, damit Zep Entitaeten und Beziehungen extrahieren kann
        Kein simulationsbezogenes Praefix hinzufuegen, um Fehlleitung bei der Graph-Aktualisierung zu vermeiden
        """
        # Verschiedene Beschreibungen je nach Aktionstyp generieren
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Direkt im Format "Agent-Name: Aktivitaetsbeschreibung" zurueckgeben, ohne Simulationspraefix
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"hat einen Beitrag veroeffentlicht: 「{content}」"
        return "hat einen Beitrag veroeffentlicht"
    
    def _describe_like_post(self) -> str:
        """Beitrag liken - enthaelt Original-Beitrag und Autoreninfo"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"hat den Beitrag von {post_author} geliked: 「{post_content}」"
        elif post_content:
            return f"hat einen Beitrag geliked: 「{post_content}」"
        elif post_author:
            return f"hat einen Beitrag von {post_author} geliked"
        return "hat einen Beitrag geliked"
    
    def _describe_dislike_post(self) -> str:
        """Beitrag disliken - enthaelt Original-Beitrag und Autoreninfo"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"hat den Beitrag von {post_author} gedisliked: 「{post_content}」"
        elif post_content:
            return f"hat einen Beitrag gedisliked: 「{post_content}」"
        elif post_author:
            return f"hat einen Beitrag von {post_author} gedisliked"
        return "hat einen Beitrag gedisliked"
    
    def _describe_repost(self) -> str:
        """Beitrag weiterleiten - enthaelt Originalbeitragsinhalt und Autoreninfo"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"hat den Beitrag von {original_author} weitergeleitet: 「{original_content}」"
        elif original_content:
            return f"hat einen Beitrag weitergeleitet: 「{original_content}」"
        elif original_author:
            return f"hat einen Beitrag von {original_author} weitergeleitet"
        return "hat einen Beitrag weitergeleitet"
    
    def _describe_quote_post(self) -> str:
        """Beitrag zitieren - enthaelt Originalbeitragsinhalt, Autoreninfo und Zitat-Kommentar"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"hat den Beitrag von {original_author} zitiert 「{original_content}」"
        elif original_content:
            base = f"hat einen Beitrag zitiert 「{original_content}」"
        elif original_author:
            base = f"hat einen Beitrag von {original_author} zitiert"
        else:
            base = "hat einen Beitrag zitiert"
        
        if quote_content:
            base += f", und kommentierte: 「{quote_content}」"
        return base
    
    def _describe_follow(self) -> str:
        """Benutzer folgen - enthaelt Name des gefolgten Benutzers"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"folgt dem Benutzer 「{target_user_name}」"
        return "folgt einem Benutzer"
    
    def _describe_create_comment(self) -> str:
        """Kommentar veroeffentlichen - enthaelt Kommentarinhalt und Beitragsinfo"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"hat unter dem Beitrag von {post_author} 「{post_content}」 kommentiert: 「{content}」"
            elif post_content:
                return f"hat unter dem Beitrag 「{post_content}」 kommentiert: 「{content}」"
            elif post_author:
                return f"hat unter dem Beitrag von {post_author} kommentiert: 「{content}」"
            return f"hat kommentiert: 「{content}」"
        return "hat einen Kommentar veroeffentlicht"
    
    def _describe_like_comment(self) -> str:
        """Kommentar liken - enthaelt Kommentarinhalt und Autoreninfo"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"hat den Kommentar von {comment_author} geliked: 「{comment_content}」"
        elif comment_content:
            return f"hat einen Kommentar geliked: 「{comment_content}」"
        elif comment_author:
            return f"hat einen Kommentar von {comment_author} geliked"
        return "hat einen Kommentar geliked"
    
    def _describe_dislike_comment(self) -> str:
        """Kommentar disliken - enthaelt Kommentarinhalt und Autoreninfo"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"hat den Kommentar von {comment_author} gedisliked: 「{comment_content}」"
        elif comment_content:
            return f"hat einen Kommentar gedisliked: 「{comment_content}」"
        elif comment_author:
            return f"hat einen Kommentar von {comment_author} gedisliked"
        return "hat einen Kommentar gedisliked"
    
    def _describe_search(self) -> str:
        """Beitraege suchen - enthaelt Suchbegriffe"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"hat nach 「{query}」 gesucht" if query else "hat eine Suche durchgefuehrt"
    
    def _describe_search_user(self) -> str:
        """Benutzer suchen - enthaelt Suchbegriffe"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"hat nach Benutzer 「{query}」 gesucht" if query else "hat nach Benutzern gesucht"
    
    def _describe_mute(self) -> str:
        """Benutzer stummschalten - enthaelt Name des stummgeschalteten Benutzers"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"hat den Benutzer 「{target_user_name}」 stummgeschaltet"
        return "hat einen Benutzer stummgeschaltet"
    
    def _describe_generic(self) -> str:
        # Fuer unbekannte Aktionstypen eine allgemeine Beschreibung generieren
        return f"hat die Aktion {self.action_type} ausgefuehrt"


class ZepGraphMemoryUpdater:
    """
    Zep-Graph-Speicher-Aktualisierer

    Ueberwacht die Actions-Logdateien der Simulation und aktualisiert neue Agent-Aktivitaeten in Echtzeit im Zep-Graph.
    Nach Plattform gruppiert, batchweise an Zep gesendet nach Ansammlung von BATCH_SIZE Aktivitaeten.

    Alle bedeutungsvollen Aktionen werden an Zep aktualisiert, action_args enthalten vollstaendige Kontextinformationen:
    - Originaltexte gelikter/gedislikter Beitraege
    - Originaltexte weitergeleiteter/zitierter Beitraege
    - Benutzernamen von gefolgten/stummgeschalteten Benutzern
    - Originaltexte gelikter/gedislikter Kommentare
    """
    
    # Batch-Sendegroesse (wie viele pro Plattform angesammelt werden bevor gesendet wird)
    BATCH_SIZE = 5
    
    # Plattformnamen-Zuordnung (fuer Konsolenausgabe)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': '世界1',
        'reddit': '世界2',
    }
    
    # Sendeintervall (Sekunden), um zu schnelle Anfragen zu vermeiden
    SEND_INTERVAL = 0.5
    
    # Wiederholungskonfiguration
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Aktualisierer initialisieren

        Args:
            graph_id: Zep-Graph-ID
            api_key: Zep API Key (optional, Standard wird aus Konfiguration gelesen)
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEY ist nicht konfiguriert")
        
        self.client = Zep(api_key=self.api_key)
        
        # Aktivitaetswarteschlange
        self._activity_queue: Queue = Queue()
        
        # Nach Plattform gruppierte Aktivitaets-Puffer (jede Plattform sendet batchweise nach Erreichen von BATCH_SIZE)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # Steuerungsflags
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistiken
        self._total_activities = 0  # 实际添加到队列的活动数
        self._total_sent = 0        # 成功发送到Zep的批次数
        self._total_items_sent = 0  # 成功发送到Zep的活动条数
        self._failed_count = 0      # 发送失败的批次数
        self._skipped_count = 0     # 被过滤跳过的活动数（DO_NOTHING）
        
        logger.info(f"ZepGraphMemoryUpdater 初始化完成: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Anzeigenamen der Plattform abrufen"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """Hintergrund-Arbeitsthread starten"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater 已启动: graph_id={self.graph_id}")
    
    def stop(self):
        """Hintergrund-Arbeitsthread stoppen"""
        self._running = False
        
        # Verbleibende Aktivitaeten senden
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"ZepGraphMemoryUpdater 已停止: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        Eine Agent-Aktivitaet zur Warteschlange hinzufuegen

        Alle bedeutungsvollen Aktionen werden der Warteschlange hinzugefuegt, darunter:
        - CREATE_POST (Beitrag erstellen)
        - CREATE_COMMENT (Kommentieren)
        - QUOTE_POST (Beitrag zitieren)
        - SEARCH_POSTS (Beitraege suchen)
        - SEARCH_USER (Benutzer suchen)
        - LIKE_POST/DISLIKE_POST (Beitrag liken/disliken)
        - REPOST (Weiterleiten)
        - FOLLOW (Folgen)
        - MUTE (Stummschalten)
        - LIKE_COMMENT/DISLIKE_COMMENT (Kommentar liken/disliken)

        action_args enthalten vollstaendige Kontextinformationen (z.B. Beitragsoriginaltext, Benutzername usw.).

        Args:
            activity: Agent-Aktivitaetsprotokoll
        """
        # Aktivitaeten vom Typ DO_NOTHING ueberspringen
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"添加活动到Zep队列: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Aktivitaet aus Woerterbuch-Daten hinzufuegen

        Args:
            data: Aus actions.jsonl geparste Woerterbuch-Daten
            platform: Plattformname (twitter/reddit)
        """
        # Eintraege vom Typ Ereignis ueberspringen
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self):
        """Hintergrund-Arbeitsschleife - Aktivitaeten batchweise nach Plattform an Zep senden"""
        while self._running or not self._activity_queue.empty():
            try:
                # Versuchen, Aktivitaet aus der Warteschlange abzurufen (Zeitlimit 1 Sekunde)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # Aktivitaet zum Puffer der entsprechenden Plattform hinzufuegen
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # Pruefen, ob diese Plattform die Batch-Groesse erreicht hat
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Nach Freigabe der Sperre senden
                            self._send_batch_activities(batch, platform)
                            # Sendeintervall, um zu schnelle Anfragen zu vermeiden
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"工作循环异常: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Aktivitaeten batchweise an den Zep-Graph senden (zu einem Text zusammengefuehrt)

        Args:
            activities: Agent-Aktivitaetsliste
            platform: Plattformname
        """
        if not activities:
            return
        
        # Mehrere Aktivitaeten zu einem Text zusammenfuehren, durch Zeilenumbrueche getrennt
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # Senden mit Wiederholung
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"成功批量发送 {len(activities)} 条{display_name}活动到图谱 {self.graph_id}")
                logger.debug(f"批量内容预览: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"批量发送到Zep失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"批量发送到Zep失败，已重试{self.MAX_RETRIES}次: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """Verbleibende Aktivitaeten aus Warteschlange und Puffer senden"""
        # Zuerst verbleibende Aktivitaeten aus der Warteschlange verarbeiten und zum Puffer hinzufuegen
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # Dann verbleibende Aktivitaeten in den Plattform-Puffern senden (auch wenn weniger als BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"发送{display_name}平台剩余的 {len(buffer)} 条活动")
                    self._send_batch_activities(buffer, platform)
            # Alle Puffer leeren
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistikinformationen abrufen"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # 添加到队列的活动总数
            "batches_sent": self._total_sent,            # 成功发送的批次数
            "items_sent": self._total_items_sent,        # 成功发送的活动条数
            "failed_count": self._failed_count,          # 发送失败的批次数
            "skipped_count": self._skipped_count,        # 被过滤跳过的活动数（DO_NOTHING）
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # 各平台缓冲区大小
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    Manager fuer Zep-Graph-Speicher-Aktualisierer mehrerer Simulationen

    Jede Simulation kann eine eigene Aktualisierer-Instanz haben
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        Graph-Speicher-Aktualisierer fuer Simulation erstellen

        Args:
            simulation_id: Simulations-ID
            graph_id: Zep-Graph-ID

        Returns:
            ZepGraphMemoryUpdater-Instanz
        """
        with cls._lock:
            # Falls bereits vorhanden, zuerst den alten stoppen
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"创建图谱记忆更新器: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Aktualisierer der Simulation abrufen"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Aktualisierer der Simulation stoppen und entfernen"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"已停止图谱记忆更新器: simulation_id={simulation_id}")
    
    # Flag zur Vermeidung wiederholter stop_all-Aufrufe
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """Alle Aktualisierer stoppen"""
        # Wiederholte Aufrufe verhindern
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"停止更新器失败: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("已停止所有图谱记忆更新器")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Statistikinformationen aller Aktualisierer abrufen"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
