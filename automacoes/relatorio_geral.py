"""
A página do relatório geral (os números vêm de automacoes/painel.py).

    html = pagina(painel.resumir(de, ate, minutos))

Um arquivo só (gráficos em SVG/HTML dentro dele, sem internet), que abre no
navegador, segue o claro/escuro do Windows e sai bem na impressão ("Salvar como
PDF"). Junta o que antes eram vários relatórios: o Painel de resultados, o Relatório
das OBs, o das NEs, as Estatísticas e o Relatório do mês do Gerar pagamento (Anexar
Documentos) e a aba Automação do Desempenho do DARE.

Acessível: títulos em ordem, sumário com atalhos, "pular para o conteúdo", tabelas
com cabeçalho, gráficos com texto alternativo e a mesma informação numa tabela,
cor nunca sozinha (sempre com rótulo), foco visível e sem animação.
"""
import html
from collections import Counter
from datetime import datetime

from automacoes.painel import AUTOMACOES, ITEM, MESES, NOMES, Resumo, _anexar_estatisticas, _numero

# Uma cor por automação, sempre na mesma ordem (paleta validada para daltonismo nos dois temas).
CORES = {"OB": 1, "NE": 2, "DARE": 3, "PAG": 4, "CAD": 5}
ANCORAS = {"OB": "ob", "NE": "ne", "DARE": "dare", "PAG": "pagamento", "CAD": "cadastro"}
SOBRE = {
    "OB": "Baixa CE, NL, PP e OB do SIGEF a partir da Ordem Bancária e anexa no SEI.",
    "NE": "Imprime a Nota de Empenho no SIGEF e anexa no SEI.",
    "DARE": "Gera o DARE avulso, salva o PDF e anexa no SEI.",
    "PAG": "Regularização (Anexar Documentos): faz CE, NL, PP e OB no SIGEF e anexa no SEI.",
    "CAD": "Cadastra o credor e a conta bancária no SIGEF.",
}


# ============================================================ formatação


def _e(texto) -> str:
    return html.escape(str(texto if texto is not None else ""))


