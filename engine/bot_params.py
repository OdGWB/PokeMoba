"""Parametri dell'IA dei bot, raccolti in un solo posto.

Prima erano costanti di modulo e numeri scritti dentro le funzioni (engine/match.py,
engine/smite.py, engine/bot_plan.py). Qui hanno un nome e un valore di default
IDENTICO a quello di prima: con i default il comportamento non cambia.

Ogni squadra ha il suo insieme (Match.bot_params[team]), cosi' si possono mettere
contro due versioni dell'IA nella stessa partita (taratura automatica, es. CMA-ES).
Solo decisioni dei bot: nessuna regola di gioco dipende da questi numeri.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace


@dataclass
class BotParams:
    # --- IA di base (match._ai_bot / _ai_jungler) --------------------------------
    aggro: float = 6.5              # tile: raggio in cui il bot cerca un bersaglio
    leash_mult: float = 1.8         # bersaglio mantenuto fino a aggro * leash_mult
    retreat_hp: float = 0.28        # frazione di vita sotto cui si ritira in base
    struct_minion_r: float = 4.5    # tile: minion alleati attorno a una struttura per attaccarla
    tower_margin: float = 0.8       # tile oltre la gittata delle torri considerati "sotto torre"
    dive_lookahead: float = 2.5     # tile: quanto avanti guarda prima di entrare in gittata
    lane_wp_reach: float = 1.2      # tile: waypoint di lane raggiunto
    defend_enemy_r: float = 6.0     # tile: nemici attorno a una struttura alleata = minacciata
    defend_max_dist: float = 20.0   # tile: si va a difendere solo entro questa distanza
    cast_min_reach: float = 2.5     # tile: gittata minima per lanciare una mossa generica

    # --- possibilita' di uccisione (smite._good_kill_chance) ---------------------
    kill_my_hp: float = 0.5         # la mia vita minima per inseguire sotto torre
    kill_low_hp: float = 0.25       # bersaglio quasi morto: si insegue comunque
    kill_mid_hp: float = 0.5        # bersaglio ferito: si insegue se in vantaggio numerico
    kill_count_r: float = 8.0       # tile: raggio per contare alleati/nemici
    kill_adv: int = 2               # vantaggio numerico richiesto

    # --- guinzaglio dalla lane (smite._bot_filter_target) ------------------------
    lane_leash_early: float = 7.0
    lane_leash: float = 14.0
    early_time: float = 150.0

    # --- gank del jungler (smite._jungler_gank_target, match._ai_jungler) --------
    gank_min_time: float = 150.0
    gank_min_level: int = 3
    gank_cooldown: float = 75.0
    gank_duration: float = 14.0
    gank_max_dist: float = 40.0
    gank_my_hp: float = 0.7
    gank_hp: float = 0.6            # vita massima (frazione) del bersaglio
    gank_count_r: float = 9.0
    gank_max_disadv: int = 2        # si rinuncia se i nemici sono almeno tanti in piu'
    gank_w_hp: float = 10.0
    gank_w_ally: float = 2.0
    gank_w_dist: float = 0.1

    # --- IA a piani (engine/bot_plan.py) -----------------------------------------
    plan_fight_r: float = 4.5       # tile: campione nemico cosi' vicino = combatte l'IA di base
    # shopping
    recall_gold: float = 850.0
    recall_cooldown: float = 110.0
    recall_max: float = 110.0
    shop_stay: float = 14.0
    shop_from: float = 150.0
    shop_done_hp: float = 0.85
    recall_safe_r: float = 9.0
    # nexus scoperto
    core_from: float = 240.0
    core_my_hp: float = 0.4
    # assedio delle torri
    siege_from: float = 300.0
    siege_my_hp: float = 0.55
    siege_late_roles: float = 480.0  # s: da qui anche jungler e support
    tower_near: float = 28.0
    tower_near_low: float = 45.0
    tower_low_frac: float = 0.5
    tower_solo_frac: float = 0.3
    tower_minion_r: float = 4.5
    tower_count_r: float = 12.0
    tower_w_dist: float = 0.5
    tower_w_frac: float = 30.0
    tower_w_minion: float = 10.0
    tower_w_ally: float = 3.0       # peso di (alleati - nemici) attorno alla torre (prima fisso a 3.0)
    # roam del support
    roam_from: float = 180.0
    roam_time: float = 26.0
    roam_cooldown: float = 70.0
    roam_my_hp: float = 0.5
    roam_foe_r: float = 10.0
    roam_w_foe: float = 4.0
    roam_w_hp: float = 3.0
    roam_w_lane: float = 2.0
    roam_w_dist: float = 0.05
    roam_skip_hp: float = 0.7
    roam_recheck: float = 15.0
    roam_follow_r: float = 3.5

    # --- decisioni a PUNTEGGIO (engine/bot_utility.py) ----------------------------
    # Se utility=True il bot non usa piu' le soglie on/off qui sopra per scegliere
    # COSA fare: ogni intenzione (ritirata, combattere, comprare, nexus, assedio,
    # roam, lane/giungla) riceve un punteggio continuo e vince il piu' alto, con
    # isteresi. Le soglie sopra restano come CENTRO delle rampe. Spento di default.
    utility: bool = False
    u_period: float = 0.2           # s tra due valutazioni (in mezzo si esegue l'ultima scelta)
    u_stick: float = 0.15           # bonus all'intenzione in corso (isteresi)
    u_min_hold: float = 1.0         # s minimi prima di cambiare...
    u_override: float = 0.35        # ...a meno che la nuova non superi di tanto
    u_band: float = 0.12            # mezza larghezza delle rampe sulla vita (frazione)
    u_threat_r: float = 9.0         # tile: raggio per la forza di alleati/nemici
    # ritirata
    u_w_retreat: float = 1.6
    u_ret_danger: float = 0.8       # quanto pesa l'inferiorita' sulla ritirata
    # combattimento
    u_w_fight: float = 1.0
    u_fight_k: float = 4.0          # pendenza della sigmoide
    u_fight_adv: float = 1.0        # peso del vantaggio di forza (-1..1)
    u_fight_hp: float = 1.0         # peso di (mia vita - vita del bersaglio)
    u_fight_bias: float = 0.3
    u_fight_tower: float = 0.6      # malus se il bersaglio e' sotto una torre nemica
    # shopping
    u_w_shop: float = 0.9
    u_shop_gold_band: float = 300.0
    u_w_heal: float = 0.5           # tornare a curarsi con poca vita e nessun nemico (~sotto il 45%)
    # nexus / assedio / roam / lane
    u_w_core: float = 1.2
    u_w_siege: float = 0.8
    u_siege_k: float = 0.15         # pendenza sul punteggio della torre
    u_siege_bias: float = 0.0
    u_w_roam: float = 0.7
    u_roam_bias: float = 3.0
    u_w_lane: float = 0.35          # punteggio fisso di lane/giungla (il "non fare altro")

    # --- utilita' -------------------------------------------------------------------
    def copy(self, **changes) -> "BotParams":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BotParams":
        """Campi sconosciuti ignorati, mancanti al default (file salvati da versioni diverse)."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    @classmethod
    def names(cls) -> list[str]:
        return [f.name for f in fields(cls)]


# Default condiviso (sola lettura) per unita' senza squadra.
DEFAULT_BOT_PARAMS = BotParams()
