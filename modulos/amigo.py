"""
==============================================================================
SISTEMA DE AUTOMAÇÕES SIGEF
==============================================================================
Aplicação de automação em Python, inspirada em fluxos do Power Automate
Desktop, utilizando:

    - Playwright  -> automações web (navegador)
    - pywin32     -> leitura/escrita no Excel (via COM), controlando o
                      próprio Microsoft Excel aberto na tela do usuário

Este arquivo junta, em um único lugar, tudo o que o sistema faz. Para
facilitar a leitura, ele está dividido nas seções abaixo, sempre nesta
ordem:

    1.  LOG AMIGÁVEL
    2.  CONFIGURAÇÕES (config.json, constantes, colunas da planilha)
    3.  EXCEL (pywin32/COM) - conectar, ler e gravar no arquivo Excel
    4.  PLAYWRIGHT - UTILIDADES GENÉRICAS (conexão via CDP)
    5.  UTILIDADES DE NEGÓCIO (conversão de identificadores e valores)
    6.  AUTOMAÇÕES (esqueletos, a implementar)
    7.  EXECUTOR DINÂMICO (dicionário PROGRAMAS)
    8.  MENUS (principal e de programas)
    9.  PONTO DE ENTRADA

==============================================================================
REVISÃO: MIGRAÇÃO GOOGLE SHEETS -> EXCEL + NOVOS PROGRAMAS
==============================================================================
Esta revisão faz duas mudanças principais em relação à versão anterior:

1. Todas as automações antigas (Regularização, Ordem Bancária, GR,
   Confirmar OB, Cancelar PP/OB, variantes "Suprimento" etc.) foram
   REMOVIDAS. Em seu lugar entram 9 automações novas, ainda vazias
   (esqueletos prontos para você programar), com os números e nomes:

        1  - CE
        2  - Raspar CE
        3  - NL
        4  - Raspar NL
        5  - PP
        6  - Raspar PP
        7  - Raspar contas
        8  - Gerar OB
        9  - Raspar OB
        10 - Confirmar OB

   (o número 9 foi propositalmente deixado livre, conforme solicitado).

2. Toda a integração que antes usava Google Sheets (gspread) foi
   substituída por integração com Excel via COM (biblioteca `pywin32`).
   Isso significa que a automação controla o próprio Microsoft Excel
   aberto na tela: o arquivo .xlsx é aberto (ou reaproveitado, se você já
   estiver com ele aberto) de forma VISÍVEL, e cada escrita feita pela
   automação aparece IMEDIATAMENTE na tela, exatamente como acontecia com
   a planilha do Google Sheets ficando aberta no navegador enquanto era
   atualizada em tempo real. Não é mais necessário nenhum arquivo de
   credenciais (`credentials.json`) nem conta de serviço - basta ter o
   Microsoft Excel instalado no Windows.

   Instale a biblioteca nova com:
       pip install pywin32
==============================================================================
"""

import os
import re
import sys
import json
import time
import unicodedata
import traceback
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

# ---- Bibliotecas externas -------------------------------------------------
# pywin32 é necessário para controlar o Excel (COM). playwright é necessário
# para a automação web do SIGEF.
try:
    import win32com.client as win32
except ImportError:
    win32 = None

try:
    from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import Error as PlaywrightError
    from playwright._impl._errors import TargetClosedError
except ImportError:
    sync_playwright = None
    Page = None
    BrowserContext = None
    TargetClosedError = Exception
    PlaywrightTimeoutError = Exception
    PlaywrightError = Exception


# ==============================================================================
# 1. LOG AMIGÁVEL
# ==============================================================================

def log_info(mensagem: str):
    """Exibe uma mensagem informativa no terminal, com timestamp."""
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"ℹ️  [{agora}] {mensagem}")


def log_sucesso(mensagem: str):
    """Exibe uma mensagem de sucesso no terminal."""
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"✅ [{agora}] {mensagem}")


def log_erro(mensagem: str):
    """Exibe uma mensagem de erro no terminal."""
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"❌ [{agora}] {mensagem}")


def log_aviso(mensagem: str):
    """Exibe uma mensagem de aviso no terminal."""
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"⚠️  [{agora}] {mensagem}")

# ==============================================================================
# 2. CONFIGURAÇÕES (config.json, constantes, colunas da planilha)
# ==============================================================================

# ==============================================================================
# CAMINHOS
# ==============================================================================

