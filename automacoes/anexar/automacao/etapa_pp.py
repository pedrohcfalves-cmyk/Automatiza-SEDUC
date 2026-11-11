"""
Etapa PP: Preparação de Pagamento da Despesa Empenhada no SIGEF.

Cada lançamento tem sua própria NL (gerada na Etapa NL), mas todas
compartilham a mesma CE. executar_pp_lote() abre a página da PP uma
única vez e repete, pra cada lançamento, o ciclo de localizar a NL/CE
na tela de Gerar Ordem Cronológica, confirmar o item encontrado e
preencher o tipo de Ordem Bancária + banco/agência/conta -- sem
recarregar a página inteira entre um lançamento e outro.

executar_pp_lote() recebe `ce`, a lista de lançamentos (já com "nl") e
`conta_pp` direto, pra dar pra testar essa etapa sozinha sem rodar as
anteriores de novo -- o bloco "__main__" abaixo carrega os últimos
valores salvos na sessão como padrão e testa com um lançamento só.

Os dados da AUTOMAÇÃO vêm das configurações -- ver configuracoes.py e o
submenu "⚙️ Configurações das automações > PP". Sem mexer em nada, são os
mesmos valores de sempre:

    Tipo de Ordem Bancária   3 - Regularização
    Tipo de Serviço          10 - Crédito conta-corrente
    Banco                    001      (só no Crédito conta-corrente)
    Agência                  2757-X   (só no Crédito conta-corrente)
    Conta                    a Conta PP dos dados do processo

Unidade Gestora (160001) e Gestão (00001) vêm do Global ([G] no menu de
configurações), o mesmo valor de todas as etapas.

Banco, Agência e Conta aceitam letras, números e símbolos e são DIGITADOS
(tecla por tecla), depois de limpar o campo.
"""
import re
from datetime import date

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.configuracoes import (
    TIPOS_ORDEM_BANCARIA_PP,
    TIPOS_SERVICO_PP,
    config_global,
    config_pp,
    problemas_pp,
    usa_conta_corrente,
)
from automacoes.anexar.automacao.utils import (
    URL_SIGEF_PP,
    carregar_sessao,
    obter_ou_criar_aba,
    perguntar_ou_reusar,
    salvar_sessao,
)


class PPConfiguracaoIncompleta(Exception):
    """
    A configuração da PP (ou a Conta PP do processo) impede a geração --
    nada foi preenchido no SIGEF ainda, então dá pra ajustar e tentar de novo.
    """


def _digitar(campo, valor: str) -> None:
    """
    Limpa e DIGITA tecla por tecla -- aceita qualquer caractere (letras,
    números, "-"), igual a uma pessoa. Limpar antes evita somar com o que
    o postback do SIGEF tenha deixado no campo.
    """
    campo.click()
    campo.fill("")
    campo.press_sequentially(valor, delay=20)


def _campo_editavel(campo) -> bool:
    try:
        return campo.count() > 0 and campo.first.is_visible() and campo.first.is_editable()
    except Exception:
        return False


