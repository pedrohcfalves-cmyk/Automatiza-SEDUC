"""
Cronômetro de cada OB e a planilha de métricas para relatórios.

Cada OB processada (sozinha ou num lote) vira UMA linha em
<pasta de dados>/metricas/metricas.csv -- um arquivo só, que vai
crescendo, pronto para abrir no Excel e fazer tabela dinâmica:

    Data/hora de início, origem (avulsa/lote), processo, OB, tipo,
    situação, PPs, documentos por tipo (CE, NL, PP, OB), páginas, NLs
    pendentes, tentativas, tempo no SIGEF, tempo no SEI e tempo total
    da automação.

O relatório gerencial (relatorio_gerencial.py) é feito a partir dela.

O tempo é SÓ da automação: o relógio para quando a tela de conferência
abre -- o tempo que a pessoa leva conferindo não entra na conta.

    cron = Cronometro("avulsa", processo, ob, tipo_ob)
    cron.etapa("sigef")      # começa a contar o SIGEF
    cron.etapa("sei")        # fecha o SIGEF, começa o SEI
    cron.parar()             # fecha a etapa aberta (tela de conferência)
    cron.registrar("ok", dados=dados)
"""
import csv
import os
import time
from datetime import datetime

from .etapa_listar_baixar import PASTA_BASE

PASTA_METRICAS = os.path.join(PASTA_BASE, "metricas")
CAMINHO_METRICAS = os.path.join(PASTA_METRICAS, "metricas.csv")

COLUNAS = [
    "Início", "Origem", "Processo", "OB", "Tipo da OB", "Situação",
    "PPs", "CE", "NL", "PP", "OB (doc)", "Documentos", "Páginas", "NLs pendentes",
    "Tentativas",
    "SIGEF (s)", "SEI (s)", "Total (s)",
    "SIGEF (min:s)", "SEI (min:s)", "Total (min:s)",
    "Mensagem",
]

SITUACOES = {"ok": "Concluído", "erro": "Erro", "pulado": "Pulado", "parado": "Interrompido"}


def formatar_duracao(segundos: float | None) -> str:
    """125.4 -> '2:05'; 3725 -> '1:02:05'; None -> ''."""
    if segundos is None:
        return ""
    s = int(round(segundos))
    horas, resto = divmod(s, 3600)
    minutos, s = divmod(resto, 60)
    return f"{horas}:{minutos:02d}:{s:02d}" if horas else f"{minutos}:{s:02d}"


def _numero_br(segundos: float | None) -> str:
    """Segundos com vírgula decimal, que é o que o Excel brasileiro lê como número."""
    return "" if segundos is None else f"{segundos:.1f}".replace(".", ",")


def contar_documentos(dados: dict | None) -> dict:
    """
    Quantos documentos de cada tipo o pacote de baixar_documentos() tem.

    Documento = o que vira UM documento no SEI (uma CE distinta, uma NL
    por PP, uma PP, a OB); páginas = os JPGs que vão dentro deles.
    Sem pacote (parou antes de baixar), tudo vazio.
    """
    if not dados:
        return {chave: "" for chave in ("pps", "ce", "nl", "pp", "ob", "documentos", "paginas", "nls_pendentes")}
    lancamentos = dados.get("lancamentos") or []
    grupos_ce = [arquivos for _, arquivos in (dados.get("grupos_ce") or []) if arquivos]
    arquivos_ob = dados.get("arquivos_ob") or []
    contagem = {
        "pps": len(lancamentos),
        "ce": len(grupos_ce),
        "nl": sum(1 for item in lancamentos if item.get("arquivos_nl")),
        "pp": sum(1 for item in lancamentos if item.get("arquivos_pp")),
        "ob": 1 if arquivos_ob else 0,
        "paginas": (
            len(arquivos_ob) + sum(len(a) for a in grupos_ce)
            + sum(len(item.get("arquivos_nl") or []) + len(item.get("arquivos_pp") or []) for item in lancamentos)
        ),
        "nls_pendentes": sum(1 for aviso in (dados.get("avisos_download") or []) if aviso.startswith("NL")),
    }
    contagem["documentos"] = contagem["ce"] + contagem["nl"] + contagem["pp"] + contagem["ob"]
    return contagem


def _separar_formato_antigo() -> None:
    """
    Se metricas.csv tem outras colunas (versão anterior do programa),
    renomeia para metricas_ate_<data>.csv e deixa começar um novo --
    misturar cabeçalhos estragaria a planilha. ler_metricas() lê os dois.
    """
    if not os.path.exists(CAMINHO_METRICAS):
        return
    with open(CAMINHO_METRICAS, encoding="utf-8-sig", newline="") as arquivo:
        cabecalho = next(csv.reader(arquivo, delimiter=";"), [])
    if cabecalho != COLUNAS:
        destino = os.path.join(PASTA_METRICAS, f"metricas_ate_{datetime.now():%Y-%m-%d_%H%M%S}.csv")
        os.replace(CAMINHO_METRICAS, destino)


def _segundos(texto: str) -> float | None:
    texto = (texto or "").strip().replace(",", ".")
    try:
        return float(texto) if texto else None
    except ValueError:
        return None


def _inteiro(texto: str) -> int:
    try:
        return int((texto or "").strip() or 0)
    except ValueError:
        return 0


