"""
Etapa OB: Ordem Bancária no SIGEF.

Gera UMA Ordem Bancária para todas as PPs do lote (executar_ob_lote): na
busca de PPs da tela de OB, marca a linha de cada PP gerada na etapa
anterior (PP + valor têm que bater) e inclui a OB.

executar_ob() recebe `pp`, `conta_ob` e `valor_padronizado` direto, no
mesmo esquema da NL/PP, pra dar pra testar essa etapa sozinha sem rodar
as anteriores de novo -- o bloco "__main__" abaixo carrega os últimos
valores salvos na sessão como padrão.

Os dados da AUTOMAÇÃO vêm das configurações -- ver configuracoes.py e o
submenu "⚙️ Configurações das automações > OB". Sem mexer em nada, são os
mesmos valores de sempre:

    Banco de origem      001
    Agência de origem    2757-X
    Tipo de OB           2 - Descentralizada
    Tipo de Pagamento    2 - Diversos
    Fonte de recurso     500001001  (busca da PP)
    Observação           "Regularização do valor pago na data de 01/07/2026 na conta do PROAFI"

Global ([G] no menu de configurações): Unidade Gestora (160001) e Gestão
(00001), usadas na tela da OB e na busca da PP.

Fixos: Conta de origem = Conta OB dos dados do processo; Data de
referência = hoje; Id Uso = 1. Banco, Agência e Conta de origem aceitam
letras, números e símbolos e são DIGITADOS depois de limpar o campo.
"""
import re
from datetime import date

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.configuracoes import (
    TIPOS_OB,
    TIPOS_PAGAMENTO_OB,
    config_global,
    config_ob,
    preencher_modelo,
    problemas_ob,
)
from automacoes.anexar.automacao.utils import (
    URL_SIGEF_OB,
    carregar_sessao,
    normalizar,
    obter_ou_criar_aba,
    perguntar_ou_reusar,
    salvar_sessao,
)


class OBConfiguracaoIncompleta(Exception):
    """
    A configuração da OB (ou a Conta OB do processo) impede a geração --
    nada foi preenchido no SIGEF ainda, então dá pra ajustar e tentar de novo.
    """


def _digitar(campo, valor: str) -> None:
    """
    Limpa e DIGITA tecla por tecla -- aceita qualquer caractere (letras,
    números, "-"). Limpar antes evita somar com o que já estiver no campo.
    """
    campo.click()
    campo.fill("")
    campo.press_sequentially(valor, delay=20)


class OBPPNaoEncontrada(Exception):
    """Alguma PP do lote não apareceu na busca da OB -- nenhuma OB foi gerada."""


_JS_GRADE_PP = """
() => [...document.querySelectorAll("tr.GridLinhaPar, tr.GridLinhaImpar")].map((linha, indice) => {
    const td = [...linha.querySelectorAll("td")].map((x) => x.innerText.trim());
    // COLUNAS REAIS DO SIGEF
    return {indice: indice, pp: td[6], valor: td[15]};
})
"""


def _marcar_pps(nova_pagina, pps: list[tuple[str, str]]) -> None:
    """
    Na busca de PPs da OB, marca a linha de CADA PP do lote -- só quando a
    PP E o valor batem (SISTEMA PARA PREVENÇÃO DE ERRO DE OB). Se faltar
    qualquer uma, não marca nada e para: melhor nenhuma OB do que uma OB
    com PPs a menos (ou a mais).
    """
    # Aguarda a tabela carregar e lê tudo de uma vez.
    nova_pagina.wait_for_selector("tr.GridLinhaPar, tr.GridLinhaImpar")
    registros_grid = nova_pagina.evaluate(_JS_GRADE_PP)
    print(f"   O SIGEF mostrou {len(registros_grid)} PP(s) para escolher.")

    escolhidos, faltando = [], []
    for pp, valor_padronizado in pps:
        valor_esperado = normalizar(valor_padronizado)
        registro = None
        for item in registros_grid:
            try:
                valor_site = normalizar(item["valor"])
            except Exception:
                continue
            # Compara em CENTAVOS inteiros: com float, "< 0.01" deixava passar
            # 1 centavo de diferença (857,51 contra 857,50).
            if item["pp"] == pp and round(valor_site * 100) == round(valor_esperado * 100) \
                    and item["indice"] not in {r["indice"] for r in escolhidos}:
                registro = item
                break
        if registro is None:
            faltando.append(f"{pp} (valor {valor_esperado:.2f})")
        else:
            escolhidos.append(registro)
            print(f"   ✔ Achei a PP {pp} (valor {valor_esperado:.2f})")

    if faltando:
        raise OBPPNaoEncontrada(
            "nenhuma OB foi feita, porque estas PPs não apareceram no SIGEF com o valor certo: "
            + "; ".join(faltando)
            + ". Confira essas PPs no SIGEF."
        )

    for registro in escolhidos:
        checkbox = nova_pagina.locator(f"#chk{registro['indice']}")
        checkbox.wait_for(state="visible")
        if not checkbox.is_checked():
            checkbox.click()
        print(f"   ☑ Marcada a PP {registro['pp']}")


