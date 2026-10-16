// ═══════════════════════════════════════
// Lista de Compras
// ═══════════════════════════════════════
let listaCompras=[]; // [{produto_id, nome, codigo, unidade, quantidade_estoque, quantidade_comprar, fornecedor_sugerido, preco_unit}]

async function carregarSugestaoCompras(){
  // Reseta todo o estado da tela ao entrar, garantindo que não sobra nada de uma visita anterior
  compraFornFiltro=null;
  produtosPorFornecedorCache={};
  compraSelecionados={};
  document.getElementById('modal-compra-select').classList.add('hidden');

  // Carrega fornecedores e monta atalhos rápidos
  if(!fornecedores.length) fornecedores=await fetch('/api/fornecedores').then(r=>r.json());
  const atalhoWrap=document.getElementById('compra-forn-atalho-wrap');
  const atalhoChips=document.getElementById('compra-forn-atalho-chips');
  if(fornecedores.length){
    atalhoWrap.classList.remove('hidden');
    atalhoChips.innerHTML=fornecedores.map(f=>`
      <span class="filter-chip" onclick="abrirBuscaCompraManualFornecedor(${f.id})">
        🚚 ${f.nome}
      </span>`).join('');
  } else {
    atalhoWrap.classList.add('hidden');
  }

  const sugestoes=await fetch('/api/lista-compras/sugestao').then(r=>r.json());
  listaCompras=sugestoes.map(p=>({
    produto_id:p.id, nome:p.nome, codigo:p.codigo, unidade:p.unidade, categoria:p.categoria,
    unid_por_fardo:p.unid_por_fardo, unid_fardo_label:p.unid_fardo_label,
    quantidade_estoque:p.quantidade, quantidade_comprar:p.quantidade_sugerida,
    fornecedor_sugerido:p.fornecedor_sugerido, preco_unit:p.preco_fornecedor!=null?p.preco_fornecedor:p.preco_custo
  }));
  renderListaCompras();
}

// Abre o modal de seleção já filtrado pelo fornecedor clicado
async function abrirBuscaCompraManualFornecedor(fid){
  await abrirBuscaCompraManual();
  await setCompraFornFiltro(fid);
}

function renderListaCompras(){
  const tbody=document.getElementById('t-lista-compras');
  if(!listaCompras.length){
    tbody.innerHTML='<tr><td colspan="6" class="empty">Nenhum produto na lista. Use a sugestão automática ou adicione manualmente.</td></tr>';
    atualizarTotaisCompras();
    return;
  }

  // Agrupar por categoria, igual ao dashboard/listagem PDF
  const grupos={};
  listaCompras.forEach((item,idx)=>{
    const cat=item.categoria||'Sem categoria';
    if(!grupos[cat]) grupos[cat]=[];
    grupos[cat].push({...item, _idx:idx});
  });

  tbody.innerHTML=Object.entries(grupos).map(([cat,itens])=>{
    const linhaGrupo=`<tr class="grupo-row"><td colspan="6" style="background:var(--card2);font-weight:700;
      font-size:11px;text-transform:uppercase;letter-spacing:.4px;padding:8px 12px">
      ${CAT_ICONS[cat]||'🏷️'} ${cat} <span style="opacity:.6;font-weight:400">(${itens.length})</span></td></tr>`;
    const linhas=itens.map(item=>{
      const idx=item._idx;
      const valorItem=(item.quantidade_comprar||0)*(item.preco_unit||0);
      const estoqueDisplay=fmtQtdComoFardo(item.quantidade_estoque, item);
      return `<tr>
        <td>${item.nome}</td>
        <td>${estoqueDisplay}</td>
        <td><input type="number" min="0" step="0.001" value="${item.quantidade_comprar}" style="width:80px;padding:4px 6px;font-size:12px"
          onchange="listaCompras[${idx}].quantidade_comprar=+this.value;atualizarTotaisCompras();renderListaCompras()">
          <div style="font-size:11px;color:var(--muted);margin-top:2px">${fmtQtdComoFardo(item.quantidade_comprar, item)}</div></td>
        <td>${item.fornecedor_sugerido?`<span class="badge badge-ok">${item.fornecedor_sugerido}</span>`:'<span style="color:var(--muted)">—</span>'}</td>
        <td>${fmtR(valorItem)}</td>
        <td><button class="btn btn-danger btn-sm" onclick="removerItemCompra(${idx})">🗑️</button></td>
      </tr>`;
    }).join('');
    return linhaGrupo+linhas;
  }).join('');
  atualizarTotaisCompras();
}

