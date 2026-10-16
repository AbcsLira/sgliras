
  const form = document.getElementById('loginForm');
  const usr = document.getElementById('usr');
  const pwd = document.getElementById('pwd');
  const err = document.getElementById('erro');
  const button = document.getElementById('loginButton');
  const buttonText = document.getElementById('buttonText');
  const togglePassword = document.getElementById('togglePassword');
  const eyeIcon = document.getElementById('eyeIcon');

  function mostrarErro(message) {
    err.textContent = message;
    err.classList.add('show');
  }

  function limparErro() {
    err.textContent = '';
    err.classList.remove('show');
  }

  togglePassword.addEventListener('click', () => {
    const mostrando = pwd.type === 'text';
    pwd.type = mostrando ? 'password' : 'text';
    togglePassword.setAttribute('aria-label', mostrando ? 'Mostrar senha' : 'Ocultar senha');
    togglePassword.setAttribute('title', mostrando ? 'Mostrar senha' : 'Ocultar senha');

    eyeIcon.innerHTML = mostrando
      ? '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.5"></circle>'
      : '<path d="M3 3l18 18"></path><path d="M10.6 6.2A10.6 10.6 0 0 1 12 6c6 0 9.5 6 9.5 6a16.6 16.6 0 0 1-3.2 3.7"></path><path d="M6.3 6.8C3.8 8.5 2.5 12 2.5 12s3.5 6 9.5 6c1.3 0 2.5-.3 3.5-.8"></path><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path>';
  });

  [usr, pwd].forEach(input => {
    input.addEventListener('input', limparErro);
  });

  form.addEventListener('submit', entrar);

  async function entrar(event) {
    if (event) event.preventDefault();

    const usuario = usr.value.trim();
    const senha = pwd.value;

    limparErro();

    if (!usuario || !senha) {
      mostrarErro('Preencha usuário e senha.');
      return;
    }

    button.disabled = true;
    buttonText.textContent = 'Entrando...';

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario, senha })
      });

      const d = await res.json();

      if (d.erro) {
        mostrarErro(d.erro);
        return;
      }

      window.location.href = '/';
    } catch (error) {
      mostrarErro('Não foi possível conectar ao servidor. Tente novamente.');
    } finally {
      button.disabled = false;
      buttonText.textContent = 'Entrar';
    }
  }
