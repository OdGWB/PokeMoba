# PokrLOL

MOBA 2D con i Pokémon, stile League of Legends, da giocare in LAN tra amici.
Progetto personale **non commerciale**. Sprite da PMD SpriteCollab (CC BY-NC 4.0,
vedi [CREDITS.md](CREDITS.md)).

> **Stato: Fase 8 completa — tutte le 8 fasi fatte.**
> Fase 8: mappa **5v5** (150×150, 3 torri per lane per lato, 1 nucleo), con la
> stessa struttura della 3v3 (3 lane, fiume, 2 tane, giungla). **Selezionabile
> dalla lobby**: l'host preme `M` per alternare 3v3/5v5. Su 5v5 giocano 5 per
> squadra e la tana di Arceus si apre al minuto 20 (invece di 15). In giocatore
> singolo: `python run_client.py --single --map data/maps/map_5v5.json`.
>
> **Stato precedente: Fase 7 completa.**
> Fase 7: giungla viva. Pokémon **neutrali** nei campi (danno XP e oro). Nella
> tana bassa il **leggendario meteo** (dal min 5, tipo casuale): sconfitto cambia
> il meteo di tutta la mappa e **trasforma la giungla** in uno dei 3 stati evoluti
> — Sole (i cespugli spariscono), Pioggia (compaiono pozze che rallentano i
> non-Acqua), Vento (si aprono passaggi nei muri) — oltre allo stato base: 4
> giungle in tutto. Ricompare ogni 5 min come meteo diverso; il meteo modifica i
> danni (Fuoco/Acqua ±50%). Nella tana alta **Arceus** (murata fino al min 15),
> con lastra di tipo casuale e buff **Giudizio** (3 min: tipo della lastra come
> STAB extra, minion che fanno doppio danno alle torri; perso morendo). I **bot
> comprano** oggetti al negozio. Meteo e terreno sincronizzati anche in rete.
>
> **Stato precedente: Fase 6 completa.**
> Fase 6: oro e negozio. Oro da ultimo colpo sui minion, uccisioni, assist, torri
> e guadagno passivo. Negozio usabile solo in **base** (tasto **P**), **6 slot
> oggetto** per Pokémon. Oggetti base economici che si combinano in oggetti
> completi (il prezzo sconta i componenti già posseduti), definiti in
> `data/items.json`. Gli oggetti sono per ora **placeholder** con bonus
> statistici generici: la meccanica è completa, gli effetti precisi di ciascuno
> si decideranno dopo cambiando solo il JSON. Icone: PokeAPI (segnaposto se mancano).
>
> **Stato precedente: Fase 5 completa.**
> Fase 5: multiplayer LAN. Un giocatore **ospita** (server autoritativo UDP a 30
> tick/s, nello stesso processo), gli altri si **uniscono** via IP locale. I client
> mandano solo input (con numero di sequenza); il server invia 20 snapshot/s
> **filtrati per la visione di ogni squadra** (anti-cheat) e i client **interpolano**
> tra gli ultimi due per un movimento fluido. Serializzazione binaria compatta
> (modulo `struct`, niente JSON). Lobby con scelta squadra e Pokémon; le disconnessioni
> non fanno crashare (il Pokémon diventa un bot). Menu: giocatore singolo / ospita / unisciti.
>
> **Stato precedente: Fase 4 completa.**
> Fase 4: nebbia di guerra (vedi solo ciò che è nel raggio visivo di un alleato;
> il resto è penombra se già esplorato, nero se mai visto), le unità nemiche non
> viste sono nascoste, i **cespugli** nascondono chi è dentro finché un nemico
> non si avvicina, e **minimappa** cliccabile in basso a destra (sinistro = sposta
> la camera, destro = ordina lo spostamento). Esplorare rende noto solo il
> **terreno** (penombra): i nemici si vedono solo quando sono ora nel tuo raggio
> visivo, come in LoL. Anche i **bot rispettano la nebbia** (ingaggiano solo chi
> vedono davvero). La visione è calcolata nel motore puro, pronta per il
> filtraggio lato server in Fase 5.
>
> **Stato precedente: Fase 3 completa.**
> Fase 2: mappa 3v3 greybox (3 lane, fiume, due tane, giungla), torri, ondate di
> minion stile LoL (melee + caster, cannone ogni 3ª ondata), nucleo, bot, respawn
> e vittoria distruggendo il nucleo nemico.
> Fase 3: statistiche + crescita per livello, tipi ed efficacia (niente immunità:
> gli 0× valgono 0,25×), danno fisico/speciale con STAB, livelli/esperienza fino
> al 15, respawn crescente col livello, cura alla base; mosse Q/W/E/R data-driven
> con 4 gradi (R 3, ai lv 8/11/14), evoluzioni ai livelli 4 e 8 con scelta dei
> potenziamenti stile Unite e dell'ultimate, effetti a particelle per tipo e
> indicatori di mira. I bot usano mosse, salgono di grado ed evolvono da soli.
> **In arrivo** (Fase 4): nebbia di guerra, cespugli, minimappa.

## Requisiti