def _n(valor: float, casas: int = 0) -> str:
    """1234.5 -> '1.234,5' (padrão brasileiro)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _dur(segundos: float | None) -> str:
    """Duração legível, com sinal: '45 s', '12 min', '3 h 05 min', '−4 min'."""
    if segundos is None:
        return "—"
    sinal = "−" if segundos < 0 else ""
    s = int(round(abs(segundos)))
    if s < 60:
        return f"{sinal}{s} s"
    if s < 3600:
        return f"{sinal}{round(s / 60)} min"
    return f"{sinal}{s // 3600} h {(s % 3600) // 60:02d} min"


def _pct(parte: float, todo: float) -> str:
    return f"{_n(100 * parte / todo)}%" if todo else "—"


def _mes(chave: str) -> str:
    ano, mes = chave.split("-")
    return f"{MESES[int(mes) - 1]}/{ano}"


def _kpi(rotulo: str, valor: str, detalhe: str = "", classe: str = "") -> str:
    return (f'<div class="kpi {classe}"><span class="kpi-rot">{_e(rotulo)}</span>'
            f'<strong class="kpi-val">{valor}</strong><span class="kpi-det">{detalhe}</span></div>')


def _tabela(cabecalho, linhas, numericas=(), legenda: str = "", vazio: str = "Nada no período.") -> str:
    """Tabela com cabeçalho; `numericas` = índices das colunas alinhadas à direita. Células já escapadas."""
    if not linhas:
        return f'<p class="vazio">{_e(vazio)}</p>'

    def cls(i):
        return ' class="num"' if i in numericas else ""

    cab = "".join(f'<th scope="col"{cls(i)}>{_e(t)}</th>' for i, t in enumerate(cabecalho))
    corpo = "".join(
        "<tr>" + "".join((f'<th scope="row">{c}</th>' if i == 0 else f"<td{cls(i)}>{c}</td>") for i, c in enumerate(linha)) + "</tr>"
        for linha in linhas
    )
    leg = f'<caption class="sr">{_e(legenda)}</caption>' if legenda else ""
    rotulo = f' role="region" aria-label="{_e(legenda)}"' if legenda else ""
    return f'<div class="rolagem" tabindex="0"{rotulo}><table>{leg}<thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>'


def _barras(itens, formatar=_n, cor: str = "") -> str:
    """Barras horizontais em HTML: rótulo · barra · valor (o valor sempre escrito)."""
    maximo = max((v for _, v, _ in itens), default=0) or 1
    linhas = []
    for rotulo, valor, detalhe in itens:
        barra = f'<span class="hb-barra {cor}" style="width:{100 * valor / maximo:.1f}%"></span>'
        linhas.append(
            f'<li class="hb"><span class="hb-rot">{_e(rotulo)}</span>'
            f'<span class="hb-trilho" aria-hidden="true">{barra if valor > 0 else ""}</span>'
            f'<span class="hb-val">{_e(formatar(valor))}{f" <small>{_e(detalhe)}</small>" if detalhe else ""}</span></li>'
        )
    return f'<ul class="barras">{"".join(linhas)}</ul>'


def _divisao(partes) -> str:
    """Uma barra dividida em partes (ex.: SIGEF × SEI), com legenda escrita."""
    total = sum(v for _, v, _ in partes) or 1
    segs = "".join(f'<span class="seg {c}" style="width:{100 * v / total:.1f}%"></span>' for _, v, c in partes)
    leg = "".join(f'<li><i class="amostra {c}" aria-hidden="true"></i>{_e(r)}: <b>{_dur(v)}</b> ({_pct(v, total)})</li>'
                  for r, v, c in partes)
    return f'<div class="pilha" aria-hidden="true">{segs}</div><ul class="legenda">{leg}</ul>'


VAZIO = '<p class="vazio">{}</p>'


# ============================================================ gráfico por mês


def _coluna(x: float, y: float, w: float, h: float, r: float) -> str:
    """Retângulo de baixo para cima, com cantos redondos só em cima (r=0: reto)."""
    h = max(h, 0.5)
    if not r:
        return f"M{x:.1f},{y:.1f}h{w:.1f}v{-h:.1f}h{-w:.1f}z"
    return (f"M{x:.1f},{y:.1f}v{-(h - r):.1f}q0,{-r:.1f} {r:.1f},{-r:.1f}h{w - 2 * r:.1f}"
            f"q{r:.1f},0 {r:.1f},{r:.1f}v{h - r:.1f}z")


def _grafico_meses(r: Resumo) -> str:
    """Colunas empilhadas: horas economizadas por mês, uma cor por automação."""
    serie = [(m, {a: max(c.economia[a], 0) / 3600 for a in AUTOMACOES}) for m, c in r.por_mes.items()]
    totais = [sum(v.values()) for _, v in serie]
    if not any(totais):
        return VAZIO.format("Nenhum item concluído no período.")
    largura, altura, base_y, topo, esq = 760, 260, 220, 28, 48
    maximo = max(totais)
    passo = (largura - esq) / len(serie)
    barra = max(6.0, min(24.0, passo * 0.55))
    pular = max(1, round(len(serie) / 12))
    escala = (base_y - topo) / maximo
    partes = [f'<svg viewBox="0 0 {largura} {altura}" class="grafico" role="img" '
              f'aria-label="Horas economizadas por mês, somando as automações. Os números estão na tabela Concluídos por mês.">']
    for frac in (0.5, 1.0):  # duas linhas de grade discretas, com o valor
        y = base_y - (base_y - topo) * frac
        partes.append(f'<line x1="{esq}" y1="{y:.1f}" x2="{largura}" y2="{y:.1f}" class="grade"/>'
                      f'<text x="{esq - 8}" y="{y + 4:.1f}" class="eixo-txt" text-anchor="end">{_n(maximo * frac, 1)} h</text>')
    partes.append(f'<line x1="{esq}" y1="{base_y}" x2="{largura}" y2="{base_y}" class="eixo"/>')
    for i, ((mes, valores), total) in enumerate(zip(serie, totais)):
        x = esq + i * passo + (passo - barra) / 2
        y = base_y
        presentes = [a for a in AUTOMACOES if valores[a] * escala >= 0.5]
        for j, a in enumerate(presentes):
            h = valores[a] * escala
            gap = 2 if j else 0  # 2px de fundo entre os pedaços
            ry = min(4, h / 2) if j == len(presentes) - 1 else 0
            partes.append(
                f'<path class="s{CORES[a]}" d="{_coluna(x, y - gap, barra, h - gap, ry)}">'
                f'<title>{_e(_mes(mes))} · {_e(NOMES[a])}: {_n(valores[a], 1)} h economizadas</title></path>')
            y -= h
        if total:
            partes.append(f'<text x="{x + barra / 2:.1f}" y="{base_y - total * escala - 8:.1f}" class="valor" '
                          f'text-anchor="middle">{_n(total, 1)} h</text>')
        if i % pular == 0:
            partes.append(f'<text x="{x + barra / 2:.1f}" y="{base_y + 20}" class="eixo-txt" text-anchor="middle">{_e(_mes(mes))}</text>')
    partes.append("</svg>")
    usadas = [a for a in AUTOMACOES if any(v[a] for _, v in serie)]
    legenda = "".join(f'<li><i class="amostra s{CORES[a]}" aria-hidden="true"></i>{_e(NOMES[a])}</li>' for a in usadas)
    return "".join(partes) + f'<ul class="legenda" aria-label="Legenda">{legenda}</ul>'


# ============================================================ detalhe de cada automação


def _base(item):
    """A rodada que vale para os documentos: a última concluída (ou a última, se nenhuma)."""
    concluidas = [r for r in item.rodadas if r.concluida]
    return (concluidas or item.rodadas)[-1]


def _primeira_vez(item) -> bool:
    return item.concluido and len(item.rodadas) == 1 and _numero(_base(item).dados.get("Tentativas")) <= 1


def _media_fases(feitos, rotulo_sigef: str, unidade: str) -> str:
    if not feitos:
        return VAZIO.format(f"Sem {unidade}s concluídas.")
    sigef = sum(_numero(r.dados.get("SIGEF (s)")) for i in feitos for r in i.rodadas) / len(feitos)
    sei = sum(_numero(r.dados.get("SEI (s)")) for i in feitos for r in i.rodadas) / len(feitos)
    return _divisao([(rotulo_sigef, sigef, "s1"), ("SEI (anexar)", sei, "s3")])


def _pendencias(itens, coluna_numero: str) -> list:
    linhas = []
    for it in sorted((i for i in itens if not i.concluido), key=lambda i: i.quando, reverse=True)[:30]:
        ultima = it.rodadas[-1].dados
        linhas.append([f"{it.quando:%d/%m/%Y %H:%M}", f'<span class="mono">{_e(ultima.get("Processo", ""))}</span>',
                       f'<span class="mono">{_e(ultima.get(coluna_numero, ""))}</span>', _e(it.pessoa),
                       _e((ultima.get("Mensagem") or "sem mensagem")[:180])])
    return linhas


def _detalhe_ob(itens) -> str:
    feitos = [i for i in itens if i.concluido]
    docs = Counter()
    por_processo: dict = {}
    for it in feitos:
        d = _base(it).dados
        for col in ("CE", "NL", "PP", "OB (doc)", "Documentos", "Páginas", "PPs", "NLs pendentes"):
            docs[col] += int(_numero(d.get(col)))
        p = por_processo.setdefault(d.get("Processo", ""), [0, 0, 0, 0.0, it.quando])
        p[0] += 1
        p[1] += int(_numero(d.get("Documentos")))
        p[2] += int(_numero(d.get("Páginas")))
        p[3] += it.segundos
        p[4] = max(p[4], it.quando)
    n, primeira = len(feitos), sum(1 for i in feitos if _primeira_vez(i))
    kpis = "".join([
        _kpi("Documentos anexados", _n(docs["Documentos"]), f"{_n(docs['Páginas'])} página(s) · {_n(docs['PPs'])} PP(s)"),
        _kpi("Sem intervenção", _pct(primeira, n), f"{_n(primeira)} de {_n(n)} concluídas de primeira"),
        _kpi("NLs feitas à mão", _n(docs["NLs pendentes"]), "deram erro no SIGEF", "alerta" if docs["NLs pendentes"] else ""),
    ])
    documentos = _barras([("Despesa Certificada (CE)", docs["CE"], ""), ("Nota de Lançamento (NL)", docs["NL"], ""),
                          ("Preparação de Pagamento (PP)", docs["PP"], ""), ("Ordem Bancária (OB)", docs["OB (doc)"], "")], cor="s1")
    linhas_proc = [[f'<span class="mono">{_e(proc)}</span>', _n(p[0]), _n(p[1]), _n(p[2]), _dur(p[3]), f"{p[4]:%d/%m/%Y}"]
                   for proc, p in sorted(por_processo.items(), key=lambda kv: (-kv[1][0], kv[0]))[:15]]
    return (f'<div class="kpis">{kpis}</div><div class="grade2">'
            f'<div class="cartao"><h4>Documentos por tipo</h4>{documentos}</div>'
            f'<div class="cartao"><h4>Onde vai o tempo <small>média por OB</small></h4>{_media_fases(feitos, "SIGEF (baixar)", "OB")}</div></div>'
            '<h4>Processos com mais OBs</h4>'
            + _tabela(["Processo", "OBs", "Documentos", "Páginas", "Tempo", "Última"], linhas_proc, (1, 2, 3, 4, 5),
                      "Processos com mais OBs no período")
            + '<h4>Pendências <small>OBs que não terminaram</small></h4>'
            + _tabela(["Quando", "Processo", "OB", "Pessoa", "O que aconteceu"], _pendencias(itens, "OB"), (), "OBs não concluídas",
                      "Nenhuma pendência no período."))


def _detalhe_ne(itens) -> str:
    feitos = [i for i in itens if i.concluido]
    n, primeira = len(feitos), sum(1 for i in feitos if _primeira_vez(i))
    paginas = sum(int(_numero(_base(i).dados.get("Páginas"))) for i in feitos)
    kpis = "".join([
        _kpi("Páginas anexadas", _n(paginas), "das NEs concluídas"),
        _kpi("Sem intervenção", _pct(primeira, n), f"{_n(primeira)} de {_n(n)} concluídas de primeira"),
    ])
    return (f'<div class="kpis">{kpis}</div><div class="cartao"><h4>Onde vai o tempo <small>média por NE</small></h4>'
            f'{_media_fases(feitos, "SIGEF (imprimir)", "NE")}</div>'
            '<h4>Pendências <small>NEs que não terminaram</small></h4>'
            + _tabela(["Quando", "Processo", "NE", "Pessoa", "O que aconteceu"], _pendencias(itens, "NE"), (), "NEs não concluídas",
                      "Nenhuma pendência no período."))


def _etapas_dare(linhas: list) -> list:
    """[(coluna, rótulo)] das etapas do DARE, na ordem do motor."""
    try:
        from automacoes.dare.motor import ETAPAS

        return [(f"{chave}_s", rotulo) for chave, rotulo, _ in ETAPAS]
    except Exception:  # noqa: BLE001 - sem o Playwright: as etapas saem pelo nome da coluna
        fixas = {"total_s", "dare_s", "sei_s", "conexao_s"}
        return [(c, c[:-2]) for c in dict.fromkeys(c for d in linhas for c in d if c and c.endswith("_s") and c not in fixas)]


def _detalhe_dare(itens) -> str:
    linhas = [r.dados for i in itens for r in i.rodadas]
    ok = [d for d in linhas if d.get("status") == "SUCESSO"]

    def media(col):
        return sum(_numero(d.get(col)) for d in ok) / len(ok) if ok else 0.0

    tempos = [(rotulo, media(col), "") for col, rotulo in _etapas_dare(ok) if any(d.get(col) for d in ok)]
    gargalo = max(tempos, key=lambda t: t[1])[0] if tempos else "—"
    total = media("total_s")
    kpis = "".join([
        _kpi("Taxa de sucesso", _pct(len(ok), len(linhas)), f"{_n(len(linhas) - len(ok))} com erro",
             "alerta" if linhas and len(ok) / len(linhas) < 0.9 else ""),
        _kpi("Lançamentos por hora", _n(3600 / total) if total else "—", f"média de {_dur(total)} cada" if total else ""),
        _kpi("Etapa mais demorada", _e(gargalo), "o gargalo"),
    ])
    etapas = _barras(tempos, formatar=_dur, cor="s3") if tempos else VAZIO.format("Sem medições das etapas.")
    fases = (_divisao([("DARE (gerar e salvar o PDF)", media("dare_s"), "s1"), ("SEI (anexar)", media("sei_s"), "s3")])
             if media("dare_s") or media("sei_s") else VAZIO.format("Sem medições das fases."))
    return (f'<div class="kpis">{kpis}</div><div class="grade2">'
            f'<div class="cartao"><h4>Tempo médio por etapa <small>lançamentos concluídos</small></h4>{etapas}</div>'
            f'<div class="cartao"><h4>Onde vai o tempo <small>média por lançamento</small></h4>{fases}</div></div>')


def _detalhe_pag(itens) -> str:
    contas, metricas = _anexar_estatisticas()
    execucoes = [r.dados for i in itens for r in i.rodadas]
    conta = contas.calcular_economia(execucoes, metricas.ler_estimativas())
    t = conta["total"]
    novos = Counter()
    for e in execucoes:
        for k in ("ce", "nl", "pp", "ob"):
            novos[k] += int(_numero((e.get("novos") or {}).get(k)))
    humano = sum(_numero(e.get("humano_s")) for e in execucoes)
    duracao = sum(_numero(e.get("duracao_s")) for e in execucoes)
    kpis = "".join([
        _kpi("Documentos feitos no SIGEF", _n(sum(novos.values())),
             f"CE {_n(novos['ce'])} · NL {_n(novos['nl'])} · PP {_n(novos['pp'])} · OB {_n(novos['ob'])}"),
        _kpi("Máquina sozinha", _dur(duracao - humano), f"{_pct(duracao - humano, duracao)} do tempo"),
        _kpi("Esperando a pessoa", _dur(humano), "respostas e conferências", "alerta" if duracao and humano / duracao > 0.5 else ""),
    ])
    por_tipo = [[f"<b>{_e(str(l['nome']).split(' — ')[0])}</b> <small>{_e(l['item'])}</small>", _n(l["itens"]), _dur(l["tempo"]),
                 _dur(l["mao"]), _dur(l["economizado"]), f"{_n(l['minutos'], 1)} min"]
                for l in conta["linhas"] if l["itens"] or l["tempo"]]
    por_etapa = [[_e(d["nome"]), _n(d["execucoes"]), _n(d["itens"]), _dur(d["tempo"]),
                  _dur(d["tempo"] / d["itens"]) if d["itens"] else "—", _dur(d["humano"])]
                 for d in contas.detalhe_do_mes(execucoes) if d["execucoes"]]
    processos = []
    for e in sorted(execucoes, key=lambda e: str(e.get("inicio")), reverse=True)[:30]:
        data = contas.data_de(e)
        texto, tom = contas.SITUACAO.get(e.get("situacao"), contas.SITUACAO["pendente"])
        erros = "; ".join(x.get("titulo") or "" for x in e.get("erros") or [])
        processos.append([f"{data:%d/%m/%Y %H:%M}" if data else "—", f'<span class="mono">{_e(e.get("processo") or "—")}</span>',
                          _e(e.get("lancamentos", "—")), _dur(_numero(e.get("duracao_s"))),
                          f'<span class="selo {_e(tom)}">{_e(texto)}</span>' + (f" <small>{_e(erros[:140])}</small>" if erros else "")])
    comparacao = _barras([("Feito à mão (estimado)", t["mao"], ""), ("Com a automação", t["tempo"], "")], formatar=_dur, cor="s4")
    return (f'<div class="kpis">{kpis}</div><div class="cartao"><h4>À mão × com a automação</h4>{comparacao}</div>'
            "<h4>Economia por tipo de item</h4>"
            + _tabela(["Tipo", "Itens", "Com a automação", "À mão (estimado)", "Economizado", "À mão, cada"], por_tipo,
                      (1, 2, 3, 4, 5), "Economia por tipo de item do Gerar pagamento")
            + "<h4>Tempo de cada etapa</h4>"
            + _tabela(["Etapa", "Execuções", "Itens", "Tempo total", "Média por item", "Esperando a pessoa"], por_etapa,
                      (1, 2, 3, 4, 5), "Tempo de cada etapa do Gerar pagamento")
            + "<h4>Processos <small>os 30 mais recentes</small></h4>"
            + _tabela(["Quando", "Processo", "Lançamentos", "Tempo", "Situação"], processos, (2, 3), "Processos do Gerar pagamento"))


def _detalhe_cad(itens) -> str:
    dados = [r.dados for i in itens for r in i.rodadas]
    status = Counter(d.get("status", "ERRO") for d in dados)
    caminhos = Counter(d.get("caminho") for d in dados if d.get("status") == "OK")
    espera = sum(_numero(d.get("espera")) for d in dados)
    motivos = Counter(d.get("motivo") or "sem detalhe" for d in dados if d.get("status") == "ERRO").most_common(10)
    kpis = "".join([
        _kpi("Taxa de sucesso", _pct(status["OK"] + status["JA"], len(dados) - status["PULADO"]), "cadastrados ou que já tinham cadastro"),
        _kpi("Já tinham cadastro", _n(status["JA"]), "não contam na economia"),
        _kpi("Conferindo na tela", _dur(espera), "pessoas conferindo e corrigindo"),
    ])
    resultado = _barras([("Cadastrado", status["OK"], ""), ("Já tinha cadastro", status["JA"], ""),
                         ("Erro", status["ERRO"], ""), ("Pulado", status["PULADO"], "")], cor="s5")
    tipo = _barras([("Credor novo + conta", caminhos.get("novo", 0), ""), ("Só a conta", caminhos.get("existente", 0), "")], cor="s5")
    return (f'<div class="kpis">{kpis}</div><div class="grade2">'
            f'<div class="cartao"><h4>Resultado de cada credor</h4>{resultado}</div>'
            f'<div class="cartao"><h4>O que foi cadastrado</h4>{tipo}</div></div><h4>Erros mais comuns</h4>'
            + _tabela(["Motivo", "Vezes"], [[_e(m), _n(q)] for m, q in motivos], (1,), "Erros mais comuns do Cadastro",
                      "Nenhum erro no período."))


DETALHES = {"OB": _detalhe_ob, "NE": _detalhe_ne, "DARE": _detalhe_dare, "PAG": _detalhe_pag, "CAD": _detalhe_cad}


def _secao(a: str, r: Resumo) -> str:
    g = r.geral
    itens = [i for i in r.itens if i.automacao == a]
    cab = (f'<section class="secao" id="{ANCORAS[a]}" aria-labelledby="t-{ANCORAS[a]}">'
           f'<header class="secao-cab"><i class="marca-cor s{CORES[a]}" aria-hidden="true"></i><div>'
           f'<h2 id="t-{ANCORAS[a]}">{_e(NOMES[a])}</h2><p>{_e(SOBRE[a])}</p></div></header>')
    if not itens:
        return cab + VAZIO.format("Sem uso no período.") + "</section>"
    resumo = "".join([
        _kpi("Concluídos", _n(g.concluidos[a]), f"de {_n(g.itens[a])} {_e(ITEM[a])}(s) · {_pct(g.concluidos[a], g.itens[a])}"),
        _kpi("Tempo da automação", _dur(g.tempo[a]),
             f"média de {_dur(g.tempo[a] / g.concluidos[a])} por {_e(ITEM[a])}" if g.concluidos[a] else "sem concluídos"),
        _kpi("Tempo economizado", _dur(g.economia[a]), f"à mão seria {_dur(g.manual[a])}", "destaque" if g.economia[a] > 0 else ""),
    ])
    try:
        detalhe = DETALHES[a](itens)
    except Exception as erro:  # noqa: BLE001 - o detalhe de uma automação não derruba a página
        detalhe = VAZIO.format(f"Não consegui montar o detalhe ({_e(erro)}).")
    return cab + f'<div class="kpis">{resumo}</div>{detalhe}</section>'


# ============================================================ página


def pagina(r: Resumo) -> str:
    g = r.geral
    kpis = "".join([
        _kpi("Tempo economizado", _dur(max(g.total_economia, 0)) if g.total_concluidos else "—",
             f"à mão seria {_dur(g.total_manual)}; com a automação, {_dur(g.total_tempo)}", "destaque grande"),
        _kpi("Itens concluídos", _n(g.total_concluidos), f"de {_n(g.total_itens)} · {_pct(g.total_concluidos, g.total_itens)} de sucesso"),
        _kpi("Dias de trabalho poupados", _n(max(g.total_economia, 0) / 3600 / 8, 1) if g.total_concluidos else "—", "contando 8 h por dia"),
        _kpi("Pessoas", _n(len(r.por_pessoa)), _e(", ".join(r.por_pessoa)) or "—"),
    ])
    maior = max((max(g.economia[a], 0) for a in AUTOMACOES), default=0) or 1
    cartoes = "".join(
        f'<a class="auto-cartao" href="#{ANCORAS[a]}"><span class="auto-nome"><i class="amostra s{CORES[a]}" aria-hidden="true"></i>'
        f'{_e(NOMES[a])}</span><strong>{_dur(g.economia[a]) if g.itens[a] else "—"}</strong>'
        f'<span class="auto-det">{_n(g.concluidos[a])} {_e(ITEM[a])}(s) concluído(s) · economizado</span>'
        f'<span class="hb-trilho" aria-hidden="true"><span class="hb-barra s{CORES[a]}" '
        f'style="width:{100 * max(g.economia[a], 0) / maior:.1f}%"></span></span></a>'
        for a in AUTOMACOES
    )

    def linhas_conta(pares):
        return [[_e(rotulo)] + [_n(c.concluidos[a]) for a in AUTOMACOES] + [_dur(c.total_tempo), f"<b>{_dur(c.total_economia)}</b>"]
                for rotulo, c in pares if c.total_itens]

    def cab_conta(primeira):
        return [primeira] + [NOMES[a] for a in AUTOMACOES] + ["Tempo da automação", "Economizado"]

    numericas = tuple(range(1, len(AUTOMACOES) + 3))
    por_automacao = [[f'<i class="amostra s{CORES[a]}" aria-hidden="true"></i> {_e(NOMES[a])}', _n(g.itens[a]), _n(g.concluidos[a]),
                      _dur(g.tempo[a]), _dur(g.tempo[a] / g.concluidos[a]) if g.concluidos[a] else "—",
                      f"{_n(r.minutos[a])} min" if a in r.minutos else "estimativa própria", f"<b>{_dur(g.economia[a])}</b>"]
                     for a in AUTOMACOES]
    fontes = "".join(
        f"<li><b>{_e(f.pessoa)}</b>: " + (" · ".join(_e(p) for p in (f.pasta_sigef, f.pasta_dare, f.pasta_anexar) if p) or "—")
        + (" · Cadastro de Credores" if f.cadastro else "") + "</li>" for f in r.fontes
    ) or "<li>nenhuma pasta</li>"
    sumario = "".join(f'<li><a href="#{ANCORAS[a]}">{_e(NOMES[a])}</a></li>' for a in AUTOMACOES)
    vazio = "" if g.total_itens else '<p class="aviso" role="status">Nenhuma automação foi usada neste período. Escolha outro período na Central.</p>'
    return MODELO.format(
        css=CSS, periodo=f"{r.de:%d/%m/%Y} a {r.ate:%d/%m/%Y}", gerado=f"{datetime.now():%d/%m/%Y às %H:%M}",
        sumario=sumario, kpis=kpis, vazio=vazio, cartoes=cartoes, grafico=_grafico_meses(r),
        tabela_automacao=_tabela(["Automação", "Itens", "Concluídos", "Tempo da automação", "Média por item", "À mão (cada)", "Economizado"],
                                 por_automacao, (1, 2, 3, 4, 5, 6), "Resumo por automação"),
        tabela_mes=_tabela(cab_conta("Mês"), linhas_conta((_mes(m), c) for m, c in r.por_mes.items()), numericas,
                           "Concluídos por mês e automação", "Nenhum item no período."),
        tabela_pessoa=_tabela(cab_conta("Pessoa"), linhas_conta(r.por_pessoa.items()), numericas, "Concluídos por pessoa"),
        secoes="".join(_secao(a, r) for a in AUTOMACOES),
        min_ob=_n(r.minutos["OB"]), min_ne=_n(r.minutos["NE"]), min_dare=_n(r.minutos["DARE"]), fontes=fontes,
    )


CSS = """
:root{color-scheme:light;--fundo:#f4f6f9;--sup:#fff;--sup2:#f8fafc;--borda:#e2e7ee;--txt:#17202e;--txt2:#47536a;--txt3:#626e81;
--pri:#1463c8;--verde:#0f7a4f;--verde-s:#e3f5ec;--ambar:#8a5200;--ambar-s:#fff4e0;--verm:#b3261e;--verm-s:#fcebea;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--raio:12px;--sombra:0 1px 2px rgba(16,32,56,.05),0 4px 16px rgba(16,32,56,.06)}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--fundo:#0e141c;--sup:#151d28;--sup2:#111821;--borda:#2a374a;
--txt:#e7ecf3;--txt2:#b4bfcf;--txt3:#939fb2;--pri:#6aa8f5;--verde:#4fd39a;--verde-s:#123a2a;--ambar:#f0b24e;--ambar-s:#33260f;--verm:#f58b84;--verm-s:#3a1917;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--sombra:0 1px 2px rgba(0,0,0,.3)}}
*{box-sizing:border-box}html{scroll-padding-top:64px}
body{margin:0;background:var(--fundo);color:var(--txt);font:15px/1.55 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}
a{color:var(--pri)}:focus-visible{outline:3px solid var(--pri);outline-offset:2px;border-radius:4px}
.pular{position:absolute;left:-9999px;top:8px;background:var(--pri);color:#fff;padding:8px 14px;border-radius:8px;z-index:9}.pular:focus{left:12px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.mono{font-family:"Cascadia Mono",Consolas,monospace;font-size:.92em}
.barra-topo{position:sticky;top:0;z-index:5;background:var(--sup);border-bottom:1px solid var(--borda)}
.barra-topo nav{max-width:1120px;margin:0 auto;padding:10px 24px;display:flex;gap:6px 18px;flex-wrap:wrap;align-items:center;font-size:13.5px}
.barra-topo ul{display:flex;flex-wrap:wrap;gap:4px 14px;list-style:none;margin:0;padding:0}
.barra-topo a{text-decoration:none;color:var(--txt2);font-weight:600;padding:4px 2px}.barra-topo a:hover{color:var(--pri);text-decoration:underline}
.btn{margin-left:auto;font:inherit;font-weight:600;cursor:pointer;border:1px solid var(--borda);background:var(--sup2);color:var(--txt);border-radius:9px;padding:6px 14px}
.btn:hover{border-color:var(--pri)}
.folha{max-width:1120px;margin:0 auto;padding:28px 24px 56px}
.topo{display:flex;justify-content:space-between;align-items:flex-end;gap:16px 32px;flex-wrap:wrap;margin-bottom:18px}
.sobre{margin:0 0 4px;color:var(--pri);font-weight:700;font-size:12.5px;letter-spacing:.06em;text-transform:uppercase}
h1{margin:0;font-size:30px;line-height:1.2;letter-spacing:-.4px}h2{margin:0;font-size:21px;letter-spacing:-.2px}
h3{margin:0 0 4px;font-size:17px}h4{margin:22px 0 10px;font-size:15px}h4 small{font-weight:400;color:var(--txt3);margin-left:6px}
.periodo{text-align:right;color:var(--txt2);font-size:13.5px;margin:0}.periodo strong{display:block;color:var(--txt);font-size:17px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:14px 0}
.kpi{background:var(--sup);border:1px solid var(--borda);border-radius:var(--raio);padding:14px 16px;box-shadow:var(--sombra);display:grid;gap:2px;min-width:0;align-content:start}
.kpi-rot{font-size:12.5px;color:var(--txt2);font-weight:600}.kpi-val{font-size:24px;line-height:1.2;overflow-wrap:anywhere}.kpi-det{font-size:12.5px;color:var(--txt3)}
.kpi.destaque{border-color:color-mix(in srgb,var(--verde) 45%,var(--borda));background:var(--verde-s)}.kpi.destaque .kpi-val{color:var(--verde)}
.kpi.grande .kpi-val{font-size:30px}.kpi.alerta{border-color:color-mix(in srgb,var(--ambar) 50%,var(--borda));background:var(--ambar-s)}
.cartao{background:var(--sup);border:1px solid var(--borda);border-radius:var(--raio);padding:18px 20px;box-shadow:var(--sombra);margin:14px 0;min-width:0}
.cartao h4{margin-top:0}.cartao>h3+p{margin:0 0 12px;color:var(--txt3);font-size:13px}
.grade2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}.grade2 .cartao{margin:0}
.autos{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:14px 0}
.auto-cartao{display:grid;gap:4px;text-decoration:none;color:inherit;background:var(--sup);border:1px solid var(--borda);border-radius:var(--raio);padding:14px 16px;box-shadow:var(--sombra)}
.auto-cartao:hover{border-color:var(--pri)}.auto-nome{font-weight:600;font-size:13.5px;display:flex;align-items:center;gap:8px}
.auto-cartao strong{font-size:21px}.auto-det{font-size:12.5px;color:var(--txt3)}
.amostra{display:inline-block;width:12px;height:12px;border-radius:3px;flex:none;vertical-align:-1px}
.marca-cor{width:6px;align-self:stretch;border-radius:3px;flex:none}
.s1{background:var(--s1);fill:var(--s1)}.s2{background:var(--s2);fill:var(--s2)}.s3{background:var(--s3);fill:var(--s3)}
.s4{background:var(--s4);fill:var(--s4)}.s5{background:var(--s5);fill:var(--s5)}
.grafico{width:100%;height:auto;display:block}.grafico .grade{stroke:var(--borda);stroke-width:1}.grafico .eixo{stroke:var(--txt3);stroke-width:1}
.grafico .eixo-txt{fill:var(--txt3);font-size:12px}.grafico .valor{fill:var(--txt);font-size:12px;font-weight:600}.grafico path:hover{opacity:.8}
.legenda{display:flex;flex-wrap:wrap;gap:6px 18px;list-style:none;margin:10px 0 0;padding:0;font-size:13px;color:var(--txt2)}
.legenda li{display:flex;align-items:center;gap:7px}
.barras{list-style:none;margin:0;padding:0;display:grid;gap:9px}
.hb{display:grid;grid-template-columns:minmax(120px,38%) 1fr auto;gap:10px;align-items:center;font-size:13.5px}
.hb-rot{color:var(--txt2)}.hb-val{font-weight:600;font-variant-numeric:tabular-nums;text-align:right}.hb-val small{font-weight:400;color:var(--txt3)}
.hb-trilho{display:block;height:10px;background:var(--sup2);border:1px solid var(--borda);border-radius:6px;overflow:hidden}
.hb-barra{display:block;height:100%;border-radius:0 4px 4px 0;min-width:2px}
.pilha{display:flex;height:16px;gap:2px;border-radius:6px;overflow:hidden}.pilha .seg{display:block;height:100%}
.rolagem{position:relative;overflow-x:auto;border:1px solid var(--borda);border-radius:10px;background:var(--sup)}
table{width:100%;border-collapse:collapse;font-size:13.5px}th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--borda);vertical-align:top}
thead th{background:var(--sup2);font-size:12px;color:var(--txt2);text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
tbody th{font-weight:600}tbody tr:last-child>*{border-bottom:0}tbody tr:hover{background:var(--sup2)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}td small{color:var(--txt3)}
.vazio{color:var(--txt3);font-style:italic;margin:8px 0}
.aviso{background:var(--ambar-s);border:1px solid color-mix(in srgb,var(--ambar) 45%,var(--borda));border-radius:10px;padding:12px 16px}
.secao{margin-top:44px}.secao-cab{display:flex;gap:14px;margin-bottom:6px}.secao-cab p{margin:2px 0 0;color:var(--txt2)}
.bloco{margin-top:36px}.bloco>p.sub{margin:2px 0 8px;color:var(--txt2)}
.selo{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:1px 9px;border:1px solid var(--borda)}
.selo.ok{background:var(--verde-s);color:var(--verde)}.selo.erro{background:var(--verm-s);color:var(--verm)}
.selo.pendente,.selo.interrompido{background:var(--ambar-s);color:var(--ambar)}
footer{margin-top:48px;padding-top:18px;border-top:1px solid var(--borda);color:var(--txt2);font-size:13.5px}footer ul{margin:6px 0 0;padding-left:18px;overflow-wrap:anywhere}
footer dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 14px;margin:8px 0}footer dt{font-weight:600;color:var(--txt)}footer dd{margin:0}
@media (max-width:640px){.folha{padding:20px 16px 40px}.periodo{text-align:left}.hb{grid-template-columns:1fr auto}.hb-trilho{grid-column:1/-1;order:3}
.barra-topo{position:static}.barra-topo nav{padding:8px 16px}.btn{margin-left:0}footer dl{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@media print{.barra-topo,.pular{display:none}body{background:#fff}.kpi,.cartao,.auto-cartao,.rolagem{box-shadow:none;break-inside:avoid}
.secao{break-before:page}a{color:inherit;text-decoration:none}}
@media (forced-colors:active){.hb-barra,.seg,.amostra,.marca-cor{forced-color-adjust:none}}
"""

MODELO = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório geral das automações · {periodo}</title><style>{css}</style></head>
<body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
<header class="barra-topo"><nav aria-label="Seções do relatório">
<ul><li><a href="#resumo">Resumo</a></li><li><a href="#mes">Por mês</a></li><li><a href="#pessoas">Por pessoa</a></li>{sumario}<li><a href="#metodo">Como contamos</a></li></ul>
<button class="btn" type="button" onclick="window.print()">Imprimir ou salvar PDF</button></nav></header>
<main class="folha" id="conteudo">
<div class="topo"><div><p class="sobre">Central de Automações · SEDUC</p><h1>Relatório geral das automações</h1></div>
<p class="periodo">Período<strong>{periodo}</strong>Gerado em {gerado}</p></div>
{vazio}
<section id="resumo" aria-labelledby="t-resumo"><h2 id="t-resumo" class="sr">Resumo</h2>
<div class="kpis">{kpis}</div>
<div class="autos">{cartoes}</div>
<div class="cartao"><h3>Por automação</h3><p>Clique num cartão acima para ir ao detalhe da automação.</p>{tabela_automacao}</div>
</section>
<section class="bloco" id="mes" aria-labelledby="t-mes"><h2 id="t-mes">Tempo economizado por mês</h2>
<p class="sub">Horas poupadas em cada mês, somando as automações (passe o mouse numa coluna para ver cada parte).</p>
<div class="cartao">{grafico}</div>
<h4>Concluídos por mês</h4>{tabela_mes}</section>
<section class="bloco" id="pessoas" aria-labelledby="t-pessoas"><h2 id="t-pessoas">Por pessoa</h2>
<p class="sub">Quem mais economizou aparece primeiro.</p>{tabela_pessoa}</section>
{secoes}
<footer id="metodo"><h2>Como contamos</h2>
<dl>
<dt>Item</dt><dd>Uma OB ou NE (processo + número), um lançamento do DARE, um processo do Gerar pagamento ou um credor do Cadastro. Um item retomado ("Continuar de onde parou") conta uma vez só.</dd>
<dt>Concluído</dt><dd>Alguma rodada do item terminou bem. No Gerar pagamento, "Faltou algo" também conta (os documentos foram feitos).</dd>
<dt>Tempo da automação</dt><dd>A soma de todas as rodadas, inclusive as que falharam.</dd>
<dt>À mão</dt><dd>OB {min_ob} min, NE {min_ne} min e DARE {min_dare} min por item (escolhidos ao gerar o relatório). O Gerar pagamento usa as estimativas por CE, NL, PP, OB, conferência e anexação da tela dele; o Cadastro, o tempo cronometrado à mão (ou a estimativa dele).</dd>
<dt>Economizado</dt><dd>Concluídos × tempo à mão − tempo da automação. Pode ficar negativo quando há muitas falhas.</dd>
</dl>
<p>Dados lidos de:</p><ul>{fontes}</ul>
</footer></main></body></html>
"""
