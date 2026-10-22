// Fluxos reais dos formulários de cartões, com rede e DOM simulados.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const copiar=valor=>JSON.parse(JSON.stringify(valor));
const resposta=(dados,status=200)=>({ok:status>=200&&status<300,status,json:async()=>copiar(dados)});
const configuracao={condicoes:[]};
const relatorio=mes=>({mes,resumo:{bruto_centavos:10000,taxas_centavos:250,previsto_centavos:9750,
  saldo_centavos:9750,recebido_no_mes_centavos:0,diferenca_centavos:0},
  por_operadora:[{operadora_id:'cielo',previsto_centavos:9750,saldo_centavos:9750,recebido_no_mes_centavos:0}],
  parcelas:[],agenda_mensal:[{mes,previsto_centavos:9750,saldo_centavos:9750,recebido_no_mes_centavos:0}],
  pendentes_configuracao:{quantidade:0,bruto_centavos:0}});
const venda={id:7,operadora_id:'cielo',modalidade:'credito',bandeira:'visa',data_venda:'2026-10-01',
  bruto_centavos:10000,observacao:'Total diário',calculado:true,taxa_percentual:'2.5',possui_recebimento:false};
const parcela={id:9,venda_id:7,operadora_id:'cielo',modalidade:'credito',bandeira:'visa',
  data_venda:'2026-10-01',parcela:1,total_parcelas:1,bruto_centavos:10000,taxa_centavos:250,
  liquido_centavos:9750,data_prevista:'2026-10-31',status:'pendente',valor_recebido_centavos:null,
  data_recebimento:null,diferenca_centavos:null,observacao_recebimento:''};

function navegador(armazenamento=new Map()){
  const elementos=new Map(),requisicoes=[],mensagens=[];
  let manipulador,confirmar=true;
  class Elemento{
    constructor(id){
      this.id=id;this._valor='';this.textContent='';this.innerHTML='';this.hidden=false;
      this.disabled=false;this.required=false;this.noValidate=false;this.attributes={};this.children=[];
      this.dataset={};this.classList={toggle(){},add(){},remove(){}};
    }
    get value(){return this._valor;}set value(valor){this._valor=String(valor);}
    setAttribute(nome,valor){this.attributes[nome]=String(valor);}
    querySelectorAll(){return this.children;}
    scrollIntoView(){}
    reportValidity(){return true;}
  }
  const elemento=id=>{if(!elementos.has(id))elementos.set(id,new Elemento(id));return elementos.get(id);};
  const contexto=vm.createContext({
    AbortController,URLSearchParams,Uint8Array,setTimeout,clearTimeout,
    crypto:{getRandomValues:bytes=>require('node:crypto').randomFillSync(bytes)},
    me:{id:1,perfil:'admin'},document:{getElementById:elemento,querySelectorAll:()=>[]},
    sessionStorage:{getItem:k=>armazenamento.get(k)||null,setItem:(k,v)=>armazenamento.set(k,v),removeItem:k=>armazenamento.delete(k)},
    hojeLocal:()=> '2026-10-21',finFmt:valor=>valor.toLocaleString('pt-BR',{style:'currency',currency:'BRL'}),
    adiarBusca:funcao=>funcao,toast:mensagem=>mensagens.push(mensagem),confirm:()=>confirmar,
    fetch:async(url,opcoes={})=>{
      const r={url,method:opcoes.method||'GET',body:opcoes.body?JSON.parse(opcoes.body):null,signal:opcoes.signal};
      requisicoes.push(r);return manipulador(r);
    },
  });
  function padrao(r){
    if(r.method!=='GET')return resposta({ok:true,id:7,calculado:true},201);
    if(r.url.endsWith('/configuracao'))return resposta(configuracao);
    if(r.url.includes('/vendas?'))return resposta([venda]);
    return resposta(relatorio(new URL('http://teste'+r.url).searchParams.get('mes')));
  }
  manipulador=padrao;
  for(const arquivo of ['movimentacoes.js','financeiro_cartoes.js'])
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/modules',arquivo),'utf8'),contexto);
  return {elemento,requisicoes,mensagens,armazenamento,contexto,padrao,
    executar:codigo=>vm.runInContext(codigo,contexto),
    dados:codigo=>copiar(vm.runInContext(codigo,contexto)),
    responder:funcao=>manipulador=funcao,confirmar:valor=>confirmar=valor,
    entrada:(id,valor)=>elemento(id).value=valor,
  };
}
function preencherVenda(n,alteracoes={}){
  n.executar('cartoesNovaVenda()');
  for(const [campo,valor] of Object.entries({operadora:'cielo',modalidade:'credito',bandeira:'visa',
    data:'2026-10-01',valor:'100.01',observacao:'Total diário',...alteracoes}))n.entrada('cartoes-venda-'+campo,valor);
}
function preencherCondicao(n,alteracoes={}){
  n.executar('cartoesNovaCondicao()');
  for(const [campo,valor] of Object.entries({operadora:'cielo',modalidade:'credito',bandeira:'',
    inicio:'2026-10-01',taxa:'2.123456',prazo:'30',tipo:'corridos',intervalo:'',...alteracoes}))n.entrada('cartoes-condicao-'+campo,valor);
}

