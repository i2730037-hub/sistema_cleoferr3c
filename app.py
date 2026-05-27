import os
import sys
import uuid
# AÑADIR después de: import uuid
from urllib.parse import quote
# Intento seguro de importar dependencias externas; si faltan, mostrar instrucciones claras y salir.
try:
    from flask import Flask, render_template, request, redirect, url_for, session, flash
    from flask_bcrypt import Bcrypt
    from functools import wraps
    from werkzeug.utils import secure_filename   # ← NUEVO
except Exception as e:
    print("\nERROR: faltan dependencias necesarias para ejecutar la aplicación.")
    print("Instale las dependencias dentro del entorno virtual y vuelva a intentarlo.")
    print("Comandos recomendados (desde el venv activado):")
    print("  pip install -r requirements.txt")
    print("Si no dispone de requirements.txt, instale al menos:")
    print("  pip install flask flask-bcrypt pymysql sqlalchemy")
    print("\nDetalle del error:", e, "\n")
    sys.exit(1)

from db import db
from db2 import get_connection
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = "clave_secreta_cleoferr"
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://prueba-cleofer:Cleoferr@mysql-prueba-cleofer.alwaysdata.net/prueba-cleofer_tienda_online"
app.config["SQLALCHEMY_DATABASE_URI"] = ("mysql+pymysql://prueba-cleofer_anthuanett:Cleoferr@mysql-prueba-cleofer.alwaysdata.net/prueba-cleofer_tienda_online")

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "pool_timeout": 30
}

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
UPLOAD_FOLDER      = os.path.join(app.root_path, 'static', 'img')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024   # 5 MB máximo
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Intentar usar PyMySQL; si no está instalado, hacer fallback a SQLite para desarrollo local.
try:
    import pymysql  # noqa: F401
except ImportError:
    # Si la configuración actual indica MySQL pero falta pymysql, sustituimos por SQLite temporalmente.
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') if 'app' in globals() else ''
    if uri and 'mysql' in uri:
        # Advertir y cambiar a sqlite local
        try:
            app.logger.warning("PyMySQL no encontrado; cambiando temporalmente a sqlite:///cleoferr.db para desarrollo local.")
        except Exception:
            pass
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cleoferr.db'
    elif not uri:
        # Si no hay URI configurada, establecer sqlite por defecto
        try:
            app.logger.info("No existe SQLALCHEMY_DATABASE_URI; usando sqlite:///cleoferr.db por defecto.")
        except Exception:
            pass
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cleoferr.db'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def guardar_imagen(file_field):
    archivo = request.files.get(file_field)
    if not archivo or archivo.filename == '':
        return None
    if not allowed_file(archivo.filename):
        flash('Formato no permitido. Usa JPG, PNG, WEBP o GIF.', 'danger')
        return None
    ext          = archivo.filename.rsplit('.', 1)[1].lower()
    nombre_unico = f"{uuid.uuid4().hex}.{ext}"
    archivo.save(os.path.join(UPLOAD_FOLDER, nombre_unico))
    return nombre_unico
db.init_app(app)
bcrypt = Bcrypt(app)


class Producto(db.Model):
    __tablename__ = "producto"
    id_producto  = db.Column(db.Integer, primary_key=True)
    nombre       = db.Column(db.String(100))
    descripcion  = db.Column(db.Text)
    precio       = db.Column(db.Numeric(10, 2))
    stock        = db.Column(db.Integer, default=0)
    id_categoria = db.Column(db.Integer)
    id_marca     = db.Column(db.Integer)
    estado       = db.Column(db.String(10), default='activo')
    imagen       = db.Column(db.String(255))

    def __repr__(self):
        return f"<Producto {self.nombre}>"


# ── Decorators ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("rol") != "administrador":
            flash("Acceso denegado.", "danger")
            return redirect(url_for("productos"))
        return f(*args, **kwargs)
    return decorated_function

def escritura_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("rol") not in ("administrador", "vendedor"):
            flash("No tienes permisos para realizar esta acción.", "danger")
            return redirect(url_for("productos"))
        return f(*args, **kwargs)
    return decorated_function


