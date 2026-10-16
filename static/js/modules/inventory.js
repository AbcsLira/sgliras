// ═══════════════════════════════════════
// INVENTÁRIO FÍSICO ESTRUTURADO
// ═══════════════════════════════════════
let invAtual = null;       // inventário aberto atual
let invItens = [];         // itens do inventário aberto
let invCatFiltro = null;

async function abrirInventario(){
  if(!categorias.length) categorias = await fetch('/api/categorias').then(r=>r.json());
  await invCarregarEstado();
}

async function invCarregarEstado(){
  // Verificar se há inventário aberto
  const lista = await fetch('/api/inventarios').then(r=>r.json());
  const aberto = lista.find(i=>i.status==='aberto');
  if(aberto){
    await invAbrirExistente(aberto.id);
  } else {
    invAtual = null;
    document.getElementById('inv-aberto-wrap').classList.add('hidden');
    document.getElementById('inv-historico-wrap').classList.remove('hidden');
    invRenderHistorico(lista.filter(i=>i.status==='finalizado'));
  }
}

function invRenderHistorico(lista){
  const el = document.getElementById('inv-historico-lista');
  if(!lista.length){
    el.innerHTML='<div class="empty">Nenhum inventário realizado ainda. Clique em "+ Novo inventário" para começar.</div>';
    return;
  }
  el.innerHTML = lista.map(inv=>{
    const data = new Date(inv.finalizado_em||inv.criado_em).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric'});
    const hora = new Date(inv.finalizado_em||inv.criado_em).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
    const corDiv = inv.total_divergentes>0?'var(--danger)':'var(--accent2)';
    return `<div class="table-wrap" style="padding:16px 18px;margin-bottom:10px;cursor:pointer" onclick="invVerDetalhes(${inv.id})">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
        <div>
          <div style="font-weight:700;font-size:14px">${inv.titulo}</div>
          <div style="font-size:12px;color:var(--muted);margin-top:3px">
            ${data} às ${hora} · ${inv.usuario_nome||'—'}
            ${inv.categoria?` · <span class="badge badge-unit">${inv.categoria}</span>`:''}
          </div>
        </div>
        <div style="display:flex;gap:16px;text-align:right">
          <div>
            <div style="font-size:11px;color:var(--muted)">Itens</div>
            <div style="font-weight:700">${inv.total_itens||0}</div>
          </div>
          <div>
            <div style="font-size:11px;color:var(--muted)">Divergentes</div>
            <div style="font-weight:700;color:${corDiv}">${inv.total_divergentes||0}</div>
          </div>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function invNovoInventario(){
  if(!categorias.length) categorias = await fetch('/api/categorias').then(r=>r.json());
  document.getElementById('inv-novo-titulo').value='';
  document.getElementById('inv-novo-obs').value='';
  document.getElementById('inv-novo-cat').innerHTML=
    `<option value="">— Todas as categorias —</option>`+
    categorias.map(c=>`<option value="${c.nome}">${CAT_ICONS[c.nome]||'🏷️'} ${c.nome}</option>`).join('');
  document.getElementById('modal-inv-novo').classList.remove('hidden');
}

async function invCriar(){
  const cat = document.getElementById('inv-novo-cat').value||null;
  const titulo = document.getElementById('inv-novo-titulo').value.trim()||null;
  const obs = document.getElementById('inv-novo-obs').value.trim();
  const r = await fetch('/api/inventarios',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({categoria:cat, titulo, observacao:obs})});
  const d = await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Inventário iniciado!');
  fecharModal('modal-inv-novo');
  await invAbrirExistente(d.id);
}

async function invAbrirExistente(id){
  const d = await fetch(`/api/inventarios/${id}`).then(r=>r.json());
  invAtual = d.inventario;
  invItens = d.itens.map(i=>({
    ...i,
    quantidade_contada: i.quantidade_contada ?? i.quantidade_sistema
  }));
  invCatFiltro = null;
  document.getElementById('inv-aberto-wrap').classList.remove('hidden');
  document.getElementById('inv-historico-wrap').classList.add('hidden');
  document.getElementById('inv-aberto-titulo').textContent = invAtual.titulo;
  document.getElementById('inv-aberto-info').textContent =
    `Iniciado em ${new Date(invAtual.criado_em).toLocaleString('pt-BR')} · ${invItens.length} produto(s)` +
    (invAtual.categoria ? ` · Categoria: ${invAtual.categoria}` : '');
  construirInvCatChips();
  renderInventario();
}

function construirInvCatChips(){
  const cats = [...new Set(invItens.map(i=>i.categoria).filter(Boolean))].sort();
  const el = document.getElementById('inv-cat-chips');
  el.innerHTML = `<span class="filter-chip ${invCatFiltro===null?'active':''}" onclick="setInvCat(null)">Todas (${invItens.length})</span>`+
    cats.map(c=>{
      const cnt = invItens.filter(i=>i.categoria===c).length;
      return `<span class="filter-chip ${invCatFiltro===c?'active':''}" onclick="setInvCat('${c}')">${CAT_ICONS[c]||'🏷️'} ${c} (${cnt})</span>`;
    }).join('');
}

function setInvCat(cat){
  invCatFiltro = cat;
  construirInvCatChips();
  renderInventario();
}

function renderInventario(){
  const itens = invCatFiltro ? invItens.filter(i=>i.categoria===invCatFiltro) : invItens;
  const tbody = document.getElementById('t-inventario');
  if(!itens.length){
    tbody.innerHTML='<tr><td colspan="5" class="empty">Nenhum produto nesta categoria</td></tr>';
  } else {
    tbody.innerHTML = itens.map((item, _)=>{
      const idx = invItens.indexOf(item);
      const contada = item.quantidade_contada ?? item.quantidade_sistema;
      const diff = contada - item.quantidade_sistema;
      let diffHtml = '<span style="color:var(--muted)">—</span>';
      if(Math.abs(diff)>0.0001){
        const cor = diff>0?'var(--accent2)':'var(--danger)';
        const sinal = diff>0?'+':'';
        diffHtml=`<strong style="color:${cor}">${sinal}${diff.toLocaleString('pt-BR',{maximumFractionDigits:3})} ${item.unidade}</strong>`;
      }
      return `<tr style="${item.quantidade_contada===null?'opacity:.55':''}">
        <td>
          <div>${item.nome}</div>
          <small style="color:var(--muted)">${item.codigo} · ${item.categoria}</small>
        </td>
        <td style="white-space:nowrap">${fmtQtdComoFardo(item.quantidade_sistema,item)}</td>
        <td>
          <input type="number" min="0" step="0.001" value="${contada}"
            style="width:90px;padding:5px 7px;font-size:13px;border-radius:8px;border:1px solid var(--border);background:rgba(255,255,255,.04);color:var(--text)"
            onchange="invItens[${idx}].quantidade_contada=+this.value; renderInventario()">
        </td>
        <td>${diffHtml}</td>
        <td>
          <input type="text" value="${item.observacao||''}" placeholder="—"
            style="width:100px;padding:4px 7px;font-size:12px;border-radius:8px;border:1px solid var(--border);background:rgba(255,255,255,.04);color:var(--text)"
            onchange="invItens[${idx}].observacao=this.value">
        </td>
      </tr>`;
    }).join('');
  }
  // Atualizar contadores
  const contados = invItens.filter(i=>i.quantidade_contada!==null).length;
  const divergentes = invItens.filter(i=>i.quantidade_contada!==null && Math.abs((i.quantidade_contada??i.quantidade_sistema)-i.quantidade_sistema)>0.0001).length;
  const pendentes = invItens.filter(i=>i.quantidade_contada===null).length;
  document.getElementById('inv-cnt-contados').textContent=contados;
  document.getElementById('inv-cnt-divergentes').textContent=divergentes;
  document.getElementById('inv-cnt-pendentes').textContent=pendentes;
}

async function invSalvarParcial(){
  if(!invAtual) return;
  const itens = invItens.map(i=>({
    produto_id:i.produto_id,
    quantidade_contada:i.quantidade_contada,
    observacao:i.observacao||''
  }));
  const r = await fetch(`/api/inventarios/${invAtual.id}/itens`,{method:'PUT',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({itens})});
  const d = await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Progresso salvo! 💾');
}

async function invFinalizar(){
  const divergentes = invItens.filter(i=>i.quantidade_contada!==null && Math.abs((i.quantidade_contada??i.quantidade_sistema)-i.quantidade_sistema)>0.0001);
  const pendentes = invItens.filter(i=>i.quantidade_contada===null).length;
  // Montar resumo
  let html='';
  if(pendentes>0){
    html+=`<div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:13px">
      ⚠️ <strong>${pendentes} produto(s)</strong> ainda não foram contados. Apenas os contados serão ajustados.
    </div>`;
  }
  if(!divergentes.length){
    html+=`<div style="color:var(--accent2);font-size:14px">✅ Nenhuma diferença encontrada! O estoque está de acordo com o sistema.</div>`;
  } else {
    html+=`<div style="font-size:13px;margin-bottom:10px">Os seguintes ajustes serão aplicados:</div>
    <div style="max-height:280px;overflow-y:auto">
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="color:var(--muted)"><th style="text-align:left;padding:5px 8px">Produto</th><th style="padding:5px 8px">Sistema</th><th style="padding:5px 8px">Contado</th><th style="padding:5px 8px">Diferença</th></tr></thead>
      <tbody>${divergentes.map(i=>{
        const diff = (i.quantidade_contada??i.quantidade_sistema)-i.quantidade_sistema;
        const cor = diff>0?'var(--accent2)':'var(--danger)';
        return `<tr style="border-top:1px solid var(--border)">
          <td style="padding:6px 8px">${i.nome}</td>
          <td style="padding:6px 8px;text-align:center">${i.quantidade_sistema} ${i.unidade}</td>
          <td style="padding:6px 8px;text-align:center">${i.quantidade_contada} ${i.unidade}</td>
          <td style="padding:6px 8px;text-align:center;color:${cor};font-weight:700">${diff>0?'+':''}${diff.toLocaleString('pt-BR',{maximumFractionDigits:3})}</td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>`;
  }
  document.getElementById('inv-finalizar-resumo').innerHTML=html;
  document.getElementById('modal-inv-finalizar').classList.remove('hidden');
}

async function invConfirmarFinalizar(){
  // Salvar contagens antes de finalizar
  await invSalvarParcial();
  const r = await fetch(`/api/inventarios/${invAtual.id}/finalizar`,{method:'POST',headers:{'Content-Type':'application/json'}});
  const d = await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  fecharModal('modal-inv-finalizar');
  toast(`Inventário finalizado! ${d.ajustados} produto(s) ajustado(s).`);
  // Verificar produtos abaixo do mínimo
  if(d.abaixo_minimo && d.abaixo_minimo.length){
    const nomes = d.abaixo_minimo.slice(0,3).map(p=>p.nome).join(', ');
    const mais = d.abaixo_minimo.length>3?` e mais ${d.abaixo_minimo.length-3}`:'';
    if(confirm(`${d.abaixo_minimo.length} produto(s) ficaram abaixo do mínimo após o inventário:\n${nomes}${mais}\n\nDeseja ir para a Lista de Compras?`)){
      navegarPara('lista-compras');
      return;
    }
  }
  produtos = await fetch('/api/produtos').then(r=>r.json());
  await invCarregarEstado();
}

async function invCancelar(){
  if(!invAtual) return;
  if(!confirm(`Cancelar o inventário "${invAtual.titulo}"? Nenhum ajuste será feito.`)) return;
  await fetch(`/api/inventarios/${invAtual.id}`,{method:'DELETE'});
  toast('Inventário cancelado');
  invAtual = null;
  await invCarregarEstado();
}

async function invVerDetalhes(id){
  const d = await fetch(`/api/inventarios/${id}`).then(r=>r.json());
  const inv = d.inventario;
  const itens = d.itens.filter(i=>i.diferenca!==null&&Math.abs(i.diferenca)>0.0001);
  const data = new Date(inv.finalizado_em||inv.criado_em).toLocaleString('pt-BR');
  let html=`<strong>${inv.titulo}</strong><br><small style="color:var(--muted)">${data}</small>`;
  if(!itens.length){
    html+=`<div style="margin-top:12px;color:var(--accent2)">✅ Nenhuma diferença encontrada neste inventário.</div>`;
  } else {
    html+=`<div style="margin-top:12px;font-size:12px;color:var(--muted)">Divergências registradas:</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:6px">
      <thead><tr style="color:var(--muted)"><th style="text-align:left;padding:4px 8px">Produto</th><th style="padding:4px 8px">Sistema</th><th style="padding:4px 8px">Contado</th><th style="padding:4px 8px">Diferença</th></tr></thead>
      <tbody>${itens.map(i=>{
        const cor=i.diferenca>0?'var(--accent2)':'var(--danger)';
        return `<tr style="border-top:1px solid var(--border)">
          <td style="padding:5px 8px">${i.nome}</td>
          <td style="padding:5px 8px;text-align:center">${i.quantidade_sistema} ${i.unidade}</td>
          <td style="padding:5px 8px;text-align:center">${i.quantidade_contada} ${i.unidade}</td>
          <td style="padding:5px 8px;text-align:center;color:${cor};font-weight:700">${i.diferenca>0?'+':''}${i.diferenca.toLocaleString('pt-BR',{maximumFractionDigits:3})}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }
  document.getElementById('inv-finalizar-resumo').innerHTML=html;
  // Reusa o modal de finalizar como visualizador (esconde o botão de confirmar)
  document.querySelector('#modal-inv-finalizar .modal-footer .btn-success').style.display='none';
  document.getElementById('modal-inv-finalizar').classList.remove('hidden');
}

// Compatibilidade com função antiga (contagem rápida ainda funciona)
async function confirmarContagemInventario(){
  const divergentes=invItens.filter(i=>Math.abs((i.quantidade_contada??i.quantidade_sistema)-i.quantidade_sistema)>0.0001);
  if(!divergentes.length){toast('Nenhuma diferença encontrada, nada para ajustar');return;}
  if(!confirm(`Confirmar ajuste de ${divergentes.length} produto(s)?`)) return;
  const itens=divergentes.map(i=>({produto_id:i.produto_id,quantidade_contada:i.quantidade_contada}));
  const res=await fetch('/api/inventario/aplicar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({itens})});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast(`${d.ajustados} produto(s) ajustado(s)!`);
  produtos=await fetch('/api/produtos').then(r=>r.json());
  await invCarregarEstado();
}
