"""
Configurações das automações do SIGEF (Global, CE, NL, PP, OB).

Cada automação tem os seus PADRÕES (os valores que antes estavam fixos no
código). Sem mexer em nada, tudo continua igual. O que for alterado fica
salvo em dados/configuracoes_automacao.json e vale para os próximos
processos até ser mudado de novo (ou restaurado para o padrão).

A pessoa altera tudo na tela "Configurações" do aplicativo: uma TABELA por
automação (Campo | Valor | Padrão), com listas para escolher, botões
Salvar e Voltar ao padrão, e o que falta em amarelo. Este arquivo monta
essas tabelas (formulario / secao) e confere e grava o que voltar delas
(salvar_secao / restaurar_padrao). Nada aqui pede para digitar letras.

GLOBAL: Unidade Gestora e Gestão valem ao mesmo tempo para CE, NL, PP, OB
e o download dos documentos.

Regra das tabelas: só aparece o que faz sentido no caso. Ex: Subsérie,
Série e Modelo só aparecem quando o Tipo de Documento é uma Nota Fiscal;
Banco e Agência da PP, só com Crédito conta-corrente.

Fixos (aparecem como "automático"): Atestado receb./resp. sempre marcado;
Nº do Documento sempre "{programa}/{ano}"; credor CNPJ ou CPF detectado
sozinho pelo {cnpj_cpf} do processo.

As Observações aceitam estes campos, trocados pelos dados do processo na
hora de preencher:

    {processo} {programa} {parcela} {escola} {municipio}
    {ano} {mes} {mes_nome} {cnpj_cpf} {valor_total}
"""
import json
import os
import re
import string
from datetime import date, datetime

from automacoes.geral import gravar_json
from automacoes.anexar import caminhos

CAMINHO_CONFIG = caminhos.ARQUIVO_CONFIGURACOES

# ============================================================ GLOBAL

# Unidade Gestora e Gestão: as mesmas em todas as telas do SIGEF usadas
# pela automação (CE, NL, PP, OB e o download dos documentos).
PADRAO_GLOBAL = {
    "unidade_gestora": "160001",
    "gestao": "00001",
}

ONDE_VALE_GLOBAL = "CE, NL, PP, OB e download dos documentos"


# ============================================================ CE

# Combo #cmbCdTipoDocumento da tela "Manter Despesa Certificada".
TIPOS_DOCUMENTO_CE = {
    "6": "Aviso Débito Banco",
    "8": "Bloquete",
    "11": "C.I/Ofício",
    "9": "Contrato",
    "13": "Cupom Fiscal",
    "14": "DARE",
    "16": "DARF",
    "5": "Diam/Orc. FRM",
    "7": "Fatura",
    "15": "GRU",
    "1": "Nota Fiscal",
    "2": "Nota Fiscal Avulsa",
    "12": "Nota Fiscal Eletrônica",
    "4": "Nota Fiscal Produtor",
    "3": "Nota Fiscal Serviço",
    "99": "Outros",
    "10": "Processo",
}

# Com estes tipos o SIGEF só gera a CE se Subsérie, Série e Modelo
# estiverem preenchidos.
TIPOS_NOTA_FISCAL = {"1", "2", "12", "4", "3"}

# Combo #cboMesComp (competência) -- tem o 13 (Décimo Terceiro).
MESES = {
    "1": "Janeiro", "2": "Fevereiro", "3": "Março", "4": "Abril", "5": "Maio", "6": "Junho",
    "7": "Julho", "8": "Agosto", "9": "Setembro", "10": "Outubro", "11": "Novembro",
    "12": "Dezembro", "13": "Décimo Terceiro",
}

# Tamanho máximo de cada campo no SIGEF (maxlength do HTML).
TAMANHO_MAXIMO = {"nf_subserie": 7, "nf_serie": 7, "nf_modelo": 20}

# Credor: detectado sozinho pelo {cnpj_cpf} do processo (14 dígitos = CNPJ,
# 11 = CPF) -- não é configurável.
CREDOR_CNPJ, CREDOR_CPF = "cnpj", "cpf"

# Nº do Documento: sempre "{programa}/{ano}" (o Programa digitado no menu
# de dados do processo) -- não é configurável.
NUMERO_DOCUMENTO_CE = "{programa}/{ano}"

OBSERVACAO_PADRAO = (
    "Regularização da {parcela} do {programa} Em favor de {escola}, "
    "localizado no município de {municipio}, referente ao processo {processo}."
)

