# YouTuber Fan-Plattform — Konzept & Bauplan

> Gehört zusammen mit `offene-fragen-youtuber-plattform.md` — dort stehen die noch offenen Fragen zu diesem Konzept, aufgeteilt nach Rechtlich/Datenschutz, Technisch/Kosten, Plattform/UX und Business.

## 1. Vision

Ein Service für große YouTuber (z.B. aus dem Bereich Politik, Gesellschaft, komplexere Themen), der ihre Abonnenten enger an den Kanal bindet, ohne dass der YouTuber selbst zusätzlichen Aufwand hat.

Fans tragen sich mit ihrer E-Mail-Adresse in eine Liste ein. Nach jedem neuen Video bekommen sie automatisch Mehrwert-Content dazu (Start: eine Zusammenfassung). **Bezahlt wird von den YouTubern selbst**, nicht von den Fans — gestaffelt nach Anzahl der Abonnenten in der Liste. Der Gedanke: Für einen großen Kanal ist Marketing/Fan-Bindung schwierig, ein solcher Service ist ein leicht buchbarer Zusatz-Mehrwert für die eigene Community.

Langfristig: eine **zentrale, weiße Plattform**, die für mehrere YouTuber gleichzeitig funktioniert, personalisierbar (Branding) pro Kanal, mit einem gemeinsamen Login für Fans, die mehrere Kanäle abonniert haben.

Marktlage (Stand unserer Recherche): Es gibt einzelne Bausteine am Markt (z.B. Self-Service-Tools, die einzelne Video-Zusammenfassungen erzeugen), aber **kein fertiges Managed-Service-Produkt** in dieser Kombination, das ein Creator einfach bucht und laufen lässt. Das ist die Nische.

---

## 2. MVP — Umfang für den ersten Wurf

Bewusst klein gehalten. Ziel: schnell etwas Vorzeigbares haben, mit dem man auf echte YouTuber zugehen kann.

### Feature 1: Automatische Video-Zusammenfassung per E-Mail
- Ablauf: neues Video wird erkannt → Transkript wird geholt → LLM erstellt Zusammenfassung → E-Mail geht an alle Abonnenten der Liste raus.
- Trigger: YouTube Data API unterstützt Push-Benachrichtigungen über **PubSubHubbub** — man abonniert den Kanal-Feed einmalig, und bekommt dann bei jedem neuen Upload automatisch eine Benachrichtigung an eine eigene Callback-URL, ganz ohne Polling.

### Feature 2: Kommentar-Sentiment-Zusammenfassung pro Video
- Ähnlich wie die Rezensions-Zusammenfassungen bei Amazon: ein kurzer, automatisch generierter Überblick über die Grundstimmung in den Kommentaren eines Videos.
- Technisch: `commentThreads.list` aus der YouTube Data API liefert öffentliche Kommentare zu jedem öffentlichen Video — **hierfür reicht ein simpler API-Key, es ist keine Zustimmung/OAuth des Kanalinhabers nötig.** Das heißt, dieses Feature lässt sich sogar für Demo-Zwecke auf beliebigen fremden Kanälen zeigen.
- Muss mitgebaut werden: Filterung von Spam/Bot-Kommentaren vor der Sentiment-Auswertung, sowie eine Sampling-Strategie bei Videos mit sehr vielen Kommentaren (nicht alles lesen/verarbeiten).

### MVP-Zugang für Fans
- **Magic-Link-Login per E-Mail** (kein Passwort) — passt zum Modell, dass wir ohnehin nur die E-Mail-Adresse haben, und ist einfach + sicher genug für den Start.
- Eine zentrale, einfache Übersicht: welche Kanäle habe ich abonniert, welche Zusammenfassungen gibt es.

### Bewusst NICHT im MVP
- Kein Chat-Assistent (siehe Zukunftsliste unten — deutlich komplexer).
- Kein Diskussionsbereich (siehe unten).
- Keine mehreren YouTuber gleichzeitig / kein Mandanten-System — erstmal ein Kanal, ein Test-Setup.
- Keine ausgefeilte Bezahl-Logik — für den MVP reicht ein manueller/vertraglicher Deal mit dem ersten Partner, keine automatisierte Abrechnung.

---

## 3. Zukunftsliste (nach dem MVP)

