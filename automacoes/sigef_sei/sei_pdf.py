"""
Anexa no SEI como PDF (documento Externo), em vez de colar imagens.

É a escolha "Como salvar no SEI" do passo 3 do Anexar no SEI e da Nota de
Empenho. O download do SIGEF é o mesmo; muda só o que acontece no SEI,
uma vez por documento:

    Incluir Documento -> "Externo" (escolher(-1)) -> espera o formulário
    #selSerie            o tipo do documento (ver SERIES_EXTERNO)
    #txtDataElaboracao   a data de hoje (dd/mm/aaaa)
    #txtNumero / #txtNomeArvore   só quando a tela tiver (PP e NE)
    #optNato             Nato-digital
    #optPublico          Nível de acesso Público
    o PDF no campo de arquivo (#filArquivo) -- o mesmo que arrastar para
    .infraDivDropFile; se o campo não reagir, o arquivo é solto na área
    #btnSalvar           e espera o formulário sumir

Um documento Externo por PDF, igual ao modo imagem: 1 CE por CE distinta,
1 NL e 1 PP por PP, 1 OB, 1 NE.

Os seletores e os cuidados são os do Externo do DARE e do BB, que já
rodam no SEI de verdade: clicar na raiz do processo antes do "Incluir
Documento", repetir o clique se a lista de tipos não abrir, e dar o
envio por terminado quando o arquivo aparece em #tblAnexos.

DE ONDE VEM O PDF -- etapa_listar_baixar.pdf_para_jpg() e a NE guardam o
PDF do SIGEF ao lado das imagens ("Nota de Lançamento - PP 2026PP066790.pdf"
junto do ".jpg"). Um download feito por uma versão anterior só tem as
imagens: aí o PDF é montado com elas, com aviso na conferência.

RETOMADA -- mesmo progresso_sei.json e mesmas chaves do modo imagem
("CE 2026CE000123", "NL 2026PP066790", "OB", "NE 000123"): o que já foi
salvo, em qualquer dos dois modos, é pulado. Falha ANTES do Salvar (nada
foi criado no SEI) é tentada de novo sozinha; depois do Salvar, não --
poderia duplicar o documento.

DIAGNÓSTICO -- Documentos\\Automacao SIGEF-SEI\\diagnostico_pdf.log (cada
passo) e, na falha, diagnostico_pdf\\<data>_<documento>.txt/.png/.html
(o passo, o erro, as mensagens do SEI, o que existe em cada frame e as
opções do #selSerie). Para testar a tela sem salvar nada:

    python -m automacoes.sigef_sei.diagnostico_pdf 0029.001947/2026-67
"""
import base64
import os
import re
import time
import unicodedata

from playwright.sync_api import Error as PlaywrightError

from automacoes.geral import decidir_pulo, gravar_json, impressao_dos_arquivos
from .etapa_listar_baixar import PASTA_BASE, abrir_processo_sei, nome_pasta_valido, normalizar_processo_sei
from .etapa_sei2 import (
    LIMITE_NOME_ARVORE,
    ProgressoSei,
    TEXTO_LINK_OB_NORMAL,
    TEXTO_LINK_OB_REGULARIZACAO,
    _aguardar_rede,
)

FORMATO_IMAGEM = "imagem"
FORMATO_PDF = "pdf"
FORMATOS = (FORMATO_IMAGEM, FORMATO_PDF)


def normalizar_formato(valor) -> str:
    """"imagem" (o de sempre) ou "pdf"; qualquer outra coisa vira "imagem"."""
    texto = str(valor or "").strip().lower()
    return texto if texto in FORMATOS else FORMATO_IMAGEM


# O tipo do modo imagem (o link de "Incluir Documento") -> (texto da opção
# no #selSerie do Externo, value dela). Vale o texto; o value é o plano B
# se o nome mudar (os dois copiados do SEI em 24/11/2026). A OB segue a
# escolha Regularização / Ordem Bancária do passo 3.
SERIES_EXTERNO = {
    "Despesa Certificada": ("Despesa Certificada", "1050"),
    "NL - Nota de Lançamento": ("NL - Nota de Lançamento", "298"),
    "PP - Preparação de Pagamento": ("PP - Preparação de Pagamento", "982"),
    TEXTO_LINK_OB_REGULARIZACAO: ("OB - Ordem Bancária de Regularização", "314"),
    TEXTO_LINK_OB_NORMAL: ("Ordem Bancária", "297"),
    "NE - Nota de Empenho": ("NE - Nota de Empenho", "294"),
}

