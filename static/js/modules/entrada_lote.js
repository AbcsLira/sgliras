// ═══════════════════════════════════════
// ENTRADA EM LOTE
// ═══════════════════════════════════════
let entradaLoteItens=[];
let entradaLoteCatFiltro=null;
let entradaLoteEstado=criarEstadoLote('entrada-lote');

async function abrirModalEntradaLote(){
  if(entradaLoteEstado.enviando) return;
  if(reabrirOperacaoPendente(entradaLoteEstado,'modal-entrada-lote')) return;
  if(!produtos.length) produtos=await fetch('/api/produtos').then(r=>r.json());
  entradaLoteEstado=criarEstadoLote('entrada-lote');
  entradaLoteItens=[];
  entradaLoteCatFiltro=null;
  document.getElementById('entrada-lote-busca').value='';
  document.getElementById('entrada-lote-scan').value='';
  document.getElementById('entrada-lote-validade').value='';
  document.getElementById('entrada-lote-obs').value='';
  renderEntradaLoteItens();
  construirEntradaLoteCatChips();
  filtrarEntradaLoteBusca();
  document.getElementById('modal-entrada-lote').classList.remove('hidden');
  setTimeout(()=>document.getElementById('entrada-lote-scan').focus(),80);
}

function construirEntradaLoteCatChips(){
  const el=document.getElementById('entrada-lote-cat-chips');
  const cats=[...new Set(produtos.map(p=>p.categoria).filter(Boolean))].sort();
  el.innerHTML=`<span class="filter-chip ${entradaLoteCatFiltro===null?'active':''}"
    onclick="setEntradaLoteCat(null)">Todas</span>`+
    cats.map(c=>`<span class="filter-chip ${entradaLoteCatFiltro===c?'active':''}"
      onclick="setEntradaLoteCat('${c}')">${CAT_ICONS[c]||'🏷️'} ${c}</span>`).join('');
}

function setEntradaLoteCat(cat){
  entradaLoteCatFiltro=cat;
  construirEntradaLoteCatChips();
  filtrarEntradaLoteBusca();
}

const filtrarEntradaLoteBuscaAoDigitar=adiarBusca(filtrarEntradaLoteBusca);
function filtrarEntradaLoteBusca(){
  filtrarEntradaLoteBuscaAoDigitar.cancelar();
  const q=document.getElementById('entrada-lote-busca').value.trim().toLowerCase();
  const lista=document.getElementById('entrada-lote-lista');
  let itens=produtos;
  if(entradaLoteCatFiltro) itens=itens.filter(p=>p.categoria===entradaLoteCatFiltro);
  if(q) itens=itens.filter(p=>produtoCorrespondeBusca(p,q));
  if(!itens.length){lista.innerHTML='<div style="padding:9px;color:var(--muted);font-size:12px">Nenhum produto encontrado</div>';return;}
  lista.innerHTML=avisoLimiteSeletor(itens.length)+itens.slice(0,LIMITE_RESULTADOS_SELETOR).map(p=>`<div class="p-opt" onclick="adicionarItemEntradaLote(${p.id})">
    <div>
      <div class="pn">${p.nome}</div>
      <div class="pi">${p.codigo} · <span class="badge badge-unit">${p.unidade||'un'}</span>${p.categoria?' · <span class="badge badge-cat" style="font-size:10px">'+p.categoria+'</span>':''}
        ${p.unid_por_fardo?`<span style="font-size:10px;color:var(--muted)"> · 1 ${p.unid_fardo_label||'fd'} = ${p.unid_por_fardo} ${p.unidade||'un'}</span>`:''}
      </div>
    </div>
    <div class="pq">Estoque: ${p.quantidade} ${p.unidade||'un'}</div>
  </div>`).join('');
}

function adicionarItemEntradaLote(pid){
  const p=produtos.find(x=>x.id===pid); if(!p) return;
  const existente=entradaLoteItens.find(i=>i.produto_id===pid);
  if(existente){
    existente.quantidade+=existente.unid_por_fardo||1;
  } else {
    entradaLoteItens.push({
      produto_id:pid, nome:p.nome, codigo:p.codigo,
      unidade:p.unidade||'un', quantidade:1,
      qtdEstoque:p.quantidade,
      unid_por_fardo:p.unid_por_fardo||null,
      unid_fardo_label:p.unid_fardo_label||'fd',
      modoEmbalagem:false  // false = digita em unidades, true = digita em embalagens
    });
  }
  renderEntradaLoteItens();
}

function removerItemEntradaLote(pid){
  entradaLoteItens=entradaLoteItens.filter(i=>i.produto_id!==pid);
  renderEntradaLoteItens();
}

function toggleModoEntradaLote(pid){
  const item=entradaLoteItens.find(i=>i.produto_id===pid);
  if(!item||!item.unid_por_fardo) return;
  item.modoEmbalagem=!item.modoEmbalagem;
  // Converter quantidade para o novo modo
  if(item.modoEmbalagem){
    item.quantidade=Math.max(1,Math.round(item.quantidade/item.unid_por_fardo*10)/10);
  } else {
    item.quantidade=Math.round(item.quantidade*item.unid_por_fardo*10)/10;
  }
  renderEntradaLoteItens();
}

