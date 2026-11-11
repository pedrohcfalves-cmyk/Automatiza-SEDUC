"""
Junta os PDFs dos DAREs de um mesmo processo num único arquivo, para anexá-lo UMA vez no SEI.

- agrupar_por_processo / ordenar_por_processo: deixam os lançamentos do mesmo processo juntos
  (na ordem em que cada processo aparece na lista), para gerar os DAREs e anexar de uma vez.
- preparar_anexos: devolve o(s) arquivo(s) a anexar no SEI. Com 2 ou mais DAREs, junta tudo
  num PDF só; com 1, anexa o próprio PDF. Se não der para juntar (componente pypdf ausente ou
  um PDF ilegível), anexa os PDFs um a um, como antes, para não perder o lançamento.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from . import config, utils
from .modelos import DadosDare

try:  # componente leve, puro Python; sem ele o programa anexa os PDFs um a um
    from pypdf import PdfWriter
except ImportError:  # pragma: no cover - depende do ambiente
    PdfWriter = None

log = logging.getLogger("dare.juntar")


def disponivel() -> bool:
    """True se o componente que junta PDFs (pypdf) está instalado."""
    return PdfWriter is not None


def chave_processo(processo: str) -> str:
    """Mesmo processo digitado com ou sem pontuação vira a mesma chave."""
    return utils.somente_digitos(processo) or processo.strip()


def agrupar_por_processo(lotes: list[DadosDare]) -> list[list[int]]:
    """Índices (base 0) agrupados por processo, na ordem em que cada processo aparece."""
    grupos: dict[str, list[int]] = {}
    for i, dados in enumerate(lotes):
        grupos.setdefault(chave_processo(dados.processo), []).append(i)
    return list(grupos.values())


def ordenar_por_processo(lotes: list[DadosDare]) -> list[DadosDare]:
    """Reordena (de forma estável) para que os lançamentos do mesmo processo fiquem seguidos."""
    return [lotes[i] for grupo in agrupar_por_processo(lotes) for i in grupo]


def nome_arquivo_juntado(processo: str, quantidade: int, quando: datetime | None = None) -> str:
    quando = quando or datetime.now()
    return (f"DARE_JUNTADO_{utils.somente_digitos(processo)}_{quantidade}-DAREs"
            f"_{quando:%d-%m-%Y_%H%M%S}.pdf")


def juntar_pdfs(pdfs: list[Path], processo: str, pasta: Path | None = None) -> Path:
    """Junta `pdfs` (na ordem dada) num novo PDF na pasta dos PDFs e devolve o caminho."""
    if PdfWriter is None:
        raise RuntimeError("O componente pypdf não está instalado.")
    pasta = Path(pasta or config.PASTA_PDF)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = utils.caminho_sem_conflito(pasta / nome_arquivo_juntado(processo, len(pdfs)))
    temporario = destino.with_name(destino.name + ".tmp")
    escritor = PdfWriter()
    try:
        for pdf in pdfs:
            escritor.append(str(pdf))
        with open(temporario, "wb") as f:
            escritor.write(f)
        os.replace(temporario, destino)  # nunca deixa um PDF pela metade com o nome final
    finally:
        escritor.close()
        if temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                pass
    return destino


def preparar_anexos(pdfs: list[Path], processo: str) -> list[Path]:
    """Arquivo(s) a anexar no SEI para um processo: o PDF juntado, ou os PDFs um a um se não der."""
    pdfs = [Path(p) for p in pdfs]
    if len(pdfs) <= 1:
        return pdfs
    if PdfWriter is None:
        log.warning("Componente pypdf ausente: os %d DAREs do processo %s serão anexados um a um.",
                    len(pdfs), processo)
        return pdfs
    log.info("Juntando %d DAREs do processo %s num único PDF.", len(pdfs), processo)
    try:
        destino = juntar_pdfs(pdfs, processo)
    except Exception:  # noqa: BLE001 - não perde o lançamento: anexa os PDFs separados
        log.warning("Não consegui juntar os PDFs do processo %s; serão anexados um a um.",
                    processo, exc_info=True)
        return pdfs
    log.info("PDF juntado: %s", destino)
    return [destino]
