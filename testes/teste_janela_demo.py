"""
A página da janela (janela/interface/) clicada como um usuário, no modo
demonstração (?demo): sem Python por trás, sem SIGEF e sem SEI.

    python testes/teste_janela_demo.py

Confere as duas automações em abas separadas: a Ordem Bancária no módulo
"Anexar no SEI" (sem nada da NE) e a Nota de Empenho no módulo dela -- um
processo e lote, do começo ao fim --, e que o registro detalhado não cresce
sem limite. Precisa do Playwright com o Chromium dele; sem ele, os testes são pulados.
"""
import os
from datetime import date
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = "file:///" + os.path.join(RAIZ, "janela", "interface", "index.html").replace(os.sep, "/").lstrip("/") + "?demo"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright não instalado")
class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.navegador = cls.pw.chromium.launch()
        except Exception as erro:  # Chromium do Playwright não baixado
            cls.pw.stop()
            raise unittest.SkipTest(f"Chromium indisponível: {erro}")

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.pw.stop()

    def setUp(self):
        self.p = self.navegador.new_page(viewport={"width": 1200, "height": 860})
        self.erros = []
        self.p.on("pageerror", lambda e: self.erros.append(str(e)))
        self.p.goto(PAGINA)
        self.p.wait_for_selector("#tela-inicio:not([hidden])")

    def tearDown(self):
        self.p.close()
        self.assertEqual(self.erros, [], "erro de JavaScript na página")

    def marcar_todas(self, seletor):
        for caixa in self.p.locator(seletor).all():
            caixa.check(force=True)


class TesteOrdemBancaria(Base):
    """O módulo Anexar no SEI: só a OB, como na 3.8.5."""

    def setUp(self):
        super().setUp()
        self.p.click("#btn-comecar")
        self.p.wait_for_selector("#login-pronto:not([hidden])", timeout=10000)
        self.marcar_todas(".chk-login")
        self.p.click("#btn-login-ok")
        self.p.wait_for_selector("#tela-dados:not([hidden])")

    def test_evento_ruim_nao_derruba_os_seguintes(self):
        # "lote_inicio" sem itens faz o tratador lançar; o "erro" que vem depois tem que aparecer
        self.p.evaluate("""lba.receber([{tipo: "lote_inicio"}, {tipo: "erro", fase: "processar", mensagem: "falha de teste"}])""")
        self.p.wait_for_selector("#erro:not([hidden])", timeout=3000)
        self.assertIn("falha de teste", self.p.inner_text("#erro"))

    def test_regioes_vivas_para_leitor_de_tela(self):
        for seletor in ("#erro", "#ne-erro"):
            self.assertEqual(self.p.get_attribute(seletor, "role"), "alert", seletor)
        for seletor in ("#agora", "#ne-agora"):
            self.assertEqual(self.p.get_attribute(seletor, "aria-live"), "polite", seletor)
        self.assertEqual(self.p.locator("#registro[aria-live], #registro [aria-live]").count(), 0,
                         "o registro recebe linhas demais para ser lido em voz alta")

    def test_foco_vai_para_o_titulo_ao_trocar_de_tela(self):
        self.p.evaluate("""lba.receber([{tipo: "erro", fase: "processar", mensagem: "x"}])""")
        self.p.wait_for_selector("#tela-execucao:not([hidden])")
        self.assertEqual(self.p.evaluate("document.activeElement.tagName"), "H1")
        self.assertTrue(self.p.evaluate("document.activeElement.closest('#tela-execucao') !== null"))

    def test_nada_da_ne_na_tela_da_ob(self):
        self.assertNotIn("Nota de Empenho", self.p.inner_html("#tela-dados"))
        self.assertEqual(self.p.locator("#tela-dados [id^='ne-'], #tela-dados [name='assunto']").count(), 0)
        self.assertTrue(self.p.is_visible("#campo-ob"))
        self.assertTrue(self.p.is_visible("#campo-docs"))
        self.assertTrue(self.p.is_hidden("#ne-versao-lateral"), "a versão da NE só aparece na aba dela")
        self.assertEqual(self.p.text_content("#dados-titulo"), "Informe o processo e a Ordem Bancária")

    def test_um_processo(self):
        self.p.fill("#in-processo", "0029001947202667")
        self.p.fill("#in-ob", "2026OB136475")
        self.p.locator('input[name="tipo-ob"][value="regularizacao"]').check(force=True)
        self.p.click("#btn-processar")
        self.p.wait_for_selector("#tela-execucao:not([hidden])")
        self.p.wait_for_selector("#resumo:not([hidden])", timeout=15000)
        self.assertIn("2026OB136475", self.p.text_content("#resumo"))
        self.p.wait_for_selector("#tela-conferencia:not([hidden])", timeout=20000)
        self.marcar_todas(".chk-conf")
        self.p.click("#btn-conf-ok")
        self.p.wait_for_selector("#tela-concluido:not([hidden])", timeout=10000)
        self.assertIn("Ordem Bancária", self.p.text_content("#btn-outra"))

    def test_lote(self):
        self.p.click("#aba-lote")
        self.p.fill("#in-lista", "0029.001947/2026-67 2026OB136475\n0029.001948/2026-11 136476 Ordem Bancária")
        self.p.wait_for_function("document.querySelector('#btn-lote-txt').textContent === 'Processar 2 OBs'")
        self.p.click("#btn-lote")
        self.p.wait_for_selector("#tela-lote-fim:not([hidden])", timeout=20000)
        self.assertIn("2026OB136475", self.p.text_content("#lotefim-linhas"))

    def test_registro_tem_limite(self):
        self.p.evaluate(
            "() => { const ev = []; for (let i = 0; i < 4500; i++) ev.push({tipo: 'log', texto: 'linha ' + i});"
            " for (let i = 0; i < ev.length; i += 300) lba.receber(ev.slice(i, i + 300)); }"
        )
        # o login simulado do setUp já imprimiu algumas linhas antes destas
        self.p.wait_for_function("Number(document.querySelector('#registro-qtd').textContent) >= 4500")
        texto = self.p.text_content("#registro-txt")
        self.assertEqual(texto.count("\n"), 3000)
        self.assertTrue(texto.rstrip().endswith("linha 4499"))


