"""Glossario degli stati e degli effetti (enciclopedia), solo testi e colori.

GLOSSARY: (chiave, nome, colore, spiegazione) per la pagina "Stati ed effetti".
target_effects(m, text): nomi degli stati che la mossa fa SUBIRE al bersaglio, presi
dagli effetti del JSON e dalle parole del testo della mossa. Nessuna logica di gioco:
i numeri delle spiegazioni sono quelli del motore (engine/status, burn, poison...).
"""
from __future__ import annotations

import re

HARD = (235, 120, 95)
SOFT = (230, 200, 110)
DOT = (190, 150, 230)
DEBUFF = (150, 190, 230)
OTHER = (170, 200, 170)

# (chiave, nome, colore, spiegazione)
GLOSSARY = [
    ("_hard", "CONTROLLI FORTI", None,
     "Tolgono il controllo del Pokémon. La Tenacia ne accorcia la durata (tranne il lancio in "
     "aria); la Pulizia li toglie."),
    ("stun", "Stordimento", HARD,
     "Il Pokémon resta fermo: non si muove, non attacca e non usa mosse. Interrompe le "
     "cariche e le mosse a canale in corso."),
    ("freeze", "Congelamento", HARD,
     "Come lo stordimento, ma il Pokémon è chiuso in un blocco di ghiaccio: fermo, senza "
     "attacchi né mosse finché il ghiaccio non si scioglie."),
    ("sleep", "Sonno", HARD,
     "Il Pokémon dorme: non si muove e non agisce. Il primo danno lo SVEGLIA (tranne il Riposo, "
     "che non si interrompe e intanto cura). Alcune mosse fanno più danno a chi dorme."),
    ("airborne", "Lanciato in aria", HARD,
     "Il Pokémon viene sbalzato in aria: non si muove e non agisce finché non ricade. La "
     "Tenacia NON lo accorcia."),
    ("charm", "Affascinato", HARD,
     "Il Pokémon cammina verso chi l'ha affascinato senza poter attaccare né usare mosse."),
    ("fear", "Spaventato", HARD,
     "Il Pokémon scappa lontano dalla fonte della paura, a metà velocità (-50%), senza "
     "attaccare né usare mosse."),
    ("taunt", "Provocato", HARD,
     "Il Pokémon può solo attaccare con l'attacco base chi l'ha provocato e gli va incontro. "
     "Finisce prima se il provocatore muore, diventa non bersagliabile o si allontana oltre "
     "12 tile."),
    ("_soft", "CONTROLLI LEGGERI", None,
     "Limitano il Pokémon ma lo lasciano agire in parte."),
    ("root", "Immobilizzato / Paralizzato", SOFT,
     "Velocità zero: il Pokémon non può camminare né scattare, ma PUÒ ancora attaccare e usare "
     "mosse che non lo spostano."),
    ("silence", "Silenziato", SOFT,
     "Niente mosse Q W E R: il Pokémon può ancora camminare e usare l'attacco base."),
    ("confuse", "Confuso", SOFT,
     "Gli attacchi base del Pokémon colpiscono l'alleato più vicino invece del nemico scelto."),
    ("blind", "Accecato", SOFT,
     "Gli attacchi base del Pokémon mancano il bersaglio (nessun danno); le mosse funzionano."),
    ("slow", "Rallentato", SOFT,
     "Velocità di movimento ridotta della percentuale indicata (es. -40%) per qualche secondo."),
    ("dashlock", "Niente scatti", SOFT,
     "Il Pokémon non può usare mosse di scatto, balzo o teletrasporto."),
    ("push", "Respinto", SOFT,
     "Il Pokémon viene spinto via di qualche tile. Se sbatte contro un muro alcune mosse lo "
     "stordiscono."),
    ("smoke", "Nel fumo", SOFT,
     "Dentro il fumo la visione del Pokémon scende a 3 tile: vede pochissimo attorno a sé."),
    ("_dot", "DANNI NEL TEMPO", None,
     "Fanno danno a intervalli finché durano."),
    ("burn", "Scottatura", DOT,
     "Ogni secondo il 2,5% degli HP massimi per 4 s e -25% di Attacco: brucia di più i "
     "Pokémon con tanta vita e indebolisce i fisici."),
    ("poison", "Veleno", DOT,
     "Danno a intervalli per qualche secondo. Le scaglie di Venomoth si ACCUMULANO fino a 6 "
     "(gocce viola sotto la barra, verdi al massimo). I tipi Acciaio sono immuni."),
    ("_debuff", "INDEBOLIMENTI", None,
     "Non fermano il Pokémon ma lo rendono più debole per un po'."),
    ("def_debuff", "Difesa ridotta", DEBUFF,
     "Meno Difesa: i colpi FISICI gli fanno più male."),
    ("spdef_debuff", "Dif. Sp. ridotta", DEBUFF,
     "Meno Difesa Speciale: i colpi SPECIALI gli fanno più male."),
    ("atk_debuff", "Attacco / Att. Sp. ridotti", DEBUFF,
     "Il Pokémon fa meno danno con i colpi fisici o speciali."),
    ("healcut", "Cure ridotte", DEBUFF,
     "Le cure ricevute (mosse, oggetti, rubavita) sono ridotte. Cuoricino verde spezzato "
     "accanto alla barra della vita."),
    ("itemlock", "Oggetti disattivati", DEBUFF,
     "Gli effetti unici degli oggetti non si attivano; le statistiche degli oggetti restano. "
     "Lucchetto accanto alla barra della vita."),
    ("_other", "ALTRI SEGNI", None,
     "Effetti di una sola linea, visibili a tutti sopra o sotto la barra della vita."),
    ("agitated", "Agitato", OTHER,
     "Segno di Hatterene (vena rossa): l'agitato si vede anche nei cespugli e subisce +10% "
     "di danno da Hatterene."),
    ("charge", "Carica magnetica + / -", OTHER,
     "Segno di Magnezone: cariche uguali si respingono, opposte si attraggono."),
    ("frost", "Gelo", OTHER,
     "Accumuli di Mamoswine (croci azzurre): a 4 accumuli il colpo successivo congela."),
    ("lock", "Agganciato (Prendimira)", OTHER,
     "Mirino di Octillery sopra la barra: i suoi colpi successivi su quel bersaglio sono "
     "potenziati."),
    ("untargetable", "Non bersagliabile", OTHER,
     "Il Pokémon non può essere preso di mira da attacchi e mosse a bersaglio per un istante "
     "(scatti, tuffi, Sub...)."),
    ("_def", "DIFESE", None,
     "Come ci si protegge dai controlli."),
    ("tenacity", "Tenacia", OTHER,
     "Accorcia la durata dei controlli subiti (non del lancio in aria). Viene da oggetti e "
     "passive."),
    ("cleanse", "Pulizia", OTHER,
     "Toglie rallentamento, stordimento, congelamento, sonno, immobilizzazione, veleno, "
     "confusione, silenzio, paura, fascino, cecità e i cali di Difesa / Dif. Sp."),
    ("unstoppable", "Inarrestabile", OTHER,
     "Per la durata il Pokémon ignora i controlli: non può essere fermato."),
]

