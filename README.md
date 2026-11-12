# Central de Automações — SEDUC

Automatiza trajetos manuais entre os sistemas do Governo de Rondônia
(SIGEF, SEI, DARE da SEFIN) e o portal do Banco do Brasil. São **seis
automações**, que rodam no mesmo Chrome e aparecem juntas numa janela só
(a *Central de Automações*):

| Automação          | O que faz                                                                 | Pasta                    |
|--------------------|---------------------------------------------------------------------------|--------------------------|
| **SIGEF → SEI**    | A partir de uma Ordem Bancária, baixa CE, NL, PP e OB do SIGEF e anexa no processo do SEI | `automacoes/sigef_sei/` |
| **Nota de Empenho** | A partir de uma NE, imprime a Nota de Empenho no SIGEF e anexa no processo do SEI | `automacoes/ne/` |
| **DARE**           | Gera o DARE avulso, salva o PDF e anexa no processo do SEI — digitado ou importado do Excel | `automacoes/dare/` |
| **Anexar Documentos** | Regularização de parcelas: **faz** a CE, a NL e a PP de cada lançamento e uma OB no SIGEF, baixa os relatórios e anexa no SEI (o antigo programa Anexar Documentos 1.6) | `automacoes/anexar/` |
| **Cadastro de Credores** | Cadastra o credor pessoa física e o domicílio bancário no SIGEF, digitado/colado ou da planilha do Excel (o antigo CadastroSIGEF 2.3) | `automacoes/cadastro/` |
| **Automações BB**  | Cargas de cartão no portal do Banco do Brasil e anexo dos saldos no SEI   | `automacoes/bb/`         |

Uma automação roda por vez: todas usam o mesmo Chrome, e a janela não
deixa duas começarem juntas. Na janela, cada automação tem a sua aba
(módulo) na barra lateral: **Anexar no SEI** (a OB), **Nota de Empenho**,
**DARE**, **Anexar Documentos**, **Cadastro de Credores** e **Banco do Brasil**.

---

## Como usar

### Programa instalado (recomendado)

Rode o `Instalar Automacao SIGEF-SEI <versão>.exe`. Instala sem senha de
administrador e sem Python, cria atalho no Menu Iniciar e abre a **janela
da Central**, com botões e campos no lugar da tela preta. O instalador é
gerado por `python instalador/construir.py` (ver
[`instalador/CONSTRUIR.md`](instalador/CONSTRUIR.md)).

