// ═══════════════════════════════════════
// Fichas
// ═══════════════════════════════════════
async function carregarFichas(){
  if(!produtos.length) produtos=await fetch('/api/produtos').then(r=>r.json());
  fichas=await fetch('/api/fichas').then(r=>r.json());
  renderFichas();
}
function renderFichas(){
  const el=document.getElementById('fichas-lista');
  if(!fichas.length){el.innerHTML='<div class="empty">Nenhuma ficha. Clique em "+ Nova ficha".</div>';return;}
  el.innerHTML=fichas.map(f=>{
    const temV=f.preco_venda&&+f.preco_venda>0;
    const lucroBox=temV&&f.lucro_porcao!==null
      ?`<div class="num-box" style="border-top:3px solid ${f.lucro_porcao>=0?'var(--accent2)':'var(--danger)'}">
          <div class="num-val ${f.lucro_porcao>=0?'lucro-pos':'lucro-neg'}">${fmtR(f.lucro_porcao)}</div>
          <div class="num-label">Lucro/porção${f.margem_pct!==null?` (${f.margem_pct>=0?'+':''}${f.margem_pct.toFixed(1)}%)`:''}  </div>
        </div>`
      :`<div class="num-box"><div class="num-val lucro-dash">—</div><div class="num-label">Lucro/porção</div></div>`;
    return `<div class="ficha-card">
      <div class="ficha-header">
        <div><div class="ficha-nome">${f.nome}</div>
          <div class="ficha-meta"><span class="badge badge-cat">${f.categoria}</span>
            &nbsp;${f.rendimento} porção${f.rendimento>1?'s':''}${f.observacao?` · <em>${f.observacao}</em>`:''}</div>
        </div>
        <div style="display:flex;gap:6px">
          ${temV?`<button class="btn btn-ghost btn-sm" onclick="abrirHistoricoPreco(${f.id},'${f.nome.replace(/'/g,"\\'")}')" title="Histórico de preço">📈</button>`:''}
          <button class="btn btn-ghost btn-sm" onclick="editarFicha(${f.id})">✏️</button>
          <button class="btn btn-danger btn-sm" onclick="deletarFicha(${f.id},'${f.nome.replace(/'/g,"\\'")}')">🗑️</button>
        </div>
      </div>
      <div class="ficha-nums">
        <div class="num-box" style="border-top:3px solid var(--accent)"><div class="num-val">${fmtR(f.custo_total)}</div><div class="num-label">Custo total</div></div>
        <div class="num-box" style="border-top:3px solid var(--warn)"><div class="num-val">${fmtR(f.custo_porcao)}</div><div class="num-label">Custo/porção</div></div>
        ${temV?`<div class="num-box" style="border-top:3px solid var(--accent2)"><div class="num-val">${fmtR(+f.preco_venda)}</div><div class="num-label">Preço venda</div></div>`:''}
        ${lucroBox}
      </div>
      <div style="font-size:12px">${f.ingredientes.length?`
        <table style="width:100%"><thead><tr><th>Ingrediente</th><th>Qtd</th><th>Un.</th><th>Custo unit.</th><th>Subtotal</th></tr></thead>
        <tbody>${f.ingredientes.map(i=>`<tr><td>${i.produto_nome}</td><td>${i.quantidade}</td>
          <td><span class="badge badge-unit">${i.unidade}</span></td>
          <td>${fmtR(i.preco_custo)}</td><td>${fmtR(i.preco_custo*i.quantidade)}</td></tr>`).join('')}</tbody></table>`
        :'<span style="color:var(--muted)">Sem ingredientes</span>'}</div>
    </div>`;
  }).join('');
}
// Categorias de produtos relevantes como ingrediente de ficha de custo
const CATEGORIAS_INGREDIENTE=['Alimentos','Molhos','Embalagens'];
let fIngCatFiltro=null;

async function abrirModalFicha(f=null){
  editandoFichaId=f?f.id:null;
  document.getElementById('mf-titulo').textContent=f?'Editar Ficha':'Nova Ficha de Custo';
  document.getElementById('f-nome').value=f?.nome||'';
  document.getElementById('f-categoria').value=f?.categoria||'Sanduíche';
  document.getElementById('f-rendimento').value=f?.rendimento??1;
  document.getElementById('f-venda').value=f?.preco_venda||'';
  document.getElementById('f-obs').value=f?.observacao||'';
  document.getElementById('f-ing-busca').value='';
  fIngCatFiltro=null;
  construirIngCatChips();
  fichaIngs=f?f.ingredientes.map(i=>({produto_id:i.produto_id,produto_nome:i.produto_nome,
    quantidade:i.quantidade,unidade:i.unidade,preco_custo:i.preco_custo})):[];
  fichaCustosFixos=f?f.custos_fixos.map(c=>({custo_fixo_id:c.custo_fixo_id,nome:c.nome,categoria:c.categoria,valor:c.valor})):[];
  custosFixosGlobais=await fetch('/api/custos-fixos-globais').then(r=>r.json());
  renderIngModal(); filtrarIngModal();
  carregarCustosFixosNaFicha();
  document.getElementById('modal-ficha').classList.remove('hidden');
  setTimeout(()=>document.getElementById('f-nome').focus(),80);
}
function construirIngCatChips(){
  const el=document.getElementById('f-ing-cat-chips');
  el.innerHTML=`<span class="filter-chip ${fIngCatFiltro===null?'active':''}"
    onclick="setIngCatFiltro(null)">Todas</span>`+
    CATEGORIAS_INGREDIENTE.map(c=>`<span class="filter-chip ${fIngCatFiltro===c?'active':''}"
      onclick="setIngCatFiltro('${c}')">${CAT_ICONS[c]||'🏷️'} ${c}</span>`).join('');
}
function setIngCatFiltro(cat){
  fIngCatFiltro=cat;
  construirIngCatChips();
  filtrarIngModal();
}
function filtrarIngModal(){
  const q=document.getElementById('f-ing-busca').value.toLowerCase();
  const lista=document.getElementById('f-ing-lista');
  let disp=produtos.filter(p=>p.ativo!==0 && +p.preco_custo>0 && CATEGORIAS_INGREDIENTE.includes(p.categoria));
  if(fIngCatFiltro) disp=disp.filter(p=>p.categoria===fIngCatFiltro);
  const itens=q?disp.filter(p=>p.nome.toLowerCase().includes(q)||p.codigo.toLowerCase().includes(q)):disp;
  if(!itens.length){lista.innerHTML='<div style="padding:9px;color:var(--muted);font-size:12px">Nenhum ingrediente encontrado</div>';return;}
  lista.innerHTML=itens.map(p=>`<div class="p-opt" onclick="adicionarIng(${p.id})">
    <div><div class="pn">${p.nome}</div><div class="pi">${p.codigo} · <span class="badge badge-unit">${p.unidade||'un'}</span> · ${fmtR(+p.preco_custo)}</div></div>
    <div style="font-size:11px;color:var(--accent)">+ Add</div></div>`).join('');
}
function adicionarIng(pid){
  const p=produtos.find(x=>x.id===pid);if(!p)return;
  const ex=fichaIngs.find(i=>i.produto_id===pid);
  if(ex){ex.quantidade+=1;}else fichaIngs.push({produto_id:pid,produto_nome:p.nome,quantidade:1,unidade:p.unidade||'un',preco_custo:+p.preco_custo});
  renderIngModal();
}
function removerIng(pid){fichaIngs=fichaIngs.filter(i=>i.produto_id!==pid);renderIngModal();}
function renderIngModal(){
  const wrap=document.getElementById('f-ings-wrap');
  const rows=document.getElementById('f-ings-rows');
  if(!fichaIngs.length){wrap.classList.add('hidden');document.getElementById('f-preview').textContent='';return;}
  wrap.classList.remove('hidden');
  rows.innerHTML=`<div class="ing-row ing-header"><span>Ingrediente</span><span>Quantidade</span><span>Unidade</span><span></span></div>`
    +fichaIngs.map((ing,idx)=>`<div class="ing-row">
      <span>${ing.produto_nome}<br><small style="color:var(--muted)">${fmtR(ing.preco_custo)}/${ing.unidade}</small></span>
      <span><input type="number" min="0.001" step="0.001" value="${ing.quantidade}" style="width:78px;padding:4px 6px;font-size:12px"
        onchange="fichaIngs[${idx}].quantidade=+this.value;atualizarPreview()"></span>
      <span><select style="width:62px;padding:4px 6px;font-size:12px" onchange="fichaIngs[${idx}].unidade=this.value">
        ${['un','cx','fd','kg','g','ml','l'].map(u=>`<option ${ing.unidade===u?'selected':''}>${u}</option>`).join('')}
      </select></span>
      <span><button class="btn btn-danger" style="padding:3px 7px;font-size:11px" onclick="removerIng(${ing.produto_id})">✕</button></span>
    </div>`).join('');
  atualizarPreview();
}
function atualizarPreview(){
  const totalIngs=fichaIngs.reduce((s,i)=>s+(i.preco_custo*i.quantidade),0);
  const totalFixos=fichaCustosFixos.reduce((s,c)=>s+c.valor,0);
  const pv=+document.getElementById('f-venda').value||0;
  const globaisAtivos=(custosFixosGlobais||[]).filter(g=>g.ativo);
  const totalGlobais=globaisAtivos.reduce((s,g)=>s+(pv*(g.percentual/100)),0);
  const total=totalIngs+totalFixos+totalGlobais;
  const rend=+document.getElementById('f-rendimento').value||1;
  const por=total/rend;
  let h=`💰 Custo total: <strong>${fmtR(total)}</strong> &nbsp;|&nbsp; Custo/porção: <strong>${fmtR(por)}</strong>`;
  if(globaisAtivos.length){
    h+=`<br><span style="font-size:11px">📊 Inclui ${globaisAtivos.map(g=>`${g.nome} (${g.percentual}%)`).join(', ')} sobre o preço de venda</span>`;
  }
  if(pv>0){const lc=pv-por;const pct=por>0?(lc/por)*100:0;
    h+=` &nbsp;|&nbsp; Lucro: <strong style="color:${lc>=0?'var(--accent2)':'var(--danger)'}">${fmtR(lc)} (${pct>=0?'+':''}${pct.toFixed(1)}%)</strong>`;}
  document.getElementById('f-preview').innerHTML=h;
}
['f-rendimento','f-venda'].forEach(id=>document.getElementById(id).addEventListener('input',()=>{atualizarPreview();}));

// ── Custos Fixos vinculados à ficha (com suporte a pendentes em ficha nova) ──
async function carregarCustosFixosNaFicha(){
  if(!custosFixos.length) custosFixos=await fetch('/api/custos-fixos').then(r=>r.json());
  const select=document.getElementById('f-custo-fixo-select');
  const jaVinculadosIds=fichaCustosFixos.map(c=>c.custo_fixo_id);
  const disponiveis=custosFixos.filter(c=>!jaVinculadosIds.includes(c.id));
  select.innerHTML='<option value="">+ Vincular um custo fixo cadastrado...</option>'
    +disponiveis.map(c=>`<option value="${c.id}">${c.nome} (${c.categoria}) — ${fmtR(c.valor)}</option>`).join('');
  renderCustosFixosNaFicha();
}

function renderCustosFixosNaFicha(){
  const wrap=document.getElementById('f-custos-fixos-marcados');
  if(!fichaCustosFixos.length){
    wrap.innerHTML='<div style="font-size:12px;color:var(--muted)">Nenhum custo fixo vinculado ainda.</div>';
    atualizarPreview();
    return;
  }
  wrap.innerHTML=fichaCustosFixos.map(c=>`<div style="display:flex;justify-content:space-between;align-items:center;
    padding:6px 10px;background:var(--card2);border-radius:6px;margin-bottom:4px;font-size:13px">
    <span>${c.nome} <small style="color:var(--muted)">(${c.categoria})</small></span>
    <span style="display:flex;align-items:center;gap:8px">
      <strong>${fmtR(c.valor)}</strong>
      <button class="btn btn-danger" style="padding:2px 7px;font-size:11px" onclick="removerCustoFixoDaFicha(${c.custo_fixo_id})">✕</button>
    </span>
  </div>`).join('');
  atualizarPreview();
}

async function vincularCustoFixoNaFicha(){
  const select=document.getElementById('f-custo-fixo-select');
  const cid=+select.value;
  if(!cid) return;
  const c=custosFixos.find(x=>x.id===cid);
  if(!c) return;

  fichaCustosFixos.push({custo_fixo_id:c.id,nome:c.nome,categoria:c.categoria,valor:c.valor});

  if(editandoFichaId){
    await fetch(`/api/fichas/${editandoFichaId}/custos-fixos`,{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({custo_fixo_id:c.id})});
  }
  // Se for ficha nova, o vínculo fica só em memória (fichaCustosFixos) até salvar

  select.value='';
  carregarCustosFixosNaFicha();
}

async function removerCustoFixoDaFicha(cid){
  fichaCustosFixos=fichaCustosFixos.filter(c=>c.custo_fixo_id!==cid);
  if(editandoFichaId){
    await fetch(`/api/fichas/${editandoFichaId}/custos-fixos/${cid}`,{method:'DELETE'});
  }
  carregarCustosFixosNaFicha();
}
async function salvarFicha(){
  const nome=document.getElementById('f-nome').value.trim();
  if(!nome){toast('Informe o nome','var(--danger)');return;}
  const pv=document.getElementById('f-venda').value;
  const body={nome,categoria:document.getElementById('f-categoria').value,rendimento:+document.getElementById('f-rendimento').value||1,
    preco_venda:pv===''?null:+pv,observacao:document.getElementById('f-obs').value,
    ingredientes:fichaIngs.map(i=>({produto_id:i.produto_id,quantidade:i.quantidade,unidade:i.unidade}))};
  const res=await fetch(editandoFichaId?`/api/fichas/${editandoFichaId}`:'/api/fichas',
    {method:editandoFichaId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}

  // Se for ficha nova e tiver custos fixos pendentes, vincula agora que já temos o ID
  if(!editandoFichaId && fichaCustosFixos.length){
    const novoId=d.id;
    for(const c of fichaCustosFixos){
      await fetch(`/api/fichas/${novoId}/custos-fixos`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({custo_fixo_id:c.custo_fixo_id})});
    }
    fichaCustosFixos=[];
  }

  toast(editandoFichaId?'Ficha atualizada!':'Ficha criada!');
  fecharModal('modal-ficha'); carregarFichas();
}
async function editarFicha(id){if(!fichas.length)fichas=await fetch('/api/fichas').then(r=>r.json());const f=fichas.find(x=>x.id===id);if(f)abrirModalFicha(f);}
async function deletarFicha(id,nome){
  if(!confirm(`Excluir "${nome}"?`))return;
  await fetch(`/api/fichas/${id}`,{method:'DELETE'});toast('Ficha removida','var(--danger)');carregarFichas();
}

// ── Histórico de Preço de Venda ──
async function abrirHistoricoPreco(fid,nome){
  document.getElementById('hp-ficha-nome').textContent=`— ${nome}`;
  const lista=document.getElementById('historico-preco-lista');
  lista.innerHTML='<div class="empty">Carregando...</div>';
  document.getElementById('modal-historico-preco').classList.remove('hidden');

  const hist=await fetch(`/api/fichas/${fid}/historico-preco`).then(r=>r.json());
  if(!hist.length){
    lista.innerHTML='<div class="empty">Nenhuma alteração de preço registrada ainda.</div>';
    return;
  }
  lista.innerHTML=hist.map((h,idx)=>{
    const data=new Date(h.criado_em).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
    const primeiro=h.preco_anterior===null;
    let variacao='';
    if(!primeiro){
      const diff=h.preco_novo-h.preco_anterior;
      const pct=h.preco_anterior>0?(diff/h.preco_anterior)*100:0;
      const cor=diff>=0?'var(--accent2)':'var(--danger)';
      variacao=`<span style="color:${cor};font-size:12px">(${diff>=0?'+':''}${fmtR(diff)} · ${pct>=0?'+':''}${pct.toFixed(1)}%)</span>`;
    }
    return `<div style="padding:10px 12px;background:var(--card2);border-radius:8px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <strong style="font-size:15px">${fmtR(h.preco_novo)}</strong>
        ${variacao}
      </div>
      <div style="font-size:12px;color:var(--muted);margin-top:3px">
        ${primeiro?'Preço inicial':`Anterior: ${fmtR(h.preco_anterior)}`} · ${data}${h.usuario_nome?` · ${h.usuario_nome}`:''}
      </div>
    </div>`;
  }).join('');
}

// ── Cadastro de Custos Fixos (reutilizável entre fichas) ──
async function abrirModalCustosFixos(){
  custosFixos=await fetch('/api/custos-fixos').then(r=>r.json());
  editandoCustoFixoId=null;
  document.getElementById('cf-nome').value='';
  document.getElementById('cf-categoria').value='Sanduíche';
  document.getElementById('cf-valor').value='';
  renderCustosFixosLista();
  document.getElementById('modal-custos-fixos').classList.remove('hidden');
}

function renderCustosFixosLista(){
  const wrap=document.getElementById('custos-fixos-lista');
  if(!custosFixos.length){
    wrap.innerHTML='<div class="empty">Nenhum custo fixo cadastrado ainda.</div>';
    return;
  }
  const porCategoria={};
  custosFixos.forEach(c=>{ (porCategoria[c.categoria]=porCategoria[c.categoria]||[]).push(c); });

  wrap.innerHTML=Object.entries(porCategoria).map(([cat,itens])=>`
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--muted);margin:10px 0 6px">${cat}</div>
    ${itens.map(c=>`<div style="display:flex;justify-content:space-between;align-items:center;
      padding:7px 10px;background:var(--card2);border-radius:6px;margin-bottom:4px;font-size:13px">
      <span>${c.nome}</span>
      <span style="display:flex;align-items:center;gap:8px">
        <strong>${fmtR(c.valor)}</strong>
        <button class="btn btn-ghost" style="padding:2px 7px;font-size:11px" onclick="editarCustoFixo(${c.id})">✏️</button>
        <button class="btn btn-danger" style="padding:2px 7px;font-size:11px" onclick="deletarCustoFixo(${c.id},'${c.nome.replace(/'/g,"\\'")}')">🗑️</button>
      </span>
    </div>`).join('')}
  `).join('');
}

async function salvarCustoFixo(){
  const nome=document.getElementById('cf-nome').value.trim();
  const valor=document.getElementById('cf-valor').value;
  if(!nome){toast('Informe o nome','var(--danger)');return;}
  const body={nome, categoria:document.getElementById('cf-categoria').value, valor:+valor||0};
  const url=editandoCustoFixoId?`/api/custos-fixos/${editandoCustoFixoId}`:'/api/custos-fixos';
  const res=await fetch(url,{method:editandoCustoFixoId?'PUT':'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}

  toast(editandoCustoFixoId?'Custo fixo atualizado':'Custo fixo cadastrado');
  editandoCustoFixoId=null;
  document.getElementById('cf-nome').value='';
  document.getElementById('cf-valor').value='';
  custosFixos=await fetch('/api/custos-fixos').then(r=>r.json());
  renderCustosFixosLista();
}

function editarCustoFixo(id){
  const c=custosFixos.find(x=>x.id===id); if(!c) return;
  editandoCustoFixoId=id;
  document.getElementById('cf-nome').value=c.nome;
  document.getElementById('cf-categoria').value=c.categoria;
  document.getElementById('cf-valor').value=c.valor;
}

async function deletarCustoFixo(id,nome){
  if(!confirm(`Excluir "${nome}"? Ele será removido de todas as fichas que o usam.`))return;
  await fetch(`/api/custos-fixos/${id}`,{method:'DELETE'});
  toast('Custo fixo removido','var(--danger)');
  custosFixos=await fetch('/api/custos-fixos').then(r=>r.json());
  renderCustosFixosLista();
}

// ── Custos Fixos Globais (%) ──
let custosFixosGlobais=[];
let editandoCustoFixoGlobalId=null;

async function abrirModalCustosFixosGlobais(){
  custosFixosGlobais=await fetch('/api/custos-fixos-globais').then(r=>r.json());
  editandoCustoFixoGlobalId=null;
  document.getElementById('cfg-nome').value='';
  document.getElementById('cfg-percentual').value='';
  renderCustosFixosGlobaisLista();
  document.getElementById('modal-custos-fixos-globais').classList.remove('hidden');
}

function renderCustosFixosGlobaisLista(){
  const wrap=document.getElementById('custos-fixos-globais-lista');
  if(!custosFixosGlobais.length){
    wrap.innerHTML='<div class="empty">Nenhum custo fixo global cadastrado ainda.</div>';
    return;
  }
  wrap.innerHTML=custosFixosGlobais.map(g=>`<div style="display:flex;justify-content:space-between;align-items:center;
    padding:8px 10px;background:var(--card2);border-radius:6px;margin-bottom:6px;font-size:13px">
    <span style="display:flex;align-items:center;gap:8px">
      <label class="toggle-switch" style="margin:0">
        <input type="checkbox" ${g.ativo?'checked':''} onchange="toggleCustoFixoGlobal(${g.id},this.checked)">
        <span class="toggle-slider"></span>
      </label>
      <span style="${g.ativo?'':'color:var(--muted);text-decoration:line-through'}">${g.nome}</span>
    </span>
    <span style="display:flex;align-items:center;gap:8px">
      <strong>${g.percentual.toFixed(2)}%</strong>
      <button class="btn btn-ghost" style="padding:2px 7px;font-size:11px" onclick="editarCustoFixoGlobal(${g.id})">✏️</button>
      <button class="btn btn-danger" style="padding:2px 7px;font-size:11px" onclick="deletarCustoFixoGlobal(${g.id},'${g.nome.replace(/'/g,"\\'")}')">🗑️</button>
    </span>
  </div>`).join('');
}

async function salvarCustoFixoGlobal(){
  const nome=document.getElementById('cfg-nome').value.trim();
  const percentual=document.getElementById('cfg-percentual').value;
  if(!nome){toast('Informe o nome','var(--danger)');return;}
  const body={nome, percentual:+percentual||0, ativo:true};
  const url=editandoCustoFixoGlobalId?`/api/custos-fixos-globais/${editandoCustoFixoGlobalId}`:'/api/custos-fixos-globais';
  if(editandoCustoFixoGlobalId){
    const atual=custosFixosGlobais.find(g=>g.id===editandoCustoFixoGlobalId);
    body.ativo=atual?!!atual.ativo:true;
  }
  const res=await fetch(url,{method:editandoCustoFixoGlobalId?'PUT':'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}

  toast(editandoCustoFixoGlobalId?'Custo fixo global atualizado':'Custo fixo global cadastrado');
  editandoCustoFixoGlobalId=null;
  document.getElementById('cfg-nome').value='';
  document.getElementById('cfg-percentual').value='';
  custosFixosGlobais=await fetch('/api/custos-fixos-globais').then(r=>r.json());
  renderCustosFixosGlobaisLista();
}

function editarCustoFixoGlobal(id){
  const g=custosFixosGlobais.find(x=>x.id===id); if(!g) return;
  editandoCustoFixoGlobalId=id;
  document.getElementById('cfg-nome').value=g.nome;
  document.getElementById('cfg-percentual').value=g.percentual;
}

async function toggleCustoFixoGlobal(id,ativo){
  const g=custosFixosGlobais.find(x=>x.id===id); if(!g) return;
  await fetch(`/api/custos-fixos-globais/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({nome:g.nome, percentual:g.percentual, ativo})});
  g.ativo=ativo?1:0;
  toast(ativo?`"${g.nome}" ativado em todas as fichas`:`"${g.nome}" desativado`);
  renderCustosFixosGlobaisLista();
}

