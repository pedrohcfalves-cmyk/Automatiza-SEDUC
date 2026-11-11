"""
Nota de Empenho (NE): baixa do SIGEF e anexa no processo do SEI.

    dados, aba_sigef = baixar_ne(context, aba_sigef, processo, ne)
    avisos = anexar_ne(context, processo, dados)

    aba_sigef, avisos, tempos = processar_ne(context, aba_sigef, processo, ne)   # as duas, com métricas

É o mesmo caminho da OB (automacoes/sigef_sei: etapa_listar_baixar +
etapa_sei2) com um único tipo de documento. Do que já existia vêm: o
login guiado, a retomada depois de queda (progresso_sei.json), a divisão
por tamanho do SEI, a redução das imagens e a conferência dos arquivos
salvos.

NO SIGEF  tela "Imprimir Nota de Empenho" -> Imprimir -> janela de formato
          -> PDF -> uma imagem PNG por página, na pasta do processo:
          "Nota de Empenho - NE 000123.png" (ou "..._1.png", "..._2.png").
NO SEI    "Incluir Documento" -> "NE - Nota de Empenho", Restrito +
          Documento Preparatório, imagens coladas no corpo.

A NE é identificada pelo SEQUENCIAL com 6 dígitos ("000123"): é o que a
tela do SIGEF pede. "2026NE000123" e "123" valem a mesma NE.
"""
import os
import re
import traceback

import pymupdf
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from automacoes.geral import ano_sigef, url_sigef
from automacoes.sigef_sei.etapa_listar_baixar import (
    CD_GESTAO,
    CD_UNIDADE_GESTORA,
    PASTA_BASE,
    TRECHO_URL_PROCESSO_ABERTO_SEI,
    URL_SEI,
    URL_SIGEF_PORTAL,
    abrir_processo_sei,
    campo_existe,
    carregar_sessao,
    fechar_janelas_sobrando,
    ler_valor_campo,
    nome_pasta_valido,
    obter_ou_criar_aba,
    salvar_sessao,
)
from automacoes.sigef_sei.etapa_sei2 import (
    CANDIDATOS_FRAMES,
    NumeroSeExistir,
    ProgressoSei,
    _aguardar_rede,
    _anexar_documento,
    _procurar_lugar,
    ob_ja_concluida,
)
from automacoes.sigef_sei.preparar_navegador import DOMINIO_SEI, DOMINIO_SIGEF, aviso_conferencia_final

from .metricas import CronometroNE

# ------------------------------------------------------------------ SIGEF

URL_SIGEF_NE = url_sigef("ORC/ORCImprimirNotaEmpenho.aspx?CdTransacao=514")
TRECHO_URL_NE = "ORCImprimirNotaEmpenho"

# A tela é de um exercício só (o escolhido na janela; padrão, o ano atual --
# automacoes/geral.py): NE de outro ano não está nela.
ANO_SIGEF = str(ano_sigef())

CAMPO_NE_INICIAL = "#txtNotaEmpenhoNumeroInicial"
CAMPO_NE_FINAL = "#txtNotaEmpenhoNumeroFinal"

# Quanto esperar pela janela de formato e pelo PDF antes de desistir.
TIMEOUT_NE_MS = 60000

# Quantas vezes o download recomeça sozinho quando o SIGEF fecha uma
# janela no meio ("Target page, context or browser has been closed").
TENTATIVAS_JANELA_FECHADA = 3

DPI_PNG = 200

# ------------------------------------------------------------------- SEI

TEXTO_LINK_NE = "NE - Nota de Empenho"

REGEX_NE = re.compile(r"^\s*(?:(\d{4})\s*NE\s*)?(\d{1,6})\s*$", re.IGNORECASE)