# :text-is = texto exato com os espaços normalizados (o link é " Externo").
SELETORES_EXTERNO = ('a.ancoraOpcao[onclick="escolher(-1)"]', "a.ancoraOpcao:text-is('Externo')")
SELETOR_INCLUIR = 'img[title="Incluir Documento"]'
SELETOR_FORMULARIO = "#selSerie"

TIMEOUT_LISTA_S = 60             # até a lista de tipos abrir (com cliques repetidos)
TIMEOUT_FORMULARIO_MS = 60000
# O campo de arquivo tem que mostrar o PDF (ou o botão Cancelar do envio) neste tempo;
# senão, o arquivo é solto na área de arrastar. Folgado de propósito: soltar enquanto o
# primeiro envio ainda corre poria o PDF em dobro.
TIMEOUT_INICIO_UPLOAD_S = 60
TIMEOUT_UPLOAD_S = 300           # PDF grande em internet lenta
TIMEOUT_SALVAR_S = 120
TENTATIVAS_ANTES_DE_SALVAR = 3
ESPERAS_ENTRE_TENTATIVAS = (5, 15)

ARQUIVO_DIAGNOSTICO_PDF = os.path.join(PASTA_BASE, "diagnostico_pdf.log")
PASTA_DIAGNOSTICO_PDF = os.path.join(PASTA_BASE, "diagnostico_pdf")

# O que procurar em cada frame quando algo falha (e no diagnostico_pdf).
SELETORES_DIAGNOSTICO = {
    "Incluir Documento": SELETOR_INCLUIR,
    "link Externo": SELETORES_EXTERNO[0],
    "Tipo do documento (#selSerie)": SELETOR_FORMULARIO,
    "Data de elaboração (#txtDataElaboracao)": "#txtDataElaboracao",
    "Número (#txtNumero)": "#txtNumero",
    "Nome na árvore (#txtNomeArvore)": "#txtNomeArvore",
    "Nato-digital (#optNato)": "#optNato",
    "Público (#optPublico)": "#optPublico",
    "campo de arquivo (#filArquivo)": "#filArquivo",
    "outro campo de arquivo": 'input[type="file"]',
    "área de soltar (.infraDivDropFile)": ".infraDivDropFile",
    "lista de anexos (#tblAnexos)": "#tblAnexos",
    "Salvar (#btnSalvar)": "#btnSalvar",
}


class FalhaPdf(SystemExit):
    """Falha no Externo. `criou`: o Salvar já tinha sido clicado (o documento pode existir)."""

    def __init__(self, mensagem: str, criou: bool = False):
        super().__init__(mensagem)
        self.criou = criou


# ==== diagnóstico ====


def _diag(texto: str) -> None:
    """Uma linha no diagnostico_pdf.log. Falha ao gravar não atrapalha a automação."""
    try:
        os.makedirs(PASTA_BASE, exist_ok=True)
        with open(ARQUIVO_DIAGNOSTICO_PDF, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"{time.strftime('%d/%m %H:%M:%S')} {texto}\n")
    except OSError:
        pass


def resumo_frames(aba_sei) -> list[str]:
    """Cada frame da aba e quais peças do Externo existem nele."""
    linhas = []
    for frame in aba_sei.frames:
        try:
            achados = [nome for nome, seletor in SELETORES_DIAGNOSTICO.items() if frame.locator(seletor).count()]
        except PlaywrightError as erro:
            achados = [f"(não deu para ler: {str(erro).splitlines()[0]})"]
        linhas.append(f"  frame name={frame.name!r} url={frame.url}")
        linhas.append(f"      tem: {', '.join(achados) or '—'}")
    return linhas


def opcoes_serie(frame) -> list[tuple[str, str]]:
    """As opções do #selSerie: [(value, texto)]. Vazia se o campo não estiver lá."""
    try:
        return [
            (o["value"], o["texto"])
            for o in frame.locator(SELETOR_FORMULARIO).first.evaluate(
                "el => Array.from(el.options).map(o => ({value: o.value, texto: o.textContent.trim()}))"
            )
        ]
    except PlaywrightError:
        return []


