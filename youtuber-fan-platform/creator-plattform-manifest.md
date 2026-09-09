# Creator-Plattform für öffentliche Audio- & Video-Inhalte — Konzept, Masterplan & Manifest

> Dieses Dokument ist der Masterplan. Es beschreibt die gesamte Idee von A bis Z: Vision, Beteiligte, Produkte, Geschäftsmodell, Einstiegspunkte, MVP, Architektur, Recht, Roadmap und Risiken. Es ist bewusst kein technischer Implementierungsplan, nennt aber überall dort konkrete Technologien, wo eine Entscheidung bereits absehbar ist.
>
> Noch nicht entschiedene Fragen stehen gesammelt in `offene-fragen-youtuber-plattform.md`, aufgeteilt nach Rechtlich/Datenschutz, Technisch/Kosten, Plattform/UX und Business.
>
> Ein Produktname ist noch nicht festgelegt; im Text steht deshalb neutral „die Plattform".

---

## 0. Auf einen Blick

**Was wir bauen:** Eine Plattform, die öffentlich gesprochene Inhalte — YouTube-Videos und Podcast-Episoden — automatisch transkribiert, mit KI analysiert und daraus zwei klar getrennte Produkte macht:

1. **Fan-Engagement für Creator:** Nach jedem neuen Video bzw. jeder neuen Episode bekommen die eingetragenen Fans automatisch eine Zusammenfassung per E-Mail, ergänzt um eine Stimmungsanalyse der Kommentare. Der Creator zahlt, gestaffelt nach Größe seiner Fan-Liste. Der Creator hat null Zusatzaufwand.
2. **Gäste-Briefing für Interviewer:** Ein Interviewer gibt den Namen seines nächsten Gastes ein und bekommt ein Briefing über dessen öffentliche Auftritte der letzten Monate — Themen, Positionen, bereits gestellte Fragen — über YouTube und Podcasts hinweg.

**Warum es funktioniert:** Beide Produkte laufen auf derselben technischen Pipeline (Quelle → Transkript → KI-Analyse → Ausgabe), sprechen aber unterschiedliche Kaufmotive an: Fanbindung auf der einen, Zeitersparnis bei der Recherche auf der anderen Seite. Viele Kunden des einen Produkts sind natürliche Kunden des anderen.

**Wie wir starten:** Mit einem bewusst kleinen MVP, der bereits Geld verdient: ein zahlender Pilot-Creator für Produkt 1, E-Mail als Haupt-Interface, keine große Dashboard-App. Produkt 2 folgt als Self-Service-Angebot, sobald die Pipeline im Betrieb steht — es kann bei Bedarf vorgezogen werden, weil es keinen Vertragspartner braucht (siehe Abschnitt 10).

**Was nicht verhandelbar ist:** Die Plattform soll einladend sein, Spaß machen und einfach funktionieren — für Fans, Creator und Interviewer genauso wie für uns beim Bauen. Technisch heißt das: minimalistisch, robust, zuverlässig, modular und von Anfang an erweiterbar, aber ohne Overengineering. Wir halten uns alle Wege offen (Quellen, KI-Modelle, Ausgabekanäle), ohne sie alle sofort zu gehen. Wir wollen schnell bauen, schnell lernen und schnell erste Erfolge feiern.

---

## 1. Vision & Kernidee

### 1.1 Der Ursprung: Fan-Bindung für große Kanäle

Ausgangspunkt war ein Service für große YouTuber (z. B. aus dem Bereich Politik, Gesellschaft, komplexere Themen), der ihre Abonnenten enger an den Kanal bindet, ohne dass der YouTuber selbst zusätzlichen Aufwand hat.

Fans tragen sich mit ihrer E-Mail-Adresse in eine Liste ein. Nach jedem neuen Video bekommen sie automatisch Mehrwert-Content dazu (Start: eine Zusammenfassung). **Bezahlt wird von den Creatorn selbst, nicht von den Fans** — gestaffelt nach Anzahl der Abonnenten in der Liste. Der Gedanke: Für einen großen Kanal ist Marketing/Fan-Bindung schwierig, ein solcher Service ist ein leicht buchbarer Zusatz-Mehrwert für die eigene Community.

Langfristig: eine **zentrale, weiße Plattform**, die für mehrere Creator gleichzeitig funktioniert, personalisierbar (Branding) pro Kanal, mit einem gemeinsamen Login für Fans, die mehrere Kanäle abonniert haben.

### 1.2 Die Neuausrichtung: eine Ebene abstrakter denken

Die Plattform sollte nicht als „YouTube-Zusammenfassungs-Tool" gedacht werden, sondern eine Ebene abstrakter: als Werkzeug, das öffentlich gesprochene Inhalte — egal ob auf YouTube oder als Podcast veröffentlicht — durchsuchbar, zusammenfassbar und nutzbar macht.

Das Produkt ist nicht „Zusammenfassung eines YouTube-Videos", sondern **„Zusammenfassung dessen, was eine Person oder ein Kanal öffentlich gesagt hat"**. YouTube und Podcast-Feeds sind dabei nur zwei austauschbare Datenquellen im Hintergrund, technisch strukturell ähnlich: Audio/Video rein, Transkript raus, KI-Analyse obendrauf.

Das ist naheliegend, weil es technisch fast der gleiche Prozess ist und weil Podcasts als Format riesig sind — viele lange, inhaltsreiche Interviews, die sich genauso gut für Zusammenfassung und Analyse eignen wie YouTube-Videos.

### 1.3 Warum das die Idee stärkt, statt sie zu verwässern

Der naheliegende Einwand: Wenn eine Plattform „alles kann", kann sie am Ende nichts richtig. Deswegen bleibt die Öffnung auf zwei Quellen (YouTube + Podcasts) **technisch-strukturell**, nicht Teil des Markenversprechens nach außen. Beworben wird weiterhin über die Zielgruppe, nicht über die Datenquelle. Das ergibt zwei klar getrennte Kernprodukte (Abschnitt 3), die auf einem gemeinsamen Fundament stehen.

Der rote Faden lautet: **eine technische Plattform, zwei klar getrennte, verständliche Produkte, keine unklare „Alles-Tool"-Botschaft nach außen.**

### 1.4 Marktlage

Stand unserer Recherche: Es gibt einzelne Bausteine am Markt (z. B. Self-Service-Tools, die einzelne Video-Zusammenfassungen erzeugen, KI-Notiz-Tools, Transkriptionsdienste), aber **kein fertiges Managed-Service-Produkt** in dieser Kombination, das ein Creator einfach bucht und laufen lässt — und erst recht keines, das Fan-Bindung und Interview-Vorbereitung auf einer gemeinsamen Datenbasis verbindet. Das ist die Nische.

Unser eigentlicher Wettbewerbsvorteil ist dabei weniger die Technik (die ist reproduzierbar) als die **direkte Vertrauensbeziehung zu den Creatorn** und — mit der Zeit — der wachsende, bereits aufbereitete Bestand an Transkripten und Analysen, der jedes weitere Briefing schneller und günstiger macht (siehe Abschnitt 3.3).

### 1.5 Was die Plattform ausmacht

Fünf Eigenschaften, an denen sich jede Entscheidung messen lässt — bei Features, Design und Code gleichermaßen:

- **Einladend.** Ein Fan trägt eine E-Mail ein und ist dabei. Ein Creator ist nach einem Gespräch und einem Klick live. Ein Interviewer tippt einen Namen. Keine Formulare, die man erklären muss, keine Hürden, die man rechtfertigen muss.
- **Macht Spaß.** Die Zusammenfassung liest sich gern, nicht pflichtbewusst: klare Sprache, ein starkes Zitat, das Stimmungsbild der Community, ein Link, der direkt an die spannendste Stelle im Video springt. Das Briefing fühlt sich an wie ein guter Kollege, der schon vorgearbeitet hat.
- **Funktioniert einfach.** Nichts, was der Kunde konfigurieren muss. Nach dem Onboarding läuft der Service, ohne dass jemand daran denken muss.
- **Minimalistisch.** Wenige Features, dafür richtig gut. Jede Seite hat genau einen Zweck. Was keinen Eintrag in der Tabelle in Abschnitt 2 erzeugt, wird nicht gebaut.
- **Robust und zuverlässig.** Jeder neue Beitrag wird genau einmal verarbeitet und genau einmal zugestellt. Fällt eine Quelle oder ein Modell aus, springt die nächste Implementierung ein. Vertrauen entsteht durch Verlässlichkeit, nicht durch Feature-Listen.

