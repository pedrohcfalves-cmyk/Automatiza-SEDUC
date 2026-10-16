# Central de Automações — SEDUC

Automatiza trajetos manuais entre os sistemas do Governo de Rondônia
(SIGEF, SEI, DARE da SEFIN) e o portal do Banco do Brasil. São **três
automações**, que rodam no mesmo Chrome e aparecem juntas numa janela só
(a *Central de Automações*):

| Automação          | O que faz                                                                 | Pasta                    |
|--------------------|---------------------------------------------------------------------------|--------------------------|
| **SIGEF → SEI**    | A partir de uma Ordem Bancária, baixa CE, NL, PP e OB do SIGEF e anexa no processo do SEI | `automacoes/sigef_sei/` |
| **DARE**           | Gera o DARE avulso, salva o PDF e anexa no processo do SEI — digitado ou importado do Excel | `automacoes/dare/` |
| **Automações BB**  | Cargas de cartão no portal do Banco do Brasil e anexo dos saldos no SEI   | `automacoes/bb/`         |

Uma automação roda por vez: todas usam o mesmo Chrome, e a janela não
deixa duas começarem juntas.

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
| `python app_janela.py`         | uso normal pelo código                      | a janela da Central (as três automações) |
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
app_janela.py             porta de entrada da janela: a Central com as três automações
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
├── dare/                 DARE avulso → PDF → SEI (o antigo aplicativo DARE, sem a janela Tkinter)
│   ├── motor.py                 a rodada: para cada lançamento, gera o DARE, salva o PDF e anexa no SEI
│   ├── dare.py · sei.py         os passos no site do DARE e no SEI
│   ├── planilha.py · excel_com.py · planilha_arquivo.py   importação do Excel (aberto ou .xlsx)
│   ├── limpeza.py · desempenho.py · armazenamento.py      PDFs, medições, histórico e pendentes
│   ├── terminal.py              o DARE sozinho, pelo terminal (python -m automacoes.dare.terminal)
│   └── GUIA_DE_USO.html · LICENCA.txt
└── bb/                   Automações BB (portal do Banco do Brasil)
    └── automacoes_bb.py

janela/                   A JANELA (usada pelo app_janela.py)
├── interface/            a página: index.html, estilo.css, app.js, modulos.js, dare.js, dare.css
├── modulos_janela.py     liga o BB à janela (configuração, thread, perguntas) e guarda o USO_DO_CHROME
├── modulo_dare.py        liga o DARE à janela: uma porta só, api.dare(acao, dados)
└── licenca.py            ativação por chave: código da máquina + chave assinada

testes/
├── testes_divisao.py     testes offline da divisão de anexos (limite de 2 MB do SEI)
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
              ├─▶ janela/modulos_janela ──▶ automacoes/bb/automacoes_bb.py
              └─▶ janela/modulo_dare ─────▶ automacoes/dare/ (motor, planilha, limpeza, desempenho)
```

O SIGEF → SEI e o BB não importam a janela: continuam falando por `print()` e
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

### Métricas e relatório gerencial

Cada OB vira uma linha em `metricas/metricas.csv` (tempo no SIGEF, no
SEI, documentos, tentativas). Pelo botão **Relatório gerencial** da
janela sai uma página HTML com indicadores e gráficos do período,
incluindo o tempo economizado frente ao trabalho manual.

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
python testes/testes_divisao.py
python -m unittest discover -s testes/dare -t .
```

Offline: não abrem navegador nem falam com SIGEF/SEI/DARE. Cobrem a
divisão dos anexos em partes (limite de 2 MB do SEI), a largura da imagem
da OB e, no DARE, as validações, a leitura de planilhas, a limpeza de
PDFs, os eventos do motor e a ponte com a janela.

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
mudança de comportamento.

### Gerar o instalador

```bash
python -m pip install -r requirements.txt pyinstaller
python instalador/construir.py
```

Passo a passo em [`instalador/CONSTRUIR.md`](instalador/CONSTRUIR.md).

---

## Aviso

Este repositório contém **apenas código**. Documentos baixados, sessão,
métricas, planilhas e configurações ficam nas pastas de dados (fora
desta pasta), são ignorados pelo `.gitignore` e **nunca devem ser
versionados**: carregam números de processo, valores, cartões e caminhos
com o login de quem executou.
