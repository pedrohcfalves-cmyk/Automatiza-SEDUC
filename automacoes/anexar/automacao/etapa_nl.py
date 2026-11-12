"""
Etapa NL: Liquidar Despesa Certificada no SIGEF.

A CE é gerada uma única vez (com o Valor Total) e pode ser liquidada em
várias NLs -- uma por lançamento (Valor + Nota de Empenho). Por isso
executar_nl_lote() pesquisa a CE uma única vez e repete só o ciclo de
inclusão (data de vencimento, nota de empenho, valor bruto, retenções,
confirmar) para cada lançamento, sem recarregar a página entre eles --
recarregar seria lento e desnecessário, já que é sempre a mesma CE.

executar_nl_lote() recebe `ce` e a lista de lançamentos direto, pra dar
pra testar essa etapa sozinha sem rodar SEI(1)/CE de novo -- o bloco
"__main__" abaixo carrega os últimos valores salvos na sessão como
padrão e testa com um lançamento só.
"""
import time
from datetime import date

from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.configuracoes import config_global
from automacoes.anexar.automacao.valores import digitar_valor_conferido
from automacoes.anexar.automacao.utils import URL_SIGEF_NL, normalizar, obter_ou_criar_aba, salvar_sessao


# Quanto esperar a NL nova aparecer na grade depois do "Confirmar".
TIMEOUT_NL_NOVA_S = 15

_JS_GRADE_NL = """
() => [...document.querySelectorAll("tr.GridLinhaPar, tr.GridLinhaImpar")]
    .map((linha) => {
        // Só os <td> filhos diretos: a coluna "Unidade Gestora" tem uma
        // tabela aninhada com <td> próprios, que desalinharia as colunas.
        const td = [...linha.children].filter((c) => c.tagName === "TD").map((c) => c.innerText.trim());
        return {nl: td[5] || "", valor: td[7] || ""};
    })
    .filter((linha) => /NL\\s*\\d+/i.test(linha.nl))
"""


def _ler_grade_nl(aba_sigef) -> list[dict]:
    """As NLs que estão na grade agora: [{"nl": "2026NL066210", "valor": "857,50"}, ...]."""
    try:
        return aba_sigef.evaluate(_JS_GRADE_NL)
    except Exception:
        return []


def _so_numero_nl(nl_bruto: str) -> str:
    """'2026NL066210' -> '066210' (é assim que o resto do fluxo guarda a NL)."""
    nl_bruto = (nl_bruto or "").strip()
    return nl_bruto.split("NL")[-1].strip() if "NL" in nl_bruto.upper() else nl_bruto


def _identificar_nl_nova(antes: list[dict], depois: list[dict], valor_padronizado: str) -> str | None:
    """
    A NL que ESTE "Confirmar" acabou de criar: a que está na grade agora e
    não estava antes. Não procura "a primeira com aquele valor" -- num lote
    com dois lançamentos de MESMO valor, isso devolvia a NL do anterior.

    Entre as novas, prefere a de valor líquido igual ao do lançamento; se a
    única nova tiver outro valor, devolve ela assim mesmo (ela FOI criada --
    devolver None faria a próxima execução gerar outra) e avisa.
    """
    ja_existiam = {_so_numero_nl(linha["nl"]) for linha in antes}
    novas = [linha for linha in depois if _so_numero_nl(linha["nl"]) not in ja_existiam]
    if not novas:
        return None

    esperado = normalizar(valor_padronizado)
    mesmas = []
    for linha in novas:
        try:
            if abs(normalizar(linha["valor"]) - esperado) < 0.001:
                mesmas.append(linha)
        except ValueError:
            continue
    escolhida = (mesmas or novas)[-1]
    if not mesmas:
        print(
            f"⚠️  A NL nova {escolhida['nl']} tem valor líquido {escolhida['valor']}, diferente do "
            f"lançamento ({valor_padronizado}) -- confira no SIGEF."
        )
    if len(novas) > 1:
        print(f"⚠️  Apareceram {len(novas)} NLs novas de uma vez na grade -- usando {escolhida['nl']}; confira.")
    return _so_numero_nl(escolhida["nl"])


def _incluir_nl(aba_sigef, context, valor_padronizado: str, nota_empenho: str) -> str | None:
    """
    Repete o ciclo de inclusão de uma NL (data de vencimento, nota de
    empenho, valor bruto, retenções, confirmar) numa CE já pesquisada na
    página e descobre o número da NL que ESTA inclusão criou: compara a
    grade antes e depois do "Confirmar" (ver _identificar_nl_nova) e
    espera a linha nova aparecer.

    Retorna o número da NL (só o número, sem o prefixo "2026NL"), ou
    None se nenhuma NL nova aparecer na grade.
    """
    data_atual = date.today().strftime("%d%m%Y")

    # O que já está na grade ANTES desta inclusão (NLs de lançamentos
    # anteriores do lote, ou já existentes nesta CE).
    antes = _ler_grade_nl(aba_sigef)

    aba_sigef.locator("#txtDataVencimento_SIGEFData").fill(data_atual)
    aba_sigef.locator("#btnAdicionar").click()

    with context.expect_page() as nova_pagina_info:
        aba_sigef.locator("#txtNotaEmpenhoNumeroId_BtnPesquisa").click()

    nova_pagina = nova_pagina_info.value
    nova_pagina.wait_for_load_state("networkidle")

    nova_pagina.locator("#txtNotaEmpenhoNumero").fill(nota_empenho)
    nova_pagina.locator("#btnConfirmar").click()
    nova_pagina.locator("td.GridLink[onclick*='SelecionarItem']").first.click()

    # Fecha a aba de busca da nota de empenho -- ela já cumpriu seu papel
    # (selecionar o item) e, se não for fechada, fica acumulando abas no
    # Chrome a cada execução.
    try:
        nova_pagina.close()
    except Exception:
        pass

    aba_sigef.bring_to_front()

    # A página troca/recarrega os campos depois de vincular a nota de
    # empenho, e às vezes esse recarregamento demora mais que os 2s de
    # espera e apaga o valor digitado. Por isso, além de esperar,
    # confere se o valor realmente ficou no campo -- se a página tiver
    # apagado, digita de novo (até 3 tentativas).
    # (limpar antes e comparar o valor numérico: ver digitar_valor_conferido).
    # Não conferiu em 3 tentativas = para aqui, ANTES de confirmar a NL.
    digitar_valor_conferido(aba_sigef, aba_sigef.locator("#txtValorBrutoId"), valor_padronizado, antes_ms=2000)

    aba_sigef.locator("#btnRetencoesId").click()
    aba_sigef.locator("#menun4").click()

    aba_sigef.locator("#btnConfirmar").click()

    # O "Confirmar" é um postback: espera a NL NOVA aparecer na grade
    # (ler na mesma hora podia não achar nada, ou achar só as antigas).
    prazo = time.monotonic() + TIMEOUT_NL_NOVA_S
    while True:
        try:
            aba_sigef.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        nl = _identificar_nl_nova(antes, _ler_grade_nl(aba_sigef), valor_padronizado)
        if nl or time.monotonic() >= prazo:
            return nl
        aba_sigef.wait_for_timeout(300)


