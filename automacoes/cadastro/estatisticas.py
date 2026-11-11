"""Estatísticas de uso para a pesquisa de implantação em massa.

Cada execução (sessão) é gravada como uma linha JSON num arquivo deste
computador e, se configurada, também numa pasta compartilhada da rede. Assim os
dados de todos os computadores e de todas as sessões podem ser somados no fim.

Por privacidade, nada de CPF, nome ou conta bancária é gravado: só tempos,
situação de cada item e o motivo dos erros (com números longos mascarados).

Formato (uma linha por registro):
    {"tipo": "sessao", "id": ..., "itens": [{"status", "caminho", "segundos", "espera"}, ...]}
    {"tipo": "manual", "id": ..., "caminho": "novo" | "existente", "segundos": ...}
"""

import configparser
import getpass
import json
import os
import platform
import re
import shutil
import sys
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import __version__
from .config import PASTA_DADOS
from .log import logger

VERSAO_DADOS = 1
PASTA_ESTATISTICAS = PASTA_DADOS / "estatisticas"
PASTA_IMPORTADOS = PASTA_ESTATISTICAS / "outros-computadores"
ARQUIVO_AJUSTES = PASTA_ESTATISTICAS / "ajustes.json"
NOME_INI = "CadastroSIGEF.ini"

# Caminhos possíveis de um item
NOVO = "novo"            # credor cadastrado + domicílio (o caso completo)
EXISTENTE = "existente"  # credor já existia: só o domicílio
VALIDACAO = "validacao"  # recusado antes de ir ao SIGEF (dado faltando, banco inválido…)

# Tempos manuais usados enquanto ninguém cronometrou (podem ser ajustados na tela)
ESTIMATIVA_PADRAO = {NOVO: 300.0, EXISTENTE: 180.0}

ROTULO_CAMINHO = {
    NOVO: "Credor novo + conta bancária",
    EXISTENTE: "Só a conta bancária (credor já existia)",
}


# ============================================================ identificação

def computador() -> str:
    return os.environ.get("COMPUTERNAME") or platform.node() or "desconhecido"


def usuario() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "desconhecido"


def _nome_arquivo() -> str:
    seguro = re.sub(r"[^\w.-]+", "_", f"{computador()}__{usuario()}")
    return f"{seguro}.jsonl"


def arquivo_local() -> Path:
    return PASTA_ESTATISTICAS / _nome_arquivo()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ============================================================ ajustes

def _pasta_do_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def ler_ajustes() -> dict:
    """Pasta da pesquisa e tempos manuais estimados.

    A pasta pode vir de um CadastroSIGEF.ini ao lado do programa (útil para a
    equipe de TI configurar todos os computadores de uma vez):
        [pesquisa]
        pasta = \\\\servidor\\compartilhado\\pesquisa-sigef
    """
    ajustes = {"pasta_pesquisa": "", "estimativa": dict(ESTIMATIVA_PADRAO)}

    ini = configparser.ConfigParser()
    try:
        ini.read(_pasta_do_programa() / NOME_INI, encoding="utf-8")
        ajustes["pasta_pesquisa"] = ini.get("pesquisa", "pasta", fallback="").strip()
    except (configparser.Error, OSError):
        pass

    try:
        salvos = json.loads(ARQUIVO_AJUSTES.read_text(encoding="utf-8"))
        ajustes["pasta_pesquisa"] = salvos.get("pasta_pesquisa", ajustes["pasta_pesquisa"])
        ajustes["estimativa"].update({k: float(v) for k, v in salvos.get("estimativa", {}).items()
                                      if k in ESTIMATIVA_PADRAO and float(v) > 0})
    except (OSError, ValueError, TypeError):
        pass

    return ajustes


def gravar_ajustes(ajustes: dict) -> None:
    PASTA_ESTATISTICAS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_AJUSTES.write_text(json.dumps(ajustes, ensure_ascii=False, indent=2),
                               encoding="utf-8")


# ============================================================ coleta

def _motivo_anonimo(texto: str) -> str:
    """Motivo curto do erro, sem números que possam identificar alguém."""
    texto = re.sub(r"\d{4,}", "#", texto or "")
    return " ".join(texto.split())[:90]


@dataclass
class Item:
    status: str
    caminho: str
    segundos: float
    espera: float = 0.0
    motivo: str = ""


