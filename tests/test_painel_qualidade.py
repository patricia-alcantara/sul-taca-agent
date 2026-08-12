from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


PAINEL = Path(__file__).parents[1] / "painel_qualidade.py"


class PainelQualidadeTestCase(unittest.TestCase):
    def test_painel_vazio_exibe_secoes_e_estados_vazios(self):
        metricas = {
            "respostas_elegiveis": 0,
            "respostas_avaliadas": 0,
            "positivas": 0,
            "negativas": 0,
            "percentual_positivo": 0.0,
            "taxa_participacao": 0.0,
            "recomendacoes": 0,
            "comparacoes": 0,
            "recomendacoes_e_comparacoes": 0,
        }
        funcionamento = {
            "interacoes": 0,
            "sucessos": 0,
            "insuficiencias": 0,
            "falhas": 0,
            "bloqueios": 0,
        }

        with (
            patch("qualidade.obter_metricas", return_value=metricas),
            patch("qualidade.obter_contexto", return_value=[]),
            patch(
                "qualidade.obter_funcionamento",
                return_value=funcionamento,
            ),
            patch("qualidade.obter_mecanismos", return_value=[]),
            patch(
                "qualidade.obter_avaliacoes_detalhadas",
                return_value=[],
            ),
        ):
            painel = AppTest.from_file(str(PAINEL), default_timeout=5).run()

        self.assertFalse(painel.exception)
        self.assertEqual(
            [item.value for item in painel.subheader],
            [
                "Qualidade das respostas",
                "Avaliações por forma de atendimento",
                "Recomendações e comparações",
                "Funcionamento do atendimento",
                "Como a Jessi respondeu",
                "Detalhes das respostas avaliadas",
            ],
        )
        self.assertEqual(len(painel.info), 3)
        self.assertIn(
            "Disponíveis para avaliação",
            [item.label for item in painel.metric],
        )
        self.assertIn(
            "Falhas registradas",
            [item.label for item in painel.metric],
        )
        self.assertIn(
            "Bloqueios registrados",
            [item.label for item in painel.metric],
        )
        self.assertEqual(
            [item.label for item in painel.expander],
            ["Sobre os dados"],
        )
        self.assertFalse(painel.expander[0].proto.expanded)
        self.assertEqual(len(painel.caption), 1)
        self.assertNotIn(
            "Uso local",
            painel.caption[0].value,
        )
        self.assertIn(
            "Este painel usa dados locais",
            painel.expander[0].markdown[0].value,
        )


if __name__ == "__main__":
    unittest.main()
