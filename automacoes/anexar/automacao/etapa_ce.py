"""
Etapa CE: preenche a Despesa Certificada no SIGEF e obtém o número CE
gerado. Cobre o trecho desde o preenchimento do formulário até a
inclusão do lançamento.

Os dados do PROCESSO (valor, CNPJ/CPF, município, escola, parcela, mês
etc.) são coletados na Etapa SEI (1) -- ver coletar_dados_sigef() em
etapa_sei1.py -- e chegam prontos no parâmetro `dados` de executar_ce().

Os dados da AUTOMAÇÃO (Unidade Gestora, Gestão, Tipo de Documento,
Nº do Documento, datas, credor CNPJ/CPF, observação) vêm das
configurações -- ver configuracoes.py e o submenu "⚙️ Configurações das
automações > CE". Sem mexer em nada, são os mesmos valores de sempre:

    Tipo de Documento 6 - Aviso Débito Banco
    Datas             data de hoje (aceite, apresentação e emissão -- cada
                      uma pode ser trocada por uma data fixa)
    Observação        "Regularização da {parcela} do {programa} Em favor de ..."

Global ([G] no menu de configurações -- vale para todas as etapas):

    Unidade Gestora   160001    (#txtCdUnidadeGestora)
    Gestão            00001     (#txtCdGestao_SIGEFPesquisa)

Fixos, sem configuração:

    Nº do Documento   {programa}/{ano} -- o Programa do menu de dados
    Atestado          sempre marcado
    Credor            CNPJ (14 dígitos) ou CPF (11 dígitos), detectado sozinho
                      pelo CNPJ/CPF do processo

Casos especiais tratados aqui:
    - Tipo de Documento Nota Fiscal (1, 2, 3, 4, 12): o SIGEF só gera a
      CE com Subsérie (#txtNuSubSerie), Série (#txtNuSerie) e Modelo
      (#txtNmModelo) preenchidos -- configurados no submenu da CE.
    - Credor pessoa física: na busca do credor, clica em "CPF" (#btnCPF)
      e preenche #txtNuCpf em vez de #txtNuCnpj.
    - Mês de competência 13 = Décimo Terceiro (#cboMesComp).
"""
import time

from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.configuracoes import (
    CREDOR_CPF,
    DATAS_CE,
    config_global,
    config_ce,
    data_ce,
    eh_nota_fiscal,
    nome_mes,
    nome_tipo_documento,
    numero_documento_ce,
    preencher_modelo,
    problemas_ce,
    so_digitos,
    tipo_credor,
)
from automacoes.geral import mascarar_cpf
from automacoes.anexar.automacao.valores import digitar_valor_conferido
from automacoes.anexar.automacao.utils import URL_SIGEF, obter_ou_criar_aba, salvar_sessao

# Quanto esperar o SIGEF devolver o número da CE depois do "Incluir".
TIMEOUT_NUMERO_CE_S = 20
# Quanto esperar os campos de Nota Fiscal aparecerem depois de escolher o tipo.
TIMEOUT_CAMPOS_NF_MS = 10000


class CENaoGerada(Exception):
    """A CE não pôde ser gerada (configuração incompleta ou o SIGEF recusou)."""


class CEConfiguracaoIncompleta(CENaoGerada):
    """
    A configuração da CE (ou os dados do processo) impede a geração -- nada
    foi preenchido no SIGEF ainda, então dá pra ajustar e tentar de novo.
    """


def _digitar(campo, valor: str) -> None:
    """
    Limpa e DIGITA o valor tecla por tecla (dispara as validações de
    teclado do SIGEF -- ValidarCaracter, AutoTabular -- igual a uma pessoa).
    """
    campo.click()
    campo.fill("")
    campo.press_sequentially(valor, delay=20)


def _ler_numero_ce(aba_sigef) -> str:
    """
    Espera o SIGEF devolver o número da CE em #txtNuSeq (o "Incluir" faz um
    postback; ler na mesma hora podia pegar o campo ainda vazio).
    """
    campo = aba_sigef.locator("#txtNuSeq")
    prazo = time.monotonic() + TIMEOUT_NUMERO_CE_S
    while time.monotonic() < prazo:
        try:
            valor = campo.input_value(timeout=2000).strip()
        except Exception:
            valor = ""
        if valor:
            return valor
        aba_sigef.wait_for_timeout(300)
    raise CENaoGerada(
        f"Cliquei em 'Incluir', mas o SIGEF não mostrou o número da CE (esperei "
        f"{TIMEOUT_NUMERO_CE_S} segundos).\n"
        "O QUE FAZER, ANTES de rodar o programa de novo:\n"
        "  1. Olhe a tela do SIGEF no Chrome do programa.\n"
        "  2. Se aparecer o número da CE: ela FOI feita. Anote o número. Ao rodar de novo,\n"
        "     quando o programa perguntar, NÃO faça outra CE.\n"
        "  3. Se aparecer uma mensagem de erro do SIGEF: leia, corrija (nos dados ou nas\n"
        "     configurações da CE) e rode de novo.\n"
        "  4. Se não entender a tela, chame quem cuida do sistema ANTES de rodar de novo."
    )


