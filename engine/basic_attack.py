"""Attacco base dei Pokémon in stile MOBA (mixin del Match).

Ciclo a tre fasi, non un semplice cooldown:
  1. CARICAMENTO (windup): l'animazione parte ma il colpo non è uscito. Un ordine
     di movimento o una mossa lo annullano senza consumare il ciclo.
  2. RILASCIO: corpo a corpo = danno istantaneo (con TOLLERANZA di portata);
     a distanza = parte un PROIETTILE A RICERCA che vola verso il bersaglio.
  3. RECUPERO: il resto del ciclo; ci si può già muovere (kiting) ma non
     riattaccare finché il ciclo non è finito.

Velocità d'attacco: attacchi/s = base del livello × (1 + somma dei bonus), con
un tetto (AS_CAP). Il caricamento è una frazione del ciclo che si accorcia con
la velocità d'attacco (un po' meno del ciclo: WINDUP_AS_SCALE).

Danno: le statistiche dell'ATTACCANTE si fotografano al rilascio (un buff preso
dopo non conta), le difese del BERSAGLIO si leggono all'impatto. Gli effetti
"al colpo" (veleno, cariche, oggetti) si applicano solo all'impatto. Se chi ha
tirato muore, il proiettile già partito colpisce lo stesso.

Puro: nessun pygame.
"""
from __future__ import annotations

import config
from .entities import Minion, Pokemon, Structure
from .vec import Vec2

AS_CAP = 2.5                 # tetto degli attacchi al secondo
MELEE_REACH = 2.2            # portata base sotto cui l'attacco è corpo a corpo
WINDUP_AS_SCALE = 0.85       # quanto il caricamento segue l'accorciarsi del ciclo (1 = uguale)
WINDUP_MIN = 0.06            # s: caricamento minimo (anche ad altissima vel. d'attacco)
MELEE_TOLERANCE = 0.3        # tile: margine al rilascio contro chi esce di poco
RANGED_TOLERANCE = 0.5       # tile: margine al rilascio per chi tira da lontano
MELEE_MINION_MULT = 1.10     # piccolo bonus del corpo a corpo contro i minion (farm)
ACQUIRE_EXTRA = 1.0          # tile: raggio d'acquisizione da fermo = portata + questo
AMOVE_EXTRA = 1.5            # tile: raggio d'acquisizione dell'attacco-movimento
IDLE_CHASE_LEASH = 2.5       # tile: da fermo insegue al massimo così lontano dall'ancora
AMOVE_DROP_EXTRA = 3.0       # tile: l'attacco-movimento molla chi va oltre portata + questo
PROJ_SPEED_DEFAULT = 20.0    # tile/s
PROJ_MAX_LIFE = 2.0          # s: sicurezza (un proiettile non vola per sempre)
CALL_HELP_THROTTLE = 0.25    # s: minimo tra due "richieste d'aiuto" dello stesso attaccante
CALL_HELP_TOWER_SLACK = 1.0  # tile: la vittima può stare poco fuori dalla gittata della torre

# Frazione del ciclo spesa nel caricamento, per ruolo (corpo a corpo / distanza).
_WINDUP_ROLE = {"assassino": 0.18, "tank": 0.30}
_WINDUP_MELEE = 0.24
_WINDUP_RANGED = 0.28        # a distanza: caricamento un filo più lungo
# Forme "pesanti" o "fulminee" (per numero di dex della forma attuale).
_WINDUP_DEX = {
    901: 0.34,   # Ursaluna
    526: 0.34,   # Gigalith
    217: 0.32,   # Ursaring
    823: 0.32,   # Corviknight
    461: 0.16,   # Weavile
    291: 0.16,   # Ninjask
}
# Velocità del proiettile (tile/s), per ruolo e per forma.
_PROJ_ROLE = {"tiratore": 24.0, "mago": 18.0, "mago mobile": 19.0, "supporto": 17.0}
_PROJ_DEX = {
    724: 25.0,   # Decidueye: tiratore puro
    1018: 16.0,  # Archaludon: palla d'acciaio pesante
    884: 16.0,   # Duraludon
    936: 18.0,   # Armarouge
}