### Persönlicher Chat-Assistent über den Backkatalog
**Explizit auf die Zukunftsliste verschoben — nicht Teil des MVP.** Grund: das ist kein einfaches Zusatzfeature, sondern eine eigene technische Baustelle:
- Braucht einen durchsuchbaren Index (Embeddings/Vektordatenbank) über den gesamten Backkatalog eines Kanals, nicht nur das letzte Video.
- Kosten skalieren nicht linear wie bei der E-Mail-Zusammenfassung: Ein Video wird einmal zusammengefasst, aber ein Chat-Assistent kann theoretisch von tausenden Fans mit individuellen Fragen angefragt werden → braucht Caching / Wiederverwendung häufiger Antworten, sonst explodieren die LLM-Kosten.
- Grobes späteres Konzept: RAG-Pipeline (Retrieval-Augmented Generation) über die gesammelten Transkripte, Antworten idealerweise mit Zeitstempel-Verweis ins Originalvideo.

### Diskussionsbereich (kuratiert, ruhiger als YouTube-Kommentare)
- Bleibt vorerst optional / im Hinterkopf. Beim Datenmodell aber schon mitdenken (z.B. nicht nur E-Mail, sondern später ggf. echte User-Accounts), damit es sich nachrüsten lässt, ohne alles umzubauen.

### Weitere Ideen für spätere Ausbaustufen
- Analytics-Dashboard für den YouTuber (Öffnungsraten, Klickraten, meistgestellte Fragen) — wichtig für die eigene Kundenbindung/Preis-Rechtfertigung.
- Mehrsprachige Zusammenfassungen.
- Personalisierte Lernpfade über mehrere Videos hinweg (bei Bildungscontent).

---

## 4. Website & Zugang — wie hängt das mit einer Webseite zusammen?

Zwei ganz unterschiedliche Bedürfnisse stecken hinter "wir brauchen eine Webseite":

1. **Verkaufsseite (B2B):** Eine Seite, die den Service den YouTubern erklärt — Feature-Übersicht, Preismodell, evtl. eine Demo. Zielgruppe: der YouTuber bzw. sein Team, nicht die Fans.
2. **Konsum-Oberfläche (B2C):** Ein Ort, an dem Fans ihre Zusammenfassungen einsehen können. Zielgruppe: die Abonnenten.

Diese zwei sollten inhaltlich getrennt gedacht werden, auch wenn sie am Ende auf derselben Domain liegen können.

### Vorschlag fürs MVP: so schlank wie möglich

**Marketing/Verkaufsseite:** Eine einzelne, klassische Landingpage (z.B. `unserservice.de`) reicht für den Start völlig aus — beschreibt den Service, zeigt die Demo aus Phase 0, hat ein Kontaktformular für interessierte YouTuber. Kein Login, keine Personalisierung nötig.

**Fan-Ansicht — Idee, um eine komplette Dashboard-App am Anfang zu vermeiden:** Statt direkt ein voll authentifiziertes Multi-Kanal-Dashboard zu bauen, könnte man im MVP komplett auf die E-Mail als Haupt-Interface setzen (die Zusammenfassung kommt ja ohnehin per Mail) und nur einen "Online ansehen"-Link pro Zusammenfassung anbieten — eine öffentlich erreichbare, aber nicht erratbare URL pro Zusammenfassung (z.B. mit langem zufälligem Token), ganz ohne Login. Das deckt den Hauptbedarf ("ich will die Zusammenfassung nochmal nachlesen") schon ab, ohne dass wir Auth, Sessions oder ein Dashboard bauen müssen.

Der zentrale Login mit Übersicht über alle abonnierten Kanäle — das, was ursprünglich als "eine Plattform" gedacht war — würde dann erst in Phase 2 kommen, sobald es überhaupt mehrere Kanäle gleichzeitig gibt und dadurch ein echter Bedarf für eine Übersichtsseite entsteht. Bei nur einem Partner-Kanal gibt es ja noch nichts "zu übersehen", der Aufwand lohnt sich vorher kaum.

### Ausbaustufen für die Fan-Seite

