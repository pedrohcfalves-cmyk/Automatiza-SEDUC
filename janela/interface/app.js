/* Automação SIGEF → SEI — lógica da janela.
 *
 * O Python chama lba.receber([eventos]) com o que aconteceu (linhas de
 * registro, mudança de etapa, pergunta, erro). A janela chama o Python
 * por window.pywebview.api.<método>(). Aberta num navegador comum, com
 * ?demo no endereço, a página roda uma simulação para ver o layout.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const ORDEM = ["inicio", "login", "dados", "execucao", "conferencia"];
  const DOCUMENTOS = ["CE", "NL", "PP", "OB"];

  const estado = {
    pasta: "",
    pastaProcesso: "",
    processo: "",
    ob: "",
    tipoOb: "",
    documentos: DOCUMENTOS.slice(), // os marcados quando o processo/lote começou
    tiposOb: {
      regularizacao: "OB - Ordem Bancária de Regularização",
      ordem_bancaria: "OB - Ordem Bancária",
    },
    concluidos: 0,
    modo: "um", // "um" processo ou "lote"
    lote: { itens: [], resultados: [], relatorio: "", resposta: null },
    totalDocsSei: 0,
    docsSei: 0,
    linhas: 0,
  };

  let api = null; // preenchido quando o pywebview fica pronto

  // ------------------------------------------------------------ Telas

  // As telas do SIGEF → SEI só aparecem quando esse módulo está aberto na
  // barra lateral (modulos.js); vendo outro módulo, a tela é só lembrada
  // e volta quando a pessoa voltar para "Anexar no SEI".
  function mostrar(tela) {
    estado.telaSei = tela;
    if (window.lbaModulos && window.lbaModulos.atual !== "sei") return;
    exibirTela(tela);
  }

  function exibirTela(tela) {
    document.querySelectorAll(".tela").forEach((s) => (s.hidden = s.id !== `tela-${tela}`));
    const passo = tela === "concluido" ? "fim" : tela === "lote-fim" ? "conferencia" : tela;
    const indice = passo === "fim" ? ORDEM.length : ORDEM.indexOf(passo);
    document.querySelectorAll("#passos li").forEach((li, i) => {
      li.classList.toggle("feito", i < indice);
      li.classList.toggle("atual", i === indice);
    });
    document.querySelector(".conteudo").scrollTop = 0;
  }

  // ---------------------------------------------------------- Registro

  function registrar(texto) {
    const pre = $("registro-txt");
    const perto = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    pre.textContent += texto + "\n";
    if (perto) pre.scrollTop = pre.scrollHeight;
    estado.linhas += 1;
    $("registro-qtd").textContent = estado.linhas;
  }

  // ------------------------------------------------------------ Fases

  function fase(nome, classe, detalhe) {
    const el = document.querySelector(`.fase[data-fase="${nome}"]`);
    el.classList.remove("ativa", "feita", "falhou");
    if (classe) el.classList.add(classe);
    if (detalhe !== undefined && $(`fase-${nome}-det`)) $(`fase-${nome}-det`).textContent = detalhe;
  }

  function barra(pct) {
    $("barra").style.width = Math.max(0, Math.min(100, pct)) + "%";
  }

  let faseAtual = null;

  // ---- Relógio da OB em andamento (só mostra; a métrica oficial é
  //      medida no Python e gravada em metricas/metricas.csv).
  function duracao(seg) {
    if (seg == null) return "—";
    const s = Math.round(seg), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    const dd = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${dd(m)}:${dd(r)}` : `${m}:${dd(r)}`;
  }
  const relogio = { inicio: 0, id: null };
  function relogioLigar() {
    relogioParar();
    relogio.inicio = Date.now();
    $("relogio").classList.remove("parado");
    $("relogio-txt").textContent = "0:00";
    relogio.id = setInterval(() => ($("relogio-txt").textContent = duracao((Date.now() - relogio.inicio) / 1000)), 1000);
  }
  function relogioParar() {
    if (relogio.id) clearInterval(relogio.id);
    relogio.id = null;
    $("relogio").classList.add("parado");
  }

  /* Lê as linhas do registro para dar andamento à barra. São as mesmas
   * mensagens que a tela preta mostrava: se o texto mudar nos .py, a
   * barra só deixa de andar -- nada quebra. */
  function interpretar(linha) {
    const t = linha.trim();
    if (!t) return;
    if (!/^[-=#!]{6,}$/.test(t)) $("agora").textContent = t.replace(/^[^\wÀ-ú(]+/, "");

    let m;
    if (faseAtual === "sigef") {
      if (/^♻️/.test(t)) {
        fase("sigef", "ativa", "Reaproveitado");
        barra(46);
      } else if ((m = t.match(/(\d+)\/(\d+): PP (\S+)/))) {
        const [i, n] = [+m[1], +m[2]];
        fase("sigef", "ativa", `PP ${i} de ${n}`);
        barra(5 + (40 * (i - 1)) / n);
      } else if (/Por último: Ordem Bancária/.test(t)) {
        fase("sigef", "ativa", "Ordem Bancária");
        barra(44);
      }
    } else if (faseAtual === "sei") {
      if ((m = t.match(/(📄|⏭️)\s+(CE|NL|PP|OB)(?: (\d+)\/(\d+))?/))) {
        estado.docsSei += 1;
        const total = Math.max(estado.totalDocsSei, estado.docsSei);
        const nome = m[3] ? `${m[2]} ${m[3]} de ${m[4]}` : m[2];
        fase("sei", "ativa", m[1] === "⏭️" ? `${nome} (já feito)` : nome);
        barra(50 + (45 * (estado.docsSei - 1)) / total);
      } else if (/Tentando de novo no mesmo documento/.test(t)) {
        fase("sei", "ativa", "Internet instável — tentando de novo");
      }
    }
  }

  // ----------------------------------------------------------- Resumo

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function mostrarResumo(r) {
    estado.pastaProcesso = r.pasta || "";
    const n = r.lancamentos.length;
    const ces = r.ces || [];
    const docs = r.documentos || DOCUMENTOS;
    const tem = (sigla) => docs.includes(sigla);
    estado.totalDocsSei =
      (tem("CE") ? ces.length : 0) + (tem("OB") && r.obs.length ? 1 : 0) + (tem("NL") ? n : 0) + (tem("PP") ? n : 0);
    estado.docsSei = 0;

    const linhas = r.lancamentos
      .map(
        (l, i) => `<tr>
          <td>${i + 1}</td>
          <td class="mono">${esc(l.pp)}</td>
          <td class="mono">${esc(l.ce || "—")}</td>
          <td class="num">R$ ${esc(l.valor)}</td>
          <td>${l.ok ? '<span class="selo ok">✓ baixado</span>' : '<span class="selo alerta">⚠ faltou algo</span>'}
              <div class="arquivos">${l.arquivos.length} arquivo(s)</div></td>
        </tr>`
      )
      .join("");

    $("resumo").innerHTML = `
      <div class="resumo-cab">
        <h3><svg class="ic"><use href="#i-doc"/></svg>Baixado do SIGEF — OB <span class="mono">${esc(r.ob)}</span></h3>
        <span class="nota">${ces.length} CE(s) distinta(s) · OB: ${r.obs.length} pág. · ${n} PP(s)${docs.length < DOCUMENTOS.length ? ` · anexando só ${esc(descreverDocs(docs))}` : ""}</span>
      </div>
      <table>
        <thead><tr><th>#</th><th>PP</th><th>CE</th><th style="text-align:right">Valor</th><th>Situação</th></tr></thead>
        <tbody>${linhas}</tbody>
      </table>`;
    $("resumo").hidden = false;
  }

  // ------------------------------------------------ Eventos do Python

  const tratar = {
    log: (e) => {
      registrar(e.texto);
      interpretar(e.texto);
      if (!$("tela-login").hidden && e.texto.trim()) $("login-status").textContent = e.texto.trim();
    },

    conectando: () => {
      $("login-carregando").hidden = false;
      $("login-carregando").classList.remove("falha");
      $("login-pronto").hidden = true;
    },

    conectado: () => {
      $("login-carregando").hidden = true;
      $("login-pronto").hidden = false;
    },

    etapa: (e) => {
      faseAtual = e.etapa;
      if (e.etapa === "sigef") {
        fase("sigef", "ativa", "Pesquisando a OB");
        barra(4);
      } else if (e.etapa === "sei") {
        fase("sigef", "feita", "Concluído");
        fase("sei", "ativa", "Abrindo o processo");
        barra(48);
      }
    },

    resumo: (e) => mostrarResumo(e.resumo),

    avisos: (e) => {
      const lista = e.avisos || [];
      $("conf-avisos-lista").innerHTML = lista.map((a) => `<li>${esc(a)}</li>`).join("");
      $("conf-avisos").hidden = lista.length === 0;
    },

    pergunta: (e) => {
      if (e.modo === "conferencia") {
        // A conferência precisa da pessoa: volta para o módulo do SEI.
        if (window.lbaModulos) window.lbaModulos.trocar("sei");
        relogioParar();
        faseAtual = "conf";
        fase("sei", "feita", "Concluído");
        fase("conf", "ativa");
        barra(100);
        $("conf-processo").textContent = estado.processo;
        document.querySelectorAll(".chk-conf").forEach((c) => (c.checked = false));
        $("btn-conf-ok").disabled = true;
        mostrar("conferencia");
      } else {
        $("modal-texto").textContent = e.texto || "O programa precisa de uma resposta.";
        $("modal-resp").value = "";
        $("modal").hidden = false;
        $("modal-resp").focus();
      }
    },

    concluido: (e) => {
      relogioParar();
      const t = (e && e.tempos) || null;
      $("fim-tempo").hidden = !t;
      if (t) $("fim-tempo").textContent = `⏱ Tempo da automação: ${duracao(t.total)} (SIGEF ${duracao(t.sigef)} · SEI ${duracao(t.sei)})`;
      faseAtual = null;
      estado.concluidos += 1;
      $("contador").hidden = false;
      $("contador-num").textContent = estado.concluidos;
      $("fim-processo").textContent = estado.processo;
      mostrar("concluido");
    },

    erro: (e) => {
      relogioParar();
      const onde = faseAtual;
      faseAtual = null;
      if (e.fase === "conectar") {
        mostrar("login");
        const box = $("login-carregando");
        box.hidden = false;
        $("login-pronto").hidden = true;
        box.innerHTML = `
          <div class="erro" style="margin:0;width:100%">
            <div class="erro-cab"><svg class="ic"><use href="#i-alerta"/></svg><strong>Não consegui abrir o navegador</strong></div>
            <pre>${esc(e.mensagem)}</pre>
            <button class="btn primario" type="button" id="btn-tentar-conectar">Tentar de novo</button>
          </div>`;
        $("btn-tentar-conectar").onclick = () => location.reload();
        return;
      }
      document.querySelectorAll(".fase.ativa").forEach((f) => f.classList.replace("ativa", "falhou"));
      $("erro-msg").textContent = e.mensagem;
      $("erro-retomar").textContent =
        onde === "sei"
          ? "“Continuar de onde parou” não baixa de novo do SIGEF e pula os documentos que já foram anexados."
          : "“Continuar de onde parou” refaz o download no SIGEF; nada foi anexado no SEI ainda.";
      $("erro").hidden = false;
      $("agora").textContent = "Parado.";
      mostrar("execucao");
    },
  };

  // ---------------------------------------------------- Lote: eventos

  const ROTULO_ESTADO = { pendente: "Na fila", rodando: "Em andamento…", ok: "Concluído", pulado: "Pulado (já feito antes)", erro: "Erro" };

  function desenharAndamento() {
    const itens = estado.lote.itens;
    $("lote-itens").innerHTML = itens
      .map(
        (it, i) => `<li class="${it.estado}" id="lote-item-${i}">
          <span class="ponto"></span>
          <span class="quem">${esc(it.processo)} · OB ${esc(it.ob)}</span>
          <span class="estado">${esc(ROTULO_ESTADO[it.estado] || "")}</span>
        </li>`
      )
      .join("");
    const feitos = itens.filter((it) => ["ok", "pulado", "erro"].includes(it.estado)).length;
    $("lote-and-cont").textContent = `· ${feitos} de ${itens.length}`;
  }

  Object.assign(tratar, {
    lote_inicio: (e) => {
      estado.modo = "lote";
      estado.lote.itens = e.itens.map((it) => ({ ...it, estado: "pendente" }));
      $("lote-andamento").hidden = false;
      $("btn-parar-lote").disabled = false;
      $("btn-parar-lote").textContent = "Parar depois deste processo";
      desenharAndamento();
    },

    lote_item: (e) => {
      const it = estado.lote.itens[e.indice];
      if (!it) return;
      Object.assign(it, { estado: e.estado, mensagem: e.mensagem, avisos: e.avisos });
      if (e.estado === "rodando") {
        estado.processo = it.processo;
        estado.ob = it.ob;
        estado.tipoOb = it.tipo;
        iniciarExecucao();
        $("exec-sobre").textContent = `Lote · processo ${e.indice + 1} de ${estado.lote.itens.length}`;
        fase("conf", null);
        document.querySelector('.fase[data-fase="conf"] small').textContent = "No fim do lote";
      }
      desenharAndamento();
      const li = $(`lote-item-${e.indice}`);
      if (li && e.estado === "rodando") li.scrollIntoView({ block: "nearest" });
    },

    lote_fim: (e) => {
      relogioParar();
      faseAtual = null;
      estado.lote.resultados = e.resultados;
      estado.lote.relatorio = e.relatorio;
      mostrarFimLote();
    },
  });

  function mostrarFimLote() {
    const res = estado.lote.resultados;
    const conta = (st) => res.filter((r) => r.estado === st).length;
    const ok = conta("ok"), pulados = conta("pulado"), erros = conta("erro");
    const naoFeitos = res.length - ok - pulados - erros;

    $("lotefim-titulo").textContent = erros ? "Lote concluído, com erros" : naoFeitos ? "Lote interrompido" : "Lote concluído";
    $("lotefim-lead").textContent = erros
      ? "Os processos com erro podem ser tentados de novo: o programa continua de onde cada um parou."
      : "Confira cada processo no SEI antes de assinar.";

    const caixa = (classe, n, rotulo) => `<div class="contador-caixa ${classe}"><strong>${n}</strong><span>${rotulo}</span></div>`;
    const cronometrados = res.filter((r) => r.tempo && r.tempo.total);
    const totalLote = cronometrados.reduce((soma, r) => soma + r.tempo.total, 0);
    $("lotefim-contadores").innerHTML =
      caixa("ok", ok, "concluído(s)") +
      (cronometrados.length
        ? caixa("", duracao(totalLote), "tempo do lote") + caixa("", duracao(totalLote / cronometrados.length), "média por OB")
        : "") +
      (pulados ? caixa("pulado", pulados, "pulado(s) — já feitos antes") : "") +
      (erros ? caixa("erro", erros, "com erro") : "") +
      (naoFeitos ? caixa("pulado", naoFeitos, "não processado(s)") : "");

    const selo = (r) =>
      ({
        ok: '<span class="selo ok">✓ Concluído</span>',
        pulado: '<span class="selo pulo">Pulado</span>',
        erro: '<span class="selo erro">✗ Erro</span>',
      })[r.estado] || '<span class="selo pulo">Não processado</span>';

    $("lotefim-linhas").innerHTML = res
      .map((r) => {
        const detalhe = r.estado === "erro"
          ? (r.mensagem || "").trim().split("\n")[0]
          : r.estado === "pulado" ? r.mensagem : "";
        const avisos = (r.avisos || []).map((a) => `<div class="detalhe" style="color:var(--vermelho)">⚠ ${esc(a)}</div>`).join("");
        return `<tr class="${r.estado === "erro" ? "invalida" : ""}">
          <td>${r.linha}</td>
          <td class="mono">${esc(r.processo)}</td>
          <td class="mono">${esc(r.ob)}</td>
          <td>${selo(r)}${detalhe ? `<div class="detalhe">${esc(detalhe)}</div>` : ""}${avisos}</td>
          <td class="mono">${r.tempo && r.tempo.total ? duracao(r.tempo.total) : "—"}</td>
        </tr>`;
      })
      .join("");

    $("btn-lote-refazer").hidden = erros === 0;
    estado.concluidos += ok;
    $("contador").hidden = estado.concluidos === 0;
    $("contador-num").textContent = estado.concluidos;
    mostrar("lote-fim");
  }

  window.lba = {
    receber(eventos) {
      for (const e of eventos) (tratar[e.tipo] || (() => {}))(e);
    },
  };

  // ------------------------------------------------------ Formulário

  function marcarCampo(id, classe, html) {
    const campo = $(`campo-${id}`);
    campo.classList.remove("valido", "invalido");
    if (classe) campo.classList.add(classe);
    $(`dica-${id}`).innerHTML = html;
  }

  const DICA_PROCESSO = 'Onde anexar os documentos. Exemplo: <code>0029.001947/2026-67</code> ou <code>0029001947202667</code>';
  const DICA_OB = 'Cujos documentos serão baixados. Exemplo: <code>2026OB136475</code> ou só <code>136475</code>';

  async function conferirProcesso(final) {
    const texto = $("in-processo").value.trim();
    if (!texto) return marcarCampo("processo", final ? "invalido" : "", final ? "Informe o número do processo." : DICA_PROCESSO), null;
    const ok = api ? await api.validar_processo(texto) : formatarProcessoLocal(texto);
    if (ok) marcarCampo("processo", "valido", `✓ Entendi como <b class="mono">${esc(ok)}</b>`);
    else if (final || texto.replace(/\D/g, "").length >= 16)
      marcarCampo("processo", "invalido", "Não parece um processo do SEI. O formato é <code>0000.000000/0000-00</code> — ou os 16 números seguidos.");
    else marcarCampo("processo", "", DICA_PROCESSO);
    return ok;
  }

  function conferirOb(final) {
    const texto = $("in-ob").value.trim();
    if (/\d/.test(texto)) return marcarCampo("ob", "valido", `✓ OB <b class="mono">${esc(texto.toUpperCase())}</b>`), true;
    if (final) marcarCampo("ob", "invalido", texto ? "Isso não tem número nenhum — não parece uma OB." : "Informe o número da OB.");
    else marcarCampo("ob", "", DICA_OB);
    return false;
  }

  function formatarProcessoLocal(t) {
    const d = t.replace(/\D/g, "");
    return d.length === 16 ? `${d.slice(0, 4)}.${d.slice(4, 10)}/${d.slice(10, 14)}-${d.slice(14)}` : null;
  }

  // ---- Documentos para anexar (caixas CE / NL / PP / OB)

  const documentosEscolhidos = () =>
    [...document.querySelectorAll(".chk-doc")].filter((c) => c.checked).map((c) => c.value);

  function descreverDocs(docs) {
    const d = DOCUMENTOS.filter((x) => (docs || DOCUMENTOS).includes(x));
    return d.length <= 1 ? d.join("") : `${d.slice(0, -1).join(", ")} e ${d[d.length - 1]}`;
  }

  const DICA_DOCS = "Desmarque o que não precisa: o programa nem baixa do SIGEF o que ficar desmarcado.";

  /* Confere que há pelo menos um marcado. Devolve a lista, ou null. */
  function conferirDocumentos() {
    const docs = documentosEscolhidos();
    const ok = docs.length > 0;
    $("campo-docs").classList.toggle("invalido", !ok);
    $("dica-docs").textContent = ok ? DICA_DOCS : "Marque pelo menos um documento para anexar.";
    return ok ? docs : null;
  }

  const tipoEscolhido = () => (document.querySelector('input[name="tipo-ob"]:checked') || {}).value || "";

  function marcarTipo(tipo) {
    document.querySelectorAll('input[name="tipo-ob"]').forEach((r) => (r.checked = r.value === tipo));
  }

  async function enviarDados(ev) {
    ev.preventDefault();
    const processo = await conferirProcesso(true);
    const obOk = conferirOb(true);
    const tipo = tipoEscolhido();
    const docs = conferirDocumentos();
    $("campo-tipo").classList.toggle("invalido", !tipo);
    if (!processo) return $("in-processo").focus();
    if (!obOk) return $("in-ob").focus();
    if (!tipo) return document.querySelector('input[name="tipo-ob"]').focus();
    if (!docs) return document.querySelector(".chk-doc").focus();

    const r = api
      ? await api.processar($("in-processo").value, $("in-ob").value, tipo, docs)
      : { ok: true, processo, ob: $("in-ob").value.trim().toUpperCase(), tipo_ob: tipo, documentos: docs };
    if (!r.ok) {
      if (r.campo === "documentos") return conferirDocumentos(), document.querySelector(".chk-doc").focus();
      return r.campo === "tipo" ? document.querySelector('input[name="tipo-ob"]').focus() : $(`in-${r.campo}`).focus();
    }

    estado.processo = r.processo;
    estado.ob = r.ob;
    estado.tipoOb = r.tipo_ob;
    estado.documentos = r.documentos || docs;
    iniciarExecucao();
    if (!api) demo.processar();
  }

  // --------------------------------------------------- Lote: a lista

  const tipoLote = () => (document.querySelector('input[name="tipo-lote"]:checked') || {}).value || "regularizacao";

  function escolherAba(modo) {
    estado.modo = modo;
    $("aba-um").classList.toggle("ativa", modo === "um");
    $("aba-lote").classList.toggle("ativa", modo === "lote");
    $("aba-um").setAttribute("aria-selected", modo === "um");
    $("aba-lote").setAttribute("aria-selected", modo === "lote");
    $("form-dados").hidden = modo !== "um";
    $("form-lote").hidden = modo !== "lote";
    $("dados-lead").textContent =
      modo === "um"
        ? "A pontuação é opcional: digite só os números, se preferir, que o programa formata."
        : "Escolha uma planilha ou cole a lista. O programa confere cada linha antes de começar.";
    if (modo === "lote") setTimeout(() => $("in-lista").focus(), 60);
  }

  function desenharPrevia(r) {
    estado.lote.resposta = r;
    $("lote-erro-leitura").hidden = true;
    if (!r) return;
    if (!r.ok) {
      $("lote-previa").hidden = true;
      $("btn-lote").disabled = true;
      $("lote-erro-leitura").textContent = `Não consegui ler ${r.arquivo ? "a planilha" : "a lista"}: ${r.erro}`;
      $("lote-erro-leitura").hidden = false;
      return;
    }
    $("lote-arquivo").textContent = r.arquivo ? `✓ ${r.arquivo}` : "";
    const itens = r.itens || [];
    $("lote-previa").hidden = itens.length === 0;

    const prontos = itens.filter((i) => !i.erro).length;
    const repetir = itens.filter((i) => !i.erro && i.ja_concluida).length;
    const erros = itens.filter((i) => i.erro).length;
    $("lote-contagem").textContent =
      `${prontos} pronta(s)` + (repetir ? ` · ${repetir} já anexada(s) antes` : "") + (erros ? ` · ${erros} com problema` : "");

    $("lote-linhas").innerHTML = itens
      .map((i) => {
        const situacao = i.erro
          ? `<span class="selo erro">✗ ${esc(i.erro)}</span><div class="original">${esc(i.original)}</div>`
          : i.ja_concluida
            ? '<span class="selo ok">✓ Pronta</span><div class="detalhe">Já foi anexada antes — será anexada de novo; confira duplicidade no fim.</div>'
            : '<span class="selo ok">✓ Pronta</span>';
        return `<tr class="${i.erro ? "invalida" : ""}">
          <td>${i.linha}</td>
          <td class="mono">${esc(i.processo || "—")}</td>
          <td class="mono">${esc(i.ob || "—")}</td>
          <td>${i.erro ? "" : esc(i.tipo === "ordem_bancaria" ? "Ordem Bancária" : "Regularização")}</td>
          <td>${situacao}</td>
        </tr>`;
      })
      .join("");

    $("btn-lote").disabled = prontos === 0;
    $("btn-lote-txt").textContent = prontos ? `Processar ${prontos} OB${prontos > 1 ? "s" : ""}` : "Processar a lista";
  }

  let esperaLeitura = null;
  function lerListaDigitada() {
    clearTimeout(esperaLeitura);
    esperaLeitura = setTimeout(async () => {
      const texto = $("in-lista").value;
      $("lote-arquivo").textContent = "";
      desenharPrevia(api ? await api.ler_lote_texto(texto, tipoLote()) : demo.lerLista(texto, tipoLote()));
    }, 350);
  }

  async function iniciarLote(somenteLinhas, documentos) {
    const docs = documentos || conferirDocumentos();
    if (!docs) return document.querySelector(".chk-doc").focus();
    const r = api ? await api.processar_lote(somenteLinhas || null, docs) : { ok: true };
    if (!r.ok) return;
    estado.documentos = docs;
    estado.modo = "lote";
    estado.lote.itens = [];
    iniciarExecucao();
    $("exec-sobre").textContent = "Lote · começando";
    if (!api) demo.lote();
  }

  function iniciarExecucao() {
    $("exec-processo").textContent = estado.processo;
    $("exec-ob").textContent = estado.ob;
    $("exec-tipo").textContent = estado.tiposOb[estado.tipoOb] || "—";
    $("exec-docs").textContent = descreverDocs(estado.documentos);
    $("erro").hidden = true;
    $("resumo").hidden = true;
    $("conf-avisos").hidden = true;
    if (estado.modo !== "lote") {
      $("lote-andamento").hidden = true;
      $("exec-sobre").textContent = "Passo 4 de 5";
      document.querySelector('.fase[data-fase="conf"] small').textContent = "Com você";
    }
    fase("sigef", null, "Aguardando");
    fase("sei", null, "Aguardando");
    fase("conf", null);
    barra(0);
    $("agora").textContent = "Começando…";
    relogioLigar();
    mostrar("execucao");
  }

  function irParaDados() {
    const outra = estado.concluidos > 0;
    $("dados-sobre").textContent = outra ? `Processo nº ${estado.concluidos + 1} desta sessão` : "Passo 3 de 5";
    $("dados-titulo").textContent = outra ? "Próximo processo e Ordem Bancária" : "Informe o processo e a Ordem Bancária";
    mostrar("dados");
    escolherAba(estado.modo === "lote" ? "lote" : "um");
    conferirProcesso(false);
    conferirOb(false);
    if (estado.modo !== "lote") setTimeout(() => $("in-processo").select(), 60);
  }

  // ------------------------------------------------------------ Botões

  function ligarBotoes() {
    $("btn-comecar").onclick = () => {
      mostrar("login");
      tratar.conectando();
      document.querySelectorAll(".chk-login").forEach((c) => (c.checked = false));
      $("btn-login-ok").disabled = true;
      api ? api.conectar() : demo.conectar();
    };
    $("btn-reabrir").onclick = () => {
      tratar.conectando();
      api ? api.conectar() : demo.conectar();
    };

    const liberar = (classe, botao) =>
      document.querySelectorAll(classe).forEach((c) =>
        c.addEventListener("change", () => {
          $(botao).disabled = ![...document.querySelectorAll(classe)].every((x) => x.checked);
        })
      );
    liberar(".chk-login", "btn-login-ok");
    liberar(".chk-conf", "btn-conf-ok");

    $("btn-login-ok").onclick = () => {
      api && api.login_confirmado(); // leva a aba do SIGEF do portal para a tela da OB
      irParaDados();
    };

    $("aba-um").onclick = () => escolherAba("um");
    $("aba-lote").onclick = () => escolherAba("lote");
    $("in-lista").addEventListener("input", lerListaDigitada);
    $("btn-planilha").onclick = async () => {
      if (!api) return alert("Na janela real, isto abre a escolha da planilha.");
      const r = await api.escolher_planilha(tipoLote());
      if (r) {
        $("in-lista").value = "";
        desenharPrevia(r);
      }
    };
    document.querySelectorAll('input[name="tipo-lote"]').forEach((radio) =>
      radio.addEventListener("change", async () => {
        if (!estado.lote.resposta) return;
        desenharPrevia(api ? await api.reler_lote(tipoLote()) : demo.lerLista($("in-lista").value, tipoLote()));
      })
    );
    $("btn-lote").onclick = () => iniciarLote();
    $("btn-parar-lote").onclick = () => {
      api && api.parar_lote();
      $("btn-parar-lote").disabled = true;
      $("btn-parar-lote").textContent = "Vai parar ao fim deste processo";
    };
    $("btn-lote-refazer").onclick = () =>
      iniciarLote(estado.lote.resultados.filter((r) => r.estado === "erro").map((r) => r.linha), estado.documentos);
    $("btn-lote-relatorio").onclick = () => api && api.abrir_arquivo(estado.lote.relatorio);
    $("btn-lote-novo").onclick = () => {
      $("in-lista").value = "";
      $("lote-arquivo").textContent = "";
      $("lote-previa").hidden = true;
      $("btn-lote").disabled = true;
      estado.lote.resposta = null;
      irParaDados();
      escolherAba("lote");
    };
    $("btn-lote-sair").onclick = () => (api ? api.fechar() : alert("Na janela real, isto fecha o programa."));

    $("in-processo").addEventListener("input", () => conferirProcesso(false));
    $("in-processo").addEventListener("blur", () => $("in-processo").value.trim() && conferirProcesso(true));
    $("in-ob").addEventListener("input", () => conferirOb(false));
    $("in-processo").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); $("in-ob").focus(); $("in-ob").select(); }
    });
    $("form-dados").addEventListener("submit", enviarDados);
    document.querySelectorAll('input[name="tipo-ob"]').forEach((r) =>
      r.addEventListener("change", () => $("campo-tipo").classList.remove("invalido"))
    );
    document.querySelectorAll(".chk-doc").forEach((c) => c.addEventListener("change", conferirDocumentos));

    $("btn-conf-ok").onclick = () => {
      fase("conf", "feita");
      $("agora").textContent = "Finalizando…";
      mostrar("execucao");
      api ? api.responder("") : demo.concluir();
    };

    $("modal-ok").onclick = () => {
      $("modal").hidden = true;
      api && api.responder($("modal-resp").value);
    };
    $("modal-resp").addEventListener("keydown", (e) => e.key === "Enter" && $("modal-ok").click());

    $("btn-erro-voltar").onclick = irParaDados;
    $("btn-erro-continuar").onclick = async () => {
      if (estado.modo === "lote") {
        if (!estado.lote.itens.length) return iniciarLote(null, estado.documentos); // parou antes de começar
        const faltam = estado.lote.itens.filter((i) => i.estado !== "ok").map((i) => i.linha);
        return faltam.length ? iniciarLote(faltam, estado.documentos) : irParaDados();
      }
      if (api) {
        const r = await api.processar(estado.processo, estado.ob, estado.tipoOb, estado.documentos);
        if (!r.ok) return irParaDados();
      }
      iniciarExecucao();
      if (!api) demo.processar();
    };
    $("btn-outra").onclick = () => {
      $("in-processo").value = "";
      $("in-ob").value = "";
      irParaDados();
    };

    const abrirPasta = (caminho) => api && api.abrir_pasta(caminho || "");
    $("btn-pasta-lateral").onclick = () => abrirPasta(estado.pasta);
    $("btn-erro-pasta").onclick = () => abrirPasta(estado.pastaProcesso || estado.pasta);
    $("btn-fim-pasta").onclick = () => abrirPasta(estado.pastaProcesso);
    $("btn-sair").onclick = () => (api ? api.fechar() : alert("Na janela real, isto fecha o programa."));

    // ---- Relatório gerencial
    const relErro = (texto) => {
      $("rel-erro").textContent = texto || "";
      $("rel-erro").hidden = !texto;
    };
    $("btn-relatorio-lateral").onclick = async () => {
      const hoje = new Date();
      const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
      const op = api
        ? await api.opcoes_relatorio()
        : { de: iso(new Date(hoje.getFullYear(), hoje.getMonth(), 1)), ate: iso(hoje), minutos_manual: 20 };
      $("rel-de").value = op.de;
      $("rel-ate").value = op.ate;
      $("rel-minutos").value = op.minutos_manual;
      relErro("");
      $("modal-relatorio").hidden = false;
      $("rel-minutos").focus();
    };
    $("rel-cancelar").onclick = () => ($("modal-relatorio").hidden = true);
    $("modal-relatorio").addEventListener("keydown", (e) => e.key === "Escape" && ($("modal-relatorio").hidden = true));
    $("rel-gerar").onclick = async () => {
      if (!api) return relErro("Na janela real, isto gera o relatório e abre no navegador.");
      const botao = $("rel-gerar");
      botao.disabled = true;
      relErro("");
      try {
        const r = await api.gerar_relatorio($("rel-de").value, $("rel-ate").value, $("rel-minutos").value);
        if (r.ok) $("modal-relatorio").hidden = true;
        else relErro(r.erro);
      } finally {
        botao.disabled = false;
      }
    };
  }

  async function iniciar() {
    let inicial = { versao: "demo", pasta: "", processo: "", ob: "", tipo_ob: "regularizacao" };
    if (api) inicial = await api.estado_inicial();
    $("versao").textContent = `versão ${inicial.versao}`;
    $("btn-pasta-lateral").title = inicial.pasta || "";
    estado.pasta = inicial.pasta;
    $("in-processo").value = inicial.processo;
    $("in-ob").value = inicial.ob;
    if (inicial.tipos_ob) {
      estado.tiposOb = inicial.tipos_ob;
      document.querySelectorAll("[data-tipo-nome]").forEach((b) => (b.textContent = inicial.tipos_ob[b.dataset.tipoNome] || b.textContent));
    }
    estado.tipoOb = inicial.tipo_ob;
    marcarTipo(inicial.tipo_ob);
    document.querySelectorAll('input[name="tipo-lote"]').forEach((r) => (r.checked = r.value === inicial.tipo_ob));
    mostrar("inicio");
  }

  // ------------------------------------------- Simulação (só no ?demo)

  const demo = {
    emitir(lista, passo = 350) {
      lista.forEach((ev, i) => setTimeout(() => lba.receber([ev]), i * passo));
    },
    conectar() {
      this.emitir([
        { tipo: "log", texto: "🌐 Abrindo o navegador da automação..." },
        { tipo: "log", texto: "Conferindo as abas dos dois sistemas:" },
        { tipo: "log", texto: "   ➕ Abrindo o SIGEF..." },
        { tipo: "log", texto: "   ➕ Abrindo o SEI..." },
        { tipo: "conectado" },
      ], 500);
    },
    processar() {
      const L = (texto) => ({ tipo: "log", texto });
      this.emitir([
        { tipo: "etapa", etapa: "sigef" },
        L("🔎 OB 2026OB136475: 2 PP(s) na grade:"),
        L("\n▶️  1/2: PP 2026PP066790 (valor 12.480,00)"),
        L("   📄 Despesa Certificada: 1 JPG(s)"),
        L("   📄 Nota de Lançamento: 1 JPG(s)"),
        L("\n▶️  2/2: PP 2026PP066791 (valor 3.215,40)"),
        L("\n▶️  Por último: Ordem Bancária 2026OB136475"),
        { tipo: "resumo", resumo: { documentos: estado.documentos, ob: "2026OB136475", pasta: "", ces: [{ numero: "2026CE001234", paginas: 1 }, { numero: "2026CE001235", paginas: 1 }], obs: ["OB_1.jpg"], lancamentos: [
          { pp: "2026PP066790", ce: "2026CE001234", valor: "12.480,00", ok: true, arquivos: ["a", "b", "c"] },
          { pp: "2026PP066791", ce: "2026CE001235", valor: "3.215,40", ok: true, arquivos: ["a", "b", "c"] } ] } },
        { tipo: "etapa", etapa: "sei" },
        L("\n📄 CE (1 página(s))..."),
        L("\n📄 NL 1/2 (1 página(s)) -- PP 2026PP066790..."),
        L("\n📄 NL 2/2 (1 página(s)) -- PP 2026PP066791..."),
        L("\n📄 PP 1/2 (1 página(s)) -- PP 066790..."),
        L("\n📄 PP 2/2 (1 página(s)) -- PP 066791..."),
        L("\n📄 OB (1 página(s))..."),
        { tipo: "pergunta", modo: "conferencia", texto: "" },
      ], 700);
    },
    concluir() {
      this.emitir([{ tipo: "concluido", tempos: { sigef: 83.2, sei: 131.9, total: 215.1 } }]);
    },
    // Leitura grosseira, só para ver o layout -- a de verdade é a do lote.py.
    lerLista(texto, tipo) {
      const itens = [];
      texto.split("\n").forEach((linha, n) => {
        if (!/\d/.test(linha)) return;
        const proc = (linha.match(/\d{4}\.?\d{6}\/?\d{4}-?\d{2}/) || [""])[0];
        const ob = (linha.replace(proc, "").match(/\d{4}OB\d+|\b\d{4,8}\b/i) || [""])[0];
        const t = /ordem|normal/i.test(linha) && !/regulariz/i.test(linha) ? "ordem_bancaria" : tipo;
        itens.push({ linha: n + 1, processo: proc ? formatarProcessoLocal(proc) : "", ob, tipo: t, original: linha.trim(),
          erro: !proc ? "não achei o número do processo" : !ob ? "não achei o número da OB" : "", ja_concluida: /pronto/i.test(linha) });
      });
      return { ok: true, arquivo: "", itens };
    },
    lote() {
      const itens = (estado.lote.resposta?.itens || []).filter((i) => !i.erro);
      const eventos = [{ tipo: "lote_inicio", itens }];
      const resultados = [];
      itens.forEach((it, i) => {
        const erro = i === 1;
        eventos.push(
          { tipo: "lote_item", indice: i, estado: "rodando" },
          { tipo: "etapa", etapa: "sigef" },
          { tipo: "log", texto: "\n▶️  1/1: PP 2026PP0667" + i },
          { tipo: "etapa", etapa: "sei" },
          { tipo: "log", texto: "\n📄 CE 1/1 -- 2026CE00123 (1 página(s))..." },
          { tipo: "lote_item", indice: i, estado: erro ? "erro" : "ok", mensagem: erro ? "⚠️  Não consegui colar e salvar o documento NL 1/1 depois de 3 tentativa(s)." : "", avisos: [] }
        );
        resultados.push({ ...it, tempo: { sigef: 70 + i * 9, sei: 120 + i * 13, total: 190 + i * 22 }, estado: erro ? "erro" : "ok", mensagem: erro ? "⚠️  Não consegui colar e salvar o documento NL 1/1 depois de 3 tentativa(s)." : "", avisos: i === 0 ? ["CE: ficou um documento VAZIO de uma tentativa anterior -- exclua o vazio."] : [] });
      });
      eventos.push({ tipo: "lote_fim", resultados, relatorio: "" });
      this.emitir(eventos, 450);
    },
  };

  // --------------------------------------------------------- Partida

  ligarBotoes();
  if (window.lbaModulos) {
    window.lbaModulos.ligar({
      api: () => api,
      mostrarSei: () => exibirTela(estado.telaSei || "inicio"),
      registrarEventos: (tratadores) => Object.assign(tratar, tratadores),
    });
  }
  if (window.pywebview && window.pywebview.api) {
    api = window.pywebview.api;
    iniciar();
  } else {
    window.addEventListener("pywebviewready", () => {
      api = window.pywebview.api;
      iniciar();
    });
    // Fora do programa (navegador comum): simulação.
    if (/[?&]demo\b/.test(location.search)) iniciar();
    else setTimeout(() => !api && iniciar(), 1500);
  }
})();
