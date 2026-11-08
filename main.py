"""Точка входа: python3 main.py [порт]

Запускает локальный веб-интерфейс LTA на 127.0.0.1 (офлайн).
"""
import sys

from lta.app import run

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run(port=port)
