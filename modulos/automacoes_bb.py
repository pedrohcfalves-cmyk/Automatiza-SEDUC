"""
Sistema de Automações BB - v4.0

NOVIDADES DA v4.0 — CARGA DE LIMITE DO CARTÃO CORPORATIVO
---------------------------------------------------------
Nova automação no menu "Executar": "Carga de Limite (Cartão Corporativo)".
Planilha: B = processo, C = cartão, D = valor (inteiro), F = situação.
Para cada linha: salva o "Saldo Anterior", altera o limite do portador
(novo limite = D; diário/semanal/mensal = limite disponível arredondado
para baixo + D), confirma, e salva o "Novo Saldo". Os PDFs ficam em
saldos_carga/<processo>/ para anexar no SEI. Tem modo SIMULAÇÃO, que para
antes do Confirmar. Detalhes no bloco "AUTOMAÇÃO 2" mais abaixo.

Também: o portal passou para autoatendimento2.bb.com.br (v3.16.5); a aba do
BB agora é reconhecida em qualquer um dos hosts e a URL do portador é
montada a partir da aba aberta.

Sistema de Automações BB - v3.9

NOVIDADES DA v3.9 — A AUTOMAÇÃO NÃO INICIAVA
--------------------------------------------
Sintoma: a rodada parava logo depois de "Teste de gravação na coluna J
passou" e o Chrome nunca abria. Nada de erro, nada de traceback.

Causa: a v3.7/3.8 mantinha a conexão COM com o Excel ABERTA durante toda a
rodada. Isso deixa a thread principal dentro de um apartamento STA o tempo
todo — e logo em seguida o Playwright entra em cena e BLOQUEIA essa mesma
thread esperando o navegador. As duas coisas juntas travam.

Correção: a conversa com o Excel voltou a ser CURTA — abre, opera, solta —
como era na v3.6, que não travava. Cada leitura e cada gravação abre e
libera a conexão, então a thread está sempre limpa quando o Playwright
assume. A classe ExcelCOM é um gerenciador de contexto que garante isso.

Além disso, seguindo o modelo que você mandou:
  * reaproveita a instância do Excel e a pasta de trabalho já abertas, em
    vez de abrir de novo (GetActiveObject + varredura de Workbooks);
  * instância criada por nós nasce VISÍVEL — nunca mais um Excel invisível
    segurando o seu arquivo;
  * retentativa com espera progressiva (1s, 2s, 4s... até 10s) para os erros
    COM temporários de "Excel ocupado" ("Call was rejected by callee"),
    e repasse imediato de qualquer erro que não seja temporário;
  * escrita em lote com ScreenUpdating desligado e UM Save no fim;
  * leitura de A..J num único Range, em vez de célula por célula.

E, para nunca mais um travamento silencioso: as etapas de abertura do
navegador agora se anunciam ("Iniciando o Playwright...", "Conectando ao
Chrome...", "Procurando a aba do BB..."), então a última linha impressa diz
exatamente onde a automação está.

Sistema de Automações BB - v3.8
================================

NOVIDADES DA v3.8 — O BALÃO "AINDA ESTÁ AÍ?"
--------------------------------------------
Depois de ~15 min o portal abre um modal do Angular avisando que vai encerrar
a sessão em POUCOS SEGUNDOS. Num lote de 200 cartões isso apareceria no meio
da rodada e derrubaria tudo. Agora ele é respondido sozinho, com "manter
ativa", e o cronômetro do portal reinicia.

A defesa principal vive DENTRO da página, não no Python, e a razão é o
relógio: a contagem é de segundos, enquanto o Python passa a maior parte do
tempo esperando PDF salvar, mexendo em janela do Windows ou gravando
planilha. Uma verificação feita entre uma etapa e outra pode chegar tarde.

Injetado na página, um MutationObserver vê o modal nascer e clica no mesmo
instante; um setInterval de 1s cobre o caso de o observer perder alguma
inserção. O script é registrado com add_init_script, então se reinstala
sozinho a cada navegação e em cada iframe novo — e o portal navega o tempo
todo. O Python ainda faz uma verificação de reforço nos pontos em que a
página está respondendo, caso a injeção não tenha subido.

Um detalhe tranquilizador: enquanto o diálogo de impressão do Chrome está
aberto, a thread de JS da página fica congelada — ou seja, o cronômetro do
portal também não anda nesse período.

O guardião só clica em "manter ativa", e só dentro do modal de renovação:
nunca em "encerrar agora", nunca em outro botão da tela. No fim da rodada o
sistema informa quantas vezes a sessão foi renovada.

Sistema de Automações BB - v3.7
================================

NOVIDADES DA v3.7
-----------------
1. PLANILHA AGORA É pywin32 (Excel COM) COMO CAMINHO PRINCIPAL. A classe
   SessaoExcel se conecta ao Excel uma vez por rodada e é usada para LER e
   para GRAVAR. Ganhos concretos:

     * gravar funciona com a planilha ABERTA — que é o caso normal aqui;
     * a marca aparece na coluna J na hora, à sua frente;
     * ler pelo Excel devolve o valor que está NA TELA, então fórmulas nas
       colunas A/B/D/E deixam de ser um problema (o openpyxl só enxergava o
       último valor gravado em cache, e esse cache some quando salvamos).

   O openpyxl virou reserva, para quando não houver pywin32 ou Excel.
   Convivência: se o Excel já estava aberto, anexamos nele e NUNCA o
   fechamos; se fomos nós que abrimos, fechamos ao terminar.

2. CORRIGIDO O "O nome do arquivo não é válido". O campo do diálogo ficava
   com o nome padrão do Chrome GRUDADO no nosso caminho
   ("Banco do Brasil.pdfC:\\Users\\...\\1.pdf") porque o Ctrl+A não
   selecionava nada — o foco do teclado não estava no campo. Agora o caminho
   entra por WM_SETTEXT direto no controle, o conteúdo é RELIDO para conferir
   que ficou exatamente certo, e a confirmação é um BM_CLICK no botão
   "Salvar". Nada disso depende de foco, seleção ou temporização. O método
   por teclado continua como reserva, agora esvaziando o campo (Ctrl+A +
   Delete) antes de escrever. E se o aviso de nome inválido ainda aparecer,
   ele é fechado e o erro sobe na hora, em vez de esperar 25 segundos.

3. DETECÇÃO DO C108-010 REFORÇADA. Além do seletor da caixa de erro, o texto
   dos frames é varrido em busca dos padrões conhecidos. Se o portal mudar a
   estrutura do HTML, a recusa continua sendo reconhecida e a linha continua
   virando 'representante' na coluna J.

Sistema de Automações BB - v3.6
================================

NOVIDADES DA v3.6 — "o ok não está sendo salvo"
-----------------------------------------------
1. TESTE DE GRAVAÇÃO ANTES DO PRIMEIRO CARTÃO. O sistema agora escreve na
   coluna J pelo MESMO caminho que a automação usa depois, de forma
   NÃO-DESTRUTIVA (lê o valor atual da célula e regrava o mesmo valor),
   ANTES de baixar qualquer PDF. Passou, você vê "Teste de gravação na
   coluna J passou". Não passou, o motivo aparece na hora e dá para fechar a
   planilha e testar de novo ali mesmo — em vez de descobrir depois de duas
   horas que nenhuma marca entrou.

2. O SISTEMA NÃO CRIA MAIS A TRAVA EM NENHUMA HIPÓTESE. No modo visível ele
   abria a planilha no Excel para você acompanhar; sem pywin32 e sem
   excel.exe localizado, o último recurso ainda era abrir normalmente — o que
   travava o arquivo e impedia a própria gravação que ele promete fazer.
   Agora, nesse caso, ele simplesmente NÃO abre e explica por quê.

3. AVISO SOBRE FÓRMULAS NAS COLUNAS A/B/D/E. Descoberto testando: quando o
   openpyxl salva a planilha (o que fazemos para marcar a coluna J), ele
   mantém as fórmulas mas DESCARTA os resultados em cache. Como a leitura usa
   data_only=True (o resultado, não o texto "=..."), numa PRÓXIMA execução
   essas colunas viriam vazias até o Excel abrir e salvar o arquivo de novo.
   Se as colunas lidas forem fórmulas, o sistema avisa e explica como evitar.

NOVIDADES DA v3.5
-----------------
1. CARTÃO RECUSADO POR PERMISSÃO VIRA 'representante' NA COLUNA J. Quando o
   portal responde com a caixa de erro dele —

       Atenção!  Permitida para representante autorizado (C108-010)

   — a linha é marcada como 'representante' e a automação vai para a próxima.
   Antes esse cartão ficava 30 segundos esperando a linha "Portador" que
   nunca ia aparecer e virava um timeout genérico. Agora a espera é uma
   CORRIDA: o que vier primeiro, a tela do portador ou a mensagem de erro.
   Reconhecida a recusa, não há tentativa de recuperação — o portal
   respondeu, e insistir daria a mesma resposta.

   Outras mensagens da mesma caixa de erro também são reconhecidas: entram
   como falha, com o texto do portal no resumo e no _execucoes.csv.

2. A MARCA ENTRA NO FIM DO LAÇO DA LINHA, NÃO NO FIM DA AUTOMAÇÃO. A gravação
   da coluna J agora insiste algumas vezes (TENTATIVAS_MARCACAO, com um
   respiro entre elas) antes de considerar adiar. Um Excel ocupado por um
   instante — salvando, recalculando, com você digitando numa célula —
   deixa de virar marcação adiada.

NOVIDADES DA v3.4
-----------------
1. ENTRE UM CARTÃO E O PRÓXIMO: "VOLTAR" + "NOVA". Terminado um cartão, a
   automação clica em botao.acao.voltar e depois em botao.acao.nova — o
   caminho do próprio sistema para encerrar a transação — e o site devolve a
   tela do portador do cartão, já pronta para receber o número da PRÓXIMA
   linha da planilha. Segue assim até o fim da planilha.

   Isso também conserta um problema silencioso: a URL do portador é uma rota
   de HASH (#/template/...), e navegar para a MESMA url com hash igual não
   recarrega nada no Chromium — o goto retorna na hora e a tela continua onde
   estava. Do segundo cartão em diante dava para ficar preso na tela de
   demonstrativos do cartão anterior. Agora ir_para_tela_portador() confere se
   o campo do cartão está na tela e, se um goto não resolver, força um reload.

2. A MARCAÇÃO DA COLUNA J FICOU VISÍVEL E CONFERIDA. Antes ela era silenciosa
   quando falhava — dava para terminar um lote inteiro sem perceber que nada
   tinha sido gravado. Agora cada linha imprime o que aconteceu, o valor é
   relido do arquivo para confirmar que chegou ao disco (VERIFICAR_MARCACAO),
   e a marcação acontece ANTES do "Voltar"/"Nova", para não depender de a
   próxima tela cooperar. Um Ctrl+C no meio do lote também não perde mais as
   marcações pendentes.

Sistema de Automações BB - v3.3
================================

PLANILHA ABERTA NÃO IMPEDE MAIS A GRAVAÇÃO (v3.3)
-------------------------------------------------
Antes, com a planilha aberta no Excel a coluna J não podia ser gravada: o
Excel tranca o arquivo para escrita e o openpyxl levava PermissionError. E a
trava costumava ser criada por NÓS MESMOS — no modo visível o sistema abre a
planilha para você acompanhar. Agora isso é resolvido em duas frentes:

  1. GRAVAR PELO PRÓPRIO EXCEL. Quando o arquivo está aberto, em vez de
     disputar o arquivo com o Excel, pedimos ao Excel que escreva e salve
     (COM/pywin32). Bônus: como a escrita entra na pasta de trabalho viva,
     você vê a coluna J sendo preenchida em tempo real. Requer
     `pip install pywin32`.

  2. NÃO CRIAR A TRAVA. Sem pywin32, o sistema passa a abrir a planilha em
     SOMENTE LEITURA (excel.exe /r). Nesse modo o Excel não segura o arquivo
     para escrita, e o openpyxl continua gravando direto.

  E, como rede final, se mesmo assim sobrar alguma marcação pendente, no fim
  da execução o sistema pede: feche a planilha e tecle Enter — e grava na
  hora. Nenhuma marcação se perde por arquivo aberto.

MARCAÇÃO NA COLUNA J
--------------------
Ao terminar cada linha da planilha, o sistema escreve o resultado na coluna J
daquela linha: "ok" quando todos os demonstrativos saíram, "parcial" quando
algum falhou, e nada quando o cartão inteiro falhou (assim a linha continua
"não processada" e uma nova rodada a pega de novo). Os textos ficam nas
constantes MARCA_* logo abaixo, e PULAR_LINHAS_JA_MARCADAS = True faz o
sistema pular o que já está marcado como "ok".

A gravação recarrega o arquivo com data_only=False para NÃO destruir as
fórmulas da planilha — ver a classe MarcadorPlanilha.

2. RECUPERAÇÃO DE TIMEOUT DEPOIS DO "VOLTAR". Se a tabela de demonstrativos
   não reaparecer depois do "Voltar" (os PDFs daquela volta já estão em
   disco), a automação atualiza a página, espera carregar, refaz o caminho
   até a lista de demonstrativos do mesmo cartão e continua do próximo — em
   vez de perder o cartão inteiro. São TENTATIVAS_RECUPERACAO tentativas
   antes de desistir.


O script não sai executando ao ser aberto: ele abre um MENU no terminal,
controlado por número + Enter.

  ════════════════════════════════════════════════════════════════
    🏦  SISTEMA DE AUTOMAÇÕES BB
        demonstrativos de cartão · v3.1
  ════════════════════════════════════════════════════════════════

    🌐  Chrome (debug)   ✅  conectado na porta 9222

  ────────────────────────────────────────────────────────────────

    [1]  📊  Escolher planilha           ➜  cartoes.xlsx (Cartoes)
    [2]  🔢  Escolher linha inicial      ➜  2
    [3]  👁️  Execução visível/invisível  ➜  VISÍVEL
    [4]  ▶️  Executar automação
    [5]  🚪  Sair

O item 4 abre um SEGUNDO menu, com a lista de automações disponíveis (hoje só
"Carregamento Pelo Portador") e a opção de voltar. Novas automações entram na
lista AUTOMACOES lá embaixo — é só escrever a função e acrescentar uma linha.

VISUAL
------
As cores usam ANSI e os ícones usam emoji, mas nada disso é obrigatório: se o
console não suportar, o sistema detecta e cai sozinho para marcadores em
ASCII, sem "??" na tela. No Windows o script já liga UTF-8 e o modo ANSI do
console por conta própria. Se a fonte do seu terminal desenhar os emojis como
quadradinhos, rode com BB_SEM_EMOJI=1 (e BB_SEM_COR=1 tira as cores).

CHROME EM MODO DEPURAÇÃO — AUTOMÁTICO
-------------------------------------
Você não precisa mais abrir o Chrome na mão com a flag. Ao executar uma
automação, o sistema verifica a porta 9222 e, se estiver fora do ar, abre o
Chrome com `--remote-debugging-port=9222` sozinho.

Um detalhe do Chrome que a lógica tem de contornar: se JÁ existe um Chrome no
ar com o perfil padrão, disparar chrome.exe com a flag NÃO abre porta
nenhuma — o executável só manda "abre essa aba" para a instância existente e
encerra, ignorando a flag em silêncio. Nesse caso o sistema pergunta se você
prefere fechar o Chrome e reabrir (mantém seu perfil e seu login) ou abrir uma
janela separada com perfil dedicado (não fecha nada, mas exige login no BB na
primeira vez).

Tudo que você escolhe é gravado em `config_sistema_bb.json`, ao lado do
script, na hora da escolha E no encerramento (inclusive se você fechar com
Ctrl+C). Na próxima abertura o menu já vem preenchido.

DE ONDE VÊM OS DADOS AGORA
--------------------------
O número do cartão deixou de ser fixo no código: cada linha da planilha é um
cartão.

    coluna D  ->  número do cartão digitado na tela
    colunas A, B e E  ->  nome da pasta de destino, separados por espaço

Exemplo: linha com A="100072", B="RAIMUNDO O MESQUITA", D="4674 8100 0252
2760", E="VALDECIR R PEREIRA" gera:

    demonstrativos_pdf/
      100072 RAIMUNDO O MESQUITA VALDECIR R PEREIRA/
        1.pdf
        2.pdf
        3.pdf

A leitura começa na linha escolhida no item 2 (linha 1 é cabeçalho) e vai até
a última linha com a coluna D preenchida.

Se uma linha falhar (cartão inválido, tela que não carrega, timeout), a
execução NÃO para: o erro é registrado e a automação segue para a próxima.
No fim aparece um resumo com o que deu certo e o que falhou.

VISÍVEL x INVISÍVEL
-------------------
Os dois modos usam o MESMO Chrome já aberto na porta 9222 (é onde sua sessão
do BB está logada).

  VISÍVEL   - fluxo completo de impressão: clica no ícone, opera a
              visualização de impressão do Chrome e salva pelo explorador de
              arquivos do Windows. Traz a janela pro primeiro plano, então
              é melhor não mexer no computador enquanto roda.

  INVISÍVEL - não toca no foco da janela e não abre diálogo nenhum: o PDF é
              gerado direto por Page.printToPDF, com o mesmo cabeçalho e
              rodapé que o Chrome imprime. Você continua usando o micro
              normalmente enquanto a automação trabalha.

DEPENDÊNCIAS
------------
    pip install playwright openpyxl pyautogui websocket-client pyperclip

    openpyxl        - ler a planilha (.xlsx/.xlsm). .csv não precisa.
    pyautogui       - só no modo VISÍVEL (teclado no diálogo do Windows)
    websocket-client- só no modo VISÍVEL (falar com o chrome://print)
    pyperclip       - opcional: cola o caminho em vez de digitar

Chrome precisa estar aberto com:
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222
"""

import os
import re
import sys
import csv
import json
import time
import shutil
import base64
import ctypes
import socket
import subprocess
import queue
import threading
import traceback
import urllib.request
from ctypes import wintypes
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    from websocket import create_connection as _ws_connect  # pip install websocket-client
except Exception:
    _ws_connect = None

try:
    import openpyxl
except Exception:
    openpyxl = None


# ============================================================================
# CONSTANTES GERAIS
# ============================================================================

if os.environ.get("BB_PASTA_DADOS"):
    # Janela unificada (app_janela.py): usa a mesma pasta do programa BB
    # instalado, para reaproveitar a configuração e os PDFs já salvos.
    PASTA_SCRIPT = os.environ["BB_PASTA_DADOS"]
    os.makedirs(PASTA_SCRIPT, exist_ok=True)
elif getattr(sys, "frozen", False):
    # Executável (PyInstaller): __file__ aponta para a pasta interna do
    # pacote. Configuração, PDFs e logs ficam em Documentos, à vista.
    PASTA_SCRIPT = os.path.join(os.path.expanduser("~"), "Documents", "Automacoes BB")
    os.makedirs(PASTA_SCRIPT, exist_ok=True)
else:
    PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_CONFIG = os.path.join(PASTA_SCRIPT, "config_sistema_bb.json")
PASTA_RAIZ_PDFS = os.path.join(PASTA_SCRIPT, "demonstrativos_pdf")

PORTA_DEPURACAO = 9222

URL_DASHBOARD = ("https://autoatendimento2.bb.com.br/apf-apj-autoatendimento/"
                 "index.html?v=3.16.5#/template/~2Fapf-apj-dashboard")
URL_PORTADOR = ("https://autoatendimento2.bb.com.br/apf-apj-autoatendimento/"
                "index.html?v=3.16.5#/template/~2Fcartoes~2FVP33-A2.bb")

MAX_TENTATIVAS = 4

# A interface gráfica liga este sinal no botão "Parar": o lote termina a
# linha em andamento e para antes da próxima (nunca no meio de uma carga).
PEDIDO_PARADA = threading.Event()


def parada_pedida():
    if PEDIDO_PARADA.is_set():
        msg_alerta("Parada pedida: encerrando antes da próxima linha.")
        return True
    return False
LIMITE_LINHAS_PLANILHA = 5000  # trava de segurança contra planilha corrompida

# ---------------------------------------------------------------------------
# MARCAÇÃO NA PLANILHA (coluna J)
# ---------------------------------------------------------------------------
# Ao terminar cada linha, o sistema escreve o resultado na coluna J daquela
# mesma linha. Falha grava vazio de propósito: assim a linha continua "não
# processada" e uma nova rodada a pega de novo.
COLUNA_MARCACAO = 10          # 10 = coluna J
MARCA_OK = "ok"
MARCA_PARCIAL = "parcial"
MARCA_FALHA = ""              # vazio = deixa em branco para reprocessar

# O portal recusa alguns cartões com "Permitida para representante autorizado
# (C108-010)". Isso não é falha da automação nem coisa que nova tentativa
# resolva — é permissão. Essas linhas ganham marca própria na coluna J, para
# você separá-las depois, e a automação segue para a linha seguinte.
MARCA_REPRESENTANTE = "representante"
PADROES_REPRESENTANTE = ("representante autorizado", "c108-010")

# Quantas vezes insistir na gravação da coluna J ANTES de deixar para o fim.
# A marca precisa entrar no fim do laço da linha, não no fim da automação.
TENTATIVAS_MARCACAO = 3
ESPERA_ENTRE_MARCACOES = 1.0

# Se True, linhas cuja coluna J já esteja marcada como MARCA_OK são puladas —
# útil para retomar um lote grande sem refazer o que já saiu.
PULAR_LINHAS_JA_MARCADAS = False

# Depois de gravar, reabre o arquivo e confere se o valor está mesmo lá. Custa
# uma leitura por linha e evita o pior dos cenários: o sistema dizer "gravado"
# quando o Excel salvou por cima logo depois.
VERIFICAR_MARCACAO = True

# Tentativas de recuperação quando a tela some depois do "Voltar".
TENTATIVAS_RECUPERACAO = 2

# ---------------------------------------------------------------------------
# RITMO / TIMEOUTS (segundos, salvo onde indicado em ms)
# ---------------------------------------------------------------------------
TIMEOUT_BOTAO_IMPRIMIR_MS = 40000
TIMEOUT_CARREGANDO_MS = 20000
TIMEOUT_REDE_OCIOSA_MS = 6000

CONFIRMA_PRINT_ABRIU = 4.0
CHECK_TRAVA_MS = 500

BUSCA_ALVO_PREVIEW = 4.0
TIMEOUT_PREVIEW_PRONTO = 20.0

ESPERA_PRIMEIRO_ENTER = 1.2
INTERVALO_REENVIO_ENTER = 1.2
TIMEOUT_DIALOGO_SALVAR = 30.0
TIMEOUT_ARQUIVO_EM_DISCO = 25.0
TIMEOUT_DESTRAVAR_PAGINA = 12.0

SELETOR_BOTAO_IMPRIMIR = "img.toolPrint, img.botaoToolbar.toolPrint"
SELETOR_LINHAS = "tr.linhaClara, tr.linhaEscura"
SELETOR_PORTADOR = (
    "xpath=//tr[td[normalize-space(text())='Portador']]"
    "//span[contains(concat(' ', normalize-space(@class), ' '), ' linkTrs ')]"
)
SELETOR_PRIMEIRA_OPCAO_POPUP = "xpath=(//a[@onclick and contains(@onclick,'ajaxProcessUrl')])[1]"

# Caixa de erro padrão do portal (a do <img imgErro.gif> + "Atenção!").
SELETOR_MENSAGEM_ERRO = "#tdMensagemErroPadrao, td.textoErro"


# ============================================================================
# CONFIGURAÇÃO PERSISTENTE
# ----------------------------------------------------------------------------
# Guardada em JSON ao lado do script. Gravamos a cada alteração (não só na
# saída) para que um Ctrl+C ou uma queda de energia no meio de uma execução
# longa não faça você perder as escolhas.
# ============================================================================

class Configuracao:

    def __init__(self):
        self.caminho_planilha = ""
        self.aba_planilha = ""
        self.linha_inicial = 2
        self.modo_visivel = True   # padrão pedido: visível
        self.caminho_chrome = ""   # descoberto sozinho; guardado pra não repetir a busca
        self.perfil_dedicado = False  # True se o Chrome foi aberto com perfil próprio

    # -- serialização ------------------------------------------------------

    def como_dicionario(self):
        return {
            "caminho_planilha": self.caminho_planilha,
            "aba_planilha": self.aba_planilha,
            "linha_inicial": self.linha_inicial,
            "modo_visivel": self.modo_visivel,
            "caminho_chrome": self.caminho_chrome,
            "perfil_dedicado": self.perfil_dedicado,
        }

    def salvar(self, silencioso=True):
        try:
            with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as arq:
                json.dump(self.como_dicionario(), arq, indent=2, ensure_ascii=False)
            if not silencioso:
                print(f"[OK] Configurações salvas em: {ARQUIVO_CONFIG}")
            return True
        except OSError as erro:
            print(f"[AVISO] Não consegui salvar as configurações: {erro}")
            return False

    @classmethod
    def carregar(cls):
        cfg = cls()
        if not os.path.exists(ARQUIVO_CONFIG):
            return cfg
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as arq:
                dados = json.load(arq)
        except (OSError, ValueError) as erro:
            print(f"[AVISO] Config existente inválida ({erro}); começando do zero.")
            return cfg

        cfg.caminho_planilha = str(dados.get("caminho_planilha", "") or "")
        cfg.aba_planilha = str(dados.get("aba_planilha", "") or "")
        try:
            cfg.linha_inicial = max(1, int(dados.get("linha_inicial", 2)))
        except (TypeError, ValueError):
            cfg.linha_inicial = 2
        cfg.modo_visivel = bool(dados.get("modo_visivel", True))
        cfg.caminho_chrome = str(dados.get("caminho_chrome", "") or "")
        cfg.perfil_dedicado = bool(dados.get("perfil_dedicado", False))

        if cfg.caminho_chrome and not os.path.exists(cfg.caminho_chrome):
            cfg.caminho_chrome = ""  # Chrome atualizou/mudou de lugar: procura de novo

        # A planilha pode ter sido movida/renomeada desde a última execução.
        if cfg.caminho_planilha and not os.path.exists(cfg.caminho_planilha):
            print(f"[AVISO] A planilha salva não existe mais:\n        {cfg.caminho_planilha}")
            print("        Escolha outra na opção 1.")
        return cfg

    # -- apresentação ------------------------------------------------------

    def rotulo_planilha(self):
        if not self.caminho_planilha:
            return "nenhuma"
        nome = os.path.basename(self.caminho_planilha)
        if self.aba_planilha:
            return f"{nome}  (aba: {self.aba_planilha})"
        return nome

    def rotulo_modo(self):
        return "VISÍVEL" if self.modo_visivel else "INVISÍVEL"

    def pronta_para_executar(self):
        """(pode_executar, motivo)"""
        if not self.caminho_planilha:
            return False, "Nenhuma planilha escolhida (opção 1)."
        if not os.path.exists(self.caminho_planilha):
            return False, f"A planilha não existe mais: {self.caminho_planilha}"
        return True, ""


# ============================================================================
# UTILIDADES DE TERMINAL
# ============================================================================

class ErroDeUso(Exception):
    """
    Erro esperado e acionável pelo usuário (Chrome fechado, biblioteca
    faltando, planilha inexistente). O menu mostra só a mensagem, sem
    traceback — traceback fica reservado para bug de verdade.
    """


