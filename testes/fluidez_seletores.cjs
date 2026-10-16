// Uso: node testes/fluidez_seletores.cjs
// Executa os seletores reais com catálogo grande e relógio determinístico.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function relogio() {
  let agora = 0, proximoId = 0;
  const tarefas = new Map();
  return {
    setTimeout(fn, espera = 0) {
      const id = ++proximoId;
      tarefas.set(id, {fn, instante: agora + espera});
      return id;
    },
    clearTimeout(id) { tarefas.delete(id); },
    avancar(tempo) {
      const destino = agora + tempo;
      while (true) {
        const proxima = [...tarefas].filter(([, tarefa]) => tarefa.instante <= destino)
          .sort((a, b) => a[1].instante - b[1].instante)[0];
        if (!proxima) break;
        tarefas.delete(proxima[0]);
        agora = proxima[1].instante;
        proxima[1].fn();
      }
      agora = destino;
    },
  };
}

function resposta(dados, status = 200) {
  return {ok: status >= 200 && status < 300, status, json: async () => dados};
}

function navegador() {
  const elementos = new Map(), requisicoes = [], mensagens = [];
  const tempo = relogio();
  let responder = async () => resposta([]);
  function elemento(id) {
    if (!elementos.has(id)) {
      let html = '';
      elementos.set(id, {
        value: '', textContent: '', escritas: 0, disabled: false,
        get innerHTML() { return html; },
        set innerHTML(valor) { html = valor; this.escritas++; },
        classList: {add() {}, remove() {}},
        focus() {}, addEventListener() {}, querySelectorAll() { return []; },
      });
    }
    return elementos.get(id);
  }
  const produtos = Array.from({length: 1200}, (_, indice) => ({
    id: indice + 1, nome: `Produto ${String(indice + 1).padStart(4, '0')}`,
    codigo: `PROD-${String(indice + 1).padStart(4, '0')}`,
    codigo_barras: `789${String(indice + 1).padStart(8, '0')}`,
    ativo: 1, quantidade: 100, unidade: 'kg', preco_custo: 2,
    categoria: ['Alimentos', 'Molhos', 'Embalagens'][indice % 3],
  }));
  const contexto = vm.createContext({
    produtos, fornecedores: [{id: 1, nome: 'Fornecedor A'}, {id: 2, nome: 'Fornecedor B'}],
    fichaIngs: [], fichaCustosFixos: [], movProdId: null, me: {id: 7}, CAT_ICONS: {},
    document: {getElementById: elemento, querySelectorAll: () => []},
    setTimeout: tempo.setTimeout, clearTimeout: tempo.clearTimeout,
    toast: mensagem => mensagens.push(mensagem), confirm: () => false,
    fmtR: valor => `R$ ${Number(valor).toFixed(2)}`,
    fetch: async url => { requisicoes.push(url); return responder(url); },
  });
  for (const arquivo of ['utilitarios.js', 'movimentacoes.js', 'entrada_lote.js', 'compras.js', 'receitas.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/modules', arquivo), 'utf8'), contexto, {filename: arquivo});
  }
  return {
    contexto, elemento, tempo, produtos, requisicoes, mensagens,
    executar: codigo => vm.runInContext(codigo, contexto),
    entrada(id, valor) { elemento(id).value = valor; },
    responder(fn) { responder = fn; },
    opcoes(id) { return (elemento(id).innerHTML.match(/class="p-opt(?:\s[^"]*)?"/g) || []).length; },
  };
}

const seletores = [
  {nome: 'movimentação', filtro: 'filtrarMovBusca', entrada: 'mov-busca', lista: 'mov-lista'},
  {nome: 'saída em lote', filtro: 'filtrarLoteBusca', entrada: 'lote-busca', lista: 'lote-lista'},
  {nome: 'entrada em lote', filtro: 'filtrarEntradaLoteBusca', entrada: 'entrada-lote-busca', lista: 'entrada-lote-lista'},
  {nome: 'compras', filtro: 'filtrarCompraBusca', entrada: 'compra-busca', lista: 'compra-lista-busca'},
  {nome: 'ingredientes', filtro: 'filtrarIngModal', entrada: 'f-ing-busca', lista: 'f-ing-lista'},
];

