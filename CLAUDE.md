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
- SOTTOBOSCO: decorazioni sparse sul layer ground_decor (step_18). Nuovo
  game/map_renderer.py _build_decor + helper (_pick_decor/_draw_decor/_deco_leaf/
  _deco_rock/_deco_fern/_deco_mushroom/_deco_root/_deco_log/_safe_px); palette
  dedicata (LEAF_*, DROCK_*, FERN_*, MUSH_*, ROOT_*, LOG_*). Oggetti SENZA
  collisione (solo cosmetici): foglie secche, sassi di terra, felci, funghi,
  radici affioranti e tronchi caduti. (1) DENSITA' modulata dalla distanza dalle
  SILHOUETTE di muri+cespugli (campo distanza low-res _dist_lo -> smoothstep):
  spaziatura PICCOLA a ridosso dei muri (sottobosco fitto al margine), GRANDE in
  campo aperto; ZERO su lane e sentieri (maschera dai TILE_FLOOR meno path_tiles)
  e mai dentro la sagoma di muri/cespugli (che sborda ~mezzo tile). (2) POISSON-
  DISC a raggio variabile: griglia jitterata visitata in ordine casuale +
  rifiuto per vicinanza (hash spaziale a celle r_far, controllo 3x3; raggio =
  max(sp_candidato, sp_vicino)) -> distribuzione blue-noise, niente
  sovrapposizioni ne pattern. I TRONCHI riservano piu' spazio (sp>=1.3 tile).
  (3) MIX per contesto (_pick_decor): vicino ai muri piu' radici/felci/funghi/
  tronchi; in aperto soprattutto foglie e sassi. (4) Sprite pixel-art con luce
  alto-sinistra: felce = ventaglio di fronde con pinnule e punta chiara; fungo =
  gambo chiaro + cappello a cupola (rosso o bruno) con riflesso; tronco = capsula
  di corteccia con cima illuminata, fondo in ombra, anelli e muschio + ombra di
  contatto; sasso = Renderer._round_rock; radice = bastoncino nodoso serpeggiante;
  foglia = rombo bruno col contorno scuro e nervatura. Disegnate su una Surface a
  piena mappa, poi blit LAZY per chunk (solo i blocchi non vuoti). Nessuna memoria
  extra apprezzabile; costo build una-tantum ~qualche secondo (loop Poisson).
  Attivo su ENTRAMBE le mappe. Screenshot: screenshots/step_18.png (ravvicinato
  erba+muro) e step_18_over.png (minimappa 3v3); step_18_5v5.png/
  step_18_5v5_over.png (5v5).
- PARTICELLE D'ATMOSFERA (step_19): particelle leggere e COSMETICHE nelle zone di
  giungla. Nuovo game/particles.py (classe ParticleSystem), integrato in
  game/scenes/match_scene.py (creazione in __init__, update in update(), draw in
  draw() DOPO renderer.draw -> sopra mappa/unita, sotto gli effetti delle mosse e
  la UI). Tre tipi: (1) LUCCIOLE = puntini caldi che fluttuano piano e PULSANO
  lentamente (sin lenta su una fase per-particella), alone radiale morbido con
  nucleo quasi bianco; (2) POLLINE = minuscoli granelli chiari che derivano
  nell'aria con leggera oscillazione; (3) FOGLIE = qualche foglia (ellisse con
  nervatura) che CADE ondeggiando e ruotando. VINCOLI rispettati: (a) al massimo
  ~60 a schermo (MAX_PARTICLES=60); (b) aggiornate SOLO dentro la camera -> si
  generano nel rettangolo visibile e, appena ne escono (oltre MARGIN px) o finita
  la vita, vengono riciclate; (c) nascono SOLO su tile di giungla (TILE_FLOOR/
  TILE_BUSH), mai su lane, acqua o muri -> se la vista inquadra poca giungla se ne
  generano meno. Dissolvenza in entrata/uscita (_fade) per evitare il 'pop'.
  PRESTAZIONI (requisito: calo FPS < 5%): niente allocazioni per-frame; gli
  sprite sono PRE-RENDERIZZATI una volta (alone e polline a GLOW_LEVELS=6 gradini
  di luminosita' -> blit SRCALPHA veloce, niente set_alpha sul percorso di blend
  lento; foglie ruotate in cache per angolo quantizzato a 16 passi; set_alpha solo
  durante la dissolvenza). Hot loop di update/draw con variabili locali e
  world_to_screen inline (ox/oy del frame). Benchmark headless (MatchScene reale,
  A/B interlacciato ON/OFF, camera che PANORAMICA ogni frame = caso peggiore di
  spawn/riciclo, scaling lowres->finestra incluso): costo isolato ~55 us/frame,
  CALO FPS misurato ~4.0-4.3% su 5 run (baseline headless piu' leggera del frame
  reale, quindi il calo in gioco e' minore; al cap di 120 FPS con margine e'
  ~0%). Screenshot: screenshots/step_19.png (giungla illuminata, senza nebbia) e
  step_19_zoom.png (dettaglio lucciole/polline accanto al fiume).
- PARTICELLE anche in MULTIPLAYER (step_20): le particelle d'atmosfera, prima
  solo su MatchScene (gioco locale), ora girano IDENTICHE anche su
  game/scenes/net_match_scene.py (partita online). Aggiunto ParticleSystem al
  NetMatchScene (creazione in __init__, update in update() con map_data.grid,
  draw in draw() DOPO renderer.draw -> sopra mappa/unita, sotto il mirino e la
  UI), stesso ordine della scena locale. Il resto della grafica della giungla
  (suolo, muri, cespugli, fiume, sottobosco, chioma, luci, nebbia, minimappa)
  era GIA' condiviso: entrambe le scene usano lo stesso Renderer/MapRenderer, le
  uniche due istanze di Renderer() nel progetto. La griglia online cambia col
  meteo (_sync_terrain): le particelle leggono grid.tiles live e nascono solo
  su TILE_FLOOR/TILE_BUSH, quindi seguono il terreno aggiornato. Nessun costo di
  memoria extra sul percorso di rete (sprite pre-renderizzati, <=60 particelle).
- LEGGIBILITA' COMBATTIMENTO (step_21): gittata delle torri nemiche + proiettili
  dei minion a distanza + sfera d'energia delle torri (stile LoL), tutto COSMETICO.
  GITTATA definita in "unit" stile LoL: config.TOWER_RANGE = TOWER_RANGE_UNITS(750)
  / UNITS_PER_TILE(125) = 6.0 tile. La passa match._build_structures a spawn_tower
  (default world.spawn_tower allineato a 6.0); renderer _TOWER_RANGE_DEFAULT =
  config.TOWER_RANGE (fallback in rete, dove le Structure non portano attack_range).
  (1) GITTATA TORRI: Renderer.draw_tower_ranges disegna attorno a OGNI torre nemica
  viva un cerchio di pericolo (decalco rosso translucido + anello rosso pulsante,
  sin su `now`); appare solo quando il giocatore e' vicino al bordo (near=6 tile, da
  player_pos), cosi "sai dove fermarti". Chiamato da match_scene.draw e
  net_match_scene.draw dopo renderer.draw (sopra la mappa). (2) EVENTI FX
  (engine/match.py _try_attack): oltre al colpo dei Pokemon, emette anche
  "tower_shot" (torre, con team) e "minion_shot" (solo minion caster/cannone, con
  team e `big` per il cannone); i melee NON sparano. Eventi COSMETICI (lista
  fx_events, il danno resta istantaneo: nessun cambio di logica). (3) DISEGNO
  (game/fx.py): MINION_SHOT_COLORS/TOWER_SHOT_COLORS colorano per SQUADRA (blu=0,
  rosso=1, non per tipo). Nuova forma "shot" in _draw_shapes: proiettile OPACO e
  netto (sfera piena alfa 255 + contorno scuro _darken + luce in alto-sinistra),
  SENZA particelle/scia; dissolve solo nell'ultimo 22% di vita. _minion_shot = shot
  piccolo (0.18) o piu' grosso per il cannone (0.26); _tower_shot = shot MOLTO piu'
  grande (0.8) con alone luminoso (glow 0.7). NOTA: la scena di rete non trasmette
  ancora gli fx_events, quindi li' si vede la gittata delle torri ma non (per ora)
  i proiettili. Screenshot: screenshots/step_21.png (vista), step_21_zoom.png
  (ravvicinato: sfera torre grande + pallini opachi blu/rossi + anello gittata) e
  step_21_over.png (mappa).