def _incluir_pp(aba_sigef, context, nl: str, ce: str, conta_pp: str, config: dict = None) -> str | None:
    """
    Localiza o lançamento pelos números `nl` e `ce` na tela de Gerar
    Ordem Cronológica, confirma o item encontrado e prepara o pagamento
    na conta `conta_pp`.

    Retorna o número da PP gerado (com prefixo, ex: "2026PP047704"), ou
    None se não for possível gerar.
    """
    config = {**config_global(), **(config or config_pp())}
    ano_atual = str(date.today().year)

    aba_sigef.locator("#txtUnidadeGestora").fill(config["unidade_gestora"])
    aba_sigef.locator("#txtGestao_SIGEFPesquisa").fill(config["gestao"])

    with context.expect_page() as nova_pagina_info:
        aba_sigef.locator("#txtNotaLancamento_BtnPesquisa").click()

    nova_pagina = nova_pagina_info.value
    nova_pagina.wait_for_load_state("networkidle")

    with context.expect_page() as nova_pagina1_info:
        nova_pagina.locator("#lnkNaoObedeceOrdemCronologica").click()

    nova_pagina1 = nova_pagina1_info.value
    nova_pagina1.wait_for_load_state("networkidle")

    nova_pagina1.locator("#txtNotaLancamentoSigla").fill(ano_atual)
    nova_pagina1.locator("#txtDespesaCertificadaSigla").fill(ano_atual)
    nova_pagina1.locator("#txtNotaLancamento_SIGEFPesquisa").fill(nl)
    nova_pagina1.locator("#txtDespesaCertificada_SIGEFPesquisa").fill(ce)
    nova_pagina1.locator("#btnConfirmar").click()
    nova_pagina1.locator("#divdtgGerarOrdemCronologica td.GridLink").first.click()

    for pagina_temp in (nova_pagina1, nova_pagina):
        try:
            pagina_temp.close()
        except Exception:
            pass

    aba_sigef.bring_to_front()
    aba_sigef.wait_for_load_state("networkidle")

    aba_sigef.wait_for_selector("#cboTipoOrdemBancaria", state="visible", timeout=5000)

    # #cboTipoOrdemBancaria dispara um postback -- TEM que ser selecionado
    # ANTES de preencher banco/agência/conta, senão o postback limpa esses
    # campos de novo.
    aba_sigef.locator("#cboTipoOrdemBancaria").select_option(value=config["tipo_ordem_bancaria"])
    aba_sigef.wait_for_load_state("networkidle")
    aba_sigef.locator("#cboTipoServico").select_option(value=config["tipo_servico"])
    aba_sigef.wait_for_load_state("networkidle")

    # Banco / Agência / Conta: aceitam letras, números e símbolos (ex:
    # agência 2757-X). No Crédito conta-corrente são obrigatórios; nos
    # outros tipos de serviço só são preenchidos se o SIGEF mostrar os
    # campos (com o banco/agência configurados e a Conta PP do processo).
    campos_conta = (
        ("#txtBanco", config["banco"]),
        ("#txtAgencia", config["agencia"]),
        ("#txtConta_SIGEFPesquisa", conta_pp),
    )
    if usa_conta_corrente(config):
        for seletor, valor in campos_conta:
            _digitar(aba_sigef.locator(seletor), valor)
        aba_sigef.wait_for_selector("#txtConta_SIGEFPesquisa", state="visible", timeout=5000)
    else:
        for seletor, valor in campos_conta:
            campo = aba_sigef.locator(seletor)
            if valor and _campo_editavel(campo):
                _digitar(campo.first, valor)

    aba_sigef.locator("#btnRetencoes").click()
    aba_sigef.wait_for_load_state("networkidle")
    aba_sigef.locator("img[src*='aba_confirmacao.gif']").click()

    aba_sigef.locator("#btnConfirmar").click()

    # O clique dispara um postback assíncrono -- conferir o elemento na
    # hora (sem esperar) pode achar que não tem nada lá ainda e devolver
    # None mesmo quando a PP FOI gerada no SIGEF. Isso é grave: o
    # lançamento fica marcado como falho e, na próxima execução, o
    # script tentaria gerar OUTRA PP pro mesmo lançamento -- duplicando.
    # Por isso espera a mensagem de sucesso aparecer antes de decidir.
    elemento_sucesso = aba_sigef.locator("td.SIGEFMensagemSucesso").first
    try:
        elemento_sucesso.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        return None

    texto_sucesso = elemento_sucesso.inner_text().strip()
    print(f"   SIGEF respondeu: {texto_sucesso}")

    # Extrai só o número COM prefixo (ex: "2026PP047704") -- é esse
    # formato que aparece na grade da Etapa OB, pra comparação lá bater.
    match = re.search(r"\d{4}PP\d+", texto_sucesso)
    pp = match.group(0) if match else texto_sucesso

    # Limpa a tela de PP de forma segura antes de devolver o número.
    try:
        aba_sigef.locator('img[src="/SIGEF/Recursos/Controles/Imagens/Limpar.GIF"]').click()
    except Exception:
        pass

    return pp


