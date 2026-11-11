"""
Diagnóstico da opção "CE pela tela Imprimir Despesa Certificada".

Testa SÓ a impressão de uma CE, passo a passo, no Chrome da automação
(já aberto e com o SIGEF logado), sem mexer no SEI:

    python -m automacoes.sigef_sei.diagnostico_ce 2026CE001234

Mostra o que achou em cada passo e, se falhar, onde ficaram a foto, o
HTML e o relatório (Documentos\\Automacao SIGEF-SEI\\diagnostico_ce\\).
Rode com nenhuma automação trabalhando: usa a aba do SIGEF e a devolve
para "Listar Ordem Bancária" no fim.

Na automação de verdade, o mesmo diagnóstico é gravado sozinho quando uma
CE falha (diagnostico_ce.log e a pasta diagnostico_ce).
"""
import os
import sys

from . import etapa_listar_baixar as baixar


def conferir_tela(aba) -> list[str]:
    """Os seletores da tela que NÃO estão lá (lista vazia = tudo certo)."""
    faltando = []
    for nome, seletor in baixar.SELETORES_TELA_CE.items():
        quantos = aba.locator(seletor).count()
        print(f"   {'✔️ ' if quantos else '❌'} {nome:16} {seletor}  ({quantos})")
        if not quantos:
            faltando.append(nome)
    return faltando


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    numero_ce = argv[0].strip().upper()
    sequencial = baixar.sequencial_ce_para_impressao(numero_ce)
    print(f"🔎 CE {numero_ce} | exercício do SIGEF: {baixar.ano_sigef()} | tela: {baixar.URL_SIGEF_IMPRIMIR_CE}")
    if not sequencial:
        print(
            "❌ Esta CE não serve para a tela de impressão: o número tem que ser "
            f"AAAACE + até 6 dígitos e do exercício {baixar.ano_sigef()}.\n"
            "   Na automação, ela sairia pelo caminho de sempre (o da PP)."
        )
        return 1

    playwright, _browser, context = baixar.conectar_chrome()
    try:
        aba = baixar.obter_ou_criar_aba(context, "sigef.sefin.ro.gov.br", baixar.URL_SIGEF_LISTAR_OB)
        print("\n1) Abrindo a tela e conferindo os campos:")
        aba.goto(baixar.URL_SIGEF_IMPRIMIR_CE)
        aba.wait_for_load_state("networkidle")
        print(f"   aba em: {aba.url}")
        faltando = conferir_tela(aba)
        if faltando:
            print(
                f"\n⚠️  Não achei: {', '.join(faltando)}. A sessão do SIGEF caiu (entre de novo) "
                "ou o SIGEF mudou a tela -- veja o relatório abaixo."
            )

        print("\n2) Imprimindo de verdade:")
        pasta = os.path.join(baixar.PASTA_DIAGNOSTICO_CE, "teste")
        os.makedirs(pasta, exist_ok=True)
        try:
            jpgs, conferida = baixar._baixar_ce_impressao(context, aba, pasta, numero_ce, sequencial)
        except SystemExit as erro:
            print(f"❌ {erro}\n   Relatório, foto e HTML em: {baixar.PASTA_DIAGNOSTICO_CE}")
            return 1
        print(f"✅ {len(jpgs)} imagem(ns) em {pasta}")
        print({True: "✅ O PDF mostra o número da CE.",
               False: "⚠️  O PDF NÃO mostra o número da CE -- abra a imagem e confira.",
               None: "ℹ️  Não deu para ler o texto do PDF -- abra a imagem e confira."}[conferida])
        return 0
    finally:
        try:
            aba.goto(baixar.URL_SIGEF_LISTAR_OB)
        except Exception:
            pass
        playwright.stop()


if __name__ == "__main__":
    sys.exit(main())
