"""
Relatório geral: TODAS as automações numa página HTML só (a página é montada em
automacoes/relatorio_geral.py; aqui ficam a leitura e as contas).

    resumo = resumir(de, ate, minutos)          # os números (usados nos testes)
    caminho = gerar(de, ate, minutos)           # a página, em <pasta de dados>/relatorios/

Mostra o tempo economizado no total, por automação, por mês e por pessoa, e um
detalhe de cada automação (documentos, etapas, pendências).
`minutos` é quanto leva cada item feito à mão nas automações que não têm uma
estimativa própria: {"OB": 20, "NE": 15, "DARE": 10}. O Gerar pagamento e o
Cadastro de Credores usam as estimativas deles (as das telas de cada um).

DE ONDE VÊM OS NÚMEROS (o que cada automação já grava; nada novo é gravado)

    OB    <pasta SIGEF-SEI>/metricas/metricas.csv (+ metricas_ate_*.csv antigos)
    NE    <pasta SIGEF-SEI>/metricas/metricas_ne.csv
    DARE  <pasta DARE>/dados/desempenho.csv
    PAG   <pasta Anexar Documentos>/relatorios/execucoes.jsonl   (Gerar pagamento)
    CAD   ~/.sigef-automacao/estatisticas/*.jsonl               (Cadastro de Credores,
          com os arquivos que ele já junta de outros computadores)

COMO CONTA (a mesma regra dos relatórios de cada automação)

    item          uma OB ou NE (processo + número), um lançamento do DARE, um processo
                  do Gerar pagamento ou um credor do Cadastro
    concluído     alguma rodada dele terminou bem
    tempo         a soma de TODAS as rodadas, as que falharam também
    economizado   concluídos x tempo à mão - tempo da automação

QUEM É A PESSOA: cada pessoa tem a sua pasta de dados (C:\\Users\\<nome>\\Documents).
O relatório lê a pasta de quem está usando e as pastas extras que forem incluídas (de
colegas, copiadas ou numa pasta da rede); a pessoa é o <nome> do caminho.
"""
import csv
import getpass
import json
import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime

from automacoes.geral import PASTA_DADOS, PASTA_DADOS_ANEXAR

AUTOMACOES = ("OB", "NE", "DARE", "PAG", "CAD")
# Só estas usam os minutos à mão da caixa do relatório; PAG e CAD têm estimativa própria.
COM_MINUTOS = ("OB", "NE", "DARE")
MINUTOS_PADRAO = {"OB": 20, "NE": 15, "DARE": 10}
NOMES = {"OB": "Anexar no SEI (OB)", "NE": "Nota de Empenho", "DARE": "DARE",
         "PAG": "Gerar pagamento", "CAD": "Cadastro de Credores"}
ITEM = {"OB": "OB", "NE": "NE", "DARE": "lançamento", "PAG": "processo", "CAD": "credor"}
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

# Nomes de pasta que não são o nome de ninguém (para achar a pessoa no caminho).
_PASTAS_GENERICAS = {"automacao sigef-sei", "dare automação", "dare automacao", "anexar documentos",
                     "documents", "documentos", "dados", "metricas", "onedrive"}


# ================================================================ Fontes


@dataclass
class Fonte:
    pessoa: str
    pasta_sigef: str = ""   # tem metricas/metricas.csv e metricas_ne.csv
    pasta_dare: str = ""    # tem dados/desempenho.csv
    pasta_anexar: str = ""  # tem relatorios/execucoes.jsonl (Gerar pagamento)
    cadastro: bool = False  # os dados do Cadastro de Credores (desta máquina e os que ele já juntou)


def pessoa_atual() -> str:
    try:
        return os.environ.get("USERNAME") or getpass.getuser()
    except Exception:  # noqa: BLE001 - sem usuário no ambiente
        return "eu"


def _pasta_dare_padrao() -> str:
    from automacoes.dare import config as config_dare

    return str(config_dare.BASE_DADOS)


def _pasta_anexar_padrao() -> str:
    return os.environ.get("ANEXAR_PASTA_DADOS") or PASTA_DADOS_ANEXAR


def fontes_padrao() -> list[Fonte]:
    """As pastas de quem está usando o programa."""
    return [Fonte(pessoa_atual(), PASTA_DADOS, _pasta_dare_padrao(), _pasta_anexar_padrao(), cadastro=True)]


