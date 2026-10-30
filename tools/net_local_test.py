"""Test STANDALONE del multiplayer online, su WebRTC vero, sulla stessa macchina.

    python tools/net_local_test.py            # test automatico (2 processi, headless)
    python tools/net_local_test.py --windows  # apre due finestre di gioco per provare a mano

Il test automatico avvia un processo HOST e un processo CLIENT e fa da
"Discord": prende il codice offerta dall'host e lo incolla nel client, prende
la risposta e la incolla nell'host. Poi verifica tutto il flusso:

  1. codici sotto 1 KB, connessione ICE, data channel aperti;
  2. lobby, avvio partita, snapshot in arrivo;
  3. movimento confermato dall'host, ping misurato, pacchetti sotto l'MTU;
  4. input illegali rifiutati (bersagli inesistenti, oggetti falsi, spazzatura,
     flood) senza far cadere la connessione;
  5. il client muore di colpo: il suo Pokémon resta fermo dov'è, slot "disconnected";
  6. rientro con una nuova offerta sullo STESSO slot e lo stesso Pokémon;
  7. l'host chiude: il client riceve la fine partita pulita;
  8. l'host muore di colpo: il client se ne accorge in pochi secondi, niente freeze.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config  # noqa: E402  (dopo sys.path: serve la radice del progetto)
TAG = "@@"


def emit(**ev):
    print(TAG + json.dumps(ev), flush=True)


def stdin_commands():
    q = queue.Queue()

    def reader():
        for line in sys.stdin:
            line = line.strip()
            if line:
                q.put(json.loads(line))
        q.put({"op": "eof"})
    threading.Thread(target=reader, daemon=True).start()
    return q


def auto_pick(session):
    """Nel draft, al proprio turno, prende il primo Pokémon libero (una volta sola)."""
    if session.phase == "draft" and session.draft_my_turn() and not getattr(session, "_picked", 0):
        free = [i for i in range(len(config.ROSTER)) if i not in session.draft_taken()]
        session.send_pick(free[0], lock=True)
        session._picked = True


# =====================================================================================
# Processo HOST
# =====================================================================================
def run_host():
    from net.host import HostSession
    h = HostSession(map_index=0, host_name="Host")
    h.start()
    local = h.local
    cmds = stdin_commands()
    emit(ev="ready")
    while True:
        local.poll()
        auto_pick(local)
        if local.phase == "loading":
            local.send_loaded()
        try:
            c = cmds.get(timeout=0.005)
        except queue.Empty:
            continue
        op = c["op"]
        if op == "open":
            h.open_slot(c["slot"])
            t = time.monotonic()
            while time.monotonic() - t < 15:
                v = h.view[c["slot"]]
                if (v["status"] == "waiting" and v["code"]) or v["status"] == "failed":
                    break
                local.poll()
                time.sleep(0.02)
            v = h.view[c["slot"]]
            emit(ev="offer", code=v["code"], status=v["status"], error=v["error"],
                 gather=round(time.monotonic() - t, 2))
        elif op == "answer":
            emit(ev="answer_result", error=h.submit_answer(c["slot"], c["code"]))
        elif op == "choice":
            local.send_choice(c["team"], c["pokemon"], c["ready"])
            emit(ev="ok")
        elif op == "start":
            h.request_start()
            emit(ev="ok")
        elif op == "state":
            s = c.get("slot", 1)
            v = h.view[s]
            ent = h.world.get(v["entity_id"]) if h.world and v["entity_id"] else None
            emit(ev="state", phase=h.phase, status=v["status"], error=v["error"],
                 joined=v["joined"], entity_id=v["entity_id"], rejected=v["rejected"],
                 snap_bytes=v["snap_bytes"], message=h.message,
                 disconnected=sorted(h.disconnected),
                 pos=[ent.pos.x, ent.pos.y] if ent else None,
                 alive=bool(ent and ent.alive), moving=bool(ent and ent.moving),
                 local_phase=local.phase)
        elif op == "quit":
            h.shutdown()
            emit(ev="bye")
            return
        elif op == "eof":
            h.shutdown()
            return


# =====================================================================================
# Processo CLIENT
# =====================================================================================
def run_client(name):
    from net import protocol as P
    from net import rtc
    from net.client import ClientSession
    from net.signaling import ANSWER, ManualSignaling, SignalMessage
    cmds = stdin_commands()
    rtc.patient_answerer()
    session = None
    peer = None
    max_snap = 0
    emit(ev="ready")
    while True:
        if session is not None:
            session.poll()
            auto_pick(session)
            if session.phase == "loading":
                session.send_loaded()
            if session.snap_bytes.last > max_snap:
                max_snap = session.snap_bytes.last
        try:
            c = cmds.get(timeout=0.005)
        except queue.Empty:
            continue
        op = c["op"]
        if op == "offer":
            msg = ManualSignaling.decode(c["code"])
            peer = rtc.RtcPeer()
            t = time.monotonic()
            sdp = peer.accept_offer(msg.sdp).result(20)
            code = ManualSignaling.encode(SignalMessage(ANSWER, msg.slot, msg.session, sdp))
            session = ClientSession(peer, name)
            emit(ev="answer", code=code, gather=round(time.monotonic() - t, 2))
        elif op == "choice":
            session.send_choice(c["team"], c["pokemon"], c["ready"])
            emit(ev="ok")
        elif op == "move":
            me = session.latest.me
            session.send_move(P.dq_pos(me[0]) + c["dx"], P.dq_pos(me[1]) + c["dy"])
            emit(ev="ok")
        elif op == "evil":
            # Tutto ciò che un client truccato potrebbe provare.
            session.send_attack(60000)                         # entità inesistente
            session.send_buy("spada_infinita")                 # oggetto inesistente
            session.send_rank(9)                               # slot mossa fuori range
            session.send_cast(7, 1e9, -1e9)                    # slot e coordinate assurde
            peer.send_state(b"\x10\x00")                       # input troncato
            peer.send_state(b"\x99garbage")                    # tipo sconosciuto
            peer.send_reliable(b"\x44fakestart")               # messaggio da host
            for _ in range(300):                               # flood di comandi
                session.send_move(10.0, 10.0)
            emit(ev="ok")
        elif op == "state":
            lt = session.latest if session else None
            emit(ev="state", phase=session.phase if session else None,
                 transport=peer.state if peer else None,
                 slot=session.slot if session else None,
                 entity=session.start_info["your_entity_id"] if session and session.start_info else None,
                 seq=lt.seq if lt else None,
                 me=[P.dq_pos(lt.me[0]), P.dq_pos(lt.me[1])] if lt and lt.me else None,
                 unacked=len(session.unacked) if session else 0,
                 rtt=session.clock.rtt if session else None,
                 loss=session.loss.loss if session else None,
                 snap_avg=session.snap_bytes.value if session else 0, snap_max=max_snap,
                 keyframes=session.keyframes if session else 0,
                 lost=session.lost_reason if session else "",
                 end=session.end_info if session else None)
        elif op == "die":
            os._exit(3)                                       # caduta improvvisa, niente BYE
        elif op in ("quit", "eof"):
            if session is not None:
                session.close()
            emit(ev="bye")
            return


# =====================================================================================
# Regista (fa da "Discord" e controlla i risultati)
# =====================================================================================
class Child:
    def __init__(self, role, log, *extra):
        self.role = role
        self.log = open(log, "w", encoding="utf-8")
        self.p = subprocess.Popen([sys.executable, "-u", __file__, "--role", role, *extra],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=self.log, text=True, encoding="utf-8", cwd=str(ROOT))
        self.events = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.expect("ready", 30)

    def _read(self):
        for line in self.p.stdout:
            if line.startswith(TAG):
                self.events.put(json.loads(line[len(TAG):]))
        self.events.put({"ev": "exit"})

    def send(self, **cmd):
        self.p.stdin.write(json.dumps(cmd) + "\n")
        self.p.stdin.flush()

    def expect(self, ev, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                e = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            if e["ev"] == ev:
                return e
            if e["ev"] == "exit":
                raise RuntimeError(f"{self.role} è terminato (log: {self.log.name})")
        raise TimeoutError(f"{self.role}: niente '{ev}' entro {timeout}s")

    def ask(self, timeout=10, **cmd):
        self.send(**cmd)
        return self.expect("state" if cmd["op"] == "state" else "ok", timeout)

    def kill(self):
        self.p.kill()
        self.p.wait(5)


class Report:
    def __init__(self):
        self.fails = 0

    def check(self, ok, what, detail=""):
        print(f"  [{'OK ' if ok else 'ERR'}] {what}" + (f"   ({detail})" if detail else ""),
              flush=True)
        if not ok:
            self.fails += 1
        return ok


def wait_until(fn, timeout, every=0.3):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = fn()
        if last:
            return last
        time.sleep(every)
    return last


def connect(host, client, slot, R):
    host.send(op="open", slot=slot)
    off = host.expect("offer", 20)
    R.check(bool(off["code"]), "l'host crea l'offerta (ICE gathering completo)",
            f"{off['gather']} s, stato {off['status']} {off['error']}")
    R.check(len(off["code"]) < 1024, "codice offerta sotto 1 KB", f"{len(off['code'])} caratteri")
    client.send(op="offer", code=off["code"])
    ans = client.expect("answer", 30)
    R.check(len(ans["code"]) < 1024, "codice risposta sotto 1 KB",
            f"{len(ans['code'])} caratteri, {ans['gather']} s")
    host.send(op="answer", slot=slot, code=ans["code"])
    res = host.expect("answer_result")
    R.check(res["error"] is None, "l'host accetta la risposta", res["error"] or "")
    st = wait_until(lambda: (lambda s: s if s["phase"] in ("lobby", "draft", "loading", "match") else None)(
        client.ask(op="state")), 25)
    R.check(bool(st), "connessione WebRTC stabilita (data channel aperti, lobby)",
            f"slot {st['slot'] if st else '?'}")


def run_auto():
    tmp = Path(tempfile.gettempdir()) / "pokrlol_net_test"
    tmp.mkdir(parents=True, exist_ok=True)
    R = Report()
    t0 = time.monotonic()
    print("== 1. Connessione con signaling manuale")
    host = Child("host", tmp / "host.log")
    cli = Child("client", tmp / "client.log", "--name", "Amico")
    try:
        connect(host, cli, 1, R)

        print("== 2. Lobby, draft e avvio partita")
        host.ask(op="choice", team=0, pokemon=0, ready=True)
        cli.ask(op="choice", team=1, pokemon=1, ready=True)
        time.sleep(0.5)
        host.ask(op="start")
        st = wait_until(lambda: (lambda s: s if s["phase"] == "match" and s["seq"] else None)(
            cli.ask(op="state")), 40)
        R.check(bool(st), "partita avviata, snapshot in arrivo", f"seq {st and st['seq']}")

        print("== 3. Input, conferme, ping, dimensione pacchetti")
        x0 = st["me"][0]
        cli.ask(op="move", dx=-4.0, dy=0.0)
        time.sleep(3.0)
        st = cli.ask(op="state")
        R.check(st["me"][0] < x0 - 2.0, "l'host ha mosso il Pokémon del client",
                f"x {x0:.2f} -> {st['me'][0]:.2f}")
        R.check(st["unacked"] == 0, "tutti i comandi confermati dall'host")
        R.check(st["rtt"] is not None, "RTT misurato sul canale reliable",
                f"{(st['rtt'] or 0) * 1000:.1f} ms")
        R.check(st["snap_max"] < 1200 and st["keyframes"] >= 1,
                "snapshot sotto l'MTU, keyframe ricevuto",
                f"media {st['snap_avg']:.0f} B, max {st['snap_max']} B, keyframe {st['keyframes']}")

        print("== 4. Input illegali")
        cli.ask(op="evil")
        time.sleep(1.5)
        hs = host.ask(op="state")
        st = cli.ask(op="state")
        R.check(hs["rejected"] >= 6, "l'host rifiuta comandi illegali e flood",
                f"{hs['rejected']} rifiutati")
        R.check(st["phase"] == "match" and hs["status"] == "connected",
                "il client resta connesso (sotto la soglia di espulsione)")
        entity = st["entity"]

        print("== 5. Il client cade di colpo")
        t = time.monotonic()
        cli.send(op="die")
        hs = wait_until(lambda: (lambda s: s if s["status"] == "disconnected" else None)(
            host.ask(op="state")), 8, every=0.1)
        R.check(bool(hs), "l'host segna lo slot come disconnesso entro ~3 s",
                f"dopo {time.monotonic() - t:.1f} s")
        # Da quel momento il Pokémon non riceve più ordini: resta dov'è.
        before = hs["pos"] if hs else [0, 0]
        time.sleep(2.5)
        hs = host.ask(op="state")
        moved = abs(hs["pos"][0] - before[0]) + abs(hs["pos"][1] - before[1]) if hs["pos"] else 99
        R.check(hs["alive"] and entity in hs["disconnected"] and moved < 1.0,
                "il Pokémon resta lì, vivo e bersagliabile (niente ritorno in base)",
                f"spostato di {moved:.2f} tile")

        print("== 6. Rientro sullo stesso slot")
        cli = Child("client", tmp / "client2.log", "--name", "Amico")
        connect(host, cli, 1, R)
        st = wait_until(lambda: (lambda s: s if s["phase"] == "match" and s["seq"] else None)(
            cli.ask(op="state")), 30)
        R.check(bool(st) and st["entity"] == entity, "rientrato con lo stesso Pokémon",
                f"entità {st and st['entity']} (era {entity})")
        hs = host.ask(op="state")
        R.check(hs["status"] == "connected" and entity not in hs["disconnected"],
                "slot di nuovo connesso")

        print("== 7. L'host chiude la partita")
        host.send(op="quit")
        host.expect("bye", 10)
        st = wait_until(lambda: (lambda s: s if s["phase"] == "ended" else None)(
            cli.ask(op="state")), 6)
        R.check(bool(st) and st["end"]["reason"] == 1, "il client riceve la fine partita pulita",
                (st or {}).get("end", {}) and st["end"]["message"])
        cli.send(op="quit")

        print("== 8. L'host muore di colpo")
        host = Child("host", tmp / "host2.log")
        cli = Child("client", tmp / "client3.log", "--name", "Amico")
        connect(host, cli, 1, R)
        host.ask(op="choice", team=0, pokemon=0, ready=True)
        cli.ask(op="choice", team=1, pokemon=1, ready=True)
        time.sleep(0.5)
        host.ask(op="start")
        wait_until(lambda: cli.ask(op="state")["phase"] == "match", 40)
        t = time.monotonic()
        host.kill()
        st = wait_until(lambda: (lambda s: s if s["phase"] == "lost" else None)(
            cli.ask(op="state")), 8, every=0.1)
        R.check(bool(st), "il client capisce che l'host è caduto",
                f"dopo {time.monotonic() - t:.1f} s: {st and st['lost']}")
        cli.send(op="quit")
    finally:
        for ch in (host, cli):
            try:
                ch.kill()
            except Exception:
                pass
    print(f"\n{'TUTTO OK' if R.fails == 0 else f'{R.fails} CONTROLLI FALLITI'}"
          f"   ({time.monotonic() - t0:.0f} s, log in {tmp})")
    return 0 if R.fails == 0 else 1


def run_windows():
    """Due finestre di gioco: in una premi O (ospita), nell'altra U (unisciti)."""
    procs = [subprocess.Popen([sys.executable, str(ROOT / "run_client.py")], cwd=str(ROOT))
             for _ in range(2)]
    print("Aperte due finestre. Finestra 1: [O] ospita online -> Crea codice -> Copia.\n"
          "Finestra 2: [U] unisciti -> Incolla -> Genera risposta -> Copia.\n"
          "Finestra 1: incolla la risposta nello slot -> Conferma. Chiudi le finestre per finire.")
    for p in procs:
        p.wait()
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")     # console Windows senza UTF-8
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["host", "client"])
    ap.add_argument("--name", default="Amico")
    ap.add_argument("--windows", action="store_true")
    a = ap.parse_args()
    if a.role == "host":
        run_host()
    elif a.role == "client":
        run_client(a.name)
    elif a.windows:
        sys.exit(run_windows())
    else:
        sys.exit(run_auto())


if __name__ == "__main__":
    main()
