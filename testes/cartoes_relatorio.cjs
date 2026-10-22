const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');

const codigo=fs.readFileSync(path.join(__dirname,'../static/js/modules/relatorio_cartoes.js'),'utf8');
function relatorio(){
  return {
    mes:'2026-10',
    resumo:{bruto_centavos:10001,taxas_centavos:251,previsto_centavos:9750,saldo_centavos:0,
      recebido_no_mes_centavos:12000,diferenca_centavos:-1},
    por_operadora:[
      {operadora_id:'cielo',previsto_centavos:9750,saldo_centavos:0,recebido_no_mes_centavos:9749},
      {operadora_id:'rede',previsto_centavos:0,saldo_centavos:0,recebido_no_mes_centavos:2251},
      {operadora_id:'sipag',previsto_centavos:0,saldo_centavos:0,recebido_no_mes_centavos:0},
    ],
    parcelas:[{id:1,venda_id:1,operadora_id:'cielo',modalidade:'credito_2x',bandeira:'Visa',
      data_venda:'2026-09-01',parcela:1,total_parcelas:2,bruto_centavos:10001,taxa_centavos:251,
      liquido_centavos:9750,data_prevista:'2026-10-01',status:'divergente',
      valor_recebido_centavos:9749,data_recebimento:'2026-10-02',diferenca_centavos:-1,
      observacao_recebimento:'Conferido no extrato'}],
    agenda_mensal:[{mes:'2026-10',previsto_centavos:9750,saldo_centavos:0,recebido_no_mes_centavos:12000},
      {mes:'2026-11',previsto_centavos:9751,saldo_centavos:9751,recebido_no_mes_centavos:0}],
    pendentes_configuracao:{quantidade:2,bruto_centavos:50000},
  };
}
function ambiente(opcoes={}){
  const eventos=[],avisos=[],requisicoes=[];
  const janela={
    closed:false,html:'',
    document:{
      write(html){janela.html+=html;eventos.push('write');},
      open(){janela.html='';eventos.push('document.open');},
      close(){eventos.push('document.close');},
      fonts:{ready:opcoes.fontes||Promise.resolve()},
    },
    focus(){eventos.push('focus');},print(){eventos.push('print');},
    close(){this.closed=true;eventos.push('close');},
  };
  const contexto=vm.createContext({URL,URLSearchParams,
    window:{location:{origin:'http://127.0.0.1:8888'},open(){eventos.push('open');return opcoes.bloqueado?null:janela;}},
    toast(...args){avisos.push(args);},
    async fetch(url){
      eventos.push('fetch');requisicoes.push(url);
      if(opcoes.fetch) return opcoes.fetch(url);
      return {ok:true,json:async()=>relatorio()};
    },
  });
  vm.runInContext(codigo,contexto);
  return {contexto,eventos,avisos,requisicoes,janela};
}

test('PDF formata centavos exatos, zeros e diferenças negativas',()=>{
  const {contexto:c}=ambiente();
  assert.equal(c.cartoesPDFDinheiro(0),'R$ 0,00');
  assert.equal(c.cartoesPDFDinheiro(1),'R$ 0,01');
  assert.equal(c.cartoesPDFDinheiro(-1),'-R$ 0,01');
  assert.equal(c.cartoesPDFDinheiro(100000001),'R$ 1.000.000,01');
  assert.equal(c.cartoesPDFDinheiro(Number.MAX_SAFE_INTEGER),'R$ 90.071.992.547.409,91');
  for(const invalido of [null,undefined,'100',1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1])
    assert.equal(c.cartoesPDFDinheiro(invalido),'—');
});

test('PDF preserva datas locais e rejeita datas impossíveis',()=>{
  const {contexto:c}=ambiente();
  assert.equal(c.cartoesPDFData('2026-10-01'),'01/10/2026');
  assert.equal(c.cartoesPDFData('2024-02-29'),'29/02/2024');
  for(const invalido of ['2026-02-29','2026-13-01','2026-2-1',null,'<script>'])
    assert.equal(c.cartoesPDFData(invalido),'—');
  assert.equal(c.cartoesPDFMes('2026-11'),'Novembro/2026');
  assert.equal(c.cartoesPDFMes('2026-00'),'Período não informado');
});

test('relatório completo inclui nomes, cores, Inter, parcela2x e agenda mensal',()=>{
  const {contexto:c}=ambiente();
  const html=c.cartoesHTMLRelatorio(relatorio(),'','http://192.168.0.10:8888');
  for(const esperado of ['Cielo','Rede','Sipag','#168bd2','#f58220','#19964b','A4 landscape',
    'http://192.168.0.10:8888/static/fonts/InterVariable.woff2','Parcela 1/2','Crédito em 2x',
    'Outubro/2026','Novembro/2026','R$ 120,00','R$ 97,49','-R$ 0,01','Conferido no extrato'])
    assert.ok(html.includes(esperado),esperado);
  assert.match(html,/Recebido com diferença/);
  assert.match(html,/inclusive de parcelas previstas em outros meses/);
  assert.match(html,/liquidadas e não compõem o saldo/);
  assert.match(html,/sem feriados/);
});

test('vendas sem condições não recebem previsões fictícias e têm aviso fora do filtro de mês',()=>{
  const {contexto:c}=ambiente();
  const d=relatorio();
  d.parcelas=[];d.agenda_mensal=[];
  const html=c.cartoesHTMLRelatorio(d,'rede');
  assert.match(html,/Vendas sem condição vigente: 2/);
  assert.match(html,/Bruto: R\$ 500,00/);
  assert.match(html,/todas as datas da operadora selecionada/);
  assert.match(html,/Nenhuma parcela prevista/);
  assert.match(html,/Nenhuma previsão ou recebimento registrado/);
  d.pendentes_configuracao.quantidade=0;
  assert.doesNotMatch(c.cartoesHTMLRelatorio(d),/Vendas sem condição vigente: 0/);
});

