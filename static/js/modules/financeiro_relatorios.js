// ═══════════════════════════════════════
// RESULTADO DO MÊS
// ═══════════════════════════════════════
function finIniciarResultado(){
  const mes=hojeLocal().slice(0,7);
  document.getElementById('resultado-mes').value=mes;
  finCarregarResultado();
}

async function finCarregarResultado(){
  const mes=document.getElementById('resultado-mes').value;
  if(!mes) return;
  const d=await fetch(`/api/fin/comparativo-resultado?mes=${mes}`).then(r=>r.json());
  const conteudo=document.getElementById('resultado-conteudo');
  const vazio=document.getElementById('resultado-vazio');

  if(!d.receita.dias_lancados && !d.total_despesas_cap){
    conteudo.classList.add('hidden');
    vazio.textContent='Nenhum dado encontrado para este mês.';
    vazio.classList.remove('hidden');
    return;
  }
  vazio.classList.add('hidden');
  conteudo.classList.remove('hidden');

  // Cards principais
  document.getElementById('res-receita-total').textContent=finFmt(d.receita.total);
  document.getElementById('res-despesas-total').textContent=finFmt(d.total_despesas_cap);

  const resultado=d.resultado_estimado;
  const cardRes=document.getElementById('res-resultado-card');
  const elRes=document.getElementById('res-resultado');
  elRes.textContent=finFmt(Math.abs(resultado));
  elRes.style.color=resultado>=0?'var(--accent2)':'var(--danger)';
  cardRes.style.borderTop=`3px solid ${resultado>=0?'var(--accent2)':'var(--danger)'}`;
  document.querySelector('#res-resultado-card .card-label').textContent=
    resultado>=0?'Resultado estimado ▲':'Resultado estimado ▼';

  // Detalhe de receitas
  const recDetalhe=document.getElementById('res-receitas-detalhe');
  const MESES_PT=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  const [ano,mesNum]=mes.split('-');
  recDetalhe.innerHTML=`
    <div style="font-size:12px;color:var(--muted);margin-bottom:6px">${MESES_PT[parseInt(mesNum)-1]}/${ano} · ${d.receita.dias_lancados} dia(s) com fechamento</div>
    ${linhaReceita('Venda (C+D+V+PIX+Din)', d.receita.venda_total)}
    ${d.receita.delivery>0?linhaReceita('↳ Delivery (informativo)', d.receita.delivery, true):''}
    ${d.receita.frete>0?linhaReceita('↳ Frete cobrado (informativo)', d.receita.frete, true):''}
    <div style="border-top:1px solid var(--border);margin-top:8px;padding-top:8px;display:flex;justify-content:space-between">
      <span style="font-weight:700">Total receita</span>
      <span style="font-weight:700;color:var(--accent2)">${finFmt(d.receita.venda_total)}</span>
    </div>`;

  // Detalhe de despesas
  const despDetalhe=document.getElementById('res-despesas-detalhe');
  if(!d.despesas_cap.length && !d.custos_operacionais.paes && !d.custos_operacionais.massas){
    despDetalhe.innerHTML='<div style="color:var(--muted);font-size:12px">Nenhuma despesa paga registrada neste mês.</div>';
  } else {
    let linhas='';
    // Custos operacionais calculados
    if(d.custos_operacionais.paes>0)
      linhas+=linhaDespesa('Custo de pães',d.custos_operacionais.paes,'calc');
    if(d.custos_operacionais.massas>0)
      linhas+=linhaDespesa('Custo de massas',d.custos_operacionais.massas,'calc');
    // Contas a pagar pagas
    d.despesas_cap.forEach(c=>{ linhas+=linhaDespesa(c.categoria,c.total_valor,'cap'); });
    const totalGeral=d.total_despesas_cap+d.custos_operacionais.paes+d.custos_operacionais.massas;
    despDetalhe.innerHTML=linhas+`
      <div style="border-top:1px solid var(--border);margin-top:8px;padding-top:8px;display:flex;justify-content:space-between">
        <span style="font-weight:700">Total despesas</span>
        <span style="font-weight:700;color:var(--danger)">${finFmt(totalGeral)}</span>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">
        <span style="background:rgba(79,124,255,.15);padding:1px 6px;border-radius:10px;margin-right:4px">calc</span>calculado do sistema
        <span style="background:rgba(255,255,255,.06);padding:1px 6px;border-radius:10px;margin-right:4px">C.A.P.</span>contas a pagar
      </div>`;
  }
}

