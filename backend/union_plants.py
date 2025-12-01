import ezdxf
import os


def juntar_arquivos_dxf(
    dxf_primeiro, dxf_segundo, distancia_offset_x, nome_dxf_saida="projeto_completo.dxf"
):
    """
    Junta duas plantas DXF em um único arquivo, aplicando um deslocamento (offset)
    no segundo arquivo para que fiquem lado a lado.
    """
    print(f"Iniciando a união de: {dxf_primeiro} e {dxf_segundo}")

    # 1. Cria um Novo Documento DXF Mestre
    doc_mestre = ezdxf.new("R2010")
    msp_mestre = doc_mestre.modelspace()

    # Cria uma nova camada para o Segundo Piso (Ajuda na organização visual no CAD)
    doc_mestre.layers.new(name="PISO_2_DESLOCADO", dxfattribs={"color": 2})

    # --- Processamento do Primeiro Piso (SEM OFFSET) ---
    try:
        doc_piso1 = ezdxf.readfile(dxf_primeiro)
        msp_piso1 = doc_piso1.modelspace()

        # 🚨 CORREÇÃO DE ERRO: Itera e adiciona entidades uma a uma
        for entity in msp_piso1:
            msp_mestre.add_entity(entity.copy())

        print(f"Entidades do {dxf_primeiro} copiadas com sucesso.")

    except IOError:
        print(f"ERRO: Não foi possível ler o arquivo {dxf_primeiro}.")
        return

    # --- Processamento do Segundo Piso (COM OFFSET) ---
    try:
        doc_piso2 = ezdxf.readfile(dxf_segundo)
        msp_piso2 = doc_piso2.modelspace()

        # O Deslocamento (Offset) é crucial para separar os desenhos!
        offset = (distancia_offset_x, 0)

        # Itera, aplica o offset e adiciona entidades uma a uma
        for entity in msp_piso2:
            cloned_entity = entity.copy()

            # Aplica a transformação de deslocamento (move)
            cloned_entity.translate(offset[0], offset[1], 0)

            # Altera a camada para "PISO_2_DESLOCADO" e copia para o mestre
            cloned_entity.dxf.layer = "PISO_2_DESLOCADO"
            msp_mestre.add_entity(cloned_entity)

        print(
            f"Entidades do {dxf_segundo} copiadas e deslocadas por {distancia_offset_x} unidades (Eixo X)."
        )

    except IOError:
        print(f"ERRO: Não foi possível ler o arquivo {dxf_segundo}.")
        return

    # Salva o arquivo DXF Mestre
    try:
        doc_mestre.saveas(nome_dxf_saida)
        print(
            f"\n✅ Sucesso! Arquivo DXF combinado salvo como: {os.path.abspath(nome_dxf_saida)}"
        )
    except IOError as e:
        print(f"ERRO ao salvar o arquivo DXF: {e}")


dxf_primeiro_piso = "planta_primeiro_piso.dxf"
dxf_segundo_piso = "planta_segundo_piso.dxf"
distancia_de_separacao = 100

juntar_arquivos_dxf(dxf_primeiro_piso, dxf_segundo_piso, distancia_de_separacao)