class TesteNotaDeEmpenho(Base):
    """O módulo Nota de Empenho, na aba dele."""

    def setUp(self):
        super().setUp()
        self.p.select_option("#ano-sigef", "2026")  # os números abaixo são de 2026, seja qual for o ano do relógio
        self.p.click('.modulo[data-modulo="ne"]')
        self.p.wait_for_selector("#tela-ne:not([hidden]) #ne-p-inicio:not([hidden])")
        self.assertTrue(self.p.is_hidden("#passos"), "os passos da OB somem na aba da NE")
        self.assertTrue(self.p.is_visible("#ne-passos"), "e aparecem os da NE")
        self.assertEqual(self.passo_atual(), "inicio")
        self.p.click("#ne-btn-comecar")
        self.p.wait_for_selector("#ne-login-pronto:not([hidden])", timeout=10000)
        self.marcar_todas(".ne-chk-login")
        self.p.click("#ne-btn-login-ok")
        self.p.wait_for_selector("#ne-p-dados:not([hidden])")
        self.assertEqual(self.passo_atual(), "dados")

    def passo_atual(self):
        return self.p.get_attribute("#ne-passos li.atual", "data-ne-passo")

    def test_uma_ne_do_comeco_ao_fim(self):
        self.p.fill("#ne-in-processo", "0029001947202667")
        self.p.fill("#ne-in-ne", "2025NE000123")  # outro exercício: recusa
        self.p.click("#ne-btn-processar")
        self.p.wait_for_function("document.querySelector('#ne-campo-ne').classList.contains('invalido')")
        self.assertTrue(self.p.is_visible("#ne-p-dados"))

        self.p.fill("#ne-in-ne", "123")
        self.p.click("#ne-btn-processar")
        self.p.wait_for_selector("#ne-p-execucao:not([hidden])")
        self.assertEqual(self.p.text_content("#ne-exec-ne"), "2026NE000123")
        self.assertEqual(self.p.text_content("#ne-exec-processo"), "0029.001947/2026-67")
        self.p.wait_for_selector("#ne-resumo:not([hidden])", timeout=15000)
        self.assertIn("Nota de Empenho - NE 000123_2.png", self.p.text_content("#ne-resumo"))
        self.p.wait_for_selector("#ne-p-conferencia:not([hidden])", timeout=15000)
        self.assertEqual(self.passo_atual(), "conferencia")
        self.assertEqual(self.p.locator("#ne-passos li.feito").count(), 4)
        self.assertTrue(self.p.is_disabled("#ne-btn-conf-ok"))
        self.marcar_todas(".ne-chk-conf")
        self.p.click("#ne-btn-conf-ok")
        self.p.wait_for_selector("#ne-p-concluido:not([hidden])", timeout=10000)
        self.assertIn("2026NE000123", self.p.text_content("#ne-fim-ne"))

        self.p.click("#ne-btn-outra")
        self.p.wait_for_selector("#ne-p-dados:not([hidden])")
        self.assertEqual(self.p.input_value("#ne-in-ne"), "")
        self.assertIn("Próximo processo e Nota de Empenho", self.p.text_content("#ne-dados-titulo"))

    def test_lote(self):
        self.p.click("#ne-aba-lote")
        self.p.fill("#ne-in-lista", "0029.001947/2026-67 2026NE000001\n0029.001948/2026-11 000002\nlixo 1")
        self.p.wait_for_function("document.querySelectorAll('#ne-lote-linhas tr').length === 3")
        self.assertEqual(self.p.text_content("#ne-btn-lote-txt"), "Processar 2 NEs")
        self.p.click("#ne-btn-lote")
        self.p.wait_for_selector("#ne-p-lotefim:not([hidden])", timeout=20000)
        self.assertIn("000001", self.p.text_content("#ne-lotefim-linhas"))
        self.assertIn("média por NE", self.p.text_content("#ne-lotefim-contadores"))
        self.assertTrue(self.p.is_visible("#ne-btn-lote-refazer"), "a demonstração tem uma NE com erro")

    def test_trocar_de_aba_nao_mistura(self):
        self.p.fill("#ne-in-processo", "0029001947202667")
        self.p.fill("#ne-in-ne", "123")
        self.p.click('.modulo[data-modulo="sei"]')
        self.p.wait_for_selector("#tela-inicio:not([hidden])")
        self.assertTrue(self.p.is_hidden("#tela-ne"))
        self.assertTrue(self.p.is_hidden("#ne-passos"))
        self.assertTrue(self.p.is_visible("#passos"))
        self.assertEqual(self.p.input_value("#in-processo"), "")
        self.p.click('.modulo[data-modulo="ne"]')
        self.p.wait_for_selector("#ne-p-dados:not([hidden])")
        self.assertEqual(self.p.input_value("#ne-in-ne"), "123")  # a NE lembra onde parou

    def test_nome_na_arvore(self):
        self.assertTrue(self.p.is_visible("#ne-in-arvore"), "campo do nome na árvore na etapa 3")
        self.assertEqual(self.p.get_attribute("#ne-in-arvore", "maxlength"), "50")
        enviados = []
        self.p.expose_function("anotar", lambda d: enviados.append(d))
        self.p.evaluate("""() => { const original = lbaNe.DEMO.chamar.bind(lbaNe.DEMO);
            lbaNe.DEMO.chamar = (acao, d) => { if (acao === "processar") anotar(d); return original(acao, d); }; }""")
        self.p.fill("#ne-in-processo", "0029001947202667")
        self.p.fill("#ne-in-ne", "123")
        self.p.fill("#ne-in-arvore", "  Empenho do contrato 12 ")
        self.p.click("#ne-btn-processar")
        self.p.wait_for_selector("#ne-p-execucao:not([hidden])")
        self.assertEqual(enviados[-1]["nome_arvore"], "Empenho do contrato 12")

    def test_versao_da_ne_na_aba(self):
        self.assertTrue(self.p.is_visible("#ne-versao-lateral"))
        self.assertEqual(self.p.text_content("#ne-versao-lateral"), "automação NE versão demo")
        self.assertIn("automação NE versão demo", self.p.text_content("#ne-p-inicio .sobre"))  # e no passo 1

    def test_relatorio_da_ne_e_o_geral(self):
        self.p.click("#ne-btn-relatorio")
        self.p.wait_for_selector("#painel-modal:not([hidden])")
        self.assertEqual(self.p.input_value("#painel-min-ne"), "15")
        self.p.keyboard.press("Escape")
        self.assertTrue(self.p.is_hidden("#painel-modal"))
        self.assertEqual(self.p.evaluate("document.activeElement.id"), "ne-btn-relatorio")  # o foco volta