class ErroDoPortal(Exception):
    """
    O site respondeu com a caixa de erro padrão dele ("Atenção!" + texto).

    Distinguir isso de um timeout importa: quando o portal RESPONDEU dizendo
    não, insistir não adianta. A automação anota e passa para a próxima linha
    em vez de gastar tentativas de recuperação à toa.
    """

    def __init__(self, mensagem, marca=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.marca = marca   # o que escrever na coluna J; None = regra padrão


class CartaoBloqueado(ErroDoPortal):
    """
    Recusa por permissão — hoje o "Permitida para representante autorizado
    (C108-010)". Nenhuma nova tentativa resolve; é caso de anotar e seguir.
    """


# ---------------------------------------------------------------------------
# Cores e emojis
# ---------------------------------------------------------------------------
# Dois cuidados específicos do Windows:
#
#  1. O console legado (conhost) nasce sem interpretar códigos ANSI — as cores
#     apareceriam como lixo tipo "[92m". SetConsoleMode com
#     ENABLE_VIRTUAL_TERMINAL_PROCESSING liga isso. Se não der, desligamos as
#     cores em vez de sujar a tela.
#  2. O cmd.exe costuma abrir em code page 850/437, onde emoji nem existe.
#     Forçamos UTF-8 na saída e, se ainda assim o encoding não aceitar os
#     emojis, caímos automaticamente para ícones em ASCII. Ninguém fica com
#     "??" no lugar do menu.
# ---------------------------------------------------------------------------

def _preparar_console():
    """Liga UTF-8 e ANSI no console. Devolve (tem_cor, tem_emoji)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    tem_cor = True
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            modo = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(modo)):
                ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                tem_cor = bool(kernel32.SetConsoleMode(
                    handle, modo.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
            else:
                tem_cor = False
        except Exception:
            tem_cor = False

    if sys.stdout is None or not sys.stdout.isatty():
        tem_cor = False   # saída redirecionada pra arquivo: nada de códigos ANSI

    try:
        "🏦✅⚠️".encode(getattr(sys.stdout, "encoding", None) or "utf-8")
        tem_emoji = True
    except Exception:
        tem_emoji = False

    # Escapes manuais: se a fonte do seu terminal desenhar os emojis como
    # quadradinhos (acontece no console legado do Windows, onde o encoding
    # aceita mas a fonte não tem os glifos), rode com BB_SEM_EMOJI=1 e o menu
    # volta para marcadores em ASCII. BB_SEM_COR=1 desliga as cores.
    if os.environ.get("BB_SEM_EMOJI"):
        tem_emoji = False
    if os.environ.get("BB_SEM_COR"):
        tem_cor = False

    return tem_cor, tem_emoji


TEM_COR, TEM_EMOJI = _preparar_console()


class C:
    """Códigos ANSI (vazios quando o console não suporta)."""
    RESET = "\033[0m" if TEM_COR else ""
    NEGRITO = "\033[1m" if TEM_COR else ""
    FRACO = "\033[2m" if TEM_COR else ""
    AMARELO = "\033[93m" if TEM_COR else ""
    VERDE = "\033[92m" if TEM_COR else ""
    VERMELHO = "\033[91m" if TEM_COR else ""
    AZUL = "\033[96m" if TEM_COR else ""
    ROXO = "\033[95m" if TEM_COR else ""


_ICONES = {
    "banco":    ("🏦", "$"),
    "planilha": ("📊", "#"),
    "linha":    ("🔢", "#"),
    "olho":     ("👁️ ", ">"),
    "fantasma": ("🌙", ">"),
    "play":     ("▶️ ", ">"),
    "sair":     ("🚪", "x"),
    "chrome":   ("🌐", "@"),
    "ok":       ("✅", "[ok]"),
    "alerta":   ("⚠️ ", "[!]"),
    "erro":     ("❌", "[x]"),
    "engrenagem": ("⚙️ ", "*"),
    "pasta":    ("📁", ">"),
    "seta":     ("➜", "->"),
    "relogio":  ("⏱️ ", "-"),
    "salvo":    ("💾", "[s]"),
    "foguete":  ("🚀", ">>"),
    "aviso":    ("💡", "*"),
    "meio":     ("🟡", "[~]"),
    "cadeado":  ("🔒", "[-]"),
}


def ico(nome):
    emoji, ascii_ = _ICONES.get(nome, ("", ""))
    return emoji if TEM_EMOJI else ascii_


LARGURA = 64


def limpar_tela():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        print("\n" * 3)


def cabecalho(titulo, icone="banco", subtitulo=""):
    """
    Cabeçalho sem borda à direita de propósito: a largura que o terminal dá a
    um emoji varia (1 ou 2 colunas, dependendo da fonte), então qualquer
    tentativa de fechar a moldura na coluna certa acabaria desalinhada em
    alguma máquina.
    """
    barra = "═" * LARGURA
    print(f"{C.AZUL}{barra}{C.RESET}")
    print(f"  {ico(icone)}  {C.NEGRITO}{titulo}{C.RESET}")
    if subtitulo:
        print(f"      {C.FRACO}{subtitulo}{C.RESET}")
    print(f"{C.AZUL}{barra}{C.RESET}")


def separador(char="─"):
    print(f"{C.FRACO}{char * LARGURA}{C.RESET}")


def item_menu(numero, icone, texto, valor=None):
    linha = f"  {C.NEGRITO}{C.AMARELO}[{numero}]{C.RESET}  {ico(icone)}  {texto}"
    if valor is not None:
        linha += f"  {C.FRACO}{ico('seta')}{C.RESET}  {C.VERDE}{valor}{C.RESET}"
    print(linha)


def msg_ok(texto):
    print(f"  {ico('ok')}  {C.VERDE}{texto}{C.RESET}")


def msg_alerta(texto):
    print(f"  {ico('alerta')} {C.AMARELO}{texto}{C.RESET}")


def msg_erro(texto):
    print(f"  {ico('erro')}  {C.VERMELHO}{texto}{C.RESET}")


def msg_dica(texto):
    print(f"  {ico('aviso')}  {C.FRACO}{texto}{C.RESET}")


def perguntar(texto):
    """input() que trata Ctrl+C/Ctrl+Z como 'voltar' em vez de explodir."""
    try:
        return input(texto).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "\x00cancelar"


def foi_cancelado(resposta):
    return resposta == "\x00cancelar"


def pausar(texto="Pressione Enter para voltar ao menu"):
    perguntar(f"\n  {C.FRACO}{texto}...{C.RESET} ")


def prompt_opcao():
    return perguntar(f"\n  {C.NEGRITO}Opção {ico('seta')}{C.RESET} ")


def _sanitizar_nome(nome):
    """Remove o que o Windows não aceita em nome de pasta/arquivo."""
    invalidos = '<>:"/\\|?*'
    limpo = "".join(c for c in str(nome) if c not in invalidos and ord(c) >= 32)
    return " ".join(limpo.split()).strip().rstrip(".")


# ============================================================================
# LEITURA DA PLANILHA
# ----------------------------------------------------------------------------
# Convenção acertada: linha 1 é cabeçalho, a leitura começa na linha escolhida
# no menu (número real da linha do Excel) e vai até a última linha com a
# coluna D preenchida.
#
#   A -> parte 1 do nome da pasta
#   B -> parte 2 do nome da pasta
#   D -> número do cartão
#   E -> parte 3 do nome da pasta
# ============================================================================

def texto_celula(valor):
    """
    Converte o valor cru da célula em texto limpo.

    Cuidado importante: o openpyxl devolve números como int/float. Um cartão
    lido como float viraria "4.674810002522760e+15" com str() direto — daí a
    normalização abaixo antes de qualquer coisa.
    """
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "SIM" if valor else "NÃO"
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return ("%f" % valor).rstrip("0").rstrip(".")
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    return str(valor).strip()


def formatar_numero_cartao(valor):
    """
    Deixa o número no formato que a máscara do campo espera:
    '4674810002522760' -> '4674 8100 0252 2760'. Se não forem 16 dígitos,
    devolve o texto como está (para não estragar formatos diferentes).
    """
    bruto = texto_celula(valor)
    digitos = "".join(c for c in bruto if c.isdigit())
    if len(digitos) == 16:
        return " ".join(digitos[i:i + 4] for i in range(0, 16, 4))
    return bruto


def nome_pasta_da_linha(col_a, col_b, col_e, reserva):
    """Pasta = {A} {B} {E}, separados por espaço, saneados."""
    partes = [texto_celula(v) for v in (col_a, col_b, col_e)]
    nome = _sanitizar_nome(" ".join(p for p in partes if p))
    return nome or reserva


class LinhaPlanilha:

    def __init__(self, numero, col_a, col_b, col_d, col_e, col_j=None):
        self.numero = numero
        self.col_a = col_a
        self.col_b = col_b
        self.col_d = col_d
        self.col_e = col_e
        self.col_j = col_j          # marcação de execuções anteriores
        self.numero_cartao = formatar_numero_cartao(col_d)
        digitos = "".join(c for c in self.numero_cartao if c.isdigit())
        self.nome_pasta = nome_pasta_da_linha(col_a, col_b, col_e,
                                              reserva=digitos or f"linha_{numero}")

    @property
    def pasta_destino(self):
        return os.path.join(PASTA_RAIZ_PDFS, self.nome_pasta)

    @property
    def ja_marcada(self):
        return texto_celula(self.col_j).strip().lower() == MARCA_OK.strip().lower()

    def resumo(self):
        marca = f"  [J={texto_celula(self.col_j)}]" if texto_celula(self.col_j) else ""
        return f"linha {self.numero}: {self.numero_cartao}  ->  {self.nome_pasta}{marca}"


def detectar_dialeto_csv(caminho):
    """
    Delimitador do CSV, de forma DETERMINÍSTICA.

    Não use csv.Sniffer aqui: ele chuta a partir de uma amostra e pode dar
    respostas diferentes para o mesmo arquivo dependendo de quanto texto leu.
    Isso já causou um estrago real — a leitura entendia ';' e a gravação
    entendia ',', e a linha marcada saía com os dois misturados
    ("...;VALDECIR,,,,,,,,,ok"), corrompendo a planilha.

    Aqui a regra é simples e igual para ler e para gravar: vence o candidato
    que mais aparece na primeira linha não vazia.
    """
    candidatos = [";", ",", "\t", "|"]
    try:
        with open(caminho, "r", encoding="utf-8-sig", newline="") as arq:
            for linha in arq:
                if linha.strip():
                    contagens = {c: linha.count(c) for c in candidatos}
                    melhor = max(contagens, key=contagens.get)
                    if contagens[melhor] > 0:
                        return melhor
                    break
    except OSError:
        pass
    return ";"


def listar_abas(caminho):
    """Nomes das abas de um .xlsx/.xlsm; lista vazia para .csv."""
    if caminho.lower().endswith(".csv"):
        return []
    if openpyxl is None:
        raise ErroDeUso("openpyxl não instalado. Rode: pip install openpyxl")
    livro = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        return list(livro.sheetnames)
    finally:
        livro.close()


def ler_linhas_planilha(caminho, aba, linha_inicial, visivel=True):
    """
    Devolve [LinhaPlanilha] da linha_inicial até a última com D preenchida.

    Caminho principal: o próprio Excel (pywin32). Os valores vêm como estão
    na tela, então fórmulas nas colunas A/B/D/E não são problema.

    Reserva: openpyxl com data_only=True, que entrega o RESULTADO das
    fórmulas — mas só o último resultado que o Excel gravou no arquivo.
    """
    if not os.path.exists(caminho):
        raise ErroDeUso(f"Planilha não encontrada: {caminho}")

    linhas = []

    bruto = ler_linhas_via_excel(caminho, aba, linha_inicial, visivel=visivel)
    if bruto is not None:
        largura = max(5, COLUNA_MARCACAO)
        for deslocamento, valores in enumerate(bruto):
            valores = list(valores) + [None] * (largura - len(valores))
            col_a, col_b, _col_c, col_d, col_e = valores[:5]
            if not texto_celula(col_d):
                break
            linhas.append(LinhaPlanilha(linha_inicial + deslocamento, col_a, col_b,
                                        col_d, col_e, valores[COLUNA_MARCACAO - 1]))
            if len(linhas) >= LIMITE_LINHAS_PLANILHA:
                break
        return linhas

    if caminho.lower().endswith(".csv"):
        delimitador = detectar_dialeto_csv(caminho)
        with open(caminho, "r", encoding="utf-8-sig", newline="") as arq:
            leitor = csv.reader(arq, delimiter=delimitador)
            for numero, campos in enumerate(leitor, start=1):
                if numero < linha_inicial:
                    continue
                def pega(i):
                    return campos[i] if i < len(campos) else ""
                if not texto_celula(pega(3)):
                    break
                linhas.append(LinhaPlanilha(numero, pega(0), pega(1), pega(3), pega(4),
                                            pega(COLUNA_MARCACAO - 1)))
                if len(linhas) >= LIMITE_LINHAS_PLANILHA:
                    break
        return linhas

    if openpyxl is None:
        raise ErroDeUso("openpyxl não instalado. Rode: pip install openpyxl")

    livro = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        planilha = livro[aba] if aba and aba in livro.sheetnames else livro[livro.sheetnames[0]]
        numero = linha_inicial
        largura = max(5, COLUNA_MARCACAO)
        for celulas in planilha.iter_rows(min_row=linha_inicial, min_col=1,
                                          max_col=largura, values_only=True):
            valores = list(celulas) + [None] * (largura - len(celulas))
            col_a, col_b, _col_c, col_d, col_e = valores[:5]
            col_j = valores[COLUNA_MARCACAO - 1]
            if not texto_celula(col_d):
                break
            linhas.append(LinhaPlanilha(numero, col_a, col_b, col_d, col_e, col_j))
            numero += 1
            if len(linhas) >= LIMITE_LINHAS_PLANILHA:
                break
    finally:
        livro.close()

    return linhas


def espiar_planilha(caminho, aba, linha_inicial, quantas=5):
    """Prévia curta usada nos menus, para conferir se as colunas batem."""
    try:
        linhas = ler_linhas_planilha(caminho, aba, linha_inicial)
    except Exception as erro:
        print(f"[ERRO] Não consegui ler a planilha: {erro}")
        return []

    if not linhas:
        print(f"[AVISO] Nenhuma linha com a coluna D preenchida a partir da linha {linha_inicial}.")
        return []

    print(f"\n  {len(linhas)} linha(s) serão processadas. Primeiras:")
    for linha in linhas[:quantas]:
        print(f"    {linha.resumo()}")
    if len(linhas) > quantas:
        print(f"    ... e mais {len(linhas) - quantas}.")
    return linhas


# ============================================================================
# MARCAÇÃO NA PLANILHA (coluna J)
# ----------------------------------------------------------------------------
# Duas armadilhas moram aqui, e é por elas que isto é uma classe em vez de
# três linhas soltas:
#
#  1. FÓRMULAS. A leitura usa data_only=True para pegar o RESULTADO das
#     fórmulas. Se salvássemos um workbook carregado assim, o openpyxl
#     gravaria esses resultados NO LUGAR das fórmulas — a planilha voltaria
#     com as fórmulas destruídas. Por isso a gravação carrega o arquivo de
#     novo com data_only=False (e keep_vba para .xlsm).
#
#  2. EXCEL SEGURANDO O ARQUIVO. No modo VISÍVEL o próprio sistema abre a
#     planilha no Excel, e o Excel trava o arquivo para escrita. Em vez de
#     estourar no meio de um lote de 200 cartões, cada marca que não puder
#     ser gravada vai para uma fila e é tentada de novo no fim da execução.
#     O _execucoes.csv continua sendo o registro que nunca falha.
#
# Desde a v3.7 o caminho PRINCIPAL é o Excel via pywin32 (classe SessaoExcel
# logo abaixo); o openpyxl virou a reserva para quando o pywin32 ou o próprio
# Excel não estiverem disponíveis.
# ============================================================================


XL_UP = -4162          # Excel.Constants.xlUp
XL_MAXIMIZADO = -4137  # Excel.Constants.xlMaximized


def _erro_temporario_do_excel(erro):
    """
    Erro COM que é só "o Excel está ocupado agora" — some sozinho na
    tentativa seguinte. Acontece muito quando você está com um menu aberto
    ou digitando dentro de uma célula.
    """
    texto = str(erro)
    return ("Call was rejected by callee" in texto
            or "RPC_E_CALL_REJECTED" in texto
            or "-2147418111" in texto      # servidor COM ocupado
            or "-2146777998" in texto)     # message filter


def executar_com_retentativa(funcao, *args, max_tentativas=6, espera_inicial=1.0, **kwargs):
    """
    Roda `funcao` retentando com espera progressiva (1s, 2s, 4s... até 10s)
    enquanto o erro for do tipo "Excel ocupado". Qualquer outro erro sobe na
    hora, sem espera — não adianta insistir no que não é temporário.
    """
    tentativa = 0
    espera = espera_inicial
    while True:
        try:
            return funcao(*args, **kwargs)
        except Exception as erro:
            if not _erro_temporario_do_excel(erro):
                raise
            tentativa += 1
            if tentativa >= max_tentativas:
                raise
            msg_alerta(f"Excel ocupado (tentativa {tentativa}/{max_tentativas}); "
                       f"aguardando {espera:.0f}s...")
            time.sleep(espera)
            espera = min(espera * 2, 10)


class ExcelCOM:
    """
    Uma conversa CURTA com o Excel: abre, opera, solta.

    Por que curta, e não uma sessão mantida aberta a rodada inteira: manter a
    conexão COM viva deixava a thread principal dentro de um apartamento STA
    o tempo todo. Quando o Playwright entrava em cena logo depois e bloqueava
    essa mesma thread esperando o navegador, a automação simplesmente parava
    — travava depois do "Teste de gravação na coluna J passou" e não abria o
    Chrome. Abrindo e soltando a cada operação, a thread volta ao estado
    normal antes de qualquer coisa do Playwright acontecer.

    Regras de convivência com o seu Excel:
      * se o aplicativo já estiver aberto, ANEXAMOS nele e nunca o fechamos;
      * se a pasta de trabalho já estiver aberta, reaproveitamos a aba;
      * só quando fomos nós que abrimos o aplicativo é que ele é encerrado.
    """

    def __init__(self, caminho, aba="", visivel=True):
        self.caminho = os.path.abspath(caminho)
        self.aba = aba
        self.visivel = visivel
        self.excel = None
        self.livro = None
        self.planilha = None
        self._excel_nosso = False
        self._livro_nosso = False
        self._com_iniciado = False

    def __enter__(self):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        self._com_iniciado = True

        try:
            self.excel = win32com.client.GetActiveObject("Excel.Application")
        except Exception:
            self.excel = win32com.client.Dispatch("Excel.Application")
            self._excel_nosso = True
            # Nunca deixamos um Excel invisível segurando o arquivo do
            # usuário: instância nossa nasce visível, como no modelo.
            try:
                self.excel.Visible = bool(self.visivel)
            except Exception:
                pass

        alvo = os.path.normcase(self.caminho)
        try:
            for indice in range(1, int(self.excel.Workbooks.Count) + 1):
                aberto = self.excel.Workbooks.Item(indice)
                try:
                    if os.path.normcase(os.path.abspath(aberto.FullName)) == alvo:
                        self.livro = aberto
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if self.livro is None:
            self.livro = self.excel.Workbooks.Open(self.caminho)
            self._livro_nosso = True

        try:
            self.planilha = (self.livro.Worksheets(self.aba) if self.aba
                             else self.livro.Worksheets(1))
        except Exception:
            self.planilha = self.livro.Worksheets(1)

        return self

    def __exit__(self, *_erro):
        try:
            if self.livro is not None and self._livro_nosso:
                self.livro.Close(SaveChanges=True)
            if self.excel is not None and self._excel_nosso:
                self.excel.Quit()
        except Exception:
            pass
        self.excel = self.livro = self.planilha = None
        if self._com_iniciado:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._com_iniciado = False
        return False

    # -- operações ---------------------------------------------------------

    def salvar(self):
        try:
            self.livro.Save()
        except Exception as erro:
            msg_alerta(f"Não consegui salvar o Excel automaticamente: {erro}")

    def somente_leitura(self):
        try:
            return bool(self.livro.ReadOnly)
        except Exception:
            return False

    def ultima_linha(self, coluna):
        try:
            linha = int(self.planilha.Cells(self.planilha.Rows.Count, coluna).End(XL_UP).Row)
            if linha == 1 and not self.planilha.Cells(1, coluna).Value:
                return 0
            return linha
        except Exception:
            return 0

    def ler_intervalo(self, linha_inicial, ultima_linha, colunas=COLUNA_MARCACAO):
        """Lê A..J de uma vez só — uma chamada COM em vez de uma por célula."""
        if ultima_linha < linha_inicial:
            return []
        faixa = self.planilha.Range(
            self.planilha.Cells(linha_inicial, 1),
            self.planilha.Cells(ultima_linha, colunas),
        )
        valores = faixa.Value
        if valores is None:
            return []
        # Intervalo de uma linha só volta como tupla simples; normalizamos.
        if not isinstance(valores[0], (tuple, list)):
            valores = (valores,)
        return [list(linha) for linha in valores]

    def escrever_celulas(self, celulas):
        """
        celulas = [(linha, coluna, valor)]. Desliga o ScreenUpdating durante a
        escrita para a tela não piscar, e salva UMA vez no fim.
        """
        aplicativo = self.planilha.Application
        try:
            aplicativo.ScreenUpdating = False
        except Exception:
            aplicativo = None
        try:
            for linha, coluna, valor in celulas:
                self.planilha.Cells(linha, coluna).Value = valor
        finally:
            if aplicativo is not None:
                try:
                    aplicativo.ScreenUpdating = True
                except Exception:
                    pass
        self.salvar()


def excel_utilizavel(caminho):
    return (os.name == "nt" and tem_pywin32()
            and not caminho.lower().endswith(".csv")
            and os.path.exists(caminho))


def ler_linhas_via_excel(caminho, aba, linha_inicial, visivel=True):
    """
    Lê a planilha pelo próprio Excel. Devolve None se não der (aí o chamador
    cai no openpyxl).

    Ler pelo Excel entrega o valor que está NA TELA — some o problema do
    cache de fórmulas, que o openpyxl só enxerga se o Excel tiver salvado o
    arquivo depois do último recálculo.
    """
    if not excel_utilizavel(caminho):
        return None
    try:
        with ExcelCOM(caminho, aba, visivel=visivel) as xl:
            ultima = max(xl.ultima_linha(4), xl.ultima_linha(1))  # D é a chave; A é reserva
            if ultima < linha_inicial:
                return []
            ultima = min(ultima, linha_inicial + LIMITE_LINHAS_PLANILHA - 1)
            return xl.ler_intervalo(linha_inicial, ultima)
    except Exception as erro:
        msg_alerta(f"Não consegui ler a planilha pelo Excel: {erro}")
        return None


def gravar_via_excel(caminho, aba, celulas, visivel=True):
    """
    Grava [(linha, coluna, valor)] pelo Excel e salva. (ok, motivo_do_erro)

    Funciona com a planilha ABERTA — que é o caso normal aqui — e a marca
    aparece na coluna J na hora, à sua frente.
    """
    if not excel_utilizavel(caminho):
        return False, "pywin32/Excel indisponível"
    try:
        def _operacao():
            with ExcelCOM(caminho, aba, visivel=visivel) as xl:
                if xl.somente_leitura():
                    raise PermissionError(
                        "a pasta de trabalho está aberta como somente leitura")
                xl.escrever_celulas(celulas)
        executar_com_retentativa(_operacao)
        return True, ""
    except Exception as erro:
        return False, str(erro)


def ler_celula_via_excel(caminho, aba, linha, coluna, visivel=True):
    if not excel_utilizavel(caminho):
        return None, "pywin32/Excel indisponível"
    try:
        with ExcelCOM(caminho, aba, visivel=visivel) as xl:
            return xl.planilha.Cells(linha, coluna).Value, ""
    except Exception as erro:
        return None, str(erro)


class MarcadorPlanilha:

    def __init__(self, caminho, aba, coluna=COLUNA_MARCACAO, excel_visivel=True):
        self.caminho = caminho
        self.aba = aba
        self.coluna = coluna
        self.excel_visivel = excel_visivel
        self.eh_csv = caminho.lower().endswith(".csv")
        self.pendentes = []   # [(numero_linha, valor)] que ninguém conseguiu gravar
        self.gravadas = 0
        self.avisou_bloqueio = False
        self.avisou_com = False
        self.avisou_sem_com = False
        self.ultimo_erro_com = ""

    # -- diagnóstico -------------------------------------------------------

    def arquivo_bloqueado(self):
        """
        Heurística dupla: o Excel cria um '~$arquivo.xlsx' ao lado e mantém o
        original aberto negando escrita, então abrir em 'r+b' falha.
        """
        pasta = os.path.dirname(self.caminho) or "."
        lock = os.path.join(pasta, "~$" + os.path.basename(self.caminho))
        if os.path.exists(lock):
            return True
        try:
            with open(self.caminho, "r+b"):
                return False
        except OSError:
            return True

    # -- gravação ----------------------------------------------------------

    def marcar(self, numero_linha, valor, tentativas=TENTATIVAS_MARCACAO,
               espera=ESPERA_ENTRE_MARCACOES):
        """
        Grava `valor` na coluna J da linha AGORA. False = ficou pendente.

        A marca tem de entrar no fim do laço daquela linha, não no fim da
        automação — então aqui insistimos algumas vezes com um respiro entre
        elas, em vez de desistir na primeira negativa. Uma janela do Excel
        ocupada por um instante (salvando, recalculando, com o usuário
        digitando numa célula) deixa de virar marcação adiada.
        """
        if valor is None or valor == "":
            return True

        item = [(numero_linha, valor)]
        for tentativa in range(1, tentativas + 1):
            if self._gravar(item):
                if VERIFICAR_MARCACAO and not self._conferir(item):
                    self.ultimo_erro_com = (
                        f"gravei a linha {numero_linha}, mas ao reler o arquivo o "
                        f"valor não estava lá (algo salvou por cima?)")
                else:
                    self.gravadas += 1
                    return True

            if tentativa < tentativas:
                print(f"  {ico('alerta')} Coluna J da linha {numero_linha}: tentativa "
                      f"{tentativa}/{tentativas} não pegou; repetindo em {espera:.0f}s...")
                time.sleep(espera)

        self.pendentes.append((numero_linha, valor))
        if not self.avisou_bloqueio:
            self.avisou_bloqueio = True
            msg_alerta("Não consegui gravar a coluna J agora (arquivo em uso e sem "
                       "acesso ao Excel).")
            msg_dica("Guardo as marcações e tento de novo no fim da execução.")
        return False

    def _conferir(self, itens):
        """
        Relê o arquivo em disco e confirma que os valores chegaram lá.

        Existe porque "não deu exceção" não é o mesmo que "está gravado":
        quando o Excel está com a planilha aberta, ele pode salvar por cima
        depois. Se a conferência não puder ser feita (arquivo travado para
        leitura, por exemplo), damos por boa — o objetivo é pegar erro real,
        não gerar alarme falso.
        """
        # Conferimos na pasta de trabalho viva — é o que você vê na tela, e
        # não depende de reler o arquivo do disco.
        if excel_utilizavel(self.caminho):
            conferidos = 0
            for numero, valor in itens:
                lido, erro = ler_celula_via_excel(self.caminho, self.aba, numero,
                                                  self.coluna, self.excel_visivel)
                if erro:
                    return True            # não deu pra conferir: sem alarme falso
                if texto_celula(lido).strip().lower() != str(valor).strip().lower():
                    return False
                conferidos += 1
            if conferidos:
                return True

        if self.eh_csv or openpyxl is None:
            return True
        try:
            livro = openpyxl.load_workbook(self.caminho, data_only=True)
            try:
                nome = self.aba if self.aba in livro.sheetnames else livro.sheetnames[0]
                planilha = livro[nome]
                for numero, valor in itens:
                    lido = texto_celula(planilha.cell(row=numero, column=self.coluna).value)
                    if lido.strip().lower() != str(valor).strip().lower():
                        return False
                return True
            finally:
                livro.close()
        except Exception:
            return True

    def _gravar(self, itens):
        """
        Ordem de tentativas (invertida na v3.7, a pedido):

          1. SESSÃO EXCEL (pywin32) — o caminho principal. Escreve na pasta de
             trabalho viva, funciona com o arquivo aberto e a marca aparece na
             coluna J na hora.
          2. Excel via COM avulso — se não houver sessão montada.
          3. openpyxl — reserva para quando não há pywin32 ou Excel.
          4. desistir por ora e deixar na fila para o fim da execução.
        """
        if self.eh_csv:
            try:
                self._gravar_csv(itens)
                return True
            except PermissionError:
                return False
            except Exception as erro:
                msg_alerta(f"Não consegui gravar no CSV: {erro}")
                return False

        # 1) Excel (pywin32) — caminho principal.
        celulas = [(linha, self.coluna, valor) for linha, valor in itens]
        ok, erro = gravar_via_excel(self.caminho, self.aba, celulas, self.excel_visivel)
        if ok:
            if not self.avisou_com:
                self.avisou_com = True
                msg_ok("Gravando a coluna J pelo Excel (pywin32).")
            return True
        if erro:
            self.ultimo_erro_com = erro

        # 2) openpyxl como reserva.
        try:
            self._gravar_xlsx(itens)
            return True
        except PermissionError:
            self.ultimo_erro_com = (self.ultimo_erro_com
                                    or "arquivo aberto e travado para escrita")
        except Exception as erro:
            msg_alerta(f"Não consegui gravar na planilha: {erro}")

        return False

    def _gravar_xlsx(self, itens):
        if openpyxl is None:
            raise ErroDeUso("openpyxl não instalado. Rode: pip install openpyxl")
        # data_only=False é OBRIGATÓRIO aqui: com True, salvar substituiria as
        # fórmulas da planilha pelos seus valores em cache.
        livro = openpyxl.load_workbook(
            self.caminho, data_only=False,
            keep_vba=self.caminho.lower().endswith(".xlsm"),
        )
        try:
            nome = self.aba if self.aba in livro.sheetnames else livro.sheetnames[0]
            planilha = livro[nome]
            for numero, valor in itens:
                planilha.cell(row=numero, column=self.coluna, value=valor)
            livro.save(self.caminho)
        finally:
            livro.close()

    def _gravar_csv(self, itens):
        # Mesma detecção usada na leitura — ver detectar_dialeto_csv().
        delimitador = detectar_dialeto_csv(self.caminho)
        with open(self.caminho, "r", encoding="utf-8-sig", newline="") as arq:
            linhas = list(csv.reader(arq, delimiter=delimitador))
        for numero, valor in itens:
            while len(linhas) < numero:
                linhas.append([])
            campos = linhas[numero - 1]
            while len(campos) < self.coluna:
                campos.append("")
            campos[self.coluna - 1] = valor
        with open(self.caminho, "w", encoding="utf-8-sig", newline="") as arq:
            csv.writer(arq, delimiter=delimitador).writerows(linhas)

    def liberar(self):
        """Última tentativa com tudo que ficou na fila. (gravadas, pendentes)"""
        if not self.pendentes:
            return 0, []
        itens = list(self.pendentes)
        if self._gravar(itens):
            self.gravadas += len(itens)
            self.pendentes = []
            return len(itens), []
        return 0, itens

    # -- teste de escrita --------------------------------------------------

    def _ler_celula_bruta(self, numero_linha):
        """Valor atual da célula da coluna J, sem conversão."""
        if excel_utilizavel(self.caminho):
            valor, erro = ler_celula_via_excel(self.caminho, self.aba, numero_linha,
                                               self.coluna, self.excel_visivel)
            if not erro:
                return valor

        if self.eh_csv:
            delimitador = detectar_dialeto_csv(self.caminho)
            with open(self.caminho, "r", encoding="utf-8-sig", newline="") as arq:
                for numero, campos in enumerate(csv.reader(arq, delimiter=delimitador),
                                                start=1):
                    if numero == numero_linha:
                        return campos[self.coluna - 1] if len(campos) >= self.coluna else None
            return None

        if openpyxl is None:
            raise ErroDeUso("openpyxl não instalado. Rode: pip install openpyxl")
        livro = openpyxl.load_workbook(self.caminho, data_only=False)
        try:
            nome = self.aba if self.aba in livro.sheetnames else livro.sheetnames[0]
            return livro[nome].cell(row=numero_linha, column=self.coluna).value
        finally:
            livro.close()

    def testar_escrita(self, numero_linha):
        """
        Descobre AGORA se a coluna J pode ser gravada. (pode, motivo)

        Por que existe: descobrir no fim de uma rodada de duas horas que
        nenhuma marca entrou é o pior desfecho possível. Este teste roda
        antes do primeiro cartão e usa exatamente o mesmo caminho de
        gravação da automação, então o que ele disser é o que vai acontecer.

        É NÃO-DESTRUTIVO: lê o valor atual da célula e regrava o MESMO valor.
        Célula vazia continua vazia, célula com "ok" continua com "ok".
        """
        try:
            atual = self._ler_celula_bruta(numero_linha)
        except Exception as erro:
            return False, f"não consegui nem ler a planilha ({erro})"

        self.ultimo_erro_com = ""
        if self._gravar([(numero_linha, atual)]):
            return True, ""

        motivo = self.ultimo_erro_com or (
            "o arquivo está aberto em outro programa e travado para escrita")
        return False, motivo


# ============================================================================
# HELPERS DE JANELA DO WINDOWS (Win32 via ctypes)
# ----------------------------------------------------------------------------
# Usados só no modo VISÍVEL. Precisamos de duas coisas que o pygetwindow não
# entrega bem: a CLASSE da janela (o explorador "Salvar como" é "#32770" e o
# Chrome é "Chrome_WidgetWin_1" — casar por título é frágil) e FORÇAR o
# foreground driblando o "foreground lock" do Windows via AttachThreadInput.
# ============================================================================

_EH_WINDOWS = os.name == "nt"

if _EH_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.BringWindowToTop.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _user32.AttachThreadInput.restype = wintypes.BOOL
    _user32.EnumChildWindows.argtypes = [wintypes.HWND, _WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumChildWindows.restype = wintypes.BOOL
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND
    _user32.SetFocus.argtypes = [wintypes.HWND]
    _user32.SetFocus.restype = wintypes.HWND
    # LPARAM/WPARAM como void* para poder passar tanto inteiros quanto
    # ponteiros de texto (WM_SETTEXT) e buffers (WM_GETTEXT).
    _user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_void_p]
    _user32.SendMessageW.restype = ctypes.c_ssize_t
else:
    _user32 = None
    _kernel32 = None

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5


def _titulo_janela(hwnd):
    if not _EH_WINDOWS:
        return ""
    n = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _classe_janela(hwnd):
    if not _EH_WINDOWS:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _listar_janelas_visiveis():
    if not _EH_WINDOWS:
        return []
    encontradas = []

    def _callback(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd):
            encontradas.append((hwnd, _titulo_janela(hwnd), _classe_janela(hwnd)))
        return True

    _user32.EnumWindows(_WNDENUMPROC(_callback), 0)
    return encontradas


def _forcar_foreground(hwnd, tentativas=3):
    if not _EH_WINDOWS or not hwnd:
        return False

    SW_RESTORE = 9
    for _ in range(tentativas):
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)

        hwnd_fg = _user32.GetForegroundWindow()
        if hwnd_fg == hwnd:
            return True

        tid_fg = _user32.GetWindowThreadProcessId(hwnd_fg, None) if hwnd_fg else 0
        tid_alvo = _user32.GetWindowThreadProcessId(hwnd, None)
        tid_atual = _kernel32.GetCurrentThreadId()

        anexadas = []
        for tid in {tid_fg, tid_alvo}:
            if tid and tid != tid_atual:
                if _user32.AttachThreadInput(tid_atual, tid, True):
                    anexadas.append(tid)

        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)

        for tid in anexadas:
            _user32.AttachThreadInput(tid_atual, tid, False)

        time.sleep(0.2)
        if _user32.GetForegroundWindow() == hwnd:
            return True

    return _user32.GetForegroundWindow() == hwnd


def achar_janela_chrome():
    if not _EH_WINDOWS:
        return None
    candidatas = [
        (hwnd, titulo)
        for hwnd, titulo, classe in _listar_janelas_visiveis()
        if classe == "Chrome_WidgetWin_1" and titulo.strip()
    ]
    for hwnd, titulo in candidatas:
        if titulo.lower().endswith("google chrome"):
            return hwnd
    return candidatas[0][0] if candidatas else None


def foreground_eh_chrome():
    if not _EH_WINDOWS:
        return False
    return _classe_janela(_user32.GetForegroundWindow()) == "Chrome_WidgetWin_1"


def achar_dialogo_salvar_como(titulos=("salvar como", "save as", "guardar como",
                                       "salvar impressão como", "salvar arquivo"),
                              aceitar_unico=True):
    if not _EH_WINDOWS:
        return None
    dialogos = [
        (hwnd, titulo)
        for hwnd, titulo, classe in _listar_janelas_visiveis()
        if classe == "#32770"
    ]
    for hwnd, titulo in dialogos:
        if any(alvo in titulo.lower() for alvo in titulos):
            return hwnd, titulo
    if aceitar_unico and len(dialogos) == 1 and dialogos[0][1].strip():
        return dialogos[0]
    return None


# ============================================================================
# CDP BRUTO — para alcançar o chrome://print
# ----------------------------------------------------------------------------
# O Playwright só expõe alvos que considera "páginas do contexto". A
# visualização de impressão é uma WebUI modal do navegador, então fica de
# fora — mesmo estando visível em Target.getTargets. Aqui abrimos um
# WebSocket direto no endpoint do BROWSER e usamos Target.attachToTarget com
# flatten:true, o que nos dá um sessionId para mandar Runtime.evaluate dentro
# do chrome://print.
# ============================================================================

class ConexaoCDP:
    """Cliente CDP mínimo: só o suficiente para attach + Runtime.evaluate."""

    def __init__(self, ws_url, timeout=15):
        if _ws_connect is None:
            raise RuntimeError("websocket-client não instalado")
        self.ws = _ws_connect(ws_url, timeout=timeout)
        self._id = 0

    def enviar(self, metodo, params=None, session_id=None, timeout=15):
        self._id += 1
        meu_id = self._id
        msg = {"id": meu_id, "method": metodo, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))

        fim = time.time() + timeout
        while time.time() < fim:
            try:
                resposta = json.loads(self.ws.recv())
            except Exception:
                continue
            if resposta.get("id") != meu_id:
                continue  # evento ou resposta de outro comando
            if "error" in resposta:
                raise RuntimeError(f"{metodo}: {resposta['error']}")
            return resposta.get("result", {})
        raise TimeoutError(f"Sem resposta do CDP para {metodo} em {timeout}s")

    def avaliar(self, funcao_js, session_id, timeout=15):
        resultado = self.enviar("Runtime.evaluate", {
            "expression": f"({funcao_js})()",
            "returnByValue": True,
            "awaitPromise": True,
        }, session_id=session_id, timeout=timeout)
        if resultado.get("exceptionDetails"):
            raise RuntimeError(f"Erro de JS no preview: {resultado['exceptionDetails']}")
        return resultado.get("result", {}).get("value")

    def fechar(self):
        try:
            self.ws.close()
        except Exception:
            pass


def _endpoint_browser(porta=PORTA_DEPURACAO, timeout=3):
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))["webSocketDebuggerUrl"]


def abrir_preview_via_cdp(porta=PORTA_DEPURACAO, timeout=BUSCA_ALVO_PREVIEW):
    """
    (conexao, session_id) já anexado ao chrome://print, ou None.
    Falha rápido de propósito: o plano B (teclado) resolve em ~1s.
    """
    if _ws_connect is None:
        print("[AVISO] 'websocket-client' não instalado; sem DOM do chrome://print. "
              "Rode: pip install websocket-client")
        return None

    conexao = None
    fim = time.time() + timeout
    try:
        conexao = ConexaoCDP(_endpoint_browser(porta))
        while time.time() < fim:
            alvos = conexao.enviar("Target.getTargets").get("targetInfos", [])
            preview = next(
                (a for a in alvos if (a.get("url") or "").startswith("chrome://print")), None
            )
            if preview:
                sessao = conexao.enviar("Target.attachToTarget", {
                    "targetId": preview["targetId"], "flatten": True,
                }).get("sessionId")
                if sessao:
                    return conexao, sessao
            time.sleep(0.25)
    except Exception as erro:
        print(f"[AVISO] Não consegui falar com o chrome://print via CDP: {erro}")

    if conexao is not None:
        conexao.fechar()
    return None


# ============================================================================
# JS PARA ATRAVESSAR O SHADOW DOM DO chrome://print
# ============================================================================

_JS_DEEP = """
  const deep = (raiz, seletor) => {
    const direto = raiz.querySelector(seletor);
    if (direto) return direto;
    for (const el of raiz.querySelectorAll('*')) {
      if (el.shadowRoot) {
        const achado = deep(el.shadowRoot, seletor);
        if (achado) return achado;
      }
    }
    return null;
  };
  const ehOpcaoPdf = (o) => {
    const v = (o.value || '');
    const t = (o.textContent || '').trim();
    return v.indexOf('Save as PDF') === 0 || /salvar como pdf|save as pdf/i.test(t);
  };
"""

JS_PREVIEW_PRONTO = "() => {" + _JS_DEEP + """
  const sel = deep(document, 'select.md-select');
  const btn = deep(document, 'cr-button.action-button');
  if (!sel) return {pronto: false, motivo: 'select de destino ainda não existe'};
  if (!btn) return {pronto: false, motivo: 'botão Salvar ainda não existe'};
  const opcoes = Array.from(sel.options).map(o => o.value);
  if (!Array.from(sel.options).some(ehOpcaoPdf))
    return {pronto: false, motivo: 'destino "Salvar como PDF" ainda não carregou', opcoes: opcoes};
  const desabilitado = btn.hasAttribute('disabled') || btn.getAttribute('aria-disabled') === 'true';
  if (desabilitado) return {pronto: false, motivo: 'botão Salvar ainda desabilitado'};
  return {pronto: true, motivo: 'ok', opcoes: opcoes, destinoAtual: sel.value};
}"""

JS_SELECIONAR_PDF = "() => {" + _JS_DEEP + """
  const sel = deep(document, 'select.md-select');
  if (!sel) return {ok: false, erro: 'select.md-select não encontrado'};
  const alvo = Array.from(sel.options).find(ehOpcaoPdf);
  if (!alvo) return {ok: false, erro: 'opção "Salvar como PDF" não encontrada',
                     opcoes: Array.from(sel.options).map(o => o.value)};
  const anterior = sel.value;
  if (sel.value !== alvo.value) {
    sel.value = alvo.value;
    // O Polymer do Chrome escuta 'change'; só atribuir .value não notifica nada.
    sel.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return {ok: true, anterior: anterior, valor: sel.value,
          texto: (alvo.textContent || '').trim(), mudou: anterior !== sel.value};
}"""

JS_CLICAR_SALVAR = "() => {" + _JS_DEEP + """
  const btn = deep(document, 'cr-button.action-button');
  if (!btn) return {ok: false, erro: 'cr-button.action-button não encontrado'};
  if (btn.hasAttribute('disabled') || btn.getAttribute('aria-disabled') === 'true')
    return {ok: false, erro: 'botão Salvar está desabilitado'};
  // Clique fora do turno atual: assim este evaluate consegue RETORNAR antes de
  // o Chrome abrir o explorador de arquivos (que é modal).
  setTimeout(() => btn.click(), 0);
  return {ok: true, texto: (btn.textContent || '').trim()};
}"""


# ============================================================================
# GUARDIÃO DA SESSÃO — o balão "Ainda está aí?"
# ----------------------------------------------------------------------------
# Depois de ~15 min o portal abre um modal do Angular avisando que vai
# encerrar a sessão em POUCOS SEGUNDOS, com os botões "encerrar agora" e
# "manter ativa". Num lote de 200 cartões isso apareceria no meio da rodada e
# derrubaria tudo.
#
# Por que a defesa principal vive DENTRO da página, e não no Python:
#
#   * a contagem é de segundos. Uma verificação feita pelo Python entre uma
#     etapa e outra pode chegar tarde — ele passa boa parte do tempo esperando
#     PDF salvar, mexendo em janela do Windows, gravando planilha;
#   * o modal pode nascer em QUALQUER momento, inclusive enquanto o Python
#     está ocupado num diálogo nativo, onde nem dá pra falar com o Playwright.
#
# Injetado na página, um MutationObserver vê o modal nascer e clica em
# "manter ativa" no mesmo instante, sem depender de ninguém. Um setInterval
# de 1s cobre o caso de o observer perder alguma inserção.
#
# Detalhe tranquilizador: enquanto o diálogo de impressão do Chrome está
# aberto, a thread de JS da página fica congelada — ou seja, o cronômetro do
# portal também não anda. Quando ela volta a rodar, o guardião volta junto.
#
# O script é registrado com add_init_script, então ele se reinstala sozinho a
# cada navegação e em cada iframe novo — e o portal navega o tempo todo.
# ============================================================================

JS_GUARDA_SESSAO = """
() => {
  if (window.__bbGuardaSessao) return 'ja-instalado';
  window.__bbGuardaSessao = true;
  window.__bbRenovacoes = 0;

  const visivel = (el) => !!(el && (el.offsetWidth || el.offsetHeight ||
                                    el.getClientRects().length));

  const acharBotao = () => {
    const direto = document.querySelector('button.modal-renovacao-sessao-botao-primario');
    if (visivel(direto)) return direto;
    // Reserva por texto, caso as classes mudem: procuramos só dentro do
    // modal de renovação, para nunca clicar em outro botão da tela.
    const modal = document.querySelector('.modalRenovacaoSessao, .modal-renovacao-sessao-container');
    if (!modal) return null;
    for (const b of modal.querySelectorAll('button')) {
      if (/manter\\s*ativa/i.test(b.textContent || '') && visivel(b)) return b;
    }
    return null;
  };

  const renovar = () => {
    try {
      const btn = acharBotao();
      if (!btn) return false;
      btn.click();
      window.__bbRenovacoes = (window.__bbRenovacoes || 0) + 1;
      window.__bbUltimaRenovacao = Date.now();
      return true;
    } catch (e) { return false; }
  };

  try {
    new MutationObserver(renovar).observe(document.documentElement,
                                          {childList: true, subtree: true});
  } catch (e) {}
  try { setInterval(renovar, 1000); } catch (e) {}
  renovar();
  return 'instalado';
}
"""

# Reserva do lado do Python, para checkpoints em que a página está respondendo.
SELETORES_MANTER_SESSAO = (
    "button.modal-renovacao-sessao-botao-primario",
    "xpath=//div[contains(@class,'modal-renovacao-sessao')]"
    "//button[contains(translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'manter ativa')]",
)

_ESTADO_SESSAO = {"ultima_checagem": 0.0, "renovacoes_python": 0}


def instalar_guarda_sessao(page):
    """
    Instala o guardião na página atual E em toda navegação futura.

    São duas chamadas de propósito: add_init_script vale para os documentos
    que vierem DEPOIS; o evaluate cobre a página que já está carregada agora.
    """
    instalado = False
    try:
        page.context.add_init_script(f"({JS_GUARDA_SESSAO})();")
        instalado = True
    except Exception as erro:
        msg_alerta(f"Não consegui registrar o guardião de sessão para as próximas "
                   f"navegações: {erro}")

    for alvo in [page] + list(page.frames):
        try:
            alvo.evaluate(JS_GUARDA_SESSAO)
            instalado = True
        except Exception:
            continue

    if instalado:
        msg_ok("Guardião de sessão ativo — o balão \"Ainda está aí?\" será "
               "respondido com \"manter ativa\" sozinho.")
    return instalado


def manter_sessao_viva(page, intervalo=3.0, forcar=False):
    """
    Reforço pelo Python: se o modal estiver na tela agora, clica.

    Serve para o caso de o script injetado não ter subido (página recém
    navegada, iframe exótico). É limitado por `intervalo` para não pesar nos
    laços de espera, e NUNCA levanta exceção — se a página estiver ocupada,
    simplesmente não faz nada e o guardião injetado assume.
    """
    agora = time.time()
    if not forcar and agora - _ESTADO_SESSAO["ultima_checagem"] < intervalo:
        return False
    _ESTADO_SESSAO["ultima_checagem"] = agora

    for alvo in [page] + list(page.frames):
        for seletor in SELETORES_MANTER_SESSAO:
            try:
                loc = alvo.locator(seletor)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000)
                    _ESTADO_SESSAO["renovacoes_python"] += 1
                    msg_ok("Balão de sessão respondido: 'manter ativa'.")
                    return True
            except PlaywrightError:
                continue
            except Exception:
                continue
    return False


def renovacoes_de_sessao(page):
    """Quantas vezes a sessão foi renovada nesta rodada (página + Python)."""
    da_pagina = 0
    try:
        da_pagina = int(page.evaluate("() => window.__bbRenovacoes || 0") or 0)
    except Exception:
        pass
    return da_pagina + _ESTADO_SESSAO["renovacoes_python"]


# ============================================================================
# HELPERS DE PÁGINA (Playwright)
# ============================================================================

def esperar_rede_ociosa(page, timeout=TIMEOUT_REDE_OCIOSA_MS):
    """
    networkidle NÃO-FATAL.

    networkidle exige 500ms sem nenhuma requisição, e esse portal (AJAX
    legado + iframes + keep-alive de sessão) pode nunca ficar assim — foi o
    que derrubou a execução na v2.7. Aqui é um bônus: se não acontecer no
    prazo, seguimos. Quem manda são as esperas por ELEMENTO.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightError:
        pass


