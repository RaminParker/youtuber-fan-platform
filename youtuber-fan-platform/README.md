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
| `RESEND_API_KEY` | E-Mail-Versand | keine Mails |
| `YOUTUBE_API_KEY` | Metadaten, Kommentare | nur der öffentliche Feed funktioniert |
| `GOOGLE_OAUTH_CLIENT_*` | offizielle Untertitel | nur der inoffizielle Anbieter |

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

**M0 bis M4** stehen: von „neues Video erkannt" bis „fertige Mail in drei
Varianten". Es fehlen **M5 bis M9** — an Fans verschickt wird also noch nichts.
Drei Bausteine warten auf ihren Aufrufer: `POST /k/{slug}` (M5), `send_batch`
und die Webhook-Signaturprüfung (M6). Fortschritt je Meilenstein in §17 des
Plans.

Sprache: Code, Kommentare und Logs auf Englisch; diese Datei und alles, was Fans
und Creator sehen, auf Deutsch.
