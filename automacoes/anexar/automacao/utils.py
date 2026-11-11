"""
Funções e constantes utilitárias compartilhadas entre as etapas do fluxo
SEI/SIGEF (SEI(1) -> CE -> NL -> PP -> OB -> SEI(2)).
"""
import json
import os
import subprocess
import time
import traceback
from datetime import datetime

import pymupdf
from playwright.sync_api import Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

from automacoes.anexar import caminhos
from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.valores import normalizar, padronizar_mes, padronizar_valor  # noqa: F401 (usadas pelas etapas)
from automacoes.anexar.sistema import ambiente

# ===== URLs dos sistemas =====

# ⚠️ Todas as URLs do SIGEF abaixo apontam pro ambiente de PRODUÇÃO
# (sigef.sefin.ro.gov.br, sem o "hom" de homologação) -- ou seja, essa
# automação mexe no sistema REAL (CE/NL/PP/OB gerados aqui valem de
# verdade). Pra voltar a testar sem afetar dados reais, troque o
# domínio de volta pra "sigefhom.sefin.ro.gov.br" nas constantes abaixo.
URL_SIGEF = "http://sigef.sefin.ro.gov.br/SIGEF2026/FIN/FINManterDespesaCertificada.aspx?CdTransacao=121"

URL_SIGEF_NL = "http://sigef.sefin.ro.gov.br/SIGEF2026/FIN/FINLiquidarDespesaCertificada.aspx?CdTransacao=160"

URL_SIGEF_PP = "http://sigef.sefin.ro.gov.br/SIGEF2026/FIN/FINPreparacaoPagamentoDespesaEmpenhada.aspx?CdTransacao=250"

URL_SIGEF_OB = "http://sigef.sefin.ro.gov.br/SIGEF2026/FIN/FINManterOrdemBancaria.aspx?CdTransacao=214"

URL_SIGEF_LISTAR_PP = "http://sigef.sefin.ro.gov.br/SIGEF2026/FIN/FINListarPreparacaoPagamento.aspx?CdTransacao=177"

# ⚠️ AINDA NÃO CONFIRMADA -- diferente das URLs acima (que já foram
# testadas ao vivo), essa aqui é um placeholder. Preencher com a URL real
# da tela "Listar Ordem Bancária" do SIGEF (mesmo jeito que
# URL_SIGEF_LISTAR_PP foi preenchida) assim que for testar
# etapa_baixar_ob.py. Enquanto estiver vazia, executar_baixar_ob() recusa
# rodar em vez de tentar navegar pra uma URL errada.
URL_SIGEF_LISTAR_OB = ""

# URL genérica (sem hash de sessão nem unidade): o SEI redireciona para o login se precisar.
URL_SEI = "https://sei.sistemas.ro.gov.br/sei/controlador.php?acao=procedimento_controlar"

# Onde ficam as pastas dos processos (os JPGs baixados): "Downloads\Anexar Documentos" do
# usuário que está usando o computador. Para outro lugar, defina ANEXAR_PASTA_PROCESSOS.
PASTA_BASE = os.environ.get("ANEXAR_PASTA_PROCESSOS") or os.path.join(
    os.path.expanduser("~"), "Downloads", "Anexar Documentos")

# Arquivo onde ficam guardados os últimos valores usados (processo, dados
# do SEI, CE, etc.) -- a tabela dos dados já vem preenchida com eles.
# Fica na pasta dados/ (ver anexar/caminhos.py).
CAMINHO_SESSAO = caminhos.ARQUIVO_SESSAO

# Os detalhes técnicos dos erros (a "tela de erro" do Python) vão para
# este arquivo em vez de aparecer na tela -- a pessoa que usa o programa
# só precisa mostrá-lo a quem cuida do sistema.
CAMINHO_REGISTRO_ERROS = caminhos.ARQUIVO_REGISTRO_ERROS

# ===== Chrome dedicado à automação (mesmos parâmetros do
# abrir_chrome_automacao.bat) =====