def ler_metricas() -> list[dict]:
    """
    Todas as linhas gravadas (metricas.csv e os metricas_ate_*.csv de
    versões anteriores), já convertidas: datas, números e segundos.
    Colunas que um arquivo antigo não tem ficam zeradas.
    """
    if not os.path.isdir(PASTA_METRICAS):
        return []
    linhas = []
    for nome in sorted(os.listdir(PASTA_METRICAS)):
        if not (nome == "metricas.csv" or (nome.startswith("metricas_ate_") and nome.endswith(".csv"))):
            continue
        with open(os.path.join(PASTA_METRICAS, nome), encoding="utf-8-sig", newline="") as arquivo:
            for bruto in csv.DictReader(arquivo, delimiter=";"):
                try:
                    inicio = datetime.strptime(bruto.get("Início", ""), "%d/%m/%Y %H:%M:%S")
                except ValueError:
                    continue
                linhas.append({
                    "inicio": inicio,
                    "origem": bruto.get("Origem", ""),
                    "processo": bruto.get("Processo", ""),
                    "ob": bruto.get("OB", ""),
                    "tipo_ob": bruto.get("Tipo da OB", ""),
                    "situacao": bruto.get("Situação", ""),
                    "pps": _inteiro(bruto.get("PPs")),
                    "ce": _inteiro(bruto.get("CE")),
                    "nl": _inteiro(bruto.get("NL")),
                    "pp": _inteiro(bruto.get("PP")),
                    "ob_doc": _inteiro(bruto.get("OB (doc)")),
                    "documentos": _inteiro(bruto.get("Documentos")),
                    "paginas": _inteiro(bruto.get("Páginas")),
                    "nls_pendentes": _inteiro(bruto.get("NLs pendentes")),
                    "tentativas": _inteiro(bruto.get("Tentativas")),
                    "sigef": _segundos(bruto.get("SIGEF (s)")),
                    "sei": _segundos(bruto.get("SEI (s)")),
                    "total": _segundos(bruto.get("Total (s)")),
                    "mensagem": bruto.get("Mensagem", ""),
                })
    linhas.sort(key=lambda linha: linha["inicio"])
    return linhas


class Cronometro:
    """Mede as etapas de UMA OB. As tentativas repetidas somam no mesmo relógio."""

    def __init__(self, origem: str, processo: str, ob: str, tipo_ob: str = ""):
        self.origem, self.processo, self.ob, self.tipo_ob = origem, processo, ob, tipo_ob
        self.inicio = datetime.now()
        self.tentativas = 0
        self.tempos: dict[str, float] = {}
        self._aberta: str | None = None
        self._desde = 0.0

    def etapa(self, nome: str) -> None:
        """Fecha a etapa aberta e começa a contar `nome`. 'sigef' conta uma tentativa."""
        self.parar()
        if nome == "sigef":
            self.tentativas += 1
        self._aberta, self._desde = nome, time.monotonic()

    def parar(self) -> None:
        if self._aberta is not None:
            decorrido = time.monotonic() - self._desde
            self.tempos[self._aberta] = self.tempos.get(self._aberta, 0.0) + decorrido
            self._aberta = None

    @property
    def total(self) -> float:
        return sum(self.tempos.values())

    def resumo(self) -> str:
        partes = [f"SIGEF {formatar_duracao(self.tempos.get('sigef'))}" if "sigef" in self.tempos else "",
                  f"SEI {formatar_duracao(self.tempos.get('sei'))}" if "sei" in self.tempos else ""]
        return " · ".join(p for p in partes if p) + f" · total {formatar_duracao(self.total)}"

    def registrar(self, situacao: str, dados: dict | None = None, mensagem: str = "") -> dict:
        """
        Fecha o relógio e acrescenta a linha em metricas.csv. Devolve os
        tempos (segundos) para a tela. Nunca derruba o programa: se a
        planilha estiver aberta no Excel (travada), só avisa.
        """
        self.parar()
        doc = contar_documentos(dados)
        sigef, sei = self.tempos.get("sigef"), self.tempos.get("sei")
        linha = [
            f"{self.inicio:%d/%m/%Y %H:%M:%S}", self.origem, self.processo, self.ob, self.tipo_ob,
            SITUACOES.get(situacao, situacao),
            doc["pps"], doc["ce"], doc["nl"], doc["pp"], doc["ob"], doc["documentos"], doc["paginas"],
            doc["nls_pendentes"], self.tentativas,
            _numero_br(sigef), _numero_br(sei), _numero_br(self.total),
            formatar_duracao(sigef), formatar_duracao(sei), formatar_duracao(self.total),
            (mensagem or "").replace("\n", " ").strip()[:300],
        ]
        try:
            os.makedirs(PASTA_METRICAS, exist_ok=True)
            _separar_formato_antigo()
            novo = not os.path.exists(CAMINHO_METRICAS)
            with open(CAMINHO_METRICAS, "a", encoding="utf-8-sig" if novo else "utf-8", newline="") as arquivo:
                saida = csv.writer(arquivo, delimiter=";")
                if novo:
                    saida.writerow(COLUNAS)
                saida.writerow(linha)
        except OSError as erro:
            print(f"⚠️  Não consegui gravar a métrica em {CAMINHO_METRICAS} ({erro}) -- a planilha está aberta no Excel?")

        print(f"⏱️  Tempo da automação: {self.resumo()}")
        return {"sigef": sigef, "sei": sei, "total": self.total}
