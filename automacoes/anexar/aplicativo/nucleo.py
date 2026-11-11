"""
Anexar Documentos -- o NÚCLEO do aplicativo (o que roda por trás da janela).

A janela (anexar/janela/) é nativa; este módulo não conhece janela nenhuma. Ele cuida de:

- Execucao: a automação (anexar/automacao/fluxo.py, ou o modo treino) rodando em OUTRO processo, através
  de executor.py. Lê tudo o que ela mostra (texto do registro técnico e eventos), guarda o estado atual
  (etapa, pergunta aberta, andamento, lançamentos ao vivo...) e manda de volta as respostas da pessoa.
  Cada pergunta chega como um PEDIDO (botões, a tabela dos dados, "Confira os dados"...).
- a sessão guardada (dados/sessao_atual.json) e as tabelas das Configurações;
- abrir pastas no Explorador.

Só usa a biblioteca padrão do Python.

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import codecs
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from automacoes.anexar import caminhos
from automacoes.anexar.aplicativo.executor import MODULO_PADRAO, MODULO_TREINO
from automacoes.anexar.automacao import configuracoes, interacao

PASTA_PROJETO = caminhos.RAIZ
ARQUIVO_SESSAO = caminhos.ARQUIVO_SESSAO
ARQUIVO_LOG = caminhos.ARQUIVO_REGISTRO_APP

MARCA_EVENTO = "\x1e"
MAXIMO_DE_ITENS = 6000          # linhas/eventos guardados para a tela
MODOS_PERMITIDOS = {"automacao"}

def registrar(texto: str) -> None:
    """Log simples do aplicativo (útil quando ele roda sem janela preta)."""
    try:
        caminhos.garantir_pasta(ARQUIVO_LOG)
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"{time.strftime('%d/%m/%Y %H:%M:%S')} {texto}\n")
    except OSError:
        pass


def comando_do_executor(modo: str) -> list:
    """
    Como abrir a automação em outro processo. Rodando pelo código: python -m ...executor.
    No .exe do instalador (PyInstaller) não existe "python -m": o próprio .exe é aberto de novo
    com --executor (ver app.py).
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--executor", modo]
    return [python_para_o_executor(), "-u", "-m", "automacoes.anexar.aplicativo.executor", modo]


def python_para_o_executor() -> str:
    """python.exe (não pythonw.exe): o executor precisa de saída de texto."""
    executavel = sys.executable
    if os.path.basename(executavel).lower() == "pythonw.exe":
        irmao = os.path.join(os.path.dirname(executavel), "python.exe")
        if os.path.exists(irmao):
            return irmao
    return executavel


