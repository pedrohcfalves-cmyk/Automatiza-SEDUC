# Histórico de versões

O número fica no `VERSAO` do `main.py` (vai para a tela, para o `.exe` e para o
instalador). Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

### Mudou
- **Automações na barra lateral, passos no topo**: a lateral esquerda tem a marca, as
  automações, o Relatório geral, a Pasta dos documentos, o contador e a versão (rola sozinha
  com a letra grande; numa janela estreita fica só com os ícones). No topo ficam os passos
  (ou as páginas do DARE e do Gerar pagamento) no meio, e o Ano do SIGEF e a Acessibilidade
  à direita. Sem espaço, só o passo atual mostra o nome.
- **Cada automação abre só as abas dela** no Chrome da automação: Anexar no SEI e NE, SIGEF e
  SEI (antes abriam também o Banco do Brasil); DARE, DARE e SEI; BB, BB e SEI; Cadastro, só o
  SIGEF — e o Cadastro não pega mais a aba de outro sistema quando não acha a do SIGEF (usa
  uma aba vazia ou abre uma). `preparar_navegador.abrir_abas_sem_conectar` abre as que faltam
  pelo `/json` do Chrome, sem tocar no resto.

### Adicionado
- **Como salvar no SEI: Como imagem ou Como PDF** (passo 3 do Anexar no SEI e da Nota de
  Empenho, nas abas de um e de vários). "Como imagem" é o caminho de sempre. "Como PDF" inclui
  cada documento como **Externo** (`escolher(-1)`), com o PDF do SIGEF: tipo no `#selSerie`
  (CE → Despesa Certificada, NL → NL - Nota de Lançamento, PP → PP - Preparação de Pagamento,
  OB → OB - Ordem Bancária de Regularização ou Ordem Bancária, conforme a escolha da OB,
  NE → NE - Nota de Empenho), data de hoje, Nato-digital, Público, Número da PP/NE e Nome na
  árvore da NE quando a tela tiver o campo. Um Externo por documento, como no modo imagem.
  Lembrado em `config.json` (`formato_sei` e `formato_sei_ne`). Código em
  `automacoes/sigef_sei/sei_pdf.py`; o download agora guarda o PDF do SIGEF ao lado das
  imagens (`guardar_pdf`); download antigo sem PDF → o PDF é montado com as imagens, com aviso.
  Retomada no mesmo `progresso_sei.json`; falha antes do Salvar é repetida sozinha, depois do
  Salvar não (poderia duplicar). Diagnóstico em `diagnostico_pdf.log` e na pasta
  `diagnostico_pdf` (passo, erro, mensagens do SEI, frames, opções do `#selSerie`, foto e HTML);
  teste da tela sem salvar: `python -m automacoes.sigef_sei.diagnostico_pdf <processo>`.
  Testes: `testes/teste_sei_pdf_navegador.py` (Chromium contra cópia do SEI: 6 documentos,
  regularização, retomada, PDF montado, clique perdido, arrastar e soltar, arquivo recusado,
  Salvar que não responde, NE) e `testes/teste_formato_sei_janela.py` (tela → API → comando).
- **Entrar nos sistemas antes de começar** no DARE e no Banco do Brasil, no modelo do Anexar
  no SEI e da NE: abre o Chrome só com as abas da automação, pede "Entrei no …" e "Conferi a
  minha gerência no SEI" e só então começa (`central.js`, `lbaLogin`; `modulo_geral`:
  `login_estado`, `abrir_abas`, `login_confirmado`). Vale uma vez por sessão, enquanto o
  Chrome estiver aberto; o DARE não pergunta de novo no meio da execução. O Gerar pagamento
  já tinha essa etapa (a primeira do fluxo dele) e o Cadastro, o passo "Entrar no SIGEF".
- Testes: `testes/geral/test_abas_e_login.py` (Chrome falso e Chromium de verdade, login,
  abas do Anexar no SEI e do Cadastro) e `TesteLayout` / `TesteEntrarAntesDeComecar` em
  `teste_janela_demo.py`.

