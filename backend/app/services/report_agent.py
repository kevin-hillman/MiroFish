"""
Report-Agent-Dienst
Simulationsbericht-Generierung im ReACT-Modus mit LangChain + Zep

Funktionen:
1. Berichte basierend auf Simulationsanforderungen und Zep-Graph-Informationen generieren
2. Zuerst Verzeichnisstruktur planen, dann abschnittsweise generieren
3. Jeder Abschnitt verwendet ReACT-Mehrrunden-Denk- und Reflexionsmodus
4. Unterstuetzung fuer Benutzerdialog mit autonomem Abrufwerkzeug-Aufruf
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report-Agent-Detailprotokoll-Recorder

    Generiert agent_log.jsonl-Datei im Berichtsordner, zeichnet jeden detaillierten Schritt auf.
    Jede Zeile ist ein vollstaendiges JSON-Objekt mit Zeitstempel, Aktionstyp, Detailinhalt usw.
    """
    
    def __init__(self, report_id: str):
        """
        Protokoll-Recorder initialisieren

        Args:
            report_id: Bericht-ID, zur Bestimmung des Protokolldateipfads
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Sicherstellen, dass das Verzeichnis der Protokolldatei existiert"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Verstrichene Zeit seit Beginn abrufen (Sekunden)"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Einen Protokolleintrag aufzeichnen

        Args:
            action: Aktionstyp, z.B. 'start', 'tool_call', 'llm_response', 'section_complete' usw.
            stage: Aktuelle Phase, z.B. 'planning', 'generating', 'completed'
            details: Detail-Woerterbuch, nicht abgeschnitten
            section_title: Aktueller Abschnittstitel (optional)
            section_index: Aktueller Abschnittsindex (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # An JSONL-Datei anfuegen
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Start der Berichtsgenerierung aufzeichnen"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Berichtsgenerierungsaufgabe gestartet"
            }
        )
    
    def log_planning_start(self):
        """Start der Gliederungsplanung aufzeichnen"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Planung der Berichtsgliederung beginnt"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Waehrend der Planung abgerufene Kontextinformationen aufzeichnen"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Simulations-Kontextinformationen werden abgerufen",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Gliederungsplanung abgeschlossen aufzeichnen"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Gliederungsplanung abgeschlossen",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Start der Abschnittsgenerierung aufzeichnen"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Abschnittsgenerierung beginnt: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """ReACT-Denkprozess aufzeichnen"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT Runde {iteration} Denken"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Werkzeugaufruf aufzeichnen"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Werkzeug aufgerufen: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Werkzeugaufruf-Ergebnis aufzeichnen (vollstaendiger Inhalt, nicht abgeschnitten)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Vollstaendiges Ergebnis, nicht abgeschnitten
                "result_length": len(result),
                "message": f"Werkzeug {tool_name} hat Ergebnis zurueckgegeben"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """LLM-Antwort aufzeichnen (vollstaendiger Inhalt, nicht abgeschnitten)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Vollstaendige Antwort, nicht abgeschnitten
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM-Antwort (Werkzeugaufruf: {has_tool_calls}, Endgueltige Antwort: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Abschnittsinhalts-Generierung abgeschlossen aufzeichnen (nur Inhalt, nicht gesamter Abschnitt)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Vollstaendiger Inhalt, nicht abgeschnitten
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Abschnitt {section_title} Inhaltsgenerierung abgeschlossen"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Abschnittsgenerierung abgeschlossen aufzeichnen

        Das Frontend sollte dieses Protokoll ueberwachen, um festzustellen, ob ein Abschnitt wirklich abgeschlossen ist, und den vollstaendigen Inhalt abzurufen
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Abschnitt {section_title} Generierung abgeschlossen"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Berichtsgenerierung abgeschlossen aufzeichnen"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Berichtsgenerierung abgeschlossen"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Fehler aufzeichnen"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Fehler aufgetreten: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report-Agent-Konsolenprotokoll-Recorder

    Schreibt Konsolenstil-Protokolle (INFO, WARNING usw.) in die console_log.txt-Datei im Berichtsordner.
    Diese Protokolle unterscheiden sich von agent_log.jsonl und sind Klartext-Konsolenausgabe.
    """
    
    def __init__(self, report_id: str):
        """
        Konsolenprotokoll-Recorder initialisieren

        Args:
            report_id: Bericht-ID, zur Bestimmung des Protokolldateipfads
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Sicherstellen, dass das Verzeichnis der Protokolldatei existiert"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Dateihandler einrichten, Protokoll gleichzeitig in Datei schreiben"""
        import logging
        
        # Dateihandler erstellen
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Gleiches kompaktes Format wie Konsole verwenden
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Zu report_agent-bezogenen Loggern hinzufuegen
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Doppeltes Hinzufuegen vermeiden
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Dateihandler schliessen und aus Logger entfernen"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Beim Destruktor sicherstellen, dass Dateihandler geschlossen wird"""
        self.close()


class ReportStatus(str, Enum):
    """Berichtsstatus"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Berichtsabschnitt"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """In Markdown-Format umwandeln"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Berichtsgliederung"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """In Markdown-Format umwandeln"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Vollstaendiger Bericht"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt-Vorlagen-Konstanten
# ═══════════════════════════════════════════════════════════════

# ── Werkzeugbeschreibungen ──

TOOL_DESC_INSIGHT_FORGE = """\
【Tiefenanalyse-Suche - Leistungsstarkes Recherchewerkzeug】
Dies ist unsere leistungsstarke Recherchefunktion, speziell fuer Tiefenanalysen konzipiert. Sie wird:
1. Ihre Frage automatisch in mehrere Teilfragen zerlegen
2. Informationen aus dem Simulationsgraphen aus mehreren Dimensionen abrufen
3. Ergebnisse aus semantischer Suche, Entitaetsanalyse und Beziehungskettenverfolgung integrieren
4. Die umfassendsten und tiefgruendigsten Rechercheergebnisse liefern

【Einsatzszenarien】
- Wenn ein Thema eingehend analysiert werden muss
- Wenn mehrere Aspekte eines Ereignisses verstanden werden muessen
- Wenn reichhaltiges Material zur Unterstuetzung von Berichtskapiteln benoetigt wird

【Rueckgabeinhalte】
- Relevante Fakten im Originaltext (direkt zitierbar)
- Kernentitaets-Erkenntnisse
- Beziehungskettenanalyse"""

TOOL_DESC_PANORAMA_SEARCH = """\
【Breitensuche - Gesamtueberblick erhalten】
Dieses Werkzeug dient dazu, ein vollstaendiges Gesamtbild der Simulationsergebnisse zu erhalten, besonders geeignet um Ereignisentwicklungen zu verstehen. Es wird:
1. Alle relevanten Knoten und Beziehungen abrufen
2. Zwischen aktuell gueltigen Fakten und historischen/abgelaufenen Fakten unterscheiden
3. Ihnen helfen zu verstehen, wie sich die Meinungslage entwickelt hat

