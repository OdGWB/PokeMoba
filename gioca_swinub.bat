@echo off
REM SWINUB (Ghiaccio/Terra): jungler tank d'ingaggio. Fiuto (impronte dei nemici
REM nella giungla anche nella nebbia, +30%% ai neutrali), Geloscheggia, Valanga,
REM Forzantica. Al liv.4 Piloswine (Grassospesso), al liv.8 Mamoswine (Gelo).
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/swinub.json