for (const seletor of seletores) {
  test(`${seletor.nome}: combina palavras fora de ordem e ignora acentos`, async () => {
    const n = navegador();
    n.produtos.at(-1).nome = 'Molho de Pizza com Açaí';
    for (const busca of ['molho pizza', 'ACAI pizza MOLHO', '  pizz\t mol  ']) {
      n.entrada(seletor.entrada, busca);
      await n.executar(`${seletor.filtro}()`);
      assert.equal(n.opcoes(seletor.lista), 1, busca);
      assert.match(n.elemento(seletor.lista).innerHTML, /Molho de Pizza com Açaí/);
    }
    n.entrada(seletor.entrada, 'molho tomate');
    await n.executar(`${seletor.filtro}()`);
    assert.equal(n.opcoes(seletor.lista), 0);
  });

  test(`${seletor.nome}: renderiza 50 opções sem truncar o catálogo`, async () => {
    const n = navegador();
    await n.executar(`${seletor.filtro}()`);
    assert.equal(n.opcoes(seletor.lista), 50);
    assert.match(n.elemento(seletor.lista).innerHTML, /Mostrando 50 de 1200\. Refine a busca/);
    assert.equal(n.produtos.length, 1200);
  });

  test(`${seletor.nome}: encontra o último produto por nome, código e barras`, async () => {
    const n = navegador();
    const ultimo = n.produtos.at(-1);
    for (const busca of [ultimo.nome.toUpperCase(), ultimo.codigo.toLowerCase(), ultimo.codigo_barras]) {
      n.entrada(seletor.entrada, ` ${busca} `);
      await n.executar(`${seletor.filtro}()`);
      assert.equal(n.opcoes(seletor.lista), 1);
      assert.match(n.elemento(seletor.lista).innerHTML, /Produto 1200/);
      assert.doesNotMatch(n.elemento(seletor.lista).innerHTML, /Refine a busca/);
    }
  });

  test(`${seletor.nome}: agrupa digitação por 150 ms e usa a busca mais recente`, async () => {
    const n = navegador();
    for (const texto of ['PROD-', 'PROD-01', 'PROD-1200']) {
      n.entrada(seletor.entrada, texto);
      n.executar(`${seletor.filtro}AoDigitar()`);
    }
    assert.equal(n.elemento(seletor.lista).escritas, 0);
    n.tempo.avancar(149);
    assert.equal(n.elemento(seletor.lista).escritas, 0);
    n.tempo.avancar(1);
    assert.equal(n.elemento(seletor.lista).escritas, 1);
    assert.match(n.elemento(seletor.lista).innerHTML, /Produto 1200/);
  });

  test(`${seletor.nome}: busca direta é imediata e cancela digitação pendente`, async () => {
    const n = navegador();
    n.entrada(seletor.entrada, 'PROD-');
    n.executar(`${seletor.filtro}AoDigitar()`);
    n.entrada(seletor.entrada, 'PROD-1200');
    await n.executar(`${seletor.filtro}()`);
    assert.equal(n.elemento(seletor.lista).escritas, 1);
    n.tempo.avancar(150);
    assert.equal(n.elemento(seletor.lista).escritas, 1);
  });
}

test('scanners continuam encontrando o catálogo inteiro sem aguardar debounce', () => {
  const n = navegador();
  const ultimo = n.produtos.at(-1);
  n.entrada('mov-scan', ultimo.codigo_barras);
  n.executar('movProcessarScan()');
  assert.equal(n.contexto.movProdId, ultimo.id);
  n.entrada('entrada-lote-scan', ultimo.codigo_barras);
  n.executar("loteProcessarScan('entrada-lote-scan',adicionarItemEntradaLote)");
  assert.equal(n.executar('entradaLoteItens[0].produto_id'), ultimo.id);
  n.entrada('lote-scan', ultimo.codigo_barras);
  n.executar("loteProcessarScan('lote-scan',adicionarItemLote)");
  assert.equal(n.executar('loteItens[0].produto_id'), ultimo.id);
});