NAME = {k: n for k, n, _c, _t in GLOSSARY if not k.startswith("_")}
COLOR = {k: c for k, _n, c, _t in GLOSSARY if c}

# chiavi degli effetti del JSON -> stato del glossario
_EFF = [
    ("stun", "stun"), ("crash_stun", "stun"), ("slam_stun", "stun"), ("wall_stun", "stun"),
    ("agitated_stun", "stun"), ("stun_chance", "stun"),
    ("freeze", "freeze"), ("freeze_time", "freeze"), ("frost_stacks", "frost"),
    ("sleep", "sleep"), ("airborne", "airborne"), ("air", "airborne"),
    ("fear", "fear"), ("taunt", "taunt"),
    ("root", "root"), ("paralyze", "root"), ("para", "root"),
    ("silence", "silence"), ("confuse", "confuse"), ("confuse_chance", "confuse"),
    ("release_confuse", "confuse"), ("blind", "blind"),
    ("slow", "slow"), ("foe_slow", "slow"), ("storm_slow", "slow"), ("ice_slow", "slow"),
    ("dashlock", "dashlock"), ("push", "push"), ("knockback", "push"),
    ("burn", "burn"), ("fire_chance", "burn"), ("poison", "poison"),
    ("def_debuff", "def_debuff"), ("spdef_debuff", "spdef_debuff"),
    ("atk_debuff", "atk_debuff"), ("foe_atk", "atk_debuff"), ("spa_down_target", "atk_debuff"),
    ("healcut", "healcut"), ("itemlock", "itemlock"),
]
# parole del testo della mossa -> stato
_WORDS = [
    (r"stord", "stun"), (r"congel|ghiaccio che blocca|blocco di ghiaccio", "freeze"),
    (r"addorment|\bsonno\b", "sleep"), (r"lanciat\w* in aria|sbalz\w* in aria|in aria per", "airborne"),
    (r"affascin", "charm"), (r"spavent|paura", "fear"), (r"provoca", "taunt"),
    (r"immobilizz|paralizz|bloccat\w* sul posto|fermi sul posto|bloccati sul posto", "root"),
    (r"silenzi", "silence"), (r"confus", "confuse"), (r"accecat|acceca", "blind"),
    (r"rallent", "slow"), (r"respin|spint\w* via|scaraventa|scaglia", "push"),
    (r"scottat|scotta", "burn"), (r"avvelen|\bveleno\b", "poison"),
    (r"(perd|cal|ridu|abbass)\w*[^.]{0,30}\bdifesa\b(?! sp)|-\d+% di difesa", "def_debuff"),
    (r"(perd|cal|ridu|abbass)\w*[^.]{0,30}dif\. ?sp", "spdef_debuff"),
    (r"(perd|cal|ridu|abbass)\w*[^.]{0,30}(\battacco\b|att\. ?sp)", "atk_debuff"),
    (r"cure ridotte|riduc\w* le cure|cure dimezzat", "healcut"),
    (r"oggetti disattivat|disattiva gli oggetti", "itemlock"),
    (r"\bfumo\b", "smoke"), (r"agitat", "agitated"), (r"\bgelo\b", "frost"),
    (r"caric\w* magnetic|carica [+-]|polarit", "charge"),
]
_WORDS_RE = [(re.compile(p), k) for p, k in _WORDS]
_SELF = re.compile(r"(su di sé|se stess|sé stess)")