- TORRI OUTER DI MID piu' indietro (3v3), cosi il centro della lane mid non e'
  coperto dalla gittata (step_22). Con range 6.0 tile gli outer di mid stavano a
  ~6.5 tile dal centro -> le due gittate si toccavano quasi al centro. Spostati a
  ~9.2 tile dal centro -> corridoio neutro aperto di ~6 tile. tools/gen_map_3v3.py:
  nuovo MID_OUTER_FRAC = {0: 0.415, 1: 0.585} usato SOLO per lane mid + name outer
  (top/bot restano a 0.44/0.56: erano gia' a ~9 tile dal rispettivo angolo).
  data/maps/map_3v3.json rigenerato (solo le 2 torri outer di mid cambiano pos:
  [45.4,54.6]->[43.5,56.5] e [54.6,45.4]->[56.5,43.5], entrambe su tile LANE).
  Il 5v5 non serviva (lane piu' lunga: outer gia' a ~9.8 tile dal centro).
  Screenshot: screenshots/step_22_mid.png (mid con le due gittate e il centro aperto).
- TORRI, BASE e PROIETTILI rifatti (step_23). Nuovo game/structure_gfx.py
  (sprite pixel-art a risoluzione nativa, in cache; a frame solo blit + piccoli
  ritocchi animati). (1) TORRE uguale per tutti, 2.5D come i pilastri di Gigalith
  (stessa pietra ST_*): plinto ottagonale ESTRUSO (cima chiara, facce frontali a
  bande luce|medio|ombra), fusto rastremato a blocchi sfalsati con crepe e
  muschio, capitello estruso con fascia d'oro e tre punte, contorno scuro da
  dilatazione della maschera (_outline). GEMMA sfaccettata che fluttua sopra
  (bob + alone a gradini che pulsa + scintilla in orbita): BLU squadra 0, ROSSA
  squadra 1 (GEMS); runa dello stesso colore incastonata nel fusto. Ombra di
  contatto + ombra lunga verso basso-destra. Torre distrutta = moncone spezzato
  con macerie (resta disegnata). Ordinata in profondita' con le unita'.
  (2) BASE di spawn (Core) = piattaforma PIATTA di pietra (raggio 2.2 tile):
  bordo frontale 2.5D, due corone di lastre (per-pixel con numpy, tono per
  lastra), smusso luce/ombra, disco interno con cornice d'oro, anello di rune e
  gemma del nucleo ottagonale sfaccettata; 4 cristalli di squadra. Si disegna
  PRIMA di tutte le unita' (renderer._draw_entities), quindi chi rinasce o fa
  shopping sta SOPRA la base; le rune pulsano (strato _rune_glow con set_alpha).
  (3) PROIETTILI di ENERGIA (fx.py, forma "energy" + "flash"): testa a 3 strati
  (alone tremolante, corpo, nucleo quasi bianco), coda a cometa, scia di bolle e
  due scintille; il colpo della torre parte dalla GEMMA (lift_a =
  structure_gfx.gem_height_tiles()) e arriva al busto del bersaglio; all'arrivo
  lampo + anello d'impatto (forme con wait = durata del volo). Minion: stessa
  forma, piu' piccola. La scena di rete ora passa `now` al renderer (gemme e rune
  animate anche online). (4) COLLISIONE: le torri vive sono ostacoli fisici
  (engine/movement.resolve_obstacles, chiamata da World.tick; raggio
  config.TOWER_BLOCK_RADIUS = 0.85 tile, distinto dal raggio di bersaglio 1.1):
  spinta radiale -> si scivola lungo il bordo, spinta laterale se si punta dritto
  al centro, waypoint dentro la torre = raggiunto. Il Core NON blocca.
  Screenshot: step_23_blu/_rossa/_zoom (torri), step_23_base (base con le unita'
  sopra), step_23_colpi/_colpi_zoom/_impatto/_impatto_zoom (proiettili),
  step_23_macerie (torre distrutta).
- SPRITE dei LEGGENDARI neutrali (step_24): Kyogre (0382), Groudon (0383), Rayquaza
  (0384) e Arceus (0493), da PMD Sprite Collab, in assets/pokemon/<dex>/. Nuovo
  game/sprites/spritesheet.py wild_legend_sprite(unit) -> (cartella, scala): kind
  "meteo" sceglie dal `weather` (rain/sun/wind), kind "arceus" fisso; i campi
  normali restano col cerchio colorato. match_scene._make_animator e
  net_match_scene._net_animator usano SpriteAnimator con quella scala (1.3/1.25/
  1.0/1.3, piu grandi dei campioni). Nessuna logica toccata. Screenshot:
  screenshots/step_24.png.
- SPRITE sui CAMPI della giungla lato BLU (step_25/26), solo grafica: la tabella
  _CAMP_SPRITES in game/sprites/spritesheet.py mappa il tile del campo -> lista di
  membri (cartella, scala, dx, dy). Settore alto: Slowbro (0080, grosso/blue buff),
  Carnivine (0455, piccolo a nord-ovest), 3 Tangela (0114). Settore basso: Magmortar
  (0467, grosso/red buff), 1 Ariados (0168) + 3 Spinarak (0167, scala 0.6) a sinistra,
  2 Hoppip (0187) sotto. Stessa disposizione su 3v3 e 5v5; i campi rossi restano
  cerchi. make_wild_animator(unit, load) serve leggendari e campi in entrambe le
  scene; i gruppi usano GroupAnimator (animator.py): l'unita resta UNA (un solo HP/
  bersaglio), i compagni sono sprite cosmetici a offset fissi, disegnati ordinati
  per y. Screenshot: step_25_alto/basso, step_26_tangela/ragni/hoppip.