@dataclass
class Sessao:
    """Uma execução da automação (um lote digitado ou uma planilha)."""

    modo: str                     # "planilha" | "lotes"
    conferencia: str              # "auto" | "manual"
    interface: str = "janela"     # "janela" | "terminal"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    inicio: str = field(default_factory=_agora)
    fim: str = ""
    interrompida: bool = False
    itens: list = field(default_factory=list)
    _relogio: float = field(default_factory=time.perf_counter, repr=False)
    segundos_sessao: float = 0.0

    def registrar(self, status: str, caminho: str, segundos: float, espera: float = 0.0,
                  motivo: str = "") -> None:
        self.itens.append(Item(status, caminho, round(max(segundos - espera, 0.0), 2),
                               round(espera, 2), _motivo_anonimo(motivo) if status == "ERRO" else ""))

    def encerrar(self, interrompida: bool = False) -> None:
        self.fim = _agora()
        self.interrompida = interrompida
        self.segundos_sessao = round(time.perf_counter() - self._relogio, 2)

    def registro(self) -> dict:
        dados = {chave: valor for chave, valor in asdict(self).items() if not chave.startswith("_")}
        dados.update(tipo="sessao", versao_dados=VERSAO_DADOS, versao_app=__version__,
                     computador=computador(), usuario=usuario())
        return dados


def registro_manual(caminho: str, segundos: float) -> dict:
    return {
        "tipo": "manual", "versao_dados": VERSAO_DADOS, "id": uuid.uuid4().hex,
        "versao_app": __version__, "computador": computador(), "usuario": usuario(),
        "data": _agora(), "caminho": caminho, "segundos": round(segundos, 1),
    }


# ============================================================ gravação

