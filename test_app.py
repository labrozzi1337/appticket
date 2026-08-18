import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as painel


class PainelTest(unittest.TestCase):
    def setUp(self):
        self.ambiente = {k: os.environ.get(k) for k in (
            "APP_SESSION_SECRET", "STORAGE_BACKEND", "VERCEL", "SUPABASE_SECRET_KEY"
        )}
        os.environ.update(
            APP_SESSION_SECRET="segredo-de-teste-com-mais-de-trinta-e-dois-caracteres",
            STORAGE_BACKEND="sqlite",
            SUPABASE_SECRET_KEY="segredo-exclusivo-do-backend",
        )
        os.environ.pop("VERCEL", None)
        arquivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        arquivo.close()
        self.db_teste = arquivo.name
        self.db_original, painel.DB = painel.DB, self.db_teste
        self.auth_original = painel.autenticar_supabase
        painel.autenticar_supabase = lambda usuario, senha: (
            (usuario, senha) == ("cfo", "correta"), "Usuario ou senha invalidos."
        )
        self.client = TestClient(painel.app)

    def tearDown(self):
        self.client.close()
        painel.autenticar_supabase = self.auth_original
        painel.DB = self.db_original
        with contextlib.suppress(OSError):
            os.remove(self.db_teste)
        for chave, valor in self.ambiente.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor

    def login(self):
        resposta = self.client.post("/login", json={"usuario": "cfo", "senha": "correta"})
        self.assertEqual(resposta.status_code, 200)
        return resposta

    def test_login_cookie_assinado_e_logout(self):
        self.assertIn("Bem-vindo", self.client.get("/").text)
        self.assertEqual(self.client.get("/dados").status_code, 401)
        self.assertEqual(self.client.post("/login", json={}).status_code, 400)
        self.assertEqual(self.client.post("/login", json={"usuario": "cfo", "senha": "errada"}).status_code, 401)

        resposta = self.login()
        cookie = resposta.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertNotIn("segredo-de-teste", cookie)
        self.assertIn("Visão executiva", self.client.get("/").text)

        saida = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(saida.status_code, 302)
        self.assertIn("Max-Age=0", saida.headers["set-cookie"])

    def test_coletor_ingest_dados_exportacao_e_limpeza(self):
        self.login()
        resposta = self.client.get("/coletor.js")
        self.assertEqual(resposta.status_code, 200)
        script = resposta.text
        self.assertIn("\"http://testserver\" + '/ingest'", script)
        self.assertNotIn("localhost:8000", script)
        self.assertNotIn(os.environ["SUPABASE_SECRET_KEY"], script)
        token = re.search(r"'X-Ingest-Token': '([^']+)'", script).group(1)

        producao = self.client.get("/coletor.js", headers={
            "x-forwarded-proto": "https", "x-forwarded-host": "painel.vercel.app"
        }).text
        self.assertIn("\"https://painel.vercel.app\" + '/ingest'", producao)

        registro = {"id_transacao": "1556034", "nome": "Mauricio", "status_code": "4",
                    "qtde_tickets": 1, "total": 0, "desconto": 497, "erro": None}
        sem_sessao = TestClient(painel.app)
        try:
            ingest = sem_sessao.post("/ingest", json=[registro], headers={"X-Ingest-Token": token})
        finally:
            sem_sessao.close()
        self.assertEqual(ingest.status_code, 200)
        self.assertEqual(ingest.text, "1 linhas gravadas")

        importado = dict(registro, id_transacao="1556035", nome="Ana")
        resposta_importacao = self.client.post(
            "/ingest", content=json.dumps([importado]), headers={"Content-Type": "text/plain"}
        )
        self.assertEqual(resposta_importacao.status_code, 200)

        dados = self.client.get("/dados").json()
        self.assertEqual(len(dados["rows"]), 2)
        linha = dict(zip(dados["cols"], dados["rows"][0]))
        self.assertEqual((linha["qtde_tickets"], linha["desconto"]), ("1", "497"))

        csv = self.client.get("/export.csv")
        self.assertEqual(csv.status_code, 200)
        self.assertTrue(csv.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("attachment", csv.headers["content-disposition"])

        self.assertEqual(self.client.post("/limpar").json(), {"ok": True})
        self.assertEqual(self.client.get("/dados").json()["rows"], [])

    def test_cookie_secure_na_vercel(self):
        os.environ["VERCEL"] = "1"
        self.assertIn("Secure", self.login().headers["set-cookie"])

    def test_vercel_escolhe_supabase_sem_escrita_sqlite(self):
        os.environ.pop("STORAGE_BACKEND", None)
        os.environ["VERCEL"] = "1"
        self.assertTrue(painel.usar_supabase())

    def test_supabase_usa_schema_e_chave_apenas_no_servidor(self):
        class Resposta(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        os.environ.update(SUPABASE_URL="https://teste.supabase.co", SUPABASE_SCHEMA="appticket")

        def abrir(req, timeout=0):
            self.assertEqual(req.get_header("Accept-profile"), "appticket")
            self.assertEqual(req.get_header("Apikey"), "segredo-exclusivo-do-backend")
            self.assertIsNone(req.get_header("Authorization"))
            return Resposta(b"[]")

        with patch("urllib.request.urlopen", abrir):
            self.assertEqual(painel._supabase("GET", "transacoes", "?select=id_transacao"), [])

    def test_dashboard_filtros_e_regras_permanecem_presentes(self):
        fonte = painel.PAGINA
        for trecho in (
            "function noPeriodo()", "function aplicarCustom()", "F=R.filter(noPeriodo())",
            "STATUS_SEL=new Set()", "function filtraTabela()", "function exportaFiltrado()",
            "num(r[col(discKey)])>0&&num(r[col('total')])===0", "const ticketsEmitidos=ap.reduce",
            "const checkoutVazio=", "Visão executiva", "Coletar dados",
        ):
            self.assertIn(trecho, fonte)

    def test_fonte_nao_contem_servidor_legado(self):
        with open(painel.__file__, encoding="utf-8") as arquivo:
            fonte = arquivo.read()
        for legado in ("ThreadingHTTPServer", "BaseHTTPRequestHandler", "serve_forever", "SESSOES", "TOKENS_COLETA"):
            self.assertNotIn(legado, fonte)


if __name__ == "__main__":
    unittest.main()
