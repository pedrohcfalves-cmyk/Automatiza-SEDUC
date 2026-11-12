"""
Etapa Anexar Documento: baixa do SIGEF, em JPG, os quatro documentos de
TODOS os lançamentos que o próprio fluxo acabou de gerar -- Despesa
Certificada (CE), Nota de Lançamento (NL), Preparação de Pagamento (PP)
e Ordem Bancária (OB) -- e salva tudo na pasta do processo.

Mesma lógica do LBA (Listar -> Baixar -> Anexar), com os parâmetros do
Anexar Documentos (utils.py, sessão, nomes de arquivo, uma OB por
lançamento).

1) LISTAGEM -- com os números GERADOS pelo fluxo, nada digitado aqui
    Os números saem da lista de lançamentos (a MESMA de main.py,
    etapa_nl.py, etapa_pp.py e etapa_ob.py) e da sessão:

        CE  sessao["ce"]   uma só, de todo o processo   ("018705")
        NL  item["nl"]     uma por lançamento           ("066235")
        PP  item["pp"]     uma por lançamento           ("2026PP039778")
        OB  item["ob"]     uma por lançamento           ("2026OB136475")

    montar_listagem() junta isso numa tabela (mostrada no terminal antes
    de abrir o SIGEF), completa os prefixos ("066235" -> "2026NL066235"),
    agrupa as PPs pela OB que as pagou e já avisa o que estiver faltando
    (lançamento sem PP, PP sem NL, PP sem OB, PP repetida...).

    É essa MESMA listagem que manda no download e na colagem no SEI
    (etapa_sei2.py): o que não foi gerado pelo fluxo não é baixado nem
    anexado, e a tela do SIGEF só serve de CONFERÊNCIA -- se ela mostrar
    um número diferente do gerado, vira aviso na conferência final.

2) BAIXAR -- a ordem não é arbitrária (igual ao LBA)
    CE + PP  modo "ob" (padrão, o caminho do LBA): para cada OB gerada,
             pesquisa em "Listar Ordem Bancária", abre o detalhe dela e,
             na grade de PPs da OB, abre SÓ as PPs geradas pelo fluxo.
             De cada PP baixa a CE (só quando o número muda) e a própria
             PP. Isso também confere que a OB gerada paga mesmo aquela PP.
             Se a OB não aparecer na pesquisa (ou a PP não estiver na
             grade dela), a PP é baixada pelo modo "pp".
             modo "pp" (reserva): pesquisa a PP em "Listar Preparação de
             Pagamento" e abre direto. É também o caminho de quem não tem
             OB gerada.
    NL       DEPOIS do loop, pela tela "Listar Nota Lançamento
             Liquidação", na ABA PRINCIPAL (abrir a NL pelo campo da PP
             dá erro no próprio SIGEF).
    OB       POR ÚLTIMO, pela tela "Imprimir Ordem Bancária Conferência",
             também na ABA PRINCIPAL (mexer nela antes derrubaria a janela
             da PP de que o loop depende). Uma por OB distinta.

3) O QUE FICA PARA A ETAPA SEI (2)
    Cada lançamento ganha arquivos_ce / arquivos_nl / arquivos_pp /
    arquivos_ob (e o número de cada um). A sessão ganha grupos_ce e
    grupos_ob (uma entrada por CE / OB distinta), listagem_download,
    avisos_download e download_processo. É de lá que etapa_sei2.py lê.

ROBUSTEZ
    - retomada: o que já foi baixado (mesmo número, arquivo em disco) não
      é baixado de novo; se TUDO já estiver baixado, nem abre o SIGEF;
    - sessão do SIGEF expirada: pausa e pede novo login;
    - janela do SIGEF fechada no meio: recomeça sozinho até 3 vezes;
    - alert()/confirm() do SIGEF: fechado sozinho (sem derrubar o driver);
    - falha em um documento não impede os demais: vira aviso.

Ponto de entrada usado pelo main.py:
    executar_anexar_lote(context, processo, lancamentos) -> lancamentos
"""
import os
import re
from urllib.parse import urlparse

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from automacoes.anexar.automacao import interacao, utils
from automacoes.anexar.automacao.configuracoes import config_global, gestao_sem_zeros
from automacoes.geral import ano_sigef
from automacoes.anexar.automacao.utils import (
    PASTA_BASE,
    URL_SIGEF,
    URL_SIGEF_LISTAR_PP,
    carregar_sessao,
    nome_pasta_valido,
    obter_ou_criar_aba,
    pdf_para_jpg,
    perguntar_ou_reusar,
    registrar_detalhes_tecnicos,
    salvar_sessao,
)


# ---------------------------------------------------------------- SIGEF

# Tudo abaixo é derivado de URL_SIGEF_LISTAR_PP (utils.py): o domínio e o
# ano do SIGEF (SIGEF2026) mudam num lugar só -- trocar produção por
# homologação em utils.py continua valendo aqui.
_URL_BASE_SIGEF = URL_SIGEF_LISTAR_PP.split("/FIN/")[0]
DOMINIO_SIGEF = urlparse(URL_SIGEF_LISTAR_PP).netloc

TRECHO_URL_DETALHAR_PP = "FINDetalharPreparacaoPagamentoDespesaEmpenhada.aspx"
TRECHO_URL_DETALHAR_OB = "FINDetalharOrdemBancaria.aspx"

# "Listar Ordem Bancária" -- a tela de onde o LBA parte. utils.py ainda
# deixa URL_SIGEF_LISTAR_OB em branco; enquanto estiver assim, usa o mesmo
# endereço do LBA (confirmado em produção), no domínio/ano do utils.py.
URL_SIGEF_LISTAR_OB = (
    getattr(utils, "URL_SIGEF_LISTAR_OB", "")
    or _URL_BASE_SIGEF + "/FIN/FINListarOrdemBancaria.aspx?CdTransacao=175"
)

# Tela de onde a OB é impressa. É uma tela de PESQUISA, aberta na aba
# principal: recebe gestão + OB e o Imprimir dela abre a janela de
# formato, igual aos outros documentos.
URL_SIGEF_IMPRIMIR_OB_CONFERENCIA = (
    _URL_BASE_SIGEF + "/FIN/FINImprimirOrdemBancariaConferencia.aspx?CdTransacao=197"
)

# Tela de onde a NL é impressa. Também é uma tela de PESQUISA na aba
# principal: recebe ano + sequencial da NL, e o número na grade abre
# "Detalhar Nota Lançamento Liquidação", que tem o Imprimir.
URL_SIGEF_LISTAR_NL = (
    _URL_BASE_SIGEF + "/FIN/FINListarNotaLancamentoLiquidacao.aspx?CdTransacao=1495"
)

# Moldes usados só como RESERVA, para voltar a uma tela de detalhe quando
# o SIGEF desvia a janela. O normal é guardar a URL real que ele abriu --
# aí CdUnidadeGestora/CdGestao vêm dele, não daqui.
URL_SIGEF_DETALHAR_PP = (
    _URL_BASE_SIGEF + "/FIN/"
    + TRECHO_URL_DETALHAR_PP
    + "?CdUnidadeGestora={unidade_gestora}"
    + "&CdGestao={gestao}"
    + "&NuPreparacaoPagamento={pp}"
    + "&TituloTransacao=Listar%20Ordem%20Banc%E1ria"
    + "&NomePagina=FIN/FINListarOrdemBancaria.aspx?CdTransacao=175"
)

URL_SIGEF_DETALHAR_OB = (
    _URL_BASE_SIGEF + "/FIN/"
    + TRECHO_URL_DETALHAR_OB
    + "?CdUnidadeGestora={unidade_gestora}"
    + "&CdGestao={gestao}"
    + "&NuOrdemBancaria={ob}"
    + "&TituloTransacao=Listar%20Ordem%20Banc%E1ria"
    + "&NomePagina=FIN/FINListarOrdemBancaria.aspx?CdTransacao=175"
)



# Unidade Gestora e Gestão: as do Global ([G] no menu de configurações),
# as mesmas de CE, NL, PP e OB -- lidas na hora, pra valer a última escolha.
# O SIGEF escreve a gestão de dois jeitos nas próprias telas: "1" na URL
# de detalhe da PP e "00001" na da OB e nas telas de pesquisa.
def _unidade_gestora() -> str:
    return config_global()["unidade_gestora"]


def _gestao_pesquisa() -> str:
    return config_global()["gestao"]


def _gestao_url_pp() -> str:
    return gestao_sem_zeros(config_global()["gestao"])

# Situação usada pelo LBA na pesquisa de "Listar Ordem Bancária". Se a OB
# gerada agora ainda estiver em outra situação, a pesquisa é refeita sem
# esse filtro (ver _abrir_ob) e, não achando, a PP vai pelo modo "pp".
SITUACAO_OB = "10"

# Modos de listagem (ver o docstring do módulo).
MODO_OB = "ob"
MODO_PP = "pp"
MODO_LISTAGEM_PADRAO = MODO_OB

# '2026NL012345' -> ano '2026', sequencial '012345'.
REGEX_NL = re.compile(r"^\s*(\d{4})\s*NL\s*(\d+)\s*$", re.IGNORECASE)

# Valor em reais no formato do SIGEF (ex: "1.234,56").
REGEX_VALOR = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

# Quanto esperar por cada janela/download antes de desistir daquele
# documento (só dele -- os demais seguem).
TIMEOUT_NL_MS = 30000
TIMEOUT_OB_MS = 30000
# Grade de resultado de uma pesquisa (OB/PP). O SIGEF é ASP.NET WebForms:
# depois do networkidle a grade ou já está lá ou não vem mais.
TIMEOUT_GRADE_MS = 15000

# Quantas vezes o download recomeça sozinho quando o SIGEF fecha uma
# janela no meio (ver baixar_documentos).
TENTATIVAS_JANELA_FECHADA = 3