function atualizarTotaisCompras(){
  const totalItens=listaCompras.length;
  const totalValor=listaCompras.reduce((acc,item)=>acc+(item.quantidade_comprar||0)*(item.preco_unit||0),0);
  document.getElementById('compra-total-itens').textContent=`${totalItens} ite${totalItens===1?'m':'ns'}`;
  document.getElementById('compra-total-valor').textContent=fmtR(totalValor);
}

function removerItemCompra(idx){
  listaCompras.splice(idx,1);
  renderListaCompras();
}

let compraFornFiltro=null; // id do fornecedor selecionado para filtrar a busca
let produtosPorFornecedorCache={}; // {fornecedor_id: [produtos com preco_fornecedor]}
let compraSelecionados={}; // {produto_id: true} - produtos marcados no modal antes de confirmar

async function abrirBuscaCompraManual(){
  if(!produtos.length) produtos=await fetch('/api/produtos').then(r=>r.json());
  if(!fornecedores.length) fornecedores=await fetch('/api/fornecedores').then(r=>r.json());
  compraFornFiltro=null;
  produtosPorFornecedorCache={};
  compraSelecionados={};

  document.getElementById('compra-busca').value='';

  const chipsEl=document.getElementById('compra-forn-chips');
  if(fornecedores.length){
    chipsEl.classList.remove('hidden');
    chipsEl.innerHTML=`<span class="filter-chip ${compraFornFiltro===null?'active':''}" onclick="setCompraFornFiltro(null)">Todos os produtos</span>`
      +fornecedores.map(f=>`<span class="filter-chip ${compraFornFiltro===f.id?'active':''}"
        onclick="setCompraFornFiltro(${f.id})">🚚 ${f.nome}</span>`).join('');
  } else {
    chipsEl.classList.add('hidden');
  }

  document.getElementById('modal-compra-select').classList.remove('hidden');
  await filtrarCompraBusca();
  setTimeout(()=>document.getElementById('compra-busca').focus(),80);
}

async function setCompraFornFiltro(fid){
  compraFornFiltro=fid;
  const chipsEl=document.getElementById('compra-forn-chips');
  chipsEl.innerHTML=`<span class="filter-chip ${compraFornFiltro===null?'active':''}" onclick="setCompraFornFiltro(null)">Todos os produtos</span>`
    +fornecedores.map(f=>`<span class="filter-chip ${compraFornFiltro===f.id?'active':''}"
      onclick="setCompraFornFiltro(${f.id})">🚚 ${f.nome}</span>`).join('');
  await filtrarCompraBusca();
}

async function filtrarCompraBusca(){
  const q=document.getElementById('compra-busca').value.toLowerCase();
  const lista=document.getElementById('compra-lista-busca');

  let baseItens;
  if(compraFornFiltro){
    if(!produtosPorFornecedorCache[compraFornFiltro]){
      produtosPorFornecedorCache[compraFornFiltro]=await fetch(`/api/fornecedores/${compraFornFiltro}/produtos`).then(r=>r.json());
    }
    baseItens=produtosPorFornecedorCache[compraFornFiltro];
  } else {
    baseItens=produtos;
  }

  // Não mostra produtos que já estão na lista de compras
  baseItens=baseItens.filter(p=>!listaCompras.find(i=>i.produto_id===p.id));

  const itens=q?baseItens.filter(p=>p.nome.toLowerCase().includes(q)||p.codigo.toLowerCase().includes(q)):baseItens;
  if(!itens.length){lista.innerHTML='<div style="padding:9px;color:var(--muted);font-size:12px">Nenhum produto encontrado</div>';return;}
  lista.innerHTML=itens.slice(0,50).map(p=>{
    const precoInfo=compraFornFiltro&&p.preco_fornecedor!=null?` · <span style="color:var(--accent2)">${fmtR(p.preco_fornecedor)}</span>`:'';
    const marcado=!!compraSelecionados[p.id];
    return `<div class="p-opt ${marcado?'p-opt-selected':''}" onclick="toggleCompraSelecionado(${p.id})">
    <input type="checkbox" class="p-opt-check" ${marcado?'checked':''} style="pointer-events:none">
    <div class="p-opt-info">
      <div class="pn">${p.nome}</div>
      <div class="pi">${p.codigo} · <span class="badge badge-unit">${p.unidade||'un'}</span>${precoInfo}</div>
    </div>
    <div class="pq">Estoque: ${p.quantidade}</div></div>`;
  }).join('');
}

function toggleCompraSelecionado(pid){
  if(compraSelecionados[pid]) delete compraSelecionados[pid];
  else compraSelecionados[pid]=true;
  document.getElementById('compra-select-contador').textContent=
    `${Object.keys(compraSelecionados).length} selecionado${Object.keys(compraSelecionados).length===1?'':'s'}`;
  filtrarCompraBusca();
}

