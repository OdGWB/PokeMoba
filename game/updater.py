"""Aggiornamento automatico dell'exe dalle GitHub Releases.

All'avvio (solo exe pubblicato dalla GitHub Action: version.BUILD > 0) un thread
chiede a api.github.com l'ultima Release del repo; se il tag "v<N>" e' piu' nuovo
scarica l'allegato PokeMoba.exe accanto all'exe in uso come "PokeMoba.exe.new".

L'exe in uso e' bloccato da Windows finche' il gioco e' aperto, quindi la
sostituzione la fa un piccolo script .cmd (senza finestra) che riprova a spostare
il file nuovo sopra quello vecchio finche' il gioco non si e' chiuso, poi lo
riavvia. App la lancia subito se si e' nel menu principale, altrimenti alla
chiusura del gioco (mai a meta' partita o nel draft online).

Se l'API non risponde (limite di 60 richieste/ora per indirizzo IP, condiviso da
tutta la rete di casa) si ripiega su github.com/<repo>/releases/latest, che non ha
quel limite: il tag si legge dall'indirizzo finale del redirect. Esito ed errori
finiscono in %APPDATA%/PokeMoba/updater.log.

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
import time
import traceback
import urllib.request
from pathlib import Path

from . import version

API = "https://api.github.com/repos/{repo}/releases/latest"
LATEST_PAGE = "https://github.com/{repo}/releases/latest"
DOWNLOAD = "https://github.com/{repo}/releases/download/{tag}/{asset}"
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


def _log(msg: str) -> None:
    """Riga in %APPDATA%/PokeMoba/updater.log (per capire perche' non si aggiorna)."""
    try:
        base = Path(os.environ.get("APPDATA") or Path.home()) / "PokeMoba"
        base.mkdir(parents=True, exist_ok=True)
        f = base / "updater.log"
        if f.exists() and f.stat().st_size > 64 * 1024:
            f.unlink()
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} v{version.BUILD} {msg}\n")
    except OSError:
        pass


UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 r"\{0C9E9176-62A4-451F-85CD-829548767599}_is1")   # AppId di installer/PokeMoba.iss


def sync_installed_version() -> None:
    """Se il gioco e' stato installato con PokeMoba-Setup.exe, tiene la versione
    mostrata in "App installate" di Windows allineata all'exe (che si aggiorna da
    solo senza ripassare dall'installer). Nessun effetto altrimenti."""
    if os.name != "nt" or version.BUILD <= 0:
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            want = version.name()
            try:
                if winreg.QueryValueEx(k, "DisplayVersion")[0] == want:
                    return
            except OSError:
                pass
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, want)
    except OSError:      # non installato (exe portatile) o registro non scrivibile
        pass


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
            sync_installed_version()
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
            found = self._latest()
            if found is None:
                self.state = "none"
                _log("nessuna release trovata")
                return
            build, dl_url, total, notes = found
            if build <= version.BUILD:
                self.state = "none"
                _log(f"gia' aggiornato (ultima v{build})")
                return
            self.new_build = build
            self.notes = notes
            self.state = "downloading"
            _log(f"scarico v{build} da {dl_url}")
            exe = _exe_path()
            dst = exe.with_name(exe.name + ".new")
            tmp = exe.with_name(exe.name + ".part")
            got = 0
            with self._get(dl_url, "application/octet-stream") as r, open(tmp, "wb") as f:
                if not total:
                    total = int(r.headers.get("Content-Length") or 0)
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
            _log(f"v{build} pronta ({got} byte)")
        except Exception as e:      # rete assente, GitHub giu', cartella non scrivibile...
            self.error = str(e)
            self.state = "error"
            _log("errore: " + traceback.format_exc().strip().replace("\n", " | "))

    def _latest(self):
        """(build, url dell'exe, dimensione o 0, note) dell'ultima Release, o None."""
        override = os.environ.get("POKEMOBA_UPDATE_URL")
        try:
            url = override or API.format(repo=version.REPO)
            with self._get(url, "application/vnd.github+json") as r:
                data = json.loads(r.read().decode("utf-8"))
            asset = next((a for a in data.get("assets", [])
                          if a.get("name") == version.ASSET), None)
            if asset is None:
                return None
            return (tag_build(data.get("tag_name", "")), asset["browser_download_url"],
                    int(asset.get("size") or 0), (data.get("body") or "").strip())
        except Exception as e:
            if override:
                raise
            _log(f"API non disponibile ({e}), uso github.com")
        # Ripiego senza limiti: github.com/<repo>/releases/latest -> .../tag/v<N>
        with self._get(LATEST_PAGE.format(repo=version.REPO), "text/html") as r:
            final = r.geturl()
        tag = final.rstrip("/").rsplit("/", 1)[-1]
        if "/tag/" not in final or not tag_build(tag):
            return None
        return (tag_build(tag), DOWNLOAD.format(repo=version.REPO, tag=tag,
                                                 asset=version.ASSET), 0, "")

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
            return f"Aggiornamento {version.name_of(self.new_build)}: download {int(self.progress * 100)}%"
        if self.state == "ready":
            return f"Aggiornamento {version.name_of(self.new_build)} pronto: si installa alla chiusura"
        return None
