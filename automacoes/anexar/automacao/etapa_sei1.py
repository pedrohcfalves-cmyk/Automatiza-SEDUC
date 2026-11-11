"""
Etapa SEI (1): abre o processo no SEI (pesquisa o número e expande a
árvore de pastas) e mostra a TABELA com todos os dados do processo de uma
vez (dados_processo.py) -- CNPJ/CPF, contas, escola, parcela, mês,
programa, Valor Total e os lançamentos --, seguida do quadro "Confira os
dados". Esses dados são usados por todas as etapas seguintes (CE, NL, PP,
OB, SEI(2)).
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from automacoes.anexar.automacao import dados_processo, interacao
from automacoes.anexar.automacao.utils import (
    URL_SEI,
    carregar_sessao,
    obter_ou_criar_aba,
    salvar_sessao,
)


def abrir_processo_sei(aba_sei: Page, processo: str, timeout_ms: int = 15000) -> None:
    """
    Abre o processo informado no SEI: pesquisa o processo pelo número na
    aba já focada e expande todas as pastas da árvore de documentos.

    Lança RuntimeError com uma mensagem clara caso algum passo falhe
    (elemento não respondeu a tempo, processo não localizado etc.), em
    vez de deixar o script travar silenciosamente em um timeout do
    Playwright.
    """
    try:
        aba_sei.locator('img.infraImg[title="Controle de Processos"]:visible').click(
            timeout=timeout_ms
        )
        aba_sei.locator("#txtPesquisaRapida").fill(processo, timeout=timeout_ms)
        aba_sei.locator('img.infraImg[title="Pesquisa Rápida"]:visible').click(
            timeout=timeout_ms
        )
    except PlaywrightTimeoutError as erro:
        raise RuntimeError(
            f"Não consegui pesquisar o processo '{processo}' no SEI. "
            "Confira se você está DENTRO do SEI (com usuário e senha) e se a "
            "página do SEI abriu normalmente; depois rode o programa de novo."
        ) from erro

    try:
        aba_sei.frame_locator("#ifrArvore").locator(
            'img[title="Abrir todas as Pastas"]:visible'
        ).click(timeout=timeout_ms)
    except PlaywrightTimeoutError as erro:
        raise RuntimeError(
            f"Não achei o processo '{processo}' no SEI. Confira se o número "
            "está certo (olhe no SEI) e rode o programa de novo."
        ) from erro


MAX_LANCAMENTOS = dados_processo.MAX_LANCAMENTOS


def coletar_dados_sigef(processo: str = None) -> dict:
    """
    Mostra a tabela com TODOS os dados do processo de uma vez (já
    preenchida com o que foi usado da última vez) e o quadro "Confira os
    dados" -- ver dados_processo.coletar(). Só volta quando a pessoa clica
    em Começar; os dados confirmados ficam salvos na sessão para as
    próximas etapas (e para a próxima vez).
    """
    dados = dados_processo.coletar(processo, carregar_sessao())
    salvar_sessao(**dados)
    return dados


def pedir_processo(sessao: dict = None) -> str:
    """O número do processo do SEI (um campo só, já com o da última vez)."""
    sessao = carregar_sessao() if sessao is None else sessao
    return interacao.pedir_texto(
        "Qual é o processo?",
        "Número do processo no SEI",
        atual=sessao.get("processo") or "",
        exemplo="0029.002180/2026-93",
        ajuda="Copie o número como aparece no SEI. O programa abre o processo para você conferir os dados.",
        rotulo_botao="Abrir o processo no SEI",
    )


def executar_sei1(context, processo: str = None) -> tuple[Page, str, dict]:
    """
    Etapa SEI (1) completa: põe a aba do SEI na frente, pede o número do
    processo (se não informado), abre o processo e mostra a tabela dos
    dados (coletar_dados_sigef).

    Retorna a aba do SEI, o número do processo e os dados confirmados.
    """
    aba_sei = obter_ou_criar_aba(
        context,
        dominio="sei.sistemas.ro.gov.br",
        url_navegacao=URL_SEI,
    )
    aba_sei.bring_to_front()

    if processo is None:
        processo = pedir_processo()

    interacao.andamento(f"Abrindo o processo {processo} no SEI")
    abrir_processo_sei(aba_sei, processo)
    salvar_sessao(processo=processo)

    dados = coletar_dados_sigef(processo)

    return aba_sei, processo, dados


if __name__ == "__main__":
    # Teste isolado da Etapa SEI (1): conecta no Chrome já aberto e só
    # executa essa etapa, sem depender do restante do fluxo.
    from automacoes.anexar.automacao.utils import conectar_chrome

    playwright, browser, context = conectar_chrome()
    try:
        interacao.continuar("Teste da Etapa SEI (1)", ["Entre no SEI no Chrome do programa antes de continuar."])
        aba_sei, processo, dados = executar_sei1(context)
        print(f"OK: processo '{processo}' aberto e pastas expandidas no SEI.")
        print("Dados coletados:", dados)
    finally:
        playwright.stop()
