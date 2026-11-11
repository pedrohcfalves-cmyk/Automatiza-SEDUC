"""
O Cadastro de Credores sozinho, pela tela preta (o antigo "python Cadastrar.py").

    python -m automacoes.cadastro.terminal     (da pasta do programa)

O script abre o Chrome da automação (o mesmo da Central: porta 9222, perfil
C:\\ChromeAutomacao), aguarda o login no SIGEF e então oferece o menu de execução.
O navegador permanece aberto ao final. As estatísticas e os registros ficam em
~/.sigef-automacao, como no programa antigo.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

from automacoes import geral
from automacoes.sigef_sei.preparar_navegador import PASTA_PERFIL_CHROME_AUTOMACAO

from . import config, navegador as _navegador
from .console import menu_principal, modo_lotes, modo_planilha, preparar_navegador
from .log import configurar_log, logger
from .navegador import ErroNavegador, Navegador

MODOS = (modo_lotes, modo_planilha)

# Como na janela da Central: o ano do SIGEF escolhido e o perfil do Chrome da Central.
geral._aplicar(geral.ano_sigef())
config.PERFIL_CHROME = _navegador.PERFIL_CHROME = Path(PASTA_PERFIL_CHROME_AUTOMACAO)


def main() -> None:
    configurar_log()
    logger.info("Início da execução (terminal)")

    with sync_playwright() as playwright:
        navegador = Navegador(playwright)
        preparar_navegador(navegador)

        while True:
            escolha = menu_principal()

            if escolha == len(MODOS):  # Sair
                break

            try:
                MODOS[escolha](navegador)
            except KeyboardInterrupt:
                print("\nExecução interrompida. Voltando ao menu.")
            except ErroNavegador as erro:
                print(f"\n{erro}")
                preparar_navegador(navegador)

            # Volta ao começo do fluxo e segue aguardando o próximo trabalho
            try:
                navegador.page.goto(_navegador.URL_MANTER_CREDOR)
            except Exception:
                pass

    logger.info("Fim da execução")
    print("\nAutomação encerrada. O Chrome continua aberto para uso normal.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário.")
    except Exception as erro:
        print(f"\nFalha: {erro}")