# Procura o Chrome onde ele estiver neste computador (Program Files, Program
# Files (x86), AppData ou registro do Windows) -- ver ambiente.py. Se não
# achar, fica o caminho de sempre, e _abrir_chrome_debug avisa com clareza.
CAMINHO_CHROME_EXECUTAVEL = ambiente.achar_chrome() or r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Perfil PRÓPRIO desse Chrome, separado do Chrome do dia a dia -- fica
# com o login do SEI/SIGEF salvo entre execuções, sem nenhuma das suas
# outras abas (GitHub, planilhas, portal etc.).
# Continua sendo C:\ChromeAutomacao (onde o login já está salvo nos
# computadores que usam o programa); só muda se o computador não deixar
# gravar em C:\ -- ver ambiente.pasta_perfil_chrome.
PASTA_PERFIL_CHROME_AUTOMACAO = ambiente.pasta_perfil_chrome()


def _abrir_chrome_debug(porta: int) -> None:
    """
    Abre o Chrome dedicado à automação em segundo plano, com os mesmos
    parâmetros do abrir_chrome_automacao.bat: perfil próprio
    (PASTA_PERFIL_CHROME_AUTOMACAO, sem as abas do Chrome do dia a dia)
    e --remote-allow-origins=*, que evita o Chrome aceitar a conexão mas
    travar sem responder ao protocolo (erro "<ws connected>" seguido de
    timeout) -- proteção de origem que as versões mais recentes do
    Chrome passaram a aplicar no DevTools Protocol.

    Não espera o Chrome terminar de abrir -- quem chamou (conectar_chrome)
    é responsável por tentar conectar de novo depois de um tempo.
    """
    if not os.path.isfile(CAMINHO_CHROME_EXECUTAVEL):
        raise Exception(
            "O Google Chrome não está instalado neste computador.\n"
            "O QUE FAZER:\n"
            f"  1. Instale o Google Chrome ({ambiente.SITE_DO_CHROME}).\n"
            "  2. Feche e abra o programa de novo."
        )
    subprocess.Popen(
        [
            CAMINHO_CHROME_EXECUTAVEL,
            f"--remote-debugging-port={porta}",
            f"--user-data-dir={PASTA_PERFIL_CHROME_AUTOMACAO}",
            "--remote-allow-origins=*",
        ]
    )


def conectar_chrome(porta: int = 9222, timeout_ms: int = 60000):
    """
    Conecta ao Chrome aberto em modo de depuração (CDP) e retorna o
    objeto playwright (para poder chamar .stop() no final), o browser e o
    primeiro contexto disponível.

    Se ninguém estiver escutando na porta de depuração, abre
    automaticamente o Chrome dedicado à automação (_abrir_chrome_debug,
    mesmo efeito de dar 2 cliques em abrir_chrome_automacao.bat) e tenta
    conectar de novo antes de desistir -- não é mais preciso abrir esse
    Chrome manualmente antes de rodar a automação.

    Por padrão desiste depois de 60s em cada tentativa (em vez do padrão
    do Playwright, que pode levar minutos) pra não parecer que o script
    travou.

    Existem dois motivos bem diferentes pra essa conexão falhar, e o
    tratamento abaixo distingue os dois:
      1) O Chrome nem está aberto na porta de depuração -> a conexão
         websocket nunca chega a abrir ("<ws connecting>" sem
         "<ws connected>" no log do erro). Esse é o caso tratado
         automaticamente: abre o Chrome dedicado e tenta de novo.
      2) O Chrome está aberto e a conexão websocket abre normalmente
         ("<ws connected>" aparece no log), mas ele demora demais pra
         responder ao protocolo CDP. Nesse caso o Chrome JÁ ESTÁ em modo
         de depuração (provavelmente o do dia a dia, com muitas abas, em
         vez do dedicado) -- abrir outro Chrome não resolve, então só
         avisa o usuário em vez de tentar de novo.
    """
    playwright = sync_playwright().start()

    tentou_abrir_automaticamente = False
    while True:
        try:
            browser = playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{porta}", timeout=timeout_ms
            )
            return playwright, browser, browser.contexts[0]
        except PlaywrightTimeoutError as erro:
            playwright.stop()
            if "<ws connected>" in str(erro):
                raise Exception(
                    "O Google Chrome está aberto, mas não respondeu ao programa "
                    f"(esperei {timeout_ms // 1000} segundos).\n"
                    "O QUE FAZER:\n"
                    "  1. Feche TODAS as janelas do Google Chrome (no X, lá em cima).\n"
                    "  2. No aplicativo, clique em Começar de novo.\n"
                    "  O programa abre o Chrome certo sozinho."
                ) from erro
            raise Exception(
                "Abri o Google Chrome do programa, mas ele não respondeu "
                f"(esperei {timeout_ms // 1000} segundos).\n"
                "O QUE FAZER:\n"
                "  1. Feche TODAS as janelas do Google Chrome (no X, lá em cima).\n"
                "  2. No aplicativo, clique em Começar de novo."
            ) from erro
        except Exception as erro:
            if tentou_abrir_automaticamente:
                playwright.stop()
                raise Exception(
                    "Não consegui abrir o Google Chrome do programa.\n"
                    "O QUE FAZER:\n"
                    "  1. Feche todas as janelas do Google Chrome e clique em Começar de novo.\n"
                    "  2. Se continuar, chame quem cuida do sistema e mostre esta tela.\n"
                    f"  (Detalhe técnico: Chrome esperado em '{CAMINHO_CHROME_EXECUTAVEL}', "
                    f"porta {porta}.)"
                ) from erro

            print(
                "🌐 Abrindo o Google Chrome do programa... (é normal demorar alguns segundos)"
            )
            _abrir_chrome_debug(porta)
            tentou_abrir_automaticamente = True
            # Dá um tempo pro Chrome terminar de abrir e começar a
            # escutar a porta de depuração antes de tentar de novo.
            time.sleep(3)