Dieselben Eigenschaften gelten für die Entwicklung selbst: kleine Schritte, jede Woche etwas Vorzeigbares, ein Deployment mit einem Befehl, Code, den man nach drei Monaten noch versteht.

---

## 2. Die Beteiligten und ihre Motive

Eine Plattform funktioniert nur, wenn jede Partei etwas Klares bekommt und etwas Klares gibt. Diese Tabelle ist der Prüfstein für jede spätere Feature-Idee: Wenn eine Idee für keine der Parteien einen Eintrag in der Spalte „bekommt" erzeugt, wird sie nicht gebaut.

| Partei | Wer das ist | Was sie will | Was sie gibt | Was sie bekommt |
|---|---|---|---|---|
| **Creator** (YouTuber, Podcaster) | Kanal mit aktiver Fanbase, oft ein kleines Team | Fans binden, Reichweite außerhalb des Algorithmus, seriöser Partner, kein Zusatzaufwand | Vertrag, Geld, OAuth-Freigabe, einen Link in der Videobeschreibung/den Shownotes | Automatischen Mehrwert-Content für die Community, eine eigene E-Mail-Liste (die er sonst nie aufbauen würde), später Analytics |
| **Fan** | Abonnent des Creators | Mehr vom Creator konsumieren, Zeit sparen, nichts verpassen | E-Mail-Adresse (Double-Opt-in) | Zusammenfassungen, Stimmungsbild der Community, später Dashboard/Chat |
| **Interviewer** (Journalist, Podcast-Host, YouTuber mit Interviewformat) | Bereitet Gespräche mit bekannten Personen vor | Vollständige Vorbereitung in Minuten statt Stunden | Geld pro Briefing oder Abo | Briefing-Dokument über die öffentlichen Auftritte des Gastes |
| **Die Plattform** (wir) | Betreiber | Wiederkehrende Umsätze, Vertrauen, wachsender Datenbestand | Technik, Betrieb, rechtliche Absicherung, Support | Umsatz von Creatorn und Interviewern |

Zwei Beobachtungen, die das Geschäftsmodell tragen:

- **Der Fan zahlt nichts und muss nichts installieren.** Die Einstiegshürde ist eine E-Mail-Adresse. Das ist der Grund, warum Listen überhaupt wachsen können.
- **Der Creator ist unser Vertragspartner, nicht der Fan.** Damit ist klar, wer OAuth-Freigaben erteilt, wer für Nutzungsrechte unterschreibt und wer die Rechnung bekommt. Rechtlich und organisatorisch ist das deutlich einfacher als ein B2C-Modell mit tausenden Kleinstkunden.

---

## 3. Die zwei Produkte

### 3.1 Produkt 1 — Fan-Engagement für Creator

Der bestehende Kern der Idee. Ein Creator (YouTuber oder Podcaster) bietet seinen Abonnenten automatische Video-/Episoden-Zusammenfassungen per E-Mail plus Kommentar-Sentiment-Analyse. Bezahlt wird vom Creator, gestaffelt nach Abonnentenzahl.

**Feature 1: Automatische Zusammenfassung per E-Mail**
- Ablauf: neues Video / neue Episode wird erkannt → Transkript wird geholt → LLM erstellt Zusammenfassung → E-Mail geht an alle Abonnenten der Liste raus, mit einem „Online ansehen"-Link.
- Trigger YouTube: Die YouTube Data API unterstützt Push-Benachrichtigungen über **PubSubHubbub** — man abonniert den Kanal-Feed einmalig und bekommt dann bei jedem neuen Upload automatisch eine Benachrichtigung an eine eigene Callback-URL, ganz ohne Polling.
- Trigger Podcast: Podcasts werden über ihren **RSS-Feed** veröffentlicht. Der Feed wird in kurzen Abständen abgefragt (Polling ist hier billig und robust); unterstützt der Feed WebSub (das Protokoll hinter PubSubHubbub), wird es genutzt.
- Inhaltlich muss die Zusammenfassung dem Ton des Kanals gerecht werden (sachlich, keine Verzerrung, kein Clickbait). Sie ersetzt das Original nicht, sondern macht Lust darauf bzw. hilft, es einzuordnen. Ein sichtbarer Hinweis „automatisch generiert" gehört in jede Ausgabe (siehe Abschnitt 9).

**Feature 2: Kommentar-Sentiment-Zusammenfassung pro Video**
- Ähnlich wie die Rezensions-Zusammenfassungen bei Amazon: ein kurzer, automatisch generierter Überblick über die Grundstimmung in den Kommentaren eines Videos — welche Punkte kamen an, wo gab es Widerspruch, welche Fragen stellt die Community.
- Technisch: `commentThreads.list` aus der YouTube Data API liefert öffentliche Kommentare zu jedem öffentlichen Video — **hierfür reicht ein simpler API-Key, es ist keine Zustimmung/OAuth des Kanalinhabers nötig.** Das heißt, dieses Feature lässt sich sogar für Demo-Zwecke auf beliebigen fremden Kanälen zeigen.
- Muss mitgebaut werden: Filterung von Spam-/Bot-Kommentaren vor der Sentiment-Auswertung sowie eine Sampling-Strategie bei Videos mit sehr vielen Kommentaren (nicht alles lesen/verarbeiten).
- Ehrliche Einschränkung: **Podcasts haben keine vergleichbare Kommentarfunktion.** Für reine Podcast-Creator entfällt dieses Feature; Podcaster, die ihre Episoden zusätzlich auf YouTube veröffentlichen, bekommen es über die YouTube-Quelle. Features degradieren also sauber je nach Quelle, statt dass die Plattform etwas verspricht, was sie für eine Quelle nicht liefern kann.

**Wie der Fan das erlebt**
- Er klickt auf einen Link in der Videobeschreibung / den Shownotes, trägt seine E-Mail ein, bestätigt sie (Double-Opt-in) — fertig.
- Nach jedem neuen Beitrag kommt eine E-Mail. Jede E-Mail hat einen Abmelde-Link und einen „Online ansehen"-Link.
- Später: ein zentrales Dashboard mit **Magic-Link-Login per E-Mail** (kein Passwort) — passt zum Modell, dass wir ohnehin nur die E-Mail-Adresse haben, und ist einfach und sicher genug. Dort sieht er, welche Kanäle er abonniert hat und welche Zusammenfassungen es gibt.

**Wie der Creator das erlebt**
- Onboarding: Vertrag, OAuth-Freigabe für seinen YouTube-Kanal bzw. Angabe seines Podcast-Feeds, Logo/Farbe/Name für das Branding, fertig.
- Danach: nichts mehr. Er verlinkt einmal die Sign-up-Seite und der Service läuft.
- Später: ein Kunden-Dashboard mit Listengröße, Öffnungs- und Klickraten.

### 3.2 Produkt 2 — Gäste-Briefing für Interviewer

Das neue Feature, das erst durch die Neuausrichtung möglich wird. Ein Interviewer (z. B. ein YouTuber, der bald jemanden interviewt) gibt den Namen einer Zielperson ein und bekommt ein automatisch erstelltes Briefing über deren öffentliche Auftritte der letzten Monate — Themen, Positionen, bereits gestellte Fragen.

