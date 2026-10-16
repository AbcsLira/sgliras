// ═══════════════════════════════════════
// Fornecedores
// ═══════════════════════════════════════
let fornecedores=[];
let editandoFornecedorId=null;

async function carregarFornecedores(){
  fornecedores=await fetch('/api/fornecedores').then(r=>r.json());
  renderFornecedores();
}

function renderFornecedores(){
  const tbody=document.getElementById('t-fornecedores');
  if(!fornecedores.length){tbody.innerHTML='<tr><td colspan="4" class="empty">Nenhum fornecedor cadastrado</td></tr>';return;}
  tbody.innerHTML=fornecedores.map(f=>`<tr>
    <td>${f.nome}</td>
    <td>${f.contato||'—'}</td>
    <td>${f.observacao||'—'}</td>
    <td>
      <button class="btn btn-ghost btn-sm" onclick="editarFornecedor(${f.id})">✏️</button>
      <button class="btn btn-danger btn-sm" onclick="deletarFornecedor(${f.id},'${f.nome.replace(/'/g,"\\'")}')">🗑️</button>
    </td>
  </tr>`).join('');
}

function abrirModalFornecedor(f=null){
  editandoFornecedorId=f?.id||null;
  document.getElementById('fornecedor-modal-titulo').textContent=f?'Editar Fornecedor':'Novo Fornecedor';
  document.getElementById('forn-nome').value=f?.nome||'';
  document.getElementById('forn-contato').value=f?.contato||'';
  document.getElementById('forn-obs').value=f?.observacao||'';
  document.getElementById('modal-fornecedor').classList.remove('hidden');
  setTimeout(()=>document.getElementById('forn-nome').focus(),80);
}

function editarFornecedor(id){
  const f=fornecedores.find(x=>x.id===id);
  if(f) abrirModalFornecedor(f);
}

async function salvarFornecedor(){
  const nome=document.getElementById('forn-nome').value.trim();
  if(!nome){toast('Informe o nome do fornecedor','var(--danger)');return;}
  const body={nome, contato:document.getElementById('forn-contato').value, observacao:document.getElementById('forn-obs').value};
  const url=editandoFornecedorId?`/api/fornecedores/${editandoFornecedorId}`:'/api/fornecedores';
  const res=await fetch(url,{method:editandoFornecedorId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast(editandoFornecedorId?'Fornecedor atualizado':'Fornecedor criado');
  fecharModal('modal-fornecedor');
  carregarFornecedores();
}

async function deletarFornecedor(id,nome){
  if(!confirm(`Excluir fornecedor "${nome}"? Os vínculos com produtos também serão removidos.`))return;
  await fetch(`/api/fornecedores/${id}`,{method:'DELETE'});
  toast('Fornecedor removido','var(--danger)');
  carregarFornecedores();
}

// ── Vínculo de fornecedor dentro do modal de produto ──
async function carregarFornecedoresDoProduto(pid){
  const wrap=document.getElementById('prod-fornecedores-wrap');
  wrap.classList.remove('hidden');

  if(!fornecedores.length) fornecedores=await fetch('/api/fornecedores').then(r=>r.json());
  const select=document.getElementById('prod-forn-select');
  select.innerHTML='<option value="">Selecione...</option>'+fornecedores.map(f=>`<option value="${f.id}">${f.nome}</option>`).join('');

  const lista=document.getElementById('prod-fornecedores-lista');

  if(!pid){
    // Produto novo: mostra os vínculos ainda não salvos (pendentes em memória)
    if(!fornecedoresPendentes.length){
      lista.innerHTML='<div style="font-size:12px;color:var(--muted)">Nenhum fornecedor adicionado ainda. Será vinculado ao salvar o produto.</div>';
      return;
    }
    lista.innerHTML=fornecedoresPendentes.map((v,idx)=>`<div style="display:flex;justify-content:space-between;align-items:center;
      padding:6px 10px;background:var(--card2);border-radius:6px;margin-bottom:4px;font-size:13px">
      <span>${v.fornecedor_nome}${v.contato?` <small style="color:var(--muted)">(${v.contato})</small>`:''}</span>
      <span style="display:flex;align-items:center;gap:8px">
        <strong>${fmtR(v.preco)}</strong>
        <button class="btn btn-danger" style="padding:2px 7px;font-size:11px" onclick="removerFornecedorPendente(${idx})">✕</button>
      </span>
    </div>`).join('');
    return;
  }

  // Produto existente: busca vínculos já salvos no banco
  const vinculos=await fetch(`/api/produtos/${pid}/fornecedores`).then(r=>r.json());
  if(!vinculos.length){
    lista.innerHTML='<div style="font-size:12px;color:var(--muted)">Nenhum fornecedor vinculado ainda.</div>';
    return;
  }
  lista.innerHTML=vinculos.map(v=>`<div style="display:flex;justify-content:space-between;align-items:center;
    padding:6px 10px;background:var(--card2);border-radius:6px;margin-bottom:4px;font-size:13px">
    <span>${v.fornecedor_nome}${v.contato?` <small style="color:var(--muted)">(${v.contato})</small>`:''}</span>
    <span style="display:flex;align-items:center;gap:8px">
      <strong>${fmtR(v.preco)}</strong>
      <button class="btn btn-danger" style="padding:2px 7px;font-size:11px" onclick="removerFornecedorDoProduto(${pid},${v.id})">✕</button>
    </span>
  </div>`).join('');
}

async function adicionarFornecedorAoProduto(){
  const fornecedorId=document.getElementById('prod-forn-select').value;
  const preco=document.getElementById('prod-forn-preco').value;
  if(!fornecedorId){toast('Selecione um fornecedor','var(--danger)');return;}

  if(!editandoProdId){
    // Produto novo: guarda em memória até salvar
    const f=fornecedores.find(x=>x.id===+fornecedorId);
    if(fornecedoresPendentes.find(p=>p.fornecedor_id===+fornecedorId)){
      toast('Fornecedor já adicionado','var(--danger)');return;
    }
    fornecedoresPendentes.push({fornecedor_id:+fornecedorId, fornecedor_nome:f?.nome, contato:f?.contato, preco:+preco||0});
    document.getElementById('prod-forn-preco').value='';
    toast('Fornecedor adicionado (será vinculado ao salvar)');
    carregarFornecedoresDoProduto(null);
    return;
  }

  const res=await fetch(`/api/produtos/${editandoProdId}/fornecedores`,{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fornecedor_id:+fornecedorId, preco:+preco||0})});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  document.getElementById('prod-forn-preco').value='';
  toast('Fornecedor vinculado');
  carregarFornecedoresDoProduto(editandoProdId);
}

function removerFornecedorPendente(idx){
  fornecedoresPendentes.splice(idx,1);
  carregarFornecedoresDoProduto(null);
}

async function removerFornecedorDoProduto(pid,vid){
  await fetch(`/api/produtos/${pid}/fornecedores/${vid}`,{method:'DELETE'});
  carregarFornecedoresDoProduto(pid);
}
