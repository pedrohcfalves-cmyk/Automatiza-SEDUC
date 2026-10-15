"""
Relatório gerencial: uma página HTML com indicadores e gráficos, feita a
partir da planilha de métricas (metricas.py).

    caminho = gerar(de=date(2026, 9, 1), ate=date(2026, 9, 30), minutos_manual=20)

A página é um arquivo só (gráficos em SVG dentro dela, sem internet),
salvo em <pasta de dados>/relatorios/. Abre no navegador e sai bem na
impressão -- "Salvar como PDF" para mandar adiante.

COMO OS NÚMEROS SÃO CONTADOS

Cada linha da planilha é uma RODADA. Uma OB pode ter mais de uma rodada
(parou, "Continuar de onde parou"). O relatório junta as rodadas pela
dupla processo + OB:

  - OB concluída    alguma rodada terminou em "Concluído";
  - tempo da OB     a soma de TODAS as rodadas dela (as que falharam
                    também custaram tempo);
  - documentos      os da rodada concluída;
  - sem intervenção concluída numa rodada só, sem tentativa repetida.

Economia = OBs concluídas × tempo manual informado − tempo da automação.
"""
import html
import os
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from etapa_listar_baixar import PASTA_BASE
from metricas import ler_metricas

PASTA_RELATORIOS = os.path.join(PASTA_BASE, "relatorios")

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ------------------------------------------------------------ formatação