def clicar_com_confirmacao(locator, descricao, timeout=15000, aguardar_apos=None, usar_hover=True):
    """
    Clica garantindo que o clique ocorreu: espera visibilidade, faz hover
    (itens do menu usam ng-mousemove para carregar o nível seguinte), clica
    e — se `aguardar_apos` for informado — espera o próximo elemento como
    prova de que a ação disparou. Fallback de clique via JS.
    """
    locator.wait_for(state="visible", timeout=timeout)
    locator.scroll_into_view_if_needed(timeout=timeout)

    if usar_hover:
        locator.hover(timeout=timeout)

    try:
        locator.click(timeout=timeout)
    except PlaywrightError:
        print(f"[AVISO] Clique padrão falhou em '{descricao}', tentando via JavaScript...")
        locator.evaluate("el => el.click()")

    print(f"[OK] Clique realizado em: {descricao}")

    if aguardar_apos is not None:
        aguardar_apos.wait_for(state="visible", timeout=timeout)
        print(f"[OK] Confirmado: próxima etapa após '{descricao}' apareceu na tela.")


def encontrar_em_qualquer_frame(page, seletor, descricao="", timeout=15000, intervalo=300,
                                 salvar_debug_em_falha=True):
    """
    Procura `seletor` na página principal e em todos os iframes. Necessário
    porque esse portal renderiza os formulários dentro de <iframe>.
    """
    tempo_restante = timeout
    while tempo_restante > 0:
        for alvo in [page] + list(page.frames):
            try:
                loc = alvo.locator(seletor)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except PlaywrightError:
                continue
        manter_sessao_viva(page)
        page.wait_for_timeout(intervalo)
        tempo_restante -= intervalo

    frames_urls = [f.url for f in page.frames]

    if salvar_debug_em_falha:
        pasta_debug = os.path.join(PASTA_SCRIPT, "debug_html")
        os.makedirs(pasta_debug, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for idx, alvo in enumerate([page] + list(page.frames)):
            try:
                html = alvo.content()
            except Exception:
                continue
            with open(os.path.join(pasta_debug, f"{timestamp}_frame{idx}.html"),
                      "w", encoding="utf-8") as f:
                f.write(html)
        print(f"[DEBUG] HTML de cada frame salvo em '{pasta_debug}' (prefixo {timestamp}).")

    raise TimeoutError(
        f"Elemento '{descricao or seletor}' não encontrado (nem na página principal, "
        f"nem nos frames) após {timeout}ms.\nFrames: {frames_urls}"
    )


def esperar_carregamento_sumir(page, timeout=TIMEOUT_CARREGANDO_MS, intervalo=300,
                                textos=("carregando",)):
    """Espera sumir o 'Aguarde, carregando' em qualquer frame."""
    tempo_restante = timeout
    while tempo_restante > 0:
        algum_visivel = False
        for alvo in [page] + list(page.frames):
            for texto in textos:
                try:
                    loc = alvo.locator(f"text={texto}")
                    if loc.count() > 0 and loc.first.is_visible():
                        algum_visivel = True
                        break
                except PlaywrightError:
                    continue
            if algum_visivel:
                break
        if not algum_visivel:
            return
        manter_sessao_viva(page)
        page.wait_for_timeout(intervalo)
        tempo_restante -= intervalo
    print("[AVISO] 'carregando' ainda visível após o timeout; seguindo mesmo assim.")


def pagina_esta_travada(page, timeout_ms=CHECK_TRAVA_MS):
    """
    True se o JS da página não responde — window.print() está segurando a
    thread porque a visualização de impressão está aberta.
    """
    try:
        page.wait_for_function("() => true", timeout=timeout_ms)
        return False
    except PlaywrightError:
        return True


# ============================================================================
# IMPRESSÃO E SALVAMENTO DO PDF
# ============================================================================

def clicar_botao_imprimir(page, descricao):
    """
    Dispara o onclick="window.print();" do <img class="botaoToolbar toolPrint">.

    window.print() é SÍNCRONO no Chromium: congela a thread de JS até o
    diálogo fechar. Por isso agendamos o clique com setTimeout(...,0) — o
    evaluate retorna limpo e só depois a página trava. Confirmar que ela
    travou é a prova de que o preview abriu, e o portão de segurança antes de
    qualquer tecla ser enviada.
    """
    esperar_carregamento_sumir(page)

    botao = encontrar_em_qualquer_frame(
        page, SELETOR_BOTAO_IMPRIMIR, descricao=descricao, timeout=TIMEOUT_BOTAO_IMPRIMIR_MS,
    )
    botao.evaluate("el => { setTimeout(() => el.click(), 0); }")
    print(f"[OK] Clique disparado em: {descricao} (window.print())")

    prazo = time.time() + CONFIRMA_PRINT_ABRIU
    while time.time() < prazo:
        if pagina_esta_travada(page):
            print("[OK] Visualização de impressão aberta (página travou o JS).")
            return True
        time.sleep(0.1)

    print("[AVISO] A página continua respondendo — o preview pode não ter aberto.")
    return False


def operar_preview_por_dom():
    """
    Seleciona "Salvar como PDF" no <select class="md-select"> e clica no
    <cr-button class="action-button">, atravessando o shadow DOM do
    chrome://print. True se conseguiu; False = usar o teclado.
    """
    anexo = abrir_preview_via_cdp()
    if anexo is None:
        return False

    conexao, sessao = anexo
    try:
        def esperar_pronto():
            fim = time.time() + TIMEOUT_PREVIEW_PRONTO
            ultimo = {}
            while time.time() < fim:
                try:
                    ultimo = conexao.avaliar(JS_PREVIEW_PRONTO, sessao) or {}
                except Exception as erro:
                    ultimo = {"pronto": False, "motivo": str(erro)}
                if ultimo.get("pronto"):
                    return
                time.sleep(0.3)
            raise TimeoutError(f"Preview não ficou pronto em {TIMEOUT_PREVIEW_PRONTO}s: {ultimo}")

        esperar_pronto()

        destino = conexao.avaliar(JS_SELECIONAR_PDF, sessao) or {}
        if not destino.get("ok"):
            raise RuntimeError(f"Não consegui selecionar 'Salvar como PDF': {destino}")
        print(f"[OK] Destino: '{destino.get('texto')}'"
              f"{' [alterado]' if destino.get('mudou') else ' [já estava]'}")

        # Trocar o destino re-renderiza o preview e desabilita o botão de novo.
        if destino.get("mudou"):
            esperar_pronto()

        clique = conexao.avaliar(JS_CLICAR_SALVAR, sessao) or {}
        if not clique.get("ok"):
            raise RuntimeError(f"Não consegui clicar no botão 'Salvar': {clique}")
        print(f"[OK] Clique no botão '{clique.get('texto')}' disparado.")
        return True
    except Exception as erro:
        print(f"[AVISO] Falhou ao operar o preview pelo DOM: {erro}")
        return False
    finally:
        conexao.fechar()


def confirmar_preview_por_teclado(hwnd_chrome, timeout_total=TIMEOUT_DIALOGO_SALVAR):
    """
    Plano B: reenvia Enter (botão padrão = "Salvar") até o explorador
    aparecer. Antes de CADA tecla conferimos se a janela em foco é do Chrome;
    se não der pra trazer o Chrome pro foreground, nenhuma tecla é enviada —
    proteção contra digitar em cima de outra janela (um editor, por exemplo).
    """
    fim = time.time() + timeout_total
    proximo_enter = time.time() + ESPERA_PRIMEIRO_ENTER
    enters = 0

    while time.time() < fim:
        if achar_dialogo_salvar_como():
            return True
        if time.time() >= proximo_enter:
            if not foreground_eh_chrome():
                _forcar_foreground(hwnd_chrome)
            if foreground_eh_chrome():
                pyautogui.press("enter")
                enters += 1
                print(f"[..] Enter #{enters} enviado à visualização de impressão...")
            else:
                print("[AVISO] Não consegui colocar o Chrome em primeiro plano; "
                      "NÃO enviei Enter (pra não digitar em outra janela).")
            proximo_enter = time.time() + INTERVALO_REENVIO_ENTER
        time.sleep(0.2)

    return False


def _listar_filhos(hwnd):
    """Todas as janelas-filhas (em qualquer profundidade) de hwnd."""
    filhos = []

    def _callback(filho, _lparam):
        filhos.append(filho)
        return True

    _user32.EnumChildWindows(hwnd, _WNDENUMPROC(_callback), 0)
    return filhos


def _achar_campo_nome_arquivo(hwnd_dialogo):
    """
    O <Edit> do "Nome do arquivo" dentro do diálogo.

    No diálogo do Windows esse campo é um Edit dentro de um ComboBox /
    ComboBoxEx32; usamos essa relação para não pegar a caixa de pesquisa nem
    outro campo qualquer.
    """
    edits = [h for h in _listar_filhos(hwnd_dialogo) if _classe_janela(h) == "Edit"]
    for hwnd in edits:
        if _classe_janela(_user32.GetParent(hwnd)) in ("ComboBox", "ComboBoxEx32"):
            return hwnd
    return edits[0] if edits else None


def _texto_do_controle(hwnd):
    tamanho = int(_user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, None, None))
    buf = ctypes.create_unicode_buffer(tamanho + 1)
    _user32.SendMessageW(hwnd, WM_GETTEXT, ctypes.c_void_p(tamanho + 1),
                         ctypes.cast(buf, ctypes.c_void_p))
    return buf.value


def _achar_botao_salvar(hwnd_dialogo, textos=("salvar", "save", "guardar")):
    for hwnd in _listar_filhos(hwnd_dialogo):
        if _classe_janela(hwnd) != "Button":
            continue
        rotulo = _titulo_janela(hwnd).replace("&", "").strip().lower()
        if any(rotulo.startswith(t) for t in textos):
            return hwnd
    return None


def _definir_nome_arquivo(hwnd_dialogo, caminho_completo):
    """
    Escreve o caminho DIRETO no campo, via WM_SETTEXT, e confere lendo de volta.

    Foi aqui que aparecia o erro "O nome do arquivo não é válido": o
    Ctrl+A não selecionava o texto existente (o foco do teclado não estava no
    campo), então o caminho era ANEXADO ao nome que o Chrome já tinha posto —
    virava "Banco do Brasil.pdfC:\\Users\\...\\1.pdf".

    WM_SETTEXT substitui o conteúdo inteiro do controle de uma vez. Não
    depende de foco, de seleção, de layout de teclado nem de temporização. E a
    releitura com WM_GETTEXT prova que o campo ficou exatamente com o caminho
    que queremos ANTES de confirmar qualquer coisa.
    """
    hwnd_edit = _achar_campo_nome_arquivo(hwnd_dialogo)
    if not hwnd_edit:
        return False

    _user32.SendMessageW(hwnd_edit, WM_SETTEXT, None,
                         ctypes.cast(ctypes.c_wchar_p(caminho_completo), ctypes.c_void_p))
    time.sleep(0.15)

    escrito = _texto_do_controle(hwnd_edit)
    if escrito != caminho_completo:
        print(f"  {ico('alerta')} O campo de nome ficou como {escrito!r} em vez do "
              f"caminho esperado.")
        return False
    return True


def _confirmar_dialogo(hwnd_dialogo):
    """Aciona o botão 'Salvar'. BM_CLICK não depende de foco nem de teclado."""
    botao = _achar_botao_salvar(hwnd_dialogo)
    if botao:
        _user32.SendMessageW(botao, BM_CLICK, None, None)
        return True
    # Sem o botão localizado, cai no Enter — mas só com o diálogo em foco.
    _forcar_foreground(hwnd_dialogo)
    if pyautogui is not None:
        pyautogui.press("enter")
        return True
    return False


def _achar_aviso_nome_invalido():
    """
    A caixinha "O nome do arquivo não é válido" que o Windows abre por cima
    do diálogo de salvar. Reconhecida pelo texto dos seus controles.
    """
    if not _EH_WINDOWS:
        return None
    padroes = ("não é válido", "nao e valido", "is not valid", "inválido", "invalid")
    for hwnd, _titulo, classe in _listar_janelas_visiveis():
        if classe != "#32770":
            continue
        textos = " ".join(_titulo_janela(h) for h in _listar_filhos(hwnd)).lower()
        if any(padrao in textos for padrao in padroes):
            return hwnd
    return None


def _enviar_caminho_para_dialogo(hwnd_dialogo, caminho_completo):
    """
    Preenche o campo de nome e confirma.

    Caminho principal: WM_SETTEXT + BM_CLICK (nada de teclado, nada de foco).
    Reserva: o método antigo por teclado, agora com o campo esvaziado e
    conferido antes de digitar, para nunca mais concatenar com o nome padrão.
    """
    if _definir_nome_arquivo(hwnd_dialogo, caminho_completo):
        print(f"  {ico('planilha')}  Nome do arquivo definido no diálogo.")
        _confirmar_dialogo(hwnd_dialogo)
        return

    print(f"  {ico('alerta')} Não consegui escrever direto no campo; "
          f"usando o teclado como reserva.")
    if pyautogui is None:
        raise RuntimeError("pyautogui não instalado e o campo não aceitou WM_SETTEXT.")

    _forcar_foreground(hwnd_dialogo)
    hwnd_edit = _achar_campo_nome_arquivo(hwnd_dialogo)
    if hwnd_edit:
        _user32.SetFocus(hwnd_edit)
    time.sleep(0.2)

    # Esvazia de verdade antes de escrever: Ctrl+A sozinho já falhou em campo
    # sem foco, e o resultado foi o nome padrão grudado no nosso caminho.
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)

    if pyperclip is not None:
        pyperclip.copy(caminho_completo)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.typewrite(caminho_completo, interval=0.01)
    time.sleep(0.25)
    pyautogui.press("enter")


def salvar_no_explorador(caminho_completo, timeout=TIMEOUT_DIALOGO_SALVAR):
    """
    Espera o explorador abrir, escreve o caminho completo e confirma. Só
    retorna quando o arquivo existir de fato em disco.
    """
    fim = time.time() + timeout
    hwnd_dialogo = None
    while time.time() < fim:
        achado = achar_dialogo_salvar_como()
        if achado:
            hwnd_dialogo, titulo = achado
            print(f"[OK] Explorador de arquivos aberto: '{titulo}'")
            break
        time.sleep(0.2)

    if hwnd_dialogo is None:
        raise TimeoutError(
            f"O explorador de arquivos não apareceu em {timeout}s. "
            f"Nenhuma tecla foi enviada para outra janela."
        )

    _forcar_foreground(hwnd_dialogo)
    time.sleep(0.25)
    _enviar_caminho_para_dialogo(hwnd_dialogo, caminho_completo)

    prazo = time.time() + TIMEOUT_ARQUIVO_EM_DISCO
    while time.time() < prazo:
        if os.path.exists(caminho_completo) and os.path.getsize(caminho_completo) > 1000:
            return caminho_completo

        # "O nome do arquivo não é válido": em vez de esperar 25s à toa,
        # fechamos o aviso e falhamos na hora, com o caminho no erro. O
        # salvamento direto (printToPDF) assume em seguida.
        aviso = _achar_aviso_nome_invalido()
        if aviso:
            botao_ok = _achar_botao_salvar(aviso, textos=("ok", "fechar"))
            if botao_ok:
                _user32.SendMessageW(botao_ok, BM_CLICK, None, None)
            raise RuntimeError(
                f"O Windows recusou o nome do arquivo: '{caminho_completo}'"
            )

        residual = achar_dialogo_salvar_como(
            titulos=("confirmar", "confirm", "substituir", "replace"), aceitar_unico=False,
        )
        if residual:
            _forcar_foreground(residual[0])
            time.sleep(0.2)
            pyautogui.press("enter")
        time.sleep(0.3)

    raise TimeoutError(
        f"Preenchi o caminho no explorador, mas '{caminho_completo}' não apareceu "
        f"em disco em {TIMEOUT_ARQUIVO_EM_DISCO}s."
    )


def fechar_preview_se_aberto(page):
    """Impede que a página fique travada com o preview aberto após um erro."""
    if pyautogui is not None and foreground_eh_chrome() and pagina_esta_travada(page):
        pyautogui.press("escape")
        time.sleep(0.4)


