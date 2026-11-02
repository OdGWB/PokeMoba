"""Trasporto WebRTC (aiortc) per il signaling manuale.

PUNTO DELICATO: THREAD E ASYNCIO
aiortc vive dentro un event loop asyncio; il gioco ha il suo loop pygame e
l'host un thread di simulazione a 30 tick/s. Non si mescolano mai:

    thread di gioco / host                      thread "rtc" (asyncio)
    ----------------------                      -----------------------
    peer.send(ch, dati)  --call_soon_threadsafe-->  channel.send(dati)
    peer.create_offer()  --run_coroutine_threadsafe--> createOffer + gathering
          (ritorna un concurrent.futures.Future: si controlla .done() a ogni frame)
    peer.recv()          <--queue.Queue------------  on("message")
    peer.state / error   <--assegnazione atomica--  on("iceconnectionstatechange")

- UN SOLO thread asyncio per processo (RtcLoop), condiviso da tutti i peer:
  l'host con 9 amici ha 9 RTCPeerConnection nello stesso loop.
- Il thread di gioco NON chiama mai await e non tocca oggetti aiortc: solo
  le tre porte sopra. Nessun lock serve oltre a queue.Queue.
- Il HEARTBEAT parte dal thread asyncio, non dal gioco: mentre un client
  costruisce la mappa (10-20 s di CPU sul thread di gioco) la connessione
  resta viva e l'host non lo crede caduto.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import ipaddress
import logging
import queue
import sys
import threading
import time

from . import ice_config
from .protocol import CH_RELIABLE, CH_STATE, HEARTBEAT
from .transport import (CLOSED, CONNECTED, CONNECTING, FAILED, GATHERING, NEW,
                        WAITING, Transport)

HEARTBEAT_EVERY = 0.5
NAT_FAILED_MSG = ("Connessione fallita: probabilmente uno dei due è dietro un NAT "
                  "simmetrico (rete aziendale, hotspot, alcuni operatori mobili). "
                  "Servirebbe un server TURN (vedi net/ice_config.py).")
_HB = bytes([HEARTBEAT])

log = logging.getLogger("pokemoba.rtc")


def available() -> bool:
    try:
        import aiortc  # noqa: F401
        return True
    except ImportError:
        return False


# --- loop asyncio dedicato ----------------------------------------------------------
class RtcLoop:
    _inst = None
    _lock = threading.Lock()

    def __init__(self):
        # Su Windows il loop di default (Proactor) a volte non completa la
        # chiusura dei socket UDP di aioice (connection_lost non arriva mai):
        # pc.close() resterebbe appeso. Il SelectorEventLoop non ha il problema
        # e a noi servono solo socket UDP.
        if sys.platform == "win32":
            self.loop = asyncio.SelectorEventLoop()
        else:
            self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="rtc-asyncio", daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @classmethod
    def get(cls) -> "RtcLoop":
        with cls._lock:
            if cls._inst is None:
                _patch_aioice()
                cls._inst = RtcLoop()
            return cls._inst

    def submit(self, coro) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, fn, *args):
        self.loop.call_soon_threadsafe(fn, *args)


# --- più STUN in parallelo + timeout del gathering ----------------------------------
def _stun_servers() -> list:
    out = []
    for srv in ice_config.ICE_SERVERS:
        urls = srv.get("urls")
        for u in ([urls] if isinstance(urls, str) else urls or []):
            if u.startswith("stun:"):
                host, _, port = u[5:].partition(":")
                out.append((host, int(port or 3478)))
    return out


def _patch_aioice():
    """aioice interroga UN solo STUN e aspetta 5 s per interfaccia. Qui li
    interroghiamo TUTTI in parallelo con il timeout di ice_config (3 s): basta
    che uno risponda, poi si concede GATHER_GRACE alle altre interfacce. Il TURN
    (se configurato) resta gestito da aioice."""
    import aioice.ice as ice

    orig = ice.Connection.get_component_candidates
    if getattr(orig, "_pokemoba", False):
        return

    async def patched(self, component, addresses, timeout=5):
        stuns = _stun_servers()
        saved = self.stun_server
        self.stun_server = None          # host (+ TURN) con il metodo originale
        try:
            cands = await orig(self, component, addresses, timeout=ice_config.GATHER_TIMEOUT)
        finally:
            self.stun_server = saved
        protos = []
        for p in self._protocols:
            lc = getattr(p, "local_candidate", None)
            if (lc is not None and lc.type == "host" and lc.component == component
                    and ipaddress.ip_address(lc.host).version == 4):
                protos.append(p)
        pending = {asyncio.ensure_future(ice.server_reflexive_candidate(p, s))
                   for p in protos for s in stuns}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ice_config.GATHER_TIMEOUT
        first_ok = None
        seen = set()
        while pending:
            wait = deadline - loop.time()
            if first_ok is not None:
                wait = min(wait, first_ok + ice_config.GATHER_GRACE - loop.time())
            if wait <= 0:
                break
            done, pending = await asyncio.wait(pending, timeout=wait,
                                               return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t.cancelled() or t.exception() is not None:
                    continue
                c, _ = t.result()
                key = (c.host, c.port, c.related_address, c.related_port)
                if key not in seen:
                    seen.add(key)
                    cands.append(c)
                    if first_ok is None:
                        first_ok = loop.time()
        for t in pending:
            t.cancel()
        return cands

    patched._pokemoba = True
    ice.Connection.get_component_candidates = patched


def patient_answerer(retries: int = 8) -> None:
    """Il client (chi risponde) avvia i controlli ICE appena genera la risposta,
    ma l'host la incolla quando la riceve su Discord: magari dopo un minuto.
    aioice di serie rinuncia dopo ~63 s (6 ritrasmissioni STUN raddoppiate);
    con 8 aspetta ~4 minuti. Appena l'host incolla, i suoi controlli arrivano e
    la connessione parte in pochi secondi. Vale per tutto il processo: va
    chiamata solo nel processo del client."""
    import aioice.stun as stun
    stun.RETRY_MAX = max(stun.RETRY_MAX, retries)


def _rtc_config():
    from aiortc import RTCConfiguration, RTCIceServer
    servers = []
    for s in ice_config.ICE_SERVERS:
        servers.append(RTCIceServer(urls=s["urls"], username=s.get("username"),
                                    credential=s.get("credential")))
    return RTCConfiguration(iceServers=servers)


# --- peer ----------------------------------------------------------------------------
class RtcPeer(Transport):
    """Una RTCPeerConnection con i due data channel negotiated:
    state (id 0, non ordinato, 0 ritrasmissioni) e reliable (id 1)."""

    def __init__(self):
        self._rt = RtcLoop.get()
        self.state = NEW
        self.error = ""
        self.last_rx = time.monotonic()
        self.bytes_in = self.bytes_out = 0
        self._inbox: queue.Queue = queue.Queue()
        self._pc = None
        self._ch = [None, None]
        self._open = [False, False]
        self._closing = False
        self._hb_task = None

    # --- API (thread di gioco) -------------------------------------------------
    def create_offer(self) -> concurrent.futures.Future:
        """Host: Future che restituisce l'SDP dell'offerta, candidati inclusi."""
        return self._rt.submit(self._create_offer())

    def accept_offer(self, sdp: str) -> concurrent.futures.Future:
        """Client: Future che restituisce l'SDP della risposta."""
        return self._rt.submit(self._accept_offer(sdp))

    def accept_answer(self, sdp: str) -> concurrent.futures.Future:
        """Host: applica la risposta incollata dall'amico."""
        return self._rt.submit(self._accept_answer(sdp))

    def send(self, channel, data):
        if self.state != CONNECTED:
            return
        self.bytes_out += len(data)
        self._rt.call(self._send_now, channel, bytes(data))

    def recv(self):
        out = []
        while True:
            try:
                out.append(self._inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        if self._closing:
            return
        self._closing = True
        if self.state != FAILED:
            self.state = CLOSED
        self._rt.submit(self._close())

    # --- lato asyncio ------------------------------------------------------------
    def _setup(self):
        from aiortc import RTCPeerConnection
        pc = RTCPeerConnection(configuration=_rtc_config())
        self._pc = pc
        st = pc.createDataChannel("state", negotiated=True, id=CH_STATE,
                                  ordered=False, maxRetransmits=0)
        rl = pc.createDataChannel("reliable", negotiated=True, id=CH_RELIABLE, ordered=True)
        for idx, ch in ((CH_STATE, st), (CH_RELIABLE, rl)):
            self._ch[idx] = ch
            self._wire_channel(idx, ch)

        @pc.on("iceconnectionstatechange")
        def _ice():
            s = pc.iceConnectionState
            log.debug("ice %s", s)
            if s == "failed" and not self._closing:
                self.error = NAT_FAILED_MSG
                self.state = FAILED
            elif s == "checking" and self.state in (NEW, WAITING, GATHERING):
                self.state = CONNECTING

        @pc.on("connectionstatechange")
        def _conn():
            s = pc.connectionState
            log.debug("conn %s", s)
            if s == "failed" and not self._closing:
                if not self.error:
                    self.error = NAT_FAILED_MSG if not all(self._open) else "Connessione persa."
                self.state = FAILED
            elif s == "closed" and self.state == CONNECTED:
                self.state = CLOSED

    def _wire_channel(self, idx, ch):
        def _opened():
            self._open[idx] = True
            if all(self._open) and self.state not in (FAILED, CLOSED):
                self.state = CONNECTED
                self.last_rx = time.monotonic()
                if self._hb_task is None:
                    self._hb_task = asyncio.ensure_future(self._heartbeat())

        ch.on("open", _opened)
        if ch.readyState == "open":
            _opened()

        @ch.on("message")
        def _msg(m):
            if not isinstance(m, (bytes, bytearray)) or not m:
                return
            self.last_rx = time.monotonic()
            self.bytes_in += len(m)
            if m[0] == HEARTBEAT:
                return
            self._inbox.put((idx, bytes(m)))

        @ch.on("close")
        def _closed():
            if self.state == CONNECTED and not self._closing:
                self.error = self.error or "Il peer ha chiuso la connessione."
                self.state = CLOSED

    async def _heartbeat(self):
        while self.state == CONNECTED:
            self._send_now(CH_STATE, _HB)
            await asyncio.sleep(HEARTBEAT_EVERY)

    def _send_now(self, channel, data):
        ch = self._ch[channel]
        if ch is None or ch.readyState != "open":
            return
        try:
            ch.send(data)
        except Exception:      # canale in chiusura: il pacchetto si perde
            pass

    async def _create_offer(self) -> str:
        self._setup()
        self.state = GATHERING
        # setLocalDescription raccoglie TUTTI i candidati (niente trickle):
        # con _patch_aioice ci mette al massimo ~GATHER_TIMEOUT secondi.
        await self._pc.setLocalDescription(await self._pc.createOffer())
        self.state = WAITING
        return self._pc.localDescription.sdp

    async def _accept_offer(self, sdp: str) -> str:
        from aiortc import RTCSessionDescription
        self._setup()
        self.state = GATHERING
        await self._pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        await self._pc.setLocalDescription(await self._pc.createAnswer())
        self.state = CONNECTING
        return self._pc.localDescription.sdp

    async def _accept_answer(self, sdp: str) -> None:
        from aiortc import RTCSessionDescription
        self.state = CONNECTING
        await self._pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    async def _close(self):
        if self._hb_task is not None:
            self._hb_task.cancel()
        if self._pc is not None:
            try:
                await self._pc.close()
            except Exception:
                pass