- NEGOZIO a SCHEDE con ICONE (step_27), insieme al nuovo catalogo oggetti a 3
  livelli (data/items.json; effetti in engine/item_effects.py). game/shop_ui.py:
  schede Consigliati + categorie di items.json (Vitamine, Intermedi, Fisici,
  Speciali, Ibridi, Combattenti, Tank, Supporto, Utilita') su due righe, griglia
  a 3 colonne, dettagli (statistiche, ricetta, effetto) al passaggio del mouse,
  ricarica degli attivabili sugli slot. ICONE da assets/items/<icon>.png
  (tools/fetch_items.py, PokeAPI/sprites, (c) The Pokemon Company): ritagliate
  al bordo trasparente e scalate x2 NEAREST, in cache per (id, dimensione); se
  il file manca, segnaposto colorato con l'iniziale. Screenshot:
  step_27_negozio/_combattenti/_tank_dettagli/_segnaposto (headless 1280x720)
  e step_27_in_partita.
- LINEA ROOKIDEE > CORVISQUIRE > CORVIKNIGHT (step_28), grafica nuova in
  game/corvi_fx.py (logica in engine/corviknight.py). Sprite PMD Sprite Collab in
  assets/pokemon/0821/0822/0823. Effetti istantanei registrati in
  FXSystem._FX_STYLES (**corvi_fx.STYLES) e forme nuove in _draw_shapes
  (corvi_fx.SHAPES: becco a due valve che scatta, piuma, ala d'acciaio): Beccata
  = becco + tratti d'urto; Perforbecco = scia ventosa a "trivella" (tratti obliqui
  alternati) + becco in punta + piume; Spennata = schiaffo d'ala + piume strappate;
  Fulmisguardo/Provocazione = cono rosso (+ ali spalancate); Baldeali = picchiata
  azzurra + ali + polvere. Disegni PERSISTENTI (game/world_fx.py): corrente di
  Ventoincoda (corsia chiara con strisce di vento che scorrono, draw_tailwind) e
  Taxi Volante (mirino d'atterraggio visibile ANCHE ai nemici, anello di carica e
  ali sul lanciatore, poi traiettoria tratteggiata; in volo le due unita' salgono
  con air_z, picco 1.3 tile). Sulle unita' (renderer -> corvi_fx.draw_unit_overlay):
  "!" rosso pixel-art sopra la barra HP dei provocati, nido di rametti durante
  Trespolo. HUD: icona occhio (Sguardofermo) / scudo a specchio (Specchiarmatura).
  Online: tailwinds in net/visual.LISTS, taxi_flights mandati a entrambe le squadre.
  Screenshot: step_28_rookidee/_corvisquire/_corviknight, _hud, _beccata,
  _perforbecco, _spennata, _provocazione, _provocato, _ventoincoda, _taxi_carica/
  _volo/_atterraggio, _baldeali, _trespolo, _draft_corviknight, _selezione.
- LINEA CHARCADET > ARMAROUGE / CERULEDGE (step_29), grafica nuova in
  game/charcadet_fx.py (logica in engine/charcadet.py). Sprite PMD Sprite Collab
  in assets/pokemon/0935/0936/0937. Forme nuove in _draw_shapes
  (charcadet_fx.SHAPES): lingua di fuoco a tre strati (flametongue), goccia di
  lava a parabola con ombra a terra (lavablob), tre graffi d'ombra (claw),
  mezzaluna di fendente (crescent), spadina orbitante (sword). Lavasbuffo =
  cratere + gocce di lava + colonna di fumo; Bruciatutto = ventaglio di fiamme
  piccole e varie (+ schegge se rompe uno scudo); Nitrocarica = fiamme sfalsate
  lungo lo scatto; Calmamente/cure = puntini che risalgono (NON _rise: bolle
  grosse che coprivano lo sprite). Disegni PERSISTENTI (world_fx): ombra di Ombra
  Notturna che scivola a terra con la scia, nube di Pulifumo, carica di Armor
  Cannon (braci risucchiate + mira tratteggiata), area di Psichico che si chiude,
  raffica di mezzalune della Lama dei Rancori; la palla di Armor Cannon in volo
  e' in draw_projectiles (proiettile con "fx"). Sulle unita'
  (charcadet_fx.draw_unit_overlay): 3 spallacci in orbita (incrinati quelli gia'
  usati), artigli viola sulle mani con Ombrartigli, aura di Calmamente. HUD:
  Armature = ritratto della forma verso cui va + barre F/I; Guardia = scudo
  (ricarica); Doppia Lama = spade incrociate. Online: shades/smogs/
  cannon_charges/psy_zones/flurries in net/visual.LISTS, armor_blocks in
  UNIT_FLAGS, barre arrotondate in "me". Screenshot: step_29_* (forme, hud_*,
  ogni mossa, draft_charcadet).
- LINEA NOIBAT > NOIVERN (step_30), grafica nuova in game/noivern_fx.py
  (logica in engine/noivern.py). Sprite PMD Sprite Collab in
  assets/pokemon/0714/0715. Forme nuove in _draw_shapes (noivern_fx.SHAPES):
  arco d'onda sonora a tre strati (soundarc, anche a zig-zag per Stridio),
  onda in volo ")))" (sonicbolt: attacco base e Supersuono), lama d'aria
  (airblade), raggio di Dragopulsar (dragonbeam: corpo viola che pulsa,
  nucleo chiaro, anelli che scorrono; NON il "beam" generico, che a strati
  sembrava una banda piatta), scia di vento sottile (windline: Acrobazia e
  respinte di Turbine, niente bande larghe), cratere di meteora (crater: al
  posto dei "flash", che sembravano macchie sfocate), folata (gust).
  Disegni PERSISTENTI (world_fx): ping di Ecolocalizzazione (bordo tratteggiato
  verde acqua + increspature), Tifone (IMBUTO: silhouette piena traslucida
  stretta in basso e larga in alto con contorno scuro e strisce che girano
  sul lato davanti; la prima versione a anelli impilati sembrava una molla),
  Dragobolide in arrivo (cerchio che si chiude + meteore dall'alto a destra).
  Sulle unita': 3 tacche delle cariche del ping SOTTO la barra della vita,
  visibili a tutti (renderer._draw_unit_hp -> noivern_fx.draw_echo_pips; online
  si riconosce dal dex 714/715 perche' il passive_id degli altri non arriva).
  Dentro il Tifone i nemici ripetono l'animazione Hurt (eventi "anim" ogni
  0,2 s). HUD: Ecolocalizzazione = tre onde accese quante le cariche + avviso
  del calo d'Att. Sp. di Dragobolide. VISIONE: VisionSystem.reveals (squadra ->
  zone x,y,r) rende visibili i nemici dentro anche in nebbia, cespuglio o
  invisibili; online i ping arrivano in net/visual.LISTS e la scena li rimette
  in reveals (altrimenti il client li rinasconderebbe). Corretto anche un bug:
  la partita offline non passava attack_fx allo spawn (le frecce di Rowlet
  non si vedevano offline). Screenshot: step_30_* (forme, hud, ogni mossa,
  ping, tifone/_pioggia, dragobolide/_arrivo, draft_noibat).
- LINEA TEDDIURSA > URSARING > URSALUNA (step_31), grafica nuova in
  game/ursa_fx.py (logica in engine/ursaring.py). Sprite PMD Sprite Collab in
  assets/pokemon/0216/0217/0901. Forme nuove in _draw_shapes (ursa_fx.SHAPES):
  tre artigliate AFFUSOLATE (claw3: spesse al centro, a punta ai capi; le
  prime a tratto pieno sembravano bande), pugno arancione che cala dall'alto e
  si schiaccia (fist), crepe a terra irregolari (groundcrack: lunghezze e
  angoli casuali, altrimenti sembrano i raggi di una ruota; "crack" esisteva
  gia' in fx.py), onda d'urto schiacciata in prospettiva (groundring), sassi
  che saltano (pebble), vasetto di miele (honeypot), luna (moonglow, alta
  sopra la barra della vita). Disegni PERSISTENTI (world_fx): nuvola di
  Profumino (macchie oro/rosa tenui + bordo tratteggiato + cuoricini che
  salgono; con il fondo pieno sembrava un disco piatto), Terremoto (area a
  trattini, crepe CORTE attorno ai piedi che tremano), balzi (cerchio
  d'atterraggio di Luna Piena visibile a tutti, online compreso). Sulle unita':
  vasetti di miele sotto la barra della vita (visibili a tutti; online dal dex
  216/217/901), Luna Piena = sprite x1,3 (SpriteAnimator.draw grow=, NEAREST in
  cache) con alone lunare e barra della vita piu' in alto, Z di Riposo a
  destra della barra, vena rossa + anello quando Dentistretti e' attivo. Chi
  dorme (sonno o Riposo) usa l'animazione Sleep (SpriteAnimator.pose, in
  entrambe le scene). HUD: Miele = tre vasetti + ricarica, sopra
  "Dentistretti" che si accende di rosso. Online: honey_zones/quakes in
  net/visual.LISTS, bear_leaps a parte (Luna Piena a entrambe le squadre),
  honey/guts_active in UNIT_FLAGS; la scena di rete rimette le nuvole di
  Profumino in vision.reveals. Screenshot: step_31_* (linea, hud_*, ogni
  mossa, lunapiena_balzo/_grande, draft_teddiursa).
- LINEA SNEASEL > WEAVILE / SNEASLER (step_32), grafica nuova in
  game/sneasel_fx.py (logica in engine/sneasel.py). Sprite PMD Sprite Collab in
  assets/pokemon/0215/0461/0903. Forme nuove in _draw_shapes (sneasel_fx.SHAPES):
  scheggia di ghiaccio in volo con scia di brina (iceshard), fendente buio
  SOTTILE e un filo curvo (darkslash: le prime versioni larghe sembravano una
  banda piatta), moneta/sfera che vola ad arco (coin: Furto, Arraffalesto),
  cristallo di brina (flake), punta velenosa che scatta (stab), stella
  d'impatto (impactstar: Picchiaduro, Agguato). Riusa le forme di Charcadet
  (claw, sword), Teddiursa (claw3, groundcrack, groundring, pebble, zzz) e
  Noibat (windline, soundarc). Disegni PERSISTENTI (world_fx): palla di fango di
  Sporcolancio in volo ad arco con mirino che si chiude, poi pozza tossica che
  ribolle; balzi di Sneasler (mirino di roccia sul bersaglio dell'Agguato,
  ombra d'arrivo dello scavalcamento; il salto e' air_z). Sulle unita':
  cuoricino verde spezzato (bitmap 7x6) a sinistra della barra per le CURE
  RIDOTTE (nuovo stato generico healcut_until/_mult, applicato in
  _heal_in_mult) + pallino rosso tra gli stati; triangolini cremisi sotto la
  barra per Arraffalesto (in giu' sul derubato, in su su Weavile); ombra che
  fuma sotto Weavile in Notte Fonda (gli alleati lo vedono traslucido). HUD:
  Sole e Luna = LUNA (verso Weavile, parita' compresa) o SOLE (verso
  Sneasler) + contatori "Minion"/"Neutr."; Arraffalesto = artigli + 5 tacche;
  Scalaroccia = roccia con l'arco del salto + ricarica. Online: claw_leaps/
  beatups/sludge_lobs in net/visual.LISTS, snatch_down/up in UNIT_FLAGS, oro
  dei contatori e climb_ready_at in "me". Launcher gioca_weavile/_sneasler
  usano --oro (stesso meccanismo di --armature). Screenshot: step_32_* (linea,
  hud_*, ogni mossa, scalaroccia/_dopo, agguato_balzo, sporcolancio_volo/
  _pozza, draft_sneasel).
- LINEA MIENFOO > MIENSHAO (step_33), grafica nuova in game/mien_fx.py
  (logica in engine/mienshao.py). Sprite PMD Sprite Collab in
  assets/pokemon/0619/0620. Forme nuove in _draw_shapes (mien_fx.SHAPES):
  manica a frusta (sleeve: nastro affusolato che ONDEGGIA con il polsino rosa
  in punta; la prima versione quasi dritta sembrava un bastone), palmo aperto
  di Bruciapelo (palm, disegnato DOPO lo scoppio dello stordimento, altrimenti
  sparisce sotto), occhio di Individua che si apre e si chiude (eye),
  stellina a 4 punte del punto dolce (twinkle, sopra il bersaglio), nastri
  che girano in prospettiva (ribbons: Danza delle Maniche), lucchetto
  (padlock). Riusa impactstar (Sneasel), groundring/groundcrack/pebble
  (Teddiursa), windline (Noibat), hexshell (Guardia Rapida). Contrattacco
  sposta l'attaccante SENZA _item_push (quello emette un evento "dash"
  generico = banda grigia larga). Disegni PERSISTENTI (world_fx): mirino
  d'atterraggio di Calcinvolo (area d'impatto che si chiude). Sulle unità
  (visibili a tutti): guardia di Individua (anello chiaro con raggi), nastri
  della Danza, lucchetto a destra della barra della vita (OGGETTI
  DISATTIVATI, nuovo stato generico itemlock_until: gli effetti unici
  passano da _fx_items, le statistiche restano) + pallino viola tra gli
  stati, crocette verdi di Rigenergia ai lati, scintilla del brutto colpo
  pronto. Solo sul proprio Pokémon: FASCIA del punto dolce (dal 70% al 100%
  della portata, CERCHI come la gittata, non ellissi: la distanza in logica e'
  circolare). HUD: maniche incrociate, barra della calma (verde con
  Rigenergia), palmo giallo = Bruciapelo stordisce, durante la Danza le
  caselle Q W E accese e il tempo. Online: mien_leaps in net/visual.LISTS,
  mien_regen in UNIT_FLAGS, fakeout_ready/dance_seq/mien_calm_at in "me"; la
  fascia del punto dolce si ricava dal dex (619/620). Screenshot: step_33_*
  (linea, hud_*, ogni mossa, calcinvolo_volo/_vuoto, parata, rigenergia,
  danza/_finale, draft_mienfoo).
- LINEA DURALUDON > ARCHALUDON (step_34), grafica nuova in game/arch_fx.py
  (logica in engine/archaludon.py). Sprite PMD Sprite Collab in
  assets/pokemon/0884/1018. Forme nuove in _draw_shapes (arch_fx.SHAPES):
  palla d'acciaio in volo con scia argentata (steelball: attacco base e
  Cannonflash, piu' grossa e con scintille se Tiro Lungo e' carico), fulmine
  dal cielo a zig-zag rifatto a ogni frame con un ramo (zigbolt: Fulmine,
  Tuono, paralisi), anello elettrico che crepita (sparkring: bordo a zig-zag
  FITTO, con pochi punti sembrava un poligono), raggio di Elettroraggio
  (railbeam: tre strati + archi sui bordi + anelli che scorrono). Riusa
  crescent (Charcadet, Codadrago: sweep ridotto, se no finiva sotto il
  bersaglio), soundarc (Noibat, Ferrosuono con jag), hexshell (Ferroscudo),
  windline, impactstar. Niente groundcrack sul fulmine: disegnato sopra lo
  sprite sembrava un mucchio di rametti. Disegni PERSISTENTI (world_fx):
  Tuononda in arrivo (area che si riempie + scariche), bersagli di Tuono
  (ombra della nube, cerchio che si chiude, gocce se allargato dalla
  pioggia), carica di Elettroraggio (corsia tratteggiata di 25 tile + globo
  d'energia che risucchia scintille) VISIBILE ANCHE AI NEMICI. SCHERMO CHE
  TREMA (Elettroraggio, per tutti): evento fx "shake" senza posizione (passa
  fx_visible per entrambe le squadre) -> FXSystem.shake_until_ms ->
  arch_fx.draw_shake fa surface.scroll di 1-2 px sul fotogramma a bassa
  risoluzione (MatchScene.draw e OnlineMatchScene.draw), la UI resta ferma.
  Sulle unita' (visibili a tutti): scintille di Conduzione sotto la pioggia,
  alone giallo del +Att. Sp., saette dei fulmini di Tuono rimasti a destra
  della barra della vita. Mirino: Tiro Lungo = corsia che si allunga con la
  pressione + barra di carica (gialla a carica piena, dimezzata sotto la
  pioggia); Tuononda/Tuono col raggio vero (+50% Tuono in pioggia). HUD:
  nuvola con saetta, accesa con la pioggia che cade quando Conduzione e'
  attiva; saette e secondi di Tuono; cornice chiara col +Att. Sp.
  PRESSIONE DEL TASTO (Tiro Lungo): InputController/NetMatchScene misurano
  la mira (aim_start) e la mettono in CastMoveCommand.hold; online viaggia nei
  6 bit alti del byte dello slot di CMD_CAST (protocol.pack_cast_slot, passi
  di 0,05 s): il formato dei pacchetti non cambia. Online: wave_zones/
  thunder_marks in net/visual.LISTS, beam_charges a entrambe le squadre (come
  taxi_flights), arch_rain/thunder_left in UNIT_FLAGS. Screenshot: step_34_*
  (linea, hud_*, ogni mossa, tirolungo_mira, tuononda_arrivo,
  elettroraggio_carica, tuono_arrivo, conduzione, draft_duraludon).
- ICONA e SCHERMATA DI CARICAMENTO (step_35). assets/ui/icon.png (+ .ico):
  quadrato "PM" ritagliato dall'immagine fornita, angoli trasparenti (flood-fill
  dagli angoli attraverso i pixel non neri). game/app.py _set_app_icon: set_icon
  PRIMA di set_mode + AppUserModelID "PokeMoba.Game" (Windows: la barra mostra la
  nostra icona, non quella di python.exe). Nuovo game/loading_screen.py: sfondo
  assets/ui/loading_bg.jpg scalato "cover" (cache per dimensione finestra) con velo
  scuro, disco scuro + spinner a 12 tacche dorate al CENTRO + testo. Usata da
  char_select_scene (partita locale) e online_draft_scene (fase LOADING: disegna
  prima il caricamento, poi costruisce OnlineMatchScene). Screenshot: step_35.png,
  step_35_icon.png.