PADRAO_CE = {
    "tipo_documento": "6",          # Aviso Débito Banco
    "nf_subserie": "",
    "nf_serie": "",
    "nf_modelo": "",
    # As três datas da CE -- cada uma: "" = data de hoje; senão "dd/mm/aaaa".
    "data_aceite": "",              # #txtDtAceite_SIGEFData
    "data_apresentacao": "",        # #txtDtApresentacao_SIGEFData
    "data_emissao": "",             # #txtDtEmissao_SIGEFData
    "observacao": OBSERVACAO_PADRAO,
}

# As datas da CE: chave da configuração, rótulo e campo do SIGEF.
DATAS_CE = (
    ("data_aceite", "Data de Aceite", "#txtDtAceite_SIGEFData"),
    ("data_apresentacao", "Data de Apresentação", "#txtDtApresentacao_SIGEFData"),
    ("data_emissao", "Data de Emissão", "#txtDtEmissao_SIGEFData"),
)

CAMPOS_MODELO = {
    "processo", "programa", "parcela", "escola", "municipio",
    "ano", "mes", "mes_nome", "cnpj_cpf", "valor_total",
}

# ============================================================ NL / PP / OB (em breve)

# Valores que as etapas usam HOJE, fixos no código. Só são mostrados no
# submenu de cada uma, até virarem configuráveis como a CE.
VALORES_FIXOS = {
    "nl": [
        ("Unidade Gestora / Gestão", "as do Global"),
        ("Data de vencimento", "data de hoje"),
        ("Retenções", "sem retenção (confirma direto)"),
    ],
}

NOMES_ETAPAS = {
    "ce": "CE  - Despesa Certificada",
    "nl": "NL  - Nota de Liquidação",
    "pp": "PP  - Preparação de Pagamento",
    "ob": "OB  - Ordem Bancária",
}


# ============================================================ arquivo


