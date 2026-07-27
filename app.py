import base64, re, io
from PIL import Image
import pytesseract
import os
import psycopg2
import re
import time
import uuid
import json
import requests
import threading
import boto3
from botocore.config import Config
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter
from flask_cors import CORS

app = Flask(__name__)  # v54.1
CORS(app, resources={r"/*": {"origins": "*"}})

TIMEOUT = 10000
MSG_NO_MATRICULADO = "El vehiculo no se encuentra matriculado en la Secretaria de Movilidad"
AÑO_ACTUAL = str(datetime.now().year)

TWOCAPTCHA_API_KEY = os.environ.get("TWOCAPTCHA_API_KEY", "")

# --- Cloudflare R2 (almacenamiento de documentos generados, ej. FUN) ---
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "")  # ej: https://docs.tramy.app

def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

def subir_a_r2(ruta_local, nombre_archivo_remoto, content_type="application/pdf", nombre_descarga=None):
    """Sube un archivo a R2 y devuelve la URL publica de descarga.
    El bucket debe tener acceso publico de lectura habilitado (o un dominio
    personalizado conectado) para que la URL funcione directo en el navegador.
    Si se da 'nombre_descarga', el navegador sugiere ese nombre al guardar
    el archivo (no el nombre interno/tecnico usado en la URL)."""
    cliente = _r2_client()
    extra_args = {"ContentType": content_type}
    if nombre_descarga:
        extra_args["ContentDisposition"] = f'inline; filename="{nombre_descarga}"'
    cliente.upload_file(
        ruta_local, R2_BUCKET_NAME, nombre_archivo_remoto,
        ExtraArgs=extra_args
    )
    return f"{R2_PUBLIC_BASE_URL}/{nombre_archivo_remoto}"


EMTRASUR_SITE_KEY  = "6Leshn4sAAAAAIas9tkeW3vKPg0a4uYqw-7fG7Pn"
EMTRASUR_URL       = "https://sistematizacion.emtrasur.com.co/"
ANTIOQUIA_SITE_KEY = "0x4AAAAAACJy_BR2tRNN1cnv"
ANTIOQUIA_URL      = "https://www.vehiculosantioquia.com.co/impuestosweb/#/public"
ANTIOQUIA_API      = "https://www.vehiculosantioquia.com.co/raiz-backimpuestosweb/backimpuestosweb"

# ============================================================
#  TABLA DE TIPOS DE DOCUMENTO ANTIOQUIA
# ============================================================
ANTIOQUIA_TIPOS_DOCUMENTO = {
    "1":  {"abreviatura": "CC",    "nombre": "Cédula de Ciudadanía"},
    "8":  {"abreviatura": "CD",    "nombre": "Carnet Diplomático"},
    "5":  {"abreviatura": "CE",    "nombre": "Cédula de Extranjería"},
    "2":  {"abreviatura": "NIT",   "nombre": "NIT"},
    "4":  {"abreviatura": "PASAP", "nombre": "Pasaporte"},
    "29": {"abreviatura": "PPT",   "nombre": "Permiso por protección temporal"},
    "7":  {"abreviatura": "RC",    "nombre": "Registro Civil"},
    "6":  {"abreviatura": "TI",    "nombre": "Tarjeta de Identidad"},
}

# Mapa de abreviatura entrante → id numérico
ANTIOQUIA_TIPO_DOC_MAP = {
    "CC": "1", "NIT": "2", "PASAP": "4", "CE": "5",
    "TI": "6", "RC": "7", "CD": "8", "PPT": "29"
}

ANTIOQUIA_LIMITE_VIGENCIAS = 20


def get_db_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def job_actualizar(job_id, mensaje, estado='procesando', datos_parciales=None):
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        if datos_parciales is not None:
            cur.execute("""
                INSERT INTO consulta_jobs (job_id, estado, mensaje, resultado, actualizado_en)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (job_id) DO UPDATE SET estado=%s, mensaje=%s, resultado=%s, actualizado_en=NOW()
            """, (job_id, estado, mensaje, json.dumps({"parcial": datos_parciales}),
                  estado, mensaje, json.dumps({"parcial": datos_parciales})))
        else:
            cur.execute("""
                INSERT INTO consulta_jobs (job_id, estado, mensaje, actualizado_en)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (job_id) DO UPDATE SET estado=%s, mensaje=%s, actualizado_en=NOW()
            """, (job_id, estado, mensaje, estado, mensaje))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Error job: {e}")

def job_terminar(job_id, resultado):
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE consulta_jobs SET estado='listo', mensaje='Consulta finalizada.', resultado=%s, actualizado_en=NOW()
            WHERE job_id=%s
        """, (json.dumps(resultado), job_id))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Error job terminar: {e}")

def job_error(job_id, mensaje_error):
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE consulta_jobs SET estado='error', mensaje=%s, actualizado_en=NOW()
            WHERE job_id=%s
        """, (mensaje_error, job_id))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Error job error: {e}")


# ============================================================
#  CACHE IMPUESTOS ANTIOQUIA
# ============================================================

def cache_antioquia_buscar(placa):
    """Busca PAZ_Y_SALVO en caché para el año actual."""
    try:
        anio_actual = datetime.now().year
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT estado, total_pagar, avaluo_comercial, retefuente, vigencia
            FROM cache_impuestos_antioquia
            WHERE placa = %s AND vigencia = %s AND estado = 'PAZ_Y_SALVO'
              AND (expira_en IS NULL OR expira_en >= NOW())
            ORDER BY creado_en DESC LIMIT 1
        """, (placa.upper(), str(anio_actual)))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {
                "estado":     row[0],
                "total":      row[1] or 0,
                "avaluo":     row[2] or 0,
                "retefuente": row[3] or 0,
                "vigencia":   row[4],
            }
        return None
    except Exception as e:
        print(f"Error cache buscar: {e}")
        return None


def cache_antioquia_buscar_vigencia(placa, anio):
    """Busca el valor cacheado de una vigencia específica con deuda."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT total_pagar, avaluo_comercial, retefuente
            FROM cache_impuestos_antioquia
            WHERE placa = %s AND vigencia = %s AND estado = 'CON_DEUDA'
              AND (expira_en IS NULL OR expira_en >= NOW())
            ORDER BY creado_en DESC LIMIT 1
        """, (placa.upper(), int(anio)))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {"total_pagar": row[0] or 0, "avaluo": row[1] or 0, "retefuente": row[2] or 0}
        return None
    except Exception as e:
        print(f"Error cache buscar vigencia: {e}")
        return None


def cache_antioquia_eliminar_vigencia(placa, anio):
    """Elimina del caché una vigencia que ya fue pagada."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            DELETE FROM cache_impuestos_antioquia
            WHERE placa = %s AND vigencia = %s AND estado = 'CON_DEUDA'
        """, (placa.upper(), int(anio)))
        conn.commit()
        cur.close(); conn.close()
        print(f"  → Caché eliminado para {placa} vigencia {anio} (fue pagada)")
    except Exception as e:
        print(f"Error cache eliminar vigencia: {e}")


def cache_antioquia_guardar_paz_salvo(placa, avaluo, estado_veh):
    """Guarda en caché que la placa está a paz y salvo hasta fin de año."""
    try:
        anio_actual = datetime.now().year
        expira = f"{anio_actual}-12-31"
        retefuente = round(avaluo / 100) if avaluo else 0
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO cache_impuestos_antioquia
                (placa, vigencia, total_pagar, avaluo_comercial, retefuente, estado, expira_en, creado_en)
            VALUES (%s, %s, 0, %s, %s, 'PAZ_Y_SALVO', %s, NOW())
            ON CONFLICT (placa, vigencia) DO UPDATE SET
                total_pagar=0, avaluo_comercial=EXCLUDED.avaluo_comercial,
                retefuente=EXCLUDED.retefuente, estado='PAZ_Y_SALVO',
                expira_en=EXCLUDED.expira_en, actualizado_en=NOW()
        """, (placa.upper(), str(anio_actual), avaluo or 0, retefuente, expira))
        conn.commit()
        cur.close(); conn.close()
        print(f"  → Caché guardado PAZ_Y_SALVO para {placa}")
    except Exception as e:
        print(f"Error cache guardar paz y salvo: {e}")


def guardar_estado_cuenta_antioquia(placa, data3):
    """Guarda TODOS los datos de la consulta (estadoCuenta, historial de
    declaraciones, procesos fiscales, bloqueos, novedades) para poder
    generar despues el documento Estado de Cuenta sin tener que volver a
    consultar. Se llama cada vez que un vehiculo sale a paz y salvo."""
    try:
        estado_veh = data3.get("estadoCuenta", {}) or {}
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO estado_cuenta_antioquia
                (placa, numero_certificado, valor_certificado, periodo_inicio, periodo_fin,
                 estado_cuenta_json, lista_detalle_pagos, lista_proceso_fiscal, lista_bloqueo,
                 novedades, actualizado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (placa) DO UPDATE SET
                numero_certificado=EXCLUDED.numero_certificado,
                valor_certificado=EXCLUDED.valor_certificado,
                periodo_inicio=EXCLUDED.periodo_inicio,
                periodo_fin=EXCLUDED.periodo_fin,
                estado_cuenta_json=EXCLUDED.estado_cuenta_json,
                lista_detalle_pagos=EXCLUDED.lista_detalle_pagos,
                lista_proceso_fiscal=EXCLUDED.lista_proceso_fiscal,
                lista_bloqueo=EXCLUDED.lista_bloqueo,
                novedades=EXCLUDED.novedades,
                actualizado_en=NOW()
        """, (
            placa.upper(),
            estado_veh.get("numeroCertificadoSap"),
            estado_veh.get("valorEstadoCuenta"),
            estado_veh.get("periodoInicioCertificacion"),
            estado_veh.get("periodoFinCertificacion"),
            json.dumps(estado_veh, ensure_ascii=False, default=str),
            json.dumps(data3.get("listaDetallePagos", []), ensure_ascii=False, default=str),
            json.dumps(data3.get("listaProcesoFiscal", []), ensure_ascii=False, default=str),
            json.dumps(data3.get("listaBloqueo", []), ensure_ascii=False, default=str),
            json.dumps(data3.get("novedades", []), ensure_ascii=False, default=str),
        ))
        conn.commit()
        cur.close(); conn.close()
        print(f"  → Estado de Cuenta guardado para {placa}")
    except Exception as e:
        print(f"Error guardando estado de cuenta: {e}")


def cache_antioquia_guardar_deuda(placa, vigencias_data, avaluo):
    """Guarda en caché vigencias con deuda.
    - Vigencia año actual antes del 1 agosto: expira el 31 de julio
    - Vigencia año actual desde 1 agosto, y vigencias anteriores: expira en 2 meses
    """
    try:
        ahora       = datetime.now()
        anio_actual = ahora.year
        conn = get_db_conn()
        cur  = conn.cursor()
        retefuente = round(avaluo / 100) if avaluo else 0

        for vig in vigencias_data:
            anio_vig   = int(vig.get('vigencia', 0))
            total      = vig.get('total_pagar', 0) or 0

            # Calcular expiración según reglas
            es_anio_actual    = (anio_vig == anio_actual)
            antes_de_agosto   = ahora.month < 8  # antes del 1 de agosto

            if es_anio_actual and antes_de_agosto:
                expira = f"{anio_actual}-07-31 23:59:59"
            else:
                # 2 meses desde ahora
                mes_exp  = ahora.month + 2
                anio_exp = anio_actual
                if mes_exp > 12:
                    mes_exp  -= 12
                    anio_exp += 1
                expira = f"{anio_exp}-{mes_exp:02d}-{ahora.day:02d} 23:59:59"

            expira_date = expira[:10]  # solo YYYY-MM-DD para columna date
            cur.execute("""
                INSERT INTO cache_impuestos_antioquia
                    (placa, vigencia, total_pagar, avaluo_comercial, retefuente, estado, expira_en, creado_en)
                VALUES (%s, %s, %s, %s, %s, 'CON_DEUDA', %s, NOW())
                ON CONFLICT (placa, vigencia) DO UPDATE SET
                    total_pagar=EXCLUDED.total_pagar,
                    avaluo_comercial=EXCLUDED.avaluo_comercial,
                    retefuente=EXCLUDED.retefuente,
                    estado='CON_DEUDA',
                    expira_en=EXCLUDED.expira_en,
                    actualizado_en=NOW()
            """, (placa.upper(), int(anio_vig), total, avaluo or 0, retefuente, expira_date))

        conn.commit()
        cur.close(); conn.close()
        print(f"  → Caché CON_DEUDA guardado para {placa}: {[v.get('vigencia') for v in vigencias_data]}")
    except Exception as e:
        print(f"Error cache guardar deuda: {e}")


# ============================================================
#  CACHE IMPUESTOS MUNICIPALES (Envigado, Sabaneta, Itagui, Bello,
#  La Estrella, Medellin, etc.) -- mismo principio que el cache de
#  Antioquia: si una placa esta a paz y salvo, lo esta hasta fin de
#  año, asi que no hace falta volver a consultar la pagina del
#  municipio (que es una consulta lenta via Playwright).
# ============================================================

def cache_municipal_buscar(placa, municipio):
    """Busca PAZ_Y_SALVO en cache municipal para el año actual."""
    try:
        anio_actual = datetime.now().year
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT fecha_pago, marca_pago, valor_pago, placa_vista
            FROM cache_impuestos_municipales
            WHERE placa = %s AND municipio = %s AND vigencia = %s AND estado = 'PAZ_Y_SALVO'
              AND (expira_en IS NULL OR expira_en >= NOW())
            ORDER BY creado_en DESC LIMIT 1
        """, (placa.upper(), municipio.lower(), str(anio_actual)))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {"fecha_pago": row[0] or "", "marca": row[1] or "", "valor_pago": row[2] or "", "placa_vista": row[3] or ""}
        return None
    except Exception as e:
        print(f"Error cache municipal buscar: {e}")
        return None