# ---------------------------------------------------- Números dos documentos


def _sequencial(numero: str) -> str:
    """'2026OB136475' -> '136475'. Sem prefixo de ano+sigla, devolve como veio."""
    return re.sub(r"^\d{4}\s*[A-Za-z]{2}\s*", "", (numero or "").strip())


def _ano_da_pp(pp: str) -> str:
    """'2026PP039778' -> '2026'. Sem prefixo, o ano corrente (o mesmo que a Etapa PP usa)."""
    achado = re.match(r"^(\d{4})PP", (pp or "").strip(), re.IGNORECASE)
    return achado.group(1) if achado else str(ano_sigef())


def _completar_numero(numero: str, sigla: str, ano: str) -> str:
    """
    Põe o prefixo de ano+sigla que faltar: '066235' -> '2026NL066235'.
    Número que já vem completo ('2026NL066235') fica como está.
    """
    numero = re.sub(r"\s+", "", (numero or "").strip().upper())
    if not numero:
        return ""
    if re.match(rf"^\d{{4}}{sigla}\d+$", numero):
        return numero
    apenas_digitos = re.sub(r"^\D+", "", numero)
    if not apenas_digitos:
        return ""
    return f"{ano}{sigla}{apenas_digitos}"


def _chave_numero(numero: str) -> str:
    """
    Chave para saber se dois textos são o MESMO documento, seja qual for
    o jeito de a tela escrever: '2026CE018705', '018705', '18705' e
    '018705/2026' viram todos '18705'.

    É o maior grupo de dígitos depois de tirar o prefixo ano+sigla (o
    sequencial tem 6 dígitos; o ano, 4), sem zeros à esquerda.
    """
    grupos = re.findall(r"\d+", _sequencial(numero))
    if not grupos:
        return ""
    maior = max(grupos, key=len)
    return str(int(maior))


def _mesmo_documento(a: str, b: str) -> bool:
    """'2026CE018705' e '018705' são o mesmo documento (ver _chave_numero)."""
    chave_a, chave_b = _chave_numero(a), _chave_numero(b)
    return bool(chave_a) and chave_a == chave_b


def _conferir_numero(rotulo: str, gerado: str, na_tela: str, pp: str, avisos: list) -> None:
    """
    Compara o número que o programa GEROU com o que a tela da PP mostra.
    Divergência não para nada -- vai para os avisos da conferência final.
    """
    if gerado and na_tela and not _mesmo_documento(gerado, na_tela):
        _avisar(
            avisos,
            f"{rotulo} da PP {pp}: o programa gerou {gerado}, mas a tela da PP mostra "
            f"{na_tela}. Confira qual está certa antes de assinar.",
        )


def _avisar(avisos: list, texto: str) -> None:
    """Guarda o aviso (sem repetir) e mostra na tela."""
    if texto not in avisos:
        avisos.append(texto)
    print(f"   ⚠️  {texto}")


def _valor_em_centavos(texto) -> int | None:
    """'1.234,56' / '123456' / 'R$ 1.234,56' -> 123456. None se não der."""
    texto = str(texto or "").replace("R$", "").strip()
    if not texto:
        return None
    if texto.isdigit():
        return int(texto)
    try:
        return round(float(texto.replace(".", "").replace(",", ".")) * 100)
    except ValueError:
        return None


# ------------------------------------------------------------ Listagem


def montar_listagem(lancamentos: list[dict], ce: str = None) -> dict:
    """
    Monta, só com os números GERADOS pelo fluxo, a lista do que vai ser
    baixado (e depois colado no SEI). Não toca no SIGEF.

    Devolve:
        {
          "ce":       CE gerada (como está na sessão) ou "",
          "itens":    [ {posicao, valor, valor_centavos, pp, nl, ob, item}, ... ]
                      -- só os lançamentos com PP, na ordem do fluxo,
                      sem PP repetida; NL e OB já com prefixo
                      ("2026NL066235", "2026OB136475");
          "por_ob":   {ob: [itens...]}, na ordem em que a OB aparece;
          "sem_ob":   [itens...] com PP mas sem OB gerada;
          "sem_pp":   [lançamentos...] sem PP (nada a baixar deles);
          "avisos":   [texto, ...] o que já se sabe que está faltando.
        }
    """
    listagem = {"ce": (ce or "").strip(), "itens": [], "por_ob": {}, "sem_ob": [], "sem_pp": [], "avisos": []}
    pps_vistas = {}

    for posicao, item in enumerate(lancamentos, start=1):
        valor = item.get("valor")
        pp = re.sub(r"\s+", "", (item.get("pp") or "").strip().upper())
        if not pp:
            listagem["sem_pp"].append(item)
            listagem["avisos"].append(
                f"Lançamento {posicao} (valor {valor}): sem PP gerada -- nada dele será baixado nem anexado."
            )
            continue

        chave_pp = _chave_numero(pp)
        if chave_pp in pps_vistas:
            listagem["avisos"].append(
                f"Lançamento {posicao} (valor {valor}): a PP {pp} já está no lançamento "
                f"{pps_vistas[chave_pp]} -- ela é baixada e anexada uma vez só."
            )
            continue
        pps_vistas[chave_pp] = posicao

        ano = _ano_da_pp(pp)
        nl = _completar_numero(item.get("nl"), "NL", ano)
        ob = _completar_numero(item.get("ob"), "OB", ano)
        linha = {
            "posicao": posicao,
            "valor": valor,
            "valor_centavos": _valor_em_centavos(item.get("valor_padronizado") or valor),
            "pp": pp,
            "nl": nl,
            "ob": ob,
            "item": item,
        }
        listagem["itens"].append(linha)

        if not nl:
            listagem["avisos"].append(
                f"PP {pp} (valor {valor}): sem NL gerada -- vou usar a NL que a tela da PP mostrar."
            )
        if ob:
            listagem["por_ob"].setdefault(ob, []).append(linha)
        else:
            listagem["sem_ob"].append(linha)
            listagem["avisos"].append(
                f"PP {pp} (valor {valor}): sem OB gerada -- baixo pela tela da PP e uso a OB que ela mostrar."
            )

    if listagem["itens"] and not listagem["ce"]:
        listagem["avisos"].append("Nenhuma CE gerada na sessão -- vou usar a CE que a tela de cada PP mostrar.")

    return listagem


def mostrar_listagem(listagem: dict, modo: str) -> None:
    """Imprime a tabela da listagem -- é o que vai ser baixado e anexado."""
    itens = listagem["itens"]
    print(f"\n{'=' * 78}")
    print(f"LISTAGEM -- {len(itens)} PP(s) gerada(s) pelo fluxo | CE {listagem['ce'] or '?'} | modo {modo.upper()}")
    print(f"{'=' * 78}")
    print(f"{'#':>3}  {'Valor':>12}  {'PP':<14}  {'NL':<14}  {'OB':<14}")
    print(f"{'-' * 78}")
    for linha in itens:
        print(
            f"{linha['posicao']:>3}  {str(linha['valor'] or '-'):>12}  {linha['pp']:<14}  "
            f"{(linha['nl'] or '-'):<14}  {(linha['ob'] or '-'):<14}"
        )
    print(f"{'-' * 78}")
    print(f"OBs distintas: {len(listagem['por_ob'])} | PPs sem OB: {len(listagem['sem_ob'])} | "
          f"lançamentos sem PP: {len(listagem['sem_pp'])}")
    for aviso in listagem["avisos"]:
        print(f"   ⚠️  {aviso}")
    print(f"{'=' * 78}")
    print("  Acima está a lista do que o programa vai baixar do SIGEF.")
    print("  Você não precisa fazer nada -- é só para conferir os números.")


def _resumo_listagem(listagem: dict) -> list[dict]:
    """A listagem em formato que dá pra gravar na sessão (sem o item inteiro)."""
    return [
        {chave: linha[chave] for chave in ("posicao", "valor", "pp", "nl", "ob")}
        for linha in listagem["itens"]
    ]


# ------------------------------------------------- Leitura das telas do SIGEF


def ler_valor_campo(locator) -> str:
    """
    Lê o texto de um campo, sem se importar se é um <input> (readonly,
    exibindo um número) ou um elemento comum (span, link).
    """
    try:
        valor = locator.input_value(timeout=1000)
    except Exception:
        valor = None
    if valor and valor.strip():
        return valor.strip()
    try:
        return (locator.inner_text(timeout=1000) or "").strip()
    except Exception:
        return ""


def campo_existe(pagina, seletor: str) -> bool:
    """
    True se `seletor` existir no HTML da página (mesmo que escondido).

    NÃO espera nada -- `.count()` confere o DOM na hora. Quem chama já
    esperou a página terminar de carregar (networkidle) e o SIGEF é tela
    clássica (ASP.NET WebForms): se o campo existe, já está no HTML.
    """
    try:
        return pagina.locator(seletor).count() > 0
    except PlaywrightError:
        return False


def numero_vinculado(pagina, seletor: str) -> str:
    """
    O número do documento vinculado à PP naquele campo (CE, NL ou OB), ou
    "" se não houver. Campo ausente e campo vazio (PP de pagamento
    devolvido) são o mesmo caso: não há documento para baixar.
    """
    if not campo_existe(pagina, seletor):
        return ""
    return ler_valor_campo(pagina.locator(seletor).first).strip()


def _existem(caminhos) -> bool:
    return bool(caminhos) and all(os.path.exists(c) for c in caminhos)


# ------------------------------------------------------- Janelas e sessão


