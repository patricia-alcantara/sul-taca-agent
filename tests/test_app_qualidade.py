from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import qualidade


APP = Path(__file__).parents[1] / "app.py"


class QualidadeNaInterfaceTestCase(unittest.TestCase):
    def setUp(self):
        self.pasta_temporaria = TemporaryDirectory()
        self.banco = (
            Path(self.pasta_temporaria.name) / "qualidade.db"
        )

        registrar_original = qualidade.registrar_resposta_elegivel
        registrar_interacao_original = qualidade.registrar_interacao
        obter_original = qualidade.obter_avaliacao
        avaliar_original = qualidade.avaliar_resposta

        self.patches = (
            patch(
                "qualidade.registrar_resposta_elegivel",
                side_effect=lambda **kwargs: registrar_original(
                    **kwargs,
                    caminho_banco=self.banco,
                ),
            ),
            patch(
                "qualidade.registrar_interacao",
                side_effect=lambda **kwargs: registrar_interacao_original(
                    **kwargs,
                    caminho_banco=self.banco,
                ),
            ),
            patch(
                "qualidade.obter_avaliacao",
                side_effect=lambda message_id: obter_original(
                    message_id,
                    caminho_banco=self.banco,
                ),
            ),
            patch(
                "qualidade.avaliar_resposta",
                side_effect=lambda **kwargs: avaliar_original(
                    **kwargs,
                    caminho_banco=self.banco,
                ),
            ),
            patch("google.genai.Client", return_value=object()),
            patch(
                "busca_semantica.gerar_embeddings",
                return_value=(),
            ),
            patch(
                "busca_semantica.criar_indice",
                return_value=object(),
            ),
            patch(
                "busca_semantica.responder_pergunta",
                return_value=(
                    "Recomendo o Doce Pampa "
                    "como uma ótima escolha para essa preferência."
                ),
            ),
        )

        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()

        self.pasta_temporaria.cleanup()

    def abrir_menu_principal(self) -> AppTest:
        app = AppTest.from_file(str(APP), default_timeout=5).run()
        app.button[0].click().run()
        app.button(key="pular_nome").click().run()
        return app

    def assert_sem_feedback(self, app: AppTest) -> None:
        mensagem = app.session_state.mensagens[-1]
        self.assertNotIn("message_id", mensagem)
        self.assertNotIn("avaliavel", mensagem)
        self.assertFalse(
            any(
                botao.label in ("👍", "👎")
                for botao in app.button
            )
        )
        self.assertNotIn(
            "Esta resposta foi útil?",
            [legenda.value for legenda in app.caption],
        )

    def ultima_forma_atendimento(self) -> str:
        with qualidade.abrir_banco(self.banco) as conexao:
            return conexao.execute(
                "SELECT tipo_atendimento FROM interacoes "
                "ORDER BY criada_em DESC, message_id DESC LIMIT 1"
            ).fetchone()["tipo_atendimento"]

    def test_perguntas_locais_do_submenu_nao_sao_avaliaveis(self):
        chaves = [
            f"submenu_escolha_{indice}"
            for indice in range(5)
        ]

        for chave in chaves:
            with self.subTest(chave=chave):
                app = self.abrir_menu_principal()
                app.button(key="menu_escolher").click().run()
                app.button(key=chave).click().run()

                self.assert_sem_feedback(app)

        metricas = qualidade.obter_metricas(self.banco)
        self.assertEqual(metricas["respostas_elegiveis"], 0)
        self.assertEqual(metricas["recomendacoes"], 0)

    def test_pergunta_local_sobre_vinho_nao_e_avaliavel(self):
        app = self.abrir_menu_principal()
        app.button(key="menu_vinho_especifico").click().run()

        self.assert_sem_feedback(app)
        metricas = qualidade.obter_metricas(self.banco)
        self.assertEqual(metricas["respostas_elegiveis"], 0)
        self.assertEqual(metricas["recomendacoes"], 0)

    def test_ajuda_com_compra_permanece_avaliavel(self):
        app = self.abrir_menu_principal()
        app.button(key="menu_ajuda_compra").click().run()

        mensagem = app.session_state.mensagens[-1]
        self.assertTrue(mensagem["avaliavel"])
        self.assertIn("message_id", mensagem)
        self.assertIn("👍", [botao.label for botao in app.button])
        self.assertIn("👎", [botao.label for botao in app.button])

        metricas = qualidade.obter_metricas(self.banco)
        self.assertEqual(metricas["respostas_elegiveis"], 1)
        self.assertEqual(metricas["recomendacoes"], 0)
        self.assertEqual(
            self.ultima_forma_atendimento(),
            "orientacao_sem_consulta",
        )

    def test_jornada_guiada_preserva_forma_de_atendimento(self):
        for continuacao in (
            "macarronada",
            "ela gosta de vinho tinto doce",
        ):
            with self.subTest(continuacao=continuacao):
                app = self.abrir_menu_principal()
                app.button(key="menu_escolher").click().run()
                app.button(key="submenu_escolha_0").click().run()

                self.assert_sem_feedback(app)
                app.chat_input[0].set_value(continuacao).run()

                mensagem = app.session_state.mensagens[-1]
                self.assertTrue(mensagem["eh_recomendacao"])
                self.assertFalse(mensagem["eh_comparacao"])
                self.assertEqual(
                    self.ultima_forma_atendimento(),
                    "fluxo_guiado",
                )

    def test_recomendacao_direta_e_classificada_pelo_resultado(self):
        app = self.abrir_menu_principal()
        app.button(key="menu_outras_duvidas").click().run()
        app.chat_input[0].set_value(
            "Recomende um vinho para macarronada."
        ).run()

        mensagem = app.session_state.mensagens[-1]
        self.assertTrue(mensagem["eh_recomendacao"])
        self.assertFalse(mensagem["eh_comparacao"])
        self.assertIsNone(app.session_state.tarefa_atual)
        self.assertEqual(
            self.ultima_forma_atendimento(),
            "catalogo_documentos",
        )

    def test_mudanca_para_privacidade_nao_carrega_recomendacao(self):
        app = self.abrir_menu_principal()
        app.button(key="menu_escolher").click().run()
        app.button(key="submenu_escolha_0").click().run()

        with patch(
            "busca_semantica.responder_pergunta",
            return_value="Seus dados são tratados conforme nossa política.",
        ):
            app.chat_input[0].set_value(
                "quero saber sobre privacidade"
            ).run()

        mensagem = app.session_state.mensagens[-1]
        self.assertFalse(mensagem["eh_recomendacao"])
        self.assertFalse(mensagem["eh_comparacao"])
        self.assertIsNone(app.session_state.tarefa_atual)
        metricas = qualidade.obter_metricas(self.banco)
        self.assertEqual(metricas["recomendacoes"], 0)
        self.assertEqual(
            self.ultima_forma_atendimento(),
            "catalogo_documentos",
        )

    def test_pagina_insuficiente_e_avaliavel_sem_comparacao(self):
        app = self.abrir_menu_principal()
        app.button(key="menu_outras_duvidas").click().run()

        with patch(
            "consulta_url.consultar_pagina_vinho",
            return_value=("", ""),
        ):
            app.chat_input[0].set_value(
                "Consulte este vinho: https://example.com/vinho"
            ).run()

        mensagem = app.session_state.mensagens[-1]
        self.assertTrue(mensagem["avaliavel"])
        self.assertFalse(mensagem["eh_recomendacao"])
        self.assertFalse(mensagem["eh_comparacao"])

    def test_comparacao_concluida_e_classificada(self):
        with (
            patch(
                "busca_semantica.recuperar_contexto",
                return_value=("contexto", "fontes internas"),
            ),
            patch(
                "consulta_url.comparar_dados_fornecidos",
                return_value=(
                    "O Doce Pampa custa R$ 70 e o Vinho Externo "
                    "custa R$ 80."
                ),
            ),
        ):
            app = self.abrir_menu_principal()
            app.button(key="menu_escolher").click().run()
            app.button(key="submenu_escolha_0").click().run()
            app.chat_input[0].set_value(
                "Compare Doce Pampa Colheita Tardia com Vinho Externo "
                "por preço."
            ).run()
            app.chat_input[0].set_value("o preço é R$ 80").run()

        mensagem = app.session_state.mensagens[-1]
        self.assertFalse(mensagem["eh_recomendacao"])
        self.assertTrue(mensagem["eh_comparacao"], mensagem)
        self.assertIsNone(app.session_state.comparacao_pendente)
        self.assertEqual(
            self.ultima_forma_atendimento(),
            "comparacao_externa",
        )


if __name__ == "__main__":
    unittest.main()
