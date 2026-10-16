// ═══════════════════════════════════════
// Movimentações
// ═══════════════════════════════════════
// Compartilhado pelos formulários de lote: a mesma tentativa conserva o ID
// mesmo quando a resposta se perde, para o servidor não repetir a gravação.
function criarEstadoLote(tipo){
  return {tipo,enviando:false,incerta:false,conteudo:null,operacaoId:null,payloadOriginal:null,recuperada:false};
}

function chaveOperacaoPendente(estado){
  const usuarioId=typeof me!=='undefined'&&me.id;
  return usuarioId&&estado.tipo ? `sgliras:operacao-pendente:${usuarioId}:${estado.tipo}` : null;
}

function recuperarOperacaoPendente(estado){
  if(estado.recuperada) return;
  const chave=chaveOperacaoPendente(estado);
  if(!chave) return;
  estado.recuperada=true;
  try{
    const salva=JSON.parse(sessionStorage.getItem(chave));
    if(salva&&typeof salva.operacaoId==='string'&&typeof salva.conteudo==='string'){
      const payload=JSON.parse(salva.conteudo);
      const formatoValido=estado.tipo==='movimentacao'
        ? payload&&Number.isInteger(payload.produto_id)&&typeof payload.tipo==='string'
        : payload&&Array.isArray(payload.itens)&&payload.itens.length>0;
      if(formatoValido){
        Object.assign(estado,{incerta:true,operacaoId:salva.operacaoId,conteudo:salva.conteudo,payloadOriginal:payload});
      }
    }
  } catch(erro){/* Armazenamento indisponível: conservar a proteção em memória. */}
}

function persistirOperacaoPendente(estado){
  const chave=chaveOperacaoPendente(estado);
  if(!chave) return;
  try{
    if(estado.incerta) sessionStorage.setItem(chave,JSON.stringify({operacaoId:estado.operacaoId,conteudo:estado.conteudo}));
    else sessionStorage.removeItem(chave);
  } catch(erro){/* Navegadores que bloqueiam armazenamento continuam usando memória. */}
}

function reabrirOperacaoPendente(estado,modalId){
  recuperarOperacaoPendente(estado);
  if(!estado.incerta) return false;
  document.getElementById(modalId).classList.remove('hidden');
  toast('Há uma tentativa anterior sem confirmação. Confirme novamente para recuperar o resultado antes de cadastrar outra operação.','var(--danger)');
  return true;
}

function criarIdOperacao(){
  if(globalThis.crypto.randomUUID) return crypto.randomUUID();
  // randomUUID exige HTTPS em alguns navegadores; getRandomValues também
  // funciona no HTTP usado pela aplicação na rede local.
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64;
  bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

function bloquearControlesModal(modalId){
  const controles=Array.from(document.getElementById(modalId).querySelectorAll('button, input, select, textarea'));
  const estados=controles.map(c=>c.disabled);
  controles.forEach(c=>c.disabled=true);
  return ()=>controles.forEach((c,i)=>c.disabled=estados[i]);
}

async function enviarOperacaoAtomica(estado,url,payload,modalId){
  if(estado.enviando) return false;
  recuperarOperacaoPendente(estado);
  estado.enviando=true;
  const desbloquear=bloquearControlesModal(modalId);
  try{
    const confirmandoAnterior=estado.incerta;
    if(confirmandoAnterior){
      payload=estado.payloadOriginal;
      toast('Confirmando tentativa anterior; alterações atuais não foram enviadas.');
    }
    const conteudo=JSON.stringify(payload);
    if(!estado.incerta&&estado.conteudo!==conteudo){
      const operacaoId=criarIdOperacao();
      estado.conteudo=conteudo;
      estado.operacaoId=operacaoId;
      estado.payloadOriginal=JSON.parse(conteudo);
    }
    // Persistir antes do envio também cobre recarregar a página com o POST em andamento.
    estado.incerta=true;
    persistirOperacaoPendente(estado);
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...estado.payloadOriginal,operacao_id:estado.operacaoId})});
    const d=await r.json();
    if(!r.ok||d.erro||d.ok!==true){
      // Autenticação e conflito não esclarecem se uma tentativa anterior foi gravada.
      if([400,404,422].includes(r.status)||(r.status===409&&d.codigo==='integridade')) estado.incerta=false;
      persistirOperacaoPendente(estado);
      toast(d.erro||'Não foi possível salvar a operação. Tente novamente.','var(--danger)');
      return false;
    }
    estado.incerta=false;
    persistirOperacaoPendente(estado);
    return {...d,tentativaAnterior:confirmandoAnterior};
  } catch(erro){
    toast('Não foi possível confirmar a operação. Verifique a conexão e tente novamente; a tentativa anterior será confirmada antes de enviar alterações.','var(--danger)');
    return false;
  } finally{
    estado.enviando=false;
    desbloquear();
  }
}

