/* Módulo Cadastro de Credores — o programa "Cadastrar_Pessoas_e_conta" (CadastroSIGEF) na Central.
 *
 * As mesmas telas, na mesma ordem, da janela original (sigef/interface/telas.py):
 *   Início → 1 Entrar no SIGEF → 2 Escolher os dados (planilha / digitar ou colar)
 *          → 3 Cadastrar → 4 Ver o resultado       (+ Estatísticas, Ajuda; a letra é a da Central)
 * e as mesmas janelinhas (conferir antes de gravar, corrigir, colar uma lista, cronometrar…).
 *
 * Tudo no Python passa por UMA porta: api.cadastro(acao, dados), que chega em
 * janela/modulo_cadastro.py. O andamento chega pelos eventos "cad_*".
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const guardar = (chave, valor) => { try { localStorage.setItem(chave, valor); } catch (e) { /* sem armazenamento */ } };
  const lembrar = (chave) => { try { return localStorage.getItem(chave); } catch (e) { return null; } };

  const PASSOS = ["Entrar no SIGEF", "Escolher os dados", "Cadastrar", "Ver o resultado"];
  const CAMPOS = ["cpf", "nome", "banco", "agencia", "conta"];
  const ROTULOS = { cpf: "CPF", nome: "Nome", banco: "Banco", agencia: "Agência", conta: "Conta" };
  const CONFERENCIA = [
    ["auto", "Cadastrar direto, sem perguntar", "O programa faz tudo sozinho. É o jeito mais rápido."],
    ["manual", "Mostrar os dados de cada pessoa antes de gravar", "Você confere e confirma cada pessoa. Mais devagar, porém mais seguro."],
  ];
  const TIPOS_CADASTRO = [
    ["novo", "Credor novo + conta bancária", "A pessoa ainda não existe no SIGEF: cadastrar o credor e depois a conta."],
    ["existente", "Só a conta bancária", "A pessoa já é credora no SIGEF: só incluir o domicílio bancário."],
  ];
  const AJUDA = {
    inicio: "Clique no botão verde Começar. O programa vai abrir o Google Chrome na página do SIGEF para você entrar com seu usuário e senha.",
    login: "O programa abriu o Google Chrome na página do SIGEF. Entre com seu usuário e senha, como você faz todos os dias. Depois volte para esta janela e clique no botão verde Já entrei no SIGEF.\n\nSe a janela do Chrome sumiu, clique em Abrir o Chrome de novo.",
    origem: "Se os dados das pessoas estão numa planilha do Excel, escolha Planilha do Excel. Se você vai digitar os dados, ou copiar de outro lugar, escolha Digitar ou colar.",
    planilha: "A lista mostra as planilhas que estão abertas no Excel agora. Clique na planilha certa e depois na aba (a folha) onde estão os dados. Se a planilha não aparecer, clique em Procurar arquivo e escolha o arquivo no computador.\n\nImportante: o resultado de cada pessoa será escrito na planilha e ela será salva a cada linha.",
    colunas: "Cada informação da pessoa fica numa coluna da planilha (A, B, C…). Olhe o exemplo ao lado de cada uma: ele mostra o que está escrito na primeira pessoa. Se algum exemplo estiver errado, troque a letra da coluna.\n\nO resultado de cada pessoa (cadastrado, já cadastrado ou o problema) será escrito na coluna do resultado, apagando o que houver nela.",
    digitar: "Preencha os cinco campos de uma pessoa e clique em Adicionar à lista (ou aperte Enter no último campo). A pessoa aparece na lista do lado direito.\n\nPara tirar alguém da lista, clique na pessoa e depois em Tirar da lista.\n\nSe você tem uma lista pronta (do Excel ou de um texto), use Colar uma lista ou Abrir arquivo.",
    cadastro: "O programa está cadastrando as pessoas no SIGEF, uma de cada vez. Espere até aparecer a tela de resultado.\n\nSe precisar interromper, clique em Parar o cadastro: o programa termina a pessoa atual e para.\n\nQuando todas as pessoas forem feitas, as que deram erro ficam guardadas e você pode refazer só elas com o botão Refazer as que deram erro.",
    resultado: "Esta tela mostra o que aconteceu com cada pessoa. As pessoas com problema estão marcadas com ✖ e o motivo aparece ao lado.\n\nAs pessoas com problema ficam guardadas enquanto a Central estiver aberta: clique em Refazer as que deram erro para tentar de novo só com elas.\n\nO registro completo fica na pasta de registros (botão Abrir a pasta de registros).",
    estatisticas: "Esta tela compara o tempo de um cadastro feito à mão com o tempo da automação.\n\nO tempo manual fica mais preciso quando você cronometra alguns cadastros feitos à mão: clique em Cronometrar um cadastro manual, faça o cadastro no SIGEF e clique em Terminei.\n\nEste computador mostra só os dados desta máquina. Todos os computadores soma também os dados da pasta da pesquisa e os arquivos trazidos de outras máquinas.\n\nPacote da pesquisa cria uma planilha do Excel e os dados brutos, na pasta Documentos. Para apresentar, use o Relatório geral: ele junta o Cadastro com as outras automações.",
  };
  const PASSO_DA_TELA = { inicio: 0, login: 1, origem: 2, planilha: 2, colunas: 2, digitar: 2, cadastro: 3, resultado: 4, estatisticas: 0 };

  let g = null; // ganchos da Central
  const s = {
    iniciado: false,
    ativo: false,
    tela: "inicio",
    retorno: "inicio",
    versao: "",
    lotes: [],
    selecionado: null,
    conferencia: "auto",
    refazer: 0,
    cadastrando: false,
    letras: [],
    info: null, // a planilha lida (tela das colunas)
    pastas: [],
    cad: null, // o cadastro em andamento
    fim: null, // o último resultado
    fimPendente: false, // terminou com erros e ainda está no passo 3
    escopo: null,
    pastaPesquisa: "",
    aberta: null, // a janelinha de pergunta aberta
  };

  // ----------------------------------------------------------- Python

  async function chamar(acao, dados = {}) {
    try {
      const api = g && g.api();
      if (!api || !api.cadastro) return { ok: false, erro: "A janela ainda está carregando. Tente de novo." };
      return (await api.cadastro(acao, dados)) || { ok: false, erro: "sem resposta" };
    } catch (erro) {
      return { ok: false, erro: String(erro && erro.message ? erro.message : erro) };
    }
  }

  // ----------------------------------------------------------- peças

  const banner = (tipo, texto) => `<div class="dare-banner ${tipo}"><span class="txt">${esc(texto)}</span></div>`;
  const tabela = (colunas, linhas, extra = "") =>
    `<div class="dare-tabela ${extra}"><table><thead><tr>${colunas.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${linhas}</tbody></table></div>`;
  const TOM = { OK: "ok", JA: "ok", PULADO: "", ERRO: "erro", AGORA: "andamento" };
  const botao = (id, texto, estilo = "fantasma", extra = "") => `<button class="btn ${estilo}" type="button" id="${id}"${extra}>${texto}</button>`;

  function linhaResultado(linha, status) {
    return `<tr class="${TOM[status] || ""}" data-chave="${esc(linha[0])}"><td class="mono">${esc(linha[0])}</td><td>${esc(linha[1])}</td><td class="mono">${esc(linha[2])}</td><td class="situ">${esc(linha[3])}</td></tr>`;
  }

  function escolha(nome, opcoes, atual) {
    return `<div class="campo"><div class="opcoes-tipo cad-escolha">${opcoes
      .map(([valor, titulo, dica]) => `<label class="opcao"><input type="radio" name="${nome}" value="${valor}"${valor === atual ? " checked" : ""}><span class="radio"></span><span class="texto"><b>${esc(titulo)}</b><small>${esc(dica)}</small></span></label>`)
      .join("")}</div></div>`;
  }
  const escolhido = (nome) => (document.querySelector(`input[name="${nome}"]:checked`) || {}).value;

  function bipe() {
    // O aviso sonoro da janela original (a pessoa pode estar olhando o Chrome).
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [[660, 0], [880, 0.2]].forEach(([f, t]) => {
        const o = ctx.createOscillator(), v = ctx.createGain();
        o.frequency.value = f;
        v.gain.value = 0.08;
        o.connect(v);
        v.connect(ctx.destination);
        o.start(ctx.currentTime + t);
        o.stop(ctx.currentTime + t + 0.18);
      });
    } catch (e) { /* sem som: tudo bem */ }
  }

  // ----------------------------------------------------------- janelinhas

  function modal(html, aoFechar) {
    const fundo = document.createElement("div");
    fundo.className = "modal dare-modal cad-modal";
    fundo.innerHTML = `<div class="modal-caixa" role="dialog" aria-modal="true">${html}</div>`;
    document.body.appendChild(fundo);
    fundo.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && aoFechar) {
        e.preventDefault();
        aoFechar();
      }
    });
    const foco = fundo.querySelector("[autofocus]") || fundo.querySelector(".btn.primario, input, textarea, button");
    if (foco) setTimeout(() => foco.focus(), 30);
    return fundo;
  }

  /* Mensagem com um ou mais botões; devolve o valor do botão clicado (recado() da janela original). */
  function recado(titulo, texto, tipo = "info", botoes = [["Entendi", true, "primario"]]) {
    return new Promise((ok) => {
      const tom = { atencao: "aviso", ok: "sucesso" }[tipo] || tipo;
      const m = modal(`<h2 style="margin:0">${esc(titulo)}</h2>${banner(tom, texto)}
        <div class="botoes">${botoes.map(([r, _v, est], i) => `<button class="btn ${est || "fantasma"}" type="button" data-i="${i}">${esc(r)}</button>`).join("")}</div>`,
        () => fechar(botoes.length === 1 ? botoes[0][1] : null));
      const fechar = (v) => {
        m.remove();
        ok(v);
      };
      m.querySelectorAll("[data-i]").forEach((b) => (b.onclick = () => fechar(botoes[Number(b.dataset.i)][1])));
    });
  }

  function formularioPessoa(prefixo, valores = {}, colunas = 1) {
    return `<div class="cad-form" style="grid-template-columns:repeat(${colunas},minmax(0,1fr))">${CAMPOS.map(
      (c) => `<div class="campo cad-campo" data-campo="${c}"><label for="${prefixo}-${c}">${ROTULOS[c]}</label>
        <input id="${prefixo}-${c}" value="${esc(valores[c] || "")}" spellcheck="false" autocomplete="off"${c === "cpf" ? ' inputmode="numeric"' : ""}>
        <div class="dica">${esc((s.dicas || {})[c] || "")}</div></div>`).join("")}</div>`;
  }

  function lerFormulario(prefixo) {
    const v = {};
    CAMPOS.forEach((c) => (v[c] = ($(`${prefixo}-${c}`) || {}).value || ""));
    return v;
  }

  function marcarErros(raiz, prefixo, r) {
    CAMPOS.forEach((c) => {
      const caixa = raiz.querySelector(`.cad-campo[data-campo="${c}"]`);
      if (!caixa) return;
      const erro = (r.erros || {})[c];
      caixa.classList.toggle("invalido", !!erro);
      if (c !== "banco" || erro) caixa.querySelector(".dica").textContent = erro || (s.dicas || {})[c] || "";
    });
    const primeiro = CAMPOS.find((c) => (r.erros || {})[c]);
    if (primeiro) $(`${prefixo}-${primeiro}`).focus();
  }

  function ligarFormulario(raiz, prefixo, aoTerminar) {
    // Enter passa para o próximo campo, como numa ficha de papel; no último, a ação.
    CAMPOS.forEach((c, i) => {
      $(`${prefixo}-${c}`).addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        if (i < CAMPOS.length - 1) $(`${prefixo}-${CAMPOS[i + 1]}`).focus();
        else aoTerminar();
      });
    });
    let espera = null;
    $(`${prefixo}-banco`).addEventListener("input", () => {
      clearTimeout(espera);
      espera = setTimeout(async () => {
        const r = await chamar("banco", { texto: $(`${prefixo}-banco`).value });
        const caixa = raiz.querySelector('.cad-campo[data-campo="banco"]');
        if (!caixa) return;
        caixa.classList.toggle("invalido", !!r.problema);
        caixa.classList.toggle("valido", !!r.texto && !r.problema);
        caixa.querySelector(".dica").textContent = r.texto || (s.dicas || {}).banco || "";
      }, 250);
    });
  }

  function conferir(ev) {
    bipe();
    const l = ev.lote;
    const m = modal(`<h2 style="margin:0">${esc(ev.pergunta)}</h2>
      <p class="nota" style="margin:0">Confira com atenção. Nada é gravado até você responder.</p>
      <dl class="dare-chaves cad-pessoa"><dt>Nome</dt><dd>${esc(l.nome)}</dd><dt>CPF</dt><dd>${esc(l.cpf_formatado)}</dd>
        <dt>Banco</dt><dd>${esc(l.banco_nome || l.banco)}</dd><dt>Agência</dt><dd>${esc(l.agencia)}</dd><dt>Conta</dt><dd>${esc(l.conta)}</dd></dl>
      <div class="cad-botoes-coluna">
        <button class="btn primario grande" type="button" data-r="s" autofocus>Sim, está certo</button>
        <button class="btn fantasma" type="button" data-r="t">Sim, e não perguntar mais sobre esta pessoa</button>
        ${ev.editavel ? '<button class="btn fantasma" type="button" data-r="n">Corrigir os dados</button>' : ""}
        <button class="btn fantasma pequeno" type="button" data-r="p">Pular esta pessoa</button>
      </div>`, () => responder("p"));
    // Fechar (Esc) equivale a pular: nada é gravado sem um "sim" explícito.
    const responder = (valor) => {
      m.remove();
      s.aberta = null;
      chamar("responder", { valor });
    };
    m.querySelectorAll("[data-r]").forEach((b) => (b.onclick = () => responder(b.dataset.r)));
    s.aberta = m;
  }

  function corrigir(ev) {
    bipe();
    const m = modal(`<h2 style="margin:0">Corrija os dados desta pessoa</h2>
      <p class="nota" style="margin:0">Depois clique em Salvar e tentar de novo. O cadastro desta pessoa recomeça do início.</p>
      ${formularioPessoa("cad-corr", ev.lote, 2)}
      <div class="botoes" style="justify-content:space-between"><button class="btn fantasma" type="button" id="cad-corr-pular">Pular esta pessoa</button>
      <button class="btn primario" type="button" id="cad-corr-salvar">Salvar e tentar de novo</button></div>`, () => pular());
    const pular = () => {
      m.remove();
      s.aberta = null;
      chamar("corrigido", { pular: true });
    };
    const salvar = async () => {
      const r = await chamar("corrigido", { valores: lerFormulario("cad-corr") });
      if (r.ok) {
        m.remove();
        s.aberta = null;
      } else marcarErros(m, "cad-corr", r);
    };
    ligarFormulario(m, "cad-corr", salvar);
    $("cad-corr-pular").onclick = pular;
    $("cad-corr-salvar").onclick = salvar;
    s.aberta = m;
  }

  function colarLista() {
    let avisado = false;
    const m = modal(`<h2 style="margin:0">Cole a lista de pessoas</h2>
      <p class="nota" style="margin:0">Uma pessoa por linha, nesta ordem: CPF, Nome, Banco, Agência, Conta. Pode copiar direto do Excel (as colunas nessa ordem) ou separar com ponto e vírgula.</p>
      <p style="margin:0"><b>Exemplo:</b> <code>529.982.247-25; Maria da Silva; 001; 1234; 56789-0</code></p>
      <div class="campo"><textarea id="cad-colar-texto" rows="9" spellcheck="false" autofocus></textarea></div>
      <div id="cad-colar-aviso"></div>
      <div class="botoes" style="justify-content:space-between"><button class="btn fantasma" type="button" id="cad-colar-cancelar">Cancelar</button>
      <button class="btn primario" type="button" id="cad-colar-ok">Adicionar à lista</button></div>`, () => m.remove());
    $("cad-colar-cancelar").onclick = () => m.remove();
    $("cad-colar-ok").onclick = async () => {
      const r = await chamar("colar", { texto: $("cad-colar-texto").value, forcar: avisado });
      if (r.ok) {
        m.remove();
        s.lotes = r.lotes;
        pintarLista();
        return;
      }
      if (r.ignoradas) {
        const linhas = r.ignoradas.slice(0, 6).map((i) => `Linha ${i.linha}: ${i.motivo}`).join("\n");
        const mais = r.ignoradas.length > 6 ? `\n… e mais ${r.ignoradas.length - 6}` : "";
        $("cad-colar-aviso").innerHTML = banner("erro", `${r.ignoradas.length} linha(s) com problema não serão adicionadas:\n${linhas}${mais}\n\nCorrija e clique de novo, ou clique em Adicionar mesmo assim.`);
        $("cad-colar-ok").textContent = "Adicionar mesmo assim";
        avisado = true;
      } else if (r.erro) $("cad-colar-aviso").innerHTML = banner("erro", r.erro);
    };
  }

  // ----------------------------------------------------------- telas

  function cabecalho(passo, titulo, explicacao) {
    return `<header class="cabeca"><p class="sobre">Cadastro de Credores no SIGEF${passo ? ` · passo ${passo} de ${PASSOS.length}` : ""}</p>
      <h1 id="cad-titulo">${esc(titulo)}</h1>${explicacao ? `<p class="lead">${esc(explicacao)}</p>` : ""}</header>`;
  }

  // O Voltar sempre à esquerda e o botão principal (verde/azul) sempre à direita, como na janela original.
  const barraDeBotoes = (esquerda, direita) => `<div class="cad-barra"><div>${esquerda || ""}</div><div class="cad-barra-dir">${direita || ""}</div></div>`;
  const voltar = (destino) => botao("cad-voltar", '<svg class="ic"><use href="#i-voltar"/></svg>Voltar', "fantasma", ` data-destino="${destino}"`);

  function ir(tela, dados) {
    if (tela !== "estatisticas") s.retorno = tela;
    if (tela !== "cadastro") s.fimPendente = false;
    s.tela = tela;
    $("cad-corpo").innerHTML = TELAS[tela](dados || {});
    const v = $("cad-voltar");
    if (v) v.onclick = () => ir(v.dataset.destino);
    (LIGAR[tela] || (() => {}))(dados || {});
    marcarPassos();
    document.querySelector(".conteudo").scrollTop = 0;
  }

  function marcarPassos() {
    const atual = PASSO_DA_TELA[s.tela];
    document.querySelectorAll("#cad-passos li").forEach((li, i) => {
      li.classList.toggle("feito", i + 1 < atual);
      li.classList.toggle("atual", i + 1 === atual);
    });
  }

  const TELAS = {
    inicio: () => `${cabecalho(0, "Cadastrar credores no SIGEF", "Este programa cadastra pessoas como credores no SIGEF e grava a conta bancária de cada uma, uma pessoa de cada vez, sem você precisar digitar nada no SIGEF.")}
      <div class="grade2">
        <div class="cartao"><h3><svg class="ic ok"><use href="#i-check"/></svg>Antes de começar, tenha em mãos:</h3>
          <ul class="lista"><li>Seu usuário e sua senha do SIGEF.</li><li>A planilha do Excel com os dados das pessoas, ou os dados para digitar.</li></ul></div>
        <div class="cartao"><h3><svg class="ic"><use href="#i-seta"/></svg>Como funciona:</h3>
          <ol class="lista">${PASSOS.map((p) => `<li>${esc(p)}</li>`).join("")}</ol></div>
      </div>
      ${banner("aviso", "O programa abre o Google Chrome sozinho (o mesmo Chrome das outras automações da Central). Enquanto o cadastro estiver acontecendo, não feche o Chrome. Você pode acompanhar tudo por ele.")}
      ${barraDeBotoes("", botao("cad-comecar", 'Começar <svg class="ic"><use href="#i-seta"/></svg>', "primario grande"))}`,

    login: () => `${cabecalho(1, "Entre no SIGEF")}
      <div id="cad-situacao">${banner("info", "Abrindo o Google Chrome… aguarde.")}</div>
      <div class="cartao"><h3>Faça assim:</h3><ol class="lista">
        <li>Clique na janela do Google Chrome que acabou de abrir.</li>
        <li>Digite seu usuário e sua senha e entre no SIGEF, como você faz todos os dias.</li>
        <li>Volte para esta janela e clique no botão verde Já entrei no SIGEF.</li></ol></div>
      ${barraDeBotoes(voltar("inicio"), botao("cad-abrir", '<svg class="ic"><use href="#i-chrome"/></svg>Abrir o Chrome de novo') + botao("cad-entrei", 'Já entrei no SIGEF <svg class="ic"><use href="#i-seta"/></svg>', "primario grande"))}`,

    origem: () => `${cabecalho(2, "De onde vêm os dados?", "Escolha uma das duas opções.")}
      ${s.refazer ? `${banner("aviso", `Pessoas com erro no último cadastro: ${s.refazer}. Se já corrigiu o problema, você pode refazer só essas pessoas.`)}
        <div class="acao" style="margin:0 0 18px">${botao("cad-refazer", "Refazer as que deram erro", "primario")}</div>` : ""}
      <div class="grade2 cad-cartoes">
        <button class="cartao cad-cartao" type="button" data-ir="planilha"><span class="cad-simbolo">▦</span><b>Planilha do Excel</b>
          <span>Os dados já estão numa planilha. O resultado de cada pessoa é escrito na própria planilha.</span><span class="btn primario">Escolher esta opção</span></button>
        <button class="cartao cad-cartao" type="button" data-ir="digitar"><span class="cad-simbolo">✎</span><b>Digitar ou colar</b>
          <span>Você digita os dados de cada pessoa ou cola uma lista copiada de outro lugar.</span><span class="btn primario">Escolher esta opção</span></button>
      </div>
      ${barraDeBotoes(voltar("login"), "")}`,

    planilha: () => `${cabecalho(2, "Escolha a planilha", "Clique na planilha com os dados das pessoas. Se ela não estiver na lista, clique em Procurar arquivo.")}
      <div id="cad-situacao">${banner("info", "Procurando planilhas abertas no Excel… aguarde.")}</div>
      <div class="grade2">
        <div><h3>Planilhas abertas no Excel</h3><select class="cad-lista" id="cad-pastas" size="7"></select>
          <div class="acao linha" style="margin-top:10px">${botao("cad-procurar", "Procurar arquivo…")}${botao("cad-atualizar", "Atualizar a lista", "fantasma pequeno")}</div></div>
        <div><h3>Aba (folha) da planilha</h3><select class="cad-lista" id="cad-abas" size="7"></select></div>
      </div>
      ${barraDeBotoes(voltar("origem"), botao("cad-continuar", 'Continuar <svg class="ic"><use href="#i-seta"/></svg>', "primario grande", " disabled"))}`,

    colunas: () => {
      const i = s.info;
      const opcoesLetra = (atual) => s.letras.map((l) => `<option${l === atual ? " selected" : ""}>${l}</option>`).join("");
      return `${cabecalho(2, "Confira as colunas da planilha")}
        <p><b>Planilha: ${esc(i.nome)}</b></p>
        ${i.somente_leitura ? banner("erro", "Esta planilha está aberta só para leitura. O programa não conseguirá escrever o resultado. Feche a planilha e abra de novo normalmente.") : ""}
        ${banner(i.detectou ? "sucesso" : "aviso", i.detectou ? `Encontrei os títulos das colunas na linha ${i.primeira - 1}. Confira os exemplos abaixo.` : "Não encontrei os títulos das colunas, então usei as colunas de costume (D, E, F, G e H). Confira os exemplos com bastante atenção.")}
        <div class="dare-tabela cad-mapa"><table><thead><tr><th>Informação</th><th>Coluna</th><th>Título na planilha</th><th>Exemplo (1ª pessoa)</th></tr></thead><tbody>
          ${i.amostra.map((a) => `<tr><td><b>${esc(a.rotulo)}</b></td><td><select class="dare-input curto" data-coluna="${a.campo}">${opcoesLetra(a.letra)}</select></td>
            <td data-titulo="${a.campo}">${esc(a.titulo || "(sem título)")}</td><td data-exemplo="${a.campo}" class="${a.exemplo ? "" : "cad-vazio"}"><b>${esc(a.exemplo || "(vazio)")}</b></td></tr>`).join("")}
        </tbody></table></div>
        <div class="cad-opcoes">
          <label>Começar na linha <input class="dare-input curto" type="number" min="1" id="cad-primeira" value="${i.primeira}"></label>
          <label>Terminar na linha <input class="dare-input curto" type="number" min="1" id="cad-final" value="${i.final}"></label>
          <label>Escrever o resultado na coluna <select class="dare-input curto" id="cad-resultado">${opcoesLetra(s.colunaResultado || "J")}</select></label>
        </div>
        <div id="cad-problema"></div>
        <h3 style="margin-top:22px">Quer conferir cada pessoa antes de gravar?</h3>
        ${escolha("cad-conf", CONFERENCIA, s.conferencia)}
        ${barraDeBotoes(voltar("planilha"), botao("cad-comecar-cad", 'Começar o cadastro <svg class="ic"><use href="#i-seta"/></svg>', "primario grande"))}`;
    },

    digitar: () => `${cabecalho(2, "Digite os dados das pessoas", "Preencha os dados de uma pessoa e clique em Adicionar à lista. Repita para cada pessoa. Quando terminar, clique em Começar o cadastro.")}
      <div class="cad-digitar">
        <div>${formularioPessoa("cad-in")}<button class="btn fantasma" type="button" id="cad-adicionar" style="width:100%;justify-content:center">＋ Adicionar à lista</button></div>
        <div><h3 id="cad-contador">A lista está vazia</h3>
          <div class="dare-tabela selecionavel" id="cad-lista-tabela"></div>
          <div class="acao linha" style="margin-top:10px;justify-content:space-between">${botao("cad-tirar", "Tirar da lista", "fantasma pequeno")}
            <span>${botao("cad-colar", "Colar uma lista…", "fantasma pequeno")} ${botao("cad-arquivo", "Abrir arquivo…", "fantasma pequeno")}</span></div></div>
      </div>
      <h3 style="margin-top:22px">Quer conferir cada pessoa antes de gravar?</h3>
      ${escolha("cad-conf", CONFERENCIA, s.conferencia)}
      ${barraDeBotoes(voltar("origem"), botao("cad-comecar-cad", 'Começar o cadastro <svg class="ic"><use href="#i-seta"/></svg>', "primario grande", " disabled"))}`,

    cadastro: () => {
      const c = s.cad;
      return `${cabecalho(3, c.refazendo ? "Refazendo as pessoas que deram erro…" : "Cadastrando…", "Não feche esta janela nem o Google Chrome. Você pode acompanhar o que o programa está fazendo pela janela do Chrome.")}
        <h3 id="cad-progresso-texto">Preparando…</h3>
        <div class="barra" aria-hidden="true"><div class="barra-cheia" id="cad-barra"></div></div>
        <div id="cad-agora">${banner("info", "Abrindo a tela de credores do SIGEF…")}</div>
        <div id="cad-avisos"></div>
        ${tabela([c.chave, "Nome", "CPF", "Resultado"], "", "cad-resultados")}
        ${barraDeBotoes("", botao("cad-parar", '<svg class="ic"><use href="#i-parar"/></svg>Parar o cadastro', "perigo"))}`;
    },

    resultado: () => {
      const f = s.fim;
      const n = f.contagem;
      const podeRefazer = f.refazer > 0 && !f.interrompido;
      return `${cabecalho(4, f.interrompido ? "Cadastro interrompido" : "Cadastro concluído")}
        <div class="dare-kpis"><div class="dare-kpi ok"><div class="rot">cadastrados</div><div class="val">${n.OK}</div></div>
          <div class="dare-kpi"><div class="rot">já tinham cadastro</div><div class="val" style="color:var(--primaria)">${n.JA}</div></div>
          <div class="dare-kpi"><div class="rot">pulados</div><div class="val">${n.PULADO}</div></div>
          <div class="dare-kpi erro"><div class="rot">com problema</div><div class="val">${n.ERRO}</div></div></div>
        ${f.economia ? banner("info", f.economia) : ""}
        ${n.ERRO ? banner("erro", `Algumas pessoas tiveram problema. Elas estão marcadas com ✖ na lista abaixo${f.modo === "planilha" ? " e na coluna do resultado da planilha, começando com ERRO" : ""}.${podeRefazer ? " Corrija os dados se precisar e clique em Refazer as que deram erro." : " Corrija os dados e cadastre de novo só essas pessoas."}`)
          : !f.interrompido ? banner("sucesso", "Todas as pessoas foram feitas sem problema.") : ""}
        ${tabela([f.modo === "planilha" ? "Linha" : "Nº", "Nome", "CPF", "Resultado"], f.resultados.map((r) => linhaResultado(r.linha, r.status)).join(""))}
        ${barraDeBotoes(botao("cad-registros", '<svg class="ic"><use href="#i-pasta"/></svg>Abrir a pasta de registros', "fantasma pequeno"),
          podeRefazer ? botao("cad-outro", "Fazer outro cadastro") + botao("cad-refazer", `Refazer as que deram erro (${f.refazer})`, "primario grande")
            : botao("cad-outro", 'Fazer outro cadastro <svg class="ic"><use href="#i-seta"/></svg>', "primario grande"))}`;
    },

    estatisticas: () => `${cabecalho(0, "Estatísticas", "Quanto tempo a automação economizou, somando todas as sessões. Esses dados servem para a pesquisa de implantação.")}
      <div class="abas" role="tablist"><button class="aba" type="button" data-escopo="local">Este computador</button><button class="aba" type="button" data-escopo="todos">Todos os computadores</button>
        <span class="nota" id="cad-est-situacao" style="align-self:center;margin-left:12px">Carregando…</span></div>
      <div class="dare-kpis" id="cad-est-placar"></div>
      <h3 style="margin-top:18px">Tempo de um cadastro</h3>
      <div id="cad-est-barras" class="cad-barras"></div>
      <p class="nota" id="cad-est-detalhe"></p>
      <div id="cad-est-aviso"></div>
      <h3 style="margin-top:22px">Tempo manual</h3>
      <p class="nota">Para a pesquisa ficar precisa, cronometre alguns cadastros feitos à mão (o ideal é pelo menos 5 de cada tipo).</p>
      <div class="acao linha">${botao("cad-cronometrar", "Cronometrar um cadastro manual")}${botao("cad-ajustar", "Ajustar a estimativa", "fantasma pequeno")}</div>
      <h3 style="margin-top:22px">Sessões</h3>
      <div id="cad-est-sessoes"></div>
      <h3 style="margin-top:22px">Juntar dados de vários computadores</h3>
      <p class="nota" id="cad-est-pasta" style="white-space:pre-line"></p>
      <div class="acao linha">${botao("cad-pasta-pesquisa", "Pasta da pesquisa…")}${botao("cad-importar", "Trazer arquivos de outro computador…")}${botao("cad-abrir-dados", '<svg class="ic"><use href="#i-pasta"/></svg>Abrir a pasta dos dados', "fantasma pequeno")}</div>
      ${barraDeBotoes(botao("cad-est-voltar", '<svg class="ic"><use href="#i-voltar"/></svg>Voltar'), botao("cad-gerar", "Pacote da pesquisa (Excel)") + '<button class="btn primario grande" type="button" data-relatorio-geral><svg class="ic" aria-hidden="true"><use href="#i-grafico"/></svg>Abrir o Relatório geral</button>')}`,
  };

  // ----------------------------------------------------------- o que cada tela faz

  function situacao(tipo, texto) {
    if ($("cad-situacao")) $("cad-situacao").innerHTML = banner(tipo, texto);
  }

  function ocupar(ids, ocupado) {
    ids.forEach((id) => $(id) && ($(id).disabled = ocupado));
    document.body.style.cursor = ocupado ? "progress" : "";
  }

  async function abrirNavegador() {
    ocupar(["cad-entrei", "cad-abrir"], true);
    situacao("info", "Abrindo o Google Chrome… aguarde.");
    const r = await chamar("abrir_navegador");
    ocupar(["cad-entrei", "cad-abrir"], false);
    if (s.tela !== "login") return;
    if (r.ok) situacao("sucesso", r.texto);
    else situacao("erro", `${r.erro}\n\nClique em Abrir o Chrome de novo.`);
  }

  async function conferirLogin() {
    ocupar(["cad-entrei", "cad-abrir"], true);
    situacao("info", "Conferindo se você já entrou no SIGEF… aguarde.");
    const r = await chamar("conferir_login");
    ocupar(["cad-entrei", "cad-abrir"], false);
    if (s.tela !== "login") return;
    if (!r.ok) return situacao("erro", `${r.erro}\n\nClique em Abrir o Chrome de novo.`);
    if (r.logado) return ir("origem");
    situacao("erro", "Ainda não consegui abrir a tela de credores do SIGEF. Confira se você terminou de entrar com usuário e senha e clique de novo em Já entrei no SIGEF.\n\nSe continuar assim, seu usuário pode não ter permissão na tela de credores (transação 1028).");
  }

  async function carregarPastas(selecionar) {
    $("cad-continuar").disabled = true;
    situacao("info", "Procurando planilhas abertas no Excel… aguarde.");
    const r = await chamar("planilhas");
    if (s.tela !== "planilha") return;
    if (!r.ok) return situacao("erro", r.erro);
    mostrarPastas(r.pastas, selecionar);
  }

  function mostrarPastas(pastas, selecionar) {
    s.pastas = pastas || [];
    $("cad-pastas").innerHTML = s.pastas.map((n, i) => `<option value="${i}">${esc(n)}</option>`).join("");
    $("cad-abas").innerHTML = "";
    $("cad-continuar").disabled = true;
    if (!s.pastas.length) return situacao("aviso", "Nenhuma planilha aberta no Excel. Clique em Procurar arquivo para escolher uma no computador.");
    situacao("info", "Clique na planilha com os dados das pessoas.");
    const indice = s.pastas.indexOf(selecionar) >= 0 ? s.pastas.indexOf(selecionar) : s.pastas.length === 1 ? 0 : -1;
    if (indice >= 0) {
      $("cad-pastas").value = String(indice);
      escolherPasta();
    }
  }

  async function escolherPasta() {
    const indice = $("cad-pastas").value;
    if (indice === "") return;
    $("cad-continuar").disabled = true;
    const r = await chamar("abas", { indice: Number(indice) });
    if (s.tela !== "planilha") return;
    if (!r.ok) return situacao("erro", r.erro);
    $("cad-abas").innerHTML = r.abas.map((a) => `<option>${esc(a)}</option>`).join("");
    if (r.abas.length === 1) {
      $("cad-abas").selectedIndex = 0;
      escolherAba();
    } else situacao("info", "Agora clique na aba (folha) onde estão os dados.");
  }

  function escolherAba() {
    if ($("cad-abas").selectedIndex < 0) return;
    $("cad-continuar").disabled = false;
    situacao("sucesso", "Tudo certo. Clique em Continuar.");
  }

  function colunasDaTela() {
    const c = {};
    document.querySelectorAll("#tela-cadastro [data-coluna]").forEach((sel) => (c[sel.dataset.coluna] = sel.value));
    return c;
  }

  // As mesmas regras de TelaColunas.validar (o Python confere de novo ao começar).
  function validarColunas() {
    const primeira = parseInt($("cad-primeira").value, 10), final = parseInt($("cad-final").value, 10);
    const usadas = Object.values(colunasDaTela());
    let problema = "";
    if (!primeira || !final) problema = "Informe os números da primeira e da última linha.";
    else if (primeira > final) problema = "A linha de começo precisa ser menor que a linha do fim.";
    else if (usadas.includes($("cad-resultado").value)) problema = "A coluna do resultado não pode ser uma das colunas com os dados. Escolha uma coluna vazia.";
    $("cad-problema").innerHTML = problema ? banner("erro", problema) : "";
    $("cad-comecar-cad").disabled = !!problema;
    return !problema;
  }

  async function atualizarAmostra() {
    validarColunas();
    const primeira = parseInt($("cad-primeira").value, 10);
    if (!primeira) return;
    const r = await chamar("amostra", { colunas: colunasDaTela(), primeira });
    if (!r.ok || s.tela !== "colunas") return;
    r.amostra.forEach((a) => {
      const t = document.querySelector(`#tela-cadastro [data-titulo="${a.campo}"]`);
      const e = document.querySelector(`#tela-cadastro [data-exemplo="${a.campo}"]`);
      t.textContent = a.titulo || "(sem título)";
      e.innerHTML = `<b>${esc(a.exemplo || "(vazio)")}</b>`;
      e.className = a.exemplo ? "" : "cad-vazio";
    });
  }

  function pintarLista() {
    if (!$("cad-lista-tabela")) return;
    const n = s.lotes.length;
    if (s.selecionado !== null && s.selecionado >= n) s.selecionado = null;
    $("cad-contador").textContent = n === 0 ? "A lista está vazia" : n === 1 ? "1 pessoa na lista" : `${n} pessoas na lista`;
    $("cad-lista-tabela").innerHTML = `<table><thead><tr><th>CPF</th><th>Nome</th><th>Banco</th><th>Agência</th><th>Conta</th></tr></thead><tbody>${s.lotes
      .map((l, i) => `<tr data-i="${i}"${i === s.selecionado ? ' class="sel"' : ""}><td class="mono">${esc(l.cpf_formatado)}</td><td>${esc(l.nome)}</td><td>${esc(l.banco_nome || l.banco)}</td><td class="mono">${esc(l.agencia)}</td><td class="mono">${esc(l.conta)}</td></tr>`)
      .join("") || '<tr><td colspan="5" class="vazio">Ninguém na lista ainda.</td></tr>'}</tbody></table>`;
    $("cad-comecar-cad").disabled = n === 0;
  }

  async function adicionar(forcar = false) {
    const r = await chamar("adicionar", { valores: lerFormulario("cad-in"), forcar });
    const raiz = $("tela-cadastro");
    if (r.confirmar_cpf) {
      const decisao = await recado("Confira o CPF", `O CPF ${r.lote.cpf_formatado} parece ter algum número errado. Confira no documento da pessoa.`, "atencao",
        [["Adicionar mesmo assim", true, "fantasma"], ["Corrigir o CPF", false, "primario"]]);
      if (decisao) return adicionar(true);
      return $("cad-in-cpf").focus();
    }
    if (!r.ok) return r.erros ? marcarErros(raiz, "cad-in", r) : recado("Não deu para adicionar", r.erro || "?", "erro");
    s.lotes = r.lotes;
    CAMPOS.forEach((c) => ($(`cad-in-${c}`).value = ""));
    raiz.querySelectorAll(".cad-campo").forEach((cx) => {
      cx.classList.remove("invalido", "valido");
      cx.querySelector(".dica").textContent = (s.dicas || {})[cx.dataset.campo] || "";
    });
    pintarLista();
    $("cad-in-cpf").focus();
  }

  async function comecarCadastro(dados) {
    s.conferencia = escolhido("cad-conf") || s.conferencia;
    const r = await chamar("comecar", { ...dados, manual: s.conferencia === "manual" });
    if (!r.ok) return recado("Não deu para começar", r.erro, "erro");
    s.cadastrando = true;
    s.cad = { modo: r.modo, manual: r.manual, refazendo: r.refazendo, chave: r.chave, total: 0, atual: 0, avisos: [] };
    ponto(true);
    ir("cadastro");
  }

  const LIGAR = {
    inicio: () => ($("cad-comecar").onclick = () => ir("login")),
    login: () => {
      $("cad-entrei").onclick = conferirLogin;
      $("cad-abrir").onclick = abrirNavegador;
      abrirNavegador();
    },
    origem: () => {
      document.querySelectorAll("#tela-cadastro [data-ir]").forEach((b) => (b.onclick = () => ir(b.dataset.ir)));
      if ($("cad-refazer")) $("cad-refazer").onclick = () => comecarCadastro({ refazer: true });
    },
    planilha: () => {
      $("cad-pastas").onchange = escolherPasta;
      $("cad-abas").onchange = escolherAba;
      $("cad-atualizar").onclick = () => carregarPastas();
      $("cad-procurar").onclick = async () => {
        situacao("info", "Abrindo a planilha no Excel… aguarde.");
        const r = await chamar("procurar_planilha");
        if (r.cancelou) return situacao("info", "Clique na planilha com os dados das pessoas.");
        if (!r.ok) return situacao("erro", r.erro);
        mostrarPastas(r.pastas, r.selecionar);
      };
      $("cad-continuar").onclick = async () => {
        const aba = $("cad-abas").value;
        $("cad-continuar").disabled = true;
        situacao("info", "Lendo a planilha… aguarde.");
        const r = await chamar("ler_planilha", { aba });
        if (!r.ok) {
          $("cad-continuar").disabled = false;
          return situacao("erro", r.erro);
        }
        s.info = r;
        s.letras = r.letras;
        ir("colunas");
      };
      carregarPastas();
    },
    colunas: () => {
      let espera = null;
      document.querySelectorAll("#tela-cadastro [data-coluna]").forEach((sel) => (sel.onchange = atualizarAmostra));
      $("cad-primeira").addEventListener("input", () => {
        clearTimeout(espera);
        espera = setTimeout(atualizarAmostra, 400);
      });
      $("cad-final").addEventListener("input", validarColunas);
      $("cad-resultado").onchange = () => {
        s.colunaResultado = $("cad-resultado").value;
        validarColunas();
      };
      $("cad-comecar-cad").onclick = () => validarColunas() && comecarCadastro({
        modo: "planilha", colunas: colunasDaTela(), primeira: $("cad-primeira").value, final: $("cad-final").value, coluna_resultado: $("cad-resultado").value,
      });
      validarColunas();
    },
    digitar: () => {
      ligarFormulario($("tela-cadastro"), "cad-in", () => adicionar());
      $("cad-adicionar").onclick = () => adicionar();
      $("cad-lista-tabela").onclick = (e) => {
        const tr = e.target.closest("tr[data-i]");
        if (!tr) return;
        s.selecionado = Number(tr.dataset.i);
        pintarLista();
      };
      $("cad-tirar").onclick = async () => {
        if (s.selecionado === null) return recado("Tirar da lista", "Primeiro clique na pessoa que você quer tirar da lista.");
        const r = await chamar("remover", { indice: s.selecionado });
        s.selecionado = null;
        if (r.ok) s.lotes = r.lotes;
        pintarLista();
      };
      $("cad-colar").onclick = colarLista;
      $("cad-arquivo").onclick = async () => {
        const r = await chamar("abrir_lista");
        if (r.cancelou) return;
        if (!r.ok) return recado("Não consegui abrir o arquivo", r.erro, "erro");
        s.lotes = r.lotes;
        pintarLista();
        if (r.ignoradas && r.ignoradas.length) {
          const linhas = r.ignoradas.slice(0, 8).map((i) => `Linha ${i.linha}: ${i.motivo}`).join("\n");
          recado("Algumas linhas ficaram de fora", `${r.adicionadas} pessoa(s) adicionada(s). Estas linhas têm problema e não entraram na lista:\n\n${linhas}`, "atencao");
        }
      };
      $("cad-comecar-cad").onclick = () => comecarCadastro({ modo: "lotes" });
      pintarLista();
      chamar("lista").then((r) => {
        if (r.ok && s.tela === "digitar") {
          s.lotes = r.lotes;
          pintarLista();
        }
      });
      setTimeout(() => $("cad-in-cpf") && $("cad-in-cpf").focus(), 100);
    },
    cadastro: () => {
      $("cad-parar").onclick = () => {
        chamar("parar");
        $("cad-parar").textContent = "Parando depois desta pessoa…";
        $("cad-parar").disabled = true;
      };
    },
    resultado: () => {
      $("cad-registros").onclick = () => chamar("abrir_registros");
      $("cad-outro").onclick = () => ir("origem");
      if ($("cad-refazer")) $("cad-refazer").onclick = () => comecarCadastro({ refazer: true });
    },
    estatisticas: () => {
      document.querySelectorAll("#tela-cadastro [data-escopo]").forEach((b) => (b.onclick = () => carregarEstatisticas(b.dataset.escopo)));
      $("cad-est-voltar").onclick = () => ir(s.fim && s.retorno === "cadastro" ? "resultado" : s.retorno || "inicio");
      $("cad-cronometrar").onclick = cronometrar;
      $("cad-ajustar").onclick = ajustarEstimativa;
      $("cad-pasta-pesquisa").onclick = escolherPastaPesquisa;
      $("cad-importar").onclick = async () => {
        const r = await chamar("importar");
        if (r.cancelou) return;
        if (!r.ok) return recado("Não consegui juntar os dados", r.erro, "erro");
        await recado("Dados juntados", r.texto, "ok");
        carregarEstatisticas("todos");
      };
      $("cad-abrir-dados").onclick = () => chamar("abrir_dados");
      $("cad-gerar").onclick = async () => {
        const b = $("cad-gerar");
        b.disabled = true;
        b.textContent = "Gerando…";
        const r = await chamar("relatorio", { escopo: s.escopo });
        b.disabled = false;
        b.textContent = "Pacote da pesquisa (Excel)";
        if (!r.ok) return recado("Não consegui gerar o relatório", r.erro, "erro");
        recado("Pacote pronto", `O pacote da pesquisa foi salvo em:\n${r.pasta}\n\n• dados_pesquisa.xlsx: planilha com todos os números\n• dados_brutos.jsonl: dados para juntar com outros computadores\n\nPara apresentar, use o Relatório geral (botão ao lado): ele junta o Cadastro com as outras automações.`, "ok");
      };
      carregarEstatisticas(null);
    },
  };

  // ----------------------------------------------------------- estatísticas

  async function carregarEstatisticas(escopo) {
    $("cad-est-situacao").textContent = "Carregando…";
    const r = await chamar("estatisticas", { escopo });
    if (s.tela !== "estatisticas") return;
    if (!r.ok) return ($("cad-est-situacao").textContent = r.erro);
    s.escopo = r.escopo;
    s.estimativa = r.estimativa;
    s.pastaPesquisa = r.pasta_pesquisa || "";
    document.querySelectorAll("#tela-cadastro [data-escopo]").forEach((b) => b.classList.toggle("ativa", b.dataset.escopo === r.escopo));
    $("cad-est-situacao").textContent = r.situacao;
    $("cad-est-placar").innerHTML = [
      [r.feitos, "cadastros concluídos", "ok"], [r.economizado, "de tempo economizado", "ok"],
      [r.media_manual, "tempo médio à mão", ""], [r.media_automacao, "tempo médio com a automação", ""],
    ].map(([v, rot, tom]) => `<div class="dare-kpi ${tom}"><div class="rot">${esc(rot)}</div><div class="val">${esc(v)}</div></div>`).join("");
    const maior = Math.max(r.media_manual_s, r.media_automacao_s, 1);
    $("cad-est-barras").innerHTML = [["À mão", r.media_manual_s, r.media_manual, "#8C9AB0"], ["Com a automação", r.media_automacao_s, r.feitos ? r.media_automacao : "sem dados", "var(--verde)"]]
      .map(([nome, seg, txt, cor]) => `<div class="cad-barra-linha"><span>${nome}</span><div class="cad-trilho"><i style="width:${Math.max(1, (seg / maior) * 100)}%;background:${cor}"></i></div><b>${esc(txt)}</b></div>`).join("");
    $("cad-est-detalhe").textContent = r.detalhe;
    $("cad-est-aviso").innerHTML = r.aviso_manual ? banner("aviso", r.aviso_manual) : "";
    $("cad-est-sessoes").innerHTML = tabela(["Data", "Computador", "Pessoas", "Cadastrados", "Erros", "Automação", "Economia"],
      r.sessoes.map((l) => `<tr class="${l.tom === "OK" ? "ok" : l.tom === "ERRO" ? "erro" : ""}"><td>${esc(l.data)}</td><td>${esc(l.computador)}</td><td class="num">${l.pessoas}</td><td class="num">${l.feitos}</td><td class="num situ">${l.erros}</td><td class="num">${esc(l.automacao)}</td><td class="num">${esc(l.economia)}</td></tr>`).join("")
      || '<tr><td colspan="7" class="vazio">Ainda não há sessões registradas.</td></tr>', "baixa");
    mostrarPastaPesquisa(s.pastaPesquisa);
  }

  function mostrarPastaPesquisa(pasta) {
    $("cad-est-pasta").textContent = pasta
      ? `Pasta da pesquisa: ${pasta}\nCada computador grava os seus dados nela automaticamente ao final de cada sessão.`
      : "Nenhuma pasta da pesquisa escolhida. Escolha uma pasta da rede para juntar os dados de todos os computadores automaticamente, ou traga os arquivos de cada computador (pen drive ou e-mail).";
  }

  async function escolherPastaPesquisa() {
    if (s.pastaPesquisa) {
      const decisao = await recado("Pasta da pesquisa", `A pasta atual é:\n${s.pastaPesquisa}`, "info",
        [["Parar de usar", "parar", "fantasma pequeno"], ["Escolher outra", "outra", "fantasma"], ["Manter", null, "primario"]]);
      if (decisao === null) return;
      if (decisao === "parar") {
        await chamar("pasta_pesquisa", { acao: "parar" });
        return carregarEstatisticas(null);
      }
    }
    const r = await chamar("pasta_pesquisa", { acao: "escolher" });
    if (r.cancelou) return;
    if (!r.ok) return recado("Pasta da pesquisa", r.erro, "erro");
    if (r.aviso) await recado("Não consegui gravar na pasta", r.aviso, "erro");
    carregarEstatisticas(null);
  }

  function cronometrar() {
    let inicio = null, relogio = null;
    const mmss = (seg) => `${String(Math.floor(seg / 60)).padStart(2, "0")}:${String(Math.floor(seg % 60)).padStart(2, "0")}`;
    const m = modal(`<h2 style="margin:0">Cronometrar um cadastro feito à mão</h2>
      <ol class="lista"><li>Escolha o tipo de cadastro que você vai fazer.</li><li>Clique em Começar e faça o cadastro no SIGEF do jeito de sempre, à mão.</li><li>Quando terminar, volte aqui e clique em Terminei.</li></ol>
      ${escolha("cad-tipo", TIPOS_CADASTRO, "novo")}
      <div class="cad-relogio" id="cad-mostrador">00:00</div>
      <p class="nota" id="cad-crono-sit" style="text-align:center">O cronômetro ainda não começou.</p>
      <div class="botoes" style="justify-content:space-between"><button class="btn fantasma" type="button" id="cad-crono-cancelar">Cancelar</button>
      <button class="btn primario" type="button" id="cad-crono-ok">Começar</button></div>`, () => cancelar());
    const cancelar = () => {
      clearInterval(relogio);
      m.remove();
    };
    $("cad-crono-cancelar").onclick = cancelar;
    $("cad-crono-ok").onclick = async () => {
      if (inicio === null) {
        inicio = performance.now();
        $("cad-crono-sit").textContent = "Contando… faça o cadastro no SIGEF e depois clique em Terminei.";
        $("cad-crono-ok").textContent = "Terminei";
        relogio = setInterval(() => ($("cad-mostrador").textContent = mmss((performance.now() - inicio) / 1000)), 500);
        return;
      }
      clearInterval(relogio);
      const segundos = (performance.now() - inicio) / 1000;
      const tipo = escolhido("cad-tipo") || "novo";
      m.remove();
      if (segundos < 20 || segundos > 1800) {
        const guarda = await recado("Confira o tempo", `O tempo medido foi ${mmss(segundos)}. Parece muito ${segundos < 20 ? "curto" : "longo"} para um cadastro. Quer guardar mesmo assim?`, "atencao",
          [["Não guardar", false, "fantasma"], ["Guardar mesmo assim", true, "primario"]]);
        if (!guarda) return;
      }
      const r = await chamar("tempo_manual", { caminho: tipo, segundos });
      if (!r.ok) return recado("Não consegui guardar", r.erro, "erro");
      await recado("Tempo guardado", r.texto, "ok");
      carregarEstatisticas(s.escopo);
    };
  }

  function ajustarEstimativa() {
    const est = s.estimativa || { novo: "5:00", existente: "3:00" };
    const m = modal(`<h2 style="margin:0">Quanto tempo leva um cadastro feito à mão?</h2>
      <p class="nota" style="margin:0">Use minutos. Exemplos: 5  ou  4:30  (4 minutos e 30 segundos). Este valor só é usado enquanto ninguém tiver cronometrado cadastros manuais.</p>
      ${TIPOS_CADASTRO.map(([k, t, d]) => `<div class="dare-campo cad-campo" data-campo="${k}"><label for="cad-est-${k}">${esc(t)}</label><input class="dare-input curto" id="cad-est-${k}" value="${esc(est[k] || "")}"><div class="dica">${esc(d)}</div></div>`).join("")}
      <div class="botoes" style="justify-content:space-between"><button class="btn fantasma" type="button" id="cad-ajuste-cancelar">Cancelar</button>
      <button class="btn primario" type="button" id="cad-ajuste-ok">Salvar</button></div>`, () => m.remove());
    $("cad-ajuste-cancelar").onclick = () => m.remove();
    $("cad-ajuste-ok").onclick = async () => {
      const r = await chamar("estimativa", { valores: { novo: $("cad-est-novo").value, existente: $("cad-est-existente").value } });
      if (r.ok) {
        m.remove();
        return carregarEstatisticas(s.escopo);
      }
      Object.entries(r.erros || {}).forEach(([k, msg]) => {
        const cx = m.querySelector(`[data-campo="${k}"]`);
        cx.classList.add("invalido");
        cx.querySelector(".dica").textContent = msg;
      });
    };
  }

  // ----------------------------------------------------------- eventos do cadastro

  function fecharPergunta() {
    if (s.aberta) {
      s.aberta.remove();
      s.aberta = null;
    }
  }

  const eventos = {
    cad_inicio(e) {
      if (!s.cad) return;
      s.cad.total = e.total;
      if ($("cad-progresso-texto")) $("cad-progresso-texto").textContent = `Pessoa ${e.atual} de ${e.total}`;
      if ($("cad-barra")) $("cad-barra").style.width = `${((e.atual - 1) / Math.max(1, e.total)) * 100}%`;
      if ($("cad-agora")) $("cad-agora").innerHTML = banner("info", `Agora: ${e.lote.nome || "(sem nome)"}   —   CPF ${e.lote.cpf_formatado}`);
      linhaNaTabela([e.chave, e.lote.nome, e.lote.cpf_formatado, "… cadastrando"], "AGORA");
    },
    cad_resultado(e) {
      if (!s.cad) return;
      s.cad.atual += 1;
      if ($("cad-barra")) $("cad-barra").style.width = `${(s.cad.atual / Math.max(1, s.cad.total)) * 100}%`;
      linhaNaTabela(e.linha, e.status);
    },
    cad_aviso(e) {
      if (!s.cad || s.cad.avisos.includes(e.texto)) return;
      s.cad.avisos.push(e.texto);
      if ($("cad-avisos")) $("cad-avisos").innerHTML = banner("aviso", s.cad.avisos.join("\n"));
    },
    cad_conferir(e) {
      fecharPergunta();
      conferir(e);
    },
    cad_corrigir(e) {
      fecharPergunta();
      corrigir(e);
    },
    cad_pergunta_fim: fecharPergunta,
    cad_fim(e) {
      s.cadastrando = false;
      ponto(false);
      fecharPergunta();
      s.fim = e;
      if (!e.interrompido) s.refazer = e.refazer || 0;
      if (e.modo === "lotes" && !e.erro) s.lotes = [];
      if (e.erro) {
        recado("O cadastro parou", `${e.erro}\n\nAs pessoas que já foram feitas estão na lista do resultado.`, "erro");
        return ir(e.navegador ? "login" : "resultado");
      }
      if (e.interrompido || !e.refazer) return ir("resultado");
      oferecerRefazer(e);
    },
  };

  function linhaNaTabela(linha, status) {
    const corpo = document.querySelector("#tela-cadastro .cad-resultados tbody");
    if (!corpo) return;
    const chave = CSS.escape(String(linha[0]));
    const html = linhaResultado(linha, status);
    const atual = corpo.querySelector(`tr[data-chave="${chave}"]`);
    if (atual) atual.outerHTML = html;
    else corpo.insertAdjacentHTML("beforeend", html);
    const nova = corpo.querySelector(`tr[data-chave="${chave}"]`);
    if (nova && nova.scrollIntoView) nova.scrollIntoView({ block: "nearest" });
  }

  /* Fim com erros: fica no passo 3 e oferece refazer só os que falharam (como a janela original). */
  function oferecerRefazer(e) {
    if (s.tela !== "cadastro") ir("cadastro");
    $("cad-titulo").textContent = "Cadastro terminado";
    $("cad-progresso-texto").textContent = `Pessoas feitas: ${e.processados}   ·   Com problema: ${e.refazer}`;
    $("cad-barra").style.width = "100%";
    const dica = e.modo === "planilha" ? " Se o problema era nos dados, corrija na planilha antes: as linhas são lidas de novo."
      : e.manual ? " Na conferência, use Corrigir os dados se algo estiver errado." : "";
    $("cad-agora").innerHTML = banner("erro", `As pessoas com erro (marcadas com ✖ na lista) ficaram guardadas. Clique em Refazer as que deram erro para tentar de novo só com elas.${dica}`);
    document.querySelector("#tela-cadastro .cad-barra-dir").innerHTML =
      botao("cad-ver", "Ver o resultado") + botao("cad-refazer", `Refazer as que deram erro (${e.refazer})`, "primario grande");
    $("cad-ver").onclick = () => ir("resultado");
    $("cad-refazer").onclick = () => comecarCadastro({ refazer: true });
    s.fimPendente = true;
  }

  // ----------------------------------------------------------- ajuda, ponto na barra
  // O tamanho da letra é o da Central (botão Acessibilidade e Ctrl + / Ctrl −), igual em todas as automações.

  function ajuda() {
    recado("Ajuda", `${AJUDA[s.tela] || "Siga as instruções escritas na tela e clique no botão verde."}\n\nDica: para letras maiores ou alto contraste, use o botão Acessibilidade no alto da janela (ou Ctrl + e Ctrl −).`);
  }

  function ponto(ligado) {
    const botaoModulo = document.querySelector('.modulo[data-modulo="cadastro"]');
    if (!botaoModulo) return;
    let el = botaoModulo.querySelector(".rodando");
    if (ligado && !el) {
      el = document.createElement("i");
      el.className = "rodando";
      el.title = "Rodando";
      botaoModulo.appendChild(el);
    } else if (!ligado && el) el.remove();
  }

  // ----------------------------------------------------------- partida

  async function mostrar() {
    s.ativo = true;
    $("tela-cadastro").hidden = false;
    if (s.iniciado) return marcarPassos();
    s.iniciado = true;
    const r = await chamar("estado");
    if (!r.ok) {
      s.iniciado = false;
      $("cad-corpo").innerHTML = banner("erro", `Não consegui carregar o módulo: ${r.erro}`);
      return;
    }
    s.versao = r.versao;
    s.dicas = r.dicas;
    s.conferencia = r.conferencia;
    s.refazer = r.refazer;
    s.lotes = r.lotes;
    s.colunaResultado = r.coluna_resultado;
    s.cadastrando = r.cadastrando;
    document.querySelectorAll("[data-cad-versao]").forEach((el) => (el.textContent = r.versao));
    ir("inicio");
  }

  function esconder() {
    s.ativo = false;
  }

  function ligar(ganchos) {
    g = ganchos;
    g.registrarEventos(eventos);
    $("cad-ajuda").onclick = ajuda;
    $("cad-estatisticas").onclick = () => {
      if (s.cadastrando) return recado("Espere o cadastro terminar", "As estatísticas podem ser vistas quando o cadastro terminar.");
      if (s.tela !== "estatisticas") ir("estatisticas");
    };
    document.addEventListener("keydown", (e) => {
      if (!s.ativo || document.querySelector(".modal:not([hidden])")) return;
      if (e.key === "F1") {
        e.preventDefault();
        ajuda();
      }
    });
  }

  window.lbaCadastro = {
    ligar,
    mostrar,
    esconder,
    get rodando() { return s.cadastrando; },
    get tela() { return s.tela; },
  };
})();
