"""HUD di partita (piena risoluzione), uguale offline e online.

- BARRA IN BASSO: statistiche | ritratto + livello | passiva + mosse Q W E R
  (nome leggibile DENTRO ogni casella) con, sotto, la barra della VITA e quella
  dell'ESPERIENZA verso il livello successivo | oggetti + oro.
- STRISCIA IN ALTO: tempo, vita dei due nuclei, squadre (vivi / respawn),
  prossima ondata e meteo.
- AVVISI al centro (richiamo, abbattuto, vittoria) e messaggi temporanei.
- POPUP delle evoluzioni: layout_popups li mette in fila sopra la barra
  senza sovrapporsi (ognuno il piu' vicino possibile alla sua casella).

Le scene costruiscono PlayerView/SlotView/MatchView dai loro dati (Match locale
o stato di rete) e chiamano le funzioni di disegno: nessuna logica di gioco qui.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from engine.stats import CUMULATIVE_XP, MAX_LEVEL

# --- palette ---------------------------------------------------------------------------
PANEL = (16, 19, 24)
PANEL_IN = (26, 30, 38)
TRIM = (150, 126, 68)          # cornice dorata
TRIM_HI = (226, 196, 116)
TEXT = (232, 232, 236)
DIM = (150, 152, 162)
GOLD = (246, 206, 92)
HP_HI, HP_LO = (98, 206, 92), (44, 128, 52)
HP_LOW = (226, 88, 70)
XP_HI, XP_LO = (154, 112, 236), (90, 60, 168)
BLUE, RED = (92, 160, 250), (240, 92, 84)

_FONTS: dict = {}


def font(size: int, bold: bool = False):
    key = (size, bold)
    f = _FONTS.get(key)
    if f is None:
        f = pygame.font.SysFont("consolas", size, bold=bold)
        _FONTS[key] = f
    return f


def text(surface, s, pos, size=14, col=TEXT, bold=False, center=False, right=False,
         shadow=True):
    """Testo con ombra netta (1px basso-destra): leggibile anche sopra la mappa."""
    f = font(size, bold)
    img = f.render(s, True, col)
    x, y = pos
    if center:
        x -= img.get_width() // 2
    elif right:
        x -= img.get_width()
    if shadow:
        surface.blit(f.render(s, True, (0, 0, 0)), (x + 1, y + 1))
    surface.blit(img, (x, y))
    return img.get_width()


def panel(surface, rect, alpha=236, trim=TRIM, radius=6):
    """Pannello scuro semitrasparente con cornice dorata e filo chiaro interno."""
    bg = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(bg, (*PANEL, alpha), bg.get_rect(), border_radius=radius)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, (0, 0, 0), rect.inflate(2, 2), 1, border_radius=radius + 1)
    pygame.draw.rect(surface, trim, rect, 1, border_radius=radius)


def bar(surface, rect, frac, hi, lo, back=(22, 24, 30), ticks=0):
    """Barra a due toni (luce in alto) con contorno scuro e tacche opzionali."""
    frac = max(0.0, min(1.0, frac))
    pygame.draw.rect(surface, back, rect)
    w = int(rect.w * frac)
    if w > 0:
        pygame.draw.rect(surface, lo, (rect.x, rect.y, w, rect.h))
        pygame.draw.rect(surface, hi, (rect.x, rect.y, w, max(1, rect.h // 2)))
    if ticks > 1:
        for i in range(1, ticks):
            tx = rect.x + rect.w * i // ticks
            pygame.draw.line(surface, (0, 0, 0), (tx, rect.y), (tx, rect.y + rect.h // 2))
    pygame.draw.rect(surface, (0, 0, 0), rect, 1)


def xp_progress(level: int, xp_total: float):
    """(xp nel livello, xp richiesta) per il livello corrente; None al massimo."""
    if level >= MAX_LEVEL:
        return None
    lo, hi = CUMULATIVE_XP[level], CUMULATIVE_XP[level + 1]
    return max(0.0, xp_total - lo), hi - lo


# --- dati che le scene passano ---------------------------------------------------------
@dataclass
class SlotView:
    key: str
    name: str = ""               # vuoto = nessuna mossa
    mtype: str = ""              # tipo (colore della casella)
    locked: str = ""             # testo al posto del nome (es. "Liv. 8")
    rank: int = 0
    max_rank: int = 4
    cd_left: float = 0.0
    cd_frac: float = 0.0         # 1 = appena usata
    charges: tuple | None = None  # (pronte, massimo, avanzamento della prossima)
    can_rank: bool = False       # c'e' un punto da spendere qui
    evolvable: bool = False      # potenziamento da scegliere


@dataclass
class PlayerView:
    name: str
    level: int
    xp: float                    # esperienza TOTALE
    hp: float
    max_hp: float
    portrait: object = None      # Surface o None
    gold: int = 0
    items: list = field(default_factory=list)
    stats: list = field(default_factory=list)   # [(etichetta, valore, segno)]
    alive: bool = True
    respawn_left: float = 0.0
    recall_left: float = 0.0
    recall_max: float = 0.0
    points: int = 0
    rank_hint: str = "clic sul + o Ctrl+tasto"
    team: int = 0


@dataclass
class MatchView:
    time: float
    cores: tuple = ((0.0, 1.0), (0.0, 1.0))      # (hp, max) BLU, ROSSO
    teams: tuple = ((), ())                       # per squadra: [respawn_left o 0 se vivo]
    next_wave: float | None = None
    weather: str = ""
    winner: int | None = None
    player_team: int = 0


@dataclass
class BarLayout:
    rect: pygame.Rect
    slot_rects: dict             # "Q" -> Rect della casella
    passive_at: tuple            # (x, y, h) dove disegnare la passiva


# --- misure della barra ----------------------------------------------------------------
SLOT = 52                        # altezza della casella della mossa (nome DENTRO)
SLOT_W = 72                      # larghezza
SLOT_GAP = 5
STATS_W = 100
PORT = 62
PASSIVE_W = 84                   # la piu larga (Armature) e bh + 30
ITEM = 27
ITEM_GAP = 3
BAR_H = 120


def bar_rect(W: int, H: int, right_limit: int | None = None) -> pygame.Rect:
    skills_w = 4 * SLOT_W + 3 * SLOT_GAP
    w = 8 + STATS_W + 8 + PORT + 10 + PASSIVE_W + skills_w + 10 + 3 * ITEM + 2 * ITEM_GAP + 8
    x = (W - w) // 2
    if right_limit is not None and x + w > right_limit - 8:
        x = max(4, right_limit - 8 - w)
    return pygame.Rect(x, H - BAR_H - 6, w, BAR_H)


def name_size(names, maxw: int) -> int:
    """Carattere UNICO per tutti i nomi della barra: il piu' grande (13..11) con
    cui ci stanno tutti su una riga; chi non ci sta comunque va a capo."""
    for size in (12, 11):
        f = font(size, True)
        if all(f.size(n)[0] <= maxw for n in names if n):
            return size
    return 11


def _wrap_name(name: str, maxw: int, size: int):
    """Una riga se ci sta, altrimenti due (sugli spazi, o col trattino)."""
    f = font(size, True)
    if f.size(name)[0] <= maxw:
        return [name]
    words = name.split()
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        wmax = max(f.size(a)[0], f.size(b)[0])
        if best is None or wmax < best[0]:
            best = (wmax, [a, b])
    if best is not None:
        return best[1]
    # parola unica: trattino a fine sillaba, alla buona ("Nitro-carica",
    # "Gigas-sorbimento", "Accom-pagnatore"), il piu' vicino a meta'
    vow = set("aeiouàèéìòùAEIOU")
    mid = len(name) / 2

    def syll(k):
        a, b, c = name[k - 1], name[k], name[k + 1]
        if a in vow and b not in vow and c in vow:              # V | C V
            return True
        z = name[k - 2]
        if not (z in vow and a not in vow and b not in vow and c in vow):   # V C | C V
            return False
        # doppie si dividono (s|s, t|t); "s+cons", "gn" e "cons+r/l/h" no
        return a == b or (a != "s" and a + b != "gn" and b not in "hrl")

    cuts = [k for k in range(3, len(name) - 2) if syll(k)
            and f.size(name[:k] + "-")[0] <= maxw and f.size(name[k:])[0] <= maxw]
    cut = min(cuts, key=lambda k: abs(k - mid)) if cuts else max(3, (len(name) + 1) // 2)
    return [name[:cut] + "-", name[cut:]]


def draw_slot(surface, r: pygame.Rect, s: SlotView, type_color, nsize: int = 11) -> None:
    """Casella della mossa col NOME DENTRO (in basso), tasto in alto a sinistra,
    "+" del grado in alto a destra, ricarica/cariche in alto al centro."""
    has = bool(s.name) and not s.locked
    tc = type_color(s.mtype) if has and s.mtype else (90, 92, 104)
    # fondo: tinta del tipo scura, con luce in alto e striscia del tipo in basso
    base = tuple(int(c * 0.30 + 12) for c in tc)
    pygame.draw.rect(surface, base, r, border_radius=5)
    hi = tuple(min(255, int(c * 0.50 + 18)) for c in tc)
    pygame.draw.rect(surface, hi, (r.x + 2, r.y + 2, r.w - 4, r.h // 3), border_radius=4)
    if has:
        pygame.draw.rect(surface, tc, (r.x + 3, r.bottom - 4, r.w - 6, 2))
    cx = r.centerx
    if has and s.rank == 0:          # non ancora imparata: casella spenta
        ov = pygame.Surface(r.size, pygame.SRCALPHA)
        ov.fill((8, 10, 14, 150))
        surface.blit(ov, r.topleft)
    # ricarica: velo che sale dal basso + secondi in alto al centro
    if s.cd_left > 0 and has:
        hh = int(r.h * max(0.0, min(1.0, s.cd_frac)))
        if hh > 0:
            ov = pygame.Surface((r.w, hh), pygame.SRCALPHA)
            ov.fill((6, 8, 12, 170))
            surface.blit(ov, (r.x, r.bottom - hh))
        t = f"{s.cd_left:.0f}" if s.cd_left >= 1.0 else f"{s.cd_left:.1f}"
        text(surface, t, (cx, r.y + 1), 16, (255, 255, 255), bold=True, center=True)
    # cariche: pallino col numero in alto al centro
    if s.charges is not None and has and s.rank > 0:
        whole, mx, prog = s.charges
        if whole == 0:
            hh = int(r.h * (1.0 - prog))
            ov = pygame.Surface((r.w, hh), pygame.SRCALPHA)
            ov.fill((6, 8, 12, 170))
            surface.blit(ov, r.topleft)
        badge = (120, 220, 140) if whole > 0 else (160, 160, 170)
        by = r.y + 10
        pygame.draw.circle(surface, (12, 16, 20), (cx, by), 8)
        pygame.draw.circle(surface, badge, (cx, by), 8, 1)
        text(surface, str(whole), (cx, by - 7), 12, badge, bold=True, center=True, shadow=False)
        if 0 < whole < mx:
            pr = pygame.Rect(r.x + 4, r.bottom - 7, int((r.w - 8) * prog), 2)
            pygame.draw.rect(surface, (120, 200, 140), pr)
    # nome dentro la casella, in basso (una o due righe)
    _draw_slot_name(surface, r, s, nsize)
    # cornice: oro se c'e' da scegliere l'evoluzione, verde se si puo' salire di grado
    if s.evolvable:
        frame = TRIM_HI
    elif s.can_rank:
        frame = (120, 220, 120)
    else:
        frame = (0, 0, 0)
    pygame.draw.rect(surface, frame, r, 2 if frame != (0, 0, 0) else 1, border_radius=5)
    # tasto in alto a sinistra
    kr = pygame.Rect(r.x + 2, r.y + 2, 15, 15)
    pygame.draw.rect(surface, (10, 12, 16), kr, border_radius=4)
    pygame.draw.rect(surface, TRIM, kr, 1, border_radius=4)
    text(surface, s.key, (kr.centerx, kr.y + 1), 12, GOLD, bold=True, center=True, shadow=False)
    # "+" per salire di grado: in alto a destra
    if s.can_rank:
        pc = (r.right - 9, r.y + 9)
        pygame.draw.circle(surface, (16, 40, 18), pc, 7)
        pygame.draw.circle(surface, (120, 220, 120), pc, 7, 2)
        pygame.draw.line(surface, (170, 255, 170), (pc[0] - 3, pc[1]), (pc[0] + 3, pc[1]), 2)
        pygame.draw.line(surface, (170, 255, 170), (pc[0], pc[1] - 3), (pc[0], pc[1] + 3), 2)
    # tacche del grado sotto la casella
    if s.max_rank > 0:
        pw = (r.w - 4) // s.max_rank
        for k in range(s.max_rank):
            pr = pygame.Rect(r.x + 2 + k * pw, r.bottom + 2, pw - 2, 4)
            pygame.draw.rect(surface, (126, 214, 112) if k < s.rank else (52, 56, 66), pr)
            pygame.draw.rect(surface, (0, 0, 0), pr, 1)


def _draw_slot_name(surface, r: pygame.Rect, s: SlotView, size: int) -> None:
    plus = False
    if s.locked:
        # lucchetto piccolo + testo
        cx, cy = r.centerx, r.y + 16
        pygame.draw.rect(surface, (120, 120, 130), (cx - 6, cy - 1, 12, 9), border_radius=2)
        pygame.draw.arc(surface, (120, 120, 130), (cx - 4, cy - 8, 8, 12), 0, 3.15, 2)
        lines, size, col = [s.locked], 11, DIM
    elif s.name:
        # "Mossa +" (variante potenziata): il "+" diventa un segno dorato a parte
        plus = s.name.endswith(" +")
        lines = _wrap_name(s.name[:-2] if plus else s.name, r.w - 6, size)
        col = (160, 162, 170) if (s.cd_left > 0 or s.rank == 0) else TEXT
    else:
        return
    lh = size + 1
    y = r.bottom - 6 - len(lines) * lh
    for k, ln in enumerate(lines):
        w = text(surface, ln, (r.centerx, y), size, col, bold=True, center=True)
        if plus and k == len(lines) - 1:
            text(surface, "+", (r.centerx + w // 2, y - 1), size, GOLD, bold=True)
        y += lh


def draw_bar(surface, pv: PlayerView, slots: list, type_color, item_icon=None,
             right_limit=None) -> BarLayout:
    """Barra in basso. `item_icon(iid, size)` -> Surface (icone del negozio)."""
    W, H = surface.get_size()
    R = bar_rect(W, H, right_limit)
    panel(surface, R)
    x = R.x + 8
    # --- statistiche --------------------------------------------------------------
    sr = pygame.Rect(x, R.y + 8, STATS_W, R.h - 16)
    pygame.draw.rect(surface, PANEL_IN, sr, border_radius=4)
    y = sr.y + 5
    for lab, val, mark in pv.stats:
        if not lab:      # riga senza etichetta (online: ruolo e tipi)
            text(surface, str(val), (sr.x + 5, y), 12, mark or TEXT, bold=True, shadow=False)
            y += 15
            continue
        text(surface, lab, (sr.x + 5, y), 12, DIM, shadow=False)
        col = (130, 230, 130) if mark == "+" else (240, 120, 110) if mark == "-" else TEXT
        text(surface, f"{val}{mark}", (sr.right - 5, y), 12, col, bold=True, right=True,
             shadow=False)
        y += 15
    # oro in fondo alle statistiche
    gy = sr.bottom - 18
    pygame.draw.line(surface, (52, 56, 66), (sr.x + 4, gy - 3), (sr.right - 4, gy - 3))
    pygame.draw.circle(surface, (150, 110, 30), (sr.x + 11, gy + 8), 6)
    pygame.draw.circle(surface, GOLD, (sr.x + 10, gy + 7), 5)
    pygame.draw.circle(surface, (255, 240, 170), (sr.x + 9, gy + 5), 1)
    text(surface, f"{pv.gold}", (sr.right - 5, gy), 14, GOLD, bold=True, right=True,
         shadow=False)
    x = sr.right + 8
    # --- ritratto + livello -------------------------------------------------------
    pr = pygame.Rect(x, R.y + 9, PORT, PORT)
    pygame.draw.rect(surface, (34, 40, 52), pr, border_radius=6)
    pygame.draw.rect(surface, (46, 54, 70), (pr.x + 3, pr.y + 3, pr.w - 6, pr.h // 2),
                     border_radius=5)
    if pv.portrait is not None:
        img = pv.portrait
        surface.blit(img, (pr.centerx - img.get_width() // 2,
                           pr.centery - img.get_height() // 2 + 2))
    if not pv.alive:
        ov = pygame.Surface(pr.size, pygame.SRCALPHA)
        ov.fill((10, 10, 14, 175))
        surface.blit(ov, pr.topleft)
        text(surface, f"{pv.respawn_left:.0f}", (pr.centerx, pr.centery - 12), 22,
             (255, 120, 100), bold=True, center=True)
    pygame.draw.rect(surface, TRIM_HI, pr, 2, border_radius=6)
    # livello: medaglione sul bordo basso del ritratto
    lc = (pr.centerx, pr.bottom)
    pygame.draw.circle(surface, (12, 14, 18), lc, 12)
    pygame.draw.circle(surface, TRIM_HI, lc, 12, 2)
    text(surface, str(pv.level), (lc[0], lc[1] - 8), 14, (255, 240, 200), bold=True,
         center=True, shadow=False)
    nm_size = 12 if font(12, True).size(pv.name)[0] <= PORT + 16 else 11
    text(surface, pv.name, (pr.centerx, pr.bottom + 14), nm_size, TEXT, bold=True, center=True)
    x = pr.right + 10
    # --- passiva + mosse ----------------------------------------------------------
    sy = R.y + 20
    passive_at = (x + 2, sy, SLOT)
    x += PASSIVE_W
    slot_rects = {}
    nsize = name_size([s.name.replace(" +", "+") for s in slots if not s.locked], SLOT_W - 6)
    for i, s in enumerate(slots):
        r = pygame.Rect(x + i * (SLOT_W + SLOT_GAP), sy, SLOT_W, SLOT)
        slot_rects[s.key] = r
        draw_slot(surface, r, s, type_color, nsize)
    skills_l = x - PASSIVE_W + 2
    skills_r = x + 4 * SLOT_W + 3 * SLOT_GAP
    # --- vita ed esperienza (sotto le mosse, larghe come passiva + mosse) ----------
    hb = pygame.Rect(skills_l, R.bottom - 28, skills_r - skills_l, 13)
    frac = pv.hp / max(1.0, pv.max_hp)
    hi, lo = (HP_HI, HP_LO) if frac > 0.3 else (HP_LOW, (150, 50, 40))
    bar(surface, hb, frac, hi, lo, ticks=max(1, int(pv.max_hp // 500)))
    text(surface, f"{int(pv.hp)} / {int(pv.max_hp)}", (hb.centerx, hb.y), 11,
         (255, 255, 255), bold=True, center=True)
    xb = pygame.Rect(skills_l, R.bottom - 14, skills_r - skills_l, 11)
    prog = xp_progress(pv.level, pv.xp)
    if prog is None:
        bar(surface, xb, 1.0, XP_HI, XP_LO)
        xp_txt = "ESPERIENZA - LIVELLO MASSIMO"
    else:
        have, need = prog
        bar(surface, xb, have / need, XP_HI, XP_LO)
        xp_txt = f"ESPERIENZA  {int(have)} / {int(need)}  ->  Lv.{pv.level + 1}"
    text(surface, xp_txt, (xb.centerx, xb.y - 1), 10, (236, 226, 255), bold=True, center=True)
    # --- oggetti ------------------------------------------------------------------
    ix = skills_r + 10
    iy = R.y + 10
    for k in range(6):
        cr = pygame.Rect(ix + (k % 3) * (ITEM + ITEM_GAP), iy + (k // 3) * (ITEM + ITEM_GAP),
                         ITEM, ITEM)
        pygame.draw.rect(surface, PANEL_IN, cr, border_radius=4)
        iid = pv.items[k] if k < len(pv.items) else None
        if iid and item_icon is not None:
            img = item_icon(iid, ITEM - 3)
            if img is not None:
                surface.blit(img, (cr.centerx - img.get_width() // 2,
                                   cr.centery - img.get_height() // 2))
        pygame.draw.rect(surface, (64, 68, 80), cr, 1, border_radius=4)
        text(surface, str(k + 1), (cr.x + 2, cr.bottom - 10), 9, DIM, shadow=False)
    icx = ix + (3 * ITEM + 2 * ITEM_GAP) // 2
    iy2 = iy + 2 * (ITEM + ITEM_GAP) + 4
    text(surface, "P: negozio", (icx, iy2), 11, DIM, center=True)
    text(surface, "B: richiamo", (icx, iy2 + 14), 11, DIM, center=True)
    # punti mossa da spendere: targhetta sopra la barra
    if pv.points > 0:
        msg = f"+{pv.points} punto mossa" if pv.points == 1 else f"+{pv.points} punti mossa"
        msg += f"  ({pv.rank_hint})"
        w = font(12, True).size(msg)[0] + 14
        tr = pygame.Rect(R.x, R.y - 22, w, 18)
        panel(surface, tr, trim=(120, 220, 120), radius=4)
        text(surface, msg, (tr.x + 7, tr.y + 2), 12, (150, 240, 150), bold=True, shadow=False)
    return BarLayout(R, slot_rects, passive_at)


def draw_top(surface, mv: MatchView, fps: float | None = None) -> None:
    """Striscia in alto: nuclei, tempo, squadre, ondata e meteo."""
    W, _ = surface.get_size()
    w = 470
    R = pygame.Rect(W // 2 - w // 2, 6, w, 46)
    panel(surface, R)
    t = int(mv.time)
    tr = pygame.Rect(R.centerx - 36, R.y + 4, 72, 24)
    text(surface, f"{t // 60:02d}:{t % 60:02d}", (tr.centerx, tr.y + 1), 20, (255, 244, 214),
         bold=True, center=True)
    for team in (0, 1):
        hp, mx = mv.cores[team]
        col = BLUE if team == 0 else RED
        dark = tuple(int(c * 0.55) for c in col)
        br = pygame.Rect(R.x + 12, R.y + 10, 140, 12) if team == 0 else \
            pygame.Rect(R.right - 152, R.y + 10, 140, 12)
        bar(surface, br, hp / max(1.0, mx), col, dark)
        lab = "BLU" if team == 0 else "ROSSO"
        if team == mv.player_team:
            lab += " (tu)"
        if team == 0:
            text(surface, lab, (br.x, br.bottom + 3), 12, col, bold=True)
        else:
            text(surface, lab, (br.right, br.bottom + 3), 12, col, bold=True, right=True)
        # pallini dei Pokémon: pieno = vivo, vuoto + secondi = in attesa di rinascere
        members = mv.teams[team]
        n = len(members)
        for k, left in enumerate(members):
            if team == 0:
                cx = br.right - 6 - (n - 1 - k) * 15
            else:
                cx = br.x + 6 + k * 15
            cy = br.bottom + 10
            if left <= 0:
                pygame.draw.circle(surface, col, (cx, cy), 5)
                pygame.draw.circle(surface, (0, 0, 0), (cx, cy), 5, 1)
            else:
                pygame.draw.circle(surface, (60, 60, 68), (cx, cy), 5)
                pygame.draw.circle(surface, dark, (cx, cy), 5, 1)
    sub = []
    if mv.next_wave is not None:
        sub.append(f"ondata {int(mv.next_wave)}s")
    if mv.weather:
        sub.append(mv.weather)
    if sub:
        text(surface, "  ".join(sub), (R.centerx, R.y + 28), 12, DIM, center=True)
    # tempi di rinascita dei caduti (sotto la striscia, per squadra)
    for team in (0, 1):
        dead = [x for x in mv.teams[team] if x > 0]
        if dead:
            col = BLUE if team == 0 else RED
            s = "rinasce " + ", ".join(f"{d:.0f}s" for d in sorted(dead))
            if team == 0:
                text(surface, s, (R.x + 6, R.bottom + 4), 12, col)
            else:
                text(surface, s, (R.right - 6, R.bottom + 4), 12, col, right=True)
    if fps is not None:
        text(surface, f"FPS {fps:.0f}", (W - 8, 6), 12, DIM, right=True)


def draw_banner(surface, title, sub="", col=(255, 230, 120), frac=None, y=None) -> None:
    """Avviso al centro (richiamo, abbattuto, vittoria), con barra opzionale."""
    W, H = surface.get_size()
    f = font(22, True)
    w = max(f.size(title)[0], font(14).size(sub)[0]) + 48
    h = 40 + (18 if sub else 0) + (10 if frac is not None else 0)
    # sotto la striscia in alto: non copre mai barra, popup o il proprio Pokémon
    R = pygame.Rect(W // 2 - w // 2, y if y is not None else 78, w, h)
    panel(surface, R, trim=col)
    text(surface, title, (R.centerx, R.y + 8), 22, col, bold=True, center=True)
    yy = R.y + 36
    if sub:
        text(surface, sub, (R.centerx, yy), 14, TEXT, center=True)
        yy += 18
    if frac is not None:
        bar(surface, pygame.Rect(R.x + 16, yy, R.w - 32, 6), frac, (150, 200, 255), (70, 110, 200))


def draw_messages(surface, lines, x=8, y=60) -> None:
    for ln in lines:
        text(surface, ln, (x, y), 14, TEXT)
        y += 18


def layout_popups(sizes, anchors, bottom: int, W: int, gap: int = 6) -> list:
    """Rettangoli per i popup (w, h) ognuno centrato sulla sua ancora x, in fila
    sopra `bottom` SENZA sovrapporsi: si spingono a destra quanto basta, poi si
    riportano dentro lo schermo; se la fila non ci sta si va a capo verso l'alto."""
    order = sorted(range(len(sizes)), key=lambda i: anchors[i])
    rows, cur, cur_w = [], [], 0
    for i in order:
        w = sizes[i][0]
        if cur and cur_w + gap + w > W - 8:
            rows.append(cur)
            cur, cur_w = [], 0
        cur.append(i)
        cur_w += (gap if cur_w else 0) + w
    if cur:
        rows.append(cur)
    out = [None] * len(sizes)
    y_bottom = bottom
    for row in rows:
        xs = []
        right = -10 ** 9
        for i in row:
            w = sizes[i][0]
            x = max(int(anchors[i] - w / 2), right + gap)
            xs.append(x)
            right = x + w
        # rientra a destra, poi a sinistra
        over = right - (W - 4)
        if over > 0:
            xs = [x - over for x in xs]
        if xs and xs[0] < 4:
            d = 4 - xs[0]
            xs = [x + d for x in xs]
        rh = max(sizes[i][1] for i in row)
        for i, x in zip(row, xs):
            w, h = sizes[i]
            out[i] = pygame.Rect(x, y_bottom - h, w, h)
        y_bottom -= rh + gap
    return out


