// Relatório de cartões para impressão e PDF, independente dos formulários.
const CARTOES_PDF_OPERADORAS=Object.freeze({
  cielo:{nome:'Cielo',cor:'#168bd2'},
  rede:{nome:'Rede',cor:'#f58220'},
  sipag:{nome:'Sipag',cor:'#19964b'},
});
const CARTOES_PDF_MODALIDADES=Object.freeze({
  debito:'Débito',credito:'Crédito à vista',credito_2x:'Crédito em 2x',voucher:'Voucher',
});
const CARTOES_PDF_STATUS=Object.freeze({
  pendente:{nome:'Pendente',cor:'#854d0e',fundo:'#fef9c3'},
  recebido:{nome:'Recebido',cor:'#166534',fundo:'#dcfce7'},
  divergente:{nome:'Recebido com diferença',cor:'#991b1b',fundo:'#fee2e2'},
});

function cartoesPDFEscapar(valor){
  return String(valor??'').replace(/[&<>"']/g,caractere=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
  })[caractere]);
}

function cartoesPDFDinheiro(centavos){
  if(!Number.isSafeInteger(centavos)) return '—';
  // Formata os dígitos do inteiro, sem arredondar valores financeiros novamente.
  const digitos=String(Math.abs(centavos)).padStart(3,'0');
  const reais=digitos.slice(0,-2).replace(/\B(?=(\d{3})+(?!\d))/g,'.');
  return `${centavos<0?'-':''}R$ ${reais},${digitos.slice(-2)}`;
}

function cartoesPDFData(valor){
  if(typeof valor!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(valor)) return '—';
  const data=new Date(`${valor}T12:00:00Z`);
  if(!Number.isFinite(data.getTime())||data.toISOString().slice(0,10)!==valor) return '—';
  return `${valor.slice(8,10)}/${valor.slice(5,7)}/${valor.slice(0,4)}`;
}

