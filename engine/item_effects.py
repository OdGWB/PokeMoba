"""Effetti unici degli oggetti (data/items.json).

Puro: nessun pygame. È un mixin di Match (engine/match.py): usa lo stesso stato
(self.time, self.world, self.fx_events, _combat_hash, gli _apply_*). Le
statistiche degli oggetti (somma dei bonus) le gestisce ItemCatalog; qui ci sono
gli effetti per NOME, controllati con `id in p.items`, quindi due copie dello
stesso oggetto non raddoppiano l'effetto unico (le statistiche sì).

Hook chiamati dal Match:
  _item_on_cast          lancio di una mossa (Scelta, Grandelente, Assorbisfera)
  _item_move_mult        moltiplicatore di danno delle mosse
  _item_after_move_hit   dopo il danno di una mossa (Assorbisfera, Vulnerassicurazione)
  _item_aa_windup / _item_aa_mult / _item_dodge / _item_after_aa   attacchi base
  _item_on_damaged       ogni danno inflitto (Focalnastro, Cartelrossa, Pulsantefuga)
  _update_items          ogni tick, dopo _update_status (rigen, Bicicletta, Palla Fumo)
  use_item               oggetti attivabili (Mentalerba, Palla Fumo)
"""
from __future__ import annotations

import random

from .entities import Pokemon, Structure, Wild
from .moves import Move
from .vec import Vec2

CHOICE_IDS = ("choice_band", "choice_specs", "choice_scarf")
CHOICE_WINDOW = 5.0        # Scelta: stessa mossa due volte di fila entro 5s...
CHOICE_MULT = 1.25         # ...la seconda fa +25%
QUICKCLAW_IDLE = 3.0       # Rapidartigli: dopo 3s senza attaccare...
QUICKCLAW_MULT = 1.3       # ...attacco base istantaneo e +30%
ZOOM_RANGE = 1.15          # Zoomlente: +15% portata degli attacchi base
ZOOM_FAR_MULT = 1.15       # ...e +15% di danno oltre metà portata
METRO_STEP = 0.10          # Metronomo: +10% per colpo consecutivo...
METRO_MAX = 5              # ...fino a +50%
METRO_WINDOW = 8.0         # s: oltre questo intervallo la serie riparte
WIDE_RANGE = 1.2           # Grandelente: +20% portata delle mosse
LIFEORB_MULT = 1.15        # Assorbisfera: mosse +15%...
LIFEORB_COST = 0.03        # ...ogni mossa a segno costa il 3% degli HP max
EXPERT_MULT = 1.25         # Abilcintura: superefficace +25%
WP_MULT = 1.25             # Vulnerassicurazione: +25% Att. e Att. Sp....
WP_DUR = 5.0               # ...per 5s
WP_CD = 15.0
SLUDGE_REGEN = 0.005       # Fangopece: 0,5% HP max/s (1,5% se Veleno)
SLUDGE_REGEN_POISON = 0.015
SLUDGE_POISON_DUR = 3.0    # veleno degli attacchi base: 3s, danno leggero
SLUDGE_DPS_BASE = 8.0
SLUDGE_DPS_ATK = 0.08      # + 8% dell'Attacco al secondo
HELMET_BASE = 15.0         # Bitorzolelmo: 15 + 20% della Difesa del possessore
HELMET_DEF = 0.20
MELEE_REACH = 2.2          # gittata d'attacco base sotto cui si è "in corpo a corpo"
LEFTOVERS_REGEN = 0.005    # Avanzi: 0,5% HP max/s...
LEFTOVERS_IDLE_REGEN = 0.02  # ...2% se non subisce danni da 6s
LEFTOVERS_IDLE = 6.0
REDCARD_FRAC = 0.15        # Cartelrossa: colpo singolo > 15% HP max...
REDCARD_DIST = 4.0         # ...respinge l'attaccante di 4 tile
REDCARD_CD = 20.0
IRONBALL_MULT = 0.4        # Ferropalla: lanci in aria / respinte subiti -60%
BRIGHT_DODGE = 0.15        # Luminpolvere: 15% di schivare gli attacchi base
LIGHTCLAY_AMT = 1.15       # Creta Luce: scudi dati +15%...
LIGHTCLAY_DUR = 1.5        # ...e +50% di durata
SOOTHE_MULT = 1.15         # Calmanella: cure date +15%
BIGROOT_MULT = 1.2         # Granradice: cure ricevute +20%
EXPSHARE_RADIUS = 8.0      # Condividi Esp.: alleato entro 8 tile fa last-hit su un minion...
EXPSHARE_GOLD = 10         # ...10 oro...
EXPSHARE_XP = 0.30         # ...e il 30% dell'esperienza del minion
SASH_CD = 90.0             # Focalnastro
MENTAL_CD = 90.0           # Mentalerba (attivabile)
SMOKE_RADIUS = 1.5         # Palla Fumo (attivabile): nube di 3 tile di diametro...
SMOKE_DUR = 3.0            # ...per 3s
SMOKE_SPEED = 1.3          # dentro: invisibile e +30% velocità
SMOKE_CD = 75.0
EJECT_FRAC = 0.30          # Pulsantefuga: sotto il 30% HP...
EJECT_DIST = 4.0           # ...scatta di 4 tile via dal nemico più vicino
EJECT_CD = 60.0
EJECT_SCAN = 12.0          # raggio in cui cercare il nemico più vicino
BIKE_IDLE = 5.0            # Bicicletta: niente danni (fatti o subiti) da 5s...
BIKE_EXTRA = 1.12          # ...+12% velocità extra

