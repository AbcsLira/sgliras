// ═══════════════════════════════════════
// Dashboard
// ═══════════════════════════════════════
async function carregarDashboard(){
  // Saudação dinâmica baseada no horário do dia
  const hora=new Date().getHours();
  const periodo=hora<12?'Bom dia':hora<18?'Boa tarde':'Boa noite';
  const primeiroNome=(me.nome||'').split(' ')[0]||'';
  document.getElementById('dash-saudacao').textContent=`${periodo}${primeiroNome?', '+primeiroNome:''}! 👋`;

  const d=await fetch('/api/dashboard').then(r=>r.json());
  document.getElementById('d-total').textContent=d.total_produtos;
  document.getElementById('d-criticos').textContent=d.criticos;
  document.getElementById('d-zerados').textContent=d.sem_estoque;
  if(d.valor_total!==null&&d.valor_total!==undefined){
    document.getElementById('card-valor').classList.remove('hidden');
    document.getElementById('d-valor').textContent='R$ '+d.valor_total.toLocaleString('pt-BR',{minimumFractionDigits:2});
  }
  // ── Faixa de avisos (validade + críticos) ──
  const vencidos=d.vencidos||[];
  const proximos=d.proximos_vencimento||[];
  const totalAlertaValidade=vencidos.length+proximos.length;
  const totalCriticos=(d.criticos||0)+(d.sem_estoque||0);

  const blocoValidade=totalAlertaValidade===0
    ? `<div class="aviso-bloco ok">
         <div class="aviso-icone">✓</div>
         <div>
           <div class="aviso-titulo">Nenhum produto vencido ou próximo do vencimento</div>
           <div class="aviso-texto">Tudo em dia! 🎉</div>
         </div>
       </div>`
    : `<div class="aviso-bloco" style="background:linear-gradient(135deg,rgba(247,110,110,.14),rgba(30,41,59,.3))">
         <div class="aviso-icone" style="background:rgba(247,110,110,.18);color:var(--danger)">⏳</div>
         <div>
           <div class="aviso-titulo">${totalAlertaValidade} produto${totalAlertaValidade>1?'s':''} com atenção na validade</div>
           <div class="aviso-texto">${vencidos.length?vencidos.length+' vencido(s)':''}${vencidos.length&&proximos.length?' · ':''}${proximos.length?proximos.length+' vencendo em breve':''}</div>
         </div>
       </div>`;

  const blocoCriticos=totalCriticos===0
    ? `<div class="aviso-bloco ok">
         <div class="aviso-icone">✓</div>
         <div>
           <div class="aviso-titulo">Estoque sob controle</div>
           <div class="aviso-texto">Nenhum produto crítico no momento</div>
         </div>
       </div>`
    : `<div class="aviso-bloco alerta">
         <div class="aviso-icone">ℹ️</div>
         <div>
           <div class="aviso-titulo">Fique atento!</div>
           <div class="aviso-texto">${totalCriticos} produto${totalCriticos>1?'s':''} abaixo do mínimo ideal.<br>Verifique e reabasteça.</div>
         </div>
       </div>`;

  document.getElementById('avisos-faixa').innerHTML=blocoValidade+blocoCriticos;

  // ── Detalhamento de validade (tabela), só aparece se houver algo vencido/próximo ──
  const valDetalhe=document.getElementById('validade-detalhe');
  if(totalAlertaValidade===0){
    valDetalhe.innerHTML='';
  } else {
    let html='';
    if(vencidos.length){
      html+=`<div class="cat-card">
        <div class="cat-header">
          <span class="cat-title">⛔ Vencidos</span>
          <span class="cat-count" style="background:rgba(247,110,110,.15);color:var(--danger)">${vencidos.length}</span>
        </div>
        <div class="cat-card-scroll"><table><thead><tr><th>Produto</th><th>Qtd</th><th>Validade</th><th></th></tr></thead>
        <tbody>${vencidos.map(p=>`<tr>
          <td>${p.nome}</td>
          <td>${p.quantidade} <span class="badge badge-unit">${p.unidade||'un'}</span></td>
          <td>${formatarData(p.validade)}</td>
          <td><span class="badge badge-danger">${Math.abs(p.dias)}d atrás</span></td>
        </tr>`).join('')}</tbody></table></div>
      </div>`;
    }
    if(proximos.length){
      html+=`<div class="cat-card">
        <div class="cat-header">
          <span class="cat-title">⏳ Vencendo em breve</span>
          <span class="cat-count">${proximos.length}</span>
        </div>
        <div class="cat-card-scroll"><table><thead><tr><th>Produto</th><th>Qtd</th><th>Validade</th><th></th></tr></thead>
        <tbody>${proximos.map(p=>`<tr>
          <td>${p.nome}</td>
          <td>${p.quantidade} <span class="badge badge-unit">${p.unidade||'un'}</span></td>
          <td>${formatarData(p.validade)}</td>
          <td><span class="badge badge-warn">${p.dias===0?'Hoje':p.dias+'d'}</span></td>
        </tr>`).join('')}</tbody></table></div>
      </div>`;
    }
    valDetalhe.innerHTML=`<div class="section-title">⏳ Detalhamento de validade</div><div class="criticos-grid" style="margin-bottom:24px">${html}</div>`;
  }

  // ── Produtos críticos por categoria ──
  const grid=document.getElementById('criticos-grid');
  const g=d.criticos_por_categoria;
  if(!Object.keys(g).length){grid.innerHTML='<div class="empty">✅ Nenhum produto crítico!</div>';return;}
  grid.innerHTML=Object.entries(g).map(([cat,itens])=>`
    <div class="cat-card">
      <div class="cat-header">
        <span class="cat-title">${CAT_ICONS[cat]||'🏷️'} ${cat}</span>
        <span class="cat-count">${itens.length} produto${itens.length>1?'s':''}</span>
      </div>
      <div class="cat-card-scroll"><table><thead><tr><th>Produto</th><th>Qtd</th><th>Mín.</th><th></th></tr></thead>
      <tbody>${itens.map(p=>{
        const sub=p.sub_qtd_por_un&&p.sub_unidade
          ?` <small style="color:var(--muted)">(${(p.quantidade*p.sub_qtd_por_un).toLocaleString('pt-BR')} ${p.sub_unidade})</small>`:'' ;
        return `<tr>
          <td>${p.nome}</td>
          <td>${p.quantidade} <span class="badge badge-unit">${p.unidade||'un'}</span>${sub}</td>
          <td>${p.estoque_min}</td>
          <td>${p.quantidade===0?'<span class="badge badge-danger">Zerado</span>':'<span class="badge badge-warn">Baixo</span>'}</td>
        </tr>`;
      }).join('')}</tbody></table></div>
    </div>`).join('');
}

function formatarData(iso){
  if(!iso) return '—';
  const [ano,mes,dia]=iso.split('-');
  return `${dia}/${mes}/${ano}`;
}
