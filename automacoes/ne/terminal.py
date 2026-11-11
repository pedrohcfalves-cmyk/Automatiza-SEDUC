"""
A NE sozinha, pela tela preta (a mesma automação da janela da Central).

    python -m automacoes.ne.terminal     (da pasta do programa)

Menu:
    1  Uma NE            pergunta o processo e a NE
    2  Lote por arquivo  planilha .xlsx, .csv ou .txt com processo + NE em cada linha
    3  Lote colado      cola a lista (do Excel, de um e-mail...) e roda
    4  Relatório         página HTML com tempo e quantidade de NEs do período

O Chrome da automação é aberto só quando a opção precisa dele (1, 2 e 3) e
já com o bloqueio de download de site http desligado. Documentos baixados,
sessão, métricas e relatórios ficam em Documentos\\Automacao SIGEF-SEI.
"""
import os
from datetime import date, datetime

from automacoes.sigef_sei.etapa_listar_baixar import PASTA_BASE, carregar_sessao, normalizar_processo_sei
from automacoes.sigef_sei.preparar_navegador import _caixa, _linha, aviso_conferencia_final, preparar_navegador

from .etapa import URL_SIGEF_NE, conferencia_final, normalizar_ne, processar_ne
from .lote import ler_arquivo_ne, ler_texto_ne, processar_lote_ne
from .relatorio import gerar


def _apresentacao_ne() -> None:
    _caixa(["AUTOMACAO  SIGEF  -->  SEI", "Nota de Empenho (NE): download e inclusao no processo"], caractere="=")
    print("O QUE ESTE PROGRAMA FAZ")
    print()
    print("  A partir do número de uma Nota de Empenho (NE) e do processo no SEI,")
    print("  o programa imprime a NE no SIGEF, baixa o PDF, converte cada página")
    print('  em imagem e a anexa ao processo como "NE - Nota de Empenho", com')
    print('  Nível de Acesso Restrito e hipótese legal "Documento Preparatório".')
    print()
    print("O QUE ELE NÃO FAZ")
    print()
    print("  Não gera, não altera e não exclui nada no SIGEF: a NE precisa JÁ")
    print("  EXISTIR. Só CONSULTA, BAIXA e ANEXA.")
    print()
    _linha("-")


_navegador = {}


def _contexto():
    """Prepara o Chrome (login guiado) na primeira vez e reaproveita nas seguintes."""
    if not _navegador:
        playwright, _browser, context, aba_sigef, _aba_sei = preparar_navegador(
            url_destino=URL_SIGEF_NE, apresentacao=_apresentacao_ne
        )
        _navegador.update(playwright=playwright, context=context, aba_sigef=aba_sigef)
    return _navegador["context"], _navegador["aba_sigef"]


def _perguntar(texto: str, padrao: str = "") -> str:
    resposta = input(f"{texto}{f' [{padrao}]' if padrao else ''}: ").strip()
    return resposta or padrao


def perguntar_processo(sessao: dict) -> str:
    while True:
        processo = normalizar_processo_sei(_perguntar("Processo do SEI (ex.: 0029.001947/2026-67)", sessao.get("processo", "")))
        if processo:
            return processo
        print("   ⚠️  Não parece um processo: são 16 dígitos (pontuação não importa).")


def perguntar_ne(sessao: dict) -> str:
    while True:
        ne = normalizar_ne(_perguntar("Nota de Empenho (ex.: 2026NE000123 ou 000123)", sessao.get("ne", "")))
        if ne:
            return ne
        print("   ⚠️  NE inválida (ou de outro exercício que não o da tela do SIGEF).")


def uma_ne() -> None:
    sessao = carregar_sessao()
    processo = perguntar_processo(sessao)
    ne = perguntar_ne(sessao)
    context, aba_sigef = _contexto()
    aba_sigef, avisos, _tempos = processar_ne(context, aba_sigef, processo, ne)
    _navegador["aba_sigef"] = aba_sigef
    conferencia_final(processo, avisos)


