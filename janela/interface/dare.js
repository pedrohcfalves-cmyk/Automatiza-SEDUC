/* Módulo DARE — as páginas do aplicativo DARE dentro da Central.
 *
 * Mesmas páginas, mesmos botões e mesmas regras da janela do DARE
 * (Início, Lançamentos, Execução, Arquivos PDF, Desempenho, Configurações e
 * a janela "Importar planilha"), no visual da Central.
 *
 * Tudo no Python passa por UMA porta: api.dare(acao, dados), que chega em
 * janela/modulo_dare.py. O motor avisa a página pelos eventos "dare_*".
 * Aberta num navegador comum (?demo), a página usa a simulação do fim do
 * arquivo para mostrar o layout.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const nBR = (v, casas = 2) => Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

  const PAGINAS = ["inicio", "lancamentos", "execucao", "arquivos", "desempenho", "configuracoes"];
  const ETAPAS = [
    ["preparo", "Preparar"], ["dare_1", "Órgão"], ["dare_2", "Receita"], ["dare_3", "CPF"], ["dare_4", "Ref./valor"],
    ["dare_5", "PDF"], ["retorno", "Voltar"], ["sei_1", "Processo"], ["sei_2", "Incluir"], ["sei_3", "Doc. externo"],
    ["sei_4", "Anexar"],
  ];
  const CAMPOS = ["processo", "cpf", "cnpj", "recolhedor", "ref", "venc", "valor"];
  const COR = { s1: "var(--serie-1)", s2: "var(--serie-4)", s3: "var(--serie-3)", s4: "var(--serie-2)", ok: "var(--verde)", erro: "var(--vermelho)", ambar: "var(--ambar)" };

  let g = null; // ganchos da Central (api, registrar eventos)

  const s = {
    ativo: false,
    pagina: "inicio",
    est: null,
    lista: { linhas: [], avisos: [], total: "", executando: false },
    editando: null,
    executando: false,
    exec: { rodou: false, total: 0, inicio: 0, tempos: [], ok: 0, erros: 0, pdfs: {}, relogio: null, parando: false },
    arquivos: null,
    desAba: "auto",
    diagFeito: false,
    monitor: false,
    serie: { cpu: [], ram: [], app_cpu: [], rede_rx: [], rede_tx: [], disco_leitura: [], disco_escrita: [] },
  };

  function formatarDuracao(seg) {
    seg = Math.max(0, Math.round(seg));
    const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), x = seg % 60;
    if (h) return `${h} h ${String(m).padStart(2, "0")} min`;
    if (m) return `${m} min ${String(x).padStart(2, "0")} s`;
    return `${x} s`;
  }

  // ----------------------------------------------------------- Python

  const DEMONSTRACAO = /[?&]demo\b/.test(location.search);

  /** A ponte com o Python. Na janela real, espera o pywebview ficar pronto (nunca cai na simulação). */
  async function apiPronta() {
    for (let i = 0; i < 100; i++) {
      const api = g && g.api();
      if (api || DEMONSTRACAO) return api;
      await new Promise((ok) => setTimeout(ok, 100));
    }
    return null;
  }

  async function chamar(acao, dados = {}) {
    try {
      const api = await apiPronta();
      if (!api && !DEMONSTRACAO) return { ok: false, erro: "A janela ainda está carregando. Tente de novo." };
      const r = api ? await api.dare(acao, dados) : await DEMO.chamar(acao, dados);
      return r || { ok: false, erro: "sem resposta" };
    } catch (erro) {
      return { ok: false, erro: String(erro && erro.message ? erro.message : erro) };
    }
  }

  // ------------------------------------------------- Avisos e perguntas

  function toast(texto, tipo = "sucesso", ms = 3500) {
    const el = document.createElement("div");
    el.className = `dare-toast ${tipo}`;
    el.textContent = texto;
    $("dare-toasts").appendChild(el);
    setTimeout(() => el.remove(), ms);
  }

  /** Caixa de pergunta no lugar do messagebox do DARE. Resolve com o valor do botão (null = fechou). */
  function perguntar(msg, botoes, titulo = "DARE") {
    return new Promise((resolver) => {
      const caixa = $("dare-confirma");
      $("dare-confirma-titulo").textContent = titulo;
      $("dare-confirma-msg").textContent = msg;
      const area = $("dare-confirma-botoes");
      area.innerHTML = "";
      const fechar = (valor) => {
        caixa.hidden = true;
        document.removeEventListener("keydown", tecla, true);
        resolver(valor);
      };
      const tecla = (e) => {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fechar(null); }
      };
      botoes.forEach((b) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = `btn ${b.classe || "fantasma"}`;
        el.textContent = b.rotulo;
        el.onclick = () => fechar(b.valor);
        area.appendChild(el);
      });
      caixa.hidden = false;
      document.addEventListener("keydown", tecla, true);
      const padrao = area.querySelector(".btn.primario, .btn.perigo") || area.lastElementChild;
      if (padrao) padrao.focus();
    });
  }
  const simNao = (msg, perigo = false) =>
    perguntar(msg, [{ rotulo: "Não", valor: false }, { rotulo: "Sim", valor: true, classe: perigo ? "perigo" : "primario" }]);

  function banner(alvo, tipo, texto, acoes = []) {
    const el = document.createElement("div");
    el.className = `dare-banner ${tipo}`;
    const t = document.createElement("div");
    t.className = "txt";
    t.textContent = texto;
    el.appendChild(t);
    acoes.forEach(([rotulo, funcao, classe]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn ${classe || "fantasma"}`;
      b.textContent = rotulo;
      b.onclick = funcao;
      el.appendChild(b);
    });
    alvo.appendChild(el);
    return el;
  }

  // ------------------------------------------------------------ Tabela

  /** Tabela com seleção (clique, Ctrl, Shift), ordenação pelo cabeçalho e "vazio". */
  class Tabela {
    constructor(el, colunas, op = {}) {
      this.el = el;
      this.colunas = colunas; // [{chave, titulo, classe, ordenar(v)}]
      this.op = { selecao: "multi", vazio: "", ordenavel: true, ...op };
      this.linhas = [];
      this.sel = new Set();
      this.ancora = null;
      this.ordem = null; // {chave, desc}
      el.addEventListener("click", (e) => this._clique(e));
      el.addEventListener("dblclick", (e) => {
        const tr = e.target.closest("tbody tr[data-id]");
        if (tr && this.op.aoDuplo) this.op.aoDuplo(tr.dataset.id);
      });
      el.addEventListener("keydown", (e) => this.op.aoTecla && this.op.aoTecla(e));
    }

    definir(linhas) {
      this.linhas = linhas; // [{id, cels: [...], classe, valores: {chave: v}}]
      const ids = new Set(linhas.map((l) => l.id));
      this.sel = new Set([...this.sel].filter((id) => ids.has(id)));
      this.render();
    }

    _ordenadas() {
      if (!this.ordem) return this.linhas;
      const i = this.colunas.findIndex((c) => c.chave === this.ordem.chave);
      const col = this.colunas[i];
      const chave = (l) => {
        const v = l.valores && l.valores[col.chave] !== undefined ? l.valores[col.chave] : l.cels[i];
        return col.ordenar ? col.ordenar(v) : String(v ?? "").toLowerCase();
      };
      const lista = [...this.linhas].sort((a, b) => (chave(a) < chave(b) ? -1 : chave(a) > chave(b) ? 1 : 0));
      return this.ordem.desc ? lista.reverse() : lista;
    }

    render() {
      const cab = this.colunas.map((c) => {
        const seta = this.ordem && this.ordem.chave === c.chave ? (this.ordem.desc ? " ▼" : " ▲") : "";
        const ord = this.op.ordenavel ? " ordenavel" : "";
        return `<th class="${c.classe || ""}${ord}" data-chave="${c.chave}">${esc(c.titulo)}${seta}</th>`;
      }).join("");
      const linhas = this._ordenadas();
      const corpo = linhas.length
        ? linhas.map((l) => `<tr data-id="${esc(l.id)}" class="${l.classe || ""}${this.sel.has(l.id) ? " sel" : ""}">${
            l.cels.map((v, i) => `<td class="${this.colunas[i].classe || ""}">${l.html && l.html[i] ? v : esc(v)}</td>`).join("")}</tr>`).join("")
        : `<tr><td class="vazio" colspan="${this.colunas.length}">${esc(this.op.vazio)}</td></tr>`;
      this.el.innerHTML = `<table><thead><tr>${cab}</tr></thead><tbody>${corpo}</tbody></table>`;
    }

    _clique(e) {
      const th = e.target.closest("th[data-chave]");
      if (th && this.op.ordenavel) {
        const chave = th.dataset.chave;
        this.ordem = this.ordem && this.ordem.chave === chave ? { chave, desc: !this.ordem.desc } : { chave, desc: false };
        return this.render();
      }
      const tr = e.target.closest("tbody tr[data-id]");
      if (!tr || this.op.selecao === "none") return;
      const id = tr.dataset.id;
      if (this.op.selecao === "multi" && (e.ctrlKey || e.metaKey)) {
        this.sel.has(id) ? this.sel.delete(id) : this.sel.add(id);
        this.ancora = id;
      } else if (this.op.selecao === "multi" && e.shiftKey && this.ancora !== null) {
        const ordem = this._ordenadas().map((l) => l.id);
        const [a, b] = [ordem.indexOf(this.ancora), ordem.indexOf(id)].sort((x, y) => x - y);
        this.sel = new Set(ordem.slice(a, b + 1));
      } else {
        this.sel = new Set([id]);
        this.ancora = id;
      }
      this._marcar(); // sem redesenhar: o duplo clique precisa da mesma linha nos dois cliques
      if (this.op.aoSelecionar) this.op.aoSelecionar();
    }

    _marcar() {
      this.el.querySelectorAll("tbody tr[data-id]").forEach((tr) => tr.classList.toggle("sel", this.sel.has(tr.dataset.id)));
    }

    selecionados() {
      return this._ordenadas().map((l) => l.id).filter((id) => this.sel.has(id));
    }

    selecionar(id) {
      this.sel = new Set(id === null || id === undefined ? [] : [String(id)]);
      this.ancora = id === null ? null : String(id);
      this.render();
      const tr = this.el.querySelector("tr.sel");
      if (tr) tr.scrollIntoView({ block: "nearest" });
    }

    linha(id) {
      return this.linhas.find((l) => l.id === String(id));
    }

    atualizarLinha(id, mudancas) {
      const l = this.linha(id);
      if (!l) return;
      Object.assign(l, mudancas);
      this.render();
    }
  }

  // ----------------------------------------------------------- Gráficos

  const NS = "http://www.w3.org/2000/svg";
  const larguraDe = (el) => Math.max(320, el.clientWidth || el.parentElement.clientWidth || 520);
  const numCurto = (v) => (v >= 10 ? nBR(v, 0) : nBR(v, v >= 1 ? 1 : 2));

  function barrasH(el, itens, unidade = "s") {
    if (!itens.length) { el.innerHTML = '<p class="dare-mudo">Sem medições ainda.</p>'; return; }
    const w = larguraDe(el), alt = 22, esp = 8, h = itens.length * (alt + esp) + 6;
    const margem = Math.min(Math.max(...itens.map(([r]) => r.length)) * 6.6 + 18, w * 0.55);
    const maior = Math.max(...itens.map(([, v]) => v)) || 1;
    const iMaior = itens.findIndex(([, v]) => v === maior);
    let svg = "";
    itens.forEach(([rot, v], i) => {
      const y = i * (alt + esp) + 3;
      const lw = Math.max(2, (w - margem - 70) * (v / maior));
      svg += `<text x="${margem - 10}" y="${y + 15}" text-anchor="end">${esc(rot)}</text>`;
      svg += `<rect x="${margem}" y="${y}" width="${lw}" height="${alt}" rx="4" style="fill:${i === iMaior ? COR.ambar : COR.s1}"/>`;
      svg += `<text x="${margem + lw + 8}" y="${y + 15}">${v >= 10 ? nBR(v, 0) : nBR(v, 2)} ${esc(unidade)}</text>`;
    });
    el.innerHTML = `<svg class="dare-grafico" viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg>`;
  }

  function linhas(el, series, op = {}) {
    const w = larguraDe(el), h = op.altura || 210, esq = 46, dir = 12, topo = 18, base = h - 26;
    const todas = series.flatMap(([, , v]) => v);
    if (!todas.length) { el.innerHTML = `<svg class="dare-grafico" viewBox="0 0 ${w} ${h}" height="${h}"><text x="${w / 2}" y="${h / 2}" text-anchor="middle">Sem dados ainda.</text></svg>`; return; }
    const max = op.maximo || Math.max(1, ...todas) * 1.1;
    const n = Math.max(2, ...series.map(([, , v]) => v.length));
    const x = (i) => esq + (w - esq - dir) * (i / (n - 1));
    const y = (v) => base - (base - topo) * Math.min(1, v / max);
    let svg = "";
    for (let k = 0; k <= 4; k++) {
      const v = (max * k) / 4, yy = y(v);
      svg += `<line class="eixo" x1="${esq}" x2="${w - dir}" y1="${yy}" y2="${yy}"/><text x="${esq - 6}" y="${yy + 4}" text-anchor="end">${numCurto(v)}</text>`;
    }
    if (op.unidade) svg += `<text x="${esq - 6}" y="${topo - 6}" text-anchor="end">${esc(op.unidade)}</text>`;
    const [rx0, rx1] = op.rotulosX || ["", ""];
    svg += `<text x="${esq}" y="${h - 6}">${esc(rx0)}</text><text x="${w - dir}" y="${h - 6}" text-anchor="end">${esc(rx1)}</text>`;
    series.forEach(([, cor, v]) => {
      if (!v.length) return;
      const desloc = n - v.length;
      const pts = v.map((val, i) => `${x(i + desloc).toFixed(1)},${y(val).toFixed(1)}`).join(" ");
      svg += `<polyline points="${pts}" style="fill:none;stroke:${cor};stroke-width:2"/>`;
    });
    const leg = series.map(([nome, cor, v]) => `<span><i style="background:${cor}"></i>${esc(nome)}${v.length ? ` · ${numCurto(v[v.length - 1])}` : ""}</span>`).join("");
    el.innerHTML = `<svg class="dare-grafico" viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg>${series.length > 1 ? `<div class="dare-legenda">${leg}</div>` : ""}`;
  }

  function colunas(el, nomes, categorias, altura = 210) {
    const w = larguraDe(el), h = altura, esq = 34, topo = 12, base = h - 24;
    const totais = categorias.map(([, v]) => v.reduce((a, b) => a + b, 0));
    const max = Math.max(1, ...totais);
    const passo = (w - esq - 6) / Math.max(1, categorias.length);
    let svg = "";
    for (let k = 0; k <= 4; k++) {
      const v = Math.round((max * k) / 4), yy = base - (base - topo) * (v / max);
      svg += `<line class="eixo" x1="${esq}" x2="${w - 6}" y1="${yy}" y2="${yy}"/><text x="${esq - 6}" y="${yy + 4}" text-anchor="end">${v}</text>`;
    }
    categorias.forEach(([rot, valores], i) => {
      let acumulado = 0;
      const x0 = esq + i * passo + passo * 0.18, lw = passo * 0.64;
      valores.forEach((v, j) => {
        if (!v) return;
        const y1 = base - (base - topo) * ((acumulado + v) / max), y0 = base - (base - topo) * (acumulado / max);
        svg += `<rect x="${x0}" y="${y1}" width="${lw}" height="${Math.max(1, y0 - y1)}" style="fill:${nomes[j][1]}"><title>${esc(rot)} · ${esc(nomes[j][0])}: ${v}</title></rect>`;
        acumulado += v;
      });
      if (categorias.length <= 16 && (i % 2 === 0 || categorias.length <= 8)) svg += `<text x="${x0 + lw / 2}" y="${h - 6}" text-anchor="middle">${esc(rot)}</text>`;
    });
    const leg = nomes.map(([nome, cor]) => `<span><i style="background:${cor}"></i>${esc(nome)}</span>`).join("");
    el.innerHTML = `<svg class="dare-grafico" viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg><div class="dare-legenda">${leg}</div>`;
  }

  function kpi(id, valor, sub = "", classe = "") {
    const el = $(id);
    el.querySelector(".val").textContent = valor;
    el.querySelector(".sub").textContent = sub;
    el.classList.remove("ok", "erro", "aviso");
    if (classe) el.classList.add(classe);
  }

  // ----------------------------------------------------- Navegação

  function ir(pagina) {
    s.pagina = pagina;
    document.querySelectorAll("#dare-nav [data-dare-ir]").forEach((b) => b.classList.toggle("ativo", b.dataset.dareIr === pagina));
    document.querySelectorAll("#tela-dare .dare-pagina").forEach((p) => (p.hidden = p.dataset.darePagina !== pagina));
    document.querySelector(".conteudo").scrollTop = 0;
    aoMostrar(pagina);
  }

  function aoMostrar(pagina) {
    if (pagina === "inicio") carregarInicio();
    else if (pagina === "lancamentos") mostrarLancamentos();
    else if (pagina === "execucao") estadoExecucao();
    else if (pagina === "arquivos") carregarArquivos();
    else if (pagina === "desempenho") trocarAbaDesempenho(s.desAba);
    else if (pagina === "configuracoes") carregarConfiguracoes();
  }

  /** O módulo DARE ficou visível na barra lateral (modulos.js). */
  function mostrar() {
    s.ativo = true;
    ir(s.pagina);
    atualizarStatus();
  }

  function esconder() {
    s.ativo = false;
  }

  function badges() {
    const n = s.lista.linhas.length;
    $("dare-badge-lista").hidden = !n;
    $("dare-badge-lista").textContent = n;
    $("dare-badge-exec").hidden = !s.executando;
    const botao = document.querySelector('.modulo[data-modulo="dare"]');
    if (!botao) return;
    let ponto = botao.querySelector(".rodando");
    if (s.executando && !ponto) {
      ponto = document.createElement("i");
      ponto.className = "rodando";
      ponto.title = "Processando DAREs";
      botao.appendChild(ponto);
    } else if (!s.executando && ponto) {
      ponto.remove();
      botao.classList.remove("atencao");
    }
  }

  // ------------------------------------------------- Barra de situação

  function pintarStatus(est) {
    const nav = $("dare-nav-estado");
    nav.classList.toggle("aberto", est.navegador.aberto);
    nav.classList.remove("abrindo");
    nav.textContent = est.navegador.aberto ? "Navegador aberto" : "Navegador fechado · abrir";
    $("dare-status-estado").textContent = s.executando ? "Processando lançamentos" : "Pronto";
    $("dare-status-pdfs").textContent = `PDFs: ${est.pdfs.qtd} (${est.pdfs.tamanho})`;
    $("dare-status-pasta").textContent = `Pasta: ${est.pasta_pdf}`;
    $("dare-status-versao").textContent = `DARE v${est.versao}`;
  }

  async function atualizarStatus() {
    const est = await chamar("estado");
    if (!est.ok) return;
    s.est = est;
    if (!s.executando) s.lista = est.lista;
    pintarStatus(est);
    badges();
    (est.mensagens || []).forEach((m) => toast(m.texto, m.tipo || "info", 5000));
    return est;
  }

  async function abrirNavegador() {
    const r = await chamar("abrir_navegador");
    if (!r.ok) return perguntar(r.erro || "Não consegui abrir o navegador.", [{ rotulo: "OK", valor: true, classe: "primario" }]);
    if (r.ja_aberto) return toast("O navegador do programa já está aberto.", "info");
    toast(`Abrindo o ${r.nome} com o SEI e o DARE...`, "info");
    const nav = $("dare-nav-estado");
    nav.classList.add("abrindo");
    nav.textContent = "Abrindo navegador...";
  }

  // ------------------------------------------------------------- Início

  let tabRecentes = null;

  async function carregarInicio() {
    const est = await atualizarStatus();
    if (!est) return;
    const avisos = $("dare-inicio-avisos");
    avisos.innerHTML = "";
    if (est.lista.linhas.length && !s.executando)
      banner(avisos, "info", `Há ${est.lista.linhas.length} lançamento(s) na lista aguardando processamento (digitados ou pendentes de uma execução anterior).`,
        [["Ver lista", () => ir("lancamentos")]]);
    if (est.pdfs.acima_do_limite)
      banner(avisos, "aviso", `A pasta dos PDFs está com ${est.pdfs.tamanho} (${est.pdfs.qtd} arquivos), acima do limite de ${est.pdfs.limite_mb} MB que você definiu.`,
        [["Limpar agora", () => ir("arquivos")]]);
    if (!est.navegador.encontrado)
      banner(avisos, "erro", "Não encontrei o Google Chrome nem o Microsoft Edge. Instale o Chrome para usar a automação.");

    kpi("dare-k-nav", est.navegador.aberto ? "Aberto" : "Fechado", est.navegador.aberto ? est.navegador.nome : "clique para abrir", est.navegador.aberto ? "ok" : "");
    kpi("dare-k-lista", String(est.lista.linhas.length), est.lista.linhas.length ? "prontos para processar" : "lista vazia");
    kpi("dare-k-hoje", String(est.hoje.ok), est.hoje.erros ? `${est.hoje.erros} com erro` : "nenhum erro", est.hoje.ok ? "ok" : "");
    kpi("dare-k-pdfs", est.pdfs.tamanho, `${est.pdfs.qtd} PDF(s) · gerenciar`);

    if (!tabRecentes)
      tabRecentes = new Tabela($("dare-recentes"), [
        { chave: "quando", titulo: "Quando" }, { chave: "situacao", titulo: "Situação", classe: "situ" },
        { chave: "processo", titulo: "Processo", classe: "mono" }, { chave: "servidor", titulo: "Servidor" },
        { chave: "valor", titulo: "Valor (R$)", classe: "num" },
      ], { selecao: "single", ordenavel: false, vazio: "Nenhuma execução ainda.\nOs DAREs processados aparecem aqui." });
    const rotulos = { SUCESSO: ["✔ Concluído", "ok"], ERRO: ["✖ Erro", "erro"], CANCELADO: ["■ Cancelado", "aviso"] };
    tabRecentes.definir(est.recentes.map((h, i) => {
      const [texto, classe] = rotulos[h.status] || [h.status, ""];
      return { id: String(i), classe, cels: [h.quando, texto, h.processo, h.servidor, h.valor] };
    }));
  }

  // --------------------------------------------------------- Lançamentos

  let tabLista = null;
  const entrada = (campo) => $(`dare-${campo}`);
  const caixaCampo = (campo) => document.querySelector(`#dare-form [data-campo="${campo}"]`);

  function erroCampo(campo, msg) {
    const c = caixaCampo(campo), dica = c.querySelector(".dica");
    c.classList.toggle("invalido", !!msg);
    dica.textContent = msg ? `✖ ${msg}` : dica.dataset.dica;
  }

  async function conferirCampo(campo) {
    const texto = entrada(campo).value.trim();
    if (!texto) return erroCampo(campo, ""), null;
    const r = await chamar("validar", { campo, texto });
    if (!r.ok) return erroCampo(campo, r.erro), null;
    erroCampo(campo, "");
    if (r.valor !== undefined && entrada(campo).value.trim() === texto) entrada(campo).value = r.valor;
    return r.valor;
  }

  function espelharRecolhedor() {
    const mesmo = $("dare-mesmo").checked;
    if (mesmo) {
      entrada("recolhedor").value = entrada("cnpj").value;
      erroCampo("recolhedor", "");
    }
    entrada("recolhedor").disabled = mesmo;
  }

  function preencherForm(campos, mesmo) {
    CAMPOS.forEach((c) => { entrada(c).value = campos[c] || ""; erroCampo(c, ""); });
    $("dare-mesmo").checked = !!mesmo;
    espelharRecolhedor();
  }

  async function novo(focar = true) {
    s.editando = null;
    const r = await chamar("novo");
    if (r.ok) preencherForm(r.campos, r.mesmo);
    $("dare-form-titulo").textContent = "Novo lançamento";
    $("dare-btn-salvar").textContent = "＋ Adicionar à lista";
    $("dare-btn-limpar").textContent = "Limpar";
    if (focar) { entrada("processo").focus(); entrada("processo").select(); }
  }

  function aplicarNovo(r) {
    s.editando = null;
    preencherForm(r.campos, r.mesmo);
    $("dare-form-titulo").textContent = "Novo lançamento";
    $("dare-btn-salvar").textContent = "＋ Adicionar à lista";
    $("dare-btn-limpar").textContent = "Limpar";
  }

  async function salvar() {
    if (s.executando) return;
    const valores = {};
    CAMPOS.forEach((c) => (valores[c] = entrada(c).value));
    const r = await chamar("salvar", { valores, indice: s.editando });
    if (!r.ok) {
      if (r.erros) {
        CAMPOS.forEach((c) => erroCampo(c, r.erros[c] || ""));
        const primeiro = CAMPOS.find((c) => r.erros[c]);
        if (primeiro) entrada(primeiro).focus();
        return toast("Corrija os campos destacados em vermelho.", "erro");
      }
      return toast(r.erro || "Não consegui salvar.", "erro");
    }
    toast(r.mensagem);
    pintarLista(r.lista, r.n - 1);
    aplicarNovo(r.novo);
    entrada("processo").focus();
  }

  async function editar(indice) {
    if (s.executando) return;
    const r = await chamar("editar", { indice });
    if (!r.ok) return;
    s.editando = indice;
    preencherForm(r.campos, r.mesmo);
    $("dare-form-titulo").textContent = r.titulo;
    $("dare-btn-salvar").textContent = "✔ Salvar alterações";
    $("dare-btn-limpar").textContent = "Cancelar";
    entrada("processo").focus();
    entrada("processo").select();
  }

  const indicesSelecionados = () => tabLista.selecionados().map(Number).sort((a, b) => a - b);

  async function duplicar() {
    const sel = indicesSelecionados();
    if (sel.length !== 1 || s.executando) return;
    const r = await chamar("duplicar", { indice: sel[0] });
    if (!r.ok) return;
    pintarLista(r.lista, r.indice);
    await editar(r.indice);
    toast("Cópia criada logo abaixo. Ajuste o processo e o CPF.", "info");
  }

  async function remover() {
    const sel = indicesSelecionados();
    if (!sel.length || s.executando) return;
    const linha = s.lista.linhas[sel[0]];
    const texto = sel.length === 1 ? `Remover o lançamento ${sel[0] + 1} (${linha ? linha.processo : ""})?` : `Remover os ${sel.length} lançamentos selecionados?`;
    if (!(await simNao(texto))) return;
    const r = await chamar("remover", { indices: sel });
    if (!r.ok) return;
    if (s.editando !== null) aplicarNovo(r.novo);
    pintarLista(r.lista);
    toast(`${sel.length} lançamento(s) removido(s).`, "info");
  }

  async function esvaziar() {
    if (!s.lista.linhas.length || s.executando) return;
    if (!(await simNao(`Remover TODOS os ${s.lista.linhas.length} lançamentos da lista?\n\nOs PDFs e o histórico não são afetados.`, true))) return;
    const r = await chamar("esvaziar");
    if (!r.ok) return;
    pintarLista(r.lista);
    aplicarNovo(r.novo);
    entrada("processo").focus();
  }

  const valorCentavos = (v) => Number(String(v || "").replace(/\D/g, "") || 0);
  const dataOrdem = (v) => { const [d, m, a] = String(v || "").split("/"); return a ? `${a}${m}${d}` : ""; };

  function pintarLista(lista, selecionar) {
    if (lista) s.lista = lista;
    if (!tabLista)
      tabLista = new Tabela($("dare-lista"), [
        { chave: "n", titulo: "#", classe: "num", ordenar: Number }, { chave: "processo", titulo: "Processo SEI", classe: "mono" },
        { chave: "cpf", titulo: "CPF", classe: "mono" }, { chave: "ref", titulo: "Ref.", classe: "cen" },
        { chave: "venc", titulo: "Vencimento", classe: "cen", ordenar: dataOrdem }, { chave: "valor", titulo: "Valor (R$)", classe: "num", ordenar: valorCentavos },
        { chave: "origem", titulo: "Origem" },
      ], {
        vazio: "Nenhum lançamento ainda.\n\nPreencha o formulário ao lado e clique em “Adicionar à lista”, ou importe uma planilha do Excel.",
        aoDuplo: (id) => editar(Number(id)),
        aoSelecionar: estadoBotoes,
        aoTecla: (e) => { if (e.key === "Delete") { e.preventDefault(); remover(); } },
      });
    tabLista.definir(s.lista.linhas.map((l, i) => ({
      id: String(i), cels: [l.n, l.processo, l.cpf, l.ref, l.venc, l.valor, l.origem],
    })));
    if (selecionar !== undefined && selecionar !== null) tabLista.selecionar(selecionar);
    const avisos = $("dare-lista-avisos");
    avisos.innerHTML = "";
    s.lista.avisos.slice(0, 5).forEach((t) => {
      const el = document.createElement("div");
      el.textContent = `⚠  ${t}`;
      avisos.appendChild(el);
    });
    if (s.lista.avisos.length > 5) {
      const el = document.createElement("div");
      el.textContent = `… e mais ${s.lista.avisos.length - 5} aviso(s).`;
      avisos.appendChild(el);
    }
    $("dare-lista-total").textContent = s.lista.total;
    estadoBotoes();
    badges();
  }

  function estadoBotoes() {
    const rodando = s.executando;
    const sel = tabLista ? tabLista.selecionados().length : 0;
    const n = s.lista.linhas.length;
    $("dare-btn-editar").disabled = sel !== 1 || rodando;
    $("dare-btn-duplicar").disabled = sel !== 1 || rodando;
    $("dare-btn-remover").disabled = !sel || rodando;
    $("dare-btn-esvaziar").disabled = !n || rodando;
    $("dare-btn-iniciar").disabled = !n || rodando;
    $("dare-btn-importar").disabled = rodando;
    $("dare-btn-salvar").disabled = rodando;
    $("dare-btn-iniciar").textContent = n ? `▶ Iniciar processamento (${n})` : "▶ Iniciar processamento";
  }

  async function mostrarLancamentos() {
    const aviso = $("dare-lanc-aviso");
    aviso.innerHTML = "";
    if (s.executando)
      banner(aviso, "info", "Há um processamento em andamento: a lista fica bloqueada até ele terminar.", [["Acompanhar", () => ir("execucao")]]);
    if (!$("dare-fixos").textContent && s.est) $("dare-fixos").textContent = s.est.fixos_texto || "";
    const r = await chamar("lista");
    if (r.ok) pintarLista(r);
    if (s.editando === null && !entrada("processo").value.trim() && !entrada("cpf").value.trim()) await novo(false);
  }

  async function iniciar() {
    if (!s.lista.linhas.length || s.executando) return;
    if (s.editando !== null || entrada("processo").value.trim()) {
      if (!(await simNao("Há dados no formulário que ainda não foram adicionados à lista.\n\nIniciar mesmo assim (sem eles)?"))) return;
    }
    const a = await chamar("avisos_inicio");
    let texto = `Processar ${a.n} lançamento(s) agora?\n\nPara cada um, o programa gera o DARE, salva o PDF e anexa no SEI, usando o navegador aberto por ele. Evite mexer nas abas do DARE e do SEI enquanto ele trabalha.`;
    if (a.avisos && a.avisos.length) texto += `\n\nAtenção: há ${a.avisos.length} aviso(s) na lista (ex.: ${a.avisos[0]})`;
    if (!(await simNao(texto))) return;
    await comecar();
  }

  async function comecar() {
    const r = await chamar("iniciar");
    if (!r.ok) return toast(r.erro || "Não consegui começar.", "erro", 6000);
    s.executando = true;
    prepararExecucao(r.lotes);
    badges();
    estadoBotoes();
    ir("execucao");
  }

  // -------------------------------------------------- Importar planilha

  const imp = { campos: [], opcoes: [], excel: false, lidos: null, selAberta: -1 };
  const NENHUMA = "", FIXO = "fixo";

  async function importarPlanilha() {
    if (s.executando) return toast("Aguarde o processamento atual terminar.", "aviso");
    if (s.pagina !== "lancamentos") ir("lancamentos");
    const r = await chamar("planilha_inicio");
    if (!r.ok) return toast(r.erro || "Não consegui abrir a importação.", "erro");
    imp.campos = r.campos;
    imp.excel = r.excel;
    imp.lidos = null;
    imp.opcoes = [];
    imp.selAberta = -1;
    $("dare-imp-modo").textContent = r.excel
      ? "Usando o Microsoft Excel. Planilhas em “Modo de Exibição Protegido” não aparecem na lista: clique em “Habilitar edição” no Excel."
      : "Excel não encontrado neste computador: arquivos .xlsx e .xlsm são lidos diretamente, sem precisar dele.";
    $("dare-imp-abertas-caixa").hidden = !r.excel;
    pintarAbertas(r.abertas || []);
    $("dare-imp-arquivo").textContent = "Nenhuma planilha escolhida.";
    $("dare-imp-aba").innerHTML = "";
    $("dare-imp-cab").value = "1";
    $("dare-imp-colunas").textContent = "";
    $("dare-imp-origem").textContent = "";
    $("dare-imp-falta").textContent = "";
    $("dare-imp-de").value = "";
    $("dare-imp-ate").value = "";
    $("dare-imp-ultima").textContent = "";
    pintarMapa({ campos: {} });
    invalidarLeitura();
    $("dare-importar").hidden = false;
  }

  function pintarAbertas(abertas) {
    const caixa = $("dare-imp-abertas");
    caixa.innerHTML = abertas.length
      ? abertas.map((p, i) => `<button type="button" data-aberta="${i}" class="${i === imp.selAberta ? "sel" : ""}">${esc(p.nome)}    —    <span class="dare-mudo">${esc(p.caminho)}</span></button>`).join("")
      : '<div class="vazio">(nenhuma planilha aberta — use “Procurar arquivo…”)</div>';
  }

  function opcoesColuna() {
    return [{ valor: NENHUMA, rotulo: "— não usar (valor padrão) —" }]
      .concat(imp.opcoes.map((o) => ({ valor: String(o.coluna), rotulo: o.rotulo })))
      .concat([{ valor: FIXO, rotulo: "✎ Mesmo valor em todas as linhas…" }]);
  }

  function pintarMapa(mapa) {
    const area = $("dare-imp-mapa");
    const opcoes = opcoesColuna();
    area.innerHTML = imp.campos.map((c) => {
      const origem = (mapa.campos || {})[c.campo] || {};
      let valor = NENHUMA;
      if (origem.fixo !== undefined && origem.fixo !== null && origem.fixo !== "") valor = FIXO;
      else if (origem.coluna) valor = String(origem.coluna);
      const extra = valor !== NENHUMA && valor !== FIXO && !opcoes.some((o) => o.valor === valor)
        ? `<option value="${valor}">Coluna ${valor}</option>` : "";
      const ops = opcoes.map((o) => `<option value="${esc(o.valor)}"${o.valor === valor ? " selected" : ""}>${esc(o.rotulo)}</option>`).join("") + extra;
      return `<label for="dare-mapa-${c.campo}">${esc(c.rotulo)}${c.obrigatorio ? " *" : ""}</label>
        <select class="dare-input" id="dare-mapa-${c.campo}" data-mapa="${c.campo}">${ops}</select>
        <input class="dare-input" id="dare-fixo-${c.campo}" data-fixo="${c.campo}" value="${esc(valor === FIXO ? origem.fixo : "")}"${valor === FIXO ? "" : " disabled"}>`;
    }).join("");
  }

  function mapaDaTela() {
    const campos = {};
    imp.campos.forEach((c) => {
      const v = $(`dare-mapa-${c.campo}`).value;
      if (v === FIXO) {
        const fixo = $(`dare-fixo-${c.campo}`).value.trim();
        if (fixo) campos[c.campo] = { fixo };
      } else if (v) campos[c.campo] = { coluna: Number(v) };
    });
    return { campos, linha_cabecalho: Math.max(0, parseInt($("dare-imp-cab").value, 10) || 0) };
  }

  function aplicarLinhas(l) {
    if (!l) return;
    $("dare-imp-de").value = l.de;
    $("dare-imp-ate").value = l.ate || "";
    $("dare-imp-ultima").textContent = l.ultima === null || l.ultima === undefined ? "" :
      l.ultima ? `Última linha com dados: ${l.ultima}.` : "Não encontrei dados nas colunas escolhidas.";
  }

  function aplicarColunas(c) {
    imp.opcoes = c.opcoes;
    $("dare-imp-colunas").textContent = c.encontradas.length
      ? "Colunas encontradas — " + c.encontradas.join("   ·   ")
      : "Nenhum título nessa linha. Se a planilha não tem cabeçalho, use 0 e escolha as colunas pela letra.";
  }

  async function usarPasta(r) {
    if (!r.ok) {
      if (!r.cancelado) await perguntar(r.erro || "Não consegui abrir a planilha.", [{ rotulo: "OK", valor: true, classe: "primario" }]);
      return;
    }
    $("dare-imp-arquivo").textContent = `✔  ${r.nome}\n${r.caminho}`;
    $("dare-imp-aba").innerHTML = r.abas.map((a) => `<option>${esc(a)}</option>`).join("");
    if (r.abas.length) await usarAba();
  }

  async function usarAba() {
    const r = await chamar("planilha_aba", { aba: $("dare-imp-aba").value });
    if (!r.ok) return perguntar(r.erro || "Não consegui ler a aba.", [{ rotulo: "OK", valor: true, classe: "primario" }]);
    $("dare-imp-cab").value = r.mapa.linha_cabecalho;
    aplicarColunas(r.colunas);
    pintarMapa(r.mapa);
    $("dare-imp-origem").textContent = r.origem;
    aplicarLinhas(r.linhas);
    invalidarLeitura();
  }

  async function mudarCabecalho() {
    if (!$("dare-imp-aba").value) return;
    const atual = mapaDaTela();
    const r = await chamar("planilha_cabecalho", atual);
    if (!r.ok) return;
    aplicarColunas(r.colunas);
    pintarMapa(atual);
    aplicarLinhas(r.linhas);
    invalidarLeitura();
  }

  async function mudouCampo(campo) {
    const fixo = $(`dare-fixo-${campo}`);
    if ($(`dare-mapa-${campo}`).value === FIXO) { fixo.disabled = false; fixo.focus(); } else fixo.disabled = true;
    const r = await chamar("planilha_linhas", mapaDaTela());
    if (r.ok) aplicarLinhas(r.linhas);
    invalidarLeitura();
  }

  function invalidarLeitura() {
    imp.lidos = null;
    $("dare-imp-leitura").textContent = "";
    $("dare-imp-leitura").className = "dare-leitura";
    $("dare-imp-problemas").hidden = true;
    estadoImportacao();
  }

  async function lerPlanilha() {
    if (!$("dare-imp-aba").value) return perguntar("Escolha uma planilha primeiro.", [{ rotulo: "OK", valor: true, classe: "primario" }]);
    const mapa = mapaDaTela();
    const de = $("dare-imp-de").value.trim(), ate = $("dare-imp-ate").value.trim();
    if (mapa.linha_cabecalho && Number(de) <= mapa.linha_cabecalho &&
      !(await simNao(`A linha ${mapa.linha_cabecalho} é o cabeçalho e seria lida como dado. Continuar?`))) return;
    $("dare-imp-ler").disabled = true;
    const r = await chamar("planilha_ler", { ...mapa, de, ate });
    $("dare-imp-ler").disabled = false;
    if (!r.ok) {
      if (r.falta) { $("dare-imp-falta").textContent = "✖ Falta indicar: " + r.falta.join(", "); return; }
      return perguntar(r.erro || "Não consegui ler a planilha.", [{ rotulo: "OK", valor: true, classe: "primario" }]);
    }
    $("dare-imp-falta").textContent = "";
    imp.lidos = r;
    const partes = [`✔ ${r.validas} linha(s) válida(s)`];
    if (r.problemas.length) partes.push(`✖ ${r.problemas.length} com problema`);
    if (r.vazias) partes.push(`${r.vazias} em branco`);
    if (r.ocultas) partes.push(`${r.ocultas} oculta(s)/filtrada(s)`);
    const el = $("dare-imp-leitura");
    el.textContent = partes.join("   ·   ");
    el.className = "dare-leitura " + (r.validas && !r.problemas.length ? "ok" : r.validas ? "aviso" : "erro");
    const prob = $("dare-imp-problemas");
    if (r.problemas.length) {
      const t = new Tabela(prob, [{ chave: "linha", titulo: "Linha", classe: "num" }, { chave: "p", titulo: "Problema (a linha fica de fora)", classe: "res" }],
        { selecao: "single", ordenavel: false });
      t.definir(r.problemas.map((p, i) => ({ id: String(i), classe: "erro", cels: [p.linha, p.mensagem] })));
      prob.hidden = false;
    } else prob.hidden = true;
    estadoImportacao();
  }

  function estadoImportacao() {
    const n = imp.lidos ? imp.lidos.validas : 0;
    $("dare-imp-adicionar").disabled = !n;
    $("dare-imp-adicionar").textContent = n ? `Adicionar ${n} lançamento(s) à lista` : "Adicionar à lista";
    $("dare-imp-rodape").textContent = n ? "Você ainda poderá conferir e editar tudo antes de iniciar."
      : "Escolha a planilha, confira as colunas e clique em “Ler planilha”.";
  }

  async function confirmarImportacao() {
    const r = imp.lidos;
    if (!r || !r.validas) return;
    if (r.problemas.length && !(await simNao(`${r.problemas.length} linha(s) com problema ficarão de fora.\n\nContinuar só com as ${r.validas} válida(s)?`))) return;
    let substituir = false;
    if (s.lista.linhas.length) {
      const escolha = await perguntar(
        `A lista já tem ${s.lista.linhas.length} lançamento(s).\n\nAcrescentar: os ${r.validas} da planilha entram no fim da lista.\nSubstituir: a lista passa a ter só os da planilha.`,
        [{ rotulo: "Cancelar", valor: null }, { rotulo: "Substituir", valor: "substituir" }, { rotulo: "Acrescentar", valor: "acrescentar", classe: "primario" }]);
      if (!escolha) return fecharImportacao();
      substituir = escolha === "substituir";
    }
    const f = await chamar("planilha_confirmar", { substituir });
    if (!f.ok) return toast(f.erro || "Não consegui importar.", "erro");
    $("dare-importar").hidden = true;
    pintarLista(f.lista);
    aplicarNovo(f.novo);
    toast(`${f.n} lançamento(s) importado(s) da planilha. Confira e clique em Iniciar.`);
  }

  async function fecharImportacao() {
    $("dare-importar").hidden = true;
    await chamar("planilha_fechar");
  }

  async function criarModelo() {
    let r = await chamar("planilha_modelo", {});
    if (!r.ok && r.existe) {
      const de_novo = await simNao("Já existe uma planilha modelo. Criar de novo (substitui o arquivo)?\n\nNão = só abrir a que já existe.");
      r = await chamar("planilha_modelo", de_novo ? { substituir: true } : { so_abrir: true });
      if (!de_novo) return;
    }
    if (!r.ok) return perguntar(r.erro || "Não consegui criar o modelo.", [{ rotulo: "OK", valor: true, classe: "primario" }]);
    if (r.caminho) {
      await perguntar(`Modelo criado em:\n${r.caminho}\n\nPreencha uma linha por DARE, salve e depois escolha o arquivo aqui (ou atualize a lista de abertas).`,
        [{ rotulo: "OK", valor: true, classe: "primario" }]);
      recarregarAbertas();
    }
  }

  async function recarregarAbertas() {
    const r = await chamar("planilha_inicio");
    if (!r.ok) return;
    imp.excel = r.excel;
    imp.selAberta = -1;
    $("dare-imp-abertas-caixa").hidden = !r.excel;
    pintarAbertas(r.abertas || []);
  }

  // ----------------------------------------------------------- Execução

  let tabExec = null;

  function estadoExecucao() {
    const rodou = s.exec.rodou || s.executando;
    $("dare-exec-vazio").hidden = rodou;
    $("dare-exec-painel").hidden = !rodou;
    $("dare-btn-parar").disabled = !(s.executando && !s.exec.parando);
  }

  function pintarEtapas(atual, concluido = false, erro = false) {
    const i = ETAPAS.findIndex(([c]) => c === atual);
    const caixa = $("dare-exec-etapas");
    caixa.classList.toggle("erro", erro);
    caixa.innerHTML = ETAPAS.map(([, rot], k) =>
      `<span class="${concluido || (i >= 0 && k < i) ? "feita" : k === i ? "atual" : ""}">${esc(rot)}</span>`).join("");
  }

  function numeros() {
    const e = s.exec;
    const decorrido = e.inicio ? (Date.now() - e.inicio) / 1000 : 0;
    $("dare-n-ok").textContent = e.ok;
    $("dare-n-erro").textContent = e.erros;
    $("dare-n-decorrido").textContent = formatarDuracao(decorrido);
    if (e.tempos.length) {
      const media = e.tempos.reduce((a, b) => a + b, 0) / e.tempos.length;
      const faltam = e.total - e.tempos.length;
      $("dare-n-media").textContent = `${nBR(media, 1)} s`;
      $("dare-n-restante").textContent = s.executando && faltam ? formatarDuracao(media * faltam) : "—";
    } else {
      $("dare-n-media").textContent = "—";
      $("dare-n-restante").textContent = "—";
    }
  }

  function logLinha(hora, texto, nivel = "") {
    const pre = $("dare-log");
    const perto = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    const linha = document.createElement("div");
    linha.innerHTML = `<span class="hora">${esc(hora)}</span>  <span class="${nivel}">${esc(texto)}</span>`;
    pre.appendChild(linha);
    while (pre.childElementCount > 3000) pre.firstElementChild.remove();
    if (perto) pre.scrollTop = pre.scrollHeight;
  }
  const agora = () => new Date().toTimeString().slice(0, 8);
  const logLocal = (texto, nivel = "") => logLinha(agora(), texto, nivel);

  function prepararExecucao(lotes) {
    const e = s.exec;
    Object.assign(e, { rodou: true, total: lotes.length, inicio: Date.now(), tempos: [], ok: 0, erros: 0, pdfs: {}, parando: false });
    $("dare-exec-avisos").innerHTML = "";
    if (!tabExec)
      tabExec = new Tabela($("dare-exec-tabela"), [
        { chave: "n", titulo: "#", classe: "num" }, { chave: "situacao", titulo: "Situação", classe: "situ" },
        { chave: "processo", titulo: "Processo", classe: "mono" }, { chave: "servidor", titulo: "Servidor / detalhe", classe: "res" },
        { chave: "tempo", titulo: "Tempo", classe: "num" },
      ], { selecao: "single", ordenavel: false, aoDuplo: abrirPdfDaLinha });
    tabExec.definir(lotes.map((d, i) => ({ id: String(i + 1), cels: [i + 1, "Aguardando", d.processo, d.cpf, ""] })));
    $("dare-exec-barra").style.width = "0%";
    $("dare-exec-barra-caixa").classList.remove("dare-barra-ok");
    $("dare-exec-lote").textContent = `Preparando ${e.total} lançamento(s)…`;
    $("dare-exec-detalhe").textContent = "Abrindo e conectando ao navegador.";
    pintarEtapas(null);
    $("dare-exec-etapa").textContent = "";
    $("dare-log").innerHTML = "";
    logLocal(`Início do processamento de ${e.total} lançamento(s).`, "destaque");
    $("dare-exec-sub").textContent = "Processando… você pode usar outras partes do programa enquanto isso.";
    numeros();
    clearInterval(e.relogio);
    e.relogio = setInterval(() => s.executando && numeros(), 1000);
    estadoExecucao();
  }

  async function abrirPdfDaLinha(id) {
    const caminho = s.exec.pdfs[id];
    if (!caminho) return;
    const r = await chamar("abrir_arquivo", { caminho });
    if (!r.ok) toast("O PDF não está mais na pasta.", "aviso");
  }

  async function parar() {
    if (!s.executando) return;
    s.exec.parando = true;
    await chamar("parar");
    $("dare-btn-parar").disabled = true;
    $("dare-exec-etapa").textContent = "Parando: o lançamento atual vai terminar e os demais ficam pendentes.";
    logLocal("Parada solicitada: termina o lançamento atual e para.", "aviso");
  }

  function mostrarLogin() {
    const caixa = $("dare-exec-avisos");
    caixa.querySelectorAll(".dare-banner:not(.erro)").forEach((b) => b.remove());
    $("dare-exec-lote").textContent = "Aguardando o seu login";
    $("dare-exec-detalhe").textContent = "Entre com a sua conta nas abas do DARE e do SEI.";
    const el = banner(caixa, "aviso",
      "Primeiro acesso nesta sessão: no navegador da automação, entre com a sua conta no DARE e no SEI. Quando as duas abas estiverem logadas, clique no botão ao lado.",
      [["✔ Já entrei nos dois sistemas", async () => {
        await chamar("login_ok");
        el.remove();
        logLocal("Login confirmado. Começando os lançamentos.", "destaque");
        const botao = document.querySelector('.modulo[data-modulo="dare"]');
        if (botao) botao.classList.remove("atencao");
      }, "primario"]]);
    const botao = document.querySelector('.modulo[data-modulo="dare"]');
    if (botao) botao.classList.add("atencao");
    toast("Faça o login no DARE e no SEI e confirme aqui.", "aviso", 6000);
  }

  function loteInicio(d) {
    $("dare-exec-lote").textContent = `Lançamento ${d.indice} de ${d.total}`;
    const origem = d.dados.origem && d.dados.origem !== "digitado" ? ` · ${d.dados.origem}` : "";
    $("dare-exec-detalhe").textContent = `Processo ${d.dados.processo} · CPF ${d.dados.cpf} · R$ ${d.dados.valor}${origem}`;
    pintarEtapas("preparo");
    $("dare-exec-etapa").textContent = "Etapa atual: Preparar formulário";
    tabExec.atualizarLinha(String(d.indice), { classe: "andamento", cels: Object.assign([...tabExec.linha(String(d.indice)).cels], { 1: "▶ Processando" }) });
    const tr = $("dare-exec-tabela").querySelector(`tr[data-id="${d.indice}"]`);
    if (tr) tr.scrollIntoView({ block: "nearest" });
  }

  function loteFim(d) {
    const e = s.exec, r = d.resultado, id = String(d.indice);
    e.tempos.push(d.segundos);
    let situacao, classe, detalhe;
    if (r.sucesso) {
      e.ok += 1;
      [situacao, classe, detalhe] = ["✔ Concluído", "ok", r.servidor || "—"];
      e.pdfs[id] = r.pdf;
    } else {
      e.erros += 1;
      [situacao, classe] = ["✖ Erro", "erro"];
      detalhe = r.erro + (r.pdf ? " · DARE gerado, não anexado" : "");
      if (r.pdf) e.pdfs[id] = r.pdf;
    }
    const cels = [...tabExec.linha(id).cels];
    cels[1] = situacao; cels[3] = detalhe; cels[4] = `${nBR(d.segundos, 1)} s`;
    tabExec.atualizarLinha(id, { classe, cels });
    $("dare-exec-barra").style.width = `${(e.tempos.length / Math.max(1, e.total)) * 100}%`;
    pintarEtapas(null, r.sucesso, !r.sucesso);
    numeros();
  }

  function fim(d) {
    const e = s.exec;
    clearInterval(e.relogio);
    s.executando = false;
    e.parando = false;
    const resultados = d.resultados || [];
    const total = d.total || e.total, ok = resultados.filter((r) => r.sucesso).length;
    e.erros = resultados.length - ok;
    // Linhas que não receberam "lote_fim" (falha geral ou parada antes delas).
    for (let i = 1; i <= total; i++) {
      const l = tabExec && tabExec.linha(String(i));
      if (!l || ["ok", "erro"].includes(l.classe)) continue;
      const cels = [...l.cels];
      const r = resultados[i - 1];
      if (r && !r.sucesso) { cels[1] = "✖ Erro"; cels[3] = r.erro; tabExec.atualizarLinha(String(i), { classe: "erro", cels }); }
      else if (!r) { cels[1] = "■ Não processado"; tabExec.atualizarLinha(String(i), { classe: "aviso", cels }); }
    }
    const decorrido = formatarDuracao((Date.now() - e.inicio) / 1000);
    numeros();
    $("dare-n-restante").textContent = "—";
    $("dare-exec-etapa").textContent = "";
    pintarEtapas(null, !d.pendentes);
    const caixa = $("dare-exec-avisos");
    caixa.querySelectorAll(".dare-banner:not(.erro)").forEach((b) => b.remove());
    if (!d.pendentes) {
      $("dare-exec-barra").style.width = "100%";
      $("dare-exec-barra-caixa").classList.add("dare-barra-ok");
      $("dare-exec-lote").textContent = "Tudo pronto!";
      $("dare-exec-detalhe").textContent = `${ok} de ${total} lançamento(s) concluído(s) em ${decorrido}.`;
      banner(caixa, "sucesso", `Concluído: ${ok} de ${total} DARE(s) gerado(s) e anexado(s) no SEI em ${decorrido}.`);
      toast(`Processamento concluído: ${ok} de ${total} com sucesso.`);
    } else {
      const naoFeitos = total - resultados.length;
      const partes = [`${ok} de ${total} concluído(s)`];
      if (e.erros) partes.push(`${e.erros} com erro`);
      if (naoFeitos) partes.push(`${naoFeitos} não processado(s)`);
      $("dare-exec-lote").textContent = d.interrompido ? "Interrompido" : "Terminou com pendências";
      $("dare-exec-detalhe").textContent = partes.join(" · ") + ` · ${decorrido}`;
      const rotulo = d.pendentes === 1 ? "↻ Processar o pendente" : `↻ Processar os ${d.pendentes} pendentes`;
      banner(caixa, "aviso",
        `${partes.join(" · ")}. Os pendentes continuam na lista de Lançamentos. Se um DARE foi gerado mas não anexado, confira o processo no SEI antes de repetir.`,
        [[rotulo, comecar, "primario"], ["Ver lista", () => ir("lancamentos")]]);
    }
    if (d.erro) banner(caixa, "erro", `O processamento parou: ${d.erro}`);
    $("dare-exec-sub").textContent = `Último processamento: ${ok} de ${total} concluído(s) · ${decorrido}`;
    if (d.lista) pintarLista(d.lista);
    badges();
    estadoBotoes();
    estadoExecucao();
    atualizarStatus();
  }

  function eventoMotor(d) {
    switch (d.evento) {
      case "status": $("dare-exec-detalhe").textContent = d.texto; break;
      case "conectado":
        logLocal(`Navegador conectado em ${nBR(d.segundos, 1)} s.`, "destaque");
        $("dare-exec-detalhe").textContent = "Navegador conectado.";
        break;
      case "aguardando_login": mostrarLogin(); break;
      case "login_confirmado":
        $("dare-exec-avisos").querySelectorAll(".dare-banner:not(.erro)").forEach((b) => b.remove());
        break;
      case "lote_inicio": loteInicio(d); break;
      case "etapa":
        pintarEtapas(d.etapa);
        $("dare-exec-etapa").textContent = `Etapa atual: ${d.rotulo}`;
        break;
      case "lote_fim": loteFim(d); break;
      case "erro_geral":
        banner($("dare-exec-avisos"), "erro", `O processamento parou: ${d.mensagem}\nConfira se o navegador da automação está aberto e tente de novo.`);
        break;
      case "fim": fim(d); break;
    }
  }

  // ------------------------------------------------------- Arquivos PDF

  let tabArq = null;
  const tamanhoBytes = (t) => {
    const [n, u] = String(t).replace(",", ".").split(" ");
    return Number(n) * ({ bytes: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3 }[u] || 0);
  };

  async function carregarArquivos() {
    const r = await chamar("arquivos");
    if (!r.ok) return;
    s.arquivos = r;
    $("dare-arq-pasta").textContent = `Pasta: ${r.pasta}`;
    kpi("dare-k-qtd", String(r.qtd), "arquivos PDF");
    kpi("dare-k-tam", r.tamanho, r.qtd ? `média ${r.media}` : "—");
    if (r.mais_antigo) kpi("dare-k-antigo", r.mais_antigo.data, `há ${r.mais_antigo.dias} dia(s)`);
    else kpi("dare-k-antigo", "—", "");
    kpi("dare-k-prot", String(r.protegidos), r.protegidos ? "protegidos da limpeza" : "nenhum pendente", r.protegidos ? "aviso" : "");
    const p = r.pref;
    if (!$("dare-dias").value) $("dare-dias").value = p.limpeza_dias || 30;
    if (!$("dare-ate").value) $("dare-ate").value = r.padrao_data;
    $("dare-lixeira").checked = p.usar_lixeira;
    $("dare-proteger").checked = p.proteger_nao_anexados;
    $("dare-auto").checked = p.limpeza_automatica;
    $("dare-auto-dias").value = p.limpeza_dias;
    $("dare-aviso-mb").value = p.aviso_tamanho_mb;
    $("dare-ultima-limpeza").textContent = p.ultima_limpeza ? `Última limpeza: ${p.ultima_limpeza}` : "Nenhuma limpeza feita ainda.";
    if (!tabArq)
      tabArq = new Tabela($("dare-arq-tabela"), [
        { chave: "nome", titulo: "Arquivo" }, { chave: "data", titulo: "Gerado em", classe: "cen", ordenar: (v) => { const [d, h] = String(v).split(" "); return dataOrdem(d) + (h || ""); } },
        { chave: "tamanho", titulo: "Tamanho", classe: "num", ordenar: tamanhoBytes }, { chave: "situacao", titulo: "Situação", classe: "situ" },
      ], {
        vazio: "A pasta dos PDFs está vazia.",
        aoDuplo: async (id) => { const r2 = await chamar("abrir_arquivo", { caminho: id }); if (!r2.ok) toast(r2.erro || "Não consegui abrir.", "aviso"); },
        aoSelecionar: previa,
      });
    tabArq.definir(r.arquivos.map((a) => ({
      id: a.caminho, classe: a.protegido ? "protegido" : "",
      cels: [a.nome, a.data, a.tamanho, a.protegido ? "⚠ Gerado, não anexado" : "✔ Gerado"],
    })));
    await previa();
  }

  const criterio = () => (document.querySelector('input[name="dare-criterio"]:checked') || {}).value || "mais_antigos";
  const escolhaLimpeza = () => ({
    criterio: criterio(), dias: $("dare-dias").value, data: $("dare-ate").value,
    selecionados: tabArq ? tabArq.selecionados() : [], proteger: $("dare-proteger").checked, lixeira: $("dare-lixeira").checked,
  });

  async function previa() {
    if (!tabArq) return;
    const sel = tabArq.selecionados().length;
    $("dare-arq-sel").textContent = sel ? `${sel} selecionado(s)` : "";
    const r = await chamar("previa", escolhaLimpeza());
    const marcar = new Set(r.ok ? r.caminhos : []);
    tabArq.linhas.forEach((l) => {
      const base = (l.classe || "").replace(/\s*apagar/g, "");
      l.classe = marcar.has(l.id) ? `${base} apagar` : base;
    });
    tabArq.el.querySelectorAll("tbody tr[data-id]").forEach((tr) => tr.classList.toggle("apagar", marcar.has(tr.dataset.id)));
    const txt = $("dare-previa-txt"), btn = $("dare-btn-apagar");
    if (!r.ok) { txt.textContent = r.erro; txt.className = "txt erro"; btn.disabled = true; return; }
    if (!r.qtd) {
      txt.textContent = "Nenhum PDF se encaixa nessa escolha." + (criterio() === "selecionados" ? " Selecione arquivos na lista." : "");
      txt.className = "txt mudo"; btn.disabled = true; return;
    }
    txt.textContent = `Serão removidos ${r.qtd} PDF(s) · ${r.tamanho}`;
    txt.className = "txt erro";
    btn.disabled = false;
  }

  async function apagar() {
    const escolha = escolhaLimpeza();
    const r0 = await chamar("previa", escolha);
    if (!r0.ok || !r0.qtd) return;
    const destino = escolha.lixeira ? "Eles irão para a Lixeira e podem ser recuperados." : "ATENÇÃO: eles serão apagados DE VEZ, sem passar pela Lixeira.";
    if (!(await simNao(`Apagar ${r0.qtd} PDF(s) (${r0.tamanho})?\n\n${destino}`, true))) return;
    const r = await chamar("limpar", escolha);
    if (!r.ok) return toast(r.erro || "Não consegui apagar.", "erro");
    if (r.falhas.length) {
      const nomes = r.falhas.slice(0, 8).map((f) => `• ${f.nome}: ${f.motivo}`).join("\n");
      await perguntar(`${r.apagados} PDF(s) removido(s). ${r.falhas.length} não puderam ser apagados (talvez estejam abertos):\n\n${nomes}`,
        [{ rotulo: "OK", valor: true, classe: "primario" }]);
    } else toast(`${r.apagados} PDF(s) ${r.para_lixeira ? "enviados para a Lixeira" : "apagados"} · ${r.liberados} liberados.`);
    carregarArquivos();
    atualizarStatus();
  }

  async function salvarPref(campos) {
    await chamar("salvar_pref", campos);
  }

  async function alterarPasta() {
    const r = await chamar("alterar_pasta");
    if (!r.ok) return;
    toast("Pasta dos PDFs alterada. Os próximos DAREs serão salvos nela.");
    carregarArquivos();
    atualizarStatus();
  }

  // -------------------------------------------------------- Desempenho

  async function trocarAbaDesempenho(aba) {
    s.desAba = aba;
    document.querySelectorAll("#dare-des-abas .aba").forEach((b) => b.classList.toggle("ativa", b.dataset.desAba === aba));
    document.querySelectorAll("[data-des-painel]").forEach((p) => (p.hidden = p.dataset.desPainel !== aba));
    if (aba === "auto") carregarAnalise();
    else if (aba === "diag" && !s.diagFeito) diagnosticar();
    else if (aba === "testes") carregarHistoricoTestes();
    else if (aba === "monitor") desenharMonitor();
  }

  const statsVazias = (e) => !e || !e.n;

  async function carregarAnalise() {
    const a = await chamar("analise", { apenas_sucesso: $("dare-so-sucesso").checked });
    if (!a.ok) return;
    kpi("dare-d-lotes", String(a.lotes), a.lotes ? `em ${a.execucoes} execução(ões)` : "nenhum ainda");
    kpi("dare-d-taxa", a.lotes ? `${nBR(a.taxa, 1)} %` : "—", a.lotes ? `${a.erros} com erro` : "", a.lotes ? (a.taxa >= 90 ? "ok" : "aviso") : "");
    kpi("dare-d-media", a.total.n ? `${nBR(a.total.media, 1)} s` : "—", a.total.n ? `mediana ${nBR(a.total.mediana, 1)} s` : "");
    kpi("dare-d-hora", a.lotes_por_hora ? nBR(a.lotes_por_hora, 0) : "—", "estimado pela média");
    kpi("dare-d-conexao", a.conexao.n ? `${nBR(a.conexao.media, 1)} s` : "—", a.conexao.n ? "média ao iniciar" : "");
    $("dare-des-vazio").hidden = !!a.lotes;
    barrasH($("dare-g-etapas"), a.etapas.map((e) => [e.rotulo, e.media]));
    $("dare-gargalo").textContent = a.gargalo;
    const dare = a.dare.media || 0, sei = a.sei.media || 0, tot = dare + sei;
    const div = $("dare-divisao");
    if (!tot) { div.innerHTML = ""; $("dare-divisao-txt").textContent = "Sem medições ainda."; }
    else {
      const pd = (dare / tot) * 100;
      div.innerHTML = `<div style="width:${pd}%;background:${COR.s1}">${pd > 14 ? `DARE ${nBR(pd, 0)} %` : ""}</div><div style="width:${100 - pd}%;background:${COR.s2}">${100 - pd > 14 ? `SEI ${nBR(100 - pd, 0)} %` : ""}</div>`;
      $("dare-divisao-txt").textContent = `DARE: ${nBR(dare)} s em média (preencher, imprimir e salvar o PDF).\nSEI: ${nBR(sei)} s em média (abrir o processo e anexar).`;
    }
    linhas($("dare-g-lotes"), a.ultimos_totais.length ? [["Tempo total", COR.s1, a.ultimos_totais]] : [], { unidade: "s", rotulosX: ["mais antigo", "mais recente"] });
    colunas($("dare-g-dias"), [["Concluídos", COR.s3], ["Com erro", COR.erro]], a.dias.map((d) => [d.dia, [d.ok, d.erro]]));
    const t = new Tabela($("dare-estat"), ["Medida", "n", "Média", "Mediana", "Desvio", "Mín", "Máx", "P95", "CV"].map((titulo, i) => ({ chave: String(i), titulo, classe: i ? "num" : "" })),
      { selecao: "none", ordenavel: false, vazio: "Sem medições ainda." });
    const lin = [["Lançamento completo", a.total], ["Fase DARE (gerar + PDF)", a.dare], ["Fase SEI (anexar)", a.sei], ["Conexão com o navegador", a.conexao]]
      .concat(a.etapas.map((e) => [`   ${e.rotulo}`, e]));
    t.definir(lin.filter(([, e]) => !statsVazias(e)).map(([nome, e], i) => ({
      id: String(i), cels: [nome, e.n, nBR(e.media), nBR(e.mediana), nBR(e.desvio), nBR(e.minimo), nBR(e.maximo), nBR(e.p95), `${nBR(e.cv, 1)} %`],
    })));
    $("dare-btn-monitor").disabled = !a.psutil;
    if (!a.psutil) $("dare-monitor-txt").textContent = "O componente psutil não está instalado: o monitor não está disponível.";
  }

  async function alternarMonitor() {
    const ligar = !s.monitor;
    const r = await chamar("monitor", { ligar });
    if (!r.ok) return toast(r.erro || "Monitor indisponível.", "aviso");
    s.monitor = ligar;
    const b = $("dare-btn-monitor");
    b.textContent = ligar ? "■ Parar monitor" : "▶ Iniciar monitor";
    b.className = `btn ${ligar ? "perigo-contorno" : "primario"}`;
  }

  const taxa = (bps) => (bps >= 1024 ** 2 ? `${nBR(bps / 1024 ** 2, 1)} MB/s` : `${nBR(bps / 1024, 0)} KB/s`);

  function amostra(a) {
    if (!a || !Object.keys(a).length) return;
    Object.keys(s.serie).forEach((k) => {
      let v = a[k] || 0;
      if (k.startsWith("rede") || k.startsWith("disco")) v /= 1024;
      s.serie[k].push(v);
      if (s.serie[k].length > 120) s.serie[k].shift();
    });
    kpi("dare-m-cpu", `${nBR(a.cpu, 0)} %`, "uso total", a.cpu > 90 ? "erro" : "");
    kpi("dare-m-ram", `${nBR(a.ram, 0)} %`, `${nBR(a.ram_usada_gb, 1)} GB em uso`);
    kpi("dare-m-app", `${nBR(a.app_mb, 0)} MB`, `CPU ${nBR(a.app_cpu, 1)} % · ${a.threads} threads`);
    kpi("dare-m-nav", `${nBR(a.navegador_mb, 0)} MB`, "todas as janelas");
    kpi("dare-m-rede", `↓ ${taxa(a.rede_rx)}`, `↑ ${taxa(a.rede_tx)}`);
    if (s.ativo && s.pagina === "desempenho" && s.desAba === "monitor") desenharMonitor();
  }

  function desenharMonitor() {
    const janela = [`-${s.serie.cpu.length} s`, "agora"];
    linhas($("dare-g-cpu"), [["CPU", COR.s1, s.serie.cpu], ["Memória", COR.s2, s.serie.ram], ["Este programa", COR.s3, s.serie.app_cpu]],
      { maximo: 100, unidade: "%", rotulosX: janela, altura: 230 });
    linhas($("dare-g-io"), [["Rede ↓", COR.s1, s.serie.rede_rx], ["Rede ↑", COR.s4, s.serie.rede_tx],
      ["Disco leitura", COR.s3, s.serie.disco_leitura], ["Disco escrita", COR.s2, s.serie.disco_escrita]],
      { unidade: "KB/s", rotulosX: janela, altura: 230 });
  }

  async function diagnosticar() {
    $("dare-btn-diag").disabled = true;
    $("dare-diag-txt").textContent = "Executando… (a parte de rede pode levar alguns segundos)";
    $("dare-diag-tabela").innerHTML = "";
    await chamar("diagnostico");
  }

  function mostrarDiagnostico(d) {
    s.diagFeito = true;
    $("dare-btn-diag").disabled = false;
    const icone = { ok: "✔", aviso: "⚠", erro: "✖", info: "•" };
    const t = new Tabela($("dare-diag-tabela"), [{ chave: "g", titulo: "Grupo" }, { chave: "i", titulo: "Item" }, { chave: "r", titulo: "Resultado", classe: "res" }, { chave: "d", titulo: "Detalhe" }],
      { selecao: "single", ordenavel: false, vazio: "Clique em “Executar diagnóstico”." });
    t.definir(d.itens.map((i, k) => ({ id: String(k), classe: i.status === "erro" ? "erro" : i.status === "aviso" ? "aviso" : "", cels: [i.grupo, i.nome, `${icone[i.status] || "•"}  ${i.valor}`, i.detalhe] })));
    const conta = (st) => d.itens.filter((i) => i.status === st).length;
    $("dare-diag-txt").textContent = `${d.itens.length} itens verificados às ${d.hora}: ${conta("ok")} OK · ${conta("aviso")} aviso(s) · ${conta("erro")} problema(s).`;
  }

  async function rodarTestes() {
    $("dare-btn-testes").disabled = true;
    $("dare-testes-barra-caixa").hidden = false;
    $("dare-testes-barra").style.width = "0%";
    await chamar("testes");
  }

  function progressoTestes(d) {
    $("dare-testes-barra").style.width = `${(d.i / d.total) * 100}%`;
    $("dare-testes-txt").textContent = d.i < d.total ? `Executando: ${d.nome}…` : "Concluído.";
  }

  function mostrarTestes(d) {
    $("dare-btn-testes").disabled = false;
    $("dare-testes-barra-caixa").hidden = true;
    const t = new Tabela($("dare-testes-tabela"), [{ chave: "t", titulo: "Teste" }, { chave: "r", titulo: "Resultado", classe: "num" }, { chave: "c", titulo: "Comparação", classe: "num res" }, { chave: "d", titulo: "Detalhe" }],
      { selecao: "single", ordenavel: false, vazio: "Clique em “Executar testes”." });
    t.definir(d.linhas.map((l, i) => ({ id: String(i), classe: l.tag === "sucesso" ? "ok" : l.tag, cels: [l.nome, l.resultado, l.comparacao, l.detalhe] })));
    $("dare-testes-txt").textContent = `Concluído às ${d.hora}. Resultado salvo para comparação.`;
    pintarHistoricoTestes(d.historico);
  }

  function pintarHistoricoTestes(linhasHist) {
    const t = new Tabela($("dare-testes-hist"), ["Data", "Computador", "Valid./s", "SHA MB/s", "Planilha l/s", "Disco MB/s", "Rede ms"].map((titulo, i) => ({ chave: String(i), titulo, classe: i > 1 ? "num" : "" })),
      { selecao: "single", vazio: "Nenhuma rodada salva ainda." });
    t.definir(linhasHist.map((l, i) => ({ id: String(i), cels: l })));
  }

  async function carregarHistoricoTestes() {
    const r = await chamar("historico_testes");
    if (r.ok) pintarHistoricoTestes(r.linhas);
    if (!$("dare-testes-tabela").innerHTML) new Tabela($("dare-testes-tabela"), [{ chave: "t", titulo: "Teste" }, { chave: "r", titulo: "Resultado" }, { chave: "c", titulo: "Comparação" }, { chave: "d", titulo: "Detalhe" }],
      { selecao: "none", ordenavel: false, vazio: "Clique em “Executar testes”." }).definir([]);
  }

  async function exportarCsv() {
    const r = await chamar("exportar_csv");
    if (r.ok) return toast("Medições exportadas.");
    if (r.erro) perguntar(r.erro, [{ rotulo: "OK", valor: true, classe: "primario" }]);
  }

  async function gerarRelatorio() {
    const r = await chamar("relatorio", { apenas_sucesso: $("dare-so-sucesso").checked });
    if (!r.ok) { if (r.erro) toast(r.erro, "erro", 6000); return; }
    toast("Relatório gerado. Abrindo no navegador…");
    if (r.sem_diagnostico) toast("Dica: rode o Diagnóstico antes para incluí-lo no relatório.", "info", 5000);
  }

  // ----------------------------------------------------- Configurações

  async function carregarConfiguracoes() {
    const c = await chamar("configuracoes");
    if (!c.ok) return;
    $("dare-cfg-versao").textContent = `Versão ${c.versao}`;
    $("dare-cfg-data").textContent = `lançada em ${c.data_versao}`;
    $("dare-cfg-modo").textContent = `Modo: ${c.modo}`;
    $("dare-cfg-nav").textContent = c.navegador.nome || "Nenhum navegador compatível encontrado. Instale o Google Chrome.";
    $("dare-cfg-exe").textContent = c.navegador.exe;
    $("dare-cfg-edge").hidden = !c.navegador.edge;
    $("dare-cfg-perfil").textContent = `Perfil: ${c.navegador.perfil}`;
    $("dare-cfg-abrir").checked = c.abrir_ao_iniciar;
    document.querySelectorAll("[data-dare-recurso]").forEach((b) => (b.disabled = !c.recursos[b.dataset.dareRecurso]));
    $("dare-cfg-pastas").innerHTML = c.pastas.map((p) =>
      `<div class="dare-pasta"><div><b>${esc(p.rotulo)}</b><span>${esc(p.caminho)}</span></div><button class="btn fantasma pequeno" type="button" data-dare-pasta="${esc(p.qual)}">Abrir</button></div>`).join("");
    $("dare-cfg-fixos").innerHTML = c.fixos.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  }

  // ------------------------------------------------------- Eventos

  const eventos = {
    dare_log: (e) => logLinha(e.hora, e.texto, e.nivel),
    dare_motor: eventoMotor,
    dare_navegador: (e) => {
      if (!e.silencioso) {
        if (e.ok) toast("Navegador aberto. Entre com a sua conta no DARE e no SEI.");
        else perguntar("Não consegui abrir o navegador em modo depuração.\n\nFeche todas as janelas do navegador da automação e tente de novo. Os detalhes estão no log.",
          [{ rotulo: "OK", valor: true, classe: "primario" }]);
      }
      if (s.ativo) atualizarStatus();
    },
    dare_aviso: (e) => { toast(e.texto, e.tipo || "info", 6000); if (s.ativo) atualizarStatus(); },
    dare_amostra: (e) => amostra(e.amostra),
    dare_diagnostico: mostrarDiagnostico,
    dare_testes_progresso: progressoTestes,
    dare_testes: mostrarTestes,
  };

  // --------------------------------------------------------- Partida

  function ligarBotoes() {
    document.querySelectorAll("[data-dare-ir]").forEach((b) => (b.onclick = () => ir(b.dataset.dareIr)));
    document.addEventListener("click", (e) => {
      const acao = e.target.closest("[data-dare-acao]");
      if (acao) {
        const a = acao.dataset.dareAcao;
        if (a === "importar") importarPlanilha();
        else if (a === "novo") { ir("lancamentos"); novo(); }
        else if (a === "abrir_navegador") abrirNavegador();
      }
      const pasta = e.target.closest("[data-dare-pasta]");
      if (pasta) chamar("abrir_pasta", { qual: pasta.dataset.darePasta });
      const recurso = e.target.closest("[data-dare-recurso]");
      if (recurso) chamar("abrir_recurso", { nome: recurso.dataset.dareRecurso });
    });
    $("dare-nav-estado").onclick = abrirNavegador;
    $("dare-k-nav").onclick = abrirNavegador;
    $("dare-k-lista").onclick = () => ir("lancamentos");
    $("dare-k-pdfs").onclick = () => ir("arquivos");

    // Lançamentos
    $("dare-form").addEventListener("submit", (e) => { e.preventDefault(); salvar(); });
    CAMPOS.forEach((c) => {
      const el = entrada(c);
      el.addEventListener("blur", () => conferirCampo(c));
      el.addEventListener("input", () => caixaCampo(c).classList.contains("invalido") && conferirCampo(c));
      el.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); novo(); } });
    });
    entrada("cnpj").addEventListener("input", () => $("dare-mesmo").checked && espelharRecolhedor());
    $("dare-mesmo").onchange = espelharRecolhedor;
    $("dare-btn-limpar").onclick = () => novo();
    $("dare-btn-editar").onclick = () => { const sel = indicesSelecionados(); if (sel.length) editar(sel[0]); };
    $("dare-btn-duplicar").onclick = duplicar;
    $("dare-btn-remover").onclick = remover;
    $("dare-btn-esvaziar").onclick = esvaziar;
    $("dare-btn-iniciar").onclick = iniciar;

    // Importar planilha
    $("dare-imp-abertas").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-aberta]");
      if (!b) return;
      imp.selAberta = Number(b.dataset.aberta);
      $("dare-imp-abertas").querySelectorAll("button").forEach((x) => x.classList.toggle("sel", x === b));
      usarPasta(await chamar("planilha_aberta", { indice: imp.selAberta }));
    });
    $("dare-imp-recarregar").onclick = recarregarAbertas;
    $("dare-imp-procurar").onclick = async () => usarPasta(await chamar("planilha_procurar"));
    $("dare-imp-modelo").onclick = criarModelo;
    $("dare-imp-aba").onchange = usarAba;
    $("dare-imp-cab").addEventListener("change", mudarCabecalho);
    $("dare-imp-cab").addEventListener("keydown", (e) => e.key === "Enter" && mudarCabecalho());
    $("dare-imp-mapa").addEventListener("change", (e) => {
      const sel = e.target.closest("[data-mapa]");
      if (sel) mudouCampo(sel.dataset.mapa);
    });
    $("dare-imp-mapa").addEventListener("input", (e) => e.target.closest("[data-fixo]") && invalidarLeitura());
    $("dare-imp-de").addEventListener("input", invalidarLeitura);
    $("dare-imp-ate").addEventListener("input", invalidarLeitura);
    $("dare-imp-ler").onclick = lerPlanilha;
    $("dare-imp-cancelar").onclick = fecharImportacao;
    $("dare-imp-adicionar").onclick = confirmarImportacao;

    // Execução
    $("dare-btn-parar").onclick = parar;

    // Arquivos
    $("dare-arq-atualizar").onclick = carregarArquivos;
    $("dare-arq-alterar").onclick = alterarPasta;
    $("dare-btn-apagar").onclick = apagar;
    $("dare-criterios").addEventListener("change", previa);
    $("dare-dias").addEventListener("input", previa);
    $("dare-ate").addEventListener("input", previa);
    $("dare-lixeira").onchange = () => salvarPref({ usar_lixeira: $("dare-lixeira").checked });
    $("dare-proteger").onchange = () => { salvarPref({ proteger_nao_anexados: $("dare-proteger").checked }); previa(); };
    $("dare-auto").onchange = () => salvarPref({ limpeza_automatica: $("dare-auto").checked });
    $("dare-auto-dias").onchange = () => salvarPref({ limpeza_dias: $("dare-auto-dias").value });
    $("dare-aviso-mb").onchange = () => salvarPref({ aviso_tamanho_mb: $("dare-aviso-mb").value });

    // Desempenho
    document.querySelectorAll("#dare-des-abas .aba").forEach((b) => (b.onclick = () => trocarAbaDesempenho(b.dataset.desAba)));
    $("dare-so-sucesso").onchange = carregarAnalise;
    $("dare-des-atualizar").onclick = carregarAnalise;
    $("dare-btn-monitor").onclick = alternarMonitor;
    $("dare-btn-diag").onclick = diagnosticar;
    $("dare-btn-testes").onclick = rodarTestes;
    $("dare-btn-csv").onclick = exportarCsv;
    $("dare-btn-relatorio").onclick = gerarRelatorio;

    // Configurações
    $("dare-cfg-abrir").onchange = async () => {
      await salvarPref({ abrir_navegador_ao_iniciar: $("dare-cfg-abrir").checked });
      toast("Preferência salva.");
    };

    // Atalhos do DARE (só com o módulo aberto e sem janela por cima)
    document.addEventListener("keydown", (e) => {
      if (!s.ativo || !$("dare-importar").hidden || !$("dare-confirma").hidden) return;
      if (e.ctrlKey && (e.key === "n" || e.key === "N")) { e.preventDefault(); ir("lancamentos"); novo(); }
      else if (e.ctrlKey && (e.key === "i" || e.key === "I")) { e.preventDefault(); importarPlanilha(); }
      else if (e.key === "F5") { e.preventDefault(); aoMostrar(s.pagina); }
    });

    // Situação a cada 5 s (como a barra de status do DARE), com o módulo aberto.
    setInterval(() => s.ativo && !document.hidden && atualizarStatus(), 5000);
  }

  function ligar(ganchos) {
    g = ganchos;
    g.registrarEventos(eventos);
    ligarBotoes();
    pintarEtapas(null);
  }

  window.lbaDare = { ligar, mostrar, esconder, ir };

  // ===================================================== Demonstração
  // Só para ver o layout num navegador comum (index.html?demo).

  const DEMO = (() => {
    const hoje = new Date();
    const dd = (d) => d.toLocaleDateString("pt-BR");
    const venc = new Date(hoje.getTime() + 30 * 864e5);
    let lotes = [
      { processo: "0012.123456/2026-12", cpf: "529.982.247-25", cnpj: "04.287.520/0001-88", recolhedor: "04.287.520/0001-88", ref: "10/2026", venc: dd(venc), valor: "7.273,07", origem: "digitado" },
      { processo: "0012.123457/2026-90", cpf: "111.444.777-35", cnpj: "04.287.520/0001-88", recolhedor: "04.287.520/0001-88", ref: "10/2026", venc: dd(venc), valor: "100,00", origem: "linha 7" },
    ];
    const lista = () => ({ ok: true, linhas: lotes.map((l, i) => ({ ...l, n: i + 1 })), avisos: [], total: lotes.length ? `${lotes.length} lançamento(s) · total R$ 7.373,07` : "", executando: false });
    const novoForm = () => ({ campos: { processo: "", cpf: "", cnpj: "04.287.520/0001-88", recolhedor: "04.287.520/0001-88", ref: "10/2026", venc: dd(venc), valor: "100,00" }, mesmo: true });
    const emitir = (lista_, passo = 400) => lista_.forEach((ev, i) => setTimeout(() => window.lba && lba.receber([ev]), i * passo));
    return {
      async chamar(acao, d) {
        switch (acao) {
          case "estado":
            return { ok: true, versao: "3.0.0", data_versao: "14/10/2026", navegador: { aberto: false, encontrado: true, nome: "Google Chrome" },
              lista: lista(), hoje: { ok: 3, erros: 1 }, pdfs: { qtd: 42, tamanho: "8,4 MB", acima_do_limite: false, limite_mb: 500 },
              pasta_pdf: "C:\\Users\\voce\\Documents\\DARE Automação\\DARE_PDFs", mensagens: [],
              fixos_texto: "Valores fixos: SEGEP · receita 7155 · UG 160001 / gestão 00001 · série SEI 310",
              recentes: [{ quando: "15/10 09:12", status: "SUCESSO", processo: "0012.123450/2026-11", servidor: "MARIA DA SILVA", valor: "7.273,07" },
                { quando: "15/10 09:10", status: "ERRO", processo: "0012.123451/2026-55", servidor: "529.982.247-25", valor: "100,00" }] };
          case "lista": return lista();
          case "novo": return { ok: true, ...novoForm() };
          case "validar": return d.texto ? { ok: true, valor: d.texto } : { ok: false, erro: "Campo obrigatório." };
          case "salvar": {
            const v = d.valores;
            if (!v.processo || !v.cpf) return { ok: false, erros: { ...(v.processo ? {} : { processo: "Campo obrigatório." }), ...(v.cpf ? {} : { cpf: "Campo obrigatório." }) } };
            const item = { ...v, origem: "digitado" };
            if (d.indice !== null && d.indice !== undefined) lotes[d.indice] = item; else lotes.push(item);
            return { ok: true, n: d.indice ?? lotes.length, mensagem: "Lançamento adicionado. Preencha o próximo.", lista: lista(), novo: novoForm() };
          }
          case "editar": return { ok: true, campos: lotes[d.indice], mesmo: true, titulo: `Editando o lançamento ${d.indice + 1}` };
          case "duplicar": lotes.splice(d.indice + 1, 0, { ...lotes[d.indice], origem: "digitado" }); return { ok: true, lista: lista(), indice: d.indice + 1 };
          case "remover": lotes = lotes.filter((_, i) => !d.indices.includes(i)); return { ok: true, lista: lista(), novo: novoForm() };
          case "esvaziar": lotes = []; return { ok: true, lista: lista(), novo: novoForm() };
          case "avisos_inicio": return { ok: true, n: lotes.length, avisos: [] };
          case "iniciar": {
            const copia = lotes.map((l, i) => ({ ...l, n: i + 1 }));
            const ev = [{ tipo: "dare_motor", evento: "status", texto: "Abrindo e conectando ao navegador..." },
              { tipo: "dare_motor", evento: "conectado", segundos: 2.4 }];
            copia.forEach((l, i) => {
              ev.push({ tipo: "dare_motor", evento: "lote_inicio", indice: i + 1, total: copia.length, dados: l });
              ["dare_1", "dare_3", "dare_5", "sei_1", "sei_4"].forEach((et) => ev.push({ tipo: "dare_motor", evento: "etapa", etapa: et, rotulo: et }));
              ev.push({ tipo: "dare_log", hora: "09:00:00", texto: `=== Lote ${i + 1}/${copia.length} · processo ${l.processo} ===`, nivel: "destaque" });
              ev.push({ tipo: "dare_motor", evento: "lote_fim", indice: i + 1, total: copia.length, segundos: 31.5 + i,
                resultado: { sucesso: i === 0, pdf: "", servidor: i === 0 ? "MARIA DA SILVA" : "", erro: i === 0 ? "" : "TimeoutError: Elemento não encontrado", dados: l } });
            });
            ev.push({ tipo: "dare_motor", evento: "fim", total: copia.length, interrompido: false, pendentes: copia.length > 1 ? 1 : 0,
              resultados: copia.map((l, i) => ({ sucesso: i === 0, dados: l })), lista: { ...lista(), linhas: lista().linhas.slice(1) } });
            emitir(ev, 300);
            return { ok: true, lotes: copia };
          }
          case "arquivos":
            return { ok: true, pasta: "C:\\Users\\voce\\Documents\\DARE Automação\\DARE_PDFs", qtd: 2, tamanho: "412,0 KB", media: "206,0 KB",
              mais_antigo: { data: "02/09/2026", dias: 43 }, protegidos: 1, padrao_data: dd(new Date(hoje.getTime() - 30 * 864e5)),
              pref: { usar_lixeira: true, proteger_nao_anexados: true, limpeza_automatica: false, limpeza_dias: 30, aviso_tamanho_mb: 500, ultima_limpeza: "" },
              arquivos: [{ caminho: "a.pdf", nome: "DARE_MARIA_52998224725_102026_venc-14-11-2026.pdf", data: "15/10/2026 09:12", tamanho: "206,0 KB", protegido: false },
                { caminho: "b.pdf", nome: "DARE__11144477735_102026_venc-14-11-2026.pdf", data: "02/09/2026 14:01", tamanho: "206,0 KB", protegido: true }] };
          case "previa": return { ok: true, qtd: 0, tamanho: "0 bytes", caminhos: [] };
          case "analise":
            return { ok: true, lotes: 12, sucessos: 11, erros: 1, execucoes: 3, taxa: 91.7, lotes_por_hora: 112,
              total: { n: 11, media: 32.1, mediana: 31.4, desvio: 2.2, minimo: 29.0, maximo: 37.5, p95: 36.0, cv: 6.9 },
              dare: { n: 11, media: 18.2 }, sei: { n: 11, media: 13.9 }, conexao: { n: 3, media: 2.6, mediana: 2.5, desvio: .3, minimo: 2.2, maximo: 3.0, p95: 3.0, cv: 11 },
              etapas: [["DARE · imprimir e salvar PDF", 7.4], ["SEI · anexar e salvar", 6.1], ["DARE · CPF do servidor", 3.2], ["SEI · abrir processo", 2.9]]
                .map(([rotulo, media]) => ({ rotulo, media, n: 11, mediana: media, desvio: .4, minimo: media - 1, maximo: media + 1, p95: media + .8, cv: 5 })),
              gargalo: "Gargalo: “DARE · imprimir e salvar PDF” leva 7,40 s em média (23,1 % do lançamento).",
              ultimos_totais: [33, 31, 30, 34, 32, 29, 31, 37, 33, 31, 30], psutil: true,
              dias: Array.from({ length: 14 }, (_, i) => ({ dia: `${String(i + 2).padStart(2, "0")}/10`, ok: i % 3 ? 2 : 0, erro: i === 9 ? 1 : 0 })) };
          case "configuracoes":
            return { ok: true, versao: "3.0.0", data_versao: "14/10/2026", modo: "executando pelo código-fonte (Python)",
              navegador: { nome: "Google Chrome 141", exe: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", edge: false, perfil: "C:\\ChromeAutomacao" },
              abrir_ao_iniciar: true, recursos: { "GUIA_DE_USO.html": true, "LICENCA.txt": true },
              pastas: [{ rotulo: "PDFs gerados", caminho: "C:\\Users\\voce\\Documents\\DARE Automação\\DARE_PDFs", qual: "pdf" }],
              fixos: [["Órgão", "SEGEP - SUPERINTENDÊNCIA ESTADUAL DE GESTÃO DE PESSOAS"], ["Código da receita", "7155"]] };
          case "historico_testes": return { ok: true, linhas: [] };
          case "planilha_inicio":
            return { ok: true, excel: true, abertas: [{ nome: "DAREs outubro.xlsx", caminho: "C:\\Planilhas\\DAREs outubro.xlsx" }],
              campos: [["processo", "Processo SEI"], ["cnpj", "CNPJ do órgão"], ["cpf", "CPF do servidor"], ["cnpj_recolhedor", "CNPJ do recolhedor"],
                ["mes_ano_referencia", "Mês/ano de referência"], ["vencimento", "Vencimento"], ["valor", "Valor"]].map(([campo, rotulo], i) => ({ campo, rotulo, obrigatorio: i < 5 })) };
          case "planilha_aberta": return { ok: true, nome: "DAREs outubro.xlsx", caminho: "C:\\Planilhas\\DAREs outubro.xlsx", abas: ["Plan1"] };
          case "planilha_aba":
            return { ok: true, origem: "Colunas sugeridas pelos títulos do cabeçalho. Confira.",
              mapa: { linha_cabecalho: 1, campos: { processo: { coluna: 1 }, cnpj: { coluna: 2 }, cpf: { coluna: 3 }, cnpj_recolhedor: { coluna: 4 }, mes_ano_referencia: { coluna: 5 } } },
              colunas: { opcoes: ["Processo", "CNPJ", "CPF", "Recolhedor", "Referência", "Vencimento", "Valor"].map((n, i) => ({ coluna: i + 1, rotulo: `${"ABCDEFG"[i]}  ·  ${n}` })),
                encontradas: ["A: Processo", "B: CNPJ", "C: CPF"] }, linhas: { de: 2, ate: 9, ultima: 9 } };
          case "planilha_ler": return { ok: true, validas: 7, vazias: 1, ocultas: 0, problemas: [{ linha: 5, mensagem: "CPF inválido: os dígitos verificadores não conferem." }] };
          default: return { ok: true, linhas: { de: 2, ate: 9, ultima: 9 } };
        }
      },
    };
  })();
})();