def registrar_falha_pdf(aba_sei, descricao: str, passo: str, erro, dialogos=(), frame=None) -> str:
    """Grava relatório, foto e HTML da falha. Devolve o caminho base ("" se nem isso deu)."""
    try:
        os.makedirs(PASTA_DIAGNOSTICO_PDF, exist_ok=True)
        base = os.path.join(
            PASTA_DIAGNOSTICO_PDF, f"{time.strftime('%Y%m%d-%H%M%S')}_{nome_pasta_valido(descricao)[:60]}"
        )
        linhas = [
            f"Documento: {descricao}",
            f"Passo: {passo}",
            f"Erro: {type(erro).__name__}: {getattr(erro, 'code', None) or erro}",
            f"Mensagens do SEI: {list(dialogos) or '—'}",
            f"Aba do SEI: {getattr(aba_sei, 'url', '?')}",
            "",
            "Frames e o que existe em cada um:",
            *resumo_frames(aba_sei),
        ]
        opcoes = opcoes_serie(frame) if frame is not None else []
        if opcoes:
            linhas += ["", f"Opções do #selSerie ({len(opcoes)}):", *[f"  {v:>6}  {t}" for v, t in opcoes]]
        with open(base + ".txt", "w", encoding="utf-8") as arquivo:
            arquivo.write("\n".join(linhas) + "\n")
        try:
            aba_sei.screenshot(path=base + ".png", full_page=True, timeout=5000)
        except Exception:
            pass
        try:
            with open(base + ".html", "w", encoding="utf-8") as arquivo:
                arquivo.write((frame or aba_sei).content())
        except Exception:
            pass
        _diag(f"  FALHOU em '{passo}': {type(erro).__name__}: {str(getattr(erro, 'code', None) or erro).splitlines()[:1]} -> {base}.txt")
        return base
    except Exception:
        return ""


# ==== o PDF de cada documento ====


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).lower().split())


def e_pdf(caminho: str) -> bool:
    try:
        with open(caminho, "rb") as arquivo:
            return arquivo.read(4) == b"%PDF"
    except OSError:
        return False


def candidatos_pdf(arquivos: list[str]) -> list[str]:
    """"X.jpg" / "X_1.jpg" -> "X.pdf" (o PDF guardado no download), na ordem de tentativa."""
    base = os.path.splitext(arquivos[0])[0]
    sem_pagina = re.sub(r"_\d+$", "", base) if len(arquivos) > 1 or re.search(r"_1$", base) else base
    return list(dict.fromkeys([sem_pagina + ".pdf", base + ".pdf"]))


def pdf_do_documento(arquivos: list[str]) -> tuple[str, bool]:
    """
    O PDF de um documento, a partir das imagens dele. Devolve (caminho,
    montado): `montado` é True quando o PDF original não estava na pasta
    (download de uma versão anterior) e foi montado com as imagens.
    """
    if not arquivos:
        raise FalhaPdf("não há arquivo deste documento para montar o PDF")
    candidatos = candidatos_pdf(arquivos)
    for caminho in candidatos:
        if e_pdf(caminho):
            return caminho, False

    import pymupdf  # só aqui: quem não usa o modo PDF não carrega

    existentes = [a for a in arquivos if os.path.exists(a)]
    if not existentes:
        raise FalhaPdf(f"nem o PDF nem as imagens deste documento estão na pasta ({candidatos[0]})")
    destino = candidatos[0]
    with pymupdf.open() as pdf:
        for imagem in existentes:
            with pymupdf.open(imagem) as img:
                with pymupdf.open("pdf", img.convert_to_pdf()) as pagina:
                    pdf.insert_pdf(pagina)
        pdf.save(destino)
    _diag(f"  PDF original não estava na pasta; montado com {len(existentes)} imagem(ns): {destino}")
    return destino, True


# ==== passos na tela do SEI ====


