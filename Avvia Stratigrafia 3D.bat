@echo off
rem Avvia l'app. Si puo' trascinare un file .scavo su questo file per aprirlo.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call "Installa (Windows).bat"
".venv\Scripts\python.exe" -c "import webview" >nul 2>nul
if errorlevel 1 (
  rem senza finestra nativa: si usa il browser, questa finestra resta aperta per chiudere l'app
  ".venv\Scripts\python.exe" -m stratigrafia3d app %*
) else (
  start "" ".venv\Scripts\pythonw.exe" -m stratigrafia3d app %*
)