Hier wird die Öffnung auf Podcasts sogar zum echten Mehrwert: Personen treten nicht nur auf YouTube auf, sondern oft auch in fremden Podcasts. Ein Briefing, das nur YouTube abdeckt, wäre unvollständig; über beide Quellen hinweg wird es tatsächlich vollständig.

**Wie der Interviewer das erlebt**
1. Er gibt Name der Zielperson und den gewünschten Zeitraum ein (Standard: die letzten sechs Monate).
2. Die Plattform sucht Auftritte auf YouTube (Data-API-Suche) und in Podcasts (Podcast-Verzeichnisse, RSS-Feeds), zeigt die Trefferliste und lässt ihn bestätigen, welche Auftritte gemeint sind. Dieser Schritt ist wichtig, um Namensdopplungen und Fehltreffer auszusortieren — er ist der billigste und zuverlässigste Relevanzfilter.
3. Bezahlung (pro Briefing oder als Abo für Vielnutzer), dann läuft die Pipeline: Transkripte holen, prüfen, ob die Person tatsächlich spricht (inhaltliche Verifikation im Transkript, nicht nur im Titel), Themen extrahieren, Positionen zusammenfassen, bereits gestellte Fragen sammeln.
4. Das Briefing kommt per E-Mail als Link auf eine Web-Seite (und/oder PDF), mit Verweisen auf die Quellen inklusive Zeitstempel, damit sich jede Aussage nachprüfen lässt.

**Was ein gutes Briefing enthält**
- Übersicht der Auftritte (wo, wann, wie lang, Link).
- Die wichtigsten Themen und die Position der Person dazu, mit Belegstellen.
- Fragen, die ihr bereits gestellt wurden — damit der Interviewer sie nicht wiederholt oder bewusst tiefer geht.
- Widersprüche oder Entwicklungen über die Zeit („im März sagte sie X, im Juli Y").
- Ein klarer Hinweis: automatisch erstellt, Belegstellen prüfen.

**Warum das ein eigenes Produkt ist und kein Feature von Produkt 1**
- Anderer Käufer, anderes Motiv: Zeitersparnis bei der Recherche statt Fanbindung.
- Anderes Preismodell: pro Nutzung statt monatlich nach Listengröße.
- Kein Vertragspartner nötig: Der Interviewer kauft selbst, sofort, ohne Onboarding. Das macht Produkt 2 zum schnellsten Weg zu ersten Umsätzen und zum idealen Türöffner für Produkt 1 (siehe 3.3).

### 3.3 Warum beide Produkte zusammengehören

**Gleiche Pipeline.** Beide Produkte nutzen dieselbe technische Grundlage: Quelle → Transkript → KI-Analyse → Ausgabe. Nur der Auslöser (neuer Beitrag vs. Suchanfrage), der Prompt und das Ausgabeformat unterscheiden sich.

**Natürliches Cross-Selling.** Viele Kunden von Produkt 1 sind potenziell auch Kunden von Produkt 2, sofern sie selbst Interviewformate machen (Beispiel: Lex Fridman) — das schafft natürliches Cross-Selling innerhalb derselben Plattform. Umgekehrt ist jeder Interviewer, der ein Briefing kauft, ein Creator mit Fanbase und damit ein Kandidat für Produkt 1.

**Das Briefing als Verkaufswerkzeug.** Der stärkste Pitch für einen Creator, den wir für Produkt 1 gewinnen wollen, ist ein Briefing über ihn selbst: „So sieht zusammengefasst aus, was du in den letzten drei Monaten öffentlich gesagt hast." Das ist ohne Vertrag und ohne Freigabe erstellbar, dauert Minuten und zeigt die Qualität der Pipeline besser als jede Folie.

**Datenkreislauf.** Jeder verarbeitete Auftritt landet als Transkript und Analyse im Bestand. Ein Briefing über eine Person, deren Auftritte teilweise schon verarbeitet sind, ist schneller und günstiger. Wichtige Einschränkung: Transkripte, die wir über die OAuth-Freigabe eines Vertragspartners bekommen haben, dürfen nur für dessen Produkt genutzt werden, sofern der Vertrag nichts anderes erlaubt (siehe Abschnitt 9).

### 3.4 Positionierung nach außen

Trotz der technischen Öffnung: Die Außenkommunikation bleibt scharf auf die zwei Produkte fokussiert, nicht auf „wir verarbeiten jedes Audio-/Video-Format". Also z. B.:

- Für Creator: *„Binde deine Fans mit automatischen Zusammenfassungen — egal ob YouTube oder Podcast."*
- Für Interviewer: *„Bereite dich auf jedes Interview in Minuten vor — mit allem, was dein Gast je öffentlich gesagt hat."*

Zielgruppen konkret:
- **Creator mit aktiver Fanbase** (YouTube oder Podcast), die ihre Abonnenten enger binden wollen — zahlender Kunde für Produkt 1.
- **Interviewer/Journalisten/Podcast-Hosts**, die sich auf Gespräche mit bekannten Personen vorbereiten — zahlender Kunde für Produkt 2.

---

## 4. Geschäftsmodell & Preislogik

### 4.1 Wer zahlt wofür

| Produkt | Zahler | Modell | Warum so |
|---|---|---|---|
| Fan-Engagement | Creator | Monatlicher Fixpreis, gestaffelt nach Anzahl der Abonnenten in der Liste | Planbar für beide Seiten; wächst mit dem Nutzen, den der Creator hat; einfach zu erklären |
| Gäste-Briefing | Interviewer | Preis pro Briefing; alternativ Monats-Abo mit Kontingent für Vielnutzer | Kein Onboarding, sofortiger Kauf, Preis direkt an den gesparten Stunden messbar |

Fans zahlen nie. Das bleibt eine Grundregel, weil die Liste sonst nicht wächst und der Creator dann nichts hat, wofür er zahlen würde.

### 4.2 Kostenseite pro Einheit (Größenordnungen, zu validieren)

Damit die Preise nicht aus der Luft gegriffen sind, hier die Kostentreiber pro verarbeitetem Beitrag:

- **Transkript:** kostenlos, wenn YouTube-Untertitel vorhanden sind (offiziell mit OAuth-Freigabe des Partners, in der Demo über eine inoffizielle Bibliothek). Für Podcasts oder Videos ohne Untertitel: Speech-to-Text (Whisper), je nach Anbieter und Selbst-Hosting im Bereich von Cent-Beträgen pro Minute Audio — eine zweistündige Episode kostet damit unter einem Euro.
- **LLM-Analyse:** Ein einstündiges Gespräch ergibt grob 8.000–12.000 Wörter Transkript. Eine Zusammenfassung daraus kostet mit einem aktuellen Modell wenige Cent, ein umfangreicheres Briefing über zehn Auftritte einige zehn Cent bis wenige Euro.
- **E-Mail-Versand:** Transaktions-E-Mail-Dienste liegen im Bereich von Zehntel-Cent pro Mail. Eine Liste mit 10.000 Fans kostet pro Beitrag also einstellige Euro-Beträge.
- **Kommentare:** Die YouTube Data API ist kostenlos, Kontingent siehe Abschnitt 7.9.

Fazit: Die variablen Kosten pro Beitrag sind niedrig und gut vorhersagbar. Der teuerste Posten ist nicht Rechenzeit, sondern Betrieb, Support und rechtliche Absicherung. Preise können daher mit gesundem Abstand über den variablen Kosten liegen.

### 4.3 Preisstaffel als Arbeitshypothese

Die konkreten Zahlen sind eine Hypothese für die Gespräche mit den ersten Partnern und werden dort validiert, nicht vorher festgelegt. Die Struktur steht:

- **Produkt 1:** drei bis vier Stufen nach Listengröße (z. B. bis 1.000 / bis 10.000 / bis 50.000 / darüber individuell), monatlich, kündbar. Die Staffel wächst mit dem Wert, den die Liste für den Creator hat.
- **Produkt 2:** ein Einzelpreis pro Briefing im Bereich einer guten Arbeitsstunde eines Journalisten, plus ein Abo für Redaktionen und Vielinterviewer.
- **Pilotphase:** Der allererste Creator bekommt einen deutlich rabattierten, aber nicht kostenlosen Pilotpreis. Kostenlos validiert keine Zahlungsbereitschaft; ein symbolischer Preis schon.
- **Umsatzbeteiligung** (ähnlich Patreon) bleibt als Alternative im Hinterkopf, ist aber für den Start zu komplex — Fixpreise sind erklärbar und abrechenbar.

### 4.4 Wie das Geld fließt

- MVP: manueller Vertrag mit dem Pilotpartner, Rechnung per Hand. Keine automatisierte Abrechnung.
- Ab Phase 2: Zahlungsdienstleister (z. B. Stripe: Checkout für Briefings, Billing für Creator-Abos). Nicht selbst bauen.

---

## 5. Der Startpunkt: Webseiten, Zugänge, Einstiegspunkte

Die Frage „Gibt es eine Website? Gibt es mehrere?" ist zentral, weil sie entscheidet, wie viel Oberfläche wir am Anfang bauen müssen. Die Antwort: **eine Domain, eine Web-Anwendung, drei klar getrennte Bereiche.** Sie liegen technisch in derselben Anwendung, sind aber inhaltlich und in der Ansprache strikt getrennt.

### 5.1 Die drei Bereiche

**Bereich A — Verkaufsseite (B2B, öffentlich, kein Login).**
Erklärt den Service den Creatorn und Interviewern: Feature-Übersicht, Preismodell, Demo, Kontaktformular. Zielgruppe ist der Creator bzw. sein Team und der Interviewer, nicht die Fans. Für den Start reicht eine einzelne, klassische Landingpage (z. B. `unserservice.de`) mit je einem Abschnitt pro Produkt.

**Bereich B — Fan-Bereich (B2C).**
- *Sign-up-Seite pro Kanal* (`unserservice.de/k/<kanalname>`): E-Mail eintragen, Double-Opt-in bestätigen. Trägt Name, Logo und Farbe des Creators, damit sich der Fan an der richtigen Stelle fühlt. Das ist der Link, den der Creator in Videobeschreibung, angeheftetem Kommentar, Endcard oder Shownotes platziert.
- *„Online ansehen"-Seite pro Zusammenfassung* (`unserservice.de/s/<langer-zufälliger-token>`): öffentlich erreichbar, aber nicht erratbar, kein Login. Ebenfalls im Branding des Kanals, mit einem „Auch abonnieren"-Hinweis — Fans leiten E-Mails weiter, und jede weitergeleitete Mail ist ein neuer Einstiegspunkt.
- *Später: zentrales Fan-Dashboard* mit Magic-Link-Login, sobald es mehrere Kanäle gibt und damit überhaupt etwas „zu übersehen" ist.

**Bereich C — Kundenbereich (Creator und Interviewer, mit Login).**
- Creator: Onboarding (OAuth-Freigabe, Podcast-Feed, Branding), Listengröße, später Analytics.
- Interviewer: Briefing beauftragen, bezahlen, abrufen.
- Login: ebenfalls Magic-Link. Ein Auth-Mechanismus für alle Rollen, keine Passwörter.
- Im MVP ist dieser Bereich minimal oder wird durch uns manuell ersetzt (Onboarding per Videocall, OAuth-Link per Mail). Er wächst mit der Zahl der Kunden.

### 5.2 Warum E-Mail das Haupt-Interface des MVP ist

Statt direkt ein voll authentifiziertes Multi-Kanal-Dashboard zu bauen, setzt der MVP komplett auf die E-Mail als Haupt-Interface: Die Zusammenfassung kommt ohnehin per Mail, und der „Online ansehen"-Link deckt den Hauptbedarf („ich will die Zusammenfassung nochmal nachlesen") ab, ohne dass wir Auth, Sessions oder ein Dashboard bauen müssen. Auch das Briefing (Produkt 2) wird per E-Mail als Link zugestellt — dasselbe Muster.

