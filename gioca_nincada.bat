@echo off
rem Avvia subito una partita in locale con Nincada/Ninjask (vs bot).
rem Parte al livello 8 (gia' Ninjask) cosi' puoi provare subito la passiva Muta,
rem la forma Shedinja e la R Rancore.
rem   Tasto H = entra SUBITO nella forma Shedinja (test, ignora la ricarica).
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/nincada.json --level 8
