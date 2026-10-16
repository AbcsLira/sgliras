// Confere os filtros reais de nome, categoria e estoque na prévia de impressão.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function previa() {
  const elementos = {'lst-nome': {value: ''}, 'lst-preview': {innerHTML: ''}};
  const categorias = [];
  const estoque = {dataset: {modo: 'todos'}};
  const contexto = vm.createContext({
    produtos: [
      {nome: 'Molho de Pizza', codigo: 'OUTRO', categoria: 'Molhos', quantidade: 5, estoque_min: 1},
      {nome: 'Molho de Tomate', codigo: 'PIZZA', categoria: 'Molhos', quantidade: 0, estoque_min: 1},
      {nome: 'Açaí Especial', categoria: 'Frutas', quantidade: 2, estoque_min: 3},
    ],
    document: {
      getElementById: id => elementos[id],
      querySelectorAll: () => categorias,
      querySelector: () => estoque,
      addEventListener() {},
    },
  });
  for (const arquivo of ['utilitarios.js', 'impressao.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/modules', arquivo), 'utf8'), contexto);
  }
  return {
    categorias, estoque,
    buscar(nome) {
      elementos['lst-nome'].value = nome;
      vm.runInContext('atualizarPreviewListagem()', contexto);
      return elementos['lst-preview'].innerHTML;
    },
  };
}

test('prévia combina palavras do nome sem exigir ordem ou acentos', () => {
  const p = previa();
  for (const nome of ['molho pizza', 'PIZZA molho', '  mol\t pizz  ', 'especial acai']) {
    assert.match(p.buscar(nome), /✓ 1 produto serão listados/, nome);
  }
  assert.match(p.buscar('pizza tomate'), /Nenhum produto/);
  assert.match(p.buscar(''), /✓ 3 produtos serão listados/);
});

test('prévia mantém busca apenas por nome e combina categoria e estoque', () => {
  const p = previa();
  assert.match(p.buscar('pizza'), /✓ 1 produto serão listados/);
  p.categorias.push({dataset: {cat: 'Frutas'}});
  assert.match(p.buscar('pizza'), /Nenhum produto/);
  assert.match(p.buscar('acai'), /✓ 1 produto serão listados/);
  p.estoque.dataset.modo = 'zerado';
  assert.match(p.buscar('acai'), /Nenhum produto/);
});