Der zentrale Login mit Übersicht über alle abonnierten Kanäle — das, was ursprünglich als „eine Plattform" gedacht war — kommt erst in Phase 2, sobald es mehrere Kanäle gleichzeitig gibt und dadurch ein echter Bedarf für eine Übersichtsseite entsteht. Bei nur einem Partner-Kanal lohnt sich der Aufwand vorher kaum.

### 5.3 Eigene Landingpage pro Creator?

Für die reine Konsum-Oberfläche reicht eine gemeinsame technische Basis. Branded Einstiegspunkte pro Kanal (die Sign-up-Seite, später ggf. eine Subdomain wie `kanalname.unserservice.de`) sind eine schlanke, austauschbare Fassade vor demselben Backend: Name, Logo, Farbe, Begrüßungstext — mehr Personalisierung braucht es lange nicht, und mehr würde die Plattform unübersichtlich machen. Die Kernarchitektur bleibt davon unberührt.

### 5.4 Ausbaustufen der Oberfläche

| Phase | Verkaufsseite (A) | Fan-Bereich (B) | Kundenbereich (C) |
|---|---|---|---|
| 0 Demo | Einfache Landingpage mit Demo-Zusammenfassungen und Demo-Briefing | Beispiel-„Online ansehen"-Seiten | keiner |
| 1 MVP | Landingpage + Kontaktformular | Sign-up-Seite pro Kanal, „Online ansehen"-Seiten, kein Login | manuell durch uns |
| 2 Plattform | Preise, Self-Service-Einstieg für Briefings | Magic-Link-Login + zentrales Dashboard | Creator-Dashboard mit Analytics, Briefing-Self-Service, Bezahlung |
| 3+ | — | Chat-Assistent, ggf. Diskussionsbereich | erweiterte Analytics, Team-Zugänge |

---

## 6. MVP — was genau gebaut wird

Bewusst klein gehalten. Ziel: schnell etwas Vorzeigbares und Zahlendes haben, mit dem man auf weitere Creator zugehen kann.

### 6.1 Im MVP

- **Ein Pilot-Creator** mit Vertrag, rabattiertem Pilotpreis und OAuth-Freigabe (bzw. Podcast-Feed).
- **Feature 1:** automatische Zusammenfassung per E-Mail nach jedem neuen Beitrag, inklusive „Online ansehen"-Seite.
- **Feature 2:** Kommentar-Sentiment, sofern der Creator auf YouTube veröffentlicht.
- **Sign-up-Seite** für den Kanal mit Double-Opt-in, Abmelde-Link in jeder Mail.
- **Landingpage** mit Demo-Material und Kontaktformular.
- **Die gemeinsame Pipeline** (Quelle → Transkript → Analyse → Ausgabe) sauber, aber minimal: ein YouTube-Connector, ein Podcast-Connector, ein Transkript-Interface mit zwei Implementierungen, ein LLM-Gateway, ein E-Mail-Dienst. Das ist der Teil, der später beide Produkte trägt und deshalb von Anfang an ordentlich geschnitten wird.
- **Der MVP braucht die offizielle YouTube-API nicht zwingend.** Transkripte kommen im ersten Schritt über die inoffizielle Bibliothek oder Whisper, Metadaten über den öffentlichen Kanal-Feed. Sobald der Pilotpartner seine OAuth-Freigabe erteilt, wird die offizielle Implementierung im Transkript-Interface aktiviert — ein Konfigurationswechsel, kein Umbau. Spätestens damit läuft alles offiziell im Rahmen der YouTube-Bedingungen.

### 6.2 Bewusst NICHT im MVP