function cartoesPDFMes(valor){
  if(typeof valor!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(valor)) return 'Período não informado';
  const nomes=['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
    'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  return `${nomes[Number(valor.slice(5))-1]}/${valor.slice(0,4)}`;
}

function cartoesPDFOperadora(id){
  return Object.hasOwn(CARTOES_PDF_OPERADORAS,id)
    ?CARTOES_PDF_OPERADORAS[id]:{nome:'Operadora não identificada',cor:'#475569'};
}

function cartoesPDFFonte(origem){
  try{
    const base=new URL(origem).origin;
    // Só um origin HTTP(S) pode compor o endereço da fonte no CSS.
    if(/^https?:\/\/(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::\d+)?$/.test(base))
      return `${base}/static/fonts/InterVariable.woff2`;
  }catch(erro){/* A janela about:blank herda a origem da aplicação. */}
  return '/static/fonts/InterVariable.woff2';
}

function cartoesHTMLRelatorio(dados,operadora='',origem=''){
  if(!dados||typeof dados!=='object'||!dados.resumo||!dados.pendentes_configuracao||
      !Array.isArray(dados.parcelas)||!Array.isArray(dados.agenda_mensal)||!Array.isArray(dados.por_operadora))
    throw new Error('O servidor retornou um relatório inválido.');
  const escapar=cartoesPDFEscapar,dinheiro=cartoesPDFDinheiro;
  const mes=cartoesPDFMes(dados.mes);
  const filtro=operadora?cartoesPDFOperadora(operadora).nome:'Todas as operadoras';
  const resumo=dados.resumo;
  const indicadores=[
    ['Bruto das parcelas',resumo.bruto_centavos],
    ['Taxas das parcelas',resumo.taxas_centavos],
    ['Líquido previsto',resumo.previsto_centavos],
    ['Saldo a receber',resumo.saldo_centavos],
    ['Recebido no mês · data real',resumo.recebido_no_mes_centavos],
    ['Diferença nas parcelas',resumo.diferenca_centavos],
  ].map(([titulo,valor])=>`<div class="indicador"><span>${titulo}</span><strong>${dinheiro(valor)}</strong></div>`).join('');
  const legenda=Object.values(CARTOES_PDF_OPERADORAS).map(op=>
    `<span class="operadora" style="border-color:${op.cor};color:${op.cor}">${op.nome}</span>`).join('');
  const porOperadora=dados.por_operadora.map(item=>{
    const op=cartoesPDFOperadora(item.operadora_id);
    return `<tr><td><span class="operadora" style="border-color:${op.cor};color:${op.cor}">${op.nome}</span></td>
      <td class="valor">${dinheiro(item.previsto_centavos)}</td><td class="valor">${dinheiro(item.saldo_centavos)}</td>
      <td class="valor">${dinheiro(item.recebido_no_mes_centavos)}</td></tr>`;
  }).join('')||'<tr><td colspan="4" class="vazio">Nenhuma previsão ou recebimento para este filtro.</td></tr>';
  const parcelas=dados.parcelas.map(item=>{
    const op=cartoesPDFOperadora(item.operadora_id);
    const modalidade=Object.hasOwn(CARTOES_PDF_MODALIDADES,item.modalidade)
      ?CARTOES_PDF_MODALIDADES[item.modalidade]:'Modalidade não identificada';
    const status=Object.hasOwn(CARTOES_PDF_STATUS,item.status)
      ?CARTOES_PDF_STATUS[item.status]:{nome:'Não identificado',cor:'#475569',fundo:'#f1f5f9'};
    const numero=Number.isSafeInteger(item.parcela)&&item.parcela>0?String(item.parcela):'—';
    const total=Number.isSafeInteger(item.total_parcelas)&&item.total_parcelas>0?String(item.total_parcelas):'—';
    const bandeira=item.bandeira?`<small>${escapar(item.bandeira)}</small>`:'';
    const observacao=item.observacao_recebimento
      ?`<small class="observacao">Obs.: ${escapar(item.observacao_recebimento)}</small>`:'';
    const recebimento=item.data_recebimento
      ?`${cartoesPDFData(item.data_recebimento)}<br><strong>${dinheiro(item.valor_recebido_centavos)}</strong>`:'—';
    return `<tr><td><strong style="color:${op.cor}">${op.nome}</strong><small>${modalidade}</small>${bandeira}</td>
      <td>${cartoesPDFData(item.data_venda)}<small>Parcela ${numero}/${total}</small></td>
      <td class="valor">${dinheiro(item.bruto_centavos)}</td><td class="valor">${dinheiro(item.taxa_centavos)}</td>
      <td class="valor">${dinheiro(item.liquido_centavos)}</td><td>${cartoesPDFData(item.data_prevista)}</td>
      <td>${recebimento}${observacao}</td>
      <td><span class="status" style="color:${status.cor};background:${status.fundo}">${status.nome}</span></td>
      <td class="valor">${dinheiro(item.diferenca_centavos)}</td></tr>`;
  }).join('')||'<tr><td colspan="9" class="vazio">Nenhuma parcela prevista neste mês para o filtro selecionado.</td></tr>';
  const agenda=dados.agenda_mensal.map(item=>`<tr><td>${cartoesPDFMes(item.mes)}</td>
    <td class="valor">${dinheiro(item.previsto_centavos)}</td><td class="valor">${dinheiro(item.saldo_centavos)}</td>
    <td class="valor">${dinheiro(item.recebido_no_mes_centavos)}</td></tr>`).join('')||
    '<tr><td colspan="4" class="vazio">Nenhuma previsão ou recebimento registrado.</td></tr>';
  const pendentes=dados.pendentes_configuracao;
  const aviso=Number.isSafeInteger(pendentes.quantidade)&&pendentes.quantidade>0
    ?`<aside class="aviso"><strong>Vendas sem condição vigente: ${pendentes.quantidade}</strong>
      <p>Bruto: ${dinheiro(pendentes.bruto_centavos)}. Ainda não há taxa, líquido ou data de recebimento calculados.
      Essas vendas não compõem a previsão, o saldo nem a agenda. O total considera todas as datas da operadora selecionada.</p></aside>`:'';
  const fonte=cartoesPDFFonte(origem);
  return `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Cartões e recebíveis · ${escapar(mes)} · ${escapar(filtro)} — S.G. Lira's</title>
  <style>
    @font-face{font-family:Inter;font-style:normal;font-weight:100 900;font-display:swap;src:url("${fonte}") format("woff2")}
    @page{size:A4 landscape;margin:12mm}
    *{box-sizing:border-box}body{font-family:Inter,Arial,sans-serif;font-size:11px;color:#172033;margin:0;padding:20px}
    h1{font-size:21px;margin:0 0 5px}h2{font-size:14px;margin:20px 0 8px}.subtitulo{color:#475569;margin:0 0 12px}
    .legenda{display:flex;gap:8px;margin-bottom:14px}.operadora{display:inline-block;border:1px solid;border-radius:4px;padding:3px 7px;font-weight:700}
    .resumo{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.indicador{border:1px solid #cbd5e1;border-radius:5px;padding:9px 11px;break-inside:avoid}
    .indicador span{display:block;font-size:10px;color:#475569;margin-bottom:4px}.indicador strong{font-size:17px}
    .explicacao{line-height:1.5;color:#475569;margin:12px 0}.aviso{border:1px solid #ca8a04;border-left:4px solid #ca8a04;padding:10px 12px;margin:14px 0;background:#fffbeb;break-inside:avoid}
    .aviso p{margin:5px 0 0;line-height:1.5}table{border-collapse:collapse;width:100%;table-layout:fixed}thead{display:table-header-group}
    th{text-align:left;background:#e2e8f0;color:#172033;font-size:10px}th,td{border-bottom:1px solid #cbd5e1;padding:7px 6px;vertical-align:top;overflow-wrap:anywhere}
    tr{break-inside:avoid}small{display:block;color:#475569;font-size:9px;margin-top:3px}.valor{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
    .parcelas{font-size:10px}.parcelas th,.parcelas td{padding:7px 5px}.parcelas th:first-child{width:17%}.parcelas th:nth-child(2){width:10%}
    .parcelas th:nth-child(7){width:15%}.parcelas th:nth-child(8){width:9%}.status{display:inline-block;font-size:9px;font-weight:700;border-radius:3px;padding:3px 4px}
    .vazio{text-align:center;color:#475569;padding:16px}.observacao{white-space:normal}.rodape{font-size:9px;color:#475569;border-top:1px solid #cbd5e1;margin-top:18px;padding-top:9px;line-height:1.5}
    h2{break-after:avoid}.indicador strong{overflow-wrap:anywhere}
    @media print{
      body{padding:0}.resumo{grid-template-columns:repeat(6,minmax(0,1fr))}
      .indicador{padding:7px 8px}.indicador strong{font-size:15px}
      h2{margin-top:14px}th,td,.parcelas th,.parcelas td{padding-top:5px;padding-bottom:5px}
      th,.status,.aviso{-webkit-print-color-adjust:exact;print-color-adjust:exact}
    }
  </style></head><body>
    <header><h1>Cartões e recebíveis</h1><p class="subtitulo">S.G. Lira's · ${escapar(mes)} · ${escapar(filtro)}</p><div class="legenda">${legenda}</div></header>
    <section class="resumo" aria-label="Resumo financeiro">${indicadores}</section>
    <p class="explicacao">Bruto, taxas, líquido previsto e parcelas abaixo correspondem ao mês da <strong>data prevista</strong>.
      O saldo contém somente parcelas pendentes. <strong>Recebido no mês</strong> usa a data real do recebimento, inclusive de parcelas previstas em outros meses.
      Parcelas recebidas com diferença estão liquidadas e não compõem o saldo. Diferença = recebido − líquido previsto.</p>
    ${aviso}
    <h2>Por operadora · mês selecionado</h2><table><thead><tr><th>Operadora</th><th class="valor">Líquido previsto</th><th class="valor">Saldo a receber</th><th class="valor">Recebido no mês · data real</th></tr></thead><tbody>${porOperadora}</tbody></table>
    <h2>Parcelas · mês de previsão selecionado</h2><table class="parcelas"><thead><tr><th>Operadora / modalidade</th><th>Venda / parcela</th><th class="valor">Bruto</th><th class="valor">Taxa</th><th class="valor">Líquido previsto</th><th>Data prevista</th><th>Recebimento real</th><th>Status</th><th class="valor">Diferença</th></tr></thead><tbody>${parcelas}</tbody></table>
    <h2>Agenda mensal · todas as datas do filtro de operadora</h2><table><thead><tr><th>Mês</th><th class="valor">Líquido previsto</th><th class="valor">Saldo a receber</th><th class="valor">Recebido no mês · data real</th></tr></thead><tbody>${agenda}</tbody></table>
    <footer class="rodape">Previsões em dias úteis consideram segunda a sexta, sem feriados. As datas podem ser ajustadas no sistema conforme o calendário da operadora.
      A agenda usa as previsões e os recebimentos reais registrados. Vendas sem condição vigente não recebem datas ou valores líquidos estimados.</footer>
  </body></html>`;
}

function cartoesPDFAvisar(mensagem){
  if(typeof toast==='function') toast(mensagem,'var(--danger)');
}

async function cartoesGerarPDF(mes,operadora=''){
  if(typeof mes!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(mes)||
      (operadora!==''&&!Object.hasOwn(CARTOES_PDF_OPERADORAS,operadora))){
    cartoesPDFAvisar('Selecione um mês e uma operadora válidos para gerar o PDF.');
    return false;
  }
  let janela;
  try{
    // Abrir antes do primeiro await mantém a ação vinculada ao clique do usuário.
    janela=window.open('','_blank');
    if(!janela){
      cartoesPDFAvisar('Permita a abertura da janela de impressão neste navegador e tente novamente.');
      return false;
    }
    janela.document.write('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>Preparando relatório</title></head><body><p>Preparando relatório de cartões…</p></body></html>');
    janela.document.close();
    const parametros=new URLSearchParams({mes});
    if(operadora) parametros.set('operadora',operadora);
    const resposta=await fetch(`/api/fin/cartoes/relatorio?${parametros}`);
    const dados=await resposta.json();
    if(!resposta.ok) throw new Error('Não foi possível carregar o relatório.');
    if(janela.closed) return false;
    const html=cartoesHTMLRelatorio(dados,operadora,window.location?.origin||'');
    janela.document.open();
    janela.document.write(html);
    janela.document.close();
    if(janela.document.fonts?.ready){
      try{await janela.document.fonts.ready;}catch(erro){/* Imprime com a fonte alternativa. */}
    }
    if(janela.closed) return false;
    janela.focus();
    janela.print();
    return true;
  }catch(erro){
    if(janela&&!janela.closed){try{janela.close();}catch(falha){/* A janela já pode ter sido fechada. */}}
    cartoesPDFAvisar('Não foi possível gerar o PDF. Verifique a conexão e tente novamente.');
    return false;
  }
}
