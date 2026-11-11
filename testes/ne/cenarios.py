"""
Cenários da automação da NE (sem janela) contra o SIGEF/SEI simulados.

    python testes/ne/rodar_cenarios.py        (sobe os simulados e o Chromium e roda todos)

Este arquivo roda UM cenário (A a F) e espera o Chromium já aberto na porta
de CENARIOS_PORTA_CDP (o rodar_cenarios.py cuida disso).
"""
import os
import sys
import urllib.request
from datetime import date, timedelta

CENARIO = sys.argv[1]
AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(os.environ.get("CENARIOS_PASTA", os.path.join(AQUI, "_dados")), f"nucleo_{CENARIO}_{os.getpid()}")   # pasta nova a cada execução
os.environ["LBA_PASTA_DADOS"] = DADOS
sys.path.insert(0, os.path.dirname(os.path.dirname(AQUI)))   # a raiz do programa

from playwright.sync_api import sync_playwright  # noqa: E402

import automacoes.ne.etapa as E  # noqa: E402
import automacoes.sigef_sei.etapa_sei2 as S  # noqa: E402
import automacoes.ne.lote as L  # noqa: E402
import automacoes.ne.metricas as M  # noqa: E402
import automacoes.ne.relatorio as R  # noqa: E402
from automacoes.sigef_sei.etapa_listar_baixar import carregar_sessao, obter_ou_criar_aba, abrir_processo_sei  # noqa: E402

PROC = "0029.001947/2026-67"
PROC_FALHA = "0030.002222/2026-99"


def ok(condicao, texto):
    print(("  ok  " if condicao else "  FALHOU  ") + texto)
    if not condicao:
        raise AssertionError(texto)


def hits():
    return int(urllib.request.urlopen("http://127.0.0.1:8001/__hits").read())


# ---- apontar o código para os servidores simulados ----
from automacoes import geral  # noqa: E402

geral._aplicar(2026)  # as listas e o PDF simulado são de 2026, seja qual for o ano do relógio
E.URL_SIGEF_NE = "http://127.0.0.1:8001/sigef.html"
E.TRECHO_URL_NE = "sigef.html"
E.DOMINIO_SIGEF = "127.0.0.1:8001"
E.DOMINIO_SEI = "127.0.0.1:8002"
E.URL_SEI = "http://127.0.0.1:8002/controlador.php?acao=procedimento_controlar"
L.ESPERA_ANTES_DE_REPETIR = 0

chamadas = []