- Kein Chat-Assistent (deutlich komplexer, siehe Zukunftsliste).
- Kein Diskussionsbereich.
- Kein Fan-Dashboard, kein Fan-Login.
- Keine Mandantenfähigkeit im Sinne von Self-Service-Onboarding — erst mal ein Kanal, ein Setup; die Datenhaltung ist aber von Anfang an pro Creator getrennt, damit Phase 2 kein Umbau ist.
- Keine ausgefeilte Bezahl-Logik — ein manueller/vertraglicher Deal mit dem ersten Partner, keine automatisierte Abrechnung.
- Kein Self-Service-Briefing. Briefings werden in Phase 0/1 als **manuell angestoßenes Verkaufswerkzeug** genutzt (wir erzeugen ein Briefing über den Creator, den wir gewinnen wollen), aber nicht als Produkt verkauft.

### 6.3 Wann der MVP „fertig" ist

Der MVP gilt als erfolgreich, wenn alle Punkte erfüllt sind:
- Ein Creator zahlt (auch wenn wenig).
- Zusammenfassungen gehen ohne manuellen Eingriff nach jedem neuen Beitrag raus.
- Die Liste wächst messbar über den Link des Creators.
- Öffnungsraten liegen deutlich über dem Newsletter-Durchschnitt (sonst stimmt der Inhalt nicht).
- Der Creator sagt von sich aus, dass er den Service weiterempfehlen würde.

Erst dann lohnt sich Phase 2.

---

## 7. Technische Architektur

### 7.1 Leitprinzipien

Für den gesamten Tech-Stack gilt: **wartbar, minimalistisch, gut bedienbar und verständlich.** Also keine Architektur-Entscheidung treffen, „weil man's kann", sondern immer die einfachste Lösung wählen, die die aktuelle Phase tatsächlich braucht. Zusätzliche Komplexität (weitere Provider, weitere Services, weitere Abstraktionen) kommt erst dazu, wenn ein echter Bedarf besteht.

Daraus folgen konkrete Regeln:
- **Ein Modularer Monolith**, keine Microservices. Eine Codebasis, ein Deployment, klare interne Module (Connectoren, Transkript, Analyse, Ausgabe, Web).
- **Pipeline zuerst, Oberfläche zuletzt.** Der Wert entsteht in der Pipeline; die Oberfläche ist im MVP E-Mail plus wenige server-gerenderte Seiten.
- **Genau zwei bewusste Abstraktionen** von Anfang an: das Quellen-/Transkript-Interface und das LLM-Gateway. Beide sind billig und verhindern nachweislich teure Umbauten. Alles andere wird erst abstrahiert, wenn es die zweite Implementierung tatsächlich gibt.
- **Nichts selbst bauen, was ein Dienst zuverlässig anbietet**: E-Mail-Versand, Zahlungen, Speech-to-Text, LLM-Routing.
- **Modular ja, verteilt nein.** Module sind Python-Pakete im selben Repository mit klaren Schnittstellen, keine eigenen Services. Modularität soll kleine, ständige Änderungen und Erweiterungen erlauben — nicht Infrastruktur erzeugen.
- **Alle Wege offenhalten, keinen vorab gehen.** Das Quellen-Interface kennt heute zwei Connectoren, das Gateway heute einen Anbieter. Ein dritter Connector oder ein zweites Modell sind eine neue Datei bzw. eine Konfigurationszeile — und werden erst dann angelegt, wenn sie gebraucht werden.
- **Ein Befehl zum Deployen.** Die gesamte Plattform startet mit `docker compose up` auf einem einzelnen Server. Wenn das Deployment ein Dokument braucht, ist es zu komplex.
- **Kein Overengineering.** Keine Abstraktion ohne zweite Implementierung, keine Konfiguration für Werte, die sich nicht ändern, keine Generalisierung „für später". Bewusste Abkürzungen werden im Code als solche markiert, damit sie später gezielt ausgebaut werden können.

### 7.2 Gesamtbild

```
Auslöser
  ├─ Neues YouTube-Video  ── PubSubHubbub-Push ──┐
  ├─ Neue Podcast-Episode ── RSS-Polling/WebSub ─┤
  └─ Briefing-Anfrage     ── Suche (Person) ─────┤
                                                 ▼
                                   Quellen-Connector (quellenspezifisch)
                                   YouTube | Podcast | später: weitere
                                                 │
                                                 ▼
                              „Öffentlicher Auftritt mit Transkript"
                              (gemeinsames internes Modell, quellenunabhängig)
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    ▼                            ▼                            ▼
             Relevanzfilter              KI-Analyse (via LLM-Gateway)     Kommentar-Layer
     (Mindestlänge, Format,          Zusammenfassung · Themen ·        (nur YouTube: Spam-
      Verifikation der Person)       Positionen · Fragen · Sentiment    Filter, Sampling)
                                                 │
                                                 ▼
                                             Ausgabe
                        E-Mail + „Online ansehen"-Seite (Produkt 1)
                        Briefing-Dokument per E-Mail-Link (Produkt 2)
```

Der Kern ist die gemeinsame interne Abstraktionsschicht für **„öffentlicher Auftritt mit Transkript"**, unabhängig von der Quelle. Alles oberhalb (Beschaffung) ist quellenspezifisch, alles unterhalb (Analyse, Ausgabe) ist quellenunabhängig.

### 7.3 Quellen-Connectoren (quellenspezifisch)

**YouTube**
- Metadaten, Suche, Kanal-Feeds: YouTube Data API (API-Key).
- Neue Uploads: PubSubHubbub-Abonnement auf den Kanal-Feed, Callback-URL bei uns, Signaturprüfung des Webhooks.
- Transkripte: siehe 7.4.
- Kommentare: `commentThreads.list` mit API-Key, kein OAuth-Blocker, auch vor Vertragsabschluss für Demos nutzbar.

**Podcast**
- Es gibt kein einheitliches API-Ökosystem wie bei YouTube. Zugriff über die offenen RSS-Feeds der Shows: Episoden-Metadaten und die Audio-Datei selbst.
- Auffinden von Shows und Episoden (für Briefings): offene Verzeichnisse wie Podcast Index, alternativ Anbieter wie Taddy oder Podchaser, die bereits durchsuchbare Transkripte über API anbieten — das kann die eigene Transkription für viele Episoden ersparen.
- Transkript: Audio herunterladen und transkribieren (Whisper), sofern nicht schon ein Transkript im Feed (`podcast:transcript`-Tag) oder beim Anbieter vorliegt.

**Erweiterbarkeit**
- Die Quellen-Schicht ist so gebaut, dass neue Quellen (z. B. später Apple Podcasts direkt, X/Twitter Spaces) sich als weiterer Connector ergänzen lassen, ohne die restliche Pipeline anzufassen. Ein Connector liefert immer dasselbe Ergebnis: Metadaten + Audio-/Transkript-Zugang für einen Auftritt.

### 7.4 Transkript-Layer

Bewusst hinter einem Interface abstrahiert, mit mehreren Implementierungen — welche greift, hängt von Quelle und Vertragslage ab:

1. **Offizieller Weg (Produktion, Produkt 1):** der `captions.download`-Endpunkt der YouTube Data API. Der funktioniert **nur mit einer OAuth-2.0-Freigabe durch den Kanalinhaber** — für fremde Videos ohne diese Freigabe gibt der offizielle Weg einen Fehler zurück. Das passt zum Geschäftsmodell: Der Creator ist unser Vertragspartner und erteilt diese Freigabe im Onboarding.
2. **Inoffizieller Weg (Demo, Anfangsphase, fremde Videos):** die Python-Bibliothek `youtube-transcript-api` — kostenlos, kein API-Key nötig, funktioniert für Videos mit vorhandenen (auch automatisch generierten) Untertiteln. Wichtiger Vorbehalt: inoffiziell, kann ohne Vorwarnung brechen, daher nur als Fallback/Demo-Lösung gedacht, nicht als Produktionsfundament.
3. **Speech-to-Text (Podcasts, Videos ohne Untertitel):** Whisper — als API-Dienst oder selbst gehostet (z. B. `faster-whisper`). Kostet Rechenzeit, liefert dafür quellenunabhängig ein Transkript. Für Podcasts ist das der Standardweg.

