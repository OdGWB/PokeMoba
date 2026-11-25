"""Firma Ed25519 dell'exe delle Release (verificata da game/updater.py).

    python tools/release_sign.py keygen
        Crea una coppia di chiavi. Stampa la PUBBLICA (da mettere in
        game/version.py -> UPDATE_PUBKEY) e la PRIVATA (da mettere SOLO nel secret
        UPDATE_SIGNING_KEY del repo GitHub, e in un posto sicuro offline). La privata
        non va MAI committata.

    python tools/release_sign.py sign dist/PokeMoba.exe
        Firma lo sha256 dell'exe con la chiave privata della variabile d'ambiente
        UPDATE_SIGNING_KEY (64 cifre esadecimali) e scrive dist/PokeMoba.exe.sig
        (64 byte). La Release deve allegare entrambi i file.

    python tools/release_sign.py verify dist/PokeMoba.exe
        Controlla la firma con UPDATE_PUBKEY di game/version.py.

Si firma lo sha256 (32 byte) e non l'exe intero: l'updater calcola l'impronta
mentre scarica, senza rileggere ~100 MB.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _sha256(path: Path) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.digest()


def keygen() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption()).hex()
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw).hex()
    print(f"UPDATE_PUBKEY (game/version.py):\n  {pub}\n")
    print(f"UPDATE_SIGNING_KEY (secret del repo, NON committare):\n  {priv}")


def sign(exe: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    raw = os.environ.get("UPDATE_SIGNING_KEY", "").strip()
    if not raw:
        sys.exit("UPDATE_SIGNING_KEY non impostata")
    k = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw))
    sig = k.sign(_sha256(exe))
    out = exe.with_name(exe.name + ".sig")
    out.write_bytes(sig)
    print(f"firmato {exe.name} -> {out.name}")


def verify(exe: Path) -> None:
    from game import updater, version
    if not version.UPDATE_PUBKEY:
        sys.exit("UPDATE_PUBKEY vuota in game/version.py")
    sig = exe.with_name(exe.name + ".sig").read_bytes()
    ok = updater.verify_signature(_sha256(exe), sig, version.UPDATE_PUBKEY)
    print("firma valida" if ok else "FIRMA NON VALIDA")
    sys.exit(0 if ok else 1)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("keygen", "sign", "verify"):
        sys.exit(__doc__)
    if sys.argv[1] == "keygen":
        keygen()
    elif len(sys.argv) < 3:
        sys.exit(__doc__)
    elif sys.argv[1] == "sign":
        sign(Path(sys.argv[2]))
    else:
        verify(Path(sys.argv[2]))


if __name__ == "__main__":
    main()
