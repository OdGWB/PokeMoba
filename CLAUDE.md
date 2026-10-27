Progetto: MOBA in Pygame, mappa top-down a tile.
Obiettivo visivo: giungla in stile League of Legends, cupa, densa,
con muri alti e vegetati. NON deve sembrare un parco.

Regole:
- La griglia di tile serve solo per la logica (collisioni, visione).
  La grafica può e deve uscire dai tile.
- Luce sempre da in alto a sinistra; ombre verso il basso a destra.
- Stile pixel art: disegna a bassa risoluzione e scala con
  pygame.transform.scale (nearest), mai smoothscale.
- Tutto ciò che è statico va pre-renderizzato una volta in Surface;
  a ogni frame solo blit.
- Dopo ogni modifica visiva salva screenshots/step_N.png, aprilo,
  analizzalo criticamente e correggi prima di dire che hai finito.
- Una modifica alla volta, senza toccare la logica di gioco.
- A fine di ogni passaggio approvato fai un commit con un messaggio
  che descrive la modifica.

## Stato lavori grafica
Aggiornare questa sezione alla fine di OGNI passaggio grafico futuro
(cosa fatto + scelte tecniche importanti).

Passaggi completati:
- Pipeline di rendering a layer (game/map_renderer.py, classe MapRenderer):
  la mappa statica e pre-renderizzata una volta in layer separati, poi a
  ogni frame solo blit. Ordine (dal basso): 1 ground, 2 ground_decor
  (rive/bordi/griglia), 3 shadows (AO + ombre dei muri), 4 walls_base
  (rilievi 2.5D), [unita/oggetti dinamici], 5 canopy, 6 lighting_overlay.
  I layer 1-4 si disegnano sotto le unita (MapRenderer.draw), 5-6 sopra
  (MapRenderer.draw_canopy).
- Ottimizzazione memoria:
  - layer `ground` opaco (senza SRCALPHA): copre tutto, blit piu veloce.
  - canopy e lighting_overlay non allocano nulla finche restano vuoti.
  - ogni layer e diviso in chunk da 1024px (map_renderer.CHUNK): un chunk
    si alloca solo se ci si disegna dentro, e nel draw si blittano solo i
    chunk visibili (culling per chunk).
  Risultato: RAM 3v3 139->93 MB, 5v5 312->208 MB; draw() ~2-3x piu veloce.
