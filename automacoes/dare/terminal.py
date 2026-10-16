"""
DARE automação — ponto de entrada.

Gera o DARE avulso, salva o PDF e o anexa como documento externo no processo do SEI.
Abre o Chrome em modo depuração (SEI + DARE) e processa os lançamentos em lote, digitados
na tela (modo em lotes) ou lidos de uma planilha do Excel (modo planilha).
Uso:  python -m automacoes.dare.terminal   (da pasta da Central de Automações)

Na Central, o normal é usar o módulo DARE da janela (app_janela.py); este é o
modo terminal original do DARE, mantido como alternativa.

Copyright (c) 2026. Todos os direitos reservados. Uso restrito a pessoas autorizadas pelo
titular (veja LICENCA.txt).
Veja o README.md para o passo a passo.
"""

import logging
import os
import sys

try:
    from playwright.sync_api import sync_playwright

    from . import armazenamento, config, dare, fluxo_planilha, logger, menu, navegador, sei, utils
    from .modelos import DadosDare, ResultadoLote
except ImportError as exc:  # dependência não instalada
    sys.exit(
        f"Falta instalar uma dependência ({exc}).\n"
        "Rode:  pip install -r requirements.txt"
    )

log = logging.getLogger("dare.main")

# Lembra, durante a execução do programa, se você já confirmou o login nos dois sistemas.
_estado = {"login_confirmado": False}


def _resumo_erro(exc: BaseException) -> str:
    texto = str(exc)
    return f"{type(exc).__name__}: {texto.splitlines()[0] if texto else ''}"


def _rotulo(i: int, total: int, dados: DadosDare) -> str:
    """'Lote 3/10 (linha 9)' para vários lançamentos; '' para um só digitado."""
    if total <= 1 and not dados.origem:
        return ""
    texto = f"Lote {i}/{total}"
    return f"{texto} ({dados.origem})" if dados.origem else texto


def _observacao(rotulo: str, extra: str = "") -> str:
    return " · ".join(p for p in (rotulo, extra) if p)[:300]


def executar_lotes(lotes: list[DadosDare]) -> tuple[list[ResultadoLote], bool]:
    """
    Processa os lançamentos em sequência, do primeiro ao último, numa única conexão com o Chrome.
    Cada lançamento percorre o fluxo completo (DARE -> PDF -> SEI). Se um falhar, o erro é
    registrado e o loop SEGUE para o próximo. Um lançamento avulso é um lote de tamanho 1.

    Devolve (resultados na ordem processada, interrompido). `interrompido` é True se o usuário
    cancelou com Ctrl+C; então os lotes que sobraram não foram processados.
    """
    total = len(lotes)
    resultados: list[ResultadoLote] = []
    interrompido = False
    try:
        navegador.garantir_chrome()  # reabre o Chrome (SEI + DARE) se foi fechado; senão, só segue
        with sync_playwright() as p:
            _, context = navegador.conectar(p)
            # Impede que o diálogo de impressão do Chrome abra e trave a automação;
            # o PDF é gerado diretamente por navegador.salvar_pdf(). Só vale para o DARE.
            context.add_init_script(
                f"if (location.hostname.includes('{config.HOST_DARE}')) "
                "window.print = () => {};"
            )

            # Abre/localiza as DUAS abas no mesmo Chrome em modo debug:
            # SEI primeiro e DARE por último, para o DARE ficar em foco.
            page_sei, _ = navegador.obter_aba(context, config.HOST_SEI, config.URL_SEI)
            page, dare_criada = navegador.obter_aba(context, config.HOST_DARE, config.URL_DARE)
            navegador.ativar_aba(context, page)
            if not dare_criada:
                page.goto(config.URL_DARE)
            page.wait_for_load_state("networkidle")

            if not _estado["login_confirmado"]:
                menu.aguardar_login()
                _estado["login_confirmado"] = True

            for i, dados in enumerate(lotes, 1):
                rotulo = _rotulo(i, total, dados)
                if total > 1:
                    menu.cabecalho_lote(i, total, dados)
                armazenamento.salvar_ultimos(dados)  # se falhar, dá para repetir sem redigitar
                log.info(
                    "=== %s · processo %s · CPF %s · venc %s · R$ %s ===",
                    rotulo or "Nova execução", dados.processo, utils.mascarar_cpf(dados.cpf),
                    dados.vencimento.strftime("%d/%m/%Y"), dados.valor,
                )
                servidor, pdf = "", ""
                try:
                    # Você pode ter ficado na aba do SEI: procura de novo a do DARE e a traz à frente.
                    page = navegador.garantir_aba(context, page, config.HOST_DARE, config.URL_DARE)
                    navegador.ativar_aba(context, page)
                    if i > 1:  # a partir do 2º lote, volta ao formulário em branco do DARE
                        page.goto(config.URL_DARE)
                    page.wait_for_load_state("networkidle")

                    caminho_pdf, servidor = dare.gerar_dare(context, page, dados)
                    pdf = str(caminho_pdf)
                    page_sei = sei.anexar_pdf(context, page_sei, dados, caminho_pdf)
                except KeyboardInterrupt:
                    log.warning("%s cancelado pelo usuário.", rotulo or "Execução")
                    armazenamento.registrar_historico(
                        dados, "CANCELADO", servidor, pdf, _observacao(rotulo)
                    )
                    raise
                except Exception as exc:  # noqa: BLE001 - registra e segue para o próximo lote
                    navegador.capturar_erro(context)
                    log.exception("Falha em %s", rotulo or "execução")
                    resumo = _resumo_erro(exc)
                    armazenamento.registrar_historico(
                        dados, "ERRO", servidor, pdf, _observacao(rotulo, resumo)
                    )
                    resultados.append(ResultadoLote(dados, False, pdf, servidor, resumo))
                    if os.environ.get("DARE_DEBUG"):
                        raise  # no depurador do VS Code, para exatamente onde deu o erro
                    if total > 1:
                        menu.erro(f"{rotulo} falhou ({resumo}). Seguindo para o próximo...")
                    continue

                armazenamento.registrar_historico(
                    dados, "SUCESSO", servidor, pdf, _observacao(rotulo)
                )
                resultados.append(ResultadoLote(dados, True, pdf, servidor))
                if total > 1:
                    menu.sucesso(f"{rotulo} concluído.")
    except KeyboardInterrupt:
        interrompido = True
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("DARE_DEBUG"):
            raise
        # Falha geral (ex.: Chrome fechado): os lotes que faltavam ficam com este erro.
        log.exception("Falha geral na execução")
        resumo = _resumo_erro(exc)
        for i, dados in enumerate(lotes[len(resultados):], len(resultados) + 1):
            rotulo = _rotulo(i, total, dados)
            armazenamento.registrar_historico(dados, "ERRO", "", "", _observacao(rotulo, resumo))
            resultados.append(ResultadoLote(dados, False, "", "", resumo))

    log.info(
        "=== Fim: %s de %s com sucesso%s ===",
        sum(r.sucesso for r in resultados), total, " (interrompido)" if interrompido else "",
    )
    return resultados, interrompido