async function carregarMovimentacoes(){
  const movs=await fetch('/api/movimentacoes').then(r=>r.json());
  if(!produtos.length) produtos=await fetch('/api/produtos').then(r=>r.json());
  renderMovs(movs); window._movs=movs;
}
function renderMovs(movs){
  const lista=filtroTipo?movs.filter(m=>m.tipo===filtroTipo):movs;
  const tbody=document.getElementById('t-movs');
  if(!lista.length){tbody.innerHTML='<tr><td colspan="8" class="empty">Nenhuma movimentação</td></tr>';return;}
  const cores={entrada:'badge-ok',saida:'badge-danger',ajuste:'badge-warn'};
  tbody.innerHTML=lista.map(m=>`<tr>
    <td>${new Date(m.criado_em).toLocaleString('pt-BR')}</td>
    <td>${m.produto}</td><td><code>${m.codigo}</code></td>
    <td><span class="badge badge-unit">${m.unidade||'un'}</span></td>
    <td><span class="badge ${cores[m.tipo]}">${m.tipo}</span></td>
    <td>${m.quantidade}</td><td>${m.usuario_nome||'—'}</td><td>${m.observacao||'—'}</td>
  </tr>`).join('');
}
document.querySelectorAll('.tipo-tab').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.tipo-tab').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active'); filtroTipo=btn.dataset.tipo;
    if(window._movs) renderMovs(window._movs);
  });
});
let movCatFiltro=null;
let movEstado=criarEstadoLote('movimentacao');
const LIMITE_RESULTADOS_SELETOR=50;

function produtoCorrespondeBusca(produto,busca){
  return [produto.nome,produto.codigo,produto.codigo_barras]
    .some(valor=>String(valor??'').toLowerCase().includes(busca));
}

function avisoLimiteSeletor(total){
  return total>LIMITE_RESULTADOS_SELETOR
    ? `<div role="status" style="padding:9px;color:var(--muted);font-size:12px">Mostrando ${LIMITE_RESULTADOS_SELETOR} de ${total}. Refine a busca.</div>`
    : '';
}

function construirMovCatChips(){
  const el=document.getElementById('mov-cat-chips');
  const cats=[...new Set(produtos.map(p=>p.categoria).filter(Boolean))].sort();
  el.innerHTML=`<span class="filter-chip ${movCatFiltro===null?'active':''}"
    onclick="setMovCat(null)">Todas</span>`+
    cats.map(c=>`<span class="filter-chip ${movCatFiltro===c?'active':''}"
      onclick="setMovCat('${c}')">${c}</span>`).join('');
}

function setMovCat(cat){
  movCatFiltro=cat;
  construirMovCatChips();
  filtrarMovBusca();
}

const filtrarMovBuscaAoDigitar=adiarBusca(filtrarMovBusca);
function filtrarMovBusca(){
  filtrarMovBuscaAoDigitar.cancelar();
  const q=document.getElementById('mov-busca').value.trim().toLowerCase();
  const lista=document.getElementById('mov-lista');
  let itens=produtos.filter(p=>p.ativo!==0);
  if(movCatFiltro) itens=itens.filter(p=>p.categoria===movCatFiltro);
  if(q) itens=itens.filter(p=>produtoCorrespondeBusca(p,q));
  if(!itens.length){lista.innerHTML='<div style="padding:9px;color:var(--muted);font-size:12px">Nenhum produto encontrado</div>';return;}
  lista.innerHTML=avisoLimiteSeletor(itens.length)+itens.slice(0,LIMITE_RESULTADOS_SELETOR).map(p=>`<div class="p-opt" onclick="selecionarMovProd(${p.id})">
    <div>
      <div class="pn">${p.nome}</div>
      <div class="pi">${p.codigo} · <span class="badge badge-unit">${p.unidade||'un'}</span>${p.categoria?' · <span class="badge badge-cat" style="font-size:10px">'+p.categoria+'</span>':''}</div>
    </div>
    <div class="pq">Qtd: ${p.quantidade}</div></div>`).join('');
}
let movModoEmbalagem=false;

