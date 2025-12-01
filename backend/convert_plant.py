import cv2
import numpy as np
import ezdxf
import os


def imagem_para_dxf(caminho_imagem, nome_dxf_saida="planta_vetorizada.dxf"):
    """
    Converte uma imagem de planta baixa (incluindo blueprints) para DXF.
    - Otimiza a binarização para rascunhos.
    - Filtra ruído (texto/pontos).
    - Exporta para o layer 'VS - Parede'.
    """
    print(f"Iniciando o processamento da imagem: {caminho_imagem}")

    # 1. Carregar a Imagem e Pré-processamento
    imagem = cv2.imread(caminho_imagem)
    if imagem is None:
        print(f"ERRO: Não foi possível carregar a imagem em {caminho_imagem}")
        return

    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

    # Suaviza a imagem para reduzir o ruído (ajuda o limiar)
    cinza_blur = cv2.GaussianBlur(cinza, (5, 5), 0)

    # 2. Limiarização (Binarização)

    # 🚨 PONTO DE AJUSTE: Ajuste este valor (ex: 50, 60, 80, 100...) para nitidez.
    # Para blueprints claros, valores BAIXOS tendem a funcionar melhor.
    limiar_ajuste = 100

    _, binarizada = cv2.threshold(cinza_blur, limiar_ajuste, 255, cv2.THRESH_BINARY_INV)

    # --- CÓDIGO DE DIAGNÓSTICO ---
    nome_teste = f"TESTE_BINARIZADA_{os.path.basename(caminho_imagem)}"
    cv2.imwrite(nome_teste, binarizada)
    print(f"Arquivo de teste de binarização salvo como: {nome_teste}")
    # ----------------------------

    # 3. Detecção de Contornos
    contornos, _ = cv2.findContours(binarizada, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    print(f"Contornos detectados (antes do filtro): {len(contornos)}")

    # 4. Geração do Arquivo DXF
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    fator_escala = 0.01

    # 🚨 PONTO DE AJUSTE: Área mínima para filtrar texto e ruído
    area_minima_contorno = 200

    # Iterar sobre os contornos e desenhá-los
    for i, contorno in enumerate(contornos):
        area = cv2.contourArea(contorno)

        # Filtra contornos pequenos (ruído e texto)
        if area < area_minima_contorno:
            continue

        # Simplificação: Otimiza o número de pontos nas linhas
        epsilon = 0.005 * cv2.arcLength(contorno, True)
        contorno_simplificado = cv2.approxPolyDP(contorno, epsilon, True)

        if len(contorno_simplificado) > 1:
            # Extrai as coordenadas e aplica o fator de escala
            pontos_dxf = [
                (p[0][0] * fator_escala, p[0][1] * fator_escala)
                for p in contorno_simplificado
            ]

            # 🚨 EXPORTA PARA O LAYER CORRETO: 'VS - Parede'
            msp.add_polyline2d(
                pontos_dxf, dxfattribs={"layer": "VS - Parede", "color": 7}
            )

    # Salvar o arquivo DXF
    try:
        doc.saveas(nome_dxf_saida)
        print(
            f"\n✅ Sucesso! Arquivo DXF salvo como: {os.path.abspath(nome_dxf_saida)}"
        )
    except IOError as e:
        print(f"ERRO ao salvar o arquivo DXF: {e}")


print("--- CONVERTENDO O 1º PISO ---")
imagem_primeiro_piso = "images/inferior.jpeg"
dxf_saida_primeiro = "planta_primeiro_piso.dxf"
imagem_para_dxf(imagem_primeiro_piso, dxf_saida_primeiro)

print("\n--- CONVERTENDO O 2º PISO ---")
imagem_segundo_piso = "images/superior2.png"
dxf_saida_segundo = "planta_segundo_piso.dxf"
imagem_para_dxf(imagem_segundo_piso, dxf_saida_segundo)
