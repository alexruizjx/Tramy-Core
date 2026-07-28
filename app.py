<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tramy — Consulta y liquidación vehicular</title>
<link rel="icon" type="image/x-icon" href="favicon.ico">
<link rel="icon" type="image/png" sizes="16x16" href="favicon-16x16.png">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#1a2340">
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
</head>
<body>
<!-- Formulario Consulta Vehicular Antioquia v6 -->

<script>
  // Perfil del usuario logueado, disponible globalmente para el resto de la app.
  // Sera null hasta que se confirme que no hay sesion, o un objeto con
  // { full_name, role, settings: { business_name, slogan, contact_info, honorario } }
  window.tramyProfile = null;

  // Devuelve el honorario guardado (como string, listo para un input), o '0' si no aplica.
  // Interruptor Asesor / Cliente Final -- determina cual columna de
  // precio usar al buscar el honorario de cada municipio.
  window.tramyTipoClienteActual = 'asesor';

  window.tramyActualizarBotonesTipoCliente = function(){
    var btnA = document.getElementById('tramyBtnAsesor');
    var btnC = document.getElementById('tramyBtnClienteFinal');
    if(!btnA || !btnC) return;
    var activo = 'background:#1a2340; color:#fff;';
    var inactivo = 'background:none; color:#5b6472;';
    btnA.style.cssText += (window.tramyTipoClienteActual === 'asesor') ? activo : inactivo;
    btnC.style.cssText += (window.tramyTipoClienteActual === 'cliente_final') ? activo : inactivo;
  };

  window.tramySeleccionarTipoCliente = function(tipo){
    window.tramyTipoClienteActual = tipo;
    window.tramyActualizarBotonesTipoCliente();
    window.tramyAplicarHonorarioGuardado();
  };

  // Busca, en settings.honorarios_por_entidad (Normal y Dificil), el
  // precio guardado para un municipio especifico, segun el tipo de
  // cliente activo (Asesor o Cliente Final). Devuelve null si no hay
  // nada guardado para ese municipio en ninguna de las dos listas.
  window.tramyBuscarHonorarioMunicipio = function(municipio){
    if(!window.tramyProfile || !window.tramyProfile.settings) return null;
    var hpe = window.tramyProfile.settings.honorarios_por_entidad;
    if(!hpe || !municipio) return null;
    var municipioNorm = municipio.trim().toUpperCase();
    var listas = [hpe.normal || [], hpe.dificil || []];
    for(var i = 0; i < listas.length; i++){
      for(var j = 0; j < listas[i].length; j++){
        var item = listas[i][j];
        if((item.municipio || '').trim().toUpperCase() === municipioNorm){
          var valor = (window.tramyTipoClienteActual === 'cliente_final') ? item.precio_cliente_final : item.precio_asesor;
          return (valor !== undefined && valor !== null) ? valor : null;
        }
      }
    }
    return null;
  };

  window.tramyHonorarioGuardado = function(){
    var campoMunicipio = document.getElementById('ant-municipio');
    var municipio = campoMunicipio ? campoMunicipio.value : '';
    var porMunicipio = window.tramyBuscarHonorarioMunicipio(municipio);
    if(porMunicipio !== null) return String(porMunicipio);
    return '0';
  };

  // Aplica el honorario guardado al campo de liquidacion. A diferencia de
  // antes, esto SI puede pisar el valor actual -- porque ahora depende
  // del municipio y del interruptor Asesor/Cliente Final, y debe
  // actualizarse cada vez que cualquiera de esos dos cambie.
  window.tramyAplicarHonorarioGuardado = function(){
    var campo = document.getElementById('liq-honorarios');
    if(campo){
      campo.value = window.tramyHonorarioGuardado();
    }
  };

  window.tramyActualizarBotonesTipoCliente();

  // Precarga, en las filas de "cobros" (conceptos libres), los conceptos que
  // el usuario eligio como predeterminados desde su panel. Solo aplica a los
  // conceptos que NO son campos fijos del formulario (Paz y Salvo y Envios
  // y/o Domicilios se manejan aparte, ver tramyAjustarFijosPredeterminados).
  window.tramyAplicarConceptosPredeterminados = function(){
    if(!window.tramyProfile || !window.tramyProfile.settings) return;
    var todos = window.tramyProfile.settings.conceptos_predeterminados;
    if(!Array.isArray(todos) || todos.length === 0) return;

    var CONCEPTOS_DINAMICOS = ['4 X 1.000', 'Improntas'];
    var seleccion = todos.filter(function(c){ return CONCEPTOS_DINAMICOS.indexOf(c) >= 0; }).slice(0, 3);

    seleccion.forEach(function(nombre, idx){
      var n = idx + 1;
      if(n > 1 && !document.getElementById('liq-cobro-'+n) && typeof window.antAgregarCobro === 'function'){
        window.antAgregarCobro();
      }
      var campoNombre = document.getElementById('liq-cobro-nombre-'+n);
      if(campoNombre) campoNombre.value = nombre;

      var valores = window.tramyProfile.settings.conceptos_valores || {};
      var campoValor = document.getElementById('liq-cobro-valor-'+n);
      if(campoValor && valores[nombre]){
        campoValor.value = Number(valores[nombre]).toLocaleString('es-CO');
        campoValor.dispatchEvent(new Event('input'));
      }
    });
  };

  // Paz y Salvo y Envios y/o Domicilios son campos fijos del formulario, con
  // su propia logica de negocio (Paz y Salvo depende del municipio). Aqui
  // solo controlamos el caso de "el usuario NO lo quiere por defecto" -- lo
  // ocultamos aunque la logica normal diria que se muestre. Si SI lo eligio,
  // no tocamos nada y dejamos que la logica normal decida (para no mostrar
  // Paz y Salvo en un municipio donde no aplica).
  window.tramyAjustarFijosPredeterminados = function(){
    if(!window.tramyProfile || !window.tramyProfile.settings) return;
    var conceptos = window.tramyProfile.settings.conceptos_predeterminados;
    var valores = window.tramyProfile.settings.conceptos_valores || {};
    if(!Array.isArray(conceptos)) return; // el usuario nunca configuro esto -> no tocar nada

    if(conceptos.indexOf('Paz y Salvo') === -1){
      var rowPS = document.getElementById('liq-row-pazsalvo');
      var campoPS = document.getElementById('liq-pazsalvo');
      if(rowPS) rowPS.style.display = 'none';
      if(campoPS){ campoPS.value = '0'; campoPS.dispatchEvent(new Event('input')); }
    } else if(valores['Paz y Salvo']){
      var campoPS2 = document.getElementById('liq-pazsalvo');
      if(campoPS2){ campoPS2.value = Number(valores['Paz y Salvo']).toLocaleString('es-CO'); campoPS2.dispatchEvent(new Event('input')); }
    }
    if(conceptos.indexOf('Envios y/o Domicilios') === -1){
      var rowEnv = document.getElementById('liq-row-envios');
      var campoEnv = document.getElementById('liq-envios');
      if(rowEnv) rowEnv.style.display = 'none';
      if(campoEnv){ campoEnv.value = '0'; campoEnv.dispatchEvent(new Event('input')); }
    } else if(valores['Envios y/o Domicilios']){
      var campoEnv2 = document.getElementById('liq-envios');
      if(campoEnv2){ campoEnv2.value = Number(valores['Envios y/o Domicilios']).toLocaleString('es-CO'); campoEnv2.dispatchEvent(new Event('input')); }
    }
  };

  // Lista de vehiculos guardados del usuario logueado (placas consultadas antes).
  window.tramyVehiculosGuardados = [];

  // Guarda (o actualiza) el vehiculo leido por OCR en Railway (tabla
  // 'vehiculos', la misma que usa el RUNT). Si esa placa ya tiene datos de
  // una consulta al RUNT, esos prevalecen -- el backend se encarga de no
  // sobrescribirlos, aqui solo se manda lo que se leyo.
  window.tramyGuardarVehiculo = function(datos){
    if(!window.tramyCurrentUserId) return;
    if(!datos.placa) return;
    var API = 'https://consulta-impuestos-production.up.railway.app';
    fetch(API + '/guardar-vehiculo-ocr', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        placa: datos.placa, municipio: datos.municipio || null,
        tipo_documento: datos.tipo_documento || null, cedula: datos.cedula || null,
        apellidos: datos.apellidos || null, clase: datos.clase || null,
        marca: datos.marca || null, linea: datos.linea || null, modelo: datos.modelo || null,
        cilindrada: datos.cilindrada || null, servicio: datos.servicio || null,
        carroceria: datos.carroceria || null, limitacion_propiedad: datos.limitacion_propiedad || null,
        user_id: window.tramyCurrentUserId
      })
    }).catch(function(){});
  };

  // Trae la lista de vehiculos guardados y la muestra como chips seleccionables.
  window.tramyCargarVehiculosGuardados = function(){
    if(!window.tramySupabaseClient || !window.tramyCurrentUserId) return;
    window.tramySupabaseClient.from('vehiculos_guardados')
      .select('*').eq('user_id', window.tramyCurrentUserId)
      .order('actualizado_en', { ascending: false })
      .then(function(res){
        if(!res.data || res.data.length === 0) return;
        window.tramyVehiculosGuardados = res.data;
        window.tramyRenderVehiculosGuardados();
      });
  };

  window.tramyRenderVehiculosGuardados = function(){
    var panel = document.getElementById('tramyVehiculosPanel');
    var lista = document.getElementById('tramyVehiculosLista');
    if(!panel || !lista) return;
    lista.innerHTML = '';
    window.tramyVehiculosGuardados.forEach(function(v){
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.textContent = v.placa + (v.marca ? ' · ' + v.marca : '');
      chip.style.cssText = 'padding:8px 14px; border-radius:20px; border:1.5px solid #1a2340; background:#fff; color:#1a2340; font-weight:600; font-size:13.5px; cursor:pointer;';
      chip.onclick = function(){
        if(typeof window.aplicarDatosLeidos === 'function'){
          window.aplicarDatosLeidos(v);
        }
      };
      lista.appendChild(chip);
    });
    panel.style.display = 'block';
  };

  function tramyMostrarResultadoRUNT(r, esGuardadoPrevio, idDestino){
    var resultadoBox = document.getElementById(idDestino || 'tramyRuntResultado');
    var lineas = [];

    lineas.push('<b>' + (esGuardadoPrevio ? '📋 Datos guardados de una consulta anterior' : '✅ Consulta RUNT completada') + '</b>');
    if(r.leido_en){
      lineas.push('<span style="color:#5B6472; font-size:12.5px;">Datos leídos el ' + r.leido_en + '</span>');
    }
    lineas.push('SOAT: ' + (r.soat_vigente ? ('vigente hasta ' + (r.soat_fecha_fin || '')) : 'NO vigente'));
    lineas.push('RTM: ' + (r.rtm_vigente ? ('vigente hasta ' + (r.rtm_fecha_fin || '')) : 'NO vigente'));
    lineas.push('Gravámenes a la propiedad: ' + (r.gravamenes_propiedad ? 'SI' : 'NO'));

    if(r.ultimo_tramite_tipo){
      lineas.push('Último trámite: ' + r.ultimo_tramite_tipo + (r.ultimo_tramite_fecha ? ' (' + r.ultimo_tramite_fecha + ')' : ''));
    }

    if(r.garantia_inscripcion_id_prenda){
      lineas.push('Garantía mobiliaria - Inscripción de prenda registrado por ' + (r.garantia_inscripcion_entidad || ''));
    }
    if(r.garantia_levantamiento_id_prenda){
      lineas.push('Garantía mobiliaria - Levantamiento de prenda registrado por ' + (r.garantia_levantamiento_entidad || ''));
    }
    if(!r.garantia_inscripcion_id_prenda && !r.garantia_levantamiento_id_prenda){
      lineas.push('Sin garantías mobiliarias (prendas) registradas.');
    }

    if(r.garantia_favor_acreedor){
      lineas.push('Garantía a favor de: ' + r.garantia_favor_acreedor);
    }

    resultadoBox.innerHTML = lineas.join('<br>');
  }

  // Escribe los datos del RUNT en los campos del formulario. El RUNT manda:
  // sobrescribe lo que haya del OCR en los mismos campos.
  // Extrae el nombre del municipio desde el texto de "Autoridad de Transito"
  // del RUNT (ej. "STRIA TTOYTTE MCPAL LA ESTRELLA" -> "LA ESTRELLA"),
  // comparando contra la lista de municipios conocidos. Se revisan los mas
  // largos primero para que los de varias palabras (ej. "LA ESTRELLA")
  // no se confundan con coincidencias parciales.
  function tramyExtraerMunicipioDeAutoridad(texto){
    if(!texto || !window.ANT_MUNICIPIOS) return '';
    var limpio = texto.toUpperCase().trim()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, ''); // quitar tildes
    var candidatos = window.ANT_MUNICIPIOS.slice().sort(function(a,b){ return b.length - a.length; });
    for(var i = 0; i < candidatos.length; i++){
      if(limpio.indexOf(candidatos[i]) !== -1){
        return candidatos[i];
      }
    }
    return '';
  }

  // Determina si el vehiculo se considera "nuevo" para efectos de si ya le
  // corresponde tener revision tecnico-mecanica: motos/motocarros y
  // vehiculos de servicio publico son nuevos hasta los 2 años; los demas
  // (carros particulares) hasta los 5 años. Devuelve true/false, o null si
  // no hay fecha de matricula para calcularlo.
  // Lleva la placa actual a las demas secciones (Revision, Ejecucion,
  // Utilidades) por la URL, para que todo el trabajo quede ligado al
  // mismo vehiculo al moverse entre secciones.
  window.tramyActualizarLinksSecciones = function(placa, vigencias){
    if(!placa) return;
    ['tramyTabRevision', 'tramyTabEjecucion', 'tramyTabUtilidades'].forEach(function(id){
      var el = document.getElementById(id);
      if(!el) return;
      var base = el.getAttribute('href').split('?')[0];
      var url = base + '?placa=' + encodeURIComponent(placa);
      if(vigencias && vigencias.length) url += '&vigencias=' + encodeURIComponent(vigencias.join(','));
      el.setAttribute('href', url);
    });
  };

  // Si se llega a Liquidacion con una placa en la URL (viniendo de otra
  // seccion), se actualizan los enlaces de una vez con esa misma placa.
  (function(){
    var params = new URLSearchParams(window.location.search);
    var placaUrl = params.get('placa');
    if(placaUrl) window.tramyActualizarLinksSecciones(placaUrl);
  })();

  function tramyEsVehiculoNuevo(r){
    if(!r.fecha_matricula_inicial) return null;
    var fechaMat = new Date(r.fecha_matricula_inicial);
    if(isNaN(fechaMat.getTime())) return null;

    var edadAnios = (new Date() - fechaMat) / (1000 * 60 * 60 * 24 * 365.25);
    var clase = (r.clase || '').toUpperCase();
    var servicio = (r.servicio || '').toUpperCase();
    var esMotoOMotocarro = clase.indexOf('MOTO') !== -1;
    var esPublico = servicio.indexOf('PUBLIC') !== -1;
    var umbralAnios = (esMotoOMotocarro || esPublico) ? 2 : 5;

    return edadAnios < umbralAnios;
  }

  // Colorea filas completas del formulario segun lo que indiquen los datos
  // del RUNT, para que salten a la vista los puntos de atencion.
  function tramyAplicarColoresRunt(r, esVehiculoNuevo){
    var ROJO  = '#fbdcdc';
    var VERDE = '#dcf5df';

    function colorear(id, color){
      var el = document.getElementById(id);
      if(!el) return;
      var fila = el.closest('.ant-group');
      if(fila) fila.style.background = color || '';
    }

    // Gravamenes a la Propiedad (fusionado con Prenda) -- rojo si SI
    colorear('ant-limitacion-propiedad', r.gravamenes_propiedad ? ROJO : '');

    // Limitaciones a la Propiedad -- rojo si hay alguna registrada
    colorear('ant-limitaciones-propiedad', r.limitacion_tipo ? ROJO : '');

    // Garantia Mobiliaria -- verde si hay alguna registrada (inscripcion o levantamiento)
    var hayGarantiaMobiliaria = !!(r.garantia_inscripcion_id_prenda || r.garantia_levantamiento_id_prenda);
    colorear('ant-garantia-mobiliaria', hayGarantiaMobiliaria ? VERDE : '');

    // SOAT -- verde si vigente, rojo si no
    colorear('ant-soat', r.soat_vigente ? VERDE : ROJO);

    // Fecha Matricula Inicial -- verde si el vehiculo es nuevo
    colorear('ant-fecha_matricula', esVehiculoNuevo === true ? VERDE : '');

    // RTM -- verde si vigente, o si esta exento por ser nuevo y no tener
    // informacion registrada (no le corresponde aun); rojo en otro caso.
    var rtmExento = (esVehiculoNuevo === true) && !r.rtm_fecha_fin;
    if(r.rtm_vigente || rtmExento){
      colorear('ant-rtm', VERDE);
    } else {
      colorear('ant-rtm', ROJO);
    }

    // Fecha Ultimo Traspaso -- rojo si el traspaso fue hace menos de 3
    // meses (umbral aproximado; falta confirmar con la Gobernacion de
    // Antioquia el tiempo real que tardan en actualizar su base de datos
    // tras un traspaso). Esto alerta de que puede que a un no se pueda
    // consultar el impuesto/retefuente actual con el propietario nuevo.
    var tipoTramiteNorm2 = (r.ultimo_tramite_tipo || '').toUpperCase();
    if(tipoTramiteNorm2.indexOf('TRASPASO') !== -1 && r.ultimo_tramite_fecha){
      var fechaTraspaso = new Date(r.ultimo_tramite_fecha);
      if(!isNaN(fechaTraspaso.getTime())){
        var mesesDesdeTraspaso = (new Date() - fechaTraspaso) / (1000 * 60 * 60 * 24 * 30.44);
        colorear('ant-fecha-ultimo-traspaso', mesesDesdeTraspaso < 3 ? ROJO : '');
      }
    } else {
      colorear('ant-fecha-ultimo-traspaso', '');
    }
  }

  // Muestra, dentro del modulo de Impuesto Departamental, una alerta
  // cuando el ultimo tramite del vehiculo fue un traspaso hecho hace
  // menos de 3 meses -- explica por que puede fallar la consulta y si el
  // impuesto departamental se puede dar por al dia o no.
  // Para tramites MUNICIPALES: a diferencia del departamental (que es
  // especifico de traspaso, por el tema de que la Gobernacion tarda en
  // actualizar al propietario nuevo), aqui aplica CUALQUIER tramite -- ya
  // que en los municipios, para poder hacer casi cualquier tramite hay
  // que estar a paz y salvo del impuesto municipal. Excepciones: revision
  // tecnico-mecanica, SOAT, y certificado de tradicion, que no requieren
  // estar a paz y salvo para expedirse.
  var TRAMITES_EXCLUIDOS_PAZ_SALVO_MUNICIPAL = ['TECNICOMECANICA', 'TECNICO MECANICA', 'TECNOMECANICA', 'SOAT', 'TRADICION'];

  function tramyRevisarPazSalvoMunicipalPorTramite(r){
    window._tramyMunicipioAlDiaPorTramite = false;
    window._tramyMunicipioAlDiaFechaTexto = '';

    var tipoTramiteNorm = (r.ultimo_tramite_tipo || '').toUpperCase();
    if(!tipoTramiteNorm || !r.ultimo_tramite_fecha) return;

    var esExcluido = TRAMITES_EXCLUIDOS_PAZ_SALVO_MUNICIPAL.some(function(palabra){
      return tipoTramiteNorm.indexOf(palabra) !== -1;
    });
    if(esExcluido) return;

    var fechaTramite = new Date(r.ultimo_tramite_fecha);
    if(isNaN(fechaTramite.getTime())) return;

    var mismoAnio = (fechaTramite.getFullYear() === new Date().getFullYear());
    if(!mismoAnio) return;

    window._tramyMunicipioAlDiaPorTramite = true;
    window._tramyMunicipioAlDiaFechaTexto = r.ultimo_tramite_fecha;
  }

  function tramyRevisarAlertaTraspasoDepto(r){
    window._tramyTraspasoRecienteMismoAnio = false;

    var caja = document.getElementById('ant-alerta-traspaso-depto');
    var cajaVerde = document.getElementById('ant-alerta-traspaso-depto-verde');
    if(!caja || !cajaVerde) return;

    var tipoTramiteNorm = (r.ultimo_tramite_tipo || '').toUpperCase();
    if(tipoTramiteNorm.indexOf('TRASPASO') === -1 || !r.ultimo_tramite_fecha){
      caja.style.display = 'none';
      cajaVerde.style.display = 'none';
      return;
    }

    var fechaTraspaso = new Date(r.ultimo_tramite_fecha);
    if(isNaN(fechaTraspaso.getTime())){
      caja.style.display = 'none';
      cajaVerde.style.display = 'none';
      return;
    }

    var hoy = new Date();
    var mesesDesdeTraspaso = (hoy - fechaTraspaso) / (1000 * 60 * 60 * 24 * 30.44);
    if(mesesDesdeTraspaso >= 3){
      caja.style.display = 'none';
      cajaVerde.style.display = 'none';
      return;
    }

    var fechaTexto = r.ultimo_tramite_fecha;
    var mismoAnio = (fechaTraspaso.getFullYear() === hoy.getFullYear());
    window._tramyTraspasoRecienteMismoAnio = mismoAnio;

    if(mismoAnio){
      cajaVerde.innerHTML = '✓ El impuesto Departamental está al día.<br>Último traspaso realizado el día ' + fechaTexto;
      cajaVerde.style.display = 'block';
      caja.innerHTML = 'El haber realizado traspaso este mismo año significa que el vehículo está al día en la Gobernación. Sin embargo, también significa que el propietario ha cambiado, y como el traspaso fue hace menos de tres meses es muy posible que el módulo te dé error de propietario, ya que la Gobernación de Antioquia se tarda más o menos ese mismo tiempo para actualizar el propietario.'
        + '<br>Sin embargo, puedes intentarlo.'
        + '<br>Si necesitas el retefuente, más abajo hay un módulo para eso.';
      caja.style.display = 'block';
    } else {
      cajaVerde.style.display = 'none';
      caja.innerHTML = 'Ten en cuenta que el último traspaso realizado a este vehículo fue el día ' + fechaTexto + '. O sea, hace menos de tres meses, así que es posible que el propietario actual de este vehículo aún no esté actualizado en la Gobernación, por eso te puede dar error.'
        + '<br>El impuesto departamental puede no estar al día, si quieres consultarlo deberás llamar a la línea de atención al cliente de la Gobernación 604 444 4666.'
        + '<br>Si necesitas el retefuente, más abajo hay un módulo para eso.';
      caja.style.display = 'block';
    }
  }

  function tramyPoblarCamposDesdeRUNT(r){
    var mapa = {
      'ant-marca': r.marca, 'ant-linea': r.linea, 'ant-modelo': r.modelo,
      'ant-clase': r.clase, 'ant-servicio': r.servicio, 'ant-cilindrada': r.cilindrada,
      'ant-carroceria': r.carroceria, 'ant-color': r.color,
      'ant-numero_serie': r.numero_serie, 'ant-numero_motor': r.numero_motor,
      'ant-numero_chasis': r.numero_chasis, 'ant-vin': r.vin,
      'ant-combustible': r.combustible,
      'ant-puertas': r.puertas, 'ant-capacidad_carga': r.capacidad_carga,
      'ant-peso_bruto': r.peso_bruto_vehicular, 'ant-capacidad_pasajeros': r.capacidad_pasajeros,
      'ant-capacidad': r.pasajeros_sentados, 'ant-numero_ejes': r.numero_ejes,
      'ant-estado_vehiculo': r.estado_vehiculo, 'ant-fecha_matricula': r.fecha_matricula_inicial
    };
    Object.keys(mapa).forEach(function(id){
      var el = document.getElementById(id);
      if(el && mapa[id] !== undefined && mapa[id] !== null && mapa[id] !== ''){
        el.value = mapa[id];
      }
    });

    // Municipio: usa el guardado directo (viene del OCR) si existe; si no,
    // lo extrae de "Autoridad de Transito" (caso RUNT). Usa la misma
    // funcion/efectos que si el usuario lo hubiera escogido manualmente
    // (activa impuestos departamentales/municipales y tramites).
    var municipioDetectado = r.municipio || tramyExtraerMunicipioDeAutoridad(r.autoridad_transito);
    if(r.autoridad_transito) window.tramyUltimoAutoridadTransito = r.autoridad_transito;
    if(municipioDetectado && typeof window.selMunicipio === 'function'){
      window.selMunicipio(municipioDetectado);
    }

    // Identificacion del propietario -- el RUNT nunca la trae, asi que solo
    // se llena desde el cache si el campo esta VACIO. Nunca se sobrescribe
    // lo que el usuario ya escribio (eso fue justo el bug: escribir una
    // cedula nueva quedaba "atascado" porque el cache reponia la vieja).
    var tipoDocEl = document.getElementById('ant-tipodoc');
    if(tipoDocEl && r.propietario_tipo_documento && !tipoDocEl.value) tipoDocEl.value = r.propietario_tipo_documento;

    var cedulaEl = document.getElementById('ant-cedula');
    if(cedulaEl && r.propietario_cedula && !cedulaEl.value.trim()) cedulaEl.value = r.propietario_cedula;

    var apellidosEl = document.getElementById('ant-apellidos');
    if(apellidosEl && r.propietario_nombre && !apellidosEl.value.trim()) apellidosEl.value = r.propietario_nombre;

    var gravamenes = document.getElementById('ant-limitacion-propiedad');
    if(gravamenes){
      gravamenes.value = r.gravamenes_propiedad ? 'SI' : 'NO';
      gravamenes.dispatchEvent(new Event('change'));
    }

    var soat = document.getElementById('ant-soat');
    if(soat) soat.value = r.soat_vigente ? ('Vigente hasta ' + (r.soat_fecha_fin || '')) : 'NO vigente';

    var esVehiculoNuevo = tramyEsVehiculoNuevo(r);
    var rtmExento = (esVehiculoNuevo === true) && !r.rtm_fecha_fin;

    var rtm = document.getElementById('ant-rtm');
    if(rtm){
      if(r.rtm_vigente){
        rtm.value = 'Vigente hasta ' + (r.rtm_fecha_fin || '');
      } else if(rtmExento){
        rtm.value = 'No aplica aún (vehículo nuevo)';
      } else {
        rtm.value = 'NO vigente';
      }
    }

    var tramite = document.getElementById('ant-ultimo-tramite');
    if(tramite) tramite.value = r.ultimo_tramite_tipo ? (r.ultimo_tramite_tipo + (r.ultimo_tramite_fecha ? ' (' + r.ultimo_tramite_fecha + ')' : '')) : 'Sin información';

    // Fecha de ultimo traspaso -- solo se sabe si el traspaso fue
    // justamente el ultimo tramite hecho al vehiculo (si despues hubo
    // otro tramite, el RUNT ya no muestra la fecha del traspaso aparte).
    var fechaTraspasoEl = document.getElementById('ant-fecha-ultimo-traspaso');
    if(fechaTraspasoEl){
      var tipoTramiteNorm = (r.ultimo_tramite_tipo || '').toUpperCase();
      if(tipoTramiteNorm.indexOf('TRASPASO') !== -1 && r.ultimo_tramite_fecha){
        fechaTraspasoEl.value = r.ultimo_tramite_fecha;
      } else {
        fechaTraspasoEl.value = 'Sin traspaso reciente registrado como último trámite';
      }
    }

    var garantiaFavor = document.getElementById('ant-garantia-favor');
    if(garantiaFavor) garantiaFavor.value = r.garantia_favor_acreedor || 'Sin información';

    var garantiaMob = document.getElementById('ant-garantia-mobiliaria');
    if(garantiaMob){
      if(r.garantia_inscripcion_id_prenda){
        garantiaMob.value = 'Inscripción registrada por ' + (r.garantia_inscripcion_entidad || '');
      } else if(r.garantia_levantamiento_id_prenda){
        garantiaMob.value = 'Levantamiento registrado por ' + (r.garantia_levantamiento_entidad || '');
      } else {
        garantiaMob.value = 'Sin garantías mobiliarias registradas';
      }
    }

    var limitacionesEl = document.getElementById('ant-limitaciones-propiedad');
    if(limitacionesEl){
      if(r.limitacion_tipo){
        limitacionesEl.value = r.limitacion_tipo + (r.limitacion_entidad ? ' - ' + r.limitacion_entidad : '');
      } else {
        limitacionesEl.value = 'Sin limitaciones registradas';
      }
    }

    tramyAplicarColoresRunt(r, esVehiculoNuevo);
    tramyRevisarAlertaTraspasoDepto(r);
    tramyRevisarPazSalvoMunicipalPorTramite(r);

    var placaInput = document.getElementById('ant-placa');
    if(placaInput && r.placa) placaInput.value = r.placa;

    var placaEditarEl = document.getElementById('ant-placa-editar');
    if(placaEditarEl && r.placa){
      placaEditarEl.value = r.placa;
      placaEditarEl.dispatchEvent(new Event('input'));
    }
  }

  // Se dispara automaticamente cuando hay tipo de documento + numero de
  // documento + placa (ya sea escritos a mano o leidos por OCR). Revisa el
  // cache global (de cualquier usuario, para ahorrar 2Captcha): si hay algo
  // reciente lo trae con la fecha y opcion de refrescar; si no, muestra un
  // boton para consultar (nunca consulta sola, sin que el usuario lo pida).
  window.tramyVerificarDisponibilidadRunt = async function(){
    var estadoBox = document.getElementById('tramyRuntEstadoInfo');
    if(!estadoBox) return;

    // Esta funcion tiene costo potencial (2Captcha), asi que solo aplica
    // para la cuenta Premium -- para Free, nunca se muestra nada aqui.
    if(!window.tramyProfile || window.tramyProfile.role !== 'admin'){
      estadoBox.style.display = 'none';
      return;
    }

    var tipoDocEl = document.getElementById('ant-tipodoc');
    var tipoDoc = tipoDocEl ? tipoDocEl.value : '';
    var cedula  = (document.getElementById('ant-cedula').value || '').trim();
    var placaEditarEl = document.getElementById('ant-placa-editar');
    var placa = (placaEditarEl ? placaEditarEl.value : (document.getElementById('ant-placa').value || '')).trim().toUpperCase();

    if(!tipoDoc || !cedula || !placa){
      estadoBox.style.display = 'none';
      return;
    }

    var API = 'https://consulta-impuestos-production.up.railway.app';
    estadoBox.style.display = 'block';
    estadoBox.innerHTML = '⏳ Revisando si ya tenemos datos guardados de esta placa...';

    try{
      var resp = await fetch(API + '/vehiculo-runt-guardado?placa=' + encodeURIComponent(placa));
      var data = await resp.json();

      if(data && data.placa){
        tramyPoblarCamposDesdeRUNT(data);
        estadoBox.innerHTML =
          '📋 Datos leídos el ' + (data.leido_en || '') + '. ' +
          '<button onclick="tramyConsultarRUNTForzado()" style="margin-left:6px; padding:4px 10px; border-radius:6px; border:none; background:#1a2340; color:#fff; font-size:12px; cursor:pointer;">Consultar de nuevo</button>';

        // Igual queda registrado en "Mis vehiculos consultados", aunque el
        // dato haya venido del cache y no de una consulta nueva.
        if(window.tramyCurrentUserId){
          fetch(API + '/registrar-mi-consulta?user_id=' + encodeURIComponent(window.tramyCurrentUserId) +
            '&placa=' + encodeURIComponent(placa) + '&cedula=' + encodeURIComponent(cedula)).catch(function(){});
        }
      } else {
        estadoBox.innerHTML =
          '<button onclick="tramyConsultarRUNTForzado()" style="padding:9px 16px; border-radius:8px; border:none; background:#1a2340; color:#fff; font-size:13px; font-weight:600; cursor:pointer;">🔎 Consultar datos en el RUNT</button>';
      }
    } catch(err){
      estadoBox.style.display = 'none';
      console.log('Error revisando cache RUNT:', err);
    }
  };

  // Dispara la verificacion automaticamente mientras se escriben los datos
  // a mano (con una pequeña espera, para no disparar una peticion por cada
  // tecla), y tambien cuando cambia el tipo de documento. Solo para Premium.
  var tramyVerificarRuntTimeout = null;
  document.addEventListener('input', function(e){
    if(!e.target || (e.target.id !== 'ant-cedula' && e.target.id !== 'ant-placa-editar')) return;
    if(!window.tramyProfile || window.tramyProfile.role !== 'admin') return;
    clearTimeout(tramyVerificarRuntTimeout);
    tramyVerificarRuntTimeout = setTimeout(window.tramyVerificarDisponibilidadRunt, 500);
  });
  document.addEventListener('change', function(e){
    if(!e.target || e.target.id !== 'ant-tipodoc') return;
    if(!window.tramyProfile || window.tramyProfile.role !== 'admin') return;
    window.tramyVerificarDisponibilidadRunt();
  });

  // Fuerza una consulta nueva al RUNT (con costo de 2Captcha), sin importar
  // si ya habia algo guardado.
  // Abre el panel para elegir el tramite y generar el FUN diligenciado.
  window.tramyAbrirGenerarFUN = function(){
    var panel = document.getElementById('tramyFunPanel');
    var abrir = panel.style.display !== 'block';
    panel.style.display = abrir ? 'block' : 'none';
    if(abrir){
      document.getElementById('tramyFunSeleccionTramite').style.display = 'block';
      document.getElementById('tramyFunResultado').style.display = 'none';
    }
  };

  // Mostrar el campo de "municipio de destino" solo si el tramite elegido
  // es un traslado.
  document.addEventListener('change', function(e){
    if(e.target && e.target.id === 'tramyFunTramite'){
      var esTraslado = e.target.value.indexOf('TRASLADO') !== -1;
      document.getElementById('tramyFunTrasladoWrap').style.display = esTraslado ? 'block' : 'none';
    }
  });

  window.tramyGenerarFUN = async function(){
    var resultado = document.getElementById('tramyFunResultado');
    resultado.style.display = 'block';
    resultado.innerHTML = '⏳ Generando el FUN... esto puede tardar 10-20 segundos.';

    function val(id){
      var el = document.getElementById(id);
      return el ? el.value.trim() : '';
    }

    var datos = {
      placa: val('ant-placa-editar'),
      municipio: val('ant-municipio') || val('ant-municipio-input'),
      autoridad_transito: window.tramyUltimoAutoridadTransito || '',
      servicio: val('ant-servicio'),
      clase: val('ant-clase'),
      marca: val('ant-marca'),
      linea: val('ant-linea'),
      modelo: val('ant-modelo'),
      color: val('ant-color'),
      cilindrada: val('ant-cilindrada'),
      carroceria: val('ant-carroceria'),
      capacidad: val('ant-capacidad'),
      numero_serie: val('ant-numero_serie'),
      numero_motor: val('ant-numero_motor'),
      numero_chasis: val('ant-numero_chasis'),
      vin: val('ant-vin'),
      gravamenes_propiedad: val('ant-limitacion-propiedad') === 'SI',
      fecha_matricula_inicial: val('ant-fecha_matricula'),
      tramite: document.getElementById('tramyFunTramite').value,
      traslado_municipio: val('tramyFunTrasladoMunicipio'),
      // El formulario del FUN pide apellidos y nombres por separado, pero
      // Tramy guarda el nombre completo en un solo campo -- se manda todo
      // en "nombres" por ahora (se ve completo en el PDF, solo que en una
      // sola columna en vez de repartido en Primer/Segundo Apellido).
      propietario_nombres: val('ant-apellidos'),
      propietario_documento: val('ant-cedula'),
    };

    try{
      var API = 'https://consulta-impuestos-production.up.railway.app';
      var resp = await fetch(API + '/generar-fun', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(datos)
      });
      var data = await resp.json();

      if(data.ok && data.url){
        resultado.innerHTML = '✅ FUN generado.<br><br>' +
          '<a href="' + data.url + '" target="_blank" style="display:inline-block; padding:10px 18px; background:#1a6e3c; color:#fff; text-decoration:none; border-radius:8px; font-weight:700;">📄 Descargar FUN</a>';
      } else {
        resultado.innerHTML = '❌ ' + (data.error || 'Ocurrió un error generando el FUN.');
      }
    } catch(err){
      resultado.innerHTML = '❌ Error de conexión: ' + err.message;
    }
  };

  window.tramyConsultarRUNTForzado = async function(){
    var placa  = (document.getElementById('ant-placa').value || '').trim().toUpperCase();
    var cedula = (document.getElementById('ant-cedula').value || '').trim();
    var estadoBox = document.getElementById('tramyRuntEstadoInfo');
    estadoBox.style.display = 'block';

    if(!placa || !cedula){
      estadoBox.innerHTML = '⚠️ Escribe la placa y la cédula del propietario antes de consultar el RUNT.';
      return;
    }

    var API = 'https://consulta-impuestos-production.up.railway.app';
    estadoBox.innerHTML = '⏳ Consultando el RUNT... esto puede tardar 1-2 minutos.';

    try{
      var url = API + '/consultar-runt-vehiculo?placa=' + encodeURIComponent(placa) + '&cedula=' + encodeURIComponent(cedula);
      if(window.tramyCurrentUserId) url += '&user_id=' + encodeURIComponent(window.tramyCurrentUserId);

      var resp = await fetch(url);
      var data = await resp.json();
      if(!data.job_id){
        if(data.limite_activo){
          estadoBox.innerHTML = '⏳ ' + data.error;
        } else {
          estadoBox.innerHTML = '❌ No se pudo iniciar la consulta: ' + (data.error || 'error desconocido');
        }
        return;
      }

      var intentos = 0;
      var intervalo = setInterval(async function(){
        intentos++;
        if(intentos > 40){
          clearInterval(intervalo);
          estadoBox.innerHTML = '❌ La consulta tardó demasiado. Intenta de nuevo.';
          return;
        }
        var estadoResp = await fetch(API + '/consultar/estado?job_id=' + data.job_id);
        var estado = await estadoResp.json();

        if(estado.estado === 'listo'){
          clearInterval(intervalo);
          tramyPoblarCamposDesdeRUNT(estado.resultado);
          estadoBox.innerHTML = '✅ Consulta RUNT completada (' + (estado.resultado.leido_en || '') + ')';
        } else if(estado.estado === 'error'){
          clearInterval(intervalo);
          estadoBox.innerHTML = '❌ ' + (estado.mensaje || 'Ocurrió un error consultando el RUNT.');
        } else {
          estadoBox.innerHTML = '⏳ ' + (estado.mensaje || 'Consultando...');
        }
      }, 4000);
    } catch(err){
      estadoBox.innerHTML = '❌ Error de conexión: ' + err.message;
    }
  };

  // Boton "Mis vehiculos consultados": abre un campo de busqueda con
  // autocompletado sobre el historial PERSONAL (solo lo que este usuario
  // especificamente ha consultado antes) -- se filtra en el servidor
  // mientras se escribe, para que funcione bien aunque la lista crezca
  // mucho (a diferencia de una lista fija de chips).
  window.tramyAbrirMisVehiculosConsultados = function(){
    var panel = document.getElementById('tramyMisVehiculosRuntPanel');
    var abrir = panel.style.display !== 'block';
    panel.style.display = abrir ? 'block' : 'none';

    if(abrir && !window.tramyCurrentUserId){
      document.getElementById('tramyMisVehiculosBuscar').placeholder = 'Inicia sesión para ver tu historial';
    }
    if(abrir){
      document.getElementById('tramyMisVehiculosBuscar').focus();
      window.tramyMisVehiculosFiltrar();
    }
  };

  var tramyMisVehiculosTimeout = null;

  window.tramyMisVehiculosFiltrar = function(){
    var input = document.getElementById('tramyMisVehiculosBuscar');
    var lista = document.getElementById('tramyMisVehiculosRuntLista');
    var texto = input.value.trim().toUpperCase();

    clearTimeout(tramyMisVehiculosTimeout);

    if(!window.tramyCurrentUserId){
      lista.style.display = 'none';
      return;
    }

    // Espera un poco a que la persona deje de escribir, para no disparar
    // una peticion por cada tecla.
    tramyMisVehiculosTimeout = setTimeout(async function(){
      var API = 'https://consulta-impuestos-production.up.railway.app';
      try{
        var resp = await fetch(API + '/mis-vehiculos-runt?user_id=' + encodeURIComponent(window.tramyCurrentUserId) +
          (texto ? '&q=' + encodeURIComponent(texto) : ''));
        var data = await resp.json();

        if(!Array.isArray(data) || data.length === 0){
          lista.innerHTML = '<div style="padding:12px; text-align:center; font-size:13px; color:#5B6472;">' +
            (texto ? 'Sin resultados.' : 'Todavía no has consultado ningún vehículo en el RUNT.') + '</div>';
          lista.style.display = 'block';
          return;
        }

        lista.innerHTML = '';
        data.forEach(function(v){
          var item = document.createElement('div');
          var etiquetaFuente = v.fuente === 'RUNT'
            ? '<span style="color:#0F6E56; font-size:11px; font-weight:700;">✓ RUNT</span>'
            : '<span style="color:#B23B2E; font-size:11px; font-weight:700;">parcial (OCR)</span>';
          item.innerHTML = '<div style="display:flex; justify-content:space-between; align-items:center;">' +
            '<span>' + v.placa + (v.marca ? ' · ' + v.marca : '') + (v.linea ? ' ' + v.linea : '') + '</span>' +
            etiquetaFuente + '</div>';
          item.title = 'Consultado el ' + (v.actualizado_en || '');
          item.style.cssText = 'padding:10px 12px; cursor:pointer; font-size:13.5px; border-bottom:1px solid #EFE9DB;';
          item.onmouseover = function(){ item.style.background = '#f4f6fb'; };
          item.onmouseout = function(){ item.style.background = '#fff'; };
          item.onclick = async function(){
            var r = await fetch(API + '/vehiculo-runt-guardado?placa=' + encodeURIComponent(v.placa));
            var datos = await r.json();
            if(datos && datos.placa){
              if(typeof window.antModoEntrada === 'function') window.antModoEntrada('manual');
              tramyPoblarCamposDesdeRUNT(datos);
              var estadoBox = document.getElementById('tramyRuntEstadoInfo');
              estadoBox.style.display = 'block';
              estadoBox.innerHTML = '📋 Datos leídos el ' + (datos.leido_en || '') +
                '. <button onclick="tramyConsultarRUNTForzado()" style="margin-left:6px; padding:4px 10px; border-radius:6px; border:none; background:#1a2340; color:#fff; font-size:12px; cursor:pointer;">Consultar de nuevo</button>';
            }
            document.getElementById('tramyMisVehiculosRuntPanel').style.display = 'none';
            input.value = '';
            lista.style.display = 'none';
          };
          lista.appendChild(item);
        });
        lista.style.display = 'block';
      } catch(err){
        lista.innerHTML = '<div style="padding:12px; text-align:center; font-size:13px; color:#5B6472;">Error cargando el historial.</div>';
        lista.style.display = 'block';
      }
    }, 300);
  };

  // Cerrar el desplegable si se hace clic afuera
  document.addEventListener('click', function(e){
    var lista = document.getElementById('tramyMisVehiculosRuntLista');
    if(lista && !e.target.closest('#tramyMisVehiculosRuntPanel')){
      lista.style.display = 'none';
    }
  });

  (function(){
    var SUPABASE_URL = 'https://ddndoxtmffoaklhwbmkq.supabase.co';
    var SUPABASE_ANON_KEY = 'sb_publishable_x3cjuv1b2Uxq_-55-PsBqw_gCTto337';
    var navClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    window.tramySupabaseClient = navClient;

    navClient.auth.getSession().then(function(result){
      var session = result.data.session;
      if(!session) return;

      window.tramyCurrentUserId = session.user.id;

      navClient.from('profiles').select('*').eq('id', session.user.id).maybeSingle()
        .then(function(res){
          if(!res.data) return;
          window.tramyProfile = res.data;

          var displayName = res.data.full_name || session.user.email;
          var link = document.getElementById('navAuthLink');
          if(link){
            link.textContent = '👤 ' + displayName;
            link.href = 'panel.html';
          }

          // Inicializar el interruptor Asesor/Cliente Final con lo que el
          // usuario haya configurado como predeterminado en su panel.
          if(res.data.settings && res.data.settings.cliente_predeterminado){
            window.tramyTipoClienteActual = res.data.settings.cliente_predeterminado;
          }
          window.tramyActualizarBotonesTipoCliente();

          // Precargar el honorario guardado en el campo de liquidacion,
          // por si el usuario ya llego a esa parte del formulario.
          window.tramyAplicarHonorarioGuardado();
          window.tramyAplicarConceptosPredeterminados();
          window.tramyCargarVehiculosGuardados();

          // Si se llega desde otra seccion (Revision, Ejecucion,
          // Utilidades) con una placa en la URL, se carga automaticamente
          // lo que ya tengamos guardado de ese vehiculo -- todo el trabajo
          // queda ligado al mismo vehiculo sin repetir datos a mano.
          (function(){
            var paramsUrl = new URLSearchParams(window.location.search);
            var placaUrl = paramsUrl.get('placa');
            if(!placaUrl) return;
            fetch(ANT_API + '/vehiculo-runt-guardado?placa=' + encodeURIComponent(placaUrl))
              .then(function(r){ return r.json(); })
              .then(function(datos){
                if(datos && datos.placa){
                  if(typeof window.antModoEntrada === 'function') window.antModoEntrada('manual');
                  tramyPoblarCamposDesdeRUNT(datos);
                  var estadoBox = document.getElementById('tramyRuntEstadoInfo');
                  if(estadoBox){
                    estadoBox.style.display = 'block';
                    estadoBox.innerHTML = '📋 Datos leídos el ' + (datos.leido_en || '') +
                      '. <button onclick="tramyConsultarRUNTForzado()" style="margin-left:6px; padding:4px 10px; border-radius:6px; border:none; background:#1a2340; color:#fff; font-size:12px; cursor:pointer;">Consultar de nuevo</button>';
                  }
                }
              })
              .catch(function(){});
          })();

          // Los botones de RUNT tienen costo real (2Captcha), asi que por
          // ahora solo se muestran desde Plus en adelante (no para Free).
          // Lo mismo para "Mis Vehiculos" y "Generar FUN". La Declaracion
          // Sugerida se movio a la seccion de Utilidades (solo Master).
          var esMaster = (res.data.role === 'admin');
          var esPlus = (res.data.role === 'plus') || esMaster;
          window.tramyEsAdmin = esMaster;
          window.tramyEsPlus = esPlus;

          if(esMaster){
            ['tramyTabRevision', 'tramyTabEjecucion', 'tramyTabUtilidades'].forEach(function(id){
              var el = document.getElementById(id);
              if(el) el.style.display = 'inline-block';
            });

            // Aviso de citas disponibles en Envigado -- exclusivo Master,
            // usa el ultimo resultado ya guardado (rapido, sin consultar
            // la API en vivo cada vez que alguien entra a Tramy). La
            // revision en vivo se hace desde Ejecucion.
            // OJO: se usa la URL directa (no la variable ANT_API) porque
            // este bloque corre en un <script> anterior al que declara
            // ANT_API -- usarla aqui rompia con "ANT_API is not defined"
            // y eso cortaba toda la funcion, incluyendo la revelacion de
            // los botones de Plus/Master mas abajo.
            try {
              fetch('https://consulta-impuestos-production.up.railway.app/envigado-citas-ultimo-resultado')
                .then(function(r){ return r.json(); })
                .then(function(data){
                  if(!data.ok || !data.hay_citas) return;
                  var caja = document.getElementById('tramyAvisoCitasEnvigado');
                  var lista = data.disponibles.slice(0, 5).map(function(d){
                    return '<b>' + d.sede + '</b> — ' + d.fecha + ' (' + d.cantidad_horarios + ' horarios)';
                  }).join('<br>');
                  caja.innerHTML = '🔔 <b>¡Hay citas disponibles en Envigado!</b><br>' + lista
                    + '<br><a href="ejecucion.html" style="color:#1a5c2e; text-decoration:underline;">Ver en Ejecución →</a>';
                  caja.style.display = 'block';
                })
                .catch(function(){});
            } catch(e) { /* nunca debe tumbar el resto de la funcion */ }
          }

          if(esPlus){
            var btnMisVehiculos = document.getElementById('btn-entrada-mis-vehiculos');
            if(btnMisVehiculos) btnMisVehiculos.style.display = 'block';
            var camposPremium = document.getElementById('tramyCamposPremium');
            if(camposPremium) camposPremium.style.display = 'contents';
            var btnFun = document.getElementById('ant-btn-fun');
            if(btnFun) btnFun.style.display = 'block';
          }
        });
    });
  })();
