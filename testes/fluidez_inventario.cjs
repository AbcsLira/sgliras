// Uso: node testes/fluidez_inventario.cjs. Apenas módulos nativos do Node.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/js/modules/inventario.js'), 'utf8');
const decode = value => value.replace(/&quot;/g, '"').replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const attribute = (html, name) => decode(html.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] || '');
const response = (data = {ok: true}, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => data,
});

function browser() {
  const elements = new Map(), requests = [], messages = [], closed = [];
  let context;
  let handler = async () => response();
  const document = {activeElement: null, getElementById: id => elements.get(id) || null};

  function element(id, html = '') {
    const classes = new Set();
    const result = {
      id, value: '', style: {}, scrollTop: 0, writes: 0, attributes: {},
      selectionStart: null, selectionEnd: null, validity: {badInput: false},
      classList: {
        add: value => classes.add(value), remove: value => classes.delete(value),
        contains: value => classes.has(value),
      },
      focus() { document.activeElement = this; },
      setCustomValidity(message) { this.validationMessage = message; },
      setAttribute(name, value) { this.attributes[name] = value; },
      input(value, badInput = false) {
        this.value = value;
        this.validity.badInput = badInput;
        context.__editedInput = this;
        vm.runInContext(`(function(){${this.oninput}}).call(__editedInput)`, context);
      },
    };
    let innerHTML = html, textContent = '';
    Object.defineProperty(result, 'textContent', {
      get: () => textContent, set: value => { textContent = String(value); },
    });
    Object.defineProperty(result, 'innerHTML', {
      get: () => innerHTML,
      set: value => {
        innerHTML = value;
        result.writes++;
        if (id === 't-inventario') parseRows(result, value);
      },
    });
    elements.set(id, result);
    return result;
  }

  function parseRows(table, html) {
    // Substituir tbody remove os inputs antigos e perde foco/posição, como no DOM.
    for (const [id, node] of elements) {
      if (!/^inv-(linha|contagem|diferenca|observacao)-\d+$/.test(id)) continue;
      if (document.activeElement === node) document.activeElement = null;
      elements.delete(id);
    }
    table.scrollTop = 0;
    table.rows = [];
    for (const match of html.matchAll(/<tr id="inv-linha-(\d+)"[^>]*>([\s\S]*?)<\/tr>/g)) {
      const idx = match[1], row = element(`inv-linha-${idx}`);
      row.controls = [];
      for (const [position, input] of [...match[2].matchAll(/<input\b[^>]*>/g)].entries()) {
        const markup = input[0];
        const id = position === 0 ? `inv-contagem-${idx}` : `inv-observacao-${idx}`;
        const field = element(id);
        field.value = attribute(markup, 'value');
        field.oninput = attribute(markup, 'oninput');
        field.onchange = attribute(markup, 'onchange');
        field.attributes['aria-invalid'] = attribute(markup, 'aria-invalid');
        row.controls.push(field);
      }
      const diff = match[2].match(/<td id="inv-diferenca-\d+">([\s\S]*?)<\/td>/)?.[1] || '';
      element(`inv-diferenca-${idx}`, diff);
      table.rows.push(row);
    }
  }

  for (const id of ['t-inventario', 'inv-cnt-contados', 'inv-cnt-divergentes',
    'inv-cnt-pendentes', 'inv-cat-chips', 'inv-finalizar-resumo', 'modal-inv-finalizar']) element(id);
  element('modal-inv-finalizar').classList.add('hidden');
  const controls = [{disabled: false}, {disabled: true}];
  context = vm.createContext({
    document, categorias: [], produtos: [], CAT_ICONS: {},
    fmtQtdComoFardo: quantity => String(quantity),
    toast: message => messages.push(message),
    fecharModal: id => closed.push(id), confirm: () => true,
    bloquearControlesModal: () => {
      const before = controls.map(control => control.disabled);
      controls.forEach(control => { control.disabled = true; });
      return () => controls.forEach((control, idx) => { control.disabled = before[idx]; });
    },
    fetch: async (url, options = {}) => {
      const request = {url, method: options.method || 'GET',
        body: options.body ? JSON.parse(options.body) : undefined};
      requests.push(request);
      return handler(request);
    },
  });
  vm.runInContext(source, context, {filename: 'inventario.js'});
  vm.runInContext('invCarregarEstado=async()=>{};', context);
  const run = script => vm.runInContext(script, context);
  run(`invAtual={id:9};invItens=${JSON.stringify([
    {produto_id: 1, nome: 'A', codigo: 'A1', categoria: 'Frutas', unidade: 'un',
      quantidade_sistema: 10, quantidade_contada: 10, observacao: ''},
    {produto_id: 2, nome: 'B', codigo: 'B1', categoria: 'Outros', unidade: 'un',
      quantidade_sistema: 4, quantidade_contada: null, observacao: ''},
    {produto_id: 3, nome: 'C', codigo: 'C1', categoria: 'Frutas', unidade: 'un',
      quantidade_sistema: 7, quantidade_contada: 7, observacao: ''},
  ])};renderInventario();`);
  return {
    run, document, requests, messages, closed, controls,
    element: id => elements.get(id),
    count: idx => elements.get(`inv-contagem-${idx}`),
    observation: idx => elements.get(`inv-observacao-${idx}`),
    state: () => JSON.parse(run('JSON.stringify(invItens)')),
    counters: () => ['contados', 'divergentes', 'pendentes']
      .map(name => elements.get(`inv-cnt-${name}`).textContent),
    respond: fn => { handler = fn; },
  };
}

