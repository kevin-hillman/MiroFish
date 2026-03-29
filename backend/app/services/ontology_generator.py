"""
Ontologie-Generierungsdienst
Schnittstelle 1: Textinhalt analysieren und Entitaets- und Beziehungstyp-Definitionen fuer Sozialsimulationen generieren
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# System-Prompt fuer Ontologie-Generierung
ONTOLOGY_SYSTEM_PROMPT = """Sie sind ein professioneller Experte fuer Wissensgraph-Ontologie-Design. Ihre Aufgabe ist es, den gegebenen Textinhalt und die Simulationsanforderungen zu analysieren und geeignete Entitaets- und Beziehungstypen fuer eine **Social-Media-Meinungssimulation** zu entwerfen.

**Wichtig: Sie muessen gueltige JSON-Daten ausgeben und keinen anderen Inhalt.**

## Kernaufgabe - Hintergrund

Wir bauen ein **Social-Media-Meinungssimulationssystem** auf. In diesem System:
- Jede Entitaet ist ein "Konto" oder "Akteur", der in sozialen Medien posten, interagieren und Informationen verbreiten kann
- Entitaeten beeinflussen sich gegenseitig, teilen, kommentieren und reagieren aufeinander
- Wir muessen die Reaktionen verschiedener Parteien bei Meinungsereignissen und die Wege der Informationsverbreitung simulieren

Daher **muessen Entitaeten real existierende Akteure sein, die in sozialen Medien posten und interagieren koennen**:

**Erlaubt**:
- Konkrete Einzelpersonen (oeffentliche Persoenlichkeiten, Beteiligte, Meinungsfuehrer, Experten, normale Buerger)
- Unternehmen und Firmen (einschliesslich ihrer offiziellen Konten)
- Organisationen (Universitaeten, Verbaende, NGOs, Gewerkschaften usw.)
- Regierungsbehoerden, Aufsichtsbehoerden
- Medienorganisationen (Zeitungen, Fernsehsender, unabhaengige Medien, Webseiten)
- Social-Media-Plattformen selbst
- Vertreter bestimmter Gruppen (z.B. Alumni-Vereine, Fangruppen, Interessengruppen usw.)

**Nicht erlaubt**:
- Abstrakte Konzepte (z.B. "oeffentliche Meinung", "Stimmung", "Trend")
- Themen/Diskussionsgegenstaende (z.B. "akademische Integritaet", "Bildungsreform")
- Standpunkte/Haltungen (z.B. "Befuerworter", "Gegner")

## Ausgabeformat

Bitte geben Sie JSON im folgenden Format aus:

```json
{
    "entity_types": [
        {
            "name": "Entitaetstypname (Englisch, PascalCase)",
            "description": "Kurzbeschreibung (Englisch, max. 100 Zeichen)",
            "attributes": [
                {
                    "name": "Attributname (Englisch, snake_case)",
                    "type": "text",
                    "description": "Attributbeschreibung"
                }
            ],
            "examples": ["Beispielentitaet1", "Beispielentitaet2"]
        }
    ],
    "edge_types": [
        {
            "name": "Beziehungstypname (Englisch, UPPER_SNAKE_CASE)",
            "description": "Kurzbeschreibung (Englisch, max. 100 Zeichen)",
            "source_targets": [
                {"source": "Quellentitaetstyp", "target": "Zielentitaetstyp"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Kurze Analysebeschreibung des Textinhalts (auf Deutsch)"
}
```

## Designrichtlinien (aeusserst wichtig!)

### 1. Entitaetstyp-Design - Muss strikt eingehalten werden

**Mengenanforderung: Es muessen genau 10 Entitaetstypen sein**

**Hierarchieanforderung (muss sowohl spezifische als auch Auffangtypen enthalten)**:

Ihre 10 Entitaetstypen muessen folgende Hierarchie aufweisen:

A. **Auffangtypen (muessen enthalten sein, als letzte 2 in der Liste)**:
   - `Person`: Auffangtyp fuer jede natuerliche Person. Wenn eine Person keinem spezifischeren Personentyp zugeordnet werden kann, wird sie hier eingeordnet.
   - `Organization`: Auffangtyp fuer jede Organisation. Wenn eine Organisation keinem spezifischeren Organisationstyp zugeordnet werden kann, wird sie hier eingeordnet.

B. **Spezifische Typen (8, basierend auf dem Textinhalt entworfen)**:
   - Entwerfen Sie spezifischere Typen fuer die Hauptakteure im Text
   - Beispiel: Bei akademischen Ereignissen koennen `Student`, `Professor`, `University` verwendet werden
   - Beispiel: Bei wirtschaftlichen Ereignissen koennen `Company`, `CEO`, `Employee` verwendet werden

**Warum Auffangtypen benoetigt werden**:
- Im Text tauchen verschiedene Personen auf, wie "Grundschullehrer", "Passanten", "anonyme Internetnutzer"
- Wenn kein spezifischer Typ passt, sollten sie unter `Person` eingeordnet werden
- Ebenso sollten kleine Organisationen, temporaere Gruppen usw. unter `Organization` eingeordnet werden

**Designprinzipien fuer spezifische Typen**:
- Identifizieren Sie haeufig auftretende oder wichtige Akteurtypen im Text
- Jeder spezifische Typ sollte klare Grenzen haben, Ueberschneidungen vermeiden
- Die description muss den Unterschied zwischen diesem Typ und dem Auffangtyp klar beschreiben

### 2. Beziehungstyp-Design

- Anzahl: 6-10
- Beziehungen sollten reale Verbindungen in Social-Media-Interaktionen widerspiegeln
- Stellen Sie sicher, dass die source_targets der Beziehungen Ihre definierten Entitaetstypen abdecken

### 3. Attribut-Design