def cache_municipal_guardar_paz_salvo(placa, municipio, fecha_pago, marca, valor_pago, placa_vista):
    """Guarda en cache que la placa esta a paz y salvo en ese municipio hasta fin de año."""
    try:
        anio_actual = datetime.now().year
        expira = f"{anio_actual}-12-31"
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO cache_impuestos_municipales
                (placa, municipio, vigencia, estado, fecha_pago, marca_pago, valor_pago, placa_vista, expira_en, creado_en)
            VALUES (%s, %s, %s, 'PAZ_Y_SALVO', %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (placa, municipio, vigencia) DO UPDATE SET
                estado='PAZ_Y_SALVO', fecha_pago=EXCLUDED.fecha_pago,
                marca_pago=EXCLUDED.marca_pago, valor_pago=EXCLUDED.valor_pago,
                placa_vista=EXCLUDED.placa_vista, expira_en=EXCLUDED.expira_en,
                actualizado_en=NOW()
        """, (placa.upper(), municipio.lower(), str(anio_actual), fecha_pago or '', marca or '', valor_pago or '', placa_vista or '', expira))
        conn.commit()
        cur.close(); conn.close()
        print(f"  → Cache municipal guardado PAZ_Y_SALVO para {placa} en {municipio}")
    except Exception as e:
        print(f"Error cache municipal guardar: {e}")


def resolver_captcha_imagen_2captcha(imagen_base64, intentos=3):
    """Resuelve un captcha de imagen simple (texto distorsionado) con 2Captcha.
    A diferencia de resolver_recaptcha_2captcha (que usa 'userrecaptcha'/'turnstile'
    con un sitekey), esto manda la imagen directamente y 2Captcha devuelve el texto
    que un humano leeria en ella. Se usa para el captcha del RUNT."""
    ultimo_error = None
    for intento in range(intentos):
        try:
            resp = requests.post("https://2captcha.com/in.php", data={
                "key": TWOCAPTCHA_API_KEY, "method": "base64",
                "body": imagen_base64, "json": 1,
            }, timeout=15)
            data = resp.json()
            if data.get("status") != 1:
                raise Exception(f"2captcha error: {data.get('request')}")
            captcha_id = data["request"]

            for _ in range(24):  # hasta 2 minutos (24 x 5s)
                time.sleep(5)
                resp2 = requests.get("https://2captcha.com/res.php", params={
                    "key": TWOCAPTCHA_API_KEY, "action": "get", "id": captcha_id, "json": 1,
                }, timeout=15)
                data2 = resp2.json()
                if data2.get("status") == 1:
                    return data2["request"]
                if data2.get("request") != "CAPCHA_NOT_READY":
                    raise Exception(f"2captcha error: {data2.get('request')}")

            raise Exception("2captcha timeout esperando solucion")
        except Exception as e:
            ultimo_error = e
            print(f"  → Intento {intento+1} de captcha imagen fallo: {e}")
    raise ultimo_error


RUNT_URL = "https://portalpublico.runt.gov.co/#/consulta-vehiculo/consulta/consulta-ciudadana"
RUNT_TIPO_DOC_MAP = {
    "CC": "Cédula Ciudadanía", "CE": "Cédula Extranjería", "NIT": "NIT",
    "PASAP": "Pasaporte", "TI": "Tarjeta Identidad", "PPT": "Permiso por Protección Temporal",
}


def _runt_seleccionar_mat_select(page, form_control, texto_opcion):
    """Los <select> de Angular Material no son <select> normales -- hay que
    hacer click para abrir el desplegable y luego click en la opcion deseada."""
    page.click(f'mat-select[formcontrolname="{form_control}"]')
    page.click(f'mat-option:has-text("{texto_opcion}")')


def consultar_runt_vehiculo(page, placa, cedula, tipo_documento="CC", job_id=None):
    """Consulta 'Placa y Propietario' en el RUNT. Devuelve un dict con los
    campos ya organizados segun el esquema de la tabla 'vehiculos', mas un
    sub-dict 'persona' si el RUNT tambien confirmo datos basicos del
    propietario en esta misma consulta."""
    if job_id:
        job_actualizar(job_id, "Abriendo el RUNT...", "procesando")

    page.goto(RUNT_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_selector('input[formcontrolname="placa"]', timeout=30000)

    # Procedencia (Nacional) y Consultar Por (Placa y Propietario) ya vienen
    # seleccionados por defecto -- no hace falta tocarlos.
    page.fill('input[formcontrolname="placa"]', placa.upper())

    if tipo_documento != "CC":
        # "Cedula Ciudadania" es el default, solo se cambia si es otro tipo
        texto = RUNT_TIPO_DOC_MAP.get(tipo_documento, "Cédula Ciudadanía")
        _runt_seleccionar_mat_select(page, "tipoDocumento", texto)

    page.fill('input[formcontrolname="documento"]', cedula)

    if job_id:
        job_actualizar(job_id, "Resolviendo captcha...", "procesando")

    # Reintenta hasta 3 veces si el captcha resulta incorrecto (el RUNT
    # regenera la imagen cada vez que falla).
    for intento_captcha in range(3):
        img_src = page.get_attribute('img.img-responsive.img-fluid', 'src')
        imagen_base64 = img_src.split(',', 1)[1]  # quitar el prefijo "data:image/png;base64,"

        texto_captcha = resolver_captcha_imagen_2captcha(imagen_base64)

        page.fill('input[formcontrolname="captcha"]', texto_captcha)

        if job_id:
            job_actualizar(job_id, "Consultando informacion...", "procesando")

        page.click('button[type="submit"]')

        try:
            page.wait_for_selector(
                'cyrconsultavehiculo-info-vehiculo-detallada, .mat-error, .swal2-popup',
                timeout=20000
            )
        except Exception:
            pass

        # Si el captcha estaba mal, el RUNT normalmente muestra un mensaje
        # de error (swal2) y limpia el campo -- reintentamos con una imagen nueva.
        error_captcha = page.query_selector('.swal2-popup:has-text("captcha")') \
                     or page.query_selector('.swal2-popup:has-text("Captcha")')
        if error_captcha:
            page.click('.swal2-confirm') if page.query_selector('.swal2-confirm') else None
            continue

        break

    # Si el RUNT muestra cualquier otro error (ej. "los datos registrados
    # no corresponden con los propietarios activos"), se propaga el mensaje
    # real en vez de seguir intentando adivinar por que fallo.
    error_popup = page.query_selector('.swal2-popup')
    if error_popup:
        texto_error = error_popup.inner_text().strip()
        if texto_error:
            if page.query_selector('.swal2-confirm'):
                page.click('.swal2-confirm')
            raise Exception(texto_error)

    # Los paneles de SOAT, RTM, garantias, etc. cargan sus datos con
    # peticiones asincronas separadas, despues de que aparece el bloque
    # principal. Si leemos el texto antes de que esas peticiones terminen,
    # esos campos salen vacios aunque el panel ya este expandido. Se espera
    # a que la red quede inactiva (sin peticiones pendientes) antes de seguir.
    if job_id:
        job_actualizar(job_id, "Esperando a que carguen todas las secciones...", "procesando")

    try:
        page.wait_for_load_state("networkidle", timeout=25000)
    except Exception:
        pass

    # Por si ademas hay paneles genuinamente colapsados (no solo cargando),
    # los desplegamos tambien.
    if job_id:
        job_actualizar(job_id, "Desplegando secciones del resultado...", "procesando")

    for _ in range(3):
        headers_colapsados = page.query_selector_all('mat-expansion-panel-header[aria-expanded="false"]')
        for header in headers_colapsados:
            try:
                header.click()
                page.wait_for_timeout(300)
            except Exception:
                pass
        page.wait_for_timeout(400)

    if job_id:
        job_actualizar(job_id, "Extrayendo datos...", "procesando")

    return _parsear_resultado_runt_vehiculo(page)


def _extraer_tarjetas_runt(page):
    """Lee directamente el HTML (no el texto visual) de cada <mat-card> de
    la pagina de resultados, devolviendo un diccionario {etiqueta: valor}
    por cada tarjeta. Esto es inmune a que el CSS reordene visualmente las
    etiquetas y los valores. Revisa tanto <p> como <div> como contenedor,
    y tanto <strong> como <b> como marcador de etiqueta, porque el RUNT usa
    una combinacion distinta segun la seccion (Info General usa <p><strong>,
    Datos Tecnicos usa <p><b>, RTM usa <div><strong>)."""
    return page.evaluate("""
        () => {
            const tarjetas = [];
            document.querySelectorAll('mat-card').forEach(card => {
                const campos = {};
                card.querySelectorAll('p, div').forEach(el => {
                    const marcador = el.querySelector(':scope > strong, :scope > b');
                    if (marcador) {
                        const label = marcador.innerText.replace(/:\\s*$/, '').trim();
                        const value = el.innerText.slice(marcador.innerText.length).trim();
                        if (label) campos[label] = value;
                    }
                });
                card.querySelectorAll('div.col-12').forEach(div => {
                    const labs = div.querySelectorAll('label');
                    if (labs.length >= 2) {
                        const label = labs[0].innerText.replace(/:\\s*$/, '').trim();
                        const value = labs[1].innerText.trim();
                        if (label) campos[label] = value;
                    }
                });
                const titulo = card.querySelector('mat-card-title');
                if (titulo) campos['_titulo'] = titulo.innerText.trim();
                if (Object.keys(campos).length > 0) tarjetas.push(campos);
            });
            return tarjetas;
        }
    """)


def _extraer_resumen_runt(page):
    """La franja superior (placa, estado del vehiculo, tipo de servicio,
    clase de vehiculo) no vive dentro de ninguna <mat-card> -- son pares de
    <label>Etiqueta:</label> y <b>Valor</b> como hermanos dentro de un
    mismo '.row'. Se emparejan por posicion dentro de cada fila."""
    return page.evaluate("""
        () => {
            const resumen = {};
            document.querySelectorAll('.row').forEach(row => {
                const labels = Array.from(row.querySelectorAll(':scope > div > label'));
                const valores = Array.from(row.querySelectorAll(':scope > div.show-grande > b'));
                if (labels.length > 0 && labels.length === valores.length) {
                    labels.forEach((lab, i) => {
                        const key = lab.innerText.replace(/:\\s*$/, '').trim();
                        resumen[key] = valores[i].innerText.trim();
                    });
                }
            });
            return resumen;
        }
    """) or {}


def _parsear_resultado_runt_vehiculo(page):
    tarjetas = _extraer_tarjetas_runt(page)
    resumen = _extraer_resumen_runt(page)

    # Se combinan todos los campos de todas las tarjetas en un diccionario
    # plano para leerlos facil. Algunas tarjetas (Info General) tienen un
    # solo campo cada una; otras (Datos Tecnicos) traen varios campos juntos
    # en una sola tarjeta. Las tarjetas que se repiten (SOAT, RTM, cada
    # poliza historica) tambien quedan aqui, pero no importa que se
    # sobreescriban entre si porque esos campos se leen aparte, directo de
    # la lista `tarjetas`, no de este diccionario plano.
    plano = dict(resumen)
    for t in tarjetas:
        for k, v in t.items():
            if k != "_titulo":
                plano[k] = v

    plano_lower = {k.lower(): v for k, v in plano.items()}

    def campo(nombre):
        return plano_lower.get(nombre.lower(), "")

    datos = {
        "marca": campo("Marca"),
        "linea": campo("Línea"),
        "modelo": campo("Modelo"),
        "color": campo("Color"),
        "clase": campo("Clase de vehículo"),
        "servicio": campo("Tipo de servicio"),
        "numero_serie": campo("Número de serie"),
        "numero_motor": campo("Número de motor"),
        "numero_chasis": campo("Número de chasis"),
        "vin": campo("Número de VIN"),
        "cilindrada": campo("Cilindraje"),
        "carroceria": campo("Tipo de carrocería"),
        "combustible": campo("Tipo Combustible"),
        "autoridad_transito": campo("Autoridad de tránsito"),
        "puertas": campo("Puertas"),
        "capacidad_carga": campo("Capacidad de Carga"),
        "peso_bruto_vehicular": campo("Peso Bruto Vehicular"),
        "capacidad_pasajeros": campo("Capacidad de Pasajeros"),
        "pasajeros_sentados": campo("Pasajeros Sentados"),
        "numero_ejes": campo("Número de Ejes"),
        "estado_vehiculo": campo("Estado del vehículo"),
        "gravamenes_propiedad": campo("Gravámenes a la propiedad").upper() == "SI",
        "fecha_matricula_inicial": _convertir_fecha_ddmmyyyy(campo("Fecha de Matricula Inicial")),
    }

    # SOAT vigente: primera tarjeta con "Número de póliza" cuyo Estado diga VIGENTE
    datos["soat_vigente"] = False
    for t in tarjetas:
        if "Número de póliza" in t:
            estado = t.get("Estado", "").upper()
            if "VIGENTE" in estado and "NO VIGENTE" not in estado:
                datos["soat_vigente"] = True
                datos["soat_fecha_fin"] = _convertir_fecha_ddmmyyyy(t.get("Fecha fin de vigencia", ""))
                break

    # RTM vigente: tarjeta "REVISION TECNICO-MECANICO" con Vigente = SI
    datos["rtm_vigente"] = False
    for t in tarjetas:
        if t.get("_titulo", "").upper().startswith("REVISION TECNICO"):
            if t.get("Vigente", "").upper() == "SI":
                datos["rtm_vigente"] = True
                datos["rtm_fecha_fin"] = _convertir_fecha_ddmmyyyy(t.get("Fecha Vigencia", ""))
                break

    # Ultimo tramite relevante (no SOAT ni RTM) -- primera tarjeta "Solicitud NNN"
    for t in tarjetas:
        if t.get("_titulo", "").startswith("Solicitud"):
            tramites = t.get("Trámites Realizados", "")
            if tramites and "revision tecnico mecanica" not in tramites.lower() and "soat" not in tramites.lower():
                datos["ultimo_tramite_tipo"] = tramites.strip(", ")
                datos["ultimo_tramite_fecha"] = _convertir_fecha_ddmmyyyy(t.get("Fecha de Solicitud", ""))
                datos["ultimo_tramite_estado"] = t.get("Estado", "")
                datos["ultimo_tramite_entidad"] = t.get("Entidad", "")
                break

    # Garantias a Favor De -- solo si el acreedor esta afiliado a Confecamaras
    for t in tarjetas:
        if "Acreedor" in t and "Identificación Acreedor" in t:
            datos["garantia_favor_acreedor"] = t.get("Acreedor", "")
            datos["garantia_favor_entidad_nit"] = t.get("Identificación Acreedor", "").replace("NIT", "").strip()
            datos["garantia_favor_fecha_inscripcion"] = _convertir_fecha_ddmmyyyy(t.get("Fecha Inscripción", ""))
            break

    # Garantias Mobiliarias -- hasta 2 registros (inscripcion / levantamiento),
    # se distinguen por el texto libre del campo "Estado".
    for t in tarjetas:
        if "ID Prenda" in t:
            estado_texto = t.get("Estado", "").lower()
            prefijo = "garantia_levantamiento_" if "levantamiento" in estado_texto else "garantia_inscripcion_"
            datos[prefijo + "id_prenda"] = t.get("ID Prenda", "")
            datos[prefijo + "entidad"] = t.get("Entidad", "")
            datos[prefijo + "entidad_nit"] = t.get("Identificación Entidad", "").replace("NIT", "").strip()
            datos[prefijo + "fecha"] = _convertir_fecha_ddmmyyyy(t.get("Fecha de Registro", ""))

    # Limitaciones a la Propiedad (embargo, hurto, etc.) -- distinto de
    # Prenda/Garantias Mobiliarias. Solo se guarda la mas reciente/vigente.
    # Nombres de columnas confirmados por el CSS real del componente
    # (fechaExpedicion, fechaRadicacion, noDocumento, departamento,
    # municipio) -- se prueban varias variantes de texto por si acaso.
    for t in tarjetas:
        titulo_lower = t.get("_titulo", "").lower()
        if "limitacion" in titulo_lower:
            datos["limitacion_tipo"] = t.get("Tipo de Limitación", "") or t.get("Tipo", "")
            datos["limitacion_numero_oficio"] = (
                t.get("Número de Documento", "") or t.get("No. de Documento", "")
                or t.get("Número de Oficio", "") or t.get("No. Oficio", ""))
            datos["limitacion_entidad"] = t.get("Entidad", "")
            datos["limitacion_departamento"] = t.get("Departamento", "")
            datos["limitacion_municipio"] = t.get("Municipio", "")
            datos["limitacion_fecha_oficio"] = _convertir_fecha_ddmmyyyy(
                t.get("Fecha de Expedición", "") or t.get("Fecha Expedición", "") or t.get("Fecha de Expedición del Oficio", ""))
            datos["limitacion_fecha_registro"] = _convertir_fecha_ddmmyyyy(
                t.get("Fecha de Radicación", "") or t.get("Fecha Radicación", "") or t.get("Fecha de Registro", ""))
            break


    datos["placa"] = campo("PLACA DEL VEHÍCULO").upper()

    # --- DIAGNOSTICO TEMPORAL (quitar despues de confirmar los nombres reales) ---
    datos["_debug_tarjetas_limitacion"] = [t for t in tarjetas if "limitacion" in t.get("_titulo", "").lower()]
    datos["_debug_titulos_tarjetas"] = [t.get("_titulo", "") for t in tarjetas if t.get("_titulo")]
    # --- FIN DIAGNOSTICO TEMPORAL ---

    return datos


def _convertir_fecha_ddmmyyyy(fecha_str):
    """Convierte 'dd/mm/yyyy' (formato del RUNT) a 'yyyy-mm-dd' (formato de
    Postgres), o None si el texto viene vacio."""
    fecha_str = (fecha_str or "").strip()
    if not fecha_str:
        return None
    try:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    except Exception:
        return None


def guardar_vehiculo_runt(datos):
    """Guarda (o actualiza) los datos de un vehiculo consultado en el RUNT.
    El RUNT siempre marca fuente='RUNT' y sobrescribe cualquier dato previo
    que hubiera venido solo de una lectura por OCR."""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # Los campos "_debug_*" son solo para diagnostico en pantalla, no
        # corresponden a columnas reales de la tabla.
        columnas = [k for k in datos.keys() if k != "placa" and not k.startswith("_debug")]
        columnas.append("fuente")
        set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in columnas)
        cols_sql = ", ".join(["placa"] + columnas + ["leido_en"])
        vals_sql = ", ".join(["%s"] * (len(columnas) + 2))
        valores = [datos["placa"]] + [datos.get(c) for c in columnas[:-1]] + ["RUNT"] + [datetime.now()]
        cur.execute(f"""
            INSERT INTO vehiculos ({cols_sql})
            VALUES ({vals_sql})
            ON CONFLICT (placa) DO UPDATE SET {set_clause}, leido_en=EXCLUDED.leido_en
        """, valores)
        conn.commit()
        cur.close(); conn.close()
        print(f"  → Vehiculo RUNT guardado: {datos['placa']}")
    except Exception as e:
        print(f"Error guardando vehiculo RUNT: {e}")


import unicodedata
import subprocess
import shutil
from openpyxl.styles import PatternFill, Alignment, Border, Side
import openpyxl as _openpyxl
import copy

# --- Generador de FUN (Formulario Unico Nacional) ---
# La plantilla debe subirse al repositorio junto a app.py, con este mismo
# nombre exacto ("AppJX.xlsm"), en el mismo directorio.
FUN_PLANTILLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AppJX.xlsm")
DECLARACION_MANUAL_PLANTILLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DECLARACION_MANUAL_DE_IMPUESTOS_DEPARTAMENTALES.xlsx")

VERDE_MARCA = PatternFill(start_color="92D050", end_color="92D050", fill_type="solid")

# Cada opcion marca DOS celdas: el numero/casilla y la etiqueta de texto,
# para que la seleccion se vea claramente (no solo el numero).
CELDAS_TRAMITE = {
    "MATRICULA/ REGISTRO": ("A7", "B7"), "TRASPASO": ("E7", "F7"),
    "TRASLADO MATRICULA / REGISTRO": ("I7", "J7"), "RADICADO  MATRICULA / REGISTRO": ("N7", "O7"),
    "CAMBIO DE COLOR": ("Q7", "R7"), "CAMBIO DE SERVICIO": ("T7", "U7"),
    "REGRABAR MOTOR": ("A9", "B9"), "REGRABAR CHASIS": ("E9", "F9"), "TRANSFORMACION": ("I9", "J9"),
    "DUPLICADO LICENCIA TRANSITO": ("N9", "O9"), "INSCRIPC. PRENDA": ("Q9", "R9"), "LEVANTA PRENDA": ("T9", "U9"),
    "CANCELACION MATRICULA / REGISTRO": ("A12", "B12"), "CAMBIO DE PLACAS": ("E12", "F12"),
    "DUPLICADO DE PLACAS": ("I12", "J12"), "REMATRICULA": ("N12", "O12"),
    "CAMBIO DE CARROCERIA": ("Q12", "R12"),
}
# "OTROS" ya no vive aqui -- se marca aparte, solo cuando hay traslado (ver mas abajo)
CELDA_OTROS_TRAMITE = ("T12", "U12")

CELDAS_CLASE = {
    "AUTOMOVIL": ("A17", "A16"), "BUS": ("D17", "D16"), "BUSETA": ("H17", "H16"),
    "CAMION": ("L17", "L16"), "CAMIONETA": ("O17", "O16"), "CAMPERO": ("P17", "P16"),
    "MICROBUS": ("S17", "S16"), "TRACTOCAMION": ("A19", "A18"), "MOTOCICLETA": ("D19", "D18"),
    "MOTOCARRO": ("H19", "H18"), "MOTOTRICICLO": ("L19", "L18"), "CUATRIMOTO": ("O19", "O18"),
    "VOLQUETA": ("P19", "P18"), "OTRO": ("S19", "S18"),
}
CELDAS_COMBUSTIBLE = {
    "GASOLINA": ("AC8", "AC7"), "DIESEL": ("AE8", "AE7"), "GAS": ("AF8", "AF7"),
    "MIXTO": ("AG8", "AG7"), "ELECTRICO": ("AH8", "AH7"), "HIDROGENO": ("AI8", "AI7"),
    "ETANOL": ("AJ8", "AJ7"), "BIODIESEL": ("AK8", "AK7"),
}
CELDAS_SERVICIO = {
    "PARTICULAR": ("AE29", "AE28"), "PUBLICO": ("AF29", "AF28"), "DIPLOMATICO": ("AG29", "AG28"),
    "OFICIAL": ("AH29", "AH28"), "ESPECIAL": ("AI29", "AI28"), "OTROS": ("AJ29", "AJ28"),
}
CELDAS_REFERENCIA_SIMPLE = {
    "AJ3": "placa", "W7": "marca", "Z7": "linea", "W10": "color",
    "AG10": "modelo", "AI10": "cilindrada", "W13": "capacidad",
    "AE17": "numero_motor", "W19": "carroceria", "AE19": "numero_chasis",
    "AE22": "numero_serie", "AE24": "vin",
    "A24": "propietario_primer_apellido", "I24": "propietario_segundo_apellido",
    "P24": "propietario_nombres", "S26": "propietario_documento",
    "A29": "propietario_direccion", "M29": "propietario_ciudad", "S29": "propietario_telefono",
    "A37": "comprador_primer_apellido", "I37": "comprador_segundo_apellido",
    "P37": "comprador_nombres", "S41": "comprador_documento",
    "A44": "comprador_direccion", "M44": "comprador_ciudad", "S44": "comprador_telefono",
    "AG41": "traslado_municipio",
}


def _fun_normalizar(texto):
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _fun_coincide(valor_tramy, etiqueta_formulario):
    """Compara por PALABRA COMPLETA (no por 'contiene'), para que por ejemplo
    'GAS' no haga match por accidente dentro de 'GASOLINA'."""
    a, b = _fun_normalizar(valor_tramy), _fun_normalizar(etiqueta_formulario)
    if not a or not b:
        return False
    if a == b:
        return True
    return re.search(r"\b" + re.escape(b) + r"\b", a) is not None


def _fun_marcar_checkboxes(ws, mapa_celdas, valor_tramy):
    """Marca TODAS las opciones que coincidan (no solo la primera) -- un
    vehiculo de combustible dual (ej. 'GASOLINA Y GAS') debe marcar ambas."""
    if not valor_tramy:
        return
    for etiqueta, celdas in mapa_celdas.items():
        if _fun_coincide(valor_tramy, etiqueta):
            for celda in celdas:
                ws[celda].fill = VERDE_MARCA


def generar_fun(datos, ruta_salida_pdf):
    """Genera el FUN diligenciado en PDF a partir de la plantilla Excel real
    (FORMULARIO + EXPORTAR), con las casillas marcadas en verde."""
    wb = _openpyxl.load_workbook(FUN_PLANTILLA, data_only=False, keep_vba=True)
    exportar = wb["EXPORTAR"]
    formulario = wb["FORMULARIO"]

    for row in formulario.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "[1]EXPORTAR!" in cell.value:
                cell.value = cell.value.replace("[1]EXPORTAR!", "EXPORTAR!")
            elif isinstance(cell.value, str) and "[1]DATOS!" in cell.value:
                cell.value = cell.value.replace("[1]DATOS!", "DATOS!")

    exportar["D8"] = datos.get("propietario_nombres", "")
    exportar["D9"] = datos.get("propietario_primer_apellido", "")
    exportar["D10"] = datos.get("propietario_segundo_apellido", "")
    exportar["D11"] = datos.get("propietario_documento", "")
    exportar["D12"] = datos.get("propietario_direccion", "")
    exportar["D13"] = datos.get("propietario_ciudad", "")
    exportar["D14"] = datos.get("propietario_telefono", "")
    exportar["D16"] = datos.get("comprador_nombres", "")
    exportar["D17"] = datos.get("comprador_primer_apellido", "")
    exportar["D18"] = datos.get("comprador_segundo_apellido", "")
    exportar["D19"] = datos.get("comprador_documento", "")
    exportar["D20"] = datos.get("comprador_direccion", "")
    exportar["D21"] = datos.get("comprador_ciudad", "")
    exportar["D22"] = datos.get("comprador_telefono", "")
    exportar["D27"] = datos.get("placa", "")
    exportar["D28"] = datos.get("servicio", "")
    exportar["D29"] = datos.get("clase", "")
    exportar["D30"] = datos.get("marca", "")
    exportar["D31"] = datos.get("linea", "")
    exportar["D32"] = datos.get("modelo", "")
    exportar["D33"] = datos.get("color", "")
    exportar["D34"] = datos.get("numero_serie", "")
    exportar["D35"] = datos.get("numero_motor", "")
    exportar["D36"] = datos.get("numero_chasis", "")
    exportar["D37"] = datos.get("cilindrada", "")
    exportar["D38"] = datos.get("carroceria", "")
    exportar["D39"] = datos.get("combustible", "")
    exportar["D40"] = datos.get("autoridad_transito", "")
    exportar["D41"] = datos.get("capacidad", "")
    exportar["D42"] = datos.get("vin", "")
    exportar["D43"] = "SI" if datos.get("gravamenes_propiedad") else "NO"
    exportar["D44"] = datos.get("fecha_matricula_inicial", "")
    exportar["D47"] = datos.get("tramite", "")
    exportar["D51"] = datos.get("traslado_municipio", "")

    formulario["AC2"] = datos.get("autoridad_transito", "")
    formulario["AC2"].alignment = Alignment(horizontal="center", vertical="center")
    formulario["AA4"] = datos.get("municipio", "")

    for celda, clave in CELDAS_REFERENCIA_SIMPLE.items():
        if not datos.get(clave):
            formulario[celda] = ""

    _fun_marcar_checkboxes(formulario, CELDAS_TRAMITE, datos.get("tramite", ""))
    _fun_marcar_checkboxes(formulario, CELDAS_CLASE, datos.get("clase", ""))
    _fun_marcar_checkboxes(formulario, CELDAS_COMBUSTIBLE, datos.get("combustible", ""))
    _fun_marcar_checkboxes(formulario, CELDAS_SERVICIO, datos.get("servicio", ""))

    # "OTROS" (en Tramite Solicitado) NO depende del tramite elegido -- se
    # marca unica y exclusivamente cuando hay un traslado de cuenta.
    if datos.get("traslado_municipio"):
        for celda in CELDA_OTROS_TRAMITE:
            formulario[celda].fill = VERDE_MARCA

    formulario["A51"] = ""  # pie de pagina "Juridicox.com..." -- se quita

    hojas_a_conservar = {"FORMULARIO", "EXPORTAR", "DATOS"}
    for nombre in list(wb.sheetnames):
        if nombre not in hojas_a_conservar:
            del wb[nombre]
    formulario.sheet_state = "visible"
    wb.active = wb.sheetnames.index("FORMULARIO")

    formulario.print_area = "A1:AY47"
    formulario.page_setup.orientation = "landscape"
    formulario.page_setup.paperSize = formulario.PAPERSIZE_LETTER
    formulario.page_setup.scale = 100

    id_temp = str(uuid.uuid4())[:8]
    ruta_xlsm_temp = f"/tmp/_fun_{id_temp}.xlsm"
    wb.save(ruta_xlsm_temp)

    subprocess.run([
        "soffice", "--headless", "--convert-to", "pdf",
        "--outdir", os.path.dirname(ruta_salida_pdf), ruta_xlsm_temp
    ], check=True, timeout=90)

    generado = os.path.join(os.path.dirname(ruta_salida_pdf), f"_fun_{id_temp}.pdf")
    shutil.move(generado, ruta_salida_pdf)
    os.remove(ruta_xlsm_temp)


def _moneda(valor):
    """Formatea un valor numerico como texto de moneda '$ X,XXX,XXX' para
    la declaracion manual."""
    try:
        return "$ {:,.0f}".format(float(valor))
    except (TypeError, ValueError):
        return valor


def generar_declaracion_manual_pdf(datos, ruta_salida_pdf):
    """Genera la Declaracion Manual (formulario FO-M8-P6-008) diligenciada,
    a partir de la plantilla Excel real (hojas CONTRIBUYENTE y ENTIDAD
    RECAUDADORA). 'datos' es un dict con todos los campos ya resueltos:
    datos del vehiculo, del propietario, y la liquidacion privada."""
    wb = _openpyxl.load_workbook(DECLARACION_MANUAL_PLANTILLA)

    for nombre_hoja in wb.sheetnames:
        ws = wb[nombre_hoja]

        # A. Periodo
        ws["H12"] = datos.get("vigencia", "")

        # C. Declarante
        ws["D15"] = datos.get("nombre_completo", "")
        ws["D18"] = datos.get("apellidos", "")
        ws["AZ18"] = datos.get("celular", "")
        ws["CA18"] = datos.get("telefono", "")
        ws["CO18"] = datos.get("email", "")
        ws["D21"] = datos.get("direccion", "")
        ws["BE21"] = datos.get("municipio_residencia", "")
        ws["CI21"] = datos.get("departamento_residencia", "ANTIOQUIA")
        ws["CR15"] = datos.get("numero_documento", "")
        tipo_doc = (datos.get("tipo_documento") or "").upper()
        casillas_tipo_doc = {"CC": "BM15", "NIT": "BV15", "TI": "CC15", "CE": "CH15", "OTRO": "CN15"}
        if tipo_doc in casillas_tipo_doc:
            ws[casillas_tipo_doc[tipo_doc]] = "X"

        # D. Vehiculo
        ws["D24"] = datos.get("placa", "")
        ws["Z24"] = datos.get("marca", "")
        ws["BB24"] = datos.get("linea", "")
        ws["CP24"] = datos.get("modelo", "")
        ws["D27"] = datos.get("clase", "")
        ws["AJ27"] = datos.get("carroceria", "")
        # D7 GRUPO se deja en blanco (instructivo oficial)
        ws["BZ27"] = datos.get("puertas", "")
        ws["CL27"] = datos.get("cilindraje", "")
        ws["D30"] = datos.get("capacidad_carga", "")
        ws["AJ30"] = datos.get("capacidad_pasajeros", "")
        ws["BP30"] = datos.get("municipio_matricula", "")
        ws["CL30"] = datos.get("departamento_matricula", "ANTIOQUIA")

        if datos.get("blindado"):
            ws["S33"] = "X"
        if datos.get("importado"):
            ws["AN33"] = "X"

        ws["CI35"] = datos.get("caja", "")
        ws["CY35"] = datos.get("traccion", "")

        # E. Liquidacion privada -- con formato de moneda
        ws["AF38"] = _moneda(datos.get("avaluo", 0))
        ws["AF40"] = _moneda(datos.get("impuesto", 0))
        ws["AF41"] = _moneda(datos.get("sanciones", 0))
        ws["AF42"] = _moneda(datos.get("descuentos", 0))
        ws["AF43"] = _moneda(datos.get("total_cargo_5", 0))
        ws["CJ37"] = _moneda(datos.get("total_cargo_6", 0))
        ws["CJ38"] = _moneda(datos.get("intereses_mora", 0))
        ws["CJ39"] = _moneda(datos.get("pagos_anteriores", 0))
        ws["CJ40"] = _moneda(datos.get("descuento_interes", 0))
        ws["CJ41"] = _moneda(datos.get("saldo_favor", 0))
        ws["CJ42"] = _moneda(datos.get("total_pagar", 0))

        # J. Distribucion del recaudo -- 20% Municipio, 80% Departamento,
        # calculado sobre el total a pagar (instructivo oficial, seccion J).
        total_pagar_num = datos.get("total_pagar", 0) or 0
        try:
            total_pagar_num = float(total_pagar_num)
        except (TypeError, ValueError):
            total_pagar_num = 0
        valor_municipio = round(total_pagar_num * 0.20)
        valor_departamento = total_pagar_num - valor_municipio
        ws["AE64"] = _moneda(valor_municipio)
        ws["AE66"] = _moneda(valor_departamento)

        # G. Declarante -- se deja en blanco a proposito. Se firma y se
        # diligencia a lapicero de forma manual, no se prellena.

        # Configuracion de pagina: una sola pagina por hoja, vertical.
        ws.print_area = "B3:DI82"
        ws.page_setup.orientation = "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.gridLines = False
        ws.sheet_view.showGridLines = False

        # Limpiar bordes sueltos (restos de la plantilla) que generaban
        # lineas verticales gruesas sin pertenecer a ninguna casilla real.
        sin_borde = Border()
        for coord in ["I7", "K7", "G35", "H35", "M49", "B50", "B64", "B66", "J66", "L66", "N66", "V66"]:
            ws[coord].border = sin_borde

        # D50 (G.2 Nombres y Apellidos) SI es la celda real de esa casilla
        # (no un borde suelto) -- se le restaura el contorno completo.
        borde_fino = Side(style="thin")
        ws["D50"].border = Border(top=borde_fino, bottom=borde_fino, left=borde_fino, right=borde_fino)

        # F40 ("VEHICULOS AUTOMOTORES") y F38 ("DEL VEHICULO") tenian
        # alineacion vertical sin fijar -- al agrandar sus filas el texto
        # se hundia y se veia separado de la linea de arriba.
        celda_f40 = ws["F40"]
        celda_f40.value = "VEHICULOS AUTOMOTORES"
        celda_f40.alignment = Alignment(vertical="top", horizontal=celda_f40.alignment.horizontal)
        celda_f38 = ws["F38"]
        celda_f38.alignment = Alignment(vertical="top", horizontal=celda_f38.alignment.horizontal)

        ws.row_dimensions[38].height = 14
        ws.row_dimensions[40].height = 14
        ws.row_dimensions[28].height = 13.5
        ws.row_dimensions[29].height = 1.5
        ws.row_dimensions[27].height = 16.5

        # Los numeros de renglon (1 al 5) mostraban "###" en el PDF sin
        # importar el ancho de columna -- convertirlos de numero a TEXTO
        # elimina el problema de raiz (el "###" solo le pasa a numeros).
        ws["D37"] = "1"
        ws["D39"] = "2"
        ws["D41"] = "3"
        ws["D42"] = "4"
        ws["D43"] = "5"

        # Ademas usan un color de TEMA que LibreOffice a veces interpreta
        # mal al convertir (texto invisible) -- se fija a negro explicito.
        for coord in ["D37", "D39", "D41", "D42", "D43"]:
            celda = ws[coord]
            nueva_fuente = copy.copy(celda.font)
            nueva_fuente.color = "FF000000"
            celda.font = nueva_fuente

    id_temp = str(uuid.uuid4())[:8]
    ruta_xlsx_temp = f"/tmp/_decl_manual_{id_temp}.xlsx"
    wb.save(ruta_xlsx_temp)

    subprocess.run([
        "soffice", "--headless", "--convert-to", "pdf",
        "--outdir", os.path.dirname(ruta_salida_pdf), ruta_xlsx_temp
    ], check=True, timeout=90)

    generado = os.path.join(os.path.dirname(ruta_salida_pdf), f"_decl_manual_{id_temp}.pdf")
    shutil.move(generado, ruta_salida_pdf)
    os.remove(ruta_xlsx_temp)


def _moneda_pys(valor):
    """Formatea un valor como '$\\xa0X.XXX.XXX', igual al formato que ya
    usa la plantilla PYS de AppJX.xlsm (con espacio duro y punto de miles)."""
    try:
        return "$\xa0" + "{:,.0f}".format(float(valor)).replace(",", ".")
    except (TypeError, ValueError):
        return "$\xa00"


def generar_estado_cuenta_pdf(datos, ruta_salida_pdf):
    """Genera el documento Estado de Cuenta (certificado de paz y salvo),
    a partir de la plantilla AppJX.xlsm real (hojas PYS + ESTADO DE
    CUENTA). 'datos' es un dict con: estado_veh (dict de estadoCuenta),
    lista_detalle_pagos, lista_proceso_fiscal, lista_bloqueo, novedades."""
    wb = _openpyxl.load_workbook(FUN_PLANTILLA, data_only=False, keep_vba=True)
    pys = wb["PYS"]
    edc = wb["ESTADO DE CUENTA"]

    estado_veh = datos.get("estado_veh", {}) or {}
    inicio = estado_veh.get("periodoInicioCertificacion", "")
    fin    = estado_veh.get("periodoFinCertificacion", "")

    # A22:B31 -- informacion general
    pys["B22"] = f"{inicio} a {fin}" if inicio and fin else ""
    pys["B23"] = estado_veh.get("placa", "")
    pys["B24"] = estado_veh.get("modelo", "")
    pys["B25"] = estado_veh.get("municipioMatricula", "")
    pys["B26"] = estado_veh.get("departamentoMatricula", "")
    # Fecha de expedicion -- debe ser la fecha en que REALMENTE se
    # consulto y se obtuvo este numero de certificado (guardada en
    # 'fecha_consulta'), no la fecha en que se genera el documento --
    # el numero de certificado es unico de esa consulta puntual.
    fecha_consulta = datos.get("fecha_consulta")
    pys["B27"] = fecha_consulta if fecha_consulta else datetime.now()
    pys["B28"] = estado_veh.get("marca", "")
    pys["B29"] = estado_veh.get("cilindraje", "")
    pys["B30"] = estado_veh.get("linea", "")
    pys["B31"] = estado_veh.get("capacidadCarga", "")

    # A35:J.. -- declaraciones presentadas (una fila por cada elemento)
    declaraciones = datos.get("lista_detalle_pagos", []) or []
    fila = 35
    for d in declaraciones:
        pys.cell(row=fila, column=1,  value=d.get("tipoLiquidacion", ""))
        pys.cell(row=fila, column=2,  value=d.get("formularioLiquidacion", ""))
        fecha_pago = d.get("fechaPago")
        if fecha_pago:
            try:
                pys.cell(row=fila, column=3, value=datetime.utcfromtimestamp(fecha_pago / 1000))
            except (TypeError, ValueError, OSError):
                pys.cell(row=fila, column=3, value="")
        pys.cell(row=fila, column=4,  value=_moneda_pys(d.get("impuesto", 0)))
        pys.cell(row=fila, column=5,  value=_moneda_pys(d.get("sancion", 0)))
        pys.cell(row=fila, column=6,  value=_moneda_pys(d.get("descuento", 0)))
        pys.cell(row=fila, column=7,  value=_moneda_pys(d.get("interesMora", 0)))
        pys.cell(row=fila, column=8,  value=_moneda_pys(d.get("totalPagar", 0)))
        pys.cell(row=fila, column=9,  value=_moneda_pys(d.get("avaluoComercial", 0)))
        pys.cell(row=fila, column=10, value=d.get("vigencia", ""))
        fila += 1

    # M22.. / O22.. / P22.. -- procesos fiscales, bloqueos, novedades
    procesos = datos.get("lista_proceso_fiscal", []) or []
    bloqueos = datos.get("lista_bloqueo", []) or []
    novedades = datos.get("novedades", []) or []

    for i, p in enumerate(procesos):
        texto = f"{p.get('descripcionProcesoFiscal', '')} ({p.get('vigencia', '')})"
        pys.cell(row=22 + i, column=13, value=texto)  # M
    for i, b in enumerate(bloqueos):
        texto = f"{b.get('descripcionBloqueo', '')} ({b.get('vigencia', '')})"
        pys.cell(row=22 + i, column=15, value=texto)  # O
    for i, n in enumerate(novedades):
        texto = n if isinstance(n, str) else str(n)
        pys.cell(row=22 + i, column=16, value=texto)  # P

    # "El vehiculo no presenta observaciones" solo si las 3 listas estan
    # vacias -- si hay cualquier cosa, se quita ese aviso.
    if procesos or bloqueos or novedades:
        edc["A74"] = ""

    # Certificado No. -- se usa el numero real que entrega la Gobernacion
    # en esta consulta puntual (cambia cada vez que se consulta).
    edc["AG5"] = estado_veh.get("numeroCertificadoSap", "")

    hojas_a_conservar = {"PYS", "ESTADO DE CUENTA"}
    for nombre in list(wb.sheetnames):
        if nombre not in hojas_a_conservar:
            del wb[nombre]
    edc.sheet_state = "visible"
    wb.active = wb.sheetnames.index("ESTADO DE CUENTA")

    id_temp = str(uuid.uuid4())[:8]
    ruta_xlsm_temp = f"/tmp/_edc_{id_temp}.xlsm"
    wb.save(ruta_xlsm_temp)

    subprocess.run([
        "soffice", "--headless", "--convert-to", "pdf",
        "--outdir", os.path.dirname(ruta_salida_pdf), ruta_xlsm_temp
    ], check=True, timeout=90)

    generado = os.path.join(os.path.dirname(ruta_salida_pdf), f"_edc_{id_temp}.pdf")
    shutil.move(generado, ruta_salida_pdf)
    os.remove(ruta_xlsm_temp)


def bloquear_recursos(page):
    page.route("**/*", lambda route: route.abort()
               if route.request.resource_type in ["image", "stylesheet", "font", "media", "other"]
               else route.continue_())


def resolver_recaptcha_2captcha(site_key, page_url, intentos=3):
    ultimo_error = None
    for intento in range(intentos):
        try:
            resp = requests.post("https://2captcha.com/in.php", data={
                "key": TWOCAPTCHA_API_KEY, "method": "userrecaptcha",
                "googlekey": site_key, "pageurl": page_url, "json": 1,
            }, timeout=15)
            data = resp.json()
            if data.get("status") != 1:
                raise Exception(f"2captcha error: {data.get('request')}")
            captcha_id = data["request"]
            for _ in range(24):
                time.sleep(5)
                resultado = requests.get("https://2captcha.com/res.php", params={
                    "key": TWOCAPTCHA_API_KEY, "action": "get", "id": captcha_id, "json": 1,
                }, timeout=10).json()
                if resultado.get("status") == 1:
                    return resultado["request"]
                if resultado.get("request") not in ("CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"):
                    raise Exception(f"2captcha error: {resultado.get('request')}")
            raise Exception("2captcha tardo demasiado.")
        except Exception as e:
            ultimo_error = e
            if "IP_BANNED" in str(e) and intento < intentos - 1:
                time.sleep(3)
                continue
            raise
    raise ultimo_error


def resolver_turnstile_2captcha(site_key, page_url, intentos=3):
    ultimo_error = None
    for intento in range(intentos):
        try:
            resp = requests.post("https://2captcha.com/in.php", data={
                "key": TWOCAPTCHA_API_KEY, "method": "turnstile",
                "sitekey": site_key, "pageurl": page_url, "json": 1,
            }, timeout=15)
            data = resp.json()
            if data.get("status") != 1:
                raise Exception(f"2captcha error: {data.get('request')}")
            captcha_id = data["request"]
            for _ in range(24):
                time.sleep(5)
                resultado = requests.get("https://2captcha.com/res.php", params={
                    "key": TWOCAPTCHA_API_KEY, "action": "get", "id": captcha_id, "json": 1,
                }, timeout=10).json()
                if resultado.get("status") == 1:
                    return resultado["request"]
                if resultado.get("request") not in ("CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"):
                    raise Exception(f"2captcha error: {resultado.get('request')}")
            raise Exception("2captcha tardo demasiado.")
        except Exception as e:
            ultimo_error = e
            if "IP_BANNED" in str(e) and intento < intentos - 1:
                time.sleep(3)
                continue
            raise
    raise ultimo_error


# ============================================================
#  MUNICIPIOS (sin tocar)
# ============================================================
def consultar_envigado(page, placa):
    url = "https://movilidad.envigado.gov.co/portal-servicios/#/impuesto-local"
    page.goto(url, wait_until="domcontentloaded")
    page.get_by_role("textbox", name="Placa").fill(placa)
    page.get_by_role("button", name="Buscar").click()
    page.wait_for_function("""() => {
        const texto = document.body.innerText;
        const tabla = document.querySelector('#tablaCollapseVigencias');
        const noMatriculado = texto.includes('El vehiculo no se encuentra matriculado en la Secretaria de Movilidad');
        // Paz y salvo: esperar que la tabla tenga al menos una fila con dato real
        const pazYSalvoHeader = texto.includes('Último pago realizado');
        const pazYSalvoConDatos = pazYSalvoHeader && document.querySelectorAll('table tr td').length >= 3;
        return tabla || noMatriculado || pazYSalvoConDatos;
    }""", timeout=TIMEOUT)
    if page.get_by_text(MSG_NO_MATRICULADO).is_visible():
        return [], 0

    # Espera extra para que Angular termine de renderizar
    page.wait_for_timeout(1500)
    texto_pagina = page.inner_text("body")

    # Verificar en el DOM real si existe Y ES VISIBLE la tabla de vigencias
    # pendientes. La tabla #tablaCollapseVigencias SIEMPRE existe en el DOM
    # (Angular la renderiza vacía), solo se oculta con ng-hide en el div
    # contenedor cuando no hay deuda — por eso hay que chequear visibilidad
    # real (is_visible), no solo presencia (.count() > 0).
    try:
        tiene_vigencias_pendientes = page.locator("#tablaCollapseVigencias").is_visible()
    except Exception:
        tiene_vigencias_pendientes = False

    # Paz y salvo — extraer datos de la tabla #tablaUltimosPagos
    if 'Último pago realizado' in texto_pagina and not tiene_vigencias_pendientes:
        try:
            page.wait_for_selector("#tablaUltimosPagos tbody tr td", timeout=5000)
        except Exception:
            pass
        fecha_pago = ""
        marca_veh  = ""
        placa_veh  = ""
        try:
            fila = page.locator("#tablaUltimosPagos tbody tr").first
            placa_veh  = (fila.locator("td[data-label='Placa']").inner_text() or "").strip()
            marca_veh  = (fila.locator("td[data-label='Marca']").inner_text() or "").strip()
            fecha_pago = (fila.locator("td[data-label='Fecha pago']").inner_text() or "").strip()
        except Exception:
            pass
        return [{
            "vigencia":       "PAZ Y SALVO",
            "estado":         f"Vehículo a paz y salvo en el Tránsito de Envigado. Último pago: {fecha_pago}".strip(". "),
            "total_vigencia": 0,
            "paz_y_salvo":    True,
            "fecha_pago":     fecha_pago,
            "marca":          marca_veh,
            "placa_info":     placa_veh,
        }], 0

    if page.locator("#selectall").is_visible():
        page.locator("#selectall").check()

    # Extraer datos de último pago aunque haya deuda (verificación anti-falso-positivo)
    placa_ult = ""; marca_ult = ""; fecha_ult = ""; valor_ult = ""
    try:
        fila_ult = page.locator("#tablaUltimosPagos tbody tr").first
        placa_ult  = (fila_ult.locator("td[data-label='Placa']").inner_text() or "").strip()
        marca_ult  = (fila_ult.locator("td[data-label='Marca']").inner_text() or "").strip()
        fecha_ult  = (fila_ult.locator("td[data-label='Fecha pago']").inner_text() or "").strip()
        valor_ult  = (fila_ult.locator("td[data-label='Valor pago']").inner_text() or "").strip()
    except Exception:
        pass

    registros = []
    filas = page.locator("#tablaCollapseVigencias tr").all()
    for fila in filas:
        texto_fila = fila.inner_text().strip()
        if not texto_fila:
            continue
        año = re.search(r'\b(20\d{2})\b', texto_fila)
        montos = re.findall(r'\$\s*[\d.]+', texto_fila)
        if año and montos:
            valor_str = montos[-1].replace('$', '').replace(' ', '').replace('.', '')
            try:
                registros.append({
                    'vigencia': año.group(), 'estado': 'Pendiente de pago',
                    'total_vigencia': int(valor_str),
                    'placa_ultimo_pago': placa_ult,
                    'marca_ultimo_pago': marca_ult,
                    'fecha_ultimo_pago': fecha_ult,
                    'valor_ultimo_pago': valor_ult,
                })
            except ValueError:
                pass
    total = sum(r['total_vigencia'] for r in registros)
    return registros, total


def consultar_sabaneta(page, placa):
    url = "https://transitosabaneta.utsetsa.com/#/impuesto-local"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.locator("#placa").wait_for(state="visible", timeout=15000)
    page.locator("#placa").fill(placa)
    page.get_by_role("button", name="Buscar").click()
    page.wait_for_timeout(20000)
    texto_pagina = page.inner_text("body")
    html_pagina  = page.content()
    if MSG_NO_MATRICULADO in texto_pagina:
        return [], 0
    if 'Último pago realizado' in texto_pagina and 'Vigencias pendientes' not in texto_pagina:
        placa_sab = ""; marca_sab = ""; fecha_sab = ""; valor_sab = ""
        try:
            fila = page.locator("#tablaUltimosPagos tbody tr").first
            celdas = fila.locator("td").all()
            texts = [c.inner_text().strip() for c in celdas]
            # Orden: Placa, Marca, Fecha pago, Valor pago
            if len(texts) > 0: placa_sab = texts[0]
            if len(texts) > 1: marca_sab = texts[1]
            if len(texts) > 2: fecha_sab = texts[2]
            if len(texts) > 3: valor_sab = texts[3]
        except Exception:
            pass
        return [{
            "vigencia":       "PAZ Y SALVO",
            "estado":         "Vehículo a paz y salvo en el Tránsito de Sabaneta.",
            "total_vigencia": 0,
            "paz_y_salvo":    True,
            "placa_info":     placa_sab,
            "marca":          marca_sab,
            "fecha_pago":     fecha_sab,
            "valor_pago":     valor_sab,
        }], 0
    if 'Vigencias pendientes' not in texto_pagina:
        return [], 0
    page.locator("#tablaCollapseVigencias").wait_for(state="visible", timeout=15000)
    checkbox = page.locator("#selectall")
    checkbox.wait_for(state="visible", timeout=15000)
    if checkbox.is_enabled():
        checkbox.check()
    page.wait_for_timeout(5000)
    spans_cop = page.locator("span.fs-16.ng-binding").all()
    total = 0
    for span in spans_cop[::-1]:
        texto = span.inner_text().strip()
        if "COP" in texto and texto != "COP 0":
            valor_str = texto.replace("COP", "").replace(".", "").strip()
            try:
                total = int(valor_str)
                break
            except ValueError:
                pass
    # Extraer datos de último pago aunque haya deuda (sirven para verificar
    # que el scraper realmente consultó ESTE vehículo y no un falso positivo)
    placa_ult = ""; marca_ult = ""; fecha_ult = ""; valor_ult = ""
    try:
        fila_ult = page.locator("#tablaUltimosPagos tbody tr").first
        celdas_ult = fila_ult.locator("td").all()
        texts_ult = [c.inner_text().strip() for c in celdas_ult]
        if len(texts_ult) > 0: placa_ult = texts_ult[0]
        if len(texts_ult) > 1: marca_ult = texts_ult[1]
        if len(texts_ult) > 2: fecha_ult = texts_ult[2]
        if len(texts_ult) > 3: valor_ult = texts_ult[3]
    except Exception:
        pass

    registros = []
    filas = page.locator("#tablaCollapseVigencias tr").all()
    for fila in filas:
        texto_fila = fila.inner_text().strip()
        if not texto_fila:
            continue
        año = re.search(r'\b(20\d{2})\b', texto_fila)
        montos = re.findall(r'COP\s*[\d.]+', texto_fila)
        if año and montos:
            valor_fila = montos[-1].replace('COP', '').replace(' ', '').replace('.', '')
            try:
                registros.append({
                    'vigencia': año.group(), 'estado': 'Pendiente de pago',
                    'total_vigencia': int(valor_fila),
                    'placa_ultimo_pago': placa_ult,
                    'marca_ultimo_pago': marca_ult,
                    'fecha_ultimo_pago': fecha_ult,
                    'valor_ultimo_pago': valor_ult,
                })
            except ValueError:
                pass
    return registros, total


def consultar_itagui(page, placa):
    url = "https://movilidad.transitoitagui.gov.co/portal-servicios/#/impuesto-local"
    page.goto(url, wait_until="domcontentloaded")
    page.get_by_role("textbox", name="Placa").fill(placa)
    page.get_by_role("button", name="Buscar").click()
    page.wait_for_function("""() => {
        const texto = document.body.innerText;
        const noMatriculado = texto.includes('El vehiculo no se encuentra matriculado en la Secretaria de Movilidad');
        const conDeuda = texto.includes('Vigencias pendientes');
        const pazYSalvo = texto.includes('Último pago realizado') && !texto.includes('Vigencias pendientes');
        return noMatriculado || conDeuda || pazYSalvo;
    }""", timeout=20000)
    texto_pagina = page.inner_text("body")
    if MSG_NO_MATRICULADO in texto_pagina:
        return [], 0

    # Paz y salvo — extraer datos de verificación (placa/marca/fecha) igual que Envigado
    if 'Vigencias pendientes' not in texto_pagina and AÑO_ACTUAL in texto_pagina:
        try:
            page.wait_for_selector("#tablaUltimosPagos tbody tr td", timeout=5000)
        except Exception:
            pass
        placa_veh = ""; marca_veh = ""; fecha_pago = ""
        try:
            fila = page.locator("#tablaUltimosPagos tbody tr").first
            placa_veh  = (fila.locator("td[data-label='Placa']").inner_text() or "").strip()
            marca_veh  = (fila.locator("td[data-label='Marca']").inner_text() or "").strip()
            fecha_pago = (fila.locator("td[data-label='Fecha pago']").inner_text() or "").strip()
        except Exception:
            pass
        return [{
            "vigencia":       "PAZ Y SALVO",
            "estado":         f"Vehículo a paz y salvo en el Tránsito de Itagüí. Último pago: {fecha_pago}".strip(". "),
            "total_vigencia": 0,
            "paz_y_salvo":    True,
            "fecha_pago":     fecha_pago,
            "marca":          marca_veh,
            "placa_info":     placa_veh,
        }], 0

    page.locator("#tablaCollapseVigencias").wait_for(state="visible", timeout=15000)
    checkbox = page.locator("#selectall")
    checkbox.wait_for(state="visible", timeout=15000)
    if checkbox.is_enabled():
        checkbox.check()
    page.wait_for_timeout(3000)
    spans_cop = page.locator("span.fs-16.ng-binding").all()
    total = 0
    for span in spans_cop[::-1]:
        texto = span.inner_text().strip()
        if "COP" in texto and texto != "COP 0":
            valor_str = texto.replace("COP", "").replace(".", "").strip()
            try:
                total = int(valor_str)
                break
            except ValueError:
                pass

    # Extraer datos de último pago aunque haya deuda (verificación anti-falso-positivo)
    placa_ult = ""; marca_ult = ""; fecha_ult = ""; valor_ult = ""
    try:
        fila_ult = page.locator("#tablaUltimosPagos tbody tr").first
        placa_ult = (fila_ult.locator("td[data-label='Placa']").inner_text() or "").strip()
        marca_ult = (fila_ult.locator("td[data-label='Marca']").inner_text() or "").strip()
        fecha_ult = (fila_ult.locator("td[data-label='Fecha pago']").inner_text() or "").strip()
        valor_ult = (fila_ult.locator("td[data-label='Valor pago']").inner_text() or "").strip()
    except Exception:
        pass

    registros = []
    filas = page.locator("#tablaCollapseVigencias tr").all()
    for fila in filas:
        texto_fila = fila.inner_text().strip()
        if not texto_fila:
            continue
        año = re.search(r'\b(20\d{2})\b', texto_fila)
        montos = re.findall(r'COP\s*[\d.]+', texto_fila)
        if año and montos:
            valor_fila = montos[-1].replace('COP', '').replace(' ', '').replace('.', '')
            try:
                registros.append({
                    'vigencia': año.group(), 'estado': 'Pendiente de pago',
                    'total_vigencia': int(valor_fila),
                    'placa_ultimo_pago': placa_ult,
                    'marca_ultimo_pago': marca_ult,
                    'fecha_ultimo_pago': fecha_ult,
                    'valor_ultimo_pago': valor_ult,
                })
            except ValueError:
                pass
    return registros, total


def consultar_bello(page, placa):
    url = "https://serviciosdigitales.movilidadavanzadabello.com.co/portal-servicios/#/public"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function("""() => { return document.querySelectorAll('input[type="search"]').length > 0; }""", timeout=30000)
    try:
        page.get_by_role("button", name="Close").click(timeout=5000)
    except:
        pass
    page.get_by_role("searchbox", name="Placa").nth(3).fill(placa)
    page.get_by_role("button").nth(5).click()
    try:
        page.wait_for_url("**/impuesto-local", timeout=15000)
    except:
        return [], 0
    page.wait_for_timeout(10000)
    texto_pagina = page.inner_text("body")

    def _extraer_verificacion():
        """Intenta extraer placa/marca/fecha/valor del último pago para verificar
        que el sistema consultó el vehículo real (anti falso-positivo)."""
        placa_v = ""; marca_v = ""; fecha_v = ""; valor_v = ""
        try:
            fila = page.locator("#tablaUltimosPagos tbody tr").first
            if fila.count() > 0:
                placa_v = (fila.locator("td[data-label='Placa']").inner_text() or "").strip()
                marca_v = (fila.locator("td[data-label='Marca']").inner_text() or "").strip()
                fecha_v = (fila.locator("td[data-label='Fecha pago']").inner_text() or "").strip()
                valor_v = (fila.locator("td[data-label='Valor pago (COP)']").inner_text() or "").strip()
        except Exception:
            pass
        return placa_v, marca_v, fecha_v, valor_v

    if 'paz y salvo' in texto_pagina or 'No se encontraron registros' in texto_pagina:
        placa_v, marca_v, fecha_v, _ = _extraer_verificacion()
        if placa_v or marca_v or fecha_v:
            return [{
                "vigencia":       "PAZ Y SALVO",
                "estado":         f"Vehículo a paz y salvo en el Tránsito de Bello. Último pago: {fecha_v}".strip(". "),
                "total_vigencia": 0,
                "paz_y_salvo":    True,
                "fecha_pago":     fecha_v,
                "marca":          marca_v,
                "placa_info":     placa_v,
            }], 0
        return [], 0

    # La sección "Vigencias pendientes" se oculta con ng-hide (display:none)
    # cuando NO hay deuda, y Playwright's inner_text() no incluye texto oculto.
    # Por eso hay que extraer la verificación (tabla de últimos pagos, que SÍ
    # es visible siempre) ANTES de decidir si hay o no vigencias pendientes.
    placa_ult, marca_ult, fecha_ult, valor_ult = _extraer_verificacion()

    if 'Vigencias pendientes' not in texto_pagina:
        if placa_ult or marca_ult or fecha_ult:
            return [{
                "vigencia":       "PAZ Y SALVO",
                "estado":         f"Vehículo a paz y salvo en el Tránsito de Bello. Último pago: {fecha_ult}".strip(". "),
                "total_vigencia": 0,
                "paz_y_salvo":    True,
                "fecha_pago":     fecha_ult,
                "marca":          marca_ult,
                "placa_info":     placa_ult,
            }], 0
        return [], 0

    registros = []
    filas_vig = page.locator("#tablaCollapseVigencias tr").all()
    for fila in filas_vig:
        texto = fila.inner_text().strip()
        if not texto:
            continue
        año = re.search(r'\b(20\d{2})\b', texto)
        montos = re.findall(r'COP\s*[\d.]+', texto)
        if año and montos:
            valor_fila = montos[-1].replace('COP', '').replace(' ', '').replace('.', '')
            try:
                registros.append({
                    'vigencia': año.group(), 'estado': 'Pendiente de pago' if 'Pendiente' in texto else 'Desconocido',
                    'total_vigencia': int(valor_fila),
                    'placa_ultimo_pago': placa_ult,
                    'marca_ultimo_pago': marca_ult,
                    'fecha_ultimo_pago': fecha_ult,
                    'valor_ultimo_pago': valor_ult,
                })
            except ValueError:
                pass
    match_total = re.search(r'Total a pagar:\s*COP\s*([\d.]+)', texto_pagina)
    total = int(match_total.group(1).replace('.', '')) if match_total else sum(r['total_vigencia'] for r in registros)

    # Si no hay vigencias reales con deuda (registros vacío / total 0) pero sí
    # se logró extraer placa/marca/fecha del último pago, es un paz y salvo
    # verificado (esto es lo que realmente pasa en Bello 27.1: la página no
    # muestra el texto "paz y salvo", solo "Vigencias pendientes ()" vacío).
    if not registros and total == 0 and (placa_ult or marca_ult or fecha_ult):
        return [{
            "vigencia":       "PAZ Y SALVO",
            "estado":         f"Vehículo a paz y salvo en el Tránsito de Bello. Último pago: {fecha_ult}".strip(". "),
            "total_vigencia": 0,
            "paz_y_salvo":    True,
            "fecha_pago":     fecha_ult,
            "marca":          marca_ult,
            "placa_info":     placa_ult,
        }], 0

    return registros, total


def _parsear_emtrasur(data):
    registros = []
    for r in data:
        registros.append({
            "vigencia": str(r.get("AnioNoFacturado", "")),
            "estado": "Pendiente de pago",
            "total_vigencia": r.get("ValorPorFacturar", 0),
            "tipo_vehiculo": r.get("TipoVehiculo", ""),
            "ultimo_pago": r.get("AnioPagado", ""),
            "descripcion": r.get("DescripcionNoFacturada", "").strip(),
        })
    total = sum(r["total_vigencia"] for r in registros)
    return registros, total


def consultar_laestrella(page, placa):
    token = resolver_recaptcha_2captcha(EMTRASUR_SITE_KEY, EMTRASUR_URL)
    api_url = f"https://sistematizacion.emtrasur.com.co/api/Sistematizacion/{placa}"
    resp = requests.get(api_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": EMTRASUR_URL,
        "Origin": "https://sistematizacion.emtrasur.com.co",
        "X-Captcha-Token": token,
    }, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("Success"):
            return _parsear_emtrasur(data.get("Data", []))
    raise Exception(f"EMTRASUR respondio {resp.status_code}: {resp.text[:200]}")


# ============================================================
#  ANTIOQUIA — MÓDULO NUEVO
# ============================================================
def _calcular_digito_nit(nit):
    """Calcula el dígito de verificación de un NIT colombiano (algoritmo DIAN)."""
    factores = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43]
    n = str(nit).strip().replace("-", "").replace(".", "").zfill(10)
    suma = sum(int(n[::-1][i]) * factores[i] for i in range(10))
    r = suma % 11
    return 0 if r == 0 else (1 if r == 1 else 11 - r)


def _sesion_antioquia(placa, identificacion, tipo_documento_id,
                      modelo, organismo_transito, apellidos_propietario):
    """
    Abre sesión completa en Antioquia y retorna (session, token_cuestionario, data3).
    Costo: 2 Turnstiles.
    """
    try:
        token_captcha = resolver_turnstile_2captcha(ANTIOQUIA_SITE_KEY, ANTIOQUIA_URL)
    except Exception as e:
        raise Exception(f"Error resolviendo captcha inicial: {e}")

    session = requests.Session()
    session.headers.update({
        "Accept": "*/*",
        "Content-Type": "application/json",
        "captcha": token_captcha,
        "Referer": "https://www.vehiculosantioquia.com.co/impuestosweb/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36",
    })

    r1 = session.post(
        f"{ANTIOQUIA_API}/ConsultarEstadoCuentaImpAntioquia/obtenerCuestionarioEstadoCuenta",
        json={"placa": placa, "idTipoIdentificacion": tipo_documento_id, "identificacion": identificacion},
        timeout=60
    )
    try:
        data1 = r1.json()
    except Exception:
        data1 = None

    if not data1 or not isinstance(data1, dict):
        raise Exception("La placa ingresada no coincide con la identificacion del propietario. Verifica los datos e intenta de nuevo.")

    if data1.get("codigo") == 0 or (not data1.get("referencia") and data1.get("mensaje")):
        mensaje = data1.get("mensaje") or data1.get("descripcion") or "La placa ingresada no coincide con la identificacion del propietario."
        raise Exception(mensaje)

    referencia = data1.get("referencia")
    if not referencia:
        raise Exception("La placa ingresada no coincide con la identificacion del propietario. Verifica los datos e intenta de nuevo.")

    opciones_nombre = (data1.get("preguntaNombrePropietario") or {}).get("opcionesPregunta", [])
    primer_apellido = apellidos_propietario.upper().split()[0] if apellidos_propietario.strip() else ""
    nombre_encontrado = next(
        (n for n in opciones_nombre if primer_apellido in n.upper()), None
    )
    if not nombre_encontrado:
        raise Exception(f"No se encontró propietario con apellidos '{apellidos_propietario}'. Opciones: {opciones_nombre}")

    r2 = session.post(
        f"{ANTIOQUIA_API}/ConsultarEstadoCuentaImpAntioquia/validarCuestionarioEstadoCuenta",
        json={
            "placa": placa, "tipoDocumento": tipo_documento_id, "numeroDocumento": identificacion,
            "idEstadoCuenta": referencia,
            "respuestas": {
                "respuestaModelo": modelo,
                "respuestaOrganismoTransito": organismo_transito,
                "respuestaNombrePropietario": nombre_encontrado
            }
        },
        timeout=60
    )
    validacion = r2.json()
    if validacion.get("codigo") != 1:
        raise Exception(f"Cuestionario inválido: {validacion.get('descripcion')}")

    try:
        token_captcha2 = resolver_turnstile_2captcha(ANTIOQUIA_SITE_KEY, ANTIOQUIA_URL)
    except Exception as e:
        raise Exception(f"Error resolviendo segundo captcha: {e}")
    session.headers.update({"captcha": token_captcha2})

    token_cuestionario = session.cookies.get("token_cuestionario")
    if not token_cuestionario:
        raise Exception("No se pudo obtener el token de sesión.")

    r3 = session.post(
        f"{ANTIOQUIA_API}/ConsultarEstadoCuentaImpAntioquia/consultarEstadoCuentaVehiculoHomePublico",
        json={"placa": placa, "informacionDeclarante": {
            "idsolicitante": identificacion, "idTipoIdentificacion": tipo_documento_id
        }},
        headers={"Cookie": f"token_cuestionario={token_cuestionario}"},
        timeout=60
    )
    return session, token_cuestionario, r3.json()


def _consultar_vigencia_antioquia(vigencia, session, token_cuestionario,
                                   placa, identificacion, tipo_documento_id,
                                   doc_abreviatura, doc_nombre,
                                   celular, email, direccion, municipio, municipio_cod, departamento_cod):
    """
    Consulta el costo de una vigencia específica.
    Costo: 2 Turnstiles adicionales.
    """
    try:
        token_prop = resolver_turnstile_2captcha(ANTIOQUIA_SITE_KEY, ANTIOQUIA_URL)
    except Exception as e:
        raise Exception(f"Error resolviendo captcha vigencia {vigencia}: {e}")
    session.headers.update({"captcha": token_prop})

    r4 = session.post(
        f"{ANTIOQUIA_API}/UsuariosPortalAntioquia/consultarPropietarioVehiculo",
        json={"tipoDoc": doc_abreviatura, "nroDoc": identificacion, "placa": placa, "vigencia": vigencia},
        headers={"Cookie": f"token_cuestionario={token_cuestionario}"},
        timeout=60
    )
    propietario = r4.json().get("propietario", {})

    session.post(f"{ANTIOQUIA_API}/TablasTipo/obtenerTablasPropietario", json={},
                 headers={"Cookie": f"token_cuestionario={token_cuestionario}"}, timeout=60)
    session.get(f"{ANTIOQUIA_API}/UtilImpuestos/obtenerDescripcionPPST",
                headers={"Cookie": f"token_cuestionario={token_cuestionario}"}, timeout=60)
    session.post(f"{ANTIOQUIA_API}/Pagos/parametrosPago", json={},
                 headers={"Cookie": f"token_cuestionario={token_cuestionario}"}, timeout=60)
    session.get(f"{ANTIOQUIA_API}/UtilImpuestos/obtenerVigenciaMinimaAutodeclarar",
                headers={"Cookie": f"token_cuestionario={token_cuestionario}"}, timeout=60)

    try:
        token_decl = resolver_turnstile_2captcha(ANTIOQUIA_SITE_KEY, ANTIOQUIA_URL)
    except Exception as e:
        raise Exception(f"Error resolviendo captcha declaración vigencia {vigencia}: {e}")
    session.headers.update({"captcha": token_decl})
    session.cookies.clear()

    es_nit = (str(tipo_documento_id) == "2")
    if es_nit:
        declarante = {
            "idsolicitante": identificacion,
            "idtipodocumento": doc_abreviatura,
            "desctipodocument": doc_nombre,
            "nombres": propietario.get("nameOrg1", ""),
            "apellidos": "",
            "celular": celular,
            "telefono": propietario.get("celphone", celular),
            "email": email,
            "direccion": direccion, "municipio": municipio,
            "departamento": "ANTIOQUIA", "nivreclamacion": 0, "procedimiento": ""
        }
    else:
        declarante = {
            "idsolicitante": identificacion,
            "idtipodocumento": doc_abreviatura,
            "desctipodocument": doc_nombre,
            "nombres": propietario.get("nameFirst", ""),
            "apellidos": propietario.get("nameLast", ""),
            "celular": celular, "telefono": celular, "email": email,
            "direccion": direccion, "municipio": municipio,
            "departamento": "ANTIOQUIA", "nivreclamacion": 0, "procedimiento": ""
        }

    r5 = session.post(
        f"{ANTIOQUIA_API}/LiquidacionAntioquia/crearDeclaracionImpuestoAnt",
        json={
            "formularioLiquidacion": "",
            "declarante": declarante,
            "iIdliqIm": 0,
            "informacionComplementaria": {
                "idTipoDocumento": int(tipo_documento_id),
                "distribucionDepartamento": departamento_cod,
                "distribucionMunicipio": municipio_cod,
                "direccionCompleta": direccion,
                "nombreDistribucionDepartamento": "ANTIOQUIA",
                "nombreDistribucionMunicipio": municipio,
                "tipoCanalLiquidacion": 2, "tipoOpcionLiquidacion": 1
            },
            "placa": placa,
            "vigencia": [{"persl": vigencia}]
        },
        timeout=60
    )
    return r5.json()


def _antioquia_construir_documento(tipo_documento_id, doc_abreviatura, doc_nombre):
    """Arma el objeto 'documento' que pide el endpoint de aceptacion de
    terminos, con la misma forma que se ve en el request real capturado."""
    es_nit = (str(tipo_documento_id) == "2")
    return {
        "idDocumentoIdentidad": int(tipo_documento_id),
        "tipoPersona": "J" if es_nit else "N",
        "abreviatura": doc_abreviatura,
        "nombreDocumento": doc_nombre,
    }


def _antioquia_aceptar_terminos_liquidacion(session, identificacion, tipo_documento_id,
                                              doc_abreviatura, doc_nombre):
    """Acepta las 3 casillas (tratamiento de datos, terminos y condiciones,
    firma digital) que en el sitio real hay que marcar antes de que se
    habilite el boton de imprimir/descargar la declaracion sugerida."""
    body = {
        "numeroDocumento": str(identificacion),
        "documento": _antioquia_construir_documento(tipo_documento_id, doc_abreviatura, doc_nombre),
    }
    r = session.post(
        f"{ANTIOQUIA_API}/AceptacionTerminoCondiciones/insertAceptaTerminosLiquidacion",
        json=body, timeout=60
    )
    if r.status_code not in (200, 204):
        raise Exception(f"Error aceptando terminos de liquidacion: {r.status_code} {r.text[:300]}")


def _antioquia_descargar_pdf_liquidacion(session, formulario_liquidacion):
    """Pide el PDF de la declaracion sugerida ya generada. El servidor lo
    devuelve codificado en base64 dentro de un campo 'archivo'."""
    r = session.post(
        f"{ANTIOQUIA_API}/LiquidacionAntioquia/gestionarImprimirLiquidacion",
        json=formulario_liquidacion, timeout=60
    )
    if r.status_code != 200:
        raise Exception(f"Error descargando PDF de liquidacion: {r.status_code} {r.text[:300]}")
    data = r.json()
    archivo_b64 = data.get("archivo")
    if not archivo_b64:
        raise Exception(f"La respuesta no trajo el campo 'archivo': {json.dumps(data)[:300]}")
    return base64.b64decode(archivo_b64)


def _extraer_caja_traccion_declaracion(pdf_bytes):
    """Extrae 'Caja' (transmision) y 'Traccion' directamente del texto del
    PDF de la Declaracion Sugerida -- la Gobernacion los incluye ahi
    aunque no vengan en la respuesta JSON de la consulta (crearDeclaracion
    ImpuestoAnt), asi que en vez de perseguirlos por la API los leemos del
    mismo documento que ya generamos.

    IMPORTANTE: el orden en que aparecen las etiquetas D.21/D.22 varia
    segun la plantilla (a veces "D.21 CAJA ... D.22 TRACCION", otras veces
    al reves, y hasta el nombre de la etiqueta cambia). Por eso, en vez de
    depender de la posicion, se buscan directamente los VALORES conocidos
    (MT/AT/CVT para caja, 4X2/4X4 para traccion) dentro de una ventana de
    texto alrededor de esas etiquetas.

    Si no los encuentra (formato distinto, o el vehiculo no tiene esos
    datos), se devuelven vacios -- el instructivo oficial permite dejarlos
    en blanco de todas formas."""
    try:
        import io, re
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texto = ""
        for pagina in reader.pages:
            texto += (pagina.extract_text() or "") + "\n"
        texto_norm = texto.upper()

        idx21 = texto_norm.find("D.21")
        idx22 = texto_norm.find("D.22")
        indices = [i for i in (idx21, idx22) if i != -1]
        ventana = texto_norm[max(0, min(indices) - 60): min(indices) + 100] if indices else texto_norm

        match_traccion = re.search(r'\b(4X[24])', ventana)
        match_caja = re.search(r'\b(MT|AT|CVT|TM|TA)\b', ventana)

        return {
            "traccion": match_traccion.group(1) if match_traccion else "",
            "caja": match_caja.group(1) if match_caja else ""
        }
    except Exception as e:
        print(f"No se pudo extraer caja/traccion del PDF de declaracion: {e}", flush=True)
    return {"traccion": "", "caja": ""}


def antioquia_generar_pdf_declaracion(placa, identificacion, tipo_documento_abrev, vigencia,
                                       modelo, municipio_transito, apellidos_propietario,
                                       celular="3000000000", email="consulta@consulta.com",
                                       direccion="CRA", municipio="MEDELLIN",
                                       municipio_cod=5001000, departamento_cod=5):
    """Flujo completo para obtener el PDF de la declaracion sugerida (el que
    se lleva al banco), TODO dentro de la misma sesion (el numero de
    liquidacion que genera el sitio solo es valido dentro de la sesion que
    lo creo, no se puede reutilizar en una sesion nueva).
    Devuelve una tupla (pdf_bytes, data_vig) -- data_vig es la respuesta
    cruda de la liquidacion (avaluo, impuesto, sanciones, intereses, etc.),
    util para reutilizar esos mismos datos en la declaracion manual sin
    tener que volver a consultar."""
    tipo_documento_id = ANTIOQUIA_TIPO_DOC_MAP.get(tipo_documento_abrev.upper(), "1")
    tipo_doc_info = ANTIOQUIA_TIPOS_DOCUMENTO.get(tipo_documento_id, ANTIOQUIA_TIPOS_DOCUMENTO["1"])
    doc_abreviatura = tipo_doc_info["abreviatura"]
    doc_nombre = tipo_doc_info["nombre"]

    if tipo_documento_id == "2":
        identificacion = str(identificacion) + str(_calcular_digito_nit(identificacion))

    # 1. Nueva sesion (igual que cualquier consulta normal)
    session, token_cuestionario, _data3 = _sesion_antioquia(
        placa, identificacion, tipo_documento_id,
        modelo, municipio_transito, apellidos_propietario
    )

    # 2. Crear la declaracion sugerida para la vigencia pedida (misma sesion)
    data_vig = _consultar_vigencia_antioquia(
        vigencia, session, token_cuestionario,
        placa, identificacion, tipo_documento_id,
        doc_abreviatura, doc_nombre,
        celular, email, direccion, municipio, municipio_cod, departamento_cod
    )
    formulario_liquidacion = data_vig.get("formularioLiquidacion")
    if not formulario_liquidacion:
        raise Exception(f"No se pudo generar la declaracion: {json.dumps(data_vig, ensure_ascii=False)[:300]}")

    # 3. Aceptar las 3 casillas (misma sesion)
    _antioquia_aceptar_terminos_liquidacion(session, identificacion, tipo_documento_id,
                                              doc_abreviatura, doc_nombre)

    # 4. Descargar el PDF ya generado (misma sesion)
    # El sitio espera este valor como NUMERO en el JSON, no como texto
    # entre comillas -- por eso se convierte antes de enviarlo.
    pdf_bytes = _antioquia_descargar_pdf_liquidacion(session, int(formulario_liquidacion))
    return pdf_bytes, data_vig


def _antioquia_calcular_validez_pdf(vigencia):
    """La declaracion sugerida de una vigencia VENCIDA solo sirve el mismo
    dia en que se genero (los intereses suben a diario). La de la vigencia
    ACTUAL (el año en curso) es distinta: sirve durante toda la ventana de
    pronto pago -- del 1 de enero al 30 de abril, o del 1 de mayo al 31 de
    julio -- y desde el 1 de agosto en adelante se comporta igual que una
    vigencia vencida (valida solo el mismo dia)."""
    hoy = datetime.now().date()
    anio_actual = hoy.year

    if int(vigencia) == anio_actual:
        if hoy.month <= 4:
            return date(anio_actual, 4, 30)
        elif hoy.month <= 7:
            return date(anio_actual, 7, 31)
    return hoy  # vigencias vencidas, o vigencia actual desde agosto en adelante


def _cache_declaracion_buscar(placa, vigencia):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT url FROM cache_declaraciones_antioquia
            WHERE placa = %s AND vigencia = %s AND valido_hasta >= CURRENT_DATE
        """, (placa.upper(), int(vigencia)))
        row = cur.fetchone()
        cur.close(); conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"Error buscando cache de declaracion: {e}")
        return None