def pessoa_do_caminho(caminho: str) -> str:
    partes = [p for p in re.split(r"[\\/]+", os.path.normpath(caminho)) if p]
    for i, parte in enumerate(partes[:-1]):
        if parte.lower() in ("users", "usuários", "usuarios", "home"):
            return partes[i + 1]
    uteis = [p for p in partes if p.lower() not in _PASTAS_GENERICAS and not p.endswith(":")]
    return uteis[-1] if uteis else caminho


def fonte_da_pasta(caminho: str) -> Fonte:
    """
    Uma pasta de outra pessoa: a pasta de dados dela (Automacao SIGEF-SEI, DARE
    Automação ou Anexar Documentos) ou a pasta acima delas (os Documentos dela).
    Acha sozinho o que houver.
    """
    sigef = dare = anexar = ""
    for candidata in (caminho, os.path.join(caminho, "Automacao SIGEF-SEI")):
        if os.path.isdir(os.path.join(candidata, "metricas")):
            sigef = candidata
            break
    for candidata in (caminho, os.path.join(caminho, "DARE Automação"), os.path.join(caminho, "DARE Automacao")):
        if os.path.isfile(os.path.join(candidata, "dados", "desempenho.csv")):
            dare = candidata
            break
    for candidata in (caminho, os.path.join(caminho, "Anexar Documentos")):
        if os.path.isfile(os.path.join(candidata, "relatorios", "execucoes.jsonl")):
            anexar = candidata
            break
    return Fonte(pessoa_do_caminho(caminho), sigef, dare, anexar)


def tem_dados(fonte: Fonte) -> bool:
    return bool(fonte.pasta_sigef or fonte.pasta_dare or fonte.pasta_anexar or fonte.cadastro)


# ============================================================== Leitura


@dataclass
class Rodada:
    automacao: str
    pessoa: str
    chave: tuple
    inicio: datetime
    concluida: bool
    segundos: float
    manual_s: float | None = None   # tempo à mão desta rodada, quando a automação tem estimativa própria
    dados: dict = field(default_factory=dict)  # a linha gravada, para o detalhe de cada automação


def _numero(texto) -> float:
    try:
        return float(str(texto or "").strip().replace(",", ".") or 0)
    except ValueError:
        return 0.0


def _linhas_csv(caminho: str) -> list[dict]:
    try:
        with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
            return list(csv.DictReader(arquivo, delimiter=";"))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []  # planilha aberta no Excel ou corrompida: o relatório sai sem ela


def _linhas_jsonl(caminho: str) -> list[dict]:
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    saida = []
    for linha in linhas:
        try:
            registro = json.loads(linha)
        except ValueError:
            continue  # linha cortada (programa fechado no meio da gravação)
        if isinstance(registro, dict):
            saida.append(registro)
    return saida