test('entrada administrativa consulta o mês local e a operadora em três leituras',async()=>{
  const n=navegador();n.entrada('cartoes-operadora','rede');
  assert.equal(await n.executar('cartoesIniciar()'),true);
  assert.equal(n.elemento('cartoes-mes').value,'2026-10');
  assert.equal(n.requisicoes.length,3);
  assert.ok(n.requisicoes.some(r=>r.url.endsWith('/vendas?mes=2026-10&operadora=rede')));
  assert.match(n.elemento('cartoes-estado').textContent,/Rede/);
  assert.match(n.elemento('cartoes-resumo').innerHTML,/Recebido no mês \(data real\)/);
});

test('perfil sem permissão não consulta cartões',async()=>{
  const n=navegador();n.executar("me.perfil='caixa'");
  assert.equal(await n.executar('cartoesIniciar()'),false);
  assert.equal(n.requisicoes.length,0);
  assert.match(n.elemento('cartoes-aviso').textContent,/Somente administradores/);
});

test('resposta antiga não substitui os dados do filtro mais recente',async()=>{
  const n=navegador(),liberar=[];
  n.entrada('cartoes-mes','2026-09');
  n.responder(r=>new Promise(resolve=>liberar.push(()=>resolve(n.padrao(r)))));
  const antiga=n.executar('cartoesAtualizar()');
  n.responder(n.padrao);n.entrada('cartoes-mes','2026-10');
  assert.equal(await n.executar('cartoesAtualizar()'),true);
  liberar.forEach(fn=>fn());assert.equal(await antiga,false);
  assert.equal(n.dados('cartoesEstado.relatorio.mes'),'2026-10');
  assert.equal(n.requisicoes[0].signal.aborted,true);
});

test('falha de atualização preserva dados e identifica o filtro ainda exibido',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');
  const html=n.elemento('cartoes-resumo').innerHTML;
  n.entrada('cartoes-mes','2026-11');n.responder(()=>resposta({erro:'Banco ocupado'},503));
  assert.equal(await n.executar('cartoesAtualizar()'),false);
  assert.equal(n.elemento('cartoes-resumo').innerHTML,html);
  assert.match(n.elemento('cartoes-aviso').textContent,/10\/2026/);
  assert.match(n.elemento('cartoes-aviso').textContent,/Banco ocupado/);
});

test('limpar o mês durante leitura cancela a consulta e remove o estado de carregamento',async()=>{
  const n=navegador(),liberar=[];
  await n.executar('cartoesIniciar()');
  const anterior=n.elemento('cartoes-resumo').innerHTML;
  n.responder(r=>new Promise(resolve=>liberar.push(()=>resolve(n.padrao(r)))));
  const pendente=n.executar('cartoesAtualizar()');
  n.entrada('cartoes-mes','');
  assert.equal(await n.executar('cartoesAtualizar()'),false);
  assert.equal(n.executar('cartoesEstado.controlador'),null);
  assert.equal(n.elemento('page-fin-cartoes').attributes['aria-busy'],'false');
  assert.match(n.elemento('cartoes-estado').textContent,/Consulta interrompida/);
  assert.match(n.elemento('cartoes-aviso').textContent,/10\/2026/);
  liberar.forEach(fn=>fn());assert.equal(await pendente,false);
  assert.equal(n.elemento('cartoes-resumo').innerHTML,anterior);
});

test('gravação recusada após cancelar uma leitura não deixa carregamento preso',async()=>{
  const n=navegador(),liberar=[];
  await n.executar('cartoesIniciar()');
  n.responder(r=>r.method==='DELETE'?resposta({erro:'Venda recebida'},409)
    :new Promise(resolve=>liberar.push(()=>resolve(n.padrao(r)))));
  const pendente=n.executar('cartoesAtualizar()');
  assert.equal(await n.executar('cartoesExcluirVenda(7)'),false);
  assert.equal(n.executar('cartoesEstado.controlador'),null);
  assert.equal(n.elemento('page-fin-cartoes').attributes['aria-busy'],'false');
  assert.match(n.elemento('cartoes-aviso').textContent,/Venda recebida/);
  assert.match(n.elemento('cartoes-estado').textContent,/Consulta interrompida/);
  liberar.forEach(fn=>fn());assert.equal(await pendente,false);
});

