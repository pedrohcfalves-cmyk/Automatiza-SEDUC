/* Módulos da barra lateral: Anexar no SEI (app.js), DARE (dare.js) e Banco do Brasil.
 *
 * app.js expõe window.lbaModulos.ganchos (api, mostrar a tela do SEI,
 * registrar tratadores de evento). Aqui ficam só a troca de módulo e a
 * tela do BB, que é simples: formulário -> Executar -> registro.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const guardar = (chave, valor) => { try { localStorage.setItem(chave, valor); } catch (e) { /* sem armazenamento: tudo bem */ } };
  const lembrar = (chave) => { try { return localStorage.getItem(chave); } catch (e) { return null; } };

  const m = {
    atual: "sei",
    rodando: null,            // "bb" | null
    carregado: { bb: false },
    bb: { automacoes: [], pasta: "", palavra: "CARREGAR" },
  };
  let g = null;               // ganchos do app.js

  // ------------------------------------------------------ Troca de módulo

  function trocar(modulo) {
    m.atual = modulo;
    document.querySelectorAll(".modulo").forEach((b) => {
      const ativo = b.dataset.modulo === modulo;
      b.classList.toggle("ativo", ativo);
      if (ativo) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    $("passos").hidden = modulo !== "sei";
    $("contador").style.display = modulo === "sei" ? "" : "none";
    // O DARE troca os passos do SEI pelas páginas dele (como a barra lateral do aplicativo DARE).
    const dare = window.lbaDare;
    if ($("dare-nav")) $("dare-nav").hidden = modulo !== "dare";
    if (dare && modulo !== "dare") dare.esconder();
    if (modulo === "sei") {
      g.mostrarSei();
      return;
    }
    document.querySelectorAll(".tela").forEach((s) => (s.hidden = s.id !== `tela-${modulo}`));
    document.querySelector(".conteudo").scrollTop = 0;
    if (modulo === "dare") {
      if (dare) dare.mostrar();
      return;
    }
    if (!m.carregado[modulo]) carregar(modulo);
  }

  function ponto(modulo, ligado) {
    const botao = document.querySelector(`.modulo[data-modulo="${modulo}"]`);
    let el = botao.querySelector(".rodando");
    if (ligado && !el) {
      el = document.createElement("i");
      el.className = "rodando";
      el.title = "Rodando";
      botao.appendChild(el);
    } else if (!ligado && el) el.remove();
  }

  function status(modulo, texto, classe) {
    const el = $(`${modulo}-status`);
    el.textContent = texto || "";
    el.className = "modulo-status" + (classe ? " " + classe : "");
  }

  // -------------------------------------------------------- Formulários

  function preencherAbas(select, abas, atual) {
    const lista = [...(abas || [])];
    if (atual && !lista.includes(atual)) lista.unshift(atual);
    select.innerHTML =
      (lista.length ? "" : '<option value="">(primeira aba)</option>') +
      lista.map((a) => `<option value="${esc(a)}"${a === atual ? " selected" : ""}>${esc(a)}</option>`).join("");
  }

  function mostrarArquivo(modulo, caminho) {
    const el = $(`${modulo}-arquivo`);
    el.textContent = caminho ? caminho : "Nenhuma escolhida";
    el.title = caminho || "";
    el.classList.toggle("escolhido", !!caminho);
    el.dataset.caminho = caminho || "";
  }

  function opcoes(container, nome, itens, escolhido) {
    container.innerHTML = itens
      .map(
        (it) => `<label class="opcao">
          <input type="radio" name="${nome}" value="${esc(it.valor)}"${String(it.valor) === String(escolhido) ? " checked" : ""}>
          <span class="radio"></span>
          <span class="texto"><b>${esc(it.nome)}</b>${it.dica ? `<small>${esc(it.dica)}</small>` : ""}</span>
        </label>`
      )
      .join("");
  }

  const escolhida = (nome) => (document.querySelector(`input[name="${nome}"]:checked`) || {}).value;

  async function carregar(modulo) {
    status(modulo, "Carregando…");
    let r;
    try {
      r = g.api() ? await g.api()[`${modulo}_estado`]() : DEMO[modulo];
    } catch (erro) {
      r = { ok: false, erro: String(erro) };
    }
    if (!r || !r.ok) {
      status(modulo, `Não consegui carregar o módulo: ${(r && r.erro) || "sem resposta"}`, "erro");
      return;
    }
    m.carregado[modulo] = true;
    status(modulo, "");
    preencherBb(r);
  }

  // ---------------------------------------------------------------- BB

  function preencherBb(r) {
    const c = r.config;
    m.bb.automacoes = r.automacoes;
    m.bb.pasta = r.pasta || "";
    m.bb.palavra = r.palavra_confirmacao || "CARREGAR";
    $("bb-programa").innerHTML = (r.programas || [])
      .map((p) => `<option value="${esc(p.valor)}">${esc(p.rotulo)}</option>`)
      .join("");
    const programa = lembrar("bb-programa");
    if (programa) $("bb-programa").value = programa;
    $("bb-confirmacao").placeholder = `Digite ${m.bb.palavra}`;
    $("bb-confirmacao-dica").textContent = `Digite ${m.bb.palavra} para liberar: a carga real movimenta dinheiro no cartão.`;
    mostrarArquivo("bb", c.caminho_planilha);
    preencherAbas($("bb-aba"), r.abas, c.aba_planilha);
    $("bb-linha").value = c.linha_inicial || 2;
    $("bb-visivel").checked = !!c.modo_visivel;
    opcoes(
      $("bb-automacoes"), "bb-auto",
      r.automacoes.map((a) => ({ valor: a.indice, nome: a.nome, dica: a.sem_planilha ? "Sem planilha: preencha processo, cartão e valor abaixo" : "" })),
      lembrar("bb-auto") ?? "0"
    );
    ajustarBb();
  }

  // Mostra só os campos que a automação escolhida usa, e a confirmação
  // da carga REAL só quando o modo é real.
  function ajustarBb() {
    const indice = Number(escolhida("bb-auto") ?? 0);
    const auto = m.bb.automacoes[indice];
    const semPlanilha = !!(auto && auto.sem_planilha);
    const campos = (auto && auto.campos) || [];
    $("bb-campo-planilha").hidden = semPlanilha;
    $("bb-campos-planilha").hidden = semPlanilha;
    document.querySelectorAll("[data-campo-bb]").forEach((el) => (el.hidden = !campos.includes(el.dataset.campoBb)));
    const real = campos.includes("modo") && $("bb-modo").value === "real";
    $("bb-campo-confirmar").hidden = !real;
    if (!real) $("bb-confirmacao").value = "";
    const anexar = document.querySelector('[data-campo-bb="anexar_saldos"]');
    if (anexar && !real) anexar.hidden = true;
  }

  function respostasBb() {
    return {
      programa: $("bb-programa").value,
      modo: $("bb-modo").value,
      repetidos: $("bb-repetidos").value,
      confirmacao: $("bb-confirmacao").value.trim(),
      processo: $("bb-processo").value.trim(),
      cartao: $("bb-cartao").value.trim(),
      valor: $("bb-valor").value.trim(),
      nova_parcela: $("bb-nova-parcela").checked,
      anexar_saldos: $("bb-anexar").checked && $("bb-modo").value === "real",
    };
  }

  function valoresBb() {
    return {
      caminho_planilha: $("bb-arquivo").dataset.caminho || "",
      aba_planilha: $("bb-aba").value,
      linha_inicial: $("bb-linha").value,
      modo_visivel: $("bb-visivel").checked,
    };
  }

  async function executarBb() {
    const indice = escolhida("bb-auto");
    if (indice == null) return status("bb", "Escolha a automação.", "erro");
    const auto = m.bb.automacoes[Number(indice)] || {};
    const respostas = respostasBb();
    if ((auto.campos || []).includes("modo") && respostas.modo === "real" && respostas.confirmacao.toUpperCase() !== m.bb.palavra) {
      $("bb-confirmacao").focus();
      return status("bb", `Carga REAL: digite ${m.bb.palavra} no campo de confirmação.`, "erro");
    }
    guardar("bb-auto", indice);
    guardar("bb-programa", respostas.programa);
    if (!g.api()) return demoRodar("bb", "BB · demonstração");
    const r = await g.api().bb_executar(valoresBb(), Number(indice), respostas);
    if (!r.ok) status("bb", r.erro || "Não consegui começar.", "erro");
    else $("bb-confirmacao").value = "";   // a confirmação vale para uma rodada só
  }

  // ------------------------------------------------------------ Eventos

  function travar(modulo, rodando) {
    $(`${modulo}-form`).setAttribute("aria-disabled", rodando ? "true" : "false");
    $(`${modulo}-executar`).disabled = rodando;
    document.querySelectorAll(`#tela-${modulo} [data-parar-modulo]`).forEach((b) => {
      b.hidden = !rodando;
      b.disabled = false;
    });
  }

  const eventos = {
    modulo_inicio: (e) => {
      m.rodando = e.modulo;
      travar(e.modulo, true);
      ponto(e.modulo, true);
      status(e.modulo, `Rodando: ${e.nome}. Acompanhe no registro abaixo.`);
      $("registro").open = true;
    },
    bb_pergunta: (e) => {
      $("bb-pergunta-texto").textContent = e.texto || "O BB precisa de uma resposta.";
      $("bb-pergunta-opcoes").innerHTML = (e.opcoes || [])
        .map((o, i) => `<button class="btn ${i === 0 ? "primario" : "fantasma"}" type="button" data-resposta="${esc(o.valor)}">${esc(o.rotulo)}</button>`)
        .join("");
      $("bb-pergunta-resp").value = "";
      $("bb-pergunta").hidden = false;
      document.querySelector('.modulo[data-modulo="bb"]').classList.add("atencao");
      if (m.atual === "bb") {
        $("bb-pergunta").scrollIntoView({ block: "nearest", behavior: "smooth" });
        const primeiro = $("bb-pergunta-opcoes").querySelector("button") || $("bb-pergunta-resp");
        primeiro.focus();
      }
      status("bb", "Esperando sua resposta (abaixo).");
    },
    bb_pergunta_fim: () => {
      $("bb-pergunta").hidden = true;
      document.querySelector('.modulo[data-modulo="bb"]').classList.remove("atencao");
      if (m.rodando === "bb") status("bb", "Rodando. Acompanhe no registro abaixo.");
    },
    modulo_fim: (e) => {
      if (e.modulo === "bb") eventos.bb_pergunta_fim();
      m.rodando = null;
      travar(e.modulo, false);
      ponto(e.modulo, false);
      if (e.erro) status(e.modulo, `Parou: ${e.erro.split("\n")[0]}`, "erro");
      else status(e.modulo, `Terminou às ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}. Confira a planilha e o registro.`, "ok");
    },
  };

  // --------------------------------------------------------- Demonstração

  const DEMO = {
    bb: {
      ok: true,
      pasta: "",
      abas: ["Cartões"],
      config: { caminho_planilha: "", aba_planilha: "", linha_inicial: 2, modo_visivel: true },
      automacoes: [
        { indice: 0, nome: "Carregamento Pelo Portador", sem_planilha: false, campos: [] },
        { indice: 1, nome: "Carga de Limite (Cartão Corporativo)", sem_planilha: false, campos: ["programa", "modo", "repetidos"] },
        { indice: 2, nome: "Anexar Saldos no SEI", sem_planilha: false, campos: [] },
        { indice: 3, nome: "Carga Avulsa (1 processo, sem planilha)", sem_planilha: true, campos: ["avulsa", "programa", "modo", "anexar_saldos"] },
      ],
      programas: [
        { valor: "PNAE", rotulo: "PNAE — 1 filtro de carregamento" },
        { valor: "PROAFI", rotulo: "PROAFI — 27 filtros de carregamento" },
      ],
      palavra_confirmacao: "CARREGAR",
    },
  };

  function demoRodar(modulo, nome) {
    eventos.modulo_inicio({ modulo, nome });
    if (modulo === "bb") {
      setTimeout(() => eventos.bb_pergunta({
        texto: "Depois de logar no BB, pressione Enter (Enviar) para continuar",
        opcoes: [{ valor: "", rotulo: "Continuar" }],
      }), 600);
      return;
    }
    setTimeout(() => eventos.modulo_fim({ modulo, erro: null }), 2500);
  }

  // -------------------------------------------------------------- Partida

  function ligar(ganchos) {
    g = ganchos;
    g.registrarEventos(eventos);
    if (window.lbaDare) window.lbaDare.ligar(ganchos);

    document.querySelectorAll(".modulo").forEach((b) => (b.onclick = () => trocar(b.dataset.modulo)));

    document.querySelectorAll("[data-escolher-planilha]").forEach((b) => {
      b.onclick = async () => {
        const modulo = b.dataset.escolherPlanilha;
        if (!g.api()) return status(modulo, "Na janela real, isto abre a escolha do arquivo.");
        const r = await g.api().escolher_planilha_modulo();
        if (!r) return;
        mostrarArquivo(modulo, r.caminho);
        preencherAbas($(`${modulo}-aba`), r.abas, (r.abas || [])[0] || "");
      };
    });

    $("bb-executar").onclick = executarBb;
    $("bb-automacoes").addEventListener("change", ajustarBb);
    $("bb-modo").addEventListener("change", ajustarBb);

    // Resposta da pergunta que surgiu no meio da rodada.
    const responderBb = (texto) => {
      $("bb-pergunta").hidden = true;
      if (g.api()) g.api().bb_responder(texto);
      else {
        eventos.bb_pergunta_fim();
        setTimeout(() => eventos.modulo_fim({ modulo: "bb", erro: null }), 800);
      }
    };
    $("bb-pergunta-opcoes").addEventListener("click", (e) => {
      const botao = e.target.closest("button[data-resposta]");
      if (botao) responderBb(botao.dataset.resposta);
    });
    $("bb-pergunta-enviar").onclick = () => responderBb($("bb-pergunta-resp").value);
    $("bb-pergunta-resp").addEventListener("keydown", (e) => e.key === "Enter" && $("bb-pergunta-enviar").click());
    $("bb-pasta").onclick = () => g.api() && g.api().abrir_pasta(m.bb.pasta);
    document.querySelectorAll("[data-parar-modulo]").forEach((b) => {
      b.onclick = () => {
        b.disabled = true;
        if (m.rodando) status(m.rodando, "Parada pedida: termina a linha atual e para.");
        if (g.api()) g.api().modulo_parar();
      };
    });
  }

  window.lbaModulos = {
    ligar,
    trocar,
    get atual() { return m.atual; },
  };
})();