def _acrescentar(registro: dict) -> None:
    """Grava no arquivo deste computador e copia para a pasta da pesquisa."""
    PASTA_ESTATISTICAS.mkdir(parents=True, exist_ok=True)
    local = arquivo_local()

    with open(local, "a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    sincronizar()


def sincronizar() -> bool:
    """Copia o arquivo inteiro deste computador para a pasta compartilhada.

    Copiar o arquivo todo (e não só a última linha) faz a pasta se corrigir
    sozinha quando a rede volta depois de uma falha.
    """
    pasta = ler_ajustes()["pasta_pesquisa"]
    local = arquivo_local()

    if not pasta or not local.exists():
        return False

    try:
        destino = Path(pasta)
        destino.mkdir(parents=True, exist_ok=True)
        temporario = destino / (local.name + ".tmp")
        shutil.copyfile(local, temporario)
        os.replace(temporario, destino / local.name)
        return True
    except OSError as erro:
        logger.info("Pasta da pesquisa indisponível (%s): %s", pasta, erro)
        return False


def salvar_sessao(sessao: Sessao) -> None:
    if not sessao.fim:
        sessao.encerrar()

    try:
        _acrescentar(sessao.registro())
        logger.info("Estatística gravada: sessão %s com %s itens", sessao.id, len(sessao.itens))
    except OSError:
        logger.exception("Não foi possível gravar a estatística da sessão")


def salvar_tempo_manual(caminho: str, segundos: float) -> dict:
    registro = registro_manual(caminho, segundos)
    _acrescentar(registro)
    return registro


def importar_arquivos(caminhos) -> int:
    """Traz arquivos .jsonl de outros computadores (pen drive, e-mail…)."""
    PASTA_IMPORTADOS.mkdir(parents=True, exist_ok=True)
    total = 0

    for caminho in caminhos:
        origem = Path(caminho)
        destino = PASTA_IMPORTADOS / origem.name

        if origem.resolve() == destino.resolve():
            continue

        shutil.copyfile(origem, destino)
        total += 1

    return total


# ============================================================ leitura

LOCAL = "local"
TODOS = "todos"


def arquivos(escopo: str = LOCAL) -> list:
    """Arquivos de dados conforme o escopo: só este computador ou todos."""
    if escopo == LOCAL:
        return [arquivo_local()] if arquivo_local().exists() else []

    encontrados = list(PASTA_ESTATISTICAS.glob("*.jsonl")) + list(PASTA_IMPORTADOS.glob("*.jsonl"))
    pasta = ler_ajustes()["pasta_pesquisa"]

    if pasta:
        try:
            encontrados += list(Path(pasta).glob("*.jsonl"))
        except OSError:
            pass

    return encontrados


def carregar(escopo: str = LOCAL) -> tuple:
    """Lê os registros sem repetir (o mesmo arquivo pode estar local e na rede)."""
    sessoes, manuais, vistos = [], [], set()

    for caminho in arquivos(escopo):
        try:
            linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        for linha in linhas:
            try:
                registro = json.loads(linha)
            except ValueError:
                continue

            if registro.get("id") in vistos:
                continue

            vistos.add(registro.get("id"))

            if registro.get("tipo") == "sessao":
                sessoes.append(registro)
            elif registro.get("tipo") == "manual":
                manuais.append(registro)

    sessoes.sort(key=lambda s: s.get("inicio", ""))
    manuais.sort(key=lambda m: m.get("data", ""))
    return sessoes, manuais


# ============================================================ indicadores

def _media(valores):
    valores = list(valores)
    return sum(valores) / len(valores) if valores else 0.0


@dataclass
class Indicadores:
    sessoes: int = 0
    computadores: int = 0
    usuarios: int = 0
    primeira_data: str = ""
    ultima_data: str = ""
    contagem: dict = field(default_factory=lambda: dict.fromkeys(("OK", "JA", "ERRO", "PULADO"), 0))
    ok_por_caminho: dict = field(default_factory=lambda: {NOVO: 0, EXISTENTE: 0})
    segundos_automacao: float = 0.0       # tempo de máquina de todos os itens enviados ao SIGEF
    segundos_automacao_ok: float = 0.0    # só dos itens concluídos
    segundos_espera: float = 0.0          # tempo de pessoas conferindo/corrigindo
    media_manual: dict = field(default_factory=dict)       # por caminho
    amostras_manuais: dict = field(default_factory=dict)   # por caminho
    segundos_manual_equivalente: float = 0.0
    por_dia: list = field(default_factory=list)
    por_computador: list = field(default_factory=list)
    motivos: list = field(default_factory=list)

    @property
    def feitos(self) -> int:
        return self.contagem["OK"]

    @property
    def processados(self) -> int:
        return sum(self.contagem.values())

    @property
    def media_automacao(self) -> float:
        return self.segundos_automacao_ok / self.feitos if self.feitos else 0.0

    @property
    def media_manual_geral(self) -> float:
        if self.feitos:
            return self.segundos_manual_equivalente / self.feitos

        return _media(self.media_manual.values())

    @property
    def segundos_economizados(self) -> float:
        return self.segundos_manual_equivalente - self.segundos_automacao

    @property
    def vezes_mais_rapido(self) -> float:
        return self.media_manual_geral / self.media_automacao if self.media_automacao else 0.0

    @property
    def taxa_sucesso(self) -> float:
        enviados = self.processados - self.contagem["PULADO"]
        return (self.contagem["OK"] + self.contagem["JA"]) / enviados if enviados else 0.0

    def fonte_manual(self, caminho: str) -> str:
        amostras = self.amostras_manuais.get(caminho, 0)
        return f"medido ({amostras} cronometragens)" if amostras else "estimativa"


def economia_de(itens, media_manual) -> tuple:
    """(segundos manuais equivalentes, segundos de automação) de um conjunto de itens."""
    manual = sum(media_manual.get(i.get("caminho"), media_manual[NOVO])
                 for i in itens if i.get("status") == "OK")
    automacao = sum(i.get("segundos", 0) for i in itens if i.get("caminho") != VALIDACAO)
    return manual, automacao


def calcular(sessoes: list, manuais: list, estimativa: Optional[dict] = None) -> Indicadores:
    """Soma todas as sessões e compara com o tempo manual.

    Metodologia (conservadora):
      - tempo manual equivalente = cadastros concluídos (OK) × tempo médio manual
        do mesmo tipo (credor novo ou só conta), medido por cronômetro; sem
        medições, usa a estimativa ajustável;
      - tempo da automação = soma do tempo de máquina de TODOS os itens enviados
        ao SIGEF, inclusive os que deram erro ou já estavam cadastrados;
      - o tempo de pessoas conferindo na tela é contado à parte (espera);
      - economia = tempo manual equivalente − tempo da automação.
    """
    estimativa = {**ESTIMATIVA_PADRAO, **(estimativa or {})}
    ind = Indicadores(sessoes=len(sessoes))

    por_caminho = defaultdict(list)
    for registro in manuais:
        if registro.get("caminho") in ESTIMATIVA_PADRAO and registro.get("segundos", 0) > 0:
            por_caminho[registro["caminho"]].append(registro["segundos"])

    for caminho in ESTIMATIVA_PADRAO:
        amostras = por_caminho.get(caminho, [])
        ind.amostras_manuais[caminho] = len(amostras)
        ind.media_manual[caminho] = _media(amostras) if amostras else estimativa[caminho]

    dias, maquinas, motivos = defaultdict(list), defaultdict(list), Counter()
    ind.computadores = len({s.get("computador") for s in sessoes})
    ind.usuarios = len({(s.get("computador"), s.get("usuario")) for s in sessoes})

    if sessoes:
        ind.primeira_data = sessoes[0].get("inicio", "")[:10]
        ind.ultima_data = sessoes[-1].get("inicio", "")[:10]

    for sessao in sessoes:
        itens = sessao.get("itens", [])
        dias[sessao.get("inicio", "")[:10]].append(sessao)
        maquinas[sessao.get("computador", "?")].append(sessao)

        for item in itens:
            status = item.get("status", "ERRO")
            ind.contagem[status] = ind.contagem.get(status, 0) + 1
            ind.segundos_espera += item.get("espera", 0)

            if item.get("caminho") != VALIDACAO:
                ind.segundos_automacao += item.get("segundos", 0)

            if status == "OK":
                caminho = item.get("caminho") if item.get("caminho") in ESTIMATIVA_PADRAO else NOVO
                ind.ok_por_caminho[caminho] += 1
                ind.segundos_automacao_ok += item.get("segundos", 0)
                ind.segundos_manual_equivalente += ind.media_manual[caminho]
            elif status == "ERRO":
                motivos[item.get("motivo") or "sem detalhe"] += 1

    def resumir(grupo: dict, chave: str) -> list:
        linhas = []

        for nome, lista in sorted(grupo.items()):
            itens = [i for s in lista for i in s.get("itens", [])]
            manual, automacao = economia_de(itens, ind.media_manual)
            linhas.append({
                chave: nome,
                "sessoes": len(lista),
                "feitos": sum(i.get("status") == "OK" for i in itens),
                "ja": sum(i.get("status") == "JA" for i in itens),
                "erros": sum(i.get("status") == "ERRO" for i in itens),
                "segundos_automacao": automacao,
                "segundos_manual": manual,
                "segundos_economizados": manual - automacao,
            })

        return linhas

    ind.por_dia = resumir(dias, "dia")
    ind.por_computador = resumir(maquinas, "computador")
    ind.motivos = motivos.most_common()
    return ind


def resumo_da_sessao(sessao: Sessao, estimativa: Optional[dict] = None) -> tuple:
    """(feitos, segundos da automação, segundos economizados) de uma sessão recém-terminada."""
    _, manuais = carregar(LOCAL)
    ind = calcular([sessao.registro()], manuais, estimativa or ler_ajustes()["estimativa"])
    return ind.feitos, ind.segundos_automacao, ind.segundos_economizados


# ============================================================ formatação

def formatar_duracao(segundos: float, curto: bool = False) -> str:
    """3725 -> '1 h 2 min'; 200 -> '3 min 20 s'; 42 -> '42 s'.

    Com `curto`, a partir de 10 minutos os segundos são omitidos (1190 -> '20 min').
    """
    negativo = segundos < 0
    segundos = int(round(abs(segundos)))

    if curto and segundos >= 600:
        segundos = int(round(segundos / 60)) * 60
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)

    if horas:
        texto = f"{horas} h {minutos} min" if minutos else f"{horas} h"
    elif minutos:
        texto = f"{minutos} min {seg} s" if seg else f"{minutos} min"
    else:
        texto = f"{seg} s"

    return f"−{texto}" if negativo else texto


def formatar_data(iso: str) -> str:
    """'2026-10-09' -> '09/10/2026'."""
    partes = (iso or "")[:10].split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else (iso or "-")


def formatar_vezes(valor: float) -> str:
    """19.87 -> '19,9×' (padrão brasileiro)."""
    return f"{valor:.1f}×".replace(".", ",") if valor else "-"