Na máquina só precisa de **Google Chrome** e **Microsoft Edge WebView2**
(já vem no Windows 11 e no Windows 10 atualizado). O instalador mostra o
termo de uso (`LICENCA.txt`) e, na primeira abertura, a janela pede a
**ativação** — ver [Licença](#licença).

### Pelo código

Requer o **Google Chrome**. Há três portas de entrada, todas na raiz:

| Porta de entrada               | Para quem                                   | O que abre                    |
|--------------------------------|---------------------------------------------|-------------------------------|
| `AUTOMACAO SIGEF-SEI.exe`      | quem não usa terminal                       | prepara o Python e roda o `main.py` |
| `python app_janela.py`         | uso normal pelo código                      | a janela da Central (as seis automações) |
| `python main.py`               | tela preta, só SIGEF → SEI                  | menus no console              |

O `AUTOMACAO SIGEF-SEI.exe` procura o Python da máquina (e oferece baixar
uma cópia própria, sem instalar nada, se não houver), instala o que falta
do `requirements.txt` e chama o `main.py`. Da segunda vez em diante a
preparação é pulada. Detalhes em [`lancador/COMPILAR.md`](lancador/COMPILAR.md).
O `INICIAR.bat` também chama o `main.py`, mas exige o ambiente já pronto.

Com **Python 3.10+** já instalado:

```bash
python -m pip install -r requirements.txt
python app_janela.py      # a janela
python main.py            # ou a tela preta
```

Não é preciso `playwright install`: a automação se conecta ao Chrome da
máquina, em modo de depuração, com um perfil próprio em
`C:\ChromeAutomacao` (separado do Chrome do dia a dia).

> **Rode sempre a partir da pasta do programa.** Os arquivos das
> automações ficam em subpastas e são importados como pacote
> (`automacoes.sigef_sei...`); por isso o `main.py` e o `app_janela.py`
> continuam na raiz.

---

## Estrutura

```
AUTOMACAO SIGEF-SEI.exe   porta de entrada sem terminal: prepara o Python e roda o main.py
main.py                   porta de entrada da tela preta (SIGEF → SEI) e a constante VERSAO
app_janela.py             porta de entrada da janela: a Central com as automações
INICIAR.bat               atalho antigo para o main.py, sem preparar o ambiente
requirements.txt          dependências
LEIA-ME.txt               manual de uso para quem opera, sem jargão
LICENCA.txt               termo de uso que o instalador mostra ("Eu aceito")

automacoes/               AS AUTOMAÇÕES — uma pasta para cada
├── sigef_sei/            SIGEF → SEI
│   ├── preparar_navegador.py    passo 0: abre o Chrome da automação e espera o login
│   ├── etapa_listar_baixar.py   passo 1: baixa CE, NL, PP e OB do SIGEF  (baixar_documentos)
│   ├── etapa_sei2.py            passo 2: anexa no processo do SEI         (executar_sei2)
│   ├── lote.py                  várias OBs de uma vez, a partir de planilha/lista
│   ├── metricas.py              cronômetro de cada OB → metricas/metricas.csv
│   └── relatorio_gerencial.py   relatório HTML de tempo economizado
├── geral.py              o que vale para todas: config.json e o ano do SIGEF (url_sigef, ano_sigef)
├── painel.py             painel de resultados: OB, NE e DARE juntos (total, por mês, por pessoa)
├── ne/                   Nota de Empenho → SEI (usa as peças do sigef_sei/)
│   ├── etapa.py                 uma NE: imprime no SIGEF, PDF → PNG, anexa no SEI (processar_ne)
│   ├── lote.py                  várias NEs de uma vez, a partir de planilha/lista
│   ├── metricas.py              cronômetro de cada NE → metricas/metricas_ne.csv
│   ├── relatorio.py             relatório HTML das NEs
│   └── terminal.py              a NE sozinha, pela tela preta (python -m automacoes.ne.terminal)
├── anexar/               Anexar Documentos: CE, NL, PP e OB no SIGEF → SEI (o antigo programa, sem a janela PySide6)
│   ├── automacao/               as etapas (sei1, ce, nl, pp, ob, listar_baixar, sei2), o fluxo, o modo treino,
│   │                            as configurações e a conversa com a pessoa (interacao.py: os PEDIDOS)
│   ├── aplicativo/              núcleo (o executor noutro processo), métricas, estatísticas, estimativas à mão
│   ├── sistema/ambiente.py      acha o Chrome e diz o que falta no computador
│   └── central.py               o que muda na Central: ano do SIGEF e o Chrome da Central
├── cadastro/             Cadastro de Credores no SIGEF (o antigo CadastroSIGEF, sem a janela Tkinter)
│   ├── fluxos.py · automacao.py · navegador.py   o cadastro de cada pessoa (credor + domicílio)
│   ├── modelos.py · bancos.py · planilha.py      validação, bancos e o Excel aberto (COM)
│   ├── estatisticas.py · relatorio.py            sessões, tempo manual, relatório da pesquisa
│   └── terminal.py              o cadastro sozinho, pela tela preta (python -m automacoes.cadastro.terminal)
├── dare/                 DARE avulso → PDF → SEI (o antigo aplicativo DARE, sem a janela Tkinter)
│   ├── motor.py                 a rodada: para cada processo, gera os DAREs, junta os PDFs e anexa no SEI
│   ├── juntar.py                agrupa por processo e junta os PDFs (pypdf)
│   ├── dare.py · sei.py         os passos no site do DARE e no SEI
│   ├── planilha.py · excel_com.py · planilha_arquivo.py   importação do Excel (aberto ou .xlsx)
│   ├── limpeza.py · desempenho.py · armazenamento.py      PDFs, medições, histórico e pendentes
│   ├── terminal.py              o DARE sozinho, pelo terminal (python -m automacoes.dare.terminal)
│   └── GUIA_DE_USO.html · LICENCA.txt
└── bb/                   Automações BB (portal do Banco do Brasil)
    └── automacoes_bb.py

janela/                   A JANELA (usada pelo app_janela.py)
├── interface/            a página: index.html, estilo.css, app.js (OB), ne.js, central.js, modulos.js, dare.js, dare.css,
│                         anexar.js, cadastro.js, modulos2.css
├── modulos_janela.py     liga o BB à janela (configuração, thread, perguntas) e guarda o USO_DO_CHROME
├── modulo_ne.py          liga a NE à janela: uma porta só, api.ne(acao, dados)
├── modulo_dare.py        liga o DARE à janela: uma porta só, api.dare(acao, dados)
├── modulo_anexar.py      liga o Anexar Documentos à janela: api.anexar(acao, dados)
├── modulo_cadastro.py    liga o Cadastro de Credores à janela: api.cadastro(acao, dados)
├── modulo_geral.py       rodapé da barra lateral (ano do SIGEF, painel): api.geral(acao, dados)
└── licenca.py            ativação por chave: código da máquina + chave assinada

testes/
├── testes_divisao.py     testes offline da divisão de anexos (limite de 2 MB do SEI)
├── teste_janela_demo.py  a página da janela clicada como um usuário (OB e NE, um processo e lote)
├── geral/                ano do SIGEF e painel de resultados (offline)
├── ne/                   NE: ponte com a janela (offline) e cenários contra SIGEF/SEI simulados
└── dare/                 testes offline do DARE (validações, planilha, limpeza, motor, ponte com a janela)

instalador/               PyInstaller + Inno Setup: gera o Setup.exe
lancador/                 código-fonte (C) do AUTOMACAO SIGEF-SEI.exe + como recompilar
```

### Quem chama quem

```
                   ┌─ main.py ───────────┐
AUTOMACAO …exe ───▶│                     ├──▶ automacoes/sigef_sei/
INICIAR.bat ──────▶└─────────────────────┘        preparar_navegador → etapa_listar_baixar → etapa_sei2
                                                  lote · metricas · relatorio_gerencial
app_janela.py ──▶ janela/licenca  (sem licença válida: só a tela de ativação)
              ├─▶ janela/interface (HTML/JS)
              ├─▶ automacoes/sigef_sei/   (mesmas funções do main.py)
              ├─▶ janela/modulo_ne ───────▶ automacoes/ne/ (etapa, lote, relatorio)
              ├─▶ janela/modulo_geral ────▶ automacoes/geral (ano do SIGEF) · automacoes/painel
              ├─▶ janela/modulos_janela ──▶ automacoes/bb/automacoes_bb.py
              ├─▶ janela/modulo_dare ─────▶ automacoes/dare/ (motor, planilha, limpeza, desempenho)
              ├─▶ janela/modulo_anexar ───▶ automacoes/anexar/aplicativo/nucleo ──(outro processo)──▶ executor → fluxo
              └─▶ janela/modulo_cadastro ─▶ automacoes/cadastro/ (fluxos, planilha, estatisticas)
```

O SIGEF → SEI, a NE e o BB não importam a janela: continuam falando por `print()` e
`input()`. O `app_janela.py` troca o `sys.stdout` (cada linha vira uma
linha no registro da janela) e o `input()` (vira uma pergunta na tela) —
por isso o mesmo código serve à janela e à tela preta. O DARE já foi
escrito com eventos (o `motor` avisa "lote_inicio", "etapa", "lote_fim"…);
o `modulo_dare.py` só repassa esses eventos para a página.

### Onde ficam os dados

Nada de dado real fica na pasta do código.

| Automação    | Pasta de dados                                                              |
|--------------|-----------------------------------------------------------------------------|
| SIGEF → SEI  | `Documentos\Automacao SIGEF-SEI` (ou a pasta em `LBA_PASTA_DADOS`): pastas dos processos, `sessao_atual.json`, `lotes/`, `metricas/`, `relatorios/`, `registros/` |
| DARE         | `Documentos\DARE Automação` (ou `DARE_PASTA_DADOS`) — a mesma do aplicativo DARE: PDFs, histórico, lançamentos pendentes, logs, medições |
| BB           | `Documentos\Automacoes BB` (ou `BB_PASTA_DADOS`) — a mesma do programa BB antigo |
| Anexar Documentos | `Documentos\Anexar Documentos` (ou `ANEXAR_PASTA_DADOS`): configurações, sessão, relatórios; os JPGs em `Downloads\Anexar Documentos`. Na 1ª vez, copia o `dados\` do Anexar Documentos instalado |
| Cadastro de Credores | `~\.sigef-automacao` — a mesma do CadastroSIGEF: estatísticas (`.jsonl`), ajustes e registros |

Rodando `automacoes_bb.py` sozinho, sem a janela, ele grava a
configuração ao lado do próprio arquivo; o `.gitignore` já cobre esses
arquivos.

---

## Automação SIGEF → SEI

A partir do número de **uma Ordem Bancária (OB)**, baixa no SIGEF os
documentos vinculados a ela e os anexa ao processo indicado no SEI:

| Sigla | Documento                          | Quantidade      |
|-------|------------------------------------|-----------------|
| CE    | Despesa Certificada                | 1 por CE distinta |
| NL    | Nota de Lançamento                 | 1 por PP        |
| PP    | Preparação de Pagamento            | 1 por PP        |
| OB    | Ordem Bancária (de Regularização ou normal) | 1 por OB |

**Não gera, não cria, não altera e não exclui nenhum documento.** A CE,
a NL, a PP e a OB precisam já existir no SIGEF: o programa apenas
**consulta, baixa e anexa**. A conferência, a ordenação na árvore do
processo e a assinatura continuam sendo de quem opera — o programa avisa
isso na tela antes de devolver o controle.

### Fluxo

```
preparar_navegador  ──▶  etapa_listar_baixar  ──▶  etapa_sei2
    (uma vez)            └────── por Ordem Bancária ──────┘
```

O programa abre o Chrome da automação com as abas do SIGEF e do SEI (na
janela, também a do Banco do Brasil) e espera você entrar nas contas. Depois pede:

```
Processo do SEI    0029.001947/2026-67   (ou só: 0029001947202667)
Ordem Bancária     2026OB136475          (ou só: 136475)
Tipo da OB         Regularização  |  Ordem Bancária
```

A pontuação é opcional. Ao terminar, pergunta se há outra OB — e
recomeça no mesmo navegador, sem refazer o login.

O SIGEF é operado pela interface, com Playwright conectado ao Chrome via
CDP — não há API. Cada relatório é impresso em PDF e convertido em JPG
(PyMuPDF), o formato aceito pelo editor do SEI. Documentos maiores que o
limite de **2 MB** do SEI são divididos em partes (`etapa_sei2.py`,
coberto por `testes/testes_divisao.py`).

### Várias OBs de uma vez (modo lote)

Na janela, aba **Vários processos**: uma planilha (`.xlsx`/`.csv`) ou uma
lista colada, uma OB por linha (processo, OB e, opcionalmente, o tipo).
A ordem das colunas e o cabeçalho não importam; o programa mostra o que
entendeu de cada linha antes de começar e deixa de fora as inválidas e
as repetidas. Pela tela preta:

```bash
python main.py lista.xlsx
```

Os processos rodam em sequência, sem pausa para conferência — ela é
feita uma vez, no fim. Uma falha espera 30 s e tenta de novo, de onde
parou; se persistir, o item fica como erro e o lote segue. OB já anexada
numa rodada anterior é anexada de novo, com aviso para excluir o que
ficar em dobro. Cada lote grava um relatório `.csv` em `lotes/`.

### Métricas, relatório das OBs e painel de resultados

Cada OB vira uma linha em `metricas/metricas.csv` (tempo no SIGEF, no
SEI, documentos, tentativas). Pelo botão **Relatório das OBs** da
janela sai uma página HTML com indicadores e gráficos do período,
incluindo o tempo economizado frente ao trabalho manual.

O botão **Painel de resultados** junta OB, NE e DARE: tempo economizado
no total, por mês e por pessoa (economizado = concluídos × minutos à mão −
tempo de todas as rodadas, inclusive as que falharam). Lê as métricas que
já existem: `metricas.csv` (e os `metricas_ate_*.csv` antigos),
`metricas_ne.csv` e o `dados\desempenho.csv` do DARE. "Por pessoa" é o
dono de cada pasta: a desta máquina entra sempre; a de cada colega entra
pelo botão "Incluir a pasta de outra pessoa" (a pasta Documentos dele,
copiada ou na rede) e fica lembrada no `config.json`.

### Ano do SIGEF

O SIGEF tem um endereço por exercício (`…/SIGEF2026/…`). O ano vem de
`automacoes/geral.py`: padrão, o ano atual; no rodapé da barra lateral dá
para escolher outro, para quando o SIGEF demora a virar. A troca vale na
hora para a OB e a NE (endereços e conferência do número da NE) e não é
aceita com uma automação rodando. Endereço novo do SIGEF: use
`url_sigef("FIN/Tela.aspx")`, nunca o ano escrito.

### Rodando uma parte isolada

Da pasta do programa:

```bash
python -m automacoes.sigef_sei.preparar_navegador   # testa só o navegador e o login
python -m automacoes.sigef_sei.etapa_sei2           # anexa um processo já baixado
```

### Particularidades do SIGEF que o código contorna

Estão anotadas no código, onde importam:

- **Ids duplicados.** O botão Imprimir tem o mesmo id no `<a>` e no
  `<img>` de dentro dele, variando só a caixa da letra. Como o SIGEF roda
  em modo *quirks*, o navegador compara ids sem diferenciar maiúscula de
  minúscula e o Playwright para com *strict mode violation*. Todos os
  Imprimir são clicados pelo `title`.
- **Desvio de janela.** Ao fechar a tela da Despesa Certificada, o SIGEF
  redireciona a janela da PP para "Detalhar Ordem Bancária", onde os
  campos da PP não existem. O código confere a URL e renavega.
- **Formato do número.** A tela de Conferência recusa `2026OB136475` e
  só aceita o sequencial `136475`.
- **Grade redesenhada.** Os números das PPs são lidos todos de uma vez,
  antes de qualquer clique: cada volta do laço sai da tela e volta, e um
  localizador por posição ficaria velho.
- **Ordem dos downloads.** A CE só é alcançável de dentro da tela de uma
  PP, então sai na primeira volta do laço. A OB vem de uma tela aberta na
  aba principal, e mexer nela antes derrubaria a janela de detalhe de
  que o laço das PPs depende — por isso é a última.

---

## Nota de Empenho (NE)

A partir do número de **uma Nota de Empenho** e do processo, imprime a NE
no SIGEF (tela *Imprimir Nota de Empenho*), converte cada página do PDF em
imagem e anexa no processo do SEI como **"NE - Nota de Empenho"** (Restrito,
hipótese legal "Documento Preparatório"). Não gera, não altera e não exclui
nada no SIGEF: a NE precisa já existir.

Na janela, é o módulo **Nota de Empenho** da barra lateral, separado do
*Anexar no SEI* (a OB): telas, lista, relatório e eventos próprios
(`janela/interface/ne.js` ↔ `janela/modulo_ne.py`, uma porta só:
`api.ne(acao, dados)`, como o DARE). As duas dividem só o Chrome da
automação e o login, e não rodam juntas (`USO_DO_CHROME`):

```
Processo do SEI    0029.001947/2026-67   (ou só: 0029001947202667)
Nota de Empenho    2026NE000123          (ou só: 123)
Nome na árvore     Empenho do contrato 12  (opcional, até 50 caracteres)
```

O nome na árvore vai no campo `#txtNomeArvore` do formulário do SEI, depois
de escolher "NE - Nota de Empenho" e preencher o resto; em branco, o campo
fica vazio. Só no modo "Uma NE".

A tela do SIGEF é de um exercício só (o do **Ano do SIGEF**): NE de outro ano é
recusada antes de começar. No lote (planilha ou lista colada), cada linha
traz o processo e a NE; sem o prefixo `2026NE`, a NE precisa dos zeros
(`000123`) — ou a coluna precisa do cabeçalho "NE", que aceita qualquer
número. Pela tela preta: `python -m automacoes.ne.terminal`.

Do caminho da OB vêm a retomada depois de queda, a divisão por tamanho do
SEI e a redução das imagens. Cada NE vira uma linha em
`metricas/metricas_ne.csv`, e o botão **Relatório das NEs**, na aba da NE,
gera o relatório gerencial delas.

O SIGEF é `http`: o Chrome da automação abre tratando o SIGEF como origem
segura, senão ele bloqueia o download do PDF ("Insecure download
blocked"). Isso só vale quando o Chrome é aberto pelo programa — um Chrome
da automação aberto por uma versão antiga precisa ser fechado uma vez.

---

## DARE

`automacoes/dare/` — o aplicativo DARE, agora como módulo da Central. Para
cada lançamento (processo SEI, CPF do servidor, CNPJ, referência,
vencimento e valor), gera o **DARE avulso** no site da SEFIN, salva o PDF e
o anexa como documento externo no processo do SEI.

Na janela, o módulo **DARE** troca os passos do SEI pelas páginas do
aplicativo DARE, na barra lateral:

| Página           | O que tem                                                                 |
|------------------|---------------------------------------------------------------------------|
| Início           | navegador, lista, concluídos hoje, tamanho da pasta de PDFs, últimas execuções |
| Lançamentos      | formulário (valida ao sair do campo), lista com editar/duplicar/remover, **Importar planilha** |
| Execução         | progresso por lançamento e por etapa, tempo restante, registro, parar após o atual |
| Arquivos PDF     | limpeza por idade, data, seleção ou tudo (Lixeira ou de vez), limpeza automática |
| Desempenho       | tempos por etapa, monitor do computador, diagnóstico, testes de velocidade, relatório |
| Configurações    | versão, navegador, pastas, valores fixos, guia de uso e licença           |

Atalhos (com o DARE aberto): **Ctrl+N** novo lançamento, **Ctrl+I**
importar planilha, **F5** atualizar.

Diferenças em relação ao aplicativo DARE separado — de propósito:

- **Um navegador só.** O DARE usa o Chrome da Central (perfil
  `C:\ChromeAutomacao`, porta 9222), não o perfil próprio dele. Na
  primeira rodada, entre no DARE e no SEI nessa janela; os logins ficam
  salvos junto com os do SIGEF e do BB.
- **Uma automação por vez.** Com o SIGEF → SEI ou o BB rodando, o DARE
  não começa (e vice-versa).
- "Abrir o navegador ao iniciar" vale quando o módulo DARE é aberto pela
  primeira vez, não ao abrir a Central.

Os dados continuam em `Documentos\DARE Automação`: quem já usava o
aplicativo DARE encontra o histórico, os pendentes e os PDFs na Central.
Sozinho, pelo terminal: `python -m automacoes.dare.terminal`.

**PDFs juntados por processo (DARE 3.1):** quando a lista tem vários
lançamentos do **mesmo processo**, o motor gera todos os DAREs, **junta os
PDFs num único arquivo** (`DARE_JUNTADO_<processo>_<N>-DAREs_<data>.pdf`, na
mesma pasta) e anexa **só esse arquivo** no SEI, uma vez por processo; os PDFs
individuais continuam na pasta. Um processo com um só DARE anexa o próprio
PDF. Se não der para juntar (`pypdf` ausente ou PDF ilegível), anexa um a um,
como antes. Os lançamentos do mesmo processo são colocados em sequência
(`juntar.ordenar_por_processo`), e a tela de Execução numera as linhas nessa
ordem.

---

## Anexar Documentos

`automacoes/anexar/` — o programa **Anexar Documentos 1.6**, agora como módulo da
Central. Regularização de parcelas: abre o processo no SEI, **faz** a Despesa
Certificada (CE) com o Valor Total e, para cada lançamento (valor + nota de
empenho), a Nota de Liquidação (NL) e a Preparação de Pagamento (PP); depois
**uma** Ordem Bancária (OB) para o lote, baixa os relatórios e anexa no SEI.
**Aponta para o SIGEF de produção: tudo o que gerar vale de verdade.**

Na janela, as mesmas telas do aplicativo (`janela/interface/anexar.js` ↔
`janela/modulo_anexar.py`, uma porta só: `api.anexar(acao, dados)`), no menu da
barra lateral: **Início**, **Fazer um processo** (ao vivo: a barra dos 7 passos, o
quadro que fica amarelo quando é a sua vez, as NL/PP/OB que vão saindo e o
registro técnico), **Configurações** (Global, CE, NL, PP, OB), **Estatísticas**,
**Relatório do mês**, **Ajuda e licença**, o **Modo treino** e a letra A/A+/A++.

Como no aplicativo, a automação roda **noutro processo** (`nucleo.Execucao` abre
`python -m automacoes.anexar.aplicativo.executor`; instalada, o próprio `.exe`
com `--executor`, tratado no começo do `app_janela.py`). Cada pergunta é um
**pedido** (`interacao.py`) que a página desenha; a página lê os eventos pela
porta `novidades`. O que muda por estar na Central (`automacoes/anexar/central.py`):
o **ano do SIGEF** da barra lateral, o **Chrome da Central** (com o SIGEF como
origem segura) e **uma automação por vez** (o `USO_DO_CHROME` fica com o Anexar
até o executor terminar; o Modo treino não usa o Chrome).

Sozinho, pela tela preta: `python -m automacoes.anexar.automacao.fluxo` (as
perguntas viram lista numerada; os dados vão para `dados\` na pasta do
programa — use `ANEXAR_PASTA_DADOS` para apontar para outro lugar).

---

## Cadastro de Credores

`automacoes/cadastro/` — o programa **Cadastrar_Pessoas_e_conta**
(CadastroSIGEF 2.3), agora como módulo da Central. Para cada pessoa: pesquisa o
CPF no cadastro de credores do SIGEF; se não existir, cadastra o credor
(consulta à Receita); inclui o domicílio bancário (banco, agência, conta e nome);
lê a mensagem do SIGEF e registra o resultado.

Na janela, as mesmas telas do aplicativo Tkinter (`janela/interface/cadastro.js`
↔ `janela/modulo_cadastro.py`, `api.cadastro(acao, dados)`), com a trilha
**1 Entrar no SIGEF → 2 Escolher os dados → 3 Cadastrar → 4 Ver o resultado** na
barra lateral: planilha do Excel aberta (o resultado vai na coluna escolhida) ou
digitar/colar/abrir `.csv`; conferir cada pessoa antes de gravar (ou direto);
parar depois da pessoa atual; refazer só as que deram erro; **Estatísticas**
(tempo manual cronometrado, pasta da pesquisa, relatório); Letra maior/menor e
Ajuda (F1). O Playwright e o Excel (COM) rodam numa linha só do módulo, como no
aplicativo. Na Central: o Chrome da Central (sem Chrome, procura o Edge, como
antes), o ano do SIGEF e uma automação por vez.

Sozinho, pela tela preta: `python -m automacoes.cadastro.terminal`.

---

## Automações BB

`automacoes/bb/automacoes_bb.py` — cargas de cartão no portal do Banco do
Brasil (`autoatendimento2.bb.com.br`), para os programas **PNAE** e
**PROAFI**:

- Carregamento pelo portador
- Carga de limite (cartão corporativo) — com modo simulação
- Anexar saldos no SEI
- Carga avulsa (1 processo, sem planilha)

Os PDFs de saldo e demonstrativos ficam em `Documentos\Automacoes BB`.
A planilha que já estiver aberta no Excel é reaproveitada (não abre um
segundo Excel), e no modo visível ela fica aberta durante a carga.
Na janela: módulo **Banco do Brasil**. Sozinho, pelo terminal:
`python automacoes/bb/automacoes_bb.py`. Precisa do **Microsoft Excel**.

---

## Licença

A janela (`app_janela.py`) só abre as automações com uma **licença
válida** neste computador; sem ela, aparece só a tela de ativação.
A tela preta (`main.py`) não confere licença.

1. A tela de ativação mostra o **código desta máquina** (ex.:
   `7K2Q-9MXA-4TRB`), derivado do identificador do Windows — não muda ao
   reinstalar o programa.
2. Quem administra as licenças gera, com o **Gerador de Licenças** (que
   não está neste repositório nem no instalador), uma chave
   `SIGEFSEI-...` para aquele código, com nome e validade.
3. A pessoa cola a chave e clica em **Ativar**. A chave fica em
   `%APPDATA%\Automacao SIGEF-SEI\licenca.txt`.

A chave é assinada (Ed25519): o programa leva só a chave pública
(`CHAVE_PUBLICA_HEX` em `janela/licenca.py`), que confere mas não cria
licenças. Sem servidor, não dá para cancelar à distância — o controle é a
validade. Faltando 15 dias, a janela avisa; o título mostra para quem e
até quando está licenciado. Voltar o relógio do computador não estende
uma licença vencida.

---

## Para quem mexe no código

### Testes

```bash
python -m pip install -r requirements-dev.txt   # uma vez: as dependências + pytest
python testes/rodar_tudo.py                     # todos os grupos; termina com erro se algum falhar
python testes/rodar_tudo.py dare geral          # só alguns grupos
```

O `rodar_tudo.py` usa uma pasta de dados temporária (nada toca os dados reais)
e se recusa a rodar com o Chrome da automação aberto (porta 9222). O mesmo
comando roda no GitHub a cada push (`.github/workflows/testes.yml`, com Python 3.13).
Para rodar só um grupo à mão:

```bash
python testes/testes_divisao.py
python testes/teste_escolha_documentos.py
python -m unittest discover -s testes/dare -t .
python -m unittest discover -s testes/ne -t .
python -m unittest discover -s testes/geral -t .
python -m pytest testes/anexar -q         # Anexar Documentos: etapas contra SIGEF/SEI simulados + a janela (Modo treino)
python -m pytest testes/cadastro -q       # Cadastro de Credores: SIGEF simulado + a janela (porta 80 e 9222)
python testes/teste_janela_demo.py        # precisa do Chromium do Playwright
python testes/ne/rodar_cenarios.py        # idem; sobe um SIGEF e um SEI simulados
```

Os cinco primeiros são offline: não abrem navegador nem falam com
SIGEF/SEI/DARE. Cobrem a divisão dos anexos em partes (limite de 2 MB do
SEI), a largura da imagem da OB, a escolha dos documentos, no DARE as
validações, a leitura de planilhas, a limpeza de PDFs, os eventos do motor
e a ponte com a janela, na NE a ponte com a janela (Api e Trabalhador), e o ano do SIGEF e o
painel de resultados.

Os dois últimos usam um Chromium sem tela: o `teste_janela_demo.py` clica
na página da janela no modo demonstração (OB e NE, um processo e lote, o
limite do registro, o ano do SIGEF e o painel), e o `rodar_cenarios.py` roda a NE de verdade contra
um SIGEF e um SEI simulados (download com popup que fecha sozinho, download
bloqueado, formulário recriado pelo SEI, campo Número ausente ou oculto,
retomada). Eles usam a porta 9333; o Chrome da automação (9222) não é tocado.

### Adicionar uma automação nova

1. Crie `automacoes/<nome>/` com um `__init__.py` e o módulo.
2. Dentro do pacote, importe com ponto (`from .modulo import ...`); de
   fora, pelo caminho completo (`from automacoes.<nome> import ...`).
3. Para aparecer na janela: a ligação vai em `janela/modulos_janela.py`
   (use o `USO_DO_CHROME` para não rodar junto com as outras), os métodos
   em `Api` no `app_janela.py`, e a tela em `janela/interface/`. Uma
   automação com muitas telas pode seguir o DARE: um `janela/modulo_<nome>.py`
   com uma porta só (`Api.<nome>(acao, dados)`) e um `<nome>.js` próprio.
4. Se ela só for importada quando a pessoa abrir o módulo, liste-a em
   `hiddenimports` no `instalador/app_janela.spec`.

### Versão

A constante `VERSAO`, no início do `main.py`, aparece na tela a cada
rodada e no `.exe` instalado. Se a tela mostrar uma versão diferente da
esperada, é cópia antiga rodando — não defeito. Suba o número a cada
mudança de comportamento. O que mudou em cada versão está no
[`CHANGELOG.md`](CHANGELOG.md).

### Gerar o instalador

```bash
python -m pip install -r requirements.txt pyinstaller -c constraints.txt
python instalador/construir.py
```

O `constraints.txt` trava as versões do ambiente que gerou o instalador
(Python 3.14.6): reconstruir daqui a meses sai com os mesmos pacotes. O
código-fonte deve rodar em Python 3.10+ (não verificado em todas as versões).

Passo a passo em [`instalador/CONSTRUIR.md`](instalador/CONSTRUIR.md).

---

## Aviso

Este repositório contém **apenas código**. Documentos baixados, sessão,
métricas, planilhas e configurações ficam nas pastas de dados (fora
desta pasta), são ignorados pelo `.gitignore` e **nunca devem ser
versionados**: carregam números de processo, valores, cartões e caminhos
com o login de quem executou.

Os registros de diagnóstico (`diagnostico_salvar.log`, `registro_*.txt`,
`construir_log.txt`) e as capturas de tela `falha_editor_*.png` também
carregam endereços do SEI com o `infra_hash` da sessão, números de processo
e o nome do computador. Ficam em `Documentos\Automacao SIGEF-SEI`, fora do
repositório; não os anexe a issues nem os suba ao Git, e revise antes de
enviá-los a alguém.
