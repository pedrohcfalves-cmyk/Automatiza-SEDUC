/* O que vale para todas as automações, no menu do topo:
 *
 *   Ano do SIGEF      o exercício que a OB e a NE usam (padrão: o ano atual)
 *   Relatório geral   TODAS as automações numa página: tempo economizado no total,
 *                     por mês, por pessoa e o detalhe de cada uma. Qualquer botão com
 *                     data-relatorio-geral (na NE, no DARE, no Gerar pagamento...) abre a
 *                     mesma caixa.
 *   Acessibilidade    tamanho do texto, alto contraste, foco destacado, sem animações e
 *                     mais espaço entre linhas, para o aplicativo inteiro (window.lbaAcess).
 *                     Fica guardado no armazenamento da janela; o <head> do index.html já
 *                     aplica antes de desenhar, para a tela não piscar.
 *   Entrar nos sistemas  antes de começar o DARE e o BB (window.lbaLogin): abre o Chrome só
 *                     com as abas da automação e espera a pessoa confirmar o login.
 *   Diálogos          o foco entra no diálogo aberto, Tab não sai dele e o foco volta
 *                     para o botão que abriu.
 *
 * Tudo no Python passa por UMA porta: api.geral(acao, dados), que chega em
 * janela/modulo_geral.py. Aberta num navegador comum (?demo), usa a simulação
 * do fim do arquivo.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const DEMONSTRACAO = /[?&]demo\b/.test(location.search);

  async function api() {
    for (let i = 0; i < 100; i++) {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.geral) return window.pywebview.api;
      if (DEMONSTRACAO) return null;
      await new Promise((ok) => setTimeout(ok, 100));
    }
    return null;
  }

  async function chamar(acao, dados = {}) {
    try {
      const a = await api();
      if (!a && !DEMONSTRACAO) return { ok: false, erro: "A janela ainda está carregando. Tente de novo." };
      return (a ? await a.geral(acao, dados) : DEMO.chamar(acao, dados)) || { ok: false, erro: "sem resposta" };
    } catch (erro) {
      return { ok: false, erro: String(erro && erro.message ? erro.message : erro) };
    }
  }

  // ------------------------------------------------------- Ano do SIGEF

  function mostrarAno(r) {
    $("ano-sigef").innerHTML = (r.anos || [])
      .slice()
      .reverse()
      .map((a) => `<option value="${a}"${a === r.ano ? " selected" : ""}>${a}${a === r.atual ? " (atual)" : ""}</option>`)
      .join("");
    $("ano-sigef-aviso").textContent = r.erro ? r.erro : r.ano !== r.atual ? `Usando ${r.ano}; o ano atual é ${r.atual}.` : "";
    // A NE mostra o ano e confere o número da NE com ele.
    if (window.lbaNe && window.lbaNe.atualizarAno) window.lbaNe.atualizarAno(String(r.ano));
  }

  async function trocarAno() {
    const sel = $("ano-sigef");
    sel.disabled = true;
    try {
      mostrarAno(await chamar("definir_ano", { ano: Number(sel.value) }));
    } finally {
      sel.disabled = false;
    }
  }

  // ---------------------------------------------------- Relatório geral

  function erro(texto) {
    $("painel-erro").textContent = texto || "";
    $("painel-erro").hidden = !texto;
  }

  function mostrarPastas(pastas) {
    const eu = $("painel-modal").dataset.eu || "você";
    $("painel-pastas").innerHTML = [`<li><b>${esc(eu)}</b><span class="caminho">este computador (sempre incluído)</span></li>`]
      .concat(
        (pastas || []).map(
          (p) => `<li><b>${esc(p.pessoa)}</b><span class="caminho" title="${esc(p.caminho)}">${esc(p.caminho)}${p.existe ? "" : " (não encontrada)"}</span>
            <button class="btn fantasma pequeno" type="button" data-remover="${esc(p.caminho)}" aria-label="Remover ${esc(p.pessoa)} do relatório">Remover</button></li>`
        )
      )
      .join("");
    $("painel-qtd-pessoas").textContent = String(1 + (pastas || []).length);
  }

  const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

  // Os atalhos de período: [de, até] em AAAA-MM-DD.
  function datasDo(qual) {
    const hoje = new Date();
    const a = hoje.getFullYear(), m = hoje.getMonth();
    const par = {
      mes: [new Date(a, m, 1), hoje],
      "mes-passado": [new Date(a, m - 1, 1), new Date(a, m, 0)],
      30: [new Date(hoje.getTime() - 29 * 864e5), hoje],
      ano: [new Date(a, 0, 1), hoje],
    }[qual];
    return par.map(iso);
  }

  // O atalho que bate com as datas fica marcado (aria-pressed), para a pessoa saber o que vale.
  function marcarPeriodo() {
    document.querySelectorAll("[data-periodo]").forEach((b) => {
      const [de, ate] = datasDo(b.dataset.periodo);
      b.setAttribute("aria-pressed", String(de === $("painel-de").value && ate === $("painel-ate").value));
    });
  }

  async function abrirRelatorio() {
    const r = await chamar("painel_opcoes");
    if (!r.ok) return alert(r.erro);
    $("painel-de").value = r.de;
    $("painel-ate").value = r.ate;
    $("painel-min-ob").value = r.minutos.OB;
    $("painel-min-ne").value = r.minutos.NE;
    $("painel-min-dare").value = r.minutos.DARE;
    $("painel-modal").dataset.eu = r.eu || "";
    mostrarPastas(r.pastas);
    marcarPeriodo();
    erro("");
    $("painel-modal").hidden = false;
    $("painel-gerar").focus();
  }

  async function gerarRelatorio() {
    const botao = $("painel-gerar");
    botao.disabled = true;
    botao.setAttribute("aria-busy", "true");
    erro("");
    try {
      const r = await chamar("painel_gerar", {
        de: $("painel-de").value,
        ate: $("painel-ate").value,
        minutos: { OB: $("painel-min-ob").value, NE: $("painel-min-ne").value, DARE: $("painel-min-dare").value },
      });
      if (r.ok) $("painel-modal").hidden = true;
      else erro(r.erro);
    } finally {
      botao.disabled = false;
      botao.removeAttribute("aria-busy");
    }
  }

  // ------------------------------------------------------ Acessibilidade

  const TAMANHOS = [1, 1.15, 1.3, 1.5];
  const CHAVE = "central-acessibilidade";
  const OPCOES = ["contraste", "foco", "movimento", "espaco"];
  const PADRAO = { tamanho: 1, contraste: false, foco: false, movimento: false, espaco: false };
  let acess = { ...PADRAO };

  function lerAcess() {
    try {
      return { ...PADRAO, ...JSON.parse(localStorage.getItem(CHAVE) || "{}") };
    } catch (e) {
      return { ...PADRAO };
    }
  }

  function aplicarAcess(novo, avisar) {
    acess = { ...acess, ...novo };
    acess.tamanho = Number(acess.tamanho);
    if (!TAMANHOS.includes(acess.tamanho)) acess.tamanho = 1;
    try { localStorage.setItem(CHAVE, JSON.stringify(acess)); } catch (e) { /* sem armazenamento: vale até fechar */ }
    const raiz = document.documentElement;
    raiz.style.zoom = acess.tamanho === 1 ? "" : String(acess.tamanho);
    raiz.style.setProperty("--acess-zoom", String(acess.tamanho));
    OPCOES.forEach((k) => raiz.toggleAttribute(`data-acess-${k}`, !!acess[k]));
    // O diálogo mostra o que está valendo.
    document.querySelectorAll('input[name="acess-tamanho"]').forEach((r) => (r.checked = Number(r.value) === acess.tamanho));
    OPCOES.forEach((k) => ($(`acess-${k}`).checked = !!acess[k]));
    $("btn-acessibilidade").classList.toggle("ligado", OPCOES.some((k) => acess[k]) || acess.tamanho !== 1);
    if (avisar) anunciar(`Tamanho do texto: ${Math.round(acess.tamanho * 100)}%`);
  }

  function mudarTamanho(passo) {
    if (passo === 0) return aplicarAcess({ tamanho: 1 }, true);
    const i = TAMANHOS.indexOf(acess.tamanho);
    const novo = TAMANHOS[Math.max(0, Math.min(TAMANHOS.length - 1, i + passo))];
    if (novo !== acess.tamanho) aplicarAcess({ tamanho: novo }, true);
  }

  // Uma região "viva" só para o leitor de tela falar o que mudou.
  function anunciar(texto) {
    let el = $("anuncio-central");
    if (!el) {
      el = document.createElement("div");
      el.id = "anuncio-central";
      el.className = "sr";
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    el.textContent = "";
    setTimeout(() => (el.textContent = texto), 30);
  }

  // ------------------------------------------- Entrar nos sistemas antes de começar
  //
  // lbaLogin.exigir("dare") -> true quando a pessoa confirmou o login (ou já tinha confirmado
  // nesta sessão, com o Chrome ainda aberto); false se cancelou. É o passo "Entrar nos
  // sistemas" do Anexar no SEI e da NE, para as automações que não tinham.

  const NOMES_LOGIN = { dare: "DARE", bb: "Banco do Brasil" };
  let loginAberto = null; // { automacao, resolver }

  function marcarLogin() {
    const caixas = [...document.querySelectorAll("#entrar-checagem input")];
    $("entrar-ok").disabled = !caixas.length || caixas.some((c) => !c.checked);
  }

  async function abrirAbasDoLogin() {
    const { automacao } = loginAberto;
    $("entrar-carregando").hidden = false;
    $("entrar-erro").hidden = $("entrar-pronto").hidden = $("entrar-reabrir").hidden = true;
    $("entrar-ok").disabled = true;
    const r = await chamar("abrir_abas", { automacao });
    if (!loginAberto) return; // cancelou enquanto abria
    $("entrar-carregando").hidden = true;
    if (!r.ok) {
      $("entrar-erro-msg").textContent = r.erro || "Erro desconhecido.";
      $("entrar-erro").hidden = false;
      $("entrar-tentar").focus();
      return;
    }
    const sistemas = r.sistemas || [];
    $("entrar-abas").textContent = `O Chrome da automação está aberto só com as abas de que ela precisa: ${sistemas.join(" e ")}.`;
    const itens = sistemas.map((nome) =>
      `<label class="item"><input type="checkbox"><span class="caixa"><svg class="ic" aria-hidden="true"><use href="#i-check"/></svg></span><span class="texto"><b>Entrei no ${esc(nome)}</b><small>Na aba do ${esc(nome)}, com meu usuário e senha.</small></span></label>`);
    if (sistemas.includes("SEI"))
      itens.push(`<label class="item destaque"><input type="checkbox"><span class="caixa"><svg class="ic" aria-hidden="true"><use href="#i-check"/></svg></span><span class="texto"><b>Conferi a minha gerência no SEI</b><small>Os documentos entram na gerência que estiver selecionada.</small></span></label>`);
    $("entrar-checagem").innerHTML = itens.join("");
    $("entrar-pronto").hidden = $("entrar-reabrir").hidden = false;
    marcarLogin();
    const primeira = document.querySelector("#entrar-checagem input");
    if (primeira) primeira.focus();
  }

  function fecharLogin(confirmou) {
    if (!loginAberto) return;
    const { resolver } = loginAberto;
    loginAberto = null;
    $("entrar-modal").hidden = true;
    resolver(confirmou);
  }

  async function exigirLogin(automacao) {
    if (loginAberto) return false; // já há um pedido na tela
    const estado = await chamar("login_estado", { automacao });
    if (!estado.ok) {
      alert(estado.erro || "Não consegui conferir o login.");
      return false;
    }
    if (estado.confirmado) return true;
    return new Promise((resolver) => {
      loginAberto = { automacao, resolver };
      $("entrar-automacao").textContent = `${NOMES_LOGIN[automacao] || automacao} · antes de começar`;
      $("entrar-titulo").textContent = `Entre no ${estado.sistemas.join(" e no ")}`;
      $("entrar-modal").hidden = false;
      abrirAbasDoLogin();
    });
  }

    // ------------------------------------------------------------ Diálogos

  const FOCAVEIS = 'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';
  const visiveis = (caixa) => [...caixa.querySelectorAll(FOCAVEIS)].filter((el) => el.offsetParent !== null);

  function cuidarDosDialogos() {
    // O último lugar com foco fora dos diálogos: é para lá que o foco volta quando o diálogo fecha.
    let foraDosDialogos = null;
    const observar = (modal) => {
      new MutationObserver(() => {
        if (!modal.hidden) {
          requestAnimationFrame(() => {
            if (!modal.hidden && !modal.contains(document.activeElement)) (visiveis(modal)[0] || modal).focus();
          });
        } else if (foraDosDialogos && document.contains(foraDosDialogos) && !document.querySelector(".modal:not([hidden])")) {
          foraDosDialogos.focus();
        }
      }).observe(modal, { attributes: true, attributeFilter: ["hidden"] });
    };
    document.querySelectorAll(".modal").forEach(observar);
    document.addEventListener("pointerdown", (e) => {
      if (!e.target.closest(".modal")) foraDosDialogos = e.target.closest(FOCAVEIS) || foraDosDialogos;
    }, true);

    // O foco não fica atrás de um diálogo aberto (algo da tela de baixo pode tentar pegar o foco).
    document.addEventListener("focusin", (e) => {
      const abertos = [...document.querySelectorAll(".modal:not([hidden])")];
      const modal = abertos[abertos.length - 1];
      if (modal && !modal.contains(e.target)) (visiveis(modal)[0] || modal).focus();
      else if (!modal && !e.target.closest(".modal")) foraDosDialogos = e.target;
    });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Tab") return;
      const abertos = [...document.querySelectorAll(".modal:not([hidden])")];
      const modal = abertos[abertos.length - 1];
      if (!modal) return;
      const itens = visiveis(modal);
      if (!itens.length) return;
      const primeiro = itens[0], ultimo = itens[itens.length - 1];
      const dentro = modal.contains(document.activeElement);
      if (e.shiftKey && (!dentro || document.activeElement === primeiro)) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && (!dentro || document.activeElement === ultimo)) {
        e.preventDefault();
        primeiro.focus();
      }
    });
  }

  // Os passos (Anexar no SEI, NE, Cadastro) dizem ao leitor de tela qual é o atual.
  function passosFalados() {
    document.querySelectorAll(".passos").forEach((ol) => {
      const marcar = () => ol.querySelectorAll("li").forEach((li) => {
        if (li.classList.contains("atual")) {
          if (li.getAttribute("aria-current") !== "step") li.setAttribute("aria-current", "step");
        } else if (li.hasAttribute("aria-current")) li.removeAttribute("aria-current");
      });
      marcar();
      new MutationObserver(marcar).observe(ol, { subtree: true, attributes: true, attributeFilter: ["class"] });
    });
  }

  // ------------------------------------------------------------- Partida

  function ligar() {
    $("ano-sigef").addEventListener("change", trocarAno);

    // Relatório geral: o botão do topo e os das automações (data-relatorio-geral).
    $("btn-relatorio-geral").onclick = abrirRelatorio;
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-relatorio-geral]")) abrirRelatorio();
    });
    $("painel-cancelar").onclick = () => ($("painel-modal").hidden = true);
    $("painel-modal").addEventListener("keydown", (e) => e.key === "Escape" && ($("painel-modal").hidden = true));
    $("painel-gerar").onclick = gerarRelatorio;
    document.querySelectorAll("[data-periodo]").forEach((b) => (b.onclick = () => {
      [$("painel-de").value, $("painel-ate").value] = datasDo(b.dataset.periodo);
      marcarPeriodo();
    }));
    ["painel-de", "painel-ate"].forEach((id) => $(id).addEventListener("change", marcarPeriodo));
    $("painel-incluir").onclick = async () => {
      const r = await chamar("painel_incluir_pasta");
      if (r.cancelou) return;
      erro(r.ok ? "" : r.erro);
      if (r.pastas) mostrarPastas(r.pastas);
    };
    $("painel-pastas").addEventListener("click", async (e) => {
      const botao = e.target.closest("button[data-remover]");
      if (!botao) return;
      const r = await chamar("painel_remover_pasta", { caminho: botao.dataset.remover });
      mostrarPastas(r.pastas);
      $("painel-incluir").focus();
    });

    // Entrar nos sistemas
    $("entrar-checagem").addEventListener("change", marcarLogin);
    $("entrar-tentar").onclick = abrirAbasDoLogin;
    $("entrar-reabrir").onclick = abrirAbasDoLogin;
    $("entrar-cancelar").onclick = () => fecharLogin(false);
    $("entrar-modal").addEventListener("keydown", (e) => e.key === "Escape" && fecharLogin(false));
    $("entrar-ok").onclick = async () => {
      if ($("entrar-ok").disabled) return;
      $("entrar-ok").disabled = true;
      const r = await chamar("login_confirmado", { automacao: loginAberto.automacao });
      if (r.ok) fecharLogin(true);
      else alert(r.erro || "Não consegui guardar a confirmação.");
    };

    // Acessibilidade
    aplicarAcess(lerAcess(), false);
    $("btn-acessibilidade").onclick = () => {
      $("acess-modal").hidden = false;
      const marcado = document.querySelector('input[name="acess-tamanho"]:checked');
      if (marcado) marcado.focus();
    };
    const fechar = () => ($("acess-modal").hidden = true);
    $("acess-fechar").onclick = fechar;
    $("acess-modal").addEventListener("keydown", (e) => e.key === "Escape" && fechar());
    $("acess-padrao").onclick = () => aplicarAcess(PADRAO, true);
    document.querySelectorAll('input[name="acess-tamanho"]').forEach((r) =>
      r.addEventListener("change", () => aplicarAcess({ tamanho: Number(r.value) }, true)));
    OPCOES.forEach((k) => $(`acess-${k}`).addEventListener("change", () => aplicarAcess({ [k]: $(`acess-${k}`).checked }, false)));
    document.addEventListener("keydown", (e) => {
      if (!e.ctrlKey || e.altKey || e.metaKey) return;
      const passo = { "+": 1, "=": 1, "-": -1, "_": -1, 0: 0 }[e.key];
      if (passo === undefined) return;
      e.preventDefault();
      mudarTamanho(passo);
    });

    cuidarDosDialogos();
    passosFalados();
    chamar("ano").then((r) => r.ok && mostrarAno(r));
  }

  window.lbaAcess = {
    mudar: mudarTamanho,
    get tamanho() { return acess.tamanho; },
  };
  window.lbaCentral = { abrirRelatorio };
  window.lbaLogin = { exigir: exigirLogin };

  // ===================================================== Demonstração

  const DEMO = {
    ano: new Date().getFullYear(),
    pastas: [],
    chamar(acao, d) {
      const atual = new Date().getFullYear();
      const anos = [];
      for (let a = 2020; a <= atual + 1; a++) anos.push(a);
      if (acao === "ano") return { ok: true, ano: this.ano, atual, anos };
      if (acao === "definir_ano") {
        this.ano = d.ano;
        return { ok: true, ano: this.ano, atual, anos };
      }
      if (acao === "painel_opcoes")
        return { ok: true, de: `${atual}-01-01`, ate: iso(new Date()), minutos: { OB: 20, NE: 15, DARE: 10 }, eu: "você", pastas: this.pastas };
      if (acao === "painel_incluir_pasta") {
        this.pastas.push({ caminho: "C:\\Users\\maria\\Documents", pessoa: "maria", existe: true });
        return { ok: true, pastas: this.pastas };
      }
      if (acao === "painel_remover_pasta") {
        this.pastas = this.pastas.filter((p) => p.caminho !== d.caminho);
        return { ok: true, pastas: this.pastas };
      }
      if (acao === "painel_gerar") return { ok: false, erro: "Na janela real, isto gera o relatório geral e abre no navegador." };
      const sistemas = { dare: ["DARE", "SEI"], bb: ["Banco do Brasil", "SEI"] }[d.automacao];
      if (acao === "login_estado") return { ok: true, sistemas, confirmado: (this.logins || []).includes(d.automacao) };
      if (acao === "abrir_abas") return { ok: true, sistemas };
      if (acao === "login_confirmado") {
        this.logins = (this.logins || []).concat(d.automacao);
        return { ok: true };
      }
      return { ok: false, erro: "?" };
    },
  };

  ligar();
})();