# ── Auth ─────────────────────────────────────────────────────
@app.route('/')
def inicio():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        clave  = request.form['clave']
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.id_usuario, u.nombres, u.email, u.contrasena, r.nombre AS rol
            FROM usuario u
            INNER JOIN rol r ON u.id_rol = r.id_rol
            WHERE u.email = %s
        """, (correo,))
        usuario = cursor.fetchone()
        conn.close()

        if usuario and bcrypt.check_password_hash(usuario['contrasena'], clave):
            rol_usuario = (usuario.get('rol') or '').lower()
            # Permitir solo administradores y vendedores en este login
            if rol_usuario not in ('administrador', 'vendedor'):
                # Mensaje breve indicando redirección al login de clientes
                return render_template('login.html', error='Acceso restringido. Si eres cliente usa el acceso de clientes: /login_cliente')
            session['usuario_id'] = usuario['id_usuario']
            session['rol']        = usuario['rol']
            session['nombre']     = usuario['nombres']
            return redirect(url_for('productos'))
        return render_template('login.html', error='Credenciales incorrectas')
    # Botón WhatsApp para recuperar credenciales (personal administrativo)
    msg_admin = quote(
        "Hola Soporte de Inversiones CLEOFERR, soy del personal ADMINISTRATIVO "
        "(Administradora/Vendedora) y presento problemas con mis credenciales de acceso al sistema."
    )
    url_whatsapp = f"https://wa.me/51900555015?text={msg_admin}"
    return render_template('login.html', url_whatsapp=url_whatsapp)


@app.route('/login_cliente', methods=['GET', 'POST'])
def login_cliente():
    if request.method == 'POST':
        correo     = request.form['correo']
        contrasena = request.form['contrasena']
        conn       = get_connection()
        cursor     = conn.cursor(dictionary=True)
        # Busca el cliente por email — la columna nombre puede variar
        cursor.execute("SELECT * FROM cliente WHERE email = %s", (correo,))
        cliente = cursor.fetchone()
        conn.close()

        if cliente:
            # Soporte bcrypt Y MD5 (según cómo esté guardada)
            import hashlib
            hash_md5 = hashlib.md5(contrasena.encode()).hexdigest()
            stored   = cliente.get('contrasena') or cliente.get('password') or ''
            ok = False
            try:
                ok = bcrypt.check_password_hash(stored, contrasena)
            except Exception:
                ok = (stored == hash_md5)

            if ok:
                nombre_cliente = (
                    cliente.get('nombre') or
                    cliente.get('nombres') or
                    cliente.get('name') or
                    cliente.get('email')
                )
                session['usuario_id'] = cliente.get('id_cliente') or cliente.get('id')
                session['rol']        = 'cliente'
                session['nombre']     = nombre_cliente
                return redirect(url_for('catalogo_cliente'))

        return render_template('login_cliente.html', error='Credenciales incorrectas')
    # Botón WhatsApp para recuperar credenciales (clientes)
    msg_cliente = quote(
        "Hola Soporte de Inversiones CLEOFERR, soy un CLIENTE registrado y necesito ayuda "
        "para recuperar mi contraseña o mis datos de acceso al sistema web."
    )
    url_whatsapp = f"https://wa.me/51900555015?text={msg_cliente}"
    return render_template('login_cliente.html', url_whatsapp=url_whatsapp)


@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))



@app.route('/productos')
@login_required
def productos():
    if session.get('rol') == 'cliente':
        return redirect(url_for('catalogo_cliente'))

    categoria = request.args.get('categoria')
    marca     = request.args.get('marca')
    conn      = get_connection()
    cursor    = conn.cursor(dictionary=True)

    query = """
        SELECT p.*, c.nombre AS categoria, m.nombre AS marca
        FROM producto p
        LEFT JOIN categoria c ON p.id_categoria = c.id_categoria
        LEFT JOIN marca m ON p.id_marca = m.id_marca
        WHERE 1=1
    """
    params = []
    if categoria:
        query += " AND c.nombre = %s"
        params.append(categoria)
    if marca:
        query += " AND m.nombre = %s"
        params.append(marca)
    query += " ORDER BY p.id_producto"
    cursor.execute(query, params)
    lista = cursor.fetchall()

    cursor.execute("SELECT * FROM categoria")
    categorias = cursor.fetchall()
    cursor.execute("SELECT * FROM marca")
    marcas = cursor.fetchall()
    conn.close()

    return render_template('productos.html', productos=lista, categorias=categorias, marcas=marcas)


@app.route('/productos/nuevo')
@login_required
@escritura_required
def nuevo_producto():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM categoria")
    categorias = cursor.fetchall()
    cursor.execute("SELECT * FROM marca")
    marcas = cursor.fetchall()
    conn.close()
    return render_template('producto_form.html', categorias=categorias, marcas=marcas)


@app.route('/productos/guardar', methods=['POST'])
@login_required
@escritura_required
def guardar_producto():
    nombre_imagen = guardar_imagen('imagen')
    nuevo = Producto(
        nombre       = request.form['nombre'],
        descripcion  = request.form['descripcion'],
        precio       = request.form['precio'],
        stock        = request.form['stock'],
        id_categoria = request.form['id_categoria'],
        id_marca     = request.form['id_marca'],
        estado       = request.form.get('estado', 'activo'),
        imagen       = nombre_imagen
    )
    db.session.add(nuevo)
    db.session.commit()
    flash("Producto creado correctamente.", "success")
    return redirect(url_for('productos'))


@app.route('/productos/editar/<int:id>')
@login_required
@escritura_required
def editar_producto(id):
    producto = db.get_or_404(Producto, id)
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM categoria")
    categorias = cursor.fetchall()
    cursor.execute("SELECT * FROM marca")
    marcas = cursor.fetchall()
    conn.close()
    return render_template('producto_form.html', producto=producto, categorias=categorias, marcas=marcas)


@app.route('/productos/actualizar/<int:id>', methods=['POST'])
@login_required
@escritura_required
def actualizar_producto(id):
    producto             = db.get_or_404(Producto, id)
    nombre_imagen = guardar_imagen('imagen')            # ← NUEVO
    if nombre_imagen and producto.imagen:               # ← NUEVO: borra imagen vieja
        ruta_vieja = os.path.join(UPLOAD_FOLDER, producto.imagen)
        if os.path.exists(ruta_vieja):
            os.remove(ruta_vieja)
    producto.nombre      = request.form['nombre']
    producto.descripcion = request.form['descripcion']
    producto.precio      = request.form['precio']
    producto.stock       = request.form['stock']
    producto.id_categoria = request.form['id_categoria']
    producto.id_marca    = request.form['id_marca']
    producto.estado      = request.form.get('estado', 'activo')
    if nombre_imagen:                                   # ← CAMBIÓ
        producto.imagen = nombre_imagen
    db.session.commit()
    flash("Producto actualizado correctamente.", "success")
    return redirect(url_for('productos'))


@app.route('/productos/eliminar/<int:id>')
@login_required
@admin_required
def eliminar_producto(id):
    producto = db.get_or_404(Producto, id)
    db.session.delete(producto)
    db.session.commit()
    flash("Producto eliminado correctamente.", "success")
    return redirect(url_for('productos'))



@app.route('/catalogo')
def catalogo_cliente():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, c.nombre AS categoria, m.nombre AS marca
        FROM producto p
        LEFT JOIN categoria c ON p.id_categoria = c.id_categoria
        LEFT JOIN marca m ON p.id_marca = m.id_marca
        WHERE p.estado = 'activo'
        ORDER BY p.id_producto
    """)
    lista = cursor.fetchall()
    conn.close()
    return render_template('catalogo.html', productos=lista)