def _tratador_dialogo(dialogo) -> None:
    """
    Fecha sozinho alert/confirm/prompt do navegador (igual ao LBA).

    Sem isso, um alert() do SIGEF ("sua sessão expirou...") fica sem
    resposta e o driver do Playwright pode quebrar fora de hora
    ("No dialog is showing"). alert é aceito; confirm/prompt são
    cancelados -- o mesmo que o Playwright já faz quando ninguém escuta,
    então nada muda no comportamento das outras etapas.
    """
    try:
        print(f"\n💬 Diálogo do navegador fechado sozinho: [{dialogo.type}] {dialogo.message}")
    except Exception:
        pass
    try:
        if dialogo.type == "alert":
            dialogo.accept()
        else:
            dialogo.dismiss()
    except Exception:
        pass


def instalar_tratador_dialogos(context):
    """
    Liga _tratador_dialogo() nas abas abertas e nas que ainda vão abrir.
    Devolve uma função que desliga tudo de novo (chamada no fim da etapa).
    """
    paginas = []

    def _ligar(pagina):
        try:
            pagina.on("dialog", _tratador_dialogo)
            paginas.append(pagina)
        except Exception:
            pass

    for pagina in list(context.pages):
        _ligar(pagina)
    context.on("page", _ligar)

    def desligar():
        try:
            context.remove_listener("page", _ligar)
        except Exception:
            pass
        for pagina in paginas:
            try:
                pagina.remove_listener("dialog", _tratador_dialogo)
            except Exception:
                pass

    return desligar


def fechar_janelas_sobrando(context, manter) -> None:
    """
    Fecha as janelas do SIGEF que sobraram de uma tentativa anterior
    (detalhe da OB, da PP, tela de formato...), menos `manter`.

    O SIGEF abre a PP numa janela COM NOME: se a da tentativa que caiu
    continua aberta, ele reaproveita essa em vez de abrir uma nova, e a
    automação fica esperando uma janela nova que nunca vem.
    """
    for pagina in list(context.pages):
        try:
            if pagina is manter or pagina.is_closed():
                continue
            if DOMINIO_SIGEF.lower() in (pagina.url or "").lower():
                pagina.close()
        except PlaywrightError:
            continue


def _fechar_janelas_novas(context, janelas_antes: set, manter=None) -> None:
    """Fecha o que abriu depois de `janelas_antes` -- limpeza de um passo que deu erro."""
    for pagina in set(context.pages) - janelas_antes:
        if pagina is manter:
            continue
        try:
            pagina.close()
        except PlaywrightError:
            pass


def _fechar(pagina) -> None:
    try:
        if pagina is not None and not pagina.is_closed():
            pagina.close()
    except PlaywrightError:
        pass


def _navegador_conectado(context) -> bool:
    try:
        return bool(context.browser and context.browser.is_connected())
    except Exception:
        return False


def _sessao_sigef_valida(aba_sigef) -> bool:
    """
    True se `aba_sigef` está mesmo na tela "Listar Preparação de Pagamento"
    (sessão ativa), False se ela caiu em outro lugar -- sinal de que a
    sessão do SIGEF expirou.
    """
    try:
        return campo_existe(aba_sigef, "#txtPrepPagSeq")
    except PlaywrightError:
        return False


def garantir_sessao_sigef(context, aba_sigef):
    """
    Navega `aba_sigef` pra "Listar Preparação de Pagamento" e confere se a
    sessão ainda está ativa. Se caiu (ou a aba fechou sozinha), pausa e
    pede pro usuário entrar de novo -- sem reabrir o Chrome nem perder o
    que já foi baixado.

    Devolve a aba do SIGEF pronta pra usar (pode ser uma aba NOVA).
    """
    if aba_sigef is None or aba_sigef.is_closed():
        aba_sigef = obter_ou_criar_aba(
            context, dominio=DOMINIO_SIGEF, url_navegacao=URL_SIGEF_LISTAR_PP
        )

    aba_sigef.bring_to_front()
    try:
        aba_sigef.goto(URL_SIGEF_LISTAR_PP)
        aba_sigef.wait_for_load_state("networkidle")
    except PlaywrightError:
        # A própria navegação pode ter fechado a aba (efeito do alert de
        # sessão expirada nalgumas versões do SIGEF).
        if aba_sigef.is_closed():
            print("   A aba do SIGEF fechou durante a navegação -- abrindo de novo.")
            aba_sigef = obter_ou_criar_aba(
                context, dominio=DOMINIO_SIGEF, url_navegacao=URL_SIGEF_LISTAR_PP
            )
        else:
            raise

    if _sessao_sigef_valida(aba_sigef):
        return aba_sigef

    aba_sigef.bring_to_front()
    aba_sigef.goto(URL_SIGEF)
    aba_sigef.wait_for_load_state("networkidle")

    print("\n🔐 O SIGEF DESCONECTOU (acontece quando passa muito tempo).")
    interacao.continuar(
        "O SIGEF desconectou",
        ["Acontece quando passa muito tempo. Nada foi perdido."],
        rotulo="Já entrei de novo no SIGEF — continuar",
        passos=[
            "Vá até o Chrome do programa, na aba do SIGEF.",
            "Entre de novo com seu usuário e senha.",
            "Volte para esta janela.",
        ],
        tom="atencao",
    )

    aba_sigef.bring_to_front()
    aba_sigef.goto(URL_SIGEF_LISTAR_PP)
    aba_sigef.wait_for_load_state("networkidle")

    if not _sessao_sigef_valida(aba_sigef):
        raise SystemExit(
            "\n❌ Mesmo depois de confirmar o login, a tela de 'Listar "
            "Preparação de Pagamento' não apareceu. Confira a aba do SIGEF "
            "-- se ela mostrar alguma mensagem de erro, resolva na tela e "
            "rode de novo (o que já foi baixado continua salvo na sessão).\n"
        )

    return aba_sigef


# ------------------------------------------------------------ Impressão


def _baixar_relatorio(
    context, pagina_detalhe, pasta_destino: str, nome_arquivo: str, nome_temp: str,
    timeout_ms: int = None, erro_sem_janela: str = None,
) -> list[str]:
    """
    A partir de uma tela de detalhe já aberta (Despesa Certificada, Nota
    de Lançamento, Preparação de Pagamento -- ou a tela de Conferência da
    OB --, todas com o mesmo botão "Imprimir"): clica em Imprimir,
    escolhe o formato PDF, baixa o relatório, converte pra JPG na
    `pasta_destino` e apaga o PDF temporário. Devolve os JPGs (um por
    página).

    Usa o botão pelo TITLE (`a[title="Gerar Relatório"]`) e não pelo id:
    o id bate em dois elementos (o <a> e o <img> de dentro dele) e o
    Playwright para com "strict mode violation".

    Fecha só a janela de formato (aberta aqui); `pagina_detalhe` continua
    aberta, porque quem chamou pode precisar dela.
    """
    opcoes = {"timeout": timeout_ms} if timeout_ms else {}

    try:
        with context.expect_page(**opcoes) as pagina_formato_info:
            pagina_detalhe.locator('a[title="Gerar Relatório"]').first.click(**opcoes)
    except PlaywrightTimeoutError:
        if erro_sem_janela:
            raise SystemExit(erro_sem_janela) from None
        raise

    pagina_formato = pagina_formato_info.value
    pagina_formato.wait_for_load_state("networkidle")

    caminho_pdf_temp = os.path.join(pasta_destino, nome_temp)
    try:
        with context.expect_event("download", **opcoes) as download_info:
            pagina_formato.locator(
                'img[alt="Imprime Arquivo Formato PostScript (.pdf)"]'
            ).first.click(**opcoes)

        download_info.value.save_as(caminho_pdf_temp)
        novos_jpg = pdf_para_jpg(caminho_pdf_temp, pasta_destino, nome_arquivo=nome_arquivo)
    finally:
        if os.path.exists(caminho_pdf_temp):
            os.remove(caminho_pdf_temp)
        _fechar(pagina_formato)

    print(f"   JPG pronto: {[os.path.basename(c) for c in novos_jpg]}")
    return novos_jpg


# ----------------------------------------------------- CE + PP (uma PP aberta)


def _url_detalhe_pp(pagina_pp, pp: str) -> str:
    """URL real da tela da PP (pra voltar a ela) ou o molde de reserva."""
    url_pp = pagina_pp.url or ""
    if TRECHO_URL_DETALHAR_PP.lower() in url_pp.lower() and _sequencial(pp).lower() in url_pp.lower():
        return url_pp
    return URL_SIGEF_DETALHAR_PP.format(unidade_gestora=_unidade_gestora(), gestao=_gestao_url_pp(), pp=pp)


