"""Guardiano del torneo di bot (tools/tier_sim.py): controlla che le partite siano
DAVVERO partite e che il lancio non sia andato a vuoto.

Ogni 30 minuti (--every) verifica:
  1. il torneo e vivo: il file di stato (tools/tier_status.json) e stato aggiornato
     da poco e il processo principale esiste;
  2. i processi figli lavorano: la CPU consumata dai worker cresce (un worker fermo
     o morto = partite che non avanzano);
  3. le partite arrivano: il file .jsonl cresce (dopo il tempo di una partita) e
     nessuna partita gira da troppo piu della media (bloccata);
  4. le partite scritte sono vere: 10 Pokemon, durata plausibile, danno e uccisioni
     non nulli, nessun Pokemon con tutto a zero (segno di un'IA ferma).
Scrive l'esito in tools/tier_watch.log; in caso di problema mostra anche una finestra.
Finisce da solo quando il torneo si ferma (limite orario o partite finite).

    python tools/tier_watch.py                 # ciclo ogni 30 minuti
    python tools/tier_watch.py --once          # un solo controllo, subito
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "tools" / "tier_status.json"
LOG = ROOT / "tools" / "tier_watch.log"
MIN_MATCH_S = 240.0         # una partita vera dura almeno 4 minuti di gioco
BUSY_MIN = 0.35             # un worker che gioca usa quasi un core intero


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def alert(text: str) -> None:
    """Finestra di avviso (in un thread: non blocca il guardiano)."""
    def show():
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, "Torneo tier list: PROBLEMA", 0x30)
        except Exception:
            pass
    threading.Thread(target=show, daemon=True).start()


def children_cpu(pid: int) -> dict:
    """pid figlio -> secondi di CPU consumati finora (Windows, via PowerShell)."""
    cmd = ("Get-CimInstance Win32_Process -Filter \"ParentProcessId=%d\" | "
           "Select-Object ProcessId,KernelModeTime,UserModeTime | ConvertTo-Json" % pid)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                             text=True, timeout=60).stdout.strip()
        data = json.loads(out) if out else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    if isinstance(data, dict):
        data = [data]
    return {int(d["ProcessId"]): (int(d["KernelModeTime"]) + int(d["UserModeTime"])) / 1e7
            for d in data}


def alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                             text=True, timeout=30).stdout
        return str(pid) in out
    except (OSError, subprocess.SubprocessError):
        return False


def read_matches(path: Path) -> list:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def bad_match(m: dict) -> str | None:
    """Motivo per cui una partita scritta sembra finta/vuota, o None se e' vera."""
    units = m.get("units", [])
    if len(units) != 10:
        return f"{len(units)} Pokemon invece di 10"
    if m.get("time", 0) < MIN_MATCH_S:
        return f"durata {m.get('time', 0):.0f}s troppo breve"
    if sum(u.get("dmg", 0) for u in units) <= 0:
        return "nessun danno inflitto"
    if sum(u.get("kills", 0) for u in units) <= 0 and m.get("timeout"):
        return "nessuna uccisione in 18 minuti"
    idle = [u["name"] for u in units if u.get("dmg", 0) <= 0 and not u.get("camps")
            and not u.get("cs") and not u.get("support")]
    if len(idle) >= 3:
        return "Pokemon fermi: " + ", ".join(idle)
    return None


