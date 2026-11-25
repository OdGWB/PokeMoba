"""Firma Ed25519 dell'exe delle Release (verificata da game/updater.py).

    python tools/release_sign.py setup
        Il modo consigliato, una volta sola: crea la coppia di chiavi, manda la
        PRIVATA direttamente nel secret UPDATE_SIGNING_KEY dell'environment "release"
        del repo (con il comando gh, gia' collegato; l'environment va creato prima e
        limitato al branch main, cosi' solo i workflow di main leggono la chiave)
        senza mai stamparla ne' salvarla su disco, e scrive la
        PUBBLICA in game/version.py -> UPDATE_PUBKEY. Nessuno deve custodire chiavi:
        da li' in poi firma release.yml. Se il secret andasse perso, gli exe
        installati non accetterebbero piu' aggiornamenti e andrebbero reinstallati a
        mano (PokeMoba-Setup.exe); per questo il comando si rifiuta se UPDATE_PUBKEY
        e' gia' impostata (--force per sostituirla apposta).

    python tools/release_sign.py keygen
        Crea una coppia di chiavi. Stampa la PUBBLICA (da mettere in
        game/version.py -> UPDATE_PUBKEY) e la PRIVATA (da mettere SOLO nel secret
        UPDATE_SIGNING_KEY del repo GitHub, e in un posto sicuro offline). La privata
        non va MAI committata.

    python tools/release_sign.py sign dist/PokeMoba.exe
        Firma sha256 dell'exe + numero di build (game/version.py -> BUILD, che
        release.yml imposta prima della build) con la chiave privata della variabile
        d'ambiente UPDATE_SIGNING_KEY (64 cifre esadecimali) e scrive
        dist/PokeMoba.exe.sig (64 byte). La Release deve allegare entrambi i file.

    python tools/release_sign.py verify dist/PokeMoba.exe
        Controlla la firma con UPDATE_PUBKEY e BUILD di game/version.py.

Si firma lo sha256 (32 byte) e non l'exe intero: l'updater calcola l'impronta
mentre scarica, senza rileggere ~100 MB. Il messaggio firmato e' quello di
game/updater.signed_message: includere il build impedisce di ripubblicare un
vecchio exe firmato sotto un tag piu' alto (downgrade).
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = "release"      # environment di GitHub (solo main) con il secret della firma
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


def setup(force: bool = False) -> None:
    import re
    import shutil
    import subprocess
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from game import version
    vfile = ROOT / "game" / "version.py"
    if version.UPDATE_PUBKEY and not force:
        sys.exit("UPDATE_PUBKEY e' gia' impostata: sostituirla fa rifiutare gli "
                 "aggiornamenti agli exe installati. Usa --force solo se lo vuoi davvero.")
    gh = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption()).hex()
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw).hex()
    # La privata passa a gh solo dallo stdin: mai sullo schermo, su disco o negli argomenti.
    r = subprocess.run([gh, "secret", "set", "UPDATE_SIGNING_KEY", "--env", ENVIRONMENT],
                       input=priv,
                       text=True, cwd=ROOT, capture_output=True)
    del priv, k
    if r.returncode:
        sys.exit("gh secret set non riuscito (nessuna modifica a game/version.py): "
                 + (r.stderr or r.stdout).strip())
    s = vfile.read_text(encoding="utf-8")
    s, n = re.subn(r'^UPDATE_PUBKEY = ".*?"', f'UPDATE_PUBKEY = "{pub}"', s, flags=re.M)
    if n != 1:
        sys.exit(f"UPDATE_PUBKEY non trovata in game/version.py; mettila a mano: {pub}")
    vfile.write_text(s, encoding="utf-8")
    print(f"Secret UPDATE_SIGNING_KEY impostato nell'environment {ENVIRONMENT!r} "
          "(la chiave privata non e' stata mostrata ne' salvata).")
    print(f"UPDATE_PUBKEY scritta in game/version.py: {pub}")
    print("Ora committa game/version.py: le Release successive saranno firmate.")


def sign(exe: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from game import updater, version
    raw = os.environ.get("UPDATE_SIGNING_KEY", "").strip()
    if not raw:
        sys.exit("UPDATE_SIGNING_KEY non impostata")
    if version.BUILD <= 0:
        sys.exit("BUILD = 0 in game/version.py: si firma solo un exe di una Release")
    k = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw))
    sig = k.sign(updater.signed_message(_sha256(exe), version.BUILD))
    out = exe.with_name(exe.name + ".sig")
    out.write_bytes(sig)
    print(f"firmato {exe.name} (build {version.BUILD}) -> {out.name}")


def verify(exe: Path) -> None:
    from game import updater, version
    if not version.UPDATE_PUBKEY:
        sys.exit("UPDATE_PUBKEY vuota in game/version.py")
    sig = exe.with_name(exe.name + ".sig").read_bytes()
    ok = updater.verify_signature(_sha256(exe), version.BUILD, sig, version.UPDATE_PUBKEY)
    print("firma valida" if ok else "FIRMA NON VALIDA")
    sys.exit(0 if ok else 1)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("setup", "keygen", "sign", "verify"):
        sys.exit(__doc__)
    if sys.argv[1] == "setup":
        setup(force="--force" in sys.argv[2:])
    elif sys.argv[1] == "keygen":
        keygen()
    elif len(sys.argv) < 3:
        sys.exit(__doc__)
    elif sys.argv[1] == "sign":
        sign(Path(sys.argv[2]))
    else:
        verify(Path(sys.argv[2]))


if __name__ == "__main__":
    main()
