import unittest

from atendimento import (
    EstadoTarefa,
    EtapaFalha,
    EtapaTarefa,
    Intencao,
    Mecanismo,
    NaturezaResposta,
    OrigemTarefa,
    Resultado,
    StatusResultado,
    TipoAtendimento,
    atualizar_tarefa_por_mensagem,
    concluir_tarefa,
    criar_envelope_resultado,
    inferir_intencoes,
    iniciar_tarefa,
    limpar_tarefa,
    registrar_continuacao,
    substituir_tarefa,
)


CHUNKS_CATALOGO = [
    {
        "texto": (
            "Pedra Andina Malbec 2024 (ST-014)\n"
            "Doce Pampa Colheita Tardia 2024 (ST-018)"
        ),
        "documento": "catalogo.pdf",
        "pagina": 1,
    }
]


class AtendimentoTestCase(unittest.TestCase):
    def envelope(
        self,
        texto,
        tarefa=None,
        natureza=NaturezaResposta.SUBSTANTIVA,
        status=StatusResultado.SUCESSO,
        participantes=(),
        etapa_falha=None,
    ):
        return criar_envelope_resultado(
            texto=texto,
            natureza=natureza,
            tipo_atendimento=TipoAtendimento.CATALOGO_DOCUMENTOS,
            rota_tecnica="rag",
            mecanismo=Mecanismo.RAG_INTERNO,
            status=status,
            tarefa=tarefa,
            chunks=CHUNKS_CATALOGO,
            participantes_comparacao=participantes,
            etapa_falha=etapa_falha,
        )

    def test_recomendacao_direta_preserva_continuacoes(self):
        tarefa = atualizar_tarefa_por_mensagem(
            None,
            "Quero um vinho tinto.",
            task_id="tarefa-direta",
        )
        tarefa = atualizar_tarefa_por_mensagem(tarefa, "macarronada")
        tarefa = atualizar_tarefa_por_mensagem(tarefa, "até R$ 100")

        resultado = self.envelope(
            "Recomendo o Pedra Andina Malbec 2024 para a macarronada.",
            tarefa,
        )

        self.assertIn(Intencao.RECOMENDACAO, tarefa.intencoes)
        self.assertEqual(tarefa.continuacoes, 2)
        self.assertIn(Resultado.RECOMENDACAO, resultado.resultados)
        self.assertEqual(resultado.produtos_sul_taca[0].codigo, "ST-014")

    def test_recomendacao_guiada_nasce_do_fluxo_com_produto(self):
        tarefa = iniciar_tarefa(
            {Intencao.RECOMENDACAO},
            OrigemTarefa.MENU_GUIADO,
            EtapaTarefa.AGUARDANDO_NECESSIDADE,
            task_id="tarefa-guiada",
        )
        tarefa = registrar_continuacao(tarefa, EtapaTarefa.EM_EXECUCAO)

        resultado = self.envelope(
            "O Doce Pampa é uma ótima escolha para você.",
            tarefa,
        )

        self.assertTrue(resultado.elegivel)
        self.assertIn(Resultado.RECOMENDACAO, resultado.resultados)

    def test_recomendacao_guiada_preserva_prato_como_continuacao(self):
        tarefa = iniciar_tarefa(
            {Intencao.RECOMENDACAO},
            OrigemTarefa.MENU_GUIADO,
            EtapaTarefa.AGUARDANDO_NECESSIDADE,
            task_id="recomendacao-guiada",
        )

        atualizada = atualizar_tarefa_por_mensagem(tarefa, "macarronada")

        self.assertEqual(atualizada.task_id, tarefa.task_id)
        self.assertEqual(atualizada.intencoes, {Intencao.RECOMENDACAO})
        self.assertEqual(atualizada.continuacoes, 1)

    def test_privacidade_substitui_recomendacao_guiada(self):
        tarefa = iniciar_tarefa(
            {Intencao.RECOMENDACAO},
            OrigemTarefa.MENU_GUIADO,
            EtapaTarefa.AGUARDANDO_NECESSIDADE,
            task_id="recomendacao-guiada",
        )

        atualizada = atualizar_tarefa_por_mensagem(
            tarefa,
            "quero saber sobre privacidade",
            task_id="consulta-privacidade",
        )

        self.assertEqual(atualizada.task_id, "consulta-privacidade")
        self.assertEqual(
            atualizada.intencoes,
            {Intencao.CONSULTA_CATALOGO_POLITICA},
        )

    def test_comparacao_pendente_preserva_dado_complementar(self):
        tarefa = iniciar_tarefa(
            {Intencao.COMPARACAO},
            OrigemTarefa.DIRETA,
            EtapaTarefa.AGUARDANDO_DADOS_EXTERNOS,
            task_id="comparacao-pendente",
        )

        atualizada = atualizar_tarefa_por_mensagem(
            tarefa,
            "o preço é R$ 89",
        )

        self.assertEqual(atualizada.task_id, tarefa.task_id)
        self.assertEqual(atualizada.intencoes, {Intencao.COMPARACAO})
        self.assertEqual(atualizada.continuacoes, 1)

    def test_assunto_operacional_substitui_comparacao_pendente(self):
        tarefa = iniciar_tarefa(
            {Intencao.COMPARACAO},
            OrigemTarefa.DIRETA,
            EtapaTarefa.AGUARDANDO_DADOS_EXTERNOS,
            task_id="comparacao-pendente",
        )

        atualizada = atualizar_tarefa_por_mensagem(
            tarefa,
            "como faço para acompanhar meu pedido?",
            task_id="orientacao-operacional",
        )

        self.assertEqual(atualizada.task_id, "orientacao-operacional")
        self.assertEqual(
            atualizada.intencoes,
            {Intencao.ORIENTACAO_OPERACIONAL},
        )

    def test_produto_ausente_ou_orientacao_nao_e_recomendacao(self):
        tarefa = iniciar_tarefa(
            {Intencao.RECOMENDACAO},
            OrigemTarefa.DIRETA,
            EtapaTarefa.EM_EXECUCAO,
        )

        sem_produto = self.envelope(
            "Posso ajudar a escolher um estilo adequado ao prato.",
            tarefa,
        )
        produto_inexistente = self.envelope(
            "Recomendo o Vento de Marte para esse prato.",
            tarefa,
        )

        self.assertNotIn(Resultado.RECOMENDACAO, sem_produto.resultados)
        self.assertNotIn(
            Resultado.RECOMENDACAO,
            produto_inexistente.resultados,
        )

    def test_comparacao_e_recomendacao_podem_coexistir(self):
        tarefa = atualizar_tarefa_por_mensagem(
            None,
            "Compare e recomende um dos dois vinhos.",
        )
        resultado = self.envelope(
            "Recomendo o Pedra Andina Malbec 2024 como a melhor escolha.",
            tarefa,
            participantes=("ST-014", "Casillero Reserva Malbec"),
        )

        self.assertEqual(
            resultado.resultados,
            {Resultado.RECOMENDACAO, Resultado.COMPARACAO},
        )

    def test_esclarecimento_local_nao_e_elegivel(self):
        tarefa = iniciar_tarefa(
            {Intencao.RECOMENDACAO},
            OrigemTarefa.MENU_GUIADO,
            EtapaTarefa.AGUARDANDO_NECESSIDADE,
        )
        resultado = self.envelope(
            "Qual prato você pretende servir?",
            tarefa,
            natureza=NaturezaResposta.ESCLARECIMENTO,
        )

        self.assertFalse(resultado.elegivel)
        self.assertFalse(resultado.resultados)

    def test_pagina_insuficiente_e_elegivel_sem_resultado(self):
        resultado = self.envelope(
            "Envie a página específica do rótulo.",
            natureza=NaturezaResposta.ORIENTACAO_RECUPERACAO,
            status=StatusResultado.INSUFICIENTE,
            participantes=("ST-014", "produto externo"),
        )

        self.assertTrue(resultado.elegivel)
        self.assertTrue(resultado.permite_persistir_textos)
        self.assertFalse(resultado.resultados)

    def test_falha_e_bloqueio_nao_sao_avaliaveis(self):
        falha = self.envelope(
            "Serviço temporariamente indisponível.",
            natureza=NaturezaResposta.OPERACIONAL,
            status=StatusResultado.FALHA_TECNICA,
            etapa_falha=EtapaFalha.GERACAO,
        )
        bloqueio = self.envelope(
            "Não acesso páginas com dados pessoais.",
            natureza=NaturezaResposta.OPERACIONAL,
            status=StatusResultado.BLOQUEIO_SEGURANCA,
        )

        for resultado in (falha, bloqueio):
            with self.subTest(status=resultado.status):
                self.assertFalse(resultado.elegivel)
                self.assertFalse(resultado.permite_persistir_textos)
                self.assertFalse(resultado.resultados)

    def test_ciclo_de_vida_concluir_substituir_e_limpar(self):
        tarefa = iniciar_tarefa(
            {Intencao.RECOMENDACAO},
            OrigemTarefa.DIRETA,
            EtapaTarefa.EM_EXECUCAO,
            task_id="original",
        )
        concluida = concluir_tarefa(tarefa)
        substituida, nova = substituir_tarefa(
            tarefa,
            {Intencao.COMPARACAO},
            OrigemTarefa.DIRETA,
            EtapaTarefa.AGUARDANDO_CRITERIOS,
            task_id="nova",
        )
        limpa = limpar_tarefa(nova)

        self.assertEqual(concluida.estado, EstadoTarefa.CONCLUIDA)
        self.assertEqual(substituida.estado, EstadoTarefa.SUBSTITUIDA)
        self.assertEqual(nova.intencoes, {Intencao.COMPARACAO})
        self.assertEqual(limpa.estado, EstadoTarefa.LIMPA)

    def test_intencoes_controladas_sao_distintas(self):
        intencoes = inferir_intencoes(
            "Compare os dois e recomende a melhor opção."
        )

        self.assertEqual(
            intencoes,
            {Intencao.RECOMENDACAO, Intencao.COMPARACAO},
        )


if __name__ == "__main__":
    unittest.main()