class TesteGeral(Base):
    """O menu do topo: vale para todas as automações."""

    def test_ano_do_sigef_em_todas_as_abas(self):
        atual = str(date.today().year)
        self.p.wait_for_function("document.querySelector('#ano-sigef').options.length > 0")
        self.assertEqual(self.p.input_value("#ano-sigef"), atual)  # padrão: o ano atual
        self.assertEqual(self.p.text_content("#ano-sigef-aviso"), "")
        for modulo in ("sei", "ne", "dare", "bb"):
            self.p.click(f'.modulo[data-modulo="{modulo}"]')
            self.assertTrue(self.p.is_visible("#ano-sigef"), modulo)

    def test_trocar_o_ano_vale_para_a_ne(self):
        self.p.wait_for_function("document.querySelector('#ano-sigef').options.length > 0")
        self.p.select_option("#ano-sigef", "2024")
        self.p.wait_for_function("document.querySelector('#ano-sigef-aviso').textContent.includes('2024')")
        self.p.click('.modulo[data-modulo="ne"]')
        self.assertEqual(self.p.text_content("[data-ne-ano]"), "2024")
        self.p.click("#ne-btn-comecar")
        self.p.wait_for_selector("#ne-login-pronto:not([hidden])", timeout=10000)
        self.marcar_todas(".ne-chk-login")
        self.p.click("#ne-btn-login-ok")
        self.p.wait_for_selector("#ne-p-dados:not([hidden])")
        self.p.fill("#ne-in-processo", "0029001947202667")
        self.p.fill("#ne-in-ne", "123")
        self.p.click("#ne-btn-processar")
        self.p.wait_for_selector("#ne-p-execucao:not([hidden])")
        self.assertEqual(self.p.text_content("#ne-exec-ne"), "2024NE000123")

    def test_relatorio_geral(self):
        self.assertEqual(self.p.locator("#modal-relatorio, #ne-modal-relatorio, #btn-relatorio-lateral").count(), 0)
        self.p.click("#btn-relatorio-geral")
        self.p.wait_for_selector("#painel-modal:not([hidden])")
        self.assertEqual(self.p.input_value("#painel-min-ob"), "20")
        self.assertEqual(self.p.locator("#painel-pastas li").count(), 1)  # só esta máquina
        self.p.click("#painel-modal summary >> text=Pessoas no relatório")
        self.p.click("#painel-incluir")
        self.p.wait_for_function("document.querySelectorAll('#painel-pastas li').length === 2")
        self.assertIn("maria", self.p.text_content("#painel-pastas"))
        self.p.click("#painel-pastas button[data-remover]")
        self.p.wait_for_function("document.querySelectorAll('#painel-pastas li').length === 1")
        self.p.click("#painel-gerar")  # na demonstração não há Python: mostra o aviso e fica aberto
        self.p.wait_for_selector("#painel-erro:not([hidden])")
        self.p.click("#painel-cancelar")
        self.assertTrue(self.p.is_hidden("#painel-modal"))

    def test_atalhos_de_periodo(self):
        self.p.click("#btn-relatorio-geral")
        self.p.wait_for_selector("#painel-modal:not([hidden])")
        self.p.click('[data-periodo="mes-passado"]')
        hoje = date.today()
        ultimo = date(hoje.year, hoje.month, 1).toordinal() - 1
        self.assertEqual(self.p.input_value("#painel-ate"), date.fromordinal(ultimo).isoformat())
        self.assertEqual(self.p.get_attribute('[data-periodo="mes-passado"]', "aria-pressed"), "true")
        self.assertEqual(self.p.get_attribute('[data-periodo="mes"]', "aria-pressed"), "false")

    def test_tab_nao_sai_do_dialogo(self):
        self.p.click("#btn-acessibilidade")
        self.p.wait_for_selector("#acess-modal:not([hidden])")
        for _ in range(12):
            self.p.keyboard.press("Tab")
            self.assertTrue(self.p.evaluate("document.getElementById('acess-modal').contains(document.activeElement)"))