def _data(texto: str):
    try:
        return datetime.strptime((texto or "").strip(), "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def _data_iso(texto) -> datetime | None:
    try:
        return datetime.fromisoformat(str(texto or "").replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _rodadas_sigef(fonte: Fonte, lidos: set) -> list[Rodada]:
    pasta = os.path.join(fonte.pasta_sigef, "metricas")
    if not fonte.pasta_sigef or not os.path.isdir(pasta):
        return []
    rodadas = []
    for nome in sorted(os.listdir(pasta)):
        if nome == "metricas_ne.csv":
            automacao, coluna = "NE", "NE"
        elif nome == "metricas.csv" or (nome.startswith("metricas_ate_") and nome.endswith(".csv")):
            automacao, coluna = "OB", "OB"
        else:
            continue
        caminho = os.path.realpath(os.path.join(pasta, nome))
        if caminho in lidos:  # a mesma pasta incluída duas vezes não conta em dobro
            continue
        lidos.add(caminho)
        for linha in _linhas_csv(caminho):
            inicio = _data(linha.get("Início"))
            if inicio is None:
                continue
            rodadas.append(Rodada(
                automacao, fonte.pessoa, (fonte.pessoa, linha.get("Processo", ""), linha.get(coluna, "")),
                inicio, linha.get("Situação") == "Concluído", _numero(linha.get("Total (s)")), dados=linha,
            ))
    return rodadas


def _rodadas_dare(fonte: Fonte, lidos: set) -> list[Rodada]:
    caminho = os.path.realpath(os.path.join(fonte.pasta_dare, "dados", "desempenho.csv")) if fonte.pasta_dare else ""
    if not caminho or caminho in lidos or not os.path.isfile(caminho):
        return []
    lidos.add(caminho)
    rodadas = []
    for i, linha in enumerate(_linhas_csv(caminho)):
        inicio = _data(linha.get("data_hora"))
        if inicio is None:
            continue
        # Cada linha é um lançamento (o desempenho.csv não guarda processo nem CPF).
        rodadas.append(Rodada("DARE", fonte.pessoa, (fonte.pessoa, caminho, i), inicio,
                              linha.get("status") == "SUCESSO", _numero(linha.get("total_s")), dados=linha))
    return rodadas


def _anexar_estatisticas():
    """O módulo de contas do Gerar pagamento (Anexar Documentos)."""
    # Antes de importar o Anexar: sem isto, ele guardaria a pasta dados\ errada para o resto da sessão.
    os.environ.setdefault("ANEXAR_PASTA_DADOS", PASTA_DADOS_ANEXAR)
    from automacoes.anexar.aplicativo import estatisticas, metricas

    return estatisticas, metricas


def _rodadas_anexar(fonte: Fonte, lidos: set) -> list[Rodada]:
    caminho = os.path.join(fonte.pasta_anexar, "relatorios", "execucoes.jsonl") if fonte.pasta_anexar else ""
    caminho = os.path.realpath(caminho) if caminho else ""
    if not caminho or caminho in lidos or not os.path.isfile(caminho):
        return []
    lidos.add(caminho)
    contas, metricas = _anexar_estatisticas()
    estimativas = metricas.ler_estimativas()  # os minutos à mão da tela dele
    rodadas = []
    for execucao in _linhas_jsonl(caminho):
        inicio = _data_iso(execucao.get("inicio"))
        if inicio is None:
            continue
        # Um processo retomado ("Continuar") tem mais de uma execução: é o mesmo item.
        chave = (fonte.pessoa, execucao.get("processo") or execucao.get("id") or str(inicio))
        rodadas.append(Rodada(
            "PAG", fonte.pessoa, chave, inicio, execucao.get("situacao") in ("concluido", "pendente"),
            _numero(execucao.get("duracao_s")), contas.calcular_economia([execucao], estimativas)["total"]["mao"],
            dados=execucao,
        ))
    return rodadas


def _rodadas_cadastro(fonte: Fonte, lidos: set) -> list[Rodada]:
    if not fonte.cadastro or "cadastro" in lidos:
        return []
    lidos.add("cadastro")
    from automacoes.cadastro import estatisticas as est

    sessoes, manuais = est.carregar(est.TODOS)
    media_manual = est.calcular([], manuais, est.ler_ajustes()["estimativa"]).media_manual
    rodadas = []
    for sessao in sessoes:
        inicio = _data_iso(sessao.get("inicio"))
        if inicio is None:
            continue
        pessoa = sessao.get("usuario") or fonte.pessoa
        for i, item in enumerate(sessao.get("itens") or []):
            caminho = item.get("caminho")
            ok = item.get("status") == "OK"
            rodadas.append(Rodada(
                "CAD", pessoa, (pessoa, sessao.get("id"), i), inicio, ok,
                0.0 if caminho == est.VALIDACAO else _numero(item.get("segundos")),  # recusado antes do SIGEF: sem tempo
                media_manual.get(caminho, media_manual[est.NOVO]) if ok else 0.0,
                dados={**item, "espera": _numero(item.get("espera"))},
            ))
    return rodadas


def ler_rodadas(fontes: list[Fonte]) -> list[Rodada]:
    lidos: set = set()
    rodadas = []
    for fonte in fontes:
        for ler in (_rodadas_sigef, _rodadas_dare, _rodadas_anexar, _rodadas_cadastro):
            try:
                rodadas += ler(fonte, lidos)
            except Exception as erro:  # noqa: BLE001 - uma automação com defeito não derruba o relatório inteiro
                print(f"⚠️  Relatório geral: não consegui ler {ler.__name__[9:]} de {fonte.pessoa} ({erro})")
    rodadas.sort(key=lambda r: r.inicio)
    return rodadas


# ================================================================ Contas


@dataclass
class Item:
    automacao: str
    pessoa: str
    quando: datetime        # a última rodada
    concluido: bool
    segundos: float         # todas as rodadas
    manual_s: float | None = None
    rodadas: list = field(default_factory=list)


def _itens(rodadas: list[Rodada]) -> list[Item]:
    grupos: "OrderedDict[tuple, list[Rodada]]" = OrderedDict()
    for r in rodadas:
        grupos.setdefault((r.automacao, r.chave), []).append(r)
    itens = []
    for grupo in grupos.values():
        manuais = [r.manual_s for r in grupo if r.manual_s is not None]
        itens.append(Item(grupo[0].automacao, grupo[0].pessoa, grupo[-1].inicio,
                          any(r.concluida for r in grupo), sum(r.segundos for r in grupo),
                          sum(manuais) if manuais else None, grupo))
    return itens


@dataclass
class Conta:
    concluidos: dict = field(default_factory=lambda: {a: 0 for a in AUTOMACOES})
    tempo: dict = field(default_factory=lambda: {a: 0.0 for a in AUTOMACOES})
    economia: dict = field(default_factory=lambda: {a: 0.0 for a in AUTOMACOES})
    itens: dict = field(default_factory=lambda: {a: 0 for a in AUTOMACOES})
    manual: dict = field(default_factory=lambda: {a: 0.0 for a in AUTOMACOES})

    def somar(self, item: Item, minutos: dict) -> None:
        a = item.automacao
        self.itens[a] += 1
        self.tempo[a] += item.segundos
        self.economia[a] -= item.segundos
        if item.concluido:
            self.concluidos[a] += 1
            manual = item.manual_s if item.manual_s is not None else minutos[a] * 60
            self.manual[a] += manual
            self.economia[a] += manual

    @property
    def total_concluidos(self) -> int:
        return sum(self.concluidos.values())

    @property
    def total_itens(self) -> int:
        return sum(self.itens.values())

    @property
    def total_tempo(self) -> float:
        return sum(self.tempo.values())

    @property
    def total_economia(self) -> float:
        return sum(self.economia.values())

    @property
    def total_manual(self) -> float:
        return sum(self.manual.values())


@dataclass
class Resumo:
    de: date
    ate: date
    minutos: dict
    geral: Conta
    por_mes: "OrderedDict[str, Conta]"      # "2026-10" -> Conta (meses sem nada também)
    por_pessoa: "OrderedDict[str, Conta]"
    fontes: list
    itens: list = field(default_factory=list)   # os itens do período, para o detalhe de cada automação


def minutos_validos(minutos: dict | None) -> dict:
    saida = dict(MINUTOS_PADRAO)
    for a in COM_MINUTOS:
        try:
            valor = float(str((minutos or {}).get(a, saida[a])).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError(f"Minutos à mão de {a} inválidos.") from None
        if valor <= 0:
            raise ValueError(f"Informe quantos minutos leva um(a) {a} feito(a) à mão.")
        saida[a] = valor
    return saida


def _meses(de: date, ate: date) -> list[str]:
    meses, ano, mes = [], de.year, de.month
    while (ano, mes) <= (ate.year, ate.month):
        meses.append(f"{ano}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


def resumir(de: date, ate: date, minutos: dict | None = None, fontes: list[Fonte] | None = None) -> Resumo:
    if ate < de:  # como nos relatórios de cada automação: datas trocadas valem o mesmo período
        de, ate = ate, de
    minutos = minutos_validos(minutos)
    fontes = fontes if fontes is not None else fontes_padrao()
    rodadas = [r for r in ler_rodadas(fontes) if de <= r.inicio.date() <= ate]
    geral = Conta()
    por_mes = OrderedDict((m, Conta()) for m in _meses(de, ate))
    por_pessoa: "OrderedDict[str, Conta]" = OrderedDict()
    itens = _itens(rodadas)
    for item in itens:
        geral.somar(item, minutos)
        por_mes.setdefault(f"{item.quando:%Y-%m}", Conta()).somar(item, minutos)
        por_pessoa.setdefault(item.pessoa, Conta()).somar(item, minutos)
    por_pessoa = OrderedDict(sorted(por_pessoa.items(), key=lambda par: -par[1].total_economia))
    return Resumo(de, ate, minutos, geral, por_mes, por_pessoa, fontes, itens)


# ================================================================ Página


def gerar(de: date, ate: date, minutos: dict | None = None, fontes: list[Fonte] | None = None,
          destino: str | None = None) -> str:
    from automacoes import relatorio_geral

    resumo = resumir(de, ate, minutos, fontes)
    if destino is None:
        pasta = os.path.join(PASTA_DADOS, "relatorios")
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(
            pasta, f"relatorio_geral_{resumo.de:%Y-%m-%d}_a_{resumo.ate:%Y-%m-%d}_{datetime.now():%H%M%S}.html")
    with open(destino, "w", encoding="utf-8") as arquivo:
        arquivo.write(relatorio_geral.pagina(resumo))
    return destino