- RINOMINA in PokéMoba + MENU PRINCIPALE rifatto (step_36). Nome visibile
  "PokéMoba" (titolo finestra, README, guide); identificatori tecnici ASCII
  "PokeMoba" (exe, cartella %APPDATA%\PokeMoba, AppUserModelID, logger); il
  profilo della cartella vecchia PokrLOL viene letto ancora (avatars.load_profile).
  game/scenes/menu_scene.py: titolo grande con ombra + 5 voci (Gioca,
  Personalizzazione, Crediti, Tier list, Esci), frecce+Invio o clic. Nuovo
  play_scene.py (mappa offline, online/LAN con pulsanti cliccabili; la char
  select torna qui). Personalizzazione = profile_scene (nickname+immagine).
  Crediti con sezione sul gioco. Nuovo tier_scene.py: tier list S-D
  trascina-e-rilascia dei Pokémon del roster, salvata in
  %APPDATA%\PokeMoba	ierlist.json (prima non esisteva nessuna tier list).
  Screenshot: step_36_menu/_gioca/_tier/_personalizzazione/_crediti.
- Tier list a DUE OPZIONI (step_37): il clic su "Tier list" apre
  tier_scene.TierChoiceScene con "Developer" (solo pulsante, per ora non fa
  nulla) e "Personale" (la TierListScene trascina-e-rilascia salvata). Esc/
  Indietro dalla tier personale torna alla scelta, poi al menu.
  Screenshot: step_37_tier_scelta.png.
