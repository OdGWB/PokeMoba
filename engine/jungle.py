"""Giungla, Pokémon neutrali, leggendario meteo e Arceus (Fase 7).

Due tane sul fiume:
  - bassa: leggendario METEO (dal min 5). Sconfitto -> cambia il meteo di tutta
    la mappa e TRASFORMA la giungla in uno dei 3 stati evoluti (Sole/Pioggia/
    Vento); ricompare ogni 5 min come meteo DIVERSO. Il meteo resta finché un
    altro leggendario non viene sconfitto. 4 stati totali: base + 3 evoluti.
  - alta: ARCEUS (tana murata fino al min 15). Lastra di tipo casuale; chi lo
    sconfigge ottiene il buff "Giudizio" (3 min): il tipo della lastra come tipo
    aggiuntivo (STAB) e i propri minion fanno doppio danno alle torri. Perso
    morendo. Ricompare 6 min dopo.

Stati giungla (il meteo trasforma il terreno):
  Sole  -> i cespugli si seccano e spariscono.
  Pioggia -> compaiono pozze che rallentano i non-Acqua.
  Vento -> si aprono passaggi nei muri di giungla.
"""
from __future__ import annotations

import random

import config
from .entities import Pokemon, Structure, Wild
from .grid import (TILE_BUSH, TILE_FLOOR, TILE_JUNGLE_WALL, TILE_PUDDLE, TILE_WALL)
from .vec import Vec2

WEATHERS = ["sun", "rain", "wind"]
WEATHER_NAMES = {"clear": "Sereno", "sun": "Sole (Groudon)",
                 "rain": "Pioggia (Kyogre)", "wind": "Vento forte (Rayquaza)"}
LEGENDARY_BY_WEATHER = {"sun": "Groudon", "rain": "Kyogre", "wind": "Rayquaza"}
WEATHER_CODE = {"clear": 0, "sun": 1, "rain": 2, "wind": 3}
CODE_WEATHER = {v: k for k, v in WEATHER_CODE.items()}


def ring_tiles(grid, cx, cy, r):
    out = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if max(abs(dx), abs(dy)) == r and grid.in_bounds(cx + dx, cy + dy):
                out.append((cx + dx, cy + dy))
    return out