def _baixar_da_tela_da_pp(
    context, pagina_pp, pasta_destino: str, linha: dict, ce_gerada: str,
    ce_baixadas: dict, avisos: list,
) -> None:
    """
    Com a tela "Detalhar Preparação Pagamento Despesa Empenhada" JÁ
    ABERTA (venha ela da grade da OB ou de "Listar PP"): confere os
    números da tela com os gerados, baixa a CE (só se ainda não foi
    baixada) e a própria PP, e anota no lançamento qual NL e qual OB
    valem para ele -- as duas são baixadas depois, na aba principal.

    Levanta PlaywrightError/SystemExit se algo falhar; quem chama decide.
    """
    item, pp = linha["item"], linha["pp"]
    ano = _ano_da_pp(pp)
    url_pp = _url_detalhe_pp(pagina_pp, pp)

    # Os três números que a tela mostra, lidos ANTES de clicar em
    # qualquer coisa (a janela pode ser desviada pelo SIGEF depois).
    ce_tela = numero_vinculado(pagina_pp, "#txtNuDespesaCertificada")
    nl_tela = numero_vinculado(pagina_pp, "#txtNotaLancamento")
    ob_tela = numero_vinculado(pagina_pp, "#txtNuOrdemBancaria")

    # ---- NL e OB: os GERADOS mandam; a tela só confere (e cobre o que
    #      o fluxo não gerou) ----
    item["pp_dos_numeros"] = pp   # de qual PP são o numero_nl / numero_ob abaixo
    _conferir_numero("NL", linha["nl"], nl_tela, pp, avisos)
    item["numero_nl"] = linha["nl"] or _completar_numero(nl_tela, "NL", ano) or None
    if item["numero_nl"]:
        print(f"   📝 Nota de Lançamento {item['numero_nl']}: baixo depois, pela tela de NLs.")
    else:
        print(f"   ⏭️  PP {pp} não tem Nota de Lançamento -- pulando a NL.")

    _conferir_numero("OB", linha["ob"], ob_tela, pp, avisos)
    item["numero_ob"] = linha["ob"] or _completar_numero(ob_tela, "OB", ano) or None
    if item["numero_ob"]:
        print(f"   🏦 Ordem Bancária {item['numero_ob']}: baixo no fim, pela tela de Conferência.")
    else:
        print(f"   ⚠️  PP {pp} não tem Ordem Bancária -- pulando a OB.")

    # ---- CE: o número que vale é o GERADO; a tela diz se esta PP está
    #      mesmo vinculada a ela (campo vazio = pagamento devolvido) ----
    if not ce_tela:
        print(f"   ⏭️  PP {pp} não tem Despesa Certificada vinculada na tela -- pulando a CE.")
        item["numero_ce"], item["arquivos_ce"] = None, []
    else:
        _conferir_numero("CE", ce_gerada, ce_tela, pp, avisos)
        numero_ce = ce_gerada if (ce_gerada and _mesmo_documento(ce_gerada, ce_tela)) else ce_tela
        chave_ce = _chave_numero(numero_ce) or numero_ce

        if chave_ce in ce_baixadas:
            print(
                f"   ↩️  Despesa Certificada '{numero_ce}' já baixada -- reaproveitando "
                f"{len(ce_baixadas[chave_ce])} arquivo(s), sem baixar de novo."
            )
        else:
            with context.expect_page() as pagina_ce_info:
                pagina_pp.locator("#txtNuDespesaCertificada").first.click()

            pagina_ce = pagina_ce_info.value
            pagina_ce.wait_for_load_state("networkidle")
            try:
                # O nome leva o número da CE: uma CE diferente não pode
                # sobrescrever o JPG de outra.
                ce_baixadas[chave_ce] = _baixar_relatorio(
                    context, pagina_ce, pasta_destino,
                    f"Despesa Certificada - CE {nome_pasta_valido(numero_ce)}", "temp_ce.pdf",
                )
            finally:
                _fechar(pagina_ce)

            print(f"   📄 Despesa Certificada '{numero_ce}': {len(ce_baixadas[chave_ce])} JPG(s)")

            # ⚠️ Ao fechar a tela da CE, o SIGEF pode desviar a janela da
            #    PP pra outra tela (ex: "Detalhar Ordem Bancária"), onde o
            #    Imprimir da PP não existe. Sem voltar aqui, o bloco
            #    seguinte falha.
            pagina_pp.bring_to_front()
            if TRECHO_URL_DETALHAR_PP.lower() not in (pagina_pp.url or "").lower():
                print(f"   ↩️  janela saiu da PP {pp} -- voltando pra tela de detalhe dela")
                pagina_pp.goto(url_pp)
            pagina_pp.wait_for_load_state("networkidle")

        item["numero_ce"], item["arquivos_ce"] = numero_ce, ce_baixadas[chave_ce]

    # ---- A própria PP: a tela já está aberta, começa no Imprimir dela ----
    item["arquivos_pp"] = _baixar_relatorio(
        context, pagina_pp, pasta_destino,
        f"Preparação de Pagamento - PP {pp}", "temp_pp.pdf",
    )
    item["pp_baixada"] = pp
    print(f"   📄 Preparação de Pagamento: {len(item['arquivos_pp'])} JPG(s)")


# ------------------------------------------------- Modo "pp": Listar PP


def _abrir_pp(context, aba_sigef, pp: str):
    """
    Localiza a PP na tela "Listar Preparação de Pagamento" (gestão + número
    sequencial) e clica nela: abre "Detalhar Preparação Pagamento Despesa
    Empenhada" numa janela nova, que é devolvida.

    Só abre a linha da PP certa: a pesquisa é pelo sequencial e pode
    trazer PPs de outro ano. Se a grade tiver UMA linha só (o normal), é
    ela; com várias e nenhuma exata, para em vez de baixar a PP errada.
    """
    aba_sigef.bring_to_front()
    aba_sigef.goto(URL_SIGEF_LISTAR_PP)
    aba_sigef.wait_for_load_state("networkidle")

    # O campo #txtPrepPagSeq só quer o número sequencial, sem o prefixo de
    # ano+"PP" ("2026PP039777" -> "039777").
    pp_sequencial = _sequencial(pp)

    aba_sigef.locator("#txtGestao_SIGEFPesquisa").fill(_gestao_pesquisa())
    aba_sigef.locator("#txtPrepPagSeq").fill(pp_sequencial)
    aba_sigef.locator("#btnConfirmar").click()
    aba_sigef.wait_for_load_state("networkidle")

    linhas = aba_sigef.locator("#dtgPP tr.GridLinhaPar, #dtgPP tr.GridLinhaImpar")
    try:
        linhas.first.wait_for(state="visible", timeout=TIMEOUT_GRADE_MS)
    except PlaywrightTimeoutError:
        raise SystemExit(
            f"a pesquisa não trouxe a PP {pp} na tela 'Listar Preparação de Pagamento'"
        ) from None

    padroes = [re.compile(rf"^\s*{re.escape(pp)}\s*$", re.IGNORECASE)]
    if pp != pp_sequencial:
        padroes.append(re.compile(rf"^\s*{re.escape(pp_sequencial)}\s*$"))

    celula = None
    for padrao in padroes:
        candidatas = aba_sigef.locator("#dtgPP td.GridLink").filter(has_text=padrao)
        if candidatas.count() > 0:
            celula = candidatas.first
            break
    if celula is None:
        if linhas.count() != 1:
            encontradas = [t.strip() for t in aba_sigef.locator("#dtgPP td.GridLink").all_inner_texts()]
            raise SystemExit(
                f"a grade de 'Listar Preparação de Pagamento' não tem a PP {pp} "
                f"(veio: {', '.join(encontradas) or 'nada'})"
            )
        print(f"   ⚠️  O texto da grade não bate exatamente com a PP {pp} -- abrindo a única linha que veio.")
        celula = linhas.first.locator("td.GridLink").first

    with context.expect_page() as pagina_pp_info:
        celula.click()

    pagina_pp = pagina_pp_info.value
    pagina_pp.wait_for_load_state("networkidle")
    return pagina_pp


def _baixar_pela_pp(
    context, aba_sigef, pasta_destino: str, linha: dict, ce_gerada: str,
    ce_baixadas: dict, avisos: list,
) -> None:
    """Modo "pp": abre a PP por "Listar PP" e baixa a CE e a PP dela."""
    pagina_pp = _abrir_pp(context, aba_sigef, linha["pp"])
    try:
        _baixar_da_tela_da_pp(context, pagina_pp, pasta_destino, linha, ce_gerada, ce_baixadas, avisos)
        linha["item"]["rota_listagem"] = "Listar PP"
    finally:
        _fechar(pagina_pp)


# ----------------------------------------- Modo "ob": Listar OB (igual ao LBA)


def _selecionar_situacao(aba_sigef, situacao) -> None:
    """
    Escolhe a situação da OB na pesquisa. `situacao` None = "todas": a
    opção cujo texto começa com "Tod" (Todas/Todos), ou a primeira em
    branco; se não houver nenhuma das duas, deixa como está.
    """
    combo = aba_sigef.locator("#cboSituacaoOB")
    if combo.count() == 0:
        return
    if situacao is not None:
        combo.select_option(situacao)
        return
    opcoes = combo.locator("option")
    for i in range(opcoes.count()):
        texto = (opcoes.nth(i).inner_text() or "").strip()
        valor = opcoes.nth(i).get_attribute("value") or ""
        if re.match(r"^tod", texto, re.IGNORECASE) or (not texto and not valor):
            combo.select_option(index=i)
            return