# Na janela unificada (app_janela.py) a configuração fica na pasta de
# dados do programa, não ao lado do código (que, instalado, é só leitura).
BASE_DIR = os.environ.get("AMIGO_PASTA_DADOS") or os.path.dirname(os.path.abspath(__file__))
os.makedirs(BASE_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Configuração padrão utilizada caso ainda não exista config.json
CONFIG_PADRAO = {
    "data": "",                 # Ex: 30062026
    "processo": "",             # Ex: 0029.037004/2026-72
    "mes_referencia": "",       # Ex: 06/2026 (sempre o mês anterior!)
    "linha_inicial": 2,         # Ex: 37
    "caminho_planilha": "",     # Ex: C:\\Pasta\\SIGEF\\controle.xlsx
    "aba_planilha": "",         # Nome da aba (opcional; se vazio, usa a 1ª aba)
}

# ==============================================================================
# AMBIENTE SIGEF (HOMOLOGAÇÃO / PRODUÇÃO)
# ==============================================================================
# ATENÇÃO: este domínio aponta para o ambiente de PRODUÇÃO do SIGEF -
# tudo o que a automação fizer tem efeito real. É o ÚNICO lugar do
# sistema que precisa ser alterado
# para trocar de ambiente - todas as URLs e verificações de aba usam esta
# constante.
#
#   Fase de testes  -> "sigefhom.sefin.ro.gov.br"   (homologação)
#   Fim dos testes  -> "sigef.sefin.ro.gov.br"      (ATUAL)

DOMINIO_SIGEF = "sigef.sefin.ro.gov.br"  # <-- ambiente de PRODUÇÃO

# ==============================================================================
# URLs DO SIGEF
# ==============================================================================
# Como as demais automações (NL, PP, OB) ainda serão programadas, deixe
# aqui as URLs de cada tela do SIGEF assim que você definir cada fluxo -
# por exemplo:
#
#   URL_NL_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/....aspx"
#   URL_PP_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/....aspx"
#   URL_OB_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/....aspx"

# Tela "Manter Despesa Certificada" (CE).
URL_CE_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/FINManterDespesaCertificada.aspx?CdTransacao=121"
MARCADOR_URL_CE = "FINManterDespesaCertificada"

# Tela "Listar Despesa Certificada Geral" (Raspar CE).
URL_RASPAR_CE_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/FINListarDespesaCertificadaGeral.aspx?CdTransacao=123"
MARCADOR_URL_RASPAR_CE = "FINListarDespesaCertificadaGeral"

# Tela "Liquidar Despesa Certificada" (NL).
URL_NL_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/FINLiquidarDespesaCertificada.aspx?CdTransacao=160"
MARCADOR_URL_NL = "FINLiquidarDespesaCertificada"

# Tela "Preparação Pagamento Despesa Empenhada" (PP).
URL_PP_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/FINPreparacaoPagamentoDespesaEmpenhada.aspx?CdTransacao=250"
MARCADOR_URL_PP = "FINPreparacaoPagamentoDespesaEmpenhada"

# Tela "Listar Preparação Pagamento Geral" (Raspar contas).
URL_RASPAR_CONTA_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/FINListarPreparacaoPagamentoGeral.aspx?CdTransacao=181"
MARCADOR_URL_RASPAR_CONTA = "FINListarPreparacaoPagamentoGeral"

# Tela "Manter Ordem Bancária" (Gerar OB, lote de 30 em 30, fluxo
# Descentralizada / Tipo de OB "2").
URL_OB_SIGEF = f"http://{DOMINIO_SIGEF}/SIGEF2026/FIN/FINManterOrdemBancaria.aspx?CdTransacao=214"
MARCADOR_URL_OB = "FINManterOrdemBancaria"

TIMEOUT_PADRAO_SIGEF = 30000  # 30s

# Espera curta para coisas que "podem ou não" acontecer - hoje só o popup do
# SIGEF que se fecha sozinho após a seleção do item. Curto de propósito: se o
# popup não fechar, `fechar_paginas()` termina o serviço sem custar 30s.
TIMEOUT_POPUP_FECHAR = 800  # 0,8s

# Espera (e repetições) do clique de seleção em grade de popup: o SIGEF às
# vezes engole o 1º clique e a tela principal continua sem o registro - o que
# depois fazia a comparação do domicílio bancário rodar com os dados errados.
TIMEOUT_CLIQUE_GRADE = 8000  # 8s por tentativa

# Espera pelo botão "Limpar". Curta de propósito: quando ele não está na tela,
# o certo é voltar (`#btnVoltar`) e tentar de novo, não ficar 30s parado.
TIMEOUT_BOTAO_LIMPAR = 5000  # 5s
TENTATIVAS_CLIQUE_GRADE = 3

# Tamanho do lote da automação "Gerar OB" (quantas linhas da planilha por
# OB) e trava de segurança contra loop infinito de paginação dentro de 1
# lote (ver `_montar_lote_ob`).
TAMANHO_LOTE_OB = 30
MAX_PAGINAS_LOTE_OB = 40

# Tipo de Ordem Bancária usado pela PP. Selecionado por VALUE (e não por
# índice): o <select> tem uma 1ª opção em branco, então qualquer mudança de
# ordem/opção no SIGEF alteraria silenciosamente a escolha feita por índice.
#   ""=(em branco)  1=Centralizada  2=Descentralizada  3=Regularização
TIPO_ORDEM_BANCARIA_PP = "2"  # Descentralizada

# ---- Regex pré-compiladas (compiladas 1 única vez, no import do módulo) --
REGEX_APENAS_DIGITOS = re.compile(r"\D")
REGEX_PREFIXO_DOCUMENTO = re.compile(r"^\d{4}(PP|OB|CE|NL|NE)")
# Usada pela PP para extrair o número gerado da mensagem de sucesso do SIGEF
# ("... O número gerado foi 2026PP039772.").
REGEX_DOCUMENTO_PP = re.compile(r"\d{4}PP\d+", re.IGNORECASE)
# Usada pela Gerar OB para extrair o número gerado da mensagem de sucesso
# do SIGEF ("... O número gerado foi 2026OB012345.").
REGEX_DOCUMENTO_OB = re.compile(r"\d{4}OB\d+", re.IGNORECASE)
# Todos os números soltos no texto de uma linha de grade (ex: de
# "2026NL065995" saem "2026" e "065995") - usada para identificar qual linha
# corresponde aos documentos da planilha.
REGEX_NUMEROS = re.compile(r"\d+")
# Célula de grade que É um valor monetário no padrão BR ("840,00",
# "1.260,50") - usada pela Raspar PP para não tentar converter em número
# células como "2026PP053126" ou o nome do favorecido.
REGEX_VALOR_BR = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")

# ==============================================================================
# COLUNAS DA PLANILHA
# ==============================================================================
# Estas constantes são apenas um PONTO DE PARTIDA (mesmo layout usado pelas
# automações antigas). Como CE, NL, PP e OB ainda serão programados, ajuste
# os números de coluna conforme o layout real de cada planilha/fluxo assim
# que definir os campos de cada automação.

# ---- Colunas de entrada (0-based, usadas para LER a lista devolvida por
# `ler_dados()`, ex: linha[COL_VALOR]) -----------------------------------
COL_DATA_PAGAMENTO = 1   # Coluna B
COL_CARTAO = 3           # Coluna D
COL_VALOR = 4            # Coluna E
COL_ESPERADO = 5         # Coluna F (ex: PP/CE/NL esperado, usado para localizar o registro certo)

# ---- Colunas de saída (base 1, usadas para ESCREVER com `worksheet.Cells`)
COL_GERADO = 6           # Coluna F (base 1) -> identificador gerado (CE/NL/PP/OB) grava aqui

# Coluna mínima (base 1) usada por `obter_proxima_coluna_livre()` para
# localizar a primeira coluna livre de uma linha, caso seja necessária.
COL_COLUNA_MINIMA = 8    # Coluna H

# Coluna (base 1) onde o resultado da conferência ("Confirmar OB") pode ser
# gravado, ex: "Validado" / "Valor divergente" / "OB divergente".
COL_STATUS_CONFIRMACAO = 13  # Coluna M

# ---- Colunas específicas da automação CE (base 0, usadas com `obter_celula`) --
COL_CE_CPF = 1      # Coluna B - CPF do credor
COL_CE_VALOR = 7    # Coluna H - valor do documento (será convertido para centavos)

# Coluna (base 1) onde o número da CE gerada é salvo, na mesma linha.
COL_CE_GERADA = 9   # Coluna I

# ---- Colunas específicas da automação NL (base 0, usadas com `obter_celula`) --
COL_NL_CE = 8       # Coluna I - número da CE já gerada (mesma coluna gravada pela CE/Raspar CE)
COL_NL_NE = 3       # Coluna D - número da Nota de Empenho vinculada

# Coluna (base 1) onde o número da NL gerada é salvo.
COL_NL_GERADA = 10  # Coluna J

# ---- Colunas específicas da automação PP (base 0, usadas com `obter_celula`) --
# Mapeamento definido junto com a automação PP - não alterar o layout da
# planilha nem o posicionamento destas colunas.
COL_PP_BANCO = 4    # Coluna E - Banco do domicílio bancário (ex: 1)
COL_PP_AGENCIA = 5  # Coluna F - Agência bancária (ex: 1178-9)
COL_PP_CONTA = 6    # Coluna G - Conta bancária (ex: 74.508-1)
COL_PP_CE = COL_NL_CE  # Coluna I - Despesa Certificada (mesma coluna lida pela NL)
COL_PP_NL = 9       # Coluna J - Nota de Lançamento gerada pela NL (COL_NL_GERADA em base 0)

# Coluna (base 1) onde o número da PP gerada é salvo. Quando o SIGEF recusa
# o lançamento (ex: "Saldo insuficiente..."), a mensagem devolvida por ele é
# gravada nesta MESMA coluna, para que a planilha mostre o motivo da falha.
COL_PP_GERADA = 11  # Coluna K

# ---- Colunas da automação Raspar PP -------------------------------------
# Entrada (base 0, usadas com `obter_celula`):
COL_RASPAR_PP_CPF = 1              # Coluna B - CPF do favorecido
COL_RASPAR_PP_VALOR = COL_CE_VALOR # Coluna H - valor usado para achar a PP na grade
COL_RASPAR_PP_CE = COL_NL_CE       # Coluna I - CE esperada
COL_RASPAR_PP_NL = COL_PP_NL       # Coluna J - NL esperada
# Saída: a PP raspada é gravada na MESMA coluna K usada pela automação PP
# (COL_PP_GERADA) - de propósito, para que as duas nunca gravem em lugares
# diferentes.

# Coluna (base 1) da mensagem de conferência da Raspar PP.
# ATENÇÃO - COLISÃO: as três constantes abaixo apontam para a coluna M:
#   COL_STATUS_CONFIRMACAO      (Confirmar OB, ainda não implementada)
#   COL_RASPAR_CONTA_RESULTADO  (Raspar contas)
#   COL_RASPAR_PP_OBSERVACAO    (Raspar PP)
# Rodar Raspar PP e depois Raspar contas SOBRESCREVE a mensagem da primeira.
# Se as duas precisarem coexistir na planilha, mova uma delas para outra
# coluna - basta alterar o número aqui, nada mais depende disso.
COL_RASPAR_PP_OBSERVACAO = 13      # Coluna M

# ---- Colunas da automação Raspar contas ---------------------------------
# Entrada (base 0, usadas com `obter_celula`):
# O CPF não é mais usado: a pesquisa passou a ser feita direto pelo número
# da PP (coluna K), sem o popup de favorecido.
COL_RASPAR_CONTA_VALOR = COL_CE_VALOR  # Coluna H - valor, usado para escolher
                                       # a linha certa quando a grade traz
                                       # mais de uma
COL_RASPAR_CONTA_PP = 10   # Coluna K  - PP já gerada (COL_PP_GERADA em base 0)
# O banco/agência/conta esperados são os MESMOS lidos pela automação PP
# (colunas E, F e G) - reaproveitados de propósito, para que as duas
# automações nunca comparem contra colunas diferentes.
COL_RASPAR_CONTA_BANCO = COL_PP_BANCO      # Coluna E
COL_RASPAR_CONTA_AGENCIA = COL_PP_AGENCIA  # Coluna F
COL_RASPAR_CONTA_CONTA = COL_PP_CONTA      # Coluna G

# Saída (base 1, usadas com `worksheet.Cells`):
# ATENÇÃO: a coluna M é a MESMA de COL_STATUS_CONFIRMACAO ("Confirmar OB").
# Como "Confirmar OB" ainda não está implementada, não há conflito hoje -
# mas ao programá-la, mova uma das duas para outra coluna.
COL_RASPAR_CONTA_RESULTADO = 13    # Coluna M - banco/agência/conta lidos do SIGEF
COL_RASPAR_CONTA_CONFERENCIA = 14  # Coluna N - "Igual" ou "Diferente"

# ---- Colunas da automação "Gerar OB" (lote de 30 em 30) -----------------
# Entrada (base 0, usadas com `obter_celula`): reaproveita as MESMAS
# colunas já lidas pela CE (valor) e pela Raspar contas (PP) - de
# propósito, para nunca comparar contra colunas diferentes das outras
# automações.
COL_OB_CPF = COL_CE_CPF                    # Coluna B - CPF do favorecido
COL_OB_VALOR = COL_CE_VALOR                # Coluna H - "Valor a Receber"
COL_OB_PP_ESPERADO = COL_RASPAR_CONTA_PP   # Coluna K - PP já gerada

# Saída (base 1, usada com `worksheet.Cells`): nº da OB gerada por este
# lote OU, se o item não foi localizado na grade, a mensagem explicando
# o motivo (mesma coluna para os dois casos, igual à COL_PP_GERADA).
COL_OB_GERADA = 12  # Coluna L


# ==============================================================================
# CARREGAR / SALVAR config.json
# ==============================================================================

def carregar_configuracoes() -> dict:
    """
    Carrega as configurações do arquivo config.json.
    Caso o arquivo não exista, cria um com valores padrão.
    """
    if not os.path.exists(CONFIG_PATH):
        salvar_configuracoes(CONFIG_PADRAO)
        return dict(CONFIG_PADRAO)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as arquivo:
            config = json.load(arquivo)
            # Garante que todas as chaves padrão existam (versões antigas do arquivo)
            for chave, valor in CONFIG_PADRAO.items():
                config.setdefault(chave, valor)
            return config
    except (json.JSONDecodeError, OSError) as erro:
        log_erro(f"Não foi possível ler config.json ({erro}). Recriando com valores padrão.")
        salvar_configuracoes(CONFIG_PADRAO)
        return dict(CONFIG_PADRAO)


def salvar_configuracoes(config: dict):
    """Salva o dicionário de configurações em config.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as arquivo:
            json.dump(config, arquivo, ensure_ascii=False, indent=4)
    except OSError as erro:
        log_erro(f"Falha ao salvar configurações: {erro}")


# ==============================================================================
# MENUS INTERATIVOS DE CONFIGURAÇÃO
# ==============================================================================

def configurar_parametros(config: dict) -> dict:
    """
    Menu interativo para o usuário informar/alterar:
    DATA, PROCESSO, MÊS REFERÊNCIA e LINHA INICIAL.
    O arquivo Excel (caminho/aba) é configurado separadamente em
    'alterar_planilha'.
    """
    print("\n🔧 CONFIGURAR PARÂMETROS")
    print("-" * 50)

    data = input(f"DATA (ex: 30062026) [{config.get('data') or 'vazio'}]: ").strip()
    if data:
        config["data"] = data

    processo = input(
        f"PROCESSO (ex: 0029.037004/2026-72) [{config.get('processo') or 'vazio'}]: "
    ).strip()
    if processo:
        config["processo"] = processo

    mes_referencia = input(
        f"MÊS REFERÊNCIA (ex: 06/2026 | Sempre o mês anterior!) [{config.get('mes_referencia') or 'vazio'}]: "
    ).strip()
    if mes_referencia:
        config["mes_referencia"] = mes_referencia

    linha_inicial = input(
        f"LINHA INICIAL DA LEITURA (ex: 37) [{config.get('linha_inicial')}]: "
    ).strip()
    if linha_inicial:
        if linha_inicial.isdigit():
            config["linha_inicial"] = int(linha_inicial)
        else:
            log_aviso("Linha inicial inválida. Mantendo valor anterior.")

    salvar_configuracoes(config)
    log_sucesso("Parâmetros atualizados com sucesso!")
    return config


def alterar_planilha(config: dict) -> dict:
    """Menu interativo para alterar o caminho do arquivo Excel e o nome da aba."""
    print("\n📊 ALTERAR ARQUIVO EXCEL")
    print("-" * 50)

    caminho_planilha = input(
        f"Caminho do arquivo .xlsx [{config.get('caminho_planilha') or 'vazio'}]: "
    ).strip().strip('"')
    if caminho_planilha:
        config["caminho_planilha"] = caminho_planilha

    aba_planilha = input(
        f"Nome da aba (opcional, deixe vazio para usar a 1ª aba) [{config.get('aba_planilha') or 'vazio'}]: "
    ).strip()
    if aba_planilha:
        config["aba_planilha"] = aba_planilha

    salvar_configuracoes(config)
    log_sucesso("Arquivo Excel atualizado com sucesso!")
    return config


def alterar_linha_inicial(config: dict) -> dict:
    """Menu interativo dedicado apenas à troca rápida da linha inicial."""
    print("\n🔢 ALTERAR LINHA INICIAL")
    print("-" * 50)

    linha_inicial = input(f"Nova linha inicial [{config.get('linha_inicial')}]: ").strip()
    if linha_inicial.isdigit():
        config["linha_inicial"] = int(linha_inicial)
        salvar_configuracoes(config)
        log_sucesso(f"Linha inicial alterada para {linha_inicial}.")
    else:
        log_aviso("Valor inválido. Nenhuma alteração foi feita.")

    return config


def exibir_configuracoes(config: dict):
    """Exibe as configurações atuais de forma organizada."""
    print("\n📋 CONFIGURAÇÕES ATUAIS")
    print("-" * 50)
    print(f"DATA .................: {config.get('data') or '(não definido)'}")
    print(f"PROCESSO .............: {config.get('processo') or '(não definido)'}")
    print(f"MÊS REFERÊNCIA .......: {config.get('mes_referencia') or '(não definido)'}")
    print(f"LINHA INICIAL ........: {config.get('linha_inicial')}")
    print(f"ARQUIVO EXCEL ........: {config.get('caminho_planilha') or '(não definido)'}")
    print(f"ABA ..................: {config.get('aba_planilha') or '(1ª aba)'}")
    print("-" * 50)


# ==============================================================================
# 3. EXCEL (pywin32/COM) - conectar, ler e gravar no arquivo Excel
# ==============================================================================
# Esta seção substitui a antiga integração com Google Sheets (gspread).
# A automação controla o próprio Microsoft Excel: abre (ou reaproveita, se
# já estiver aberto) o arquivo .xlsx de forma visível, e cada escrita feita
# aqui aparece imediatamente na tela do usuário - o mesmo comportamento que
# a planilha do Google tinha ao ficar aberta no navegador em tempo real.

XL_UP = -4162        # constante COM: Excel.Constants.xlUp
XL_TO_LEFT = -4159   # constante COM: Excel.Constants.xlToLeft


# ==============================================================================
# CONEXÃO
# ==============================================================================

def _obter_excel_em_execucao():
    """
    Tenta obter uma instância do Excel que já esteja aberta na tela do
    usuário (via GetActiveObject). Retorna None se nenhuma instância do
    Excel estiver rodando no momento.
    """
    if win32 is None:
        return None
    try:
        return win32.GetActiveObject("Excel.Application")
    except Exception:
        return None


def _localizar_pasta_de_trabalho_aberta(excel_app, caminho_planilha: str):
    """
    Procura, entre as pastas de trabalho já abertas na instância do Excel
    informada, uma cujo caminho completo corresponda a `caminho_planilha` -
    para reaproveitar o arquivo já aberto em vez de abri-lo de novo.
    """
    if excel_app is None or not caminho_planilha:
        return None

    caminho_normalizado = os.path.normcase(os.path.abspath(caminho_planilha))
    try:
        for pasta in excel_app.Workbooks:
            try:
                if os.path.normcase(os.path.abspath(pasta.FullName)) == caminho_normalizado:
                    return pasta
            except Exception:
                continue
    except Exception:
        pass
    return None


def conectar_planilha(config: dict):
    """
    Conecta ao arquivo Excel configurado, via COM (pywin32).

    Comportamento (equivalente ao antigo fluxo do Google Sheets, porém
    tudo em uma única etapa, já que aqui não existe distinção entre "abrir
    para visualizar" e "conectar para ler/escrever" - é o mesmo Excel):
        - Se o arquivo já estiver aberto em uma instância do Excel na tela
          do usuário, essa instância/aba é REAPROVEITADA (não abre de novo).
        - Caso contrário, abre uma nova instância do Excel, VISÍVEL, com o
          arquivo configurado.

    Requisitos:
        - Microsoft Excel instalado (Windows).
        - 'caminho_planilha' definido nas configurações.

    Retorna:
        worksheet (objeto COM Worksheet) em caso de sucesso, ou None em
        caso de erro.
    """
    if win32 is None:
        log_erro("A biblioteca 'pywin32' não está instalada.")
        log_info("Instale com: pip install pywin32")
        return None

    caminho_planilha = config.get("caminho_planilha")
    if not caminho_planilha:
        log_erro("Nenhum arquivo Excel configurado. Use a opção 'Alterar planilha' no menu.")
        return None

    if not os.path.exists(caminho_planilha):
        log_erro(f"Arquivo não encontrado: {caminho_planilha}")
        return None

    try:
        excel_app = _obter_excel_em_execucao()
        pasta = _localizar_pasta_de_trabalho_aberta(excel_app, caminho_planilha) if excel_app else None

        if pasta is None:
            if excel_app is None:
                excel_app = win32.Dispatch("Excel.Application")
            excel_app.Visible = True
            pasta = excel_app.Workbooks.Open(os.path.abspath(caminho_planilha))
            log_sucesso(f"Arquivo Excel aberto: {os.path.basename(caminho_planilha)}")
        else:
            excel_app.Visible = True
            log_sucesso(f"Reaproveitando arquivo Excel já aberto: {os.path.basename(caminho_planilha)}")

        aba_nome = config.get("aba_planilha")
        if aba_nome:
            worksheet = pasta.Worksheets(aba_nome)
        else:
            worksheet = pasta.Worksheets(1)

        worksheet.Activate()
        excel_app.WindowState = -4137  # xlMaximized: traz o Excel para frente, maximizado
        log_sucesso(f"Conectado à aba '{worksheet.Name}'.")
        return worksheet

    except Exception as erro:
        log_erro(f"Erro ao conectar ao arquivo Excel: {erro}")
        return None


def salvar_planilha(worksheet):
    """Salva a pasta de trabalho no disco (equivalente ao autosave da nuvem
    do Google Sheets, que não existe no Excel local)."""
    try:
        worksheet.Parent.Save()
    except Exception as erro:
        log_aviso(f"Não foi possível salvar o arquivo Excel automaticamente: {erro}")


# ==============================================================================
# LEITURA
# ==============================================================================

def obter_ultima_linha(worksheet) -> int:
    """Obtém a última linha preenchida da coluna A."""
    try:
        ultima_linha = worksheet.Cells(worksheet.Rows.Count, 1).End(XL_UP).Row
        if ultima_linha == 1 and not worksheet.Cells(1, 1).Value:
            ultima_linha = 0
        log_info(f"Última linha preenchida na coluna A: {ultima_linha}")
        return ultima_linha
    except Exception as erro:
        log_erro(f"Erro ao obter última linha: {erro}")
        return 0


def ler_dados(worksheet, linha_inicial: int):
    """
    Lê os dados da planilha, da 'linha_inicial' até a última linha
    preenchida, das colunas A até L.
    """
    if worksheet is None:
        log_erro("Worksheet inválida. Não é possível ler dados.")
        return []

    ultima_linha = obter_ultima_linha(worksheet)

    if ultima_linha < linha_inicial:
        log_aviso(
            f"A linha inicial ({linha_inicial}) é maior que a última linha "
            f"preenchida ({ultima_linha}). Nenhum dado será lido."
        )
        return []

    try:
        intervalo = f"A{linha_inicial}:L{ultima_linha}"
        valores = worksheet.Range(intervalo).Value  # tupla de tuplas (linhas x colunas)

        if valores is None:
            return []

        # Quando o intervalo tem uma única linha, o COM devolve uma tupla
        # simples em vez de uma tupla de tuplas - normaliza os dois casos.
        if not isinstance(valores[0], tuple):
            valores = (valores,)

        dados = [
            ["" if celula is None else celula for celula in linha]
            for linha in valores
        ]
        log_sucesso(f"{len(dados)} linha(s) lida(s) do intervalo {intervalo}.")
        return dados
    except Exception as erro:
        log_erro(f"Erro ao ler dados da planilha: {erro}")
        return []


def obter_celula(linha: List, indice: int) -> str:
    """
    Obtém o valor de uma célula pelo índice (base 0), retornando string vazia
    caso a linha não tenha células suficientes ou o valor seja vazio.

    Números lidos do Excel via COM vêm como `float` (ex: 18380.0), mesmo
    que a célula exiba só "18380" - quando o valor é um número inteiro,
    remove essa parte decimal espúria antes de converter para string
    (senão comandos como `.zfill(6)` não completam corretamente, já que
    "18380.0" já tem mais de 6 caracteres).
    """
    if indice < len(linha):
        valor = linha[indice]
        if valor is None:
            return ""
        if isinstance(valor, float) and valor.is_integer():
            valor = int(valor)
        return str(valor).strip()
    return ""


# ==============================================================================
# ESCRITA
# ==============================================================================
# Toda escrita no Excel passa por `executar_escrita_com_retentativa()` -
# caso o COM devolva um erro temporário (Excel ocupado processando outra
# chamada, por exemplo enquanto o usuário está com um menu aberto na
# interface), a escrita é retentada automaticamente em vez de a automação
# simplesmente falhar naquela linha.

def _e_erro_temporario_excel(erro: Exception) -> bool:
    """Detecta erros COM temporários do Excel (aplicativo ocupado), que
    costumam se resolver tentando de novo logo em seguida."""
    texto = str(erro)
    return (
        "Call was rejected by callee" in texto
        or "RPC_E_CALL_REJECTED" in texto
        or "-2147418111" in texto  # servidor COM ocupado
        or "-2146777998" in texto  # "message filter indicates..."
    )


def executar_escrita_com_retentativa(func_escrita, *args, max_tentativas: int = 6,
                                      espera_inicial: float = 1.0, **kwargs):
    """
    Executa uma escrita no Excel com retentativas e espera progressiva
    (backoff exponencial: 1s, 2s, 4s... até 10s) caso o Excel esteja
    momentaneamente ocupado (erro COM temporário).

    Qualquer outro tipo de erro (não relacionado a uma ocupação temporária)
    é repassado imediatamente, sem espera.
    """
    tentativa = 0
    espera = espera_inicial

    while True:
        try:
            return func_escrita(*args, **kwargs)
        except Exception as erro:
            if not _e_erro_temporario_excel(erro):
                raise

            tentativa += 1
            if tentativa >= max_tentativas:
                log_erro(
                    f"Excel ocupado após {tentativa} tentativa(s). Desistindo desta escrita."
                )
                raise

            log_aviso(
                f"Excel temporariamente ocupado (tentativa {tentativa}/{max_tentativas}). "
                f"Aguardando {espera:.0f}s antes de tentar novamente..."
            )
            time.sleep(espera)
            espera = min(espera * 2, 10)


def atualizar_status(worksheet, linha: int, coluna: int, status: str):
    """Atualiza uma célula específica (ex: coluna de status) com o valor informado."""
    if worksheet is None:
        log_erro("Worksheet inválida. Não é possível atualizar status.")
        return

    def _escrever():
        worksheet.Cells(linha, coluna).Value = status
        salvar_planilha(worksheet)

    try:
        executar_escrita_com_retentativa(_escrever)
        log_sucesso(f"Status da linha {linha} atualizado para '{status}'.")
    except Exception as erro:
        log_erro(f"Erro ao atualizar status da linha {linha}: {erro}")


def indice_para_letra_coluna(indice: int) -> str:
    """
    Converte um índice de coluna base 1 (1, 2, 3, ... 13, ...) para a
    letra correspondente no Excel (A, B, C, ... M, ...).
    """
    letras = ""
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def gravar_status_em_lote(worksheet, atualizacoes, coluna: int):
    """
    Grava vários status de uma só vez, em uma única transação (com
    `ScreenUpdating` desligado durante a escrita, para não piscar a tela a
    cada célula), e salva o arquivo apenas 1 vez ao final.

    Args:
        worksheet: aba (objeto COM Worksheet) já conectada.
        atualizacoes: lista de tuplas (numero_linha, valor_a_gravar).
        coluna: número da coluna (base 1) onde gravar, ex: COL_STATUS_CONFIRMACAO.
    """
    if worksheet is None:
        log_erro("Worksheet inválida. Não é possível gravar os status em lote.")
        return

    if not atualizacoes:
        log_aviso("Nenhuma atualização para gravar em lote.")
        return

    letra_coluna = indice_para_letra_coluna(coluna)

    def _gravar():
        aplicativo = worksheet.Application
        aplicativo.ScreenUpdating = False
        try:
            for numero_linha, valor in atualizacoes:
                worksheet.Cells(numero_linha, coluna).Value = valor
        finally:
            aplicativo.ScreenUpdating = True
        salvar_planilha(worksheet)

    try:
        executar_escrita_com_retentativa(_gravar)
        log_sucesso(
            f"{len(atualizacoes)} status gravado(s) na planilha (coluna {letra_coluna})."
        )
    except Exception as erro:
        log_erro(f"Erro ao gravar status em lote: {erro}")


def salvar_valor_gerado(worksheet, linha: int, coluna: int, valor: str, rotulo: str = "documento"):
    """
    Grava um identificador gerado pelo SIGEF (ex: número de CE, NL, PP ou
    OB) na planilha, na MESMA linha de onde vieram os dados que o
    originaram. Pensada para ser chamada assim que o SIGEF confirma a
    geração do documento, para que a planilha fique salva
    incrementalmente. O valor é gravado exatamente como veio do SIGEF
    (ex: "2026PP123456"), sem remover o prefixo.

    `rotulo` é usado apenas para deixar a mensagem de log mais clara (ex:
    "PP", "OB", "CE", "NL").
    """
    if worksheet is None:
        log_erro(f"Worksheet inválida. Não é possível salvar o(a) {rotulo} gerado(a).")
        return

    def _escrever():
        worksheet.Cells(linha, coluna).Value = valor
        salvar_planilha(worksheet)

    try:
        executar_escrita_com_retentativa(_escrever)
        letra_coluna = indice_para_letra_coluna(coluna)
        log_sucesso(f"{rotulo} '{valor}' salvo(a) na planilha (linha {linha}, coluna {letra_coluna}).")
    except Exception as erro:
        log_erro(f"Erro ao salvar {rotulo} '{valor}' na linha {linha}: {erro}")


def obter_proxima_coluna_livre(worksheet, linha: int, coluna_minima: int = COL_COLUNA_MINIMA) -> int:
    """
    Descobre a primeira coluna livre (vazia) na linha informada, a partir
    de `coluna_minima`, para gravar um novo valor sem sobrescrever nenhuma
    coluna já usada por outra automação.
    """
    try:
        if not worksheet.Cells(linha, 1).Value:
            return coluna_minima
        ultima_coluna_preenchida = worksheet.Cells(linha, worksheet.Columns.Count).End(XL_TO_LEFT).Column
        return max(ultima_coluna_preenchida + 1, coluna_minima)
    except Exception as erro:
        log_erro(f"Erro ao localizar coluna livre na linha {linha}: {erro}")
        return coluna_minima


# ==============================================================================
# 4. PLAYWRIGHT - UTILIDADES GENÉRICAS (conexão via CDP)
# ==============================================================================
# Reaproveitadas por qualquer automação do SIGEF que você programar nas
# seções seguintes (CE, NL, PP, OB) - nenhuma mudança em relação à versão
# anterior, já que são independentes da fonte de dados (Google Sheets ou
# Excel).

def iniciar_navegador():
    """
    Inicia um navegador novo via Playwright (não depende de um Chrome já
    aberto). Retorna (playwright, browser, page) para que o chamador possa
    controlar o ciclo de vida (e fechar corretamente ao final).

    Uso típico:
        pw, browser, page = iniciar_navegador()
        try:
            page.goto("https://sigef.exemplo.gov.br")
            ...
        finally:
            fechar_navegador(pw, browser)
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return None, None, None

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        log_sucesso("Navegador iniciado com sucesso.")
        return pw, browser, page
    except Exception as erro:
        log_erro(f"Erro ao iniciar o navegador: {erro}")
        return None, None, None


def fechar_navegador(pw, browser):
    """Fecha o navegador e encerra a instância do Playwright com segurança."""
    try:
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
        log_info("Navegador encerrado.")
    except Exception as erro:
        log_erro(f"Erro ao fechar o navegador: {erro}")


def conectar_navegador_sigef(playwright):
    """
    Conecta ao Chrome já aberto em modo de depuração (porta 9222). Todas as
    automações do SIGEF usam esta MESMA conexão, pois dependem do usuário
    já estar autenticado no SIGEF nesse Chrome. Deve ser chamada 1 única
    vez por execução.
    """
    try:
        browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
    except Exception:
        raise Exception(
            "Chrome em modo de depuração não encontrado.\n"
            "Abra o Chrome com:\n"
            "\"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" "
            "--remote-debugging-port=9222"
        )
    return browser


def localizar_ou_abrir_pagina_sigef(context: "BrowserContext", url: str, url_marker: str) -> "Page":
    """
    Implementação genérica, reaproveitada por TODAS as automações do
    SIGEF: reaproveita a aba já aberta no domínio do SIGEF (evita abrir
    uma nova aba/contexto a cada automação - reduz chamadas ao
    navegador), navegando para `url` somente se a aba encontrada não for
    a tela esperada (`url_marker` ausente da URL atual). Se nenhuma aba
    do SIGEF estiver aberta, cria uma nova.

    Cada automação mantém sua própria função `localizar_ou_abrir_pagina_*`
    (fina, delegando para esta) para preservar nomes descritivos nos
    pontos de chamada e permitir evolução independente, se necessário.

    Comportamento (qualquer aba do domínio SIGEF é "tomada"):
        - Se já existir uma aba EXATAMENTE na tela esperada (`url_marker`
          bate), reaproveita ela direto, sem navegar de novo.
        - Caso contrário, toma controle de QUALQUER outra aba do domínio
          SIGEF que esteja aberta (ex: o portal `SIGEFPortal.html`, ou a
          tela de outra automação que rodou antes) e a substitui pela URL
          pedida agora - e vice-versa: ao trocar de automação, a aba que
          antes estava na tela da CE, por exemplo, é redirecionada para a
          tela da nova automação.
        - Se não houver NENHUMA aba do SIGEF aberta, cria uma nova.

    Também fecha, ao final, qualquer OUTRA aba/popup do domínio do SIGEF
    que não seja a aba escolhida acima - evita que a automação confunda a
    aba principal com um popup órfão de uma execução anterior (ex:
    "Pesquisar Credor" que ficou aberto), o que travava o
    `context.expect_page()` das automações esperando um evento de "nova
    página" que nunca chegava.
    """
    page = None
    candidata_generica = None

    for aba in context.pages:
        if DOMINIO_SIGEF not in aba.url.lower():
            continue
        if url_marker in aba.url:
            page = aba
            break
        if candidata_generica is None:
            candidata_generica = aba

    if page is None:
        page = candidata_generica

    if page is None:
        page = context.new_page()
        page.goto(url)
    else:
        page.bring_to_front()
        if url_marker not in page.url:
            page.goto(url)

    for aba in list(context.pages):
        if aba is not page and DOMINIO_SIGEF in aba.url.lower():
            try:
                aba.close()
            except Exception:
                pass

    # `aguardar_pagina_estavel` no lugar do `networkidle` puro: sem teto, ele
    # trava até o timeout em telas do SIGEF que mantêm requisições em segundo
    # plano (otimização trazida da automação PP).
    aguardar_pagina_estavel(page)
    return page


def conectar_e_obter_pagina_sigef(playwright, url: str, url_marker: str):
    """
    Conecta ao Chrome em modo debug, garante que existe ao menos um
    BrowserContext e localiza/abre a aba do SIGEF na URL informada.
    Concentra em 1 único lugar a sequência repetida em toda automação:
    conectar -> validar contexto -> obter página.

    Chamada dentro de um `with sync_playwright() as p:` já aberto pela
    automação (o navegador/contexto permanecem sob controle dela).
    """
    browser = conectar_navegador_sigef(playwright)
    if not browser.contexts:
        raise Exception("Nenhum contexto de navegador encontrado no Chrome conectado.")
    context = browser.contexts[0]
    page = localizar_ou_abrir_pagina_sigef(context, url, url_marker)
    return context, page


def aguardar_pagina_estavel(page: "Page", timeout_networkidle: int = 5000) -> None:
    """
    Aguarda o DOM carregar (`domcontentloaded`, bloqueante) e, na
    sequência, tenta aguardar a rede ficar ociosa (`networkidle`) por até
    `timeout_networkidle` ms - sem falhar caso a página tenha pollers/
    requisições contínuas que nunca ficam totalmente ociosas (comum em
    telas do SIGEF).
    """
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_networkidle)
    except Exception:
        pass


def aguardar_pagina_ociosa(page: "Page", periodo_calmo: float = 0.6,
                           timeout: int = TIMEOUT_PADRAO_SIGEF) -> bool:
    """
    Espera a página parar DE VERDADE: `document.readyState == "complete"`
    mantido por `periodo_calmo` segundos seguidos.

    `aguardar_pagina_estavel()` sozinho não basta quando o SIGEF encadeia
    postbacks: o DOM fica "pronto" por um instante e volta a recarregar
    logo em seguida. Uma ação disparada nessa janela (selecionar o combo,
    por exemplo) é desfeita pelo recarregamento seguinte.

    Retorna True se a página ficou parada dentro do prazo.
    """
    aguardar_pagina_estavel(page)

    prazo = time.monotonic() + (timeout / 1000)
    calmo_desde = None

    while time.monotonic() < prazo:
        try:
            pronta = page.evaluate("() => document.readyState === 'complete'")
        except Exception:
            # navegação em curso: o contexto de execução foi destruído
            pronta = False
            calmo_desde = None

        if pronta:
            if calmo_desde is None:
                calmo_desde = time.monotonic()
            elif time.monotonic() - calmo_desde >= periodo_calmo:
                return True
        else:
            calmo_desde = None

        time.sleep(0.1)

    return False


def clicar_e_aguardar_navegacao(page: "Page", seletor: str, timeout: int = TIMEOUT_PADRAO_SIGEF) -> None:
    """
    Clica no elemento de `seletor` esperando uma navegação de página (com
    fallback silencioso caso o SIGEF não dispare uma navegação "de
    verdade" - por exemplo, um postback via AJAX) e, em seguida, aguarda
    a página seguinte estabilizar (`aguardar_pagina_estavel`).
    """
    try:
        with page.expect_navigation(timeout=timeout):
            page.locator(seletor).click()
    except Exception:
        page.locator(seletor).click()

    aguardar_pagina_estavel(page)


def clicar_e_aguardar_elemento(page: "Page", seletor: str, seletor_esperado: str = None,
                               timeout: int = TIMEOUT_PADRAO_SIGEF) -> None:
    """
    Clica em `seletor` e, em vez de esperar a rede ficar ociosa
    (`networkidle` - que em telas do SIGEF com requisições em segundo
    plano fica pendurado até estourar o timeout), espera apenas o
    ELEMENTO SEGUINTE do fluxo aparecer: é ele que prova que o postback
    terminou.

    Passe `seletor_esperado=None` quando o passo seguinte já tiver a sua
    própria espera (ex: o `wait_for_selector` da mensagem de retorno do
    SIGEF) - assim nenhuma espera é feita em duplicidade.
    """
    alvo = page.locator(seletor).first
    alvo.wait_for(state="visible", timeout=timeout)
    alvo.click(timeout=timeout)

    if seletor_esperado:
        page.locator(seletor_esperado).first.wait_for(state="visible", timeout=timeout)


def limpar_formulario(page: "Page", timeout: int = TIMEOUT_BOTAO_LIMPAR) -> bool:
    """
    Devolve o formulário ao estado inicial clicando em "Limpar", com um
    plano B para o caso de o botão não estar na tela.

    Em algumas telas do SIGEF (e depois de certos erros), a automação
    fica numa etapa em que o "Limpar" simplesmente não existe - só o
    "Voltar". Antes, isso estourava um timeout e a linha seguinte
    começava com a tela suja. Agora, SE E SOMENTE SE der timeout
    esperando o "Limpar", clica em `#btnVoltar` e tenta o "Limpar"
    novamente.

    Compartilhada por todas as automações que limpam o formulário entre
    uma linha e outra (NL, PP, ...).

    Retorna True se conseguiu limpar; False se nem pelo Voltar deu.
    """
    seletor_limpar = "img[src*='Limpar.GIF']"

    try:
        botao_limpar = page.locator(seletor_limpar).first
        botao_limpar.wait_for(state="visible", timeout=timeout)
        botao_limpar.click(timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        log_aviso("Botão 'Limpar' não encontrado na tela. Tentando pelo 'Voltar'.")
    except Exception as erro:
        log_aviso(f"Não foi possível clicar em 'Limpar': {erro}")
        return False

    try:
        botao_voltar = page.locator("#btnVoltar").first
        botao_voltar.wait_for(state="visible", timeout=timeout)
        botao_voltar.click(timeout=timeout)

        botao_limpar = page.locator(seletor_limpar).first
        botao_limpar.wait_for(state="visible", timeout=timeout)
        botao_limpar.click(timeout=timeout)
        log_info("Formulário limpo após voltar para a tela anterior.")
        return True
    except Exception as erro:
        log_erro(f"Não foi possível limpar o formulário nem pelo 'Voltar': {erro}")
        return False


def aguardar_campo_com_valor_por_id(page: "Page", padrao_id: str,
                                    timeout: int = TIMEOUT_PADRAO_SIGEF) -> bool:
    """
    Espera até que exista, na tela, um campo de texto cujo `id` case com
    `padrao_id` (sem diferenciar maiúsculas) e que esteja PREENCHIDO.

    É o sinal de que um popup de pesquisa do SIGEF terminou de devolver o
    registro escolhido para a tela principal - o clique na grade dispara
    um postback, e a tela principal só fica utilizável quando ele acaba.
    A checagem é feita por JavaScript, sem depender do `id` exato (o
    SIGEF varia o sufixo do campo entre telas).

    Exemplos de uso: "NotaLancamento" (PP) e "NotaEmpenho" (NL).
    """
    prazo = time.monotonic() + (timeout / 1000)

    while time.monotonic() < prazo:
        try:
            preenchido = page.evaluate("""
                padrao => [...document.querySelectorAll("input[type=text]")]
                    .some(campo => new RegExp(padrao, "i").test(campo.id)
                                   && campo.value.trim() !== "")
            """, padrao_id)
            if preenchido:
                return True
        except Exception:
            pass
        time.sleep(0.1)

    return False


def aguardar_campo_preenchido(campo, valor_esperado: str,
                              timeout: int = TIMEOUT_PADRAO_SIGEF) -> bool:
    """
    Confere se um campo terminou de receber TODO o valor digitado, antes
    de a automação seguir em frente.

    Necessário para os campos preenchidos com `press_sequentially()`: a
    digitação é tecla a tecla e as máscaras/JS do SIGEF podem atrasar (ou
    engolir) os últimos dígitos - o clique seguinte então acontecia com o
    campo pela metade.

    A comparação é feita só pelos dígitos, já que a máscara do SIGEF
    reformata o que foi digitado (ex: digitado "140000", exibido
    "1.400,00" - os dois viram "140000").
    """
    digitos_esperados = REGEX_APENAS_DIGITOS.sub("", str(valor_esperado)).lstrip("0")
    prazo = time.monotonic() + (timeout / 1000)

    while time.monotonic() < prazo:
        try:
            digitos_na_tela = REGEX_APENAS_DIGITOS.sub("", campo.input_value()).lstrip("0")
            if digitos_na_tela == digitos_esperados:
                return True
        except Exception:
            pass
        time.sleep(0.1)

    return False


def selecionar_combo_com_conferencia(page: "Page", combo, valor: str, tentativas: int = 3,
                                     timeout: int = TIMEOUT_PADRAO_SIGEF) -> bool:
    """
    Seleciona uma opção de <select> pelo VALUE e CONFERE se ela ficou
    mesmo selecionada DEPOIS de a página parar de recarregar, repetindo
    enquanto necessário.

    Combos do SIGEF são montados e revalidados por postback. Havia duas
    formas de perder a seleção:
      - selecionar antes de a lista terminar de montar; e
      - selecionar no meio de um postback ainda em curso, que logo em
        seguida recarrega a tela e desfaz a escolha (era o caso do Tipo
        de Ordem Bancária, que "sumia" e a automação seguia para a
        pesquisa da conta sem tipo nenhum).

    Por isso a página é aguardada parada (`aguardar_pagina_ociosa`) antes
    de selecionar E depois de selecionar - só então o valor é lido de
    volta. Só retorna True com o combo de fato no valor pedido.
    """
    for _ in range(tentativas):
        try:
            aguardar_pagina_ociosa(page, timeout=timeout)

            combo.wait_for(state="visible", timeout=timeout)
            combo.locator(f"option[value='{valor}']").first.wait_for(state="attached", timeout=timeout)
            combo.select_option(value=valor)

            # A própria seleção pode disparar postback: espera a tela parar
            # de novo antes de conferir.
            aguardar_pagina_ociosa(page, timeout=timeout)

            if combo.input_value() == valor:
                return True
        except Exception:
            pass

        time.sleep(0.2)

    return False


def fechar_paginas(paginas) -> None:
    """
    Fecha somente as janelas/popups que a automação abriu (ignora as
    demais abas do usuário e as que o próprio SIGEF já fechou). Evita que
    um popup órfão trave o `context.expect_page()` da linha seguinte.
    """
    for pagina in paginas:
        try:
            if pagina is not None and not pagina.is_closed():
                pagina.close()
        except Exception:
            pass


def aguardar_popup_lancamento(page: "Page", context: "BrowserContext", popup_adicionar: "Page",
                               campo_marcador: str = "#txtIdentificadorUso",
                               timeout_total_ms: int = TIMEOUT_PADRAO_SIGEF) -> "Page":
    """
    Espera o campo `campo_marcador` ficar pronto após confirmar o Evento -
    seja porque o SIGEF reaproveitou a MESMA janela (`popup_adicionar`,
    postback no lugar - o caso mais comum) ou porque abriu uma aba/janela
    nova de verdade.

    Faz polling curto, verificando os dois candidatos a cada volta e
    retornando assim que QUALQUER um deles ficar pronto.

    Retorna a página onde o campo apareceu; se nada aparecer dentro de
    `timeout_total_ms`, devolve `popup_adicionar` mesmo assim.
    """
    prazo = time.monotonic() + (timeout_total_ms / 1000)
    intervalo_checagem_ms = 250

    while time.monotonic() < prazo:
        try:
            popup_adicionar.locator(campo_marcador).wait_for(state="attached", timeout=intervalo_checagem_ms)
            return popup_adicionar
        except Exception:
            pass

        for pg in context.pages:
            if pg is page or pg is popup_adicionar:
                continue
            try:
                if pg.url:
                    pg.locator(campo_marcador).wait_for(state="attached", timeout=intervalo_checagem_ms)
                    return pg
            except Exception:
                continue

    return popup_adicionar


# ==============================================================================
# 5. UTILIDADES DE NEGÓCIO (conversão de identificadores e valores)
# ==============================================================================
# A planilha SEMPRE armazena o identificador completo, exatamente como o
# SIGEF gerou (ex: "2026PP123456", "2026OB654321", "2026CE111222" ou
# "2026NL333444") - isso nunca é alterado. Porém várias telas do SIGEF só
# aceitam o número final, sem o prefixo "AAAA" + sigla do documento.
#
# `extrair_numero_documento()` é o ÚNICO ponto do sistema que faz essa
# conversão - reconhece automaticamente o tipo de documento e devolve
# apenas os dígitos finais. Nenhuma outra função deve usar `.replace(...)`
# ou regex própria para isso; toda conversão passa por aqui.

def extrair_numero_documento(codigo_completo: str) -> str:
    """
    Remove o prefixo "AAAA" + sigla (ano + tipo de documento: PP, OB, CE
    ou NL) de um identificador do SIGEF, retornando apenas os dígitos
    finais que os campos de pesquisa das telas do SIGEF aceitam.

    Exemplos:
        "2026PP123456" -> "123456"
        "2026OB654321" -> "654321"
    """
    if not codigo_completo:
        return ""

    codigo = codigo_completo.strip()
    sem_prefixo = REGEX_PREFIXO_DOCUMENTO.sub("", codigo)
    return sem_prefixo or codigo


def normalizar_numero_documento(valor) -> str:
    """
    Normaliza um número de documento do SIGEF (CE, NL, OB, PP, NE) para
    comparação entre a planilha e a grade do SIGEF: remove o prefixo
    "AAAA+sigla" (reaproveitando `extrair_numero_documento`) e quaisquer
    zeros à esquerda, convertendo ambos os lados para o mesmo formato
    numérico - assim "2026CE018487" (SIGEF) e "18487" (planilha) ficam
    ambos "18487", e a comparação funciona independentemente da
    quantidade de zeros à esquerda. Nunca compara strings brutas.

    Exemplo:
        "2026CE018487" -> "18487"
        "18487"        -> "18487"
    """
    texto = str(valor).strip()

    # Defesa extra contra floats do Excel que escapem de `obter_celula`
    # (ex: "18487.0") - remove a parte decimal quando ela for só zeros.
    if "." in texto:
        parte_inteira, parte_decimal = texto.split(".", 1)
        if parte_decimal.strip("0") == "":
            texto = parte_inteira

    sem_prefixo = extrair_numero_documento(texto)
    apenas_digitos = REGEX_APENAS_DIGITOS.sub("", sem_prefixo)
    return str(int(apenas_digitos)) if apenas_digitos else ""


# Homóglifos: caracteres cirílicos/gregos VISUALMENTE idênticos a letras
# latinas. Aparecem em planilhas montadas por copiar/colar de PDF, e-mail
# ou teclado com layout trocado. O caso clássico aqui é o dígito
# verificador "X" de conta bancária vir como "Х" (U+0425, cirílico): a
# limpeza `[^0-9A-Za-z]` DESCARTA esse caractere, a conta "81.590-Х" vira
# "81590" em vez de "81590X" e nunca bate com a grade do SIGEF - embora no
# log os dois apareçam idênticos. Por isso a conversão vem ANTES da limpeza.
_HOMOGLIFOS_LATINOS = str.maketrans({
    # Cirílico maiúsculo
    "\u0410": "A", "\u0412": "B", "\u0415": "E", "\u041a": "K", "\u041c": "M",
    "\u041d": "H", "\u041e": "O", "\u0420": "P", "\u0421": "C", "\u0422": "T",
    "\u0423": "Y", "\u0425": "X", "\u0405": "S", "\u0406": "I", "\u0408": "J",
    # Cirílico minúsculo
    "\u0430": "a", "\u0432": "b", "\u0435": "e", "\u043a": "k", "\u043c": "m",
    "\u043d": "h", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0442": "t",
    "\u0443": "y", "\u0445": "x", "\u0455": "s", "\u0456": "i", "\u0458": "j",
    # Grego maiúsculo
    "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z", "\u0397": "H",
    "\u0399": "I", "\u039a": "K", "\u039c": "M", "\u039d": "N", "\u039f": "O",
    "\u03a1": "P", "\u03a4": "T", "\u03a5": "Y", "\u03a7": "X",
    # Grego minúsculo
    "\u03b1": "a", "\u03bd": "v", "\u03bf": "o", "\u03c1": "p", "\u03c4": "t",
    "\u03c7": "x",
})


def latinizar_homoglifos(texto: str) -> str:
    """
    Converte caracteres visualmente idênticos a letras latinas para o
    equivalente ASCII. Aplica NFKC antes (resolve largura total, como
    "\uff38" -> "X", e dígitos de outras escritas) e depois a tabela de
    homóglifos cirílicos/gregos, que o NFKC NÃO converte.
    """
    return unicodedata.normalize("NFKC", texto).translate(_HOMOGLIFOS_LATINOS)


def normalizar_chave_bancaria(valor) -> str:
    """
    Normaliza banco, agência e conta para comparação entre a planilha e a
    grade do SIGEF: mantém apenas letras e números (remove pontos,
    vírgulas, traços, barras, espaços e `&nbsp;`), passa para maiúsculo e
    tira os zeros à esquerda - assim os dois lados chegam no MESMO
    formato. É o único ponto do sistema que faz essa conversão.

    Exemplos:
        "1"        -> "1"       |  "001"        -> "1"
        "1401-X"   -> "1401X"   |  "01401X"     -> "1401X"
        "67.287-4" -> "672874"  |  "0000672874" -> "672874"
    """
    if valor is None:
        return ""

    texto = str(valor).replace("\xa0", " ")

    # Defesa contra floats do Excel que escapem de `obter_celula`
    # (ex: "74508.0" numa conta digitada sem máscara).
    if "." in texto:
        parte_inteira, parte_decimal = texto.split(".", 1)
        if parte_decimal.strip("0") == "":
            texto = parte_inteira

    limpo = re.sub(r"[^0-9A-Za-z]", "", latinizar_homoglifos(texto)).upper()
    if not limpo:
        return ""

    sem_zeros = limpo.lstrip("0")
    return sem_zeros or "0"


def normalizar_valor_sigef(valor) -> float:
    """
    Normaliza valores monetários vindos tanto da planilha (sem separador,
    ex: '55980' -> 559.80) quanto da grade do SIGEF (com separador BR, ex:
    '790,54' ou '1.234,56' -> 1234.56).
    """
    valor_str = str(valor).replace("R$", "").strip()

    if valor_str.isdigit():
        # Valor vindo da planilha (sem separador decimal).
        return float(valor_str) / 100

    # Valor vindo da grade do SIGEF.
    return float(valor_str.replace(".", "").replace(",", "."))


def decimal_br(valor):
    """
    Converte diferentes formatos de valor para Decimal.
    Exemplos aceitos:
        193600
        "193600"
        "1.936,00"
        "1936.00"
        Decimal(...)
    """
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor)) / Decimal("100")
    valor = str(valor).strip()
    if "." in valor and "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
        return Decimal(valor)
    if "," in valor:
        return Decimal(valor.replace(",", "."))
    if valor.isdigit():
        return Decimal(valor) / Decimal("100")
    return Decimal(valor)