function selecionarMovProd(id){
  const p=produtos.find(x=>x.id===id);if(!p)return;
  movProdId=id;
  movModoEmbalagem=false;
  movRenderSelLabel();
  document.getElementById('mov-sel-wrap').classList.remove('hidden');
  document.getElementById('mov-busca-wrap').classList.add('hidden');
  movAtualizarPreview();
}

function movRenderSelLabel(){
  const p=produtos.find(x=>x.id===movProdId);if(!p)return;
  const temConversao=p.unid_por_fardo>0;
  const unLabel=movModoEmbalagem?(p.unid_fardo_label||'fd'):(p.unidade||'un');
  const badgeStyle=temConversao
    ? 'cursor:pointer;border:1px dashed var(--accent);'
    : '';
  const badgeTitle=temConversao
    ? `title="Clique para alternar entre ${p.unidade||'un'} e ${p.unid_fardo_label||'fd'} (1 ${p.unid_fardo_label||'fd'} = ${p.unid_por_fardo} ${p.unidade||'un'})"`
    : '';
  document.getElementById('mov-sel-label').innerHTML=
    `<strong>${p.nome}</strong> &nbsp;<code>${p.codigo}</code>
     &nbsp;<span class="badge badge-unit" style="${badgeStyle}" ${badgeTitle} onclick="movToggleModo(event)">${unLabel}${temConversao?' ⇄':''}</span>
     &nbsp;<span style="color:var(--accent2);font-size:12px">Qtd: ${p.quantidade}</span>`;
}

function movToggleModo(ev){
  if(ev) ev.stopPropagation();
  const p=produtos.find(x=>x.id===movProdId);
  if(!p||!p.unid_por_fardo) return;
  movModoEmbalagem=!movModoEmbalagem;
  movRenderSelLabel();
  movAtualizarPreview();
}

function movAtualizarPreview(){
  const el=document.getElementById('mov-qtd-preview');
  if(!el) return;
  const p=produtos.find(x=>x.id===movProdId);
  if(!p||!p.unid_por_fardo||!movModoEmbalagem){el.textContent='';return;}
  const qtd=parseFloat(document.getElementById('mov-qtd').value)||0;
  if(qtd<=0){el.textContent='';return;}
  el.innerHTML=`<span style="color:var(--accent2)">= ${(qtd*p.unid_por_fardo).toLocaleString('pt-BR',{maximumFractionDigits:2})} ${p.unidade||'un'}</span>`;
}

function limparMovSel(){
  movProdId=null;
  movModoEmbalagem=false;
  document.getElementById('mov-sel-wrap').classList.add('hidden');
  document.getElementById('mov-busca-wrap').classList.remove('hidden');
  document.getElementById('mov-busca').value=''; filtrarMovBusca();
  const prev=document.getElementById('mov-qtd-preview');
  if(prev) prev.textContent='';
}
function toggleCampoValidadeMov(){
  const tipo=document.getElementById('mov-tipo').value;
  const wrap=document.getElementById('mov-validade-wrap');
  if(tipo==='entrada'){ wrap.classList.remove('hidden'); }
  else { wrap.classList.add('hidden'); document.getElementById('mov-validade').value=''; }
}
async function abrirModalMov(){
  if(movEstado.enviando) return;
  if(reabrirOperacaoPendente(movEstado,'modal-mov')) return;
  if(!produtos.length) produtos=await fetch('/api/produtos').then(r=>r.json());
  movEstado=criarEstadoLote('movimentacao');
  limparMovSel();
  movCatFiltro=null;
  document.getElementById('mov-qtd').value=1;
  document.getElementById('mov-obs').value='';
  document.getElementById('mov-tipo').value='entrada';
  document.getElementById('mov-validade').value='';
  document.getElementById('mov-busca').value='';
  document.getElementById('mov-scan').value='';
  toggleCampoValidadeMov();
  construirMovCatChips();
  filtrarMovBusca();
  document.getElementById('modal-mov').classList.remove('hidden');
  setTimeout(()=>document.getElementById('mov-scan').focus(),80);
}

function movProcessarScan(){
  const codigo=document.getElementById('mov-scan').value.trim();
  document.getElementById('mov-scan').value='';
  if(!codigo) return;
  const p=produtos.find(x=>x.codigo_barras===codigo && x.ativo!==0);
  if(p){
    selecionarMovProd(p.id);
    toast(`✅ ${p.nome}`);
    setTimeout(()=>document.getElementById('mov-qtd').focus(),50);
  } else {
    toast(`Código "${codigo}" não cadastrado`,'var(--danger)');
    if(confirm(`Nenhum produto tem o código de barras "${codigo}".\n\nDeseja cadastrar um novo produto com esse código?`)){
      fecharModal('modal-mov');
      abrirModalProduto();
      document.getElementById('p-codigo-barras').value=codigo;
    } else {
      document.getElementById('mov-scan').focus();
    }
  }
}

