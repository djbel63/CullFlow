#!/usr/bin/env bash
set -e

# ==============================================================
#  ⚡ CullFlow — The Private AI RAW Culling & Studio (Linux/macOS)
# ==============================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo ""
echo "=============================================================="
echo "  ⚡ CullFlow — The Private AI RAW Culling & Studio"
echo "=============================================================="
echo ""

# 1. Verificar si existe el entorno virtual
if [ ! -f ".venv/bin/python" ]; then
    echo "[1/3] Detectando Python 3..."
    if command -v python3 >/dev/null 2>&1; then
        PY_CMD="python3"
    elif command -v python >/dev/null 2>&1; then
        PY_CMD="python"
    else
        echo "[ERROR] Python 3 no está instalado. Instálalo desde tu gestor de paquetes o https://python.org"
        exit 1
    fi

    echo "[OK] $($PY_CMD --version)"
    echo ""
    echo "[2/3] Creando entorno virtual (.venv)..."
    $PY_CMD -m venv .venv

    echo ""
    echo "[3/3] Instalando dependencias de CullFlow..."
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
    echo ""
    echo "¡Instalación completada con éxito!"
fi

echo "Iniciando estudio CullFlow..."
echo "URL local: http://127.0.0.1:8765"
echo ""

# Abrir navegador según SO
(sleep 2 && {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://127.0.0.1:8765"
    elif command -v open >/dev/null 2>&1; then
        open "http://127.0.0.1:8765"
    fi
}) &

.venv/bin/python revelar.py web --puerto 8765