def formatar_cpf(valor) -> str:
    """
    Formata um CPF (vindo da planilha com ou sem máscara) no padrão
    XXX.XXX.XXX-XX exigido pelo campo #txtNuCpf do SIGEF. Caso não tenha
    exatamente 11 dígitos, devolve o valor original (sem inventar máscara).
    """
    digitos = REGEX_APENAS_DIGITOS.sub("", str(valor))
    if len(digitos) == 11:
        return f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return str(valor).strip()


def formatar_valor_centavos(valor) -> str:
    """
    Converte o valor da planilha (ex: 1400, representando R$ 1.400,00)
    para o formato que os campos de valor em centavos do SIGEF esperam
    (#txtVlDocumento na CE, #txtValorBrutoId na NL): o mesmo número
    multiplicado por 100, sem separadores. Compartilhada entre as
    automações que preenchem valores dessa forma.

    Exemplos:
        1400        -> "140000"
        "1400"      -> "140000"
        "1.400,00"  -> "140000"
    """
    texto = str(valor).replace("R$", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    numero = float(texto) if texto else 0.0
    return str(int(round(numero * 100)))


def formatar_valor_br(valor) -> str:
    """
    Formata um valor monetário da planilha (ex: 1400, representando R$
    1.400,00) no padrão brasileiro com separador de milhar e 2 casas
    decimais (ex: "1.400,00") - usado para comparar com o valor líquido
    exibido na grade de resultados do SIGEF (que já vem formatado assim),
    já que a planilha guarda o valor sem separadores e o SIGEF exibe com
    separadores; sem essa conversão a comparação nunca bateria.
    """
    texto = str(valor).replace("R$", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    numero = float(texto) if texto else 0.0
    formatado = f"{numero:,.2f}"
    return formatado.replace(",", "X").replace(".", ",").replace("X", ".")


def obter_numero_mes_referencia(mes_referencia: str) -> str:
    """
    Extrai o número do mês (sem zero à esquerda) a partir do Mês
    Referência configurado (formato "MM/AAAA", ex: "06/2026" -> "6"),
    para selecionar a opção correta no combo de mês de competência
    (#cboMesComp) do SIGEF.
    """
    mes_str = (mes_referencia or "").split("/")[0].strip()
    return str(int(mes_str)) if mes_str.isdigit() else mes_str


# ==============================================================================
# 6. AUTOMAÇÕES (esqueletos, a implementar)
# ==============================================================================
# Cada função abaixo é o ponto de entrada de uma automação do submenu (ver
# dicionário PROGRAMAS, seção 7). Todas seguem a MESMA assinatura, chamada
# pelo executor dinâmico:
#
#       def minha_automacao(dados, config=None, worksheet=None): ...
#
#   - dados:     lista de linhas lidas da planilha (ver `ler_dados`), já a
#                partir da linha inicial configurada.
#   - config:    dicionário de configurações atual (DATA, PROCESSO, MÊS REFERÊNCIA,
#                caminho/aba da planilha, etc.).
#   - worksheet: aba do Excel já conectada (objeto COM), pronta para leitura
#                e escrita (ver seção 3 - EXCEL).
#
# Estão vazias de propósito - implemente aqui a lógica de cada fluxo no
# SIGEF, reaproveitando as utilidades genéricas do Playwright (seção 4) e
# do Excel (seção 3) conforme for programando.

def _preencher_campos_fixos_ce(page: "Page", config: dict) -> None:
    """
    Preenche os campos fixos da tela "Manter Despesa Certificada" (CE) -
    os MESMOS para todas as linhas da planilha, portanto executados uma
    única vez por automação (parte fixa).
    """
    mes_referencia = config.get("mes_referencia", "")
    processo = config.get("processo", "")
    data = config.get("data", "")

    page.locator("#txtCdGestao_SIGEFPesquisa").fill("00001")
    page.locator("#txtNuDocumento").fill(mes_referencia)
    page.locator("#chkFlAtestadoRecSouResp").check()
    page.locator("#txtDeObservacao").fill(
        f"Gratificação amigo voluntario {mes_referencia} Processo: {processo}"
    )
    page.locator("#txtDtAceite_SIGEFData").fill(data)
    page.locator("#txtDtApresentacao_SIGEFData").fill(data)
    page.locator("#txtDtEmissao_SIGEFData").fill(data)
    page.locator("#cboMesComp").select_option(obter_numero_mes_referencia(mes_referencia))


def _aguardar_resultado_ou_erro_grade(resultado_grade, mensagem_erro,
                                       timeout_ms: int = TIMEOUT_PADRAO_SIGEF) -> bool:
    """
    Faz polling curto (a cada 150ms) esperando QUALQUER UM dos dois
    desfechos possíveis de uma pesquisa em popup do SIGEF (credor, Nota
    de Empenho etc.): uma linha aparecer na grade OU a mensagem "Não há
    registros a serem listados." ficar visível - respondendo assim que
    qualquer um dos dois ocorrer, em vez de esperar o timeout inteiro
    sempre que o SIGEF já respondeu rapidamente com "sem resultados" (era
    o que causava a demora extra para pular de linha).

    Retorna True se encontrou ao menos 1 linha na grade, False se a
    mensagem de erro apareceu (e permaneceu) ou se o timeout total
    expirar sem nenhum dos dois sinais.
    """
    prazo = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < prazo:
        if resultado_grade.count() > 0:
            return True

        if mensagem_erro.first.is_visible():
            # A mensagem de erro pode aparecer BREVEMENTE antes da grade
            # terminar de renderizar (falso positivo transitório - foi o
            # caso do CPF 764.167.802-59, que aparecia normalmente como
            # 1ª linha da grade, mas era marcado como "não encontrado").
            # Por isso, espera um instante e reconfirma os dois sinais
            # antes de aceitar a mensagem de erro como definitiva.
            time.sleep(0.3)
            if resultado_grade.count() > 0:
                return True
            if mensagem_erro.first.is_visible():
                return False
        time.sleep(0.15)

    return resultado_grade.count() > 0


def _selecionar_credor_por_cpf(
    page: "Page",
    context: "BrowserContext",
    cpf_formatado: str,
    seletor_botao_pesquisa: str = "#txtNmCredor_BtnPesquisa",
) -> bool:
    """
    Abre o popup de pesquisa de credor, pesquisa pelo CPF informado e
    seleciona o primeiro resultado da grade - reproduz o fluxo manual
    (clicar em pesquisar -> CPF -> confirmar -> selecionar item) e traz o
    foco de volta para a página principal ao final.

    Compartilhada entre as automações CE (`#txtNmCredor_BtnPesquisa`) e
    Raspar CE (`#txtCdCredor_BtnPesquisa`) - o botão de pesquisa muda de
    uma tela para outra, mas o restante do fluxo do popup é idêntico.

    Retorna:
        True  -> credor encontrado e selecionado normalmente.
        False -> a pesquisa não retornou nenhuma linha selecionável na
                 grade (`td.GridLink[onclick*='SelecionarItem']`); a
                 linha deve ser pulada e a automação segue para a próxima.
    """
    with context.expect_page() as popup_info:
        page.locator(seletor_botao_pesquisa).click()

    popup = popup_info.value
    aguardar_pagina_estavel(popup)

    popup.locator("#btnCPF").click()
    popup.locator("#txtNuCpf").fill(cpf_formatado)

    mensagem_erro = popup.locator("td.SIGEFMensagemErro")
    resultado_grade = popup.locator("td.GridLink[onclick*='SelecionarItem']")

    popup.locator("#btnConfirmar").click()

    if not _aguardar_resultado_ou_erro_grade(resultado_grade, mensagem_erro):
        # Chega aqui quando a mensagem de erro apareceu (ou, no pior caso,
        # quando o timeout total expirou sem nenhum dos dois sinais) - a
        # checagem abaixo só deixa o aviso mais preciso quando o SIGEF
        # confirma explicitamente "Não há registros a serem listados.".
        if mensagem_erro.first.is_visible():
            print(
                f"⚠️  CPF {cpf_formatado}: SIGEF respondeu 'Não há registros a serem "
                f"listados.'. Pulando para a próxima linha."
            )
        else:
            print(f"⚠️  CPF {cpf_formatado}: nenhum registro encontrado no SIGEF. Pulando para a próxima linha.")
        popup.close()
        page.bring_to_front()
        return False

    resultado_grade.first.click()
    page.bring_to_front()
    return True


def _selecionar_empenho_por_numero(page: "Page", context: "BrowserContext", numero_empenho: str) -> bool:
    """
    Abre o popup de pesquisa de Nota de Empenho, pesquisa pelo número
    informado (já sem o prefixo "AAAANE") e seleciona o primeiro
    resultado da grade - mesmo padrão de `_selecionar_credor_por_cpf`
    (popup -> preencher -> confirmar -> selecionar item), usado pela
    automação NL.

    Retorna:
        True  -> empenho encontrado e selecionado normalmente.
        False -> a pesquisa não retornou nenhuma linha selecionável na
                 grade; a linha deve ser pulada e a automação segue para
                 a próxima.
    """
    with context.expect_page() as popup_info:
        page.locator("#txtNotaEmpenhoNumeroId_BtnPesquisa").click()

    popup = popup_info.value
    aguardar_pagina_estavel(popup)

    mensagem_erro = popup.locator("td.SIGEFMensagemErro")
    resultado_grade = popup.locator("td.GridLink[onclick*='SelecionarItem']")

    popup.locator("#txtNotaEmpenhoNumero").fill(numero_empenho)
    popup.locator("#btnConfirmar").click()

    if not _aguardar_resultado_ou_erro_grade(resultado_grade, mensagem_erro):
        if mensagem_erro.first.is_visible():
            print(
                f"⚠️  NE {numero_empenho}: SIGEF respondeu 'Não há registros a serem "
                f"listados.'. Pulando para a próxima linha."
            )
        else:
            print(f"⚠️  NE {numero_empenho}: nenhum registro encontrado no SIGEF. Pulando para a próxima linha.")
        popup.close()
        page.bring_to_front()
        return False

    resultado_grade.first.click()
    page.bring_to_front()

    # O clique dispara um postback na tela principal (a NE selecionada volta
    # preenchida). Sem esperar esse retorno, a digitação do valor bruto
    # começava com a página ainda carregando e perdia dígitos.
    if not aguardar_campo_com_valor_por_id(page, "NotaEmpenho"):
        log_aviso(
            f"NE {numero_empenho}: a Nota de Empenho selecionada não voltou para a tela "
            f"principal. Pulando para a próxima linha."
        )
        return False

    aguardar_pagina_estavel(page)
    return True


def ce(dados, config=None, worksheet=None):
    """
    Automação: CE (Manter Despesa Certificada).

    Fluxo:
        1. Conecta 1 única vez à aba do SIGEF na tela de CE (parte fixa).
        2. Preenche os campos fixos da tela (gestão, mês de competência,
           observação, datas etc.) - também 1 única vez.
        3. Para cada linha da planilha: pesquisa o credor pelo CPF
           (coluna B), preenche o valor (coluna H, convertido para
           centavos), inclui o documento, captura o número da CE gerada
           e grava na coluna I da mesma linha.
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação CE.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(p, URL_CE_SIGEF, MARCADOR_URL_CE)
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de CE do SIGEF: {erro}")
            return

        try:
            _preencher_campos_fixos_ce(page, config)
        except Exception as erro:
            log_erro(f"Erro ao preencher os campos fixos da CE: {erro}")
            return

        # Locators reaproveitados em TODAS as linhas - buscados uma única
        # vez fora do loop, evitando repetir `page.locator(...)` a cada
        # iteração (reduz consultas ao DOM e chamadas ao Playwright).
        campo_valor = page.locator("#txtVlDocumento")
        botao_incluir = page.locator("#btnManutencao_BtnIncluir")
        campo_ce_gerada = page.locator("#txtNuSeq")

        total_processadas = 0

        # ---- Parte em loop até a última linha da planilha ------------------
        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice
            cpf = obter_celula(linha, COL_CE_CPF)
            valor_bruto = obter_celula(linha, COL_CE_VALOR)

            if not cpf or not valor_bruto:
                log_aviso(f"Linha {numero_linha}: CPF ou valor vazio. Pulando.")
                continue

            try:
                if not _selecionar_credor_por_cpf(page, context, formatar_cpf(cpf)):
                    continue

                # Requisito obrigatório: manter `press_sequentially()`
                # exatamente como está - não substituir por `.fill()`.
                campo_valor.press_sequentially(formatar_valor_centavos(valor_bruto))
                botao_incluir.click()

                # Captura a CE gerada e salva na coluna I da mesma linha.
                ce_gerada = campo_ce_gerada.input_value()
                log_sucesso(f"Linha {numero_linha}: CE '{ce_gerada}' gerada para o CPF {cpf}.")
                salvar_valor_gerado(worksheet, numero_linha, COL_CE_GERADA, ce_gerada, rotulo="CE")

                # Apaga a CE e o valor antes de reiniciar o loop na próxima linha.
                campo_ce_gerada.fill("")
                campo_valor.fill("")
                total_processadas += 1

            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da automação CE: {erro}")
                continue

        log_sucesso(
            f"Automação CE concluída: {total_processadas} de {len(dados)} linha(s) processada(s)."
        )


def _extrair_ultima_despesa_certificada(page: "Page"):
    """
    Executa, dentro do próprio navegador (via `evaluate`, sem round-trips
    extras de Playwright para cada célula), a extração da última linha da
    grade `#dtgDespesaCertificada`: número da CE, mês/ano do documento e
    valor. Devolve os 3 valores já desempacotados (não o dicionário bruto
    retornado pelo JavaScript).
    """
    dados = page.locator("#dtgDespesaCertificada").evaluate("""
        table => {
            const linhas = [...table.querySelectorAll("tr")]
                .filter(tr => tr.querySelector("td.GridLink"));

            const ultima = linhas.at(-1);

            const numero = ultima.querySelector("td.GridLink").textContent.trim();

            const valor = [...ultima.querySelectorAll("td")]
                .find(td => td.align === "right")
                .textContent.trim();

            const numeroDocumento =
                ultima.querySelector("td.GridLink")
                    .nextElementSibling
                    .nextElementSibling
                    .textContent.trim();

            return { numero, numero_documento: numeroDocumento, valor };
        }
    """)
    return dados["numero"], dados["numero_documento"], dados["valor"]


def raspar_ce(dados, config=None, worksheet=None):
    """
    Automação: Raspar CE (Listar Despesa Certificada Geral).

    Mesma arquitetura da automação CE: conexão/preenchimento fixo 1 única
    vez, loop reaproveitando locators e reaproveitando o popup de busca de
    credor (`_selecionar_credor_por_cpf`, compartilhado com a CE).

    Fluxo:
        1. Conecta 1 única vez à aba do SIGEF na tela de listagem de CE
           (parte fixa).
        2. Preenche unidade gestora/gestão e abre a aba "Favorecida" -
           também 1 única vez.
        3. Para cada linha da planilha: pesquisa o credor pelo CPF
           (coluna B), confirma a busca, extrai da grade o número da CE,
           o mês/ano do documento e o valor da última despesa certificada
           listada, e grava os 3 valores na coluna I da mesma linha.
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação Raspar CE.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(p, URL_RASPAR_CE_SIGEF, MARCADOR_URL_RASPAR_CE)
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de listagem de CE do SIGEF: {erro}")
            return

        try:
            page.locator("#txtCdUnidadeGestora").fill("160001")
            page.locator("#txtCdGestao_SIGEFPesquisa").fill("00001")
            page.locator("#btnAbaFavorecida").click()
        except Exception as erro:
            log_erro(f"Erro ao preencher os campos fixos da Raspar CE: {erro}")
            return

        # Locators reaproveitados em TODAS as linhas - buscados uma única
        # vez fora do loop (reduz consultas ao DOM e chamadas ao Playwright).
        botao_confirmar = page.locator("#btnConfirmar")
        linhas_grade = page.locator("#dtgDespesaCertificada td.GridLink")

        total_processadas = 0

        # ---- Parte em loop até a última linha da planilha ------------------
        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice
            cpf = obter_celula(linha, COL_CE_CPF)

            if not cpf:
                log_aviso(f"Linha {numero_linha}: CPF vazio. Pulando.")
                continue

            try:
                # Mesmo popup de busca de credor da CE, só muda o botão
                # que o abre nesta tela (#txtCdCredor_BtnPesquisa).
                if not _selecionar_credor_por_cpf(
                    page, context, formatar_cpf(cpf), seletor_botao_pesquisa="#txtCdCredor_BtnPesquisa"
                ):
                    continue

                botao_confirmar.click()

                # Aguarda a grade recarregar (postback/AJAX) antes de ler os
                # dados - sem isso, a extração podia rodar antes da tabela
                # ser atualizada com o resultado da pesquisa.
                aguardar_pagina_estavel(page)
                linhas_grade.first.wait_for(state="visible", timeout=TIMEOUT_PADRAO_SIGEF)

                numero, numero_documento, valor = _extrair_ultima_despesa_certificada(page)
                print(f"Valores da linha [{numero_linha}]: {numero}, {numero_documento}, {valor}")

                # Grava só o número da CE na coluna I (mesma coluna/formato
                # que a automação CE grava) - a NL depende dessa coluna
                # conter apenas o número puro para poder pesquisar a
                # despesa certificada; mês/valor ficam só no log acima.
                salvar_valor_gerado(worksheet, numero_linha, COL_CE_GERADA, numero, rotulo="Raspar CE")

                total_processadas += 1

            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da automação Raspar CE: {erro}")
                continue

        log_sucesso(
            f"Automação Raspar CE concluída: {total_processadas} de {len(dados)} linha(s) processada(s)."
        )


def _extrair_documentos_grade(page: "Page"):
    """
    Extrai todos os pares (documento, valor_líquido) das linhas
    preenchidas da grade `#dtgDocumentos` - o SIGEF pode devolver mais de
    uma NL para uma única liquidação (ex: quando alguma retenção obriga a
    dividir em mais de um documento).

    Usa reconhecimento por PADRÃO em vez de índice fixo de coluna
    (`.nth(5)`/`.nth(7)` se mostraram frágeis, pois a grade pode variar
    de estrutura entre execuções): identifica a célula do documento pelo
    formato "AAAA" + 2 letras + dígitos (ex: "2026NL066020") e assume o
    valor líquido como a ÚLTIMA célula alinhada à direita da linha (o
    Valor Líquido sempre vem depois do Valor Bruto) - mesma estratégia já
    usada com sucesso em `_extrair_ultima_despesa_certificada` (Raspar CE).
    """
    linhas = page.locator("#dtgDocumentos").evaluate("""
        table => {
            const padraoDocumento = /^\\d{4}[A-Z]{2}\\d+$/;

            return [...table.querySelectorAll("tr")]
                .map(tr => {
                    const tds = [...tr.querySelectorAll("td")];
                    const tdDocumento = tds.find(td => padraoDocumento.test(td.textContent.trim()));
                    if (!tdDocumento) return null;

                    const valoresDireita = tds
                        .filter(td => td.align === "right")
                        .map(td => td.textContent.trim());

                    return {
                        documento: tdDocumento.textContent.trim(),
                        valor_liquido: valoresDireita.length ? valoresDireita[valoresDireita.length - 1] : ""
                    };
                })
                .filter(item => item !== null);
        }
    """)

    return [(item["documento"], item["valor_liquido"]) for item in linhas if item["valor_liquido"]]


def _valor_br_para_float(texto: str) -> float:
    """Converte um valor exibido no padrão BR pelo SIGEF (ex: '1.260,00')
    de volta para float, para permitir somar valores de múltiplos
    documentos antes de comparar com o esperado pela planilha."""
    texto = str(texto).replace("R$", "").strip()
    return float(texto.replace(".", "").replace(",", ".")) if texto else 0.0


def _selecionar_documento_correspondente(documentos, valor_liquido_esperado: str):
    """
    Decide qual(is) documento(s) de uma lista (documento, valor_líquido)
    correspondem ao valor esperado pela planilha, com a mesma prioridade
    usada tanto na checagem prévia (documento já lançado antes de
    liquidar de novo) quanto na checagem final (após confirmar):

        1. Algum documento, sozinho, já bate exatamente com o esperado -
           usa só esse (mesmo que existam outras linhas na grade).
        2. Só existe 1 documento na grade - usa ele.
        3. Nenhum bate sozinho - soma os valores líquidos de todos e
           combina os números na mesma célula.

    Retorna (numero_documento, valor_liquido) - `numero_documento` já vem
    combinado com " + " quando forem 2 ou mais somados.
    """
    correspondencia_unica = next(
        (doc for doc in documentos if doc[1] == valor_liquido_esperado), None
    )
    if correspondencia_unica is not None:
        return correspondencia_unica

    if len(documentos) == 1:
        return documentos[0]

    soma = sum(_valor_br_para_float(valor) for _, valor in documentos)
    numero_combinado = " + ".join(documento for documento, _ in documentos)
    return numero_combinado, formatar_valor_br(soma)


def nl(dados, config=None, worksheet=None):
    """
    Automação: NL (Liquidar Despesa Certificada).

    Fluxo (repetido por completo a cada linha, já que a pesquisa por CE e
    o preenchimento do formulário resetam a tela a cada iteração):
        1. Conecta 1 única vez à aba do SIGEF na tela de liquidação
           (a única etapa que realmente ocorre 1 única vez).
        2. Para cada linha da planilha: pesquisa a despesa certificada
           pelo número da CE (coluna I). Se a grade já mostrar alguma NL
           lançada e o valor líquido bater com o esperado (coluna H),
           salva direto na coluna J, avisa e reinicia o ciclo - sem
           lançar uma nova liquidação por cima. Caso contrário, prossegue
           normalmente: define a data de vencimento (Data configurada no
           sistema) e adiciona a liquidação.
        3. Pesquisa e seleciona a Nota de Empenho vinculada (coluna D).
        4. Preenche o valor bruto (coluna H, convertido para centavos) e
           confirma as retenções.
        5. Extrai o(s) documento(s) e valor(es) líquido(s) gerados pelo
           SIGEF na grade. Se algum documento, sozinho, já bater
           exatamente com o valor esperado, usa só esse (mesmo que
           existam outras linhas na grade). Caso contrário, e se vierem
           2 ou mais documentos, soma os valores líquidos de todos e
           compara a soma com o esperado. Em qualquer um dos casos, se
           conferir, grava o(s) número(s) da NL na coluna J (quando forem
           2+ combinados na soma, todos juntos na MESMA célula).
        6. Limpa o formulário (`img[src*='Limpar.GIF']`) e segue para a
           próxima linha.
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação NL.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)
    data_vencimento = config.get("data", "")

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(p, URL_NL_SIGEF, MARCADOR_URL_NL)
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de liquidação de despesa certificada do SIGEF: {erro}")
            return

        # Locators reaproveitados em TODAS as linhas - buscados uma única
        # vez fora do loop (reduz consultas ao DOM e chamadas ao Playwright).
        campo_gestao = page.locator("#txtCdGestao_SIGEFPesquisa")
        campo_ce_pesquisa = page.locator("#txtDespesaCertificadaNumero_SIGEFPesquisa")
        botao_pesquisar = page.locator("#btnPesquisar")
        campo_data_vencimento = page.locator("#txtDataVencimento_SIGEFData")
        botao_adicionar = page.locator("#btnAdicionar")
        campo_valor_bruto = page.locator("#txtValorBrutoId")
        botao_retencoes = page.locator("#btnRetencoesId")
        botao_menu_n4 = page.locator("#menun4")
        botao_confirmar = page.locator("#btnConfirmar")

        # Clica em "Limpar" assim que a página carrega, antes de começar o
        # loop - garante que o formulário comece limpo, mesmo que a aba
        # reaproveitada tenha ficado com dados de uma execução anterior.
        try:
            limpar_formulario(page)
        except Exception as erro:
            log_aviso(f"Não foi possível clicar em Limpar ao iniciar a NL: {erro}")

        total_processadas = 0

        # ---- Parte em loop até a última linha da planilha ------------------
        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice

            numero_ce = obter_celula(linha, COL_NL_CE)
            numero_ne = obter_celula(linha, COL_NL_NE)
            valor_bruto = obter_celula(linha, COL_CE_VALOR)

            if not numero_ce or not numero_ne or not valor_bruto:
                log_aviso(f"Linha {numero_linha}: CE, NE ou valor vazio. Pulando.")
                continue

            try:
                campo_gestao.fill("00001")
                campo_ce_pesquisa.fill(extrair_numero_documento(numero_ce).zfill(6))
                botao_pesquisar.click()
                aguardar_pagina_estavel(page)

                # Verifica se essa despesa certificada JÁ TEM alguma NL
                # lançada antes de prosseguir - se já existir e o valor
                # bater (mesmo critério da checagem final, após
                # confirmar), só salva e reinicia o ciclo sem lançar uma
                # nova liquidação por cima.
                valor_liquido_esperado = formatar_valor_br(valor_bruto)
                documentos_existentes = _extrair_documentos_grade(page)

                if documentos_existentes:
                    nl_existente, valor_liquido_existente = _selecionar_documento_correspondente(
                        documentos_existentes, valor_liquido_esperado
                    )

                    if valor_liquido_existente == valor_liquido_esperado:
                        log_sucesso(
                            f"Linha {numero_linha}: NL '{nl_existente}' já lançada, valor líquido "
                            f"{valor_liquido_existente} confere com a planilha. NL salva."
                        )
                        salvar_valor_gerado(worksheet, numero_linha, COL_NL_GERADA, nl_existente, rotulo="NL")
                        limpar_formulario(page)
                        total_processadas += 1
                        continue

                    log_aviso(
                        f"Linha {numero_linha}: já existe(m) documento(s) na grade, mas o valor "
                        f"não confere ({valor_liquido_existente} != {valor_liquido_esperado}). "
                        f"Prosseguindo com o lançamento normal."
                    )

                campo_data_vencimento.fill(data_vencimento)
                botao_adicionar.click()

                if not _selecionar_empenho_por_numero(page, context, extrair_numero_documento(numero_ne)):
                    continue

                # Requisito obrigatório: manter `press_sequentially()`
                # exatamente como está - não substituir por `.fill()`.
                valor_centavos = formatar_valor_centavos(valor_bruto)
                campo_valor_bruto.press_sequentially(valor_centavos)

                # Só prossegue depois que o campo confirma ter recebido TODO o
                # valor - a digitação tecla a tecla pode ficar para trás e o
                # clique seguinte acontecer com o valor pela metade.
                if not aguardar_campo_preenchido(campo_valor_bruto, valor_centavos):
                    log_erro(
                        f"Linha {numero_linha}: o valor bruto não foi digitado por completo "
                        f"no SIGEF (esperado {valor_centavos}, campo com "
                        f"'{campo_valor_bruto.input_value()}'). Pulando para a próxima linha."
                    )
                    limpar_formulario(page)
                    continue

                botao_retencoes.click()
                botao_menu_n4.click()
                botao_confirmar.click()

                # Aguarda a grade recarregar (postback) fazendo polling da
                # PRÓPRIA extração, em vez de esperar a linha ficar
                # "visível" - as linhas (mesmo vazias, só com "&nbsp;") já
                # ficam visíveis antes do SIGEF preencher os dados de
                # verdade, então esperar só por visibilidade resolvia cedo
                # demais e a extração rodava com a grade ainda vazia.
                aguardar_pagina_estavel(page)

                documentos = []
                prazo = time.monotonic() + (TIMEOUT_PADRAO_SIGEF / 1000)
                while time.monotonic() < prazo:
                    documentos = _extrair_documentos_grade(page)
                    if documentos:
                        break
                    time.sleep(0.15)

                if not documentos:
                    total_tabelas = page.locator("#dtgDocumentos").count()
                    total_linhas = page.locator("#dtgDocumentos tr").count()
                    log_erro(
                        f"Linha {numero_linha}: nenhum documento encontrado na grade após "
                        f"confirmar (tabela #dtgDocumentos encontrada: {total_tabelas}x, "
                        f"total de linhas <tr> dentro dela: {total_linhas})."
                    )
                    continue

                # valor_liquido_esperado já foi calculado antes do
                # Pesquisar (reaproveitado aqui, mesmo valor da linha).
                nl_gerada, valor_liquido_sigef = _selecionar_documento_correspondente(
                    documentos, valor_liquido_esperado
                )

                if valor_liquido_sigef == valor_liquido_esperado:
                    log_sucesso(
                        f"Linha {numero_linha}: NL '{nl_gerada}' gerada, valor líquido "
                        f"{valor_liquido_sigef} confere com a planilha."
                    )
                    salvar_valor_gerado(worksheet, numero_linha, COL_NL_GERADA, nl_gerada, rotulo="NL")
                    total_processadas += 1
                else:
                    log_erro(
                        f"Linha {numero_linha}: valor líquido do SIGEF ({valor_liquido_sigef}) "
                        f"não confere com o esperado pela planilha ({valor_liquido_esperado}). NL não salva."
                    )

                # Limpa o formulário antes de reiniciar o loop na próxima linha.
                limpar_formulario(page)

            except PlaywrightTimeoutError as erro:
                log_erro(f"Timeout ao processar a linha {numero_linha} da automação NL: {erro}")
                try:
                    limpar_formulario(page)
                except Exception as erro_limpar:
                    log_aviso(f"Linha {numero_linha}: não foi possível clicar em Limpar após o timeout: {erro_limpar}")
                continue

            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da automação NL: {erro}")
                continue

        log_sucesso(
            f"Automação NL concluída: {total_processadas} de {len(dados)} linha(s) processada(s)."
        )


def ler_tabela_despesa_certificada(page: "Page"):
    """
    Lê TODA a grade `#dtgDespesaCertificada` de uma única vez, via
    JavaScript (`evaluate`) - evita dezenas/centenas de chamadas ao
    Playwright (1 locator + 1 round-trip, em vez de 1 chamada por
    célula). Para cada linha com um registro clicável (`td.GridLink`),
    captura Número, Valor, Documento e Favorecido - preparado para
    futuras expansões (basta acrescentar mais campos ao objeto JS
    retornado).

    Offsets confirmados a partir da célula do Número (`td.GridLink`):
    1 célula depois = Tipo, 2 células depois = Número Documento, 3
    células depois = Favorecido (o texto visível dessa célula é o CPF; o
    nome completo do favorecido vem no atributo `title`).
    """
    return page.locator("#dtgDespesaCertificada").evaluate("""
        table => {
            const linhas = [...table.querySelectorAll("tr")]
                .filter(tr => tr.querySelector("td.GridLink"));

            return linhas.map(tr => {
                const tdNumero = tr.querySelector("td.GridLink");

                const valoresDireita = [...tr.querySelectorAll("td")]
                    .filter(td => td.align === "right")
                    .map(td => td.textContent.trim());

                const tdTipo = tdNumero.nextElementSibling;
                const tdDocumento = tdTipo ? tdTipo.nextElementSibling : null;
                const tdFavorecido = tdDocumento ? tdDocumento.nextElementSibling : null;

                const favorecido = tdFavorecido
                    ? (tdFavorecido.getAttribute("title") || tdFavorecido.textContent.trim())
                    : "";

                return {
                    numero: tdNumero.textContent.trim(),
                    documento: tdDocumento ? tdDocumento.textContent.trim() : "",
                    favorecido: favorecido,
                    valor: valoresDireita.length ? valoresDireita[valoresDireita.length - 1] : ""
                };
            });
        }
    """)


def raspar_nl(dados, config=None, worksheet=None):
    """
    Automação: Raspar NL (Listar Despesa Certificada Geral - pesquisa
    direta pelo número da despesa).

    Fluxo:
        1. Conecta 1 única vez à tela de listagem de despesa certificada
           (mesma tela/URL da Raspar CE).
        2. Parte fixa (1 única vez): clica em Limpar, preenche unidade
           gestora e gestão.
        3. Para cada linha da planilha: pesquisa pelo número da CE
           (coluna I, já com zeros à esquerda), lê a tabela inteira de
           uma vez (`ler_tabela_despesa_certificada`), normaliza os
           números (remove prefixo "AAAACE" e zeros à esquerda) e compara
           com o número esperado da planilha.
        4. Se encontrar: abre os detalhes (despesa -> Nota de Lançamento
           -> popup), captura CE/NL/NE e salva a NL na coluna J.
        5. Se NÃO encontrar (ou a tabela vier vazia): registra o aviso e
           segue para a próxima linha, sem interromper a automação.
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação Raspar NL.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(p, URL_RASPAR_CE_SIGEF, MARCADOR_URL_RASPAR_CE)
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de listagem de despesa certificada do SIGEF: {erro}")
            return

        # ---- Parte fixa: executa 1 única vez -------------------------------
        try:
            page.locator("#btnBotoesImpressao_BtnLimpar").click(timeout=5000)
        except Exception as erro:
            log_aviso(
                f"Não foi possível clicar em Limpar ao iniciar a Raspar NL "
                f"(botão pode não existir nesta tela): {erro}"
            )

        page.locator("#txtCdUnidadeGestora").fill("160001")
        page.locator("#txtCdGestao_SIGEFPesquisa").fill("00001")

        # Locators reaproveitados em TODAS as linhas - buscados uma única
        # vez fora do loop (reduz consultas ao DOM e chamadas ao Playwright).
        campo_despesa = page.locator("#txtNuDespesa")
        botao_confirmar = page.locator("#btnConfirmar")
        linhas_grid_link = page.locator("#dtgDespesaCertificada td.GridLink")

        total_processadas = 0

        # ---- Parte em loop até a última linha da planilha ------------------
        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice

            numero_ce_bruto = obter_celula(linha, COL_NL_CE)
            if not numero_ce_bruto:
                log_aviso(f"Linha {numero_linha}: CE vazia. Pulando.")
                continue

            numero_ce_normalizado = normalizar_numero_documento(numero_ce_bruto)
            numero_pesquisa = extrair_numero_documento(numero_ce_bruto).zfill(6)

            log_info(f"Pesquisando CE/NL {numero_ce_normalizado}...")

            try:
                campo_despesa.fill(numero_pesquisa)
                botao_confirmar.click()
                aguardar_pagina_estavel(page)

                registros = ler_tabela_despesa_certificada(page)
                log_info("Tabela carregada.")

                if not registros:
                    log_aviso(
                        f"Linha {numero_linha}: tabela veio vazia para a CE/NL "
                        f"{numero_ce_normalizado}. Pulando para a próxima linha."
                    )
                    continue

                log_info("Comparando registros...")
                indice_encontrado = next(
                    (
                        i for i, registro in enumerate(registros)
                        if normalizar_numero_documento(registro["numero"]) == numero_ce_normalizado
                    ),
                    None,
                )

                if indice_encontrado is None:
                    log_aviso(
                        f"Linha {numero_linha}: nenhum registro correspondente à CE/NL "
                        f"{numero_ce_normalizado} encontrado. Pulando para a próxima linha."
                    )
                    continue

                log_sucesso("Registro encontrado.")
                log_info("Abrindo detalhes...")

                with context.expect_page() as nova_pagina_info:
                    linhas_grid_link.nth(indice_encontrado).click()

                nova_pagina = nova_pagina_info.value
                aguardar_pagina_estavel(nova_pagina)
                nova_pagina.locator("#btnNotaLancamento").click()

                popup_nl = nova_pagina.locator("#dtgNotaLancamento td.GridLink")
                if popup_nl.count() == 0:
                    log_aviso(
                        f"Linha {numero_linha}: nenhuma Nota de Lançamento encontrada para "
                        f"a CE {numero_ce_normalizado}. Pulando para a próxima linha."
                    )
                    nova_pagina.close()
                    page.bring_to_front()
                    continue

                with context.expect_page() as popup_info:
                    popup_nl.first.click()

                pop_up = popup_info.value
                aguardar_pagina_estavel(pop_up)

                ce_capturada = pop_up.locator("#txtDespesaCeritificada").input_value()
                nl_capturada = pop_up.locator("#txtDocumentoOriginal").input_value()
                ne_capturada = pop_up.locator("#txtNotaEmpenhoOriginal").input_value()

                log_sucesso(f"Linha {numero_linha}: CE {ce_capturada} | NL {nl_capturada} | NE {ne_capturada}.")

                # Salva a NL apenas na coluna J (mesma coluna usada pela
                # automação NL).
                salvar_valor_gerado(worksheet, numero_linha, COL_NL_GERADA, nl_capturada, rotulo="Raspar NL")

                pop_up.locator("#btnImpressao_BtnFechar").click()
                pop_up.close()
                nova_pagina.close()
                page.bring_to_front()

                total_processadas += 1

            except PlaywrightTimeoutError as erro:
                log_erro(f"Timeout ao processar a linha {numero_linha} da automação Raspar NL: {erro}")
                continue
            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da automação Raspar NL: {erro}")
                continue

        log_sucesso(
            f"Automação Raspar NL concluída: {total_processadas} de {len(dados)} linha(s) processada(s)."
        )


def ler_tabela_domicilio_bancario(popup: "Page"):
    """
    Lê TODA a grade `#dtgDomicilioBancario` de uma única vez, via
    JavaScript (`evaluate`) - mesmo padrão de
    `ler_tabela_despesa_certificada`: 1 round-trip em vez de 1 chamada ao
    Playwright por célula (a leitura célula a célula era o trecho mais
    lento da PP).

    Devolve apenas as linhas selecionáveis (`td.GridLink`), já sem o
    cabeçalho e sem as linhas vazias (`&nbsp;`) do rodapé da grade. O
    campo `indice` é a posição da linha entre os `td.GridLink` da grade,
    usada depois para clicar sem varrer o DOM de novo.
    """
    return popup.locator("#dtgDomicilioBancario").evaluate("""
        table => [...table.querySelectorAll("td.GridLink")].map((tdBanco, indice) => {
            const celulas = [...tdBanco.closest("tr").querySelectorAll("td")]
                .slice(0, 3)
                .map(td => td.textContent.trim());

            return {
                indice: indice,
                banco: celulas[0] || "",
                agencia: celulas[1] || "",
                conta: celulas[2] || ""
            };
        })
    """)


def ler_tabela_ordem_cronologica(popup: "Page"):
    """
    Lê a grade "Gerar Ordem Cronológica" de uma vez só, via JavaScript -
    mesmo padrão de `ler_tabela_despesa_certificada` e
    `ler_tabela_domicilio_bancario`.

    Para cada linha clicável (`td.GridLink`) devolve a posição (`indice`,
    usada depois para clicar) e o texto inteiro da linha (`texto`), que
    contém os identificadores da NL e da CE - assim a escolha não depende
    de saber a ordem exata das colunas.
    """
    return popup.locator("#divdtgGerarOrdemCronologica").evaluate(r"""
        div => [...div.querySelectorAll("td.GridLink")].map((td, indice) => ({
            indice: indice,
            texto: (td.closest("tr").innerText || "").replace(/\s+/g, " ").trim()
        }))
    """)


def _indice_registro_ordem_cronologica(popup: "Page", numero_nl: str, numero_ce: str,
                                       numero_linha: int):
    """
    Descobre QUAL linha da grade deve ser clicada: aquela que contém, ao
    mesmo tempo, o número da Nota de Lançamento e o da Despesa
    Certificada da planilha.

    Antes a automação clicava sempre na primeira linha (`.first`), o que
    erra sempre que a grade traz mais de um registro (ou quando ainda
    mostra o resultado da pesquisa anterior).

    A comparação ignora prefixo, pontuação e zeros à esquerda (ex:
    "2026NL065995", "065995" e "65995" são o mesmo número).

    Retorna o índice da linha ou None quando nenhuma linha corresponde
    (nesse caso, registra no log o conteúdo do que o SIGEF mostrou).
    """
    nl_alvo = normalizar_numero_documento(numero_nl)
    ce_alvo = normalizar_numero_documento(numero_ce)

    linhas = ler_tabela_ordem_cronologica(popup)

    if not linhas:
        log_aviso(f"Linha {numero_linha}: a grade da ordem cronológica veio vazia.")
        return None

    # Todos os números de cada linha, já sem zeros à esquerda, para comparar
    # com os identificadores da planilha no mesmo formato.
    numeros_por_linha = [
        (
            registro,
            {str(int(numero)) for numero in REGEX_NUMEROS.findall(registro["texto"])},
        )
        for registro in linhas
    ]

    # 1ª escolha: a linha que traz a NL e a CE juntas (identificação exata).
    for registro, numeros in numeros_por_linha:
        if nl_alvo and ce_alvo and nl_alvo in numeros and ce_alvo in numeros:
            return registro["indice"]

    # 2ª escolha: a linha que traz pelo menos um dos dois identificadores.
    for alvo, rotulo in ((nl_alvo, "NL"), (ce_alvo, "CE")):
        if not alvo:
            continue
        for registro, numeros in numeros_por_linha:
            if alvo in numeros:
                log_info(f"Linha {numero_linha}: registro localizado na grade pela {rotulo} {alvo}.")
                return registro["indice"]

    # Nada reconhecido: com uma única linha, ela é a candidata óbvia; com
    # várias, é melhor pular do que gerar a PP do documento errado.
    if len(linhas) == 1:
        log_aviso(
            f"Linha {numero_linha}: não foi possível reconhecer a NL {nl_alvo} / CE {ce_alvo} "
            f"no texto da grade. Como há um único registro, ele será usado."
        )
        return linhas[0]["indice"]

    log_aviso(
        f"Linha {numero_linha}: a grade trouxe {len(linhas)} registros e nenhum bate com a "
        f"NL {nl_alvo} / CE {ce_alvo}. Pulando para não gerar a PP do documento errado."
    )
    for registro in linhas:
        log_aviso(f"   [{registro['indice']}] {registro['texto']}")

    return None


def _selecionar_registro_ordem_cronologica(page: "Page", popup: "Page", registro_grade,
                                           numero_nl: str, numero_ce: str,
                                           numero_linha: int) -> bool:
    """
    Clica no registro da grade "Gerar Ordem Cronológica" e só devolve o
    controle quando a tela principal confirma que recebeu a Nota de
    Lançamento.

    O SIGEF ocasionalmente ignora o primeiro clique (a janela continua
    aberta e a tela principal segue vazia). Antes, a automação seguia
    assim mesmo e o erro só aparecia lá na frente, na comparação do
    domicílio bancário - que então rodava com os dados da linha anterior.
    Agora o clique é repetido até `TENTATIVAS_CLIQUE_GRADE` vezes e a
    linha só prossegue com a confirmação em mãos.

    Retorna True se o registro foi selecionado; False se a linha deve ser
    pulada.
    """
    for tentativa in range(1, TENTATIVAS_CLIQUE_GRADE + 1):
        try:
            # A linha precisa estar VISÍVEL, e não apenas presente no DOM: a
            # grade do SIGEF já existe (com linhas vazias) antes de os dados
            # chegarem.
            registro_grade.first.wait_for(state="visible", timeout=TIMEOUT_CLIQUE_GRADE)

            indice = _indice_registro_ordem_cronologica(popup, numero_nl, numero_ce, numero_linha)
            if indice is None:
                return False

            registro_grade.nth(indice).click()
        except Exception as erro:
            log_aviso(f"Linha {numero_linha}: falha ao clicar no registro (tentativa {tentativa}): {erro}")

        page.bring_to_front()

        if aguardar_campo_com_valor_por_id(page, "NotaLancamento", TIMEOUT_CLIQUE_GRADE):
            # A tela principal só está pronta para a etapa seguinte quando o
            # postback termina E os campos dela aparecem.
            # Não basta o DOM estar pronto: o SIGEF encadeia postbacks aqui, e
            # agir na janela entre eles fazia a automação perder a seleção do
            # Tipo de Ordem Bancária.
            aguardar_pagina_ociosa(page, timeout=TIMEOUT_CLIQUE_GRADE)

            try:
                page.locator("#cboTipoOrdemBancaria").wait_for(
                    state="visible", timeout=TIMEOUT_CLIQUE_GRADE
                )
                return True
            except Exception:
                log_aviso(
                    f"Linha {numero_linha}: a tela de preparação não terminou de carregar "
                    f"após a seleção (tentativa {tentativa} de {TENTATIVAS_CLIQUE_GRADE})."
                )

        log_aviso(
            f"Linha {numero_linha}: o clique no registro não chegou à tela principal "
            f"(tentativa {tentativa} de {TENTATIVAS_CLIQUE_GRADE}). Repetindo."
        )

        if popup.is_closed():
            break
        popup.bring_to_front()

    log_erro(
        f"Linha {numero_linha}: não foi possível selecionar o registro da ordem "
        f"cronológica. Pulando para a próxima linha."
    )
    return False


def _selecionar_domicilio_bancario(page: "Page", context: "BrowserContext",
                                   banco: str, agencia: str, conta: str) -> bool:
    """
    Abre o popup "Pesquisar Domicílio Bancário", pesquisa pelo banco da
    planilha (coluna E) e seleciona a linha em que os TRÊS dados conferem:
    banco (coluna E), agência (coluna F) e conta (coluna G) - todos
    comparados por `normalizar_chave_bancaria`, nunca como texto bruto
    (a planilha traz "1 / 1178-9 / 74.508-1" e o SIGEF mostra
    "001 / 01178-9 / 0000745081").

    Mesmo padrão de `_selecionar_credor_por_cpf` e
    `_selecionar_empenho_por_numero` (popup -> preencher -> confirmar ->
    selecionar item), inclusive no retorno:

        True  -> domicílio encontrado e selecionado.
        False -> nenhuma linha atende aos três critérios; a linha deve
                 ser pulada e a automação segue para a próxima.
    """
    banco_alvo = normalizar_chave_bancaria(banco)
    agencia_alvo = normalizar_chave_bancaria(agencia)
    conta_alvo = normalizar_chave_bancaria(conta)

    with context.expect_page() as popup_info:
        page.locator("#txtConta_BtnPesquisa").click()

    popup = popup_info.value

    campo_banco = popup.locator("#txtCdBanco")
    campo_banco.wait_for(state="visible")
    campo_banco.fill(banco_alvo.zfill(3))

    mensagem_erro = popup.locator("td.SIGEFMensagemErro")
    resultado_grade = popup.locator("#dtgDomicilioBancario td.GridLink")

    popup.locator("#btnConfirmar").click()

    if not _aguardar_resultado_ou_erro_grade(resultado_grade, mensagem_erro):
        log_aviso(
            f"Banco {banco_alvo}: nenhum domicílio bancário listado pelo SIGEF. "
            f"Pulando para a próxima linha."
        )
        fechar_paginas([popup])
        page.bring_to_front()
        return False

    linhas_grade = ler_tabela_domicilio_bancario(popup)

    encontrado = next(
        (
            linha for linha in linhas_grade
            if normalizar_chave_bancaria(linha["banco"]) == banco_alvo
            and normalizar_chave_bancaria(linha["agencia"]) == agencia_alvo
            and normalizar_chave_bancaria(linha["conta"]) == conta_alvo
        ),
        None,
    )

    if encontrado is None:
        # Loga a chave JÁ NORMALIZADA dos dois lados. Comparar os valores
        # brutos no log engana: caracteres diferentes podem ser idênticos na
        # tela (ver `latinizar_homoglifos`). Com as chaves normalizadas dá
        # para ver na hora QUAL dos três campos não bateu.
        disponiveis = " ; ".join(
            f'{normalizar_chave_bancaria(l["banco"])}/'
            f'{normalizar_chave_bancaria(l["agencia"])}/'
            f'{normalizar_chave_bancaria(l["conta"])}'
            for l in linhas_grade
        ) or "(grade vazia)"

        log_aviso(
            f"Domicílio bancário não encontrado (Banco: {banco} | Agência: {agencia} | "
            f"Conta: {conta}). Pulando para a próxima linha."
        )
        log_info(
            f"    planilha (normalizado): {banco_alvo}/{agencia_alvo}/{conta_alvo}\n"
            f"    SIGEF    (normalizado): {disponiveis}"
        )
        fechar_paginas([popup])
        page.bring_to_front()
        return False

    # O clique fecha o popup. NÃO esperar carregamento nele: a aba está
    # sendo destruída e qualquer `wait_for_load_state` fica pendurado até
    # estourar o timeout - espera-se apenas o evento de fechamento.
    resultado_grade.nth(encontrado["indice"]).click()

    try:
        popup.wait_for_event("close", timeout=TIMEOUT_POPUP_FECHAR)
    except Exception:
        pass  # se não fechou sozinho, `fechar_paginas` resolve

    fechar_paginas([popup])
    page.bring_to_front()
    return True


def _ano_do_documento(codigo_completo: str) -> str:
    """
    Devolve o ano (prefixo "AAAA") de um identificador do SIGEF gravado na
    planilha (ex: "2026NL065995" -> "2026"). Quando a célula traz só o
    número, sem prefixo, usa o ano corrente - evita ano fixo no código.
    """
    texto = str(codigo_completo).strip()
    if REGEX_PREFIXO_DOCUMENTO.match(texto):
        return texto[:4]
    return str(datetime.now().year)


def pp(dados, config=None, worksheet=None):
    """
    Automação: PP (Preparação de Pagamento de Despesa Empenhada).

    Fluxo (repetido por completo a cada linha, já que a confirmação e o
    Limpar resetam a tela a cada iteração):
        1. Conecta 1 única vez à aba do SIGEF na tela de preparação de
           pagamento (a única etapa que ocorre 1 única vez).
        2. Para cada linha da planilha: preenche a gestão e a data de
           referência (Data configurada no sistema) e abre a pesquisa de
           Nota de Lançamento.
        3. Na janela de pesquisa, entra em "Não obedece ordem
           cronológica" e informa a NL (coluna J) e a Despesa Certificada
           (coluna I), ambas sem o prefixo "AAAA+sigla", e seleciona o
           registro.
        4. Seleciona o tipo de ordem bancária e escolhe o domicílio
           bancário cujo banco (coluna E), agência (coluna F) e conta
           (coluna G) conferem com a planilha.
        5. Confirma as retenções e o lançamento. Se o SIGEF devolver
           sucesso, grava o número da PP (com prefixo, ex: "2026PP039772")
           na coluna K; se devolver erro (ex: "Saldo insuficiente..."),
           grava a própria mensagem do SIGEF nessa mesma coluna.
        6. Limpa o formulário (`img[src*='Limpar.GIF']`) e segue para a
           próxima linha.
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação PP.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)
    data_referencia = config.get("data", "")

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(p, URL_PP_SIGEF, MARCADOR_URL_PP)
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de preparação de pagamento do SIGEF: {erro}")
            return

        # Locators reaproveitados em TODAS as linhas - buscados uma única
        # vez fora do loop (reduz consultas ao DOM e chamadas ao Playwright).
        campo_gestao = page.locator("#txtGestao_SIGEFPesquisa")
        campo_data_referencia = page.locator("#txtDataReferencia_SIGEFData")
        botao_pesquisar_nl = page.locator("#txtNotaLancamento_BtnPesquisa")
        combo_tipo_ordem = page.locator("#cboTipoOrdemBancaria")

        # Clica em "Limpar" assim que a página carrega, antes de começar o
        # loop - garante que o formulário comece limpo, mesmo que a aba
        # reaproveitada tenha ficado com dados de uma execução anterior.
        try:
            limpar_formulario(page)
        except Exception as erro:
            log_aviso(f"Não foi possível clicar em Limpar ao iniciar a PP: {erro}")

        total_processadas = 0

        # ---- Parte em loop até a última linha da planilha ------------------
        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice
            janelas = []

            numero_nl = obter_celula(linha, COL_PP_NL)
            numero_ce = obter_celula(linha, COL_PP_CE)
            banco = obter_celula(linha, COL_PP_BANCO)
            agencia = obter_celula(linha, COL_PP_AGENCIA)
            conta = obter_celula(linha, COL_PP_CONTA)

            if not numero_nl or not numero_ce:
                log_aviso(f"Linha {numero_linha}: NL ou CE vazia. Pulando.")
                continue

            if not banco or not agencia or not conta:
                log_aviso(f"Linha {numero_linha}: banco, agência ou conta vazio. Pulando.")
                continue

            try:
                campo_gestao.fill("00001")
                campo_data_referencia.fill(data_referencia)

                with context.expect_page() as pagina_pesquisa_info:
                    botao_pesquisar_nl.click()

                pagina_pesquisa = pagina_pesquisa_info.value
                janelas.append(pagina_pesquisa)

                # Espera o link que será usado, em vez de esperar a rede parar.
                link_fora_ordem = pagina_pesquisa.locator("#lnkNaoObedeceOrdemCronologica")
                link_fora_ordem.wait_for(state="visible")

                with context.expect_page() as pagina_lancamento_info:
                    link_fora_ordem.click()

                pagina_lancamento = pagina_lancamento_info.value
                janelas.append(pagina_lancamento)

                campo_sigla_nl = pagina_lancamento.locator("#txtNotaLancamentoSigla")
                campo_sigla_nl.wait_for(state="visible")

                campo_sigla_nl.fill(_ano_do_documento(numero_nl))
                pagina_lancamento.locator("#txtDespesaCertificadaSigla").fill(_ano_do_documento(numero_ce))
                pagina_lancamento.locator("#txtNotaLancamento_SIGEFPesquisa").fill(
                    extrair_numero_documento(numero_nl).zfill(6)
                )
                pagina_lancamento.locator("#txtDespesaCertificada_SIGEFPesquisa").fill(
                    extrair_numero_documento(numero_ce).zfill(6)
                )
                pagina_lancamento.locator("#btnConfirmar").click()

                # Espera o postback da pesquisa terminar e a GRADE existir na
                # tela antes de qualquer leitura ou clique - sem isso, a
                # comparação rodava com a tabela ainda vazia.
                aguardar_pagina_estavel(pagina_lancamento)
                pagina_lancamento.wait_for_selector(
                    "#divdtgGerarOrdemCronologica", timeout=TIMEOUT_PADRAO_SIGEF
                )

                registro_grade = pagina_lancamento.locator("#divdtgGerarOrdemCronologica td.GridLink")
                mensagem_erro_grade = pagina_lancamento.locator("td.SIGEFMensagemErro")

                if not _aguardar_resultado_ou_erro_grade(registro_grade, mensagem_erro_grade):
                    log_aviso(
                        f"Linha {numero_linha}: nenhuma preparação encontrada para a NL "
                        f"{numero_nl} / CE {numero_ce}. Pulando para a próxima linha."
                    )
                    fechar_paginas(janelas)
                    page.bring_to_front()
                    continue

                if not _selecionar_registro_ordem_cronologica(
                    page, pagina_lancamento, registro_grade,
                    numero_nl, numero_ce, numero_linha
                ):
                    fechar_paginas(janelas)
                    limpar_formulario(page)
                    continue

                fechar_paginas(janelas)
                page.bring_to_front()

                if not selecionar_combo_com_conferencia(page, combo_tipo_ordem, TIPO_ORDEM_BANCARIA_PP):
                    log_erro(
                        f"Linha {numero_linha}: não foi possível selecionar o Tipo de Ordem "
                        f"Bancária. Pulando para a próxima linha."
                    )
                    limpar_formulario(page)
                    continue

                # Última conferência antes de abrir a pesquisa da conta: se um
                # postback tardio limpou o combo, a seleção é refeita.
                if combo_tipo_ordem.input_value() != TIPO_ORDEM_BANCARIA_PP:
                    log_aviso(
                        f"Linha {numero_linha}: o Tipo de Ordem Bancária foi limpo por um "
                        f"recarregamento da tela. Selecionando novamente."
                    )
                    if not selecionar_combo_com_conferencia(page, combo_tipo_ordem, TIPO_ORDEM_BANCARIA_PP):
                        log_erro(
                            f"Linha {numero_linha}: não foi possível manter o Tipo de Ordem "
                            f"Bancária selecionado. Pulando para a próxima linha."
                        )
                        limpar_formulario(page)
                        continue

                if not _selecionar_domicilio_bancario(page, context, banco, agencia, conta):
                    fechar_paginas(janelas)
                    limpar_formulario(page)
                    continue

                # Cada clique espera apenas o elemento SEGUINTE aparecer.
                clicar_e_aguardar_elemento(page, "#btnRetencoes", "img[src*='aba_confirmacao.gif']")
                clicar_e_aguardar_elemento(page, "img[src*='aba_confirmacao.gif']", "#btnConfirmar")

                # Depois deste clique, quem manda é o `wait_for_selector` abaixo.
                clicar_e_aguardar_elemento(page, "#btnConfirmar")

                page.wait_for_selector(
                    "td.SIGEFMensagemSucesso, td.SIGEFMensagemErro",
                    timeout=TIMEOUT_PADRAO_SIGEF,
                )

                if page.locator("td.SIGEFMensagemErro").count() > 0:
                    # O SIGEF recusou o lançamento (ex: saldo insuficiente ou
                    # data de referência anterior à da NE/NL). O motivo vai
                    # para a coluna K, para aparecer na planilha.
                    mensagem_erro = page.locator("td.SIGEFMensagemErro").first.inner_text().strip()
                    log_erro(f"Linha {numero_linha}: SIGEF recusou a PP - {mensagem_erro}")
                    atualizar_status(worksheet, numero_linha, COL_PP_GERADA, mensagem_erro)
                    limpar_formulario(page)
                    continue

                mensagem_sucesso = page.locator("td.SIGEFMensagemSucesso").first.inner_text().strip()
                busca_pp = REGEX_DOCUMENTO_PP.search(mensagem_sucesso)

                if busca_pp is None:
                    log_erro(
                        f"Linha {numero_linha}: não foi possível extrair o número da PP "
                        f"da mensagem do SIGEF ({mensagem_sucesso})."
                    )
                    limpar_formulario(page)
                    continue

                numero_pp = busca_pp.group(0).upper()
                log_sucesso(f"Linha {numero_linha}: PP '{numero_pp}' gerada.")
                salvar_valor_gerado(worksheet, numero_linha, COL_PP_GERADA, numero_pp, rotulo="PP")
                total_processadas += 1

                # Limpa o formulário antes de reiniciar o loop na próxima linha.
                limpar_formulario(page)

            except PlaywrightTimeoutError as erro:
                log_erro(f"Timeout ao processar a linha {numero_linha} da automação PP: {erro}")
                fechar_paginas(janelas)
                page.bring_to_front()
                try:
                    limpar_formulario(page)
                except Exception as erro_limpar:
                    log_aviso(f"Linha {numero_linha}: não foi possível clicar em Limpar após o timeout: {erro_limpar}")
                continue

            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da automação PP: {erro}")
                fechar_paginas(janelas)
                page.bring_to_front()
                try:
                    limpar_formulario(page)
                except Exception:
                    pass
                continue

        log_sucesso(
            f"Automação PP concluída: {total_processadas} de {len(dados)} linha(s) processada(s)."
        )


def ler_tabela_pp_geral(page: "Page"):
    """
    Lê de uma vez só a grade `#dtgPP` da tela "Listar Preparação Pagamento
    Geral" - mesmo padrão de `ler_tabela_despesa_certificada` e
    `ler_tabela_domicilio_bancario`: 1 round-trip em vez de 1 chamada ao
    Playwright por célula.

    Devolve, para cada linha clicável (`td.GridLink`):

        indice  - posição na grade, usada depois para clicar sem varrer o
                  DOM de novo.
        texto   - texto da célula clicável, que traz o identificador da PP
                  no formato "AAAAPPnnnnnn" (usado pela Raspar contas).
        celulas - texto de TODAS as células VISÍVEIS da linha (usado pela
                  Raspar PP, que procura o valor da coluna H sem depender
                  da posição fixa da coluna na grade). O filtro
                  `offsetParent !== null` descarta as células ocultas que
                  o SIGEF mantém no HTML.
    """
    return page.locator("#dtgPP").evaluate("""
        table => [...table.querySelectorAll("td.GridLink")].map((td, indice) => ({
            indice: indice,
            texto: (td.textContent || "").trim(),
            celulas: [...td.closest("tr").cells]
                .filter(celula => celula.offsetParent !== null)
                .map(celula => celula.innerText.trim())
        }))
    """)


def _selecionar_favorecido_por_cpf(page: "Page", context: "BrowserContext",
                                   cpf: str) -> bool:
    """
    Seleciona o favorecido pelo CPF na tela "Listar Preparação Pagamento
    Geral".

    NÃO reaproveita `_selecionar_credor_por_cpf` porque esta tela tem um
    passo a mais: o primeiro popup (`#txtFavorecido_BtnPesquisa`) abre uma
    lista genérica, e é o link `#lnkPesquisaCNPJCPFIG` que abre o popup de
    pesquisa por CPF - fechando o primeiro no processo. Por isso o clique
    no link é protegido: o Playwright pode acusar "target closed" quando a
    própria aba que recebeu o clique é destruída, e isso é o comportamento
    esperado, não um erro.

    Retorna:
        True  -> favorecido encontrado e selecionado.
        False -> a pesquisa não retornou nenhuma linha; a linha da
                 planilha deve ser pulada.
    """
    # O campo do SIGEF nesta tela aceita o CPF apenas com dígitos.
    cpf_digitos = REGEX_APENAS_DIGITOS.sub("", str(cpf))

    with context.expect_page() as popup_info:
        page.locator("#txtFavorecido_BtnPesquisa").click()

    popup = popup_info.value
    aguardar_pagina_estavel(popup)

    with context.expect_page() as popup_cpf_info:
        try:
            popup.locator("#lnkPesquisaCNPJCPFIG").click()
        except PlaywrightError as erro:
            # "closed"/"target closed" aqui é normal: o clique destrói a
            # própria aba. Qualquer outro erro é problema de verdade.
            if "closed" not in str(erro).lower():
                raise

    popup_cpf = popup_cpf_info.value
    aguardar_pagina_estavel(popup_cpf)

    popup_cpf.locator("#btnCPF").click()
    popup_cpf.locator("#txtNuCpf").fill(cpf_digitos)

    mensagem_erro = popup_cpf.locator("td.SIGEFMensagemErro")
    resultado_grade = popup_cpf.locator(
        "#dtgCredor tbody tr:not(.GridCabecalho) td.GridLink"
    )

    popup_cpf.locator("#btnConfirmar").click()

    if not _aguardar_resultado_ou_erro_grade(resultado_grade, mensagem_erro):
        log_aviso(
            f"CPF {cpf_digitos}: nenhum favorecido encontrado no SIGEF. "
            f"Pulando para a próxima linha."
        )
        fechar_paginas([popup_cpf, popup])
        page.bring_to_front()
        return False

    resultado_grade.first.click()
    fechar_paginas([popup_cpf, popup])
    page.bring_to_front()
    return True


def _valor_planilha_para_float(valor) -> float:
    """
    Converte o valor da planilha (coluna H) para float em reais.

    A planilha guarda "840" querendo dizer R$ 840,00, enquanto a grade do
    SIGEF exibe "840,00" - sem essa conversão a comparação nunca bateria.
    Reaproveita `formatar_valor_centavos`, que já é a regra oficial do
    sistema para ler esse formato (e também aceita "1.400,00" e "1400,00").
    """
    return int(formatar_valor_centavos(valor)) / 100


def _linha_grade_tem_valor(celulas, valor_esperado: float) -> bool:
    """
    Diz se alguma célula VISÍVEL da linha da grade é o valor esperado.

    Procura em TODAS as células em vez de olhar uma posição fixa: assim a
    automação não quebra se o SIGEF mudar a ordem das colunas da grade.
    Só tenta converter as células que têm cara de valor monetário BR
    (`REGEX_VALOR_BR`), e a comparação usa tolerância de meio centavo,
    porque float não é exato.
    """
    for celula in celulas:
        texto = str(celula).replace("R$", "").strip()
        if REGEX_VALOR_BR.match(texto):
            if abs(_valor_br_para_float(texto) - valor_esperado) < 0.005:
                return True
    return False


def raspar_pp(dados, config=None, worksheet=None):
    """
    Automação: Raspar PP (Listar Preparação Pagamento Geral).

    Recupera a PP que já foi gerada no SIGEF para cada linha da planilha -
    útil quando a automação PP rodou mas o número não chegou a ser gravado
    (queda de conexão, execução manual etc.).

    Fluxo:
        1. Conecta 1 única vez à tela "Listar Preparação Pagamento Geral".
        2. Para cada linha da planilha:
           a. Preenche a parte fixa (unidade gestora 160001 / gestão 00001).
           b. Pesquisa e seleciona o favorecido pelo CPF (coluna B) e
              confirma - o SIGEF lista TODAS as PPs daquele favorecido.
           c. Procura na grade a(s) linha(s) cujo valor bate com a coluna H.
              Havendo mais de uma, usa a ÚLTIMA (a mais recente).
           d. Abre o detalhe e captura CE, NL e PP.
           e. Se CE e NL conferem com as colunas I e J, grava a PP na
              coluna K e a mensagem de conferência na coluna M. Se NÃO
              conferem, NÃO grava a PP - apenas registra a divergência.
        3. Erro em uma linha nunca interrompe a automação - registra e
           segue para a próxima.

    Toda comparação é feita sobre valores normalizados, nunca texto bruto:
    números de documento por `normalizar_numero_documento` (que resolve o
    "18487" da planilha contra o "2026CE018487" do SIGEF) e valores por
    `_valor_planilha_para_float` (que resolve o "840" contra "840,00").
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação Raspar PP.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(
                p, URL_RASPAR_CONTA_SIGEF, MARCADOR_URL_RASPAR_CONTA
            )
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de listagem de PP do SIGEF: {erro}")
            return

        campo_unidade_gestora = page.locator("#txtUnidadeGestora")
        campo_gestao = page.locator("#txtGestao_SIGEFPesquisa")
        botao_confirmar = page.locator("#btnConfirmar")
        linhas_grid_link = page.locator("#dtgPP td.GridLink")

        total_processadas = 0
        total_correspondentes = 0
        total_divergentes = 0

        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice

            cpf = obter_celula(linha, COL_RASPAR_PP_CPF)
            valor_bruto = obter_celula(linha, COL_RASPAR_PP_VALOR)
            ce_esperada = obter_celula(linha, COL_RASPAR_PP_CE)
            nl_esperada = obter_celula(linha, COL_RASPAR_PP_NL)

            if not cpf or not valor_bruto:
                log_aviso(f"Linha {numero_linha}: CPF ou valor (coluna H) vazio. Pulando.")
                continue

            if not ce_esperada or not nl_esperada:
                log_aviso(
                    f"Linha {numero_linha}: CE (coluna I) ou NL (coluna J) vazia - "
                    f"sem elas não há como conferir a PP. Pulando."
                )
                continue

            try:
                valor_esperado = _valor_planilha_para_float(valor_bruto)
            except (ValueError, TypeError):
                log_aviso(
                    f"Linha {numero_linha}: valor '{valor_bruto}' (coluna H) não é "
                    f"numérico. Pulando."
                )
                continue

            log_info(
                f"Linha {numero_linha}: procurando PP de {formatar_valor_br(valor_bruto)} "
                f"para o CPF {formatar_cpf(cpf)}..."
            )

            try:
                # Parte fixa refeita A CADA linha: a tela faz postback ao
                # confirmar e ao selecionar o favorecido, e os campos podem
                # voltar em branco.
                campo_unidade_gestora.fill("160001")
                campo_gestao.fill("00001")

                if not _selecionar_favorecido_por_cpf(page, context, cpf):
                    continue

                botao_confirmar.click()
                aguardar_pagina_estavel(page)

                registros = ler_tabela_pp_geral(page)
                if not registros:
                    log_aviso(
                        f"Linha {numero_linha}: nenhuma PP listada para este favorecido. "
                        f"Pulando para a próxima linha."
                    )
                    continue

                candidatos = [
                    registro for registro in registros
                    if len(registro["celulas"]) > 1
                    and _linha_grade_tem_valor(registro["celulas"], valor_esperado)
                ]

                if not candidatos:
                    log_aviso(
                        f"Linha {numero_linha}: nenhuma PP na grade com o valor "
                        f"{formatar_valor_br(valor_bruto)}. Pulando para a próxima linha."
                    )
                    continue

                # Havendo mais de uma PP com o mesmo valor, a ÚLTIMA da grade
                # é a mais recente - é ela que interessa.
                escolhido = candidatos[-1]
                if len(candidatos) > 1:
                    log_aviso(
                        f"Linha {numero_linha}: {len(candidatos)} PPs com o valor "
                        f"{formatar_valor_br(valor_bruto)}. Usando a última (mais recente)."
                    )

                with context.expect_page() as detalhe_info:
                    linhas_grid_link.nth(escolhido["indice"]).click()

                detalhe = detalhe_info.value
                aguardar_pagina_estavel(detalhe)

                ce_sigef = detalhe.locator("#txtNuDespesaCertificada").input_value()
                nl_sigef = detalhe.locator("#txtNotaLancamento").input_value()
                pp_sigef = detalhe.locator("#txtNuPreparacaoPagamento").input_value()

                try:
                    detalhe.locator("#SIGEFBotoesImpressao_BtnFechar").click()
                except Exception:
                    # O botão pode não estar presente/visível; `fechar_paginas`
                    # encerra a aba de qualquer forma.
                    pass
                fechar_paginas([detalhe])
                page.bring_to_front()

                ce_confere = (
                    normalizar_numero_documento(ce_sigef)
                    == normalizar_numero_documento(ce_esperada)
                )
                nl_confere = (
                    normalizar_numero_documento(nl_sigef)
                    == normalizar_numero_documento(nl_esperada)
                )

                if ce_confere and nl_confere:
                    log_sucesso(
                        f"Linha {numero_linha}: {pp_sigef} corresponde à CE e NL da planilha."
                    )
                    salvar_valor_gerado(
                        worksheet, numero_linha, COL_PP_GERADA, pp_sigef, rotulo="Raspar PP"
                    )
                    atualizar_status(
                        worksheet, numero_linha, COL_RASPAR_PP_OBSERVACAO,
                        f"PP {pp_sigef} correspondente à CE {ce_sigef} e NL {nl_sigef}"
                    )
                    total_correspondentes += 1
                else:
                    # PP divergente NÃO vai para a coluna K - gravar um número
                    # errado ali contaminaria as automações seguintes, que
                    # leem essa coluna.
                    divergencias = []
                    if not ce_confere:
                        divergencias.append(f"CE {ce_sigef} != {ce_esperada}")
                    if not nl_confere:
                        divergencias.append(f"NL {nl_sigef} != {nl_esperada}")

                    log_aviso(
                        f"Linha {numero_linha}: {pp_sigef} NÃO corresponde à CE e NL da "
                        f"planilha ({'; '.join(divergencias)}). PP não gravada na coluna K."
                    )
                    atualizar_status(
                        worksheet, numero_linha, COL_RASPAR_PP_OBSERVACAO,
                        f"PP {pp_sigef} NÃO corresponde: {'; '.join(divergencias)}"
                    )
                    total_divergentes += 1

                total_processadas += 1

            except PlaywrightTimeoutError as erro:
                log_erro(f"Timeout ao processar a linha {numero_linha} da Raspar PP: {erro}")
                continue
            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da Raspar PP: {erro}")
                continue

        log_sucesso(
            f"Automação Raspar PP concluída: {total_processadas} de {len(dados)} "
            f"linha(s) processada(s) - {total_correspondentes} correspondente(s) e "
            f"{total_divergentes} divergente(s)."
        )


def raspar_conta(dados, config=None, worksheet=None):
    """
    Automação: Raspar contas (Listar Preparação Pagamento Geral).

    Confere se o domicílio bancário que ficou gravado em cada PP no SIGEF
    é o mesmo que está na planilha - ou seja, é a conferência DEPOIS do
    fato, complementando a validação que a automação PP faz ANTES de
    gerar o documento.

    Fluxo:
        1. Conecta 1 única vez à tela "Listar Preparação Pagamento Geral".
        2. Para cada linha da planilha:
           a. Preenche a parte fixa (unidade gestora 160001 / gestão 00001)
              e o número da PP da coluna K, já sem o prefixo "AAAAPP", e
              confirma.
           b. Lê a grade `#dtgPP` e procura a linha cujo valor bate com a
              coluna H. Se NENHUMA bater, usa a PRIMEIRA linha da grade -
              a pesquisa já foi filtrada pelo número exato da PP, então a
              grade normalmente traz só ela; o casamento pelo valor é uma
              conferência a mais, não um filtro que possa descartar a
              linha certa.
           c. Abre o detalhe da PP e captura banco, agência e conta.
           d. Grava os três na coluna M e escreve "Igual"/"Diferente" na
              coluna N, comparando com as colunas E, F e G.
        3. Erro em uma linha nunca interrompe a automação - registra e
           segue para a próxima.

    A comparação usa `normalizar_chave_bancaria` nos dois lados (nunca
    texto bruto): a planilha traz "1 / 0951-2 / 81.590-X" e o SIGEF
    devolve "001 / 009512 / 000081590X".
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação Raspar contas.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(
                p, URL_RASPAR_CONTA_SIGEF, MARCADOR_URL_RASPAR_CONTA
            )
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de listagem de PP do SIGEF: {erro}")
            return

        # Locators reaproveitados em TODAS as linhas - buscados uma única
        # vez fora do loop (reduz consultas ao DOM).
        campo_unidade_gestora = page.locator("#txtUnidadeGestora")
        campo_gestao = page.locator("#txtGestao_SIGEFPesquisa")
        campo_pp = page.locator("#txtPrepPagSeq")
        botao_confirmar = page.locator("#btnConfirmar")
        linhas_grid_link = page.locator("#dtgPP td.GridLink")

        total_processadas = 0
        total_iguais = 0
        total_diferentes = 0

        for indice, linha in enumerate(dados):
            numero_linha = linha_inicial + indice

            pp_bruta = obter_celula(linha, COL_RASPAR_CONTA_PP)
            if not pp_bruta:
                log_aviso(f"Linha {numero_linha}: PP (coluna K) vazia. Pulando.")
                continue

            pp_pesquisa = extrair_numero_documento(pp_bruta).zfill(6)

            # O valor da coluna H é opcional aqui: serve só para escolher a
            # linha certa quando a grade traz mais de uma. Sem ele (ou se
            # não for numérico), cai no comportamento padrão de usar a
            # primeira linha.
            valor_bruto = obter_celula(linha, COL_RASPAR_CONTA_VALOR)
            try:
                valor_esperado = _valor_planilha_para_float(valor_bruto) if valor_bruto else None
            except (ValueError, TypeError):
                valor_esperado = None

            log_info(f"Linha {numero_linha}: conferindo a PP {pp_bruta}...")

            try:
                # Parte fixa preenchida A CADA linha (e não uma única vez
                # fora do loop): a tela faz postback ao confirmar, e os
                # campos podem voltar em branco. Preencher de novo é barato
                # e evita pesquisar na unidade gestora errada.
                campo_unidade_gestora.fill("160001")
                campo_gestao.fill("00001")
                campo_pp.fill(pp_pesquisa)

                botao_confirmar.click()
                aguardar_pagina_estavel(page)

                registros = ler_tabela_pp_geral(page)
                if not registros:
                    log_aviso(
                        f"Linha {numero_linha}: grade vazia para a PP "
                        f"{pp_bruta}. Pulando para a próxima linha."
                    )
                    continue

                escolhido = None
                if valor_esperado is not None:
                    escolhido = next(
                        (
                            registro for registro in registros
                            if len(registro["celulas"]) > 1
                            and _linha_grade_tem_valor(registro["celulas"], valor_esperado)
                        ),
                        None,
                    )

                if escolhido is None:
                    # Fallback previsto: usa a primeira linha da grade.
                    escolhido = registros[0]
                    if valor_esperado is not None:
                        log_aviso(
                            f"Linha {numero_linha}: nenhuma linha da grade com o valor "
                            f"{formatar_valor_br(valor_bruto)}. Usando a primeira linha "
                            f"({escolhido['texto']})."
                        )

                with context.expect_page() as detalhe_info:
                    linhas_grid_link.nth(escolhido["indice"]).click()

                detalhe = detalhe_info.value
                aguardar_pagina_estavel(detalhe)

                banco = detalhe.locator("#txtDomicilioBancarioBanco").input_value()
                agencia = detalhe.locator("#txtDomicilioBancarioAgencia").input_value()
                conta = detalhe.locator("#txtDomicilioBancarioConta").input_value()

                try:
                    detalhe.locator("#SIGEFBotoesImpressao_BtnFechar").click()
                except Exception:
                    # O botão pode não estar presente/visível; o
                    # `fechar_paginas` abaixo encerra a aba de qualquer forma.
                    pass
                fechar_paginas([detalhe])
                page.bring_to_front()

                # ---- Grava o que o SIGEF devolveu (coluna M) --------------
                domicilio_sigef = f"{banco} / {agencia} / {conta}"
                salvar_valor_gerado(
                    worksheet, numero_linha, COL_RASPAR_CONTA_RESULTADO,
                    domicilio_sigef, rotulo="Domicílio (SIGEF)"
                )

                # ---- Compara com a planilha (colunas E, F e G) ------------
                banco_planilha = obter_celula(linha, COL_RASPAR_CONTA_BANCO)
                agencia_planilha = obter_celula(linha, COL_RASPAR_CONTA_AGENCIA)
                conta_planilha = obter_celula(linha, COL_RASPAR_CONTA_CONTA)

                divergencias = [
                    rotulo
                    for rotulo, do_sigef, da_planilha in (
                        ("banco", banco, banco_planilha),
                        ("agência", agencia, agencia_planilha),
                        ("conta", conta, conta_planilha),
                    )
                    if normalizar_chave_bancaria(do_sigef)
                    != normalizar_chave_bancaria(da_planilha)
                ]

                if divergencias:
                    resultado = "Diferente"
                    total_diferentes += 1
                    log_aviso(
                        f"Linha {numero_linha}: DIFERENTE em {', '.join(divergencias)}. "
                        f"SIGEF: {domicilio_sigef} | planilha: "
                        f"{banco_planilha} / {agencia_planilha} / {conta_planilha}"
                    )
                else:
                    resultado = "Igual"
                    total_iguais += 1
                    log_sucesso(f"Linha {numero_linha}: IGUAL ({domicilio_sigef}).")

                atualizar_status(
                    worksheet, numero_linha, COL_RASPAR_CONTA_CONFERENCIA, resultado
                )

                total_processadas += 1

            except PlaywrightTimeoutError as erro:
                log_erro(f"Timeout ao processar a linha {numero_linha} da Raspar contas: {erro}")
                continue
            except Exception as erro:
                log_erro(f"Erro ao processar a linha {numero_linha} da Raspar contas: {erro}")
                continue

        log_sucesso(
            f"Automação Raspar contas concluída: {total_processadas} de "
            f"{len(dados)} linha(s) processada(s) - {total_iguais} igual(is) e "
            f"{total_diferentes} diferente(s)."
        )


def _cpf_para_comparacao_ob(valor) -> str:
    """
    Normaliza um CPF (vindo da planilha OU da grade do SIGEF) para 11
    dígitos, sem pontuação/máscara, com zeros à esquerda preservados -
    usado só para COMPARAR os dois lados. Para digitar num campo do
    SIGEF, use `formatar_cpf` (devolve com máscara XXX.XXX.XXX-XX).
    """
    digitos = REGEX_APENAS_DIGITOS.sub("", str(valor or ""))
    return digitos.zfill(11) if digitos else ""


def _ler_grade_ob(popup: "Page") -> List[dict]:
    """
    Lê a grade `#dtgPrepPgto` (Preparação de Pagamento) inteira em UMA
    chamada JS, em vez de 1 chamada Playwright por célula. Índices de
    célula (6=PP, 13=Favorecido/CPF, 15=Valor) conferidos no HTML da
    tela "Manter Ordem Bancária" > "Adicionar" (mesmo esquema usado pelo
    `_localizar_registro_pp` do pacote `sigef_automacao`, que só
    precisava de PP e Valor).
    """
    return popup.evaluate(
        """
        () => {
            const linhas = document.querySelectorAll("tr.GridLinhaPar, tr.GridLinhaImpar");
            return [...linhas].map((linha, indice) => {
                const celulas = [...linha.querySelectorAll("td")].map(td => td.innerText.trim());
                return { indice: indice, pp: celulas[6] || "", cpf: celulas[13] || "", valor: celulas[15] || "" };
            });
        }
        """
    )


def _buscar_item_na_grade_ob(grade: List[dict], item: dict) -> Optional[dict]:
    """
    Só considera um registro da grade como "o item da planilha" quando os
    TRÊS critérios batem ao mesmo tempo: PP, CPF do favorecido e Valor -
    todos padronizados antes de comparar, reaproveitando as MESMAS
    funções já usadas por Raspar PP/Raspar contas para os mesmos dados:
    `_valor_br_para_float` (valor da grade, com separador BR) e
    `_valor_planilha_para_float` (valor da planilha, coluna H, em reais -
    NÃO usar `normalizar_valor_sigef` aqui, que trataria um "1330" da
    planilha como centavos e devolveria 13,30 em vez de 1.330,00).
    """
    valor_esperado = _valor_planilha_para_float(item["valor"])
    cpf_esperado = _cpf_para_comparacao_ob(item["cpf_esperado"])

    for linha in grade:
        if linha["pp"] != item["pp_esperado"]:
            continue
        if _cpf_para_comparacao_ob(linha["cpf"]) != cpf_esperado:
            continue
        try:
            valor_grade = _valor_br_para_float(linha["valor"])
        except (ValueError, TypeError):
            continue
        if abs(valor_grade - valor_esperado) < 0.01:
            return linha
    return None


def _marcar_checkbox_ob(popup: "Page", indice: int) -> bool:
    """Marca `#chk{indice}` da grade, com retentativas - a grade às vezes
    engole o 1º clique (mesmo comportamento já visto em outras telas do
    SIGEF, ver `TENTATIVAS_CLIQUE_GRADE`)."""
    checkbox = popup.locator(f"#chk{indice}")
    for _ in range(TENTATIVAS_CLIQUE_GRADE):
        try:
            checkbox.wait_for(state="visible", timeout=TIMEOUT_CLIQUE_GRADE)
            if checkbox.is_checked():
                return True
            checkbox.click()
            popup.wait_for_timeout(150)
            if checkbox.is_checked():
                return True
        except Exception:
            pass
    log_aviso(f"Não foi possível confirmar a marcação de #chk{indice} após {TENTATIVAS_CLIQUE_GRADE} tentativa(s).")
    return False


def _avancar_pagina_ob(popup: "Page") -> bool:
    """Clica em 'Próxima página' (`#pagFormulario_BtnProximo`). Retorna
    False se o botão não existir ou o clique falhar - tratado como 'não
    há mais páginas' por `_montar_lote_ob`."""
    botao = popup.locator("#pagFormulario_BtnProximo")
    if botao.count() == 0:
        return False
    try:
        botao.click()
    except Exception:
        return False

    aguardar_pagina_estavel(popup)
    try:
        popup.wait_for_selector("tr.GridLinhaPar, tr.GridLinhaImpar", timeout=TIMEOUT_PADRAO_SIGEF)
    except Exception:
        return False
    return True


def _anotar_falha_ob(worksheet, item: dict, motivo: str) -> None:
    """Grava o motivo da falha na coluna L da linha (mesma coluna usada
    para o número da OB quando dá certo) - a planilha fica com o
    histórico completo de cada linha, tenha ela entrado numa OB ou não."""
    mensagem = (
        f"{motivo} (PP {item['pp_esperado']}, CPF {formatar_cpf(item['cpf_esperado'])}, "
        f"valor {formatar_valor_br(item['valor'])})"
    )
    log_erro(f"Linha {item['numero_linha']}: {mensagem}")
    atualizar_status(worksheet, item["numero_linha"], COL_OB_GERADA, mensagem)


def _abastecer_lote_ob(dados: List, cursor: int, linha_inicial: int,
                        pendentes_atual: List[dict], faltam: int) -> tuple:
    """
    Garante que `pendentes_atual` tenha pelo menos `faltam` itens,
    puxando novas linhas VÁLIDAS (com PP, CPF e valor preenchidos) da
    planilha a partir de `cursor`. Linhas inválidas (algum campo vazio)
    são só puladas - não contam para o lote nem são anotadas como falha.
    """
    pendentes = list(pendentes_atual)
    while len(pendentes) < faltam and cursor < len(dados):
        linha = dados[cursor]
        numero_linha = linha_inicial + cursor
        cursor += 1

        pp_esperado = obter_celula(linha, COL_OB_PP_ESPERADO)
        cpf_esperado = obter_celula(linha, COL_OB_CPF)
        valor_bruto = obter_celula(linha, COL_OB_VALOR)
        if not pp_esperado or not cpf_esperado or not valor_bruto:
            log_aviso(f"Linha {numero_linha}: PP (coluna K), CPF (coluna B) ou valor "
                      f"(coluna H) vazio. Pulando.")
            continue

        pendentes.append({
            "numero_linha": numero_linha,
            "pp_esperado": pp_esperado,
            "cpf_esperado": cpf_esperado,
            "valor": valor_bruto,
        })
    return pendentes, cursor


def _montar_lote_ob(popup: "Page", dados: List, cursor: int, linha_inicial: int, worksheet) -> tuple:
    """
    Monta e marca (via checkbox) até `TAMANHO_LOTE_OB` itens confirmados
    na grade `popup`, avançando páginas (`_avancar_pagina_ob`) e repondo
    com novas linhas da planilha (`_abastecer_lote_ob`) sempre que um
    item não é encontrado - assim um lote só fecha com MENOS itens que
    `TAMANHO_LOTE_OB` se a planilha realmente acabar ou a busca esgotar
    as páginas disponíveis.

    Retorna (confirmados, cursor_atualizado). `confirmados` é a lista de
    dicts (mesma forma de `_abastecer_lote_ob`) cujo checkbox já foi
    marcado na grade.

    LOOP: laço de BUSCA/PAGINAÇÃO deste lote (`while True`), com 5
    condições de saída - nunca infinito, porque a cada volta ou marca
    item(ns), ou avança de página, ou encerra por uma das condições
    abaixo:
        1. já confirmou os `TAMANHO_LOTE_OB` itens do lote;
        2. a planilha acabou e não sobrou item pendente para repor;
        3. não há botão de próxima página (ou o clique falhou);
        4. a página seguinte é IDÊNTICA a uma já vista (a paginação deu
           volta ou parou de avançar de verdade);
        5. limite de segurança `MAX_PAGINAS_LOTE_OB` atingido.
    """
    confirmados: List[dict] = []
    pendentes, cursor = _abastecer_lote_ob(dados, cursor, linha_inicial, [], TAMANHO_LOTE_OB)
    paginas_vistas = set()

    while True:
        try:
            popup.wait_for_selector("tr.GridLinhaPar, tr.GridLinhaImpar", timeout=TIMEOUT_PADRAO_SIGEF)
        except Exception:
            log_erro("A grade de itens (Preparação de Pagamento) não apareceu na tela.")
            for item in pendentes:
                _anotar_falha_ob(worksheet, item, "Grade de itens não carregou.")
            break

        grade = _ler_grade_ob(popup)

        assinatura = tuple((linha["pp"], linha["valor"]) for linha in grade)
        if assinatura in paginas_vistas:
            log_aviso("A grade repetiu uma página já vista (fim da paginação). Encerrando busca deste lote.")
            for item in pendentes:
                _anotar_falha_ob(worksheet, item, "PP não localizado em nenhuma página da grade.")
            break
        paginas_vistas.add(assinatura)

        ainda_pendentes = []
        for item in pendentes:
            registro = _buscar_item_na_grade_ob(grade, item)
            if registro is None:
                ainda_pendentes.append(item)
                continue
            _marcar_checkbox_ob(popup, registro["indice"])
            confirmados.append(item)
        pendentes = ainda_pendentes

        if len(confirmados) >= TAMANHO_LOTE_OB:
            cursor -= len(pendentes)  # devolve o que sobrou (não tentado) para o próximo lote
            break

        pendentes, cursor = _abastecer_lote_ob(
            dados, cursor, linha_inicial, pendentes, TAMANHO_LOTE_OB - len(confirmados)
        )

        if not pendentes:
            break  # nada mais a procurar (planilha acabou e não sobrou pendente)

        if not _avancar_pagina_ob(popup):
            for item in pendentes:
                _anotar_falha_ob(worksheet, item, "PP não localizado em nenhuma página da grade.")
            break

        if len(paginas_vistas) >= MAX_PAGINAS_LOTE_OB:
            log_aviso(f"Limite de {MAX_PAGINAS_LOTE_OB} páginas atingido neste lote.")
            for item in pendentes:
                _anotar_falha_ob(worksheet, item, "Limite de páginas de busca atingido.")
            break

    return confirmados, cursor


def _preencher_cabecalho_ob(page: "Page", config: dict) -> None:
    """
    Preenche o cabeçalho da tela "Manter Ordem Bancária" - fluxo
    Descentralizada (Tipo de OB "2"), os mesmos valores do OB_amigo.py
    original: Gestão, Banco/Agência/Conta de origem, Tipo de OB, Tipo de
    Pagamento e a Observação com o mês de referência (agora vindo de
    verdade de `config["mes_referencia"]`, o mesmo campo já usado pelas
    demais automações e configurado no menu "Configurar parâmetros").
    """
    mes_referencia = config.get("mes_referencia", "")
    processo = config.get("processo", "")

    page.locator("#txtGestao_SIGEFPesquisa").fill("0001")
    page.locator("#txtBancoOrigem").fill("001")
    page.locator("#txtAgenciaOrigem").fill("2757X")
    page.locator("#txtContaOrigem").fill(config.get("conta_origem") or "100005")
    page.locator("#cboTipoOB").select_option(value="2")        # Descentralizada
    page.locator("#cboTipoPagamento").select_option(value="2")
    page.locator("#txtDeObservacao").fill(
        f"Ressarcimento de amigos voluntario Referente ao {mes_referencia} Processo: {processo}"
    )


def _garantir_cabecalho_ob(page: "Page", config: dict) -> None:
    """
    Preenche o cabeçalho da OB apenas 1 ÚNICA VEZ, quando a tela é
    aberta: os campos permanecem preenchidos entre um lote e outro porque
    `_limpar_para_proximo_lote_ob` só mexe na grade de itens incluídos
    (Selecionar Todos + Remover), nunca no cabeçalho.

    Chamada antes de CADA lote, mas só preenche de fato quando a Gestão
    está vazia - na 1ª chamada (sempre) e, se algum imprevisto do SIGEF
    limpar a tela no meio da execução (ex: sessão expirou e a página
    recarregou sozinha), nas chamadas seguintes também: essa é a "regra
    de continuação" pedida por você - o cabeçalho só é refeito se, na
    prática, precisar ser refeito.
    """
    campo_gestao = page.locator("#txtGestao_SIGEFPesquisa")
    try:
        if campo_gestao.count() and campo_gestao.input_value().strip():
            return
    except Exception:
        pass
    log_info("Preenchendo o cabeçalho da OB (Gestão, Banco, Agência, Conta, Tipo de OB/Pagamento)...")
    _preencher_cabecalho_ob(page, config)


def _abrir_popup_pesquisa_ob(page: "Page", context: "BrowserContext") -> "Page":
    """Clica em 'Adicionar' e preenche a pesquisa do popup (Unidade
    Gestora, Gestão, Id de Uso e Fonte) - mesmos 4 campos para TODOS os
    lotes, refeitos a cada popup novo (o SIGEF não guarda isso de um
    popup para o outro)."""
    with context.expect_page() as nova_pagina_info:
        page.locator("#btnAdicionar").click()

    popup = nova_pagina_info.value
    aguardar_pagina_estavel(popup)

    popup.locator("#txtUnidadeGestora").fill("160001")
    popup.locator("#txtGestao_SIGEFPesquisa").fill("0001")
    popup.locator("#txtIdUso").fill("1")
    popup.locator("#txtFonte_SIGEFPesquisa").fill("500001001")
    popup.locator("#btnPesquisar").click()
    aguardar_pagina_estavel(popup)
    return popup


def _confirmar_lote_no_popup_ob(popup: "Page") -> None:
    botao_confirmar = popup.locator("#btnConfirmar")
    botao_confirmar.wait_for(state="visible", timeout=TIMEOUT_PADRAO_SIGEF)
    botao_confirmar.click()
    popup.wait_for_event("close", timeout=TIMEOUT_PADRAO_SIGEF)


def _confirmar_ob_e_capturar_numero(page: "Page") -> Optional[str]:
    """
    Clica em "Incluir" na tela principal e devolve o número da OB gerada
    - ou None se o SIGEF recusou o lote (mensagem de erro) ou o número
    não pôde ser extraído; o motivo, em qualquer um dos dois casos, já
    vai para o log (mesmo padrão da automação PP)."""
    page.bring_to_front()
    aguardar_pagina_estavel(page)

    botao_incluir = page.locator("#SIGEFBotoesManutencao_BtnIncluir")
    botao_incluir.wait_for(state="visible", timeout=TIMEOUT_PADRAO_SIGEF)
    botao_incluir.click()

    page.wait_for_selector(
        "td.SIGEFMensagemSucesso, td.SIGEFMensagemErro", timeout=TIMEOUT_PADRAO_SIGEF
    )

    if page.locator("td.SIGEFMensagemErro").count() > 0:
        mensagem_erro = page.locator("td.SIGEFMensagemErro").first.inner_text().strip()
        log_erro(f"SIGEF recusou a OB deste lote: {mensagem_erro}")
        return None

    mensagem_sucesso = page.locator("td.SIGEFMensagemSucesso").first.inner_text().strip()
    busca = REGEX_DOCUMENTO_OB.search(mensagem_sucesso)
    if busca is None:
        log_erro(f"Não foi possível extrair o número da OB da mensagem do SIGEF ({mensagem_sucesso}).")
        return None
    return busca.group(0).upper()


def _limpar_para_proximo_lote_ob(page: "Page") -> None:
    """
    Remove os itens incluídos da lista da tela principal, preparando para
    o próximo lote. Usa 'Selecionar Todos' (`#Selecao_SelectAll`) em vez
    de marcar só o 1º checkbox (como no fluxo de 1 item por OB do pacote
    `sigef_automacao`/`ordem_bancaria.py`), porque aqui um lote inclui
    vários itens de uma vez. NUNCA mexe no cabeçalho (Gestão, Banco,
    Tipo de OB...) - só na grade de itens incluídos.
    """
    try:
        page.locator("#txtNumeroOB").fill("")
        page.locator("#Selecao_SelectAll").check()
        page.locator("#btnRemover").click()
    except Exception as erro:
        log_aviso(f"Não foi possível limpar a tela para o próximo lote: {erro}")


def gerar_ob(dados, config=None, worksheet=None):
    """
    Automação: Gerar OB (lote de 30 em 30) - tela "Manter Ordem Bancária",
    fluxo Descentralizada (Tipo de OB "2").

    Em vez de abrir 1 popup de pesquisa por linha da planilha (fluxo de
    Regularização do pacote `sigef_automacao`/`ordem_bancaria.py`, 1 PP =
    1 OB), esta automação:
        1. Conecta 1 única vez à tela de Ordem Bancária e garante o
           cabeçalho preenchido (Gestão, Banco, Agência, Conta, Tipo de
           OB, Tipo de Pagamento, Observação com o mês de referência) -
           ver `_garantir_cabecalho_ob`.
        2. Para cada lote de até `TAMANHO_LOTE_OB` linhas da planilha:
           abre 1 popup de pesquisa e procura na grade `#dtgPrepPgto`
           (paginando com `_avancar_pagina_ob` quando necessário) os
           itens cujo PP (coluna K), CPF do favorecido (coluna B) e
           Valor (coluna H) batem com a planilha, marcando o checkbox de
           cada um (`_montar_lote_ob`).
        3. Item não encontrado em NENHUMA página é anotado na coluna L
           com o motivo, e o lote é REPOSTO com a próxima linha ainda
           não tentada da planilha, para fechar em `TAMANHO_LOTE_OB`
           itens confirmados mesmo assim (ver `_abastecer_lote_ob`).
        4. Confirma o lote (Confirmar no popup + Incluir na tela
           principal), captura o número da OB gerada e grava na coluna L
           de TODAS as linhas confirmadas daquele lote.
        5. Limpa a lista de itens incluídos (sem mexer no cabeçalho) e
           repete para o próximo lote, até acabar a planilha.

    LIMITAÇÃO CONHECIDA: a grade só tem botão de avançar página
    (`#pagFormulario_BtnProximo`) - sem "anterior"/"primeira página" no
    HTML fornecido. Por isso a reposição só encontra o item de troca se
    o PP dele estiver numa página AINDA NÃO visitada nesta rodada; se
    estiver numa página já passada, também é anotado como não
    encontrado (no pior caso, um lote fecha com menos itens do que
    `TAMANHO_LOTE_OB`).

    LOOP PRINCIPAL: o `while cursor < len(dados)` mais abaixo percorre a
    planilha INTEIRA, lote de 30 em 30, gerando 1 OB por lote, até não
    sobrar mais linha - nunca infinito, porque `_montar_lote_ob` sempre
    avança `cursor` (confirmando itens e/ou consumindo linhas via
    reposição), mesmo no pior caso em que nada é encontrado em lugar
    nenhum.
    """
    if sync_playwright is None:
        log_erro("A biblioteca 'playwright' não está instalada.")
        log_info("Instale com: pip install playwright && playwright install")
        return

    if not dados:
        log_aviso("Nenhuma linha para processar na automação Gerar OB.")
        return

    config = config or {}
    linha_inicial = config.get("linha_inicial", 2)

    with sync_playwright() as p:
        try:
            context, page = conectar_e_obter_pagina_sigef(p, URL_OB_SIGEF, MARCADOR_URL_OB)
        except Exception as erro:
            log_erro(f"Erro ao conectar à tela de Ordem Bancária do SIGEF: {erro}")
            return

        cursor = 0
        total_obs = 0
        total_itens_confirmados = 0

        while cursor < len(dados):
            # "Regra de continuação": só preenche de novo se necessário
            # (ver docstring de `_garantir_cabecalho_ob`).
            _garantir_cabecalho_ob(page, config)

            try:
                popup = _abrir_popup_pesquisa_ob(page, context)
            except Exception as erro:
                log_erro(f"Não foi possível abrir a pesquisa de lançamentos: {erro}")
                break

            confirmados, cursor = _montar_lote_ob(popup, dados, cursor, linha_inicial, worksheet)

            if not confirmados:
                log_aviso("Nenhum item confirmado neste lote; nada para submeter.")
                fechar_paginas([popup])
                page.bring_to_front()
                continue

            try:
                _confirmar_lote_no_popup_ob(popup)
            except Exception as erro:
                log_erro(f"Falha ao confirmar o lote no popup de pesquisa: {erro}")
                for item in confirmados:
                    _anotar_falha_ob(worksheet, item, f"Falha ao confirmar o lote no popup: {erro}")
                page.bring_to_front()
                continue

            numero_ob = _confirmar_ob_e_capturar_numero(page)
            if numero_ob is None:
                for item in confirmados:
                    _anotar_falha_ob(worksheet, item, "SIGEF recusou ou não confirmou a OB deste lote.")
                continue

            for item in confirmados:
                salvar_valor_gerado(worksheet, item["numero_linha"], COL_OB_GERADA, numero_ob, rotulo="OB")

            total_obs += 1
            total_itens_confirmados += len(confirmados)
            log_sucesso(f"OB '{numero_ob}' gerada com {len(confirmados)} item(ns) do lote.")

            _limpar_para_proximo_lote_ob(page)

        log_sucesso(
            f"Automação 'Gerar OB' concluída: {total_obs} OB(s) gerada(s), "
            f"{total_itens_confirmados} item(ns) confirmados de {len(dados)} linha(s) da planilha."
        )


def raspar_ob(dados, config=None, worksheet=None):
    """Automação: Raspar OB (a implementar)."""
    log_info("Executando: Raspar OB (não implementado ainda).")


def confirmar_ob(dados, config=None, worksheet=None):
    """Automação: Confirmar OB (a implementar)."""
    log_info("Executando: Confirmar OB (não implementado ainda).")


# ==============================================================================
# 7. EXECUTOR DINÂMICO
# ==============================================================================
# Dicionário que mapeia o número escolhido no submenu para a função
# correspondente. Para adicionar uma nova automação no futuro, basta:
#   1. Criar a nova função "minha_automacao(dados, config=None, worksheet=None)"
#   2. Adicionar uma entrada nova neste dicionário
#   3. A opção já aparece automaticamente em 'menu_programas()'
#
# OBS: a numeração é contígua de 1 a 10 - a "Raspar contas" entrou como 7 e
# empurrou "Gerar OB" e "Raspar OB" para 8 e 9, ocupando o slot que estava
# reservado; "Confirmar OB" seguiu em 10.
# ==============================================================================

PROGRAMAS = {
    1: ("CE", ce),
    2: ("Raspar CE", raspar_ce),
    3: ("NL", nl),
    4: ("Raspar NL", raspar_nl),
    5: ("PP", pp),
    6: ("Raspar PP", raspar_pp),
    7: ("Raspar contas", raspar_conta),
    8: ("Gerar OB", gerar_ob),
    9: ("Raspar OB", raspar_ob),
    10: ("Confirmar OB", confirmar_ob),
}

# ==============================================================================
# 8. MENUS (principal e de programas)
# ==============================================================================

def print_menu():
    """Exibe o menu principal do sistema."""
    print("\n🚀 SISTEMA DE AUTOMAÇÕES SIGEF 🚀")
    print("=" * 50)
    print("1 - Configurar parâmetros")
    print("2 - Executar automação")
    print("3 - Alterar planilha")
    print("4 - Alterar linha inicial")
    print("5 - Exibir configurações atuais")
    print("6 - Sair")
    print("=" * 50)


def menu_programas() -> int:
    """Exibe o submenu com as automações disponíveis e retorna a opção escolhida."""
    print("\n🧩 MENU DE PROGRAMAS")
    print("=" * 50)
    for numero, (nome, _funcao) in PROGRAMAS.items():
        print(f"{numero:>2} - {nome}")
    print(" 0 - Voltar")
    print("=" * 50)

    escolha = input("Escolha uma automação: ").strip()
    if not escolha.isdigit():
        log_aviso("Opção inválida.")
        return 0

    return int(escolha)


def executar_automacao(config: dict):
    """
    Fluxo completo de execução de uma automação:
        1. Conecta ao arquivo Excel via COM (abre/reaproveita, de forma
           visível, para acompanhamento em tempo real)
        2. Lê os dados a partir da linha inicial configurada
        3. Exibe o submenu de programas
        4. Executa a função correspondente via dicionário PROGRAMAS
    """
    if not config.get("caminho_planilha"):
        log_erro("Nenhum arquivo Excel configurado. Use a opção 'Alterar planilha' primeiro.")
        return

    log_info("Conectando ao arquivo Excel...")
    worksheet = conectar_planilha(config)
    if worksheet is None:
        log_erro("Não foi possível continuar sem conexão com a planilha.")
        return

    linha_inicial = config.get("linha_inicial", 2)
    dados = ler_dados(worksheet, linha_inicial)

    if not dados:
        log_aviso("Nenhum dado encontrado para processar.")
        return

    opcao = menu_programas()
    if opcao == 0:
        log_info("Retornando ao menu principal.")
        return

    if opcao not in PROGRAMAS:
        log_erro("Opção de automação inválida.")
        return

    nome_programa, funcao = PROGRAMAS[opcao]
    log_info(f"Iniciando automação: {nome_programa}...")

    try:
        funcao(dados, config, worksheet)
        log_sucesso(f"Automação '{nome_programa}' finalizada.")
    except Exception:
        log_erro(f"Erro inesperado durante a automação '{nome_programa}':")
        traceback.print_exc()


def menu_principal():
    """Loop principal do sistema, controla a navegação entre as opções."""
    config = carregar_configuracoes()

    while True:
        print_menu()
        opcao = input("Escolha uma opção: ").strip()

        try:
            if opcao == "1":
                config = configurar_parametros(config)

            elif opcao == "2":
                executar_automacao(config)

            elif opcao == "3":
                config = alterar_planilha(config)

            elif opcao == "4":
                config = alterar_linha_inicial(config)

            elif opcao == "5":
                exibir_configuracoes(config)

            elif opcao == "6":
                log_info("Encerrando o sistema. Até logo! 👋")
                sys.exit(0)

            else:
                log_aviso("Opção inválida. Tente novamente.")

        except KeyboardInterrupt:
            print()
            log_info("Execução interrompida pelo usuário. Encerrando...")
            sys.exit(0)
        except Exception:
            log_erro("Ocorreu um erro inesperado:")
            traceback.print_exc()

# ==============================================================================
# 9. PONTO DE ENTRADA
# ==============================================================================

def main():
    """Ponto de entrada da aplicação."""
    try:
        menu_principal()
    except Exception:
        log_erro("Erro fatal na aplicação:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()