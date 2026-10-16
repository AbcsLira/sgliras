// Executa o JavaScript da aplicação sem navegador ou dependências externas.
// Uso: node testes/estabilidade_interface.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

function response(data = {ok: true}, status = 200) {
  return {ok: status >= 200 && status < 300, status, json: async () => data};
}

function browser(storage = new Map(), userId = 7) {
  const elements = new Map();
  const requests = [], messages = [], closed = [];
  let handler = async request => response(request.method === 'GET' ? [] : {ok: true, novo_estoque: 8, ajustados: 1});
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: '', disabled: false, innerHTML: '', textContent: '',
      classList: {add() {}, remove() {}}, focus() {},
      controls: [{disabled: false}, {disabled: true}],
      querySelectorAll() { return this.controls; },
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    crypto: webcrypto, produtos: [], categorias: [], movProdId: 1, me: {id: userId},
    sessionStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    document: {getElementById: element, querySelectorAll: () => []},
    toast: message => messages.push(message),
    fecharModal: id => closed.push(id),
    confirm: () => false,
    fetch: async (url, options = {}) => {
      const request = {url, method: options.method || 'GET', body: options.body && JSON.parse(options.body)};
      requests.push(request);
      return handler(request);
    },
  });
  for (const file of ['movimentacoes.js', 'entrada_lote.js', 'financeiro_contas.js', 'inventario.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/modulos', file), 'utf8'), context, {filename: file});
  }
  vm.runInContext('carregarMovimentacoes=async()=>{};finCarregarContasPagar=async()=>{};invCarregarEstado=async()=>{};', context);
  return {
    context, requests, messages, closed, element, storage,
    run: source => vm.runInContext(source, context),
    input(id, value) { element(id).value = value; },
    respond(fn) { handler = fn; },
    posts() { return requests.filter(request => request.method === 'POST'); },
  };
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const stockItems = [
  {produto_id: 1, nome: 'A', quantidade: 2, qtdEstoque: 20},
  {produto_id: 2, nome: 'B', quantidade: 3, qtdEstoque: 30, modoEmbalagem: true, unid_por_fardo: 4},
];

function configureStock(b, entry) {
  b.run(`${entry ? 'entradaLoteItens' : 'loteItens'}=${JSON.stringify(stockItems)};`);
}

function configureFinance(b) {
  for (const [id, value] of Object.entries({
    'fin-pagar-desc': 'Compra', 'fin-pagar-valor': '100',
    'fin-pagar-venc': '2026-10-01', 'fin-pagar-parcelas': '2',
    'fin-pagar-cat': 'Ingredientes', 'fin-pagar-forn': '', 'fin-pagar-obs': '',
    'fin-parc-val-0': '50', 'fin-parc-venc-0': '2026-10-01',
    'fin-parc-val-1': '50', 'fin-parc-venc-1': '2026-11-01',
  })) b.input(id, value);
}

const forms = [
  {name: 'entrada em lote', setup: b => configureStock(b, true), invoke: 'confirmarEntradaLote()',
    modal: 'modal-entrada-lote', reopen: 'abrirModalEntradaLote()', edit: b => b.run('entradaLoteItens[0].quantidade=5;')},
  {name: 'saída em lote', setup: b => configureStock(b, false), invoke: 'confirmarSaidaLote()',
    modal: 'modal-lote', reopen: 'abrirModalLote()', edit: b => b.run('loteItens[0].quantidade=5;')},
  {name: 'parcelamento', setup: configureFinance, invoke: 'finSalvarContaPagar()',
    modal: 'modal-fin-pagar', reopen: 'finAbrirModalPagar()', edit: b => b.input('fin-pagar-desc', 'Outra compra')},
  {name: 'movimentação individual', setup: b => {
    b.input('mov-qtd', '2'); b.input('mov-tipo', 'saida');
  }, invoke: 'salvarMov()', modal: 'modal-mov', reopen: 'abrirModalMov()', edit: b => b.input('mov-qtd', '3')},
];

