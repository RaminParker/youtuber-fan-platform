# Creator-Plattform (Arbeitsname: Klartext)

Eine Plattform, die öffentlich gesprochene Inhalte (zuerst YouTube-Videos, später Podcast-Episoden) automatisch transkribiert, mit KI zusammenfasst und den Fans eines Creators einige Tage nach jedem neuen Beitrag per E-Mail zustellt, ergänzt um ein Stimmungsbild der Kommentare. Der Creator zahlt, gestaffelt nach Listengröße; Fans zahlen nie.

Das vollständige Konzept steht im Manifest. Es ist die Spezifikation: Was dort nicht steht, wird nicht gebaut.

## Wo liegt was

| Pfad | Inhalt |
|---|---|
| `docs/manifest/creator-plattform-manifest.md` | Das Manifest: Vision, Produkte, Geschäftsmodell, MVP, Architektur, Roadmap, Entscheidungen. |
| `docs/manifest/offene-fragen-youtuber-plattform.md` | Noch nicht entschiedene Fragen. Beantwortete Fragen wandern ins Entscheidungsprotokoll des Manifests. |
| `docs/plans/` | Implementierungspläne, je Datei ein Vorhaben, Datum im Namen. Aktuell: `2026-09-mvp-implementation-plan.md`. |
| `docs/ARCHITECTURE.md` | Modulschnitt, Datenmodell, Zustandsautomaten, Entscheidungen, „Wo finde ich was" (entsteht mit Meilenstein M0). |
| `docs/runbooks/` | Betriebsanleitungen: Creator-Onboarding, Deployment, Störungen, Löschungen (entstehen mit M7/M9). |
| `config/settings.toml` | Die eine zentrale Konfigurationsdatei. Geheimnisse kommen ausschließlich aus Umgebungsvariablen (`.env.example`). |
| `config/roadmap.toml` | Inhalt der Feature-Vorschau auf der Verkaufsseite. |
| `src/app/` | Der Anwendungscode: `sources/` (Quellen), `transcripts/`, `analysis/`, `delivery/` (E-Mail), `jobs/` (Pipeline-Schritte), `web/` (Seiten), `worker.py` (Worker-Schleife). |
| `migrations/` | Alembic-Migrationen. |
| `tests/` | Unit- und Integrationstests, Fakes für externe Dienste, Prompt-Beispiele. |

Sprache: Code, Docstrings, Kommentare, Logs und technische Dokumentation sind auf Englisch. Diese README und alle Texte, die Fans und Creator sehen, sind auf Deutsch.

## Stand

Der Implementierungsplan für den MVP ist geschrieben und wartet auf Freigabe. Code gibt es noch nicht. Sobald Meilenstein M0 des Plans umgesetzt ist, steht hier der lokale Start:

```
cp .env.example .env          # Schlüssel eintragen
docker compose up             # Postgres, LLM-Gateway, Web, Worker
uv run alembic upgrade head   # Datenbank anlegen
uv run app --help             # Betriebsbefehle (Onboarding, Backfill, Status)
uv run pytest && uv run ruff check
```

## Arbeitsweise

- Jede Aufgabe wird aus einem Abschnitt des Manifests abgeleitet und ist klein genug für eine Arbeitssitzung.
- Jeder Meilenstein ist deploybar und hat einen Test, der zeigt, dass er funktioniert.
- Vor jeder Umsetzung liegt ein Plan in `docs/plans/`; der Review-Abschnitt des Plans hält fest, was gebaut wurde und was vom Plan abwich.