def _abrir_ob(context, aba_sigef, ob: str):
    """
    Pesquisa a OB em "Listar Ordem Bancária" (LBA, passo 2-3) e abre o
    detalhe dela. Tenta primeiro com a situação do LBA (SITUACAO_OB); a OB
    acabou de ser gerada e pode estar em outra situação, então tenta de
    novo sem esse filtro antes de desistir.

    Devolve (pagina_ob, url_ob, ob_completa).
    Levanta SystemExit se a OB não for encontrada.
    """
    ob = (ob or "").strip().upper()
    ob_sequencial = _sequencial(ob)
    if ob_sequencial != ob:
        padrao_ob = re.compile(rf"^\s*{re.escape(ob)}\s*$", re.IGNORECASE)
    else:
        padrao_ob = re.compile(rf"^\s*(\d{{4}}OB)?{re.escape(ob_sequencial)}\s*$", re.IGNORECASE)

    encontradas = []
    for situacao in (SITUACAO_OB, None):
        aba_sigef.bring_to_front()
        aba_sigef.goto(URL_SIGEF_LISTAR_OB)
        aba_sigef.wait_for_load_state("networkidle")

        aba_sigef.locator("#txtCdGestao_SIGEFPesquisa").fill(_gestao_pesquisa())
        aba_sigef.locator("#txtOBNumero").fill(ob_sequencial)
        try:
            _selecionar_situacao(aba_sigef, situacao)
        except PlaywrightError as erro:
            print(f"   ⚠️  Não consegui escolher a situação da OB ({erro}) -- pesquisando assim mesmo.")
        aba_sigef.locator("#btnConfirmar").click()
        aba_sigef.wait_for_load_state("networkidle")

        grade_ob = aba_sigef.locator("#dtgListarOrdemBancaria")
        try:
            grade_ob.wait_for(state="visible", timeout=TIMEOUT_GRADE_MS)
        except PlaywrightTimeoutError:
            continue

        celulas_ob = grade_ob.locator("td.GridLink").filter(has_text=padrao_ob)
        if celulas_ob.count() == 0:
            encontradas = [t.strip() for t in grade_ob.locator("td.GridLink").all_inner_texts()]
            continue
        if celulas_ob.count() > 1:
            print(f"   ⚠️  {celulas_ob.count()} linhas batem com a OB {ob} -- usando a primeira.")

        # A OB completa sai da grade, não do que foi digitado.
        ob_completa = celulas_ob.first.inner_text().strip() or ob

        with context.expect_page() as pagina_ob_info:
            celulas_ob.first.click()
        pagina_ob = pagina_ob_info.value
        pagina_ob.wait_for_load_state("networkidle")

        url_ob = pagina_ob.url or ""
        if TRECHO_URL_DETALHAR_OB.lower() not in url_ob.lower():
            url_ob = URL_SIGEF_DETALHAR_OB.format(
                unidade_gestora=_unidade_gestora(), gestao=_gestao_pesquisa(), ob=ob_completa
            )
        return pagina_ob, url_ob, ob_completa

    raise SystemExit(
        f"a OB {ob} não apareceu em 'Listar Ordem Bancária' "
        f"(veio: {', '.join(encontradas) or 'nada'})"
    )


def _ler_grade_pps(pagina_ob) -> list[tuple[str, str | None]]:
    """
    Lê a grade de PPs da OB (#grdPreparacaoPagamento): [(pp, valor), ...].

    A busca é por 'a.GridLink' e não pela classe da linha porque as
    tabelinhas de Fonte Recurso dentro de cada linha usam as MESMAS
    classes GridLinhaPar/GridLinhaImpar. Lê tudo AGORA: a grade é
    redesenhada a cada volta do loop.
    """
    grade_pp = pagina_ob.locator("#grdPreparacaoPagamento")
    try:
        # "attached" e não "visible": uma grade VAZIA não tem altura, mas
        # existe -- aí cada PP gerada vira aviso "não está na grade da OB".
        grade_pp.wait_for(state="attached", timeout=TIMEOUT_GRADE_MS)
    except PlaywrightTimeoutError:
        raise SystemExit("a OB não tem grade de Preparações de Pagamento (#grdPreparacaoPagamento)") from None

    links_pp = grade_pp.locator("a.GridLink")
    pps_da_grade = []
    for i in range(links_pp.count()):
        link = links_pp.nth(i)
        numero = (link.inner_text() or "").strip()
        if not numero:
            continue
        # Valor da linha: o último número em formato de dinheiro do <tr>.
        # CNPJ e fonte de recurso não têm vírgula decimal, então não batem.
        valor_linha = None
        try:
            achados = REGEX_VALOR.findall(link.locator("xpath=ancestor::tr[1]").inner_text())
            if achados:
                valor_linha = achados[-1]
        except Exception:
            pass
        pps_da_grade.append((numero, valor_linha))
    return pps_da_grade


def _baixar_pela_ob(
    context, aba_sigef, pasta_destino: str, ob: str, linhas: list[dict], ce_gerada: str,
    ce_baixadas: dict, avisos: list, erro_para_valer,
) -> list[dict]:
    """
    Modo "ob" (o caminho do LBA): abre a OB gerada, e na grade de PPs dela
    abre SÓ as PPs geradas pelo fluxo que essa OB paga, baixando a CE e a
    PP de cada uma.

    Devolve as linhas que NÃO foram resolvidas por aqui (OB não achada,
    PP fora da grade, erro no meio) -- quem chama tenta pelo modo "pp".
    """
    try:
        pagina_ob, url_ob, ob_completa = _abrir_ob(context, aba_sigef, ob)
    except (PlaywrightError, SystemExit) as erro:
        if erro_para_valer(erro):
            raise
        print(f"   ↪️  OB {ob}: {_detalhe_do_erro(erro)} -- vou pela tela Listar PP.")
        return list(linhas)

    pendentes = []
    try:
        try:
            pps_da_grade = _ler_grade_pps(pagina_ob)
        except (PlaywrightError, SystemExit) as erro:
            if erro_para_valer(erro):
                raise
            print(f"   ↪️  OB {ob_completa}: {_detalhe_do_erro(erro)} -- vou pela tela Listar PP.")
            return list(linhas)

        print(f"🔎 OB {ob_completa}: {len(pps_da_grade)} PP(s) na grade: "
              + ", ".join(f"{numero} ({valor})" for numero, valor in pps_da_grade))

        geradas = {_chave_numero(linha["pp"]) for linha in linhas}
        for numero, _valor in pps_da_grade:
            if _chave_numero(numero) not in geradas:
                print(f"   ⏭️  PP {numero} está na OB, mas não foi gerada por este fluxo -- não baixo.")

        for posicao, linha in enumerate(linhas):
            pp = linha["pp"]

            # A janela da OB caiu numa volta anterior: reabre; não dando,
            # o resto vai pelo modo "pp".
            if pagina_ob is None or pagina_ob.is_closed():
                try:
                    pagina_ob, url_ob, ob_completa = _abrir_ob(context, aba_sigef, ob)
                except (PlaywrightError, SystemExit) as erro:
                    if erro_para_valer(erro):
                        raise
                    print(f"   ↪️  Não consegui reabrir a OB {ob} ({_detalhe_do_erro(erro)}) -- o resto vai pela tela Listar PP.")
                    pagina_ob = None
                    pendentes.extend(linhas[posicao:])
                    break

            na_grade = [(n, v) for n, v in pps_da_grade if _mesmo_documento(n, pp)]
            if not na_grade:
                _avisar(
                    avisos,
                    f"PP {pp}: não está na grade da OB {ob_completa} gerada para ela -- "
                    "confira se a OB paga mesmo esta PP (baixei a PP pela tela Listar PP).",
                )
                pendentes.append(linha)
                continue

            numero_grade, valor_grade = na_grade[0]
            centavos_grade = _valor_em_centavos(valor_grade)
            if linha["valor_centavos"] is not None and centavos_grade is not None \
                    and centavos_grade != linha["valor_centavos"]:
                _avisar(
                    avisos,
                    f"PP {pp}: na OB {ob_completa} o valor é {valor_grade}, mas o lançamento "
                    f"gerado é de {linha['valor']}. Confira antes de assinar.",
                )

            print(f"\n▶️  PP {pp} (valor {linha['valor']}) pela OB {ob_completa}")
            interacao.andamento(f"Baixando a PP {pp} e a CE (valor R$ {linha['valor']})")
            janelas_antes = set(context.pages)
            pagina_pp = None
            try:
                # Reencontra a linha pelo NÚMERO, não por posição: a grade
                # pode ter sido redesenhada na volta anterior.
                pagina_ob.bring_to_front()
                link_pp = pagina_ob.locator("#grdPreparacaoPagamento a.GridLink").filter(
                    has_text=re.compile(rf"^\s*{re.escape(numero_grade)}\s*$")
                ).first
                with context.expect_page() as pagina_pp_info:
                    link_pp.click()
                pagina_pp = pagina_pp_info.value
                pagina_pp.wait_for_load_state("networkidle")

                _baixar_da_tela_da_pp(
                    context, pagina_pp, pasta_destino, linha, ce_gerada, ce_baixadas, avisos
                )
                linha["item"]["rota_listagem"] = "Listar OB"
                print(f"✅ PP {pp}: CE e PP baixadas (pela OB)")
            except (PlaywrightError, SystemExit) as erro:
                if erro_para_valer(erro):
                    raise
                print(f"   ↪️  PP {pp} deu erro pela OB ({_detalhe_do_erro(erro)}) -- tento pela tela Listar PP.")
                _fechar_janelas_novas(context, janelas_antes, manter=pagina_ob)
                linha["item"].pop("pp_baixada", None)
                pendentes.append(linha)
            finally:
                _fechar(pagina_pp)

            # Volta pra grade da OB (o SIGEF pode ter desviado a janela).
            # Se ela fechou, a próxima volta reabre.
            if not pagina_ob.is_closed():
                try:
                    pagina_ob.bring_to_front()
                    if TRECHO_URL_DETALHAR_OB.lower() not in (pagina_ob.url or "").lower():
                        print(f"   ↩️  voltando pra grade da OB {ob_completa}")
                        pagina_ob.goto(url_ob)
                    pagina_ob.wait_for_load_state("networkidle")
                except PlaywrightError as erro:
                    if erro_para_valer(erro):
                        raise
                    _fechar(pagina_ob)
    finally:
        _fechar(pagina_ob)

    return pendentes


# ---------------------------------------------------------------- NL


