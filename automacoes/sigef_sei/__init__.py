"""
Automação SIGEF -> SEI: a partir de uma Ordem Bancária, baixa do SIGEF
os documentos vinculados (CE, NL, PP, OB) e os anexa no processo do SEI.

    preparar_navegador.py   abre o Chrome da automação e espera o login
    etapa_listar_baixar.py  baixa os documentos do SIGEF  (baixar_documentos)
    etapa_sei2.py           anexa os documentos no SEI    (executar_sei2)
    lote.py                 várias OBs em sequência, a partir de planilha/lista
    metricas.py             cronômetro de cada OB (metricas/metricas.csv)
    relatorio_gerencial.py  relatório HTML de tempo economizado

As portas de entrada são o main.py e o app_janela.py, na raiz.
"""
