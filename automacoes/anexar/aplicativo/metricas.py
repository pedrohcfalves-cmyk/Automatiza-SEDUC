"""
Dados para os relatórios do estudo sobre a automação.

Cada processo rodado pelo aplicativo vira UMA linha em
dados/relatorios/execucoes.jsonl (um JSON por linha), com:

    - quando começou e terminou, e quanto tempo levou;
    - o tempo de cada etapa (SEI 1, CE, NL, PP, OB, Baixar, SEI 2),
      separado em tempo da MÁQUINA e tempo de ATENÇÃO HUMANA (o tempo em
      que o programa ficou parado esperando uma resposta da pessoa);
    - quantas respostas a pessoa precisou dar;
    - quantos documentos foram gerados (CE, NL, PP, OB) e baixados;
    - os avisos de erro que apareceram (só o título, sem dados pessoais);
    - a situação final: concluído, pendente, erro ou interrompido.

Esse arquivo fica só neste computador (pasta ignorada pelo git): tem
números de processo e valores reais. A exportação do aplicativo tem a
opção de tirar o número do processo (anônimo).

As ESTIMATIVAS de quanto tempo leva fazer cada item À MÃO (base de
comparação das Estatísticas) ficam NO CÓDIGO, no arquivo
estimativas_manuais.py -- o botão "Salvar estimativas" do aplicativo
reescreve esse arquivo (ver ler_estimativas / salvar_estimativas).

Este módulo não depende do Playwright nem do SIGEF -- pode ser testado
sozinho (testes/test_aplicativo.py).

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import ast
import json
import os
import threading
import time
import uuid
from datetime import datetime

from automacoes.anexar import caminhos
from automacoes.anexar.versao import VERSAO

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
# ANEXAR_PASTA_RELATORIOS troca a pasta (usado nos testes, para não sujar a real).
# No modo treino (ANEXAR_MODULO_PRINCIPAL=...modo_treino), os dados vão para
# outra pasta, para nunca se misturarem com os do estudo.
_SIMULACAO = "modo_treino" in os.environ.get("ANEXAR_MODULO_PRINCIPAL", "")
PASTA_RELATORIOS = os.environ.get("ANEXAR_PASTA_RELATORIOS") or (
    caminhos.PASTA_RELATORIOS_TREINO if _SIMULACAO else caminhos.PASTA_RELATORIOS
)
ARQUIVO_EXECUCOES = "execucoes.jsonl"
ARQUIVO_ESTIMATIVAS = os.path.join(PASTA_PROJETO, "estimativas_manuais.py")

# Etapas na ordem do ciclo. "SEI1" começa junto com o ciclo; as outras
# começam quando main.py chama inicio_de_etapa() com a chave delas.
ETAPAS = [
    ("SEI1", "SEI (1) — dados do processo"),
    ("CE", "CE — Despesa Certificada"),
    ("NL", "NL — Nota de Lançamento"),
    ("PP", "PP — Preparação de Pagamento"),
    ("OB", "OB — Ordem Bancária"),
    ("BAIXAR", "Baixar os documentos"),
    ("SEI", "SEI (2) — colocar no processo"),
]
NOMES_ETAPAS = dict(ETAPAS)

_trava_arquivo = threading.Lock()


def _agora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _caminho(nome: str, pasta: str = None) -> str:
    return os.path.join(pasta or PASTA_RELATORIOS, nome)


def _acrescentar(nome: str, registro: dict, pasta: str = None) -> None:
    pasta = pasta or PASTA_RELATORIOS
    os.makedirs(pasta, exist_ok=True)
    with _trava_arquivo, open(_caminho(nome, pasta), "a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _ler(nome: str, pasta: str = None) -> list[dict]:
    caminho = _caminho(nome, pasta)
    if not os.path.exists(caminho):
        return []
    registros = []
    with _trava_arquivo, open(caminho, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                # Linha quebrada (ex: luz acabou no meio da gravação):
                # ignora só ela, o resto do histórico continua valendo.
                continue
            if isinstance(registro, dict):
                registros.append(registro)
    return registros


# ============================================================ execuções


def ler_execucoes(pasta: str = None) -> list[dict]:
    return _ler(ARQUIVO_EXECUCOES, pasta)


def salvar_execucao(registro: dict, pasta: str = None) -> None:
    _acrescentar(ARQUIVO_EXECUCOES, registro, pasta)


def _centavos(valor) -> int | None:
    texto = str(valor or "").strip()
    return int(texto) if texto.isdigit() else None


def contar_documentos(sessao: dict) -> dict:
    """Quantos documentos o processo tem prontos, a partir da sessão salva."""
    lancamentos = sessao.get("lancamentos") or []
    obs = {item.get("ob") for item in lancamentos if item.get("ob")}
    return {
        "ce": 1 if sessao.get("ce") else 0,
        "nl": sum(1 for item in lancamentos if item.get("nl")),
        "pp": sum(1 for item in lancamentos if item.get("pp")),
        "ob": len(obs),
        "baixados": sum(1 for item in lancamentos if item.get("anexo_baixado")),
    }


def contar_novos(antes: list[dict], depois: list[dict], ce_reaproveitada: bool) -> dict:
    """
    Quantos NL/PP/OB foram feitos NESTA execução (e não numa anterior, na
    retomada). Com CE nova, main.py apaga NL/PP/OB antigos -- tudo é novo.
    """
    novos = {"ce": 0 if ce_reaproveitada else 1, "nl": 0, "pp": 0, "ob": 0}
    obs_antes = set()
    for indice, item in enumerate(depois):
        anterior = antes[indice] if (ce_reaproveitada and indice < len(antes)) else {}
        for chave in ("nl", "pp"):
            if item.get(chave) and item.get(chave) != anterior.get(chave):
                novos[chave] += 1
        if anterior.get("ob"):
            obs_antes.add(anterior["ob"])
    obs_depois = {item.get("ob") for item in depois if item.get("ob")}
    novos["ob"] = len(obs_depois - obs_antes)
    return novos


def situacao_final(status: str, sessao: dict) -> str:
    """concluido | pendente | erro | interrompido."""
    if status in ("erro", "interrompido"):
        return status
    lancamentos = sessao.get("lancamentos") or []
    if lancamentos and all(item.get("ob") and item.get("anexo_baixado") for item in lancamentos):
        return "concluido"
    return "pendente"


class Medidor:
    """
    Cronometra UM ciclo (um processo) de cada vez. O executor do
    aplicativo (anexar/aplicativo/executor.py) chama:

        inicio_ciclo() -> inicio_etapa("CE") ... -> fim_ciclo(...)

    e, em volta de cada input(), antes_da_pergunta()/depois_da_pergunta()
    -- é assim que o tempo de ATENÇÃO HUMANA é separado do tempo da máquina.
    `relogio` pode ser trocado nos testes.
    """

    def __init__(self, relogio=time.monotonic, pasta: str = None):
        self.relogio = relogio
        self.pasta = pasta
        self.ciclo = None
        self._pergunta_desde = None

    def inicio_ciclo(self) -> None:
        agora = self.relogio()
        self.ciclo = {
            "inicio_iso": _agora_iso(),
            "t0": agora,
            "etapas": [{"chave": "SEI1", "t0": agora, "humano_s": 0.0, "respostas": 0}],
            "erros": [],
            "antes": [],
            "ce_reaproveitada": False,
        }

    def _etapa_atual(self) -> dict | None:
        return self.ciclo["etapas"][-1] if self.ciclo else None

    def inicio_etapa(self, chave: str) -> None:
        if not self.ciclo:
            return
        atual = self._etapa_atual()
        if atual and atual["chave"] == chave:
            return
        self.ciclo["etapas"].append({"chave": chave, "t0": self.relogio(), "humano_s": 0.0, "respostas": 0})

    def guardar_lancamentos_iniciais(self, lancamentos: list[dict]) -> None:
        if self.ciclo:
            self.ciclo["antes"] = [dict(item) for item in (lancamentos or [])]

    def marcar_ce_reaproveitada(self, reaproveitada: bool) -> None:
        if self.ciclo:
            self.ciclo["ce_reaproveitada"] = bool(reaproveitada)

    def antes_da_pergunta(self) -> None:
        self._pergunta_desde = self.relogio()

    def depois_da_pergunta(self) -> None:
        if self._pergunta_desde is None:
            return
        gasto = max(0.0, self.relogio() - self._pergunta_desde)
        self._pergunta_desde = None
        etapa = self._etapa_atual()
        if etapa is not None:
            etapa["humano_s"] += gasto
            etapa["respostas"] += 1

    def registrar_erro(self, titulo: str) -> None:
        if self.ciclo:
            etapa = self._etapa_atual()
            self.ciclo["erros"].append({"etapa": etapa["chave"] if etapa else None, "titulo": str(titulo)[:160]})

    def fim_ciclo(self, status: str, sessao: dict, salvar: bool = True) -> dict | None:
        """Fecha o ciclo, monta o registro e grava (se `salvar`). Devolve o registro."""
        if not self.ciclo:
            return None
        # Pergunta aberta quando o ciclo terminou (ex: Parar no meio de uma
        # pergunta): o tempo de espera até aqui conta como atenção humana.
        self.depois_da_pergunta()
        fim = self.relogio()
        ciclo = self.ciclo
        self.ciclo = None

        etapas = []
        for indice, etapa in enumerate(ciclo["etapas"]):
            proximo = ciclo["etapas"][indice + 1]["t0"] if indice + 1 < len(ciclo["etapas"]) else fim
            duracao = max(0.0, proximo - etapa["t0"])
            humano = min(etapa["humano_s"], duracao)
            etapas.append({
                "chave": etapa["chave"],
                "duracao_s": round(duracao, 1),
                "humano_s": round(humano, 1),
                "maquina_s": round(duracao - humano, 1),
                "respostas": etapa["respostas"],
            })

        duracao_total = max(0.0, fim - ciclo["t0"])
        humano_total = min(duracao_total, sum(etapa["humano_s"] for etapa in etapas))
        lancamentos = sessao.get("lancamentos") or []
        registro = {
            "id": uuid.uuid4().hex[:12],
            "versao": VERSAO,
            "inicio": ciclo["inicio_iso"],
            "fim": _agora_iso(),
            "situacao": situacao_final(status, sessao),
            "processo": sessao.get("processo") or "",
            "lancamentos": len(lancamentos),
            "valor_total_centavos": _centavos(sessao.get("valor_total_padronizado")),
            "ce_reaproveitada": ciclo["ce_reaproveitada"],
            "duracao_s": round(duracao_total, 1),
            "humano_s": round(humano_total, 1),
            "maquina_s": round(duracao_total - humano_total, 1),
            "respostas": sum(etapa["respostas"] for etapa in etapas),
            "documentos": contar_documentos(sessao),
            "novos": contar_novos(ciclo["antes"], lancamentos, ciclo["ce_reaproveitada"]),
            "etapas": etapas,
            "erros": ciclo["erros"],
        }
        if salvar:
            salvar_execucao(registro, self.pasta)
        return registro


# ============================================================ estimativas (à mão)

# Categorias das Estatísticas: o que é contado como "1 item" e de quais
# etapas vem o tempo COM a automação.
CATEGORIAS = [
    {"chave": "CE", "nome": "CE — Despesa Certificada", "item": "por CE", "etapas": ["CE"]},
    {"chave": "NL", "nome": "NL — Nota de Lançamento", "item": "por NL", "etapas": ["NL"]},
    {"chave": "PP", "nome": "PP — Preparação de Pagamento", "item": "por PP", "etapas": ["PP"]},
    {"chave": "OB", "nome": "OB — Ordem Bancária", "item": "por OB", "etapas": ["OB"]},
    {"chave": "CONFERENCIA", "nome": "Conferência — dados do processo no SEI", "item": "por processo", "etapas": ["SEI1"]},
    {"chave": "ANEXAR", "nome": "Anexar — baixar e colocar no SEI", "item": "por processo", "etapas": ["BAIXAR", "SEI"]},
]
ESTIMATIVAS_PADRAO = {"CE": 3.0, "NL": 3.0, "PP": 3.0, "OB": 4.0, "CONFERENCIA": 2.0, "ANEXAR": 5.0}
ESTIMATIVA_MAXIMA = 240.0  # minutos por item

_MODELO_ESTIMATIVAS = '''"""
Quanto tempo leva fazer 1 item À MÃO, sem o aplicativo (em minutos).

