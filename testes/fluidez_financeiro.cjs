// Regressão do carregamento financeiro sem navegador ou dependências externas.
// Uso: node testes/fluidez_financeiro.cjs
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const copiar=valor=>JSON.parse(JSON.stringify(valor));
const resposta=(dados,status=200)=>({ok:status>=200&&status<300,status,json:async()=>copiar(dados)});
const categorias=[{id:1,nome:'Ingredientes'},{id:2,nome:'Aluguel'},{id:3,nome:'Outros'}];
const fornecedores=[{id:1,nome:'Primeiro'},{id:2,nome:'Segundo'}];
const contas=[
  {id:2,descricao:'Pagamento atual',categoria:'Aluguel',fornecedor_id:2,valor:200,status:'pago',vencimento:'2026-09-01',pago_em:'2026-10-05'},
  {id:7,descricao:'Pagamento anterior',categoria:'Outros',fornecedor_id:null,valor:10,status:'pago',vencimento:'2026-09-30',pago_em:'2026-09-30'},
  {id:1,descricao:'Vencida',categoria:'Ingredientes',fornecedor_id:1,valor:100,status:'aberto',vencimento:'2026-10-01'},
  {id:6,descricao:'Outra vencida',categoria:'Aluguel',fornecedor_id:1,valor:40,status:'aberto',vencimento:'2026-10-14'},
  {id:4,descricao:'Vence hoje',categoria:'Outros',fornecedor_id:1,valor:20,status:'aberto',vencimento:'2026-10-15'},
  {id:3,descricao:'Pagamento adiantado',categoria:'Ingredientes',fornecedor_id:2,valor:50,status:'pago',vencimento:'2026-10-20',pago_em:'2026-09-30'},
  {id:5,descricao:'Próximo mês',categoria:'Ingredientes',fornecedor_id:1,valor:30,status:'aberto',vencimento:'2026-11-01'},
];
const receber=[
  {id:1,descricao:'A receber vencida',categoria:'Venda',valor:15,status:'aberto',vencimento:'2026-10-01'},
  {id:2,descricao:'A receber hoje',categoria:'Venda',valor:25,status:'aberto',vencimento:'2026-10-15'},
  {id:3,descricao:'Recebida atual',categoria:'Venda',valor:50,status:'recebido',vencimento:'2026-09-01',recebido_em:'2026-10-01'},
  {id:4,descricao:'Recebida anterior',categoria:'Venda',valor:80,status:'recebido',vencimento:'2026-09-01',recebido_em:'2026-09-01'},
];