test('recebimento zero aparece como valor recebido e diferença mantém sinal',()=>{
  const {contexto:c}=ambiente(),d=relatorio();
  d.parcelas[0].valor_recebido_centavos=0;
  d.parcelas[0].diferenca_centavos=-9750;
  const html=c.cartoesHTMLRelatorio(d);
  assert.match(html,/02\/10\/2026<br><strong>R\$ 0,00<\/strong>/);
  assert.match(html,/-R\$ 97,50/);
});

test('textos do banco são escapados e cores só vêm da lista conhecida',()=>{
  const {contexto:c}=ambiente(),d=relatorio();
  const ataque='<img src=x onerror="alert(1)"><script>alert(1)</script>&';
  d.parcelas[0].bandeira=ataque;d.parcelas[0].observacao_recebimento=ataque;
  d.por_operadora[0].nome=ataque;d.por_operadora[0].cor='red;}</style><script>alert(1)</script>';
  d.parcelas[0].modalidade='constructor';d.parcelas[0].status='__proto__';
  const html=c.cartoesHTMLRelatorio(d,ataque,'javascript:alert(1)');
  assert.doesNotMatch(html,/<script>|<img|javascript:alert|red;}|\[object Object\]/);
  assert.match(html,/&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.match(html,/Operadora não identificada/);
  assert.match(html,/Modalidade não identificada/);
  assert.match(html,/src:url\("\/static\/fonts\/InterVariable.woff2"\)/);
});

test('origem da fonte rejeita esquemas e normaliza caminho sem inserir CSS',()=>{
  const {contexto:c}=ambiente();
  assert.equal(c.cartoesPDFFonte('https://exemplo.com:444/pasta?x=1'),
    'https://exemplo.com:444/static/fonts/InterVariable.woff2');
  assert.equal(c.cartoesPDFFonte('http://[::1]:8888'),
    'http://[::1]:8888/static/fonts/InterVariable.woff2');
  for(const origem of ['data:text/html,teste','javascript:alert(1)','file:///tmp/x','"></style><script>'])
    assert.equal(c.cartoesPDFFonte(origem),'/static/fonts/InterVariable.woff2');
});

test('geração abre janela antes da rede, transmite filtros e imprime após fonte pronta',async()=>{
  let resolver;
  const fontes=new Promise(resolve=>resolver=resolve);
  const a=ambiente({fontes});
  const resultado=a.contexto.cartoesGerarPDF('2026-10','sipag');
  assert.deepEqual(a.eventos.slice(0,4),['open','write','document.close','fetch']);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.eventos.includes('print'),false);
  resolver();
  assert.equal(await resultado,true);
  assert.deepEqual(a.requisicoes,['/api/fin/cartoes/relatorio?mes=2026-10&operadora=sipag']);
  assert.equal(a.eventos.at(-1),'print');
  assert.match(a.janela.html,/<title>Cartões e recebíveis · Outubro\/2026 · Sipag/);
});

test('geração sem filtro de operadora não envia parâmetro artificial',async()=>{
  const a=ambiente();
  assert.equal(await a.contexto.cartoesGerarPDF('2026-10'),true);
  assert.deepEqual(a.requisicoes,['/api/fin/cartoes/relatorio?mes=2026-10']);
});

test('filtros inválidos impedem abrir janela ou consultar API',async()=>{
  const a=ambiente();
  for(const [mes,op] of [['2026-00',''],['2026-13',''],['2026-10','__proto__'],['2026-10','inexistente'],[null,'']])
    assert.equal(await a.contexto.cartoesGerarPDF(mes,op),false);
  assert.deepEqual(a.eventos,[]);
  assert.equal(a.avisos.length,5);
});

test('popup bloqueado informa como continuar e não consulta API',async()=>{
  const a=ambiente({bloqueado:true});
  assert.equal(await a.contexto.cartoesGerarPDF('2026-10'),false);
  assert.deepEqual(a.eventos,['open']);
  assert.match(a.avisos[0][0],/Permita a abertura/);
});

test('falhas HTTP, rede, JSON e contrato fecham janela sem imprimir',async()=>{
  const cenarios=[
    async()=>({ok:false,json:async()=>({erro:'Sessão expirada'})}),
    async()=>{throw new Error('offline');},
    async()=>({ok:true,json:async()=>{throw new SyntaxError('json');}}),
    async()=>({ok:true,json:async()=>({resumo:{}})}),
  ];
  for(const fetch of cenarios){
    const a=ambiente({fetch});
    assert.equal(await a.contexto.cartoesGerarPDF('2026-10'),false);
    assert.equal(a.janela.closed,true);
    assert.equal(a.eventos.includes('print'),false);
    assert.equal(a.avisos.length,1);
  }
});

test('fechar janela durante carregamento não força impressão',async()=>{
  let resolver;
  const a=ambiente({fetch:()=>new Promise(resolve=>resolver=resolve)});
  const resultado=a.contexto.cartoesGerarPDF('2026-10');
  a.janela.closed=true;
  resolver({ok:true,json:async()=>relatorio()});
  assert.equal(await resultado,false);
  assert.equal(a.eventos.includes('print'),false);
});
