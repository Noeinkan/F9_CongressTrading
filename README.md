# Congress Trading (House + Senate)

Tracker per disclosure pubbliche del Congresso che acquisisce PTR e filing metadata, conserva i documenti raw, normalizza transazioni e asset in SQLite, ed esporta un dataset pronto per analisi e dashboard.

## Requisiti
- Python 3.10+
- API key Polygon (gratuita) per il ticker mapping
- (Opzionale) API key OpenFIGI per fallback mapping

Imposta le variabili d’ambiente:
- `POLYGON_API_KEY`
- `OPENFIGI_API_KEY` (opzionale)
- (Opzionale, House PTR) `HOUSE_PTR_AUTO_DOWNLOAD`, `HOUSE_PTR_AUTO_DOWNLOAD_MIN_YEAR`, `HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR`, `HOUSE_PTR_DOWNLOAD_MIN_INTERVAL_SECONDS` — vedi sezione House (PTR).
- (Opzionale, ingest veloce) `HOUSE_INGEST_SKIP_EXTERNAL_ASSET_LOOKUP=1` — durante `ingest-house` non chiama Polygon/OpenFIGI per asset non in cache (solo `manual_review` locale); utile con molti PDF; poi puoi rilanciare senza per arricchire i ticker dove serve.
- (Opzionale, re-parse) `HOUSE_INGEST_FORCE_REPARSE_PDFS=1` — ignora `files_ingested` e riparsa tutti i PDF House (aggiorna righe `transactions` esistenti grazie a `ON CONFLICT`); **disattivato di default**. Equivalente CLI: `python -m src.main ingest-house --force-reparse`. Da usare solo se vuoi riapplicare fix di parser/ticker a tutti i PDF senza cancellare il DB.

## Struttura
- `src/` codice
- `data/raw/house/` PDF House
- `data/raw/senate/` PDF Senate
- `data/db/` SQLite
- `data/cache/` cache lookup ticker

I contenuti sotto `data/raw/`, `data/db/`, `data/cache/` e i CSV in `data/*.csv` sono esclusi da Git (vedi `.gitignore`): si ricreano in locale con download, ingest ed export.

## Note legali
- Senate eFD richiede accettazione dei termini. Il downloader è progettato per uso conforme; verifica i termini prima dell’uso.
- Per `download-house-fd` e per l’autodownload dei PTR House durante `ingest-house`, verifica i termini e le policy di `disclosures-clerk.house.gov` e non schedulare richieste massicce o troppo frequenti.

## Nota House (PTR)
Con i metadata FD (`.txt`/`.xml`) gia presenti sotto `data/raw/house/`, `ingest-house` prova a scaricare dal Clerk ogni PTR mancante (`FilingType` = `P`) usando l’URL `public_disc/ptr-pdfs/<Year>/<DocID>.pdf`, per gli anni di filing da **`HOUSE_PTR_AUTO_DOWNLOAD_MIN_FILING_YEAR_DEFAULT`** in `src/config.py` (oggi **2023**) fino all’anno solare corrente, salvo override con le variabili sotto. Tra un download e l’altro viene applicata una breve pausa (default 0,2 s) per ridurre il carico sul server.

**Nota:** i `DocID` dei PTR spesso **iniziano con `200…`** (es. `20022428`); non sono l’anno 2002, sono identificativi del Clerk. Nella barra di avanzamento viene mostrato `Year/DocID.pdf` per evitare ambiguita.

Opzioni ambiente:
- `HOUSE_PTR_AUTO_DOWNLOAD` — default attivo; `0` / `false` / `no` disattiva del tutto il download PTR dal Clerk (restano solo i PDF gia su disco).
- `HOUSE_PTR_AUTO_DOWNLOAD_MIN_YEAR` — primo `Year` incluso (default in codice: **2023**; imposta `2022` se ti servono anche i PTR con filing year 2022).
- `HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR` — se impostato (es. `2024`), non si richiedono PDF con `Year` oltre quel valore (default: anno corrente).
- `HOUSE_PTR_DOWNLOAD_MIN_INTERVAL_SECONDS` — pausa minima tra richieste successive (default `0.2`).

