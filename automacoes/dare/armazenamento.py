"""Persistência local: últimos dados digitados (JSON) e histórico das execuções (CSV)."""

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from . import config
from .modelos import DadosDare

log = logging.getLogger("dare.armazenamento")

COLUNAS_HISTORICO = [
    "data_hora", "status", "processo", "cnpj", "cpf", "servidor", "cnpj_recolhedor",
    "mes_ano_referencia", "vencimento", "valor", "pdf", "observacao",
]


def carregar_ultimos() -> DadosDare | None:
    """Últimos dados salvos (usados como padrão no menu) ou None se não houver/estiver ilegível."""
    try:
        bruto = json.loads(config.ARQ_ULTIMOS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Não consegui ler %s (%s). Ignorando.", config.ARQ_ULTIMOS, exc)
        return None
    return DadosDare.de_dict(bruto)


def salvar_ultimos(dados: DadosDare) -> None:
    """Grava de forma atômica (arquivo temporário + troca), sem risco de ficar pela metade."""
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = Path(f"{config.ARQ_ULTIMOS}.tmp")
    temporario.write_text(
        json.dumps(dados.para_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporario, config.ARQ_ULTIMOS)
    log.debug("Últimos dados salvos em %s", config.ARQ_ULTIMOS)


def registrar_historico(
    dados: DadosDare,
    status: str,
    servidor: str = "",
    pdf: Path | str = "",
    observacao: str = "",
) -> None:
    """Acrescenta uma linha ao historico.csv (separador ';', abre direto no Excel)."""
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    novo = not config.ARQ_HISTORICO.exists()
    linha = {
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "status": status,
        "processo": dados.processo,
        "cnpj": dados.cnpj,
        "cpf": dados.cpf,
        "servidor": servidor,
        "cnpj_recolhedor": dados.cnpj_recolhedor,
        "mes_ano_referencia": dados.mes_ano_referencia,
        "vencimento": dados.vencimento.strftime("%d/%m/%Y"),
        "valor": dados.valor,
        "pdf": str(pdf),
        "observacao": observacao,
    }
    with open(config.ARQ_HISTORICO, "a", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, COLUNAS_HISTORICO, delimiter=";")
        if novo:
            escritor.writeheader()
        escritor.writerow(linha)


def ler_historico(limite: int = 10) -> list[dict]:
    """As últimas `limite` execuções, da mais recente para a mais antiga."""
    try:
        with open(config.ARQ_HISTORICO, newline="", encoding="utf-8-sig") as f:
            linhas = list(csv.DictReader(f, delimiter=";"))
    except FileNotFoundError:
        return []
    except (OSError, csv.Error) as exc:
        log.warning("Não consegui ler o histórico (%s).", exc)
        return []
    return list(reversed(linhas[-limite:]))


# ---- Lote pendente ------------------------------------------------------------------------

def salvar_lote(lotes: list[DadosDare]) -> None:
    """Guarda os lançamentos ainda não concluídos (para retomar após erro ou queda)."""
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = Path(f"{config.ARQ_LOTE}.tmp")
    temporario.write_text(
        json.dumps([d.para_dict() for d in lotes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporario, config.ARQ_LOTE)


def carregar_lote() -> list[DadosDare]:
    """Lançamentos pendentes salvos (lista vazia se não houver ou estiver ilegível)."""
    try:
        bruto = json.loads(config.ARQ_LOTE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        log.warning("Não consegui ler %s (%s). Ignorando.", config.ARQ_LOTE, exc)
        return []
    if not isinstance(bruto, list):
        return []
    lotes = [DadosDare.de_dict(item) for item in bruto if isinstance(item, dict)]
    return [d for d in lotes if d is not None]


def limpar_lote() -> None:
    try:
        config.ARQ_LOTE.unlink()
    except FileNotFoundError:
        pass