def _ler_arquivo() -> dict:
    if not os.path.exists(CAMINHO_CONFIG):
        return {}
    try:
        with open(CAMINHO_CONFIG, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _gravar(tudo: dict) -> None:
    caminhos.garantir_pasta(CAMINHO_CONFIG)
    gravar_json(CAMINHO_CONFIG, tudo)


def config_ce() -> dict:
    """A configuração da CE: o padrão, com o que o usuário alterou por cima."""
    salvo = dict(_ler_arquivo().get("ce") or {})
    # Versão anterior: uma data só para as três ("data_documento").
    antiga = salvo.pop("data_documento", None)
    if antiga:
        for chave, _rotulo, _seletor in DATAS_CE:
            salvo.setdefault(chave, antiga)
    config = dict(PADRAO_CE)
    config.update({chave: valor for chave, valor in salvo.items() if chave in PADRAO_CE})
    # Arquivo editado à mão com valor estranho: vira texto.
    for chave in PADRAO_CE:
        if not isinstance(config[chave], str):
            config[chave] = str(config[chave])
    # Unidade Gestora e Gestão vêm da configuração GLOBAL.
    return {**config_global(), **config}


def salvar_config_ce(config: dict) -> None:
    """Grava só o que é diferente do padrão (o resto segue o padrão do código)."""
    tudo = _ler_arquivo()
    tudo["ce"] = {chave: valor for chave, valor in config.items()
                  if chave in PADRAO_CE and valor != PADRAO_CE[chave]}
    _gravar(tudo)


def config_global() -> dict:
    """Unidade Gestora e Gestão de todas as etapas (padrão + o que foi alterado)."""
    salvo = _ler_arquivo().get("global") or {}
    config = dict(PADRAO_GLOBAL)
    config.update({chave: str(valor) for chave, valor in salvo.items() if chave in PADRAO_GLOBAL})
    return config


def salvar_config_global(config: dict) -> None:
    tudo = _ler_arquivo()
    tudo["global"] = {chave: valor for chave, valor in config.items()
                      if chave in PADRAO_GLOBAL and valor != PADRAO_GLOBAL[chave]}
    _gravar(tudo)


def gestao_sem_zeros(gestao: str) -> str:
    """'00001' -> '1' (o jeito que o SIGEF escreve a gestão na URL da PP)."""
    digitos = so_digitos(gestao)
    return str(int(digitos)) if digitos else ""


def problemas_global(config: dict = None) -> list[str]:
    config = config or config_global()
    problemas = []
    if not so_digitos(config.get("unidade_gestora")):
        problemas.append("Global: Unidade Gestora em branco.")
    if not so_digitos(config.get("gestao")):
        problemas.append("Global: Gestão em branco.")
    return problemas


def resumo_global(config: dict = None) -> str:
    config = config or config_global()
    alterados = sum(1 for chave in PADRAO_GLOBAL if config.get(chave) != PADRAO_GLOBAL[chave])
    return (f"UG {config['unidade_gestora']} | Gestão {config['gestao']} | "
            + ("padrão" if not alterados else f"{alterados} alteração(ões)"))


# ============================================================ regras da CE


def eh_nota_fiscal(config: dict) -> bool:
    return str(config.get("tipo_documento")) in TIPOS_NOTA_FISCAL


def nome_tipo_documento(codigo: str) -> str:
    return TIPOS_DOCUMENTO_CE.get(str(codigo), f"código {codigo} (desconhecido)")


def nome_mes(mes) -> str:
    return MESES.get(str(mes).strip().lstrip("0") or "0", "")


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def tipo_credor(cnpj_cpf: str) -> str | None:
    """
    "cnpj" ou "cpf" -- o caminho da busca do credor, decidido sozinho pelo
    número de dígitos do {cnpj_cpf} do processo (14 = CNPJ, 11 = CPF).
    None se não for nenhum dos dois.
    """
    digitos = len(so_digitos(cnpj_cpf))
    if digitos == 14:
        return CREDOR_CNPJ
    if digitos == 11:
        return CREDOR_CPF
    return None


def campos_do_modelo(modelo: str) -> set:
    """Os {campos} usados num modelo de texto."""
    try:
        return {nome for _texto, nome, _fmt, _conv in string.Formatter().parse(modelo or "") if nome}
    except ValueError:
        return {"(chave mal fechada)"}


def valores_do_modelo(dados: dict = None, processo: str = None) -> dict:
    dados = dados or {}
    mes = str(dados.get("mes_referencia") or "")
    return {
        "processo": processo or dados.get("processo") or "",
        "programa": dados.get("programa") or "",
        "parcela": dados.get("parcela") or "",
        "escola": dados.get("escola") or "",
        "municipio": dados.get("municipio") or "",
        "ano": str(date.today().year),
        "mes": mes,
        "mes_nome": nome_mes(mes),
        "cnpj_cpf": dados.get("cnpj_cpf") or "",
        "valor_total": dados.get("valor_total") or "",
    }


def preencher_modelo(modelo: str, dados: dict = None, processo: str = None) -> str:
    """Troca os {campos} pelos dados do processo; campo desconhecido fica como está."""
    valores = valores_do_modelo(dados, processo)

    def trocar(achado):
        nome = achado.group(1)
        return str(valores[nome]) if nome in valores else achado.group(0)

    return re.sub(r"\{([a-z_]+)\}", trocar, modelo or "")


def numero_documento_ce(dados: dict = None, processo: str = None) -> str:
    """Nº do Documento da CE: "{programa}/{ano}" com os dados do processo."""
    return preencher_modelo(NUMERO_DOCUMENTO_CE, dados, processo)


def data_ce(config: dict, chave: str = "data_emissao", hoje: date = None) -> str:
    """
    Uma das datas da CE (`chave`: data_aceite, data_apresentacao ou
    data_emissao), no formato que o SIGEF recebe (ddmmaaaa). Em branco =
    data de hoje.
    """
    fixa = (config.get(chave) or "").strip()
    if fixa:
        return datetime.strptime(fixa, "%d/%m/%Y").strftime("%d%m%Y")
    return (hoje or date.today()).strftime("%d%m%Y")


def problemas_ce(config: dict, dados: dict = None) -> list[str]:
    """
    O que impede a CE de ser gerada (ou a deixaria errada). Lista vazia =
    pronta. `dados` (do processo) é opcional: com eles, confere também o
    credor e o mês.
    """
    problemas = []
    if str(config.get("tipo_documento")) not in TIPOS_DOCUMENTO_CE:
        problemas.append(f"Tipo de Documento desconhecido ({config.get('tipo_documento')}).")

    if eh_nota_fiscal(config):
        for chave, rotulo in (("nf_subserie", "Subsérie"), ("nf_serie", "Série"), ("nf_modelo", "Modelo")):
            valor = (config.get(chave) or "").strip()
            if not valor:
                problemas.append(f"{rotulo} da Nota Fiscal em branco -- sem ela o SIGEF não gera a CE.")
            elif len(valor) > TAMANHO_MAXIMO[chave]:
                problemas.append(f"{rotulo} passa de {TAMANHO_MAXIMO[chave]} caracteres.")

    desconhecidos = campos_do_modelo(config.get("observacao") or "") - CAMPOS_MODELO
    if desconhecidos:
        problemas.append(f"Observação usa campo(s) que não existem: {', '.join(sorted(desconhecidos))}.")

    for chave, rotulo, _seletor in DATAS_CE:
        fixa = (config.get(chave) or "").strip()
        if fixa:
            try:
                datetime.strptime(fixa, "%d/%m/%Y")
            except ValueError:
                problemas.append(f"{rotulo} '{fixa}' inválida (use dd/mm/aaaa).")

    if dados:
        cnpj_cpf = dados.get("cnpj_cpf")
        if tipo_credor(cnpj_cpf) is None:
            problemas.append(
                f"CNPJ/CPF '{cnpj_cpf}' não tem 14 dígitos (CNPJ) nem 11 (CPF) -- "
                "corrija nos dados do processo."
            )
        if not (dados.get("programa") or "").strip():
            problemas.append("Programa em branco -- o Nº do Documento ({programa}/{ano}) ficaria vazio.")
        mes = str(dados.get("mes_referencia") or "")
        if mes and mes not in MESES:
            problemas.append(f"Mês de competência '{mes}' inválido (1 a 13).")
    return problemas


def resumo_ce(config: dict) -> str:
    """Uma linha -- usada no menu de configurações e na conferência dos dados."""
    partes = [nome_tipo_documento(config["tipo_documento"])]
    if eh_nota_fiscal(config):
        partes.append(f"Série {config.get('nf_serie') or '?'}")
    fixas = [f"{rotulo.split()[-1].lower()} {config[chave]}" for chave, rotulo, _s in DATAS_CE if config.get(chave)]
    if fixas:
        partes.append("datas: " + ", ".join(fixas))
    alterados = sum(1 for chave in PADRAO_CE if config.get(chave) != PADRAO_CE[chave])
    partes.append("tudo padrão" if not alterados else f"{alterados} alteração(ões)")
    return " | ".join(partes)


# ============================================================ PP

# Combo #cboTipoOrdemBancaria da tela "Preparação de Pagamento".
TIPOS_ORDEM_BANCARIA_PP = {
    "1": "Centralizada",
    "2": "Descentralizada",
    "3": "Regularização",
}

# Combo #cboTipoServico.
TIPOS_SERVICO_PP = {
    "10": "Crédito conta-corrente",
    "1": "Pagto não Corr",
    "5": "Pagto Quitação Docto Caixa",
    "6": "Pagto Quitação Eletrônica",
}

# Só o Crédito em conta-corrente usa o banco/agência configurados aqui;
# nos outros tipos de serviço essas duas opções nem aparecem no menu.
SERVICO_CREDITO_CONTA = "10"

PADRAO_PP = {
    "tipo_ordem_bancaria": "3",     # Regularização
    "tipo_servico": "10",           # Crédito conta-corrente
    "banco": "001",                 # #txtBanco
    "agencia": "2757-X",            # #txtAgencia
}


def config_pp() -> dict:
    """A configuração da PP: o padrão, com o que o usuário alterou por cima."""
    salvo = _ler_arquivo().get("pp") or {}
    config = dict(PADRAO_PP)
    config.update({chave: str(valor) for chave, valor in salvo.items() if chave in PADRAO_PP})
    # Unidade Gestora e Gestão vêm da configuração GLOBAL.
    return {**config_global(), **config}


def salvar_config_pp(config: dict) -> None:
    """Grava só o que é diferente do padrão (o resto segue o padrão do código)."""
    tudo = _ler_arquivo()
    tudo["pp"] = {chave: valor for chave, valor in config.items()
                  if chave in PADRAO_PP and valor != PADRAO_PP[chave]}
    _gravar(tudo)


def usa_conta_corrente(config: dict) -> bool:
    return str(config.get("tipo_servico")) == SERVICO_CREDITO_CONTA


def problemas_pp(config: dict, dados: dict = None) -> list[str]:
    """O que impede a PP de ser gerada. Lista vazia = pronta."""
    problemas = []
    if str(config.get("tipo_ordem_bancaria")) not in TIPOS_ORDEM_BANCARIA_PP:
        problemas.append(f"PP: Tipo de Ordem Bancária desconhecido ({config.get('tipo_ordem_bancaria')}).")
    if str(config.get("tipo_servico")) not in TIPOS_SERVICO_PP:
        problemas.append(f"PP: Tipo de Serviço desconhecido ({config.get('tipo_servico')}).")
    if usa_conta_corrente(config):
        if not (config.get("banco") or "").strip():
            problemas.append("PP: Banco em branco (Crédito conta-corrente precisa de banco).")
        if not (config.get("agencia") or "").strip():
            problemas.append("PP: Agência em branco (Crédito conta-corrente precisa de agência).")
        if dados is not None and not (dados.get("conta_pp") or "").strip():
            problemas.append("PP: Conta PP em branco nos dados do processo.")
    return problemas


def resumo_pp(config: dict) -> str:
    partes = [
        f"OB {TIPOS_ORDEM_BANCARIA_PP.get(config['tipo_ordem_bancaria'], config['tipo_ordem_bancaria'])}",
        TIPOS_SERVICO_PP.get(config["tipo_servico"], config["tipo_servico"]),
    ]
    if usa_conta_corrente(config):
        partes.append(f"banco {config['banco']} ag. {config['agencia']}")
    alterados = sum(1 for chave in PADRAO_PP if config.get(chave) != PADRAO_PP[chave])
    partes.append("tudo padrão" if not alterados else f"{alterados} alteração(ões)")
    return " | ".join(partes)


# ============================================================ OB

# Combo #cboTipoOB da tela "Manter Ordem Bancária".
TIPOS_OB = {
    "1": "Centralizada",
    "2": "Descentralizada",
    "3": "Regularização",
    "4": "Extra-Orçamentária",
}

# Combo #cboTipoPagamento.
TIPOS_PAGAMENTO_OB = {
    "1": "Específico",
    "2": "Diversos",
    "3": "Consignações/Retenções",
    "4": "Diárias",
}

OBSERVACAO_OB_PADRAO = "Regularização do valor pago na data de 01/07/2026 na conta do PROAFI"

PADRAO_OB = {
    "banco_origem": "001",          # txtBancoOrigem
    "agencia_origem": "2757-X",     # txtAgenciaOrigem
    "tipo_ob": "2",                 # Descentralizada
    "tipo_pagamento": "2",          # Diversos
    "fonte_recurso": "500001001",   # #txtFonte_SIGEFPesquisa (busca da PP)
    "observacao": OBSERVACAO_OB_PADRAO,
}


def config_ob() -> dict:
    """A configuração da OB: o padrão, com o que o usuário alterou por cima."""
    salvo = _ler_arquivo().get("ob") or {}
    config = dict(PADRAO_OB)
    config.update({chave: str(valor) for chave, valor in salvo.items() if chave in PADRAO_OB})
    # Unidade Gestora e Gestão vêm da configuração GLOBAL.
    return {**config_global(), **config}


def salvar_config_ob(config: dict) -> None:
    """Grava só o que é diferente do padrão (o resto segue o padrão do código)."""
    tudo = _ler_arquivo()
    tudo["ob"] = {chave: valor for chave, valor in config.items()
                  if chave in PADRAO_OB and valor != PADRAO_OB[chave]}
    _gravar(tudo)


def problemas_ob(config: dict, dados: dict = None) -> list[str]:
    """O que impede a OB de ser gerada. Lista vazia = pronta."""
    problemas = []
    if not (config.get("banco_origem") or "").strip():
        problemas.append("OB: Banco de origem em branco.")
    if not (config.get("agencia_origem") or "").strip():
        problemas.append("OB: Agência de origem em branco.")
    if str(config.get("tipo_ob")) not in TIPOS_OB:
        problemas.append(f"OB: Tipo de OB desconhecido ({config.get('tipo_ob')}).")
    if str(config.get("tipo_pagamento")) not in TIPOS_PAGAMENTO_OB:
        problemas.append(f"OB: Tipo de Pagamento desconhecido ({config.get('tipo_pagamento')}).")
    if not so_digitos(config.get("fonte_recurso")):
        problemas.append("OB: Fonte de recurso em branco.")
    if not (config.get("observacao") or "").strip():
        problemas.append("OB: Observação em branco.")
    desconhecidos = campos_do_modelo(config.get("observacao") or "") - CAMPOS_MODELO
    if desconhecidos:
        problemas.append(f"OB: Observação usa campo(s) que não existem: {', '.join(sorted(desconhecidos))}.")
    if dados is not None and not (dados.get("conta_ob") or "").strip():
        problemas.append("OB: Conta OB em branco nos dados do processo.")
    return problemas


def resumo_ob(config: dict) -> str:
    partes = [
        TIPOS_OB.get(config["tipo_ob"], config["tipo_ob"]),
        f"pagto {TIPOS_PAGAMENTO_OB.get(config['tipo_pagamento'], config['tipo_pagamento'])}",
        f"origem {config['banco_origem']} ag. {config['agencia_origem']}",
        f"fonte {config['fonte_recurso']}",
    ]
    alterados = sum(1 for chave in PADRAO_OB if config.get(chave) != PADRAO_OB[chave])
    partes.append("tudo padrão" if not alterados else f"{alterados} alteração(ões)")
    return " | ".join(partes)




# ============================================================ tabelas da tela "Configurações"
#
# formulario() monta, para o aplicativo, uma tabela por automação:
#     {"chave", "titulo", "descricao", "campos": [...], "automaticos": [...],
#      "problemas": [...], "resumo", "editavel", "alterados", "valores_modelo"}
# Cada campo: {"chave", "rotulo", "tipo" (lista | texto | data | modelo),
#     "valor", "padrao", "padrao_texto", "opcoes": [[valor, rótulo]],
#     "maximo", "ajuda", "mostrar_se": {"campo", "valores"}}
# salvar_secao() confere e grava o que voltar da tela.


class ErroNasConfiguracoes(ValueError):
    """Algum valor da tabela não pode ser gravado. `erros` = {campo: mensagem}."""

    def __init__(self, erros: dict):
        self.erros = erros
        super().__init__("; ".join(erros.values()))


SECOES = ("global", "ce", "nl", "pp", "ob")
PADROES = {"global": PADRAO_GLOBAL, "ce": PADRAO_CE, "pp": PADRAO_PP, "ob": PADRAO_OB}


def _opcoes(tabela: dict, ordenar: bool = False, nota: dict = None) -> list:
    itens = sorted(tabela.items(), key=lambda item: item[1]) if ordenar else list(tabela.items())
    return [[codigo, f"{nome}{(nota or {}).get(codigo, '')}"] for codigo, nome in itens]


def _campo(chave, rotulo, tipo, config, padrao, opcoes=None, maximo=None, ajuda=None, mostrar_se=None):
    valor = str(config.get(chave) or "")
    if tipo == "lista":
        nomes = dict(opcoes)
        padrao_texto = nomes.get(padrao[chave], padrao[chave])
    elif tipo == "data":
        padrao_texto = padrao[chave] or "Data de hoje"
    elif tipo == "modelo":
        padrao_texto = "Texto padrão"
    else:
        padrao_texto = padrao[chave] or "(em branco)"
    return {"chave": chave, "rotulo": rotulo, "tipo": tipo, "valor": valor, "padrao": padrao[chave],
            "padrao_texto": padrao_texto, "opcoes": opcoes, "maximo": maximo, "ajuda": ajuda,
            "mostrar_se": mostrar_se, "alterado": valor != padrao[chave]}


def _automaticos_global() -> list:
    config = config_global()
    return [["Unidade Gestora", f"{config['unidade_gestora']} (do Global)"], ["Gestão", f"{config['gestao']} (do Global)"]]


def secao(chave: str, dados: dict = None, processo: str = None) -> dict:
    """A tabela de UMA automação (chave: global, ce, nl, pp ou ob)."""
    dados = dados or {}
    modelo = valores_do_modelo(dados, processo)
    if chave == "global":
        config = config_global()
        campos = [
            _campo("unidade_gestora", "Unidade Gestora", "texto", config, PADRAO_GLOBAL, maximo=6,
                   ajuda="Só números."),
            _campo("gestao", "Gestão", "texto", config, PADRAO_GLOBAL, maximo=5, ajuda="Só números."),
        ]
        return {"chave": "global", "sigla": "Global", "titulo": "Global — vale para todas as etapas",
                "descricao": f"Unidade Gestora e Gestão usadas na {ONDE_VALE_GLOBAL}.",
                "campos": campos, "automaticos": [], "problemas": problemas_global(config),
                "resumo": resumo_global(config), "editavel": True, "valores_modelo": modelo,
                "alterados": sum(1 for c in campos if c["alterado"])}
    if chave == "ce":
        config = config_ce()
        nf = {"mostrar_se": {"campo": "tipo_documento", "valores": sorted(TIPOS_NOTA_FISCAL)}}
        campos = [
            _campo("tipo_documento", "Tipo de Documento", "lista", config, PADRAO_CE,
                   opcoes=_opcoes(TIPOS_DOCUMENTO_CE, ordenar=True,
                                  nota={c: " (pede Subsérie, Série e Modelo)" for c in TIPOS_NOTA_FISCAL})),
            _campo("nf_subserie", "Subsérie da Nota Fiscal", "texto", config, PADRAO_CE,
                   maximo=TAMANHO_MAXIMO["nf_subserie"], ajuda="Obrigatória para Nota Fiscal.", **nf),
            _campo("nf_serie", "Série da Nota Fiscal", "texto", config, PADRAO_CE,
                   maximo=TAMANHO_MAXIMO["nf_serie"], ajuda="Obrigatória para Nota Fiscal.", **nf),
            _campo("nf_modelo", "Modelo da Nota Fiscal", "texto", config, PADRAO_CE,
                   maximo=TAMANHO_MAXIMO["nf_modelo"], ajuda="Obrigatório para Nota Fiscal.", **nf),
        ]
        campos += [_campo(chave_data, rotulo, "data", config, PADRAO_CE) for chave_data, rotulo, _s in DATAS_CE]
        campos.append(_campo("observacao", "Observação", "modelo", config, PADRAO_CE,
                             ajuda="Os {campos} são trocados pelos dados do processo."))
        tipo = tipo_credor(dados.get("cnpj_cpf"))
        automaticos = _automaticos_global() + [
            ["Credor", f"{tipo.upper()} {dados.get('cnpj_cpf')}" if tipo else "CNPJ ou CPF, conforme o processo"],
            ["Nº do Documento", numero_documento_ce(dados, processo) if dados.get("programa") else NUMERO_DOCUMENTO_CE + " (Programa do processo)"],
            ["Atestado receb./resp.", "sempre marcado"],
            ["Mês de competência", f"{dados.get('mes_referencia')} - {nome_mes(dados.get('mes_referencia'))}"
             if dados.get("mes_referencia") else "o Mês de referência do processo"],
        ]
        return {"chave": "ce", "sigla": "CE", "titulo": "CE — Despesa Certificada",
                "descricao": "Feita uma vez por processo, com o Valor Total.",
                "campos": campos, "automaticos": automaticos, "problemas": problemas_ce(config, dados or None),
                "resumo": resumo_ce(config), "editavel": True, "valores_modelo": modelo,
                "campos_modelo": sorted(CAMPOS_MODELO),
                "alterados": sum(1 for c in campos if c["alterado"])}
    if chave == "nl":
        return {"chave": "nl", "sigla": "NL", "titulo": "NL — Nota de Liquidação",
                "descricao": "Ainda usa os valores fixos do programa. A configuração chega numa próxima versão.",
                "campos": [], "automaticos": [[rotulo, valor] for rotulo, valor in VALORES_FIXOS["nl"]],
                "problemas": [], "resumo": "Valores fixos", "editavel": False, "valores_modelo": modelo,
                "alterados": 0}
    if chave == "pp":
        config = config_pp()
        conta = {"mostrar_se": {"campo": "tipo_servico", "valores": [SERVICO_CREDITO_CONTA]}}
        campos = [
            _campo("tipo_ordem_bancaria", "Tipo de Ordem Bancária", "lista", config, PADRAO_PP,
                   opcoes=_opcoes(TIPOS_ORDEM_BANCARIA_PP)),
            _campo("tipo_servico", "Tipo de Serviço", "lista", config, PADRAO_PP,
                   opcoes=_opcoes(TIPOS_SERVICO_PP, nota={SERVICO_CREDITO_CONTA: " (pede Banco e Agência)"})),
            _campo("banco", "Banco", "texto", config, PADRAO_PP, ajuda="Aceita letras, números e símbolos.", **conta),
            _campo("agencia", "Agência", "texto", config, PADRAO_PP, ajuda="Ex: 2757-X", **conta),
        ]
        automaticos = _automaticos_global() + [
            ["Conta", (dados.get("conta_pp") or "a Conta PP do processo") + " (Conta PP dos dados do processo)"],
        ]
        return {"chave": "pp", "sigla": "PP", "titulo": "PP — Preparação de Pagamento",
                "descricao": "Uma por lançamento.",
                "campos": campos, "automaticos": automaticos,
                "problemas": problemas_pp(config, dados if dados else None),
                "resumo": resumo_pp(config), "editavel": True, "valores_modelo": modelo,
                "alterados": sum(1 for c in campos if c["alterado"])}
    if chave == "ob":
        config = config_ob()
        campos = [
            _campo("tipo_ob", "Tipo de OB", "lista", config, PADRAO_OB, opcoes=_opcoes(TIPOS_OB)),
            _campo("tipo_pagamento", "Tipo de Pagamento", "lista", config, PADRAO_OB, opcoes=_opcoes(TIPOS_PAGAMENTO_OB)),
            _campo("banco_origem", "Banco de origem", "texto", config, PADRAO_OB),
            _campo("agencia_origem", "Agência de origem", "texto", config, PADRAO_OB, ajuda="Ex: 2757-X"),
            _campo("fonte_recurso", "Fonte de recurso", "texto", config, PADRAO_OB, ajuda="Só números."),
            _campo("observacao", "Observação", "modelo", config, PADRAO_OB,
                   ajuda="Os {campos} são trocados pelos dados do processo."),
        ]
        automaticos = _automaticos_global() + [
            ["Conta de origem", (dados.get("conta_ob") or "a Conta OB do processo") + " (Conta OB dos dados do processo)"],
            ["Data de referência", "data de hoje"],
            ["Id Uso", "1"],
        ]
        return {"chave": "ob", "sigla": "OB", "titulo": "OB — Ordem Bancária",
                "descricao": "Uma OB paga todas as PPs do processo.",
                "campos": campos, "automaticos": automaticos,
                "problemas": problemas_ob(config, dados if dados else None),
                "resumo": resumo_ob(config), "editavel": True, "valores_modelo": modelo,
                "campos_modelo": sorted(CAMPOS_MODELO),
                "alterados": sum(1 for c in campos if c["alterado"])}
    raise ValueError(f"Configuração desconhecida: {chave}")


def formulario(dados: dict = None, processo: str = None) -> list[dict]:
    """Todas as tabelas, na ordem da tela."""
    return [secao(chave, dados, processo) for chave in SECOES]


def _data_da_tela(texto: str) -> str:
    """'' (hoje), 'dd/mm/aaaa', 'ddmmaaaa' ou 'aaaa-mm-dd' (campo de data) -> '' ou 'dd/mm/aaaa'."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        texto = f"{texto[8:]}/{texto[5:7]}/{texto[:4]}"
    digitos = so_digitos(texto)
    if len(digitos) == 8 and "/" not in texto:
        texto = f"{digitos[:2]}/{digitos[2:4]}/{digitos[4:]}"
    datetime.strptime(texto, "%d/%m/%Y")      # ValueError se a data não existe
    return texto


def salvar_secao(chave: str, valores: dict) -> dict:
    """
    Confere e grava o que voltou da tabela `chave`. Campos que não vieram
    ficam como estavam. Lança ErroNasConfiguracoes com o erro de cada campo
    (nada é gravado nesse caso). Devolve a tabela atualizada.
    """
    if chave not in PADROES:
        raise ErroNasConfiguracoes({"_": "Esta configuração não pode ser alterada."})
    valores = {campo: ("" if valor is None else str(valor)).strip() for campo, valor in (valores or {}).items()
               if campo in PADROES[chave]}
    erros = {}

    def lista(campo, tabela, rotulo):
        if campo in valores and valores[campo] not in tabela:
            erros[campo] = f"{rotulo}: escolha uma das opções da lista."

    def modelo(campo):
        if campo in valores:
            if not valores[campo]:
                erros[campo] = "A observação não pode ficar em branco (use Voltar ao padrão)."
            desconhecidos = campos_do_modelo(valores[campo]) - CAMPOS_MODELO
            if desconhecidos:
                erros[campo] = "Campo(s) que não existem: " + ", ".join("{" + n + "}" for n in sorted(desconhecidos))

    if chave == "global":
        for campo, rotulo in (("unidade_gestora", "Unidade Gestora"), ("gestao", "Gestão")):
            if campo in valores:
                if not so_digitos(valores[campo]) or so_digitos(valores[campo]) != valores[campo]:
                    erros[campo] = f"{rotulo}: só números (não pode ficar em branco)."
        if not erros:
            salvar_config_global({**config_global(), **valores})
    elif chave == "ce":
        config = {**config_ce(), **valores}
        lista("tipo_documento", TIPOS_DOCUMENTO_CE, "Tipo de Documento")
        for campo, maximo in TAMANHO_MAXIMO.items():
            if len(config.get(campo) or "") > maximo:
                erros[campo] = f"No máximo {maximo} caracteres."
        for campo, rotulo, _seletor in DATAS_CE:
            if campo in valores:
                try:
                    config[campo] = _data_da_tela(valores[campo])
                except ValueError:
                    erros[campo] = f"{rotulo}: data inválida (use dd/mm/aaaa)."
        modelo("observacao")
        if not erros:
            salvar_config_ce(config)
    elif chave == "pp":
        lista("tipo_ordem_bancaria", TIPOS_ORDEM_BANCARIA_PP, "Tipo de Ordem Bancária")
        lista("tipo_servico", TIPOS_SERVICO_PP, "Tipo de Serviço")
        if not erros:
            salvar_config_pp({**config_pp(), **valores})
    elif chave == "ob":
        lista("tipo_ob", TIPOS_OB, "Tipo de OB")
        lista("tipo_pagamento", TIPOS_PAGAMENTO_OB, "Tipo de Pagamento")
        for campo, rotulo in (("banco_origem", "Banco de origem"), ("agencia_origem", "Agência de origem")):
            if campo in valores and not valores[campo]:
                erros[campo] = f"{rotulo} não pode ficar em branco."
        if "fonte_recurso" in valores and (not valores["fonte_recurso"] or so_digitos(valores["fonte_recurso"]) != valores["fonte_recurso"]):
            erros["fonte_recurso"] = "Fonte de recurso: só números."
        modelo("observacao")
        if not erros:
            salvar_config_ob({**config_ob(), **valores})
    if erros:
        raise ErroNasConfiguracoes(erros)
    return secao(chave)


def restaurar_padrao(chave: str) -> dict:
    """Volta uma automação inteira para o padrão do código."""
    if chave == "global":
        salvar_config_global(dict(PADRAO_GLOBAL))
    elif chave == "ce":
        salvar_config_ce(dict(PADRAO_CE))
    elif chave == "pp":
        salvar_config_pp(dict(PADRAO_PP))
    elif chave == "ob":
        salvar_config_ob(dict(PADRAO_OB))
    else:
        raise ErroNasConfiguracoes({"_": "Esta configuração não pode ser alterada."})
    return secao(chave)