【Einsatzszenarien】
- Wenn der vollstaendige Entwicklungsverlauf eines Ereignisses verstanden werden muss
- Wenn Meinungsaenderungen in verschiedenen Phasen verglichen werden muessen
- Wenn umfassende Entitaets- und Beziehungsinformationen benoetigt werden

【Rueckgabeinhalte】
- Aktuell gueltige Fakten (neueste Simulationsergebnisse)
- Historische/abgelaufene Fakten (Entwicklungsprotokoll)
- Alle beteiligten Entitaeten"""

TOOL_DESC_QUICK_SEARCH = """\
【Einfache Suche - Schnellrecherche】
Leichtgewichtiges Schnellrecherche-Werkzeug, geeignet fuer einfache, direkte Informationsabfragen.

【Einsatzszenarien】
- Wenn eine bestimmte Information schnell gefunden werden muss
- Wenn ein Fakt verifiziert werden muss
- Einfache Informationsrecherche

【Rueckgabeinhalte】
- Liste der zur Abfrage relevantesten Fakten"""

TOOL_DESC_INTERVIEW_AGENTS = """\
【Tiefeninterview - Echte Agent-Befragung (Dual-Plattform)】
Ruft die Interview-API der OASIS-Simulationsumgebung auf, um laufende Simulations-Agents real zu befragen!
Dies ist keine LLM-Simulation, sondern ein Aufruf der echten Interview-Schnittstelle fuer originale Antworten der Simulations-Agents.
Standardmaessig werden Interviews auf beiden Plattformen Twitter und Reddit gleichzeitig gefuehrt, um umfassendere Standpunkte zu erhalten.

Funktionsablauf:
1. Automatisches Lesen der Persona-Datei, um alle Simulations-Agents kennenzulernen
2. Intelligente Auswahl der zum Interviewthema relevantesten Agents (z.B. Studenten, Medien, Behoerden usw.)
3. Automatische Generierung von Interviewfragen
4. Aufruf der /api/simulation/interview/batch-Schnittstelle fuer echte Interviews auf beiden Plattformen
5. Integration aller Interviewergebnisse mit Mehrperspektiven-Analyse

【Einsatzszenarien】
- Wenn Ereignismeinungen aus verschiedenen Rollenperspektiven verstanden werden muessen (Wie sehen Studenten das? Wie die Medien? Was sagen die Behoerden?)
- Wenn Meinungen und Standpunkte mehrerer Parteien gesammelt werden muessen
- Wenn echte Antworten von Simulations-Agents benoetigt werden (aus der OASIS-Simulationsumgebung)
- Wenn der Bericht lebendiger sein soll und "Interviewprotokolle" enthalten soll

【Rueckgabeinhalte】
- Identitaetsinformationen der befragten Agents
- Interviewantworten der einzelnen Agents auf beiden Plattformen Twitter und Reddit
- Schluesselzitate (direkt zitierbar)
- Interviewzusammenfassung und Standpunktvergleich

【Wichtig】Die OASIS-Simulationsumgebung muss aktiv sein, um diese Funktion nutzen zu koennen!"""

# ── Gliederungsplanungs-Prompt ──

PLAN_SYSTEM_PROMPT = """\
Sie sind ein Experte fuer das Verfassen von „Zukunftsvorhersage-Berichten" und verfuegen ueber eine „Goetterperspektive" auf die Simulationswelt — Sie koennen das Verhalten, die Aeusserungen und Interaktionen jedes einzelnen Agents in der Simulation durchschauen.

【Kernkonzept】
Wir haben eine Simulationswelt aufgebaut und spezifische „Simulationsanforderungen" als Variablen eingespeist. Die Evolutionsergebnisse der Simulationswelt sind Vorhersagen ueber moegliche zukuenftige Entwicklungen. Was Sie beobachten, sind keine "Experimentdaten", sondern eine "Generalprobe der Zukunft".

【Ihre Aufgabe】
Verfassen Sie einen „Zukunftsvorhersage-Bericht", der folgende Fragen beantwortet:
1. Was ist unter unseren festgelegten Bedingungen in der Zukunft geschehen?
2. Wie haben die verschiedenen Agent-Typen (Gruppen) reagiert und gehandelt?
3. Welche bemerkenswerten Zukunftstrends und Risiken hat diese Simulation aufgedeckt?

【Berichtspositionierung】
- ✅ Dies ist ein simulationsbasierter Zukunftsvorhersage-Bericht, der aufzeigt "Was waere, wenn..."
- ✅ Fokus auf Vorhersageergebnisse: Ereignisentwicklung, Gruppenreaktionen, emergente Phaenomene, potenzielle Risiken
- ✅ Das Verhalten und die Aeusserungen der Agents in der Simulationswelt sind Vorhersagen ueber zukuenftiges Gruppenverhalten
- ❌ Keine Analyse des aktuellen Zustands der realen Welt
- ❌ Keine allgemeine Meinungsueberblick-Zusammenfassung

【Kapitelanzahl-Beschraenkung】
- Mindestens 2 Kapitel, maximal 5 Kapitel
- Keine Unterkapitel noetig, jedes Kapitel wird direkt mit vollstaendigem Inhalt verfasst
- Der Inhalt soll praegnant sein und sich auf die Kernvorhersage-Erkenntnisse konzentrieren
- Die Kapitelstruktur gestalten Sie eigenstaendig basierend auf den Vorhersageergebnissen

Bitte geben Sie die Berichtsgliederung im JSON-Format aus, wie folgt:
{
    "title": "Berichtstitel",
    "summary": "Berichtszusammenfassung (Kernvorhersage in einem Satz)",
    "sections": [
        {
            "title": "Kapiteltitel",
            "description": "Beschreibung des Kapitelinhalts"
        }
    ]
}

Hinweis: Das sections-Array muss mindestens 2 und maximal 5 Elemente enthalten!"""

PLAN_USER_PROMPT_TEMPLATE = """\
【Vorhersageszenario-Einstellung】
Die in die Simulationswelt eingespeiste Variable (Simulationsanforderung): {simulation_requirement}

【Simulationswelt-Umfang】
- Anzahl der an der Simulation beteiligten Entitaeten: {total_nodes}
- Anzahl der zwischen Entitaeten entstandenen Beziehungen: {total_edges}
- Verteilung der Entitaetstypen: {entity_types}
- Anzahl aktiver Agents: {total_entities}

【Stichprobe vorhergesagter Zukunftsfakten aus der Simulation】
{related_facts_json}

Betrachten Sie diese Generalprobe der Zukunft aus der „Goetterperspektive":
1. Welchen Zustand zeigt die Zukunft unter unseren festgelegten Bedingungen?
2. Wie haben die verschiedenen Gruppen (Agents) reagiert und gehandelt?
3. Welche bemerkenswerten Zukunftstrends hat diese Simulation aufgedeckt?