class TesteAcessibilidade(Base):
    """O modo de acessibilidade vale para o aplicativo inteiro, não para cada automação."""

    def zoom(self):
        return self.p.evaluate("document.documentElement.style.zoom || '1'")

    def test_tamanho_do_texto_vale_em_todas_as_abas_e_fica_guardado(self):
        self.p.click("#btn-acessibilidade")
        self.p.check('input[name="acess-tamanho"][value="1.3"]', force=True)
        self.p.click("#acess-fechar")
        self.assertEqual(self.zoom(), "1.3")
        for modulo in ("ne", "dare", "cadastro", "bb"):
            self.p.click(f'.modulo[data-modulo="{modulo}"]')
            self.assertEqual(self.zoom(), "1.3")
        # Nada sai para fora da janela com a letra maior.
        self.assertLessEqual(self.p.evaluate("document.documentElement.scrollWidth"), 1200)
        self.p.reload()
        self.p.wait_for_selector("#tela-inicio:not([hidden])")
        self.assertEqual(self.zoom(), "1.3")

    def test_atalhos_do_teclado(self):
        self.p.keyboard.press("Control+=")
        self.assertEqual(self.zoom(), "1.15")
        self.p.keyboard.press("Control+=")
        self.p.keyboard.press("Control+-")
        self.assertEqual(self.zoom(), "1.15")
        self.p.keyboard.press("Control+0")
        self.assertEqual(self.zoom(), "1")

    def test_contraste_foco_movimento_e_padrao(self):
        self.p.click("#btn-acessibilidade")
        for opcao in ("contraste", "foco", "movimento", "espaco"):
            self.p.check(f"#acess-{opcao}")
            self.assertTrue(self.p.evaluate(f"document.documentElement.hasAttribute('data-acess-{opcao}')"))
        self.assertIn("ligado", self.p.get_attribute("#btn-acessibilidade", "class"))
        self.p.click("#acess-padrao")
        self.assertFalse(self.p.evaluate("document.documentElement.hasAttribute('data-acess-contraste')"))
        self.assertEqual(self.zoom(), "1")

    def test_sem_botoes_de_letra_nas_automacoes(self):
        self.assertEqual(self.p.locator("[data-anx-letra], #cad-letra-maior, #cad-letra-menor").count(), 0)

    def test_pular_para_o_conteudo(self):
        self.p.keyboard.press("Tab")
        self.assertEqual(self.p.evaluate("document.activeElement.className"), "pular")



