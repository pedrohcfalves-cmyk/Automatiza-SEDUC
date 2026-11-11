"""Interface de terminal: menus, entrada de dados e confirmações."""

from . import estatisticas
from .config import COLUNA_RESULTADO, URL_SIGEF
from .fluxos import Relator, Resumo, executar_lotes, executar_planilha
from .modelos import ROTULOS, Lote, Resposta, ler_arquivo_lotes, limpar, lote_de_linha
from .navegador import Navegador
from .planilha import (
    ErroPlanilha,
    Planilha,
    abas_da_pasta,
    abrir_arquivo,
    conectar_excel,
    indice_para_letra,
    letra_para_indice,
    pastas_abertas,
)

TITULO = (
    "========================================\n"
    " CADASTRO DE CREDOR / DOMICÍLIO BANCÁRIO\n"
    "========================================"
)


# ------------------------------------------------------------- primitivas

def escolher(opcoes: list, titulo: str) -> int:
    """Menu numérico; devolve o índice da opção escolhida."""
    print(f"\n{titulo}")

    for numero, texto in enumerate(opcoes, 1):
        print(f"   {numero} - {texto}")

    while True:
        escolha = input("Opção > ").strip()

        if escolha.isdigit() and 1 <= int(escolha) <= len(opcoes):
            return int(escolha) - 1


def inteiro(pergunta: str, padrao: int) -> int:
    resposta = input(f"{pergunta} [{padrao}]: ").strip()
    return int(resposta) if resposta.isdigit() else padrao


def sim(pergunta: str, padrao: bool = True) -> bool:
    opcoes = "[S/n]" if padrao else "[s/N]"
    resposta = input(f"{pergunta} {opcoes} ").strip().lower()
    return padrao if not resposta else resposta in ("s", "sim")


def pedir(campo: str, atual: str = "") -> str:
    """Lê um campo do teclado, validando e normalizando o valor."""
    rotulo = ROTULOS[campo]
    sufixo = f" [{atual}]" if atual else ""

    while True:
        bruto = input(f"   {rotulo}{sufixo}: ").strip()
        valor = limpar(campo, bruto) if bruto else atual

        if not valor:
            if campo == "banco" and bruto:
                print(f"      Banco não reconhecido: {bruto}. Informe o código (ex. 001).")
            else:
                print(f"      {rotulo} não pode ficar vazio.")
            continue

        if campo == "cpf" and len(valor) != 11:
            print("      CPF deve ter 11 dígitos.")
            continue

        return valor


# --------------------------------------------------------------- navegador

def preparar_navegador(navegador: Navegador) -> None:
    """Abre o navegador, leva ao SIGEF e só retorna com a sessão confirmada."""
    print("Abrindo o navegador em modo de depuração...")
    navegador.abrir()

    print(
        "\n========================================\n"
        " LOGIN NO SIGEF\n"
        "========================================\n"
        f" O navegador foi aberto em {URL_SIGEF}\n"
        " Entre na sua conta e volte aqui."
    )

    while True:
        input("\n>> Pressione ENTER depois de concluir o login... ")

        try:
            navegador.abrir()

            if navegador.logado():
                print("Sessão confirmada.")
                return

        except Exception as erro:
            print(f"   Não foi possível abrir a tela de credores: {str(erro).splitlines()[0]}")
            continue

        print("   A tela de credores não abriu — login incompleto ou sem permissão.")


# ----------------------------------------------------------------- menus

def menu_principal() -> int:
    return escolher(
        [
            "Modo lote (digitar / colar / arquivo)",
            "Modo planilha (Excel via win32)",
            "Sair",
        ],
        TITULO,
    )


def escolher_modo_manual() -> bool:
    return escolher(
        [
            "Automática (não interrompe o fluxo)",
            "Manual (pergunta antes de incluir credor e de confirmar o domicílio)",
        ],
        "CONFIRMAÇÃO DAS AÇÕES",
    ) == 1


def perguntar(lote: Lote, acao: str, editavel: bool) -> Resposta:
    """Conferência manual antes de um clique que grava no SIGEF."""
    opcao_n = "   [N] não, corrigir e reiniciar este lote\n" if editavel else ""

    while True:
        print(f"\n>> {acao}\n   {lote}")

        resposta = input(
            "   Os dados estão corretos?\n"
            "   [S] sim, continuar   [T] sim, e não perguntar mais neste lote\n"
            f"{opcao_n}"
            "   [P] pular este lote\n"
            "   > "
        ).strip().lower()

        if resposta in ("", "s"):
            return Resposta.SIM

        if resposta == "t":
            return Resposta.SIM_TODOS

        if resposta == "n" and editavel:
            return Resposta.CORRIGIR

        if resposta == "p":
            return Resposta.PULAR


