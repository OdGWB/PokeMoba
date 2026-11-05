@echo off
REM REMORAID (Acqua): tiratore da duello a distanza, danno fisico. Cecchino
REM (brutti colpi +125%), Prendimira (aggancio ogni 10 s), munizioni Acqua/Ghiaccio
REM (W), Pistolacqua, Octazooka. Al liv.8 Octillery (Ventose).
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/remoraid.json
