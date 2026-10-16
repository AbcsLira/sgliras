// Testa o catálogo e a digitação com os scripts reais e um relógio controlado.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function browser(){
  const elements=new Map(), timers=new Map(), requests=[];
  let nextTimer=0, handler=async()=>({ok:true,json:async()=>[]});
  function element(id){
    if(!elements.has(id)) elements.set(id,{
      value:'',checked:false,hidden:false,disabled:false,innerHTML:'',textContent:'',attrs:{},events:{},
      setAttribute(name,value){this.attrs[name]=value;},
      addEventListener(name,fn){this.events[name]=fn;},
    });
    return elements.get(id);
  }
  const context=vm.createContext({
    AbortController,
    produtos:[],categorias:[],filtroCatId:null,me:{permissoes:['produtos','fichas']},CAT_ICONS:{},
    document:{getElementById:element},
    setTimeout(fn){const id=++nextTimer;timers.set(id,fn);return id;},
    clearTimeout(id){timers.delete(id);},
    fetch:async url=>{requests.push(url);return handler(url);},
  });
  for(const file of ['utilitarios.js','produtos.js']){
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/modules',file),'utf8'),context,{filename:file});
  }
  return {context,element,requests,timers,
    run:src=>vm.runInContext(src,context),
    respond(fn){handler=fn;},
    type(value){const input=element('busca-produto');input.value=value;input.events.input({target:input});},
    flush(){for(const [id,fn] of [...timers]){timers.delete(id);fn();}},
  };
}
function products(total=123){
  return Array.from({length:total},(_,i)=>({id:i+1,nome:`Produto ${String(i+1).padStart(4,'0')}`,
    codigo:`P${i+1}`,codigo_barras:`BAR${i+1}`,quantidade:10,preco_custo:1,estoque_min:2,ativo:1,categoria_id:1}));
}
function setProducts(b,items=products()){
  b.run(`produtos=${JSON.stringify(items)};categorias=[{id:1,nome:'Alimentos'}];`);
}
function rows(b){return (b.element('t-produtos').innerHTML.match(/<tr /g)||[]).length;}

test('paginação limita DOM e alcança o catálogo completo sem remover dados',()=>{
  const b=browser();setProducts(b);b.run('renderProdutos()');
  assert.equal(rows(b),50);
  assert.match(b.element('produtos-total').textContent,/1–50 de 123/);
  assert.equal(b.element('produtos-anterior').disabled,true);
  b.run('mudarPaginaProdutos(1)');assert.equal(rows(b),50);
  b.run('mudarPaginaProdutos(1)');assert.equal(rows(b),23);
  assert.match(b.element('t-produtos').innerHTML,/Produto 0123/);
  assert.equal(b.element('produtos-proxima').disabled,true);
  assert.equal(b.run('produtos.length'),123);
  assert.equal(b.requests.length,0);
});

test('busca por barras encontra produto na última página e agrupa teclas',()=>{
  const b=browser();setProducts(b,products(1000));b.run('renderProdutos()');
  b.type('B');b.type('BAR');b.type('BAR1000');
  assert.equal(b.timers.size,1);
  assert.equal(rows(b),50);
  b.flush();
  assert.equal(rows(b),1);
  assert.match(b.element('t-produtos').innerHTML,/Produto 1000/);
  assert.equal(b.requests.length,0);
});

test('filtros, página e busca persistem em atualização e página fica válida após exclusão',()=>{
  const b=browser();setProducts(b);b.run('renderProdutos();mudarPaginaProdutos(1)');
  b.run('renderProdutos()');assert.match(b.element('produtos-total').textContent,/página 2 de 3/);
  b.type('Produto 0123');b.flush();b.run('renderProdutos()');
  assert.equal(rows(b),1);assert.match(b.element('t-produtos').innerHTML,/Produto 0123/);
  b.type('');b.flush();b.run('mudarPaginaProdutos(2);produtos=produtos.slice(0,10);renderProdutos()');
  assert.equal(rows(b),10);assert.equal(b.element('produtos-proxima').disabled,true);
});

