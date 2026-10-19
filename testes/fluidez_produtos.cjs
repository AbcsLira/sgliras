// Testa o catálogo e a digitação com os scripts reais e um relógio controlado.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function browser(){
  const elements=new Map(), timers=new Map(), requests=[], requestDetails=[], messages=[], confirmations=[];
  let nextTimer=0, handler=async()=>({ok:true,json:async()=>[]}), confirmHandler=()=>true;
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
    confirm:message=>{confirmations.push(message);return confirmHandler(message,confirmations.length);},
    toast:(message,color)=>messages.push({message,color}),
    fetch:async(url,options={})=>{
      requests.push(url);requestDetails.push({url,options});return handler(url,options);
    },
  });
  for(const file of ['utilitarios.js','produtos.js']){
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/modules',file),'utf8'),context,{filename:file});
  }
  return {context,element,requests,requestDetails,messages,confirmations,timers,
    run:src=>vm.runInContext(src,context),
    respond(fn){handler=fn;},
    confirm(fn){confirmHandler=fn;},
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

test('catálogo busca todas as palavras em qualquer ordem, sem acentos, e mantém códigos',()=>{
  const b=browser();
  setProducts(b,[
    {...products(1)[0],nome:'Molho de Pizza',codigo:'MP-01',codigo_barras:'007890123'},
    {...products(1)[0],id:2,nome:'Açaí Especial',codigo:'AC-02',codigo_barras:null},
    {...products(1)[0],id:3,nome:'Molho de Tomate',codigo:'MT-03',codigo_barras:'789000003'},
  ]);
  b.run('renderProdutos()');
  for(const busca of ['molho pizza','PIZZA molho','  mol\t pizz  ','MP-01','007890123']){
    b.type(busca);b.flush();
    assert.equal(rows(b),1,busca);
    assert.match(b.element('t-produtos').innerHTML,/Molho de Pizza/);
  }
  b.type('especial acai');b.flush();assert.equal(rows(b),1);
  assert.match(b.element('t-produtos').innerHTML,/Açaí Especial/);
  b.type('pizza tomate');b.flush();assert.equal(rows(b),0);
  b.type('   ');b.flush();assert.equal(rows(b),3);
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

test('exclusão recusada mostra motivo do servidor e mantém catálogo sem recarregar',async()=>{
  for(const status of [400,403,404,409,500]){
    const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
    b.confirm((message,number)=>number===1);
    const original=b.element('t-produtos').innerHTML;
    const reason='Produto com histórico. Desative o produto em vez de excluí-lo.';
    b.respond(async()=>({ok:false,status,json:async()=>({erro:reason})}));
    await b.run('deletarProduto(1,"Produto 0001")');
    assert.equal(b.requests.length,1,status);
    assert.equal(b.requestDetails[0].options.method,'DELETE');
    assert.equal(b.confirmations.length,status===400?2:1);
    assert.equal(b.element('t-produtos').innerHTML,original);
    assert.equal(b.run('produtos.length'),2);
    assert.deepEqual(b.messages,[{message:reason,color:'var(--danger)'}]);
  }
});

test('erro ou resposta inválida na exclusão não anuncia sucesso',async()=>{
  for(const response of [
    {ok:true,json:async()=>({erro:'Exclusão não autorizada'})},
    {ok:true,json:async()=>({ok:false})},
    {ok:true,json:async()=>null},
    {ok:true,json:async()=>{throw new SyntaxError('JSON inválido');}},
    {ok:false,status:502,json:async()=>{throw new SyntaxError('HTML do proxy');}},
  ]){
    const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
    const original=b.element('t-produtos').innerHTML;
    b.respond(async()=>response);
    await b.run('deletarProduto(1,"Produto 0001")');
    assert.equal(b.requests.length,1);
    assert.equal(b.messages.length,1);
    assert.equal(b.messages[0].color,'var(--danger)');
    assert.doesNotMatch(b.messages[0].message,/Removido/);
    assert.equal(b.element('t-produtos').innerHTML,original);
  }
});

test('falha de rede na exclusão informa incerteza e mantém dados atuais',async()=>{
  const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
  const original=b.element('t-produtos').innerHTML;
  b.respond(async()=>{throw new TypeError('Failed to fetch');});
  await b.run('deletarProduto(1,"Produto 0001")');
  assert.equal(b.requests.length,1);
  assert.equal(b.run('produtos.length'),2);
  assert.equal(b.element('t-produtos').innerHTML,original);
  assert.equal(b.messages.length,1);
  assert.match(b.messages[0].message,/Não foi possível confirmar a exclusão/);
  assert.match(b.messages[0].message,/atualize a lista/);
});

test('exclusão aceita anuncia sucesso e força atualização sem perder busca por palavras',async()=>{
  const b=browser();
  const items=[
    {...products(1)[0],nome:'Molho de Pizza'},
    {...products(1)[0],id:2,codigo:'P2',nome:'Molho de Pizza Especial'},
  ];
  setProducts(b,items);b.type('pizza molho');b.flush();
  let concludeDelete;
  b.respond(async(url,options)=>{
    if(options.method==='DELETE') return new Promise(resolve=>{concludeDelete=resolve;});
    return {ok:true,json:async()=>url==='/api/produtos'?items.slice(1):[{id:1,nome:'Alimentos'}]};
  });
  const pending=b.run('deletarProduto(1,"Molho de Pizza")');
  assert.equal(b.messages.length,0);
  assert.equal(rows(b),2);
  concludeDelete({ok:true,json:async()=>({ok:true})});
  await pending;
  assert.deepEqual(b.requests,['/api/produtos/1','/api/produtos','/api/categorias']);
  assert.deepEqual(b.messages,[{message:'Removido',color:'var(--danger)'}]);
  assert.equal(b.element('busca-produto').value,'pizza molho');
  assert.equal(rows(b),1);
  assert.match(b.element('t-produtos').innerHTML,/Molho de Pizza Especial/);
  assert.equal(b.run('produtos.length'),1);
});

test('exclusão aceita renova snapshot mesmo com leitura anterior em andamento',async()=>{
  const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
  const previous=[];
  b.respond(url=>new Promise(resolve=>previous.push({url,resolve})));
  const old=b.run('carregarProdutos()');
  b.respond(async(url,options)=>({ok:true,json:async()=>options.method==='DELETE'?{ok:true}
    :url==='/api/produtos'?products(1):[{id:1,nome:'Alimentos'}]}));
  await b.run('deletarProduto(2,"Produto 0002")');
  assert.equal(rows(b),1);
  for(const {url,resolve} of previous){
    resolve({ok:true,json:async()=>url==='/api/produtos'?products(2):[]});
  }
  assert.equal(await old,false);
  assert.equal(rows(b),1);
  assert.equal(b.run('produtos.length'),1);
});

test('cancelar exclusão não envia DELETE nem oferece desativação',async()=>{
  const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
  b.confirm(()=>false);
  await b.run('deletarProduto(1,"Produto 0001")');
  assert.equal(b.requests.length,0);
  assert.equal(b.confirmations.length,1);
  assert.equal(b.messages.length,0);
  assert.equal(rows(b),2);
});

test('desativação após exclusão bloqueada exige confirmação e atualiza produto existente',async()=>{
  const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
  const reason='Produto com histórico. Desative o produto em vez de excluí-lo.';
  b.respond(async(url,options)=>{
    if(options.method==='DELETE') return {ok:false,status:400,json:async()=>({erro:reason})};
    if(options.method==='PUT') return {ok:true,json:async()=>({ok:true,ativo:false})};
    return {ok:true,json:async()=>url==='/api/produtos'
      ?products(2).map(p=>({...p,ativo:p.id===1?0:1})):[{id:1,nome:'Alimentos'}]};
  });
  await b.run('deletarProduto(1,"Produto 0001")');
  assert.equal(b.confirmations.length,2);
  assert.match(b.confirmations[1],/Deseja desativar "Produto 0001" agora/);
  assert.match(b.confirmations[1],/Produto com histórico/);
  assert.deepEqual(b.requests,['/api/produtos/1','/api/produtos/1/ativo','/api/produtos','/api/categorias']);
  assert.equal(b.requestDetails[1].options.method,'PUT');
  assert.equal(b.requestDetails[1].options.headers['Content-Type'],'application/json');
  assert.deepEqual(JSON.parse(b.requestDetails[1].options.body),{ativo:false});
  assert.deepEqual(b.messages,[{message:'"Produto 0001" desativado.',color:undefined}]);
  assert.equal(rows(b),1);
  assert.equal(b.run('produtos.length'),2);
  assert.equal(b.run('produtos.find(p=>p.id===1).ativo'),0);
});

test('desativação recusada ou sem confirmação válida do servidor não anuncia sucesso',async()=>{
  for(const response of [
    {ok:false,status:403,json:async()=>({erro:'Sem permissão para desativar'})},
    {ok:true,json:async()=>({erro:'Operação recusada'})},
    {ok:true,json:async()=>({ok:true,ativo:true})},
    {ok:true,json:async()=>null},
    {ok:true,json:async()=>{throw new SyntaxError('JSON inválido');}},
    {ok:false,status:502,json:async()=>{throw new SyntaxError('HTML do proxy');}},
  ]){
    const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
    const original=b.element('t-produtos').innerHTML;
    b.respond(async(url,options)=>options.method==='DELETE'
      ?{ok:false,status:400,json:async()=>({erro:'Produto com histórico'})}:response);
    await b.run('deletarProduto(1,"Produto 0001")');
    assert.equal(b.requests.length,2);
    assert.equal(b.messages.length,1);
    assert.equal(b.messages[0].color,'var(--danger)');
    assert.doesNotMatch(b.messages[0].message,/Removido|"Produto 0001" desativado/);
    assert.equal(b.element('t-produtos').innerHTML,original);
    assert.equal(b.run('produtos[0].ativo'),1);
  }
});

test('falha de rede na desativação informa incerteza sem alterar catálogo',async()=>{
  const b=browser();setProducts(b,products(2));b.run('renderProdutos()');
  const original=b.element('t-produtos').innerHTML;
  b.respond(async(url,options)=>{
    if(options.method==='DELETE') return {ok:false,status:400,json:async()=>({erro:'Produto com histórico'})};
    throw new TypeError('Failed to fetch');
  });
  await b.run('deletarProduto(1,"Produto 0001")');
  assert.equal(b.requests.length,2);
  assert.equal(b.messages.length,1);
  assert.match(b.messages[0].message,/Não foi possível confirmar a desativação/);
  assert.match(b.messages[0].message,/atualize a lista/);
  assert.equal(b.element('t-produtos').innerHTML,original);
});