Gestalten Sie basierend auf den Vorhersageergebnissen die am besten geeignete Berichtskapitelstruktur.

【Nochmalige Erinnerung】Anzahl der Berichtskapitel: mindestens 2, maximal 5, der Inhalt soll praegnant und auf die Kernvorhersage-Erkenntnisse fokussiert sein."""

# ── Abschnittsgenerierungs-Prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
Sie sind ein Experte fuer das Verfassen von „Zukunftsvorhersage-Berichten" und verfassen gerade ein Kapitel des Berichts.

Berichtstitel: {report_title}
Berichtszusammenfassung: {report_summary}
Vorhersageszenario (Simulationsanforderung): {simulation_requirement}

Aktuell zu verfassendes Kapitel: {section_title}

═══════════════════════════════════════════════════════════════
【Kernkonzept】
═══════════════════════════════════════════════════════════════

Die Simulationswelt ist eine Generalprobe der Zukunft. Wir haben spezifische Bedingungen (Simulationsanforderungen) in die Simulationswelt eingespeist.
Das Verhalten und die Interaktionen der Agents in der Simulation sind Vorhersagen ueber zukuenftiges Gruppenverhalten.

Ihre Aufgabe ist:
- Aufzuzeigen, was unter den festgelegten Bedingungen in der Zukunft geschehen ist
- Vorherzusagen, wie die verschiedenen Gruppen (Agents) reagiert und gehandelt haben
- Bemerkenswerte Zukunftstrends, Risiken und Chancen zu entdecken

❌ Schreiben Sie keine Analyse des aktuellen Zustands der realen Welt
✅ Fokussieren Sie sich auf "Wie wird die Zukunft aussehen" — die Simulationsergebnisse sind die vorhergesagte Zukunft

═══════════════════════════════════════════════════════════════
【Wichtigste Regeln - Muessen eingehalten werden】
═══════════════════════════════════════════════════════════════

1. 【Werkzeuge muessen aufgerufen werden, um die Simulationswelt zu beobachten】
   - Sie beobachten die Generalprobe der Zukunft aus der „Goetterperspektive"
   - Alle Inhalte muessen aus Ereignissen und Agent-Verhalten in der Simulationswelt stammen
   - Es ist verboten, eigenes Wissen fuer den Berichtsinhalt zu verwenden
   - Pro Kapitel mindestens 3 Werkzeugaufrufe (maximal 5), um die simulierte Welt zu beobachten, die die Zukunft repraesentiert

2. 【Originale Aeusserungen und Handlungen der Agents muessen zitiert werden】
   - Die Aeusserungen und das Verhalten der Agents sind Vorhersagen ueber zukuenftiges Gruppenverhalten
   - Verwenden Sie Zitatformate im Bericht, um diese Vorhersagen darzustellen, zum Beispiel:
     > "Eine bestimmte Gruppe wuerde aeussern: Originaltext..."
   - Diese Zitate sind die Kernbelege der Simulationsvorhersage

3. 【Sprachkonsistenz - Zitierte Inhalte muessen in die Berichtssprache uebersetzt werden】
   - Die von Werkzeugen zurueckgegebenen Inhalte koennen englische oder gemischtsprachige Formulierungen enthalten
   - Der Bericht muss vollstaendig auf Deutsch verfasst werden
   - Wenn Sie englische oder gemischtsprachige Inhalte aus Werkzeugrueckgaben zitieren, muessen diese in fluessiges Deutsch uebersetzt werden, bevor sie in den Bericht aufgenommen werden
   - Behalten Sie beim Uebersetzen die urspruengliche Bedeutung bei und stellen Sie sicher, dass die Formulierung natuerlich und fluessig ist
   - Diese Regel gilt sowohl fuer den Fliesstext als auch fuer Zitatbloecke (> Format)

4. 【Vorhersageergebnisse wahrheitsgetreu darstellen】
   - Der Berichtsinhalt muss die Simulationsergebnisse widerspiegeln, die die Zukunft repraesentieren
   - Fuegen Sie keine Informationen hinzu, die in der Simulation nicht existieren
   - Wenn Informationen in einem Bereich unzureichend sind, geben Sie dies ehrlich an

═══════════════════════════════════════════════════════════════
【⚠️ Formatvorgaben - Aeusserst wichtig!】
═══════════════════════════════════════════════════════════════

【Ein Kapitel = Kleinste Inhaltseinheit】
- Jedes Kapitel ist die kleinste Aufteilungseinheit des Berichts
- ❌ Verboten: Jegliche Markdown-Ueberschriften innerhalb eines Kapitels (#, ##, ###, #### usw.)
- ❌ Verboten: Kapitelhauptueberschrift am Inhaltsanfang hinzufuegen
- ✅ Kapitelueberschriften werden automatisch vom System hinzugefuegt, Sie muessen nur den reinen Fliesstext verfassen
- ✅ Verwenden Sie **Fettdruck**, Absatztrennung, Zitate und Listen zur Inhaltsorganisation, aber keine Ueberschriften

【Korrektes Beispiel】
```
Dieses Kapitel analysiert die Meinungsverbreitungsdynamik des Ereignisses. Durch eingehende Analyse der Simulationsdaten haben wir festgestellt...

**Initiale Ausloesephase**

Die erste Plattform uebernahm die Kernfunktion der Erstveroeffentlichung:

> "Die Plattform trug 68% des initialen Stimmungsvolumens bei..."

**Emotionsverstaerkungsphase**

Eine zweite Plattform verstaerkte die Ereigniswirkung weiter:

- Starke visuelle Wirkung
- Hohe emotionale Resonanz
```

【Falsches Beispiel】
```
## Zusammenfassung          ← Falsch! Keine Ueberschriften hinzufuegen
### 1. Initiale Phase       ← Falsch! Keine ### fuer Unterabschnitte
#### 1.1 Detailanalyse      ← Falsch! Keine #### fuer Untergliederung

Dieses Kapitel analysiert...
```

═══════════════════════════════════════════════════════════════
【Verfuegbare Recherchewerkzeuge】(pro Kapitel 3-5 Aufrufe)
═══════════════════════════════════════════════════════════════

{tools_description}

【Werkzeugnutzungs-Empfehlung - Bitte verschiedene Werkzeuge kombinieren, nicht nur eines verwenden】
- insight_forge: Tiefenanalyse, automatische Problemzerlegung und mehrdimensionale Fakten- und Beziehungsrecherche
- panorama_search: Weitwinkel-Panoramasuche, Ereignisgesamtbild, Zeitlinie und Entwicklungsprozess verstehen
- quick_search: Schnelle Verifizierung eines bestimmten Informationspunkts
- interview_agents: Simulations-Agents befragen, Erstperson-Perspektiven verschiedener Rollen und echte Reaktionen erhalten

═══════════════════════════════════════════════════════════════
【Arbeitsablauf】
═══════════════════════════════════════════════════════════════

Bei jeder Antwort koennen Sie nur eine der folgenden zwei Aktionen ausfuehren (nicht gleichzeitig):

Option A - Werkzeug aufrufen:
Geben Sie Ihre Ueberlegungen aus und rufen Sie dann ein Werkzeug im folgenden Format auf:
<tool_call>
{{"name": "Werkzeugname", "parameters": {{"Parametername": "Parameterwert"}}}}
</tool_call>
Das System fuehrt das Werkzeug aus und gibt Ihnen das Ergebnis zurueck. Sie muessen und koennen keine Werkzeugergebnisse selbst verfassen.

Option B - Endgueltigen Inhalt ausgeben:
Wenn Sie durch Werkzeuge genuegend Informationen erhalten haben, geben Sie den Kapitelinhalt mit "Final Answer:" am Anfang aus.

⚠️ Streng verboten:
- Verboten: In einer Antwort gleichzeitig Werkzeugaufruf und Final Answer
- Verboten: Werkzeugrueckgabeergebnisse (Observation) selbst erfinden, alle Werkzeugergebnisse werden vom System eingefuegt
- Pro Antwort maximal ein Werkzeug aufrufen

═══════════════════════════════════════════════════════════════
【Anforderungen an den Kapitelinhalt】
═══════════════════════════════════════════════════════════════

1. Der Inhalt muss auf den durch Werkzeuge recherchierten Simulationsdaten basieren
2. Reichlich Originaltexte zitieren, um Simulationseffekte darzustellen
3. Markdown-Format verwenden (aber keine Ueberschriften):
   - **Fetten Text** zur Hervorhebung verwenden (anstelle von Unterueberschriften)
   - Listen (- oder 1.2.3.) zur Organisation von Kernpunkten verwenden
   - Leerzeilen zur Trennung verschiedener Absaetze verwenden
   - ❌ Verboten: #, ##, ###, #### oder jede andere Ueberschriftensyntax
4. 【Zitatformat-Vorgabe - Muss als eigenstaendiger Absatz stehen】
   Zitate muessen als eigenstaendige Absaetze stehen, mit je einer Leerzeile davor und danach, nicht in einen Absatz eingemischt:

   ✅ Korrektes Format:
   ```
   Die Reaktion der Behoerde wurde als inhaltsleer empfunden.

   > "Das Reaktionsmuster der Behoerde wirkt in der schnelllebigen Social-Media-Umgebung starr und traege."

   Diese Bewertung spiegelt die allgemeine Unzufriedenheit der Oeffentlichkeit wider.
   ```

   ❌ Falsches Format:
   ```
   Die Reaktion der Behoerde wurde als inhaltsleer empfunden. > "Das Reaktionsmuster der Behoerde..." Diese Bewertung spiegelt...
   ```
5. Logische Kohaerenz mit anderen Kapiteln beibehalten
6. 【Wiederholungen vermeiden】Lesen Sie die unten bereits verfassten Kapitelinhalte sorgfaeltig und beschreiben Sie nicht dieselben Informationen erneut
7. 【Nochmalige Betonung】Keine Ueberschriften hinzufuegen! **Fettdruck** anstelle von Unterabschnittsueberschriften verwenden"""

