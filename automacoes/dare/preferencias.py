"""Preferências do aplicativo (dados/preferencias.json): pasta dos PDFs, limpeza automática etc."""

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import config

log = logging.getLogger("dare.preferencias")


@dataclass
class Preferencias:
    pasta_pdf: str = ""  # vazio = pasta padrão (config.PASTA_PDF_PADRAO ou DARE_PASTA_PDF)
    abrir_navegador_ao_iniciar: bool = True
    usar_lixeira: bool = True  # apagar PDFs mandando para a Lixeira (dá para recuperar)
    proteger_nao_anexados: bool = True  # não apagar PDFs de DAREs gerados mas não anexados
    limpeza_automatica: bool = False  # ao abrir o programa, apagar PDFs antigos
    limpeza_dias: int = 30  # "antigos" = com mais de N dias
    aviso_tamanho_mb: int = 500  # avisar quando a pasta dos PDFs passar deste tamanho (0 = nunca)
    ultima_limpeza: str = ""  # dd/mm/aaaa hh:mm da última limpeza

    @classmethod
    def de_dict(cls, d: dict) -> "Preferencias":
        padrao = cls()
        valores = {}
        for campo in fields(cls):
            if campo.name not in d:
                continue
            bruto, tipo = d[campo.name], type(getattr(padrao, campo.name))
            try:
                valores[campo.name] = bruto if isinstance(bruto, tipo) else tipo(bruto)
            except (TypeError, ValueError):
                continue
        return cls(**valores)


def carregar() -> Preferencias:
    try:
        bruto = json.loads(config.ARQ_PREFERENCIAS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Preferencias()
    except (OSError, ValueError) as exc:
        log.warning("Não consegui ler %s (%s). Usando o padrão.", config.ARQ_PREFERENCIAS, exc)
        return Preferencias()
    return Preferencias.de_dict(bruto) if isinstance(bruto, dict) else Preferencias()


def salvar(pref: Preferencias) -> None:
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = Path(f"{config.ARQ_PREFERENCIAS}.tmp")
    temporario.write_text(json.dumps(asdict(pref), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, config.ARQ_PREFERENCIAS)


def aplicar(pref: Preferencias) -> None:
    """Aplica as preferências que mudam o comportamento do núcleo (hoje: a pasta dos PDFs)."""
    if pref.pasta_pdf:
        config.PASTA_PDF = Path(pref.pasta_pdf)
    else:
        config.PASTA_PDF = Path(os.environ.get("DARE_PASTA_PDF") or config.PASTA_PDF_PADRAO)