def salvar_via_impressao(page, caminho_completo, descricao_botao):
    """Fluxo completo: imprimir -> preview -> explorador de arquivos."""
    if pyautogui is None:
        raise RuntimeError("pyautogui não instalado. Rode: pip install pyautogui")
    if not _EH_WINDOWS:
        raise RuntimeError("O modo VISÍVEL com diálogo só funciona no Windows.")

    os.makedirs(os.path.dirname(caminho_completo), exist_ok=True)

    # Apagar um arquivo anterior de mesmo nome elimina o popup "substituir?"
    # e faz a existência do arquivo virar prova de sucesso.
    if os.path.exists(caminho_completo):
        try:
            os.remove(caminho_completo)
        except OSError:
            pass

    try:
        page.bring_to_front()
    except PlaywrightError:
        pass
    hwnd_chrome = achar_janela_chrome()
    if hwnd_chrome is None:
        raise RuntimeError("Não achei a janela do Google Chrome (classe 'Chrome_WidgetWin_1').")
    _forcar_foreground(hwnd_chrome)

    clicar_botao_imprimir(page, descricao_botao)

    try:
        avancou = operar_preview_por_dom()
        if not avancou:
            print("[..] Usando o plano B: Enter no botão padrão do preview.")
            if not confirmar_preview_por_teclado(hwnd_chrome):
                raise TimeoutError(
                    "A visualização de impressão não avançou para o explorador de "
                    "arquivos. Confira se o 'Destino' está em 'Salvar como PDF'."
                )
        salvar_no_explorador(caminho_completo)
    except Exception:
        fechar_preview_se_aberto(page)
        raise

    prazo = time.time() + TIMEOUT_DESTRAVAR_PAGINA
    while time.time() < prazo and pagina_esta_travada(page):
        time.sleep(0.2)

    print(f"[OK] PDF salvo em: {caminho_completo}")
    return caminho_completo


def salvar_pdf_via_cdp(page, caminho_completo):
    """
    Page.printToPDF: renderiza com a mídia de impressão (o mesmo @media print
    que produz a folha do relatório) e devolve os bytes. Não abre janela
    nenhuma nem depende de foco — é o motor do modo INVISÍVEL.
    """
    os.makedirs(os.path.dirname(caminho_completo), exist_ok=True)

    cabecalho = (
        "<div style=\"font-size:9px;font-family:Arial,sans-serif;width:100%;"
        "padding:0 10mm;display:flex;justify-content:space-between;color:#000;\">"
        "<span class=\"date\"></span><span class=\"title\"></span></div>"
    )
    rodape = (
        "<div style=\"font-size:9px;font-family:Arial,sans-serif;width:100%;"
        "padding:0 10mm;display:flex;justify-content:space-between;color:#000;\">"
        "<span class=\"url\"></span>"
        "<span><span class=\"pageNumber\"></span>/<span class=\"totalPages\"></span></span></div>"
    )

    # Garante que o relatório está pronto — no modo invisível não temos o
    # clique no ícone de imprimir servindo de sincronização.
    esperar_carregamento_sumir(page)
    encontrar_em_qualquer_frame(
        page, SELETOR_BOTAO_IMPRIMIR, descricao="tela do relatório",
        timeout=TIMEOUT_BOTAO_IMPRIMIR_MS,
    )

    cdp = page.context.new_cdp_session(page)
    resultado = cdp.send("Page.printToPDF", {
        "printBackground": True,
        "displayHeaderFooter": True,
        "headerTemplate": cabecalho,
        "footerTemplate": rodape,
        "marginTop": 0.4, "marginBottom": 0.4, "marginLeft": 0.4, "marginRight": 0.4,
        "preferCSSPageSize": False,
    })

    with open(caminho_completo, "wb") as f:
        f.write(base64.b64decode(resultado["data"]))

    tamanho = os.path.getsize(caminho_completo)
    if tamanho < 1000:
        raise RuntimeError(f"PDF em '{caminho_completo}' ficou com só {tamanho} bytes.")

    print(f"[OK] PDF salvo ({tamanho // 1024} KB): {caminho_completo}")
    return caminho_completo


def salvar_demonstrativo(page, caminho_pdf, descricao_botao, cfg):
    """
    Escolhe o motor conforme o modo.

    No modo INVISÍVEL usamos SÓ o printToPDF: cair no diálogo roubaria o foco
    da sua tela, que é justamente o que esse modo promete não fazer.
    No modo VISÍVEL o printToPDF fica como rede de segurança se o diálogo
    falhar — o arquivo sai com o mesmo nome e na mesma pasta.
    """
    if not cfg.modo_visivel:
        return salvar_pdf_via_cdp(page, caminho_pdf)

    try:
        return salvar_via_impressao(page, caminho_pdf, descricao_botao)
    except Exception as erro:
        print(f"[AVISO] Salvamento pelo diálogo falhou: {erro}")
        print("[..] Tentando gerar o PDF direto (sem diálogo)...")
        return salvar_pdf_via_cdp(page, caminho_pdf)


# ============================================================================
# CHROME EM MODO DEPURAÇÃO — garantido em todos os casos
# ----------------------------------------------------------------------------
# A automação inteira depende da porta 9222 estar escutando. Em vez de exigir
# que você abra o Chrome na mão com a flag certa, o sistema cuida disso.
#
# A pegadinha que obriga a lógica abaixo a ser mais que um Popen: se JÁ existe
# um Chrome rodando com o perfil padrão, disparar chrome.exe com
# --remote-debugging-port NÃO abre porta nenhuma. O executável apenas manda
# "abre essa aba" para a instância que já está no ar e encerra — a flag é
# ignorada silenciosamente. Por isso:
#
#   Chrome fechado          -> abrimos com a flag, no seu perfil normal.
#   Chrome aberto sem flag  -> não dá pra retrofitar; você escolhe entre
#                              reabrir o Chrome ou usar um perfil dedicado
#                              (que roda em paralelo, sem fechar nada).
# ============================================================================

PASTA_PERFIL_DEDICADO = os.path.join(PASTA_SCRIPT, "perfil_chrome_bb")

# Abas abertas quando a janela do Chrome da automação é iniciada.
URLS_ABERTURA = (
    "https://autoatendimento2.bb.com.br/apf-apj-acesso/index.html"
    "?ambiente=WEB_PESSOA_JURIDICA_CHAVEJ_GOVERNO&segmento=est#/transacao/acesso-apj/1",
    "https://sei.sistemas.ro.gov.br/sip/login.php?sigla_orgao_sistema=RO&sigla_sistema=SEI",
)

CAMINHOS_CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def porta_debug_aberta(porta=PORTA_DEPURACAO, timeout=0.4):
    """Teste barato (socket puro) para saber se alguém escuta na porta."""
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=timeout):
            return True
    except OSError:
        return False


