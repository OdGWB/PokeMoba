"""Compila il motore Rust (native/) e lo installa nel Python in uso.

Usato da ci.yml, release.yml e crea_exe.bat: un solo modo di costruirlo, cosi'
l'exe pubblicato ha lo stesso motore di quello provato nei test.
Servono Rust (https://rustup.rs) e maturin (requirements-build.txt).

    python tools/build_native.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory() as out:
        # --locked: le versioni di Cargo.lock, mai altre.
        subprocess.run([sys.executable, "-m", "maturin", "build", "--release", "--locked",
                        "--manifest-path", str(ROOT / "native" / "Cargo.toml"),
                        "--interpreter", sys.executable, "--out", out], check=True)
        wheel = next(Path(out).glob("pokemoba_native-*.whl"))
        # --force-reinstall: la versione del pacchetto non cambia a ogni modifica.
        subprocess.run([sys.executable, "-m", "pip", "install", "--force-reinstall",
                        "--no-deps", str(wheel)], check=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode or 1)
