"""
O que muda no Anexar Documentos por ele rodar dentro da Central de Automações.

Roda no processo da automação (o executor), logo antes do fluxo começar:

    ano do SIGEF   os endereços do SIGEF (SIGEF2026/...) passam a usar o exercício escolhido no
                   rodapé da barra lateral da Central (automacoes/geral.py), como a OB e a NE.
    um Chrome só   quando precisa abrir o Chrome da automação, abre o da Central (mesma porta 9222,
                   mesmo perfil C:\\ChromeAutomacao), com as opções dela: o SIGEF tratado como origem
                   segura (o download do PDF não é bloqueado) e os popups do SEI liberados.

Nada das regras do Anexar Documentos muda: só o endereço e o jeito de abrir o Chrome.
"""


def ligar() -> None:
    from automacoes import geral
    from automacoes.anexar.automacao import utils

    try:
        geral._aplicar(geral.ano_sigef())
    except Exception as erro:  # noqa: BLE001 - sem o ano, fica o do código
        print(f"⚠️  Não consegui aplicar o ano do SIGEF da Central ({erro}); usando o do programa.")

    _abrir_original = utils._abrir_chrome_debug

    def abrir_chrome_da_central(porta: int) -> None:
        from automacoes.sigef_sei import preparar_navegador

        try:
            preparar_navegador.achar_chrome()
        except SystemExit:
            # A Central não achou o Chrome nos lugares dela: o Anexar procura também no registro
            # do Windows (e, sem Chrome nenhum, dá a mensagem de sempre).
            return _abrir_original(porta)
        preparar_navegador.abrir_chrome_debug(porta, urls=())

    utils._abrir_chrome_debug = abrir_chrome_da_central
