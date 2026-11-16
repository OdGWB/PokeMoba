"""Registro della GRAFICA delle linee di Pokémon (gemello di engine/lines.py).

Ogni linea con grafica propria ha un modulo game/<linea>_fx.py che espone:
  SHAPES               insieme delle forme che sa disegnare (FXSystem._draw_shapes)
  draw_shape(overlay, s, S, ts, f, a)
  STYLES               stile "fx" della mossa -> handler (FXSystem._FX_STYLES)
  draw_unit_overlay(surface, e, gx, gy, now, ts)   facoltativo: disegni sulle unità

PER AGGIUNGERE UNA LINEA: aggiungi il modulo a FX_LINES. game/fx.py e
game/renderer.py leggono le tabelle qui sotto. Restano a parte, perché fatti su
misura per ogni linea, i disegni persistenti (game/world_fx.py) e l'HUD della
passiva (game/hud_passives.py).
"""
from __future__ import annotations

from . import (arch_fx, char_fx, charcadet_fx, corvi_fx, eevee_fx, flor_fx, gastly_fx, hatt_fx, incin_fx, mag_fx,
               mien_fx, moth_fx, noivern_fx, octi_fx, scy_fx, sneasel_fx, swine_fx, ursa_fx)

# L'ORDINE conta: a parità di forma vince il primo modulo, a parità di stile l'ultimo.
FX_LINES: tuple = (
    eevee_fx, corvi_fx, charcadet_fx, noivern_fx, ursa_fx, sneasel_fx, mien_fx, arch_fx,
    hatt_fx, mag_fx, swine_fx, moth_fx, octi_fx, flor_fx, scy_fx, incin_fx, char_fx,
    gastly_fx,
)


def _shapes() -> dict:
    out: dict = {}
    for mod in FX_LINES:
        for kind in mod.SHAPES:
            out.setdefault(kind, mod.draw_shape)
    return out


def _styles() -> dict:
    out: dict = {}
    for mod in FX_LINES:
        out.update(mod.STYLES)
    return out


# forma -> draw_shape del modulo che la disegna
LINE_SHAPES: dict = _shapes()
# stile "fx" -> handler (unito agli stili generici in FXSystem._FX_STYLES)
LINE_STYLES: dict = _styles()
# forma -> frazione del volo della testa per gli attacchi base a ricerca
LINE_AA_TRAVEL: dict = {k: v for mod in FX_LINES for k, v in getattr(mod, "AA_TRAVEL", {}).items()}
# disegni sulle unità, nell'ordine del registro
UNIT_OVERLAYS: tuple = tuple(mod.draw_unit_overlay for mod in FX_LINES
                             if hasattr(mod, "draw_unit_overlay"))