Se un `DocID` non e piu disponibile o l’URL cambia, salva il PDF a mano in `data/raw/house/<Year>/<DocID>.pdf` e rilancia l’ingest.

Durante `ingest-house`, la pipeline prova anche a correggere automaticamente i PTR House gia presenti nel database:
- recupera `filing_date` dai metadata FD quando il PDF PTR non lo espone chiaramente
- ripara `transaction_date` e campi transazione quando vecchie righe erano state parse male
- consolida filing PTR duplicati creati in precedenza per lo stesso PDF/raw path

## Dove trovare i PDF
- House: usa il portale ufficiale del Clerk della House su https://disclosures-clerk.house.gov/PublicDisclosure/FinancialDisclosure. I file FD annuali sono scaricabili in blocco (`download-house-fd` o zip manuali); i PTR possono essere scaricati automaticamente da `ingest-house` quando conosci `Year` e `DocID` dai metadata, oppure dal portale e salvati sotto `data/raw/house/<anno>/`.
- Senate: usa il portale ufficiale eFD su https://efdsearch.senate.gov/search/. Devi prima accettare i termini di utilizzo, poi puoi cercare i filing dal 2012 in avanti. Filtra o cerca i Periodic Transaction Report, apri il filing e salva il PDF sotto `data/raw/senate/<anno>/`.
- Executive (OGE): i 278-T (periodic transactions) e 278e (annual report) del Presidente USA sono pubblici sotto 5 U.S.C. § 13107 sul portale https://extapps2.oge.gov/201/Presiden.nsf/. La pipeline OGE è registrata come lista di URL hard-coded in `src/oge_source.py` (`TRUMP_OGE_FILINGS`): aggiungere un nuovo filer = appendere un `OgeFiling`. `download-oge` scarica a 1 req/sec, salta i file gia presenti, fallisce loud su 404; `ingest-oge` processa i PDF in `data/raw/oge/`, scrive i 278-T nella tabella `transactions` (come i PTR) e gli 278e nella nuova tabella `executive_holdings` (snapshot annuale).
- Il parser cerca ricorsivamente qualsiasi file `.pdf` dentro `data/raw/house/`, `data/raw/senate/` e `data/raw/oge/`, quindi le sottocartelle per anno sono consigliate ma non obbligatorie.
- Se hai archivi `.zip`, puoi anche copiarli in `data/raw/`, `data/raw/house/` o `data/raw/senate/`: la pipeline prova a estrarli automaticamente prima del parsing.

## Setup rapido Windows
- Esegui `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 ingest-all` per installare le dipendenze nel venv del progetto e lanciare l’ingestione.
- Se vuoi un comando diverso, sostituisci `ingest-all` con ad esempio `export-csv`, `ingest-house` o `ingest-senate`.
- In VS Code puoi usare i task workspace `Ingest All (venv)`, `API Server (venv)` e `Frontend Dev` per eseguire sempre il progetto con `.venv\Scripts\python.exe`.

## Comandi principali
- Bulk FD House (metadata annuali `.zip` dal Clerk, poi estrazione in `data/raw/house/<anno>FD/`): `python -m src.main download-house-fd` (default: anni da `START_YEAR` in `src/config.py` fino all’anno corrente). Opzioni: `--years 2020 2021`, `--overwrite`, `--zip-only` (solo zip; l’estrazione avviene al prossimo `ingest-house`).
- Download OGE Executive (PDF 278-T + 278e dal registro in `src/oge_source.py`): `python -m src.main download-oge` (opzioni: `--filer "Donald J. Trump"`, `--overwrite`).
- Ingest House 2022+: `python -m src.main ingest-house`
- Ingest Senate 2022+: `python -m src.main ingest-senate`
- Ingest OGE Executive (PDF in `data/raw/oge/`): `python -m src.main ingest-oge`
- Esegui tutto: `python -m src.main ingest-all` (House + Senate + OGE)
- Export CSV: `python -m src.main export-csv --out data/congress_trades.csv`
- Export review queue: `python -m src.main export-review-csv --out data/review_queue.csv`
- API: `python -m src.api` (frontend: `cd frontend && npm run dev`)
- Alert Telegram delle transazioni notevoli appena ingerite: `python -m src.main notify-events` (aggiungi `--dry-run` per vedere il messaggio senza inviarlo)
- Riepilogo settimanale + stato pipeline: `python -m src.main notify-digest` (`--force` per inviarlo subito)
- Verifica che il bot funzioni: `python -m src.main notify-test`