def anexar_falso(context, aba_sei, progresso, avisos, chave, descricao, texto_link, rotulo, arquivos, numero_pp=None,
                 nome_arvore=""):
    if PROC_FALHA in aba_sei.frame(name="ifrArvore").locator("body").inner_text():
        raise SystemExit("boom de teste")
    chamadas.append(dict(chave=chave, texto_link=texto_link, rotulo=rotulo, arquivos=list(arquivos), numero=numero_pp,
                         nome_arvore=nome_arvore))
    progresso.marcar(chave, "salvo")


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{os.environ.get('CENARIOS_PORTA_CDP', '9333')}")
    context = browser.contexts[0]
    aba_sigef = None

    if CENARIO == "C":
        print("== C: download que não vem (Chrome bloqueando) ==")
        E.TIMEOUT_NE_MS = 4000
        try:
            E.baixar_ne(context, aba_sigef, PROC, "000001", reaproveitar=False)
            ok(False, "devia ter levantado SystemExit")
        except SystemExit as erro:
            ok("não entregou o PDF" in str(erro.code) and "Insecure download blocked" in str(erro.code), "mensagem de download bloqueado clara")
        print("\nTUDO OK no cenário C")
        sys.exit(0)

    if CENARIO == "B":
        print("== B: tipo NE sem campo Número ==")
        aba_sei = obter_ou_criar_aba(context, "127.0.0.1:8002", E.URL_SEI)
        abrir_processo_sei(aba_sei, PROC)
        frame = S._incluir_documento(aba_sei, "NE - Nota de Empenho", "NE", numero_pp=S.NumeroSeExistir("000001"))
        ok(frame.locator("#txtNumero").count() == 0, "sem #txtNumero: seguiu sem travar nem preencher")
        ok(frame.locator("#selHipoteseLegal").input_value() == "3", "Restrito + Documento Preparatório preenchidos")
        print("\nTUDO OK no cenário B")
        sys.exit(0)

    if CENARIO == "F":
        print("== F: tentativa anterior deixou um formulário aberto no processo ==")
        aba_sei = obter_ou_criar_aba(context, "127.0.0.1:8002", E.URL_SEI)
        abrir_processo_sei(aba_sei, PROC)
        S._incluir_documento(aba_sei, "NE - Nota de Empenho", "NE", numero_pp=S.NumeroSeExistir("000001"))
        ok(aba_sei.frame(name="ifrVisualizacao").locator('img[title="Incluir Documento"]').count() == 0,
           "a aba ficou no formulário, sem o botão Incluir Documento")

        def anexar_que_inclui(context, aba_sei, progresso, avisos, chave, descricao, texto_link, rotulo, arquivos, numero_pp=None, nome_arvore=""):
            S._incluir_documento(aba_sei, texto_link, rotulo, numero_pp=numero_pp)   # precisa achar o botão de novo
            progresso.marcar(chave, "salvo")

        E._anexar_documento = anexar_que_inclui
        E.anexar_ne(context, PROC, {"ne": "000001", "arquivos": ["nao_usado.png"], "avisos_download": []})
        ok(E.ne_ja_concluida(PROC, "000001"), "anexar_ne reabriu o processo e achou o Incluir Documento")
        print("\nTUDO OK no cenário F")
        sys.exit(0)

    if CENARIO == "E":
        print("== E: #txtNumero existe mas está oculto/somente leitura ==")
        aba_sei = obter_ou_criar_aba(context, "127.0.0.1:8002", E.URL_SEI)
        abrir_processo_sei(aba_sei, PROC)
        frame = S._incluir_documento(aba_sei, "NE - Nota de Empenho", "NE", numero_pp=S.NumeroSeExistir("000001"))
        ok(frame.locator("#txtNumero").input_value() == "", "campo oculto não foi preenchido e não travou")
        ok(frame.locator("#selHipoteseLegal").input_value() == "3", "Restrito + Documento Preparatório preenchidos")
        print("\nTUDO OK no cenário E")
        sys.exit(0)

    if CENARIO == "D":
        print("== D: SEI recria o iframe do formulário depois de marcar 'Nenhum' ==")
        aba_sei = obter_ou_criar_aba(context, "127.0.0.1:8002", E.URL_SEI)
        abrir_processo_sei(aba_sei, PROC)
        frame = S._incluir_documento(aba_sei, "NE - Nota de Empenho", "NE", numero_pp=S.NumeroSeExistir("000001"))
        ok(frame.locator("#txtNumero").input_value() == "000001", "#txtNumero preenchido no formulário recriado")
        ok(frame.locator("#selHipoteseLegal").input_value() == "3", "Restrito + Documento Preparatório preenchidos")
        ok(frame.locator("#optNenhum").is_checked() and frame.locator("#optRestrito").is_checked(), "radios marcados")
        print("\nTUDO OK no cenário D")
        sys.exit(0)

    print("== A1: leitura de NE/lista ==")
    ok(E.normalizar_ne("2026NE000123") == "000123", "2026NE000123 -> 000123")
    ok(E.normalizar_ne("123") == "000123", "123 -> 000123")
    ok(E.normalizar_ne("2025NE000123") is None, "outro exercício recusado")
    ok(E.normalizar_ne("abc") is None, "lixo recusado")
    texto = "\n".join([
        "Processo;Número",                               # cabeçalho sem coluna "NE": vale a regra dos zeros
        f"{PROC};2026NE000001",                          # ok
        f"{PROC_FALHA}\t000001",                         # ok (vai falhar de propósito)
        "0029001947202667 123",                          # NE curta demais
        f"{PROC}; 2025NE000009",                         # outro exercício
        f"{PROC};2026NE000001",                          # repetido
        "",
    ])
    itens = L.ler_texto_ne(texto)
    ok([i.valido for i in itens] == [True, True, False, False, False], "validade das linhas")
    ok("NE" in itens[2].erro and "outro exercício" in itens[3].erro and "repetido" in itens[4].erro, "mensagens de erro")
    ok(itens[0].ne == "000001" and itens[0].processo == PROC, "processo e NE normalizados")

    print("== A2: download (popup que se fecha sozinho) ==")
    dados, aba_sigef = E.baixar_ne(context, aba_sigef, PROC, "000001", reaproveitar=False)
    nomes = sorted(os.path.basename(a) for a in dados["arquivos"])
    ok(nomes == ["Nota de Empenho - NE 000001_1.png", "Nota de Empenho - NE 000001_2.png"], f"2 PNGs: {nomes}")
    ok(all(os.path.getsize(a) > 0 for a in dados["arquivos"]), "PNGs não vazios")
    ok(not os.path.exists(os.path.join(dados["pasta_processo"], "temp_ne.pdf")), "PDF temporário removido")
    ok(dados["avisos_download"] == [], "PDF traz o número da NE: sem aviso")
    ok(carregar_sessao()["ne_download"]["ne"] == "000001", "sessão gravada")
    antes = hits()
    dados2, _ = E.baixar_ne(context, aba_sigef, PROC, "000001")
    ok(hits() == antes and dados2["arquivos"] == dados["arquivos"], "segunda chamada reaproveita (não baixou de novo)")

    dados_outra, _ = E.baixar_ne(context, aba_sigef, PROC, "000002", reaproveitar=False)
    ok(len(dados_outra["avisos_download"]) == 1 and "000002" in dados_outra["avisos_download"][0], "PDF sem o número pedido gera aviso")

    print("== A3: SEI (processo aberto, tipo NE, retomada) ==")
    E._anexar_documento = anexar_falso
    avisos = E.anexar_ne(context, PROC, dados, "  Empenho do contrato 12  ")
    ok(len(chamadas) == 1, "um documento anexado")
    c = chamadas[0]
    ok(c["nome_arvore"] == "Empenho do contrato 12", f"nome na árvore repassado: {c['nome_arvore']!r}")
    ok(c["chave"] == "NE 000001" and c["texto_link"] == "NE - Nota de Empenho" and c["rotulo"] == "NE", f"tipo e chave: {c['chave']}")
    ok(len(c["arquivos"]) == 2 and isinstance(c["numero"], S.NumeroSeExistir) and c["numero"] == "000001", "2 imagens; número opcional da NE")
    ok(E.ne_ja_concluida(PROC, "000001"), "NE marcada como concluída")
    ok(carregar_sessao()["ne_download"] == {}, "registro de download limpo depois do SEI")
    ok(E.download_ne_ja_feito(PROC, "000001") is None, "download já anexado não é reaproveitado")

    print("== A4: _incluir_documento com campo Número ==")
    aba_sei = obter_ou_criar_aba(context, "127.0.0.1:8002", E.URL_SEI)
    abrir_processo_sei(aba_sei, PROC)
    frame = S._incluir_documento(aba_sei, "NE - Nota de Empenho", "NE", numero_pp=S.NumeroSeExistir("000001"))
    ok(frame.locator("#txtNumero").input_value() == "000001", "#txtNumero preenchido com a NE")
    ok(frame.locator("#txtNomeArvore").input_value() == "", "sem nome: #txtNomeArvore fica vazio")
    aba_sei.reload()  # volta do formulário para o processo, como o anexar_ne faz
    abrir_processo_sei(aba_sei, PROC)
    frame = S._incluir_documento(aba_sei, "NE - Nota de Empenho", "NE", numero_pp=S.NumeroSeExistir("000001"),
                                 nome_arvore="Empenho do contrato 12")
    ok(frame.locator("#txtNomeArvore").input_value() == "Empenho do contrato 12", "#txtNomeArvore preenchido")
    ok(frame.locator("#selHipoteseLegal").input_value() == "3", "e o resto do formulário também")

    print("== A5: processar_ne + lote + métricas + relatório ==")
    chamadas.clear()
    aba_sigef, avisos, tempos = E.processar_ne(context, aba_sigef, PROC, "000001", nome_arvore="NE A5")
    ok(len(chamadas) == 1, "processar_ne anexou")
    ok(chamadas[0]["nome_arvore"] == "NE A5", "processar_ne repassa o nome na árvore")
    ok(tempos["total"] is not None and tempos["sigef"] is not None, "processar_ne devolve os tempos")
    itens = L.ler_texto_ne(texto)   # a lista é lida logo antes de rodar: agora a NE 000001 já consta como concluída
    ok(itens[0].ja_concluida, "lista marca a NE já anexada")
    resultados, csv_lote = L.processar_lote_ne(context, aba_sigef, itens)
    ok([r.estado for r in resultados] == ["ok", "erro"], f"lote: ok + erro -> {[r.estado for r in resultados]}")
    ok(L.AVISO_JA_ANEXADA in resultados[0].avisos, "NE repetida anexada de novo com aviso")
    ok("boom de teste" in resultados[1].mensagem, "erro do segundo registrado")
    conteudo = open(csv_lote, encoding="utf-8-sig").read()
    ok("Concluído" in conteudo and "Erro" in conteudo and "Média por NE" in conteudo, "CSV do lote")
    linhas = M.ler_metricas_ne()
    ok([l["situacao"] for l in linhas] == ["Concluído", "Concluído", "Erro"], f"métricas: {[l['situacao'] for l in linhas]}")
    ok(linhas[0]["paginas"] == 2 and linhas[0]["total"] is not None, "páginas e tempo gravados")
    caminho = R.gerar(date.today() - timedelta(days=1), date.today(), 15)
    html = open(caminho, encoding="utf-8").read()
    ok("NEs concluídas" in html and "000001" in html and "boom de teste" in html, "relatório gerencial gerado")

print("\nTUDO OK no cenário", CENARIO)