def _baixar_nl(context, aba_sigef, pasta_destino: str, pp: str, numero_nl: str) -> list[str]:
    """
    Baixa a Nota de Lançamento `numero_nl` (ex: '2026NL012345') e devolve
    os JPGs. Levanta PlaywrightError ou SystemExit se o SIGEF não
    colaborar -- quem chama decide pular só esta NL.

    ⚠️ NÃO abre a NL pelo campo #txtNotaLancamento da PP: por ali o
       próprio SIGEF dá erro. Vai pela tela de pesquisa "Listar Nota
       Lançamento Liquidação", na aba principal.
    """
    achado = REGEX_NL.match(numero_nl or "")
    if not achado:
        raise SystemExit(f"número da NL fora do padrão: '{numero_nl}'")
    ano, sequencial = achado.group(1), achado.group(2)
    numero_completo = f"{ano}NL{sequencial}"

    aba_sigef.bring_to_front()
    aba_sigef.goto(URL_SIGEF_LISTAR_NL)
    aba_sigef.wait_for_load_state("networkidle")

    # UG e gestão costumam vir preenchidas; só mexe se estiverem diferentes
    # (trocar a UG dispara recarga da tela no SIGEF).
    unidade_gestora, gestao = _unidade_gestora(), _gestao_pesquisa()
    campo_ug = aba_sigef.locator("#txtUnidadeGestora")
    if ler_valor_campo(campo_ug).strip() != unidade_gestora:
        campo_ug.fill(unidade_gestora)
    campo_gestao = aba_sigef.locator("#txtGestao_SIGEFPesquisa")
    if ler_valor_campo(campo_gestao).strip() != gestao:
        campo_gestao.fill(gestao)

    aba_sigef.locator("#txtNuNotaLancamentoAno").fill(ano)
    aba_sigef.locator("#txtNuNotaLancamento").fill(sequencial)
    aba_sigef.locator("#btnPesquisar").click()
    aba_sigef.wait_for_load_state("networkidle")

    # A grade pode trazer outras NLs junto: clica só na linha exata.
    celula_nl = aba_sigef.locator("#dtgNotaLancamento td.GridLink").filter(
        has_text=re.compile(rf"^\s*{re.escape(numero_completo)}\s*$", re.IGNORECASE)
    ).first
    try:
        celula_nl.wait_for(state="visible", timeout=TIMEOUT_NL_MS)
    except PlaywrightTimeoutError:
        raise SystemExit(f"a pesquisa não trouxe a {numero_completo} na grade") from None

    with context.expect_page(timeout=TIMEOUT_NL_MS) as pagina_nl_info:
        celula_nl.click()

    pagina_nl = pagina_nl_info.value
    pagina_nl.wait_for_load_state("networkidle")

    try:
        # O nome leva a PP junto: uma NL não pode sobrescrever a de outra.
        return _baixar_relatorio(
            context, pagina_nl, pasta_destino,
            f"Nota de Lançamento - PP {pp}", "temp_nl.pdf", timeout_ms=TIMEOUT_NL_MS,
        )
    finally:
        _fechar(pagina_nl)


# ---------------------------------------------------------------- OB


def _baixar_ob(context, aba_sigef, pasta_destino: str, ob_completa: str) -> list[str]:
    """
    Baixa a Ordem Bancária `ob_completa` (ex: '2026OB136475') pela tela de
    Conferência, na aba principal, e devolve os JPGs. Levanta
    PlaywrightError ou SystemExit se o SIGEF não colaborar.
    """
    ob_sequencial = _sequencial(ob_completa)

    aba_sigef.bring_to_front()
    aba_sigef.goto(URL_SIGEF_IMPRIMIR_OB_CONFERENCIA)
    aba_sigef.wait_for_load_state("networkidle")

    gestao = _gestao_pesquisa()
    aba_sigef.locator("#txtCdGestao_SIGEFPesquisa").fill(gestao)

    # ⚠️ Este campo recusa '2026OB136475' e só aceita o sequencial
    #    ('136475') -- confirmado ao vivo.
    #
    # A tela é um intervalo: o fim leva a MESMA OB de propósito. Em
    # branco, o SIGEF imprimiria da OB pesquisada em diante.
    aba_sigef.locator("#txtOrdemBancariaAInicio_SIGEFPesquisa").fill(ob_sequencial)

    campo_ob_fim = aba_sigef.locator("#txtOrdemBancariaAFim_SIGEFPesquisa")
    if campo_ob_fim.count() > 0:
        campo_ob_fim.fill(ob_sequencial)

    print(f"   🔎 Pesquisando a OB como '{ob_sequencial}' (gestão {gestao})")

    return _baixar_relatorio(
        context, aba_sigef, pasta_destino, f"Ordem Bancária - OB {ob_completa}", "temp_ob.pdf",
        timeout_ms=TIMEOUT_OB_MS,
        erro_sem_janela=(
            f"❌ Cliquei em Imprimir na tela de Conferência pra OB {ob_completa} "
            f"(pesquisada como '{ob_sequencial}', gestão {gestao}), mas a "
            "janela 'Selecione o tipo de arquivo' não abriu. Olhe a tela do SIGEF que "
            "ficou aberta: se ela mostrar alguma crítica, é o número ou a gestão que não bateram."
        ),
    )


# ------------------------------------------------------------- Download


def _detalhe_do_erro(erro: BaseException) -> str:
    linhas = str(getattr(erro, "code", None) or erro).strip().splitlines()
    return linhas[0] if linhas else type(erro).__name__


def _montar_grupos(lancamentos: list[dict], chave_numero: str, chave_arquivos: str) -> list[tuple]:
    """
    Uma entrada (número, [JPGs]) por documento DISTINTO -- a mesma CE (ou a
    mesma OB) usada por várias PPs entra uma vez só, na ordem em que apareceu.
    """
    grupos, vistos = [], set()
    for item in lancamentos:
        numero, arquivos = item.get(chave_numero), item.get(chave_arquivos)
        chave = _chave_numero(numero) or numero
        if numero and arquivos and chave not in vistos:
            vistos.add(chave)
            grupos.append((numero, list(arquivos)))
    return grupos


def _limpar_baixado_velho(item: dict) -> None:
    """
    Tira do lançamento o que foi baixado para OUTRO número. Acontece quando
    uma CE nova gera NL/PP/OB novas (main.py só apaga os números, não os
    arquivos): sem isso, um JPG da CE ou da OB antiga entraria no pacote.
    """
    pp = item.get("pp")
    if item.get("pp_baixada") != pp:
        for chave in ("pp_baixada", "arquivos_pp", "numero_ce", "arquivos_ce", "rota_listagem"):
            item.pop(chave, None)

    # NL e OB anotadas para OUTRA PP (a PP foi refeita): não valem mais.
    if item.get("pp_dos_numeros") not in (None, pp):
        for chave in ("pp_dos_numeros", "numero_nl", "arquivos_nl", "nl_baixada",
                      "numero_ob", "arquivos_ob", "ob_baixada"):
            item.pop(chave, None)

    ano = _ano_da_pp(pp)
    for chave_gerada, sigla, chave_numero, chave_arquivos, chave_baixada in (
        ("nl", "NL", "numero_nl", "arquivos_nl", "nl_baixada"),
        ("ob", "OB", "numero_ob", "arquivos_ob", "ob_baixada"),
    ):
        gerada = _completar_numero(item.get(chave_gerada), sigla, ano)
        if gerada and item.get(chave_numero) not in (None, gerada):
            for chave in (chave_numero, chave_arquivos, chave_baixada):
                item.pop(chave, None)


def _limpar_ce_velha(item: dict, ce_gerada: str) -> None:
    """A CE baixada antes é de OUTRA CE (a CE foi refeita): baixa a nova."""
    if ce_gerada and item.get("numero_ce") and not _mesmo_documento(item["numero_ce"], ce_gerada):
        item.pop("numero_ce", None)
        item.pop("arquivos_ce", None)
        item.pop("pp_baixada", None)


def _atualizar_item(item: dict) -> None:
    """
    Refaz `arquivos_anexar` (CE + NL + PP + OB, achatado, só para o
    resumo) e `anexo_baixado`: True quando a PP foi baixada e não falta
    nem a NL nem a OB que este lançamento tem.
    """
    item["arquivos_anexar"] = (
        list(item.get("arquivos_ce") or []) + list(item.get("arquivos_nl") or [])
        + list(item.get("arquivos_pp") or []) + list(item.get("arquivos_ob") or [])
    )
    item["anexo_baixado"] = bool(
        item.get("arquivos_pp")
        and (not item.get("numero_nl") or item.get("arquivos_nl"))
        and (not item.get("numero_ob") or item.get("arquivos_ob"))
    )


def _ce_e_pp_prontas(item: dict) -> bool:
    return bool(
        item.get("pp_baixada") == item.get("pp") and _existem(item.get("arquivos_pp"))
        and (not item.get("numero_ce") or _existem(item.get("arquivos_ce")))
    )


def _tudo_pronto(item: dict) -> bool:
    """Este lançamento já tem CE, PP, NL e OB baixadas, com os números de agora."""
    return bool(
        _ce_e_pp_prontas(item)
        and item.get("pp_dos_numeros") == item.get("pp")
        and (not item.get("numero_nl") or (item.get("nl_baixada") == item.get("numero_nl")
                                           and _existem(item.get("arquivos_nl"))))
        and (not item.get("numero_ob") or (item.get("ob_baixada") == item.get("numero_ob")
                                           and _existem(item.get("arquivos_ob"))))
    )


