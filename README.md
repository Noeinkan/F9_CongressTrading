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
- (Opzionale, re-parse) `HOUSE_INGEST_FORCE_REPARSE_PDFS=1` — ignora `files_ingested` e riparsa tutti i PDF House (aggiorna righe `transactions` esistenti grazie a `ON CONFLICT`); usalo dopo un ingest veloce per applicare Polygon/OpenFIGI senza cancellare il DB.

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
- Il parser cerca ricorsivamente qualsiasi file `.pdf` dentro `data/raw/house/` e `data/raw/senate/`, quindi le sottocartelle per anno sono consigliate ma non obbligatorie.
- Se hai archivi `.zip`, puoi anche copiarli in `data/raw/`, `data/raw/house/` o `data/raw/senate/`: la pipeline prova a estrarli automaticamente prima del parsing.

## Setup rapido Windows
- Esegui `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 ingest-all` per installare le dipendenze nel venv del progetto e lanciare l’ingestione.
- Se vuoi un comando diverso, sostituisci `ingest-all` con ad esempio `export-csv`, `ingest-house` o `ingest-senate`.
- In VS Code puoi usare i task workspace `Ingest All (venv)`, `API Server (venv)` e `Frontend Dev` per eseguire sempre il progetto con `.venv\Scripts\python.exe`.

## Comandi principali
- Bulk FD House (metadata annuali `.zip` dal Clerk, poi estrazione in `data/raw/house/<anno>FD/`): `python -m src.main download-house-fd` (default: anni da `START_YEAR` in `src/config.py` fino all’anno corrente). Opzioni: `--years 2020 2021`, `--overwrite`, `--zip-only` (solo zip; l’estrazione avviene al prossimo `ingest-house`).
- Ingest House 2022+: `python -m src.main ingest-house`
- Ingest Senate 2022+: `python -m src.main ingest-senate`
- Esegui tutto: `python -m src.main ingest-all`
- Export CSV: `python -m src.main export-csv --out data/congress_trades.csv`
- Export review queue: `python -m src.main export-review-csv --out data/review_queue.csv`
- API: `python -m src.api` (frontend: `cd frontend && npm run dev`)

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
- non esiste ancora un sistema di alert; la dashboard React e il primo layer di analisi sopra il backend normalizzato

## Dashboard (React + FastAPI)
La dashboard legge dallo SQLite normalizzato (`members`, `filings`, `transactions`, `review_queue`) e, se non trova righe, prova i CSV esportati.

Vista inclusa:
- KPI su volume transazioni, membri attivi, ticker risolti e review aperte
- timeline mensile dell'attivita
- ranking di membri e ticker
- filtri per lookback e trimestre
- pannello review queue per casi irrisolti o derivati dal `review_status`
- tabella raw con download CSV del subset filtrato

Avvio locale:
- **Un comando (consigliato):** `npm start` dalla root del repo.
  Lancia backend FastAPI (`:8000`) e frontend Vite (`:5173`) in parallelo, con log colorati, e apre il browser. Ctrl+C termina entrambi.
  La prima volta esegui `npm install` (installa `concurrently`).
- **Alternativa senza Node backend:** `powershell -ExecutionPolicy Bypass -File .\dev.ps1` (stesso comportamento, log in file `.dev-*.log`).
- **Manuale (due terminali):** API: `python -m src.api` (porta 8000); Frontend: `cd frontend && npm install && npm run dev` (porta 5173, proxy `/api/*`).
- **In VS Code:** task compound `Start Dashboard` (build default), oppure i due task separati `API Server (venv)` + `Frontend Dev`.

### Dashboard remota (VPS)

Per esporre l'app su internet (es. `http://77.42.70.26/`) da un VPS Linux con repo e SQLite locali:

1. Copia `.env.example` in `.env` e imposta `APP_USERNAME`, `APP_PASSWORD`, `API_SERVER_ADDRESS=127.0.0.1`, `API_SERVER_PORT=8000`
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
