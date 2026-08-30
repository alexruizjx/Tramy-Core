<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tramy — Ejecución</title>
<link rel="icon" type="image/x-icon" href="favicon.ico">
<link rel="icon" type="image/png" sizes="16x16" href="favicon-16x16.png">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#1a2340">
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<style>
  html { overscroll-behavior-y: contain; }
  * { box-sizing: border-box; }
  body { font-family: Arial, sans-serif; margin: 0; background: #f7f9fc; color: #1a2340; overscroll-behavior-y: contain; }
  .ant-app-navbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
    background: #1a2340; height: 48px;
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.18);
  }
  .ant-app-navbar-titulo {
    font-family: Arial, sans-serif; font-size: 16px; font-weight: 900;
    color: #fff; letter-spacing: 1px; display: flex; align-items: center; gap: 8px;
  }
  .ant-app-navbar-salir {
    font-family: Arial, sans-serif; font-size: 13px; font-weight: 700;
    color: #fff; text-decoration: none; padding: 6px 14px;
    border: 1px solid rgba(255,255,255,0.3); border-radius: 6px;
  }
  .ant-secciones-nav {
    position: fixed; top: 48px; left: 0; right: 0; z-index: 9998;
    background: #f4f6fb; border-bottom: 1px solid #dde3ec;
    display: flex; gap: 4px; padding: 6px 12px; overflow-x: auto;
  }
  .tramy-seccion-tab {
    font-family: Arial, sans-serif; font-size: 12.5px; font-weight: 700;
    color: #5b6472; text-decoration: none; padding: 7px 14px;
    border-radius: 7px; white-space: nowrap;
  }
  .tramy-seccion-tab.activa { background: #1a2340; color: #fff; }
  .ant-wrap { max-width: 760px; margin: 0 auto; padding: 86px 8px 40px 8px; }
  .ant-card { background: #fff; border: 1px solid #dde3ec; border-radius: 10px; padding: 24px; text-align: left; }
  .ant-card h2 { font-size: 16px; margin: 0 0 4px 0; text-align:center; }
  .ant-card p.hint { font-size: 12.5px; color: #888; margin: 0 0 14px 0; text-align:center; }
  .ant-btn {
    display: inline-block; width: 100%; margin-top: 6px; padding: 11px; border-radius: 8px;
    border: none; background: #1a2340; color: #fff; font-size: 14.5px; font-weight: 700;
    cursor: pointer; text-align: center;
  }
  .ant-btn:disabled { opacity: 0.6; cursor: default; }
  .ant-btn-verde { background: #1a6e3c; }
  .ant-alert { padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-top: 10px; }
  .ant-alert.error { background: #fdecec; color: #a33; }
  .ant-loading { display: flex; align-items: center; gap: 12px; padding: 14px 0; color: #555; font-size: 13.5px; }
  .ant-spinner-ring {
    width: 26px; height: 26px; flex-shrink: 0;
    background-image: url('tramy-logo-navbar.png');
    background-size: contain; background-repeat: no-repeat; background-position: center;
    animation: ant-pulso 1.1s ease-in-out infinite;
  }
  @keyframes ant-pulso {
    0%, 100% { transform: scale(0.85); opacity: 0.7; }
    50% { transform: scale(1.05); opacity: 1; }
  }
  .loading-box { max-width: 480px; margin: 100px auto; text-align: center; color: #888; }
</style>
</head>
<body>

<div class="loading-box" id="loadingBox">Cargando...</div>

<div id="pagina" style="display:none;">
  <div class="ant-app-navbar">
    <span class="ant-app-navbar-titulo">
      <img src="tramy-logo-navbar.png" alt="Tramy" style="width:28px; height:28px; object-fit:contain;">
      TRAMY
    </span>
    <div style="display:flex; gap:8px; align-items:center;">
      <a href="panel.html" class="ant-app-navbar-salir">Mi cuenta</a>
      <a href="https://juridicox.com/" class="ant-app-navbar-salir">Salir →</a>
    </div>
  </div>

  <div class="ant-secciones-nav">
    <a href="index.html" class="tramy-seccion-tab">LIQUIDACIÓN</a>
    <a href="preparacion.html" class="tramy-seccion-tab">PREPARACIÓN</a>
    <a href="ejecucion.html" class="tramy-seccion-tab activa">EJECUCIÓN</a>
    <a href="utilidades.html" class="tramy-seccion-tab">UTILIDADES</a>
  </div>

  <div class="ant-wrap">
    <div class="ant-card">
      <h2>📢 Monitor de Turnos Llamados — Envigado</h2>
      <p class="hint">Graba, por hasta 2 horas (o hasta que lo detengas), cada turno que se llame (taquilla, placa, número, nombre) con la hora en que Tramy lo detectó. La plataforma no entrega su propia hora exacta del llamado, así que se usa el momento de la detección (revisando cada 8 segundos). Los datos capturados quedan guardados todo el día, aunque refresques la página o inicies otra sesión más tarde — se renuevan al día siguiente.</p>

      <label id="tramyCitasVigilarLabel" style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333; cursor:pointer;">Citas a vigilar (hasta 20) <span id="tramyCitasVigilarChevron">▼</span></label>
      <div id="tramyCitasVigilarContenido">
        <div id="tramyCitasVigilarWrap"></div>
        <button type="button" id="tramyBtnMasCitaVigilar" style="display:block; margin-top:6px; background:none; border:1.5px dashed #DAD3C2; border-radius:8px; padding:8px; font-size:12.5px; color:#666; cursor:pointer; width:100%;">+ Agregar cita a vigilar</button>
        <button type="button" id="tramyBtnGuardarBloqueCitas" style="display:block; margin-top:6px; background:none; border:1.5px solid #1a2340; border-radius:8px; padding:8px; font-size:12.5px; color:#1a2340; cursor:pointer; width:100%;">💾 Guardar este bloque de citas</button>
        <div id="tramyGuardarBloqueEstado" style="margin-top:6px; font-size:12px;"></div>
      </div>

      <div id="tramyAlertaCitaEncontrada" style="display:none; margin-top:10px;"></div>

      <button id="ant-btn-turnos-iniciar" class="ant-btn ant-btn-verde" style="margin-top:10px;" onclick="tramyIniciarMonitoreoTurnos()">Iniciar monitoreo (2 horas)</button>
      <button id="ant-btn-turnos-detener" class="ant-btn" style="margin-top:8px; background:#a33;" onclick="tramyDetenerMonitoreoTurnos()">Detener monitoreo</button>
      <div id="ant-turnos-estado" style="margin-top:10px;"></div>

      <button id="ant-btn-turnos-ver" class="ant-btn" style="margin-top:10px; background:#5b6472;" onclick="tramyVerTurnosCapturados()">Ver turnos capturados hoy</button>
      <div id="ant-turnos-capturados" style="margin-top:10px; max-height:320px; overflow-y:auto;"></div>

      <div style="border-top:1px dashed #DAD3C2; margin-top:14px; padding-top:12px;">
        <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px; color:#333;">📆 Historial por día</label>
        <div style="display:flex; gap:6px;">
          <select id="tramySelectorFechaHistorial" style="flex:1; padding:8px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:13.5px;">
            <option value="">Cargando fechas...</option>
          </select>
          <button class="ant-btn" style="width:auto; margin-top:0; padding:8px 14px; background:#5b6472;" onclick="tramyVerHistorialTurnosPorFecha()">Ver</button>
        </div>
        <div id="ant-turnos-historial" style="margin-top:10px; max-height:320px; overflow-y:auto;"></div>
      </div>
    </div>

    <div class="ant-card">
      <h2>👤 Crear Usuario — Portal Medellín</h2>
      <p class="hint">Registra un usuario nuevo en "Movilidad en Línea" de la Alcaldía de Medellín. Medellín manda un correo de activación aparte -- esta herramienta solo hace el registro inicial.</p>

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Tipo de Sociedad</label>
      <select id="medTipoSociedad" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">
        <option value="Persona Natural">Persona Natural</option>
        <option value="Persona Juridica">Persona Jurídica</option>
      </select>

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Tipo de Identificación</label>
      <select id="medTipoIdentificacion" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">
        <option value="Cedula de ciudadania">Cédula de ciudadanía</option>
        <option value="Tarjeta de identidad">Tarjeta de identidad</option>
        <option value="Cedula de extranjeria">Cédula de extranjería</option>
        <option value="NIT">NIT</option>
      </select>

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Número de Identificación</label>
      <input type="text" id="medNumeroIdentificacion" placeholder="Ej: 79334002" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Nombre</label>
      <input type="text" id="medNombre" placeholder="Ej: FABIO ISRAEL" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Apellidos</label>
      <input type="text" id="medApellidos" placeholder="Ej: GORDILLO" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Género</label>
      <select id="medGenero" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">
        <option value="Masculino">Masculino</option>
        <option value="Femenino">Femenino</option>
        <option value="Otro">Otro</option>
      </select>

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Correo Electrónico</label>
      <input type="text" id="medEmail" placeholder="Ej: correo@ejemplo.com" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Dirección</label>
      <input type="text" id="medDireccion" placeholder="Ej: CRA 74 98-10" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">

      <label style="display:block; font-size:12.5px; font-weight:700; margin:10px 0 4px 0; color:#333;">Teléfono</label>
      <input type="text" id="medTelefono" placeholder="Ej: 3205878758" style="width:100%; padding:9px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box; margin-bottom:8px;">

      <button id="ant-btn-medellin-crear" class="ant-btn ant-btn-verde" onclick="tramyCrearUsuarioMedellin()">Crear usuario</button>
      <div id="ant-medellin-resultado" style="margin-top:10px;"></div>
    </div>

    <div class="ant-card">
      <h2>⏱️ Monitoreo Automático 24/7</h2>
      <p class="hint">Corre solo en el servidor, todos los días, en el horario y con el intervalo que definas aquí — sin que nadie tenga que darle "Iniciar" a mano.</p>

      <div style="border:1.5px solid #DAD3C2; border-radius:10px; padding:12px; margin-bottom:12px;">
        <h3 style="margin:0 0 8px 0; font-size:15px;">Envigado — Citas</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <div style="flex:1; min-width:110px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Revisar cada (seg)</label>
            <input type="number" id="cfgEnvIntervalo" min="10" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
          <div style="flex:1; min-width:90px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Desde</label>
            <input type="time" id="cfgEnvHoraInicio" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
          <div style="flex:1; min-width:90px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Hasta</label>
            <input type="time" id="cfgEnvHoraFin" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
        </div>
        <button id="cfgEnvBotonToggle" class="ant-btn ant-btn-verde" style="margin-top:10px;" onclick="tramyToggleConfigMonitoreo('envigado_citas')">Iniciar</button>
        <div id="cfgEnvEstadoVivo" style="margin-top:8px; font-size:13px;"></div>
      </div>

      <div style="border:2px solid #d4a017; border-radius:10px; padding:12px; background:#fff9ec;">
        <h3 style="margin:0 0 4px 0; font-size:15px;">Medellín — Citas <span style="background:#d4a017; color:#fff; font-size:11px; padding:2px 8px; border-radius:10px; font-weight:700;">USA PROXY</span></h3>
        <p class="hint" style="margin-top:0;">Módulo idéntico al de arriba, pero <b>SIEMPRE</b> hace las consultas a través del proxy residencial de DataImpulse — cada revisión que haga este panel consume saldo de tu cuenta de DataImpulse.</p>

        <!-- Fila 1: intervalo, desde, hasta -->
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <div style="flex:1; min-width:110px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Revisar cada (seg)</label>
            <input type="number" id="cfgMedProxyIntervalo" min="60" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
          <div style="flex:1; min-width:90px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Desde</label>
            <input type="time" id="cfgMedProxyHoraInicio" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
          <div style="flex:1; min-width:90px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Hasta</label>
            <input type="time" id="cfgMedProxyHoraFin" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
        </div>

        <!-- Fila 2: usuario, contraseña, placa -->
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <div style="flex:1; min-width:120px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Usuario</label>
            <input type="text" id="cfgMedProxyUsuario" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
          <div style="flex:1; min-width:120px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Contraseña <span id="cfgMedProxyPassTieneHint" style="font-weight:400; color:#888;"></span></label>
            <input type="password" id="cfgMedProxyPassword" placeholder="Dejar vacío para no cambiarla" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
          <div style="flex:1; min-width:100px;">
            <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Placa</label>
            <input type="text" id="cfgMedProxyPlaca" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
          </div>
        </div>

        <!-- Fila 2b: sede (opcional) -->
        <div style="margin-top:10px;">
          <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Sede (opcional)</label>
          <input type="text" id="cfgMedProxySede" placeholder="Ej: Sao Paulo -- vacío = avisa de cualquier sede" style="width:100%; padding:8px 10px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; box-sizing:border-box;">
        </div>

        <!-- Fila 3: boton -->
        <button id="cfgMedProxyBotonToggle" class="ant-btn ant-btn-verde" style="margin-top:10px;" onclick="tramyToggleConfigMonitoreo('medellin_citas_proxy')">Iniciar</button>
        <div id="cfgMedProxyEstadoVivo" style="margin-top:8px; font-size:13px;"></div>
        <div id="ant-medellin-citas-proxy-alerta" style="display:none; margin-top:10px;"></div>
        <button id="ant-btn-medellin-citas-proxy-resetear-aviso" class="ant-btn" style="margin-top:8px; background:#5b6472;" onclick="tramyResetearAvisoCitasMedellinProxy()">🔔 Avisarme de nuevo (aunque la disponibilidad no haya cambiado)</button>
      </div>

      <div id="ant-config-monitoreo-estado" style="margin-top:10px;"></div>
    </div>
  </div>
</div>

<script>
  var ANT_API = 'https://consulta-impuestos-production.up.railway.app';

  // Cambia el aspecto de un boton "Iniciar monitoreo" entre normal
  // (verde, clickeable) y deshabilitado (gris, sin poder darle clic) --
  // se usa para que sea obvio con solo mirarlo que ya hay un monitoreo
  // corriendo, sin tener que leer el mensaje de texto.
  function _tramyPonerBotonMonitoreo(btn, inhabilitado) {
    if (!btn) return;
    btn.disabled = inhabilitado;
    if (inhabilitado) {
      btn.style.background = '#9aa0ab';
      btn.style.cursor = 'not-allowed';
    } else {
      btn.style.background = '';
      btn.style.cursor = '';
    }
  }


  // Convierte la llave publica VAPID (base64 url-safe) al formato que
  // pide PushManager.subscribe() -- un Uint8Array.
  function _tramyUrlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - base64String.length % 4) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = window.atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
  }

  window.tramyActivarNotificacionesPush = async function() {
    var cont = document.getElementById('ant-push-estado');
    var btn = document.getElementById('ant-btn-activar-push');

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      cont.innerHTML = '<div class="ant-alert error">Este navegador no soporta notificaciones push.</div>';
      return;
    }

    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Activando...</span></div>';

    try {
      var permiso = await Notification.requestPermission();
      if (permiso !== 'granted') {
        cont.innerHTML = '<div class="ant-alert error">No se activaron las notificaciones (permiso denegado).</div>';
        btn.disabled = false;
        return;
      }

      var registro = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;

      var respKey = await fetch(ANT_API + '/push-vapid-public-key');
      var dataKey = await respKey.json();
      if (!dataKey.publicKey) {
        cont.innerHTML = '<div class="ant-alert error">El servidor todavía no tiene configuradas las notificaciones push.</div>';
        btn.disabled = false;
        return;
      }

      var suscripcion = await registro.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _tramyUrlBase64ToUint8Array(dataKey.publicKey)
      });

      var suscripcionJson = suscripcion.toJSON();
      var respGuardar = await fetch(ANT_API + '/push-subscribe', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(suscripcionJson)
      });
      var dataGuardar = await respGuardar.json();

      if (dataGuardar.ok) {
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Notificaciones activadas en este dispositivo.</div>';
        _tramyMarcarBotonPushActivo();
      } else {
        cont.innerHTML = '<div class="ant-alert error">No se pudo guardar la suscripción en el servidor.</div>';
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error activando notificaciones: ' + err.message + '</div>';
    }
    btn.disabled = false;
  };

  function _tramyMarcarBotonPushActivo() {
    // Si ya estan activadas, no hace falta el boton para nada -- se
    // oculta en vez de cambiarle el texto.
    var btn = document.getElementById('ant-btn-activar-push');
    btn.style.display = 'none';
  }

  // Se revisa al cargar la pagina si YA hay una suscripcion activa en
  // este dispositivo (sin pedir permiso ni crear nada nuevo) -- asi no
  // hay que adivinar dandole clic al boton para saber si ya estaba
  // hecho de antes. Como las notificaciones no se "vencen" solas, esto
  // deberia mostrar "activadas" indefinidamente una vez que se activan
  // una vez, sin importar cuantos dias pasen.
  window._tramyRevisarEstadoNotificacionesPushAlCargar = async function() {
    var cont = document.getElementById('ant-push-estado');
    try {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
      var registro = await navigator.serviceWorker.getRegistration('/sw.js');
      if (!registro) {
        cont.innerHTML = '<div class="ant-alert" style="background:#fff3cd;color:#856404;">Aún no has activado las notificaciones en este dispositivo.</div>';
        return;
      }
      var suscripcion = await registro.pushManager.getSubscription();
      if (suscripcion) {
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Ya tienes las notificaciones activadas en este dispositivo (no hace falta repetirlo).</div>';
        _tramyMarcarBotonPushActivo();
      } else {
        cont.innerHTML = '<div class="ant-alert" style="background:#fff3cd;color:#856404;">Aún no has activado las notificaciones en este dispositivo.</div>';
      }
    } catch (err) { /* se ignora, no es critico */ }
  };



  window.tramyRevisarCitasEnvigado = async function() {
    var btn = document.getElementById('ant-btn-citas-envigado');
    var cont = document.getElementById('ant-citas-envigado-resultado');
    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Revisando ambas sedes, próximo día hábil...</span></div>';

    try {
      var resp = await fetch(ANT_API + '/envigado-citas-disponibles?dias=14');
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'Error revisando citas.') + '</div>';
        btn.disabled = false;
        return;
      }
      if (!data.hay_citas) {
        cont.innerHTML = '<div class="ant-alert error">Sin citas disponibles en ninguna sede por ahora. Vuelve a revisar más tarde.</div>';
      } else {
        var html = '<div style="background:#dcf5df;border:1px solid #8fd6a0;border-radius:7px;padding:12px 14px;color:#1a5c2e;font-weight:700;margin-bottom:8px;">✓ ¡Hay citas disponibles!</div>';
        data.disponibles.forEach(function(d){
          html += '<div style="padding:8px 12px;border-radius:8px;background:#f4f6fb;margin-bottom:6px;font-size:13px;"><b>' + d.sede + '</b> — ' + d.fecha + ' (' + d.cantidad_horarios + ' horarios)</div>';
        });
        cont.innerHTML = html;
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
    btn.disabled = false;
  };

  window.tramyIniciarMonitoreoCitas = async function() {
    var btn = document.getElementById('ant-btn-citas-monitoreo-iniciar');
    var cont = document.getElementById('ant-citas-monitoreo-estado');
    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Iniciando...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-iniciar-monitoreo?minutos=120');
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'Ya hay un monitoreo corriendo.') + '</div>';
        _tramyPonerBotonMonitoreo(btn, true);  // ya hay uno corriendo -- se queda gris igual
      } else {
        var fin = new Date(data.fin_esperado);
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Monitoreo de citas iniciado — revisando cada 30 segundos hasta las ' + fin.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'}) + '. El aviso aparecerá en Liquidación apenas se detecte algo.</div>';
        _tramyPonerBotonMonitoreo(btn, true);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
      _tramyPonerBotonMonitoreo(btn, false);
    }
  };

  window.tramyDetenerMonitoreoCitas = async function() {
    var cont = document.getElementById('ant-citas-monitoreo-estado');
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Deteniendo...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-detener-monitoreo');
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'No se pudo detener.') + '</div>';
      } else {
        cont.innerHTML = '<div class="ant-alert" style="background:#fff3cd;color:#856404;">⏸ Deteniendo el monitoreo de citas (puede tardar hasta 30 segundos en terminar del todo).</div>';
        _tramyPonerBotonMonitoreo(document.getElementById('ant-btn-citas-monitoreo-iniciar'), false);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  };

  // ── Filas de "citas a vigilar" (prefijo C/G + numero + placa opcional) ──
  // Genera las opciones de hora (07 a 17, formato militar fijo -- no
  // depende de la configuracion regional del navegador, a diferencia de
  // un <input type="time"> nativo que a veces muestra AM/PM sin que la
  // pagina pueda evitarlo).
  function _tramyOpcionesHoraMilitar(horaSel) {
    var html = '<option value="">--</option>';
    for (var h = 7; h <= 17; h++) {
      var hh = String(h).padStart(2, '0');
      html += '<option value="' + hh + '"' + (hh === horaSel ? ' selected' : '') + '>' + hh + '</option>';
    }
    return html;
  }
  function _tramyOpcionesMinuto(minSel) {
    var html = '<option value="">--</option>';
    for (var m = 0; m < 60; m++) {
      var mm = String(m).padStart(2, '0');
      html += '<option value="' + mm + '"' + (mm === minSel ? ' selected' : '') + '>' + mm + '</option>';
    }
    return html;
  }

  function _tramyCrearFilaCitaVigilar(horaPrellenada) {
    var partesHora = (horaPrellenada || '').split(':');
    var fila = document.createElement('div');
    fila.className = 'tramy-cita-vigilar-fila';
    fila.style.cssText = 'display:flex; gap:6px; flex-wrap:wrap; align-items:flex-end; margin-bottom:8px; padding:8px; background:#f8fafc; border-radius:8px;';
    fila.innerHTML =
      '<div style="width:110px;">' +
        '<label style="display:block; font-size:11px; font-weight:700; margin-bottom:3px;">Hora (opc.)</label>' +
        '<div style="display:flex; gap:3px;">' +
          '<select class="tramy-cv-hora-h" style="width:50%; padding:6px 2px; border:1px solid #DAD3C2; border-radius:6px; font-size:13px;">' + _tramyOpcionesHoraMilitar(partesHora[0]) + '</select>' +
          '<select class="tramy-cv-hora-m" style="width:50%; padding:6px 2px; border:1px solid #DAD3C2; border-radius:6px; font-size:13px;">' + _tramyOpcionesMinuto(partesHora[1]) + '</select>' +
        '</div>' +
      '</div>' +
      '<div style="width:56px;">' +
        '<label style="display:block; font-size:11px; font-weight:700; margin-bottom:3px;">Tipo</label>' +
        '<select class="tramy-cv-prefijo" style="width:100%; padding:7px 4px; border:1px solid #DAD3C2; border-radius:6px; font-size:13.5px;">' +
          '<option value="C" selected>C</option>' +
          '<option value="G">G</option>' +
        '</select>' +
      '</div>' +
      '<div style="width:70px;">' +
        '<label style="display:block; font-size:11px; font-weight:700; margin-bottom:3px;">Número</label>' +
        '<input type="text" class="tramy-cv-numero" placeholder="89" style="width:100%; padding:7px 6px; border:1px solid #DAD3C2; border-radius:6px; font-size:13.5px; box-sizing:border-box;">' +
      '</div>' +
      '<div style="width:90px;">' +
        '<label style="display:block; font-size:11px; font-weight:700; margin-bottom:3px;">Placa (opc.)</label>' +
        '<input type="text" class="tramy-cv-placa upper" placeholder="ABC123" style="width:100%; padding:7px 6px; border:1px solid #DAD3C2; border-radius:6px; font-size:13.5px; box-sizing:border-box; text-transform:uppercase;">' +
      '</div>' +
      '<button type="button" title="Quitar" style="flex-shrink:0; border:1px solid #a33; background:#fff; color:#a33; border-radius:6px; font-size:13px; padding:7px 10px; cursor:pointer;">✕</button>';

    fila.querySelector('button').addEventListener('click', function() {
      fila.remove();
      _tramyActualizarBotonMasCitaVigilar();
    });
    return fila;
  }

  function _tramyActualizarBotonMasCitaVigilar() {
    var btn = document.getElementById('tramyBtnMasCitaVigilar');
    var visibles = document.querySelectorAll('.tramy-cita-vigilar-fila').length;
    btn.style.display = visibles < 20 ? 'block' : 'none';
  }

  function _tramyLlenarFilaCitaVigilar(fila, cita) {
    fila.querySelector('.tramy-cv-prefijo').value = cita.numero.split('-')[0] || 'C';
    fila.querySelector('.tramy-cv-numero').value = cita.numero.split('-').slice(1).join('-') || '';
    fila.querySelector('.tramy-cv-placa').value = cita.placa || '';
    if (cita.hora) {
      var partes = cita.hora.split(':');
      fila.querySelector('.tramy-cv-hora-h').value = partes[0] || '';
      fila.querySelector('.tramy-cv-hora-m').value = partes[1] || '';
    }
  }

  // ── Guardar/cargar el bloque de citas (localStorage, por navegador) --
  // asi no hay que volver a escribir la misma lista de numeros cada vez
  // que se va a iniciar un nuevo monitoreo.
  var CLAVE_BLOQUE_CITAS = 'tramy_bloque_citas_envigado';

  function _tramyGuardarBloqueCitas() {
    var citas = _tramyLeerCitasVigilar();
    localStorage.setItem(CLAVE_BLOQUE_CITAS, JSON.stringify(citas));
    var estado = document.getElementById('tramyGuardarBloqueEstado');
    estado.textContent = '✓ Bloque guardado (' + citas.length + ' cita' + (citas.length === 1 ? '' : 's') + ').';
    estado.style.color = '#1a6e3c';
    setTimeout(function(){ estado.textContent = ''; }, 4000);
    _tramyColapsarCitasVigilar(true);
  }

  function _tramyColapsarCitasVigilar(colapsar) {
    document.getElementById('tramyCitasVigilarContenido').style.display = colapsar ? 'none' : 'block';
    document.getElementById('tramyCitasVigilarChevron').textContent = colapsar ? '▶' : '▼';
  }

  document.getElementById('tramyCitasVigilarLabel').addEventListener('click', function() {
    var contenido = document.getElementById('tramyCitasVigilarContenido');
    _tramyColapsarCitasVigilar(contenido.style.display !== 'none');
  });

  function _tramyCargarBloqueCitasGuardado() {
    var wrap = document.getElementById('tramyCitasVigilarWrap');
    wrap.innerHTML = '';
    var guardado = [];
    try { guardado = JSON.parse(localStorage.getItem(CLAVE_BLOQUE_CITAS) || '[]'); } catch (e) { guardado = []; }
    if (!Array.isArray(guardado) || guardado.length === 0) {
      wrap.appendChild(_tramyCrearFilaCitaVigilar());
    } else {
      guardado.forEach(function(cita) {
        var fila = _tramyCrearFilaCitaVigilar();
        _tramyLlenarFilaCitaVigilar(fila, cita);
        wrap.appendChild(fila);
      });
    }
    _tramyActualizarBotonMasCitaVigilar();
  }

  _tramyCargarBloqueCitasGuardado();

  document.getElementById('tramyBtnMasCitaVigilar').addEventListener('click', function() {
    var filas = document.querySelectorAll('.tramy-cita-vigilar-fila');
    if (filas.length >= 20) return;
    var ultimaFila = filas[filas.length - 1];
    var hAnt = ultimaFila ? ultimaFila.querySelector('.tramy-cv-hora-h').value : '';
    var mAnt = ultimaFila ? ultimaFila.querySelector('.tramy-cv-hora-m').value : '';
    var horaAnterior = (hAnt && mAnt) ? (hAnt + ':' + mAnt) : '';
    document.getElementById('tramyCitasVigilarWrap').appendChild(_tramyCrearFilaCitaVigilar(horaAnterior));
    _tramyActualizarBotonMasCitaVigilar();
  });

  document.getElementById('tramyBtnGuardarBloqueCitas').addEventListener('click', _tramyGuardarBloqueCitas);

  function _tramyLeerCitasVigilar() {
    return Array.from(document.querySelectorAll('.tramy-cita-vigilar-fila')).map(function(fila) {
      var numero = fila.querySelector('.tramy-cv-numero').value.trim();
      if (!numero) return null;
      var prefijo = fila.querySelector('.tramy-cv-prefijo').value;
      var h = fila.querySelector('.tramy-cv-hora-h').value;
      var m = fila.querySelector('.tramy-cv-hora-m').value;
      return {
        numero: prefijo + '-' + numero,
        placa: fila.querySelector('.tramy-cv-placa').value.trim().toUpperCase(),
        hora: (h && m) ? (h + ':' + m) : '',
      };
    }).filter(Boolean);
  }

  window.tramyIniciarMonitoreoTurnos = async function() {
    var btn = document.getElementById('ant-btn-turnos-iniciar');
    var cont = document.getElementById('ant-turnos-estado');
    var citas = _tramyLeerCitasVigilar();
    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Iniciando...</span></div>';
    try {
      var url = ANT_API + '/envigado-turnos-iniciar-monitoreo?minutos=120&citas=' + encodeURIComponent(JSON.stringify(citas));
      var resp = await fetch(url);
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'Ya hay un monitoreo corriendo.') + '</div>';
        _tramyPonerBotonMonitoreo(btn, true);  // ya hay uno corriendo -- se queda gris igual
      } else {
        var numerosTexto = citas.map(function(c){ return c.numero; }).join(', ');
        var mensajeVigilancia = numerosTexto ? (' Avisando cuando llamen a <b>' + numerosTexto + '</b>.') : '';
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ ' + data.mensaje + mensajeVigilancia + '</div>';
        _tramyPonerBotonMonitoreo(btn, true);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
      _tramyPonerBotonMonitoreo(btn, false);
    }
  };

  // Suena y vibra (Android) cuando se detecta una de las citas vigiladas.
  // En iPhone la vibracion no esta disponible desde el navegador (limite
  // de Apple, no de Tramy) -- el sonido si funciona en cualquier celular.
  function _tramyAlertaSonidoVibracion() {
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.35, 0.7].forEach(function(t){
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.3, ctx.currentTime + t);
        osc.start(ctx.currentTime + t);
        osc.stop(ctx.currentTime + t + 0.25);
      });
    } catch (e) { /* navegador sin soporte de audio, se ignora */ }
    if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 300]);
  }

  // Mientras la pagina de Ejecucion este abierta, se revisa cada 10
  // segundos si hay coincidencias nuevas guardadas en la base de datos
  // (persiste todo el dia, sin importar si la sesion de vigilancia sigue
  // activa o si se refresco la pagina). Arranca solo, no depende de que
  // se le de "Iniciar".
  var _tramyIdsAlertados = {};
  async function _tramyCargarVigiladosHoy() {
    try {
      var resp = await fetch(ANT_API + '/envigado-turnos-vigilados-hoy');
      var data = await resp.json();
      if (!data.ok || !data.encontrados || !data.encontrados.length) return;

      var caja = document.getElementById('tramyAlertaCitaEncontrada');
      var huboAlertaNueva = false;
      var html = '';
      data.encontrados.forEach(function(enc){
        var clave = enc.nro_atencion + '_' + enc.detectado_en;
        if (!_tramyIdsAlertados[clave]) {
          _tramyIdsAlertados[clave] = true;
          huboAlertaNueva = true;
        }
        var hora = new Date(enc.detectado_en).toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false});
        var taquillaConEspacios = (enc.taquilla || '').replace('-', ' - ');
        html += '<div style="background:#dcf5df;border:1.5px solid #8fd6a0;border-radius:8px;padding:12px 14px;margin-bottom:8px;font-size:13.5px;color:#1a5c2e;">'
          + '🔔 <b style="font-size:22px;">' + enc.nro_atencion + '</b><br>'
          + '<b style="font-size:20px;">' + taquillaConEspacios + '</b>'
          + (enc.placa ? '<br><b style="font-size:20px;">' + enc.placa + '</b>' : '')
          + (enc.nombre_usuario ? '<br>' + enc.nombre_usuario : '')
          + '<br><span style="color:#555;">Detectado a las ' + hora + '</span></div>';
      });
      caja.innerHTML = html;
      caja.style.display = 'block';
      if (huboAlertaNueva) _tramyAlertaSonidoVibracion();
    } catch (err) { /* se reintenta en el siguiente ciclo */ }
  }
  _tramyCargarVigiladosHoy();
  setInterval(_tramyCargarVigiladosHoy, 10000);

  window.tramyDetenerMonitoreoTurnos = async function() {
    var cont = document.getElementById('ant-turnos-estado');
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Deteniendo...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/envigado-turnos-detener-monitoreo');
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'No se pudo detener.') + '</div>';
      } else {
        cont.innerHTML = '<div class="ant-alert" style="background:#fff3cd;color:#856404;">⏸ Deteniendo el monitoreo (puede tardar unos segundos en terminar del todo).</div>';
        _tramyPonerBotonMonitoreo(document.getElementById('ant-btn-turnos-iniciar'), false);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  };

  // Mientras la lista de capturados este visible, se refresca sola cada
  // 10 segundos -- asi no hace falta darle "Ver" a cada rato para saber
  // si ya llamaron un turno nuevo.
  var _tramyTimerListaCapturados = null;
  // ── COLA DE RESERVA AUTOMATICA DE CITAS -- Envigado ──────────────────
  // Llenar el select de horas (0 a 23) una sola vez al cargar la pagina.
  (function _tramyLlenarSelectHoras() {
    var sel = document.getElementById('envCitaHora');
    if (!sel) return;
    for (var h = 6; h <= 20; h++) {
      var op = document.createElement('option');
      op.value = h;
      op.textContent = (h < 10 ? '0'+h : h) + ':00';
      sel.appendChild(op);
    }
  })();

  window.tramyAgregarSolicitudCitaEnvigado = async function() {
    var cont = document.getElementById('ant-envcita-estado');
    var payload = {
      nombres: document.getElementById('envCitaNombres').value.trim(),
      apellidos: document.getElementById('envCitaApellidos').value.trim(),
      numero_documento: document.getElementById('envCitaDocumento').value.trim(),
      placa: document.getElementById('envCitaPlaca').value.trim(),
      correo: document.getElementById('envCitaCorreo').value.trim(),
      celular: document.getElementById('envCitaCelular').value.trim(),
      id_servicio: document.getElementById('envCitaTramite').value,
      sede_preferida: document.getElementById('envCitaSede').value.trim(),
      hora_aproximada: document.getElementById('envCitaHora').value,
    };
    if (!payload.nombres || !payload.apellidos || !payload.numero_documento || !payload.placa || !payload.correo || !payload.celular) {
      cont.innerHTML = '<div class="ant-alert error">Completa todos los campos obligatorios.</div>';
      return;
    }
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Agregando...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-solicitud-agregar', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      var data = await resp.json();
      if (data.ok) {
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Agregado a la cola.</div>';
        ['envCitaNombres','envCitaApellidos','envCitaDocumento','envCitaPlaca','envCitaCorreo','envCitaCelular','envCitaSede'].forEach(function(id){
          document.getElementById(id).value = '';
        });
        tramyCargarListaSolicitudesCitaEnvigado();
      } else {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'No se pudo agregar.') + '</div>';
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  };

  window.tramyEliminarSolicitudCitaEnvigado = async function(id) {
    try {
      await fetch(ANT_API + '/envigado-citas-solicitud-eliminar?id=' + id);
      tramyCargarListaSolicitudesCitaEnvigado();
    } catch (err) { /* se ignora */ }
  };

  window.tramyProbarAhoraSolicitudCitaEnvigado = async function(id) {
    var cont = document.getElementById('ant-probar-resultado-' + id);
    var btn = document.getElementById('ant-probar-btn-' + id);
    if (btn) btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Probando el flujo real (puede tardar 30-60 segundos)...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-solicitud-probar-ahora?id=' + id);
      var data = await resp.json();
      if (!data.job_id) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'No se pudo iniciar la prueba.') + '</div>';
        if (btn) btn.disabled = false;
        return;
      }
      var jobId = data.job_id;
      var timer = setInterval(async function() {
        try {
          var respEstado = await fetch(ANT_API + '/consultar/estado?job_id=' + jobId);
          var estado = await respEstado.json();
          if (estado.mensaje) {
            cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>' + estado.mensaje + '</span></div>';
          }
          if (estado.estado === 'listo') {
            clearInterval(timer);
            if (btn) btn.disabled = false;
            var r = estado.resultado || {};
            var color = r.exito ? '#dcf5df' : '#fff3cd';
            var colorTexto = r.exito ? '#1a5c2e' : '#7a4a00';
            var capturasHtml = '';
            if (r.capturas && Object.keys(r.capturas).length > 0) {
              var etiquetasCaptura = { antes_confirmar: '📸 Ver captura: antes de confirmar', despues_confirmar: '📸 Ver captura: después de confirmar' };
              capturasHtml = '<div style="margin-top:8px; display:flex; flex-direction:column; gap:4px;">';
              Object.keys(r.capturas).forEach(function(clave) {
                var nombreArchivo = r.capturas[clave];
                var url = ANT_API + '/envigado-captura?nombre=' + encodeURIComponent(nombreArchivo);
                capturasHtml += '<a href="' + url + '" target="_blank" download="' + nombreArchivo + '" style="display:inline-block; padding:5px 10px; background:#1a2340; color:#fff; text-decoration:none; border-radius:5px; font-size:12px;">' + (etiquetasCaptura[clave] || ('📸 ' + clave)) + '</a>';
              });
              capturasHtml += '</div>';
            }
            cont.innerHTML = '<div style="background:' + color + '; color:' + colorTexto + '; padding:8px 10px; border-radius:6px; font-size:12.5px;">'
              + (r.exito ? '✓ ' : '⚠️ ') + (r.mensaje || 'Sin mensaje.')
              + (r.nro_atencion ? '<br>Nro. atención: <b>' + r.nro_atencion + '</b>' : '')
              + '</div>'
              + capturasHtml;
          } else if (estado.estado === 'error') {
            clearInterval(timer);
            if (btn) btn.disabled = false;
            cont.innerHTML = '<div class="ant-alert error">' + (estado.error || estado.mensaje || 'Error desconocido.') + '</div>';
          }
        } catch (errPoll) { /* se sigue intentando en el proximo ciclo */ }
      }, 3000);
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
      if (btn) btn.disabled = false;
    }
  };

  window.tramyCargarListaSolicitudesCitaEnvigado = async function() {
    var cont = document.getElementById('ant-envcita-lista');
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-solicitud-listar');
      var data = await resp.json();
      if (!data.ok || !data.solicitudes.length) {
        cont.innerHTML = '<p class="hint">No hay solicitudes en la cola todavía.</p>';
        return;
      }
      var iconosEstado = { pendiente: '🟡', reservada: '🟢', error: '🔴', cancelada: '⚪' };
      var html = '';
      data.solicitudes.forEach(function(s) {
        html += '<div style="border:1px solid #DAD3C2; border-radius:8px; padding:10px; margin-bottom:8px; font-size:13.5px;">'
          + '<b>' + (iconosEstado[s.estado] || '') + ' ' + s.nombres + ' ' + s.apellidos + '</b> — ' + s.placa + ' <span style="color:#888;">(ID: ' + s.id + ')</span><br>'
          + 'Doc: ' + s.numero_documento + ' · Hora aprox: ' + s.hora_aproximada + ':00' + (s.sede_preferida ? ' · Sede: ' + s.sede_preferida : '') + '<br>'
          + 'Estado: <b>' + s.estado + '</b>'
          + (s.nro_atencion ? ' — Nro. atención: <b>' + s.nro_atencion + '</b>' : '')
          + (s.error_mensaje ? '<br><span style="color:#a33;">' + s.error_mensaje + '</span>' : '')
          + '<br><button class="ant-btn" style="margin-top:6px; padding:4px 10px; font-size:12px; background:#a33;" onclick="tramyEliminarSolicitudCitaEnvigado(' + s.id + ')">Eliminar</button>'
          + ' <button class="ant-btn" id="ant-probar-btn-' + s.id + '" style="margin-top:6px; padding:4px 10px; font-size:12px; background:#1a5fa8;" onclick="tramyProbarAhoraSolicitudCitaEnvigado(' + s.id + ')">🧪 Probar ahora</button>'
          + '<div id="ant-probar-resultado-' + s.id + '" style="margin-top:6px;"></div>'
          + '</div>';
      });
      cont.innerHTML = html;
    } catch (err) { /* se ignora */ }
  };

  function _tramyRenderizarListaTurnos(turnos) {
    if (turnos.length === 0) return '';
    return turnos.map(function(t){
      var hora = new Date(t.detectado_en).toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false});
      return '<div style="padding:8px 12px;border-radius:8px;background:#f4f6fb;margin-bottom:6px;font-size:13px;">'
        + '<b>Taquilla ' + t.taquilla + (t.placa ? ' — ' + t.placa : '') + ' — ' + t.nro_atencion + '</b> — ' + (t.nombre_usuario || '(sin nombre)') + '<br>'
        + (t.servicio || '') + ' · <span style="color:#888;">' + hora + '</span>'
        + '</div>';
    }).join('');
  }

  async function _tramyCargarListaTurnos() {
    var cont = document.getElementById('ant-turnos-capturados');
    try {
      var resp = await fetch(ANT_API + '/envigado-turnos-capturados?limite=100');
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'Error cargando los turnos.') + '</div>';
      } else if (data.turnos.length === 0) {
        cont.innerHTML = '<div class="ant-alert error">Todavía no se ha capturado ningún turno hoy.</div>';
      } else {
        cont.innerHTML = _tramyRenderizarListaTurnos(data.turnos);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  }

  // ── Historial por dia (solo las citas que YO dejo vigilando, no todos los turnos) ──
  async function _tramyCargarFechasHistorial() {
    var sel = document.getElementById('tramySelectorFechaHistorial');
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-vigiladas-fechas');
      var data = await resp.json();
      if (!data.ok || data.fechas.length === 0) {
        sel.innerHTML = '<option value="">Sin días con citas guardadas</option>';
        return;
      }
      var hoyISO = new Date().toISOString().slice(0, 10);
      sel.innerHTML = data.fechas.map(function(f){
        var fechaTexto = new Date(f.fecha + 'T00:00:00').toLocaleDateString('es-CO', {weekday:'long', day:'numeric', month:'long', year:'numeric'});
        var etiqueta = (f.fecha === hoyISO ? 'Hoy — ' : '') + fechaTexto + ' (' + f.total + ' citas)';
        return '<option value="' + f.fecha + '">' + etiqueta + '</option>';
      }).join('');
    } catch (err) {
      sel.innerHTML = '<option value="">Error cargando fechas</option>';
    }
  }
  _tramyCargarFechasHistorial();

  window.tramyVerHistorialTurnosPorFecha = async function() {
    var fecha = document.getElementById('tramySelectorFechaHistorial').value;
    var cont = document.getElementById('ant-turnos-historial');
    // El mismo boton funciona como colapsable: si ya hay contenido
    // visible, un segundo clic solo lo oculta (sin volver a consultar).
    if (cont.style.display !== 'none' && cont.innerHTML.trim() !== '') {
      cont.style.display = 'none';
      return;
    }
    cont.style.display = 'block';
    if (!fecha) { cont.innerHTML = ''; return; }
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Cargando...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/envigado-citas-vigiladas-historial?fecha=' + encodeURIComponent(fecha));
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'Error cargando las citas.') + '</div>';
      } else if (data.citas.length === 0) {
        cont.innerHTML = '<div class="ant-alert error">No dejaste ninguna cita vigilando ese día.</div>';
      } else {
        cont.innerHTML = data.citas.map(function(c){
          if (c.encontrado) {
            var horaDetectado = new Date(c.detectado_en).toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false});
            return '<div style="padding:8px 12px;border-radius:8px;background:#dcf5df;margin-bottom:6px;font-size:13px;color:#1a5c2e;">'
              + '<b>✓ ' + c.numero + (c.placa ? ' — ' + c.placa : '') + '</b>' + (c.hora_cita ? ' · Cita programada: ' + c.hora_cita : '') + '<br>'
              + 'Llamado en Taquilla ' + c.taquilla + ' — ' + (c.nombre_usuario || '(sin nombre)') + ' · <span style="color:#3a7a54;">detectado a las ' + horaDetectado + '</span>'
              + '</div>';
          }
          return '<div style="padding:8px 12px;border-radius:8px;background:#f4f6fb;margin-bottom:6px;font-size:13px;color:#666;">'
            + '<b>' + c.numero + (c.placa ? ' — ' + c.placa : '') + '</b>' + (c.hora_cita ? ' · Cita programada: ' + c.hora_cita : '') + '<br>'
            + '<span style="color:#999;">No se detectó que la llamaran ese día.</span>'
            + '</div>';
        }).join('');
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  };

  window.tramyVerTurnosCapturados = async function() {
    var btn = document.getElementById('ant-btn-turnos-ver');
    var cont = document.getElementById('ant-turnos-capturados');

    // Si ya esta abierto, este clic solo lo OCULTA visualmente -- la
    // actualizacion automatica cada 10 segundos sigue corriendo de
    // fondo igual, para que la lista ya este al dia cuando se vuelva a
    // mostrar.
    if (btn.dataset.abierto === '1') {
      cont.style.display = 'none';
      btn.textContent = 'Ver turnos capturados hoy';
      btn.dataset.abierto = '0';
      return;
    }

    cont.style.display = '';
    if (!cont.innerHTML.trim()) {
      btn.disabled = true;
      cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Cargando...</span></div>';
      await _tramyCargarListaTurnos();
      btn.disabled = false;
    }
    // Se actualiza sola cada 10 segundos -- si ya habia un temporizador
    // corriendo (de una vez anterior), no se duplica.
    clearInterval(_tramyTimerListaCapturados);
    _tramyTimerListaCapturados = setInterval(_tramyCargarListaTurnos, 10000);
    btn.textContent = 'Ocultar turnos capturados';
    btn.dataset.abierto = '1';
  };

  window.tramyCrearUsuarioMedellin = async function() {
    var btn = document.getElementById('ant-btn-medellin-crear');
    var cont = document.getElementById('ant-medellin-resultado');

    var datos = {
      tipo_sociedad: document.getElementById('medTipoSociedad').value,
      tipo_identificacion: document.getElementById('medTipoIdentificacion').value,
      numero_identificacion: document.getElementById('medNumeroIdentificacion').value.trim(),
      nombre: document.getElementById('medNombre').value.trim(),
      apellidos: document.getElementById('medApellidos').value.trim(),
      genero: document.getElementById('medGenero').value,
      email: document.getElementById('medEmail').value.trim(),
      direccion: document.getElementById('medDireccion').value.trim(),
      telefono: document.getElementById('medTelefono').value.trim(),
    };
    if (!datos.numero_identificacion || !datos.nombre || !datos.apellidos || !datos.email || !datos.direccion || !datos.telefono) {
      cont.innerHTML = '<div class="ant-alert error">Completa todos los campos.</div>';
      return;
    }

    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span id="ant-medellin-prog-msg">Iniciando...</span></div>';

    try {
      var params = new URLSearchParams(datos);
      var respInicio = await fetch(ANT_API + '/medellin-crear-usuario?' + params.toString());
      var dataInicio = await respInicio.json();
      if (dataInicio.error) {
        cont.innerHTML = '<div class="ant-alert error">' + dataInicio.error + '</div>';
        btn.disabled = false;
        return;
      }
      var jobId = dataInicio.job_id;
      var timer = setInterval(async function() {
        try {
          var respEstado = await fetch(ANT_API + '/consultar/estado?job_id=' + jobId);
          var estado = await respEstado.json();
          var msgEl = document.getElementById('ant-medellin-prog-msg');
          if (msgEl && estado.mensaje) msgEl.textContent = estado.mensaje;

          if (estado.estado === 'listo') {
            clearInterval(timer);
            btn.disabled = false;
            var r = estado.resultado || {};
            cont.innerHTML = '<div class="ant-alert' + (r.exito ? '' : ' error') + '">' + (r.mensaje || 'Sin mensaje.') + '</div>';
          } else if (estado.estado === 'error') {
            clearInterval(timer);
            btn.disabled = false;
            cont.innerHTML = '<div class="ant-alert error">' + (estado.error || 'Ocurrió un error.') + '</div>';
          }
        } catch (errPoll) {
          console.warn('Error consultando estado, reintentando...', errPoll);
        }
      }, 3000);
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
      btn.disabled = false;
    }
  };

  window.tramyRevisarCitasMedellin = async function() {
    var btn = document.getElementById('ant-btn-medellin-citas');
    var cont = document.getElementById('ant-medellin-citas-resultado');

    var usuario = document.getElementById('medCitasUsuario').value.trim();
    var password = document.getElementById('medCitasPassword').value.trim();
    var placa = document.getElementById('medCitasPlaca').value.trim().toUpperCase();
    var sede = document.getElementById('medCitasSede').value.trim();
    if (!usuario || !password || !placa) {
      cont.innerHTML = '<div class="ant-alert error">Completa usuario, contraseña y placa.</div>';
      return;
    }

    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span id="ant-medellin-citas-prog-msg">Iniciando...</span></div>';

    try {
      var params = new URLSearchParams({usuario: usuario, password: password, placa: placa});
      if (sede) params.set('sede', sede);
      var respInicio = await fetch(ANT_API + '/medellin-citas-disponibles?' + params.toString());
      var dataInicio = await respInicio.json();
      if (dataInicio.error) {
        cont.innerHTML = '<div class="ant-alert error">' + dataInicio.error + '</div>';
        btn.disabled = false;
        return;
      }
      var jobId = dataInicio.job_id;
      var timer = setInterval(async function() {
        try {
          var respEstado = await fetch(ANT_API + '/consultar/estado?job_id=' + jobId);
          var estado = await respEstado.json();
          var msgEl = document.getElementById('ant-medellin-citas-prog-msg');
          if (msgEl && estado.mensaje) msgEl.textContent = estado.mensaje;

          if (estado.estado === 'listo') {
            clearInterval(timer);
            btn.disabled = false;
            var r = estado.resultado || {};
            if (r.hay_citas) {
              cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ ¡Hay citas disponibles! Sede: ' + (r.detalle && r.detalle.sede || '') + '</div>';
            } else {
              cont.innerHTML = '<div class="ant-alert error">Sin citas disponibles por ahora. ' + (r.detalle && (r.detalle.mensaje || r.detalle.error) || '') + '</div>';
            }
          } else if (estado.estado === 'error') {
            clearInterval(timer);
            btn.disabled = false;
            cont.innerHTML = '<div class="ant-alert error">' + (estado.error || 'Ocurrió un error.') + '</div>';
          }
        } catch (errPoll) {
          console.warn('Error consultando estado, reintentando...', errPoll);
        }
      }, 3000);
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
      btn.disabled = false;
    }
  };

  window.tramyIniciarMonitoreoCitasMedellin = async function() {
    var btn = document.getElementById('ant-btn-medellin-citas-monitoreo-iniciar');
    var cont = document.getElementById('ant-medellin-citas-monitoreo-estado');

    var usuario = document.getElementById('medCitasUsuario').value.trim();
    var password = document.getElementById('medCitasPassword').value.trim();
    var placa = document.getElementById('medCitasPlaca').value.trim().toUpperCase();
    var sede = document.getElementById('medCitasSede').value.trim();
    if (!usuario || !password || !placa) {
      cont.innerHTML = '<div class="ant-alert error">Completa usuario, contraseña y placa arriba.</div>';
      return;
    }

    btn.disabled = true;
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Iniciando...</span></div>';
    try {
      var params = new URLSearchParams({usuario: usuario, password: password, placa: placa, minutos: '120'});
      if (sede) params.set('sede', sede);
      var resp = await fetch(ANT_API + '/medellin-citas-iniciar-monitoreo?' + params.toString());
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'Ya hay un monitoreo corriendo.') + '</div>';
        _tramyPonerBotonMonitoreo(btn, true);  // ya hay uno corriendo -- se queda gris igual
      } else {
        var fin = new Date(data.fin_esperado);
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Monitoreo de citas de Medellín iniciado — revisando cada 30 segundos hasta las ' + fin.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'}) + '.</div>';
        clearInterval(_tramyTimerMedellinCitas);
        _tramyTimerMedellinCitas = setInterval(_tramyCargarUltimoHallazgoMedellin, 10000);
        _tramyPonerBotonMonitoreo(btn, true);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
      _tramyPonerBotonMonitoreo(btn, false);
    }
  };

  window.tramyDetenerMonitoreoCitasMedellin = async function() {
    var cont = document.getElementById('ant-medellin-citas-monitoreo-estado');
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Deteniendo...</span></div>';
    try {
      var resp = await fetch(ANT_API + '/medellin-citas-detener-monitoreo');
      var data = await resp.json();
      if (!data.ok) {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'No se pudo detener.') + '</div>';
      } else {
        cont.innerHTML = '<div class="ant-alert" style="background:#fff3cd;color:#856404;">⏸ Deteniendo el monitoreo de citas de Medellín (puede tardar hasta 30 segundos en terminar del todo).</div>';
        clearInterval(_tramyTimerMedellinCitas);
        _tramyPonerBotonMonitoreo(document.getElementById('ant-btn-medellin-citas-monitoreo-iniciar'), false);
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  };

  // Mientras el monitoreo de citas de Medellin este corriendo, se revisa
  // cada 10 segundos si ya encontro algo -- si aparece un hallazgo NUEVO
  // (que antes no estaba), se dispara sonido + vibracion, igual que el
  // monitor de turnos de Envigado.
  var _tramyTimerMedellinCitas = null;
  var _tramyUltimoHallazgoMedellinVisto = null;

  // Version espejo (proxy) -- estado completamente separado.
  var _tramyTimerMedellinCitasProxy = null;
  var _tramyUltimoHallazgoMedellinProxyVisto = null;

  window.tramyResetearAvisoCitasMedellinProxy = async function() {
    var btn = document.getElementById('ant-btn-medellin-citas-proxy-resetear-aviso');
    btn.disabled = true;
    var textoOriginal = btn.textContent;
    btn.textContent = 'Reiniciando...';
    try {
      var resp = await fetch(ANT_API + '/medellin-citas-proxy-resetear-aviso');
      var data = await resp.json();
      if (data.ok) {
        _tramyUltimoHallazgoMedellinProxyVisto = null;
        var caja = document.getElementById('ant-medellin-citas-proxy-alerta');
        caja.style.display = 'none';
        btn.textContent = '✓ Listo, avisará de nuevo';
        setTimeout(function(){ btn.textContent = textoOriginal; }, 3000);
      } else {
        btn.textContent = 'Error, intenta de nuevo';
      }
    } catch (err) {
      btn.textContent = 'Error de conexión';
    }
    btn.disabled = false;
  };

  async function _tramyCargarUltimoHallazgoMedellinProxy() {
    var caja = document.getElementById('ant-medellin-citas-proxy-alerta');
    try {
      var resp = await fetch(ANT_API + '/medellin-citas-proxy-ultimo-hallazgo');
      var data = await resp.json();
      if (!data.ok) return;

      if (data.ultimo_hallazgo) {
        var esNuevo = !_tramyUltimoHallazgoMedellinProxyVisto
          || _tramyUltimoHallazgoMedellinProxyVisto.encontrado_en !== data.ultimo_hallazgo.encontrado_en;
        _tramyUltimoHallazgoMedellinProxyVisto = data.ultimo_hallazgo;

        var hora = new Date(data.ultimo_hallazgo.encontrado_en).toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
        var sede = (data.ultimo_hallazgo.detalle && data.ultimo_hallazgo.detalle.sede) || '';
        caja.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;font-weight:bold;">'
          + '✓ ¡Hay citas disponibles en Medellín! (proxy) Sede: ' + sede
          + '<br><span style="color:#555;font-weight:normal;">Detectado a las ' + hora + '</span></div>';
        caja.style.display = 'block';
        if (esNuevo) _tramyAlertaSonidoVibracion();
      }
    } catch (err) { /* se reintenta en el siguiente ciclo */ }
  }

  window.tramyResetearAvisoCitasMedellin = async function() {
    var btn = document.getElementById('ant-btn-medellin-citas-resetear-aviso');
    btn.disabled = true;
    var textoOriginal = btn.textContent;
    btn.textContent = 'Reiniciando...';
    try {
      var resp = await fetch(ANT_API + '/medellin-citas-resetear-aviso');
      var data = await resp.json();
      if (data.ok) {
        _tramyUltimoHallazgoMedellinVisto = null;
        var caja = document.getElementById('ant-medellin-citas-alerta');
        caja.style.display = 'none';
        btn.textContent = '✓ Listo, avisará de nuevo';
        setTimeout(function(){ btn.textContent = textoOriginal; }, 3000);
      } else {
        btn.textContent = 'Error, intenta de nuevo';
      }
    } catch (err) {
      btn.textContent = 'Error de conexión';
    }
    btn.disabled = false;
  };

  async function _tramyCargarUltimoHallazgoMedellin() {
    var caja = document.getElementById('ant-medellin-citas-alerta');
    try {
      var resp = await fetch(ANT_API + '/medellin-citas-estado-monitoreo');
      var data = await resp.json();
      if (!data.ok) return;

      if (!data.activo) {
        clearInterval(_tramyTimerMedellinCitas);
      }

      if (data.ultimo_hallazgo) {
        var esNuevo = !_tramyUltimoHallazgoMedellinVisto
          || _tramyUltimoHallazgoMedellinVisto.encontrado_en !== data.ultimo_hallazgo.encontrado_en;
        _tramyUltimoHallazgoMedellinVisto = data.ultimo_hallazgo;

        var hora = new Date(data.ultimo_hallazgo.encontrado_en).toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
        var sede = (data.ultimo_hallazgo.detalle && data.ultimo_hallazgo.detalle.sede) || '';
        caja.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;font-weight:bold;">'
          + '✓ ¡Hay citas disponibles en Medellín! Sede: ' + sede
          + '<br><span style="color:#555;font-weight:normal;">Detectado a las ' + hora + '</span></div>';
        caja.style.display = 'block';
        if (esNuevo) _tramyAlertaSonidoVibracion();
      }
    } catch (err) { /* se reintenta en el siguiente ciclo */ }
  }

  // Se revisa al CARGAR la pagina (no solo justo despues de darle clic a
  // "Iniciar") si ya hay un monitoreo corriendo en el servidor -- asi,
  // si sales de Tramy y vuelves despues, el aviso "monitoreo activo"
  // sigue ahi fijo, en vez de desaparecer solo porque cerraste la
  // pestaña. Esto es clave para que la persona confie en que sigue
  // corriendo aunque no lo este viendo en pantalla todo el tiempo.
  window._tramyRevisarMonitoreosActivosAlCargar = async function() {
    // Envigado -- citas
    try {
      var respEnv = await fetch(ANT_API + '/envigado-citas-estado-monitoreo');
      var dataEnv = await respEnv.json();
      if (dataEnv.ok && dataEnv.activo) {
        var contEnv = document.getElementById('ant-citas-monitoreo-estado');
        var finEnv = new Date(dataEnv.fin_esperado);
        contEnv.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Monitoreo activo — revisando cada 30 segundos hasta las ' + finEnv.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'}) + '. El aviso aparecerá en Liquidación apenas se detecte algo.</div>';
        _tramyPonerBotonMonitoreo(document.getElementById('ant-btn-citas-monitoreo-iniciar'), true);
      }
    } catch (err) { /* se ignora, no es critico */ }

    // Envigado -- turnos llamados
    try {
      var respTur = await fetch(ANT_API + '/envigado-turnos-estado-monitoreo');
      var dataTur = await respTur.json();
      if (dataTur.ok && dataTur.activo) {
        var contTur = document.getElementById('ant-turnos-estado');
        var finTur = new Date(dataTur.fin_esperado);
        var numerosVigilados = (dataTur.numeros_vigilados && dataTur.numeros_vigilados.length)
          ? (' Avisando cuando llamen a <b>' + dataTur.numeros_vigilados.join(', ') + '</b>.') : '';
        contTur.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Monitoreo activo — corriendo hasta las ' + finTur.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit', hour12:false}) + '.' + numerosVigilados + '</div>';
        _tramyPonerBotonMonitoreo(document.getElementById('ant-btn-turnos-iniciar'), true);
      }
    } catch (err) { /* se ignora, no es critico */ }

    // Medellin
    try {
      var respMed = await fetch(ANT_API + '/medellin-citas-estado-monitoreo');
      var dataMed = await respMed.json();
      if (dataMed.ok && dataMed.activo) {
        var contMed = document.getElementById('ant-medellin-citas-monitoreo-estado');
        var finMed = new Date(dataMed.fin_esperado);
        contMed.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ Monitoreo activo — revisando cada 30 segundos hasta las ' + finMed.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'}) + '.</div>';
        _tramyPonerBotonMonitoreo(document.getElementById('ant-btn-medellin-citas-monitoreo-iniciar'), true);
        clearInterval(_tramyTimerMedellinCitas);
        _tramyTimerMedellinCitas = setInterval(_tramyCargarUltimoHallazgoMedellin, 10000);
        _tramyCargarUltimoHallazgoMedellin();
      }
    } catch (err) { /* se ignora, no es critico */ }
  };

  // No sobreescribe un campo si el usuario lo tiene enfocado ahora
  // mismo (escribiendo en el) -- sin esto, el refresco automatico cada
  // 15 segundos podia borrar lo que la persona estaba a punto de
  // guardar, reemplazandolo por el valor viejo del servidor.
  function _tramySetValueSiNoEnfocado(id, valor) {
    var el = document.getElementById(id);
    if (el && document.activeElement !== el) {
      el.value = valor;
    }
  }

  window.tramyCargarConfigMonitoreo = async function() {
    try {
      var resp = await fetch(ANT_API + '/monitoreo-config');
      var data = await resp.json();
      if (!data.ok) return;

      var env = data.envigado_citas;
      _tramySetValueSiNoEnfocado('cfgEnvIntervalo', env.intervalo_segundos);
      _tramySetValueSiNoEnfocado('cfgEnvHoraInicio', env.hora_inicio);
      _tramySetValueSiNoEnfocado('cfgEnvHoraFin', env.hora_fin);
      document.getElementById('cfgEnvEstadoVivo').innerHTML = _tramyFormatoEstadoVivo(env);
      _tramyPonerBotonToggle('cfgEnvBotonToggle', env.activo);

      // Monitor ESPEJO (siempre con proxy) -- estado y logica identica
      // a la de arriba, pero completamente separada.
      var medP = data.medellin_citas_proxy;
      if (medP) {
        _tramySetValueSiNoEnfocado('cfgMedProxyIntervalo', medP.intervalo_segundos);
        _tramySetValueSiNoEnfocado('cfgMedProxyHoraInicio', medP.hora_inicio);
        _tramySetValueSiNoEnfocado('cfgMedProxyHoraFin', medP.hora_fin);
        _tramySetValueSiNoEnfocado('cfgMedProxyUsuario', medP.usuario || '');
        _tramySetValueSiNoEnfocado('cfgMedProxyPlaca', medP.placa || '');
        _tramySetValueSiNoEnfocado('cfgMedProxySede', medP.sede || '');
        document.getElementById('cfgMedProxyPassTieneHint').textContent = medP.tiene_password ? '(ya hay una guardada)' : '(sin guardar)';
        document.getElementById('cfgMedProxyEstadoVivo').innerHTML = _tramyFormatoEstadoVivo(medP);
        _tramyPonerBotonToggle('cfgMedProxyBotonToggle', medP.activo);

        if (medP.activo && !_tramyTimerMedellinCitasProxy) {
          _tramyTimerMedellinCitasProxy = setInterval(_tramyCargarUltimoHallazgoMedellinProxy, 10000);
          _tramyCargarUltimoHallazgoMedellinProxy();
        }
      }
    } catch (err) { /* se ignora, no es critico */ }
  };

  // Cambia el texto/color del boton interruptor segun si el monitor
  // esta activo (rojo, dice "Detener") o no (verde, dice "Iniciar").
  // Ademas guarda el estado actual en el propio boton (data-activo),
  // para que el clic sepa hacia donde tiene que cambiar.
  function _tramyPonerBotonToggle(idBoton, activo) {
    var btn = document.getElementById(idBoton);
    if (!btn) return;
    btn.dataset.activo = activo ? '1' : '0';
    if (activo) {
      btn.textContent = 'Detener';
      btn.style.background = '#a33';
    } else {
      btn.textContent = 'Iniciar';
      btn.style.background = '';
    }
  }

  // Arma el mensaje de estado en vivo de un monitor, segun estos casos:
  // desactivado / activado-pero-fuera-de-horario / corriendo-de-verdad.
  function _tramyFormatoEstadoVivo(cfg) {
    if (!cfg.activo) {
      return '<span style="color:#888;">⚪ Desactivado.</span>';
    }
    if (!cfg.dentro_de_horario) {
      return '<span style="color:#b8860b;">🟡 Activado, pero fuera de horario ahora mismo (revisa entre ' + cfg.hora_inicio + ' y ' + cfg.hora_fin + ').</span>';
    }
    if (cfg.ultimo_error) {
      return '<span style="color:#c0392b;">🔴 Corriendo, pero la última revisión falló: ' + cfg.ultimo_error + '</span>';
    }
    if (cfg.ultima_revision) {
      var seg = Math.round((Date.now() - new Date(cfg.ultima_revision).getTime()) / 1000);
      var texto = seg < 60 ? (seg + ' segundos') : (Math.round(seg/60) + ' minutos');
      return '<span style="color:#1a6e3c;">🟢 Corriendo — última revisión hace ' + texto + '.</span>';
    }
    return '<span style="color:#1a6e3c;">🟢 Corriendo — esperando la primera revisión...</span>';
  }

  // El boton hace las dos cosas en un solo clic: guarda los campos
  // actuales del panel (intervalo, horario, credenciales) Y cambia el
  // estado activo/inactivo -- si estaba apagado, lo prende (Iniciar);
  // si estaba prendido, lo apaga (Detener).
  window.tramyToggleConfigMonitoreo = async function(monitor) {
    var idBoton = monitor === 'envigado_citas' ? 'cfgEnvBotonToggle'
      : monitor === 'medellin_citas_proxy' ? 'cfgMedProxyBotonToggle'
      : 'cfgMedBotonToggle';
    var btn = document.getElementById(idBoton);
    var estabaActivo = btn.dataset.activo === '1';

    var cont = document.getElementById('ant-config-monitoreo-estado');
    cont.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>' + (estabaActivo ? 'Deteniendo' : 'Iniciando') + '...</span></div>';

    var payload = { monitor: monitor, activo: !estabaActivo };
    if (monitor === 'envigado_citas') {
      payload.intervalo_segundos = parseInt(document.getElementById('cfgEnvIntervalo').value, 10) || 30;
      payload.hora_inicio = document.getElementById('cfgEnvHoraInicio').value;
      payload.hora_fin = document.getElementById('cfgEnvHoraFin').value;
    } else if (monitor === 'medellin_citas_proxy') {
      payload.intervalo_segundos = parseInt(document.getElementById('cfgMedProxyIntervalo').value, 10) || 60;
      payload.hora_inicio = document.getElementById('cfgMedProxyHoraInicio').value;
      payload.hora_fin = document.getElementById('cfgMedProxyHoraFin').value;
      payload.usuario = document.getElementById('cfgMedProxyUsuario').value.trim();
      payload.placa = document.getElementById('cfgMedProxyPlaca').value.trim();
      payload.sede = document.getElementById('cfgMedProxySede').value.trim();
      var passP = document.getElementById('cfgMedProxyPassword').value;
      if (passP) payload.password = passP;
      if (!estabaActivo && (!payload.usuario || !payload.placa || (!passP && !document.getElementById('cfgMedProxyPassTieneHint').textContent.includes('ya hay')))) {
        cont.innerHTML = '<div class="ant-alert error">Completa usuario, contraseña y placa antes de iniciar.</div>';
        return;
      }
    } else {
      payload.intervalo_segundos = parseInt(document.getElementById('cfgMedIntervalo').value, 10) || 60;
      payload.hora_inicio = document.getElementById('cfgMedHoraInicio').value;
      payload.hora_fin = document.getElementById('cfgMedHoraFin').value;
      payload.usuario = document.getElementById('cfgMedUsuario').value.trim();
      payload.placa = document.getElementById('cfgMedPlaca').value.trim();
      payload.sede = document.getElementById('cfgMedSede').value.trim();
      var pass = document.getElementById('cfgMedPassword').value;
      if (pass) payload.password = pass;
      if (!estabaActivo && (!payload.usuario || !payload.placa || (!pass && !document.getElementById('cfgMedPassTieneHint').textContent.includes('ya hay')))) {
        cont.innerHTML = '<div class="ant-alert error">Completa usuario, contraseña y placa antes de iniciar.</div>';
        return;
      }
    }

    try {
      var resp = await fetch(ANT_API + '/monitoreo-config', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      var data = await resp.json();
      if (data.ok) {
        cont.innerHTML = '<div class="ant-alert" style="background:#dcf5df;color:#1a5c2e;">✓ ' + (payload.activo ? 'Monitoreo iniciado.' : 'Monitoreo detenido.') + '</div>';
        document.getElementById('cfgMedPassword').value = '';
        var elPassP = document.getElementById('cfgMedProxyPassword');
        if (elPassP) elPassP.value = '';
        tramyCargarConfigMonitoreo();
      } else {
        cont.innerHTML = '<div class="ant-alert error">' + (data.error || 'No se pudo guardar.') + '</div>';
      }
    } catch (err) {
      cont.innerHTML = '<div class="ant-alert error">Error de conexión: ' + err.message + '</div>';
    }
  };
</script>

<script>
  var SUPABASE_URL = 'https://ddndoxtmffoaklhwbmkq.supabase.co';
  var SUPABASE_ANON_KEY = 'sb_publishable_x3cjuv1b2Uxq_-55-PsBqw_gCTto337';
  var supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

  (async function verificarAcceso(){
    var sessionRes = await supabaseClient.auth.getSession();
    var session = sessionRes.data.session;
    if(!session){ window.location.href = 'login.html'; return; }
    var profileRes = await supabaseClient
      .from('profiles').select('*').eq('id', session.user.id).maybeSingle();
    var profile = profileRes.data;
    if(!profile || profile.role !== 'admin'){ window.location.href = 'index.html'; return; }
    document.getElementById('loadingBox').style.display = 'none';
    document.getElementById('pagina').style.display = 'block';
    if ('clearAppBadge' in navigator) {
      navigator.clearAppBadge().catch(function(){});
    }
    if (typeof window._tramyRevisarEstadoNotificacionesPushAlCargar === 'function') {
      window._tramyRevisarEstadoNotificacionesPushAlCargar();
    }
    if (typeof window._tramyRevisarMonitoreosActivosAlCargar === 'function') {
      window._tramyRevisarMonitoreosActivosAlCargar();
    }
    if (typeof window.tramyCargarConfigMonitoreo === 'function') {
      window.tramyCargarConfigMonitoreo();
      // Se refresca sola cada 15 segundos, para que el estado en vivo
      // (🟢 corriendo / 🟡 fuera de horario / 🔴 con error) se mantenga
      // al dia mientras la pagina este abierta.
      setInterval(window.tramyCargarConfigMonitoreo, 15000);
    }
    if (typeof window.tramyCargarListaSolicitudesCitaEnvigado === 'function') {
      window.tramyCargarListaSolicitudesCitaEnvigado();
      setInterval(window.tramyCargarListaSolicitudesCitaEnvigado, 15000);
    }
  })();
</script>

</body>
</html>
