@echo off
REM Crea PokrLOL.exe (un unico file, senza console) in dist\PokrLOL.exe.
REM Doppio clic ogni volta che vuoi un exe aggiornato da mandare in giro.
cd /d "%~dp0"

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installo PyInstaller...
    python -m pip install pyinstaller || goto :errore
)

echo Creo l'exe, ci vuole qualche minuto...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name PokrLOL ^
    --icon "%~dp0assets\ui\icon.ico" ^
    --add-data "%~dp0assets;assets" ^
    --add-data "%~dp0data;data" ^
    --collect-submodules game --collect-submodules engine ^
    --collect-submodules net --collect-submodules sim ^
    --collect-all aiortc ^
    --distpath dist --workpath build\pyinstaller --specpath build ^
    "%~dp0run_client.py" || goto :errore

echo.
echo FATTO: %~dp0dist\PokrLOL.exe
echo Manda quel file agli amici. Nome e immagine profilo sono salvati su ogni
echo PC in %%APPDATA%%\PokrLOL, quindi ognuno ha i suoi.
pause
exit /b 0

:errore
echo.
echo ERRORE: creazione dell'exe fallita (vedi sopra).
pause
exit /b 1