SEED_REGEN = 0.003         # Miracolseme: 0,3% HP max/s
HEALCUT_MULT = 0.6         # Velenpuntale / Spettrotarga: cure ricevute -40%...
HEALCUT_DUR = 3.0          # ...per 3s
EMBER_FRAC = 0.01          # Carbonella: 1% degli HP max del bersaglio al secondo...
EMBER_DUR = 3.0            # ...per 3s (si rinnova, non si cumula)
BAND_FRAC = 0.30           # Bandana: sotto il 30% HP...
BAND_SHIELD = 0.30         # ...scudo pari al 30% degli HP max...
BAND_DUR = 4.0             # ...per 4s
BAND_CD = 60.0
RUST_ATK = 0.03            # Spada Arrugginita: +3% Attacco per carica (in Pokemon.eff_attack)...
RUST_MAX = 5               # ...fino a 5 cariche...
RUST_DUR = 4.0             # ...per 4s dall'ultimo colpo...
RUST_SPEED = 1.10          # ...a 5 cariche +10% velocità di movimento
ICE_SLOW = 0.8             # Gelomai: chi lo colpisce con un attacco base ha -20% vel. d'attacco...
ICE_DUR = 2.0              # ...per 2s
AURA_RADIUS = 6.0          # Acqua Mistica: alleati entro 6 tile...
AURA_SPDEF = 20.0          # ...+20 Dif. Sp.
FLUTE_RADIUS = 6.0         # Pokéflauto (attivabile): alleati entro 6 tile...
FLUTE_SPEED = 1.2          # ...+20% velocità per 2s e via sonno/confusione/paralisi
FLUTE_DUR = 2.0
FLUTE_CD = 90.0

ITEM_COOLDOWNS = {"weakness_policy": WP_CD, "red_card": REDCARD_CD, "focus_sash": SASH_CD,
                  "mental_herb": MENTAL_CD, "smoke_ball": SMOKE_CD, "eject_button": EJECT_CD,
                  "focus_band": BAND_CD, "poke_flute": FLUTE_CD}


def cdr_to_haste(cdr: float) -> float:
    """Riduzione ricariche (frazione) -> ability haste equivalente:
    ricarica × 100/(100+haste) = ricarica × (1 − cdr)."""
    cdr = max(0.0, min(0.6, cdr))
    return 100.0 * cdr / (1.0 - cdr)