## Stato attuale
Il repository ora mantiene due livelli di storage:

1. tabelle legacy per compatibilita (`trades`, `fd_filings`)
2. schema normalizzato per il tracker:
	- `members`
	- `filings`
	- `transactions`
	- `issuers`
	- `transaction_tags`
	- `review_queue`
	- `asset_resolution_cache`

Questo permette di conservare l'asset raw dichiarato, un ticker se risolvibile, un `confidence_score`, e uno `review_status` per distinguere match esatti, match fuzzy e casi da revisione manuale.

## Risoluzione asset
La pipeline di resolution classifica ogni asset in una di tre categorie:
- `exact_match`: nome/ticker risolto con corrispondenza canonica affidabile; non entra in review queue per la sola resolution
- `fuzzy_match`: ticker trovato ma con corrispondenza approssimata; resta disponibile nel dataset ma viene messo in review queue
- `manual_review`: nessun ticker affidabile; il record viene trattenuto per revisione manuale

La cache `asset_resolution_cache` persiste anche questa classificazione, cosi le riesecuzioni non ricadono ogni volta sugli stessi lookup esterni.

## Schema CSV
Colonne principali dell'export normalizzato:
- `member`
- `chamber`
- `filing_type`
- `filing_date`
- `transaction_date`
- `owner_type`
- `asset_name_raw`
- `asset_name_normalized`
- `asset_type`
- `issuer_name`
- `ticker`
- `transaction_type`
- `amount_low`
- `amount_high`
- `amount_range_raw`
- `confidence_score`
- `review_status`
- `source_url`
- `raw_document_path`

## Limiti correnti
- un `ingest-house` con molti anni di metadata FD puo innescare centinaia o migliaia di download PTR dal Clerk; usa `HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR` o disattiva con `HOUSE_PTR_AUTO_DOWNLOAD=0` se vuoi solo file locali
- il parser PTR resta euristico e dipende dalla struttura del PDF
- alcuni PDF House con layout o note molto anomale possono ancora richiedere affinamenti puntuali del parser
- la risoluzione degli asset distingue ora exact match, fuzzy match e manual review, ma resta limitata dalla qualita dei nomi dichiarati nei PDF
- i fuzzy match vengono esportati con ticker e tenuti in review queue; i manual review restano senza ticker finche non vengono corretti a valle
- gli alert Telegram coprono quattro casi (opzioni, importi grandi, cluster di membri sullo stesso ticker, filing oltre i 45 giorni): tutto il resto resta visibile solo in dashboard

## Notifiche Telegram

Il job notturno, finita l'ingestione, invia **un solo messaggio** con le
transazioni notevoli arrivate quella notte, e **niente** se non c'e nulla di
notevole. Il silenzio e informativo: se non arriva un messaggio, non e arrivato
nulla che valga la pena. Una volta a settimana arriva anche un riepilogo con la
forma della settimana e una riga sullo stato della pipeline.

### Cosa arriva

Quattro casi accendono un alert immediato, dal piu raro al piu comune:

- **Opzioni** — un membro compra o vende opzioni sopra i 15.000 $ dichiarati.
  Raro, a leva e direzionale: il segnale piu forte su singola riga.
