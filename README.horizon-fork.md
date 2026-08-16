# Dieser Fork: Horizon als tägliches KI-Briefing per E-Mail

Kurzreferenz für diesen Fork von [Thysrael/Horizon](https://github.com/Thysrael/Horizon).
Für die allgemeine Projekt-Doku siehe [README.md](README.md) und
[docs/configuration.md](docs/configuration.md).

## Was hier eingerichtet ist

- **KI-Provider:** Google Gemini 2.5 Flash (kostenlos, kein Claude-/OpenAI-Key).
- **Quellen:** 7 YouTube-Kanäle (als RSS), OpenAI News RSS, Google DeepMind Blog RSS,
  und ein selbstgebauter Anthropic-News-Scraper (Anthropic hat keinen RSS-Feed).
- **Sprache:** Deutsch (`ai.languages: ["de"]`).
- **Versand:** E-Mail via Gmail-SMTP, ein fester Empfänger, kein Subscribe/Unsubscribe.
- **Zeitplan:** täglich per GitHub Actions Cron.

## Vor dem ersten scharfen Lauf: GitHub Secrets eintragen

Unter **Settings → Secrets and variables → Actions** im Repo `Dallwyn/Horizon`
müssen drei Secrets angelegt werden. Ich kann sie nicht selbst eintragen.

| Secret | Zweck | Woher |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini-API-Zugang | Kostenlos erzeugen unter [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `EMAIL_PASSWORD` | SMTP-Login für das Absender-Postfach `kherank@googlemail.com` | Gmail-**App-Passwort** (nicht das normale Passwort!) unter [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) — dafür muss 2FA auf dem Google-Konto aktiv sein |
| `EMAIL_RECIPIENT` | Empfängeradresse der Briefing-Mail | `micjoachim@yahoo.fr` |

`EMAIL_RECIPIENT` ist absichtlich ein Secret und keine feste Datei im Repo: Das Repo
ist öffentlich, und `data/subscribers.json` (wo Horizon normalerweise Empfänger
erwartet) ist projektweit `.gitignore`d. Ein Workflow-Schritt schreibt die Datei bei
jedem Lauf frisch aus dem Secret, damit die Adresse nie in der Git-Historie landet.

Sobald alle drei Secrets gesetzt sind, kann der Workflow **Daily Horizon Summary**
manuell über **Actions → Daily Horizon Summary → Run workflow** ausgelöst werden.
Das schickt eine echte Mail an `micjoachim@yahoo.fr` — vorher bitte kurz Bescheid
geben, dann triggere ich das oder du machst es selbst.

## Quellen ändern

Alles in [`data/config.github.json`](data/config.github.json) unter `sources`.

- **YouTube-Kanal hinzufügen:** neuer Eintrag unter `sources.rss` mit
  `"url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC..."`. Die
  Channel-ID vorher wirklich verifizieren (RSS-Feed abrufen, `<title>` gegen den
  erwarteten Kanalnamen prüfen) — Namens-Handles sind nicht eindeutig, siehe die
  Y-Combinator/AI-Impact-Recherche in diesem Setup als Beispiel, wo Namensvettern
  existierten.
- **Beliebigen anderen RSS/Atom-Feed hinzufügen:** gleiches Muster, `content_extractor:
  "full-text"` nur setzen, wenn es eine echte Artikelseite ist (bei YouTube-Links
  bringt das nichts, da die Seite clientseitig gerendert wird).
- **Anthropic-Quelle deaktivieren:** `sources.anthropic.enabled: false`.

### Zu wenig (oder zu viel) kommt durch

Zwei unabhängige Stellschrauben in `data/config.github.json`, beide unter
`processing.profile_settings`:

- **`tech-news.threshold` (aktuell 7.0):** gilt für OpenAI/DeepMind/Anthropic.
  Bewusst hoch, weil die Rubrik in `profiles/tech-news/analysis.md` nach
  "bahnbrechend/wichtige Ankündigung" fragt — für echte Firmen-Announcements
  angemessen.
- **`tech-blog.threshold` (aktuell 4.5):** gilt für alle 6 YouTube-Kanäle. Die
  Rubrik in `profiles/tech-blog/analysis.md` fragt stattdessen "lohnt sich das
  gründliche Lesen/Ansehen, bringt es mir übertragbares Wissen" — deutlich
  passender für Tutorial-/Praxis-Content als der "bahnbrechend"-Maßstab von
  tech-news, unter dem die YouTube-Kanäle anfangs kaum etwas durchließen.

Threshold-Werte: `0`–`10`, oder `null` für "kein Filter" (dann kommt alles
durch, was thematisch passt — kann an ruhigen Tagen sehr viel Rauschen sein).
Ein Blick in die jeweilige `analysis.md`-Rubrik hilft einzuschätzen, welcher
Wert realistisch ist, bevor man an der Zahl dreht.

Aktuell konfigurierte Kanal-IDs (verifiziert per RSS-Feed-Titel-Abgleich):

| Kanal | Channel-ID |
|---|---|
| Julian Ivanov \| KI-Automatisierung | `UCdoTbckiMelGtWvGMfhlkgQ` |
| Everlast AI | `UC8T5gQ4U4GbI2h8kYCkEcvg` |
| Y Combinator | `UCcefcZRL2oaA_uBNeo5UOWg` |
| Nate Herk \| AI Automation | `UC2ojq-nuP8ceeHqiroeKhBA` |
| AI Impact | `UCnNA2EuEVybpo3WGEace4HQ` |
| Christoph Magnussen | `UCDx6L69jmKBJbNu5GnkCilg` |
| Leonard Schmedding | `UCiKCgeGNFCoLF086q-Bl-HA` |

## Modell wechseln

`data/config.github.json` → `ai.model`. Der Feldwert wird ungeprüft an die
Gemini-API durchgereicht (kein Allowlist im Code), also funktioniert z. B.
`"gemini-3.7-flash-lite"` oder ein späteres Modell direkt. `ai.provider` nur
ändern, wenn auch ein anderer Provider-Key als Secret hinterlegt wird.

**Das ist bereits einmal live passiert:** Der ursprünglich konfigurierte
`gemini-2.5-flash` wurde von Google zwischen Einrichtung und erstem Testlauf
für neue API-Keys abgeschaltet ("This model ... is no longer available to new
users", HTTP 404). Aktuell steht `gemini-3.7-flash`. Google pflegt Modelle nur
befristet — wenn eine ganze Mail plötzlich wieder leer ankommt (siehe nächster
Abschnitt), im Actions-Log nach `404` und `no longer available` suchen und den
aktuellen Modellnamen unter [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
nachschlagen. Bewusst *kein* `-latest`-Alias verwendet: Google gibt dafür nur
eine 2-Wochen-Vorlaufzeit per E-Mail vor Breaking Changes, was für einen
unbeaufsichtigten täglichen Lauf zu knapp ist — ein fester, stabiler Modellname
ist vorhersehbarer, auch wenn er irgendwann manuell nachgezogen werden muss.

## Uhrzeit ändern

`.github/workflows/daily-summary.yml` → das `cron`-Feld (UTC!). Aktuell `0 5 * * *`
= 07:00 Berlin während Sommerzeit (CEST). GitHub-Actions-Cron kennt keine
Zeitzonen und folgt der Sommer-/Winterzeit-Umstellung nicht automatisch:

- **Sommer (CEST, UTC+2, bis Ende Oktober):** `0 5 * * *` → 07:00 Berlin ✓
- **Winter (CET, UTC+1, ab Ende Oktober):** `0 5 * * *` → 06:00 Berlin (eine
  Stunde zu früh). Für exakt 07:00 im Winter müsstest du dann manuell auf
  `0 6 * * *` umstellen (was im darauffolgenden Sommer wiederum 08:00 ergibt).

GitHub Actions Cron ist zusätzlich "best effort" und kann unter Last einige
Minuten später als geplant starten.

Davon unabhängig ist die **Datumsbeschriftung** der Mail: `report_timezone` in
[`data/config.github.json`](data/config.github.json) steht auf `Europe/Berlin`.
Damit richtet sich das Datum in Betreff, Überschrift und Dateiname nach der
Berliner Kalenderwoche statt nach UTC. Ohne diese Einstellung (Default `UTC`)
würde ein Lauf, der nach 00:00 Berliner Zeit aber vor 00:00 UTC startet, noch
unter dem Vortag abgelegt. Das Abholfenster (`time_window_hours`) bleibt
unabhängig davon UTC-basiert.

## Erkennen, wenn das kostenlose Kontingent aufgebraucht ist

Zwei Signale:

1. **Im Actions-Log** (Run → Job → "Run Horizon"-Schritt): nach `429`, `quota`,
   `RESOURCE_EXHAUSTED` oder `rate limit` suchen.
2. **In der Mail selbst:** Horizon bricht den Lauf bei einem reinen KI-Kontingent-
   Ausfall nicht ab. Wenn an einem Tag *alle* Items wegen Kontingent-Fehlern nicht
   bewertet werden konnten, kommt trotzdem eine Mail — nur mit dem Hinweis "keine
   Beiträge haben die Relevanzschwelle erreicht" statt echten Inhalten. Bleibt
   dieser leere Zustand mehrere Tage hintereinander bestehen, ist das ein starkes
   Indiz für ein ausgeschöpftes Kontingent.

Ein Totalausfall *aller* Quellen (z. B. Netzwerkproblem) würde dagegen den Lauf
abbrechen und keine Mail verschicken — das steht dann eindeutig im Actions-Log als
fehlgeschlagener Workflow-Run.

## Rate-Limits: reicht das kostenlose Kontingent?

Google veröffentlicht seit 2026 keine feste RPD-Tabelle mehr im offiziellen
Docs-Text (die Seite verweist stattdessen auf das persönliche Kontingent in
AI Studio: [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit)).
Dritt-Quellen nennen für Gemini 2.5 Flash im kostenlosen Tier Werte zwischen
250 und 1.500 Requests/Tag — ich kann das nicht auf eine verlässliche, aktuelle
Zahl festnageln und will hier nichts behaupten, was ich nicht verifizieren konnte.
Bitte nach dem ersten echten Lauf selbst unter dem obigen Link nachsehen.

Was ich aus der eigenen Konfiguration sicher sagen kann: Ein einzelner Lauf über
9 Quellen mit 24h-Fenster erzeugt üblicherweise 10–20 Items, von denen bei
Schwelle 7.0 grob 2–8 die Anreicherung durchlaufen (~1 Analyse-Call je Item plus
~4–6 Calls je angereichertem Item). Das ergibt realistisch **gut unter 100
Gemini-Calls pro Tag** — selbst der niedrigste kolportierte Wert (250/Tag) lässt
damit deutlich Luft. `throttle_sec: 4.5` in der Config begrenzt zusätzlich auf
rund 13 Requests/Minute, um gängige Minutenlimits (oft ~10–15 RPM im Free-Tier)
nicht zu reißen.

Eine Ausnahme: Der **allererste** echte Lauf holt den kompletten aktuellen
Anthropic-News-Bestand nach (aktuell 13 Artikel, da es noch keinen
Dedup-Zustand gibt) — einmaliger Ausreißer, kein Dauerzustand.

## Bekannte Lücken (bewusst nicht vorgetäuscht)

- **Kein automatischer Provider-Fallback.** Nur Gemini ist konfiguriert. Horizon
  hat zwar einen echten `provider_chain`-Mechanismus, der aber pro Zweit-Provider
  feste Default-Modelle erzwingt (ein OpenRouter-Fallback mit frei wählbarem
  kostenlosem Modell wäre nur mit einem Code-Patch am Provider-Enum sauber
  möglich). Ohne Fallback sendet Horizon bei komplettem Kontingent-Ausfall trotzdem
  eine Mail (siehe oben) — nur eben ohne Ausweichmodell.
- **Kein 👍/👎-Feedback.** Existiert im Horizon-Code nicht (keine Route, keine
  Speicherung) — bewusst nicht mit einem toten `mailto:`-Link vorgetäuscht.
- **Der Anthropic-Scraper ist selbst geschrieben**, nicht Teil des offiziellen
  Horizon-Projekts. Er liest die aktuelle HTML-Struktur von anthropic.com/news
  (Selektoren sind bewusst strukturell statt an exakte CSS-Klassennamen gebunden,
  um Redesigns robuster zu überstehen, aber ein Garant ist das nicht). Bricht die
  Seite komplett um, würde die Quelle vermutlich einfach 0 Items liefern statt
  den Lauf zum Absturz zu bringen — das würde man daran merken, dass "Anthropic
  News" über mehrere Tage konstant leer bleibt.