def executar_nl_lote(context, ce: str, lancamentos: list[dict], dados: dict = None) -> list[dict]:
    """
    Gera a NL de cada lançamento da lista, todos vinculados à mesma CE
    `ce` (pesquisada uma única vez).

    Retorna a MESMA lista `lancamentos`, com a chave "nl" adicionada em
    cada item (o número gerado, ou None se não foi possível gerar
    aquela NL).
    """
    aba_sigef = obter_ou_criar_aba(
        context,
        dominio="sigef.sefin.ro.gov.br",
        url_navegacao=URL_SIGEF_NL,
    )
    aba_sigef.goto(URL_SIGEF_NL)
    aba_sigef.wait_for_load_state("networkidle")

    # Unidade Gestora e Gestão: as do Global ([G] no menu de configurações).
    global_ = config_global()
    aba_sigef.locator("#txtCdUnidadeGestora").fill(global_["unidade_gestora"])
    aba_sigef.locator("#txtCdGestao_SIGEFPesquisa").fill(global_["gestao"])
    aba_sigef.locator("#txtDespesaCertificadaNumero_SIGEFPesquisa").fill(ce)
    aba_sigef.locator("#btnPesquisar").click()

    gerou_alguma_nova = False
    for numero, item in enumerate(lancamentos, start=1):
        if item.get("nl"):
            # Já tem NL de uma execução anterior (mesma CE) -- pula pra
            # não gerar duplicado.
            print(f"⏭️  O valor {item['valor']} já tem NL ({item['nl']}) de antes -- não faz de novo.")
            continue

        interacao.andamento(f"Fazendo a NL do valor R$ {item['valor']} (NE {item['nota_de_empenho']})",
                            numero, len(lancamentos))
        item["nl"] = _incluir_nl(aba_sigef, context, item["valor_padronizado"], item["nota_de_empenho"])
        if item["nl"]:
            print(f"✅ NL feita para o valor {item['valor']}: {item['nl']}")
            gerou_alguma_nova = True
        else:
            print(
                f"⚠️  A NL do valor {item['valor']} não apareceu no SIGEF. O programa segue com os outros "
                "valores; confira este no SIGEF (veja o resumo no final)."
            )
        salvar_sessao(lancamentos=lancamentos)

    # Depois de colocar todas as NLs na grade (dtgDocumentos), falta
    # confirmar a operação uma última vez pra fechar o lote inteiro --
    # só com esse clique final o fluxo da NL fica completo de verdade.
    # Só clica se algo NOVO foi incluído na grade nesta execução -- se
    # todo mundo já tinha NL de antes (tudo pulado), não tem nada na
    # grade pra confirmar.
    if gerou_alguma_nova:
        aba_sigef.locator("#btnConfirmar").click()
        aba_sigef.wait_for_load_state("networkidle")

    aba_sigef.locator("img[src*='Limpar.GIF']").click()

    return lancamentos


if __name__ == "__main__":
    # Teste isolado da Etapa NL: conecta no Chrome já aberto e pede o CE
    # e um lançamento de teste (valor + nota de empenho) diretamente
    # pelo teclado — não precisa rodar SEI(1) nem CE de novo.
    from automacoes.anexar.automacao.utils import carregar_sessao, conectar_chrome, perguntar_ou_reusar

    playwright, browser, context = conectar_chrome()
    try:
        sessao = carregar_sessao()
        ce = perguntar_ou_reusar("Digite o CE (gerado na Etapa CE)", "ce", sessao)
        valor_padronizado = perguntar_ou_reusar(
            "Digite o valor padronizado de um lançamento de teste (ex: 787875)",
            "valor_padronizado",
            sessao,
        )
        nota_empenho = perguntar_ou_reusar(
            "Digite a nota de empenho desse lançamento", "nota_de_empenho", sessao
        )
        item_teste = {
            "valor": valor_padronizado,
            "valor_padronizado": valor_padronizado,
            "nota_de_empenho": nota_empenho,
        }
        resultado = executar_nl_lote(context, ce, [item_teste])
        print(f"OK: NL processada para o CE '{ce}'. Número da NL: {resultado[0]['nl']}")
    finally:
        playwright.stop()