def _achar(aba_sei, seletores, timeout: int = 0):
    """
    O primeiro dos `seletores` VISÍVEL em algum frame da aba: (frame,
    locator, nome do frame). Olha todos os frames de uma vez (sem esperar
    em cada um) e repete até `timeout` ms. (None, None, None) se não achar.
    """
    prazo = time.monotonic() + timeout / 1000
    while True:
        for seletor in seletores:
            for frame in aba_sei.frames:
                try:
                    locator = frame.locator(f"{seletor} >> visible=true")
                    if locator.count():
                        return frame, locator.first, frame.name or "aba_sei"
                except PlaywrightError:
                    continue
        if time.monotonic() >= prazo:
            return None, None, None
        time.sleep(0.25)


def clicar_raiz_do_processo(aba_sei, processo: str) -> None:
    """Volta a visualização para o processo, onde fica o 'Incluir Documento' (como no BB)."""
    arvore = aba_sei.frame(name="ifrArvore")
    if arvore is None or not processo:
        return
    try:
        link = arvore.locator(f'a:has-text("{processo}")').first
        if link.count():
            link.click(timeout=5000)
            aba_sei.wait_for_timeout(800)
    except PlaywrightError:
        pass


def abrir_lista_e_clicar_externo(aba_sei, processo: str) -> None:
    """
    Incluir Documento -> Externo, com confirmação: o clique no 'Incluir
    Documento' às vezes cai enquanto o frame ainda carrega e se perde
    (visto no BB). Espera, clica, confere se a lista abriu e, se não,
    clica de novo -- até TIMEOUT_LISTA_S.
    """
    clicar_raiz_do_processo(aba_sei, processo)
    prazo, cliques, externo = time.monotonic() + TIMEOUT_LISTA_S, 0, None
    while time.monotonic() < prazo:
        _l, externo, _n = _achar(aba_sei, SELETORES_EXTERNO)
        if externo is not None:
            break
        lugar, incluir, nome = _achar(aba_sei, (SELETOR_INCLUIR,), timeout=5000)
        if incluir is None:
            clicar_raiz_do_processo(aba_sei, processo)
            continue
        try:
            lugar.wait_for_load_state("load", timeout=5000)
        except (PlaywrightError, AttributeError):
            pass
        try:
            incluir.click(timeout=5000)
        except PlaywrightError:
            try:   # o <img> fica dentro do <a> que abre a lista
                incluir.evaluate("el => (el.closest('a') || el).click()")
            except PlaywrightError:
                pass
        cliques += 1
        _diag(f"  clique {cliques} em 'Incluir Documento' (frame '{nome}')")
        _l, externo, nome_ext = _achar(aba_sei, SELETORES_EXTERNO, timeout=6000)
        if externo is not None:
            break
        print(f"   ⚠️  O clique em 'Incluir Documento' não abriu a lista ({cliques}); clicando de novo...")
    if externo is None:
        raise FalhaPdf(
            f"a lista de tipos não mostrou 'Externo' nem depois de {cliques} clique(s) em 'Incluir Documento'"
        )
    externo.click(timeout=10000)


def _esperar_formulario(aba_sei, timeout_ms: int = TIMEOUT_FORMULARIO_MS):
    """O frame com o #selSerie (o SEI pode recriar o iframe no caminho)."""
    prazo = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < prazo:
        for frame in aba_sei.frames:
            try:
                if frame.locator(SELETOR_FORMULARIO).count():
                    return frame
            except PlaywrightError:
                continue
        aba_sei.wait_for_timeout(250)
    return None


def _escolher_serie(aba_sei, frame, texto: str, valor: str):
    """Escolhe o tipo no #selSerie (pelo texto, ou pelo value). Devolve o frame (pode ter sido recriado)."""
    opcoes = opcoes_serie(frame)
    alvo = _sem_acento(texto)
    escolhida = next((v for v, t in opcoes if _sem_acento(t) == alvo), None)
    if escolhida is None and any(v == valor for v, _t in opcoes):
        escolhida = valor
        _diag(f"  '{texto}' não está pelo nome no #selSerie; usando o value {valor}")
    if escolhida is None:
        chave = alvo.split(" - ")[-1]
        parecidas = [t for _v, t in opcoes if chave in _sem_acento(t)]
        raise FalhaPdf(
            f"o tipo '{texto}' não está na lista do Externo"
            + (f" (parecidos: {', '.join(parecidas[:5])})" if parecidas else "")
        )
    for _ in range(3):
        try:
            frame.locator(SELETOR_FORMULARIO).first.select_option(value=escolhida, timeout=10000)
            aba_sei.wait_for_timeout(400)   # trocarSerie() reajusta o formulário
            _aguardar_rede(aba_sei, 3000)
            if frame.locator(SELETOR_FORMULARIO).first.input_value(timeout=5000) == escolhida:
                return frame
        except PlaywrightError as erro:
            _diag(f"  escolher o tipo: {str(erro).splitlines()[0]}; procurando o formulário de novo")
        frame = _esperar_formulario(aba_sei, 15000) or frame
    raise FalhaPdf(f"escolhi '{texto}' no #selSerie, mas o SEI não manteve a escolha")


