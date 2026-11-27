@echo off
REM Crea PokeMoba.exe (un unico file, senza console) in dist\PokeMoba.exe.
REM Doppio clic ogni volta che vuoi un exe aggiornato da mandare in giro.
cd /d "%~dp0"

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installo PyInstaller...
    python -m pip install pyinstaller || goto :errore
)

REM Il motore Rust (native/) fa parte del gioco: si ricompila a ogni exe.
where cargo >nul 2>&1
if errorlevel 1 (
    echo Manca Rust: installalo da https://rustup.rs e rilancia.
    goto :errore
)
python -m maturin --version >nul 2>&1
if errorlevel 1 (
    echo Installo maturin...
    python -m pip install maturin==1.16.0 || goto :errore
)
echo Compilo il motore Rust...
python tools\build_native.py || goto :errore

echo Creo l'exe, ci vuole qualche minuto...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name PokeMoba ^
    --icon "%~dp0assets\ui\icon.ico" ^
    --add-data "%~dp0assets;assets" ^
    --add-data "%~dp0data;data" ^
    --collect-submodules game --collect-submodules engine ^
    --collect-submodules net --collect-submodules sim ^
    --collect-all aiortc ^
    --distpath dist --workpath build\pyinstaller --specpath build ^
    "%~dp0run_client.py" || goto :errore

start /wait "" "%~dp0dist\PokeMoba.exe" --check-engine
if errorlevel 1 (
    echo L'exe non carica il motore Rust: non distribuirlo.
    goto :errore
)

echo.
echo FATTO: %~dp0dist\PokeMoba.exe
echo Manda quel file agli amici. Nome e immagine profilo sono salvati su ogni
echo PC in %%APPDATA%%\PokeMoba, quindi ognuno ha i suoi.
pause
exit /b 0

:errore
echo.
echo ERRORE: creazione dell'exe fallita (vedi sopra).
pause
exit /b 1