async function salvarMov(){
  if(movEstado.enviando) return;
  recuperarOperacaoPendente(movEstado);
  let body;
  if(movEstado.incerta){
    body=movEstado.payloadOriginal;
  } else {
    if(!movProdId){toast('Selecione um produto','var(--danger)');return;}
    let qtd=+document.getElementById('mov-qtd').value;
    // Se estiver em modo embalagem (fardo/caixa), converte para unidades
    const p=produtos.find(x=>x.id===movProdId);
    if(movModoEmbalagem && p && p.unid_por_fardo){
      qtd=Math.round(qtd*p.unid_por_fardo*1000)/1000;
    }
    const tipo=document.getElementById('mov-tipo').value;
    if(!Number.isFinite(qtd)||qtd<0||(tipo!=='ajuste'&&qtd===0)){
      toast('Informe uma quantidade válida','var(--danger)');return;
    }
    body={produto_id:movProdId,tipo,
      quantidade:qtd,observacao:document.getElementById('mov-obs').value,
      validade:document.getElementById('mov-validade').value||null};
  }
  const d=await enviarOperacaoAtomica(movEstado,'/api/movimentacoes',body,'modal-mov');
  if(!d) return;
  toast(d.tentativaAnterior?'Movimentação anterior confirmada. Alterações atuais não foram enviadas.':`Novo estoque: ${d.novo_estoque}`);
  fecharModal('modal-mov');
  try{
    produtos=await fetch('/api/produtos').then(r=>{if(!r.ok) throw new Error();return r.json();});
    await carregarMovimentacoes();
  } catch(erro){
    toast('Movimentação registrada. Recarregue a página para atualizar o estoque.','var(--danger)');
  }
}

// ═══════════════════════════════════════
// Saída em Lote
// ═══════════════════════════════════════
let loteItens=[]; // [{produto_id, nome, codigo, unidade, quantidade, qtdEstoque}]
let loteCatFiltro=null;
let saidaLoteEstado=criarEstadoLote('saida-lote');

async function abrirModalLote(){
  if(saidaLoteEstado.enviando) return;
  if(reabrirOperacaoPendente(saidaLoteEstado,'modal-lote')) return;
  if(!produtos.length) produtos=await fetch('/api/produtos').then(r=>r.json());
  saidaLoteEstado=criarEstadoLote('saida-lote');
  loteItens=[];
  loteCatFiltro=null;
  document.getElementById('lote-busca').value='';
  document.getElementById('lote-scan').value='';
  renderLoteItens();
  construirLoteCatChips();
  filtrarLoteBusca();
  document.getElementById('modal-lote').classList.remove('hidden');
  setTimeout(()=>document.getElementById('lote-scan').focus(),80);
}

// Função genérica de scan, usada na entrada e saída em lote.
// campoScanId: id do input onde o leitor "digita" o código.
// fnAdicionar: função que adiciona o item à lista (adicionarItemLote ou equivalente na entrada).
function loteProcessarScan(campoScanId, fnAdicionar){
  const campo=document.getElementById(campoScanId);
  const codigo=campo.value.trim();
  campo.value='';
  if(!codigo) return;
  const p=produtos.find(x=>x.codigo_barras===codigo && x.ativo!==0);
  if(p){
    fnAdicionar(p.id);
    toast(`✅ ${p.nome} adicionado`);
  } else {
    toast(`Código "${codigo}" não cadastrado`,'var(--danger)');
  }
  campo.focus();
}

function construirLoteCatChips(){
  const el=document.getElementById('lote-cat-chips');
  const cats=[...new Set(produtos.map(p=>p.categoria).filter(Boolean))].sort();
  el.innerHTML=`<span class="filter-chip ${loteCatFiltro===null?'active':''}"
    onclick="setLoteCat(null)">Todas</span>`+
    cats.map(c=>`<span class="filter-chip ${loteCatFiltro===c?'active':''}"
      onclick="setLoteCat('${c}')">${c}</span>`).join('');
}

function setLoteCat(cat){
  loteCatFiltro=cat;
  construirLoteCatChips();
  filtrarLoteBusca();
}

