@echo off
cd /d "%~dp0"

if not exist "venv\" (
    echo Criando ambiente virtual...
    python -m venv venv
)

echo Ativando ambiente virtual...
call venv\Scripts\activate.bat

echo Instalando dependencias...
pip install -q -r requirements.txt

echo Iniciando TokenSaver...
streamlit run app.py

pause
