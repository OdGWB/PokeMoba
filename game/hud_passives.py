"""Indicatori delle PASSIVE accanto alla barra delle mosse (uguali offline e online).

Corpofunesto (anime), Inversione, Muta, Sabbiafiume, I 108 Spiriti e la linea
Eevee (Adattabilità prima dell'evoluzione, poi la passiva della forma).
`p` è il Pokémon del giocatore: offline quello del motore, online l'entità
ricostruita a cui OnlineMatchScene ha copiato i campi dello stato visivo.
`ctx` porta ciò che non sta sul Pokémon: tempo, ritratti, pioggia e meteo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame

from engine.eevee import eevee_candidates, eevee_forms

from . import eevee_fx, ursa_fx


@dataclass
class PassiveCtx:
    now: float
    portrait: Callable           # (sprite_dir, lato) -> Surface o None
    in_rain: bool = False
    weather: str = "clear"


def draw_passive(surface, font, p, bx, y0, bh, ctx) -> None:
    """Indicatore della passiva di `p` con l'angolo in alto a sinistra in (bx, y0)."""
    now = ctx.now
    # Cariche d'anima (passiva Corpofunesto): visibili in interfaccia.
    if p.passive_id == "corpofunesto":
        cz = p.soul_charges
        pygame.draw.rect(surface, (40, 28, 56), pygame.Rect(bx, y0, 16, bh))
        fill = int(bh * min(1.0, cz / 100.0))
        pygame.draw.rect(surface, (170, 90, 230), pygame.Rect(bx, y0 + bh - fill, 16, fill))
        pygame.draw.rect(surface, (210, 170, 240), pygame.Rect(bx, y0, 16, bh), 1)
        surface.blit(font.render(f"Anime {cz}", True, (210, 170, 240)), (bx - 6, y0 - 18))
    # Cariche d'Inversione (passiva linea Snivy).
    if p.passive_id == "inversione":
        iz = p.inversion_stacks
        pygame.draw.rect(surface, (24, 40, 28), pygame.Rect(bx, y0, 16, bh))
        fill = int(bh * min(1.0, iz / 100.0))
        pygame.draw.rect(surface, (110, 215, 130), pygame.Rect(bx, y0 + bh - fill, 16, fill))
        pygame.draw.rect(surface, (170, 230, 180), pygame.Rect(bx, y0, 16, bh), 1)
        surface.blit(font.render(f"Inv {iz}", True, (170, 230, 180)), (bx - 6, y0 - 18))
    # Passiva Muta (linea Nincada): ricarica e stato della forma Shedinja.
    if p.passive_id == "muta":
        in_form = getattr(p, "form", "") == "shedinja"
        cd_left = max(0.0, p.muta_cd_until - now)
        ready = cd_left <= 0.0 and not in_form
        frame = (230, 200, 120) if ready else (120, 110, 90)
        pygame.draw.rect(surface, (40, 36, 24), pygame.Rect(bx, y0, 16, bh))
        frac = 1.0 - min(1.0, cd_left / max(1.0, p.muta_cd_max))
        fill = int(bh * (1.0 if ready else frac))
        col = (235, 210, 110) if ready else (150, 140, 70)
        pygame.draw.rect(surface, col, pygame.Rect(bx, y0 + bh - fill, 16, fill))
        pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 1)
        surface.blit(font.render("Muta", True, frame), (bx - 6, y0 - 18))
        if in_form:
            left = max(0.0, p.form_until - now)
            tag = font.render(f"SHEDINJA {left:0.1f}s", True, (210, 180, 240))
            surface.blit(tag, (bx - tag.get_width() // 2 + 8, y0 + bh + 2))
        elif not ready:
            t = font.render(f"{cd_left:0.0f}s", True, frame)
            surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))

    # Passiva Sabbiafiume (linea Roggenrola): tempesta attiva da Gigalith,
    # raddoppiata da Terrempesta (barra = tempo rimasto del raddoppio).
    if p.passive_id == "sabbiafiume":
        boost = max(0.0, p.sandstorm_boost_until - now)
        on = p.sand_radius > 0.0
        frame = (226, 196, 130) if on else (120, 108, 86)
        pygame.draw.rect(surface, (44, 36, 24), pygame.Rect(bx, y0, 16, bh))
        fill = int(bh * (min(1.0, boost / 4.0) if boost > 0 else (1.0 if on else 0.0)))
        col = (250, 200, 110) if boost > 0 else (200, 168, 104)
        pygame.draw.rect(surface, col, pygame.Rect(bx, y0 + bh - fill, 16, fill))
        pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 1)
        surface.blit(font.render("Sabbia", True, frame), (bx - 10, y0 - 18))
        if boost > 0:
            t = font.render(f"x2 {boost:0.1f}s", True, (250, 210, 130))
            surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))
        elif not on:
            t = font.render("liv.8", True, frame)
            surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))

    # Passiva I 108 Spiriti (Spiritomb): cariche raccolte (max 108), tacche dei
    # risvegli a 36/72 e Spirito Vagante pronto (riquadro acceso).
    if p.passive_id == "108spiriti":
        ready = now >= p.wander_ready_at
        frame = (214, 255, 128) if ready else (110, 150, 70)
        pygame.draw.rect(surface, (22, 34, 18), pygame.Rect(bx, y0, 16, bh))
        fill = int(bh * min(1.0, p.spirit_charges / 108.0))
        pygame.draw.rect(surface, (150, 230, 50), pygame.Rect(bx, y0 + bh - fill, 16, fill))
        for n in (36, 72):
            ty = y0 + bh - int(bh * n / 108.0)
            pygame.draw.line(surface, (240, 255, 200), (bx, ty), (bx + 15, ty))
        pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 2 if ready else 1)
        surface.blit(font.render(f"Spiriti {p.spirit_charges}", True, frame), (bx - 14, y0 - 18))
        if not ready:
            t = font.render(f"{p.wander_ready_at - now:0.0f}s", True, frame)
            surface.blit(t, (bx - t.get_width() // 2 + 8, y0 + bh + 2))

    # Linea Rookidee: Sguardofermo (occhio) / Specchiarmatura (scudo d'acciaio).
    if p.passive_id in ("sguardofermo", "specchiarmatura"):
        mirror = p.passive_id == "specchiarmatura"
        frame = (196, 206, 230) if mirror else (246, 196, 72)
        pygame.draw.rect(surface, (26, 30, 48), pygame.Rect(bx, y0, 16, bh))
        cx, cy = bx + 8, y0 + bh // 2
        if mirror:   # scudo a specchio con riflesso
            pts = [(cx - 6, cy - 7), (cx + 6, cy - 7), (cx + 6, cy + 1), (cx, cy + 8), (cx - 6, cy + 1)]
            pygame.draw.polygon(surface, (140, 150, 180), pts)
            pygame.draw.polygon(surface, (240, 244, 255), pts, 1)
            pygame.draw.line(surface, (255, 255, 255), (cx - 3, cy - 5), (cx - 3, cy + 1))
        else:        # occhio vigile
            pygame.draw.ellipse(surface, (240, 236, 220), pygame.Rect(cx - 7, cy - 4, 14, 8))
            pygame.draw.circle(surface, (200, 60, 50), (cx, cy), 3)
            pygame.draw.circle(surface, (20, 20, 20), (cx, cy), 1)
        pygame.draw.rect(surface, frame, pygame.Rect(bx, y0, 16, bh), 1)
        name = "Specchiarm." if mirror else "Sguardofermo"
        surface.blit(font.render(name, True, frame), (bx - 18, y0 - 18))

    # Linea Charcadet: Armature (barre e forma verso cui va), Guardia, Doppia Lama.
    if p.passive_id == "armature":
        _draw_armature(surface, font, p, bx, y0, bh, ctx)
    elif p.passive_id in ("guardia", "doppialama"):
        _draw_charcadet_form(surface, font, p, bx, y0, bh, ctx)

    # Linea Noibat: Ecolocalizzazione (onde sonore + cariche del ping).
    if p.passive_id == "ecolocalizzazione":
        _draw_echo(surface, font, p, bx, y0, bh, ctx)

    # Linea Teddiursa: Miele (vasetti) e, da Ursaring, Dentistretti.
    if p.passive_id in ("miele", "dentistretti"):
        _draw_honey(surface, font, p, bx, y0, bh, ctx)

    # Linea Eevee: Adattabilità (prima dell'evoluzione) o passiva della forma.
    if p.passive_id == "adattabilita":
        _draw_adaptability(surface, font, p, bx, y0, bh, ctx)
    elif p.passive_id in eevee_fx.PASSIVE_NAMES:
        _draw_form_passive(surface, font, p, bx, y0, bh, ctx)


def _draw_adaptability(surface, font, p, bx, y0, bh, ctx) -> None:
    """Passiva Adattabilità (Eevee): icona della forma verso cui vanno le scelte
    ("?" senza scelte; con più forme possibili scorre tra quelle) e barra con
    gli 8 colori delle forme (accese quelle ancora raggiungibili)."""
    forms = eevee_forms(p)
    cands = eevee_candidates(p)
    now = ctx.now
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (24, 22, 30), box)
    one = cands[0] if len(cands) == 1 else None
    if len(cands) == len(forms):
        q = font.render("?", True, (235, 225, 200))
        q = pygame.transform.scale(q, (q.get_width() * 2, q.get_height() * 2))
        surface.blit(q, (box.centerx - q.get_width() // 2, box.centery - q.get_height() // 2))
        frame = (120, 112, 100)
    else:
        show = one or cands[int(now / 0.8) % len(cands)]
        img = ctx.portrait(show["sprite_dir"], bh - 10)
        if img is not None:
            if one is None:
                img = img.copy()
                img.set_alpha(150)   # ancora incerto: ritratto attenuato
            surface.blit(img, (box.centerx - img.get_width() // 2,
                               box.centery - img.get_height() // 2))
        frame = tuple(show["form_color"])
    pygame.draw.rect(surface, frame, box, 2 if one else 1)
    # Barra degli 8 colori (verticale, accanto all'icona).
    seg_h = bh // len(forms)
    bar_x = box.right + 4
    for i, st in enumerate(forms):
        col = tuple(st["form_color"])
        on = st in cands
        if not on:
            col = tuple(int(c * 0.22 + 20) for c in col)
        r = pygame.Rect(bar_x, y0 + i * seg_h, 10, seg_h - 1)
        pygame.draw.rect(surface, col, r)
        if on and one is not None:
            pygame.draw.rect(surface, (255, 255, 255), r.inflate(2, 2), 1)
    pygame.draw.rect(surface, (90, 86, 96), pygame.Rect(bar_x - 1, y0 - 1, 12, seg_h * len(forms) + 1), 1)
    title = one["name"] if one else ("Adattabilità" if len(cands) == len(forms)
                                     else f"{len(cands)} forme")
    tcol = tuple(one["form_color"]) if one else (225, 215, 190)
    if one and sum(tcol) < 200:   # Umbreon (nero): testo leggibile
        tcol = (200, 200, 215)
    surface.blit(font.render(title, True, tcol), (bx - 4, y0 - 18))


def _draw_form_passive(surface, font, p, bx, y0, bh, ctx) -> None:
    """Passiva della forma evoluta di Eevee: ritratto + nome + stato."""
    st = next((e for e in p.evolutions if e.get("dex") == p.dex), None)
    if st is None:
        return
    now = ctx.now
    col = tuple(st.get("form_color", (200, 200, 200)))
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (24, 22, 30), box)
    img = ctx.portrait(st["sprite_dir"], bh - 10)
    if img is not None:
        surface.blit(img, (box.centerx - img.get_width() // 2, box.centery - img.get_height() // 2))
    info = ""
    lit = True
    if p.passive_id == "assorbivolt":
        left = p.voltabsorb_ready_at - now
        lit = left <= 0
        info = "pronto" if lit else f"{left:0.0f}s"
    elif p.passive_id == "fuocardore":
        left = p.flashfire_until - now
        lit = left > 0
        info = f"+30% {left:0.1f}s" if lit else ""
    elif p.passive_id == "idratazione":
        lit = ctx.in_rain
        info = "pioggia" if lit else ""
    elif p.passive_id == "fogliamanto":
        lit = ctx.weather == "sun"
        info = "sole" if lit else ""
    frame = col if lit else tuple(int(c * 0.5) for c in col)
    if sum(frame) < 200:
        frame = (150, 150, 170)
    pygame.draw.rect(surface, frame, box, 2 if lit else 1)
    name = eevee_fx.PASSIVE_NAMES.get(p.passive_id, p.passive_id)
    if info:
        name += f" {info}"
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


ARM_FAUSTA = (236, 74, 70)      # Armatura Fausta -> Armarouge (rosso)
ARM_INFAUSTA = (110, 132, 250)  # Armatura Infausta -> Ceruledge (blu)


def _draw_armature(surface, font, p, bx, y0, bh, ctx) -> None:
    """Passiva Armature (Charcadet): ritratto della forma verso cui sta andando
    (Armarouge se Fausta > Infausta, altrimenti Ceruledge) e le due barre."""
    fa, inf = float(getattr(p, "fausta", 0.0)), float(getattr(p, "infausta", 0.0))
    to_arma = fa > inf
    name = "Armarouge" if to_arma else "Ceruledge"
    st = next((e for e in p.evolutions if e.get("name") == name), None)
    col = ARM_FAUSTA if to_arma else ARM_INFAUSTA
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (30, 20, 22), box)
    if st is not None:
        img = ctx.portrait(st["sprite_dir"], bh - 10)
        if img is not None:
            if fa == inf == 0.0:
                img = img.copy()
                img.set_alpha(120)   # ancora nessun danno: forma incerta
            surface.blit(img, (box.centerx - img.get_width() // 2,
                               box.centery - img.get_height() // 2))
    pygame.draw.rect(surface, col, box, 2)
    top = max(1.0, fa, inf)
    for i, (v, c, lab) in enumerate(((fa, ARM_FAUSTA, "F"), (inf, ARM_INFAUSTA, "I"))):
        # barra + lettera sotto, tutto dentro l'altezza del riquadro
        r = pygame.Rect(box.right + 4 + i * 13, y0, 10, bh - 16)
        pygame.draw.rect(surface, (24, 20, 26), r)
        fill = int((r.h - 2) * min(1.0, v / top))
        pygame.draw.rect(surface, c, pygame.Rect(r.x + 1, r.bottom - 1 - fill, r.w - 2, fill))
        lead = (i == 0) == to_arma
        pygame.draw.rect(surface, (255, 255, 255) if lead else (90, 84, 96), r, 1)
        t = font.render(lab, True, c)
        surface.blit(t, (r.centerx - t.get_width() // 2, r.bottom))
    surface.blit(font.render(f"Armature -> {name}", True, col), (bx - 4, y0 - 18))


def _draw_charcadet_form(surface, font, p, bx, y0, bh, ctx) -> None:
    """Guardia (Armarouge: scudo dorato, ricarica) o Doppia Lama (Ceruledge:
    due spade incrociate)."""
    guard = p.passive_id == "guardia"
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (30, 20, 22) if guard else (20, 20, 36), box)
    cx, cy = box.center
    s = bh // 2 - 10
    if guard:
        left = getattr(p, "guard_ready_at", 0.0) - ctx.now
        lit = left <= 0
        gold = (246, 200, 84) if lit else (130, 110, 70)
        pts = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
        pygame.draw.polygon(surface, (206, 40, 52) if lit else (96, 40, 44), pts)
        pygame.draw.polygon(surface, gold, pts, 2)
        pygame.draw.line(surface, gold, (cx, cy - s + 3), (cx, cy + s - 4), 2)
        frame = gold
        name = "Guardia" if lit else f"Guardia {left:0.0f}s"
    else:
        for side in (-1, 1):   # due lame incrociate: elsa in basso, punta in alto
            a = (cx - side * s, cy + s)          # pomo
            g = (cx - side * (s - 5), cy + s - 5)   # guardia
            b = (cx + side * s, cy - s)          # punta
            pygame.draw.line(surface, (30, 34, 110), g, b, 6)
            pygame.draw.line(surface, (110, 140, 255), g, b, 4)
            pygame.draw.line(surface, (220, 230, 255), g, b, 1)
            pygame.draw.line(surface, (120, 70, 30), a, g, 3)
            pygame.draw.line(surface, (246, 200, 84), (g[0] - 4, g[1] - side * 4),
                             (g[0] + 4, g[1] + side * 4), 3)
        claws = getattr(p, "shadowclaw_until", -1.0) > ctx.now
        frame = (176, 120, 236) if claws else (110, 132, 250)
        name = "Doppia Lama" + (" +Ombra" if claws else "")
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


def _draw_echo(surface, font, p, bx, y0, bh, ctx) -> None:
    """Ecolocalizzazione (Noibat/Noivern): tre onde sonore che escono da un
    punto, accese quante sono le cariche del ping (alla terza parte il ping);
    sotto, l'avviso del calo d'Att. Sp. di Dragobolide."""
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (22, 20, 40), box)
    n = int(getattr(p, "echo_count", 0))
    cx, cy = box.left + 9, box.centery
    pygame.draw.circle(surface, (110, 236, 220), (cx, cy), 3)
    for k in range(3):
        r = 7 + k * (bh // 2 - 9) // 2
        lit = k < n
        col = (110, 236, 220) if lit else (70, 70, 100)
        rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.arc(surface, (16, 60, 64) if lit else (30, 30, 46), rect.inflate(2, 2),
                        -0.9, 0.9, 4)
        pygame.draw.arc(surface, col, rect, -0.9, 0.9, 2)
    frame = (110, 236, 220) if n >= 2 else (150, 130, 230)
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(f"Ecolocalizz. {n}/3", True, frame), (bx - 4, y0 - 18))
    left = getattr(p, "spa_down_until", -1.0) - ctx.now
    if left > 0:
        t = font.render(f"Att.Sp -40% {left:0.0f}s", True, (255, 140, 80))
        surface.blit(t, (bx - 4, y0 - 34))


def _draw_honey(surface, font, p, bx, y0, bh, ctx) -> None:
    """Miele: tre vasetti (pieni quanti ne ha) e la ricarica di 10 s; sopra,
    da Ursaring, Dentistretti che si accende di rosso quando è attivo."""
    box = pygame.Rect(bx, y0, bh + 8, bh)
    pygame.draw.rect(surface, (40, 28, 18), box)
    n = int(getattr(p, "honey", 0))
    s = max(6, bh // 4)
    for k in range(3):
        ursa_fx.draw_jar(surface, box.left + 5 + k * (s + 4), box.centery - s // 2, s, k < n)
    left = getattr(p, "honey_ready_at", 0.0) - ctx.now
    frame = (244, 178, 48) if n else (150, 120, 80)
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(f"Miele {n}/3", True, frame), (bx - 4, y0 - 18))
    if left > 0:
        t = font.render(f"{left:0.0f}s", True, frame)
        surface.blit(t, (box.centerx - t.get_width() // 2, y0 + bh + 2))
    if p.passive_id == "dentistretti":
        on = bool(getattr(p, "guts_active", False))
        col = (255, 84, 54) if on else (130, 110, 100)
        txt = "Dentistretti +50% Att" if on else "Dentistretti"
        surface.blit(font.render(txt, True, col), (bx - 4, y0 - 34))