class TesteLayout(Base):
    """Automações e o resto do menu na lateral; no topo, os passos no meio, o ano e a acessibilidade."""

    def test_lateral_e_topo(self):
        lateral = self.p.locator("aside.lateral")
        self.assertEqual(lateral.locator(".modulo").count(), 6)
        for item in ("#btn-relatorio-geral", "#btn-pasta-lateral", "#versao", "#contador"):
            self.assertEqual(lateral.locator(item).count(), 1, item)
        topo = self.p.locator("header.topo-app")
        for item in ("#passos", "#ne-passos", "#cad-passos", "#dare-nav", "#anx-nav", "#ano-sigef", "#btn-acessibilidade"):
            self.assertEqual(topo.locator(item).count(), 1, item)
        # Os passos ficam no meio da faixa dos passos, numa linha só.
        caixa = self.p.locator(".topo-passos").bounding_box()
        passos = self.p.locator("#passos").bounding_box()
        meio = lambda b: b["x"] + b["width"] / 2  # noqa: E731
        self.assertLess(abs(meio(caixa) - meio(passos)), 2)
        self.assertLess(passos["height"], 45)
        self.assertLessEqual(self.p.evaluate("document.documentElement.scrollWidth"), 1200)

    def test_cada_automacao_mostra_os_passos_dela(self):
        visiveis = lambda: [i for i in ("passos", "ne-passos", "cad-passos", "dare-nav", "anx-nav")  # noqa: E731
                            if self.p.is_visible(f"#{i}")]
        self.assertEqual(visiveis(), ["passos"])
        for modulo, nav in (("ne", "ne-passos"), ("dare", "dare-nav"), ("anexar", "anx-nav"), ("cadastro", "cad-passos")):
            self.p.click(f'.modulo[data-modulo="{modulo}"]')
            self.assertEqual(visiveis(), [nav], modulo)

    def test_janela_estreita_lateral_so_com_icones(self):
        self.p.set_viewport_size({"width": 900, "height": 800})
        self.assertLess(self.p.locator("aside.lateral").bounding_box()["width"], 80)
        self.assertLessEqual(self.p.evaluate("document.documentElement.scrollWidth"), 900)
        self.assertEqual(self.p.get_attribute('.modulo[data-modulo="dare"]', "data-modulo"), "dare")
        self.assertIn("DARE", self.p.inner_text('.modulo[data-modulo="dare"]'))  # o nome continua para o leitor de tela


