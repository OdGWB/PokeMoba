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
  use_item               oggetti attivabili (Mentalerba, Palla Fumo, Bici Cross,
                         Scudo Rovinato, Etere)
  _item_buy_ok           regole d'acquisto (gruppi, copie, Pietrastante)
  _item_dmg_mult         ogni danno (Mielino, Occhialineri, Elettropalla)
  _item_on_takedown      uccisioni e assist (Occhialineri, Monetamuleto)
  _item_on_ult           lancio dell'ultimate (Rocciaumida, Rocciacalda)
  _item_on_wild_kill     neutrale sconfitto (Mielino)
"""
from __future__ import annotations

import random

from .entities import Minion, Pokemon, Structure, Wild
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
AUGURITE_TOWER = 1.20     # Augite Nera: +20% danno alle torri
ICE_SLOW = 0.8             # Gelomai: chi lo colpisce con un attacco base ha -20% vel. d'attacco...
ICE_DUR = 2.0              # ...per 2s
AURA_RADIUS = 6.0          # Acqua Mistica: alleati entro 6 tile...
AURA_SPDEF = 20.0          # ...+20 Dif. Sp.
FLUTE_RADIUS = 6.0         # Pokéflauto (attivabile): alleati entro 6 tile...
FLUTE_SPEED = 1.2          # ...+20% velocità per 2s e via sonno/confusione/paralisi
FLUTE_DUR = 2.0
FLUTE_CD = 90.0

# --- aggiornamento 3.1 (nuovi oggetti) ---
EVIOLITE_MULT = 1.25       # Evolcondensa: +25% Difesa e Dif. Sp. finche' non e' completamente evoluto
EVERSTONE_XP = 1.5         # Pietrastante: +50% esperienza...
EVERSTONE_XP_LEVEL = 15    # ...fino al livello 15
ORAN_REGEN = 0.003         # Baccarancia: 0,3% HP max/s
HONEY_WILD = 1.30          # Mielino: +30% danno ai neutrali...
HONEY_HEAL = 0.06          # ...ogni neutrale sconfitto cura il 6% HP max...
HONEY_UNTIL = 15 * 60.0    # ...fino al minuto 15 (poi solo +100 HP)
ACRO_SLOW = 0.7            # Bici Cross: rallentamenti subiti -30%...
ACRO_JUMP = 3.0            # ...salto di 3 tile (attivabile)
ACRO_CD = 40.0
SITRUS_FRAC = 0.30         # Baccacedro: sotto il 30% HP...
SITRUS_HEAL = 0.20         # ...cura il 20% HP max
ETHER_CUT = 4.0            # Etere: -4 s alle ricariche (non l'ultimate)
GLASSES_LOW = 0.40         # Occhialineri: +20% sui Pokemon sotto il 40% HP...
GLASSES_MULT = 1.20
GLASSES_SPEED = 1.15       # ...+15% velocita' per 3 s dopo uccisione/assist
GLASSES_DUR = 3.0
PLATE_FRAC = 0.06          # Lastraferro: 6% degli HP attuali (fisico)...
PLATE_WILD_MAX = 60.0      # ...massimo 60 sui neutrali
SILVER_BASE = 20.0         # Polvere Argento: 20 + 15% Att. Sp. (speciale)
SILVER_SPA = 0.15
LIGHTBALL_TAKEN = 1.10     # Elettropalla: +10% danno subito
SAND_SINGLE = 0.8          # Sabbia Soffice: -20% su bersaglio singolo...
SAND_AREA = 0.9            # ...-10% con le mosse ad area...
SAND_DUR = 1.5             # ...per 1,5 s
SNOWBALL_TEN = 0.75        # Pallaneve: controlli subiti -25%...
SNOWBALL_ATK = 1.25        # ...e alla fine di un controllo +25% Attacco...
SNOWBALL_DUR = 4.0         # ...per 4 s...
SNOWBALL_CD = 10.0         # ...(ricarica 10 s)
RSHIELD_RADIUS = 6.0       # Scudo Rovinato (attivabile): alleati entro 6 tile...
RSHIELD_BASE = 80.0        # ...scudo di 80 + 8% HP max del possessore...
RSHIELD_HP = 0.08
RSHIELD_DUR = 3.0          # ...per 3 s
RSHIELD_CD = 90.0
AMULET_GOLD_S = 1.0        # Monetamuleto: +1 oro/s...
AMULET_ASSIST = 30.0       # ...+30 oro per assist
PRISM_OUT = 1.10           # Squama Bella: cure e scudi dati +10%...
PRISM_AS = 0.20            # ...l'alleato ottiene +20% vel. d'attacco...
PRISM_AA = 15.0            # ...e +15 danno sugli attacchi base...
PRISM_DUR = 4.0            # ...per 4 s
WEATHER_ROCK_RADIUS = 4.0  # Rocciaumida / Rocciacalda: area di 4 tile...
WEATHER_ROCK_DUR = 6.0     # ...per 6 s all'ultimate
DAMP_RAIN_DUR = 1.5        # Rocciaumida: le aree di pioggia del possessore +50%
SUN_FIRE = 1.30            # sole locale: mosse Fuoco +30%...
SUN_WATER = 0.70           # ...mosse Acqua -30%
HEAT_FIRE = 1.10           # Rocciacalda: mosse Fuoco del possessore +10%
# Forme di mossa che colpiscono un solo bersaglio (Sabbia Soffice: -20%; le altre -10%).
SINGLE_TARGET_SHAPES = {"projectile", "dash", "blink", "chain", "curse", "dashback",
                        "deligift", "bolt", "leap", "throwback"}

ITEM_COOLDOWNS = {"weakness_policy": WP_CD, "red_card": REDCARD_CD, "focus_sash": SASH_CD,
                  "mental_herb": MENTAL_CD, "smoke_ball": SMOKE_CD, "eject_button": EJECT_CD,
                  "focus_band": BAND_CD, "poke_flute": FLUTE_CD, "acro_bike": ACRO_CD,
                  "rusted_shield": RSHIELD_CD, "snowball": SNOWBALL_CD}


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
        if not isinstance(caster, Pokemon) or not caster.items:
            return 1.0
        items = self._fx_items(caster)
        m = SOOTHE_MULT if "soothe_bell" in items else 1.0
        if "prism_scale" in items:
            m *= PRISM_OUT   # Squama Bella: cure date +10%
        return m

    def _give_shield(self, caster, target, amt, dur) -> None:
        """Scudo dato da `caster` (Creta Luce: +15% e +50% di durata; Squama
        Bella: +10% e l'alleato si carica)."""
        if isinstance(caster, Pokemon) and caster.items:
            items = self._fx_items(caster)
            if "light_clay" in items:
                amt *= LIGHTCLAY_AMT
                dur *= LIGHTCLAY_DUR
            if "prism_scale" in items:
                amt *= PRISM_OUT
        self._apply_shield(target, amt, dur)
        self._item_on_support(caster, target)

    def _item_on_support(self, caster, target) -> None:
        """Squama Bella: l'alleato curato o protetto ottiene +20% vel. d'attacco
        e +15 danno sugli attacchi base per 4 s."""
        if (isinstance(caster, Pokemon) and isinstance(target, Pokemon) and caster.items
                and "prism_scale" in self._fx_items(caster) and target.team == caster.team):
            target.prism_until = self.time + PRISM_DUR

    def _item_as_bonus(self, u) -> float:
        return PRISM_AS if getattr(u, "prism_until", -1.0) > self.time else 0.0

    # --- regole d'acquisto ---------------------------------------------------------
    def _item_buy_ok(self, p, iid) -> bool:
        """Gruppi a possesso limitato, copie massime (consumabili), Condividi Esp.
        uno per squadra, Pietrastante solo a chi non e' completamente evoluto."""
        cat = self.item_catalog
        it = cat.get(iid)
        if it is None:
            return False
        if not cat.group_ok(iid, p.items) or not cat.count_ok(iid, p.items):
            return False
        if iid == "exp_share" and self._team_has_item(p.team, iid):
            return False
        if iid == "everstone" and not self._can_evolve_more(p):
            return False
        return True

    def _can_evolve_more(self, p) -> bool:
        """Vero se la linea ha ancora un'evoluzione (Scyther compreso finche' non
        evolve). Senza evoluzioni (Spiritomb, Delibird) o alla forma finale: falso."""
        return not self._is_final_form(p)

    # --- danno ---------------------------------------------------------------------------
    def _item_dmg_mult(self, attacker, target) -> float:
        """Ogni danno: Mielino (+30% ai neutrali fino al minuto 15),
        Occhialineri (+20% sui Pokemon sotto il 40%), Elettropalla (+10% subito)."""
        m = 1.0
        if isinstance(attacker, Pokemon) and attacker.items:
            items = self._fx_items(attacker)
            if "honey" in items and isinstance(target, Wild) and self.time < HONEY_UNTIL:
                m *= HONEY_WILD
            if ("black_glasses" in items and isinstance(target, Pokemon)
                    and target.team != attacker.team and target.max_hp > 0
                    and target.hp < GLASSES_LOW * target.max_hp):
                m *= GLASSES_MULT
        if isinstance(target, Pokemon) and target.items and "light_ball" in self._fx_items(target):
            m *= LIGHTBALL_TAKEN
        return m

    def _item_on_takedown(self, killer, assisters) -> None:
        """Uccisione o assist su un Pokemon: Occhialineri (+15% velocita' 3 s),
        Monetamuleto (+30 oro per assist)."""
        for p, assist in ([(killer, False)] if isinstance(killer, Pokemon) else []) + \
                [(a, True) for a in assisters]:
            if not p.items:
                continue
            items = self._fx_items(p)
            if "black_glasses" in items:
                self._apply_speed(p, GLASSES_SPEED, GLASSES_DUR)
            if assist and "amulet_coin" in items:
                p.gold += AMULET_ASSIST

    def _item_on_wild_kill(self, killer) -> None:
        """Mielino: ogni neutrale sconfitto cura il 6% degli HP max (fino al minuto 15)."""
        if (isinstance(killer, Pokemon) and killer.alive and "honey" in self._fx_items(killer)
                and self.time < HONEY_UNTIL):
            killer.hp = min(killer.max_hp, killer.hp + killer.max_hp * HONEY_HEAL
                            * self._heal_in_mult(killer))

    def _item_on_ult(self, p) -> None:
        """Lancio dell'ultimate: area di pioggia (Rocciaumida) o di sole
        (Rocciacalda) di 4 tile attorno al possessore per 6 s."""
        if not p.items:
            return
        items = self._fx_items(p)
        c = Vec2(p.pos.x, p.pos.y)
        if "damp_rock" in items:
            dur = WEATHER_ROCK_DUR
            self.rain_zones.append({"center": c, "radius": WEATHER_ROCK_RADIUS,
                                    "end": self.time + dur, "team": p.team})
            self.fx_events.append({"kind": "zone", "c": (c.x, c.y), "radius": WEATHER_ROCK_RADIUS,
                                   "mtype": "Water", "fx": "polirain", "dur": dur})
        if "heat_rock" in items:
            self.sun_zones.append({"c": c, "radius": WEATHER_ROCK_RADIUS, "team": p.team,
                                   "start": self.time, "end": self.time + WEATHER_ROCK_DUR})

    def _rain_dur_mult(self, p) -> float:
        """Rocciaumida: le aree di pioggia create dal possessore durano +50%."""
        return DAMP_RAIN_DUR if isinstance(p, Pokemon) and "damp_rock" in self._fx_items(p) else 1.0

    def _sun_mult(self, caster, mv) -> float:
        """Sole locale (Rocciacalda): chi lancia dentro un'area di sole fa +30% con
        le mosse Fuoco e -30% con quelle Acqua (il +10% di Rocciacalda e' in _item_move_mult)."""
        m = 1.0
        if mv.type not in ("Fire", "Water") or not self.sun_zones:
            return m
        for z in self.sun_zones:
            if z["c"].dist(caster.pos) <= z["radius"]:
                m *= SUN_FIRE if mv.type == "Fire" else SUN_WATER
                break
        return m

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
        if knockback:
            dist *= self._octi_disp_mult(u)   # Ventose (Octillery): -50%
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
        if mv.type == "Fire" and "heat_rock" in items:
            m *= HEAT_FIRE   # Rocciacalda
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
        if self._item_hits_foe(caster, target) and caster.items and "soft_sand" in self._fx_items(caster):
            single = mv.shape in SINGLE_TARGET_SHAPES or mv.d.get("target") == "unit"
            self._apply_slow(target, SAND_SINGLE if single else SAND_AREA, SAND_DUR)
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

    def _item_struct_mult(self, attacker, target) -> float:
        """Augite Nera: +20% di danno alle torri (attacchi base e mosse)."""
        if (isinstance(attacker, Pokemon) and isinstance(target, Structure)
                and getattr(target, "kind", "") == "tower" and attacker.items
                and "black_augurite" in self._fx_items(attacker)):
            return AUGURITE_TOWER
        return 1.0

    def _item_aa_mult(self, u, tgt) -> float:
        m = QUICKCLAW_MULT if u.aa_quick else 1.0
        if "zoom_lens" in self._fx_items(u):
            reach = self._aa_reach(u, tgt)   # bordo a bordo
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
        """Dopo un attacco base a segno: veleno di Fangopece, Bitorzolelmo,
        danni extra di Lastraferro / Polvere Argento / Squama Bella, Sabbia Soffice."""
        self._item_hit_debuffs(attacker, target, False)   # Velenpuntale
        self._item_aa_extra(attacker, target)
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

    def _item_aa_extra(self, attacker, target) -> None:
        if not isinstance(attacker, Pokemon) or not attacker.alive or not getattr(target, "alive", False):
            return
        if target.team == attacker.team or isinstance(target, Structure):
            return
        items = self._fx_items(attacker) if attacker.items else ()
        if "iron_plate" in items:   # Lastraferro: 6% degli HP attuali, fisico
            extra = PLATE_FRAC * target.hp
            if isinstance(target, Wild):
                extra = min(extra, PLATE_WILD_MAX)
            if extra > 0:
                self._deal_damage(attacker, target,
                                  self._basic_damage(attacker, target, power=extra, magic=False))
        if "silver_powder" in items and target.alive:   # Polvere Argento: speciale
            power = SILVER_BASE + SILVER_SPA * attacker.eff_sp_attack()
            self._deal_damage(attacker, target,
                              self._basic_damage(attacker, target, power=power, magic=True))
        if attacker.prism_until > self.time and target.alive:   # Squama Bella (alleato)
            self._deal_damage(attacker, target, PRISM_AA)
        if ("soft_sand" in items and isinstance(target, Pokemon) and target.alive
                and not target.is_decoy):
            self._apply_slow(target, SAND_SINGLE, SAND_DUR)

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
        if ("sitrus_berry" in items and 0.0 < target.hp < SITRUS_FRAC * target.max_hp
                and target.alive):   # Baccacedro: si consuma da sola
            self._consume_item(target, "sitrus_berry")
            target.hp = min(target.max_hp, target.hp + target.max_hp * SITRUS_HEAL
                            * self._heal_in_mult(target))
            self._item_fx(target, "sitrus_berry", "Grass", 1.0)
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
        elif iid == "acro_bike":   # Bici Cross: salto di 3 tile dove si guarda
            if p.dashlock_until > self.time or self._immobile(p):
                return False
            if p.path:
                dirv = p.path[0] - p.pos
            else:
                from .vec import DIR_VECTORS
                dirv = DIR_VECTORS[p.facing % 8]
            if dirv.length() < 1e-6:
                return False
            origin = Vec2(p.pos.x, p.pos.y)
            dest = self._clamp_to_wall(origin, origin + dirv.normalized() * ACRO_JUMP)
            p.pos = dest
            p.stop()
            self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                                   "b": (dest.x, dest.y), "mtype": "Flying", "fx": "acrobike"})
        elif iid == "rusted_shield":   # Scudo Rovinato: scudo a se' e agli alleati vicini
            amt = RSHIELD_BASE + RSHIELD_HP * p.max_hp
            for q in self.world.pokemons():
                if (q.team == p.team and q.alive and not q.is_decoy
                        and q.pos.dist(p.pos) <= RSHIELD_RADIUS):
                    self._give_shield(p, q, amt, RSHIELD_DUR)
                    self._item_fx(q, "rusted_shield", "Steel", 1.0)
        elif iid == "ether":   # Etere (consumabile): -4 s alle ricariche tranne la R
            for s_, ms in p.moveset.items():
                if s_ != "R" and ms.cooldown_remaining > 0.0:
                    ms.cooldown_remaining = max(0.0, ms.cooldown_remaining - ETHER_CUT)
            self._consume_item(p, "ether")
            self._item_fx(p, "ether", "Psychic", 1.0)
            return True
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

    def _consume_item(self, p, iid) -> None:
        """Consumabile usato: toglie UNA copia e ricalcola le statistiche."""
        if iid in p.items:
            p.items.remove(iid)
            self._apply_items(p)

    def _hard_cc(self, p) -> bool:
        t = self.time
        return (p.stun_until > t or p.sleep_until > t or p.frozen_until > t
                or p.root_until > t or p.charm_until > t or p.fear_until > t
                or p.taunt_until > t or p.confuse_until > t or p.airborne_until > t)

    # --- tick --------------------------------------------------------------------------
    def _update_items(self, dt: float) -> None:
        """Dopo _update_status (che ricalcola p.speed e p.invisible): rigenerazioni,
        Bicicletta, Vulnerassicurazione e nubi della Palla Fumo."""
        now = self.time
        aura_holders = []
        for p in self.world.pokemons():
            p.wp_active = p.wp_until > now
            p.snow_atk_active = p.snow_atk_until > now
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
            if "oran_berry" in items:
                regen += ORAN_REGEN   # Baccarancia
            if "amulet_coin" in items:
                p.gold += AMULET_GOLD_S * dt   # Monetamuleto: +1 oro/s
            if "lum_berry" in items and self._has_status(p):   # Baccaprugna
                self._cleanse(p)
                self._consume_item(p, "lum_berry")
                self._item_fx(p, "lum_berry", "Grass", 1.0)
                items = self._fx_items(p)
            if "snowball" in items:   # Pallaneve: fine di un controllo -> +25% Attacco
                cc = self._hard_cc(p)
                if (p.snow_cc and not cc and self._item_ready(p, "snowball")):
                    p.snow_atk_until = now + SNOWBALL_DUR
                    self._item_cooldown(p, "snowball")
                    self._item_fx(p, "snowball", "Ice", 1.0)
                p.snow_cc = cc
            if regen > 0.0 and p.hp < p.max_hp:
                p.hp = min(p.max_hp, p.hp + p.max_hp * regen * dt * self._heal_in_mult(p))
            if ("bicycle" in items and now - p.last_damaged_at >= BIKE_IDLE
                    and now - p.last_dealt_at >= BIKE_IDLE):
                p.speed *= BIKE_EXTRA
        for h in aura_holders:   # Acqua Mistica: aura +20 Dif. Sp. agli alleati vicini (non cumulabile)
            for q in self.world.pokemons():
                if q is not h and q.alive and q.team == h.team and q.pos.dist(h.pos) <= AURA_RADIUS:
                    q.aura_spdef = AURA_SPDEF
        if self.sun_zones:
            self.sun_zones = [z for z in self.sun_zones if now < z["end"]]
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