# ------------------------------------------------------- entrada de lotes

def _lotes_colados() -> list:
    print(
        "\nCole/digite um lote por linha, na ordem:\n"
        "   CPF,Nome,Código do Banco,Agência,Conta\n"
        "(separador , ou ; ou TAB — linha vazia encerra)\n"
    )

    lotes = []

    while True:
        linha = input(f"{len(lotes) + 1}> ").strip()

        if not linha:
            return lotes

        try:
            lotes.append(lote_de_linha(linha))
        except ValueError as erro:
            print(f"   Linha ignorada ({erro}).")


def _lotes_digitados() -> list:
    lotes = []

    while True:
        print(f"\n--- Lote {len(lotes) + 1} ---")
        lotes.append(Lote(**{campo: pedir(campo) for campo in ROTULOS}))

        if not sim("Incluir outro lote?", padrao=False):
            return lotes


def _lotes_de_arquivo() -> list:
    caminho = input("Caminho do arquivo (.csv/.txt): ").strip().strip('"')

    try:
        lotes, ignoradas = ler_arquivo_lotes(caminho)
    except OSError as erro:
        print(f"   Não foi possível ler o arquivo: {erro}")
        return []

    for numero, motivo in ignoradas:
        print(f"   Linha {numero} ignorada ({motivo}).")

    return lotes


def coletar_lotes() -> list:
    """Menu de entrada dos lotes, com conferência da lista antes de executar."""
    entradas = (_lotes_colados, _lotes_digitados, _lotes_de_arquivo)

    while True:
        escolha = escolher(
            [
                "Colar lotes em linhas",
                "Digitar campo por campo",
                "Carregar de arquivo (.csv/.txt)",
                "Voltar",
            ],
            "ENTRADA DOS LOTES",
        )

        if escolha == len(entradas):
            return []

        lotes = entradas[escolha]()

        if not lotes:
            print("Nenhum lote válido informado.")
            continue

        print(f"\n{len(lotes)} lote(s) carregado(s):")

        for numero, lote in enumerate(lotes, 1):
            print(f"   {numero}. {lote}")

        if sim("\nConfirmar esta lista?"):
            return lotes


# ------------------------------------------------------- entrada planilha

def abrir_planilha():
    """Escolhe pasta de trabalho e aba; devolve Planilha ou None."""
    try:
        excel = conectar_excel()
    except ErroPlanilha as erro:
        print(f"\n{erro}")
        return None

    abertas = pastas_abertas(excel)
    escolha = escolher(abertas + ["Abrir outro arquivo...", "Voltar"],
                       "PLANILHAS ABERTAS NO EXCEL")

    if escolha == len(abertas) + 1:
        return None

    try:
        if escolha == len(abertas):
            pasta, ja_aberta = abrir_arquivo(excel, input("Caminho completo do arquivo: "))

            if ja_aberta:
                print("   (a pasta já estava aberta no Excel)")
        else:
            pasta = excel.Workbooks(escolha + 1)

        abas = abas_da_pasta(pasta)
        planilha = Planilha.da_pasta(pasta, abas[escolher(abas, f"ABAS DE {pasta.Name}")])

    except Exception as erro:
        print(f"   Não foi possível abrir a planilha: {erro}")
        return None

    print(f"\nArquivo: {planilha.caminho}")
    print(f"Aba:     {planilha.nome_aba}")

    if planilha.somente_leitura:
        print("ATENÇÃO: a pasta está aberta somente para leitura — nada será gravado.")

    return planilha


def confirmar_colunas(planilha: Planilha) -> tuple:
    """Mostra o mapa das colunas (detectado ou padrão) e permite ajustar."""
    colunas, primeira, detectou = planilha.colunas_sugeridas()

    if detectou:
        print(f"\nCabeçalho encontrado. Colunas detectadas (dados a partir da linha {primeira}):")
    else:
        print("\nCabeçalho não encontrado. Usando as colunas padrão:")

    while True:
        for campo, letra, titulo, exemplo in planilha.amostra(colunas, primeira):
            print(f"   {ROTULOS[campo]:<16} -> {letra:>2}  ({titulo or 'sem título'})  ex.: {exemplo}")

        if sim("\nAs colunas estão corretas?"):
            return colunas, primeira

        print("\nInforme a letra de cada coluna:")

        for campo in colunas:
            letra = input(f"   {ROTULOS[campo]} [{indice_para_letra(colunas[campo])}]: ").strip()

            if letra:
                colunas[campo] = letra_para_indice(letra)