def debug_responde(porta=PORTA_DEPURACAO, timeout=2):
    """Confirma que quem está na porta é mesmo o DevTools do Chrome."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version",
                                    timeout=timeout) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        return dados.get("Browser", "Chrome")
    except Exception:
        return None


def localizar_chrome(cfg=None):
    if cfg and cfg.caminho_chrome and os.path.exists(cfg.caminho_chrome):
        return cfg.caminho_chrome

    for caminho in CAMINHOS_CHROME:
        if caminho and os.path.exists(caminho):
            return caminho

    if os.name == "nt":
        # O instalador do Chrome registra o caminho aqui, o que cobre
        # instalações fora dos diretórios padrão.
        try:
            import winreg
            for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    chave = winreg.OpenKey(
                        raiz,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
                    valor, _ = winreg.QueryValueEx(chave, None)
                    winreg.CloseKey(chave)
                    if valor and os.path.exists(valor):
                        return valor
                except OSError:
                    continue
        except Exception:
            pass

    for nome in ("chrome", "google-chrome", "chromium", "chromium-browser"):
        achado = shutil.which(nome)
        if achado:
            return achado
    return None


def chrome_esta_rodando():
    if os.name != "nt":
        try:
            saida = subprocess.run(["pgrep", "-f", "chrome"], capture_output=True, timeout=5)
            return saida.returncode == 0
        except Exception:
            return False
    try:
        saida = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "chrome.exe" in (saida.stdout or "").lower()
    except Exception:
        return False


def encerrar_chrome():
    if os.name != "nt":
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True, timeout=10)
        time.sleep(2)
        return True
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"],
                       capture_output=True, timeout=20,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(2.5)
        return not chrome_esta_rodando()
    except Exception as erro:
        print(f"  {ico('alerta')} Não consegui encerrar o Chrome: {erro}")
        return False


def iniciar_chrome_debug(caminho_chrome, perfil_dedicado=False, abrir_url=URLS_ABERTURA,
                         espera=20):
    """Sobe o Chrome com a flag e espera a porta responder de verdade."""
    argumentos = [
        caminho_chrome,
        f"--remote-debugging-port={PORTA_DEPURACAO}",
        # Sem isso, versões recentes do Chrome recusam o handshake WebSocket
        # do CDP vindo de origem desconhecida.
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if perfil_dedicado:
        os.makedirs(PASTA_PERFIL_DEDICADO, exist_ok=True)
        argumentos.append(f"--user-data-dir={PASTA_PERFIL_DEDICADO}")
    if isinstance(abrir_url, str):
        abrir_url = [abrir_url]
    argumentos.extend(abrir_url or [])

    criacao = 0
    if os.name == "nt":
        criacao = (getattr(subprocess, "DETACHED_PROCESS", 0)
                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))

    try:
        subprocess.Popen(argumentos, creationflags=criacao,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as erro:
        raise ErroDeUso(f"Não consegui iniciar o Chrome: {erro}")

    fim = time.time() + espera
    while time.time() < fim:
        if porta_debug_aberta() and debug_responde():
            return True
        time.sleep(0.5)
    return False


def garantir_chrome_em_debug(cfg, interativo=True):
    """
    Deixa a porta 9222 no ar, aconteça o que acontecer. True se conseguiu.
    """
    versao = debug_responde() if porta_debug_aberta() else None
    if versao:
        print(f"  {ico('ok')}  Chrome em modo depuração já ativo ({versao}).")
        return True

    caminho = localizar_chrome(cfg)
    if not caminho:
        raise ErroDeUso(
            "Não encontrei o chrome.exe nesta máquina.\n"
            "       Instale o Google Chrome ou abra-o manualmente com:\n"
            f'         chrome.exe --remote-debugging-port={PORTA_DEPURACAO}'
        )
    if caminho != cfg.caminho_chrome:
        cfg.caminho_chrome = caminho
        cfg.salvar()

    # Desde o Chrome 136 a flag --remote-debugging-port é IGNORADA no perfil
    # padrão (regra de segurança do Google). Só funciona com --user-data-dir
    # próprio. Então a automação usa sempre uma janela com perfil dedicado:
    # abre ao lado do seu Chrome normal, sem fechar nada, e o login no BB
    # feito nela fica guardado para as próximas vezes.
    print(f"  {ico('chrome')}  Abrindo a janela do Chrome da automação (perfil próprio)...")
    if not iniciar_chrome_debug(caminho, perfil_dedicado=True):
        msg_erro("O Chrome abriu, mas a porta de depuração não respondeu.")
        msg_dica(f"Feche as janelas do Chrome da automação e tente de novo. "
                 f"Perfil: {PASTA_PERFIL_DEDICADO}")
        return False

    if not cfg.perfil_dedicado:
        cfg.perfil_dedicado = True
        cfg.salvar()
    msg_ok(f"Chrome da automação aberto na porta {PORTA_DEPURACAO}.")
    if interativo:
        msg_dica("Se o BB pedir login, entre nessa janela (só na primeira vez).")
        pausar("Depois de logar no BB, pressione Enter (Enviar) para continuar")
    return True


# ============================================================================
# AUTOMAÇÃO 1 — CARREGAMENTO PELO PORTADOR
# ============================================================================

def abas_travadas(porta=PORTA_DEPURACAO, espera=4):
    """
    [(target_id, titulo, url)] das abas cujo JavaScript não responde.

    O connect_over_cdp do Playwright se liga a TODAS as abas do Chrome e
    espera cada uma responder. Uma aba parada num alert()/confirm() ou numa
    impressão (visto com o SIGEF) segura a conexão até o timeout, calada.
    Aqui cada aba recebe um "1" para avaliar; quem não responde é apontado.
    """
    travadas = []
    try:
        cdp = ConexaoCDP(_endpoint_browser(porta), timeout=espera)
    except Exception:
        return travadas
    try:
        alvos = cdp.enviar("Target.getTargets", timeout=espera).get("targetInfos", [])
        for alvo in alvos:
            if alvo.get("type") != "page":
                continue
            try:
                sessao = cdp.enviar("Target.attachToTarget",
                                    {"targetId": alvo["targetId"], "flatten": True},
                                    timeout=espera)["sessionId"]
            except Exception:
                continue
            try:
                cdp.enviar("Runtime.evaluate", {"expression": "1"},
                           session_id=sessao, timeout=espera)
            except TimeoutError:
                travadas.append((alvo["targetId"], alvo.get("title", ""), alvo.get("url", "")))
            except Exception:
                pass
            try:
                cdp.enviar("Target.detachFromTarget", {"sessionId": sessao}, timeout=3)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        cdp.fechar()
    return travadas


def fechar_abas(abas, porta=PORTA_DEPURACAO):
    try:
        cdp = ConexaoCDP(_endpoint_browser(porta), timeout=5)
    except Exception as erro:
        msg_alerta(f"Não consegui falar com o Chrome para fechar as abas: {erro}")
        return
    try:
        for target_id, titulo, _url in abas:
            try:
                cdp.enviar("Target.closeTarget", {"targetId": target_id}, timeout=5)
                msg_ok(f"Aba fechada: {titulo or target_id}")
            except Exception as erro:
                msg_alerta(f"Não consegui fechar '{titulo}': {erro}")
    finally:
        cdp.fechar()
    time.sleep(1.5)


def conectar_navegador(playwright):
    print(f"  {ico('chrome')}  Conferindo se todas as abas do Chrome respondem...")
    while True:
        travadas = abas_travadas()
        if not travadas:
            break
        print()
        msg_alerta(f"{len(travadas)} aba(s) do Chrome não respondem. Com elas assim, "
                   f"a automação não consegue se conectar:")
        for _id, titulo, url in travadas:
            print(f"       - {titulo or '(sem título)'}  ·  {url[:90]}")
        msg_dica("Quase sempre é um alerta, uma confirmação ou uma impressão aberta "
                 "nessa aba. Resolva lá mesmo (ou feche a aba) e tente de novo.")
        resposta = perguntar(
            f"  {C.NEGRITO}Enter para verificar de novo · 'f' para FECHAR essa(s) aba(s) "
            f"(perde o que não foi salvo nela) · 'c' para cancelar{C.RESET} ")
        if foi_cancelado(resposta) or resposta.lower().startswith("c"):
            raise ErroDeUso("Conexão cancelada: há aba travada no Chrome.")
        if resposta.lower().startswith("f"):
            fechar_abas(travadas)

    try:
        return playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{PORTA_DEPURACAO}", timeout=60000)
    except Exception as erro:
        raise ErroDeUso(
            f"Não consegui conectar no Chrome da porta {PORTA_DEPURACAO}: "
            f"{str(erro).splitlines()[0]}\n"
            f"       Confira se alguma aba está com alerta/impressão aberta e tente de novo."
        )


def obter_pagina_bb(browser, cfg):
    """Reaproveita a aba do BB já aberta (é onde a sessão está logada)."""
    context = browser.contexts[0]
    context.set_default_timeout(30000)

    page = None
    for aba in context.pages:
        if aba.is_closed():
            continue
        url_aba = (aba.url or "").lower()
        if "bb.com.br" in url_aba and "autoatendimento" in url_aba:
            page = aba
            print("[OK] Aba do BB encontrada.")
            break

    if page is None:
        page = context.new_page()
        page.goto(URL_DASHBOARD)
    else:
        # No modo invisível não trazemos nada pra frente: a promessa é não
        # atrapalhar o que você estiver fazendo na máquina.
        if cfg.modo_visivel:
            try:
                page.bring_to_front()
            except PlaywrightError:
                pass
        if "apf-apj-autoatendimento" not in (page.url or ""):
            page.goto(URL_DASHBOARD)

    page.wait_for_load_state("domcontentloaded")

    # O host e a versão mudam (autoatendimento / autoatendimento2, ?v=...):
    # a URL do portador é montada a partir da aba que está aberta de fato.
    global URL_PORTADOR
    base = (page.url or "").split("#")[0]
    if "apf-apj-autoatendimento" in base:
        URL_PORTADOR = base + "#/template/~2Fcartoes~2FVP33-A2.bb"

    # Antes de qualquer coisa: o balão "Ainda está aí?" pode aparecer a
    # qualquer momento daqui em diante.
    instalar_guarda_sessao(page)
    manter_sessao_viva(page, forcar=True)
    return page


def preparar_sessao(page):
    """
    Navegação Menu > Cartão > Portador, feita UMA vez por execução.
    É o que inicializa a sessão do módulo de cartões; depois disso cada
    cartão é só um page.goto(URL_PORTADOR).
    """
    icone_menu = page.locator("i.mi.mi--menu.mpjv").first
    item_cartao = page.locator("div.col-name-menu.mpjv", has_text="Cartão").first
    item_portador_nv2 = page.locator("li.item-menu-segundo-nivel", has_text="Portador").first
    item_portador_nv3 = page.locator("li.item-menu-terceiro-nivel", has_text="Portador").first

    clicar_com_confirmacao(icone_menu, "ícone do menu (☰)",
                           aguardar_apos=item_cartao, usar_hover=False)
    clicar_com_confirmacao(item_cartao, "menu 'Cartão'", aguardar_apos=item_portador_nv2)
    clicar_com_confirmacao(item_portador_nv2, "submenu 'Portador' (2º nível)",
                           aguardar_apos=item_portador_nv3)
    clicar_com_confirmacao(item_portador_nv3, "opção 'Portador' (3º nível)")
    print("[OK] Sequência Menu > Cartão > Portador concluída.")


# ----------------------------------------------------------------------------
# CARGAS: caminho Cartão > Órgão > Portador
# ----------------------------------------------------------------------------
# A tela de Cartão > Portador > Portador (URL_PORTADOR, "VP33-A2") é a de
# DADOS DO PORTADOR, que só o próprio portador pode usar: com o órgão, o
# número do cartão ia para lá e o portal respondia "Permitida para
# representante autorizado". Nas cargas (limite e avulsa) o cartão é
# digitado na tela de Cartão > Órgão > Portador. O endereço dessa tela é
# guardado depois do menu (URL_CARTAO_ORGAO) para voltar a ela entre um
# cartão e outro; se ele não servir, refaz o caminho pelo menu.

ROTA_CARTAO = "portador"      # "orgao" durante as cargas (definir_rota_cartao)
URL_CARTAO_ORGAO = None       # aprendido em preparar_sessao_orgao()


def definir_rota_cartao(rota):
    """'orgao' (cargas) ou 'portador' (demonstrativos): por onde chegar ao campo do cartão."""
    global ROTA_CARTAO
    ROTA_CARTAO = rota


def preparar_sessao_orgao(page):
    """
    Menu > Cartão > Órgão > Portador, até o campo 'Número do cartão'
    (input numeroPlasticoFormatado). Guarda o endereço da tela para as
    próximas voltas. Levanta ErroDeUso se o caminho não abrir.
    """
    global URL_CARTAO_ORGAO
    icone_menu = page.locator("i.mi.mi--menu.mpjv").first
    item_cartao = page.locator("div.col-name-menu.mpjv", has_text="Cartão").first
    item_orgao = page.locator(
        "li.item-menu-segundo-nivel", has_text=re.compile(r"[ÓOóo]rg[ãa]o")).first
    item_portador = page.locator(
        "li.item-menu-terceiro-nivel:visible", has_text=re.compile(r"^\s*Portador\s*$")).first
    try:
        clicar_com_confirmacao(icone_menu, "ícone do menu (☰)",
                               aguardar_apos=item_cartao, usar_hover=False)
        clicar_com_confirmacao(item_cartao, "menu 'Cartão'", aguardar_apos=item_orgao)
        clicar_com_confirmacao(item_orgao, "submenu 'Órgão' (2º nível)",
                               aguardar_apos=item_portador)
        clicar_com_confirmacao(item_portador, "opção 'Portador' do Órgão (3º nível)")
        esperar_carregamento_sumir(page)
        esperar_rede_ociosa(page)
        campo = localizar_campo_cartao(page, timeout=30000)
    except Exception as erro:
        raise ErroDeUso(
            "Não consegui abrir Cartão > Órgão > Portador no menu do BB "
            f"({str(erro).splitlines()[0]}). Confira se o portal está logado e "
            "na página inicial, e tente de novo."
        )
    url = page.url or ""
    if "apf-apj-autoatendimento" in url and "#" in url:
        URL_CARTAO_ORGAO = url
    print("[OK] Sequência Menu > Cartão > Órgão > Portador concluída.")
    return campo


def ir_para_tela_cartao_orgao(page):
    """
    De volta ao campo do cartão pela rota do Órgão: pelo endereço guardado
    (com recarga, porque é rota de hash) e, se não der, pelo menu de novo.
    Nunca pela URL do portador (VP33-A2).
    """
    if URL_CARTAO_ORGAO:
        try:
            page.goto(URL_CARTAO_ORGAO)
            page.wait_for_load_state("domcontentloaded")
            esperar_rede_ociosa(page)
            return localizar_campo_cartao(page, timeout=15000)
        except (TimeoutError, PlaywrightError):
            pass
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            esperar_rede_ociosa(page)
            esperar_carregamento_sumir(page)
            return localizar_campo_cartao(page, timeout=20000)
        except (TimeoutError, PlaywrightError):
            pass
    msg_alerta("Voltando ao campo do cartão pelo menu (Cartão > Órgão > Portador).")
    return preparar_sessao_orgao(page)


def texto_mensagem_erro(page):
    """
    Texto da caixa de erro padrão do portal, ou "" se não houver nenhuma.

    É aquele bloco com o imgErro.gif e o "Atenção!" em negrito:

        <table id="tdMensagemErroPadrao"> ...
          <td class="textoErro">
            <b class="textoErroTitulo">Atenção!</b>
            <b>Permitida para representante autorizado (C108-010)</b>
    """
    for alvo in [page] + list(page.frames):
        try:
            loc = alvo.locator(SELETOR_MENSAGEM_ERRO)
            if loc.count() > 0 and loc.first.is_visible():
                texto = " ".join(loc.first.inner_text().split())
                if texto:
                    return texto
        except PlaywrightError:
            continue

    # Rede de segurança: se o portal mudar a estrutura da caixa de erro, o
    # seletor deixa de casar — mas o TEXTO continua o mesmo. Procuramos os
    # padrões conhecidos diretamente no conteúdo de cada frame.
    for alvo in [page] + list(page.frames):
        try:
            conteudo = alvo.inner_text("body")
        except PlaywrightError:
            continue
        except Exception:
            continue
        if not conteudo:
            continue
        normalizado = conteudo.lower()
        for padrao in PADROES_REPRESENTANTE:
            if padrao in normalizado:
                for pedaco in conteudo.splitlines():
                    if padrao in pedaco.lower():
                        return " ".join(pedaco.split())
                return padrao
    return ""


def classificar_erro_portal(mensagem):
    """Transforma o texto da caixa de erro na exceção certa."""
    normalizado = mensagem.lower()
    if any(padrao in normalizado for padrao in PADROES_REPRESENTANTE):
        return CartaoBloqueado(mensagem, marca=MARCA_REPRESENTANTE)
    return ErroDoPortal(mensagem)


def esperar_portador_ou_erro(page, timeout=30000, intervalo=300):
    """
    Espera a linha "Portador" aparecer OU o portal responder com erro — o que
    vier primeiro.

    Esta corrida é o ponto da mudança: antes, um cartão recusado com
    "Permitida para representante autorizado (C108-010)" ficava 30 segundos
    esperando um elemento que nunca ia chegar, e só então virava timeout
    genérico. Agora a recusa é reconhecida na hora, vira CartaoBloqueado, a
    linha é marcada como 'representante' na coluna J e o lote segue.
    """
    restante = timeout
    while restante > 0:
        mensagem = texto_mensagem_erro(page)
        if mensagem:
            raise classificar_erro_portal(mensagem)

        for alvo in [page] + list(page.frames):
            try:
                loc = alvo.locator(SELETOR_PORTADOR)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except PlaywrightError:
                continue

        page.wait_for_timeout(intervalo)
        restante -= intervalo

    # Última olhada: a mensagem pode ter demorado a renderizar.
    mensagem = texto_mensagem_erro(page)
    if mensagem:
        raise classificar_erro_portal(mensagem)

    raise TimeoutError(
        f"Não encontrei a linha 'Portador' nem mensagem de erro do portal "
        f"após {timeout}ms."
    )


def abrir_popup_portador(page):
    alvo = esperar_portador_ou_erro(page, timeout=30000)
    print(f"[OK] Portador: '{alvo.inner_text().strip()}'")
    clicar_com_confirmacao(alvo, "portador selecionado", usar_hover=False)


def clicar_primeira_opcao_popup(page, descricao, reabrir, texto_esperado=None):
    """
    Os popups desse portal fecham sozinhos poucos segundos depois de abertos
    (há um setTimeout('HidePopup(...)') no onclick). Por isso: timeout curto
    por tentativa e, se já tiver fechado, `reabrir()` e tentar de novo.

    A 1ª opção é localizada pelo onclick (ajaxProcessUrl), não pela classe
    CSS — ela varia entre "linkPopUp" e "linkPopup" dependendo da tela.
    """
    link = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            link = encontrar_em_qualquer_frame(
                page, SELETOR_PRIMEIRA_OPCAO_POPUP, descricao=descricao, timeout=4000,
                salvar_debug_em_falha=(tentativa == MAX_TENTATIVAS),
            )
            break
        except TimeoutError:
            if tentativa == MAX_TENTATIVAS:
                raise
            print(f"[AVISO] Popup não apareceu (tentativa {tentativa}/{MAX_TENTATIVAS}) "
                  f"— deve ter fechado sozinho. Reabrindo...")
            reabrir()

    texto = link.inner_text().strip()
    print(f"[OK] 1ª opção do popup: '{texto}'")
    if texto_esperado and texto_esperado.lower() not in texto.lower():
        print(f"[AVISO] Texto ('{texto}') não parece ser '{texto_esperado}'.")

    clicar_com_confirmacao(link, descricao, usar_hover=False)


def esperar_frame_da_tabela(page, timeout=25000, intervalo=300):
    """
    Procuramos direto pelas LINHAS, não pela tabela: a classe
    'tabelaTrsResposta' é genérica e existe em outras telas com 0 linhas.
    """
    tempo_restante = timeout
    while tempo_restante > 0:
        for alvo in [page] + list(page.frames):
            try:
                loc = alvo.locator(SELETOR_LINHAS)
                if loc.count() > 0 and loc.first.is_visible():
                    return alvo
            except PlaywrightError:
                continue
        manter_sessao_viva(page)
        page.wait_for_timeout(intervalo)
        tempo_restante -= intervalo
    return None


SELETOR_CAMPO_CARTAO = "input[name='numeroPlasticoFormatado']"
SELETOR_BOTAO_VOLTAR = "input[name='botao.acao.voltar']"
SELETOR_BOTAO_NOVA = "input[name='botao.acao.nova']"


def localizar_campo_cartao(page, timeout=15000, debug=False):
    return encontrar_em_qualquer_frame(
        page, SELETOR_CAMPO_CARTAO, descricao="campo 'Número do cartão'",
        timeout=timeout, salvar_debug_em_falha=debug,
    )


def ir_para_tela_portador(page):
    """
    Garante que a tela do portador (com o campo do número do cartão) está no ar.

    Três níveis, do mais barato ao mais bruto:

      1. Já estamos nela? É o caso normal entre um cartão e o próximo, depois
         do "Voltar" + "Nova" — aí não navegamos nada e economizamos segundos.
      2. Um goto na URL do portador.
      3. Um reload de verdade. Isto existe porque a URL do portador é uma rota
         de HASH (#/template/...). Navegar para a MESMA url com hash igual não
         recarrega coisa alguma no Chromium: o goto retorna na hora e a tela
         continua onde estava. Sem o reload, o segundo cartão em diante podia
         ficar preso na tela de demonstrativos do cartão anterior.
    """
    try:
        return localizar_campo_cartao(page, timeout=4000)
    except TimeoutError:
        pass

    if ROTA_CARTAO == "orgao":
        return ir_para_tela_cartao_orgao(page)

    page.goto(URL_PORTADOR)
    page.wait_for_load_state("domcontentloaded")
    esperar_rede_ociosa(page)
    try:
        return localizar_campo_cartao(page, timeout=15000)
    except TimeoutError:
        pass

    page.reload(wait_until="domcontentloaded", timeout=60000)
    esperar_rede_ociosa(page)
    esperar_carregamento_sumir(page)
    return localizar_campo_cartao(page, timeout=30000, debug=True)


def voltar_para_nova_transacao(page):
    """
    Encerra o cartão atual pelo caminho do próprio sistema: "Voltar" e depois
    "Nova", que reinicia a transação e devolve a tela do portador do cartão —
    pronta para receber o número da próxima linha da planilha.

    Só damos a operação por concluída quando o campo do número do cartão
    reaparece; é a prova de que o "Nova" fez efeito.
    """
    botao_voltar = encontrar_em_qualquer_frame(
        page, SELETOR_BOTAO_VOLTAR, descricao="botão 'Voltar' (fim do cartão)",
        timeout=20000, salvar_debug_em_falha=False,
    )
    clicar_com_confirmacao(botao_voltar, "botão 'Voltar' (fim do cartão)", usar_hover=False)
    esperar_carregamento_sumir(page)
    esperar_rede_ociosa(page)

    botao_nova = encontrar_em_qualquer_frame(
        page, SELETOR_BOTAO_NOVA, descricao="botão 'Nova' (nova transação)",
        timeout=20000, salvar_debug_em_falha=False,
    )
    clicar_com_confirmacao(botao_nova, "botão 'Nova' (nova transação)", usar_hover=False)
    esperar_carregamento_sumir(page)
    esperar_rede_ociosa(page)

    localizar_campo_cartao(page, timeout=30000)
    return True


def abrir_lista_demonstrativos(page, linha):
    """
    Da tela do portador até a tabela de demonstrativos mensais do cartão da
    linha: preenche o cartão -> Ok -> popup do portador -> "Demonstrativos
    mensais". Devolve (frame_da_tabela, total_de_linhas).

    Está numa função separada porque é usada em três momentos: no começo do
    cartão, na RECUPERAÇÃO quando a tela se perde depois do "Voltar", e a cada
    nova linha da planilha.
    """
    campo = ir_para_tela_portador(page)
    campo.fill(linha.numero_cartao)
    print(f"[OK] Cartão preenchido: {linha.numero_cartao}")

    botao_ok = encontrar_em_qualquer_frame(
        page, "input[name='botao.acao.ok']", descricao="botão 'Ok'"
    )
    clicar_com_confirmacao(botao_ok, "botão 'Ok'", usar_hover=False)

    abrir_popup_portador(page)
    clicar_primeira_opcao_popup(
        page, "1ª opção do popup ('Demonstrativos mensais')",
        reabrir=lambda: abrir_popup_portador(page), texto_esperado="Demonstrativ",
    )

    page.wait_for_load_state("domcontentloaded")
    esperar_rede_ociosa(page)

    frame = esperar_frame_da_tabela(page)
    if frame is None:
        raise TimeoutError("Não encontrei a tabela de demonstrativos mensais.")
    return frame, frame.locator(SELETOR_LINHAS).count()


def recuperar_pagina(page, linha, motivo, tentativas=TENTATIVAS_RECUPERACAO):
    """
    Plano de recuperação quando a tela trava/some depois do "Voltar".

    Recarrega a página (F5), espera carregar e refaz o caminho até a lista de
    demonstrativos daquele mesmo cartão. Assim um timeout isolado custa uns
    segundos em vez de derrubar o cartão inteiro — os PDFs já baixados
    continuam no lugar e a automação retoma do próximo demonstrativo.

    Devolve (frame, total) ou (None, 0) se nem a recuperação funcionou.
    """
    for tentativa in range(1, tentativas + 1):
        msg_alerta(f"{motivo} — recuperando ({tentativa}/{tentativas}): "
                   f"atualizando a página...")
        try:
            # Um preview de impressão preso deixaria o JS travado e o reload
            # penduraria; então tiramos ele da frente antes.
            try:
                fechar_preview_se_aberto(page)
            except Exception:
                pass

            page.reload(wait_until="domcontentloaded", timeout=60000)
            esperar_rede_ociosa(page)
            esperar_carregamento_sumir(page)

            frame, total = abrir_lista_demonstrativos(page, linha)
            msg_ok(f"Página recuperada — {total} demonstrativo(s) de volta na tela.")
            return frame, total
        except ErroDoPortal:
            # O portal respondeu com a caixa de erro dele. Nova tentativa vai
            # dar exatamente na mesma resposta — repassa para quem chamou
            # anotar a linha e seguir.
            raise
        except Exception as erro:
            print(f"  {ico('alerta')} Recuperação {tentativa} falhou: "
                  f"{str(erro).splitlines()[0]}")
            time.sleep(2)

    return None, 0


def processar_cartao(page, linha, cfg):
    """
    Processa UM cartão (uma linha da planilha): abre a tela do portador,
    percorre os demonstrativos mensais e salva 1.pdf, 2.pdf, ... na pasta
    montada com as colunas A, B e E.

    Retorna (quantidade_salva, [erros_de_demonstrativo]).
    """
    pasta = linha.pasta_destino
    os.makedirs(pasta, exist_ok=True)

    frame_tabela, total_linhas = abrir_lista_demonstrativos(page, linha)
    print(f"[OK] {total_linhas} demonstrativo(s) para o cartão {linha.numero_cartao}.")

    salvos = 0
    erros = []

    for i in range(total_linhas):
        try:
            span_data = frame_tabela.locator(SELETOR_LINHAS).nth(i).locator("span.linkTrs")
            texto_data = span_data.inner_text().strip()

            clicar_com_confirmacao(span_data, f"demonstrativo {i + 1}/{total_linhas} "
                                              f"('{texto_data}')", usar_hover=False)

            def reabrir_data(indice=i):
                alvo = frame_tabela.locator(SELETOR_LINHAS).nth(indice).locator("span.linkTrs")
                clicar_com_confirmacao(alvo, f"demonstrativo {indice + 1} (reaberto)",
                                       usar_hover=False)

            clicar_primeira_opcao_popup(
                page, f"link 'Por lançamento' (demonstrativo {i + 1})",
                reabrir=reabrir_data, texto_esperado="ançamento",
            )

            # Sem networkidle aqui: a espera real está dentro do salvamento
            # (o "carregando" sumir + o ícone de imprimir aparecer).
            caminho_pdf = os.path.join(pasta, f"{i + 1}.pdf")
            print(f"[..] '{texto_data}' -> {caminho_pdf}")
            salvar_demonstrativo(page, caminho_pdf,
                                 f"botão imprimir (demonstrativo {i + 1})", cfg)
            salvos += 1
        except Exception as erro:
            erros.append(f"demonstrativo {i + 1}: {erro}")
            print(f"[ERRO] Demonstrativo {i + 1} falhou: {erro}")

        # Voltar para a tabela, mesmo depois de erro, para tentar o próximo.
        try:
            botao_voltar = encontrar_em_qualquer_frame(
                page, "input[name='botao.acao.voltar']",
                descricao=f"botão 'Voltar' (demonstrativo {i + 1})",
                salvar_debug_em_falha=False,
            )
            clicar_com_confirmacao(botao_voltar, f"botão 'Voltar' (demonstrativo {i + 1})",
                                   usar_hover=False)
        except Exception:
            print("[AVISO] Não achei o botão 'Voltar'; talvez já estejamos na tabela.")

        novo_frame = esperar_frame_da_tabela(page)

        if novo_frame is None:
            # Timeout depois do "Voltar" (os PDFs desta volta já estão em
            # disco). Em vez de perder o cartão inteiro: F5, espera carregar,
            # refaz o caminho até a lista e segue do próximo demonstrativo.
            novo_frame, novo_total = recuperar_pagina(
                page, linha, f"A tabela não voltou depois do 'Voltar' "
                             f"(demonstrativo {i + 1})",
            )
            if novo_frame is None:
                raise TimeoutError(
                    f"Depois do demonstrativo {i + 1}, a tabela não reapareceu "
                    f"nem após {TENTATIVAS_RECUPERACAO} tentativa(s) de recuperação."
                )
            erros.append(f"demonstrativo {i + 1}: tela recuperada após timeout no 'Voltar'")
            if novo_total and novo_total != total_linhas:
                msg_alerta(f"A lista agora mostra {novo_total} demonstrativo(s) "
                           f"(antes {total_linhas}); seguindo pelo total original.")

        frame_tabela = novo_frame

    return salvos, erros


def executar_carregamento_portador(cfg):
    """Automação 1: percorre a planilha e baixa os demonstrativos de cada cartão."""
    excel_visivel = cfg.modo_visivel
    if excel_utilizavel(cfg.caminho_planilha):
        msg_ok("Planilha será lida e gravada pelo Excel (pywin32).")
    else:
        msg_alerta("Sem acesso à planilha pelo Excel; usando openpyxl.")
        if os.name == "nt" and not tem_pywin32():
            msg_dica("Instale o pywin32 (pip install pywin32) — é o caminho que "
                     "funciona com a planilha aberta.")

    linhas = ler_linhas_planilha(cfg.caminho_planilha, cfg.aba_planilha,
                                 cfg.linha_inicial, visivel=excel_visivel)

    if not linhas:
        print(f"\n[AVISO] Nenhuma linha com a coluna D preenchida a partir da "
              f"linha {cfg.linha_inicial}. Nada a fazer.")
        return

    if PULAR_LINHAS_JA_MARCADAS:
        antes = len(linhas)
        linhas = [linha for linha in linhas if not linha.ja_marcada]
        if antes != len(linhas):
            msg_dica(f"{antes - len(linhas)} linha(s) já marcadas com "
                     f"'{MARCA_OK}' na coluna J foram puladas.")
        if not linhas:
            msg_ok("Todas as linhas já estavam marcadas. Nada a fazer.")
            return

    print()
    cabecalho(f"CARREGAMENTO PELO PORTADOR  ·  {len(linhas)} cartão(ões)", "foguete",
              f"Modo {cfg.rotulo_modo()}   ·   destino: {PASTA_RAIZ_PDFS}")
    print()

    marcador = MarcadorPlanilha(cfg.caminho_planilha, cfg.aba_planilha,
                                excel_visivel=excel_visivel)
    # Antes de gastar horas baixando PDF, descobrir se a marca vai conseguir
    # entrar na planilha. Se não for, é aqui que dá para resolver.
    conferir_gravacao_antes_de_comecar(marcador, linhas[0].numero)
    if not excel_utilizavel(cfg.caminho_planilha):
        avisar_formulas_nas_colunas(cfg)

    os.makedirs(PASTA_RAIZ_PDFS, exist_ok=True)
    resultados = []
    inicio = time.time()

    try:
        # Estes avisos existem por causa de um travamento real: a rodada
        # parava aqui, calada, e não dava para saber em que etapa. Agora a
        # última linha impressa diz exatamente onde a automação está.
        print(f"  {ico('chrome')}  Iniciando o Playwright...")
        with sync_playwright() as playwright:
            print(f"  {ico('chrome')}  Conectando ao Chrome na porta "
                  f"{PORTA_DEPURACAO}...")
            browser = conectar_navegador(playwright)
            print(f"  {ico('chrome')}  Procurando a aba do BB...")
            page = obter_pagina_bb(browser, cfg)

            definir_rota_cartao("portador")
            try:
                preparar_sessao(page)
            except Exception as erro:
                print(f"[AVISO] A navegação pelo menu falhou ({erro}). "
                      f"Vou tentar ir direto pela URL do portador.")

            for indice, linha in enumerate(linhas, start=1):
                if parada_pedida():
                    break
                print()
                separador()
                print(f"  {ico('pasta')}  {C.NEGRITO}[{indice}/{len(linhas)}]{C.RESET} "
                      f"{linha.resumo()}")
                separador()
                # Checkpoint: o balão pode ter nascido enquanto salvávamos o
                # PDF anterior. O guardião injetado já cuida, isto é reforço.
                manter_sessao_viva(page, forcar=True)
                marca_do_portal = None
                try:
                    salvos, erros = processar_cartao(page, linha, cfg)
                    situacao = "OK" if not erros else "PARCIAL"
                    resultados.append((linha, situacao, salvos, "; ".join(erros)))
                    msg_ok(f"Cartão concluído: {salvos} PDF(s) em {linha.pasta_destino}")
                except ErroDoPortal as erro:
                    # O portal RESPONDEU dizendo não (ex.: "Permitida para
                    # representante autorizado"). Insistir não muda nada:
                    # anota o motivo na coluna J e vai para a próxima linha.
                    situacao = "BLOQUEADO" if isinstance(erro, CartaoBloqueado) else "FALHA"
                    marca_do_portal = erro.marca
                    resultados.append((linha, situacao, 0, erro.mensagem))
                    msg_alerta(f"Linha {linha.numero} recusada pelo portal: {erro.mensagem}")
                except Exception as erro:
                    situacao = "FALHA"
                    resultados.append((linha, situacao, 0, str(erro).splitlines()[0]))
                    msg_erro(f"Linha {linha.numero} falhou: {erro}")
                    # Não deixa um preview preso travar as próximas linhas.
                    try:
                        fechar_preview_se_aberto(page)
                    except Exception:
                        pass

                # 1) Marca a coluna J ANTES de qualquer navegação: assim o
                #    registro do que já saiu não depende de a tela seguinte
                #    cooperar.
                anotar_resultado_na_planilha(marcador, linha, situacao,
                                             marca=marca_do_portal)

                # 2) "Voltar" e "Nova": é o caminho do próprio sistema para
                #    encerrar a transação e devolver a tela do portador, já
                #    pronta para o cartão da próxima linha.
                if indice < len(linhas):
                    preparar_proximo_cartao(page, indice, len(linhas))

            renovacoes = renovacoes_de_sessao(page)
            if renovacoes:
                msg_dica(f"A sessão do portal foi renovada {renovacoes} vez(es) "
                         f"durante a rodada.")
    finally:
        # Mesmo com Ctrl+C no meio do lote, o que já foi processado precisa
        # ficar registrado na planilha.
        fechar_marcacoes(marcador)

    imprimir_resumo(resultados, time.time() - inicio)


def conferir_gravacao_antes_de_comecar(marcador, numero_linha_exemplo, rodadas=4):
    """
    Teste de escrita ANTES do primeiro cartão, pelo mesmo caminho que a
    automação usa depois. Se não passar, você fica sabendo agora — e pode
    fechar a planilha e seguir sem perder nada.
    """
    pode, motivo = marcador.testar_escrita(numero_linha_exemplo)
    if pode:
        msg_ok("Teste de gravação na coluna J passou — as marcas entram linha a linha.")
        return True

    for rodada in range(rodadas):
        print()
        msg_erro("NÃO vou conseguir gravar a coluna J deste jeito.")
        msg_dica(f"Motivo: {motivo}")
        msg_dica("Feche a planilha no Excel (ou instale o pywin32, que permite gravar "
                 "com ela aberta) e tente de novo aqui.")
        resposta = perguntar(
            f"  {C.NEGRITO}Enter para testar de novo, ou 'p' para rodar assim mesmo"
            f"{C.RESET} ")
        if foi_cancelado(resposta) or resposta.lower().startswith("p"):
            break
        pode, motivo = marcador.testar_escrita(numero_linha_exemplo)
        if pode:
            msg_ok("Agora sim — gravação na coluna J liberada.")
            return True

    msg_alerta("Seguindo sem garantia de gravação: as marcas vão para uma fila e "
               "serão tentadas de novo no fim.")
    return False


def avisar_formulas_nas_colunas(cfg):
    """
    Alerta quando as colunas lidas são FÓRMULAS, e explica a consequência.

    Descoberta ao testar: quando o openpyxl salva a planilha (é o que fazemos
    para marcar a coluna J), ele descarta os valores em cache das fórmulas —
    a fórmula continua lá, mas o resultado guardado some. Como a leitura usa
    data_only=True (o resultado, não o texto "=..."), numa PRÓXIMA execução
    essas colunas viriam vazias até que o Excel abra e salve o arquivo de
    novo. Melhor avisar do que deixar você descobrir sozinho.
    """
    if openpyxl is None or cfg.caminho_planilha.lower().endswith(".csv"):
        return
    try:
        livro = openpyxl.load_workbook(cfg.caminho_planilha, data_only=False)
        try:
            nome = (cfg.aba_planilha if cfg.aba_planilha in livro.sheetnames
                    else livro.sheetnames[0])
            planilha = livro[nome]
            com_formula = []
            for coluna, letra in ((1, "A"), (2, "B"), (4, "D"), (5, "E")):
                valor = planilha.cell(row=cfg.linha_inicial, column=coluna).value
                if isinstance(valor, str) and valor.startswith("="):
                    com_formula.append(letra)
        finally:
            livro.close()
    except Exception:
        return

    if not com_formula:
        return

    msg_alerta(f"As colunas {', '.join(com_formula)} são fórmulas.")
    msg_dica("Ao gravar a coluna J, o openpyxl mantém as fórmulas mas descarta os "
             "resultados em cache. Numa PRÓXIMA execução essas colunas viriam vazias "
             "até você abrir e salvar a planilha no Excel uma vez.")
    msg_dica("Para evitar: use valores fixos nessas colunas (copiar > colar especial > "
             "valores), ou abra e salve a planilha no Excel antes de cada rodada.")


def anotar_resultado_na_planilha(marcador, linha, situacao, marca=None):
    """
    Escreve a marca da linha na coluna J e DIZ o que aconteceu, sempre.

    `marca` permite ao chamador sobrescrever o texto padrão — é assim que a
    recusa "Permitida para representante autorizado" vira 'representante' em
    vez de cair na regra genérica de falha.

    Isso roda no fim do laço de CADA linha, nunca no fim da automação.
    """
    if marca is None:
        marca = {
            "OK": MARCA_OK,
            "PARCIAL": MARCA_PARCIAL,
            "FALHA": MARCA_FALHA,
            "BLOQUEADO": MARCA_REPRESENTANTE,
        }.get(situacao, MARCA_FALHA)

    if not marca:
        print(f"  {ico('planilha')}  Linha {linha.numero}: coluna J deixada em branco "
              f"de propósito (situação {situacao}), para reprocessar depois.")
        return

    if marcador.marcar(linha.numero, marca):
        msg_ok(f"Coluna J da linha {linha.numero} gravada como '{marca}'.")
    else:
        msg_alerta(f"Coluna J da linha {linha.numero} NÃO foi gravada agora "
                   f"('{marca}' ficou na fila para o fim da execução).")
        if marcador.ultimo_erro_com:
            msg_dica(f"Motivo: {marcador.ultimo_erro_com[:120]}")


def preparar_proximo_cartao(page, indice, total):
    """
    Voltar -> Nova, deixando o site na tela do portador para a próxima linha.

    Se algo der errado aqui, não é motivo para abortar o lote: a próxima
    chamada de ir_para_tela_portador() navega pela URL (e recarrega, se
    precisar) e a execução segue.
    """
    try:
        voltar_para_nova_transacao(page)
        msg_ok(f"Nova transação aberta — pronto para o cartão {indice + 1}/{total}.")
        return True
    except Exception as erro:
        msg_alerta(f"Não consegui fazer 'Voltar' + 'Nova' ({str(erro).splitlines()[0]}). "
                   f"Vou chegar na tela do portador pela URL.")
        return False


def fechar_marcacoes(marcador, rodadas=3):
    """
    Última chance para as marcações que não entraram durante a rodada.

    Se ainda assim não der, em vez de só reclamar no log, avisamos e
    oferecemos: feche a planilha, aperte Enter, e gravamos na hora. É o
    caminho que sobra quando não há pywin32 e o arquivo ficou aberto o tempo
    todo — nenhuma marcação se perde por causa disso.
    """
    gravadas, pendentes = marcador.liberar()
    if gravadas:
        msg_ok(f"{gravadas} marcação(ões) pendente(s) gravadas na planilha agora.")
    if not pendentes:
        return

    for rodada in range(rodadas):
        print()
        msg_alerta(f"{len(pendentes)} marcação(ões) ainda não entraram na planilha: "
                   f"linhas {', '.join(str(n) for n, _ in pendentes)}")
        if marcador.ultimo_erro_com:
            msg_dica(f"Motivo do Excel: {marcador.ultimo_erro_com[:120]}")
        resposta = perguntar(
            f"  {C.NEGRITO}Feche a planilha e tecle Enter para gravar "
            f"(ou 'p' para pular){C.RESET} ")
        if foi_cancelado(resposta) or resposta.lower().startswith("p"):
            break
        gravadas, pendentes = marcador.liberar()
        if gravadas:
            msg_ok(f"{gravadas} marcação(ões) gravadas.")
        if not pendentes:
            return

    if pendentes:
        msg_alerta(f"{len(pendentes)} marcação(ões) ficaram de fora da planilha.")
        msg_dica("O resultado completo está no _execucoes.csv, ao lado dos PDFs.")


def registrar_log_execucao(resultados):
    """
    Anexa o resultado de cada linha num CSV ao lado dos PDFs.

    Numa rodada longa e desacompanhada, o terminal rola e some; esse arquivo
    é o registro que sobra para você conferir depois quais cartões ficaram
    incompletos e por quê.
    """
    caminho = os.path.join(PASTA_RAIZ_PDFS, "_execucoes.csv")
    novo = not os.path.exists(caminho)
    carimbo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(PASTA_RAIZ_PDFS, exist_ok=True)
        with open(caminho, "a", encoding="utf-8-sig", newline="") as arq:
            escritor = csv.writer(arq, delimiter=";")
            if novo:
                escritor.writerow(["data_hora", "linha_planilha", "cartao", "pasta",
                                   "situacao", "pdfs", "detalhe"])
            for linha, situacao, salvos, detalhe in resultados:
                escritor.writerow([carimbo, linha.numero, linha.numero_cartao,
                                   linha.nome_pasta, situacao, salvos, detalhe])
        print(f"  {ico('salvo')}  Log da execução: {caminho}")
    except OSError as erro:
        msg_alerta(f"Não consegui gravar o log da execução: {erro}")


def imprimir_resumo(resultados, segundos):
    print()
    cabecalho("RESUMO DA EXECUÇÃO", "salvo")
    print()

    ok = [r for r in resultados if r[1] == "OK"]
    parcial = [r for r in resultados if r[1] == "PARCIAL"]
    falha = [r for r in resultados if r[1] == "FALHA"]
    bloqueado = [r for r in resultados if r[1] == "BLOQUEADO"]
    total_pdfs = sum(r[2] for r in resultados)

    marcas = {
        "OK": (ico("ok"), C.VERDE),
        "PARCIAL": (ico("meio"), C.AMARELO),
        "FALHA": (ico("erro"), C.VERMELHO),
        "BLOQUEADO": (ico("cadeado"), C.ROXO),
    }
    for linha, situacao, salvos, detalhe in resultados:
        marca, cor = marcas.get(situacao, (ico("erro"), C.VERMELHO))
        print(f"  {marca}  {cor}linha {linha.numero:<5}{C.RESET} "
              f"{salvos:>3} PDF(s)   {linha.nome_pasta}")
        if detalhe:
            print(f"        {C.FRACO}{ico('seta')} {detalhe[:150]}{C.RESET}")

    print()
    separador()
    print(f"  {C.VERDE}{len(ok)} completo(s){C.RESET}  ·  "
          f"{C.AMARELO}{len(parcial)} parcial(is){C.RESET}  ·  "
          f"{C.VERMELHO}{len(falha)} com falha{C.RESET}"
          + (f"  ·  {C.ROXO}{len(bloqueado)} sem permissão{C.RESET}" if bloqueado else ""))
    print(f"  {ico('relogio')} {total_pdfs} PDF(s) em {segundos / 60:.1f} min")
    print(f"  {ico('pasta')}  {PASTA_RAIZ_PDFS}")
    registrar_log_execucao(resultados)


# ============================================================================
# AUTOMAÇÃO 2 — CARGA DE LIMITE DO CARTÃO CORPORATIVO (v4.0)
# ----------------------------------------------------------------------------
# Para cada linha da planilha (B = processo, C = cartão, D = valor):
#
#   1. cartão -> Ok -> portador -> "Limites" -> salva "Saldo Anterior - <cc>"
#   2. portador -> "Alterar limite do portador"
#        novoLimitePortador              = valor (D)
#        diário / semanal / mensal       = limiteDisponivel (p/ baixo) + valor
#   3. Ok -> Confirmar
#   4. Voltar, Voltar, Ok -> portador -> "Limites" -> salva "Novo Saldo - <cc>"
#   5. Voltar -> Nova -> próxima linha
#
# Os PDFs vão para saldos_carga/<processo>/, prontos para anexar no SEI.
#
# SEGURANÇA — isto movimenta dinheiro, então:
#   * modo SIMULAÇÃO: faz tudo até a tela do Confirmar e NÃO confirma;
#   * modo REAL só começa depois de digitar CARREGAR;
#   * cartão repetido na planilha exige decisão explícita;
#   * os 4 campos são relidos antes do Ok; qualquer diferença aborta a linha;
#   * a coluna F é gravada logo depois do Confirmar, e linha com F preenchida
#     nunca é processada de novo (nem em outra rodada);
#   * qualquer dúvida DEPOIS do Confirmar vira 'verificar' e pausa o lote.
# ============================================================================

COLUNA_CARGA_PROCESSO = 2   # B
COLUNA_CARGA_CARTAO = 3     # C
COLUNA_CARGA_VALOR = 4      # D
COLUNA_CARGA_STATUS = 6     # F

PASTA_SALDOS = os.path.join(PASTA_SCRIPT, "saldos_carga")
PASTA_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")

MARCA_CARGA_OK = "ok"
MARCA_CARGA_FEITA = "carregado - falta novo saldo"
MARCA_CARGA_VERIFICAR = "verificar"
MARCA_CARGA_REPRESENTANTE = "representante"
MARCA_CARGA_SIMULADO = "simulação ok"
PREFIXO_MARCA_ERRO = "erro: "

# Situações na coluna F que tiram a linha das próximas rodadas. Qualquer
# outra ("erro: ...", "simulação ok") é refeita — nada foi carregado nelas.
MARCAS_CONCLUIDAS = (MARCA_CARGA_OK, "carregado", MARCA_CARGA_VERIFICAR,
                     MARCA_CARGA_REPRESENTANTE)


def linha_concluida(status):
    status = (status or "").strip().lower()
    return any(status.startswith(m) for m in MARCAS_CONCLUIDAS)


def marca_de_erro(detalhe):
    return (PREFIXO_MARCA_ERRO + " ".join(str(detalhe).split()))[:120]


# Recusas conhecidas do portal ganham marca curta, fácil de filtrar na planilha.
MARCAS_RECUSA_CONHECIDA = (
    (re.compile(r"limite.*centro de custo", re.IGNORECASE), "erro: limite do centro de custo"),
)


def marca_de_recusa(mensagem):
    for padrao, marca in MARCAS_RECUSA_CONHECIDA:
        if padrao.search(mensagem):
            return marca
    return marca_de_erro(f"portal: {mensagem}")

PALAVRA_CONFIRMACAO = "CARREGAR"

SELETOR_BOTAO_OK = "input[name='botao.acao.ok']"
SELETOR_BOTAO_CONFIRMAR = "input[name='botao.transacao.confirmar']"
SELETOR_SALVAR = "#selectSalvar"
SELETOR_OPCAO_PDF = "xpath=//p[contains(normalize-space(.), 'Arquivo PDF')]"
SELETOR_LIMITE_DISPONIVEL = "#limiteDisponivel"
SELETOR_NOVO_LIMITE = "#novoLimitePortador"

# Filtros de carregamento. Na tela "Alterar limite do portador" o filtro i
# (a partir de 0) tem os campos #vlrLimDiario{i}, #vlrLimSemanal{i} e
# #vlrLimMensal{i}. Filtro não habilitado para o cartão = campos ausentes.
#
# Todo filtro presente recebe o mesmo valor: limite disponível (p/ baixo) +
# carga, em diário, semanal e mensal.
#
#   filtros             quantos o programa pode ter (índices 0..n-1)
#   todos_obrigatorios  True  = faltar qualquer um é "erro: habilitar filtros"
#                       False = preenche os que a escola tiver e ignora os
#                               outros na hora; erro só se não houver nenhum
#   digitar             True  = tecla a tecla (dispara a máscara do portal)
#                       False = valor já formatado direto no campo (rápido;
#                               o PROAFI tem até 81 campos)
FILTROS_PROAFI = (
    "AGENCIAS DE TURISMO", "ALUGUEL DE CARROS", "ARTIGOS ELETRONICOS", "CIAS AEREAS",
    "DROGARIAS E FARMACIAS", "ENTRETENIMENTO", "ESTACIONAMENTOS", "HOSPITAIS E CLINICAS",
    "HOTEIS", "JOALHERIA", "LOJAS DE DEPARTAMENTO", "MATERIAIS DE CONSTRUCAO",
    "MOVEIS E DECORACAO", "OUTROS VAREJOS", "PEDAGIOS", "PAGAMENTO DE CONVENIO",
    "PAGAMENTO DE TITULOS", "POSTOS DE COMBUSTIVEL", "RESTAURANTES",
    "REVENDAS DE VEICULOS", "SERVIÇOS E AUTOPECAS", "SERVICOS", "SUPERMERCADOS",
    "TELEMARKETING E CATALOGO", "TRANSFERENCIAS PARA CONTAS BB",
    "TRANSFERENCIA PARA OUTROS BANCOS", "VESTUARIO",
)
PROGRAMAS_CARGA = {
    "PNAE": {"filtros": 1, "todos_obrigatorios": True, "digitar": True, "nomes": ()},
    "PROAFI": {"filtros": len(FILTROS_PROAFI), "todos_obrigatorios": False,
               "digitar": False, "nomes": FILTROS_PROAFI},
}
PROGRAMA_CARGA = "PNAE"   # trocado por escolher_programa_carga() a cada rodada
TIMEOUT_FILTROS = 3.0     # segundos: a tela já carregou quando conferimos
MARCA_CARGA_FILTROS = "erro: habilitar filtros"


def nome_do_filtro(indice):
    nomes = PROGRAMAS_CARGA[PROGRAMA_CARGA]["nomes"]
    return nomes[indice] if indice < len(nomes) else f"filtro {indice + 1}"


def campos_do_filtro(indice):
    nome = nome_do_filtro(indice)
    return ((f"#vlrLimDiario{indice}", f"diário ({nome})"),
            (f"#vlrLimSemanal{indice}", f"semanal ({nome})"),
            (f"#vlrLimMensal{indice}", f"mensal ({nome})"))


def escolher_programa_carga():
    """Pergunta o programa (se houver mais de um). False = cancelado."""
    global PROGRAMA_CARGA
    programas = list(PROGRAMAS_CARGA)
    if len(programas) == 1:
        PROGRAMA_CARGA = programas[0]
        return True
    print()
    for i, nome in enumerate(programas, start=1):
        filtros = PROGRAMAS_CARGA[nome]["filtros"]
        print(f"    [{i}]  {nome:<8} {C.FRACO}— {filtros} filtro{'s' if filtros > 1 else ''} "
              f"de carregamento{C.RESET}")
    while True:
        escolha = perguntar(f"\n  {C.NEGRITO}Programa {ico('seta')}{C.RESET} ")
        if foi_cancelado(escolha) or escolha.lower().startswith("c"):
            return False
        if escolha.isdigit() and 1 <= int(escolha) <= len(programas):
            PROGRAMA_CARGA = programas[int(escolha) - 1]
            msg_ok(f"Programa: {PROGRAMA_CARGA}")
            return True
        msg_alerta("Opção inválida.")

# Padrões (em ordem de preferência) do texto da opção no popup do portador.
OPCAO_LIMITES = (r"^\s*Limites\s*$",)
OPCAO_ALTERAR_LIMITE = (r"alterar.*limites?.*portador", r"alterar\s+(o\s+)?limites?")

TIMEOUT_DOWNLOAD = 60      # segundos
TIMEOUT_CONFIRMACAO = 30   # segundos para o portal responder ao Confirmar


class ErroDeCarga(Exception):
    """Algo deu errado ANTES do Confirmar: nada foi carregado."""


class CargaIncerta(Exception):
    """Algo deu errado DEPOIS de clicar em Confirmar: conferir à mão."""


class FiltrosDesabilitados(ErroDeCarga):
    """Os campos de algum filtro de carregamento não estão na tela."""

    def __init__(self, faltando, total):
        self.faltando = faltando
        if total == 1 or len(faltando) == total:
            self.marca = MARCA_CARGA_FILTROS
        else:
            self.marca = f"{MARCA_CARGA_FILTROS} ({', '.join(str(n) for n in faltando)})"
        super().__init__(f"filtro(s) de carregamento não habilitado(s): "
                         f"{', '.join(str(n) for n in faltando)} de {total}")


# -- valores ----------------------------------------------------------------

def decimal_br(texto):
    """'17.224,98' -> Decimal('17224.98'). Recusa formatos ambíguos."""
    bruto = re.sub(r"[^\d,.\-]", "", str(texto))
    if not bruto or not re.search(r"\d", bruto):
        raise ValueError(f"valor vazio ou ilegível: {texto!r}")
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    elif "." in bruto:
        if not re.fullmatch(r"-?\d{1,3}(\.\d{3})+", bruto):
            raise ValueError(f"valor ambíguo: {texto!r}")
        bruto = bruto.replace(".", "")
    try:
        return Decimal(bruto)
    except InvalidOperation:
        raise ValueError(f"valor ilegível: {texto!r}")


def valor_inteiro(valor):
    """Valor da coluna D como inteiro. Centavos são recusados, nunca arredondados."""
    if valor is None or texto_celula(valor) == "":
        raise ValueError("valor (coluna D) vazio")
    if isinstance(valor, bool):
        raise ValueError(f"valor inválido: {valor!r}")
    if isinstance(valor, (int, float)):
        numero = Decimal(str(valor))
    else:
        numero = decimal_br(valor)
    if numero != numero.to_integral_value():
        raise ValueError(f"valor {valor} tem centavos; o campo do portal só aceita inteiro")
    if numero <= 0:
        raise ValueError(f"valor {valor} não é positivo")
    return int(numero)


def formatar_milhar(numero):
    """20250 -> '20.250' (mesma máscara ###.###.### do portal)."""
    return f"{int(numero):,}".replace(",", ".")


def so_digitos(texto):
    return "".join(c for c in str(texto or "") if c.isdigit())


def calcular_limites(texto_limite_disponivel, valor):
    """
    (base, novo_limite_portador, limite_periodo)

    base            = limiteDisponivel arredondado para baixo
    novo_limite     = valor da carga (coluna D)
    limite_periodo  = base + valor  -> diário, semanal e mensal
    """
    disponivel = decimal_br(texto_limite_disponivel)
    base = int(disponivel.to_integral_value(rounding=ROUND_FLOOR))
    return base, valor, base + valor


# -- planilha ---------------------------------------------------------------

class LinhaCarga:

    def __init__(self, numero, processo, cartao, valor, status):
        self.numero = numero
        self.processo = texto_celula(processo)
        self.cartao = formatar_numero_cartao(cartao)
        self.digitos_cartao = so_digitos(self.cartao)
        self.status = texto_celula(status)
        self.valor = None
        self.problema = ""
        self.centro_custo = ""
        self.portador = ""

        try:
            self.valor = valor_inteiro(valor)
        except ValueError as erro:
            self.problema = str(erro)
        if len(self.digitos_cartao) != 16:
            self.problema = f"cartão com {len(self.digitos_cartao)} dígitos (esperado 16)"
        if not self.processo:
            self.problema = "processo (coluna B) vazio"

    @property
    def pasta(self):
        nome = _sanitizar_nome(self.processo.replace("/", "-")) or f"linha_{self.numero}"
        return os.path.join(PASTA_SALDOS, nome)

    def resumo(self):
        valor = formatar_milhar(self.valor) if self.valor is not None else "?"
        return f"linha {self.numero}: {self.cartao}  ·  R$ {valor}  ·  {self.processo}"


def ler_bruto_planilha(cfg, ultima_coluna, coluna_chave):
    """
    Valores crus das colunas A..ultima_coluna, da linha inicial até a última
    com `coluna_chave` preenchida. Excel (pywin32) primeiro, openpyxl de reserva.
    Cada item vem completado com None até `ultima_coluna`.
    """
    if not os.path.exists(cfg.caminho_planilha):
        raise ErroDeUso(f"Planilha não encontrada: {cfg.caminho_planilha}")

    brutos = None
    if excel_utilizavel(cfg.caminho_planilha):
        try:
            with ExcelCOM(cfg.caminho_planilha, cfg.aba_planilha, visivel=cfg.modo_visivel) as xl:
                ultima = xl.ultima_linha(coluna_chave)
                ultima = min(ultima, cfg.linha_inicial + LIMITE_LINHAS_PLANILHA - 1)
                brutos = xl.ler_intervalo(cfg.linha_inicial, ultima, colunas=ultima_coluna)
        except Exception as erro:
            msg_alerta(f"Não consegui ler a planilha pelo Excel ({erro}); usando openpyxl.")
            brutos = None

    if brutos is None:
        if openpyxl is None:
            raise ErroDeUso("openpyxl não instalado. Rode: pip install openpyxl")
        livro = openpyxl.load_workbook(cfg.caminho_planilha, data_only=True, read_only=True)
        try:
            nome = (cfg.aba_planilha if cfg.aba_planilha in livro.sheetnames
                    else livro.sheetnames[0])
            brutos = [list(v) for v in livro[nome].iter_rows(
                min_row=cfg.linha_inicial, max_col=ultima_coluna, values_only=True)]
        finally:
            livro.close()

    return [list(v) + [None] * (ultima_coluna - len(v)) for v in brutos]


def ler_linhas_carga(cfg):
    """Lê B, C, D e F da linha inicial até a última com a coluna C preenchida."""
    brutos = ler_bruto_planilha(cfg, COLUNA_CARGA_STATUS, COLUNA_CARGA_CARTAO)

    linhas = []
    for deslocamento, valores in enumerate(brutos):
        cartao = valores[COLUNA_CARGA_CARTAO - 1]
        valor = valores[COLUNA_CARGA_VALOR - 1]
        if not texto_celula(cartao) and not texto_celula(valor):
            continue
        linhas.append(LinhaCarga(cfg.linha_inicial + deslocamento,
                                 valores[COLUNA_CARGA_PROCESSO - 1], cartao, valor,
                                 valores[COLUNA_CARGA_STATUS - 1]))
    return linhas


# -- portal -----------------------------------------------------------------

def clicar_botao(page, seletor, descricao, timeout=20000):
    # Sem esperar_rede_ociosa: esse portal quase nunca fica 500ms sem
    # requisição, então aquilo custava até 6s por clique à toa. Quem vem
    # depois espera pelo ELEMENTO de que precisa.
    #
    # O botão clicado ganha a marca data-bb-clicado e só um botão SEM a marca
    # é aceito no clique seguinte. Sem isso, dois "Voltar" em sequência
    # podiam acertar o MESMO botão duas vezes, antes de a tela trocar.
    botao = encontrar_em_qualquer_frame(page, f"{seletor}:not([data-bb-clicado])",
                                        descricao=descricao, timeout=timeout)
    marcar_tela_antes_do_ok(page)
    clicar_elemento_uma_vez(botao, descricao)
    esperar_carregamento_sumir(page, intervalo=150)


def clicar_elemento_uma_vez(locator, descricao, timeout=15000):
    """
    Clica marcando o elemento com data-bb-clicado. Usa um handle (referência
    fixa ao elemento): o locator costuma ser "botão SEM a marca" e deixaria
    de achar o próprio botão depois de marcado.
    """
    elemento = locator.element_handle(timeout=timeout)
    elemento.evaluate("el => el.setAttribute('data-bb-clicado', '1')")
    try:
        elemento.click(timeout=timeout)
    except PlaywrightError:
        print(f"[AVISO] Clique padrão falhou em '{descricao}', tentando via JavaScript...")
        elemento.evaluate("el => el.click()")
    print(f"[OK] Clique realizado em: {descricao}")


# Caixa de erro padrão do portal + qualquer caixa com cara de erro/alerta.
_SELETOR_CAIXAS_ERRO = ("#tdMensagemErroPadrao, td.textoErro, .textoErro, [class*='rro'], "
                        "[id*='rro'], [class*='alert'], [role='alert']")

# Antes de cada Ok: carimba as mensagens de erro que JÁ estão na tela (as do
# cartão anterior, por exemplo). Sem isso, a mensagem velha seria lida como
# resposta do cartão novo.
JS_MARCAR_TELA_ANTES = r"""
(seletor) => {
  window.__bbAntesDoOk = true;
  document.querySelectorAll(seletor).forEach(
    el => el.setAttribute('data-bb-velho', (el.innerText || '').trim()));
}
"""

JS_ERRO_NA_TELA = r"""
([seletor, ignorarVelhos]) => {
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const tipico = /aten[çc][ãa]o|n[ãa]o\s|inv[áa]lid|erro|permitid|representante|negad|bloque|[A-Z]\d{3}-\d{3}/i;
  for (const el of document.querySelectorAll(seletor)) {
    if (!vis(el)) continue;
    const t = (el.innerText || '').trim();
    if (!t || t.length >= 400 || !tipico.test(t)) continue;
    if (ignorarVelhos && el.getAttribute('data-bb-velho') === t) continue;
    return t.replace(/\s+/g, ' ');
  }
  // Rede de segurança pelo TEXTO (estrutura da caixa mudou), só em
  // documento novo — num documento antigo o texto pode ser do cartão anterior.
  if (!ignorarVelhos || !window.__bbAntesDoOk) {
    const corpo = document.body ? document.body.innerText : '';
    const linha = corpo.split('\n').find(l => /representante autorizado|c108-010/i.test(l));
    if (linha) return linha.trim().replace(/\s+/g, ' ');
  }
  return '';
}
"""


def marcar_tela_antes_do_ok(page):
    for alvo in [page] + list(page.frames):
        try:
            alvo.evaluate(JS_MARCAR_TELA_ANTES, _SELETOR_CAIXAS_ERRO)
        except Exception:
            continue


def mensagem_de_erro_na_tela(page, ignorar_velhos=True):
    """Texto da primeira mensagem de erro NOVA na tela (ou '')."""
    for alvo in [page] + list(page.frames):
        try:
            mensagem = alvo.evaluate(JS_ERRO_NA_TELA, [_SELETOR_CAIXAS_ERRO, ignorar_velhos])
        except Exception:
            continue
        if mensagem:
            return mensagem
    return ""


def esperar_elemento_ou_erro(page, seletor, descricao, rotulo_debug,
                             timeout=15000, intervalo=150):
    """
    O portal responde quase na hora: ou aparece o elemento da próxima tela,
    ou uma caixa de erro. Corrida a cada 150ms entre os dois. Erro vira
    ErroDoPortal com o texto do banco (que vai para a coluna F).
    """
    restante = timeout
    while restante > 0:
        elemento = elemento_visivel(page, seletor)
        if elemento is not None:
            return elemento
        mensagem = mensagem_de_erro_na_tela(page)
        if mensagem:
            raise classificar_erro_portal(mensagem)
        page.wait_for_timeout(intervalo)
        restante -= intervalo

    # Nada novo em todo o prazo: se a mesma mensagem continua na tela, o
    # portal provavelmente repetiu o erro no mesmo lugar (cartão com o mesmo
    # problema do anterior).
    mensagem = mensagem_de_erro_na_tela(page, ignorar_velhos=False)
    if mensagem:
        raise classificar_erro_portal(mensagem)
    salvar_debug_da_tela(page, rotulo_debug)
    raise TimeoutError(f"{descricao} não apareceu em {timeout // 1000}s depois do Ok "
                       f"(tela salva em debug_html)")


def esperar_portador_rapido(page, timeout=15000):
    return esperar_elemento_ou_erro(page, SELETOR_PORTADOR, "o portador", "sem_portador",
                                    timeout=timeout)


def salvar_debug_da_tela(page, rotulo):
    pasta = os.path.join(PASTA_SCRIPT, "debug_html")
    os.makedirs(pasta, exist_ok=True)
    prefixo = os.path.join(pasta, f"{datetime.now():%Y%m%d_%H%M%S}_{rotulo}")
    for i, alvo in enumerate([page] + list(page.frames)):
        try:
            with open(f"{prefixo}_frame{i}.html", "w", encoding="utf-8") as arq:
                arq.write(alvo.content())
        except Exception:
            continue
    print(f"[DEBUG] Tela salva em {prefixo}_frame*.html")


def elemento_visivel(page, seletor):
    for alvo in [page] + list(page.frames):
        try:
            loc = alvo.locator(seletor)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except PlaywrightError:
            continue
    return None


JS_CENTRO_CUSTO = r"""
() => {
  const re = /^\s*\d+\s*-\s*\S/;
  const labels = [...document.querySelectorAll('label')]
    .filter(l => l.offsetParent !== null && re.test(l.innerText || ''));
  const perto = labels.find(l => {
    const bloco = l.closest('tr') || l.parentElement;
    return bloco && /centro/i.test(bloco.innerText || '');
  });
  const alvo = perto || labels[0];
  return alvo ? alvo.innerText.trim() : '';
}
"""


def ler_centro_custo(page, timeout=10000, intervalo=300):
    """Texto do <label> '44 - CARLOS GOMES' (ou '' se não aparecer)."""
    restante = timeout
    while restante > 0:
        for alvo in [page] + list(page.frames):
            try:
                texto = alvo.evaluate(JS_CENTRO_CUSTO)
            except Exception:
                continue
            if texto:
                return " ".join(texto.split())
        page.wait_for_timeout(intervalo)
        restante -= intervalo
    return ""


def nome_centro_custo(texto):
    """'44 - CARLOS GOMES' -> '44 CARLOS GOMES' (para nome de arquivo)."""
    return _sanitizar_nome(re.sub(r"^\s*(\d+)\s*-\s*", r"\1 ", texto))


def clicar_portador(page, linha):
    """Clica no <label> com o nome do portador (fallback: a linha 'Portador')."""
    if linha.portador:
        padrao = re.compile(rf"^\s*{re.escape(linha.portador)}\s*$")
        for _ in range(3):
            for alvo in [page] + list(page.frames):
                try:
                    loc = alvo.locator("label").filter(has_text=padrao)
                    if loc.count() > 0 and loc.first.is_visible():
                        clicar_com_confirmacao(loc.first, f"portador '{linha.portador}'",
                                               usar_hover=False)
                        return
                except PlaywrightError:
                    continue
            page.wait_for_timeout(1000)

    alvo = esperar_portador_ou_erro(page, timeout=30000)
    if not linha.portador:
        linha.portador = " ".join(alvo.inner_text().split())
    clicar_com_confirmacao(alvo, f"portador '{linha.portador}'", usar_hover=False)


JS_OPCAO_POPUP = r"""
(padroes) => {
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const todos = [...document.querySelectorAll('a')].filter(vis);
  const doPopup = todos.filter(a => /ajaxProcessUrl/.test(a.getAttribute('onclick') || '')
                                  || /popup/i.test(a.className || ''));
  const candidatos = doPopup.length ? doPopup : todos;
  for (const p of padroes) {
    const re = new RegExp(p, 'i');
    const a = candidatos.find(x => re.test((x.innerText || '').trim()));
    if (a) { const texto = (a.innerText || '').trim(); a.click(); return {clicado: texto}; }
  }
  if (!doPopup.length) return null;
  const caixa = doPopup[0].closest('table') || doPopup[0].parentElement;
  return {opcoes: doPopup.map(a => (a.innerText || '').trim()),
          html: caixa ? caixa.outerHTML.slice(0, 40000) : ''};
}
"""


def salvar_html_popup(info, descricao):
    """Guarda o HTML do popup (ele some em segundos, difícil copiar à mão)."""
    pasta = os.path.join(PASTA_SCRIPT, "debug_html")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f"{datetime.now():%Y%m%d_%H%M%S}_popup.html")
    try:
        with open(caminho, "w", encoding="utf-8") as arq:
            arq.write(f"<!-- procurando: {descricao} -->\n"
                      f"<!-- opções: {' | '.join(info.get('opcoes', []))} -->\n")
            arq.write(info.get("html", ""))
        print(f"[DEBUG] HTML do popup salvo em {caminho}")
    except OSError:
        pass


def clicar_opcao_popup(page, padroes, descricao, reabrir, timeout_tentativa=4000,
                       intervalo=150):
    """
    Clica numa opção do popup do portador pelo TEXTO.

    O popup fecha sozinho em poucos segundos, então a busca e o clique são
    feitos numa única chamada de JavaScript dentro da página (não dá tempo de
    ele sumir entre "achar" e "clicar"). Se o popup abrir sem a opção
    esperada, as opções que ele mostrou vão para o registro e o HTML dele é
    salvo em debug_html.
    """
    vistos = set()
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        restante = timeout_tentativa
        while restante > 0:
            for alvo in [page] + list(page.frames):
                try:
                    info = alvo.evaluate(JS_OPCAO_POPUP, list(padroes))
                except Exception:
                    continue
                if not info:
                    continue
                if info.get("clicado"):
                    print(f"[OK] Clique realizado em: {descricao} ('{info['clicado']}')")
                    esperar_carregamento_sumir(page, intervalo=150)
                    return
                opcoes = tuple(info.get("opcoes", []))
                if opcoes and opcoes not in vistos:
                    vistos.add(opcoes)
                    msg_alerta(f"O popup abriu sem '{descricao}'. Opções que apareceram: "
                               + " | ".join(f"'{o}'" for o in opcoes))
                    salvar_html_popup(info, descricao)
            page.wait_for_timeout(intervalo)
            restante -= intervalo
        if tentativa < MAX_TENTATIVAS:
            print(f"[AVISO] Opção '{descricao}' não apareceu (tentativa "
                  f"{tentativa}/{MAX_TENTATIVAS}); reabrindo o popup...")
            reabrir()
    raise TimeoutError(f"Opção '{descricao}' não apareceu no popup do portador.")


def abrir_cartao(page, linha):
    """Tela do portador -> cartão -> Ok. Lê centro de custo e nome do portador."""
    campo = ir_para_tela_portador(page)
    campo.fill(linha.cartao)
    print(f"[OK] Cartão preenchido: {linha.cartao}")

    clicar_botao(page, SELETOR_BOTAO_OK, "botão 'Ok' (cartão)")
    portador = esperar_portador_rapido(page)
    if not linha.portador:
        linha.portador = " ".join(portador.inner_text().split())

    if not linha.centro_custo:
        linha.centro_custo = ler_centro_custo(page, timeout=5000, intervalo=150)
    if not linha.centro_custo:
        raise ErroDeCarga("não achei o centro de custo na tela (label 'NN - NOME')")
    print(f"[OK] Centro de custo: {linha.centro_custo}  ·  Portador: {linha.portador}")


def abrir_limites(page, linha):
    clicar_portador(page, linha)
    clicar_opcao_popup(page, OPCAO_LIMITES, "opção 'Limites'",
                       reabrir=lambda: clicar_portador(page, linha))


def caminho_livre(caminho):
    """Não sobrescreve: 'x.pdf' -> 'x (2).pdf' se já existir."""
    if not os.path.exists(caminho):
        return caminho
    base, ext = os.path.splitext(caminho)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def pdfs_em_downloads():
    try:
        return {n for n in os.listdir(PASTA_DOWNLOADS) if n.lower().endswith(".pdf")}
    except OSError:
        return set()


def esperar_pdf_novo_em_downloads(antes, inicio, timeout=15):
    """Reserva: o PDF caiu direto na pasta Downloads sem o Playwright ver."""
    limite = time.time() + timeout
    while time.time() < limite:
        for nome in pdfs_em_downloads() - antes:
            caminho = os.path.join(PASTA_DOWNLOADS, nome)
            try:
                if os.path.getmtime(caminho) >= inicio - 2 and os.path.getsize(caminho) > 0:
                    tamanho = os.path.getsize(caminho)
                    time.sleep(0.8)
                    if os.path.getsize(caminho) == tamanho:
                        return caminho
            except OSError:
                continue
        time.sleep(0.5)
    return None


def baixar_saldo(page, destino):
    """Clica em #selectSalvar -> 'Arquivo PDF' e guarda o download em `destino`."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    destino = caminho_livre(destino)
    antes = pdfs_em_downloads()
    inicio = time.time()

    opcao = None
    for tentativa in range(1, 4):
        botao = encontrar_em_qualquer_frame(page, SELETOR_SALVAR,
                                            descricao="botão salvar (disquete)")
        clicar_com_confirmacao(botao, "botão salvar (disquete)", usar_hover=False)
        try:
            opcao = encontrar_em_qualquer_frame(page, SELETOR_OPCAO_PDF,
                                                descricao="opção 'Arquivo PDF'",
                                                timeout=5000,
                                                salvar_debug_em_falha=(tentativa == 3))
            break
        except TimeoutError:
            if tentativa == 3:
                raise

    try:
        with page.expect_download(timeout=TIMEOUT_DOWNLOAD * 1000) as info:
            clicar_com_confirmacao(opcao, "opção 'Arquivo PDF'", usar_hover=False)
        info.value.save_as(destino)
    except PlaywrightError:
        origem = esperar_pdf_novo_em_downloads(antes, inicio)
        if not origem:
            raise ErroDeCarga("o PDF do saldo não foi baixado")
        shutil.move(origem, destino)

    with open(destino, "rb") as arq:
        if arq.read(4) != b"%PDF":
            raise ErroDeCarga(f"o arquivo baixado não é um PDF: {destino}")
    msg_ok(f"Saldo salvo: {destino}")
    return destino


def preencher_valor(page, seletor, numero, descricao, digitar=True):
    """
    Preenche e confere. digitar=True: tecla a tecla (dispara a máscara do
    portal). digitar=False: o valor já formatado ('208.936') direto no
    campo — o mesmo resultado da máscara, muito mais rápido.
    """
    campo = encontrar_em_qualquer_frame(page, seletor, descricao=descricao)
    if digitar:
        campo.click()
        campo.press("Control+a")
        campo.press("Delete")
        campo.press_sequentially(str(numero), delay=60)
    if not digitar or so_digitos(campo.input_value()) != str(numero):
        campo.fill(formatar_milhar(numero))
    lido = campo.input_value()
    if so_digitos(lido) != str(numero):
        raise ErroDeCarga(f"{descricao}: digitei {formatar_milhar(numero)} "
                          f"mas o campo ficou com '{lido}'")
    print(f"[OK] {descricao}: {lido}")
    return campo


JS_TEXTO_E_CAMPOS = r"""
() => (document.body ? document.body.innerText : '') + ' ' +
      [...document.querySelectorAll('input')].map(i => i.value || '').join(' ')
"""


def texto_da_tela(page):
    partes = []
    for alvo in [page] + list(page.frames):
        try:
            partes.append(alvo.evaluate(JS_TEXTO_E_CAMPOS))
        except Exception:
            continue
    return " ".join(partes)


JS_FILTROS_PRESENTES = r"""
(quantidade) => {
  const ok = id => {
    const el = document.getElementById(id);
    return !!el && !el.disabled && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const presentes = [];
  for (let i = 0; i < quantidade; i++) {
    if (ok('vlrLimDiario' + i) && ok('vlrLimSemanal' + i) && ok('vlrLimMensal' + i)) presentes.push(i);
  }
  return presentes;
}
"""


def filtros_presentes(page, quantidade, todos_obrigatorios, espera=TIMEOUT_FILTROS):
    """
    Índices dos filtros com os 3 campos na tela e habilitados — lidos todos
    numa chamada só por frame. Programa que exige todos espera até `espera`
    pelos que faltam; o que aceita parte (PROAFI) devolve assim que houver
    algum filtro, sem esperar pelos que a escola não tem.
    """
    fim = time.time() + espera
    while True:
        melhor = []
        for alvo in [page] + list(page.frames):
            try:
                achados = alvo.evaluate(JS_FILTROS_PRESENTES, quantidade)
            except Exception:
                continue
            if len(achados) > len(melhor):
                melhor = achados
        completo = len(melhor) == quantidade
        if completo or (melhor and not todos_obrigatorios) or time.time() >= fim:
            return melhor
        page.wait_for_timeout(150)


def alterar_limite(page, linha):
    """Preenche novo limite + filtros, confere e clica em Ok. Devolve (base, novo, periodo)."""
    clicar_portador(page, linha)
    clicar_opcao_popup(page, OPCAO_ALTERAR_LIMITE, "opção 'Alterar limite do portador'",
                       reabrir=lambda: clicar_portador(page, linha))

    campo_disp = encontrar_em_qualquer_frame(page, SELETOR_LIMITE_DISPONIVEL,
                                             descricao="limite disponível")
    texto_disp = campo_disp.input_value()
    try:
        base, novo, periodo = calcular_limites(texto_disp, linha.valor)
    except ValueError as erro:
        raise ErroDeCarga(f"limite disponível ilegível ('{texto_disp}'): {erro}")
    if base < 0 or periodo <= 0:
        raise ErroDeCarga(f"limite disponível negativo ('{texto_disp}'); "
                          f"não mexi nos limites deste cartão")
    print(f"[..] Limite disponível {texto_disp} -> {formatar_milhar(base)} + "
          f"{formatar_milhar(novo)} = {formatar_milhar(periodo)}")

    # Antes de digitar QUALQUER coisa: os filtros do programa estão na tela?
    perfil = PROGRAMAS_CARGA[PROGRAMA_CARGA]
    quantidade = perfil["filtros"]
    presentes = filtros_presentes(page, quantidade, perfil["todos_obrigatorios"])
    faltando = [i + 1 for i in range(quantidade) if i not in presentes]
    if not presentes or (faltando and perfil["todos_obrigatorios"]):
        salvar_debug_da_tela(page, "filtros")
        raise FiltrosDesabilitados(faltando, quantidade)
    if faltando:
        print(f"[..] {PROGRAMA_CARGA}: {len(presentes)} de {quantidade} filtros nesta escola; "
              f"ignorados os que não existem: "
              f"{', '.join(nome_do_filtro(n - 1) for n in faltando)}")

    campos = [(preencher_valor(page, SELETOR_NOVO_LIMITE, novo, "novo limite do portador"),
               novo, "novo limite do portador")]
    for indice in presentes:
        for seletor, descricao in campos_do_filtro(indice):
            campos.append((preencher_valor(page, seletor, periodo, descricao,
                                           digitar=perfil["digitar"]),
                           periodo, descricao))

    # Conferência final: a máscara/saltaCampo pode ter mexido em algum campo
    # depois que o seguinte foi preenchido.
    for campo, esperado, descricao in campos:
        if so_digitos(campo.input_value()) != str(esperado):
            raise ErroDeCarga(f"{descricao} mudou para '{campo.input_value()}' "
                              f"(esperado {formatar_milhar(esperado)})")

    clicar_botao(page, SELETOR_BOTAO_OK, "botão 'Ok' (alterar limite)")
    # Aqui o portal pode recusar (ex.: a carga passa do limite do portador e
    # exige alteração de limite antes). O texto do banco vai para a coluna F.
    esperar_elemento_ou_erro(page, SELETOR_BOTAO_CONFIRMAR, "o botão Confirmar",
                             "sem_confirmar")
    return base, novo, periodo


def confirmar_carga(page, linha, novo, periodo, simulacao):
    """
    Está na tela do Confirmar. Confere o valor na tela e — só no modo REAL —
    clica em Confirmar. Devolve True se confirmou.
    """
    encontrar_em_qualquer_frame(page, SELETOR_BOTAO_CONFIRMAR,
                                descricao="botão 'Confirmar'", timeout=30000)
    # A confirmação mostra SALDO + CARGA (só mostraria a carga sozinha com o
    # cartão zerado). Esse total é o mesmo dos limites diário/semanal/mensal:
    # limite disponível arredondado para baixo + coluna D. É ele que conferimos
    # — "37.474" casa com "37.474" e com "37.474,98".
    tela = texto_da_tela(page)
    if not re.search(rf"(?<![\d.]){re.escape(formatar_milhar(periodo))}(?![\d.])", tela):
        valores = sorted(set(re.findall(r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?", tela)))
        salvar_debug_da_tela(page, "confirmacao")
        raise ErroDeCarga(f"a tela de confirmação não mostra {formatar_milhar(periodo)} "
                          f"(saldo + carga); valores na tela: {', '.join(valores[:8]) or 'nenhum'}. "
                          f"Não confirmei")
    msg_ok(f"Tela de confirmação conferida: R$ {formatar_milhar(periodo)} "
           f"(saldo + carga de R$ {formatar_milhar(novo)}).")

    if simulacao:
        msg_dica("SIMULAÇÃO: parei antes do Confirmar. Nada foi carregado.")
        return False

    botao = encontrar_em_qualquer_frame(page, SELETOR_BOTAO_CONFIRMAR,
                                        descricao="botão 'Confirmar'")
    # Daqui em diante qualquer erro vira 'verificar', nunca 'erro' (que seria
    # refeito numa próxima rodada e poderia carregar duas vezes).
    linha.clicou_confirmar = True
    marcar_tela_antes_do_ok(page)
    try:
        clicar_com_confirmacao(botao, "botão 'Confirmar'", usar_hover=False)
    except Exception as erro:
        raise CargaIncerta(f"falha ao clicar em Confirmar: {erro}")

    # Resposta do portal: ou erro, ou o botão Confirmar some.
    limite = time.time() + TIMEOUT_CONFIRMACAO
    while time.time() < limite:
        mensagem = mensagem_de_erro_na_tela(page)
        if mensagem:
            raise CargaIncerta(f"o portal respondeu ao Confirmar com: {mensagem}")
        if elemento_visivel(page, SELETOR_BOTAO_CONFIRMAR) is None:
            break
        page.wait_for_timeout(300)
    else:
        raise CargaIncerta("o botão Confirmar continuou na tela depois do clique")

    esperar_carregamento_sumir(page, intervalo=150)
    mensagem = mensagem_de_erro_na_tela(page)
    if mensagem:
        raise CargaIncerta(f"o portal respondeu ao Confirmar com: {mensagem}")
    try:
        os.makedirs(linha.pasta, exist_ok=True)
        page.screenshot(path=caminho_livre(os.path.join(
            linha.pasta, f"_tela_confirmacao - {nome_centro_custo(linha.centro_custo)}.png")),
            full_page=True)
    except Exception:
        pass
    msg_ok(f"Carga de R$ {formatar_milhar(novo)} confirmada no cartão {linha.cartao}.")
    return True


def proximo_cartao_rapido(page):
    """
    Deixa a tela pronta para o próximo cartão, sem esperar por botão que não
    existe: a cada 150ms, se o campo do cartão já está à vista (ex.: depois
    de um erro no cartão), pronto; senão clica no que houver — "Nova" (que
    abre a transação nova) ou "Voltar". Se nada disso resolver, o próximo
    ir_para_tela_portador() chega lá pela URL.
    """
    cliques = 0
    fim = time.time() + 15
    while time.time() < fim and cliques <= 4:
        if elemento_visivel(page, SELETOR_CAMPO_CARTAO) is not None:
            return
        for seletor, descricao in ((SELETOR_BOTAO_NOVA, "botão 'Nova'"),
                                   (SELETOR_BOTAO_VOLTAR, "botão 'Voltar'")):
            botao = elemento_visivel(page, f"{seletor}:not([data-bb-clicado])")
            if botao is not None:
                try:
                    clicar_elemento_uma_vez(botao, descricao, timeout=5000)
                    esperar_carregamento_sumir(page, intervalo=150)
                except Exception:
                    pass
                cliques += 1
                break
        page.wait_for_timeout(150)
    msg_alerta("Não voltei ao campo do cartão pelos botões; vou pela URL do portador.")


def reabrir_cartao_apos_carga(page, linha):
    """
    Depois do Confirmar: Voltar, Voltar — e o portal já está de novo na tela
    do portador (com o nome dele), pronta para "Limites". Não precisa digitar
    o cartão de novo.

    Só se o portador não aparecer (tela diferente da esperada) é que caímos
    no caminho longo: campo do cartão -> Ok.
    """
    for i in (1, 2):
        try:
            clicar_botao(page, SELETOR_BOTAO_VOLTAR, f"botão 'Voltar' ({i}/2)", timeout=15000)
        except TimeoutError:
            break

    padrao = re.compile(rf"^\s*{re.escape(linha.portador)}\s*$") if linha.portador else None
    fim = time.time() + 8
    while time.time() < fim:
        for alvo in [page] + list(page.frames):
            try:
                if padrao is not None:
                    loc = alvo.locator("label").filter(has_text=padrao)
                    if loc.count() > 0 and loc.first.is_visible():
                        return
                loc = alvo.locator(SELETOR_PORTADOR)
                if loc.count() > 0 and loc.first.is_visible():
                    return
            except PlaywrightError:
                continue
        page.wait_for_timeout(150)

    msg_alerta("Depois dos dois 'Voltar' o portador não apareceu; reabrindo pelo cartão.")
    campo = ir_para_tela_portador(page)
    if so_digitos(campo.input_value()) != linha.digitos_cartao:
        campo.fill(linha.cartao)
    clicar_botao(page, SELETOR_BOTAO_OK, "botão 'Ok' (reconsulta)")
    esperar_portador_rapido(page)


class GravadorColunaF:
    """
    Grava a coluna F sem segurar o portal.

    Cada marcação abre o Excel, grava, salva e relê para conferir — alguns
    segundos. Para erro/representante/simulação isso roda numa thread à
    parte (depois()), e a automação já segue para o próximo cartão. As marcas
    que impedem carga dupla ('carregado', 'ok') continuam síncronas
    (agora()). A trava garante uma gravação por vez no Excel.
    """

    def __init__(self, marcador, letra="F"):
        self.marcador = marcador
        self.letra = letra
        self.trava = threading.Lock()
        self.fila = queue.Queue()
        self.thread = threading.Thread(target=self._rodar, daemon=True)
        self.thread.start()

    def _rodar(self):
        while True:
            item = self.fila.get()
            if item is None:
                return
            numero, valor = item
            try:
                with self.trava:
                    gravou = self.marcador.marcar(numero, valor)
                if gravou:
                    msg_ok(f"Coluna {self.letra} da linha {numero}: '{valor}'")
            except Exception as erro:
                msg_alerta(f"Coluna {self.letra} da linha {numero} não gravada: {erro}")

    def depois(self, numero, valor):
        self.fila.put((numero, valor))

    def agora(self, numero, valor):
        with self.trava:
            return self.marcador.marcar(numero, valor)

    def terminar(self):
        pendentes = self.fila.qsize()
        if pendentes:
            print(f"  {ico('planilha')}  Terminando de gravar {pendentes} marcação(ões) "
                  f"na coluna F...")
        self.fila.put(None)
        self.thread.join()


def processar_carga(page, linha, simulacao, gravador):
    """
    Uma linha da planilha. Devolve (situacao, detalhe, arquivos).
    A coluna F é gravada aqui, logo depois do Confirmar.
    """
    arquivos = []
    abrir_cartao(page, linha)
    cc = nome_centro_custo(linha.centro_custo)

    abrir_limites(page, linha)
    arquivos.append(baixar_saldo(page, os.path.join(linha.pasta, f"Saldo Anterior - {cc}.pdf")))

    _base, novo, periodo = alterar_limite(page, linha)
    if not confirmar_carga(page, linha, novo, periodo, simulacao):
        return "SIMULADO", f"pararia em R$ {formatar_milhar(novo)} / " \
                           f"{formatar_milhar(periodo)}", arquivos

    # A partir daqui a carga ESTÁ feita: marcar antes de qualquer outra coisa.
    gravador.agora(linha.numero, MARCA_CARGA_FEITA)
    try:
        reabrir_cartao_apos_carga(page, linha)
        abrir_limites(page, linha)
        arquivos.append(baixar_saldo(page, os.path.join(linha.pasta, f"Novo Saldo - {cc}.pdf")))
    except Exception as erro:
        return "CARREGADO", f"carga feita, mas o novo saldo falhou: " \
                            f"{str(erro).splitlines()[0]}", arquivos

    gravador.agora(linha.numero, MARCA_CARGA_OK)
    return "OK", f"R$ {formatar_milhar(novo)}", arquivos


# -- preparação do lote -----------------------------------------------------

def resolver_repetidos(linhas):
    """Cartão repetido nunca passa em silêncio. Devolve a lista final ou None."""
    grupos = {}
    for linha in linhas:
        grupos.setdefault(linha.digitos_cartao, []).append(linha)
    repetidos = {k: v for k, v in grupos.items() if len(v) > 1}
    if not repetidos:
        return linhas

    print()
    msg_alerta(f"{len(repetidos)} cartão(ões) aparecem mais de uma vez:")
    for grupo in repetidos.values():
        numeros = ", ".join(str(l.numero) for l in grupo)
        print(f"     {grupo[0].cartao}  ·  linhas {numeros}  ·  "
              f"{' / '.join('R$ ' + formatar_milhar(l.valor) for l in grupo)}")
    print()
    print("    [1]  Carregar só a PRIMEIRA linha de cada cartão repetido")
    print("    [2]  Carregar TODAS as linhas (o cartão recebe mais de uma carga)")
    print("    [3]  Cancelar")
    while True:
        escolha = perguntar(f"\n  {C.NEGRITO}Opção {ico('seta')}{C.RESET} ")
        if foi_cancelado(escolha) or escolha == "3":
            return None
        if escolha == "1":
            vistos, final = set(), []
            for linha in linhas:
                if linha.digitos_cartao not in vistos:
                    vistos.add(linha.digitos_cartao)
                    final.append(linha)
            msg_dica(f"{len(linhas) - len(final)} linha(s) repetida(s) ficam de fora "
                     f"(sem marca na coluna F).")
            return final
        if escolha == "2":
            confirma = perguntar(f"  Digite REPETIR para confirmar cargas repetidas: ")
            if confirma.strip().upper() == "REPETIR":
                return linhas
        msg_alerta("Opção inválida.")


def escolher_modo_carga():
    """True = simulação, False = real, None = cancelar."""
    print()
    print(f"    [1]  SIMULAÇÃO  {C.FRACO}— faz tudo até a tela do Confirmar e NÃO confirma"
          f"{C.RESET}")
    print(f"    [2]  REAL       {C.FRACO}— confirma as cargas{C.RESET}")
    print("    [3]  Cancelar")
    while True:
        escolha = perguntar(f"\n  {C.NEGRITO}Modo {ico('seta')}{C.RESET} ")
        if foi_cancelado(escolha) or escolha == "3":
            return None
        if escolha in ("1", "2"):
            return escolha == "1"
        msg_alerta("Opção inválida.")


def registrar_log_carga(resultados, simulacao, mostrar=True):
    caminho = os.path.join(PASTA_SALDOS, "_cargas.csv")
    novo = not os.path.exists(caminho)
    carimbo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(PASTA_SALDOS, exist_ok=True)
        with open(caminho, "a", encoding="utf-8-sig", newline="") as arq:
            escritor = csv.writer(arq, delimiter=";")
            if novo:
                escritor.writerow(["data_hora", "modo", "linha", "processo", "cartao",
                                   "valor", "centro_custo", "situacao", "detalhe"])
            for linha, situacao, detalhe in resultados:
                escritor.writerow([carimbo, "SIMULACAO" if simulacao else "REAL",
                                   linha.numero, linha.processo, linha.cartao, linha.valor,
                                   linha.centro_custo, situacao, detalhe])
        if mostrar:
            print(f"  {ico('salvo')}  Log: {caminho}")
    except OSError as erro:
        msg_alerta(f"Não consegui gravar o log: {erro}")


def executar_carga_limite(cfg):
    """Automação 2: carga de limite do cartão corporativo + saldos antes/depois."""
    linhas = ler_linhas_carga(cfg)
    if not linhas:
        msg_alerta(f"Nenhuma linha com cartão (coluna C) a partir da linha "
                   f"{cfg.linha_inicial}.")
        return

    ja_feitas = [l for l in linhas if linha_concluida(l.status)]
    if ja_feitas:
        msg_dica(f"{len(ja_feitas)} linha(s) já concluídas na coluna F serão puladas "
                 f"(ok / carregado / verificar / representante).")
    refazer = [l for l in linhas if l.status and not linha_concluida(l.status)]
    if refazer:
        msg_dica(f"{len(refazer)} linha(s) com erro ou simulação anterior serão refeitas.")
    linhas = [l for l in linhas if not linha_concluida(l.status)]
    invalidas = [l for l in linhas if l.problema]
    if invalidas:
        marcador_invalidas = MarcadorPlanilha(cfg.caminho_planilha, cfg.aba_planilha,
                                              coluna=COLUNA_CARGA_STATUS,
                                              excel_visivel=cfg.modo_visivel)
        for linha in invalidas:
            msg_erro(f"Linha {linha.numero} ignorada: {linha.problema}")
            marcador_invalidas.marcar(linha.numero, marca_de_erro(linha.problema))
    linhas = [l for l in linhas if not l.problema]
    if not linhas:
        msg_ok("Nada a carregar.")
        return

    linhas = resolver_repetidos(linhas)
    if not linhas:
        msg_alerta("Cancelado.")
        return

    if not escolher_programa_carga():
        msg_alerta("Cancelado.")
        return
    simulacao = escolher_modo_carga()
    if simulacao is None:
        msg_alerta("Cancelado.")
        return

    total = sum(l.valor for l in linhas)
    print()
    cabecalho(f"{'SIMULAÇÃO' if simulacao else 'CARGA REAL'}  ·  {len(linhas)} cartão(ões)",
              "banco", f"{cfg.rotulo_planilha()}  ·  total R$ {formatar_milhar(total)}")
    for linha in linhas:
        print(f"    {linha.resumo()}")
    separador()
    filtros = PROGRAMAS_CARGA[PROGRAMA_CARGA]["filtros"]
    print(f"    Programa: {PROGRAMA_CARGA} ({filtros} filtro{'s' if filtros > 1 else ''} "
          f"de carregamento)")
    print(f"    Regra: novo limite = coluna D  ·  diário/semanal/mensal = "
          f"limite disponível (p/ baixo) + coluna D")
    print(f"    Total: {C.NEGRITO}R$ {formatar_milhar(total)}{C.RESET}")
    if simulacao:
        resposta = perguntar(f"\n  {C.NEGRITO}Enter para simular, 'c' para cancelar{C.RESET} ")
        if foi_cancelado(resposta) or resposta.lower().startswith("c"):
            return
    else:
        resposta = perguntar(f"\n  {C.NEGRITO}{C.VERMELHO}Digite {PALAVRA_CONFIRMACAO} para "
                             f"efetivar as cargas{C.RESET} ")
        if resposta.strip().upper() != PALAVRA_CONFIRMACAO:
            msg_alerta("Não confirmado. Nada foi feito.")
            return

    marcador = MarcadorPlanilha(cfg.caminho_planilha, cfg.aba_planilha,
                                coluna=COLUNA_CARGA_STATUS, excel_visivel=cfg.modo_visivel)
    if not simulacao and not conferir_gravacao_antes_de_comecar(marcador, linhas[0].numero):
        msg_erro("Sem gravar a coluna F, uma nova rodada carregaria de novo os mesmos "
                 "cartões. Carga real cancelada.")
        return

    os.makedirs(PASTA_SALDOS, exist_ok=True)
    resultados = []
    inicio = time.time()
    gravador = GravadorColunaF(marcador)
    try:
        print(f"  {ico('chrome')}  Conectando ao Chrome na porta {PORTA_DEPURACAO}...")
        with sync_playwright() as playwright:
            browser = conectar_navegador(playwright)
            page = obter_pagina_bb(browser, cfg)
            definir_rota_cartao("orgao")
            preparar_sessao_orgao(page)

            for indice, linha in enumerate(linhas, start=1):
                if parada_pedida():
                    break
                print()
                separador()
                print(f"  {ico('banco')}  {C.NEGRITO}[{indice}/{len(linhas)}]{C.RESET} "
                      f"{linha.resumo()}")
                separador()
                manter_sessao_viva(page, forcar=True)
                try:
                    situacao, detalhe, _arquivos = processar_carga(page, linha, simulacao,
                                                                   gravador)
                except CargaIncerta as erro:
                    situacao, detalhe = "VERIFICAR", str(erro)
                except FiltrosDesabilitados as erro:
                    situacao, detalhe = "FILTROS", str(erro)
                    linha.marca_filtros = erro.marca
                except CartaoBloqueado as erro:
                    situacao, detalhe = "REPRESENTANTE", erro.mensagem
                except ErroDoPortal as erro:
                    situacao, detalhe = "RECUSADO", erro.mensagem
                except Exception as erro:
                    situacao, detalhe = "FALHA", str(erro).splitlines()[0]
                if situacao in ("RECUSADO", "FALHA") and getattr(linha, "clicou_confirmar", False):
                    situacao = "VERIFICAR"
                resultados.append((linha, situacao, detalhe))
                # Na hora, não no fim do lote: se o app for fechado no meio,
                # o que já aconteceu continua registrado.
                registrar_log_carga([(linha, situacao, detalhe)], simulacao, mostrar=False)

                # Status de TODA linha na coluna F (OK/CARREGADO já foram
                # gravados dentro de processar_carga, logo após o Confirmar).
                marca = {
                    "VERIFICAR": f"{MARCA_CARGA_VERIFICAR}: {' '.join(detalhe.split())}"[:120],
                    "REPRESENTANTE": MARCA_CARGA_REPRESENTANTE,
                    "FILTROS": getattr(linha, "marca_filtros", MARCA_CARGA_FILTROS),
                    "SIMULADO": MARCA_CARGA_SIMULADO,
                    "RECUSADO": marca_de_recusa(detalhe),
                    "FALHA": marca_de_erro(detalhe),
                }.get(situacao)
                if marca:
                    gravador.depois(linha.numero, marca)

                cor = {"OK": C.VERDE, "SIMULADO": C.AZUL}.get(situacao, C.AMARELO)
                print(f"  {cor}{situacao}{C.RESET}  {detalhe}")

                if situacao == "VERIFICAR":
                    msg_erro(f"Linha {linha.numero}: NÃO sei se a carga entrou. "
                             f"Confira no portal antes de seguir.")
                    resposta = perguntar(f"  {C.NEGRITO}Enter para continuar o lote, "
                                         f"'p' para parar{C.RESET} ")
                    if foi_cancelado(resposta) or resposta.lower().startswith("p"):
                        break

                if indice < len(linhas):
                    proximo_cartao_rapido(page)
    finally:
        gravador.terminar()
        fechar_marcacoes(marcador)
        print()
        cabecalho("RESUMO DA CARGA", "salvo")
        for linha, situacao, detalhe in resultados:
            print(f"  {situacao:<10} linha {linha.numero:<5} {linha.cartao}  {detalhe[:90]}")
        separador()
        contagem = {}
        for _l, situacao, _d in resultados:
            contagem[situacao] = contagem.get(situacao, 0) + 1
        print("  " + "  ·  ".join(f"{k}: {v}" for k, v in contagem.items()))
        carregado = sum(l.valor for l, s, _d in resultados if s in ("OK", "CARREGADO"))
        print(f"  Carregado de fato: R$ {formatar_milhar(carregado)}  ·  "
              f"{(time.time() - inicio) / 60:.1f} min")
        print(f"  {ico('pasta')}  {PASTA_SALDOS}")
        print(f"  {ico('salvo')}  Log: {os.path.join(PASTA_SALDOS, '_cargas.csv')}")


# ============================================================================
# AUTOMAÇÃO 3 — ANEXAR OS SALDOS NO SEI
# ----------------------------------------------------------------------------
# Para cada processo (coluna B) cuja carga foi feita (coluna F = "ok" ou
# "carregado..."), inclui no SEI dois Documentos Externos, a partir dos PDFs
# de saldos_carga/<processo>/:
#
#     Saldo Anterior - <centro de custo>
#     Novo Saldo - <centro de custo>
#
# Cada um: Incluir Documento -> Externo; Tipo "Anexo"; data de hoje; Nome na
# Árvore = nome do arquivo; Nato-digital; Público; PDF anexado; Salvar.
# O resultado vai para a coluna G.
#
# Abertura do processo (Pesquisa Rápida, tela de resultado, Reabrir
# Processo) e a busca de elementos entre os iframes do SEI vêm do projeto
# LBA (etapa_listar_baixar.abrir_processo_sei / etapa_sei2).
#
# Duplicidade: assim que QUALQUER documento de um processo é salvo, um erro
# depois disso vira "sei verificar" (pulado nas próximas rodadas), nunca
# "erro" — senão uma nova rodada incluiria o mesmo documento duas vezes.
# ============================================================================

COLUNA_SEI_STATUS = 7   # G
URL_SEI = ("https://sei.sistemas.ro.gov.br/sip/login.php"
           "?sigla_orgao_sistema=RO&sigla_sistema=SEI")
DOMINIO_SEI = "sei.sistemas.ro.gov.br"
TIPO_DOCUMENTO_SEI = "Anexo"
LIMITE_NOME_ARVORE = 50   # maxlength do #txtNomeArvore
TIMEOUT_SEI = 30          # segundos

MARCA_SEI_OK = "sei ok"
MARCA_SEI_CONFERIR = "sei conferir"

# Reprocessar é seguro: antes de incluir cada documento, a árvore do processo
# é lida e o que já estiver lá é pulado. Só não se reprocessa o que foi salvo
# mas NÃO apareceu na árvore ("sei conferir") — ali a leitura da árvore não
# serve de garantia contra duplicar.

DOCUMENTOS_SEI = ("Saldo Anterior", "Novo Saldo")   # nesta ordem no processo


class ErroSei(Exception):
    pass


def normalizar_processo(texto):
    """'0029001868202656' ou '0029.001868/2026-56' -> '0029.001868/2026-56' (ou None)."""
    digitos = so_digitos(texto)
    if len(digitos) != 16:
        return None
    return f"{digitos[:4]}.{digitos[4:10]}/{digitos[10:14]}-{digitos[14:]}"


class LinhaSei:

    def __init__(self, numero, processo, status_carga, status_sei):
        self.numero = numero
        self.processo_bruto = texto_celula(processo)
        self.processo = normalizar_processo(self.processo_bruto)
        self.status_carga = texto_celula(status_carga).strip().lower()
        self.status_sei = texto_celula(status_sei).strip().lower()

    @property
    def carregada(self):
        return self.status_carga.startswith((MARCA_CARGA_OK, "carregado"))

    def concluida_no_sei(self, parcelas):
        s = self.status_sei
        if s.startswith((f"{MARCA_SEI_OK} - parcela", MARCA_SEI_CONFERIR)):
            return True
        # "sei ok" simples só vale para processo de UMA linha. Em processo com
        # 2+ parcelas ele é da versão antiga, que anexava só um par: refaz.
        return s.startswith(MARCA_SEI_OK) and parcelas == 1

    @property
    def pasta(self):
        # Mesmo nome de pasta que LinhaCarga.pasta usa ao salvar os saldos.
        nome = _sanitizar_nome(self.processo_bruto.replace("/", "-"))
        return os.path.join(PASTA_SALDOS, nome or f"linha_{self.numero}")


def ler_linhas_sei(cfg):
    brutos = ler_bruto_planilha(cfg, COLUNA_SEI_STATUS, COLUNA_CARGA_PROCESSO)
    linhas = []
    for deslocamento, valores in enumerate(brutos):
        if not texto_celula(valores[COLUNA_CARGA_PROCESSO - 1]):
            continue
        linhas.append(LinhaSei(cfg.linha_inicial + deslocamento,
                               valores[COLUNA_CARGA_PROCESSO - 1],
                               valores[COLUNA_CARGA_STATUS - 1],
                               valores[COLUNA_SEI_STATUS - 1]))
    return linhas


def pdfs_com_prefixo(pasta, prefixo):
    nomes = os.listdir(pasta) if os.path.isdir(pasta) else []
    caminhos = [os.path.join(pasta, n) for n in nomes
                if n.lower().startswith(prefixo.lower() + " - ") and n.lower().endswith(".pdf")]
    return sorted(caminhos, key=os.path.getmtime)


def pares_de_saldos(pasta):
    """
    [(saldo_anterior, novo_saldo)] da pasta do processo, do mais antigo ao
    mais recente — um par por carga REAL.

    "Novo Saldo" só existe depois de uma carga confirmada; cada um é casado
    com o "Saldo Anterior" mais recente ANTES dele. As cópias '(2)', '(3)'
    de Saldo Anterior deixadas pelas simulações ficam de fora sozinhas.
    """
    anteriores = pdfs_com_prefixo(pasta, DOCUMENTOS_SEI[0])
    pares = []
    for novo in pdfs_com_prefixo(pasta, DOCUMENTOS_SEI[1]):
        limite = os.path.getmtime(novo) + 2
        antes = [a for a in anteriores if os.path.getmtime(a) <= limite]
        pares.append((antes[-1] if antes else None, novo))
    return pares


def centro_custo_do_arquivo(caminho_pdf):
    nome = os.path.splitext(os.path.basename(caminho_pdf))[0]
    nome = re.sub(r"\s*\(\d+\)$", "", nome)
    return nome.split(" - ", 1)[1] if " - " in nome else nome


def nomes_na_arvore(caminho_pdf, prefixo, parcela, parcelas):
    """(nome, alternativos). Com 2+ parcelas o nome leva '(Nª parcela)'; a
    ÚLTIMA parcela também aceita o nome simples, que é como a versão antiga
    (que anexava só o par mais recente) a deixou no SEI."""
    cc = centro_custo_do_arquivo(caminho_pdf)
    simples = f"{prefixo} - {cc}"[:LIMITE_NOME_ARVORE].strip()
    if parcelas == 1:
        return simples, ()
    nome = f"{prefixo} ({parcela}ª parcela) - {cc}"[:LIMITE_NOME_ARVORE].strip()
    return nome, ((simples,) if parcela == parcelas else ())


# -- SEI: navegação ---------------------------------------------------------

def achar_no_sei(page, seletor, timeout=5.0, intervalo=0.15):
    """(frame, locator) do primeiro `seletor` visível na página ou em qualquer
    iframe — o SEI muda o mesmo botão de frame conforme a tela."""
    fim = time.time() + timeout
    while True:
        for alvo in [page] + list(page.frames):
            try:
                loc = alvo.locator(seletor).first
                if loc.count() > 0 and loc.is_visible():
                    return alvo, loc
            except PlaywrightError:
                continue
        if time.time() >= fim:
            return None, None
        page.wait_for_timeout(int(intervalo * 1000))


def obter_aba_sei(browser):
    for contexto in browser.contexts:
        for aba in contexto.pages:
            if DOMINIO_SEI in (aba.url or "").lower():
                aba.bring_to_front()
                return aba
    aba = browser.contexts[0].new_page()
    aba.goto(URL_SEI)
    return aba


def garantir_login_sei(page):
    while True:
        _frame, campo = achar_no_sei(page, "#txtPesquisaRapida", timeout=5)
        if campo is not None:
            return
        msg_alerta("O SEI não está logado nesta janela do Chrome (não achei a Pesquisa Rápida).")
        resposta = perguntar(f"  {C.NEGRITO}Faça login no SEI na aba aberta e tecle Enter "
                             f"(ou 'c' para cancelar){C.RESET} ")
        if foi_cancelado(resposta) or resposta.lower().startswith("c"):
            raise ErroDeUso("Anexo no SEI cancelado: sem login no SEI.")


def texto_da_arvore(page):
    arvore = page.frame(name="ifrArvore")
    if arvore is None:
        return ""
    try:
        return arvore.locator("body").inner_text(timeout=3000)
    except PlaywrightError:
        return ""


def abrir_processo_sei(page, processo):
    """Pesquisa Rápida -> (tela de resultado) -> árvore montada -> reabrir se arquivado."""
    if processo in texto_da_arvore(page):
        clicar_raiz_do_processo(page, processo)
    else:
        _frame, campo = achar_no_sei(page, "#txtPesquisaRapida", timeout=10)
        if campo is None:
            raise ErroSei("não achei a Pesquisa Rápida do SEI")
        campo.click()
        campo.fill(processo)
        campo.press("Enter")

        fim = time.time() + TIMEOUT_SEI
        while time.time() < fim:
            if processo in texto_da_arvore(page):
                break
            _f, link = achar_no_sei(page, f'a:has-text("{processo}")', timeout=0.5)
            if link is not None and page.frame(name="ifrArvore") is None:
                link.click()   # caiu na tela de resultado da pesquisa
            page.wait_for_timeout(300)
        else:
            raise ErroSei(f"o processo {processo} não abriu (confira o número e o acesso)")

    _f, reabrir = achar_no_sei(page, 'img[title="Reabrir Processo"]', timeout=2)
    if reabrir is not None:
        reabrir.click()
        msg_ok("Processo estava fechado na unidade: cliquei em 'Reabrir Processo'.")
        page.wait_for_timeout(1500)
    print(f"[OK] Processo {processo} aberto no SEI.")


def clicar_raiz_do_processo(page, processo):
    """Volta a tela de visualização para o processo (onde está 'Incluir Documento')."""
    arvore = page.frame(name="ifrArvore")
    if arvore is None:
        return
    try:
        link = arvore.locator(f'a:has-text("{processo}")').first
        if link.count() > 0:
            link.click()
            page.wait_for_timeout(800)
    except PlaywrightError:
        pass


def incluir_documento_externo(page, processo, caminho_pdf, nome, dialogos):
    """
    Inclui um Documento Externo com o PDF. Devolve True se o documento
    apareceu na árvore depois de salvar (False = salvou, mas não vi).
    Levanta ErroSei se o SEI recusar (antes de salvar nada).
    """
    # Clique em "Incluir Documento" com CONFIRMAÇÃO. Visto na rodada real: o
    # botão é achado, mas o clique cai enquanto o frame ainda está carregando
    # (logo depois de salvar o documento anterior ou de voltar à raiz) e se
    # perde — a lista de tipos nunca abre, e um clique à mão resolvia. Então:
    # espera o frame carregar, clica, confere se a lista abriu em poucos
    # segundos e, se não abriu, clica de novo.
    # :text-is = texto exato, com espaços normalizados (o link é " Externo").
    seletor_externo = "a.ancoraOpcao:text-is('Externo')"
    clicar_raiz_do_processo(page, processo)
    externo = None
    cliques = 0
    fim = time.time() + 60
    while time.time() < fim:
        _f, externo = achar_no_sei(page, seletor_externo, timeout=0)
        if externo is not None:
            break
        frame, incluir = achar_no_sei(page, 'img[title="Incluir Documento"]', timeout=5)
        if incluir is None:
            clicar_raiz_do_processo(page, processo)
            continue
        try:
            frame.wait_for_load_state("load", timeout=5000)
        except PlaywrightError:
            pass
        try:
            incluir.click(timeout=5000)
        except PlaywrightError:
            try:   # o <img> fica dentro do <a> que abre a lista
                incluir.evaluate("el => (el.closest('a') || el).click()")
            except PlaywrightError:
                pass
        cliques += 1
        _f, externo = achar_no_sei(page, seletor_externo, timeout=6)
        if externo is not None:
            break
        print(f"[AVISO] O clique em 'Incluir Documento' não abriu a lista ({cliques}); "
              f"clicando de novo...")
    if externo is None:
        raise ErroSei(f"a lista de tipos não abriu nem depois de {cliques} clique(s) "
                      f"em 'Incluir Documento'")
    externo.click()

    form, _serie = achar_no_sei(page, "#selSerie", timeout=TIMEOUT_SEI)
    if form is None:
        raise ErroSei("o formulário 'Registrar Documento Externo' não abriu")

    form.select_option("#selSerie", label=TIPO_DOCUMENTO_SEI)
    page.wait_for_timeout(400)   # trocarSerie() reajusta o formulário
    form.fill("#txtDataElaboracao", datetime.now().strftime("%d/%m/%Y"))
    form.fill("#txtNomeArvore", nome)
    form.locator('label.infraRadioLabel[for="optNato"]').click()
    form.locator('label.infraRadioLabel[for="optPublico"]').click()

    form.locator("#filArquivo").set_input_files(caminho_pdf)
    fim = time.time() + TIMEOUT_SEI
    while time.time() < fim:
        try:
            if form.locator("#tblAnexos tbody tr").count() >= 1:
                break
        except PlaywrightError:
            pass
        if dialogos:
            raise ErroSei(f"o SEI recusou o arquivo: {dialogos.pop()}")
        page.wait_for_timeout(300)
    else:
        raise ErroSei("o upload do PDF não terminou (a Lista de Anexos continuou vazia)")
    print(f"[OK] Arquivo anexado ao formulário: {os.path.basename(caminho_pdf)}")

    dialogos.clear()
    form.locator("#btnSalvar").first.click()
    print(f"[..] Salvando '{nome}'...")

    fim = time.time() + TIMEOUT_SEI
    while time.time() < fim:
        if dialogos:
            raise ErroSei(f"o SEI não aceitou o formulário: {dialogos.pop()}")
        try:
            aberto = form.locator("#selSerie").count() > 0 and form.locator("#selSerie").is_visible()
        except PlaywrightError:
            aberto = False   # o frame navegou: o formulário saiu da tela
        if not aberto:
            break
        page.wait_for_timeout(300)
    else:
        raise ErroSei("depois do Salvar, o formulário continuou na tela")

    fim = time.time() + 15
    while time.time() < fim:
        if nome in texto_da_arvore(page):
            msg_ok(f"'{nome}' incluído no processo {processo}.")
            return True
        page.wait_for_timeout(500)
    msg_alerta(f"'{nome}' foi salvo, mas não o vi na árvore do processo. Confira.")
    return False


# -- lote -------------------------------------------------------------------

def registrar_log_sei(processo, linhas, situacao, detalhe):
    caminho = os.path.join(PASTA_SALDOS, "_sei.csv")
    novo = not os.path.exists(caminho)
    try:
        os.makedirs(PASTA_SALDOS, exist_ok=True)
        with open(caminho, "a", encoding="utf-8-sig", newline="") as arq:
            escritor = csv.writer(arq, delimiter=";")
            if novo:
                escritor.writerow(["data_hora", "processo", "linhas", "situacao", "detalhe"])
            escritor.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), processo,
                               " ".join(str(l.numero) for l in linhas), situacao, detalhe])
    except OSError as erro:
        msg_alerta(f"Não consegui gravar o log do SEI: {erro}")


def incluir_se_faltar(page, processo, caminho, nome, alternativos, dialogos):
    """'ja' se o documento já está na árvore; senão inclui: 'novo' ou 'nao_visto'."""
    arvore = texto_da_arvore(page)
    if nome in arvore or any(alt in arvore for alt in alternativos):
        print(f"[OK] Já está no processo, pulando: {nome}")
        return "ja"
    visto = incluir_documento_externo(page, processo, caminho, nome, dialogos)
    return "novo" if visto else "nao_visto"


def planejar_anexos_sei(linhas, gravador):
    """
    [(processo, [(linha, parcela, parcelas, (saldo_anterior, novo_saldo))])]
    e quantas linhas já estavam concluídas. Processo em 2+ linhas = 2+
    parcelas (cargas) = um par de saldos por linha, na ordem das linhas.
    """
    grupos = {}
    for linha in linhas:
        if linha.carregada:
            grupos.setdefault(linha.processo_bruto, []).append(linha)

    trabalho = []
    ja = 0
    for bruto, grupo in grupos.items():
        parcelas = len(grupo)
        pendentes = [l for l in grupo if not l.concluida_no_sei(parcelas)]
        ja += parcelas - len(pendentes)
        if not pendentes:
            continue
        processo = grupo[0].processo
        if processo is None:
            msg_erro(f"{bruto}: número de processo inválido.")
            for linha in pendentes:
                gravador.depois(linha.numero, "erro sei: processo inválido na coluna B")
            continue

        pares = pares_de_saldos(grupo[0].pasta)[-parcelas:]
        faltam = parcelas - len(pares)   # parcelas sem Novo Saldo: as primeiras
        itens = []
        for indice, linha in enumerate(grupo):
            if linha not in pendentes:
                continue
            parcela = indice + 1
            par = pares[indice - faltam] if indice >= faltam else None
            if par is None or par[0] is None:
                falta = "novo saldo" if par is None else "saldo anterior"
                msg_erro(f"{processo} linha {linha.numero}: falta o {falta} "
                         f"da parcela {parcela}/{parcelas} em {linha.pasta}.")
                gravador.depois(linha.numero,
                                f"erro sei: falta {falta} (parcela {parcela}/{parcelas})")
                continue
            itens.append((linha, parcela, parcelas, par))
        if itens:
            trabalho.append((processo, itens))
    return trabalho, ja


def executar_anexar_sei(cfg):
    """Automação 3: anexa os saldos (anterior e novo) de cada parcela no SEI."""
    linhas = ler_linhas_sei(cfg)
    marcador = MarcadorPlanilha(cfg.caminho_planilha, cfg.aba_planilha,
                                coluna=COLUNA_SEI_STATUS, excel_visivel=cfg.modo_visivel)
    gravador = GravadorColunaF(marcador, letra="G")

    print()
    cabecalho("ANEXAR SALDOS NO SEI", "pasta",
              f"{cfg.rotulo_planilha()}  ·  Externo / {TIPO_DOCUMENTO_SEI} / Nato-digital / Público")
    trabalho, ja = planejar_anexos_sei(linhas, gravador)
    for processo, itens in trabalho:
        print(f"    {processo}")
        for linha, parcela, total, par in itens:
            for prefixo, caminho in zip(DOCUMENTOS_SEI, par):
                nome, _alt = nomes_na_arvore(caminho, prefixo, parcela, total)
                print(f"        linha {linha.numero:<4} {nome}")

    if ja:
        msg_dica(f"{ja} linha(s) já concluída(s) no SEI (coluna G) foram puladas.")
    if not trabalho:
        gravador.terminar()
        fechar_marcacoes(marcador)
        msg_ok("Nada pendente de anexo no SEI.")
        return

    resposta = perguntar(f"\n  {C.NEGRITO}Enter para anexar em {len(trabalho)} processo(s) "
                         f"(o que já estiver na árvore é pulado), 'c' para cancelar{C.RESET} ")
    if foi_cancelado(resposta) or resposta.lower().startswith("c"):
        gravador.terminar()
        fechar_marcacoes(marcador)
        return

    resultados = []
    try:
        with sync_playwright() as playwright:
            browser = conectar_navegador(playwright)
            page = obter_aba_sei(browser)
            dialogos = []

            def ao_abrir_dialogo(dialogo):
                dialogos.append(" ".join((dialogo.message or "").split()))
                try:
                    dialogo.accept()
                except PlaywrightError:
                    pass

            page.on("dialog", ao_abrir_dialogo)
            garantir_login_sei(page)

            for indice, (processo, itens) in enumerate(trabalho, start=1):
                if parada_pedida():
                    break
                print()
                separador()
                print(f"  {ico('pasta')}  {C.NEGRITO}[{indice}/{len(trabalho)}]{C.RESET} {processo}")
                separador()
                try:
                    abrir_processo_sei(page, processo)
                except Exception as erro:
                    detalhe = str(erro).splitlines()[0]
                    msg_erro(f"{processo}: {detalhe}")
                    for linha, _p, _t, _par in itens:
                        gravador.depois(linha.numero, f"erro sei: {detalhe}"[:120])
                        registrar_log_sei(processo, [linha], "ERRO", detalhe)
                        resultados.append((processo, linha.numero, "ERRO", detalhe))
                    continue

                for linha, parcela, total, par in itens:
                    rotulo = f"parcela {parcela}/{total}" if total > 1 else ""
                    estados = []
                    try:
                        for prefixo, caminho in zip(DOCUMENTOS_SEI, par):
                            nome, alternativos = nomes_na_arvore(caminho, prefixo, parcela, total)
                            estados.append(incluir_se_faltar(page, processo, caminho, nome,
                                                             alternativos, dialogos))
                        if "nao_visto" in estados:
                            situacao, detalhe = "CONFERIR", "salvo, mas não apareceu na árvore"
                            marca = f"{MARCA_SEI_CONFERIR}: {detalhe}"
                        else:
                            novos = estados.count("novo")
                            situacao = "OK"
                            detalhe = (f"{novos} documento(s) incluído(s)"
                                       + (f", {2 - novos} já estava(m)" if novos < 2 else ""))
                            marca = f"{MARCA_SEI_OK} - {rotulo}" if rotulo else MARCA_SEI_OK
                    except Exception as erro:
                        detalhe = str(erro).splitlines()[0]
                        situacao, marca = "ERRO", f"erro sei: {detalhe}"[:120]
                        msg_erro(f"{processo} linha {linha.numero}: {detalhe}")
                    gravador.depois(linha.numero, marca)
                    registrar_log_sei(processo, [linha], situacao,
                                      f"{rotulo + ': ' if rotulo else ''}{detalhe}")
                    resultados.append((processo, linha.numero, situacao,
                                       f"{rotulo + ' · ' if rotulo else ''}{detalhe}"))
    finally:
        gravador.terminar()
        fechar_marcacoes(marcador)
        print()
        cabecalho("RESUMO DO SEI", "salvo")
        for processo, numero, situacao, detalhe in resultados:
            print(f"  {situacao:<9} linha {numero:<4} {processo}  {detalhe[:80]}")
        contagem = {}
        for _p, _n, situacao, _d in resultados:
            contagem[situacao] = contagem.get(situacao, 0) + 1
        if contagem:
            print("  " + "  ·  ".join(f"{k}: {v}" for k, v in contagem.items()))
        print(f"  {ico('salvo')}  Log: {os.path.join(PASTA_SALDOS, '_sei.csv')}")
        msg_dica("Confira no SEI a ordem dos documentos na árvore antes de tramitar.")


# ============================================================================
# AUTOMAÇÃO 4 — CARGA AVULSA (UM PROCESSO, SEM PLANILHA)
# ----------------------------------------------------------------------------
# Processo, cartão e valor digitados na hora. Mesmo fluxo e mesmas travas da
# carga pela planilha (processar_carga): simulação/real, Saldo Anterior,
# filtros, conferência saldo + carga, Confirmar, Novo Saldo.
#
# Sem planilha não há coluna F para barrar carga repetida: no lugar dela o
# histórico _cargas.csv é consultado, e um cartão que já teve carga REAL
# exige digitar REPETIR. No fim de uma carga real, oferece anexar os dois
# saldos no SEI na mesma hora.
# ============================================================================

class MarcadorNulo:
    """Sem planilha: as marcas vão só para o registro e o _cargas.csv."""
    pendentes = []
    gravadas = 0
    ultimo_erro_com = ""

    def marcar(self, _numero_linha, _valor, **_kw):
        return True

    def liberar(self):
        return 0, []


def perguntar_campo(rotulo, converter):
    """Pergunta até vir um valor válido. None = cancelado."""
    while True:
        resposta = perguntar(f"  {C.NEGRITO}{rotulo}{C.RESET} ")
        if foi_cancelado(resposta) or resposta.strip().lower() in ("c", "cancelar"):
            return None
        try:
            return converter(resposta)
        except ValueError as erro:
            msg_alerta(str(erro))


def _processo_digitado(texto):
    processo = normalizar_processo(texto)
    if not processo:
        raise ValueError("Processo inválido: são 16 dígitos (ex.: 0029.001868/2026-56).")
    return processo


def _cartao_digitado(texto):
    digitos = so_digitos(texto)
    if len(digitos) != 16:
        raise ValueError(f"Cartão com {len(digitos)} dígitos; são 16.")
    return formatar_numero_cartao(digitos)


def cargas_reais_anteriores(cartao):
    """Linhas do _cargas.csv com carga REAL feita (ou incerta) neste cartão."""
    caminho = os.path.join(PASTA_SALDOS, "_cargas.csv")
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, encoding="utf-8-sig", newline="") as arq:
            registros = list(csv.DictReader(arq, delimiter=";"))
    except (OSError, csv.Error):
        return []
    alvo = so_digitos(cartao)
    return [r for r in registros
            if so_digitos(r.get("cartao")) == alvo and r.get("modo") == "REAL"
            and r.get("situacao") in ("OK", "CARREGADO", "VERIFICAR")]


def anexar_ultimo_par_no_sei(browser, processo, pasta):
    """Inclui no SEI o par de saldos mais recente da pasta do processo."""
    pares = pares_de_saldos(pasta)
    if not pares or pares[-1][0] is None:
        msg_erro("Não achei o par Saldo Anterior / Novo Saldo desta carga na pasta.")
        return
    parcela = len(pares)   # 2ª carga do mesmo processo = "(2ª parcela)"
    page = obter_aba_sei(browser)
    dialogos = []

    def ao_abrir_dialogo(dialogo):
        dialogos.append(" ".join((dialogo.message or "").split()))
        try:
            dialogo.accept()
        except PlaywrightError:
            pass

    page.on("dialog", ao_abrir_dialogo)
    garantir_login_sei(page)
    abrir_processo_sei(page, processo)
    for prefixo, caminho in zip(DOCUMENTOS_SEI, pares[-1]):
        nome, alternativos = nomes_na_arvore(caminho, prefixo, parcela, parcela)
        if parcela > 1:
            alternativos = ()   # o nome simples é da 1ª carga, não desta
        incluir_se_faltar(page, processo, caminho, nome, alternativos, dialogos)
    msg_ok(f"Saldos anexados no processo {processo}.")


def executar_carga_avulsa(cfg):
    """Automação 4: carga de UM processo, sem planilha."""
    print()
    cabecalho("CARGA AVULSA", "banco", "um processo, sem planilha  ·  'c' cancela")
    print()
    processo = perguntar_campo("Processo (ex.: 0029.001868/2026-56):", _processo_digitado)
    if processo is None:
        return
    cartao = perguntar_campo("Número do cartão (16 dígitos):", _cartao_digitado)
    if cartao is None:
        return
    valor = perguntar_campo("Valor da carga (inteiro, ex.: 20250):", valor_inteiro)
    if valor is None:
        return

    linha = LinhaCarga("avulsa", processo, cartao, valor, "")
    if linha.problema:
        msg_erro(f"Não dá para carregar: {linha.problema}")
        return

    anteriores = cargas_reais_anteriores(cartao)
    if anteriores:
        print()
        msg_alerta(f"Este cartão já tem {len(anteriores)} carga(s) REAL(is) registrada(s):")
        for r in anteriores[-5:]:
            print(f"       {r.get('data_hora')}  ·  processo {r.get('processo')}  ·  "
                  f"R$ {formatar_milhar(int(float(r.get('valor') or 0)))}  ·  {r.get('situacao')}")
        confirma = perguntar(f"  {C.NEGRITO}Se é mesmo uma NOVA parcela, digite REPETIR "
                             f"(qualquer outra coisa cancela){C.RESET} ")
        if confirma.strip().upper() != "REPETIR":
            msg_alerta("Cancelado. Nada foi feito.")
            return

    if not escolher_programa_carga():
        msg_alerta("Cancelado.")
        return
    simulacao = escolher_modo_carga()
    if simulacao is None:
        msg_alerta("Cancelado.")
        return

    filtros = PROGRAMAS_CARGA[PROGRAMA_CARGA]["filtros"]
    print()
    cabecalho("SIMULAÇÃO" if simulacao else "CARGA REAL", "banco", "carga avulsa")
    print(f"    Processo:  {processo}")
    print(f"    Cartão:    {cartao}")
    print(f"    Valor:     {C.NEGRITO}R$ {formatar_milhar(valor)}{C.RESET}")
    print(f"    Programa:  {PROGRAMA_CARGA} ({filtros} filtro{'s' if filtros > 1 else ''})")
    print(f"    Regra: novo limite = valor  ·  diário/semanal/mensal = "
          f"limite disponível (p/ baixo) + valor")
    if simulacao:
        resposta = perguntar(f"\n  {C.NEGRITO}Enter para simular, 'c' para cancelar{C.RESET} ")
        if foi_cancelado(resposta) or resposta.lower().startswith("c"):
            return
    else:
        resposta = perguntar(f"\n  {C.NEGRITO}{C.VERMELHO}Digite {PALAVRA_CONFIRMACAO} para "
                             f"efetivar a carga{C.RESET} ")
        if resposta.strip().upper() != PALAVRA_CONFIRMACAO:
            msg_alerta("Não confirmado. Nada foi feito.")
            return

    gravador = GravadorColunaF(MarcadorNulo())
    situacao, detalhe = "FALHA", ""
    try:
        with sync_playwright() as playwright:
            browser = conectar_navegador(playwright)
            page = obter_pagina_bb(browser, cfg)
            definir_rota_cartao("orgao")
            preparar_sessao_orgao(page)
            manter_sessao_viva(page, forcar=True)
            try:
                situacao, detalhe, _arquivos = processar_carga(page, linha, simulacao, gravador)
            except CargaIncerta as erro:
                situacao, detalhe = "VERIFICAR", str(erro)
            except FiltrosDesabilitados as erro:
                situacao, detalhe = "FILTROS", f"{erro} — habilite os filtros no BB"
            except CartaoBloqueado as erro:
                situacao, detalhe = "REPRESENTANTE", erro.mensagem
            except ErroDoPortal as erro:
                situacao, detalhe = "RECUSADO", marca_de_recusa(erro.mensagem)
            except Exception as erro:
                situacao, detalhe = "FALHA", str(erro).splitlines()[0]
            if situacao in ("RECUSADO", "FALHA") and getattr(linha, "clicou_confirmar", False):
                situacao = "VERIFICAR"
            registrar_log_carga([(linha, situacao, detalhe)], simulacao, mostrar=False)

            print()
            cor = {"OK": C.VERDE, "SIMULADO": C.AZUL}.get(situacao, C.AMARELO)
            print(f"  {cor}{situacao}{C.RESET}  {detalhe}")
            print(f"  {ico('pasta')}  {linha.pasta}")
            if situacao == "VERIFICAR":
                msg_erro("NÃO sei se a carga entrou. Confira no portal antes de repetir.")

            if situacao == "OK" and not simulacao:
                resposta = perguntar(f"\n  {C.NEGRITO}Anexar os dois saldos no SEI agora? "
                                     f"(s/N){C.RESET} ")
                if resposta.strip().lower() in ("s", "sim"):
                    try:
                        anexar_ultimo_par_no_sei(browser, processo, linha.pasta)
                    except Exception as erro:
                        msg_erro(f"Anexo no SEI não concluído: {str(erro).splitlines()[0]}")
                        msg_dica("Confira a árvore do processo; rodando de novo, o que já "
                                 "estiver lá é pulado.")
    finally:
        gravador.terminar()
        print(f"  {ico('salvo')}  Log: {os.path.join(PASTA_SALDOS, '_cargas.csv')}")


executar_carga_avulsa.sem_planilha = True


# ============================================================================
# REGISTRO DE AUTOMAÇÕES
# ----------------------------------------------------------------------------
# Para adicionar uma automação nova: escreva a função (recebendo `cfg`) e
# acrescente uma linha aqui. O menu se ajusta sozinho.
# ============================================================================

AUTOMACOES = [
    ("Carregamento Pelo Portador", executar_carregamento_portador),
    ("Carga de Limite (Cartão Corporativo)", executar_carga_limite),
    ("Anexar Saldos no SEI", executar_anexar_sei),
    ("Carga Avulsa (1 processo, sem planilha)", executar_carga_avulsa),
]


# ============================================================================
# MENUS
# ============================================================================

def menu_escolher_planilha(cfg):
    limpar_tela()
    cabecalho("ESCOLHER PLANILHA", "planilha",
              "de onde saem os cartões (coluna D) e o nome das pastas (A, B, E)")
    print()
    msg_dica("Cole o caminho completo do arquivo (.xlsx, .xlsm ou .csv).")
    msg_dica("No Explorer: Shift + botão direito no arquivo > 'Copiar como caminho'.")
    if cfg.caminho_planilha:
        print(f"\n  {ico('pasta')}  {C.FRACO}Atual:{C.RESET} {cfg.caminho_planilha}")
    print(f"\n  {C.FRACO}Enter em branco cancela e volta.{C.RESET}")

    resposta = perguntar(f"\n  {C.NEGRITO}Caminho {ico('seta')}{C.RESET} ")
    if foi_cancelado(resposta) or not resposta:
        return

    # "Copiar como caminho" do Windows entrega o caminho entre aspas.
    caminho = resposta.strip().strip('"').strip("'")
    caminho = os.path.expandvars(os.path.expanduser(caminho))

    if not os.path.exists(caminho):
        print()
        msg_erro(f"Arquivo não encontrado: {caminho}")
        pausar()
        return
    if not caminho.lower().endswith((".xlsx", ".xlsm", ".xltx", ".csv")):
        print()
        msg_erro("Formato não suportado. Use .xlsx, .xlsm ou .csv.")
        pausar()
        return

    # Escolha da aba, quando houver mais de uma.
    aba_escolhida = ""
    try:
        abas = listar_abas(caminho)
    except Exception as erro:
        print()
        msg_erro(f"Não consegui abrir a planilha: {erro}")
        pausar()
        return

    if len(abas) == 1:
        aba_escolhida = abas[0]
    elif len(abas) > 1:
        print(f"\n  {ico('planilha')}  {C.NEGRITO}Abas encontradas:{C.RESET}")
        for i, nome in enumerate(abas, start=1):
            print(f"      {C.AMARELO}[{i}]{C.RESET}  {nome}")
        escolha = perguntar(f"\n  Qual aba? (1-{len(abas)}, Enter = a primeira) "
                            f"{ico('seta')} ")
        if foi_cancelado(escolha):
            return
        if escolha.isdigit() and 1 <= int(escolha) <= len(abas):
            aba_escolhida = abas[int(escolha) - 1]
        else:
            aba_escolhida = abas[0]

    cfg.caminho_planilha = caminho
    cfg.aba_planilha = aba_escolhida
    cfg.salvar()

    print()
    msg_ok(f"Planilha definida: {cfg.rotulo_planilha()}")
    msg_dica(f"Leitura a partir da linha {cfg.linha_inicial}.")
    espiar_planilha(caminho, aba_escolhida, cfg.linha_inicial)
    pausar()


def menu_linha_inicial(cfg):
    limpar_tela()
    cabecalho("LINHA INICIAL DE LEITURA", "linha",
              "número real da linha do Excel onde os dados começam")
    print()
    msg_dica("Como a linha 1 é cabeçalho, normalmente é 2.")
    print(f"\n  {ico('engrenagem')} {C.FRACO}Atual:{C.RESET} "
          f"{C.VERDE}{cfg.linha_inicial}{C.RESET}")
    print(f"\n  {C.FRACO}Enter em branco cancela e volta.{C.RESET}")

    resposta = perguntar(f"\n  {C.NEGRITO}Linha inicial {ico('seta')}{C.RESET} ")
    if foi_cancelado(resposta) or not resposta:
        return
    if not resposta.isdigit() or int(resposta) < 1:
        print()
        msg_erro("Informe um número inteiro maior que zero.")
        pausar()
        return

    cfg.linha_inicial = int(resposta)
    cfg.salvar()
    print()
    msg_ok(f"Linha inicial definida: {cfg.linha_inicial}")

    if cfg.caminho_planilha and os.path.exists(cfg.caminho_planilha):
        espiar_planilha(cfg.caminho_planilha, cfg.aba_planilha, cfg.linha_inicial)
    pausar()


def menu_modo_execucao(cfg):
    while True:
        limpar_tela()
        cabecalho("MODO DE EXECUÇÃO", "engrenagem",
                  f"atualmente em {cfg.rotulo_modo()}")
        print()

        item_menu("1", "olho", f"{C.NEGRITO}VISÍVEL{C.RESET}  (padrão)")
        print(f"        {C.FRACO}Fluxo completo de impressão: clica no ícone, opera a")
        print(f"        visualização do Chrome e salva pelo explorador de arquivos.")
        print(f"        Traz a janela pro primeiro plano — evite mexer no PC.{C.RESET}")
        print()
        item_menu("2", "fantasma", f"{C.NEGRITO}INVISÍVEL{C.RESET}")
        print(f"        {C.FRACO}Não mexe no foco e não abre diálogo nenhum: o PDF é")
        print(f"        gerado direto pelo Chrome. Você continua usando o micro.{C.RESET}")
        print()
        item_menu("3", "sair", "Voltar")

        escolha = prompt_opcao()
        if foi_cancelado(escolha) or escolha == "3":
            return
        if escolha == "1":
            cfg.modo_visivel = True
            cfg.salvar()
            print()
            msg_ok("Modo VISÍVEL.")
            pausar()
            return
        if escolha == "2":
            cfg.modo_visivel = False
            cfg.salvar()
            print()
            msg_ok("Modo INVISÍVEL — pode usar o computador enquanto roda.")
            pausar()
            return
        print()
        msg_alerta("Opção inválida.")
        time.sleep(0.8)


def tem_pywin32():
    try:
        import win32com.client  # noqa: F401
        import pythoncom        # noqa: F401
        return True
    except Exception:
        return False


def localizar_excel():
    """Caminho do excel.exe, para conseguir abrir em modo somente leitura."""
    if os.name != "nt":
        return None
    try:
        import winreg
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                chave = winreg.OpenKey(
                    raiz, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\excel.exe")
                valor, _ = winreg.QueryValueEx(chave, None)
                winreg.CloseKey(chave)
                if valor and os.path.exists(valor):
                    return valor
            except OSError:
                continue
    except Exception:
        pass
    return shutil.which("excel")


def abrir_planilha_no_excel(cfg):
    """
    Abre a planilha para você acompanhar — só no modo VISÍVEL.

    Aqui mora a raiz do problema antigo: era ESTE atalho que criava a trava
    que depois impedia a gravação da coluna J. A escolha de como abrir agora
    depende de conseguirmos ou não escrever pelo Excel:

      * com pywin32 -> abre normal. A gravação passa a ser feita dentro da
        pasta de trabalho viva, e você vê o "ok" surgir na coluna J em tempo
        real, sem trava nenhuma atrapalhar.

      * sem pywin32 -> abre em SOMENTE LEITURA (excel.exe /r). Nesse modo o
        Excel não segura o arquivo para escrita, então o openpyxl continua
        gravando direto. A tela fica com os dados do momento da abertura;
        basta reabrir no fim para ver a coluna J preenchida.
    """
    if not cfg.modo_visivel:
        return

    caminho = cfg.caminho_planilha
    nome = os.path.basename(caminho)

    if tem_pywin32():
        try:
            if hasattr(os, "startfile"):
                os.startfile(caminho)  # type: ignore[attr-defined]
                msg_ok(f"Planilha aberta: {nome}")
                msg_dica("A coluna J vai ser preenchida ao vivo, pelo próprio Excel.")
                return
        except Exception as erro:
            msg_alerta(f"Não consegui abrir a planilha: {erro}")
            return

    excel = localizar_excel()
    if excel and not caminho.lower().endswith(".csv"):
        try:
            subprocess.Popen([excel, "/r", os.path.abspath(caminho)],
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            msg_ok(f"Planilha aberta em somente leitura: {nome}")
            msg_dica("Somente leitura de propósito: assim o Excel não tranca o arquivo "
                     "e a coluna J pode ser gravada. Reabra no fim para ver as marcas.")
            return
        except Exception:
            pass

    # Chegar aqui significa: sem pywin32 (não dá pra gravar com o arquivo
    # aberto) e sem excel.exe localizado (não dá pra abrir só-leitura). Abrir
    # normalmente criaria a trava que impede a coluna J de ser gravada — e
    # essa trava seria obra NOSSA. Então não abrimos.
    msg_alerta(f"Não vou abrir '{nome}' agora, para não travar o arquivo.")
    msg_dica("Abrir a planilha aqui impediria a gravação da coluna J. Instale o "
             "pywin32 (pip install pywin32) para acompanhar ao vivo, ou abra a "
             "planilha você mesmo DEPOIS que a automação terminar.")


def menu_executar(cfg):
    pode, motivo = cfg.pronta_para_executar()
    if not pode:
        limpar_tela()
        cabecalho("EXECUTAR AUTOMAÇÃO", "play")
        print()
        msg_erro(motivo)
        pausar()
        return

    limpar_tela()
    cabecalho("PREPARANDO", "engrenagem", "planilha e navegador")
    print()

    abrir_planilha_no_excel(cfg)

    # "Chrome em debug em todos os casos": se a porta não estiver no ar, o
    # sistema abre o Chrome com a flag em vez de mandar você fazer isso à mão.
    try:
        if not garantir_chrome_em_debug(cfg):
            print()
            msg_erro("Sem o Chrome em modo depuração a automação não roda.")
            pausar()
            return
    except ErroDeUso as erro:
        print()
        msg_erro(str(erro))
        pausar()
        return

    time.sleep(0.6)

    while True:
        limpar_tela()
        cabecalho("EXECUTAR AUTOMAÇÃO", "play")
        print()
        print(f"  {ico('planilha')}  {C.FRACO}Planilha{C.RESET}  "
              f"{C.VERDE}{cfg.rotulo_planilha()}{C.RESET}")
        print(f"  {ico('linha')}  {C.FRACO}Linha{C.RESET}     "
              f"{C.VERDE}a partir da {cfg.linha_inicial}{C.RESET}")
        print(f"  {ico('olho' if cfg.modo_visivel else 'fantasma')}  "
              f"{C.FRACO}Modo{C.RESET}      {C.VERDE}{cfg.rotulo_modo()}{C.RESET}")
        print()
        separador()
        for i, (nome, _funcao) in enumerate(AUTOMACOES, start=1):
            item_menu(str(i), "foguete", nome)
        item_menu(str(len(AUTOMACOES) + 1), "sair", "Voltar ao menu principal")
        separador()

        escolha = prompt_opcao()
        if foi_cancelado(escolha):
            return
        if not escolha:
            continue
        if escolha == str(len(AUTOMACOES) + 1):
            return
        if not escolha.isdigit() or not (1 <= int(escolha) <= len(AUTOMACOES)):
            print()
            msg_alerta("Opção inválida.")
            time.sleep(0.8)
            continue

        nome, funcao = AUTOMACOES[int(escolha) - 1]
        limpar_tela()
        cabecalho(nome, "foguete")

        try:
            funcao(cfg)
        except KeyboardInterrupt:
            print()
            msg_alerta("Execução interrompida por você (Ctrl+C).")
        except ErroDeUso as erro:
            # Situação prevista: mostra só o recado, sem assustar com traceback.
            print()
            msg_erro(str(erro))
        except Exception as erro:
            print()
            msg_erro(f"A automação parou: {erro}")
            print()
            traceback.print_exc()

        cfg.salvar()
        pausar("Pressione Enter para voltar")


def status_chrome():
    """Linha de status do menu principal (checagem barata, por socket)."""
    if porta_debug_aberta(timeout=0.25):
        return f"{ico('ok')}  {C.VERDE}conectado na porta {PORTA_DEPURACAO}{C.RESET}"
    return (f"{ico('alerta')} {C.AMARELO}fora do ar — será aberto ao executar"
            f"{C.RESET}")


def menu_principal(cfg):
    while True:
        limpar_tela()
        cabecalho("SISTEMA DE AUTOMAÇÕES BB", "banco",
                  "demonstrativos e carga de limite · v4.0")
        print()
        print(f"  {ico('chrome')}  {C.FRACO}Chrome (debug){C.RESET}   {status_chrome()}")
        print()
        separador()
        print()

        item_menu("1", "planilha", "Escolher planilha        ", cfg.rotulo_planilha())
        item_menu("2", "linha", "Escolher linha inicial   ", cfg.linha_inicial)
        item_menu("3", "olho" if cfg.modo_visivel else "fantasma",
                  "Execução visível/invisível", cfg.rotulo_modo())
        item_menu("4", "play", "Executar automação")
        item_menu("5", "sair", "Sair")

        print()
        separador()
        print(f"  {C.FRACO}Digite o número e pressione Enter{C.RESET}")

        escolha = prompt_opcao()

        if foi_cancelado(escolha) or escolha == "5":
            return
        if escolha == "1":
            menu_escolher_planilha(cfg)
        elif escolha == "2":
            menu_linha_inicial(cfg)
        elif escolha == "3":
            menu_modo_execucao(cfg)
        elif escolha == "4":
            menu_executar(cfg)
        elif escolha:
            print()
            msg_alerta("Opção inválida.")
            time.sleep(0.8)


def avisar_dependencias(cfg):
    """Aviso amigável antes de qualquer coisa quebrar no meio da execução."""
    faltando = []
    if openpyxl is None:
        faltando.append(("openpyxl", "ler planilhas .xlsx/.xlsm"))
    if cfg.modo_visivel and pyautogui is None:
        faltando.append(("pyautogui", "teclado no diálogo do Windows"))
    if cfg.modo_visivel and _ws_connect is None:
        faltando.append(("websocket-client", "operar o chrome://print"))
    if os.name == "nt" and not tem_pywin32():
        faltando.append(("pywin32", "gravar a coluna J com a planilha aberta"))
    if not faltando:
        return

    limpar_tela()
    cabecalho("BIBLIOTECAS AUSENTES", "alerta")
    print()
    for pacote, para_que in faltando:
        print(f"  {ico('erro')}  {C.VERMELHO}{pacote:<18}{C.RESET} "
              f"{C.FRACO}{para_que}{C.RESET}")
    print()
    print(f"  {C.NEGRITO}pip install "
          f"{' '.join(pacote for pacote, _ in faltando)}{C.RESET}")
    pausar("Pressione Enter para continuar mesmo assim")


def main():
    cfg = Configuracao.carregar()
    avisar_dependencias(cfg)
    try:
        menu_principal(cfg)
    finally:
        # "Todos os dados devem ser salvos após o sistema ser encerrado":
        # este finally cobre saída normal, Ctrl+C e exceção inesperada.
        cfg.salvar()
        print()
        print(f"  {ico('salvo')}  {C.FRACO}Configurações salvas em "
              f"{ARQUIVO_CONFIG}{C.RESET}")
        print(f"  {ico('banco')}  {C.NEGRITO}Até logo!{C.RESET}\n")


if __name__ == "__main__":
    main()