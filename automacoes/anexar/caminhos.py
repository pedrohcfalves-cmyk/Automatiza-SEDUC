"""
Onde cada arquivo fica -- um lugar só.

O CÓDIGO fica em anexar/. Os DADOS deste computador (o que a pessoa
digitou, as configurações, os relatórios e os registros) ficam todos na
pasta dados/, ao lado. Para atualizar o programa basta trocar a pasta
anexar/ (e os .bat): a pasta dados/ continua do jeito que está.

    dados/sessao_atual.json              últimos valores do processo
    dados/configuracoes_automacao.json   configurações da CE, PP, OB e Global
    dados/relatorios/                    tempos de cada processo (estatísticas)
    dados/relatorios_simulacao/          o mesmo, só do modo treino
    dados/registro_de_erros.txt          detalhes técnicos dos erros
    dados/registro_do_aplicativo.txt     registro simples do aplicativo

Versões até a 1.3.0 guardavam esses arquivos soltos na pasta do programa;
migrar_dados_antigos() os traz para dados/ na primeira vez.

Variável (usada nos testes): ANEXAR_PASTA_DADOS troca a pasta dados/.

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import os
import shutil
import sys

PASTA_CODIGO = os.path.dirname(os.path.abspath(__file__))           # .../automacoes/anexar
# A pasta do programa (a da Central de Automações). No .exe do instalador (PyInstaller) o código fica
# dentro de _internal/, então a pasta do programa é a do próprio .exe. Pelo código, é a pasta acima de
# automacoes/ -- de onde o executor roda como  python -m automacoes.anexar.aplicativo.executor.
CONGELADO = bool(getattr(sys, "frozen", False))
RAIZ = (os.path.dirname(os.path.abspath(sys.executable)) if CONGELADO
        else os.path.dirname(os.path.dirname(PASTA_CODIGO)))
PASTA_RECURSOS = os.path.join(PASTA_CODIGO, "janela", "recursos")
# A licença do Anexar Documentos vai junto com o código (automacoes/anexar/LICENSE).
ARQUIVO_LICENCA = os.path.join(PASTA_CODIGO, "LICENSE")

# Na Central, a pasta dados/ fica fora da pasta do programa (Documentos\Anexar Documentos): quem
# decide é janela/modulo_anexar.py, pela variável ANEXAR_PASTA_DADOS.
PASTA_DADOS = os.environ.get("ANEXAR_PASTA_DADOS") or os.path.join(RAIZ, "dados")

ARQUIVO_SESSAO = os.path.join(PASTA_DADOS, "sessao_atual.json")
ARQUIVO_CONFIGURACOES = os.path.join(PASTA_DADOS, "configuracoes_automacao.json")
ARQUIVO_REGISTRO_ERROS = os.path.join(PASTA_DADOS, "registro_de_erros.txt")
ARQUIVO_REGISTRO_APP = os.path.join(PASTA_DADOS, "registro_do_aplicativo.txt")
PASTA_RELATORIOS = os.path.join(PASTA_DADOS, "relatorios")
PASTA_RELATORIOS_TREINO = os.path.join(PASTA_DADOS, "relatorios_simulacao")
ARQUIVO_SESSAO_TREINO = os.path.join(PASTA_RELATORIOS_TREINO, "sessao_treino.json")

# Arquivo/pasta solto na pasta do programa (até a 1.3.0) -> lugar novo.
_ANTIGOS = {
    "sessao_atual.json": ARQUIVO_SESSAO,
    "configuracoes_automacao.json": ARQUIVO_CONFIGURACOES,
    "registro_de_erros.txt": ARQUIVO_REGISTRO_ERROS,
    "registro_do_aplicativo.txt": ARQUIVO_REGISTRO_APP,
    "relatorios": PASTA_RELATORIOS,
    "relatorios_simulacao": PASTA_RELATORIOS_TREINO,
}


def garantir_pasta(caminho_arquivo: str) -> None:
    """Cria a pasta de um arquivo antes de gravar nele."""
    os.makedirs(os.path.dirname(os.path.abspath(caminho_arquivo)), exist_ok=True)


def migrar_dados_antigos(raiz: str = None, destinos: dict = None) -> list:
    """
    Traz para dados/ o que as versões antigas deixavam solto na pasta do
    programa. Nunca apaga nem sobrescreve: se já existe no lugar novo, o
    antigo fica onde está. Devolve os nomes do que foi movido.
    """
    raiz = raiz or RAIZ
    movidos = []
    for nome, destino in (destinos or _ANTIGOS).items():
        origem = os.path.join(raiz, nome)
        if not os.path.exists(origem) or os.path.exists(destino):
            continue
        try:
            garantir_pasta(destino)
            shutil.move(origem, destino)
            movidos.append(nome)
        except OSError:
            continue   # sem permissão: o programa segue com o lugar novo (vazio)
    return movidos
