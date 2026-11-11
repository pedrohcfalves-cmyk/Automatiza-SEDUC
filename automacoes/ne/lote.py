"""
Lote de NEs: vários pares processo + NE de uma vez, sem perguntar nada
entre um e outro. Mesmo desenho do lote das OBs (automacoes/sigef_sei/lote.py).

    itens = ler_arquivo_ne("lista.xlsx")       # ou ler_texto_ne(texto_colado)
    resultados, relatorio = processar_lote_ne(context, aba_sigef, itens)

DE ONDE VÊM OS PARES

Planilha (.xlsx), .csv ou uma lista colada (do Excel, de um e-mail, de um
bloco de notas). Uma linha por NE. Em cada linha o programa procura:

    processo  o que tiver 16 dígitos (0029.001947/2026-67, 0029001947202667)
    NE        2026NE000123, ou só o número com 5 ou 6 dígitos (000123) --
              ou qualquer número, se a coluna tiver o cabeçalho "NE"

A ordem das colunas não importa e o cabeçalho é ignorado sozinho. Número
curto (1, 2, 3...) nunca é tomado por NE -- é coluna de numeração; por
isso uma NE sem o prefixo "2026NE" precisa dos zeros (000123, não 123). A
NE de outro exercício que não o da tela do SIGEF vira erro na conferência
da lista, antes de começar -- nada é processado com dado duvidoso.

COMO RODA

Um processo por vez, na ordem da lista, no mesmo Chrome e com o mesmo
login. Uma falha não para o lote: espera a internet e tenta de novo,
continuando de onde parou (a retomada do SEI); falhando de novo, marca
erro e segue. NE já anexada inteira numa rodada anterior NÃO é pulada:
é anexada de novo, com aviso para conferir o que ficar em dobro.

Cada lote grava um .csv em <pasta de dados>/lotes/, atualizado a cada NE.
"""
import csv
import io
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from automacoes.sigef_sei.etapa_listar_baixar import PASTA_BASE, normalizar_processo_sei, salvar_sessao
from automacoes.sigef_sei.lote import (
    ESPERA_ANTES_DE_REPETIR,
    TENTATIVAS_POR_PROCESSO,
    Interromper,
    _celula_texto,
    _mensagem,
    _separar_linha,
)
from automacoes.sigef_sei.metricas import formatar_duracao

from .etapa import ANO_SIGEF, anexar_ne, baixar_ne, ne_ja_concluida, normalizar_ne
from .metricas import CronometroNE

PASTA_RELATORIOS = os.path.join(PASTA_BASE, "lotes")

AVISO_JA_ANEXADA = (
    "Esta NE já tinha sido anexada neste processo numa rodada anterior e foi anexada de novo -- "
    "confira se não ficaram documentos em dobro e exclua os repetidos."
)

# "2026NE000123" ou um número de 5 a 8 dígitos.
REGEX_CANDIDATA_NE = re.compile(r"^(?:\d{4}NE\d{1,6}|\d{5,6})$", re.IGNORECASE)

# Cabeçalho da coluna da NE ("NE", "Nº NE", "Nota de Empenho", "Empenho"). Com ele, a
# coluna vale mesmo com número curto -- o Excel tira os zeros (000123 vira 123).
REGEX_CABECALHO_NE = re.compile(r"^(?:n[º°o]?\.?\s*(?:da\s+)?)?(?:ne|nota\s+de\s+empenho|empenho)$", re.IGNORECASE)


# ================================================================ Leitura


@dataclass
class ItemNE:
    linha: int                  # linha na planilha/lista, para o usuário achar
    processo: str = ""
    ne: str = ""                # sequencial com 6 dígitos
    erro: str = ""              # motivo de não dar para processar
    ja_concluida: bool = False  # anexada inteira numa rodada anterior (só avisa)
    original: str = ""          # a linha como veio, para mostrar no erro

    @property
    def valido(self) -> bool:
        return not self.erro


def coluna_ne_do_cabecalho(celulas: list) -> int | None:
    """Índice da coluna da NE, se a linha for um cabeçalho com ela."""
    for indice, celula in enumerate(celulas):
        if REGEX_CABECALHO_NE.match(_celula_texto(celula)):
            return indice
    return None


