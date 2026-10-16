// ── Status de Backup ──────────────────────────────────────────────────────
async function verificarStatusBackup(){
  if(me.perfil!=='admin') return;
  try{
    const s=await fetch('/api/status-backup').then(r=>r.json());
    const pill=document.getElementById('backup-status-pill');
    if(!pill) return;

    // Definir cor e mensagem baseado no status
    let cor, icone, msg;
    if(!s.banco_ok){
      cor='rgba(239,68,68,.2)'; icone='🔴'; msg='Banco com erro!';
    } else if(!s.backup_hoje){
      cor='rgba(245,158,11,.15)'; icone='🟡'; msg='Sem backup hoje';
    } else {
      cor='rgba(34,197,94,.12)'; icone='🟢'; msg='Backup em dia';
    }

    pill.style.display='block';
    pill.style.background=cor;
    pill.style.color='var(--text)';
    pill.innerHTML=`${icone} ${msg}`;

    // Atualizar painel detalhado se estiver na tela de usuários
    const painel=document.getElementById('backup-status-painel');
    if(painel&&painel.offsetParent!==null){
      renderStatusBackup(s, painel);
    }
  }catch(e){
    console.log('Status backup indisponível:', e);
  }
}

function renderStatusBackup(s, painel){
  const ultimoFmt = s.ultimo_backup
    ? new Date(s.ultimo_backup).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})
    : 'Nenhum';
  const corBanco = s.banco_ok ? 'var(--accent2)' : 'var(--danger)';
  const corBackup = s.backup_hoje ? 'var(--accent2)' : 'var(--warn)';
  painel.innerHTML=`
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:4px">
      <div class="table-wrap" style="padding:14px 16px">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px">🗃️ Integridade do banco</div>
        <div style="font-size:16px;font-weight:700;color:${corBanco}">${s.banco_ok?'✅ OK':'❌ Erro!'}</div>
        <div style="font-size:11px;color:var(--muted)">${s.tamanho_banco_kb} KB</div>
      </div>
      <div class="table-wrap" style="padding:14px 16px">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px">💾 Backup de hoje</div>
        <div style="font-size:16px;font-weight:700;color:${corBackup}">${s.backup_hoje?'✅ Feito':'⚠️ Pendente'}</div>
        <div style="font-size:11px;color:var(--muted)">${s.total_backups_internos} arquivo(s) salvos</div>
      </div>
      <div class="table-wrap" style="padding:14px 16px">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px">🕐 Último backup</div>
        <div style="font-size:13px;font-weight:600">${ultimoFmt}</div>
        <div style="font-size:11px;color:var(--muted)">backup interno</div>
      </div>
    </div>`;
}

function navegarParaBackup(){
  navegarPara('usuarios');
  setTimeout(()=>{
    const painel=document.getElementById('backup-status-painel');
    if(painel) verificarStatusBackup();
  }, 300);
}

// ── Sidebar recolhível ────────────────────────────────────────────────────
function toggleSidebar(){
  const sb=document.getElementById('sidebar');
  const btn=document.getElementById('btn-toggle-sb');
  const recolhida=sb.classList.toggle('recolhida');
  btn.textContent=recolhida?'▶':'◀';
  btn.style.left=recolhida?'46px':'218px';
  localStorage.setItem('sidebar_recolhida', recolhida?'1':'0');
}

function toggleNavGrupo(id){
  const sb=document.getElementById('sidebar');
  // Se sidebar estiver recolhida, expande ela primeiro e abre o grupo
  if(sb.classList.contains('recolhida')){
    toggleSidebar();
    const grupo=document.getElementById(id);
    const itens=document.getElementById(id+'-itens');
    if(grupo.classList.contains('fechado')){
      itens.style.maxHeight=itens.scrollHeight+'px';
      grupo.classList.remove('fechado');
      localStorage.setItem('grupo_'+id,'aberto');
    }
    return;
  }
  const grupo=document.getElementById(id);
  const itens=document.getElementById(id+'-itens');
  const aberto=!grupo.classList.contains('fechado');
  if(aberto){
    itens.style.maxHeight='0';
    grupo.classList.add('fechado');
  } else {
    itens.style.maxHeight=itens.scrollHeight+'px';
    grupo.classList.remove('fechado');
  }
  localStorage.setItem('grupo_'+id, aberto?'fechado':'aberto');
}

function restaurarEstadoSidebar(){
  if(localStorage.getItem('sidebar_recolhida')==='1'){
    const sb=document.getElementById('sidebar');
    const btn=document.getElementById('btn-toggle-sb');
    sb.classList.add('recolhida');
    btn.textContent='▶';
    btn.style.left='46px';
  }
  // Restaurar estado dos grupos
  ['nav-grupo-financeiro'].forEach(id=>{
    const estado=localStorage.getItem('grupo_'+id);
    if(estado==='fechado'){
      const grupo=document.getElementById(id);
      const itens=document.getElementById(id+'-itens');
      if(grupo&&itens){
        grupo.classList.add('fechado');
        itens.style.maxHeight='0';
      }
    }
  });
}

init();