| Phase | Was gibt es |
|---|---|
| MVP | Landingpage (B2B) + einzelne "Online ansehen"-Seiten pro Zusammenfassung, kein Login |
| Phase 2 | Magic-Link-Login + zentrales Dashboard, sobald mehrere Kanäle live sind |
| Später | Personalisierung pro Kanal, z.B. eigene Unterseite (`unserservice.de/kanalname`) oder Subdomain (`kanalname.unserservice.de`) als Einstiegspunkt fürs Fan-Onboarding, die dann ins gemeinsame Dashboard führt |

Das beantwortet auch die Frage "eigene Landingpage pro YouTuber oder nicht": Für die reine Konsum-Oberfläche reicht eine gemeinsame technische Basis; branded/personalisierte Einstiegspunkte pro Kanal (z.B. für den Sign-up-Flow, den der YouTuber in seiner Videobeschreibung verlinkt) lassen sich später als schlanke, austauschbare Fassade vor demselben Backend ergänzen, ohne die Kernarchitektur anzufassen.

---

## 5. Technische Architektur (MVP — bewusst schlank)

```
Neues Video (YouTube)
   │  PubSubHubbub Push-Notification
   ▼
Ingestion-Service (empfängt Webhook)
   │
   ▼
Transkript-Layer  ──►  LLM (Zusammenfassung)  ──►  E-Mail-Versand
   │
Kommentar-Layer  ──►  LLM (Sentiment)  ──►  Anzeige im Fan-Dashboard
```

**Transkript-Layer — bewusst hinter einem Interface abstrahiert, zwei Implementierungen:**
- *Demo/Anfangsphase (kein Vertrag mit Kanal nötig):* die inoffizielle Python-Bibliothek `youtube-transcript-api` — kostenlos, kein API-Key nötig, funktioniert für Videos mit vorhandenen (auch automatisch generierten) Untertiteln. Wichtiger Vorbehalt: inoffiziell, kann ohne Vorwarnung brechen, daher nur als Fallback/Demo-Lösung gedacht, nicht als Produktionsfundament.
- *Produktion, sobald ein Partner-Vertrag steht:* der offizielle `captions.download`-Endpunkt der YouTube Data API. Der funktioniert **nur mit einer OAuth-2.0-Freigabe durch den Kanalinhaber** — für fremde Videos ohne diese Freigabe gibt der offizielle Weg einen Fehler zurück. Das passt aber gut zum Geschäftsmodell: Der YouTuber ist ohnehin unser Vertragspartner und muss uns diese Freigabe im Onboarding erteilen.

**Kommentar-Layer:** `commentThreads.list`, YouTube Data API, reiner API-Key reicht (siehe oben) — kein OAuth-Blocker, kann auch vor Vertragsabschluss für Demos genutzt werden.

**Kosten/Kontingent im Blick behalten:** Die YouTube Data API selbst ist kostenlos, hat aber ein Tageskontingent von standardmäßig 10.000 Einheiten pro Google-Cloud-Projekt; die meisten Lese-Operationen (Videoliste, Kommentare) kosten nur 1 Einheit, sollte für den MVP-Maßstab also unkritisch sein.

**E-Mail-Versand:** Über einen Transaktions-E-Mail-Dienst (z.B. Postmark, Resend o.ä.) — noch zu entscheiden, aber nicht selbst bauen.

**Speicherung:** Zusammenfassungen + Metadaten in einer Datenbank; Rohvideos/-audios nicht dauerhaft speichern (unnötige Kosten und Datenschutz-Risiko).

**Auth:** Magic-Link.

---

## 6. KI/Agent-SDK — welches Fundament?