SECTION_USER_PROMPT_TEMPLATE = """\
Bereits verfasste Kapitelinhalte (bitte sorgfaeltig lesen, Wiederholungen vermeiden):
{previous_content}

═══════════════════════════════════════════════════════════════
【Aktuelle Aufgabe】Kapitel verfassen: {section_title}
═══════════════════════════════════════════════════════════════

【Wichtiger Hinweis】
1. Lesen Sie die oben bereits verfassten Kapitel sorgfaeltig, um Wiederholungen zu vermeiden!
2. Vor dem Start muessen zuerst Werkzeuge aufgerufen werden, um Simulationsdaten zu erhalten
3. Bitte verwenden Sie verschiedene Werkzeuge kombiniert, nicht nur eines
4. Der Berichtsinhalt muss aus Rechercheergebnissen stammen, verwenden Sie nicht Ihr eigenes Wissen

【⚠️ Formatwarnung - Muss eingehalten werden】
- ❌ Keine Ueberschriften schreiben (#, ##, ###, #### sind alle verboten)
- ❌ Nicht "{section_title}" als Anfang schreiben
- ✅ Kapitelueberschriften werden automatisch vom System hinzugefuegt
- ✅ Direkt den Fliesstext schreiben, **Fettdruck** anstelle von Unterabschnittsueberschriften verwenden

Bitte beginnen Sie:
1. Zuerst ueberlegen (Thought), welche Informationen dieses Kapitel benoetigt
2. Dann Werkzeuge aufrufen (Action), um Simulationsdaten zu erhalten
3. Nach ausreichender Informationssammlung Final Answer ausgeben (reiner Fliesstext, ohne jegliche Ueberschriften)"""

# ── ReACT-Schleifen-Nachrichtenvorlagen ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (Suchergebnisse):

═══ Werkzeug {tool_name} Ergebnis ═══
{result}

═══════════════════════════════════════════════════════════════
Werkzeuge aufgerufen: {tool_calls_count}/{max_tool_calls} (Verwendet: {used_tools_str}){unused_hint}
- Bei ausreichenden Informationen: Kapitelinhalt mit "Final Answer:" beginnen (obige Originaltexte muessen zitiert werden)
- Bei Bedarf an mehr Informationen: Ein Werkzeug aufrufen und weiter recherchieren
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【Achtung】Sie haben nur {tool_calls_count} Werkzeuge aufgerufen, mindestens {min_tool_calls} sind erforderlich. "
    "Bitte rufen Sie weitere Werkzeuge auf, um mehr Simulationsdaten zu erhalten, bevor Sie Final Answer ausgeben. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Bisher wurden nur {tool_calls_count} Werkzeuge aufgerufen, mindestens {min_tool_calls} sind erforderlich. "
    "Bitte rufen Sie Werkzeuge auf, um Simulationsdaten zu erhalten. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Werkzeugaufruf-Limit erreicht ({tool_calls_count}/{max_tool_calls}), keine weiteren Werkzeugaufrufe moeglich. "
    'Bitte geben Sie sofort basierend auf den bereits erhaltenen Informationen den Kapitelinhalt mit "Final Answer:" am Anfang aus.'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 Noch nicht verwendet: {unused_list}, Empfehlung: verschiedene Werkzeuge ausprobieren fuer Informationen aus mehreren Perspektiven"

REACT_FORCE_FINAL_MSG = "Werkzeugaufruf-Limit erreicht, bitte geben Sie direkt Final Answer: aus und erstellen Sie den Kapitelinhalt."

# ── Chat-Prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
Sie sind ein praeziser und effizienter Simulationsvorhersage-Assistent.