def normalizar_ne(texto) -> str | None:
    """
    O sequencial da NE com 6 dígitos, ou None se não for uma NE desta tela.

        2026NE000123 -> 000123      123 -> 000123      2025NE000123 -> None
    """
    achado = REGEX_NE.match(str(texto or ""))
    if not achado:
        return None
    ano, numero = achado.groups()
    if (ano and ano != ANO_SIGEF) or int(numero) == 0:
        return None
    return numero.zfill(6)


def _pasta(processo: str) -> str:
    return os.path.join(PASTA_BASE, nome_pasta_valido(processo))


def _prefixo(ne: str) -> str:
    return f"Nota de Empenho - NE {ne}"


def arquivos_da_ne(processo: str, ne: str) -> list[str]:
    """As páginas já salvas desta NE na pasta do processo, em ordem."""
    pasta = _pasta(processo)
    padrao = re.compile(rf"^{re.escape(_prefixo(ne))}(?:_(\d+))?\.png$")
    achados = []
    for nome in os.listdir(pasta) if os.path.isdir(pasta) else []:
        casamento = padrao.match(nome)
        if casamento:
            achados.append((int(casamento.group(1) or 1), os.path.join(pasta, nome)))
    return [caminho for _pagina, caminho in sorted(achados)]


def download_ne_ja_feito(processo: str, ne: str) -> list[str] | None:
    """
    As imagens do último download, se foi desta NE neste processo e todas
    ainda estão na pasta. É o que evita baixar de novo quando a falha foi
    depois, no SEI (quase sempre a internet caindo na hora de colar).
    """
    registro = carregar_sessao().get("ne_download") or {}
    if registro.get("processo") != processo or registro.get("ne") != ne:
        return None
    arquivos = registro.get("arquivos") or []
    return arquivos if arquivos and all(os.path.exists(a) for a in arquivos) else None


MSG_DOWNLOAD_NAO_VEIO = (
    "\n❌ O Chrome não entregou o PDF da NE {ne} em {segundos}s.\n"
    "   Quase sempre é o bloqueio de download de site http (\"Insecure download blocked\").\n\n"
    "   O QUE FAZER:\n"
    "     1. Feche TODAS as janelas do Chrome da automação.\n"
    "     2. Rode o programa de novo -- ele reabre o Chrome já com o bloqueio desligado\n"
    "        (isso só vale quando o Chrome é aberto pelo programa).\n"
    "     3. Se o Chrome já foi aberto assim e ainda bloqueia: clique no ícone de\n"
    "        download da barra do Chrome e em 'Manter' no arquivo bloqueado.\n"
)


# --------------------------------------------------------- Sessão do SIGEF


def _abrir_tela_ne(context, aba_sigef):
    """Leva a aba do SIGEF à tela da NE; reabre a aba se ela fechou sozinha."""
    if aba_sigef is None or aba_sigef.is_closed():
        return obter_ou_criar_aba(context, DOMINIO_SIGEF, URL_SIGEF_NE, TRECHO_URL_NE)
    aba_sigef.bring_to_front()
    try:
        aba_sigef.goto(URL_SIGEF_NE)
        aba_sigef.wait_for_load_state("networkidle")
    except PlaywrightError:
        # O alert de sessão expirada do SIGEF às vezes fecha a própria aba.
        if not aba_sigef.is_closed():
            raise
        return obter_ou_criar_aba(context, DOMINIO_SIGEF, URL_SIGEF_NE, TRECHO_URL_NE)
    return aba_sigef


