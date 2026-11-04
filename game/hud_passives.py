"""Indicatori delle PASSIVE accanto alla barra delle mosse (uguali offline e online).

Corpofunesto (anime), Inversione, Muta, Sabbiafiume, I 108 Spiriti e la linea
Eevee (Adattabilità prima dell'evoluzione, poi la passiva della forma).
`p` è il Pokémon del giocatore: offline quello del motore, online l'entità
ricostruita a cui OnlineMatchScene ha copiato i campi dello stato visivo.
`ctx` porta ciò che non sta sul Pokémon: tempo, ritratti, pioggia e meteo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pygame

from engine.eevee import eevee_candidates, eevee_forms

from . import arch_fx, eevee_fx, hatt_fx, mag_fx, mien_fx, sneasel_fx, swine_fx, ursa_fx


@dataclass
class PassiveCtx:
    now: float
    portrait: Callable           # (sprite_dir, lato) -> Surface o None
    in_rain: bool = False
    weather: str = "clear"
    agitated: int = 0            # Quiete: nemici agitati visibili (linea Hatenna)
    charged: int = 0             # Magnetismo: nemici con una carica (linea Magnemite)
    frost_ready: int = 0         # Gelo: nemici con 4 accumuli pronti (linea Swinub)


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

    # Linea Sneasel: Sole e Luna (luna/sole + oro), Arraffalesto, Scalaroccia.
    if p.passive_id == "soleluna":
        _draw_sunmoon(surface, font, p, bx, y0, bh, ctx)
    elif p.passive_id in ("arraffalesto", "scalaroccia"):
        _draw_sneasel_form(surface, font, p, bx, y0, bh, ctx)

    # Linea Mienfoo: Maniche a Frusta + Rigenergia, Bruciapelo pronto, Danza.
    if p.passive_id == "manichefrusta":
        _draw_mien(surface, font, p, bx, y0, bh, ctx)

    # Linea Duraludon: Conduzione (pioggia), fulmini di Tuono, carica di Elettroraggio.
    if p.passive_id == "conduzione":
        _draw_conduct(surface, font, p, bx, y0, bh, ctx)

    # Linea Hatenna: Quiete (nemici agitati vicino).
    if p.passive_id == "quiete":
        _draw_quiet(surface, font, p, bx, y0, bh, ctx)
    if p.passive_id == "magnetismo":
        _draw_magnet(surface, font, p, bx, y0, bh, ctx)
    # Linea Swinub: Fiuto, Grassospesso (scudo), Gelo (nemici pronti al congelamento).
    if p.passive_id in ("fiuto", "grassospesso", "gelo"):
        _draw_swine(surface, font, p, bx, y0, bh, ctx)

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


def _draw_sunmoon(surface, font, p, bx, y0, bh, ctx) -> None:
    """Sole e Luna (Sneasel): luna se l'oro dai minion è in vantaggio (verso
    Weavile, parità compresa), sole se lo è quello dai neutrali (verso
    Sneasler); sotto i due contatori."""
    gm, gw = float(getattr(p, "gold_minion", 0.0)), float(getattr(p, "gold_wild", 0.0))
    sun = gw > gm
    box = pygame.Rect(bx, y0, bh, bh)
    pygame.draw.rect(surface, (44, 30, 18) if sun else (18, 22, 44), box)
    if sun:
        sneasel_fx.draw_sun_icon(surface, box.centerx, box.centery, bh // 5, ctx.now)
        frame, name = sneasel_fx.SUN, "Sneasler"
    else:
        sneasel_fx.draw_moon_icon(surface, box.centerx, box.centery, bh // 3)
        frame, name = sneasel_fx.MOON, "Weavile"
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(f"Sole e Luna -> {name}", True, frame), (bx - 4, y0 - 18))
    rows = ((f"Minion {gm:0.0f}", sneasel_fx.MOON, not sun),
            (f"Neutr. {gw:0.0f}", sneasel_fx.SUN, sun))
    for i, (txt, col, lead) in enumerate(rows):
        t = font.render(txt, True, col if lead else (120, 116, 128))
        surface.blit(t, (box.right + 5, y0 + 2 + i * (t.get_height() + 2)))


def _draw_sneasel_form(surface, font, p, bx, y0, bh, ctx) -> None:
    """Arraffalesto (Weavile: cariche rubate, +x% Att/Att.Sp) o Scalaroccia
    (Sneasler: ricarica dello scavalcamento)."""
    box = pygame.Rect(bx, y0, bh, bh)
    cx, cy = box.center
    s = bh // 2 - 8
    if p.passive_id == "arraffalesto":
        n = int(getattr(p, "snatch_up", 0))
        pygame.draw.rect(surface, (30, 16, 30), box)
        for k in range(3):   # tre artigli cremisi
            x = cx + (k - 1) * s * 0.6
            pygame.draw.line(surface, sneasel_fx.CRIMSON_DK, (x - s * 0.3, cy - s), (x + s * 0.3, cy + s), 5)
            pygame.draw.line(surface, sneasel_fx.CRIMSON, (x - s * 0.3, cy - s), (x + s * 0.3, cy + s), 3)
            pygame.draw.line(surface, sneasel_fx.CRIMSON_HI, (x - s * 0.3, cy - s), (x - s * 0.05, cy - s * 0.2), 1)
        frame = sneasel_fx.CRIMSON if n else (130, 96, 110)
        name = f"Arraffalesto +{n * 5}%" if n else "Arraffalesto"
        for k in range(5):   # cariche (5 = 25%)
            r = pygame.Rect(box.left + 4 + k * ((bh - 8) // 5), box.bottom - 7, (bh - 8) // 5 - 2, 4)
            pygame.draw.rect(surface, sneasel_fx.CRIMSON if k < n else (60, 40, 50), r)
    else:
        left = getattr(p, "climb_ready_at", 0.0) - ctx.now
        lit = left <= 0
        pygame.draw.rect(surface, (34, 28, 22), box)
        rock = sneasel_fx.ROCK if lit else (100, 90, 76)
        hi = sneasel_fx.ROCK_HI if lit else (130, 120, 100)
        pts = [(cx - s, cy + s), (cx - s * 0.3, cy - s), (cx + s * 0.2, cy - s * 0.2),
               (cx + s * 0.5, cy - s * 0.6), (cx + s, cy + s)]
        pygame.draw.polygon(surface, sneasel_fx.ROCK_DK, pts)
        pygame.draw.polygon(surface, rock, [(x, y + 2) for x, y in pts[:-1]] + [(cx + s - 2, cy + s)])
        pygame.draw.line(surface, hi, pts[0], pts[1], 2)
        # freccia ad arco sopra la roccia: lo scavalcamento
        arc = [(cx - s + i * s / 4, cy - s * 0.2 - math.sin(math.pi * i / 8) * s * 0.9) for i in range(9)]
        pygame.draw.lines(surface, sneasel_fx.SUN if lit else (120, 100, 60), False, arc, 2)
        frame = sneasel_fx.SUN if lit else (130, 110, 80)
        name = "Scalaroccia" if lit else f"Scalaroccia {left:0.0f}s"
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


def _draw_mien(surface, font, p, bx, y0, bh, ctx) -> None:
    """Maniche a Frusta (Mienfoo/Mienshao): maniche lavanda; sotto, la barra
    della calma (si riempie in 4 s, verde quando Rigenergia cura); in alto a
    destra il palmo giallo quando Bruciapelo stordisce; durante la Danza delle
    Maniche le tre mosse Q W E (accese quelle già usate) e il tempo rimasto."""
    now = ctx.now
    box = pygame.Rect(bx, y0, bh, bh)
    cx, cy = box.center
    s = bh // 2 - 6
    pygame.draw.rect(surface, (30, 22, 40), box)
    old_clip = surface.get_clip()
    surface.set_clip(box.inflate(-4, -4))
    for k in (-1, 1):   # due maniche che si incrociano
        pts = [(cx + k * (s - i * s / 4), cy - s * 0.6 + i * s / 6
                + math.sin(i * 1.1 + now * 4) * 2) for i in range(9)]
        pygame.draw.lines(surface, mien_fx.SLEEVE_DK, False, pts, 6)
        pygame.draw.lines(surface, mien_fx.SLEEVE, False, pts, 4)
        pygame.draw.lines(surface, mien_fx.SLEEVE_HI, False, pts[:4], 1)
        pygame.draw.line(surface, mien_fx.PINK, pts[0], pts[1], 4)   # polsino
    surface.set_clip(old_clip)
    calm = now - getattr(p, "mien_calm_at", -1e9)
    regen = bool(getattr(p, "mien_regen", False))
    bar = pygame.Rect(box.left + 4, box.bottom - 8, bh - 8, 4)
    pygame.draw.rect(surface, (40, 40, 44), bar)
    fill = int(bar.width * max(0.0, min(1.0, calm / 4.0)))
    pygame.draw.rect(surface, mien_fx.HEAL if regen else (150, 150, 160),
                     pygame.Rect(bar.left, bar.top, fill, bar.height))
    ready = bool(getattr(p, "fakeout_ready", False))
    if ready:
        mien_fx.draw_hand_icon(surface, box.right - 9, box.top + 12, 8, mien_fx.GOLD,
                               mien_fx.GOLD_DK)
    frame = mien_fx.GOLD if ready else (mien_fx.HEAL if regen else (150, 120, 170))
    name = "Rigenergia" if regen else "Maniche a Frusta"
    left = getattr(p, "dance_until", -1.0) - now
    if left > 0:   # sequenza della danza
        seq = getattr(p, "dance_seq", "")
        for i, sl in enumerate("QWE"):
            r = pygame.Rect(box.left + 3 + i * (bh - 6) // 3, box.top + 3, (bh - 6) // 3 - 2, 14)
            on = sl in seq
            pygame.draw.rect(surface, mien_fx.SLEEVE if on else (50, 40, 60), r)
            pygame.draw.rect(surface, mien_fx.SLEEVE_HI if on else (110, 96, 130), r, 1)
            t = font.render(sl, True, (30, 20, 40) if on else (170, 160, 190))
            surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
        frame = mien_fx.PINK
        name = f"Danza {left:0.1f}s"
    elif ready:
        name = "Bruciapelo pronto"
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


def _draw_conduct(surface, font, p, bx, y0, bh, ctx) -> None:
    """Conduzione (Duraludon/Archaludon): nuvola con la saetta, accesa e con la
    pioggia che cade quando la passiva è attiva (cariche e ritardi dimezzati,
    mosse Elettro che rallentano). In basso le saette di Tuono ancora da
    lanciare e il tempo per farlo; cornice gialla durante il +Att. Sp. di
    Elettroraggio."""
    now = ctx.now
    box = pygame.Rect(bx, y0, bh, bh)
    cx, cy = box.center
    rain = bool(getattr(p, "arch_rain", False))
    pygame.draw.rect(surface, (22, 28, 44) if rain else (30, 32, 38), box)
    old_clip = surface.get_clip()
    surface.set_clip(box.inflate(-4, -4))
    if rain:   # gocce che cadono
        for k in range(7):
            x = box.left + 5 + (k * 9) % (bh - 8)
            y = box.top + int((now * 40 + k * 13) % (bh - 4))
            pygame.draw.line(surface, arch_fx.RAIN, (x, y), (x - 1, y + 3))
    cloud = (150, 160, 180) if rain else (90, 94, 104)
    for dx, dy, r in ((-6, -8, 7), (2, -11, 8), (9, -7, 6), (0, -5, 7)):
        pygame.draw.circle(surface, cloud, (cx + dx, cy + dy), r)
    col = arch_fx.ELEC if rain else (120, 116, 90)
    arch_fx.draw_bolt_icon(surface, cx + 1, cy + 7, 9, col, (40, 30, 10))
    surface.set_clip(old_clip)
    frame = arch_fx.ELEC if rain else (140, 150, 170)
    name = "Conduzione: pioggia!" if rain else "Conduzione"
    left = getattr(p, "thunder_left", 0)
    t_left = getattr(p, "thunder_until", -1.0) - now
    if left > 0 and t_left > 0:
        for k in range(left):
            arch_fx.draw_bolt_icon(surface, box.left + 8 + k * 10, box.bottom - 9, 5)
        name = f"Tuono x{left}  {t_left:0.1f}s"
    if getattr(p, "arch_spa_until", -1.0) > now:
        frame = arch_fx.ELEC_HI
        if not (left > 0 and t_left > 0):
            name = "Att. Sp. +30%"
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


def _draw_magnet(surface, font, p, bx, y0, bh, ctx) -> None:
    """Magnetismo (Magnemite/Magneton/Magnezone): calamita su fondo scuro e
    numero di nemici carichi; con una R a polarita', in alto a destra il badge
    della polarita' scelta (rotella o Tab mentre si mira la R)."""
    box = pygame.Rect(bx, y0, bh, bh)
    cx, cy = box.center
    n = int(getattr(ctx, "charged", 0))
    pygame.draw.rect(surface, (36, 34, 22) if n else (26, 28, 36), box)
    mag_fx.draw_magnet_icon(surface, cx - 2, cy - 2, max(6, bh // 4))
    frame = mag_fx.ELEC if n else (170, 180, 200)
    name = f"Magnetismo: {n} car{'ico' if n == 1 else 'ichi'}" if n else "Magnetismo"
    mset = getattr(p, "moveset", None) or {}
    ms = mset.get("R")
    if ms is not None and mag_fx.has_polarity(getattr(ms, "chosen", None)):
        mag_fx.blit_badge(surface, box.right - 8, box.top + 8, mag_fx.polarity())
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


def _draw_swine(surface, font, p, bx, y0, bh, ctx) -> None:
    """Swinub/Piloswine/Mamoswine: muso che annusa su fondo scuro. Da
    Piloswine a destra la barra dello scudo di Grassospesso (bianco-ghiaccio);
    da Mamoswine, quanti nemici visibili hanno 4 accumuli di Gelo."""
    pid = p.passive_id
    fat = pid in ("grassospesso", "gelo")
    box = pygame.Rect(bx, y0, bh + (8 if fat else 0), bh)
    n = int(getattr(ctx, "frost_ready", 0))
    pygame.draw.rect(surface, (30, 40, 52) if n else (36, 30, 26), box)
    swine_fx.draw_snout_icon(surface, bx + bh // 2, box.centery - 1, max(5, bh // 4))
    frame = swine_fx.ICE_HI if n else (196, 170, 140)
    if fat:
        cap = max(1.0, getattr(p, "max_hp", 1.0) * 0.10)
        frac = max(0.0, min(1.0, getattr(p, "fat_shield", 0.0) / cap))
        bar = pygame.Rect(box.right - 9, box.top + 4, 5, bh - 8)
        pygame.draw.rect(surface, (20, 26, 34), bar)
        fh = int(bar.height * frac)
        pygame.draw.rect(surface, swine_fx.FAT, pygame.Rect(bar.left, bar.bottom - fh, bar.width, fh))
        pygame.draw.rect(surface, swine_fx.ICE_DK, bar, 1)
    if pid == "gelo":
        name = "Gelo: %d pront%s" % (n, "o" if n == 1 else "i") if n else "Fiuto + Gelo"
        if n:
            swine_fx.draw_flake(surface, box.left + 7, box.top + 7, 4, 255, swine_fx.ICE)
    elif pid == "grassospesso":
        name = "Fiuto + Grassospesso"
    else:
        name = "Fiuto"
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))


def _draw_quiet(surface, font, p, bx, y0, bh, ctx) -> None:
    """Quiete (Hatenna/Hattrem/Hatterene): cappello della linea su fondo
    viola; con nemici agitati entro 10 tile (ctx.agitated) la cornice diventa
    rossa, compare il segno di rabbia e il numero."""
    box = pygame.Rect(bx, y0, bh, bh)
    cx, cy = box.center
    n = int(getattr(ctx, "agitated", 0))
    pygame.draw.rect(surface, (44, 24, 48) if n else (30, 24, 40), box)
    hatt_fx.draw_hat_icon(surface, cx - 3, cy + 2, max(6, bh // 4))
    frame = hatt_fx.ANGER if n else (200, 150, 210)
    name = "Quiete"
    if n:
        hatt_fx.draw_anger(surface, box.right - 9, box.top + 9)
        name = f"Quiete: {n} agitat{'o' if n == 1 else 'i'}"
    pygame.draw.rect(surface, frame, box, 2)
    surface.blit(font.render(name, True, frame), (bx - 4, y0 - 18))
