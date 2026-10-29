# Giocare a PokrLOL online con gli amici

Niente server, niente account, niente costi. Uno di voi fa da **host** (la
partita gira sul suo PC), gli altri si collegano a lui scambiandosi dei
**codici** su Discord o WhatsApp. Fino a 10 giocatori (5 contro 5).

---

## 1. Preparazione (una volta sola, tutti)

1. Installa **Python 3.13** da <https://www.python.org/downloads/>.
   Durante l'installazione spunta **"Add python.exe to PATH"**.
2. Fatti mandare dall'host la cartella del gioco **PokrLOL** (zip) e
   scompattala dove vuoi. Dovete avere tutti **la stessa versione**: se l'host
   aggiorna il gioco, rimandatevi la cartella.
3. Apri la cartella, clicca sulla barra dell'indirizzo, scrivi `cmd` e premi
   Invio. Nella finestra nera scrivi:

   ```bash
   python -m pip install -r requirements.txt
   ```

   Aspetta che finisca (scarica pygame e aiortc, un paio di minuti).
4. Avvia il gioco con un doppio clic su **`gioca.bat`**.

> La prima volta Windows potrebbe chiedere se Python può usare la rete:
> rispondi **Consenti** (anche "reti private").

---

## 2. Se sei l'AMICO (ti unisci)

1. Nel menu premi **U** ("Unisciti online").
2. L'host ti manda un codice che inizia con **`PKO`**. Copialo tutto.
3. Nel gioco premi **Incolla** (o clicca nel campo e premi `Ctrl+V`), poi
   **Genera risposta**. Ci vuole al massimo qualche secondo.
4. Compare un codice che inizia con **`PKA`**: premi **Copia risposta** e
   mandalo all'host nella chat.
5. Aspetta: appena l'host incolla la tua risposta sei dentro la lobby.
   Hai qualche minuto di tempo, non serve correre.
6. Nella lobby: **T** cambia squadra, **,** e **.** cambiano Pokémon,
   **SPAZIO** = pronto. La partita la avvia l'host.

## 3. Se sei l'HOST (ospiti la partita)

1. Nel menu scegli la mappa (3v3 o 5v5) e premi **O** ("Ospita online").
2. Ogni amico ha il suo **slot**. Per lo slot 1 premi **Crea codice**, poi
   **Copia codice** e mandalo al primo amico. Ripeti con lo slot 2 per il
   secondo amico, e così via: **un codice diverso per ogni amico**.
3. Quando l'amico ti rimanda la sua risposta (`PKA...`), incollala nel campo
   **dello stesso slot** e premi **Conferma**.
4. Lo stato dello slot diventa **CONNESSO**. Gli slot liberi vengono riempiti
   dai bot.
5. Scegli il tuo Pokémon (T , . SPAZIO come gli altri). Quando tutti sono
   **PRONTO** premi **INVIO**.

Durante la partita l'host può premere **F2** per vedere gli slot.

---

## 4. Problemi comuni

| Cosa vedi | Cosa fare |
|---|---|
| **"Connessione fallita: probabilmente NAT simmetrico..."** | La rete di uno dei due blocca le connessioni dirette (succede con alcune reti aziendali/universitarie, hotspot del telefono, alcuni operatori). Provate da un'altra rete (es. il Wi-Fi di casa invece dell'hotspot). Se non va mai, serve un server TURN: chiedete a chi gestisce il gioco. |
| **"Risposta vecchia o di un'altra offerta"** | L'host ha rigenerato il codice. L'amico deve rifare il punto 2 col codice nuovo. |
| **"Questa risposta è per lo slot N"** | L'host ha incollato la risposta nello slot sbagliato. |
| **"Versione del gioco diversa"** | Fatevi rimandare la cartella dall'host. |
| **Un amico cade durante la partita** | Il suo Pokémon resta fermo dov'è (si può ancora colpire). L'host preme **F2** → **Nuovo codice** su quello slot e lo rimanda all'amico, che rifà i passi della sezione 2: rientra con lo stesso Pokémon. |
| **Cade l'host** | La partita finisce per tutti con un messaggio. Si torna al menu con INVIO. |
| **"Manca aiortc"** | Rifai il punto 3 della preparazione. |

## 5. Comandi in partita

- **Clic destro**: muoviti. **Clic sinistro** su un nemico: attacca.
- **Q W E R** (tieni premuto, poi rilascia): mosse. **Ctrl + Q/W/E/R**: alza il grado.
- **P**: negozio (in base). **B**: torna in base. **Y**: blocca/sblocca la telecamera.
- **F3**: mostra o nasconde le info di rete (ping, pacchetti persi...).
- **ESC**: esci (se sei l'host, chiude la partita per tutti).

---

### Per i curiosi: come funziona

La connessione è **WebRTC** (la stessa tecnologia delle videochiamate): i PC si
parlano direttamente, i server STUN pubblici di Google e Cloudflare servono solo
a scoprire il proprio indirizzo Internet. I codici `PKO`/`PKA` sono la
"presentazione" dei due PC, compressa. La partita gira solo sul PC dell'host;
gli altri mandano i comandi e ricevono 20 aggiornamenti al secondo, con solo
quello che la propria squadra può vedere. Il codice è in `net/`.

Per provare tutto su un solo PC: `python tools/net_local_test.py` (test
automatico) oppure `python tools/net_local_test.py --windows` (due finestre).