test('venda manual preserva centavos no payload e informa ausência de condição',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');preencherVenda(n);
  n.responder(r=>r.method==='POST'?resposta({ok:true,id:7,calculado:false},201):n.padrao(r));
  assert.equal(await n.executar('cartoesSalvarVenda()'),true);
  const enviada=n.requisicoes.find(r=>r.method==='POST').body;
  assert.equal(enviada.valor_bruto,'100.01');assert.match(enviada.operacao_id,/^[a-f0-9-]{36}$/);
  assert.ok(n.mensagens.some(t=>t.includes('sem condição vigente')));
  assert.equal(n.elemento('cartoes-venda-editor').hidden,true);
});

test('resposta perdida sobrevive a recarregamento e recupera a mesma venda antes de alterações',async()=>{
  const armazenamento=new Map(),n=navegador(armazenamento);
  await n.executar('cartoesIniciar()');preencherVenda(n);
  n.responder(r=>{if(r.method==='POST')throw new Error('resposta perdida');return n.padrao(r);});
  assert.equal(await n.executar('cartoesSalvarVenda()'),false);
  const primeira=n.requisicoes.find(r=>r.method==='POST').body;
  assert.equal(armazenamento.size,1);
  const recarregada=navegador(armazenamento);await recarregada.executar('cartoesIniciar()');
  preencherVenda(recarregada,{valor:'999.99',data:'2026-10-20'});
  recarregada.elemento('cartoes-venda-formulario').reportValidity=()=>false;
  assert.equal(recarregada.elemento('cartoes-venda-formulario').noValidate,true);
  assert.equal(await recarregada.executar('cartoesSalvarVenda()'),true);
  assert.deepEqual(recarregada.requisicoes.find(r=>r.method==='POST').body,primeira);
  assert.equal(armazenamento.size,0);
  assert.ok(recarregada.mensagens.some(t=>t.includes('Alterações atuais não foram enviadas')));
});

test('persistência inválida não produz payload recuperado',()=>{
  const salvos=new Map([['sgliras:operacao-pendente:1:cartoes-venda',JSON.stringify({
    operacaoId:'teste',conteudo:JSON.stringify({itens:[{produto_id:1}]})})]]);
  const n=navegador(salvos);n.executar('cartoesNovaVenda()');
  assert.equal(n.dados('cartoesVendaOperacao.incerta'),false);
});

test('erro ao excluir mantém venda e não anuncia sucesso',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');
  n.responder(r=>r.method==='DELETE'?resposta({erro:'Venda já recebida'},409):n.padrao(r));
  assert.equal(await n.executar('cartoesExcluirVenda(7)'),false);
  assert.equal(n.dados('cartoesEstado.vendas.length'),1);
  assert.match(n.elemento('cartoes-aviso').textContent,/Venda já recebida/);
  assert.equal(n.mensagens.includes('Total diário excluído.'),false);
});

test('recebimento de zero bloqueia edição e exclusão mesmo fora do mês previsto',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');
  n.executar('cartoesEstado.vendas[0].possui_recebimento=true;cartoesRenderizarVendas()');
  assert.doesNotMatch(n.elemento('cartoes-vendas-lista').innerHTML,/cartoesExcluirVenda|cartoesEditarVenda/);
  const antes=n.requisicoes.length;
  n.executar('cartoesEditarVenda(7)');assert.equal(await n.executar('cartoesExcluirVenda(7)'),false);
  assert.equal(n.requisicoes.length,antes);
  assert.equal(n.executar("cartoesRecebida({status:'divergente',valor_recebido_centavos:0})"),true);
});

test('recebimento zero é enviado explicitamente e erro conserva o formulário',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');
  n.executar(`cartoesEstado.relatorio.parcelas=${JSON.stringify([parcela])};cartoesAbrirRecebimento(9)`);
  assert.equal(n.elemento('cartoes-recebimento-valor').value,'');
  n.entrada('cartoes-recebimento-valor','0');
  n.responder(r=>r.method==='POST'?resposta({erro:'Confira novamente'},409):n.padrao(r));
  assert.equal(await n.executar('cartoesSalvarParcela()'),false);
  const post=n.requisicoes.find(r=>r.method==='POST');
  assert.equal(post.body.valor_recebido,'0');assert.equal(post.body.data_recebimento,'2026-10-21');
  assert.equal(n.elemento('cartoes-parcela-editor').hidden,false);
  assert.match(n.elemento('cartoes-parcela-aviso').textContent,/Confira novamente/);
});