def escolher_coluna_resultado() -> str:
    """Coluna do diagnóstico; o conteúdo anterior da linha é sempre sobrescrito."""
    while True:
        letra = (input(f"\nColuna do diagnóstico [{COLUNA_RESULTADO}]: ").strip()
                 or COLUNA_RESULTADO).upper()

        if letra_para_indice(letra):
            return letra


# ---------------------------------------------------------------- execução

class RelatorTerminal(Relator):
    def __init__(self, rotulo: str):
        self.rotulo = rotulo

    def inicio(self, chave, lote, atual, total):
        sufixo = f"/{total}" if self.rotulo == "LOTE" else ""
        print(f"\n================ {self.rotulo} {chave}{sufixo} ================")
        print(f"   {lote}")

    def resultado(self, chave, lote, status, texto):
        print(f"   {texto}")

    def aviso(self, texto):
        print(f"   {texto}")

    def corrigir(self, lote):
        print("\n   Corrija os dados (Enter mantém o valor atual):")

        for campo in ROTULOS:
            setattr(lote, campo, pedir(campo, getattr(lote, campo)))

        return True


def mostrar_resumo(resumo: Resumo) -> None:
    contagem = resumo.contagem
    print("\n================ RESUMO ================")
    print(f"   Sucesso:        {contagem['OK']}")
    print(f"   Já cadastrados: {contagem['JA']}")
    print(f"   Pulados:        {contagem['PULADO']}")
    print(f"   Erros:          {contagem['ERRO']}")


def _nova_sessao(modo: str, manual: bool) -> estatisticas.Sessao:
    return estatisticas.Sessao(modo, "manual" if manual else "auto", interface="terminal")


def _guardar(sessao: estatisticas.Sessao) -> None:
    """Grava a sessão para as estatísticas e mostra o tempo economizado."""
    estatisticas.salvar_sessao(sessao)
    feitos, automacao, economia = estatisticas.resumo_da_sessao(sessao)

    if feitos:
        print(f"   Tempo da automação: {estatisticas.formatar_duracao(automacao)}"
              f"   |   Economia estimada: {estatisticas.formatar_duracao(economia)}")


def _rodar(modo: str, manual: bool, executar) -> None:
    """Executa com estatística e, ao final, oferece refazer só os itens com erro.

    `executar(sessao, falhas)` recebe None na primeira vez e, nas seguintes, as
    falhas [(chave, Lote)] da execução anterior, que ficam só na memória.
    """
    falhas = None

    while True:
        sessao = _nova_sessao(modo, manual)

        try:
            resumo = executar(sessao, falhas)
            mostrar_resumo(resumo)
        finally:
            _guardar(sessao)

        falhas = resumo.falhas

        if not falhas or not sim(f"\n{len(falhas)} com erro. Refazer só esses agora?", False):
            return


def modo_lotes(navegador: Navegador) -> None:
    lotes = coletar_lotes()

    if not lotes:
        return

    manual = escolher_modo_manual()
    relator, conferir = RelatorTerminal("LOTE"), perguntar if manual else None

    def executar(sessao, falhas):
        if falhas is None:
            return executar_lotes(navegador, lotes, relator, conferir, sessao)

        numeros, refazer = zip(*falhas)
        return executar_lotes(navegador, refazer, relator, conferir, sessao, numeros)

    _rodar("lotes", manual, executar)


def modo_planilha(navegador: Navegador) -> None:
    planilha = abrir_planilha()

    if planilha is None:
        return

    colunas, sugestao = confirmar_colunas(planilha)
    primeira = inteiro("\nLinha inicial", sugestao)
    final = inteiro("Linha final", max(planilha.ultima_linha(colunas), primeira))
    resultado = escolher_coluna_resultado()
    manual = escolher_modo_manual()
    relator, conferir = RelatorTerminal("LINHA"), perguntar if manual else None

    def executar(sessao, falhas):
        linhas = range(primeira, final + 1) if falhas is None else [l for l, _ in falhas]
        return executar_planilha(navegador, planilha, colunas, linhas, resultado, relator,
                                 conferir, sessao)

    _rodar("planilha", manual, executar)
