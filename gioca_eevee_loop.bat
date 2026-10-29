@echo off
REM EEVEE in LOOP per il playtest: quando chiudi la finestra del gioco parte
REM subito un'altra partita (liv.4). Per smettere chiudi QUESTA finestra nera
REM (o Ctrl+C qui dentro).
cd /d "%~dp0"
title Eevee playtest - chiudi questa finestra per smettere
:loop
echo.
echo === Nuova partita con Eevee (chiudi questa finestra per smettere) ===
python run_client.py --single --pokemon data/pokemon/eevee.json --level 4
timeout /t 1 /nobreak >nul
goto loop