def interpretar_celulas_ne(celulas: list, numero_linha: int, coluna_ne: int | None = None) -> ItemNE | None:
    """
    Uma linha da planilha/lista vira um ItemNE. None se não tem número nenhum (vazia ou cabeçalho).
    `coluna_ne`: a coluna marcada "NE" no cabeçalho -- nela, qualquer número de 1 a 6 dígitos é a NE.
    """
    textos = [t for t in (_celula_texto(c) for c in celulas) if t]
    if not any(re.search(r"\d", t) for t in textos):
        return None

    item = ItemNE(linha=numero_linha, original="  |  ".join(textos))
    texto_coluna = _celula_texto(celulas[coluna_ne]) if coluna_ne is not None and coluna_ne < len(celulas) else ""
    restantes = []
    for texto in textos:
        if not item.processo and normalizar_processo_sei(texto):
            item.processo = normalizar_processo_sei(texto)
        else:
            restantes.append(texto)

    if texto_coluna:
        compacto = re.sub(r"\s+", "", texto_coluna)
        item.ne = normalizar_ne(compacto) or ""
        if not item.ne and re.match(r"^\d{4}NE\d", compacto, re.IGNORECASE):
            item.erro = f"a NE '{compacto}' é de outro exercício (a tela do SIGEF é de {ANO_SIGEF})"
        elif not item.ne:
            item.erro = f"a NE '{compacto}' não é válida (ex.: 2026NE000123 ou 123)"
        restantes = []

    for texto in restantes:
        compacto = re.sub(r"\s+", "", texto)
        if REGEX_CANDIDATA_NE.match(compacto):
            item.ne = normalizar_ne(compacto) or ""
            if not item.ne:
                item.erro = f"a NE '{compacto}' é de outro exercício (a tela do SIGEF é de {ANO_SIGEF})"
            break

    if not item.erro:
        if not item.processo:
            item.erro = "não achei o número do processo (16 dígitos, ex.: 0029.001947/2026-67)"
        elif not item.ne:
            item.erro = "não achei o número da NE (ex.: 2026NE000123 ou 000123)"
    return item


def _conferir_ne(itens: list[ItemNE]) -> list[ItemNE]:
    """Marca repetidos e o que já foi concluído numa rodada anterior."""
    vistos = {}
    for item in itens:
        if not item.valido:
            continue
        chave = (item.processo, item.ne)
        if chave in vistos:
            item.erro = f"repetido -- igual à linha {vistos[chave]}"
            continue
        vistos[chave] = item.linha
        item.ja_concluida = ne_ja_concluida(item.processo, item.ne)
    return itens


def _montar(linhas) -> list[ItemNE]:
    itens = []
    coluna_ne = None
    for numero, celulas in enumerate(linhas, start=1):
        celulas = list(celulas)
        if coluna_ne is None and not itens:   # cabeçalho só vale antes da primeira linha com dados
            coluna_ne = coluna_ne_do_cabecalho(celulas)
            if coluna_ne is not None:
                continue
        item = interpretar_celulas_ne(celulas, numero, coluna_ne)
        if item is not None:
            itens.append(item)
    return _conferir_ne(itens)


def ler_texto_ne(texto: str) -> list[ItemNE]:
    """Lista colada: uma NE por linha."""
    return _montar(_separar_linha(linha) for linha in (texto or "").splitlines())


def ler_arquivo_ne(caminho: str) -> list[ItemNE]:
    """Planilha .xlsx (primeira aba) ou texto .csv/.txt."""
    extensao = os.path.splitext(caminho)[1].lower()

    if extensao in (".xlsx", ".xlsm"):
        import openpyxl

        livro = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        try:
            return _montar(livro.worksheets[0].iter_rows(values_only=True))
        finally:
            livro.close()

    if extensao == ".xls":
        raise ValueError("Planilha no formato antigo (.xls). Abra no Excel e salve como .xlsx.")

    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read()
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252", errors="replace")
    if extensao == ".csv":
        # O Excel brasileiro grava com ";".
        separador = next((s for s in (";", "\t") if s in texto), ",")
        return _montar(csv.reader(io.StringIO(texto), delimiter=separador))
    return ler_texto_ne(texto)


# ============================================================== Execução


@dataclass
class ResultadoNE:
    item: ItemNE
    estado: str = "pendente"        # ok | erro
    mensagem: str = ""
    avisos: list = field(default_factory=list)
    pasta: str = ""
    tempo: dict = field(default_factory=dict)   # segundos: sigef, sei, total


