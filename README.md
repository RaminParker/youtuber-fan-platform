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
```

Diese Befehle nehmen auf und berichten — Pipeline-Schritte führt nur der
Worker aus. Sie sprechen mit YouTube beziehungsweise dem LLM-Gateway; ohne den
passenden Schlüssel brechen sie mit einer Meldung ab, die sagt, welcher fehlt.

## Schlüssel

Pflicht zum Start sind nur `DATABASE_URL` und `SECRET_KEY`; beide stehen mit
Werten für die lokale Entwicklung in `.env.example`. Die übrigen braucht die
Schicht, die sie benutzt:

| Variable | Wofür | Ohne sie |
|---|---|---|
| `ANTHROPIC_API_KEY` | LLM-Gateway | Gateway läuft, lehnt Anfragen aber mit „no keys found" ab |
| `RESEND_API_KEY` | E-Mail-Versand; lokal genügt ein Key mit „Sending access" | keine Mails |
| `RESEND_WEBHOOK_SECRET` | Signatur der Bounce- und Beschwerde-Meldungen | jede Meldung wird als ungültig verworfen |
| `SENDER_ADDRESS` | Absender, solange die Domain bei Resend nicht verifiziert ist: `onboarding@resend.dev` | Absender `post@mail.<domain>`, den Resend ohne Verifizierung ablehnt |
| `YOUTUBE_API_KEY` | Metadaten, Kommentare | nur der öffentliche Feed funktioniert |
| `GOOGLE_OAUTH_CLIENT_*` | offizielle Untertitel | nur der inoffizielle Anbieter |

Ohne verifizierte Domain stellt Resend nur an die Adresse des eigenen Kontos
und an seine Testadressen (`bounced@resend.dev`, `complained@resend.dev`) zu.
Den Webhook lokal erreichbar machen, ohne Konto:

```sh
cloudflared tunnel --url http://localhost:8000   # druckt eine https-URL
```

In Resend dann einen Webhook auf `<URL>/webhooks/resend` mit den Ereignissen
`email.bounced` und `email.complained` anlegen und dessen Secret als
`RESEND_WEBHOOK_SECRET` eintragen. Die URL ändert sich bei jedem Start.

`.env` ist git-ignoriert. Jede Tabelle aus `config/settings.toml` lässt sich per
Umgebungsvariable mit doppeltem Unterstrich überschreiben, etwa
`LOGGING__JSON=true`.

## Wo liegt was

| Pfad | Inhalt |
|---|---|
| `config/settings.toml` | Alle Stellschrauben, kommentiert |
| `.env.example` | Alle Geheimnisse, je eines mit Kommentar |
| `src/app/` | `sources/` → `transcripts/` → `analysis/` → `delivery/`, dazu `jobs/` (Pipeline), `web/`, `worker.py` |
| `tests/` | Unit- und Integrationstests, Fakes in `fakes.py` |
| `docs/manifest/` | Die Spezifikation |
| `docs/plans/` | Implementierungspläne, Fortschritt in §17 |
| `docs/ARCHITECTURE.md` | Modulschnitt, Entscheidungen, „Wo finde ich was" |
| `implementation-notes.html` | Wo die Umsetzung vom Plan abweicht und warum |

## Stand

**M0 bis M5** stehen: von „neues Video erkannt" bis „fertige Mail in drei
Varianten", dazu der Fan-Bereich — Anmeldung mit Double-Opt-in, Abmeldung und
die Sperre nach Bounce oder Beschwerde. Es fehlen **M6 bis M9**: Zusammenfassungen
gehen noch an niemanden, nur Bestätigungsmails. `send_batch` wartet auf seinen
Aufrufer (M6). Fortschritt je Meilenstein in §17 des Plans.

Sprache: Code, Kommentare und Logs auf Englisch; diese Datei und alles, was Fans
und Creator sehen, auf Deutsch.