function navegador(){
  const elementos=new Map(),requisicoes=[],mensagens=[],alertas=[];
  let manipulador,relogio=Date.now();
  class DataControlada extends Date{static now(){return relogio;}}
  class Elemento{
    constructor(id=''){
      this.id=id;this._valor='';this._html='';this._texto='';this.children=[];
      this.style={};this.attributes={};this.hidden=false;this.options=[];
      const classes=new Set(id==='fin-cats-painel'?['hidden']:[]);
      this.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),
        toggle:(c,forcar)=>{const ativo=forcar??!classes.has(c);ativo?classes.add(c):classes.delete(c);return ativo;}};
    }
    get value(){return this._valor;}
    set value(valor){this._valor=String(valor);}
    get innerHTML(){return this._html;}
    set innerHTML(html){
      this._html=html;this.children=[];
      if(html.includes('<option')){this.options=[];this._valor='';}
    }
    get textContent(){return this._texto+this.children.map(c=>c.textContent).join('');}
    set textContent(texto){this._texto=String(texto);this.children=[];}
    setAttribute(nome,valor){this.attributes[nome]=valor;}
    getAttribute(nome){return this.attributes[nome];}
    add(opcao){this.options.push(opcao);}
    append(filho){this.children.push(filho);if(filho.id) elementos.set(filho.id,filho);}
    prepend(filho){this.children.unshift(filho);if(filho.id) elementos.set(filho.id,filho);}
    focus(){}
    select(){}
  }
  function elemento(id){
    if(!elementos.has(id)) elementos.set(id,new Elemento(id));
    return elementos.get(id);
  }
  const dadosPadrao=url=>({
    '/api/fin/contas-pagar':contas,'/api/fin/categorias-pagar':categorias,
    '/api/fornecedores':fornecedores,'/api/fin/alertas-vencimento':[],
    '/api/fin/contas-receber':receber,'/api/fin/categorias-receber':['Venda','Outros'],
  })[url]??[];
  manipulador=requisicao=>resposta(requisicao.method==='GET'?dadosPadrao(requisicao.url):{ok:true});
  const contexto=vm.createContext({
    AbortController,Date:DataControlada,Option:function(text,value){this.text=text;this.value=String(value);},
    document:{getElementById:id=>id.startsWith('fin-aviso-contas-')?(elementos.get(id)||null):elemento(id),
      createElement:()=>new Elemento(),querySelectorAll:()=>[]},
    finCatsPagar:[],finFornecedores:[],finCatsReceber:[],finContasPagar:[],finContasReceber:[],
    criarEstadoLote:()=>({enviando:false}),reabrirOperacaoPendente:()=>false,
    recuperarOperacaoPendente:()=>{},enviarOperacaoAtomica:async()=>({ok:true}),
    fecharModal:()=>{},hojeLocal:()=> '2026-10-15',finFmt:valor=>Number(valor).toFixed(2),
    finStatusBadge:status=>status,dataLocalISO:data=>data.toISOString().slice(0,10),
    finCarregarAlertasVencimento:async({dados})=>{alertas.push(copiar(dados));},
    toast:mensagem=>mensagens.push(mensagem),confirm:()=>true,
    fetch:async(url,opcoes={})=>{
      const requisicao={url,method:opcoes.method||'GET',signal:opcoes.signal,
        body:opcoes.body&&JSON.parse(opcoes.body)};
      requisicoes.push(requisicao);
      return manipulador(requisicao);
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/modules/financeiro_contas.js'),'utf8'),contexto);
  return {elemento,requisicoes,mensagens,alertas,contexto,dadosPadrao,
    executar:codigo=>vm.runInContext(codigo,contexto),
    dados:codigo=>copiar(vm.runInContext(codigo,contexto)),
    responder:funcao=>{manipulador=funcao;},
    adiantar:milissegundos=>{relogio+=milissegundos;},
    entrada:(id,valor)=>{elemento(id).value=valor;},
    gets:()=>requisicoes.filter(r=>r.method==='GET'),
  };
}

function referenciaLista({status,categoria,mes,fornecedor}){
  let lista=contas;
  if(categoria) lista=lista.filter(c=>c.categoria===categoria);
  if(mes) lista=lista.filter(c=>c.vencimento.slice(0,7)===mes||(c.pago_em||'').slice(0,7)===mes);
  if(fornecedor) lista=lista.filter(c=>c.fornecedor_id===Number(fornecedor));
  if(status==='vencido') lista=lista.filter(c=>c.status==='aberto'&&c.vencimento<'2026-10-15');
  else if(status!=='todos') lista=lista.filter(c=>c.status===status);
  return lista.map(c=>c.id);
}

function referenciaResumo(status,mes){
  if(!mes) return [];
  const grupos={};
  for(const c of contas){
    if(c.vencimento.slice(0,7)!==mes&&(c.pago_em||'').slice(0,7)!==mes) continue;
    if(status!=='todos'&&status!=='vencido'&&c.status!==status) continue;
    const grupo=grupos[c.categoria]??={nome:c.categoria,valor:0,quantidade:0};
    grupo.valor+=c.valor;grupo.quantidade++;
  }
  return Object.values(grupos).sort((a,b)=>b.valor-a.valor||a.nome.localeCompare(b.nome));
}

test('uma leitura alimenta tabela/cards/resumo e filtros não fazem nova consulta',async()=>{
  const n=navegador();
  assert.equal(await n.executar('finCarregarContasPagar({atualizar:true})'),true);
  assert.equal(n.gets().length,4);
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fin/contas-pagar').length,1);
  for(const status of ['todos','aberto','vencido','pago']){
    for(const categoria of ['','Ingredientes','Outros']){
      for(const mes of ['','2026-09','2026-10']){
        for(const fornecedor of ['','1','2']){
          n.entrada('fin-filtro-cat-pagar',categoria);n.entrada('fin-filtro-mes-pagar',mes);
          n.entrada('fin-filtro-forn-pagar',fornecedor);
          await n.executar(`finFiltroStatusPagar=${JSON.stringify(status)};finCarregarContasPagar()`);
          assert.deepEqual(n.dados('finContasPagar.map(c=>c.id)'),referenciaLista({status,categoria,mes,fornecedor}));
          assert.equal(n.elemento('fin-pagar-total-aberto').textContent,'190.00');
          assert.equal(n.elemento('fin-pagar-total-vencido').textContent,'140.00');
          assert.equal(n.elemento('fin-pagar-total-pago').textContent,'200.00');
          const resumo=referenciaResumo(status,mes);
          assert.equal(n.elemento('fin-resumo-cats-wrap').classList.contains('hidden'),resumo.length===0);
          if(resumo.length){
            const html=n.elemento('fin-resumo-cats').innerHTML;
            let anterior=-1;
            for(const grupo of resumo){
              const atual=html.indexOf(`>${grupo.nome}</div>`);
              assert.ok(atual>anterior);anterior=atual;
              assert.ok(html.includes(`>${grupo.valor.toFixed(2)}</div>`));
              assert.ok(html.includes(`>${grupo.quantidade} conta(s)</div>`));
            }
          }
        }
      }
    }
  }
  assert.equal(n.gets().length,4);
  assert.equal(n.elemento('page-fin-contas-pagar').getAttribute('aria-busy'),'false');
  assert.equal(n.elemento('fin-aviso-contas-pagar').hidden,true);
});

test('filtros concorrentes compartilham a leitura e aplicam a seleção mais recente',async()=>{
  const n=navegador();let concluir;
  n.responder(r=>r.url==='/api/fin/contas-pagar'
    ?new Promise(resolver=>{concluir=resolver;}):resposta(n.dadosPadrao(r.url)));
  const primeira=n.executar('finCarregarContasPagar()');
  assert.equal(n.elemento('page-fin-contas-pagar').getAttribute('aria-busy'),'true');
  n.entrada('fin-filtro-mes-pagar','2026-10');
  const ultima=n.executar("finFiltroStatusPagar='vencido';finCarregarContasPagar()");
  assert.equal(n.gets().length,4);
  concluir(resposta(contas));
  assert.deepEqual(await Promise.all([primeira,ultima]),[false,true]);
  assert.deepEqual(n.dados('finContasPagar.map(c=>c.id)'),[1,6]);
  assert.equal(n.elemento('page-fin-contas-pagar').getAttribute('aria-busy'),'false');
});

test('TTL de 30 segundos renova contas na próxima interação sem consultas ociosas',async()=>{
  const n=navegador();await n.executar('finCarregarContasPagar()');
  n.adiantar(29999);await n.executar('finCarregarContasPagar()');
  assert.equal(n.gets().length,4);
  n.responder(r=>resposta(r.url==='/api/fin/contas-pagar'
    ?contas.map(c=>c.id===1?{...c,valor:120}:c):n.dadosPadrao(r.url)));
  n.adiantar(1);
  // A passagem do tempo não inicia polling; somente a interação renova a leitura.
  assert.equal(n.gets().length,4);
  await n.executar('finCarregarContasPagar()');
  assert.equal(n.gets().length,6);
  assert.equal(n.elemento('fin-pagar-total-aberto').textContent,'210.00');
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fin/categorias-pagar').length,1);
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fornecedores').length,1);
  await n.executar('finCarregarContasReceber()');
  n.adiantar(30000);await n.executar('finCarregarContasReceber()');
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fin/contas-receber').length,2);
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fin/categorias-receber').length,1);
});

test('categorias e fornecedores vazios continuam em cache inclusive ao abrir modal',async()=>{
  const n=navegador();
  n.responder(r=>resposta(['/api/fin/categorias-pagar','/api/fornecedores'].includes(r.url)?[]:n.dadosPadrao(r.url)));
  await n.executar('finCarregarContasPagar()');
  await n.executar('finAbrirModalPagar()');
  await n.executar('finAbrirEdicaoPagar(1)');
  await n.executar('finCarregarContasPagar()');
  assert.equal(n.gets().length,4);
  assert.deepEqual(n.dados('finCatsPagar'),[]);
  assert.deepEqual(n.dados('finFornecedores'),[]);
});

test('reentrada cancela leituras antigas e respostas tardias não substituem a tela',async()=>{
  const n=navegador(),antigas=[];let fase=0;
  const novas=[{...contas[0],descricao:'Dados novos',valor:300}];
  n.responder(r=>fase===0?new Promise(resolver=>antigas.push({r,resolver}))
    :resposta(r.url==='/api/fin/contas-pagar'?novas:n.dadosPadrao(r.url)));
  const antiga=n.executar('finCarregarContasPagar({atualizar:true})');
  fase=1;
  assert.equal(await n.executar('finCarregarContasPagar({atualizar:true})'),true);
  assert.ok(antigas.every(({r})=>r.signal.aborted));
  for(const {r,resolver} of antigas) resolver(resposta(n.dadosPadrao(r.url)));
  assert.equal(await antiga,false);
  assert.equal(n.dados('finContasPagar[0].descricao'),'Dados novos');
  assert.equal(n.elemento('fin-pagar-total-pago').textContent,'300.00');
  assert.equal(n.alertas.length,1);
  assert.equal(n.gets().length,8);
});

test('pagar durante leitura pendente força dados novos e descarta a resposta anterior',async()=>{
  const n=navegador();await n.executar('finCarregarContasPagar()');
  let concluirAntiga,paga=false;
  n.responder(r=>{
    if(r.method==='POST'){paga=true;return resposta({ok:true});}
    if(r.url==='/api/fin/contas-pagar'){
      if(!paga) return new Promise(resolver=>{concluirAntiga=resolver;});
      return resposta(contas.map(c=>c.id===1?{...c,status:'pago',pago_em:'2026-10-15'}:c));
    }
    return resposta(n.dadosPadrao(r.url));
  });
  const antiga=n.executar('finCarregarContasPagar({atualizar:true})');
  await n.executar('finPagarConta(1)');
  concluirAntiga(resposta(contas));await antiga;
  assert.equal(n.dados('finContasPagar.find(c=>c.id===1).status'),'pago');
  assert.equal(n.elemento('fin-pagar-total-aberto').textContent,'90.00');
  assert.equal(n.elemento('fin-pagar-total-pago').textContent,'300.00');
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fin/contas-pagar').length,3);
  assert.equal(n.elemento('fin-aviso-contas-pagar').hidden,true);
});

test('CRUD de categoria atualiza opções, contas e fornecedor sem temporizador',async()=>{
  const n=navegador();let criada=false,renomeada=false;
  n.responder(r=>{
    if(r.method==='POST'){criada=true;return resposta({ok:true});}
    if(r.method==='PUT'){renomeada=true;return resposta({ok:true});}
    if(r.url==='/api/fin/categorias-pagar') return resposta(criada?[{id:9,nome:renomeada?'Renomeada':'Nova'}]:[]);
    if(r.url==='/api/fornecedores') return resposta(criada?[{id:3,nome:'Atualizado'}]:fornecedores);
    if(r.url==='/api/fin/contas-pagar') return resposta(criada?[{...contas[0],categoria:renomeada?'Renomeada':'Nova'}]:[]);
    return resposta(n.dadosPadrao(r.url));
  });
  await n.executar('finCarregarContasPagar()');
  n.entrada('fin-nova-cat-input','Nova');await n.executar('finCriarCategoria()');
  assert.deepEqual(n.dados('finCatsPagar.map(c=>c.nome)'),['Nova']);
  assert.equal(n.elemento('fin-cats-painel').classList.contains('hidden'),false);
  assert.deepEqual(n.elemento('fin-filtro-forn-pagar').options.map(o=>o.value),['3']);
  n.entrada('fin-filtro-cat-pagar','Nova');n.entrada('fin-cat-edit-9','Renomeada');
  await n.executar('finSalvarRenomeacao(9)');
  assert.deepEqual(n.dados('finCatsPagar.map(c=>c.nome)'),['Renomeada']);
  assert.equal(n.elemento('fin-filtro-cat-pagar').value,'');
  assert.equal(n.dados('finContasPagar[0].categoria'),'Renomeada');
  assert.equal(n.gets().length,12);
});

test('falhas HTTP, conexão e JSON mantêm dados, liberam busy e oferecem tentar novamente',async()=>{
  for(const falha of [()=>resposta({erro:'Indisponível'},503),
    ()=>Promise.reject(new Error('Sem conexão')),()=>({ok:true,json:async()=>{throw new SyntaxError('JSON incompleto');}}),
    ()=>resposta({erro:'Formato inesperado'})]){
    const n=navegador();await n.executar('finCarregarContasPagar()');
    const html=n.elemento('t-fin-pagar').innerHTML;
    n.responder(r=>r.url==='/api/fin/contas-pagar'?falha():resposta(n.dadosPadrao(r.url)));
    assert.equal(await n.executar('finCarregarContasPagar({atualizar:true})'),false);
    assert.equal(n.elemento('t-fin-pagar').innerHTML,html);
    assert.equal(n.elemento('fin-pagar-total-aberto').textContent,'190.00');
    assert.equal(n.elemento('page-fin-contas-pagar').getAttribute('aria-busy'),'false');
    const aviso=n.elemento('fin-aviso-contas-pagar');
    assert.equal(aviso.getAttribute('role'),'alert');
    assert.equal(aviso.hidden,false);
    assert.equal(aviso.children[0].textContent,'Tentar novamente');
    n.responder(r=>resposta(n.dadosPadrao(r.url)));
    assert.equal(await aviso.children[0].onclick(),true);
    assert.equal(aviso.hidden,true);
  }
});

test('falha em cadastro auxiliar não publica conjunto parcial nem grava erro como cache',async()=>{
  const n=navegador();await n.executar('finCarregarContasPagar()');
  n.responder(r=>r.url==='/api/fin/categorias-pagar'?resposta({erro:'Falhou'},500)
    :resposta(r.url==='/api/fin/contas-pagar'?[]:n.dadosPadrao(r.url)));
  await n.executar('finCarregarContasPagar({atualizar:true})');
  assert.equal(n.dados('finContasPagar.length'),contas.length);
  n.responder(r=>resposta(n.dadosPadrao(r.url)));
  await n.executar('finAbrirModalPagar()');
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fin/categorias-pagar').length,3);
  assert.equal(n.requisicoes.filter(r=>r.url==='/api/fornecedores').length,2);
});

test('contas a receber compartilham consulta para cards e filtros e recarregam após mutação',async()=>{
  const n=navegador();await n.executar('finCarregarContasReceber({atualizar:true})');
  assert.equal(n.gets().length,2);
  const esperado={todos:[1,2,3,4],aberto:[1,2],vencido:[1],recebido:[3,4]};
  for(const [status,ids] of Object.entries(esperado)){
    await n.executar(`finFiltroStatusReceber=${JSON.stringify(status)};finCarregarContasReceber()`);
    assert.deepEqual(n.dados('finContasReceber.map(c=>c.id)'),ids);
    assert.equal(n.elemento('fin-receber-total-aberto').textContent,'40.00');
    assert.equal(n.elemento('fin-receber-total-recebido').textContent,'50.00');
  }
  assert.equal(n.gets().length,2);
  n.responder(r=>resposta(r.method==='POST'?{ok:true}:r.url==='/api/fin/contas-receber'
    ?receber.map(c=>c.id===1?{...c,status:'recebido',recebido_em:'2026-10-15'}:c):n.dadosPadrao(r.url)));
  await n.executar('finReceberConta(1)');
  assert.equal(n.gets().length,4);
  assert.equal(n.elemento('fin-receber-total-aberto').textContent,'25.00');
  assert.equal(n.elemento('fin-receber-total-recebido').textContent,'65.00');
});

test('mutação recusada não anuncia sucesso nem invalida a lista disponível',async()=>{
  const n=navegador();await n.executar('finCarregarContasPagar()');
  n.responder(()=>resposta({erro:'Conta vinculada'},409));
  await n.executar('finDeletarContaPagar(1)');
  assert.equal(n.mensagens.at(-1),'Conta vinculada');
  assert.equal(n.gets().length,4);
  await n.executar('finCarregarContasPagar()');
  assert.equal(n.gets().length,4);
  assert.equal(n.dados('finContasPagar.length'),contas.length);
});