### Mudou (também)
- "Anexar Documentos" aparece na Central como **Gerar pagamento** (para não confundir com
  "Anexar no SEI"); o código e os dados continuam os mesmos.
- **Um relatório só: Relatório geral** (`automacoes/painel.py` + `automacoes/relatorio_geral.py`),
  no lugar do Painel de resultados, do Relatório das OBs, do Relatório das NEs, das
  Estatísticas/Relatório do mês do Gerar pagamento, da aba Automação e do "Gerar relatório" do
  DARE e da página `relatorio.html` do Cadastro. Junta OB, NE, DARE, Gerar pagamento e
  Cadastro: tempo economizado, por mês (gráfico empilhado + tabela), por pessoa e uma seção
  de cada automação (documentos, sem intervenção, SIGEF × SEI, etapas, pendências,
  processos, erros mais comuns). Sumário fixo, claro/escuro, impressão/PDF, tabelas com
  cabeçalho e cor sempre com rótulo. A caixa tem atalhos de período (este mês, mês passado,
  30 dias, este ano). As pastas de colegas também trazem o `Anexar Documentos`.
- Gerar pagamento: a página Estatísticas virou **Tempos e planilhas** (estimativas à mão e as
  planilhas do estudo, com o botão do Relatório geral); a página Relatório do mês saiu.
- DARE: a página Desempenho virou **Diagnóstico** (monitor, diagnóstico e testes de
  velocidade); as estatísticas dos lançamentos estão no Relatório geral.
- Cadastro: "Gerar relatório" virou **Pacote da pesquisa (Excel)** (planilha + dados brutos)
  e a tela Estatísticas ganhou o botão do Relatório geral.

### Adicionado
- **Acessibilidade para o aplicativo inteiro** (botão no topo; `central.js`): tamanho do
  texto (100/115/130/150%, também com Ctrl +, Ctrl − e Ctrl 0), alto contraste (claro e
  escuro), foco destacado com links sublinhados, sem animações (também segue o Windows) e
  mais espaço entre linhas. Fica guardado na janela. Saíram os botões de letra próprios do
  Gerar pagamento (A/A+/A++) e do Cadastro (Letra maior/menor).
- Acessibilidade em geral: "Pular para o conteúdo", foco preso no diálogo aberto e
  devolvido ao botão que o abriu, passo atual anunciado (`aria-current="step"`), ícones
  escondidos do leitor de tela, nomes nos botões só com ícone (janela estreita).
- Testes: `TesteAcessibilidade` e o Relatório geral em `teste_janela_demo.py`;
  `TestGerarPagamentoECadastro` em `testes/geral`.
- Anexar no SEI, passo 3: **Como listar e imprimir a CE**, logo acima de "Como a OB
  entra no SEI" (nas abas Um processo e Vários processos; o programa lembra a última
  escolha em `config.json`, chave `modo_ce`). "Pela tela da PP" é o caminho de sempre
  e continua o padrão. "Pela tela Imprimir Despesa Certificada": o loop das PPs só
  anota o número de cada CE (sem clicar no campo da PP); depois do loop, cada CE
  distinta é impressa em `FINImprimirDespesaCertificadaSituacao.aspx?CdTransacao=131`
  (UG 160001, gestão 1, sequencial da CE, Imprimir padrão). CE de outro exercício ou
  fora do padrão `AAAACE######` sai pelo caminho de sempre (o campo de lá só aceita o
  sequencial e trocaria a CE). Uma CE que falhar é pulada e avisada na conferência,
  como a NL; um PDF que não mostra o número pedido também vira aviso.
  Nessa tela o PDF não baixa na hora: depois do Imprimir, o programa espera o
  relatório novo em `REL/RELListarRelatoriosAssincronos.aspx?CdTransacao=568`
  (até 120 s, recarregando a cada 3 s), clica no último relatório novo e pega o
  download do popup. Se o Chrome barrar o arquivo como perigoso, busca o mesmo
  endereço direto com a sessão do navegador.
