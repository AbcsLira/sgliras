
// ═══════════════════════════════════════
// Estado
// ═══════════════════════════════════════
let me={permissoes:[]};
let produtos=[], categorias=[], fichas=[], usuarios=[];
let editandoProdId=null, editandoFichaId=null, editandoUserId=null;
let fornecedoresPendentes=[]; // vínculos de fornecedor para produto ainda não salvo: [{fornecedor_id, fornecedor_nome, contato, preco}]
let movProdId=null, filtroTipo='';
let fichaIngs=[];
let custosFixos=[]; // cadastro reutilizável carregado do servidor
let fichaCustosFixos=[]; // custos fixos vinculados à ficha sendo editada: [{custo_fixo_id, nome, categoria, valor}]
let editandoCustoFixoId=null;
let filtroCatId=null;

const PERFIL_LABEL={admin:'Administrador',estoquista:'Estoquista',caixa:'Caixa'};
const PERFIL_BADGE={admin:'badge-perfil-admin',estoquista:'badge-perfil-estoquista',caixa:'badge-perfil-caixa'};
const PERFIL_PERMS={admin:['Dashboard','Produtos','Movimentações','Fichas de Custo','Usuários'],
                    estoquista:['Dashboard','Produtos','Movimentações'],caixa:['Dashboard','Movimentações (sem lucro)']};
const CAT_ICONS={'Alimentos':'🍞','Bebidas':'🥤','Limpeza':'🧹','Embalagens':'📦','Molhos':'🧂','Oficina':'🔧','Outros':'🗂️','Gelatos':'🍦','Sem categoria':'❓'};

// ═══════════════════════════════════════
// Init
// ═══════════════════════════════════════
async function init(){
  const r=await fetch('/api/auth/me');
  if(!r.ok){window.location.href='/login';return;}
  me=await r.json();
  me.id=me.id||null;
  document.getElementById('user-nome').textContent=me.nome;
  document.getElementById('user-perfil').textContent=me.perfil_label;
  document.querySelectorAll('.nav-item[data-perm]').forEach(el=>{
    if(!me.permissoes.includes(el.dataset.perm)) el.classList.add('hidden');
  });
  // Esconder grupo financeiro se não tiver permissão
  const grupoFin=document.getElementById('nav-grupo-financeiro');
  if(grupoFin && !me.permissoes.includes('financeiro')){
    grupoFin.style.display='none';
  } else if(grupoFin){
    // Inicializar max-height para animação funcionar
    const itens=document.getElementById('nav-grupo-financeiro-itens');
    itens.style.maxHeight=itens.scrollHeight+'px';
  }
  if(!me.permissoes.includes('fichas')){
    document.getElementById('th-venda').classList.add('hidden');
    document.getElementById('th-lucro').classList.add('hidden');
  }
  restaurarEstadoSidebar();
  verificarStatusBackup();
  // Restaurar última página visitada (evita voltar pro dashboard no F5)
  const paginaSalva=localStorage.getItem('pagina_atual');
  if(paginaSalva && paginaSalva!=='dashboard'){
    irParaPagina(paginaSalva);
  } else {
    carregarDashboard();
  }
  await carregarProdutos();
}

// ═══════════════════════════════════════
// Nav
// ═══════════════════════════════════════
document.querySelectorAll('.nav-item').forEach(el=>{
  el.addEventListener('click',()=>{
    if(el.classList.contains('hidden'))return;
    irParaPagina(el.dataset.page);
  });
});
function irParaPagina(page){
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  const nav=document.querySelector(`.nav-item[data-page="${page}"]`);
  if(nav) nav.classList.add('active');
  document.getElementById('page-'+page)?.classList.add('active');
  // Salvar página atual no localStorage para restaurar após F5
  localStorage.setItem('pagina_atual', page);
  if(page==='dashboard')     carregarDashboard();
  if(page==='produtos')      renderProdutos();
  if(page==='movimentacoes') carregarMovimentacoes();
  if(page==='fichas')        carregarFichas();
  if(page==='comparativo-fichas') carregarComparativoFichas();
  if(page==='fornecedores')  carregarFornecedores();
  if(page==='lista-compras') carregarSugestaoCompras();
  if(page==='inventario')    abrirInventario();
  if(page==='consumo')       abrirRelatorioConsumo();
  if(page==='usuarios')      { carregarUsuarios(); verificarStatusBackup(); }
  if(page==='log-auditoria') carregarLogAuditoria();
  if(page==='fin-fechamento')     finIniciarFechamento();
  if(page==='fin-cartoes')        cartoesIniciar();
  if(page==='fin-paes')           paesIniciar();
  if(page==='fin-massas')         massaIniciar();
  if(page==='fin-contas-pagar') finCarregarContasPagar({atualizar:true});
  if(page==='fin-contas-receber') finCarregarContasReceber({atualizar:true});
  if(page==='fin-resumo')         finIniciarResumo();
  if(page==='fin-fds')            fdsIniciar();
  if(page==='fin-relatorio')      finCarregarRelatorioMensal();
  if(page==='fin-resultado')      finIniciarResultado();
}

function toast(msg,cor='var(--accent2)'){
  const t=document.getElementById('toast');
  t.textContent=msg;t.style.borderColor=cor;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2800);
}
function fecharModal(id){document.getElementById(id).classList.add('hidden');}
async function sair(){await fetch('/api/auth/logout',{method:'POST'});window.location.href='/login';}
