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
  piu cupa delle lane; (b) poche macchie di luce calda #B68246 vicino ai campi
  (falloff gaussiano, raggio ~3 tile) che "aprono" la chioma scurita (radura
  illuminata); (c) composite warm-over-dark premoltiplicato in un'unica RGBA per
  pixel, calcolato a strisce (niente array a piena mappa) e blittato a blocchi
  CHUNK lazy. Alfe contenute: le unita restano leggibili. Vignettatura leggera
  (VIGNETTE_*) scurisce i bordi dello SCHERMO: screen-space, costruita una volta
  per dimensione vista (_vignette, cache) e blittata per ultima in draw_canopy,
  NON nei layer di mappa. Screenshot: screenshots/step_7.png (ravvicinato con
  finte unita) e step_7_over.png (mappa intera).

Scelte tecniche importanti:
- canopy resta RISERVATO e VUOTO; lighting_overlay ora porta il velo d'atmosfera
  (chioma + luce campi, vedi sopra). La vignettatura e' screen-space e vive in
  draw_canopy, fuori dai layer. Le chiome dei cespugli stanno ancora in
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