class RelatorioNE:
    """O .csv do lote, reescrito a cada NE."""

    def __init__(self):
        os.makedirs(PASTA_RELATORIOS, exist_ok=True)
        self.caminho = os.path.join(PASTA_RELATORIOS, f"lote_ne_{datetime.now():%Y-%m-%d_%H%M%S}.csv")

    def gravar(self, resultados: list[ResultadoNE]) -> None:
        with open(self.caminho, "w", encoding="utf-8-sig", newline="") as arquivo:
            saida = csv.writer(arquivo, delimiter=";")
            saida.writerow([
                "Linha", "Processo", "NE", "Situação", "Mensagem", "Avisos", "Pasta",
                "Tempo SIGEF", "Tempo SEI", "Tempo total",
            ])
            for r in resultados:
                saida.writerow([
                    r.item.linha, r.item.processo, r.item.ne,
                    {"ok": "Concluído", "erro": "Erro"}.get(r.estado, "Não processado"),
                    r.mensagem.replace("\n", " ").strip(), " | ".join(r.avisos), r.pasta,
                    formatar_duracao(r.tempo.get("sigef")), formatar_duracao(r.tempo.get("sei")),
                    formatar_duracao(r.tempo.get("total")),
                ])
            feitos = [r for r in resultados if r.tempo.get("total")]
            if feitos:
                total = sum(r.tempo["total"] for r in feitos)
                saida.writerow([])
                saida.writerow(["", "Tempo do lote", formatar_duracao(total)])
                saida.writerow(["", "Média por NE", formatar_duracao(total / len(feitos))])


def processar_lote_ne(
    context, aba_sigef, itens: list[ItemNE], deve_parar=None, ao_etapa=None
) -> tuple[list[ResultadoNE], str]:
    """
    Processa os itens válidos, um por vez. Devolve (resultados, caminho do
    relatório). `deve_parar()`, se informado, é consultado entre um item e
    outro: devolvendo True, o lote para ali (o item em andamento termina).
    `ao_etapa(indice, etapa, resultados)` avisa a tela: "sigef", "sei", "fim".
    """
    ao_etapa = ao_etapa or (lambda indice, etapa, resultados: None)
    resultados = [ResultadoNE(item) for item in itens if item.valido]
    relatorio = RelatorioNE()
    relatorio.gravar(resultados)

    for indice, resultado in enumerate(resultados):
        item = resultado.item
        if deve_parar and deve_parar():
            print("\n⏹️  Lote interrompido a pedido -- as que faltam ficam para depois.")
            break

        print(f"\n{'=' * 60}\n📋 LOTE {indice + 1}/{len(resultados)}: processo {item.processo} | NE {item.ne}\n{'=' * 60}")
        if item.ja_concluida:
            print(f"⚠️  NE {item.ne} já foi anexada neste processo antes -- anexando de novo (confira duplicidade).")

        # Um relógio por NE: as tentativas repetidas somam nele (a espera
        # entre elas não conta -- só o tempo trabalhando).
        cron = CronometroNE("lote", item.processo, item.ne)
        dados = None
        for tentativa in range(1, TENTATIVAS_POR_PROCESSO + 1):
            try:
                salvar_sessao(processo=item.processo, ne=item.ne)
                cron.etapa("sigef")
                ao_etapa(indice, "sigef", resultados)
                dados, aba_sigef = baixar_ne(context, aba_sigef, item.processo, item.ne)
                resultado.pasta = dados.get("pasta_processo") or ""
                cron.etapa("sei")
                ao_etapa(indice, "sei", resultados)
                avisos = anexar_ne(context, item.processo, dados)
                if item.ja_concluida:
                    avisos.insert(0, AVISO_JA_ANEXADA)
                resultado.estado, resultado.mensagem, resultado.avisos = "ok", "", avisos
                break
            except Interromper:
                cron.registrar("parado", dados=dados, mensagem="Lote interrompido")
                raise
            except BaseException as erro:  # SystemExit é o jeito das etapas pararem
                if getattr(erro, "interromper_lote", False) or isinstance(erro, KeyboardInterrupt):
                    cron.registrar("parado", dados=dados, mensagem=_mensagem(erro))
                    raise
                cron.parar()   # a espera antes de repetir não conta
                resultado.mensagem = _mensagem(erro)
                if tentativa < TENTATIVAS_POR_PROCESSO:
                    print(
                        f"\n⚠️  O processo {item.processo} parou. Esperando {ESPERA_ANTES_DE_REPETIR}s "
                        "e tentando de novo, de onde parou..."
                    )
                    time.sleep(ESPERA_ANTES_DE_REPETIR)
                else:
                    resultado.estado = "erro"
                    print(f"\n❌ A NE {item.ne} do processo {item.processo} ficou com erro -- seguindo para a próxima.")

        resultado.tempo = cron.registrar(resultado.estado, dados=dados, mensagem=resultado.mensagem)
        relatorio.gravar(resultados)
        ao_etapa(indice, "fim", resultados)

    return resultados, relatorio.caminho