def nome_pasta_valido(nome: str) -> str:
    """Remove caracteres que o Windows não aceita em nome de pasta/arquivo."""
    for caractere in '<>:"/\\|?*':
        nome = nome.replace(caractere, "-")
    return nome.strip()


def pdf_para_jpg(caminho_pdf: str, pasta_destino: str, nome_arquivo: str) -> list[str]:
    """Converte cada página do PDF em um JPG e salva na pasta destino."""
    os.makedirs(pasta_destino, exist_ok=True)
    doc = pymupdf.open(caminho_pdf)

    caminhos_gerados = []
    for i, pagina in enumerate(doc, start=1):
        pix = pagina.get_pixmap(dpi=200)
        sufixo = "" if len(doc) == 1 else f"_{i}"
        caminho_jpg = os.path.join(pasta_destino, f"{nome_arquivo}{sufixo}.jpg")
        pix.save(caminho_jpg)
        caminhos_gerados.append(caminho_jpg)

    doc.close()
    return caminhos_gerados


def obter_ou_criar_aba(context, dominio: str, url_navegacao: str, trecho_pagina: str = None) -> Page:
    """
    Procura, entre as abas já abertas no Chrome em debug, uma que pertença ao
    domínio informado. Se não encontrar, cria uma nova aba e navega até a URL.

    dominio        -> trecho da URL usado para identificar a aba (ex: "sigef.sefin.ro.gov.br")
    url_navegacao  -> URL para onde navegar caso a aba não exista ou esteja na página errada
    trecho_pagina  -> (opcional) trecho específico da URL que indica que já está na página certa
    """
    aba = None

    for pagina in context.pages:
        if dominio.lower() in pagina.url.lower():
            aba = pagina
            break

    if aba is None:
        aba = context.new_page()
        aba.goto(url_navegacao)
    else:
        aba.bring_to_front()
        if trecho_pagina and trecho_pagina not in aba.url:
            aba.goto(url_navegacao)

    aba.wait_for_load_state("networkidle")
    return aba