const filtrarLoteBuscaAoDigitar=adiarBusca(filtrarLoteBusca);
function filtrarLoteBusca(){
  filtrarLoteBuscaAoDigitar.cancelar();
  const q=document.getElementById('lote-busca').value.trim().toLowerCase();
  const lista=document.getElementById('lote-lista');
  let itens=produtos.filter(p=>p.ativo!==0);
  if(loteCatFiltro) itens=itens.filter(p=>p.categoria===loteCatFiltro);
  if(q) itens=itens.filter(p=>produtoCorrespondeBusca(p,q));
  if(!itens.length){lista.innerHTML='<div style="padding:9px;color:var(--muted);font-size:12px">Nenhum produto encontrado</div>';return;}
  lista.innerHTML=avisoLimiteSeletor(itens.length)+itens.slice(0,LIMITE_RESULTADOS_SELETOR).map(p=>`<div class="p-opt" onclick="adicionarItemLote(${p.id})">
    <div><div class="pn">${p.nome}</div><div class="pi">${p.codigo} · <span class="badge badge-unit">${p.unidade||'un'}</span>${p.categoria?' · <span class="badge badge-cat" style="font-size:10px">'+p.categoria+'</span>':''}</div></div>
    <div class="pq">Qtd: ${p.quantidade}</div></div>`).join('');
}

function adicionarItemLote(pid){
  const p=produtos.find(x=>x.id===pid); if(!p) return;
  const existente=loteItens.find(i=>i.produto_id===pid);
  if(existente){ existente.quantidade+=1; }
  else{
    loteItens.push({produto_id:pid, nome:p.nome, codigo:p.codigo, unidade:p.unidade||'un',
      quantidade:1, qtdEstoque:p.quantidade,
      unid_por_fardo:p.unid_por_fardo||null, unid_fardo_label:p.unid_fardo_label||'fd',
      modoEmbalagem:false});
  }
  renderLoteItens();
}

function removerItemLote(pid){
  loteItens=loteItens.filter(i=>i.produto_id!==pid);
  renderLoteItens();
}

function toggleModoLote(pid){
  const item=loteItens.find(i=>i.produto_id===pid);
  if(!item||!item.unid_por_fardo) return;
  item.modoEmbalagem=!item.modoEmbalagem;
  // Converter a quantidade digitada para o novo modo
  if(item.modoEmbalagem){
    item.quantidade=Math.max(1,Math.round(item.quantidade/item.unid_por_fardo*10)/10);
  } else {
    item.quantidade=Math.round(item.quantidade*item.unid_por_fardo*10)/10;
  }
  renderLoteItens();
}