def garantir_sessao_ne(context, aba_sigef):
    """
    Abre a tela da NE e confere que a sessão do SIGEF está ativa. Se
    caiu, pede o login de novo (sem reabrir o Chrome nem perder o que já
    foi feito). Devolve a aba pronta -- pode ser uma aba nova.
    """
    aba_sigef = _abrir_tela_ne(context, aba_sigef)
    if campo_existe(aba_sigef, CAMPO_NE_INICIAL):
        return aba_sigef

    print("\n⚠️  A sessão do SIGEF expirou (a tela da NE não abriu).")
    aba_sigef.bring_to_front()
    try:
        aba_sigef.goto(URL_SIGEF_PORTAL)
        aba_sigef.wait_for_load_state("networkidle")
    except PlaywrightError:
        pass
    input(
        "\n>>> A SESSÃO DO SIGEF EXPIROU.\n"
        "\n"
        "    Na aba do SIGEF, entre de novo com seu usuário e senha. Depois\n"
        "    volte aqui e aperte ENTER para continuar de onde parou: "
    )

    aba_sigef = _abrir_tela_ne(context, aba_sigef)
    if not campo_existe(aba_sigef, CAMPO_NE_INICIAL):
        raise SystemExit(
            "\n❌ Mesmo depois de entrar, a tela 'Imprimir Nota de Empenho' não abriu. "
            "Confira a aba do SIGEF -- se houver uma mensagem de erro, resolva nela e rode de novo "
            "(o que já foi baixado continua salvo).\n"
        )
    return aba_sigef


# ---------------------------------------------------------------- Download