- 1-3 Schluesselattribute pro Entitaetstyp
- **Achtung**: Attributnamen duerfen nicht `name`, `uuid`, `group_id`, `created_at`, `summary` verwenden (diese sind Systemreservierungen)
- Empfohlen: `full_name`, `title`, `role`, `position`, `location`, `description` usw.

## Entitaetstyp-Referenz

**Personentypen (spezifisch)**:
- Student: Student
- Professor: Professor/Wissenschaftler
- Journalist: Journalist
- Celebrity: Prominenter/Influencer
- Executive: Fuehrungskraft
- Official: Regierungsbeamter
- Lawyer: Rechtsanwalt
- Doctor: Arzt

**Personentypen (Auffang)**:
- Person: Jede natuerliche Person (wird verwendet, wenn kein spezifischerer Typ passt)

**Organisationstypen (spezifisch)**:
- University: Hochschule
- Company: Unternehmen
- GovernmentAgency: Regierungsbehoerde
- MediaOutlet: Medienorganisation
- Hospital: Krankenhaus
- School: Schule
- NGO: Nichtregierungsorganisation

**Organisationstypen (Auffang)**:
- Organization: Jede Organisation (wird verwendet, wenn kein spezifischerer Typ passt)

## Beziehungstyp-Referenz

- WORKS_FOR: Arbeitet bei
- STUDIES_AT: Studiert an
- AFFILIATED_WITH: Gehoert zu
- REPRESENTS: Vertritt
- REGULATES: Beaufsichtigt
- REPORTS_ON: Berichtet ueber
- COMMENTS_ON: Kommentiert
- RESPONDS_TO: Reagiert auf
- SUPPORTS: Unterstuetzt
- OPPOSES: Widerspricht
- COLLABORATES_WITH: Kooperiert mit
- COMPETES_WITH: Konkurriert mit
"""


class OntologyGenerator:
    """
    Ontologie-Generator
    Textinhalt analysieren und Entitaets- und Beziehungstyp-Definitionen generieren
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ontologie-Definition generieren

        Args:
            document_texts: Liste der Dokumenttexte
            simulation_requirement: Beschreibung der Simulationsanforderung
            additional_context: Zusaetzlicher Kontext

        Returns:
            Ontologie-Definition (entity_types, edge_types usw.)
        """
        # Benutzernachricht erstellen
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # LLM aufrufen
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # Validieren und nachbearbeiten
        result = self._validate_and_process(result)
        
        return result
    
    # Maximale Textlaenge fuer LLM (50.000 Zeichen)
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Benutzernachricht erstellen"""
        
        # Texte zusammenfuehren
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # Falls Text 50.000 Zeichen ueberschreitet, abschneiden (betrifft nur LLM-Eingabe, nicht den Graph-Aufbau)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Originaltext umfasst {original_length} Zeichen, die ersten {self.MAX_TEXT_LENGTH_FOR_LLM} Zeichen wurden fuer die Ontologie-Analyse verwendet)..."
        
        message = f"""## Simulationsanforderungen

{simulation_requirement}

## Dokumentinhalt

{combined_text}
"""

        if additional_context:
            message += f"""
## Zusaetzliche Hinweise

{additional_context}
"""

        message += """
Bitte entwerfen Sie auf Basis des obigen Inhalts geeignete Entitaets- und Beziehungstypen fuer eine Meinungssimulation.

**Verbindliche Regeln**:
1. Es muessen genau 10 Entitaetstypen ausgegeben werden
2. Die letzten 2 muessen Auffangtypen sein: Person (Personen-Auffang) und Organization (Organisations-Auffang)
3. Die ersten 8 sind spezifische Typen, die auf dem Textinhalt basieren
4. Alle Entitaetstypen muessen real existierende Akteure sein, keine abstrakten Konzepte
5. Attributnamen duerfen keine Reservierungen wie name, uuid, group_id verwenden, stattdessen full_name, org_name usw.
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Ergebnis validieren und nachbearbeiten"""
        
        # Sicherstellen, dass erforderliche Felder vorhanden sind
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # Entitaetstypen validieren
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Sicherstellen, dass description nicht mehr als 100 Zeichen hat
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # Beziehungstypen validieren
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API Einschraenkung: maximal 10 benutzerdefinierte Entitaetstypen, maximal 10 benutzerdefinierte Kantentypen
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        
        # Fallback-Typ-Definitionen
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # Pruefen, ob Fallback-Typen bereits vorhanden sind
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # Hinzuzufuegende Fallback-Typen
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # Falls nach dem Hinzufuegen mehr als 10, einige vorhandene Typen entfernen
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Berechnen, wie viele entfernt werden muessen
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Vom Ende entfernen (wichtigere spezifische Typen am Anfang beibehalten)
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # Fallback-Typen hinzufuegen
            result["entity_types"].extend(fallbacks_to_add)
        
        # Abschliessend sicherstellen, dass Limits nicht ueberschritten werden (defensive Programmierung)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Ontologie-Definition in Python-Code umwandeln (aehnlich wie ontology.py)

        Args:
            ontology: Ontologie-Definition

        Returns:
            Python-Code-String
        """
        code_lines = [
            '"""',
            'Benutzerdefinierte Entitaetstyp-Definitionen',
            'Automatisch von MiroFish generiert, fuer Sozialsimulationen',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Entitaetstyp-Definitionen ==============',
            '',
        ]
        
        # Entitaetstypen generieren
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== Beziehungstyp-Definitionen ==============')
        code_lines.append('')
        
        # Beziehungstypen generieren
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # In PascalCase-Klassennamen umwandeln
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # Typ-Woerterbuch generieren
        code_lines.append('# ============== Typkonfiguration ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # source_targets-Zuordnung fuer Kanten generieren
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

