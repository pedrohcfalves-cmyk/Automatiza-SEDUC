/* Módulo Anexar Documentos — o programa "Anexar Documentos" 1.6 (regularização de parcelas) na Central.
 *
 * As mesmas telas da janela original (anexar/janela/): Início, Fazer um processo (ao vivo),
 * Configurações, Tempos e planilhas (os números ficam no Relatório geral), Ajuda e licença e o Modo treino.
 * O tamanho da letra é o da Central (botão Acessibilidade), igual para todas as automações.
 *
 * A automação roda num processo à parte (o executor); cada pergunta chega como um PEDIDO
 * (botoes, formulario, conferencia, configuracoes) que esta página desenha, e a resposta é o
 * botão clicado (e o que foi preenchido). A página lê o que aconteceu pela porta "novidades",
 * como a janela original lia o núcleo. Tudo passa por api.anexar(acao, dados), que chega em
 * janela/modulo_anexar.py.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const guardar = (chave, valor) => { try { localStorage.setItem(chave, valor); } catch (e) { /* sem armazenamento */ } };
  const lembrar = (chave) => { try { return localStorage.getItem(chave); } catch (e) { return null; } };

  // ----------------------------------------------------------- formatos (anexar/janela/formatos.py)

  const F = {
    numeroBr(valor, casas = 0) {
      return Number(valor || 0).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
    },
    duracao(segundos) {
      if (segundos === null || segundos === undefined || isNaN(Number(segundos))) return "—";
      const s = Math.max(0, Math.round(Number(segundos)));
      if (s < 60) return `${s} s`;
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
      if (h > 0) return m ? `${h} h ${m} min` : `${h} h`;
      return r && m < 10 ? `${m} min ${r} s` : `${m} min`;
    },
    horas(segundos) {
      const h = (segundos || 0) / 3600;
      return h >= 10 ? `${F.numeroBr(h)} h` : `${F.numeroBr(h, 1)} h`;
    },
    porcentagem: (parte, todo) => (todo ? `${F.numeroBr((parte / todo) * 100)}%` : "—"),
    INVALIDO: -1,
    // '1.105,50', '1105,5' ou '110550' (os 2 últimos números são os centavos). null = vazio.
    centavos(texto) {
      const t = String(texto ?? "").replace("R$", "").trim();
      if (!t) return null;
      if (/^\d+$/.test(t)) return parseInt(t, 10);
      if (!/^[\d.,]+$/.test(t)) return F.INVALIDO;
      const n = parseFloat(t.replace(/\./g, "").replace(",", "."));
      return isNaN(n) ? F.INVALIDO : Math.round(n * 100);
    },
    reais: (c) => `${Math.floor(c / 100).toLocaleString("pt-BR")},${String(c % 100).padStart(2, "0")}`,
  };

  // O registro técnico: o mesmo jeito de classificar as linhas da janela original.
  const SEM_ENFEITE = /^[\s✅⚠️❌⏭️↩️➡️🔄💾▶️⏳👉]+/u;
  const LINHA_DO_RESUMO = /^\s*(✅|⚠️?)\s*\d+\)/u;
  function classificar(texto) {
    if (texto.includes("❌")) return "falha";
    if (/^\s*👉/u.test(texto)) return "instrucao";
    if (texto.includes("⚠")) return "aviso";
    if (texto.includes("✅")) return "ok";
    if (texto.includes("⏭") || texto.includes("↩")) return "pulado";
    return "";
  }

  const ETAPAS = ["SEI1", "CE", "NL", "PP", "OB", "BAIXAR", "SEI"];
  const PASSOS = [["SEI1", "Dados", "Conferir no SEI"], ["CE", "CE", "Despesa Certificada"], ["NL", "NL", "Nota de Lançamento"],
    ["PP", "PP", "Preparação de Pagamento"], ["OB", "OB", "Ordem Bancária"], ["BAIXAR", "Baixar", "Documentos do SIGEF"], ["SEI", "SEI", "Colocar no processo"]];
  const NOME_ETAPA = {
    LOGIN: "Entrar no SEI e no SIGEF", SEI1: "Dados do processo (SEI)", CE: "CE — Despesa Certificada", NL: "NL — Nota de Lançamento",
    PP: "PP — Preparação de Pagamento", OB: "OB — Ordem Bancária", BAIXAR: "Baixar os documentos do SIGEF", SEI: "Colocar os documentos no processo (SEI)",
  };
  const ICONE_ATIVIDADE = { ok: "✓", aviso: "⚠", falha: "✖", pulado: "↩", etapa: "▶", nota: "•" };
  const AJUDA = {
    inicio: ["Esta é a tela de entrada.", "Clique no botão azul grande para fazer um processo.", "Se ficou um processo pela metade, aparece um aviso amarelo com o botão Continuar.", "Para aumentar a letra, use o botão Acessibilidade no alto da janela (ou Ctrl + e Ctrl −): vale para o aplicativo inteiro."],
    processo: ["Clique em Começar. O Chrome do programa abre sozinho.", "Quando o quadro ficar amarelo, é a sua vez: leia e clique em um dos botões.",
      "Os dados do processo aparecem numa tabela só, já preenchida com o que foi usado da última vez. Mude o que precisar e clique em Conferir os dados.",
      "Enquanto o programa trabalha, o quadro mostra o que ele está fazendo agora, e a tabela ao lado mostra as NL, PP e OB que vão saindo. Não mexa no Chrome dele.",
      "Para parar, use o botão vermelho Parar o programa. Nada do que foi feito se perde."],
    configuracoes: ["Escolha a automação nas abas (Global, CE, NL, PP, OB).", "Na tabela, a coluna Valor é o que o programa vai preencher; a coluna Padrão mostra o valor original.",
      "Mude o que precisar e clique em Salvar. Voltar ao padrão desfaz todas as mudanças daquela automação.", "O que estiver em amarelo precisa ser arrumado antes de fazer um processo."],
    estatisticas: ["Os números (quanto foi feito, quanto tempo levou e quanto foi economizado) ficam no Relatório geral, junto com as outras automações: clique em Abrir o Relatório geral.",
      "Aqui você digita quantos minutos leva fazer cada item à mão e clica em Salvar estimativas: é a base do tempo economizado.", "Para o estudo, baixe as planilhas do período escolhido."],
    ajuda: ["Aqui ficam o passo a passo, as novidades da versão e a licença.", "O tamanho da letra e o alto contraste ficam no botão Acessibilidade, no alto da janela; as cores (claro ou escuro) seguem as da Central."],
  };
  const TITULOS = { inicio: "Início", processo: "Fazer um processo", configuracoes: "Configurações", estatisticas: "Tempos e planilhas", ajuda: "Ajuda e licença" };
  const PASSO_A_PASSO = [
    "Clique em <b>Fazer um processo</b> e depois em <b>Começar</b>. O Chrome do programa abre sozinho.",
    "No Chrome do programa, <b>entre no SEI e no SIGEF</b> com o seu usuário e senha. Volte para esta janela e clique em <b>Continuar</b>.",
    "Confira a <b>tabela dos dados do processo</b>: ela já vem com o que foi usado da última vez. Mude o que precisar, preencha os lançamentos e clique em <b>Conferir os dados</b>.",
    "Leia o quadro <b>Confira os dados</b> e clique em <b>Começar no SIGEF</b>.",
    "Enquanto o programa trabalha, <b>não mexa no Chrome dele</b>. A tela mostra ao vivo o que está sendo feito e toca um aviso quando precisar de você.",
    "No fim, <b>confira no SEI e assine</b>. O programa não assina nada.",
  ];
  const NOVIDADES = [
    ["Central", "O Anexar Documentos agora é um módulo da Central de Automações: mesmas telas e botões, o mesmo Chrome das outras automações (um login só), o Ano do SIGEF do menu do topo e uma automação por vez. Na Central ele se chama Gerar pagamento, e os números dele estão no Relatório geral."],
    ["1.6.0", "Janela de programa de verdade, separada do Chrome (que continua sendo usado só pela automação para entrar no SEI e no SIGEF). Uma instalação só, para todos os computadores."],
    ["1.5.0", "Um clique só em qualquer computador: instala sozinho o Python e as peças que faltam. Pasta mais enxuta e JSONs de configuração de volta ao padrão."],
    ["1.4.0", "Dados do processo numa tabela só (todos de uma vez), só botões (nada de digitar letras), tela que mostra ao vivo o que o programa está fazendo, Configurações em tabelas e letra ajustável."],
    ["1.3.0", "Pacote para instalar em outros computadores e uma lista “Este computador” que avisa se faltar o Chrome."],
    ["1.2.0", "Tela nova, pensada para ler e clicar com facilidade: letras maiores, uma pergunta por vez, botões grandes, aviso sonoro e Modo treino. Estatísticas e Relatório do mês."],
    ["1.1.0", "Primeira versão do aplicativo com janela própria."],
  ];

  let g = null; // ganchos da Central
  const s = {
    ativo: false,
    iniciado: false,
    tela: "inicio",
    info: null, // estado inicial (versão, retomar, problemas…)
    som: lembrar("anx-som") !== "0",
    periodo: lembrar("anx-periodo") || "tudo",
    anonimo: lembrar("anx-anonimo") !== "0",
    abaConfig: lembrar("anx-aba-config") || "global",
    quantidade: 100,
    // a execução, como o EstadoProcesso da janela original
    seq: 0,
    rodando: false,
    abrindo: false,
    treino: false,
    pergunta: null,
    desenhadaPara: null,
    respondendo: false,
    etapa: null,
    etapaInfo: null,
    andamento: null,
    sessao: null,
    atividades: [],
    etapasComErro: new Set(),
    estados: {},
    parcial: "",
    registro: [],
    ultimoCiclo: null,
    encerrado: null,
    lendo: false,
    configModal: null,
  };

  // ----------------------------------------------------------- Python

  async function chamar(acao, dados = {}) {
    try {
      const api = g && g.api();
      if (!api || !api.anexar) return { ok: false, erro: "A janela ainda está carregando. Tente de novo." };
      return (await api.anexar(acao, dados)) || { ok: false, erro: "sem resposta" };
    } catch (erro) {
      return { ok: false, erro: String(erro && erro.message ? erro.message : erro) };
    }
  }

  // ----------------------------------------------------------- peças

  const banner = (tipo, html) => `<div class="dare-banner ${tipo}"><span class="txt">${html}</span></div>`;
  const etiqueta = (texto, tom) => `<span class="anx-etiqueta ${tom || ""}">${esc(texto)}</span>`;
  const cabecalho = (titulo, texto) => `<header class="cabeca"><p class="sobre">Gerar pagamento</p><h1 id="anx-titulo">${esc(titulo)}</h1><p class="lead">${texto}</p></header>`;
  const cartao = (titulo, corpo, extra = "") => `<div class="cartao anx-cartao ${extra}"><h3>${titulo}</h3>${corpo}</div>`;
  function grade(cabecalhoCols, linhas, opcoes = {}) {
    const direita = new Set(opcoes.direita || []);
    const th = cabecalhoCols.length ? `<thead><tr>${cabecalhoCols.map((c, i) => `<th class="${direita.has(i) ? "num" : ""}">${esc(c)}</th>`).join("")}</tr></thead>` : "";
    const tr = linhas.map((l) => {
      const tom = l.tom || "";
      const celulas = (l.celulas || l).map((c, i) => `<td class="${direita.has(i) ? "num" : ""}${i === 0 && opcoes.negrito ? " forte" : ""}">${c}</td>`).join("");
      return `<tr class="${tom}">${celulas}</tr>`;
    }).join("");
    const rodape = opcoes.rodape ? `<tfoot><tr>${opcoes.rodape.map((c, i) => `<td class="${direita.has(i) ? "num" : ""}">${esc(c)}</td>`).join("")}</tr></tfoot>` : "";
    return `<div class="dare-tabela anx-grade"><table>${th}<tbody>${tr}</tbody>${rodape}</table></div>`;
  }
  const celulaNumero = (valor, fazendo) => (valor ? `<b class="anx-feito">${esc(valor)}</b>` : fazendo ? '<span class="anx-fazendo">● fazendo…</span>' : '<span class="anx-falta">—</span>');

  function aviso(texto) {
    const caixa = $("dare-toasts");
    if (!caixa) return;
    const el = document.createElement("div");
    el.className = "dare-toast info";
    el.textContent = texto;
    caixa.appendChild(el);
    setTimeout(() => el.remove(), 6500);
  }

  function bipe() {
    if (!s.som) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [[660, 0], [880, 0.2]].forEach(([f, t]) => {
        const o = ctx.createOscillator(), v = ctx.createGain();
        o.frequency.value = f;
        v.gain.value = 0.08;
        o.connect(v);
        v.connect(ctx.destination);
        o.start(ctx.currentTime + t);
        o.stop(ctx.currentTime + t + 0.2);
      });
    } catch (e) { /* sem som: tudo bem */ }
  }

  function modal(html, aoFechar, classe = "") {
    const fundo = document.createElement("div");
    fundo.className = `modal dare-modal anx-modal ${classe}`;
    fundo.innerHTML = `<div class="modal-caixa" role="dialog" aria-modal="true">${html}</div>`;
    document.body.appendChild(fundo);
    // Nome do diálogo para o leitor de tela (o título dele) e o foco de volta a quem abriu, ao fechar.
    const caixa = fundo.querySelector(".modal-caixa");
    const titulo = caixa.querySelector("h1, h2, h3, .modal-titulo");
    if (titulo) {
      titulo.id = titulo.id || "dlg-" + Math.random().toString(36).slice(2, 8);
      caixa.setAttribute("aria-labelledby", titulo.id);
    } else caixa.setAttribute("aria-label", "Janela");
    const quemAbriu = document.activeElement;
    const remover = fundo.remove.bind(fundo);
    fundo.remove = () => {
      remover();
      if (quemAbriu && quemAbriu.isConnected) quemAbriu.focus();
    };
    fundo.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && aoFechar) {
        e.preventDefault();
        aoFechar();
      }
    });
    const foco = fundo.querySelector(".btn.primario, button");
    if (foco) setTimeout(() => foco.focus(), 30);
    return fundo;
  }

  /* perguntar() da janela original: mensagem e botões [valor, rótulo, estilo]; devolve o valor. */
  function perguntar(titulo, texto, botoes) {
    return new Promise((ok) => {
      const m = modal(`<h2 style="margin:0">${esc(titulo)}</h2><p class="msg">${esc(texto)}</p>
        <div class="botoes">${botoes.map(([v, r, est]) => `<button class="btn ${est === "perigo" ? "perigo" : est === "principal" ? "primario" : "fantasma"}" type="button" data-v="${esc(v)}">${esc(r)}</button>`).join("")}</div>`,
        () => fechar(null));
      const fechar = (v) => {
        m.remove();
        ok(v);
      };
      m.querySelectorAll("[data-v]").forEach((b) => (b.onclick = () => fechar(b.dataset.v)));
    });
  }

  // ----------------------------------------------------------- navegação

  async function ir(tela) {
    if (s.tela === "configuracoes" && tela !== "configuracoes" && !(await Config.liberar())) return;
    s.tela = tela;
    document.querySelectorAll("#anx-nav [data-anx-ir]").forEach((b) => b.classList.toggle("ativo", b.dataset.anxIr === tela));
    const corpo = $("anx-corpo");
    corpo.innerHTML = "";
    if (tela === "inicio") desenharInicio();
    else if (tela === "processo") desenharProcesso();
    else if (tela === "configuracoes") {
      corpo.innerHTML = `${cabecalho("Configurações", "O que o programa preenche no SIGEF. Escolha a automação na aba, mude o que precisar na tabela e clique em Salvar. Vale para todos os processos até ser mudado. No dia a dia, não é preciso mexer aqui.")}<div id="anx-config"></div>`;
      Config.montar($("anx-config"), s.abaConfig);
    } else if (tela === "estatisticas") desenharEstatisticas();
    else if (tela === "ajuda") desenharAjuda();
    document.querySelector(".conteudo").scrollTop = 0;
    sinalDaVez();
  }

  function comoUsar() {
    const passos = AJUDA[s.tela] || [];
    perguntar(`Como usar: ${TITULOS[s.tela]}`, passos.map((t, i) => `${i + 1}.  ${t}`).join("\n\n"), [["ok", "Entendi", "principal"]]);
  }

  // ============================================================ Início

  async function desenharInicio() {
    const r = await chamar("estado");
    if (s.tela !== "inicio") return;
    if (r.ok) s.info = r;
    const info = s.info || {};
    const hora = new Date().getHours();
    const sessao = info.retomar || {};
    const lanc = sessao.lancamentos || [];
    const prontos = lanc.filter((l) => l.ob && l.baixado).length;
    const retomar = sessao.processo && lanc.length && prontos < lanc.length;
    const problemas = info.problemas || [];
    $("anx-corpo").innerHTML = `
      <header class="cabeca"><p class="sobre">Gerar pagamento · Anexar Documentos versão ${esc(info.versao || "")}</p>
        <h1>${hora < 12 ? "Bom dia!" : hora < 18 ? "Boa tarde!" : "Boa noite!"}</h1><p class="lead">O que você quer fazer agora?</p></header>
      ${problemas.length ? `<div class="dare-banner aviso"><span class="txt"><b>Falta uma coisa neste computador</b>${problemas.map((p) => `<br><b>${esc(p.titulo)}</b><br>${esc(p.texto)}`).join("")}</span><button class="btn fantasma" type="button" id="anx-verificar">Verificar de novo</button></div>` : ""}
      ${retomar ? `<div class="dare-banner aviso anx-retomar"><span class="txt"><b>Ficou um processo pela metade</b><br>Processo ${esc(sessao.processo)}${sessao.escola ? ` (${esc(sessao.escola)})` : ""}: ${prontos} de ${lanc.length} lançamento(s) prontos.<br>Clique em <b>Continuar este processo</b> e use o mesmo número. O programa faz só o que faltou, sem repetir nada.</span>
        <button class="btn primario" type="button" id="anx-continuar">Continuar este processo</button></div>` : ""}
      <button class="anx-atalho destaque" type="button" data-atalho="processo"><span class="anx-atalho-ic">▶</span><span><b>Fazer um processo</b><small>O programa faz a CE, NL, PP e OB e coloca os documentos no SEI. Você confere os dados numa tabela e clica nos botões.</small></span></button>
      <div class="anx-atalhos">
        <button class="anx-atalho" type="button" data-relatorio-geral><span class="anx-atalho-ic" aria-hidden="true">◔</span><span><b>Ver quanto tempo foi economizado</b><small>No Relatório geral: CE, NL, PP e OB feitas, tempo de cada etapa e economia, junto com as outras automações.</small></span></button>
        <button class="anx-atalho" type="button" data-atalho="configuracoes"><span class="anx-atalho-ic">⚙</span><span><b>Configurações</b><small>No dia a dia não é preciso mexer aqui.</small></span></button>
      </div>
      <div class="cartao anx-convite"><div><h3>Primeira vez? Faça um treino</h3><p class="nota">Ligue o <b>Modo treino</b>, no menu logo acima, e faça um processo de mentira. As telas são as mesmas, mas nada é feito no SEI nem no SIGEF.</p></div>
        <button class="btn fantasma" type="button" id="anx-treinar">Treinar agora</button></div>
      ${banner("info", "É o mesmo Chrome das outras automações da Central (perfil C:\\ChromeAutomacao): se você já entrou no SEI e no SIGEF por lá, o login continua valendo. <b>Atenção:</b> esta automação faz a CE, NL, PP e OB no SIGEF de produção — tudo que ela gerar vale de verdade.")}`;
    document.querySelectorAll("#anx-corpo [data-atalho]").forEach((b) => (b.onclick = () => (b.dataset.atalho === "processo" ? comecarProcesso() : ir(b.dataset.atalho))));
    if ($("anx-continuar")) $("anx-continuar").onclick = comecarProcesso;
    if ($("anx-verificar")) $("anx-verificar").onclick = desenharInicio;
    $("anx-treinar").onclick = () => {
      if (!$("anx-treino").checked && !s.rodando) {
        $("anx-treino").checked = true;
        treinoMudou();
      }
      ir("processo");
    };
  }

  function comecarProcesso() {
    ir("processo").then(() => comecar());
  }

  // ============================================================ Fazer um processo

  function desenharProcesso() {
    const treino = s.rodando ? s.treino : $("anx-treino").checked;
    $("anx-corpo").innerHTML = `
      ${cabecalho(treino && (s.rodando || s.encerrado === null) ? "Fazer um processo (treino)" : "Fazer um processo", "O programa trabalha sozinho no SIGEF e no SEI. Quando precisar de você, ele pergunta aqui.")}
      <div class="dare-banner aviso" id="anx-faixa-treino"${treino ? "" : " hidden"}><span class="txt">Modo treino ligado. É um processo de mentira: nada é feito no SEI nem no SIGEF.</span></div>
      <ol class="anx-passos" id="anx-passos">${PASSOS.map(([chave, sigla, legenda], i) => `<li data-etapa="${chave}"><span class="bolha">${i + 1}</span><b>${sigla}</b><small>${legenda}</small></li>`).join("")}</ol>
      <div class="anx-principal">
        <div class="anx-cartao-principal" id="anx-cp"></div>
        <div class="cartao anx-painel" id="anx-painel" hidden></div>
      </div>
      <div class="anx-rodape">
        <button class="btn perigo" type="button" id="anx-parar" hidden><svg class="ic" aria-hidden="true"><use href="#i-parar"/></svg>Parar o programa</button>
        <label class="check"><input type="checkbox" id="anx-som"${s.som ? " checked" : ""}> Tocar um aviso quando for a minha vez</label>
      </div>
      <details class="registro" id="anx-registro"><summary><svg class="ic" aria-hidden="true"><use href="#i-registro"/></svg>Registro técnico (para o suporte)</summary><pre id="anx-registro-texto"></pre></details>`;
    $("anx-parar").onclick = pedirParaParar;
    $("anx-som").onchange = () => {
      s.som = $("anx-som").checked;
      guardar("anx-som", s.som ? "1" : "0");
      if (s.som) bipe();
    };
    $("anx-registro").addEventListener("toggle", () => $("anx-registro").open && pintarRegistro(true));
    pintarPassos();
    desenharCartao(true);
  }

  async function comecar() {
    if (s.rodando) {
      aviso("O programa já está rodando.");
      return;
    }
    const treino = $("anx-treino").checked;
    Object.assign(s, { treino, parcial: "", etapa: null, etapaInfo: null, andamento: null, pergunta: null, encerrado: null,
      ultimoCiclo: null, sessao: null, abrindo: true, atividades: [], registro: [], estados: {} });
    s.etapasComErro.clear();
    nota("—— Começando ——");
    if (s.tela === "processo") desenharProcesso();
    const r = await chamar("iniciar", { treino });
    if (!r.ok) {
      s.abrindo = false;
      aviso(r.erro);
      if (s.tela === "processo") desenharCartao(true);
      return;
    }
    s.rodando = true;
    travarTreino();
    if (s.tela === "processo") desenharProcesso();
    lerSempre();
  }

  async function pedirParaParar() {
    const escolha = await perguntar("Parar o programa?", "Tudo o que já foi feito fica guardado. Para continuar depois, clique em Começar e use o mesmo número de processo: o programa faz só o que faltou.",
      [["nao", "Não, deixar trabalhando"], ["sim", "Sim, parar agora", "perigo"]]);
    if (escolha !== "sim") return;
    nota("Pedido para parar enviado. O programa guarda o que já fez e para em alguns segundos.");
    adicionarAtividade("Você pediu para parar. O programa guarda o que já fez.", "aviso");
    chamar("parar");
  }

  // ---------- leitura contínua (o QTimer da janela original)

  let relogio = null;
  function lerSempre() {
    if (relogio) return;
    relogio = setInterval(ler, 300);
  }

  async function ler() {
    if (s.lendo) return;
    s.lendo = true;
    try {
      const r = await chamar("novidades", { seq: s.seq });
      if (!r.ok) return;
      for (const item of r.itens || []) {
        if (item.seq <= s.seq) continue;
        s.seq = item.seq;
        if (item.tipo === "texto") receberTexto(item.texto);
        else tratarEvento(item.evento);
      }
      const estado = r.estado || {};
      if (estado.rodando && !s.rodando) {
        s.rodando = true;
        desenharCartao();
      }
      if (estado.rodando && estado.pergunta && !s.pergunta) {
        // Perdeu o evento (a tela ficou para trás): sincroniza com o núcleo.
        s.pergunta = estado.pergunta;
        desenharCartao(true);
      }
      if (!estado.rodando && !s.rodando && !s.abrindo && relogio) {
        clearInterval(relogio);
        relogio = null;
      }
    } finally {
      s.lendo = false;
    }
  }

  function receberTexto(texto) {
    const partes = (s.parcial + texto).split("\n");
    s.parcial = partes.pop();
    for (const linha of partes) {
      s.registro.push(linha);
      const tipo = classificar(linha);
      const limpo = linha.trim();
      if (["ok", "aviso", "falha", "pulado"].includes(tipo) && !LINHA_DO_RESUMO.test(linha) && limpo.length < 220)
        adicionarAtividade(limpo.replace(SEM_ENFEITE, ""), tipo);
    }
    if (s.registro.length > 3000) s.registro.splice(0, s.registro.length - 3000);
    pintarRegistro(false);
  }

  function pintarRegistro(rolar) {
    const pre = $("anx-registro-texto");
    if (!pre || !$("anx-registro").open) return;
    const perto = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 160;
    pre.textContent = s.registro.join("\n") + (s.parcial ? `\n${s.parcial}` : "");
    if (rolar || perto) pre.scrollTop = pre.scrollHeight;
  }

  function nota(texto) {
    s.registro.push(`— ${texto}`);
  }

  function adicionarAtividade(texto, tipo = "nota") {
    if (!texto) return;
    const ultimo = s.atividades[s.atividades.length - 1];
    if (ultimo && ultimo.texto === texto) return;
    const agora = new Date();
    s.atividades.push({ texto, tipo, hora: `${String(agora.getHours()).padStart(2, "0")}:${String(agora.getMinutes()).padStart(2, "0")}` });
    if (s.atividades.length > 60) s.atividades.shift();
    desenharPainel();
  }

  // ---------- passos

  function pintarPassos() {
    document.querySelectorAll("#anx-passos li").forEach((li) => (li.className = s.estados[li.dataset.etapa] || ""));
  }
  function definirPasso(chave, estado) {
    s.estados[chave] = estado;
    pintarPassos();
  }
  function marcarEtapa(chave) {
    const indice = ETAPAS.indexOf(chave);
    ETAPAS.forEach((etapa, i) => {
      if (i < indice) s.estados[etapa] = s.etapasComErro.has(etapa) ? "falhou" : "feito";
      else if (i === indice) s.estados[etapa] = "atual";
    });
    pintarPassos();
  }
  function marcarEsperando(sim) {
    Object.entries(s.estados).forEach(([etapa, estado]) => {
      if (estado === "atual" || estado === "esperando") s.estados[etapa] = sim ? "esperando" : "atual";
    });
    pintarPassos();
  }
  function fecharPassos(registro) {
    if (!registro) return;
    const chegou = (registro.etapas || []).map((e) => e.chave);
    const ultima = chegou[chegou.length - 1];
    ETAPAS.forEach((etapa) => {
      if (!chegou.includes(etapa)) return;
      const falhou = s.etapasComErro.has(etapa) || (["erro", "interrompido"].includes(registro.situacao) && etapa === ultima);
      s.estados[etapa] = falhou ? "falhou" : "feito";
    });
    pintarPassos();
  }

  // ---------- painel ao vivo

  function desenharPainel() {
    const painel = $("anx-painel");
    if (!painel) return;
    const sessao = s.sessao || {};
    const itens = sessao.lancamentos || [];
    const pedido = s.rodando ? s.pergunta : null;
    const ocupado = !!(pedido && (["formulario", "conferencia"].includes(pedido.tipo) || pedido.resumo));
    const mostrar = (s.rodando || s.encerrado !== null) && !ocupado && s.sessao && (sessao.processo || itens.length);
    painel.hidden = !mostrar;
    if (!mostrar) return;
    const partes = [];
    if (sessao.escola) partes.push(esc(sessao.escola));
    if (sessao.valor_total) partes.push(`Valor Total R$ ${esc(sessao.valor_total)}`);
    partes.push(sessao.ce ? `CE ${esc(sessao.ce)}` : "CE ainda não feita");
    const atual = s.andamento && s.andamento.atual ? s.andamento.atual - 1 : -1;
    const trabalhando = s.rodando && !s.pergunta;
    const fazendo = (chave, i) => trabalhando && s.etapa === chave && i === atual;
    const blocos = itens.map((item, i) => {
      const docs = item.baixado ? '<b class="anx-feito">✓ baixados</b>' : trabalhando && s.etapa === "BAIXAR" && item.ob ? '<span class="anx-fazendo">● baixando…</span>' : '<span class="anx-falta">—</span>';
      let titulo = `Lançamento ${i + 1}`;
      if (item.valor) titulo += ` — R$ ${item.valor}`;
      if (item.nota_de_empenho) titulo += ` · NE ${item.nota_de_empenho}`;
      return `<h4>${esc(titulo)}</h4>${grade([], [["NL", celulaNumero(item.nl, fazendo("NL", i))], ["PP", celulaNumero(item.pp, fazendo("PP", i))],
        ["OB", celulaNumero(item.ob, trabalhando && s.etapa === "OB")], ["Documentos", docs]], { negrito: true })}`;
    }).join("");
    const atividades = s.atividades.slice().reverse().slice(0, 14)
      .map((a) => `<li class="${a.tipo}"><span class="anx-ic">${ICONE_ATIVIDADE[a.tipo] || "•"}</span><span>${esc(a.texto)}</span><small>${a.hora}</small></li>`).join("");
    painel.innerHTML = `<h3>${esc(sessao.processo ? `Processo ${sessao.processo}` : "Este processo")}</h3><p class="nota">${partes.join(" · ")}</p>
      ${itens.length ? blocos : '<p class="nota">Os lançamentos aparecem aqui depois da conferência dos dados.</p>'}
      <h3 style="margin-top:14px">O que já aconteceu</h3><ul class="anx-atividades">${atividades || '<li class="nota">Ainda nada.</li>'}</ul>`;
  }

  // ---------- o quadro principal

  function desenharCartao(forcar = false) {
    const cp = $("anx-cp");
    if ($("anx-parar")) $("anx-parar").hidden = !s.rodando;
    desenharPainel();
    if (!cp) return;
    if (s.pergunta && s.rodando) {
      if (!forcar && s.desenhadaPara === s.pergunta.id && cp.dataset.estado === "vez") return;
      s.desenhadaPara = s.pergunta.id;
      s.respondendo = false;
      desenharPedido(cp, s.pergunta);
      return;
    }
    s.desenhadaPara = null;
    if (s.abrindo) {
      cp.dataset.estado = "trabalhando";
      cp.innerHTML = '<div class="carregando"><div class="giro"></div><div><strong>Abrindo o programa…</strong><span>Isso leva só alguns segundos.</span></div></div>';
      return;
    }
    if (s.rodando) return desenharTrabalhando(cp);
    if (s.encerrado !== null) return desenharFim(cp);
    const treino = $("anx-treino").checked;
    cp.dataset.estado = "parado";
    cp.innerHTML = `<p class="anx-cp-rotulo">${treino ? "Modo treino" : "Pronto para começar"}</p>
      <h2>${treino ? "Vamos treinar com um processo de mentira" : "Clique em Começar para fazer um processo"}</h2>
      <p class="lead">${treino ? "As telas são as mesmas do programa de verdade. Nada é feito no SEI nem no SIGEF." : "O Chrome do programa abre sozinho. Depois você confere os dados do processo numa tabela e clica nos botões."}</p>
      <div class="acao"><button class="btn primario grande" type="button" id="anx-comecar">▶ ${treino ? "Começar o treino" : "Começar"}</button></div>`;
    $("anx-comecar").onclick = comecar;
  }

  function desenharTrabalhando(cp) {
    cp.dataset.estado = "trabalhando";
    const info = s.etapaInfo || {};
    const nome = NOME_ETAPA[s.etapa] || info.titulo || "Preparando";
    const a = s.andamento;
    let andamento = "";
    if (a && a.texto) {
      const total = Number(a.total || 0), atual = Number(a.atual || 0);
      andamento = `<div class="agora-linha"><p class="agora">● ${esc(a.texto)}</p>${total ? `<b>${atual} de ${total}</b>` : ""}</div>
        <div class="barra"><div class="barra-cheia" style="width:${total ? Math.min(100, Math.round((atual / total) * 100)) : 35}%"></div></div>`;
    }
    cp.innerHTML = `<div class="carregando anx-trabalhando"><div class="giro"></div><div><span>O programa está trabalhando</span><strong>Agora: ${esc(nome)}</strong></div></div>
      ${info.texto ? `<p class="lead">${esc(info.texto)}</p>` : ""}${andamento}
      <p class="anx-cp-aviso">⚠ Não mexa no Chrome do programa. Quando precisar de você, este quadro fica amarelo${s.som ? " e toca um aviso." : "."}</p>`;
  }

  function desenharFim(cp) {
    const r = s.ultimoCiclo;
    const situacao = r ? r.situacao : "interrompido";
    cp.dataset.estado = situacao === "concluido" ? "fim-ok" : "fim-atencao";
    const titulos = { concluido: "Processo concluído", pendente: "O processo terminou, mas faltou alguma coisa", erro: "O programa parou por causa de um problema", interrompido: "O programa foi parado" };
    const textos = {
      concluido: "Agora confira no SEI e assine. O programa não assina nada.",
      pendente: "Clique em Começar de novo e use o mesmo número de processo: o programa faz só o que faltou.",
      erro: "Veja em “O que já aconteceu” o que houve. Depois, clique em Começar de novo com o mesmo processo.",
      interrompido: "Tudo o que foi feito está guardado. Para continuar, clique em Começar de novo e use o mesmo número de processo.",
    };
    const docs = (r && r.documentos) || {};
    cp.innerHTML = `<p class="anx-cp-rotulo ${situacao === "concluido" ? "ok" : ""}">${s.treino ? "Fim do treino" : "Fim"}</p>
      <h2>${esc((titulos[situacao] || titulos.pendente) + (r && r.processo ? ` — ${r.processo}` : ""))}</h2>
      <p class="lead">${esc(textos[situacao] || textos.pendente)}</p>
      ${r ? `<div class="dare-kpis anx-fim">${[["Tempo total", F.duracao(r.duracao_s)], ["Esperando você", F.duracao(r.humano_s)], ["Documentos", `${docs.nl || 0} NL, ${docs.pp || 0} PP, ${docs.ob || 0} OB`]]
        .map(([n, v]) => `<div class="dare-kpi"><div class="rot">${n}</div><div class="val">${esc(v)}</div></div>`).join("")}</div>` : ""}
      <div class="acao linha"><button class="btn primario grande" type="button" id="anx-de-novo">▶ Começar de novo</button>
        ${s.treino ? "" : '<button class="btn fantasma" type="button" data-relatorio-geral>Ver no Relatório geral</button>'}</div>`;
    $("anx-de-novo").onclick = comecar;
  }

  // ---------- os pedidos do programa (anexar/janela/pedidos.py)

  function cabecalhoDoPedido(p) {
    return `<p class="anx-cp-rotulo vez">⚠ Sua vez</p>
      <div class="anx-pedido-titulo"><h2>${esc(p.titulo || "O programa precisa de você")}</h2>${p.processo ? `<span class="anx-etiqueta processo">Processo ${esc(p.processo)}</span>` : ""}</div>
      ${(p.linhas || []).map((l) => `<p class="lead">${esc(l)}</p>`).join("")}
      ${(p.passos || []).length ? `<ol class="lista">${p.passos.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}`;
  }

  function botoesDoPedido(p) {
    return `<div class="acao linha anx-botoes">${(p.botoes || []).map((b) => {
      const classe = b.estilo === "principal" ? "primario grande" : b.estilo === "perigo" ? "perigo grande" : "fantasma grande";
      const html = `<button class="btn ${classe}" type="button" data-valor="${esc(b.valor)}"${b.desabilitado ? " disabled" : ""}${b.ajuda ? ` title="${esc(b.ajuda)}"` : ""}>${esc(b.rotulo)}</button>`;
      return b.desabilitado && b.ajuda ? `<span class="anx-botao-ajuda">${html}<small>${esc(b.ajuda)}</small></span>` : html;
    }).join("")}</div>`;
  }

  function desenharPedido(cp, p) {
    cp.dataset.estado = "vez";
    cp.dataset.tom = p.tom || "normal";
    let corpo = "";
    if (p.tipo === "formulario") corpo = Formulario.html(p);
    else if (p.tipo === "conferencia") corpo = conferenciaHtml(p);
    else if (p.tipo === "configuracoes")
      corpo = `<div class="acao linha"><button class="btn fantasma grande" type="button" id="anx-abrir-config">⚙ Abrir as configurações</button>
        <button class="btn primario grande" type="button" id="anx-voltar-processo">✓ Voltar para o processo</button></div>`;
    else corpo = (p.resumo ? tabelaResumo(p.resumo) : "") + botoesDoPedido(p);
    cp.innerHTML = cabecalhoDoPedido(p) + corpo;
    if (p.tipo === "formulario") Formulario.ligar(cp, p, (valor, resposta) => responder(resposta));
    else if (p.tipo === "configuracoes") {
      $("anx-abrir-config").onclick = () => abrirConfiguracoes(p);
      $("anx-voltar-processo").onclick = voltarParaOProcesso;
      setTimeout(() => abrirConfiguracoes(p), 0);
    } else cp.querySelectorAll(".anx-botoes [data-valor]").forEach((b) => (b.onclick = () => responder(b.dataset.valor)));
    if (s.tela === "processo" && cp.scrollIntoView) cp.scrollIntoView({ block: "nearest" });
  }

  async function responder(resposta) {
    if (!s.pergunta || s.respondendo) return;
    const id = s.pergunta.id;
    s.respondendo = true;
    document.querySelectorAll("#anx-cp button").forEach((b) => (b.disabled = true));
    const r = await chamar("responder", { resposta, id });
    if (!r.ok) {
      s.respondendo = false;
      aviso(r.erro);
      const estado = r.estado || {};
      s.pergunta = estado.rodando ? estado.pergunta : null;
      desenharCartao(true);
      return;
    }
    if (s.pergunta && s.pergunta.id === id) {
      s.pergunta = null;
      marcarEsperando(false);
      desenharCartao();
      sinalDaVez();
    }
  }

  // O formulário em tabela: os dados do processo e os lançamentos (valor e nota de empenho).
  const Formulario = {
    controle(c, erro) {
      const inval = erro ? " anx-invalido" : "";
      if (c.tipo === "mes" || c.tipo === "lista") {
        return `<select class="dare-input${inval}" data-chave="${esc(c.chave)}">${c.valor ? "" : '<option value="">Escolha…</option>'}${(c.opcoes || [])
          .map(([v, n]) => `<option value="${esc(v)}"${String(v) === String(c.valor) ? " selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
      }
      return `<input class="dare-input${inval}" data-chave="${esc(c.chave)}" value="${esc(c.valor || "")}" maxlength="${Number(c.maximo) || 300}"${c.exemplo ? ` placeholder="Ex: ${esc(c.exemplo)}"` : ""} spellcheck="false">
        ${c.tipo === "valor" ? '<small class="anx-dica-valor"></small>' : ""}`;
    },
    html(p) {
      const campos = p.campos || [];
      const erros = p.erros || {};
      const temAnterior = campos.some((c) => c.anterior);
      const total = Object.keys(erros).length;
      const linhas = campos.map((c) => {
        const erro = erros[c.chave];
        let anterior = c.anterior;
        if (anterior && c.opcoes) anterior = (c.opcoes.find(([v]) => String(v) === String(anterior)) || [null, anterior])[1];
        return `<tr class="${erro ? "erro" : ""}"><td><b>${esc(c.rotulo || c.chave)}</b>${c.ajuda ? `<br><small class="nota">${esc(c.ajuda)}</small>` : ""}</td>
          <td>${Formulario.controle(c, erro)}${erro ? `<div class="anx-erro-campo">${esc(erro)}</div>` : ""}</td>
          ${temAnterior ? `<td>${anterior ? `${esc(anterior)} <button class="btn fantasma pequeno" type="button" data-usar="${esc(c.chave)}" data-valor-usar="${esc(c.anterior)}" title="Usar o valor da última vez">usar</button>` : '<span class="nota">—</span>'}</td>` : ""}</tr>`;
      }).join("");
      const lanc = p.lancamentos;
      return `${total ? banner("erro", `Falta arrumar ${total === 1 ? "1 item" : `${total} itens`} (em vermelho).`) : ""}
        <div class="dare-tabela anx-form"><table><thead><tr><th>Campo</th><th>Valor</th>${temAnterior ? "<th>Da última vez</th>" : ""}</tr></thead><tbody>${linhas}</tbody></table></div>
        ${lanc ? `<div class="cartao anx-lancamentos"><h3>Lançamentos (valor e nota de empenho)</h3>${lanc.explicacao ? `<p class="nota">${esc(lanc.explicacao)}</p>` : ""}
          <table class="anx-lanc"><thead><tr><th>Nº</th><th>Valor (R$)</th><th>Nota de Empenho</th><th></th></tr></thead><tbody id="anx-lanc-linhas"></tbody></table>
          <div class="acao linha"><button class="btn fantasma" type="button" id="anx-lanc-mais">＋ Adicionar lançamento</button><span class="anx-soma" id="anx-soma"></span></div></div>` : ""}
        ${erros.lancamentos ? `<div class="anx-erro-campo">${esc(erros.lancamentos)}</div>` : ""}
        ${botoesDoPedido(p)}`;
    },
    ligar(raiz, p, aoBotao) {
      const erros = p.erros || {};
      const lanc = p.lancamentos;
      const maximo = lanc ? Number(lanc.maximo) || 20 : 0;
      const campoTotal = lanc ? raiz.querySelector(`[data-chave="${CSS.escape(lanc.campo_total || "valor_total")}"]`) : null;
      const dica = (entrada, alvo) => {
        const texto = entrada.value.trim(), c = F.centavos(texto);
        let conteudo = "", tom = "";
        if (!texto || c === null) conteudo = "";
        else if (c === F.INVALIDO) [conteudo, tom] = ["Valor inválido. Exemplo: 1.105,50", "erro"];
        else if (/^\d+$/.test(texto)) [conteudo, tom] = [`Sem vírgula: fica R$ ${F.reais(c)} (os 2 últimos números são os centavos).`, "atencao"];
        else conteudo = `= R$ ${F.reais(c)}`;
        alvo.textContent = conteudo;
        alvo.className = `anx-dica-valor ${tom}`;
      };
      raiz.querySelectorAll("input[data-chave]").forEach((entrada) => {
        const alvo = entrada.parentElement.querySelector(".anx-dica-valor");
        if (alvo) {
          entrada.addEventListener("input", () => dica(entrada, alvo));
          dica(entrada, alvo);
        }
      });
      raiz.querySelectorAll("[data-usar]").forEach((b) => (b.onclick = () => {
        const alvo = raiz.querySelector(`[data-chave="${CSS.escape(b.dataset.usar)}"]`);
        alvo.value = b.dataset.valorUsar;
        alvo.dispatchEvent(new Event("input"));
      }));

      const linhas = [];
      const somar = () => {
        if (!lanc) return;
        let soma = 0;
        linhas.forEach((l) => {
          const c = F.centavos(l.valor.value);
          if (typeof c === "number" && c > 0) soma += c;
        });
        let texto = `Soma dos lançamentos: R$ ${F.reais(soma)}`, tom = "";
        const total = campoTotal ? F.centavos(campoTotal.value) : null;
        if (typeof total === "number" && total >= 0) {
          texto += `   ·   Valor Total: R$ ${F.reais(total)}   ·   `;
          if (soma === total) [texto, tom] = [`${texto}✓ Confere`, "ok"];
          else if (soma < total) [texto, tom] = [`${texto}Falta lançar R$ ${F.reais(total - soma)}`, "atencao"];
          else [texto, tom] = [`${texto}Passou R$ ${F.reais(soma - total)} — confira!`, "erro"];
        }
        $("anx-soma").textContent = texto;
        $("anx-soma").className = `anx-soma ${tom}`;
      };
      const reposicionar = () => {
        linhas.forEach((l, i) => {
          l.numero.textContent = String(i + 1);
          l.remover.disabled = linhas.length <= 1;
        });
        $("anx-lanc-mais").disabled = linhas.length >= maximo;
      };
      const novaLinha = (item, indice) => {
        const tr = document.createElement("tr");
        const eV = indice !== null ? erros[`lancamentos.${indice}.valor`] : null;
        const eN = indice !== null ? erros[`lancamentos.${indice}.nota_de_empenho`] : null;
        tr.innerHTML = `<td class="mono"></td>
          <td><input class="dare-input${eV ? " anx-invalido" : ""}" placeholder="Ex: 1.105,50" aria-label="Valor do lançamento" value="${esc(item.valor || "")}"><small class="anx-dica-valor"></small>${eV ? `<div class="anx-erro-campo">${esc(eV)}</div>` : ""}</td>
          <td><input class="dare-input${eN ? " anx-invalido" : ""}" placeholder="Ex: 002180" aria-label="Nota de empenho" value="${esc(item.nota_de_empenho || "")}">${eN ? `<div class="anx-erro-campo">${esc(eN)}</div>` : ""}</td>
          <td><button class="btn fantasma pequeno" type="button" title="Remover este lançamento">Remover</button></td>`;
        $("anx-lanc-linhas").appendChild(tr);
        const [valor, empenho] = tr.querySelectorAll("input");
        const l = { tr, numero: tr.firstElementChild, valor, empenho, remover: tr.querySelector("button") };
        valor.addEventListener("input", () => { dica(valor, tr.querySelector(".anx-dica-valor")); somar(); });
        dica(valor, tr.querySelector(".anx-dica-valor"));
        l.remover.onclick = () => {
          if (linhas.length <= 1) return;
          linhas.splice(linhas.indexOf(l), 1);
          tr.remove();
          reposicionar();
          somar();
        };
        linhas.push(l);
        reposicionar();
        return l;
      };
      if (lanc) {
        (lanc.itens && lanc.itens.length ? lanc.itens : [{}]).forEach((item, i) => novaLinha(item, i));
        $("anx-lanc-mais").onclick = () => {
          novaLinha({}, null).valor.focus();
          somar();
        };
        if (campoTotal) campoTotal.addEventListener("input", somar);
        somar();
      }
      // ENTER nunca envia nada: só vai para o próximo campo (quem envia é o botão).
      raiz.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" || e.target.tagName !== "INPUT") return;
        e.preventDefault();
        const todos = [...raiz.querySelectorAll("input, select")];
        const proximo = todos[todos.indexOf(e.target) + 1];
        if (proximo) proximo.focus();
      });
      const resposta = (valorBotao) => {
        const valores = {};
        raiz.querySelectorAll("[data-chave]").forEach((c) => (valores[c.dataset.chave] = c.value));
        return { botao: valorBotao, valores, lancamentos: lanc ? linhas.map((l) => ({ valor: l.valor.value, nota_de_empenho: l.empenho.value })) : null };
      };
      raiz.querySelectorAll(".anx-botoes [data-valor]").forEach((b) => (b.onclick = () => aoBotao(b.dataset.valor, resposta(b.dataset.valor))));
      const errado = raiz.querySelector(".anx-invalido") || raiz.querySelector("[data-chave]");
      if (errado) setTimeout(() => errado.focus(), 30);
    },
  };

  function conferenciaHtml(p) {
    const lanc = (p.lancamentos || {}).itens || [];
    const comp = (p.lancamentos || {}).comparacao;
    const tomComp = comp ? (comp.tipo === "ok" ? "ok" : comp.tipo === "falta" ? "atencao" : "erro") : "";
    const configs = (p.configuracoes || []).map((c) => {
      const problemas = c.problemas || [];
      return { tom: problemas.length ? "aviso" : "", celulas: [esc(c.titulo || ""), `${esc(c.resumo || "")}${problemas.map((x) => `<div class="anx-erro-campo">• ${esc(x)}</div>`).join("")}`,
        problemas.length ? etiqueta("Precisa de ajuste", "precisa") : etiqueta("Pronta", "ok")] };
    });
    return `<div class="grade2 anx-conferencia">
        ${cartao("Dados do processo", grade([], (p.dados || []).map(([r, v]) => [esc(r), esc(v || "—")]), { negrito: true }))}
        ${cartao(`Lançamentos (${lanc.length})`, grade(["Nº", "Valor (R$)", "Nota de Empenho"], lanc.map((i) => [esc(i.numero), esc(i.valor || ""), esc(i.nota_de_empenho || "")]), { direita: [0, 1] })
          + (comp ? `<p class="anx-soma ${tomComp}">${tomComp === "ok" ? "✓" : "⚠"} Soma: R$ ${esc(comp.soma)} — ${esc(comp.texto)}</p>` : ""))}
      </div>
      ${cartao("O que vai ser usado no SIGEF", grade(["Automação", "Configuração", "Situação"], configs, { negrito: true }))}
      ${(p.problemas || []).length ? banner("erro", "Antes de começar, arrume o que está em amarelo: clique em “Configurações (CE, PP, OB)”, ou em “Corrigir os dados” se o problema for nos dados do processo.") : ""}
      ${botoesDoPedido(p)}`;
  }

  function tabelaResumo(resumo) {
    const linhas = (resumo.lancamentos || []).map((i) => ({
      tom: i.pronto ? "" : "aviso",
      celulas: [esc(i.numero), esc(i.valor || "—"), celulaNumero(i.nl), celulaNumero(i.pp), celulaNumero(i.ob), i.pronto ? etiqueta("Pronto", "ok") : etiqueta("Faltou algo", "precisa")],
    }));
    return cartao(`Resumo${resumo.ce ? ` — CE ${esc(resumo.ce)}` : ""}`, grade(["Nº", "Valor (R$)", "NL", "PP", "OB", "Situação"], linhas, { direita: [0, 1] }));
  }

  // ---------- configurações no meio do processo

  function abrirConfiguracoes(p) {
    if (!p || s.configModal) return;
    const m = modal(`<div class="topo"><h2 style="margin:0">⚙ ${esc(p.titulo || "Configurações")}</h2>${(p.linhas || []).length ? `<p class="nota">${esc(p.linhas.join(" "))}</p>` : ""}</div>
      <div class="corpo" id="anx-config-modal"></div>
      <div class="rodape"><span class="txt"></span><button class="btn primario grande" type="button" id="anx-config-voltar">✓ Voltar para o processo</button></div>`,
      () => voltarParaOProcesso(), "grande");
    s.configModal = m;
    $("anx-config-voltar").onclick = voltarParaOProcesso;
    Config.montar($("anx-config-modal"), p.secao || "ce");
  }

  async function voltarParaOProcesso() {
    if (s.configModal && !(await Config.liberar())) return;
    fecharConfigModal();
    if (s.pergunta && s.pergunta.tipo === "configuracoes") responder("pronto");
  }

  function fecharConfigModal() {
    if (s.configModal) {
      s.configModal.remove();
      s.configModal = null;
      Config.alvo = null;
      if (s.tela === "configuracoes" && $("anx-config")) Config.montar($("anx-config"), s.abaConfig);
    }
  }

  // ---------- eventos da automação (tela_processo.tratar_evento)

  function tratarEvento(ev) {
    const tipo = ev.tipo;
    if (tipo === "sessao_app") {
      s.treino = !!ev.treino;
    } else if (tipo === "inicio") {
      s.abrindo = false;
      nota(s.treino ? "Treino aberto." : "Programa aberto.");
      desenharCartao();
    } else if (tipo === "etapa") {
      s.abrindo = false;
      s.etapa = ev.chave;
      s.etapaInfo = ev;
      s.andamento = null;
      if (ETAPAS.includes(s.etapa)) marcarEtapa(s.etapa);
      adicionarAtividade(`Começou: ${NOME_ETAPA[s.etapa] || ev.titulo || s.etapa}`, "etapa");
      sinalDaVez();
      if (!s.pergunta) desenharCartao();
    } else if (tipo === "andamento") {
      s.andamento = ev;
      if (!s.pergunta) desenharCartao();
    } else if (tipo === "sessao") {
      s.sessao = ev.sessao;
      desenharPainel();
    } else if (tipo === "ciclo_inicio") {
      s.estados = {};
      s.etapasComErro.clear();
      pintarPassos();
    } else if (tipo === "erro") {
      if (ETAPAS.includes(s.etapa)) s.etapasComErro.add(s.etapa);
      const passos = ev.passos || [];
      adicionarAtividade((ev.titulo || "Erro") + (passos.length ? ` — ${passos[0]}` : ""), "falha");
    } else if (tipo === "pergunta") {
      s.abrindo = false;
      s.pergunta = ev.pedido || {};
      s.respondendo = false;
      marcarEsperando(true);
      desenharCartao(true);
      sinalDaVez();
      bipe();
      if (!s.ativo || s.tela !== "processo") aviso(`Gerar pagamento — sua vez: ${s.pergunta.titulo || "o programa precisa de você"}.`);
    } else if (tipo === "respondido") {
      if (s.pergunta && (!ev.id || s.pergunta.id === ev.id)) {
        s.pergunta = null;
        marcarEsperando(false);
        desenharCartao();
        sinalDaVez();
      }
    } else if (tipo === "ciclo_fim") {
      s.ultimoCiclo = ev.registro;
      if (ev.sessao) s.sessao = ev.sessao;
      fecharPassos(ev.registro);
    } else if (tipo === "aviso_relatorio") {
      nota(ev.texto || "");
    } else if (tipo === "encerrado") {
      programaTerminou(ev.codigo);
    }
  }

  function programaTerminou(codigo) {
    s.rodando = false;
    s.abrindo = false;
    s.pergunta = null;
    s.encerrado = codigo ?? 0;
    Object.entries(s.estados).forEach(([etapa, estado]) => {
      if (estado === "atual" || estado === "esperando") s.estados[etapa] = "falhou";
    });
    pintarPassos();
    fecharConfigModal();
    nota("O programa terminou.");
    desenharCartao();
    travarTreino();
    sinalDaVez();
    if (s.tela === "inicio") desenharInicio();
  }

  // ---------- sinal da vez, treino e ponto na barra

  function sinalDaVez() {
    const esperando = !!(s.rodando && s.pergunta);
    const vendo = s.ativo && s.tela === "processo";
    if ($("anx-selo-vez")) $("anx-selo-vez").hidden = !(esperando && !vendo);
    let texto = "Nenhuma automação rodando";
    if (esperando) texto = "Esperando você";
    else if (s.rodando) texto = `${s.treino ? "Treino rodando" : "Programa rodando"}${NOME_ETAPA[s.etapa] ? `: ${NOME_ETAPA[s.etapa]}` : ""}`;
    if ($("anx-situacao")) {
      $("anx-situacao").textContent = texto;
      $("anx-situacao").classList.toggle("vez", esperando);
      $("anx-situacao").hidden = !s.rodando; // parado, o aviso só ocupava o espaço dos passos no topo
    }
    const botaoModulo = document.querySelector('.modulo[data-modulo="anexar"]');
    if (!botaoModulo) return;
    let ponto = botaoModulo.querySelector(".rodando");
    if ((s.rodando || s.abrindo) && !ponto) {
      ponto = document.createElement("i");
      ponto.className = "rodando";
      botaoModulo.appendChild(ponto);
    } else if (!(s.rodando || s.abrindo) && ponto) ponto.remove();
    if (ponto) {
      ponto.title = esperando ? "Sua vez" : "Rodando";
      botaoModulo.classList.toggle("atencao", esperando);
    } else botaoModulo.classList.remove("atencao");
  }

  function travarTreino() {
    $("anx-treino").disabled = s.rodando;
  }

  function treinoMudou() {
    const ligado = $("anx-treino").checked;
    guardar("anx-treino", ligado ? "1" : "0");
    aviso(ligado ? "Modo treino ligado: nada será feito no SEI nem no SIGEF." : "Modo treino desligado: o próximo processo é de verdade.");
    if (s.tela === "processo" && !s.rodando) {
      s.encerrado = null;
      desenharProcesso();
    }
  }

  // ============================================================ Configurações (anexar/janela/config.py)

  const Config = {
    alvo: null,
    secoes: [],
    bloqueado: false,
    erro: null,
    atual: "global",
    original: {},
    mensagem: null,
    erros: {},

    async montar(alvo, secaoInicial) {
      Config.alvo = alvo;
      Config.atual = secaoInicial || "global";
      alvo.innerHTML = '<p class="nota">Carregando…</p>';
      const r = await chamar("config_tabelas");
      if (Config.alvo !== alvo) return;
      if (!r.ok) {
        alvo.innerHTML = banner("erro", esc(r.erro));
        return;
      }
      Config.secoes = r.secoes || [];
      Config.bloqueado = !!r.bloqueado;
      Config.erro = r.erro;
      if (!Config.secoes.some((x) => x.chave === Config.atual)) Config.atual = Config.secoes.length ? Config.secoes[0].chave : "global";
      Config.desenhar();
    },

    secao: () => Config.secoes.find((x) => x.chave === Config.atual),

    desenhar(erros = {}, mensagem = null) {
      const alvo = Config.alvo;
      if (!alvo) return;
      if (Config.erro) {
        alvo.innerHTML = banner("erro", esc(Config.erro));
        return;
      }
      Config.erros = erros;
      const abas = Config.secoes.map((x) => {
        const situacao = !x.editavel ? "neutra" : (x.problemas || []).length ? "precisa" : "ok";
        const sub = !x.editavel ? "valores fixos" : (x.problemas || []).length ? "precisa de ajuste" : x.alterados ? `${x.alterados} mudança(s)` : "padrão";
        return `<button class="aba anx-aba ${x.chave === Config.atual ? "ativa" : ""} ${situacao}" type="button" data-secao="${x.chave}"><b>${esc(x.sigla)}</b><span class="aba-sub">${sub}</span></button>`;
      }).join("");
      const x = Config.secao();
      alvo.innerHTML = `<div class="abas anx-abas">${abas}</div>${x ? Config.painel(x, erros, mensagem) : ""}`;
      alvo.querySelectorAll("[data-secao]").forEach((b) => (b.onclick = () => Config.trocar(b.dataset.secao)));
      if (x) Config.ligar(x);
    },

    painel(x, erros, mensagem) {
      const etiquetaSecao = !x.editavel ? etiqueta("Valores fixos", "neutra") : (x.problemas || []).length ? etiqueta("Precisa de ajuste", "precisa") : etiqueta("Pronta", "ok");
      const linhas = (x.campos || []).map((c) => {
        const erro = erros[c.chave];
        return `<tr class="${erro ? "erro" : ""}" data-linha="${c.chave}"><td><b>${esc(c.rotulo)}</b>${c.ajuda ? `<br><small class="nota">${esc(c.ajuda)}</small>` : ""}</td>
          <td>${Config.controle(c, x, !!erro)}${erro ? `<div class="anx-erro-campo">${esc(erro)}</div>` : ""}</td>
          <td>${esc(c.tipo === "modelo" ? "texto padrão" : c.padrao_texto || "")}${c.alterado ? `<br>${etiqueta("mudado", "alterado")}` : ""}</td></tr>`;
      }).join("");
      const desab = !x.editavel || Config.bloqueado ? " disabled" : "";
      return `<div class="anx-config-cab"><div><h2>${esc(x.titulo)}</h2><p class="nota">${esc(x.descricao || "")}</p></div>${etiquetaSecao}</div>
        ${Config.bloqueado && x.editavel ? banner("aviso", "A automação está trabalhando no SIGEF. Para mudar as configurações, espere ela terminar (ou pedir você).") : ""}
        ${(x.problemas || []).length ? banner("aviso", `<b>Falta arrumar:</b>${x.problemas.map((p) => `<br>• ${esc(p)}`).join("")}`) : ""}
        ${(x.campos || []).length ? `<fieldset class="anx-config-campos"${desab}><div class="dare-tabela anx-form"><table><thead><tr><th>Campo</th><th>Valor</th><th>Padrão</th></tr></thead><tbody>${linhas}</tbody></table></div></fieldset>` : ""}
        ${(x.automaticos || []).length ? `<h3 style="margin-top:14px">${x.editavel ? "Preenchido sozinho (não precisa mexer)" : "Valores usados hoje"}</h3>${grade([], x.automaticos.map(([r, v]) => [esc(r), esc(v || "—")]), { negrito: true })}` : ""}
        ${x.editavel ? `<div class="acao linha"><button class="btn primario" type="button" id="anx-cfg-salvar"${desab}>Salvar</button>
          <button class="btn fantasma" type="button" id="anx-cfg-desfazer"${desab}>Desfazer as mudanças</button>
          <button class="btn perigo-contorno" type="button" id="anx-cfg-padrao"${desab}>Voltar ao padrão</button>
          ${mensagem ? etiqueta(mensagem[1], mensagem[0] === "ok" ? "ok" : "erro") : ""}</div>` : ""}`;
    },

    controle(c, x, comErro) {
      const inval = comErro ? " anx-invalido" : "";
      const id = `anx-cfg-${c.chave}`;
      if (c.tipo === "lista")
        return `<select class="dare-input${inval}" id="${id}" data-campo="${c.chave}">${(c.opcoes || []).map(([v, n]) => `<option value="${esc(v)}"${String(v) === String(c.valor) ? " selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
      if (c.tipo === "data") {
        const fixa = !!c.valor;
        const iso = fixa ? c.valor.split("/").reverse().join("-") : new Date().toISOString().slice(0, 10);
        return `<div class="anx-data" data-campo="${c.chave}"><label><input type="radio" name="${id}" value="hoje"${fixa ? "" : " checked"}> Data de hoje</label>
          <label><input type="radio" name="${id}" value="fixa"${fixa ? " checked" : ""}> Data fixa:</label> <input class="dare-input data" type="date" value="${iso}"${fixa ? "" : " disabled"}></div>`;
      }
      if (c.tipo === "modelo")
        return `<textarea class="dare-input anx-modelo${inval}" id="${id}" data-campo="${c.chave}" rows="3">${esc(c.valor)}</textarea>
          <div class="anx-fichas"><span class="nota">Clique para pôr no texto:</span>${(x.campos_modelo || []).map((n) => `<button class="btn fantasma pequeno" type="button" data-ficha="${esc(n)}" data-alvo="${id}">{${esc(n)}}</button>`).join("")}</div>
          <p class="nota" data-previa="${id}"></p><button class="btn fantasma pequeno" type="button" data-padrao-de="${id}" data-texto="${esc(c.padrao)}">usar o texto padrão</button>`;
      return `<input class="dare-input${inval}" id="${id}" data-campo="${c.chave}" value="${esc(c.valor)}"${c.maximo ? ` maxlength="${Number(c.maximo)}"` : ""} spellcheck="false">`;
    },

    valor(c) {
      const id = `anx-cfg-${c.chave}`;
      if (c.tipo === "data") {
        const caixa = Config.alvo.querySelector(`.anx-data[data-campo="${c.chave}"]`);
        const fixa = caixa.querySelector('input[value="fixa"]').checked;
        const iso = caixa.querySelector('input[type="date"]').value;
        return fixa && iso ? iso.split("-").reverse().join("/") : "";
      }
      const el = $(id);
      return el ? String(el.value || "").trim() : "";
    },

    visivel(c) {
      const regra = c.mostrar_se;
      if (!regra) return true;
      const campo = (Config.secao().campos || []).find((x) => x.chave === regra.campo);
      return !campo || regra.valores.includes(Config.valor(campo));
    },

    aplicarVisibilidade() {
      const x = Config.secao();
      (x.campos || []).forEach((c) => {
        const linha = Config.alvo.querySelector(`tr[data-linha="${CSS.escape(c.chave)}"]`);
        if (linha) linha.hidden = !Config.visivel(c);
      });
    },

    ligar(x) {
      const alvo = Config.alvo;
      Config.original = {};
      (x.campos || []).forEach((c) => (Config.original[c.chave] = String(c.valor || "").trim()));
      const valoresModelo = x.valores_modelo || {};
      const previa = (id) => {
        const texto = $(id).value.replace(/\{([a-z_]+)\}/g, (achado, nome) => (nome in valoresModelo ? (valoresModelo[nome] ? String(valoresModelo[nome]) : `‹${nome}›`) : achado));
        alvo.querySelector(`[data-previa="${id}"]`).textContent = `Vai ficar: ${texto}`;
      };
      alvo.querySelectorAll("textarea.anx-modelo").forEach((t) => {
        t.addEventListener("input", () => previa(t.id));
        previa(t.id);
      });
      alvo.querySelectorAll("[data-ficha]").forEach((b) => (b.onclick = () => {
        const t = $(b.dataset.alvo);
        const ini = t.selectionStart ?? t.value.length, fim = t.selectionEnd ?? t.value.length;
        t.value = `${t.value.slice(0, ini)}{${b.dataset.ficha}}${t.value.slice(fim)}`;
        t.focus();
        previa(t.id);
      }));
      alvo.querySelectorAll("[data-padrao-de]").forEach((b) => (b.onclick = () => {
        $(b.dataset.padraoDe).value = b.dataset.texto;
        previa(b.dataset.padraoDe);
      }));
      alvo.querySelectorAll(".anx-data").forEach((caixa) => caixa.querySelectorAll('input[type="radio"]').forEach((r) => (r.onchange = () => {
        caixa.querySelector('input[type="date"]').disabled = !caixa.querySelector('input[value="fixa"]').checked;
      })));
      alvo.querySelectorAll("select[data-campo]").forEach((sel) => sel.addEventListener("change", Config.aplicarVisibilidade));
      alvo.querySelectorAll("input[data-campo]").forEach((e) => e.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter") return;
        ev.preventDefault();
        const todos = [...alvo.querySelectorAll("input, select, textarea")];
        const proximo = todos[todos.indexOf(e) + 1];
        if (proximo) proximo.focus();
      }));
      Config.aplicarVisibilidade();
      if ($("anx-cfg-salvar")) {
        $("anx-cfg-salvar").onclick = () => Config.salvar();
        $("anx-cfg-desfazer").onclick = () => Config.desenhar();
        $("anx-cfg-padrao").onclick = () => Config.restaurar();
      }
    },

    sujo() {
      const x = Config.secao();
      if (!Config.alvo || !x || !x.editavel || !Config.alvo.isConnected) return false;
      return (x.campos || []).some((c) => Config.visivel(c) && Config.valor(c) !== Config.original[c.chave]);
    },

    valores() {
      const out = {};
      (Config.secao().campos || []).forEach((c) => {
        if (Config.visivel(c)) out[c.chave] = Config.valor(c); // campo escondido (ex: Série sem Nota Fiscal) fica como está
      });
      return out;
    },

    async salvar() {
      const x = Config.secao();
      const r = await chamar("config_salvar", { secao: x.chave, valores: Config.valores() });
      if (!r.ok) {
        Config.desenhar(r.erros || {}, ["erro", r.erro || "Algum valor não pôde ser salvo: veja em vermelho."]);
        if (r.erros) aviso("Algum valor não pôde ser salvo: veja em vermelho.");
        return false;
      }
      Config.secoes = Config.secoes.map((y) => (y.chave === r.secao.chave ? r.secao : y));
      Config.desenhar({}, ["ok", "Salvo. Já vale para o próximo processo."]);
      return true;
    },

    async restaurar() {
      const x = Config.secao();
      const escolha = await perguntar(`Voltar ${x.sigla} ao padrão?`, "Todas as mudanças desta automação serão desfeitas e ela volta a usar os valores originais do programa.",
        [["nao", "Não, deixar como está"], ["sim", "Sim, voltar ao padrão", "perigo"]]);
      if (escolha !== "sim") return;
      const r = await chamar("config_padrao", { secao: x.chave });
      if (!r.ok) return Config.desenhar({}, ["erro", r.erro]);
      Config.secoes = Config.secoes.map((y) => (y.chave === r.secao.chave ? r.secao : y));
      Config.desenhar();
    },

    async trocar(chave) {
      if (chave === Config.atual || !(await Config.liberar())) return;
      Config.atual = chave;
      if (!s.configModal) {
        s.abaConfig = chave;
        guardar("anx-aba-config", chave);
      }
      Config.desenhar();
    },

    /* Antes de sair de uma tabela com mudanças não salvas: pergunta o que fazer. false = ficar. */
    async liberar() {
      if (!Config.sujo()) return true;
      const escolha = await perguntar("Salvar as mudanças?", "Você mudou esta configuração e ainda não salvou.",
        [["cancelar", "Continuar mexendo"], ["descartar", "Sair sem salvar"], ["salvar", "Salvar", "principal"]]);
      if (escolha === "descartar") return true;
      if (escolha === "salvar") return Config.salvar();
      return false;
    },
  };

  // ============================================================ Estatísticas

  /* Os números do Gerar pagamento ficam no Relatório geral (junto com as outras automações). Aqui
     ficam só os ajustes: quantos minutos leva cada item à mão (a base da economia) e as planilhas do estudo. */
  async function desenharEstatisticas() {
    const r = await chamar("estatisticas", { periodo: s.periodo, quantidade: s.quantidade });
    if (s.tela !== "estatisticas") return;
    if (!r.ok) {
      $("anx-corpo").innerHTML = banner("erro", esc(r.erro));
      return;
    }
    $("anx-corpo").innerHTML = `${cabecalho("Tempos e planilhas", "Os números do Gerar pagamento — CE, NL, PP e OB feitas, tempo de cada etapa e quanto foi economizado — agora ficam no Relatório geral, junto com as outras automações.")}
      <div class="cartao anx-convite"><div><h3>Relatório geral</h3><p class="nota">Abre no navegador, com gráficos, a lista dos processos do período e o tempo de cada etapa. Dá para imprimir ou salvar em PDF.</p></div>
        <button class="btn primario" type="button" data-relatorio-geral><svg class="ic" aria-hidden="true"><use href="#i-grafico"/></svg>Abrir o Relatório geral</button></div>
      ${cartao("Quanto tempo leva fazer 1 item à mão (sem o aplicativo)", `<div class="anx-estimativas">${r.categorias.map((c) => `<label><b>${esc(c.curto)}</b>
          <input class="dare-input curto" type="number" min="0" max="${r.maximo}" step="0.5" data-estimativa="${c.chave}" value="${r.estimativas[c.chave] ?? 0}" aria-label="${esc(c.nome)}: minutos à mão ${esc(c.item)}"><small>minutos ${esc(c.item)}</small></label>`).join("")}</div>
        <div class="acao linha"><button class="btn primario" type="button" id="anx-salvar-est">Salvar estimativas</button><span id="anx-est-msg" role="status"></span></div>
        <p class="nota">É a base do tempo economizado no Relatório geral. Fica salvo no código do programa (arquivo automacoes\\anexar\\aplicativo\\estimativas_manuais.py). Para chegar num bom número, cronometre alguns itens feitos à mão e use a média.</p>`)}
      ${cartao("Levar os dados para o estudo", `<p class="nota">Planilhas que abrem no Excel, com os dados do período escolhido.</p>
        <div class="acao linha anx-filtro"><label for="anx-periodo"><b>Período:</b></label><select class="dare-input" id="anx-periodo">${r.periodos.map(([k, n]) => `<option value="${k}"${k === s.periodo ? " selected" : ""}>${esc(n)}</option>`).join("")}</select>
          <span class="nota">${r.processos} processo(s) no período</span></div>
        <label class="check"><input type="checkbox" id="anx-anonimo"${s.anonimo ? " checked" : ""}> Tirar o número do processo (anônimo)</label>
        <div class="acao linha"><button class="btn fantasma" type="button" data-exportar="processos">Planilha por processo</button><button class="btn fantasma" type="button" data-exportar="etapas">Planilha por etapa</button>
          <button class="btn fantasma" type="button" data-exportar="economia">Planilha da economia</button><button class="btn fantasma pequeno" type="button" data-exportar="json">Dados completos (JSON)</button>
          <button class="btn fantasma pequeno" type="button" id="anx-pasta-rel"><svg class="ic" aria-hidden="true"><use href="#i-pasta"/></svg>Abrir a pasta dos dados</button></div>`)}`;
    $("anx-periodo").onchange = () => {
      s.periodo = $("anx-periodo").value;
      guardar("anx-periodo", s.periodo);
      desenharEstatisticas();
    };
    $("anx-salvar-est").onclick = async () => {
      const valores = {};
      document.querySelectorAll("[data-estimativa]").forEach((i) => (valores[i.dataset.estimativa] = i.value));
      const res = await chamar("salvar_estimativas", { valores });
      if (!res.ok) return ($("anx-est-msg").innerHTML = etiqueta(res.erro, "erro"));
      await desenharEstatisticas();
      $("anx-est-msg").innerHTML = etiqueta("Estimativas salvas no código do programa.", "ok");
    };
    $("anx-anonimo").onchange = () => {
      s.anonimo = $("anx-anonimo").checked;
      guardar("anx-anonimo", s.anonimo ? "1" : "0");
    };
    document.querySelectorAll("[data-exportar]").forEach((b) => (b.onclick = () => exportar({ tipo: b.dataset.exportar, periodo: s.periodo, anonimo: s.anonimo })));
    $("anx-pasta-rel").onclick = () => chamar("abrir_pasta", { qual: "relatorios" });
  }

  async function exportar(dados) {
    const r = await chamar("exportar", dados);
    if (r.cancelou) return;
    aviso(r.ok ? r.texto : r.erro);
  }

  // ============================================================ Ajuda e licença

  async function desenharAjuda() {
    const r = await chamar("ajuda");
    if (s.tela !== "ajuda") return;
    const data = r.data_versao ? `, de ${r.data_versao.split("-").reverse().join("/")}` : "";
    const ambiente = r.ok ? grade([], (r.linhas || []).map((l) => [etiqueta(l.ok ? "Certo" : "Falta", l.ok ? "ok" : "erro"), `<b>${esc(l.nome)}</b>`, `<span class="nota">${esc(l.valor)}</span>`]))
      : banner("erro", esc(r.erro || "Não foi possível verificar."));
    $("anx-corpo").innerHTML = `${cabecalho("Ajuda e licença", `Gerar pagamento (Anexar Documentos), versão ${esc(r.versao || "")}${esc(data)} — módulo da Central de Automações.`)}
      ${cartao("Passo a passo de um processo", `<ol class="lista">${PASSO_A_PASSO.map((p) => `<li>${p}</li>`).join("")}</ol>`)}
      ${cartao("Se algo der errado", `<ul class="lista"><li>O programa explica na própria tela o que aconteceu e o que fazer.</li><li>Rodar de novo com o mesmo processo é seguro: ele não faz nada em dobro.</li>
        <li>Os detalhes técnicos ficam no arquivo registro_de_erros.txt, na pasta dos dados.</li></ul>
        <div class="acao linha"><button class="btn fantasma" type="button" id="anx-pasta-dados"><svg class="ic" aria-hidden="true"><use href="#i-pasta"/></svg>Abrir a pasta dos dados</button>
          <button class="btn fantasma pequeno" type="button" id="anx-pasta-processos"><svg class="ic" aria-hidden="true"><use href="#i-pasta"/></svg>Pasta dos processos (JPGs)</button>
          <a class="btn fantasma pequeno" href="mailto:pedrohcfalves@gmail.com">Escrever para pedrohcfalves@gmail.com</a></div>`)}
      ${cartao("Este computador", `<p class="nota">Se o programa não funcionar, mostre esta lista a quem cuida do seu computador.</p>${ambiente}<div class="acao"><button class="btn fantasma pequeno" type="button" id="anx-verificar-ajuda">Verificar de novo</button></div>`)}
      ${cartao("O que há de novo", NOVIDADES.map(([v, t]) => `<p><b>${esc(v)}</b> — ${esc(t)}</p>`).join(""))}
      ${cartao("Licença", `<p class="nota">Software de uso restrito. Todos os direitos reservados a ${esc(r.autor || "")}.</p><pre class="anx-licenca">${esc(r.licenca || "")}</pre>`)}`;
    $("anx-pasta-dados").onclick = () => chamar("abrir_pasta", { qual: "dados" });
    $("anx-pasta-processos").onclick = () => chamar("abrir_pasta", { qual: "processos" });
    $("anx-verificar-ajuda").onclick = desenharAjuda;
  }

  // ============================================================ partida

  async function mostrar() {
    s.ativo = true;
    $("tela-anexar").hidden = false;
    if (!s.iniciado) {
      s.iniciado = true;
      const r = await chamar("estado");
      if (!r.ok) {
        s.iniciado = false;
        $("anx-corpo").innerHTML = banner("erro", `Não consegui carregar o módulo: ${esc(r.erro)}`);
        return;
      }
      s.info = r;
      document.querySelectorAll("[data-anx-versao]").forEach((el) => (el.textContent = r.versao));
      // A página começa a ler do que já aconteceu só se a automação estiver rodando (para refazer a
      // tela dela); parada, o que ficou de antes não interessa.
      const execucao = r.execucao || {};
      if (execucao.rodando) {
        s.rodando = true;
        lerSempre();
      } else s.seq = Number(execucao.seq) || 0;
    }
    ir(s.tela);
  }

  function esconder() {
    s.ativo = false;
    sinalDaVez();
  }

  function ligar(ganchos) {
    g = ganchos;
    document.querySelectorAll("#anx-nav [data-anx-ir]").forEach((b) => (b.onclick = () => ir(b.dataset.anxIr)));
    $("anx-como-usar").onclick = comoUsar;
    $("anx-treino").checked = lembrar("anx-treino") === "1";
    $("anx-treino").onchange = treinoMudou;
  }

  window.lbaAnexar = {
    ligar,
    mostrar,
    esconder,
    get rodando() { return s.rodando; },
    get tela() { return s.tela; },
    get esperando() { return !!(s.rodando && s.pergunta); },
  };
})();