def _conferir_lista(itens) -> bool:
    """Mostra o que vai e o que não vai ser processado e pede o OK."""
    validos = [i for i in itens if i.valido]
    print(f"\n📋 {len(itens)} linha(s) lida(s): {len(validos)} válida(s), {len(itens) - len(validos)} com problema.")
    for i in itens:
        if not i.valido:
            print(f"   ❌ linha {i.linha}: {i.erro}   [{i.original}]")
        elif i.ja_concluida:
            print(f"   ⚠️  linha {i.linha}: NE {i.ne} já foi anexada no processo {i.processo} antes -- será anexada de novo.")
    if not validos:
        print("Nada para processar.")
        return False
    return _perguntar(f"\nProcessar as {len(validos)} NE(s) válidas? (S/N)", "S").lower() in ("s", "sim")


def _rodar_lote(itens) -> None:
    if not _conferir_lista(itens):
        return
    context, aba_sigef = _contexto()
    resultados, relatorio = processar_lote_ne(context, aba_sigef, itens)

    ok = [r for r in resultados if r.estado == "ok"]
    erros = [r for r in resultados if r.estado == "erro"]
    print(f"\n{'=' * 60}\nLOTE TERMINADO: {len(ok)} concluída(s), {len(erros)} com erro.\nRelatório: {relatorio}\n{'=' * 60}")
    for r in erros:
        print(f"   ❌ {r.item.processo} | NE {r.item.ne}: {r.mensagem.strip().splitlines()[0] if r.mensagem.strip() else 'erro'}")
    avisos = [f"{r.item.processo} NE {r.item.ne}: {aviso}" for r in ok for aviso in r.avisos]
    aviso_conferencia_final("", avisos)
    input("\n>>> Confira os processos no SEI e, quando terminar, aperte ENTER: ")


def lote_arquivo() -> None:
    caminho = _perguntar("Caminho da planilha/lista (.xlsx, .csv, .txt)").strip('"')
    if not os.path.isfile(caminho):
        print(f"   ⚠️  Não achei o arquivo: {caminho}")
        return
    try:
        itens = ler_arquivo_ne(caminho)
    except (ValueError, OSError) as erro:
        print(f"   ⚠️  {erro}")
        return
    _rodar_lote(itens)


def lote_colado() -> None:
    print("Cole a lista (uma NE por linha, com o processo e a NE). Termine com uma linha em branco:")
    linhas = []
    while True:
        linha = input()
        if not linha.strip():
            break
        linhas.append(linha)
    _rodar_lote(ler_texto_ne("\n".join(linhas)))


def _data(texto: str, padrao: date) -> date:
    while True:
        resposta = _perguntar(texto, f"{padrao:%d/%m/%Y}")
        try:
            return datetime.strptime(resposta, "%d/%m/%Y").date()
        except ValueError:
            print("   ⚠️  Use dia/mês/ano, ex.: 31/10/2026.")


def relatorio() -> None:
    hoje = date.today()
    de = _data("De", hoje.replace(day=1))
    ate = _data("Até", hoje)
    minutos = float(_perguntar("Minutos para fazer uma NE à mão", "15").replace(",", "."))
    caminho = gerar(de, ate, minutos)
    print(f"\n✅ Relatório gerado: {caminho}")
    if hasattr(os, "startfile"):
        os.startfile(caminho)


MENU = {"1": uma_ne, "2": lote_arquivo, "3": lote_colado, "4": relatorio}


def main() -> None:
    try:
        while True:
            print(f"\n{'=' * 60}\nAUTOMAÇÃO NE  (dados em {PASTA_BASE})\n{'=' * 60}")
            print("  1  Uma NE\n  2  Lote por arquivo (planilha/csv/txt)\n  3  Lote colado\n  4  Relatório gerencial\n  0  Sair")
            opcao = input("\nEscolha: ").strip()
            if opcao in ("0", "sair"):
                return
            acao = MENU.get(opcao)
            if acao is None:
                print("   ⚠️  Opção inválida.")
                continue
            try:
                acao()
            except SystemExit as erro:   # as etapas param assim, com a explicação em português
                if erro.code not in (None, 0):
                    print(erro.code)
            except KeyboardInterrupt:
                print("\n⏹️  Interrompido. O que já foi anexado fica salvo; rodar de novo continua de onde parou.")
    finally:
        if _navegador:
            _navegador["playwright"].stop()
            print("\nO Chrome da automação continua aberto -- pode fechar na mão, se quiser.")


if __name__ == "__main__":
    main()