- Diagnóstico dessa opção: cada passo em `diagnostico_ce.log`; numa falha, foto, HTML
  e relatório (passo, erro, seletores achados na tela, janelas abertas) em
  `diagnostico_ce\`. Teste avulso de uma CE no Chrome da automação:
  `python -m automacoes.sigef_sei.diagnostico_ce 2026CE001234`.
- Testes: `teste_escolha_documentos.py` (modo novo contra o SIGEF simulado),
  `teste_ce_impressao_janela.py` (a tela até o comando da automação) e
  `teste_ce_impressao_navegador.py` (Chromium real contra uma cópia da tela do SIGEF).

### Corrigido (revisão de segurança dos fluxos — planos 002 a 023)
- **O SEI abriu o processo certo?** Antes de anexar, o programa confere que a árvore que abriu é
  a do processo pedido (SIGEF→SEI, NE e Gerar pagamento). Não sendo, para com "O SEI não abriu o
  processo …" e nada é anexado.
- **Segundo clique em Processar** (OB, NE e lotes) é recusado com "Já há uma automação em
  andamento" em vez de enfileirar a mesma automação de novo.
- **Arquivos de retomada e de configuração gravados de forma atômica** (`progresso_sei.json`,
  `sessao_atual.json`, `config.json`): uma queda no meio da gravação não deixa mais o arquivo
  pela metade.
- **Retomada no SEI**: o "já salvo" guarda a impressão dos arquivos. Se numa nova tentativa os
  arquivos do documento mudaram, o documento antigo continua sendo pulado (sem duplicar), mas
  o aviso vai para a conferência final.
- **Avisos do download** (NL com erro, CE não impressa) chegam à conferência final do SIGEF→SEI.
- **Gerar pagamento**: trocar o número do processo não reaproveita mais CE/NL/PP/OB do processo
  anterior; valor com ponto e sem vírgula (`1105.50`) vira erro em vez de ser lido como
  110.550,00; o valor digitado na CE e na NL é lido de volta e, não conferindo, a automação
  **para** antes de incluir/confirmar; PP, download e textos usam o exercício escolhido no
  "Ano do SIGEF", não o ano do relógio.
- **DARE**: CSV do histórico aberto no Excel (ou disco cheio) não derruba mais o lote — a linha
  vai para `historico_reserva.csv`; célula com erro do Excel (`#N/A`, `#REF!`) na planilha vira
  problema da linha em vez de usar o valor padrão; a limpeza da pasta só enxerga `DARE_*.pdf`.
- **BB**: um segundo clique em Executar não apaga mais o "Parar" nem as respostas da execução
  em andamento. Removido `encerrar_chrome`, que nunca era chamado e fecharia o Chrome do usuário.
- **Janela**: não abre programas nem scripts (`.exe`, `.bat`, `.ps1`…) a pedido da página; um
  evento com defeito não congela mais a tela; falha ao falar com o Python aparece na tela.
- **CPF mascarado** (`***.456.789-**`) no registro do Gerar pagamento e no log do Cadastro.

### Acessibilidade
- Erros da automação são anunciados pelo leitor de tela (`role="alert"`), o "agora" é região
  viva e, ao trocar de tela, o foco vai para o título.
- Diálogos do Gerar pagamento e do Cadastro têm nome e devolvem o foco a quem abriu; a tabela
  do DARE funciona pelo teclado (setas, Shift+setas, Espaço, Enter; cabeçalhos ordenam com
  Enter); os ícones decorativos ficam fora do leitor de tela.

### Para quem mexe no código
- `python testes/rodar_tudo.py` roda todos os grupos de teste (e o GitHub roda a cada push:
  `.github/workflows/testes.yml`). `requirements-dev.txt`.
- `constraints.txt` trava as versões do ambiente de build; `requirements.txt` ganhou
  `pyautogui`, `pyperclip` e `websocket-client` (o BB usa) e pisos novos de `pillow` e `pypdf`.
- `instalador/construir.py` usa `--clean`, confere as bibliotecas do BB e **recusa gerar o
  instalador se o CHANGELOG não tiver a seção da versão**; `_gerar_instalador.bat` devolve o
  código de erro do build.
- `testes/ferramentas/comparar_funcoes.py`: o que é igual e o que divergiu entre as duas
  cópias de `etapa_sei2.py`.

