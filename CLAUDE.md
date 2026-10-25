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
