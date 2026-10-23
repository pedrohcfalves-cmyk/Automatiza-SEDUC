"""
Cache da janela (WebView2).

A interface (janela/interface/*.html, *.js, *.css) é carregada de arquivos
locais, e o WebView2 guarda uma cópia delas no cache da pasta da janela.
Instalada uma versão nova por cima, a janela continuava mostrando a tela
ANTIGA (a versão na barra lateral, que vem do Python, já aparecia como a
nova): foi o que escondeu as caixas de documentos da 3.8.

limpar() apaga só esse cache de arquivos, a cada abertura do programa. O
que a janela guarda de uso (cookies, armazenamento local) não é tocado.
Se a pasta estiver em uso (outra janela aberta), ou não existir, segue
sem erro -- no pior caso o cache antigo fica até a próxima abertura.
"""
import os
import shutil

# Dentro de <pasta da janela>/EBWebView/Default.
PASTAS_DE_CACHE = ("Cache", "Code Cache", "GPUCache")


def limpar(pasta_janela: str) -> list[str]:
    """Apaga o cache de arquivos do WebView2. Devolve o que apagou."""
    apagadas = []
    base = os.path.join(pasta_janela, "EBWebView", "Default")
    for nome in PASTAS_DE_CACHE:
        caminho = os.path.join(base, nome)
        if not os.path.isdir(caminho):
            continue
        try:
            shutil.rmtree(caminho)
            apagadas.append(nome)
        except OSError:
            pass  # em uso ou sem permissão: fica para a próxima
    return apagadas
