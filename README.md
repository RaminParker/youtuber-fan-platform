# Creator-Plattform (Arbeitsname: Klartext)

Fasst neue YouTube-Videos eines Creators automatisch zusammen und schickt sie
einige Tage später per E-Mail an dessen Fans — mit Sprungmarken ins Video und
einem Stimmungsbild der Kommentare.

Das Manifest in `docs/manifest/` ist die Spezifikation. Was dort nicht steht,
wird nicht gebaut.

## Installieren

Voraussetzungen: [uv](https://docs.astral.sh/uv/) und Docker.

```sh
uv sync                          # Python 3.13 und alle Abhängigkeiten
cp .env.example .env             # Schlüssel eintragen, siehe unten
docker compose up -d postgres    # Datenbank und Testdatenbank
uv run alembic upgrade head      # Schema anlegen
```

## Starten

```sh
docker compose up                # Postgres, Web (:8000), Worker, LLM-Gateway
```

Prüfen: <http://localhost:8000/health> antwortet `{"status": "ok"}`.

Einzeln, etwa mit Neuladen bei Codeänderungen:

```sh
uv run uvicorn app.web.server:create_app --factory --reload
uv run python -m app.worker
```

## Testen

```sh
uv run pytest                    # alle Tests
uv run pytest tests/unit         # nur ohne Datenbank, ~0,5 s
uv run pytest -k feed            # nach Namen filtern
uv run ruff check                # Linter
uv run ruff format               # Formatierer
```

Die Integrationstests brauchen das laufende Postgres. Fehlt es, überspringen
sie sich und die Unit-Tests laufen trotzdem.

## Betreiben

```sh
uv run app onboard --slug pilot --name "Kanalname" \
                   --email kontakt@example.org --channel-id UC…
uv run app backfill pilot --count 10   # Backkatalog holen, ohne zu mailen
uv run app poll pilot                  # Feed jetzt lesen
uv run app process pilot <video-id>    # ein einzelnes Video aufnehmen
uv run app demo-mails pilot --count 3  # Mails aller Varianten nach out/
uv run app eval-prompts                # Prompts gegen Beispieltranskripte
uv run app eval-prompts --model anthropic/<modell>   # zum Vergleich zweier Modelle
uv run app gateway-config              # Modelle aus settings.toml in den Gateway schreiben
```

Eine gesperrte Adresse (Bounce, Beschwerde) bekommt nie wieder Mail — die
Sperre spiegelt Resends eigene Sperrliste. Wie der Betreiber eine Adresse
entsperrt, deren Postfach wieder funktioniert, steht in `docs/ARCHITECTURE.md`
unter „The fan area".

Diese Befehle nehmen auf und berichten — Pipeline-Schritte führt nur der
Worker aus. Sie sprechen mit YouTube beziehungsweise dem LLM-Gateway; ohne den
passenden Schlüssel brechen sie mit einer Meldung ab, die sagt, welcher fehlt.

## Schlüssel und ihre Rechte

`.env.example` zeigt alle Variablen, gruppiert danach, wann sie gebraucht
werden; `cp .env.example .env` und ausfüllen. Pflicht zum Start sind nur
`DATABASE_URL` und `SECRET_KEY`. Fehlt ein Schlüssel, den ein Prozess braucht,
steht beim Start ein ERROR `config.secret_missing` im Log; lehnt ein Anbieter
einen Schlüssel ab oder ist ein Kontingent aufgebraucht, schreibt der Worker
bei jedem Versuch `operator.action_needed` — mit Dienst, Meldung des Anbieters
und der Variable, die zu prüfen ist. Kein Video geht dabei verloren.

**Grundregel für jeden statischen Schlüssel:** so wenig Rechte wie möglich, ein
eigener Schlüssel pro Umgebung (lokal, Render), nie im Chat oder im Repo, nach
einem Leck sofort widerrufen.

| Variable | Was ist das | Woher | So einschränken | Ohne sie |
|---|---|---|---|---|
| `YOUTUBE_API_KEY` | Liest öffentliche Videodaten (Titel, Dauer, Kommentare) | Google Cloud Console → APIs & Services → Credentials → API key | *API restrictions*: nur „YouTube Data API v3"; in Produktion zusätzlich auf die Ausgangs-IPs von Render beschränken | nur der öffentliche Feed; kein Video wird verarbeitet |
| `ANTHROPIC_API_KEY` | Schlüssel des LLM-Gateways beim Modellanbieter; die App selbst sieht ihn nie | Anthropic Console → Workspace wählen → API Keys | in einem eigenen Workspace nur für diese App anlegen, dort ein Ausgabenlimit setzen; der Schlüssel **muss** zu einem Workspace gehören | Gateway antwortet „no keys found" |
| `LLM_GATEWAY_KEY` | Gemeinsames Geheimnis zwischen App und Gateway („virtual key") | selbst erzeugen: `openssl rand -hex 32` mit Präfix `sk-bf-` | erlaubt im Gateway nur das eine Modell (`allowed_models` in `config/bifrost.json`); das Gateway ist auf Render nicht öffentlich erreichbar | keine Zusammenfassung |
| `BIFROST_SETUP_TOKEN` | Einmal-Token für die Admin-Oberfläche des Gateways, die wir nie öffnen | selbst erzeugen: `openssl rand -hex 32` | — | Admin-Oberfläche ohne Schutz |
| `RESEND_API_KEY` | Versendet Mails | Resend → API Keys | Berechtigung *Sending access* (nicht *Full access*), in Produktion auf die eigene Domain beschränkt | keine Mails |
| `RESEND_WEBHOOK_SECRET` | Prüft, dass Bounce-Meldungen wirklich von Resend kommen | Resend → Webhooks → Endpoint → Signing secret (`whsec_…`) | ein Secret pro Endpoint | jede Meldung wird mit 401 abgewiesen, Bounces sperren niemanden |
| `SENDER_ADDRESS` | Absender, solange die Domain bei Resend nicht verifiziert ist: `onboarding@resend.dev` | — | — | Absender `post@mail.<domain>`, den Resend ohne Verifizierung ablehnt |
| `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` | Damit ein Creator seinen Kanal verbindet und wir seine offiziellen Untertitel lesen | Google Cloud Console → Credentials → OAuth client ID (Webanwendung) | einzige Redirect-URI `<BASE_URL>/creator/youtube/callback`; einziger Scope `youtube.force-ssl` | nur der inoffizielle Untertitel-Anbieter |
| `TOKEN_ENCRYPTION_KEYS` | Verschlüsselt die gespeicherten OAuth-Tokens der Creator | selbst erzeugen: `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | pro Umgebung verschieden; zum Wechseln den neuen Schlüssel vorne anfügen | kein Kanal lässt sich verbinden |
| `TRANSCRIPT_PROXY_*` | Wohnungs-Proxy für den inoffiziellen Untertitel-Abruf; YouTube sperrt Cloud-IPs | webshare.io, Paket „Residential" | eigener Zugang nur für diese App | auf Render meist keine Untertitel; lokal unnötig |
| `SENTRY_DSN` | Macht aus jedem ERROR eine Benachrichtigung | sentry.io → Projekt → Client Keys (DSN) | ein DSN darf nur Ereignisse senden; persönliche Daten schickt die App ohnehin nicht mit | Fehler stehen nur im Log |

Ohne verifizierte Domain stellt Resend nur an die Adresse des eigenen Kontos
und an seine Testadressen (`delivered@resend.dev`, `bounced@resend.dev`) zu.

Nach einer Änderung an `ANTHROPIC_API_KEY` den Gateway neu erzeugen:
`docker compose up -d --force-recreate bifrost`.

Den Webhook erreicht Resend nur über eine öffentliche Adresse. Lokal ginge das
mit einem Tunnel (`cloudflared tunnel --url http://localhost:8000`) — aber nur
in einem Netz, in dem Tunnel erlaubt sind, und nie von einem Firmenrechner.
Die echte Abnahme des Webhooks findet deshalb auf Render statt (Plan §17, M9).
Ohne Webhook laufen die Tests trotzdem vollständig: Sie signieren ihre
Ereignisse selbst.

### Was die Kostenzahlen wert sind

**Maßgeblich ist die Seite des Anbieters**, nicht unsere Rechnung: Sie zeigt
live, was wirklich ausgegeben wurde — je Modell, je Schlüssel, je Zeitraum, in
Dollar. Die Adresse steht in `config/settings.toml` unter `usage_dashboard`
(heute <https://console.anthropic.com/settings/usage>; bei einem Wechsel zu
OpenAI entsprechend <https://platform.openai.com/usage>) und wird überall
mitgedruckt, wo die App Zahlen nennt: beim Start des Workers, in der Warnung zu
alten Preisen und in `eval-prompts`. Gespiegelt wird diese Seite bewusst nicht
— eine zweite Quelle würde still veralten.

**Diese Zahlen sieht nur der Betreiber.** Sie liegen in der Datenbank, in den
Logs und in Betreiber-Befehlen. Keine Seite und keine Mail zeigt sie: weder
einem Fan noch einem Creator, der sonst erführe, was sein Kanal uns kostet. Ein
Test weist jedes Template zurück, das davon spricht.

Die Zahlen in `llm_calls` sind eine **Schätzung** dieser Seite. Damit man der Schätzung trauen kann, trägt jeder Preis in
`config/settings.toml` seine Herkunft und sein Prüfdatum, und jede gebuchte
Zeile hält fest, mit welchem Preis sie gerechnet wurde — eine Preisänderung
verfälscht also keine alten Zeilen. Bepreist wird das Modell, das tatsächlich
geantwortet hat; kennt die Tabelle es nicht, bucht die Zeile 0 und ist als
`price_source = "unknown"` markiert, dazu ein ERROR im Log. Zwischengespeicherte
Eingaben werden mit ihren eigenen Faktoren gerechnet (Lesen etwa 0,1×,
Schreiben 1,25×). Ist ein Preis älter als drei Monate, sagt der Worker das beim
Start (`llm.prices_stale`).

### Modell wechseln

Drei Schritte, und die Preise ziehen automatisch nach:

1. In `config/settings.toml` `model_summary`/`model_sentiment` ändern und den
   Preis-Eintrag mit Herkunft und Prüfdatum ergänzen (fehlt er, startet die App
   nicht).
2. `uv run app gateway-config` — schreibt dieselben Modellnamen in die
   Gateway-Konfiguration, damit niemand sie doppelt pflegt.
3. `docker compose up -d --force-recreate bifrost`, Worker neu starten.

Alte Preis-Einträge bleiben stehen: Buchungen von vorher wurden mit ihnen
gerechnet und sollen erklärbar bleiben. Vorher vergleichen lohnt sich:
`uv run app eval-prompts --model anthropic/<modell> --out out/eval` rendert
dieselben Beispiel-Transkripte mit beiden Modellen nebeneinander, mit Token und
Kosten.

`.env` ist git-ignoriert. Jede Tabelle aus `config/settings.toml` lässt sich per
Umgebungsvariable mit doppeltem Unterstrich überschreiben, etwa
`LOGGING__JSON=true`.

## Wo liegt was

| Pfad | Inhalt |
|---|---|
| `config/settings.toml` | Alle Stellschrauben, kommentiert |
| `src/app/design.py` | Jede Farbe und Schriftgröße — Seiten und Mails lesen dieselben Werte |
| `.env.example` | Alle Geheimnisse, je eines mit Kommentar |
| `src/app/` | `sources/` → `transcripts/` → `analysis/` → `delivery/`, dazu `jobs/` (Pipeline), `web/`, `worker.py` |
| `tests/` | Unit- und Integrationstests, Fakes in `fakes.py` |
| `docs/manifest/` | Die Spezifikation |
| `docs/plans/` | Implementierungspläne, Fortschritt in §17 |
| `docs/backlog.md` | Alles, was bewusst nach dem MVP kommt — mit dem Auslöser, ab dem es sich lohnt |
| `docs/ARCHITECTURE.md` | Modulschnitt, Entscheidungen, „Wo finde ich was" |
| `implementation-notes.html` | Wo die Umsetzung vom Plan abweicht und warum |

## Stand

**M0 bis M6** stehen: von „neues Video erkannt" über den Fan-Bereich
(Double-Opt-in, strenge Adressprüfung, Abmeldung, Sperre nach Bounce oder
Beschwerde) bis zum Versand. Zwei Stunden vor dem Sendezeitpunkt holt der Worker
das Stimmungsbild, eine Stunde vorher bekommt der Creator die Vorschau mit
„stoppen" und „verschieben", dann geht die Mail genau einmal an alle
bestätigten Fans. Der Durchlauf ist am 19.09.2026 einmal vollständig gegen die
echten Dienste gelaufen: YouTube, Transkript, Zusammenfassung, Stimmungsbild,
Vorschau und Versand an zwei Test-Adressen, genau einmal.
Danach wurde M6 nach einem Code-Review gehärtet (19 Befunde, darunter ein still
verworfener Commit nach einem Datenbankfehler und ein Versand, der trotz
Erfolgs als gescheitert enden konnte).

Es fehlen **M7 bis M9**: Einstellungsseite, Verkaufsseite, Deployment; der echte
Bounce-Webhook wird mit dem Deployment abgenommen (M9). Ebenfalls offen und
bewusst nicht gebaut: **wie das Geld fließt.** Der MVP sieht laut Manifest §4.4
einen Vertrag und eine Rechnung von Hand vor; was ein einzelner Kunde kostet,
lässt sich aus `llm_calls` und `deliveries` ableiten (siehe `docs/backlog.md`).
Fortschritt je Meilenstein in §17 des Plans.

Sprache: Code, Kommentare und Logs auf Englisch; diese Datei und alles, was Fans
und Creator sehen, auf Deutsch.