test('editar contagem preserva input, linha, foco, seleção, tabela e rolagem', () => {
  const b = browser();
  const table = b.element('t-inventario'), field = b.count(0), row = table.rows[0];
  const originalHTML = table.innerHTML, writes = table.writes;
  table.scrollTop = 213;
  field.focus();
  field.selectionStart = 1;
  field.selectionEnd = 3;
  field.input('6.5');
  assert.strictEqual(b.count(0), field);
  assert.strictEqual(table.rows[0], row);
  assert.strictEqual(b.document.activeElement, field);
  assert.deepEqual([field.selectionStart, field.selectionEnd], [1, 3]);
  assert.equal(table.innerHTML, originalHTML);
  assert.equal(table.writes, writes);
  assert.equal(table.scrollTop, 213);
  assert.equal(b.state()[0].quantidade_contada, 6.5);
  assert.match(b.element('inv-diferenca-0').innerHTML, /-3,5 un/);
  assert.deepEqual(b.counters(), ['2', '1', '1']);
  // Tab pode avançar normalmente: o próximo campo mantém a identidade.
  const next = b.observation(0);
  next.focus();
  next.input('Conferido antes de sair do campo');
  assert.strictEqual(b.document.activeElement, next);
  assert.equal(b.state()[0].observacao, 'Conferido antes de sair do campo');
  assert.equal(field.onchange, '');
  assert.equal(next.onchange, '');
  assert.equal(table.writes, writes);
});

test('apagar quantidade impede salvar até informar um valor; zero salva sem blur', async () => {
  const b = browser();
  b.count(0).input('');
  assert.equal(b.state()[0].quantidade_contada, null);
  assert.equal(b.state()[0]._contagemInvalida, true);
  assert.match(b.element('inv-diferenca-0').innerHTML, /Informe a quantidade ou 0/);
  assert.deepEqual(b.counters(), ['1', '0', '2']);
  assert.equal(await b.run('invSalvarParcial()'), false);
  await b.run('invConfirmarFinalizar()');
  assert.equal(b.requests.length, 0);
  assert.match(b.messages.at(-1), /Informe uma quantidade válida; use 0 para estoque zerado/);
  b.count(0).input('0');
  assert.equal(b.state()[0].quantidade_contada, 0);
  assert.equal(b.state()[0]._contagemInvalida, false);
  assert.equal(b.count(0).validationMessage, '');
  assert.match(b.element('inv-diferenca-0').innerHTML, /-10 un/);
  assert.deepEqual(b.counters(), ['2', '1', '1']);
  b.observation(0).focus();
  b.observation(0).input('Conferido "na mão"');
  assert.equal(await b.run('invSalvarParcial()'), true);
  assert.deepEqual(b.requests.map(request => [request.method, request.url]), [
    ['PUT', '/api/inventarios/9/itens'],
  ]);
  assert.deepEqual(b.requests[0].body.itens, [
    {produto_id: 1, quantidade_contada: 0, observacao: 'Conferido "na mão"'},
    {produto_id: 2, quantidade_contada: null, observacao: ''},
    {produto_id: 3, quantidade_contada: 7, observacao: ''},
  ]);
});