function linhaReceita(label, valor, informativo=false){
  return `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border);font-size:13px">
    <span style="color:${informativo?'var(--muted)':'var(--muted)'}">${label}</span>
    <span style="${informativo?'color:var(--muted);font-style:italic':'font-weight:600;color:var(--accent2)'}">${informativo?'':''} ${finFmt(valor)}</span>
  </div>`;
}

function linhaDespesa(label, valor, origem){
  const badge=origem==='calc'
    ? `<span style="font-size:10px;background:rgba(79,124,255,.15);color:var(--accent);padding:1px 5px;border-radius:10px;margin-left:4px">calc</span>`
    : `<span style="font-size:10px;background:rgba(255,255,255,.06);color:var(--muted);padding:1px 5px;border-radius:10px;margin-left:4px">C.A.P.</span>`;
  return `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border);font-size:13px">
    <span style="color:var(--muted)">${label}${badge}</span>
    <span style="font-weight:600;color:var(--danger)">${finFmt(valor)}</span>
  </div>`;
}

// ── Alertas de vencimento ──────────────────────────────────────────────────
let finAlertasVersao=0;
async function finCarregarAlertasVencimento({dados}={}){
  const versao=++finAlertasVersao;
  const wrap=document.getElementById('fin-alertas-venc');
  const alertas=dados??await fetch('/api/fin/alertas-vencimento').then(r=>{
    if(!r.ok) throw new Error('Não foi possível carregar os alertas.');
    return r.json();
  });
  if(versao!==finAlertasVersao) return;
  if(!alertas.length){wrap.classList.add('hidden');return;}
  wrap.classList.remove('hidden');
  const vencidas=alertas.filter(a=>a.dias_restantes<0);
  const hoje=alertas.filter(a=>a.dias_restantes===0);
  const proximas=alertas.filter(a=>a.dias_restantes>0);
  let html='<div style="background:linear-gradient(135deg,rgba(239,68,68,.12),rgba(30,41,59,.3));border:1px solid rgba(239,68,68,.3);border-radius:14px;padding:14px 18px">';
  html+=`<div style="font-weight:700;font-size:13px;color:var(--danger);margin-bottom:8px">⚠️ Atenção — ${alertas.length} conta${alertas.length>1?'s':''} vencendo ou já vencida${alertas.length>1?'s':''}</div>`;
  html+='<div style="display:flex;flex-wrap:wrap;gap:8px">';
  alertas.forEach(a=>{
    const cor=a.dias_restantes<0?'var(--danger)':a.dias_restantes===0?'var(--warn)':'var(--accent)';
    const label=a.dias_restantes<0?`${Math.abs(Math.round(a.dias_restantes))}d atrás`:a.dias_restantes===0?'Hoje':`${Math.round(a.dias_restantes)}d`;
    html+=`<span style="background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:8px;padding:5px 10px;font-size:12px">
      <span style="color:${cor};font-weight:700">${label}</span>
      · ${a.descricao}
      · <strong>${finFmt(a.valor)}</strong>
      <button onclick="finPagarConta(${a.id})" style="background:none;border:none;color:var(--accent2);cursor:pointer;font-size:11px;margin-left:4px;padding:0">✅</button>
    </span>`;
  });
  html+='</div></div>';
  wrap.innerHTML=html;
}

// ── Pães com custo no resumo ───────────────────────────────────────────────
// (já integrado no finCarregarResumo via campo custo_paes do backend)

