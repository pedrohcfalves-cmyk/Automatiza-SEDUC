"""
Relatório gerencial das NEs: uma página HTML com os indicadores do
período, feita a partir de metricas/metricas_ne.csv (metricas.py, neste pacote).

    caminho = gerar(de=date(2026, 10, 1), ate=date(2026, 10, 31), minutos_manual=15)

Um arquivo só (gráfico em SVG dentro dele, sem internet), salvo em
<pasta de dados>/relatorios/. Abre no navegador e sai bem na impressão.

COMO OS NÚMEROS SÃO CONTADOS

Cada linha da planilha é uma RODADA. Uma NE pode ter mais de uma (parou,
foi retomada). As rodadas são juntadas pela dupla processo + NE:

  - NE concluída    alguma rodada terminou em "Concluído";
  - tempo da NE     a soma de TODAS as rodadas (as que falharam também custaram tempo);
  - sem intervenção concluída numa rodada só, sem tentativa repetida.

Economia = NEs concluídas × tempo manual informado − tempo da automação.
"""
import os
from collections import OrderedDict
from datetime import date, datetime

from automacoes.sigef_sei.etapa_listar_baixar import PASTA_BASE
from automacoes.sigef_sei.relatorio_gerencial import _dur, _e, _n, _periodos

from .metricas import ler_metricas_ne

PASTA_RELATORIOS = os.path.join(PASTA_BASE, "relatorios")


def _agrupar(linhas: list[dict]) -> list[dict]:
    """Junta as rodadas de cada processo + NE (ver o topo do arquivo)."""
    grupos: "OrderedDict[tuple, list[dict]]" = OrderedDict()
    for linha in linhas:
        grupos.setdefault((linha["processo"], linha["ne"]), []).append(linha)

    nes = []
    for (processo, ne), rodadas in grupos.items():
        concluidas = [r for r in rodadas if r["situacao"] == "Concluído"]
        base = concluidas[-1] if concluidas else rodadas[-1]
        nes.append({
            "processo": processo,
            "ne": ne,
            "origem": base["origem"],
            "inicio": rodadas[0]["inicio"],
            "fim": rodadas[-1]["inicio"],
            "concluida": bool(concluidas),
            "rodadas": len(rodadas),
            "sem_intervencao": len(rodadas) == 1 and bool(concluidas) and base["tentativas"] <= 1,
            "tempo": sum(r["total"] or 0 for r in rodadas),
            "sigef": sum(r["sigef"] or 0 for r in rodadas),
            "sei": sum(r["sei"] or 0 for r in rodadas),
            "paginas": base["paginas"] if concluidas else 0,
            "ultima_mensagem": "" if concluidas else base["mensagem"],
        })
    return nes


def _svg_colunas(serie: list[tuple[str, int]]) -> str:
    """Colunas verticais com o valor em cima; o rótulo do eixo X pula se forem muitas."""
    if not serie or not any(v for _, v in serie):
        return '<p class="vazio">Nenhuma NE concluída no período.</p>'
    largura, altura, base_y, topo = 720, 220, 190, 24
    maximo = max(v for _, v in serie)
    passo = largura / len(serie)
    barra = max(2.0, min(34.0, passo * 0.62))
    pular = max(1, round(len(serie) / 16))
    partes = [f'<svg viewBox="0 0 {largura} {altura}" class="grafico" role="img" aria-label="NEs concluídas no período">',
              f'<line x1="0" y1="{base_y}" x2="{largura}" y2="{base_y}" class="eixo"/>']
    for i, (rotulo, valor) in enumerate(serie):
        x = i * passo + (passo - barra) / 2
        if valor:
            h = max(2, (base_y - topo) * valor / maximo)
            partes.append(f'<rect x="{x:.1f}" y="{base_y - h:.1f}" width="{barra:.1f}" height="{h:.1f}" rx="2" class="barra"><title>{_e(rotulo)}: {valor} NE(s)</title></rect>')
            partes.append(f'<text x="{x + barra / 2:.1f}" y="{base_y - h - 6:.1f}" class="valor" text-anchor="middle">{valor}</text>')
        if i % pular == 0:
            partes.append(f'<text x="{x + barra / 2:.1f}" y="{base_y + 18}" class="rotulo" text-anchor="middle">{_e(rotulo)}</text>')
    partes.append("</svg>")
    return "".join(partes)