- TIER LIST DEVELOPER dai bot (step_38/39/51). tools/tier_sim.py gioca partite
  headless (Match + bot) sulla mappa 5v5, 18 min di gioco; se nessuno distrugge il
  nucleo decidono torri, uccisioni, danno. Ogni squadra: 1 jungler (Nincada, Sneasel,
  Teddiursa, Swinub, Totodile) + 4 giocatori casuali, 2 in bot lane; il supporto
  (puro, o chi ha una forma support se non ce n'e') va in bot e prende la forma
  support (Politoad, Sylveon), gli altri una forma non support; Sneasel jungler ->
  Sneasler, in lane -> Weavile. FastVision = visione identica ma piu veloce (solo nel
  tool). Squadre bilanciate (pesca i meno usati). Risultati in
  tools/tier_matches_5v5.jsonl (98 partite: il torneo da 160 e' stato fermato per
  tempo; una partita richiede ~14 min reali, 7 processi). Metriche per unita':
  uccisioni, morti, assist, danno, subito, CC (rising edge degli stati *_until),
  cure/scudi, campi, leggendari, minion, torri, Smite, livelli. tools/tier_build.py:
  punteggio PER RUOLO con vittorie 30% + partecipazione alle uccisioni + CC per tutti
  (un Totodile con CC/assist sale) + pesi del ruolo; correzione "fortuna di tipo";
  tier 3/5/7/6/4. data/tier_developer.json con forme, tipi, scontri, contesto
  (jungler/lane, con/senza supporto, corsie) e match_data. Scene (tier_scene.py):
  DeveloperTierScene, DeveloperDetailScene (due colonne), DeveloperMatchDataScene
  ("Dati partite"). Screenshot: step_51_*.png.
- SMITE e IA PIU PRUDENTE (engine/smite.py, SmiteMixin in Match). Smite come in LoL:
  danno vero ai soli neutrali, 2 cariche, 90 s per carica, 15 s tra due usi, gittata
  4 tile, 600->1200 col livello; SmiteCommand + tasto F (solo locale, niente HUD/rete).
  I jungler bot lo usano per finire un mostro (una sola carica = solo grandi/leggendari).
  Bot: niente inseguimento di campioni sotto torre senza buone possibilita' di kill,
  leash dalla lane (7 tile nei primi 150 s, poi 14), jungler che gankano solo da 2:30,
  liv.3, bersaglio sotto il 60% e senza troppi rinforzi. engine/grid.line_of_sight
  inlineata (stesso risultato).