def _cache_declaracion_guardar(placa, vigencia, url):
    try:
        valido_hasta = _antioquia_calcular_validez_pdf(vigencia)
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cache_declaraciones_antioquia (placa, vigencia, url, valido_hasta)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (placa, vigencia) DO UPDATE SET url = EXCLUDED.url,
                valido_hasta = EXCLUDED.valido_hasta, creado_en = NOW()
        """, (placa.upper(), int(vigencia), url, valido_hasta))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Error guardando cache de declaracion: {e}")


def antioquia_generar_todas_declaraciones(placa, identificacion, tipo_documento_abrev, vigencias,
                                           modelo, municipio_transito, apellidos_propietario,
                                           celular="3000000000", email="consulta@consulta.com",
                                           direccion="CRA", municipio="MEDELLIN",
                                           municipio_cod=5001000, departamento_cod=5, job_id=None,
                                           ignorar_cache=False):
    """Genera (o reutiliza del cache, si sigue vigente) el PDF de cada
    vigencia adeudada. Cada vigencia es INDEPENDIENTE: si una falla (a
    veces la Gobernacion tiene problemas puntuales con alguna), las demas
    igual se entregan, y solo habria que reintentar la que fallo.
    Si 'ignorar_cache' es True (ej. porque se dieron datos reales del
    cliente para el PDF final), se ignora cualquier PDF ya cacheado y se
    genera uno nuevo -- para no entregar por error una version vieja con
    datos de relleno.
    Devuelve una lista de dicts: {vigencia, ok, url, error}."""
    placa = placa.upper()
    resultados = []

    for vigencia in vigencias:
        url_cache = None if ignorar_cache else _cache_declaracion_buscar(placa, vigencia)
        if url_cache:
            resultados.append({"vigencia": vigencia, "ok": True, "url": url_cache})
            if job_id:
                job_actualizar(job_id, f"Vigencia {vigencia}: usando declaración ya generada hoy...",
                                datos_parciales=resultados)
            continue

        if job_id:
            job_actualizar(job_id, f"Generando declaración de la vigencia {vigencia}...",
                            datos_parciales=resultados)
        try:
            pdf_bytes, _data_vig = antioquia_generar_pdf_declaracion(
                placa, identificacion, tipo_documento_abrev, vigencia,
                modelo, municipio_transito, apellidos_propietario,
                celular, email, direccion, municipio, municipio_cod, departamento_cod
            )
            id_unico = uuid.uuid4().hex[:8]
            ruta = f"/tmp/decl_{placa}_{vigencia}_{id_unico}.pdf"
            with open(ruta, "wb") as f:
                f.write(pdf_bytes)

            url = subir_a_r2(ruta, f"declaraciones/{placa}_{vigencia}_{id_unico}.pdf",
                              nombre_descarga=f"Declaracion_{placa}_{vigencia}.pdf")
            os.remove(ruta)
            _cache_declaracion_guardar(placa, vigencia, url)
            resultados.append({"vigencia": vigencia, "ok": True, "url": url})
        except Exception as e:
            print(f"Error generando declaracion vigencia {vigencia} para {placa}: {e}", flush=True)
            resultados.append({"vigencia": vigencia, "ok": False, "error": str(e)})

        if job_id:
            job_actualizar(job_id, f"Vigencia {vigencia} lista.", datos_parciales=resultados)

    return resultados


def consultar_antioquia(page, placa, identificacion, tipo_documento_abrev,
                        modelo, municipio_transito, apellidos_propietario,
                        celular="3000000000", email="consulta@consulta.com",
                        direccion="CRA", municipio="MEDELLIN",
                        municipio_cod=5001000, departamento_cod=5, job_id=None):
    """
    Proceso completo para Antioquia.
    Retorna (registros, total, avaluo, estado_vehiculo, excede_limite).
    """
    LIMITE = ANTIOQUIA_LIMITE_VIGENCIAS

    # Resolver tipo de documento
    tipo_documento_id = ANTIOQUIA_TIPO_DOC_MAP.get(tipo_documento_abrev.upper(), "1")
    tipo_doc_info     = ANTIOQUIA_TIPOS_DOCUMENTO.get(tipo_documento_id, ANTIOQUIA_TIPOS_DOCUMENTO["1"])
    doc_abreviatura   = tipo_doc_info["abreviatura"]
    doc_nombre        = tipo_doc_info["nombre"]

    # Si es NIT, calcular y agregar dígito de verificación
    if tipo_documento_id == "2":
        identificacion = str(identificacion) + str(_calcular_digito_nit(identificacion))

    if job_id:
        job_actualizar(job_id, "Estoy ingresando a la página de la Gobernación de Antioquia...")
    print(f"\n  → Consultando primer bloque de datos ({placa})...")
    session0, token0, data3 = _sesion_antioquia(
        placa, identificacion, tipo_documento_id,
        modelo, municipio_transito, apellidos_propietario
    )

    estado_veh          = data3.get("estadoCuenta", {})
    vigencias_adeudadas = data3.get("listaVigenciasAdeudas", [])
    avaluo              = estado_veh.get("avaluoComercial", 0) or 0
    print(f"  → Vigencias adeudadas encontradas: {len(vigencias_adeudadas)}")
    if job_id:
        if not vigencias_adeudadas:
            job_actualizar(job_id, "Este vehículo está a paz y salvo con la Gobernación de Antioquia.")
        else:
            job_actualizar(job_id, f"Encontré {len(vigencias_adeudadas)} año(s) con impuesto pendiente. Consultando valores...")

    # Paz y salvo — solo retornar si el avaluo es confiable (> 0)
    if not vigencias_adeudadas:
        if not avaluo or avaluo == 0:
            raise Exception("No se pudo obtener información completa del vehículo. Por favor intente de nuevo.")
        return [], 0, avaluo, estado_veh, False

    total_vigencias       = len(vigencias_adeudadas)
    vigencias_a_consultar = sorted(vigencias_adeudadas, key=lambda x: x["vigencia"], reverse=True)
    excede_limite         = total_vigencias > LIMITE
    if excede_limite:
        vigencias_a_consultar = vigencias_a_consultar[:LIMITE]

    registros         = []
    total_suma        = 0
    avaluo_actual     = 0
    retefuente_actual = 0
    MAX_INTENTOS      = 2

    # Vigencias actualmente adeudadas según el portal
    anios_adeudados = set(str(v.get("vigencia")) for v in vigencias_a_consultar)

    # Limpiar del caché las vigencias que ya fueron pagadas
    try:
        conn_c = get_db_conn()
        cur_c  = conn_c.cursor()
        cur_c.execute("""
            SELECT vigencia FROM cache_impuestos_antioquia
            WHERE placa = %s AND estado = 'CON_DEUDA'
              AND (expira_en IS NULL OR expira_en >= NOW())
        """, (placa.upper(),))
        anios_en_cache = set(str(r[0]) for r in cur_c.fetchall())
        cur_c.close(); conn_c.close()
        for anio_pagado in (anios_en_cache - anios_adeudados):
            cache_antioquia_eliminar_vigencia(placa, anio_pagado)
    except Exception as e:
        print(f"  → Error limpiando caché: {e}")

    for v in vigencias_a_consultar:
        anio = v.get("vigencia")
        if job_id:
            job_actualizar(job_id, f"Estoy consultando el impuesto del año {anio}...")
        print(f"\n  → Consultando vigencia {anio}...")

        total_pagar  = None
        avaluo_vig   = 0

        # Intentar desde caché primero
        cache_vig = cache_antioquia_buscar_vigencia(placa, anio)
        if cache_vig:
            total_pagar = cache_vig['total_pagar']
            avaluo_vig  = cache_vig['avaluo']
            print(f"  ✔ Vigencia {anio} desde caché: ${total_pagar:,}")
        else:
            for intento in range(1, MAX_INTENTOS + 1):
                if intento > 1:
                    print(f"  ↺ Reintentando vigencia {anio}...")
                try:
                    session_v, token_v, _ = _sesion_antioquia(
                        placa, identificacion, tipo_documento_id,
                        modelo, municipio_transito, apellidos_propietario
                    )
                    data_vig = _consultar_vigencia_antioquia(
                        anio, session_v, token_v,
                        placa, identificacion, tipo_documento_id,
                        doc_abreviatura, doc_nombre,
                        celular, email, direccion, municipio, municipio_cod, departamento_cod
                    )
                    _msg    = data_vig.get("mensaje") or data_vig.get("descripcion")
                    _codigo = data_vig.get("codigo")
                    if _codigo and _codigo != 1 and _msg:
                        print(f"  ✖ Error servidor vigencia {anio}: {_msg}")

                    total_pagar = data_vig.get("totalPagar")
                    avaluo_vig  = data_vig.get("avaluoComercial", 0) or 0
                    if total_pagar is not None:
                        print(f"  ✔ Vigencia {anio}: ${total_pagar:,}")
                        # Guardar en caché
                        try:
                            cache_antioquia_guardar_deuda(placa, [{
                                'vigencia': anio,
                                'total_pagar': total_pagar,
                            }], avaluo_vig or avaluo)
                            print(f"  → Caché guardado exitosamente para {placa} vigencia {anio}")
                        except Exception as ce:
                            print(f"  ✖ Error guardando caché vigencia {anio}: {ce}")
                        break
                except Exception as e:
                    print(f"  ✖ Error vigencia {anio} intento {intento}: {e}")

        if not avaluo_actual and avaluo_vig:
            avaluo_actual     = avaluo_vig
            retefuente_actual = round(avaluo_vig / 100)

        if total_pagar is not None:
            total_suma += total_pagar

        registros.append({
            "vigencia":       str(anio),
            "estado":         "Pendiente de pago",
            "total_vigencia": total_pagar,
        })

        if job_id and total_pagar is not None:
            job_actualizar(job_id,
                f"Año {anio}: impuesto es ${total_pagar:,}. Continuando...",
                datos_parciales=list(registros))

    print(f"\n  ✔ ¡Consulta Antioquia finalizada!")
    return registros, total_suma, avaluo_actual or avaluo, estado_veh, excede_limite



def consultar_medellin(page, placa, identificacion, modelo, apellidos_propietario,
                       celular="3208578787", email="consulta@juridicox.com",
                       direccion="CRA 20 20 20"):
    """Consulta impuesto municipal de Medellín (servicio público) con valores reales incluyendo intereses."""
    import re as _re

    url = "https://www.medellin.gov.co/irj/portal/medellin/pago-impuesto-circulacion-transito"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Esperar popup de validación
    page.wait_for_selector("#popupValidacion", timeout=30000)

    # Cerrar popup de imagen si aparece
    try:
        cerrar = page.locator(".divCerrarPopup")
        if cerrar.is_visible(timeout=3000):
            cerrar.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # Paso 0 — popup validación: servicio público + Medellín
    page.locator("input[name='tipoVehiculo'][value='publico']").check()
    page.wait_for_timeout(500)
    page.wait_for_selector("#matriculaLugar", timeout=5000)
    page.locator("input[name='lugarMatricula'][value='medellin']").check()
    page.wait_for_timeout(500)
    page.wait_for_function("() => !document.getElementById('btnContinuar').disabled", timeout=5000)
    page.locator("#btnContinuar").click()

    # Paso 1 — llenar placa y documento
    page.wait_for_selector("#placa", timeout=15000)
    page.locator("#placa").fill(placa.upper())
    page.locator("#id").fill(identificacion)
    page.locator("button.boton_consulta").click()

    # Esperar tabla de vigencias
    page.wait_for_selector("#cont_paso1 table tbody tr", timeout=30000)

    body_text = page.inner_text("body").lower()
    if "no se encuentra matriculado" in body_text or "no está matriculado" in body_text:
        raise Exception("Este vehículo no está matriculado en la Secretaría de Movilidad de Medellín.")
    if "no presenta deuda" in body_text or "no adeuda" in body_text or "paz y salvo" in body_text:
        return [], 0

    # Seleccionar todos los checkboxes de vigencias
    try:
        page.locator(".sel_todo").click(timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(500)
    # Si no quedaron todos marcados, marcarlos uno a uno
    checkboxes = page.locator("#cont_paso1 input[type='checkbox']").all()
    for cb in checkboxes:
        try:
            if not cb.is_checked():
                cb.check()
        except Exception:
            pass
    page.wait_for_timeout(500)
    # Verificar que hay checkboxes marcados antes de continuar
    marcados = page.locator("#cont_paso1 input[type='checkbox']:checked").count()
    btn = page.locator("button.boton_continuar").first
    disabled = btn.get_attribute("disabled")
    # Forzar click aunque esté deshabilitado
    btn.evaluate("el => el.click()")
    page.wait_for_timeout(1000)

    # Paso 2a — modelo y propietario
    page.wait_for_selector("#modelo_veh", timeout=15000)
    modelo_str = str(modelo).strip()[:4].zfill(4)
    page.locator("#modelo_veh").fill(modelo_str)

    # Seleccionar propietario — primera opción disponible si no hay match por apellido
    try:
        opciones = page.locator("#nombres_props option.valorSel").all()
        valor_sel = opciones[0].get_attribute("value") if opciones else None
        for op in opciones:
            texto = (op.inner_text() or "").upper()
            if apellidos_propietario and apellidos_propietario.split()[0].upper() in texto:
                valor_sel = op.get_attribute("value")
                break
        if valor_sel:
            page.locator("#nombres_props").select_option(valor_sel)
    except Exception:
        pass

    # Forzar click en boton_validar ignorando validación HTML5
    page.locator("button.boton_validar").evaluate("el => el.click()")
    page.wait_for_timeout(1500)

    # Paso 2b — datos de contacto del propietario
    page.wait_for_selector("#correo", timeout=15000)
    page.locator("#correo").fill(email)
    page.locator("#celular").fill(celular)
    try:
        page.locator("#telefono").fill("6042379933")
    except Exception:
        pass

    # Dirección — abrir popup y llenar
    try:
        page.locator("#direccion").click()
        page.wait_for_selector("#tipo_via", state="visible", timeout=5000)
        page.locator("#tipo_via").select_option("CARRERA")
        page.locator("#numero1").fill("20")
        page.locator("#numero2").fill("20")
        page.locator("#numero3").fill("20")
        # Guardar dirección con evaluate para bypass validación
        page.locator("button.boton_dir").evaluate("el => el.click()")
        page.wait_for_timeout(1000)
        # Verificar que la dirección quedó guardada
        dir_val = page.locator("#direccion").input_value()
    except Exception as e:
        # Si falla el popup, inyectar la dirección directamente
        try:
            page.evaluate("document.getElementById('direccion').removeAttribute('readonly')")
            page.locator("#direccion").fill("CARRERA 20 20 20")
        except Exception:
            pass

    # Departamento y municipio
    try:
        page.locator("#departamento").select_option("05")
        page.wait_for_timeout(500)
        page.locator("#municipio").select_option("000000005001")
        page.wait_for_timeout(500)
    except Exception as e:
        pass

    # Guardar datos del propietario — bypass validación HTML5
    # Intentar el botón de guardar del form info_propietario
    try:
        page.locator("button[form='info_propietario']").first.evaluate("el => el.click()")
    except Exception:
        # Si no existe, buscar boton_continuar o cualquier submit visible
        try:
            page.locator(".divContBotones button:not(.boton_cancelar)").first.evaluate("el => el.click()")
        except Exception as e2:
            pass
    page.wait_for_timeout(1500)

    # Esperar tabla del paso 3 con valores reales
    page.wait_for_selector("#cont_paso3 table tbody tr", timeout=30000)

    # Extraer total general del tfoot
    total = 0
    try:
        tfoot_text = page.locator("#cont_paso3 table tfoot").inner_text()
        total_match = _re.search(r'\$([\d\.]+)', tfoot_text)
        if total_match:
            total = int(total_match.group(1).replace('.', ''))
    except Exception:
        pass

    # Extraer vigencias con valores reales (impuesto + intereses + total por vigencia)
    registros = []
    filas = page.locator("#cont_paso3 table tbody tr").all()
    for fila in filas:
        texto = fila.inner_text().strip()
        if not texto:
            continue
        anio = _re.search(r'\b(20\d{2}|19\d{2})\b', texto)
        # Buscar "Total a pagar" que es la última columna
        valores = _re.findall(r'\$([\d\.]+)', texto)
        if anio and valores:
            try:
                # El último valor es "Total a pagar" por vigencia
                total_vigencia = int(valores[-1].replace('.', ''))
                impuesto = int(valores[-3].replace('.', '')) if len(valores) >= 3 else 0
                interes = int(valores[-2].replace('.', '')) if len(valores) >= 2 else 0
                if total_vigencia > 0:
                    registros.append({
                        'vigencia': anio.group(),
                        'estado': 'Pendiente de pago',
                        'impuesto_base': impuesto,
                        'interes_mora': interes,
                        'total_vigencia': total_vigencia
                    })
            except ValueError:
                pass

    if not total and registros:
        total = sum(r['total_vigencia'] for r in registros)

    return registros, total

# ============================================================
#  MAPA DE MUNICIPIOS
# ============================================================
MUNICIPIOS = {
    "envigado":    consultar_envigado,
    "sabaneta":    consultar_sabaneta,
    "itagui":      consultar_itagui,
    "bello":       consultar_bello,
    "laestrella":  consultar_laestrella,
    "la estrella": consultar_laestrella,
    "medellin":    consultar_medellin,
    "medellín":    consultar_medellin,
}


@app.route("/consultar", methods=["GET"])
def consultar():
    import traceback
    placa     = request.args.get("placa", "").upper().strip()
    municipio = request.args.get("municipio", "").lower().strip()
    if not placa or not municipio:
        return jsonify({"error": "Debes proporcionar placa y municipio."}), 400
    if municipio not in MUNICIPIOS and municipio != "antioquia":
        return jsonify({"error": f"Municipio '{municipio}' no reconocido.", "opciones": list(MUNICIPIOS.keys()) + ["antioquia"]}), 400

    identificacion     = request.args.get("identificacion", "").strip()
    tipo_documento     = request.args.get("tipo_documento", "CC").strip().upper() or "CC"
    modelo             = request.args.get("modelo", "").strip()
    municipio_transito = request.args.get("municipio_transito", "").upper().strip()
    apellidos          = request.args.get("apellidos_propietario", "").upper().strip()
    celular            = request.args.get("celular", "3000000000").strip()
    email              = request.args.get("email", "consulta@consulta.com").strip()
    direccion          = request.args.get("direccion", "CRA").strip()
    mun_declarante     = request.args.get("municipio_declarante", "MEDELLIN").strip().upper()
    municipio_cod      = int(request.args.get("municipio_cod", 5001000))
    departamento_cod   = int(request.args.get("departamento_cod", 5))

    if municipio == "antioquia":
        if not identificacion or not modelo or not municipio_transito or not apellidos:
            return jsonify({"error": "Para Antioquia debes proporcionar: identificacion, modelo, municipio_transito, apellidos_propietario."}), 400

    # Municipios síncronos
    if municipio != "antioquia":
        # Verificar cache antes de lanzar Playwright -- si ya sabemos que esta
        # a paz y salvo este año, no hace falta volver a consultar la pagina
        # del municipio (evita una consulta lenta e innecesaria).
        cache_hit_mun = cache_municipal_buscar(placa, municipio)
        if cache_hit_mun:
            print(f"  → Cache hit municipal para {placa} en {municipio} — respondiendo sin Playwright")
            return jsonify({
                "placa":       placa,
                "municipio":   municipio,
                "registros":   [],
                "total":       0,
                "sin_deuda":   True,
                "verificado":  True,
                "placa_vista": cache_hit_mun["placa_vista"],
                "fecha_pago":  cache_hit_mun["fecha_pago"],
                "marca":       cache_hit_mun["marca"],
                "valor_pago":  cache_hit_mun["valor_pago"],
                "desde_cache": True,
            })

        resultado       = {}
        error_container = {}

        def ejecutar_mun():
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, args=[
                        "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                        "--single-process", "--no-zygote", "--disable-setuid-sandbox"
                    ])
                    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                    page = context.new_page()
                    if municipio not in ["bello", "sabaneta", "laestrella"]:
                        bloquear_recursos(page)
                    funcion = MUNICIPIOS[municipio]
                    if municipio == "medellin":
                        registros, total = funcion(page, placa,
                            identificacion=identificacion,
                            modelo=modelo,
                            apellidos_propietario=apellidos,
                            celular=celular,
                            email=email)
                    else:
                        registros, total = funcion(page, placa)
                    resultado['registros'] = registros
                    resultado['total']     = total
                    context.close(); browser.close()
            except Exception as e:
                error_container['error'] = str(e)
                print(traceback.format_exc(), flush=True)

        hilo = threading.Thread(target=ejecutar_mun)
        hilo.start()
        hilo.join(timeout=620)

        if hilo.is_alive():
            return jsonify({"error": "La consulta tardo demasiado. Intenta de nuevo."}), 504
        if error_container:
            return jsonify({"error": error_container['error']}), 500
        registros_mun   = resultado.get('registros', [])
        total_mun       = resultado.get('total', 0)
        fecha_pago_mun  = ""
        marca_pago_mun  = ""
        valor_pago_mun  = ""
        placa_vista_mun = ""

        # Extraer datos de paz y salvo si el municipio los devuelve
        if registros_mun and registros_mun[0].get('paz_y_salvo'):
            r0              = registros_mun[0]
            fecha_pago_mun  = r0.get('fecha_pago', '')
            marca_pago_mun  = r0.get('marca', '')
            valor_pago_mun  = r0.get('valor_pago', '')
            placa_vista_mun = r0.get('placa_info', '')
            registros_mun   = []
            total_mun       = 0
        # Extraer último pago de registros con deuda (si viene en el primer registro)
        elif registros_mun and registros_mun[0].get('fecha_ultimo_pago'):
            r0              = registros_mun[0]
            fecha_pago_mun  = r0.get('fecha_ultimo_pago', '')
            marca_pago_mun  = r0.get('marca_ultimo_pago', '')
            valor_pago_mun  = r0.get('valor_ultimo_pago', '')
            placa_vista_mun = r0.get('placa_ultimo_pago', '')

        # Reintento automático si paz y salvo sin evidencia de verificación
        # (posible falso positivo: la página no cargó los datos reales del vehículo).
        # Se considera "verificado" cuando trajo placa y/o marca vistas en la página.
        verificado_mun = bool(placa_vista_mun or marca_pago_mun)
        if total_mun == 0 and not verificado_mun and municipio in ("envigado", "sabaneta", "itagui", "bello"):
            resultado2    = {}
            error2        = {}
            funcion_reint = MUNICIPIOS[municipio]
            def _reintento():
                try:
                    with sync_playwright() as pw2:
                        b2 = pw2.chromium.launch(headless=True, args=[
                            "--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                            "--single-process","--no-zygote","--disable-setuid-sandbox"
                        ])
                        ctx2  = b2.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                        pg2   = ctx2.new_page()
                        bloquear_recursos(pg2)
                        r2, t2 = funcion_reint(pg2, placa)
                        resultado2['registros'] = r2
                        resultado2['total']     = t2
                        ctx2.close(); b2.close()
                except Exception as e2:
                    error2['error'] = str(e2)
            import threading as _th2
            hilo2 = _th2.Thread(target=_reintento)
            hilo2.start()
            hilo2.join(timeout=120)
            if not error2 and resultado2:
                r2 = resultado2.get('registros', [])
                t2 = resultado2.get('total', 0)
                fp2 = ""; mp2 = ""; vp2 = ""; pv2 = ""
                if r2 and r2[0].get('paz_y_salvo'):
                    fp2 = r2[0].get('fecha_pago', '')
                    mp2 = r2[0].get('marca', '')
                    vp2 = r2[0].get('valor_pago', '')
                    pv2 = r2[0].get('placa_info', '')
                    r2  = []
                    t2  = 0
                elif r2 and r2[0].get('fecha_ultimo_pago'):
                    fp2 = r2[0].get('fecha_ultimo_pago', '')
                    mp2 = r2[0].get('marca_ultimo_pago', '')
                    vp2 = r2[0].get('valor_ultimo_pago', '')
                    pv2 = r2[0].get('placa_ultimo_pago', '')
                # Si el reintento también da paz y salvo verificado → confirmado
                # Si el reintento da deuda → el primero era falso positivo
                registros_mun   = r2
                total_mun       = t2
                fecha_pago_mun  = fp2
                marca_pago_mun  = mp2
                valor_pago_mun  = vp2
                placa_vista_mun = pv2
                verificado_mun  = bool(pv2 or mp2)

        # Guardar en cache si quedo confirmado a paz y salvo -- asi no se
        # vuelve a consultar este municipio para esta placa el resto del año.
        if verificado_mun and total_mun == 0 and not registros_mun:
            cache_municipal_guardar_paz_salvo(
                placa, municipio, fecha_pago_mun, marca_pago_mun, valor_pago_mun, placa_vista_mun
            )

        return jsonify({
            "placa":       placa,
            "municipio":   municipio,
            "registros":   registros_mun,
            "total":       total_mun,
            "sin_deuda":   total_mun == 0 and not registros_mun,
            "verificado":  verificado_mun,
            "placa_vista": placa_vista_mun,
            "fecha_pago":  fecha_pago_mun,
            "marca":       marca_pago_mun,
            "valor_pago":  valor_pago_mun,
        })

    # Antioquia — verificar caché de vigencias antes de lanzar Playwright
    # El snippet pasa las vigencias adeudadas que ya conoce del paso 1
    vigencias_param = request.args.get("vigencias", "").strip()
    if vigencias_param:
        anios_solicitados = [a.strip() for a in vigencias_param.split(",") if a.strip()]
        registros_cache = []
        avaluo_cache    = 0
        total_cache     = 0
        todos_cacheados = True

        for anio in anios_solicitados:
            cv = cache_antioquia_buscar_vigencia(placa, anio)
            if cv:
                registros_cache.append({
                    "vigencia":       str(anio),
                    "estado":         "Pendiente de pago",
                    "total_vigencia": cv['total_pagar'],
                })
                total_cache  += cv['total_pagar']
                if not avaluo_cache:
                    avaluo_cache = cv['avaluo']
            else:
                todos_cacheados = False
                break

        if todos_cacheados and registros_cache:
            print(f"  → Cache hit completo para {placa} — respondiendo sin Playwright")
            return jsonify({
                "placa":      placa,
                "municipio":  "antioquia",
                "placa_info": {},
                "registros":  registros_cache,
                "total":      total_cache,
                "avaluo":     avaluo_cache,
                "retefuente": round(avaluo_cache / 100) if avaluo_cache else 0,
                "sin_deuda":  False,
                "desde_cache": True,
            })

    # Antioquia — sistema asíncrono
    job_id = str(uuid.uuid4())[:12]
    job_actualizar(job_id, "Iniciando consulta...", "procesando")

    def ejecutar_antioquia():
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=[
                    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                    "--single-process", "--no-zygote", "--disable-setuid-sandbox"
                ])
                context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                page = context.new_page()
                registros, total, avaluo, estado_veh, excede = consultar_antioquia(
                    page, placa, identificacion, tipo_documento,
                    modelo, municipio_transito, apellidos,
                    celular, email, direccion, mun_declarante,
                    municipio_cod, departamento_cod, job_id=job_id
                )
                context.close(); browser.close()

            respuesta = {
                "placa":      placa,
                "municipio":  "antioquia",
                "placa_info": {
                    "marca":       estado_veh.get("marca", ""),
                    "linea":       estado_veh.get("linea", ""),
                    "modelo":      estado_veh.get("modelo", ""),
                    "propietario": estado_veh.get("nombrePropietario", ""),
                },
                "registros":  registros,
                "total":      total,
                "avaluo":     avaluo,
                "retefuente": round(avaluo / 100) if avaluo else 0,
                "sin_deuda":  len(registros) == 0,
            }
            if excede:
                respuesta["excede_limite"]  = True
                respuesta["mensaje_limite"] = f"El límite de consulta es de {ANTIOQUIA_LIMITE_VIGENCIAS} vigencias. Comunícate con un asesor de la Gobernación de Antioquia al 6044444666."
            job_terminar(job_id, respuesta)
        except Exception as e:
            print(traceback.format_exc(), flush=True)
            msg = str(e)
            if any(x in msg.lower() for x in ["net::err", "connection"]):
                msg = "No se pudo conectar al portal de Antioquia. Intenta más tarde."
            job_error(job_id, msg)

    threading.Thread(target=ejecutar_antioquia, daemon=True).start()
    return jsonify({"job_id": job_id, "estado": "procesando"})


@app.route("/consultar/antioquia/vigencias", methods=["GET"])
def consultar_antioquia_vigencias():
    """PASO 1 — Rápido (2 captchas). Devuelve lista de vigencias sin valores."""
    import traceback
    placa              = request.args.get("placa", "").upper().strip()
    identificacion     = request.args.get("identificacion", "").strip()
    tipo_documento     = request.args.get("tipo_documento", "CC").strip().upper()
    modelo             = request.args.get("modelo", "").strip()
    municipio_transito = request.args.get("municipio_transito", "").upper().strip()
    apellidos          = request.args.get("apellidos_propietario", "").upper().strip()

    if not all([placa, identificacion, modelo, municipio_transito, apellidos]):
        return jsonify({"error": "Faltan datos requeridos"}), 400

    # Verificar caché primero
    cache = cache_antioquia_buscar(placa)
    if cache and cache['estado'] == 'PAZ_Y_SALVO':
        print(f"  → Cache hit PAZ_Y_SALVO para {placa}")
        return jsonify({
            "placa":       placa,
            "sin_deuda":   True,
            "avaluo":      cache.get('avaluo', 0),
            "retefuente":  cache.get('retefuente', 0),
            "vigencias":   [],
            "placa_info":  {},
            "desde_cache": True,
        })


    resultado       = {}
    error_container = {}

    def ejecutar():
        try:
            tipo_documento_id = ANTIOQUIA_TIPO_DOC_MAP.get(tipo_documento, "1")
            if tipo_documento_id == "2":
                ident = str(identificacion) + str(_calcular_digito_nit(identificacion))
            else:
                ident = identificacion
            session0, token0, data3 = _sesion_antioquia(
                placa, ident, tipo_documento_id,
                modelo, municipio_transito, apellidos
            )
            estado_veh          = data3.get("estadoCuenta", {})
            vigencias_adeudadas = data3.get("listaVigenciasAdeudas", [])
            avaluo              = estado_veh.get("avaluoComercial", 0) or 0
            resultado['vigencias']  = vigencias_adeudadas
            resultado['avaluo']     = avaluo
            resultado['estado_veh'] = estado_veh
            resultado['sin_deuda']  = len(vigencias_adeudadas) == 0
            # Guardar en caché si está a paz y salvo
            if not vigencias_adeudadas and avaluo and avaluo > 0:
                cache_antioquia_guardar_paz_salvo(placa, avaluo, estado_veh)
                # Se guardan tambien TODOS los datos (historial de
                # declaraciones, procesos fiscales, bloqueos, novedades)
                # para poder generar el documento Estado de Cuenta despues.
                guardar_estado_cuenta_antioquia(placa, data3)
        except Exception as e:
            error_container['error'] = str(e)
            print(traceback.format_exc(), flush=True)

    hilo = threading.Thread(target=ejecutar)
    hilo.start()
    hilo.join(timeout=120)

    if hilo.is_alive():
        return jsonify({"error": "La consulta tardó demasiado. Intenta de nuevo."}), 504
    if error_container:
        return jsonify({"error": error_container['error']}), 500

    estado_veh = resultado.get('estado_veh', {})
    avaluo     = resultado.get('avaluo', 0)
    vigencias  = resultado.get('vigencias', [])

    return jsonify({
        "placa":      placa,
        "sin_deuda":  resultado.get('sin_deuda', True),
        "avaluo":     avaluo,
        "retefuente": round(avaluo / 100) if avaluo else 0,
        "vigencias":  vigencias,
        "placa_info": {
            "marca":       estado_veh.get("marca", ""),
            "linea":       estado_veh.get("linea", ""),
            "modelo":      estado_veh.get("modelo", ""),
            "propietario": estado_veh.get("nombrePropietario", ""),
        }
    })


@app.route("/consultar-runt-vehiculo", methods=["GET"])
def consultar_runt_vehiculo_endpoint():
    """Consulta el RUNT (Placa y Propietario) para una placa + cedula.
    Es una consulta con su propio costo de 2Captcha, independiente de las
    consultas de impuestos -- por eso se guarda directo en la tabla
    'vehiculos' cada vez que se llama, sin verificar cache primero (los
    datos del RUNT cambian con cada tramite, a diferencia del estado de
    paz y salvo que dura todo el año)."""
    placa  = request.args.get("placa", "").upper().strip()
    cedula = request.args.get("cedula", "").strip()
    tipo_documento = request.args.get("tipo_documento", "CC").strip().upper() or "CC"
    user_id = request.args.get("user_id", "").strip()  # id del usuario en Supabase (opcional)

    if not placa or not cedula:
        return jsonify({"error": "Debes proporcionar placa y cedula."}), 400

    # Limite: no se puede forzar una nueva consulta al RUNT para la misma
    # placa si ya se hizo una en los ultimos 3 dias -- en ese caso hay que
    # usar el dato ya guardado en cache (vehiculo-runt-guardado).
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT leido_en FROM vehiculos WHERE placa = %s AND fuente = 'RUNT'
        """, (placa,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0]:
            transcurrido = datetime.now() - row[0]
            if transcurrido < timedelta(days=3):
                faltan = timedelta(days=3) - transcurrido
                horas_faltantes = int(faltan.total_seconds() // 3600)
                return jsonify({
                    "error": f"Esta placa ya se consultó en el RUNT hace menos de 3 días. "
                             f"Debes usar el dato ya guardado; podrás forzar una nueva consulta "
                             f"en aproximadamente {horas_faltantes} horas.",
                    "limite_activo": True,
                    "horas_restantes": horas_faltantes
                }), 429
    except Exception as e:
        print(f"Error verificando limite de consulta RUNT: {e}", flush=True)
        # Si falla la verificacion, se deja continuar (no se bloquea por un
        # problema tecnico ajeno al limite en si).

    job_id = str(uuid.uuid4())[:12]
    job_actualizar(job_id, "Iniciando consulta RUNT...", "procesando")

    def ejecutar():
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=[
                    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                    "--single-process", "--no-zygote", "--disable-setuid-sandbox"
                ])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                    viewport={"width": 390, "height": 844},
                )
                page = context.new_page()
                datos = consultar_runt_vehiculo(page, placa, cedula, tipo_documento, job_id=job_id)
                context.close(); browser.close()

            if not datos.get("placa"):
                job_error(job_id, "No se pudo leer la placa en el resultado. Verifica los datos o intenta de nuevo.")
                return

            guardar_vehiculo_runt(datos)
            if user_id:
                guardar_mi_consulta(user_id, datos["placa"], cedula)
            datos["leido_en"] = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
            job_terminar(job_id, datos)
        except Exception as e:
            import traceback
            print(traceback.format_exc(), flush=True)
            job_error(job_id, str(e))

    hilo = threading.Thread(target=ejecutar)
    hilo.start()

    return jsonify({"job_id": job_id})