def _preencher_data(frame) -> str:
    hoje = time.strftime("%d/%m/%Y")
    campo = frame.locator("#txtDataElaboracao").first
    if not campo.count():
        raise FalhaPdf("não achei o campo Data de Elaboração (#txtDataElaboracao)")
    campo.fill(hoje, timeout=10000)
    if campo.input_value() != hoje:   # a máscara do SEI mexeu no texto: digita como gente
        campo.fill("")
        campo.press_sequentially(hoje.replace("/", ""), delay=30)
    if re.sub(r"\D", "", campo.input_value()) != re.sub(r"\D", "", hoje):
        raise FalhaPdf(f"a Data de Elaboração ficou '{campo.input_value()}', e não {hoje}")
    return hoje


def _preencher_se_existir(frame, seletor: str, valor: str, nome: str) -> bool:
    if not valor:
        return False
    campo = frame.locator(seletor).first
    try:
        if campo.count() and campo.is_visible() and campo.is_editable():
            campo.fill(valor, timeout=5000)
            return True
    except PlaywrightError:
        pass
    _diag(f"  campo {nome} ({seletor}) não está na tela ou não aceita texto; seguindo sem ele")
    return False


def _marcar_opcao(frame, id_radio: str, nome: str) -> None:
    radio = frame.locator(f"#{id_radio}").first
    if not radio.count():
        raise FalhaPdf(f"não achei a opção '{nome}' (#{id_radio})")
    rotulo = frame.locator(f'label[for="{id_radio}"]').first
    jeitos = [lambda: None]
    if rotulo.count():
        jeitos.append(lambda: rotulo.click(timeout=5000))
    jeitos += [lambda: radio.check(timeout=5000, force=True), lambda: radio.evaluate("el => el.click()")]
    for jeito in jeitos:
        try:
            if radio.is_checked():
                return
            jeito()
        except PlaywrightError:
            continue
    if not radio.is_checked():
        raise FalhaPdf(f"cliquei em '{nome}' (#{id_radio}), mas a opção não ficou marcada")


_JS_ANEXOS = """el => {
    const doc = el.ownerDocument;
    const tabela = doc.querySelector('#tblAnexos');
    const cancelar = doc.querySelector('[id^="btnUploadCancelar"]');
    return {
        linhas: tabela ? tabela.querySelectorAll('tbody tr').length : 0,
        texto: tabela ? tabela.innerText : '',
        enviando: !!cancelar && getComputedStyle(cancelar).display !== 'none',
    };
}"""


def _anexos(frame) -> dict:
    try:
        return frame.locator("body").first.evaluate(_JS_ANEXOS)
    except PlaywrightError:
        return {"linhas": 0, "texto": "", "enviando": False}


def _soltar_arquivo(area, caminho: str) -> None:
    """O mesmo que arrastar o arquivo do Windows e soltar na área do SEI."""
    with open(caminho, "rb") as arquivo:
        dados = base64.b64encode(arquivo.read()).decode("ascii")
    area.evaluate(
        """(el, [b64, nome]) => {
            const bin = atob(b64); const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            const dt = new DataTransfer();
            dt.items.add(new File([bytes], nome, {type: 'application/pdf'}));
            for (const tipo of ['dragenter', 'dragover', 'drop'])
                el.dispatchEvent(new DragEvent(tipo, {bubbles: true, cancelable: true, dataTransfer: dt}));
        }""",
        [dados, os.path.basename(caminho)],
    )