test('filtro de categoria continua imediato e mantém regras de ingredientes', () => {
  const n = navegador();
  n.produtos.push(
    {id: 1201, nome: 'Inativo', codigo: 'INATIVO', ativo: 0, preco_custo: 2, categoria: 'Molhos'},
    {id: 1202, nome: 'Sem custo', codigo: 'SEM-CUSTO', ativo: 1, preco_custo: 0, categoria: 'Molhos'},
    {id: 1203, nome: 'Limpeza', codigo: 'LIMPEZA', ativo: 1, preco_custo: 2, categoria: 'Limpeza'},
  );
  n.executar('filtrarIngModalAoDigitar()');
  n.executar("setIngCatFiltro('Molhos')");
  assert.equal(n.opcoes('f-ing-lista'), 50);
  assert.match(n.elemento('f-ing-lista').innerHTML, /Mostrando 50 de 400/);
  const escritas = n.elemento('f-ing-lista').escritas;
  n.tempo.avancar(150);
  assert.equal(n.elemento('f-ing-lista').escritas, escritas);
  for (const busca of ['INATIVO', 'SEM-CUSTO', 'LIMPEZA']) {
    n.entrada('f-ing-busca', busca);
    n.executar('filtrarIngModal()');
    assert.equal(n.opcoes('f-ing-lista'), 0);
  }
});

test('compras ignora resposta antiga ao trocar de fornecedor', async () => {
  const n = navegador();
  let concluirA, concluirB;
  n.responder(url => new Promise(resolve => {
    if (url.includes('/1/')) concluirA = resolve;
    if (url.includes('/2/')) concluirB = resolve;
  }));
  const anterior = n.executar('setCompraFornFiltro(1)');
  const atual = n.executar('setCompraFornFiltro(2)');
  concluirB(resposta([{...n.produtos[0], nome: 'Produto do fornecedor atual'}]));
  await atual;
  const htmlAtual = n.elemento('compra-lista-busca').innerHTML;
  concluirA(resposta([{...n.produtos[1], nome: 'Produto do fornecedor antigo'}]));
  await anterior;
  assert.equal(n.elemento('compra-lista-busca').innerHTML, htmlAtual);
  assert.match(htmlAtual, /fornecedor atual/);
});

test('compras não mostra busca antiga durante intervalo de digitação', async () => {
  const n = navegador();
  let concluir;
  n.responder(() => new Promise(resolve => { concluir = resolve; }));
  n.entrada('compra-busca', 'PROD-0001');
  const anterior = n.executar('setCompraFornFiltro(1)');
  n.entrada('compra-busca', 'PROD-1200');
  n.executar('filtrarCompraBuscaAoDigitar()');
  concluir(resposta(n.produtos));
  await anterior;
  assert.equal(n.elemento('compra-lista-busca').escritas, 0);
  n.tempo.avancar(150);
  await Promise.resolve();
  assert.match(n.elemento('compra-lista-busca').innerHTML, /Produto 1200/);
  assert.equal(n.requisicoes.length, 1);
});

test('compras mantém produtos já adicionados fora do seletor e seleção fora da página', async () => {
  const n = navegador();
  n.executar('listaCompras=[{produto_id:1}];compraSelecionados={1200:true};');
  await n.executar('filtrarCompraBusca()');
  assert.match(n.elemento('compra-lista-busca').innerHTML, /Mostrando 50 de 1199/);
  assert.doesNotMatch(n.elemento('compra-lista-busca').innerHTML, /Produto 0001/);
  n.entrada('compra-busca', 'PROD-1200');
  await n.executar('filtrarCompraBusca()');
  assert.match(n.elemento('compra-lista-busca').innerHTML, /p-opt-selected/);
  assert.equal(n.executar('compraSelecionados[1200]'), true);
});

test('compras não substitui fornecedor atual por erro de uma requisição antiga', async () => {
  const n = navegador();
  let concluir;
  n.responder(() => new Promise(resolve => { concluir = resolve; }));
  const anterior = n.executar('setCompraFornFiltro(1)');
  await n.executar('setCompraFornFiltro(null)');
  const htmlAtual = n.elemento('compra-lista-busca').innerHTML;
  concluir(resposta({erro: 'Falha antiga'}, 500));
  await anterior;
  assert.equal(n.elemento('compra-lista-busca').innerHTML, htmlAtual);
});

test('compras exibe falha atual e permite tentar novamente sem cache rejeitado', async () => {
  const n = navegador();
  n.responder(async () => resposta({erro: 'Indisponível'}, 503));
  await n.executar('setCompraFornFiltro(1)');
  assert.match(n.elemento('compra-lista-busca').innerHTML, /Não foi possível carregar/);
  n.responder(async () => resposta(n.produtos));
  await n.executar('filtrarCompraBusca()');
  assert.equal(n.requisicoes.length, 2);
  assert.equal(n.opcoes('compra-lista-busca'), 50);
  assert.match(n.elemento('compra-lista-busca').innerHTML, /Mostrando 50 de 1200/);
});