def ler_sessao() -> dict:
    try:
        with open(ARQUIVO_SESSAO, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resumo_da_sessao() -> dict:
    """O processo que ficou guardado (para a tela inicial oferecer continuar)."""
    return interacao.resumo_da_sessao(ler_sessao())

# ============================================================ processo em execução


class Execucao:
    """A automação (via executor.py) rodando, e tudo o que ela mostrou."""

    def __init__(self):
        self.trava = threading.Lock()
        self.processo = None
        self.modo = None
        self.treino = False
        self.itens = []          # [{"seq", "tipo", ...}]
        self.seq = 0
        self.etapa = None
        self.etapa_info = None   # {"chave", "titulo", "texto"} da etapa atual
        self.pergunta = None     # o PEDIDO aberto (dict); None = não está esperando
        self.andamento = None    # o que o programa está fazendo agora
        self.sessao = None       # lançamentos com NL/PP/OB, ao vivo
        self.resumo = None       # resumo do último processo
        self.ultimo_ciclo = None
        self.codigo_saida = None
        self.parar_pedido_em = None

    # ---------- estado

    @property
    def rodando(self) -> bool:
        return self.processo is not None and self.processo.poll() is None

    def estado(self) -> dict:
        with self.trava:
            return {
                "rodando": self.rodando,
                "modo": self.modo,
                "treino": self.treino,
                "etapa": self.etapa,
                "etapa_info": self.etapa_info,
                "pergunta": self.pergunta,
                "andamento": self.andamento,
                "sessao": self.sessao,
                "resumo": self.resumo,
                "ultimo_ciclo": self.ultimo_ciclo,
                "codigo_saida": self.codigo_saida,
                "seq": self.seq,
            }

    def _adicionar(self, item: dict) -> None:
        # chamado com a trava
        self.seq += 1
        item["seq"] = self.seq
        self.itens.append(item)
        if len(self.itens) > MAXIMO_DE_ITENS:
            del self.itens[: len(self.itens) - MAXIMO_DE_ITENS]

    def itens_desde(self, seq: int) -> list[dict]:
        with self.trava:
            if self.itens and seq < self.itens[0]["seq"] - 1:
                # A tela ficou muito para trás: manda o que ainda existe.
                return list(self.itens)
            return [item for item in self.itens if item["seq"] > seq]

    # ---------- ciclo de vida

    def iniciar(self, modo: str, treino: bool = False) -> None:
        with self.trava:
            if self.rodando:
                raise RuntimeError("O programa já está rodando. Termine ou pare antes de começar outro.")
            self.modo = modo
            self.treino = bool(treino and modo == "automacao")
            self.etapa = None
            self.etapa_info = None
            self.pergunta = None
            self.andamento = None
            self.sessao = None
            self.resumo = None
            self.codigo_saida = None
            self.parar_pedido_em = None
            self._adicionar({"tipo": "evento", "evento": {"tipo": "sessao_app", "modo": modo, "treino": self.treino}})

        ambiente = dict(os.environ)
        ambiente.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        if self.treino:
            # Processo de mentira: nada no SEI/SIGEF, dados em dados/relatorios_simulacao/.
            ambiente["ANEXAR_MODULO_PRINCIPAL"] = MODULO_TREINO
            ambiente.setdefault("ANEXAR_SESSAO_SIMULADA", caminhos.ARQUIVO_SESSAO_TREINO)
            ambiente.setdefault("ANEXAR_DEMO_PAUSA", "1")
        elif ambiente.get("ANEXAR_MODULO_PRINCIPAL") in (None, "", MODULO_TREINO):
            ambiente["ANEXAR_MODULO_PRINCIPAL"] = MODULO_PADRAO
        opcoes = {}
        if os.name == "nt":
            opcoes["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        processo = subprocess.Popen(
            comando_do_executor(modo),
            cwd=PASTA_PROJETO,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=ambiente,
            bufsize=0,
            **opcoes,
        )
        with self.trava:
            self.processo = processo
        threading.Thread(target=self._ler_saida, args=(processo,), daemon=True).start()
        registrar(f"Iniciado: {modo} (pid {processo.pid})")

    def _ler_saida(self, processo) -> None:
        decodificador = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pendente = ""
        while True:
            pedaco = processo.stdout.read1(4096) if hasattr(processo.stdout, "read1") else os.read(processo.stdout.fileno(), 4096)
            if not pedaco:
                break
            pendente += decodificador.decode(pedaco)
            pendente = self._processar(pendente)
        pendente += decodificador.decode(b"", final=True)
        if pendente:
            self._processar(pendente + "\n")
        processo.wait()
        with self.trava:
            self.codigo_saida = processo.returncode
            self.pergunta = None
            self._adicionar({"tipo": "evento", "evento": {"tipo": "encerrado", "codigo": processo.returncode}})
        registrar(f"Encerrado: {self.modo} (código {processo.returncode})")

    def _processar(self, texto: str) -> str:
        """Separa texto normal e eventos. Devolve o que ainda não dá para processar."""
        with self.trava:
            while texto:
                marca = texto.find(MARCA_EVENTO)
                if marca == -1:
                    self._texto(texto)
                    return ""
                if marca > 0:
                    self._texto(texto[:marca])
                    texto = texto[marca:]
                fim = texto.find("\n")
                if fim == -1:
                    return texto  # evento ainda incompleto
                bruto, texto = texto[1:fim], texto[fim + 1:]
                try:
                    evento = json.loads(bruto)
                except json.JSONDecodeError:
                    self._texto(bruto + "\n")
                    continue
                self._evento(evento)
            return ""

    def _texto(self, texto: str) -> None:
        if not texto:
            return
        self._adicionar({"tipo": "texto", "texto": texto.replace("\r\n", "\n")})

    def _evento(self, evento: dict) -> None:
        tipo = evento.get("tipo")
        if tipo == "etapa":
            self.etapa = evento.get("chave")
            self.etapa_info = {chave: evento.get(chave) for chave in ("chave", "titulo", "texto")}
            self.andamento = None
        elif tipo == "ciclo_inicio":
            self.etapa = "SEI1"
            self.resumo = None
        elif tipo == "pergunta":
            self.pergunta = evento.get("pedido") or {}
        elif tipo == "respondido":
            self.pergunta = None
        elif tipo == "andamento":
            self.andamento = {chave: evento.get(chave) for chave in ("texto", "atual", "total")}
        elif tipo == "sessao":
            self.sessao = evento.get("sessao")
        elif tipo == "resumo":
            self.resumo = evento.get("resumo")
        elif tipo == "ciclo_fim":
            self.ultimo_ciclo = evento.get("registro")
            self.etapa = "FIM"
        self._adicionar({"tipo": "evento", "evento": evento})

    def responder(self, resposta, id_pergunta=None) -> None:
        """
        Manda a resposta da pergunta aberta (o botão clicado e o que foi
        preenchido). `id_pergunta` evita que um clique duplo responda, sem
        querer, a pergunta SEGUINTE.
        """
        linha = json.dumps(resposta, ensure_ascii=False)   # uma linha só, sem \x1e solto
        with self.trava:
            if not self.rodando:
                raise RuntimeError("O programa não está rodando.")
            if self.pergunta is None:
                raise RuntimeError("O programa ainda não fez nenhuma pergunta. Espere ele pedir.")
            if id_pergunta is not None and str(id_pergunta) != str(self.pergunta.get("id")):
                raise RuntimeError("Essa pergunta já foi respondida.")
            self.pergunta = None
            processo = self.processo
        processo.stdin.write((linha + "\n").encode("utf-8"))
        processo.stdin.flush()

    def pode_mudar_configuracoes(self) -> bool:
        """Parado, ou esperando a pessoa ajustar as configurações (ou conferir os dados)."""
        with self.trava:
            if not self.rodando:
                return True
            return bool(self.pergunta) and self.pergunta.get("tipo") in ("configuracoes", "conferencia")

    def parar(self) -> None:
        with self.trava:
            if not self.rodando:
                return
            processo = self.processo
            self.parar_pedido_em = time.time()
        try:
            processo.stdin.write((MARCA_EVENTO + "PARAR\n").encode("utf-8"))
            processo.stdin.flush()
        except OSError:
            pass

        def garantir():
            # O main.py costuma parar em segundos. Se travar, encerra à força.
            try:
                processo.wait(timeout=20)
            except subprocess.TimeoutExpired:
                registrar("Não parou em 20 s -- encerrando à força.")
                processo.kill()

        threading.Thread(target=garantir, daemon=True).start()


# ============================================================ configurações e pastas


def tabelas_de_configuracao(execucao: Execucao) -> dict:
    """As tabelas da tela Configurações, com os dados do processo atual (para os exemplos)."""
    sessao = ler_sessao()
    try:
        secoes = configuracoes.formulario(sessao, sessao.get("processo"))
        erro = None
    except Exception as falha:  # arquivo de configuração estranho não derruba a tela
        secoes, erro = [], f"Não foi possível ler as configurações: {falha}"
    return {"secoes": secoes, "erro": erro, "bloqueado": not execucao.pode_mudar_configuracoes()}


def salvar_configuracao(execucao: Execucao, secao: str, valores: dict = None, padrao: bool = False) -> dict:
    """
    Grava (ou volta ao padrão) uma tabela de configuração e devolve a tabela nova.
    Levanta RuntimeError se a automação estiver trabalhando no SIGEF, e configuracoes.ErroNasConfiguracoes
    (com .erros = {campo: mensagem}) se algum valor não servir.
    """
    if not execucao.pode_mudar_configuracoes():
        raise RuntimeError("A automação está trabalhando no SIGEF. Espere ela pedir você para mudar.")
    if padrao:
        configuracoes.restaurar_padrao(secao)
    else:
        configuracoes.salvar_secao(secao, valores or {})
    sessao = ler_sessao()
    return configuracoes.secao(secao, sessao, sessao.get("processo"))


def abrir_no_explorador(caminho: str) -> None:
    os.makedirs(caminho, exist_ok=True)
    if os.name == "nt":
        os.startfile(caminho)  # noqa: S606 -- pasta local do próprio programa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", caminho])


def ler_licenca() -> str:
    try:
        with open(caminhos.ARQUIVO_LICENCA, "r", encoding="utf-8") as arquivo:
            return arquivo.read()
    except OSError:
        return "Arquivo LICENSE não encontrado na pasta do programa."
