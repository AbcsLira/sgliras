"""Garante que a fonte local referenciada nos estilos é íntegra e servida pelo Flask."""
from hashlib import sha256
from pathlib import Path
import re
import struct
import unittest

from sgliras import create_app


RAIZ = Path(__file__).resolve().parent.parent
SHA256_INTER = '693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3'


class FontesLocaisTests(unittest.TestCase):
    def test_binario_woff2_oficial_e_licenca_preservados(self):
        dados = (RAIZ / 'static/fonts/InterVariable.woff2').read_bytes()
        assinatura, _, comprimento, tabelas, reservado = struct.unpack('>4sIIHH', dados[:16])
        self.assertEqual(assinatura, b'wOF2')
        self.assertEqual(comprimento, len(dados))
        self.assertGreater(tabelas, 0)
        self.assertEqual(reservado, 0)
        self.assertEqual(sha256(dados).hexdigest(), SHA256_INTER)
        licenca = (RAIZ / 'static/fonts/OFL.txt').read_text(encoding='utf-8')
        self.assertIn('SIL OPEN FONT LICENSE Version 1.1', licenca)
        self.assertIn('Copyright (c) 2016 The Inter Project Authors', licenca)

    def test_ambos_estilos_referenciam_fonte_local_servida_sem_autenticacao(self):
        app = create_app({'TESTING': True, 'SECRET_KEY': 'fontes-apenas-testes'})
        cliente = app.test_client()
        for nome in ('index.css', 'login.css'):
            with self.subTest(estilo=nome):
                estilo = (RAIZ / 'static/css' / nome).read_text(encoding='utf-8')
                urls = re.findall(r'url\([\'\"]?([^\)\'\"]+)', estilo)
                self.assertIn('/static/fonts/InterVariable.woff2', urls)
                for url in urls:
                    self.assertTrue(url.startswith('/static/fonts/'), url)
                    with cliente.get(url) as resposta:
                        self.assertEqual(resposta.status_code, 200)
                        self.assertEqual(resposta.mimetype, 'font/woff2')
                        self.assertEqual(sha256(resposta.data).hexdigest(), SHA256_INTER)


if __name__ == '__main__':
    unittest.main()