async function deletarCustoFixoGlobal(id,nome){
  if(!confirm(`Excluir "${nome}"? Ele deixará de ser aplicado em todas as fichas.`))return;
  await fetch(`/api/custos-fixos-globais/${id}`,{method:'DELETE'});
  toast('Custo fixo global removido','var(--danger)');
  custosFixosGlobais=await fetch('/api/custos-fixos-globais').then(r=>r.json());
  renderCustosFixosGlobaisLista();
}

// ═══════════════════════════════════════
// Comparativo de Fichas
// ═══════════════════════════════════════
async function carregarComparativoFichas(){
  const todasFichas=await fetch('/api/fichas').then(r=>r.json());
  // Só entram no comparativo fichas que têm margem calculável (preço de venda cadastrado)
  const comMargem=todasFichas.filter(f=>f.margem_pct!==null&&f.margem_pct!==undefined);

  if(!comMargem.length){
    document.getElementById('comparativo-vazio').classList.remove('hidden');
    document.getElementById('comparativo-conteudo').classList.add('hidden');
    return;
  }
  document.getElementById('comparativo-vazio').classList.add('hidden');
  document.getElementById('comparativo-conteudo').classList.remove('hidden');

  // Ordena por margem de lucro (%) decrescente, como padrão
  comMargem.sort((a,b)=>b.margem_pct-a.margem_pct);

  const margemMedia=comMargem.reduce((acc,f)=>acc+f.margem_pct,0)/comMargem.length;
  document.getElementById('comp-total-fichas').textContent=comMargem.length;
  document.getElementById('comp-margem-media').textContent=margemMedia.toFixed(1)+'%';

  function corMargem(pct){
    if(pct<0) return 'var(--danger)';
    if(pct<30) return 'var(--warn)';
    return 'var(--accent2)';
  }

  function linhaRanking(f){
    return `<div style="display:flex;justify-content:space-between;align-items:center;
      padding:8px 12px;background:var(--card2);border-radius:8px;margin-bottom:6px">
      <span style="font-size:13px">${f.nome}</span>
      <strong style="color:${corMargem(f.margem_pct)}">${f.margem_pct>=0?'+':''}${f.margem_pct.toFixed(1)}%</strong>
    </div>`;
  }

  const top5Rentaveis=comMargem.slice(0,5);
  const top5Fracas=[...comMargem].sort((a,b)=>a.margem_pct-b.margem_pct).slice(0,5);

  document.getElementById('comp-top-rentaveis').innerHTML=top5Rentaveis.map(linhaRanking).join('');
  document.getElementById('comp-top-fracas').innerHTML=top5Fracas.map(linhaRanking).join('');

  const tbody=document.getElementById('t-comparativo');
  tbody.innerHTML=comMargem.map(f=>{
    const cor=corMargem(f.margem_pct);
    return `<tr>
      <td>${f.nome}</td>
      <td>${f.categoria}</td>
      <td>${fmtR(f.custo_porcao)}</td>
      <td>${fmtR(f.preco_venda)}</td>
      <td style="color:${cor}">${fmtR(f.lucro_porcao)}</td>
      <td><strong style="color:${cor}">${f.margem_pct>=0?'+':''}${f.margem_pct.toFixed(1)}%</strong></td>
    </tr>`;
  }).join('');
}