class Watch:
    def __init__(self):
        self.prev_cpu = {}
        self.prev_t = None
        self.prev_lines = None
        self.prev_lines_t = None

    def check(self) -> tuple[bool, str]:
        """Un controllo. Ritorna (tutto_ok, torneo_finito)."""
        problems, info = [], []
        if not STATUS.exists():
            problems.append("file di stato assente: il torneo non e' mai partito")
            return self._report(problems, info, False)
        st = json.loads(STATUS.read_text(encoding="utf-8"))
        now = time.time()
        if str(st.get("state", "")).startswith("stopped"):
            info.append(f"torneo fermo ({st['state']}), {st['finished']} partite scritte")
            return self._report(problems, info, True)
        age = now - st.get("updated", 0)
        if age > 120:
            problems.append(f"stato non aggiornato da {age:.0f}s: il torneo e' fermo o morto")
        if not alive(st["pid"]):
            problems.append(f"processo principale {st['pid']} non esiste piu")
        info.append(f"{st['finished']} partite finite, {st['running']} in corso, "
                    f"{st['queued']} in coda, durata media "
                    + (f"{st['avg_match_s'] / 60:.1f} min" if st.get("avg_match_s") else "n/d"))

        # 2. CPU dei worker.
        cpu = children_cpu(st["pid"])
        if self.prev_t is None and cpu:         # primo controllo: serve un secondo prelievo
            self.prev_cpu, self.prev_t = cpu, now
            time.sleep(20)
            cpu, now = children_cpu(st["pid"]), time.time()
        if self.prev_t is not None and cpu:
            dt = max(1.0, now - self.prev_t)
            busy = [(cpu[p] - self.prev_cpu.get(p, cpu[p])) / dt for p in cpu]
            n_busy = sum(1 for b in busy if b >= BUSY_MIN)
            want = min(st["workers"], max(1, st["running"]))
            info.append(f"worker attivi {n_busy}/{len(cpu)} (CPU media "
                        f"{sum(busy) / max(1, len(busy)) * 100:.0f}%)")
            if n_busy < want:
                problems.append(f"solo {n_busy} worker su {want} stanno calcolando")
        elif not cpu:
            problems.append("nessun processo figlio: nessuno sta giocando")
        self.prev_cpu, self.prev_t = cpu, now

        # 3. Il file cresce / nessuna partita bloccata.
        lines = st.get("out_lines", 0)
        avg = st.get("avg_match_s") or 16 * 60.0
        if self.prev_lines is not None and lines == self.prev_lines:
            stall = now - self.prev_lines_t
            if stall > max(2 * avg, 40 * 60):
                problems.append(f"nessuna partita finita da {stall / 60:.0f} minuti")
        if self.prev_lines is None or lines != self.prev_lines:
            self.prev_lines, self.prev_lines_t = lines, now
        for since in st.get("running_since", []):
            if now - since > max(3 * avg, 50 * 60):
                problems.append(f"una partita gira da {(now - since) / 60:.0f} minuti: bloccata?")

        # 4. Le ultime partite scritte sono vere?
        matches = read_matches(ROOT / st["out"])
        recent = matches[-10:]
        bad = [(m.get("seed"), bad_match(m)) for m in recent]
        bad = [(s, r) for s, r in bad if r]
        for s, r in bad:
            problems.append(f"partita seed {s} sospetta: {r}")
        if recent:
            info.append(f"ultime {len(recent)} partite: durata media "
                        f"{sum(m['time'] for m in recent) / len(recent) / 60:.1f} min, "
                        f"{sum(1 for m in recent if not m['timeout'])} finite col nucleo")
        elif now - st.get("started", now) > 25 * 60:
            problems.append("dopo 25 minuti nessuna partita e' ancora stata scritta")
        return self._report(problems, info, False)

    def _report(self, problems, info, finished):
        for i in info:
            log("   " + i)
        if problems:
            log("ALLARME: " + " | ".join(problems))
            alert("\n".join(problems))
        else:
            log("OK: il torneo sta giocando partite vere.")
        return not problems, finished


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=float, default=30.0, help="minuti tra i controlli")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    w = Watch()
    log("Guardiano avviato")
    while True:
        _, finished = w.check()
        if a.once or finished:
            break
        time.sleep(a.every * 60)
        # secondo prelievo CPU ravvicinato non serve: il confronto e' tra due controlli
    log("Guardiano finito")


if __name__ == "__main__":
    sys.exit(main())