def _esperar_anexo(frame, antes: dict, dialogos: list, segundos: float) -> bool:
    """True quando o arquivo aparece na lista de anexos. Mensagem do SEI no meio = recusa."""
    prazo = time.monotonic() + segundos
    while time.monotonic() < prazo:
        if dialogos:
            raise FalhaPdf(f"o SEI recusou o arquivo: {' | '.join(dialogos)}")
        agora = _anexos(frame)
        if agora["linhas"] > antes["linhas"] and not agora["enviando"]:
            return True
        if agora["enviando"]:   # ainda enviando: não desiste no meio
            prazo = max(prazo, time.monotonic() + 2)
        time.sleep(0.3)
    return False


def _enviar_pdf(frame, caminho_pdf: str, dialogos: list) -> str:
    """Põe o PDF no formulário e espera o SEI receber. Devolve como foi enviado."""
    antes = _anexos(frame)
    entrada = next(
        (frame.locator(s).first for s in ("#filArquivo", 'input[type="file"]') if frame.locator(s).count()), None
    )
    area = frame.locator(".infraDivDropFile").first
    jeitos = []
    if entrada is not None:
        jeitos.append(("campo de arquivo", lambda: entrada.set_input_files(caminho_pdf, timeout=30000)))
    if area.count():
        jeitos.append(("arrastar e soltar", lambda: _soltar_arquivo(area, caminho_pdf)))
    if not jeitos:
        raise FalhaPdf("não achei onde pôr o arquivo: nem o campo #filArquivo nem a área .infraDivDropFile")

    for indice, (jeito, enviar) in enumerate(jeitos):
        _diag(f"  enviando {os.path.basename(caminho_pdf)} ({os.path.getsize(caminho_pdf) // 1024} KB) por {jeito}")
        enviar()
        ultimo = indice == len(jeitos) - 1
        if _esperar_anexo(frame, antes, dialogos, TIMEOUT_UPLOAD_S if ultimo else TIMEOUT_INICIO_UPLOAD_S):
            return jeito
        if not ultimo:
            _diag(f"  o SEI não mostrou o arquivo em {TIMEOUT_INICIO_UPLOAD_S}s pelo {jeito}; tentando {jeitos[indice + 1][0]}")
    raise FalhaPdf(
        f"o SEI não terminou de receber o PDF em {TIMEOUT_UPLOAD_S}s (a Lista de Anexos continuou vazia)"
    )


def _salvar(aba_sei, frame, dialogos: list) -> None:
    """Clica em Salvar e espera o formulário do Externo sair da tela."""
    botao = frame.locator("#btnSalvar").first
    if not botao.count():
        raise FalhaPdf("não achei o botão Salvar (#btnSalvar)")
    dialogos.clear()
    try:
        botao.click(timeout=10000)
    except PlaywrightError as erro:
        _diag(f"  clique normal no Salvar falhou ({str(erro).splitlines()[0]}); clicando direto no DOM")
        botao.evaluate("el => el.click()")
    prazo = time.monotonic() + TIMEOUT_SALVAR_S
    while time.monotonic() < prazo:
        try:
            aberto = frame.locator(SELETOR_FORMULARIO).count() > 0 and frame.locator(SELETOR_FORMULARIO).is_visible()
        except PlaywrightError:
            aberto = False   # o frame navegou: o formulário saiu
        if not aberto:
            return
        if dialogos:   # alert com o formulário ainda aberto: o SEI recusou, nada foi criado
            aba_sei.wait_for_timeout(1500)
            try:
                if frame.locator(SELETOR_FORMULARIO).count():
                    raise FalhaPdf(f"o SEI não aceitou o formulário: {' | '.join(dialogos)}", criou=False)
            except PlaywrightError:
                return
        time.sleep(0.3)
    raise FalhaPdf(
        f"cliquei em Salvar, mas o formulário continuou na tela por {TIMEOUT_SALVAR_S}s -- "
        "o documento PODE ter sido criado",
        criou=True,
    )