function renderEntradaLoteItens(){
  const wrap=document.getElementById('entrada-lote-itens-wrap');
  const rows=document.getElementById('entrada-lote-itens-rows');
  const empty=document.getElementById('entrada-lote-empty');
  const totalEl=document.getElementById('entrada-lote-total');

  if(!entradaLoteItens.length){
    wrap.classList.add('hidden');
    empty.classList.remove('hidden');
    totalEl.textContent='';
    return;
  }
  wrap.classList.remove('hidden');
  empty.classList.add('hidden');
  totalEl.textContent=`${entradaLoteItens.length} produto${entradaLoteItens.length>1?'s':''}`;

  rows.innerHTML=`<div class="ing-row ing-header">
    <span>Produto</span><span>Quantidade</span><span>Unidade</span><span></span>
  </div>`+entradaLoteItens.map((item,idx)=>{
    const temConversao=item.unid_por_fardo>0;
    const unLabel=item.modoEmbalagem?item.unid_fardo_label:item.unidade;
    const qtdUnidades=item.modoEmbalagem
      ? (item.quantidade*item.unid_por_fardo).toLocaleString('pt-BR',{maximumFractionDigits:2})
      : item.quantidade;
    const previewConversao=temConversao
      ? item.modoEmbalagem
        ? `<small style="color:var(--accent2)">= ${qtdUnidades} ${item.unidade}</small>`
        : `<small style="color:var(--muted)">= ${(item.quantidade/item.unid_por_fardo).toLocaleString('pt-BR',{maximumFractionDigits:2})} ${item.unid_fardo_label}</small>`
      : '';
    return `<div class="ing-row">
      <span>
        ${item.nome}
        <br><small style="color:var(--muted)">Estoque atual: ${item.qtdEstoque} ${item.unidade}</small>
        ${previewConversao?`<br>${previewConversao}`:''}
      </span>
      <span>
        <input type="number" min="0.001" step="${item.modoEmbalagem?'0.5':'0.001'}" value="${item.quantidade}"
          style="width:80px;padding:4px 6px;font-size:12px"
          onchange="entradaLoteItens[${idx}].quantidade=+this.value;renderEntradaLoteItens()">
      </span>
      <span>
        <span class="badge badge-unit" style="cursor:${temConversao?'pointer':'default'};${temConversao?'border:1px solid var(--accent);color:var(--accent)':''}"
          ${temConversao?`onclick="toggleModoEntradaLote(${item.produto_id})" title="Clique para alternar entre ${item.unidade} e ${item.unid_fardo_label}"`:''}
        >${unLabel}</span>
        ${temConversao?`<br><small style="color:var(--muted);font-size:10px">clique p/ alternar</small>`:''}
      </span>
      <span><button class="btn btn-danger" style="padding:3px 7px;font-size:11px" onclick="removerItemEntradaLote(${item.produto_id})">✕</button></span>
    </div>`;
  }).join('');
}

async function confirmarEntradaLote(){
  if(entradaLoteEstado.enviando) return;
  recuperarOperacaoPendente(entradaLoteEstado);
  const itens=entradaLoteEstado.incerta?entradaLoteEstado.payloadOriginal.itens:[];
  if(!entradaLoteEstado.incerta){
    if(!entradaLoteItens.length){toast('Adicione pelo menos um produto','var(--danger)');return;}
    const validade=document.getElementById('entrada-lote-validade').value||null;
    const obs=document.getElementById('entrada-lote-obs').value||'Entrada em lote';

    for(const item of entradaLoteItens){
      // Converter para unidades se estiver em modo embalagem
      const qtdUnidades=item.modoEmbalagem
        ? item.quantidade*item.unid_por_fardo
        : item.quantidade;
      if(!Number.isFinite(qtdUnidades)||qtdUnidades<=0){
        toast(`Informe uma quantidade válida para ${item.nome}`,'var(--danger)');
        return;
      }
      itens.push({produto_id:item.produto_id,tipo:'entrada',quantidade:qtdUnidades,observacao:obs,validade});
    }
  }

  const d=await enviarOperacaoAtomica(entradaLoteEstado,'/api/movimentacoes/lote',{itens},'modal-entrada-lote');
  if(!d) return;
  toast(d.tentativaAnterior?'Entrada anterior confirmada. Alterações atuais não foram enviadas.':`Entrada de ${itens.length} produto${itens.length>1?'s':''} registrada com sucesso! 📦`);
  fecharModal('modal-entrada-lote');
  try{
    produtos=await fetch('/api/produtos').then(r=>{if(!r.ok) throw new Error();return r.json();});
    await carregarMovimentacoes();
  } catch(erro){
    toast('Entrada registrada. Recarregue a página para atualizar o estoque.','var(--danger)');
  }
}