// ── Relatório Mês a Mês ───────────────────────────────────────────────────
async function finCarregarRelatorioMensal(){
  const tbody=document.getElementById('t-fin-relatorio-mensal');
  tbody.innerHTML='<tr><td colspan="10" class="empty">Carregando...</td></tr>';
  const rows=await fetch('/api/fin/relatorio-mensal').then(r=>r.json());
  if(!rows.length){tbody.innerHTML='<tr><td colspan="10" class="empty">Nenhum mês com fechamento registrado ainda.</td></tr>';return;}
  // Calcular média e máximo para barras visuais
  const maxVenda=Math.max(...rows.map(r=>r.venda_total||0));
  tbody.innerHTML=rows.map((r,i)=>{
    const [ano,mes]=r.mes.split('-');
    const nomeMes=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][parseInt(mes)-1];
    const pct=maxVenda>0?Math.round((r.venda_total/maxVenda)*100):0;
    const anterior=rows[i+1];
    let variacao='';
    if(anterior&&anterior.venda_total>0){
      const diff=((r.venda_total-anterior.venda_total)/anterior.venda_total*100);
      const cor=diff>=0?'var(--accent2)':'var(--danger)';
      variacao=`<span style="font-size:10px;color:${cor};margin-left:4px">${diff>=0?'▲':'▼'}${Math.abs(diff).toFixed(1)}%</span>`;
    }
    return `<tr>
      <td style="white-space:nowrap;font-weight:600">${nomeMes}/${ano}${variacao}</td>
      <td style="color:var(--muted)">${r.dias}</td>
      <td>
        <div style="font-weight:700;color:var(--accent2)">${finFmt(r.venda_total)}</div>
        <div style="height:3px;background:rgba(255,255,255,.06);border-radius:2px;margin-top:3px;width:120px">
          <div style="height:100%;width:${pct}%;background:var(--accent2);border-radius:2px"></div>
        </div>
      </td>
      <td>${finFmt(r.cartao_total)}</td>
      <td>${finFmt(r.pix_total)}</td>
      <td>${finFmt(r.dinheiro_total)}</td>
      <td>${finFmt(r.delivery_total)} <span style="color:var(--muted);font-size:11px">(${r.entregas_total||0})</span></td>
      <td>${finFmt(r.frete_total||0)}</td>
      <td>${(r.paes_total||0).toLocaleString('pt-BR')}</td>
      <td>${finFmt(r.custo_paes_total)}</td>
      <td>${finFmt(r.janta_total)}</td>
      <td>${finFmt(r.func_total)}</td>
      <td>${finFmt(r.cortesia_total)}</td>
    </tr>`;
  }).join('');
}

// ═══════════════════════════════════════
// COMPARATIVO FINAIS DE SEMANA
// ═══════════════════════════════════════
let fdsModo = 'mes';
const MESES_PT = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

function fdsIniciar(){
  const mes = hojeLocal().slice(0,7);
  document.getElementById('fds-mes').value = mes;
  fdsCarregar();
}