for (const form of forms) {
  test(`${form.name}: bloqueia cliques concorrentes e restaura controles`, async () => {
    const b = browser();
    form.setup(b);
    let complete;
    b.respond(request => request.method === 'POST'
      ? new Promise(resolve => { complete = resolve; }) : response([]));
    const first = b.run(form.invoke);
    await b.run(form.invoke);
    assert.equal(b.posts().length, 1);
    assert.deepEqual(b.element(form.modal).controls.map(control => control.disabled), [true, true]);
    complete(response({ok: true, novo_estoque: 8}));
    await first;
    assert.deepEqual(b.element(form.modal).controls.map(control => control.disabled), [false, true]);
    assert.deepEqual(b.closed, [form.modal]);
  });

  test(`${form.name}: tentativa incerta conserva ID e conteúdo mesmo após edição`, async () => {
    const b = browser();
    form.setup(b);
    b.respond(async () => { throw new Error('Resposta perdida'); });
    await b.run(form.invoke);
    await b.run(form.invoke);
    assert.equal(b.posts().length, 2);
    const [first, retry] = b.posts().map(request => request.body);
    assert.match(first.operacao_id, uuid);
    assert.deepEqual(first, retry);
    assert.equal(b.closed.length, 0);
    assert.match(b.messages.at(-1), /conexão/i);
    form.edit(b);
    await b.run(form.invoke);
    assert.deepEqual(b.posts()[2].body, first);
  });

  test(`${form.name}: resposta perdida, edição e reabertura aplicam uma única vez`, async () => {
    const b = browser();
    form.setup(b);
    const applied = new Map();
    let lostResponse = true;
    const server = async request => {
      if (request.method !== 'POST') return response([]);
      const {operacao_id: id} = request.body;
      if (!applied.has(id)) applied.set(id, request.body);
      else assert.deepEqual(request.body, applied.get(id));
      if (lostResponse) { lostResponse = false; throw new Error('Servidor gravou, resposta perdida'); }
      return response({ok: true, novo_estoque: 8});
    };
    b.respond(server);
    await b.run(form.invoke);
    const original = b.posts()[0].body;
    form.edit(b);
    await b.run(form.reopen);
    await b.run(form.invoke);
    assert.equal(applied.size, 1);
    assert.deepEqual(b.posts()[1].body, original);
    assert.match(b.messages.at(-1), /anterior confirmada.*alterações atuais não foram enviadas/i);
    assert.equal(b.storage.size, 0);
  });

  test(`${form.name}: refresh recupera tentativa antes de validar campos vazios`, async () => {
    const before = browser();
    form.setup(before);
    before.respond(async () => { throw new Error('Resposta perdida'); });
    await before.run(form.invoke);
    const original = before.posts()[0].body;
    const refreshed = browser(before.storage);
    await refreshed.run(form.reopen);
    await refreshed.run(form.invoke);
    assert.deepEqual(refreshed.posts()[0].body, original);
    assert.deepEqual(refreshed.closed, [form.modal]);
    assert.equal(before.storage.size, 0);
  });

  test(`${form.name}: erro 400 permite corrigir com uma nova chave`, async () => {
    const b = browser();
    form.setup(b);
    b.respond(async () => response({erro: 'Dados inválidos'}, 400));
    await b.run(form.invoke);
    assert.equal(b.storage.size, 0);
    const original = b.posts()[0].body;
    form.edit(b);
    b.respond(async request => response(request.method === 'GET' ? [] : {ok: true, novo_estoque: 8}));
    await b.run(form.invoke);
    assert.notEqual(b.posts()[1].body.operacao_id, original.operacao_id);
    assert.notDeepEqual(b.posts()[1].body, original);
  });
}

for (const entry of [true, false]) {
  test(`${entry ? 'entrada' : 'saída'}: envia todos os itens numa única transação`, async () => {
    const b = browser();
    configureStock(b, entry);
    await b.run(entry ? 'confirmarEntradaLote()' : 'confirmarSaidaLote()');
    assert.equal(b.posts().length, 1);
    const request = b.posts()[0];
    assert.equal(request.url, '/api/movimentacoes/lote');
    assert.deepEqual(request.body.itens.map(item => item.quantidade), [2, 12]);
    assert.ok(request.body.itens.every(item => item.tipo === (entry ? 'entrada' : 'saida')));
  });
}

test('erro HTTP, conflito e resposta inválida mantêm o modal aberto e a chave', async () => {
  const b = browser();
  configureStock(b, true);
  const failures = [response({erro: 'Estoque indisponível'}, 400),
    response({erro: 'Operação em conflito'}, 409), response({ok: false}),
    {ok: true, json: async () => { throw new SyntaxError('invalid JSON'); }}];
  b.respond(async () => failures.shift());
  for (let i = 0; i < 4; i++) await b.run('confirmarEntradaLote()');
  assert.equal(b.closed.length, 0);
  assert.ok(b.messages.length >= 4);
  assert.equal(new Set(b.posts().map(request => request.body.operacao_id)).size, 1);
});

test('parcelamento inválido não grava nem a primeira parcela', async () => {
  for (const invalid of ['', '0', '-10', 'Infinity', 'NaN']) {
    const b = browser();
    configureFinance(b);
    b.input('fin-parc-val-1', invalid);
    await b.run('finSalvarContaPagar()');
    assert.equal(b.requests.length, 0, `valor inválido: ${invalid}`);
  }
  const b = browser();
  configureFinance(b);
  b.input('fin-parc-venc-1', '');
  await b.run('finSalvarContaPagar()');
  assert.equal(b.requests.length, 0);
  assert.equal(b.closed.length, 0);
});