def _limpar_tela_ob(aba_sigef, qtd_itens: int) -> None:
    """
    Depois de gerada, tira as PPs da lista da tela (pra ela ficar pronta pra
    próxima OB). Não é crítico: um erro aqui NÃO pode fazer perder o número
    da OB que já foi gerada.
    """
    try:
        aba_sigef.locator("#txtNumeroOB").fill("")
        for indice in range(max(1, qtd_itens)):
            checkbox = aba_sigef.locator(f"#chk{indice}")
            if checkbox.count() > 0 and not checkbox.first.is_checked():
                checkbox.first.check()
        aba_sigef.locator("#btnRemover").click()
    except Exception as erro:
        print(f"⚠️  Não consegui limpar a tela da OB ({erro}) -- sem problema, a OB já foi gerada.")


def executar_ob_lote(
    context, pps: list[tuple[str, str]], conta_ob: str, dados: dict = None, config: dict = None,
) -> str | None:
    """
    Gera UMA Ordem Bancária para TODAS as PPs do lote: `pps` é a lista
    [(pp, valor_padronizado), ...] (ex: [("2026PP039778", "325850"), ...]).
    Na busca de PPs, marca a linha de cada uma (PP + valor têm que bater);
    se faltar alguma, para sem gerar nada (OBPPNaoEncontrada).

    `config` é a configuração da OB (padrão: a salva em configuracoes.py).
    Antes de tocar no SIGEF, confere se ela está completa e para com
    OBConfiguracaoIncompleta dizendo o que falta.

    Retorna o número da OB gerado, ou None se não for possível gerar.
    """
    if not pps:
        raise ValueError("Nenhuma PP para a OB.")
    config = {**config_global(), **(config or config_ob())}
    problemas = problemas_ob(config, {**(dados or {}), "conta_ob": conta_ob})
    if problemas:
        raise OBConfiguracaoIncompleta(
            "A OB não pode ser gerada com a configuração atual:\n  - "
            + "\n  - ".join(problemas)
            + "\nAjuste em '⚙️ Configurações das automações > OB' (ou a Conta OB nos dados do processo)."
        )
    print(
        f"   🏦 OB ({len(pps)} PP(s)): {config['tipo_ob']} - {TIPOS_OB[config['tipo_ob']]} | pagamento "
        f"{config['tipo_pagamento']} - {TIPOS_PAGAMENTO_OB[config['tipo_pagamento']]} | origem "
        f"{config['banco_origem']} ag. {config['agencia_origem']} conta {conta_ob} | fonte {config['fonte_recurso']}"
    )

    aba_sigef = obter_ou_criar_aba(
        context,
        dominio="sigef.sefin.ro.gov.br",
        url_navegacao=URL_SIGEF_OB,
    )
    aba_sigef.goto(URL_SIGEF_OB)
    aba_sigef.wait_for_load_state("networkidle")

    data_atual = date.today().strftime("%d%m%Y")
    interacao.andamento(f"Preenchendo a OB que paga {len(pps)} PP(s)")

    aba_sigef.locator("input[name='txtDataReferencia$SIGEFData']").fill(data_atual)
    aba_sigef.locator("#txtUnidadeGestora").fill(config["unidade_gestora"])
    aba_sigef.locator("#txtGestao_SIGEFPesquisa").fill(config["gestao"])
    _digitar(aba_sigef.locator("input[name='txtBancoOrigem']"), config["banco_origem"])
    _digitar(aba_sigef.locator("input[name='txtAgenciaOrigem']"), config["agencia_origem"])
    _digitar(aba_sigef.locator("input[name='txtContaOrigem']"), conta_ob)
    # 1 Centralizada, 2 Descentralizada, 3 Regularização, 4 Extra-Orçamentária
    aba_sigef.locator("#cboTipoOB").select_option(config["tipo_ob"])
    # 1 Específico, 2 Diversos, 3 Consignações/Retenções, 4 Diárias
    aba_sigef.locator("#cboTipoPagamento").select_option(config["tipo_pagamento"])

    aba_sigef.locator("#txtDeObservacao").fill(
        preencher_modelo(config["observacao"], dados, (dados or {}).get("processo"))
    )

    with context.expect_page() as nova_pagina_info:
        aba_sigef.locator("#btnAdicionar").click()

    nova_pagina = nova_pagina_info.value
    nova_pagina.wait_for_load_state("networkidle")

    nova_pagina.locator("#txtUnidadeGestora").fill(config["unidade_gestora"])
    nova_pagina.locator("#txtGestao_SIGEFPesquisa").fill(config["gestao"])
    nova_pagina.locator("#txtIdUso").fill("1")
    nova_pagina.locator("#txtFonte_SIGEFPesquisa").fill(config["fonte_recurso"])
    nova_pagina.locator("#btnPesquisar").click()

    interacao.andamento(f"Marcando as {len(pps)} PP(s) do lote na busca da OB")
    try:
        _marcar_pps(nova_pagina, pps)
    except OBPPNaoEncontrada:
        try:
            nova_pagina.close()
        except Exception:
            pass
        raise

    nova_pagina.locator("#btnConfirmar").click()
    nova_pagina.wait_for_event("close")

    aba_sigef.bring_to_front()
    aba_sigef.wait_for_load_state("networkidle")

    aba_sigef.locator("#SIGEFBotoesManutencao_BtnIncluir").click()

    # O clique dispara um postback assíncrono -- conferir o elemento na
    # hora (sem esperar) pode achar que não tem nada lá ainda e devolver
    # None mesmo quando a OB FOI gerada no SIGEF (mesmo bug já visto na
    # Etapa PP). Espera a mensagem de sucesso aparecer antes de decidir.
    elemento_sucesso = aba_sigef.locator("td.SIGEFMensagemSucesso").first
    try:
        elemento_sucesso.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        print("⚠️  O SIGEF não confirmou a OB. Olhe a tela do SIGEF antes de rodar de novo.")
        return None

    ob = elemento_sucesso.inner_text().strip()
    print(f"   SIGEF respondeu: {ob}")

    match = re.search(r"\d{4}OB\d+", ob)
    if not match:
        raise Exception(
            "o SIGEF respondeu, mas não achei o número da OB na mensagem. "
            "Olhe a tela do SIGEF: se a OB foi feita, anote o número antes de rodar de novo."
        )

    numero_ob = match.group(0)
    print(f"✅ OB feita: {numero_ob} (paga {len(pps)} PP(s))")

    # Grava ANTES de mexer na tela de novo: o número não pode se perder.
    salvar_sessao(ob=numero_ob)
    _limpar_tela_ob(aba_sigef, len(pps))

    return numero_ob