def _disc(grid, cx, cy, r, src, dst):
    for y in range(max(0, cy - r), min(grid.height, cy + r + 1)):
        row = grid.tiles[y]
        for x in range(max(0, cx - r), min(grid.width, cx + r + 1)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and row[x] == src:
                row[x] = dst


def apply_weather(grid, base_tiles, weather, puddles=None, puddle_spots=None,
                  wind_passages=None):
    """Trasforma la griglia nello stato di giungla del meteo (puro, riusabile da
    server e client).

    - Sole: i cespugli si seccano (BUSH -> FLOOR).
    - Pioggia: poche pozze GRANDI nei quadranti (dischi da `puddle_spots`); se non
      definiti, ripiega sul vecchio reticolo `puddles`.
    - Vento: si aprono POCHI varchi nei muri di giungla (dischi da `wind_passages`);
      se non definiti, apre tutti i muri di giungla (vecchio comportamento)."""
    grid.tiles = [row[:] for row in base_tiles]
    if weather == "sun":
        for y in range(grid.height):
            row = grid.tiles[y]
            for x in range(grid.width):
                if row[x] == TILE_BUSH:
                    row[x] = TILE_FLOOR
    elif weather == "rain":
        if puddle_spots:
            for sp in puddle_spots:
                cx, cy = sp["pos"]
                _disc(grid, int(cx), int(cy), int(sp.get("r", 4)), TILE_FLOOR, TILE_PUDDLE)
        elif puddles:
            for (x, y) in puddles:
                if grid.in_bounds(x, y) and grid.tiles[y][x] == TILE_FLOOR:
                    grid.tiles[y][x] = TILE_PUDDLE
    elif weather == "wind":
        if wind_passages:
            for sp in wind_passages:
                cx, cy = sp["pos"]
                _disc(grid, int(cx), int(cy), int(sp.get("r", 3)), TILE_JUNGLE_WALL, TILE_FLOOR)
        else:
            for y in range(grid.height):
                row = grid.tiles[y]
                for x in range(grid.width):
                    if row[x] == TILE_JUNGLE_WALL:
                        row[x] = TILE_FLOOR


class JungleSystem:
    def __init__(self, match):
        self.m = match
        self.world = match.world
        self.map = match.map
        self.grid = self.world.grid
        self.puddles = list(self.map.puddles)
        self.weather = "clear"

        self.low = self._den("low")
        self.high = self._den("high")
        # Mura la tana di Arceus finché non si apre (muro permanente, non apribile dal Vento).
        self._seal_tiles = self._ring(self.high, 2)
        for (x, y) in self._seal_tiles:
            self.grid.tiles[y][x] = TILE_WALL
        # Copia base DOPO la sigillatura: le trasformazioni meteo ripartono da qui.
        self.base_tiles = [row[:] for row in self.grid.tiles]

        self._pending_weather = random.choice(WEATHERS)  # primo leggendario casuale
        self._meteo = None
        self._next_meteo = config.WEATHER_FIRST_SPAWN
        self._arceus = None
        self._arceus_opened = False
        # Arceus si apre più tardi sul 5v5 (mappa più grande).
        self._arceus_open_time = (config.ARCEUS_OPEN_5V5 if self.map.team_size >= 5
                                  else config.ARCEUS_OPEN_3V3)
        self._next_arceus = None
        self._camps = [{"pos": s["pos"], "type": s["type"], "id": None, "next": 25.0}
                       for s in self._camp_spots()]
        self.announcements = match.announcements

    # --- setup ---------------------------------------------------------------
    def _den(self, name):
        p = self.map.dens.get(name, (50, 50))
        return Vec2(p[0] + 0.5, p[1] + 0.5)

    def _ring(self, center, r):
        return ring_tiles(self.grid, int(center.x), int(center.y), r)

    def _camp_spots(self):
        """Campi dei Pokémon minori: presi dalla mappa (data-driven). Ripiego su
        quattro posizioni fisse se la mappa non li definisce."""
        out = []
        for c in getattr(self.map, "camps", []) or []:
            x, y = c["pos"]
            out.append({"pos": Vec2(x + 0.5, y + 0.5), "type": c.get("type", "small")})
        if not out:
            for (x, y) in [(30, 62), (62, 30), (40, 42), (60, 58)]:
                out.append({"pos": Vec2(x + 0.5, y + 0.5), "type": "small"})
        return out

    # --- meteo / trasformazione giungla -------------------------------------
    def set_weather(self, weather):
        self.weather = weather
        self._transform()
        self.announcements.append((self.m.time, f"Meteo: {WEATHER_NAMES.get(weather, weather)}"))

    def _transform(self):
        apply_weather(self.grid, self.base_tiles, self.weather, puddles=self.puddles,
                      puddle_spots=getattr(self.map, "puddle_spots", None),
                      wind_passages=getattr(self.map, "wind_passages", None))

    def weather_damage_mult(self, move_type):
        return config.WEATHER_DMG.get(self.weather, {}).get(move_type, 1.0)

    def terrain_speed_mult(self, p):
        tx, ty = int(p.pos.x), int(p.pos.y)
        m = 1.0
        if self.grid.tile_at(tx, ty) == TILE_PUDDLE and "Water" not in p.types:
            m *= config.PUDDLE_SLOW
        if self.weather == "wind" and "Flying" in p.types:
            m *= config.WIND_FLYING_SPEED
        return m

    def team_has_judgment(self, team):
        return any(isinstance(p, Pokemon) and p.team == team and p.alive
                   and p.judgment_until > self.m.time for p in self.world.pokemons())

    # --- ciclo ---------------------------------------------------------------
    def update(self, dt):
        t = self.m.time
        # Leggendario meteo (tana bassa).
        if self._meteo is None and t >= self._next_meteo:
            self._spawn_meteo()
        # Apertura tana di Arceus.
        if not self._arceus_opened and t >= self._arceus_open_time:
            self._open_arceus_den()
        if self._arceus_opened and self._arceus is None and self._next_arceus is not None \
                and t >= self._next_arceus:
            self._spawn_arceus()
        # Campi neutrali.
        for camp in self._camps:
            if camp["id"] is None and t >= camp["next"]:
                big = camp.get("type") == "big"
                hp = config.CAMP_HP * (config.CAMP_BIG_MULT if big else 1.0)
                dmg = config.CAMP_DMG * (config.CAMP_BIG_MULT if big else 1.0)
                rw = config.CAMP_BIG_REWARD_MULT if big else 1.0
                gold = config.CAMP_GOLD_BIG if big else config.CAMP_GOLD_SMALL
                col = (210, 180, 90) if big else (170, 160, 120)
                rad = 0.95 if big else 0.7
                w = self.world.spawn_wild(camp["pos"], "camp", hp, dmg, 1.6, 1.2,
                                          config.CAMP_XP * rw, gold,
                                          radius=rad, color=col)
                camp["id"] = w.id

    def _spawn_meteo(self):
        w = self._pending_weather
        leg = self.world.spawn_wild(self.low, "meteo", config.LEGENDARY_HP,
                                    config.LEGENDARY_DMG, 3.0, 1.1, config.LEGENDARY_XP,
                                    config.LEGENDARY_GOLD, radius=1.1, weather=w,
                                    color=(220, 180, 80))
        self._meteo = leg.id
        self.announcements.append((self.m.time,
                                   f"È comparso {LEGENDARY_BY_WEATHER[w]} (tana bassa)!"))

    def _open_arceus_den(self):
        self._arceus_opened = True
        self._next_arceus = self.m.time
        for (x, y) in self._seal_tiles:
            self.grid.tiles[y][x] = TILE_FLOOR
            self.base_tiles[y][x] = TILE_FLOOR
        self._transform()  # riapplica il meteo corrente sul terreno aggiornato
        self.announcements.append((self.m.time, "La tana di ARCEUS si è aperta!"))

    def _spawn_arceus(self):
        plate = random.choice(config.ARCEUS_PLATES)
        a = self.world.spawn_wild(self.high, "arceus", config.ARCEUS_HP, config.ARCEUS_DMG,
                                  3.5, 1.2, config.ARCEUS_XP, config.ARCEUS_GOLD,
                                  radius=1.3, plate=plate, color=(230, 220, 240))
        self._arceus = a.id
        self.announcements.append((self.m.time, f"ARCEUS ({plate}) è comparso!"))

    # --- morte dei neutrali --------------------------------------------------
    def on_wild_death(self, victim, killer):
        # Ricompensa: oro all'ultimo colpo, XP alla squadra del killer vicina.
        if isinstance(killer, Pokemon):
            # Oro al last-hit SOLO per i campi: +2% per livello medio dei
            # giocatori, raddoppiato dalla taglia di recupero se la squadra è
            # indietro. I leggendari danno oro di squadra (sotto).
            if victim.kind == "camp":
                gold = victim.reward_gold
                gold *= 1.0 + config.CAMP_GOLD_PER_LEVEL * self.m._avg_player_level()
                gold *= self.m._comeback_mult(killer.team)
                killer.gold += gold
                self.m._track_gold(killer, gold, "wild")   # Sole e Luna (Sneasel)
            # I campi danno +3% XP per ogni livello medio dei giocatori; chi e' 2+
            # livelli sotto la media prende il bonus recupero (+15%).
            lvl_mult = (1.0 + 0.03 * self.m._avg_player_level()
                        if victim.kind == "camp" else 1.0)
            for p in self.world.pokemons():
                if p.alive and p.team == killer.team and p.pos.dist(victim.pos) <= 10.0:
                    amt = victim.reward_xp * lvl_mult
                    if victim.kind == "camp":
                        amt *= self.m._recovery_mult(p)
                    self.m._gain_xp(p, amt)

        if victim.kind == "meteo":
            self._meteo = None
            self._next_meteo = self.m.time + config.WEATHER_RESPAWN
            # Prossimo leggendario: meteo DIVERSO da quello appena attivato.
            self._pending_weather = random.choice([w for w in WEATHERS if w != victim.weather])
            self.set_weather(victim.weather)
            if isinstance(killer, Pokemon):
                mult = self.m._comeback_mult(killer.team)
                for p in self.world.pokemons():
                    if p.team == killer.team:
                        p.gold += config.LEGENDARY_TEAM_GOLD * mult   # oro di squadra
                        self.m._track_gold(p, config.LEGENDARY_TEAM_GOLD * mult, "wild")
        elif victim.kind == "arceus":
            self._arceus = None
            self._next_arceus = self.m.time + config.ARCEUS_RESPAWN
            if isinstance(killer, Pokemon):
                mult = self.m._comeback_mult(killer.team)
                for p in self.world.pokemons():
                    if p.team == killer.team:
                        p.gold += config.LEGENDARY_TEAM_GOLD * mult   # oro di squadra
                        self.m._track_gold(p, config.LEGENDARY_TEAM_GOLD * mult, "wild")
                        if p.alive:
                            p.judgment_until = self.m.time + config.JUDGMENT_DURATION
                            p.judgment_plate = victim.plate
                self.announcements.append((self.m.time,
                                           f"Giudizio ({victim.plate}) per la squadra {killer.team}!"))
        elif victim.kind == "camp":
            for camp in self._camps:
                if camp["id"] == victim.id:
                    camp["id"] = None
                    camp["next"] = self.m.time + config.CAMP_RESPAWN