- Suolo di giungla PER PIXEL in coord mondo, bordi pixel-art (game/map_renderer.py
  _build_floor con numpy; _np_vnoise/_np_tone/_np_moss/_np_mud; _BAYER): palette
  cupa e desaturata (base #2E4A33, scuro #233B29, chiaro #3A5A3C, muschio
  #4A6B3A, terra #5A4A35, fango #3E3527). Niente smoothscale: i campi di rumore
  (tinta a 2 scale, muschio, fango) si calcolano a risoluzione ridotta (STEP=4
  px) UNA volta e si interpolano (bilineare, numpy) a piena risoluzione per
  strisce; il verde resta continuo, muschio e fango vengono QUANTIZZATI in 2-3
  livelli coi confini sgranati a DITHERING di Bayer -> chiazze organiche che
  attraversano i tile ma con bordi a gradini, non sfumati. Il dithering e' in
  una FASCIA STRETTA vicino al confine (dlevel: interno a tinta piena) e il
  muschio ha gradini piccoli -> poco contrasto, niente retino a scacchiera.
  Dettagli (ciuffi, fiocchi, granelli) disegnati sopra, saltando i sentieri.
  Costo una-tantum ~3-7s (solo al build; a frame solo blit). Screenshot:
  screenshots/step_3.png.
- Fango ridotto e schiarito (_np_mud/_mud_at soglia 0.70, _build_floor,
  _scatter_detail, _inner_mask): area ~60% in meno (chiazze piu piccole e
  sparse), colore schiarito a #4A3D2C (JUNGLE_MUD) con VARIAZIONE interna da
  rumore fine (_np_mudtone: lerp tra fango chiaro e pozzanghera scura) -> non
  piu una macchia marrone uniforme che sembra un buco. Nel fango denso: granelli
  + qualche pozzanghera piu scura; ai BORDI (0.15<mu<0.5) ciuffi d'erba piu
  fitti che invadono. Il fango e SOLO dentro l'anello delle lane: _inner_mask fa
  un flood-fill dal bordo mappa con le LANE come barriera -> la zona ESTERNA
  (corridoio oltre le lane) resta senza fango. Screenshot: screenshots/step_6.png
  (chiazza ravvicinata) e step_6_over.png (minimappa).
- Sentieri pixel-art a 3 livelli (game/map_renderer.py _compute_paths/
  _stroke_paths/_catmull): Dijkstra multi-sorgente dai tile-lane. I cespugli
  (oltre ai muri) sono OSTACOLI: il sentiero li AGGIRA, non ci passa sotto. La
  PENALITA' sui tile adiacenti a muri/cespugli tiene il sentiero in campo aperto
  e, se un ostacolo e vicino, gli corre ACCANTO; collega sempre campo<->lane (rotte
  troppo corte scartate, niente vicoli ciechi). Spline Catmull-Rom deformata con
  rumore, larghezza variabile (rumore, 1-2 tile). Profilo a 3 LIVELLI netti
  (bordo scuro, terra, nucleo secco DIRT_DRY) col bordo esterno a 2 densita' di
  DITHERING (niente sfumatura); sopra, ciuffi d'erba che invadono la terra,
  sassolini e foglie. La terra resta solo sui tile d'erba (gli altri ritagliati)
  e sul sentiero NON si disegnano fili d'erba. I campi arrivano via
  MapRenderer.set_camps(camps). Screenshot: screenshots/step_4.png.
- Incroci FUSI + radura del campo (_stroke_paths rifatto): i dischi di TUTTE le
  rotte confluiscono in UN SOLO insieme (er_d/br_d/mr_d/cr_d). Ogni rotta si
  rasterizza nella propria bbox ma con l'UNIONE dei dischi che la toccano, quindi
  dove due sentieri si incrociano o condividono un tratto (piu campi -> stessa
  lane) le maschere sono l'unione: un UNICO incrocio a bordi fusi, senza strisce
  sovrapposte ne doppi bordi scuri. Le bbox che si sovrappongono ricompongono gli
  STESSI pixel (stesse maschere di unione + dithering in coord assolute) ->
  idempotente. Ogni ramo TERMINA sul suo campo con una RADURA tonda di terra
  battuta (disco centrato sul tile del campo, aggiunto ai dischi): il sentiero
  "porta a un campo" e non svanisce piu nell'erba vicino a un muro. Screenshot:
  screenshots/step_5.png (incrocio) e step_5_over.png (mappa intera).
- Cespugli ricolorati coi toni della giungla (BUSH_* in renderer.py: base
  #1F3B24, luce #3E6B3A, cresta non-lime): armonia con la nuova palette, in
  attesa del rifacimento completo delle chiome (passo futuro).
- Lane desaturata (LANE_* verso il grigio-bruno) e bordo lane<->erba IRREGOLARE
  OVUNQUE in stile pixel art (renderer.py _edge_overlay): la frontiera segue un
  rumore in coordinate MONDO lungo il bordo -> continua e mossa attraverso tutti
  i tile (mai dritta); transizione a gradini con dithering di Bayer (solido
  vicino all'erba, stipple verso la terra) + ciuffi d'erba che invadono la lane.
- Ambient occlusion sul layer shadows (game/map_renderer.py _build_ao): ombra di
  contatto morbida entro ~1.5 tile dai tile "alti" (muri + cespugli), colore
  #0F1E1A alpha max 110. Distanza euclidea dai tile alti calcolata a BASSA
  risoluzione (step ~ts/4) con shifted-min (per ogni offset entro il raggio si
  aggiorna il minimo della distanza), falloff smoothstep (max a ridosso
  dell'ostacolo -> 0 a 1.5 tile), poi upscale bilineare (_upscale) e blit a
  blocchi CHUNK saltando i blocchi vuoti (_blit_blocks) -> lazy come gli altri
  layer. Screenshot: screenshots/step_7.png.
- Velo d'atmosfera sul layer lighting_overlay (game/map_renderer.py
  _build_lighting), SOPRA le unita: (a) ombre della chioma = rumore a bassa
  frequenza (_np_vnoise, chiazze ~6 tile) scuro #0C1613, SOLO sulla giungla
  (tutto cio che non e' TILE_LANE) con un velo base uniforme -> la giungla resta
  piu cupa delle lane; (b) poche macchie di luce calda #DC925C (arancio chiaro)
  vicino ai campi (falloff gaussiano, raggio ~3 tile) che "aprono" la chioma
  scurita (radura illuminata); (c) composite warm-over-dark premoltiplicato in
  un'unica RGBA per pixel, calcolato a strisce (niente array a piena mappa) e
  blittato a blocchi CHUNK lazy. Alfe contenute: le unita restano leggibili.
  LEGGIBILITA' DEI MURI: la cima dei muri (TILE_WALL/TILE_JUNGLE_WALL) e' quasi
  esclusa dal velo di chioma (resta al 30%, WALL_CANOPY_KEEP) e attenua la luce
  calda (resta al 35%, WALL_WARM_KEEP), cosi i muri restano nettamente piu
  chiari del terreno (a colpo d'occhio e in minimappa si distingue il
  calpestabile). I muri sono estrusi verso l'alto di H, quindi la maschera a
  piena risoluzione (wall_px) marca anche la fascia della CIMA indicizzando la
  riga del muro sia da y//ts sia da (y+H)//ts. I cespugli NON sono esclusi (sono
  vegetazione: il velo ci sta bene). Vignettatura leggera
  (VIGNETTE_*) scurisce i bordi dello SCHERMO: screen-space, costruita una volta
  per dimensione vista (_vignette, cache) e blittata per ultima in draw_canopy,
  NON nei layer di mappa. Screenshot: screenshots/step_7.png (ravvicinato con
  finte unita) e step_7_over.png (mappa intera).
- [SUPERATO dal passo seguente] Primo tentativo: autotiling a 8 vicini per-tile
  sui muri di giungla (angoli tondi per sprite). Migliorava i bordi ma le
  diagonali restavano scalini da un tile e i muri isolati rettangoli, quindi e'
  stato sostituito dalla SILHOUETTE a maschera (sotto). Screenshot d'epoca:
  step_8.png.
- SILHOUETTE dei MURI DI GIUNGLA a maschera (game/map_renderer.py
  _jungle_solid/_build_jungle_walls/_build_jungle_shadow; _build_ao ora prende la
  silhouette). La SAGOMA non e' piu per-tile: si ricava da una maschera binaria e
  si ammorbidisce, cosi diagonali e muri isolati non mostrano la griglia.
  _jungle_solid: (1) maschera binaria dei TILE muro-giungla; (2) campo da DISCHI
  sovrapposti sui centri-muro (NON dai quadrati dei tile: l'unione di dischi non
  ha spigoli di griglia -> niente lati dritti/basi rettangolari residue), blur
  ~gaussiano a bassa risoluzione (STEP ts/4; 3 box blur separabili via somme
  cumulate, _sep_blur, raggio ~0.55 tile), upscalato bilineare a piena
  risoluzione, poi SOGLIA 0.5. Il rumore di bordo (_np_vnoise, ampiezza 0.33) si
  applica SOLO nella fascia di transizione (0.22<bf<0.80): l'INTERNO (bf alto)
  resta SEMPRE pieno e l'ESTERNO (bf basso) sempre vuoto -> contorno irregolare
  pixel-art SOLO al bordo, e NIENTE buchi/fessure nere dentro il muro. CLAMP
  mezzo tile (la COLLISIONE resta sui tile): distanza low-res dai centri-muro
  (_dist_lo); ogni cella entro ~0.42 tile da un centro resta piena (i muri
  piccoli diventano BLOB tondi, non spariscono ne restano rettangoli) e la sagoma
  non sborda oltre ~mezzo tile (allowed, dist<=1.0 tile dal centro).
  _build_jungle_walls riempie la silhouette: cima = roccia mottled chiaro/scuro
  (rumore low-res a strisce, lerp JW_TOP..JW_TOP_HI, avvallamenti verso JW_TOP_SH,
  NON neri) + muschio JW_MOSS/_DK, ritagliata alla sagoma; sopra, per la DENSITA'
  della vecchia texture: tante FACCETTE spigolose _rock_facet (~2-3 per tile:
  piatti + crepe nette + volume), qualche MASSO tondo _round_rock in rilievo e
  fiocchi di muschio. MASSI _round_rock anche lungo il NUOVO contorno (chiari
  verso N/O, scuri verso S/E). PARETE 2.5D (cliff) che segue il bordo sud della
  sagoma (depth per colonna) in tono di ROCCIA (spalla JW_CLIFF_HI in alto ->
  JW_CLIFF in basso, NON nera, cosi non sembra un buco; niente contatto nero: il
  contatto a terra lo da gia il layer ombre). Tutto su un'unica Surface a piena
  mappa, poi blit LAZY per chunk (solo i blocchi con alpha). _build_jungle_shadow:
  ombra proiettata a SUD-EST dalla SILHOUETTE (non dai tile), accumulata a bassa
  risoluzione con alfa calante e upscalata. _build_ao: l'occupazione low-res
  viene dalla silhouette (+ cespugli e pietra per-tile) -> l'AO segue il contorno
  curvo, non piu rettangoli allineati ai tile (risolve il "pilastro" con AO
  quadrata). Il MURO DI CONFINE in pietra (TILE_WALL) e i CESPUGLI restano
  per-tile come prima.
  Rimossi i vecchi builder per-tile dei jungle wall (_jwall_surf/_build_jwall) e
  l'autotiling (_carve_autotile/_autotile_footprint/_mask8); _rock_facet/
  _round_rock/_jitter restano, riusati dalla silhouette. Costo build una-tantum:
  3v3 ~8s, 5v5 ~17s (noise a bassa risoluzione). Correzioni post-revisione (vedi
  sopra: dischi anziche quadrati, rumore solo al bordo, cliff/base in tono di
  roccia, densita' di faccette/massi/muschio): niente piu macchie nere interne,
  basi/bordi curvi che seguono la maschera, superficie meno piatta. Screenshot:
  screenshots/step_9.png (diagonale lungo il fiume) e step_9_over.png (minimappa).
- MURI DI GIUNGLA come RILIEVI pseudo-3D in stile LoL (game/map_renderer.py
  _build_jungle_walls rifatto + nuovo _jungle_components; CANOPY_OUTLINE #12281A):
  la cima NON e' piu roccia ma VEGETAZIONE. (1) CIMA vegetata: griglia di chiome
  (passo ~0.48 tile, solo celle SOLID via meshgrid) dove ogni chioma e' una
  _sphere illuminata alto-sinistra (riuso del mattone 3D dei cespugli); i toni
  salgono dallo scuro al chiaro (tiers BUSH_SHADOW..BUSH_HILITE) per chiazze di
  rumore + bonus "verso la luce" sul bordo NORD del muro; sotto, base uniforme
  BUSH_SHADOW che riempie i buchi; ritaglio alla silhouette; CONTORNO scuro
  #12281A sui lati esposti (dn|rt|lf) e cresta BUSH_RIMLIGHT sul bordo nord (up).
  (2) PARETE frontale (cliff) alzata a ~1 tile (RELIEF = max(H, 0.95*ts), non
  tocca self._H globale): gradiente spalla JW_CLIFF_HI -> JW_CLIFF -> JW_CLIFF_DK
  (piu SCURA in basso), UN solo strato orizzontale tenue a meta, crepe CORTE,
  spezzate e oblique (set_at con serpeggio ~1px: sembrano roccia, NON uno
  steccato come le vecchie verticali piene) + muschio JW_MOSS/_DK sul bordo.
  (3) OVERHANG: le chiome del bordo SUD sporgono nel layer CANOPY (lobi scuri
  sotto-chioma alla base della parete, debordano un filo in basso -> SOPRA le
  unita che passano vicino; azzerate dove c'e la sagoma, non coprono la cima).
  SEED per muro: _jungle_components etichetta le componenti connesse (8-vicini)
  dei tile muro-giungla; da id-componente derivano dimensione/densita'/jitter
  delle chiome -> ogni muro ha forma propria. Ombra proiettata ALLUNGATA a
  sud-est (_build_jungle_shadow: L ~1.3 tile, alfa 105). Via la vecchia cima di
  roccia (mottled + _rock_facet/_round_rock/massi sul contorno): _rock_facet/
  _round_rock ora NON piu usati (restano in renderer.py). Costo build invariato:
  3v3 ~8s, 5v5 ~18s. Screenshot: screenshots/step_10.png (ravvicinato) e
  step_10_over.png (minimappa).
- REVISIONE dei rilievi (step_11), su feedback. (1) CHIOMA ad ALBERI, non piu
  cerchi uniformi (sembrava pluriball): nuovo _draw_tree disegna UN albero come
  gruppo di ciuffi tondi (chioma irregolare) con illuminazione sull'INTERO
  albero (ciuffi basso-destra scuri, alto-sinistra chiari + riflessi); alberi
  GRANDI all'interno e PICCOLI sul bordo via campo distanza-dal-bordo (_dist_lo
  su ~solid, low-res, R cresce con la distanza); passo ~0.76 tile, toni
  BUSH_DARK..BUSH_HILITE + riflessi BUSH_RIMLIGHT. CONTORNO esterno TUTTO scuro
  #12281A (tolta la cresta chiara sul bordo nord: niente verde chiaro sul
  contorno). (2) PARETE piu alta (RELIEF = max(H, 1.12*ts); il margine `top`
  della mappa ora e' max(H, 1.2*ts) cosi la cima estrusa non si taglia in alto):
  DUE strati orizzontali, crepe corte spezzate, muschio e RADICI verde-brune
  (ROOT/ROOT_D) che scendono serpeggiando dalla chioma, base piu SCURA.
  (3) ARTEFATTI rimossi: l'overhang usa _draw_tree (niente piu "ciambelle"
  semitrasparenti delle _sphere) e i suoi centri stanno SOTTO la sagoma (niente
  tagli orizzontali). (4) MURO DI CONFINE unificato: TILE_WALL entra nella
  SILHOUETTE (in _jungle_solid e _jungle_components) e viene reso come
  foresta+scogliera come i muri di giungla; rimossi il vecchio rilievo di pietra
  per-tile (_tall_surf) e la sua ombra per-tile; in _build_ao TILE_WALL non e'
  piu per-tile (viene dalla silhouette curva). (5) NESSUN cespuglio sui muri:
  _jungle_solid RITAGLIA la sagoma via dai tile BUSH (il muro si ferma al confine
  del cespuglio) e i cespugli si disegnano PRIMA dei muri (coperti dove un muro
  li sovrasta). Costo build ~invariato (3v3 ~8s, 5v5 ~19s; densita' alberi
  tarata) nonostante l'area raddoppiata dall'unione di TILE_WALL. Screenshot:
  screenshots/step_11.png (ravvicinato) e step_11_over.png (minimappa).
- CHIOMA densa e con volume (step_12), su feedback (prima: palline piatte su
  fondo nero, "pois"). (1) DENSITA': base della chioma verde MEDIO-SCURO (#1F3B24
  = BUSH_DARK) invece del quasi-nero BUSH_SHADOW, passo tra alberi ridotto a
  ~0.6 tile e alberi piu grandi -> si sovrappongono, restano solo piccole
  fessure d'ombra. (2) VOLUME per albero: _draw_tree rifatto -> 3-4 ciuffi, e
  OGNI ciuffo e' un piccolo rilievo a 3 bande (base/ombra -> corpo -> cappello di
  luce verso alto-sinistra) + riflesso; i ciuffi in basso-destra usano toni piu
  scuri, quelli in alto-sinistra piu chiari -> cupola, non disco piatto con un
  punto. (3) niente piu TAGLI DRITTI: i tile BUSH si scavano dal campo dischi a
  BASSA risoluzione in _jungle_solid PRIMA del blur (non piu `solid &= ~bpx`
  sulla sagoma finale, che lasciava spigoli di griglia) -> il muro si curva
  attorno ai cespugli seguendo la maschera. PRESTAZIONI: gli alberi ora sono
  SPRITE in CACHE (_tree_sprite, _tree_cache: chiave = raggio quantizzato +
  variante 0-7 + palette) disegnati poche decine di volte e BLITTATI a migliaia
  -> build di nuovo ~8s (3v3) / ~17s (5v5) nonostante la densita' molto maggiore.
  Screenshot: screenshots/step_12.png (ravvicinato) e step_12_over.png (minimappa).
- CESPUGLI come ERBA ALTA stile Pokemon (step_13), su richiesta: i cespugli
  NON sono piu palline-chioma come i muri (prima erano indistinguibili dalla
  vegetazione dei muri). Nuovo game/renderer.py _build_bush (rifatto da zero) +
  helper _blade; via _sphere (non piu usato). Ogni tile BUSH e' una macchia di
  LAME a V: niente cerchi, solo triangoli sottili che salgono dalla base.
  (1) Disegno a BASSA RISOLUZIONE (PX = ts//12 px schermo per px logico) su una
  Surface piccola, poi pygame.transform.scale NEAREST a (ts, ts+H) -> pixel
  grossi, look retro (come da CLAUDE.md). (2) PALETTE giallo-oliva CHIARA
  (GRASS_BASE..GRASS_HILITE in renderer.py: base #22361C, lame #38521F/#5C7C2E/
  #86A63C, punte #B8CE5C) scelta apposta per STACCARE dalla chioma scura dei muri
  (BUSH_*): leggibile a colpo d'occhio e in minimappa. (3) Ogni LAMA = triangolo
  col CONTORNO scuro (GRASS_OUT, triangolo piu largo dietro) poi il colore dentro
  -> bordo netto pixel-art. I ciuffi sono VENTAGLI a V (2-4 lame con lean
  crescente). (4) STRATI dal piu' SCURO al piu' CHIARO verso la luce: il colore
  della lama dipende da uno `score` = altezza della punta + bias verso
  ALTO-SINISTRA; le lame si disegnano ordinate per score (retro scuro/corto ->
  fronte chiaro/alto), e il colpo di luce GRASS_HILITE tocca SOLO le punte nella
  meta' superiore e a sinistra. (5) SILHOUETTE irregolare: le punte bucano il
  bordo alto del tile (dentro l'estrusione H), niente cima piatta. (6) Banda di
  base scura che riempie tutta la larghezza (erba continua coi vicini, nessun
  buco tra tile) + ombra di contatto a BASSO-DESTRA solo sui lati esposti (mask).
  Seme per tile (variant) -> ciuffi diversi dai vicini; sprite in cache come
  prima (chiave mask+variant+H). Screenshot: screenshots/step_13.png (ravvicinato,
  erba accanto a un muro per il confronto) e step_13_over.png (minimappa).
- CESPUGLI rifatti a SILHOUETTE (step_14), su feedback allo step_13 (prima:
  rettangoli a scaletta allineati ai tile, fili in righe regolari tipo "lettere",
  colore troppo saturo). Il rendering dei cespugli PASSA da per-tile (renderer.py)
  a LIVELLO MAPPA (game/map_renderer.py): rimossi _bush_surf/_build_bush/_blade/
  _sphere dal Renderer. Nuovi: _bush_solid, _bush_points, _build_bushes,
  _build_bush_shadow, _grass_tuft. (1) FORMA: _bush_solid usa la STESSA tecnica
  dei muri (_jungle_solid): maschera tile -> campo di DISCHI sui centri -> blur
  (_sep_blur) -> soglia 0.5 + rumore (_np_vnoise) SOLO al bordo, con CLAMP ~mezzo
  tile (core/allowed da _dist_lo). Contorno organico che puo' sporgere fino a
  mezzo tile; i tile ISOLATI diventano BLOB tondi (core) e i vicini si FONDONO
  (niente piu' rettangoli; niente chiazze da un solo tile squadrate). (2) CIUFFI:
  _bush_points posiziona le basi con DART-THROWING (Poisson-disc, spaziatura
  ~0.26 tile) dentro la sagoma -> fitti ma senza pattern allineato; si disegnano
  ordinati per y (dal FONDO al DAVANTI: le punte di una fila coprono la base di
  quella dietro). Ogni ciuffo (_grass_tuft, sprite in cache) e' un ventaglio di
  4-6 lame a V di altezze diverse, disegnato a BASSA risoluzione e scalato NEAREST
  (pixel grossi); contorno scuro per lama; colore per altezza della punta
  (dal basso al chiaro) e POCHE punte col colpo di luce in cima. (3) COLORE
  desaturato oliva come richiesto: base #3E5228 (GR_BASE), medio #6B7F3A (GR_MID),
  chiaro #8A9A48 (GR_LIGHT), punte #A8B560 (GR_TIP) -> distinguibile dalla chioma
  scura dei muri ma integrato nella palette. (4) VOLUME: riempimento della sagoma
  con gradiente verticale (piu' chiaro in cima, piu' SCURO in basso), ombra
  morbida a terra verso BASSO-DESTRA (_build_bush_shadow, nel layer shadows) e
  bordo inferiore irregolare (rumore della maschera). AO (_build_ao) e la silhou-
  ette dei muri (_jungle_solid) ora SCAVANO attorno ai cespugli con un campo
  distanza (disco), non piu' per-tile: il muro si CURVA attorno all'erba (niente
  bordi dritti dove si toccano) e l'AO segue il contorno curvo dei cespugli.
  (5) BONUS vento: le punte possono OSCILLARE (GRASS_FRAMES fotogrammi, punte
  sfalsate di ~1px). Di DEFAULT GRASS_FRAMES=1 -> erba STATICA nel layer
  walls_base (ZERO memoria extra, come prima): ogni fotogramma in piu' e' un layer
  a se e MOLTIPLICA la memoria dell'erba (3v3: ~+22MB/frame), contro il budget di
  memoria del progetto. Alzando GRASS_FRAMES a 2-3 si abilita il vento (i punti
  Poisson si calcolano una volta e si riusano; in draw() si fa solo il blit del
  fotogramma corrente scelto da get_ticks). Costo build 3v3 ~10s. Screenshot:
  screenshots/step_14.png (ravvicinato, erba accanto a un muro) e step_14_over.png
  (minimappa: erba oliva-chiara vs chioma muri scura).
- CESPUGLI come MASSA COMPATTA stile MOBA (step_16), su feedback (step_14 e un
  tentativo intermedio a tile 16x16 disegnati a mano risultavano "piatti/una fila
  di punte": non si leggeva un'AREA). Rifatto a LIVELLO MAPPA in game/map_renderer.py
  (_bush_solid, _grass_tuft, _build_bushes, _px1); palette SMERALDO FREDDA nuova
  (GB_FILL #16402E, GB_OUT #0F2A20, GB_DARK #1E5A3F, GB_MID #2F7D5B, GB_LIGHT
  #4FA36E, GB_TIP #8FD08A), distinta dalla chioma dei muri anche in minimappa.
  (1) AREA: _bush_solid = stessa maschera organica dei muri (dischi sui centri ->
  blur -> soglia + rumore SOLO al bordo, clamp ~mezzo tile): tile isolati -> blob,
  vicini fusi. (2) FONDO PIENO scuro GB_FILL su tutta la sagoma (gradiente un filo
  piu' scuro in basso = ombra interna) col CONTORNO GB_OUT tutt'intorno (anello =
  dilatazione-sagoma): niente terreno visibile dentro. (3) SUPERFICIE: file di
  CIUFFI (_grass_tuft, sprite in cache: 2-3 lame a punta, corpo+cappello chiaro,
  contorno scuro) ogni ~5px, SFALSATE (stagger), scansione per riga VETTORIALE
  (solo celle della sagoma; seme da hash -> veloce), disegnate dal fondo (y
  piccola) al davanti; tier piu' CHIARO verso ALTO e SINISTRA (luce alto-sx), con
  GB_TIP solo qua e la'. (4) FRONTE: sotto il bordo inferiore uno SKIRT (fascia
  piu' scura, altezza da rumore ~0.2-0.5 tile) + fili (_px1) piu' lunghi e scuri
  che SCENDONO oltre il contorno e si scuriscono verso la punta -> l'area ha
  ALTEZZA come la parete dei muri. (5) OMBRA morbida a terra (sagoma spostata a
  sud-est, corta, sfumata) nel layer shadows. Resta nel layer walls_base PRIMA dei
  muri (un muro sovrapposto copre). _jungle_solid scava ancora attorno ai cespugli
  con campo-distanza (muro curvo attorno all'erba); _build_ao li include per-tile.
  Rimossi _bush_tile/GRASS_FULL/GRASS_EDGE (tentativo a tile a mano) dal Renderer.
  Attivo su ENTRAMBE le mappe (3v3 e 5v5). Costo build +~2s (profilato),
  memoria invariata (3v3 140MB). Screenshot: step_16.png (ravvicinato erba+muro),
  step_16_3v3.png/step_16_5v5.png (zone reali) e step_16_3v3_over.png/
  step_16_5v5_over.png (minimappe).
- FIUME rifatto a LIVELLO MAPPA (step_17), prima era per-tile nel Renderer
  (_paint_water + rive per-tile in _shore). Nuovo game/map_renderer.py:
  _water_solid, _build_river, _scatter_river, _draw_reeds/_draw_lily/_draw_rock,
  _build_foam, _draw_foam. (1) BORDI SMUSSATI (autotiling implicito): _water_solid
  usa la STESSA tecnica di muri/cespugli (maschera tile -> dischi sui centri ->
  blur _sep_blur -> soglia 0.5 + rumore SOLO al bordo, clamp ~mezzo tile) -> rive
  curve e organiche, niente scaletta per-tile; la collisione resta sui tile.
  (2) PROFONDITA': gradiente dal campo-distanza dall'acqua alla terra (_dist_lo):
  bordi CHIARI (RIV_EDGE bassofondo) -> centro SCURO (RIV_DEEP), lerp a 3 stop
  (EDGE->MID->DEEP). (3) CORRENTE: sottili increspature = cresta di un seno
  diagonale deformato da rumore (sin^3), tenui e assenti sul bordo (niente grandi
  riflessi). (4) RIVA sfumata: alfa dell'acqua che SFUMA sulla riva (l'erba
  traspare al contatto: i tile fiume lasciano il suolo di giungla sotto, come i
  muri) + banda di FANGO bagnato sul lato terra (SHORE_WET2->SHORE_MUD2 dal
  campo-distanza dalla terra all'acqua) + CANNE (steli sottili verdi con punta
  illuminata, griglia fine lungo il bordo). (5) SCHIUMA ANIMATA: anello ~2px sul
  bordo interno (erosione della silhouette), spezzato in trattini da un rumore
  mosso di fase -> FOAM_FRAMES=3 fotogrammi pre-renderizzati; in draw() si sceglie
  il fotogramma da get_ticks (FOAM_MS=240) e si blitta tra ground_decor e shadows
  (sotto le unita). Sprite di schiuma per CELLA (FCELL=256, bbox stretto) -> poca
  memoria (niente 3 layer-chunk interi lungo la diagonale). (6) NINFEE e SASSI
  RADI (griglia LARGA ~2.3 tile, pochi): ninfea = foglia ellittica con bordo
  scuro + colpo di luce + tacca, raro fiore; sasso = Renderer._round_rock (luce
  alto-sx) con tenue anello di schiuma. Tutto STATICO nel layer decor (una volta,
  poi solo blit), tranne la schiuma. Il Renderer._shore NON genera piu' la riva
  per-tile del fiume (TILE_RIVER tolto dal set `water`); _paint_water/_shore
  restano per la pozza dinamica (TILE_PUDDLE, Pioggia). Costo build: 3v3 ~+?s,
  invariato in pratica (noise a bassa risoluzione, sprite in loop vettoriali).
  Screenshot: step_17.png (sintetico ravvicinato), step_17_3v3.png/step_17_5v5.png
  (zone reali), step_17_3v3_over.png/step_17_5v5_over.png (minimappe),
  step_17_foam0.png/step_17_foam1.png (due fotogrammi della schiuma).

Scelte tecniche importanti:
- canopy NON e' piu del tutto vuoto: porta l'OVERHANG delle chiome dei muri sul
  bordo sud (sopra le unita, vedi passo rilievi pseudo-3D). lighting_overlay
  porta il velo d'atmosfera (chioma + luce campi). La vignettatura e'
  screen-space e vive in draw_canopy, fuori dai layer. I CESPUGLI (TILE_BUSH)
  sono una MASSA COMPATTA di erba alta stile MOBA, resa a LIVELLO MAPPA come
  silhouette organica a fondo pieno + ciuffi + fronte (map_renderer:
  _bush_solid/_build_bushes, vedi step_16), con palette smeraldo DIVERSA dai muri
  (distinguibili a colpo d'occhio e in minimappa). Stanno nel layer walls_base e
  si disegnano PRIMA dei muri, quindi un muro che li sovrasta li copre.
- TILE_WALL (muro di confine) NON e' piu reso come pietra per-tile: e' entrato
  nella silhouette vegetata dei muri (foresta+scogliera). I builder di pietra
  (_tall_surf/_paint_stone_tall) e _rock_facet/_round_rock restano in
  renderer.py ma non sono piu usati dalla mappa. Lo sprite della LANE resta
  costruito dal Renderer; i cespugli sono ora erba alta (step_13) e il FIUME
  (TILE_RIVER) e' reso a livello mappa (map_renderer._build_river, step_17): sotto
  i tile fiume resta il suolo di giungla e l'acqua ci si sfuma sopra. Resta nel
  Renderer _paint_water/_shore solo per la pozza dinamica (TILE_PUDDLE, Pioggia).
- Offset camera: camera.snap() arrotonda l'offset a interi UNA volta per
  frame (camera.ox/oy); mappa e unita (world_to_screen) usano lo stesso
  valore -> niente tremolio di 1px ne seam tra chunk su scroll sub-pixel
  (verificato: chunk == rendering monolitico, scarto 0).
- Il margine superiore `top` (= altezza estrusione H) nei layer serve ai
  rilievi 2.5D che sporgono sopra la riga 0.
- I layer sono grandi quanto la mappa; `ground` e pieno per natura, quindi
  su mappe dense il chunking rende poco oltre ai layer riservati lazy.