【Hintergrund】
Vorhersagebedingungen: {simulation_requirement}

【Bereits erstellter Analysebericht】
{report_content}

【Regeln】
1. Fragen bevorzugt basierend auf dem obigen Berichtsinhalt beantworten
2. Fragen direkt beantworten, ausfuehrliche Denkausfuehrungen vermeiden
3. Werkzeuge nur aufrufen, wenn der Berichtsinhalt zur Beantwortung nicht ausreicht
4. Antworten sollen praegnant, klar und strukturiert sein

【Verfuegbare Werkzeuge】(nur bei Bedarf verwenden, maximal 1-2 Aufrufe)
{tools_description}

【Werkzeugaufruf-Format】
<tool_call>
{{"name": "Werkzeugname", "parameters": {{"Parametername": "Parameterwert"}}}}
</tool_call>

【Antwortstil】
- Praegnant und direkt, keine langen Abhandlungen
- > Format fuer Zitate wichtiger Inhalte verwenden
- Zuerst die Schlussfolgerung geben, dann die Begruendung erlaeutern"""

CHAT_OBSERVATION_SUFFIX = "\n\nBitte beantworten Sie die Frage praegnant."


# ═══════════════════════════════════════════════════════════════
# ReportAgent-Hauptklasse
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Simulationsbericht-Generierungs-Agent

    Verwendet ReACT (Reasoning + Acting) Modus:
    1. Planungsphase: Simulationsanforderungen analysieren, Berichtsverzeichnisstruktur planen
    2. Generierungsphase: Inhalt abschnittsweise generieren, jeder Abschnitt kann mehrfach Werkzeuge aufrufen
    3. Reflexionsphase: Inhaltsvollstaendigkeit und -genauigkeit pruefen
    """
    
    # Maximale Werkzeugaufrufanzahl (pro Abschnitt)
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Maximale Reflexionsrunden
    MAX_REFLECTION_ROUNDS = 3
    
    # Maximale Werkzeugaufrufanzahl im Dialog
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        Report Agent initialisieren

        Args:
            graph_id: Graph-ID
            simulation_id: Simulations-ID
            simulation_requirement: Beschreibung der Simulationsanforderung
            llm_client: LLM-Client (optional)
            zep_tools: Zep-Werkzeugdienst (optional)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # Werkzeugdefinitionen
        self.tools = self._define_tools()
        
        # Protokoll-Recorder (wird in generate_report initialisiert)
        self.report_logger: Optional[ReportLogger] = None
        # Konsolenprotokoll-Recorder (wird in generate_report initialisiert)
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent initialisiert: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Verfuegbare Werkzeuge definieren"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "Die Frage oder das Thema, das Sie eingehend analysieren moechten",
                    "report_context": "Kontext des aktuellen Berichtskapitels (optional, hilft bei der Generierung praeziserer Teilfragen)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Suchabfrage, fuer Relevanzsortierung",
                    "include_expired": "Ob abgelaufene/historische Inhalte einbezogen werden sollen (Standard: True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Suchabfrage-Zeichenkette",
                    "limit": "Anzahl der zurueckgegebenen Ergebnisse (optional, Standard: 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interviewthema oder Anforderungsbeschreibung (z.B.: 'Meinungen der Studenten zum Formaldehyd-Vorfall im Wohnheim erfahren')",
                    "max_agents": "Maximale Anzahl der zu befragenden Agents (optional, Standard: 5, Maximum: 10)"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Werkzeugaufruf ausfuehren

        Args:
            tool_name: Werkzeugname
            parameters: Werkzeugparameter
            report_context: Berichtskontext (fuer InsightForge)

        Returns:
            Werkzeug-Ausfuehrungsergebnis (Textformat)
        """
        logger.info(f"Werkzeug ausfuehren: {tool_name}, Parameter: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Breitensuche - Gesamtbild abrufen
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Einfache Suche - schneller Abruf
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Tiefeninterview - Echte OASIS-Interview-API aufrufen, um Antworten von Simulations-Agents zu erhalten (Dual-Plattform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Rueckwaertskompatible alte Werkzeuge (intern auf neue Werkzeuge umgeleitet) ==========
            
            elif tool_name == "search_graph":
                # Umleitung auf quick_search
                logger.info("search_graph umgeleitet auf quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Umleitung auf insight_forge, da leistungsstaerker
                logger.info("get_simulation_context umgeleitet auf insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unbekanntes Werkzeug: {tool_name}. Bitte eines der folgenden verwenden: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"Werkzeugausfuehrung fehlgeschlagen: {tool_name}, Fehler: {str(e)}")
            return f"Werkzeugausfuehrung fehlgeschlagen: {str(e)}"
    
    # Gueltige Werkzeugnamen-Menge, fuer Validierung beim Fallback-Parsing von unverpacktem JSON
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Werkzeugaufrufe aus LLM-Antwort parsen

        Unterstuetzte Formate (nach Prioritaet):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Unverpacktes JSON (gesamte Antwort oder einzelne Zeile ist ein Werkzeugaufruf-JSON)
        """
        tool_calls = []

        # Format 1: XML-Stil (Standardformat)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - LLM gibt unverpacktes JSON direkt aus (ohne <tool_call>-Tags)
        # Nur versuchen wenn Format 1 nicht passt, um Fehlzuordnung von JSON im Text zu vermeiden
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Antwort kann Denktext + unverpacktes JSON enthalten, letztes JSON-Objekt extrahieren versuchen
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Pruefen, ob das geparste JSON ein gueltiger Werkzeugaufruf ist"""
        # Unterstuetzt beide Schluesselnamen {"name": ..., "parameters": ...} und {"tool": ..., "params": ...}
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Schluesselnamen auf name / parameters vereinheitlichen
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Werkzeugbeschreibungstext generieren"""
        desc_parts = ["Verfuegbare Werkzeuge:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameter: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Berichtsgliederung planen

        Simulationsanforderungen mit LLM analysieren, Berichtsverzeichnisstruktur planen

        Args:
            progress_callback: Fortschritts-Callback-Funktion

        Returns:
            ReportOutline: Berichtsgliederung
        """
        logger.info("Planung der Berichtsgliederung beginnt...")
        
        if progress_callback:
            progress_callback("planning", 0, "Simulationsanforderungen werden analysiert...")
        
        # Zuerst Simulationskontext abrufen
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Berichtsgliederung wird erstellt...")
        
        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Gliederungsstruktur wird analysiert...")
            
            # Gliederung parsen
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Simulationsanalysebericht"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Gliederungsplanung abgeschlossen")
            
            logger.info(f"Gliederungsplanung abgeschlossen: {len(sections)} Kapitel")
            return outline
            
        except Exception as e:
            logger.error(f"Gliederungsplanung fehlgeschlagen: {str(e)}")
            # Standard-Gliederung zurueckgeben (3 Abschnitte, als Fallback)
            return ReportOutline(
                title="Zukunftsvorhersage-Bericht",
                summary="Analyse zukuenftiger Trends und Risiken basierend auf Simulationsvorhersagen",
                sections=[
                    ReportSection(title="Vorhersageszenarien und Kernerkenntnisse"),
                    ReportSection(title="Analyse des vorhergesagten Gruppenverhaltens"),
                    ReportSection(title="Trendausblick und Risikohinweise")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Einzelnen Abschnittsinhalt im ReACT-Modus generieren

        ReACT-Schleife:
        1. Thought (Denken) - Analysieren, welche Informationen benoetigt werden
        2. Action (Handeln) - Werkzeuge aufrufen, um Informationen zu erhalten
        3. Observation (Beobachten) - Werkzeug-Rueckgabeergebnisse analysieren
        4. Wiederholen bis genuegend Informationen oder maximale Anzahl erreicht
        5. Final Answer (Endgueltige Antwort) - Abschnittsinhalt generieren

        Args:
            section: Zu generierender Abschnitt
            outline: Vollstaendige Gliederung
            previous_sections: Inhalte vorheriger Abschnitte (fuer Kohaerenz)
            progress_callback: Fortschritts-Callback
            section_index: Abschnittsindex (fuer Protokollierung)

        Returns:
            Abschnittsinhalt (Markdown-Format)
        """
        logger.info(f"ReACT Kapitelgenerierung: {section.title}")
        
        # Protokolleintrag fuer Abschnittsstart
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Benutzer-Prompt erstellen - jeder abgeschlossene Abschnitt maximal 4000 Zeichen
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Jeder Abschnitt maximal 4000 Zeichen
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(Dies ist das erste Kapitel)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT-Schleife
        tool_calls_count = 0
        max_iterations = 5  # Maximale Iterationsrunden
        min_tool_calls = 3  # Mindestanzahl Werkzeugaufrufe
        conflict_retries = 0  # Aufeinanderfolgende Konflikte: Werkzeugaufruf und Final Answer gleichzeitig
        used_tools = set()  # Aufgerufene Werkzeugnamen protokollieren
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Berichtskontext, fuer InsightForge-Unterfragengenerierung
        report_context = f"Kapiteltitel: {section.title}\nSimulationsanforderung: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Tiefenrecherche und Verfassen ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # LLM aufrufen
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Pruefen, ob LLM-Rueckgabe None ist (API-Ausnahme oder leerer Inhalt)
            if response is None:
                logger.warning(f"Kapitel {section.title} Iteration {iteration + 1}: LLM gab None zurueck")
                # Falls noch Iterationen uebrig, Nachricht hinzufuegen und erneut versuchen
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(Antwort leer)"})
                    messages.append({"role": "user", "content": "Bitte fahren Sie mit der Inhaltserstellung fort."})
                    continue
                # Auch letzte Iteration gibt None zurueck, Schleife verlassen fuer erzwungenen Abschluss
                break

            logger.debug(f"LLM-Antwort: {response[:200]}...")

            # Einmal parsen, Ergebnis wiederverwenden
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Konfliktbehandlung: LLM hat gleichzeitig Werkzeugaufruf und Final Answer ausgegeben ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Kapitel {section.title} Runde {iteration+1}: "
                    f"LLM hat gleichzeitig Werkzeugaufruf und Final Answer ausgegeben (Konflikt Nr. {conflict_retries})"
                )

                if conflict_retries <= 2:
                    # Erste zwei Male: Diese Antwort verwerfen, LLM auffordern erneut zu antworten
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【Formatfehler】Sie haben in einer Antwort gleichzeitig einen Werkzeugaufruf und Final Answer enthalten, das ist nicht erlaubt.\n"
                            "Jede Antwort darf nur eine der folgenden zwei Aktionen enthalten:\n"
                            "- Ein Werkzeug aufrufen (einen <tool_call>-Block ausgeben, kein Final Answer schreiben)\n"
                            "- Endgueltigen Inhalt ausgeben (mit 'Final Answer:' beginnen, kein <tool_call> enthalten)\n"
                            "Bitte antworten Sie erneut und fuehren Sie nur eine der beiden Aktionen aus."
                        ),
                    })
                    continue
                else:
                    # Drittes Mal: Fallback-Behandlung, auf ersten Werkzeugaufruf abschneiden, erzwungen ausfuehren
                    logger.warning(
                        f"Kapitel {section.title}: {conflict_retries} aufeinanderfolgende Konflikte, "
                        "Fallback auf Abschneiden und Ausfuehrung des ersten Werkzeugaufrufs"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # LLM-Antwort protokollieren
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Fall 1: LLM hat Final Answer ausgegeben ──
            if has_final_answer:
                # Unzureichende Werkzeugaufrufe, ablehnen und weitere Werkzeugaufrufe anfordern
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(Diese Werkzeuge wurden noch nicht verwendet, Verwendung empfohlen: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normaler Abschluss
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Kapitel {section.title} Generierung abgeschlossen (Werkzeugaufrufe: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Fall 2: LLM versucht Werkzeug aufzurufen ──
            if has_tool_calls:
                # Werkzeugkontingent erschoepft -> Klar mitteilen, Final Answer anfordern
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Nur ersten Werkzeugaufruf ausfuehren
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM versuchte {len(tool_calls)} Werkzeuge aufzurufen, nur erstes ausgefuehrt: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Hinweis zu nicht verwendeten Werkzeugen erstellen
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Fall 3: Weder Werkzeugaufruf noch Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Unzureichende Werkzeugaufrufe, nicht verwendete Werkzeuge empfehlen
                unused_tools = all_tools - used_tools
                unused_hint = f"(Diese Werkzeuge wurden noch nicht verwendet, Verwendung empfohlen: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Werkzeugaufrufe ausreichend, LLM hat Inhalt ohne "Final Answer:"-Praefix ausgegeben
            # Diesen Inhalt direkt als endgueltige Antwort verwenden, kein Leerlauf mehr
            logger.info(f"Kapitel {section.title}: Kein 'Final Answer:'-Praefix erkannt, LLM-Ausgabe direkt als Endinhalt uebernommen (Werkzeugaufrufe: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Maximale Iterationsanzahl erreicht, Inhaltsgenerierung erzwingen
        logger.warning(f"Kapitel {section.title}: Maximale Iterationsanzahl erreicht, erzwungene Generierung")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Pruefen, ob LLM beim erzwungenen Abschluss None zurueckgibt
        if response is None:
            logger.error(f"Kapitel {section.title}: LLM gab bei erzwungenem Abschluss None zurueck, verwende Standard-Fehlermeldung")
            final_answer = f"(Dieser Abschnitt konnte nicht generiert werden: LLM hat leere Antwort zurueckgegeben, bitte spaeter erneut versuchen)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Protokolleintrag fuer Abschnittsinhalts-Generierungsabschluss
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Vollstaendigen Bericht generieren (abschnittsweise Echtzeitausgabe)

        Jeder Abschnitt wird sofort nach Fertigstellung im Ordner gespeichert, ohne auf den gesamten Bericht warten zu muessen.
        Dateistruktur:
        reports/{report_id}/
            meta.json       - Bericht-Metainformationen
            outline.json    - Berichtsgliederung
            progress.json   - Generierungsfortschritt
            section_01.md   - Kapitel 1
            section_02.md   - Kapitel 2
            ...
            full_report.md  - Vollstaendiger Bericht
        
        Args:
            progress_callback: Fortschritts-Callback-Funktion (stage, progress, message)
            report_id: Bericht-ID (optional, wird automatisch generiert falls nicht angegeben)

        Returns:
            Report: Vollstaendiger Bericht
        """
        import uuid
        
        # Falls keine report_id uebergeben, automatisch generieren
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Liste abgeschlossener Abschnittstitel (fuer Fortschrittsverfolgung)
        completed_section_titles = []
        
        try:
            # Initialisierung: Berichtsordner erstellen und Anfangsstatus speichern
            ReportManager._ensure_report_folder(report_id)
            
            # Protokoll-Recorder initialisieren (strukturiertes Protokoll agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Konsolenprotokoll-Recorder initialisieren (console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Bericht wird initialisiert...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Phase 1: Gliederung planen
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Planung der Berichtsgliederung beginnt...",
                completed_sections=[]
            )
            
            # Protokolleintrag fuer Planungsstart
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Planung der Berichtsgliederung beginnt...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Protokolleintrag fuer Planungsabschluss
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Gliederung in Datei speichern
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Gliederungsplanung abgeschlossen, {len(outline.sections)} Kapitel",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Gliederung in Datei gespeichert: {report_id}/outline.json")
            
            # Phase 2: Abschnittsweise Generierung (abschnittsweise speichern)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Inhalt fuer Kontext speichern
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Fortschritt aktualisieren
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Kapitel wird erstellt: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating",
                        base_progress,
                        f"Kapitel wird erstellt: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Hauptabschnittsinhalt generieren
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Abschnitt speichern
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Protokolleintrag fuer Abschnittsabschluss
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Kapitel gespeichert: {report_id}/section_{section_num:02d}.md")
                
                # Fortschritt aktualisieren
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Kapitel {section.title} abgeschlossen",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Phase 3: Vollstaendigen Bericht zusammensetzen
            if progress_callback:
                progress_callback("generating", 95, "Vollstaendiger Bericht wird zusammengestellt...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Vollstaendiger Bericht wird zusammengestellt...",
                completed_sections=completed_section_titles
            )
            
            # Vollstaendigen Bericht mit ReportManager zusammensetzen
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Gesamtdauer berechnen
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Protokolleintrag fuer Berichtsabschluss
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Endgueltigen Bericht speichern
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Berichterstellung abgeschlossen",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Berichterstellung abgeschlossen")
            
            logger.info(f"Berichterstellung abgeschlossen: {report_id}")
            
            # Konsolenprotokoll-Recorder schliessen
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Berichterstellung fehlgeschlagen: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Fehlerprotokoll aufzeichnen
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Fehlgeschlagenen Status speichern
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Berichterstellung fehlgeschlagen: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Fehler beim Speichern des Fehlerstatus ignorieren
            
            # Konsolenprotokoll-Recorder schliessen
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Mit Report Agent chatten

        Im Dialog kann der Agent autonom Abrufwerkzeuge aufrufen, um Fragen zu beantworten

        Args:
            message: Benutzernachricht
            chat_history: Chat-Verlauf

        Returns:
            {
                "response": "Agent-Antwort",
                "tool_calls": [Liste der aufgerufenen Werkzeuge],
                "sources": [Informationsquellen]
            }
        """
        logger.info(f"Report Agent Dialog: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Bereits generierten Berichtsinhalt abrufen
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Berichtslaenge begrenzen, um zu langen Kontext zu vermeiden
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Berichtsinhalt gekuerzt] ..."
        except Exception as e:
            logger.warning(f"Berichtsinhalt konnte nicht abgerufen werden: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(Noch kein Bericht vorhanden)",
            tools_description=self._get_tools_description(),
        )

        # Nachrichten aufbauen
        messages = [{"role": "system", "content": system_prompt}]

        # Chatverlauf hinzufuegen
        for h in chat_history[-10:]:  # Verlaufslaenge begrenzen
            messages.append(h)
        
        # Benutzernachricht hinzufuegen
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT-Schleife (vereinfachte Version)
        tool_calls_made = []
        max_iterations = 2  # Reduzierte Iterationsrunden
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Werkzeugaufrufe parsen
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # Keine Werkzeugaufrufe, Antwort direkt zurueckgeben
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Werkzeugaufrufe ausfuehren (Anzahl begrenzt)
            tool_results = []
            for call in tool_calls[:1]:  # Pro Runde maximal 1 Werkzeugaufruf
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Ergebnislaenge begrenzen
                })
                tool_calls_made.append(call)
            
            # Ergebnisse zu Nachrichten hinzufuegen
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} Ergebnis]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Maximale Iteration erreicht, endgueltige Antwort abrufen
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Antwort bereinigen
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Berichtsmanager

    Verantwortlich fuer die persistente Speicherung und den Abruf von Berichten

    Dateistruktur (kapitelweise Ausgabe):
    reports/
      {report_id}/
        meta.json          - Bericht-Metainformationen und Status
        outline.json       - Berichtsgliederung
        progress.json      - Generierungsfortschritt
        section_01.md      - Kapitel 1
        section_02.md      - Kapitel 2
        ...
        full_report.md     - Vollstaendiger Bericht
    """

    # Berichtsspeicherverzeichnis
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Sicherstellen, dass das Berichts-Stammverzeichnis existiert"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Berichtsordner-Pfad abrufen"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Sicherstellen, dass der Berichtsordner existiert und Pfad zurueckgeben"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Bericht-Metainformations-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Vollstaendigen Bericht-Markdown-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Gliederungs-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Fortschritts-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Kapitel-Markdown-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Agent-Protokoll-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Konsolenprotokoll-Dateipfad abrufen"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Konsolenprotokoll-Inhalt abrufen

        Dies sind die Konsolenausgabe-Protokolle waehrend der Berichtsgenerierung (INFO, WARNING usw.),
        unterschiedlich zu den strukturierten Protokollen in agent_log.jsonl.

        Args:
            report_id: Bericht-ID
            from_line: Ab welcher Zeile gelesen werden soll (fuer inkrementelles Abrufen, 0 fuer Anfang)

        Returns:
            {
                "logs": [Liste der Protokollzeilen],
                "total_lines": Gesamtzeilenzahl,
                "from_line": Startzeilennummer,
                "has_more": Ob weitere Protokolle vorhanden sind
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Originale Protokollzeile beibehalten, Zeilenumbruch am Ende entfernen
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Bis zum Ende gelesen
        }

    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Vollstaendiges Konsolenprotokoll abrufen (einmalig alles abrufen)

        Args:
            report_id: Bericht-ID

        Returns:
            Liste der Protokollzeilen
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Agent-Protokoll-Inhalt abrufen

        Args:
            report_id: Bericht-ID
            from_line: Ab welcher Zeile gelesen werden soll (fuer inkrementelles Abrufen, 0 fuer Anfang)

        Returns:
            {
                "logs": [Liste der Protokolleintraege],
                "total_lines": Gesamtzeilenzahl,
                "from_line": Startzeilennummer,
                "has_more": Ob weitere Protokolle vorhanden sind
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Zeilen mit fehlgeschlagenem Parsing ueberspringen
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Bis zum Ende gelesen
        }

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Vollstaendiges Agent-Protokoll abrufen (einmalig alles abrufen)

        Args:
            report_id: Bericht-ID

        Returns:
            Liste der Protokolleintraege
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Berichtsgliederung speichern

        Wird sofort nach Abschluss der Planungsphase aufgerufen
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Gliederung gespeichert: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Einzelnes Kapitel speichern

        Wird sofort nach Abschluss der Generierung jedes Kapitels aufgerufen, fuer kapitelweise Ausgabe

        Args:
            report_id: Bericht-ID
            section_index: Kapitelindex (ab 1)
            section: Kapitelobjekt

        Returns:
            Gespeicherter Dateipfad
        """
        cls._ensure_report_folder(report_id)

        # Kapitel-Markdown-Inhalt erstellen - moeglicherweise vorhandene doppelte Ueberschriften bereinigen
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Datei speichern
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Kapitel gespeichert: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Kapitelinhalt bereinigen

        1. Markdown-Ueberschriftenzeilen am Inhaltsanfang entfernen, die den Kapiteltitel duplizieren
        2. Alle ### und niedrigere Ueberschriftenebenen in Fetttext umwandeln

        Args:
            content: Originalinhalt
            section_title: Kapiteltitel

        Returns:
            Bereinigter Inhalt
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Pruefen, ob es eine Markdown-Ueberschriftenzeile ist
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Pruefen, ob es eine mit dem Kapiteltitel doppelte Ueberschrift ist (Duplikate in den ersten 5 Zeilen ueberspringen)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Alle Ueberschriftenebenen (#, ##, ###, #### usw.) in Fetttext umwandeln
                # Da Kapitelueberschriften vom System hinzugefuegt werden, sollte der Inhalt keine Ueberschriften enthalten
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Leerzeile hinzufuegen
                continue
            
            # Wenn die vorherige Zeile eine uebersprungene Ueberschrift war und die aktuelle Zeile leer ist, ebenfalls ueberspringen
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Leerzeilen am Anfang entfernen
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Trennlinien am Anfang entfernen
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Gleichzeitig Leerzeilen nach der Trennlinie entfernen
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Berichtsgenerierungs-Fortschritt aktualisieren

        Das Frontend kann durch Lesen von progress.json den Echtzeitfortschritt abrufen
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Berichtsgenerierungs-Fortschritt abrufen"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Liste der generierten Kapitel abrufen

        Gibt Informationen aller gespeicherten Kapiteldateien zurueck
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Kapitelindex aus Dateinamen parsen
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Vollstaendigen Bericht zusammensetzen

        Aus gespeicherten Kapiteldateien den vollstaendigen Bericht zusammensetzen und Ueberschriften bereinigen
        """
        folder = cls._get_report_folder(report_id)
        
        # Berichtskopf erstellen
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Alle Kapiteldateien der Reihe nach lesen
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Nachbearbeitung: Ueberschriftenprobleme im gesamten Bericht bereinigen
        md_content = cls._post_process_report(md_content, outline)
        
        # Vollstaendigen Bericht speichern
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Vollstaendiger Bericht zusammengesetzt: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Berichtsinhalt nachbearbeiten

        1. Doppelte Ueberschriften entfernen
        2. Berichtshaupttitel (#) und Kapitelueberschriften (##) beibehalten, andere Ebenen (###, #### usw.) entfernen
        3. Ueberfluessige Leerzeilen und Trennlinien bereinigen

        Args:
            content: Originaler Berichtsinhalt
            outline: Berichtsgliederung

        Returns:
            Nachbearbeiteter Inhalt
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Alle Kapitelueberschriften aus der Gliederung sammeln
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Pruefen, ob es eine Ueberschriftenzeile ist
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Pruefen, ob es eine doppelte Ueberschrift ist (gleicher Inhalt innerhalb von 5 aufeinanderfolgenden Zeilen)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Doppelte Ueberschrift und nachfolgende Leerzeilen ueberspringen
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Ueberschriften-Ebenen-Behandlung:
                # - # (level=1) Nur Berichtshaupttitel beibehalten
                # - ## (level=2) Kapitelueberschriften beibehalten
                # - ### und darunter (level>=3) In Fetttext umwandeln
                
                if level == 1:
                    if title == outline.title:
                        # Berichtshaupttitel beibehalten
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Kapitelueberschrift hat faelschlicherweise # verwendet, auf ## korrigieren
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Andere Ebene-1-Ueberschriften in Fetttext umwandeln
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Kapitelueberschrift beibehalten
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Nicht-Kapitel-Ebene-2-Ueberschriften in Fetttext umwandeln
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### und niedrigere Ebenen in Fetttext umwandeln
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Trennlinie direkt nach Ueberschrift ueberspringen
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Nach Ueberschrift nur eine Leerzeile beibehalten
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Aufeinanderfolgende Leerzeilen bereinigen (maximal 2 beibehalten)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Bericht-Metainformationen und vollstaendigen Bericht speichern"""
        cls._ensure_report_folder(report.report_id)
        
        # Metainformationen-JSON speichern
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Gliederung speichern
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Vollstaendigen Markdown-Bericht speichern
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Bericht gespeichert: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Bericht abrufen"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Kompatibilitaet mit altem Format: Dateien pruefen, die direkt im reports-Verzeichnis gespeichert sind
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Report-Objekt rekonstruieren
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # Wenn markdown_content leer ist, versuchen aus full_report.md zu lesen
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Bericht anhand der Simulations-ID abrufen"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Neues Format: Ordner
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Kompatibilitaet mit altem Format: JSON-Datei
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """Berichte auflisten"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Neues Format: Ordner
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Kompatibilitaet mit altem Format: JSON-Datei
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)

        # Nach Erstellungszeit absteigend sortieren
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Bericht loeschen (gesamter Ordner)"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # Neues Format: Gesamten Ordner loeschen
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Berichtsordner geloescht: {report_id}")
            return True

        # Kompatibilitaet mit altem Format: Einzelne Dateien loeschen
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
