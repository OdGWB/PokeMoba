@echo off
REM HATTERENE (Psico/Folletto), gia' al liv.8.
REM R a scelta: Distortozona / Strega della Foresta.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/hatenna.json --level 8