async function confirmarAdicaoCompraManual(){
  const ids=Object.keys(compraSelecionados).map(Number);
  if(!ids.length){toast('Selecione pelo menos um produto','var(--danger)');return;}

  for(const pid of ids){
    const p=produtos.find(x=>x.id===pid); if(!p) continue;
    if(listaCompras.find(i=>i.produto_id===pid)) continue;

    const fornecedoresProd=await fetch(`/api/produtos/${pid}/fornecedores`).then(r=>r.json());
    let melhor=fornecedoresProd[0]||null;
    if(compraFornFiltro){
      const doFiltro=fornecedoresProd.find(f=>f.fornecedor_id===compraFornFiltro);
      if(doFiltro) melhor=doFiltro;
    }

    listaCompras.push({
      produto_id:pid, nome:p.nome, codigo:p.codigo, unidade:p.unidade||'un', categoria:p.categoria,
      unid_por_fardo:p.unid_por_fardo, unid_fardo_label:p.unid_fardo_label,
      quantidade_estoque:p.quantidade, quantidade_comprar:Math.max(p.estoque_min||1,1),
      fornecedor_sugerido:melhor?melhor.fornecedor_nome:null,
      preco_unit:melhor?melhor.preco:p.preco_custo
    });
  }

  renderListaCompras();
  toast(`${ids.length} produto${ids.length===1?'':'s'} adicionado${ids.length===1?'':'s'} à lista`);
  fecharModal('modal-compra-select');
}

function imprimirListaCompras(){
  if(!listaCompras.length){toast('Lista de compras vazia','var(--danger)');return;}

  const agora=new Date().toLocaleString('pt-BR');
  const totalValor=listaCompras.reduce((acc,item)=>acc+(item.quantidade_comprar||0)*(item.preco_unit||0),0);

  // Agrupar por categoria, igual ao dashboard/listagem PDF
  const grupos={};
  listaCompras.forEach(item=>{
    const cat=item.categoria||'Sem categoria';
    if(!grupos[cat]) grupos[cat]=[];
    grupos[cat].push(item);
  });

  const blocosGrupos=Object.entries(grupos).map(([cat,itens])=>{
    const linhasItens=itens.map(item=>{
      const valorItem=(item.quantidade_comprar||0)*(item.preco_unit||0);
      const qtdDisplay=fmtQtdComoFardo(item.quantidade_comprar, item);
      return `<div class="item">
        <div class="nome"><span class="check"></span>${item.nome}</div>
        <div class="det"><span>${qtdDisplay}</span><span>${fmtR(valorItem)}</span></div>
        ${item.fornecedor_sugerido?`<div class="forn">Comprar em: ${item.fornecedor_sugerido}</div>`:''}
      </div>`;
    }).join('');
    return `<div class="grupo-titulo">${cat}</div>${linhasItens}`;
  }).join('');

  const html=`<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
  <title>Lista de Compras</title>
  <style>
    @page { margin: 0; }
    * { box-sizing: border-box; margin:0; padding:0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    html, body { width: 100%; max-width: 80mm; }
    body { font-family: 'Courier New', Consolas, monospace; padding: 6px 8px; font-size: 14px;
           font-weight: bold; color:#000; background:#fff; }
    .titulo { text-align:center; font-weight:900; font-size:19px; margin-bottom:2px; letter-spacing:1px; }
    .sub { text-align:center; font-size:12px; font-weight:bold; margin-bottom:8px; }
    .linha { border-top: 3px solid #000; margin: 8px 0; }
    .grupo-titulo { font-size:13px; font-weight:900; text-transform:uppercase; letter-spacing:.5px;
                    background:#000; color:#fff; padding:4px 6px; margin-top:10px; }
    .item { padding:8px 0; border-bottom: 2px solid #000; }
    .nome { font-size:15px; font-weight:900; }
    .det { display:flex; justify-content:space-between; margin-top:3px; font-size:13px; }
    .forn { font-size:12px; font-weight:900; color:#000; }
    .total { text-align:right; font-size:16px; font-weight:900; margin-top:10px; }
    .rodape { text-align:center; font-size:12px; font-weight:bold; margin-top:12px; }
    .check { display:inline-block; width:14px; height:14px; border:3px solid #000; margin-right:7px; vertical-align:middle; }
  </style></head><body>
    <div class="titulo">LISTA DE COMPRAS</div>
    <div class="sub">S.G. Lira's - ${agora}</div>
    <div class="linha"></div>
    ${blocosGrupos}
    <div class="linha"></div>
    <div class="total">TOTAL ESTIMADO: ${fmtR(totalValor)}</div>
    <div class="rodape">${listaCompras.length} ite${listaCompras.length===1?'m':'ns'}</div>
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

// ═══════════════════════════════════════