## [3.9.0] - 2026-11-03

### Adicionado
- **Anexar Documentos** (módulo novo, barra lateral): o programa Anexar Documentos
  1.6 dentro da Central — regularização de parcelas: faz a CE, a NL e a PP de cada
  lançamento e uma OB no SIGEF, baixa os relatórios e anexa no SEI. As mesmas telas
  do aplicativo (Início, Fazer um processo ao vivo, Configurações, Estatísticas,
  Relatório do mês, Ajuda e licença, Modo treino, letra A/A+/A++), agora em HTML no
  estilo da Central. A automação continua rodando noutro processo (o executor);
  instalada, é o próprio `.exe` com `--executor`. Código em `automacoes/anexar/`
  (sem a janela PySide6), ligação em `janela/modulo_anexar.py` e `anexar.js`.
- **Cadastro de Credores** (módulo novo, barra lateral): o programa
  Cadastrar_Pessoas_e_conta (CadastroSIGEF 2.3) dentro da Central — credor pessoa
  física e domicílio bancário no SIGEF, digitado/colado ou da planilha do Excel. As
  mesmas telas e janelinhas do aplicativo Tkinter (trilha de 4 passos, conferir
  antes de gravar, corrigir, refazer os erros, Estatísticas, Letra maior/menor,
  Ajuda F1). Código em `automacoes/cadastro/`, ligação em `janela/modulo_cadastro.py`
  e `cadastro.js`; pela tela preta: `python -m automacoes.cadastro.terminal`.
- Nos dois: o **Chrome da Central** (um login só), o **Ano do SIGEF** da barra
  lateral e **uma automação por vez** (`USO_DO_CHROME`). Fechar a janela com um
  deles trabalhando pede confirmação.
- Testes: os dos dois programas, trazidos para `testes/anexar` e `testes/cadastro`
  (os mesmos cenários, contra SIGEF/SEI simulados), e a página de cada módulo
  clicada como um usuário falando com o Python de verdade (`testes/ponte_pagina.py`).

### Dados
- Anexar Documentos: `Documentos\Anexar Documentos` (fora da pasta do programa); na
  primeira vez, o `dados\` do Anexar Documentos instalado é copiado para lá.
- Cadastro de Credores: continua em `~\.sigef-automacao`, como no programa antigo.

## [3.8.10] - 2026-11-03

### Adicionado
- NE, passo 3 (Processo e NE): campo opcional **Nome na árvore do processo**.
  Depois de escolher "NE - Nota de Empenho" no SEI e preencher o formulário,
  o texto vai no campo "Nome na Árvore" (`#txtNomeArvore`, até 50
  caracteres). Em branco, o campo fica vazio, como antes. Se o SEI não
  mostrar o campo, a NE é anexada assim mesmo, com um aviso no registro.
  Vale para "Uma NE"; o modo "Várias NEs" e a tela preta seguem sem nome.

## [3.8.9] - 2026-11-02

### Adicionado
- **Ano do SIGEF**, no rodapé da barra lateral, vale para todas as abas.
  Padrão: o ano atual. Dá para escolher outro (de 2020 ao ano que vem)
  enquanto o SIGEF não vira o exercício; a escolha fica no `config.json` e
  escolher o ano atual volta ao padrão. Muda na hora os endereços da OB
  (CE, NL, PP, OB) e da NE e a conferência do número da NE (`2025NE…` só
  passa com 2025 escolhido). Não troca com uma automação rodando. DARE e BB
  não usam o ano do SIGEF. Tudo sai de `automacoes/geral.py`
  (`url_sigef`, `ano_sigef`): o ano não fica mais escrito no código.
- **Painel de resultados** (botão na barra lateral): OB, NE e DARE juntos,
  com o tempo economizado no total, por mês e por pessoa, e um gráfico por
  mês. Lê as métricas que cada automação já grava (nada muda nelas). Para
  somar a equipe, inclua a pasta Documentos de cada colega (copiada ou na
  rede); os minutos à mão de cada automação ficam guardados
  (`automacoes/painel.py`, `janela/modulo_geral.py`, `api.geral`).

