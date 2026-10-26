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

Scelte tecniche importanti:
- canopy NON e' piu del tutto vuoto: porta l'OVERHANG delle chiome dei muri sul
  bordo sud (sopra le unita, vedi passo rilievi pseudo-3D). lighting_overlay
  porta il velo d'atmosfera (chioma + luce campi). La vignettatura e'
  screen-space e vive in draw_canopy, fuori dai layer. Le chiome dei CESPUGLI
  (TILE_BUSH) stanno ancora in walls_base e restano per-tile/squadrate: il loro
  rifacimento e' un passaggio futuro a se.
- I singoli sprite dei tile NON sono stati spostati: restano i builder nel
  Renderer (game/renderer.py), riusati da MapRenderer -> grafica invariata.
- Offset camera: camera.snap() arrotonda l'offset a interi UNA volta per
  frame (camera.ox/oy); mappa e unita (world_to_screen) usano lo stesso
  valore -> niente tremolio di 1px ne seam tra chunk su scroll sub-pixel
  (verificato: chunk == rendering monolitico, scarto 0).
- Il margine superiore `top` (= altezza estrusione H) nei layer serve ai
  rilievi 2.5D che sporgono sopra la riga 0.
- I layer sono grandi quanto la mappa; `ground` e pieno per natura, quindi
  su mappe dense il chunking rende poco oltre ai layer riservati lazy.