def is_melee(u) -> bool:
    return getattr(u, "attack_range", 0.0) <= MELEE_REACH


def windup_frac(p) -> float:
    f = _WINDUP_DEX.get(getattr(p, "dex", 0))
    if f is not None:
        return f
    f = _WINDUP_ROLE.get(getattr(p, "role", ""))
    if f is not None and is_melee(p):
        return f
    return _WINDUP_MELEE if is_melee(p) else _WINDUP_RANGED


def proj_speed(p) -> float:
    s = _PROJ_DEX.get(getattr(p, "dex", 0))
    if s is not None:
        return s
    return _PROJ_ROLE.get(getattr(p, "role", ""), PROJ_SPEED_DEFAULT)


class BasicAttackMixin:
    """Ciclo dell'attacco base, proiettili a ricerca, richiesta d'aiuto."""

    def _init_basic_attack(self) -> None:
        self.aa_projectiles: list[dict] = []

    # --- velocità d'attacco -----------------------------------------------------
    def _eff_attack_speed(self, u) -> float:
        base = u.as_base if u.as_base > 0.0 else u.attack_speed
        bonus = u.as_bonus + self._moth_as_bonus(u)   # Eledanza: +30%
        bonus += self._octi_as_bonus(u)                # Presa a Ventosa: +50%
        if u.rampage_until > self.time:
            bonus += 1.0                      # Oltraggio: +100% (si somma agli altri)
        aps = min(AS_CAP, base * (1.0 + bonus))
        aps /= self._item_aa_cd_mult(u)       # Gelomai: rallentamento, dopo il tetto
        return max(0.2, aps)

    def _aa_timing(self, u) -> tuple[float, float]:
        """(durata del ciclo, durata del caricamento) in secondi."""
        cycle = 1.0 / self._eff_attack_speed(u)
        base = u.as_base if u.as_base > 0.0 else u.attack_speed
        base_cycle = 1.0 / max(0.2, base)
        # Il caricamento si accorcia con la velocità d'attacco, un po' meno del ciclo.
        scale = 1.0 + WINDUP_AS_SCALE * (cycle / base_cycle - 1.0)
        windup = max(WINDUP_MIN, windup_frac(u) * base_cycle * scale)
        return cycle, min(windup, cycle * 0.6)

    def _aa_reach(self, u, tgt) -> float:
        """Portata da BORDO a BORDO: portata + raggio dell'attaccante + del bersaglio."""
        return self._auto_reach(u) + getattr(u, "radius", 0.0) + getattr(tgt, "radius", 0.0)

    def _aa_cancel(self, u) -> None:
        """Annulla il caricamento: l'attacco non è uscito, il ciclo non si consuma."""
        if u.aa_active:
            u.aa_active = False
            u.attack_timer = 0.0

    def _aa_reset(self, u) -> None:
        """Reset dell'attacco (mosse con "aa_reset"): il prossimo parte subito."""
        if not u.aa_active:
            u.attack_timer = 0.0

    # --- ciclo ------------------------------------------------------------------
    def _pokemon_auto_attack(self, u) -> None:
        t = self.world.get(u.target_id) if u.target_id is not None else None
        if u.confuse_until > self.time:
            t = self._nearest_ally(u)   # confuso: colpisce gli alleati
        if u.aa_active:
            tgt = self.world.get(u.aa_target_id)
            switched = (t is not None and t.id != u.aa_target_id
                        and u.confuse_until <= self.time)
            if (u.moving or switched or tgt is None or not getattr(tgt, "alive", False)
                    or (isinstance(tgt, Pokemon) and tgt.untargetable_until > self.time)):
                self._aa_cancel(u)   # ordine di movimento / cambio bersaglio: niente colpo
                return
            if self.time >= u.aa_until:
                u.aa_active = False
                u.last_aa_at = self.time
                self._aa_release(u, tgt)
                u.aa_quick = False
            return
        # Nuovo attacco: bersaglio a portata, ciclo finito e stare fermi.
        if t is None or not getattr(t, "alive", False) or not self._within_attack(u, t):
            return
        if u.attack_timer > 0.0 or u.moving:
            return
        if isinstance(t, Pokemon) and t.untargetable_until > self.time:
            return
        # Passiva Distacco: ricarica il colpo furtivo quando sei allo scoperto.
        if u.passive_id == "distacco" and not self._is_hidden(u):
            u.stealth_shot_ready = True
        u.aa_stealth = (u.passive_id == "distacco" and u.stealth_shot_ready
                        and self._is_hidden(u))
        cycle, windup = self._aa_timing(u)
        u.aa_active = True
        u.aa_target_id = t.id
        u.aa_until = self.time + windup * self._item_aa_windup(u)   # Rapidartigli: 0
        u.attack_timer = cycle            # il ciclo parte dall'inizio dell'attacco
        self._face(u, t)
        self.fx_events.append({"eid": u.id, "anim": "Attack", "aa": True})   # avvia l'anim

    def _aa_release(self, u, tgt) -> None:
        """Fine del caricamento: colpo (corpo a corpo) o proiettile (distanza)."""
        melee = is_melee(u)
        slack = MELEE_TOLERANCE if melee else RANGED_TOLERANCE
        if u.pos.dist(tgt.pos) > self._aa_reach(u, tgt) + slack:
            return   # uscito dalla portata (oltre la tolleranza): il colpo va a vuoto
        self._face(u, tgt)
        if u.blind_until > self.time:
            # Turbosabbia: l'attacco base va a vuoto.
            self.fx_events.append({"kind": "miss", "c": (tgt.pos.x, tgt.pos.y),
                                   "mtype": "Ground", "fx": "miss"})
            return
        snap = self._aa_snapshot(u, tgt)
        self._octi_snap(u, tgt, snap)   # linea Remoraid: munizione e bonus del cambio
        mt = snap.get("ammo") or (u.types[0] if u.types else "Normal")
        self.fx_events.append({"kind": "attack", "a": (u.pos.x, u.pos.y),
                               "b": (tgt.pos.x, tgt.pos.y), "mtype": mt,
                               "melee": melee, "src": u.id,
                               "fx": "shadowclawhit" if snap["claws"] else u.attack_fx})
        if melee:
            self._aa_land(u, tgt, snap)
            return
        self.aa_projectiles.append({"src": u, "tgt_id": tgt.id,
                                    "pos": Vec2(u.pos.x, u.pos.y),
                                    "speed": proj_speed(u), "life": PROJ_MAX_LIFE,
                                    "snap": snap})

    def _aa_snapshot(self, u, tgt) -> dict:
        """Statistiche dell'attaccante fotografate al rilascio."""
        self._mien_before_aa(u, tgt)   # Maniche a Frusta: punto dolce (distanza al rilascio)
        claws = self._claws_on(u)      # Ombrartigli: Spettro, sempre brutto colpo
        mult = self._item_aa_mult(u, tgt) * self._mien_aa_mult(u)
        if u.aa_stealth:               # Distacco: primo colpo furtivo potenziato
            mult *= config.DISTACCO_BONUS_MULT
            u.stealth_shot_ready = False
            u.reveal_block_until = self.time + config.DISTACCO_REVEAL_BLOCK
        if claws:
            power, magic = u.eff_attack(), False
        else:
            power, magic = self._aa_power(u)
        return {"claws": claws, "mult": mult, "power": power, "magic": magic,
                "melee": is_melee(u)}

    def _aa_land(self, u, tgt, snap) -> None:
        """Impatto: schivate/parate, danno con le difese ATTUALI, effetti al colpo."""
        if not getattr(tgt, "alive", False):
            return
        if isinstance(tgt, Pokemon) and tgt.untargetable_until > self.time:
            return
        self._octi_before_land(u, tgt)      # Prendimira: aggancia il bersaglio
        if not self._octi_ignores_dodge(u, tgt) and self._item_dodge(u, tgt):   # Luminpolvere
            return
        if self._mien_parry_aa(u, tgt):     # Individua (Mienshao): parato
            return
        if snap["claws"]:
            dmg = self._aa_ghost_damage(u, tgt, power=snap["power"])
        else:
            dmg = self._basic_damage(u, tgt, power=snap["power"], magic=snap["magic"])
        dmg *= snap["mult"]
        dmg = self._octi_aa_land(u, tgt, snap, dmg)   # munizione: efficacia del tipo + STAB
        if snap["melee"] and isinstance(tgt, Minion):
            dmg *= MELEE_MINION_MULT
        self._deal_damage(u, tgt, dmg,
                          dmg_type="Ghost" if snap["claws"] else snap.get("ammo"))
        if not u.alive:
            return   # il proiettile colpisce lo stesso, ma niente effetti su chi è caduto
        self._vamp(u, dmg, physical=True)
        self._item_after_aa(u, tgt)   # Fangopece / Bitorzolelmo
        self._after_aa(u, tgt)        # Doppia Lama (Ceruledge)
        self._echo_after_aa(u, tgt)   # Ecolocalizzazione: ping ogni 3 colpi
        self._ursa_after_aa(u, tgt)   # Luna Piena: attacchi base ad area
        self._sneasel_after_aa(u, tgt)   # Arraffalesto, colpo d'agguato
        self._mien_after_aa(u, tgt)      # punto dolce, brutto colpo di Individua
        self._swine_after_aa(u, tgt)     # Gelo (Mamoswine): accumuli e congelamento
        self._moth_after_aa(u, tgt)      # Scaglie Velenose: accumuli di veleno
        self._octi_after_aa(u, tgt, snap, dmg)   # munizioni: Ghiaccio, Fuoco, Erba
        self._spirit_wander(u, tgt)   # Spirito Vagante (Spiritomb)
        self._cute_charm(u, tgt)      # Incantevole (Sylveon)

    def _update_aa_projectiles(self, dt: float) -> None:
        """Proiettili a ricerca: seguono il bersaglio, non si schivano camminando.
        Svaniscono solo se il bersaglio muore o diventa non bersagliabile."""
        alive = []
        for pr in self.aa_projectiles:
            tgt = self.world.get(pr["tgt_id"])
            if (tgt is None or not getattr(tgt, "alive", False)
                    or (isinstance(tgt, Pokemon) and tgt.untargetable_until > self.time)):
                continue
            pr["life"] -= dt
            d = tgt.pos - pr["pos"]
            dist = d.length()
            step = pr["speed"] * dt
            if dist <= step + 1e-6 or pr["life"] <= 0.0:
                self._aa_land(pr["src"], tgt, pr["snap"])
                continue
            pr["pos"] = pr["pos"] + d * (step / dist)
            alive.append(pr)
        self.aa_projectiles = alive

    # --- richiesta d'aiuto (minion e torri) -------------------------------------
    def _call_for_help(self, attacker, victim) -> None:
        """Un Pokémon che colpisce un Pokémon nemico attira i minion vicini e la
        torre della vittima, che cambiano bersaglio su di lui."""
        if self.time - getattr(attacker, "_cfh_at", -1e9) < CALL_HELP_THROTTLE:
            return
        attacker._cfh_at = self.time
        team = victim.team
        r = 7.0
        for e in self._combat_hash.query_radius(attacker.pos.x, attacker.pos.y, r):
            if e.team != team or not getattr(e, "alive", False):
                continue
            if isinstance(e, Minion):
                if e.pos.dist(attacker.pos) > e.aggro + getattr(attacker, "radius", 0.0):
                    continue
                cur = self.world.get(e.target_id) if e.target_id is not None else None
                if isinstance(cur, Pokemon) and getattr(cur, "alive", False):
                    continue   # già su un Pokémon: non rimbalza tra i due
                e.target_id = attacker.id
                self._ai.setdefault(e.id, {})["leash"] = Vec2(e.pos.x, e.pos.y)
            elif isinstance(e, Structure) and e.kind == "tower" and e.attack_damage > 0:
                rng = e.attack_range
                if (e.pos.dist(attacker.pos) <= rng + getattr(attacker, "radius", 0.0)
                        and e.pos.dist(victim.pos) <= rng + CALL_HELP_TOWER_SLACK):
                    e._forced_id = attacker.id