</script>

<style>
  .ant-app-navbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
    background: #1a2340; height: 48px;
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.18);
  }
  .ant-app-navbar-titulo {
    font-family: Arial, sans-serif; font-size: 16px; font-weight: 900;
    color: #fff; letter-spacing: 1px;
  }
  .ant-app-navbar-salir {
    font-family: Arial, sans-serif; font-size: 13px; font-weight: 700;
    color: #fff; text-decoration: none; padding: 6px 14px;
    border: 1px solid rgba(255,255,255,0.3); border-radius: 6px;
    transition: background .2s;
  }
  .ant-app-navbar-salir:hover { background: rgba(255,255,255,0.12); }

  .ant-secciones-nav {
    position: fixed; top: 48px; left: 0; right: 0; z-index: 9998;
    background: #f4f6fb; border-bottom: 1px solid #dde3ec;
    display: flex; gap: 4px; padding: 6px 12px; overflow-x: auto;
  }
  .tramy-seccion-tab {
    font-family: Arial, sans-serif; font-size: 12.5px; font-weight: 700;
    color: #5b6472; text-decoration: none; padding: 7px 14px;
    border-radius: 7px; white-space: nowrap; transition: background .15s, color .15s;
  }
  .tramy-seccion-tab:hover { background: #e4e9f4; }
  .tramy-seccion-tab.activa { background: #1a2340; color: #fff; }

  .ant-wrap { max-width: 760px; margin: 0 auto; padding: 86px 8px 24px 8px; font-family: Arial, sans-serif; }

  .ant-top { background: #fff; border: 1px solid #dde3ec; border-radius: 10px; padding: 13px 18px; margin-bottom: 10px; }
  #ant-saludo { padding-top: 3px; padding-bottom: 6px; margin-bottom: 6px; margin-top: 0; }

  .ant-card { background: #fff; border: 1px solid #dde3ec; border-radius: 10px; padding: 16px 18px; margin-bottom: 10px; display: none; }
  .ant-card.visible { display: block; }
  .ant-card-liq { background: #fff; border: 1px solid #dde3ec; border-radius: 10px; padding: 16px 18px; margin-bottom: 10px; }

  .ant-bloque-titulo {
    font-size: 15px; font-weight: 900; color: #fff;
    background: #1a2340; border-radius: 7px;
    padding: 11px 16px; margin-bottom: 16px;
    display: flex; align-items: center; justify-content: space-between;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .ant-bloque-titulo-texto { flex: 1; text-align: center; }
  .ant-bloque-titulo-chevron { font-size: 14px; min-width: 20px; text-align: right; }
  .ant-bloque-titulo-left { min-width: 20px; }

  .ant-bienvenida { text-align: center; padding: 2px 20px 2px; margin-bottom: 2px; }
  .ant-bienvenida-titulo { font-size: 22px; font-weight: 900; color: #0047AB; margin-bottom: 6px; }
  .ant-bienvenida-sub { font-size: 15px; color: #555; line-height: 1.6; }

  /* Botones entrada */
  .ant-entrada-btns { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
  .ant-entrada-btn {
    flex: 1 1 calc(50% - 4px); padding: 10px 6px; border: 2px solid #dde3ec; border-radius: 9px;
    background: #f8fafc; cursor: pointer; font-size: 12px; font-weight: 700;
    color: #1a2340; text-align: center; transition: all .2s;
  }
  @media(min-width: 480px) { .ant-entrada-btn { flex: 1; } }
  .ant-entrada-btn:hover { border-color: #3b7de8; background: #f0f6ff; color: #1a5fa8; }
  .ant-entrada-btn.activo { border-color: #1a5fa8; background: #e8f0f8; color: #1a5fa8; }
  .ant-entrada-btn .ant-entrada-icon { font-size: 22px; display: block; margin-bottom: 4px; }

  /* Lista desplegable honorarios y cobros */
  .ant-honorarios-wrap { position: relative; }
  .ant-cobro-valor-wrap { position: relative; flex: 1; }
  .ant-cobro-valor-wrap .ant-liq-input { width: 100%; box-sizing: border-box; }
  .ant-chips-wrap { position: absolute; top: 100%; left: 0; right: 0; border: 0.5px solid var(--color-border-secondary,#ccd3de); border-radius: var(--border-radius-md,8px); overflow: hidden; margin-top: 3px; z-index: 1000; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.10); max-height: 220px; overflow-y: auto; }
  .ant-chip { display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; font-size: 13px; cursor: pointer; color: var(--color-text-primary,#1a2340); border-bottom: 0.5px solid var(--color-border-tertiary,#eef0f5); background: var(--color-background-primary,#fff); transition: background .12s; }
  .ant-chip:last-child { border-bottom: none; }
  .ant-chip:hover { background: var(--color-background-secondary,#f5f7fa); }
  .ant-chip.activo { background: #EAF3DE; color: #3B6D11; }
  .ant-chip .ant-chip-check { font-size: 11px; color: #3B6D11; opacity: 0; }
  .ant-chip.activo .ant-chip-check { opacity: 1; }
  /* Autocomplete cobros (concepto) */
  .ant-cobro-wrap { position: relative; }
  .ant-cobro-lista { position: absolute; top: 100%; left: 0; right: 0; background: var(--color-background-primary,#fff); border: 0.5px solid var(--color-border-secondary,#ccd3de); border-radius: 8px; z-index: 1000; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.10); max-height: 200px; overflow-y: auto; }
  .ant-cobro-lista div { padding: 10px 12px; cursor: pointer; font-size: 14px; color: var(--color-text-primary,#1a2340); border-bottom: 0.5px solid var(--color-border-tertiary,#eef0f5); }
  .ant-cobro-lista div:last-child { border-bottom: none; }
  .ant-cobro-lista div:hover, .ant-cobro-lista div.activo { background: var(--color-background-secondary,#e8f0f8); font-weight: 500; }
  /* Municipio */
  .ant-mun-wrap { position: relative; }
  .ant-mun-input {
    width: 100%; padding: 10px 14px; border: 1px solid #ccd3de;
    border-radius: 7px; font-size: 16px; box-sizing: border-box;
    outline: none; transition: border .2s; background: #fff;
    text-align: center;
  }
  .ant-mun-input:focus { border-color: #3b7de8; }
  .ant-mun-lista {
    border: 1px solid #ccd3de; border-top: none;
    border-radius: 0 0 7px 7px; max-height: 200px;
    overflow-y: auto; background: white;
    position: absolute; width: 100%; z-index: 1000; display: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  }
  .ant-mun-lista div { padding: 10px 14px; cursor: pointer; font-size: 16px; text-align: center; }
  .ant-mun-lista div:hover, .ant-mun-lista div.activo { background: #e8f0f8; font-weight: 600; }

  /* OCR */
  .ant-ocr-zone {
    border: 2px dashed #3b7de8; border-radius: 10px; padding: 22px;
    text-align: center; background: #f0f6ff; cursor: pointer;
    margin-bottom: 14px; transition: background 0.2s; position: relative;
  }
  .ant-ocr-zone:hover, .ant-ocr-zone.dragover { background: #dceeff; border-color: #1a2340; }
  #ant-ocr-segunda-slot.dragover #ant-ocr-segunda-placeholder { background: #dceeff; border-color: #1a2340; }
  .ant-ocr-zone input[type="file"] { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; z-index: 2; }
  .ant-ocr-icon { font-size: 30px; margin-bottom: 4px; }
  .ant-ocr-texto { font-size: 14px; color: #3b7de8; font-weight: 600; }
  .ant-ocr-sub { font-size: 12px; color: #888; margin-top: 3px; }
  .ant-ocr-preview { max-height: 130px; border-radius: 7px; margin-top: 8px; border: 1px solid #ccd3de; position: relative; z-index: 1; display: block; margin-left: auto; margin-right: auto; }
  .ant-ocr-status { font-size: 26px; line-height: 1.4; margin-top: 8px; padding: 12px 16px; border-radius: 6px; display: none; text-align: center; font-weight: 700; }
  .ant-ocr-status.procesando { background: #fff3cd; color: #856404; }
  .ant-ocr-status.ok  { background: #f0fff6; color: #1a6e3c; }
  .ant-ocr-status.err { background: #fff0f0; color: #c0392b; }

  /* Campos */
  .ant-grid { display: flex; flex-direction: column; margin-bottom: 8px; border: 1px solid #dde3ec; border-radius: 6px; overflow: hidden; }
  .ant-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 14px; }
  .ant-group {
    position: relative; display: flex; align-items: stretch;
    gap: 0; padding: 0; border-bottom: 1px solid #dde3ec; background: #fff;
  }
  .ant-group:nth-child(even) { background: #f7f9fc; }
  /* Regla de "campo vacio en rojo" desactivada a peticion del usuario --
     entraba en conflicto con los colores del RUNT (gravamenes, SOAT, RTM, etc.) */
  .ant-group.ant-campo-vacio { }
  .ant-group:last-child { border-bottom: none; }
  .ant-label {
    flex: 0 0 44%; text-align: left; font-size: 12.5px; font-weight: 700;
    color: #1a2340; text-transform: none; letter-spacing: normal; margin: 0;
    padding: 3px 8px; border-right: 1px solid #dde3ec;
    display: flex; align-items: center;
  }
  .ant-input {
    flex: 1 1 auto; min-width: 0; max-width: 56%; text-align: right;
    padding: 3px 8px; border: none;
    border-radius: 0; font-size: 13.5px; box-sizing: border-box;
    outline: none; transition: background .15s; background: transparent;
  }
  .ant-input:focus { background: #eaf1ff; }
  .ant-input.upper { text-transform: uppercase; }

  /* Botones */
  .ant-btn {
    width: auto; padding: 9px 3px; border: none; border-radius: 7px;
    font-size: 14px; font-weight: 700; cursor: pointer;
    transition: background .2s; display: flex;
    align-items: center; justify-content: center; gap: 8px; margin-top: 12px;
    min-width: 140px; margin-left: auto; margin-right: auto;
  }
  .ant-btn-verde  { background: #1a6e3c; color: #fff; }
  .ant-btn-verde:hover  { background: #2a9e5c; }
  .ant-btn-azul   { background: #1a5fa8; color: #fff; }
  .ant-btn-azul:hover   { background: #2a7fd8; }
  .ant-btn-wa     { background: #25D366; color: #fff; }
  .ant-btn-wa:hover     { background: #1da851; }
  .ant-btn:disabled { background: #9aabc2; cursor: not-allowed; }

  .ant-no-depto { background: #fff3cd; border: 1px solid #ffc107; border-radius: 7px; padding: 10px 14px; color: #856404; font-size: 13px; font-weight: 600; display: none; }

  /* Tramites con autocomplete y X */
  .ant-tramite-bloque { background: #f8fafc; border: 1px solid #e0e7ef; border-radius: 8px; padding: 12px; margin-bottom: 10px; position: relative; }
  .ant-tramite-num { font-size: 11px; font-weight: 700; color: #1a5fa8; text-transform: uppercase; margin-bottom: 7px; display: flex; justify-content: space-between; align-items: center; }
  .ant-tramite-x {
    background: none; border: none; color: #c0392b; font-size: 18px; font-weight: 900;
    cursor: pointer; padding: 0 4px; line-height: 1; display: none;
  }
  .ant-tramite-x:hover { color: #e74c3c; }

  /* Autocomplete tramite */
  .ant-tram-wrap { position: relative; }
  .ant-tram-input {
    width: 100%; padding: 9px 12px; border: 1px solid #ccd3de;
    border-radius: 7px; font-size: 14px; box-sizing: border-box;
    outline: none; background: #fff; transition: border .2s;
  }
  .ant-tram-input:focus { border-color: #3b7de8; }
  .ant-tram-input:disabled { background: #f5f5f5; color: #999; cursor: not-allowed; }
  .ant-tram-lista {
    border: 1px solid #ccd3de; border-top: none;
    border-radius: 0 0 7px 7px; max-height: 180px;
    overflow-y: auto; background: white;
    position: absolute; width: 100%; z-index: 1000; display: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  }
  .ant-tram-lista div { padding: 9px 14px; cursor: pointer; font-size: 13px; }
  .ant-tram-lista div:hover, .ant-tram-lista div.activo { background: #e8f0f8; font-weight: 600; }

  .ant-tarifa-precio-inline {
    display: none; margin-top: 7px; padding: 7px 12px;
    background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 6px;
    font-size: 14px; color: #1a6e3c; font-weight: 700;
  }

  /* Resultados */
  .ant-result { margin-top: 12px; }
  .ant-alert  { padding: 12px 16px; border-radius: 7px; font-size: 14px; margin-bottom: 10px; }
  .ant-alert.error   { background: #fff0f0; border: 1px solid #f5c6c6; color: #c0392b; }
  .ant-alert.success { background: #f0fff6; border: 1px solid #b2e4c8; color: #1a6e3c; }
  .ant-alert.warning { background: #fffaf0; border: 1px solid #f5dba0; color: #7a4a00; }
  .ant-info { display: flex; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
  .ant-info-item label { font-size: 11px; color: #888; display: block; margin-bottom: 2px; }
  .ant-info-item span  { font-size: 13px; font-weight: 600; color: #1a2340; }
  .ant-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .ant-table th { background: #f4f6fb; color: #555; font-weight: 600; padding: 8px 10px; text-align: left; border-bottom: 2px solid #dde3ec; }
  .ant-table td { padding: 8px 10px; border-bottom: 1px solid #eef0f5; color: #333; }
  .ant-table tr:last-child td { border-bottom: none; }
  .ant-total-bar { display: flex; justify-content: space-between; align-items: center; background: #2a7fd8; color: #fff; border-radius: 7px; padding: 12px 16px; margin-top: 12px; }
  .ant-total-bar span:first-child { font-size: 13px; opacity: .85; }
  .ant-total-bar span:last-child  { font-size: 20px; font-weight: 700; }
  .ant-extra { display: flex; justify-content: space-between; padding: 8px 14px; background: #f4f6fb; border-radius: 6px; margin-top: 6px; font-size: 13px; color: #444; }
  .ant-loading { display: flex; align-items: center; gap: 12px; padding: 18px 0; color: #555; font-size: 14px; }
  .ant-spinner-ring {
    width: 28px; height: 28px; flex-shrink: 0;
    background-image: url('tramy-logo-navbar.png');
    background-size: contain; background-repeat: no-repeat; background-position: center;
    animation: ant-pulso 1.1s ease-in-out infinite;
  }
  @keyframes ant-pulso {
    0%, 100% { transform: scale(0.85); opacity: 0.7; }
    50% { transform: scale(1.05); opacity: 1; }
  }
  @keyframes ant-spin { to { transform: rotate(360deg); } }
  .ant-warning { background: #fff3cd; border: 1px solid #ffc107; border-radius: 7px; padding: 10px 14px; color: #856404; font-size: 13px; margin-top: 10px; }

  /* Liquidacion */
  .ant-liq-item { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #eef0f5; }
  .ant-liq-item:last-child { border-bottom: none; }
  .ant-liq-nombre { font-size: 13px; color: #444; font-weight: 600; }
  .ant-liq-input { width: 140px; padding: 7px 10px; border: 1px solid #ccd3de; border-radius: 6px; font-size: 13px; text-align: right; box-sizing: border-box; outline: none; }
  .ant-liq-input:focus { border-color: #3b7de8; }
  .ant-liq-total { background: #2a7fd8; color: #fff; border-radius: 8px; padding: 14px 18px; margin-top: 16px; display: flex; justify-content: space-between; align-items: center; }
  .ant-liq-total span:first-child { font-size: 14px; opacity: .85; }
  .ant-liq-total span:last-child  { font-size: 24px; font-weight: 900; }
  .ant-liq-nota { font-size: 11px; color: #888; margin-top: 8px; text-align: center; }
  .ant-liq-cobro { display: grid; grid-template-columns: 1fr 140px 32px; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #eef0f5; }
  .ant-liq-cobro-nombre { font-size: 13px; color: #444; border: 1px solid #ccd3de; border-radius: 6px; padding: 6px 10px; outline: none; width: 100%; box-sizing: border-box; background: #fff; }
  .ant-liq-cobro-nombre:focus { border-color: #3b7de8; }
  .ant-liq-btn-add { background: #1a5fa8; color: #fff; border: none; border-radius: 6px; width: 32px; height: 32px; font-size: 20px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background .2s; flex-shrink: 0; }
  .ant-liq-btn-add:hover { background: #2a7fd8; }
  .ant-liq-btn-del { background: #c0392b; color: #fff; border: none; border-radius: 6px; width: 32px; height: 32px; font-size: 18px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background .2s; flex-shrink: 0; }
  .ant-liq-btn-del:hover { background: #e74c3c; }
  .ant-wa-preview { margin-top: 12px; border-radius: 8px; overflow: hidden; border: 1px solid #dde3ec; display: none; }
  .ant-wa-preview img { width: 100%; display: block; }

  /* Tooltip ayuda */
  .ant-ayuda-btn { background: none; border: 1.5px solid #fff; color: #fff; border-radius: 50%; width: 18px; height: 18px; font-size: 11px; font-weight: 900; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; margin-left: 6px; flex-shrink: 0; opacity: 0.85; transition: opacity .2s; }
  .ant-ayuda-btn:hover { opacity: 1; }
  .ant-ayuda-panel { display: none; background: #f0f6ff; border: 1px solid #b3d0f5; border-radius: 8px; padding: 12px 14px; margin-top: 10px; font-size: 13px; color: #1a2340; line-height: 1.6; }
  .ant-ayuda-panel ol { margin: 6px 0 0 16px; padding: 0; }
  .ant-ayuda-panel li { margin-bottom: 4px; }

  .ant-progreso-wrap { padding: 14px; background: #f8fafc; border-radius: 8px; border: 1px solid #dde3ec; }
  .ant-progreso-msg { font-size: 14px; color: #1a2340; font-weight: 600; margin-bottom: 10px; line-height: 1.4; }
  .ant-progreso-barra-bg { background: #e0e7ef; border-radius: 10px; height: 10px; overflow: hidden; }
  .ant-progreso-barra { background: linear-gradient(90deg, #1a5fa8, #25a06e); height: 10px; border-radius: 10px; width: 5%; transition: width 0.8s ease; }

  /* Botón nueva liquidación */
  .ant-fab-nuevo {
    position: fixed; bottom: 20px; right: 20px; z-index: 9998;
    width: 56px; height: 56px; border-radius: 50%;
    background: #0047AB; color: #fff; border: none;
    font-size: 32px; font-weight: 300; cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,71,171,0.4);
    display: flex; align-items: center; justify-content: center;
    transition: background .2s, transform .2s;
    line-height: 1;
  }
  .ant-fab-nuevo:hover { background: #1a5fa8; transform: scale(1.08); }

  /* Botón reporte */
  .ant-reporte-btn {
    position: fixed; bottom: 20px; left: 20px; z-index: 9998;
    background: #1a2340; color: #fff; border: none; border-radius: 50px;
    padding: 10px 16px; font-size: 12px; font-weight: 700; cursor: pointer;
    box-shadow: 0 3px 10px rgba(0,0,0,0.2); transition: background .2s;
    display: flex; align-items: center; gap: 6px; font-family: Arial, sans-serif;
  }
  .ant-reporte-btn:hover { background: #2a3a60; }
  .ant-reporte-panel {
    position: fixed; bottom: 70px; left: 20px; z-index: 9997;
    background: #fff; border: 1px solid #dde3ec; border-radius: 12px;
    padding: 18px; width: 280px; box-shadow: 0 6px 24px rgba(0,0,0,0.15);
    display: none; font-family: Arial, sans-serif;
  }
  .ant-reporte-titulo { font-size: 14px; font-weight: 700; color: #1a2340; margin-bottom: 12px; }
  .ant-reporte-opciones { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .ant-reporte-opcion {
    padding: 6px 12px; border: 1px solid #dde3ec; border-radius: 20px;
    font-size: 12px; cursor: pointer; transition: all .2s; color: #444;
    background: #f8fafc;
  }
  .ant-reporte-opcion:hover, .ant-reporte-opcion.sel { background: #1a2340; color: #fff; border-color: #1a2340; }
  .ant-reporte-textarea {
    width: 100%; border: 1px solid #ccd3de; border-radius: 7px;
    padding: 8px 10px; font-size: 12px; resize: none; outline: none;
    box-sizing: border-box; margin-bottom: 10px; font-family: Arial, sans-serif;
  }
  .ant-reporte-textarea:focus { border-color: #3b7de8; }
  .ant-reporte-enviar {
    width: 100%; padding: 9px; background: #1a6e3c; color: #fff;
    border: none; border-radius: 7px; font-size: 13px; font-weight: 700;
    cursor: pointer; transition: background .2s;
  }
  .ant-reporte-enviar:hover { background: #2a9e5c; }
  .ant-reporte-ok { font-size: 13px; color: #1a6e3c; font-weight: 700; text-align: center; display: none; margin-top: 8px; }

  /* Retefuente */
  .ant-ret-opcion {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 14px; border: 1px solid #dde3ec; border-radius: 7px;
    margin-bottom: 8px; cursor: pointer; transition: background .2s;
    font-size: 13px;
  }
  .ant-ret-opcion:hover { background: #f0f6ff; border-color: #3b7de8; }
  .ant-ret-opcion.seleccionada { background: #e8f5e9; border-color: #1a6e3c; }
  .ant-ret-opcion-nombre { color: #1a2340; font-weight: 600; flex: 1; }
  .ant-ret-opcion-valor { color: #1a6e3c; font-weight: 700; text-align: right; min-width: 120px; }

  /* Preview con orientación */
  .ant-preview-wrap { display: none; margin-bottom: 12px; }
  .ant-preview-aviso {
    background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px;
    padding: 10px 14px; font-size: 15px; color: #856404; font-weight: 600;
    margin-bottom: 8px; text-align: center;
  }
  .ant-preview-img-wrap { position: relative; text-align: center; margin-bottom: 8px; }
  .ant-preview-img-wrap img { max-height: 180px; border-radius: 8px; border: 1px solid #ccd3de; transition: transform 0.3s; }
  .ant-btn-girar {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    background: #1a5fa8; color: #fff; border: none; border-radius: 7px;
    padding: 11px 24px; font-size: 15px; font-weight: 700; cursor: pointer;
    margin: 0 auto 10px auto; transition: background .2s;
  }
  .ant-btn-girar:hover { background: #2a7fd8; }
  .ant-btn-continuar {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    background: #1a6e3c; color: #fff; border: none; border-radius: 7px;
    padding: 11px 24px; font-size: 15px; font-weight: 700; cursor: pointer;
    margin: 0 auto; transition: background .2s; width: 100%;
  }
  .ant-btn-continuar:hover { background: #2a9e5c; }
</style>

<div class="ant-app-navbar">
  <span class="ant-app-navbar-titulo" style="display:flex; align-items:center; gap:8px;">
    <img src="tramy-logo-navbar.png" alt="Tramy" style="width:28px; height:28px; object-fit:contain;">
    TRAMY
  </span>
  <div style="display:flex; gap:8px; align-items:center;">
    <a href="login.html" class="ant-app-navbar-salir" id="navAuthLink">Iniciar sesión</a>
    <a href="https://juridicox.com/" class="ant-app-navbar-salir">Salir →</a>
  </div>
</div>

<div class="ant-secciones-nav">
  <a href="index.html" id="tramyTabLiquidacion" class="tramy-seccion-tab activa">LIQUIDACIÓN</a>
  <a href="revision.html" id="tramyTabRevision" class="tramy-seccion-tab" style="display:none;">REVISIÓN</a>
  <a href="ejecucion.html" id="tramyTabEjecucion" class="tramy-seccion-tab" style="display:none;">EJECUCIÓN</a>
  <a href="utilidades.html" id="tramyTabUtilidades" class="tramy-seccion-tab" style="display:none;">UTILIDADES</a>
</div>

<div class="ant-wrap">

  <div id="tramyAvisoCitasEnvigado" style="display:none; background:#dcf5df; border:1.5px solid #8fd6a0; border-radius:8px; padding:12px 14px; margin-bottom:14px; font-size:13.5px; color:#1a5c2e;"></div>

  <!-- SALUDO -->
  <div class="ant-top" id="ant-saludo">
    <div class="ant-bienvenida" id="ant-bienvenida">
      <div style="text-align:center; margin-bottom:6px;">
        <span style="font-size:18px; font-weight:900; color:#0047AB;">Hola, </span><span style="font-size:32px; font-weight:900; color:#0047AB;">soy Tramy</span>
      </div>
      <div style="font-size:16px; color:#1a2340; text-align:center; line-height:1.6; font-family:Arial, sans-serif; font-weight:700;">Hagamos esto juntos.<br>Yo liquido, tú haces la magia.</div>
    </div>
  </div>

  <!-- OCR + Municipio -->
  <div class="ant-top" id="bloque-info-top" style="display:block;">
    <div id="contenido-info-top">

    <!-- Encabezado Paso 1 -->
    <div id="ant-paso1-header" class="ant-bloque-titulo" style="cursor:default;">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto">PASO 1 — INFORMACIÓN</span>
      <span style="display:flex;align-items:center;gap:6px;">
        <button class="ant-ayuda-btn" onclick="event.stopPropagation();antToggleAyuda('ayuda-paso1')" title="Ayuda">?</button>
        <span class="ant-bloque-titulo-chevron" style="opacity:0;">▲</span>
      </span>
    </div>
    <div id="ayuda-paso1" class="ant-ayuda-panel">
      Puedes subir una foto de la tarjeta de propiedad por el lado de en frente, captura del RUNT, foto del formulario, compraventa o cualquier imagen en la que tengas todos o la mayoría de los datos del vehículo. También puedes tomar la foto directamente con la cámara del celular. Ten en cuenta que si faltan datos deberás llenarlos manualmente para poder entregarte toda la información necesaria para tu liquidación.
    </div>

    <!-- Botones de entrada -->
    <div class="ant-entrada-btns">
      <div class="ant-entrada-btn" id="btn-entrada-camara" onclick="antModoEntrada('camara')">
        <span class="ant-entrada-icon">📷</span>
        Tomar foto
      </div>
      <div class="ant-entrada-btn activo" id="btn-entrada-ocr" onclick="antModoEntrada('ocr')">
        <span class="ant-entrada-icon">🖼️</span>
        Subir o arrastrar
      </div>
      <div class="ant-entrada-btn" id="btn-entrada-runt" onclick="antModoEntrada('runt')">
        <span class="ant-entrada-icon">📋</span>
        Pegar datos del RUNT
      </div>
      <div class="ant-entrada-btn" id="btn-entrada-manual" onclick="antModoEntrada('manual')">
        <span class="ant-entrada-icon">✏️</span>
        Ingresar manualmente
      </div>
      <div class="ant-entrada-btn" id="btn-entrada-mis-vehiculos" onclick="tramyAbrirMisVehiculosConsultados()" style="display:none;">
        <span class="ant-entrada-icon">📂</span>
        Mis vehículos consultados
      </div>
    </div>

    <div id="tramyMisVehiculosRuntPanel" style="display:none; margin-top:10px; padding:10px 12px; border-radius:8px; border:1.5px solid #dde3ec; background:#f8fafc;">
      <div style="font-size:12.5px; font-weight:700; color:#5B6472; margin-bottom:8px; text-align:center;">Buscar en tus vehículos consultados</div>
      <div style="position:relative;">
        <input id="tramyMisVehiculosBuscar" type="text" maxlength="7" placeholder="Escribe una placa (ej. ABC123)" autocomplete="off"
          oninput="tramyMisVehiculosFiltrar()"
          style="width:100%; box-sizing:border-box; padding:10px 12px; border:1.5px solid #DAD3C2; border-radius:8px; font-size:14px; text-transform:uppercase;">
        <div id="tramyMisVehiculosRuntLista" style="display:none; position:absolute; top:44px; left:0; right:0; background:#fff; border:1.5px solid #DAD3C2; border-radius:8px; z-index:50; max-height:240px; overflow-y:auto;"></div>
      </div>
    </div>

    <!-- Input cámara (oculto) -->
    <input type="file" id="ant-camara-file" accept="image/*" capture="environment" style="display:none">

    <!-- Zona pegar datos del RUNT -->
    <div id="ant-zona-runt" style="display:none; margin-bottom:14px;">
      <label class="ant-label" style="display:block; margin-bottom:4px;" for="ant-runt-placa">Datos del RUNT por Placa</label>
      <textarea id="ant-runt-placa" rows="5" placeholder="Pega aqui el texto copiado de la consulta del RUNT por placa..." style="
        width:100%; box-sizing:border-box; padding:10px 12px; border:2px solid #d0dce8;
        border-radius:6px; font-size:13px; font-family:inherit; resize:vertical;"></textarea>

      <label class="ant-label" style="display:block; margin:12px 0 4px;" for="ant-runt-cedula">Datos del RUNT por Cedula</label>
      <textarea id="ant-runt-cedula" rows="5" placeholder="Pega aqui el texto copiado de la consulta del RUNT por cedula..." style="
        width:100%; box-sizing:border-box; padding:10px 12px; border:2px solid #d0dce8;
        border-radius:6px; font-size:13px; font-family:inherit; resize:vertical;"></textarea>

      <button class="ant-btn-continuar" style="margin-top:12px;" onclick="antLeerRunt()">Leer datos</button>
      <div class="ant-ocr-status" id="ant-runt-status"></div>
    </div>

    <!-- Zona OCR (subir/arrastrar) -->
    <div id="ant-zona-ocr">
      <div class="ant-ocr-zone" id="ant-ocr-zone">
        <input type="file" id="ant-ocr-file" accept="image/*,application/pdf">
        <div class="ant-ocr-icon">🖼️</div>
        <div class="ant-ocr-texto">Haz clic aqui o arrastra la tarjeta de propiedad</div>
        <div class="ant-ocr-sub">JPG, PNG, WEBP o PDF</div>
      </div>
      <!-- Panel de orientación -->
      <div class="ant-preview-wrap" id="ant-preview-wrap">
        <div style="display:flex; gap:8px; align-items:stretch;">
          <div style="flex:1; min-width:0;">
            <div class="ant-preview-img-wrap" style="height:160px;">
              <img id="ant-ocr-preview" src="" style="width:100%; height:160px; object-fit:contain; display:block; border-radius:7px; background:#f4f6fb;">
              <div id="ant-ocr-preview-pdf" style="display:none; text-align:center; padding:20px 8px; background:#f4f6fb; border-radius:7px; border:1px solid #ccd3de; height:160px; box-sizing:border-box;">
                <div style="font-size:36px;">📄</div>
                <div id="ant-ocr-preview-pdf-nombre" style="font-size:11px; color:#1a2340; font-weight:700; margin-top:6px; word-break:break-all;"></div>
              </div>
            </div>
            <button class="ant-btn-girar" id="ant-btn-girar-primera" style="width:100%; box-sizing:border-box; margin-top:8px;" onclick="antGirarImagen()">↻ Girar Imagen 1</button>
          </div>
          <div style="flex:1; min-width:0;">
            <div id="ant-ocr-segunda-slot" style="position:relative; height:160px;">
              <div id="ant-ocr-segunda-placeholder" onclick="document.getElementById('ant-ocr-file-2').click()" style="
                border:2px dashed #3b7de8; border-radius:7px; cursor:pointer; box-sizing:border-box;
                display:flex; flex-direction:column; align-items:center; justify-content:center;
                height:160px; padding:10px; text-align:center; background:#f0f6ff;">
                <div style="font-size:24px;">➕</div>
                <div style="font-size:12px; color:#3b7de8; font-weight:700; margin-top:4px;">Agregar la otra cara<br>(opcional)</div>
              </div>
              <input type="file" id="ant-ocr-file-2" accept="image/*,application/pdf" style="display:none">
              <img id="ant-ocr-preview-2" src="" onclick="document.getElementById('ant-ocr-file-2').click()" style="display:none; width:100%; height:160px; object-fit:contain; border-radius:7px; border:1px solid #ccd3de; background:#f4f6fb; cursor:pointer;">
              <div id="ant-ocr-preview-pdf-2" onclick="document.getElementById('ant-ocr-file-2').click()" style="display:none; text-align:center; padding:20px 8px; background:#f4f6fb; border-radius:7px; border:1px solid #ccd3de; height:160px; box-sizing:border-box; cursor:pointer;">
                <div style="font-size:36px;">📄</div>
                <div id="ant-ocr-preview-pdf-nombre-2" style="font-size:11px; color:#1a2340; font-weight:700; margin-top:6px; word-break:break-all;"></div>
              </div>
            </div>
            <button class="ant-btn-girar" id="ant-btn-girar-segunda" style="display:none; width:100%; box-sizing:border-box; margin-top:8px;" onclick="antGirarImagen2()">↻ Girar Imagen 2</button>
          </div>
        </div>

        <button onclick="antEliminarImagen()" style="
          display:block; width:100%; box-sizing:border-box; margin-top:10px;
          background:#c0392b; color:#fff; border:none; border-radius:7px;
          padding:11px 16px; font-size:15px; font-weight:700; cursor:pointer;
          transition:background .2s;" onmouseover="this.style.background='#e74c3c'" onmouseout="this.style.background='#c0392b'">
          🗑 Eliminar
        </button>

        <button class="ant-btn-continuar" style="margin-top:10px;" onclick="antContinuarOCR()">Continuar</button>
      </div>
      <div class="ant-ocr-status" id="ant-ocr-status"></div>
    </div>

    <!-- Municipio -->
    </div><!-- fin contenido-info-top -->
  </div><!-- fin bloque-info-top -->


  <!-- BLOQUE 1 — INFORMACION -->
  <div class="ant-card" id="bloque-info">
    <!-- Placa visual -- por encima del encabezado, siempre visible -->
    <div style="margin-bottom:8px; text-align:center;">
      <label class="ant-label" style="text-align:center; display:none;">Placa</label>
      <div style="
        display:inline-block; position:relative; margin-top:4px;
        box-shadow: 3px 3px 10px rgba(0,0,0,0.25); border-radius:6px; overflow:hidden;
      ">
        <!-- Fondo placa colombiana -->
        <div style="
          background:#FDD835; border:3px solid #111;
          border-radius:6px; padding:8px 10px 6px 10px; width:220px;
          position:relative; box-sizing:border-box;
        ">
          <!-- Caracteres + escudo en fila -->
          <div style="display:flex; align-items:center; justify-content:center; gap:0;">

            <!-- Primeras 3 letras -->
            <div id="ant-placa-letras" style="
              font-size:28px; font-weight:900; letter-spacing:4px;
              color:#111; font-family:'Arial Black', Arial, sans-serif;
              min-width:80px; text-align:center;
            ">---</div>

            <!-- Últimos 3 caracteres -->
            <div id="ant-placa-numeros" style="
              font-size:28px; font-weight:900; letter-spacing:4px;
              color:#111; font-family:'Arial Black', Arial, sans-serif;
              min-width:80px; text-align:center;
            ">---</div>
          </div>

          <!-- Input oculto que guarda el valor real -->
          <input id="ant-placa" type="text" maxlength="7"
            style="position:absolute; opacity:0; pointer-events:none; width:1px; height:1px;">

          <!-- Municipio -->
          <div id="ant-placa-municipio" style="
            font-size:10px; font-weight:900; color:#111; text-align:center;
            letter-spacing:2px; margin-top:3px; text-transform:uppercase; min-height:12px;
          "></div>
        </div>


      </div>

    </div>

    <!-- Cabecera con colapso -->
    <div class="ant-bloque-titulo" style="cursor:pointer;" onclick="antToggleInfo()">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto" id="titulo-info">PASO 1 — INFORMACION</span>
      <span id="ant-info-placa-mun" style="font-size:12px; opacity:0.85; margin-left:6px; display:none;"></span>
      <span class="ant-bloque-titulo-chevron" id="ant-info-chevron">▲</span>
    </div>

    <!-- Contenido completo -->
    <div id="ant-info-colapsado" style="display:none;"></div>
    <div id="ant-info-contenido">
      <div id="tramyRuntEstadoInfo" style="display:none; margin-bottom:12px; padding:10px 12px; border-radius:8px; background:#eef2fb; font-size:13px; color:#1a2340; text-align:center; max-width:280px; margin-left:auto; margin-right:auto;"></div>

      <div class="ant-grid">
        <div class="ant-group">
          <label class="ant-label" for="ant-placa-editar">Placa</label>
          <input class="ant-input upper" id="ant-placa-editar" type="text" maxlength="7" placeholder="Ej: ABC123">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-tipodoc">Tipo Documento</label>
          <select class="ant-input" id="ant-tipodoc">
            <option value="CC">C.C. - Cedula de Ciudadania</option>
            <option value="NIT">NIT</option>
            <option value="CE">C.E. - Cedula de Extranjeria</option>
            <option value="TI">T.I. - Tarjeta de Identidad</option>
            <option value="RC">R.C. - Registro Civil</option>
            <option value="PPT">P.P.T. - Permiso por Proteccion Temporal</option>
          </select>
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-cedula">Identificacion</label>
          <input class="ant-input" id="ant-cedula" type="text" inputmode="numeric" placeholder="Ej: 1128402520">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-municipio-input">Municipio</label>
          <div class="ant-mun-wrap" style="flex:1 1 auto; max-width:56%;">
            <input type="text" class="ant-mun-input" id="ant-municipio-input" placeholder="Escribe o selecciona..." autocomplete="off" style="text-align:right; padding:3px 8px; font-size:13.5px; border:none; border-radius:0; background:transparent;">
            <input type="hidden" id="ant-municipio">
            <div class="ant-mun-lista" id="ant-mun-lista"></div>
          </div>
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-apellidos">Nombre</label>
          <input class="ant-input upper" id="ant-apellidos" type="text" placeholder="Ej: LOPEZ AGUDELO">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-clase">Clase de Vehiculo</label>
          <input class="ant-input upper" id="ant-clase" type="text" placeholder="Ej: AUTOMOVIL">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-marca">Marca</label>
          <input class="ant-input upper" id="ant-marca" type="text" placeholder="Ej: CHEVROLET">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-linea">Linea</label>
          <input class="ant-input upper" id="ant-linea" type="text" placeholder="Ej: SPARK">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-modelo">Modelo</label>
          <input class="ant-input" id="ant-modelo" type="text" inputmode="numeric" placeholder="Ej: 2015" maxlength="4">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-cilindrada">Cilindraje (cc)</label>
          <input class="ant-input" id="ant-cilindrada" type="text" placeholder="Ej: 1200">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-servicio">Servicio</label>
          <input class="ant-input upper" id="ant-servicio" type="text" placeholder="Ej: PARTICULAR">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-capacidad">Capacidad Pax Sentados</label>
          <input class="ant-input" id="ant-capacidad" type="text" placeholder="Ej: 5">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-carroceria">Carroceria</label>
          <input class="ant-input upper" id="ant-carroceria" type="text" placeholder="Ej: SEDAN">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-limitacion-propiedad">Gravámenes a la Propiedad</label>
          <select class="ant-input" id="ant-limitacion-propiedad">
            <option value="">Sin información</option>
            <option value="NO">NO</option>
            <option value="SI">SI</option>
          </select>
        </div>

        <!-- Campos adicionales del RUNT -- solo relevantes para Premium -->
        <div id="tramyCamposPremium" style="display:none;">
        <div class="ant-group">
          <label class="ant-label" for="ant-color">Color</label>
          <input class="ant-input upper" id="ant-color" type="text" placeholder="Ej: BLANCO">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-numero_serie">Número de Serie</label>
          <input class="ant-input upper" id="ant-numero_serie" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-numero_motor">Número de Motor</label>
          <input class="ant-input upper" id="ant-numero_motor" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-numero_chasis">Número de Chasis</label>
          <input class="ant-input upper" id="ant-numero_chasis" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-vin">VIN</label>
          <input class="ant-input upper" id="ant-vin" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-combustible">Combustible</label>
          <input class="ant-input upper" id="ant-combustible" type="text" placeholder="Ej: GASOLINA">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-puertas">Puertas</label>
          <input class="ant-input" id="ant-puertas" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-capacidad_carga">Capacidad de Carga</label>
          <input class="ant-input" id="ant-capacidad_carga" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-peso_bruto">Peso Bruto Vehicular</label>
          <input class="ant-input" id="ant-peso_bruto" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-capacidad_pasajeros">Capacidad de Pasajeros</label>
          <input class="ant-input" id="ant-capacidad_pasajeros" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-numero_ejes">Número de Ejes</label>
          <input class="ant-input" id="ant-numero_ejes" type="text">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-estado_vehiculo">Estado del Vehículo</label>
          <input class="ant-input upper" id="ant-estado_vehiculo" type="text" placeholder="Ej: ACTIVO">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-fecha_matricula">Fecha Matrícula Inicial</label>
          <input class="ant-input" id="ant-fecha_matricula" type="text" placeholder="DD/MM/AAAA">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-soat">SOAT</label>
          <input class="ant-input" id="ant-soat" type="text" placeholder="Sin consultar">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-rtm">RTM (Tecnomecánica)</label>
          <input class="ant-input" id="ant-rtm" type="text" placeholder="Sin consultar">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-ultimo-tramite">Último Trámite</label>
          <input class="ant-input" id="ant-ultimo-tramite" type="text" placeholder="Sin consultar">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-fecha-ultimo-traspaso">Fecha Último Traspaso</label>
          <input class="ant-input" id="ant-fecha-ultimo-traspaso" type="text" placeholder="Sin consultar">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-garantia-favor">Garantía a Favor De</label>
          <input class="ant-input" id="ant-garantia-favor" type="text" placeholder="Sin consultar">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-garantia-mobiliaria">Garantía Mobiliaria (Prenda RNGM)</label>
          <input class="ant-input" id="ant-garantia-mobiliaria" type="text" placeholder="Sin consultar">
        </div>
        <div class="ant-group">
          <label class="ant-label" for="ant-limitaciones-propiedad">Limitaciones a la Propiedad</label>
          <input class="ant-input" id="ant-limitaciones-propiedad" type="text" placeholder="Sin consultar">
        </div>
        </div><!-- fin tramyCamposPremium -->
      </div>

      <button class="ant-btn ant-btn-verde" onclick="antConfirmarInfo()" style="margin-top:8px;">
        ✓ He comparado los datos y están bien
      </button>
    </div>
  </div>

  <!-- BLOQUE 2 — IMPUESTO DEPARTAMENTAL -->
  <div class="ant-card" id="bloque-depto">
    <div class="ant-bloque-titulo" style="cursor:pointer;" onclick="antToggleBloque('depto')">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto" id="titulo-depto">PASO 2 — IMPUESTO DEPARTAMENTAL</span>
      <span style="display:flex;align-items:center;gap:6px;">
        <button class="ant-ayuda-btn" onclick="event.stopPropagation();antToggleAyuda('ayuda-depto')" title="Ayuda">?</button>
        <span class="ant-bloque-titulo-chevron" id="chevron-depto">▲</span>
      </span>
    </div>
    <div id="ayuda-depto" class="ant-ayuda-panel">
      Este módulo funciona igual que si consultaras directamente en la página de impuestos departamentales de Antioquia. Si te sale error puede ser por los mismos motivos que si lo hicieras tú mismo en la página oficial:
      <ol>
        <li>La placa ingresada no coincide con la identificación del propietario. Verifica los datos y realiza el proceso nuevamente — este error es el más frecuente y significa que el propietario que aparece en tu tarjeta no es el propietario actual según la base de datos de la Gobernación de Antioquia. Revisa en el RUNT para verificar que ese sí sea el propietario. Si lo es, revisa la tarjeta por el lado de atrás: si hace menos de tres meses le hicieron traspaso, la Gobernación aún no ha actualizado.</li>
        <li>Cualquier otro error será debido a que: la plataforma de impuestos departamentales de Antioquia está caída, la plataforma interna de Tramy está caída, o el vehículo tiene algún dato desactualizado en la base de datos de la Gobernación de Antioquia.</li>
        <li>Si el vehículo está a nombre de persona indeterminada, debes consultar con los datos de la persona indeterminada, los cuales son: cédula <strong>5134</strong>, nombre <strong>PERSONA INDETERMINADA</strong>.</li>
        <li>En los casos en que no es posible obtener el dato por este medio, tampoco es posible obtenerlo por la página oficial de impuestos departamentales. Deberás llamar al <strong>604 444 4666 opción 6</strong>.</li>
      </ol>
    </div>
    <div id="contenido-depto">
    <div id="ant-alerta-traspaso-depto-verde" style="display:none; margin-bottom:8px; padding:10px 12px; border-radius:8px; background:#dcf5df; border:1px solid #8fd6a0; font-size:14px; font-weight:700; color:#1a5c2e; line-height:1.5; text-align:center;"></div>
    <div id="ant-alerta-traspaso-depto" style="display:none; margin-bottom:12px; padding:10px 12px; border-radius:8px; background:#fff3cd; border:1px solid #ffe08a; font-size:13px; color:#5c4813; line-height:1.5;"></div>
    <div class="ant-no-depto" id="ant-no-depto" style="display:none">⚠️ Este vehiculo NO PAGA IMPUESTOS DEPARTAMENTALES</div>
    <button class="ant-btn ant-btn-verde" id="ant-btn-impuesto" style="display:none">🏛️ Consultar</button>
    <div class="ant-result" id="ant-result-depto"></div>
    </div>
  </div>

  <!-- BLOQUE 3 — IMPUESTO MUNICIPAL -->
  <div class="ant-card" id="bloque-municipal">
    <div class="ant-bloque-titulo" style="cursor:pointer;" onclick="antToggleBloque('municipal')">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto" id="titulo-municipal">PASO 3 — IMPUESTO MUNICIPAL</span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span class="ant-bloque-titulo-chevron" id="chevron-municipal">▲</span>
      </span>
    </div>
    <div id="contenido-municipal">
    <button class="ant-btn ant-btn-azul" id="ant-btn-municipal">🏘️ Consultar</button>
    <div class="ant-result" id="ant-result-municipal"></div>
    </div>
  </div>

  <!-- BLOQUE 4 — TRAMITES -->
  <div class="ant-card" id="bloque-tramites">
    <div class="ant-bloque-titulo" style="cursor:pointer;" onclick="antToggleBloque('tramites')">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto" id="titulo-tramites">PASO 4 — TRAMITES</span>
      <span class="ant-bloque-titulo-chevron" id="chevron-tramites">▲</span>
    </div>
    <div id="contenido-tramites">
    <div class="ant-tramite-bloque" id="ant-bloque-1">
      <div class="ant-tramite-num">
        <span>Tramite 1</span>
      </div>
      <div class="ant-tram-wrap">
        <input type="text" class="ant-tram-input" id="ant-tramite-1" placeholder="Escribe para filtrar tramites..." autocomplete="off" disabled>
        <div class="ant-tram-lista" id="ant-tram-lista-1"></div>
      </div>
      <div class="ant-tarifa-precio-inline" id="ant-precio-1"></div>
    </div>
    <div class="ant-tramite-bloque" id="ant-bloque-2" style="display:none">
      <div class="ant-tramite-num">
        <span>Tramite 2</span>
        <button class="ant-tramite-x" id="ant-x-2" onclick="antEliminarTramite(2)" title="Eliminar">✕</button>
      </div>
      <div class="ant-tram-wrap">
        <input type="text" class="ant-tram-input" id="ant-tramite-2" placeholder="Escribe para filtrar tramites..." autocomplete="off" disabled>
        <div class="ant-tram-lista" id="ant-tram-lista-2"></div>
      </div>
      <div class="ant-tarifa-precio-inline" id="ant-precio-2"></div>
    </div>
    <div class="ant-tramite-bloque" id="ant-bloque-3" style="display:none">
      <div class="ant-tramite-num">
        <span>Tramite 3</span>
        <button class="ant-tramite-x" id="ant-x-3" onclick="antEliminarTramite(3)" title="Eliminar">✕</button>
      </div>
      <div class="ant-tram-wrap">
        <input type="text" class="ant-tram-input" id="ant-tramite-3" placeholder="Escribe para filtrar tramites..." autocomplete="off" disabled>
        <div class="ant-tram-lista" id="ant-tram-lista-3"></div>
      </div>
      <div class="ant-tarifa-precio-inline" id="ant-precio-3"></div>
    </div>
    <div class="ant-tramite-bloque" id="ant-bloque-4" style="display:none">
      <div class="ant-tramite-num">
        <span>Tramite 4</span>
        <button class="ant-tramite-x" id="ant-x-4" onclick="antEliminarTramite(4)" title="Eliminar">✕</button>
      </div>
      <div class="ant-tram-wrap">
        <input type="text" class="ant-tram-input" id="ant-tramite-4" placeholder="Escribe para filtrar tramites..." autocomplete="off" disabled>
        <div class="ant-tram-lista" id="ant-tram-lista-4"></div>
      </div>
      <div class="ant-tarifa-precio-inline" id="ant-precio-4"></div>
    </div>
    <div class="ant-tramite-bloque" id="ant-bloque-5" style="display:none">
      <div class="ant-tramite-num">
        <span>Tramite 5</span>
        <button class="ant-tramite-x" id="ant-x-5" onclick="antEliminarTramite(5)" title="Eliminar">✕</button>
      </div>
      <div class="ant-tram-wrap">
        <input type="text" class="ant-tram-input" id="ant-tramite-5" placeholder="Escribe para filtrar tramites..." autocomplete="off" disabled>
        <div class="ant-tram-lista" id="ant-tram-lista-5"></div>
      </div>
      <div class="ant-tarifa-precio-inline" id="ant-precio-5"></div>
    </div>
    </div>
  </div>

  <!-- BLOQUE RETEFUENTE -->
  <div class="ant-card" id="bloque-retefuente" style="display:none;">
    <div class="ant-bloque-titulo" style="cursor:pointer;" onclick="antToggleBloque('ret')">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto" id="titulo-ret">PASO 5 — RETEFUENTE</span>
      <span style="display:flex;align-items:center;gap:6px;">
        <button class="ant-ayuda-btn" onclick="event.stopPropagation();antToggleAyuda('ayuda-ret')" title="Ayuda">?</button>
        <span class="ant-bloque-titulo-chevron" id="chevron-ret">▲</span>
      </span>
    </div>
    <div id="ayuda-ret" class="ant-ayuda-panel">
      Este módulo tiene exactamente los mismos datos del SITBGA. Recuerda que el retefuente obtenido es a modo de guía, ya que es el taquillero que ingresa el trámite quien elige el retefuente a utilizar para la liquidación del mismo. Es por eso que te entrego varias opciones, para que tú determines cuál utilizar dependiendo de las características del vehículo que estás liquidando.
    </div>
    <div id="contenido-ret">
      <div id="ant-ret-datos-veh" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px;">
        <span id="ret-dato-clase" style="background:#e8f0f8; border-radius:20px; padding:4px 12px; font-size:13px; font-weight:700; color:#1a2340;"></span>
        <span id="ret-dato-marca" style="background:#e8f0f8; border-radius:20px; padding:4px 12px; font-size:13px; font-weight:700; color:#1a2340;"></span>
        <span id="ret-dato-linea" style="background:#e8f0f8; border-radius:20px; padding:4px 12px; font-size:13px; font-weight:700; color:#1a2340;"></span>
        <span id="ret-dato-modelo" style="background:#e8f0f8; border-radius:20px; padding:4px 12px; font-size:13px; font-weight:700; color:#1a2340;"></span>
        <span id="ret-dato-cil" style="background:#e8f0f8; border-radius:20px; padding:4px 12px; font-size:13px; font-weight:700; color:#1a2340;"></span>
        <span id="ret-dato-cap" style="background:#e8f0f8; border-radius:20px; padding:4px 12px; font-size:13px; font-weight:700; color:#1a2340;"></span>
      </div>
      <p style="font-size:13px; color:#555; margin:0 0 12px 0;">Elige la opción más acertada con tu vehículo.</p>
      <div id="ant-ret-estado" style="font-size:13px; color:#888; margin-bottom:10px;"></div>
      <div id="ant-ret-opciones"></div>
      <div id="ant-ret-resultado" style="display:none; margin-top:12px;">
        <div style="background:#f0fff6; border:1px solid #b2e4c8; border-radius:7px; padding:14px 16px;">
          <div style="font-size:13px; color:#888; margin-bottom:4px;">Línea seleccionada</div>
          <div id="ant-ret-linea-sel" style="font-size:14px; font-weight:700; color:#1a2340; margin-bottom:10px;"></div>
          <div style="display:flex; gap:20px; flex-wrap:wrap;">
            <div><div style="font-size:11px; color:#888;">Avalúo Comercial</div><div id="ant-ret-avaluo" style="font-size:18px; font-weight:900; color:#1a2340;"></div></div>
            <div><div style="font-size:11px; color:#888;">Retefuente (1%)</div><div id="ant-ret-retefuente" style="font-size:18px; font-weight:900; color:#1a6e3c;"></div></div>
          </div>
          <button class="ant-btn ant-btn-verde" onclick="antUsarRetefuente()" style="margin-top:12px;">
            ✓ Usar este valor en la liquidación
          </button>
        </div>
      </div>
      <p style="font-size:11px; color:#999; margin-top:14px; text-align:center; line-height:1.5;">
        Los datos aquí enlistados provienen del <a href="https://web.mintransporte.gov.co/sibga/" target="_blank" style="color:#1a5fa8;">SIBGA</a>, de las <a href="https://mintransporte.gov.co/publicaciones/12234/base-gravable-2026/" target="_blank" style="color:#1a5fa8;">tablas de avalúos</a> publicadas por el Ministerio de Transporte.
      </p>
    </div>
  </div>

  <!-- BLOQUE 5 — LIQUIDACION -->
  <div class="ant-card-liq" id="bloque-liq" style="display:none">
    <div class="ant-bloque-titulo" style="cursor:pointer;" onclick="antToggleBloque('liq')">
      <span class="ant-bloque-titulo-left" style="opacity:0;">▼</span>
      <span class="ant-bloque-titulo-texto" id="titulo-liq">PASO 6 — LIQUIDACION</span>
      <span class="ant-bloque-titulo-chevron" id="chevron-liq">▲</span>
    </div>
    <div id="contenido-liq">
    <div style="display:flex; justify-content:center; margin-bottom:12px;">
      <div style="display:inline-flex; gap:2px; background:#e4e9f4; border-radius:8px; padding:3px;">
        <button type="button" id="tramyBtnAsesor" onclick="tramySeleccionarTipoCliente('asesor')" style="border:none; padding:7px 16px; border-radius:6px; font-size:12.5px; font-weight:700; cursor:pointer;">Asesor</button>
        <button type="button" id="tramyBtnClienteFinal" onclick="tramySeleccionarTipoCliente('cliente_final')" style="border:none; padding:7px 16px; border-radius:6px; font-size:12.5px; font-weight:700; cursor:pointer;">Cliente Final</button>
      </div>
    </div>
    <div id="liq-row-tramite1" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre" id="liq-label-tramite1">Tramite 1</span><input class="ant-liq-input" id="liq-tramite1" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-tramite2" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre" id="liq-label-tramite2">Tramite 2</span><input class="ant-liq-input" id="liq-tramite2" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-tramite3" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre" id="liq-label-tramite3">Tramite 3</span><input class="ant-liq-input" id="liq-tramite3" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-tramite4" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre" id="liq-label-tramite4">Tramite 4</span><input class="ant-liq-input" id="liq-tramite4" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-tramite5" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre" id="liq-label-tramite5">Tramite 5</span><input class="ant-liq-input" id="liq-tramite5" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-retefuente" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre">Retefuente (1% avaluo)</span><input class="ant-liq-input" id="liq-retefuente" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-depto" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre">Impuesto Departamental</span><input class="ant-liq-input" id="liq-depto" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-municipal" class="ant-liq-item" style="display:none"><span class="ant-liq-nombre">Impuesto Municipal</span><input class="ant-liq-input" id="liq-municipal" type="text" value="0" inputmode="numeric"></div>
    <div id="liq-row-honorarios" class="ant-liq-item" style="display:grid"><span class="ant-liq-nombre">Honorarios</span><div class="ant-honorarios-wrap"><input class="ant-liq-input" id="liq-honorarios" type="text" value="0" inputmode="numeric" autocomplete="off"><div class="ant-chips-wrap" id="ant-honorarios-chips"></div></div></div>
    <div id="liq-row-pazsalvo" class="ant-liq-item" style="display:none; grid-template-columns: 1fr auto auto;"><span class="ant-liq-nombre">Paz y Salvo</span><input class="ant-liq-input" id="liq-pazsalvo" type="text" value="6.000" inputmode="numeric"><button class="ant-liq-btn-del" onclick="antEliminarFila('pazsalvo')" title="Eliminar">×</button></div>
    <div id="liq-row-envios" class="ant-liq-item" style="display:none; grid-template-columns: 1fr auto auto;"><span class="ant-liq-nombre">Envios y/o Domicilios</span><input class="ant-liq-input" id="liq-envios" type="text" value="18.000" inputmode="numeric"><button class="ant-liq-btn-del" onclick="antEliminarFila('envios')" title="Eliminar">×</button></div>
    <!-- Otros Cobros dinámicos -->
    <div id="liq-cobros-wrap">
      <div class="ant-liq-cobro" id="liq-cobro-1">
        <div class="ant-cobro-wrap" id="ant-cobro-wrap-1"><input class="ant-liq-cobro-nombre" id="liq-cobro-nombre-1" type="text" placeholder="Concepto" autocomplete="off"><div class="ant-cobro-lista" id="ant-cobro-lista-1"></div></div>
        <div class="ant-cobro-valor-wrap"><input class="ant-liq-input liq-cobro-valor" id="liq-cobro-valor-1" type="text" value="0" inputmode="numeric"><div class="ant-chips-wrap" id="ant-cobro-chips-1"></div></div>
        <button class="ant-liq-btn-add" onclick="antAgregarCobro()" id="liq-cobro-add-btn" title="Agregar otro cobro">+</button>
      </div>
    </div>

    <div class="ant-liq-total"><span>TOTAL</span><span id="liq-total">$ 0</span></div>
    <p class="ant-liq-nota">Todos los valores son editables. El total se actualiza automaticamente.</p>
    <button class="ant-btn ant-btn-wa" id="ant-btn-wa" onclick="antEnviarWA()">📲 Generar y Enviar por WhatsApp</button>
    <div class="ant-wa-preview" id="ant-wa-preview"><img id="ant-wa-img" src="" alt="Vista previa liquidacion"></div>
    <canvas id="ant-canvas-liq" style="display:none"></canvas>

    <button class="ant-btn" id="ant-btn-fun" onclick="tramyAbrirGenerarFUN()" style="display:none; margin-top:8px; background:#fff; border:1.5px solid #1a2340; color:#1a2340;">📄 Generar FUN (Formulario Único Nacional)</button>
    <div id="tramyFunPanel" style="display:none; margin-top:10px; padding:12px; border-radius:8px; border:1.5px solid #dde3ec; background:#f8fafc; text-align:center;">
      <div id="tramyFunSeleccionTramite">
        <div style="font-size:13px; font-weight:700; color:#1a2340; margin-bottom:8px;">¿Cuál trámite se marca en el formulario?</div>
        <select id="tramyFunTramite" style="width:100%; padding:8px; border-radius:8px; border:1.5px solid #DAD3C2; margin-bottom:8px;">
          <option value="MATRICULA/ REGISTRO">Matrícula / Registro</option>
          <option value="TRASPASO">Traspaso</option>
          <option value="TRASLADO MATRICULA / REGISTRO">Traslado Matrícula / Registro</option>
          <option value="RADICADO  MATRICULA / REGISTRO">Radicado Matrícula / Registro</option>
          <option value="CAMBIO DE COLOR">Cambio de Color</option>
          <option value="CAMBIO DE SERVICIO">Cambio de Servicio</option>
          <option value="REGRABAR MOTOR">Regrabar Motor</option>
          <option value="REGRABAR CHASIS">Regrabar Chasis</option>
          <option value="TRANSFORMACION">Transformación</option>
          <option value="DUPLICADO LICENCIA TRANSITO">Duplicado Licencia Tránsito</option>
          <option value="INSCRIPC. PRENDA">Inscripción de Prenda</option>
          <option value="LEVANTA PRENDA">Levantamiento de Prenda</option>
          <option value="CANCELACION MATRICULA / REGISTRO">Cancelación Matrícula / Registro</option>
          <option value="CAMBIO DE PLACAS">Cambio de Placas</option>
          <option value="DUPLICADO DE PLACAS">Duplicado de Placas</option>
          <option value="REMATRICULA">Rematrícula</option>
          <option value="CAMBIO DE CARROCERIA">Cambio de Carrocería</option>
          <option value="OTROS">Otros</option>
        </select>
        <div id="tramyFunTrasladoWrap" style="display:none; margin-bottom:8px;">
          <input id="tramyFunTrasladoMunicipio" type="text" placeholder="Municipio de destino del traslado" style="width:100%; padding:8px; border-radius:8px; border:1.5px solid #DAD3C2; box-sizing:border-box;">
        </div>
        <button onclick="tramyGenerarFUN()" class="ant-btn ant-btn-verde" style="width:100%;">Generar PDF</button>
      </div>
      <div id="tramyFunResultado" style="display:none; margin-top:10px;"></div>
    </div>
    </div>
  </div>

</div>



<!-- Botón flotante nueva liquidación -->
<button class="ant-fab-nuevo" onclick="antNuevaLiquidacion()" title="Nueva liquidación">+</button>



<!-- Botón flotante de reporte -->
<button class="ant-reporte-btn" onclick="antToggleReporte()" style="left:20px;right:auto;">⚠️ Reportar daños</button>
<div class="ant-reporte-panel" id="ant-reporte-panel" style="left:20px;right:auto;">
  <div class="ant-reporte-titulo">¿Qué está pasando?</div>
  <div class="ant-reporte-opciones">
    <div class="ant-reporte-opcion" onclick="antSelOpcion(this,'Dato incorrecto')">Dato incorrecto</div>
    <div class="ant-reporte-opcion" onclick="antSelOpcion(this,'Precio errado')">Precio errado</div>
    <div class="ant-reporte-opcion" onclick="antSelOpcion(this,'No cargó')">No cargó</div>
    <div class="ant-reporte-opcion" onclick="antSelOpcion(this,'Error en consulta')">Error en consulta</div>
    <div class="ant-reporte-opcion" onclick="antSelOpcion(this,'Otro')">Otro</div>
  </div>
  <textarea class="ant-reporte-textarea" id="ant-reporte-texto" rows="3" placeholder="Cuéntanos más (opcional)..."></textarea>
  <button class="ant-reporte-enviar" onclick="antEnviarReporte()">Enviar reporte</button>
  <div class="ant-reporte-ok" id="ant-reporte-ok">✓ Gracias, lo revisaremos pronto.</div>
</div>

<script>
(function() {
  var ANT_MUNICIPIOS = [
    "ANDES","APARTADO","BARBOSA","BELLO","CALDAS","CAREPA","CHIGORODO",
    "EL CARMEN DE VIBORAL","CAUCASIA","CIUDAD BOLIVAR","COPACABANA","DEPARTAMENTAL",
    "DON MATIAS","ENVIGADO","EL SANTUARIO","FRONTINO","GIRARDOTA","GUARNE","ITAGUI","LA CEJA",
    "LA ESTRELLA","LA UNION","MARINILLA","MEDELLIN","PUERTO BERRIO","RIONEGRO",
    "SABANETA","SANTA FE DE ANTIOQUIA","SANTA ROSA DE OSOS","SONSON","TURBO",
    "URRAO","YARUMAL"
  ];
  window.ANT_MUNICIPIOS = ANT_MUNICIPIOS;

  var MUNICIPIOS_MUNICIPALES = {
    "ENVIGADO":"envigado","SABANETA":"sabaneta","BELLO":"bello",
    "LA ESTRELLA":"la estrella","ITAGUI":"itagui","MEDELLIN":"medellin"
  };

  // Municipios que muestran mensaje de oficina en impuesto municipal
  var MUNICIPIOS_OFICINA_SIEMPRE = ["CALDAS","BARBOSA"];
  var MUNICIPIOS_OFICINA_PUBLICO = ["RIONEGRO","SANTA ROSA DE OSOS","SANTA FE DE ANTIOQUIA"];

  function debeMostrarMensajeOficina() {
    var municipio = antMunicipioActual.toUpperCase();
    var serv      = (document.getElementById('ant-servicio').value || '').trim().toUpperCase();
    if (MUNICIPIOS_OFICINA_SIEMPRE.indexOf(municipio) >= 0) return true;
    if (MUNICIPIOS_OFICINA_PUBLICO.indexOf(municipio) >= 0 && (serv === 'PUBLICO' || serv.normalize('NFD').replace(/[\u0300-\u036f]/g,'') === 'PUBLICO')) return true;
    return false;
  }

  var CLASE_A_TIPO = {
    'AUTOMOVIL':'CARRO','CAMPERO':'CARRO','CAMIONETA':'CARRO','CAMIONETA CARGA':'CARRO','CAMIONETA ESTACAS':'CARRO','VOLQUETA':'CARRO',
    'CAMION':'CARRO','BUS':'CARRO','BUSETA':'CARRO',
    'MOTOCICLETA':'MOTO','MOTO':'MOTO',
    'MOTOCARRO':'MOTOCARRO','TRICIMOTO':'MOTOCARRO'
  };

  var ANT_API           = 'https://consulta-impuestos-production.up.railway.app';
  var antDatosOCR       = null;
  var antIdxActivo      = -1;
  var cacheTramites     = {};
  var antAvaluo         = 0;
  var ocrLeido          = false;
  var modoEntrada       = 'ocr';
  var tramiteOpciones   = [];
  var antMunicipioActual = ''; // municipio seleccionado, guardado en variable JS

  // ── TABLA DE AUTENTICACION POR MUNICIPIO ─────────────────────────────────
  var AUTENTICACION = {
    "MEDELLIN": {
      traspaso:  { propietario: ["mandato"] },
      otro:      { propietario: ["mandato"] }
    },
    "ENVIGADO": {
      traspaso:  { propietario: ["cualquier documento"] },
      otro:      { propietario: ["cualquier documento"] }
    },
    "BELLO": {
      traspaso:  { propietario: ["cualquier documento"] },
      otro:      { propietario: ["cualquier documento"] }
    },
    "ITAGUI": {
      traspaso:  { propietario: ["contrato de compraventa"] },
      otro:      { propietario: ["formulario"] }
    },
    "LA CEJA": {
      traspaso:  { propietario: [], nota_especial: "No requiere autenticación. Revisan firma del propietario en el RUNT." },
      otro:      { propietario: [], nota_especial: "No requiere autenticación. Revisan firma del propietario en el RUNT." }
    },
    "COPACABANA": {
      traspaso:  { propietario: ["mandato", "contrato de compraventa"], comprador: ["mandato"] },
      otro:      { propietario: ["mandato", "formulario"] }
    },
    "DEPARTAMENTAL": {
      traspaso:  { propietario: ["contrato de compraventa"] },
      otro:      { propietario: ["formulario"] }
    },
    "GIRARDOTA": {
      traspaso:  { propietario: ["contrato de compraventa"] },
      otro:      { propietario: ["formulario"] }
    },
    "LA ESTRELLA": {
      traspaso:  { propietario: ["contrato de compraventa"] },
      otro:      { propietario: ["formulario"] }
    },
    "MARINILLA": {
      traspaso:  { propietario: ["mandato"] },
      otro:      { propietario: ["mandato"] }
    },
    "RIONEGRO": {
      traspaso:  { propietario: ["contrato de compraventa"] },
      otro:      { propietario: ["formulario"] }
    },
    "EL SANTUARIO": {
      traspaso:  { propietario: ["contrato de compraventa", "mandato"] },
      otro:      { propietario: ["formulario"] }
    },
    "SABANETA": {
      traspaso:  { propietario: ["contrato de compraventa"] },
      otro:      { propietario: ["formulario"] }
    },
    "SANTA FE DE ANTIOQUIA": {
      traspaso:  { propietario: ["mandato"], nota_especial: "Si la firma es diferente a la cédula, debe autenticar todos los documentos." },
      otro:      { propietario: ["mandato"], nota_especial: "Si la firma es diferente a la cédula, debe autenticar todos los documentos." }
    }
  };

  function generarNotaAutenticacion() {
    var municipio = antMunicipioActual.toUpperCase();
    var reglas    = AUTENTICACION[municipio];
    if (!reglas) return null;

    // Detectar si hay al menos un traspaso entre los tramites seleccionados
    var hayTraspaso = [1,2,3,4,5].some(function(n) {
      var v = (document.getElementById('ant-tramite-'+n).value || '').toUpperCase();
      return v.includes('TRASPASO');
    });

    var regla = hayTraspaso ? reglas.traspaso : reglas.otro;
    if (!regla) return null;

    var lineas = [];

    // Documentos del propietario
    if (regla.propietario && regla.propietario.length > 0) {
      lineas.push('El propietario debe autenticar: ' + regla.propietario.join(' + ').toUpperCase());
    }

    // Documentos del comprador (solo Copacabana traspaso)
    if (regla.comprador && regla.comprador.length > 0) {
      lineas.push('El comprador debe autenticar: ' + regla.comprador.join(' + ').toUpperCase());
    }

    // Nota especial si existe
    if (regla.nota_especial) {
      lineas.push(regla.nota_especial);
    }

    if (lineas.length === 0) return null;
    return 'NOTA (' + antMunicipioActual + '): ' + lineas.join(' | ');
  }

  // ── MODO ENTRADA ─────────────────────────────────────────────────────────

  function actualizarColorPlaca() {
    var serv  = (document.getElementById('ant-servicio').value || '').trim().toUpperCase();
    var placa = document.getElementById('ant-placa-letras').closest('div[style*="background"]');
    if (!placa) return;
    if (serv === 'PUBLICO' || serv.normalize('NFD').replace(/[\u0300-\u036f]/g,'') === 'PUBLICO') {
      placa.style.background = '#FFFFFF';
    } else {
      placa.style.background = '#FDD835';
    }
  }

  window.antModoEntrada = function(modo) {
    modoEntrada = modo;
    // Marcar botón activo
    ['btn-entrada-camara','btn-entrada-ocr','btn-entrada-runt','btn-entrada-manual'].forEach(function(id) {
      document.getElementById(id).classList.remove('activo');
    });
    document.getElementById('btn-entrada-'+modo).classList.add('activo');

    // Mostrar u ocultar zona OCR
    document.getElementById('ant-zona-ocr').style.display = (modo === 'ocr' || modo === 'camara') ? 'block' : 'none';
    document.getElementById('ant-zona-runt').style.display = modo === 'runt' ? 'block' : 'none';

    if (modo === 'ocr') {
      // Mostrar zona de arrastre limpia aunque haya datos previos
      document.getElementById('ant-ocr-zone').style.display = 'block';
      document.getElementById('ant-preview-wrap').style.display = 'none';
      document.getElementById('ant-ocr-status').style.display = 'none';
      // Colapsar todos los bloques
      ocultarTodo();
    } else if (modo === 'camara') {
      // Abrir cámara directamente — zona OCR sigue visible para ver preview
      document.getElementById('ant-ocr-zone').style.display = 'block';
      document.getElementById('ant-preview-wrap').style.display = 'none';
      document.getElementById('ant-camara-file').click();
      // Colapsar todos los bloques
      ocultarTodo();
    } else if (modo === 'runt') {
      ocultarTodo();
      document.getElementById('ant-runt-status').style.display = 'none';
    } else if (modo === 'manual') {
      limpiarCampos();
      ocrLeido = true;
      document.getElementById('ant-bienvenida').style.display = 'none';
      var vp1189 = document.getElementById('tramyVehiculosPanel'); if (vp1189) vp1189.style.display = 'none';
      document.getElementById('ant-zona-ocr').style.display = 'none';
      var elInfoTopManual = document.getElementById('bloque-info-top');
      if (elInfoTopManual) elInfoTopManual.style.display = 'none';
      document.getElementById('bloque-info').classList.add('visible');
      actualizarVisibilidad();
    }
  };

  window.antLeerRunt = function() {
    var textoPlaca  = document.getElementById('ant-runt-placa').value.trim();
    var textoCedula = document.getElementById('ant-runt-cedula').value.trim();
    if (!textoPlaca && !textoCedula) {
      mostrarStatusRunt('err', 'Pega al menos uno de los dos textos.');
      return;
    }
    mostrarStatusRunt('procesando', 'Leyendo datos del RUNT...');
    fetch(ANT_API+'/ocr-runt-texto', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({texto_placa: textoPlaca, texto_cedula: textoCedula})
    })
    .then(function(r){return r.json();})
    .then(function(data) {
      if (data.error) { mostrarStatusRunt('err','Error: '+data.error); return; }
      limpiarCampos();
      var detectados = aplicarDatosLeidos(data);
      if (detectados === 0) {
        mostrarStatusRunt('err', 'No se pudieron detectar datos en el texto pegado.');
      }
    })
    .catch(function(err){ mostrarStatusRunt('err','Error: '+err.message); });
  };

  function mostrarStatusRunt(tipo, msg) {
    var el = document.getElementById('ant-runt-status');
    el.className = 'ant-ocr-status ' + tipo;
    el.textContent = msg;
    el.style.display = 'block';
  }

  // ── LIQUIDACION ──────────────────────────────────────────────────────────

  var LIQ_IDS = ['liq-tramite1','liq-tramite2','liq-tramite3','liq-tramite4','liq-tramite5','liq-retefuente',
                 'liq-depto','liq-municipal','liq-pazsalvo','liq-envios',
                 'liq-honorarios'];
  var antCobroSeq = 1; // contador siempre creciente para IDs únicos

  function parseLiq(id) {
    return parseInt((document.getElementById(id).value||'0').replace(/\D/g,''),10)||0;
  }

  function calcularTotal() {
    var total = LIQ_IDS.reduce(function(s,id){ return s+parseLiq(id); },0);
    // Sumar todos los cobros dinámicos existentes
    document.querySelectorAll('.liq-cobro-valor').forEach(function(el) {
      total += parseInt((el.value||'0').replace(/\D/g,''),10)||0;
    });
    document.getElementById('liq-total').textContent = '$ '+total.toLocaleString('es-CO');
  }

  function getCobrosActuales() {
    return document.querySelectorAll('#liq-cobros-wrap .ant-liq-cobro').length;
  }

  function actualizarBotones() {
    var wrap = document.getElementById('liq-cobros-wrap');
    var cobros = wrap.querySelectorAll('.ant-liq-cobro');
    cobros.forEach(function(cobro, idx) {
      var btn = cobro.querySelector('.ant-liq-btn-add, .ant-liq-btn-del');
      if (!btn) return;
      var esUltimo = idx === cobros.length - 1;
      if (esUltimo && cobros.length < 3) {
        btn.className = 'ant-liq-btn-add';
        btn.textContent = '+';
        btn.title = 'Agregar otro cobro';
        btn.onclick = antAgregarCobro;
      } else {
        btn.className = 'ant-liq-btn-del';
        btn.textContent = '×';
        btn.title = 'Eliminar';
        btn.onclick = (function(c){ return function(){ antEliminarCobro(c); }; })(cobro);
      }
    });
  }

  window.antAgregarCobro = function() {
    if (getCobrosActuales() >= 3) return;
    antCobroSeq++;
    var n = antCobroSeq;
    var wrap = document.getElementById('liq-cobros-wrap');
    var div = document.createElement('div');
    div.className = 'ant-liq-cobro';
    div.id = 'liq-cobro-'+n;
    div.innerHTML =
      '<div class="ant-cobro-wrap" id="ant-cobro-wrap-'+n+'"><input class="ant-liq-cobro-nombre" id="liq-cobro-nombre-'+n+'" type="text" placeholder="Concepto" autocomplete="off"><div class="ant-cobro-lista" id="ant-cobro-lista-'+n+'"></div></div>' +
      '<div class="ant-cobro-valor-wrap"><input class="ant-liq-input liq-cobro-valor" id="liq-cobro-valor-'+n+'" type="text" value="0" inputmode="numeric"><div class="ant-chips-wrap" id="ant-cobro-chips-'+n+'"></div></div>' +
      '<button class="ant-liq-btn-del" title="Eliminar">×</button>';
    wrap.appendChild(div);
    document.getElementById('liq-cobro-valor-'+n).addEventListener('input', calcularTotal);
    antInitCobro(n);
    antInitCobroChips(n);
    actualizarBotones();
  };

  window.antEliminarFila = function(key) {
    var row = document.getElementById('liq-row-' + key);
    if (row) row.style.display = 'none';
    var input = document.getElementById('liq-' + key);
    if (input) input.value = '0';
    calcularTotal();
  };

  window.antEliminarCobro = function(cobro) {
    if (cobro) cobro.remove();
    actualizarBotones();
    calcularTotal();
  };

  function setLiq(id, valor) {
    var el = document.getElementById(id);
    if (el) el.value = Math.round(valor).toLocaleString('es-CO');
    var rowId = 'liq-row-'+id.replace('liq-','');
    var row = document.getElementById(rowId);
    if (row) row.style.display = valor > 0 ? 'grid' : 'none';
    calcularTotal();
  }

  function mostrarFilasDefecto() {
    var municipio  = document.getElementById('ant-municipio').value;
    var tieneDepto = ANT_MUNICIPIOS.indexOf(municipio) >= 0;
    var exentoLiq  = exentoDepto();
    if (tieneDepto && !exentoLiq) {
      document.getElementById('liq-row-pazsalvo').style.display = 'grid';
      document.getElementById('liq-pazsalvo').value = '6.000';
    } else {
      document.getElementById('liq-row-pazsalvo').style.display = 'none';
      document.getElementById('liq-pazsalvo').value = '0';
    }
    document.getElementById('liq-row-envios').style.display = 'grid';
    // Honorarios siempre visible
    document.getElementById('liq-row-honorarios').style.display = 'grid';
    calcularTotal();
    if(typeof window.tramyAjustarFijosPredeterminados === 'function'){
      window.tramyAjustarFijosPredeterminados();
    }
  }

  function limpiarLiq() {
    LIQ_IDS.forEach(function(id) { document.getElementById(id).value = '0'; });
    document.getElementById('liq-pazsalvo').value  = '6.000';
    document.getElementById('liq-envios').value    = '18.000';
    document.getElementById('liq-honorarios').value = window.tramyHonorarioGuardado ? window.tramyHonorarioGuardado() : '0';
    ['tramite1','tramite2','tramite3','retefuente','depto','municipal',
     'pazsalvo','envios'].forEach(function(k) {
      var r = document.getElementById('liq-row-'+k);
      if (r) r.style.display = 'none';
    });
    // Honorarios siempre visible
    document.getElementById('liq-row-honorarios').style.display = 'grid';
    // Resetear cobros dinámicos
    var wrap = document.getElementById('liq-cobros-wrap');
    if (wrap) {
      wrap.innerHTML =
        '<div class="ant-liq-cobro" id="liq-cobro-1">' +
        '<div class="ant-cobro-wrap" id="ant-cobro-wrap-1"><input class="ant-liq-cobro-nombre" id="liq-cobro-nombre-1" type="text" placeholder="Concepto" autocomplete="off"><div class="ant-cobro-lista" id="ant-cobro-lista-1"></div></div>' +
        '<div class="ant-cobro-valor-wrap"><input class="ant-liq-input liq-cobro-valor" id="liq-cobro-valor-1" type="text" value="0" inputmode="numeric"><div class="ant-chips-wrap" id="ant-cobro-chips-1"></div></div>' +
        '<button class="ant-liq-btn-add" id="liq-cobro-add-btn" onclick="antAgregarCobro()" title="Agregar otro cobro">+</button>' +
        '</div>';
      antCobrosCount = 1;
      document.getElementById('liq-cobro-valor-1').addEventListener('input', calcularTotal);
      antInitCobro(1);
      antInitCobroChips(1);
      antCobroSeq = 1;
      actualizarBotones();
    }
    calcularTotal();
    if(typeof window.tramyAplicarConceptosPredeterminados === 'function'){
      window.tramyAplicarConceptosPredeterminados();
      calcularTotal();
    }
  }

  LIQ_IDS.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', calcularTotal);
  });
  // Listener cobro inicial
  var ANT_COBRO_OPCIONES = ['Retefuente','Impuesto Departamental','Impuesto Municipal','Paz y Salvo','Envio / Domicilio','4 X 1.000','Camara Comercio','Copias','Liquidacion de Impuesto','Cupl','Parqueadero','Improntas','Reparacion de Documento'];

  var ANT_COBRO_CHIPS = ['3.000','6.000','11.000','18.000','20.000','25.000','30.000','40.000','50.000'];

  function antInitCobroChips(n) {
    var input = document.getElementById('liq-cobro-valor-'+n);
    var wrap  = document.getElementById('ant-cobro-chips-'+n);
    if (!input || !wrap) return;
    ANT_COBRO_CHIPS.forEach(function(op) {
      var chip = document.createElement('div');
      chip.className = 'ant-chip';
      chip.innerHTML = '$ ' + op + '<span class="ant-chip-check">✓</span>';
      chip.addEventListener('mousedown', function(e) {
        e.preventDefault();
        wrap.querySelectorAll('.ant-chip').forEach(function(c){ c.classList.remove('activo'); });
        chip.classList.add('activo');
        input.value = op;
        wrap.style.display = 'none';
        calcularTotal();
      });
      wrap.appendChild(chip);
    });
    input.addEventListener('focus', function(){ wrap.style.display = 'block'; });
    input.addEventListener('blur', function(){ setTimeout(function(){ wrap.style.display = 'none'; }, 150); });
    input.addEventListener('input', function() {
      wrap.querySelectorAll('.ant-chip').forEach(function(c){ c.classList.remove('activo'); });
      calcularTotal();
    });
  }

  function antInitCobro(n) {
    var input = document.getElementById('liq-cobro-nombre-'+n);
    var lista = document.getElementById('ant-cobro-lista-'+n);
    if (!input || !lista) return;
    var idxActivo = -1;

    function mostrarOpciones(filtro) {
      lista.innerHTML = '';
      idxActivo = -1;
      var items = filtro
        ? ANT_COBRO_OPCIONES.filter(function(o){ return o.toLowerCase().indexOf(filtro.toLowerCase()) >= 0; })
        : ANT_COBRO_OPCIONES;
      if (!items.length) { lista.style.display = 'none'; return; }
      items.forEach(function(op) {
        var div = document.createElement('div');
        div.textContent = op;
        div.addEventListener('mousedown', function(e) {
          e.preventDefault();
          input.value = op;
          lista.style.display = 'none';
        });
        lista.appendChild(div);
      });
      lista.style.display = 'block';
    }

    input.addEventListener('focus', function(){ mostrarOpciones(this.value); });
    input.addEventListener('input', function(){ mostrarOpciones(this.value); });
    input.addEventListener('blur', function(){ setTimeout(function(){ lista.style.display = 'none'; }, 150); });
    input.addEventListener('keydown', function(e) {
      var items = lista.querySelectorAll('div');
      if (!items.length || lista.style.display === 'none') return;
      if (e.key === 'ArrowDown') { idxActivo = Math.min(idxActivo+1, items.length-1); items.forEach(function(el,i){ el.classList.toggle('activo', i===idxActivo); }); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { idxActivo = Math.max(idxActivo-1, 0); items.forEach(function(el,i){ el.classList.toggle('activo', i===idxActivo); }); e.preventDefault(); }
      else if (e.key === 'Enter' && idxActivo >= 0) { input.value = items[idxActivo].textContent; lista.style.display = 'none'; e.preventDefault(); }
      else if (e.key === 'Escape') { lista.style.display = 'none'; }
    });
  }

  antInitCobro(1);
  antInitCobroChips(1);
  actualizarBotones();

  // Chips honorarios
  (function() {
    var opciones = ['40.000','50.000','60.000','65.000','70.000','75.000','80.000','85.000','90.000','100.000','110.000'];
    var input = document.getElementById('liq-honorarios');
    var wrap  = document.getElementById('ant-honorarios-chips');
    if (!input || !wrap) return;
    opciones.forEach(function(op) {
      var chip = document.createElement('div');
      chip.className = 'ant-chip';
      chip.innerHTML = '$ ' + op + '<span class="ant-chip-check">✓</span>';
      chip.addEventListener('mousedown', function(e) {
        e.preventDefault();
        wrap.querySelectorAll('.ant-chip').forEach(function(c){ c.classList.remove('activo'); });
        chip.classList.add('activo');
        input.value = op;
        wrap.style.display = 'none';
        calcularTotal();
      });
      wrap.appendChild(chip);
    });
    input.addEventListener('focus', function(){ wrap.style.display = 'block'; });
    input.addEventListener('blur', function(){ setTimeout(function(){ wrap.style.display = 'none'; }, 150); });
    input.addEventListener('input', function() {
      wrap.querySelectorAll('.ant-chip').forEach(function(c){ c.classList.remove('activo'); });
      calcularTotal();
    });
  })();

  var cobroInicial = document.getElementById('liq-cobro-valor-1');
  if (cobroInicial) cobroInicial.addEventListener('input', calcularTotal);

  // ── EXENCION ─────────────────────────────────────────────────────────────

  function exentoDepto() {
    var serv     = (document.getElementById('ant-servicio').value||'').trim().toUpperCase();
    var cilStr   = (document.getElementById('ant-cilindrada').value||'').trim();
    var cil      = cilStr ? parseInt(cilStr.replace(/\./g, '').replace(/,/g, ''), 10) : 999; // limpiar puntos y comas antes de parsear
    var esPublico = serv === 'PUBLICO' || serv === 'PÚBLICO' || serv.normalize('NFD').replace(/[\u0300-\u036f]/g,'') === 'PUBLICO';
    var esMoto125 = cilStr && cil > 0 && cil <= 125;
    var clase     = (document.getElementById('ant-clase').value||'').trim().toUpperCase();
    // "REMOLQUE" como subcadena tambien cubre "SEMIRREMOLQUE"
    var esMaquinariaORemolque = clase.indexOf('MAQUINARIA') >= 0 || clase.indexOf('REMOLQUE') >= 0;
    return esPublico || esMoto125 || esMaquinariaORemolque;
  }

  // ── VISIBILIDAD DE BLOQUES ────────────────────────────────────────────────

  var infoConfirmada = false;

  function ocultarTodo() {
    ['bloque-tramites','bloque-depto','bloque-municipal'].forEach(function(id) {
      var bl = document.getElementById(id);
      bl.classList.remove('visible');
      bl.style.display = 'none';
    });
    document.getElementById('bloque-info').classList.remove('visible');
    var blLiq = document.getElementById('bloque-liq');
    blLiq.style.cssText = 'display:none !important';
    var blRet = document.getElementById('bloque-retefuente');
    if (blRet) { blRet.style.display = 'none'; blRet.classList.remove('visible'); }
  }

  function mostrarYExpandirBloques() {
    var municipio  = antMunicipioActual.toUpperCase();
    var servicioActual = (document.getElementById('ant-servicio').value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase();
    var esMedellinPublico = (municipio === 'MEDELLIN' && servicioActual === 'PUBLICO');
    var tieneMun = esMedellinPublico ? true : (municipio !== 'MEDELLIN' && !!MUNICIPIOS_MUNICIPALES[municipio]);
    var tieneDepto = ANT_MUNICIPIOS.indexOf(municipio) >= 0;
    var exento     = exentoDepto();
    var tipodoc    = document.getElementById('ant-tipodoc').value;

    // Departamental — visible pero colapsado
    if (tieneDepto && !exento) {
      var blD = document.getElementById('bloque-depto');
      blD.classList.add('visible'); blD.style.display = 'block';
      var cD = document.getElementById('contenido-depto');
      if (cD) cD.style.display = 'none';
      var chD = document.getElementById('chevron-depto');
      if (chD) chD.textContent = '▼';
      document.getElementById('ant-btn-impuesto').style.display = 'flex';
      document.getElementById('ant-no-depto').style.display = 'none';

      // Por defecto se muestra en $0 en la liquidacion, sin necesidad de
      // consultar -- si luego se consulta de verdad, ese resultado
      // reemplaza este valor por defecto (ver setLiq('liq-depto', ...)
      // en las respuestas de la consulta).
      var liqRowDeptoDefault = document.getElementById('liq-row-depto');
      if (liqRowDeptoDefault) {
        setLiq('liq-depto', 0);
        liqRowDeptoDefault.style.display = 'grid';
        var lblDDefault = document.querySelector('#liq-row-depto .ant-liq-nombre');
        if (lblDDefault) lblDDefault.textContent = 'Impuesto Departamental';
      }
    }

    // Municipal — visible pero colapsado
    if (tieneMun || debeMostrarMensajeOficina()) {
      var blM = document.getElementById('bloque-municipal');
      blM.classList.add('visible'); blM.style.display = 'block';
      var cM = document.getElementById('contenido-municipal');
      if (cM) cM.style.display = 'none';
      var chM = document.getElementById('chevron-municipal');
      if (chM) chM.textContent = '▼';

      // Por defecto se muestra en $0 en la liquidacion, sin necesidad de
      // consultar (excepto en el caso de "pregunta en la oficina", donde
      // realmente no se sabe el estado y no corresponde asumir nada).
      if (tieneMun && !debeMostrarMensajeOficina()) {
        var liqRowMunDefault = document.getElementById('liq-row-municipal');
        if (liqRowMunDefault) {
          setLiq('liq-municipal', 0);
          liqRowMunDefault.style.display = 'grid';
          var lblMDefault = document.querySelector('#liq-row-municipal .ant-liq-nombre');
          if (lblMDefault) lblMDefault.textContent = 'Impuesto Municipal';
        }
      }

      if (debeMostrarMensajeOficina()) {
        document.getElementById('ant-btn-municipal').style.display = 'none';
        document.getElementById('ant-result-municipal').innerHTML =
          '<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:7px;padding:14px 16px;color:#856404;font-size:14px;font-weight:700;text-align:center;margin-top:8px;">⚠️ DEBES PREGUNTAR DIRECTAMENTE EN LA OFICINA DE MOVILIDAD</div>';
      } else if (window._tramyMunicipioAlDiaPorTramite) {
        // Cualquier tramite reciente (excepto RTM/SOAT/certificado de
        // tradicion) hecho este mismo año ya implica que el vehiculo
        // estaba a paz y salvo del impuesto municipal para poder
        // realizarlo. No hace falta consultar ni mostrar el boton -- pero
        // igual se deja la fila en la liquidacion en $0, para que quede
        // constancia de que se reviso y esta al dia (evita que el
        // cliente pregunte).
        document.getElementById('ant-btn-municipal').style.display = 'none';
        document.getElementById('ant-result-municipal').innerHTML =
          '<div style="background:#dcf5df;border:1px solid #8fd6a0;border-radius:7px;padding:14px 16px;color:#1a5c2e;font-size:14px;font-weight:700;text-align:center;margin-top:8px;">✓ El impuesto municipal está al día.<br>Último trámite realizado el día ' + window._tramyMunicipioAlDiaFechaTexto + '</div>';
        setLiq('liq-municipal', 0);
        document.getElementById('liq-row-municipal').style.display = 'grid';
        var lblMAlDia = document.querySelector('#liq-row-municipal .ant-liq-nombre');
        if (lblMAlDia) lblMAlDia.textContent = 'Impuesto Municipal';
      } else {
        document.getElementById('ant-btn-municipal').style.display = 'flex';
        document.getElementById('ant-result-municipal').innerHTML = '';
      }
    }

    // Tramites — visible pero colapsado
    var blT = document.getElementById('bloque-tramites');
    blT.classList.add('visible'); blT.style.display = 'block';
    var cT = document.getElementById('contenido-tramites');
    if (cT) cT.style.display = 'none';
    var chT = document.getElementById('chevron-tramites');
    if (chT) chT.textContent = '▼';

    // Liquidacion — visible pero colapsada
    var blL = document.getElementById('bloque-liq');
    blL.style.cssText = 'display:block !important';
    var cL = document.getElementById('contenido-liq');
    if (cL) cL.style.display = 'none';
    var chL = document.getElementById('chevron-liq');
    if (chL) chL.textContent = '▼';

    // WhatsApp — visible pero colapsado
    var blWA = document.getElementById('bloque-wa');
    if (blWA) { blWA.classList.add('visible'); blWA.style.display = 'block'; }
    var cWA = document.getElementById('contenido-wa');
    if (cWA) cWA.style.display = 'none';
    var chWA = document.getElementById('chevron-wa');
    if (chWA) chWA.textContent = '▼';

    // Retefuente — visible pero colapsado (solo si no es NIT)
    if (tipodoc !== 'NIT') {
      var blR = document.getElementById('bloque-retefuente');
      blR.classList.add('visible'); blR.style.display = 'block';
      var cR = document.getElementById('contenido-ret');
      if (cR) cR.style.display = 'none';
      var chR = document.getElementById('chevron-ret');
      if (chR) chR.textContent = '▼';
      antCargarRetefuente();
    }
  }

  function actualizarVisibilidad() {
    if (!ocrLeido) {
      ocultarTodo();
      return;
    }

    // Paso 2: mostrar solo informacion expandida
    if (!infoConfirmada) {
      ocultarTodo();
      document.getElementById('bloque-info').classList.add('visible');
      document.getElementById('ant-info-contenido').style.display = 'block';
      document.getElementById('ant-info-colapsado').style.display = 'none';
      document.getElementById('ant-info-chevron').textContent = '▲';
    }
    // Si ya confirmó, no hacer nada — antConfirmarInfo maneja el siguiente paso
  }

  // ── LIMPIEZA ─────────────────────────────────────────────────────────────

  function limpiarCampos() {
    ['ant-placa','ant-placa-edit','ant-modelo','ant-cedula','ant-apellidos',
     'ant-clase','ant-servicio','ant-cilindrada','ant-carroceria'].forEach(function(id) {
      var el = document.getElementById(id); if(el) el.value = '';
    });
    document.getElementById('ant-limitacion-propiedad').value = '';
    document.getElementById('ant-placa-letras').textContent  = '---';
    document.getElementById('ant-placa-numeros').textContent = '---';
    var pe3 = document.getElementById('ant-placa-editar');
    if (pe3) pe3.value = '';
    actualizarColorPlaca();
    ['ant-marca','ant-linea','ant-capacidad'].forEach(function(id) {
      document.getElementById(id).value = '';
    });
    document.getElementById('ant-tipodoc').value         = 'CC';
    document.getElementById('ant-municipio-input').value = '';
    document.getElementById('ant-municipio').value       = '';
    document.getElementById('ant-result-depto').innerHTML    = '';
    document.getElementById('ant-result-municipal').innerHTML = '';
    document.getElementById('ant-preview-wrap').style.display = 'none';
    document.getElementById('ant-ocr-zone').style.display    = 'block';
    document.getElementById('ant-ocr-status').style.display  = 'none';
    if (window.antEliminarSegunda) window.antEliminarSegunda();
    document.getElementById('ant-wa-preview').style.display  = 'none';
    ['bloque-info','bloque-tramites','bloque-depto','bloque-municipal'].forEach(function(id) {
      document.getElementById(id).classList.remove('visible');
    });
    antDatosOCR = null; antAvaluo = 0; ocrLeido = false; infoConfirmada = false; antMunicipioActual = '';
    antRetAvaluo = 0; antRetRetefuente = 0;
    document.getElementById('ant-ret-estado').textContent   = '';
    document.getElementById('ant-ret-opciones').innerHTML   = '';
    document.getElementById('ant-ret-resultado').style.display = 'none';
    var blRet = document.getElementById('bloque-retefuente');
    if (blRet) { blRet.style.display = 'none'; blRet.classList.remove('visible'); }
    document.getElementById('ant-bienvenida').style.display     = 'block';
    if (window.tramyVehiculosGuardados && window.tramyVehiculosGuardados.length) { var vp2 = document.getElementById('tramyVehiculosPanel'); if (vp2) vp2.style.display = 'block'; }
    document.getElementById('bloque-liq').style.display         = 'none';
    limpiarTramites();
    limpiarLiq();
  }

  // ── TRAMITES CON AUTOCOMPLETE ─────────────────────────────────────────────

  function getTipo() {
    var clase = (document.getElementById('ant-clase').value||'').trim().toUpperCase();
    if (CLASE_A_TIPO[clase]) return CLASE_A_TIPO[clase];
    // Coincidencia flexible: el valor real puede traer texto adicional
    // (ej. "CAMIONETA WAGON" en vez de solo "CAMIONETA", como suele pasar
    // en las Declaraciones Sugeridas de la Gobernacion) -- se busca que
    // la clase EMPIECE con alguna de las claves conocidas, probando
    // primero las mas largas para no confundir "CAMIONETA" con
    // "CAMIONETA CARGA"/"CAMIONETA ESTACAS".
    var claves = Object.keys(CLASE_A_TIPO).sort(function(a,b){ return b.length - a.length; });
    for (var i = 0; i < claves.length; i++) {
      if (clase.indexOf(claves[i]) === 0) return CLASE_A_TIPO[claves[i]];
    }
    return '';
  }

  function limpiarTramites() {
    [1,2,3,4,5].forEach(function(n) {
      var inp = document.getElementById('ant-tramite-'+n);
      inp.value    = '';
      inp.disabled = true;
      document.getElementById('ant-tram-lista-'+n).style.display = 'none';
      document.getElementById('ant-precio-'+n).style.display     = 'none';
      if (n > 1) document.getElementById('ant-bloque-'+n).style.display = 'none';
    });
    tramiteOpciones = [];
  }

  function cargarTramites() {
    var municipio = document.getElementById('ant-municipio').value;
    var tipo      = getTipo();
    if(typeof window.tramyAplicarHonorarioGuardado === 'function') window.tramyAplicarHonorarioGuardado();
    if (!municipio || !tipo) { limpiarTramites(); return; }
    var key = municipio+'|'+tipo;
    if (cacheTramites[key]) {
      tramiteOpciones = cacheTramites[key];
      habilitarTramite(1);
      autoSeleccionarLevantamientoPrenda();
      autoSeleccionarTraspasoPropiedad();
      return;
    }
    fetch(ANT_API+'/tramites/filtros?campo=tramite&municipio='+encodeURIComponent(municipio)+'&clase='+encodeURIComponent(tipo))
      .then(function(r){return r.json();})
      .then(function(data){
        cacheTramites[key] = data.valores||[];
        tramiteOpciones    = cacheTramites[key];
        habilitarTramite(1);
        autoSeleccionarLevantamientoPrenda();
        autoSeleccionarTraspasoPropiedad();
      })
      .catch(function(){});
  }

  // Precarga el tramite "TRASPASO DE PROPIEDAD" por defecto (para Free y
  // Premium por igual), a menos que el usuario haya apagado esta opcion
  // desde su panel de configuracion.
  function autoSeleccionarTraspasoPropiedad() {
    var settings = (window.tramyProfile && window.tramyProfile.settings) || {};
    var precargarActivo = settings.tramite_precargado_traspaso !== false; // activo por defecto
    if (!precargarActivo) return;

    // ¿Ya esta seleccionado en algun slot?
    for (var i = 1; i <= 5; i++) {
      var elT = document.getElementById('ant-tramite-'+i);
      if (elT && (elT.value||'').toUpperCase().includes('TRASPASO DE PROPIEDAD')) return;
    }
    var match = (tramiteOpciones||[]).find(function(t){
      return t.toUpperCase().includes('TRASPASO DE PROPIEDAD');
    });
    if (!match) return;
    for (var n = 1; n <= 5; n++) {
      var inp = document.getElementById('ant-tramite-'+n);
      if (inp && !inp.disabled && !inp.value) {
        seleccionarTramite(n, match);
        return;
      }
    }
  }

  // Si el vehiculo tiene gravamenes (prenda), agrega automaticamente el
  // tramite "LEVANTAMIENTO DE PRENDA" en el primer slot vacio disponible.
  function autoSeleccionarLevantamientoPrenda() {
    var elGrav = document.getElementById('ant-limitacion-propiedad');
    if (!elGrav || elGrav.value !== 'SI') return;
    // ¿Ya esta seleccionado en algun slot?
    for (var i = 1; i <= 5; i++) {
      var elT = document.getElementById('ant-tramite-'+i);
      if (elT && (elT.value||'').toUpperCase().includes('LEVANTAMIENTO DE PRENDA')) return;
    }
    // Buscar la opcion real disponible para este municipio/clase
    var match = (tramiteOpciones||[]).find(function(t){
      return t.toUpperCase().includes('LEVANTAMIENTO DE PRENDA');
    });
    if (!match) return;
    // Colocar en el primer slot vacio
    for (var n = 1; n <= 5; n++) {
      var inp = document.getElementById('ant-tramite-'+n);
      if (inp && !inp.disabled && !inp.value) {
        seleccionarTramite(n, match);
        return;
      }
    }
  }

  function habilitarTramite(n) {
    var inp = document.getElementById('ant-tramite-'+n);
    if (inp) inp.disabled = false;
  }

  function filtrarTramites(n, texto) {
    var lista = document.getElementById('ant-tram-lista-'+n);
    var filtro = texto.trim().toUpperCase();
    var items  = filtro
      ? tramiteOpciones.filter(function(t){ return t.toUpperCase().includes(filtro); })
      : tramiteOpciones;
    lista.innerHTML = '';
    if (!items.length) { lista.style.display='none'; return; }
    items.forEach(function(t) {
      var div = document.createElement('div');
      div.textContent = t;
      div.addEventListener('mousedown', function(e){
        e.preventDefault();
        seleccionarTramite(n, t);
      });
      lista.appendChild(div);
    });
    lista.style.display = 'block';
  }

  function seleccionarTramite(n, valor) {
    document.getElementById('ant-tramite-'+n).value = valor;
    document.getElementById('ant-tram-lista-'+n).style.display = 'none';
    // Mostrar X en tramites 2 y 3
    var xBtn = document.getElementById('ant-x-'+n);
    if (xBtn) xBtn.style.display = 'inline-block';
    consultarTarifaN(n);
  }

  window.antEliminarTramite = function(n) {
    document.getElementById('ant-tramite-'+n).value = '';
    document.getElementById('ant-precio-'+n).style.display = 'none';
    document.getElementById('ant-bloque-'+n).style.display = 'none';
    var xBtn = document.getElementById('ant-x-'+n);
    if (xBtn) xBtn.style.display = 'none';
    setLiq('liq-tramite'+n, 0);
    document.getElementById('liq-row-tramite'+n).style.display = 'none';
    // Si elimina uno, también oculta los siguientes
    for (var i = n + 1; i <= 5; i++) {
      var elB = document.getElementById('ant-bloque-'+i);
      var elT = document.getElementById('ant-tramite-'+i);
      var elP = document.getElementById('ant-precio-'+i);
      var elR = document.getElementById('liq-row-tramite'+i);
      if (elT) elT.value = '';
      if (elP) elP.style.display = 'none';
      if (elB) elB.style.display = 'none';
      setLiq('liq-tramite'+i, 0);
      if (elR) elR.style.display = 'none';
    }
    actualizarLiqTramites();
    calcularTotal();
  };

  function iniciarAutocomplete(n) {
    var inp   = document.getElementById('ant-tramite-'+n);
    var lista = document.getElementById('ant-tram-lista-'+n);
    var idxAct = -1;

    inp.addEventListener('focus', function(){ filtrarTramites(n, this.value); });
    inp.addEventListener('input', function(){
      filtrarTramites(n, this.value);
      // Limpiar precio si cambia el texto
      document.getElementById('ant-precio-'+n).style.display = 'none';
      setLiq('liq-tramite'+n, 0);
      actualizarLiqTramites();
    });
    inp.addEventListener('keydown', function(e) {
      var items = lista.querySelectorAll('div');
      if (!items.length) return;
      if (e.key==='ArrowDown') { idxAct=Math.min(idxAct+1,items.length-1); items.forEach(function(el,i){el.classList.toggle('activo',i===idxAct);}); e.preventDefault(); }
      else if (e.key==='ArrowUp') { idxAct=Math.max(idxAct-1,0); items.forEach(function(el,i){el.classList.toggle('activo',i===idxAct);}); e.preventDefault(); }
      else if (e.key==='Enter'&&idxAct>=0) { seleccionarTramite(n, items[idxAct].textContent); idxAct=-1; e.preventDefault(); }
      else if (e.key==='Escape') { lista.style.display='none'; }
    });
    inp.addEventListener('blur', function(){
      setTimeout(function(){ lista.style.display='none'; }, 150);
    });
  }

  function mostrarSiguiente(n) {
    if (n < 5) {
      var tramite = document.getElementById('ant-tramite-'+n).value.trim();
      if (tramite) {
        var sig = document.getElementById('ant-bloque-'+(n+1));
        if (sig) {
          sig.style.display = 'block';
          habilitarTramite(n+1);
        }
      }
    }
  }

  function hayTraspaso() {
    return [1,2,3,4,5].some(function(n) {
      return (document.getElementById('ant-tramite-'+n).value||'').toUpperCase().includes('TRASPASO');
    });
  }

  function esEmpresa() {
    // Las empresas (NIT) no pagan retefuente
    return (document.getElementById('ant-tipodoc').value||'') === 'NIT';
  }

  function actualizarLiqTramites() {
    [1,2,3,4,5].forEach(function(n) {
      var tramite = document.getElementById('ant-tramite-'+n).value;
      var row     = document.getElementById('liq-row-tramite'+n);
      var label   = document.getElementById('liq-label-tramite'+n);
      if (tramite && parseLiq('liq-tramite'+n) > 0) {
        label.textContent = tramite.length > 38 ? tramite.substring(0,36)+'...' : tramite;
        row.style.display = 'grid';
      } else {
        row.style.display = 'none';
      }
    });
    // Retefuente: visible si hay traspaso Y hay avaluo
    var refRow = document.getElementById('liq-row-retefuente');
    if (hayTraspaso() && antAvaluo > 0 && !esEmpresa()) {
      setLiq('liq-retefuente', Math.round(antAvaluo / 100));
      refRow.style.display = 'grid';
    } else {
      refRow.style.display = 'none';
    }
    calcularTotal();
  }

  function consultarTarifaN(n) {
    var municipio = document.getElementById('ant-municipio').value;
    var tipo      = getTipo();
    var tramite   = document.getElementById('ant-tramite-'+n).value.trim();
    var precioDiv = document.getElementById('ant-precio-'+n);
    precioDiv.style.display = 'none';
    setLiq('liq-tramite'+n, 0);
    mostrarSiguiente(n);
    actualizarLiqTramites();
    if (!tramite || !municipio || !tipo) return;
    fetch(ANT_API+'/tramites/precio?municipio='+encodeURIComponent(municipio)
      +'&clase='+encodeURIComponent(tipo)
      +'&tramite='+encodeURIComponent(tramite)
      +'&departamento=ANTIOQUIA')
      .then(function(r){return r.json();})
      .then(function(data){
        if (data.precio) {
          precioDiv.textContent = '$ '+data.precio.toLocaleString('es-CO');
          precioDiv.style.display = 'block';
          setLiq('liq-tramite'+n, data.precio);
          actualizarLiqTramites();
        }
      }).catch(function(){});
  }

  // ── INIT ─────────────────────────────────────────────────────────────────

  window.addEventListener('load', function() {

    ['ant-cedula','ant-modelo'].forEach(function(id) {
      document.getElementById(id).addEventListener('input', function() {
        this.value = this.value.replace(/[^0-9]/g,'');
      });
    });

    // Sincronizar input placa con visualización (ant-placa-edit legacy)
    var placaEdit = document.getElementById('ant-placa-edit');
    var placaHidden = document.getElementById('ant-placa');
    if (placaEdit) {
      placaEdit.addEventListener('input', function() {
        var val = this.value.toUpperCase().replace(/[^A-Z0-9]/g,'');
        this.value = val;
        placaHidden.value = val;
        document.getElementById('ant-placa-letras').textContent  = val.substring(0,3) || '---';
        document.getElementById('ant-placa-numeros').textContent = val.substring(3)   || '---';
      });
    }

    // Input editable de placa (nuevo)
    var placaEditarEl = document.getElementById('ant-placa-editar');
    if (placaEditarEl) {
      placaEditarEl.addEventListener('input', function() {
        var val = this.value.toUpperCase().replace(/[^A-Z0-9]/g,'');
        this.value = val;
        document.getElementById('ant-placa').value = val;
        document.getElementById('ant-placa-letras').textContent  = val.substring(0,3) || '---';
        document.getElementById('ant-placa-numeros').textContent = val.substring(3)   || '---';
      });
    }

    ['ant-servicio','ant-cilindrada','ant-clase'].forEach(function(id) {
      document.getElementById(id).addEventListener('input', function() {
        actualizarVisibilidad(); cargarTramites();
        actualizarColorPlaca();
      });
    });

    document.getElementById('ant-tipodoc').addEventListener('change', function() {
      actualizarReglasDocumento();
    });

    document.querySelector('.ant-grid').addEventListener('input', function(e){
      if (CAMPOS_A_VALIDAR.indexOf(e.target.id) === -1) return;
      var fila = e.target.closest('.ant-group');
      if (!fila) return;
      if (e.target.value && e.target.value.trim()) fila.classList.remove('ant-campo-vacio');
      else fila.classList.add('ant-campo-vacio');
    });

    document.getElementById('ant-limitacion-propiedad').addEventListener('change', function() {
      if (this.value === 'SI') {
        cargarTramites(); // internamente llama autoSeleccionarLevantamientoPrenda() tras cargar opciones
      }
      var filaGrav = this.closest('.ant-group');
      if (filaGrav) {
        if (this.value) filaGrav.classList.remove('ant-campo-vacio');
        else filaGrav.classList.add('ant-campo-vacio');
      }
    });

    function actualizarReglasDocumento() {
      var tipodoc = document.getElementById('ant-tipodoc').value;
      var rowRet  = document.getElementById('liq-row-retefuente');
      var blRet   = document.getElementById('bloque-retefuente');
      if (tipodoc === 'NIT') {
        // NIT no paga retefuente — ocultar fila en liquidacion y modulo,
        // y poner el valor en 0 para que no quede sumado invisiblemente al total
        if (rowRet) rowRet.style.display = 'none';
        setLiq('liq-retefuente', 0);
        if (blRet) { blRet.style.display = 'none'; blRet.classList.remove('visible'); }
      } else {
        // Todos los demas si pagan retefuente
        if (blRet && infoConfirmada) {
          blRet.style.display = 'block'; blRet.classList.add('visible');
        }
      }
      calcularTotal();
    }

    // Iniciar autocomplete para los 3 tramites
    [1,2,3,4,5].forEach(function(n){ iniciarAutocomplete(n); });

    LIQ_IDS.forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('input', calcularTotal);
    });

    // Municipio autocomplete
    var inputMun  = document.getElementById('ant-municipio-input');
    var hiddenMun = document.getElementById('ant-municipio');
    var listaMun  = document.getElementById('ant-mun-lista');

    function mostrarOpciones(filtro) {
      var items = filtro
        ? ANT_MUNICIPIOS.filter(function(m){ return m.includes(filtro.toUpperCase()); })
        : ANT_MUNICIPIOS;
      listaMun.innerHTML = '';
      antIdxActivo = -1;
      if (!items.length) { listaMun.style.display='none'; return; }
      items.forEach(function(m) {
        var div = document.createElement('div');
        div.textContent = m;
        div.addEventListener('mousedown', function(e){ e.preventDefault(); selMunicipio(m); });
        listaMun.appendChild(div);
      });
      listaMun.style.display = 'block';
    }

    function selMunicipio(valor) {
      inputMun.value     = valor;
      hiddenMun.value    = valor;
      antMunicipioActual = valor;
      var placaMun = document.getElementById('ant-placa-municipio');
      if (placaMun) placaMun.textContent = valor;
      listaMun.style.display = 'none';
      actualizarVisibilidad();
      cargarTramites();
      var placa = document.getElementById('ant-placa').value.trim().toUpperCase();
      if (placa && valor) {
        fetch(ANT_API+'/ocr-guardar-municipio', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({placa: placa, municipio: valor})
        }).catch(function(){});
      }
      mostrarFilasDefecto();
      marcarCamposVacios();
      if(typeof window.tramyVerificarDisponibilidadRunt === 'function') window.tramyVerificarDisponibilidadRunt();
    }
    window.selMunicipio = selMunicipio;

    inputMun.addEventListener('focus', function(){ mostrarOpciones(this.value); });
    inputMun.addEventListener('input', function(){
      hiddenMun.value=''; actualizarVisibilidad(); mostrarOpciones(this.value);
      var placaMunLive = document.getElementById('ant-placa-municipio');
      if (placaMunLive) placaMunLive.textContent = this.value.toUpperCase();
    });
    inputMun.addEventListener('keydown', function(e) {
      var items = listaMun.querySelectorAll('div');
      if (!items.length) return;
      if (e.key==='ArrowDown') { antIdxActivo=Math.min(antIdxActivo+1,items.length-1); items.forEach(function(el,i){el.classList.toggle('activo',i===antIdxActivo);}); e.preventDefault(); }
      else if (e.key==='ArrowUp') { antIdxActivo=Math.max(antIdxActivo-1,0); items.forEach(function(el,i){el.classList.toggle('activo',i===antIdxActivo);}); e.preventDefault(); }
      else if (e.key==='Enter'&&antIdxActivo>=0) { selMunicipio(items[antIdxActivo].textContent); e.preventDefault(); }
      else if (e.key==='Escape') { listaMun.style.display='none'; }
    });
    inputMun.addEventListener('blur', function() {
      setTimeout(function(){ listaMun.style.display='none'; },150);
      var val = inputMun.value.toUpperCase();
      if (ANT_MUNICIPIOS.includes(val)) { inputMun.value=val; hiddenMun.value=val; actualizarVisibilidad(); }
      else { hiddenMun.value=''; actualizarVisibilidad(); }
    });
    document.addEventListener('click', function(e){ if(e.target!==inputMun) listaMun.style.display='none'; });

    // OCR
    var zona    = document.getElementById('ant-ocr-zone');
    var fileIn  = document.getElementById('ant-ocr-file');
    var preview = document.getElementById('ant-ocr-preview');
    var status  = document.getElementById('ant-ocr-status');

    zona.addEventListener('dragover', function(e){ e.preventDefault(); zona.classList.add('dragover'); });
    zona.addEventListener('dragleave', function(){ zona.classList.remove('dragover'); });
    zona.addEventListener('drop', function(e){ e.preventDefault(); zona.classList.remove('dragover'); if(e.dataTransfer.files[0]) cargarImagen(e.dataTransfer.files[0]); });
    fileIn.addEventListener('change', function(){ if(this.files[0]) cargarImagen(this.files[0]); });

    // Listener para la cámara
    var camaraIn = document.getElementById('ant-camara-file');
    camaraIn.addEventListener('change', function(){
      if(this.files[0]) {
        document.getElementById('ant-zona-ocr').style.display = 'block';
        document.getElementById('ant-ocr-zone').style.display = 'block';
        document.getElementById('ant-preview-wrap').style.display = 'none';
        cargarImagen(this.files[0]);
        this.value = '';
      }
    });

    var imagenBase64Actual = null;
    var imagenOriginal     = null;
    var rotacionActual     = 0;
    var esArchivoPDF       = false;
    var imagenBase64Actual2 = null;
    var imagenOriginal2     = null;
    var rotacionActual2     = 0;

    function cargarSegundaFoto(file2) {
      if (!file2) return;
      var esPDF2 = file2.type === 'application/pdf';
      if (!file2.type.startsWith('image/') && !esPDF2) return;
      rotacionActual2 = 0;
      imagenOriginal2 = null;
      var reader2 = new FileReader();
      reader2.onload = function(e) {
        imagenBase64Actual2 = e.target.result;
        imagenOriginal2     = e.target.result;
        document.getElementById('ant-ocr-segunda-placeholder').style.display = 'none';
        if (esPDF2) {
          document.getElementById('ant-ocr-preview-2').style.display = 'none';
          document.getElementById('ant-ocr-preview-pdf-nombre-2').textContent = file2.name;
          document.getElementById('ant-ocr-preview-pdf-2').style.display = 'block';
          document.getElementById('ant-btn-girar-segunda').style.display = 'none';
        } else {
          document.getElementById('ant-ocr-preview-pdf-2').style.display = 'none';
          document.getElementById('ant-ocr-preview-2').src = e.target.result;
          document.getElementById('ant-ocr-preview-2').style.display = 'block';
          document.getElementById('ant-btn-girar-segunda').style.display = 'block';
        }
      };
      reader2.readAsDataURL(file2);
    }

    document.getElementById('ant-ocr-file-2').addEventListener('change', function(){
      cargarSegundaFoto(this.files[0]);
    });

    var zonaSegunda = document.getElementById('ant-ocr-segunda-slot');
    zonaSegunda.addEventListener('dragover', function(e){ e.preventDefault(); zonaSegunda.classList.add('dragover'); });
    zonaSegunda.addEventListener('dragleave', function(){ zonaSegunda.classList.remove('dragover'); });
    zonaSegunda.addEventListener('drop', function(e){
      e.preventDefault();
      zonaSegunda.classList.remove('dragover');
      if (e.dataTransfer.files[0]) cargarSegundaFoto(e.dataTransfer.files[0]);
    });

    window.antEliminarSegunda = function() {
      imagenBase64Actual2 = null;
      imagenOriginal2     = null;
      rotacionActual2     = 0;
      document.getElementById('ant-ocr-file-2').value = '';
      document.getElementById('ant-ocr-segunda-placeholder').style.display = 'flex';
      document.getElementById('ant-btn-girar-segunda').style.display = 'none';
      document.getElementById('ant-ocr-preview-2').style.display = 'none';
      document.getElementById('ant-ocr-preview-2').src = '';
      document.getElementById('ant-ocr-preview-pdf-2').style.display = 'none';
    };

    function cargarImagen(file) {
      var esPDF = file.type === 'application/pdf';
      if (!file.type.startsWith('image/') && !esPDF) { mostrarStatus('err','Solo imagenes JPG, PNG, WEBP o archivos PDF'); return; }
      limpiarCampos();
      rotacionActual = 0;
      imagenOriginal = null;
      esArchivoPDF   = esPDF;

      if (esPDF) {
        var readerPdf = new FileReader();
        readerPdf.onload = function(e) {
          imagenBase64Actual = e.target.result;
          mostrarPreviewPDF(file.name);
        };
        readerPdf.readAsDataURL(file);
        return;
      }

      var reader = new FileReader();
      reader.onload = function(e) {
        var img = new Image();
        img.onload = function() {
          // Auto-rotar si está vertical
          if (img.height > img.width) rotacionActual = 90;
          imagenBase64Actual = e.target.result;
          mostrarPreviewConRotacion();
        };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    }

    function mostrarPreviewPDF(nombreArchivo) {
      document.getElementById('ant-ocr-preview').style.display = 'none';
      var pdfBox = document.getElementById('ant-ocr-preview-pdf');
      pdfBox.style.display = 'block';
      document.getElementById('ant-ocr-preview-pdf-nombre').textContent = nombreArchivo || 'documento.pdf';
      // Girar no aplica a PDF (se lee tal cual, con todas sus páginas)
      document.getElementById('ant-btn-girar-primera').style.display = 'none';
      document.getElementById('ant-ocr-zone').style.display = 'none';
      document.getElementById('ant-preview-wrap').style.display = 'block';
      document.getElementById('ant-ocr-status').style.display = 'none';
    }

    function mostrarPreviewConRotacion() {
      var img = new Image();
      img.onload = function() {
        // Guardar imagen original sin rotar para que girar siempre parta de cero
        if (!imagenOriginal) imagenOriginal = imagenBase64Actual;
        var canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
        var rad = rotacionActual * Math.PI / 180;
        if (rotacionActual === 90 || rotacionActual === 270) {
          canvas.width = img.height; canvas.height = img.width;
        } else {
          canvas.width = img.width; canvas.height = img.height;
        }
        ctx.translate(canvas.width/2, canvas.height/2);
        ctx.rotate(rad);
        ctx.drawImage(img, -img.width/2, -img.height/2);
        var imagenRotada = canvas.toDataURL('image/jpeg', 0.9);
        // Mostrar preview (restaurar UI en caso de que el archivo anterior fuera un PDF)
        var previewEl = document.getElementById('ant-ocr-preview');
        previewEl.style.display = 'block';
        previewEl.src = imagenRotada;
        document.getElementById('ant-ocr-preview-pdf').style.display = 'none';
        document.getElementById('ant-btn-girar-primera').style.display = 'block';
        // Guardar imagen rotada para el OCR
        imagenBase64Actual = imagenRotada;
        // Mostrar panel de orientación
        document.getElementById('ant-ocr-zone').style.display = 'none';
        document.getElementById('ant-preview-wrap').style.display = 'block';
        document.getElementById('ant-ocr-status').style.display = 'none';
      };
      img.src = imagenBase64Actual;
    }

    var imagenOriginal = null; // guarda siempre la imagen sin ninguna rotación

    window.antGirarImagen = function() {
      rotacionActual = (rotacionActual + 90) % 360;
      var img = new Image();
      img.onload = function() {
        var canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
        var rad = rotacionActual * Math.PI / 180;
        if (rotacionActual === 90 || rotacionActual === 270) {
          canvas.width = img.height; canvas.height = img.width;
        } else {
          canvas.width = img.width; canvas.height = img.height;
        }
        ctx.translate(canvas.width/2, canvas.height/2);
        ctx.rotate(rad);
        ctx.drawImage(img, -img.width/2, -img.height/2);
        var imagenRotada = canvas.toDataURL('image/jpeg', 0.9);
        document.getElementById('ant-ocr-preview').src = imagenRotada;
        imagenBase64Actual = imagenRotada;
      };
      // Siempre desde la imagen original sin rotación acumulada
      img.src = imagenOriginal;
    };

    window.antGirarImagen2 = function() {
      rotacionActual2 = (rotacionActual2 + 90) % 360;
      var img2 = new Image();
      img2.onload = function() {
        var canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
        var rad = rotacionActual2 * Math.PI / 180;
        if (rotacionActual2 === 90 || rotacionActual2 === 270) {
          canvas.width = img2.height; canvas.height = img2.width;
        } else {
          canvas.width = img2.width; canvas.height = img2.height;
        }
        ctx.translate(canvas.width/2, canvas.height/2);
        ctx.rotate(rad);
        ctx.drawImage(img2, -img2.width/2, -img2.height/2);
        var imagenRotada2 = canvas.toDataURL('image/jpeg', 0.9);
        document.getElementById('ant-ocr-preview-2').src = imagenRotada2;
        imagenBase64Actual2 = imagenRotada2;
      };
      // Siempre desde la imagen original sin rotación acumulada
      img2.src = imagenOriginal2;
    };

    window.antContinuarOCR = function() {
      document.getElementById('ant-preview-wrap').style.display = 'none';
      procesarImagen(imagenBase64Actual, imagenBase64Actual2);
    };

    window.antEliminarImagen = function() {
      imagenBase64Actual = null;
      rotacionActual = 0;
      esArchivoPDF = false;
      document.getElementById('ant-preview-wrap').style.display = 'none';
      document.getElementById('ant-ocr-zone').style.display = 'block';
      document.getElementById('ant-ocr-status').style.display = 'none';
      document.getElementById('ant-ocr-preview').style.display = 'block';
      document.getElementById('ant-ocr-preview').src = '';
      document.getElementById('ant-ocr-preview-pdf').style.display = 'none';
      document.getElementById('ant-btn-girar-primera').style.display = 'block';
      document.getElementById('ant-ocr-file').value = '';
      document.getElementById('ant-camara-file').value = '';
      window.antEliminarSegunda();
    };

    // Mostrar solo bloque-info al terminar de confirmar la foto
    window.antMostrarSoloInfo = function() {
      document.getElementById('bloque-info').classList.add('visible');
      ['bloque-tramites','bloque-depto','bloque-municipal'].forEach(function(id) {
        document.getElementById(id).classList.remove('visible');
      });
      document.getElementById('bloque-liq').style.display = 'none';
      // Expandir info
      document.getElementById('ant-info-contenido').style.display = 'block';
      document.getElementById('ant-info-colapsado').style.display = 'none';
    };

    var CAMPOS_A_VALIDAR = ['ant-placa-editar','ant-municipio-input','ant-cedula','ant-apellidos',
      'ant-clase','ant-marca','ant-linea','ant-modelo','ant-cilindrada','ant-servicio','ant-capacidad',
      'ant-limitacion-propiedad'];

    function marcarCamposVacios() {
      CAMPOS_A_VALIDAR.forEach(function(id) {
        var el = document.getElementById(id);
        if (!el) return;
        var fila = el.closest('.ant-group');
        if (!fila) return;
        if (!el.value || !el.value.trim()) {
          fila.classList.add('ant-campo-vacio');
        } else {
          fila.classList.remove('ant-campo-vacio');
        }
      });
    }

    window.aplicarDatosLeidos = function(data) {
      var scrollGuardado = window.scrollY;
      var tipodocMap = (function(t) {
        if (!t) return 'CC';
        t = t.toUpperCase().replace(/[.\s]/g,'');
        if (t==='CC') return 'CC';
        if (t==='NIT') return 'NIT';
        if (t==='CE') return 'CE';
        if (t==='TI') return 'TI';
        if (t==='RC') return 'RC';
        if (t==='PPT') return 'PPT';
        return 'CC';
      })(data.tipo_documento);

      if (data.placa) {
        document.getElementById('ant-placa').value = data.placa;
        var pe = document.getElementById('ant-placa-edit');
        if (pe) pe.value = data.placa;
        var pe2 = document.getElementById('ant-placa-editar');
        if (pe2) pe2.value = data.placa;
        document.getElementById('ant-placa-letras').textContent  = data.placa.substring(0,3) || '---';
        document.getElementById('ant-placa-numeros').textContent = data.placa.substring(3)   || '---';
      }
      if (data.marca)      document.getElementById('ant-marca').value      = data.marca;
      if (data.linea)      document.getElementById('ant-linea').value      = data.linea;
      if (data.modelo)     document.getElementById('ant-modelo').value     = data.modelo;
      if (data.clase)      document.getElementById('ant-clase').value      = data.clase;
      if (data.servicio) {
        var servicioVal = data.servicio.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
        document.getElementById('ant-servicio').value = servicioVal;
        actualizarColorPlaca();
      }
      if (data.capacidad)  document.getElementById('ant-capacidad').value  = data.capacidad;
      if (data.cilindrada) document.getElementById('ant-cilindrada').value = data.cilindrada;
      if (data.carroceria) document.getElementById('ant-carroceria').value = data.carroceria;
      if (data.cedula)     document.getElementById('ant-cedula').value     = data.cedula;
      if (data.apellidos)  document.getElementById('ant-apellidos').value  = data.apellidos;
      if (!data.limitacion_propiedad) {
        document.getElementById('ant-limitacion-propiedad').value = '';
      } else if (/^\s*(ningun[ao]?|\*+)\s*$/i.test(data.limitacion_propiedad)) {
        document.getElementById('ant-limitacion-propiedad').value = 'NO';
      } else {
        document.getElementById('ant-limitacion-propiedad').value = 'SI';
      }
      document.getElementById('ant-tipodoc').value = tipodocMap;
      actualizarReglasDocumento();

      if (!data.desde_cache) antDatosOCR = data;
      ocrLeido = true;

      document.getElementById('ant-bienvenida').style.display = 'none';
      var vp2327 = document.getElementById('tramyVehiculosPanel'); if (vp2327) vp2327.style.display = 'none';
      document.getElementById('ant-zona-ocr').style.display = 'none';
      var elInfoTop = document.getElementById('bloque-info-top');
      if (elInfoTop) elInfoTop.style.display = 'none';
      var elZonaRunt = document.getElementById('ant-zona-runt');
      if (elZonaRunt) elZonaRunt.style.display = 'none';

      if (data.municipio) {
        // Se quitan tildes -- el sistema guarda los municipios sin tilde
        // en todas sus listas (ej. "MEDELLIN"), pero algunos documentos
        // (como la Declaracion Sugerida) los traen bien escritos CON
        // tilde ("MEDELLÍN"), y esa diferencia rompia las comparaciones
        // exactas en varios lados (Impuesto Departamental, honorarios, etc).
        var municipioLimpio = data.municipio.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().trim();
        document.getElementById('ant-municipio-input').value = municipioLimpio;
        document.getElementById('ant-municipio').value       = municipioLimpio;
        antMunicipioActual = municipioLimpio;
        var placaMunAplicar = document.getElementById('ant-placa-municipio');
        if (placaMunAplicar) placaMunAplicar.textContent = municipioLimpio;
      }

      actualizarVisibilidad();
      cargarTramites();

      var detectados = [data.placa,data.marca,data.modelo,data.cedula].filter(Boolean).length;
      if (data.paz_salvo_antioquia_detectado) {
        var elStatus = document.getElementById('ant-ocr-status');
        elStatus.className = 'ant-ocr-status ok';
        elStatus.innerHTML = '✓ Se detectó el recibo de pago de Impuesto Departamental — este vehículo quedó marcado como paz y salvo para el año actual.';
        elStatus.style.display = 'block';
      } else {
        document.getElementById('ant-ocr-status').style.display = 'none';
      }
      marcarCamposVacios();
      window.scrollTo(0, scrollGuardado);
      if(typeof window.tramyVerificarDisponibilidadRunt === 'function') window.tramyVerificarDisponibilidadRunt();
      return detectados;
    };

    function procesarImagen(imagenBase64, imagenBase64_2) {
      mostrarStatus('procesando','Leyendo tarjeta de propiedad...');
      var cuerpoPeticion = {imagen: imagenBase64, municipio: document.getElementById('ant-municipio').value};
      if (imagenBase64_2) cuerpoPeticion.imagen2 = imagenBase64_2;
      fetch(ANT_API+'/ocr-tarjeta', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(cuerpoPeticion)
      })
      .then(function(r){return r.json();})
      .then(function(data) {
        if (data.error) { mostrarStatus('err','Error: '+data.error); return; }
        var detectados = aplicarDatosLeidos(data);
        if (detectados === 0) {
          mostrarStatus('err', 'No se pudieron detectar datos. Completa manualmente.');
        }
      })
      .catch(function(err){ mostrarStatus('err','Error: '+err.message); });
    }

    function mostrarStatus(tipo, msg) {
      status.className = 'ant-ocr-status '+tipo;
      status.innerHTML = msg; status.style.display='block';
    }

    // Impuesto Departamental
    document.getElementById('ant-btn-impuesto').addEventListener('click', function() {
      var placa     = document.getElementById('ant-placa').value.trim().toUpperCase();
      var cedula    = document.getElementById('ant-cedula').value.trim();
      var modelo    = document.getElementById('ant-modelo').value.trim();
      var municipio = antMunicipioActual.toUpperCase();
      var apellidos = document.getElementById('ant-apellidos').value.trim().toUpperCase();
      var tipodoc   = document.getElementById('ant-tipodoc').value.trim().toUpperCase();
      var btn       = document.getElementById('ant-btn-impuesto');
      var resultado = document.getElementById('ant-result-depto');

      if (!placa||!cedula||!modelo||!municipio||!apellidos) {
        resultado.innerHTML='<div class="ant-alert error">Por favor completa todos los datos del vehiculo.</div>';
        return;
      }


      // ── PASO 1: Consultar vigencias (rapido) ──────────────────────────────
      btn.disabled = true;
      resultado.innerHTML = '<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Consultando vigencias en la Gobernación de Antioquia...</span></div>';

      fetch(ANT_API+'/consultar/antioquia/vigencias?placa='+encodeURIComponent(placa)
        +'&identificacion='+encodeURIComponent(cedula)
        +'&modelo='+encodeURIComponent(modelo)
        +'&municipio_transito='+encodeURIComponent(municipio)
        +'&apellidos_propietario='+encodeURIComponent(apellidos)
        +'&tipo_documento='+encodeURIComponent(tipodoc))
        .then(function(r){ return r.json(); })
        .then(function(data) {
          btn.disabled = false;
          if (data.error) {
            resultado.innerHTML = '<div class="ant-alert error">'+data.error+'</div>';
            return;
          }

          var info = data.placa_info || {};
          var infoHtml = info.marca
            ? '<div class="ant-info"><div class="ant-info-item"><label>Placa</label><span>'+data.placa+'</span></div>'
              +'<div class="ant-info-item"><label>Marca</label><span>'+info.marca+' '+(info.linea||'')+'</span></div>'
              +'<div class="ant-info-item"><label>Modelo</label><span>'+(info.modelo||'')+'</span></div>'
              +'<div class="ant-info-item"><label>Propietario</label><span>'+(info.propietario||info.nombrePropietario||'')+'</span></div></div>' : '';

          // Paz y salvo
          if (data.sin_deuda) {
            if (data.avaluo) {
              antAvaluo = data.avaluo;
              if (hayTraspaso() && !esEmpresa()) {
                setLiq('liq-retefuente', Math.round(data.avaluo/100));
                document.getElementById('liq-row-retefuente').style.display = 'grid';
              }
              var blRet = document.getElementById('bloque-retefuente');
              if (blRet) { blRet.style.display='none'; blRet.classList.remove('visible'); }
            }
            resultado.innerHTML = infoHtml
              + '<div class="ant-alert success">'+data.placa+' esta a paz y salvo con la Gobernacion de Antioquia.</div>'
              + (data.avaluo ? '<div class="ant-extra"><span>Retefuente (1%)</span><strong>$'+Math.round(data.avaluo/100).toLocaleString('es-CO')+'</strong></div>' : '');

            // Aunque no haya ninguna vigencia adeudada, se deja la fila
            // del departamental en $0 en la liquidacion -- para que
            // quede constancia de que se consulto y esta al dia (evita
            // que el cliente pregunte si debe impuestos).
            var liqRowDeptoPaz = document.getElementById('liq-row-depto');
            if (liqRowDeptoPaz) {
              setLiq('liq-depto', 0);
              liqRowDeptoPaz.style.display = 'grid';
              var lblDPaz = document.querySelector('#liq-row-depto .ant-liq-nombre');
              if (lblDPaz) lblDPaz.textContent = 'Impuesto Departamental';
            }
            return;
          }

          // Hay vigencias — mostrar tabla con botón para consultar valores
          var vigencias = data.vigencias || [];
          var filasHtml = vigencias.map(function(v) {
            return '<tr><td>'+v.vigencia+'</td><td>Pendiente de pago</td><td style="text-align:right;color:#888;">Pendiente...</td></tr>';
          }).join('');

          resultado.innerHTML = infoHtml
            + '<table class="ant-table"><thead><tr><th>Vigencia</th><th>Estado</th><th style="text-align:right">Valor</th></tr></thead>'
            + '<tbody id="ant-tbody-vigencias">'+filasHtml+'</tbody></table>'
            + '<button id="ant-btn-valores" class="ant-btn ant-btn-primary" style="margin-top:12px;width:100%;">Consultar valores de cada vigencia</button>'
            + '<div id="ant-prog-wrap" style="display:none;margin-top:12px;">'
            + '<div class="ant-progreso-wrap"><div class="ant-progreso-msg" id="ant-prog-msg">Iniciando...</div>'
            + '<div class="ant-progreso-barra-bg"><div class="ant-progreso-barra" id="ant-prog-barra" style="width:5%"></div></div></div>'
            + '</div>';

          // ── PASO 2: Consultar valores (asincrono) ─────────────────────────
          document.getElementById('ant-btn-valores').addEventListener('click', function() {
            var btnVal = this;
            btnVal.disabled = true;
            document.getElementById('ant-prog-wrap').style.display = 'block';
            var antProgresoPorc = 5;

            var aniosVigencias = vigencias.map(function(v){ return v.vigencia; }).join(',');
            fetch(ANT_API+'/consultar?placa='+encodeURIComponent(placa)
              +'&municipio=antioquia&identificacion='+encodeURIComponent(cedula)
              +'&modelo='+encodeURIComponent(modelo)
              +'&municipio_transito='+encodeURIComponent(municipio)
              +'&apellidos_propietario='+encodeURIComponent(apellidos)
              +'&tipo_documento='+encodeURIComponent(tipodoc)
              +'&vigencias='+encodeURIComponent(aniosVigencias))
              .then(function(r){ return r.json(); })
              .then(function(resp) {
                if (resp.error) {
                  btnVal.disabled = false;
                  document.getElementById('ant-prog-msg').textContent = 'Error: '+resp.error;
                  return;
                }

                // Respuesta desde caché — sin polling
                if (resp.desde_cache && !resp.job_id) {
                  btnVal.disabled = false;
                  document.getElementById('ant-prog-wrap').style.display = 'none';
                  var d = resp;
                  if (d.avaluo) {
                    antAvaluo = d.avaluo;
                    if (hayTraspaso() && !esEmpresa()) {
                      setLiq('liq-retefuente', Math.round(d.avaluo/100));
                      document.getElementById('liq-row-retefuente').style.display = 'grid';
                    }
                    var blRet = document.getElementById('bloque-retefuente');
                    if (blRet) { blRet.style.display='none'; blRet.classList.remove('visible'); }
                  }
                  setLiq('liq-depto', d.total || 0);
                  document.getElementById('liq-row-depto').style.display = 'grid';
                  var nVig = (d.registros || []).filter(function(r){ return r.total_vigencia > 0; }).length;
                  var lblD = document.querySelector('#liq-row-depto .ant-liq-nombre');
                  if (lblD) {
                    lblD.textContent = nVig > 0
                      ? 'Impuesto Departamental (' + nVig + ' vigencia' + (nVig > 1 ? 's' : '') + ')'
                      : 'Impuesto Departamental';
                  }
                  var tbody = document.getElementById('ant-tbody-vigencias');
                  if (tbody && d.registros) {
                    tbody.innerHTML = d.registros.map(function(r) {
                      return '<tr><td>'+r.vigencia+'</td><td>'+r.estado+'</td><td style="text-align:right">'
                        +(r.total_vigencia ? '$'+r.total_vigencia.toLocaleString('es-CO') : 'Ver con asesor')+'</td></tr>';
                    }).join('');
                  }
                  var totalHtml = (d.total ? '<div class="ant-total-bar"><span>Total vigencias</span><span>$'+d.total.toLocaleString('es-CO')+'</span></div>' : '')
                    + (d.avaluo ? '<div class="ant-extra"><span>Retefuente (1%)</span><strong>$'+Math.round(d.avaluo/100).toLocaleString('es-CO')+'</strong></div>' : '');
                  var btnValEl = document.getElementById('ant-btn-valores');
                  if (btnValEl) btnValEl.remove();
                  resultado.innerHTML += totalHtml;
                  window._tramyUltimaConsultaAntioquia = {
                    vigenciasConDeuda: (d.registros || []).filter(function(r){ return r.total_vigencia > 0; }).map(function(r){ return r.vigencia; }),
                    placa: placa, cedula: cedula, tipodoc: tipodoc, modelo: modelo, municipio: municipio, apellidos: apellidos
                  };
                  if(typeof window.tramyActualizarLinksSecciones === 'function'){
                    window.tramyActualizarLinksSecciones(placa, window._tramyUltimaConsultaAntioquia.vigenciasConDeuda);
                  }
                  return;
                }

                var jobId = resp.job_id;
                var timer = setInterval(function() {
                  fetch(ANT_API+'/consultar/estado?job_id='+jobId)
                    .then(function(r){ return r.json(); })
                    .then(function(estado) {
                      // Actualizar barra y mensaje
                      if (estado.mensaje) {
                        antProgresoPorc = Math.min(antProgresoPorc + 10, 90);
                        var msgEl = document.getElementById('ant-prog-msg');
                        var barEl = document.getElementById('ant-prog-barra');
                        if (msgEl) msgEl.textContent = estado.mensaje;
                        if (barEl) barEl.style.width = antProgresoPorc + '%';
                      }

                      if (estado.estado === 'listo') {
                        clearInterval(timer);
                        btnVal.disabled = false;
                        document.getElementById('ant-prog-wrap').style.display = 'none';
                        var d = estado.resultado;
                        if (!d) return;

                        // Rellenar valores en la tabla
                        if (d.avaluo) {
                          antAvaluo = d.avaluo;
                          if (hayTraspaso() && !esEmpresa()) {
                            setLiq('liq-retefuente', Math.round(d.avaluo/100));
                            document.getElementById('liq-row-retefuente').style.display = 'grid';
                          }
                          var blRet = document.getElementById('bloque-retefuente');
                          if (blRet) { blRet.style.display='none'; blRet.classList.remove('visible'); }
                        }
                        setLiq('liq-depto', d.total || 0);
                        document.getElementById('liq-row-depto').style.display = 'grid';
                        var nVig = (d.registros || []).filter(function(r){ return r.total_vigencia > 0; }).length;
                        var lblD = document.querySelector('#liq-row-depto .ant-liq-nombre');
                        if (lblD) {
                          lblD.textContent = nVig > 0
                            ? 'Impuesto Departamental (' + nVig + ' vigencia' + (nVig > 1 ? 's' : '') + ')'
                            : 'Impuesto Departamental';
                        }

                        // Actualizar filas de la tabla con los valores reales
                        var tbody = document.getElementById('ant-tbody-vigencias');
                        if (tbody && d.registros) {
                          tbody.innerHTML = d.registros.map(function(r) {
                            return '<tr><td>'+r.vigencia+'</td><td>'+r.estado+'</td><td style="text-align:right">'
                              +(r.total_vigencia ? '$'+r.total_vigencia.toLocaleString('es-CO') : 'Ver con asesor')+'</td></tr>';
                          }).join('');
                        }

                        // Agregar total y retefuente debajo de la tabla
                        var totalHtml = (d.total ? '<div class="ant-total-bar"><span>Total vigencias</span><span>$'+d.total.toLocaleString('es-CO')+'</span></div>' : '')
                          + (d.avaluo ? '<div class="ant-extra"><span>Retefuente (1%)</span><strong>$'+Math.round(d.avaluo/100).toLocaleString('es-CO')+'</strong></div>' : '')
                          + (d.excede_limite ? '<div class="ant-warning">'+d.mensaje_limite+'</div>' : '');

                        var btnValEl = document.getElementById('ant-btn-valores');
                        if (btnValEl) btnValEl.remove();
                        resultado.innerHTML += totalHtml;
                        window._tramyUltimaConsultaAntioquia = {
                          vigenciasConDeuda: (d.registros || []).filter(function(r){ return r.total_vigencia > 0; }).map(function(r){ return r.vigencia; }),
                          placa: placa, cedula: cedula, tipodoc: tipodoc, modelo: modelo, municipio: municipio, apellidos: apellidos
                        };
                        if(typeof window.tramyActualizarLinksSecciones === 'function'){
                          window.tramyActualizarLinksSecciones(placa, window._tramyUltimaConsultaAntioquia.vigenciasConDeuda);
                        }

                        // Mostrar bloque municipal si aplica (colapsado)
                        var _munUp = antMunicipioActual ? antMunicipioActual.toUpperCase() : '';
                        var _servUp = (document.getElementById('ant-servicio').value||'').normalize('NFD').replace(/[̀-ͯ]/g,'').trim().toUpperCase();
                        var _esMedPublico = (_munUp === 'MEDELLIN' && _servUp === 'PUBLICO');
                        var _tieneMunAqui = (_munUp !== 'MEDELLIN') ? !!MUNICIPIOS_MUNICIPALES[_munUp] : _esMedPublico;
                        if (antMunicipioActual && _tieneMunAqui) {
                          var blMun = document.getElementById('bloque-municipal');
                          blMun.classList.add('visible'); blMun.style.display = 'block';
                          document.getElementById('ant-result-municipal').innerHTML = '';
                          var contMun = document.getElementById('contenido-municipal');
                          if (contMun) contMun.style.display = 'none';
                          var chevMun = document.getElementById('chevron-municipal');
                          if (chevMun) chevMun.textContent = '▼';
                        }

                      } else if (estado.estado === 'error') {
                        clearInterval(timer);
                        btnVal.disabled = false;
                        document.getElementById('ant-prog-msg').textContent = 'Error: '+(estado.error||estado.mensaje);
                      }
                    })
                    .catch(function(){});
                }, 3000);
              })
              .catch(function(){
                btnVal.disabled = false;
                document.getElementById('ant-prog-msg').textContent = 'Error de conexion.';
              });
          });
        })
        .catch(function(){
          btn.disabled = false;
          resultado.innerHTML = '<div class="ant-alert error">Error de conexion.</div>';
        });
    });
    // Impuesto Municipal
    document.getElementById('ant-btn-municipal').addEventListener('click', function() {
      var placa     = document.getElementById('ant-placa').value.trim().toUpperCase();
      var municipio = document.getElementById('ant-municipio').value;
      var resultado = document.getElementById('ant-result-municipal');
      var btn       = this;

      if (!placa||!municipio) {
        resultado.innerHTML='<div class="ant-alert error">Ingresa la placa y selecciona el municipio.</div>'; return;
      }

      var municipioApi = (municipio === 'MEDELLIN') ? 'medellin' : MUNICIPIOS_MUNICIPALES[municipio];
      btn.disabled=true;
      resultado.innerHTML='<div class="ant-loading"><div class="ant-spinner-ring"></div><span>Consultando impuesto municipal...</span></div>';

      var urlMun = ANT_API+'/consultar?placa='+encodeURIComponent(placa)+'&municipio='+encodeURIComponent(municipioApi);
      if (municipioApi === 'medellin') {
        var cedula   = document.getElementById('ant-cedula').value || '';
        var modelo   = document.getElementById('ant-modelo').value || '';
        var apellidos = document.getElementById('ant-apellidos').value || '';
        urlMun += '&identificacion='+encodeURIComponent(cedula)
               +  '&modelo='+encodeURIComponent(modelo)
               +  '&apellidos_propietario='+encodeURIComponent(apellidos)
               +  '&tipo_documento='+encodeURIComponent(document.getElementById('ant-tipodoc').value||'CC');
      }
      fetch(urlMun)
        .then(function(r){return r.json();})
        .then(function(data){
          btn.disabled=false;
          if (data.error){resultado.innerHTML='<div class="ant-alert error">'+data.error+'</div>';return;}

          setLiq('liq-municipal', data.total || 0);
          document.getElementById('liq-row-municipal').style.display='grid';
          var nVigM = (data.registros || []).length;
          var lblM = document.querySelector('#liq-row-municipal .ant-liq-nombre');
          if (lblM) {
            lblM.textContent = nVigM > 0
              ? 'Impuesto Municipal (' + nVigM + ' vigencia' + (nVigM > 1 ? 's' : '') + ')'
              : 'Impuesto Municipal';
          }

          if (data.sin_deuda) {
            var msgPaz = data.placa+' está a paz y salvo en el Tránsito de '+municipio+'.';
            var detalles = [];
            if (data.placa_vista) detalles.push('Placa verificada: <strong>'+data.placa_vista+'</strong>');
            if (data.marca)       detalles.push('Marca: <strong>'+data.marca+'</strong>');
            if (data.fecha_pago)  detalles.push('Fecha pago: <strong>'+data.fecha_pago+'</strong>');
            if (data.valor_pago)  detalles.push('Valor pago: <strong>'+data.valor_pago+'</strong>');
            if (detalles.length) msgPaz += '<br><small>'+detalles.join(' · ')+'</small>';
            if (!data.verificado) {
              // No se pudo confirmar placa/marca del vehículo consultado: posible falso positivo
              msgPaz += '<br><small style="color:#b45309">⚠ No se pudo verificar placa/marca en la página de origen. '
                      + 'Revisa manualmente antes de confiar en este resultado (posible falso positivo).</small>';
            }
            resultado.innerHTML='<div class="ant-alert '+(data.verificado ? 'success' : 'warning')+'">'+msgPaz+'</div>';
            return;
          }

          var _ultPago = '';
          if (data.placa_vista || data.marca || data.fecha_pago || data.valor_pago) {
            var _det = [];
            if (data.placa_vista) _det.push('Placa vista: <strong>'+data.placa_vista+'</strong>');
            if (data.marca)       _det.push('Marca: <strong>'+data.marca+'</strong>');
            if (data.fecha_pago)  _det.push('Último pago: <strong>'+data.fecha_pago+'</strong>');
            if (data.valor_pago)  _det.push('Valor: <strong>'+data.valor_pago+'</strong>');
            _ultPago = '<div class="ant-info-item" style="grid-column:1/-1"><label>Último pago</label><span>'+_det.join(' · ')+'</span></div>';
          }
          resultado.innerHTML='<div class="ant-info">'
            +'<div class="ant-info-item"><label>Placa</label><span>'+data.placa+'</span></div>'
            +'<div class="ant-info-item"><label>Municipio</label><span>'+municipio+'</span></div>'
            +(data.registros&&data.registros[0]&&data.registros[0].tipo_vehiculo?'<div class="ant-info-item"><label>Tipo</label><span>'+data.registros[0].tipo_vehiculo+'</span></div>':'')
            +_ultPago
            +'</div>'
            +'<table class="ant-table"><thead><tr><th>Anio</th><th>Descripcion</th><th style="text-align:right">Valor</th></tr></thead><tbody>'
            +(data.registros||[]).map(function(r){
              return '<tr><td>'+r.vigencia+'</td><td>'+(r.descripcion||'Sistematizacion')+'</td><td style="text-align:right">$'+r.total_vigencia.toLocaleString('es-CO')+'</td></tr>';
            }).join('')+'</tbody></table>'
            +'<div class="ant-total-bar"><span>Total adeudado</span><span>$'+data.total.toLocaleString('es-CO')+'</span></div>';
        })
        .catch(function(){btn.disabled=false;resultado.innerHTML='<div class="ant-alert error">Error de conexion.</div>';});
    });

  }); // end load

  // ── FUNCIONES GLOBALES ────────────────────────────────────────────────────

  // ── RETEFUENTE ───────────────────────────────────────────────────────────
  var antRetAvaluo     = 0;
  var antRetRetefuente = 0;

  function antCargarRetefuente() {
    var marca      = (document.getElementById('ant-marca').value || '').trim().toUpperCase();
    var linea      = (document.getElementById('ant-linea').value || '').trim().toUpperCase();
    var clase      = (document.getElementById('ant-clase').value || '').trim().toUpperCase();
    var carroceria = (document.getElementById('ant-carroceria').value || '').trim().toUpperCase();
    var modelo     = (document.getElementById('ant-modelo').value || '').trim();
    var cil        = (document.getElementById('ant-cilindrada').value || '').trim();
    var cap        = (document.getElementById('ant-capacidad').value || '').trim();
    var capLimpiaFetch = cap.replace(/\./g, '').replace(/,/g, '');  // 5.610 -> 5610

    // Llenar datos del vehículo en el módulo retefuente
    var setDato = function(id, val) {
      var el = document.getElementById(id);
      if (el) { el.textContent = val; el.style.display = val ? '' : 'none'; }
    };
    setDato('ret-dato-clase',  clase);
    setDato('ret-dato-marca',  marca);
    setDato('ret-dato-linea',  linea);
    setDato('ret-dato-modelo', modelo);
    setDato('ret-dato-cil',    cil ? cil + 'cc' : '');
    // Limpiar puntos de miles antes de parsear (5.610 -> 5610)
    var capLimpia = cap ? cap.replace(/\./g, '').replace(/,/g, '') : '';
    var capNum = parseInt(capLimpia) || 0;
    var capDisplay = '';
    if (cap) {
        if (capNum >= 100) {
            capDisplay = capNum.toLocaleString('es-CO') + ' Kg · — pasajeros';
        } else {
            capDisplay = '— Kg · ' + capNum + ' pasajeros';
        }
    }
    setDato('ret-dato-cap', capDisplay);

    if (!marca || !clase || !modelo) return;

    var estado = document.getElementById('ant-ret-estado');
    var opcDiv = document.getElementById('ant-ret-opciones');
    estado.textContent = 'Buscando...';
    opcDiv.innerHTML   = '';
    document.getElementById('ant-ret-resultado').style.display = 'none';

    var cilindrada = (document.getElementById('ant-cilindrada').value || '').trim();
    var cilNum = cilindrada ? parseInt(cilindrada) : 999;
    var esBajoCil = (clase === 'MOTOCICLETA' || clase === 'MOTOCARRO') && cilNum > 0 && cilNum <= 125;

    if (esBajoCil) {
      // ── MÓDULO BAJO CILINDRAJE (SIBGA 2024) ──────────────────────────────
      estado.textContent = 'Buscando...';
      var modeloNum = parseInt(modelo) || 2020;

      fetch(ANT_API + '/sibga/opciones?marca=' + encodeURIComponent(marca)
        + '&linea=' + encodeURIComponent(linea)
        + '&modelo=' + modeloNum)
        .then(function(r){ return r.json(); })
        .then(function(data) {
          if (data.error || !data.opciones || !data.opciones.length) {
            estado.textContent = 'No se encontraron resultados para esta marca.';
            return;
          }
          estado.textContent = 'Se encontraron ' + data.opciones.length + ' opciones. Selecciona la que corresponde:';
          opcDiv.innerHTML = '';
          data.opciones.forEach(function(op) {
            var div = document.createElement('div');
            div.className = 'ant-ret-opcion';
            div.innerHTML =
              '<div class="ant-ret-opcion-nombre">' + op.linea +
                (op.cilindraje ? ' — ' + op.cilindraje + 'cc' : '') +
              '</div>' +
              '<div class="ant-ret-opcion-valor">Avalúo: $' + op.avaluo.toLocaleString('es-CO') + '</div>';
            div.addEventListener('click', function() {
              document.querySelectorAll('.ant-ret-opcion').forEach(function(el){ el.classList.remove('seleccionada'); });
              div.classList.add('seleccionada');
              antRetAvaluo     = op.avaluo;
              antRetRetefuente = op.retefuente;
              document.getElementById('ant-ret-linea-sel').textContent  = op.linea;
              document.getElementById('ant-ret-avaluo').textContent     = '$' + op.avaluo.toLocaleString('es-CO');
              document.getElementById('ant-ret-retefuente').textContent = '$' + op.retefuente.toLocaleString('es-CO');
              document.getElementById('ant-ret-resultado').style.display = 'block';
            });
            opcDiv.appendChild(div);
          });
        })
        .catch(function(e){ estado.textContent = 'Error de conexión.'; });

    } else {
      // ── MÓDULO NORMAL (retefuente_2026) ──────────────────────────────────
      var capacidad = (document.getElementById('ant-capacidad') ? document.getElementById('ant-capacidad').value : '') || '';
      fetch(ANT_API + '/retefuente/opciones?marca=' + encodeURIComponent(marca)
        + '&linea=' + encodeURIComponent(linea)
        + '&clase=' + encodeURIComponent(clase)
        + '&carroceria=' + encodeURIComponent(carroceria)
        + '&modelo=' + encodeURIComponent(modelo)
        + '&cilindraje=' + encodeURIComponent((cilindrada||'').replace(/\./g,'').replace(/,/g,''))
        + '&capacidad=' + encodeURIComponent(capacidad.replace(/\./g,'').replace(/,/g,'')))
        .then(function(r){ return r.json(); })
        .then(function(data) {
          if (data.error) { estado.textContent = 'Error: ' + data.error; return; }
          if (!data.opciones || data.opciones.length === 0) {
            estado.textContent = 'No se encontraron resultados para esta marca y clase.';
            return;
          }
          estado.textContent = 'Se encontraron ' + data.opciones.length + ' opciones. Selecciona la que corresponde:';
          opcDiv.innerHTML = '';
          data.opciones.forEach(function(op) {
            var div = document.createElement('div');
            div.className = 'ant-ret-opcion';
            div.innerHTML =
              '<div class="ant-ret-opcion-nombre">' + op.linea + (op.cilindraje ? ' — ' + op.cilindraje + 'cc' : '') +
                (op.tonelaje_kg ? ' · ' + op.tonelaje_kg.toLocaleString('es-CO') + ' Kg · — pax' : '') +
                (!op.tonelaje_kg && op.pasajeros ? ' · — Kg · ' + op.pasajeros + ' pasajeros' : '') +
                (!op.tonelaje_kg && !op.pasajeros ? '' : '') +
              '</div>' +
              '<div class="ant-ret-opcion-valor">Avalúo: $' + op.avaluo.toLocaleString('es-CO') + '</div>';
            div.addEventListener('click', function() {
              document.querySelectorAll('.ant-ret-opcion').forEach(function(el){ el.classList.remove('seleccionada'); });
              div.classList.add('seleccionada');
              antRetAvaluo     = op.avaluo;
              antRetRetefuente = op.retefuente;
              document.getElementById('ant-ret-linea-sel').textContent = op.linea;
              document.getElementById('ant-ret-avaluo').textContent    = '$' + op.avaluo.toLocaleString('es-CO');
              document.getElementById('ant-ret-retefuente').textContent = '$' + op.retefuente.toLocaleString('es-CO');
              document.getElementById('ant-ret-resultado').style.display = 'block';
            });
            opcDiv.appendChild(div);
          });
        })
        .catch(function(e){ estado.textContent = 'Error de conexión.'; });
    }
  }

  window.antUsarRetefuente = function() {
    if (!antRetRetefuente) return;
    if (esEmpresa()) return; // las empresas no pagan retefuente
    setLiq('liq-retefuente', antRetRetefuente);
    document.getElementById('liq-row-retefuente').style.display = 'grid';
    antAvaluo = antRetAvaluo;
    calcularTotal();
    // Cerrar bloque retefuente
    document.getElementById('contenido-ret').style.display = 'none';
    document.getElementById('chevron-ret').textContent = '▼';
  };

  // Recalcular numeración de pasos según bloques visibles
  window.antToggleAyuda = function(id) {
    var panel = document.getElementById(id);
    if (!panel) return;
    panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
  };

  function recalcularPasos() {
    var orden = [
      {id:'bloque-info',       titulo:'titulo-info',       nombre:'INFORMACION'},
      {id:'bloque-depto',      titulo:'titulo-depto',      nombre:'IMPUESTO DEPARTAMENTAL'},
      {id:'bloque-municipal',  titulo:'titulo-municipal',  nombre:'IMPUESTO MUNICIPAL'},
      {id:'bloque-tramites',   titulo:'titulo-tramites',   nombre:'TRAMITES'},
      {id:'bloque-retefuente', titulo:'titulo-ret',        nombre:'RETEFUENTE'},
      {id:'bloque-liq',        titulo:'titulo-liq',        nombre:'LIQUIDACION'},
      {id:'bloque-wa',         titulo:'titulo-wa',         nombre:'ENVIAR LIQUIDACION POR WHATSAPP'},
    ];
    var paso = 1;
    orden.forEach(function(b) {
      var bl  = document.getElementById(b.id);
      var tit = document.getElementById(b.titulo);
      if (!bl || !tit) return;
      var visible = bl.style.display !== 'none' && bl.style.cssText.indexOf('display: none') < 0;
      if (visible) {
        tit.textContent = 'PASO ' + paso + ' — ' + b.nombre;
        paso++;
      }
    });
  }

  window.antToggleInfoTop = function() {
    var contenido = document.getElementById('contenido-info-top');
    var chevron   = document.getElementById('chevron-info-top');
    if (!contenido) return;
    var visible = contenido.style.display !== 'none';
    contenido.style.display = visible ? 'none' : 'block';
    if (chevron) chevron.textContent = visible ? '▼' : '▲';
    // Si se expande, hacer scroll hacia el bloque
    if (!visible) {
      var bloque = document.getElementById('bloque-'+id);
      if (bloque) antScrollTo(bloque);
    }
  };


  function antScrollTo(el) {
    if (!el) return;
    setTimeout(function() {
      var top = el.getBoundingClientRect().top + window.scrollY - 56;
      document.documentElement.scrollTop = top;
    }, 100);
  }
  window.antToggleBloque = function(id) {
    var contenido = document.getElementById('contenido-'+id);
    var chevron   = document.getElementById('chevron-'+id);
    if (!contenido) return;
    var visible = contenido.style.display !== 'none';

    // Colapsar todos los bloques y sus ayudas primero
    var todos = ['depto','municipal','tramites','ret','liq'];
    todos.forEach(function(bid) {
      var c = document.getElementById('contenido-'+bid);
      var ch = document.getElementById('chevron-'+bid);
      var ay = document.getElementById('ayuda-'+bid);
      if (c) c.style.display = 'none';
      if (ch) ch.textContent = '▼';
      if (ay) ay.style.display = 'none';
    });
    // Colapsar también info
    var cInfo = document.getElementById('ant-info-contenido');
    var chInfo = document.getElementById('ant-info-chevron');
    if (cInfo) cInfo.style.display = 'none';
    if (chInfo) chInfo.textContent = '▼';

    // Si estaba cerrado, abrirlo. Si estaba abierto, dejarlo cerrado.
    if (!visible) {
      contenido.style.display = 'block';
      if (chevron) chevron.textContent = '▲';
      var bloqueId = id === 'ret' ? 'bloque-retefuente' : 'bloque-'+id;
      var bloque = document.getElementById(bloqueId);
      if (bloque) antScrollTo(bloque);
    }
  };

  window.antToggleInfo = function() {
    var contenido = document.getElementById('ant-info-contenido');
    var chevron   = document.getElementById('ant-info-chevron');
    var visible   = contenido.style.display !== 'none';
    // Al expandir info, colapsar todos los demás bloques
    if (!visible) {
      ['depto','municipal','tramites','ret','liq'].forEach(function(bid) {
        var c = document.getElementById('contenido-'+bid);
        var ch = document.getElementById('chevron-'+bid);
        if (c && c.style.display !== 'none') {
          c.style.display = 'none';
          if (ch) ch.textContent = '▼';
        }
      });
    }
    contenido.style.display = visible ? 'none' : 'block';
    document.getElementById('ant-info-colapsado').style.display = 'none';
    chevron.textContent = visible ? '▼' : '▲';
    if (!visible) {
      var bloqueInfo = document.getElementById('bloque-info');
      if (bloqueInfo) antScrollTo(bloqueInfo);
    }

    // Mostrar/ocultar placa mini y zona OCR
    var placaMini = document.getElementById('ant-placa-mini');
    if (infoConfirmada) {
      if (placaMini) placaMini.style.display = visible ? 'block' : 'none';
      var zonaOcr = document.getElementById('ant-zona-ocr');
      if (!visible && zonaOcr) zonaOcr.style.display = 'none';
    }
  };

  window.antConfirmarInfo = function() {
    var placa     = document.getElementById('ant-placa').value.trim().toUpperCase();
    var municipio = document.getElementById('ant-municipio').value;

    infoConfirmada = true;

    // Llevar la placa a las demas secciones (Revision, Ejecucion,
    // Utilidades) por la URL, para que todo el trabajo quede ligado al
    // mismo vehiculo sin tener que volver a escribir los datos.
    if(typeof window.tramyActualizarLinksSecciones === 'function'){
      window.tramyActualizarLinksSecciones(placa);
    }

    // Guardar este vehiculo en la lista del usuario logueado (si aplica),
    // para poder elegirlo de una lista la proxima vez sin repetir el OCR.
    if(typeof window.tramyGuardarVehiculo === 'function'){
      window.tramyGuardarVehiculo({
        placa:      placa,
        municipio:  municipio,
        tipo_documento: document.getElementById('ant-tipodoc').value,
        cedula:     document.getElementById('ant-cedula').value.trim(),
        apellidos:  document.getElementById('ant-apellidos').value.trim(),
        clase:      document.getElementById('ant-clase').value.trim(),
        marca:      document.getElementById('ant-marca').value.trim(),
        linea:      document.getElementById('ant-linea').value.trim(),
        modelo:     document.getElementById('ant-modelo').value.trim(),
        cilindrada: document.getElementById('ant-cilindrada').value.trim(),
        servicio:   document.getElementById('ant-servicio').value.trim(),
        capacidad:  document.getElementById('ant-capacidad').value.trim(),
        carroceria: document.getElementById('ant-carroceria').value.trim(),
        limitacion_propiedad: document.getElementById('ant-limitacion-propiedad').value
      });
    }

    // 1. Guardar en cache
    if (placa && municipio) {
      fetch(ANT_API+'/ocr-guardar-municipio', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({placa: placa, municipio: municipio})
      }).catch(function(){});
    }

    // 2. Colapsar informacion y ocultar zona OCR/bienvenida
    document.getElementById('ant-info-contenido').style.display = 'none';
    document.getElementById('ant-info-chevron').textContent = '▼';
    // Ocultar zona OCR, botones de entrada, bienvenida, saludo y bloque-info-top
    ['ant-zona-ocr', 'ant-bienvenida', 'ant-info-expandido'].forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    var elSaludo = document.getElementById('ant-saludo');
    if (elSaludo) elSaludo.style.display = 'none';
    var elInfoTop = document.getElementById('bloque-info-top');
    if (elInfoTop) elInfoTop.style.display = 'none';
    // Ocultar botones de entrada (tomar foto, subir, manual)
    var entradaBtns = document.querySelector('.ant-entrada-btns');
    if (entradaBtns) entradaBtns.style.display = 'none';
    var camaraFile = document.getElementById('ant-camara-file');
    if (camaraFile) camaraFile.style.display = 'none';

    // Mostrar placa mini encima del wrap
    var placaMini = document.getElementById('ant-placa-mini');
    if (placaMini) placaMini.style.display = 'block';
    var plcLetras  = document.getElementById('ant-placa-letras');
    var plcNumeros = document.getElementById('ant-placa-numeros');
    var plcMun     = document.getElementById('ant-placa-municipio');
    var colLetras  = document.getElementById('ant-placa-col-letras');
    var colNumeros = document.getElementById('ant-placa-col-numeros');
    var colMun     = document.getElementById('ant-placa-col-municipio');
    if (colLetras && plcLetras)   colLetras.textContent  = plcLetras.textContent;
    if (colNumeros && plcNumeros) colNumeros.textContent = plcNumeros.textContent;
    if (colMun && plcMun)         colMun.textContent     = plcMun.textContent;

    // 3. Ocultar mensaje OCR
    document.getElementById('ant-ocr-status').style.display = 'none';

    // Actualizar título del bloque-info con placa y municipio (permanente)
    var tituloInfo = document.getElementById('titulo-info');
    if (tituloInfo && placa) {
      tituloInfo.textContent = 'PASO 1 — INFORMACION ' + placa + (municipio ? ' ' + municipio : '') + ' - EDITAR';
    }

    // 4. Mostrar todos los bloques expandidos
    mostrarYExpandirBloques();
    cargarTramites();
    mostrarFilasDefecto();
    recalcularPasos();
    setTimeout(function() {
      window.scrollTo({top: 0, behavior: 'smooth'});
    }, 150);
  };

  window.antEnviarWA = function() {
    var canvas = document.getElementById('ant-canvas-liq');
    var ctx    = canvas.getContext('2d');
    var W      = 800;
    var filas  = [];

    [1,2,3,4,5].forEach(function(n) {
      var row = document.getElementById('liq-row-tramite'+n);
      if (row && row.style.display !== 'none') {
        var label = document.getElementById('liq-label-tramite'+n);
        var val   = parseLiq('liq-tramite'+n);
        filas.push({label: label ? label.textContent : 'Tramite '+n, valor: val});
      }
    });

    var rowRef = document.getElementById('liq-row-retefuente');
    if (rowRef && rowRef.style.display !== 'none') {
      var vRef = parseLiq('liq-retefuente');
      filas.push({label:'Retefuente (1% avaluo)', valor: vRef});
    }

    // Impuesto Departamental y Municipal -- SIEMPRE se incluyen en el
    // mensaje de WhatsApp, aunque esten en $0 (asi el cliente ve que se
    // revisaron y no pregunta si esta al dia de impuestos).
    ['liq-depto', 'liq-municipal'].forEach(function(id) {
      var rowEl = document.getElementById('liq-row-' + id.replace('liq-', ''));
      if (!rowEl || rowEl.style.display === 'none') return;
      var v = parseLiq(id);
      var spanNombre = rowEl.querySelector('.ant-liq-nombre');
      var label = (spanNombre && spanNombre.textContent.trim()) ? spanNombre.textContent.trim() : id;
      filas.push({label: label, valor: v});
    });

    var itemsFijos = [
      {id:'liq-pazsalvo',  rowId:'liq-row-pazsalvo',  label:'Paz y Salvo'},
      {id:'liq-envios',    rowId:'liq-row-envios',     label:'Envios y/o Domicilios'},
      {id:'liq-honorarios',rowId:'liq-row-honorarios', label:'Honorarios'}
    ];
    // Si el concepto esta agregado (fila visible), se incluye siempre en
    // el mensaje -- no tiene sentido agregarlo sin querer mostrarlo.
    itemsFijos.forEach(function(c) {
      var rowEl = document.getElementById(c.rowId);
      if (!rowEl || rowEl.style.display === 'none') return;
      var v = parseLiq(c.id);
      var spanNombre = rowEl.querySelector('.ant-liq-nombre');
      var label = (spanNombre && spanNombre.textContent.trim())
        ? spanNombre.textContent.trim()
        : (c.label || c.id);
      filas.push({label: label, valor: v});
    });
    // Cobros dinámicos -- se recorren TODAS las filas que existan en el
    // DOM (igual que hace calcularTotal), en vez de depender de
    // antCobrosCount, que nunca se incrementaba al agregar filas nuevas
    // y por eso el mensaje de WhatsApp solo traia la primera fila aunque
    // el total si sumara bien las demas.
    document.querySelectorAll('#liq-cobros-wrap .ant-liq-cobro').forEach(function(fila) {
      var cobroNombreEl = fila.querySelector('.ant-liq-cobro-nombre');
      var cobroValEl    = fila.querySelector('.liq-cobro-valor');
      if (cobroValEl && cobroNombreEl && cobroNombreEl.value.trim()) {
        var cobroVal = parseInt((cobroValEl.value||'0').replace(/\D/g,''),10)||0;
        filas.push({label: cobroNombreEl.value.trim(), valor: cobroVal});
      }
    });

    if (filas.length === 0) { alert('No hay items en la liquidacion.'); return; }

    var total    = filas.reduce(function(s,f){return s+f.valor;},0);
    var placa    = (document.getElementById('ant-placa').value||'').toUpperCase()||'SIN PLACA';
    var municipio = antMunicipioActual || '';
    var fecha    = new Date().toLocaleDateString('es-CO',{day:'2-digit',month:'long',year:'numeric'});

    // Obtener nombres de tramites seleccionados
    var tramitesNombres = [];
    [1,2,3,4,5].forEach(function(n) {
      var inp = document.getElementById('ant-tramite-'+n);
      if (inp && inp.value.trim()) tramitesNombres.push(inp.value.trim());
    });
    var tituloTramites = tramitesNombres.length > 0 ? tramitesNombres.join(' + ') : 'Liquidacion';
    var tituloCompleto = 'Tramy ' + tituloTramites + (municipio ? ' - ' + municipio : '');

    // Generar texto y enviar por WhatsApp
    var cedula  = document.getElementById('ant-cedula').value.trim();
    var tipodoc = document.getElementById('ant-tipodoc').value;
    var tituloTramitesTexto = tramitesNombres.length > 0 ? tramitesNombres.join(' + ') : 'LIQUIDACION';
    var tituloLiq = '*TRAMITE ' + tituloTramitesTexto + (municipio ? ' ' + municipio : '') + ' ' + placa + ' ' + tipodoc + ' ' + cedula + '*';
    var lineasLiq = filas.map(function(f){ return '- ' + f.label + ': $' + f.valor.toLocaleString('es-CO'); }).join('\n');

    // Helper: revisar si algún trámite contiene alguna de las palabras clave
    function tramiteContiene(palabras) {
      return [1,2,3,4,5].some(function(n) {
        var v = (document.getElementById('ant-tramite-'+n).value || '').toUpperCase();
        return palabras.some(function(p){ return v.includes(p.toUpperCase()); });
      });
    }

    var munReq    = antMunicipioActual.toUpperCase();
    var esDepto   = (munReq === 'DEPARTAMENTAL' || munReq === 'GIRARDOTA');
    var servicioVal = (document.getElementById('ant-servicio').value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase();
    var claseVal    = (document.getElementById('ant-clase').value || '').trim().toUpperCase();
    var capVal      = (document.getElementById('ant-capacidad').value || '').trim();
    var esPublico   = servicioVal === 'PUBLICO';
    var esPasajeros = ['BUS','BUSETA','MICROBUS','TAXI','COLECTIVO'].some(function(c){ return claseVal.includes(c); })
                   || (claseVal.includes('MOTOCARRO') && (capVal === '4' || capVal === '4 PASAJEROS'));

    var necesitaGenerales = false;
    var requisitosEspeciales = '';

    // TRASPASO DE PROPIEDAD
    if (tramiteContiene(['TRASPASO DE PROPIEDAD'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Contrato de compraventa\n- Copia documento de identidad Comprador\n- Improntas';
      if (esPublico && esPasajeros) {
        requisitosEspeciales += '\n- Sesion de derechos emitido por la empresa afiliadora';
      }
    }

    // TRASLADO DE CUENTA
    if (tramiteContiene(['TRASLADO DE CUENTA'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas';
    }

    // LEVANTAMIENTO DE PRENDA
    if (tramiteContiene(['LEVANTAMIENTO DE PRENDA'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Registro del levantamiento de prenda en la plataforma RUNT\n- Improntas';
    }

    // INSCRIPCION DE PRENDA
    if (tramiteContiene(['INSCRIPCION DE PRENDA'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Registro de inscripcion de prenda en la plataforma RUNT\n- Improntas';
    }

    // RADICADO DE CUENTA
    if (tramiteContiene(['RADICADO DE CUENTA'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas';
    }

    // DUPLICADO DE PLACAS
    if (tramiteContiene(['DUPLICADO DE PLACAS'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Contrato de mandato adicional (para reclamar las placas)\n- Copia documento de identidad Propietario adicional (para reclamar las placas)';
      if (esDepto) requisitosEspeciales += '\n- Improntas';
    }

    // DUPLICADO DE LICENCIA DE TRANSITO
    if (tramiteContiene(['DUPLICADO DE LICENCIA DE TRANSITO'])) {
      necesitaGenerales = true;
      if (esDepto) requisitosEspeciales += '\n- Improntas';
    }

    // CANCELACION DE CUENTA
    if (tramiteContiene(['CANCELACION DE CUENTA'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Certificado de vehiculo no recuperado expedido por la Fiscalia';
    }

    // MATRICULA INICIAL
    if (tramiteContiene(['MATRICULA INICIAL'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas\n- Factura de compra\n- Manifiesto de importacion';
    }

    // CERTIFICADO DE TRADICION (no lleva generales)
    if (tramiteContiene(['CERTIFICADO DE TRADICION'])) {
      requisitosEspeciales += '\n- Copia de la tarjeta de propiedad';
    }

    // CAMBIO DE MOTOR
    if (tramiteContiene(['CAMBIO DE MOTOR'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas';
      requisitosEspeciales += '\n- Factura de compra con trazabilidad (si es nuevo)';
      requisitosEspeciales += '\n- Manifiesto de importacion (si es nuevo)';
      requisitosEspeciales += '\n- Certificado de tradicion del vehiculo al cual pertenecia el motor (si es usado)';
      requisitosEspeciales += '\n- Certificado de tradicion del vehiculo en el cual se va a instalar el motor (si es usado)';
      requisitosEspeciales += '\n- Contrato de compraventa del motor (si es usado)';
      requisitosEspeciales += '\n- Certificado de revision expedido por la SIJIN';
    }

    // REGRABACION DE MOTOR
    if (tramiteContiene(['REGRABACION DE MOTOR'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas\n- Certificado de revision expedido por la SIJIN';
    }

    // REGRABACION DE CHASIS
    if (tramiteContiene(['REGRABACION DE CHASIS'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas\n- Certificado de revision expedido por la SIJIN';
    }

    // REGRABACION DE SERIE
    if (tramiteContiene(['REGRABACION DE SERIE'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas\n- Certificado de revision expedido por la SIJIN';
    }

    // CAMBIO DE COLOR
    if (tramiteContiene(['CAMBIO DE COLOR'])) {
      necesitaGenerales = true;
      requisitosEspeciales += '\n- Improntas\n- Carta de solicitud de cambio de color';
    }

    // Agregar generales UNA sola vez al inicio si algún trámite los requiere
    if (necesitaGenerales) {
      requisitosEspeciales = '\n- Formulario\n- Contrato de mandato\n- Copia documento de identidad Propietario' + requisitosEspeciales;
    }

    var autenticacionTexto = '';
    var munAuth = antMunicipioActual.toUpperCase();
    var reglasAuth = AUTENTICACION[munAuth];
    if (reglasAuth) {
      var reglaAuth = hayTraspaso() ? reglasAuth.traspaso : reglasAuth.otro;
      if (reglaAuth) {
        var docsAuth = reglaAuth.propietario || [];
        var docsCompradorAuth = reglaAuth.comprador || [];
        var notaAuth = reglaAuth.nota_especial || '';
        var lineasAuth = [];
        if (docsAuth.length > 0) lineasAuth.push('- Propietario debe autenticar: ' + docsAuth.join(' + ').toUpperCase());
        if (docsCompradorAuth.length > 0) lineasAuth.push('- Comprador debe autenticar: ' + docsCompradorAuth.join(' + ').toUpperCase());
        if (notaAuth) lineasAuth.push('- ' + notaAuth);
        if (lineasAuth.length > 0) autenticacionTexto = '\n\n*AUTENTICACION:*\n' + lineasAuth.join('\n');
      }
    }

    // Notas -- las predeterminadas (configurables desde el panel) + notas
    // personalizadas del usuario. La nota de "no ponga precio en la compra
    // venta" solo aplica cuando uno de los tramites es Traspaso de Propiedad.
    // La nota de "traslado de cuenta" solo aplica cuando uno de los
    // tramites es Traslado de Cuenta.
    var hayTraspasoPropiedad = tramiteContiene(['TRASPASO DE PROPIEDAD']);
    var hayTrasladoCuenta = tramiteContiene(['TRASLADO DE CUENTA']);
    var notasConfig = (window.tramyProfile && window.tramyProfile.settings && window.tramyProfile.settings.notas)
      ? window.tramyProfile.settings.notas : null;
    var notasActivas = (notasConfig && Array.isArray(notasConfig.activas)) ? notasConfig.activas : ['firmas', 'precio_compraventa', 'traslado_cuenta'];
    var notasPersonalizadas = (notasConfig && Array.isArray(notasConfig.personalizadas)) ? notasConfig.personalizadas : [];

    var lineasNotas = [];
    if(notasActivas.indexOf('firmas') >= 0){
      lineasNotas.push('- NO olvide firmas y huellas en todos los documentos.');
    }
    if(notasActivas.indexOf('precio_compraventa') >= 0 && hayTraspasoPropiedad){
      lineasNotas.push('- No ponga precio en la compra venta. En caso de tener que ponerlo puede usar el precio del avaluo.');
    }
    if(notasActivas.indexOf('traslado_cuenta') >= 0 && hayTrasladoCuenta){
      lineasNotas.push('- Por favor, marque la casilla de traslado y escriba el municipio de destino en el formulario. Es muy importante hacerlo para evitar contratiempos.');
    }
    notasPersonalizadas.forEach(function(n){
      if(n && n.trim()) lineasNotas.push('- ' + n.trim());
    });
    var notasTexto = lineasNotas.length > 0 ? ('*NOTAS:*\n' + lineasNotas.join('\n') + '\n\n') : '';

    // Datos del RUNT (SOAT, RTM, limitaciones) -- solo se agregan si
    // efectivamente se consulto el RUNT para este vehiculo (Premium).
    var textoRuntLiq = '';
    var elSoatLiq = document.getElementById('ant-soat');
    var elRtmLiq = document.getElementById('ant-rtm');
    var elLimitacionesLiq = document.getElementById('ant-limitaciones-propiedad');
    if(elSoatLiq && elSoatLiq.value){
      var lineasRunt = [];
      lineasRunt.push('SOAT ' + elSoatLiq.value);
      if(elRtmLiq && elRtmLiq.value) lineasRunt.push('RTM ' + elRtmLiq.value);
      if(elLimitacionesLiq && elLimitacionesLiq.value){
        var hayLimitacion = elLimitacionesLiq.value !== 'Sin limitaciones registradas';
        lineasRunt.push('Limitaciones ' + (hayLimitacion ? 'Sí' : 'No'));
      }
      textoRuntLiq = lineasRunt.join('\n') + '\n\n';
    }

    // Datos de negocio del usuario logueado (si los tiene configurados en su panel)
    var perfilNegocio = (window.tramyProfile && window.tramyProfile.settings) ? window.tramyProfile.settings : null;
    var encabezadoNegocio = '';
    if(perfilNegocio && perfilNegocio.business_name){
      encabezadoNegocio = '*' + perfilNegocio.business_name + '*';
      if(perfilNegocio.slogan) encabezadoNegocio += '\n' + perfilNegocio.slogan;
      if(perfilNegocio.contact_info) encabezadoNegocio += '\n' + perfilNegocio.contact_info;
      encabezadoNegocio += '\n\n';
    }

    var textoWA = encabezadoNegocio
      + (encabezadoNegocio ? '' : 'Liquidacion realizada por Tramy App\nhttps://tramy.app/\n\n')
      + tituloLiq + '\n\n'
      + '*LIQUIDACION*\n'
      + lineasLiq + '\n'
      + 'TOTAL: $' + total.toLocaleString('es-CO') + '\n\n'
      + '*REQUISITOS:*'
      + requisitosEspeciales
      + autenticacionTexto + '\n\n'
      + notasTexto
      + textoRuntLiq
      + (encabezadoNegocio ? encabezadoNegocio.replace(/\n\n$/, '') : 'Liquidacion realizada por Tramy App\nhttps://tramy.app/');

    var esMovil = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    if (esMovil && navigator.share) {
      navigator.share({title: tituloCompleto, text: textoWA})
        .catch(function(){ window.open('https://wa.me/?text='+encodeURIComponent(textoWA),'_blank'); });
    } else {
      var btnWA = document.getElementById('ant-btn-wa');
      function confirmarCopiado() {
        if (btnWA) {
          var orig = btnWA.innerHTML;
          btnWA.innerHTML = 'Texto copiado! Pega en WhatsApp';
          setTimeout(function(){ btnWA.innerHTML = orig; }, 3000);
        }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(textoWA).then(confirmarCopiado).catch(function() {
          var ta = document.createElement('textarea');
          ta.value = textoWA;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          confirmarCopiado();
        });
      } else {
        var ta = document.createElement('textarea');
        ta.value = textoWA;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        confirmarCopiado();
      }
    }
  };

  // ── NUEVA LIQUIDACION ────────────────────────────────────────────────────
  window.antNuevaLiquidacion = function() {
    document.documentElement.scrollTop = 0;
    window.location.reload();
    return;
    // Limpiar todo y volver al estado inicial
    limpiarCampos();
    antMunicipioActual = '';
    ocrLeido = false;
    infoConfirmada = false;
    antAvaluo = 0;
    antRetAvaluo = 0;
    antRetRetefuente = 0;

    // Ocultar todos los bloques excepto info
    ['bloque-depto','bloque-municipal','bloque-tramites','bloque-retefuente'].forEach(function(id) {
      var bl = document.getElementById(id);
      if (bl) { bl.style.display='none'; bl.classList.remove('visible'); }
    });
    var blLiq = document.getElementById('bloque-liq');
    if (blLiq) blLiq.style.cssText = 'display:none !important';
    var blRet = document.getElementById('bloque-retefuente');
    if (blRet) { blRet.style.display='none'; blRet.classList.remove('visible'); }

    // Mostrar y expandir bloque info
    var blInfo = document.getElementById('bloque-info');
    if (blInfo) { blInfo.style.display='block'; blInfo.classList.add('visible'); }
    var contInfo = document.getElementById('contenido-info');
    if (contInfo) contInfo.style.display='block';
    var chevInfo = document.getElementById('ant-info-chevron');
    if (chevInfo) chevInfo.textContent = '▲';

    // Mostrar bienvenida
    document.getElementById('ant-bienvenida').style.display = 'block';
    if (window.tramyVehiculosGuardados && window.tramyVehiculosGuardados.length) { var vp = document.getElementById('tramyVehiculosPanel'); if (vp) vp.style.display = 'block'; }
    document.getElementById('ant-info-expandido').style.display = 'block';
    document.getElementById('ant-info-colapsado').style.display = 'none';

    // Mostrar zona OCR y botones de entrada
    document.getElementById('ant-zona-ocr').style.display = 'block';
    document.getElementById('ant-ocr-zone').style.display = 'block';
    document.getElementById('ant-preview-wrap').style.display = 'none';
    document.getElementById('ant-ocr-status').style.display = 'none';
    var entradaBtns = document.querySelector('.ant-entrada-btns');
    if (entradaBtns) entradaBtns.style.display = 'flex';

    // Limpiar liquidacion
    limpiarLiq();

    // Ocultar placa mini
    var placaMini = document.getElementById('ant-placa-mini');
    if (placaMini) placaMini.style.display = 'none';

    // Scroll al inicio
    window.scrollTo({top: 0, behavior: 'smooth'});
  };

  // ── REPORTE ──────────────────────────────────────────────────────────────
  var antReporteTipo = '';

  window.antToggleReporte = function() {
    var panel = document.getElementById('ant-reporte-panel');
    panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
    document.getElementById('ant-reporte-ok').style.display = 'none';
    document.getElementById('ant-reporte-texto').value = '';
    document.querySelectorAll('.ant-reporte-opcion').forEach(function(el){ el.classList.remove('sel'); });
    antReporteTipo = '';
  };

  window.antSelOpcion = function(el, tipo) {
    document.querySelectorAll('.ant-reporte-opcion').forEach(function(e){ e.classList.remove('sel'); });
    el.classList.add('sel');
    antReporteTipo = tipo;
  };

  window.antEnviarReporte = function() {
    if (!antReporteTipo) { alert('Selecciona qué está pasando.'); return; }
    var comentario  = document.getElementById('ant-reporte-texto').value.trim();
    var placaEl     = document.getElementById('ant-placa');
    var placa       = placaEl ? placaEl.value.trim() : '';
    var tipoGuardar = antReporteTipo; // guardar antes de resetear

    // Enviar primero
    fetch(ANT_API + '/reportar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        tipo:       tipoGuardar,
        comentario: comentario,
        placa:      placa,
        municipio:  antMunicipioActual || '',
        pagina:     window.location.href
      })
    }).catch(function(){});

    // Mostrar confirmación inmediatamente
    antReporteTipo = '';
    document.getElementById('ant-reporte-ok').style.display = 'block';
    setTimeout(function(){
      document.getElementById('ant-reporte-panel').style.display = 'none';
      document.getElementById('ant-reporte-ok').style.display = 'none';
    }, 1500);
  };

})();
</script>

</body>
</html>