test('parcelamento envia todas as parcelas no endpoint transacional', async () => {
  const b = browser();
  configureFinance(b);
  await b.run('finSalvarContaPagar()');
  assert.equal(b.posts().length, 1);
  const request = b.posts()[0];
  assert.equal(request.url, '/api/fin/contas-pagar/lote');
  assert.deepEqual(request.body.itens.map(item => [item.descricao, item.valor, item.vencimento]), [
    ['Compra 1/2', 50, '2026-10-01'], ['Compra 2/2', 50, '2026-11-01'],
  ]);
});

test('inventário não finaliza se salvar contagens falhar', async () => {
  for (const fail of [async () => response({erro: 'Falha ao salvar'}, 400),
    async () => response({ok: false}), async () => { throw new Error('offline'); }]) {
    const b = browser();
    b.run('invAtual={id:1};invItens=[{produto_id:1,quantidade_contada:2}];');
    b.respond(fail);
    await b.run('invConfirmarFinalizar()');
    await b.run('invConfirmarFinalizar()');
    assert.deepEqual(b.requests.map(request => request.method), ['PUT', 'PUT']);
    assert.equal(b.closed.length, 0);
    assert.deepEqual(b.element('modal-inv-finalizar').controls.map(control => control.disabled), [false, true]);
  }
});

test('inventário aguarda salvar e bloqueia dupla finalização', async () => {
  const b = browser();
  b.run('invAtual={id:1};invItens=[{produto_id:1,quantidade_contada:2}];');
  let complete;
  b.respond(request => request.method === 'PUT'
    ? new Promise(resolve => { complete = resolve; })
    : response(request.method === 'GET' ? [] : {ok: true, ajustados: 1}));
  const first = b.run('invConfirmarFinalizar()');
  await b.run('invConfirmarFinalizar()');
  assert.deepEqual(b.requests.map(request => request.method), ['PUT']);
  complete(response({ok: true}));
  await first;
  assert.deepEqual(b.requests.map(request => request.method), ['PUT', 'POST', 'GET']);
  assert.equal(b.posts()[0].url, '/api/inventarios/1/finalizar');
  assert.deepEqual(b.closed, ['modal-inv-finalizar']);
});

test('ID seguro funciona em HTTP quando randomUUID não está disponível', async () => {
  const b = browser();
  b.context.crypto = {getRandomValues: webcrypto.getRandomValues.bind(webcrypto)};
  configureStock(b, true);
  await b.run('confirmarEntradaLote()');
  assert.match(b.posts()[0].body.operacao_id, uuid);
});

test('tentativas persistidas são separadas por usuário e por formulário', async () => {
  const b = browser();
  configureStock(b, true);
  b.respond(async () => { throw new Error('offline'); });
  await b.run('confirmarEntradaLote()');
  const anotherUser = browser(b.storage, 8);
  await anotherUser.run('confirmarEntradaLote()');
  assert.equal(anotherUser.posts().length, 0);
  const sameUser = browser(b.storage);
  await sameUser.run('confirmarSaidaLote()');
  assert.equal(sameUser.posts().length, 0);
  assert.equal(b.storage.size, 1);
});

test('erro 500 ou JSON inválido conservam a tentativa original após edição', async () => {
  for (const failure of [response({erro: 'Falha interna'}, 500),
    {ok: true, status: 201, json: async () => { throw new SyntaxError('Resposta incompleta'); }}]) {
    const b = browser();
    configureStock(b, true);
    b.respond(async () => failure);
    await b.run('confirmarEntradaLote()');
    const original = b.posts()[0].body;
    b.run('entradaLoteItens=[];');
    b.respond(async request => response(request.method === 'GET' ? [] : {ok: true}));
    await b.run('confirmarEntradaLote()');
    assert.deepEqual(b.posts()[1].body, original);
    assert.equal(b.storage.size, 0);
  }
});

test('armazenamento bloqueado mantém reconciliação em memória', async () => {
  const b = browser();
  configureStock(b, true);
  b.context.sessionStorage = {
    getItem() { throw new Error('bloqueado'); },
    setItem() { throw new Error('bloqueado'); },
    removeItem() { throw new Error('bloqueado'); },
  };
  b.respond(async () => { throw new Error('offline'); });
  await b.run('confirmarEntradaLote()');
  b.run('entradaLoteItens=[];');
  await b.run('confirmarEntradaLote()');
  assert.deepEqual(b.posts()[0].body, b.posts()[1].body);
});

test('erro 409 de integridade libera correção após rollback confirmado', async () => {
  const b = browser();
  configureStock(b, true);
  b.respond(async () => response({erro: 'Restrição do banco', codigo: 'integridade'}, 409));
  await b.run('confirmarEntradaLote()');
  const original = b.posts()[0].body;
  assert.equal(b.storage.size, 0);
  b.run('entradaLoteItens[0].quantidade=5;');
  b.respond(async request => response(request.method === 'GET' ? [] : {ok: true}));
  await b.run('confirmarEntradaLote()');
  assert.notEqual(b.posts()[1].body.operacao_id, original.operacao_id);
  assert.equal(b.posts()[1].body.itens[0].quantidade, 5);
});
