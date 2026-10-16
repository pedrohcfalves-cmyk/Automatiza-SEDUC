"""Passos no site do DARE: preencher o DARE avulso e salvar o PDF."""

import logging
from datetime import date
from pathlib import Path

from playwright.sync_api import expect

from . import config, navegador, utils
from .modelos import DadosDare

log = logging.getLogger("dare.dare")


def selecionar_data_no_picker(page, alvo: date) -> None:
    """Abre o seletor de datas, navega até o mês/ano desejado e clica no dia."""
    page.get_by_placeholder("00/00/0000").click()
    picker = page.locator(".picker--opened")

    for _ in range(36):  # limite de segurança
        mes_txt = picker.locator(".picker__month").inner_text().strip().lower()
        ano_txt = picker.locator(".picker__year").inner_text().strip()
        mes_atual = next((i + 1 for i, m in enumerate(utils.MESES) if mes_txt.startswith(m)), None)
        if mes_atual is None or not ano_txt.isdigit():
            break  # não foi possível interpretar o cabeçalho; tenta clicar direto
        delta = (alvo.year - int(ano_txt)) * 12 + (alvo.month - mes_atual)
        if delta == 0:
            break
        picker.locator(".picker__nav--next" if delta > 0 else ".picker__nav--prev").click()

    picker.locator(".picker__day--infocus:not(.picker__day--disabled)").get_by_text(
        str(alvo.day), exact=True
    ).click()


def gerar_dare(context, page, dados: DadosDare) -> tuple[Path, str]:
    """
    Preenche o DARE avulso, imprime para PDF e volta à tela inicial.
    Devolve (caminho do PDF, nome do servidor).
    """
    # Se a página tiver um aviso inicial (modal), fecha.
    aviso = page.locator("#dare-avulso-alert-title")
    if aviso.is_visible():
        log.info("Fechando o aviso inicial do DARE.")
        page.locator(".dare-avulso-modal-action").click()

    # 1.0 Menu
    log.info("DARE 1/5 · Órgão e contribuinte")
    page.locator("#select2-orgaos_opcao-container").click()
    page.click(f"li.select2-results__option:has-text('{config.ORGAO}')")
    page.locator('input[name="ind"][value="3"]').check()
    page.locator("#identificacao").fill(dados.cnpj)
    page.locator("#identificar-contribuinte").click()

    # 2.1 Código da receita
    log.info("DARE 2/5 · Receita %s, unidade gestora e gestão", config.CODIGO_RECEITA)
    page.locator("#toggle-modal-rec").click()
    page.wait_for_selector("#datatable-receitas")
    page.click(f"tr[data-receita='{config.CODIGO_RECEITA}']")
    # 2.2 Gestão
    page.get_by_placeholder("CÓDIGO DA UNIDADE GESTORA").fill(config.UNIDADE_GESTORA)
    page.get_by_placeholder("CÓDIGO DA GESTÃO").fill(config.GESTAO)

    # 2.3 CPF e nome
    log.info("DARE 3/5 · CPF %s", utils.mascarar_cpf(dados.cpf))
    cpf_campo = page.get_by_placeholder("000.000.000-00")
    cpf_campo.press_sequentially(dados.cpf, delay=50)
    campo_nome_servidor = page.locator('input[name="reembolso_nome"]')
    campo_nome_servidor.click()

    # 2.4 Recolhedor, referência e vencimento
    log.info(
        "DARE 4/5 · Referência %s, vencimento %s, valor R$ %s",
        utils.formatar_mes_ano(dados.mes_ano_referencia),
        dados.vencimento.strftime("%d/%m/%Y"),
        dados.valor,
    )
    page.locator("input[name='complemento_identificacao']").fill(dados.cnpj_recolhedor)
    page.locator("input[name='mesano_referencia']").fill(dados.mes_ano_referencia)
    selecionar_data_no_picker(page, dados.vencimento)
    # 2.5 Valor (a vírgula é automática: 100,00 -> digita 10000)
    page.locator("#valor_principal").press_sequentially(dados.valor_digitos, delay=50)

    # Nome do servidor (preenchido automaticamente pelo site após informar o CPF)
    try:
        expect(campo_nome_servidor).not_to_have_value("", timeout=5000)
    except AssertionError:
        log.warning("O site não preencheu o nome do servidor; o PDF ficará sem o nome.")
    nome_servidor = campo_nome_servidor.input_value()
    log.info("Servidor: %s", nome_servidor or "(não preenchido)")

    # 3.0 IMPRIMIR -> salvar como PDF
    log.info("DARE 5/5 · Imprimindo e salvando o PDF")
    config.PASTA_PDF.mkdir(parents=True, exist_ok=True)
    nome_pdf = (
        f"DARE_{utils.nome_arquivo_seguro(nome_servidor)}_{utils.somente_digitos(dados.cpf)}"
        f"_{utils.somente_digitos(dados.mes_ano_referencia)}"
        f"_venc-{dados.vencimento:%d-%m-%Y}.pdf"
    )
    caminho_pdf = utils.caminho_sem_conflito(config.PASTA_PDF / nome_pdf)

    paginas_antes = list(context.pages)
    page.locator(
        "button.dare-avulso-dados-action.dare-avulso-dados-primary:has-text('IMPRIMIR')"
    ).click()

    pagina_impressao = navegador.aguardar_pagina_de_impressao(context, page, paginas_antes)
    navegador.ativar_aba(context, pagina_impressao)
    navegador.salvar_pdf(context, pagina_impressao, caminho_pdf)
    log.info("PDF salvo em: %s", caminho_pdf)

    # 4.0 Voltar
    voltar = pagina_impressao.locator("a.btn.btn-info[href='/avulso']")
    if voltar.count() == 0:
        voltar = page.locator("a.btn.btn-info[href='/avulso']")
    voltar.first.click()

    # Se o documento abriu em outra aba, fecha-a e volta para a aba principal
    if pagina_impressao is not page and not pagina_impressao.is_closed():
        pagina_impressao.close()

    return caminho_pdf, nome_servidor
