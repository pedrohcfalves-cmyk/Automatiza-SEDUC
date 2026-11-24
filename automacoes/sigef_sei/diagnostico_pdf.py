"""
Diagnóstico do modo "Como salvar no SEI: Como PDF" (documento Externo).

Testa a tela do Externo no Chrome da automação (já aberto e com o SEI
logado), SEM SALVAR NADA:

    python -m automacoes.sigef_sei.diagnostico_pdf 0029.001947/2026-67
    python -m automacoes.sigef_sei.diagnostico_pdf 0029.001947/2026-67 --enviar C:\\caminho\\teste.pdf

1. abre o processo, clica em "Incluir Documento" e em "Externo";
2. confere se cada campo que a automação usa está na tela;
3. confere se cada tipo (CE, NL, PP, OB, NE) está na lista #selSerie;
4. com --enviar, põe o PDF no formulário e espera ele aparecer na Lista
   de Anexos (sem clicar em Salvar);
5. recarrega a aba, largando o formulário sem salvar.

Rode com nenhuma automação trabalhando. Na automação de verdade, o mesmo
diagnóstico é gravado sozinho quando um documento falha
(diagnostico_pdf.log e a pasta diagnostico_pdf).
"""
import os
import sys

from . import etapa_listar_baixar as baixar
from . import sei_pdf

CAMPOS = {
    "Tipo do documento": "#selSerie",
    "Data de Elaboração": "#txtDataElaboracao",
    "Número (opcional)": "#txtNumero",
    "Nome na árvore (opcional)": "#txtNomeArvore",
    "Nato-digital": "#optNato",
    "Público": "#optPublico",
    "Campo de arquivo": "#filArquivo",
    "Área de arrastar": ".infraDivDropFile",
    "Salvar": "#btnSalvar",
}
OPCIONAIS = {"Número (opcional)", "Nome na árvore (opcional)", "Área de arrastar"}


def conferir_formulario(frame) -> list[str]:
    """Os campos obrigatórios que NÃO estão na tela (lista vazia = tudo certo)."""
    faltando = []
    for nome, seletor in CAMPOS.items():
        quantos = frame.locator(seletor).count()
        print(f"   {'✔️ ' if quantos else ('➖' if nome in OPCIONAIS else '❌')} {nome:26} {seletor}  ({quantos})")
        if not quantos and nome not in OPCIONAIS:
            faltando.append(nome)
    return faltando


def conferir_tipos(frame) -> list[str]:
    """Os tipos do SERIES_EXTERNO que NÃO estão no #selSerie (nem pelo nome, nem pelo value)."""
    opcoes = sei_pdf.opcoes_serie(frame)
    por_nome = {sei_pdf._sem_acento(t): v for v, t in opcoes}
    valores = {v for v, _t in opcoes}
    faltando = []
    for _tipo, (texto, valor) in sei_pdf.SERIES_EXTERNO.items():
        if sei_pdf._sem_acento(texto) in por_nome:
            print(f"   ✔️  {texto:40} (value {por_nome[sei_pdf._sem_acento(texto)]})")
        elif valor in valores:
            print(f"   ⚠️  {texto:40} não está pelo nome; o value {valor} existe e será usado")
        else:
            print(f"   ❌ {texto:40} não está na lista")
            faltando.append(texto)
    return faltando


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    processo = baixar.normalizar_processo_sei(argv[0]) or argv[0].strip()
    arquivo = argv[argv.index("--enviar") + 1] if "--enviar" in argv and argv.index("--enviar") + 1 < len(argv) else ""
    if arquivo and not sei_pdf.e_pdf(arquivo):
        print(f"❌ {arquivo} não existe ou não é um PDF.")
        return 2

    playwright, _browser, context = baixar.conectar_chrome()
    aba = None
    problemas = []
    try:
        aba = baixar.obter_ou_criar_aba(context, "sei.sistemas.ro.gov.br", baixar.URL_SEI)
        print(f"🔎 Processo {processo} | aba do SEI: {aba.url}")
        print("\n1) Abrindo o processo e clicando em 'Incluir Documento' -> 'Externo':")
        baixar.abrir_processo_sei(aba, processo)
        try:
            sei_pdf.abrir_lista_e_clicar_externo(aba, processo)
        except SystemExit as erro:
            print(f"   ❌ {erro.code}")
            print("\n   O que existe em cada frame agora:")
            print("\n".join(sei_pdf.resumo_frames(aba)))
            return 1
        frame = sei_pdf._esperar_formulario(aba)
        if frame is None:
            print("   ❌ O formulário do Externo (#selSerie) não abriu.")
            print("\n".join(sei_pdf.resumo_frames(aba)))
            return 1
        print(f"   ✔️  formulário aberto no frame '{frame.name}' ({frame.url})")

        print("\n2) Campos do formulário:")
        problemas += conferir_formulario(frame)

        print("\n3) Tipos usados pela automação na lista #selSerie:")
        problemas += conferir_tipos(frame)

        if arquivo:
            print(f"\n4) Enviando {os.path.basename(arquivo)} (sem salvar):")
            try:
                jeito = sei_pdf._enviar_pdf(frame, arquivo, [])
                print(f"   ✔️  o arquivo apareceu na Lista de Anexos (enviado por {jeito})")
            except SystemExit as erro:
                print(f"   ❌ {erro.code}")
                problemas.append("envio do arquivo")

        if problemas:
            base = sei_pdf.registrar_falha_pdf(
                aba, f"diagnostico {processo}", "diagnóstico", SystemExit(", ".join(problemas)), frame=frame
            )
            print(f"\n⚠️  Problemas: {', '.join(problemas)}.\n   Relatório, foto e HTML: {base}.*")
            return 1
        print("\n✅ A tela do Externo tem tudo o que o modo PDF usa.")
        return 0
    finally:
        if aba is not None:
            try:
                aba.reload()   # larga o formulário sem salvar
            except Exception:
                pass
        playwright.stop()


if __name__ == "__main__":
    sys.exit(main())
