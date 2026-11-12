/* Módulo Nota de Empenho — a NE numa aba só dela, separada da OB (app.js).
 *
 * Tudo no Python passa por UMA porta: api.ne(acao, dados), que chega em
 * janela/modulo_ne.py. A automação avisa a página pelos eventos "ne_*".
 * Das linhas do registro (eventos "log", que o app.js recebe), esta página
 * só lê as que chegam enquanto a NE roda, para a linha de andamento.
 * Aberta num navegador comum (?demo), a página usa a simulação do fim do
 * arquivo para mostrar o layout.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const DEMONSTRACAO = /[?&]demo\b/.test(location.search);
  const PASSOS = ["inicio", "login", "dados", "execucao", "conferencia", "concluido", "lotefim"];

  let g = null; // ganchos da Central (api, registrar eventos)

  const s = {
    iniciado: false,
    passo: "inicio",
    rodando: false,
    modo: "um", // "um" | "lote"
    ano: "2026",
    tipo: "NE - Nota de Empenho",
    pasta: "",
    pastaProcesso: "",
    processo: "",
    ne: "", // a NE completa, ex.: 2026NE000123
    fase: null,
    concluidas: 0,
    lote: { itens: [], resultados: [], relatorio: "", resposta: null },
  };

  // ----------------------------------------------------------- Python

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
      const r = api ? await api.ne(acao, dados) : DEMO.chamar(acao, dados);
      return r || { ok: false, erro: "sem resposta" };
    } catch (erro) {
      return { ok: false, erro: String(erro && erro.message ? erro.message : erro) };
    }
  }

  const semPython = () => DEMONSTRACAO && !(g && g.api());

  // ------------------------------------------------------------ Telas

  // Nos passos do topo: o fim do lote fica na Conferência; a NE concluída marca todos.
  const NA_BARRA = { inicio: 0, login: 1, dados: 2, execucao: 3, conferencia: 4, lotefim: 4, concluido: 5 };

  function ir(passo) {
    s.passo = passo;
    PASSOS.forEach((p) => ($(`ne-p-${p}`).hidden = p !== passo));
    document.querySelectorAll("#ne-passos li").forEach((li, i) => {
      li.classList.toggle("feito", i < NA_BARRA[passo]);
      li.classList.toggle("atual", i === NA_BARRA[passo]);
    });
    document.querySelector(".conteudo").scrollTop = 0;
  }

  async function mostrar() {
    $("tela-ne").hidden = false;
    ir(s.passo);
    if (s.iniciado) return;
    s.iniciado = true;
    const e = await chamar("estado");
    if (!e.ok) return;
    s.ano = e.ano;
    s.tipo = e.tipo_sei;
    s.pasta = e.pasta;
    document.querySelectorAll("[data-ne-versao]").forEach((el) => (el.textContent = e.versao));
    document.querySelectorAll("[data-ne-ano]").forEach((el) => (el.textContent = e.ano));
    document.querySelectorAll("[data-ne-tipo]").forEach((el) => (el.textContent = e.tipo_sei));
    if (!$("ne-in-processo").value) $("ne-in-processo").value = e.processo || "";
    if (!$("ne-in-ne").value) $("ne-in-ne").value = e.ne || "";
  }

  // ------------------------------------------------------ Andamento

  function fase(nome, classe, detalhe) {
    const el = document.querySelector(`[data-ne-fase="${nome}"]`);
    el.classList.remove("ativa", "feita", "falhou");
    if (classe) el.classList.add(classe);
    if (detalhe !== undefined && $(`ne-fase-${nome}-det`)) $(`ne-fase-${nome}-det`).textContent = detalhe;
  }
  const barra = (pct) => ($("ne-barra").style.width = Math.max(0, Math.min(100, pct)) + "%");

  function duracao(seg) {
    if (seg == null) return "—";
    const t = Math.round(seg), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), r = t % 60;
    const dd = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${dd(m)}:${dd(r)}` : `${m}:${dd(r)}`;
  }
  const relogio = { id: null };
  function relogioLigar() {
    relogioParar();
    const inicio = Date.now();
    $("ne-relogio-txt").textContent = "0:00";
    relogio.id = setInterval(() => ($("ne-relogio-txt").textContent = duracao((Date.now() - inicio) / 1000)), 1000);
  }
  function relogioParar() {
    if (relogio.id) clearInterval(relogio.id);
    relogio.id = null;
  }

  /* As mesmas mensagens da tela preta. Se o texto mudar nos .py, a barra
   * só deixa de andar -- nada quebra. */
  function log(linha) {
    const t = String(linha || "").trim();
    if (!t) return;
    if (!/^[-=#!]{6,}$/.test(t)) $("ne-agora").textContent = t.replace(/^[^\wÀ-ú(]+/, "");
    let m;
    if (s.fase === "sigef") {
      if (/^♻️/.test(t)) {
        fase("sigef", "ativa", "Reaproveitado");
        barra(44);
      } else if ((m = t.match(/📄 NE \d+: (\d+) página/))) {
        fase("sigef", "ativa", `${m[1]} página(s)`);
        barra(44);
      }
    } else if (s.fase === "sei") {
      if (/(📄|⏭️)\s+NE/.test(t)) {
        fase("sei", "ativa", /⏭️/.test(t) ? "NE (já feita)" : "Colando as páginas");
        barra(70);
      } else if (/Tentando de novo no mesmo documento/.test(t)) {
        fase("sei", "ativa", "Internet instável — tentando de novo");
      }
    }
  }

  function iniciarExecucao(rotuloLote) {
    s.rodando = true;
    $("ne-exec-processo").textContent = s.processo;
    $("ne-exec-ne").textContent = s.ne;
    $("ne-exec-sobre").textContent = rotuloLote || "Nota de Empenho · passo 4 de 5";
    $("ne-erro").hidden = true;
    $("ne-resumo").hidden = true;
    if (s.modo !== "lote") $("ne-lote-andamento").hidden = true;
    $("ne-fase-conf-det").textContent = s.modo === "lote" ? "No fim do lote" : "Com você";
    fase("sigef", null, "Aguardando");
    fase("sei", null, "Aguardando");
    fase("conf", null);
    barra(0);
    $("ne-agora").textContent = "Começando…";
    relogioLigar();
    ir("execucao");
  }

  function mostrarResumo(r) {
    s.pastaProcesso = r.pasta || "";
    const linhas = (r.arquivos || [])
      .map((a, i) => `<tr><td>${i + 1}</td><td class="mono">${esc(a.nome)}</td><td class="num">${esc(a.kb)} KB</td></tr>`)
      .join("");
    const avisos = (r.avisos || []).map((a) => `<div class="detalhe" style="color:var(--vermelho);padding:8px 20px">⚠ ${esc(a)}</div>`).join("");
    $("ne-resumo").innerHTML = `
      <div class="resumo-cab">
        <h3><svg class="ic"><use href="#i-doc"/></svg>Baixado do SIGEF — NE <span class="mono">${esc(s.ne)}</span></h3>
        <span class="nota">${(r.arquivos || []).length} página(s) em imagem · vira um documento “${esc(s.tipo)}”</span>
      </div>
      ${avisos}
      <table>
        <thead><tr><th>#</th><th>Arquivo</th><th style="text-align:right">Tamanho</th></tr></thead>
        <tbody>${linhas}</tbody>
      </table>`;
    $("ne-resumo").hidden = false;
  }

  // ------------------------------------------------ Eventos do Python

  const ROTULO_ESTADO = { pendente: "Na fila", rodando: "Em andamento…", ok: "Concluída", erro: "Erro" };

  function desenharAndamento() {
    const itens = s.lote.itens;
    $("ne-lote-itens").innerHTML = itens
      .map((it, i) => `<li class="${it.estado}" id="ne-lote-item-${i}">
          <span class="ponto"></span>
          <span class="quem">${esc(it.processo)} · NE ${esc(it.ne)}</span>
          <span class="estado">${esc(ROTULO_ESTADO[it.estado] || "")}</span>
        </li>`)
      .join("");
    const feitos = itens.filter((it) => ["ok", "erro"].includes(it.estado)).length;
    $("ne-lote-and-cont").textContent = `· ${feitos} de ${itens.length}`;
  }

  function mostrarFimLote() {
    const res = s.lote.resultados;
    const conta = (st) => res.filter((r) => r.estado === st).length;
    const ok = conta("ok"), erros = conta("erro"), naoFeitas = res.length - ok - erros;
    $("ne-lotefim-titulo").textContent = erros ? "Lote concluído, com erros" : naoFeitas ? "Lote interrompido" : "Lote concluído";
    $("ne-lotefim-lead").textContent = erros
      ? "As NEs com erro podem ser tentadas de novo: o programa continua de onde cada uma parou."
      : "Confira cada processo no SEI antes de assinar.";
    const caixa = (classe, n, rotulo) => `<div class="contador-caixa ${classe}"><strong>${n}</strong><span>${rotulo}</span></div>`;
    const cronometradas = res.filter((r) => r.tempo && r.tempo.total);
    const total = cronometradas.reduce((soma, r) => soma + r.tempo.total, 0);
    $("ne-lotefim-contadores").innerHTML =
      caixa("ok", ok, "concluída(s)") +
      (cronometradas.length ? caixa("", duracao(total), "tempo do lote") + caixa("", duracao(total / cronometradas.length), "média por NE") : "") +
      (erros ? caixa("erro", erros, "com erro") : "") +
      (naoFeitas ? caixa("pulado", naoFeitas, "não processada(s)") : "");
    const selo = (r) =>
      ({ ok: '<span class="selo ok">✓ Concluída</span>', erro: '<span class="selo erro">✗ Erro</span>' })[r.estado] ||
      '<span class="selo pulo">Não processada</span>';
    $("ne-lotefim-linhas").innerHTML = res
      .map((r) => {
        const detalhe = r.estado === "erro" ? (r.mensagem || "").trim().split("\n")[0] : "";
        const avisos = (r.avisos || []).map((a) => `<div class="detalhe" style="color:var(--vermelho)">⚠ ${esc(a)}</div>`).join("");
        return `<tr class="${r.estado === "erro" ? "invalida" : ""}">
          <td>${r.linha}</td><td class="mono">${esc(r.processo)}</td><td class="mono">${esc(r.ne)}</td>
          <td>${selo(r)}${detalhe ? `<div class="detalhe">${esc(detalhe)}</div>` : ""}${avisos}</td>
          <td class="mono">${r.tempo && r.tempo.total ? duracao(r.tempo.total) : "—"}</td>
        </tr>`;
      })
      .join("");
    $("ne-btn-lote-refazer").hidden = erros === 0;
    s.concluidas += ok;
    ir("lotefim");
  }

  const eventos = {
    ne_conectado: () => {
      $("ne-login-carregando").hidden = true;
      $("ne-login-erro").hidden = true;
      $("ne-login-pronto").hidden = false;
    },

    ne_etapa: (e) => {
      s.fase = e.etapa;
      if (e.etapa === "sigef") {
        fase("sigef", "ativa", "Imprimindo a NE");
        barra(4);
      } else if (e.etapa === "sei") {
        fase("sigef", "feita", "Concluído");
        fase("sei", "ativa", "Abrindo o processo");
        barra(48);
      }
    },

    ne_resumo: (e) => mostrarResumo(e.resumo),

    ne_conferencia: (e) => {
      s.rodando = false;
      s.fase = null;
      relogioParar();
      fase("sei", "feita", "Concluído");
      barra(100);
      const avisos = e.avisos || [];
      $("ne-conf-processo").textContent = e.processo || s.processo;
      $("ne-conf-avisos-lista").innerHTML = avisos.map((a) => `<li>${esc(a)}</li>`).join("");
      $("ne-conf-avisos").hidden = avisos.length === 0;
      document.querySelectorAll(".ne-chk-conf").forEach((c) => (c.checked = false));
      $("ne-btn-conf-ok").disabled = true;
      // A conferência precisa da pessoa: a aba da NE vem para a frente.
      if (window.lbaModulos && window.lbaModulos.atual !== "ne") window.lbaModulos.trocar("ne");
      ir("conferencia");
    },

    ne_concluido: (e) => {
      const t = e.tempos;
      $("ne-fim-tempo").hidden = !t;
      if (t) $("ne-fim-tempo").textContent = `⏱ Tempo da automação: ${duracao(t.total)} (SIGEF ${duracao(t.sigef)} · SEI ${duracao(t.sei)})`;
      $("ne-fim-ne").textContent = s.ne;
      $("ne-fim-processo").textContent = s.processo;
      s.concluidas += 1;
      ir("concluido");
    },

    ne_erro: (e) => {
      s.rodando = false;
      relogioParar();
      if (e.fase === "ne_conectar") {
        $("ne-login-carregando").hidden = true;
        $("ne-login-pronto").hidden = true;
        $("ne-login-erro-msg").textContent = e.mensagem;
        $("ne-login-erro").hidden = false;
        return ir("login");
      }
      const onde = s.fase;
      s.fase = null;
      document.querySelectorAll("#ne-p-execucao .fase.ativa").forEach((f) => f.classList.replace("ativa", "falhou"));
      $("ne-erro-msg").textContent = e.mensagem;
      $("ne-erro-retomar").textContent =
        onde === "sei"
          ? "“Continuar de onde parou” não baixa a NE de novo e não repete o que já foi anexado."
          : "“Continuar de onde parou” refaz o download no SIGEF; nada foi anexado no SEI ainda.";
      $("ne-erro").hidden = false;
      $("ne-agora").textContent = "Parado.";
      ir("execucao");
    },

    ne_lote_inicio: (e) => {
      s.modo = "lote";
      s.lote.itens = e.itens.map((it) => ({ ...it, estado: "pendente" }));
      $("ne-lote-andamento").hidden = false;
      $("ne-btn-parar-lote").disabled = false;
      $("ne-btn-parar-lote").textContent = "Parar depois desta NE";
      desenharAndamento();
    },

    ne_lote_item: (e) => {
      const it = s.lote.itens[e.indice];
      if (!it) return;
      Object.assign(it, { estado: e.estado, mensagem: e.mensagem, avisos: e.avisos });
      if (e.estado === "rodando") {
        s.processo = it.processo;
        s.ne = `${s.ano}NE${it.ne}`;
        iniciarExecucao(`Lote · NE ${e.indice + 1} de ${s.lote.itens.length}`);
      }
      desenharAndamento();
    },

    ne_lote_fim: (e) => {
      s.rodando = false;
      s.fase = null;
      relogioParar();
      s.lote.resultados = e.resultados;
      s.lote.relatorio = e.relatorio;
      mostrarFimLote();
    },
  };

  // ------------------------------------------------------ Formulário

  function marcar(campo, classe, html) {
    const el = $(`ne-campo-${campo}`);
    el.classList.remove("valido", "invalido");
    if (classe) el.classList.add(classe);
    $(`ne-dica-${campo}`).innerHTML = html;
  }
  const DICA_PROCESSO = 'Onde anexar a NE. Exemplo: <code>0029.001947/2026-67</code> ou <code>0029001947202667</code>';
  const DICA_NE = () => `Exemplo: <code>${esc(s.ano)}NE000123</code> ou só <code>123</code>`;

  async function conferir(final) {
    const processo = $("ne-in-processo").value.trim(), ne = $("ne-in-ne").value.trim();
    const r = await chamar("validar", { processo, ne });
    if (!processo) marcar("processo", final ? "invalido" : "", final ? "Informe o número do processo." : DICA_PROCESSO);
    else if (r.processo) marcar("processo", "valido", `✓ Entendi como <b class="mono">${esc(r.processo)}</b>`);
    else if (final || processo.replace(/\D/g, "").length >= 16)
      marcar("processo", "invalido", "Não parece um processo do SEI. O formato é <code>0000.000000/0000-00</code> — ou os 16 números seguidos.");
    else marcar("processo", "", DICA_PROCESSO);
    if (!ne) marcar("ne", final ? "invalido" : "", final ? "Informe o número da NE." : DICA_NE());
    else if (r.ne) marcar("ne", "valido", `✓ NE <b class="mono">${esc(r.ne.completa)}</b>`);
    else if (final || ne.length >= 6)
      marcar("ne", "invalido", `Não parece uma NE de ${esc(s.ano)} (a tela do SIGEF é deste exercício). ${DICA_NE()}.`);
    else marcar("ne", "", DICA_NE());
    return r;
  }

  // Um envio por vez: o segundo clique (ou Enter) enquanto o Python responde não manda de novo.
  let enviando = false;
  async function umEnvio(botao, fazer) {
    if (enviando) return;
    enviando = true;
    const antes = botao.disabled;
    botao.disabled = true;
    try {
      return await fazer();
    } finally {
      enviando = false;
      botao.disabled = antes;
    }
  }

  function avisoDeEnvio(id, texto) {
    $(id).textContent = texto || "";
    $(id).hidden = !texto;
  }

  const processar = (ev) => (ev && ev.preventDefault(), umEnvio($("ne-btn-processar"), processarAgora));

  async function processarAgora() {
    avisoDeEnvio("ne-dados-erro", "");
    const v = await conferir(true);
    if (!v.processo) return $("ne-in-processo").focus();
    if (!v.ne) return $("ne-in-ne").focus();
    const nomeArvore = $("ne-in-arvore").value.trim();
    const r = await chamar("processar", { processo: $("ne-in-processo").value, ne: $("ne-in-ne").value, nome_arvore: nomeArvore });
    if (!r.ok) return r.campo ? $(`ne-in-${r.campo}`).focus() : avisoDeEnvio("ne-dados-erro", r.erro || "Não consegui começar. Tente de novo.");
    s.modo = "um";
    s.nomeArvore = nomeArvore;
    s.processo = r.processo;
    s.ne = r.ne_completa;
    iniciarExecucao();
    if (semPython()) DEMO.processar();
  }

  function escolherAba(modo) {
    s.modo = modo;
    $("ne-aba-um").classList.toggle("ativa", modo === "um");
    $("ne-aba-lote").classList.toggle("ativa", modo === "lote");
    $("ne-aba-um").setAttribute("aria-selected", modo === "um");
    $("ne-aba-lote").setAttribute("aria-selected", modo === "lote");
    $("ne-form").hidden = modo !== "um";
    $("ne-form-lote").hidden = modo !== "lote";
    if (modo === "lote") setTimeout(() => $("ne-in-lista").focus(), 60);
  }

  function irParaDados() {
    const outra = s.concluidas > 0;
    $("ne-dados-sobre").textContent = outra ? `NE nº ${s.concluidas + 1} desta sessão` : "Nota de Empenho · passo 3 de 5";
    $("ne-dados-titulo").textContent = outra ? "Próximo processo e Nota de Empenho" : "Informe o processo e a Nota de Empenho";
    ir("dados");
    escolherAba(s.modo === "lote" ? "lote" : "um");
    conferir(false);
    if (s.modo !== "lote") setTimeout(() => $("ne-in-processo").select(), 60);
  }

  function desenharPrevia(r) {
    s.lote.resposta = r;
    $("ne-lote-erro-leitura").hidden = true;
    if (!r || r.cancelou) return;
    if (!r.ok) {
      $("ne-lote-previa").hidden = true;
      $("ne-btn-lote").disabled = true;
      $("ne-lote-erro-leitura").textContent = `Não consegui ler ${r.arquivo ? "a planilha" : "a lista"}: ${r.erro}`;
      $("ne-lote-erro-leitura").hidden = false;
      return;
    }
    $("ne-lote-arquivo").textContent = r.arquivo ? `✓ ${r.arquivo}` : "";
    const itens = r.itens || [];
    $("ne-lote-previa").hidden = itens.length === 0;
    const prontas = itens.filter((i) => !i.erro).length;
    const repetir = itens.filter((i) => !i.erro && i.ja_concluida).length;
    const erros = itens.length - prontas;
    $("ne-lote-contagem").textContent =
      `${prontas} pronta(s)` + (repetir ? ` · ${repetir} já anexada(s) antes` : "") + (erros ? ` · ${erros} com problema` : "");
    $("ne-lote-linhas").innerHTML = itens
      .map((i) => {
        const situacao = i.erro
          ? `<span class="selo erro">✗ ${esc(i.erro)}</span><div class="original">${esc(i.original)}</div>`
          : i.ja_concluida
            ? '<span class="selo ok">✓ Pronta</span><div class="detalhe">Já foi anexada antes — será anexada de novo; confira duplicidade no fim.</div>'
            : '<span class="selo ok">✓ Pronta</span>';
        return `<tr class="${i.erro ? "invalida" : ""}"><td>${i.linha}</td><td class="mono">${esc(i.processo || "—")}</td><td class="mono">${esc(i.ne || "—")}</td><td>${situacao}</td></tr>`;
      })
      .join("");
    $("ne-btn-lote").disabled = prontas === 0;
    $("ne-btn-lote-txt").textContent = prontas ? `Processar ${prontas} NE${prontas > 1 ? "s" : ""}` : "Processar a lista";
  }

  let esperaLeitura = null;
  function lerListaDigitada() {
    clearTimeout(esperaLeitura);
    esperaLeitura = setTimeout(async () => {
      $("ne-lote-arquivo").textContent = "";
      desenharPrevia(await chamar("ler_texto", { texto: $("ne-in-lista").value }));
    }, 350);
  }

  const iniciarLote = (linhas) => umEnvio($("ne-btn-lote"), () => iniciarLoteAgora(linhas));

  async function iniciarLoteAgora(linhas) {
    avisoDeEnvio("ne-lote-erro-leitura", "");
    const r = await chamar("processar_lote", { linhas: linhas || null });
    if (!r.ok) return avisoDeEnvio("ne-lote-erro-leitura", r.erro || "");
    s.modo = "lote";
    s.lote.itens = [];
    iniciarExecucao("Lote · começando");
    if (semPython()) DEMO.lote();
  }

  // ------------------------------------------------------------ Botões

  function conectar() {
    $("ne-login-carregando").hidden = false;
    $("ne-login-erro").hidden = true;
    $("ne-login-pronto").hidden = true;
    document.querySelectorAll(".ne-chk-login").forEach((c) => (c.checked = false));
    $("ne-btn-login-ok").disabled = true;
    ir("login");
    chamar("conectar");
    if (semPython()) setTimeout(() => eventos.ne_conectado(), 600);
  }

  function ligarBotoes() {
    $("ne-btn-comecar").onclick = conectar;
    $("ne-btn-reabrir").onclick = conectar;
    $("ne-btn-reconectar").onclick = conectar;

    const liberar = (classe, botao) =>
      document.querySelectorAll(classe).forEach((c) =>
        c.addEventListener("change", () => ($(botao).disabled = ![...document.querySelectorAll(classe)].every((x) => x.checked)))
      );
    liberar(".ne-chk-login", "ne-btn-login-ok");
    liberar(".ne-chk-conf", "ne-btn-conf-ok");

    $("ne-btn-login-ok").onclick = () => {
      chamar("login_ok"); // leva a aba do SIGEF para a tela da NE
      irParaDados();
    };

    $("ne-aba-um").onclick = () => escolherAba("um");
    $("ne-aba-lote").onclick = () => escolherAba("lote");
    $("ne-form").addEventListener("submit", processar);
    $("ne-in-processo").addEventListener("input", () => conferir(false));
    $("ne-in-ne").addEventListener("input", () => conferir(false));
    $("ne-in-processo").addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      $("ne-in-ne").focus();
      $("ne-in-ne").select();
    });

    $("ne-in-lista").addEventListener("input", lerListaDigitada);
    $("ne-btn-planilha").onclick = async () => {
      if (semPython()) return alert("Na janela real, isto abre a escolha da planilha.");
      const r = await chamar("escolher_planilha");
      if (r.cancelou) return;
      $("ne-in-lista").value = "";
      desenharPrevia(r);
    };
    $("ne-btn-lote").onclick = () => iniciarLote();
    $("ne-btn-parar-lote").onclick = () => {
      chamar("parar_lote");
      $("ne-btn-parar-lote").disabled = true;
      $("ne-btn-parar-lote").textContent = "Vai parar ao fim desta NE";
    };
    $("ne-btn-lote-refazer").onclick = () => iniciarLote(s.lote.resultados.filter((r) => r.estado === "erro").map((r) => r.linha));
    $("ne-btn-lote-relatorio").onclick = () => chamar("abrir_arquivo", { caminho: s.lote.relatorio });
    $("ne-btn-lote-novo").onclick = () => {
      $("ne-in-lista").value = "";
      $("ne-lote-arquivo").textContent = "";
      $("ne-lote-previa").hidden = true;
      $("ne-btn-lote").disabled = true;
      s.lote.resposta = null;
      s.modo = "lote";
      irParaDados();
    };

    $("ne-btn-conf-ok").onclick = () => {
      fase("conf", "feita");
      $("ne-agora").textContent = "Finalizando…";
      chamar("concluir_conferencia");
      if (semPython()) DEMO.concluir();
    };

    $("ne-btn-erro-voltar").onclick = irParaDados;
    $("ne-btn-erro-continuar").onclick = async () => {
      if (s.modo === "lote") {
        if (!s.lote.itens.length) return iniciarLote(); // parou antes de começar
        const faltam = s.lote.itens.filter((i) => i.estado !== "ok").map((i) => i.linha);
        return faltam.length ? iniciarLote(faltam) : irParaDados();
      }
      const r = await chamar("processar", { processo: s.processo, ne: s.ne, nome_arvore: s.nomeArvore || "" });
      if (!r.ok) return irParaDados();
      iniciarExecucao();
      if (semPython()) DEMO.processar();
    };
    $("ne-btn-outra").onclick = () => {
      $("ne-in-processo").value = "";
      $("ne-in-ne").value = "";
      $("ne-in-arvore").value = "";
      s.modo = "um";
      irParaDados();
    };
    $("ne-btn-erro-pasta").onclick = () => chamar("abrir_pasta", { caminho: s.pastaProcesso || s.pasta });
    $("ne-btn-fim-pasta").onclick = () => chamar("abrir_pasta", { caminho: s.pastaProcesso });

    // "Relatório geral" (data-relatorio-geral) é ligado em central.js: um relatório só, de todas as automações.
  }

  function ligar(ganchos) {
    g = ganchos;
    g.registrarEventos(eventos);
    ligarBotoes();
  }

  /* O ano do SIGEF mudou (menu do topo, central.js): a NE é conferida
   * com o ano novo -- e a lista já colada é lida de novo. */
  function atualizarAno(ano) {
    if (!ano || ano === s.ano) return;
    s.ano = ano;
    document.querySelectorAll("[data-ne-ano]").forEach((el) => (el.textContent = ano));
    if (s.passo !== "dados") return;
    conferir(false);
    if ($("ne-in-lista").value.trim()) lerListaDigitada();
  }

  window.lbaNe = {
    ligar,
    mostrar,
    log,
    atualizarAno,
    get rodando() { return s.rodando; },
    get DEMO() { return DEMO; }, // os testes espiam a simulação (?demo)
  };

  // ===================================================== Demonstração
  // Só para ver o layout num navegador comum (index.html?demo).

  const DEMO = {
    itens: [],
    emitir(lista, passo = 450) {
      lista.forEach((ev, i) => setTimeout(() => (ev.tipo === "log" ? log(ev.texto) : eventos[ev.tipo](ev)), i * passo));
    },
    // A mesma regra do automacoes/ne/etapa.py (normalizar_ne).
    ne(t) {
      const m = String(t || "").trim().match(/^(?:(\d{4})\s*NE\s*)?(\d{1,6})$/i);
      if (!m || (m[1] && m[1] !== s.ano) || !Number(m[2])) return null;
      const ne = m[2].padStart(6, "0");
      return { ne, completa: `${s.ano}NE${ne}` };
    },
    processo(t) {
      const d = String(t || "").replace(/\D/g, "");
      return d.length === 16 ? `${d.slice(0, 4)}.${d.slice(4, 10)}/${d.slice(10, 14)}-${d.slice(14)}` : null;
    },
    chamar(acao, d) {
      if (acao === "estado") return { ok: true, versao: "demo", ano: s.ano, tipo_sei: "NE - Nota de Empenho", pasta: "", processo: "", ne: "" };
      if (acao === "validar") return { ok: true, processo: this.processo(d.processo), ne: this.ne(d.ne) };
      if (acao === "processar") {
        const p = this.processo(d.processo), n = this.ne(d.ne);
        return !p ? { ok: false, campo: "processo" } : !n ? { ok: false, campo: "ne" } : { ok: true, processo: p, ne: n.ne, ne_completa: n.completa };
      }
      if (acao === "ler_texto") {
        this.itens = [];
        String(d.texto || "").split("\n").forEach((linha, i) => {
          if (!/\d/.test(linha)) return;
          const proc = (linha.match(/\d{4}\.?\d{6}\/?\d{4}-?\d{2}/) || [""])[0];
          const n = this.ne((linha.replace(proc, "").match(/\d{4}NE\d+|\b\d{5,6}\b/i) || [""])[0]);
          this.itens.push({ linha: i + 1, processo: this.processo(proc) || "", ne: n ? n.ne : "", original: linha.trim(), ja_concluida: false,
            erro: !proc ? "não achei o número do processo" : !n ? "não achei o número da NE" : "" });
        });
        return { ok: true, arquivo: "", itens: this.itens };
      }
      return { ok: true };
    },
    processar() {
      const ne = s.ne.slice(-6);
      this.emitir([
        { tipo: "ne_etapa", etapa: "sigef" },
        { tipo: "log", texto: `   📄 NE ${ne}: 2 página(s) em PNG.` },
        { tipo: "ne_etapa", etapa: "sei" },
        { tipo: "ne_resumo", resumo: { ne, pasta: "", avisos: [], arquivos: [
          { nome: `Nota de Empenho - NE ${ne}_1.png`, kb: 182 }, { nome: `Nota de Empenho - NE ${ne}_2.png`, kb: 97 }] } },
        { tipo: "log", texto: `📄 NE ${ne} (2 página(s))...` },
        { tipo: "ne_conferencia", processo: s.processo, avisos: [] },
      ]);
    },
    concluir() {
      this.emitir([{ tipo: "ne_concluido", tempos: { sigef: 41.2, sei: 63.9, total: 105.1 } }]);
    },
    lote() {
      const itens = this.itens.filter((i) => !i.erro);
      const ev = [{ tipo: "ne_lote_inicio", itens }];
      const resultados = [];
      itens.forEach((it, i) => {
        const erro = i === 1;
        const mensagem = erro ? "❌ falha de demonstração" : "";
        ev.push(
          { tipo: "ne_lote_item", indice: i, estado: "rodando" },
          { tipo: "ne_etapa", etapa: "sigef" },
          { tipo: "ne_etapa", etapa: "sei" },
          { tipo: "ne_lote_item", indice: i, estado: erro ? "erro" : "ok", mensagem, avisos: [] }
        );
        resultados.push({ ...it, estado: erro ? "erro" : "ok", mensagem, avisos: [], tempo: { sigef: 40 + i, sei: 60 + i, total: 100 + 2 * i } });
      });
      ev.push({ tipo: "ne_lote_fim", resultados, relatorio: "" });
      this.emitir(ev, 300);
    },
  };
})();
