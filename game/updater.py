"""Aggiornamento automatico dell'exe dalle GitHub Releases.

All'avvio (solo exe pubblicato dalla GitHub Action: version.BUILD > 0) un thread
chiede a api.github.com l'ultima Release del repo; se il tag "v<N>" e' piu' nuovo
scarica l'allegato PokeMoba.exe accanto all'exe in uso come "PokeMoba.exe.new".

L'exe in uso e' bloccato da Windows finche' il gioco e' aperto, quindi la
sostituzione la fa un piccolo script .cmd (senza finestra) che riprova a spostare
il file nuovo sopra quello vecchio finche' il gioco non si e' chiuso, poi lo
riavvia. App la lancia subito se si e' nel menu principale, altrimenti alla
chiusura del gioco (mai a meta' partita o nel draft online).

POKEMOBA_NO_UPDATE=1 disattiva tutto; POKEMOBA_UPDATE_URL sostituisce l'indirizzo
dell'API (solo per provare l'aggiornamento con un server locale).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from . import version

API = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT = 15


def tag_build(tag: str) -> int:
    """'v123' -> 123; tag non numerici -> 0 (ignorati)."""
    t = (tag or "").strip().lstrip("vV")
    return int(t) if t.isdigit() else 0


def _exe_path() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def enabled() -> bool:
    return (version.BUILD > 0 and "/" in version.REPO and "OWNER" not in version.REPO
            and _exe_path() is not None and not os.environ.get("POKEMOBA_NO_UPDATE"))


class Updater:
    """Stato: idle -> checking -> (none | downloading -> ready) oppure error."""

    def __init__(self):
        self.state = "idle"
        self.progress = 0.0
        self.new_build = 0
        self.error = ""
        self.notes = ""
        self._new_file: Path | None = None
        self._applied = False

    # ---------------------------------------------------------------- avvio
    def start(self) -> None:
        exe = _exe_path()
        if exe is not None:      # resti di un aggiornamento precedente
            for p in (exe.with_name(exe.name + ".new"), exe.with_name(exe.name + ".old")):
                try:
                    p.unlink()
                except OSError:
                    pass
        if not enabled():
            return
        self.state = "checking"
        threading.Thread(target=self._run, name="updater", daemon=True).start()

    def _get(self, url: str, accept: str):
        req = urllib.request.Request(url, headers={
            "User-Agent": "PokeMoba-updater", "Accept": accept})
        return urllib.request.urlopen(req, timeout=TIMEOUT)

    def _run(self) -> None:
        try:
            url = os.environ.get("POKEMOBA_UPDATE_URL") or API.format(repo=version.REPO)
            with self._get(url, "application/vnd.github+json") as r:
                data = json.loads(r.read().decode("utf-8"))
            build = tag_build(data.get("tag_name", ""))
            if build <= version.BUILD:
                self.state = "none"
                return
            asset = next((a for a in data.get("assets", [])
                          if a.get("name") == version.ASSET), None)
            if asset is None:
                self.state = "none"
                return
            self.new_build = build
            self.notes = (data.get("body") or "").strip()
            self.state = "downloading"
            exe = _exe_path()
            dst = exe.with_name(exe.name + ".new")
            tmp = exe.with_name(exe.name + ".part")
            total = int(asset.get("size") or 0)
            got = 0
            with self._get(asset["browser_download_url"], "application/octet-stream") as r, \
                    open(tmp, "wb") as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        self.progress = min(1.0, got / total)
            if total and got != total:
                raise OSError(f"download incompleto ({got}/{total} byte)")
            os.replace(tmp, dst)
            self._new_file = dst
            self.progress = 1.0
            self.state = "ready"
        except Exception as e:      # rete assente, GitHub giu', cartella non scrivibile...
            self.error = str(e)
            self.state = "error"

    # ---------------------------------------------------------------- applica
    def apply(self, relaunch: bool) -> bool:
        """Lancia lo script che sostituisce l'exe appena il gioco si chiude.
        Il chiamante deve poi chiudere il gioco. Ritorna False se non c'e' nulla."""
        if self.state != "ready" or self._applied or self._new_file is None:
            return False
        exe = _exe_path()
        script = Path(tempfile.gettempdir()) / "pokemoba_update.cmd"
        lines = [
            "@echo off",
            "set n=0",
            ":retry",
            # 'ping' come pausa: 'timeout' non funziona senza console.
            "ping -n 2 127.0.0.1 >nul",
            f'move /y "{self._new_file}" "{exe}" >nul 2>&1 && goto done',
            "set /a n+=1",
            "if %n% lss 90 goto retry",
            "goto end",
            ":done",
        ]
        if relaunch:
            lines.append(f'start "" "{exe}"')
        lines += [":end", '(goto) 2>nul & del "%~f0"']
        try:
            script.write_text("\r\n".join(lines) + "\r\n", encoding="mbcs" if os.name == "nt"
                              else "utf-8")
            env = dict(os.environ)
            # Il nuovo exe deve estrarsi da capo, non riusare l'ambiente di questo.
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            flags = 0
            if os.name == "nt":
                flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(["cmd", "/c", str(script)], env=env, creationflags=flags,
                             close_fds=True, cwd=str(exe.parent))
        except OSError as e:
            self.error = str(e)
            self.state = "error"
            return False
        self._applied = True
        return True

    # ---------------------------------------------------------------- testo
    def banner(self) -> str | None:
        if self.state == "downloading":
            return f"Aggiornamento v{self.new_build}: download {int(self.progress * 100)}%"
        if self.state == "ready":
            return f"Aggiornamento v{self.new_build} pronto: si installa alla chiusura"
        return None
