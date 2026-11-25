# Sicurezza

## Segnalare una vulnerabilità

Non aprire una issue pubblica. Usa la segnalazione privata di GitHub:
**Security → Report a vulnerability** in questo repository.

Descrivi il problema, come riprodurlo e, se lo sai, la versione del gioco
(schermata del menu, es. "3.1.0"). Rispondiamo appena possibile.

## Cosa interessa di più

- **Aggiornamento automatico** (`game/updater.py`): tutto ciò che può far
  installare un exe non pubblicato da noi.
- **Multiplayer** (`net/`): un host o un client modificato che manda in crash
  gli altri, esegue codice, legge file o vede attraverso la nebbia.

## Versioni supportate

Solo l'ultima Release: l'exe si aggiorna da solo all'avvio.

## Aggiornamenti firmati

Quando `UPDATE_PUBKEY` in `game/version.py` è impostata, gli exe delle Release
sono firmati con Ed25519 (`tools/release_sign.py`) e l'updater installa un aggiornamento solo se la firma, che copre l'impronta
sha256 dell'exe e il numero di build, è valida per la chiave pubblica in
`game/version.py`.
