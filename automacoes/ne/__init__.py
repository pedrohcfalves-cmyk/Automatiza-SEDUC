"""
Nota de Empenho (NE): imprime a NE no SIGEF, converte cada página do PDF
em imagem e anexa no processo do SEI como "NE - Nota de Empenho".

Usa as mesmas peças da automação SIGEF -> SEI (automacoes/sigef_sei/): o
Chrome da automação, o login, a retomada depois de queda, a divisão por
tamanho do SEI e a redução das imagens. Na janela, aparece como a opção
"Nota de Empenho" do módulo Anexar no SEI.

    etapa.py      uma NE: baixa do SIGEF (baixar_ne) e anexa no SEI (anexar_ne)
    lote.py       várias NEs a partir de planilha/lista
    metricas.py   cronômetro de cada NE (metricas/metricas_ne.csv)
    relatorio.py  relatório gerencial HTML das NEs
    terminal.py   a NE sozinha, pela tela preta (python -m automacoes.ne.terminal)
"""

# Versão da automação da NE (aparece na aba da NE). Continua a do programa
# "Automação NE" (2.0.2), que virou este módulo. Suba a cada mudança na NE.
__version__ = "2.1.0"
