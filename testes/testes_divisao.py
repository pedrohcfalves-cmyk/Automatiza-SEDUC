"""
Testes offline da divisão em partes do etapa_sei2.py (limite de 2 MB do
SEI) e da largura da OB. Não abre navegador, não fala com SIGEF nem SEI.

    python testes/testes_divisao.py

Roda de qualquer pasta. O etapa_listar_baixar de verdade NÃO é
carregado: um substituto mínimo entra no lugar (só o que o etapa_sei2
importa dele), e a pasta de dados é uma pasta temporária.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

PASTA_AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(PASTA_AQUI)
PASTA_SIGEF_SEI = os.path.join(RAIZ, "automacoes", "sigef_sei")
sys.path.insert(0, RAIZ)

# ---- substitutos: etapa_listar_baixar (sempre) e playwright (se faltar) ----
_PASTA_DADOS = tempfile.mkdtemp(prefix="testes_sei2_")

_listar_baixar = types.ModuleType("automacoes.sigef_sei.etapa_listar_baixar")
_listar_baixar.PASTA_BASE = _PASTA_DADOS
_listar_baixar.URL_SEI = "https://sei.exemplo/"
_listar_baixar.abrir_processo_sei = lambda *a, **k: None
_listar_baixar.aviso_conferencia_final = lambda *a, **k: None
_listar_baixar.carregar_sessao = lambda: {}
_listar_baixar.nome_pasta_valido = lambda texto: "".join(c if c.isalnum() else "_" for c in texto)
_listar_baixar.obter_ou_criar_aba = lambda *a, **k: None
sys.modules["automacoes.sigef_sei.etapa_listar_baixar"] = _listar_baixar

try:
    import playwright.sync_api  # noqa: F401
except ImportError:
    _sync_api = types.ModuleType("playwright.sync_api")

    class _ErroPlaywright(Exception):
        pass

    class _TimeoutPlaywright(_ErroPlaywright):
        pass

    _sync_api.Error = _ErroPlaywright
    _sync_api.TimeoutError = _TimeoutPlaywright
    sys.modules["playwright"] = types.ModuleType("playwright")
    sys.modules["playwright.sync_api"] = _sync_api

from automacoes.sigef_sei import etapa_sei2 as sei  # noqa: E402

# Tamanho de base64 + folga de uma página no teto de 250.000 bytes.
PAGINA_CHEIA = 4 * -(-250_000 // 3) + sei.FOLGA_HTML_POR_IMAGEM_BYTES
LIMITE_UTIL = sei.LIMITE_DOCUMENTO_BYTES - sei.FOLGA_HTML_DOCUMENTO_BYTES


def _tamanhos_das_partes(tamanhos, partes):
    return [sum(tamanhos[i] for i in parte) for parte in partes]


class TestaDividirEmPartes(unittest.TestCase):
    def conferir_basico(self, tamanhos, partes):
        # ordem preservada, blocos seguidos, nenhuma página perdida/repetida
        self.assertEqual([i for parte in partes for i in parte], list(range(len(tamanhos))))
        for parte in partes:
            self.assertTrue(parte, "parte vazia")
            self.assertEqual(parte, list(range(parte[0], parte[-1] + 1)))
            if len(parte) > 1:
                self.assertLessEqual(sum(tamanhos[i] for i in parte), LIMITE_UTIL)

    def test_oito_paginas_cheias_viram_4_mais_4(self):
        tamanhos = [PAGINA_CHEIA] * 8
        partes = sei._dividir_em_partes(tamanhos, LIMITE_UTIL)
        self.conferir_basico(tamanhos, partes)
        self.assertEqual([len(p) for p in partes], [4, 4])

    def test_uma_pagina(self):
        self.assertEqual(sei._dividir_em_partes([PAGINA_CHEIA], LIMITE_UTIL), [[0]])

    def test_nenhuma_pagina(self):
        self.assertEqual(sei._dividir_em_partes([], LIMITE_UTIL), [])

    def test_cabe_tudo_numa_parte(self):
        tamanhos = [PAGINA_CHEIA] * 5  # 5 x 333.736 = 1.668.680 < 1.780.000
        self.assertEqual(sei._dividir_em_partes(tamanhos, LIMITE_UTIL), [list(range(5))])

    def test_quatorze_paginas_cheias_viram_3_partes(self):
        tamanhos = [PAGINA_CHEIA] * 14
        partes = sei._dividir_em_partes(tamanhos, LIMITE_UTIL)
        self.conferir_basico(tamanhos, partes)
        self.assertEqual(len(partes), 3)
        self.assertEqual(max(len(p) for p in partes), 5)  # 5+5+4, não 5+5+4 em outra ordem pior

    def test_pagina_maior_que_o_limite_fica_sozinha(self):
        tamanhos = [100, LIMITE_UTIL * 3, 100, 100]
        partes = sei._dividir_em_partes(tamanhos, LIMITE_UTIL)
        self.assertEqual(partes, [[0], [1], [2, 3]])
        self.assertEqual(sei._dividir_em_partes([LIMITE_UTIL + 1], LIMITE_UTIL), [[0]])
        # a página enorme não desequilibra as outras
        tamanhos = [PAGINA_CHEIA] * 4 + [LIMITE_UTIL * 2]
        partes = sei._dividir_em_partes(tamanhos, 3 * PAGINA_CHEIA)
        self.assertEqual([len(p) for p in partes], [2, 2, 1])

    def test_tamanhos_variados_menor_numero_e_equilibrio(self):
        import itertools
        import random

        sorteio = random.Random(20261015)
        for _ in range(400):
            n = sorteio.randint(1, 11)
            limite = sorteio.randint(500, 2000)
            tamanhos = [sorteio.randint(50, 900) for _ in range(n)]
            partes = sei._dividir_em_partes(tamanhos, limite)
            self.conferir_basico_limite(tamanhos, partes, limite)
            # força bruta: menor número de partes válidas e, com ele, menor "maior parte"
            melhor = None
            for cortes in itertools.product((0, 1), repeat=n - 1):
                blocos, atual = [], [0]
                for i, corta in enumerate(cortes, start=1):
                    if corta:
                        blocos.append(atual)
                        atual = []
                    atual.append(i)
                blocos.append(atual)
                if any(len(b) > 1 and sum(tamanhos[i] for i in b) > limite for b in blocos):
                    continue
                pesos = [sum(tamanhos[i] for i in b) for b in blocos]
                pesos = [p if p <= limite else 0 for p in pesos]
                chave = (len(blocos), max(pesos))
                melhor = chave if melhor is None or chave < melhor else melhor
            pesos = [p if p <= limite else 0 for p in _tamanhos_das_partes(tamanhos, partes)]
            self.assertEqual((len(partes), max(pesos)), melhor, (tamanhos, limite, partes))

    def conferir_basico_limite(self, tamanhos, partes, limite):
        self.assertEqual([i for parte in partes for i in parte], list(range(len(tamanhos))))
        for parte in partes:
            if len(parte) > 1:
                self.assertLessEqual(sum(tamanhos[i] for i in parte), limite)

    def test_deterministico(self):
        tamanhos = [300, 500, 200, 700, 100, 400, 600, 250]
        primeiro = sei._dividir_em_partes(tamanhos, 1000)
        for _ in range(20):
            self.assertEqual(sei._dividir_em_partes(list(tamanhos), 1000), primeiro)
        self.assertEqual(sei._dividir_em_partes([10] * 7, 40), [[0, 1, 2, 3], [4, 5, 6]])


class TestaErroDeTamanho(unittest.TestCase):
    def test_reconhece(self):
        mensagem = (
            "[Microsoft][ODBC Driver 18 for SQL Server] documento com imagem não pode "
            "exceder 2MB. Utilize a opção Documento Externo"
        )
        self.assertTrue(sei._eh_erro_de_tamanho(mensagem))
        self.assertTrue(sei._eh_erro_de_tamanho("DOCUMENTO COM IMAGEM NAO PODE"))
        self.assertTrue(sei._eh_erro_de_tamanho("Não pode EXCEDER 2 MB"))
        self.assertTrue(sei._eh_erro_de_tamanho("utilize a opção documento   externo"))

    def test_nao_confunde(self):
        for texto in ("", None, "Timeout 30000ms exceeded", "net::ERR_INTERNET_DISCONNECTED",
                      "CONFIRMAÇÃO FALHOU na CE: tem 0 imagem(ns)"):
            self.assertFalse(sei._eh_erro_de_tamanho(texto), texto)


class _Teclado:
    def press(self, _tecla):
        pass


class PaginaFalsa:
    """O mínimo de uma Page do Playwright que o _anexar_documento usa."""

    def __init__(self, url, texto_na_tela=""):
        self.url = url
        self.fechada = False
        self.keyboard = _Teclado()
        self.ouvintes = {}
        self.texto_na_tela = texto_na_tela

    @property
    def frames(self):
        return [_FrameFalso(self.texto_na_tela)] if self.texto_na_tela else []

    def on(self, evento, funcao):
        self.ouvintes.setdefault(evento, []).append(funcao)

    def is_closed(self):
        return self.fechada

    def close(self):
        self.fechada = True


class _FrameFalso:
    def __init__(self, texto):
        self.texto = texto

    def locator(self, _seletor):
        return self

    @property
    def first(self):
        return self

    def inner_text(self, timeout=None):
        return self.texto


class _DialogoFalso:
    def __init__(self, mensagem):
        self.message = mensagem
        self.fechado = False

    def dismiss(self):
        self.fechado = True


class AbaFalsa:
    def bring_to_front(self):
        pass

    def wait_for_load_state(self, *a, **k):
        pass


class TestaAnexarDocumento(unittest.TestCase):
    """_anexar_documento com as partes do navegador trocadas por gravadores."""

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="sei2_doc_")
        self.originais = {
            nome: getattr(sei, nome)
            for nome in ("_incluir_e_editar_documento", "_limpar_e_inserir_imagens", "_clicar_salvar_editor",
                         "_confirmar_imagens_persistidas", "_reabrir_editor", "_aguardar_rede")
        }
        self.sleep_original = sei.time.sleep
        self.criados, self.colados, self.confirmados, self.reabertos, self.esperas = [], [], [], [], []
        self.falha_confirmacao = None     # função(tentativa) -> SystemExit ou None
        self.dialogo_ao_salvar = None
        self.texto_na_tela = ""
        self.reabrir_funciona = True

        def incluir(context, aba_sei, texto_link, rotulo, numero_pp=None, antes_de_criar=None):
            if antes_de_criar:
                antes_de_criar()
            pagina = PaginaFalsa(f"https://sei/editor/{len(self.criados) + 1}", self.texto_na_tela)
            self.criados.append({"texto_link": texto_link, "rotulo": rotulo, "numero_pp": numero_pp,
                                 "pagina": pagina})
            return pagina

        def colar(pagina_editor, arquivos, rotulo):
            self.colados.append((pagina_editor.url, list(arquivos), rotulo))
            return object()

        def salvar(pagina_editor, frame_editor=None):
            if self.dialogo_ao_salvar:
                for ouvinte in pagina_editor.ouvintes.get("dialog", []):
                    ouvinte(_DialogoFalso(self.dialogo_ao_salvar))

        def confirmar(pagina_editor, qtd_esperada, rotulo):
            self.confirmados.append((pagina_editor.url, qtd_esperada))
            if self.falha_confirmacao:
                erro = self.falha_confirmacao(len(self.confirmados))
                if erro:
                    raise erro

        def reabrir(context, url):
            self.reabertos.append(url)
            return PaginaFalsa(url) if (self.reabrir_funciona and url) else None

        sei._incluir_e_editar_documento = incluir
        sei._limpar_e_inserir_imagens = colar
        sei._clicar_salvar_editor = salvar
        sei._confirmar_imagens_persistidas = confirmar
        sei._reabrir_editor = reabrir
        sei._aguardar_rede = lambda *a, **k: None
        sei.time.sleep = lambda segundos: self.esperas.append(segundos)

    def tearDown(self):
        for nome, funcao in self.originais.items():
            setattr(sei, nome, funcao)
        sei.time.sleep = self.sleep_original
        shutil.rmtree(self.pasta, ignore_errors=True)

    # ---- apoio ----

    def jpgs(self, quantidade, tamanho=250_000, prefixo="Despesa Certificada - CE 2026CE000123"):
        caminhos = []
        for i in range(1, quantidade + 1):
            caminho = os.path.join(self.pasta, f"{prefixo}_{i}.jpg")
            with open(caminho, "wb") as arquivo:
                arquivo.write(b"\xff" * tamanho)
            caminhos.append(caminho)
        return caminhos

    def progresso(self, documentos=None):
        progresso = sei.ProgressoSei("0029.001947/2026-67", "2026OB136475", pasta_base=self.pasta)
        if documentos:
            for chave, dados in documentos.items():
                progresso.marcar(chave, **dados)
            # relê do disco, como numa nova execução
            progresso = sei.ProgressoSei("0029.001947/2026-67", "2026OB136475", pasta_base=self.pasta)
        return progresso

    def gravado(self):
        with open(os.path.join(self.pasta, "0029_001947_2026_67", sei.ARQUIVO_PROGRESSO), encoding="utf-8") as f:
            return json.load(f)["documentos"]

    def anexar(self, progresso, arquivos, chave="CE 2026CE000123", descricao="CE 1/1 -- 2026CE000123",
               texto_link="Despesa Certificada", rotulo="CE", numero_pp=None, avisos=None):
        avisos = [] if avisos is None else avisos
        sei._anexar_documento(None, AbaFalsa(), progresso, avisos, chave, descricao, texto_link, rotulo,
                              arquivos, numero_pp=numero_pp)
        return avisos

    # ---- casos ----

    def test_a_uma_parte_mesma_chave_e_formato(self):
        progresso = self.progresso()
        arquivos = self.jpgs(3)
        avisos = self.anexar(progresso, arquivos)
        self.assertEqual(len(self.criados), 1)
        self.assertEqual(self.colados[0][1], arquivos)  # caminhos de sempre (já cabiam em 250 KB)
        self.assertEqual(self.confirmados, [("https://sei/editor/1", 3)])
        self.assertEqual(self.gravado(), {"CE 2026CE000123": {"estado": "salvo"}})  # sem "partes"
        self.assertEqual(avisos, [])

    def test_b_duas_partes(self):
        progresso = self.progresso()
        arquivos = self.jpgs(8)
        avisos = self.anexar(progresso, arquivos)
        self.assertEqual(len(self.criados), 2)
        self.assertEqual([c[1] for c in self.colados], [arquivos[:4], arquivos[4:]])
        self.assertEqual([qtd for _url, qtd in self.confirmados], [4, 4])  # imagens DA PARTE
        self.assertEqual(self.gravado(), {
            "CE 2026CE000123 · parte 1/2": {"estado": "salvo", "partes": 2},
            "CE 2026CE000123 · parte 2/2": {"estado": "salvo", "partes": 2},
        })
        self.assertEqual(len(avisos), 1)
        self.assertIn("dividida em 2 documentos (4 + 4 páginas)", avisos[0])
        self.assertIn("2 MB", avisos[0])

    def test_b2_pp_e_ob_repetem_numero_e_tipo(self):
        progresso = self.progresso()
        self.anexar(progresso, self.jpgs(8, prefixo="PP"), chave="PP 2026PP066790",
                    descricao="PP 1/1 -- PP 066790", texto_link="PP - Preparação de Pagamento",
                    rotulo="PP", numero_pp="066790")
        self.anexar(progresso, self.jpgs(7, prefixo="OB"), chave="OB", descricao="OB -- x",
                    texto_link=sei.TEXTO_LINK_OB_NORMAL, rotulo="OB")
        self.assertEqual([c["numero_pp"] for c in self.criados[:2]], ["066790", "066790"])
        self.assertEqual([c["texto_link"] for c in self.criados[2:]], [sei.TEXTO_LINK_OB_NORMAL] * 2)
        self.assertEqual([c["rotulo"] for c in self.criados[2:]], ["OB", "OB"])
        self.assertEqual([len(c[1]) for c in self.colados[2:]], [4, 3])

    def test_c_reaproveita_documento_vazio_como_parte_1(self):
        progresso = self.progresso({"CE 2026CE000123": {"estado": "criado", "url_editor": "https://sei/vazio"}})
        avisos = self.anexar(progresso, self.jpgs(8))
        self.assertEqual(self.reabertos, ["https://sei/vazio"])
        self.assertEqual(len(self.criados), 1)              # só a parte 2 é criada
        self.assertEqual(self.colados[0][0], "https://sei/vazio")
        self.assertEqual(set(self.gravado()), {"CE 2026CE000123 · parte 1/2", "CE 2026CE000123 · parte 2/2"})
        self.assertFalse(any("VAZIO" in aviso for aviso in avisos))

    def test_c2_nao_reabre_cria_outro_e_avisa_do_vazio(self):
        self.reabrir_funciona = False
        progresso = self.progresso({"CE 2026CE000123": {"estado": "criado", "url_editor": "https://sei/vazio"}})
        avisos = self.anexar(progresso, self.jpgs(8))
        self.assertEqual(len(self.criados), 2)
        self.assertTrue(any("VAZIO" in aviso for aviso in avisos))
        self.assertNotIn("CE 2026CE000123", self.gravado())

    def test_d_chave_original_salva_pula(self):
        progresso = self.progresso({"CE 2026CE000123": {"estado": "salvo"}})
        self.anexar(progresso, self.jpgs(8))
        self.assertEqual(self.criados, [])
        self.assertEqual(self.colados, [])

    def test_e_parte_1_salva_so_faz_a_parte_2(self):
        progresso = self.progresso({"CE 2026CE000123 · parte 1/2": {"estado": "salvo", "partes": 2}})
        arquivos = self.jpgs(8)
        self.anexar(progresso, arquivos)
        self.assertEqual(len(self.criados), 1)
        self.assertEqual(self.colados[0][1], arquivos[4:])
        self.assertEqual(self.gravado()["CE 2026CE000123 · parte 2/2"], {"estado": "salvo", "partes": 2})

    def test_e2_plano_diferente_do_gravado_avisa(self):
        progresso = self.progresso({"CE 2026CE000123 · parte 1/3": {"estado": "salvo", "partes": 3}})
        avisos = self.anexar(progresso, self.jpgs(8))
        self.assertTrue(any("de outro jeito" in aviso for aviso in avisos))
        self.assertEqual(len(self.criados), 2)

    def test_f_erro_de_tamanho_na_excecao_nao_repete(self):
        self.falha_confirmacao = lambda n: SystemExit(
            "[Microsoft][ODBC Driver 18 for SQL Server] documento com imagem não pode exceder 2MB."
        )
        with self.assertRaises(SystemExit) as parada:
            self.anexar(self.progresso(), self.jpgs(3))
        self.assertEqual(len(self.colados), 1)
        self.assertEqual(self.esperas, [])
        self.assertIn("2 MB", str(parada.exception.code))
        self.assertIn("NÃO é problema de internet", str(parada.exception.code))

    def test_f2_erro_de_tamanho_no_alerta_do_sei(self):
        self.dialogo_ao_salvar = "documento com imagem não pode exceder 2MB. Utilize a opção Documento Externo"
        self.falha_confirmacao = lambda n: SystemExit("❌ CONFIRMAÇÃO FALHOU na CE: tem 0 imagem(ns)")
        with self.assertRaises(SystemExit) as parada:
            self.anexar(self.progresso(), self.jpgs(3))
        self.assertEqual(len(self.colados), 1)
        self.assertIn("TAMANHO", str(parada.exception.code))

    def test_f3_erro_de_tamanho_no_texto_da_tela(self):
        self.texto_na_tela = "Erro: documento com imagem nao pode exceder 2MB"
        self.falha_confirmacao = lambda n: SystemExit("❌ CONFIRMAÇÃO FALHOU na CE: tem 0 imagem(ns)")
        with self.assertRaises(SystemExit):
            self.anexar(self.progresso(), self.jpgs(3))
        self.assertEqual(len(self.colados), 1)

    def test_outros_erros_seguem_com_3_tentativas(self):
        self.falha_confirmacao = lambda n: SystemExit("❌ CONFIRMAÇÃO FALHOU na CE: tem 0 imagem(ns)")
        with self.assertRaises(SystemExit) as parada:
            self.anexar(self.progresso(), self.jpgs(3))
        self.assertEqual(len(self.colados), 3)
        self.assertEqual(self.esperas, [5, 15])
        self.assertIn("Quase sempre é a internet", str(parada.exception.code))

    def test_falha_na_1a_tentativa_e_depois_salva(self):
        self.falha_confirmacao = lambda n: SystemExit("Timeout") if n == 1 else None
        self.anexar(self.progresso(), self.jpgs(2))
        self.assertEqual(len(self.colados), 2)
        self.assertEqual(self.gravado(), {"CE 2026CE000123": {"estado": "salvo"}})


class TestaPlanejarPartes(unittest.TestCase):
    def test_reduz_uma_vez_e_reaproveita(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("sem Pillow")
        import random

        pasta = tempfile.mkdtemp(prefix="sei2_plano_")
        try:
            sorteio = random.Random(1)
            caminhos = []
            for i in range(8):
                imagem = Image.new("RGB", (1653, 2337))
                imagem.putdata([(sorteio.randrange(256),) * 3 for _ in range(1653 * 2337)])
                caminho = os.path.join(pasta, f"Despesa Certificada - CE TESTE_{i + 1}.jpg")
                imagem.save(caminho, quality=95)
                caminhos.append(caminho)
            self.assertTrue(all(os.path.getsize(c) > 250_000 for c in caminhos))

            chamadas = []
            original = sei._preparar_imagem_para_insercao

            def contar(caminho, *a, **k):
                chamadas.append(caminho)
                return original(caminho, *a, **k)

            sei._preparar_imagem_para_insercao = contar
            try:
                partes = sei._planejar_partes(caminhos)
            finally:
                sei._preparar_imagem_para_insercao = original

            self.assertEqual(chamadas, caminhos)                       # uma vez por arquivo
            preparados = [c for parte in partes for c in parte]
            self.assertTrue(all(os.path.getsize(c) <= 250_000 for c in preparados))
            self.assertEqual([original(c) for c in preparados], preparados)  # de novo: inofensivo
            self.assertGreaterEqual(len(partes), 1)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)


class TestaLarguraOb(unittest.TestCase):
    def test_largura_por_tipo(self):
        self.assertEqual(sei.LARGURA_IMAGEM_NO_DOCUMENTO_PX, 800)
        self.assertEqual(sei.LARGURA_IMAGEM_POR_TIPO.get("OB"), 1000)
        for rotulo in ("CE", "NL", "PP"):
            self.assertEqual(sei.LARGURA_IMAGEM_POR_TIPO.get(rotulo, sei.LARGURA_IMAGEM_NO_DOCUMENTO_PX), 800)

    def test_ajustar_largura_manda_o_valor_pedido(self):
        recebido = []

        class Frame:
            def frame_element(self):
                return "iframe"

        class Pagina:
            def evaluate(self, _js, argumentos):
                recebido.append(argumentos[1])
                return {"ok": True, "qtd": 1}

        sei._ajustar_largura_imagens(Pagina(), Frame())
        sei._ajustar_largura_imagens(Pagina(), Frame(), 1000)
        self.assertEqual(recebido, [800, 1000])


class TestaNomesUsadosPorFora(unittest.TestCase):
    """Os nomes que main.py, lote.py e app_janela.py usam continuam existindo."""

    def test_nomes(self):
        for nome in ("executar_sei2", "ob_ja_concluida", "TEXTO_LINK_OB_REGULARIZACAO",
                     "TEXTO_LINK_OB_NORMAL", "aviso_conferencia_final", "ProgressoSei",
                     "_anexar_documento", "_preparar_imagem_para_insercao"):
            self.assertTrue(hasattr(sei, nome), nome)

    def test_assinaturas(self):
        with open(os.path.join(PASTA_SIGEF_SEI, "etapa_sei2.py"), encoding="utf-8") as arquivo:
            arvore = ast.parse(arquivo.read())
        funcoes = {no.name: no for no in arvore.body if isinstance(no, ast.FunctionDef)}

        def parametros(nome):
            argumentos = funcoes[nome].args
            return [a.arg for a in argumentos.args + argumentos.kwonlyargs]

        self.assertEqual(parametros("executar_sei2"),
                         ["context", "processo", "dados", "tipo_ob", "conferir_no_fim", "avisos_saida"])
        self.assertEqual(parametros("ob_ja_concluida"), ["processo", "ob", "pasta_base"])
        self.assertEqual(parametros("_anexar_documento"),
                         ["context", "aba_sei", "progresso", "avisos", "chave", "descricao", "texto_link",
                          "rotulo", "arquivos", "numero_pp"])
        self.assertEqual(parametros("_preparar_imagem_para_insercao"), ["caminho_arquivo", "limite_bytes_arquivo"])
        self.assertEqual(parametros("_limpar_e_inserir_imagens"), ["pagina_editor", "arquivos", "rotulo"])
        self.assertEqual(parametros("_confirmar_imagens_persistidas"),
                         ["pagina_editor", "qtd_esperada", "rotulo", "timeout_ms"])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(_PASTA_DADOS, ignore_errors=True)