**Stufenplan für Produkt 2 — vom schnellen Start zur vollständigen Offizialität.** Briefings verarbeiten Auftritte von Personen, die nicht unsere Vertragspartner sind. Das ist kein Blocker, sondern eine Reihenfolge:

1. **Podcasts sind von Anfang an sauber:** öffentliche RSS-Feeds, öffentliche Audio-Dateien, eigene Transkription. Bei Interviewgästen ist der Podcast-Anteil ohnehin hoch — damit sind Briefings vom ersten Tag an wertvoll.
2. **YouTube-Auftritte kommen in der Startphase über Untertitel** (inoffizielle Bibliothek). Kein Audio-Download von YouTube — das wäre gegen die Nutzungsbedingungen, und wir brauchen es nicht.
3. **Partnerkanäle liefern offiziell:** Jeder Creator, der Produkt 1 nutzt und der Verwendung zugestimmt hat, bringt seinen Backkatalog offiziell (OAuth) in den Bestand. Interviewgäste treten überproportional oft in genau solchen Formaten auf. Je mehr Partner, desto größer der offizielle Anteil.
4. **Verifiziertes Profil (kreative Ergänzung):** Die Zielperson eines Briefings selbst kann ihren Kanal kostenlos verbinden. Ihr Vorteil: Briefings über sie sind vollständig und korrekt, und sie sieht, welche Positionen ihr zugeschrieben werden. Unser Vorteil: offizieller Zugang und ein weiterer Einstieg ins Netzwerk.

Das Transkript-Interface macht diese Stufen zu einer Konfigurationsfrage: Pro Auftritt wird die beste verfügbare Herkunft gewählt und mitgespeichert. Was rechtlich noch abzuklären bleibt, steht in Abschnitt 9; es hält uns nicht vom Bauen ab.

### 7.5 Analyse-Layer (KI)

Gemeinsame Pipeline ab dem Transkript, quellenunabhängig:
- **Relevanzfilterung:** Mindestlänge, Format (Interview/Monolog/Shorts), inhaltliche Verifikation der Zielperson bei Briefings (spricht die Person tatsächlich, oder wird nur über sie geredet?).
- **KI-Zusammenfassung / Themenextraktion / Sentiment-Analyse** — verschiedene Prompts auf derselben Grundlage.
- **Ausgabe-Struktur** wird als strukturierte Daten erzeugt (Abschnitte, Belegstellen mit Zeitstempel), nicht als Fließtext, damit E-Mail, Web-Seite und Briefing-Dokument dieselbe Analyse unterschiedlich rendern können.

Alle LLM-Aufrufe laufen über das Gateway aus Abschnitt 8. Lange Transkripte werden in Abschnitte geteilt und hierarchisch zusammengefasst; das ist Standardtechnik und kein Grund für eine eigene Bibliothek.

### 7.6 Ausgabe-Layer

- **E-Mail-Versand:** über einen Transaktions-E-Mail-Dienst (z. B. Resend oder Postmark) — nicht selbst bauen. Jede Mail mit Abmelde-Link und `List-Unsubscribe`-Header, eigene Absender-Domain mit korrekt eingerichtetem SPF/DKIM/DMARC, sonst landet der Service im Spam und der Creator kündigt.
- **„Online ansehen"-Seiten und Briefings:** server-gerendertes HTML, Token-URL mit mindestens 128 Bit Zufall, Branding des Kanals.
- **Digest-Option** (täglich/wöchentlich statt pro Beitrag) ist ein Phase-2-Feature gegen E-Mail-Müdigkeit bei sehr aktiven Kanälen. Damit das nachrüstbar ist, wird die Zusammenfassung getrennt vom Versand gespeichert: erst erzeugen, dann (sofort oder gebündelt) zustellen.

### 7.7 Datenmodell-Skizze

Nur die Kernbegriffe, damit alle dasselbe meinen. Kein Schema.

- **Creator** — unser Kunde für Produkt 1; hat Branding, Vertrag, eine oder mehrere Quellen.
- **Quelle** — ein YouTube-Kanal oder ein Podcast-Feed; gehört zu einem Creator (Produkt 1) oder wird nur für Briefings beobachtet (Produkt 2).
- **Auftritt** — ein Video oder eine Episode: Metadaten, Quelle, Personen, Dauer, Link. Das zentrale, quellenunabhängige Objekt.
- **Transkript** — gehört zu einem Auftritt; Herkunft (offiziell/inoffiziell/Whisper) wird mitgespeichert, weil sie rechtlich relevant ist.
- **Analyse** — Zusammenfassung, Themen, Sentiment; strukturiert, versioniert nach Prompt/Modell.
- **Abonnent** — eine E-Mail-Adresse mit Double-Opt-in-Status; kann mehrere Creator abonnieren (Vorbereitung für das zentrale Dashboard und spätere echte User-Accounts, damit z. B. ein Diskussionsbereich sich nachrüsten lässt, ohne alles umzubauen).
- **Zustellung** — welche Analyse wann an welchen Abonnenten ging, mit Status (für Analytics).
- **Briefing** — Anfrage eines Interviewers: Person, Zeitraum, bestätigte Auftritte, Ergebnis, Bezahlstatus.

Rohvideos/-audios werden nicht dauerhaft gespeichert (unnötige Kosten und Datenschutz-Risiko); nur Transkripte, Analysen und Metadaten.

### 7.8 Stack-Empfehlung

Eine Empfehlung, keine Festlegung — aber jede Abweichung sollte einen Grund haben.

| Baustein | Empfehlung | Warum |
|---|---|---|
| Sprache | Python 3.12+, Paketverwaltung mit **uv** | Bestes Ökosystem für LLM-/Datenverarbeitung, `youtube-transcript-api`, Whisper-Bindings |
| Web-Framework | FastAPI | Webhooks, wenige Seiten und eine kleine API in einem; async passt zu I/O-lastigen Pipelines |
| Oberfläche | Server-gerendertes HTML (Jinja2), bei Bedarf HTMX | Keine separate Frontend-App im MVP; die Oberfläche ist klein |
| Datenbank | PostgreSQL | Eine Datenbank für alles; später `pgvector` für den Chat-Assistenten statt einer separaten Vektordatenbank |
| Hintergrundjobs | Job-Queue auf Postgres-Basis; Redis erst bei Bedarf | Transkription und Analyse laufen asynchron; ein zusätzlicher Dienst weniger |
| LLM | Anthropic-Modelle als Start, hinter **Bifrost** als Gateway | Siehe Abschnitt 8 |
| Speech-to-Text | Whisper (API oder `faster-whisper` selbst gehostet) | Standard, mehrsprachig, günstig |
| E-Mail | Resend oder Postmark | Transaktions-Mail mit Zustellbarkeit, Webhooks für Öffnungs-/Klickraten |
| Zahlungen (ab Phase 2) | Stripe | Checkout für Briefings, Billing für Abos |
| Hosting | Ein VPS oder eine PaaS mit Docker Compose; eine Umgebung | Reicht für Jahre; Skalierung ist ein Phase-3-Thema |
| Beobachtbarkeit | Strukturierte Logs, Fehler-Tracking (z. B. Sentry) | Genug, um nachts zu schlafen |

### 7.9 Betrieb, Kontingente, Sicherheit