- Python 3.11+
- [pygame-ce](https://pyga.me/)

## Installazione

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Avvio

Avvia il client. Il **menu** permette di scegliere la **modalità** (3v3 / 5v5,
tasto `M`) e poi: giocatore singolo (vs bot), ospita LAN, o unisciti via IP.
Ogni squadra ha un **jungler bot** che farma i campi neutrali e il leggendario.

```bash
python run_client.py
```

Partita 3v3 contro i bot, diretta:

```bash
python run_client.py --single
```

Multiplayer LAN: un giocatore sceglie **Ospita** dal menu (mostra il proprio IP);
gli altri scelgono **Unisciti** e digitano quell'IP. In alternativa un server
dedicato: `python run_server.py`. Demo Fase 1: `python run_client.py --single --map data/maps/map_test.json`.

Rigenerare le mappe (dopo aver modificato i parametri nei generatori):

```bash
python tools/gen_map_3v3.py
python tools/gen_map_5v5.py
```

Il server LAN non esiste ancora (Fase 5). `run_server.py` è solo un segnaposto.

## La partita 3v3

Controlli il Pokémon della **squadra blu** in mid; due bot alleati tengono top e
bot, tre bot rossi difendono. Partono ondate di **minion** (3 melee + 3 caster,
cannone ogni 3ª) che seguono le lane; le **torri** colpiscono prima i minion,
poi i Pokémon nemici che hanno appena attaccato un alleato, e "scaldano" (più
colpi di fila sullo stesso bersaglio = più danno: niente dive senza minion
davanti). Avvicinati ai nemici per fare **auto-attacco**. Il **nucleo** è
invulnerabile finché la squadra ha ancora torri in piedi: vanno abbattute prima.
I respawn crescono col livello e i minion si rinforzano col tempo, così le
partite durano circa **15-20 minuti** e finiscono in modo deciso. Si vince
distruggendo il nucleo nemico (in alto a destra). I numeri di bilanciamento
stanno in `config.py` e nei JSON in `data/` (facili da tarare).

## Comandi

| Comando          | Azione                                             |
|------------------|----------------------------------------------------|
| Tasto destro     | Muovi il Pokémon verso il punto (percorso A*)      |
| Tasto sinistro   | Attacca: su un nemico lo insegue e colpisce; a terra = attack-move |
| `Q`/`W`/`E`/`R` (tieni premuto) | Mira la mossa (compare l'indicatore); rilascia o clic sinistro per lanciare; clic destro annulla |
| `Ctrl` + `Q`/`W`/`E`/`R` | Assegna un punto grado alla mossa          |
| `1` / `2`        | Scegli il potenziamento (solo **in base**): Q al lv 5, W al 6, E al 7, R al 8 |
| Minimappa (sinistro) | Sposta la camera in quel punto                 |
| Minimappa (destro)   | Ordina al Pokémon di muoversi in quel punto    |
| `P`              | Apri/chiudi il negozio (acquisti solo in base; 6 slot) |
| `Y`              | Blocca/sblocca la camera                           |
| Mouse ai bordi   | Scorre la camera (solo da sbloccata)               |
| `Spazio` (tenuto)| Ricentra la camera sul Pokémon                     |
| `S`              | Ferma il Pokémon                                   |
| `F11` / `F`      | Schermo intero on/off                              |
| `ESC`            | Esci                                               |

La finestra è **ridimensionabile** a qualsiasi dimensione e supporta il
**fullscreen**: l'area di gioco resta fissa e uguale per tutti (scalata con
lettera-box), così nessuno vede più mappa degli altri.

## Sprite (opzionale in Fase 1)

Se non ci sono sprite, il Pokémon è disegnato come un **cerchio colorato** con un
indicatore di direzione: così movimento, A* e camera si testano subito.

Per usare gli sprite veri, metti una cartella PMD SpriteCollab in
`assets/pokemon/{numero_dex}/` (es. `assets/pokemon/0004/` per Charmander), con
i fogli `*-Anim.png` e il file `AnimData.xml`. Il percorso è indicato nel JSON
del Pokémon (`sprite_dir`). Il loader taglia i frame e li tiene in cache.

## Struttura del progetto

```
engine/   Simulazione PURA (niente pygame): griglia, A*, hash spaziale,
          movimento, entità, World e match.py (ondate, IA, combattimento, vittoria).
sim/      Orchestrazione: comandi di input + passo a tick fisso.
game/     Client pygame: app, camera, renderer, input, sprite, scene.
data/     Contenuti data-driven: mappe e Pokémon in JSON.
tools/    Generatori (es. gen_map_3v3.py).
assets/   Sprite PMD SpriteCollab (non inclusi nel repo).
net/      Multiplayer LAN: protocol (codec binario), server, client, snapshot.
tests/    Test della logica pura.
```

Vincolo chiave: `engine/` e `sim/` non importano mai pygame, così la stessa
simulazione girerà sul server (Fase 5) ed è testabile senza grafica.

## Test

```bash
python -m pytest tests/ -q
```

(oppure, senza pytest installato: `python -m unittest discover -s tests`)

## Modificare la mappa

Le mappe sono JSON con una griglia ASCII facile da editare: `legend` associa i
caratteri ai tipi di tile, `rows` è la mappa (`.` pavimento, `#` muro), `spawns`
i punti di partenza. Vedi [data/maps/map_test.json](data/maps/map_test.json).
