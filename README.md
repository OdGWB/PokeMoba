# PokéMoba

MOBA 2D con i Pokémon, in stile League of Legends, da giocare **online tra amici** o
contro i bot. È un progetto personale **non commerciale**. Gli sprite vengono da PMD
SpriteCollab (CC BY-NC 4.0, vedi [CREDITS.md](CREDITS.md) e la schermata **Crediti**
nel menu).

## Cosa c'è

- **Due mappe**: 3v3 (100×100) e 5v5 (150×150). Ognuna ha 3 lane, il fiume, la
  giungla e due tane. Ci sono 3 torri per lane per lato e 1 nucleo. Il nucleo si
  scopre quando una lane di quella squadra resta senza torri.
- **Roster di 25 linee evolutive**, tutte data-driven (`data/pokemon/*.json`).
  - Mosse Q/W/E/R con 4 gradi (la R ne ha 3).
  - Evoluzioni ai livelli 4 e 8, alcune ramificate (per scelta, combinazione
    di mosse, oro o oggetto).
  - Potenziamenti delle mosse stile Unite.
  - Tipi ed efficacia (niente immunità: 0× vale 0,25×), danno fisico e speciale
    con STAB, livelli fino al 15.
- **Giungla viva**:
  - Campi neutrali.
  - Il **leggendario meteo** dal minuto 5: cambia il meteo e trasforma la giungla
    in 3 varianti (Sole, Pioggia, Vento).
  - **Arceus**, dal minuto 15 nella 3v3 e dal 20 nella 5v5, dà il buff *Giudizio*.
  - **Smite** per i jungler.
- **Oro e negozio**:
  - Catalogo a 3 livelli (`data/items.json`), con effetti in
    `engine/item_effects.py`.
  - 6 slot oggetto, acquisti solo in base.
- **Nebbia di guerra**: cespugli, minimappa e visione calcolate nel motore puro.
  Online, l'host filtra la visione per ogni squadra.
- **Bot**: lane, jungler e supporto. Comprano oggetti, tornano in base, assediano
  il nucleo scoperto e vanno in roam.
- **Online WebRTC** senza server: i codici si scambiano su Discord o WhatsApp.
  - L'host è autoritativo.
  - Il client usa predizione e interpolazione.
  - Draft a turni: 3v3 uno a testa; 5v5 B1, R1 R2, B2 B3, R3 R4, B4 B5, R5.
    I bot scelgono a caso dopo i giocatori.
  - Guida per gli amici: [GIOCARE_ONLINE.md](GIOCARE_ONLINE.md).
- **LAN (vecchia modalità, resta come riferimento)**: dalla schermata Gioca,
  Ospita [H] / Unisciti con l'IP [J]; server dedicato con `python run_server.py`.
  Il codice è in `net/lan/` e verrà tolto quando l'online sarà collaudato.
- **Menu**: Gioca, Personalizzazione (nickname e immagine profilo), Crediti, Tier
  list (personale e "developer", ricavata da tornei di bot), Editor delle animazioni
  e Opzioni.

Il profilo si salva in `%APPDATA%\PokeMoba\profile.json`, fuori dalla cartella del
gioco. Gli avatar si riscaricano con `python tools/fetch_avatars.py`.

## Requisiti e installazione