- HUD DI PARTITA rifatto (step_40), nuovo game/hud.py condiviso da MatchScene e
  NetMatchScene/OnlineMatchScene (le scene costruiscono PlayerView/SlotView/
  MatchView, hud.py disegna: nessuna logica). Prima: righe di testo in alto e
  caselle 72x56 coi nomi tagliati a 10 lettere. (1) BARRA IN BASSO (pannello scuro
  con cornice d'oro, a sinistra della minimappa): statistiche + oro | ritratto con
  medaglione del livello e nome (velo + secondi se abbattuto) | passiva
  (hud_passives, colonna larga PASSIVE_W=94 per Armature/Eevee) + caselle Q W E R
  (tinta del TIPO della mossa, tasto e "+" del grado DENTRO la casella, velo e
  secondi di ricarica, cariche, tacche del grado, lucchetto "Liv. 8"/"Evolvi") col
  NOME SOTTO in un carattere UNICO per la barra (name_size 13..11, due righe solo
  se serve; il "+" delle varianti e' un segno dorato) | sotto: barra VITA (tacche
  ogni 500) e barra ESPERIENZA "x / y -> Lv.n" (xp_progress da CUMULATIVE_XP) |
  6 oggetti con le icone del negozio (ShopUI._icon). Targhetta "+N punti mossa"
  sopra la barra. (2) STRISCIA IN ALTO: tempo, vita dei due nuclei, pallini dei
  Pokemon (vivo/caduto) + "rinasce Ns", prossima ondata, meteo, FPS a destra.
  (3) AVVISI (draw_banner) sotto la striscia: richiamo con barra, abbattuto,
  vittoria/sconfitta. (4) POPUP delle EVOLUZIONI: layout_popups li mette in fila
  sopra la barra, ognuno centrato sulla sua casella e spinto di lato quanto basta
  (a capo verso l'alto se non ci stanno), mai sopra la minimappa; nome intero +
  tipo colorato (draw_choice). Online stesso layout (scelta coi tasti 1/2); al
  posto delle statistiche (non nello snapshot) ruolo e tipi della forma attuale.
  App._draw_hud ora disegna solo messaggi temporanei (eventi rete, F3) a y=62.
  Screenshot: step_40_hud (evoluzioni), _gioco (ricariche, oggetti, richiamo),
  _eevee (abbattuto + popup Eevee), _charcadet/_zoom, step_40_online_60.
- HUD piu' COMPATTO coi NOMI DENTRO le caselle (step_41), su feedback (troppo
  spazio tra le caselle). Barra 752x150 -> 680x120: SLOT_GAP 16 -> 5, caselle
  72x52, statistiche/ritratto/oggetti piu' piccoli (ITEM 27). Il nome della
  mossa sta in basso DENTRO la casella (1-2 righe, carattere 11-12 unico per la
  barra); niente piu' gemma al centro: tasto in alto a sinistra, "+" in alto a
  destra, secondi di ricarica o pallino delle cariche in alto al centro,
  striscia del colore del tipo sul fondo. Parole troppo lunghe: trattino a fine
  sillaba (_wrap_name: V|CV o VC|CV, doppie divise, niente s+cons/gn/cons+r-l-h:
  "Danza-dipiume", "Elettro-raggio"). Le etichette della passiva usano
  hud.font(13) per stare tra le caselle e la barra della vita.
  Screenshot: step_41_hud, _gioco, _eevee, _mienfoo, _online.
- LINEA HATENNA > HATTREM > HATTERENE (step_42), grafica nuova in
  game/hatt_fx.py (logica in engine/hatterene.py). Sprite PMD Sprite Collab in
  assets/pokemon/0856/0857/0858. Forme nuove in _draw_shapes (hatt_fx.SHAPES):
  increspatura psichica schiacciata in prospettiva con 5 lobi che ruotano
  (psywave: Confusione, Incantavoce, impatti), raggio di Psicoraggio
  (psyband: corpo rosa + tre fili SOTTILI rosa/viola/azzurro a onda lunga; la
  prima versione a fili spessi e onda corta sembrava una catena di perline),
  nota musicale (note: Incantavoce), cuoricino in volo (heartfly:
  Assorbibacio cura), onda della Strega con le CIOCCHE a uncino sul bordo
  (witchring, svanisce in fretta: con alfa lineare restavano ragnatele sulla
  mappa), falce di luna (moonarc: Forza Lunare a segno, disegnata SUL colpito,
  non sul punto di contatto della sfera). Riusa twinkle (Mienfoo), windline
  (Noibat), energy/flash/ring (fx.py). Disegni PERSISTENTI (world_fx):
  Confusione in arrivo (area che si riempie + spirale a tre bracci; viola-blu
  con Psicoshock), sfera LENTA di Forza Lunare (globo rosa con ombra a falce,
  scia, ombra a terra; Magifiamma = palla di fiamma magenta), Distortozona
  VISIBILE A TUTTI (scacchiera deformata che si torce al centro, bordo
  tratteggiato che gira, frecce, barra del tempo; a scacchi troppo tenui non si
  vedeva), carica della Strega (anello che si allarga + ciocche che si
  arricciano verso l'esterno; dritte sembravano una gabbia). Sulle unità
  (visibili a tutti): VENA DI RABBIA pixel art (bitmap 9x9 in cache, sopra la
  barra) sugli AGITATI, brillantini viola + pallino rosa di Magipolvere (tipo
  Psico). HUD: Quiete = cappello della linea, cornice rossa e "N agitati"
  quando ci sono nemici agitati entro 10 tile (PassiveCtx.agitated). VISIONE:
  campo `agitated` dell'unità -> VisionSystem non applica la regola dei
  cespugli (solo la squadra nemica dell'agitato, che è quella di Hatterene).
  Online: hatt_marks/moon_orbs/witch_waves in net/visual.LISTS (moon_orbs anche
  in online_world.MOVING: avanza tra i pacchetti), trick_rooms a entrambe le
  squadre, agitated in UNIT_FLAGS. Screenshot: step_42_* (draft_hatenna,
  confusione/_arrivo, psicoraggio, incantavoce, magipolvere/_dopo,
  assorbibacio, forzalunare/_volo/_piu, magifiamma/_volo, distortozona,
  agitato, strega/_carica/_stordito, hud).
- EDITOR DELLE ANIMAZIONI (step_43), menu principale -> "Animazioni"
  (game/scenes/anim_editor_scene.py). Si sceglie un Pokémon (tutte le cartelle
  di assets/pokemon + i minion; ricerca scrivendo il nome) e un'azione: Fermo,
  Camminata, Attacco base o una delle mosse della sua linea (prese dai JSON del
  roster, slot Q/W/E/R). Per ognuna, SOLO VISIVO: animazione PMD da usare,
  velocita' (x0,10..x5,00), taglio (primo/ultimo fotogramma), e per attacco base
  e mosse il fotogramma del proiettile + il punto di partenza (clic
  sull'anteprima, misurato rivolto a destra: [avanti, su] in px sprite, ruota con
  la direzione). Anteprima ingrandita NEAREST con proiettile di prova, timeline
  con miniature (tagliati scuri, proiettile in oro, durate). Salvataggio in
  data/anim_overrides.json; formato e regole in game/anim_tuning.py. IN GIOCO:
  AnimationSet.key = nome cartella; SpriteAnimator legge la tabella (cache per
  versione) -> Idle/Walk con anim/velocita'/taglio, play_once(..., action=) per
  "aa"/"move:<id>". Il motore tagga SOLO eventi cosmetici: evento anim del lancio
  con "move" (emesso anche se la forma non ha animazione: l'editor puo'
  assegnarla), eventi della mossa con "src"/"move", anim dell'attacco base con
  "aa", rilascio "attack" con "src"; CAST_ANIMS (forma -> anim) e' ora una
  costante di engine/match.py. anim_tuning.FxTuner (MatchScene e
  OnlineMatchScene): sposta "a" al punto scelto, all'attacco base fa saltare
  l'animazione al fotogramma del proiettile (snap_release), per le mosse
  RITARDA l'effetto visivo fino a quel fotogramma (max 0,6 s; il danno resta
  quello del motore). Velocita' di movimento/attacco e tempi invariati.
  AnimData.xml: letto anche <HitFrame> (pulsante "colpo del file").
  Screenshot: step_43_menu, step_43_editor_idle/_mossa/_aa/_rayquaza.
- LINEA MAGNEMITE > MAGNETON > MAGNEZONE (step_44), grafica nuova in
  game/mag_fx.py (logica in engine/magnezone.py). Sprite PMD Sprite Collab in
  assets/pokemon/0081/0082/0462. Forme nuove in _draw_shapes (mag_fx.SHAPES):
  saetta a zig-zag tra due punti rifatta a ogni frame (ziglink), linee di
  campo magnetico (fieldlines: archi POCO gonfi, bulge ~0,1; a 0,3 formavano
  un'enorme "lente" viola che copriva tutto), badge della carica che compare
  (signpop), frecce dell'inversione di Voltcambio (fliparrows), anello
  schiacciato che crepita (magring: impulsi di pilastro e campo). Riusa
  energy/flash/ring/hexshell (fx.py) e impactstar (Sneasel). BADGE della
  carica: dischetto 11x11 rosso con "+" o blu con "-" (in cache, contorno
  scuro, luce in alto a sinistra), sopra la barra della vita con un alone
  tenue (a destra della vena di rabbia se l'unità è anche agitata), lampeggia
  nell'ultimo secondo; visibile a tutti. Disegni PERSISTENTI (world_fx):
  Tuonoshock in volo con la SAETTA che lo segue dal punto di lancio (max 2,2
  tile; Elettrotela = rete esagonale azzurra che gira, Falcecannone = sfera
  d'acciaio lenta con l'anello di scariche), cariche sui muri (badge sul punto
  colpito + anello che pulsa), Scia Ionica (corsia gialla tenue che crepita con
  i "+" rossi; con la fascia scura sembrava un sentiero), pilastro di
  Bombagnete = calamita a FERRO DI CAVALLO pixel art (_pillar_sprite, per
  pixel e in cache: arco + gambe del colore della polarità, punte d'acciaio,
  gamba destra in ombra; la prima versione a colonna sembrava una pila di
  mattoni) che cade dall'alto sul mirino, area di 6 tile tratteggiata e
  granelli che scorrono, barra del tempo STRETTA (larga sembrava una barra
  della vita); Campo Elettrico = ellisse gialla con bordo che crepita, piccole
  scariche a terra (spessore 2, a 1 px restava solo il nucleo bianco e
  sembravano vermi) e i segni della polarità che salgono; interazioni in corso
  (linee di campo viola tese per i trascinamenti, strisce e scarica dietro chi
  è respinto). POLARITÀ della R: mentre si mira, rotella del mouse o Tab
  alternano + / - (mag_fx._POLARITY, ricordata tra un lancio e l'altro); il
  mirino mostra il badge grande e l'area del colore scelto, l'HUD della passiva
  il badge in alto a destra; viaggia nel campo `hold` del lancio (1,0 = "-"),
  quindi il formato dei pacchetti non cambia (InputController e
  NetMatchScene). HUD: Magnetismo = calamita rossa/blu + "N carichi" (nemici
  carichi visibili). Online: mag_bolts/ion_trails/mag_links in
  net/visual.LISTS (mag_bolts anche in online_world.MOVING), mag_walls/
  mag_pillars/mag_fields a entrambe le squadre, mag_sign in UNIT_FLAGS
  (mag_until passa da solo come timer). Screenshot: step_44_* (draft_magnemite,
  tuonoshock/_volo, cariche, attrazione, urto, respinta,
  campomagnetico_alleato, ancora, catena, muro_carico/_trascina, voltcambio,
  scia_ionica, elettrotela/_volo, falcecannone/_volo, bombagnete_mira/
  _caduta/_dopo, campoelettrico/_dopo, hud, hud_polarita).
- LINEA SWINUB > PILOSWINE > MAMOSWINE (step_45), grafica nuova in
  game/swine_fx.py (logica in engine/mamoswine.py). Sprite PMD Sprite Collab
  in assets/pokemon/0220/0221/0473. Forme nuove in _draw_shapes
  (swine_fx.SHAPES): getto di neve nel cono (snowcone; Bora con tre raffiche
  CORTE che scorrono: lunghe da un capo all'altro sembravano corde tese),
  sasso a parabola (rockarc: Forzantica, resta un attimo a terra e svanisce),
  sasso che cade dall'alto (rockfall: Frana), raggiera di cristalli
  (iceburst), frecce che salgono (uparrows), zanne di ghiaccio (icefangs:
  Gelodenti; le "jaws" bianche di Eevee sparivano su sprite chiari, e con la
  gengiva sembravano una clessidra). Riusa windline, impactstar, groundring,
  pebble, flake, flash, ring. All'arrivo dei sassi solo due sassolini: gli
  anelli a terra sembravano ciambelle di corda, l'anello grande con le crepe
  una ruota. Disegni PERSISTENTI (world_fx): IMPRONTE del Fiuto (zampa 9x10
  pixel art viola tenue, 8 direzioni in cache, alternate sinistra/destra,
  sbiadiscono in 8 s; disegnate DOPO la nebbia, solo per la squadra che fiuta),
  Scia Ghiacciata (corsia di ghiaccio a bordo frastagliato con riflessi),
  blocco di Era Glaciale in volo (cubo 2.5D con crepa, scia di neve, ombra a
  terra), bufera (ellisse con bordo tratteggiato che gira, raffiche curve,
  fiocchi che vorticano). Sulla barra della vita (visibili a tutti): scudo di
  Grassospesso = segmento bianco-ghiaccio in coda; accumuli di Gelo = 4
  posti sotto la barra, croce azzurra con contorno a 4 vicini (a 8 vicini
  diventavano quadrotti attaccati), BIANCHE a 4 accumuli; Forzantica = tre
  sassi in orbita. Il congelamento usa il blocco di ghiaccio di Eevee. HUD:
  muso che annusa + nomi delle passive attive, barra dello scudo da
  Piloswine, "Gelo: N pronti" (nemici visibili con 4 accumuli). Online:
  ice_trails/glacial_blocks/ice_storms in net/visual.LISTS (glacial_blocks
  anche in online_world.MOVING), swine_tracks SOLO alla squadra che fiuta,
  frost_stacks/fat_shield in UNIT_FLAGS. Screenshot: step_45_* (draft_swinub,
  impronte, hud_swinub, grassospesso, hud_piloswine, valanga, bora,
  gelodenti, gelo_accumuli, gelo_congelato, hud, scia/_dopo, riduttore/_mira,
  forzantica/_volo, frana/_dopo, eraglaciale_mira/_volo/_colpo/_bufera).
- LINEA VENONAT > VENOMOTH (step_46), grafica nuova in game/moth_fx.py
  (logica in engine/venomoth.py). Sprite PMD Sprite Collab in
  assets/pokemon/0048/0049. Forme nuove in _draw_shapes (moth_fx.SHAPES):
  scaglia in volo che rotea (mothscale: attacco base), raggio ondulato
  (mothbeam: Psicoraggio con anelli rosa che scorrono; Ventargenteo
  TRASLUCIDO, piu' stretto e con scaglie argentate: pieno e largo sembrava un
  tubo bianco), stelline della confusione (dizzy), ali di falena che battono
  (wingflap: scia di Raffica, semitrasparente; tolte da Eledanza perche'
  coprivano lo sprite), granelli che salgono (dustrise). Riusa soundarc
  verde (Noibat: Ronzio), windline (raffiche di Raffica CORTE a distanze
  diverse: lunghe da un capo all'altro sembravano fili tesi), ziglink (Magnemite:
  scintille della paralisi), zzz (Teddiursa), hexshell/flash/ring (fx.py).
  Disegni PERSISTENTI (world_fx): nubi di Velenpolvere/Paralizzante/Sonnifero
  (viola/giallo/azzurro: chiazze tenui che respirano, bordo a trattini che
  gira, granelli che salgono) e Tempesta di Polveri (tre colori che
  vorticano; trattini del bordo in numero proporzionale alla circonferenza:
  a 28 fissi, sul raggio di 5 tile, sembravano bastoncini sparsi). Sotto la
  barra della vita (visibili a tutti, anche su minion e neutrali): accumuli
  di veleno = gocce 5x6 viola, VERDI TOSSICO a 6 (la prima versione con
  contorno a 4 vicini sembrava una fila di frecce); vanno sotto ping/miele/
  Gelo se presenti. Sulle unita': scaglie che girano (Eledanza), scintille
  argentate (Ventargenteo), velo di polvere (Polvoscudo). Mirino: corsia del
  raggio, ellisse della nube, cono di respinta + freccia dello scatto
  all'indietro (Raffica). HUD: falena + "Veleno: N al massimo" (nemici visibili
  a 6 accumuli). Online: powder_clouds in net/visual.LISTS, venom_stacks in
  UNIT_FLAGS; Eledanza/Ventargenteo/Polvoscudo passano dai timer *_until.
  Screenshot: step_46_* (attacco, hud_venonat, psicoraggio/_mira, confuso,
  ronzio, ventargenteo/_buff, velenpolvere/_dopo, paralizzante/_dopo,
  sonnifero/_dopo, raffica/_mira, polvoscudo, eledanza/_dopo, hud,
  tempesta/_mira/_dopo, draft_venonat).
- LINEA REMORAID > OCTILLERY (step_47), grafica nuova in game/octi_fx.py
  (logica in engine/octillery.py). Sprite PMD Sprite Collab in
  assets/pokemon/0223/0224. MUNIZIONI = colore + sagoma (AMMO_COLS):
  Acqua goccia blu, Ghiaccio scheggia azzurra a rombo, Fuoco palla di brace
  con fiammella, Erba seme verde con fogliolina (draw_pellet). L'attacco
  base porta mtype = munizione (evento "attack", stile "octishot"). Forme
  nuove in _draw_shapes (octi_fx.SHAPES): pallottola in volo con spruzzo
  all'arrivo (octipellet), macchia d'inchiostro ad arco che si spiaccica
  (inksplat: Octazooka), Iper Raggio (octibeam: tre fasce arancio/bianco,
  anelli che scorrono, crepitio ai bordi, si assottiglia sparendo; schermo
  che trema 250 ms), tentacolo affusolato con ventose (octitentacle: Presa),
  mirino che si chiude (octireticle: aggancio). Disegni PERSISTENTI
  (world_fx): proiettili di Pistolacqua/Raffica/Colpo Perforante in volo
  (octi_shots: scia del colore della munizione + ombra; il Perforante più
  grosso). MIRINO di Prendimira (draw_reticle): PIXEL ART a quattro angolari
  che pulsano + croce col punto, ombra scura in basso a destra (la prima
  versione ad archi a raggio 7 px era una macchia rossa piena); sopra la
  barra della vita dell'agganciato, visibile a tutti, lampeggia
  nell'ultimo secondo (renderer._draw_unit_hp, che ora conosce il tempo da
  self._now). Sulle unità: l'afferrato è AVVOLTO da due fasce di tentacolo
  davanti allo sprite (contorno scuro, ventose, punta arricciata; i
  tentacoli sottili attorno non si vedevano), vapore e scintille durante la
  ricarica dell'Iper Raggio. Mirino: corsia della Q del colore della
  munizione con la pallottola in punta (Renderer.draw_aim ha il parametro
  ammo), cono d'inchiostro + freccia della spinta all'indietro, corsia di
  15 tile dell'Iper Raggio, cerchio di 3 tile della Presa. HUD: riquadro
  col mirino (acceso = il prossimo attacco base aggancia, altrimenti i
  secondi), a destra la colonna delle munizioni disponibili (attiva grande,
  le altre spente), sopra il nome della munizione (+30% dopo il cambio con
  Octillery). W con grado gratuito dal liv.1 ("start_rank" nel JSON,
  engine/moves.build_moveset). Online: octi_shots in net/visual.LISTS e
  online_world.MOVING, octi_lock_by in UNIT_FLAGS (i timer octi_* passano da
  soli), ammo/ammo_boost in ME_FIELDS. Screenshot: step_47_* (attacco_water/
  _ice/_fire/_grass, hud, hud_remoraid, hud_erba, prendimira/_dopo,
  pistolacqua_mira/_/_colpo, raffica, perforante, cambio, erba_schegge,
  octazooka_mira/_/_dopo, iperraggio_mira/_/_ricarica, presa_mira/_/_dopo,
  draft_remoraid).
- LINEA FLABEBE > FLOETTE > FLORGES (step_48), grafica nuova in
  game/flor_fx.py (logica in engine/florges.py). Sprite PMD Sprite Collab in
  assets/pokemon/0669/0670/0671. FIORI (flower_sprite, pixel art nativa in
  cache): germoglio = stelo con due foglioline, bocciolo = goccia chiusa del
  colore con i sepali, sbocciato = 5 petali a goccia (contorno, scuro, colore,
  luce in alto a sinistra) col centro; 5 palette (FLOWER_COLS). Disegnati dal
  RENDERER a terra prima delle unita' (Renderer.flower_source, impostato dalle
  scene), visibili a TUTTI anche nella nebbia: ombra, anello della squadra
  (azzurro alleato, rosso nemico), alone del colore che pulsa da sbocciato,
  barra della crescita sotto germoglio/bocciolo, lampeggio negli ultimi 3 s,
  scintille dorate sui fiori del Giardino Reale. Forme nuove in _draw_shapes
  (flor_fx.SHAPES): petalo che rotea in volo (florpetal: attacco base,
  Florocura, Simbiosi), vortice di petali (florswirl: Petalbufera, sui fiori
  al 50%), raggio di Solarraggio (florsolar, a 3 strati, sottile: largo
  sembrava una banda piatta), seme ad arco (florseedarc: Semina), croce di cura
  che sale (florplus). Disegni PERSISTENTI (world_fx): Radici (area verde con
  radici che si allargano + croci) e Campo Nebbioso (velo rosa con chiazze e
  bordo tratteggiato che gira). Sulle unita': petali che girano (Petalodanza),
  petali rossi/gialli ai piedi (bonus dei fiori raccolti), anello verde
  (Simbiosi), scintille rosa (dentro il Campo Nebbioso). HUD: fiore del colore
  scelto + pallini dei fiori piantati (pieni = sbocciati) + effetto del colore.
  SCELTA DEL COLORE: tavolozza a 5 caselle (draw_color_picker, tasti 1-5) nel
  pannello della selezione offline e sotto le carte del draft online; online il
  colore viaggia nei bit 1-3 del byte "lock" di R_PICK (formato invariato).
  Online: flowers/flor_roots/flor_mists a entrambe le squadre (net/visual),
  flower_color in UNIT_FLAGS e ME_FIELDS. Screenshot: step_48_* (fiori,
  semina, bocciolo, sbocciato, raccolta, giallo, hud, florocura/_mira,
  petalbufera/_mira, petalodanza, camponebbioso, radici, giardinoreale/_mira/
  _dopo, solarraggio/_mira, selezione, draft_flabebe).
- LINEA SCYTHER > SCIZOR / KLEAVOR (step_49), grafica nuova in game/scy_fx.py
  (logica in engine/scizor.py; evoluzione TRAMITE OGGETTO, condizione
  "evo_item" in engine/evolution.py). Sprite PMD Sprite Collab in
  assets/pokemon/0123/0212/0900. Icone nuove assets/items/metal-coat.png e
  black-augurite.png (la seconda su PokeAPI e' 160x160: ridotta a mano a 30x30
  con alfa netto, come le altre). Forme nuove in _draw_shapes (scy_fx.SHAPES):
  lama curva affusolata che corre lungo l'arco (scyblade: falce verde di
  Scyther, ascia di pietra di Kleavor, scia doppia con gli accumuli di
  Tagliofuria), chela che si chiude (scypincer: attacco base di Scizor),
  pugno pixel art con le linee di velocita' (scyfist: Pugnoscarica, enorme e
  arancione per Troppoforte), scheggia che vola a parabola (scyshard),
  fiammella rossa che sale (scyflame: Focalenergia), ascia gigante sul cono
  (scychop: Taglio d'Albero a segno). Riusa windline, impactstar,
  groundcrack, groundring, pebble, flash, ring. Disegni PERSISTENTI
  (world_fx, VISIBILI A TUTTI): campo di schegge (terreno scurito + bordo
  tratteggiato + schegge di pietra scura piantate, sprite in cache per
  variante, posizioni stabili per campo; cerchio per Asciapietra, cono per
  Taglio d'Albero), carica di Taglio d'Albero (cono che si riempie dal
  lanciatore + ascia alzata). Sulle unita': fiammelle di Focalenergia, due
  falci sopra la testa con Doppiocolpo pronto, riflessi d'acciaio di Chele,
  frecce blu di Troppoforte, linee di vento di Cuordeciso, pugni arancioni
  di Spaccaroccia, schegge che girano attorno a Kleavor nel suo campo; sotto
  la barra della vita 5 tacche d'armatura incrinata (Spaccaroccia subita,
  a tutti). HUD: falce/chela/ascia della passiva + tacche di Tagliofuria;
  dal liv.8 Scyther mostra "Evolvi: Metalcoperta/Augite" lampeggiante. Nel
  NEGOZIO (ShopUI.draw evo=) per Scyther i due oggetti hanno la cornice d'oro
  e "-> Scizor"/"-> Kleavor". Online: scy_fields/scy_chops a entrambe le
  squadre (net/visual), scy_fury_stacks/scy_double_ready/scy_shred/
  scy_infield in UNIT_FLAGS, i timer scy_*_until passano da soli.
  Screenshot: step_49_* (forme, ogni mossa, mirini, hud_*, negozio, draft).
- LINEA LITTEN > TORRACAT > INCINEROAR (step_50), grafica nuova in
  game/incin_fx.py (logica in engine/incineroar.py). Sprite PMD Sprite Collab
  in assets/pokemon/0725/0726/0727. Forme nuove in _draw_shapes
  (incin_fx.SHAPES): fauci di fuoco che si chiudono (incinjaw: Fuocodenti),
  due tagli affusolati che si incrociano uno dopo l'altro (incinx:
  Incrocolpo), tre archi spessi che escono nel cono (incinroar: Bullo rosso,
  Granfisico arancio, Provocazione viola), CORDE DEL RING (incinropes: tre
  corde rossa/bianca/rossa con i paletti d'oro che si tendono contro il muro
  e vibrano: il rimbalzo di Corsa alle Corde), scia di fuoco della corsa e
  del nemico scagliato (incinstreak, sollevata con air_z), anello schiacciato
  del Darkest Lariat con fiammate che girano (incinspin). Riusa scyblade e
  scyfist (Scyther: calci e pugno di Incineroar), claw3/groundring/
  groundcrack/pebble (Teddiursa), impactstar (Sneasel), flametongue
  (Charcadet). Schianto contro il muro = stella d'impatto + crepe + sassi +
  schermo che trema. Sulle unita' (visibili a tutti, anche online dai timer
  *_until): braccia tese che girano con le fiamme scure (Lariat), pugni
  accesi (colpo potenziato dal rimbalzo), freccine pixel art accanto alla
  barra della vita: ROSSA in su = +Attacco di Bullo, AZZURRA in giu' =
  Prepotenza subita. HUD: cintura di fuoco con la fibbia d'oro (accesa e
  "Prepotenza pronta" dopo 5 s di calma, barra della calma sotto), con
  Incineroar 3 tacche di Cattivo del Ring + "+N%". Mirini: cono (Doppiocalcio,
  Bullo), cerchio del morso, X di Incrocolpo, corsia di 5 tile con le corde in
  punta e le frecce dei rimbalzi, cerchio del Lariat, cerchio di presa +
  freccia del lancio. Online: incin_calm_at/incin_ring_n in ME_FIELDS, il
  resto passa dai timer e dagli eventi fx. Screenshot: step_50_* (linea, ogni
  mossa, corsa_trascina/_schianto/_rimbalzo/_potenziato, presa_volo/_muro,
  lariat, prepotenza, mira_*, hud_litten, hud).

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
