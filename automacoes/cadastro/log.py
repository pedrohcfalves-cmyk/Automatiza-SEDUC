"""Registro das execuções em arquivo, para auditoria posterior."""

import io
import logging
import os
import sys
from datetime import date

from .config import PASTA_LOGS

logger = logging.getLogger("sigef")


def configurar_log() -> None:
    """Grava um arquivo por dia em ~/.sigef-automacao/logs."""
    if logger.handlers:
        return

    try:
        PASTA_LOGS.mkdir(parents=True, exist_ok=True)
        arquivo = PASTA_LOGS / f"cadastrar-{date.today():%Y-%m-%d}.log"
        manipulador = logging.FileHandler(arquivo, encoding="utf-8")
        manipulador.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger.addHandler(manipulador)
        logger.setLevel(logging.INFO)
    except OSError:
        logger.addHandler(logging.NullHandler())


def garantir_saidas() -> None:
    """Programa sem console (executável/pythonw) não tem stdout/stderr de verdade.

    O Playwright repassa o stderr ao processo do navegador (Node.js), que fecha na
    hora se ele for inválido. Aqui as saídas passam a ir para um arquivo de registro.
    """
    for nome in ("stdout", "stderr"):
        atual = getattr(sys, nome)

        try:
            atual.fileno()
            continue
        except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
            pass

        try:
            PASTA_LOGS.mkdir(parents=True, exist_ok=True)
            setattr(sys, nome, open(PASTA_LOGS / "saida-do-programa.log", "a",  # noqa: SIM115
                                    encoding="utf-8", buffering=1))
        except OSError:
            setattr(sys, nome, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
