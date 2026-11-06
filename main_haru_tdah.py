"""
Punto de Entrada Principal — Asistente Virtual Educativo para Niños de Primaria con TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Integrantes:
- Conde Merma Javier Leonardo
- Espinoza Condori Ángel Fernando
- Limachi Llusco Lizeth Gabriela
- Mendoza Conde Rolando Junior
- Nacho Hilari Alexander Aron
- Calle Mamani María Elena
- Mollo Ampuero José Fernando
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main() -> None:
    os.chdir(ROOT_DIR)
    from ui.app import VentanaPrincipalHaru

    app = VentanaPrincipalHaru()
    app.mainloop()


if __name__ == "__main__":
    main()