CSS = """
:root { --azul:#1664D9; --texto:#1B2733; --texto-2:#46566A; --texto-3:#6B7A8D; --linha:#E1E6EC; --fundo:#F4F6F9; --papel:#fff;
        --verde:#1E8E5A; --vermelho:#C0392B; }
* { box-sizing: border-box; }
body { margin:0; background:var(--fundo); color:var(--texto); font:14px/1.45 "Segoe UI", system-ui, sans-serif; }
.folha { max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }
.topo { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:18px; }
.sobre { margin:0; color:var(--texto-3); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
h1 { margin:2px 0 0; font-size:24px; } h2 { margin:0 0 10px; font-size:15px; } h2 small { color:var(--texto-3); font-weight:400; }
.periodo { text-align:right; color:var(--texto-3); font-size:12px; } .periodo strong { display:block; color:var(--texto); font-size:14px; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:12px; }
.kpi, .cartao { background:var(--papel); border:1px solid var(--linha); border-radius:12px; padding:14px 16px; }
.cartao { margin-bottom:12px; break-inside:avoid; }
.kpi .rot { color:var(--texto-3); font-size:12px; } .kpi .val { font-size:26px; font-weight:700; margin:2px 0; } .kpi .sub { color:var(--texto-3); font-size:12px; }
.kpi.destaque .val { color:var(--verde); }
.grafico { width:100%; height:auto; display:block; } .grafico .eixo { stroke:var(--linha); }
.grafico .barra { fill:var(--azul); } .grafico .valor { fill:var(--texto-2); font-size:11px; font-weight:600; } .grafico .rotulo { fill:var(--texto-3); font-size:10.5px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:var(--texto-2); font-size:12px; border-bottom:1px solid var(--linha); padding:8px; white-space:nowrap; }
td { border-bottom:1px solid var(--linha); padding:7px 8px; vertical-align:top; } tbody tr:last-child td { border-bottom:0; }
.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; } th.num { text-align:right; }
.selo { display:inline-block; font-size:11.5px; font-weight:600; border-radius:999px; padding:1px 8px; }
.selo.ok { background:#E3F4EB; color:var(--verde); } .selo.erro { background:#FBE7E4; color:var(--vermelho); }
.vazio { color:var(--texto-3); text-align:center; padding:18px 0; margin:0; }
.rolagem { overflow-x:auto; } footer { color:var(--texto-3); font-size:12px; margin-top:20px; border-top:1px solid var(--linha); padding-top:12px; }
.imprimir { position:fixed; right:20px; bottom:20px; background:var(--azul); color:#fff; border:0; border-radius:10px; padding:10px 16px; font:600 14px "Segoe UI",system-ui,sans-serif; cursor:pointer; }
@media print { body { background:#fff; font-size:12px; } .imprimir { display:none; } * { -webkit-print-color-adjust:exact; print-color-adjust:exact; } }
"""


def _kpi(rotulo: str, valor: str, sub: str = "", classe: str = "") -> str:
    return f'<div class="kpi {classe}"><div class="rot">{_e(rotulo)}</div><div class="val">{_e(valor)}</div><div class="sub">{_e(sub)}</div></div>'