def _n(valor: float, casas: int = 0) -> str:
    """1234.5 -> '1.234,5' (padrão brasileiro)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _dur(segundos: float | None) -> str:
    """Duração legível: '45 s', '3 min 20 s', '12 h 05 min'."""
    if segundos is None:
        return "—"
    s = int(round(segundos))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600} h {(s % 3600) // 60:02d} min"


def _e(texto) -> str:
    return html.escape(str(texto if texto is not None else ""))


# ------------------------------------------------------------- agregação


def _agrupar(linhas: list[dict]) -> list[dict]:
    """Junta as rodadas de cada processo + OB (ver o topo do arquivo)."""
    grupos: "OrderedDict[tuple, list[dict]]" = OrderedDict()
    for linha in linhas:
        grupos.setdefault((linha["processo"], linha["ob"]), []).append(linha)

    obs = []
    for (processo, ob), rodadas in grupos.items():
        concluidas = [r for r in rodadas if r["situacao"] == "Concluído"]
        base = concluidas[-1] if concluidas else rodadas[-1]
        obs.append({
            "processo": processo,
            "ob": ob,
            "tipo_ob": base["tipo_ob"],
            "origem": base["origem"],
            "inicio": rodadas[0]["inicio"],
            "fim": rodadas[-1]["inicio"],
            "concluida": bool(concluidas),
            "rodadas": len(rodadas),
            "sem_intervencao": len(rodadas) == 1 and bool(concluidas) and base["tentativas"] <= 1,
            "tempo": sum(r["total"] or 0 for r in rodadas),
            "sigef": sum(r["sigef"] or 0 for r in rodadas),
            "sei": sum(r["sei"] or 0 for r in rodadas),
            **{k: (base[k] if concluidas else 0) for k in ("pps", "ce", "nl", "pp", "ob_doc", "documentos", "paginas")},
            "nls_pendentes": base["nls_pendentes"] if concluidas else 0,
            "ultima_mensagem": "" if concluidas else base["mensagem"],
        })
    return obs


def _periodos(de: date, ate: date, concluidas: list[dict]) -> tuple[str, list[tuple[str, int]]]:
    """Série de OBs concluídas: por dia até 62 dias, por mês acima disso."""
    if (ate - de).days <= 62:
        contagem = defaultdict(int)
        for ob in concluidas:
            contagem[ob["fim"].date()] += 1
        serie, dia = [], de
        while dia <= ate:
            serie.append((f"{dia.day:02d}/{dia.month:02d}", contagem.get(dia, 0)))
            dia += timedelta(days=1)
        return "por dia", serie
    contagem = defaultdict(int)
    for ob in concluidas:
        contagem[(ob["fim"].year, ob["fim"].month)] += 1
    serie, ano, mes = [], de.year, de.month
    while (ano, mes) <= (ate.year, ate.month):
        serie.append((f"{MESES[mes - 1]}/{str(ano)[2:]}", contagem.get((ano, mes), 0)))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return "por mês", serie


# --------------------------------------------------------------- gráficos


def _svg_colunas(serie: list[tuple[str, int]]) -> str:
    """Colunas verticais com rótulo em cima; eixo X escalonado se forem muitas."""
    if not serie or not any(v for _, v in serie):
        return '<p class="vazio">Nenhuma OB concluída no período.</p>'
    largura, altura, base_y, topo = 720, 220, 190, 24
    maximo = max(v for _, v in serie)
    passo = largura / len(serie)
    barra = max(2.0, min(34.0, passo * 0.62))
    pular = max(1, round(len(serie) / 16))
    partes = [f'<svg viewBox="0 0 {largura} {altura}" class="grafico" role="img" aria-label="OBs concluídas no período">',
              f'<line x1="0" y1="{base_y}" x2="{largura}" y2="{base_y}" class="eixo"/>']
    for i, (rotulo, valor) in enumerate(serie):
        x = i * passo + (passo - barra) / 2
        h = 0 if not valor else max(2, (base_y - topo) * valor / maximo)
        if valor:
            partes.append(f'<rect x="{x:.1f}" y="{base_y - h:.1f}" width="{barra:.1f}" height="{h:.1f}" rx="2" class="barra"><title>{_e(rotulo)}: {valor} OB(s)</title></rect>')
            if len(serie) <= 40 or valor == maximo:
                partes.append(f'<text x="{x + barra / 2:.1f}" y="{base_y - h - 6:.1f}" class="valor" text-anchor="middle">{valor}</text>')
        if i % pular == 0:
            partes.append(f'<text x="{x + barra / 2:.1f}" y="{base_y + 18}" class="rotulo" text-anchor="middle">{_e(rotulo)}</text>')
    partes.append("</svg>")
    return "".join(partes)


def _barras_horizontais(itens: list[tuple[str, float, str]], formatar=lambda v: _n(v)) -> str:
    """Barras horizontais em HTML (rótulo · barra · valor). itens: (rótulo, valor, classe)."""
    maximo = max((v for _, v, _ in itens), default=0) or 1
    linhas = []
    for rotulo, valor, classe in itens:
        pct = 100 * valor / maximo
        linhas.append(
            f'<div class="hb"><span class="hb-rot">{_e(rotulo)}</span>'
            f'<span class="hb-trilho"><span class="hb-barra {classe}" style="width:{pct:.1f}%"></span></span>'
            f'<span class="hb-val">{_e(formatar(valor))}</span></div>'
        )
    return "".join(linhas)


def _barra_empilhada(sigef: float, sei: float) -> str:
    total = (sigef + sei) or 1
    return (
        f'<div class="pilha"><span class="seg sigef" style="width:{100 * sigef / total:.1f}%" title="SIGEF {_dur(sigef)}"></span>'
        f'<span class="seg sei" style="width:{100 * sei / total:.1f}%" title="SEI {_dur(sei)}"></span></div>'
    )


# ------------------------------------------------------------------ página


def gerar(de: date, ate: date, minutos_manual: float, destino: str | None = None) -> str:
    """Monta o relatório do período [de, ate] e devolve o caminho do .html."""
    if ate < de:
        de, ate = ate, de
    linhas = [l for l in ler_metricas() if de <= l["inicio"].date() <= ate]
    obs = _agrupar(linhas)
    concluidas = [ob for ob in obs if ob["concluida"]]
    pendentes = [ob for ob in obs if not ob["concluida"]]

    qtd = len(concluidas)
    processos = sorted({ob["processo"] for ob in concluidas})
    tempo_auto = sum(ob["tempo"] for ob in concluidas)
    tempo_manual = qtd * minutos_manual * 60
    economia = tempo_manual - tempo_auto
    media = tempo_auto / qtd if qtd else None
    sem_intervencao = sum(1 for ob in concluidas if ob["sem_intervencao"])
    docs = {k: sum(ob[k] for ob in concluidas) for k in ("ce", "nl", "pp", "ob_doc", "documentos", "paginas", "pps", "nls_pendentes")}
    rodadas_erro = [l for l in linhas if l["situacao"] in ("Erro", "Interrompido")]

    # ---- indicadores
    def kpi(rotulo, valor, detalhe="", destaque=""):
        return (f'<div class="kpi {destaque}"><span class="kpi-rot">{_e(rotulo)}</span>'
                f'<strong class="kpi-val">{valor}</strong><span class="kpi-det">{detalhe}</span></div>')

    kpis = "".join([
        kpi("OBs concluídas", _n(qtd), f"{_n(len(processos))} processo(s) atendido(s)"),
        kpi("Documentos anexados", _n(docs["documentos"]), f"{_n(docs['paginas'])} página(s) · {_n(docs['pps'])} PP(s)"),
        kpi("Tempo da automação", _dur(tempo_auto) if qtd else "—", f"média de {_dur(media)} por OB" if qtd else "sem OBs no período"),
        kpi("Tempo economizado", _dur(max(economia, 0)) if qtd else "—",
            f"vs. {_n(minutos_manual, 0 if float(minutos_manual).is_integer() else 1)} min por OB à mão", "destaque"),
        kpi("Sem intervenção", f"{_n(100 * sem_intervencao / qtd, 0)}%" if qtd else "—",
            f"{_n(sem_intervencao)} de {_n(qtd)} concluídas de primeira"),
        kpi("Pendências", _n(len(pendentes) + docs["nls_pendentes"]),
            f"{_n(len(pendentes))} OB(s) sem concluir · {_n(docs['nls_pendentes'])} NL(s) à mão",
            "alerta" if pendentes or docs["nls_pendentes"] else ""),
    ])

    # ---- gráficos
    rotulo_serie, serie = _periodos(de, ate, concluidas)
    grafico_obs = _svg_colunas(serie)
    grafico_docs = _barras_horizontais([
        ("Despesa Certificada (CE)", docs["ce"], "c1"),
        ("Nota de Lançamento (NL)", docs["nl"], "c2"),
        ("Preparação de Pagamento (PP)", docs["pp"], "c3"),
        ("Ordem Bancária (OB)", docs["ob_doc"], "c4"),
    ])
    grafico_economia = _barras_horizontais(
        [("Feito à mão (estimado)", tempo_manual, "manual"), ("Com a automação", tempo_auto, "auto")],
        formatar=_dur,
    )

    etapas = []
    for rotulo, grupo in (("Todas", concluidas),
                          ("OB avulsa", [o for o in concluidas if o["origem"] == "avulsa"]),
                          ("Em lote", [o for o in concluidas if o["origem"] == "lote"])):
        if not grupo:
            continue
        s = sum(o["sigef"] for o in grupo) / len(grupo)
        e = sum(o["sei"] for o in grupo) / len(grupo)
        etapas.append(
            f'<div class="etapa-linha"><span class="hb-rot">{rotulo} <small>({len(grupo)})</small></span>'
            f'{_barra_empilhada(s, e)}<span class="hb-val">{_dur(s + e)}</span></div>'
            f'<div class="etapa-det">SIGEF {_dur(s)} · SEI {_dur(e)}</div>'
        )
    grafico_etapas = "".join(etapas) or '<p class="vazio">Sem dados.</p>'

    # ---- tabela por processo
    por_processo: dict[str, dict] = {}
    for ob in concluidas:
        p = por_processo.setdefault(ob["processo"], {"obs": 0, "documentos": 0, "paginas": 0, "tempo": 0.0, "ultima": ob["fim"]})
        p["obs"] += 1
        p["documentos"] += ob["documentos"]
        p["paginas"] += ob["paginas"]
        p["tempo"] += ob["tempo"]
        p["ultima"] = max(p["ultima"], ob["fim"])
    linhas_processo = "".join(
        f'<tr><td class="mono">{_e(proc)}</td><td class="num">{_n(p["obs"])}</td><td class="num">{_n(p["documentos"])}</td>'
        f'<td class="num">{_n(p["paginas"])}</td><td class="num">{_dur(p["tempo"])}</td><td class="num">{p["ultima"]:%d/%m/%Y}</td></tr>'
        for proc, p in sorted(por_processo.items(), key=lambda kv: (-kv[1]["obs"], kv[0]))
    ) or '<tr><td colspan="6" class="vazio">Nenhum processo no período.</td></tr>'

    # ---- ocorrências
    ocorrencias = []
    for ob in pendentes:
        ocorrencias.append(f'<tr><td class="mono">{_e(ob["processo"])}</td><td class="mono">{_e(ob["ob"])}</td>'
                           f'<td><span class="selo erro">Não concluída</span></td><td>{_e(ob["ultima_mensagem"][:160])}</td></tr>')
    for ob in concluidas:
        if ob["nls_pendentes"]:
            ocorrencias.append(f'<tr><td class="mono">{_e(ob["processo"])}</td><td class="mono">{_e(ob["ob"])}</td>'
                               f'<td><span class="selo aviso">NL à mão</span></td><td>{ob["nls_pendentes"]} NL(s) deram erro no SIGEF e tiveram que ser incluídas à mão.</td></tr>')
    tabela_ocorrencias = (
        '<table><thead><tr><th>Processo</th><th>OB</th><th>Situação</th><th>Detalhe</th></tr></thead><tbody>'
        + "".join(ocorrencias) + "</tbody></table>"
        if ocorrencias else '<p class="vazio">Nenhuma pendência no período.</p>'
    )

    # ---- detalhe
    linhas_detalhe = "".join(
        f'<tr><td class="num">{ob["fim"]:%d/%m/%Y %H:%M}</td><td class="mono">{_e(ob["processo"])}</td><td class="mono">{_e(ob["ob"])}</td>'
        f'<td>{_e(ob["tipo_ob"])}</td><td>{"Lote" if ob["origem"] == "lote" else "Avulsa"}</td>'
        f'<td>{"<span class=\'selo ok\'>Concluída</span>" if ob["concluida"] else "<span class=\'selo erro\'>Não concluída</span>"}</td>'
        f'<td class="num">{_n(ob["pps"])}</td><td class="num">{_n(ob["documentos"])}</td><td class="num">{_n(ob["paginas"])}</td>'
        f'<td class="num">{ob["rodadas"]}</td><td class="num">{_dur(ob["tempo"])}</td></tr>'
        for ob in sorted(obs, key=lambda o: o["fim"], reverse=True)
    ) or '<tr><td colspan="11" class="vazio">Nenhuma OB no período.</td></tr>'

    periodo = f"{de:%d/%m/%Y} a {ate:%d/%m/%Y}"
    agora = datetime.now()
    pagina = MODELO.format(
        periodo=periodo,
        gerado=f"{agora:%d/%m/%Y às %H:%M}",
        kpis=kpis,
        rotulo_serie=rotulo_serie,
        grafico_obs=grafico_obs,
        grafico_docs=grafico_docs,
        grafico_etapas=grafico_etapas,
        grafico_economia=grafico_economia,
        economia_texto=(
            f"{_n(qtd)} OB(s) × {_n(minutos_manual, 0 if float(minutos_manual).is_integer() else 1)} min = "
            f"{_dur(tempo_manual)} estimados à mão, contra {_dur(tempo_auto)} da automação."
            if qtd else "Sem OBs concluídas no período."
        ),
        linhas_processo=linhas_processo,
        tabela_ocorrencias=tabela_ocorrencias,
        qtd_rodadas_erro=len(rodadas_erro),
        linhas_detalhe=linhas_detalhe,
        minutos_manual=_n(minutos_manual, 0 if float(minutos_manual).is_integer() else 1),
    )

    os.makedirs(PASTA_RELATORIOS, exist_ok=True)
    caminho = destino or os.path.join(
        PASTA_RELATORIOS, f"relatorio_gerencial_{de:%Y-%m-%d}_a_{ate:%Y-%m-%d}.html"
    )
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(pagina)
    return caminho


MODELO = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório gerencial</title>
<style>
:root {{
  --fundo: #F4F6F9; --papel: #FFFFFF; --texto: #14202E; --texto-2: #4F5D6E; --texto-3: #7A8797;
  --linha: #E1E6ED; --azul: #1664D9; --azul-claro: #DCE8FB; --verde: #16875A; --verde-claro: #DDF3E9;
  --vermelho: #C0392B; --vermelho-claro: #FBE4E1; --ambar: #A86400; --ambar-claro: #FCEFD6;
  --c1: #1664D9; --c2: #0F8B8D; --c3: #7B4FD6; --c4: #D9661F; --cinza: #B7C0CC;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--fundo); color: var(--texto); font: 14px/1.5 "Segoe UI", system-ui, sans-serif; }}
.folha {{ max-width: 1040px; margin: 0 auto; padding: 32px 24px 48px; }}
header.topo {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap;
  border-bottom: 2px solid var(--texto); padding-bottom: 14px; margin-bottom: 24px; }}
.sobre {{ margin: 0 0 4px; color: var(--texto-3); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; font-weight: 600; }}
h1 {{ margin: 0; font-size: 26px; line-height: 1.2; }}
.periodo {{ text-align: right; color: var(--texto-2); font-size: 13px; }}
.periodo strong {{ display: block; color: var(--texto); font-size: 16px; }}
h2 {{ font-size: 15px; margin: 0 0 12px; }}
h2 small {{ color: var(--texto-3); font-weight: 400; }}
.kpis {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
.kpi {{ background: var(--papel); border: 1px solid var(--linha); border-radius: 12px; padding: 14px 16px; display: grid; gap: 2px; }}
.kpi-rot {{ color: var(--texto-2); font-size: 12.5px; font-weight: 600; }}
.kpi-val {{ font-size: 28px; line-height: 1.15; font-variant-numeric: tabular-nums; letter-spacing: -.01em; }}
.kpi-det {{ color: var(--texto-3); font-size: 12.5px; }}
.kpi.destaque {{ background: var(--verde-claro); border-color: color-mix(in srgb, var(--verde) 30%, transparent); }}
.kpi.destaque .kpi-val {{ color: var(--verde); }}
.kpi.alerta {{ background: var(--ambar-claro); border-color: color-mix(in srgb, var(--ambar) 30%, transparent); }}
.kpi.alerta .kpi-val {{ color: var(--ambar); }}
.grade {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }}
.cartao {{ background: var(--papel); border: 1px solid var(--linha); border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; break-inside: avoid; }}
.grade .cartao {{ margin-bottom: 0; }}
.grafico {{ width: 100%; height: auto; display: block; }}
.grafico .eixo {{ stroke: var(--linha); stroke-width: 1; }}
.grafico .barra {{ fill: var(--azul); }}
.grafico .valor {{ fill: var(--texto-2); font-size: 11px; font-weight: 600; }}
.grafico .rotulo {{ fill: var(--texto-3); font-size: 10.5px; }}
.hb {{ display: grid; grid-template-columns: 190px 1fr 90px; align-items: center; gap: 10px; margin: 8px 0; }}
.hb-rot {{ color: var(--texto-2); font-size: 13px; }}
.hb-rot small {{ color: var(--texto-3); }}
.hb-trilho {{ background: var(--fundo); border-radius: 4px; height: 14px; overflow: hidden; }}
.hb-barra {{ display: block; height: 100%; border-radius: 4px; min-width: 2px; }}
.hb-barra.c1 {{ background: var(--c1); }} .hb-barra.c2 {{ background: var(--c2); }}
.hb-barra.c3 {{ background: var(--c3); }} .hb-barra.c4 {{ background: var(--c4); }}
.hb-barra.manual {{ background: var(--cinza); }} .hb-barra.auto {{ background: var(--verde); }}
.hb-val {{ text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; font-size: 13px; }}
.etapa-linha {{ display: grid; grid-template-columns: 190px 1fr 90px; align-items: center; gap: 10px; margin-top: 10px; }}
.etapa-det {{ margin-left: 200px; color: var(--texto-3); font-size: 12px; }}
.pilha {{ display: flex; height: 14px; border-radius: 4px; overflow: hidden; background: var(--fundo); }}
.seg.sigef {{ background: var(--c1); }} .seg.sei {{ background: var(--c2); }}
.legenda {{ display: flex; gap: 16px; color: var(--texto-3); font-size: 12px; margin-top: 10px; }}
.legenda i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }}
.nota {{ color: var(--texto-3); font-size: 12.5px; margin: 10px 0 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; color: var(--texto-2); font-weight: 600; font-size: 12px; border-bottom: 1px solid var(--linha); padding: 8px 8px; white-space: nowrap; }}
td {{ border-bottom: 1px solid var(--linha); padding: 7px 8px; vertical-align: top; }}
tbody tr:last-child td {{ border-bottom: 0; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
th.num {{ text-align: right; }}
.mono {{ font-family: Consolas, "Cascadia Mono", monospace; font-size: 12.5px; white-space: nowrap; }}
.rolagem {{ overflow-x: auto; }}
.selo {{ display: inline-block; font-size: 11.5px; font-weight: 600; border-radius: 999px; padding: 1px 8px; white-space: nowrap; }}
.selo.ok {{ background: var(--verde-claro); color: var(--verde); }}
.selo.erro {{ background: var(--vermelho-claro); color: var(--vermelho); }}
.selo.aviso {{ background: var(--ambar-claro); color: var(--ambar); }}
.vazio {{ color: var(--texto-3); text-align: center; padding: 18px 0; margin: 0; }}
footer {{ color: var(--texto-3); font-size: 12px; margin-top: 20px; border-top: 1px solid var(--linha); padding-top: 12px; }}
.imprimir {{ position: fixed; right: 20px; bottom: 20px; background: var(--azul); color: #fff; border: 0; border-radius: 10px;
  padding: 10px 16px; font: 600 14px "Segoe UI", system-ui, sans-serif; cursor: pointer; box-shadow: 0 6px 20px rgba(22,100,217,.35); }}
@media (max-width: 760px) {{
  .kpis, .grade {{ grid-template-columns: 1fr; }}
  .hb, .etapa-linha {{ grid-template-columns: 120px 1fr 80px; }}
  .etapa-det {{ margin-left: 130px; }}
  .periodo {{ text-align: left; }}
}}
@media print {{
  @page {{ size: A4; margin: 14mm; }}
  body {{ background: #fff; font-size: 12px; }}
  .folha {{ padding: 0; max-width: none; }}
  .imprimir {{ display: none; }}
  .kpi, .cartao {{ border-color: #CCD3DC; }}
  * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .quebra {{ break-before: page; }}
}}
</style>
</head>
<body>
<div class="folha">
  <header class="topo">
    <div>
      <p class="sobre">Automação SIGEF → SEI</p>
      <h1>Relatório gerencial</h1>
    </div>
    <div class="periodo">Período<strong>{periodo}</strong>Gerado em {gerado}</div>
  </header>

  <section class="kpis">{kpis}</section>

  <section class="cartao">
    <h2>OBs concluídas <small>{rotulo_serie}</small></h2>
    {grafico_obs}
  </section>

  <div class="grade">
    <section class="cartao">
      <h2>Documentos anexados no SEI <small>por tipo</small></h2>
      {grafico_docs}
    </section>
    <section class="cartao">
      <h2>Tempo manual × automação</h2>
      {grafico_economia}
      <p class="nota">{economia_texto}</p>
    </section>
  </div>

  <section class="cartao">
    <h2>Tempo médio por OB <small>por etapa</small></h2>
    {grafico_etapas}
    <div class="legenda"><span><i style="background:var(--c1)"></i>Baixar do SIGEF</span><span><i style="background:var(--c2)"></i>Anexar no SEI</span></div>
  </section>

  <section class="cartao quebra">
    <h2>Por processo</h2>
    <div class="rolagem"><table>
      <thead><tr><th>Processo</th><th class="num">OBs</th><th class="num">Documentos</th><th class="num">Páginas</th><th class="num">Tempo</th><th class="num">Última OB</th></tr></thead>
      <tbody>{linhas_processo}</tbody>
    </table></div>
  </section>

  <section class="cartao">
    <h2>Pendências e ocorrências <small>{qtd_rodadas_erro} rodada(s) com erro no período</small></h2>
    <div class="rolagem">{tabela_ocorrencias}</div>
  </section>

  <section class="cartao">
    <h2>Todas as OBs do período</h2>
    <div class="rolagem"><table>
      <thead><tr><th>Data</th><th>Processo</th><th>OB</th><th>Tipo</th><th>Origem</th><th>Situação</th><th class="num">PPs</th><th class="num">Docs</th><th class="num">Págs</th><th class="num">Rodadas</th><th class="num">Tempo</th></tr></thead>
      <tbody>{linhas_detalhe}</tbody>
    </table></div>
  </section>

  <footer>
    Como ler: o tempo é só o da automação (a conferência feita pela pessoa não entra). Uma OB que parou e foi
    retomada conta uma vez, com o tempo de todas as rodadas somado. Tempo economizado = OBs concluídas × {minutos_manual} min
    (tempo informado para fazer uma OB à mão) − tempo da automação. Fonte: metricas/metricas.csv.
  </footer>
</div>
<button class="imprimir" onclick="window.print()">Imprimir / salvar PDF</button>
</body>
</html>
"""