É a base de comparação da tela "Estatísticas": o tempo economizado é
(itens feitos x estes minutos) menos o tempo que a automação levou.

Este arquivo é atualizado pelo próprio aplicativo, no botão
"Salvar estimativas" da tela Estatísticas -- mas também pode ser editado
à mão (só os números). Fica no código de propósito: vai junto com o
programa e entra no histórico do git.

Última alteração: {quando}

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""

ESTIMATIVAS_MINUTOS = {{
{linhas}
}}
'''


def ler_estimativas(caminho: str = None) -> dict:
    """
    Lê ESTIMATIVAS_MINUTOS do estimativas_manuais.py SEM executar o
    arquivo (só lê o dicionário). Faltando algo ou com valor estranho,
    vale o padrão.
    """
    valores = dict(ESTIMATIVAS_PADRAO)
    try:
        with open(caminho or ARQUIVO_ESTIMATIVAS, "r", encoding="utf-8") as arquivo:
            arvore = ast.parse(arquivo.read())
        for no in arvore.body:
            if isinstance(no, ast.Assign) and any(getattr(alvo, "id", None) == "ESTIMATIVAS_MINUTOS" for alvo in no.targets):
                lidos = ast.literal_eval(no.value)
                for chave in ESTIMATIVAS_PADRAO:
                    valor = lidos.get(chave)
                    if isinstance(valor, (int, float)) and 0 <= valor <= ESTIMATIVA_MAXIMA:
                        valores[chave] = float(valor)
    except (OSError, SyntaxError, ValueError, AttributeError):
        pass
    return valores


def salvar_estimativas(novos: dict, caminho: str = None) -> dict:
    """
    Grava as estimativas no estimativas_manuais.py. Lança ValueError com
    uma mensagem simples se algum número não servir. Devolve o que gravou.
    """
    valores = ler_estimativas(caminho)
    nomes = {categoria["chave"]: categoria["nome"] for categoria in CATEGORIAS}
    for chave, valor in (novos or {}).items():
        if chave not in ESTIMATIVAS_PADRAO:
            continue
        try:
            numero = float(str(valor).replace(",", "."))
        except ValueError:
            raise ValueError(f"{nomes[chave]}: digite um número de minutos (ex: 3 ou 2,5).")
        if not 0 <= numero <= ESTIMATIVA_MAXIMA:
            raise ValueError(f"{nomes[chave]}: o tempo vai de 0 a {ESTIMATIVA_MAXIMA:.0f} minutos.")
        valores[chave] = round(numero, 1)
    linhas = "\n".join(
        f'    "{chave}": {valores[chave]!r},  # {nomes[chave]} ({next(c["item"] for c in CATEGORIAS if c["chave"] == chave)})'
        for chave in ESTIMATIVAS_PADRAO
    )
    texto = _MODELO_ESTIMATIVAS.format(quando=datetime.now().strftime("%d/%m/%Y %H:%M"), linhas=linhas)
    destino = caminho or ARQUIVO_ESTIMATIVAS
    temporario = destino + ".tmp"
    with open(temporario, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)
    os.replace(temporario, destino)
    return valores