def gerar(de: date, ate: date, minutos_manual: float = 15, destino: str | None = None) -> str:
    """Gera o relatório do período [de, ate] e devolve o caminho do .html."""
    if ate < de:  # como no relatório das OBs: datas trocadas valem o mesmo período
        de, ate = ate, de
    linhas = [l for l in ler_metricas_ne() if de <= l["inicio"].date() <= ate]
    nes = _agrupar(linhas)
    concluidas = [n for n in nes if n["concluida"]]
    pendentes = [n for n in nes if not n["concluida"]]

    qtd = len(concluidas)
    tempo_auto = sum(n["tempo"] for n in concluidas)
    economia = qtd * minutos_manual * 60 - tempo_auto
    sem_intervencao = sum(1 for n in concluidas if n["sem_intervencao"])
    rotulo_serie, serie = _periodos(de, ate, concluidas)

    kpis = "".join([
        _kpi("NEs concluídas", _n(qtd), f"{_n(len({n['processo'] for n in concluidas}))} processo(s) atendido(s)"),
        _kpi("Tempo da automação", _dur(tempo_auto) if qtd else "—", f"média de {_dur(tempo_auto / qtd)} por NE" if qtd else "sem NEs no período"),
        _kpi("Tempo economizado", _dur(economia) if qtd else "—", f"vs. {_n(minutos_manual, 0 if float(minutos_manual).is_integer() else 1)} min por NE à mão", "destaque"),
        _kpi("Sem intervenção", f"{_n(sem_intervencao)} de {_n(qtd)}", f"{_n(len(pendentes))} NE(s) sem concluir · {_n(sum(n['paginas'] for n in concluidas))} página(s)"),
    ])

    erros = [l for l in linhas if l["situacao"] != "Concluído"]
    ocorrencias = "".join(
        f"<tr><td>{l['inicio']:%d/%m/%Y %H:%M}</td><td>{_e(l['processo'])}</td><td>{_e(l['ne'])}</td>"
        f"<td>{_e(l['situacao'])}</td><td>{_e(l['mensagem'])}</td></tr>"
        for l in erros
    )
    tabela_ocorrencias = (
        f"<table><thead><tr><th>Data</th><th>Processo</th><th>NE</th><th>Situação</th><th>Mensagem</th></tr></thead><tbody>{ocorrencias}</tbody></table>"
        if erros else '<p class="vazio">Nenhuma ocorrência no período.</p>'
    )

    detalhe = "".join(
        f"<tr><td>{n['fim']:%d/%m/%Y}</td><td>{_e(n['processo'])}</td><td>{_e(n['ne'])}</td><td>{_e(n['origem'])}</td>"
        f"<td><span class=\"selo {'ok' if n['concluida'] else 'erro'}\">{'Concluída' if n['concluida'] else 'Pendente'}</span></td>"
        f"<td class=\"num\">{n['paginas']}</td><td class=\"num\">{n['rodadas']}</td><td class=\"num\">{_dur(n['tempo'])}</td></tr>"
        for n in nes
    ) or '<tr><td colspan="8" class="vazio">Nenhuma NE no período.</td></tr>'

    pagina = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Relatório gerencial - NE</title><style>{CSS}</style></head>
<body><div class="folha">
  <header class="topo">
    <div><p class="sobre">Automação SIGEF → SEI · Nota de Empenho</p><h1>Relatório gerencial</h1></div>
    <div class="periodo">Período<strong>{de:%d/%m/%Y} a {ate:%d/%m/%Y}</strong>Gerado em {datetime.now():%d/%m/%Y %H:%M}</div>
  </header>
  <section class="kpis">{kpis}</section>
  <section class="cartao"><h2>NEs concluídas <small>{_e(rotulo_serie)}</small></h2>{_svg_colunas(serie)}</section>
  <section class="cartao"><h2>Ocorrências <small>{len(erros)} rodada(s) com problema</small></h2><div class="rolagem">{tabela_ocorrencias}</div></section>
  <section class="cartao"><h2>Todas as NEs do período</h2><div class="rolagem"><table>
    <thead><tr><th>Data</th><th>Processo</th><th>NE</th><th>Origem</th><th>Situação</th><th class="num">Págs</th><th class="num">Rodadas</th><th class="num">Tempo</th></tr></thead>
    <tbody>{detalhe}</tbody></table></div></section>
  <footer>Como ler: o tempo é só o da automação (a conferência feita pela pessoa não entra). Uma NE que parou e foi retomada
    conta uma vez, com o tempo de todas as rodadas somado. Tempo economizado = NEs concluídas × {_e(minutos_manual)} min
    (tempo informado para fazer uma NE à mão) − tempo da automação. Fonte: metricas/metricas_ne.csv.</footer>
</div><button class="imprimir" onclick="window.print()">Imprimir / salvar PDF</button></body></html>"""

    if destino is None:
        os.makedirs(PASTA_RELATORIOS, exist_ok=True)
        destino = os.path.join(PASTA_RELATORIOS, f"relatorio_ne_{de:%Y-%m-%d}_{ate:%Y-%m-%d}.html")
    with open(destino, "w", encoding="utf-8") as arquivo:
        arquivo.write(pagina)
    return destino