test('condição não presume taxas ou prazos e aceita as seis casas contratadas',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');n.executar('cartoesNovaCondicao()');
  for(const id of ['taxa','prazo','tipo','intervalo'])assert.equal(n.elemento('cartoes-condicao-'+id).value,'');
  preencherCondicao(n);assert.equal(await n.executar('cartoesSalvarCondicao()'),true);
  const enviada=n.requisicoes.find(r=>r.method==='POST').body;
  assert.equal(enviada.taxa_percentual,'2.123456');assert.equal(enviada.intervalo_parcelas_dias,null);
  assert.equal(enviada.prazo_dias,30);
});

test('crédito em 2x exige intervalo e não oferece outras quantidades',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');preencherCondicao(n,{modalidade:'credito_2x'});
  n.executar('cartoesAlternarIntervalo()');
  assert.equal(n.elemento('cartoes-condicao-intervalo').required,true);
  assert.equal(await n.executar('cartoesSalvarCondicao()'),false);
  assert.equal(n.requisicoes.filter(r=>r.method==='POST').length,0);
  n.entrada('cartoes-condicao-intervalo','30');assert.equal(await n.executar('cartoesSalvarCondicao()'),true);
  assert.equal(n.requisicoes.find(r=>r.method==='POST').body.intervalo_parcelas_dias,30);
  assert.deepEqual(n.dados('Object.keys(CARTOES_MODALIDADES)'),['debito','credito','credito_2x','voucher']);
});

test('valores com precisão indevida são recusados antes do envio',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');preencherVenda(n,{valor:'1.001'});
  assert.equal(await n.executar('cartoesSalvarVenda()'),false);
  preencherCondicao(n,{taxa:'2.1234567'});assert.equal(await n.executar('cartoesSalvarCondicao()'),false);
  assert.equal(n.requisicoes.filter(r=>r.method==='POST').length,0);
});

test('observação e bandeira são escapadas na tabela, nomes e cores são fixos',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');
  n.executar(`cartoesEstado.vendas[0].bandeira='<img src=x onerror=alert(1)>';cartoesEstado.vendas[0].observacao='<script>falha</script>';cartoesRenderizarVendas()`);
  const html=n.elemento('cartoes-vendas-lista').innerHTML;
  assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;script&gt;/);
  assert.deepEqual(n.dados('CARTOES_OPERADORAS'),{cielo:{nome:'Cielo',cor:'#168bd2'},rede:{nome:'Rede',cor:'#f58220'},sipag:{nome:'Sipag',cor:'#19964b'}});
});

test('duplo envio durante requisição pendente faz somente um POST',async()=>{
  const n=navegador();await n.executar('cartoesIniciar()');preencherVenda(n);
  let concluir;n.responder(r=>r.method==='POST'?new Promise(resolve=>concluir=()=>resolve(resposta({ok:true,id:7,calculado:true},201))):n.padrao(r));
  const primeiro=n.executar('cartoesSalvarVenda()');
  assert.equal(await n.executar('cartoesSalvarVenda()'),false);
  assert.equal(n.requisicoes.filter(r=>r.method==='POST').length,1);
  concluir();assert.equal(await primeiro,true);
});

test('template integra PDF e todas as funções dos formulários estão disponíveis',()=>{
  const n=navegador();n.contexto.cartoesGerarPDF=()=>{};
  const template=fs.readFileSync(path.join(__dirname,'../templates/financeiro_cartoes.html'),'utf8');
  const ids=Array.from(template.matchAll(/\bid="([^"]+)"/g),m=>m[1]);
  assert.equal(new Set(ids).size,ids.length);
  for(const [,nome] of template.matchAll(/\b(?:onclick|onchange|onsubmit)="(cartoes\w+)\(/g))
    assert.equal(n.executar(`typeof ${nome}`),'function',nome);
  const index=fs.readFileSync(path.join(__dirname,'../templates/index.html'),'utf8');
  assert.match(index,/include 'financeiro_cartoes.html'/);
  assert.ok(index.indexOf('relatorio_cartoes.js')<index.indexOf('financeiro_cartoes.js'));
  assert.ok(index.indexOf('financeiro_cartoes.js')<index.indexOf('navegacao.js'));
});