- **Start: Anthropic SDK / Claude als Modell.** Einfachster Einstieg, gute Doku, passt zum Team-Know-how.
- **Aber: bewusst kein Lock-in.** Mittelfristig soll es leicht möglich sein, auch andere — insbesondere Open-Source — Modelle einzusetzen, sei es aus Kosten-, Datenschutz- oder Qualitätsgründen für einzelne Aufgaben. Die Architektur soll daher von Anfang an so gebaut sein, dass der LLM-Anbieter **austauschbar (Plug-and-Play)** bleibt, ohne den Anwendungscode anzufassen. Dafür eine Gateway-/Abstraktionsschicht dazwischenschalten statt direkt gegen den Anthropic-Client zu programmieren.
- Vorschlag dafür: **Bifrost** (Open-Source-Alternative zu LiteLLM) als LLM-Gateway einsetzen. Im MVP wird dort trotzdem nur ein einziger Provider (Anthropic/Claude) konfiguriert — der Zusatzaufwand ist gering, der Nutzen (späterer Wechsel oder Ergänzung um Open-Source-Modelle, z.B. günstigeres/lokales Modell für einfache Zusammenfassungen, potenteres für komplexere Aufgaben) ist dann nur eine Konfigurationsänderung statt Code-Umbau.
- Wichtig für die Kollegen: **nicht am Anfang schon Multi-Provider-Logik selbst bauen.** Bifrost übernimmt das Routing, die Anwendung spricht nur mit Bifrost.
- **Package Manager:** Sofern in Python umgesetzt (naheliegend, u.a. wegen `youtube-transcript-api` und dem generell guten Ökosystem für LLM-/Datenverarbeitung) soll **uv** als Package Manager verwendet werden.

### Leitprinzipien für die Umsetzung
Über das KI-Modell hinaus gilt für den gesamten Tech-Stack: **wartbar, minimalistisch, gut bedienbar und verständlich.** Also keine Architektur-Entscheidung treffen, "weil man's kann", sondern immer die einfachste Lösung wählen, die die aktuelle Phase (siehe Roadmap) tatsächlich braucht. Zusätzliche Komplexität (weitere Provider, weitere Services, weitere Abstraktionen) kommt erst dazu, wenn ein echter Bedarf dafür besteht.

---

## 7. Rechtliches & Datenschutz — muss vor echtem Launch geklärt sein

- **DSGVO:** Double-Opt-in für die E-Mail-Liste ist Pflicht. Es muss geklärt werden, ob wir als Auftragsverarbeiter für den YouTuber auftreten oder gemeinsam mit ihm verantwortlich sind — das bestimmt, welche Verträge (AVV) nötig sind. Klares Lösch-/Auskunftskonzept für Fan-Daten.
- **Haftung bei fehlerhaften KI-Zusammenfassungen:** Besonders relevant bei Politik-/Gesellschaftsthemen — was, wenn die KI eine Aussage verzerrt zusammenfasst? Muss vertraglich mit dem Partner abgesichert werden (z.B. Hinweis "automatisch generiert, kein Ersatz fürs Originalvideo").
- **Nutzungsrechte:** Wir verarbeiten fremden Content (Video-Inhalt, ggf. Stimme, Kommentare der Community) zu einem eigenen Produkt — muss über den Partnervertrag klar geregelt sein, nicht nur implizit über die OAuth-Freigabe.

---

## 8. Roadmap — MVP zu Ausbaustufen

**Phase 0 — Prototyp/Demo (kein Vertrag mit einem Kanal nötig)**
Ein beliebiger Kanal, 10–20 Videos, Transkripte über `youtube-transcript-api`, Sentiment über die Kommentar-API mit reinem API-Key. Kein Login, keine Bezahlung — reine klickbare Demo, um YouTuber von der Idee zu überzeugen.

**Phase 1 — MVP mit echtem ersten Partner**
Ein YouTuber mit Vertrag inkl. OAuth-Freigabe. Offizielle Data API für Transkripte. Echte Double-Opt-in-Liste, Magic-Link-Login, Zusammenfassung + Sentiment live im Betrieb.

**Phase 2 — Mehrere YouTuber, zentrale Plattform**
Mandantenfähigkeit (Branding pro Kanal auf einer gemeinsamen technischen Basis), Preismodell final ausgearbeitet und ggf. automatisiert abgerechnet, erstes Analytics-Dashboard für die Kunden (YouTuber).

**Phase 3 — Erweiterte Features**
Chat-Assistent (RAG-basiert), ggf. Diskussionsbereich, ggf. mehrsprachige Zusammenfassungen.

**Leitplanke für die Umsetzung:** Bei jeder Phase gilt — nur so viel Komplexität einbauen, wie für die aktuelle Phase nötig ist. Die Architektur (z.B. das Transkript-Interface, die Bifrost-Gateway-Schicht) so anlegen, dass spätere Phasen sich einfügen lassen, aber nichts davon vorab implementieren, was noch nicht gebraucht wird.

---

## 9. Offene Fragen

Siehe separates Dokument: `offene-fragen-youtuber-plattform.md`