def incluir_documento_sigef(aba_sigef, valor_padronizado: str) -> str:
    """
    Preenche o valor do documento no SIGEF, inclui o lançamento e retorna
    o número de sequência gerado (CE - Certificado de Despesa).
    """
    aba_sigef.bring_to_front()

    # Limpa, digita e lê de volta: valor errado na CE não tem como desfazer depois do Incluir.
    digitar_valor_conferido(aba_sigef, aba_sigef.locator("#txtVlDocumento"), valor_padronizado)
    aba_sigef.locator("#btnManutencao_BtnIncluir").click()

    ce = _ler_numero_ce(aba_sigef)

    aba_sigef.locator("#txtNuSeq").fill("")

    return ce


def _preencher_nota_fiscal(aba_sigef, config: dict) -> None:
    """Subsérie, Série e Modelo -- só quando o Tipo de Documento é Nota Fiscal."""
    aba_sigef.wait_for_load_state("networkidle")
    campos = (
        ("#txtNuSubSerie", config["nf_subserie"], "Subsérie"),
        ("#txtNuSerie", config["nf_serie"], "Série"),
        ("#txtNmModelo", config["nf_modelo"], "Modelo"),
    )
    for seletor, valor, rotulo in campos:
        campo = aba_sigef.locator(seletor)
        try:
            campo.wait_for(state="visible", timeout=TIMEOUT_CAMPOS_NF_MS)
        except Exception as erro:
            raise CENaoGerada(
                f"Escolhi o Tipo de Documento '{nome_tipo_documento(config['tipo_documento'])}', "
                f"mas o campo {rotulo} ({seletor}) não apareceu na tela do SIGEF."
            ) from erro
        _digitar(campo, valor)


def _selecionar_credor(context, aba_sigef, dados: dict) -> None:
    """
    Abre a busca do credor e escolhe o credor pelo CNPJ (como sempre) ou,
    se for pessoa física, pelo CPF (botão "CPF" + #txtNuCpf). Quem decide
    é o próprio {cnpj_cpf} do processo: 14 dígitos = CNPJ, 11 = CPF.
    """
    cnpj_cpf = dados["cnpj_cpf"]
    tipo = tipo_credor(cnpj_cpf)

    with context.expect_page() as nova_pagina_info:
        aba_sigef.locator("#txtNmCredor_BtnPesquisa").click()

    nova_pagina = nova_pagina_info.value
    nova_pagina.wait_for_load_state("networkidle")

    try:
        if tipo == CREDOR_CPF:
            print(f"   👤 Credor pessoa física -- pesquisando pelo CPF {mascarar_cpf(cnpj_cpf)}")
            nova_pagina.locator("#btnCPF").click()
            nova_pagina.wait_for_load_state("networkidle")
            _digitar(nova_pagina.locator("#txtNuCpf"), so_digitos(cnpj_cpf))
        else:
            print(f"   🏢 Credor pessoa jurídica -- pesquisando pelo CNPJ {cnpj_cpf}")
            nova_pagina.locator("#txtNuCnpj").fill(cnpj_cpf)

        nova_pagina.locator("#btnConfirmar").click()
        nova_pagina.locator("td.GridLink[onclick*='SelecionarItem']").first.click()
    finally:
        # Fecha a aba de busca do credor -- já cumpriu seu papel.
        try:
            nova_pagina.close()
        except Exception:
            pass