def executar_ob(
    context, pp: str, conta_ob: str, valor_padronizado: str, dados: dict = None, config: dict = None,
) -> str | None:
    """
    OB de UMA PP só (atalho de executar_ob_lote, usado pelo teste isolado
    desta etapa). O fluxo do main.py gera uma OB para o lote inteiro.
    """
    return executar_ob_lote(context, [(pp, valor_padronizado)], conta_ob, dados, config)


if __name__ == "__main__":
    # Teste isolado da Etapa OB: conecta no Chrome já aberto e pede só a
    # PP, a conta OB e o valor diretamente pelo teclado — não precisa
    # rodar as etapas anteriores de novo. Útil quando você já tem esses
    # valores de um teste anterior e só quer testar essa etapa.
    from automacoes.anexar.automacao.utils import conectar_chrome

    playwright, browser, context = conectar_chrome()
    try:
        sessao = carregar_sessao()
        pp = perguntar_ou_reusar("Digite a PP (gerada na Etapa PP)", "pp", sessao)
        conta_ob = perguntar_ou_reusar("Digite a conta OB", "conta_ob", sessao)
        valor_padronizado = perguntar_ou_reusar(
            "Digite o valor padronizado (ex: 787875 para 7.878,75)",
            "valor_padronizado",
            sessao,
        )
        ob = executar_ob(context, pp, conta_ob, valor_padronizado)
        print(f"OK: OB processada para a PP '{pp}'. Número da OB: {ob}")
    finally:
        playwright.stop()
