// ═══════════════════════════════════════
// Usuários
// ═══════════════════════════════════════
async function carregarUsuarios(){
  usuarios=await fetch('/api/usuarios').then(r=>r.json()); renderUsuarios();
  carregarBackups();
}

// ═══════════════════════════════════════
// Backups
// ═══════════════════════════════════════
async function carregarBackups(){
  const tbody=document.getElementById('t-backups');
  if(!tbody) return;
  const res=await fetch('/api/backups');
  if(!res.ok){tbody.innerHTML='<tr><td colspan="4" class="empty">Sem permissão</td></tr>';return;}
  const backups=await res.json();
  if(!backups.length){tbody.innerHTML='<tr><td colspan="4" class="empty">Nenhum backup ainda</td></tr>';return;}
  tbody.innerHTML=backups.map(b=>{
    const tipo=b.nome.includes('_manual')?'<span class="badge badge-ok">Manual</span>':'<span class="badge badge-unit">Automático</span>';
    return `<tr>
      <td><code style="font-size:11px">${b.nome}</code> ${tipo}</td>
      <td>${b.tamanho_kb} KB</td>
      <td>${b.criado_em}</td>
      <td><a class="btn btn-ghost btn-sm" href="/api/backups/${b.nome}" download>⬇️ Baixar</a></td>
    </tr>`;
  }).join('');
}

async function criarBackupManual(){
  const res=await fetch('/api/backups',{method:'POST'});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Backup criado: '+d.nome);
  carregarBackups();
}

// ═══════════════════════════════════════
// Log de Auditoria
// ═══════════════════════════════════════
const ACAO_BADGE={'criou':'badge-ok','editou':'badge-warn','excluiu':'badge-danger'};
const ACAO_LABEL={'criou':'Criou','editou':'Editou','excluiu':'Excluiu'};
const ENTIDADE_LABEL={'produto':'Produto','ficha':'Ficha de Custo','usuario':'Usuário'};

async function carregarLogAuditoria(){
  const tbody=document.getElementById('t-log-auditoria');
  tbody.innerHTML='<tr><td colspan="5" class="empty">Carregando...</td></tr>';
  const res=await fetch('/api/log-auditoria');
  if(res.status===403){
    tbody.innerHTML='<tr><td colspan="5" class="empty">Apenas administradores podem ver este log.</td></tr>';
    return;
  }
  const log=await res.json();
  if(!log.length){
    tbody.innerHTML='<tr><td colspan="5" class="empty">Nenhuma ação registrada ainda.</td></tr>';
    return;
  }
  tbody.innerHTML=log.map(l=>{
    const data=new Date(l.criado_em).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
    return `<tr>
      <td style="white-space:nowrap;font-size:12px">${data}</td>
      <td>${l.usuario_nome||'—'}</td>
      <td><span class="badge ${ACAO_BADGE[l.acao]||'badge-ok'}">${ACAO_LABEL[l.acao]||l.acao}</span></td>
      <td>${ENTIDADE_LABEL[l.entidade]||l.entidade}: <strong>${l.entidade_nome||'—'}</strong></td>
      <td style="font-size:12px;color:var(--muted)">${l.detalhes||'—'}</td>
    </tr>`;
  }).join('');
}

function renderUsuarios(){
  const tbody=document.getElementById('t-usuarios');
  if(!usuarios.length){tbody.innerHTML='<tr><td colspan="6" class="empty">Nenhum usuário</td></tr>';return;}
  tbody.innerHTML=usuarios.map(u=>`<tr>
    <td>${u.nome}</td><td><code>${u.usuario}</code></td>
    <td><span class="badge ${PERFIL_BADGE[u.perfil]||'badge-ok'}">${PERFIL_LABEL[u.perfil]||u.perfil}</span></td>
    <td>${u.ativo?'<span class="badge badge-ok">Ativo</span>':'<span class="badge badge-warn">Inativo</span>'}</td>
    <td>${new Date(u.criado_em).toLocaleDateString('pt-BR')}</td>
    <td>
      <button class="btn btn-ghost btn-sm" onclick="editarUsuario(${u.id})">✏️</button>
      <button class="btn btn-danger btn-sm" onclick="deletarUsuario(${u.id},'${u.nome.replace(/'/g,"\\'")}')">🗑️</button>
    </td></tr>`).join('');
}
function abrirModalUsuario(u=null){
  editandoUserId=u?u.id:null;
  document.getElementById('mu-titulo').textContent=u?'Editar Usuário':'Novo Usuário';
  document.getElementById('u-nome').value=u?.nome||'';
  document.getElementById('u-usuario').value=u?.usuario||'';
  document.getElementById('u-perfil').value=u?.perfil||'caixa';
  document.getElementById('u-ativo').value=u?.ativo??1;
  document.getElementById('u-senha').value='';
  document.getElementById('u-senha-label').textContent=u?'Nova senha (deixe vazio para não alterar)':'Senha *';
  atualizarInfoPerfil();
  document.getElementById('modal-usuario').classList.remove('hidden');
}
function editarUsuario(id){const u=usuarios.find(x=>x.id===id);if(u)abrirModalUsuario(u);}
function atualizarInfoPerfil(){
  const pf=document.getElementById('u-perfil').value;
  document.getElementById('u-perms-box').innerHTML=`<strong>Permissões:</strong> ${(PERFIL_PERMS[pf]||[]).join(', ')}`;
}
async function salvarUsuario(){
  const senha=document.getElementById('u-senha').value;
  if(!editandoUserId&&!senha){toast('Informe a senha','var(--danger)');return;}
  const body={nome:document.getElementById('u-nome').value.trim(),usuario:document.getElementById('u-usuario').value.trim(),
    perfil:document.getElementById('u-perfil').value,ativo:+document.getElementById('u-ativo').value};
  if(senha) body.senha=senha;
  if(!body.nome||!body.usuario){toast('Preencha nome e usuário','var(--danger)');return;}
  const res=await fetch(editandoUserId?`/api/usuarios/${editandoUserId}`:'/api/usuarios',
    {method:editandoUserId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast(editandoUserId?'Usuário atualizado!':'Usuário criado!');
  fecharModal('modal-usuario'); carregarUsuarios();
}
async function deletarUsuario(id,nome){
  if(!confirm(`Excluir "${nome}"?`))return;
  const res=await fetch(`/api/usuarios/${id}`,{method:'DELETE'});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Removido','var(--danger)'); carregarUsuarios();
}

// ═══════════════════════════════════════
// Senha
// ═══════════════════════════════════════
function abrirModalSenha(){
  ['s-atual','s-nova','s-conf'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('modal-senha').classList.remove('hidden');
}
async function salvarSenha(){
  const nova=document.getElementById('s-nova').value;
  const conf=document.getElementById('s-conf').value;
  if(nova!==conf){toast('As senhas não coincidem','var(--danger)');return;}
  if(nova.length<4){toast('Senha muito curta (mín. 4)','var(--danger)');return;}
  const res=await fetch('/api/auth/senha',{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({senha_atual:document.getElementById('s-atual').value,senha_nova:nova})});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Senha alterada!'); fecharModal('modal-senha');
}
