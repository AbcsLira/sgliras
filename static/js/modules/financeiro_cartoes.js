// Cartões e recebíveis: lançamentos manuais, independentes do fechamento diário.
const CARTOES_OPERADORAS={
  cielo:{nome:'Cielo',cor:'#168bd2'},rede:{nome:'Rede',cor:'#f58220'},sipag:{nome:'Sipag',cor:'#19964b'}
};
const CARTOES_MODALIDADES={debito:'Débito',credito:'Crédito à vista',credito_2x:'Crédito em 2x',voucher:'Voucher'};
const cartoesEstado={
  configuracao:null,relatorio:null,vendas:[],versao:0,controlador:null,
  gravando:false,vendaId:null,parcela:null,acaoParcela:null,filtroExibido:null
};
let cartoesVendaOperacao=criarEstadoLote('cartoes-venda');

function cartoesEl(id){return document.getElementById(id);}
function cartoesEscapar(valor){
  return String(valor??'').replace(/[&<>"']/g,letra=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[letra]));
}
function cartoesDinheiro(centavos){return Number.isSafeInteger(centavos)?finFmt(centavos/100):'—';}
function cartoesData(data){return /^\d{4}-\d{2}-\d{2}$/.test(data||'')?data.split('-').reverse().join('/'):'—';}
function cartoesMes(mes){return /^\d{4}-\d{2}$/.test(mes||'')?mes.slice(5)+'/'+mes.slice(0,4):'—';}
function cartoesTaxa(taxa){
  if(taxa===null||taxa===undefined||taxa==='') return '—';
  const numero=Number(taxa);
  return Number.isFinite(numero)?numero.toLocaleString('pt-BR',{maximumFractionDigits:6})+'%':'—';
}
function cartoesId(valor){const id=Number(valor);return Number.isSafeInteger(id)&&id>0?id:null;}
function cartoesOperadora(id){
  const operadora=Object.hasOwn(CARTOES_OPERADORAS,id)?CARTOES_OPERADORAS[id]:null;
  return operadora?`<span class="cartoes-operadora cartoes-op-${id}">${operadora.nome}</span>`:'Operadora desconhecida';
}
function cartoesModalidade(id){return Object.hasOwn(CARTOES_MODALIDADES,id)?CARTOES_MODALIDADES[id]:'Modalidade desconhecida';}
function cartoesAviso(id,mensagem='',erro=true){
  const elemento=cartoesEl(id);
  elemento.textContent=mensagem;
  elemento.hidden=!mensagem;
  elemento.setAttribute('role',erro?'alert':'status');
}
function cartoesFiltros(){
  const mes=cartoesEl('cartoes-mes').value;
  const operadora=cartoesEl('cartoes-operadora').value;
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(mes)) throw new Error('Selecione um mês válido.');
  if(operadora&&!Object.hasOwn(CARTOES_OPERADORAS,operadora)) throw new Error('Selecione uma operadora válida.');
  return {mes,operadora};
}
function cartoesConsulta(filtros){
  const consulta=new URLSearchParams({mes:filtros.mes});
  if(filtros.operadora) consulta.set('operadora',filtros.operadora);
  return consulta.toString();
}
async function cartoesRequisitar(url,opcoes={}){
  const resposta=await fetch('/api/fin/cartoes'+url,opcoes);
  let dados;
  try{dados=await resposta.json();}catch(erro){throw new Error('O servidor enviou uma resposta incompleta. Tente novamente.');}
  if(!resposta.ok||dados?.erro) throw new Error(dados?.erro||'Não foi possível concluir a operação. Tente novamente.');
  if(opcoes.method&&opcoes.method!=='GET'&&dados?.ok!==true) throw new Error('A alteração não foi confirmada. Tente novamente.');
  return dados;
}
function cartoesTrocarAba(aba){
  if(!['recebiveis','vendas','condicoes'].includes(aba)) return;
  for(const nome of ['recebiveis','vendas','condicoes']) cartoesEl('cartoes-painel-'+nome).hidden=nome!==aba;
  document.querySelectorAll('[data-cartoes-aba]').forEach(botao=>{
    const ativo=botao.dataset.cartoesAba===aba;
    botao.classList.toggle('active',ativo);
    botao.setAttribute('aria-selected',String(ativo));
  });
}
async function cartoesIniciar(){
  if(me.perfil!=='admin'){
    cartoesAviso('cartoes-aviso','Somente administradores podem acessar os cartões e recebíveis.');
    return false;
  }
  if(!cartoesEl('cartoes-mes').value) cartoesEl('cartoes-mes').value=hojeLocal().slice(0,7);
  return cartoesAtualizar();
}
async function cartoesAtualizar(){
  const versao=++cartoesEstado.versao;
  cartoesEstado.controlador?.abort();
  cartoesEstado.controlador=null;
  cartoesEl('page-fin-cartoes').setAttribute('aria-busy','false');
  let filtros;
  try{filtros=cartoesFiltros();}catch(erro){
    const anterior=cartoesEstado.filtroExibido;
    cartoesAviso('cartoes-aviso',erro.message+(anterior?` Os dados visíveis ainda são da consulta ${cartoesMes(anterior.mes)} (${anterior.operadora?CARTOES_OPERADORAS[anterior.operadora].nome:'todas as operadoras'}).`:''));
    cartoesEl('cartoes-estado').textContent='Consulta interrompida. Corrija os filtros para atualizar.';
    return false;
  }
  const controlador=new AbortController();
  cartoesEstado.controlador=controlador;
  cartoesAviso('cartoes-aviso');
  cartoesEl('cartoes-estado').textContent='Carregando cartões e recebíveis…';
  cartoesEl('page-fin-cartoes').setAttribute('aria-busy','true');
  try{
    const consulta=cartoesConsulta(filtros);
    const [configuracao,vendas,relatorio]=await Promise.all([
      cartoesRequisitar('/configuracao',{signal:controlador.signal}),
      cartoesRequisitar('/vendas?'+consulta,{signal:controlador.signal}),
      cartoesRequisitar('/relatorio?'+consulta,{signal:controlador.signal})
    ]);
    if(versao!==cartoesEstado.versao) return false;
    if(!Array.isArray(configuracao?.condicoes)||!Array.isArray(vendas)||!Array.isArray(relatorio?.parcelas)||
       !Array.isArray(relatorio?.agenda_mensal)||!relatorio.resumo) throw new Error('Os dados recebidos estão incompletos. Tente atualizar novamente.');
    Object.assign(cartoesEstado,{configuracao,vendas,relatorio,filtroExibido:filtros});
    cartoesRenderizar();
    cartoesEl('cartoes-estado').textContent=`Consulta: ${cartoesMes(filtros.mes)} · ${filtros.operadora?CARTOES_OPERADORAS[filtros.operadora].nome:'Todas as operadoras'}. Vendas pela data da venda; recebíveis pela previsão.`;
    return true;
  }catch(erro){
    if(versao!==cartoesEstado.versao||erro.name==='AbortError') return false;
    const anterior=cartoesEstado.filtroExibido;
    cartoesAviso('cartoes-aviso',(erro.message||'Falha de conexão. Tente novamente.')+
      (anterior?` Os dados visíveis ainda são da consulta ${cartoesMes(anterior.mes)} (${anterior.operadora?CARTOES_OPERADORAS[anterior.operadora].nome:'todas as operadoras'}).`:''));
    cartoesEl('cartoes-estado').textContent='Não foi possível atualizar. Use Atualizar para tentar novamente.';
    return false;
  }finally{
    if(versao===cartoesEstado.versao){
      cartoesEstado.controlador=null;
      cartoesEl('page-fin-cartoes').setAttribute('aria-busy','false');
    }
  }
}
function cartoesRecebida(parcela){
  return parcela.status==='recebido'||parcela.status==='divergente'||
    (parcela.valor_recebido_centavos!==null&&parcela.valor_recebido_centavos!==undefined);
}
function cartoesStatus(parcela){
  if(parcela.status==='divergente') return '<span class="cartoes-status cartoes-status-divergente">Recebido com diferença</span>';
  if(cartoesRecebida(parcela)) return '<span class="cartoes-status cartoes-status-recebido">Recebido</span>';
  const atrasada=parcela.data_prevista<hojeLocal();
  return `<span class="cartoes-status ${atrasada?'cartoes-status-atrasado':'cartoes-status-pendente'}">${atrasada?'Em atraso':'Em aberto'}</span>`;
}
function cartoesRenderizar(){
  const relatorio=cartoesEstado.relatorio;
  const resumo=relatorio.resumo;
  const cartoes=[['Bruto previsto',resumo.bruto_centavos],['Taxas previstas',resumo.taxas_centavos],
    ['Líquido previsto',resumo.previsto_centavos],['Saldo em aberto',resumo.saldo_centavos],
    ['Recebido no mês (data real)',resumo.recebido_no_mes_centavos],['Diferença nas parcelas do mês',resumo.diferenca_centavos]];
  cartoesEl('cartoes-resumo').innerHTML=cartoes.map(([titulo,valor])=>
    `<div class="cartoes-resumo-card"><span class="cartoes-resumo-rotulo">${titulo}</span><strong class="cartoes-valor">${cartoesDinheiro(valor)}</strong></div>`).join('');
  const pendentes=relatorio.pendentes_configuracao;
  cartoesEl('cartoes-pendentes').innerHTML=pendentes?.quantidade
    ? `<div class="cartoes-pendencia"><strong>${cartoesEscapar(pendentes.quantidade)} venda(s) sem condição: ${cartoesDinheiro(pendentes.bruto_centavos)}.</strong> Não há datas, parcelas ou valor líquido estimados para essas vendas. A contagem inclui todos os meses da operadora selecionada. Cadastre as condições e use <button type="button" class="btn btn-ghost btn-sm" onclick="cartoesCalcularPendentes()">Calcular pendentes</button>.</div>`:'';
  cartoesEl('cartoes-por-operadora').innerHTML=(relatorio.por_operadora||[]).map(item=>
    `<div class="cartoes-operadora-card ${Object.hasOwn(CARTOES_OPERADORAS,item.operadora_id)?'cartoes-op-'+item.operadora_id:''}">${cartoesOperadora(item.operadora_id)}<dl><dt>Líquido previsto</dt><dd>${cartoesDinheiro(item.previsto_centavos)}</dd><dt>Saldo em aberto</dt><dd>${cartoesDinheiro(item.saldo_centavos)}</dd><dt>Recebido no mês</dt><dd>${cartoesDinheiro(item.recebido_no_mes_centavos)}</dd></dl></div>`).join('');
  cartoesEl('cartoes-parcelas').innerHTML=relatorio.parcelas.map(parcela=>{
    const id=cartoesId(parcela.id),recebida=cartoesRecebida(parcela);
    const acoes=id?(recebida
      ? `<button type="button" class="btn btn-ghost btn-sm" onclick="cartoesEstornar(${id})">Estornar recebimento</button>`
      : `<button type="button" class="btn btn-primary btn-sm" onclick="cartoesAbrirRecebimento(${id})">Receber</button> <button type="button" class="btn btn-ghost btn-sm" onclick="cartoesAbrirPrevisao(${id})">Ajustar data</button>`):'';
    return `<tr><td>${cartoesData(parcela.data_prevista)}</td><td>${cartoesOperadora(parcela.operadora_id)}</td><td>${cartoesEscapar(cartoesModalidade(parcela.modalidade))}${parcela.bandeira?`<small>${cartoesEscapar(parcela.bandeira)}</small>`:''}</td>
      <td>${cartoesData(parcela.data_venda)}</td><td>${cartoesEscapar(parcela.parcela)}/${cartoesEscapar(parcela.total_parcelas)}</td>
      <td>${cartoesDinheiro(parcela.bruto_centavos)}</td><td>${cartoesDinheiro(parcela.taxa_centavos)}</td><td>${cartoesDinheiro(parcela.liquido_centavos)}</td>
      <td>${recebida?`${cartoesDinheiro(parcela.valor_recebido_centavos)}<small>${cartoesData(parcela.data_recebimento)}</small>`:'—'}</td>
      <td>${cartoesStatus(parcela)}</td><td>${cartoesDinheiro(parcela.diferenca_centavos)}</td><td><div class="cartoes-acoes">${acoes}</div></td></tr>`;
  }).join('')||'<tr><td colspan="12" class="empty">Nenhuma parcela prevista neste mês.</td></tr>';
  cartoesEl('cartoes-agenda').innerHTML=relatorio.agenda_mensal.map(item=>
    `<tr><td>${cartoesMes(item.mes)}</td><td>${cartoesDinheiro(item.previsto_centavos)}</td><td>${cartoesDinheiro(item.saldo_centavos)}</td><td>${cartoesDinheiro(item.recebido_no_mes_centavos)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">Sem previsões ou recebimentos cadastrados.</td></tr>';
  cartoesRenderizarVendas();
  cartoesRenderizarCondicoes();
}
function cartoesVendaTemRecebimento(venda){
  return !!venda.possui_recebimento||(cartoesEstado.relatorio?.parcelas||[]).some(p=>p.venda_id===venda.id&&cartoesRecebida(p));
}
function cartoesRenderizarVendas(){
  cartoesEl('cartoes-vendas-lista').innerHTML=cartoesEstado.vendas.map(venda=>{
    const id=cartoesId(venda.id),bloqueada=cartoesVendaTemRecebimento(venda);
    const acoes=bloqueada?'Estorne os recebimentos antes de corrigir a venda.':id?
      `<button type="button" class="btn btn-ghost btn-sm" onclick="cartoesEditarVenda(${id})">Editar</button> <button type="button" class="btn btn-danger btn-sm" onclick="cartoesExcluirVenda(${id})">Excluir</button>`:'';
    return `<tr><td>${cartoesData(venda.data_venda)}</td><td>${cartoesOperadora(venda.operadora_id)}</td><td>${cartoesEscapar(cartoesModalidade(venda.modalidade))}</td>
      <td>${cartoesEscapar(venda.bandeira||'Padrão')}</td><td>${cartoesDinheiro(venda.bruto_centavos)}</td><td>${cartoesTaxa(venda.taxa_percentual)}</td>
      <td>${venda.calculado?'Calculada':'Sem condição vigente'}</td><td>${cartoesEscapar(venda.observacao)}</td><td><div class="cartoes-acoes">${acoes}</div></td></tr>`;
  }).join('')||'<tr><td colspan="9" class="empty">Nenhum total diário lançado neste mês.</td></tr>';
}
function cartoesRenderizarCondicoes(){
  cartoesEl('cartoes-condicoes-lista').innerHTML=cartoesEstado.configuracao.condicoes.map(condicao=>{
    const id=cartoesId(condicao.id);
    return `<tr><td>${cartoesOperadora(condicao.operadora_id)}</td><td>${cartoesEscapar(cartoesModalidade(condicao.modalidade))}</td><td>${cartoesEscapar(condicao.bandeira||'Padrão')}</td>
      <td>${cartoesData(condicao.inicio_vigencia)}</td><td>${cartoesTaxa(condicao.taxa_percentual)}</td><td>${cartoesEscapar(condicao.prazo_dias)} dias ${condicao.tipo_dias==='uteis'?'úteis':'corridos'}</td>
      <td>${condicao.modalidade==='credito_2x'?cartoesEscapar(condicao.intervalo_parcelas_dias)+' dias':'—'}</td><td>${id?`<button type="button" class="btn btn-ghost btn-sm" onclick="cartoesEditarCondicao(${id})">Editar condição</button>`:''}</td></tr>`;
  }).join('')||'<tr><td colspan="8" class="empty">Nenhuma condição cadastrada. Informe suas taxas e prazos contratados.</td></tr>';
}
function cartoesBloquear(id){
  const elementos=Array.from(cartoesEl(id).querySelectorAll('button,input,select,textarea'));
  const estados=elementos.map(elemento=>elemento.disabled);
  elementos.forEach(elemento=>elemento.disabled=true);
  cartoesEl(id).setAttribute('aria-busy','true');
  return ()=>{
    elementos.forEach((elemento,indice)=>elemento.disabled=estados[indice]);
    cartoesEl(id).setAttribute('aria-busy','false');
  };
}
async function cartoesGravar(formulario,aviso,acao){
  if(cartoesEstado.gravando) return null;
  cartoesEstado.gravando=true;
  cartoesEstado.versao++;
  if(cartoesEstado.controlador) cartoesEl('cartoes-estado').textContent='Consulta interrompida para salvar. Use Atualizar para consultar novamente.';
  cartoesEstado.controlador?.abort();
  cartoesEstado.controlador=null;
  cartoesEl('page-fin-cartoes').setAttribute('aria-busy','false');
  const desbloquear=cartoesBloquear(formulario);
  cartoesAviso(aviso);
  try{return await acao();}
  catch(erro){cartoesAviso(aviso,erro.message||'Falha de conexão. Tente novamente.');return null;}
  finally{cartoesEstado.gravando=false;desbloquear();}
}
function cartoesValor(id){return cartoesEl(id).value.trim();}
function cartoesDecimal(id,nome,{zero=false,maximo=10000000,casas=2}={}){
  const valor=cartoesValor(id).replace(',','.');
  if(!new RegExp(`^\\d+(?:\\.\\d{1,${casas}})?$`).test(valor)||!Number.isFinite(Number(valor))||
    Number(valor)<0||(!zero&&Number(valor)===0)||Number(valor)>maximo) throw new Error(`Informe ${nome} válido${zero?' (zero é permitido)':''}.`);
  return valor;
}
function cartoesDataObrigatoria(id){
  const valor=cartoesValor(id);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(valor)) throw new Error('Informe uma data válida.');
  return valor;
}
function cartoesEscolhas(operadora,modalidade){
  if(!Object.hasOwn(CARTOES_OPERADORAS,operadora)||!Object.hasOwn(CARTOES_MODALIDADES,modalidade))
    throw new Error('Selecione a operadora e a modalidade.');
}
function cartoesMostrarEditor(id){cartoesEl(id).hidden=false;cartoesEl(id).scrollIntoView?.({block:'nearest',behavior:'smooth'});}
function cartoesNovaVenda(){
  if(cartoesEstado.gravando) return;
  cartoesTrocarAba('vendas');
  recuperarOperacaoPendente(cartoesVendaOperacao);
  cartoesEstado.vendaId=null;
  cartoesEl('cartoes-venda-formulario').noValidate=cartoesVendaOperacao.incerta;
  if(cartoesVendaOperacao.incerta){
    cartoesAviso('cartoes-venda-aviso','Há uma venda anterior sem confirmação. Salve novamente para recuperar o resultado; alterações atuais não serão enviadas.');
    cartoesMostrarEditor('cartoes-venda-editor');
    return;
  }
  cartoesVendaOperacao=criarEstadoLote('cartoes-venda');
  cartoesEl('cartoes-venda-titulo').textContent='Novo total diário';
  for(const campo of ['operadora','modalidade','bandeira','valor','observacao']) cartoesEl('cartoes-venda-'+campo).value='';
  cartoesEl('cartoes-venda-data').value=hojeLocal();
  cartoesAviso('cartoes-venda-aviso');
  cartoesMostrarEditor('cartoes-venda-editor');
}
function cartoesFecharVenda(){if(!cartoesEstado.gravando) cartoesEl('cartoes-venda-editor').hidden=true;}
function cartoesEditarVenda(id){
  if(cartoesEstado.gravando) return;
  recuperarOperacaoPendente(cartoesVendaOperacao);
  if(cartoesVendaOperacao.incerta){cartoesNovaVenda();return;}
  const venda=cartoesEstado.vendas.find(item=>item.id===id);
  if(!venda) return;
  if(cartoesVendaTemRecebimento(venda)){cartoesAviso('cartoes-aviso','Estorne os recebimentos antes de editar esta venda.');return;}
  cartoesEstado.vendaId=id;
  cartoesEl('cartoes-venda-formulario').noValidate=false;
  cartoesEl('cartoes-venda-titulo').textContent='Editar total diário';
  for(const [campo,valor] of Object.entries({operadora:venda.operadora_id,modalidade:venda.modalidade,
    bandeira:venda.bandeira||'',data:venda.data_venda,valor:(venda.bruto_centavos/100).toFixed(2),observacao:venda.observacao||''}))
    cartoesEl('cartoes-venda-'+campo).value=valor;
  cartoesAviso('cartoes-venda-aviso');
  cartoesMostrarEditor('cartoes-venda-editor');
}
async function cartoesSalvarVenda(evento){
  evento?.preventDefault();
  if(cartoesEstado.gravando) return false;
  recuperarOperacaoPendente(cartoesVendaOperacao);
  let payload;
  try{
    if(!cartoesEstado.vendaId&&cartoesVendaOperacao.incerta) payload=cartoesVendaOperacao.payloadOriginal;
    else{
      if(cartoesEl('cartoes-venda-formulario').reportValidity?.()===false) return false;
      const operadora_id=cartoesValor('cartoes-venda-operadora'),modalidade=cartoesValor('cartoes-venda-modalidade');
      cartoesEscolhas(operadora_id,modalidade);
      payload={operadora_id,modalidade,bandeira:cartoesValor('cartoes-venda-bandeira'),
        data_venda:cartoesDataObrigatoria('cartoes-venda-data'),valor_bruto:cartoesDecimal('cartoes-venda-valor','um valor bruto'),
        observacao:cartoesValor('cartoes-venda-observacao')};
    }
  }catch(erro){cartoesAviso('cartoes-venda-aviso',erro.message);return false;}
  const id=cartoesEstado.vendaId;
  const resultado=await cartoesGravar('cartoes-venda-formulario','cartoes-venda-aviso',()=>id
    ?cartoesRequisitar('/vendas/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    :enviarOperacaoAtomica(cartoesVendaOperacao,'/api/fin/cartoes/vendas',payload,'cartoes-venda-editor'));
  if(!resultado){
    cartoesEl('cartoes-venda-formulario').noValidate=cartoesVendaOperacao.incerta;
    if(!cartoesEl('cartoes-venda-aviso').textContent) cartoesAviso('cartoes-venda-aviso',cartoesVendaOperacao.incerta
      ?'A venda anterior está sem confirmação. Salve novamente para recuperar o resultado; não será criado outro lançamento.'
      :'A venda não foi confirmada. Confira os dados e tente novamente.');
    return false;
  }
  cartoesFecharVenda();
  toast(resultado.tentativaAnterior?'Venda anterior confirmada. Alterações atuais não foram enviadas.':resultado.calculado===false?'Total salvo sem condição vigente. Cadastre taxas e prazos e calcule as pendências.':'Total diário salvo.');
  await cartoesAtualizar();
  return true;
}
async function cartoesExcluirVenda(id){
  const venda=cartoesEstado.vendas.find(item=>item.id===id);
  if(!venda||cartoesEstado.gravando) return false;
  if(cartoesVendaTemRecebimento(venda)){cartoesAviso('cartoes-aviso','Estorne os recebimentos antes de excluir esta venda.');return false;}
  if(!confirm('Excluir este total diário e suas parcelas ainda não recebidas?')) return false;
  const resultado=await cartoesGravar('page-fin-cartoes','cartoes-aviso',()=>cartoesRequisitar('/vendas/'+id,{method:'DELETE'}));
  if(!resultado) return false;
  if(cartoesEstado.vendaId===id) cartoesFecharVenda();
  await cartoesAtualizar();
  toast('Total diário excluído.');
  return true;
}
function cartoesNovaCondicao(){
  if(cartoesEstado.gravando) return;
  cartoesTrocarAba('condicoes');
  cartoesEl('cartoes-condicao-titulo').textContent='Nova condição de taxas e prazos';
  for(const campo of ['operadora','modalidade','bandeira','taxa','prazo','tipo','intervalo']) cartoesEl('cartoes-condicao-'+campo).value='';
  cartoesEl('cartoes-condicao-inicio').value=hojeLocal();
  cartoesAlternarIntervalo();
  cartoesAviso('cartoes-condicao-aviso');
  cartoesMostrarEditor('cartoes-condicao-editor');
}
function cartoesFecharCondicao(){if(!cartoesEstado.gravando) cartoesEl('cartoes-condicao-editor').hidden=true;}
function cartoesAlternarIntervalo(){
  const duas=cartoesValor('cartoes-condicao-modalidade')==='credito_2x';
  cartoesEl('cartoes-condicao-intervalo-grupo').hidden=!duas;
  cartoesEl('cartoes-condicao-intervalo').disabled=!duas;
  cartoesEl('cartoes-condicao-intervalo').required=duas;
}
function cartoesEditarCondicao(id){
  if(cartoesEstado.gravando) return;
  const condicao=cartoesEstado.configuracao?.condicoes.find(item=>item.id===id);
  if(!condicao) return;
  cartoesEl('cartoes-condicao-titulo').textContent='Editar condição para novos lançamentos';
  for(const [campo,valor] of Object.entries({operadora:condicao.operadora_id,modalidade:condicao.modalidade,
    bandeira:condicao.bandeira||'',inicio:condicao.inicio_vigencia,taxa:condicao.taxa_percentual,
    prazo:condicao.prazo_dias,tipo:condicao.tipo_dias,intervalo:condicao.intervalo_parcelas_dias??''}))
    cartoesEl('cartoes-condicao-'+campo).value=valor;
  cartoesAlternarIntervalo();
  cartoesAviso('cartoes-condicao-aviso','Vendas calculadas preservam a condição original. Alterar o início cria uma nova vigência.',false);
  cartoesMostrarEditor('cartoes-condicao-editor');
}
function cartoesInteiroCampo(id,nome,minimo=0){
  const texto=cartoesValor(id),numero=Number(texto);
  if(!texto||!Number.isInteger(numero)||numero<minimo||numero>365) throw new Error(`Informe ${nome} em dias inteiros, de ${minimo} a 365.`);
  return numero;
}
async function cartoesSalvarCondicao(evento){
  evento?.preventDefault();
  if(cartoesEstado.gravando) return false;
  let payload;
  try{
    if(cartoesEl('cartoes-condicao-formulario').reportValidity?.()===false) return false;
    const operadora_id=cartoesValor('cartoes-condicao-operadora'),modalidade=cartoesValor('cartoes-condicao-modalidade');
    cartoesEscolhas(operadora_id,modalidade);
    const tipo_dias=cartoesValor('cartoes-condicao-tipo');
    if(!['corridos','uteis'].includes(tipo_dias)) throw new Error('Selecione dias corridos ou úteis.');
    payload={operadora_id,modalidade,bandeira:cartoesValor('cartoes-condicao-bandeira'),
      inicio_vigencia:cartoesDataObrigatoria('cartoes-condicao-inicio'),
      taxa_percentual:cartoesDecimal('cartoes-condicao-taxa','uma taxa',{zero:true,maximo:100,casas:6}),
      prazo_dias:cartoesInteiroCampo('cartoes-condicao-prazo','o prazo'),tipo_dias,
      intervalo_parcelas_dias:modalidade==='credito_2x'?cartoesInteiroCampo('cartoes-condicao-intervalo','o intervalo',1):null};
  }catch(erro){cartoesAviso('cartoes-condicao-aviso',erro.message);return false;}
  const resultado=await cartoesGravar('cartoes-condicao-formulario','cartoes-condicao-aviso',()=>cartoesRequisitar('/condicoes',
    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}));
  if(!resultado) return false;
  cartoesFecharCondicao();
  await cartoesAtualizar();
  toast('Condição salva. O histórico calculado foi preservado; pendências exigem cálculo explícito.');
  return true;
}
async function cartoesCalcularPendentes(){
  if(cartoesEstado.gravando) return false;
  const resultado=await cartoesGravar('page-fin-cartoes','cartoes-aviso',()=>cartoesRequisitar('/vendas/calcular-pendentes',{method:'POST'}));
  if(!resultado) return false;
  await cartoesAtualizar();
  toast(`${resultado.calculadas} venda(s) calculada(s); ${resultado.pendentes} ainda sem condição.`);
  return true;
}
function cartoesAbrirParcela(id,acao){
  if(cartoesEstado.gravando) return;
  const parcela=cartoesEstado.relatorio?.parcelas.find(item=>item.id===id);
  if(!parcela||cartoesRecebida(parcela)) return;
  cartoesEstado.parcela=parcela;
  cartoesEstado.acaoParcela=acao;
  cartoesEl('cartoes-parcela-titulo').textContent=acao==='recebimento'?'Registrar recebimento':'Ajustar data prevista';
  cartoesEl('cartoes-parcela-detalhe').textContent=`${CARTOES_OPERADORAS[parcela.operadora_id]?.nome||''} · ${cartoesModalidade(parcela.modalidade)} · parcela ${parcela.parcela}/${parcela.total_parcelas} · líquido previsto ${cartoesDinheiro(parcela.liquido_centavos)}`;
  for(const [grupo,ativo] of [['cartoes-recebimento-campos',acao==='recebimento'],['cartoes-previsao-campos',acao==='previsao']]){
    cartoesEl(grupo).hidden=!ativo;
    cartoesEl(grupo).querySelectorAll('input,textarea,button').forEach(campo=>campo.disabled=!ativo);
  }
  cartoesEl('cartoes-recebimento-data').value=hojeLocal();
  cartoesEl('cartoes-recebimento-valor').value='';
  cartoesEl('cartoes-recebimento-observacao').value='';
  cartoesEl('cartoes-previsao-data').value=parcela.data_prevista;
  cartoesAviso('cartoes-parcela-aviso');
  cartoesMostrarEditor('cartoes-parcela-editor');
}
function cartoesAbrirRecebimento(id){cartoesAbrirParcela(id,'recebimento');}
function cartoesAbrirPrevisao(id){cartoesAbrirParcela(id,'previsao');}
function cartoesUsarPrevisto(){
  if(cartoesEstado.parcela&&!cartoesEstado.gravando)
    cartoesEl('cartoes-recebimento-valor').value=(cartoesEstado.parcela.liquido_centavos/100).toFixed(2);
}
function cartoesFecharParcela(){if(!cartoesEstado.gravando) cartoesEl('cartoes-parcela-editor').hidden=true;}
async function cartoesSalvarParcela(evento){
  evento?.preventDefault();
  if(cartoesEstado.gravando||!cartoesEstado.parcela) return false;
  const id=cartoesEstado.parcela.id,recebimento=cartoesEstado.acaoParcela==='recebimento';
  let payload;
  try{
    if(cartoesEl('cartoes-parcela-formulario').reportValidity?.()===false) return false;
    payload=recebimento?{data_recebimento:cartoesDataObrigatoria('cartoes-recebimento-data'),
      valor_recebido:cartoesDecimal('cartoes-recebimento-valor','um valor recebido',{zero:true}),
      observacao:cartoesValor('cartoes-recebimento-observacao')}
      :{data_prevista:cartoesDataObrigatoria('cartoes-previsao-data')};
  }catch(erro){cartoesAviso('cartoes-parcela-aviso',erro.message);return false;}
  const resultado=await cartoesGravar('cartoes-parcela-formulario','cartoes-parcela-aviso',()=>cartoesRequisitar(
    `/parcelas/${id}/${recebimento?'recebimento':'previsao'}`,
    {method:recebimento?'POST':'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}));
  if(!resultado) return false;
  cartoesFecharParcela();
  await cartoesAtualizar();
  toast(recebimento?'Recebimento registrado. Diferenças são mostradas separadamente.':'Previsão atualizada.');
  return true;
}
async function cartoesEstornar(id){
  if(cartoesEstado.gravando||!confirm('Estornar este recebimento e reabrir a parcela? O histórico da alteração será preservado.')) return false;
  const resultado=await cartoesGravar('page-fin-cartoes','cartoes-aviso',()=>cartoesRequisitar(`/parcelas/${id}/recebimento`,{method:'DELETE'}));
  if(!resultado) return false;
  await cartoesAtualizar();
  toast('Recebimento estornado; a parcela voltou a ficar em aberto.');
  return true;
}