def preencher_despesa_certificada(aba_sigef, context, dados: dict, processo: str, config: dict = None) -> str:
    """
    Preenche o formulário de Despesa Certificada no SIGEF (gestão, tipo de
    documento, datas, observação, credor) e inclui o lançamento.

    `config` é a configuração da CE (padrão: a salva em configuracoes.py).
    Antes de tocar no SIGEF, confere se ela está completa -- ex: tipo Nota
    Fiscal sem Série -- e para com CENaoGerada dizendo o que falta.

    Retorna o número CE gerado por incluir_documento_sigef.
    """
    # Unidade Gestora e Gestão: as do Global, a menos que `config` traga outras.
    config = {**config_global(), **(config or config_ce())}
    problemas = problemas_ce(config, dados)
    if problemas:
        raise CEConfiguracaoIncompleta(
            "A CE não pode ser gerada com a configuração atual:\n  - "
            + "\n  - ".join(problemas)
            + "\nAjuste em '⚙️ Configurações das automações > CE' (ou nos dados do processo)."
        )

    datas = {chave: data_ce(config, chave) for chave, _rotulo, _seletor in DATAS_CE}
    mes = str(dados["mes_referencia"])
    tipo = config["tipo_documento"]

    print(
        f"   🧾 CE: {tipo} - {nome_tipo_documento(tipo)} | competência {mes} - {nome_mes(mes)} | "
        + " | ".join(
            f"{rotulo.split()[-1].lower()} {datas[chave][:2]}/{datas[chave][2:4]}/{datas[chave][4:]}"
            for chave, rotulo, _seletor in DATAS_CE
        )
    )

    aba_sigef.bring_to_front()

    aba_sigef.locator("#txtCdUnidadeGestora").fill(config["unidade_gestora"])
    aba_sigef.locator("#txtCdGestao_SIGEFPesquisa").fill(config["gestao"])
    aba_sigef.locator("#cmbCdTipoDocumento").select_option(tipo)
    if eh_nota_fiscal(config):
        _preencher_nota_fiscal(aba_sigef, config)

    aba_sigef.locator("#txtNuDocumento").fill(numero_documento_ce(dados, processo))
    aba_sigef.locator("#chkFlAtestadoRecSouResp").check()   # sempre marcado
    # Aceite, Apresentação e Emissão -- cada uma com a sua data (hoje ou fixa).
    for chave, _rotulo, seletor in DATAS_CE:
        aba_sigef.locator(seletor).fill(datas[chave])
    # 1 a 12 = meses; 13 = Décimo Terceiro.
    aba_sigef.locator("#cboMesComp").select_option(mes)
    aba_sigef.locator("#txtDeObservacao").fill(preencher_modelo(config["observacao"], dados, processo))

    _selecionar_credor(context, aba_sigef, dados)

    return incluir_documento_sigef(aba_sigef, dados["valor_padronizado"])


def executar_ce(context, processo: str, dados: dict, config: dict = None) -> str:
    """
    Executa a Etapa CE completa: obtém/cria a aba do SIGEF, preenche a
    Despesa Certificada com os dados recebidos (já coletados na Etapa SEI
    (1), via coletar_dados_sigef()) e a configuração da CE, e obtém o CE
    gerado.

    Retorna o número CE gerado.
    """
    aba_sigef = obter_ou_criar_aba(
        context,
        dominio="sigef.sefin.ro.gov.br",
        url_navegacao=URL_SIGEF,
        trecho_pagina="FINManterDespesaCertificada",
    )

    interacao.andamento(f"Preenchendo a CE no SIGEF (Valor Total R$ {dados.get('valor_total')})")
    ce = preencher_despesa_certificada(aba_sigef, context, dados, processo, config)
    print(f"✅ CE feita: {ce}")
    salvar_sessao(ce=ce)

    return ce


if __name__ == "__main__":
    # Teste isolado da Etapa CE: conecta no Chrome já aberto e só executa
    # essa etapa, sem precisar rodar a Etapa SEI(1) de verdade. Os dados
    # (que normalmente vêm do SEI(1)) são coletados aqui na hora, chamando
    # a mesma função que o SEI(1) usa -- inclusive com o submenu de
    # configurações.
    from automacoes.anexar.automacao.etapa_sei1 import coletar_dados_sigef
    from automacoes.anexar.automacao.utils import carregar_sessao, conectar_chrome, perguntar_ou_reusar

    playwright, browser, context = conectar_chrome()
    try:
        sessao = carregar_sessao()
        processo = perguntar_ou_reusar(
            "Digite o processo do SEI (para nomear a pasta)", "processo", sessao
        )
        dados = coletar_dados_sigef(processo)
        dados["valor_padronizado"] = dados["valor_total_padronizado"]
        ce = executar_ce(context, processo, dados)
        print(f"OK: CE '{ce}' processado.")
    finally:
        playwright.stop()