def baixar_documentos(
    context,
    aba_sigef,
    processo: str,
    lancamentos: list[dict],
    ce: str = None,
    pasta_base: str = PASTA_BASE,
    salvar_na_sessao: bool = True,
    modo: str = MODO_LISTAGEM_PADRAO,
) -> dict:
    """
    Igual a _baixar_documentos_uma_vez(), mas recomeça sozinho quando uma
    janela do SIGEF fecha no meio ("Target page, context or browser has
    been closed").

    Recomeçar aqui é seguro: nada foi anexado no SEI ainda, o que já foi
    baixado é reaproveitado e garantir_sessao_sigef() reabre a aba do
    SIGEF se foi ela que fechou. Na última tentativa o erro de janela não
    recomeça mais: vira aviso do lançamento, como qualquer outro erro.
    """
    desligar_dialogos = instalar_tratador_dialogos(context)
    try:
        for tentativa in range(1, TENTATIVAS_JANELA_FECHADA + 1):
            try:
                return _baixar_documentos_uma_vez(
                    context, aba_sigef, processo, lancamentos, ce, pasta_base, salvar_na_sessao,
                    ultima_tentativa=(tentativa == TENTATIVAS_JANELA_FECHADA), modo=modo,
                )
            except PlaywrightError as erro:
                if "has been closed" not in str(erro) or tentativa == TENTATIVAS_JANELA_FECHADA:
                    raise
                if not _navegador_conectado(context):
                    raise   # o Chrome inteiro fechou: recomeçar não adianta
                print(
                    f"\n⚠️  Uma janela do SIGEF fechou no meio do download ({erro}).\n"
                    f"   Recomeçando sozinho, sem baixar de novo o que já está pronto "
                    f"(tentativa {tentativa + 1} de {TENTATIVAS_JANELA_FECHADA})..."
                )
                # Onde fechou: fica no registro pra achar a causa de vez
                # (no arquivo, não na tela -- assusta quem está usando).
                registrar_detalhes_tecnicos("janela do SIGEF fechou no download")
                if aba_sigef is not None and aba_sigef.is_closed():
                    aba_sigef = None   # garantir_sessao_sigef() abre outra
    finally:
        desligar_dialogos()


def _pacote(processo, pasta_destino, lancamentos, listagem, avisos) -> dict:
    """O pacote da etapa SEI (2): arquivos já separados por tipo de documento."""
    grupos_ce = _montar_grupos(lancamentos, "numero_ce", "arquivos_ce")
    grupos_ob = _montar_grupos(lancamentos, "ob_baixada", "arquivos_ob")
    arquivos_ob = [caminho for _numero, arquivos in grupos_ob for caminho in arquivos]
    return {
        "processo": processo,
        "ce": listagem["ce"],
        "ob": ", ".join(numero for numero, _arquivos in grupos_ob),
        "pasta_processo": pasta_destino,
        "grupos_ce": grupos_ce,
        "grupos_ob": grupos_ob,
        "arquivos_ob": arquivos_ob,
        "lancamentos": lancamentos,
        "listagem": _resumo_listagem(listagem),
        "avisos_download": avisos,
    }


def _baixar_documentos_uma_vez(
    context,
    aba_sigef,
    processo: str,
    lancamentos: list[dict],
    ce: str,
    pasta_base: str,
    salvar_na_sessao: bool,
    ultima_tentativa: bool = True,
    modo: str = MODO_LISTAGEM_PADRAO,
) -> dict:
    """
    Baixa do SIGEF a CE, as PPs, as NLs e as OBs dos `lancamentos`, só
    com os números gerados pelo fluxo (ver montar_listagem).

    Os JPGs vão pra uma subpasta com o número do processo. O retorno é o
    pacote que executar_sei2() recebe; ele também vai pra sessão.

    Uma falha em um documento não derruba os outros: vira aviso (que
    aparece na conferência final) e o lançamento fica sem `anexo_baixado`.
    """
    modo = (modo or MODO_LISTAGEM_PADRAO).lower()
    if modo not in (MODO_OB, MODO_PP):
        raise ValueError(f"modo de listagem desconhecido: {modo!r} (use 'ob' ou 'pp')")

    ce_gerada = ce if ce is not None else carregar_sessao().get("ce")
    pasta_destino = os.path.join(pasta_base, nome_pasta_valido(processo))

    def erro_para_valer(erro) -> bool:
        """
        Erro que NÃO deve ser isolado no documento: o Chrome inteiro fechou
        ou (fora da última tentativa) uma janela fechou -- aí quem manda é
        o baixar_documentos(), que recomeça.
        """
        if isinstance(erro, PlaywrightError) and not isinstance(erro, PlaywrightTimeoutError):
            if not _navegador_conectado(context):
                return True
            if "has been closed" in str(erro) and not ultima_tentativa:
                return True
        return False

    def gravar(**extra) -> None:
        # Salva depois de CADA documento: se o programa parar no meio
        # (trava, é fechado, dá erro), o que já foi baixado não se perde.
        if salvar_na_sessao:
            salvar_sessao(lancamentos=lancamentos, **extra)

    # ---- 1. Listagem: o que o fluxo gerou ----
    listagem = montar_listagem(lancamentos, ce_gerada)
    mostrar_listagem(listagem, modo)
    avisos: list[str] = list(listagem["avisos"])   # vai para a conferência

    itens = listagem["itens"]
    if not itens:
        print("\n⚠️  Nenhum lançamento tem PP -- não há o que baixar do SIGEF (rode as etapas NL e PP).")
        return _pacote(processo, pasta_destino, lancamentos, listagem, avisos)

    for linha in itens:
        _limpar_baixado_velho(linha["item"])
        _limpar_ce_velha(linha["item"], ce_gerada)

    # Tudo já baixado (mesmos números, arquivos em disco)? Não abre o SIGEF.
    if all(_tudo_pronto(linha["item"]) for linha in itens):
        print("\n♻️  Todos os documentos desta listagem já estão baixados -- reaproveitando, sem abrir o SIGEF.")
        for linha in itens:
            _atualizar_item(linha["item"])
        pacote = _pacote(processo, pasta_destino, lancamentos, listagem, avisos)
        gravar(
            pasta_processo=pasta_destino, grupos_ce=pacote["grupos_ce"], grupos_ob=pacote["grupos_ob"],
            arquivos_ob=pacote["arquivos_ob"], avisos_download=avisos, listagem_download=pacote["listagem"],
            download_completo=not avisos, download_processo=processo,
        )
        return pacote

    # Daqui em diante a sessão guarda um download em andamento: se parar no
    # meio, a próxima tentativa não pode tomar isso por completo.
    if salvar_na_sessao:
        salvar_sessao(
            download_completo=False, download_processo=processo, avisos_download=[],
            grupos_ce=[], grupos_ob=[], arquivos_ob=[], listagem_download=_resumo_listagem(listagem),
        )

    # ---- 2. Aba do SIGEF, com a sessão conferida ----
    aba_sigef = garantir_sessao_sigef(context, aba_sigef)
    fechar_janelas_sobrando(context, manter=aba_sigef)
    os.makedirs(pasta_destino, exist_ok=True)

    # O que já foi baixado numa tentativa anterior e ainda vale.
    ce_baixadas: dict[str, list[str]] = {}
    for linha in itens:
        item = linha["item"]
        if _ce_e_pp_prontas(item) and item.get("numero_ce"):
            ce_baixadas.setdefault(_chave_numero(item["numero_ce"]) or item["numero_ce"], item["arquivos_ce"])

    pendentes = []
    for linha in itens:
        if _ce_e_pp_prontas(linha["item"]):
            print(f"   ⏭️  PP {linha['pp']}: CE e PP já foram baixadas -- pulando.")
        else:
            pendentes.append(linha)

    # ---- 3. CE + PP. Modo "ob": OB por OB, como no LBA ----
    pela_pp = []
    if modo == MODO_OB:
        por_ob: dict[str, list[dict]] = {}
        for linha in pendentes:
            if linha["ob"]:
                por_ob.setdefault(linha["ob"], []).append(linha)
            else:
                pela_pp.append(linha)

        for indice, (ob, linhas_da_ob) in enumerate(por_ob.items(), start=1):
            print(f"\n▶️  OB {indice}/{len(por_ob)}: {ob} ({len(linhas_da_ob)} PP(s) gerada(s))")
            interacao.andamento(f"Procurando a OB {ob} no SIGEF ({len(linhas_da_ob)} PP(s))", indice, len(por_ob))
            pela_pp += _baixar_pela_ob(
                context, aba_sigef, pasta_destino, ob, linhas_da_ob, ce_gerada,
                ce_baixadas, avisos, erro_para_valer,
            )
            for linha in linhas_da_ob:
                _atualizar_item(linha["item"])
            gravar(avisos_download=avisos)

        # Volta a ordem do fluxo para o que sobrou.
        pela_pp.sort(key=lambda linha: linha["posicao"])
    else:
        pela_pp = list(pendentes)

    # ---- 3 (reserva). CE + PP pela tela "Listar PP" ----
    for indice, linha in enumerate(pela_pp, start=1):
        pp, item = linha["pp"], linha["item"]
        print(f"\n▶️  {indice}/{len(pela_pp)}: PP {pp} (valor {linha['valor']}) pela tela Listar PP")
        interacao.andamento(f"Baixando a PP {pp} pela tela Listar PP", indice, len(pela_pp))
        janelas_antes = set(context.pages)
        try:
            _baixar_pela_pp(context, aba_sigef, pasta_destino, linha, ce_gerada, ce_baixadas, avisos)
        except (PlaywrightError, SystemExit) as erro:
            if erro_para_valer(erro):
                raise
            _avisar(avisos, f"PP {pp}: deu erro no SIGEF e a CE/PP dela NÃO foram baixadas ({_detalhe_do_erro(erro)}).")
            registrar_detalhes_tecnicos(f"download da PP {pp} pela tela Listar PP")
            _fechar_janelas_novas(context, janelas_antes, manter=aba_sigef)
            item.pop("pp_baixada", None)
            item["arquivos_pp"] = []
        else:
            print(f"✅ PP {pp}: CE e PP baixadas")

        _atualizar_item(item)
        gravar(avisos_download=avisos)

    # ---- 4. NLs e OBs, no fim, na ABA PRINCIPAL ----
    #
    # Ficam no fim: mexer na aba principal antes derrubaria a janela da
    # PP/OB de que o loop de cima depende a cada volta.
    aba_sigef.bring_to_front()

    # 4.A  Uma NL por PP (a mesma NL em duas PPs é baixada uma vez).
    nls_baixadas: dict[str, list[str]] = {}
    for linha in itens:
        item = linha["item"]
        if item.get("nl_baixada") and item.get("nl_baixada") == item.get("numero_nl") and _existem(item.get("arquivos_nl")):
            nls_baixadas.setdefault(item["nl_baixada"], item["arquivos_nl"])

    for linha in itens:
        item, pp = linha["item"], linha["pp"]
        # numero_nl só existe se a PP chegou a ser lida; se ela falhou, a
        # NL gerada ainda vale.
        numero_nl = item.get("numero_nl") or linha["nl"]
        if not numero_nl:
            continue
        item["numero_nl"] = numero_nl
        item.setdefault("pp_dos_numeros", pp)

        if numero_nl in nls_baixadas:
            novos_jpg = nls_baixadas[numero_nl]
            print(f"\n↩️  Nota de Lançamento {numero_nl} (PP {pp}): já baixada -- reaproveitando.")
        else:
            print(f"\n▶️  Nota de Lançamento {numero_nl} (PP {pp})")
            interacao.andamento(f"Baixando a NL {numero_nl}")
            janelas_antes = set(context.pages)
            try:
                novos_jpg = _baixar_nl(context, aba_sigef, pasta_destino, pp, numero_nl)
                print(f"   📄 Nota de Lançamento: {len(novos_jpg)} JPG(s)")
            except (PlaywrightError, SystemExit) as erro:
                if erro_para_valer(erro):
                    raise
                detalhe = _detalhe_do_erro(erro)
                _avisar(
                    avisos,
                    f"NL {numero_nl} da PP {pp}: deu erro no SIGEF e NÃO foi anexada ({detalhe}). "
                    "Baixe e inclua esta NL à mão.",
                )
                _fechar_janelas_novas(context, janelas_antes, manter=aba_sigef)
                novos_jpg = []
            if novos_jpg:
                nls_baixadas[numero_nl] = novos_jpg

        item["arquivos_nl"] = novos_jpg
        item["nl_baixada"] = numero_nl if novos_jpg else None
        _atualizar_item(item)
        gravar(avisos_download=avisos)

    # 4.B  Ordens Bancárias, por último: uma por OB DISTINTA.
    obs_baixadas: dict[str, list[str]] = {}
    for linha in itens:
        item = linha["item"]
        if item.get("ob_baixada") and item.get("ob_baixada") == item.get("numero_ob") and _existem(item.get("arquivos_ob")):
            obs_baixadas.setdefault(item["ob_baixada"], item["arquivos_ob"])

    for linha in itens:
        item = linha["item"]
        numero_ob = item.get("numero_ob") or linha["ob"]
        if not numero_ob:
            continue
        item["numero_ob"] = numero_ob
        item.setdefault("pp_dos_numeros", linha["pp"])

        if numero_ob in obs_baixadas:
            novos_jpg = obs_baixadas[numero_ob]
            print(f"\n↩️  Ordem Bancária {numero_ob} (PP {linha['pp']}): já baixada -- reaproveitando.")
        else:
            print(f"\n▶️  Ordem Bancária {numero_ob} (PP {linha['pp']})")
            interacao.andamento(f"Baixando a OB {numero_ob}")
            janelas_antes = set(context.pages)
            try:
                novos_jpg = _baixar_ob(context, aba_sigef, pasta_destino, numero_ob)
                print(f"   📄 Ordem Bancária: {len(novos_jpg)} JPG(s)")
            except (PlaywrightError, SystemExit) as erro:
                if erro_para_valer(erro):
                    raise
                detalhe = _detalhe_do_erro(erro)
                _avisar(
                    avisos,
                    f"OB {numero_ob}: deu erro no SIGEF e NÃO foi anexada ({detalhe}). "
                    "Baixe e inclua esta OB à mão.",
                )
                _fechar_janelas_novas(context, janelas_antes, manter=aba_sigef)
                novos_jpg = []
            if novos_jpg:
                obs_baixadas[numero_ob] = novos_jpg

        item["arquivos_ob"] = novos_jpg
        item["ob_baixada"] = numero_ob if novos_jpg else None
        _atualizar_item(item)
        gravar(avisos_download=avisos)

    # 4.C  CE gerada que não veio de nenhuma PP: avisa (o SEI ficaria sem ela).
    if ce_gerada and not any(
        _mesmo_documento(linha["item"].get("numero_ce"), ce_gerada) and linha["item"].get("arquivos_ce")
        for linha in itens
    ):
        _avisar(
            avisos,
            f"CE {ce_gerada}: nenhuma PP mostrou esta Despesa Certificada, então ela NÃO foi "
            "baixada. Baixe e inclua a CE à mão.",
        )

    # 4.D  Deixa a aba do SIGEF arrumada. Não é crítico.
    try:
        aba_sigef.bring_to_front()
        aba_sigef.goto(URL_SIGEF_LISTAR_PP)
        aba_sigef.wait_for_load_state("networkidle")
    except PlaywrightError as erro:
        print(f"\n⚠️  Não consegui deixar a aba do SIGEF pronta pro que vem depois ({erro}) -- sem problema.")

    # ---- 5. Pacote da etapa SEI (2) ----
    pacote = _pacote(processo, pasta_destino, lancamentos, listagem, avisos)
    completo = not avisos and all(linha["item"].get("anexo_baixado") for linha in itens)
    gravar(
        pasta_processo=pasta_destino,
        grupos_ce=pacote["grupos_ce"],
        grupos_ob=pacote["grupos_ob"],
        arquivos_ob=pacote["arquivos_ob"],
        avisos_download=avisos,
        listagem_download=pacote["listagem"],
        download_completo=completo,
        download_processo=processo,
    )
    return pacote