def carregar_sessao() -> dict:
    """
    Lê o arquivo de sessão (CAMINHO_SESSAO) com os últimos valores usados
    (processo, dados do SEI, CE, etc.). Retorna um dict vazio se o
    arquivo ainda não existir ou estiver corrompido.
    """
    if not os.path.exists(CAMINHO_SESSAO):
        return {}
    try:
        with open(CAMINHO_SESSAO, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        return {}


def salvar_sessao(**novos_valores) -> None:
    """
    Atualiza o arquivo de sessão com os valores passados, mesclando com o
    que já estava salvo (não apaga o resto). Ex: salvar_sessao(ce=ce)
    guarda só o CE, mantendo processo/dados que já estavam salvos.
    """
    sessao = carregar_sessao()
    sessao.update(novos_valores)
    caminhos.garantir_pasta(CAMINHO_SESSAO)
    with open(CAMINHO_SESSAO, "w", encoding="utf-8") as arquivo:
        json.dump(sessao, arquivo, ensure_ascii=False, indent=2)
    # A tela do aplicativo mostra, ao vivo, as NL/PP/OB que vão sendo feitas.
    interacao.avisar("sessao", sessao=interacao.resumo_da_sessao(sessao))


def perguntar_ou_reusar(
    mensagem: str, chave: str, sessao: dict, exemplo: str = None, obrigatorio: bool = True
) -> str:
    """
    Um campo só, já preenchido com o valor salvo na sessão (se houver) --
    usado pelos testes isolados de cada etapa. A automação completa usa a
    tabela dos dados do processo (dados_processo.py).
    """
    return interacao.pedir_texto(mensagem, mensagem, atual=str(sessao.get(chave) or ""), exemplo=exemplo)


# ===== Mensagens na tela =====
#
# Quem usa o programa nem sempre tem prática com o computador. Por isso
# todas as etapas usam estas funções para falar com a pessoa do mesmo
# jeito: frases curtas, sem palavras técnicas, sempre dizendo O QUE
# ESTÁ ACONTECENDO e O QUE ELA DEVE FAZER (ou não fazer).

LARGURA_TELA = 60

# As etapas que o programa faz sozinho depois da conferência, na ordem.
# inicio_de_etapa() mostra "PASSO 3 de 6" a partir desta lista.
PASSOS_AUTOMATICOS = ["CE", "NL", "PP", "OB", "BAIXAR", "SEI"]


def caixa(titulo: str, linhas=(), borda: str = "=") -> None:
    """Mostra um título em destaque, entre duas linhas, e o texto abaixo."""
    print("\n" + borda * LARGURA_TELA)
    print(f"  {titulo}")
    print(borda * LARGURA_TELA)
    for linha in linhas:
        print(f"  {linha}")
    if linhas:
        print(borda * LARGURA_TELA)


def instrucao(*linhas: str) -> None:
    """Mostra o que a pessoa deve fazer agora (cada linha com 👉)."""
    for linha in linhas:
        print(f"  👉 {linha}")


def inicio_de_etapa(chave: str, titulo: str, o_que_faz: str) -> None:
    """
    Abre cada etapa automática com: em que passo está, o que vai
    acontecer e o lembrete de não mexer no Chrome enquanto isso.
    """
    numero = PASSOS_AUTOMATICOS.index(chave) + 1 if chave in PASSOS_AUTOMATICOS else None
    passo = f"PASSO {numero} de {len(PASSOS_AUTOMATICOS)} -- " if numero else ""
    interacao.avisar("etapa", chave=chave, titulo=titulo, texto=o_que_faz)
    caixa(
        f"⏳ {passo}{titulo}",
        [
            o_que_faz,
            "",
            "✋ NÃO mexa no Chrome do programa. Só acompanhe.",
            "   O programa avisa na tela quando precisar de você.",
        ],
    )


def registrar_detalhes_tecnicos(onde: str) -> str | None:
    """
    Acrescenta o erro que está sendo tratado agora (traceback completo,
    com data e hora) em CAMINHO_REGISTRO_ERROS. Chamar dentro de um
    `except`. Devolve o caminho do arquivo, ou None se não deu pra gravar.
    """
    try:
        caminhos.garantir_pasta(CAMINHO_REGISTRO_ERROS)
        with open(CAMINHO_REGISTRO_ERROS, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M:%S} -- {onde} =====\n")
            arquivo.write(traceback.format_exc())
        return CAMINHO_REGISTRO_ERROS
    except OSError:
        return None


def explicar_erro(o_que_aconteceu: str, o_que_fazer=()) -> None:
    """
    Explica um problema em linguagem simples: o que aconteceu e, passo a
    passo, o que fazer. Usada antes de parar ou de pular algo.
    """
    interacao.avisar("erro", titulo=str(o_que_aconteceu), passos=[str(passo) for passo in o_que_fazer])
    caixa("❌ ATENÇÃO: " + o_que_aconteceu, borda="!")
    if o_que_fazer:
        print("  O QUE FAZER:")
        for numero, passo in enumerate(o_que_fazer, start=1):
            print(f"    {numero}. {passo}")
        print("!" * LARGURA_TELA)
