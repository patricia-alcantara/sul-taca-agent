from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from qualidade import (
    TIPO_CATALOGO,
    TIPO_COMPARACAO,
    avaliar_resposta,
    abrir_banco,
    obter_avaliacoes_detalhadas,
    obter_contexto,
    obter_metricas,
    registrar_resposta_elegivel,
    resposta_eh_avaliavel,
    sanitizar_texto,
)


class QualidadeTestCase(unittest.TestCase):
    def setUp(self):
        self.pasta_temporaria = TemporaryDirectory()
        self.banco = Path(self.pasta_temporaria.name) / "qualidade.db"

    def tearDown(self):
        self.pasta_temporaria.cleanup()

    def registrar(
        self,
        message_id="mensagem-1",
        recomendacao=False,
        comparacao=False,
        tipo=TIPO_CATALOGO,
    ):
        return registrar_resposta_elegivel(
            message_id=message_id,
            session_id="sessao-anonima",
            rota_tecnica="rag",
            tipo_atendimento=tipo,
            eh_recomendacao=recomendacao,
            eh_comparacao=comparacao,
            caminho_banco=self.banco,
            criada_em="2026-08-10T12:00:00+00:00",
        )

    def buscar_registros(self):
        with abrir_banco(self.banco) as conexao:
            return conexao.execute(
                "SELECT * FROM avaliacoes ORDER BY message_id"
            ).fetchall()

    def test_resposta_elegivel_cria_um_registro_minimo(self):
        self.assertTrue(self.registrar())
        registros = self.buscar_registros()

        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["message_id"], "mensagem-1")
        self.assertEqual(registros[0]["session_id"], "sessao-anonima")
        self.assertIsNone(registros[0]["avaliacao"])
        self.assertIsNone(registros[0]["pergunta"])
        self.assertIsNone(registros[0]["resposta"])

    def test_rerun_nao_duplica_registro(self):
        self.assertTrue(self.registrar())
        self.assertFalse(self.registrar())
        self.assertEqual(len(self.buscar_registros()), 1)

    def test_avaliacao_atualiza_registro_existente(self):
        self.registrar()

        atualizado = avaliar_resposta(
            "mensagem-1",
            True,
            "Qual vinho você recomenda?",
            "Recomendo este vinho.",
            caminho_banco=self.banco,
        )
        registro = self.buscar_registros()[0]

        self.assertTrue(atualizado)
        self.assertEqual(registro["avaliacao"], 1)
        self.assertEqual(registro["pergunta"], "Qual vinho você recomenda?")
        self.assertEqual(registro["resposta"], "Recomendo este vinho.")

    def test_segundo_clique_nao_cria_linha_nem_troca_avaliacao(self):
        self.registrar()
        avaliar_resposta(
            "mensagem-1",
            True,
            "Pergunta original",
            "Resposta original",
            caminho_banco=self.banco,
        )

        atualizado = avaliar_resposta(
            "mensagem-1",
            False,
            "Outra pergunta",
            "Outra resposta",
            caminho_banco=self.banco,
        )
        registros = self.buscar_registros()

        self.assertFalse(atualizado)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["avaliacao"], 1)
        self.assertEqual(registros[0]["pergunta"], "Pergunta original")

    def test_interacao_alimenta_metricas_simultaneas(self):
        self.registrar(recomendacao=True, comparacao=True)
        avaliar_resposta(
            "mensagem-1",
            False,
            "Compare e recomende",
            "Comparação",
            caminho_banco=self.banco,
        )

        metricas = obter_metricas(self.banco)

        self.assertEqual(metricas["respostas_avaliadas"], 1)
        self.assertEqual(metricas["negativas"], 1)
        self.assertEqual(metricas["recomendacoes"], 1)
        self.assertEqual(metricas["comparacoes"], 1)

    def test_metricas_comerciais_incluem_nao_avaliadas(self):
        self.registrar("recomendacao", recomendacao=True)
        self.registrar(
            "comparacao",
            comparacao=True,
            tipo=TIPO_COMPARACAO,
        )

        metricas = obter_metricas(self.banco)

        self.assertEqual(metricas["recomendacoes"], 1)
        self.assertEqual(metricas["comparacoes"], 1)
        self.assertEqual(metricas["respostas_avaliadas"], 0)

    def test_qualidade_e_participacao_consideram_so_avaliadas(self):
        self.registrar("positiva")
        self.registrar("negativa")
        self.registrar("sem-avaliacao")
        avaliar_resposta(
            "positiva", True, "P1", "R1", caminho_banco=self.banco
        )
        avaliar_resposta(
            "negativa", False, "P2", "R2", caminho_banco=self.banco
        )

        metricas = obter_metricas(self.banco)

        self.assertEqual(metricas["respostas_elegiveis"], 3)
        self.assertEqual(metricas["respostas_avaliadas"], 2)
        self.assertEqual(metricas["positivas"], 1)
        self.assertEqual(metricas["negativas"], 1)
        self.assertAlmostEqual(metricas["percentual_positivo"], 50.0)
        self.assertAlmostEqual(metricas["taxa_participacao"], 200 / 3)

    def test_pagina_insuficiente_e_avaliavel(self):
        self.assertTrue(resposta_eh_avaliavel("pagina_insuficiente"))

    def test_mensagens_sem_conteudo_nao_sao_avaliaveis(self):
        categorias = (
            "apresentacao",
            "maioridade",
            "identificacao_nome",
            "menu",
            "submenu",
            "navegacao",
            "erro_api",
            "bloqueio_seguranca",
        )

        for categoria in categorias:
            with self.subTest(categoria=categoria):
                self.assertFalse(resposta_eh_avaliavel(categoria))

    def test_dados_pessoais_basicos_sao_redigidos(self):
        texto = (
            "Meu nome é Maria da Silva, CPF 123.456.789-10, "
            "telefone (51) 99999-8888 e email maria@example.com. "
            "Veja https://exemplo.com/vinho?email=maria@example.com."
        )

        resultado = sanitizar_texto(texto, ("Maria da Silva",))

        self.assertNotIn("Maria da Silva", resultado)
        self.assertNotIn("123.456.789-10", resultado)
        self.assertNotIn("99999-8888", resultado)
        self.assertNotIn("maria@example.com", resultado)
        self.assertNotIn("?email=", resultado)

    def test_painel_funciona_com_banco_vazio(self):
        metricas = obter_metricas(self.banco)

        self.assertEqual(metricas["respostas_elegiveis"], 0)
        self.assertEqual(metricas["percentual_positivo"], 0.0)
        self.assertEqual(metricas["taxa_participacao"], 0.0)
        self.assertEqual(obter_contexto(self.banco), [])
        self.assertEqual(obter_avaliacoes_detalhadas(self.banco), [])


if __name__ == "__main__":
    unittest.main()