def executar_pp_lote(
    context, ce: str, lancamentos: list[dict], conta_pp: str, dados: dict = None, config: dict = None,
) -> list[dict]:
    """
    Gera a PP de cada lançamento da lista (cada um já com sua "nl",
    vinda de executar_nl_lote), sem recarregar a página inteira entre
    um lançamento e outro.

    `config` é a configuração da PP (padrão: a salva em configuracoes.py).
    Antes de tocar no SIGEF, confere se ela está completa e para com
    PPConfiguracaoIncompleta dizendo o que falta.

    Retorna a MESMA lista `lancamentos`, com a chave "pp" adicionada em
    cada item (o número gerado, ou None se não foi possível gerar).
    """
    config = {**config_global(), **(config or config_pp())}
    problemas = problemas_pp(config, {**(dados or {}), "conta_pp": conta_pp})
    if problemas:
        raise PPConfiguracaoIncompleta(
            "A PP não pode ser gerada com a configuração atual:\n  - "
            + "\n  - ".join(problemas)
            + "\nAjuste em '⚙️ Configurações das automações > PP' (ou a Conta PP nos dados do processo)."
        )
    print(
        f"   💳 PP: OB {config['tipo_ordem_bancaria']} - {TIPOS_ORDEM_BANCARIA_PP[config['tipo_ordem_bancaria']]} | "
        f"serviço {config['tipo_servico']} - {TIPOS_SERVICO_PP[config['tipo_servico']]}"
        + (f" | banco {config['banco']} ag. {config['agencia']} conta {conta_pp}" if usa_conta_corrente(config) else "")
    )

    aba_sigef = obter_ou_criar_aba(
        context,
        dominio="sigef.sefin.ro.gov.br",
        url_navegacao=URL_SIGEF_PP,
    )
    aba_sigef.goto(URL_SIGEF_PP)
    aba_sigef.wait_for_load_state("networkidle")

    for numero, item in enumerate(lancamentos, start=1):
        if item.get("pp"):
            # Já tem PP de uma execução anterior -- pula pra não gerar
            # duplicado.
            print(f"⏭️  O valor {item['valor']} já tem PP ({item['pp']}) de antes -- não faz de novo.")
            continue

        nl = item.get("nl")
        if not nl:
            print(f"⚠️  O valor {item['valor']} ficou sem NL -- por isso não dá para fazer a PP dele.")
            item["pp"] = None
            continue

        interacao.andamento(f"Fazendo a PP do valor R$ {item['valor']} (NL {nl})", numero, len(lancamentos))
        item["pp"] = _incluir_pp(aba_sigef, context, nl, ce, conta_pp, config)
        if item["pp"]:
            print(f"✅ PP feita para o valor {item['valor']}: {item['pp']}")
        else:
            print(
                f"⚠️  A PP do valor {item['valor']} não foi confirmada pelo SIGEF. O programa segue com os "
                "outros; confira este no SIGEF (veja o resumo no final)."
            )
        salvar_sessao(lancamentos=lancamentos)

    return lancamentos


if __name__ == "__main__":
    # Teste isolado da Etapa PP: conecta no Chrome já aberto e pede o
    # CE, a conta PP e um lançamento de teste (NL + valor) diretamente
    # pelo teclado — não precisa rodar as etapas anteriores de novo.
    from automacoes.anexar.automacao.utils import conectar_chrome

    playwright, browser, context = conectar_chrome()
    try:
        sessao = carregar_sessao()
        ce = perguntar_ou_reusar("Digite o CE (gerado na Etapa CE)", "ce", sessao)
        conta_pp = perguntar_ou_reusar("Digite a conta PP", "conta_pp", sessao)
        nl = perguntar_ou_reusar("Digite a NL (gerada na Etapa NL)", "nl", sessao)
        valor_padronizado = perguntar_ou_reusar(
            "Digite o valor padronizado desse lançamento (ex: 787875)",
            "valor_padronizado",
            sessao,
        )
        item_teste = {"valor": valor_padronizado, "valor_padronizado": valor_padronizado, "nl": nl}
        resultado = executar_pp_lote(context, ce, [item_teste], conta_pp)
        print(f"OK: PP processada para a NL '{nl}'. Número da PP: {resultado[0]['pp']}")
    finally:
        playwright.stop()