test('mudar categoria imediatamente cancela digitação pendente; tamanho da página é respeitado',()=>{
  const b=browser();setProducts(b);b.type('Produto');
  b.run('filtroCatId=2;renderProdutos()');
  assert.equal(b.timers.size,0);assert.equal(rows(b),0);
  b.run('filtroCatId=1;alterarTamanhoPaginaProdutos(25)');assert.equal(rows(b),25);
  b.run('alterarTamanhoPaginaProdutos(100)');assert.equal(rows(b),100);
  b.run('alterarTamanhoPaginaProdutos(999999)');assert.equal(rows(b),100);
});

test('requisições simultâneas compartilham a leitura e concluem com os mesmos dados',async()=>{
  const b=browser();setProducts(b);b.run('renderProdutos()');
  const pending=[];
  b.respond(url=>new Promise(resolve=>{pending.push({url,resolve});}));
  const first=b.run('carregarProdutos()');
  const second=b.run('carregarProdutos()');
  assert.equal(b.requests.length,2);
  assert.equal(b.element('t-produtos').attrs['aria-busy'],'true');
  pending.forEach(({url,resolve})=>resolve({ok:true,json:async()=>url.endsWith('/produtos')
    ?products(2):[{id:1,nome:'Alimentos'}]}));
  assert.deepEqual(await Promise.all([first,second]),[true,true]);
  assert.equal(rows(b),2);
  assert.equal(b.element('t-produtos').attrs['aria-busy'],'false');
});

test('falha HTTP mantém catálogo anterior, encerra busy e permite retry',async()=>{
  const b=browser();setProducts(b);b.run('renderProdutos()');
  const original=b.element('t-produtos').innerHTML;
  b.respond(async()=>({ok:false,json:async()=>({})}));
  assert.equal(await b.run('carregarProdutos()'),false);
  assert.equal(b.element('t-produtos').innerHTML,original);
  assert.equal(b.element('t-produtos').attrs['aria-busy'],'false');
  assert.match(b.element('produtos-status').innerHTML,/Tentar novamente/);
  b.respond(async url=>({ok:true,json:async()=>url.endsWith('/produtos')?products(1):[{id:1,nome:'Alimentos'}]}));
  assert.equal(await b.run('carregarProdutos()'),true);
  assert.equal(rows(b),1);assert.equal(b.element('produtos-status').hidden,true);
});

test('refresh após gravação descarta snapshot antigo mesmo se abort não interromper a rede',async()=>{
  const b=browser();setProducts(b);
  const pending=[];
  b.respond(url=>new Promise(resolve=>pending.push({url,resolve})));
  const old=b.run('carregarProdutos()');
  const refresh=b.run('carregarProdutos({atualizar:true})');
  assert.equal(pending.length,4);
  for(const {url,resolve} of pending.slice(2)) resolve({ok:true,json:async()=>url.endsWith('/produtos')?products(2):[]});
  assert.equal(await refresh,true);
  for(const {url,resolve} of pending.slice(0,2)) resolve({ok:true,json:async()=>url.endsWith('/produtos')?products(1):[]});
  assert.equal(await old,false);
  assert.equal(b.run('produtos.length'),2);
  assert.equal(rows(b),2);
  assert.equal(b.element('t-produtos').attrs['aria-busy'],'false');
});

test('debounce pode executar imediatamente ou cancelar sem executar',()=>{
  const b=browser();b.run('globalThis.chamadas=[];globalThis.busca=adiarBusca(valor=>chamadas.push(valor));busca(1);busca(2);busca.executar();');
  assert.equal(b.run('chamadas.join()'),'2');assert.equal(b.timers.size,0);
  b.run('busca(3);busca.cancelar()');b.flush();assert.equal(b.run('chamadas.join()'),'2');
});