test('quantidade inválida aparece no campo e bloqueia salvar, resumo e finalização', async () => {
  for (const [value, badInput] of [['-1', false], ['NaN', false], ['Infinity', false],
    ['abc', false], ['', true]]) {
    const b = browser();
    const field = b.count(0);
    field.focus();
    field.input(value, badInput);
    assert.strictEqual(b.document.activeElement, field);
    assert.equal(b.state()[0].quantidade_contada, null);
    assert.equal(b.state()[0]._contagemInvalida, true);
    assert.equal(field.attributes['aria-invalid'], 'true');
    assert.match(field.validationMessage, /quantidade válida/);
    assert.match(b.element('inv-diferenca-0').innerHTML, value===''?/Informe a quantidade ou 0/:/Valor inválido/);
    assert.equal(await b.run('invSalvarParcial()'), false);
    await b.run('invFinalizar()');
    await b.run('invConfirmarFinalizar()');
    await b.run('confirmarContagemInventario()');
    assert.equal(b.requests.length, 0);
    assert.equal(b.closed.length, 0);
    assert.equal(b.element('modal-inv-finalizar').classList.contains('hidden'), true);
    assert.deepEqual(b.controls.map(control => control.disabled), [false, true]);
    assert.match(b.messages.at(-1), /Informe uma quantidade válida; use 0 para estoque zerado/);
    field.input('0');
    assert.equal(field.attributes['aria-invalid'], 'false');
    assert.equal(field.validationMessage, '');
    assert.equal(await b.run('invSalvarParcial()'), true);
    assert.equal(b.requests[0].body.itens[0].quantidade_contada, 0);
  }
});

test('filtro pode reconstruir tabela sem perder contagem vazia, zero ou observação', () => {
  const b = browser();
  b.count(0).input('0');
  b.observation(0).input('Lote "A" & conferido');
  b.count(1).input('');
  b.run("setInvCat('Outros')");
  assert.equal(b.element('t-inventario').rows.length, 1);
  assert.equal(b.count(1).value, '');
  assert.match(b.element('inv-diferenca-1').innerHTML, /Informe a quantidade ou 0/);
  b.count(1).input('9');
  assert.equal(b.state()[0].quantidade_contada, 0);
  assert.equal(b.state()[1].quantidade_contada, 9);
  b.run('setInvCat(null)');
  assert.equal(b.count(0).value, '0');
  assert.equal(b.count(1).value, '9');
  assert.equal(b.observation(0).value, 'Lote "A" & conferido');
  assert.deepEqual(b.counters(), ['3', '2', '0']);
  b.count(1).input('-2');
  b.run("setInvCat('Frutas');setInvCat(null)");
  assert.equal(b.count(1).attributes['aria-invalid'], 'true');
  assert.match(b.element('inv-diferenca-1').innerHTML, /Valor inválido/);
});

test('finalização mantém ordem PUT/POST e para quando salvar falha', async () => {
  for (const fail of [async () => response({erro: 'Falha ao salvar'}, 400),
    async () => response({ok: false}), async () => { throw new Error('offline'); }]) {
    const b = browser();
    b.count(0).input('5');
    b.respond(fail);
    await b.run('invConfirmarFinalizar()');
    assert.deepEqual(b.requests.map(request => request.method), ['PUT']);
    assert.equal(b.requests[0].body.itens[0].quantidade_contada, 5);
    assert.equal(b.closed.length, 0);
    assert.deepEqual(b.controls.map(control => control.disabled), [false, true]);
  }
  const b = browser();
  let resolveSave;
  b.respond(request => request.method === 'PUT'
    ? new Promise(resolve => { resolveSave = resolve; })
    : response(request.method === 'GET' ? [] : {ok: true, ajustados: 1}));
  const pending = b.run('invConfirmarFinalizar()');
  await b.run('invConfirmarFinalizar()');
  assert.deepEqual(b.requests.map(request => request.method), ['PUT']);
  resolveSave(response());
  await pending;
  assert.deepEqual(b.requests.map(request => request.method), ['PUT', 'POST', 'GET']);
  assert.equal(b.requests[1].url, '/api/inventarios/9/finalizar');
  assert.deepEqual(b.closed, ['modal-inv-finalizar']);
  assert.deepEqual(b.controls.map(control => control.disabled), [false, true]);
});