# --- popup di scelta del potenziamento -------------------------------------------------
def choice_size(sl: str, moves: list) -> tuple:
    f = font(14, True)
    w = max([f.size(f"Evolvi {sl} - torna in BASE")[0]]
            + [f.size(f"{i + 1}. {mv.name}")[0] + 16 + font(11).size(mv.type)[0]
               for i, mv in enumerate(moves)])
    return w + 24, 32 + 24 * len(moves)


def draw_choice(surface, rect, title: str, moves: list, type_color, active: bool,
                title_col=GOLD) -> list:
    """Popup con le opzioni (nome + tipo). Ritorna i rettangoli delle righe se
    cliccabili (`active`), altrimenti []. La riga sotto il mouse si illumina."""
    panel(surface, rect, trim=TRIM_HI)
    text(surface, title, (rect.x + 10, rect.y + 6), 14, title_col, bold=True)
    mouse = pygame.mouse.get_pos()
    rows = []
    for i, mv in enumerate(moves):
        r = pygame.Rect(rect.x + 6, rect.y + 28 + i * 24, rect.w - 12, 22)
        if active:
            pygame.draw.rect(surface, (64, 70, 90) if r.collidepoint(mouse) else (38, 42, 54),
                             r, border_radius=4)
            rows.append(r)
        text(surface, f"{i + 1}. {mv.name}", (r.x + 6, r.y + 3), 14, TEXT, bold=True)
        tw = font(11).size(mv.type)[0]
        text(surface, mv.type, (r.right - 6 - tw, r.y + 5), 11, type_color(mv.type))
    return rows