- **Importi grandi** — il *minimo* della fascia dichiarata supera i 50.000 $.
  Il Congresso dichiara fasce, non cifre: usare il minimo tiene la soglia
  prudente (una fascia "50.001–100.000 $" passa, una "15.001–50.000 $" no).
- **Cluster** — piu membri (default 3) sullo stesso ticker nella stessa
  finestra. Calcolato con la stessa funzione della pagina Patterns, quindi
  alert e dashboard non possono divergere. Un cluster viene riannunciato solo
  se *cresce*: "3 membri su NVDA" e notizia una volta, "5 membri" lo e di nuovo.
- **Filing in ritardo** — depositato oltre i 45 giorni previsti dallo STOCK Act.
  Segnale di compliance piu che di trading, quindi viene segnalato a prescindere
  dall'importo ma con un tetto stretto: se una notte ne arrivano decine, ne
  vedi le prime 3 e un "... and N more".

Un ritardo su una transazione gia segnalata per altri motivi diventa
un'etichetta sulla riga esistente (`filed 87d late`), non un secondo messaggio.

### Configurazione (una volta)

1. In Telegram apri la chat con **@BotFather**, manda `/newbot` e segui le due
   domande (nome e username del bot). Alla fine BotFather risponde con una riga
   `Use this token to access the HTTP API:` seguita dal token: quello e
   `TELEGRAM_BOT_TOKEN`.
2. Apri la chat col bot appena creato e mandagli un messaggio qualsiasi (serve
   solo a far esistere la conversazione: un bot non puo scrivere a chi non gli
   ha mai scritto). Se preferisci ricevere gli alert in un gruppo, aggiungi il
   bot al gruppo e scrivi un messaggio la.
3. Nel browser apri `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates`.
   Nella risposta JSON cerca `"chat":{"id":...}`: quel numero e
   `TELEGRAM_CHAT_ID` (per un gruppo e negativo, col meno davanti — va copiato
   col meno). Se la risposta e `{"ok":true,"result":[]}` il messaggio del punto
   2 non e arrivato: mandane un altro e ricarica.
4. Scrivi i due valori nel `.env` del server (`/opt/F9_CongressTrading/.env`).
   Tutte le soglie sono opzionali: vedi `.env.example` per l'elenco commentato.
5. Verifica subito, dalla cartella del repo:
   `python -m src.main notify-test`. Se il token o la chat sono sbagliati il
   comando stampa l'errore ed esce con codice diverso da zero — non resta
   silenzioso.
6. Il **primo** `notify-events` non invia lo storico: marca le righe gia
   presenti come "viste" e manda un solo messaggio "alerts armed". Dalla notte
   successiva arrivano solo le novita.

### Come e agganciato al cron

`scripts/nightly_ingest.sh` chiama `notify-events` e `notify-digest` dopo gli
export. Il digest si auto-limita al giorno configurato
(`CONGRESS_NOTIFY_DIGEST_WEEKDAY`, default lunedi), quindi **basta la voce di
cron che esiste gia**: non serve aggiungerne una seconda.

Lo script ha anche un trap sull'errore: se l'ingestione stessa muore, arriva un
messaggio che nomina la riga fallita. Prima l'unico modo di accorgersene era
aprire `/var/log/f9-congress-trading/ingest.log`.

### Se gli alert smettono di arrivare

Due cause hanno aspetti diversi, e la differenza e nel log:

- **Non e arrivato niente di notevole.** Nel log trovi
  `notify-events: quiet - ...`. Normale: i depositi arrivano a ondate intorno
  alle scadenze.
- **La consegna e fallita.** Nel log trovi `notify-events: failed - ...` con lo
  stato HTTP, e il comando esce con codice diverso da zero. Il punto importante:
  in questo caso il segnaposto delle righe gia lette **non avanza**, quindi gli
  eventi non vengono persi — la notte dopo vengono ritentati. Un token
  revocato da Telegram da HTTP 401: rifallo dal punto 1 e rimetti il valore
  nel `.env`.