function renderLoteItens(){
  const wrap=document.getElementById('lote-itens-wrap');
  const rows=document.getElementById('lote-itens-rows');
  const empty=document.getElementById('lote-empty');

  if(!loteItens.length){
    wrap.classList.add('hidden');
    empty.classList.remove('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  empty.classList.add('hidden');

  rows.innerHTML=`<div class="ing-row ing-header"><span>Produto</span><span>Quantidade</span><span>Un.</span><span></span></div>`
    +loteItens.map((item,idx)=>{
      const temConversao=item.unid_por_fardo>0;
      const unLabel=item.modoEmbalagem?item.unid_fardo_label:item.unidade;
      const badgeStyle=temConversao?'cursor:pointer;border:1px dashed var(--accent)':'';
      const preview=temConversao&&item.modoEmbalagem
        ? `<br><small style="color:var(--accent2)">= ${(item.quantidade*item.unid_por_fardo).toLocaleString('pt-BR',{maximumFractionDigits:2})} ${item.unidade}</small>`
        : '';
      return `<div class="ing-row">
      <span>${item.nome}<br><small style="color:var(--muted)">Estoque atual: ${item.qtdEstoque}</small></span>
      <span><input type="number" min="0.001" step="0.001" value="${item.quantidade}" style="width:78px;padding:4px 6px;font-size:12px"
        onchange="loteItens[${idx}].quantidade=+this.value;renderLoteItens()">${preview}</span>
      <span><span class="badge badge-unit" style="${badgeStyle}"
        ${temConversao?`title="Clique para alternar (1 ${item.unid_fardo_label} = ${item.unid_por_fardo} ${item.unidade})" onclick="toggleModoLote(${item.produto_id})"`:''}>${unLabel}${temConversao?' ⇄':''}</span></span>
      <span><button class="btn btn-danger" style="padding:3px 7px;font-size:11px" onclick="removerItemLote(${item.produto_id})">✕</button></span>
    </div>`;}).join('');
}

async function confirmarSaidaLote(){
  if(saidaLoteEstado.enviando) return;
  recuperarOperacaoPendente(saidaLoteEstado);
  const itens=saidaLoteEstado.incerta?saidaLoteEstado.payloadOriginal.itens:[];
  if(!saidaLoteEstado.incerta){
    if(!loteItens.length){toast('Adicione pelo menos um produto','var(--danger)');return;}

    // Validação prévia de estoque suficiente (converte fardos para unidades antes)
    for(const item of loteItens){
      const qtdReal=item.modoEmbalagem&&item.unid_por_fardo
        ? Math.round(item.quantidade*item.unid_por_fardo*1000)/1000
        : item.quantidade;
      if(!Number.isFinite(qtdReal)||qtdReal<=0){
        toast(`Informe uma quantidade válida para ${item.nome}`,'var(--danger)');
        return;
      }
      if(qtdReal>item.qtdEstoque){
        toast(`Estoque insuficiente: ${item.nome} (tem ${item.qtdEstoque}, pediu ${qtdReal})`,'var(--danger)');
        return;
      }
      itens.push({produto_id:item.produto_id,tipo:'saida',quantidade:qtdReal,observacao:'Saída em lote'});
    }
  }

  const d=await enviarOperacaoAtomica(saidaLoteEstado,'/api/movimentacoes/lote',{itens},'modal-lote');
  if(!d) return;
  toast(d.tentativaAnterior?'Saída anterior confirmada. Alterações atuais não foram enviadas.':`Saída de ${itens.length} produto${itens.length>1?'s':''} registrada com sucesso!`);
  fecharModal('modal-lote');
  try{
    produtos=await fetch('/api/produtos').then(r=>{if(!r.ok) throw new Error();return r.json();});
    await carregarMovimentacoes();
  } catch(erro){
    toast('Saída registrada. Recarregue a página para atualizar o estoque.','var(--danger)');
  }
}

function imprimirListaLote(){
  if(!loteItens.length){toast('Adicione pelo menos um produto','var(--danger)');return;}

  const agora=new Date().toLocaleString('pt-BR');
  let linhas=loteItens.map(item=>{
    const unLabel=item.modoEmbalagem?item.unid_fardo_label:item.unidade;
    return `<div class="item">
      <div class="nome">${item.nome}</div>
      <div class="qtd">${item.quantidade} ${unLabel}</div>
    </div>`;
  }).join('');

  const html=`<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
  <title>Lista de Separação</title>
  <style>
    @page { margin: 0; }
    * { box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    html, body { width: 100%; max-width: 80mm; }
    body { font-family: 'Courier New', Consolas, monospace; padding: 6px 8px; font-size: 15px;
           font-weight: bold; color:#000; background:#fff; }
    .titulo { text-align:center; font-weight:900; font-size:20px; margin-bottom:2px; letter-spacing:1px; }
    .sub { text-align:center; font-size:13px; font-weight:bold; margin-bottom:8px; }
    .linha { border-top: 3px solid #000; margin: 8px 0; }
    .item { display:flex; justify-content:space-between; align-items:center; padding:8px 0;
            border-bottom: 2px solid #000; }
    .nome { flex:1; padding-right:8px; font-size:16px; font-weight:900; }
    .qtd { font-weight:900; font-size:17px; white-space:nowrap; }
    .rodape { text-align:center; font-size:13px; font-weight:bold; margin-top:12px; }
    .check { display:inline-block; width:16px; height:16px; border:3px solid #000; margin-right:8px; vertical-align:middle; }
  </style></head><body>
    <div class="titulo">LISTA DE SEPARAÇÃO</div>
    <div class="sub">S.G. Lira's - ${agora}</div>
    <div class="linha"></div>
    ${loteItens.map(item=>`<div class="item">
      <span style="display:flex;align-items:center"><span class="check"></span>${item.nome}</span>
      <span class="qtd">${item.quantidade} ${item.unidade}</span>
    </div>`).join('')}
    <div class="linha"></div>
    <div class="rodape">Total de itens: ${loteItens.length}</div>
    <script>window.onload=()=>setTimeout(()=>window.print(),300);<\/script>
  </body></html>`;

  const blob=new Blob([html],{type:'text/html;charset=utf-8'});
  const blobUrl=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=blobUrl;
  a.target='_blank';
  a.click();
  setTimeout(()=>URL.revokeObjectURL(blobUrl), 60000);
}