class TesteEntrarAntesDeComecar(Base):
    """DARE e BB pedem o login (com o Chrome só com as abas deles) antes de começar."""

    def marcar_login(self):
        for caixa in self.p.locator("#entrar-checagem input").all():
            caixa.evaluate("e => e.click()")

    def iniciar_dare(self):
        self.p.click('.modulo[data-modulo="dare"]')
        self.p.click('[data-dare-ir="lancamentos"]')
        self.p.click("#dare-btn-iniciar")
        self.p.click("#dare-confirma .btn.primario")
        self.p.wait_for_selector("#entrar-modal:not([hidden])")

    def test_dare_cancelar_nao_comeca(self):
        self.iniciar_dare()
        self.p.wait_for_selector("#entrar-pronto:not([hidden])")
        self.assertIn("DARE e SEI", self.p.inner_text("#entrar-abas"))
        self.assertEqual(self.p.locator("#entrar-checagem input").count(), 3)  # DARE, SEI e a gerência
        self.assertTrue(self.p.is_disabled("#entrar-ok"))
        self.p.keyboard.press("Escape")
        self.assertTrue(self.p.is_hidden("#entrar-modal"))
        self.assertEqual(self.p.get_attribute('[data-dare-ir="lancamentos"]', "class"), "ativo")

    def test_dare_confirmar_comeca_e_nao_pede_de_novo(self):
        self.iniciar_dare()
        self.p.wait_for_selector("#entrar-pronto:not([hidden])")
        self.marcar_login()
        self.assertFalse(self.p.is_disabled("#entrar-ok"))
        self.p.click("#entrar-ok")
        self.p.wait_for_selector('[data-dare-ir="execucao"].ativo')
        self.assertTrue(self.p.is_hidden("#entrar-modal"))
        self.assertTrue(self.p.evaluate("window.lbaLogin.exigir('dare')"))  # já confirmado nesta sessão

    def test_bb(self):
        self.p.click('.modulo[data-modulo="bb"]')
        self.p.click("#bb-executar")
        self.p.wait_for_selector("#entrar-pronto:not([hidden])")
        self.assertIn("Banco do Brasil e SEI", self.p.inner_text("#entrar-abas"))
        self.p.click("#entrar-cancelar")
        self.assertIn("Entre no Banco do Brasil", self.p.inner_text("#bb-status"))
        self.p.click("#bb-executar")
        self.p.wait_for_selector("#entrar-pronto:not([hidden])")
        self.marcar_login()
        self.p.click("#entrar-ok")
        self.p.wait_for_selector("#bb-pergunta:not([hidden])")  # a demonstração começou

    def test_erro_ao_abrir_e_tentar_de_novo(self):
        self.p.evaluate("""() => {
            const real = window.pywebview;
            let vez = 0;
            window.pywebview = { api: { geral: async (acao, d) => {
                if (acao === "login_estado") return { ok: true, sistemas: ["DARE", "SEI"], confirmado: false };
                if (acao === "abrir_abas") return ++vez === 1 ? { ok: false, erro: "Chrome não encontrado" } : { ok: true, sistemas: ["DARE", "SEI"] };
                return { ok: true };
            } } };
        }""")
        self.p.evaluate("() => { window.__resposta = window.lbaLogin.exigir('dare'); }")
        self.p.wait_for_selector("#entrar-erro:not([hidden])")
        self.assertIn("Chrome não encontrado", self.p.inner_text("#entrar-erro-msg"))
        self.p.click("#entrar-tentar")
        self.p.wait_for_selector("#entrar-pronto:not([hidden])")
        self.marcar_login()
        self.p.click("#entrar-ok")
        self.assertTrue(self.p.evaluate("window.__resposta"))


if __name__ == "__main__":
    unittest.main()
