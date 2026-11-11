"""
Cronômetro de cada NE e a planilha de métricas (metricas/metricas_ne.csv).

Igual ao da OB (automacoes/sigef_sei/metricas.py) -- mesmo relógio, mesma regra de só contar o
tempo da automação --, mas com as colunas da NE, num arquivo separado:
as NEs não entram nas contas do relatório das OBs.

    cron = CronometroNE("avulsa", processo, ne)
    cron.etapa("sigef"); cron.etapa("sei")
    cron.registrar("ok", dados=dados)       # dados = o pacote de baixar_ne()
"""
import csv
import os
from datetime import datetime

from automacoes.sigef_sei.etapa_listar_baixar import PASTA_BASE
from automacoes.sigef_sei.metricas import SITUACOES, Cronometro, _inteiro, _numero_br, _segundos, formatar_duracao

PASTA_METRICAS = os.path.join(PASTA_BASE, "metricas")
CAMINHO_METRICAS_NE = os.path.join(PASTA_METRICAS, "metricas_ne.csv")

COLUNAS_NE = [
    "Início", "Origem", "Processo", "NE", "Situação", "Páginas", "Tentativas",
    "SIGEF (s)", "SEI (s)", "Total (s)", "SIGEF (min:s)", "SEI (min:s)", "Total (min:s)", "Mensagem",
]


class CronometroNE(Cronometro):
    """Mede as etapas de UMA NE. As tentativas repetidas somam no mesmo relógio."""

    def __init__(self, origem: str, processo: str, ne: str):
        super().__init__(origem, processo, ne)

    def registrar(self, situacao: str, dados: dict | None = None, mensagem: str = "") -> dict:
        """
        Fecha o relógio e acrescenta a linha em metricas_ne.csv. Nunca
        derruba o programa: se a planilha estiver aberta no Excel, só avisa.
        """
        self.parar()
        sigef, sei = self.tempos.get("sigef"), self.tempos.get("sei")
        linha = [
            f"{self.inicio:%d/%m/%Y %H:%M:%S}", self.origem, self.processo, self.ob,
            SITUACOES.get(situacao, situacao), len((dados or {}).get("arquivos") or []), self.tentativas,
            _numero_br(sigef), _numero_br(sei), _numero_br(self.total),
            formatar_duracao(sigef), formatar_duracao(sei), formatar_duracao(self.total),
            (mensagem or "").replace("\n", " ").strip()[:300],
        ]
        try:
            os.makedirs(PASTA_METRICAS, exist_ok=True)
            novo = not os.path.exists(CAMINHO_METRICAS_NE)
            with open(CAMINHO_METRICAS_NE, "a", encoding="utf-8-sig" if novo else "utf-8", newline="") as arquivo:
                saida = csv.writer(arquivo, delimiter=";")
                if novo:
                    saida.writerow(COLUNAS_NE)
                saida.writerow(linha)
        except OSError as erro:
            print(f"⚠️  Não consegui gravar a métrica em {CAMINHO_METRICAS_NE} ({erro}) -- a planilha está aberta no Excel?")

        print(f"⏱️  Tempo da automação: {self.resumo()}")
        return {"sigef": sigef, "sei": sei, "total": self.total}


def ler_metricas_ne() -> list[dict]:
    """Todas as linhas de metricas_ne.csv, com data, números e segundos já convertidos."""
    if not os.path.exists(CAMINHO_METRICAS_NE):
        return []
    linhas = []
    with open(CAMINHO_METRICAS_NE, encoding="utf-8-sig", newline="") as arquivo:
        for bruto in csv.DictReader(arquivo, delimiter=";"):
            try:
                inicio = datetime.strptime(bruto.get("Início", ""), "%d/%m/%Y %H:%M:%S")
            except ValueError:
                continue
            linhas.append({
                "inicio": inicio,
                "origem": bruto.get("Origem", ""),
                "processo": bruto.get("Processo", ""),
                "ne": bruto.get("NE", ""),
                "situacao": bruto.get("Situação", ""),
                "paginas": _inteiro(bruto.get("Páginas")),
                "tentativas": _inteiro(bruto.get("Tentativas")),
                "sigef": _segundos(bruto.get("SIGEF (s)")),
                "sei": _segundos(bruto.get("SEI (s)")),
                "total": _segundos(bruto.get("Total (s)")),
                "mensagem": bruto.get("Mensagem", ""),
            })
    linhas.sort(key=lambda linha: linha["inicio"])
    return linhas
