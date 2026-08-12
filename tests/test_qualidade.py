from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from atendimento import (
    Intencao,
    Mecanismo,
    NaturezaResposta,
    Resultado,
    StatusResultado,
    TipoAtendimento,
)

from qualidade import (
    TIPO_CATALOGO,
    TIPO_COMPARACAO,
    avaliar_resposta,
    abrir_banco,
    obter_avaliacoes_detalhadas,
    obter_contexto,
    obter_funcionamento,
    obter_mecanismos,
    obter_metricas,
    registrar_interacao,
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
                "SELECT * FROM interacoes ORDER BY message_id"
            ).fetchall()

    def buscar_avaliacoes(self):
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
        self.assertEqual(self.buscar_avaliacoes(), [])

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
        registro = self.buscar_avaliacoes()[0]

        self.assertTrue(atualizado)
        self.assertEqual(registro["avaliacao"], 1)
        self.assertEqual(
            registro["pergunta_sanitizada"],
            "Qual vinho você recomenda?",
        )
        self.assertEqual(
            registro["resposta_sanitizada"],
            "Recomendo este vinho.",
        )

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
        registros = self.buscar_avaliacoes()

        self.assertFalse(atualizado)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["avaliacao"], 1)
        self.assertEqual(
            registros[0]["pergunta_sanitizada"],
            "Pergunta original",
        )

    def test_banco_novo_cria_schema_v2(self):
        with abrir_banco(self.banco) as conexao:
            tabelas = {
                linha["name"]
                for linha in conexao.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

        self.assertTrue(
            {"interacoes", "classificacoes_interacao", "avaliacoes"}
            <= tabelas
        )

    def test_migracao_preserva_banco_existente_e_e_idempotente(self):
        conexao = sqlite3.connect(self.banco)
        conexao.executescript(
            """
            CREATE TABLE avaliacoes (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                criada_em TEXT NOT NULL,
                rota_tecnica TEXT NOT NULL,
                tipo_atendimento TEXT NOT NULL,
                eh_recomendacao INTEGER NOT NULL DEFAULT 0,
                eh_comparacao INTEGER NOT NULL DEFAULT 0,
                avaliacao INTEGER,
                pergunta TEXT,
                resposta TEXT
            );
            INSERT INTO avaliacoes VALUES (
                'legada-1', 'sessao', '2026-08-10T12:00:00+00:00',
                'hibrida', 'Comparação externa', 1, 1, 1,
                'Pergunta segura', 'Resposta segura'
            );
            INSERT INTO avaliacoes VALUES (
                'legada-2', 'sessao', '2026-08-10T12:01:00+00:00',
                'rag', 'Catálogo e documentos', 0, 0, NULL, NULL, NULL
            );
            """
        )
        conexao.close()

        with abrir_banco(self.banco):
            pass
        with abrir_banco(self.banco) as conexao:
            interacoes = conexao.execute(
                "SELECT COUNT(*) FROM interacoes"
            ).fetchone()[0]
            avaliacoes = conexao.execute(
                "SELECT COUNT(*) FROM avaliacoes"
            ).fetchone()[0]
            classificacoes = conexao.execute(
                "SELECT COUNT(*) FROM classificacoes_interacao"
            ).fetchone()[0]
            formas = {
                linha["message_id"]: linha["tipo_atendimento"]
                for linha in conexao.execute(
                    "SELECT message_id, tipo_atendimento FROM interacoes"
                )
            }

        self.assertEqual(interacoes, 2)
        self.assertEqual(avaliacoes, 1)
        self.assertEqual(classificacoes, 2)
        self.assertEqual(
            formas,
            {
                "legada-1": "comparacao_externa",
                "legada-2": "catalogo_documentos",
            },
        )
        self.assertEqual(obter_metricas(self.banco)["recomendacoes"], 1)
        self.assertEqual(obter_metricas(self.banco)["comparacoes"], 1)
        self.assertEqual(
            obter_metricas(self.banco)["recomendacoes_e_comparacoes"],
            1,
        )
        contexto = obter_contexto(self.banco)
        comparacao = next(
            item
            for item in contexto
            if item["Forma de atendimento"] == TIPO_COMPARACAO
        )
        self.assertEqual(comparacao["Disponíveis para avaliação"], 1)
        self.assertEqual(comparacao["Respostas avaliadas"], 1)
        self.assertEqual(comparacao["Taxa de participação"], 100.0)
        self.assertEqual(
            obter_avaliacoes_detalhadas(self.banco)[0]["Resultado"],
            "Recomendação e comparação",
        )

    def test_envelope_persiste_classificacoes_simultaneas(self):
        envelope = SimpleNamespace(
            elegivel=True,
            natureza=NaturezaResposta.SUBSTANTIVA,
            tipo_atendimento=TipoAtendimento.COMPARACAO_EXTERNA,
            rota_tecnica="hibrida",
            mecanismo=Mecanismo.HIBRIDO,
            status=StatusResultado.SUCESSO,
            etapa_falha=None,
            intencoes=frozenset(
                {Intencao.RECOMENDACAO, Intencao.COMPARACAO}
            ),
            resultados=frozenset(
                {Resultado.RECOMENDACAO, Resultado.COMPARACAO}
            ),
        )

        self.assertTrue(
            registrar_interacao(
                "dupla",
                "sessao",
                envelope,
                task_id="tarefa",
                caminho_banco=self.banco,
            )
        )

        with abrir_banco(self.banco) as conexao:
            classificacoes = {
                (linha["dimensao"], linha["classificacao"])
                for linha in conexao.execute(
                    "SELECT dimensao, classificacao "
                    "FROM classificacoes_interacao WHERE message_id = 'dupla'"
                )
            }

        self.assertEqual(
            classificacoes,
            {
                ("intencao", "recomendacao"),
                ("intencao", "comparacao"),
                ("resultado", "recomendacao"),
                ("resultado", "comparacao"),
            },
        )
        metricas = obter_metricas(self.banco)
        self.assertEqual(metricas["recomendacoes"], 1)
        self.assertEqual(metricas["comparacoes"], 1)
        self.assertEqual(metricas["recomendacoes_e_comparacoes"], 1)

    def test_falha_persiste_so_metadados_controlados(self):
        envelope = SimpleNamespace(
            elegivel=False,
            natureza=NaturezaResposta.OPERACIONAL,
            tipo_atendimento=TipoAtendimento.CATALOGO_DOCUMENTOS,
            rota_tecnica="erro_api",
            mecanismo=Mecanismo.RAG_INTERNO,
            status=StatusResultado.FALHA_TECNICA,
            etapa_falha=SimpleNamespace(value="geracao"),
            intencoes=frozenset({Intencao.RECOMENDACAO}),
            resultados=frozenset(),
        )
        registrar_interacao(
            "falha",
            "sessao",
            envelope,
            caminho_banco=self.banco,
        )

        atualizado = avaliar_resposta(
            "falha",
            False,
            "CPF 123.456.789-10",
            "erro sensível",
            caminho_banco=self.banco,
        )

        with abrir_banco(self.banco) as conexao:
            interacao = conexao.execute(
                "SELECT status, etapa_falha FROM interacoes "
                "WHERE message_id = 'falha'"
            ).fetchone()
            avaliacoes = conexao.execute(
                "SELECT COUNT(*) FROM avaliacoes"
            ).fetchone()[0]

        self.assertFalse(atualizado)
        self.assertEqual(interacao["status"], "falha_tecnica")
        self.assertEqual(interacao["etapa_falha"], "geracao")
        self.assertEqual(avaliacoes, 0)

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

        contexto = obter_contexto(self.banco)[0]
        self.assertEqual(contexto["Disponíveis para avaliação"], 3)
        self.assertEqual(contexto["Respostas avaliadas"], 2)
        self.assertAlmostEqual(
            contexto["Taxa de participação"],
            200 / 3,
        )
        self.assertEqual(contexto["Percentual positivo"], 50.0)

    def test_funcionamento_e_mecanismos_usam_todas_as_interacoes(self):
        cenarios = (
            ("sucesso", StatusResultado.SUCESSO, True, Mecanismo.RAG_INTERNO),
            (
                "insuficiente",
                StatusResultado.INSUFICIENTE,
                True,
                Mecanismo.URL_CONTEXT,
            ),
            (
                "falha",
                StatusResultado.FALHA_TECNICA,
                False,
                Mecanismo.RAG_INTERNO,
            ),
            (
                "bloqueio",
                StatusResultado.BLOQUEIO_SEGURANCA,
                False,
                Mecanismo.REGRA_LOCAL,
            ),
        )

        for message_id, status, elegivel, mecanismo in cenarios:
            envelope = SimpleNamespace(
                elegivel=elegivel,
                natureza=NaturezaResposta.SUBSTANTIVA,
                tipo_atendimento=TipoAtendimento.CATALOGO_DOCUMENTOS,
                rota_tecnica="teste",
                mecanismo=mecanismo,
                status=status,
                etapa_falha=(
                    SimpleNamespace(value="geracao")
                    if status == StatusResultado.FALHA_TECNICA
                    else None
                ),
                intencoes=frozenset(),
                resultados=frozenset(),
            )
            registrar_interacao(
                message_id,
                "sessao",
                envelope,
                caminho_banco=self.banco,
            )

        funcionamento = obter_funcionamento(self.banco)
        mecanismos = obter_mecanismos(self.banco)

        self.assertEqual(
            funcionamento,
            {
                "interacoes": 4,
                "sucessos": 1,
                "insuficiencias": 1,
                "falhas": 1,
                "bloqueios": 1,
            },
        )
        self.assertEqual(
            mecanismos[0],
            {
                "Como a Jessi respondeu": "Base interna Sul Taça",
                "O que significa": (
                    "Consulta ao catálogo e aos documentos internos."
                ),
                "Interações": 2,
            },
        )

    def test_detalhes_nao_duplicam_resposta_com_dois_resultados(self):
        envelope = SimpleNamespace(
            elegivel=True,
            natureza=NaturezaResposta.SUBSTANTIVA,
            tipo_atendimento=TipoAtendimento.COMPARACAO_EXTERNA,
            rota_tecnica="hibrida",
            mecanismo=Mecanismo.HIBRIDO,
            status=StatusResultado.SUCESSO,
            etapa_falha=None,
            intencoes=frozenset(),
            resultados=frozenset(
                {Resultado.RECOMENDACAO, Resultado.COMPARACAO}
            ),
        )
        registrar_interacao(
            "dupla-avaliada",
            "sessao",
            envelope,
            caminho_banco=self.banco,
        )
        avaliar_resposta(
            "dupla-avaliada",
            True,
            "Pergunta",
            "Resposta",
            caminho_banco=self.banco,
        )

        detalhes = obter_avaliacoes_detalhadas(self.banco)

        self.assertEqual(len(detalhes), 1)
        self.assertEqual(
            detalhes[0]["Resultado"],
            "Recomendação e comparação",
        )
        self.assertEqual(
            detalhes[0]["Como a Jessi respondeu"],
            "Base interna + página externa",
        )

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
        self.assertEqual(
            obter_funcionamento(self.banco),
            {
                "interacoes": 0,
                "sucessos": 0,
                "insuficiencias": 0,
                "falhas": 0,
                "bloqueios": 0,
            },
        )
        self.assertEqual(obter_mecanismos(self.banco), [])
        self.assertEqual(obter_avaliacoes_detalhadas(self.banco), [])


if __name__ == "__main__":
    unittest.main()
