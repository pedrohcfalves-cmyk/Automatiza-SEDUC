"""
Os DADOS DO PROCESSO -- todos de uma vez, numa tabela só.

Antes o programa perguntava um dado por vez (CNPJ, município, escola...).
Agora a tela mostra uma TABELA com todos os campos já preenchidos com o
que foi usado da última vez, mais a tabela de LANÇAMENTOS (valor + nota de
empenho, com botões para adicionar e remover linhas e a soma conferida com
o Valor Total na hora). A pessoa confere, muda o que precisar e clica em
"Conferir os dados". Depois vem o quadro "Confira os dados" (com as
configurações da CE, PP e OB que vão ser usadas) e os botões:

    Começar no SIGEF      |   Corrigir os dados   |   Configurações

Usado pela Etapa SEI (1) de verdade (etapa_sei1.py) e pelo modo treino
(modo_treino.py) -- por isso não depende do Playwright.

Lançamento: cada parte em que o Valor Total foi dividido (1 a 20), com o
seu valor e a sua nota de empenho. Cada um vira 1 NL + 1 PP; no fim, UMA
OB paga todas as PPs. Numa RETOMADA (mesmo processo, programa parou no
meio), um lançamento que não mudou continua com as NL/PP/OB que já tinha
-- assim nada é feito em dobro.

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
from automacoes.anexar.automacao import configuracoes as cfg
from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.interacao import botao, campo
from automacoes.anexar.automacao.valores import normalizar, padronizar_mes, padronizar_valor, reais, so_digitos

MAX_LANCAMENTOS = 20

# chave, rótulo, tipo, exemplo, ajuda
CAMPOS = [
    ("cnpj_cpf", "CNPJ ou CPF", "texto", "03.508.155/0001-21", "Com ou sem pontos. O programa descobre se é CNPJ ou CPF."),
    ("municipio", "Município", "texto", "Porto Velho", None),
    ("escola", "Escola", "texto", "EEEF Nome da Escola", None),
    ("conta_pp", "Conta PP", "texto", "105805", None),
    ("conta_ob", "Conta OB", "texto", "105805", None),
    ("parcela", "Parcela", "texto", "7", "Só o número."),
    ("mes_referencia", "Mês de referência", "mes", None, "13 = Décimo Terceiro."),
    ("programa", "Programa", "texto", "PROAFI", None),
    ("valor_total", "Valor Total da parcela", "valor", "5.335,50", "É o valor da CE. Use vírgula nos centavos."),
]
ROTULOS = {chave: rotulo for chave, rotulo, *_ in CAMPOS}
OPCOES_MES = [[numero, f"{numero} - {nome}"] for numero, nome in cfg.MESES.items()]

EXPLICACAO = [
    "Confira cada linha com o processo aberto no SEI. O que está preenchido é o que foi usado da última vez.",
    "Mudou alguma coisa? É só apagar e escrever por cima. Depois clique em “Conferir os dados”.",
]
EXPLICACAO_LANCAMENTOS = (
    "Cada lançamento é uma parte do Valor Total, com o seu valor e a sua nota de empenho (NE). "
    "Se o valor não foi dividido, deixe um lançamento só, com o Valor Total inteiro."
)


# ============================================================ tabela para preencher


def valores_iniciais(sessao: dict) -> dict:
    return {chave: str(sessao.get(chave) or "") for chave, *_ in CAMPOS}


def lancamentos_iniciais(sessao: dict) -> list[dict]:
    return [{"valor": str(item.get("valor") or ""), "nota_de_empenho": str(item.get("nota_de_empenho") or "")}
            for item in (sessao.get("lancamentos") or [])]


def pedido_dados(processo: str, valores: dict, lancamentos: list[dict], anteriores: dict = None,
                 erros: dict = None, treino: bool = False) -> dict:
    """Os argumentos de interacao.preencher() para a tabela dos dados do processo."""
    anteriores = anteriores or {}
    campos = []
    for chave, rotulo, tipo, exemplo, ajuda in CAMPOS:
        campos.append(campo(
            chave, rotulo, tipo, valor=valores.get(chave, ""), anterior=anteriores.get(chave) or None,
            exemplo=exemplo, ajuda=ajuda, opcoes=OPCOES_MES if tipo == "mes" else None,
        ))
    return {
        "titulo": "Dados do processo",
        "linhas": EXPLICACAO,
        "processo": processo,
        "campos": campos,
        "erros": erros or {},
        "lancamentos": {
            "itens": lancamentos or [{"valor": "", "nota_de_empenho": ""}],
            "maximo": MAX_LANCAMENTOS,
            "campo_total": "valor_total",
            "explicacao": EXPLICACAO_LANCAMENTOS,
        },
        "botoes": [botao("conferir", "Conferir os dados", "principal", "check")],
        "treino": treino,
    }


def validar(valores: dict, digitados: list[dict], salvos: list[dict] = None) -> tuple[dict | None, dict]:
    """
    Confere tudo o que foi preenchido. Devolve (dados, {}) quando está certo,
    ou (None, erros) -- erros = {chave: mensagem}; para os lançamentos,
    "lancamentos" (geral) e "lancamentos.N.valor" / "lancamentos.N.nota_de_empenho".
    """
    erros = {}
    dados = {}
    for chave, rotulo, *_ in CAMPOS:
        texto = str(valores.get(chave) or "").strip()
        dados[chave] = texto
        if not texto:
            erros[chave] = f"Preencha {rotulo.lower() if chave != 'cnpj_cpf' else 'o CNPJ ou CPF'}."

    if dados["cnpj_cpf"] and len(so_digitos(dados["cnpj_cpf"])) not in (11, 14):
        erros["cnpj_cpf"] = "Precisa ter 14 números (CNPJ) ou 11 números (CPF)."
    if dados["mes_referencia"]:
        try:
            dados["mes_referencia"] = padronizar_mes(dados["mes_referencia"])
        except ValueError:
            erros["mes_referencia"] = "Escolha um mês de 1 a 12 (ou 13 = Décimo Terceiro)."
    if dados["valor_total"]:
        try:
            dados["valor_total_padronizado"], dados["valor_total"] = padronizar_valor(dados["valor_total"])
        except ValueError:
            erros["valor_total"] = "Valor inválido. Exemplo: 5.335,50"

    linhas = [item for item in (digitados or []) if (item.get("valor") or item.get("nota_de_empenho"))]
    if not linhas:
        erros["lancamentos"] = "Coloque pelo menos um lançamento (valor e nota de empenho)."
    elif len(linhas) > MAX_LANCAMENTOS:
        erros["lancamentos"] = f"No máximo {MAX_LANCAMENTOS} lançamentos por processo."

    salvos = list(salvos or [])
    lancamentos = []
    for indice, item in enumerate(linhas):
        valor_texto = str(item.get("valor") or "").strip()
        empenho = str(item.get("nota_de_empenho") or "").strip()
        padronizado = formatado = None
        if not valor_texto:
            erros[f"lancamentos.{indice}.valor"] = "Preencha o valor."
        else:
            try:
                padronizado, formatado = padronizar_valor(valor_texto)
                if padronizado == "0":
                    erros[f"lancamentos.{indice}.valor"] = "O valor não pode ser zero."
            except ValueError:
                erros[f"lancamentos.{indice}.valor"] = "Valor inválido. Exemplo: 1.105,50"
        if not empenho:
            erros[f"lancamentos.{indice}.nota_de_empenho"] = "Preencha a nota de empenho."
        novo = {"valor": formatado or valor_texto, "valor_padronizado": padronizado, "nota_de_empenho": empenho}
        # Retomada: a mesma linha de antes (mesmo valor e mesma NE) continua
        # com o que já foi feito para ela (NL, PP, OB, documentos).
        if indice < len(salvos):
            antigo = salvos[indice]
            if str(antigo.get("valor_padronizado")) == str(padronizado) and \
                    str(antigo.get("nota_de_empenho")).strip() == empenho:
                novo = {**antigo, **novo}
        lancamentos.append(novo)

    if erros:
        return None, erros
    dados["lancamentos"] = lancamentos
    return dados, {}


# ============================================================ soma dos lançamentos


def comparar_total(lancamentos: list[dict], valor_total: str) -> dict:
    """{"tipo": ok|falta|passou, "soma": "1.000,00", "texto": ...}"""
    soma = sum(normalizar(item["valor"]) for item in lancamentos if item.get("valor"))
    total = normalizar(valor_total) if valor_total else 0.0
    if soma < total - 0.005:
        return {"tipo": "falta", "soma": reais(soma),
                "texto": f"Falta lançar R$ {reais(total - soma)} para chegar ao Valor Total (R$ {reais(total)})."}
    if soma > total + 0.005:
        return {"tipo": "passou", "soma": reais(soma),
                "texto": f"A soma passou R$ {reais(soma - total)} do Valor Total (R$ {reais(total)}). Confira!"}
    return {"tipo": "ok", "soma": reais(soma), "texto": f"Confere com o Valor Total (R$ {reais(total)})."}


# ============================================================ "Confira os dados"


def situacao_das_configuracoes(dados: dict) -> list[dict]:
    """O que cada configuração vai usar, e o que impede de gerar (problemas)."""
    config_ce, config_pp, config_ob = cfg.config_ce(), cfg.config_pp(), cfg.config_ob()
    return [
        {"secao": "global", "titulo": "Global (UG e Gestão)", "resumo": cfg.resumo_global(),
         "problemas": cfg.problemas_global()},
        {"secao": "ce", "titulo": "CE — Despesa Certificada", "resumo": cfg.resumo_ce(config_ce),
         "problemas": cfg.problemas_ce(config_ce, dados)},
        {"secao": "pp", "titulo": "PP — Preparação de Pagamento", "resumo": cfg.resumo_pp(config_pp),
         "problemas": cfg.problemas_pp(config_pp, dados)},
        {"secao": "ob", "titulo": "OB — Ordem Bancária", "resumo": cfg.resumo_ob(config_ob),
         "problemas": cfg.problemas_ob(config_ob, dados)},
    ]


def pedido_conferencia(dados: dict, processo: str, treino: bool = False) -> dict:
    mes = str(dados.get("mes_referencia") or "")
    linhas_dados = [
        ["CNPJ/CPF", dados.get("cnpj_cpf")],
        ["Município", dados.get("municipio")],
        ["Escola", dados.get("escola")],
        ["Conta PP", dados.get("conta_pp")],
        ["Conta OB", dados.get("conta_ob")],
        ["Parcela", dados.get("parcela")],
        ["Mês de referência", f"{mes} - {cfg.nome_mes(mes)}" if mes else ""],
        ["Programa", dados.get("programa")],
        ["Valor Total (CE)", f"R$ {dados.get('valor_total')}"],
    ]
    lancamentos = dados.get("lancamentos") or []
    comparacao = comparar_total(lancamentos, dados.get("valor_total"))
    configuracoes = situacao_das_configuracoes(dados)
    problemas = [problema for item in configuracoes for problema in item["problemas"]]

    if problemas:
        seguir = botao("seguir", "Começar no SIGEF", "principal", "play", desabilitado=True,
                       ajuda="Antes, arrume o que está em amarelo (botão Configurações).")
    elif comparacao["tipo"] != "ok":
        seguir = botao("seguir", "A soma não bate — começar mesmo assim", "perigo", "alerta")
    else:
        seguir = botao("seguir", "Está tudo certo — começar no SIGEF", "principal", "play")
    aviso = ("É um treino: nada será feito no SEI nem no SIGEF." if treino else
             "Leia tudo com calma. Depois de “Começar”, o programa faz os documentos no SIGEF de verdade.")
    return {
        "titulo": "Confira os dados",
        "linhas": [aviso],
        "processo": processo,
        "dados": linhas_dados,
        "lancamentos": {
            "itens": [{"numero": numero, "valor": item["valor"], "nota_de_empenho": item["nota_de_empenho"]}
                      for numero, item in enumerate(lancamentos, start=1)],
            "comparacao": comparacao,
        },
        "configuracoes": configuracoes,
        "problemas": problemas,
        "tom": "atencao" if problemas or comparacao["tipo"] != "ok" else "normal",
        "botoes": [
            seguir,
            botao("corrigir", "Corrigir os dados", "normal", "voltar"),
            botao("configurar", "Configurações (CE, PP, OB)", "normal", "engrenagem"),
        ],
        "treino": treino,
    }


# ============================================================ a conversa inteira


def coletar(processo: str, sessao: dict, treino: bool = False) -> dict:
    """
    Tabela dos dados -> "Confira os dados" -> (Corrigir / Configurações) ...
    até a pessoa clicar em Começar. Devolve os dados confirmados (com
    valor_total_padronizado e os lançamentos já padronizados).
    """
    anteriores = valores_iniciais(sessao)
    valores = dict(anteriores)
    digitados = lancamentos_iniciais(sessao)
    salvos = list(sessao.get("lancamentos") or [])
    erros = {}
    while True:
        resposta = interacao.preencher(**pedido_dados(processo, valores, digitados, anteriores, erros, treino))
        valores = {chave: resposta["valores"].get(chave, valores.get(chave, "")) for chave, *_ in CAMPOS}
        if resposta["lancamentos"] is not None:
            digitados = resposta["lancamentos"]
        dados, erros = validar(valores, digitados, salvos)
        if erros:
            print("⚠️  Falta arrumar: " + "; ".join(f"{_nome_do_erro(chave)}: {msg}" for chave, msg in erros.items()))
            continue

        while True:
            escolha = interacao.conferir(pedido_conferencia(dados, processo, treino))
            if escolha == "configurar":
                interacao.abrir_configuracoes(None, "Configurações das automações", [
                    "Ajuste o que precisar e clique em Salvar. Depois, clique em “Voltar para o processo”.",
                ])
                continue
            break
        if escolha == "seguir":
            return dados
        # "corrigir": volta para a tabela com o que já foi preenchido.
        valores = {chave: str(dados.get(chave) or "") for chave, *_ in CAMPOS}
        digitados = [{"valor": item["valor"], "nota_de_empenho": item["nota_de_empenho"]} for item in dados["lancamentos"]]
        print("🔄 Corrigindo os dados.")


def _nome_do_erro(chave: str) -> str:
    if chave.startswith("lancamentos."):
        _, numero, parte = chave.split(".")
        return f"lançamento {int(numero) + 1} ({'valor' if parte == 'valor' else 'nota de empenho'})"
    return ROTULOS.get(chave, "lançamentos")
