"""Regras de cartões exercitadas pela API, sempre em bancos temporários."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from sgliras import create_app
from sgliras.banco_dados import init_db


class TesteCartoes(unittest.TestCase):
    prefixo = "/api/fin/cartoes"

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.banco = str(Path(self.pasta.name) / "cartoes.db")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "apenas-testes-cartoes",
                               "DATABASE": self.banco,
                               "BACKUP_DIR": str(Path(self.pasta.name) / "copias")})
        with self.app.app_context():
            init_db()
        self.cliente = self.cliente_admin()
        self.contador = 0

    def cliente_admin(self):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sessao:
            sessao.update(usuario_id=1, usuario="admin", perfil="admin")
        return cliente

    def linhas(self, sql, parametros=()):
        with closing(sqlite3.connect(self.banco)) as db:
            db.row_factory = sqlite3.Row
            return [dict(linha) for linha in db.execute(sql, parametros)]

    def executar(self, sql, parametros=()):
        with closing(sqlite3.connect(self.banco)) as db, db:
            db.execute(sql, parametros)

    def dados_condicao(self, **alteracoes):
        return {"operadora_id": "cielo", "modalidade": "credito", "bandeira": "",
                "inicio_vigencia": "2026-01-01", "taxa_percentual": "2.5",
                "prazo_dias": 30, "tipo_dias": "corridos", "intervalo_parcelas_dias": None,
                **alteracoes}

    def condicao(self, **alteracoes):
        resposta = self.cliente.post(self.prefixo + "/condicoes", json=self.dados_condicao(**alteracoes))
        self.assertIn(resposta.status_code, (200, 201), resposta.json)
        self.assertTrue(resposta.json["ok"])
        return resposta.json["id"]

    def dados_venda(self, **alteracoes):
        self.contador += 1
        return {"operacao_id": f"cartoes-teste-{self.contador}", "operadora_id": "cielo",
                "modalidade": "credito", "bandeira": "", "data_venda": "2026-10-01",
                "valor_bruto": "100.01", "observacao": "Total do dia", **alteracoes}

    def venda(self, **alteracoes):
        resposta = self.cliente.post(self.prefixo + "/vendas", json=self.dados_venda(**alteracoes))
        self.assertEqual(resposta.status_code, 201, resposta.json)
        self.assertTrue(resposta.json["ok"])
        return resposta.json["id"]

    def vendas(self, **filtros):
        resposta = self.cliente.get(self.prefixo + "/vendas", query_string=filtros)
        self.assertEqual(resposta.status_code, 200, resposta.json)
        return resposta.json

    def relatorio(self, mes="2026-10", operadora=""):
        resposta = self.cliente.get(self.prefixo + "/relatorio", query_string={"mes": mes, "operadora": operadora})
        self.assertEqual(resposta.status_code, 200, resposta.json)
        return resposta.json

    def parcelas(self, venda_id, mes="2026-10"):
        return [p for p in self.relatorio(mes)["parcelas"] if p["venda_id"] == venda_id]

    def receber(self, parcela_id, valor="97.51", data="2026-10-31", **alteracoes):
        return self.cliente.post(f"{self.prefixo}/parcelas/{parcela_id}/recebimento", json={
            "data_recebimento": data, "valor_recebido": valor, "observacao": "Repasse conferido", **alteracoes})

    def estado(self):
        tabelas = ("fin_cartoes_condicoes", "fin_cartoes_vendas", "fin_cartoes_parcelas",
                   "operacoes_idempotentes", "log_auditoria")
        return {tabela: self.linhas(f"SELECT * FROM {tabela} ORDER BY id" if tabela != "operacoes_idempotentes"
                                   else f"SELECT * FROM {tabela} ORDER BY operacao_id") for tabela in tabelas}

    def test_configuracao_inicial_sem_taxas_ou_prazos_inventados(self):
        resposta = self.cliente.get(self.prefixo + "/configuracao")
        self.assertEqual(resposta.status_code, 200, resposta.json)
        self.assertEqual(resposta.json["condicoes"], [])
        self.assertEqual([(o["id"], o["cor"]) for o in resposta.json["operadoras"]],
                         [("cielo", "#168bd2"), ("rede", "#f58220"), ("sipag", "#19964b")])
        self.assertEqual(self.relatorio()["parcelas"], [])

    def test_todas_as_rotas_exigem_administrador(self):
        rotas = [("GET", "/configuracao"), ("POST", "/condicoes"), ("GET", "/vendas"),
                 ("POST", "/vendas"), ("PUT", "/vendas/1"), ("DELETE", "/vendas/1"),
                 ("POST", "/vendas/calcular-pendentes"), ("POST", "/parcelas/1/recebimento"),
                 ("DELETE", "/parcelas/1/recebimento"), ("PUT", "/parcelas/1/previsao"),
                 ("GET", "/relatorio")]
        anonimo = self.app.test_client()
        for metodo, caminho in rotas:
            with self.subTest(perfil="anônimo", metodo=metodo, caminho=caminho):
                self.assertEqual(anonimo.open(self.prefixo + caminho, method=metodo, json={}).status_code, 401)
        for perfil in ("caixa", "estoquista"):
            self.executar("UPDATE usuarios SET perfil=? WHERE id=1", (perfil,))
            for metodo, caminho in rotas:
                with self.subTest(perfil=perfil, metodo=metodo, caminho=caminho):
                    self.assertEqual(self.cliente.open(self.prefixo + caminho, method=metodo, json={}).status_code, 403)

    def test_venda_sem_condicao_permanece_pendente_ate_calculo_explicito(self):
        vid = self.venda(modalidade="voucher")
        venda = self.vendas()[0]
        self.assertFalse(venda["calculado"])
        self.assertIsNone(venda["taxa_percentual"])
        self.assertEqual(self.parcelas(vid), [])
        self.assertEqual(self.relatorio()["pendentes_configuracao"], {"quantidade": 1, "bruto_centavos": 10001})
        self.condicao(modalidade="voucher", prazo_dias=0, taxa_percentual="0")
        self.assertFalse(self.vendas()[0]["calculado"])
        resposta = self.cliente.post(self.prefixo + "/vendas/calcular-pendentes")
        self.assertEqual(resposta.json, {"ok": True, "calculadas": 1, "pendentes": 0})
        self.assertEqual(self.parcelas(vid)[0]["liquido_centavos"], 10001)
        self.assertEqual(self.cliente.post(self.prefixo + "/vendas/calcular-pendentes").json["calculadas"], 0)

    def test_pendencias_incluem_todas_as_datas_mas_respeitam_operadora(self):
        self.venda(valor_bruto="10", data_venda="2026-01-01")
        self.venda(valor_bruto="20", data_venda="2026-02-01")
        self.venda(valor_bruto="30", operadora_id="sipag")
        self.assertEqual(self.relatorio(operadora="cielo")["pendentes_configuracao"],
                         {"quantidade": 2, "bruto_centavos": 3000})
        self.assertEqual(self.relatorio()["resumo"]["saldo_centavos"], 0)

    def test_vigencia_preserva_snapshot_e_nao_recalcula_historico(self):
        self.condicao(taxa_percentual="2", prazo_dias=0)
        antiga = self.venda(valor_bruto="100")
        self.condicao(taxa_percentual="3", inicio_vigencia="2026-10-02", prazo_dias=0)
        nova = self.venda(data_venda="2026-10-03", valor_bruto="100")
        self.condicao(taxa_percentual="9", prazo_dias=10)
        self.cliente.post(self.prefixo + "/vendas/calcular-pendentes")
        self.assertEqual(self.parcelas(antiga)[0]["liquido_centavos"], 9800)
        self.assertEqual(self.parcelas(nova)[0]["liquido_centavos"], 9700)

    def test_condicao_futura_nao_se_aplica_a_venda_anterior(self):
        self.condicao(inicio_vigencia="2026-10-02")
        self.venda()
        self.assertFalse(self.vendas()[0]["calculado"])

    def test_bandeira_especifica_valida_prevalece_sobre_padrao_mais_novo(self):
        self.condicao(bandeira=" VÍSA ", taxa_percentual="1", prazo_dias=0)
        self.condicao(inicio_vigencia="2026-09-01", taxa_percentual="5", prazo_dias=0)
        vid = self.venda(bandeira="vi\u0301sa", valor_bruto="100")
        self.assertEqual(self.parcelas(vid)[0]["liquido_centavos"], 9900)
        self.assertEqual(self.vendas()[0]["bandeira"], "vísa")

    def test_bandeira_especifica_futura_nao_oculta_padrao_vigente(self):
        self.condicao(taxa_percentual="2", prazo_dias=0)
        self.condicao(bandeira="visa", inicio_vigencia="2026-11-01", taxa_percentual="1", prazo_dias=0)
        vid = self.venda(bandeira="VISA", valor_bruto="100")
        self.assertEqual(self.parcelas(vid)[0]["liquido_centavos"], 9800)

    def test_alterar_mesma_vigencia_atualiza_condicao_sem_duplicar(self):
        cid = self.condicao(taxa_percentual="1.123456")
        self.assertEqual(self.condicao(taxa_percentual="2.123456"), cid)
        condicoes = self.cliente.get(self.prefixo + "/configuracao").json["condicoes"]
        self.assertEqual(len(condicoes), 1)
        self.assertEqual(condicoes[0]["taxa_percentual"], "2.123456")

    def test_credito_2x_preserva_centavos_e_relatorio_nao_duplica_bruto(self):
        self.condicao(modalidade="credito_2x", taxa_percentual="2.5", prazo_dias=30, intervalo_parcelas_dias=30)
        vid = self.venda(modalidade="credito_2x", valor_bruto="100.01")
        parcelas = self.parcelas(vid) + self.parcelas(vid, "2026-11")
        self.assertEqual(len(parcelas), 2)
        self.assertEqual([p["data_prevista"] for p in parcelas], ["2026-10-31", "2026-11-30"])
        self.assertEqual(sum(p["bruto_centavos"] for p in parcelas), 10001)
        self.assertEqual(sum(p["taxa_centavos"] for p in parcelas), 250)
        self.assertEqual(sum(p["liquido_centavos"] for p in parcelas), 9751)
        self.assertEqual(self.relatorio()["resumo"]["bruto_centavos"], parcelas[0]["bruto_centavos"])
        self.assertEqual(len(self.relatorio()["agenda_mensal"]), 2)

    def test_taxa_total_arredonda_antes_da_divisao_em_duas_parcelas(self):
        self.condicao(modalidade="credito_2x", taxa_percentual="50", prazo_dias=0, intervalo_parcelas_dias=1)
        vid = self.venda(modalidade="credito_2x", valor_bruto="0.03")
        parcelas = self.parcelas(vid)
        self.assertEqual(sum(p["taxa_centavos"] for p in parcelas), 2)
        self.assertEqual(sum(p["liquido_centavos"] for p in parcelas), 1)
        self.assertTrue(all(p["liquido_centavos"] >= 0 for p in parcelas))

    def test_prazos_uteis_pulam_fim_de_semana(self):
        self.condicao(modalidade="debito", prazo_dias=1, tipo_dias="uteis")
        vid = self.venda(modalidade="debito", data_venda="2026-10-02")
        self.assertEqual(self.parcelas(vid)[0]["data_prevista"], "2026-10-05")

    def test_valores_de_venda_invalidos_nao_gravam(self):
        for valor in (0, -1, True, None, "NaN", "Infinity", "1.001", "10000000.01", [], {}):
            with self.subTest(valor=valor):
                resposta = self.cliente.post(self.prefixo + "/vendas", json=self.dados_venda(valor_bruto=valor))
                self.assertEqual(resposta.status_code, 400, resposta.json)
        self.assertEqual(self.vendas(), [])

    def test_limite_monetario_e_taxa_zero_sao_aceitos(self):
        self.condicao(taxa_percentual="0", prazo_dias=0)
        vid = self.venda(valor_bruto="10000000.00")
        self.assertEqual(self.parcelas(vid)[0]["liquido_centavos"], 1000000000)

    def test_condicoes_invalidas_nao_gravam(self):
        alteracoes = ({"taxa_percentual": -1}, {"taxa_percentual": "100.000001"},
                      {"taxa_percentual": "1.0000001"}, {"taxa_percentual": "NaN"},
                      {"prazo_dias": 366}, {"prazo_dias": 1.5}, {"prazo_dias": True},
                      {"tipo_dias": "mensais"}, {"inicio_vigencia": "2026-02-30"},
                      {"modalidade": "credito_3x"}, {"operadora_id": "outra"},
                      {"operadora_id": []}, {"modalidade": "credito_2x", "intervalo_parcelas_dias": None},
                      {"modalidade": "credito_2x", "intervalo_parcelas_dias": 0})
        for invalida in alteracoes:
            with self.subTest(alteracao=invalida):
                resposta = self.cliente.post(self.prefixo + "/condicoes", json=self.dados_condicao(**invalida))
                self.assertEqual(resposta.status_code, 400, resposta.json)
        self.assertEqual(self.cliente.get(self.prefixo + "/configuracao").json["condicoes"], [])

    def test_payloads_e_filtros_invalidos_retornam_400(self):
        for valor in ([], None, "texto"):
            with self.subTest(valor=valor):
                self.assertEqual(self.cliente.post(self.prefixo + "/vendas", json=valor).status_code, 400)
        for caminho in ("/relatorio?mes=2026-13", "/relatorio?mes=2026-1", "/relatorio?operadora=invalida",
                        "/vendas?mes=ontem", "/vendas?operadora=invalida"):
            self.assertEqual(self.cliente.get(self.prefixo + caminho).status_code, 400, caminho)
        for invalida in ({"data_venda": "2026-02-30"}, {"modalidade": "credito_3x"}, {"bandeira": []}):
            self.assertEqual(self.cliente.post(self.prefixo + "/vendas", json=self.dados_venda(**invalida)).status_code, 400)

    def test_repeticao_da_mesma_operacao_nao_duplica_venda(self):
        dados = self.dados_venda()
        primeira = self.cliente.post(self.prefixo + "/vendas", json=dados)
        segunda = self.cliente.post(self.prefixo + "/vendas", json=dados)
        self.assertEqual([primeira.status_code, segunda.status_code], [201, 200])
        self.assertEqual(primeira.json, segunda.json)
        self.assertEqual(len(self.vendas()), 1)
        alterada = self.cliente.post(self.prefixo + "/vendas", json={**dados, "valor_bruto": "200"})
        self.assertEqual(alterada.status_code, 409)

    def test_total_diario_duplicado_com_outra_chave_e_recusado(self):
        self.venda(bandeira=" VISA ")
        resposta = self.cliente.post(self.prefixo + "/vendas", json=self.dados_venda(bandeira="visa"))
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(len(self.vendas()), 1)

    def test_repeticoes_concorrentes_criam_uma_unica_venda(self):
        dados = self.dados_venda()
        barreira = Barrier(2)

        def enviar(_):
            cliente = self.cliente_admin()
            barreira.wait(timeout=10)
            return cliente.post(self.prefixo + "/vendas", json=dados).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(enviar, range(2)))
        self.assertEqual(sorted(resultados), [200, 201])
        self.assertEqual(len(self.vendas()), 1)

    def test_edicao_explicita_recalcula_e_exclusao_remove_parcelas(self):
        self.condicao(taxa_percentual="1", prazo_dias=0)
        vid = self.venda(valor_bruto="100")
        self.condicao(taxa_percentual="2", prazo_dias=0)
        resposta = self.cliente.put(f"{self.prefixo}/vendas/{vid}", json=self.dados_venda(valor_bruto="200"))
        self.assertEqual(resposta.status_code, 200, resposta.json)
        self.assertEqual(self.parcelas(vid)[0]["liquido_centavos"], 19600)
        self.assertEqual(self.cliente.delete(f"{self.prefixo}/vendas/{vid}").status_code, 200)
        self.assertEqual(self.vendas(), [])
        self.assertEqual(self.relatorio()["parcelas"], [])

    def test_edicao_duplicada_desfaz_tambem_a_remocao_das_parcelas(self):
        self.condicao(prazo_dias=0)
        primeira = self.venda()
        self.venda(data_venda="2026-10-02")
        antes = self.estado()
        resposta = self.cliente.put(f"{self.prefixo}/vendas/{primeira}", json=self.dados_venda(data_venda="2026-10-02"))
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.estado(), antes)

    def test_recebido_em_outro_mes_segue_data_real_sem_mudar_previsao(self):
        self.condicao()
        vid = self.venda()
        pid = self.parcelas(vid)[0]["id"]
        self.assertEqual(self.receber(pid, data="2026-11-02").status_code, 200)
        outubro, novembro = self.relatorio(), self.relatorio("2026-11")
        self.assertEqual(outubro["resumo"]["recebido_no_mes_centavos"], 0)
        self.assertEqual(outubro["resumo"]["saldo_centavos"], 0)
        self.assertEqual(novembro["resumo"]["recebido_no_mes_centavos"], 9751)
        self.assertEqual(novembro["parcelas"], [])
        self.assertEqual(novembro["por_operadora"][0]["recebido_no_mes_centavos"], 9751)
        self.assertEqual(outubro["agenda_mensal"][-1]["recebido_no_mes_centavos"], 9751)

    def test_diferenca_e_liquidada_sem_deixar_saldo_ficticio(self):
        self.condicao()
        vid = self.venda()
        pid = self.parcelas(vid)[0]["id"]
        self.assertEqual(self.receber(pid, valor="97").status_code, 200)
        relatorio = self.relatorio()
        self.assertEqual(relatorio["parcelas"][0]["status"], "divergente")
        self.assertEqual(relatorio["resumo"]["diferenca_centavos"], -51)
        self.assertEqual(relatorio["resumo"]["saldo_centavos"], 0)

    def test_recebimento_zero_protege_venda_e_informa_flag(self):
        self.condicao()
        vid = self.venda()
        self.assertFalse(self.vendas()[0]["possui_recebimento"])
        pid = self.parcelas(vid)[0]["id"]
        self.assertEqual(self.receber(pid, valor="0").status_code, 200)
        self.assertTrue(self.vendas()[0]["possui_recebimento"])
        self.assertEqual(self.cliente.put(f"{self.prefixo}/vendas/{vid}", json=self.dados_venda()).status_code, 409)
        self.assertEqual(self.cliente.delete(f"{self.prefixo}/vendas/{vid}").status_code, 409)
        self.assertEqual(self.cliente.put(f"{self.prefixo}/parcelas/{pid}/previsao", json={"data_prevista": "2026-11-01"}).status_code, 409)

    def test_recebimento_repetido_idempotente_mas_valor_diferente_conflita(self):
        self.condicao()
        pid = self.parcelas(self.venda())[0]["id"]
        self.assertEqual(self.receber(pid).status_code, 200)
        antes = self.estado()
        self.assertEqual(self.receber(pid).status_code, 200)
        self.assertEqual(self.estado(), antes)
        self.assertEqual(self.receber(pid, valor="90").status_code, 409)
        self.assertEqual(self.receber(pid, data="2026-11-01").status_code, 409)
        self.assertEqual(self.receber(pid, observacao="Outro repasse").status_code, 409)
        self.assertEqual(self.estado(), antes)

    def test_recebimentos_invalidos_preservam_parcela_em_aberto(self):
        self.condicao()
        pid = self.parcelas(self.venda())[0]["id"]
        antes = self.estado()
        for valor in (-1, "NaN", "1.001", True, None, []):
            with self.subTest(valor=valor):
                self.assertEqual(self.receber(pid, valor=valor).status_code, 400)
        self.assertEqual(self.receber(pid, data="2026-02-30").status_code, 400)
        self.assertEqual(self.estado(), antes)

    def test_previsao_fora_do_calendario_desfaz_gravacao(self):
        self.condicao(prazo_dias=30)
        antes = self.estado()
        resposta = self.cliente.post(self.prefixo + "/vendas", json=self.dados_venda(data_venda="9999-12-31"))
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(self.estado(), antes)

    def test_estorno_reabre_parcela_e_permite_edicao(self):
        self.condicao()
        vid = self.venda()
        pid = self.parcelas(vid)[0]["id"]
        self.receber(pid)
        resposta = self.cliente.delete(f"{self.prefixo}/parcelas/{pid}/recebimento")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(self.vendas()[0]["possui_recebimento"])
        self.assertEqual(self.relatorio()["resumo"]["saldo_centavos"], 9751)
        self.assertEqual(self.relatorio()["resumo"]["recebido_no_mes_centavos"], 0)
        self.assertEqual(self.cliente.put(f"{self.prefixo}/vendas/{vid}", json=self.dados_venda(valor_bruto="200")).status_code, 200)

    def test_ajuste_previsao_move_mes_e_fica_auditado(self):
        self.condicao()
        vid = self.venda()
        pid = self.parcelas(vid)[0]["id"]
        resposta = self.cliente.put(f"{self.prefixo}/parcelas/{pid}/previsao", json={"data_prevista": "2026-11-03"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.parcelas(vid), [])
        self.assertEqual(self.parcelas(vid, "2026-11")[0]["data_prevista"], "2026-11-03")
        self.assertTrue(self.linhas("SELECT * FROM log_auditoria WHERE entidade='cartoes_parcela' AND entidade_id=?", (pid,)))

    def test_filtros_de_mes_e_operadora_em_vendas_e_relatorio(self):
        for operadora in ("cielo", "rede", "sipag"):
            self.condicao(operadora_id=operadora, prazo_dias=0)
            self.venda(operadora_id=operadora)
        self.venda(data_venda="2026-11-01")
        self.assertEqual(len(self.vendas(mes="2026-10", operadora="cielo")), 1)
        relatorio = self.relatorio(operadora="rede")
        self.assertEqual(len(relatorio["parcelas"]), 1)
        self.assertEqual([p["operadora_id"] for p in relatorio["por_operadora"]], ["rede"])
        self.assertEqual(relatorio["resumo"]["bruto_centavos"], 10001)

    def test_falha_na_auditoria_desfaz_toda_a_venda_e_idempotencia(self):
        self.condicao()
        antes = self.estado()
        self.executar("""CREATE TRIGGER falhar_auditoria BEFORE INSERT ON log_auditoria
                         WHEN NEW.entidade='cartoes_venda'
                         BEGIN SELECT RAISE(ABORT,'Falha simulada'); END""")
        resposta = self.cliente.post(self.prefixo + "/vendas", json=self.dados_venda())
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.estado(), antes)

    def test_reinicializacao_preserva_vendas_e_financeiro_legado_independente(self):
        tabelas = ("fin_fechamento_diario", "fin_contas_pagar", "fin_contas_receber")
        antes = {tabela: self.linhas(f"SELECT * FROM {tabela}") for tabela in tabelas}
        self.condicao()
        vid = self.venda()
        self.receber(self.parcelas(vid)[0]["id"])
        estado = self.estado()
        with self.app.app_context():
            self.assertIsNone(init_db())
        self.assertEqual(self.estado(), estado)
        self.assertEqual({tabela: self.linhas(f"SELECT * FROM {tabela}") for tabela in tabelas}, antes)


if __name__ == "__main__":
    unittest.main()