def executar_anexar_lote(
    context,
    processo: str,
    lancamentos: list[dict],
    pasta_base: str = PASTA_BASE,
    salvar_na_sessao: bool = True,
    ce: str = None,
    modo: str = MODO_LISTAGEM_PADRAO,
) -> list[dict]:
    """
    Roda a Etapa Anexar Documento pra TODOS os lançamentos que já têm uma
    PP gerada (item.get("pp")), sejam 3, sejam 20: baixa a CE, as NLs, as
    PPs e as OBs desses lançamentos, com os números que o próprio fluxo
    gerou (ver o docstring do módulo).

    `ce` é a CE gerada na Etapa CE; sem ela, usa a da sessão.
    `modo` é o modo de listagem: "ob" (padrão, igual ao LBA) ou "pp".

    Salva os arquivos baixados em cada item (arquivos_ce/arquivos_nl/
    arquivos_pp/arquivos_ob e o achatado `arquivos_anexar`) e marca
    `item["anexo_baixado"]`. Com `salvar_na_sessao` (padrão), grava a
    sessão a cada documento.

    `salvar_na_sessao=False` é pra teste com uma lista de lançamentos
    "avulsa" (ex: PPs digitadas na hora), sem sobrescrever os lançamentos
    reais salvos em sessao_atual.json.

    Retorna a MESMA lista `lancamentos`.
    """
    baixar_documentos(
        context, None, processo, lancamentos, ce=ce,
        pasta_base=pasta_base, salvar_na_sessao=salvar_na_sessao, modo=modo,
    )
    return lancamentos


def _resumo(lancamentos: list[dict]) -> None:
    print(f"\n{'=' * 50}\nRESUMO DO DOWNLOAD\n{'=' * 50}")
    print("  ✅ = documentos baixados    ⚠️  = faltou baixar algo (leia os avisos acima)")
    for i, item in enumerate(lancamentos, start=1):
        status = "✅" if item.get("anexo_baixado") else "⚠️ "
        print(
            f"{status} {i}) Valor {item.get('valor')} | PP {item.get('pp')} | "
            f"CE {item.get('numero_ce') or '-'} | NL {item.get('numero_nl') or '-'} | "
            f"OB {item.get('numero_ob') or '-'} | via {item.get('rota_listagem') or '-'}"
        )
        for caminho in item.get("arquivos_anexar") or []:
            print(f"     - {os.path.basename(caminho)}")


if __name__ == "__main__":
    # Teste isolado da Etapa Anexar Documento: conecta no Chrome já
    # aberto e roda o lote inteiro usando os lançamentos já salvos na
    # sessão (os mesmos preenchidos por main.py / etapa_nl.py /
    # etapa_pp.py / etapa_ob.py, cada um já com "nl", "pp" e "ob") --
    # não precisa rodar as etapas anteriores de novo.
    from automacoes.anexar.automacao.utils import conectar_chrome

    playwright, browser, context = conectar_chrome()
    try:
        sessao = carregar_sessao()
        processo = perguntar_ou_reusar(
            "Digite o processo do SEI (para nomear a pasta)", "processo", sessao
        )
        # Modo de teste: usa os lançamentos salvos na sessão; o botão escolhe
        # o modo de listagem (OB, igual ao LBA, ou PP).
        lancamentos_teste = []
        modo = interacao.escolher("Modo de listagem", ["Como procurar os documentos no SIGEF?"], [
            interacao.botao(MODO_OB, "Pela OB (igual ao LBA)", "principal"),
            interacao.botao(MODO_PP, "Pela PP"),
        ])

        if lancamentos_teste:
            print(f"➡️  {len(lancamentos_teste)} PP(s) digitada(s): {', '.join(i['pp'] for i in lancamentos_teste)}")
            lancamentos = lancamentos_teste
            salvar_na_sessao = False
        else:
            lancamentos = sessao.get("lancamentos") or []
            salvar_na_sessao = True

        if not lancamentos:
            print("⚠️  Nenhuma PP digitada e nenhum lançamento salvo na sessão (chave 'lancamentos' vazia ou ausente).")
        else:
            lancamentos = executar_anexar_lote(
                context, processo, lancamentos, salvar_na_sessao=salvar_na_sessao, modo=modo,
            )
            _resumo(lancamentos)
    finally:
        playwright.stop()