def _baixar_ne_uma_vez(context, aba_sigef, processo: str, ne: str):
    aba_sigef = garantir_sessao_ne(context, aba_sigef)
    # Janelas do SIGEF que sobraram de uma tentativa que caiu atrapalham a nova.
    fechar_janelas_sobrando(context, manter=aba_sigef)

    # UG e gestão costumam vir preenchidas; só mexe se estiverem diferentes
    # (trocar a UG dispara recarga da tela no SIGEF).
    mudou = False
    for seletor, valor in (("#txtUnidadeGestora", CD_UNIDADE_GESTORA), ("#txtGestao_SIGEFPesquisa", CD_GESTAO)):
        campo = aba_sigef.locator(seletor)
        if ler_valor_campo(campo).strip().lstrip("0") != valor.lstrip("0"):
            campo.fill(valor)
            mudou = True
    if mudou:
        aba_sigef.wait_for_load_state("networkidle")

    aba_sigef.locator(CAMPO_NE_INICIAL).fill(ne)
    aba_sigef.locator(CAMPO_NE_FINAL).fill(ne)

    # O id do botão bate em dois elementos (o <a> e o <img>): o SIGEF roda
    # em modo quirks e o id não diferencia maiúscula. Por isso a tag.
    try:
        with context.expect_page(timeout=TIMEOUT_NE_MS) as formato_info:
            aba_sigef.locator("img#btnImpressao_BtnImprimir").click()
    except PlaywrightTimeoutError:
        raise SystemExit(
            f"\n❌ Cliquei em Imprimir para a NE {ne}, mas a janela 'Selecione o tipo de arquivo' "
            "não abriu.\n   Olhe a tela do SIGEF: se mostrar uma crítica, é o número da NE "
            "(ela existe no SIGEF? é desta gestão?).\n"
        ) from None
    pagina_formato = formato_info.value
    pagina_formato.wait_for_load_state("networkidle")

    pasta = _pasta(processo)
    os.makedirs(pasta, exist_ok=True)
    caminho_pdf = os.path.join(pasta, "temp_ne.pdf")

    # O SIGEF fecha esta janela sozinho logo depois de baixar: por isso o
    # download é ouvido no context (como o sistema da OB), não na janela.
    try:
        with context.expect_event("download", timeout=TIMEOUT_NE_MS) as download_info:
            try:
                pagina_formato.locator('img[alt="Imprime Arquivo Formato PostScript (.pdf)"]').click()
            except PlaywrightTimeoutError:
                raise SystemExit(
                    f"\n❌ Não achei o ícone do PDF na janela de formato da NE {ne}. "
                    "Olhe a janela que ficou aberta no Chrome.\n"
                ) from None
            except PlaywrightError as erro:
                if "closed" not in str(erro).lower():
                    raise  # janela fechando logo após o clique é o esperado
    except PlaywrightTimeoutError:
        raise SystemExit(MSG_DOWNLOAD_NAO_VEIO.format(ne=ne, segundos=TIMEOUT_NE_MS // 1000)) from None
    download_info.value.save_as(caminho_pdf)

    for velho in arquivos_da_ne(processo, ne):   # sobras de uma rodada com outro nº de páginas
        os.remove(velho)

    avisos = []
    with pymupdf.open(caminho_pdf) as doc:
        texto = " ".join(pagina.get_text() for pagina in doc)
        arquivos = []
        for i, pagina in enumerate(doc, start=1):
            sufixo = "" if len(doc) == 1 else f"_{i}"
            destino = os.path.join(pasta, f"{_prefixo(ne)}{sufixo}.png")
            pagina.get_pixmap(dpi=DPI_PNG).save(destino)
            arquivos.append(destino)
    os.remove(caminho_pdf)

    # PDF com texto que não traz o número pedido: pode ser outra NE.
    if texto.strip() and ne not in texto:
        avisos.append(f"O PDF baixado não traz o número {ne} no texto -- confira se é a NE certa.")

    if not pagina_formato.is_closed():
        pagina_formato.close()

    salvar_sessao(ne_download={"processo": processo, "ne": ne, "arquivos": arquivos})
    print(f"   📄 NE {ne}: {len(arquivos)} página(s) em PNG.")
    dados = {"processo": processo, "ne": ne, "pasta_processo": pasta, "arquivos": arquivos, "avisos_download": avisos}
    return dados, aba_sigef


def baixar_ne(context, aba_sigef, processo: str, ne: str, reaproveitar: bool = True):
    """
    Baixa a NE do SIGEF e devolve (dados, aba_sigef). Recomeça sozinho
    quando uma janela do SIGEF fecha no meio; nada foi anexado no SEI
    nesta etapa, então recomeçar é seguro.
    """
    if reaproveitar:
        ja_feito = download_ne_ja_feito(processo, ne)
        if ja_feito:
            print(f"   ♻️  A NE {ne} já foi baixada ({len(ja_feito)} página(s)) -- não baixo de novo.")
            dados = {
                "processo": processo, "ne": ne, "pasta_processo": _pasta(processo),
                "arquivos": ja_feito, "avisos_download": [],
            }
            return dados, aba_sigef

    for tentativa in range(1, TENTATIVAS_JANELA_FECHADA + 1):
        try:
            return _baixar_ne_uma_vez(context, aba_sigef, processo, ne)
        except PlaywrightError as erro:
            if "has been closed" not in str(erro) or tentativa == TENTATIVAS_JANELA_FECHADA:
                raise
            if not context.browser or not context.browser.is_connected():
                raise   # o Chrome inteiro fechou: recomeçar não adianta
            print(
                f"\n⚠️  Uma janela do SIGEF fechou no meio do download ({erro}).\n"
                f"   Recomeçando o download da NE sozinho (tentativa {tentativa + 1} de {TENTATIVAS_JANELA_FECHADA})..."
            )
            print(traceback.format_exc())
            if aba_sigef is not None and aba_sigef.is_closed():
                aba_sigef = None   # garantir_sessao_ne() abre outra


# --------------------------------------------------------------------- SEI


def anexar_ne(context, processo: str, dados: dict, nome_arvore: str = "") -> list[str]:
    """
    Anexa as imagens da NE no processo do SEI e devolve os avisos da
    rodada (documento vazio que sobrou de uma queda, divisão por
    tamanho...). Sabe retomar: o que já foi salvo numa tentativa
    anterior é pulado. `nome_arvore` vai no campo "Nome na Árvore" do
    SEI (em branco, fica vazio).
    """
    ne, arquivos = dados["ne"], dados["arquivos"]
    if not arquivos:
        raise SystemExit(f"\n⚠️  Não há imagem da NE {ne} para anexar no processo '{processo}'.\n")

    progresso = ProgressoSei(processo, f"NE{ne}")
    avisos = list(dados.get("avisos_download") or [])
    if progresso.retomando:
        prontos = sum(1 for d in progresso.documentos.values() if d.get("estado") == "salvo")
        print(f"\n🔁 Continuando de onde parou: {prontos} documento(s) já anexado(s) desta NE.")

    aba_sei = obter_ou_criar_aba(context, dominio=DOMINIO_SEI, url_navegacao=URL_SEI)
    aba_sei.bring_to_front()
    # Nunca navega para um endereço escrito à mão: o SEI só aceita links com o código de
    # segurança (infra_hash) da sessão, e sem ele manda para o login. A aba que a pessoa
    # já abriu logada é reaproveitada como está. Se ela ficou num processo com um formulário
    # aberto (tentativa que caiu), recarrega o mesmo endereço, que mantém o código.
    if TRECHO_URL_PROCESSO_ABERTO_SEI in (aba_sei.url or ""):
        aba_sei.reload()
        _aguardar_rede(aba_sei)
    abrir_processo_sei(aba_sei, processo)
    _aguardar_rede(aba_sei)

    # Processo arquivado: o SEI mostra "Reabrir Processo". Não achar não é erro.
    _, reabrir, lugar = _procurar_lugar(aba_sei, CANDIDATOS_FRAMES, 'img[title="Reabrir Processo"]:visible')
    if reabrir is not None:
        reabrir.click()
        print(f"Processo estava arquivado -- cliquei em 'Reabrir Processo' (achado em '{lugar}').")

    _anexar_documento(
        context, aba_sei, progresso, avisos,
        f"NE {ne}", f"NE {ne}", TEXTO_LINK_NE, "NE", arquivos,
        numero_pp=NumeroSeExistir(ne), nome_arvore=(nome_arvore or "").strip(),
    )
    progresso.concluir()
    salvar_sessao(ne_download={})
    return avisos


def ne_ja_concluida(processo: str, ne: str) -> bool:
    """True se esta NE já foi anexada inteira neste processo numa rodada anterior."""
    return ob_ja_concluida(processo, f"NE{ne}")


def conferencia_final(processo: str, avisos) -> None:
    """Aviso de conferência e pausa, para a pessoa olhar o SEI antes de assinar."""
    aviso_conferencia_final(processo, avisos)
    input(
        "\n>>> Confira o documento na tela do SEI, faça o que for preciso\n"
        "    (ordenar, assinar, incluir em bloco de assinatura) e, quando\n"
        "    terminar, volte aqui e aperte ENTER: "
    )


def processar_ne(context, aba_sigef, processo: str, ne: str, origem: str = "avulsa", ao_etapa=None,
                 nome_arvore: str = ""):
    """
    Uma NE do começo ao fim (SIGEF e SEI), com a métrica gravada. O
    relógio para antes da conferência: o tempo da pessoa não entra.
    Devolve (aba_sigef, avisos, tempos) -- tempos em segundos: sigef, sei,
    total. `ao_etapa("sigef"|"sei", dados)` avisa a tela.
    """
    ao_etapa = ao_etapa or (lambda etapa, dados=None: None)
    cron = CronometroNE(origem, processo, ne)
    dados = None
    try:
        salvar_sessao(processo=processo, ne=ne)
        cron.etapa("sigef")
        ao_etapa("sigef")
        dados, aba_sigef = baixar_ne(context, aba_sigef, processo, ne)
        cron.etapa("sei")
        ao_etapa("sei", dados)
        avisos = anexar_ne(context, processo, dados, nome_arvore)
    except BaseException as erro:
        texto = str(erro.code if isinstance(erro, SystemExit) else erro).strip()
        # Ctrl+C ou a janela fechada no meio (Encerrado, do app_janela): parou, não deu erro.
        parado = isinstance(erro, KeyboardInterrupt) or getattr(erro, "interromper_lote", False)
        cron.registrar("parado" if parado else "erro", dados, texto or type(erro).__name__)
        raise
    tempos = cron.registrar("ok", dados)
    return aba_sigef, avisos, tempos
