"""Resa a voto di squadra (SurrenderMixin in Match).

- Si puo' proporre dal minuto SURRENDER_MIN_TIME; il voto dura SURRENDER_VOTE_TIME.
- Votano solo i GIOCATORI umani della squadra (i bot e i bot sostituti non contano).
- Servono tutti i voti se gli umani sono al piu' 3, altrimenti tutti meno uno.
- Se il voto fallisce (troppi no o tempo scaduto) la squadra aspetta SURRENDER_COOLDOWN.
- Se passa vince l'altra squadra (winner = 1 - team), come la caduta del nucleo.
La resa lascia un annuncio; l'HUD ricava i suoni dai cambi di surrender_state.
"""
from __future__ import annotations

SURRENDER_MIN_TIME = 600.0     # 10 minuti
SURRENDER_VOTE_TIME = 30.0
SURRENDER_COOLDOWN = 120.0


class SurrenderMixin:
    def _surr_init(self):
        if not hasattr(self, "surrender_votes"):
            self.surrender_votes: dict[int, dict] = {}     # team -> voto in corso
            self._surr_next: dict[int, float] = {0: SURRENDER_MIN_TIME, 1: SURRENDER_MIN_TIME}

    def _surr_voters(self, team):
        return [p for p in self.world.pokemons()
                if p.team == team and not getattr(p, "is_bot", False)]

    @staticmethod
    def surrender_needed(n_humans: int) -> int:
        return n_humans if n_humans <= 3 else n_humans - 1

    def surrender_vote(self, unit, yes: bool) -> str | None:
        """Voto (o proposta, se non c'e' un voto aperto e yes) di `unit`.
        Ritorna un motivo di rifiuto o None."""
        self._surr_init()
        if self.winner is not None or unit is None or getattr(unit, "is_bot", False):
            return "non puoi votare"
        team = unit.team
        v = self.surrender_votes.get(team)
        if v is None:
            if not yes:
                return "nessun voto in corso"
            if self.time < self._surr_next[team]:
                return f"resa possibile tra {int(self._surr_next[team] - self.time) + 1} s"
            voters = self._surr_voters(team)
            v = {"by": unit.id, "start": self.time, "voters": {p.id for p in voters},
                 "need": self.surrender_needed(len(voters)), "yes": set(), "no": set()}
            self.surrender_votes[team] = v
        if unit.id not in v["voters"] or unit.id in v["yes"] or unit.id in v["no"]:
            return "hai gia' votato"
        (v["yes"] if yes else v["no"]).add(unit.id)
        self._surr_check(team)
        return None

    def _surr_check(self, team):
        v = self.surrender_votes.get(team)
        if v is None:
            return
        n = len(v["voters"])
        if len(v["yes"]) >= v["need"]:
            del self.surrender_votes[team]
            self.winner = 1 - team
            self.announcements.append((self.time, f"La squadra {'BLU' if team == 0 else 'ROSSA'} si arrende"))
        elif len(v["no"]) > n - v["need"] or self.time - v["start"] >= SURRENDER_VOTE_TIME:
            del self.surrender_votes[team]
            self._surr_next[team] = self.time + SURRENDER_COOLDOWN

    def _surrender_tick(self):
        self._surr_init()
        for team in list(self.surrender_votes):
            self._surr_check(team)

    def surrender_state(self, team) -> dict:
        """Stato del voto per l'HUD: solo dati semplici e ISTANTI assoluti (cambia solo
        quando cambia il voto, quindi online il pacchetto visivo non riparte a ogni tick)."""
        self._surr_init()
        v = self.surrender_votes.get(team)
        out = {"next_at": round(self._surr_next[team], 1)}
        if v is not None:
            out.update(by=v["by"], yes=sorted(v["yes"]), no=sorted(v["no"]), need=v["need"],
                       n=len(v["voters"]), end_at=round(v["start"] + SURRENDER_VOTE_TIME, 1))
        return out