def guardar_mi_consulta(user_id, placa, cedula):
    """Registra que este usuario en particular consulto esta placa (y
    cedula), para el historial personal de 'Mis vehiculos consultados'."""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO mis_consultas (user_id, placa, cedula, actualizado_en)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, placa, cedula) DO UPDATE SET actualizado_en = NOW()
        """, (user_id, placa, cedula))
        conn.commit()
        cur.close(); conn.close()
        return True, None
    except Exception as e:
        print(f"Error guardando mi_consulta: {e}")
        return False, str(e)


@app.route("/guardar-vehiculo-ocr", methods=["POST"])
def guardar_vehiculo_ocr():
    """Guarda lo leido por OCR de una tarjeta de propiedad. Si esa placa ya
    tenia datos de una consulta al RUNT, el RUNT prevalece: no se
    sobrescriben marca/linea/modelo/etc, ni la fuente ni la fecha de
    lectura -- solo se actualizan los campos que el RUNT NUNCA trae
    (tipo de documento, cedula, nombre del propietario, municipio, y la
    limitacion a la propiedad tal como la leyo el OCR)."""
    data = request.get_json(silent=True) or {}
    placa = (data.get("placa") or "").upper().strip()
    if not placa:
        return jsonify({"error": "Debes proporcionar placa."}), 400

    user_id = (data.get("user_id") or "").strip()
    cedula  = (data.get("cedula") or "").strip()

    campos_ocr_siempre = ["municipio", "propietario_tipo_documento", "propietario_cedula", "propietario_nombre", "ocr_limitacion_propiedad"]
    campos_ocr_si_no_hay_runt = ["clase", "marca", "linea", "modelo", "cilindrada", "servicio", "carroceria"]

    valores = {
        "municipio": data.get("municipio"),
        "propietario_tipo_documento": data.get("tipo_documento"),
        "propietario_cedula": cedula,
        "propietario_nombre": data.get("apellidos"),
        "ocr_limitacion_propiedad": data.get("limitacion_propiedad"),
        "clase": data.get("clase"),
        "marca": data.get("marca"),
        "linea": data.get("linea"),
        "modelo": data.get("modelo"),
        "cilindrada": data.get("cilindrada"),
        "servicio": data.get("servicio"),
        "carroceria": data.get("carroceria"),
    }

    try:
        conn = get_db_conn()
        cur = conn.cursor()

        todas_columnas = campos_ocr_siempre + campos_ocr_si_no_hay_runt
        cols_sql = ", ".join(["placa"] + todas_columnas + ["fuente", "leido_en"])
        vals_sql = ", ".join(["%s"] * (len(todas_columnas) + 3))
        params = [placa] + [valores[c] for c in todas_columnas] + ["OCR", datetime.now()]

        set_siempre = ", ".join(f"{c}=EXCLUDED.{c}" for c in campos_ocr_siempre)
        set_condicional = ", ".join(
            f"{c}=CASE WHEN vehiculos.fuente='RUNT' THEN vehiculos.{c} ELSE EXCLUDED.{c} END"
            for c in campos_ocr_si_no_hay_runt
        )

        cur.execute(f"""
            INSERT INTO vehiculos ({cols_sql})
            VALUES ({vals_sql})
            ON CONFLICT (placa) DO UPDATE SET
                {set_siempre}, {set_condicional},
                fuente = CASE WHEN vehiculos.fuente='RUNT' THEN 'RUNT' ELSE 'OCR' END,
                leido_en = CASE WHEN vehiculos.fuente='RUNT' THEN vehiculos.leido_en ELSE EXCLUDED.leido_en END
        """, params)
        conn.commit()
        cur.close(); conn.close()

        if user_id:
            guardar_mi_consulta(user_id, placa, cedula)

        return jsonify({"ok": True})
    except Exception as e:
        print(f"Error guardando vehiculo OCR: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/combinar-pdfs", methods=["POST"])
def combinar_pdfs_endpoint():
    """Toma varias URLs de PDFs YA generados (ej. de /generar-pdf-declaracion)
    y las une en un solo PDF de varias paginas -- pensado para el boton
    'Combinar PDFs' en el frontend, una vez ya se generaron los individuales.
    No vuelve a consultar nada ni gasta captchas, solo descarga y pega."""
    datos = request.get_json(silent=True) or {}
    urls = datos.get("urls", [])
    placa = (datos.get("placa") or "declaraciones").upper().strip()

    if not urls or len(urls) < 2:
        return jsonify({"error": "Se necesitan al menos 2 URLs para combinar"}), 400

    rutas_temp = []
    try:
        writer = PdfWriter()
        for i, url in enumerate(urls):
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                raise Exception(f"No se pudo descargar {url}")
            ruta = f"/tmp/combinar_{i}_{uuid.uuid4().hex[:6]}.pdf"
            with open(ruta, "wb") as f:
                f.write(resp.content)
            rutas_temp.append(ruta)
            writer.append(ruta)

        id_unico = uuid.uuid4().hex[:8]
        ruta_combinado = f"/tmp/combinado_{placa}_{id_unico}.pdf"
        with open(ruta_combinado, "wb") as f:
            writer.write(f)
        writer.close()

        url_final = subir_a_r2(ruta_combinado, f"declaraciones/combinado_{placa}_{id_unico}.pdf",
                                nombre_descarga=f"Declaracion_{placa}_combinado.pdf")
        os.remove(ruta_combinado)
        for ruta in rutas_temp:
            os.remove(ruta)

        return jsonify({"ok": True, "url": url_final})
    except Exception as e:
        for ruta in rutas_temp:
            if os.path.exists(ruta):
                os.remove(ruta)
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/generar-pdf-declaracion", methods=["GET"])
def generar_pdf_declaracion_endpoint():
    """Genera el/los PDF(s) de la declaracion sugerida (pago en banco) EN
    SEGUNDO PLANO -- con varias vigencias (cada una con sus propios
    captchas) el proceso puede tardar varios minutos, y una sola peticion
    tan larga corre el riesgo de que el navegador (o algun proxy en el
    camino) la corte con 'Failed to fetch' aunque el servidor siga
    trabajando bien. Por eso, igual que la consulta de impuestos, esto
    responde de inmediato con un job_id para consultar el avance en
    /consultar/estado."""
    placa = request.args.get("placa", "").upper().strip()
    identificacion = request.args.get("identificacion", "").strip()
    tipo_documento = request.args.get("tipo_documento", "CC").strip()
    vigencias_raw = request.args.get("vigencia", "").strip()
    modelo = request.args.get("modelo", "").strip()
    municipio_transito = request.args.get("municipio_transito", "").strip()
    apellidos_propietario = request.args.get("apellidos_propietario", "").strip()
    # Opcionales -- para que el PDF quede diligenciado con los datos reales
    # del cliente que va a pagar, en vez de los datos de relleno. Si no se
    # envian, se usan los valores por defecto de siempre.
    celular_raw = request.args.get("celular", "").strip()
    email_raw = request.args.get("email", "").strip()
    direccion_raw = request.args.get("direccion", "").strip()
    municipio_raw = request.args.get("municipio", "").strip()
    municipio_cod_raw = request.args.get("municipio_cod", "").strip()
    departamento_cod_raw = request.args.get("departamento_cod", "").strip()

    celular = celular_raw or "3000000000"
    email = email_raw or "consulta@consulta.com"
    direccion = direccion_raw or "CRA"
    municipio_residencia = municipio_raw or "MEDELLIN"
    municipio_cod = int(municipio_cod_raw) if municipio_cod_raw.isdigit() else 5001000
    departamento_cod = int(departamento_cod_raw) if departamento_cod_raw.isdigit() else 5

    # Si se dieron datos reales, no se reutiliza un PDF cacheado (podria
    # tener los datos de relleno de una consulta anterior).
    tiene_datos_reales = bool(celular_raw or email_raw or direccion_raw or municipio_raw)

    if not all([placa, identificacion, vigencias_raw, modelo, municipio_transito, apellidos_propietario]):
        return jsonify({"error": "Faltan parametros: placa, identificacion, vigencia, modelo, municipio_transito, apellidos_propietario"}), 400

    vigencias = [v.strip() for v in vigencias_raw.split(",") if v.strip()]
    job_id = str(uuid.uuid4())
    job_actualizar(job_id, "Iniciando...", "procesando")

    def ejecutar_declaraciones():
        try:
            resultados = antioquia_generar_todas_declaraciones(
                placa, identificacion, tipo_documento, vigencias,
                modelo, municipio_transito, apellidos_propietario,
                celular=celular, email=email, direccion=direccion,
                municipio=municipio_residencia, municipio_cod=municipio_cod,
                departamento_cod=departamento_cod,
                ignorar_cache=tiene_datos_reales,
                job_id=job_id
            )
            job_terminar(job_id, {"resultados": resultados})
        except Exception as e:
            import traceback
            print(traceback.format_exc(), flush=True)
            job_error(job_id, str(e))

    threading.Thread(target=ejecutar_declaraciones, daemon=True).start()
    return jsonify({"job_id": job_id, "estado": "procesando"})


@app.route("/generar-declaracion-manual", methods=["GET"])
def generar_declaracion_manual_endpoint():
    """Genera la Declaracion Manual (formulario FO-M8-P6-008) diligenciada,
    combinando: datos del vehiculo ya guardados en Tramy (tabla vehiculos),
    los datos del propietario que escribe el usuario, y la liquidacion
    privada + caja/traccion que se obtienen de una consulta real a la
    Gobernacion (la misma consulta que usa la Declaracion Sugerida).
    Se ejecuta en segundo plano por el mismo motivo que las demas consultas
    a la Gobernacion: puede tardar por los captchas."""
    placa = request.args.get("placa", "").upper().strip()
    identificacion = request.args.get("identificacion", "").strip()
    tipo_documento = request.args.get("tipo_documento", "CC").strip()
    vigencia = request.args.get("vigencia", "").strip()
    modelo = request.args.get("modelo", "").strip()
    municipio_transito = request.args.get("municipio_transito", "").strip()
    apellidos_propietario = request.args.get("apellidos_propietario", "").strip()
    nombres_propietario = request.args.get("nombres_propietario", "").strip()

    celular = request.args.get("celular", "").strip() or "3000000000"
    email = request.args.get("email", "").strip() or "consulta@consulta.com"
    direccion = request.args.get("direccion", "").strip() or "CRA"
    municipio_residencia = request.args.get("municipio", "").strip() or "MEDELLIN"
    municipio_cod = request.args.get("municipio_cod", "").strip()
    municipio_cod = int(municipio_cod) if municipio_cod.isdigit() else 5001000
    departamento_cod = request.args.get("departamento_cod", "").strip()
    departamento_cod = int(departamento_cod) if departamento_cod.isdigit() else 5

    if not all([placa, identificacion, vigencia, modelo, municipio_transito, apellidos_propietario]):
        return jsonify({"error": "Faltan parametros: placa, identificacion, vigencia, modelo, municipio_transito, apellidos_propietario"}), 400

    job_id = str(uuid.uuid4())
    job_actualizar(job_id, "Iniciando...", "procesando")

    def ejecutar():
        try:
            job_actualizar(job_id, "Consultando datos guardados del vehículo...")
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT * FROM vehiculos WHERE placa = %s", (placa,))
            fila = cur.fetchone()
            vehiculo = {}
            if fila:
                columnas = [desc[0] for desc in cur.description]
                vehiculo = dict(zip(columnas, fila))
            cur.close(); conn.close()

            job_actualizar(job_id, "Consultando liquidación en la Gobernación (puede tardar por el captcha)...")
            pdf_sugerida_bytes, data_vig = antioquia_generar_pdf_declaracion(
                placa, identificacion, tipo_documento, vigencia,
                modelo, municipio_transito, apellidos_propietario,
                celular=celular, email=email, direccion=direccion,
                municipio=municipio_residencia, municipio_cod=municipio_cod,
                departamento_cod=departamento_cod
            )

            job_actualizar(job_id, "Extrayendo Caja y Tracción del documento...")
            caja_traccion = _extraer_caja_traccion_declaracion(pdf_sugerida_bytes)

            datos = {
                "vigencia": vigencia,
                "nombre_completo": nombres_propietario,
                "apellidos": apellidos_propietario,
                "celular": celular if celular != "3000000000" else "",
                "telefono": "",
                "email": email if email != "consulta@consulta.com" else "",
                "direccion": direccion if direccion != "CRA" else "",
                "municipio_residencia": municipio_residencia,
                "departamento_residencia": "ANTIOQUIA",
                "numero_documento": identificacion,
                "tipo_documento": tipo_documento,

                "placa": placa,
                "marca": vehiculo.get("marca", ""),
                "linea": vehiculo.get("linea", ""),
                "modelo": modelo,
                "clase": vehiculo.get("clase", ""),
                "carroceria": vehiculo.get("carroceria", ""),
                "puertas": vehiculo.get("puertas", ""),
                "cilindraje": vehiculo.get("cilindrada", ""),
                "capacidad_carga": vehiculo.get("capacidad_carga", ""),
                "capacidad_pasajeros": vehiculo.get("capacidad_pasajeros", ""),
                "municipio_matricula": municipio_transito,
                "departamento_matricula": "ANTIOQUIA",
                "blindado": bool(vehiculo.get("info_blindaje")),
                "importado": False,
                "caja": caja_traccion.get("caja", ""),
                "traccion": caja_traccion.get("traccion", ""),

                # Liquidacion privada -- ver nota de mapeo mas abajo
                "avaluo": data_vig.get("avaluoComercial", 0),
                "impuesto": data_vig.get("impuesto", 0),
                "sanciones": data_vig.get("sancion", 0),
                "descuentos": data_vig.get("descuentoSancion", 0),
                "total_cargo_5": data_vig.get("totalCargo", 0),
                "total_cargo_6": data_vig.get("totalCargo", 0),
                "intereses_mora": data_vig.get("interesesMora", 0),
                "pagos_anteriores": data_vig.get("pagosAnteriores", 0),
                "descuento_interes": data_vig.get("descuentoInteresesMora", 0),
                "saldo_favor": data_vig.get("saldoFavor", 0),
                # OJO: se usa "saldoPagar", NO "totalPagar" -- este ultimo
                # incluye el costo de $25.900 del servicio de declaracion
                # sugerida, que no aplica a la declaracion manual.
                "total_pagar": data_vig.get("saldoPagar", 0),
            }

            job_actualizar(job_id, "Generando el documento...")
            id_unico = uuid.uuid4().hex[:8]
            ruta_pdf = f"/tmp/decl_manual_{placa}_{vigencia}_{id_unico}.pdf"
            generar_declaracion_manual_pdf(datos, ruta_pdf)

            url = subir_a_r2(ruta_pdf, f"declaraciones-manuales/{placa}_{vigencia}_{id_unico}.pdf",
                              nombre_descarga=f"Declaracion_Manual_{placa}_{vigencia}.pdf")
            os.remove(ruta_pdf)

            job_terminar(job_id, {"url": url})
        except Exception as e:
            import traceback
            print(traceback.format_exc(), flush=True)
            job_error(job_id, str(e))

    threading.Thread(target=ejecutar, daemon=True).start()
    return jsonify({"job_id": job_id, "estado": "procesando"})


@app.route("/generar-fun", methods=["POST"])
def generar_fun_endpoint():
    """Genera el FUN diligenciado con los datos recibidos, lo sube a R2, y
    devuelve el enlace de descarga. Recibe todo por POST (no se re-consulta
    la base de datos) porque el frontend ya tiene en pantalla justo los
    datos que el usuario confirmo -- incluyendo cosas que no vivimos en
    'vehiculos' (tramite elegido, datos del comprador, etc.)."""
    datos = request.get_json(silent=True) or {}
    placa = (datos.get("placa") or "SINPLACA").upper().strip()

    if not os.path.exists(FUN_PLANTILLA):
        return jsonify({"error": "No se encontro la plantilla AppJX.xlsm en el servidor."}), 500

    id_doc = str(uuid.uuid4())[:10]
    ruta_pdf_local = f"/tmp/FUN_{placa}_{id_doc}.pdf"

    try:
        generar_fun(datos, ruta_pdf_local)
        nombre_remoto = f"fun/{placa}_{id_doc}.pdf"
        url = subir_a_r2(ruta_pdf_local, nombre_remoto)
        os.remove(ruta_pdf_local)
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/generar-estado-cuenta", methods=["GET"])
def generar_estado_cuenta_endpoint():
    """Genera el documento Estado de Cuenta a partir de los datos ya
    guardados (de la ultima vez que esta placa salio a paz y salvo). No
    requiere consulta en vivo ni captcha -- responde directo."""
    placa = request.args.get("placa", "").upper().strip()
    if not placa:
        return jsonify({"error": "Debes proporcionar la placa."}), 400

    if not os.path.exists(FUN_PLANTILLA):
        return jsonify({"error": "No se encontro la plantilla AppJX.xlsm en el servidor."}), 500

    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT estado_cuenta_json, lista_detalle_pagos, lista_proceso_fiscal,
                   lista_bloqueo, novedades, actualizado_en
            FROM estado_cuenta_antioquia WHERE placa = %s
        """, (placa,))
        fila = cur.fetchone()
        cur.close(); conn.close()

        if not fila:
            return jsonify({"error": "No tenemos datos de Estado de Cuenta guardados para esta placa. Debes consultar primero el impuesto departamental (y que el vehículo esté a paz y salvo) antes de poder generar este documento."}), 404

        datos = {
            "estado_veh": fila[0] or {},
            "lista_detalle_pagos": fila[1] or [],
            "lista_proceso_fiscal": fila[2] or [],
            "lista_bloqueo": fila[3] or [],
            "novedades": fila[4] or [],
            # Fecha real en que se consulto y se obtuvo este numero de
            # certificado -- NO la fecha en que se genera el documento,
            # ya que el certificado es unico de esa consulta puntual.
            "fecha_consulta": fila[5],
        }

        id_doc = str(uuid.uuid4())[:10]
        ruta_pdf_local = f"/tmp/EstadoCuenta_{placa}_{id_doc}.pdf"
        generar_estado_cuenta_pdf(datos, ruta_pdf_local)

        nombre_remoto = f"estado-cuenta/{placa}_{id_doc}.pdf"
        url = subir_a_r2(ruta_pdf_local, nombre_remoto,
                          nombre_descarga=f"EstadoCuenta_{placa}.pdf")
        os.remove(ruta_pdf_local)
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/registrar-mi-consulta", methods=["GET"])
def registrar_mi_consulta_endpoint():
    """Registra en el historial personal del usuario que consulto esta
    placa, SIN volver a scrapear el RUNT -- se usa cuando el dato vino del
    cache global, para que igual quede en 'Mis vehiculos consultados'."""
    user_id = request.args.get("user_id", "").strip()
    placa   = request.args.get("placa", "").upper().strip()
    cedula  = request.args.get("cedula", "").strip()
    if not user_id or not placa:
        return jsonify({"error": "Debes proporcionar user_id y placa."}), 400
    ok, error = guardar_mi_consulta(user_id, placa, cedula)
    return jsonify({"ok": ok, "error": error})