- **YouTube-Kontingent:** Die YouTube Data API selbst ist kostenlos, hat aber ein Tageskontingent von standardmäßig 10.000 Einheiten pro Google-Cloud-Projekt; die meisten Lese-Operationen (Videoliste, Kommentare) kosten nur 1 Einheit. Für den MVP-Maßstab unkritisch. Achtung: Die **Suche** (`search.list`, relevant für Briefings) kostet 100 Einheiten pro Aufruf — Briefings müssen sparsam suchen und Ergebnisse cachen.
- **Idempotenz:** PubSubHubbub liefert Benachrichtigungen mitunter mehrfach; jeder Auftritt wird genau einmal verarbeitet und genau einmal versendet.
- **Sicherheit:** Webhook-Signaturen prüfen, OAuth-Tokens verschlüsselt speichern, Token-URLs unerratbar, Rate-Limits auf Sign-up und Briefing-Suche, keine Rohdaten länger als nötig.
- **Kostenkontrolle:** Pro Creator und pro Briefing werden LLM-Kosten mitgeschrieben; ein Kostendeckel pro Tag verhindert Überraschungen durch Endlosschleifen oder Missbrauch.
- **Nachträglich gelöschte oder privat gestellte Beiträge:** Der Auftritt wird markiert, die „Online ansehen"-Seite deaktiviert; bereits versendete Mails lassen sich nicht zurückholen — das gehört in den Partnervertrag.

---

## 8. KI-Fundament

- **Start mit einem bezahlten Standardmodell** (Anthropic SDK / Claude). Einfachster Einstieg, gute Doku, passt zum Team-Know-how. Bezahlte Modelle über eine API sind am Anfang bewusst die richtige Wahl: kein Betrieb eigener Modelle, keine GPU, sofort gute Qualität — wir wollen schnell entwickeln, schnell Erfahrung sammeln und schnell erste Erfolge sehen. Eigene oder Open-Source-Modelle lohnen sich erst, wenn Volumen oder Datenschutzanforderungen es verlangen.
- **Aber: bewusst kein Lock-in.** Mittelfristig soll es leicht möglich sein, auch andere — insbesondere Open-Source — Modelle einzusetzen, sei es aus Kosten-, Datenschutz- oder Qualitätsgründen für einzelne Aufgaben. Die Architektur ist daher von Anfang an so gebaut, dass der LLM-Anbieter **austauschbar (Plug-and-Play)** bleibt, ohne den Anwendungscode anzufassen. Dafür eine Gateway-/Abstraktionsschicht dazwischenschalten statt direkt gegen den Anbieter-Client zu programmieren.
- **Vorschlag: Bifrost** (Open-Source-Alternative zu LiteLLM) als LLM-Gateway. Im MVP wird dort trotzdem nur ein einziger Provider konfiguriert — der Zusatzaufwand ist gering, der Nutzen (späterer Wechsel oder Ergänzung um Open-Source-Modelle, z. B. günstigeres/lokales Modell für einfache Zusammenfassungen, potenteres für komplexere Briefings) ist dann nur eine Konfigurationsänderung statt Code-Umbau.
- **Wichtig für die Kollegen:** nicht am Anfang schon Multi-Provider-Logik selbst bauen. Bifrost übernimmt das Routing, die Anwendung spricht nur mit Bifrost.
- **Prompts sind Produkt.** Zusammenfassungs- und Briefing-Prompts werden versioniert und mit einem kleinen, festen Satz Beispiel-Transkripte regelmäßig gegengeprüft (stimmt der Ton, werden Aussagen verzerrt, fehlen Belegstellen). Das ist die günstigste Qualitätssicherung, die es gibt, und sie schützt vor dem größten Reputationsrisiko (Abschnitt 9).
- **Mehrsprachigkeit** ist mit LLMs kein Architekturthema, sondern ein Prompt-Parameter — die Zusammenfassung kann in der Sprache des Fans erzeugt werden, sobald wir sie kennen.

---

## 9. Rechtliches & Datenschutz — muss vor echtem Launch geklärt sein

