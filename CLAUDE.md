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
- Palette da giungla del suolo, rumore PER PIXEL in coord mondo
  (game/renderer.py _floor_color/_moss_at/_mud_at; game/map_renderer.py
  _build_floor/_scatter_detail): palette cupa e desaturata (base #2E4A33, scuro
  #233B29, chiaro #3A5A3C, muschio #4A6B3A, terra #5A4A35, fango #3E3527). Il
  colore NON e piu per tile: _build_floor campiona una maschera a bassa
  risoluzione (k=2 campioni/tile) in coordinate MONDO e la scala con
  smoothscale -> un'unica immagine continua, chiazze organiche che attraversano
  i tile senza cuciture ne "mattonelle"; muschio/fango usano due ottave con
  soglia -> bordi irregolari e sfumati. I dettagli (ciuffi d'erba, fiocchi,
  granelli) si disegnano sull'immagine prima del blit, saltando i tile dei
  sentieri e il fango nudo. Screenshot: screenshots/step_3.png.
- Sentieri come STRISCE continue (game/map_renderer.py _compute_paths/
  _stroke_paths/_catmull): la BFS multi-sorgente dai tile-lane da, per ogni
  campo, il percorso piu corto che aggira muri ed evita l'acqua; i punti si
  uniscono con una spline Catmull-Rom, deformata con rumore in perpendicolare,
  e si disegna una striscia con profilo sfumato (cerchi concentrici dal bordo
  trasparente al nucleo secco DIRT_DRY, largo 1-2 tile variabile). La terra
  resta solo sui tile d'erba (gli altri tile vengono ritagliati dalla striscia)
  e sui sentieri NON si disegnano fili d'erba. Puramente grafico. I campi
  arrivano via MapRenderer.set_camps(camps), chiamato dalle scene.
  Screenshot: screenshots/step_4.png.
- Cespugli ricolorati coi toni della giungla (BUSH_* in renderer.py: base
  #1F3B24, luce #3E6B3A, cresta non-lime): armonia con la nuova palette, in
  attesa del rifacimento completo delle chiome (passo futuro).
- Lane desaturata (LANE_* verso il grigio-bruno) e bordo lane<->erba IRREGOLARE
  (_shore_overlay kind path/fringe, per-tile via _edge_variant): frontiera
  ondulata (due seni + rumore) con ciuffi d'erba che invadono la terra battuta.

Scelte tecniche importanti:
- canopy e lighting_overlay sono RISERVATI e per ora VUOTI: la resa resta
  identica alla versione pre-layer. Le chiome dei cespugli stanno ancora in
  walls_base (sotto le unita); spostarle in canopy (sopra le unita) sara un
  passaggio futuro a se.
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