ORDER = [k for k, *_ in GLOSSARY if not k.startswith("_")]


_CLAUSE = re.compile(r"[.;:,]|\bma\b|\bpoi\b|\be\b")


def _foe_text(text, own=()):
    """Il testo senza le frasi che parlano del lanciatore (nomi della linea, 'su di sé')."""
    own = [n.lower() for n in own if n]
    keep = []
    for c in _CLAUSE.split((text or "").lower()):
        if _SELF.search(c) or any(n in c for n in own):
            continue
        keep.append(c)
    return " | ".join(keep)


def target_effects(m, text="", own=()):
    """Chiavi del glossario che la mossa infligge ai NEMICI, in ordine di gravità.
    own: nomi delle forme della linea; le frasi che li nominano parlano del lanciatore."""
    if m.get("target") in ("self", "ally") and m.get("shape") == "buff":
        return []
    eff = m.get("effects") or {}
    found = {k for e, k in _EFF if e in eff}
    t = _foe_text(text, own)
    for rx, k in _WORDS_RE:
        if rx.search(t):
            found.add(k)
    return [k for k in ORDER if k in found]


def target_line(m, text="", own=()):
    """'Stordimento, Rallentato' oppure '' se la mossa non infligge stati."""
    return ", ".join(NAME[k] for k in target_effects(m, text, own))