def incluir_externo(
    aba_sei, processo: str, texto_link: str, descricao: str, caminho_pdf: str,
    numero: str = None, nome_arvore: str = "", antes_de_salvar=None,
) -> None:
    """
    Um documento Externo com o PDF, do "Incluir Documento" ao Salvar.
    Levanta FalhaPdf (com `criou`) dizendo o passo, depois de gravar o
    diagnóstico.
    """
    if texto_link not in SERIES_EXTERNO:
        raise FalhaPdf(f"não sei qual tipo do Externo corresponde a '{texto_link}'")
    texto_serie, valor_serie = SERIES_EXTERNO[texto_link]
    dialogos: list[str] = []

    def ao_dialogo(dialogo):
        try:
            dialogos.append(dialogo.message)
            _diag(f"  mensagem do SEI ({dialogo.type}): {dialogo.message}")
            dialogo.dismiss()
        except Exception:
            pass

    passo, frame, clicou_salvar = "abrir 'Incluir Documento' e clicar em 'Externo'", None, False
    _diag(f"=== {descricao} · Externo '{texto_serie}' · {os.path.basename(caminho_pdf)} · aba {aba_sei.url}")
    aba_sei.on("dialog", ao_dialogo)
    try:
        abrir_lista_e_clicar_externo(aba_sei, normalizar_processo_sei(processo) or processo)

        passo = "esperar o formulário do Externo carregar"
        _aguardar_rede(aba_sei, 8000)
        frame = _esperar_formulario(aba_sei)
        if frame is None:
            raise FalhaPdf(f"o formulário do Externo (#selSerie) não abriu em {TIMEOUT_FORMULARIO_MS // 1000}s")

        passo = f"escolher o tipo '{texto_serie}'"
        frame = _escolher_serie(aba_sei, frame, texto_serie, valor_serie)

        passo = "preencher a Data de Elaboração"
        data = _preencher_data(frame)

        passo = "preencher o Número / Nome na árvore"
        _preencher_se_existir(frame, "#txtNumero", numero, "Número")
        _preencher_se_existir(frame, "#txtNomeArvore", (nome_arvore or "")[:LIMITE_NOME_ARVORE], "Nome na árvore")

        passo = "marcar Nato-digital"
        _marcar_opcao(frame, "optNato", "Nato-digital")
        passo = "marcar Público"
        _marcar_opcao(frame, "optPublico", "Público")
        _diag(f"  formulário: '{texto_serie}', {data}, número {numero or '—'}, Nato-digital, Público")

        passo = "enviar o PDF"
        jeito = _enviar_pdf(frame, caminho_pdf, dialogos)
        _diag(f"  PDF na Lista de Anexos ({jeito})")

        passo = "clicar em Salvar"
        if antes_de_salvar is not None:
            antes_de_salvar()
        clicou_salvar = True
        _salvar(aba_sei, frame, dialogos)
        _aguardar_rede(aba_sei, 8000)
        _diag(f"  salvo: {descricao}")
    except KeyboardInterrupt:
        raise
    except BaseException as erro:
        # Depois do clique no Salvar só a recusa explícita do SEI garante que nada foi criado.
        criou = clicou_salvar and getattr(erro, "criou", True)
        base = registrar_falha_pdf(aba_sei, descricao, passo, erro, dialogos, frame)
        detalhe = (str(getattr(erro, "code", None) or erro).strip().splitlines() or [type(erro).__name__])[0]
        onde = f" Detalhes em {base}.txt" if base else ""
        raise FalhaPdf(f"falhou ao {passo}: {detalhe}.{onde}", criou=criou) from erro
    finally:
        try:
            aba_sei.remove_listener("dialog", ao_dialogo)
        except Exception:
            pass


def _voltar_ao_processo(aba_sei, processo: str) -> None:
    """Larga o formulário pela metade: recarrega a aba (o endereço mantém o código do SEI) e reabre o processo."""
    try:
        aba_sei.reload(timeout=60000)
    except PlaywrightError:
        pass
    _aguardar_rede(aba_sei, 8000)
    abrir_processo_sei(aba_sei, processo)
    _aguardar_rede(aba_sei)


