# Offene Fragen — Creator-Plattform

> Gehört zusammen mit `creator-plattform-manifest.md` — dort steht das eigentliche Konzept (Vision, beide Produkte, MVP, Architektur, Roadmap), diese Datei sammelt nur die dazu noch offenen Fragen.

Diese Fragen sind noch nicht final geklärt und sollten vor bzw. während der jeweils relevanten Ausbaustufe adressiert werden.

## Rechtlich & Datenschutz
- Sind wir gegenüber dem YouTuber Auftragsverarbeiter oder gemeinsam Verantwortliche im Sinne der DSGVO? Bestimmt, welche Verträge (AVV) nötig sind.
- Wie sieht das Double-Opt-in und das Lösch-/Auskunftskonzept für die Fan-E-Mail-Listen konkret aus?
- Wie gehen wir mit Haftung um, wenn eine KI-generierte Zusammenfassung eine Aussage verzerrt wiedergibt — besonders relevant bei Politik-/Gesellschaftsthemen?
- Wie werden die Nutzungsrechte am Video-/Kommentar-Content vertraglich mit dem YouTuber geregelt (über die reine OAuth-Freigabe hinaus)? Dürfen Transkripte eines Partners auch für Briefings (Produkt 2) genutzt werden?
- Trägt die Text-und-Data-Mining-Schranke (EU/§ 44b UrhG) das Erstellen von Briefings über öffentliche Auftritte Dritter? Wie gehen wir mit einem Nutzungsvorbehalt des Rechteinhabers um?
- Welche Rechtsgrundlage und Speicherdauer gilt für die personenbezogenen Daten der Zielperson eines Briefings? Wie grenzen wir „Person des öffentlichen Lebens" ab?
- Wie lange bleiben wir für fremde YouTube-Auftritte (Briefings) beim inoffiziellen Untertitel-Zugriff, und ab welchem Punkt setzen wir ausschließlich auf Podcasts, Partnerkanäle und verifizierte Profile (Stufenplan in Abschnitt 7.4 des Manifests)?

## Technisch & Kosten
- Wie bauen wir die Kostenkontrolle für LLM-Aufrufe auf, besonders für Features, die potenziell von vielen Fans gleichzeitig genutzt werden (relevant vor allem für den späteren Chat-Assistenten)?
- Welche Sampling-/Filterstrategie nutzen wir bei Videos mit sehr vielen Kommentaren (z.B. 50.000+), um Sentiment nicht durch Spam/Bots zu verzerren?
- Wie gehen wir mit Videos ohne verfügbare Untertitel um (Livestreams, ältere Uploads)? Ein Whisper-Fallback ist möglich, kostet aber zusätzliche Rechenzeit/Geld — wie viel ist das wert?
- Was passiert mit bereits verarbeiteten Daten, wenn ein Video nachträglich gelöscht oder auf privat gestellt wird?
- Wie gehen wir mit sehr unterschiedlicher Upload-Frequenz zwischen Kanälen um (mehrmals täglich vs. einmal im Monat) — beeinflusst das Preismodell oder nur die technische Skalierung?
- Whisper als API-Dienst oder selbst gehostet? Ab welchem Volumen lohnt sich Selbst-Hosting?
- Eigene Podcast-Suche über Podcast Index/RSS oder Transkript-Anbieter wie Taddy/Podchaser einkaufen? Was kosten diese pro Briefing?
- Wie zuverlässig erkennen wir, dass die Zielperson in einem Auftritt tatsächlich spricht (und nicht nur erwähnt wird)? Reicht die manuelle Bestätigung der Trefferliste durch den Interviewer?
- Die YouTube-Suche kostet 100 Kontingent-Einheiten pro Aufruf — wie viele Briefings pro Tag sind damit möglich, und brauchen wir früh ein höheres Kontingent?

## Plattform & UX
- Wie soll der Login/Dashboard-Flow für Fans konkret aussehen, die mehrere Kanäle abonniert haben (zentrale Übersicht aller abonnierten Zusammenfassungen)?
- Wie personalisieren wir eine gemeinsame technische Plattform pro YouTuber (Branding, Farben, Logo), ohne dass es unübersichtlich oder zu komplex wird?
- Wie tragen sich Fans überhaupt ein — über ein Widget in der Videobeschreibung, im Endcard oder in einem angehefteten Kommentar?
- Droht bei sehr aktiven Kanälen E-Mail-Müdigkeit? Brauchen wir von Anfang an eine Digest-Option (täglich/wöchentlich) statt einer Mail pro Video?

## Business
- Wie soll die Bezahlung durch den YouTuber konkret ablaufen (Rechnung, Abo, automatisierte Abrechnung)?
- Fixpreis gestaffelt nach Listengröße, oder zusätzlich/alternativ ein Umsatzbeteiligungsmodell (ähnlich Patreon)?
- Wie gewinnen wir den allerersten YouTuber ohne bestehende Referenz — z.B. über eine kostenlose oder stark rabattierte Pilotphase?
- Startet Produkt 1 (Fan-Engagement mit Pilotpartner) oder Produkt 2 (Self-Service-Briefing) zuerst? Das Konzept sieht Produkt 1 vor und Produkt 2 als Alternative, falls kein Pilotpartner unterschreibt — nach welcher Frist tauschen wir?
- Preis pro Briefing: Einzelpreis, Abo oder beides? Wer ist der bessere Erstkunde — einzelne Podcast-Hosts oder Redaktionen?
- Wie heißt das Produkt? Der Name muss beide Produkte tragen können, ohne „YouTube" oder „Podcast" im Namen.
- Was ist unser eigentlicher Wettbewerbsvorteil (Moat), falls ein größerer Player (oder YouTube selbst) etwas Ähnliches baut? Vermutlich eher die direkte Vertrauensbeziehung zu den YouTubern als die reine Technik.