function fdsSetModo(modo, el){
  fdsModo = modo;
  document.querySelectorAll('#page-fin-fds .filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('fds-ctrl-mes').style.display  = modo==='mes'   ? 'flex'   : 'none';
  document.getElementById('fds-ctrl-anual').style.display= modo==='anual' ? 'flex'   : 'none';
  fdsCarregar();
}

async function fdsCarregar(){
  const conteudo = document.getElementById('fds-conteudo');
  conteudo.innerHTML = '<div class="empty">Carregando...</div>';

  let url = `/api/fin/comparativo-fds?modo=${fdsModo}`;
  if(fdsModo === 'mes'){
    const mes = document.getElementById('fds-mes').value;
    if(!mes){ conteudo.innerHTML='<div class="empty">Selecione um mês.</div>'; return; }
    url += `&mes=${mes}`;
  }

  const d = await fetch(url).then(r=>r.json());
  if(fdsModo === 'mes') fdsRenderMes(d, conteudo);
  else fdsRenderAnual(d, conteudo);
}

function fdsRenderMes(d, conteudo){
  if(!d.fds || !d.fds.length){
    conteudo.innerHTML='<div class="empty">Nenhum final de semana com fechamento registrado neste mês.</div>';
    return;
  }
  const [ano, mes] = d.mes.split('-');
  const nomeMes = MESES_PT[parseInt(mes)-1];
  const maxTotal = Math.max(...d.fds.map(f=>f.total));

  let html = `<div style="font-size:12px;color:var(--muted);margin-bottom:16px">Sexta, Sábado e Domingo — ${nomeMes}/${ano}</div>`;

  // Cards de comparação lado a lado
  html += `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-bottom:24px">`;
  d.fds.forEach((fds, idx) => {
    const pct = maxTotal > 0 ? Math.round((fds.total/maxTotal)*100) : 0;
    const isMelhor = fds.total === maxTotal && maxTotal > 0;
    html += `<div class="table-wrap" style="padding:18px;position:relative;${isMelhor?'border-color:rgba(34,197,94,.4)':''}">
      ${isMelhor ? '<div style="position:absolute;top:10px;right:10px;font-size:10px;background:rgba(34,197,94,.15);color:var(--accent2);padding:2px 8px;border-radius:20px;font-weight:700">Melhor</div>' : ''}
      <div style="font-size:11px;color:var(--muted);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">${fds.label}</div>
      <div style="font-size:24px;font-weight:800;color:${isMelhor?'var(--accent2)':'var(--text)'};margin-bottom:10px">${finFmt(fds.total)}</div>
      <div style="height:4px;background:rgba(255,255,255,.06);border-radius:4px;margin-bottom:12px">
        <div style="height:100%;width:${pct}%;background:${isMelhor?'var(--accent2)':'var(--accent)'};border-radius:4px;transition:.4s"></div>
      </div>
      <div style="font-size:12px">
        ${fds.dias.map(dia=>`
          <div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
            <span style="color:var(--muted)">${dia.dia_nome} ${new Date(dia.data+'T12:00:00').toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})}</span>
            <span style="font-weight:600">${finFmt(dia.venda)}</span>
          </div>`).join('')}
        ${fds.dias.some(d=>d.delivery_val>0) ? `
          <div style="display:flex;justify-content:space-between;padding:5px 0;margin-top:4px">
            <span style="color:var(--muted);font-size:11px">🛵 Delivery</span>
            <span style="color:var(--muted);font-size:11px">${finFmt(fds.dias.reduce((s,d)=>s+d.delivery_val,0))}</span>
          </div>` : ''}
      </div>
    </div>`;
  });
  html += `</div>`;

  // Tabela comparativa
  html += `<div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;font-weight:600;margin-bottom:10px">Detalhamento por dia</div>`;
  html += `<div class="table-wrap"><table>
    <thead><tr><th>Data</th><th>Dia</th><th>FDS</th><th>Venda</th><th>Delivery</th></tr></thead>
    <tbody>`;
  d.fds.forEach(fds=>{
    fds.dias.forEach(dia=>{
      html += `<tr>
        <td style="white-space:nowrap">${new Date(dia.data+'T12:00:00').toLocaleDateString('pt-BR')}</td>
        <td style="color:var(--muted)">${dia.dia_nome}</td>
        <td><span class="badge badge-unit">${fds.label}</span></td>
        <td style="font-weight:600">${finFmt(dia.venda)}</td>
        <td style="color:var(--muted)">${dia.delivery_val>0?finFmt(dia.delivery_val):'—'}</td>
      </tr>`;
    });
  });
  html += `</tbody></table></div>`;
  conteudo.innerHTML = html;
}

function fdsRenderAnual(d, conteudo){
  if(!d.semanas || !d.semanas.length){
    conteudo.innerHTML='<div class="empty">Nenhum final de semana com fechamento nos últimos 6 meses.</div>';
    return;
  }

  let html = `<div style="font-size:12px;color:var(--muted);margin-bottom:16px">Comparando últimos 6 meses — Sexta, Sábado e Domingo</div>`;

  d.semanas.forEach(sem => {
    if(!sem.por_mes.length) return;
    const maxVal = Math.max(...sem.por_mes.map(m=>m.total));
    html += `<div style="margin-bottom:24px">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px;color:var(--text)">${sem.semana}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">`;

    sem.por_mes.forEach(mp => {
      const [ano, mes] = mp.mes.split('-');
      const nomeMes = MESES_PT[parseInt(mes)-1];
      const pct = maxVal>0 ? Math.round((mp.total/maxVal)*100) : 0;
      const isMelhor = mp.total === maxVal && maxVal > 0;
      html += `<div class="table-wrap" style="padding:14px;${isMelhor?'border-color:rgba(34,197,94,.4)':''}">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px">${nomeMes}/${ano}${isMelhor?' ⭐':''}</div>
        <div style="font-size:20px;font-weight:800;color:${isMelhor?'var(--accent2)':'var(--text)'};margin-bottom:8px">${finFmt(mp.total)}</div>
        <div style="height:4px;background:rgba(255,255,255,.06);border-radius:4px;margin-bottom:8px">
          <div style="height:100%;width:${pct}%;background:${isMelhor?'var(--accent2)':'var(--accent)'};border-radius:4px"></div>
        </div>
        <div style="font-size:11px">
          ${mp.dias.map(dia=>`
            <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--muted)">${dia.dia_nome}</span>
              <span>${finFmt(dia.venda)}</span>
            </div>`).join('')}
        </div>
      </div>`;
    });
    html += `</div></div>`;
  });

  conteudo.innerHTML = html;
}
