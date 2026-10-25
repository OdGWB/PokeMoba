"""Classe base per le scene del client."""
from __future__ import annotations

import pygame


class Scene:
    def handle_events(self, events: list[pygame.event.Event]) -> None:
        """Riceve gli eventi del frame (input, tasti)."""

    def fixed_update(self) -> None:
        """Un tick di simulazione (chiamato a frequenza fissa)."""

    def update(self, dt: float) -> None:
        """Aggiornamenti legati al frame (camera, animazioni)."""

    def draw(self, surface: pygame.Surface) -> None:
        """Disegna la scena sulla surface a bassa risoluzione."""

    def hud_lines(self) -> list[str]:
        """Righe di testo da mostrare nell'HUD (disegnate a piena risoluzione)."""
        return []