def anexar_documento_pdf(
    context, aba_sei, progresso: ProgressoSei, avisos: list, processo: str,
    chave: str, descricao: str, texto_link: str, rotulo: str, arquivos: list[str],
    numero_pp: str = None, nome_arvore: str = "",
) -> None:
    """
    Inclui UM documento Externo com o PDF, sabendo retomar (mesmo
    progresso_sei.json e mesmas chaves do modo imagem):

        já salvo antes (em qualquer modo)   -> pula
        falha antes do Salvar               -> tenta de novo sozinho
        falha depois do Salvar              -> para e pede para conferir
    """
    estado = progresso.estado(chave)
    impressao = impressao_dos_arquivos(arquivos)
    pular, aviso = decidir_pulo(estado, impressao, descricao)
    if pular:
        print(f"\n⏭️  {descricao}: já foi anexado numa tentativa anterior -- pulando.")
        if aviso:
            avisos.append(aviso)
            print(f"   ⚠️  {aviso}")
        return

    if estado.get("estado") == "criado":
        avisos.append(
            f"{descricao}: ficou um documento VAZIO de uma tentativa anterior (modo imagem) no processo. "
            "O PDF entrou num documento novo -- exclua o vazio."
        )
        print(f"   ⚠️  {avisos[-1]}")
    elif estado.get("estado") == "criando":
        avisos.append(
            f"{descricao}: a tentativa anterior caiu no momento de salvar. "
            "Confira se este documento não ficou em dobro no processo."
        )
        print(f"   ⚠️  {avisos[-1]}")

    caminho_pdf, montado = pdf_do_documento(arquivos)
    if montado:
        avisos.append(
            f"{descricao}: o PDF original do SIGEF não estava na pasta (download de uma versão anterior); "
            "o PDF anexado foi montado com as imagens."
        )
    serie = SERIES_EXTERNO.get(texto_link, (texto_link,))[0]
    print(f"\n📄 {descricao} (PDF, {os.path.getsize(caminho_pdf) // 1024} KB) como Externo '{serie}'...")

    def _desfazer_criando() -> None:
        """O SEI recusou o Salvar: nada foi criado, a marca "criando" volta ao que era."""
        if progresso.estado(chave).get("estado") != "criando" or estado.get("estado") == "criando":
            return
        if estado:
            progresso.documentos[chave] = dict(estado)
        else:
            progresso.documentos.pop(chave, None)
        try:
            gravar_json(progresso.caminho, {"ob": progresso.ob, "documentos": progresso.documentos})
        except OSError:
            pass

    for tentativa in range(1, TENTATIVAS_ANTES_DE_SALVAR + 1):
        try:
            _aguardar_rede(aba_sei)
            incluir_externo(
                aba_sei, processo, texto_link, descricao, caminho_pdf, numero=numero_pp, nome_arvore=nome_arvore,
                antes_de_salvar=lambda: progresso.marcar(chave, "criando", formato=FORMATO_PDF),
            )
            break
        except FalhaPdf as erro:
            if erro.criou:
                raise SystemExit(
                    f"\n⚠️  {descricao}: {erro.code}\n\n"
                    "    Olhe o processo no SEI: se o documento apareceu na árvore, ele está pronto.\n"
                    "    Se não apareceu, rode de novo com o MESMO processo -- o programa avisa para\n"
                    "    conferir se ficou em dobro.\n"
                ) from None
            _desfazer_criando()
            if tentativa == TENTATIVAS_ANTES_DE_SALVAR:
                raise SystemExit(
                    f"\n⚠️  Não consegui anexar {descricao} como PDF depois de {tentativa} tentativa(s).\n"
                    f"    Último erro: {erro.code}\n\n"
                    "    Nada foi criado no SEI para este documento. Se foi a internet, rode de novo com o\n"
                    "    MESMO processo: o que já foi anexado é pulado. Se foi a tela (um campo ou tipo que\n"
                    "    não existe), mande o arquivo .txt citado acima para quem mantém o programa, ou rode\n"
                    "    python -m automacoes.sigef_sei.diagnostico_pdf <processo>\n"
                ) from None
            espera = ESPERAS_ENTRE_TENTATIVAS[min(tentativa, len(ESPERAS_ENTRE_TENTATIVAS)) - 1]
            print(f"   ⚠️  {erro.code}\n   Tentando de novo em {espera}s (tentativa {tentativa + 1} de {TENTATIVAS_ANTES_DE_SALVAR})...")
            time.sleep(espera)
            _voltar_ao_processo(aba_sei, processo)

    progresso.marcar(chave, "salvo", impressao=impressao, formato=FORMATO_PDF)
    print(f"   ✅ {descricao}: PDF anexado.")
