"""Test del multiplayer online (net/): protocollo, delta, signaling, validazione,
predizione e un flusso host+client completo in memoria (senza WebRTC)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from net import protocol as P
from net.interp import InterpBuffer
from net.prediction import Predictor
from net.signaling import (ANSWER, OFFER, ManualSignaling, SignalingError, SignalMessage)
from net.validation import TokenBucket, clamp_point

# SDP reale prodotto da aiortc 1.15 (offerta con 3 candidati: 2 host + 1 srflx).
SDP = (
    "v=0\r\no=- 4002276703 4002276703 IN IP4 0.0.0.0\r\ns=-\r\nt=0 0\r\n"
    "a=group:BUNDLE 0\r\na=msid-semantic:WMS *\r\n"
    "m=application 62542 UDP/DTLS/SCTP webrtc-datachannel\r\nc=IN IP4 10.5.0.2\r\n"
    "a=mid:0\r\na=sctp-port:5000\r\na=max-message-size:65536\r\n"
    "a=candidate:d58210efba2ed9db3c6582c09eb339bc 1 udp 2130706431 10.5.0.2 62542 typ host\r\n"
    "a=candidate:59d8218451c120bd8b767372a27be3f9 1 udp 2130706431 192.168.1.217 62543 typ host\r\n"
    "a=candidate:13401f55c29230261ff41a9b516f8213 1 udp 1694498815 82.84.122.193 62543 typ srflx "
    "raddr 192.168.1.217 rport 62543\r\n"
    "a=end-of-candidates\r\na=ice-ufrag:wr6k\r\na=ice-pwd:Gv4Vmj4XN8MHa0pdQ8aQRL\r\n"
    "a=fingerprint:sha-256 6A:30:93:5E:FE:EA:91:BD:9C:70:24:6F:10:8B:C5:31:19:CF:2B:7F:B9:A9:3E:"
    "31:EE:89:36:3C:64:2D:51:10\r\n"
    "a=fingerprint:sha-384 46:75:95:26:FD:94:CE:23:3F:96:26:E2:F9:77:9C:65:58:AC:1E:FE:B3:E8:10:"
    "1D:46:60:7F:60:F6:0E:E1:88:74:EA:4A:5B:F2:76:12:89:57:F1:24:ED:BC:03:DF:4F\r\n"
    "a=setup:actpass\r\n")


def _ent(x, y, hp=100, kind=P.K_MINION):
    return (kind, 0, P.q_pos(x), P.q_pos(y), 0, P.EF_ALIVE, hp, 100, 30, 0)


class TestSequence(unittest.TestCase):
    def test_wraparound(self):
        self.assertTrue(P.seq_newer(0, 0xFFFF))
        self.assertTrue(P.seq_newer(5, 0xFFF0))
        self.assertFalse(P.seq_newer(0xFFFF, 0))
        self.assertEqual(P.seq_diff(1, 0xFFFF), 2)
        self.assertEqual(P.seq_next(0xFFFF), 0)

    def test_0xffff_is_a_normal_delta(self):
        """0xFFFF non è una sentinella: un delta con base 0xFFFF resta un delta."""
        base = P.Frame(0xFFFF, 10, {1: _ent(1, 1)}, (1, 1, -1, 0, 0), None, None)
        data = P.enc_snapshot(0, 11, {1: _ent(2, 1)}, base.glob, None, None, base=base)
        self.assertFalse(P.peek_snapshot(data)[2])
        fr = P.dec_snapshot(data, {0xFFFF: base}.get)
        self.assertFalse(fr.keyframe)
        self.assertEqual(fr.ents[1][P.E_X], P.q_pos(2))


class TestSnapshotDelta(unittest.TestCase):
    def test_roundtrip_and_size(self):
        glob = (6000, 6000, -1, 0, 0)
        hud = (3, 1234, 1, 0) + (0, 1, 0) * 4 + (500, ("potion",))
        me = (P.q_pos(10), P.q_pos(12), 900, P.ME_ALIVE | P.ME_CAN_MOVE, 7, 300)
        ents = {i: _ent(i, i * 0.5) for i in range(1, 60)}
        key = P.enc_snapshot(1, 100, ents, glob, hud, me)
        f1 = P.dec_snapshot(key, lambda s: None)
        self.assertTrue(f1.keyframe)
        self.assertEqual(f1.ents, ents)
        self.assertEqual(f1.hud, hud)
        self.assertEqual(f1.me, me)
        # Il turno dopo si muovono 10 entità, una muore, una nasce.
        ents2 = dict(ents)
        for i in range(1, 11):
            ents2[i] = _ent(i + 0.3, i * 0.5)
        del ents2[30]
        ents2[99] = _ent(5, 5, kind=P.K_POKEMON)
        delta = P.enc_snapshot(2, 101, ents2, glob, hud, me, base=f1)
        f2 = P.dec_snapshot(delta, {1: f1}.get)
        self.assertEqual(f2.ents, ents2)
        self.assertEqual(f2.hud, hud)            # non cambiato: preso dalla base
        self.assertLess(len(delta), len(key) // 4)
        self.assertLess(len(delta), P.MAX_STATE_PACKET)

    def test_missing_base(self):
        base = P.Frame(4, 1, {}, (0, 0, -1, 0, 0), None, None)
        data = P.enc_snapshot(5, 2, {}, base.glob, None, None, base=base)
        with self.assertRaises(P.MissingBase):
            P.dec_snapshot(data, lambda s: None)

    def test_truncated_packets_raise(self):
        data = P.enc_snapshot(1, 1, {1: _ent(1, 1)}, (0, 0, -1, 0, 0), None, None)
        for n in range(1, len(data)):
            with self.assertRaises((P.ProtocolError, P.MissingBase)):
                P.dec_snapshot(data[:n], lambda s: None)


class TestInputAndFx(unittest.TestCase):
    def test_input_roundtrip(self):
        cmds = [{"seq": 65535, "kind": P.CMD_MOVE, "x": 10.5, "y": 20.25},
                {"seq": 0, "kind": P.CMD_CAST, "slot": 2, "x": 1.0, "y": 2.0},
                {"seq": 1, "kind": P.CMD_ATTACK, "target_id": 42},
                {"seq": 2, "kind": P.CMD_STOP}]
        m = P.dec_input(P.enc_input(9, cmds))
        self.assertEqual(m["ack"], 9)
        self.assertEqual([c["seq"] for c in m["cmds"]], [65535, 0, 1, 2])
        self.assertAlmostEqual(m["cmds"][0]["x"], 10.5)
        self.assertEqual(m["cmds"][2]["target_id"], 42)
        self.assertIsNone(P.dec_input(P.enc_input(None, []))["ack"])

    def test_unknown_command_rejected(self):
        bad = bytes([P.C_INPUT, 0, 0, 0, 1, 1, 0, 99])
        with self.assertRaises(P.ProtocolError):
            P.dec_input(bad)

    def test_fx_split_under_mtu(self):
        events = [{"kind": "projectile", "a": (1.0, 2.0), "b": (3.0, 4.0), "mtype": "Fire",
                   "t": 0.4, "eid": i, "melee": False, "obj": object()} for i in range(80)]
        pkts = P.enc_fx(10, events)
        self.assertGreater(len(pkts), 1)
        out = []
        for p in pkts:
            self.assertLessEqual(len(p), P.MAX_STATE_PACKET)
            out += P.dec_fx(p)[1]
        self.assertEqual(len(out), 80)
        self.assertEqual(out[3]["eid"], 3)
        self.assertNotIn("obj", out[0])          # non rappresentabile: saltato


class TestSignaling(unittest.TestCase):
    def test_compact_code_under_1kb(self):
        code = ManualSignaling.encode(SignalMessage(OFFER, 3, 0xDEADBEEF, SDP))
        self.assertTrue(code.startswith("PKO3-"))
        self.assertLess(len(code), 1024)
        self.assertLess(len(code), 300)          # forma compatta, non l'SDP intero
        msg = ManualSignaling.decode(f"  ```{code[:40]}\n{code[40:]}```  ")
        self.assertEqual((msg.kind, msg.slot, msg.session), (OFFER, 3, 0xDEADBEEF))
        for field in ("a=ice-ufrag:wr6k", "a=ice-pwd:Gv4Vmj4XN8MHa0pdQ8aQRL",
                      "6A:30:93:5E:FE:EA:91:BD", "82.84.122.193 62543 typ srflx raddr "
                      "192.168.1.217 rport 62543", "a=setup:actpass", "a=sctp-port:5000"):
            self.assertIn(field, msg.sdp)

    def test_fallback_full_sdp(self):
        weird = SDP.replace("typ host", "typ host tcptype passive").replace(" udp ", " tcp ")
        code = ManualSignaling.encode(SignalMessage(ANSWER, 1, 7, weird))
        self.assertEqual(ManualSignaling.decode(code).sdp, weird)

    def test_garbage_rejected(self):
        for txt in ("", "ciao", "PKO1-!!!!", "PKO1-AAAA"):
            with self.assertRaises(SignalingError):
                ManualSignaling.decode(txt)
        code = ManualSignaling.encode(SignalMessage(OFFER, 2, 1, SDP))
        with self.assertRaises(SignalingError):
            ManualSignaling.decode(code.replace("PKO2", "PKO5"))   # slot manomesso


class TestValidation(unittest.TestCase):
    def test_bucket(self):
        b = TokenBucket(10, 5)
        t = b.t
        self.assertEqual(sum(b.take(now=t) for _ in range(20)), 5)
        self.assertTrue(b.take(now=t + 0.15))

    def test_clamp(self):
        self.assertEqual(clamp_point(-5, 500, 100, 100), (0.0, 99.99))
        self.assertIsNone(clamp_point(float("nan"), 1, 100, 100))


class _LineModel:
    """Movimento in linea retta senza muri, per testare la predizione."""
    def __init__(self):
        self.plans = 0

    def plan(self, pos, kind, target):
        if kind == P.CMD_STOP:
            return ()
        if kind != P.CMD_MOVE:
            return None
        self.plans += 1
        return (target,)

    def advance(self, pos, path, speed, dt):
        (tx, ty), = path[:1]
        dx, dy = tx - pos[0], ty - pos[1]
        d = (dx * dx + dy * dy) ** 0.5
        step = speed * dt
        if d <= step:
            return (tx, ty), path[1:], 2
        return (pos[0] + dx / d * step, pos[1] + dy / d * step), path, 2


class TestPrediction(unittest.TestCase):
    def test_reconcile_and_replay_without_astar(self):
        m = _LineModel()
        pr = Predictor(m, 1 / 30)
        pr.reconcile((0.0, 0.0), 3.0, True, False, None, 0, 0)       # primo snapshot
        pr.command(1, P.CMD_MOVE, (30.0, 0.0))
        for _ in range(10):
            pr.step()
        self.assertAlmostEqual(pr.pos[0], 1.0, places=5)              # 10 tick × 0.1
        # L'host ha applicato il comando 1 al suo tick 101 e al tick 105 dice x=0.5
        # (era previsto 0.5 al nostro tick locale 4): previsione giusta, niente replay.
        pr.reconcile((0.5, 0.0), 3.0, True, True, 1, 101, 105)
        self.assertEqual(pr.replays, 0)
        # Ora l'host dice che al tick 107 eravamo più indietro (spinti): replay.
        pr.reconcile((0.4, 0.0), 3.0, True, True, 1, 101, 107)
        self.assertEqual(pr.replays, 1)
        self.assertAlmostEqual(pr.pos[0], 0.4 + 3 * 0.1, places=5)  # 3 tick rigiocati
        self.assertEqual(m.plans, 1)                                   # A* solo al click
        self.assertGreater(abs(pr.smooth[0]), 0.0)                     # correzione smussata

    def test_cc_freezes_prediction(self):
        pr = Predictor(_LineModel(), 1 / 30)
        pr.reconcile((0.0, 0.0), 3.0, True, False, None, 0, 0)
        pr.command(1, P.CMD_MOVE, (30.0, 0.0))
        pr.reconcile((0.0, 0.0), 3.0, False, False, 1, 1, 1)          # stordito
        for _ in range(10):
            pr.step()
        self.assertEqual(pr.pos, (0.0, 0.0))


class TestInterp(unittest.TestCase):
    def test_midpoint_and_teleport(self):
        b = InterpBuffer()
        b.push(1, 0.0, 0.0, 0.0)
        b.push(1, 0.05, 1.0, 0.0)
        self.assertAlmostEqual(b.sample(1, 0.025)[0], 0.5)
        b.push(1, 0.10, 20.0, 0.0)                                     # teletrasporto
        self.assertEqual(b.sample(1, 0.075), (1.0, 0.0))


class TestDraft(unittest.TestCase):
    def test_orders(self):
        from net.draft import pick_order
        self.assertEqual([t for t, _ in pick_order(3)], [0, 1, 0, 1, 0, 1])
        self.assertEqual([t for t, _ in pick_order(5)], [0, 1, 1, 0, 0, 1, 1, 0, 0, 1])
        self.assertEqual(pick_order(5)[:3], [(0, 0), (1, 0), (1, 1)])

    def test_humans_then_bots_all_together(self):
        import random
        from net.draft import Draft
        # 5v5 con 2 blu (slot 0, 2) e 1 rosso (slot 1): B1 R1 B2, poi i bot.
        d = Draft(5, {0: [0, 2], 1: [1]}, 10, now=0.0, rng=random.Random(1))
        self.assertEqual(d.current_slot(), 0)
        self.assertFalse(d.lock(1, 3, 0.0))            # non è il suo turno
        self.assertTrue(d.lock(0, 3, 0.0))
        self.assertEqual(d.current_slot(), 1)
        self.assertFalse(d.lock(1, 3, 0.0))            # già preso
        self.assertTrue(d.lock(1, 4, 0.0))
        self.assertEqual(d.current_slot(), 2)
        self.assertFalse(d.done)
        self.assertTrue(d.lock(2, 5, 0.0))
        self.assertTrue(d.done)
        pokes = [e["poke"] for e in d.entries]
        self.assertEqual(sorted(pokes), list(range(10)))   # tutti diversi
        self.assertEqual(sum(1 for e in d.entries if e["slot"] is None), 7)

    def test_timeout_and_drop(self):
        from net.draft import PICK_TIME, Draft
        d = Draft(3, {0: [0], 1: [1]}, 10, now=0.0)
        d.hover_pick(0, 7)
        self.assertTrue(d.tick(PICK_TIME + 0.1))       # scaduto: prende l'anteprima
        self.assertEqual(d.entries[0]["poke"], 7)
        self.assertTrue(d.drop_slot(1, 31.0))          # il rosso esce: diventa bot
        self.assertTrue(d.done)
        self.assertEqual(len({e["poke"] for e in d.entries}), 6)

    def test_visual_packet_nested(self):
        from engine.vec import Vec2
        st = {"u": {7: {"frozen_until": 12.5, "invisible": True}},
              "avalanches": [{"pos": Vec2(3, 4), "dir": Vec2(1, 0), "speed": 2.0, "hit": {1, 2}}],
              "me": {"item_cd": {"smoke_ball": 9.0}, "charges": {"Q": 1.5}}}
        d = P.dec_vis(P.enc_vis(st))
        self.assertEqual(d["u"][7], {"frozen_until": 12.5, "invisible": True})
        av = d["avalanches"][0]
        self.assertEqual((av["pos"].x, av["dir"].x, av["speed"]), (3.0, 1.0, 2.0))
        self.assertNotIn("hit", av)                       # i set non viaggiano: solo logica
        self.assertEqual(d["me"]["item_cd"], {"smoke_ball": 9.0})

    def test_draft_packets(self):
        e = [{"team": 0, "pos": 0, "slot": 0, "poke": 3, "name": "Ana", "avatar": 150},
             {"team": 1, "pos": 0, "slot": None, "poke": None, "name": "", "avatar": 0}]
        d = P.dec_draft(P.enc_draft(1, e, 1, None, 12.5, False))
        self.assertEqual((d["map_index"], d["turn"], d["hover"], d["done"]), (1, 1, None, False))
        self.assertAlmostEqual(d["time_left"], 12.5)
        self.assertEqual(d["entries"], e)
        self.assertEqual(P.dec_pick(P.enc_pick(4, True)), {"pokemon": 4, "lock": True, "color": 0})
        self.assertEqual(P.dec_pick(P.enc_pick(9, True, 4)), {"pokemon": 9, "lock": True, "color": 4})
        self.assertEqual(P.dec_pick(P.enc_pick(9, False, 3))["lock"], False)


class TestHostClientLoopback(unittest.TestCase):
    """Flusso completo con la simulazione VERA, su un tubo in memoria con
    latenza e perdita: lobby, avvio, movimento, validazione, disconnessione,
    rientro con lo stesso Pokémon, chiusura pulita dell'host."""

    def _pump(self, sessions, sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            for s in sessions:
                s.poll()
                if s.phase == "draft" and s.draft_my_turn() and not getattr(s, "_picked", 0):
                    free = [i for i in range(10) if i not in s.draft_taken()]
                    s.send_pick(free[0], lock=True)
                    s._picked = True
                if s.phase == "loading":
                    s.send_loaded()
            time.sleep(0.005)

    def test_full_flow(self):
        from net import ClientSession, HostSession, LoopbackTransport
        from net.draft import DONE_TIME
        h = HostSession(map_index=0, host_name="Host")
        h.start()
        try:
            a, b = LoopbackTransport.pair(latency=0.03, loss=0.05, seed=3)
            h.attach_transport(1, a)
            c = ClientSession(b, "Amico")
            me = h.local
            self._pump([me, c], 0.4)
            self.assertEqual((me.phase, c.phase, c.slot), ("lobby", "lobby", 1))
            me.send_choice(0, 0, True)
            c.send_choice(1, 1, True)
            self._pump([me, c], 0.3)
            h.request_start()
            self._pump([me, c], 1.0)
            self.assertEqual(h.phase, "draft")
            self.assertEqual(me.phase, "draft")
            self._pump([me, c], DONE_TIME + 1.5)       # draft completo + caricamento
            self.assertEqual(h.phase, "match")
            # Ognuno ha il SUO Pokémon e nessun doppione fra umani e bot.
            pokes = [e["poke"] for e in h.draft.entries]
            self.assertEqual(len(set(pokes)), len(pokes))
            self.assertIsNotNone(c.latest)
            eid = c.start_info["your_entity_id"]
            x0 = P.dq_pos(c.latest.me[0])
            c.send_move(x0 - 4, P.dq_pos(c.latest.me[1]))
            # Comandi illegali: fuori mappa (clamp), bersaglio inesistente, oggetto falso.
            c.send_attack(60000)
            c.send_buy("spada_di_dio")
            self._pump([me, c], 2.0)
            self.assertLess(P.dq_pos(c.latest.me[0]), x0 - 2)          # si è mosso
            self.assertEqual(len(c.unacked), 0)                         # tutto confermato
            self.assertGreaterEqual(h.view[1]["rejected"], 2)
            # Stato visivo: stati sulle unità, nube della Palla Fumo, ricarica oggetto.
            from engine.vec import Vec2
            hp = h.world.get(eid)
            t = h.match.time
            hp.sleep_until = t + 30
            hp.item_cd["smoke_ball"] = t + 30
            h.match.item_clouds.append({"center": Vec2(hp.pos.x, hp.pos.y), "radius": 1.5,
                                        "end": t + 30, "owner_id": eid, "team": hp.team})
            self._pump([me, c], 0.5)
            self.assertAlmostEqual(c.visual["u"][eid]["sleep_until"], t + 30, places=2)
            self.assertIn("smoke_ball", c.visual["me"]["item_cd"])
            self.assertEqual(len(c.visual["item_clouds"]), 1)
            self.assertNotIn("mv", c.visual["item_clouds"][0])
            self.assertIsNotNone(c.clock.rtt)
            # Il client cade: il Pokémon resta lì, fermo e bersagliabile.
            pos = h.world.get(eid).pos
            b.close()
            self._pump([me], 3.6)
            self.assertEqual(h.view[1]["status"], "disconnected")
            p = h.world.get(eid)
            self.assertTrue(p.alive)
            self.assertLess(p.pos.dist(pos), 0.5)
            # Rientro sullo stesso slot: stesso Pokémon.
            a2, b2 = LoopbackTransport.pair(latency=0.03)
            h.attach_transport(1, a2)
            c2 = ClientSession(b2, "Amico")
            self._pump([me, c2], 1.0)
            self.assertEqual(c2.start_info["your_entity_id"], eid)
            self.assertIsNotNone(c2.latest)
            self.assertNotIn(eid, h.disconnected)
            # Chiusura pulita dell'host.
            h.shutdown()
            self._pump([me, c2], 0.3)
            self.assertEqual(c2.phase, "ended")
            self.assertEqual(c2.end_info["reason"], P.END_HOST_QUIT)
        finally:
            h.shutdown()


class TestClockSync(unittest.TestCase):
    def test_pong_before_first_tick_is_ignored(self):
        """Durante il caricamento l'orologio della partita e' fermo: quei PONG non
        devono entrare nella stima (darebbero un offset sbagliato di tutta l'attesa)."""
        from net import ClientSession, LoopbackTransport
        _a, b = LoopbackTransport.pair()
        c = ClientSession(b, "Amico")
        t0 = c._t0
        # caricamento: 5 s di attesa con l'orologio dell'host fermo a 0
        for k in range(5):
            c._handle(P.CH_RELIABLE, P.enc_pong(k * 1000, 0.0, 0), t0 + k + 0.05)
        self.assertIsNone(c.clock.offset)
        # partita: l'host e' a 2,0 s quando il client e' a t0+10
        c._handle(P.CH_RELIABLE, P.enc_pong(10000, 2.0, 60), t0 + 10.05)
        self.assertAlmostEqual(c.clock.host_time(t0 + 10.05), 2.025, places=3)


if __name__ == "__main__":
    unittest.main()