def _rodar_lotes(lotes: list[DadosDare]) -> None:
    """Roda todos os lançamentos (digitados ou da planilha) e oferece repetir só os que falharam."""
    armazenamento.salvar_lote(lotes)  # lote pendente: sobrevive a erro, Ctrl+C ou queda do PC
    pendentes = list(lotes)
    while pendentes:
        rodada = pendentes
        resultados, interrompido = executar_lotes(rodada)
        # Pendentes = os que falharam + os que nem chegaram a ser processados.
        pendentes = [d for d, r in zip(rodada, resultados) if not r.sucesso] + \
            rodada[len(resultados):]
        menu.resumo_lotes(resultados, len(rodada))
        if interrompido or not pendentes:
            break
        if not menu.sim_nao(f"Tentar de novo os {len(pendentes)} lote(s) com erro?", padrao=False):
            break
    if pendentes:
        armazenamento.salvar_lote(pendentes)
        menu.info(f"{len(pendentes)} lançamento(s) pendente(s) guardado(s): "
                  "os modos em lotes e planilha oferecem retomá-los.")
    else:
        armazenamento.limpar_lote()
    menu.pausar("Pressione Enter para voltar ao menu...")


def _retomar_pendentes() -> list[DadosDare] | None:
    """Se sobraram lançamentos de uma execução anterior, oferece retomá-los (modo lotes e planilha)."""
    pendentes = armazenamento.carregar_lote()
    if pendentes and menu.sim_nao(
        f"Há {len(pendentes)} lançamento(s) pendente(s) de uma execução anterior. "
        "Retomar? (Não = descartar e começar do zero)", padrao=True,
    ):
        return pendentes
    return None


def _conferir_e_rodar(lotes: list[DadosDare]) -> None:
    armazenamento.salvar_lote(lotes)  # guarda já: não perde o que foi digitado/lido
    if menu.revisar_lotes(lotes):  # conferir, editar, remover ou adicionar antes de iniciar
        armazenamento.salvar_lote(lotes)  # grava a versão corrigida
        _rodar_lotes(lotes)


def _opcao_lotes(ultimos: DadosDare | None) -> None:
    """Modo em lotes: os dados são digitados na tela."""
    lotes = _retomar_pendentes() or menu.coletar_lotes(ultimos)
    _conferir_e_rodar(lotes)


def _opcao_planilha() -> None:
    """Modo planilha: os dados são lidos de uma planilha do Excel (pywin32)."""
    lotes = _retomar_pendentes() or fluxo_planilha.obter_lotes()
    if lotes:
        _conferir_e_rodar(lotes)


def _abrir_chrome_no_inicio() -> None:
    """Abre o Chrome em modo depuração com o SEI e o DARE assim que o programa inicia."""
    if navegador.chrome_debug_ativo():
        return
    menu.info("Abrindo o Chrome em modo depuração com o SEI e o DARE...")
    if navegador.iniciar_chrome():
        menu.sucesso("Chrome aberto. Já pode entrar com a sua conta nos dois sistemas.")
    else:
        menu.aviso(
            "Não consegui abrir o Chrome sozinho (detalhes no log). "
            "Use 'iniciar_chrome_debug.bat' ou defina DARE_CHROME_PATH."
        )
    menu.pausar()


def main() -> None:
    menu.preparar_terminal()
    logger.configurar()
    log.info("Programa iniciado (Python %s).", sys.version.split()[0])
    _abrir_chrome_no_inicio()

    while True:
        try:
            escolha = menu.menu_principal(navegador.chrome_debug_ativo())
        except (KeyboardInterrupt, EOFError):
            break
        if escolha == "0":
            break
        try:
            if escolha == "1":
                _opcao_lotes(armazenamento.carregar_ultimos())
            elif escolha == "2":
                _opcao_planilha()
            elif escolha == "3":
                menu.abrir_pasta(config.PASTA_PDF)
                menu.pausar()
            elif escolha == "4":
                menu.abrir_pasta(config.PASTA_LOGS)
                menu.pausar()
        except (KeyboardInterrupt, EOFError):
            menu.aviso("Cancelado.")
            menu.pausar()

    log.info("Programa encerrado.")
    print("\n  Até logo!\n")


if __name__ == "__main__":
    main()