### Mudou
- O botão "Relatório gerencial" da barra lateral agora se chama
  "Relatório das OBs" (é o mesmo relatório).

## [3.8.8] - 2026-11-02

### Adicionado
- Com a aba da NE aberta, a barra lateral mostra os passos dela (Início, Entrar
  nos sistemas, Processo e NE, Baixar e anexar, Conferência), como na OB.
- A automação da NE tem versão própria (`__version__` em `automacoes/ne/`,
  agora **2.1.0**: a 2.0.2 era o programa "Automação NE" separado). Ela aparece
  na aba da NE, no rodapé da barra lateral e no passo 1.

## [3.8.7] - 2026-11-02

### Mudou
- A **Nota de Empenho tem a sua própria aba** ("Nota de Empenho", na barra
  lateral), separada do *Anexar no SEI*, que volta a ser só da Ordem Bancária
  (CE, NL, PP e OB), com as telas e o código da janela da OB iguais aos da
  3.8.5. A NE tem telas, lista, relatório e eventos próprios
  (`janela/interface/ne.js` e `janela/modulo_ne.py`, uma porta só:
  `api.ne(acao, dados)`, como o DARE). As duas dividem só o Chrome da
  automação e o login, e uma espera a outra terminar.
- O relatório das NEs sai pelo botão "Relatório das NEs", na aba da NE; o
  "Relatório gerencial" da barra lateral volta a ser só das OBs.

### Corrigido
- O instalador agora leva o módulo da NE (`hiddenimports`), que passou a ser
  carregado só quando a aba é aberta.

## [3.8.6] - 2026-10-30 (não distribuída: a NE ficava dentro do Anexar no SEI)

### Adicionado
- **Nota de Empenho (NE)** na Central, no módulo *Anexar no SEI*: no passo 3,
  "O que anexar no SEI" escolhe entre Ordem Bancária e Nota de Empenho. A NE é
  impressa no SIGEF, cada página vira imagem e entra no processo como
  "NE - Nota de Empenho" (Restrito, Documento Preparatório). Um processo ou
  lote (planilha/lista), com a mesma tela de execução, conferência e
  "Continuar de onde parou" da OB. Veio do programa *Automação NE* 2.0.2,
  que deixa de ser um aplicativo separado (`automacoes/ne/`).
- Relatório gerencial das NEs (`metricas/metricas_ne.csv`), escolhido na
  mesma caixa do relatório das OBs.
- A NE pela tela preta: `python -m automacoes.ne.terminal`.
- Testes: a página da janela clicada como um usuário
  (`testes/teste_janela_demo.py`), a ponte da NE com a janela
  (`testes/ne/test_janela_ne.py`) e os cenários da NE contra SIGEF e SEI
  simulados (`testes/ne/rodar_cenarios.py`).

### Mudou
- O Chrome da automação abre tratando o SIGEF (http) como origem segura: o
  Chrome deixa de bloquear os downloads do SIGEF ("Insecure download blocked").
  Vale quando o Chrome é aberto pelo programa.
- O registro detalhado da janela guarda as últimas 3000 linhas (o arquivo em
  `registros/` continua com tudo) e recebe as linhas em lote: antes, cada linha
  reescrevia o registro inteiro, e a janela ficava mais lenta e mais pesada a
  cada processo de um lote longo.
- A redução das imagens grandes para o SEI só redimensiona quando a escala
  muda e codifica na memória (mesmo resultado, ~25% mais rápida com Pillow),
  e libera a imagem e o documento ao terminar.
- O PDF do SIGEF é fechado mesmo quando a conversão de uma página falha.

### Corrigido
- O SEI às vezes recria o formulário de "Incluir Documento" logo depois de um
  clique ("Frame was detached"): agora o programa acha o formulário de novo e
  continua, em vez de parar (vale para a OB e para a NE).
- O relatório gerencial não abria em Python anterior ao 3.12 (aspas dentro de
  f-string).
- O relatório das NEs com a data final antes da inicial saía vazio; agora vale
  o mesmo período, como no relatório das OBs.