@app.route("/mis-vehiculos-runt", methods=["GET"])
def mis_vehiculos_runt():
    """Historial personal: solo las placas que ESTE usuario ha consultado
    en el RUNT antes (a diferencia de /vehiculo-runt-guardado, que es
    global para todos los usuarios). Acepta 'q' opcional para filtrar por
    placa mientras el usuario escribe (la lista puede crecer mucho)."""
    user_id = request.args.get("user_id", "").strip()
    texto   = request.args.get("q", "").upper().strip()
    if not user_id:
        return jsonify({"error": "Debes proporcionar user_id."}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        if texto:
            cur.execute("""
                SELECT v.placa, v.marca, v.linea, v.modelo, mc.actualizado_en, v.fuente
                FROM mis_consultas mc
                JOIN vehiculos v ON v.placa = mc.placa
                WHERE mc.user_id = %s AND v.placa LIKE %s
                ORDER BY mc.actualizado_en DESC LIMIT 8
            """, (user_id, texto + '%'))
        else:
            cur.execute("""
                SELECT v.placa, v.marca, v.linea, v.modelo, mc.actualizado_en, v.fuente
                FROM mis_consultas mc
                JOIN vehiculos v ON v.placa = mc.placa
                WHERE mc.user_id = %s
                ORDER BY mc.actualizado_en DESC LIMIT 8
            """, (user_id,))
        filas = []
        for r in cur.fetchall():
            filas.append({
                "placa": r[0], "marca": r[1], "linea": r[2], "modelo": r[3],
                "actualizado_en": (r[4] - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M") if r[4] else None,
                "fuente": r[5],
            })
        cur.close(); conn.close()
        return jsonify(filas)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/vehiculos-buscar", methods=["GET"])
def vehiculos_buscar():
    """Autocompletado: si hay texto ('q'), devuelve placas que empiecen con
    ese texto; si no hay texto, devuelve las mas recientes -- para que el
    desplegable muestre algo util apenas se abre, antes de escribir nada."""
    prefijo = request.args.get("q", "").upper().strip()
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        if prefijo:
            cur.execute("""
                SELECT placa, marca, linea FROM vehiculos
                WHERE placa LIKE %s ORDER BY leido_en DESC LIMIT 8
            """, (prefijo + '%',))
        else:
            cur.execute("""
                SELECT placa, marca, linea FROM vehiculos
                ORDER BY leido_en DESC LIMIT 8
            """)
        filas = [{"placa": r[0], "marca": r[1], "linea": r[2]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify(filas)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/vehiculo-runt-guardado", methods=["GET"])
def vehiculo_runt_guardado():
    """Trae los datos de RUNT ya guardados para una placa, sin consultar el
    RUNT de nuevo (no tiene costo de 2Captcha). Se usa para que Tramy pueda
    mostrar automaticamente lo que ya se sabe de un vehiculo, y que el
    usuario decida si esta lo bastante reciente o prefiere consultar de nuevo."""
    placa = request.args.get("placa", "").upper().strip()
    if not placa:
        return jsonify({"error": "Debes proporcionar la placa."}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM vehiculos WHERE placa = %s", (placa,))
        fila = cur.fetchone()
        if not fila:
            cur.close(); conn.close()
            return jsonify(None)
        columnas = [desc[0] for desc in cur.description]
        datos = dict(zip(columnas, fila))
        cur.close(); conn.close()
        # Convertir fechas a texto para que se puedan mostrar en JSON.
        # "leido_en" es la unica con hora (las demas son solo fecha), y se
        # guarda en UTC -- se ajusta a hora de Colombia (UTC-5) para mostrar.
        for k, v in datos.items():
            if hasattr(v, "isoformat"):
                if k == "leido_en":
                    datos[k] = (v - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
                else:
                    datos[k] = str(v)
        return jsonify(datos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/consultar/estado", methods=["GET"])
def consultar_estado():
    job_id = request.args.get("job_id", "").strip()
    if not job_id:
        return jsonify({"error": "Falta job_id"}), 400
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT estado, mensaje, resultado FROM consulta_jobs WHERE job_id=%s", (job_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return jsonify({"estado": "no_encontrado"})
        estado, mensaje, resultado = row
        resp = {"estado": estado, "mensaje": mensaje}
        if resultado:
            # Siempre devolver resultado si existe (parcial o final)
            resp["resultado"] = resultado
        if estado == "error":
            resp["error"] = mensaje
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
#  RETEFUENTE
# ============================================================

# Mapeo clase OCR → tabla retefuente
def _normalizar_marca(cur, marca):
    """Si la marca no existe exacta, busca por ILIKE y devuelve la más cercana."""
    cur.execute("SELECT COUNT(*) FROM retefuente_2026 WHERE marca = %s", (marca,))
    if cur.fetchone()[0] > 0:
        return marca
    cur.execute("SELECT DISTINCT marca FROM retefuente_2026 WHERE marca ILIKE %s LIMIT 1", (f"%{marca}%",))
    row = cur.fetchone()
    return row[0] if row else marca


def _es_carga(capacidad):
    """Devuelve True si la capacidad indica carga (kg) en lugar de pasajeros."""
    if not capacidad:
        return False
    cap = str(capacidad).strip().upper().replace('.','').replace(',','')
    # Si contiene KG o KILO es carga
    if 'KG' in cap or 'KILO' in cap or 'TON' in cap:
        return True
    # Si contiene PAX o PASAJERO es pasajeros
    if 'PAX' in cap or 'PASAJERO' in cap or 'PASAJ' in cap:
        return False
    # Si es número puro para CAMIONETA: >=100 = carga (kg), <100 = pasajeros
    try:
        # Limpiar puntos de miles y comas decimales
        cap_clean = re.sub(r'[^0-9]', '', cap)
        num = int(cap_clean)
        # Si el número original tiene punto como separador de miles (ej: 5.610 -> 5610)
        # ya se limpió arriba. Si era 5 pasajeros sería simplemente "5"
        return num >= 100
    except Exception:
        return False


def _tabla_retefuente(clase, carroceria='', capacidad=''):
    clase      = (clase or '').strip().upper()
    carroceria = (carroceria or '').strip().upper()
    if clase in ('AUTOMOVIL', 'AUTOMÓVIL'):                          return 'T1'
    if clase == 'CAMIONETA CARGA' or clase == 'CAMIONETA ESTACAS':   return 'T7'
    if clase == 'CAMIONETA':
        if carroceria == 'DOBLE CABINA':                             return 'T3'
        if _es_carga(capacidad):                                     return 'T7'
        return 'T2'
    if clase in ('CAMPERO',):                                         return 'T2'
    if clase in ('MOTOCICLETA', 'MOTOCARRO'):                         return 'T5'
    if clase in ('BUS', 'BUSETA', 'MICROBUS', 'MICROBÚS'):           return 'T6'
    if clase in ('CAMION', 'CAMIÓN', 'VOLQUETA', 'TRACTOCAMION'):    return 'T7'
    if clase == 'AMBULANCIA':                                         return 'T8'
    return None

def _col_anio(modelo):
    """Devuelve el nombre de columna según el modelo del vehículo."""
    try:
        anio = int(str(modelo).strip())
    except:
        return 'anio_2001_ant'
    if anio <= 2001:
        return 'anio_2001_ant'
    if anio > 2025:
        return 'anio_2025'
    return f'anio_{anio}'



@app.route("/retefuente/marcas-all", methods=["GET"])
def retefuente_marcas_all():
    """Devuelve todas las marcas para una clase (tabla o clase_bd)."""
    clase      = request.args.get("clase", "").strip().upper()
    clase_bd   = request.args.get("clase_bd", "").strip().upper()
    carroceria = request.args.get("carroceria", "").strip().upper()
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        capacidad_m = request.args.get("capacidad","")
        if clase_bd:
            if clase_bd == 'CAMIONETA':
                cur.execute("SELECT DISTINCT marca FROM retefuente_2026 WHERE clase='CAMIONETA' AND tabla='T7' ORDER BY marca")
            else:
                cur.execute("SELECT DISTINCT marca FROM retefuente_2026 WHERE clase=%s ORDER BY marca", (clase_bd,))
        elif clase:
            tabla = _tabla_retefuente(clase, carroceria, request.args.get('capacidad',''))
            if tabla:
                cur.execute("SELECT DISTINCT marca FROM retefuente_2026 WHERE tabla=%s ORDER BY marca", (tabla,))
            else:
                cur.execute("SELECT DISTINCT marca FROM retefuente_2026 ORDER BY marca")
        else:
            cur.execute("SELECT DISTINCT marca FROM retefuente_2026 ORDER BY marca")
        marcas = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"marcas": marcas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/retefuente/lineas", methods=["GET"])
def retefuente_lineas():
    """Devuelve las lineas para una marca (y opcionalmente clase o clase_bd)."""
    marca      = request.args.get("marca", "").strip().upper()
    clase      = request.args.get("clase", "").strip().upper()
    clase_bd   = request.args.get("clase_bd", "").strip().upper()
    carroceria = request.args.get("carroceria", "").strip().upper()
    if not marca:
        return jsonify({"error": "Debes enviar marca."}), 400
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        capacidad = request.args.get('capacidad','')
        capacidad_l = request.args.get("capacidad","")
        marca = _normalizar_marca(cur, marca)
        if clase_bd:
            if clase_bd == 'CAMIONETA':
                # clase_bd=CAMIONETA significa explícitamente camioneta de carga → T7
                cur.execute("SELECT DISTINCT linea FROM retefuente_2026 WHERE marca=%s AND clase='CAMIONETA' AND tabla='T7' ORDER BY linea", (marca,))
            else:
                cur.execute("SELECT DISTINCT linea FROM retefuente_2026 WHERE marca=%s AND clase=%s ORDER BY linea", (marca, clase_bd))
        elif clase:
            tabla = _tabla_retefuente(clase, carroceria, capacidad)
            if tabla:
                cur.execute("SELECT DISTINCT linea FROM retefuente_2026 WHERE marca=%s AND tabla=%s ORDER BY linea", (marca, tabla))
            else:
                cur.execute("SELECT DISTINCT linea FROM retefuente_2026 WHERE marca=%s ORDER BY linea", (marca,))
        else:
            cur.execute("SELECT DISTINCT linea FROM retefuente_2026 WHERE marca=%s ORDER BY linea", (marca,))
        lineas = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"lineas": lineas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/retefuente/modelos", methods=["GET"])
def retefuente_modelos():
    """Devuelve los modelos (anos) disponibles."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'retefuente_2026'
              AND column_name LIKE 'anio_%'
            ORDER BY column_name DESC
        """)
        modelos = [r[0].replace('anio_', '').replace('_ant', ' y anteriores') for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"modelos": modelos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/retefuente/opciones", methods=["GET"])
def retefuente_opciones():
    """
    Devuelve todas las opciones para marca+linea+modelo+cilindraje.
    Cilindraje >= al ingresado. Incluye clase, tonelaje, pasajeros.
    """
    marca      = request.args.get("marca", "").strip().upper()
    linea      = request.args.get("linea", "").strip().upper()
    clase      = request.args.get("clase", "").strip().upper()
    carroceria = request.args.get("carroceria", "").strip().upper()
    modelo     = request.args.get("modelo", "").strip()
    cilindraje = request.args.get("cilindraje", "0").strip()

    if not marca or not modelo:
        return jsonify({"error": "Debes enviar marca y modelo."}), 400

    # Normalizar modelo — acepta año libre, "2001 y anteriores", etc.
    modelo_norm = modelo.replace(" y anteriores", "").replace("_ant", "").strip()
    try:
        anio_int = int(modelo_norm)
    except:
        return jsonify({"error": "Modelo invalido."}), 400
    col_anio = _col_anio(str(anio_int))

    try:
        # Limpiar puntos de miles y comas decimales (ej: 3.760 -> 3760)
        cil = int(re.sub(r'[^0-9]', '', cilindraje)) if cilindraje else 0
    except:
        cil = 0

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        marca  = _normalizar_marca(cur, marca)
        where  = ["marca = %s", f"{col_anio} > 0"]
        params = [marca]

        if linea:
            palabras = [p for p in linea.split() if len(p) > 2][:3]
            for p in palabras:
                where.append("linea ILIKE %s")
                params.append(f'%{p}%')

        clase_bd   = request.args.get("clase_bd", "").strip().upper()
        capacidad  = request.args.get("capacidad", "")
        if clase_bd:
            if clase_bd == 'CAMIONETA':
                where.append("clase = 'CAMIONETA'")
                where.append("tabla = 'T7'")
            else:
                where.append("clase = %s")
                params.append(clase_bd)
        elif clase:
            tabla = _tabla_retefuente(clase, carroceria, capacidad)
            if tabla:
                where.append("tabla = %s")
                params.append(tabla)

        if cil > 0:
            where.append("cilindraje >= %s")
            params.append(cil)

        sql = f"""
            SELECT marca, linea, cilindraje, tabla, {col_anio} as avaluo,
                   clase, tonelaje, pasajeros
            FROM retefuente_2026
            WHERE {' AND '.join(where)}
            ORDER BY cilindraje ASC
            LIMIT 40
        """
        cur.execute(sql, params)
        rows = cur.fetchall()

        # Si no hay resultados con filtro de linea, buscar sin él
        if not rows and linea:
            where2  = ["marca = %s", f"{col_anio} > 0"]
            params2 = [marca]
            if clase_bd:
                if clase_bd == 'CAMIONETA':
                    where2.append("clase = 'CAMIONETA'")
                    where2.append("tabla = 'T7'")
                else:
                    where2.append("clase = %s")
                    params2.append(clase_bd)
            elif clase:
                tabla = _tabla_retefuente(clase, carroceria, capacidad)
                if tabla:
                    where2.append("tabla = %s")
                    params2.append(tabla)
            if cil > 0:
                where2.append("cilindraje >= %s")
                params2.append(cil)
            cil_dist2 = f"ABS(cilindraje - {cil})," if cil > 0 else ""
            sql2 = f"""
                SELECT marca, linea, cilindraje, tabla, {col_anio} as avaluo,
                       clase, tonelaje, pasajeros
                FROM retefuente_2026
                WHERE {' AND '.join(where2)}
                ORDER BY {cil_dist2} cilindraje ASC
                LIMIT 20
            """
            cur.execute(sql2, params2)
            rows = cur.fetchall()

        # Ordenar en Python: 1) cilindraje más cercano, 2) mayor coincidencia con línea del OCR
        linea_words = [w.upper() for w in linea.split() if len(w) > 1][:5] if linea else []
        def score_row(r):
            cil_r    = r[2] or 0
            cil_dist = abs(cil_r - cil) if cil > 0 else cil_r
            lin_score = sum(1 for w in linea_words if w in (r[1] or '').upper())
            return (cil_dist, -lin_score)
        rows = sorted(rows, key=score_row)[:20]

        cur.close(); conn.close()

        TABLA_CLASE = {
            'T1':'Automóvil','T2':'Campero/Camioneta','T3':'Camioneta D.C.',
            'T4':'Eléctrico','T5':'Motocicleta','T6':'Bus/Buseta',
            'T7':'Camión/Volqueta','T8':'Ambulancia','T9':'Híbrido'
        }

        opciones = []
        for r in rows:
            op = {
                "marca":      r[0],
                "linea":      r[1],
                "cilindraje": r[2],
                "tabla":      r[3],
                "avaluo":     r[4],
                "retefuente": round(r[4] / 100) if r[4] else 0,
                "clase_veh":  r[5] or TABLA_CLASE.get(r[3], r[3]),
                "tonelaje":    float(r[6]) if r[6] else None,
                "tonelaje_kg": int(float(r[6]) * 1000) if r[6] else None,
                "pasajeros":   r[7] if r[7] else None,
            }
            opciones.append(op)

        return jsonify({"opciones": opciones})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/retefuente/buscar", methods=["GET"])
def retefuente_buscar():
    """
    Busca opciones de retefuente según marca, clase, carroceria y modelo.
    Devuelve lista de opciones para que el usuario elija.
    """
    marca      = request.args.get("marca", "").strip().upper()
    linea      = request.args.get("linea", "").strip().upper()
    clase      = request.args.get("clase", "").strip().upper()
    carroceria = request.args.get("carroceria", "").strip().upper()
    modelo     = request.args.get("modelo", "").strip()
    cilindraje = request.args.get("cilindraje", "0").strip()

    if not marca or not clase or not modelo:
        return jsonify({"error": "Debes enviar marca, clase y modelo."}), 400

    tabla = _tabla_retefuente(clase, carroceria, request.args.get('capacidad',''))
    if not tabla:
        return jsonify({"error": f"Clase '{clase}' no tiene tabla de retefuente."}), 400

    col_anio = _col_anio(modelo)

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        # Cilindraje del vehículo para filtrar — mostrar desde (cilindraje - 100) hacia arriba
        try:
            cil_vehiculo = int(cilindraje) if cilindraje else 0
        except:
            cil_vehiculo = 0
        cil_min = max(0, cil_vehiculo - 50) if cil_vehiculo > 0 else 0

        # Función auxiliar para construir query con filtro cilindraje
        def query_retefuente(where_extra, params_extra, cil_desde, limite=8):
            cil_cond = f"AND cilindraje >= {cil_desde}" if cil_desde > 0 else ""
            order = f"CASE WHEN cilindraje >= {cil_vehiculo} THEN cilindraje ELSE cilindraje + 999999 END, linea"
            sql = f"""
                SELECT id, marca, linea, cilindraje, {col_anio} as avaluo
                FROM retefuente_2026
                WHERE tabla = %s AND marca = %s {where_extra} {cil_cond} AND {col_anio} > 0
                ORDER BY {order}
                LIMIT {limite}
            """
            cur.execute(sql, [tabla, marca] + params_extra)
            return cur.fetchall()

        # Buscar solo cilindraje >= vehiculo (exacto o superior)
        rows = []
        palabras = [p for p in linea.split() if len(p) > 2][:3]

        # 1. Con palabras de la línea + cilindraje >= vehiculo
        if palabras and linea:
            like_conds = " AND ".join(["linea ILIKE %s" for _ in palabras])
            rows = query_retefuente(f"AND {like_conds}", [f'%{p}%' for p in palabras], cil_vehiculo)

        # 2. Línea base estándar + cilindraje >= vehiculo
        if not rows:
            rows = query_retefuente(
                "AND (linea ILIKE %s OR linea ILIKE %s)",
                ['%LINEA BASE%', '%BASE ESTANDAR%'], cil_vehiculo
            )

        # 3. Todas las líneas de esa marca + cilindraje >= vehiculo
        if not rows:
            rows = query_retefuente("", [], cil_vehiculo)

        cur.close()
        conn.close()

        opciones = [{
            "id":         r[0],
            "marca":      r[1],
            "linea":      r[2],
            "cilindraje": r[3],
            "avaluo":     r[4],
            "retefuente": round(r[4] / 100) if r[4] else 0
        } for r in rows]

        return jsonify({
            "tabla":   tabla,
            "col_anio": col_anio,
            "opciones": opciones,
            "total":   len(opciones)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/retefuente/marcas", methods=["GET"])
def retefuente_marcas():
    """Devuelve lista de marcas disponibles para una tabla."""
    clase      = request.args.get("clase", "").strip().upper()
    carroceria = request.args.get("carroceria", "").strip().upper()
    tabla = _tabla_retefuente(clase, carroceria, request.args.get('capacidad',''))
    if not tabla:
        return jsonify({"error": "Clase no reconocida"}), 400
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT DISTINCT marca FROM retefuente_2026 WHERE tabla=%s ORDER BY marca", (tabla,))
        marcas = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"marcas": marcas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tramites/filtros", methods=["GET"])
def tramites_filtros():
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        campo        = request.args.get("campo", "")
        departamento = request.args.get("departamento", "").strip().upper()
        municipio    = request.args.get("municipio", "").strip().upper()
        clase        = request.args.get("clase", "").strip().upper()
        if campo == "departamento" and municipio:
            cur.execute("SELECT DISTINCT departamento FROM tramites_transito WHERE municipio=%s ORDER BY departamento LIMIT 1", (municipio,))
        elif campo == "departamento":
            cur.execute("SELECT DISTINCT departamento FROM tramites_transito ORDER BY departamento")
        elif campo == "municipio" and departamento:
            cur.execute("SELECT DISTINCT municipio FROM tramites_transito WHERE departamento=%s ORDER BY municipio", (departamento,))
        elif campo == "municipio" and not departamento:
            cur.execute("SELECT DISTINCT municipio FROM tramites_transito ORDER BY municipio")
        elif campo == "clase" and municipio:
            cur.execute("SELECT DISTINCT clase FROM tramites_transito WHERE municipio=%s ORDER BY clase", (municipio,))
        elif campo == "tramite" and municipio and clase:
            cur.execute("SELECT DISTINCT tramite FROM tramites_transito WHERE municipio=%s AND clase=%s ORDER BY tramite", (municipio, clase))
        else:
            cur.close(); conn.close()
            return jsonify({"error": "Parametros insuficientes"}), 400
        valores = [row[0] for row in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"valores": valores})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tramites/precio", methods=["GET"])
def tramites_precio():
    departamento = request.args.get("departamento", "").strip().upper()
    municipio    = request.args.get("municipio", "").strip().upper()
    clase        = request.args.get("clase", "").strip().upper()
    tramite      = request.args.get("tramite", "").strip().upper()
    if not all([departamento, municipio, clase, tramite]):
        return jsonify({"error": "Debes enviar departamento, municipio, clase y tramite"}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT precio FROM tramites_transito WHERE departamento=%s AND municipio=%s AND clase=%s AND tramite=%s LIMIT 1", (departamento, municipio, clase, tramite))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return jsonify({"departamento": departamento, "municipio": municipio, "clase": clase, "tramite": tramite, "precio": row[0]})
        return jsonify({"error": "No se encontro el tramite"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ SOAT ============

@app.route("/soat/clases", methods=["GET"])
def soat_clases():
    """Devuelve las clases de vehiculo disponibles, en orden de tarifa (1-9)."""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT tarifa, clase_vehiculo FROM soat_tarifas
            WHERE periodo = 2026 ORDER BY tarifa
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify([{"tarifa": r[0], "clase_vehiculo": r[1]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/soat/opciones", methods=["GET"])
def soat_opciones():
    """Devuelve las descripciones (cilindraje/toneladas/pasajeros) para una clase dada."""
    clase = request.args.get("clase", "").strip().upper()
    if not clase:
        return jsonify({"error": "Debes enviar clase"}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT codigo, descripcion FROM soat_tarifas
            WHERE periodo = 2026 AND clase_vehiculo = %s ORDER BY codigo
        """, (clase,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify([{"codigo": r[0], "descripcion": r[1]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/soat/modelos", methods=["GET"])
def soat_modelos():
    """Devuelve los rangos de modelo disponibles (si aplica) para clase+descripcion."""
    clase       = request.args.get("clase", "").strip().upper()
    descripcion = request.args.get("descripcion", "").strip()
    if not clase or not descripcion:
        return jsonify({"error": "Debes enviar clase y descripcion"}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT codigo, modelo FROM soat_tarifas
            WHERE periodo = 2026 AND clase_vehiculo = %s AND descripcion = %s
            ORDER BY codigo
        """, (clase, descripcion))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify([{"codigo": r[0], "modelo": r[1]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/soat/precio", methods=["GET"])
def soat_precio():
    """Precio final. 'codigo' es suficiente si ya se conoce (mas directo),
    o se puede armar con clase+descripcion+modelo."""
    codigo = request.args.get("codigo", "").strip()
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        if codigo:
            cur.execute("SELECT clase_vehiculo, descripcion, modelo, valor FROM soat_tarifas WHERE periodo=2026 AND codigo=%s", (codigo,))
        else:
            clase       = request.args.get("clase", "").strip().upper()
            descripcion = request.args.get("descripcion", "").strip()
            modelo      = request.args.get("modelo", "").strip()
            if not clase:
                return jsonify({"error": "Debes enviar codigo, o al menos clase"}), 400
            if descripcion and modelo:
                cur.execute("SELECT clase_vehiculo, descripcion, modelo, valor FROM soat_tarifas WHERE periodo=2026 AND clase_vehiculo=%s AND descripcion=%s AND modelo=%s", (clase, descripcion, modelo))
            elif descripcion:
                cur.execute("SELECT clase_vehiculo, descripcion, modelo, valor FROM soat_tarifas WHERE periodo=2026 AND clase_vehiculo=%s AND descripcion=%s", (clase, descripcion))
            else:
                cur.execute("SELECT clase_vehiculo, descripcion, modelo, valor FROM soat_tarifas WHERE periodo=2026 AND clase_vehiculo=%s", (clase,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return jsonify({"clase_vehiculo": row[0], "descripcion": row[1], "modelo": row[2], "valor": row[3]})
        return jsonify({"error": "No se encontro tarifa SOAT para esos criterios"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ TECNOMECANICA ============

@app.route("/tecnomecanica/categorias", methods=["GET"])
def tecnomecanica_categorias():
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT categoria, valor FROM tecnomecanica_tarifas WHERE periodo = 2026 ORDER BY id")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify([{"categoria": r[0], "valor": r[1]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tecnomecanica/precio", methods=["GET"])
def tecnomecanica_precio():
    categoria = request.args.get("categoria", "").strip()
    if not categoria:
        return jsonify({"error": "Debes enviar categoria"}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT valor FROM tecnomecanica_tarifas WHERE periodo = 2026 AND categoria = %s", (categoria,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return jsonify({"categoria": categoria, "valor": row[0]})
        return jsonify({"error": "No se encontro esa categoria"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ COMPARENDOS ============

@app.route("/comparendos/buscar", methods=["GET"])
def comparendos_buscar():
    """Busca por codigo exacto o por palabra clave dentro de la descripcion."""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT codigo, descripcion, valor, valor_desc_50, valor_desc_25 FROM comparendos_tarifas
            WHERE periodo = 2026 AND (codigo ILIKE %s OR descripcion ILIKE %s)
            ORDER BY codigo LIMIT 20
        """, (f"{q}%", f"%{q}%"))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify([{"codigo": r[0], "descripcion": r[1], "valor": r[2], "valor_desc_50": r[3], "valor_desc_25": r[4]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/comparendos/precio", methods=["GET"])
def comparendos_precio():
    codigo = request.args.get("codigo", "").strip().upper()
    if not codigo:
        return jsonify({"error": "Debes enviar codigo"}), 400
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT descripcion, valor, valor_desc_50, valor_desc_25 FROM comparendos_tarifas WHERE periodo = 2026 AND codigo = %s", (codigo,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return jsonify({"codigo": codigo, "descripcion": row[0], "valor": row[1], "valor_desc_50": row[2], "valor_desc_25": row[3]})
        return jsonify({"error": "No se encontro esa infraccion"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/reportar", methods=["POST"])
def reportar():
    try:
        data      = request.get_json()
        tipo      = data.get("tipo", "").strip()
        comentario = data.get("comentario", "").strip()
        placa     = data.get("placa", "").strip().upper()
        municipio = data.get("municipio", "").strip().upper()
        pagina    = data.get("pagina", "").strip()
        if not tipo:
            return jsonify({"ok": False, "error": "Tipo requerido"}), 400
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO reportes_usuarios (tipo, comentario, placa, municipio, pagina)
            VALUES (%s, %s, %s, %s, %s)
        """, (tipo, comentario, placa, municipio, pagina))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/reportar/lista", methods=["GET"])
def reportar_lista():
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, tipo, comentario, placa, municipio, pagina, creado_en
            FROM reportes_usuarios
            ORDER BY creado_en DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"reportes": [{
            "id": r[0], "tipo": r[1], "comentario": r[2],
            "placa": r[3], "municipio": r[4], "pagina": r[5],
            "fecha": str(r[6])
        } for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/reportar/eliminar/<int:reporte_id>", methods=["DELETE"])
def reportar_eliminar(reporte_id):
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM reportes_usuarios WHERE id = %s", (reporte_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500





@app.route("/ocr-tarjeta", methods=["POST"])
def ocr_tarjeta():
    try:
        data = request.get_json()
        if not data or "imagen" not in data:
            return jsonify({"error": "No se recibio imagen"}), 400

        def preparar_archivo(img_data):
            es_pdf = "data:application/pdf" in img_data
            media_type = "application/pdf" if es_pdf else "image/jpeg"
            if not es_pdf:
                if "data:image/png" in img_data:
                    media_type = "image/png"
                elif "data:image/webp" in img_data:
                    media_type = "image/webp"
            if "," in img_data:
                img_data = img_data.split(",")[1]
            if es_pdf:
                return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": img_data}}
            return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}}

        # Puede venir un solo archivo (imagen o PDF con ambas caras), o dos
        # archivos separados (ej: foto de la cara frontal + foto de la cara
        # trasera, subidas por separado). Ambos se envian juntos a Claude.
        archivos_content = [preparar_archivo(data["imagen"])]
        if data.get("imagen2"):
            archivos_content.append(preparar_archivo(data["imagen2"]))

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_key:
            return jsonify({"error": "API Key de Anthropic no configurada"}), 500

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-opus-4-5", "max_tokens": 600, "messages": [{"role": "user", "content": archivos_content + [
                {"type": "text", "text": "Eres un experto en leer tarjetas/licencias de tránsito y documentos de impuestos vehiculares de Colombia. Puedes recibir UNO o DOS archivos (imagenes y/o PDFs): si recibes dos, son la cara frontal y la cara trasera de la MISMA tarjeta, subidas por separado — analiza ambos como si fueran las dos caras de un mismo documento. Cada archivo puede incluir SOLO la cara frontal, SOLO la cara trasera, o AMBAS caras. Los archivos pueden estar rotados o de lado (esto es MUY comun en fotos, especialmente de la cara trasera) — gira mentalmente el texto para leerlo sin importar su orientacion. Analiza TODOS los caracteres con mucho cuidado especialmente los numeros. Extrae: 1. PLACA (exactamente 3 letras + 3 numeros, verifica cada caracter) 2. MARCA del vehiculo 3. LINEA del vehiculo 4. MODELO (anno 4 digitos) 5. CLASE (automovil, motocicleta, campero, camioneta, etc) 6. SERVICIO (particular, publico, oficial) 7. CAPACIDAD (numero de pasajeros o carga) 8. CILINDRADA (numero en cc) 9. TIPO_DOCUMENTO (uno de: C.C, NIT, P.P.T, T.I, R.C - aparece debajo de IDENTIFICACION al lado izquierdo del numero) 10. CEDULA (numero de identificacion, verifica TODOS los digitos uno por uno, no omitas ninguno) 11. NOMBRE_COMPLETO del propietario: la tarjeta suele tener dos campos separados, 'APELLIDOS' y 'NOMBRES' -- combina AMBOS en un solo texto (ej. si dice Apellidos: GARCIA PEREZ y Nombres: JUAN CARLOS, responde 'GARCIA PEREZ JUAN CARLOS'). Si solo encuentras un campo con el nombre completo ya junto, cópialo tal cual. Nunca dejes fuera los nombres de pila, solo los apellidos no es una respuesta completa. 12. MUNICIPIO: este dato SOLO aparece en la cara TRASERA. Hay dos formatos posibles, busca cualquiera de los dos: (a) un campo llamado 'MUNICIPIO DE MATRICULA' (o similar, ej. 'Municipio Matricula') — en este caso el valor de ese campo ES DIRECTAMENTE el nombre del municipio, cópialo tal cual. (b) un campo llamado 'ORGANISMO DE TRANSITO', que casi siempre viene ABREVIADO de forma variable, por ejemplo 'STRIA TTEYTTO ENVIGADO' o 'STRIA DE TTOYTTE MEDELLIN' — ambos significan 'Secretaria de Transito y Transporte de <MUNICIPIO>'. El patron general es: unas siglas abreviadas de 'Secretaria de Transito y Transporte' seguidas del NOMBRE DEL MUNICIPIO al final del texto. En este caso extrae SOLAMENTE el nombre del municipio (la ultima palabra o palabras), sin ninguna de las siglas ni abreviaturas que la preceden. Si la cara trasera no esta visible en ninguno de los archivos, deja este campo vacio, NO lo inventes ni lo asumas. 13. LIMITACION_PROPIEDAD: este dato tambien esta SOLO en la cara TRASERA. SOLO debes responder algo distinto de vacio si encuentras EXACTAMENTE uno de estos dos patrones — si no encuentras ninguno de los dos (por ejemplo la cara trasera no esta visible, o esta borrosa, o no aparece ninguno de estos campos), deja el valor VACIO, NUNCA asumas ni adivines: (a) un campo llamado 'LIMITACION A LA PROPIEDAD' — debajo de ese titulo puede aparecer una serie de ASTERISCOS (ej: '******'), lo que significa que el vehiculo NO tiene ningun gravamen (responde 'NINGUNA', nunca copies los asteriscos tal cual); o puede aparecer el nombre de una persona natural o juridica (ej: 'PRENDA - BANCO FINANDINA', 'PRENDA - BANCO DE OCCIDENTE'), lo que significa que SI tiene gravamen (copia el valor completo tal cual aparece). (b) un campo llamado 'GRAVAMENES A LA PROPIEDAD' con una respuesta directa 'SI' o 'NO' — si dice 'SI' responde 'SI' (tiene gravamen), si dice 'NO' responde 'NINGUNA' (no tiene gravamen). Recuerda: si no ves con claridad ninguno de estos dos campos, deja limitacion_propiedad vacio — es preferible dejarlo vacio a arriesgarte a decir que no tiene gravamen cuando en realidad no pudiste verificarlo. 14. ES_DECLARACION_ANTIOQUIA: true SOLO si alguno de los archivos es un documento titulado 'DECLARACION SUGERIDA DE IMPUESTOS SOBRE VEHICULOS AUTOMOTORES' emitido por la Gobernacion de Antioquia. Si es asi, ademas: (a) el SERVICIO de este vehiculo SIEMPRE es 'PARTICULAR' (este tipo de documento solo se emite para vehiculos particulares), pon SERVICIO='PARTICULAR' sin importar lo que digan otros campos. (b) DECLARACION_VIGENCIA: el año de la vigencia que se esta declarando/pagando, normalmente aparece en la zona superior izquierda del documento (ej: 'Vigencia 2026' o similar — copia solo el numero de 4 digitos del año). (c) DECLARACION_PAGADO: true si el documento tiene un SELLO DE BANCO O ENTIDAD FINANCIERA que indique que fue pagado (busca sellos, timbres, o textos como 'PAGADO', 'RECIBIDO', nombre de un banco estampado, codigos de transaccion bancaria, etc). false si no hay ningun sello o indicio de pago. (d) DECLARACION_AVALUO: el valor del avaluo comercial del vehiculo que aparece en ese mismo documento (solo el numero, sin simbolos de moneda ni puntos de miles). Si el archivo NO es este tipo de documento, deja ES_DECLARACION_ANTIOQUIA en false y los demas campos de declaracion vacios. Responde SOLO en JSON sin explicaciones: {\"placa\": \"\", \"marca\": \"\", \"linea\": \"\", \"modelo\": \"\", \"clase\": \"\", \"servicio\": \"\", \"capacidad\": \"\", \"cilindrada\": \"\", \"carroceria\": \"\", \"tipo_documento\": \"\", \"cedula\": \"\", \"apellidos\": \"\", \"municipio\": \"\", \"limitacion_propiedad\": \"\", \"es_declaracion_antioquia\": false, \"declaracion_vigencia\": \"\", \"declaracion_pagado\": false, \"declaracion_avaluo\": \"\"}"}
            ]}]},
            timeout=120
        )
        if response.status_code != 200:
            return jsonify({"error": f"Error Claude API: {response.status_code}"}), 500
        resp_data = response.json()
        texto = resp_data["content"][0]["text"].strip()
        import json as json_lib, re as re_module
        texto_clean = texto.replace("```json", "").replace("```", "").strip()
        json_match = re_module.search(r'\{[^{}]*\}', texto_clean, re_module.DOTALL)
        if not json_match:
            return jsonify({"error": "No se pudo parsear respuesta de Claude"}), 500
        resultado = json_lib.loads(json_match.group())
        placa                = resultado.get("placa", "").upper().replace(" ", "").replace("-", "")
        marca                = resultado.get("marca", "").upper().strip()
        linea                = resultado.get("linea", "").upper().strip()
        modelo               = resultado.get("modelo", "").strip()
        clase                = resultado.get("clase", "").upper().strip()
        servicio             = resultado.get("servicio", "").upper().strip()
        capacidad            = resultado.get("capacidad", "").strip()
        cilindrada           = resultado.get("cilindrada", "").strip()
        carroceria           = resultado.get("carroceria", "").upper().strip()
        tipo_documento       = resultado.get("tipo_documento", "").upper().strip()
        cedula               = resultado.get("cedula", "").strip()
        apellidos            = resultado.get("apellidos", "").upper().strip()
        municipio            = resultado.get("municipio", "").upper().strip()
        limitacion_propiedad = resultado.get("limitacion_propiedad", "").strip()

        # Declaración Sugerida de Impuestos sobre Vehículos Automotores (Gobernación de Antioquia)
        es_declaracion_antioquia = bool(resultado.get("es_declaracion_antioquia"))
        paz_salvo_detectado = False
        if es_declaracion_antioquia:
            # 1. Este tipo de documento solo se emite para vehiculos particulares
            servicio = "PARTICULAR"

            # 2. Si tiene sello de pago Y la vigencia es el año actual -> paz y salvo
            declaracion_pagado = bool(resultado.get("declaracion_pagado"))
            declaracion_vigencia_raw = str(resultado.get("declaracion_vigencia", "")).strip()
            declaracion_avaluo_raw = str(resultado.get("declaracion_avaluo", "")).strip()
            anio_actual = datetime.now().year  # siempre el año actual real, nunca fijo

            try:
                declaracion_vigencia = int(re.sub(r"[^\d]", "", declaracion_vigencia_raw)) if declaracion_vigencia_raw else 0
            except ValueError:
                declaracion_vigencia = 0
            try:
                declaracion_avaluo = int(re.sub(r"[^\d]", "", declaracion_avaluo_raw)) if declaracion_avaluo_raw else 0
            except ValueError:
                declaracion_avaluo = 0

            if declaracion_pagado and declaracion_vigencia == anio_actual and placa and declaracion_avaluo > 0:
                cache_antioquia_guardar_paz_salvo(placa, declaracion_avaluo, {})
                paz_salvo_detectado = True

        return jsonify({"placa": placa, "marca": marca, "linea": linea, "modelo": modelo, "clase": clase, "servicio": servicio, "capacidad": capacidad, "cilindrada": cilindrada, "carroceria": carroceria, "tipo_documento": tipo_documento, "cedula": cedula, "apellidos": apellidos, "municipio": municipio, "limitacion_propiedad": limitacion_propiedad, "paz_salvo_antioquia_detectado": paz_salvo_detectado, "desde_cache": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ocr-runt-texto", methods=["POST"])
def ocr_runt_texto():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400
        texto_placa  = (data.get("texto_placa") or "").strip()
        texto_cedula = (data.get("texto_cedula") or "").strip()
        if not texto_placa and not texto_cedula:
            return jsonify({"error": "Debes pegar al menos un texto"}), 400

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_key:
            return jsonify({"error": "API Key de Anthropic no configurada"}), 500

        texto_combinado = ""
        if texto_placa:
            texto_combinado += "=== TEXTO COPIADO DEL RUNT — CONSULTA POR PLACA (datos del VEHICULO) ===\n" + texto_placa + "\n\n"
        if texto_cedula:
            texto_combinado += "=== TEXTO COPIADO DEL RUNT — CONSULTA POR CEDULA (datos del PROPIETARIO/CONDUCTOR) ===\n" + texto_cedula

        prompt = (
            "Eres un experto en interpretar texto copiado y pegado directamente del portal RUNT "
            "(Registro Unico Nacional de Transito de Colombia). Te voy a dar el texto plano que un "
            "usuario copio de la pagina de resultados del RUNT — puede ser de una consulta por PLACA "
            "(trae datos del vehiculo), por CEDULA (trae datos del propietario/conductor), o ambas. "
            "El texto puede venir desordenado, con saltos de linea irregulares, o con texto de menus/"
            "botones de la pagina mezclado — ignora ese ruido y concentrate en los datos reales. "
            "Extrae los siguientes datos si estan presentes en cualquiera de los dos textos: "
            "1. PLACA 2. MARCA 3. LINEA 4. MODELO (año) 5. CLASE 6. SERVICIO 7. CAPACIDAD "
            "8. CILINDRADA (cc) 9. TIPO_DOCUMENTO (C.C, NIT, C.E, T.I, R.C, P.P.T) "
            "10. CEDULA (numero de identificacion del propietario) 11. APELLIDOS (y nombres) del "
            "propietario 12. MUNICIPIO: hay dos formatos posibles, busca cualquiera de los dos: "
            "(a) un campo llamado 'MUNICIPIO DE MATRICULA' (o similar, ej. 'Municipio Matricula') — en "
            "este caso el valor de ese campo ES DIRECTAMENTE el nombre del municipio, cópialo tal cual. "
            "(b) un campo llamado 'Organismo de Transito' u 'Organismo de Transito Matricula', casi "
            "siempre ABREVIADO de forma variable, por ejemplo "
            "'STRIA TTEYTTO ENVIGADO' o 'STRIA DE TTOYTTE MEDELLIN' — ambos significan 'Secretaria de "
            "Transito y Transporte de <MUNICIPIO>'. El patron general es: unas siglas abreviadas de "
            "'Secretaria de Transito y Transporte' seguidas del NOMBRE DEL MUNICIPIO al final del texto. "
            "En este caso extrae SOLAMENTE el nombre del municipio (la ultima palabra o palabras), sin "
            "ninguna de las siglas ni abreviaturas que la preceden (nunca dejes 'STRIA', 'TTEYTTO', "
            "'SRIA', 'SECRETARIA' ni similares como parte del valor). Si no aparece ese dato en el "
            "texto, deja el campo vacio, no lo inventes. 13. LIMITACION_PROPIEDAD (gravamenes, prenda "
            "a favor de alguna entidad, o 'NINGUNA' si no tiene). SOLO debes responder algo distinto de "
            "vacio si encuentras EXACTAMENTE uno de estos dos patrones — si no encuentras ninguno, deja "
            "el valor VACIO, nunca asumas ni adivines: (a) un campo 'Limitacion a la Propiedad' — si "
            "aparece con una serie de asteriscos como '******', eso significa 'NINGUNA' (nunca copies "
            "los asteriscos tal cual); si aparece el nombre de una persona o entidad, copia ese valor "
            "tal cual (tiene gravamen). (b) un campo 'Gravamenes a la Propiedad' con respuesta directa "
            "SI o NO — si dice SI responde 'SI' (tiene gravamen), si dice NO responde 'NINGUNA' (no "
            "tiene gravamen). Es preferible dejarlo vacio a arriesgarte a decir que no tiene gravamen "
            "cuando en realidad no pudiste verificarlo. Si un dato no aparece en el texto, "
            "deja ese campo vacio, NO lo inventes ni lo asumas. Responde SOLO en JSON sin explicaciones: "
            "{\"placa\": \"\", \"marca\": \"\", \"linea\": \"\", \"modelo\": \"\", \"clase\": \"\", "
            "\"servicio\": \"\", \"capacidad\": \"\", \"cilindrada\": \"\", \"carroceria\": \"\", "
            "\"tipo_documento\": \"\", \"cedula\": \"\", \"apellidos\": \"\", \"municipio\": \"\", "
            "\"limitacion_propiedad\": \"\"}\n\nTEXTO A ANALIZAR:\n" + texto_combinado
        )

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-opus-4-5", "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]},
            timeout=90
        )
        if response.status_code != 200:
            return jsonify({"error": f"Error Claude API: {response.status_code}"}), 500
        resp_data = response.json()
        texto_resp = resp_data["content"][0]["text"].strip()
        import json as json_lib, re as re_module
        texto_clean = texto_resp.replace("```json", "").replace("```", "").strip()
        json_match = re_module.search(r'\{[^{}]*\}', texto_clean, re_module.DOTALL)
        if not json_match:
            return jsonify({"error": "No se pudo parsear respuesta"}), 500
        resultado = json_lib.loads(json_match.group())
        placa                = resultado.get("placa", "").upper().replace(" ", "").replace("-", "")
        marca                = resultado.get("marca", "").upper().strip()
        linea                = resultado.get("linea", "").upper().strip()
        modelo               = resultado.get("modelo", "").strip()
        clase                = resultado.get("clase", "").upper().strip()
        servicio             = resultado.get("servicio", "").upper().strip()
        capacidad            = resultado.get("capacidad", "").strip()
        cilindrada           = resultado.get("cilindrada", "").strip()
        carroceria           = resultado.get("carroceria", "").upper().strip()
        tipo_documento       = resultado.get("tipo_documento", "").upper().strip()
        cedula               = resultado.get("cedula", "").strip()
        apellidos            = resultado.get("apellidos", "").upper().strip()
        municipio            = resultado.get("municipio", "").upper().strip()
        limitacion_propiedad = resultado.get("limitacion_propiedad", "").strip()
        return jsonify({"placa": placa, "marca": marca, "linea": linea, "modelo": modelo, "clase": clase, "servicio": servicio, "capacidad": capacidad, "cilindrada": cilindrada, "carroceria": carroceria, "tipo_documento": tipo_documento, "cedula": cedula, "apellidos": apellidos, "municipio": municipio, "limitacion_propiedad": limitacion_propiedad})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ocr-guardar-municipio", methods=["POST"])
def ocr_guardar_municipio():
    try:
        data      = request.get_json()
        placa     = data.get("placa", "").upper().strip()
        municipio = data.get("municipio", "").upper().strip()
        if not placa or not municipio:
            return jsonify({"ok": False}), 400
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("UPDATE cache_tarjetas SET municipio=%s, actualizado_en=NOW() WHERE placa=%s", (municipio, placa))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ============================================================
# SIBGA — Avalúos motos bajo cilindraje (≤125cc)
# Datos en tabla retefuente_bajocilindraje
# ============================================================

SIBGA_PERIODO = 2024

def _sibga_col_anio(modelo):
    try:
        anio = int(str(modelo).strip())
    except:
        return "anio_2001_ant"
    if anio <= 2001: return "anio_2001_ant"
    if anio > 2024:  return "anio_2024"
    return f"anio_{anio}"


@app.route("/sibga/marcas", methods=["GET"])
def sibga_marcas():
    """Marcas de motos bajo cilindraje desde BD."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT marca FROM retefuente_bajocilindraje
            WHERE cilindraje <= 125 AND cilindraje > 0
            ORDER BY marca
        """)
        rows = cur.fetchall(); cur.close(); conn.close()
        return jsonify({"marcas": [r[0] for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sibga/lineas", methods=["GET"])
def sibga_lineas():
    """Líneas de una marca desde BD."""
    marca = request.args.get("marca", "").upper().strip()
    if not marca:
        return jsonify({"error": "marca requerida"}), 400
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT linea_id, linea FROM retefuente_bajocilindraje
            WHERE marca=%s AND cilindraje <= 125 AND cilindraje > 0
            ORDER BY linea
        """, (marca,))
        rows = cur.fetchall(); cur.close(); conn.close()
        return jsonify({"lineas": [{"id": r[0], "nombre": r[1]} for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sibga/avaluo", methods=["GET"])
def sibga_avaluo():
    """Avalúo de moto bajo cilindraje desde BD."""
    linea_id = request.args.get("linea_id", type=int)
    modelo   = request.args.get("modelo", type=int)
    if not linea_id or not modelo:
        return jsonify({"error": "linea_id y modelo requeridos"}), 400

    col_anio = _sibga_col_anio(modelo)

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT {col_anio}, linea, cilindraje, marca
            FROM retefuente_bajocilindraje
            WHERE linea_id=%s
        """, (linea_id,))
        row = cur.fetchone(); cur.close(); conn.close()

        if not row or not row[0]:
            return jsonify({"error": "No se encontró avalúo para esa línea y modelo"}), 404

        return jsonify({
            "avaluo":     row[0],
            "linea":      row[1],
            "cilindraje": row[2],
            "marca":      row[3],
            "modelo":     modelo,
            "periodo":    SIBGA_PERIODO,
            "fuente":     "bd"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sibga/opciones", methods=["GET"])
def sibga_opciones():
    """Devuelve opciones de avalúo para motos bajo cilindraje — igual que retefuente/opciones."""
    marca  = request.args.get("marca", "").strip().upper()
    linea  = request.args.get("linea", "").strip().upper()
    modelo = request.args.get("modelo", type=int, default=2020)
    if not marca:
        return jsonify({"error": "marca requerida"}), 400

    col_anio = _sibga_col_anio(modelo)

    try:
        conn = get_db_conn(); cur = conn.cursor()

        # Buscar por marca + palabras de la línea
        cil_sibga = int(re.sub(r'[^0-9]', '', request.args.get('cilindraje','0') or '0') or 0)
        where  = ["marca = %s", f"{col_anio} > 0", "cilindraje <= 125", "cilindraje > 0"]
        params = [marca]

        if linea:
            # Separar letras y números pegados: AK125 -> AK 125
            linea_sep = re.sub(r'([A-Za-z])(\d)', r'\1 \2', linea)
            linea_sep = re.sub(r'(\d)([A-Za-z])', r'\1 \2', linea_sep)
            palabras = [p for p in linea_sep.split() if len(p) > 1][:5]
            if palabras:
                or_conds = []
                for p in palabras:
                    or_conds.append("REPLACE(linea, ' ', '') ILIKE %s")
                    params.append(f'%{p}%')
                where.append("(" + " OR ".join(or_conds) + ")")

        sql = f"""
            SELECT linea_id, linea, cilindraje, {col_anio} as avaluo
            FROM retefuente_bajocilindraje
            WHERE {' AND '.join(where)}
            ORDER BY cilindraje ASC
            LIMIT 200
        """
        cur.execute(sql, params)
        rows = cur.fetchall()

        # Si no hay resultados con filtro de línea, buscar solo por marca
        if not rows and linea:
            cur.execute(f"""
                SELECT linea_id, linea, cilindraje, {col_anio} as avaluo
                FROM retefuente_bajocilindraje
                WHERE marca=%s AND {col_anio} > 0 AND cilindraje <= 125 AND cilindraje > 0
                ORDER BY cilindraje ASC
                LIMIT 40
            """, (marca,))
            rows = cur.fetchall()

        # Ordenar: cilindraje más cercano primero, luego mayor coincidencia con línea
        if linea:
            linea_sep2 = re.sub(r'([A-Za-z])(\d)', r'\1 \2', linea)
            linea_sep2 = re.sub(r'(\d)([A-Za-z])', r'\1 \2', linea_sep2)
            linea_words_s = [w.upper() for w in linea_sep2.split() if len(w) > 1][:5]
        else:
            linea_words_s = []
        def score_sibga(r):
            cil_r = r[2] or 0
            cil_dist = abs(cil_r - cil_sibga) if cil_sibga > 0 else cil_r
            linea_db_sin_esp = (r[1] or '').upper().replace(' ', '')
            lin_score = sum(1 for w in linea_words_s if w in linea_db_sin_esp)
            return (cil_dist, -lin_score)
        rows = sorted(rows, key=score_sibga)[:20]

        cur.close(); conn.close()

        opciones = [{
            "linea_id":   r[0],
            "linea":      r[1],
            "cilindraje": r[2],
            "avaluo":     r[3],
            "retefuente": round(r[3] / 100) if r[3] else 0,
        } for r in rows]

        return jsonify({"opciones": opciones})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
