@echo off
rem Installa Stratigrafia 3D in un ambiente Python dedicato (cartella .venv).
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python non trovato.
  echo Installa Python 3.12 da https://www.python.org/downloads/ ^(spunta "Add python.exe to PATH"^) e rilancia questo file.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creo l'ambiente Python...
  py -3 -m venv .venv || goto errore
)
echo Installo le librerie ^(qualche minuto la prima volta^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -e ".[demo]" || goto errore
echo Installo la finestra dell'app...
".venv\Scripts\python.exe" -m pip install "pywebview>=5" || echo Finestra non disponibile: l'app si aprira' nel browser.
echo.
echo Installazione completata. Avvia l'app con "Avvia Stratigrafia 3D.bat".
pause
exit /b 0
:errore
echo Installazione non riuscita. Copia il messaggio qui sopra e mandamelo.
pause
exit /b 1