class ItemEffectsMixin:
    # --- utilità ---------------------------------------------------------------
    def _item_ready(self, p, iid) -> bool:
        return self.time >= p.item_cd.get(iid, -1e9)

    def _item_cooldown(self, p, iid) -> None:
        p.item_cd[iid] = self.time + ITEM_COOLDOWNS.get(iid, 0.0)

    def _item_fx(self, p, fx, mtype="Normal", radius=1.0) -> None:
        self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": radius,
                               "mtype": mtype, "fx": fx})

    def _is_final_form(self, p) -> bool:
        return p.stage >= self._n_stages(p) - 1

    def _item_bonus_for(self, p) -> dict:
        """Bonus statistici degli oggetti; l'Evolcondensa non dà nulla alla forma finale."""
        skip = ("eviolite",) if self._is_final_form(p) else ()
        return self.item_catalog.total_bonus(p.items, skip)

    def _heal_in_mult(self, p) -> float:
        m = BIGROOT_MULT if isinstance(p, Pokemon) and "big_root" in self._fx_items(p) else 1.0
        return m * self._healcut_mult(p)   # cure ridotte (Sporcolancio)

    def _heal_out_mult(self, caster) -> float:
        return SOOTHE_MULT if isinstance(caster, Pokemon) and "soothe_bell" in self._fx_items(caster) else 1.0

    def _give_shield(self, caster, target, amt, dur) -> None:
        """Scudo dato da `caster` (Creta Luce: +15% e +50% di durata)."""
        if isinstance(caster, Pokemon) and "light_clay" in self._fx_items(caster):
            amt *= LIGHTCLAY_AMT
            dur *= LIGHTCLAY_DUR
        self._apply_shield(target, amt, dur)

    def _item_aa_cd_mult(self, u) -> float:
        """Gelomai: chi è stato rallentato attacca più piano (cooldown × 1/0.8)."""
        return 1.0 / ICE_SLOW if getattr(u, "aspd_slow_until", -1.0) > self.time else 1.0

    def _item_hits_foe(self, caster, target) -> bool:
        return (isinstance(caster, Pokemon) and caster.alive and isinstance(target, Pokemon)
                and target.alive and target.team != caster.team and not target.is_decoy)

    def _item_hit_debuffs(self, caster, target, is_move) -> None:
        """Effetti su colpo a segno contro un Pokémon nemico: cure ridotte
        (Velenpuntale su attacchi e mosse, Spettrotarga sulle mosse), bruciatura
        di Carbonella (solo mosse)."""
        if not self._item_hits_foe(caster, target) or not caster.items:
            return
        items = self._fx_items(caster)
        if "poison_barb" in items or (is_move and "spell_tag" in items):
            self._apply_healcut(target, HEALCUT_MULT, HEALCUT_DUR)
        if is_move and "charcoal" in items:
            target.ember_until = self.time + EMBER_DUR
            target.ember_src = caster.id

    def _item_push(self, u, dirv, dist, knockback=True) -> None:
        """Spostamento istantaneo (respinta o scatto), fermato dai muri."""
        if dirv.length() < 1e-6:
            dirv = Vec2(1.0, 0.0)
        if knockback and isinstance(u, Pokemon) and "iron_ball" in self._fx_items(u):
            dist *= IRONBALL_MULT
        origin = Vec2(u.pos.x, u.pos.y)
        dest = self._clamp_to_wall(origin, origin + dirv.normalized() * dist)
        u.pos = dest
        u.stop()
        if isinstance(u, Pokemon):
            u.aa_active = False
            u.recalling = False
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": "Normal"})

    # --- mosse -----------------------------------------------------------------
    def _item_on_cast(self, p, mv, slot):
        """Al lancio: serie Scelta, contatore Assorbisfera, portata Grandelente.
        Ritorna la mossa da eseguire (copia con portata +20% se Grandelente)."""
        p.cast_seq += 1
        key = (slot, mv.id)
        repeat = p.choice_key == key and self.time - p.choice_at <= CHOICE_WINDOW
        p.choice_boost = mv.id if repeat and any(i in self._fx_items(p) for i in CHOICE_IDS) else ""
        p.choice_key = key
        p.choice_at = self.time
        if "wide_lens" in self._fx_items(p) and mv.range > 0:
            return Move(mv.slot, mv.max_rank, dict(mv.d, range=mv.range * WIDE_RANGE))
        return mv

    def _item_move_mult(self, caster, mv, target, eff) -> float:
        if not isinstance(caster, Pokemon) or not caster.items:
            return 1.0
        items = self._fx_items(caster)
        m = 1.0
        if caster.choice_boost and caster.choice_boost == mv.id:
            m *= CHOICE_MULT
        if "life_orb" in items:
            m *= LIFEORB_MULT
        if "expert_belt" in items and eff > 1.0:
            m *= EXPERT_MULT
        if "metronome" in items:
            prev = caster.metro.get(target.id)
            n = 0
            if prev and prev[0] == mv.id and self.time - prev[2] <= METRO_WINDOW:
                n = prev[1] + 1
            caster.metro[target.id] = (mv.id, n, self.time)
            if len(caster.metro) > 24:   # dimentica i bersagli vecchi
                caster.metro = {k: v for k, v in caster.metro.items()
                                if self.time - v[2] <= METRO_WINDOW}
            m *= 1.0 + METRO_STEP * min(METRO_MAX, n)
        return m

    def _item_after_move_hit(self, caster, mv, target, eff) -> None:
        self._item_hit_debuffs(caster, target, True)   # Carbonella, Spettrotarga, Velenpuntale
        # Assorbisfera: una sola volta per lancio, anche se colpisce piu' bersagli.
        if (isinstance(caster, Pokemon) and "life_orb" in self._fx_items(caster) and caster.alive
                and caster.orb_paid_seq != caster.cast_seq):
            caster.orb_paid_seq = caster.cast_seq
            caster.hp = max(1.0, caster.hp - caster.max_hp * LIFEORB_COST)
        # Vulnerassicurazione: subire una mossa superefficace nemica.
        if (isinstance(target, Pokemon) and target.alive and eff > 1.0
                and "weakness_policy" in self._fx_items(target) and isinstance(caster, Pokemon)
                and caster.team != target.team and self._item_ready(target, "weakness_policy")):
            target.wp_until = self.time + WP_DUR
            target.wp_active = True
            self._item_cooldown(target, "weakness_policy")
            self._item_fx(target, "weakness_policy", "Fighting", 1.2)

    # --- attacchi base ---------------------------------------------------------
    def _item_aa_windup(self, u) -> float:
        """Fattore del windup del nuovo attacco base (Rapidartigli: 0 = istantaneo)."""
        u.aa_quick = ("quick_claw" in self._fx_items(u)
                      and self.time - u.last_aa_at >= QUICKCLAW_IDLE)
        return 0.0 if u.aa_quick else 1.0

    def _item_aa_mult(self, u, tgt) -> float:
        m = QUICKCLAW_MULT if u.aa_quick else 1.0
        if "zoom_lens" in self._fx_items(u):
            reach = self._auto_reach(u) + getattr(tgt, "radius", 0.0)
            if u.pos.dist(tgt.pos) > 0.5 * reach:
                m *= ZOOM_FAR_MULT
        return m

    def _item_dodge(self, attacker, target) -> bool:
        """Luminpolvere: il possessore schiva il 15% degli attacchi base."""
        if (isinstance(target, Pokemon) and "bright_powder" in self._fx_items(target)
                and not isinstance(attacker, Structure) and random.random() < BRIGHT_DODGE):
            self.fx_events.append({"kind": "miss", "c": (target.pos.x, target.pos.y),
                                   "mtype": "Normal", "fx": "miss"})
            return True
        return False

    def _item_after_aa(self, attacker, target) -> None:
        """Dopo un attacco base a segno: veleno di Fangopece, Bitorzolelmo."""
        self._item_hit_debuffs(attacker, target, False)   # Velenpuntale
        if self._item_hits_foe(attacker, target) and attacker.items:
            if "rusted_sword" in self._fx_items(attacker):   # Spada Arrugginita
                attacker.rust_stacks = (min(RUST_MAX, attacker.rust_stacks + 1)
                                        if attacker.rust_until > self.time else 1)
                attacker.rust_until = self.time + RUST_DUR
                attacker.rust_n = attacker.rust_stacks
        if (isinstance(target, Pokemon) and isinstance(attacker, Pokemon) and target.items
                and attacker.team != target.team and "never_melt_ice" in self._fx_items(target)):
            attacker.aspd_slow_until = self.time + ICE_DUR   # Gelomai
        if (isinstance(attacker, Pokemon) and "black_sludge" in self._fx_items(attacker)
                and isinstance(target, Pokemon) and target.alive and target.team != attacker.team):
            self._apply_poison(target, attacker,
                               SLUDGE_DPS_BASE + SLUDGE_DPS_ATK * attacker.eff_attack(),
                               SLUDGE_POISON_DUR)
        # Bitorzolelmo: chi colpisce in corpo a corpo (Pokémon e selvatici; non
        # minion, per non dare oro "passivo" col last-hit) subisce danno senza tipo.
        if (isinstance(target, Pokemon) and "rocky_helmet" in self._fx_items(target)
                and isinstance(attacker, (Pokemon, Wild)) and attacker.alive
                and attacker.team != target.team and attacker.attack_range <= MELEE_REACH):
            self._deal_damage(target, attacker, HELMET_BASE + HELMET_DEF * target.eff_defense())

    # --- danno subito ------------------------------------------------------------
    def _item_on_damaged(self, attacker, target, amount) -> None:
        """Dopo che `target` ha perso `amount` HP (prima del controllo di morte)."""
        if isinstance(attacker, Pokemon) and getattr(attacker, "team", -1) != target.team:
            attacker.last_dealt_at = self.time
        if not isinstance(target, Pokemon) or not target.items or target.is_decoy:
            return
        items = self._fx_items(target)
        if target.hp <= 0.0:
            if "focus_sash" in items and self._item_ready(target, "focus_sash"):
                target.hp = 1.0
                self._item_cooldown(target, "focus_sash")
                self._item_fx(target, "focus_sash", "Fighting", 1.0)
            else:
                return
        if ("focus_band" in items and 0.0 < target.hp < BAND_FRAC * target.max_hp
                and self._item_ready(target, "focus_band")):
            self._item_cooldown(target, "focus_band")
            self._apply_shield(target, target.max_hp * BAND_SHIELD, BAND_DUR)
            self._item_fx(target, "focus_band", "Fighting", 1.0)
        if ("red_card" in items and amount > REDCARD_FRAC * target.max_hp
                and isinstance(attacker, Pokemon) and attacker.alive
                and attacker.team != target.team and self._item_ready(target, "red_card")):
            self._item_cooldown(target, "red_card")
            self._item_push(attacker, attacker.pos - target.pos, REDCARD_DIST)
        if ("eject_button" in items and target.hp < EJECT_FRAC * target.max_hp
                and self._item_ready(target, "eject_button")):
            foe = None
            bd = EJECT_SCAN
            for e in self._combat_hash.query_radius(target.pos.x, target.pos.y, EJECT_SCAN):
                if e.team == target.team or not getattr(e, "alive", False):
                    continue
                if isinstance(e, Structure) and not getattr(e, "attack_damage", 0):
                    continue
                d = target.pos.dist(e.pos)
                if d < bd:
                    foe, bd = e, d
            if foe is None and attacker is not None and hasattr(attacker, "pos"):
                foe = attacker
            if foe is not None:
                self._item_cooldown(target, "eject_button")
                self._item_push(target, target.pos - foe.pos, EJECT_DIST, knockback=False)

    # --- Condividi Esp. ------------------------------------------------------------
    def _exp_share(self, victim, killer) -> None:
        for a in self.world.pokemons():
            if (a is killer or a.team != killer.team or not a.alive
                    or "exp_share" not in a.items):
                continue
            if a.pos.dist(killer.pos) > EXPSHARE_RADIUS:
                continue
            a.gold += EXPSHARE_GOLD
            self._gain_xp(a, victim.xp * EXPSHARE_XP)

    def _team_has_item(self, team, iid) -> bool:
        return any(q.team == team and iid in q.items for q in self.world.pokemons())

    # --- attivabili ------------------------------------------------------------------
    def use_item(self, p, slot: int) -> bool:
        """Attiva l'oggetto nello slot (Mentalerba, Palla Fumo). True se attivato."""
        if not isinstance(p, Pokemon) or not p.alive or not 0 <= slot < len(p.items):
            return False
        iid = p.items[slot]
        if not self._item_ready(p, iid) or not self._fx_items(p):   # Privazione: spenti
            return False
        if iid == "mental_herb":
            self._cleanse(p)
            p.airborne_until = -1.0
            p.airborne_start = -1.0
            p.air_z = 0.0
            self._item_fx(p, "mental_herb", "Psychic", 1.2)
        elif iid == "poke_flute":
            now = self.time
            for q in self.world.pokemons():
                if (q.team != p.team or not q.alive or q.is_decoy
                        or q.pos.dist(p.pos) > FLUTE_RADIUS):
                    continue
                q.sleep_until = q.confuse_until = q.root_until = -1.0
                q.sleep_arm_at = -1.0
                if not (q.speed_until > now and q.speed_mult >= FLUTE_SPEED):
                    self._apply_speed(q, FLUTE_SPEED, FLUTE_DUR)
                self._item_fx(q, "poke_flute", "Normal", 1.0)
        elif iid == "smoke_ball":
            c = Vec2(p.pos.x, p.pos.y)
            self.item_clouds.append({"center": c, "radius": SMOKE_RADIUS,
                                     "end": self.time + SMOKE_DUR, "owner_id": p.id,
                                     "team": p.team})
            self.fx_events.append({"kind": "zone", "c": (c.x, c.y), "radius": SMOKE_RADIUS,
                                   "mtype": "Normal", "fx": "smoke"})
        else:
            return False
        self._item_cooldown(p, iid)
        return True

    # --- tick --------------------------------------------------------------------------
    def _update_items(self, dt: float) -> None:
        """Dopo _update_status (che ricalcola p.speed e p.invisible): rigenerazioni,
        Bicicletta, Vulnerassicurazione e nubi della Palla Fumo."""
        now = self.time
        aura_holders = []
        for p in self.world.pokemons():
            p.wp_active = p.wp_until > now
            p.smoke_hidden = False
            p.aura_spdef = 0.0
            if p.rust_n and p.rust_until <= now:
                p.rust_stacks = p.rust_n = 0
            if p.ember_until > now and p.alive and p.ember_src is not None:   # Carbonella
                src = self.world.get(p.ember_src)
                if src is not None and src.alive:
                    self._deal_damage(src, p, EMBER_FRAC * p.max_hp * dt)
            if not p.alive or not p.items:
                continue
            items = self._fx_items(p)
            if "mystic_water" in items:
                aura_holders.append(p)
            if p.rust_n >= RUST_MAX and "rusted_sword" in items:
                p.speed *= RUST_SPEED
            regen = 0.0
            if "miracle_seed" in items:
                regen += SEED_REGEN
            if "leftovers" in items:
                regen += (LEFTOVERS_IDLE_REGEN if now - p.last_damaged_at >= LEFTOVERS_IDLE
                          else LEFTOVERS_REGEN)
            if "black_sludge" in items:
                regen += SLUDGE_REGEN_POISON if "Poison" in p.types else SLUDGE_REGEN
            if regen > 0.0 and p.hp < p.max_hp:
                p.hp = min(p.max_hp, p.hp + p.max_hp * regen * dt * self._heal_in_mult(p))
            if ("bicycle" in items and now - p.last_damaged_at >= BIKE_IDLE
                    and now - p.last_dealt_at >= BIKE_IDLE):
                p.speed *= BIKE_EXTRA
        for h in aura_holders:   # Acqua Mistica: aura +20 Dif. Sp. agli alleati vicini (non cumulabile)
            for q in self.world.pokemons():
                if q is not h and q.alive and q.team == h.team and q.pos.dist(h.pos) <= AURA_RADIUS:
                    q.aura_spdef = AURA_SPDEF
        if self.item_clouds:
            keep = []
            for c in self.item_clouds:
                if now >= c["end"]:
                    continue
                keep.append(c)
                o = self.world.get(c["owner_id"])
                if (o is not None and o.alive
                        and o.pos.dist(c["center"]) <= c["radius"] + o.radius):
                    o.smoke_hidden = True
                    o.invisible = True
                    o.speed *= SMOKE_SPEED
            self.item_clouds = keep