# ── Gestión de Clientes ───────────────────────────────────────
@app.route('/clientes')
@login_required
@escritura_required
def clientes():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SHOW COLUMNS FROM cliente")
    columnas = [c['Field'] for c in cursor.fetchall()]
    cursor.execute("SELECT * FROM cliente ORDER BY id_cliente DESC")
    lista = cursor.fetchall()
    conn.close()
    return render_template('clientes.html', clientes=lista, columnas=columnas)


@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
@escritura_required
def nuevo_cliente():
    if request.method == 'POST':
        nombre    = request.form['nombre']
        email     = request.form['email']
        telefono  = request.form.get('telefono', '')
        direccion = request.form.get('direccion', '')
        contrasena = request.form.get('contrasena', '123456')
        hash_pw   = bcrypt.generate_password_hash(contrasena).decode('utf-8')

        conn   = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO cliente (nombre, email, telefono, direccion, contrasena) VALUES (%s,%s,%s,%s,%s)",
                (nombre, email, telefono, direccion, hash_pw)
            )
            conn.commit()
            flash("Cliente registrado correctamente.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error al registrar cliente: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('clientes'))
    return render_template('cliente_form.html')


@app.route('/clientes/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@escritura_required
def editar_cliente(id):
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        nombre    = request.form['nombre']
        email     = request.form['email']
        telefono  = request.form.get('telefono', '')
        direccion = request.form.get('direccion', '')
        try:
            cursor.execute(
                "UPDATE cliente SET nombre=%s, email=%s, telefono=%s, direccion=%s WHERE id_cliente=%s",
                (nombre, email, telefono, direccion, id)
            )
            conn.commit()
            flash("Cliente actualizado correctamente.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('clientes'))

    cursor.execute("SELECT * FROM cliente WHERE id_cliente = %s", (id,))
    cliente = cursor.fetchone()
    conn.close()
    if not cliente:
        flash("Cliente no encontrado.", "danger")
        return redirect(url_for('clientes'))
    return render_template('cliente_form.html', cliente=cliente)


@app.route('/clientes/eliminar/<int:id>')
@login_required
@admin_required
def eliminar_cliente(id):
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM cliente WHERE id_cliente = %s", (id,))
        conn.commit()
        flash("Cliente eliminado.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('clientes'))


# ── Inventario ────────────────────────────────────────────────
@app.route('/inventario')
@login_required
@escritura_required
def inventario():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT i.*, p.nombre AS producto_nombre, pr.nombre AS proveedor_nombre,
               u.nombres AS usuario_nombre
        FROM inventario_movimiento i
        LEFT JOIN producto p ON i.id_producto = p.id_producto
        LEFT JOIN proveedor pr ON i.id_proveedor = pr.id_proveedor
        LEFT JOIN usuario u ON i.id_usuario = u.id_usuario
        ORDER BY i.fecha DESC
        LIMIT 200
    """)
    movimientos = cursor.fetchall()

    cursor.execute("SELECT * FROM producto WHERE estado='activo' ORDER BY nombre")
    productos = cursor.fetchall()
    cursor.execute("SELECT * FROM proveedor ORDER BY nombre")
    proveedores = cursor.fetchall()

    # Obtener lista de vendedores (usuarios con rol 'vendedor')
    cursor.execute("""
        SELECT u.id_usuario, u.nombres
        FROM usuario u
        INNER JOIN rol r ON u.id_rol = r.id_rol
        WHERE r.nombre = 'vendedor'
        ORDER BY u.nombres
    """)
    vendedores = cursor.fetchall()

    conn.close()
    return render_template('inventario.html',
                           movimientos=movimientos,
                           productos=productos,
                           proveedores=proveedores,
                           vendedores=vendedores)


@app.route('/inventario/registrar', methods=['POST'])
@login_required
@escritura_required
def registrar_movimiento():
    tipo         = request.form['tipo']           # 'entrada' | 'salida'
    id_producto  = request.form['id_producto']
    # Para compatibilidad: recibimos ambos campos, uno estará vacío según tipo
    id_proveedor = request.form.get('id_proveedor') or None
    id_vendedor  = request.form.get('id_vendedor') or None
    cantidad     = int(request.form['cantidad'])
    precio_unit  = request.form.get('precio_unitario') or 0
    observacion  = request.form.get('observacion', '')
    id_usuario   = session['usuario_id']

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Obtener stock actual
    cursor.execute("SELECT stock FROM producto WHERE id_producto=%s", (id_producto,))
    prod = cursor.fetchone()
    if not prod:
        flash("Producto no encontrado.", "danger")
        conn.close()
        return redirect(url_for('inventario'))

    stock_actual = prod['stock']
    if tipo == 'salida' and cantidad > stock_actual:
        flash(f"Stock insuficiente. Disponible: {stock_actual}", "danger")
        conn.close()
        return redirect(url_for('inventario'))

    nuevo_stock = stock_actual + cantidad if tipo == 'entrada' else stock_actual - cantidad

    # Si es salida y se seleccionó un vendedor, obtener su nombre y añadir a observación
    if tipo == 'salida' and id_vendedor:
        try:
            cursor.execute("SELECT nombres FROM usuario WHERE id_usuario=%s", (id_vendedor,))
            row = cursor.fetchone()
            nombre_vendedor = row['nombres'] if row else None
            if nombre_vendedor:
                observacion = f"Vendedor: {nombre_vendedor}" + (f" - {observacion}" if observacion else "")
        except Exception:
            # no crítico, continuar con la observación sin nombre
            pass

    # Para compatibilidad con la estructura actual, solo llenamos id_proveedor para entradas.
    proveedor_db_value = id_proveedor if tipo == 'entrada' and id_proveedor else None

    try:
        cursor.execute("""
            INSERT INTO inventario_movimiento
                (tipo, id_producto, id_proveedor, cantidad, precio_unitario, observacion, id_usuario, stock_resultante)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (tipo, id_producto, proveedor_db_value, cantidad, precio_unit, observacion, id_usuario, nuevo_stock))

        cursor.execute("UPDATE producto SET stock=%s WHERE id_producto=%s", (nuevo_stock, id_producto))
        conn.commit()
        flash(f"Movimiento de {'entrada' if tipo=='entrada' else 'salida'} registrado. Nuevo stock: {nuevo_stock}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al registrar movimiento: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('inventario'))


# ── Proveedores ───────────────────────────────────────────────
@app.route('/proveedores')
@login_required
@escritura_required
def proveedores():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM proveedor ORDER BY nombre")
    lista = cursor.fetchall()
    conn.close()
    return render_template('proveedores.html', proveedores=lista)


@app.route('/proveedores/nuevo', methods=['GET', 'POST'])
@login_required
@escritura_required
def nuevo_proveedor():
    if request.method == 'POST':
        nombre    = request.form['nombre']
        contacto  = request.form.get('contacto', '')
        telefono  = request.form.get('telefono', '')
        email     = request.form.get('email', '')
        direccion = request.form.get('direccion', '')
        conn      = get_connection()
        cursor    = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO proveedor (nombre, contacto, telefono, email, direccion) VALUES (%s,%s,%s,%s,%s)",
                (nombre, contacto, telefono, email, direccion)
            )
            conn.commit()
            flash("Proveedor registrado.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('proveedores'))
    return render_template('proveedor_form.html')


@app.route('/proveedores/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@escritura_required
def editar_proveedor(id):
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        nombre    = request.form['nombre']
        contacto  = request.form.get('contacto', '')
        telefono  = request.form.get('telefono', '')
        email     = request.form.get('email', '')
        direccion = request.form.get('direccion', '')
        try:
            cursor.execute(
                "UPDATE proveedor SET nombre=%s, contacto=%s, telefono=%s, email=%s, direccion=%s WHERE id_proveedor=%s",
                (nombre, contacto, telefono, email, direccion, id)
            )
            conn.commit()
            flash("Proveedor actualizado.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for('proveedores'))
    cursor.execute("SELECT * FROM proveedor WHERE id_proveedor=%s", (id,))
    proveedor = cursor.fetchone()
    conn.close()
    return render_template('proveedor_form.html', proveedor=proveedor)


@app.route('/proveedores/eliminar/<int:id>')
@login_required
@admin_required
def eliminar_proveedor(id):
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM proveedor WHERE id_proveedor=%s", (id,))
        conn.commit()
        flash("Proveedor eliminado.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('proveedores'))


# Reemplazar/añadir la vista de eliminación evitando sobrescribir un endpoint existente.
# Si ya existe otra función llamada eliminar_proveedor, esta usa un nombre de función y endpoint distintos.
@app.route('/proveedores/eliminar/<int:proveedor_id>', methods=['POST'], endpoint='eliminar_proveedor_post')
def eliminar_proveedor_post(proveedor_id):
    # Verificar sesión / permisos básicos
    if not session.get('usuario_id'):
        flash('Acceso no autorizado.', 'danger')
        return redirect('/login')

    try:
        # Borrado parametrizado para evitar inyecciones
        db.session.execute(text("DELETE FROM proveedores WHERE id = :id"), {'id': proveedor_id})
        db.session.commit()
        flash('Proveedor eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al eliminar proveedor. Revise dependencias o logs.', 'danger')
        app.logger.exception("Error eliminando proveedor %s: %s", proveedor_id, e)
    return redirect('/proveedores')


# ── Pedidos ─────────────────────────────────────────────────
@app.route('/pedidos')
@login_required
@escritura_required
def pedidos():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM pedido ORDER BY fecha DESC LIMIT 200")
        pedidos = cursor.fetchall()
    except Exception:
        pedidos = []
    finally:
        conn.close()
    return render_template('pedidos.html', pedidos=pedidos)


@app.route('/pedidos/detalle/<int:id>')
@login_required
@escritura_required
def pedido_detalle(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    pedido = None
    items = []
    try:
        cursor.execute("SELECT * FROM pedido WHERE id_pedido = %s", (id,))
        pedido = cursor.fetchone()
        # Intentar obtener ítems del pedido si existe la tabla
        cursor.execute("""
            SELECT ip.*, p.nombre AS producto_nombre
            FROM pedido_item ip
            LEFT JOIN producto p ON ip.id_producto = p.id_producto
            WHERE ip.id_pedido = %s
        """, (id,))
        items = cursor.fetchall()
    except Exception:
        pedido = pedido or None
        items = items or []
    finally:
        conn.close()
    return render_template('pedido_detalle.html', pedido=pedido, items=items)


# ── Reportes / Dashboard inventario ─────────────────────────
@app.route('/reportes')
@login_required
@escritura_required
def reportes():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    resumen = {}
    reportes_data = None

    try:
        # Ventas hoy (si existe tabla pedido con campo total y fecha)
        try:
            cursor.execute("SELECT IFNULL(SUM(total),0) AS ventas_hoy FROM pedido WHERE DATE(fecha) = CURDATE()")
            row = cursor.fetchone()
            resumen['ventas_hoy'] = float(row['ventas_hoy'] or 0)
        except Exception:
            resumen['ventas_hoy'] = 0

        # Stock total (suma de stock de productos)
        try:
            cursor.execute("SELECT IFNULL(SUM(stock),0) AS stock_total FROM producto")
            row = cursor.fetchone()
            resumen['stock_total'] = int(row['stock_total'] or 0)
        except Exception:
            resumen['stock_total'] = 0

        # Alertas pendientes
        try:
            cursor.execute("SELECT COUNT(*) AS cnt FROM alertas WHERE resuelta = 0")
            row = cursor.fetchone()
            resumen['alertas'] = int(row['cnt'] or 0)
        except Exception:
            resumen['alertas'] = 0

        # Dashboard inventario: entradas/salidas últimos 30 días (cantidad y valor)
        try:
            cursor.execute("""
                SELECT tipo,
                       IFNULL(SUM(cantidad),0) AS total_cantidad,
                       IFNULL(SUM(precio_unitario * cantidad),0) AS total_valor
                FROM inventario_movimiento
                WHERE fecha >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY tipo
            """)
            agg = cursor.fetchall()
            # Construir filas para la tabla de reportes
            headers = ['Tipo', 'Cantidad (30d)', 'Valor (30d)']
            rows = []
            entradas = salidas = 0
            entradas_val = salidas_val = 0.0
            for a in agg:
                tipo = a.get('tipo') or '–'
                qty  = int(a.get('total_cantidad') or 0)
                val  = float(a.get('total_valor') or 0.0)
                rows.append([tipo, qty, f"{val:.2f}"])
                if tipo == 'entrada':
                    entradas += qty; entradas_val += val
                elif tipo == 'salida':
                    salidas += qty; salidas_val += val
            reportes_data = {
                'headers': headers,
                'rows': rows,
                'entradas_30d': entradas,
                'salidas_30d': salidas,
                'entradas_val_30d': entradas_val,
                'salidas_val_30d': salidas_val
            }
        except Exception:
            reportes_data = None

    finally:
        conn.close()

    return render_template('reportes.html', resumen=resumen, reportes=reportes_data)


# ── Alertas ─────────────────────────────────────────────────
@app.route('/alertas')
@login_required
@escritura_required
def alertas():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM alertas ORDER BY fecha DESC LIMIT 200")
        alertas = cursor.fetchall()
    except Exception:
        alertas = []
    finally:
        conn.close()
    return render_template('alertas.html', alertas=alertas)


@app.route('/alertas/resolver/<int:id>', methods=['POST'])
@login_required
@escritura_required
def alertas_resolver(id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE alertas SET resuelta = 1, fecha_resuelta = NOW() WHERE id = %s", (id,))
        conn.commit()
        flash("Alerta marcada como resuelta.", "success")
    except Exception as e:
        conn.rollback()
        flash("Error al resolver alerta.", "danger")
        app.logger.exception("Error resolviendo alerta %s: %s", id, e)
    finally:
        conn.close()
    return redirect(url_for('alertas'))

# ── Carrito cliente ────────────────────────────────────────────
@app.route('/carrito')
@login_required
def carrito():
    if session.get('rol') != 'cliente':
        return redirect(url_for('productos'))
    return render_template('carrito.html')


@app.route('/carrito/agregar', methods=['POST'])
@login_required
def carrito_agregar():
    data        = request.get_json()
    id_producto = int(data.get('id_producto', 0))
    cantidad    = int(data.get('cantidad', 1))
    carrito     = session.get('carrito', {})
    key         = str(id_producto)
    if key in carrito:
        carrito[key]['cantidad'] += cantidad
    else:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT nombre, precio FROM producto WHERE id_producto=%s", (id_producto,))
        prod = cursor.fetchone()
        conn.close()
        if prod:
            carrito[key] = {
                'id_producto': id_producto,
                'nombre':      prod['nombre'],
                'precio':      float(prod['precio']),
                'cantidad':    cantidad
            }
    session['carrito'] = carrito
    return {'ok': True, 'items': len(carrito)}


@app.route('/carrito/confirmar', methods=['POST'])
@login_required
def carrito_confirmar():
    data  = request.get_json() or {}
    items = data.get('items', []) or []
    # Si no hay items, mantener comportamiento simple
    if not items:
        session['carrito'] = {}
        session['ultimo_pedido'] = []
        return {'ok': True}

    # Si usuario no es cliente, solo guardar en sesión (compatibilidad)
    if session.get('rol') != 'cliente':
        session['carrito'] = {}
        session['ultimo_pedido'] = items
        return {'ok': True}

    # Usuario es cliente: registrar pedido en DB
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # calcular total
        total = 0.0
        for it in items:
            precio = float(it.get('precio', 0) or 0)
            cantidad = int(it.get('cantidad', 1) or 1)
            total += precio * cantidad

        # insertar pedido
        cursor.execute(
            "INSERT INTO pedido (id_cliente, fecha, total, estado) VALUES (%s, NOW(), %s, %s)",
            (session['usuario_id'], total, 'pendiente')
        )
        id_pedido = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
        # MySQL connector may provide lastrowid; if not, fetch max id (fallback)
        if not id_pedido:
            cursor.execute("SELECT LAST_INSERT_ID() AS id")
            row = cursor.fetchone()
            id_pedido = row[0] if row else None

        # insertar items y ajustar stock (si existe tabla producto)
        for it in items:
            id_producto = int(it.get('id_producto') or it.get('id') or 0)
            cantidad    = int(it.get('cantidad', 1))
            precio_unit = float(it.get('precio', 0) or 0)
            try:
                cursor.execute(
                    "INSERT INTO pedido_item (id_pedido, id_producto, cantidad, precio_unitario) VALUES (%s, %s, %s, %s)",
                    (id_pedido, id_producto, cantidad, precio_unit)
                )
            except Exception:
                # si no existe pedido_item, continuar
                pass
            # intentar decrementar stock (no fallar si no existe)
            try:
                cursor.execute("SELECT stock FROM producto WHERE id_producto=%s", (id_producto,))
                r = cursor.fetchone()
                if r:
                    current_stock = int(r[0])
                    nuevo_stock = max(0, current_stock - cantidad)
                    cursor.execute("UPDATE producto SET stock=%s WHERE id_producto=%s", (nuevo_stock, id_producto))
            except Exception:
                pass

        conn.commit()
        session['carrito'] = {}
        session['ultimo_pedido'] = items
        flash(f"Pedido registrado correctamente. ID: {id_pedido}", "success")
        return {'ok': True, 'id_pedido': id_pedido}
    except Exception as e:
        conn.rollback()
        app.logger.exception("Error creando pedido desde carrito: %s", e)
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()


@app.route('/procesar_pago', methods=['POST'])
@login_required
def procesar_pago():
    # Simulación de pago: si hay items en session['ultimo_pedido'] o en session['carrito'], crear pedido si cliente
    if session.get('rol') != 'cliente':
        flash("Solo clientes pueden procesar pagos.", "warning")
        return redirect(url_for('productos'))

    # Preferir items del body si llegan (compatibilidad con pago.html)
    items = session.get('ultimo_pedido') or []
    if not items:
        # intentar obtener desde session carrito dict -> transformar a lista
        carrito = session.get('carrito', {})
        items = []
        for k, v in carrito.items():
            items.append({
                'id_producto': v.get('id_producto') or v.get('id'),
                'cantidad': v.get('cantidad'),
                'precio': v.get('precio')
            })

    if not items:
        flash("No hay items en el carrito para procesar.", "warning")
        return redirect(url_for('catalogo_cliente'))

    # Reusar la lógica de carrito_confirmar para crear pedido (llamar internamente)
    # Construir payload y llamar a la función interna
    from flask import jsonify
    resp = carrito_confirmar()  # devuelve dict o respuesta
    # carrito_confirmar ya hizo commit y flash
    # redirigir al cliente a catálogo o a detalle del pedido si id devuelto
    if isinstance(resp, dict) and resp.get('ok') and resp.get('id_pedido'):
        return redirect(url_for('catalogo_cliente'))
    # si fue Response (JS fetch), intentar interpretar
    try:
        # si retornó flask Response con JSON
        d = resp.get_json() if hasattr(resp, 'get_json') else {}
        if d.get('ok') and d.get('id_pedido'):
            return redirect(url_for('catalogo_cliente'))
    except Exception:
        pass
    # fallback
    return redirect(url_for('catalogo_cliente'))


# ── Cambiar clave ─────────────────────────────────────────────
@app.route('/cambiar_clave', methods=['GET', 'POST'])
@login_required
def cambiar_clave():
    if request.method == 'POST':
        nueva     = request.form['nueva']
        confirmar = request.form['confirmar']
        if nueva != confirmar:
            return render_template('cambiar_clave.html', error='Las contraseñas no coinciden')
        nueva_hash = bcrypt.generate_password_hash(nueva).decode('utf-8')
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE usuario SET contrasena = %s WHERE id_usuario = %s",
                       (nueva_hash, session['usuario_id']))
        conn.commit()
        conn.close()
        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for('productos'))
    return render_template('cambiar_clave.html')


if __name__ == '__main__':
    app.run(debug=True)
