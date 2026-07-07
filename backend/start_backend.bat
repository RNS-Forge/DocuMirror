@echo off
cd /d "c:\RNS Office\Axodian\My Projects\DocuMirror\backend"
"c:\RNS Office\Axodian\My Projects\DocuMirror\backend\.venv\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8000 --reload
