# Offene Fragen — YouTuber Fan-Plattform

> Gehört zusammen mit `youtuber-plattform-konzept.md` — dort steht das eigentliche Konzept (Vision, MVP, Architektur, Roadmap), diese Datei sammelt nur die dazu noch offenen Fragen.

Diese Fragen sind noch nicht final geklärt und sollten vor bzw. während der jeweils relevanten Ausbaustufe adressiert werden.

## Rechtlich & Datenschutz
- Sind wir gegenüber dem YouTuber Auftragsverarbeiter oder gemeinsam Verantwortliche im Sinne der DSGVO? Bestimmt, welche Verträge (AVV) nötig sind.
- Wie sieht das Double-Opt-in und das Lösch-/Auskunftskonzept für die Fan-E-Mail-Listen konkret aus?
- Wie gehen wir mit Haftung um, wenn eine KI-generierte Zusammenfassung eine Aussage verzerrt wiedergibt — besonders relevant bei Politik-/Gesellschaftsthemen?
- Wie werden die Nutzungsrechte am Video-/Kommentar-Content vertraglich mit dem YouTuber geregelt (über die reine OAuth-Freigabe hinaus)?

## Technisch & Kosten
- Wie bauen wir die Kostenkontrolle für LLM-Aufrufe auf, besonders für Features, die potenziell von vielen Fans gleichzeitig genutzt werden (relevant vor allem für den späteren Chat-Assistenten)?
- Welche Sampling-/Filterstrategie nutzen wir bei Videos mit sehr vielen Kommentaren (z.B. 50.000+), um Sentiment nicht durch Spam/Bots zu verzerren?
- Wie gehen wir mit Videos ohne verfügbare Untertitel um (Livestreams, ältere Uploads)? Ein Whisper-Fallback ist möglich, kostet aber zusätzliche Rechenzeit/Geld — wie viel ist das wert?
- Was passiert mit bereits verarbeiteten Daten, wenn ein Video nachträglich gelöscht oder auf privat gestellt wird?
- Wie gehen wir mit sehr unterschiedlicher Upload-Frequenz zwischen Kanälen um (mehrmals täglich vs. einmal im Monat) — beeinflusst das Preismodell oder nur die technische Skalierung?

## Plattform & UX
- Wie soll der Login/Dashboard-Flow für Fans konkret aussehen, die mehrere Kanäle abonniert haben (zentrale Übersicht aller abonnierten Zusammenfassungen)?
- Wie personalisieren wir eine gemeinsame technische Plattform pro YouTuber (Branding, Farben, Logo), ohne dass es unübersichtlich oder zu komplex wird?
- Wie tragen sich Fans überhaupt ein — über ein Widget in der Videobeschreibung, im Endcard oder in einem angehefteten Kommentar?
- Droht bei sehr aktiven Kanälen E-Mail-Müdigkeit? Brauchen wir von Anfang an eine Digest-Option (täglich/wöchentlich) statt einer Mail pro Video?

## Business
- Wie soll die Bezahlung durch den YouTuber konkret ablaufen (Rechnung, Abo, automatisierte Abrechnung)?
- Fixpreis gestaffelt nach Listengröße, oder zusätzlich/alternativ ein Umsatzbeteiligungsmodell (ähnlich Patreon)?
- Wie gewinnen wir den allerersten YouTuber ohne bestehende Referenz — z.B. über eine kostenlose oder stark rabattierte Pilotphase?
- Was ist unser eigentlicher Wettbewerbsvorteil (Moat), falls ein größerer Player (oder YouTube selbst) etwas Ähnliches baut? Vermutlich eher die direkte Vertrauensbeziehung zu den YouTubern als die reine Technik.