In ogni caso `python -m src.main notify-test` risponde in due secondi se il
canale e vivo, e il digest settimanale segnala da solo se la pipeline non
ingerisce piu nulla da piu di 10 giorni.

## Dashboard (React + FastAPI)
La dashboard legge dallo SQLite normalizzato (`members`, `filings`, `transactions`, `review_queue`, `executive_holdings`) e, se non trova righe, prova i CSV esportati.

Vista inclusa:
- KPI su volume transazioni, membri attivi, ticker risolti e review aperte
- timeline mensile dell'attivita
- ranking di membri e ticker
- filtri per lookback e trimestre
- pannello review queue per casi irrisolti o derivati dal `review_status`
- tabella raw con download CSV del subset filtrato
- pagina Executive (OGE 278-T + 278e): filers, filings, transazioni periodiche, holdings annuali — `chamber='Executive'`, esposta via `/api/executive/*`

Avvio locale (tutto dalla root del repo):

| Comando | Cosa fa |
|---|---|
| `npm start` | **⭐ Lancia API + frontend insieme.** Log colorati, Ctrl+C termina entrambi. |
| `npm run dev` | Identico a `npm start` (alias). |
| `npm run start:api-only` | Solo backend FastAPI (`:9001`). |
| `npm run start:web-only` | Solo frontend Vite (`:5173`). |
| `npm run start:detach` | Apre una nuova finestra PowerShell con dentro `npm start` (sopravvive se chiudi quella attuale). |
| `npm run clean` | Killa processi appesi alle porte 9001/5173-5175. |
| `powershell -ExecutionPolicy Bypass -File .\dev.ps1` | Fallback shell pura (no Node), log in file `.dev-*.log`. |
| Manuale (2 terminali) | `python -m src.api` + `cd frontend && npm run dev`. |
| In VS Code | `Ctrl+Shift+B` → `Start Dashboard` (compound task). |

**Prima volta:** `npm install` (installa `concurrently` come dev-dep). Le dipendenze frontend sono già gestite da `frontend/package.json`; al primo `npm start` Vite le usa direttamente da `frontend/node_modules/` (se mancanti, `dev.ps1` fa `npm install` automaticamente).

**Se una porta è occupata:** `npm run clean` e riprova.

### Dashboard remota (VPS)

Per esporre l'app su internet (es. `http://77.42.70.26/`) da un VPS Linux con repo e SQLite locali:

1. Copia `.env.example` in `.env` e imposta `APP_USERNAME`, `APP_PASSWORD`, `API_SERVER_ADDRESS=127.0.0.1`, `API_SERVER_PORT=9001`
2. Apri le porte firewall: `sudo ufw allow 80/tcp` (e `443/tcp` per HTTPS)
3. Installa Caddy + systemd (`deploy/congress-api.service`, `deploy/congress-web.service` — vedi `deploy/README.md`)
4. Da un altro laptop apri l’URL pubblico e accedi con username/password

**Sicurezza:** su HTTP le credenziali viaggiano in chiaro; per uso pubblico prolungato conviene HTTPS (Caddy con dominio). Dettagli operativi in `deploy/README.md`.

## Troubleshooting interprete VS Code
Se vedi errori come `ModuleNotFoundError: No module named 'dateutil'`, il problema di solito non e nel repository ma nell'interprete Python usato dalla sessione corrente.

Checklist rapida:
1. seleziona l'interprete del workspace: `.venv\Scripts\python.exe`
2. chiudi i terminali gia aperti e aprine uno nuovo dopo il cambio interprete
3. usa i task `Ingest All (venv)` o `API Server (venv)` invece di lanciare `python` generico

Nota: in questo workspace `.vscode/settings.json` punta gia al venv locale, ma un terminale aperto prima del cambio puo continuare a usare un Python globale.

Se il database e vuoto:
1. `python -m src.main ingest-all`
2. `python -m src.main export-csv --out data/congress_trades.csv`
3. `python -m src.api` e `cd frontend && npm run dev`