**Für Produkt 1**
- **DSGVO:** Double-Opt-in für die E-Mail-Liste ist Pflicht. Es muss geklärt werden, ob wir als Auftragsverarbeiter für den Creator auftreten oder gemeinsam mit ihm verantwortlich sind — das bestimmt, welche Verträge (AVV) nötig sind. Klares Lösch-/Auskunftskonzept für Fan-Daten; Abmeldung mit einem Klick.
- **Haftung bei fehlerhaften KI-Zusammenfassungen:** Besonders relevant bei Politik-/Gesellschaftsthemen — was, wenn die KI eine Aussage verzerrt zusammenfasst? Muss vertraglich mit dem Partner abgesichert werden (z. B. Hinweis „automatisch generiert, kein Ersatz fürs Originalvideo" in jeder Ausgabe, Freigabe-Option für den Creator vor Versand als spätere Funktion).
- **Nutzungsrechte:** Wir verarbeiten fremden Content (Video-Inhalt, ggf. Stimme, Kommentare der Community) zu einem eigenen Produkt — muss über den Partnervertrag klar geregelt sein, nicht nur implizit über die OAuth-Freigabe. Dazu gehört ausdrücklich, ob Transkripte des Partners auch für Briefings (Produkt 2) verwendet werden dürfen.

**Zusätzlich für Produkt 2**
- **Text- und Data-Mining fremder Inhalte:** Briefings werten öffentlich zugängliche Aufnahmen Dritter aus. In der EU gibt es dafür eine Schranke für Text- und Data-Mining, mit Vorbehalt eines Nutzungsvorbehalts des Rechteinhabers. Ob und wie weit sie unser Vorgehen trägt (interne Rechercheunterstützung, keine Veröffentlichung der Transkripte), ist anwaltlich zu prüfen, bevor Briefings verkauft werden.
- **Personenbezogene Daten der Zielperson:** Ein Briefing ist eine Zusammenstellung dessen, was eine Person öffentlich gesagt hat. Rechtsgrundlage (berechtigtes Interesse, journalistische Zwecke), Speicherdauer und Auskunftsrechte der Zielperson müssen definiert sein. Briefings nur über Personen des öffentlichen Lebens und öffentliche Auftritte — keine privaten Personen.
- **YouTube-Nutzungsbedingungen:** Mit der offiziellen API und OAuth-Freigabe ist der Zugriff vollständig im Rahmen. Für die Startphase mit inoffiziellem Untertitel-Zugriff gilt der Stufenplan aus Abschnitt 7.4; Audio-Download von YouTube findet nicht statt.

---

## 10. Roadmap & Meilensteine

Jede Phase hat ein klares Ziel und ein Kriterium, ab dem die nächste Phase beginnt. Es wird nicht vorgebaut.

**Phase 0 — Prototyp/Demo (kein Vertrag mit einem Kanal nötig)**
Ein beliebiger Kanal, 10–20 Videos, Transkripte über `youtube-transcript-api`, Sentiment über die Kommentar-API mit reinem API-Key, ein Podcast-Feed mit Whisper-Transkription. Kein Login, keine Bezahlung — eine klickbare Demo (Beispiel-Mails, „Online ansehen"-Seiten) und **ein Demo-Briefing über den Creator, den wir als Ersten gewinnen wollen.**
*Fertig, wenn:* Wir können in einem 15-Minuten-Gespräch beide Produkte zeigen, ohne etwas zu erklären, was nicht läuft.

**Phase 1 — MVP mit echtem ersten Partner**
Ein Creator mit Vertrag inkl. OAuth-Freigabe (bzw. Podcast-Feed). Offizielle Data API für Transkripte, sobald die Freigabe da ist — bis dahin läuft der inoffizielle Weg weiter. Echte Double-Opt-in-Liste, Sign-up-Seite im Branding, Zusammenfassung + Sentiment live im Betrieb, rabattierter Pilotpreis, Rechnung per Hand.
*Fertig, wenn:* Die Kriterien aus Abschnitt 6.3 erfüllt sind.

**Phase 2 — Mehrere Creator, zentrale Plattform, Briefing als Produkt**
Mandantenfähigkeit (Branding pro Kanal auf einer gemeinsamen technischen Basis, Self-Service-Onboarding), Preismodell final ausgearbeitet und automatisiert abgerechnet, Magic-Link-Login und zentrales Fan-Dashboard, erstes Analytics-Dashboard für die Creator (Öffnungsraten, Klickraten), Digest-Option. **Produkt 2 geht als Self-Service live:** Person eingeben, Auftritte bestätigen, bezahlen, Briefing erhalten.
*Fertig, wenn:* Mindestens eine Handvoll zahlender Creator und regelmäßig verkaufte Briefings, ohne dass wir pro Kunde Hand anlegen müssen.

**Phase 3 — Erweiterte Features**
Chat-Assistent (RAG-basiert, siehe Zukunftsliste), ggf. Diskussionsbereich, mehrsprachige Zusammenfassungen als Standard, weitere Quellen-Connectoren (Apple Podcasts direkt, X/Twitter Spaces), Team-Zugänge für Redaktionen.

**Strategische Alternative — Reihenfolge tauschen.** Weil beide Produkte auf demselben Kern stehen, kann Produkt 2 vor Produkt 1 an den Markt gehen, falls die Gewinnung des ersten Pilot-Creators länger dauert als gedacht: Ein Briefing braucht keinen Vertragspartner, kein Onboarding und keine wachsende Liste, sondern nur eine Bezahlseite. Das Kriterium für den Tausch: Nach Phase 0 ist innerhalb eines definierten Zeitraums kein Pilot-Creator unterschrieben, aber die rechtliche Prüfung für Briefings ist positiv. Die Pipeline wird in beiden Fällen identisch gebaut; nur die erste Oberfläche unterscheidet sich.

**Arbeitsweise in allen Phasen: kleine Schritte, schnelle Erfolge.** Jede Woche geht etwas Vorzeigbares raus — eine bessere Zusammenfassung, eine neue Seite, ein neuer Connector. Erfahrung aus echtem Betrieb schlägt jede Planung: Die ersten zehn versendeten Zusammenfassungen sagen mehr über den richtigen Prompt als ein Monat Konzeption. Erfolgsmeldungen (erste Liste über 100 Fans, erstes verkauftes Briefing, erste Weiterempfehlung) werden bewusst als Meilensteine gefeiert und in der Verkaufsseite sichtbar gemacht.

**Leitplanke für die Umsetzung:** Bei jeder Phase gilt — nur so viel Komplexität einbauen, wie für die aktuelle Phase nötig ist. Die Architektur (das Quellen-/Transkript-Interface, die Bifrost-Gateway-Schicht, die Trennung von Erzeugen und Zustellen) so anlegen, dass spätere Phasen sich einfügen lassen, aber nichts davon vorab implementieren, was noch nicht gebraucht wird.

---

## 11. Risiken & Gegenmaßnahmen

| Risiko | Warum es real ist | Gegenmaßnahme |
|---|---|---|
| Kein erster Creator ohne Referenz | Klassisches Henne-Ei-Problem | Demo-Briefing über den Zielkunden als Türöffner, rabattierter Pilot, Ansprache über das Team des Creators statt über ihn selbst |
| Inoffizielle Transkript-Bibliothek bricht | Ist bereits mehrfach passiert | Nur für Demo/Produkt 2-YouTube-Anteil; Produktion auf OAuth + Whisper; Interface erlaubt Austausch ohne Umbau |
| Verzerrte Zusammenfassung schadet dem Creator | Politik-/Gesellschaftsthemen sind empfindlich | Prompt-Tests mit festen Beispielen, Belegstellen, sichtbarer Hinweis, später Freigabe-Option, vertragliche Regelung |
| E-Mails landen im Spam | Tötet das Produkt lautlos | Eigene Domain, SPF/DKIM/DMARC, seriöser Versanddienst, Abmelde-Link, Digest gegen Müdigkeit |
| LLM-Kosten laufen davon | Vor allem bei späteren interaktiven Features | Kosten pro Kunde mitschreiben, Tagesdeckel, Caching, Modellwahl über das Gateway |
| Rechtsfragen bei Briefings | TDM-Schranke, Persönlichkeitsrechte | Stufenplan aus 7.4 (Podcasts, Partnerkanäle, verifizierte Profile); anwaltliche Prüfung parallel zum Bauen; nur Personen des öffentlichen Lebens |
| Großer Player baut es nach | Technik ist reproduzierbar | Vertrauensbeziehung zu Creatorn, aufgebauter Transkript-/Analysebestand, Geschwindigkeit |
| Zu viel gebaut, zu wenig verkauft | Der Standardfehler | Phasenkriterien einhalten; keine Phase-2-Features vor Phase-1-Umsatz |

---

## 12. Zukunftsliste (nach dem MVP)

### Persönlicher Chat-Assistent über den Backkatalog
**Explizit auf die Zukunftsliste verschoben — nicht Teil des MVP.** Grund: Das ist kein einfaches Zusatzfeature, sondern eine eigene technische Baustelle:
- Braucht einen durchsuchbaren Index (Embeddings/Vektordatenbank, im Stack: `pgvector`) über den gesamten Backkatalog eines Kanals, nicht nur das letzte Video.
- Kosten skalieren nicht linear wie bei der E-Mail-Zusammenfassung: Ein Video wird einmal zusammengefasst, aber ein Chat-Assistent kann theoretisch von tausenden Fans mit individuellen Fragen angefragt werden → braucht Caching / Wiederverwendung häufiger Antworten, sonst explodieren die LLM-Kosten.
- Grobes späteres Konzept: RAG-Pipeline (Retrieval-Augmented Generation) über die gesammelten Transkripte, Antworten idealerweise mit Zeitstempel-Verweis ins Originalvideo. Der Transkript-Bestand, den Produkt 1 und 2 ohnehin aufbauen, ist die Grundlage dafür.

### Diskussionsbereich (kuratiert, ruhiger als YouTube-Kommentare)
- Bleibt vorerst optional / im Hinterkopf. Beim Datenmodell aber schon mitgedacht (Abonnent als eigenes Objekt, nicht nur E-Mail, später ggf. echte User-Accounts), damit es sich nachrüsten lässt, ohne alles umzubauen.

### Weitere Ideen für spätere Ausbaustufen
- Analytics-Dashboard für den Creator (Öffnungsraten, Klickraten, meistgestellte Fragen) — wichtig für die eigene Kundenbindung und Preis-Rechtfertigung; erste Stufe bereits in Phase 2.
- Mehrsprachige Zusammenfassungen.
- Personalisierte Lernpfade über mehrere Videos hinweg (bei Bildungscontent).
- Freigabe-Workflow: Der Creator sieht die Zusammenfassung vor dem Versand und kann sie korrigieren.
- **Fragen-Radar für den Creator:** Aus den Kommentaren werden die meistgestellten offenen Fragen extrahiert — als Vorschlag fürs nächste Video. Macht aus dem Sentiment-Feature ein Werkzeug, das Content-Ideen liefert.
- **Sprung-Links:** Jede Aussage in Zusammenfassung und Briefing verlinkt auf den Zeitstempel im Original. Klein, aber der Grund, warum Fans die Mail öffnen.
- **Monatsrückblick:** Eine Mail pro Monat mit den wichtigsten Themen, Zitaten und der Stimmungsentwicklung des Kanals — auch ein Anlass, die Liste zu teilen.
- **Teilbare Zitat-Karten:** Das beste Zitat eines Beitrags als Bild, das der Fan mit einem Klick teilt und das auf die Sign-up-Seite verweist.
- **Verifiziertes Profil für Interviewgäste:** Siehe 7.4 — die Zielperson verbindet ihren Kanal selbst und bekommt dafür Einblick, wie sie öffentlich wahrgenommen wird.
- Briefing-Abos: laufende Beobachtung einer Person („sag mir Bescheid, wenn X etwas Neues zu Thema Y sagt").
- Weitere Quellen als Connector: Apple Podcasts direkt, X/Twitter Spaces, Konferenz-Aufzeichnungen.

---

## 13. Offene Fragen

Siehe separates Dokument: `offene-fragen-youtuber-plattform.md`. Es enthält auch die neuen Fragen, die durch Produkt 2 und die Podcast-Quelle hinzugekommen sind.
