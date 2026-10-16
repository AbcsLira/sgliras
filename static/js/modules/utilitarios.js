// Agrupa a digitação sem atrasar ações explícitas, como leitura de código de barras.
function adiarBusca(funcao, espera=150){
  let temporizador=null, argumentos=null, contexto=null;
  function cancelar(){
    if(temporizador!==null) clearTimeout(temporizador);
    temporizador=null;
    argumentos=null;
    contexto=null;
  }
  function executar(){
    if(argumentos===null) return;
    const valores=argumentos, origem=contexto;
    cancelar();
    return funcao.apply(origem,valores);
  }
  function adiada(...valores){
    cancelar();
    argumentos=valores;
    contexto=this;
    temporizador=setTimeout(executar,espera);
  }
  adiada.cancelar=cancelar;
  adiada.executar=executar;
  return adiada;
}