- Python 3.11+ (sviluppato su 3.13)
- [pygame](https://www.pygame.org/), [aiortc](https://github.com/aiortc/aiortc) (online)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
pip install -r requirements-dev.txt   # solo per i test (pytest)
```

## Avvio

```bash
python run_client.py
```

Oppure fai doppio clic su `gioca.bat`. Dal menu: **Gioca**, poi scegli la mappa
(partita offline contro i bot) oppure **Ospita / Unisciti** per l'online.

Per partire subito in una partita offline (comodo per i test):

```bash
python run_client.py --single --map data/maps/map_5v5.json --pokemon data/pokemon/sneasel.json --level 8
```

Altre opzioni: `--item <id>` (ripetibile), `--armature fausta|infausta`,
`--oro minion|neutrali`, `--colore rosso|giallo|...`. I launcher di prova per ogni
Pokémon sono in [launchers/](launchers/), per esempio `launchers/gioca_weavile.bat`.

Altri strumenti:

- Test online su un solo PC: `python tools/net_local_test.py`.
- Exe unico da mandare agli amici: `crea_exe.bat` (crea `dist\PokeMoba.exe`).
- Installer: `crea_installer.bat` (crea `dist\PokeMoba-Setup.exe` dall'exe, serve
  Inno Setup 6). Le Release su GitHub pubblicano l'installer da sole; il gioco
  installato si aggiorna poi da solo come prima.

## GitHub Actions

- **CI** (`.github/workflows/ci.yml`): i test (`pytest`) su ogni Pull Request verso
  `main` e su ogni push su `main`. Non crea exe né Release.
- **Release** (`.github/workflows/release.yml`): NON parte a ogni merge. Parte solo
  quando su `main` arriva una voce nuova in cima a `data/news.json`
  (`python -m game.news 3.0.N "Titolo" "punto"...`) con una versione non ancora
  pubblicata, oppure a mano da Actions → Release → Run workflow. Versione, tag
  (`v<build>`) e note della Release vengono da quella voce
  (`tools/release_info.py`).

## Comandi in partita

| Comando | Azione |
|---|---|
| Tasto destro | Muovi (percorso A*) |
| Tasto sinistro | Attacca un nemico; a terra = attack-move |
| `Maiusc` + sinistro | Attack-move solo sui Pokémon |
| `Q` `W` `E` `R` (tieni premuto) | Mira la mossa; rilascia o clic sinistro per lanciare, clic destro annulla |
| `Ctrl` + `Q` `W` `E` `R` | Assegna un punto grado alla mossa |
| `1` / `2` (in base) | Scegli il potenziamento o l'evoluzione in sospeso |
| `1`–`6` | Usa l'oggetto attivabile dello slot |
| `D` | Smite (solo offline, per ora) |
| `B` | Torna in base |
| `P` | Negozio (acquisti solo in base) |
| `S` | Ferma il Pokémon |
| `Y` | Blocca o sblocca la camera; mouse ai bordi per scorrere |
| `Spazio` (tenuto) | Ricentra la camera |
| Minimappa | Sinistro: sposta la camera. Destro: muovi lì |
| `Tab` / rotella | Cambia polarità (Magnezone, mentre miri) |
| `F11` / `F` | Schermo intero |
| `Esc` | Esci |

La finestra si può ridimensionare. L'area di gioco resta fissa e uguale per tutti,
scalata con le bande nere, così nessuno vede più mappa degli altri.

## Struttura del progetto

```
engine/     Simulazione PURA (niente pygame): griglia, A*, visione, entità,
            match.py (ondate, torri, IA, combattimento, vittoria) + un mixin per
            ogni linea di Pokémon (engine/<pokemon>.py).
sim/        Comandi di input + passo a tick fisso.
game/       Client pygame: app, camera, renderer, map_renderer (mappa a layer
            pre-renderizzati), hud, negozio, scene/, sprites/, effetti *_fx.py.
net/        Online WebRTC: host autoritativo, snapshot per squadra, delta,
            predizione e interpolazione (vedi net/__init__.py).
            net/lan/ = vecchia modalità LAN UDP.
data/       Contenuti JSON: mappe, Pokémon, oggetti, tier list, animazioni.
tools/      Generatori di mappe, download di sprite e icone, torneo di bot per la
            tier list (tier_sim.py / tier_build.py), sincronizzazione animazioni.
assets/     Sprite PMD SpriteCollab, icone, UI.
launchers/  .bat di prova (un Pokémon già a un certo livello).
tests/      Test della logica pura.
```

Vincolo chiave: `engine/` e `sim/` non importano mai pygame. La stessa simulazione
gira così sull'host online e si testa senza grafica.

Le regole grafiche e lo storico dei passaggi visivi sono in [CLAUDE.md](CLAUDE.md).

## Test

```bash
python -m pytest tests/ -q
```

Senza pytest: `python -m unittest discover -s tests`.

## Mappe

Le mappe (`data/maps/map_3v3.json`, `map_5v5.json`) sono generate da script e
contengono:

- `tiles`: la griglia.
- `lanes`, `structures`, `camps`, `dens`, `spawns`: lane, strutture, campi, tane
  e punti di partenza.
- `puddle_spots`, `wind_passages`: i punti che cambiano col meteo.

Per rigenerarle dopo aver cambiato i parametri dei generatori:

```bash
python tools/gen_map_3v3.py
python tools/gen_map_5v5.py
```
